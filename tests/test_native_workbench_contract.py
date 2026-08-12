from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_native_workbench.py"
SPEC = importlib.util.spec_from_file_location("check_native_workbench", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_native_workbench_contract_has_bounded_c5_evidence() -> None:
    report = checker.check_native_workbench(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["cutover_gate"] == "C5"
    assert "general GUI replacement" in report["claim_boundary"]
    assert "C6" in report["claim_boundary"]


def test_native_workbench_checker_fails_closed_on_evidence_drift(tmp_path: Path) -> None:
    for relative in checker.REQUIRED_TOKENS:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    manifest_source = ROOT / "native/capabilities.json"
    manifest_destination = tmp_path / "native/capabilities.json"
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(manifest_source.read_text(encoding="utf-8"))
    manifest_destination.write_text(json.dumps(payload), encoding="utf-8")

    test_path = (
        tmp_path
        / "native/crates/structural-workbench/tests/native_workbench_e2e.rs"
    )
    text = test_path.read_text(encoding="utf-8").replace(
        "command.env_clear()", "removed_environment_boundary"
    )
    test_path.write_text(text, encoding="utf-8")
    report = checker.check_native_workbench(tmp_path)

    assert report["contract_pass"] is False
    assert any("command.env_clear()" in blocker for blocker in report["blockers"])
