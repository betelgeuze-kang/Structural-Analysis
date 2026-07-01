from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_benchmark_factory_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_benchmark_factory_artifacts", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_benchmark_factory_seed_has_manifest_and_scorecard() -> None:
    artifacts = module.build_phase3_benchmark_factory_artifacts(repo_root=REPO_ROOT)
    manifest = artifacts["manifest"]
    scorecard = artifacts["scorecard"]
    summary = artifacts["summary"]
    reproducibility_bundle = artifacts["reproducibility_bundle"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["phase3_closure_claim"] is False
    assert summary["full_phase3_quantity_gates_met"] is False
    assert summary["analytic_component_quantity_gate_met"] is True
    package_runner = summary["package_benchmark_runner"]
    assert package_runner["status"] == "ready"
    assert package_runner["contract_pass"] is True
    assert package_runner["entry_point"] == (
        "structural-analysis-benchmark = structural_analysis.benchmark.cli:main"
    )
    assert package_runner["module_command"] == "python -m structural_analysis.benchmark.cli"
    assert package_runner["invocation_surfaces"] == ["python_api_factory", "package_cli"]
    assert package_runner["scope"] == (
        "generated analytic-small, element-patch, and nonlinear material-mesh seed only"
    )
    assert package_runner["same_manifest_as_python_factory"] is True
    assert package_runner["same_scorecard_as_python_factory"] is True
    assert package_runner["expected_output_contract_pass"] is True
    assert package_runner["factory_manifest_checksum"] == (
        package_runner["package_cli_manifest_checksum"]
    )
    assert package_runner["factory_scorecard_checksum"] == (
        package_runner["package_cli_scorecard_checksum"]
    )
    assert package_runner["phase3_closure_claim"] is False
    assert package_runner["developer_preview_release_candidate_claim"] is False
    assert summary["case_count"] == 30
    assert summary["pass_count"] == 30
    assert summary["lanes"] == [
        "analytic-small",
        "element-patch",
        "nonlinear-material-mesh",
    ]
    assert summary["lane_case_counts"] == {
        "analytic-small": 20,
        "element-patch": 6,
        "nonlinear-material-mesh": 4,
    }
    expected_comparison_count = sum(
        len(row["expected_outputs"]) for row in manifest["rows"]
    )
    assert summary["scorecard_expected_output_comparison_count"] == expected_comparison_count
    assert (
        summary["scorecard_expected_output_comparison_pass_count"]
        == expected_comparison_count
    )
    assert summary["scorecard_expected_output_contract_pass"] is True
    assert package_runner["expected_output_comparison_count"] == expected_comparison_count
    assert (
        package_runner["expected_output_comparison_pass_count"]
        == expected_comparison_count
    )
    assert summary["artifacts"]["reproducibility_bundle"].endswith(
        "phase3_benchmark_factory_seed_reproducibility_bundle.json"
    )
    assert summary["artifacts"]["clean_checkout_reproduction"].endswith(
        "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
    )
    assert summary["artifacts"]["git_clean_clone_reproduction"].endswith(
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
    )
    assert summary["artifacts"]["acquisition_plan"].endswith("phase3_benchmark_acquisition_plan.json")
    assert summary["artifacts"]["opensees_source_license_receipt"].endswith(
        "phase3_opensees_medium_source_license_receipt.json"
    )
    assert summary["all_cases_have_license_checksum_truth_and_expected_outputs"] is True
    assert summary["remaining_quantity_targets"] == {
        "analytic_component_cases_required": 20,
        "analytic_component_cases_current": 30,
        "medium_structural_models_required": 5,
        "medium_structural_models_current": 0,
        "large_structural_models_required": 2,
        "large_structural_models_current": 0,
        "ifc_clean_dirty_import_cases_required": 10,
        "ifc_clean_dirty_import_cases_current": 0,
    }
    remaining_lanes = {row["lane"]: row for row in summary["remaining_corpus_lanes"]}
    assert set(remaining_lanes) == {
        "element-patch",
        "opensees-medium",
        "opensees-megatall",
        "buildingsmart-clean-ifc",
        "buildingsmart-dirty-ifc",
        "ifc-query-and-gui",
        "commercial-cross-solver",
        "large-model-performance",
    }
    assert remaining_lanes["element-patch"] == {
        "lane": "element-patch",
        "status": "seed_ready",
        "case_count": 6,
    }
    assert all(
        row["status"] == "not_started"
        for row in summary["remaining_corpus_lanes"]
        if row["lane"] != "element-patch"
    )

    assert manifest["case_count"] == 30
    assert manifest["lanes"] == [
        "analytic-small",
        "element-patch",
        "nonlinear-material-mesh",
    ]
    assert {
        row["element_count"]
        for row in manifest["rows"]
        if row["lane"] == "analytic-small"
    } == {1, 2, 3, 4}
    assert sum(1 for row in manifest["rows"] if row["lane"] == "element-patch") == 6
    assert sum(1 for row in manifest["rows"] if row["lane"] == "nonlinear-material-mesh") == 4
    nonlinear_rows = [row for row in manifest["rows"] if row["lane"] == "nonlinear-material-mesh"]
    assert {row["analysis_type"] for row in nonlinear_rows} == {"nonlinear_static_material_mesh"}
    assert {row["structural_family"] for row in nonlinear_rows} == {
        "nonlinear_axial_material_mesh"
    }
    for row in manifest["rows"]:
        assert row["truth_class"] == "analytic_truth"
        assert row["checksum"].startswith("sha256:")
        assert row["license"]["redistribution_allowed"] is True
        assert row["license"]["commercial_use_allowed"] is True
        assert row["expected_outputs"]

    assert scorecard["status"] == "pass"
    assert scorecard["contract_pass"] is True
    assert scorecard["expected_output_comparison_count"] == expected_comparison_count
    assert (
        scorecard["expected_output_comparison_pass_count"]
        == expected_comparison_count
    )
    assert scorecard["expected_output_contract_pass"] is True
    assert all(row["contract_pass"] is True for row in scorecard["rows"])
    manifest_by_case = {row["case_id"]: row for row in manifest["rows"]}
    for row in scorecard["rows"]:
        expected_output_fields = set(manifest_by_case[row["case_id"]]["expected_outputs"])
        comparison_fields = {comparison["field"] for comparison in row["expected_output_comparisons"]}
        assert comparison_fields == expected_output_fields
        assert row["expected_output_contract_pass"] is True
        assert all(
            comparison["status"] == "pass"
            for comparison in row["expected_output_comparisons"]
        )
    assert all(row["metrics"]["residual_formula"] == "F_internal_minus_F_external" for row in scorecard["rows"])
    assert all(row["metrics"]["regularization_used"] is False for row in scorecard["rows"])
    assert all(row["metrics"]["fallback_used"] is False for row in scorecard["rows"])
    assert all(row["convergence_history"] for row in scorecard["rows"])
    assert all(
        "residual_norm" in history_row and "relative_increment" in history_row
        for row in scorecard["rows"]
        for history_row in row["convergence_history"]
    )
    nonlinear_score_rows = [
        row for row in scorecard["rows"] if row["lane"] == "nonlinear-material-mesh"
    ]
    assert len(nonlinear_score_rows) == 4
    assert all(row["metrics"]["residual_gate_passed"] is True for row in nonlinear_score_rows)
    assert all(row["metrics"]["increment_gate_passed"] is True for row in nonlinear_score_rows)
    assert all(row["metrics"]["assembled_jacobian_fd_pass"] is True for row in nonlinear_score_rows)
    assert all(row["metrics"]["series_force_equilibrium_pass"] is True for row in nonlinear_score_rows)

    assert reproducibility_bundle["status"] == "ready"
    assert reproducibility_bundle["contract_pass"] is True
    assert reproducibility_bundle["clean_checkout_reproducibility_claim"] == "command_replay_contract_only"
    assert reproducibility_bundle["clean_checkout_executed"] is False
    assert (
        reproducibility_bundle["git_clean_clone_reproducibility_claim"]
        == "local_file_protocol_clone_when_preflight_passes"
    )
    assert reproducibility_bundle["git_clean_clone_executed"] is False
    assert reproducibility_bundle["phase3_closure_claim"] is False
    assert reproducibility_bundle["developer_preview_release_candidate_claim"] is False
    assert set(reproducibility_bundle["artifact_paths"]) == {
        "acquisition_plan",
        "buildingsmart_dirty_ifc_acquisition_receipt",
        "buildingsmart_ifc_acquisition_receipt",
        "commercial_comparison_import_template",
        "phase4_analytic_physical_fallback_scorecard",
        "commercial_operator_reference_contract",
        "commercial_operator_reference_ingest_validator",
        "ifc_import_health_execution_receipt",
        "ifc_source_license_receipt",
        "manifest",
        "opensees_source_license_receipt",
        "scorecard",
        "summary",
    }
    assert set(reproducibility_bundle["stable_artifact_checksums"]) == {
        "acquisition_plan",
        "buildingsmart_dirty_ifc_acquisition_receipt",
        "buildingsmart_ifc_acquisition_receipt",
        "commercial_comparison_import_template",
        "phase4_analytic_physical_fallback_scorecard",
        "commercial_operator_reference_contract",
        "commercial_operator_reference_ingest_validator",
        "ifc_import_health_execution_receipt",
        "ifc_source_license_receipt",
        "manifest",
        "opensees_source_license_receipt",
        "scorecard",
        "summary",
    }
    assert all(
        checksum.startswith("sha256:")
        for checksum in reproducibility_bundle["stable_artifact_checksums"].values()
    )
    normalization = reproducibility_bundle["stable_checksum_normalization"]
    assert "source_commit_sha" in normalization["excluded_keys"]
    assert "source_file_acquired" in normalization["excluded_keys"]
    assert "execution" in normalization["excluded_keys"]
    assert "ignored local corpora" in normalization["rationale"]
    assert reproducibility_bundle["expected_scorecard"] == {
        "status": "pass",
        "case_count": 30,
        "pass_count": 30,
        "lanes": ["analytic-small", "element-patch", "nonlinear-material-mesh"],
        "lane_case_counts": {
            "analytic-small": 20,
            "element-patch": 6,
            "nonlinear-material-mesh": 4,
        },
        "expected_output_comparison_count": expected_comparison_count,
        "expected_output_comparison_pass_count": expected_comparison_count,
        "expected_output_contract_pass": True,
        "residual_formula": "F_internal_minus_F_external",
        "regularization_used": False,
        "fallback_used": False,
    }
    assert "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase3_benchmark_acquisition_artifacts.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase3_ifc_import_health_execution_receipt.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase3_opensees_source_license_receipt.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase4_commercial_comparison_import_template.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase4_analytic_physical_fallback_scorecard.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase4_commercial_operator_reference_contract.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert "python3 scripts/build_phase4_commercial_operator_reference_ingest_validator.py --check" in reproducibility_bundle[
        "regeneration_commands"
    ]
    assert any(
        "python3 -m structural_analysis.benchmark.cli" in command
        for command in reproducibility_bundle["regeneration_commands"]
    )
    assert any(
        "tests/test_structural_analysis_benchmark_cli.py" in command
        for command in reproducibility_bundle["regeneration_commands"]
    )
    assert (
        "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py"
        in reproducibility_bundle["regeneration_commands"]
    )
    assert (
        "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py"
        in reproducibility_bundle["regeneration_commands"]
    )
    assert reproducibility_bundle["clean_checkout_reproduction_receipt_path"].endswith(
        "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
    )
    assert reproducibility_bundle["git_clean_clone_reproduction_receipt_path"].endswith(
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
    )
    assert reproducibility_bundle["required_git_clean_clone_inputs"] == module.path_strings(
        module.GIT_CLEAN_CLONE_REQUIRED_INPUTS
    )
    assert "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_benchmark_acquisition_artifacts.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_opensees_source_license_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_ifc_source_license_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_ifc_import_health_execution_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "scripts/build_phase4_analytic_physical_fallback_scorecard.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "src/structural_analysis" in reproducibility_bundle["required_git_clean_clone_inputs"]
    assert "tests/test_structural_analysis_benchmark_cli.py" in reproducibility_bundle[
        "required_clean_checkout_inputs"
    ]
    assert "tests/test_build_phase3_opensees_source_license_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "tests/test_build_phase3_ifc_source_license_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "tests/test_build_phase3_ifc_import_health_execution_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert "tests/test_build_phase4_analytic_physical_fallback_scorecard.py" in reproducibility_bundle[
        "required_git_clean_clone_inputs"
    ]
    assert (
        "implementation/phase1/release_evidence/productization/phase4_analytic_physical_fallback_scorecard.json"
        in reproducibility_bundle["required_git_clean_clone_inputs"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json"
        in reproducibility_bundle["required_git_clean_clone_inputs"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json"
        not in reproducibility_bundle["input_checksums"]
    )
    assert all(
        not key.startswith("implementation/phase1/release_evidence/productization/")
        for key in reproducibility_bundle["input_checksums"]
    )
    assert "full Phase 3 closure" in reproducibility_bundle["claim_boundary"]


def test_phase3_benchmark_factory_check_detects_missing_outputs(tmp_path: Path) -> None:
    ok, message = module.check_phase3_benchmark_factory_artifacts(
        repo_root=REPO_ROOT,
        manifest_out=tmp_path / "missing_manifest.json",
        scorecard_out=tmp_path / "missing_scorecard.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase3_benchmark_factory_missing:")


def test_phase3_benchmark_factory_check_detects_stale_outputs(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    acquisition_plan = tmp_path / "acquisition_plan.json"
    buildingsmart_ifc_acquisition = tmp_path / "buildingsmart_ifc_acquisition.json"
    buildingsmart_dirty_ifc_acquisition = tmp_path / "buildingsmart_dirty_ifc_acquisition.json"
    ifc_source_license = tmp_path / "ifc_source_license.json"
    ifc_import_health_execution = tmp_path / "ifc_import_health_execution.json"
    opensees_source_license = tmp_path / "opensees_source_license.json"
    commercial_comparison_template = tmp_path / "commercial_comparison_template.json"
    phase4_analytic_physical_fallback = tmp_path / "phase4_analytic_physical_fallback.json"
    commercial_operator_reference_contract = tmp_path / "commercial_operator_reference_contract.json"
    commercial_operator_reference_ingest_validator = (
        tmp_path / "commercial_operator_reference_ingest_validator.json"
    )
    scorecard = tmp_path / "scorecard.json"
    summary = tmp_path / "summary.json"
    reproducibility_bundle = tmp_path / "reproducibility_bundle.json"
    module.write_phase3_benchmark_factory_artifacts(
        repo_root=REPO_ROOT,
        manifest_out=manifest,
        acquisition_plan_out=acquisition_plan,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition,
        ifc_source_license_out=ifc_source_license,
        ifc_import_health_execution_out=ifc_import_health_execution,
        opensees_source_license_out=opensees_source_license,
        commercial_comparison_template_out=commercial_comparison_template,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator,
        scorecard_out=scorecard,
        summary_out=summary,
        reproducibility_bundle_out=reproducibility_bundle,
    )
    payload = json.loads(summary.read_text(encoding="utf-8"))
    payload["contract_pass"] = not payload["contract_pass"]
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_benchmark_factory_artifacts(
        repo_root=REPO_ROOT,
        manifest_out=manifest,
        acquisition_plan_out=acquisition_plan,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition,
        ifc_source_license_out=ifc_source_license,
        ifc_import_health_execution_out=ifc_import_health_execution,
        opensees_source_license_out=opensees_source_license,
        commercial_comparison_template_out=commercial_comparison_template,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator,
        scorecard_out=scorecard,
        summary_out=summary,
    )

    assert ok is False
    assert message == "phase3_benchmark_factory_mismatch:summary"


def test_phase3_benchmark_factory_check_detects_reproducibility_bundle_drift(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    acquisition_plan = tmp_path / "acquisition_plan.json"
    buildingsmart_ifc_acquisition = tmp_path / "buildingsmart_ifc_acquisition.json"
    buildingsmart_dirty_ifc_acquisition = tmp_path / "buildingsmart_dirty_ifc_acquisition.json"
    ifc_source_license = tmp_path / "ifc_source_license.json"
    ifc_import_health_execution = tmp_path / "ifc_import_health_execution.json"
    opensees_source_license = tmp_path / "opensees_source_license.json"
    commercial_comparison_template = tmp_path / "commercial_comparison_template.json"
    phase4_analytic_physical_fallback = tmp_path / "phase4_analytic_physical_fallback.json"
    commercial_operator_reference_contract = tmp_path / "commercial_operator_reference_contract.json"
    commercial_operator_reference_ingest_validator = (
        tmp_path / "commercial_operator_reference_ingest_validator.json"
    )
    scorecard = tmp_path / "scorecard.json"
    summary = tmp_path / "summary.json"
    reproducibility_bundle = tmp_path / "reproducibility_bundle.json"
    module.write_phase3_benchmark_factory_artifacts(
        repo_root=REPO_ROOT,
        manifest_out=manifest,
        acquisition_plan_out=acquisition_plan,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition,
        ifc_source_license_out=ifc_source_license,
        ifc_import_health_execution_out=ifc_import_health_execution,
        opensees_source_license_out=opensees_source_license,
        commercial_comparison_template_out=commercial_comparison_template,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator,
        scorecard_out=scorecard,
        summary_out=summary,
        reproducibility_bundle_out=reproducibility_bundle,
    )
    payload = json.loads(reproducibility_bundle.read_text(encoding="utf-8"))
    payload["clean_checkout_executed"] = True
    reproducibility_bundle.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_phase3_benchmark_factory_artifacts(
        repo_root=REPO_ROOT,
        manifest_out=manifest,
        acquisition_plan_out=acquisition_plan,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition,
        ifc_source_license_out=ifc_source_license,
        ifc_import_health_execution_out=ifc_import_health_execution,
        opensees_source_license_out=opensees_source_license,
        commercial_comparison_template_out=commercial_comparison_template,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator,
        scorecard_out=scorecard,
        summary_out=summary,
        reproducibility_bundle_out=reproducibility_bundle,
    )

    assert ok is False
    assert message == "phase3_benchmark_factory_mismatch:reproducibility_bundle"
