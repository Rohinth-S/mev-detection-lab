"""Audit normalized archived transactions or a saved receipt bundle."""

import argparse
import csv
import hashlib
import json
from io import StringIO
from pathlib import Path

from .artifacts import write_text_atomic

from . import __version__
from .artifacts import require_distinct_paths

from pydantic import TypeAdapter

from .archive import Archive, Economics, ReceiptBundle, Truth
from .audit import audit_archive
from .decoder import decode_receipts
from .fixtures import demo_archive


def _write(path: Path | None, payload: str) -> None:
    if path:
        write_text_atomic(path, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transaction ordering from archived mined receipts")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--input", type=Path, help="normalized mined transaction archive")
    sources.add_argument("--receipts", type=Path, help="captured JSON-RPC receipt bundle and protocol allowlist")
    parser.add_argument("--truth", type=Path, help="independent transaction labels as JSON")
    parser.add_argument("--economics", type=Path, help="independent USD benchmarks as JSON")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ledger-csv", type=Path)
    parser.add_argument("--write-input", type=Path, help="export normalized input")
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--window-blocks", type=int, default=20)
    parser.add_argument("--require-complete-blocks", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    try:
        require_distinct_paths(
            archive=args.input,
            raw_receipts=args.receipts,
            truth=args.truth,
            benchmarks=args.economics,
            report=args.output,
            ledger=args.ledger_csv,
            normalized_output=args.write_input,
        )
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
            raw = args.truth.read_bytes()
            truth = TypeAdapter(list[Truth]).validate_json(raw)
            provenance["truth_sha256"] = hashlib.sha256(raw).hexdigest()
        if args.economics:
            raw = args.economics.read_bytes()
            economics = TypeAdapter(list[Economics]).validate_json(raw)
            provenance["economics_sha256"] = hashlib.sha256(raw).hexdigest()
        report = audit_archive(
            archive, truth=truth, economics=economics, min_confidence=args.min_confidence,
            window_blocks=args.window_blocks, require_complete_blocks=args.require_complete_blocks,
        )
        report["source"] = provenance
        report["producer"] = {"name": "mev-detection-lab", "version": __version__, "format_version": 1}
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.ledger_csv:
            buffer = StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=list(report["rows"][0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(report["rows"])
            write_text_atomic(args.ledger_csv, buffer.getvalue())
        _write(args.write_input, archive.model_dump_json(indent=2) + "\n")
        _write(args.output, payload)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(payload, end="")


if __name__ == "__main__":
    main()
