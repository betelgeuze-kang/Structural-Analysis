from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase4_commercial_cross_solver_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase4_commercial_cross_solver_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_commercial_cross_solver_readiness_blocks_without_operator_package() -> None:
    payload = module.build_phase4_commercial_cross_solver_readiness_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase4-commercial-cross-solver-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["commercial_outputs_are_absolute_truth"] is False
    assert payload["required_reference_solver_count"] == 2
    assert payload["current_reference_solver_count"] == 0
    assert payload["operator_package_attached"] is False
    assert payload["operator_permission_attached"] is False
    assert payload["operator_checksum_count"] == 0
    assert payload["operator_trace_rows_available"] is False
    assert payload["required_evidence_pass_count"] == 1
    assert payload["required_evidence_count"] == len(payload["required_evidence"])
    assert "operator_reference_package_missing" in payload["blockers"]
    assert "license_or_customer_permission_missing" in payload["blockers"]
    assert "operator_file_checksums_missing" in payload["blockers"]
    assert "two_reference_solver_comparison_not_available" in payload["blockers"]
    assert "modeling_assumption_diagnosis_execution_missing" in payload["blockers"]
    assert "operator_comparison_trace_rows_missing" in payload["blockers"]
    assert "commercial_cross_solver_execution_missing" in payload["blockers"]
    assert payload["readiness_inputs"]["import_template"].endswith(
        "phase4_commercial_comparison_import_template.json"
    )
    assert "does not include operator files" in payload["claim_boundary"]


def test_commercial_cross_solver_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase4_commercial_cross_solver_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase4_commercial_cross_solver_readiness_missing:")


def test_commercial_cross_solver_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "commercial-cross-solver.json"
    module.write_phase4_commercial_cross_solver_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase4_commercial_cross_solver_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_commercial_cross_solver_readiness_mismatch"
