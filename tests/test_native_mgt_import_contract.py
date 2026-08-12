from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_mgt_import.py"
SPEC = importlib.util.spec_from_file_location("check_native_mgt_import", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mgt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mgt
SPEC.loader.exec_module(mgt)


def _copy_contract(tmp_path: Path) -> None:
    relatives = {
        "native/capabilities.json",
        "native/tests/golden/mgt_import_health_v1.json",
        *mgt.REQUIRED_TOKENS,
    }
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_mgt_import_contract_is_evidence_backed() -> None:
    report = mgt.check_native_mgt_import(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["blockers"] == []


def test_contract_fails_closed_when_loss_disposition_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-contracts/src/mgt_import.rs"
    text = path.read_text(encoding="utf-8").replace(
        "mgt_element_family_dropped", "mgt_element_family_omitted"
    )
    path.write_text(text, encoding="utf-8")

    report = mgt.check_native_mgt_import(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "mgt_import_evidence_token_missing:"
        "native/crates/structural-contracts/src/mgt_import.rs:"
        "mgt_element_family_dropped" in report["blockers"]
    )
