from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_phase5_task_based_ux_browser_smoke.py"
SPEC = importlib.util.spec_from_file_location(
    "run_phase5_task_based_ux_browser_smoke",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def _native_receipt(*, skip_build: bool = False) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": "structural-native-phase5-task-browser-smoke-receipt.v1",
        "action": "phase5_task_browser_smoke",
        "execution_mode": "execute",
        "status": "passed",
        "source_map_sha256": "sha256:" + "1" * 64,
        "frontend_contract_receipt_hash": "sha256:" + "2" * 64,
        "build_skipped": skip_build,
        "build_disposition": (
            "skipped_existing_delivery" if skip_build else "executed"
        ),
        "frontend_build_receipt_hash": (
            None if skip_build else "sha256:" + "3" * 64
        ),
        "delivery_receipt_hash": "sha256:" + "4" * 64,
        "specification": {
            "path": "tests/frontend/developer-preview-workflow.spec.ts",
            "byte_length": 1,
            "sha256": "sha256:" + "5" * 64,
        },
        "playwright_cli_sha256": "sha256:" + "6" * 64,
        "playwright_command": [
            "node",
            "node_modules/@playwright/test/cli.js",
            "test",
            "tests/frontend/developer-preview-workflow.spec.ts",
            "--reporter=line",
        ],
        "dist_directory": "dist",
        "spa_fallback_entry": "index.html",
        "base_url_environment": "DEVELOPER_PREVIEW_BASE_URL",
        "required_workflow_steps": [
            "import",
            "model_health",
            "analysis_setup",
            "run_monitor",
            "compare_report",
        ],
        "runtime_requirements": {
            "node_required": True,
            "browser_required": True,
        },
        "loopback_listener_count": 1,
        "loopback_port": 4173,
        "direct_processes_spawned": 1 if skip_build else 3,
        "successful_exit_codes": [0] if skip_build else [0, 0, 0],
        "request_error_count": 0,
        "external_network_access_accounting": (
            "not_instrumented_frontend_build_and_browser_page_requests"
        ),
        "deterministic_receipt": False,
        "claim_boundary": "bounded transitional C0 execution",
    }
    canonical = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    receipt["receipt_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return receipt


def test_native_phase5_receipt_is_strict_and_self_hashed() -> None:
    receipt = _native_receipt()
    stdout = "retained browser output\n" + json.dumps(receipt, separators=(",", ":"))

    assert runner._native_receipt(stdout, skip_build=False) == receipt
    forged = {**receipt, "direct_processes_spawned": 2}
    assert runner._native_receipt(json.dumps(forged), skip_build=False) == {}
    assert (
        runner._native_receipt(
            '{"schema_version":"first","schema_version":"forged"}',
            skip_build=False,
        )
        == {}
    )
    assert runner._native_receipt('{"loopback_port":NaN}', skip_build=False) == {}


def test_phase5_wrapper_launches_one_direct_rust_command(monkeypatch: Any) -> None:
    receipt = _native_receipt()
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(receipt, separators=(",", ":")) + "\n",
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    payload = runner.run_phase5_task_based_ux_browser_smoke(
        repo_root=ROOT,
        source_commit_sha="a" * 40,
    )

    assert payload["contract_pass"] is True
    assert payload["browser_execution_passed"] is True
    assert payload["executed_workflow_steps"] == runner.WORKFLOW_STEPS
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == runner.NATIVE_CMD
    assert not {"npm", "npx", "node"}.intersection(command)
    assert kwargs["cwd"] == ROOT
    assert kwargs["check"] is False
    assert payload["commands"]["native"]["receipt_hash"] == receipt["receipt_hash"]
    assert payload["commands"]["preview"]["owned_by"] == (
        "structural-frontend-contract"
    )
    assert payload["commands"]["playwright"]["argv"] == runner.PLAYWRIGHT_CMD


def test_phase5_wrapper_preserves_skip_build_in_native_command(monkeypatch: Any) -> None:
    receipt = _native_receipt(skip_build=True)
    observed: list[str] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(receipt), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    payload = runner.run_phase5_task_based_ux_browser_smoke(
        repo_root=ROOT,
        source_commit_sha="b" * 40,
        skip_build=True,
    )

    assert payload["contract_pass"] is True
    assert observed == [*runner.NATIVE_CMD, "--skip-build"]
    assert payload["commands"]["build"]["skipped"] is True


def test_phase5_wrapper_classifies_native_loopback_permission_failure(
    monkeypatch: Any,
) -> None:
    error = {
        "schema_version": "structural-frontend-contract-error.v1",
        "code": "phase5_task_browser_smoke_bind_failed",
        "detail": "bind Playwright loopback server failed: Operation not permitted (os error 1)",
    }

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(error), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    payload = runner.run_phase5_task_based_ux_browser_smoke(
        repo_root=ROOT,
        source_commit_sha="c" * 40,
        skip_build=True,
    )

    assert payload["contract_pass"] is False
    assert payload["failed_phase"] == "preview_server_start"
    assert payload["blocker"] == runner.PREVIEW_LOOPBACK_BIND_BLOCKER
    assert payload["blocker_reason_code"] == runner.PREVIEW_LOOPBACK_BIND_REASON_CODE
    assert payload["environment_blocker"] is True
    assert payload["blocker_evidence"]["port"] == 4173


def test_phase5_wrapper_rejects_zero_exit_without_native_receipt(monkeypatch: Any) -> None:
    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="browser passed\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    payload = runner.run_phase5_task_based_ux_browser_smoke(
        repo_root=ROOT,
        source_commit_sha="d" * 40,
    )

    assert payload["contract_pass"] is False
    assert payload["failed_phase"] == "native_receipt_validation"
    assert payload["blocker"] == "native_phase5_task_browser_receipt_invalid"
