from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_g1_stateful_steel_hip_lifecycle as gate


def test_committed_material_receipt_is_current() -> None:
    passed, reason = gate.check(root=ROOT)
    assert passed, reason


def test_claim_boundary_preserves_mgt_resultir_and_gfx1100_blockers() -> None:
    payload = json.loads((ROOT / gate.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["claims"]["material_trial_commit_rollback_on_device"] is True
    assert payload["claims"]["actual_mgt_worker_connected"] is False
    assert payload["claims"]["resultir_emitted"] is False
    assert payload["claims"]["independent_gfx1100_run"] is False
    assert payload["claims"]["g1_closure"] is False
