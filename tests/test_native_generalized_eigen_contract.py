from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_generalized_eigen.py"
SPEC = importlib.util.spec_from_file_location("check_native_generalized_eigen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
generalized = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generalized
SPEC.loader.exec_module(generalized)


def _copy_contract(tmp_path: Path) -> None:
    for relative in {"native/capabilities.json", *generalized.REQUIRED_TOKENS}:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def test_repository_generalized_eigen_c1_contract_passes() -> None:
    report = generalized.check_native_generalized_eigen(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C1"
    assert "Sparse extraction" in report["claim_boundary"]
    assert "HIP C2" in report["claim_boundary"]
    assert "C6" in report["claim_boundary"]


def test_generalized_eigen_contract_fails_closed_on_source_drift(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    source = tmp_path / "native/cpp/src/solver_cpu/generalized_eigen.cpp"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "canonicalize_eigenspace", "removed_eigenspace_canonicalization"
        ),
        encoding="utf-8",
    )

    report = generalized.check_native_generalized_eigen(tmp_path)

    assert report["contract_pass"] is False
    assert any("canonicalize_eigenspace" in item for item in report["blockers"])
