#!/usr/bin/env python3
"""Generate native authoring solver family breadth coverage report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_FAMILY_TRACKS_JSON = DEFAULT_OUT_DIR / "native_authoring_family_tracks.json"
DEFAULT_RUNTIME_SUBMISSION_JSON = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_solver_family_breadth_report.json"

REASONS = {
    "PASS": "native authoring solver family breadth report generated",
    "CHECK": "native authoring solver family breadth report generated with partial coverage",
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


def _first_bool(*values: Any) -> bool | None:
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "false"}:
            return text == "true"
    return None


def _unique_sorted_tokens(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _compact_label(values: list[str], max_items: int = 4) -> str:
    normalized = _unique_sorted_tokens(values)
    if not normalized:
        return ""
    if len(normalized) <= max_items:
        return ", ".join(normalized)
    return f"{', '.join(normalized[:max_items])} +{len(normalized) - max_items}"


def _extract_rows(
    payload: dict[str, Any] | list[Any] | None,
    *,
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in keys:
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [row for row in candidate if isinstance(row, dict)]
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _family_id(row: dict[str, Any], index: int) -> str:
    return _first_text(
        row.get("family_id"),
        row.get("authoring_family_id"),
        row.get("project_id"),
        f"family-{index}",
    )


def _status_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"ready", "broad", "pass"}:
        return "ready"
    if token in {"targeted", "narrowing", "partial"}:
        return "narrowing"
    if token in {"check", "none"}:
        return "check"
    return token


def _derive_combo_status(combo_count: int, combo_status: str) -> str:
    if combo_status:
        return combo_status
    if combo_count >= 12:
        return "broad"
    if combo_count > 0:
        return "targeted"
    return "none"


def _derive_mesh_status(mesh_request_count: int, mesh_cell_count: int, mesh_status: str) -> str:
    if mesh_status:
        return mesh_status
    if mesh_request_count >= 2 and mesh_cell_count > 0:
        return "broad"
    if mesh_request_count > 0 or mesh_cell_count > 0:
        return "targeted"
    return "none"


def _merge_artifacts(*artifact_maps: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for artifact_map in artifact_maps:
        if not isinstance(artifact_map, dict):
            continue
        for key, value in artifact_map.items():
            text = _first_text(value)
            if text:
                merged[str(key)] = text
    return merged


def build_native_authoring_solver_family_breadth_report(
    *,
    portfolio_report: dict[str, Any] | list[Any] | None = None,
    family_tracks_report: dict[str, Any] | list[Any] | None = None,
    runtime_submission_report: dict[str, Any] | list[Any] | None = None,
    portfolio_path: Path | None = None,
    family_tracks_path: Path | None = None,
    runtime_submission_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()

    portfolio_rows = _extract_rows(portfolio_report, keys=("family_rows", "families"))
    family_track_rows = _extract_rows(family_tracks_report, keys=("track_rows", "family_rows", "tracks"))
    runtime_rows = _extract_rows(runtime_submission_report, keys=("family_rows", "submission_rows", "rows"))

    portfolio_by_family = {
        _family_id(row, index): row for index, row in enumerate(portfolio_rows, start=1) if _family_id(row, index)
    }
    track_by_family = {
        _family_id(row, index): row for index, row in enumerate(family_track_rows, start=1) if _family_id(row, index)
    }
    runtime_by_family = {
        _family_id(row, index): row for index, row in enumerate(runtime_rows, start=1) if _family_id(row, index)
    }

    family_ids = sorted(set(portfolio_by_family) | set(track_by_family) | set(runtime_by_family))
    emitted_rows: list[dict[str, Any]] = []

    for family_id in family_ids:
        portfolio_row = portfolio_by_family.get(family_id, {})
        track_row = track_by_family.get(family_id, {})
        runtime_row = runtime_by_family.get(family_id, {})
        family_label = _first_text(
            runtime_row.get("family_label"),
            track_row.get("family_label"),
            portfolio_row.get("family_label"),
            family_id.replace("_", " "),
        )
        solver_combo_count = _first_int(
            runtime_row.get("solver_combo_count"),
            track_row.get("solver_combo_count"),
            portfolio_row.get("solver_combo_count"),
        )
        solver_combo_status = _derive_combo_status(
            solver_combo_count,
            _first_text(
                runtime_row.get("solver_combo_status"),
                track_row.get("solver_combo_status"),
                portfolio_row.get("solver_combo_status"),
            ),
        )
        solver_mesh_request_count = _first_int(
            runtime_row.get("solver_mesh_request_count"),
            track_row.get("solver_mesh_request_count"),
            portfolio_row.get("solver_mesh_request_count"),
        )
        solver_mesh_cell_count = _first_int(
            runtime_row.get("solver_mesh_cell_count"),
            track_row.get("solver_mesh_cell_count"),
            portfolio_row.get("solver_mesh_cell_count"),
        )
        mesh_breadth_status = _derive_mesh_status(
            solver_mesh_request_count,
            solver_mesh_cell_count,
            _first_text(
                runtime_row.get("mesh_breadth_status"),
                track_row.get("mesh_breadth_status"),
                portfolio_row.get("mesh_breadth_status"),
            ),
        )
        member_type_count = _first_int(
            runtime_row.get("member_type_count"),
            track_row.get("member_type_count"),
            portfolio_row.get("member_type_count"),
        )
        member_type_label = _first_text(
            runtime_row.get("member_type_label"),
            track_row.get("member_type_label"),
            portfolio_row.get("member_type_label"),
        )
        palette_family_count = _first_int(
            runtime_row.get("palette_family_count"),
            track_row.get("palette_family_count"),
            portfolio_row.get("palette_family_count"),
        )
        active_family_count = _first_int(
            runtime_row.get("active_family_count"),
            track_row.get("active_family_count"),
            portfolio_row.get("active_family_count"),
        )
        active_family_label = _first_text(
            runtime_row.get("active_family_label"),
            track_row.get("active_family_label"),
            portfolio_row.get("active_family_label"),
        )
        runtime_ready = bool(
            _first_bool(
                runtime_row.get("runtime_ready"),
                runtime_row.get("native_runtime_ready"),
                track_row.get("runtime_ready"),
                portfolio_row.get("runtime_ready"),
            )
        )
        solver_ready = bool(
            _first_bool(
                runtime_row.get("solver_ready"),
                runtime_row.get("runtime_ready"),
                track_row.get("solver_ready"),
                portfolio_row.get("solver_ready"),
                runtime_row.get("contract_pass"),
                track_row.get("contract_pass"),
            )
        )
        release_ready = bool(
            _first_bool(
                runtime_row.get("release_ready"),
                runtime_row.get("submission_ready"),
                track_row.get("release_ready"),
                portfolio_row.get("release_ready"),
            )
        )
        signature_verified = bool(
            _first_bool(
                runtime_row.get("signature_verified"),
                track_row.get("signature_verified"),
                portfolio_row.get("signature_verified"),
            )
        )

        combo_breadth_ready = solver_combo_status == "broad"
        mesh_coverage_ready = mesh_breadth_status in {"broad", "targeted"}
        member_family_breadth_ready = member_type_count >= 2
        palette_breadth_ready = palette_family_count >= 3
        active_multi_family_ready = active_family_count >= 2
        broad_solver_family_ready = bool(
            solver_ready
            and runtime_ready
            and release_ready
            and signature_verified
            and combo_breadth_ready
            and mesh_coverage_ready
            and member_family_breadth_ready
            and palette_breadth_ready
        )
        full_solver_family_ready = bool(
            broad_solver_family_ready
            and mesh_breadth_status == "broad"
            and active_multi_family_ready
        )
        solver_family_breadth_status = (
            "broad"
            if broad_solver_family_ready
            else "targeted"
            if solver_ready and combo_breadth_ready and mesh_coverage_ready
            else _status_token(
                runtime_row.get("solver_family_breadth_status")
                or track_row.get("solver_family_breadth_status")
                or portfolio_row.get("solver_family_breadth_status")
                or "check"
            )
        )
        scope_axes_label = " | ".join(
            [
                f"combo={solver_combo_status or 'none'}:{solver_combo_count}",
                f"mesh={mesh_breadth_status or 'none'}:{solver_mesh_request_count}",
                f"member_types={member_type_count}",
                f"active={active_family_count}",
                f"palette={palette_family_count}",
            ]
        )
        artifacts = _merge_artifacts(
            portfolio_row.get("artifacts"),
            track_row.get("artifacts"),
            runtime_row.get("artifacts"),
        )
        emitted_rows.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "solver_family_breadth_status": solver_family_breadth_status,
                "solver_ready": solver_ready,
                "runtime_ready": runtime_ready,
                "release_ready": release_ready,
                "signature_verified": signature_verified,
                "combo_breadth_ready": combo_breadth_ready,
                "mesh_coverage_ready": mesh_coverage_ready,
                "member_family_breadth_ready": member_family_breadth_ready,
                "palette_breadth_ready": palette_breadth_ready,
                "active_multi_family_ready": active_multi_family_ready,
                "broad_solver_family_ready": broad_solver_family_ready,
                "full_solver_family_ready": full_solver_family_ready,
                "solver_combo_count": solver_combo_count,
                "solver_combo_status": solver_combo_status,
                "solver_mesh_request_count": solver_mesh_request_count,
                "solver_mesh_cell_count": solver_mesh_cell_count,
                "mesh_breadth_status": mesh_breadth_status,
                "member_type_count": member_type_count,
                "member_type_label": member_type_label,
                "palette_family_count": palette_family_count,
                "active_family_count": active_family_count,
                "active_family_label": active_family_label,
                "scope_axes_label": scope_axes_label,
                "summary_line": (
                    f"{family_id}: {solver_family_breadth_status.upper()} | "
                    f"combo={solver_combo_status}:{solver_combo_count} | "
                    f"mesh={mesh_breadth_status}:{solver_mesh_request_count} | "
                    f"member_types={member_type_count} | active={active_family_count} | "
                    f"palette={palette_family_count}"
                ),
                "artifacts": artifacts,
            }
        )

    runtime_summary = (
        runtime_submission_report.get("summary")
        if isinstance(runtime_submission_report, dict) and isinstance(runtime_submission_report.get("summary"), dict)
        else {}
    )
    queued_submission_count = _first_int(
        runtime_summary.get("queued_submission_count"),
        runtime_summary.get("queue_count"),
    )
    solver_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("solver_ready", False)))
    broad_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("broad_solver_family_ready", False)))
    full_breadth_family_count = sum(1 for row in emitted_rows if bool(row.get("full_solver_family_ready", False)))
    runtime_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("runtime_ready", False)))
    release_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("release_ready", False)))
    combo_broad_family_count = sum(1 for row in emitted_rows if bool(row.get("combo_breadth_ready", False)))
    mesh_coverage_family_count = sum(1 for row in emitted_rows if bool(row.get("mesh_coverage_ready", False)))
    mesh_broad_family_count = sum(
        1 for row in emitted_rows if str(row.get("mesh_breadth_status", "")).strip().lower() == "broad"
    )
    member_multi_family_count = sum(
        1 for row in emitted_rows if bool(row.get("member_family_breadth_ready", False))
    )
    palette_breadth_family_count = sum(1 for row in emitted_rows if bool(row.get("palette_breadth_ready", False)))
    active_multi_family_count = sum(
        1 for row in emitted_rows if bool(row.get("active_multi_family_ready", False))
    )
    family_count = len(emitted_rows)
    contract_pass = bool(
        family_count > 0 and broad_ready_family_count >= family_count and queued_submission_count == 0
    )
    reason_code = "PASS" if contract_pass else "CHECK" if emitted_rows else "ERR_INPUT"
    summary = {
        "family_count": int(family_count),
        "solver_ready_family_count": int(solver_ready_family_count),
        "runtime_ready_family_count": int(runtime_ready_family_count),
        "release_ready_family_count": int(release_ready_family_count),
        "broad_ready_family_count": int(broad_ready_family_count),
        "full_breadth_family_count": int(full_breadth_family_count),
        "combo_broad_family_count": int(combo_broad_family_count),
        "mesh_coverage_family_count": int(mesh_coverage_family_count),
        "mesh_broad_family_count": int(mesh_broad_family_count),
        "member_multi_family_count": int(member_multi_family_count),
        "palette_breadth_family_count": int(palette_breadth_family_count),
        "active_multi_family_count": int(active_multi_family_count),
        "queued_submission_count": int(queued_submission_count),
        "family_status_label": ", ".join(
            f"{row['family_id']}:{row['solver_family_breadth_status']}" for row in emitted_rows
        ),
        "solver_family_breadth_ready": bool(contract_pass),
    }
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-solver-family-breadth-report",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "family_tracks_json": str(family_tracks_path or DEFAULT_FAMILY_TRACKS_JSON),
            "runtime_submission_json": str(runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON),
        },
        "summary": summary,
        "family_rows": emitted_rows,
        "artifacts": {
            "native_authoring_ops_portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "native_authoring_family_tracks_json": str(family_tracks_path or DEFAULT_FAMILY_TRACKS_JSON),
            "native_authoring_runtime_submission_lane_json": str(
                runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON
            ),
            "native_authoring_solver_family_breadth_report_json": str(out),
        },
        "summary_line": (
            f"Native authoring solver family breadth: {'PASS' if contract_pass else 'CHECK'} | "
            f"families={family_count} | broad_ready={broad_ready_family_count} | "
            f"full_breadth={full_breadth_family_count} | solver_ready={solver_ready_family_count} | "
            f"combo_broad={combo_broad_family_count} | mesh_coverage={mesh_coverage_family_count} | "
            f"mesh_broad={mesh_broad_family_count} | member_multi={member_multi_family_count} | "
            f"queue={queued_submission_count}"
        ),
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    _write_json(out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-json", type=Path, default=DEFAULT_PORTFOLIO_JSON)
    parser.add_argument("--family-tracks-json", type=Path, default=DEFAULT_FAMILY_TRACKS_JSON)
    parser.add_argument("--runtime-submission-json", type=Path, default=DEFAULT_RUNTIME_SUBMISSION_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    portfolio_report = _load_json(args.portfolio_json) if args.portfolio_json.exists() else {}
    family_tracks_report = _load_json(args.family_tracks_json) if args.family_tracks_json.exists() else {}
    runtime_submission_report = (
        _load_json(args.runtime_submission_json) if args.runtime_submission_json.exists() else {}
    )
    payload = build_native_authoring_solver_family_breadth_report(
        portfolio_report=portfolio_report,
        family_tracks_report=family_tracks_report,
        runtime_submission_report=runtime_submission_report,
        portfolio_path=args.portfolio_json,
        family_tracks_path=args.family_tracks_json,
        runtime_submission_path=args.runtime_submission_json,
        out=args.out,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
