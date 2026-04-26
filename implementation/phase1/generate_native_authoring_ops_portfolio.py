#!/usr/bin/env python3
"""Generate a multi-family native authoring ops portfolio surface."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.batch_job_runner import build_batch_job_report
    from implementation.phase1.generate_native_authoring_family_tracks import (
        build_native_authoring_family_tracks,
    )
    from implementation.phase1.generate_native_authoring_runtime_submission_lane import (
        build_native_authoring_runtime_submission_lane,
    )
    from implementation.phase1.generate_native_authoring_runtime_writeback_depth_report import (
        build_native_authoring_runtime_writeback_depth_report,
    )
    from implementation.phase1.generate_native_authoring_multi_project_runtime_writeback_report import (
        build_native_authoring_multi_project_runtime_writeback_report,
    )
    from implementation.phase1.generate_native_authoring_solver_family_breadth_report import (
        build_native_authoring_solver_family_breadth_report,
    )
    from implementation.phase1.generate_native_authoring_local_runtime_scenario_depth_report import (
        build_native_authoring_local_runtime_scenario_depth_report,
    )
    from implementation.phase1.generate_native_authoring_local_variant_writeback_trace_report import (
        build_native_authoring_local_variant_writeback_trace_report,
    )
    from implementation.phase1.generate_native_authoring_writeback_breadth_report import (
        build_native_authoring_writeback_breadth_report,
    )
    from implementation.phase1.generate_native_authoring_workspace_ops_bundle import (
        build_native_authoring_workspace_ops_bundle,
    )
    from implementation.phase1.project_registry_service import build_project_registry_index
except ImportError:  # pragma: no cover
    from batch_job_runner import build_batch_job_report  # type: ignore
    from generate_native_authoring_family_tracks import build_native_authoring_family_tracks  # type: ignore
    from generate_native_authoring_runtime_submission_lane import build_native_authoring_runtime_submission_lane  # type: ignore
    from generate_native_authoring_runtime_writeback_depth_report import (  # type: ignore
        build_native_authoring_runtime_writeback_depth_report,
    )
    from generate_native_authoring_multi_project_runtime_writeback_report import (  # type: ignore
        build_native_authoring_multi_project_runtime_writeback_report,
    )
    from generate_native_authoring_solver_family_breadth_report import (  # type: ignore
        build_native_authoring_solver_family_breadth_report,
    )
    from generate_native_authoring_local_runtime_scenario_depth_report import (  # type: ignore
        build_native_authoring_local_runtime_scenario_depth_report,
    )
    from generate_native_authoring_local_variant_writeback_trace_report import (  # type: ignore
        build_native_authoring_local_variant_writeback_trace_report,
    )
    from generate_native_authoring_writeback_breadth_report import (  # type: ignore
        build_native_authoring_writeback_breadth_report,
    )
    from generate_native_authoring_workspace_ops_bundle import build_native_authoring_workspace_ops_bundle  # type: ignore
    from project_registry_service import build_project_registry_index  # type: ignore


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_SIGNING_DIR = Path("implementation/phase1/release/signing/native_authoring_portfolio")
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_BATCH_OUT = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio_batch.json"
DEFAULT_REGISTRY_INDEX_OUT = DEFAULT_OUT_DIR / "native_authoring_project_registry_index.json"
DEFAULT_REGISTRY_WORKSPACE_OUT = DEFAULT_OUT_DIR / "native_authoring_project_registry_workspace.json"
DEFAULT_FAMILY_TRACKS_OUT = DEFAULT_OUT_DIR / "native_authoring_family_tracks.json"
DEFAULT_RUNTIME_SUBMISSION_LANE_OUT = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_RUNTIME_WRITEBACK_DEPTH_OUT = DEFAULT_OUT_DIR / "native_authoring_runtime_writeback_depth_report.json"
DEFAULT_MULTI_PROJECT_RUNTIME_WRITEBACK_OUT = (
    DEFAULT_OUT_DIR / "native_authoring_multi_project_runtime_writeback_report.json"
)
DEFAULT_SOLVER_FAMILY_BREADTH_OUT = DEFAULT_OUT_DIR / "native_authoring_solver_family_breadth_report.json"
DEFAULT_LOCAL_RUNTIME_SCENARIO_DEPTH_OUT = (
    DEFAULT_OUT_DIR / "native_authoring_local_runtime_scenario_depth_report.json"
)
DEFAULT_LOCAL_VARIANT_WRITEBACK_TRACE_OUT = (
    DEFAULT_OUT_DIR / "native_authoring_local_variant_writeback_trace_report.json"
)
DEFAULT_WRITEBACK_BREADTH_OUT = DEFAULT_OUT_DIR / "native_authoring_writeback_breadth_report.json"
DEFAULT_SNAPSHOT_ROOT = DEFAULT_OUT_DIR / "snapshots"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_int(*values: Any) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(float(value))
            except ValueError:
                continue
    return 0


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _unique_sorted_tokens(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _compact_label(values: list[str], max_items: int = 4) -> str:
    normalized = _unique_sorted_tokens(values)
    if not normalized:
        return ""
    if len(normalized) <= max_items:
        return ", ".join(normalized)
    return f"{', '.join(normalized[:max_items])} +{len(normalized) - max_items}"


def _authoring_section_family(section_id: str) -> str:
    normalized = str(section_id or "").strip().lower()
    if not normalized:
        return "unknown"
    if normalized.startswith("steel") or "steel_" in normalized:
        return "steel"
    if normalized.startswith("cft") or normalized.startswith("src") or "composite" in normalized:
        return "composite"
    if normalized.startswith("deck") or "slab" in normalized or "plate" in normalized:
        return "deck/floor"
    if (
        normalized.startswith("rc")
        or "concrete" in normalized
        or "wall" in normalized
        or "column" in normalized
    ):
        return "rc"
    return "other"


def _load_dict(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _build_family_commercialization_row(
    *,
    family_id: str,
    portfolio_name: str,
    row: dict[str, Any],
    bundle_payload: dict[str, Any],
    bundle_summary: dict[str, Any],
    bundle_artifacts: dict[str, Any],
    workspace_summary_path: Path,
    solver_session_path: Path,
    batch_report_path: Path,
    project_registry_path: Path,
) -> dict[str, Any]:
    workspace_payload = _load_dict(workspace_summary_path)
    solver_payload = _load_dict(solver_session_path)
    batch_payload = _load_dict(batch_report_path)
    registry_payload = _load_dict(project_registry_path)

    workspace_summary = (
        workspace_payload.get("summary") if isinstance(workspace_payload.get("summary"), dict) else {}
    )
    selected_family = (
        workspace_payload.get("selected_family")
        if isinstance(workspace_payload.get("selected_family"), dict)
        else {}
    )
    editor_controls = (
        workspace_payload.get("editor_controls")
        if isinstance(workspace_payload.get("editor_controls"), dict)
        else {}
    )
    solver_summary = (
        solver_payload.get("summary") if isinstance(solver_payload.get("summary"), dict) else {}
    )
    authoring_summary = (
        solver_payload.get("authoring_summary")
        if isinstance(solver_payload.get("authoring_summary"), dict)
        else {}
    )
    mesh_session = (
        solver_payload.get("mesh_session") if isinstance(solver_payload.get("mesh_session"), dict) else {}
    )
    load_combination_session = (
        solver_payload.get("load_combination_session")
        if isinstance(solver_payload.get("load_combination_session"), dict)
        else {}
    )
    runtime_summary = (
        load_combination_session.get("runtime_summary")
        if isinstance(load_combination_session.get("runtime_summary"), dict)
        else {}
    )
    batch_summary = batch_payload.get("summary") if isinstance(batch_payload.get("summary"), dict) else {}
    registry_summary = (
        registry_payload.get("summary") if isinstance(registry_payload.get("summary"), dict) else {}
    )
    registry_checks = (
        registry_payload.get("checks") if isinstance(registry_payload.get("checks"), dict) else {}
    )

    section_palette = [
        str(value).strip()
        for value in editor_controls.get("section_palette", [])
        if str(value or "").strip()
    ]
    section_usage_counts = (
        authoring_summary.get("section_usage_counts")
        if isinstance(authoring_summary.get("section_usage_counts"), dict)
        else workspace_summary.get("section_usage_counts")
        if isinstance(workspace_summary.get("section_usage_counts"), dict)
        else {}
    )
    member_type_counts = (
        authoring_summary.get("member_type_counts")
        if isinstance(authoring_summary.get("member_type_counts"), dict)
        else workspace_summary.get("member_type_counts")
        if isinstance(workspace_summary.get("member_type_counts"), dict)
        else {}
    )
    active_section_ids = [str(key).strip() for key in section_usage_counts.keys() if str(key).strip()]
    palette_families = [_authoring_section_family(section_id) for section_id in section_palette]
    active_families = [_authoring_section_family(section_id) for section_id in active_section_ids]
    member_types = [str(key).strip() for key in member_type_counts.keys() if str(key).strip()]

    workspace_ready = bool(
        workspace_payload.get("contract_pass", False) and workspace_summary.get("native_authoring_ready", False)
    )
    solver_ready = bool(
        solver_payload.get("contract_pass", False)
        and (
            solver_summary.get("session_ready", False)
            or runtime_summary.get("authoring_ready", False)
        )
    )
    runtime_ready = bool(runtime_summary.get("authoring_ready", False))
    ops_ready = bool(bundle_payload.get("contract_pass", False))
    batch_ready = bool(batch_payload.get("contract_pass", False))
    registry_ready = bool(registry_payload.get("contract_pass", False))
    signature_verified = bool(registry_checks.get("signature_verified_pass", False))

    score = 30
    for ready_flag, increment in (
        (workspace_ready, 10),
        (solver_ready, 14),
        (runtime_ready, 8),
        (ops_ready, 10),
        (batch_ready, 5),
        (registry_ready, 8),
        (signature_verified, 10),
    ):
        if ready_flag:
            score += increment
    if _first_int(bundle_summary.get("solver_combo_count"), solver_summary.get("combo_count")) >= 10:
        score += 3
    if _first_int(bundle_summary.get("solver_mesh_request_count"), solver_summary.get("mesh_request_count")) >= 2:
        score += 1
    if len(_unique_sorted_tokens(palette_families)) >= 4:
        score += 1
    score = min(score, 100)

    if score >= 82 and signature_verified and ops_ready and solver_ready:
        commercialization_status = "ready"
    elif score >= 60:
        commercialization_status = "narrowing"
    else:
        commercialization_status = "check"

    return {
        "family_id": family_id,
        "family_label": _first_text(selected_family.get("label"), family_id.replace("_", " ")),
        "portfolio_name": portfolio_name,
        "project_id": str(row["project_id"]),
        "project_name": str(row["project_name"]),
        "draft_label": str(row["draft_label"]),
        "authoring_family_id": str(row.get("authoring_family_id", "") or family_id),
        "draft_json_path": str(row.get("draft_json_path", "") or ""),
        "preferred_design_family": _first_text(selected_family.get("preferred_design_family")),
        "commercialization_status": commercialization_status,
        "commercialization_score": int(score),
        "workspace_ready": workspace_ready,
        "solver_ready": solver_ready,
        "runtime_ready": runtime_ready,
        "ops_ready": ops_ready,
        "batch_ready": batch_ready,
        "registry_ready": registry_ready,
        "signature_verified": signature_verified,
        "story_count": _first_int(bundle_summary.get("story_count"), workspace_summary.get("story_count")),
        "node_count": _first_int(workspace_summary.get("node_count"), authoring_summary.get("node_count")),
        "member_count": _first_int(bundle_summary.get("member_count"), workspace_summary.get("member_count")),
        "load_pattern_count": _first_int(bundle_summary.get("load_pattern_count"), workspace_summary.get("load_pattern_count")),
        "solver_combo_count": _first_int(
            bundle_summary.get("solver_combo_count"),
            solver_summary.get("combo_count"),
            runtime_summary.get("combo_count"),
        ),
        "solver_mesh_request_count": _first_int(
            bundle_summary.get("solver_mesh_request_count"),
            solver_summary.get("mesh_request_count"),
            mesh_session.get("request_count"),
        ),
        "solver_mesh_cell_count": _first_int(
            mesh_session.get("total_estimated_cells"),
            bundle_summary.get("solver_cell_count"),
        ),
        "solver_load_case_count": _first_int(
            solver_summary.get("load_case_count"),
            runtime_summary.get("runtime_case_count"),
        ),
        "solver_loadcomb_line_count": _first_int(
            solver_summary.get("loadcomb_line_count"),
            load_combination_session.get("loadcomb_preview_line_count"),
        ),
        "job_count": _first_int(bundle_summary.get("job_count"), batch_summary.get("job_count")),
        "snapshot_count": _first_int(bundle_summary.get("snapshot_count"), batch_summary.get("snapshot_count")),
        "approval_count": _first_int(
            registry_summary.get("approved_count"),
            registry_summary.get("approval_count"),
            bundle_summary.get("registry_approval_count"),
        ),
        "package_bytes": _first_int(registry_summary.get("package_bytes")),
        "registry_package_sha256": _first_text(
            bundle_summary.get("registry_package_sha256"),
            registry_summary.get("package_sha256"),
        ),
        "palette_section_count": len(_unique_sorted_tokens(section_palette)),
        "palette_family_count": len(_unique_sorted_tokens(palette_families)),
        "palette_family_label": _compact_label(palette_families),
        "active_section_count": len(_unique_sorted_tokens(active_section_ids)),
        "active_family_count": len(_unique_sorted_tokens(active_families)),
        "active_family_label": _compact_label(active_families),
        "member_type_count": len(_unique_sorted_tokens(member_types)),
        "member_type_label": _compact_label(member_types),
        "contract_pass": bool(bundle_payload.get("contract_pass", False)),
        "reason_code": str(bundle_payload.get("reason_code", "") or ""),
        "summary_line": str(bundle_payload.get("summary_line", "") or ""),
        "commercialization_summary_line": (
            f"{family_id}: {commercialization_status.upper()} | score={score} | "
            f"solver_combos={_first_int(bundle_summary.get('solver_combo_count'), solver_summary.get('combo_count'))} | "
            f"mesh_requests={_first_int(bundle_summary.get('solver_mesh_request_count'), solver_summary.get('mesh_request_count'))} | "
            f"approvals={_first_int(registry_summary.get('approved_count'), registry_summary.get('approval_count'))} | "
            f"palette_families={len(_unique_sorted_tokens(palette_families))} | "
            f"active_families={len(_unique_sorted_tokens(active_families))}"
        ),
        "artifacts": dict(bundle_artifacts),
    }


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if (char.isalnum() or char == "_") else "-" for char in str(value or "").strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "family"


def _default_family_rows() -> list[dict[str, Any]]:
    return [
        {
            "family_id": "sample_tower",
            "project_id": "native-authoring-sample-tower",
            "project_name": "Native Authoring Sample Tower",
            "draft_label": "baseline",
            "story_count": 5,
            "bay_count": 3,
            "floor_height_m": 3.9,
            "load_pattern_count": 4,
            "section_id": "steel_h_600x200",
        },
        {
            "family_id": "steel_braced_frame",
            "project_id": "native-authoring-steel-braced",
            "project_name": "Native Authoring Steel Braced",
            "draft_label": "steel-alt",
            "story_count": 8,
            "bay_count": 5,
            "floor_height_m": 3.6,
            "load_pattern_count": 6,
            "section_id": "steel_box_400x400x16",
        },
        {
            "family_id": "rc_wall_core",
            "project_id": "native-authoring-rc-wall-core",
            "project_name": "Native Authoring RC Wall Core",
            "draft_label": "core-residential",
            "story_count": 9,
            "bay_count": 4,
            "floor_height_m": 3.3,
            "load_pattern_count": 6,
            "section_id": "rc_column_700x700",
        },
        {
            "family_id": "composite_podium",
            "project_id": "native-authoring-composite-podium",
            "project_name": "Native Authoring Composite Podium",
            "draft_label": "podium-heavy",
            "story_count": 7,
            "bay_count": 4,
            "floor_height_m": 4.1,
            "load_pattern_count": 6,
            "section_id": "deck_beam_500x250",
        },
        {
            "family_id": "outrigger_transfer_tower",
            "project_id": "native-authoring-outrigger-transfer-tower",
            "project_name": "Native Authoring Outrigger Transfer Tower",
            "draft_label": "outrigger-mixed",
            "story_count": 10,
            "bay_count": 5,
            "floor_height_m": 4.1,
            "load_pattern_count": 6,
            "section_id": "steel_h_600x200",
        },
        {
            "family_id": "dual_system_hospital",
            "project_id": "native-authoring-dual-system-hospital",
            "project_name": "Native Authoring Dual-System Hospital",
            "draft_label": "hospital-mixed",
            "story_count": 8,
            "bay_count": 5,
            "floor_height_m": 4.0,
            "load_pattern_count": 6,
            "section_id": "steel_h_600x200",
        },
        {
            "family_id": "belt_truss_mega_frame",
            "project_id": "native-authoring-belt-truss-mega-frame",
            "project_name": "Native Authoring Belt-Truss Mega Frame",
            "draft_label": "belt-truss-mixed",
            "story_count": 12,
            "bay_count": 6,
            "floor_height_m": 4.2,
            "load_pattern_count": 6,
            "section_id": "steel_h_600x200",
        },
        {
            "family_id": "deep_transfer_basement",
            "project_id": "native-authoring-deep-transfer-basement",
            "project_name": "Native Authoring Deep Transfer Basement",
            "draft_label": "transfer-basement",
            "story_count": 6,
            "bay_count": 4,
            "floor_height_m": 4.4,
            "load_pattern_count": 6,
            "section_id": "steel_h_600x200",
        },
    ]


def _normalize_family_rows(
    *,
    portfolio_payload: dict[str, Any] | list[Any] | None,
    portfolio_name: str,
) -> tuple[str, list[dict[str, Any]]]:
    payload_name = portfolio_name
    if isinstance(portfolio_payload, dict):
        payload_name = str(portfolio_payload.get("portfolio_name", "") or portfolio_name).strip() or portfolio_name
        source_rows = portfolio_payload.get("family_rows")
        if not isinstance(source_rows, list):
            source_rows = portfolio_payload.get("families")
    elif isinstance(portfolio_payload, list):
        source_rows = portfolio_payload
    else:
        source_rows = None

    if not isinstance(source_rows, list):
        source_rows = _default_family_rows()

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows, start=1):
        if not isinstance(row, dict):
            continue
        family_id = _slug(str(row.get("family_id", row.get("project_id", row.get("draft_label", f"family-{index}")))))
        project_id = str(row.get("project_id", "") or f"native-authoring-{family_id}").strip()
        project_name = str(row.get("project_name", "") or f"Native Authoring {family_id}").strip()
        draft_label = str(row.get("draft_label", "") or f"draft-{index}").strip()
        normalized.append(
            {
                "family_id": family_id,
                "authoring_family_id": str(row.get("authoring_family_id", "") or family_id).strip(),
                "project_id": project_id,
                "project_name": project_name,
                "draft_label": draft_label,
                "draft_json_path": str(row.get("draft_json_path", "") or "").strip(),
                "story_count": row.get("story_count"),
                "bay_count": row.get("bay_count"),
                "floor_height_m": row.get("floor_height_m"),
                "load_pattern_count": row.get("load_pattern_count"),
                "section_id": str(row.get("section_id", "") or "").strip(),
            }
        )
    return payload_name, normalized


def _portfolio_job_manifest(*, family_rows: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-ops-portfolio-manifest",
        "generated_at": generated_at,
        "jobs": [
            {
                "job_id": f"native_authoring_portfolio::{row['family_id']}",
                "phase": "authoring_portfolio",
                "benchmark_family": str(row["family_id"]),
                "submission_scope": "family_ops_bundle",
                "lifecycle_status": "planned",
                "input_path": str(row.get("draft_json_path", "") or row["family_id"]),
                "artifact_paths": [],
                "note": f"materialize ops bundle for family={row['family_id']} draft={row['draft_label']}",
            }
            for row in family_rows
        ],
    }


def build_native_authoring_ops_portfolio(
    *,
    portfolio_payload: dict[str, Any] | list[Any] | None = None,
    portfolio_json_path: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    signing_dir: Path = DEFAULT_SIGNING_DIR,
    out: Path = DEFAULT_OUT,
    batch_out: Path = DEFAULT_BATCH_OUT,
    registry_index_out: Path = DEFAULT_REGISTRY_INDEX_OUT,
    registry_workspace_out: Path = DEFAULT_REGISTRY_WORKSPACE_OUT,
    family_tracks_out: Path | None = None,
    runtime_submission_lane_out: Path | None = None,
    runtime_writeback_depth_out: Path | None = None,
    multi_project_runtime_writeback_out: Path | None = None,
    solver_family_breadth_out: Path | None = None,
    local_runtime_scenario_depth_out: Path | None = None,
    local_variant_writeback_trace_out: Path | None = None,
    writeback_breadth_out: Path | None = None,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    generated_at: str | None = None,
    portfolio_name: str = "phase1-native-authoring-ops-portfolio",
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    if portfolio_json_path is not None:
        portfolio_payload = _load_json(portfolio_json_path)
    resolved_portfolio_name, family_rows = _normalize_family_rows(
        portfolio_payload=portfolio_payload,
        portfolio_name=portfolio_name,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    signing_dir.mkdir(parents=True, exist_ok=True)
    resolved_family_tracks_out = family_tracks_out or (out_dir / DEFAULT_FAMILY_TRACKS_OUT.name)
    resolved_runtime_submission_lane_out = runtime_submission_lane_out or (
        out_dir / DEFAULT_RUNTIME_SUBMISSION_LANE_OUT.name
    )
    resolved_runtime_writeback_depth_out = runtime_writeback_depth_out or (
        out_dir / DEFAULT_RUNTIME_WRITEBACK_DEPTH_OUT.name
    )
    resolved_multi_project_runtime_writeback_out = multi_project_runtime_writeback_out or (
        out_dir / DEFAULT_MULTI_PROJECT_RUNTIME_WRITEBACK_OUT.name
    )
    resolved_solver_family_breadth_out = solver_family_breadth_out or (
        out_dir / DEFAULT_SOLVER_FAMILY_BREADTH_OUT.name
    )
    resolved_local_runtime_scenario_depth_out = local_runtime_scenario_depth_out or (
        out_dir / DEFAULT_LOCAL_RUNTIME_SCENARIO_DEPTH_OUT.name
    )
    resolved_local_variant_writeback_trace_out = local_variant_writeback_trace_out or (
        out_dir / DEFAULT_LOCAL_VARIANT_WRITEBACK_TRACE_OUT.name
    )
    resolved_writeback_breadth_out = writeback_breadth_out or (out_dir / DEFAULT_WRITEBACK_BREADTH_OUT.name)

    job_manifest = _portfolio_job_manifest(family_rows=family_rows, generated_at=timestamp)
    updates: list[dict[str, Any]] = []
    emitted_registry_paths: list[Path] = []
    emitted_family_rows: list[dict[str, Any]] = []

    for row in family_rows:
        family_id = str(row["family_id"])
        family_dir = out_dir / family_id
        family_signing_dir = signing_dir / family_id
        family_dir.mkdir(parents=True, exist_ok=True)
        family_signing_dir.mkdir(parents=True, exist_ok=True)

        workspace_summary = family_dir / "native_authoring_workspace_summary.json"
        solver_session = family_dir / "native_authoring_solver_session.json"
        solver_loadcomb = family_dir / "native_authoring_solver_session.loadcomb_preview.mgt"
        job_manifest_out = family_dir / "native_authoring_job_manifest.json"
        batch_report_out = family_dir / "native_authoring_batch_job_report.json"
        project_registry_out = family_dir / "native_authoring_project_registry.json"
        project_package_out = family_dir / "native_authoring_project_package.zip"
        private_key_out = family_signing_dir / "native_authoring_project_registry_ed25519.pem"
        public_key_out = family_signing_dir / "native_authoring_project_registry_ed25519.pub.pem"
        signature_out = family_signing_dir / "native_authoring_project_registry.signature.b64"
        bundle_out = family_dir / "native_authoring_ops_bundle.json"

        bundle_payload = build_native_authoring_workspace_ops_bundle(
            workspace_summary_path=workspace_summary,
            solver_session_out=solver_session,
            solver_loadcomb_out=solver_loadcomb,
            draft_json_path=str(row.get("draft_json_path", "") or None or "") or None,
            story_count=row.get("story_count"),
            bay_count=row.get("bay_count"),
            floor_height_m=row.get("floor_height_m"),
            load_pattern_count=row.get("load_pattern_count"),
            section_id=str(row.get("section_id", "") or "").strip() or None,
            job_manifest_out=job_manifest_out,
            batch_report_out=batch_report_out,
            snapshot_root=family_dir / "snapshots",
            project_registry_out=project_registry_out,
            project_package_out=project_package_out,
            private_key_out=private_key_out,
            public_key_out=public_key_out,
            signature_out=signature_out,
            out=bundle_out,
            generated_at=timestamp,
            project_id=str(row["project_id"]),
            project_name=str(row["project_name"]),
            family_id=family_id,
            authoring_family_id=str(row.get("authoring_family_id", "") or family_id),
            portfolio_name=resolved_portfolio_name,
            draft_label=str(row["draft_label"]),
        )
        if project_registry_out.exists():
            emitted_registry_paths.append(project_registry_out)

        bundle_summary = bundle_payload.get("summary") if isinstance(bundle_payload.get("summary"), dict) else {}
        bundle_artifacts = bundle_payload.get("artifacts") if isinstance(bundle_payload.get("artifacts"), dict) else {}
        emitted_family_rows.append(
            _build_family_commercialization_row(
                family_id=family_id,
                portfolio_name=resolved_portfolio_name,
                row=row,
                bundle_payload=bundle_payload,
                bundle_summary=bundle_summary,
                bundle_artifacts=bundle_artifacts,
                workspace_summary_path=workspace_summary,
                solver_session_path=solver_session,
                batch_report_path=batch_report_out,
                project_registry_path=project_registry_out,
            )
        )
        updates.append(
            {
                "job_id": f"native_authoring_portfolio::{family_id}",
                "lifecycle_status": "completed" if bundle_payload.get("contract_pass", False) else "failed",
                "artifact_paths": [
                    path
                    for path in (
                        str(bundle_out),
                        str(project_registry_out),
                        str(project_package_out),
                        str(batch_report_out),
                    )
                    if Path(path).exists()
                ],
                "note": str(bundle_payload.get("summary_line", "") or ""),
            }
        )

    batch_report = build_batch_job_report(
        job_manifest=job_manifest,
        updates_payload={"updates": updates},
        snapshot_root=snapshot_root,
        out=batch_out,
        generated_at=timestamp,
    )
    registry_index = build_project_registry_index(
        registry_paths=emitted_registry_paths,
        out=registry_index_out,
        workspace_out=registry_workspace_out,
        generated_at=timestamp,
    )
    family_tracks = build_native_authoring_family_tracks(
        family_rows=emitted_family_rows,
        out=resolved_family_tracks_out,
        generated_at=timestamp,
        portfolio_name=resolved_portfolio_name,
    )
    family_tracks_summary = (
        family_tracks.get("summary") if isinstance(family_tracks.get("summary"), dict) else {}
    )
    runtime_submission_lane = build_native_authoring_runtime_submission_lane(
        family_rows=emitted_family_rows,
        track_rows=family_tracks.get("track_rows") if isinstance(family_tracks.get("track_rows"), list) else None,
        out=resolved_runtime_submission_lane_out,
        generated_at=timestamp,
        portfolio_name=resolved_portfolio_name,
    )
    runtime_submission_lane_summary = (
        runtime_submission_lane.get("summary")
        if isinstance(runtime_submission_lane.get("summary"), dict)
        else {}
    )
    runtime_writeback_depth_report = build_native_authoring_runtime_writeback_depth_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        runtime_submission_report=runtime_submission_lane,
        registry_index_report=registry_index,
        portfolio_path=out,
        runtime_submission_path=resolved_runtime_submission_lane_out,
        registry_index_path=registry_index_out,
        out=resolved_runtime_writeback_depth_out,
        generated_at=timestamp,
    )
    runtime_writeback_depth_summary = (
        runtime_writeback_depth_report.get("summary")
        if isinstance(runtime_writeback_depth_report.get("summary"), dict)
        else {}
    )
    multi_project_runtime_writeback_report = build_native_authoring_multi_project_runtime_writeback_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        runtime_submission_report=runtime_submission_lane,
        runtime_writeback_depth_report=runtime_writeback_depth_report,
        registry_workspace_report=_load_dict(registry_workspace_out),
        portfolio_path=out,
        runtime_submission_path=resolved_runtime_submission_lane_out,
        runtime_writeback_depth_path=resolved_runtime_writeback_depth_out,
        registry_workspace_path=registry_workspace_out,
        out=resolved_multi_project_runtime_writeback_out,
        generated_at=timestamp,
    )
    multi_project_runtime_writeback_summary = (
        multi_project_runtime_writeback_report.get("summary")
        if isinstance(multi_project_runtime_writeback_report.get("summary"), dict)
        else {}
    )
    solver_family_breadth_report = build_native_authoring_solver_family_breadth_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        family_tracks_report=family_tracks,
        runtime_submission_report=runtime_submission_lane,
        portfolio_path=out,
        family_tracks_path=resolved_family_tracks_out,
        runtime_submission_path=resolved_runtime_submission_lane_out,
        out=resolved_solver_family_breadth_out,
        generated_at=timestamp,
    )
    solver_family_breadth_summary = (
        solver_family_breadth_report.get("summary")
        if isinstance(solver_family_breadth_report.get("summary"), dict)
        else {}
    )
    local_runtime_scenario_depth_report = build_native_authoring_local_runtime_scenario_depth_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        runtime_submission_report=runtime_submission_lane,
        portfolio_path=out,
        runtime_submission_path=resolved_runtime_submission_lane_out,
        out=resolved_local_runtime_scenario_depth_out,
        generated_at=timestamp,
    )
    local_runtime_scenario_depth_summary = (
        local_runtime_scenario_depth_report.get("summary")
        if isinstance(local_runtime_scenario_depth_report.get("summary"), dict)
        else {}
    )
    local_variant_writeback_trace_report = build_native_authoring_local_variant_writeback_trace_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        portfolio_path=out,
        out=resolved_local_variant_writeback_trace_out,
        generated_at=timestamp,
    )
    local_variant_writeback_trace_summary = (
        local_variant_writeback_trace_report.get("summary")
        if isinstance(local_variant_writeback_trace_report.get("summary"), dict)
        else {}
    )
    writeback_breadth_report = build_native_authoring_writeback_breadth_report(
        portfolio_report={"portfolio_name": resolved_portfolio_name, "family_rows": emitted_family_rows},
        family_tracks_report=family_tracks,
        runtime_submission_report=runtime_submission_lane,
        portfolio_path=out,
        family_tracks_path=resolved_family_tracks_out,
        runtime_submission_path=resolved_runtime_submission_lane_out,
        out=resolved_writeback_breadth_out,
        generated_at=timestamp,
    )
    writeback_breadth_summary = (
        writeback_breadth_report.get("summary")
        if isinstance(writeback_breadth_report.get("summary"), dict)
        else {}
    )

    complete_count = sum(1 for row in emitted_family_rows if bool(row["contract_pass"]))
    ready_count = _first_int(
        family_tracks_summary.get("ready_family_count"),
        sum(1 for row in emitted_family_rows if str(row.get("commercialization_status", "")) == "ready"),
    )
    narrowing_count = _first_int(
        family_tracks_summary.get("narrowing_family_count"),
        sum(1 for row in emitted_family_rows if str(row.get("commercialization_status", "")) == "narrowing"),
    )
    total_combos = sum(int(row["solver_combo_count"]) for row in emitted_family_rows)
    total_mesh_requests = sum(int(row["solver_mesh_request_count"]) for row in emitted_family_rows)
    max_combo_count = max((int(row["solver_combo_count"]) for row in emitted_family_rows), default=0)
    max_mesh_request_count = max((int(row["solver_mesh_request_count"]) for row in emitted_family_rows), default=0)
    max_member_count = max((int(row["member_count"]) for row in emitted_family_rows), default=0)
    family_status_label = _first_text(
        family_tracks_summary.get("family_status_label"),
        _compact_label(
            [
                f"{str(row.get('family_id', 'family'))}:{str(row.get('commercialization_status', 'check'))}"
                for row in emitted_family_rows
            ],
            max_items=6,
        ),
    )
    contract_pass = bool(
        emitted_family_rows
        and complete_count == len(emitted_family_rows)
        and bool(batch_report.get("contract_pass", False))
        and bool(registry_index.get("contract_pass", False))
        and bool(family_tracks.get("contract_pass", False))
        and bool(runtime_submission_lane.get("contract_pass", False))
        and bool(runtime_writeback_depth_report.get("contract_pass", False))
        and bool(multi_project_runtime_writeback_report.get("contract_pass", False))
        and bool(solver_family_breadth_report.get("contract_pass", False))
        and bool(local_runtime_scenario_depth_report.get("contract_pass", False))
        and bool(local_variant_writeback_trace_report.get("contract_pass", False))
        and bool(writeback_breadth_report.get("contract_pass", False))
    )
    reason_code = "PASS" if contract_pass else ("CHECK" if emitted_family_rows else "ERR_INPUT")
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-ops-portfolio",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json_path": str(portfolio_json_path) if portfolio_json_path is not None else "",
            "portfolio_name": resolved_portfolio_name,
            "out_dir": str(out_dir),
            "signing_dir": str(signing_dir),
            "batch_out": str(batch_out),
            "registry_index_out": str(registry_index_out),
            "registry_workspace_out": str(registry_workspace_out),
            "family_tracks_out": str(resolved_family_tracks_out),
            "runtime_submission_lane_out": str(resolved_runtime_submission_lane_out),
            "snapshot_root": str(snapshot_root),
        },
        "summary": {
            "portfolio_name": resolved_portfolio_name,
            "family_count": len(emitted_family_rows),
            "complete_family_count": complete_count,
            "failed_family_count": len(emitted_family_rows) - complete_count,
            "ready_family_count": ready_count,
            "narrowing_family_count": narrowing_count,
            "family_track_count": _first_int(family_tracks_summary.get("family_count"), len(emitted_family_rows)),
            "release_ready_family_count": _first_int(family_tracks_summary.get("release_ready_count")),
            "job_ready_family_count": _first_int(family_tracks_summary.get("job_ready_count")),
            "registry_ready_family_count": _first_int(family_tracks_summary.get("registry_ready_count")),
            "submission_ready_family_count": _first_int(runtime_submission_lane_summary.get("submission_ready_count")),
            "runtime_ready_family_count": _first_int(runtime_submission_lane_summary.get("runtime_ready_count")),
            "writeback_ready_family_count": _first_int(runtime_submission_lane_summary.get("writeback_ready_count")),
            "full_lane_ready_family_count": _first_int(runtime_submission_lane_summary.get("full_ready_count")),
            "runtime_writeback_depth_ready_family_count": _first_int(
                runtime_writeback_depth_summary.get("depth_ready_family_count")
            ),
            "runtime_writeback_depth_targeted_family_count": _first_int(
                runtime_writeback_depth_summary.get("targeted_family_count")
            ),
            "runtime_writeback_depth_snapshot_ready_family_count": _first_int(
                runtime_writeback_depth_summary.get("snapshot_ready_family_count")
            ),
            "multi_project_runtime_writeback_ready_project_count": _first_int(
                multi_project_runtime_writeback_summary.get("ready_project_count")
            ),
            "multi_project_runtime_writeback_full_project_family_count": _first_int(
                multi_project_runtime_writeback_summary.get("full_depth_project_family_count")
            ),
            "multi_project_runtime_writeback_snapshot_ready_project_count": _first_int(
                multi_project_runtime_writeback_summary.get("snapshot_ready_project_count")
            ),
            "solver_family_breadth_ready_family_count": _first_int(
                solver_family_breadth_summary.get("broad_ready_family_count")
            ),
            "solver_family_breadth_full_family_count": _first_int(
                solver_family_breadth_summary.get("full_breadth_family_count")
            ),
            "solver_family_breadth_mesh_broad_family_count": _first_int(
                solver_family_breadth_summary.get("mesh_broad_family_count")
            ),
            "local_runtime_scenario_depth_ready_family_count": _first_int(
                local_runtime_scenario_depth_summary.get("depth_ready_family_count")
            ),
            "local_runtime_scenario_trace_ready_family_count": _first_int(
                local_runtime_scenario_depth_summary.get("trace_ready_family_count")
            ),
            "local_runtime_scenario_mesh_ready_family_count": _first_int(
                local_runtime_scenario_depth_summary.get("mesh_trace_ready_family_count")
            ),
            "local_variant_writeback_trace_ready_family_count": _first_int(
                local_variant_writeback_trace_summary.get("deep_ready_family_count")
            ),
            "local_variant_writeback_trace_targeted_family_count": _first_int(
                local_variant_writeback_trace_summary.get("targeted_family_count")
            ),
            "local_variant_workspace_variant_ready_family_count": _first_int(
                local_variant_writeback_trace_summary.get("workspace_variant_ready_family_count")
            ),
            "local_variant_solver_variant_ready_family_count": _first_int(
                local_variant_writeback_trace_summary.get("solver_variant_ready_family_count")
            ),
            "local_variant_writeback_signed_family_count": _first_int(
                local_variant_writeback_trace_summary.get("signed_writeback_family_count")
            ),
            "writeback_breadth_ready_family_count": _first_int(
                writeback_breadth_summary.get("broad_ready_family_count")
            ),
            "writeback_breadth_full_family_count": _first_int(
                writeback_breadth_summary.get("full_breadth_family_count")
            ),
            "writeback_breadth_mesh_broad_family_count": _first_int(
                writeback_breadth_summary.get("mesh_broad_family_count")
            ),
            "solver_combo_count": total_combos,
            "solver_mesh_request_count": total_mesh_requests,
            "max_solver_combo_count": max_combo_count,
            "max_solver_mesh_request_count": max_mesh_request_count,
            "max_member_count": max_member_count,
            "family_status_label": family_status_label,
            "batch_snapshot_count": int((batch_report.get("summary") or {}).get("snapshot_count", 0) or 0),
            "registry_project_count": int((registry_index.get("summary") or {}).get("project_count", 0) or 0),
            "registry_signature_verified_count": int(
                (registry_index.get("summary") or {}).get("signature_verified_count", 0) or 0
            ),
            "registry_reproducible_count": int(
                (registry_index.get("summary") or {}).get("package_reproducible_count", 0) or 0
            ),
        },
        "family_rows": emitted_family_rows,
        "family_tracks_summary": family_tracks_summary,
        "runtime_submission_lane_summary": runtime_submission_lane_summary,
        "runtime_submission_lane_summary_line": str(runtime_submission_lane.get("summary_line", "") or ""),
        "runtime_writeback_depth_summary": runtime_writeback_depth_summary,
        "runtime_writeback_depth_summary_line": str(
            runtime_writeback_depth_report.get("summary_line", "") or ""
        ),
        "multi_project_runtime_writeback_summary": multi_project_runtime_writeback_summary,
        "multi_project_runtime_writeback_summary_line": str(
            multi_project_runtime_writeback_report.get("summary_line", "") or ""
        ),
        "solver_family_breadth_summary": solver_family_breadth_summary,
        "solver_family_breadth_summary_line": str(solver_family_breadth_report.get("summary_line", "") or ""),
        "local_runtime_scenario_depth_summary": local_runtime_scenario_depth_summary,
        "local_runtime_scenario_depth_summary_line": str(
            local_runtime_scenario_depth_report.get("summary_line", "") or ""
        ),
        "local_variant_writeback_trace_summary": local_variant_writeback_trace_summary,
        "local_variant_writeback_trace_summary_line": str(
            local_variant_writeback_trace_report.get("summary_line", "") or ""
        ),
        "writeback_breadth_summary": writeback_breadth_summary,
        "writeback_breadth_summary_line": str(writeback_breadth_report.get("summary_line", "") or ""),
        "batch_report_summary": batch_report.get("summary", {}),
        "registry_index_summary": registry_index.get("summary", {}),
        "artifacts": {
            "native_authoring_ops_portfolio_json": str(out),
            "native_authoring_ops_portfolio_batch_json": str(batch_out),
            "native_authoring_project_registry_index_json": str(registry_index_out),
            "native_authoring_project_registry_workspace_json": str(registry_workspace_out),
            "native_authoring_family_tracks_json": str(resolved_family_tracks_out),
            "native_authoring_runtime_submission_lane_json": str(resolved_runtime_submission_lane_out),
            "native_authoring_runtime_writeback_depth_report_json": str(
                resolved_runtime_writeback_depth_out
            ),
            "native_authoring_multi_project_runtime_writeback_report_json": str(
                resolved_multi_project_runtime_writeback_out
            ),
            "native_authoring_solver_family_breadth_report_json": str(
                resolved_solver_family_breadth_out
            ),
            "native_authoring_local_runtime_scenario_depth_report_json": str(
                resolved_local_runtime_scenario_depth_out
            ),
            "native_authoring_local_variant_writeback_trace_report_json": str(
                resolved_local_variant_writeback_trace_out
            ),
            "native_authoring_writeback_breadth_report_json": str(resolved_writeback_breadth_out),
            "portfolio_root_dir": str(out_dir),
        },
        "summary_line": (
            "Native authoring ops portfolio: "
            f"{reason_code} | families={len(emitted_family_rows)} | complete={complete_count} | "
            f"ready={ready_count} | job_ready={_first_int(family_tracks_summary.get('job_ready_count'))} | "
            f"submission_ready={_first_int(runtime_submission_lane_summary.get('submission_ready_count'))} | "
            f"writeback_ready={_first_int(runtime_submission_lane_summary.get('writeback_ready_count'))} | "
            f"runtime_writeback_depth={_first_int(runtime_writeback_depth_summary.get('depth_ready_family_count'))} | "
            f"multi_project_runtime={_first_int(multi_project_runtime_writeback_summary.get('ready_project_count'))} | "
            f"solver_family_breadth={_first_int(solver_family_breadth_summary.get('broad_ready_family_count'))} | "
            f"local_runtime_depth={_first_int(local_runtime_scenario_depth_summary.get('depth_ready_family_count'))} | "
            f"local_variant_trace={_first_int(local_variant_writeback_trace_summary.get('deep_ready_family_count'))} | "
            f"writeback_breadth={_first_int(writeback_breadth_summary.get('broad_ready_family_count'))} | "
            f"signature={int((registry_index.get('summary') or {}).get('signature_verified_count', 0) or 0)} | "
            f"combos={total_combos} | snapshots={int((batch_report.get('summary') or {}).get('snapshot_count', 0) or 0)}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": "native authoring portfolio ops artifacts generated" if emitted_family_rows else "no family rows supplied",
    }
    _write_json(out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-json", default="")
    parser.add_argument("--portfolio-name", default="phase1-native-authoring-ops-portfolio")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--signing-dir", default=str(DEFAULT_SIGNING_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--batch-out", default=str(DEFAULT_BATCH_OUT))
    parser.add_argument("--registry-index-out", default=str(DEFAULT_REGISTRY_INDEX_OUT))
    parser.add_argument("--registry-workspace-out", default=str(DEFAULT_REGISTRY_WORKSPACE_OUT))
    parser.add_argument("--family-tracks-out", default="")
    parser.add_argument("--runtime-submission-lane-out", default="")
    parser.add_argument("--runtime-writeback-depth-out", default="")
    parser.add_argument("--multi-project-runtime-writeback-out", default="")
    parser.add_argument("--solver-family-breadth-out", default="")
    parser.add_argument("--local-runtime-scenario-depth-out", default="")
    parser.add_argument("--local-variant-writeback-trace-out", default="")
    parser.add_argument("--writeback-breadth-out", default="")
    parser.add_argument("--snapshot-root", default=str(DEFAULT_SNAPSHOT_ROOT))
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    payload = build_native_authoring_ops_portfolio(
        portfolio_json_path=Path(args.portfolio_json) if str(args.portfolio_json).strip() else None,
        out_dir=Path(args.out_dir),
        signing_dir=Path(args.signing_dir),
        out=Path(args.out),
        batch_out=Path(args.batch_out),
        registry_index_out=Path(args.registry_index_out),
        registry_workspace_out=Path(args.registry_workspace_out),
        family_tracks_out=Path(args.family_tracks_out) if str(args.family_tracks_out).strip() else None,
        runtime_submission_lane_out=(
            Path(args.runtime_submission_lane_out)
            if str(args.runtime_submission_lane_out).strip()
            else None
        ),
        runtime_writeback_depth_out=(
            Path(args.runtime_writeback_depth_out)
            if str(args.runtime_writeback_depth_out).strip()
            else None
        ),
        multi_project_runtime_writeback_out=(
            Path(args.multi_project_runtime_writeback_out)
            if str(args.multi_project_runtime_writeback_out).strip()
            else None
        ),
        solver_family_breadth_out=(
            Path(args.solver_family_breadth_out)
            if str(args.solver_family_breadth_out).strip()
            else None
        ),
        local_runtime_scenario_depth_out=(
            Path(args.local_runtime_scenario_depth_out)
            if str(args.local_runtime_scenario_depth_out).strip()
            else None
        ),
        local_variant_writeback_trace_out=(
            Path(args.local_variant_writeback_trace_out)
            if str(args.local_variant_writeback_trace_out).strip()
            else None
        ),
        writeback_breadth_out=Path(args.writeback_breadth_out) if str(args.writeback_breadth_out).strip() else None,
        snapshot_root=Path(args.snapshot_root),
        generated_at=str(args.generated_at).strip() or None,
        portfolio_name=str(args.portfolio_name).strip() or "phase1-native-authoring-ops-portfolio",
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
