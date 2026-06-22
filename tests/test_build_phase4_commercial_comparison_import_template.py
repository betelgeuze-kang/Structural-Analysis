from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase4_commercial_comparison_import_template.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase4_commercial_comparison_import_template", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_commercial_comparison_import_template_authors_mapping_expectations_only() -> None:
    payload = module.build_phase4_commercial_comparison_import_template(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase4-commercial-comparison-import-template.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["truth_class"] == "comparison_reference"
    assert payload["selected_benchmark_lanes"] == ["commercial-cross-solver"]
    assert payload["template_scope"]["operator_files_bundled"] is False
    assert payload["template_scope"]["commercial_results_are_absolute_truth"] is False
    assert payload["template_scope"]["requires_two_reference_solvers_for_phase4_closure"] is True

    required = payload["required_result_fields"]
    for field in [
        "case_id",
        "modeling_convention_id",
        "engine_name",
        "engine_version",
        "input_checksum",
        "node_member_mapping_coverage",
        "displacement_metrics",
        "reaction_metrics",
        "member_force_metrics",
        "modal_metrics",
        "nonlinear_curve_metrics",
        "equilibrium_residual",
        "runtime",
        "peak_memory",
        "warnings",
        "unsupported_features",
    ]:
        assert field in required
    assert "node_mapping_coverage_ratio" in payload["csv_columns"]
    assert "unsupported_feature_codes" in payload["csv_columns"]
    assert payload["json_template"]["input_checksum"].startswith("sha256:")
    assert "operator_files_missing" in payload["remaining_blockers"]
    assert "two_reference_solver_comparison_not_available" in payload["remaining_blockers"]
    assert "does not attach operator files" in payload["claim_boundary"]


def test_commercial_comparison_import_template_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase4_commercial_comparison_import_template(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase4_commercial_comparison_import_template_missing:")


def test_commercial_comparison_import_template_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "template.json"
    module.write_phase4_commercial_comparison_import_template(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = False
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase4_commercial_comparison_import_template(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_commercial_comparison_import_template_mismatch"
