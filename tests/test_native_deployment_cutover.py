from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_native_deployment_cutover.py"
SPEC = importlib.util.spec_from_file_location("check_native_deployment_cutover", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _copy_required_tree(destination: Path) -> None:
    for relative in checker.REQUIRED_FILES:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_native_deployment_cutover_is_fail_closed_and_c5_bounded() -> None:
    report = checker.check_native_deployment_cutover(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["cutover_gate"] == "C5"
    assert report["active_entrypoint"] == "deployment/onprem/Containerfile"
    assert report["active_pages_deployment_authority"] is False
    assert report["active_runtime_interpreters"] == []
    assert report["local_rootfs_isolation_harness"] is True
    assert report["local_rootfs_receipt_authority"] == "local_rootfs_diagnostic_c5"
    assert report["customer_image_receipt"] is False
    assert report["c6_complete"] is False
    assert "global Python/Node removal" in report["claim_boundary"]


def test_native_deployment_cutover_rejects_reactivated_legacy_entrypoints(
    tmp_path: Path,
) -> None:
    _copy_required_tree(tmp_path)
    active_workflow = tmp_path / ".github/workflows/deploy-pages.yml"
    active_workflow.parent.mkdir(parents=True, exist_ok=True)
    active_workflow.write_text(
        "permissions:\n  pages: write\njobs:\n  deploy:\n"
        "    steps:\n      - uses: actions/deploy-pages@v4\n",
        encoding="utf-8",
    )
    container = tmp_path / checker.ACTIVE_CONTAINER
    container.write_text(
        container.read_text(encoding="utf-8")
        + '\nFROM python:3.10-slim\nCMD ["python", "project_ops_api_service.py"]\n',
        encoding="utf-8",
    )

    report = checker.check_native_deployment_cutover(tmp_path)

    assert report["contract_pass"] is False
    assert report["active_pages_deployment_authority"] is True
    assert "legacy_pages_workflow_still_active" in report["blockers"]
    assert any(
        blocker.startswith("active_container_forbidden_runtime_token:from python")
        for blocker in report["blockers"]
    )
