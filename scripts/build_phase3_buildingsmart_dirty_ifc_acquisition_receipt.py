#!/usr/bin/env python3
"""Build buildingSMART community dirty IFC acquisition expectation receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
COMMUNITY_RAW_BASE = "https://raw.githubusercontent.com/buildingsmart-community/Community-Sample-Test-Files/main"
PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT = 10
ACQUISITION_PYTHON_SNIPPET = (
    "from pathlib import Path; "
    "from urllib.request import urlretrieve; "
    "import sys; "
    "Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True); "
    "urlretrieve(sys.argv[1], sys.argv[2])"
)


DIRTY_CANDIDATES = [
    {
        "case_id": "buildingsmart_community_duplex_architectural",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment",
        "filename": "Duplex_A_20110907.ifc",
        "expected_negative_signals": ["discipline_model_architectural", "community_sample_not_official"],
    },
    {
        "case_id": "buildingsmart_community_duplex_electrical",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment",
        "filename": "Duplex_Electrical_20121207.ifc",
        "expected_negative_signals": ["discipline_model_electrical", "structural_entities_may_be_sparse"],
    },
    {
        "case_id": "buildingsmart_community_duplex_mep",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment",
        "filename": "Duplex_MEP_20110907.ifc",
        "expected_negative_signals": ["discipline_model_mep", "structural_entities_may_be_sparse"],
    },
    {
        "case_id": "buildingsmart_community_clinic_architectural",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic",
        "filename": "Clinic_Architectural.ifc",
        "expected_negative_signals": ["discipline_model_architectural", "community_sample_not_official"],
    },
    {
        "case_id": "buildingsmart_community_clinic_electrical",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic",
        "filename": "Clinic_Electrical.ifc",
        "expected_negative_signals": ["discipline_model_electrical", "structural_entities_may_be_sparse"],
    },
    {
        "case_id": "buildingsmart_community_clinic_hvac",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic",
        "filename": "Clinic_HVAC.ifc",
        "expected_negative_signals": ["discipline_model_hvac", "structural_entities_may_be_sparse"],
    },
    {
        "case_id": "buildingsmart_community_clinic_plumbing",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic",
        "filename": "Clinic_Plumbing.ifc",
        "expected_negative_signals": ["discipline_model_plumbing", "structural_entities_may_be_sparse"],
    },
    {
        "case_id": "buildingsmart_community_clinic_structural",
        "folder": "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic",
        "filename": "Clinic_Structural.ifc",
        "expected_negative_signals": ["community_sample_not_official", "validation_status_unverified"],
    },
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _source_url(folder: str, filename: str) -> str:
    return f"{COMMUNITY_RAW_BASE}/{quote(folder, safe='/')}/{quote(filename)}"


def _selected_file(row: dict[str, Any]) -> dict[str, Any]:
    case_id = str(row["case_id"])
    filename = str(row["filename"])
    folder = str(row["folder"])
    local_path = f"private_corpus/phase3/buildingsmart/community/{case_id}/{filename}"
    result_path = f"implementation/phase1/release_evidence/productization/{case_id}.model_health_result.json"
    report_path = f"implementation/phase1/release_evidence/productization/{case_id}.model_health_report.json"
    return {
        "case_id": case_id,
        "filename": filename,
        "source_url": _source_url(folder, filename),
        "source_folder": folder,
        "local_path": local_path,
        "structural_family": "community_ifc_import_hardening",
        "selected_benchmark_lanes": ["buildingsmart-dirty-ifc"],
        "truth_class": "negative_or_import_hardening_truth",
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "source_checksum_status": "pending_until_operator_acquisition",
        "source_sha256": "",
        "acquisition_command": [
            "python3",
            "-c",
            ACQUISITION_PYTHON_SNIPPET,
            _source_url(folder, filename),
            local_path,
        ],
        "verification_command_after_acquisition": [
            "python3",
            "-m",
            "structural_analysis.api.cli",
            local_path,
            "--analysis-type",
            "model_health",
            "--out",
            result_path,
            "--report-out",
            report_path,
        ],
        "expected_negative_import_contract": {
            "adapter": "structural_analysis.io.ifc.load_ifc_step",
            "source_format": "ifc_step",
            "analysis_type": "model_health",
            "expected_status": "blocked",
            "expected_result_status": "blocked",
            "text_scan_only": True,
            "required_warning_fragments": [
                "IFC adapter is STEP text scan only",
            ],
            "required_metadata_fields": [
                "record_count",
                "parsed_record_count",
                "entity_counts",
                "structural_entity_count",
                "material_entity_count",
                "section_entity_count",
                "load_related_entity_count",
            ],
            "required_blocked_fields": [
                "ifc_geometry_not_canonicalized",
            ],
            "expected_negative_signals": list(row["expected_negative_signals"]),
            "silent_data_loss_policy": "fail_until_warnings_blocks_and_entity_counts_are_receipt_visible",
            "solver_accuracy_claim": False,
            "phase3_quantity_credit_claim": False,
        },
        "claim_boundary": (
            "This dirty/community IFC contract records acquisition and expected block/warning "
            "behavior only. It does not attach the IFC file, compute its source checksum, "
            "approve redistribution, execute import health, or prove solver-ready geometry."
        ),
        "blockers": [
            "source_file_not_acquired",
            "source_sha256_missing",
            "per_file_license_review_pending",
            "dirty_import_execution_missing",
            "silent_data_loss_negative_gate_not_executed",
        ],
    }


def build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    selected_files = [_selected_file(row) for row in DIRTY_CANDIDATES]
    selected_dirty_count = len(selected_files)
    blockers = sorted({blocker for row in selected_files for blocker in row["blockers"]})
    return {
        "schema_version": "phase3-buildingsmart-dirty-ifc-acquisition-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
                Path("scripts/build_phase3_ifc_source_license_receipt.py"),
                Path("src/structural_analysis/io/ifc/loader.py"),
            ],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_file_count": selected_dirty_count,
        "source_file_acquired_count": 0,
        "source_checksum_attached_count": 0,
        "expected_negative_import_contract_count": selected_dirty_count,
        "dirty_import_execution_count": 0,
        "ready_source_count": 0,
        "redistribution_allowed_source_count": 0,
        "commercial_use_allowed_source_count": 0,
        "phase3_ifc_import_case_requirement": {
            "minimum_clean_dirty_import_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
            "selected_dirty_import_contract_count": selected_dirty_count,
            "quantity_credit_ready_count": 0,
            "status": "blocked",
            "blocker": "dirty_ifc_import_execution_missing",
            "claim_boundary": (
                "These eight community IFC files fill the dirty/negative expected-contract "
                "selection gap, but they do not count toward Phase 3 quantity credit until "
                "files are acquired, checksummed, license-reviewed, and import health is executed."
            ),
        },
        "selected_files": selected_files,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt narrows the buildingSMART dirty IFC lane from source identity to "
            "selected-file acquisition and expected negative/import-hardening contracts. It "
            "does not download or bundle IFC files, compute selected-file checksums, approve "
            "redistribution, execute import-health checks, or close Phase 3."
        ),
    }


def write_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_buildingsmart_dirty_ifc_acquisition_receipt_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            f"phase3_buildingsmart_dirty_ifc_acquisition_receipt_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_buildingsmart_dirty_ifc_acquisition_receipt_mismatch"
    return True, "phase3_buildingsmart_dirty_ifc_acquisition_receipt_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 buildingSMART dirty IFC acquisition check: {message}")
        return 0 if ok else 1
    payload = write_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 buildingSMART dirty IFC acquisition receipt: "
            f"{payload['status']} | selected_files={payload['selected_file_count']} | "
            f"executed={payload['dirty_import_execution_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
