#!/usr/bin/env python3
"""Convert the strict Phase 0 MIDAS/MGT subset to audited ModelIR v2."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.io.midas.v2 import import_mgt_v2  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--model-ir-out", type=Path)
    parser.add_argument("--audit-out", type=Path)
    parser.add_argument("--canonical-mgt-out", type=Path)
    args = parser.parse_args(argv)

    try:
        result = import_mgt_v2(args.input)
    except (OSError, UnicodeDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "input_error",
                    "input": str(args.input),
                    "message": str(exc),
                    "claim_boundary": (
                        "phase0_supported_subset_import_audit_not_full_midas_interoperability"
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 3

    if args.audit_out is not None:
        _atomic_write(args.audit_out, result.audit.canonical_json + "\n")
    if args.model_ir_out is not None and result.model_ir is not None:
        _atomic_write(args.model_ir_out, result.model_ir.canonical_json + "\n")
    if args.canonical_mgt_out is not None and result.canonical_mgt is not None:
        _atomic_write(args.canonical_mgt_out, result.canonical_mgt)

    audit = result.audit.to_dict()
    summary = {
        "status": audit["status"],
        "ready": result.ready,
        "input": str(args.input),
        "source_sha256": audit["source"]["sha256"],
        "model_ir_content_hash": audit["model_ir"]["content_hash"],
        "audit_content_hash": result.audit.content_hash,
        "capabilities": audit["capabilities"],
        "diagnostic_codes": [row["code"] for row in audit["diagnostics"]],
        "outputs": {
            "model_ir": str(args.model_ir_out) if args.model_ir_out and result.model_ir else None,
            "audit": str(args.audit_out) if args.audit_out else None,
            "canonical_mgt": (
                str(args.canonical_mgt_out)
                if args.canonical_mgt_out and result.canonical_mgt is not None
                else None
            ),
        },
        "claim_boundary": audit["claim_boundary"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ready else 2


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
