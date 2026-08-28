#!/usr/bin/env python3
"""Build and verify an exact-source support-bundle completeness receipt.

The support-bundle contract is intentionally narrower than release readiness.
It proves that the required handoff artifacts are present, redacted, and
round-trip clean while preserving OPEN/BLOCKED child statuses verbatim.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_support_bundle import (  # noqa: E402
    SCHEMA_VERSION as SUPPORT_BUNDLE_SCHEMA_VERSION,
    _archive_roundtrip_self_test,
    _build_export_archive,
    _build_pm_failure_bundle_coverage,
    _redact_text,
    _redaction_self_test,
    build_support_bundle,
    redact_payload,
)
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
SUPPORT_REQUIRED_LABELS = (
    "p0_status",
    "p1_status",
    "p1_strict_evidence_preflight",
    "project_ops_snapshot",
    "project_ops_deployment_drill",
    "runtime_probe",
    "runtime_packaging_manifest",
    "viewer_performance_budget_manifest",
    "viewer_browser_performance_probe",
    "viewer_visual_regression_baseline",
    "workstation_hardware_profile",
    "workstation_service_budget",
    "workstation_delivery_package_manifest",
    "workstation_delivery_readiness",
    "workstation_delivery_viewer_smoke",
    "client_input_validation_report",
    "workstation_job_record",
    "workstation_job_retention_policy",
    "external_benchmark_updates",
    "residual_holdout_updates",
    "package_json",
    "pyproject",
)
SUPPORT_OPTIONAL_LABELS = (
    "pm_release_blocker_action_register",
    "pm_release_blocker_closure_board",
    "pm_release_gate_completion_audit",
    "pm_release_gate_reviewer_handoff",
    "pm_owner_evidence_request_packet",
    "structural_scope_owner_review_packet",
    "developer_preview_final_gate_owner_packet",
    "ci_streak_intake_packet",
    "ci_streak_manifest",
    "github_actions_ci_streak_evidence",
    "license_status_intake_packet",
    "license_status_closure_report",
    "license_status_template",
    "frontend_dependency_audit_report",
    "ga_enterprise_readiness_report",
    "ga_enterprise_signoff_intake_packet",
    "fresh_full_validation_lane_status",
    "independent_vv_attestation_template",
    "family_validation_manual_signoff_template",
    "customer_audit_failure_bundle_sla_template",
    "paid_pilot_scope_guard_report",
    "release_validation_manual",
    "release_limitation_manual",
    "ux_new_user_observation_report",
    "ux_new_user_observation_intake_packet",
    "ux_new_user_observation_template",
    "template_evidence_safety_report",
    "pm_release_reproduction_command_audit",
    "ai_orchestration_preflight_report",
    "commercial_gap_ledger_status",
    "gap_closure_status",
)
SUPPORT_ALL_LABELS = (*SUPPORT_REQUIRED_LABELS, *SUPPORT_OPTIONAL_LABELS)
_SUPPORT_BUILDER_DEFAULTS = build_support_bundle.__kwdefaults__ or {}
SUPPORT_DEFAULT_SOURCE_PATHS = {
    label: Path(_SUPPORT_BUILDER_DEFAULTS[label])
    for label in SUPPORT_ALL_LABELS
    if label not in GENERATED_INPUT_LABELS
}
SUPPORT_BUNDLE_POLICY = {
    "redact_secrets": True,
    "include_private_keys": False,
    "include_tokens": False,
    "tenant_scoped": True,
    "copy_mode": "redacted_evidence_plus_digest",
    "one_click_export": True,
    "export_format": "zip",
}
CLIENT_CLAIM_BOUNDARY = {
    "allowed": "bounded input-package shape and metadata validation",
    "forbidden": [
        "structural adequacy approval",
        "client-source authenticity",
        "engineer-of-record approval",
    ],
    "source_authority": "repository_reference_fixture",
}
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
CLAIM_BOUNDARY = {
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
        "freshness or current authority of pre-existing bundled evidence",
        "product code signing or platform notarization",
        "release, commercial, or engineering-design authority",
    ],
    "sigstore_note": (
        "Workflow attestation proves receipt provenance only; it is not an "
        "embedded product signature or platform code-signing authority."
    ),
}
RECEIPT_TOP_LEVEL_KEYS = {
    "artifact_hash",
    "blockers",
    "checks",
    "claim_boundary",
    "contract_pass",
    "generated_at",
    "generated_inputs",
    "output_root",
    "readiness_status_preserved",
    "reason_code",
    "schema_version",
    "source",
    "summary_line",
    "support_bundle",
}
TECHNICAL_CHECK_LABELS = (
    "source_worktree_clean",
    "source_commit_matches_expected",
    "client_fixture_tracked_at_source_head",
    "client_fixture_directory",
    "p0_status_explicit",
    "p0_status_current_source_and_coherent",
    "p1_status_explicit",
    "p1_status_current_source_and_coherent",
    "p0_p1_producer_semantics_replayed",
    "project_ops_status_explicit",
    "project_ops_status_coherent",
    "client_reference_fixture_ready",
    "client_reference_fixture_current_worktree_bound",
    "client_reference_fixture_artifact_hash_valid",
    "client_reference_fixture_producer_semantics_replayed",
    "generated_missing_four_present",
    "support_bundle_contract_pass",
    "support_bundle_missing_required_zero",
    "support_bundle_all_artifacts_available",
    "support_bundle_redaction_pass",
    "support_bundle_roundtrip_pass",
    "support_bundle_archive_roundtrip_pass",
    "support_bundle_pm_failure_coverage_pass",
    "support_bundle_transitive_bindings_pass",
    "support_bundle_layout_pass",
    "support_bundle_producer_semantics_replayed",
)


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


def _reject_lexical_symlink_components(path: Path) -> None:
    lexical = Path(os.path.abspath(os.fspath(path)))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            raise CurrentSupportBundleError(f"output_path_symlink_forbidden:{current}")


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
    def object_without_duplicates(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CurrentSupportBundleError(
                    f"json_duplicate_key:{_display_path(path)}:{key}"
                )
            result[key] = value
        return result

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=object_without_duplicates,
        parse_constant=lambda token: (_ for _ in ()).throw(
            CurrentSupportBundleError(
                f"json_nonfinite_value:{_display_path(path)}:{token}"
            )
        ),
    )
    if not isinstance(payload, dict):
        raise CurrentSupportBundleError(f"json_object_required:{_display_path(path)}")
    return payload


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(
        parsed
    )


def _receipt_artifact_row_shape(row: Any) -> bool:
    return bool(
        isinstance(row, dict)
        and set(row) == {"path", "bytes", "sha256"}
        and isinstance(row.get("path"), str)
        and bool(row.get("path"))
        and isinstance(row.get("bytes"), int)
        and not isinstance(row.get("bytes"), bool)
        and row["bytes"] >= 0
        and isinstance(row.get("sha256"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", row["sha256"]) is not None
    )


def _receipt_shape_pass(payload: dict[str, Any]) -> bool:
    try:
        source = payload.get("source")
        generated = payload.get("generated_inputs")
        support = payload.get("support_bundle")
        readiness = payload.get("readiness_status_preserved")
        checks = payload.get("checks")
        blockers = payload.get("blockers")
        if (
            set(payload) != RECEIPT_TOP_LEVEL_KEYS
            or payload.get("schema_version") != SCHEMA_VERSION
            or not _utc_timestamp(payload.get("generated_at"))
            or not isinstance(payload.get("contract_pass"), bool)
            or not isinstance(payload.get("reason_code"), str)
            or not isinstance(payload.get("summary_line"), str)
            or not isinstance(payload.get("output_root"), str)
            or not payload.get("output_root")
            or not isinstance(payload.get("artifact_hash"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", payload["artifact_hash"]) is None
            or not isinstance(blockers, list)
            or not all(isinstance(item, str) and item for item in blockers)
            or len(blockers) != len(set(blockers))
            or not isinstance(checks, dict)
            or set(checks) != set(TECHNICAL_CHECK_LABELS)
            or not all(isinstance(value, bool) for value in checks.values())
        ):
            return False
        if (
            not isinstance(source, dict)
            or set(source)
            != {
                "commit_sha",
                "tree_sha",
                "worktree_clean",
                "expected_commit_sha",
                "client_reference_fixture",
                "client_reference_fixture_head_files",
            }
            or SHA_PATTERN.fullmatch(str(source.get("commit_sha", ""))) is None
            or SHA_PATTERN.fullmatch(str(source.get("tree_sha", ""))) is None
            or SHA_PATTERN.fullmatch(str(source.get("expected_commit_sha", ""))) is None
            or not isinstance(source.get("worktree_clean"), bool)
            or not isinstance(source.get("client_reference_fixture"), str)
            or not isinstance(source.get("client_reference_fixture_head_files"), list)
            or not all(
                isinstance(item, str) and item
                for item in source["client_reference_fixture_head_files"]
            )
        ):
            return False
        if (
            not isinstance(generated, dict)
            or set(generated) != set(GENERATED_INPUT_LABELS)
            or not all(
                _receipt_artifact_row_shape(generated[label])
                for label in GENERATED_INPUT_LABELS
            )
        ):
            return False
        support_artifact_labels = (
            "manifest",
            "bundle_index",
            "pm_failure_bundle_coverage",
            "archive",
        )
        if (
            not isinstance(support, dict)
            or set(support)
            != {
                *support_artifact_labels,
                "artifact_count",
                "available_artifact_count",
                "missing_required_count",
            }
            or not all(
                _receipt_artifact_row_shape(support[label])
                for label in support_artifact_labels
            )
            or not all(
                isinstance(support.get(label), int)
                and not isinstance(support.get(label), bool)
                and support[label] >= 0
                for label in (
                    "artifact_count",
                    "available_artifact_count",
                    "missing_required_count",
                )
            )
        ):
            return False
        if not isinstance(readiness, dict) or set(readiness) != {
            "p0",
            "p1",
            "project_ops",
            "client_input_reference_fixture",
        }:
            return False
        p0 = readiness.get("p0")
        p1 = readiness.get("p1")
        project_ops = readiness.get("project_ops")
        client = readiness.get("client_input_reference_fixture")
        return bool(
            isinstance(p0, dict)
            and set(p0)
            == {
                "status",
                "p0_closed",
                "core_evidence_closed",
                "release_publication_closed",
                "open_gates",
            }
            and p0.get("status") in {"open", "closed"}
            and all(
                isinstance(p0.get(label), bool)
                for label in (
                    "p0_closed",
                    "core_evidence_closed",
                    "release_publication_closed",
                )
            )
            and isinstance(p0.get("open_gates"), list)
            and all(isinstance(item, str) and item for item in p0["open_gates"])
            and isinstance(p1, dict)
            and set(p1)
            == {
                "status",
                "p1_inputs_ready",
                "p1_execution_unblocked",
                "p0_release_blocker",
                "blocked_gates",
            }
            and p1.get("status") in {"ready", "blocked"}
            and all(
                isinstance(p1.get(label), bool)
                for label in (
                    "p1_inputs_ready",
                    "p1_execution_unblocked",
                    "p0_release_blocker",
                )
            )
            and isinstance(p1.get("blocked_gates"), list)
            and all(isinstance(item, str) and item for item in p1["blocked_gates"])
            and isinstance(project_ops, dict)
            and set(project_ops) == {"contract_pass", "reason_code", "summary_line"}
            and isinstance(project_ops.get("contract_pass"), bool)
            and isinstance(project_ops.get("reason_code"), str)
            and isinstance(project_ops.get("summary_line"), str)
            and isinstance(client, dict)
            and set(client)
            == {"contract_pass", "status", "reason_code", "source_authority"}
            and isinstance(client.get("contract_pass"), bool)
            and isinstance(client.get("status"), str)
            and isinstance(client.get("reason_code"), str)
            and isinstance(client.get("source_authority"), str)
        )
    except (KeyError, TypeError, ValueError):
        return False


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


def _strict_gates(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    gates = payload.get("gates")
    if (
        not isinstance(gates, list)
        or not gates
        or not all(isinstance(row, dict) for row in gates)
    ):
        return None
    labels: list[str] = []
    for gate in gates:
        label = gate.get("label")
        if (
            not isinstance(label, str)
            or not label
            or not isinstance(gate.get("ok"), bool)
        ):
            return None
        labels.append(label)
        children = gate.get("children", [])
        if not isinstance(children, list) or not all(
            isinstance(row, dict)
            and isinstance(row.get("label"), str)
            and bool(row.get("label"))
            and isinstance(row.get("ok"), bool)
            for row in children
        ):
            return None
        if children and gate["ok"] is not all(bool(row["ok"]) for row in children):
            return None
    if len(labels) != len(set(labels)):
        return None
    return gates


def _without_generated_at(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    normalized.pop("generated_at", None)
    return normalized


def _p0_status_coherent(payload: dict[str, Any]) -> bool:
    gates = _strict_gates(payload)
    if gates is None:
        return False
    release = next(
        (row for row in gates if row.get("label") == "P0-1 release publication"),
        None,
    )
    core = [row for row in gates if row is not release]
    all_closed = all(bool(row["ok"]) for row in gates)
    core_closed = bool(core) and all(bool(row["ok"]) for row in core)
    return bool(
        release is not None
        and payload.get("p0_closed") is all_closed
        and payload.get("core_evidence_closed") is core_closed
        and payload.get("release_publication_closed") is bool(release["ok"])
        and payload.get("status") == ("closed" if all_closed else "open")
    )


def _p1_status_coherent(payload: dict[str, Any], *, p0: dict[str, Any]) -> bool:
    inputs_ready = payload.get("p1_inputs_ready")
    release_blocker = payload.get("p0_release_blocker")
    execution_unblocked = payload.get("p1_execution_unblocked")
    if not all(
        isinstance(value, bool)
        for value in (inputs_ready, release_blocker, execution_unblocked)
    ):
        return False
    gates = _strict_gates(payload)
    if gates is None or len(gates) < 2:
        return False
    calculated_inputs_ready = bool(p0.get("core_evidence_closed")) and all(
        bool(row["ok"]) for row in gates[1:]
    )
    return bool(
        gates[0].get("label") == "P0 release publication"
        and gates[0].get("ok") is p0.get("p0_closed")
        and release_blocker is (not bool(p0.get("p0_closed")))
        and payload.get("p0_core_evidence_closed") is p0.get("core_evidence_closed")
        and inputs_ready is calculated_inputs_ready
        and execution_unblocked is (calculated_inputs_ready and not release_blocker)
        and payload.get("status") == ("ready" if execution_unblocked else "blocked")
    )


def _plain_sha256(path: Path) -> str:
    return _sha256_path(path).removeprefix("sha256:")


def _contained_regular_file(path: Path, *, root: Path) -> bool:
    try:
        root = root.resolve(strict=True)
        lexical = path if path.is_absolute() else REPO_ROOT / path
        lexical.relative_to(root)
        current = root
        for part in lexical.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                return False
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
        return resolved.is_file() and not lexical.is_symlink()
    except (OSError, RuntimeError, ValueError):
        return False


def _expected_redacted_bytes(source_path: Path) -> bytes:
    try:
        json_payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        json_payload = None
    if json_payload is not None:
        return (
            json.dumps(
                redact_payload(json_payload),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    return (
        _redact_text(source_path.read_text(encoding="utf-8", errors="replace")) + "\n"
    ).encode("utf-8")


def _canonical_support_source_paths_pass(
    *,
    support_bundle: dict[str, Any],
    generated_paths: dict[str, Path],
) -> bool:
    rows = support_bundle.get("artifact_rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return False
    rows_by_label = {str(row.get("label", "")): row for row in rows}
    expected_sources = {
        **SUPPORT_DEFAULT_SOURCE_PATHS,
        **generated_paths,
    }
    if set(expected_sources) != set(SUPPORT_ALL_LABELS) or set(rows_by_label) != set(
        SUPPORT_ALL_LABELS
    ):
        return False
    try:
        return all(
            rows_by_label[label].get("source_path") == _display_path(expected_path)
            for label, expected_path in expected_sources.items()
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _bundle_transitive_bindings_pass(
    *,
    support_bundle: dict[str, Any],
    generated_paths: dict[str, Path],
) -> bool:
    """Recompute raw, redacted, index, and ZIP bindings independently."""

    try:
        artifact_rows = support_bundle.get("artifact_rows")
        if not isinstance(artifact_rows, list) or not all(
            isinstance(row, dict) for row in artifact_rows
        ):
            return False
        rows = artifact_rows
        labels = [str(row.get("label", "")) for row in rows]
        if len(labels) != len(set(labels)):
            return False
        rows_by_label = {str(row["label"]): row for row in rows}
        if set(generated_paths) != set(GENERATED_INPUT_LABELS):
            return False
        generated_roots = {path.parent.resolve() for path in generated_paths.values()}
        if len(generated_roots) != 1:
            return False
        generated_root = next(iter(generated_roots))
        if not _canonical_support_source_paths_pass(
            support_bundle=support_bundle,
            generated_paths=generated_paths,
        ):
            return False

        for label, expected_path in generated_paths.items():
            row = rows_by_label.get(label)
            if row is None or row.get("available") is not True:
                return False
            source_path = _resolve_path(str(row.get("source_path", "")))
            if source_path.resolve() != expected_path.resolve():
                return False
            if row.get("bytes") != source_path.stat().st_size or row.get(
                "sha256"
            ) != _plain_sha256(source_path):
                return False

        bundle_index_info = support_bundle.get("bundle_index")
        if not isinstance(bundle_index_info, dict):
            return False
        index_path = _resolve_path(str(bundle_index_info.get("path", "")))
        if index_path.is_symlink():
            return False
        bundle_dir = index_path.parent.resolve()
        index = _json_object(index_path)
        if (
            index.get("artifact_rows") != rows
            or index.get("artifact_count") != len(rows)
            or index.get("available_artifact_count") != len(rows)
            or index.get("audit_digest") != support_bundle.get("audit_digest")
            or bundle_index_info.get("sha256") != _plain_sha256(index_path)
        ):
            return False

        expected_members: dict[str, Path] = {}
        for row in rows:
            if row.get("available") is not True:
                return False
            source_path = _resolve_path(str(row.get("source_path", "")))
            redacted_path = _resolve_path(str(row.get("redacted_bundle_path", "")))
            redacted_path.resolve().relative_to(bundle_dir)
            source_root = (
                generated_root
                if row.get("label") in GENERATED_INPUT_LABELS
                else REPO_ROOT
            )
            label = str(row.get("label", ""))
            suffix = source_path.suffix
            if suffix not in {".json", ".md", ".txt", ".toml", ".jsonl"}:
                suffix = ".txt"
            expected_redacted_path = bundle_dir / "redacted" / f"{label}{suffix}"
            if (
                not _contained_regular_file(source_path, root=source_root)
                or not redacted_path.is_file()
                or redacted_path.is_symlink()
                or row.get("redacted_bundle_path")
                != _display_path(expected_redacted_path)
                or redacted_path.resolve() != expected_redacted_path.resolve()
                or row.get("bytes") != source_path.stat().st_size
                or row.get("sha256") != _plain_sha256(source_path)
                or row.get("redacted_sha256") != _plain_sha256(redacted_path)
                or redacted_path.read_bytes() != _expected_redacted_bytes(source_path)
            ):
                return False
            member = redacted_path.resolve().relative_to(bundle_dir).as_posix()
            if member in expected_members:
                return False
            expected_members[member] = redacted_path

        required_sections = support_bundle.get("required_sections")
        if not isinstance(required_sections, dict) or any(
            label not in rows_by_label
            or rows_by_label[label].get("redacted_bundle_path") != path
            for label, path in required_sections.items()
        ):
            return False

        special_paths = {
            "support_bundle_index.json": index_path,
            "audit_digest.json": _resolve_path(
                str(support_bundle.get("audit_digest", {}).get("bundle_path", ""))
            ),
            "license_status.json": _resolve_path(
                str(support_bundle.get("license_status", {}).get("bundle_path", ""))
            ),
            "pm_failure_bundle_coverage.json": _resolve_path(
                str(
                    support_bundle.get("pm_failure_bundle_coverage", {}).get(
                        "bundle_path", ""
                    )
                )
            ),
        }
        for member, path in special_paths.items():
            if (
                member in expected_members
                or not path.is_file()
                or path.resolve().parent != bundle_dir
            ):
                return False
            expected_members[member] = path
        if support_bundle.get("pm_failure_bundle_coverage", {}).get(
            "sha256"
        ) != _plain_sha256(special_paths["pm_failure_bundle_coverage.json"]):
            return False
        if support_bundle.get("license_status", {}).get("sha256") != _plain_sha256(
            special_paths["license_status.json"]
        ):
            return False
        expected_pm_file = deepcopy(support_bundle["pm_failure_bundle_coverage"])
        expected_pm_file.pop("bundle_path", None)
        expected_pm_file.pop("sha256", None)
        expected_audit_file = deepcopy(support_bundle["audit_digest"])
        expected_audit_file.pop("bundle_path", None)
        if (
            _json_object(special_paths["pm_failure_bundle_coverage.json"])
            != expected_pm_file
            or _json_object(special_paths["audit_digest.json"]) != expected_audit_file
            or _json_object(special_paths["license_status.json"])
            != {
                "status": "not_configured",
                "tier": "",
                "expires_at": "",
                "note": "No license status file was provided for this support bundle.",
            }
        ):
            return False

        export = support_bundle.get("export_archive")
        roundtrip = support_bundle.get("archive_roundtrip")
        if not isinstance(export, dict) or not isinstance(roundtrip, dict):
            return False
        archive_path = _resolve_path(str(export.get("path", "")))
        if archive_path.is_symlink():
            return False
        expected_names = sorted(expected_members)
        if (
            export.get("available") is not True
            or export.get("bytes") != archive_path.stat().st_size
            or export.get("sha256") != _plain_sha256(archive_path)
            or export.get("member_count") != len(expected_names)
            or export.get("members") != expected_names
            or roundtrip.get("pass") is not True
            or roundtrip.get("reason") != "PASS"
            or roundtrip.get("artifact_count") != len(rows)
            or roundtrip.get("actual_artifact_count") != len(rows)
            or roundtrip.get("member_count") != len(expected_names)
            or roundtrip.get("missing_members") != []
        ):
            return False
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if names != expected_names or len(names) != len(set(names)):
                return False
            for member, path in expected_members.items():
                if archive.read(member) != path.read_bytes():
                    return False
        return True
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ):
        return False


def _bundle_layout_pass(
    *,
    support_bundle: dict[str, Any],
    output_root: Path,
) -> bool:
    try:
        root = output_root.resolve()
        bundle_dir = (root / "bundle").resolve()
        expected = {
            "bundle_index": bundle_dir / "support_bundle_index.json",
            "audit_digest": bundle_dir / "audit_digest.json",
            "license_status": bundle_dir / "license_status.json",
            "pm_failure_bundle_coverage": bundle_dir
            / "pm_failure_bundle_coverage.json",
        }
        for label, path in expected.items():
            section = support_bundle.get(label)
            if not isinstance(section, dict):
                return False
            key = "path" if label == "bundle_index" else "bundle_path"
            if (
                section.get(key) != _display_path(path)
                or _resolve_path(str(section.get(key, ""))).resolve() != path
            ):
                return False
        export = support_bundle.get("export_archive")
        if (
            not isinstance(export, dict)
            or export.get("path") != _display_path(root / "support-bundle-export.zip")
            or _resolve_path(str(export.get("path", ""))).resolve()
            != (root / "support-bundle-export.zip").resolve()
        ):
            return False
        for row in support_bundle.get("artifact_rows", []):
            if not isinstance(row, dict) or row.get("available") is not True:
                return False
            redacted = _resolve_path(str(row.get("redacted_bundle_path", "")))
            redacted.resolve().relative_to((bundle_dir / "redacted").resolve())
        return True
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def _pm_coverage_semantics_pass(support_bundle: dict[str, Any]) -> bool:
    rows = support_bundle.get("artifact_rows")
    optional_sections = support_bundle.get("optional_sections")
    actual = support_bundle.get("pm_failure_bundle_coverage")
    if (
        not isinstance(rows, list)
        or not isinstance(optional_sections, dict)
        or not isinstance(actual, dict)
    ):
        return False
    rows_by_label = {
        str(row.get("label", "")): row for row in rows if isinstance(row, dict)
    }

    def source(label: str) -> Path:
        row = rows_by_label.get(label)
        if not isinstance(row, dict):
            raise CurrentSupportBundleError(f"support_row_missing:{label}")
        return Path(str(row.get("source_path", "")))

    try:
        with tempfile.TemporaryDirectory(prefix="support-pm-replay-") as temp:
            expected = _build_pm_failure_bundle_coverage(
                bundle_dir=Path(temp),
                optional_sections=optional_sections,
                pm_release_blocker_action_register=source(
                    "pm_release_blocker_action_register"
                ),
                pm_release_blocker_closure_board=source(
                    "pm_release_blocker_closure_board"
                ),
                pm_release_gate_completion_audit=source(
                    "pm_release_gate_completion_audit"
                ),
                pm_release_gate_reviewer_handoff=source(
                    "pm_release_gate_reviewer_handoff"
                ),
                pm_owner_evidence_request_packet=source(
                    "pm_owner_evidence_request_packet"
                ),
            )
        normalized_actual = deepcopy(actual)
        normalized_expected = deepcopy(expected)
        for payload in (normalized_actual, normalized_expected):
            payload.pop("generated_at", None)
            payload.pop("bundle_path", None)
            payload.pop("sha256", None)
        return normalized_actual == normalized_expected
    except (CurrentSupportBundleError, OSError, TypeError, ValueError):
        return False


def _support_manifest_semantics_pass(
    *,
    support_bundle: dict[str, Any],
    generated_paths: dict[str, Path],
) -> bool:
    try:
        if set(support_bundle) != {
            "archive_roundtrip",
            "artifact_rows",
            "audit_digest",
            "blockers",
            "bundle_index",
            "bundle_policy",
            "checks",
            "contract_pass",
            "export_archive",
            "generated_at",
            "license_status",
            "optional_sections",
            "pm_failure_bundle_coverage",
            "reason_code",
            "required_sections",
            "schema_version",
            "summary_line",
        } or not _utc_timestamp(support_bundle.get("generated_at")):
            return False
        if not _canonical_support_source_paths_pass(
            support_bundle=support_bundle,
            generated_paths=generated_paths,
        ):
            return False
        rows = support_bundle.get("artifact_rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            return False
        expected_labels = SUPPORT_ALL_LABELS
        if tuple(str(row.get("label", "")) for row in rows) != expected_labels:
            return False
        required = support_bundle.get("required_sections")
        optional = support_bundle.get("optional_sections")
        if (
            not isinstance(required, dict)
            or not isinstance(optional, dict)
            or set(required) != set(SUPPORT_REQUIRED_LABELS)
            or set(optional) != set(SUPPORT_OPTIONAL_LABELS)
        ):
            return False
        rows_by_label = {str(row["label"]): row for row in rows}
        bundle_index = support_bundle.get("bundle_index")
        if not isinstance(bundle_index, dict):
            return False
        bundle_dir = _resolve_path(str(bundle_index.get("path", ""))).resolve().parent
        expected_sources = {
            **SUPPORT_DEFAULT_SOURCE_PATHS,
            **generated_paths,
        }
        for label, expected_source in expected_sources.items():
            suffix = Path(expected_source).suffix
            if suffix not in {".json", ".md", ".txt", ".toml", ".jsonl"}:
                suffix = ".txt"
            if rows_by_label[label].get("redacted_bundle_path") != _display_path(
                bundle_dir / "redacted" / f"{label}{suffix}"
            ):
                return False
        for labels, section in (
            (SUPPORT_REQUIRED_LABELS, required),
            (SUPPORT_OPTIONAL_LABELS, optional),
        ):
            for label in labels:
                row = rows_by_label[label]
                if set(row) != {
                    "label",
                    "source_path",
                    "available",
                    "bytes",
                    "sha256",
                    "redacted_bundle_path",
                    "redacted_sha256",
                }:
                    return False
                if (
                    not isinstance(row.get("available"), bool)
                    or not isinstance(row.get("bytes"), int)
                    or isinstance(row.get("bytes"), bool)
                    or row["bytes"] < 0
                    or not all(
                        isinstance(row.get(key), str)
                        for key in (
                            "source_path",
                            "sha256",
                            "redacted_bundle_path",
                            "redacted_sha256",
                        )
                    )
                ):
                    return False
                expected_path = (
                    row["redacted_bundle_path"] if row["available"] else "missing"
                )
                if section[label] != expected_path:
                    return False

        audit = support_bundle.get("audit_digest")
        archive = support_bundle.get("archive_roundtrip")
        pm = support_bundle.get("pm_failure_bundle_coverage")
        if not all(
            isinstance(value, dict) for value in (bundle_index, audit, archive, pm)
        ):
            return False
        artifact_count = len(rows)
        available_count = sum(row["available"] is True for row in rows)
        missing_required = [
            label
            for label in SUPPORT_REQUIRED_LABELS
            if not rows_by_label[label]["available"]
        ]
        redaction_pass = _redaction_self_test().get("pass") is True
        audit_pass = bool(audit.get("sha256"))
        bundle_roundtrip_pass = (
            bundle_index.get("artifact_count") == artifact_count
            and bundle_index.get("available_artifact_count") == available_count
        )
        archive_roundtrip_pass = archive.get("pass") is True
        pm_coverage_pass = (
            _pm_coverage_semantics_pass(support_bundle)
            and pm.get("coverage_pass") is True
        )
        checks = {
            "redaction_self_test_pass": redaction_pass,
            "audit_event_digest_pass": audit_pass,
            "bundle_roundtrip_test_pass": bundle_roundtrip_pass,
            "archive_roundtrip_test_pass": archive_roundtrip_pass,
            "missing_required_count": len(missing_required),
            "pm_failure_bundle_coverage_pass": pm_coverage_pass,
        }
        blockers = [
            *(f"required_artifact_missing:{label}" for label in missing_required),
            *([] if redaction_pass else ["redaction_self_test_failed"]),
            *([] if audit_pass else ["audit_event_digest_missing"]),
            *([] if bundle_roundtrip_pass else ["bundle_roundtrip_test_failed"]),
            *(
                []
                if support_bundle.get("export_archive", {}).get("available") is True
                else ["archive_export_failed"]
            ),
            *([] if archive_roundtrip_pass else ["archive_roundtrip_test_failed"]),
            *([] if pm_coverage_pass else ["pm_failure_bundle_coverage_incomplete"]),
        ]
        contract_pass = not blockers
        return bool(
            support_bundle.get("schema_version") == SUPPORT_BUNDLE_SCHEMA_VERSION
            and support_bundle.get("bundle_policy") == SUPPORT_BUNDLE_POLICY
            and support_bundle.get("checks") == checks
            and support_bundle.get("blockers") == blockers
            and support_bundle.get("contract_pass") is contract_pass
            and support_bundle.get("reason_code")
            == ("PASS" if contract_pass else "ERR_SUPPORT_BUNDLE_EVIDENCE_PENDING")
            and support_bundle.get("summary_line")
            == (
                f"Support bundle: {'PASS' if contract_pass else 'BLOCKED'} | "
                f"artifacts={available_count}/{artifact_count} | "
                f"redaction={redaction_pass} | "
                f"roundtrip={bundle_roundtrip_pass} | "
                f"archive={archive_roundtrip_pass}"
            )
        )
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def _client_report_semantics_pass(
    *,
    client_input: dict[str, Any],
    fixture: Path,
) -> bool:
    try:
        declared_fixture = Path(str(client_input.get("input_path", "")))
        if _resolve_path(str(declared_fixture)).resolve() != fixture.resolve():
            return False
        expected = validate_client_input_package(
            input_path=declared_fixture,
            source_kind="repository_reference_fixture",
        )
        actual_stable = deepcopy(client_input)
        expected_stable = deepcopy(expected)
        for payload in (actual_stable, expected_stable):
            payload.pop("generated_at", None)
            payload.pop("artifact_hash", None)
        return bool(
            client_input.get("claim_boundary") == CLIENT_CLAIM_BOUNDARY
            and actual_stable == expected_stable
        )
    except (OSError, TypeError, ValueError):
        return False


def _project_ops_producer_semantics_pass(
    *,
    project_ops: dict[str, Any],
    snapshot_path: Path,
) -> bool:
    def normalize(payload: dict[str, Any], *, expected_path: Path) -> dict[str, Any]:
        normalized = deepcopy(payload)
        normalized.pop("generated_at", None)
        artifacts = normalized.get("artifacts")
        paths = normalized.get("paths")
        if not isinstance(artifacts, dict) or not isinstance(paths, dict):
            raise CurrentSupportBundleError("project_ops_output_sections_invalid")
        if (
            artifacts.get("project_ops_service_snapshot_json")
            != _display_path(expected_path)
            or paths.get("snapshot_json") != _display_path(expected_path)
            or _resolve_path(
                str(artifacts.get("project_ops_service_snapshot_json", ""))
            ).resolve()
            != expected_path.resolve()
            or _resolve_path(str(paths.get("snapshot_json", ""))).resolve()
            != expected_path.resolve()
        ):
            raise CurrentSupportBundleError("project_ops_output_binding_invalid")
        artifacts["project_ops_service_snapshot_json"] = "<snapshot>"
        paths["snapshot_json"] = "<snapshot>"
        return normalized

    try:
        with tempfile.TemporaryDirectory(prefix="project-ops-replay-") as temp:
            expected_path = Path(temp) / "project-ops-service-snapshot.json"
            expected = write_project_ops_snapshot(expected_path)
            return normalize(
                project_ops,
                expected_path=snapshot_path,
            ) == normalize(expected, expected_path=expected_path)
    except (
        CurrentSupportBundleError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False


def _readiness_producer_semantics_pass(
    *,
    p0: dict[str, Any],
    p1: dict[str, Any],
    p0_path: Path,
) -> bool:
    try:
        expected_p0 = build_p0_status()
        expected_p1 = build_p1_status(p0_status=Path(_display_path(p0_path)))
        return bool(
            _without_generated_at(p0) == _without_generated_at(expected_p0)
            and _without_generated_at(p1) == _without_generated_at(expected_p1)
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _reason_code(blockers: list[str]) -> str:
    return "PASS" if not blockers else "ERR_CURRENT_SUPPORT_BUNDLE_INCOMPLETE"


def _summary_line(
    *,
    blockers: list[str],
    available_count: int,
    artifact_count: int,
    p0: dict[str, Any],
    p1: dict[str, Any],
    project_ops: dict[str, Any],
) -> str:
    return (
        f"Current support bundle: {'PASS' if not blockers else 'BLOCKED'} | "
        f"artifacts={available_count}/{artifact_count} | "
        f"p0={p0.get('status')} | p1={p1.get('status')} | "
        f"project_ops={project_ops.get('reason_code')}"
    )


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
    generated_paths: dict[str, Path],
    output_root: Path,
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
        "p0_status_current_source_and_coherent": (
            p0.get("source_commit_sha") == identity.get("commit_sha")
            and _p0_status_coherent(p0)
        ),
        "p1_status_explicit": (
            p1.get("status") in {"ready", "blocked"}
            and isinstance(p1.get("p1_inputs_ready"), bool)
            and isinstance(p1.get("p1_execution_unblocked"), bool)
            and isinstance(p1.get("p0_release_blocker"), bool)
        ),
        "p1_status_current_source_and_coherent": (
            p1.get("source_commit_sha") == identity.get("commit_sha")
            and _p1_status_coherent(p1, p0=p0)
        ),
        "p0_p1_producer_semantics_replayed": _readiness_producer_semantics_pass(
            p0=p0,
            p1=p1,
            p0_path=generated_paths["p0_status"],
        ),
        "project_ops_status_explicit": (
            isinstance(project_ops.get("contract_pass"), bool)
            and project_ops.get("reason_code") in {"PASS", "CHECK", "ERR_INPUT"}
        ),
        "project_ops_status_coherent": (
            isinstance(project_ops.get("contract_pass"), bool)
            and (project_ops.get("reason_code") == "PASS")
            is project_ops.get("contract_pass")
            and _project_ops_producer_semantics_pass(
                project_ops=project_ops,
                snapshot_path=generated_paths["project_ops_snapshot"],
            )
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
        "client_reference_fixture_artifact_hash_valid": (
            client_input.get("source_commit_sha") == identity.get("commit_sha")
            and client_input.get("artifact_hash") == _artifact_hash(client_input)
        ),
        "client_reference_fixture_producer_semantics_replayed": (
            _client_report_semantics_pass(
                client_input=client_input,
                fixture=fixture,
            )
        ),
        "generated_missing_four_present": all(
            required_sections.get(label) not in {None, "", "missing"}
            for label in GENERATED_INPUT_LABELS
        ),
        "support_bundle_contract_pass": support_bundle.get("contract_pass") is True,
        "support_bundle_missing_required_zero": checks.get("missing_required_count")
        == 0,
        "support_bundle_all_artifacts_available": (
            isinstance(bundle_index.get("artifact_count"), int)
            and bundle_index.get("artifact_count", 0) > 0
            and bundle_index.get("available_artifact_count")
            == bundle_index.get("artifact_count")
        ),
        "support_bundle_redaction_pass": checks.get("redaction_self_test_pass") is True,
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
        "support_bundle_transitive_bindings_pass": (
            _bundle_transitive_bindings_pass(
                support_bundle=support_bundle,
                generated_paths=generated_paths,
            )
        ),
        "support_bundle_layout_pass": _bundle_layout_pass(
            support_bundle=support_bundle,
            output_root=output_root,
        ),
        "support_bundle_producer_semantics_replayed": (
            _support_manifest_semantics_pass(
                support_bundle=support_bundle,
                generated_paths=generated_paths,
            )
        ),
    }


def _recorded_artifact_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    generated = payload.get("generated_inputs")
    support = payload.get("support_bundle")
    if not isinstance(generated, dict) or not isinstance(support, dict):
        raise CurrentSupportBundleError("receipt_artifact_sections_invalid")
    if set(generated) != set(GENERATED_INPUT_LABELS):
        raise CurrentSupportBundleError("receipt_generated_input_labels_invalid")
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


def _receipt_layout_pass(
    *,
    payload: dict[str, Any],
    support_bundle: dict[str, Any],
    output_root: Path,
) -> bool:
    try:
        generated = payload.get("generated_inputs")
        support = payload.get("support_bundle")
        if not isinstance(generated, dict) or not isinstance(support, dict):
            return False
        if set(support) != {
            "manifest",
            "bundle_index",
            "pm_failure_bundle_coverage",
            "archive",
            "artifact_count",
            "available_artifact_count",
            "missing_required_count",
        }:
            return False
        root = output_root.resolve()
        expected_generated = {
            "p0_status": root / "generated" / "p0-status.json",
            "p1_status": root / "generated" / "p1-readiness-status.json",
            "project_ops_snapshot": root
            / "generated"
            / "project-ops-service-snapshot.json",
            "client_input_validation_report": root
            / "generated"
            / "client-input-validation-report.json",
        }
        if any(
            generated[label].get("path") != _display_path(expected_path)
            or _resolve_path(str(generated[label].get("path", ""))).resolve()
            != expected_path.resolve()
            for label, expected_path in expected_generated.items()
        ):
            return False

        manifest_path = root / "support-bundle-manifest.json"
        manifest_links = {
            "manifest": manifest_path,
            "bundle_index": _resolve_path(
                str(support_bundle.get("bundle_index", {}).get("path", ""))
            ),
            "pm_failure_bundle_coverage": _resolve_path(
                str(
                    support_bundle.get("pm_failure_bundle_coverage", {}).get(
                        "bundle_path", ""
                    )
                )
            ),
            "archive": _resolve_path(
                str(support_bundle.get("export_archive", {}).get("path", ""))
            ),
        }
        return all(
            isinstance(support.get(label), dict)
            and support[label].get("path") == _display_path(expected_path)
            and _resolve_path(str(support[label].get("path", ""))).resolve()
            == expected_path.resolve()
            for label, expected_path in manifest_links.items()
        )
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def _validate_expected_sha(expected_source_sha: str, actual_sha: str) -> str:
    expected = expected_source_sha or actual_sha
    if SHA_PATTERN.fullmatch(expected) is None:
        raise CurrentSupportBundleError("expected_source_sha_invalid")
    return expected


def _rebase_value(value: Any, *, old_root: Path, new_root: Path | str) -> Any:
    old_texts = tuple(
        sorted(
            {str(old_root), _display_path(old_root)},
            key=len,
            reverse=True,
        )
    )
    new_text = str(new_root)
    if isinstance(value, dict):
        return {
            str(
                _rebase_value(key, old_root=old_root, new_root=new_root)
            ): _rebase_value(
                item,
                old_root=old_root,
                new_root=new_root,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _rebase_value(item, old_root=old_root, new_root=new_root) for item in value
        ]
    if isinstance(value, str):
        for old_text in old_texts:
            if value == old_text or value.startswith(old_text + os.sep):
                return new_text + value[len(old_text) :]
    return value


def _physical_path_for_logical(
    path_text: str,
    *,
    staging_root: Path,
    final_root: Path,
) -> Path:
    logical = _resolve_path(path_text).resolve()
    try:
        relative = logical.relative_to(final_root)
    except ValueError:
        return logical
    return staging_root / relative


def _logical_file_row(*, physical_path: Path, logical_path: Path) -> dict[str, Any]:
    if not physical_path.is_file() or physical_path.is_symlink():
        raise CurrentSupportBundleError(
            f"artifact_missing_or_symlink:{_display_path(physical_path)}"
        )
    return {
        "path": _display_path(logical_path),
        "bytes": physical_path.stat().st_size,
        "sha256": _sha256_path(physical_path),
    }


def _rebase_staged_bundle(
    *,
    staging_root: Path,
    final_root: Path,
    support_bundle: dict[str, Any],
    generated_paths: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, Path]]:
    logical_final_root = _display_path(final_root)
    logical_generated = {
        label: final_root / path.relative_to(staging_root)
        for label, path in generated_paths.items()
    }

    for path in sorted(staging_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".json",
            ".jsonl",
            ".md",
            ".txt",
            ".toml",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        rebased = text
        for old_text in {str(staging_root), _display_path(staging_root)}:
            rebased = rebased.replace(old_text, logical_final_root)
        if rebased != text:
            path.write_text(rebased, encoding="utf-8")

    rebased_bundle = _rebase_value(
        support_bundle,
        old_root=staging_root,
        new_root=logical_final_root,
    )
    rows = rebased_bundle.get("artifact_rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise CurrentSupportBundleError("support_artifact_rows_invalid")
    for row in rows:
        source_path = _physical_path_for_logical(
            str(row.get("source_path", "")),
            staging_root=staging_root,
            final_root=final_root,
        )
        redacted_path = _physical_path_for_logical(
            str(row.get("redacted_bundle_path", "")),
            staging_root=staging_root,
            final_root=final_root,
        )
        if not source_path.is_file() or not redacted_path.is_file():
            raise CurrentSupportBundleError("rebased_support_artifact_missing")
        row["bytes"] = source_path.stat().st_size
        row["sha256"] = _plain_sha256(source_path)
        row["redacted_sha256"] = _plain_sha256(redacted_path)

    index_logical = _resolve_path(str(rebased_bundle["bundle_index"]["path"]))
    index_physical = _physical_path_for_logical(
        str(index_logical),
        staging_root=staging_root,
        final_root=final_root,
    )
    index = _json_object(index_physical)
    index = _rebase_value(
        index,
        old_root=staging_root,
        new_root=logical_final_root,
    )
    index["artifact_rows"] = rows
    index["artifact_count"] = len(rows)
    index["available_artifact_count"] = sum(
        row.get("available") is True for row in rows
    )
    index["audit_digest"] = rebased_bundle["audit_digest"]
    _write_json(index_physical, index)
    rebased_bundle["bundle_index"]["sha256"] = _plain_sha256(index_physical)
    rebased_bundle["bundle_index"]["artifact_count"] = len(rows)
    rebased_bundle["bundle_index"]["available_artifact_count"] = sum(
        row.get("available") is True for row in rows
    )

    pm_physical = _physical_path_for_logical(
        str(rebased_bundle["pm_failure_bundle_coverage"]["bundle_path"]),
        staging_root=staging_root,
        final_root=final_root,
    )
    rebased_bundle["pm_failure_bundle_coverage"]["sha256"] = _plain_sha256(pm_physical)
    license_physical = _physical_path_for_logical(
        str(rebased_bundle["license_status"]["bundle_path"]),
        staging_root=staging_root,
        final_root=final_root,
    )
    rebased_bundle["license_status"]["sha256"] = _plain_sha256(license_physical)

    bundle_dir = staging_root / "bundle"
    archive_physical = staging_root / "support-bundle-export.zip"
    archive_sources = [
        *[
            _physical_path_for_logical(
                str(row["redacted_bundle_path"]),
                staging_root=staging_root,
                final_root=final_root,
            )
            for row in rows
            if row.get("available") is True
        ],
        staging_root / "bundle" / "audit_digest.json",
        license_physical,
        index_physical,
        pm_physical,
    ]
    physical_export = _build_export_archive(
        bundle_dir=bundle_dir,
        archive_out=archive_physical,
        source_paths=archive_sources,
    )
    rebased_bundle["export_archive"] = _rebase_value(
        physical_export,
        old_root=staging_root,
        new_root=logical_final_root,
    )
    rebased_bundle["archive_roundtrip"] = _archive_roundtrip_self_test(physical_export)
    return rebased_bundle, logical_generated


def _atomic_publish(staging_root: Path, final_root: Path) -> None:
    if final_root.exists() or final_root.is_symlink():
        raise CurrentSupportBundleError(
            f"output_root_already_exists:{_display_path(final_root)}"
        )
    staging_root.rename(final_root)


def _cleanup_failed_build(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    if path.exists() or path.is_symlink():
        raise CurrentSupportBundleError(
            f"failed_build_cleanup_incomplete:{_display_path(path)}"
        )


def _build_staged_current_support_bundle(
    *,
    output_root: Path,
    final_root: Path,
    client_fixture: Path,
    identity: dict[str, Any],
    expected: str,
    fixture_head_files: list[str],
) -> dict[str, Any]:
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
    p1 = build_p1_status(p0_status=Path(_display_path(p0_path)))
    _write_json(p1_path, p1)
    project_ops = write_project_ops_snapshot(Path(_display_path(project_ops_path)))
    client_input = validate_client_input_package(
        input_path=client_fixture,
        source_kind="repository_reference_fixture",
    )
    _write_json(client_input_path, client_input)
    support_bundle = build_support_bundle(
        bundle_dir=Path(_display_path(bundle_dir)),
        archive_out=Path(_display_path(archive_path)),
        p0_status=Path(_display_path(p0_path)),
        p1_status=Path(_display_path(p1_path)),
        project_ops_snapshot=Path(_display_path(project_ops_path)),
        client_input_validation_report=Path(_display_path(client_input_path)),
    )
    _write_json(manifest_path, support_bundle)

    generated_paths = {
        "p0_status": p0_path,
        "p1_status": p1_path,
        "project_ops_snapshot": project_ops_path,
        "client_input_validation_report": client_input_path,
    }
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
        generated_paths=generated_paths,
        output_root=output_root,
    )
    blockers = [label for label, passed in checks.items() if not passed]
    support_bundle, logical_generated = _rebase_staged_bundle(
        staging_root=output_root,
        final_root=final_root,
        support_bundle=support_bundle,
        generated_paths=generated_paths,
    )
    p0 = _rebase_value(
        p0,
        old_root=output_root,
        new_root=_display_path(final_root),
    )
    p1 = _rebase_value(
        p1,
        old_root=output_root,
        new_root=_display_path(final_root),
    )
    project_ops = _rebase_value(
        project_ops,
        old_root=output_root,
        new_root=_display_path(final_root),
    )
    client_input = _rebase_value(
        client_input,
        old_root=output_root,
        new_root=_display_path(final_root),
    )
    _write_json(manifest_path, support_bundle)

    bundle_index_logical = _resolve_path(str(support_bundle["bundle_index"]["path"]))
    pm_failure_logical = _resolve_path(
        str(support_bundle["pm_failure_bundle_coverage"]["bundle_path"])
    )
    archive_logical = _resolve_path(str(support_bundle["export_archive"]["path"]))
    bundle_index_path = _physical_path_for_logical(
        str(bundle_index_logical),
        staging_root=output_root,
        final_root=final_root,
    )
    pm_failure_path = _physical_path_for_logical(
        str(pm_failure_logical),
        staging_root=output_root,
        final_root=final_root,
    )
    artifact_count = int(support_bundle["bundle_index"]["artifact_count"])
    available_count = int(support_bundle["bundle_index"]["available_artifact_count"])
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
        "reason_code": _reason_code(blockers),
        "summary_line": _summary_line(
            blockers=blockers,
            available_count=available_count,
            artifact_count=artifact_count,
            p0=p0,
            p1=p1,
            project_ops=project_ops,
        ),
        "output_root": _display_path(final_root),
        "generated_inputs": {
            label: _logical_file_row(
                physical_path=generated_paths[label],
                logical_path=logical_generated[label],
            )
            for label in GENERATED_INPUT_LABELS
        },
        "support_bundle": {
            "manifest": _logical_file_row(
                physical_path=manifest_path,
                logical_path=final_root / "support-bundle-manifest.json",
            ),
            "bundle_index": _logical_file_row(
                physical_path=bundle_index_path,
                logical_path=bundle_index_logical,
            ),
            "pm_failure_bundle_coverage": _logical_file_row(
                physical_path=pm_failure_path,
                logical_path=pm_failure_logical,
            ),
            "archive": _logical_file_row(
                physical_path=archive_path,
                logical_path=archive_logical,
            ),
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
        "claim_boundary": deepcopy(CLAIM_BOUNDARY),
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    _write_json(receipt_path, payload)
    return payload


def build_current_support_bundle(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    client_fixture: Path = DEFAULT_CLIENT_FIXTURE,
    expected_source_sha: str = "",
) -> dict[str, Any]:
    if Path.cwd().resolve() != REPO_ROOT.resolve():
        raise CurrentSupportBundleError("repository_root_working_directory_required")
    _reject_lexical_symlink_components(output_root)
    if output_root.is_symlink():
        raise CurrentSupportBundleError("output_root_symlink_forbidden")
    final_root = output_root.resolve()
    if final_root.exists() or final_root.is_symlink():
        raise CurrentSupportBundleError(
            f"output_root_already_exists:{_display_path(final_root)}"
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

    final_root.parent.mkdir(parents=True, exist_ok=True)
    if final_root.parent.is_symlink():
        raise CurrentSupportBundleError("output_root_parent_symlink_forbidden")
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{final_root.name}.tmp-",
            dir=final_root.parent,
        )
    )
    published = False
    try:
        _build_staged_current_support_bundle(
            output_root=staging_root,
            final_root=final_root,
            client_fixture=client_fixture,
            identity=identity,
            expected=expected,
            fixture_head_files=fixture_head_files,
        )
        _atomic_publish(staging_root, final_root)
        published = True
        return verify_current_support_bundle(
            receipt_path=final_root / RECEIPT_NAME,
            expected_source_sha=expected,
        )
    except Exception:
        cleanup_root = final_root if published else staging_root
        _cleanup_failed_build(cleanup_root)
        raise


def verify_current_support_bundle(
    *,
    receipt_path: Path,
    expected_source_sha: str = "",
) -> dict[str, Any]:
    if Path.cwd().resolve() != REPO_ROOT.resolve():
        raise CurrentSupportBundleError("repository_root_working_directory_required")
    payload = _json_object(receipt_path)
    if not _receipt_shape_pass(payload):
        raise CurrentSupportBundleError("receipt_schema_invalid")
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

    if payload.get("output_root") != _display_path(receipt_path.parent):
        raise CurrentSupportBundleError("receipt_output_root_not_canonical")
    output_root = _resolve_path(str(payload.get("output_root", ""))).resolve()
    if (
        receipt_path.is_symlink()
        or not _contained_regular_file(receipt_path, root=output_root)
        or receipt_path.resolve().parent != output_root
    ):
        raise CurrentSupportBundleError("receipt_output_root_invalid")
    try:
        receipt_path.resolve().relative_to(output_root)
    except ValueError as exc:
        raise CurrentSupportBundleError("receipt_outside_output_root") from exc
    for row in _recorded_artifact_rows(payload):
        lexical_path = _resolve_path(str(row.get("path", "")))
        path = lexical_path.resolve()
        try:
            path.relative_to(output_root)
        except ValueError as exc:
            raise CurrentSupportBundleError("artifact_outside_output_root") from exc
        if (
            not _contained_regular_file(lexical_path, root=output_root)
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
    generated_paths = {
        label: _resolve_path(str(generated[label]["path"]))
        for label in GENERATED_INPUT_LABELS
    }
    p0 = _json_object(_resolve_path(generated["p0_status"]["path"]))
    p1 = _json_object(_resolve_path(generated["p1_status"]["path"]))
    project_ops = _json_object(_resolve_path(generated["project_ops_snapshot"]["path"]))
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
        generated_paths=generated_paths,
        output_root=output_root,
    )
    blockers = [label for label, passed in checks.items() if not passed]
    readiness = _readiness_snapshot(
        p0=p0,
        p1=p1,
        project_ops=project_ops,
        client_input=client_input,
    )
    bundle_index = support_bundle.get("bundle_index", {})
    artifact_count = bundle_index.get("artifact_count")
    available_count = bundle_index.get("available_artifact_count")
    reason_code = _reason_code(blockers)
    summary_line = _summary_line(
        blockers=blockers,
        available_count=available_count,
        artifact_count=artifact_count,
        p0=p0,
        p1=p1,
        project_ops=project_ops,
    )
    if (
        payload.get("checks") != checks
        or payload.get("blockers") != blockers
        or payload.get("contract_pass") is not (not blockers)
        or payload.get("reason_code") != reason_code
        or payload.get("summary_line") != summary_line
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
        or payload.get("readiness_status_preserved") != readiness
        or not _receipt_layout_pass(
            payload=payload,
            support_bundle=support_bundle,
            output_root=output_root,
        )
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
    build.add_argument("--client-fixture", type=Path, default=DEFAULT_CLIENT_FIXTURE)
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
    except (
        CurrentSupportBundleError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"current support bundle failed: {exc}", file=sys.stderr)
        return 2
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
