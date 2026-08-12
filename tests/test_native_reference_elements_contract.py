from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_reference_elements.py"
SPEC = importlib.util.spec_from_file_location("check_native_reference_elements", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
reference = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reference
SPEC.loader.exec_module(reference)


def _copy_contract(tmp_path: Path) -> None:
    relatives = {"native/capabilities.json", *reference.REQUIRED_TOKENS}
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_reference_element_contract_is_evidence_backed() -> None:
    report = reference.check_native_reference_elements(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C1"
    assert "does not close HIP C2" in report["claim_boundary"]
    assert report["blockers"] == []


def test_contract_fails_closed_when_failure_atomicity_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/cpp/tests/abi/reference_elements_contract_test.cpp"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "failures_do_not_publish_partial_outputs",
            "failures_may_publish_partial_outputs",
        ),
        encoding="utf-8",
    )

    report = reference.check_native_reference_elements(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "reference_evidence_token_missing:"
        "native/cpp/tests/abi/reference_elements_contract_test.cpp:"
        "failures_do_not_publish_partial_outputs" in report["blockers"]
    )
