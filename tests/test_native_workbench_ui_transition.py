from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_native_workbench_ui_transition.py"
SPEC = importlib.util.spec_from_file_location("check_native_workbench_ui_transition", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _copy_file(relative: Path, destination_root: Path) -> None:
    source = ROOT / relative
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_transition_inventory(destination_root: Path) -> None:
    copied: set[Path] = set()
    for relative in checker.REQUIRED_PATHS:
        _copy_file(relative, destination_root)
        copied.add(relative)
    for directory, suffixes in (
        (Path("src"), {".ts", ".tsx", ".js", ".mjs"}),
        (Path("scripts"), {".js", ".mjs"}),
        (Path("tests/frontend"), {".ts", ".tsx"}),
        (Path("tests"), {".js", ".mjs"}),
        (Path(".github/workflows"), {".yml", ".yaml"}),
    ):
        for source in (ROOT / directory).rglob("*"):
            if not source.is_file() or source.suffix not in suffixes:
                continue
            relative = source.relative_to(ROOT)
            if relative not in copied:
                _copy_file(relative, destination_root)
                copied.add(relative)


def test_workbench_ui_transition_inventory_is_honest_and_not_c6() -> None:
    report = checker.check_native_workbench_ui_transition(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["c6_ready"] is False
    assert report["removal_allowed"] is False
    assert report["source_inventory"] == {
        "src_ts_tsx_files": 43,
        "src_js_mjs_files": 83,
        "frontend_ts_tsx_test_files": 9,
        "node_js_mjs_script_files": 18,
        "js_mjs_test_files": 2,
    }
    assert len(report["active_node_workflows"]) == 7
    assert "active_node_verification_workflows_present" in report["transition_blockers"]
    assert "not C6 readiness" in report["claim_boundary"]


def test_workbench_ui_transition_rejects_premature_removal_claim(tmp_path: Path) -> None:
    _copy_transition_inventory(tmp_path)
    manifest_path = tmp_path / checker.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["legacy_surface"]["removal_allowed"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = checker.check_native_workbench_ui_transition(tmp_path)

    assert report["contract_pass"] is False
    assert "workbench_ui_legacy_field_invalid:removal_allowed" in report["blockers"]
    assert "workbench_ui_c6_claim_not_derived_from_prerequisites" not in report["blockers"]


def test_workbench_ui_transition_detects_new_node_authority(tmp_path: Path) -> None:
    _copy_transition_inventory(tmp_path)
    workflow = tmp_path / ".github/workflows/react-reintroduced.yml"
    workflow.write_text(
        "name: reintroduced\njobs:\n  test:\n    steps:\n      - uses: actions/setup-node@v6\n",
        encoding="utf-8",
    )

    report = checker.check_native_workbench_ui_transition(tmp_path)

    assert report["contract_pass"] is False
    assert "workbench_ui_active_node_workflow_inventory_drift" in report["blockers"]
