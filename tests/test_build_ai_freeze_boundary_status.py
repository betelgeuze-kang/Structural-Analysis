from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_ai_freeze_boundary_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_ai_freeze_boundary_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_ai_freeze_boundary_status_marks_boundary_ready_without_autonomous_claim() -> None:
    payload = module.build_ai_freeze_boundary_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "ai-freeze-boundary-status.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["boundary_claim_ready"] is True
    assert payload["autonomous_ai_engine_claim"] is False
    assert payload["autonomous_legal_or_design_approval_claim"] is False
    assert payload["surrogate_truth_claim_frozen"] is True
    assert payload["ai_training_frozen"] is True
    assert payload["shadow_solver_gated_only"] is True
    assert payload["production_pareto_policy_claim"] is False
    assert payload["ml_shadow_gate"]["status"] == "production_shadow_solver_gated_ready"
    assert payload["ml_shadow_gate"]["production_ml_wired"] is True
    assert payload["ml_shadow_gate"]["multi_objective_pareto_wired"] is False
    assert payload["ml_shadow_gate"]["hard_gate_bypass_prevented"] is True
    assert payload["guard_gates"]["physics_guard_ready"] is True
    assert payload["guard_gates"]["code_guard_ready"] is True
    assert payload["blockers"] == []
    assert "does not prove autonomous structural-design AI" in payload["claim_boundary"]
    assert "shadow_with_solver_fallback" in payload["claim_boundary"]


def test_ai_freeze_boundary_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_ai_freeze_boundary_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("ai_freeze_boundary_status_missing:")


def test_ai_freeze_boundary_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "ai.json"
    module.write_ai_freeze_boundary_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["autonomous_ai_engine_claim"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_ai_freeze_boundary_status(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "ai_freeze_boundary_status_mismatch"
