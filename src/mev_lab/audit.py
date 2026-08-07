"""Read-only classification and labeled evaluation of archived blocks."""

from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import groupby
from typing import TypeVar

from .archive import Archive, Economics, MinedTransaction, Swap, Truth
from .detect import confidence

LABELS = ("other", "arbitrage", "backrun", "liquidation", "sandwich")
Annotation = TypeVar("Annotation", Truth, Economics)


def _annotate(values: Sequence[Annotation], valid_hashes: set[str]) -> dict[str, Annotation]:
    rows = {value.tx_hash: value for value in values}
    if len(rows) != len(values) or rows.keys() - valid_hashes:
        raise ValueError("annotation hashes must be unique and refer to captured transactions")
    return rows


def _cycle(swaps: list[Swap]) -> bool:
    return (
        len(swaps) >= 2 and len({swap.pool for swap in swaps}) >= 2
        and swaps[0].token_in == swaps[-1].token_out
        and all(a.token_out == b.token_in for a, b in zip(swaps, swaps[1:]))
    )


def _block_predictions(block: list[MinedTransaction]) -> dict[str, tuple[str, str]]:
    evidence = {tx.tx_hash: ("other", "no_supported_pattern") for tx in block}
    by_pool = defaultdict(list)
    previous = None
    for tx in block:
        swaps = sorted(tx.swaps, key=lambda swap: swap.log_index)
        if tx.liquidation_events:
            evidence[tx.tx_hash] = ("liquidation", "decoded_liquidation_call")
        elif _cycle(swaps):
            prior_swaps = previous.swaps if previous and previous.index + 1 == tx.index else []
            if previous and previous.sender != tx.sender and any(s.pool == swaps[0].pool for s in prior_swaps):
                evidence[tx.tx_hash] = ("backrun", "closed_swap_path_after_other_sender")
            else:
                evidence[tx.tx_hash] = ("arbitrage", "closed_swap_path_across_pools")
        for swap in swaps:
            by_pool[swap.pool].append((tx, swap))
        previous = tx
    for pool_trades in by_pool.values():
        for (first, left), (middle, mid), (last, right) in zip(pool_trades, pool_trades[1:], pool_trades[2:]):
            if (
                first.index < middle.index < last.index and first.sender == last.sender != middle.sender
                and (left.token_in, left.token_out) == (mid.token_in, mid.token_out)
                and (left.token_in, left.token_out) == (right.token_out, right.token_in)
                and all(len(tx.swaps) == 1 and not tx.liquidation_events for tx in (first, middle, last))
            ):
                for tx, reason in ((first, "first_leg"), (middle, "middle_trade"), (last, "last_leg")):
                    if evidence[tx.tx_hash][0] == "other":
                        evidence[tx.tx_hash] = ("sandwich", reason)
    return evidence


def score_labels(rows: list[dict]) -> dict:
    labeled = [row for row in rows if row["truth"] is not None]
    matrix = {actual: dict.fromkeys(LABELS, 0) for actual in LABELS}
    for row in labeled:
        matrix[row["truth"]][row["prediction"]] += 1
    metrics = {}
    for label in LABELS:
        tp = matrix[label][label]
        predicted = sum(matrix[actual][label] for actual in LABELS)
        actual = sum(matrix[label].values())
        precision = tp / predicted if predicted else None
        recall = tp / actual if actual else None
        metrics[label] = {
            "support": actual, "predicted": predicted, "precision": precision, "recall": recall,
            "f1": 2 * tp / (actual + predicted) if actual + predicted else None,
        }
    return {
        "scored_transactions": len(labeled), "accuracy": (
            sum(matrix[label][label] for label in LABELS) / len(labeled) if labeled else None
        ),
        "false_positives": sum(matrix["other"][label] for label in LABELS if label != "other"),
        "false_negatives": sum(matrix[label]["other"] for label in LABELS if label != "other"),
        "per_label": metrics, "confusion": matrix,
    }


def _total(rows: list[dict], key: str) -> dict:
    values = [row[key] for row in rows if row[key] is not None]
    return {"observations": len(values), "total_usd": sum(values) if values else None}


