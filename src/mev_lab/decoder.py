"""Decode a small event ABI from previously captured JSON-RPC receipts."""

import re

from eth_abi.exceptions import DecodingError
from web3 import Web3

from .archive import Archive, MinedTransaction, Pool, ReceiptBundle, Swap

SWAP_TOPIC = "0x" + Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
LIQUIDATION_TOPIC = "0x" + Web3.keccak(
    text="LiquidationCall(address,address,address,uint256,uint256,address,bool)",
).hex()
CODEC = Web3().codec


def _quantity(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})", value):
        raise ValueError("receipt quantity must be canonical hexadecimal")
    return int(value, 16)


def _decode(types: list[str], data: str) -> tuple:
    if not re.fullmatch(r"0x[0-9a-fA-F]*", str(data)) or len(data) != 2 + 64 * len(types):
        raise ValueError("unexpected ABI word count")
    try:
        return CODEC.decode(types, bytes.fromhex(data[2:]))
    except (DecodingError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid ABI log data") from exc


def _validate_topics(topics: list[str], count: int) -> None:
    if len(topics) != count or any(not re.fullmatch(r"0x[0-9a-f]{64}", topic) for topic in topics):
        raise ValueError("invalid indexed topic words")


def _swap(pool: Pool, log: dict) -> Swap | None:
    amount0, amount1, _, _, _ = _decode(["int256", "int256", "uint160", "uint128", "int24"], log["data"])
    if amount0 > 0 and amount1 < 0:
        amount_in_raw, amount_out_raw = amount0, -amount1
        values = (pool.token0, pool.token1, amount0 / 10**pool.decimals0, -amount1 / 10**pool.decimals1)
    elif amount1 > 0 and amount0 < 0:
        amount_in_raw, amount_out_raw = amount1, -amount0
        values = (pool.token1, pool.token0, amount1 / 10**pool.decimals1, -amount0 / 10**pool.decimals0)
    else:
        return None
    return Swap(
        log_index=_quantity(log["logIndex"]), pool=pool.address, token_in=values[0], token_out=values[1],
        amount_in=values[2], amount_out=values[3],
        amount_in_raw=str(amount_in_raw), amount_out_raw=str(amount_out_raw),
    )


def _check_log_identity(receipt: dict, log: dict) -> None:
    for field in ("blockHash", "transactionHash"):
        if field in log and log[field].lower() != receipt[field].lower():
            raise ValueError(f"log {field} disagrees with its receipt")
    for field in ("blockNumber", "transactionIndex"):
        if field in log and _quantity(log[field]) != _quantity(receipt[field]):
            raise ValueError(f"log {field} disagrees with its receipt")


def decode_receipts(bundle: ReceiptBundle) -> Archive:
    pools = {pool.address: pool for pool in bundle.uniswap_v3_pools}
    lending = set(bundle.aave_v3_pools)
    if (
        len(pools) != len(bundle.uniswap_v3_pools) or len(lending) != len(bundle.aave_v3_pools)
        or pools.keys() & lending
    ):
        raise ValueError("contract addresses must be unique across protocol mappings")
    transactions = []
    for receipt in bundle.receipts:
        try:
            if "blockHash" not in receipt or not receipt["blockHash"]:
                raise ValueError("every receipt must have a mined block hash")
            status = _quantity(receipt["status"])
            if status not in (0, 1):
                raise ValueError("receipt status must be 0 or 1")
            swaps = []
            liquidations = 0
            for log in receipt["logs"]:
                _check_log_identity(receipt, log)
                address = log["address"].lower()
                topics = [topic.lower() for topic in log["topics"]]
                if not topics:
                    continue
                if address in pools and topics[0] == SWAP_TOPIC:
                    if log.get("removed"):
                        raise ValueError("removed Uniswap Swap log")
                    _validate_topics(topics, 3)
                    if not status:
                        raise ValueError("invalid Uniswap Swap log")
                    swap = _swap(pools[address], log)
                    if swap is not None:
                        swaps.append(swap)
                elif address in lending and topics[0] == LIQUIDATION_TOPIC:
                    if log.get("removed"):
                        raise ValueError("removed Aave LiquidationCall log")
                    _validate_topics(topics, 4)
                    if not status:
                        raise ValueError("invalid Aave LiquidationCall log")
                    _decode(["uint256", "uint256", "address", "bool"], log["data"])
                    liquidations += 1
            transactions.append(MinedTransaction(
                block=_quantity(receipt["blockNumber"]), block_hash=receipt["blockHash"],
                index=_quantity(receipt["transactionIndex"]), tx_hash=receipt["transactionHash"],
                sender=receipt["from"], success=bool(status),
                gas_used=_quantity(receipt["gasUsed"]), effective_gas_price_wei=_quantity(receipt["effectiveGasPrice"]),
                swaps=sorted(swaps, key=lambda swap: swap.log_index), liquidation_events=liquidations,
            ))
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("receipt is missing a required JSON-RPC field") from exc
    return Archive(chain_id=bundle.chain_id, transactions=transactions, native_usd_by_block=bundle.native_usd_by_block)
