#!/usr/bin/env python3
"""Build Phase 3 IFC source/license boundary receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT = 10
DIRTY_IFC_CANDIDATE_FILES = [
    "Duplex_A_20110907.ifc",
    "Duplex_Electrical_20121207.ifc",
    "Duplex_MEP_20110907.ifc",
    "Clinic_Architectural.ifc",
    "Clinic_Electrical.ifc",
    "Clinic_HVAC.ifc",
    "Clinic_Plumbing.ifc",
    "Clinic_Structural.ifc",
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


def build_phase3_ifc_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    sources = [
        {
            "source_id": "buildingsmart_pcert_sample_scene",
            "lanes": ["buildingsmart-clean-ifc"],
            "source_url_verified": True,
            "source_url": "https://github.com/buildingSMART/Sample-Test-Files",
            "source_path_url": (
                "https://github.com/buildingSMART/Sample-Test-Files/tree/main/"
                "IFC%204.3.2.0%20%28IFC4X3_ADD2%29/PCERT-Sample-Scene"
            ),
            "candidate_files": ["Building-Structural.ifc", "Infra-Bridge.ifc"],
            "declared_license": "CC-BY-4.0",
            "license_url": "https://raw.githubusercontent.com/buildingSMART/Sample-Test-Files/main/LICENSE",
            "license_review_status": "declared_upstream_license_seen_product_legal_review_pending",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "checksum_status": "missing_until_acquisition_script_fetches_selected_files",
            "expected_output_status": "authored_import_health_contracts_pending_execution",
            "acquisition_receipt_path": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_buildingsmart_ifc_acquisition_receipt.json"
            ),
            "ready_for_phase3_quantity_credit": False,
            "claim_boundary": (
                "Official buildingSMART PCERT sample source identity and declared license "
                "URL are attached, but no source file checksums, product/legal approval, "
                "executed import-health/silent-import-loss gate outputs, or Phase 3 "
                "quantity credit are claimed."
            ),
            "blockers": [
                "selected_file_checksums_missing",
                "product_legal_license_review_pending",
                "import_health_execution_missing",
                "silent_import_loss_gate_not_executed",
            ],
        },
        {
            "source_id": "buildingsmart_community_dirty_samples",
            "lanes": ["buildingsmart-dirty-ifc"],
            "source_url_verified": True,
            "source_url": "https://github.com/buildingsmart-community/Community-Sample-Test-Files",
            "source_path_url": "https://github.com/buildingsmart-community/Community-Sample-Test-Files",
            "candidate_files": DIRTY_IFC_CANDIDATE_FILES,
            "declared_license": "CC-BY-4.0",
            "license_url": (
                "https://raw.githubusercontent.com/buildingsmart-community/"
                "Community-Sample-Test-Files/main/LICENSE"
            ),
            "license_review_status": "declared_upstream_license_seen_per_file_review_pending",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "checksum_status": "missing_until_dirty_file_acquisition",
            "expected_output_status": "authored_negative_import_contracts_pending_execution",
            "acquisition_receipt_path": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
            ),
            "ready_for_phase3_quantity_credit": False,
            "claim_boundary": (
                "Community sample source identity and declared license URL are attached "
                "with eight selected dirty/import-hardening IFC contracts. Per-file "
                "license review, checksums, import-health execution, and quantity "
                "credit remain blocked."
            ),
            "blockers": [
                "selected_file_checksums_missing",
                "per_file_license_review_pending",
                "dirty_import_execution_missing",
                "silent_data_loss_negative_gate_not_executed",
            ],
        },
        {
            "source_id": "ifc_bench_v2_arxiv_query_tasks",
            "lanes": ["ifc-query-and-gui"],
            "source_url_verified": True,
            "source_url": "https://arxiv.org/abs/2605.01698",
            "source_doi": "https://doi.org/10.48550/arXiv.2605.01698",
            "candidate_files": [],
            "declared_license": "paper_license_visible_dataset_license_unverified",
            "license_url": "https://arxiv.org/abs/2605.01698",
            "license_review_status": "dataset_repository_and_per_file_license_missing",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "checksum_status": "missing_until_dataset_repository_and_files_are_attached",
            "expected_output_status": "missing_until_query_answers_authored",
            "ready_for_phase3_quantity_credit": False,
            "claim_boundary": (
                "The arXiv paper is attached only as source identity for ifc-bench v2 "
                "query-task planning. It is not a dataset repository receipt, per-file "
                "license review, file checksum manifest, or GUI task expected-answer receipt."
            ),
            "blockers": [
                "dataset_repository_url_missing",
                "per_file_license_review_pending",
                "query_task_file_checksums_missing",
                "query_expected_answers_missing",
                "gui_task_runner_not_implemented",
            ],
        },
    ]
    selected_clean_import_contract_count = sum(
        len(row["candidate_files"])
        for row in sources
        if "buildingsmart-clean-ifc" in row["lanes"]
    )
    selected_dirty_import_contract_count = sum(
        len(row["candidate_files"])
        for row in sources
        if "buildingsmart-dirty-ifc" in row["lanes"]
    )
    selected_total_import_contract_count = selected_clean_import_contract_count + selected_dirty_import_contract_count
    remaining_import_contract_count = max(
        PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT - selected_total_import_contract_count,
        0,
    )
    count_blockers = ["phase3_ifc_import_case_quantity_credit_missing"]
    if remaining_import_contract_count > 0:
        count_blockers.append("phase3_ifc_import_case_count_below_minimum")
    blockers = sorted({blocker for row in sources for blocker in [*row["blockers"], *count_blockers]})
    return {
        "schema_version": "phase3-ifc-source-license-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase3_ifc_source_license_receipt.py"),
                Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
                Path("scripts/build_phase3_ifc_import_health_execution_receipt.py"),
                Path("src/structural_analysis/benchmark/acquisition.py"),
            ],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "source_count": len(sources),
        "source_url_verified_count": sum(1 for row in sources if row["source_url_verified"]),
        "ready_source_count": sum(1 for row in sources if row["ready_for_phase3_quantity_credit"]),
        "redistribution_allowed_source_count": sum(1 for row in sources if row["redistribution_allowed"]),
        "commercial_use_allowed_source_count": sum(1 for row in sources if row["commercial_use_allowed"]),
        "phase3_ifc_import_case_requirement": {
            "minimum_clean_dirty_import_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
            "selected_clean_import_contract_count": selected_clean_import_contract_count,
            "selected_dirty_import_contract_count": selected_dirty_import_contract_count,
            "selected_total_import_contract_count": selected_total_import_contract_count,
            "remaining_import_contract_count": remaining_import_contract_count,
            "quantity_credit_ready_count": 0,
            "import_health_execution_receipt_path": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_import_health_execution_receipt.json"
            ),
            "status": "blocked",
            "blocker": "phase3_ifc_import_case_quantity_credit_missing",
            "claim_boundary": (
                "The Phase 3 roadmap requires at least 10 clean/dirty IFC import cases. "
                "Current source-license evidence identifies two clean PCERT contracts "
                "and eight dirty/import-hardening community contracts; none have source "
                "checksums, product legal approval, import-health execution, or quantity credit."
            ),
        },
        "sources": sources,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt attaches source identity and upstream license URLs for selected "
            "IFC benchmark candidates. It does not download or bundle IFC files, approve "
            "redistribution/commercial use, attach file checksums, author expected outputs, "
            "or close Phase 3."
        ),
    }


def write_phase3_ifc_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_ifc_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_ifc_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_ifc_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_ifc_source_license_receipt_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_ifc_source_license_receipt_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_ifc_source_license_receipt_mismatch"
    return True, "phase3_ifc_source_license_receipt_consistent"


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
        ok, message = check_phase3_ifc_source_license_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 IFC source/license check: {message}")
        return 0 if ok else 1
    payload = write_phase3_ifc_source_license_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 IFC source/license receipt: "
            f"{payload['status']} | sources={payload['source_count']} | "
            f"ready_sources={payload['ready_source_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
