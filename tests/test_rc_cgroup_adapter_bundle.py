"""Standalone loading uses the same anonymous module mechanism as the E2 bridge."""

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_boundary_adapter_test", ROOT / "scripts/build_rc_cgroup_boundary_adapter.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def loaded(root):
    module = ModuleType("owned_admitted_B_descendant_adapter")
    source = builder.build_adapter_source(root)
    exec(compile(source, "<exact adapter bytes>", "exec"), module.__dict__)
    return module, source


def test_real_source_loads_anonymously_and_rejects_bad_plan_without_allocation():
    module, source = loaded(ROOT)
    assert source == builder.build_adapter_source(ROOT)
    before = set(sys.modules)
    with pytest.raises(ValueError, match="invalid guardian boundary plan"):
        module.prepare_boundary({})
    assert not {
        name
        for name in set(sys.modules) - before
        if name.startswith("_owned_rc_boundary_")
    }
    for name, value in module.SOURCE_BYTES.items():
        assert hashlib.sha256(value).hexdigest() == module.SOURCE_SHA256[name]


def test_successful_binding_retains_embedded_code_after_module_cleanup(tmp_path):
    directory = tmp_path / "src/structural_analysis/execution"
    directory.mkdir(parents=True)
    for name in builder.MODULES:
        (directory / f"{name}.py").write_text("VALUE = 42\n")
    (directory / "rc_cgroup_guardian.py").write_text(
        "from .rc_resource_boundary import VALUE\n"
        "class Binding:\n    def read(self): return VALUE\n"
        "def prepare_boundary(plan): return Binding()\n"
    )
    module, _ = loaded(tmp_path)
    before = set(sys.modules)
    binding = module.prepare_boundary({})
    (directory / "rc_resource_boundary.py").write_text(
        "raise RuntimeError('mutable checkout')\n"
    )
    assert binding.read() == 42
    assert not {
        name
        for name in set(sys.modules) - before
        if name.startswith("_owned_rc_boundary_")
    }


def test_changed_embedded_source_rejected_before_execution():
    module, _ = loaded(ROOT)
    module.SOURCE_BYTES[builder.MODULES[0]] += b"\n# changed\n"
    with pytest.raises(ValueError, match="digest mismatch"):
        module.prepare_boundary({})
