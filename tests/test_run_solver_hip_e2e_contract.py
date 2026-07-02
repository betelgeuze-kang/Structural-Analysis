from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE1_DIR = REPO_ROOT / "implementation" / "phase1"
SCRIPT_PATH = PHASE1_DIR / "run_solver_hip_e2e_contract.py"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

SPEC = importlib.util.spec_from_file_location(
    "run_solver_hip_e2e_contract", SCRIPT_PATH
)
assert SPEC is not None
solver_hip = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = solver_hip
SPEC.loader.exec_module(solver_hip)


def test_rocm_runtime_environment_status_blocks_missing_device_interface() -> None:
    payload = solver_hip._rocm_runtime_environment_status(
        rocminfo_path="/usr/bin/rocminfo",
        rocm_smi_path="/usr/local/bin/rocm-smi",
        dev_kfd_present=False,
        dev_dri_present=True,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["runtime_device_interface_present"] is False
    assert payload["blockers"] == ["dev_kfd_missing"]


def test_rocm_runtime_environment_status_requires_rocminfo() -> None:
    payload = solver_hip._rocm_runtime_environment_status(
        rocminfo_path="",
        rocm_smi_path="",
        dev_kfd_present=True,
        dev_dri_present=True,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["runtime_device_interface_present"] is True
    assert payload["blockers"] == ["rocminfo_not_found"]


def test_rocm_runtime_environment_status_passes_when_runtime_visible() -> None:
    payload = solver_hip._rocm_runtime_environment_status(
        rocminfo_path="/usr/bin/rocminfo",
        rocm_smi_path="",
        dev_kfd_present=True,
        dev_dri_present=True,
    )

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
