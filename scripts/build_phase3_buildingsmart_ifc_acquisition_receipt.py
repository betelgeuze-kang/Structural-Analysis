#!/usr/bin/env python3
"""Build buildingSMART IFC acquisition and import-health expectation receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
DEFAULT_OUT = PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"

PCERT_RAW_BASE = (
    "https://raw.githubusercontent.com/buildingSMART/Sample-Test-Files/main/"
    "IFC%204.3.2.0%20%28IFC4X3_ADD2%29/PCERT-Sample-Scene"
)
PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT = 10
ACQUISITION_PYTHON_SNIPPET = (
    "from pathlib import Path; "
    "from urllib.request import urlretrieve; "
    "import sys; "
    "Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True); "
    "urlretrieve(sys.argv[1], sys.argv[2])"
)


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_git_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            prefix = handle.read(128)
    except OSError:
        return False
    return prefix.startswith(b"version https://git-lfs.github.com/spec/v1")


def _attach_local_source_state(repo_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    local_path = repo_root / str(row["local_path"])
    is_lfs_pointer = local_path.exists() and local_path.is_file() and _is_git_lfs_pointer(local_path)
    acquired = local_path.exists() and local_path.is_file() and not is_lfs_pointer
    updated = dict(row)
    updated["source_file_acquired"] = acquired
    updated["source_file_is_git_lfs_pointer"] = is_lfs_pointer
    if acquired:
        updated["source_sha256"] = _sha256(local_path)
        updated["source_checksum_status"] = "attached_from_local_private_corpus"
        updated["blockers"] = [
            blocker
            for blocker in row["blockers"]
            if blocker not in {"source_file_not_acquired", "source_sha256_missing"}
        ]
    else:
        updated["source_file_acquired"] = False
        if is_lfs_pointer:
            updated["source_checksum_status"] = "git_lfs_pointer_not_source_file"
            updated["blockers"] = [
                *row["blockers"],
                "source_file_git_lfs_pointer_not_acquired",
            ]
    return updated


def _selected_file(
    *,
    case_id: str,
    filename: str,
    structural_family: str,
    expected_structural_classes: list[str],
) -> dict[str, Any]:
    local_path = f"private_corpus/phase3/buildingsmart/pcert/{filename}"
    result_path = f"implementation/phase1/release_evidence/productization/{case_id}.model_health_result.json"
    report_path = f"implementation/phase1/release_evidence/productization/{case_id}.model_health_report.json"
    return {
        "case_id": case_id,
        "filename": filename,
        "source_url": f"{PCERT_RAW_BASE}/{filename}",
        "local_path": local_path,
        "structural_family": structural_family,
        "selected_benchmark_lanes": ["buildingsmart-clean-ifc"],
        "truth_class": "geometry_and_import_truth",
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "source_checksum_status": "pending_until_operator_acquisition",
        "source_sha256": "",
        "acquisition_command": [
            "python3",
            "-c",
            ACQUISITION_PYTHON_SNIPPET,
            f"{PCERT_RAW_BASE}/{filename}",
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
        "expected_import_health_contract": {
            "adapter": "structural_analysis.io.ifc.load_ifc_step",
            "source_format": "ifc_step",
            "analysis_type": "model_health",
            "expected_status": "blocked",
            "expected_result_status": "blocked",
            "text_scan_only": True,
            "required_metadata_fields": [
                "record_count",
                "parsed_record_count",
                "entity_counts",
                "structural_entity_count",
                "material_entity_count",
                "section_entity_count",
                "load_related_entity_count",
            ],
            "required_warning_fragments": [
                "IFC adapter is STEP text scan only",
            ],
            "required_blocked_fields": [
                "ifc_geometry_not_canonicalized",
            ],
            "expected_structural_classes_present": expected_structural_classes,
            "silent_import_loss_policy": "fail_until_entity_scan_counts_and_unsupported_features_are_receipt_visible",
            "solver_accuracy_claim": False,
            "phase3_quantity_credit_claim": False,
        },
        "claim_boundary": (
            "This selected-file contract records acquisition and import-health expectations only. "
            "It does not attach the IFC file, compute its source checksum, approve redistribution, "
            "or prove solver-ready geometry/topology."
        ),
        "blockers": [
            "source_file_not_acquired",
            "source_sha256_missing",
            "product_legal_license_review_pending",
            "import_health_execution_missing",
            "silent_import_loss_gate_not_executed",
        ],
    }


def build_phase3_buildingsmart_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    selected_files = [
        _selected_file(
            case_id="buildingsmart_pcert_building_structural",
            filename="Building-Structural.ifc",
            structural_family="building_structural_ifc",
            expected_structural_classes=["IFCBEAM", "IFCCOLUMN", "IFCSLAB", "IFCWALL"],
        ),
        _selected_file(
            case_id="buildingsmart_pcert_infra_bridge",
            filename="Infra-Bridge.ifc",
            structural_family="bridge_ifc",
            expected_structural_classes=["IFCBEAM", "IFCMEMBER", "IFCSLAB"],
        ),
    ]
    selected_files = [_attach_local_source_state(repo_root, row) for row in selected_files]
    selected_clean_import_contract_count = len(selected_files)
    selected_dirty_import_contract_count = 0
    selected_total_import_contract_count = selected_clean_import_contract_count + selected_dirty_import_contract_count
    remaining_import_contract_count = max(
        PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT - selected_total_import_contract_count,
        0,
    )
    source_file_acquired_count = sum(1 for row in selected_files if row["source_file_acquired"])
    source_checksum_attached_count = sum(1 for row in selected_files if row["source_sha256"])
    blockers = sorted(
        {
            blocker
            for row in selected_files
            for blocker in [*row["blockers"], "phase3_ifc_import_case_count_below_minimum"]
        }
    )
    return {
        "schema_version": "phase3-buildingsmart-ifc-acquisition-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
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
        "selected_file_count": len(selected_files),
        "source_file_acquired_count": source_file_acquired_count,
        "source_checksum_attached_count": source_checksum_attached_count,
        "expected_import_health_contract_count": len(selected_files),
        "import_health_execution_count": 0,
        "ready_source_count": 0,
        "redistribution_allowed_source_count": 0,
        "commercial_use_allowed_source_count": 0,
        "phase3_ifc_import_case_requirement": {
            "minimum_clean_dirty_import_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
            "selected_clean_import_contract_count": selected_clean_import_contract_count,
            "selected_dirty_import_contract_count": selected_dirty_import_contract_count,
            "selected_total_import_contract_count": selected_total_import_contract_count,
            "remaining_import_contract_count": remaining_import_contract_count,
            "quantity_credit_ready_count": 0,
            "status": "blocked",
            "blocker": "phase3_ifc_import_case_count_below_minimum",
            "claim_boundary": (
                "The Phase 3 roadmap requires at least 10 clean/dirty IFC import cases. "
                "This receipt authors expected import-health contracts for two clean "
                "buildingSMART files only; no dirty/negative IFC contracts or "
                "quantity-credit-ready IFC cases are claimed."
            ),
        },
        "selected_files": selected_files,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt narrows the buildingSMART clean IFC lane from source identity to "
            "selected-file acquisition and import-health expectation contracts. It records local "
            "private-corpus acquisition/checksums when present, but it does not bundle IFC files, "
            "approve redistribution, execute import-health checks, or close Phase 3."
        ),
    }


def write_phase3_buildingsmart_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_buildingsmart_ifc_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_buildingsmart_ifc_acquisition_receipt_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            f"phase3_buildingsmart_ifc_acquisition_receipt_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_buildingsmart_ifc_acquisition_receipt_mismatch"
    return True, "phase3_buildingsmart_ifc_acquisition_receipt_consistent"


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
        ok, message = check_phase3_buildingsmart_ifc_acquisition_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 buildingSMART IFC acquisition check: {message}")
        return 0 if ok else 1
    payload = write_phase3_buildingsmart_ifc_acquisition_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 buildingSMART IFC acquisition receipt: "
            f"{payload['status']} | selected_files={payload['selected_file_count']} | "
            f"executed={payload['import_health_execution_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
