#!/usr/bin/env python3
"""Generate native authoring local runtime scenario-depth coverage report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_RUNTIME_SUBMISSION_JSON = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_local_runtime_scenario_depth_report.json"

REASONS = {
    "PASS": "native authoring local runtime scenario depth report generated",
    "CHECK": "native authoring local runtime scenario depth report generated with partial depth",
    "ERR_INPUT": "no native authoring family/runtime rows supplied",
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


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


def _status_token(*, depth_ready: bool, partial_ready: bool) -> str:
    if depth_ready:
        return "deep"
    if partial_ready:
        return "targeted"
    return "check"


def _load_solver_payload_from_row(*rows: dict[str, Any]) -> dict[str, Any]:
    for row in rows:
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, dict):
            continue
        path_text = _first_text(
            artifacts.get("solver_session_json"),
            artifacts.get("native_authoring_solver_session_json"),
        )
        if not path_text:
            continue
        payload = _load_json_object(Path(path_text))
        if payload:
            return payload
    return {}


def build_native_authoring_local_runtime_scenario_depth_report(
    *,
    portfolio_report: dict[str, Any] | list[Any] | None = None,
    runtime_submission_report: dict[str, Any] | list[Any] | None = None,
    portfolio_path: Path | None = None,
    runtime_submission_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()

    portfolio_rows = _extract_rows(portfolio_report, keys=("family_rows", "families"))
    runtime_rows = _extract_rows(runtime_submission_report, keys=("family_rows", "submission_rows", "rows"))

    portfolio_by_family = {
        _family_id(row, index): row
        for index, row in enumerate(portfolio_rows, start=1)
        if _family_id(row, index)
    }
    runtime_by_family = {
        _family_id(row, index): row
        for index, row in enumerate(runtime_rows, start=1)
        if _family_id(row, index)
    }
    family_ids = sorted(set(portfolio_by_family) | set(runtime_by_family))

    family_rows: list[dict[str, Any]] = []
    for index, family_id in enumerate(family_ids, start=1):
        portfolio_row = portfolio_by_family.get(family_id, {})
        runtime_row = runtime_by_family.get(family_id, {})
        solver_payload = _load_solver_payload_from_row(runtime_row, portfolio_row)
        solver_summary = solver_payload.get("summary") if isinstance(solver_payload.get("summary"), dict) else {}
        mesh_session = solver_payload.get("mesh_session") if isinstance(solver_payload.get("mesh_session"), dict) else {}
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
        editor_seed = (
            load_combination_session.get("editor_seed")
            if isinstance(load_combination_session.get("editor_seed"), dict)
            else {}
        )
        editor_summary = editor_seed.get("summary") if isinstance(editor_seed.get("summary"), dict) else {}

        case_count = _first_int(
            editor_summary.get("case_count"),
            len(editor_seed.get("case_nodes") or []) if isinstance(editor_seed.get("case_nodes"), list) else 0,
        )
        combo_count = _first_int(
            runtime_summary.get("combo_count"),
            editor_summary.get("combination_count"),
            solver_summary.get("combo_count"),
        )
        stage_count = _first_int(editor_summary.get("stage_count"))
        graph_edge_count = _first_int(editor_summary.get("graph_edge_count"))
        limit_state_count = len(editor_summary.get("limit_state_counts", {})) if isinstance(
            editor_summary.get("limit_state_counts"), dict
        ) else 0
        runtime_case_breadth_count = _first_int(runtime_summary.get("runtime_case_breadth_count"))
        combo_family_count = len(runtime_summary.get("combo_family_counts", {})) if isinstance(
            runtime_summary.get("combo_family_counts"), dict
        ) else 0
        mesh_request_count = _first_int(
            mesh_session.get("request_count"),
            solver_summary.get("mesh_request_count"),
        )
        mesh_cell_count = _first_int(mesh_session.get("total_estimated_cells"))
        selected_combination_count = len(load_combination_session.get("selected_combination_names") or []) if isinstance(
            load_combination_session.get("selected_combination_names"), list
        ) else 0
        loadcomb_preview_line_count = _first_int(load_combination_session.get("loadcomb_preview_line_count"))
        omitted_library_count = len(load_combination_session.get("omitted_library_combinations") or []) if isinstance(
            load_combination_session.get("omitted_library_combinations"), list
        ) else 0

        runtime_ready = bool(
            _first_bool(
                runtime_row.get("runtime_ready"),
                runtime_row.get("ready"),
                runtime_summary.get("authoring_ready"),
                portfolio_row.get("runtime_ready"),
            )
        )
        scenario_ready = bool(
            case_count >= 4
            and combo_count >= 12
            and runtime_case_breadth_count >= 3
            and combo_family_count >= 3
        )
        trace_ready = bool(
            stage_count >= 2
            and graph_edge_count >= max(combo_count, 1)
            and limit_state_count >= 2
            and selected_combination_count > 0
            and loadcomb_preview_line_count > 0
        )
        mesh_trace_ready = bool(mesh_request_count >= 2 and mesh_cell_count > 0)
        partial_ready = any((runtime_ready, scenario_ready, trace_ready, mesh_trace_ready))
        depth_ready = bool(
            runtime_ready
            and scenario_ready
            and trace_ready
            and mesh_trace_ready
        )
        depth_status = _status_token(depth_ready=depth_ready, partial_ready=partial_ready)

        family_rows.append(
            {
                "family_id": family_id,
                "family_label": _first_text(
                    runtime_row.get("family_label"),
                    portfolio_row.get("family_label"),
                    family_id.replace("_", " "),
                ),
                "project_id": _first_text(runtime_row.get("project_id"), portfolio_row.get("project_id")),
                "project_name": _first_text(runtime_row.get("project_name"), portfolio_row.get("project_name")),
                "local_runtime_scenario_depth_status": depth_status,
                "runtime_ready": runtime_ready,
                "scenario_ready": scenario_ready,
                "trace_ready": trace_ready,
                "mesh_trace_ready": mesh_trace_ready,
                "case_count": case_count,
                "combo_count": combo_count,
                "stage_count": stage_count,
                "graph_edge_count": graph_edge_count,
                "limit_state_count": limit_state_count,
                "runtime_case_breadth_count": runtime_case_breadth_count,
                "combo_family_count": combo_family_count,
                "mesh_request_count": mesh_request_count,
                "mesh_cell_count": mesh_cell_count,
                "selected_combination_count": selected_combination_count,
                "loadcomb_preview_line_count": loadcomb_preview_line_count,
                "omitted_library_combination_count": omitted_library_count,
                "summary_line": (
                    f"{family_id}: {depth_status.upper()} | runtime={'yes' if runtime_ready else 'no'} | "
                    f"cases={case_count} | combos={combo_count} | breadth={runtime_case_breadth_count} | "
                    f"combo_families={combo_family_count} | trace={stage_count}/{limit_state_count}/{graph_edge_count} | "
                    f"mesh={mesh_request_count}/{mesh_cell_count} | loadcomb={loadcomb_preview_line_count} | "
                    f"omitted={omitted_library_count}"
                ),
                "artifacts": {
                    "solver_session_json": _first_text(
                        (runtime_row.get("artifacts") or {}).get("solver_session_json")
                        if isinstance(runtime_row.get("artifacts"), dict)
                        else "",
                        (portfolio_row.get("artifacts") or {}).get("solver_session_json")
                        if isinstance(portfolio_row.get("artifacts"), dict)
                        else "",
                    ),
                },
            }
        )

    family_count = len(family_rows)
    depth_ready_family_count = sum(
        1 for row in family_rows if _first_text(row.get("local_runtime_scenario_depth_status")) == "deep"
    )
    targeted_family_count = sum(
        1 for row in family_rows if _first_text(row.get("local_runtime_scenario_depth_status")) == "targeted"
    )
    runtime_ready_family_count = sum(1 for row in family_rows if bool(row.get("runtime_ready")))
    scenario_ready_family_count = sum(1 for row in family_rows if bool(row.get("scenario_ready")))
    trace_ready_family_count = sum(1 for row in family_rows if bool(row.get("trace_ready")))
    mesh_trace_ready_family_count = sum(1 for row in family_rows if bool(row.get("mesh_trace_ready")))
    omitted_library_family_count = sum(
        1 for row in family_rows if _first_int(row.get("omitted_library_combination_count")) > 0
    )
    family_status_label = ", ".join(
        f"{_first_text(row.get('family_id'))}:{_first_text(row.get('local_runtime_scenario_depth_status'), 'check')}"
        for row in family_rows
        if _first_text(row.get("family_id"))
    )

    contract_pass = bool(family_rows and depth_ready_family_count >= family_count)
    reason_code = "PASS" if contract_pass else ("CHECK" if family_rows else "ERR_INPUT")
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-local-runtime-scenario-depth",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json_path": str(portfolio_path) if portfolio_path is not None else "",
            "runtime_submission_json_path": str(runtime_submission_path) if runtime_submission_path is not None else "",
        },
        "summary": {
            "family_count": family_count,
            "depth_ready_family_count": depth_ready_family_count,
            "targeted_family_count": targeted_family_count,
            "runtime_ready_family_count": runtime_ready_family_count,
            "scenario_ready_family_count": scenario_ready_family_count,
            "trace_ready_family_count": trace_ready_family_count,
            "mesh_trace_ready_family_count": mesh_trace_ready_family_count,
            "omitted_library_family_count": omitted_library_family_count,
            "family_status_label": family_status_label,
            "local_runtime_scenario_depth_ready": contract_pass,
        },
        "family_rows": family_rows,
        "artifacts": {
            "native_authoring_local_runtime_scenario_depth_report_json": str(out),
            "native_authoring_ops_portfolio_json": str(portfolio_path) if portfolio_path is not None else "",
            "native_authoring_runtime_submission_lane_json": (
                str(runtime_submission_path) if runtime_submission_path is not None else ""
            ),
        },
        "summary_line": (
            "Native authoring local runtime scenario depth: "
            f"{reason_code} | families={family_count} | deep={depth_ready_family_count} | "
            f"scenario_ready={scenario_ready_family_count} | trace_ready={trace_ready_family_count} | "
            f"mesh_ready={mesh_trace_ready_family_count} | runtime_ready={runtime_ready_family_count} | "
            f"omitted={omitted_library_family_count}"
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
    parser.add_argument("--runtime-submission-json", default=str(DEFAULT_RUNTIME_SUBMISSION_JSON))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    portfolio_path = Path(args.portfolio_json)
    runtime_submission_path = Path(args.runtime_submission_json)
    payload = build_native_authoring_local_runtime_scenario_depth_report(
        portfolio_report=_load_json_object(portfolio_path) if portfolio_path.exists() else {},
        runtime_submission_report=_load_json_object(runtime_submission_path) if runtime_submission_path.exists() else {},
        portfolio_path=portfolio_path,
        runtime_submission_path=runtime_submission_path,
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
