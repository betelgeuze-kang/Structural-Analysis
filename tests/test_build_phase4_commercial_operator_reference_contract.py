from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase4_commercial_operator_reference_contract.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase4_commercial_operator_reference_contract", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_commercial_operator_reference_contract_stays_blocked_without_operator_outputs() -> None:
    payload = module.build_phase4_commercial_operator_reference_contract(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase4-commercial-operator-reference-contract.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["truth_class"] == "comparison_reference"
    assert payload["selected_benchmark_lanes"] == ["commercial-cross-solver"]
    assert payload["required_reference_solver_count"] == 2
    assert payload["current_reference_solver_count"] == 0
    assert payload["import_template"].endswith("phase4_commercial_comparison_import_template.json")
    diagnostic_order = [
        "unit_system",
        "local_axis_convention",
        "rigid_offset_policy",
        "end_release_policy",
        "diaphragm_policy",
        "mass_source_policy",
        "self_weight_policy",
        "material_modulus_convention",
        "shell_formulation",
        "mesh_density",
        "damping_policy",
        "p_delta_policy",
        "eigen_solver",
        "load_combinations",
        "convergence_tolerance",
    ]
    diagnostic_policy = payload["comparison_diagnostic_policy"]
    assert diagnostic_policy["policy_id"] == "modeling_assumption_first"
    assert diagnostic_policy["commercial_outputs_are_absolute_truth"] is False
    assert diagnostic_policy["solver_correctness_claim_allowed"] is False
    assert diagnostic_policy["diagnostic_order"] == diagnostic_order
    gui_traceability = payload["gui_traceability_contract"]
    assert gui_traceability["status"] == "ready"
    assert gui_traceability["contract_pass"] is True
    assert gui_traceability["required_trace_dimensions"] == ["member", "story", "mode"]
    assert gui_traceability["missing_trace_dimensions_are_blocking"] is True
    assert gui_traceability["operator_trace_rows_available"] is False

    required_fields = payload["required_package_fields"]
    for field in [
        "modeling_assumption_diagnostic_order",
        "permission_scope",
        "reference_solvers",
        "raw_input_files",
        "raw_result_files",
        "file_checksums",
        "unit_system",
        "local_axis_convention",
        "p_delta_policy",
        "convergence_tolerance",
        "unsupported_features",
    ]:
        assert field in required_fields

    rule_ids = {row["rule_id"] for row in payload["validation_rules"]}
    assert "two_independent_reference_solvers_required" in rule_ids
    assert "operator_permission_must_be_attached" in rule_ids
    assert "all_raw_files_need_sha256" in rule_ids
    assert "modeling_assumption_first_diagnosis_required" in rule_ids
    assert "commercial_outputs_are_not_absolute_truth" in rule_ids
    assert payload["operator_reference_package_template"]["modeling_assumption_diagnostic_order"] == diagnostic_order
    assert "operator_reference_package_missing" in payload["remaining_blockers"]
    assert "two_reference_solver_comparison_not_available" in payload["remaining_blockers"]
    assert "operator_comparison_trace_rows_missing" in payload["remaining_blockers"]
    assert "does not include operator files" in payload["claim_boundary"]
    assert "execute modeling-assumption diagnostics" in payload["claim_boundary"]
    assert "execute GUI story/member/mode trace rows" in payload["claim_boundary"]
    assert "close Phase 3, Phase 4, Phase 6" in payload["claim_boundary"]


def test_commercial_operator_reference_contract_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase4_commercial_operator_reference_contract(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase4_commercial_operator_reference_contract_missing:")


def test_commercial_operator_reference_contract_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "contract.json"
    module.write_phase4_commercial_operator_reference_contract(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase4_commercial_operator_reference_contract(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_commercial_operator_reference_contract_mismatch"
