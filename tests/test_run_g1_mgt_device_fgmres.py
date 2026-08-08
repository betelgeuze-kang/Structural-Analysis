from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_g1_mgt_device_fgmres as gate


def test_committed_receipt_is_current_and_artifacts_are_bound() -> None:
    passed, reason = gate.check(root=ROOT)
    assert passed, reason


def test_receipt_keeps_remaining_hardware_and_nonlinear_boundaries_visible() -> None:
    payload = json.loads((ROOT / gate.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["claims"]["production_size_fgmres"] is True
    assert payload["claims"]["mid_iteration_d2h_zero"] is True
    assert payload["claims"]["independent_gfx1100_run"] is False
    assert payload["claims"]["newton_update_line_search_material_checkpoint"] is False
    assert payload["claims"]["g1_closure"] is False
