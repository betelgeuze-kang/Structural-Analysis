#!/usr/bin/env python3
"""Execute Phase 3 IFC import-health checks for locally acquired IFC files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_phase3_buildingsmart_dirty_ifc_acquisition_receipt import (  # noqa: E402
    build_phase3_buildingsmart_dirty_ifc_acquisition_receipt,
)
from build_phase3_buildingsmart_ifc_acquisition_receipt import (  # noqa: E402
    build_phase3_buildingsmart_ifc_acquisition_receipt,
)
from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT = 10
SILENT_IMPORT_LOSS_REQUIRED_ACCOUNTING_FIELDS = [
    "record_count",
    "parsed_record_count",
    "entity_counts",
    "structural_entity_count",
    "material_entity_count",
    "section_entity_count",
    "load_related_entity_count",
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"elapsed_seconds", "generated_at", "stdout_excerpt", "stderr_excerpt"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _candidate_rows(repo_root: Path, source_commit_sha: str | None) -> list[dict[str, Any]]:
    clean = build_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    dirty = build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    rows: list[dict[str, Any]] = []
    for source, lane_kind, contract_key in (
        (clean, "clean", "expected_import_health_contract"),
        (dirty, "dirty", "expected_negative_import_contract"),
    ):
        for row in source["selected_files"]:
            rows.append(
                {
                    "case_id": row["case_id"],
                    "lane_kind": lane_kind,
                    "filename": row["filename"],
                    "source_url": row["source_url"],
                    "local_path": row["local_path"],
                    "selected_benchmark_lanes": row["selected_benchmark_lanes"],
                    "truth_class": row["truth_class"],
                    "contract": row[contract_key],
                }
            )
    return rows


def _run_model_health(repo_root: Path, local_path: Path, case_id: str) -> dict[str, Any]:
    result_out = repo_root / PRODUCTIZATION / f"{case_id}.model_health_result.json"
    report_out = repo_root / PRODUCTIZATION / f"{case_id}.model_health_report.json"
    command = [
        sys.executable,
        "-m",
        "structural_analysis.api.cli",
        str(local_path),
        "--analysis-type",
        "model_health",
        "--out",
        str(result_out),
        "--report-out",
        str(report_out),
    ]
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_ROOT)
        if not env.get("PYTHONPATH")
        else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    return {
        "command": " ".join(command),
        "return_code": completed.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_excerpt": completed.stdout[-2000:],
        "stderr_excerpt": completed.stderr[-4000:],
        "result_path": str(result_out.relative_to(repo_root)),
        "report_path": str(report_out.relative_to(repo_root)),
        "result_exists": result_out.exists(),
        "report_exists": report_out.exists(),
        "result": _load_json(result_out) if result_out.exists() else {},
        "report": _load_json(report_out) if report_out.exists() else {},
    }


def _case_receipt(repo_root: Path, row: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    local_path = repo_root / row["local_path"]
    base = {
        "case_id": row["case_id"],
        "lane_kind": row["lane_kind"],
        "filename": row["filename"],
        "source_url": row["source_url"],
        "local_path": row["local_path"],
        "selected_benchmark_lanes": row["selected_benchmark_lanes"],
        "truth_class": row["truth_class"],
        "source_file_acquired": local_path.exists(),
        "source_sha256": "",
        "import_health_executed": False,
        "import_health_contract_pass": False,
        "silent_import_loss_gate": {
            "status": "blocked",
            "contract_pass": False,
            "executed": False,
            "silent_import_loss_zero": False,
            "visible_entity_accounting": False,
            "required_accounting_fields": SILENT_IMPORT_LOSS_REQUIRED_ACCOUNTING_FIELDS,
            "blockers": [
                "source_file_not_acquired",
                "source_sha256_missing",
                "silent_import_loss_gate_not_executed",
            ],
        },
        "quantity_credit_ready": False,
        "blockers": [],
        "claim_boundary": (
            "This case can receive Phase 3 IFC quantity credit only after the source file "
            "is locally acquired, checksummed, product/legal review remains visible, "
            "and model_health execution proves the expected blocked/warning contract."
        ),
    }
    if not local_path.exists():
        base["status"] = "blocked"
        base["blockers"] = [
            "source_file_not_acquired",
            "source_sha256_missing",
            "import_health_execution_missing",
        ]
        return base

    base["source_sha256"] = _sha256(local_path)
    if not execute:
        base["status"] = "blocked"
        base["blockers"] = ["import_health_execution_not_requested"]
        base["silent_import_loss_gate"]["blockers"] = [
            "silent_import_loss_gate_not_executed"
        ]
        return base

    execution = _run_model_health(repo_root, local_path, str(row["case_id"]))
    result = execution["result"]
    result_metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
    report = execution["report"]
    unsupported = {
        item.get("kind")
        for item in result.get("unsupported_features", [])
        if isinstance(item, dict)
    }
    warnings = result.get("warnings", [])
    required_warning_fragments = row["contract"].get("required_warning_fragments", [])
    warning_pass = all(
        any(fragment in warning for warning in warnings)
        for fragment in required_warning_fragments
    )
    blocked_pass = all(
        field in unsupported
        for field in row["contract"].get("required_blocked_fields", [])
    )
    status_pass = report.get("status") == row["contract"].get("expected_status")
    contract_pass = bool(
        execution["return_code"] in {0, 2}
        and execution["result_exists"]
        and execution["report_exists"]
        and warning_pass
        and blocked_pass
        and status_pass
    )
    accounting_fields = row["contract"].get(
        "required_metadata_fields",
        SILENT_IMPORT_LOSS_REQUIRED_ACCOUNTING_FIELDS,
    )
    visible_entity_accounting = all(field in result_metrics for field in accounting_fields)
    unsupported_visible = bool(result.get("unsupported_features"))
    warning_visible = bool(warnings)
    silent_gate_blockers = [
        *(["visible_entity_accounting_missing"] if not visible_entity_accounting else []),
        *(["unsupported_feature_visibility_missing"] if not unsupported_visible else []),
        *(["import_warning_visibility_missing"] if not warning_visible else []),
        *(["import_health_contract_failed"] if not contract_pass else []),
    ]
    silent_import_loss_gate = {
        "status": "pass" if not silent_gate_blockers else "blocked",
        "contract_pass": not silent_gate_blockers,
        "executed": True,
        "silent_import_loss_zero": not silent_gate_blockers,
        "visible_entity_accounting": visible_entity_accounting,
        "required_accounting_fields": accounting_fields,
        "record_count": result_metrics.get("record_count"),
        "parsed_record_count": result_metrics.get("parsed_record_count"),
        "structural_entity_count": result_metrics.get("structural_entity_count"),
        "material_entity_count": result_metrics.get("material_entity_count"),
        "section_entity_count": result_metrics.get("section_entity_count"),
        "load_related_entity_count": result_metrics.get("load_related_entity_count"),
        "unsupported_feature_count": len(result.get("unsupported_features", [])),
        "warning_count": len(warnings),
        "blockers": silent_gate_blockers,
    }
    base.update(
        {
            "status": "blocked",
            "import_health_executed": True,
            "import_health_contract_pass": contract_pass,
            "silent_import_loss_gate": silent_import_loss_gate,
            "execution": execution,
            "blockers": [] if contract_pass else ["import_health_contract_failed"],
        }
    )
    return base


def build_phase3_ifc_import_health_execution_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    rows = _candidate_rows(repo_root, source_commit_sha)
    case_receipts = [_case_receipt(repo_root, row, execute=execute) for row in rows]
    blockers = sorted({blocker for row in case_receipts for blocker in row["blockers"]})
    if not blockers:
        blockers = ["phase3_ifc_import_case_quantity_credit_blocked_pending_license_review"]
    executed_count = sum(1 for row in case_receipts if row["import_health_executed"])
    acquired_count = sum(1 for row in case_receipts if row["source_file_acquired"])
    checksum_count = sum(1 for row in case_receipts if row["source_sha256"])
    contract_pass_count = sum(1 for row in case_receipts if row["import_health_contract_pass"])
    silent_gate_pass_count = sum(
        1 for row in case_receipts if row["silent_import_loss_gate"]["contract_pass"]
    )
    visible_entity_accounting_count = sum(
        1 for row in case_receipts if row["silent_import_loss_gate"]["visible_entity_accounting"]
    )
    quantity_credit_ready_count = sum(1 for row in case_receipts if row["quantity_credit_ready"])
    silent_import_loss_gate_blockers = sorted(
        {
            blocker
            for row in case_receipts
            for blocker in row["silent_import_loss_gate"]["blockers"]
        }
    )
    silent_import_loss_gate_contract_pass = bool(
        len(case_receipts) >= PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT
        and silent_gate_pass_count == len(case_receipts)
        and quantity_credit_ready_count >= PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT
    )
    return {
        "schema_version": "phase3-ifc-import-health-execution-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase3_ifc_import_health_execution_receipt.py"),
                Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
                Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
                Path("src/structural_analysis/api/cli.py"),
                Path("src/structural_analysis/io/ifc/loader.py"),
            ],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "candidate_case_count": len(case_receipts),
        "minimum_clean_dirty_import_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
        "source_file_acquired_count": acquired_count,
        "source_checksum_attached_count": checksum_count,
        "import_health_execution_count": executed_count,
        "import_health_contract_pass_count": contract_pass_count,
        "visible_entity_accounting_case_count": visible_entity_accounting_count,
        "silent_import_loss_gate_pass_count": silent_gate_pass_count,
        "silent_import_loss_gate": {
            "status": "pass" if silent_import_loss_gate_contract_pass else "blocked",
            "contract_pass": silent_import_loss_gate_contract_pass,
            "silent_import_loss_zero": silent_import_loss_gate_contract_pass,
            "required_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
            "candidate_case_count": len(case_receipts),
            "source_file_acquired_count": acquired_count,
            "source_checksum_attached_count": checksum_count,
            "import_health_execution_count": executed_count,
            "visible_entity_accounting_case_count": visible_entity_accounting_count,
            "case_gate_pass_count": silent_gate_pass_count,
            "quantity_credit_ready_count": quantity_credit_ready_count,
            "blockers": silent_import_loss_gate_blockers
            or ["phase3_ifc_import_case_quantity_credit_missing"],
            "claim_boundary": (
                "This gate proves zero silent IFC import loss only when every selected "
                "clean/dirty IFC case is acquired, checksummed, import-health executed, "
                "entity-accounted, and quantity-credit ready. Text-scan accounting is "
                "not solver-ready geometry evidence."
            ),
        },
        "quantity_credit_ready_count": quantity_credit_ready_count,
        "case_receipts": case_receipts,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt is the execution gate for the 10 selected Phase 3 IFC clean/dirty "
            "contracts. It does not download files, approve licenses, approve redistribution, "
            "or turn text-scan import health into solver accuracy evidence."
        ),
    }


def write_phase3_ifc_import_health_execution_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    payload = build_phase3_ifc_import_health_execution_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        execute=execute,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_ifc_import_health_execution_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
    execute: bool = True,
) -> tuple[bool, str]:
    expected = build_phase3_ifc_import_health_execution_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        execute=execute,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_ifc_import_health_execution_receipt_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            f"phase3_ifc_import_health_execution_receipt_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_ifc_import_health_execution_receipt_mismatch"
    return True, "phase3_ifc_import_health_execution_receipt_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    execute = not args.no_execute
    if args.check:
        ok, message = check_phase3_ifc_import_health_execution_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
            execute=execute,
        )
        print(f"Phase 3 IFC import-health execution check: {message}")
        return 0 if ok else 1
    payload = write_phase3_ifc_import_health_execution_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
        execute=execute,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 IFC import-health execution receipt: "
            f"{payload['status']} | candidates={payload['candidate_case_count']} | "
            f"executed={payload['import_health_execution_count']} | "
            f"credit_ready={payload['quantity_credit_ready_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
