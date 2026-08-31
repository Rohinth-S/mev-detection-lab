"""Windowed MEV detection rollups and configurable false-positive controls."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from collections.abc import Iterable, Sequence

from .detect import Tx, confidence


@dataclass(frozen=True)
class MevWindowConfig:
    window_blocks: int = 20
    min_confidence: float = 0.7
    min_amount: float = 0.0
    allowlisted_senders: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.window_blocks < 1 or not 0 <= self.min_confidence <= 1 or self.min_amount < 0:
            raise ValueError("window_blocks, confidence, and amount thresholds are invalid")


def _tx(row: dict) -> Tx:
    transaction = row.get("tx")
    if not isinstance(transaction, Tx):
        raise ValueError("detection rows must contain a Tx under 'tx'")
    return transaction


def filter_detections(rows: Iterable[dict], config: MevWindowConfig = MevWindowConfig()) -> tuple[list[dict], int]:
    """Return accepted detections and the count suppressed by policy."""
    accepted: list[dict] = []
    suppressed = 0
    for row in rows:
        tx = _tx(row)
        score = confidence(row)
        if (row.get("prediction") == "other" or score < config.min_confidence
                or tx.sender in config.allowlisted_senders or tx.amount < config.min_amount):
            suppressed += 1
            continue
        enriched = dict(row)
        enriched["confidence"] = score
        accepted.append(enriched)
    return accepted, suppressed


def aggregate_windows(rows: Sequence[dict], config: MevWindowConfig = MevWindowConfig()) -> list[dict]:
    """Aggregate accepted MEV detections into block windows."""
    accepted, suppressed = filter_detections(rows, config)
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in accepted:
        groups[(_tx(row).block // config.window_blocks) * config.window_blocks].append(row)
    result = []
    for start in sorted(groups):
        group = groups[start]
        transactions = [_tx(row) for row in group]
        labels: dict[str, int] = defaultdict(int)
        for row in group:
            labels[row["prediction"]] += 1
        result.append({"window_start": start, "window_end": start + config.window_blocks - 1,
                       "detections": len(group), "notional": sum(tx.amount for tx in transactions),
                       "senders": sorted({tx.sender for tx in transactions}), "labels": dict(labels),
                       "mean_confidence": sum(row["confidence"] for row in group) / len(group),
                       "suppressed": suppressed})
    return result
