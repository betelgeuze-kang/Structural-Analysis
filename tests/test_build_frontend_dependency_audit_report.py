from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_frontend_dependency_audit_report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_frontend_dependency_audit_report", SCRIPT_PATH
)
assert SPEC is not None
audit_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit_report)

SOURCE_SHA = "a" * 40
TREE_SHA = "b" * 40


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _package_files(tmp_path: Path) -> tuple[Path, Path]:
    dependencies = {
        "ajv": audit_report.REQUIRED_AJV_VERSION,
        "react": "18.2.0",
    }
    dev_dependencies = {"vite": "8.0.16"}
    package_json = _write(
        tmp_path / "package.json",
        {
            "dependencies": dependencies,
            "devDependencies": dev_dependencies,
        },
    )
    package_lock = _write(
        tmp_path / "package-lock.json",
        {
            "packages": {
                "": {
                    "dependencies": dependencies,
                    "devDependencies": dev_dependencies,
                },
                "node_modules/ajv": {
                    "version": audit_report.REQUIRED_AJV_VERSION
                },
            }
        },
    )
    return package_json, package_lock


def _identity(*, commit: str = SOURCE_SHA, clean: bool = True) -> dict[str, object]:
    return {"commit_sha": commit, "tree_sha": TREE_SHA, "worktree_clean": clean}


def _audit_payload(
    *,
    vulnerabilities: dict[str, object] | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, object]:
    vulnerability_counts = counts or {
        "info": 0,
        "low": 0,
        "moderate": 0,
        "high": 0,
        "critical": 0,
        "total": 0,
    }
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities or {},
        "metadata": {
            "vulnerabilities": vulnerability_counts,
            "dependencies": {
                "prod": 2,
                "dev": 1,
                "optional": 0,
                "peer": 0,
                "peerOptional": 0,
                "total": 3,
            },
        },
    }


def _build(
    tmp_path: Path,
    *,
    audit_payload: dict[str, object] | None = None,
    audit_exit_code: int = 0,
    identity: dict[str, object] | None = None,
) -> tuple[dict[str, object], Path, Path]:
    package_json, package_lock = _package_files(tmp_path)
    payload = audit_payload or _audit_payload()
    report = audit_report.build_report(
        audit_payload=payload,
        audit_exit_code=audit_exit_code,
        audit_stdout=json.dumps(payload),
        source_identity=identity or _identity(),
        expected_source_sha=SOURCE_SHA,
        node_version="v20.19.0",
        npm_version="10.8.2",
        package_json=package_json,
        package_lock=package_lock,
    )
    return report, package_json, package_lock


def test_frontend_dependency_audit_blocks_moderate_vulnerability(
    tmp_path: Path,
) -> None:
    vulnerability = {
        "ajv": {
            "name": "ajv",
            "severity": "moderate",
            "isDirect": True,
            "range": "7.0.0-alpha.0 - 8.17.1",
            "fixAvailable": {
                "name": "ajv",
                "version": audit_report.REQUIRED_AJV_VERSION,
                "isSemVerMajor": False,
            },
            "via": [
                {
                    "title": "ajv has ReDoS when using `$data` option",
                    "severity": "moderate",
                    "url": "https://github.com/advisories/GHSA-2g4f-4pwh-qvx6",
                    "range": ">=7.0.0-alpha.0 <8.18.0",
                }
            ],
        }
    }
    counts = {
        "info": 0,
        "low": 0,
        "moderate": 1,
        "high": 0,
        "critical": 0,
        "total": 1,
    }
    payload, _, _ = _build(
        tmp_path,
        audit_payload=_audit_payload(vulnerabilities=vulnerability, counts=counts),
        audit_exit_code=1,
    )

    assert payload["contract_pass"] is False
    assert "dependency_vulnerability_total_zero_pass" in payload["blockers"]
    assert payload["summary"]["moderate_vulnerability_count"] == 1
    assert (
        payload["vulnerabilities"][0]["fix_available"]["version"]
        == audit_report.REQUIRED_AJV_VERSION
    )


def test_zero_report_binds_source_manifests_payload_and_verifies(
    tmp_path: Path,
) -> None:
    payload, package_json, package_lock = _build(tmp_path)

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert all(payload["checks"].values())
    assert payload["source"] == {
        "commit_sha": SOURCE_SHA,
        "tree_sha": TREE_SHA,
        "expected_commit_sha": SOURCE_SHA,
        "worktree_clean": True,
    }
    assert payload["inputs"]["package_json"]["sha256"].startswith("sha256:")
    assert payload["inputs"]["package_lock"]["sha256"].startswith("sha256:")
    assert payload["audit"]["payload"]["metadata"]["vulnerabilities"]["total"] == 0
    assert "license or third-party redistribution clearance" in payload[
        "claim_boundary"
    ]["not_granted"]

    verified = audit_report.verify_report(
        payload,
        source_identity=_identity(),
        expected_source_sha=SOURCE_SHA,
        package_json=package_json,
        package_lock=package_lock,
    )
    assert verified == payload


