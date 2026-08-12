from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_sparse_linear.py"
SPEC = importlib.util.spec_from_file_location("check_native_sparse_linear", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sparse = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sparse
SPEC.loader.exec_module(sparse)


def test_repository_sparse_linear_c1_contract_passes() -> None:
    report = sparse.check_native_sparse_linear(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C1"
    assert "general sparse solvers" in report["claim_boundary"]
    assert "HIP C2" in report["claim_boundary"]
    assert "C6" in report["claim_boundary"]


def test_sparse_linear_contract_fails_closed_on_source_or_gate_drift(
    tmp_path: Path,
) -> None:
    relatives = {*sparse.REQUIRED_TOKENS, "native/capabilities.json"}
    for relative in relatives:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    source = tmp_path / "native/cpp/src/solver_cpu/sparse_linear.cpp"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "SolverStatus::singularity", "SolverStatus::removed"
        ),
        encoding="utf-8",
    )

    report = sparse.check_native_sparse_linear(tmp_path)

    assert report["contract_pass"] is False
    assert any("SolverStatus::singularity" in item for item in report["blockers"])
