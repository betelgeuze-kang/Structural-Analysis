#!/usr/bin/env python3
"""Generate release-consumable native authoring commercialization tracks by family."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_family_tracks.json"
DEFAULT_PORTFOLIO_NAME = "phase1-native-authoring-ops-portfolio"

REASONS = {
    "PASS": "native authoring family tracks generated",
    "CHECK": "native authoring family tracks generated with incomplete source families",
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


def _mesh_breadth_status(mesh_request_count: int, mesh_cell_count: int) -> str:
    if mesh_request_count >= 2 and mesh_cell_count > 0:
        return "broad"
    if mesh_request_count > 0 or mesh_cell_count > 0:
        return "targeted"
    return "none"


def _solver_combo_status(combo_count: int) -> str:
    if combo_count >= 10:
        return "broad"
    if combo_count > 0:
        return "targeted"
    return "none"


def _resolve_source_rows(
    *,
    family_rows: list[Any] | None,
    portfolio_payload: dict[str, Any] | list[Any] | None,
    portfolio_name: str,
) -> tuple[str, list[dict[str, Any]], str]:
    resolved_portfolio_name = str(portfolio_name or "").strip() or DEFAULT_PORTFOLIO_NAME
    source_mode = "family_rows"
    source_rows: list[Any] = []

    if family_rows is not None:
        source_rows = family_rows
    elif isinstance(portfolio_payload, dict):
        resolved_portfolio_name = _first_text(
            portfolio_payload.get("portfolio_name"),
            (portfolio_payload.get("summary") or {}).get("portfolio_name")
            if isinstance(portfolio_payload.get("summary"), dict)
            else "",
            (portfolio_payload.get("inputs") or {}).get("portfolio_name")
            if isinstance(portfolio_payload.get("inputs"), dict)
            else "",
            resolved_portfolio_name,
        )
        for candidate_key in ("family_rows", "track_rows", "tracks"):
            candidate_rows = portfolio_payload.get(candidate_key)
            if isinstance(candidate_rows, list):
                source_rows = candidate_rows
                source_mode = candidate_key
                break
    elif isinstance(portfolio_payload, list):
        source_rows = portfolio_payload
        source_mode = "list"

    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows, start=1):
        if not isinstance(row, dict):
            continue

        family_id = _first_text(
            row.get("family_id"),
            row.get("authoring_family_id"),
            row.get("project_id"),
            f"family-{index}",
        )
        commercialization_status = _normalize_status(row.get("commercialization_status"))
        job_count = _first_int(row.get("job_count"))
        snapshot_count = _first_int(row.get("snapshot_count"))
        batch_ready = bool(row.get("batch_ready", False))
        job_ready = bool(row.get("job_ready", batch_ready and job_count > 0 and snapshot_count > 0))
        solver_combo_count = _first_int(row.get("solver_combo_count"))
        solver_mesh_request_count = _first_int(row.get("solver_mesh_request_count"))
        solver_mesh_cell_count = _first_int(row.get("solver_mesh_cell_count"))
        solver_combo_status = _solver_combo_status(solver_combo_count)
        mesh_breadth_status = _mesh_breadth_status(solver_mesh_request_count, solver_mesh_cell_count)
        solver_ready = bool(row.get("solver_ready", False))
        ops_ready = bool(row.get("ops_ready", False))
        registry_ready = bool(row.get("registry_ready", False))
        release_ready = bool(
            row.get(
                "release_ready",
                commercialization_status == "ready"
                and solver_ready
                and job_ready
                and registry_ready
                and ops_ready,
            )
        )
        artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), dict) else {}
        track_summary_line = (
            f"{family_id}: {commercialization_status.upper()} | release_ready={release_ready} | "
            f"solver_ready={solver_ready} | job_ready={job_ready} | registry_ready={registry_ready} | "
            f"combos={solver_combo_count} | mesh={solver_mesh_request_count}req/{solver_mesh_cell_count}cells"
        )

        normalized_rows.append(
            {
                "track_id": f"native_authoring_family::{family_id}",
                "family_id": family_id,
                "family_label": _family_label(
                    family_id,
                    _first_text(row.get("family_label")),
                ),
                "portfolio_name": _first_text(row.get("portfolio_name"), resolved_portfolio_name),
                "project_id": _first_text(row.get("project_id")),
                "project_name": _first_text(row.get("project_name")),
                "draft_label": _first_text(row.get("draft_label")),
                "authoring_family_id": _first_text(row.get("authoring_family_id"), family_id),
                "draft_json_path": _first_text(row.get("draft_json_path")),
                "commercialization_status": commercialization_status,
                "commercialization_score": _first_int(row.get("commercialization_score")),
                "release_ready": release_ready,
                "workspace_ready": bool(row.get("workspace_ready", False)),
                "solver_ready": solver_ready,
                "runtime_ready": bool(row.get("runtime_ready", False)),
                "ops_ready": ops_ready,
                "job_ready": job_ready,
                "batch_ready": batch_ready,
                "registry_ready": registry_ready,
                "signature_verified": bool(row.get("signature_verified", False)),
                "story_count": _first_int(row.get("story_count")),
                "node_count": _first_int(row.get("node_count")),
                "member_count": _first_int(row.get("member_count")),
                "load_pattern_count": _first_int(row.get("load_pattern_count")),
                "solver_combo_count": solver_combo_count,
                "solver_combo_status": solver_combo_status,
                "solver_mesh_request_count": solver_mesh_request_count,
                "solver_mesh_cell_count": solver_mesh_cell_count,
                "mesh_breadth_status": mesh_breadth_status,
                "mesh_breadth_label": (
                    f"{solver_mesh_request_count} requests / {solver_mesh_cell_count} cells"
                    if solver_mesh_request_count or solver_mesh_cell_count
                    else "no mesh breadth evidence"
                ),
                "solver_load_case_count": _first_int(row.get("solver_load_case_count")),
                "solver_loadcomb_line_count": _first_int(row.get("solver_loadcomb_line_count")),
                "job_count": job_count,
                "snapshot_count": snapshot_count,
                "approval_count": _first_int(row.get("approval_count")),
                "package_bytes": _first_int(row.get("package_bytes")),
                "registry_package_sha256": _first_text(row.get("registry_package_sha256")),
                "palette_section_count": _first_int(row.get("palette_section_count")),
                "palette_family_count": _first_int(row.get("palette_family_count")),
                "palette_family_label": _first_text(row.get("palette_family_label")),
                "active_section_count": _first_int(row.get("active_section_count")),
                "active_family_count": _first_int(row.get("active_family_count")),
                "active_family_label": _first_text(row.get("active_family_label")),
                "member_type_count": _first_int(row.get("member_type_count")),
                "member_type_label": _first_text(row.get("member_type_label")),
                "contract_pass": bool(row.get("contract_pass", False)),
                "reason_code": _first_text(row.get("reason_code")),
                "summary_line": _first_text(row.get("summary_line")),
                "commercialization_summary_line": _first_text(
                    row.get("commercialization_summary_line"),
                    track_summary_line,
                ),
                "track_summary_line": track_summary_line,
                "artifacts": dict(artifacts),
            }
        )

    return resolved_portfolio_name, normalized_rows, source_mode


def build_native_authoring_family_tracks(
    *,
    family_rows: list[Any] | None = None,
    portfolio_payload: dict[str, Any] | list[Any] | None = None,
    portfolio_json_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
    portfolio_name: str = DEFAULT_PORTFOLIO_NAME,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()
    if portfolio_json_path is not None:
        portfolio_payload = _load_json(portfolio_json_path)

    resolved_portfolio_name, track_rows, source_mode = _resolve_source_rows(
        family_rows=family_rows,
        portfolio_payload=portfolio_payload,
        portfolio_name=portfolio_name,
    )
    complete_count = sum(1 for row in track_rows if bool(row.get("contract_pass", False)))
    ready_count = sum(1 for row in track_rows if str(row.get("commercialization_status", "")) == "ready")
    narrowing_count = sum(1 for row in track_rows if str(row.get("commercialization_status", "")) == "narrowing")
    release_ready_count = sum(1 for row in track_rows if bool(row.get("release_ready", False)))
    solver_ready_count = sum(1 for row in track_rows if bool(row.get("solver_ready", False)))
    job_ready_count = sum(1 for row in track_rows if bool(row.get("job_ready", False)))
    registry_ready_count = sum(1 for row in track_rows if bool(row.get("registry_ready", False)))
    signature_verified_count = sum(1 for row in track_rows if bool(row.get("signature_verified", False)))
    total_solver_combo_count = sum(_first_int(row.get("solver_combo_count")) for row in track_rows)
    total_solver_mesh_request_count = sum(_first_int(row.get("solver_mesh_request_count")) for row in track_rows)
    max_solver_combo_count = max((_first_int(row.get("solver_combo_count")) for row in track_rows), default=0)
    max_solver_mesh_request_count = max(
        (_first_int(row.get("solver_mesh_request_count")) for row in track_rows),
        default=0,
    )
    max_solver_mesh_cell_count = max(
        (_first_int(row.get("solver_mesh_cell_count")) for row in track_rows),
        default=0,
    )
    max_member_count = max((_first_int(row.get("member_count")) for row in track_rows), default=0)
    family_status_label = _compact_label(
        [
            f"{str(row.get('family_id', 'family'))}:{str(row.get('commercialization_status', 'check'))}"
            for row in track_rows
        ],
        max_items=6,
    )
    mesh_status_label = _compact_label(
        [
            f"{str(row.get('family_id', 'family'))}:{str(row.get('mesh_breadth_status', 'none'))}"
            for row in track_rows
        ],
        max_items=6,
    )
    contract_pass = bool(track_rows and complete_count == len(track_rows))
    reason_code = "PASS" if contract_pass else ("CHECK" if track_rows else "ERR_INPUT")

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-family-tracks",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json_path": str(portfolio_json_path) if portfolio_json_path is not None else "",
            "portfolio_name": resolved_portfolio_name,
            "source_mode": source_mode,
            "source_family_count": len(track_rows),
            "out": str(out),
        },
        "summary": {
            "portfolio_name": resolved_portfolio_name,
            "family_count": len(track_rows),
            "complete_family_count": complete_count,
            "ready_family_count": ready_count,
            "narrowing_family_count": narrowing_count,
            "check_family_count": max(len(track_rows) - ready_count - narrowing_count, 0),
            "release_ready_count": release_ready_count,
            "solver_ready_count": solver_ready_count,
            "job_ready_count": job_ready_count,
            "registry_ready_count": registry_ready_count,
            "signature_verified_count": signature_verified_count,
            "total_solver_combo_count": total_solver_combo_count,
            "total_solver_mesh_request_count": total_solver_mesh_request_count,
            "max_solver_combo_count": max_solver_combo_count,
            "max_solver_mesh_request_count": max_solver_mesh_request_count,
            "max_solver_mesh_cell_count": max_solver_mesh_cell_count,
            "max_member_count": max_member_count,
            "family_status_label": family_status_label,
            "mesh_status_label": mesh_status_label,
        },
        "track_rows": track_rows,
        "artifacts": {
            "native_authoring_family_tracks_json": str(out),
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
        },
        "summary_line": (
            "Native authoring family tracks: "
            f"{reason_code} | families={len(track_rows)} | ready={ready_count} | "
            f"release_ready={release_ready_count} | job_ready={job_ready_count} | "
            f"registry_ready={registry_ready_count} | combos={total_solver_combo_count}"
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
    parser.add_argument("--portfolio-name", default=DEFAULT_PORTFOLIO_NAME)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    portfolio_json_path = Path(args.portfolio_json) if str(args.portfolio_json).strip() else None
    payload = build_native_authoring_family_tracks(
        portfolio_json_path=portfolio_json_path,
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
        portfolio_name=str(args.portfolio_name).strip() or DEFAULT_PORTFOLIO_NAME,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
