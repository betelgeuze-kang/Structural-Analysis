from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_frontend_dependency_audit_report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_frontend_dependency_audit_report", SCRIPT_PATH
)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


def _sha256_identity(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _report(*, contract_pass: bool) -> tuple[dict[str, Any], bytes]:
    high = 0 if contract_pass else 1
    blockers = (
        []
        if contract_pass
        else [
            "frontend_dependency_high_or_critical_vulnerabilities_present",
            "frontend_dependency_vulnerabilities_present",
        ]
    )
    payload: dict[str, Any] = {
        "schema_version": "frontend-dependency-audit-report.v1",
        "generated_at": "2026-08-13T12:34:56Z",
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS"
            if contract_pass
            else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED"
        ),
        "blockers": blockers,
        "checks": {
            "package_json_present": True,
            "package_lock_present": True,
            "npm_audit_json_parse_pass": True,
            "dependency_vulnerability_total_zero_pass": contract_pass,
            "dependency_high_or_critical_zero_pass": contract_pass,
            "npm_audit_exit_code_zero_pass": contract_pass,
        },
        "summary": {
            "package_json": "package.json",
            "package_lock": "package-lock.json",
            "npm_audit_exit_code": 0 if contract_pass else 1,
            "vulnerability_total": high,
            "high_or_critical_vulnerability_count": high,
            "info_vulnerability_count": 0,
            "low_vulnerability_count": 0,
            "moderate_vulnerability_count": 0,
            "high_vulnerability_count": high,
            "critical_vulnerability_count": 0,
        },
        "vulnerabilities": [],
        "diagnostics": {
            "npm_audit_stdout_bytes": 100,
            "npm_audit_stderr_tail": "",
        },
        "claim_boundary": "bounded native report",
    }
    return payload, (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _receipt(
    *, requested: Path, report: dict[str, Any], report_bytes: bytes
) -> dict[str, Any]:
    summary = report["summary"]
    receipt: dict[str, Any] = {
        "schema_version": "structural-native-frontend-audit-report-receipt.v1",
        "action": "frontend_audit_report",
        "status": (
            "published_pass" if report["contract_pass"] else "published_blocked"
        ),
        "source_map_sha256": "sha256:" + "1" * 64,
        "frontend_contract_receipt_hash": "sha256:" + "2" * 64,
        "logical_command": ["npm", "audit", "--json"],
        "process_launcher": "npm",
        "node_options_disposition": "removed_for_direct_child",
        "direct_processes_spawned": 1,
        "observed_exit_code": summary["npm_audit_exit_code"],
        "report": {
            "path": str(requested),
            "byte_length": len(report_bytes),
            "sha256": _sha256_identity(report_bytes),
            "publication_strategy": (
                "bounded_staging_then_backup_rename_with_rollback"
            ),
        },
        "contract_pass": report["contract_pass"],
        "reason_code": report["reason_code"],
        "blocker_count": len(report["blockers"]),
        "vulnerability_total": summary["vulnerability_total"],
        "high_or_critical_vulnerability_count": summary[
            "high_or_critical_vulnerability_count"
        ],
        "network_access_accounting": "bounded network claim",
        "filesystem_mutation_accounting": "bounded filesystem claim",
        "environment_accounting": "bounded environment claim",
        "deterministic_receipt": False,
        "claim_boundary": "bounded native receipt",
    }
    canonical = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    receipt["receipt_hash"] = _sha256_identity(canonical)
    return receipt


def test_wrapper_launches_one_direct_native_command_and_validates_report(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    requested = Path("evidence/audit.json")
    payload, report_bytes = _report(contract_pass=True)
    receipt = _receipt(
        requested=requested, report=payload, report_bytes=report_bytes
    )
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        output = tmp_path / requested
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(report_bytes)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(receipt) + "\n", stderr=""
        )

    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main(["--out", str(requested)]) == 0
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[: len(runner.NATIVE_COMMAND)] == runner.NATIVE_COMMAND
    assert not {"npm", "npx", "node"}.intersection(command)
    assert command[-6:] == [
        "--package-json",
        "package.json",
        "--package-lock",
        "package-lock.json",
        "--out",
        str(requested),
    ]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["check"] is False
    assert "vulnerability_total" in capsys.readouterr().out


def test_wrapper_preserves_native_fail_blocked_after_publication(
    tmp_path: Path, monkeypatch: Any
) -> None:
    requested = Path("evidence/blocked.json")
    payload, report_bytes = _report(contract_pass=False)
    receipt = _receipt(
        requested=requested, report=payload, report_bytes=report_bytes
    )
    observed: list[str] = []

    def fake_run(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        output = tmp_path / requested
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(report_bytes)
        return subprocess.CompletedProcess(
            command, 1, stdout=json.dumps(receipt) + "\n", stderr=""
        )

    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main(["--out", str(requested), "--fail-blocked"]) == 1
    assert observed[-1] == "--fail-blocked"
    assert (tmp_path / requested).is_file()


def test_wrapper_rejects_forged_receipt_and_tampered_report(
    tmp_path: Path, monkeypatch: Any
) -> None:
    requested = Path("evidence/tampered.json")
    payload, report_bytes = _report(contract_pass=True)
    receipt = _receipt(
        requested=requested, report=payload, report_bytes=report_bytes
    )

    def forged_run(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        forged = {**receipt, "vulnerability_total": 99}
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(forged), stderr=""
        )

    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", forged_run)
    assert runner.main(["--out", str(requested)]) == 1

    def tampered_run(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        output = tmp_path / requested
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(report_bytes + b" ")
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(receipt), stderr=""
        )

    monkeypatch.setattr(runner.subprocess, "run", tampered_run)
    assert runner.main(["--out", str(requested)]) == 1


def test_strict_receipt_parser_rejects_duplicate_and_nonfinite_json() -> None:
    assert runner._receipt_from_stdout('{"action":"a","action":"b"}') == {}
    assert runner._receipt_from_stdout('{"blocker_count":NaN}') == {}
