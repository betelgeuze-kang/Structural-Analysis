#!/usr/bin/env python3
"""Normalize operator-attached MIDAS GEN/SAP2000 full-result CSV exports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from structural_analysis.validation.commercial_frame3d_export import (  # noqa: E402
    CommercialExportError,
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


def _write_outputs_fail_closed(items: list[tuple[Path, Any]]) -> None:
    staged: list[tuple[Path, Path]] = []
    created: list[Path] = []
    try:
        for target, value in items:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_json_bytes(value))
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temp_path, target))
        for temp_path, target in staged:
            os.link(temp_path, target)
            created.append(target)
    except OSError:
        for target in reversed(created):
            try:
                target.unlink()
            except OSError:
                pass
        raise
    finally:
        for temp_path, _ in staged:
            try:
                temp_path.unlink()
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-package", type=Path, required=True)
    parser.add_argument("--adapter-manifest", type=Path, required=True)
    parser.add_argument("--reference-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if any(path.exists() for path in (args.reference_out, args.receipt_out)):
        print("commercial_frame3d_output_exists: outputs are no-overwrite", file=sys.stderr)
        return 1
    output_paths = [args.reference_out, args.receipt_out]
    resolved_outputs = [path.resolve(strict=False) for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs) or any(path.is_symlink() for path in output_paths):
        print("commercial_frame3d_output_paths_invalid: outputs must be distinct non-symlinks", file=sys.stderr)
        return 1
    try:
        reference, receipt = build_reference_ir(
            operator_package_path=args.operator_package,
            adapter_manifest_path=args.adapter_manifest,
        )
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
        output_items = [(args.reference_out, reference), (args.receipt_out, receipt)]
        _write_outputs_fail_closed(output_items)
    except OSError as exc:
        print(f"commercial_frame3d_output_write_failed:{exc.__class__.__name__}", file=sys.stderr)
        return 1
    print(
        "Commercial Frame3D export normalized: "
        f"tool={reference['source']['tool']} nodes={len(reference['nodes'])} "
        f"members={len(reference['members'])} comparison=use-structural-cli "
        "semantic-equivalence=false vv-credit=false promotion=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
