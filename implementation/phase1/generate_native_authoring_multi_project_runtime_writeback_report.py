#!/usr/bin/env python3
"""Generate multi-project native authoring runtime/writeback depth report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_RUNTIME_SUBMISSION_JSON = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON = DEFAULT_OUT_DIR / "native_authoring_runtime_writeback_depth_report.json"
DEFAULT_REGISTRY_WORKSPACE_JSON = DEFAULT_OUT_DIR / "native_authoring_project_registry_workspace.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_multi_project_runtime_writeback_report.json"

REASONS = {
    "PASS": "native authoring multi-project runtime writeback report generated",
    "CHECK": "native authoring multi-project runtime writeback report generated with partial depth",
    "ERR_INPUT": "no native authoring project/family rows supplied",
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
        row.get("project_family_id"),
        f"family-{index}",
    )


def _project_id(row: dict[str, Any], index: int) -> str:
    return _first_text(row.get("project_id"), f"project-{index}")


def _pair_key(project_id: str, family_id: str) -> str:
    return f"{project_id}::{family_id}"


def _status_label(*, full_ready: bool, partial_ready: bool) -> str:
    if full_ready:
        return "full"
    if partial_ready:
        return "targeted"
    return "check"


def build_native_authoring_multi_project_runtime_writeback_report(
    *,
    portfolio_report: dict[str, Any] | list[Any] | None = None,
    runtime_submission_report: dict[str, Any] | list[Any] | None = None,
    runtime_writeback_depth_report: dict[str, Any] | list[Any] | None = None,
    registry_workspace_report: dict[str, Any] | list[Any] | None = None,
    portfolio_path: Path | None = None,
    runtime_submission_path: Path | None = None,
    runtime_writeback_depth_path: Path | None = None,
    registry_workspace_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()

    portfolio_rows = _extract_rows(portfolio_report, keys=("family_rows", "families"))
    runtime_rows = _extract_rows(runtime_submission_report, keys=("family_rows", "submission_rows", "rows"))
    depth_rows = _extract_rows(runtime_writeback_depth_report, keys=("family_rows", "rows"))
    registry_project_rows = _extract_rows(registry_workspace_report, keys=("project_rows", "projects"))

    portfolio_by_pair: dict[str, dict[str, Any]] = {}
    runtime_by_pair: dict[str, dict[str, Any]] = {}
    depth_by_pair: dict[str, dict[str, Any]] = {}
    registry_by_project: dict[str, dict[str, Any]] = {}

    for index, row in enumerate(portfolio_rows, start=1):
        project_id = _project_id(row, index)
        family_id = _family_id(row, index)
        if project_id and family_id:
            portfolio_by_pair[_pair_key(project_id, family_id)] = row

    for index, row in enumerate(runtime_rows, start=1):
        project_id = _project_id(row, index)
        family_id = _family_id(row, index)
        if project_id and family_id:
            runtime_by_pair[_pair_key(project_id, family_id)] = row

    for index, row in enumerate(depth_rows, start=1):
        project_id = _project_id(row, index)
        family_id = _family_id(row, index)
        if project_id and family_id:
            depth_by_pair[_pair_key(project_id, family_id)] = row

    for index, row in enumerate(registry_project_rows, start=1):
        project_id = _project_id(row, index)
        if project_id:
            registry_by_project[project_id] = row

    pair_keys = sorted(set(portfolio_by_pair) | set(runtime_by_pair) | set(depth_by_pair))
    project_family_rows: list[dict[str, Any]] = []

    for pair_key in pair_keys:
        project_id, family_id = pair_key.split("::", 1)
        portfolio_row = portfolio_by_pair.get(pair_key, {})
        runtime_row = runtime_by_pair.get(pair_key, {})
        depth_row = depth_by_pair.get(pair_key, {})
        registry_row = registry_by_project.get(project_id, {})

        project_name = _first_text(
            runtime_row.get("project_name"),
            portfolio_row.get("project_name"),
            registry_row.get("project_name"),
        )
        family_label = _first_text(
            runtime_row.get("family_label"),
            portfolio_row.get("family_label"),
            family_id.replace("_", " "),
        )
        submission_status = _first_text(runtime_row.get("submission_status"), runtime_row.get("lane_status"))
        runtime_ready = bool(_first_bool(runtime_row.get("runtime_ready"), portfolio_row.get("runtime_ready")))
        submission_ready = bool(
            _first_bool(
                runtime_row.get("submission_ready"),
                runtime_row.get("release_ready"),
                portfolio_row.get("release_ready"),
            )
        )
        writeback_ready = bool(
            _first_bool(
                depth_row.get("writeback_ready"),
                runtime_row.get("writeback_ready"),
                runtime_row.get("registry_ready"),
                portfolio_row.get("registry_ready"),
            )
        )
        registry_ready = bool(
            _first_bool(
                depth_row.get("registry_ready"),
                runtime_row.get("registry_ready"),
                portfolio_row.get("registry_ready"),
                _first_int(registry_row.get("registry_count")) > 0,
            )
        )
        signature_verified = bool(
            _first_bool(
                depth_row.get("signature_verified"),
                runtime_row.get("signature_verified"),
                portfolio_row.get("signature_verified"),
                registry_row.get("latest_signature_verified"),
            )
        )
        package_reproducible = bool(
            _first_bool(
                depth_row.get("package_reproducible"),
                registry_row.get("latest_package_reproducible"),
                registry_row.get("package_reproducible"),
            )
        )
        approval_count = _first_int(
            depth_row.get("approval_count"),
            runtime_row.get("approval_count"),
            registry_row.get("latest_approval_count"),
        )
        approved_count = _first_int(
            depth_row.get("approved_count"),
            registry_row.get("latest_approved_count"),
            approval_count,
        )
        approvals_ready = bool(approval_count > 0 and approved_count >= approval_count)
        snapshot_count = _first_int(
            depth_row.get("snapshot_count"),
            runtime_row.get("snapshot_count"),
            portfolio_row.get("snapshot_count"),
        )
        snapshot_ready = bool(
            _first_bool(depth_row.get("snapshot_ready"))
            or snapshot_count > 0
        )
        queue_clear = bool(
            _first_bool(depth_row.get("queue_clear"))
            if _first_bool(depth_row.get("queue_clear")) is not None
            else submission_status.lower() not in {"queued", "planned", "blocked", "rerun_requested"}
        )
        solver_combo_count = _first_int(runtime_row.get("solver_combo_count"), portfolio_row.get("solver_combo_count"))
        solver_mesh_request_count = _first_int(
            runtime_row.get("solver_mesh_request_count"),
            portfolio_row.get("solver_mesh_request_count"),
        )
        partial_ready = any(
            (
                runtime_ready,
                submission_ready,
                writeback_ready,
                registry_ready,
                signature_verified,
                package_reproducible,
                approvals_ready,
                snapshot_ready,
            )
        )
        full_ready = all(
            (
                runtime_ready,
                submission_ready,
                writeback_ready,
                registry_ready,
                signature_verified,
                package_reproducible,
                approvals_ready,
                snapshot_ready,
                queue_clear,
            )
        )
        status = _status_label(full_ready=full_ready, partial_ready=partial_ready)

        project_family_rows.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "family_id": family_id,
                "family_label": family_label,
                "project_family_status": status,
                "runtime_ready": runtime_ready,
                "submission_ready": submission_ready,
                "writeback_ready": writeback_ready,
                "registry_ready": registry_ready,
                "signature_verified": signature_verified,
                "package_reproducible": package_reproducible,
                "approval_count": approval_count,
                "approved_count": approved_count,
                "approvals_ready": approvals_ready,
                "snapshot_count": snapshot_count,
                "snapshot_ready": snapshot_ready,
                "queue_clear": queue_clear,
                "submission_status": submission_status,
                "solver_combo_count": solver_combo_count,
                "solver_mesh_request_count": solver_mesh_request_count,
                "summary_line": (
                    f"{project_id}/{family_id}: {status.upper()} | runtime={'yes' if runtime_ready else 'no'} | "
                    f"writeback={'yes' if writeback_ready else 'no'} | registry={'yes' if registry_ready else 'no'} | "
                    f"signature={'yes' if signature_verified else 'no'} | repro={'yes' if package_reproducible else 'no'} | "
                    f"approvals={approved_count}/{approval_count} | snapshots={snapshot_count} | "
                    f"queue={'clear' if queue_clear else submission_status or 'queued'}"
                ),
            }
        )

    project_map: dict[str, dict[str, Any]] = {}
    for row in project_family_rows:
        project_id = str(row.get("project_id", "") or "")
        if not project_id:
            continue
        record = project_map.setdefault(
            project_id,
            {
                "project_id": project_id,
                "project_name": str(row.get("project_name", "") or ""),
                "family_count": 0,
                "full_depth_count": 0,
                "targeted_count": 0,
                "signature_verified_count": 0,
                "package_reproducible_count": 0,
                "snapshot_ready_count": 0,
                "queue_clear_count": 0,
                "family_ids": [],
            },
        )
        record["project_name"] = record["project_name"] or str(row.get("project_name", "") or "")
        record["family_count"] += 1
        if str(row.get("family_id", "") or "").strip():
            record["family_ids"].append(str(row.get("family_id")))
        if str(row.get("project_family_status", "")) == "full":
            record["full_depth_count"] += 1
        elif str(row.get("project_family_status", "")) == "targeted":
            record["targeted_count"] += 1
        if bool(row.get("signature_verified")):
            record["signature_verified_count"] += 1
        if bool(row.get("package_reproducible")):
            record["package_reproducible_count"] += 1
        if bool(row.get("snapshot_ready")):
            record["snapshot_ready_count"] += 1
        if bool(row.get("queue_clear")):
            record["queue_clear_count"] += 1

    project_rows: list[dict[str, Any]] = []
    for project_id, record in sorted(project_map.items()):
        family_count = int(record["family_count"])
        full_depth_count = int(record["full_depth_count"])
        signature_count = int(record["signature_verified_count"])
        repro_count = int(record["package_reproducible_count"])
        snapshot_count = int(record["snapshot_ready_count"])
        queue_clear_count = int(record["queue_clear_count"])
        ready = bool(
            family_count > 0
            and full_depth_count >= family_count
            and signature_count >= family_count
            and repro_count >= family_count
            and snapshot_count >= family_count
            and queue_clear_count >= family_count
        )
        project_rows.append(
            {
                "project_id": project_id,
                "project_name": str(record["project_name"] or ""),
                "project_status": "full" if ready else "targeted" if full_depth_count > 0 else "check",
                "ready": ready,
                "family_count": family_count,
                "full_depth_count": full_depth_count,
                "targeted_count": int(record["targeted_count"]),
                "signature_verified_count": signature_count,
                "package_reproducible_count": repro_count,
                "snapshot_ready_count": snapshot_count,
                "queue_clear_count": queue_clear_count,
                "family_ids": sorted({str(item).strip() for item in record["family_ids"] if str(item).strip()}),
                "summary_line": (
                    f"{project_id}: {'FULL' if ready else 'CHECK'} | families={family_count} | "
                    f"full_depth={full_depth_count} | signature={signature_count} | repro={repro_count} | "
                    f"snapshot={snapshot_count} | queue_clear={queue_clear_count}"
                ),
            }
        )

    project_count = len(project_rows)
    family_count = len({str(row.get("family_id", "") or "").strip() for row in project_family_rows if str(row.get("family_id", "") or "").strip()})
    project_family_count = len(project_family_rows)
    full_depth_project_family_count = sum(
        1 for row in project_family_rows if str(row.get("project_family_status", "")) == "full"
    )
    targeted_project_family_count = sum(
        1 for row in project_family_rows if str(row.get("project_family_status", "")) == "targeted"
    )
    ready_project_count = sum(1 for row in project_rows if bool(row.get("ready")))
    signature_verified_project_count = sum(
        1 for row in project_rows if int(row.get("signature_verified_count", 0) or 0) >= int(row.get("family_count", 0) or 0) > 0
    )
    package_reproducible_project_count = sum(
        1 for row in project_rows if int(row.get("package_reproducible_count", 0) or 0) >= int(row.get("family_count", 0) or 0) > 0
    )
    snapshot_ready_project_count = sum(
        1 for row in project_rows if int(row.get("snapshot_ready_count", 0) or 0) >= int(row.get("family_count", 0) or 0) > 0
    )
    queue_clear_project_count = sum(
        1 for row in project_rows if int(row.get("queue_clear_count", 0) or 0) >= int(row.get("family_count", 0) or 0) > 0
    )
    contract_pass = bool(
        project_count > 0
        and project_family_count > 0
        and ready_project_count >= project_count
        and full_depth_project_family_count >= project_family_count
    )
    reason_code = "PASS" if contract_pass else "CHECK" if project_family_rows else "ERR_INPUT"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-multi-project-runtime-writeback-report",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "runtime_submission_json": str(runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON),
            "runtime_writeback_depth_json": str(
                runtime_writeback_depth_path or DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON
            ),
            "registry_workspace_json": str(registry_workspace_path or DEFAULT_REGISTRY_WORKSPACE_JSON),
        },
        "summary": {
            "project_count": int(project_count),
            "family_count": int(family_count),
            "project_family_count": int(project_family_count),
            "full_depth_project_family_count": int(full_depth_project_family_count),
            "targeted_project_family_count": int(targeted_project_family_count),
            "ready_project_count": int(ready_project_count),
            "signature_verified_project_count": int(signature_verified_project_count),
            "package_reproducible_project_count": int(package_reproducible_project_count),
            "snapshot_ready_project_count": int(snapshot_ready_project_count),
            "queue_clear_project_count": int(queue_clear_project_count),
            "multi_project_runtime_writeback_ready": bool(contract_pass),
            "project_status_label": ", ".join(
                f"{row['project_id']}:{row['project_status']}" for row in project_rows
            ),
        },
        "project_rows": project_rows,
        "project_family_rows": project_family_rows,
        "artifacts": {
            "native_authoring_ops_portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "native_authoring_runtime_submission_lane_json": str(
                runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON
            ),
            "native_authoring_runtime_writeback_depth_report_json": str(
                runtime_writeback_depth_path or DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON
            ),
            "native_authoring_project_registry_workspace_json": str(
                registry_workspace_path or DEFAULT_REGISTRY_WORKSPACE_JSON
            ),
            "native_authoring_multi_project_runtime_writeback_report_json": str(out),
        },
        "summary_line": (
            f"Native authoring multi-project runtime/writeback: {'PASS' if contract_pass else 'CHECK'} | "
            f"projects={project_count} | families={family_count} | project_families={project_family_count} | "
            f"full_depth={full_depth_project_family_count} | ready_projects={ready_project_count} | "
            f"signature={signature_verified_project_count} | repro={package_reproducible_project_count} | "
            f"snapshot={snapshot_ready_project_count} | queue_clear={queue_clear_project_count}"
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
    parser.add_argument("--runtime-submission-json", type=Path, default=DEFAULT_RUNTIME_SUBMISSION_JSON)
    parser.add_argument("--runtime-writeback-depth-json", type=Path, default=DEFAULT_RUNTIME_WRITEBACK_DEPTH_JSON)
    parser.add_argument("--registry-workspace-json", type=Path, default=DEFAULT_REGISTRY_WORKSPACE_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    portfolio_report = _load_json(args.portfolio_json) if args.portfolio_json.exists() else {}
    runtime_submission_report = _load_json(args.runtime_submission_json) if args.runtime_submission_json.exists() else {}
    runtime_writeback_depth_report = (
        _load_json(args.runtime_writeback_depth_json) if args.runtime_writeback_depth_json.exists() else {}
    )
    registry_workspace_report = (
        _load_json(args.registry_workspace_json) if args.registry_workspace_json.exists() else {}
    )
    payload = build_native_authoring_multi_project_runtime_writeback_report(
        portfolio_report=portfolio_report,
        runtime_submission_report=runtime_submission_report,
        runtime_writeback_depth_report=runtime_writeback_depth_report,
        registry_workspace_report=registry_workspace_report,
        portfolio_path=args.portfolio_json,
        runtime_submission_path=args.runtime_submission_json,
        runtime_writeback_depth_path=args.runtime_writeback_depth_json,
        registry_workspace_path=args.registry_workspace_json,
        out=args.out,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
