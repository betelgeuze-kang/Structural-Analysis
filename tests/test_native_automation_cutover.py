from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_native_automation_cutover.py"
SPEC = importlib.util.spec_from_file_location("check_native_automation_cutover", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _copy_contract(destination: Path) -> None:
    for relative in checker.REQUIRED_FILES:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_native_automation_cutover_removes_active_remote_mutation_authority() -> None:
    report = checker.check_native_automation_cutover(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["active_contents_write_workflows"] == []
    assert report["active_branch_push_workflows"] == []
    assert report["active_python_release_mutators"] == []
    assert report["technical_receipt_workflows_retained"] is True
    assert report["c6_complete"] is False


def test_native_automation_cutover_rejects_reactivated_writer(tmp_path: Path) -> None:
    _copy_contract(tmp_path)
    workflow = tmp_path / ".github/workflows/release-publish.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "name: Reactivated\npermissions:\n  contents: write\njobs:\n"
        "  publish:\n    steps:\n      - run: git push origin HEAD:main\n",
        encoding="utf-8",
    )

    report = checker.check_native_automation_cutover(tmp_path)

    assert report["contract_pass"] is False
    assert report["active_contents_write_workflows"] == [
        ".github/workflows/release-publish.yml"
    ]
    assert report["active_branch_push_workflows"] == [
        ".github/workflows/release-publish.yml"
    ]
    assert any(
        blocker.startswith("retired_mutation_entrypoint_reactivated:")
        for blocker in report["blockers"]
    )
