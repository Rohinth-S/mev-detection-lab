"""Audit normalized archived transactions or a saved receipt bundle."""

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from .archive import Archive, Economics, ReceiptBundle, Truth
from .audit import audit_archive
from .decoder import decode_receipts
from .fixtures import demo_archive


def _write(path: Path | None, payload: str) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transaction ordering from archived mined receipts")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--input", type=Path, help="normalized mined transaction archive")
    sources.add_argument("--receipts", type=Path, help="captured JSON-RPC receipt bundle and protocol allowlist")
    parser.add_argument("--truth", type=Path, help="independent transaction labels as JSON")
    parser.add_argument("--economics", type=Path, help="independent USD benchmarks as JSON")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-input", type=Path, help="export normalized input")
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--window-blocks", type=int, default=20)
    args = parser.parse_args()

    try:
        truth, economics = [], []
        source = args.input or args.receipts
        if source:
            raw = source.read_bytes()
            if args.receipts:
                archive = decode_receipts(ReceiptBundle.model_validate_json(raw))
                kind = "rpc_receipt_bundle"
            else:
                archive = Archive.model_validate_json(raw)
                kind = "normalized_archive"
            provenance = {"kind": kind, "sha256": hashlib.sha256(raw).hexdigest()}
        else:
            archive, truth, economics = demo_archive()
            provenance = {"kind": "synthetic"}
        if args.truth:
            truth = TypeAdapter(list[Truth]).validate_json(args.truth.read_bytes())
        if args.economics:
            economics = TypeAdapter(list[Economics]).validate_json(args.economics.read_bytes())
        report = audit_archive(
            archive, truth=truth, economics=economics, min_confidence=args.min_confidence,
            window_blocks=args.window_blocks,
        )
        report["source"] = provenance
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        _write(args.write_input, archive.model_dump_json(indent=2) + "\n")
        _write(args.output, payload)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(payload, end="")


if __name__ == "__main__":
    main()
