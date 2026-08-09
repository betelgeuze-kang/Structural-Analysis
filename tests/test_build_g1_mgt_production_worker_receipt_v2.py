from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import structural_analysis.engine_v2_backends.hip_residual_jvp_worker as public_worker  # noqa: E402


SCRIPT = ROOT / "scripts/build_g1_mgt_production_worker_receipt_v2.py"
SPEC = importlib.util.spec_from_file_location("g1_worker_receipt_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _result(name: str) -> dict:
    return module._read(ROOT / name)


def test_current_worker_receipt_uses_authority_digest_not_full_hash_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_local_probe() -> bool:
        raise AssertionError("offline replay must not probe local device nodes")

    monkeypatch.setattr(
        public_worker, "_local_hip_device_nodes_valid", forbidden_local_probe
    )
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    module.validate(payload, root=ROOT)
    parity = payload["terminal_parity"]
    assert parity["hip_result_hash"] != parity["cpu_result_hash"]
    assert parity["full_result_hashes_equal"] is False
    assert payload["claims"]["terminal_resultir_authority_parity"] is True
    assert payload["claims"]["terminal_resultir_full_hash_equality_required"] is False
    assert payload["capture_boundary"] == {
        "mode": "offline_bound_artifact_replay",
        "local_device_probe_performed": False,
        "local_device_probe_required_for_offline_replay": False,
        "signed_hardware_envelope_verified": False,
        "hardware_identity_trusted": False,
    }
    assert payload["claims"]["production_worker_ready"] is False
    assert payload["lifecycle"]["accepted_state_tangent_refresh_on_device"] is False
    assert payload["claims"]["accepted_state_tangent_refresh_on_device_proven"] is False
    assert (
        "accepted_state_tangent_refresh_hip_not_proven" in payload["blockers_remaining"]
    )


def test_backend_specific_hash_drift_does_not_change_authority_digest() -> None:
    hip = _result(module.result_gate.DEFAULT_HIP_RESULT.as_posix())
    cpu = _result(module.result_gate.DEFAULT_CPU_RESULT.as_posix())
    original = module.terminal_parity_digest(hip, cpu)
    cpu["result_hash"] = "sha256:" + "f" * 64
    cpu["backend"]["backend_receipt_hash"] = "sha256:" + "e" * 64
    assert module.terminal_parity_digest(hip, cpu) == original


def test_state_or_displacement_drift_fails_terminal_parity() -> None:
    hip = _result(module.result_gate.DEFAULT_HIP_RESULT.as_posix())
    cpu = _result(module.result_gate.DEFAULT_CPU_RESULT.as_posix())
    for path in ("state", "displacement"):
        candidate = deepcopy(cpu)
        if path == "state":
            candidate["bindings"]["state_hash"] = "sha256:" + "d" * 64
        else:
            candidate["displacement_artifact"]["data_hash"] = "sha256:" + "c" * 64
        with pytest.raises(ValueError, match="terminal_authority_parity_failed"):
            module.terminal_parity_digest(hip, candidate)


def test_schema_forbids_offline_replay_from_claiming_trusted_hardware() -> None:
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    schema = json.loads((ROOT / module.SCHEMA).read_text(encoding="utf-8"))
    promoted = deepcopy(payload)
    promoted["capture_boundary"]["hardware_identity_trusted"] = True
    promoted["claims"]["trusted_hardware_execution"] = True
    promoted["claims"]["production_worker_ready"] = True
    assert list(module.Draft202012Validator(schema).iter_errors(promoted))
