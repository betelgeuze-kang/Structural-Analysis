#!/usr/bin/env python3
"""Build and verify an exact-source support-bundle completeness receipt.

The support-bundle contract is intentionally narrower than release readiness.
It proves that the required handoff artifacts are present, redacted, and
round-trip clean while preserving OPEN/BLOCKED child statuses verbatim.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_support_bundle import build_support_bundle  # noqa: E402
from check_p0_closure_status import build_status as build_p0_status  # noqa: E402
from check_p1_readiness_status import build_status as build_p1_status  # noqa: E402
from implementation.phase1.project_ops_api_service import (  # noqa: E402
    write_project_ops_snapshot,
)
from validate_client_input_package import (  # noqa: E402
    validate_client_input_package,
)


SCHEMA_VERSION = "current-support-bundle-receipt.v1"
DEFAULT_OUTPUT_ROOT = Path(".ci/current-support-bundle")
DEFAULT_CLIENT_FIXTURE = Path(
    "tests/fixtures/current_support_bundle/client_input/model.json"
).parent
RECEIPT_NAME = "current-support-bundle-receipt.v1.json"
GENERATED_INPUT_LABELS = (
    "p0_status",
    "p1_status",
    "project_ops_snapshot",
    "client_input_validation_report",
)
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class CurrentSupportBundleError(RuntimeError):
    """Raised when current-source bundle materialization fails closed."""


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_text(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CurrentSupportBundleError(f"git_identity_unavailable:{args[0]}") from exc


def _git_identity() -> dict[str, Any]:
    commit_sha = _git_text("rev-parse", "HEAD")
    tree_sha = _git_text("rev-parse", "HEAD^{tree}")
    if SHA_PATTERN.fullmatch(commit_sha) is None:
        raise CurrentSupportBundleError("source_commit_sha_invalid")
    if SHA_PATTERN.fullmatch(tree_sha) is None:
        raise CurrentSupportBundleError("source_tree_sha_invalid")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "worktree_clean": not bool(status),
    }


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else REPO_ROOT / path


def _head_fixture_files(fixture: Path) -> list[str]:
    resolved = fixture.resolve()
    try:
        relative = resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise CurrentSupportBundleError("client_fixture_outside_repository") from exc
    output = _git_text("ls-tree", "-r", "--name-only", "HEAD", "--", relative)
    return [row for row in output.splitlines() if row]


def _file_row(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CurrentSupportBundleError(f"artifact_missing:{_display_path(path)}")
    return {
        "path": _display_path(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _artifact_hash(payload: dict[str, Any]) -> str:
    return _canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CurrentSupportBundleError(f"json_object_required:{_display_path(path)}")
    return payload


def _status_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in payload.get("gates", []):
        if not isinstance(gate, dict):
            continue
        rows.append(gate)
        children = gate.get("children")
        if isinstance(children, list):
            rows.extend(row for row in children if isinstance(row, dict))
    return rows


def _readiness_snapshot(
    *,
    p0: dict[str, Any],
    p1: dict[str, Any],
    project_ops: dict[str, Any],
    client_input: dict[str, Any],
) -> dict[str, Any]:
    return {
        "p0": {
            "status": p0.get("status"),
            "p0_closed": p0.get("p0_closed"),
            "core_evidence_closed": p0.get("core_evidence_closed"),
            "release_publication_closed": p0.get("release_publication_closed"),
            "open_gates": [
                str(row.get("label", ""))
                for row in _status_rows(p0)
                if row.get("ok") is False
            ],
        },
        "p1": {
            "status": p1.get("status"),
            "p1_inputs_ready": p1.get("p1_inputs_ready"),
            "p1_execution_unblocked": p1.get("p1_execution_unblocked"),
            "p0_release_blocker": p1.get("p0_release_blocker"),
            "blocked_gates": [
                str(row.get("label", ""))
                for row in _status_rows(p1)
                if row.get("ok") is False
            ],
        },
        "project_ops": {
            "contract_pass": project_ops.get("contract_pass"),
            "reason_code": project_ops.get("reason_code"),
            "summary_line": project_ops.get("summary_line"),
        },
        "client_input_reference_fixture": {
            "contract_pass": client_input.get("contract_pass"),
            "status": client_input.get("status"),
            "reason_code": client_input.get("reason_code"),
            "source_authority": (
                client_input.get("input_binding", {}).get("source_kind")
                if isinstance(client_input.get("input_binding"), dict)
                else None
            ),
        },
    }


def _technical_checks(
    *,
    identity: dict[str, Any],
    expected_source_sha: str,
    fixture: Path,
    fixture_head_files: list[str],
    p0: dict[str, Any],
    p1: dict[str, Any],
    project_ops: dict[str, Any],
    client_input: dict[str, Any],
    support_bundle: dict[str, Any],
) -> dict[str, bool]:
    binding = (
        client_input.get("input_binding")
        if isinstance(client_input.get("input_binding"), dict)
        else {}
    )
    required_sections = (
        support_bundle.get("required_sections")
        if isinstance(support_bundle.get("required_sections"), dict)
        else {}
    )
    bundle_index = (
        support_bundle.get("bundle_index")
        if isinstance(support_bundle.get("bundle_index"), dict)
        else {}
    )
    checks = (
        support_bundle.get("checks")
        if isinstance(support_bundle.get("checks"), dict)
        else {}
    )
    return {
        "source_worktree_clean": identity.get("worktree_clean") is True,
        "source_commit_matches_expected": identity.get("commit_sha")
        == expected_source_sha,
        "client_fixture_tracked_at_source_head": bool(fixture_head_files),
        "client_fixture_directory": fixture.is_dir() and not fixture.is_symlink(),
        "p0_status_explicit": (
            p0.get("status") in {"open", "closed"}
            and isinstance(p0.get("p0_closed"), bool)
            and isinstance(p0.get("core_evidence_closed"), bool)
            and isinstance(p0.get("release_publication_closed"), bool)
        ),
        "p1_status_explicit": (
            p1.get("status") in {"ready", "blocked"}
            and isinstance(p1.get("p1_inputs_ready"), bool)
            and isinstance(p1.get("p1_execution_unblocked"), bool)
            and isinstance(p1.get("p0_release_blocker"), bool)
        ),
        "project_ops_status_explicit": (
            isinstance(project_ops.get("contract_pass"), bool)
            and project_ops.get("reason_code") in {"PASS", "CHECK", "ERR_INPUT"}
        ),
        "client_reference_fixture_ready": (
            client_input.get("contract_pass") is True
            and client_input.get("status") == "ready"
        ),
        "client_reference_fixture_current_worktree_bound": (
            binding.get("source_kind") == "repository_reference_fixture"
            and binding.get("repository_path") == _display_path(fixture)
            and binding.get("current_worktree_bound") is True
            and binding.get("commit_tree_bound") is False
            and binding.get("source_commit_sha") == identity.get("commit_sha")
        ),
        "generated_missing_four_present": all(
            required_sections.get(label) not in {None, "", "missing"}
            for label in GENERATED_INPUT_LABELS
        ),
        "support_bundle_contract_pass": support_bundle.get("contract_pass")
        is True,
        "support_bundle_missing_required_zero": checks.get(
            "missing_required_count"
        )
        == 0,
        "support_bundle_all_artifacts_available": (
            isinstance(bundle_index.get("artifact_count"), int)
            and bundle_index.get("artifact_count", 0) > 0
            and bundle_index.get("available_artifact_count")
            == bundle_index.get("artifact_count")
        ),
        "support_bundle_redaction_pass": checks.get("redaction_self_test_pass")
        is True,
        "support_bundle_roundtrip_pass": checks.get("bundle_roundtrip_test_pass")
        is True,
        "support_bundle_archive_roundtrip_pass": checks.get(
            "archive_roundtrip_test_pass"
        )
        is True,
        "support_bundle_pm_failure_coverage_pass": checks.get(
            "pm_failure_bundle_coverage_pass"
        )
        is True,
    }


def _recorded_artifact_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    generated = payload.get("generated_inputs")
    support = payload.get("support_bundle")
    if not isinstance(generated, dict) or not isinstance(support, dict):
        raise CurrentSupportBundleError("receipt_artifact_sections_invalid")
    rows = [generated.get(label) for label in GENERATED_INPUT_LABELS]
    rows.extend(
        support.get(label)
        for label in (
            "manifest",
            "bundle_index",
            "pm_failure_bundle_coverage",
            "archive",
        )
    )
    if not all(isinstance(row, dict) for row in rows):
        raise CurrentSupportBundleError("receipt_artifact_row_invalid")
    return rows  # type: ignore[return-value]


def _validate_expected_sha(expected_source_sha: str, actual_sha: str) -> str:
    expected = expected_source_sha or actual_sha
    if SHA_PATTERN.fullmatch(expected) is None:
        raise CurrentSupportBundleError("expected_source_sha_invalid")
    return expected


def build_current_support_bundle(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    client_fixture: Path = DEFAULT_CLIENT_FIXTURE,
    expected_source_sha: str = "",
) -> dict[str, Any]:
    if Path.cwd().resolve() != REPO_ROOT.resolve():
        raise CurrentSupportBundleError("repository_root_working_directory_required")
    if output_root.exists():
        raise CurrentSupportBundleError(
            f"output_root_already_exists:{_display_path(output_root)}"
        )

    identity = _git_identity()
    expected = _validate_expected_sha(expected_source_sha, identity["commit_sha"])
    if identity["worktree_clean"] is not True:
        raise CurrentSupportBundleError("source_worktree_not_clean")
    if identity["commit_sha"] != expected:
        raise CurrentSupportBundleError("source_commit_does_not_match_expected")
    fixture_head_files = _head_fixture_files(client_fixture)
    if not fixture_head_files:
        raise CurrentSupportBundleError("client_fixture_not_tracked_at_source_head")

    generated_root = output_root / "generated"
    p0_path = generated_root / "p0-status.json"
    p1_path = generated_root / "p1-readiness-status.json"
    project_ops_path = generated_root / "project-ops-service-snapshot.json"
    client_input_path = generated_root / "client-input-validation-report.json"
    manifest_path = output_root / "support-bundle-manifest.json"
    bundle_dir = output_root / "bundle"
    archive_path = output_root / "support-bundle-export.zip"
    receipt_path = output_root / RECEIPT_NAME

    p0 = build_p0_status()
    _write_json(p0_path, p0)
    p1 = build_p1_status(p0_status=p0_path)
    _write_json(p1_path, p1)
    project_ops = write_project_ops_snapshot(project_ops_path)
    client_input = validate_client_input_package(
        input_path=client_fixture,
        source_kind="repository_reference_fixture",
    )
    _write_json(client_input_path, client_input)
    support_bundle = build_support_bundle(
        bundle_dir=bundle_dir,
        archive_out=archive_path,
        p0_status=p0_path,
        p1_status=p1_path,
        project_ops_snapshot=project_ops_path,
        client_input_validation_report=client_input_path,
    )
    _write_json(manifest_path, support_bundle)

    checks = _technical_checks(
        identity=identity,
        expected_source_sha=expected,
        fixture=client_fixture,
        fixture_head_files=fixture_head_files,
        p0=p0,
        p1=p1,
        project_ops=project_ops,
        client_input=client_input,
        support_bundle=support_bundle,
    )
    blockers = [label for label, passed in checks.items() if not passed]
    bundle_index_path = Path(str(support_bundle["bundle_index"]["path"]))
    pm_failure_path = Path(
        str(support_bundle["pm_failure_bundle_coverage"]["bundle_path"])
    )
    artifact_count = int(support_bundle["bundle_index"]["artifact_count"])
    available_count = int(
        support_bundle["bundle_index"]["available_artifact_count"]
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source": {
            **identity,
            "expected_commit_sha": expected,
            "client_reference_fixture": _display_path(client_fixture),
            "client_reference_fixture_head_files": fixture_head_files,
        },
        "contract_pass": not blockers,
        "reason_code": (
            "PASS" if not blockers else "ERR_CURRENT_SUPPORT_BUNDLE_INCOMPLETE"
        ),
        "summary_line": (
            f"Current support bundle: {'PASS' if not blockers else 'BLOCKED'} | "
            f"artifacts={available_count}/{artifact_count} | "
            f"p0={p0.get('status')} | p1={p1.get('status')} | "
            f"project_ops={project_ops.get('reason_code')}"
        ),
        "output_root": _display_path(output_root),
        "generated_inputs": {
            "p0_status": _file_row(p0_path),
            "p1_status": _file_row(p1_path),
            "project_ops_snapshot": _file_row(project_ops_path),
            "client_input_validation_report": _file_row(client_input_path),
        },
        "support_bundle": {
            "manifest": _file_row(manifest_path),
            "bundle_index": _file_row(bundle_index_path),
            "pm_failure_bundle_coverage": _file_row(pm_failure_path),
            "archive": _file_row(archive_path),
            "artifact_count": artifact_count,
            "available_artifact_count": available_count,
            "missing_required_count": support_bundle["checks"][
                "missing_required_count"
            ],
        },
        "readiness_status_preserved": _readiness_snapshot(
            p0=p0,
            p1=p1,
            project_ops=project_ops,
            client_input=client_input,
        ),
        "checks": checks,
        "blockers": blockers,
        "claim_boundary": {
            "allowed": [
                "exact-source support-bundle input availability",
                "redaction and bundle/archive roundtrip",
                "current readiness-state handoff",
            ],
            "not_granted": [
                "P0 or P1 closure",
                "project-operations readiness",
                "human new-user observation",
                "client-source authenticity",
                "product code signing or platform notarization",
                "release, commercial, or engineering-design authority",
            ],
            "sigstore_note": (
                "Workflow attestation proves receipt provenance only; it is not "
                "an embedded product signature or platform code-signing authority."
            ),
        },
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    _write_json(receipt_path, payload)
    return payload


def verify_current_support_bundle(
    *,
    receipt_path: Path,
    expected_source_sha: str = "",
) -> dict[str, Any]:
    if Path.cwd().resolve() != REPO_ROOT.resolve():
        raise CurrentSupportBundleError("repository_root_working_directory_required")
    payload = _json_object(receipt_path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CurrentSupportBundleError("receipt_schema_version_invalid")
    if payload.get("artifact_hash") != _artifact_hash(payload):
        raise CurrentSupportBundleError("receipt_artifact_hash_invalid")

    identity = _git_identity()
    expected = _validate_expected_sha(expected_source_sha, identity["commit_sha"])
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if (
        identity["worktree_clean"] is not True
        or identity["commit_sha"] != expected
        or source.get("commit_sha") != identity["commit_sha"]
        or source.get("tree_sha") != identity["tree_sha"]
        or source.get("expected_commit_sha") != expected
        or source.get("worktree_clean") is not True
    ):
        raise CurrentSupportBundleError("receipt_source_binding_invalid")

    output_root = _resolve_path(str(payload.get("output_root", ""))).resolve()
    try:
        receipt_path.resolve().relative_to(output_root)
    except ValueError as exc:
        raise CurrentSupportBundleError("receipt_outside_output_root") from exc
    for row in _recorded_artifact_rows(payload):
        path = _resolve_path(str(row.get("path", ""))).resolve()
        try:
            path.relative_to(output_root)
        except ValueError as exc:
            raise CurrentSupportBundleError("artifact_outside_output_root") from exc
        if (
            not path.is_file()
            or row.get("bytes") != path.stat().st_size
            or row.get("sha256") != _sha256_path(path)
        ):
            raise CurrentSupportBundleError(
                f"artifact_binding_invalid:{_display_path(path)}"
            )

    fixture = _resolve_path(str(source.get("client_reference_fixture", "")))
    fixture_head_files = _head_fixture_files(fixture)
    if fixture_head_files != source.get("client_reference_fixture_head_files"):
        raise CurrentSupportBundleError("client_fixture_head_binding_invalid")
    generated = payload["generated_inputs"]
    support = payload["support_bundle"]
    p0 = _json_object(_resolve_path(generated["p0_status"]["path"]))
    p1 = _json_object(_resolve_path(generated["p1_status"]["path"]))
    project_ops = _json_object(
        _resolve_path(generated["project_ops_snapshot"]["path"])
    )
    client_input = _json_object(
        _resolve_path(generated["client_input_validation_report"]["path"])
    )
    support_bundle = _json_object(_resolve_path(support["manifest"]["path"]))
    checks = _technical_checks(
        identity=identity,
        expected_source_sha=expected,
        fixture=fixture,
        fixture_head_files=fixture_head_files,
        p0=p0,
        p1=p1,
        project_ops=project_ops,
        client_input=client_input,
        support_bundle=support_bundle,
    )
    blockers = [label for label, passed in checks.items() if not passed]
    readiness = _readiness_snapshot(
        p0=p0,
        p1=p1,
        project_ops=project_ops,
        client_input=client_input,
    )
    bundle_index = support_bundle.get("bundle_index", {})
    if (
        payload.get("checks") != checks
        or payload.get("blockers") != blockers
        or payload.get("contract_pass") is not (not blockers)
        or payload.get("readiness_status_preserved") != readiness
        or support.get("artifact_count") != bundle_index.get("artifact_count")
        or support.get("available_artifact_count")
        != bundle_index.get("available_artifact_count")
        or support.get("missing_required_count")
        != support_bundle.get("checks", {}).get("missing_required_count")
    ):
        raise CurrentSupportBundleError("receipt_contract_invalid")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument(
        "--client-fixture", type=Path, default=DEFAULT_CLIENT_FIXTURE
    )
    build.add_argument("--expected-source-sha", default="")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--expected-source-sha", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            payload = build_current_support_bundle(
                output_root=args.output_root,
                client_fixture=args.client_fixture,
                expected_source_sha=args.expected_source_sha,
            )
        else:
            payload = verify_current_support_bundle(
                receipt_path=args.receipt,
                expected_source_sha=args.expected_source_sha,
            )
    except (CurrentSupportBundleError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"current support bundle failed: {exc}", file=sys.stderr)
        return 2
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
