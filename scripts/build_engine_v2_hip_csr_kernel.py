#!/usr/bin/env python3
"""Build and emit a strict Engine v2 HIP CSR AOT artifact receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip import (  # noqa: E402
    HipCsrKernelArtifactError,
    build_hip_csr_kernel_artifact,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical Engine v2 HIP CSR residual/JVP shared artifact "
            "with explicit gfx targets and a same-root ROCm toolchain."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        help="Explicit gfx target; repeat for a fat artifact.",
    )
    parser.add_argument("--hipcc", type=Path)
    parser.add_argument("--device-libraries", type=Path)
    parser.add_argument("--source", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.output.resolve(strict=False) == args.receipt_out.resolve(strict=False):
        print("Artifact and receipt paths must differ.", file=sys.stderr)
        return 3
    if not args.receipt_out.parent.is_dir():
        print("Receipt output parent does not exist.", file=sys.stderr)
        return 3
    if args.output.exists() or args.receipt_out.exists():
        print("Artifact and receipt outputs must not already exist.", file=sys.stderr)
        return 3
    try:
        receipt = build_hip_csr_kernel_artifact(
            args.output,
            targets=tuple(args.target),
            source_path=args.source,
            hipcc_path=args.hipcc,
            device_libraries_path=args.device_libraries,
        )
        rendered = json.dumps(
            receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        )
        args.receipt_out.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except HipCsrKernelArtifactError as exc:
        print(
            f"HIP CSR AOT build unavailable: {exc.code} {exc.path} {exc.message}",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        try:
            args.output.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"Receipt write failed: {type(exc).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
