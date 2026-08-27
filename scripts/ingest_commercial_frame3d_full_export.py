#!/usr/bin/env python3
"""Normalize operator-attached MIDAS GEN/SAP2000 full-result CSV exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from structural_analysis.validation.commercial_frame3d_export import (  # noqa: E402
    CommercialExportError,
    build_comparison_ir_with_native_cli,
    build_reference_ir,
)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-package", type=Path, required=True)
    parser.add_argument("--adapter-manifest", type=Path, required=True)
    parser.add_argument("--reference-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--native-result", type=Path)
    parser.add_argument("--structural-cli", type=Path)
    parser.add_argument("--comparison-id")
    parser.add_argument("--comparison-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    comparison_options = (
        args.native_result,
        args.structural_cli,
        args.comparison_id,
        args.comparison_out,
    )
    if any(item is not None for item in comparison_options) and not all(
        item is not None for item in comparison_options
    ):
        print(
            "commercial_frame3d_comparison_options_incomplete: "
            "--native-result, --structural-cli, --comparison-id and --comparison-out are atomic",
            file=sys.stderr,
        )
        return 1
    if any(path.exists() for path in (args.reference_out, args.receipt_out)):
        print("commercial_frame3d_output_exists: outputs are no-overwrite", file=sys.stderr)
        return 1
    if args.comparison_out is not None and args.comparison_out.exists():
        print("commercial_frame3d_output_exists: comparison output is no-overwrite", file=sys.stderr)
        return 1
    output_paths = [args.reference_out, args.receipt_out]
    if args.comparison_out is not None:
        output_paths.append(args.comparison_out)
    resolved_outputs = [path.resolve(strict=False) for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs) or any(path.is_symlink() for path in output_paths):
        print("commercial_frame3d_output_paths_invalid: outputs must be distinct non-symlinks", file=sys.stderr)
        return 1
    try:
        reference, receipt = build_reference_ir(
            operator_package_path=args.operator_package,
            adapter_manifest_path=args.adapter_manifest,
        )
        comparison = None
        if args.comparison_out is not None:
            comparison = build_comparison_ir_with_native_cli(
                reference_ir=reference,
                native_result_path=args.native_result,
                structural_cli_path=args.structural_cli,
                comparison_id=args.comparison_id,
            )
            receipt["authority"]["comparison"] = "bounded_cross_code_evaluation"
            receipt["comparison"] = {
                "comparison_id": comparison["comparison_id"],
                "comparison_hash": comparison["comparison_hash"],
                "passed": comparison["summary"]["passed"],
                "external_validation": "not_established",
            }
    except (CommercialExportError, OSError) as exc:
        if isinstance(exc, CommercialExportError):
            print(
                f"commercial_frame3d_ingest_failed:{exc.code}:{exc.path}:{exc.detail}",
                file=sys.stderr,
            )
        else:
            print(f"commercial_frame3d_ingest_failed:{exc.__class__.__name__}", file=sys.stderr)
        return 1

    # All parsing, semantic gates, and optional Rust replay complete before any
    # authoritative output path is materialized.
    try:
        if comparison is not None:
            _write_new(args.comparison_out, comparison)
        _write_new(args.reference_out, reference)
        _write_new(args.receipt_out, receipt)
    except OSError as exc:
        print(f"commercial_frame3d_output_write_failed:{exc.__class__.__name__}", file=sys.stderr)
        return 1
    print(
        "Commercial Frame3D export normalized: "
        f"tool={reference['source']['tool']} nodes={len(reference['nodes'])} "
        f"members={len(reference['members'])} comparison={'yes' if comparison else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
