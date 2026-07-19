#!/usr/bin/env python3
"""Validate an Engine v2 ModelIR file without promoting solver readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.model_ir import (  # noqa: E402
    load_json_object_strict,
    validate_model_ir_v2,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_report(path: Path) -> dict[str, Any]:
    try:
        payload = load_json_object_strict(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "structural-analysis-model-ir-validation-report.v1",
            "input_path": str(path),
            "input_sha256": _sha256(path) if path.is_file() else None,
            "schema_valid": False,
            "semantics_valid": False,
            "contract_valid": False,
            "analysis_ready": False,
            "issues": [
                {
                    "code": "input_read_error",
                    "path": "/",
                    "message": str(exc),
                }
            ],
            "blocking_feature_ids": [],
            "derived_blocking_feature_ids": [],
            "content_hash": None,
            "semantic_hash": None,
            "provenance_hash": None,
            "claim_boundary": "model_ir_contract_validation_not_solver_readiness",
        }

    validation = validate_model_ir_v2(payload).to_dict()
    return {
        "schema_version": "structural-analysis-model-ir-validation-report.v1",
        "input_path": str(path),
        "input_sha256": _sha256(path),
        **{key: value for key, value in validation.items() if key != "schema_version"},
        "model_ir_schema_version": validation["schema_version"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Return success for contract-valid documents with explicit blocking features.",
    )
    parser.add_argument("--out", type=Path, help="Optional report output path.")
    args = parser.parse_args(argv)

    report = build_report(args.input)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    contract_valid = bool(report.get("contract_valid"))
    analysis_ready = bool(report.get("analysis_ready"))
    return 0 if contract_valid and (analysis_ready or args.allow_blocked) else 2


if __name__ == "__main__":
    raise SystemExit(main())
