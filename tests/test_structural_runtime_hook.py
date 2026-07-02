from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation" / "phase1" / "structural_runtime_hook.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("structural_runtime_hook", SCRIPT_PATH)
assert SPEC is not None
structural_runtime_hook = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(structural_runtime_hook)


def test_dispatches_zero_copy_probe_with_challenge_echo() -> None:
    payload = structural_runtime_hook.dispatch(
        {
            "action": "dlpack_bridge_probe",
            "challenge": "challenge-123",
            "probe_length": 128,
            "probe_alpha": 1.25,
            "probe_seed": 7,
        }
    )

    assert payload["producer_kind"] == "rust_hip"
    assert payload["runtime_backend"] == "structural_runtime_ffi"
    assert payload["challenge_echo"] == "challenge-123"
    assert payload["host_copy_bytes"] == 0
    assert payload["cpu_required"] is False
    assert payload["cpu_fallback_used"] is False
    assert payload["roundtrip_success"] is True
    assert payload["shared_storage"] is True


def test_dispatches_structural_step5_profile() -> None:
    payload = structural_runtime_hook.dispatch(
        {
            "action": "step5_profile",
            "n": 100_000,
            "branch_batch": 4,
            "state_components": 5,
            "cache_mb": 128.0,
            "graph_overhead_mb": 24.0,
        }
    )

    assert payload["runtime_backend"] == "structural_runtime_ffi"
    assert payload["seconds"] > 0.0
    assert payload["peak_vram_bytes"] > 0
    assert payload["host_copy_bytes"] == 0
    assert 0.0 < payload["cache_fit_ratio"]
    assert isinstance(payload["cache_fit"], bool)
