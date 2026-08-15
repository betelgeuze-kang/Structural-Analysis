from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_model_ir_linear_product.py"
SPEC = importlib.util.spec_from_file_location("check_native_model_ir_linear_product", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_repository_contract_passes_without_promoting_numerical_c2() -> None:
    report = checker.check_model_ir_linear_product(ROOT)
    assert report["contract_pass"] is True
    assert report["checkpoint_gate"] == "C4"
    assert report["product_gate"] == "C5"
    assert report["reaction_result_gate"] == "C5"
    assert report["sequential_numerical_gate"] == "C1"
    assert report["blockers"] == []
    assert "cannot promote C2" in report["claim_boundary"]


def test_checker_fails_closed_on_missing_evidence_and_gate_drift(tmp_path: Path) -> None:
    for relative in checker.REQUIRED_TOKENS:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    manifest_source = ROOT / "native/capabilities.json"
    manifest_destination = tmp_path / "native/capabilities.json"
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(manifest_source.read_text(encoding="utf-8"))
    payload["capabilities"]["modelir_linear_product_e2e"]["cutover_gate"] = "C6"
    manifest_destination.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "native/crates/structural-runtime/src/model_linear_checkpoint.rs").unlink()

    report = checker.check_model_ir_linear_product(tmp_path)
    assert report["contract_pass"] is False
    assert any("gate_not_c5" in blocker for blocker in report["blockers"])
    assert any("evidence_missing" in blocker for blocker in report["blockers"])
