from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_checkpoint_restart.py"
SPEC = importlib.util.spec_from_file_location("check_native_checkpoint_restart", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checkpoint = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checkpoint
SPEC.loader.exec_module(checkpoint)


def _copy_contract(tmp_path: Path) -> None:
    for relative in (
        "native/capabilities.json",
        *checkpoint.REQUIRED_TOKENS,
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_checkpoint_restart_contract_is_evidence_backed() -> None:
    report = checkpoint.check_checkpoint_restart_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C4"
    assert report["blockers"] == []


def test_contract_fails_closed_when_atomic_publish_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-runtime/src/checkpoint.rs"
    text = path.read_text(encoding="utf-8").replace("fs::rename", "publish_file")
    path.write_text(text, encoding="utf-8")

    report = checkpoint.check_checkpoint_restart_contract(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "checkpoint_evidence_token_missing:"
        "native/crates/structural-runtime/src/checkpoint.rs:fs::rename"
        in report["blockers"]
    )
