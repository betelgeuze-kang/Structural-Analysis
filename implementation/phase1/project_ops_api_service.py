#!/usr/bin/env python3
"""Local JSON API service for project ops, portfolio, and release governance surfaces."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

try:
    from implementation.phase1.project_registry_service import build_project_registry_index
except ImportError:  # pragma: no cover
    from project_registry_service import build_project_registry_index  # type: ignore


DEFAULT_RELEASE_ROOT = Path("implementation/phase1/release")
DEFAULT_PROJECT_OPS_SNAPSHOT_OUT = DEFAULT_RELEASE_ROOT / "project_ops_service_snapshot.json"
DEFAULT_SNAPSHOT_MANIFEST_GLOB = "phase3_nightly_hardening_*/snapshot_manifest.json"
DEFAULT_RUNTIME_SUBMISSION_JSON = (
    DEFAULT_RELEASE_ROOT / "authoring" / "portfolio" / "native_authoring_runtime_submission_lane.json"
)
DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON = (
    DEFAULT_RELEASE_ROOT / "authoring" / "portfolio" / "native_authoring_runtime_writeback_depth_report.json"
)
DEFAULT_MULTI_PROJECT_RUNTIME_WRITEBACK_JSON = (
    DEFAULT_RELEASE_ROOT / "authoring" / "portfolio" / "native_authoring_multi_project_runtime_writeback_report.json"
)
DEFAULT_SOLVER_FAMILY_BREADTH_JSON = (
    DEFAULT_RELEASE_ROOT / "authoring" / "portfolio" / "native_authoring_solver_family_breadth_report.json"
)
DEFAULT_LOCAL_RUNTIME_SCENARIO_DEPTH_JSON = (
    DEFAULT_RELEASE_ROOT / "authoring" / "portfolio" / "native_authoring_local_runtime_scenario_depth_report.json"
)
PROJECT_OPS_JWT_HMAC_SECRET_ENV = "PROJECT_OPS_JWT_HMAC_SECRET"
SERVICE_ENDPOINT_PATHS = (
    "/health",
    "/summary",
    "/projects",
    "/projects/{project_id}",
    "/families",
    "/families/{family_id}",
    "/portfolios",
    "/portfolios/{portfolio_name}",
    "/submissions",
    "/submissions/{family_id}",
    "/audit/events",
    "/audit/digest",
    "/ops/policy",
    "/license",
    "/version",
    "/update-channel",
)

REASONS = {
    "PASS": "project ops service snapshot generated",
    "CHECK": "project ops service snapshot generated with missing or non-green dependencies",
    "ERR_INPUT": "project ops service inputs were missing",
}


@dataclass(frozen=True)
class ProjectOpsServiceConfig:
    release_root: Path = DEFAULT_RELEASE_ROOT
    portfolio_json_path: Path | None = None
    registry_index_json_path: Path | None = None
    portfolio_batch_json_path: Path | None = None
    runtime_submission_json_path: Path | None = None
    runtime_writeback_depth_json_path: Path | None = None
    multi_project_runtime_writeback_json_path: Path | None = None
    solver_family_breadth_json_path: Path | None = None
    local_runtime_scenario_depth_json_path: Path | None = None
    release_registry_json_path: Path | None = None
    committee_summary_json_path: Path | None = None
    release_gap_report_json_path: Path | None = None
    snapshot_manifest_glob: str = DEFAULT_SNAPSHOT_MANIFEST_GLOB
    project_registry_paths: tuple[str, ...] = ()
    project_registry_dirs: tuple[str, ...] = ()
    auth_required: bool = True
    jwt_hmac_secret: str = ""
    allowed_tenants: tuple[str, ...] = ()
    audit_log_path: Path | None = None
    audit_digest_path: Path | None = None
    audit_digest_enabled: bool = True
    audit_retention_days: int = 365
    audit_export_max_events: int = 1000
    request_metadata_byte_limit: int = 8192
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 120
    backup_policy: str = "operator_managed_snapshot_required"
    tenant_delete_policy: str = "manual_approval_required"
    telemetry_enabled: bool = False
    license_status_path: Path | None = None
    service_version: str = "project-ops-api-service.v1"
    update_channel: str = "stable"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "n", "off"}:
            return False
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
    return bool(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        token = _text(value)
        if token:
            return token
    return ""


def _first_int(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return _coerce_int(value, default=default)
    return default


def _first_bool(*values: Any, default: bool = False) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return _coerce_bool(value)
    return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _path_text(path: Path | None) -> str:
    return str(path) if path is not None else ""


def _dedupe_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _text(value)
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _iso_max(values: list[str]) -> str:
    normalized = [_text(value) for value in values if _text(value)]
    return max(normalized, default="")


def _family_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (_safe_label(_text(row.get("portfolio_name"))), _text(row.get("family_id")))


def _safe_label(value: str) -> str:
    return _text(value) or "unassigned"


def _coalesce_batch_count(summary: dict[str, Any], key: str, fallback: int) -> int:
    if key in summary:
        return _coerce_int(summary.get(key, fallback))
    return fallback


def _decode_query(params: dict[str, list[str]], name: str) -> str:
    values = params.get(name, [])
    return _text(values[0] if values else "")


def _decode_bool_query(params: dict[str, list[str]], name: str) -> bool | None:
    value = _decode_query(params, name)
    if not value:
        return None
    return _coerce_bool(value)


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _base64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def create_project_ops_test_token(
    *,
    secret: str,
    tenant_id: str = "tenant-a",
    actor_id: str = "engineer-1",
    roles: list[str] | tuple[str, ...] = ("viewer",),
    expires_in_seconds: int = 3600,
) -> str:
    """Create a compact HS256 JWT fixture for local tests and examples."""

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": actor_id,
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "roles": list(roles),
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
    }
    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def _resolve_project_ops_hmac_secret(*, explicit_secret: str, auth_required: bool) -> str:
    secret = _text(explicit_secret) or _text(os.environ.get(PROJECT_OPS_JWT_HMAC_SECRET_ENV))
    if secret or not auth_required:
        return secret
    raise ValueError(
        f"jwt_hmac_secret is required when auth_required=True; pass --jwt-hmac-secret "
        f"or set {PROJECT_OPS_JWT_HMAC_SECRET_ENV}."
    )


def _verify_project_ops_token(token: str, *, secret: str) -> tuple[dict[str, Any] | None, str]:
    parts = token.split(".")
    if len(parts) != 3:
        return None, "malformed_token"
    try:
        header = json.loads(_base64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(_base64url_decode(parts[1]).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "malformed_token"
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None, "malformed_token"
    if header.get("alg") != "HS256":
        return None, "unsupported_token_alg"
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = _base64url_decode(parts[2])
    except ValueError:
        return None, "malformed_token"
    if not hmac.compare_digest(expected, actual):
        return None, "invalid_token_signature"
    exp = payload.get("exp")
    if exp is not None and int(exp) < int(time.time()):
        return None, "token_expired"
    return payload, ""


def _roles_from_claims(payload: dict[str, Any]) -> set[str]:
    roles = payload.get("roles", payload.get("role", []))
    if isinstance(roles, str):
        return {roles}
    if isinstance(roles, list):
        return {str(role) for role in roles if str(role).strip()}
    return set()


def _tenant_matches(row: dict[str, Any], tenant_id: str) -> bool:
    row_tenant = _text(row.get("tenant_id") or row.get("tenant"))
    return not row_tenant or row_tenant == tenant_id


def _filter_snapshot_for_tenant(snapshot: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    filtered = dict(snapshot)
    for key in ("projects", "families", "portfolios", "submissions"):
        rows = snapshot.get(key)
        if isinstance(rows, list):
            filtered[key] = [row for row in rows if isinstance(row, dict) and _tenant_matches(row, tenant_id)]
    return filtered


def _load_license_status(config: ProjectOpsServiceConfig) -> dict[str, Any]:
    payload = _read_json_object(config.license_status_path)
    if not payload:
        payload = {
            "status": "active",
            "tier": "enterprise_reference",
            "expires_at": "",
        }
    expires_at = _text(payload.get("expires_at"))
    expired = False
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            expired = expires < datetime.now(timezone.utc)
        except ValueError:
            expired = True
    status = "expired" if expired else _text(payload.get("status")) or "active"
    return {
        "status": status,
        "degraded": expired or status not in {"active", "trial", "enterprise_reference"},
        "tier": _text(payload.get("tier")) or "enterprise_reference",
        "expires_at": expires_at,
        "telemetry_enabled": bool(config.telemetry_enabled),
    }


def _resolve_paths(config: ProjectOpsServiceConfig) -> dict[str, Any]:
    release_root = config.release_root
    portfolio_root = release_root / "authoring" / "portfolio"
    return {
        "release_root": release_root,
        "portfolio_root": portfolio_root,
        "portfolio_json_path": config.portfolio_json_path or (portfolio_root / "native_authoring_ops_portfolio.json"),
        "registry_index_json_path": config.registry_index_json_path
        or (portfolio_root / "native_authoring_project_registry_index.json"),
        "portfolio_batch_json_path": config.portfolio_batch_json_path
        or (portfolio_root / "native_authoring_ops_portfolio_batch.json"),
        "runtime_submission_json_path": config.runtime_submission_json_path
        or (portfolio_root / DEFAULT_RUNTIME_SUBMISSION_JSON.name),
        "runtime_writeback_depth_json_path": config.runtime_writeback_depth_json_path
        or (portfolio_root / DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON.name),
        "multi_project_runtime_writeback_json_path": config.multi_project_runtime_writeback_json_path
        or (portfolio_root / DEFAULT_MULTI_PROJECT_RUNTIME_WRITEBACK_JSON.name),
        "solver_family_breadth_json_path": config.solver_family_breadth_json_path
        or (portfolio_root / DEFAULT_SOLVER_FAMILY_BREADTH_JSON.name),
        "local_runtime_scenario_depth_json_path": config.local_runtime_scenario_depth_json_path
        or (portfolio_root / DEFAULT_LOCAL_RUNTIME_SCENARIO_DEPTH_JSON.name),
        "release_registry_json_path": config.release_registry_json_path or (release_root / "release_registry.json"),
        "committee_summary_json_path": config.committee_summary_json_path
        or (release_root / "committee_review" / "committee_summary.json"),
        "release_gap_report_json_path": config.release_gap_report_json_path
        or (release_root / "release_gap_report.json"),
        "snapshot_manifest_glob": _text(config.snapshot_manifest_glob) or DEFAULT_SNAPSHOT_MANIFEST_GLOB,
        "project_registry_paths": [Path(item) for item in config.project_registry_paths if _text(item)],
        "project_registry_dirs": [Path(item) for item in config.project_registry_dirs if _text(item)],
    }


def _registry_paths_from_portfolio(portfolio_payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in _rows(portfolio_payload, "family_rows"):
        artifacts = _dict(row.get("artifacts"))
        path_text = _text(artifacts.get("project_registry_json"))
        if path_text:
            paths.append(Path(path_text))
    return _dedupe_paths(paths)


def _batch_paths_from_portfolio(portfolio_payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in _rows(portfolio_payload, "family_rows"):
        artifacts = _dict(row.get("artifacts"))
        path_text = _text(artifacts.get("batch_job_report_json"))
        if path_text:
            paths.append(Path(path_text))
    return _dedupe_paths(paths)


def _normalize_registry_index(
    *,
    registry_index_payload: dict[str, Any],
    registry_paths: list[Path],
    registry_dirs: list[Path],
    generated_at: str,
) -> dict[str, Any]:
    if registry_index_payload:
        return registry_index_payload
    if not registry_paths and not registry_dirs:
        return {}
    return build_project_registry_index(
        registry_paths=registry_paths,
        registry_dirs=registry_dirs,
        generated_at=generated_at,
    )


def _summarize_batch_report(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(payload.get("summary"))
    return {
        "path": str(path),
        "job_count": _coerce_int(summary.get("job_count", 0)),
        "snapshot_count": _coerce_int(summary.get("snapshot_count", 0)),
        "completed_count": _coerce_int(summary.get("completed_count", 0)),
        "failed_count": _coerce_int(summary.get("failed_count", 0)),
        "planned_count": _coerce_int(summary.get("planned_count", 0)),
        "blocked_count": _coerce_int(summary.get("blocked_count", 0)),
        "rerun_requested_count": _coerce_int(summary.get("rerun_requested_count", 0)),
        "contract_pass": _coerce_bool(payload.get("contract_pass", False)),
        "reason_code": _text(payload.get("reason_code")),
        "summary_line": _text(payload.get("summary_line")),
    }


def _collect_batch_reports(
    *,
    portfolio_payload: dict[str, Any],
    portfolio_batch_json_path: Path,
    portfolio_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[Path]]:
    primary_batch_payload = _read_json_object(portfolio_batch_json_path)
    family_paths = _batch_paths_from_portfolio(portfolio_payload)
    if not family_paths and portfolio_root.exists():
        family_paths = _dedupe_paths(list(portfolio_root.rglob("native_authoring_batch_job_report.json")))

    family_reports: list[dict[str, Any]] = []
    loaded_paths: list[Path] = []
    for path in family_paths:
        payload = _read_json_object(path)
        if not payload:
            continue
        loaded_paths.append(path)
        report = _summarize_batch_report(path, payload)
        report["family_id"] = _text(path.parent.name)
        family_reports.append(report)

    return primary_batch_payload, family_reports, loaded_paths


def _resolve_latest_release_snapshot(release_root: Path, snapshot_manifest_glob: str) -> tuple[dict[str, Any], Path | None]:
    candidates = _dedupe_paths(list(release_root.glob(snapshot_manifest_glob)))
    best_payload: dict[str, Any] = {}
    best_path: Path | None = None
    best_key: tuple[str, str] = ("", "")

    for path in candidates:
        payload = _read_json_object(path)
        if not payload:
            continue
        generated_at = _text(payload.get("generated_at"))
        key = (generated_at, str(path))
        if key >= best_key:
            best_key = key
            best_payload = payload
            best_path = path
    return best_payload, best_path


def _submission_source_rows(runtime_submission_payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("submission_rows", "family_rows", "rows"):
        rows = _rows(runtime_submission_payload, key)
        if rows:
            return rows
    return []


def _build_submission_rows(
    *,
    portfolio_payload: dict[str, Any],
    runtime_submission_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    source_rows = _submission_source_rows(runtime_submission_payload)
    portfolio_family_rows = _rows(portfolio_payload, "family_rows")
    portfolio_by_family = {
        _text(row.get("family_id")): row
        for row in portfolio_family_rows
        if _text(row.get("family_id"))
    }
    portfolio_by_project = {
        _text(row.get("project_id")): row
        for row in portfolio_family_rows
        if _text(row.get("project_id"))
    }

    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for source_row in source_rows:
        family_id = _first_text(
            source_row.get("family_id"),
            source_row.get("authoring_family_id"),
            source_row.get("project_family_id"),
        )
        project_id = _first_text(source_row.get("project_id"))
        portfolio_row = portfolio_by_family.get(family_id) or portfolio_by_project.get(project_id) or {}
        artifacts = {**_dict(portfolio_row.get("artifacts")), **_dict(source_row.get("artifacts"))}
        submission_id = _first_text(source_row.get("submission_id"), family_id, project_id)
        submitted_at = _first_text(
            source_row.get("submitted_at"),
            source_row.get("generated_at"),
            source_row.get("updated_at"),
        )
        row = {
            "submission_id": submission_id,
            "family_id": family_id,
            "family_label": _first_text(source_row.get("family_label"), portfolio_row.get("family_label")),
            "portfolio_name": _first_text(source_row.get("portfolio_name"), portfolio_row.get("portfolio_name")),
            "project_id": _first_text(source_row.get("project_id"), portfolio_row.get("project_id")),
            "project_name": _first_text(source_row.get("project_name"), portfolio_row.get("project_name")),
            "draft_label": _first_text(source_row.get("draft_label"), portfolio_row.get("draft_label")),
            "submission_status": _first_text(
                source_row.get("submission_status"),
                source_row.get("queue_status"),
                source_row.get("status"),
            ),
            "queue_status": _first_text(
                source_row.get("queue_status"),
                source_row.get("submission_status"),
                source_row.get("status"),
            ),
            "runtime_ready": _first_bool(
                source_row.get("runtime_ready"),
                source_row.get("ready"),
                source_row.get("release_ready"),
                portfolio_row.get("runtime_ready"),
                source_row.get("contract_pass"),
            ),
            "writeback_ready": _first_bool(
                source_row.get("writeback_ready"),
                source_row.get("registry_ready"),
                source_row.get("signature_verified"),
                portfolio_row.get("registry_ready"),
                portfolio_row.get("signature_verified"),
            ),
            "release_ready": _first_bool(
                source_row.get("release_ready"),
                source_row.get("runtime_ready"),
                source_row.get("ready"),
            ),
            "registry_ready": _first_bool(
                source_row.get("registry_ready"),
                portfolio_row.get("registry_ready"),
            ),
            "signature_verified": _first_bool(
                source_row.get("signature_verified"),
                portfolio_row.get("signature_verified"),
            ),
            "contract_pass": _first_bool(
                source_row.get("contract_pass"),
                source_row.get("runtime_ready"),
                source_row.get("ready"),
            ),
            "reason_code": _first_text(source_row.get("reason_code"), portfolio_row.get("reason_code")),
            "commercialization_status": _first_text(
                source_row.get("commercialization_status"),
                portfolio_row.get("commercialization_status"),
            ),
            "commercialization_score": _first_int(
                source_row.get("commercialization_score"),
                portfolio_row.get("commercialization_score"),
            ),
            "story_count": _first_int(source_row.get("story_count"), portfolio_row.get("story_count")),
            "member_count": _first_int(source_row.get("member_count"), portfolio_row.get("member_count")),
            "solver_combo_count": _first_int(
                source_row.get("solver_combo_count"),
                portfolio_row.get("solver_combo_count"),
            ),
            "solver_mesh_request_count": _first_int(
                source_row.get("solver_mesh_request_count"),
                portfolio_row.get("solver_mesh_request_count"),
            ),
            "submitted_at": submitted_at,
            "latest_generated_at": submitted_at,
            "summary_line": _first_text(source_row.get("summary_line")),
            "artifacts": artifacts,
        }
        key = (
            _text(row.get("family_id")),
            _text(row.get("submission_id")),
            _text(row.get("submitted_at")),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(row)

    rows.sort(
        key=lambda row: (
            _text(row.get("portfolio_name")),
            _text(row.get("family_id")),
            _text(row.get("submission_id")),
            _text(row.get("submitted_at")),
        )
    )
    return rows


def _build_runtime_submission_surface(
    *,
    runtime_submission_payload: dict[str, Any],
    runtime_submission_json_path: Path,
    submission_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = _dict(runtime_submission_payload.get("summary"))
    submission_ready_count = _first_int(
        summary.get("submission_ready_count"),
        summary.get("ready_submission_count"),
        summary.get("release_ready_count"),
        sum(
            1
            for row in submission_rows
            if _first_bool(
                row.get("submission_ready"),
                row.get("runtime_ready"),
                row.get("release_ready"),
            )
        ),
    )
    runtime_ready_count = _first_int(
        summary.get("runtime_ready_count"),
        summary.get("ready_submission_count"),
        summary.get("release_ready_count"),
        sum(1 for row in submission_rows if _first_bool(row.get("runtime_ready"), row.get("release_ready"))),
    )
    submission_count = _first_int(
        summary.get("submission_count"),
        summary.get("family_count"),
        len(submission_rows),
    )
    ready_submission_count = _first_int(
        summary.get("ready_submission_count"),
        summary.get("runtime_ready_count"),
        summary.get("submission_ready_count"),
        summary.get("release_ready_count"),
        runtime_ready_count,
    )
    writeback_ready_count = _first_int(
        summary.get("writeback_ready_count"),
        sum(1 for row in submission_rows if _first_bool(row.get("writeback_ready"))),
    )
    full_ready_count = _first_int(
        summary.get("full_ready_count"),
        sum(
            1
            for row in submission_rows
            if _first_bool(row.get("runtime_ready"), row.get("release_ready"))
            and _first_bool(row.get("writeback_ready"))
        ),
    )
    queue_count = _first_int(
        summary.get("queue_count"),
        summary.get("pending_submission_count"),
        summary.get("open_submission_count"),
        sum(
            1
            for row in submission_rows
            if _text(row.get("submission_status")).lower() in {"queued", "pending", "submitted", "open"}
        ),
    )
    runtime_submission_ready = _first_bool(
        summary.get("runtime_submission_ready"),
        runtime_submission_payload.get("contract_pass"),
        submission_count > 0 and ready_submission_count >= submission_count,
    )
    summary_line = _first_text(
        runtime_submission_payload.get("summary_line"),
        (
            "Native authoring runtime submission lane: "
            f"{'READY' if runtime_submission_ready else 'CHECK'} | "
            f"submissions={submission_count} | submission_ready={submission_ready_count} | "
            f"runtime_ready={runtime_ready_count} | writeback_ready={writeback_ready_count} | "
            f"full_ready={full_ready_count} | queue={queue_count}"
            if runtime_submission_payload
            else ""
        ),
    )
    return {
        "available": bool(runtime_submission_payload),
        "report_path": str(runtime_submission_json_path) if runtime_submission_payload else "",
        "summary": {
            "runtime_submission_ready": runtime_submission_ready,
            "submission_count": submission_count,
            "submission_ready_count": submission_ready_count,
            "runtime_ready_count": runtime_ready_count,
            "ready_submission_count": ready_submission_count,
            "writeback_ready_count": writeback_ready_count,
            "full_ready_count": full_ready_count,
            "queue_count": queue_count,
            "contract_pass": _first_bool(
                runtime_submission_payload.get("contract_pass"),
                runtime_submission_ready,
            ),
        },
        "summary_line": summary_line,
    }


def _build_endpoint_rows() -> list[dict[str, Any]]:
    return [
        {
            "method": "GET",
            "path": path,
            "resource": path.strip("/").split("/", 1)[0] or "root",
        }
        for path in SERVICE_ENDPOINT_PATHS
    ]


def _project_rows_from_registry(registry_index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(registry_index_payload, "project_rows")
    if rows:
        return rows

    fallback_rows: list[dict[str, Any]] = []
    for row in _rows(registry_index_payload, "rows"):
        fallback_rows.append(
            {
                "project_id": _text(row.get("project_id")) or Path(_text(row.get("path"))).stem,
                "project_name": _text(row.get("project_name")) or _text(row.get("project_id")),
                "registry_count": 1,
                "all_contract_pass": _coerce_bool(row.get("contract_pass", False)),
                "any_contract_pass": _coerce_bool(row.get("contract_pass", False)),
                "latest_generated_at": _text(row.get("generated_at")),
                "latest_path": _text(row.get("path")),
                "latest_reason_code": _text(row.get("reason_code")),
                "latest_signature_verified": _coerce_bool(row.get("signature_verified", False)),
                "latest_package_reproducible": _coerce_bool(row.get("package_reproducible", False)),
                "latest_approval_count": _coerce_int(row.get("approval_count", 0)),
                "latest_approved_count": _coerce_int(row.get("approved_count", 0)),
                "latest_pending_count": _coerce_int(row.get("pending_count", 0)),
                "latest_audit_event_count": _coerce_int(row.get("audit_event_count", 0)),
                "latest_artifact_count": _coerce_int(row.get("artifact_count", 0)),
                "latest_package_sha256": _text(row.get("package_sha256")),
                "latest_family_id": _text(row.get("family_id")),
                "latest_portfolio_name": _text(row.get("portfolio_name")),
                "latest_draft_label": _text(row.get("draft_label")),
                "registry_paths": [_text(row.get("path"))] if _text(row.get("path")) else [],
            }
        )
    return fallback_rows


def _build_project_rows(
    *,
    portfolio_payload: dict[str, Any],
    registry_index_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    portfolio_family_rows = _rows(portfolio_payload, "family_rows")
    portfolio_by_project = {
        _text(row.get("project_id")): row
        for row in portfolio_family_rows
        if _text(row.get("project_id"))
    }
    registry_project_rows = _project_rows_from_registry(registry_index_payload)

    rows: list[dict[str, Any]] = []
    seen_project_ids: set[str] = set()
    for registry_row in registry_project_rows:
        project_id = _text(registry_row.get("project_id"))
        if not project_id:
            continue
        seen_project_ids.add(project_id)
        family_row = portfolio_by_project.get(project_id, {})
        artifacts = _dict(family_row.get("artifacts"))
        rows.append(
            {
                "project_id": project_id,
                "project_name": _text(registry_row.get("project_name")) or _text(family_row.get("project_name")),
                "family_id": _text(registry_row.get("latest_family_id")) or _text(family_row.get("family_id")),
                "family_label": _text(family_row.get("family_label")),
                "portfolio_name": _text(registry_row.get("latest_portfolio_name"))
                or _text(family_row.get("portfolio_name")),
                "draft_label": _text(registry_row.get("latest_draft_label")) or _text(family_row.get("draft_label")),
                "registry_count": _coerce_int(registry_row.get("registry_count", 0)),
                "registry_contract_pass": _coerce_bool(registry_row.get("all_contract_pass", False)),
                "registry_signature_verified": _coerce_bool(
                    registry_row.get("latest_signature_verified", registry_row.get("signature_verified", False))
                ),
                "package_reproducible": _coerce_bool(
                    registry_row.get(
                        "latest_package_reproducible",
                        registry_row.get("package_reproducible", False),
                    )
                ),
                "approval_count": _coerce_int(registry_row.get("latest_approval_count", 0)),
                "approved_count": _coerce_int(registry_row.get("latest_approved_count", 0)),
                "pending_count": _coerce_int(registry_row.get("latest_pending_count", 0)),
                "audit_event_count": _coerce_int(registry_row.get("latest_audit_event_count", 0)),
                "artifact_count": _coerce_int(registry_row.get("latest_artifact_count", 0)),
                "package_sha256": _text(registry_row.get("latest_package_sha256")),
                "latest_generated_at": _text(registry_row.get("latest_generated_at")),
                "latest_path": _text(registry_row.get("latest_path")),
                "registry_paths": [
                    _text(path)
                    for path in registry_row.get("registry_paths", [])
                    if _text(path)
                ],
                "registry_reason_code": _text(registry_row.get("latest_reason_code")),
                "contract_pass": _coerce_bool(family_row.get("contract_pass", False)),
                "reason_code": _text(family_row.get("reason_code")),
                "commercialization_status": _text(family_row.get("commercialization_status")),
                "commercialization_score": _coerce_int(family_row.get("commercialization_score", 0)),
                "story_count": _coerce_int(family_row.get("story_count", 0)),
                "member_count": _coerce_int(family_row.get("member_count", 0)),
                "load_pattern_count": _coerce_int(family_row.get("load_pattern_count", 0)),
                "solver_combo_count": _coerce_int(family_row.get("solver_combo_count", 0)),
                "solver_mesh_request_count": _coerce_int(family_row.get("solver_mesh_request_count", 0)),
                "job_count": _coerce_int(family_row.get("job_count", 0)),
                "snapshot_count": _coerce_int(family_row.get("snapshot_count", 0)),
                "workspace_ready": _coerce_bool(family_row.get("workspace_ready", False)),
                "solver_ready": _coerce_bool(family_row.get("solver_ready", False)),
                "runtime_ready": _coerce_bool(family_row.get("runtime_ready", False)),
                "ops_ready": _coerce_bool(family_row.get("ops_ready", False)),
                "batch_ready": _coerce_bool(family_row.get("batch_ready", False)),
                "registry_ready": _coerce_bool(family_row.get("registry_ready", False)),
                "signature_verified": _coerce_bool(family_row.get("signature_verified", False)),
                "summary_line": _text(family_row.get("summary_line")),
                "artifacts": artifacts,
            }
        )

    for family_row in portfolio_family_rows:
        project_id = _text(family_row.get("project_id"))
        if not project_id or project_id in seen_project_ids:
            continue
        rows.append(
            {
                "project_id": project_id,
                "project_name": _text(family_row.get("project_name")),
                "family_id": _text(family_row.get("family_id")),
                "family_label": _text(family_row.get("family_label")),
                "portfolio_name": _text(family_row.get("portfolio_name")),
                "draft_label": _text(family_row.get("draft_label")),
                "registry_count": 0,
                "registry_contract_pass": False,
                "registry_signature_verified": False,
                "package_reproducible": False,
                "approval_count": 0,
                "approved_count": 0,
                "pending_count": 0,
                "audit_event_count": 0,
                "artifact_count": 0,
                "package_sha256": _text(family_row.get("registry_package_sha256")),
                "latest_generated_at": "",
                "latest_path": _text(_dict(family_row.get("artifacts")).get("project_registry_json")),
                "registry_paths": [],
                "registry_reason_code": "",
                "contract_pass": _coerce_bool(family_row.get("contract_pass", False)),
                "reason_code": _text(family_row.get("reason_code")),
                "commercialization_status": _text(family_row.get("commercialization_status")),
                "commercialization_score": _coerce_int(family_row.get("commercialization_score", 0)),
                "story_count": _coerce_int(family_row.get("story_count", 0)),
                "member_count": _coerce_int(family_row.get("member_count", 0)),
                "load_pattern_count": _coerce_int(family_row.get("load_pattern_count", 0)),
                "solver_combo_count": _coerce_int(family_row.get("solver_combo_count", 0)),
                "solver_mesh_request_count": _coerce_int(family_row.get("solver_mesh_request_count", 0)),
                "job_count": _coerce_int(family_row.get("job_count", 0)),
                "snapshot_count": _coerce_int(family_row.get("snapshot_count", 0)),
                "workspace_ready": _coerce_bool(family_row.get("workspace_ready", False)),
                "solver_ready": _coerce_bool(family_row.get("solver_ready", False)),
                "runtime_ready": _coerce_bool(family_row.get("runtime_ready", False)),
                "ops_ready": _coerce_bool(family_row.get("ops_ready", False)),
                "batch_ready": _coerce_bool(family_row.get("batch_ready", False)),
                "registry_ready": _coerce_bool(family_row.get("registry_ready", False)),
                "signature_verified": _coerce_bool(family_row.get("signature_verified", False)),
                "summary_line": _text(family_row.get("summary_line")),
                "artifacts": _dict(family_row.get("artifacts")),
            }
        )

    rows.sort(key=lambda row: (_text(row.get("portfolio_name")), _text(row.get("family_id")), _text(row.get("project_id"))))
    return rows


def _build_family_rows(
    *,
    portfolio_payload: dict[str, Any],
    registry_index_payload: dict[str, Any],
    project_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    portfolio_family_rows = _rows(portfolio_payload, "family_rows")
    portfolio_by_key = {
        (_text(row.get("portfolio_name")), _text(row.get("family_id"))): row
        for row in portfolio_family_rows
        if _text(row.get("family_id"))
    }
    registry_family_rows = {
        (_text(row.get("portfolio_name")), _text(row.get("family_id"))): row
        for row in _rows(registry_index_payload, "family_rows")
        if _text(row.get("family_id"))
    }

    all_keys = sorted({*portfolio_by_key.keys(), *registry_family_rows.keys()})
    family_rows: list[dict[str, Any]] = []
    for key in all_keys:
        portfolio_name, family_id = key
        portfolio_row = portfolio_by_key.get(key, {})
        registry_row = registry_family_rows.get(key, {})
        matching_projects = [row for row in project_rows if _text(row.get("portfolio_name")) == portfolio_name and _text(row.get("family_id")) == family_id]
        if not matching_projects and portfolio_row:
            project_ids = [_text(portfolio_row.get("project_id"))] if _text(portfolio_row.get("project_id")) else []
        else:
            project_ids = _dedupe_strings([_text(row.get("project_id")) for row in matching_projects])

        family_rows.append(
            {
                "family_id": family_id,
                "portfolio_name": portfolio_name,
                "family_label": _text(portfolio_row.get("family_label")),
                "project_ids": project_ids or [_text(item) for item in registry_row.get("project_ids", []) if _text(item)],
                "project_count": len(project_ids or registry_row.get("project_ids", [])),
                "draft_labels": [
                    _text(item) for item in registry_row.get("draft_labels", []) if _text(item)
                ] or ([_text(portfolio_row.get("draft_label"))] if _text(portfolio_row.get("draft_label")) else []),
                "registry_count": _coerce_int(registry_row.get("registry_count", 0)),
                "complete_registry_count": _coerce_int(registry_row.get("complete_registry_count", 0)),
                "signature_verified_count": _coerce_int(registry_row.get("signature_verified_count", 0)),
                "package_reproducible_count": _coerce_int(registry_row.get("package_reproducible_count", 0)),
                "latest_generated_at": _text(registry_row.get("latest_generated_at")),
                "latest_path": _text(registry_row.get("latest_path")),
                "latest_project_id": _text(registry_row.get("latest_project_id")),
                "latest_project_name": _text(registry_row.get("latest_project_name")),
                "contract_pass": _coerce_bool(portfolio_row.get("contract_pass", False)),
                "reason_code": _text(portfolio_row.get("reason_code")),
                "commercialization_status": _text(portfolio_row.get("commercialization_status")),
                "commercialization_score": _coerce_int(portfolio_row.get("commercialization_score", 0)),
                "story_count": _coerce_int(portfolio_row.get("story_count", 0)),
                "member_count": _coerce_int(portfolio_row.get("member_count", 0)),
                "load_pattern_count": _coerce_int(portfolio_row.get("load_pattern_count", 0)),
                "solver_combo_count": _coerce_int(portfolio_row.get("solver_combo_count", 0)),
                "solver_mesh_request_count": _coerce_int(portfolio_row.get("solver_mesh_request_count", 0)),
                "job_count": _coerce_int(portfolio_row.get("job_count", 0)),
                "snapshot_count": _coerce_int(portfolio_row.get("snapshot_count", 0)),
                "workspace_ready": _first_bool(
                    portfolio_row.get("workspace_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("workspace_ready", False)) for row in matching_projects),
                ),
                "solver_ready": _first_bool(
                    portfolio_row.get("solver_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("solver_ready", False)) for row in matching_projects),
                ),
                "runtime_ready": _first_bool(
                    portfolio_row.get("runtime_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("runtime_ready", False)) for row in matching_projects),
                ),
                "ops_ready": _first_bool(
                    portfolio_row.get("ops_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("ops_ready", False)) for row in matching_projects),
                ),
                "batch_ready": _first_bool(
                    portfolio_row.get("batch_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("batch_ready", False)) for row in matching_projects),
                ),
                "registry_ready": _first_bool(
                    portfolio_row.get("registry_ready"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("registry_ready", False)) for row in matching_projects),
                ),
                "signature_verified": _first_bool(
                    portfolio_row.get("signature_verified"),
                    bool(matching_projects)
                    and all(_coerce_bool(row.get("signature_verified", False)) for row in matching_projects),
                ),
                "summary_line": _text(portfolio_row.get("summary_line")),
                "artifacts": _dict(portfolio_row.get("artifacts")),
            }
        )

    if not family_rows:
        grouped_projects: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in project_rows:
            key = (_text(row.get("portfolio_name")), _text(row.get("family_id")))
            if not key[1]:
                continue
            grouped_projects.setdefault(key, []).append(row)
        for (portfolio_name, family_id), grouped in sorted(grouped_projects.items()):
            family_rows.append(
                {
                    "family_id": family_id,
                    "portfolio_name": portfolio_name,
                    "family_label": "",
                    "project_ids": _dedupe_strings([_text(row.get("project_id")) for row in grouped]),
                    "project_count": len(grouped),
                    "draft_labels": _dedupe_strings([_text(row.get("draft_label")) for row in grouped]),
                    "registry_count": sum(_coerce_int(row.get("registry_count", 0)) for row in grouped),
                    "complete_registry_count": sum(1 for row in grouped if _coerce_bool(row.get("registry_contract_pass", False))),
                    "signature_verified_count": sum(1 for row in grouped if _coerce_bool(row.get("registry_signature_verified", False))),
                    "package_reproducible_count": sum(1 for row in grouped if _coerce_bool(row.get("package_reproducible", False))),
                    "latest_generated_at": _iso_max([_text(row.get("latest_generated_at")) for row in grouped]),
                    "latest_path": next((_text(row.get("latest_path")) for row in grouped if _text(row.get("latest_path"))), ""),
                    "latest_project_id": _text(grouped[0].get("project_id")),
                    "latest_project_name": _text(grouped[0].get("project_name")),
                    "contract_pass": all(_coerce_bool(row.get("contract_pass", False)) for row in grouped),
                    "reason_code": "",
                    "commercialization_status": "",
                    "commercialization_score": 0,
                    "story_count": 0,
                    "member_count": 0,
                    "load_pattern_count": 0,
                    "solver_combo_count": sum(_coerce_int(row.get("solver_combo_count", 0)) for row in grouped),
                    "solver_mesh_request_count": sum(
                        _coerce_int(row.get("solver_mesh_request_count", 0)) for row in grouped
                    ),
                    "job_count": sum(_coerce_int(row.get("job_count", 0)) for row in grouped),
                    "snapshot_count": sum(_coerce_int(row.get("snapshot_count", 0)) for row in grouped),
                    "workspace_ready": all(_coerce_bool(row.get("workspace_ready", False)) for row in grouped),
                    "solver_ready": all(_coerce_bool(row.get("solver_ready", False)) for row in grouped),
                    "runtime_ready": all(_coerce_bool(row.get("runtime_ready", False)) for row in grouped),
                    "ops_ready": all(_coerce_bool(row.get("ops_ready", False)) for row in grouped),
                    "batch_ready": all(_coerce_bool(row.get("batch_ready", False)) for row in grouped),
                    "registry_ready": all(_coerce_bool(row.get("registry_ready", False)) for row in grouped),
                    "signature_verified": all(_coerce_bool(row.get("signature_verified", False)) for row in grouped),
                    "summary_line": "",
                    "artifacts": {},
                }
            )

    family_rows.sort(key=lambda row: (_text(row.get("portfolio_name")), _text(row.get("family_id"))))
    return family_rows


def _build_portfolio_rows(
    *,
    portfolio_payload: dict[str, Any],
    project_rows: list[dict[str, Any]],
    family_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in family_rows:
        portfolio_name = _safe_label(_text(row.get("portfolio_name")))
        grouped.setdefault(
            portfolio_name,
            {
                "portfolio_name": portfolio_name,
                "family_ids": [],
                "project_ids": [],
                "ready_family_count": 0,
                "narrowing_family_count": 0,
                "complete_family_count": 0,
                "signature_verified_count": 0,
                "package_reproducible_count": 0,
                "solver_combo_count": 0,
                "batch_snapshot_count": 0,
                "latest_generated_at": "",
            },
        )
        bucket = grouped[portfolio_name]
        family_id = _text(row.get("family_id"))
        if family_id:
            bucket["family_ids"].append(family_id)
        bucket["project_ids"].extend([_text(item) for item in row.get("project_ids", []) if _text(item)])
        if _coerce_bool(row.get("contract_pass", False)):
            bucket["complete_family_count"] = _coerce_int(bucket["complete_family_count"]) + 1
        if _text(row.get("commercialization_status")) == "ready":
            bucket["ready_family_count"] = _coerce_int(bucket["ready_family_count"]) + 1
        if _text(row.get("commercialization_status")) == "narrowing":
            bucket["narrowing_family_count"] = _coerce_int(bucket["narrowing_family_count"]) + 1
        bucket["signature_verified_count"] = _coerce_int(bucket["signature_verified_count"]) + _coerce_int(
            row.get("signature_verified_count", 0)
        )
        bucket["package_reproducible_count"] = _coerce_int(bucket["package_reproducible_count"]) + _coerce_int(
            row.get("package_reproducible_count", 0)
        )
        bucket["solver_combo_count"] = _coerce_int(bucket["solver_combo_count"]) + _coerce_int(
            row.get("solver_combo_count", 0)
        )
        bucket["batch_snapshot_count"] = _coerce_int(bucket["batch_snapshot_count"]) + _coerce_int(
            row.get("snapshot_count", 0)
        )
        bucket["latest_generated_at"] = max(_text(bucket["latest_generated_at"]), _text(row.get("latest_generated_at")))

    portfolio_summary = _dict(portfolio_payload.get("summary"))
    portfolio_artifacts = _dict(portfolio_payload.get("artifacts"))
    source_portfolio_name = _safe_label(_text(portfolio_summary.get("portfolio_name")))

    rows: list[dict[str, Any]] = []
    for portfolio_name, bucket in sorted(grouped.items()):
        matching_projects = [row for row in project_rows if _safe_label(_text(row.get("portfolio_name"))) == portfolio_name]
        source_summary = portfolio_summary if portfolio_name == source_portfolio_name else {}
        rows.append(
            {
                "portfolio_name": portfolio_name,
                "family_count": len(_dedupe_strings(bucket["family_ids"])),
                "project_count": len(_dedupe_strings(bucket["project_ids"])),
                "complete_family_count": _coerce_int(
                    source_summary.get("complete_family_count", bucket["complete_family_count"])
                ),
                "ready_family_count": _coerce_int(source_summary.get("ready_family_count", bucket["ready_family_count"])),
                "narrowing_family_count": _coerce_int(
                    source_summary.get("narrowing_family_count", bucket["narrowing_family_count"])
                ),
                "signature_verified_count": _coerce_int(bucket["signature_verified_count"]),
                "package_reproducible_count": _coerce_int(bucket["package_reproducible_count"]),
                "solver_combo_count": _coerce_int(source_summary.get("solver_combo_count", bucket["solver_combo_count"])),
                "batch_snapshot_count": _coerce_int(
                    source_summary.get("batch_snapshot_count", bucket["batch_snapshot_count"])
                ),
                "latest_generated_at": _text(bucket["latest_generated_at"]),
                "artifacts": portfolio_artifacts if portfolio_name == source_portfolio_name else {},
                "summary_line": _text(portfolio_payload.get("summary_line")) if portfolio_name == source_portfolio_name else "",
                "project_ids": _dedupe_strings([_text(row.get("project_id")) for row in matching_projects]),
                "family_ids": _dedupe_strings(bucket["family_ids"]),
            }
        )

    if not rows and portfolio_summary:
        rows.append(
            {
                "portfolio_name": source_portfolio_name,
                "family_count": _coerce_int(portfolio_summary.get("family_count", 0)),
                "project_count": _coerce_int(portfolio_summary.get("registry_project_count", 0)),
                "complete_family_count": _coerce_int(portfolio_summary.get("complete_family_count", 0)),
                "ready_family_count": _coerce_int(portfolio_summary.get("ready_family_count", 0)),
                "narrowing_family_count": _coerce_int(portfolio_summary.get("narrowing_family_count", 0)),
                "signature_verified_count": _coerce_int(portfolio_summary.get("registry_signature_verified_count", 0)),
                "package_reproducible_count": _coerce_int(portfolio_summary.get("registry_reproducible_count", 0)),
                "solver_combo_count": _coerce_int(portfolio_summary.get("solver_combo_count", 0)),
                "batch_snapshot_count": _coerce_int(portfolio_summary.get("batch_snapshot_count", 0)),
                "latest_generated_at": _text(portfolio_payload.get("generated_at")),
                "artifacts": portfolio_artifacts,
                "summary_line": _text(portfolio_payload.get("summary_line")),
                "project_ids": [],
                "family_ids": [],
            }
        )

    return rows


def _build_release_governance(
    *,
    release_registry_payload: dict[str, Any],
    committee_summary_payload: dict[str, Any],
    release_gap_payload: dict[str, Any],
    latest_snapshot_payload: dict[str, Any],
    latest_snapshot_path: Path | None,
) -> dict[str, Any]:
    release_registry_summary = _dict(release_registry_payload.get("summary"))
    release_registry_checks = _dict(release_registry_payload.get("checks"))
    committee_metrics = _dict(committee_summary_payload.get("metrics"))
    gap_summary = _dict(release_gap_payload.get("summary"))
    snapshot_release_policy = _dict(latest_snapshot_payload.get("release_policy"))

    return {
        "release_registry": {
            "available": bool(release_registry_payload),
            "contract_pass": _coerce_bool(release_registry_payload.get("contract_pass", False)),
            "reason_code": _text(release_registry_payload.get("reason_code")),
            "signature_verified": _coerce_bool(release_registry_checks.get("signature_verified_pass", False)),
            "project_registry_signature_verified": _coerce_bool(
                release_registry_checks.get("project_registry_signature_verified_pass", False)
            ),
            "artifact_count": _coerce_int(release_registry_summary.get("artifact_count", 0)),
            "deployment_model": _text(release_registry_summary.get("deployment_model")),
            "project_registry_artifact_count": _coerce_int(
                release_registry_summary.get("project_registry_artifact_count", 0)
            ),
            "project_registry_approval_count": _coerce_int(
                release_registry_summary.get("project_registry_approval_count", 0)
            ),
            "project_registry_package_sha256": _text(
                release_registry_summary.get("project_registry_package_sha256")
            ),
            "project_registry_package_bytes": _coerce_int(
                release_registry_summary.get("project_registry_package_bytes", 0)
            ),
            "signing_algorithm": _text(release_registry_summary.get("signing_algorithm")),
        },
        "committee_summary": {
            "available": bool(committee_summary_payload),
            "authority_catalog_diff_change_count": _coerce_int(
                committee_summary_payload.get(
                    "authority_catalog_diff_change_count",
                    committee_metrics.get("authority_catalog_diff_change_count", 0),
                )
            ),
            "authority_catalog_routing_warning_active": _coerce_bool(
                committee_summary_payload.get(
                    "authority_catalog_routing_warning_active",
                    committee_metrics.get("authority_catalog_routing_warning_active", False),
                )
            ),
            "advanced_holdout_open_count": _coerce_int(
                committee_summary_payload.get(
                    "advanced_holdout_open_count",
                    committee_metrics.get("advanced_holdout_open_count", 0),
                )
            ),
            "advanced_holdout_total_count": _coerce_int(
                committee_summary_payload.get(
                    "advanced_holdout_total_count",
                    committee_metrics.get("advanced_holdout_total_count", 0),
                )
            ),
        },
        "release_gap_report": {
            "available": bool(release_gap_payload),
            "release_candidate_pass": _coerce_bool(gap_summary.get("release_candidate_pass", False)),
            "commercial_grade": _text(gap_summary.get("commercial_grade")),
            "deployment_model": _text(gap_summary.get("deployment_model")),
        },
        "latest_release_snapshot": {
            "available": bool(latest_snapshot_payload),
            "path": _path_text(latest_snapshot_path),
            "snapshot": _text(latest_snapshot_payload.get("snapshot")),
            "generated_at": _text(latest_snapshot_payload.get("generated_at")),
            "release_policy_pass": _coerce_bool(snapshot_release_policy.get("policy_pass", False)),
            "file_count": len(latest_snapshot_payload.get("files", []))
            if isinstance(latest_snapshot_payload.get("files"), list)
            else 0,
            "optional_file_count": len(latest_snapshot_payload.get("optional_files", []))
            if isinstance(latest_snapshot_payload.get("optional_files"), list)
            else 0,
        },
    }


def build_project_ops_snapshot(
    *,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    portfolio_json_path: Path | None = None,
    registry_index_json_path: Path | None = None,
    portfolio_batch_json_path: Path | None = None,
    runtime_submission_json_path: Path | None = None,
    runtime_writeback_depth_json_path: Path | None = None,
    multi_project_runtime_writeback_json_path: Path | None = None,
    solver_family_breadth_json_path: Path | None = None,
    local_runtime_scenario_depth_json_path: Path | None = None,
    release_registry_json_path: Path | None = None,
    committee_summary_json_path: Path | None = None,
    release_gap_report_json_path: Path | None = None,
    snapshot_manifest_glob: str = DEFAULT_SNAPSHOT_MANIFEST_GLOB,
    project_registry_paths: list[Path | str] | None = None,
    project_registry_dirs: list[Path | str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config = ProjectOpsServiceConfig(
        release_root=release_root,
        portfolio_json_path=portfolio_json_path,
        registry_index_json_path=registry_index_json_path,
        portfolio_batch_json_path=portfolio_batch_json_path,
        runtime_submission_json_path=runtime_submission_json_path,
        runtime_writeback_depth_json_path=runtime_writeback_depth_json_path,
        multi_project_runtime_writeback_json_path=multi_project_runtime_writeback_json_path,
        solver_family_breadth_json_path=solver_family_breadth_json_path,
        local_runtime_scenario_depth_json_path=local_runtime_scenario_depth_json_path,
        release_registry_json_path=release_registry_json_path,
        committee_summary_json_path=committee_summary_json_path,
        release_gap_report_json_path=release_gap_report_json_path,
        snapshot_manifest_glob=snapshot_manifest_glob,
        project_registry_paths=tuple(str(item) for item in (project_registry_paths or []) if _text(item)),
        project_registry_dirs=tuple(str(item) for item in (project_registry_dirs or []) if _text(item)),
    )
    paths = _resolve_paths(config)
    timestamp = _text(generated_at) or _now_utc_iso()

    portfolio_payload = _read_json_object(paths["portfolio_json_path"])
    registry_index_payload = _read_json_object(paths["registry_index_json_path"])
    registry_paths = _dedupe_paths(paths["project_registry_paths"] + _registry_paths_from_portfolio(portfolio_payload))
    registry_dirs = _dedupe_paths(paths["project_registry_dirs"] or [paths["portfolio_root"]])
    registry_index_payload = _normalize_registry_index(
        registry_index_payload=registry_index_payload,
        registry_paths=registry_paths,
        registry_dirs=registry_dirs,
        generated_at=timestamp,
    )

    primary_batch_payload, family_batch_reports, family_batch_paths = _collect_batch_reports(
        portfolio_payload=portfolio_payload,
        portfolio_batch_json_path=paths["portfolio_batch_json_path"],
        portfolio_root=paths["portfolio_root"],
    )
    runtime_submission_payload = _read_json_object(paths["runtime_submission_json_path"])
    runtime_writeback_depth_payload = _read_json_object(paths["runtime_writeback_depth_json_path"])
    multi_project_runtime_writeback_payload = _read_json_object(
        paths["multi_project_runtime_writeback_json_path"]
    )
    solver_family_breadth_payload = _read_json_object(paths["solver_family_breadth_json_path"])
    local_runtime_scenario_depth_payload = _read_json_object(
        paths["local_runtime_scenario_depth_json_path"]
    )
    release_registry_payload = _read_json_object(paths["release_registry_json_path"])
    committee_summary_payload = _read_json_object(paths["committee_summary_json_path"])
    release_gap_payload = _read_json_object(paths["release_gap_report_json_path"])
    latest_snapshot_payload, latest_snapshot_path = _resolve_latest_release_snapshot(
        paths["release_root"],
        paths["snapshot_manifest_glob"],
    )

    project_rows = _build_project_rows(
        portfolio_payload=portfolio_payload,
        registry_index_payload=registry_index_payload,
    )
    family_rows = _build_family_rows(
        portfolio_payload=portfolio_payload,
        registry_index_payload=registry_index_payload,
        project_rows=project_rows,
    )
    portfolio_rows = _build_portfolio_rows(
        portfolio_payload=portfolio_payload,
        project_rows=project_rows,
        family_rows=family_rows,
    )
    submission_rows = _build_submission_rows(
        portfolio_payload=portfolio_payload,
        runtime_submission_payload=runtime_submission_payload,
    )
    runtime_submissions = _build_runtime_submission_surface(
        runtime_submission_payload=runtime_submission_payload,
        runtime_submission_json_path=paths["runtime_submission_json_path"],
        submission_rows=submission_rows,
    )
    runtime_writeback_depth_summary = _dict(runtime_writeback_depth_payload.get("summary"))
    runtime_writeback_depth_rows = _rows(runtime_writeback_depth_payload, "family_rows")
    multi_project_runtime_writeback_summary = _dict(
        multi_project_runtime_writeback_payload.get("summary")
    )
    multi_project_runtime_writeback_project_rows = _rows(
        multi_project_runtime_writeback_payload,
        "project_rows",
    )
    multi_project_runtime_writeback_project_family_rows = _rows(
        multi_project_runtime_writeback_payload,
        "project_family_rows",
    )
    solver_family_breadth_summary = _dict(solver_family_breadth_payload.get("summary"))
    solver_family_breadth_rows = _rows(solver_family_breadth_payload, "family_rows")
    local_runtime_scenario_depth_summary = _dict(local_runtime_scenario_depth_payload.get("summary"))
    local_runtime_scenario_depth_rows = _rows(local_runtime_scenario_depth_payload, "family_rows")
    endpoint_rows = _build_endpoint_rows()

    portfolio_summary = _dict(portfolio_payload.get("summary"))
    primary_batch_summary = _dict(primary_batch_payload.get("summary"))
    effective_batch_job_count = _coalesce_batch_count(
        primary_batch_summary,
        "job_count",
        sum(_coerce_int(row.get("job_count", 0)) for row in family_batch_reports),
    )
    effective_batch_snapshot_count = _coalesce_batch_count(
        primary_batch_summary,
        "snapshot_count",
        sum(_coerce_int(row.get("snapshot_count", 0)) for row in family_batch_reports),
    )
    release_governance = _build_release_governance(
        release_registry_payload=release_registry_payload,
        committee_summary_payload=committee_summary_payload,
        release_gap_payload=release_gap_payload,
        latest_snapshot_payload=latest_snapshot_payload,
        latest_snapshot_path=latest_snapshot_path,
    )

    health_checks = {
        "portfolio_available_pass": bool(portfolio_payload),
        "registry_index_available_pass": bool(registry_index_payload),
        "project_rows_present_pass": bool(project_rows),
        "primary_batch_report_available_pass": bool(primary_batch_payload) or bool(family_batch_reports),
        "runtime_writeback_depth_available_pass": bool(runtime_writeback_depth_payload),
        "multi_project_runtime_writeback_available_pass": bool(multi_project_runtime_writeback_payload),
        "solver_family_breadth_available_pass": bool(solver_family_breadth_payload),
        "local_runtime_scenario_depth_available_pass": bool(local_runtime_scenario_depth_payload),
        "release_registry_available_pass": bool(release_registry_payload),
        "release_registry_signature_verified_pass": bool(
            release_governance["release_registry"]["signature_verified"]
        ),
        "release_gap_report_available_pass": bool(release_gap_payload),
        "latest_release_snapshot_available_pass": bool(latest_snapshot_payload),
    }
    missing_inputs = [
        name
        for name, passed in health_checks.items()
        if not passed
    ]

    ready_family_count = sum(1 for row in family_rows if _text(row.get("commercialization_status")) == "ready")
    family_track_count = _first_int(
        portfolio_summary.get("family_track_count"),
        portfolio_summary.get("family_count"),
        len(family_rows),
    )
    family_identities = {
        _family_identity(row)
        for row in family_rows
        if _family_identity(row)[1]
    }
    ready_family_identities = {
        _family_identity(row)
        for row in family_rows
        if _family_identity(row)[1] and _text(row.get("commercialization_status")) == "ready"
    }
    runtime_ready_family_identities = {
        _family_identity(row)
        for row in submission_rows
        if _family_identity(row)[1] and _first_bool(row.get("runtime_ready"), row.get("release_ready"))
    }
    if not runtime_ready_family_identities:
        runtime_ready_family_identities = {
            _family_identity(row)
            for row in family_rows
            if _family_identity(row)[1] and _first_bool(row.get("runtime_ready"))
        }
    writeback_ready_family_identities = {
        _family_identity(row)
        for row in submission_rows
        if _family_identity(row)[1] and _first_bool(row.get("writeback_ready"))
    }
    if not writeback_ready_family_identities:
        writeback_ready_family_identities = {
            _family_identity(row)
            for row in family_rows
            if _family_identity(row)[1] and _first_bool(row.get("registry_ready"), row.get("signature_verified"))
        }
    full_ready_family_identities = {
        _family_identity(row)
        for row in submission_rows
        if _family_identity(row)[1]
        and _first_bool(row.get("runtime_ready"), row.get("release_ready"))
        and _first_bool(row.get("writeback_ready"))
    }
    if not full_ready_family_identities:
        full_ready_family_identities = {
            _family_identity(row)
            for row in family_rows
            if _family_identity(row)[1]
            and _first_bool(row.get("runtime_ready"))
            and _first_bool(row.get("registry_ready"), row.get("signature_verified"))
        }
    runtime_ready_family_count = _first_int(
        portfolio_summary.get("runtime_ready_family_count"),
        runtime_submissions["summary"].get("runtime_ready_count"),
        len(runtime_ready_family_identities),
    )
    writeback_ready_family_count = _first_int(
        portfolio_summary.get("writeback_ready_family_count"),
        runtime_submissions["summary"].get("writeback_ready_count"),
        len(writeback_ready_family_identities),
    )
    full_ready_family_count = _first_int(
        portfolio_summary.get("full_lane_ready_family_count"),
        runtime_submissions["summary"].get("full_ready_count"),
        len(full_ready_family_identities),
    )
    aligned_ready_family_identities = (
        ready_family_identities & runtime_ready_family_identities & writeback_ready_family_identities & full_ready_family_identities
    )
    alignment_pass = (
        ready_family_identities == runtime_ready_family_identities
        == writeback_ready_family_identities
        == full_ready_family_identities
    )
    alignment_count = len(aligned_ready_family_identities)
    ready_family_label = f"{ready_family_count}/{max(len(family_identities), family_track_count, 1)} ready families"
    runtime_ready_family_label = (
        f"{runtime_ready_family_count}/{max(len(family_identities), family_track_count, 1)} runtime-ready families"
    )
    writeback_ready_submission_count = _first_int(
        runtime_submissions["summary"].get("writeback_ready_count"),
    )
    writeback_ready_submission_label = (
        f"{writeback_ready_submission_count}/"
        f"{max(_first_int(runtime_submissions['summary'].get('submission_count'), len(submission_rows)), 1)} "
        "writeback-ready submissions"
    )
    if ready_family_count > 0:
        alignment_label = (
            f"{'PASS' if alignment_pass else 'CHECK'} "
            f"{alignment_count}/{ready_family_count} ready families aligned"
        )
    else:
        alignment_label = f"{'PASS' if alignment_pass else 'CHECK'} 0 ready families aligned"
    alignment_evidence = (
        f"ready_families={ready_family_count}/{max(len(family_identities), family_track_count, 1)} | "
        f"runtime_ready_families={runtime_ready_family_count} | "
        f"writeback_ready_families={writeback_ready_family_count} | "
        f"writeback_ready_submissions={writeback_ready_submission_count} | "
        f"full_ready_families={full_ready_family_count}"
    )
    runtime_writeback_depth_ready = _first_bool(
        runtime_writeback_depth_summary.get("runtime_writeback_depth_ready"),
        runtime_writeback_depth_payload.get("contract_pass"),
        default=False,
    )
    runtime_writeback_depth_family_count = _first_int(
        runtime_writeback_depth_summary.get("family_count"),
        len(runtime_writeback_depth_rows),
    )
    runtime_writeback_depth_full_count = _first_int(
        runtime_writeback_depth_summary.get("depth_ready_family_count"),
    )
    runtime_writeback_depth_targeted_count = _first_int(
        runtime_writeback_depth_summary.get("targeted_family_count"),
    )
    runtime_writeback_depth_signature_count = _first_int(
        runtime_writeback_depth_summary.get("signature_verified_family_count"),
    )
    runtime_writeback_depth_repro_count = _first_int(
        runtime_writeback_depth_summary.get("package_reproducible_family_count"),
    )
    runtime_writeback_depth_snapshot_count = _first_int(
        runtime_writeback_depth_summary.get("snapshot_ready_family_count"),
    )
    runtime_writeback_depth_queue_clear_count = _first_int(
        runtime_writeback_depth_summary.get("queue_clear_family_count"),
    )
    runtime_writeback_depth_summary_line = _first_text(
        runtime_writeback_depth_payload.get("summary_line")
    )
    runtime_writeback_depth_status_label = _first_text(
        runtime_writeback_depth_summary.get("family_status_label"),
        ", ".join(
            f"{_text(row.get('family_id'))}:{_text(row.get('runtime_writeback_depth_status'))}"
            for row in runtime_writeback_depth_rows
            if _text(row.get("family_id"))
        ),
    )
    multi_project_runtime_writeback_ready = _first_bool(
        multi_project_runtime_writeback_summary.get("multi_project_runtime_writeback_ready"),
        multi_project_runtime_writeback_payload.get("contract_pass"),
        default=False,
    )
    multi_project_runtime_writeback_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("project_count"),
        len(multi_project_runtime_writeback_project_rows),
    )
    multi_project_runtime_writeback_project_family_count = _first_int(
        multi_project_runtime_writeback_summary.get("project_family_count"),
        len(multi_project_runtime_writeback_project_family_rows),
    )
    multi_project_runtime_writeback_full_count = _first_int(
        multi_project_runtime_writeback_summary.get("full_depth_project_family_count"),
    )
    multi_project_runtime_writeback_targeted_count = _first_int(
        multi_project_runtime_writeback_summary.get("targeted_project_family_count"),
    )
    multi_project_runtime_writeback_ready_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("ready_project_count"),
    )
    multi_project_runtime_writeback_signature_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("signature_verified_project_count"),
    )
    multi_project_runtime_writeback_repro_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("package_reproducible_project_count"),
    )
    multi_project_runtime_writeback_snapshot_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("snapshot_ready_project_count"),
    )
    multi_project_runtime_writeback_queue_clear_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("queue_clear_project_count"),
    )
    multi_project_runtime_writeback_summary_line = _first_text(
        multi_project_runtime_writeback_payload.get("summary_line")
    )
    multi_project_runtime_writeback_status_label = _first_text(
        multi_project_runtime_writeback_summary.get("project_status_label"),
        ", ".join(
            f"{_text(row.get('project_id'))}:{_text(row.get('project_status'))}"
            for row in multi_project_runtime_writeback_project_rows
            if _text(row.get("project_id"))
        ),
    )
    solver_family_breadth_ready = _first_bool(
        solver_family_breadth_summary.get("solver_family_breadth_ready"),
        solver_family_breadth_payload.get("contract_pass"),
        default=False,
    )
    solver_family_breadth_family_count = _first_int(
        solver_family_breadth_summary.get("family_count"),
        len(solver_family_breadth_rows),
    )
    solver_family_breadth_broad_ready_count = _first_int(
        solver_family_breadth_summary.get("broad_ready_family_count"),
    )
    solver_family_breadth_full_count = _first_int(
        solver_family_breadth_summary.get("full_breadth_family_count"),
    )
    solver_family_breadth_mesh_broad_count = _first_int(
        solver_family_breadth_summary.get("mesh_broad_family_count"),
    )
    solver_family_breadth_member_multi_count = _first_int(
        solver_family_breadth_summary.get("member_multi_family_count"),
    )
    solver_family_breadth_summary_line = _first_text(solver_family_breadth_payload.get("summary_line"))
    solver_family_breadth_status_label = _first_text(
        solver_family_breadth_summary.get("family_status_label"),
        ", ".join(
            f"{_text(row.get('family_id'))}:{_text(row.get('solver_family_breadth_status'))}"
            for row in solver_family_breadth_rows
            if _text(row.get("family_id"))
        ),
    )
    local_runtime_scenario_depth_ready = _first_bool(
        local_runtime_scenario_depth_summary.get("local_runtime_scenario_depth_ready"),
        local_runtime_scenario_depth_payload.get("contract_pass"),
        default=False,
    )
    local_runtime_scenario_depth_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("family_count"),
        len(local_runtime_scenario_depth_rows),
    )
    local_runtime_scenario_depth_ready_count = _first_int(
        local_runtime_scenario_depth_summary.get("depth_ready_family_count"),
    )
    local_runtime_scenario_trace_ready_count = _first_int(
        local_runtime_scenario_depth_summary.get("trace_ready_family_count"),
    )
    local_runtime_scenario_mesh_ready_count = _first_int(
        local_runtime_scenario_depth_summary.get("mesh_trace_ready_family_count"),
    )
    local_runtime_scenario_runtime_ready_count = _first_int(
        local_runtime_scenario_depth_summary.get("runtime_ready_family_count"),
    )
    local_runtime_scenario_omitted_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("omitted_library_family_count"),
    )
    local_runtime_scenario_depth_summary_line = _first_text(
        local_runtime_scenario_depth_payload.get("summary_line")
    )
    local_runtime_scenario_depth_status_label = _first_text(
        local_runtime_scenario_depth_summary.get("family_status_label"),
        ", ".join(
            f"{_text(row.get('family_id'))}:{_text(row.get('local_runtime_scenario_depth_status'))}"
            for row in local_runtime_scenario_depth_rows
            if _text(row.get("family_id"))
        ),
    )
    signature_verified_count = sum(1 for row in project_rows if _coerce_bool(row.get("registry_signature_verified", False)))
    package_reproducible_count = sum(1 for row in project_rows if _coerce_bool(row.get("package_reproducible", False)))
    contract_pass = bool(project_rows and all(health_checks.values()))
    reason_code = "PASS" if contract_pass else ("CHECK" if project_rows or family_rows or portfolio_rows else "ERR_INPUT")

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-project-ops-service-snapshot",
        "generated_at": timestamp,
        "inputs": {
            "release_root": str(paths["release_root"]),
            "portfolio_json_path": str(paths["portfolio_json_path"]),
            "registry_index_json_path": str(paths["registry_index_json_path"]),
            "portfolio_batch_json_path": str(paths["portfolio_batch_json_path"]),
            "runtime_submission_json_path": str(paths["runtime_submission_json_path"]),
            "runtime_writeback_depth_json_path": str(paths["runtime_writeback_depth_json_path"]),
            "multi_project_runtime_writeback_json_path": str(
                paths["multi_project_runtime_writeback_json_path"]
            ),
            "solver_family_breadth_json_path": str(paths["solver_family_breadth_json_path"]),
            "local_runtime_scenario_depth_json_path": str(
                paths["local_runtime_scenario_depth_json_path"]
            ),
            "release_registry_json_path": str(paths["release_registry_json_path"]),
            "committee_summary_json_path": str(paths["committee_summary_json_path"]),
            "release_gap_report_json_path": str(paths["release_gap_report_json_path"]),
            "snapshot_manifest_glob": str(paths["snapshot_manifest_glob"]),
            "project_registry_paths": [str(path) for path in registry_paths],
            "project_registry_dirs": [str(path) for path in registry_dirs],
        },
        "health": {
            "status": "ok" if contract_pass else ("degraded" if reason_code == "CHECK" else "missing"),
            "checks": health_checks,
            "missing_inputs": missing_inputs,
        },
        "summary": {
            "project_count": len(project_rows),
            "family_count": len(family_rows),
            "portfolio_count": len(portfolio_rows),
            "complete_project_count": sum(
                1 for row in project_rows if _coerce_bool(row.get("registry_contract_pass", False))
            ),
            "ready_family_count": ready_family_count,
            "ready_family_label": ready_family_label,
            "family_track_count": family_track_count,
            "runtime_ready_family_count": runtime_ready_family_count,
            "runtime_ready_family_label": runtime_ready_family_label,
            "writeback_ready_family_count": writeback_ready_family_count,
            "full_ready_family_count": full_ready_family_count,
            "registry_signature_verified_count": signature_verified_count,
            "registry_package_reproducible_count": package_reproducible_count,
            "batch_job_count": effective_batch_job_count,
            "batch_snapshot_count": effective_batch_snapshot_count,
            "family_batch_report_count": len(family_batch_reports),
            "submission_count": _first_int(
                runtime_submissions["summary"].get("submission_count"),
                len(submission_rows),
            ),
            "ready_submission_count": _first_int(
                runtime_submissions["summary"].get("ready_submission_count"),
            ),
            "writeback_ready_submission_count": writeback_ready_submission_count,
            "writeback_ready_submission_label": writeback_ready_submission_label,
            "queued_submission_count": _first_int(
                runtime_submissions["summary"].get("queue_count"),
            ),
            "runtime_writeback_depth_ready": runtime_writeback_depth_ready,
            "runtime_writeback_depth_family_count": runtime_writeback_depth_family_count,
            "runtime_writeback_depth_full_count": runtime_writeback_depth_full_count,
            "runtime_writeback_depth_targeted_count": runtime_writeback_depth_targeted_count,
            "runtime_writeback_depth_signature_count": runtime_writeback_depth_signature_count,
            "runtime_writeback_depth_repro_count": runtime_writeback_depth_repro_count,
            "runtime_writeback_depth_snapshot_count": runtime_writeback_depth_snapshot_count,
            "runtime_writeback_depth_queue_clear_count": runtime_writeback_depth_queue_clear_count,
            "runtime_writeback_depth_status_label": runtime_writeback_depth_status_label,
            "runtime_writeback_depth_summary_line": runtime_writeback_depth_summary_line,
            "multi_project_runtime_writeback_ready": multi_project_runtime_writeback_ready,
            "multi_project_runtime_writeback_project_count": multi_project_runtime_writeback_project_count,
            "multi_project_runtime_writeback_project_family_count": multi_project_runtime_writeback_project_family_count,
            "multi_project_runtime_writeback_full_count": multi_project_runtime_writeback_full_count,
            "multi_project_runtime_writeback_targeted_count": multi_project_runtime_writeback_targeted_count,
            "multi_project_runtime_writeback_ready_project_count": multi_project_runtime_writeback_ready_project_count,
            "multi_project_runtime_writeback_signature_project_count": multi_project_runtime_writeback_signature_project_count,
            "multi_project_runtime_writeback_repro_project_count": multi_project_runtime_writeback_repro_project_count,
            "multi_project_runtime_writeback_snapshot_project_count": multi_project_runtime_writeback_snapshot_project_count,
            "multi_project_runtime_writeback_queue_clear_project_count": multi_project_runtime_writeback_queue_clear_project_count,
            "multi_project_runtime_writeback_status_label": multi_project_runtime_writeback_status_label,
            "multi_project_runtime_writeback_summary_line": multi_project_runtime_writeback_summary_line,
            "solver_family_breadth_ready": solver_family_breadth_ready,
            "solver_family_breadth_family_count": solver_family_breadth_family_count,
            "solver_family_breadth_broad_ready_count": solver_family_breadth_broad_ready_count,
            "solver_family_breadth_full_count": solver_family_breadth_full_count,
            "solver_family_breadth_mesh_broad_count": solver_family_breadth_mesh_broad_count,
            "solver_family_breadth_member_multi_count": solver_family_breadth_member_multi_count,
            "solver_family_breadth_status_label": solver_family_breadth_status_label,
            "solver_family_breadth_summary_line": solver_family_breadth_summary_line,
            "local_runtime_scenario_depth_ready": local_runtime_scenario_depth_ready,
            "local_runtime_scenario_depth_family_count": local_runtime_scenario_depth_family_count,
            "local_runtime_scenario_depth_ready_count": local_runtime_scenario_depth_ready_count,
            "local_runtime_scenario_trace_ready_count": local_runtime_scenario_trace_ready_count,
            "local_runtime_scenario_mesh_ready_count": local_runtime_scenario_mesh_ready_count,
            "local_runtime_scenario_runtime_ready_count": local_runtime_scenario_runtime_ready_count,
            "local_runtime_scenario_omitted_family_count": local_runtime_scenario_omitted_family_count,
            "local_runtime_scenario_depth_status_label": local_runtime_scenario_depth_status_label,
            "local_runtime_scenario_depth_summary_line": local_runtime_scenario_depth_summary_line,
            "family_runtime_writeback_alignment_pass": alignment_pass,
            "family_runtime_writeback_alignment_count": alignment_count,
            "family_runtime_writeback_alignment_label": alignment_label,
            "family_runtime_writeback_alignment_evidence": alignment_evidence,
            "service_ready": contract_pass,
            "endpoint_count": len(endpoint_rows),
            "release_registry_pass": _coerce_bool(release_governance["release_registry"]["contract_pass"]),
            "release_candidate_pass": _coerce_bool(release_governance["release_gap_report"]["release_candidate_pass"]),
            "commercial_grade": _text(release_governance["release_gap_report"]["commercial_grade"]),
            "latest_release_snapshot": _text(release_governance["latest_release_snapshot"]["snapshot"]),
            "latest_release_snapshot_generated_at": _text(
                release_governance["latest_release_snapshot"]["generated_at"]
            ),
        },
        "projects": project_rows,
        "project_rows": project_rows,
        "families": family_rows,
        "family_rows": family_rows,
        "portfolios": portfolio_rows,
        "portfolio_rows": portfolio_rows,
        "submissions": submission_rows,
        "submission_rows": submission_rows,
        "runtime_submissions": runtime_submissions,
        "endpoint_rows": endpoint_rows,
        "batch": {
            "primary_report_path": str(paths["portfolio_batch_json_path"]) if primary_batch_payload else "",
            "primary_summary": {
                "job_count": _coalesce_batch_count(primary_batch_summary, "job_count", effective_batch_job_count),
                "snapshot_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "snapshot_count",
                    effective_batch_snapshot_count,
                ),
                "completed_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "completed_count",
                    sum(_coerce_int(row.get("completed_count", 0)) for row in family_batch_reports),
                ),
                "failed_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "failed_count",
                    sum(_coerce_int(row.get("failed_count", 0)) for row in family_batch_reports),
                ),
                "planned_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "planned_count",
                    sum(_coerce_int(row.get("planned_count", 0)) for row in family_batch_reports),
                ),
                "blocked_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "blocked_count",
                    sum(_coerce_int(row.get("blocked_count", 0)) for row in family_batch_reports),
                ),
                "rerun_requested_count": _coalesce_batch_count(
                    primary_batch_summary,
                    "rerun_requested_count",
                    sum(_coerce_int(row.get("rerun_requested_count", 0)) for row in family_batch_reports),
                ),
                "contract_pass": _coerce_bool(primary_batch_payload.get("contract_pass", False)),
            },
            "family_reports": family_batch_reports,
        },
        "release_governance": release_governance,
        "artifacts": {
            "portfolio_json": str(paths["portfolio_json_path"]) if portfolio_payload else "",
            "registry_index_json": str(paths["registry_index_json_path"]) if registry_index_payload else "",
            "portfolio_batch_json": str(paths["portfolio_batch_json_path"]) if primary_batch_payload else "",
            "runtime_submission_json": (
                str(paths["runtime_submission_json_path"]) if runtime_submission_payload else ""
            ),
            "native_authoring_runtime_submission_lane_json": (
                str(paths["runtime_submission_json_path"]) if runtime_submission_payload else ""
            ),
            "native_authoring_runtime_writeback_depth_report_json": (
                str(paths["runtime_writeback_depth_json_path"]) if runtime_writeback_depth_payload else ""
            ),
            "native_authoring_multi_project_runtime_writeback_report_json": (
                str(paths["multi_project_runtime_writeback_json_path"])
                if multi_project_runtime_writeback_payload
                else ""
            ),
            "native_authoring_solver_family_breadth_report_json": (
                str(paths["solver_family_breadth_json_path"]) if solver_family_breadth_payload else ""
            ),
            "native_authoring_local_runtime_scenario_depth_report_json": (
                str(paths["local_runtime_scenario_depth_json_path"])
                if local_runtime_scenario_depth_payload
                else ""
            ),
            "family_batch_report_jsons": [str(path) for path in family_batch_paths],
            "release_registry_json": str(paths["release_registry_json_path"]) if release_registry_payload else "",
            "committee_summary_json": str(paths["committee_summary_json_path"]) if committee_summary_payload else "",
            "release_gap_report_json": str(paths["release_gap_report_json_path"]) if release_gap_payload else "",
            "latest_release_snapshot_manifest_json": _path_text(latest_snapshot_path),
            "project_ops_service_snapshot_json": "",
        },
        "paths": {
            "snapshot_json": "",
        },
        "summary_line": (
            "Project ops service snapshot: "
            f"{reason_code} | projects={len(project_rows)} | families={len(family_rows)} | "
            f"portfolios={len(portfolio_rows)} | submissions={len(submission_rows)} | "
            f"runtime_writeback_depth={runtime_writeback_depth_full_count}/{max(runtime_writeback_depth_family_count, 1)} | "
            f"multi_project_runtime={multi_project_runtime_writeback_ready_project_count}/{max(multi_project_runtime_writeback_project_count, 1)} | "
            f"solver_family_breadth={solver_family_breadth_broad_ready_count}/{max(solver_family_breadth_family_count, 1)} | "
            f"local_runtime_depth={local_runtime_scenario_depth_ready_count}/{max(local_runtime_scenario_depth_family_count, 1)} | "
            f"batch_jobs={effective_batch_job_count} | "
            f"release_candidate={_coerce_bool(release_governance['release_gap_report']['release_candidate_pass'])} | "
            f"snapshot={_text(release_governance['latest_release_snapshot']['snapshot']) or 'n/a'}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    return payload


def write_project_ops_snapshot(out: Path, **kwargs: Any) -> dict[str, Any]:
    payload = build_project_ops_snapshot(**kwargs)
    payload["artifacts"]["project_ops_service_snapshot_json"] = str(out)
    payload["paths"]["snapshot_json"] = str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


class ProjectOpsHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that rebuilds the snapshot on each request."""

    def __init__(self, server_address: tuple[str, int], config: ProjectOpsServiceConfig) -> None:
        super().__init__(server_address, ProjectOpsRequestHandler)
        self.config = config
        self._audit_lock = threading.Lock()
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_hits: dict[str, list[float]] = {}

    def build_snapshot(self) -> dict[str, Any]:
        return build_project_ops_snapshot(
            release_root=self.config.release_root,
            portfolio_json_path=self.config.portfolio_json_path,
            registry_index_json_path=self.config.registry_index_json_path,
            portfolio_batch_json_path=self.config.portfolio_batch_json_path,
            runtime_submission_json_path=self.config.runtime_submission_json_path,
            runtime_writeback_depth_json_path=self.config.runtime_writeback_depth_json_path,
            multi_project_runtime_writeback_json_path=self.config.multi_project_runtime_writeback_json_path,
            solver_family_breadth_json_path=self.config.solver_family_breadth_json_path,
            local_runtime_scenario_depth_json_path=self.config.local_runtime_scenario_depth_json_path,
            release_registry_json_path=self.config.release_registry_json_path,
            committee_summary_json_path=self.config.committee_summary_json_path,
            release_gap_report_json_path=self.config.release_gap_report_json_path,
            snapshot_manifest_glob=self.config.snapshot_manifest_glob,
            project_registry_paths=[Path(item) for item in self.config.project_registry_paths],
            project_registry_dirs=[Path(item) for item in self.config.project_registry_dirs],
        )

    def write_audit_event(
        self,
        *,
        status: HTTPStatus,
        path: str,
        context: dict[str, Any] | None,
    ) -> None:
        if self.config.audit_log_path is None:
            return
        event = {
            "event_id": hashlib.sha256(
                f"{time.time_ns()}|{path}|{status.value}".encode("utf-8")
            ).hexdigest()[:16],
            "timestamp": _now_utc_iso(),
            "tenant_id": _text((context or {}).get("tenant_id")) or "unknown",
            "actor_id": _text((context or {}).get("actor_id")) or "unknown",
            "request_id": _text((context or {}).get("request_id")) or "unknown",
            "roles": sorted((context or {}).get("roles", [])),
            "method": "GET",
            "path": urlsplit(path).path,
            "status": int(status),
            "token_redacted": True,
        }
        with self._audit_lock:
            self.config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config.audit_log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            self._write_audit_digest_unlocked()

    def audit_digest_path(self) -> Path | None:
        if self.config.audit_digest_path is not None:
            return self.config.audit_digest_path
        if self.config.audit_log_path is None:
            return None
        return self.config.audit_log_path.with_name(f"{self.config.audit_log_path.name}.digest.json")

    def write_audit_digest(self) -> dict[str, Any]:
        with self._audit_lock:
            return self._write_audit_digest_unlocked()

    def _write_audit_digest_unlocked(self) -> dict[str, Any]:
        audit_path = self.config.audit_log_path
        digest_path = self.audit_digest_path()
        if not self.config.audit_digest_enabled or audit_path is None or digest_path is None:
            return {"available": False, "reason": "audit_digest_disabled_or_unconfigured"}
        if not audit_path.exists():
            return {"available": False, "reason": "audit_log_missing", "audit_log_path": str(audit_path)}
        audit_bytes = audit_path.read_bytes()
        lines = [line for line in audit_bytes.splitlines() if line.strip()]
        last_event_id = ""
        last_timestamp = ""
        if lines:
            try:
                last_event = json.loads(lines[-1].decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                last_event = {}
            if isinstance(last_event, dict):
                last_event_id = _text(last_event.get("event_id"))
                last_timestamp = _text(last_event.get("timestamp"))
        payload = {
            "schema_version": "project-ops-audit-digest.v1",
            "generated_at": _now_utc_iso(),
            "available": True,
            "audit_log_path": str(audit_path),
            "audit_digest_path": str(digest_path),
            "audit_log_sha256": hashlib.sha256(audit_bytes).hexdigest(),
            "event_count": len(lines),
            "last_event_id": last_event_id,
            "last_event_timestamp": last_timestamp,
            "retention_days": max(0, int(self.config.audit_retention_days)),
            "export_max_events": max(1, int(self.config.audit_export_max_events)),
            "tamper_evidence": "sha256_batch_digest",
        }
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def check_rate_limit(self, context: dict[str, Any]) -> tuple[bool, int]:
        window_seconds = max(0, int(self.config.rate_limit_window_seconds))
        max_requests = max(0, int(self.config.rate_limit_max_requests))
        if window_seconds <= 0 or max_requests <= 0:
            return True, 0
        now = time.monotonic()
        cutoff = now - window_seconds
        key = "|".join(
            [
                _text(context.get("tenant_id")) or "unknown",
                _text(context.get("actor_id")) or "unknown",
            ]
        )
        with self._rate_limit_lock:
            hits = [timestamp for timestamp in self._rate_limit_hits.get(key, []) if timestamp > cutoff]
            if len(hits) >= max_requests:
                oldest = min(hits)
                retry_after = max(1, int((oldest + window_seconds) - now) + 1)
                self._rate_limit_hits[key] = hits
                return False, retry_after
            hits.append(now)
            self._rate_limit_hits[key] = hits
        return True, 0

    def ops_policy_manifest(self) -> dict[str, Any]:
        audit_digest_path = self.audit_digest_path()
        return {
            "schema_version": "project-ops-policy.v1",
            "generated_at": _now_utc_iso(),
            "service": "phase1-project-ops-api-service",
            "auth": {
                "auth_required": bool(self.config.auth_required),
                "allowed_tenants": list(self.config.allowed_tenants),
                "token": "bearer_hs256_jwt",
                "required_headers": ["Authorization", "X-Tenant-ID", "X-Actor-ID", "X-Request-ID"],
            },
            "rate_limit": {
                "enabled": self.config.rate_limit_window_seconds > 0 and self.config.rate_limit_max_requests > 0,
                "key_scope": "tenant_id+actor_id",
                "window_seconds": max(0, int(self.config.rate_limit_window_seconds)),
                "max_requests": max(0, int(self.config.rate_limit_max_requests)),
            },
            "request_limits": {
                "metadata_byte_limit": max(0, int(self.config.request_metadata_byte_limit)),
                "methods": ["GET"],
                "request_body_policy": "no_request_body_accepted",
            },
            "audit": {
                "audit_log_path": str(self.config.audit_log_path or ""),
                "audit_digest_path": str(audit_digest_path or ""),
                "digest_enabled": bool(self.config.audit_digest_enabled),
                "tamper_evidence": "sha256_batch_digest",
                "retention_days": max(0, int(self.config.audit_retention_days)),
                "export_max_events": max(1, int(self.config.audit_export_max_events)),
            },
            "storage_lifecycle": {
                "backup_policy": _text(self.config.backup_policy),
                "tenant_delete_policy": _text(self.config.tenant_delete_policy),
                "restore_policy": "operator_verified_restore_required",
                "export_policy": "tenant_scoped_admin_export",
            },
            "telemetry": {
                "enabled": bool(self.config.telemetry_enabled),
                "default": "off",
            },
            "incident_response": {
                "support_bundle": "redacted_support_bundle_roundtrip_required",
                "audit_trace": "audit_log_and_digest_required",
                "rollback": "disable_token_or_gateway_route_then_restore_snapshot",
            },
        }


class ProjectOpsRequestHandler(BaseHTTPRequestHandler):
    """JSON-only request handler for the local project ops service."""

    server_version = "ProjectOpsAPI/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        server = self.server
        if not isinstance(server, ProjectOpsHTTPServer):  # pragma: no cover
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "server_misconfigured"})
            return

        request_metadata_bytes = self._request_metadata_bytes()
        metadata_limit = max(0, int(server.config.request_metadata_byte_limit))
        if metadata_limit and request_metadata_bytes > metadata_limit:
            self._auth_context = {
                "tenant_id": _text(self.headers.get("X-Tenant-ID")) or "unknown",
                "actor_id": _text(self.headers.get("X-Actor-ID")) or "unknown",
                "request_id": _text(self.headers.get("X-Request-ID")) or "unknown",
                "roles": set(),
            }
            self._write_json(
                HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                {
                    "error": "request_metadata_too_large",
                    "request_metadata_bytes": request_metadata_bytes,
                    "request_metadata_byte_limit": metadata_limit,
                },
            )
            return

        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        auth_context = self._authenticate(path)
        self._auth_context = auth_context
        if auth_context.get("error"):
            self._write_json(
                auth_context["status"],
                {
                    "error": auth_context["error"],
                    "reason": auth_context["reason"],
                },
            )
            return

        rate_limit_ok, retry_after_seconds = server.check_rate_limit(auth_context)
        if not rate_limit_ok:
            self._write_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {
                    "error": "rate_limited",
                    "retry_after_seconds": retry_after_seconds,
                    "rate_limit": {
                        "window_seconds": max(0, int(server.config.rate_limit_window_seconds)),
                        "max_requests": max(0, int(server.config.rate_limit_max_requests)),
                        "key_scope": "tenant_id+actor_id",
                    },
                },
            )
            return

        snapshot = _filter_snapshot_for_tenant(server.build_snapshot(), auth_context["tenant_id"])

        if path == "/":
            self._write_json(
                HTTPStatus.OK,
                {
                    "service": "phase1-project-ops-api-service",
                    "generated_at": snapshot["generated_at"],
                    "summary_line": snapshot["summary_line"],
                    "endpoints": list(SERVICE_ENDPOINT_PATHS),
                    "tenant_id": auth_context["tenant_id"],
                },
            )
            return

        if path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "health": snapshot["health"],
                    "summary": snapshot["summary"],
                    "license": _load_license_status(server.config),
                    "telemetry": {"enabled": bool(server.config.telemetry_enabled)},
                    "contract_pass": snapshot["contract_pass"],
                    "reason_code": snapshot["reason_code"],
                    "summary_line": snapshot["summary_line"],
                },
            )
            return

        if path == "/summary":
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "summary": snapshot["summary"],
                    "tenant_id": auth_context["tenant_id"],
                    "batch": snapshot["batch"],
                    "runtime_submissions": snapshot["runtime_submissions"],
                    "release_governance": snapshot["release_governance"],
                    "endpoint_rows": snapshot["endpoint_rows"],
                    "artifacts": snapshot["artifacts"],
                    "contract_pass": snapshot["contract_pass"],
                    "reason_code": snapshot["reason_code"],
                    "summary_line": snapshot["summary_line"],
                },
            )
            return

        if path == "/audit/events":
            if "admin" not in auth_context["roles"]:
                self._write_json(HTTPStatus.FORBIDDEN, {"error": "insufficient_role", "required_role": "admin"})
                return
            audit_path = server.config.audit_log_path
            events: list[dict[str, Any]] = []
            if audit_path and audit_path.exists():
                export_max_events = max(1, int(server.config.audit_export_max_events))
                for line in audit_path.read_text(encoding="utf-8").splitlines()[-export_max_events:]:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and _text(row.get("tenant_id")) == auth_context["tenant_id"]:
                        events.append(row)
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": _now_utc_iso(),
                    "tenant_id": auth_context["tenant_id"],
                    "count": len(events),
                    "items": events,
                },
            )
            return

        if path == "/audit/digest":
            if "admin" not in auth_context["roles"]:
                self._write_json(HTTPStatus.FORBIDDEN, {"error": "insufficient_role", "required_role": "admin"})
                return
            digest = server.write_audit_digest()
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": _now_utc_iso(),
                    "tenant_id": auth_context["tenant_id"],
                    "audit_digest": digest,
                },
            )
            return

        if path == "/ops/policy":
            if not ({"admin", "operator"} & set(auth_context["roles"])):
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "insufficient_role", "required_role": "admin_or_operator"},
                )
                return
            self._write_json(HTTPStatus.OK, server.ops_policy_manifest())
            return

        if path == "/license":
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": _now_utc_iso(),
                    "tenant_id": auth_context["tenant_id"],
                    "license": _load_license_status(server.config),
                },
            )
            return

        if path == "/version":
            self._write_json(
                HTTPStatus.OK,
                {
                    "service": "phase1-project-ops-api-service",
                    "version": server.config.service_version,
                    "schema_version": "project-ops-api-service.version.v1",
                },
            )
            return

        if path == "/update-channel":
            self._write_json(
                HTTPStatus.OK,
                {
                    "schema_version": "project-ops-api-service.update-channel.v1",
                    "channel": server.config.update_channel,
                    "latest_version": server.config.service_version,
                    "mandatory": False,
                },
            )
            return

        if path == "/projects":
            items = list(snapshot["projects"])
            family_id = _decode_query(query, "family_id")
            portfolio_name = _decode_query(query, "portfolio_name")
            commercialization_status = _decode_query(query, "commercialization_status")
            if family_id:
                items = [row for row in items if _text(row.get("family_id")) == family_id]
            if portfolio_name:
                items = [row for row in items if _text(row.get("portfolio_name")) == portfolio_name]
            if commercialization_status:
                items = [
                    row
                    for row in items
                    if _text(row.get("commercialization_status")) == commercialization_status
                ]
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "count": len(items),
                    "items": items,
                },
            )
            return

        if path.startswith("/projects/"):
            project_id = unquote(path.split("/", 2)[2])
            project = next((row for row in snapshot["projects"] if _text(row.get("project_id")) == project_id), None)
            if project is None:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "project_not_found", "project_id": project_id})
                return
            self._write_json(HTTPStatus.OK, project)
            return

        if path == "/families":
            items = list(snapshot["families"])
            portfolio_name = _decode_query(query, "portfolio_name")
            commercialization_status = _decode_query(query, "commercialization_status")
            if portfolio_name:
                items = [row for row in items if _text(row.get("portfolio_name")) == portfolio_name]
            if commercialization_status:
                items = [
                    row
                    for row in items
                    if _text(row.get("commercialization_status")) == commercialization_status
                ]
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "count": len(items),
                    "items": items,
                },
            )
            return

        if path.startswith("/families/"):
            family_id = unquote(path.split("/", 2)[2])
            matches = [row for row in snapshot["families"] if _text(row.get("family_id")) == family_id]
            if not matches:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "family_not_found", "family_id": family_id})
                return
            if len(matches) == 1:
                self._write_json(HTTPStatus.OK, matches[0])
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "family_id": family_id,
                    "count": len(matches),
                    "items": matches,
                },
            )
            return

        if path == "/portfolios":
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "count": len(snapshot["portfolios"]),
                    "items": snapshot["portfolios"],
                },
            )
            return

        if path.startswith("/portfolios/"):
            portfolio_name = unquote(path.split("/", 2)[2])
            portfolio = next(
                (
                    row
                    for row in snapshot["portfolios"]
                    if _safe_label(_text(row.get("portfolio_name"))) == _safe_label(portfolio_name)
                ),
                None,
            )
            if portfolio is None:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "portfolio_not_found", "portfolio_name": portfolio_name},
                )
                return
            self._write_json(HTTPStatus.OK, portfolio)
            return

        if path == "/submissions":
            items = list(snapshot["submissions"])
            family_id = _decode_query(query, "family_id")
            portfolio_name = _decode_query(query, "portfolio_name")
            submission_status = _decode_query(query, "submission_status")
            runtime_ready = _decode_bool_query(query, "runtime_ready")
            writeback_ready = _decode_bool_query(query, "writeback_ready")
            if family_id:
                items = [row for row in items if _text(row.get("family_id")) == family_id]
            if portfolio_name:
                items = [row for row in items if _text(row.get("portfolio_name")) == portfolio_name]
            if submission_status:
                items = [
                    row
                    for row in items
                    if _text(row.get("submission_status")).lower() == submission_status.lower()
                ]
            if runtime_ready is not None:
                items = [row for row in items if _first_bool(row.get("runtime_ready")) == runtime_ready]
            if writeback_ready is not None:
                items = [row for row in items if _first_bool(row.get("writeback_ready")) == writeback_ready]
            self._write_json(
                HTTPStatus.OK,
                {
                    "generated_at": snapshot["generated_at"],
                    "count": len(items),
                    "items": items,
                },
            )
            return

        if path.startswith("/submissions/"):
            family_id = unquote(path.split("/", 2)[2])
            matches = [row for row in snapshot["submissions"] if _text(row.get("family_id")) == family_id]
            if not matches:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "submission_not_found", "family_id": family_id},
                )
                return
            if len(matches) == 1:
                self._write_json(HTTPStatus.OK, matches[0])
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "family_id": family_id,
                    "count": len(matches),
                    "ready_submission_count": sum(
                        1 for row in matches if _first_bool(row.get("runtime_ready"), row.get("release_ready"))
                    ),
                    "writeback_ready_count": sum(1 for row in matches if _first_bool(row.get("writeback_ready"))),
                    "queue_count": sum(
                        1
                        for row in matches
                        if _text(row.get("submission_status")).lower() in {"queued", "pending", "submitted", "open"}
                    ),
                    "items": matches,
                },
            )
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "route_not_found", "path": path})

    def _request_metadata_bytes(self) -> int:
        total = len(self.requestline.encode("utf-8", errors="replace"))
        for key, value in self.headers.items():
            total += len(key.encode("utf-8", errors="replace"))
            total += len(str(value).encode("utf-8", errors="replace"))
            total += 4
        return total

    def _authenticate(self, path: str) -> dict[str, Any]:
        server = self.server
        if not isinstance(server, ProjectOpsHTTPServer):  # pragma: no cover
            return {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "error": "server_misconfigured", "reason": "server"}
        config = server.config
        if not config.auth_required:
            return {
                "tenant_id": "local",
                "actor_id": "local",
                "request_id": "local",
                "roles": {"admin", "operator", "viewer"},
            }
        authorization = self.headers.get("Authorization", "")
        tenant_id = _text(self.headers.get("X-Tenant-ID"))
        actor_id = _text(self.headers.get("X-Actor-ID"))
        request_id = _text(self.headers.get("X-Request-ID"))
        if not authorization.startswith("Bearer "):
            return {"status": HTTPStatus.UNAUTHORIZED, "error": "missing_auth", "reason": "bearer token required"}
        if not tenant_id or not actor_id or not request_id:
            return {
                "status": HTTPStatus.UNAUTHORIZED,
                "error": "missing_control_plane_headers",
                "reason": "X-Tenant-ID, X-Actor-ID, and X-Request-ID are required",
            }
        token_payload, token_error = _verify_project_ops_token(
            authorization.removeprefix("Bearer ").strip(),
            secret=config.jwt_hmac_secret,
        )
        if token_payload is None:
            return {"status": HTTPStatus.UNAUTHORIZED, "error": "invalid_token", "reason": token_error}
        token_tenant = _text(token_payload.get("tenant_id") or token_payload.get("tid"))
        token_actor = _text(token_payload.get("actor_id") or token_payload.get("sub"))
        roles = _roles_from_claims(token_payload)
        if not roles:
            return {"status": HTTPStatus.FORBIDDEN, "error": "missing_role", "reason": "token role is required"}
        if token_tenant and token_tenant != tenant_id:
            return {"status": HTTPStatus.FORBIDDEN, "error": "tenant_mismatch", "reason": "token tenant mismatch"}
        if token_actor and token_actor != actor_id:
            return {"status": HTTPStatus.FORBIDDEN, "error": "actor_mismatch", "reason": "token actor mismatch"}
        if config.allowed_tenants and tenant_id not in set(config.allowed_tenants):
            return {"status": HTTPStatus.FORBIDDEN, "error": "tenant_not_allowed", "reason": "tenant not allowed"}
        if path.startswith("/audit") and "admin" not in roles:
            return {"status": HTTPStatus.FORBIDDEN, "error": "insufficient_role", "reason": "admin role required"}
        return {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "request_id": request_id,
            "roles": roles,
        }

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        server = self.server
        if isinstance(server, ProjectOpsHTTPServer):
            server.write_audit_event(
                status=status,
                path=self.path,
                context=getattr(self, "_auth_context", None),
            )


