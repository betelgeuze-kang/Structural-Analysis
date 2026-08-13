from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_model_ir_linear_workbench.py"
SPEC = importlib.util.spec_from_file_location(
    "check_native_model_ir_linear_workbench", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_repository_contract_closes_only_bounded_linear_workbench_c5() -> None:
    report = checker.check_model_ir_linear_workbench(ROOT)
    assert report["contract_pass"] is True, report["blockers"]
    assert report["cutover_gate"] == "C5"
    assert report["sequential_numerical_gates"] == {
        "dense_assembly_cpu": "C1",
        "sparse_linear_solver_cpu": "C1",
    }
    assert "cannot promote numerical C2" in report["claim_boundary"]
    assert "authoritative C3" in report["claim_boundary"]
    assert "PDF authority" in report["claim_boundary"]
    assert "C6" in report["claim_boundary"]


def test_checker_fails_closed_on_missing_evidence_and_gate_drift(
    tmp_path: Path,
) -> None:
    for relative in checker.REQUIRED_TOKENS:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    manifest_source = ROOT / "native/capabilities.json"
    manifest_destination = tmp_path / "native/capabilities.json"
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(manifest_source.read_text(encoding="utf-8"))
    payload["capabilities"]["modelir_linear_workbench"]["cutover_gate"] = "C6"
    manifest_destination.write_text(json.dumps(payload), encoding="utf-8")
    (
        tmp_path
        / "native/crates/structural-workbench/tests/model_ir_linear_workbench_e2e.rs"
    ).unlink()

    report = checker.check_model_ir_linear_workbench(tmp_path)
    assert report["contract_pass"] is False
    assert any("gate_not_c5" in blocker for blocker in report["blockers"])
    assert any("evidence_missing" in blocker for blocker in report["blockers"])
