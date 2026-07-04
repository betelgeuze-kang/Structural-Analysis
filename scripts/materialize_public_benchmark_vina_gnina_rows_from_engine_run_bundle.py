#!/usr/bin/env python3
"""Materialize Vina/GNINA rows from completed engine-run bundle receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM,
    REQUIRED_ENGINE_RUN_FIELDS,
    materialize_vina_gnina_comparison_adapter,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_ENGINE_RUN_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_bundle.json"
)
DEFAULT_OUT_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json"
)
SCHEMA_VERSION = "public-benchmark-vina-gnina-rows-from-engine-run-bundle.v1"
ROWS_SCHEMA_VERSION = "public-benchmark-vina-gnina-rows.v1"
COMPLETED_RECEIPT_STATUSES = {
    "complete",
    "completed",
    "engine_run_complete",
    "pass",
    "ready",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _required_text(value: Any) -> str:
    return str(value or "").strip()


def _file_checksum_status(
    repo_root: Path,
    path_value: Any,
    expected_checksum: Any,
    *,
    role: str,
) -> tuple[str, dict[str, Any]]:
    path_text = _required_text(path_value)
    expected = _required_text(expected_checksum)
    if not path_text:
        return (
            f"{role}_path_missing",
            {
                "path": "",
                "expected_checksum": expected,
                "actual_checksum": "",
                "checksum_verified": False,
            },
        )
    if not expected:
        return (
            f"{role}_checksum_missing",
            {
                "path": path_text,
                "expected_checksum": expected,
                "actual_checksum": "",
                "checksum_verified": False,
            },
        )
    resolved = _resolve(repo_root, Path(path_text))
    if not resolved.is_file():
        return (
            f"{role}_file_missing",
            {
                "path": path_text,
                "expected_checksum": expected,
                "actual_checksum": "",
                "checksum_verified": False,
            },
        )
    actual = _sha256_file(resolved)
    if actual.lower() != expected.lower():
        return (
            f"{role}_checksum_mismatch",
            {
                "path": path_text,
                "expected_checksum": expected,
                "actual_checksum": actual,
                "checksum_verified": False,
            },
        )
    return (
        "",
        {
            "path": path_text,
            "expected_checksum": expected,
            "actual_checksum": actual,
            "checksum_verified": True,
        },
    )


def _load_required_json_artifact(
    repo_root: Path,
    path_value: Any,
    *,
    role: str,
) -> tuple[dict[str, Any], str]:
    path_text = _required_text(path_value)
    if not path_text:
        return {}, f"{role}_path_missing"
    resolved = _resolve(repo_root, Path(path_text))
    if not resolved.is_file():
        return {}, f"{role}_file_missing"
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"{role}_json_invalid:{exc.__class__.__name__}"
    return payload if isinstance(payload, dict) else {}, ""


def _row_from_bundle_receipt(
    *,
    repo_root: Path,
    bundle_row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = _required_text(bundle_row.get("case_id"))
    engine_id = _required_text(bundle_row.get("engine_id"))
    run_key = f"{case_id}::{engine_id}"
    blockers: list[str] = []
    config, config_blocker = _load_required_json_artifact(
        repo_root,
        bundle_row.get("config_ref"),
        role="engine_config",
    )
    receipt, receipt_blocker = _load_required_json_artifact(
        repo_root,
        bundle_row.get("receipt_template_ref"),
        role="engine_run_receipt",
    )
    if config_blocker:
        blockers.append(config_blocker)
    if receipt_blocker:
        blockers.append(receipt_blocker)
    receipt_status = _required_text(receipt.get("status")).lower()
    if receipt and receipt_status not in COMPLETED_RECEIPT_STATUSES:
        blockers.append("engine_run_receipt_not_complete")

    config_text = _json_text(config) if config else ""
    actual_config_checksum = (
        "sha256:" + hashlib.sha256(config_text.encode("utf-8")).hexdigest()
        if config_text
        else ""
    )
    receipt_config_checksum = _required_text(receipt.get("engine_config_checksum"))
    if receipt and actual_config_checksum and receipt_config_checksum != actual_config_checksum:
        blockers.append("engine_config_checksum_mismatch")

    pose_path = _required_text(
        receipt.get("predicted_ligand_path_or_pose_ref")
        or bundle_row.get("predicted_ligand_path_or_pose_ref")
    )
    pose_checksum = _required_text(receipt.get("predicted_ligand_checksum"))
    pose_blocker, pose_status = _file_checksum_status(
        repo_root,
        pose_path,
        pose_checksum,
        role="predicted_ligand",
    )
    if pose_blocker:
        blockers.append(pose_blocker)

    rmsd = _number(receipt.get("symmetry_aware_rmsd_angstrom"))
    if rmsd is None or rmsd < 0:
        blockers.append("symmetry_aware_rmsd_angstrom_invalid")
    pose_success = _boolean(receipt.get("pose_success"))
    if pose_success is None:
        blockers.append("pose_success_invalid")
    elif rmsd is not None:
        expected = bool(rmsd <= DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM)
        if pose_success is not expected:
            blockers.append("pose_success_inconsistent_with_rmsd_threshold")
    score = _number(receipt.get("score"))
    if score is None:
        blockers.append("score_invalid")
    score_direction = _required_text(receipt.get("score_direction"))
    if score_direction not in {"higher_is_better", "lower_is_better"}:
        blockers.append("score_direction_invalid")

    engine_run = {
        "engine_id": engine_id,
        "docking_run_id": _required_text(
            receipt.get("docking_run_id") or bundle_row.get("docking_run_id")
        ),
        "predicted_ligand_path_or_pose_ref": pose_path,
        "predicted_ligand_checksum": pose_checksum,
        "engine_version": _required_text(receipt.get("engine_version")),
        "engine_config_checksum": receipt_config_checksum,
        "engine_run_provenance_ref": _required_text(
            receipt.get("engine_run_provenance_ref")
            or bundle_row.get("receipt_template_ref")
        ),
        "symmetry_aware_rmsd_angstrom": rmsd,
        "pose_success": pose_success,
        "score": score,
        "score_direction": score_direction,
    }
    for field in REQUIRED_ENGINE_RUN_FIELDS:
        if field not in engine_run or engine_run[field] in {"", None}:
            blockers.append(f"{field}_missing")

    row = {
        "case_id": case_id,
        "complex_id": _required_text(bundle_row.get("complex_id") or config.get("complex_id")),
        "benchmark_split": _required_text(
            bundle_row.get("benchmark_split") or config.get("benchmark_split")
        ),
        "source_family": _required_text(
            bundle_row.get("source_family")
            or config.get("source_family")
            or "CASF/PDBBind + Vina/GNINA"
        ),
        "reference_pose_id": _required_text(
            bundle_row.get("reference_pose_id")
            or config.get("reference_pose_id")
            or f"{case_id}_reference"
        ),
        "source_license_or_accession": _required_text(
            config.get("source_license_or_accession")
        ),
        "source_checksum": _required_text(config.get("source_checksum")),
        "provenance_ref": _required_text(config.get("provenance_ref")),
        "engine_run": engine_run,
    }
    row_status = {
        "run_key": run_key,
        "case_id": case_id,
        "engine_id": engine_id,
        "docking_run_id": engine_run["docking_run_id"],
        "status": "ready" if not blockers else "operator_completion_required",
        "config_ref": _required_text(bundle_row.get("config_ref")),
        "receipt_ref": _required_text(bundle_row.get("receipt_template_ref")),
        "predicted_ligand_status": pose_status,
        "blockers": list(dict.fromkeys(blockers)),
    }
    return row, row_status


def _cases_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            _required_text(row.get("case_id")),
            _required_text(row.get("source_family")),
            _required_text(row.get("benchmark_split")),
            _required_text(row.get("complex_id")),
            _required_text(row.get("reference_pose_id")),
            _required_text(row.get("source_license_or_accession")),
            _required_text(row.get("source_checksum")),
            _required_text(row.get("provenance_ref")),
        )
        case = grouped.setdefault(
            key,
            {
                "case_id": key[0],
                "source_family": key[1],
                "benchmark_split": key[2],
                "complex_id": key[3],
                "reference_pose_id": key[4],
                "source_license_or_accession": key[5],
                "source_checksum": key[6],
                "provenance_ref": key[7],
                "engine_runs": [],
            },
        )
        case["engine_runs"].append(row["engine_run"])
    return list(grouped.values())


def materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle(
    *,
    repo_root: Path = ROOT,
    engine_run_bundle: Path = DEFAULT_ENGINE_RUN_BUNDLE,
    out_rows: Path = DEFAULT_OUT_ROWS,
    out_report: Path = DEFAULT_OUT_REPORT,
) -> dict[str, Any]:
    bundle = _load_json(repo_root, engine_run_bundle)
    bundle_ready = bool(bundle.get("bundle_materialized"))
    raw_bundle_rows = [
        row for row in _as_list(bundle.get("bundle_rows")) if isinstance(row, dict)
    ]
    row_results = (
        [
            _row_from_bundle_receipt(repo_root=repo_root, bundle_row=row)
            for row in raw_bundle_rows
        ]
        if bundle_ready
        else []
    )
    flat_rows = [row for row, _status in row_results]
    row_statuses = [status for _row, status in row_results]
    row_blockers = [
        f"{status['run_key']}::{blocker}"
        for status in row_statuses
        for blocker in _as_list(status.get("blockers"))
    ]
    cases = _cases_from_rows(flat_rows) if flat_rows else []
    adapter_status = "not_run"
    adapter_summary: dict[str, Any] = {}
    adapter_blockers: list[str] = []
    rows_written = False
    if bundle_ready and not row_blockers and cases:
        adapter = materialize_vina_gnina_comparison_adapter(
            {"cases": cases},
            repo_root=repo_root,
            intake_path=engine_run_bundle,
        )
        adapter_status = _required_text(adapter.get("status"))
        adapter_summary = dict(adapter.get("summary") or {})
        adapter_blockers = [
            str(row) for row in _as_list(adapter.get("blockers")) if str(row)
        ]
        if adapter.get("public_benchmark_engine_comparison_ready"):
            rows_payload = {
                "schema_version": ROWS_SCHEMA_VERSION,
                **release_evidence_metadata(
                    input_paths=[
                        Path(
                            "scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
                        ),
                        Path(
                            "scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"
                        ),
                        Path(
                            "scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"
                        ),
                        engine_run_bundle,
                    ],
                    reused_evidence=False,
                    reuse_policy=(
                        "public_benchmark_vina_gnina_rows_materialized_from_completed_"
                        "engine_run_bundle_receipts"
                    ),
                    repo_root=repo_root,
                ),
                "cases": cases,
                "engine_run_bundle_artifact": str(engine_run_bundle),
                "case_count": len(cases),
                "engine_run_count": sum(
                    len(_as_list(case.get("engine_runs"))) for case in cases
                ),
                "claim_boundary": (
                    "These rows are materialized from completed Vina/GNINA engine-run "
                    "bundle receipts after checksum and adapter validation. They do "
                    "not prove Public Benchmark Phase 2 closure until the downstream "
                    "row audit accepts the full public benchmark evidence set."
                ),
            }
            _write_json(repo_root, out_rows, rows_payload)
            rows_written = True
    blockers: list[str] = []
    if not bundle_ready:
        blockers.append("public_benchmark_vina_gnina_engine_run_bundle_not_ready")
    if bundle_ready and not cases:
        blockers.append("public_benchmark_vina_gnina_engine_run_bundle_rows_missing")
    blockers.extend(row_blockers)
    if adapter_blockers:
        blockers.append("public_benchmark_vina_gnina_adapter_validation_failed")
        blockers.extend(adapter_blockers)
    blockers = list(dict.fromkeys(blockers))
    if rows_written:
        status = "rows_materialized"
    elif bundle_ready:
        status = "operator_receipts_completion_required"
    else:
        status = "engine_run_bundle_not_ready"
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path(
                    "scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
                ),
                Path("scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"),
                engine_run_bundle,
            ],
            reused_evidence=False,
            reuse_policy=(
                "public_benchmark_vina_gnina_rows_from_engine_run_bundle_report"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": rows_written,
        "rows_materialized": rows_written,
        "bundle_ready": bundle_ready,
        "engine_run_bundle_artifact": str(engine_run_bundle),
        "out_rows_artifact": str(out_rows),
        "out_report_artifact": str(out_report),
        "case_count": len(cases),
        "engine_run_count": (
            sum(len(_as_list(case.get("engine_runs"))) for case in cases)
            if cases
            else len(raw_bundle_rows)
        ),
        "ready_engine_run_count": sum(
            1 for row in row_statuses if row.get("status") == "ready"
        ),
        "adapter_validation_status": adapter_status,
        "adapter_validation_summary": adapter_summary,
        "row_statuses": row_statuses,
        "blockers": blockers,
        "commands": {
            "rerun_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py "
                "--fail-blocked"
            ),
            "rerun_rows_materialization": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py "
                f"--engine-run-bundle {engine_run_bundle} --out-rows {out_rows} "
                f"--out-report {out_report} --fail-blocked"
            ),
            "materialize_adapter": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {out_rows} "
                f"--out-adapter {PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                f"--out-report {PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
            "rerun_phase2_row_audit": (
                "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
                f"--vina-gnina-rows {out_rows} --fail-blocked"
            ),
        },
        "summary": {
            "bundle_ready": bundle_ready,
            "rows_materialized": rows_written,
            "case_count": len(cases),
            "engine_run_count": sum(
                len(_as_list(case.get("engine_runs"))) for case in cases
            )
            if cases
            else len(raw_bundle_rows),
            "ready_engine_run_count": sum(
                1 for row in row_statuses if row.get("status") == "ready"
            ),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This helper only promotes completed Vina/GNINA engine-run bundle "
            "receipts into adapter rows after file checksum and adapter validation. "
            "It does not run engines, compute RMSD, invent scores, or close Public "
            "Benchmark Phase 2 by itself."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--engine-run-bundle", type=Path, default=DEFAULT_ENGINE_RUN_BUNDLE)
    parser.add_argument("--out-rows", type=Path, default=DEFAULT_OUT_ROWS)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle(
        repo_root=args.repo_root,
        engine_run_bundle=args.engine_run_bundle,
        out_rows=args.out_rows,
        out_report=args.out_report,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-rows-from-engine-run-bundle: "
            f"{payload['status']} | runs={payload['engine_run_count']} | "
            f"written={payload['rows_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