def audit_archive(
    archive: Archive, *, truth: Sequence[Truth] = (), economics: Sequence[Economics] = (),
    min_confidence: float = 0.7, window_blocks: int = 20, require_complete_blocks: bool = False,
) -> dict:
    if not 0 <= min_confidence <= 1 or window_blocks < 1:
        raise ValueError("confidence must be in [0, 1] and block window must be positive")
    hashes = {tx.tx_hash for tx in archive.transactions}
    labeled = _annotate(truth, hashes)
    accounting = _annotate(economics, hashes)
    ordered = sorted(archive.transactions, key=lambda tx: (tx.block, tx.index))
    rows = []
    coverage = []
    windows: dict[int, list[dict]] = defaultdict(list)
    for block_number, batch in groupby(ordered, key=lambda tx: tx.block):
        block = list(batch)
        declared = archive.transaction_counts_by_block.get(block_number)
        coverage_state = "unknown" if declared is None else "complete" if declared == len(block) else "partial"
        coverage.append({"block": block_number, "declared": declared, "captured": len(block), "status": coverage_state})
        predictions = _block_predictions(block)
        for tx in block:
            raw_prediction, evidence = predictions[tx.tx_hash]
            heuristic_score = confidence({"prediction": raw_prediction})
            ordering_label = raw_prediction in {"arbitrage", "backrun", "sandwich"}
            missing_context = require_complete_blocks and ordering_label and coverage_state != "complete"
            suppressed = raw_prediction != "other" and (missing_context or heuristic_score < min_confidence)
            native_usd = archive.native_usd_by_block.get(block_number)
            native_gas_wei = tx.gas_used * tx.effective_gas_price_wei
            native_gas = native_gas_wei / 10**18
            gas = native_gas * native_usd if native_usd is not None else None
            item = accounting.get(tx.tx_hash)
            gross = item.gross_extraction_usd if item else None
            slippage = None
            if item and item.reference_price_usd is not None:
                sign = 1 if item.side == "buy" else -1
                slippage = sign * (item.executed_price_usd / item.reference_price_usd - 1) * 10_000
            row = {
                "block": block_number, "block_hash": tx.block_hash, "index": tx.index, "tx_hash": tx.tx_hash,
                "prediction": "other" if suppressed else raw_prediction, "raw_prediction": raw_prediction,
                "truth": labeled[tx.tx_hash].label if tx.tx_hash in labeled else None, "confidence": heuristic_score,
                "evidence": evidence, "suppressed": suppressed, "gas_native": native_gas, "gas_usd": gas,
                "receipt_success": tx.success, "gas_wei": str(native_gas_wei),
                "block_coverage": coverage_state,
                "suppression_reason": "incomplete_capture" if missing_context else "confidence_floor" if suppressed else None,
                "gross_extraction_usd": gross, "net_extraction_usd": gross - gas if gross is not None and gas is not None else None,
                "adverse_slippage_bps": slippage, "swap_events": len(tx.swaps),
            }
            rows.append(row)
            windows[(block_number // window_blocks) * window_blocks].append(row)
    return {
        "chain_id": archive.chain_id, "min_confidence": min_confidence, "window_blocks": window_blocks,
        "transactions": len(rows), "detections": sum(r["prediction"] != "other" for r in rows),
        "block_coverage": coverage,
        "require_complete_blocks": require_complete_blocks,
        "suppression_reasons": dict(Counter(row["suppression_reason"] for row in rows if row["suppressed"])),
        "evaluation": score_labels(rows), "gas": _total(rows, "gas_usd"),
        "net_extraction": _total(rows, "net_extraction_usd"),
        "windows": [
            {
                "start_block": start, "end_block": start + window_blocks - 1,
                "transactions": len(subset), "labels": dict(Counter(row["prediction"] for row in subset)),
                "suppressed": sum(row["suppressed"] for row in subset), "gas": _total(subset, "gas_usd"),
            }
            for start, subset in sorted(windows.items())
        ],
        "rows": rows,
    }
