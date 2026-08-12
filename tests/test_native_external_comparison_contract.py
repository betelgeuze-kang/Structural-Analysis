from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_external_comparison.py"
SPEC = importlib.util.spec_from_file_location(
    "check_native_external_comparison", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


def _copy_contract(tmp_path: Path) -> None:
    relatives = (
        "native/capabilities.json",
        comparison.EXTERNAL_FIXTURE,
        comparison.ORACLE_FIXTURE,
        *comparison.REQUIRED_TOKENS,
    )
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_external_comparison_contract_is_evidence_backed() -> None:
    report = comparison.check_external_comparison_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["oracle_quantity_count"] == 3
    assert report["blockers"] == []


def test_contract_fails_closed_when_oracle_source_hash_drifts(tmp_path: Path) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / comparison.ORACLE_FIXTURE
    path.write_bytes(path.read_bytes() + b"\n")

    report = comparison.check_external_comparison_contract(tmp_path)

    assert report["contract_pass"] is False
    assert "external_comparison_oracle_source_hash_mismatch" in report["blockers"]


def test_contract_fails_closed_when_executable_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = (
        tmp_path
        / "native/crates/structural-contracts/tests/external_comparison_wire.rs"
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "live_evidence_requires_verified_executable_bytes",
            "live_evidence_token_removed",
        ),
        encoding="utf-8",
    )

    report = comparison.check_external_comparison_contract(tmp_path)

    assert report["contract_pass"] is False
    assert any(
        blocker.endswith(":live_evidence_requires_verified_executable_bytes")
        for blocker in report["blockers"]
    )
