from __future__ import annotations

import sys
from pathlib import Path

import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
sys.path.insert(0, str(PHASE1))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_default_commands_use_structural_hook() -> None:
    legacy_hook_name = "rust_hip_" + "md3" + "bead_hook.py"
    for script_name in [
        "zero_copy_real_probe.py",
        "profile_p0_engine_path.py",
        "profile_branch64_microbatch_cache.py",
        "run_scaleout_io_profile.py",
        "run_p0_core_gap_pipeline.py",
        "run_megastructure_commercial_readiness.py",
        "run_nightly_release_gate.py",
    ]:
        source = (PHASE1 / script_name).read_text(encoding="utf-8")
        assert "structural_runtime_hook.py" in source
        assert legacy_hook_name not in source


def test_scaleout_command_policy_accepts_structural_runtime_hook() -> None:
    module = _load_module(
        "run_scaleout_io_profile",
        PHASE1 / "run_scaleout_io_profile.py",
    )

    assert module._cmd_looks_rust_hip("python3 implementation/phase1/structural_runtime_hook.py")
    assert module._cmd_looks_rust_hip("implementation/phase1/structural_runtime_ffi/target/release/lib.so")