def create_project_ops_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    portfolio_json_path: Path | None = None,
    registry_index_json_path: Path | None = None,
    portfolio_batch_json_path: Path | None = None,
    runtime_submission_json_path: Path | None = None,
    runtime_writeback_depth_json_path: Path | None = None,
    multi_project_runtime_writeback_json_path: Path | None = None,
    solver_family_breadth_json_path: Path | None = None,
    local_runtime_scenario_depth_json_path: Path | None = None,
    release_registry_json_path: Path | None = None,
    committee_summary_json_path: Path | None = None,
    release_gap_report_json_path: Path | None = None,
    snapshot_manifest_glob: str = DEFAULT_SNAPSHOT_MANIFEST_GLOB,
    project_registry_paths: list[Path | str] | None = None,
    project_registry_dirs: list[Path | str] | None = None,
    auth_required: bool = True,
    jwt_hmac_secret: str = "",
    allowed_tenants: list[str] | tuple[str, ...] | None = None,
    audit_log_path: Path | None = None,
    audit_digest_path: Path | None = None,
    audit_digest_enabled: bool = True,
    audit_retention_days: int = 365,
    audit_export_max_events: int = 1000,
    request_metadata_byte_limit: int = 8192,
    rate_limit_window_seconds: int = 60,
    rate_limit_max_requests: int = 120,
    backup_policy: str = "operator_managed_snapshot_required",
    tenant_delete_policy: str = "manual_approval_required",
    telemetry_enabled: bool = False,
    license_status_path: Path | None = None,
    service_version: str = "project-ops-api-service.v1",
    update_channel: str = "stable",
) -> ProjectOpsHTTPServer:
    resolved_jwt_hmac_secret = _resolve_project_ops_hmac_secret(
        explicit_secret=jwt_hmac_secret,
        auth_required=auth_required,
    )
    config = ProjectOpsServiceConfig(
        release_root=release_root,
        portfolio_json_path=portfolio_json_path,
        registry_index_json_path=registry_index_json_path,
        portfolio_batch_json_path=portfolio_batch_json_path,
        runtime_submission_json_path=runtime_submission_json_path,
        runtime_writeback_depth_json_path=runtime_writeback_depth_json_path,
        multi_project_runtime_writeback_json_path=multi_project_runtime_writeback_json_path,
        solver_family_breadth_json_path=solver_family_breadth_json_path,
        local_runtime_scenario_depth_json_path=local_runtime_scenario_depth_json_path,
        release_registry_json_path=release_registry_json_path,
        committee_summary_json_path=committee_summary_json_path,
        release_gap_report_json_path=release_gap_report_json_path,
        snapshot_manifest_glob=snapshot_manifest_glob,
        project_registry_paths=tuple(str(item) for item in (project_registry_paths or []) if _text(item)),
        project_registry_dirs=tuple(str(item) for item in (project_registry_dirs or []) if _text(item)),
        auth_required=auth_required,
        jwt_hmac_secret=resolved_jwt_hmac_secret,
        allowed_tenants=tuple(str(item) for item in (allowed_tenants or []) if _text(item)),
        audit_log_path=audit_log_path,
        audit_digest_path=audit_digest_path,
        audit_digest_enabled=audit_digest_enabled,
        audit_retention_days=max(0, int(audit_retention_days)),
        audit_export_max_events=max(1, int(audit_export_max_events)),
        request_metadata_byte_limit=max(0, int(request_metadata_byte_limit)),
        rate_limit_window_seconds=max(0, int(rate_limit_window_seconds)),
        rate_limit_max_requests=max(0, int(rate_limit_max_requests)),
        backup_policy=_text(backup_policy) or "operator_managed_snapshot_required",
        tenant_delete_policy=_text(tenant_delete_policy) or "manual_approval_required",
        telemetry_enabled=telemetry_enabled,
        license_status_path=license_status_path,
        service_version=service_version,
        update_channel=update_channel,
    )
    return ProjectOpsHTTPServer((host, port), config)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--portfolio-json", default="")
    parser.add_argument("--registry-index-json", default="")
    parser.add_argument("--portfolio-batch-json", default="")
    parser.add_argument("--runtime-submission-json", default="")
    parser.add_argument("--runtime-writeback-depth-json", default="")
    parser.add_argument("--multi-project-runtime-writeback-json", default="")
    parser.add_argument("--solver-family-breadth-json", default="")
    parser.add_argument("--local-runtime-scenario-depth-json", default="")
    parser.add_argument("--release-registry-json", default="")
    parser.add_argument("--committee-summary-json", default="")
    parser.add_argument("--release-gap-report-json", default="")
    parser.add_argument("--snapshot-manifest-glob", default=DEFAULT_SNAPSHOT_MANIFEST_GLOB)
    parser.add_argument("--project-registry-paths", default="")
    parser.add_argument("--project-registry-dirs", default="")
    parser.add_argument("--no-auth", action="store_true", help="disable SaaS control-plane auth for local debugging")
    parser.add_argument(
        "--jwt-hmac-secret",
        default="",
        help=f"HMAC secret for bearer-token verification; may also be set with {PROJECT_OPS_JWT_HMAC_SECRET_ENV}",
    )
    parser.add_argument("--allowed-tenants", default="")
    parser.add_argument("--audit-log-path", default="")
    parser.add_argument("--audit-digest-path", default="")
    parser.add_argument("--no-audit-digest", action="store_true")
    parser.add_argument("--audit-retention-days", type=int, default=365)
    parser.add_argument("--audit-export-max-events", type=int, default=1000)
    parser.add_argument("--request-metadata-byte-limit", type=int, default=8192)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=60)
    parser.add_argument("--rate-limit-max-requests", type=int, default=120)
    parser.add_argument("--backup-policy", default="operator_managed_snapshot_required")
    parser.add_argument("--tenant-delete-policy", default="manual_approval_required")
    parser.add_argument("--telemetry-enabled", action="store_true")
    parser.add_argument("--license-status-json", default="")
    parser.add_argument("--service-version", default="project-ops-api-service.v1")
    parser.add_argument("--update-channel", default="stable")
    args = parser.parse_args()

    project_registry_paths = [Path(item) for item in _dedupe_strings(_text(args.project_registry_paths).split(","))]
    project_registry_dirs = [Path(item) for item in _dedupe_strings(_text(args.project_registry_dirs).split(","))]
    allowed_tenants = _dedupe_strings(_text(args.allowed_tenants).split(","))

    server = create_project_ops_server(
        host=_text(args.host) or "127.0.0.1",
        port=int(args.port),
        release_root=Path(args.release_root),
        portfolio_json_path=Path(args.portfolio_json) if _text(args.portfolio_json) else None,
        registry_index_json_path=Path(args.registry_index_json) if _text(args.registry_index_json) else None,
        portfolio_batch_json_path=Path(args.portfolio_batch_json) if _text(args.portfolio_batch_json) else None,
        runtime_submission_json_path=(
            Path(args.runtime_submission_json) if _text(args.runtime_submission_json) else None
        ),
        runtime_writeback_depth_json_path=(
            Path(args.runtime_writeback_depth_json) if _text(args.runtime_writeback_depth_json) else None
        ),
        multi_project_runtime_writeback_json_path=(
            Path(args.multi_project_runtime_writeback_json)
            if _text(args.multi_project_runtime_writeback_json)
            else None
        ),
        solver_family_breadth_json_path=(
            Path(args.solver_family_breadth_json) if _text(args.solver_family_breadth_json) else None
        ),
        local_runtime_scenario_depth_json_path=(
            Path(args.local_runtime_scenario_depth_json)
            if _text(args.local_runtime_scenario_depth_json)
            else None
        ),
        release_registry_json_path=Path(args.release_registry_json) if _text(args.release_registry_json) else None,
        committee_summary_json_path=Path(args.committee_summary_json) if _text(args.committee_summary_json) else None,
        release_gap_report_json_path=Path(args.release_gap_report_json) if _text(args.release_gap_report_json) else None,
        snapshot_manifest_glob=_text(args.snapshot_manifest_glob) or DEFAULT_SNAPSHOT_MANIFEST_GLOB,
        project_registry_paths=project_registry_paths,
        project_registry_dirs=project_registry_dirs,
        auth_required=not bool(args.no_auth),
        jwt_hmac_secret=_text(args.jwt_hmac_secret),
        allowed_tenants=allowed_tenants,
        audit_log_path=Path(args.audit_log_path) if _text(args.audit_log_path) else None,
        audit_digest_path=Path(args.audit_digest_path) if _text(args.audit_digest_path) else None,
        audit_digest_enabled=not bool(args.no_audit_digest),
        audit_retention_days=int(args.audit_retention_days),
        audit_export_max_events=int(args.audit_export_max_events),
        request_metadata_byte_limit=int(args.request_metadata_byte_limit),
        rate_limit_window_seconds=int(args.rate_limit_window_seconds),
        rate_limit_max_requests=int(args.rate_limit_max_requests),
        backup_policy=_text(args.backup_policy) or "operator_managed_snapshot_required",
        tenant_delete_policy=_text(args.tenant_delete_policy) or "manual_approval_required",
        telemetry_enabled=bool(args.telemetry_enabled),
        license_status_path=Path(args.license_status_json) if _text(args.license_status_json) else None,
        service_version=_text(args.service_version) or "project-ops-api-service.v1",
        update_channel=_text(args.update_channel) or "stable",
    )
    bound_host, bound_port = server.server_address[:2]
    print(f"http://{bound_host}:{bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
