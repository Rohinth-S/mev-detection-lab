from mev_lab.detect import Tx, classify
from mev_lab.window import MevWindowConfig, aggregate_windows, filter_detections


def test_window_aggregation_and_allowlist_controls_false_positives():
    rows = classify([
        Tx(10, 0, "bot", "p", "swap", "A", "B", 100),
        Tx(10, 1, "bot", "p", "swap", "B", "A", 101),
        Tx(10, 2, "bot", "p", "swap", "A", "B", 102),
        Tx(11, 0, "trusted", "p", "liquidation", "A", "B", 50),
    ])
    accepted, suppressed = filter_detections(rows, MevWindowConfig(allowlisted_senders=frozenset({"trusted"}), min_confidence=.8))
    assert len(accepted) == 2 and suppressed == 2
    windows = aggregate_windows(rows, MevWindowConfig(allowlisted_senders=frozenset({"trusted"}), min_confidence=.8))
    assert windows[0]["detections"] == 2
    assert windows[0]["notional"] == 201
    assert windows[0]["labels"] == {"arbitrage": 2}
