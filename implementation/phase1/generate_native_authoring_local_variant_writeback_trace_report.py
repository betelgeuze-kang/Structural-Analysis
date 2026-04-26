#!/usr/bin/env python3
"""Generate native authoring local variant/writeback trace coverage report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_local_variant_writeback_trace_report.json"

REASONS = {
    "PASS": "native authoring local variant/writeback trace report generated",
    "CHECK": "native authoring local variant/writeback trace report generated with partial local depth",
    "ERR_INPUT": "no native authoring family rows supplied",
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


def _unique_sorted_tokens(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


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


def _row_artifacts(row: dict[str, Any]) -> dict[str, Any]:
    artifacts = row.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def _artifact_text(row: dict[str, Any], *keys: str) -> str:
    artifacts = _row_artifacts(row)
    values: list[Any] = []
    for key in keys:
        values.append(row.get(key))
        values.append(artifacts.get(key))
    return _first_text(*values)


def _artifact_present(path_text: str) -> bool:
    return bool(path_text and Path(path_text).exists())


def _family_palette_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        if isinstance(value, dict):
            normalized.append(_first_text(value.get("family_id"), value.get("id"), value.get("label")))
        else:
            normalized.append(_first_text(value))
    return _unique_sorted_tokens(normalized)


def build_native_authoring_local_variant_writeback_trace_report(
    *,
    family_rows: list[Any] | None = None,
    portfolio_report: dict[str, Any] | list[Any] | None = None,
    portfolio_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()

    if family_rows is None:
        family_rows = _extract_rows(
            portfolio_report,
            keys=("family_rows", "families", "track_rows", "tracks", "rows"),
        )
    else:
        family_rows = [row for row in family_rows if isinstance(row, dict)]

    family_rows_by_id = {
        _family_id(row, index): row
        for index, row in enumerate(family_rows, start=1)
        if _family_id(row, index)
    }
    ordered_family_ids = sorted(family_rows_by_id)

    emitted_rows: list[dict[str, Any]] = []
    for family_id in ordered_family_ids:
        row = family_rows_by_id.get(family_id, {})
        workspace_summary_path_text = _artifact_text(
            row,
            "workspace_summary_json",
            "native_authoring_workspace_summary_json",
        )
        solver_session_path_text = _artifact_text(
            row,
            "solver_session_json",
            "native_authoring_solver_session_json",
            "solver_session_artifact_json",
        )
        project_package_path_text = _artifact_text(row, "project_package_zip")
        project_signature_path_text = _artifact_text(
            row,
            "project_registry_signature",
            "project_signature_b64",
        )
        project_registry_path_text = _artifact_text(
            row,
            "project_registry_json",
            "native_authoring_project_registry_json",
        )

        workspace_payload = _load_json_object(Path(workspace_summary_path_text)) if workspace_summary_path_text else {}
        solver_payload = _load_json_object(Path(solver_session_path_text)) if solver_session_path_text else {}

        workspace_summary = (
            workspace_payload.get("summary") if isinstance(workspace_payload.get("summary"), dict) else {}
        )
        selected_family = (
            workspace_payload.get("selected_family")
            if isinstance(workspace_payload.get("selected_family"), dict)
            else {}
        )
        authoring_controls = (
            workspace_payload.get("authoring_controls")
            if isinstance(workspace_payload.get("authoring_controls"), dict)
            else {}
        )
        editor_controls = (
            workspace_payload.get("editor_controls")
            if isinstance(workspace_payload.get("editor_controls"), dict)
            else {}
        )
        section_usage_counts = (
            workspace_summary.get("section_usage_counts")
            if isinstance(workspace_summary.get("section_usage_counts"), dict)
            else {}
        )
        member_type_counts = (
            workspace_summary.get("member_type_counts")
            if isinstance(workspace_summary.get("member_type_counts"), dict)
            else {}
        )

        workspace_family_palette_ids = _family_palette_ids(editor_controls.get("family_palette"))
        workspace_family_palette_count = max(
            len(workspace_family_palette_ids),
            _first_int(row.get("palette_family_count")),
        )
        section_palette_values = editor_controls.get("section_palette")
        if not isinstance(section_palette_values, list):
            section_palette_values = authoring_controls.get("section_palette")
        workspace_section_palette_count = len(
            _unique_sorted_tokens(
                [
                    _first_text(
                        value.get("section_id"),
                        value.get("id"),
                        value.get("label"),
                    )
                    if isinstance(value, dict)
                    else _first_text(value)
                    for value in (section_palette_values or [])
                ]
            )
        )
        active_section_count = len(section_usage_counts)
        active_family_count = max(
            len(
                _unique_sorted_tokens(
                    [_authoring_section_family(section_id) for section_id in section_usage_counts.keys()]
                )
            ),
            _first_int(row.get("active_family_count")),
        )
        member_type_count = max(len(member_type_counts), _first_int(row.get("member_type_count")))
        load_pattern_count = _first_int(
            workspace_summary.get("load_pattern_count"),
            row.get("load_pattern_count"),
        )
        workspace_contract = bool(workspace_payload.get("contract_pass", False))
        workspace_native_ready = bool(workspace_summary.get("native_authoring_ready", False))
        workspace_ready = bool(
            _first_bool(
                row.get("workspace_ready"),
                workspace_contract and workspace_native_ready,
                workspace_contract,
                workspace_native_ready,
            )
        )
        workspace_variant_ready = bool(
            workspace_ready
            and workspace_family_palette_count >= 4
            and workspace_section_palette_count >= 4
            and active_family_count >= 2
            and member_type_count >= 2
            and load_pattern_count >= 4
        )

        solver_summary = solver_payload.get("summary") if isinstance(solver_payload.get("summary"), dict) else {}
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
        editor_seed = (
            load_combination_session.get("editor_seed")
            if isinstance(load_combination_session.get("editor_seed"), dict)
            else {}
        )
        editor_seed_summary = (
            editor_seed.get("summary") if isinstance(editor_seed.get("summary"), dict) else {}
        )
        combo_count = _first_int(
            runtime_summary.get("combo_count"),
            solver_summary.get("combo_count"),
            row.get("solver_combo_count"),
        )
        runtime_case_count = _first_int(
            runtime_summary.get("runtime_case_count"),
            solver_summary.get("load_case_count"),
            row.get("solver_load_case_count"),
        )
        combo_family_count = max(
            len(runtime_summary.get("combo_family_counts", {}))
            if isinstance(runtime_summary.get("combo_family_counts"), dict)
            else 0,
            _first_int(row.get("solver_combo_family_count")),
        )
        mesh_request_count = _first_int(
            mesh_session.get("request_count"),
            solver_summary.get("mesh_request_count"),
            row.get("solver_mesh_request_count"),
        )
        mesh_cell_count = _first_int(
            mesh_session.get("total_estimated_cells"),
            row.get("solver_mesh_cell_count"),
        )
        selected_combination_count = len(load_combination_session.get("selected_combination_names", [])) if isinstance(
            load_combination_session.get("selected_combination_names"), list
        ) else 0
        limit_state_count = len(editor_seed_summary.get("limit_state_counts", {})) if isinstance(
            editor_seed_summary.get("limit_state_counts"), dict
        ) else 0
        omitted_library_combination_count = len(
            load_combination_session.get("omitted_library_combinations", [])
        ) if isinstance(load_combination_session.get("omitted_library_combinations"), list) else 0
        solver_contract = bool(solver_payload.get("contract_pass", False))
        solver_session_ready = bool(solver_summary.get("session_ready", False))
        solver_runtime_ready = bool(runtime_summary.get("authoring_ready", False))
        solver_ready = bool(
            _first_bool(
                row.get("solver_ready"),
                solver_contract and (solver_session_ready or solver_runtime_ready),
                solver_contract,
                solver_session_ready,
                solver_runtime_ready,
            )
        )
        solver_variant_ready = bool(
            solver_ready
            and combo_count >= 12
            and runtime_case_count >= 3
            and combo_family_count >= 3
            and mesh_request_count >= 2
            and limit_state_count >= 2
            and selected_combination_count > 0
        )

        snapshot_count = _first_int(row.get("snapshot_count"))
        approval_count = _first_int(row.get("approval_count"))
        package_bytes = _first_int(row.get("package_bytes"))
        registry_ready = bool(_first_bool(row.get("registry_ready"), row.get("writeback_ready")))
        signature_verified = bool(_first_bool(row.get("signature_verified")))
        package_ready = bool(package_bytes > 0 or _artifact_present(project_package_path_text))
        signature_artifact_present = _artifact_present(project_signature_path_text)
        registry_artifact_present = _artifact_present(project_registry_path_text)
        writeback_trace_ready = bool(
            registry_ready
            and signature_verified
            and approval_count > 0
            and snapshot_count > 0
            and package_ready
            and (signature_artifact_present or signature_verified)
            and (registry_artifact_present or registry_ready)
        )

        partial_ready = any(
            (
                workspace_ready,
                workspace_variant_ready,
                solver_ready,
                solver_variant_ready,
                registry_ready,
                signature_verified,
                writeback_trace_ready,
                approval_count > 0,
                snapshot_count > 0,
            )
        )
        depth_ready = bool(workspace_variant_ready and solver_variant_ready and writeback_trace_ready)
        depth_status = _status_token(depth_ready=depth_ready, partial_ready=partial_ready)

        family_label = _first_text(
            row.get("family_label"),
            selected_family.get("label"),
            selected_family.get("family_id"),
            family_id.replace("_", " "),
        )
        project_id = _first_text(row.get("project_id"))
        project_name = _first_text(row.get("project_name"))
        selected_family_id = _first_text(
            selected_family.get("family_id"),
            authoring_controls.get("family_id"),
            row.get("authoring_family_id"),
            family_id,
        )
        emitted_rows.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "project_id": project_id,
                "project_name": project_name,
                "selected_family_id": selected_family_id,
                "local_variant_writeback_trace_status": depth_status,
                "workspace_ready": workspace_ready,
                "workspace_variant_ready": workspace_variant_ready,
                "workspace_family_palette_count": workspace_family_palette_count,
                "workspace_section_palette_count": workspace_section_palette_count,
                "workspace_active_section_count": active_section_count,
                "workspace_active_family_count": active_family_count,
                "member_type_count": member_type_count,
                "load_pattern_count": load_pattern_count,
                "solver_ready": solver_ready,
                "solver_variant_ready": solver_variant_ready,
                "solver_combo_count": combo_count,
                "runtime_case_count": runtime_case_count,
                "solver_combo_family_count": combo_family_count,
                "mesh_request_count": mesh_request_count,
                "mesh_cell_count": mesh_cell_count,
                "selected_combination_count": selected_combination_count,
                "limit_state_count": limit_state_count,
                "omitted_library_combination_count": omitted_library_combination_count,
                "registry_ready": registry_ready,
                "signature_verified": signature_verified,
                "package_ready": package_ready,
                "writeback_trace_ready": writeback_trace_ready,
                "snapshot_count": snapshot_count,
                "approval_count": approval_count,
                "package_bytes": package_bytes,
                "variant_axis_count": sum(
                    (
                        workspace_variant_ready,
                        solver_variant_ready,
                        writeback_trace_ready,
                    )
                ),
                "summary_line": (
                    f"{family_id}: {depth_status.upper()} | "
                    f"workspace={workspace_family_palette_count}/{workspace_section_palette_count}/"
                    f"{active_family_count}/{member_type_count} | "
                    f"solver={combo_count}/{runtime_case_count}/{combo_family_count}/"
                    f"{mesh_request_count}/{limit_state_count} | "
                    f"writeback=snapshots:{snapshot_count},approvals:{approval_count},"
                    f"signature:{'yes' if signature_verified else 'no'},package:{'yes' if package_ready else 'no'}"
                ),
                "artifacts": {
                    "workspace_summary_json": workspace_summary_path_text,
                    "solver_session_json": solver_session_path_text,
                    "project_registry_json": project_registry_path_text,
                    "project_package_zip": project_package_path_text,
                    "project_registry_signature": project_signature_path_text,
                },
            }
        )

    family_count = len(emitted_rows)
    deep_ready_family_count = sum(
        1 for row in emitted_rows if _first_text(row.get("local_variant_writeback_trace_status")) == "deep"
    )
    targeted_family_count = sum(
        1 for row in emitted_rows if _first_text(row.get("local_variant_writeback_trace_status")) == "targeted"
    )
    workspace_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("workspace_ready")))
    workspace_variant_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("workspace_variant_ready")))
    solver_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("solver_ready")))
    solver_variant_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("solver_variant_ready")))
    writeback_trace_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("writeback_trace_ready")))
    active_multi_family_count = sum(
        1 for row in emitted_rows if _first_int(row.get("workspace_active_family_count")) >= 2
    )
    combo_multi_family_count = sum(
        1 for row in emitted_rows if _first_int(row.get("solver_combo_family_count")) >= 3
    )
    signed_writeback_family_count = sum(1 for row in emitted_rows if bool(row.get("signature_verified")))
    package_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("package_ready")))
    omitted_library_family_count = sum(
        1 for row in emitted_rows if _first_int(row.get("omitted_library_combination_count")) > 0
    )
    contract_pass = bool(family_count > 0 and deep_ready_family_count >= family_count)
    reason_code = "PASS" if contract_pass else ("CHECK" if emitted_rows else "ERR_INPUT")

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-local-variant-writeback-trace-report",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
        },
        "summary": {
            "family_count": int(family_count),
            "deep_ready_family_count": int(deep_ready_family_count),
            "targeted_family_count": int(targeted_family_count),
            "workspace_ready_family_count": int(workspace_ready_family_count),
            "workspace_variant_ready_family_count": int(workspace_variant_ready_family_count),
            "solver_ready_family_count": int(solver_ready_family_count),
            "solver_variant_ready_family_count": int(solver_variant_ready_family_count),
            "writeback_trace_ready_family_count": int(writeback_trace_ready_family_count),
            "active_multi_family_count": int(active_multi_family_count),
            "combo_multi_family_count": int(combo_multi_family_count),
            "signed_writeback_family_count": int(signed_writeback_family_count),
            "package_ready_family_count": int(package_ready_family_count),
            "omitted_library_family_count": int(omitted_library_family_count),
            "family_status_label": ", ".join(
                f"{row['family_id']}:{row['local_variant_writeback_trace_status']}" for row in emitted_rows
            ),
            "local_variant_writeback_trace_ready": bool(contract_pass),
        },
        "family_rows": emitted_rows,
        "artifacts": {
            "native_authoring_ops_portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "native_authoring_local_variant_writeback_trace_report_json": str(out),
        },
        "summary_line": (
            f"Native authoring local variant/writeback trace: {'PASS' if contract_pass else 'CHECK'} | "
            f"families={family_count} | deep={deep_ready_family_count} | targeted={targeted_family_count} | "
            f"workspace_variant={workspace_variant_ready_family_count} | "
            f"solver_variant={solver_variant_ready_family_count} | "
            f"writeback_trace={writeback_trace_ready_family_count} | "
            f"active_multi={active_multi_family_count} | combo_multi={combo_multi_family_count} | "
            f"signed={signed_writeback_family_count} | omitted={omitted_library_family_count}"
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
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    portfolio_report = _load_json(args.portfolio_json) if args.portfolio_json.exists() else {}
    payload = build_native_authoring_local_variant_writeback_trace_report(
        portfolio_report=portfolio_report,
        portfolio_path=args.portfolio_json,
        out=args.out,
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
