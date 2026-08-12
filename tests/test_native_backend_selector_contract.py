from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_backend_selector.py"
SPEC = importlib.util.spec_from_file_location("check_native_backend_selector", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)


def _copy_contract(tmp_path: Path) -> None:
    for relative in selector.REQUIRED_TOKENS:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_backend_selector_static_contract_passes() -> None:
    report = selector.check_native_backend_selector(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["binary_validation"] is None
    assert "approved HIP C2" in report["claim_boundary"]


def test_adapter_symbol_by_symbol_lookup_drift_fails_closed(tmp_path: Path) -> None:
    _copy_contract(tmp_path)
    adapter = tmp_path / "implementation/phase1/mgt_hip_full_residual_ffi/src/lib.rs"
    text = adapter.read_text(encoding="utf-8")
    adapter.write_text(
        text
        + '\nfn forbidden_probe() { let _ = unsafe { dlsym(core::ptr::null_mut(), c"mgt_hip_full_residual_eval".as_ptr()) }; }\n',
        encoding="utf-8",
    )

    report = selector.check_native_backend_selector(tmp_path)

    assert report["contract_pass"] is False
    assert "backend_selector_adapter_dlsym_call_count_invalid" in report["blockers"]
