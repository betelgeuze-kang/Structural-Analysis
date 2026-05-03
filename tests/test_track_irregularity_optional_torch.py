from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "implementation" / "phase1" / "track_irregularity_generator.py"


def _load_module():
    phase1 = SCRIPT_PATH.parent.resolve()
    if str(phase1) not in sys.path:
        sys.path.insert(0, str(phase1))
    spec = importlib.util.spec_from_file_location("track_irregularity_generator_test", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _block_torch_import(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "torch" or str(name).startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.delitem(sys.modules, "torch", raising=False)


def test_track_irregularity_uses_numpy_when_torch_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    _block_torch_import(monkeypatch)
    monkeypatch.delenv("PHASE1_GPU_PREPROCESS", raising=False)
    monkeypatch.delenv("PHASE1_GPU_PREPROCESS_STRICT", raising=False)

    _x, _z, metrics = module.generate_profile(
        module.IrregularityConfig(length_m=8.0, dx_m=0.25, quality_class="B", seed=7)
    )

    assert metrics["preprocess_backend"] == "numpy_cpu"
    assert metrics["node_count"] == 33


def test_force_cpu_runtime_overrides_strict_gpu_preprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    _block_torch_import(monkeypatch)
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS", "1")
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS_STRICT", "1")
    monkeypatch.setenv("PHASE1_FORCE_CPU_RUNTIME", "1")

    _x, _z, metrics = module.generate_profile(
        module.IrregularityConfig(length_m=8.0, dx_m=0.25, quality_class="B", seed=7)
    )

    assert metrics["preprocess_backend"] == "numpy_cpu"


def test_strict_gpu_preprocess_fails_when_torch_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    _block_torch_import(monkeypatch)
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS", "1")
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS_STRICT", "1")
    monkeypatch.delenv("PHASE1_FORCE_CPU_RUNTIME", raising=False)

    with pytest.raises(RuntimeError, match="GPU preprocess required for track irregularity"):
        module.generate_profile(module.IrregularityConfig(length_m=8.0, dx_m=0.25, quality_class="B", seed=7))
