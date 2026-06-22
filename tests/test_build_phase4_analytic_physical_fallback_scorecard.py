from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase4_analytic_physical_fallback_scorecard.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase4_analytic_physical_fallback_scorecard",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase4_analytic_physical_fallback_scorecard_is_ready_but_not_phase4_closure() -> None:
    payload = module.build_phase4_analytic_physical_fallback_scorecard(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase4-analytic-physical-fallback-scorecard.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["truth_class"] == "analytic_physical_fallback"
    assert payload["commercial_reference_case_count"] == 0
    assert payload["operator_reference_package_attached"] is False
    assert payload["two_reference_solver_comparison_available"] is False
    assert payload["case_count"] == 30
    assert payload["pass_count"] == 30
    assert payload["analytic_expected_output_pass_count"] == 30
    assert payload["physical_equilibrium_pass_count"] == 30
    assert payload["expected_output_comparison_count"] == 88
    assert payload["expected_output_comparison_pass_count"] == 88
    assert payload["fallback_scope"]["supports_cases_without_commercial_outputs"] is True
    assert payload["fallback_scope"]["supports_commercial_cross_solver_closure"] is False
    assert payload["fallback_scope"]["supports_two_reference_solver_comparison"] is False
    assert payload["fallback_scope"]["supports_gui_story_member_mode_traceability"] is False
    assert payload["fallback_scope"]["gui_traceability_contract_available"] is True
    assert (
        payload["fallback_scope"]["gui_traceability_contract_scope"]
        == "commercial_crosswalk_schema_and_report_export_only"
    )
    assert "commercial_cross_solver_execution_missing" in payload["remaining_blockers"]
    assert "two_reference_solver_comparison_not_available" in payload["remaining_blockers"]
    assert "operator_comparison_trace_rows_missing" in payload["remaining_blockers"]
    assert "does not attach commercial outputs" in payload["claim_boundary"]
    assert "execute GUI story/member/mode trace rows" in payload["claim_boundary"]
    assert "close Phase 4" in payload["claim_boundary"]
    assert all(row["contract_pass"] is True for row in payload["rows"])
    assert all(row["commercial_reference_available"] is False for row in payload["rows"])
    assert all(
        row["analytic_expected_output_contract_pass"] is True for row in payload["rows"]
    )
    assert all(row["physical_equilibrium_contract_pass"] is True for row in payload["rows"])
    assert all(row["residual_formula"] == "F_internal_minus_F_external" for row in payload["rows"])
    assert all(row["regularization_used"] is False for row in payload["rows"])
    assert all(row["fallback_used"] is False for row in payload["rows"])
    assert all(row["convergence_history_count"] > 0 for row in payload["rows"])


def test_phase4_analytic_physical_fallback_scorecard_check_detects_missing_output(
    tmp_path: Path,
) -> None:
    ok, message = module.check_phase4_analytic_physical_fallback_scorecard(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase4_analytic_physical_fallback_scorecard_missing:")


def test_phase4_analytic_physical_fallback_scorecard_check_detects_drift(
    tmp_path: Path,
) -> None:
    out = tmp_path / "fallback.json"
    module.write_phase4_analytic_physical_fallback_scorecard(
        repo_root=REPO_ROOT,
        out_path=out,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["phase4_closure_claim"] = True
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_phase4_analytic_physical_fallback_scorecard(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_analytic_physical_fallback_scorecard_mismatch"
