#!/usr/bin/env python3
"""Generate deterministic authoring ops artifacts from the native authoring summary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from inspect import Parameter, signature
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.batch_job_runner import build_batch_job_report
    from implementation.phase1.generate_native_authoring_solver_session import (
        DEFAULT_OUT as DEFAULT_SOLVER_SESSION_OUT,
        DEFAULT_LOADCOMB_PREVIEW_OUT,
        DEFAULT_LOADCOMB_PREVIEW_OUT as DEFAULT_SOLVER_LOADCOMB_OUT,
        build_native_authoring_solver_session_payload,
    )
    from implementation.phase1.load_combination_engine import export_midas_loadcomb_from_editor_seed
    from implementation.phase1.generate_native_authoring_workspace_summary import (
        DEFAULT_OUT as DEFAULT_WORKSPACE_SUMMARY,
        build_native_authoring_workspace_payload,
        resolve_authoring_controls,
    )
    from implementation.phase1.project_registry_service import build_project_registry
except ImportError:  # pragma: no cover
    from batch_job_runner import build_batch_job_report  # type: ignore
    from generate_native_authoring_solver_session import (  # type: ignore
        DEFAULT_OUT as DEFAULT_SOLVER_SESSION_OUT,
        DEFAULT_LOADCOMB_PREVIEW_OUT,
        DEFAULT_LOADCOMB_PREVIEW_OUT as DEFAULT_SOLVER_LOADCOMB_OUT,
        build_native_authoring_solver_session_payload,
    )
    from load_combination_engine import export_midas_loadcomb_from_editor_seed  # type: ignore
    from generate_native_authoring_workspace_summary import (  # type: ignore
        DEFAULT_OUT as DEFAULT_WORKSPACE_SUMMARY,
        build_native_authoring_workspace_payload,
        resolve_authoring_controls,
    )
    from project_registry_service import build_project_registry  # type: ignore


DEFAULT_AUTHORING_DIR = Path("implementation/phase1/release/authoring")
DEFAULT_SIGNING_DIR = Path("implementation/phase1/release/signing")
DEFAULT_WORKSPACE_DRAFT_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_workspace_draft.json"
DEFAULT_JOB_MANIFEST_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_job_manifest.json"
DEFAULT_BATCH_REPORT_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_batch_job_report.json"
DEFAULT_SNAPSHOT_ROOT = DEFAULT_AUTHORING_DIR / "snapshots"
DEFAULT_PROJECT_REGISTRY_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_project_registry.json"
DEFAULT_PROJECT_PACKAGE_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_project_package.zip"
DEFAULT_PRIVATE_KEY_OUT = DEFAULT_SIGNING_DIR / "native_authoring_project_registry_ed25519.pem"
DEFAULT_PUBLIC_KEY_OUT = DEFAULT_SIGNING_DIR / "native_authoring_project_registry_ed25519.pub.pem"
DEFAULT_SIGNATURE_OUT = DEFAULT_SIGNING_DIR / "native_authoring_project_registry.signature.b64"
DEFAULT_OUT = DEFAULT_AUTHORING_DIR / "native_authoring_ops_bundle.json"

REASONS = {
    "PASS": "native authoring ops bundle generated",
    "ERR_INPUT": "invalid native authoring workspace summary",
    "ERR_AUTHORING": "native authoring workspace summary was not ready for ops packaging",
    "ERR_SOLVER": "native authoring solver session generation failed",
    "ERR_REGISTRY": "native authoring project registry/package generation failed",
    "ERR_BATCH": "native authoring batch job report generation failed",
}


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effective_generated_at(explicit_generated_at: str | None, workspace_summary: dict[str, Any]) -> str:
    explicit = str(explicit_generated_at or "").strip()
    if explicit:
        return explicit
    summary_generated_at = str(workspace_summary.get("generated_at", "") or "").strip()
    if summary_generated_at:
        return summary_generated_at
    return _now_utc_iso()


def _has_explicit_control_inputs(
    *,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    family_id: str | None = None,
) -> bool:
    return any(
        value is not None and str(value).strip() != ""
        for value in (
            authoring_controls,
            draft_payload,
            draft_json_path,
            story_count,
            bay_count,
            floor_height_m,
            load_pattern_count,
            section_id,
            family_id,
        )
    )


def _resolve_ops_bundle_controls(
    *,
    workspace_summary: dict[str, Any],
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    family_id: str | None = None,
) -> Any:
    explicit_inputs_present = _has_explicit_control_inputs(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )
    source = authoring_controls if explicit_inputs_present else workspace_summary
    return resolve_authoring_controls(
        authoring_controls=source,
        draft_payload=draft_payload if explicit_inputs_present and authoring_controls is None else None,
        draft_json_path=draft_json_path if explicit_inputs_present and authoring_controls is None and draft_payload is None else None,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )


def _load_or_generate_workspace_summary(
    *,
    workspace_summary_path: Path,
    generated_at: str | None,
    force_regenerate_summary: bool,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    family_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    explicit_controls_present = _has_explicit_control_inputs(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )
    if workspace_summary_path.exists() and not force_regenerate_summary and not explicit_controls_present:
        payload = _load_json(workspace_summary_path)
        if not isinstance(payload, dict):
            raise ValueError("workspace summary payload must be a JSON object")
        return payload, "loaded"

    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    payload = build_native_authoring_workspace_payload(
        generated_at=timestamp,
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )
    _write_json(workspace_summary_path, payload)
    return payload, "generated"


def _workspace_summary_row(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("workspace summary payload is missing summary")
    return summary


def _workspace_ready(payload: dict[str, Any]) -> bool:
    summary = _workspace_summary_row(payload)
    return bool(payload.get("contract_pass", False) and summary.get("native_authoring_ready", False))


def _materialize_workspace_draft(
    *,
    workspace_summary: dict[str, Any],
    workspace_draft_out: Path,
    generated_at: str,
    authoring_controls: Any,
) -> dict[str, Any]:
    summary = _workspace_summary_row(workspace_summary)
    controls = resolve_authoring_controls(authoring_controls=authoring_controls)
    palette_source = (
        workspace_summary.get("editor_controls")
        if isinstance(workspace_summary.get("editor_controls"), dict)
        else {}
    )
    section_palette = [
        str(item).strip()
        for item in (palette_source.get("section_palette") or [])
        if str(item).strip()
    ]
    payload = {
        "schema_version": "1.0",
        "report_family": "native_authoring_workspace_draft",
        "generated_at": generated_at,
        "authoring_controls": controls.to_draft_payload(section_palette=section_palette),
        "baseline_summary": {
            "model_id": str(summary.get("model_id", "") or ""),
            "story_count": int(summary.get("story_count", 0) or 0),
            "node_count": int(summary.get("node_count", 0) or 0),
            "member_count": int(summary.get("member_count", 0) or 0),
            "load_pattern_count": int(summary.get("load_pattern_count", 0) or 0),
            "solver_ready_score": float(summary.get("solver_ready_score", 0.0) or 0.0),
            "native_authoring_ready": bool(summary.get("native_authoring_ready", False)),
        },
        "summary_line": str(workspace_summary.get("summary_line", "") or summary.get("summary_line", "") or ""),
        "contract_pass": bool(workspace_summary.get("contract_pass", False)),
        "reason_code": "PASS" if workspace_summary.get("contract_pass", False) else "CHECK",
        "reason": "native authoring draft seed exported",
    }
    _write_json(workspace_draft_out, payload)
    return payload


def _job_ids(model_id: str) -> tuple[str, str, str]:
    normalized_model_id = str(model_id or "").strip() or "native-authoring-workspace"
    return (
        f"authoring::{normalized_model_id}::workspace-summary",
        f"authoring::{normalized_model_id}::solver-session",
        f"authoring::{normalized_model_id}::project-registry",
    )


def _call_builder(builder: Any, **kwargs: Any) -> Any:
    try:
        builder_signature = signature(builder)
    except (TypeError, ValueError):
        return builder(**kwargs)
    accepts_kwargs = any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in builder_signature.parameters.values()
    )
    call_kwargs = kwargs if accepts_kwargs else {
        key: value for key, value in kwargs.items() if key in builder_signature.parameters
    }
    return builder(**call_kwargs)


def _solver_session_editor_seed(payload: dict[str, Any]) -> dict[str, Any]:
    load_combination_session = (
        payload.get("load_combination_session") if isinstance(payload.get("load_combination_session"), dict) else {}
    )
    editor_seed = load_combination_session.get("editor_seed")
    if isinstance(editor_seed, dict):
        return editor_seed

    model_payload = payload.get("model_payload") if isinstance(payload.get("model_payload"), dict) else {}
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    editor_seed = metadata.get("load_combination_editor_seed")
    return editor_seed if isinstance(editor_seed, dict) else {}


def _materialize_solver_session_from_payload(
    *,
    generated_at: str,
    workspace_summary: dict[str, Any],
    workspace_summary_path: Path,
    solver_session_out: Path,
    loadcomb_preview_out: Path,
    authoring_controls: Any,
) -> tuple[dict[str, Any], list[Path]]:
    payload = _call_builder(
        build_native_authoring_solver_session_payload,
        generated_at=generated_at,
        authoring_controls=authoring_controls,
        workspace_summary=workspace_summary,
        workspace_summary_path=workspace_summary_path,
        out=solver_session_out,
        out_path=solver_session_out,
        loadcomb_preview_out=loadcomb_preview_out,
        loadcomb_out=loadcomb_preview_out,
        loadcomb_out_path=loadcomb_preview_out,
    )
    if not isinstance(payload, dict):
        raise ValueError("solver session payload must be a JSON object")

    _write_json(solver_session_out, payload)
    artifact_paths = [solver_session_out]
    editor_seed = _solver_session_editor_seed(payload)
    if editor_seed:
        loadcomb_preview = export_midas_loadcomb_from_editor_seed(editor_seed)
        if str(loadcomb_preview).strip():
            _write_text(loadcomb_preview_out, loadcomb_preview)
            artifact_paths.append(loadcomb_preview_out)
    return payload, artifact_paths


def _build_authoring_job_manifest(
    *,
    workspace_summary: dict[str, Any],
    workspace_summary_path: Path,
    workspace_draft_path: Path,
    generated_at: str,
) -> dict[str, Any]:
    summary = _workspace_summary_row(workspace_summary)
    model_id = str(summary.get("model_id", "") or "native-authoring-workspace").strip()
    workspace_job_id, solver_job_id, registry_job_id = _job_ids(model_id)
    ready = _workspace_ready(workspace_summary)
    summary_line = str(workspace_summary.get("summary_line", summary.get("summary_line", "")) or "").strip()
    solver_note = "build solver session and deterministic LOADCOMB preview from native authoring scaffold"
    registry_note = "package native authoring workspace and solver session artifacts into signed registry artifacts"
    if not ready:
        solver_note = "blocked until native authoring workspace summary is ready"
        registry_note = "blocked until native authoring workspace summary is ready"
    return {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-job-manifest",
        "generated_at": generated_at,
        "source_summary": str(workspace_summary_path),
        "jobs": [
            {
                "job_id": workspace_job_id,
                "phase": "authoring_release",
                "benchmark_family": "native_authoring_workspace",
                "submission_scope": "workspace_summary",
                "lifecycle_status": "completed",
                "input_path": str(workspace_summary_path),
                "artifact_paths": [str(workspace_summary_path), str(workspace_draft_path)],
                "note": summary_line,
            },
            {
                "job_id": solver_job_id,
                "phase": "authoring_solver",
                "benchmark_family": "native_authoring_workspace",
                "submission_scope": "solver_session",
                "lifecycle_status": "planned" if ready else "blocked",
                "input_path": str(workspace_summary_path),
                "artifact_paths": [],
                "note": solver_note,
            },
            {
                "job_id": registry_job_id,
                "phase": "authoring_registry",
                "benchmark_family": "native_authoring_workspace",
                "submission_scope": "signed_project_registry",
                "lifecycle_status": "planned" if ready else "blocked",
                "input_path": str(workspace_summary_path),
                "artifact_paths": [],
                "note": registry_note,
            },
        ],
    }


def _build_registry_audit_payload(
    *,
    workspace_summary_path: Path,
    job_manifest_path: Path,
    solver_session_path: Path,
    solver_loadcomb_path: Path,
    workspace_summary: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    summary_line = str(workspace_summary.get("summary_line", "") or "").strip()
    notes_by_name = {
        workspace_summary_path.name: summary_line,
        job_manifest_path.name: "native authoring jobs scaffolded from workspace summary",
        solver_session_path.name: "native authoring solver session exported for solver-ready review",
        solver_loadcomb_path.name: "deterministic MIDAS LOADCOMB preview exported from solver session",
    }
    audit_log = []
    for index, artifact_path in enumerate(
        [workspace_summary_path, job_manifest_path, solver_session_path, solver_loadcomb_path],
        start=1,
    ):
        audit_log.append(
            {
                "event_id": f"authoring-registry-artifact-{index:03d}",
                "actor": "generate_native_authoring_workspace_ops_bundle",
                "action": "registered_artifact",
                "status": "completed",
                "artifact_label": artifact_path.name,
                "timestamp": generated_at,
                "note": notes_by_name[artifact_path.name],
            }
        )
    return {"audit_log": audit_log}


def _build_registry_approval_payload(
    *,
    workspace_summary: dict[str, Any],
    job_manifest: dict[str, Any],
    solver_session_payload: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    summary_line = str(workspace_summary.get("summary_line", "") or "").strip()
    job_count = len([row for row in job_manifest.get("jobs", []) if isinstance(row, dict)])
    solver_summary = (
        solver_session_payload.get("summary")
        if isinstance(solver_session_payload.get("summary"), dict)
        else {}
    )
    return {
        "approvals": [
            {
                "gate_id": "native_authoring_ready",
                "approver": "generate_native_authoring_workspace_ops_bundle",
                "status": "approved",
                "decided_at": generated_at,
                "comment": summary_line,
            },
            {
                "gate_id": "authoring_solver_session_ready",
                "approver": "generate_native_authoring_workspace_ops_bundle",
                "status": "approved" if solver_session_payload.get("contract_pass", False) else "rejected",
                "decided_at": generated_at,
                "comment": (
                    f"solver session combos={int(solver_summary.get('combo_count', 0) or 0)} "
                    f"mesh_requests={int(solver_summary.get('mesh_request_count', 0) or 0)}"
                ),
            },
            {
                "gate_id": "authoring_ops_manifest_frozen",
                "approver": "generate_native_authoring_workspace_ops_bundle",
                "status": "approved",
                "decided_at": generated_at,
                "comment": f"job manifest frozen with {job_count} authoring jobs",
            },
        ]
    }


def _resolve_project_identity(
    *,
    workspace_summary: dict[str, Any],
    explicit_project_id: str,
    explicit_project_name: str,
) -> tuple[str, str]:
    summary = _workspace_summary_row(workspace_summary)
    model_id = str(summary.get("model_id", "") or "native-authoring-workspace").strip()
    project_id = str(explicit_project_id or "").strip() or model_id
    project_name = str(explicit_project_name or "").strip() or f"Native Authoring Workspace {project_id}"
    return project_id, project_name


def build_native_authoring_workspace_ops_bundle(
    *,
    workspace_summary_path: Path = DEFAULT_WORKSPACE_SUMMARY,
    solver_session_out: Path = DEFAULT_SOLVER_SESSION_OUT,
    solver_loadcomb_out: Path | None = None,
    loadcomb_preview_out: Path = DEFAULT_LOADCOMB_PREVIEW_OUT,
    draft_json_path: str | Path | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
    job_manifest_out: Path = DEFAULT_JOB_MANIFEST_OUT,
    batch_report_out: Path = DEFAULT_BATCH_REPORT_OUT,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    project_registry_out: Path = DEFAULT_PROJECT_REGISTRY_OUT,
    project_package_out: Path = DEFAULT_PROJECT_PACKAGE_OUT,
    private_key_out: Path = DEFAULT_PRIVATE_KEY_OUT,
    public_key_out: Path = DEFAULT_PUBLIC_KEY_OUT,
    signature_out: Path = DEFAULT_SIGNATURE_OUT,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
    project_id: str = "",
    project_name: str = "",
    family_id: str = "",
    authoring_family_id: str = "",
    portfolio_name: str = "",
    draft_label: str = "",
    force_regenerate_summary: bool = False,
) -> dict[str, Any]:
    authoring_controls_seed = {"family_id": str(authoring_family_id).strip()} if str(authoring_family_id).strip() else None
    workspace_summary, source_mode = _load_or_generate_workspace_summary(
        workspace_summary_path=workspace_summary_path,
        generated_at=generated_at,
        force_regenerate_summary=bool(force_regenerate_summary),
        authoring_controls=authoring_controls_seed,
        draft_json_path=draft_json_path,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )
    summary = _workspace_summary_row(workspace_summary)
    timestamp = _effective_generated_at(generated_at, workspace_summary)
    ready = _workspace_ready(workspace_summary)
    effective_loadcomb_preview_out = solver_loadcomb_out or loadcomb_preview_out
    workspace_draft_out = workspace_summary_path.with_name(DEFAULT_WORKSPACE_DRAFT_OUT.name)
    resolved_controls = _resolve_ops_bundle_controls(
        workspace_summary=workspace_summary,
        authoring_controls=authoring_controls_seed,
        draft_json_path=draft_json_path,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
        family_id=family_id,
    )
    _materialize_workspace_draft(
        workspace_summary=workspace_summary,
        workspace_draft_out=workspace_draft_out,
        generated_at=timestamp,
        authoring_controls=resolved_controls,
    )

    job_manifest = _build_authoring_job_manifest(
        workspace_summary=workspace_summary,
        workspace_summary_path=workspace_summary_path,
        workspace_draft_path=workspace_draft_out,
        generated_at=timestamp,
    )
    _write_json(job_manifest_out, job_manifest)

    workspace_job_id, solver_job_id, registry_job_id = _job_ids(
        str(summary.get("model_id", "") or "native-authoring-workspace")
    )

    solver_session_payload: dict[str, Any] = {}
    solver_session_summary: dict[str, Any] = {}
    solver_artifact_paths: list[Path] = []
    project_registry_payload: dict[str, Any] = {}
    project_registry_checks: dict[str, Any] = {}
    project_registry_summary: dict[str, Any] = {}
    registry_artifact_paths: list[Path] = []
    updates: list[dict[str, Any]] = []
    resolved_family_id = str(family_id or "").strip() or str(summary.get("model_id", "") or "").strip()
    resolved_portfolio_name = str(portfolio_name or "").strip()
    resolved_draft_label = str(draft_label or "").strip() or source_mode

    if ready:
        solver_session_payload, solver_artifact_paths = _materialize_solver_session_from_payload(
            generated_at=timestamp,
            workspace_summary=workspace_summary,
            workspace_summary_path=workspace_summary_path,
            solver_session_out=solver_session_out,
            loadcomb_preview_out=effective_loadcomb_preview_out,
            authoring_controls=resolved_controls,
        )
        solver_session_summary = (
            solver_session_payload.get("summary")
            if isinstance(solver_session_payload.get("summary"), dict)
            else {}
        )
        updates.append(
            {
                "job_id": solver_job_id,
                "lifecycle_status": "completed" if solver_session_payload.get("contract_pass", False) else "failed",
                "artifact_paths": [str(path) for path in solver_artifact_paths],
                "note": str(solver_session_payload.get("summary_line", "") or "").strip(),
            }
        )

    if ready and solver_session_payload.get("contract_pass", False):
        resolved_project_id, resolved_project_name = _resolve_project_identity(
            workspace_summary=workspace_summary,
            explicit_project_id=project_id,
            explicit_project_name=project_name,
        )
        project_registry_payload = build_project_registry(
            project_id=resolved_project_id,
            project_name=resolved_project_name,
            artifact_paths=[workspace_summary_path, job_manifest_out, *solver_artifact_paths],
            audit_payload=_build_registry_audit_payload(
                workspace_summary_path=workspace_summary_path,
                job_manifest_path=job_manifest_out,
                solver_session_path=solver_session_out,
                solver_loadcomb_path=effective_loadcomb_preview_out,
                workspace_summary=workspace_summary,
                generated_at=timestamp,
            ),
            approval_payload=_build_registry_approval_payload(
                workspace_summary=workspace_summary,
                job_manifest=job_manifest,
                solver_session_payload=solver_session_payload,
                generated_at=timestamp,
            ),
            project_metadata={
                "family_id": resolved_family_id,
                "portfolio_name": resolved_portfolio_name,
                "draft_label": resolved_draft_label,
                "model_id": str(summary.get("model_id", "") or ""),
            },
            private_key_out=private_key_out,
            public_key_out=public_key_out,
            signature_out=signature_out,
            package_out=project_package_out,
            out=project_registry_out,
            generated_at=timestamp,
        )
        project_registry_checks = (
            project_registry_payload.get("checks")
            if isinstance(project_registry_payload.get("checks"), dict)
            else {}
        )
        project_registry_summary = (
            project_registry_payload.get("summary")
            if isinstance(project_registry_payload.get("summary"), dict)
            else {}
        )
        registry_artifact_paths = [
            path
            for path in (project_registry_out, project_package_out, public_key_out, signature_out)
            if path.exists()
        ]
        updates.append(
            {
                "job_id": registry_job_id,
                "lifecycle_status": "completed" if project_registry_payload.get("contract_pass", False) else "failed",
                "artifact_paths": [str(path) for path in registry_artifact_paths],
                "note": str(project_registry_payload.get("summary_line", "") or "").strip(),
            }
        )
    elif ready:
        updates.append(
            {
                "job_id": registry_job_id,
                "lifecycle_status": "blocked",
                "note": "blocked until native authoring solver session artifacts are ready",
            }
        )

    updates_payload = {"updates": updates} if updates else None
    batch_report_payload = build_batch_job_report(
        job_manifest=job_manifest,
        updates_payload=updates_payload,
        snapshot_root=snapshot_root,
        out=batch_report_out,
        generated_at=timestamp,
    )
    batch_report_checks = (
        batch_report_payload.get("checks")
        if isinstance(batch_report_payload.get("checks"), dict)
        else {}
    )
    batch_report_summary = (
        batch_report_payload.get("summary")
        if isinstance(batch_report_payload.get("summary"), dict)
        else {}
    )

    checks = {
        "workspace_summary_ready_pass": ready,
        "job_manifest_written_pass": job_manifest_out.exists(),
        "solver_session_pass": bool(solver_session_payload.get("contract_pass", False)),
        "solver_session_written_pass": solver_session_out in solver_artifact_paths and solver_session_out.exists(),
        "loadcomb_preview_written_pass": (
            effective_loadcomb_preview_out in solver_artifact_paths and effective_loadcomb_preview_out.exists()
        ),
        "batch_job_report_pass": bool(batch_report_payload.get("contract_pass", False)),
        "batch_job_snapshots_written_pass": bool(batch_report_checks.get("snapshot_manifest_written_pass", False)),
        "project_registry_pass": bool(project_registry_payload.get("contract_pass", False)),
        "project_registry_signature_verified_pass": bool(project_registry_checks.get("signature_verified_pass", False)),
    }

    reason_code = "PASS"
    if not checks["job_manifest_written_pass"]:
        reason_code = "ERR_INPUT"
    elif not ready:
        reason_code = "ERR_AUTHORING"
    elif (
        not checks["solver_session_pass"]
        or not checks["solver_session_written_pass"]
        or not checks["loadcomb_preview_written_pass"]
    ):
        reason_code = "ERR_SOLVER"
    elif not checks["project_registry_pass"] or not checks["project_registry_signature_verified_pass"]:
        reason_code = "ERR_REGISTRY"
    elif not checks["batch_job_report_pass"] or not checks["batch_job_snapshots_written_pass"]:
        reason_code = "ERR_BATCH"

    contract_pass = bool(reason_code == "PASS")
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-workspace-ops-bundle",
        "generated_at": timestamp,
        "inputs": {
            "workspace_summary": str(workspace_summary_path),
            "workspace_summary_source_mode": source_mode,
            "draft_json_path": str(draft_json_path or ""),
            "story_count": story_count if story_count is not None else "",
            "bay_count": bay_count if bay_count is not None else "",
            "floor_height_m": floor_height_m if floor_height_m is not None else "",
            "load_pattern_count": load_pattern_count if load_pattern_count is not None else "",
            "section_id": str(section_id or ""),
            "family_id": resolved_family_id,
            "authoring_family_id": str(authoring_family_id or ""),
            "portfolio_name": resolved_portfolio_name,
            "draft_label": resolved_draft_label,
            "solver_session_out": str(solver_session_out),
            "loadcomb_preview_out": str(effective_loadcomb_preview_out),
            "solver_session_source_mode": "generated" if solver_artifact_paths else "skipped",
            "job_manifest_out": str(job_manifest_out),
            "batch_report_out": str(batch_report_out),
            "snapshot_root": str(snapshot_root),
            "project_registry_out": str(project_registry_out),
            "project_package_out": str(project_package_out),
            "private_key_out": str(private_key_out),
            "public_key_out": str(public_key_out),
            "signature_out": str(signature_out),
            "out": str(out),
        },
        "checks": checks,
        "summary": {
            "model_id": str(summary.get("model_id", "") or ""),
            "family_id": resolved_family_id,
            "authoring_family_id": str(authoring_family_id or ""),
            "portfolio_name": resolved_portfolio_name,
            "draft_label": resolved_draft_label,
            "story_count": int(summary.get("story_count", 0) or 0),
            "member_count": int(summary.get("member_count", 0) or 0),
            "load_pattern_count": int(summary.get("load_pattern_count", 0) or 0),
            "workspace_artifact_count": 1 + len(solver_artifact_paths),
            "solver_session_artifact_count": len(solver_artifact_paths),
            "solver_combo_count": int(solver_session_summary.get("combo_count", 0) or 0),
            "solver_mesh_request_count": int(solver_session_summary.get("mesh_request_count", 0) or 0),
            "solver_load_case_count": int(solver_session_summary.get("load_case_count", 0) or 0),
            "solver_loadcomb_line_count": int(solver_session_summary.get("loadcomb_line_count", 0) or 0),
            "job_count": int(batch_report_summary.get("job_count", len(job_manifest.get("jobs", []))) or 0),
            "snapshot_count": int(batch_report_summary.get("snapshot_count", 0) or 0),
            "registry_artifact_count": int(project_registry_summary.get("artifact_count", 0) or 0),
            "registry_approval_count": int(project_registry_summary.get("approval_count", 0) or 0),
            "registry_package_sha256": str(project_registry_summary.get("package_sha256", "") or ""),
            "workspace_job_id": workspace_job_id,
            "solver_job_id": solver_job_id,
            "registry_job_id": registry_job_id,
        },
        "artifacts": {
            "workspace_summary_json": str(workspace_summary_path),
            "workspace_draft_json": str(workspace_draft_out) if workspace_draft_out.exists() else "",
            "solver_session_json": str(solver_session_out) if solver_session_out.exists() else "",
            "solver_session_artifact_json": str(solver_session_out) if solver_session_out.exists() else "",
            "solver_loadcomb_preview_mgt": (
                str(effective_loadcomb_preview_out) if effective_loadcomb_preview_out.exists() else ""
            ),
            "loadcomb_preview_mgt": str(effective_loadcomb_preview_out) if effective_loadcomb_preview_out.exists() else "",
            "job_manifest_json": str(job_manifest_out),
            "batch_job_report_json": str(batch_report_out) if batch_report_out.exists() else "",
            "project_registry_json": str(project_registry_out) if project_registry_out.exists() else "",
            "project_package_zip": str(project_package_out) if project_package_out.exists() else "",
            "project_registry_public_key": str(public_key_out) if public_key_out.exists() else "",
            "project_registry_signature": str(signature_out) if signature_out.exists() else "",
        },
        "solver_session_summary": solver_session_summary,
        "batch_job_report_summary": batch_report_summary,
        "project_registry_summary": project_registry_summary,
        "summary_line": (
            "Native authoring ops bundle: "
            f"{reason_code} | family={resolved_family_id or 'none'} | source={source_mode} | ready={ready} | "
            f"solver_combos={int(solver_session_summary.get('combo_count', 0) or 0)} | "
            f"jobs={batch_report_summary.get('job_count', len(job_manifest.get('jobs', [])))} | "
            f"snapshots={batch_report_summary.get('snapshot_count', 0)} | "
            f"package_artifacts={project_registry_summary.get('artifact_count', 0)}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    _write_json(out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-summary", default=str(DEFAULT_WORKSPACE_SUMMARY))
    parser.add_argument("--solver-session-out", default=str(DEFAULT_SOLVER_SESSION_OUT))
    parser.add_argument("--draft-json", default="")
    parser.add_argument("--story-count", type=float, default=None)
    parser.add_argument("--bay-count", type=float, default=None)
    parser.add_argument("--floor-height-m", type=float, default=None)
    parser.add_argument("--load-pattern-count", type=float, default=None)
    parser.add_argument("--section-id", default=None)
    parser.add_argument(
        "--loadcomb-preview-out",
        "--solver-loadcomb-out",
        dest="solver_loadcomb_out",
        default=str(DEFAULT_SOLVER_LOADCOMB_OUT),
    )
    parser.add_argument("--force-regenerate-summary", action="store_true")
    parser.add_argument("--job-manifest-out", default=str(DEFAULT_JOB_MANIFEST_OUT))
    parser.add_argument("--batch-report-out", default=str(DEFAULT_BATCH_REPORT_OUT))
    parser.add_argument("--snapshot-root", default=str(DEFAULT_SNAPSHOT_ROOT))
    parser.add_argument("--project-id", default="")
    parser.add_argument("--project-name", default="")
    parser.add_argument("--family-id", default="")
    parser.add_argument("--authoring-family-id", default="")
    parser.add_argument("--portfolio-name", default="")
    parser.add_argument("--draft-label", default="")
    parser.add_argument("--private-key-out", default=str(DEFAULT_PRIVATE_KEY_OUT))
    parser.add_argument("--public-key-out", default=str(DEFAULT_PUBLIC_KEY_OUT))
    parser.add_argument("--signature-out", default=str(DEFAULT_SIGNATURE_OUT))
    parser.add_argument("--project-package-out", default=str(DEFAULT_PROJECT_PACKAGE_OUT))
    parser.add_argument("--project-registry-out", default=str(DEFAULT_PROJECT_REGISTRY_OUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    payload = build_native_authoring_workspace_ops_bundle(
        workspace_summary_path=Path(args.workspace_summary),
        solver_session_out=Path(args.solver_session_out),
        solver_loadcomb_out=Path(args.solver_loadcomb_out),
        draft_json_path=str(args.draft_json).strip() or None,
        story_count=args.story_count,
        bay_count=args.bay_count,
        floor_height_m=args.floor_height_m,
        load_pattern_count=args.load_pattern_count,
        section_id=str(args.section_id).strip() if isinstance(args.section_id, str) and args.section_id.strip() else None,
        job_manifest_out=Path(args.job_manifest_out),
        batch_report_out=Path(args.batch_report_out),
        snapshot_root=Path(args.snapshot_root),
        project_registry_out=Path(args.project_registry_out),
        project_package_out=Path(args.project_package_out),
        private_key_out=Path(args.private_key_out),
        public_key_out=Path(args.public_key_out),
        signature_out=Path(args.signature_out),
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
        project_id=str(args.project_id),
        project_name=str(args.project_name),
        family_id=str(args.family_id),
        authoring_family_id=str(args.authoring_family_id),
        portfolio_name=str(args.portfolio_name),
        draft_label=str(args.draft_label),
        force_regenerate_summary=bool(args.force_regenerate_summary),
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
