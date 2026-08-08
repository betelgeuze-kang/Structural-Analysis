from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_g1_mgt_nonlinear_result_ir as gate


def test_committed_result_ir_receipt_is_current() -> None:
    passed, reason = gate.check(root=ROOT)
    assert passed, reason


def test_result_ir_parity_does_not_promote_open_g1_boundaries() -> None:
    payload = json.loads((ROOT / gate.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["claims"]["authoritative_nonlinear_resultir_emitted"] is True
    assert payload["claims"]["terminal_resultir_parity"] is True
    assert payload["claims"]["diagnosticir_emitted"] is True
    assert payload["diagnostic"]["status"] == "partial"
    assert payload["diagnostic"]["entry_count"] == 5
    assert payload["diagnostic"]["unsupported_count"] == 2
    assert payload["claims"]["independent_gfx1100_run"] is False
    assert payload["claims"]["g1_closure"] is False
    assert payload["terminal"]["material_entry_count"] == 5_572
