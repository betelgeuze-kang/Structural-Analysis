from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def _runner():
    path = ROOT / "scripts/run_g1_mgt_accepted_state_preconditioned_jvp_parity.py"
    spec = importlib.util.spec_from_file_location("accepted_preconditioned_jvp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def test_schema_keeps_transfer_and_fgmres_claims_false() -> None:
    runner = _runner(); schema = json.loads((ROOT / runner.SCHEMA_PATH).read_text(encoding="utf-8")); Draft202012Validator.check_schema(schema)
    claims = schema["properties"]["claims"]["properties"]
    assert claims["mathematical_right_preconditioned_jvp_composition"] == {"const": True}
    assert claims["single_device_lifecycle"] == {"const": False}
    assert claims["mid_composition_d2h_zero"] == {"const": False}
    assert claims["production_fgmres"] == {"const": False}
    assert claims["g1_closure"] == {"const": False}


def test_preconditioner_solution_is_exact_source_artifact() -> None:
    runner = _runner(); payload = json.loads((ROOT / runner.PRECONDITIONER_RECEIPT).read_text(encoding="utf-8"))
    direction = runner._solution_from_preconditioner(payload, root=ROOT)
    assert direction.shape == (runner.EQUATION_COUNT,)
    assert runner.array_data_hash(direction) == payload["comparison"]["solution_data_hash"]


def test_check_fails_closed_when_missing(tmp_path: Path) -> None:
    runner = _runner(); passed, reason = runner.check(root=tmp_path, out_path=Path("missing.json"))
    assert passed is False
    assert reason == "g1_mgt_accepted_state_preconditioned_jvp_receipt_missing"


def test_runner_names_the_process_bridge_blocker() -> None:
    source = Path(_runner().__file__).read_text(encoding="utf-8")
    assert "persisted_d2h_h2d_bridge_between_preconditioner_and_jvp" in source
    assert "arnoldi_recurrence_not_connected_to_actual_mgt_operator_and_factor" in source
