import pytest

from mev_lab.archive import Archive, ReceiptBundle
from mev_lab.audit import audit_archive
from mev_lab.decoder import CODEC, LIQUIDATION_TOPIC, SWAP_TOPIC, decode_receipts
from mev_lab.fixtures import demo_archive


def address(value):
    return f"0x{value:040x}"


def hash_(value):
    return f"0x{value:064x}"


def test_decode_captured_logs_with_integer_signs_and_token_decimals():
    pool = {"address": address(11), "token0": address(10), "token1": address(20), "decimals0": 6, "decimals1": 18}
    v3_data = CODEC.encode(["int256", "int256", "uint160", "uint128", "int24"], [5 * 10**6, -12 * 10**18, 2**96, 10, -7])
    liquidation = CODEC.encode(["uint256", "uint256", "address", "bool"], [123, 100, address(90), True])
    receipt = {
        "blockHash": hash_(42), "blockNumber": "0x2a", "transactionIndex": "0x3", "transactionHash": hash_(88),
        "from": address(80), "gasUsed": "0x186a0", "effectiveGasPrice": hex(1_000_000_000), "status": "0x1",
        "logs": [
            {"address": pool["address"], "topics": [SWAP_TOPIC, hash_(80), hash_(81)], "logIndex": "0x5", "data": "0x" + v3_data.hex()},
            {"address": address(12), "topics": [LIQUIDATION_TOPIC, hash_(10), hash_(20), hash_(33)], "logIndex": "0x7",
             "data": "0x" + liquidation.hex()},
        ],
    }
    bundle = ReceiptBundle(
        chain_id=1, uniswap_v3_pools=[pool], aave_v3_pools=[address(12)], receipts=[receipt],
        native_usd_by_block={42: 2_000},
    )
    archive = decode_receipts(bundle)
    tx = archive.transactions[0]
    assert tx.swaps[0].amount_in == 5 and tx.swaps[0].amount_out == 12
    report = audit_archive(archive)
    assert report["rows"][0]["prediction"] == "liquidation"
    assert report["gas"] == {"observations": 1, "total_usd": 0.2}


def test_no_false_positive_for_ordinary_adjacent_swaps_and_truth_is_independent():
    archive, truth, economic = demo_archive()
    report = audit_archive(archive, truth=truth, economics=economic)
    rows = report["rows"]
    assert report["evaluation"]["accuracy"] == 1.0
    assert rows[3]["prediction"] == "other" and rows[4]["prediction"] == "backrun"
    assert rows[1]["adverse_slippage_bps"] == pytest.approx(50)
    assert rows[2]["net_extraction_usd"] == pytest.approx(9.94)
    assert rows[-1]["gas_usd"] is None

    filtered = audit_archive(archive, truth=truth[3:5], min_confidence=0.85)
    assert filtered["evaluation"]["scored_transactions"] == 2
    assert filtered["evaluation"]["false_negatives"] == 1
    assert [window["suppressed"] for window in filtered["windows"]] == [1, 0]


def test_mixed_block_hashes_are_rejected():
    archive, _, _ = demo_archive()
    data = archive.model_dump()
    data["transactions"][1]["block_hash"] = hash_(99)
    with pytest.raises(ValueError, match="different block hashes"):
        Archive.model_validate(data)
