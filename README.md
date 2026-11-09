# MEV Detection & Transaction Ordering Research Lab

A block-level research harness that reconstructs transaction order and applies transparent rules for arbitrage, liquidation, backrunning, and sandwich patterns. Synthetic blocks make the evaluation reproducible and safe to run offline.

## Architecture
```mermaid
flowchart LR
 L[Decoded block + logs] --> O[Order reconstruction]
 O --> R[Pattern rules]
 R --> C[Classification ledger]
 C --> E[Precision/recall + extraction estimates]
```

## Structural overview
`src/mev_lab/detect.py` contains normalized transaction records, pattern classification, fixtures, and evaluation; `cli.py` prints a compact detection run; `tests/` covers labeled patterns.

## Workflow
1. Decode transactions into a stable `(block,index)` order.
2. Join neighboring swaps and sender/victim relationships.
3. Emit an auditable classification with the triggering rule.
4. Compare labels against a fixture truth set.

## Design rationale
Rules are explicit before any ML is introduced. This makes false positives inspectable and provides a labeled corpus for future models. Production adapters should preserve raw hashes and event topics alongside normalized fields.

## Run
```bash
pip install -e .
python -m mev_lab.cli
pytest -q
```

## Limitations
The fixture does not model private mempools, builder policies, or multi-hop calldata semantics. Classification is research evidence, not an accusation of malicious behavior.
