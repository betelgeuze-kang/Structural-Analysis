from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase4_commercial_operator_reference_ingest_validator.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase4_commercial_operator_reference_ingest_validator",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_package(tmp_path: Path) -> Path:
    raw_input = tmp_path / "operator_refs" / "case-a" / "model.etabs"
    solver_a_raw = tmp_path / "operator_refs" / "case-a" / "solver-a.csv"
    solver_b_raw = tmp_path / "operator_refs" / "case-a" / "solver-b.csv"
    solver_a_normalized = tmp_path / "operator_refs" / "case-a" / "solver-a.normalized.json"
    solver_b_normalized = tmp_path / "operator_refs" / "case-a" / "solver-b.normalized.json"
    for path, text in [
        (raw_input, "model"),
        (solver_a_raw, "solver-a"),
        (solver_b_raw, "solver-b"),
        (solver_a_normalized, "{}"),
        (solver_b_normalized, "{}"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    package = {
        "case_id": "case-a",
        "modeling_convention_id": "convention-a",
        "permission_scope": {
            "comparison_use_allowed": True,
            "redistribution_allowed": False,
            "approval_receipt": "operator-permission-ticket-1",
        },
        "reference_solvers": [
            {
                "engine_name": "ETABS",
                "engine_version": "v1",
                "normalized_result_file": "operator_refs/case-a/solver-a.normalized.json",
            },
            {
                "engine_name": "SAP2000",
                "engine_version": "v2",
                "normalized_result_file": "operator_refs/case-a/solver-b.normalized.json",
            },
        ],
        "raw_input_files": ["operator_refs/case-a/model.etabs"],
        "raw_result_files": [
            "operator_refs/case-a/solver-a.csv",
            "operator_refs/case-a/solver-b.csv",
        ],
        "file_checksums": {
            "operator_refs/case-a/model.etabs": _sha256(raw_input),
            "operator_refs/case-a/solver-a.csv": _sha256(solver_a_raw),
            "operator_refs/case-a/solver-b.csv": _sha256(solver_b_raw),
            "operator_refs/case-a/solver-a.normalized.json": _sha256(solver_a_normalized),
            "operator_refs/case-a/solver-b.normalized.json": _sha256(solver_b_normalized),
        },
        "modeling_convention": {
            "unit_system": "kN-m",
            "local_axis_convention": "operator-declared",
            "rigid_offset_policy": "operator-declared",
            "end_release_policy": "operator-declared",
            "diaphragm_policy": "operator-declared",
            "mass_source_policy": "operator-declared",
            "self_weight_policy": "operator-declared",
            "material_modulus_convention": "operator-declared",
            "shell_formulation": "operator-declared",
            "mesh_density": "operator-declared",
            "damping_policy": "operator-declared",
            "p_delta_policy": "operator-declared",
            "eigen_solver": "operator-declared",
            "load_combinations": ["LC1"],
            "convergence_tolerance": "operator-declared",
        },
        "unsupported_features": [],
        "warnings": [],
    }
    package_path = tmp_path / "operator_package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return package_path


def test_operator_reference_ingest_validator_blocks_without_package() -> None:
    payload = module.build_phase4_commercial_operator_reference_ingest_validator(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase4-commercial-operator-reference-ingest-validator.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["validation_result"]["blockers"] == ["operator_reference_package_missing"]
    assert payload["remaining_blockers"] == ["operator_reference_package_missing"]
    assert "ingest preflight only" in payload["claim_boundary"]


def test_operator_reference_ingest_validator_blocks_incomplete_package(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps(
            {
                "case_id": "case-a",
                "modeling_convention_id": "convention-a",
                "permission_scope": {"comparison_use_allowed": False},
                "reference_solvers": [{"engine_name": "ETABS"}],
                "raw_input_files": ["missing.etabs"],
                "raw_result_files": [],
                "file_checksums": {},
                "modeling_convention": {},
                "unsupported_features": [],
                "warnings": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package,
    )

    blockers = payload["validation_result"]["blockers"]
    assert payload["status"] == "blocked"
    assert "comparison_use_permission_missing" in blockers
    assert "permission_approval_receipt_missing" in blockers
    assert "two_reference_solver_comparison_not_available" in blockers
    assert "checksum_missing:missing.etabs" in blockers
    assert "modeling_convention_missing:unit_system" in blockers


def test_operator_reference_ingest_validator_accepts_complete_package_as_preflight_only(tmp_path: Path) -> None:
    package = _complete_package(tmp_path)

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package,
    )

    assert payload["status"] == "pass"
    assert payload["contract_pass"] is True
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["validation_result"]["distinct_reference_solver_count"] == 2
    assert payload["validation_result"]["checked_file_count"] == 5
    assert payload["validation_result"]["checksum_declared_count"] == 5
    assert payload["remaining_blockers"] == [
        "commercial_cross_solver_execution_missing",
        "operator_comparison_trace_rows_missing",
        "phase4_two_solver_comparison_metrics_not_recorded",
    ]


def test_operator_reference_ingest_validator_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "validator.json"
    module.write_phase4_commercial_operator_reference_ingest_validator(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_commercial_operator_reference_ingest_validator_mismatch"
