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


SCRIPT = ROOT / "scripts/build_g1_mgt_terminal_checkpoint_bundle_v2.py"
SPEC = importlib.util.spec_from_file_location("g1_checkpoint_bundle_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_current_terminal_checkpoint_bundle_replays_without_device_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_local_probe() -> bool:
        raise AssertionError("offline replay must not probe local device nodes")

    monkeypatch.setattr(
        public_worker, "_local_hip_device_nodes_valid", forbidden_local_probe
    )
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    module.validate(payload, root=ROOT)
    assert payload["contract_pass"] is True
    assert payload["claims"]["accepted_newton_terminal_restart_bound"] is True
    assert payload["claims"]["material_state_restart_bound"] is True
    assert payload["claims"]["offline_replay_without_local_device_probe"] is True
    assert payload["claims"]["mid_krylov_restart"] is False
    assert payload["claims"]["g1_closure"] is False
    assert payload["material"]["entry_count"] == 5_572


def test_checkpoint_bundle_hash_and_schema_fail_closed() -> None:
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    tampered = deepcopy(payload)
    tampered["solver_bindings"]["path_history_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate(tampered, root=ROOT)

    schema = json.loads((ROOT / module.SCHEMA).read_text(encoding="utf-8"))
    promoted = deepcopy(payload)
    promoted["claims"]["mid_krylov_restart"] = True
    assert list(module.Draft202012Validator(schema).iter_errors(promoted))


def test_result_binding_or_diagnostic_drift_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = module._read

    def drifted(path: Path):
        payload = original(path)
        if path.name == module.result_gate.DEFAULT_CPU_RESULT.name:
            payload["bindings"]["state_hash"] = "sha256:" + "e" * 64
        return payload

    monkeypatch.setattr(module, "_read", drifted)
    with pytest.raises(ValueError):
        module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
