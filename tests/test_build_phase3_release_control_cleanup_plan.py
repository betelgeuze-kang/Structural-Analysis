from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_release_control_cleanup_plan.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_release_control_cleanup_plan", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_release_control_cleanup_plan_keeps_git_gate_blocked() -> None:
    payload = module.build_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["codex_commit_or_push_performed"] is False
    assert payload["human_git_action_required"] is True
    assert payload["git_clean_clone_status"] == "blocked"
    assert payload["git_clean_clone_contract_pass"] is False
    assert payload["candidate_release_control_commit_set_count"] == 45
    assert len(payload["candidate_release_control_commit_set"]) == 45
    assert payload["track_or_add_required_paths"] == [
        "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_acquisition_plan.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_clean_checkout_reproduction.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_manifest.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_scorecard.json",
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_summary.json",
        "implementation/phase1/release_evidence/productization/phase3_buildingsmart_dirty_ifc_acquisition_receipt.json",
        "implementation/phase1/release_evidence/productization/phase3_buildingsmart_ifc_acquisition_receipt.json",
        "implementation/phase1/release_evidence/productization/phase3_ifc_import_health_execution_receipt.json",
        "implementation/phase1/release_evidence/productization/phase3_ifc_source_license_receipt.json",
        "implementation/phase1/release_evidence/productization/phase3_opensees_medium_source_license_receipt.json",
        "implementation/phase1/release_evidence/productization/phase4_commercial_comparison_import_template.json",
        "implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_contract.json",
        "implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_ingest_validator.json",
        "scripts/build_phase3_benchmark_acquisition_artifacts.py",
        "scripts/build_phase3_benchmark_factory_artifacts.py",
        "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
        "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
        "scripts/build_phase3_ifc_import_health_execution_receipt.py",
        "scripts/build_phase3_ifc_source_license_receipt.py",
        "scripts/build_phase3_opensees_source_license_receipt.py",
        "scripts/build_phase4_commercial_comparison_import_template.py",
        "scripts/build_phase4_commercial_operator_reference_contract.py",
        "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
        "scripts/phase3_benchmark_reproduction_contract.py",
        "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
        "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
        "setup.cfg",
        "src/structural_analysis",
        "tests/test_build_phase3_benchmark_acquisition_artifacts.py",
        "tests/test_build_phase3_benchmark_factory_artifacts.py",
        "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
        "tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py",
        "tests/test_build_phase3_ifc_import_health_execution_receipt.py",
        "tests/test_build_phase3_ifc_source_license_receipt.py",
        "tests/test_build_phase3_opensees_source_license_receipt.py",
        "tests/test_build_phase4_commercial_comparison_import_template.py",
        "tests/test_build_phase4_commercial_operator_reference_contract.py",
        "tests/test_build_phase4_commercial_operator_reference_ingest_validator.py",
        "tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py",
        "tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
        "tests/test_structural_analysis_benchmark_cli.py",
    ]
    assert payload["resolve_or_commit_dirty_tracked_paths"] == [
        "pyproject.toml",
        "scripts/release_evidence_metadata.py",
    ]
    assert payload["path_role_counts"] == {
        "focused_test": 13,
        "generated_productization_evidence": 14,
        "package_config_core_package": 3,
        "reproduction_build_script": 14,
        "source_input_report": 1,
    }
    assert payload["recommended_action_counts"] == {
        "resolve_or_commit_dirty_tracked_input": 2,
        "track_focused_regression_test": 13,
        "track_generated_productization_evidence": 14,
        "track_package_config_or_core_package": 2,
        "track_reproduction_builder_or_runner": 13,
        "track_source_input_or_report": 1,
    }
    rows_by_path = {row["path"]: row for row in payload["path_rows"]}
    assert rows_by_path["pyproject.toml"] == {
        "path": "pyproject.toml",
        "role": "package_config_core_package",
        "git_state": "dirty_tracked",
        "recommended_action": "resolve_or_commit_dirty_tracked_input",
    }
    assert rows_by_path["scripts/build_phase3_benchmark_factory_artifacts.py"]["recommended_action"] == (
        "track_reproduction_builder_or_runner"
    )
    assert rows_by_path[
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_summary.json"
    ]["recommended_action"] == "track_generated_productization_evidence"
    handoff = payload["human_handoff"]
    assert handoff["status"] == "blocked_until_human_git_action"
    assert handoff["codex_executed_commands"] is False
    assert handoff["remote_mutation_required"] is False
    assert handoff["push_or_release_command_included"] is False
    assert handoff["track_or_add_required_paths"] == payload["track_or_add_required_paths"]
    assert handoff["resolve_or_commit_dirty_tracked_paths"] == payload[
        "resolve_or_commit_dirty_tracked_paths"
    ]
    assert handoff["candidate_release_control_commit_set_count"] == 45
    assert handoff["suggested_local_command_args"][0][:3] == ["git", "add", "--"]
    assert handoff["suggested_local_command_args"][1] == [
        "git",
        "add",
        "--",
        "pyproject.toml",
        "scripts/release_evidence_metadata.py",
    ]
    assert not any(command[:2] == ["git", "push"] for command in handoff["suggested_local_command_args"])
    assert not any(command[:2] == ["gh", "release"] for command in handoff["suggested_local_command_args"])
    assert handoff["next_action"] == "owner_review_then_track_or_commit_required_inputs"
    assert "does not commit" in payload["claim_boundary"]
    assert "Dirty tracked paths require owner review" in payload["claim_boundary"]


def test_phase3_release_control_cleanup_plan_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_release_control_cleanup_plan(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_release_control_cleanup_plan_missing:")


def test_phase3_release_control_cleanup_plan_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "cleanup.json"
    module.write_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["codex_commit_or_push_performed"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "phase3_release_control_cleanup_plan_mismatch"