def test_report_rejects_package_byte_or_source_tamper(tmp_path: Path) -> None:
    payload, package_json, package_lock = _build(tmp_path)
    package_json.write_text(package_json.read_text() + "\n", encoding="utf-8")
    with pytest.raises(
        audit_report.FrontendDependencyAuditError,
        match="report_input_bindings_invalid",
    ):
        audit_report.verify_report(
            payload,
            source_identity=_identity(),
            expected_source_sha=SOURCE_SHA,
            package_json=package_json,
            package_lock=package_lock,
        )

    with pytest.raises(
        audit_report.FrontendDependencyAuditError,
        match="report_source_binding_invalid",
    ):
        audit_report.verify_report(
            payload,
            source_identity=_identity(commit="c" * 40),
            expected_source_sha="c" * 40,
            package_json=package_json,
            package_lock=package_lock,
        )


def test_audit_metadata_and_rows_fail_closed(tmp_path: Path) -> None:
    malformed = _audit_payload()
    malformed["metadata"]["vulnerabilities"]["total"] = False
    payload, _, _ = _build(tmp_path / "malformed", audit_payload=malformed)
    assert payload["contract_pass"] is False
    assert payload["checks"]["npm_audit_metadata_consistent"] is False

    hidden_row = _audit_payload(
        vulnerabilities={
            "ajv": {
                "name": "ajv",
                "severity": "moderate",
                "isDirect": True,
                "via": [],
            }
        }
    )
    payload, _, _ = _build(tmp_path / "hidden", audit_payload=hidden_row)
    assert payload["contract_pass"] is False
    assert payload["checks"]["npm_audit_vulnerability_rows_match_metadata"] is False


def test_audit_rejects_old_or_non_exact_ajv_lock(tmp_path: Path) -> None:
    payload, package_json, package_lock = _build(tmp_path)
    manifest = json.loads(package_json.read_text(encoding="utf-8"))
    manifest["dependencies"]["ajv"] = "8.17.1"
    package_json.write_text(json.dumps(manifest), encoding="utf-8")
    lock = json.loads(package_lock.read_text(encoding="utf-8"))
    lock["packages"][""]["dependencies"]["ajv"] = "8.17.1"
    lock["packages"]["node_modules/ajv"]["version"] = "8.17.1"
    package_lock.write_text(json.dumps(lock), encoding="utf-8")
    old_payload = _audit_payload()
    payload = audit_report.build_report(
        audit_payload=old_payload,
        audit_exit_code=0,
        audit_stdout=json.dumps(old_payload),
        source_identity=_identity(),
        expected_source_sha=SOURCE_SHA,
        node_version="v20.19.0",
        npm_version="10.8.2",
        package_json=package_json,
        package_lock=package_lock,
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["ajv_direct_runtime_fixed_exact_version"] is False


def test_artifact_hash_and_claim_boundary_tamper_rejected(tmp_path: Path) -> None:
    payload, package_json, package_lock = _build(tmp_path)
    payload["claim_boundary"]["not_granted"] = []
    with pytest.raises(
        audit_report.FrontendDependencyAuditError,
        match="report_artifact_hash_invalid",
    ):
        audit_report.verify_report(
            payload,
            source_identity=_identity(),
            expected_source_sha=SOURCE_SHA,
            package_json=package_json,
            package_lock=package_lock,
        )


def test_hash_coherent_stdout_payload_split_is_rejected(tmp_path: Path) -> None:
    payload, package_json, package_lock = _build(tmp_path)
    payload["audit"]["stdout"] = json.dumps(
        {"auditReportVersion": 2, "vulnerabilities": {"hidden": {}}}
    )
    payload["audit"]["stdout_bytes"] = len(payload["audit"]["stdout"].encode())
    payload["audit"]["stdout_sha256"] = audit_report._sha256_bytes(
        payload["audit"]["stdout"].encode()
    )
    payload["artifact_hash"] = audit_report._canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )

    with pytest.raises(
        audit_report.FrontendDependencyAuditError,
        match="report_audit_stdout_binding_invalid",
    ):
        audit_report.verify_report(
            payload,
            source_identity=_identity(),
            expected_source_sha=SOURCE_SHA,
            package_json=package_json,
            package_lock=package_lock,
        )
