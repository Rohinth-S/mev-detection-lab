"""Schema for an archive of already-mined transaction receipts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Address = Annotated[str, StringConstraints(to_lower=True, pattern=r"^0x[0-9a-fA-F]{40}$")]
Hash = Annotated[str, StringConstraints(to_lower=True, pattern=r"^0x[0-9a-fA-F]{64}$")]
Number = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Ordinal = Annotated[int, Field(ge=0, le=2**64 - 1)]
Uint256 = Annotated[int, Field(ge=0, le=2**256 - 1)]
Label = Literal["other", "arbitrage", "backrun", "liquidation", "sandwich"]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Swap(Contract):
    log_index: Ordinal
    pool: Address
    token_in: Address
    token_out: Address
    amount_in: Positive
    amount_out: Positive
    amount_in_raw: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,77}$")] | None = None
    amount_out_raw: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,77}$")] | None = None

    @model_validator(mode="after")
    def require_distinct_tokens(self) -> "Swap":
        if self.token_in == self.token_out:
            raise ValueError("swap input and output assets must differ")
        return self


class MinedTransaction(Contract):
    block: Ordinal
    block_hash: Hash
    index: Ordinal
    tx_hash: Hash
    sender: Address
    gas_used: Ordinal
    effective_gas_price_wei: Uint256
    success: bool = True
    liquidation_events: Ordinal = 0
    swaps: list[Swap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_events(self) -> "MinedTransaction":
        indices = [swap.log_index for swap in self.swaps]
        if len(set(indices)) != len(indices):
            raise ValueError("swap log indices must be unique")
        if not self.success and (self.swaps or self.liquidation_events):
            raise ValueError("reverted receipts cannot contain successful protocol events")
        return self


class Archive(Contract):
    chain_id: Annotated[int, Field(gt=0)]
    transactions: list[MinedTransaction] = Field(min_length=1)
    native_usd_by_block: dict[Ordinal, Positive] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_block_identity(self) -> "Archive":
        hashes: dict[int, str] = {}
        heights_by_hash: dict[str, int] = {}
        positions = set()
        tx_hashes = set()
        swap_positions = set()
        for tx in self.transactions:
            if hashes.setdefault(tx.block, tx.block_hash) != tx.block_hash:
                raise ValueError("archive mixes different block hashes at one height")
            if heights_by_hash.setdefault(tx.block_hash, tx.block) != tx.block:
                raise ValueError("one block hash cannot identify multiple block heights")
            key = (tx.block, tx.index)
            if key in positions or tx.tx_hash in tx_hashes:
                raise ValueError("archive contains duplicate transaction identity or ordering position")
            positions.add(key)
            tx_hashes.add(tx.tx_hash)
            for swap in tx.swaps:
                position = (tx.block, swap.log_index)
                if position in swap_positions:
                    raise ValueError("archive contains duplicate decoded log positions in one block")
                swap_positions.add(position)
        return self


class Truth(Contract):
    tx_hash: Hash
    label: Label


class Economics(Contract):
    tx_hash: Hash
    gross_extraction_usd: Number | None = None
    reference_price_usd: Positive | None = None
    executed_price_usd: Positive | None = None
    side: Literal["buy", "sell"] | None = None

    @model_validator(mode="after")
    def validate_benchmark(self) -> "Economics":
        populated = [value is not None for value in (self.reference_price_usd, self.executed_price_usd, self.side)]
        if any(populated) and not all(populated):
            raise ValueError("slippage requires reference price, executed price, and side")
        return self


class Pool(Contract):
    address: Address
    token0: Address
    token1: Address
    decimals0: Annotated[int, Field(ge=0, le=36)]
    decimals1: Annotated[int, Field(ge=0, le=36)]

    @model_validator(mode="after")
    def validate_assets(self) -> "Pool":
        if self.token0 == self.token1:
            raise ValueError("a Uniswap pool requires two different assets")
        return self


class ReceiptBundle(Contract):
    chain_id: Annotated[int, Field(gt=0)]
    uniswap_v3_pools: list[Pool] = Field(default_factory=list)
    aave_v3_pools: list[Address] = Field(default_factory=list)
    native_usd_by_block: dict[Ordinal, Positive] = Field(default_factory=dict)
    receipts: list[dict] = Field(min_length=1)
