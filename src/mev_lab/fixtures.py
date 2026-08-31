"""Synthetic mined receipts and separate audit annotations."""

from .archive import Archive, Economics, MinedTransaction, Swap, Truth


def demo_archive() -> tuple[Archive, list[Truth], list[Economics]]:
    pool, other, first, second = (f"0x{n:040x}" for n in range(1, 5))

    def swap(index, address, direct=True):
        return Swap(
            log_index=index, pool=address, token_in=first if direct else second,
            token_out=second if direct else first, amount_in=10, amount_out=9,
        )

    def mined(block, index, sender, *swaps, liquidations=0):
        return MinedTransaction(
            block=block, block_hash=f"0x{block:064x}", index=index, tx_hash=f"0x{block * 100 + index:064x}",
            sender=f"0x{sender:040x}", gas_used=100_000 + index * 1_500,
            effective_gas_price_wei=10**10, swaps=list(swaps), liquidation_events=liquidations,
        )

    rows = [
        mined(100, 0, 81, swap(0, pool)),
        mined(100, 1, 82, swap(1, pool)),
        mined(100, 2, 81, swap(2, pool, False)),
        mined(110, 0, 12, swap(0, pool)),
        mined(110, 1, 14, swap(1, pool), swap(2, other, False)),
        mined(110, 2, 13, liquidations=1),
        mined(130, 0, 12, swap(0, pool), swap(1, other, False)),
        mined(130, 1, 13, swap(2, other)),
        mined(130, 2, 12),
    ]
    labels = ("sandwich", "sandwich", "sandwich", "other", "backrun", "liquidation", "arbitrage", "other", "other")
    truths = [Truth(tx_hash=row.tx_hash, label=label) for row, label in zip(rows, labels, strict=True)]
    economics = [
        Economics(tx_hash=rows[1].tx_hash, reference_price_usd=100, executed_price_usd=100.5, side="buy"),
        Economics(tx_hash=rows[2].tx_hash, gross_extraction_usd=12),
        Economics(tx_hash=rows[4].tx_hash, gross_extraction_usd=5),
    ]
    return Archive(
        chain_id=1, transactions=rows, native_usd_by_block={100: 2_000, 110: 2_020},
        transaction_counts_by_block={100: 3, 110: 3, 130: 3},
    ), truths, economics
