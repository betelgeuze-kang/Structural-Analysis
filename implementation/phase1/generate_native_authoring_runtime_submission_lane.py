#!/usr/bin/env python3
"""Generate a native authoring runtime/submission/writeback lane artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_FAMILY_TRACKS_JSON = DEFAULT_OUT_DIR / "native_authoring_family_tracks.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_PORTFOLIO_NAME = "phase1-native-authoring-ops-portfolio"

REASONS = {
    "PASS": "native authoring runtime submission lane generated",
    "CHECK": "native authoring runtime submission lane generated with incomplete source surfaces",
    "ERR_INPUT": "no native authoring family rows supplied",
}


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


def _family_label(family_id: str, explicit_label: str) -> str:
    if explicit_label.strip():
        return explicit_label.strip()
    tokens = [token for token in str(family_id).replace("-", "_").split("_") if token]
    return " ".join(token.capitalize() for token in tokens) or "Family"


def _normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ready", "narrowing", "check"}:
        return normalized
    return "check"


def _artifact_present(path_value: Any) -> bool:
    path_text = _first_text(path_value)
    return bool(path_text and Path(path_text).exists())


def _extract_rows(
    payload: dict[str, Any] | list[Any] | None,
    *,
    keys: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str]:
    if isinstance(payload, dict):
        for key in keys:
            candidate_rows = payload.get(key)
            if isinstance(candidate_rows, list):
                return [row for row in candidate_rows if isinstance(row, dict)], key
        return [], "missing"
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], "list"
    return [], "none"


def _portfolio_name_from_payload(payload: dict[str, Any] | list[Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    return _first_text(
        payload.get("portfolio_name"),
        summary.get("portfolio_name"),
        inputs.get("portfolio_name"),
    )


def _row_family_id(row: dict[str, Any], index: int) -> str:
    return _first_text(
        row.get("family_id"),
        row.get("authoring_family_id"),
        row.get("project_id"),
        f"family-{index}",
    )


def _merge_artifacts(*artifact_maps: dict[str, Any]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for artifact_map in artifact_maps:
        for key, value in artifact_map.items():
            text = _first_text(value)
            if text:
                merged[str(key)] = text
    return merged


def _axis_status(*, ready: bool, partial: bool) -> str:
    if ready:
        return "ready"
    if partial:
        return "narrowing"
    return "check"


def _build_family_lane_row(
    *,
    family_id: str,
    portfolio_row: dict[str, Any],
    track_row: dict[str, Any],
    portfolio_name: str,
) -> dict[str, Any]:
    artifacts = _merge_artifacts(
        track_row.get("artifacts") if isinstance(track_row.get("artifacts"), dict) else {},
        portfolio_row.get("artifacts") if isinstance(portfolio_row.get("artifacts"), dict) else {},
    )
    family_label = _family_label(
        family_id,
        _first_text(track_row.get("family_label"), portfolio_row.get("family_label")),
    )
    commercialization_status = _normalize_status(
        _first_text(track_row.get("commercialization_status"), portfolio_row.get("commercialization_status")),
    )
    workspace_ready = bool(track_row.get("workspace_ready", portfolio_row.get("workspace_ready", False)))
    solver_ready = bool(track_row.get("solver_ready", portfolio_row.get("solver_ready", False)))
    native_runtime_ready = bool(track_row.get("runtime_ready", portfolio_row.get("runtime_ready", False)))
    ops_ready = bool(track_row.get("ops_ready", portfolio_row.get("ops_ready", False)))
    batch_ready = bool(track_row.get("batch_ready", portfolio_row.get("batch_ready", False)))
    release_ready = bool(track_row.get("release_ready", False))
    job_ready = bool(track_row.get("job_ready", batch_ready))
    registry_ready = bool(track_row.get("registry_ready", portfolio_row.get("registry_ready", False)))
    signature_verified = bool(
        track_row.get("signature_verified", portfolio_row.get("signature_verified", False))
    )

    solver_combo_count = _first_int(track_row.get("solver_combo_count"), portfolio_row.get("solver_combo_count"))
    solver_mesh_request_count = _first_int(
        track_row.get("solver_mesh_request_count"),
        portfolio_row.get("solver_mesh_request_count"),
    )
    solver_mesh_cell_count = _first_int(
        track_row.get("solver_mesh_cell_count"),
        portfolio_row.get("solver_mesh_cell_count"),
    )
    solver_load_case_count = _first_int(
        track_row.get("solver_load_case_count"),
        portfolio_row.get("solver_load_case_count"),
    )
    solver_loadcomb_line_count = _first_int(
        track_row.get("solver_loadcomb_line_count"),
        portfolio_row.get("solver_loadcomb_line_count"),
    )
    job_count = _first_int(track_row.get("job_count"), portfolio_row.get("job_count"))
    snapshot_count = _first_int(track_row.get("snapshot_count"), portfolio_row.get("snapshot_count"))
    approval_count = _first_int(track_row.get("approval_count"), portfolio_row.get("approval_count"))
    registry_package_sha256 = _first_text(
        track_row.get("registry_package_sha256"),
        portfolio_row.get("registry_package_sha256"),
    )

    solver_session_present = any(
        _artifact_present(artifacts.get(key))
        for key in ("solver_session_json", "solver_session_artifact_json")
    )
    loadcomb_preview_present = any(
        _artifact_present(artifacts.get(key))
        for key in ("solver_loadcomb_preview_mgt", "loadcomb_preview_mgt")
    )
    job_manifest_present = _artifact_present(artifacts.get("job_manifest_json"))
    batch_report_present = _artifact_present(artifacts.get("batch_job_report_json"))
    registry_json_present = _artifact_present(artifacts.get("project_registry_json"))
    project_package_present = _artifact_present(artifacts.get("project_package_zip"))
    signature_artifact_present = _artifact_present(artifacts.get("project_registry_signature"))
    public_key_present = _artifact_present(artifacts.get("project_registry_public_key"))

    runtime_ready = bool(
        workspace_ready
        and solver_ready
        and native_runtime_ready
        and solver_combo_count > 0
        and solver_loadcomb_line_count > 0
        and solver_session_present
        and loadcomb_preview_present
    )
    submission_ready = bool(
        release_ready
        and job_ready
        and ops_ready
        and job_manifest_present
        and batch_report_present
        and job_count > 0
        and snapshot_count > 0
    )
    writeback_ready = bool(
        registry_ready
        and signature_verified
        and approval_count > 0
        and bool(registry_package_sha256)
        and registry_json_present
        and project_package_present
        and signature_artifact_present
    )

    submission_status = _axis_status(
        ready=submission_ready,
        partial=bool(release_ready or job_ready or ops_ready or job_count > 0 or snapshot_count > 0),
    )
    runtime_status = _axis_status(
        ready=runtime_ready,
        partial=bool(
            workspace_ready
            or solver_ready
            or native_runtime_ready
            or solver_combo_count > 0
            or solver_session_present
            or loadcomb_preview_present
        ),
    )
    writeback_status = _axis_status(
        ready=writeback_ready,
        partial=bool(
            registry_ready
            or signature_verified
            or approval_count > 0
            or bool(registry_package_sha256)
            or registry_json_present
            or project_package_present
            or signature_artifact_present
        ),
    )

    lane_status = "ready"
    if not (submission_ready and runtime_ready and writeback_ready):
        lane_status = "narrowing" if any(
            status in {"ready", "narrowing"}
            for status in (submission_status, runtime_status, writeback_status)
        ) else "check"

    portfolio_row_present = bool(portfolio_row)
    track_row_present = bool(track_row)
    source_surface_complete = bool(portfolio_row_present and track_row_present)
    contract_pass = bool(
        source_surface_complete
        and portfolio_row.get("contract_pass", False)
        and track_row.get("contract_pass", False)
    )
    reason_code = "PASS" if contract_pass else "CHECK"

    return {
        "lane_id": f"native_authoring_runtime_submission::{family_id}",
        "family_id": family_id,
        "family_label": family_label,
        "portfolio_name": _first_text(
            track_row.get("portfolio_name"),
            portfolio_row.get("portfolio_name"),
            portfolio_name,
        ),
        "project_id": _first_text(track_row.get("project_id"), portfolio_row.get("project_id")),
        "project_name": _first_text(track_row.get("project_name"), portfolio_row.get("project_name")),
        "draft_label": _first_text(track_row.get("draft_label"), portfolio_row.get("draft_label")),
        "authoring_family_id": _first_text(
            track_row.get("authoring_family_id"),
            portfolio_row.get("authoring_family_id"),
            family_id,
        ),
        "commercialization_status": commercialization_status,
        "commercialization_score": _first_int(
            track_row.get("commercialization_score"),
            portfolio_row.get("commercialization_score"),
        ),
        "lane_status": lane_status,
        "portfolio_row_present": portfolio_row_present,
        "family_track_row_present": track_row_present,
        "source_surface_complete": source_surface_complete,
        "submission_ready": submission_ready,
        "submission_status": submission_status,
        "runtime_ready": runtime_ready,
        "runtime_status": runtime_status,
        "writeback_ready": writeback_ready,
        "writeback_status": writeback_status,
        "workspace_ready": workspace_ready,
        "solver_ready": solver_ready,
        "native_runtime_ready": native_runtime_ready,
        "ops_ready": ops_ready,
        "release_ready": release_ready,
        "job_ready": job_ready,
        "batch_ready": batch_ready,
        "registry_ready": registry_ready,
        "signature_verified": signature_verified,
        "solver_session_present": solver_session_present,
        "loadcomb_preview_present": loadcomb_preview_present,
        "job_manifest_present": job_manifest_present,
        "batch_report_present": batch_report_present,
        "registry_json_present": registry_json_present,
        "project_package_present": project_package_present,
        "signature_artifact_present": signature_artifact_present,
        "public_key_present": public_key_present,
        "story_count": _first_int(track_row.get("story_count"), portfolio_row.get("story_count")),
        "node_count": _first_int(track_row.get("node_count"), portfolio_row.get("node_count")),
        "member_count": _first_int(track_row.get("member_count"), portfolio_row.get("member_count")),
        "load_pattern_count": _first_int(
            track_row.get("load_pattern_count"),
            portfolio_row.get("load_pattern_count"),
        ),
        "solver_combo_count": solver_combo_count,
        "solver_combo_status": _first_text(track_row.get("solver_combo_status")),
        "solver_mesh_request_count": solver_mesh_request_count,
        "solver_mesh_cell_count": solver_mesh_cell_count,
        "mesh_breadth_status": _first_text(track_row.get("mesh_breadth_status")),
        "solver_load_case_count": solver_load_case_count,
        "solver_loadcomb_line_count": solver_loadcomb_line_count,
        "job_count": job_count,
        "snapshot_count": snapshot_count,
        "approval_count": approval_count,
        "package_bytes": _first_int(track_row.get("package_bytes"), portfolio_row.get("package_bytes")),
        "registry_package_sha256": registry_package_sha256,
        "palette_family_count": _first_int(
            track_row.get("palette_family_count"),
            portfolio_row.get("palette_family_count"),
        ),
        "palette_family_label": _first_text(
            track_row.get("palette_family_label"),
            portfolio_row.get("palette_family_label"),
        ),
        "active_family_count": _first_int(
            track_row.get("active_family_count"),
            portfolio_row.get("active_family_count"),
        ),
        "active_family_label": _first_text(
            track_row.get("active_family_label"),
            portfolio_row.get("active_family_label"),
        ),
        "member_type_count": _first_int(
            track_row.get("member_type_count"),
            portfolio_row.get("member_type_count"),
        ),
        "member_type_label": _first_text(
            track_row.get("member_type_label"),
            portfolio_row.get("member_type_label"),
        ),
        "source_summary_line": _first_text(portfolio_row.get("summary_line")),
        "track_summary_line": _first_text(track_row.get("track_summary_line"), track_row.get("summary_line")),
        "commercialization_summary_line": _first_text(
            track_row.get("commercialization_summary_line"),
            portfolio_row.get("commercialization_summary_line"),
        ),
        "summary_line": (
            f"{family_id}: submission={submission_status.upper()} | runtime={runtime_status.upper()} | "
            f"writeback={writeback_status.upper()} | release_ready={release_ready} | "
            f"combos={solver_combo_count} | approvals={approval_count}"
        ),
        "artifacts": artifacts,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
    }


def build_native_authoring_runtime_submission_lane(
    *,
    family_rows: list[Any] | None = None,
    track_rows: list[Any] | None = None,
    portfolio_payload: dict[str, Any] | list[Any] | None = None,
    track_payload: dict[str, Any] | list[Any] | None = None,
    portfolio_json_path: Path | None = None,
    family_tracks_json_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
    portfolio_name: str = DEFAULT_PORTFOLIO_NAME,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    if portfolio_json_path is not None:
        portfolio_payload = _load_json(portfolio_json_path)
    if family_tracks_json_path is not None:
        track_payload = _load_json(family_tracks_json_path)

    if family_rows is None:
        family_rows, portfolio_source_mode = _extract_rows(
            portfolio_payload,
            keys=("family_rows", "track_rows", "tracks"),
        )
    else:
        family_rows = [row for row in family_rows if isinstance(row, dict)]
        portfolio_source_mode = "family_rows"
    if track_rows is None:
        track_rows, family_track_source_mode = _extract_rows(
            track_payload,
            keys=("track_rows", "family_rows", "tracks"),
        )
    else:
        track_rows = [row for row in track_rows if isinstance(row, dict)]
        family_track_source_mode = "track_rows"

    explicit_portfolio_name = str(portfolio_name or "").strip()
    resolved_portfolio_name = _first_text(
        explicit_portfolio_name if explicit_portfolio_name != DEFAULT_PORTFOLIO_NAME else "",
        _portfolio_name_from_payload(portfolio_payload),
        _portfolio_name_from_payload(track_payload),
        explicit_portfolio_name,
        DEFAULT_PORTFOLIO_NAME,
    )

    portfolio_rows_by_family = {
        _row_family_id(row, index): row
        for index, row in enumerate(family_rows, start=1)
        if _row_family_id(row, index)
    }
    track_rows_by_family = {
        _row_family_id(row, index): row
        for index, row in enumerate(track_rows, start=1)
        if _row_family_id(row, index)
    }

    ordered_family_ids = list(portfolio_rows_by_family.keys())
    for family_id in track_rows_by_family:
        if family_id not in portfolio_rows_by_family:
            ordered_family_ids.append(family_id)

    lane_rows = [
        _build_family_lane_row(
            family_id=family_id,
            portfolio_row=portfolio_rows_by_family.get(family_id, {}),
            track_row=track_rows_by_family.get(family_id, {}),
            portfolio_name=resolved_portfolio_name,
        )
        for family_id in ordered_family_ids
    ]

    complete_source_family_count = sum(1 for row in lane_rows if bool(row["source_surface_complete"]))
    contract_pass_family_count = sum(1 for row in lane_rows if bool(row["contract_pass"]))
    submission_ready_count = sum(1 for row in lane_rows if bool(row["submission_ready"]))
    runtime_ready_count = sum(1 for row in lane_rows if bool(row["runtime_ready"]))
    writeback_ready_count = sum(1 for row in lane_rows if bool(row["writeback_ready"]))
    full_ready_count = sum(
        1
        for row in lane_rows
        if bool(row["submission_ready"] and row["runtime_ready"] and row["writeback_ready"])
    )
    release_ready_count = sum(1 for row in lane_rows if bool(row["release_ready"]))
    job_ready_count = sum(1 for row in lane_rows if bool(row["job_ready"]))
    registry_ready_count = sum(1 for row in lane_rows if bool(row["registry_ready"]))
    signature_verified_count = sum(1 for row in lane_rows if bool(row["signature_verified"]))
    total_solver_combo_count = sum(_first_int(row.get("solver_combo_count")) for row in lane_rows)
    total_solver_mesh_request_count = sum(
        _first_int(row.get("solver_mesh_request_count"))
        for row in lane_rows
    )
    total_approval_count = sum(_first_int(row.get("approval_count")) for row in lane_rows)

    family_status_label = _compact_label(
        [f"{row['family_id']}:{row['lane_status']}" for row in lane_rows],
        max_items=6,
    )
    submission_status_label = _compact_label(
        [f"{row['family_id']}:{row['submission_status']}" for row in lane_rows],
        max_items=6,
    )
    runtime_status_label = _compact_label(
        [f"{row['family_id']}:{row['runtime_status']}" for row in lane_rows],
        max_items=6,
    )
    writeback_status_label = _compact_label(
        [f"{row['family_id']}:{row['writeback_status']}" for row in lane_rows],
        max_items=6,
    )

    contract_pass = bool(
        lane_rows
        and complete_source_family_count == len(lane_rows)
        and contract_pass_family_count == len(lane_rows)
    )
    reason_code = "PASS" if contract_pass else ("CHECK" if lane_rows else "ERR_INPUT")

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-runtime-submission-lane",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json_path": str(portfolio_json_path) if portfolio_json_path is not None else "",
            "family_tracks_json_path": (
                str(family_tracks_json_path) if family_tracks_json_path is not None else ""
            ),
            "portfolio_name": resolved_portfolio_name,
            "portfolio_source_mode": portfolio_source_mode,
            "family_track_source_mode": family_track_source_mode,
            "portfolio_family_count": len(portfolio_rows_by_family),
            "family_track_count": len(track_rows_by_family),
            "out": str(out),
        },
        "summary": {
            "portfolio_name": resolved_portfolio_name,
            "family_count": len(lane_rows),
            "complete_source_family_count": complete_source_family_count,
            "contract_pass_family_count": contract_pass_family_count,
            "submission_ready_count": submission_ready_count,
            "runtime_ready_count": runtime_ready_count,
            "writeback_ready_count": writeback_ready_count,
            "full_ready_count": full_ready_count,
            "release_ready_count": release_ready_count,
            "job_ready_count": job_ready_count,
            "registry_ready_count": registry_ready_count,
            "signature_verified_count": signature_verified_count,
            "total_solver_combo_count": total_solver_combo_count,
            "total_solver_mesh_request_count": total_solver_mesh_request_count,
            "total_approval_count": total_approval_count,
            "family_status_label": family_status_label,
            "submission_status_label": submission_status_label,
            "runtime_status_label": runtime_status_label,
            "writeback_status_label": writeback_status_label,
        },
        "family_rows": lane_rows,
        "artifacts": {
            "native_authoring_runtime_submission_lane_json": str(out),
            "source_native_authoring_ops_portfolio_json": (
                str(portfolio_json_path)
                if portfolio_json_path is not None
                else _first_text(
                    (portfolio_payload.get("artifacts") or {}).get("native_authoring_ops_portfolio_json")
                    if isinstance(portfolio_payload, dict)
                    and isinstance(portfolio_payload.get("artifacts"), dict)
                    else ""
                )
            ),
            "source_native_authoring_family_tracks_json": (
                str(family_tracks_json_path)
                if family_tracks_json_path is not None
                else _first_text(
                    (track_payload.get("artifacts") or {}).get("native_authoring_family_tracks_json")
                    if isinstance(track_payload, dict)
                    and isinstance(track_payload.get("artifacts"), dict)
                    else ""
                )
            ),
        },
        "summary_line": (
            "Native authoring runtime submission lane: "
            f"{reason_code} | families={len(lane_rows)} | submission_ready={submission_ready_count} | "
            f"runtime_ready={runtime_ready_count} | writeback_ready={writeback_ready_count} | "
            f"full_ready={full_ready_count} | approvals={total_approval_count}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    _write_json(out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-json", default=str(DEFAULT_PORTFOLIO_JSON))
    parser.add_argument("--family-tracks-json", default=str(DEFAULT_FAMILY_TRACKS_JSON))
    parser.add_argument("--portfolio-name", default=DEFAULT_PORTFOLIO_NAME)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    portfolio_json_path = Path(args.portfolio_json) if str(args.portfolio_json).strip() else None
    family_tracks_json_path = Path(args.family_tracks_json) if str(args.family_tracks_json).strip() else None
    payload = build_native_authoring_runtime_submission_lane(
        portfolio_json_path=portfolio_json_path,
        family_tracks_json_path=family_tracks_json_path,
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
        portfolio_name=str(args.portfolio_name).strip() or DEFAULT_PORTFOLIO_NAME,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
