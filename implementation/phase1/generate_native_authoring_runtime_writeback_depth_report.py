#!/usr/bin/env python3
"""Generate native authoring runtime/writeback depth coverage report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/portfolio")
DEFAULT_PORTFOLIO_JSON = DEFAULT_OUT_DIR / "native_authoring_ops_portfolio.json"
DEFAULT_RUNTIME_SUBMISSION_JSON = DEFAULT_OUT_DIR / "native_authoring_runtime_submission_lane.json"
DEFAULT_REGISTRY_INDEX_JSON = DEFAULT_OUT_DIR / "native_authoring_project_registry_index.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_runtime_writeback_depth_report.json"

REASONS = {
    "PASS": "native authoring runtime writeback depth report generated",
    "CHECK": "native authoring runtime writeback depth report generated with partial closure",
    "ERR_INPUT": "no native authoring runtime/project rows supplied",
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
        row.get("project_id"),
        f"family-{index}",
    )


def _depth_status(*, depth_ready: bool, partial_ready: bool) -> str:
    if depth_ready:
        return "full"
    if partial_ready:
        return "targeted"
    return "check"


def build_native_authoring_runtime_writeback_depth_report(
    *,
    portfolio_report: dict[str, Any] | list[Any] | None = None,
    runtime_submission_report: dict[str, Any] | list[Any] | None = None,
    registry_index_report: dict[str, Any] | list[Any] | None = None,
    portfolio_path: Path | None = None,
    runtime_submission_path: Path | None = None,
    registry_index_path: Path | None = None,
    out: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or _now_utc_iso()

    portfolio_rows = _extract_rows(portfolio_report, keys=("family_rows", "families"))
    runtime_rows = _extract_rows(runtime_submission_report, keys=("family_rows", "submission_rows", "rows"))
    registry_project_rows = _extract_rows(registry_index_report, keys=("project_rows", "projects"))

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
    registry_by_project = {
        _first_text(row.get("project_id")): row
        for row in registry_project_rows
        if _first_text(row.get("project_id"))
    }

    family_ids = sorted(set(portfolio_by_family) | set(runtime_by_family))
    emitted_rows: list[dict[str, Any]] = []

    for family_id in family_ids:
        portfolio_row = portfolio_by_family.get(family_id, {})
        runtime_row = runtime_by_family.get(family_id, {})
        project_id = _first_text(runtime_row.get("project_id"), portfolio_row.get("project_id"))
        registry_row = registry_by_project.get(project_id, {})

        family_label = _first_text(
            runtime_row.get("family_label"),
            portfolio_row.get("family_label"),
            family_id.replace("_", " "),
        )
        project_name = _first_text(runtime_row.get("project_name"), portfolio_row.get("project_name"))

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
                runtime_row.get("writeback_ready"),
                runtime_row.get("registry_ready"),
                portfolio_row.get("registry_ready"),
            )
        )
        registry_ready = bool(
            _first_bool(
                runtime_row.get("registry_ready"),
                portfolio_row.get("registry_ready"),
                _first_int(registry_row.get("registry_count")) > 0,
            )
        )
        signature_verified = bool(
            _first_bool(
                runtime_row.get("signature_verified"),
                portfolio_row.get("signature_verified"),
                registry_row.get("latest_signature_verified"),
            )
        )
        package_reproducible = bool(
            _first_bool(
                registry_row.get("latest_package_reproducible"),
                registry_row.get("package_reproducible"),
            )
        )
        approval_count = _first_int(
            runtime_row.get("approval_count"),
            registry_row.get("latest_approval_count"),
        )
        approved_count = _first_int(
            registry_row.get("latest_approved_count"),
            approval_count,
        )
        approvals_ready = bool(approval_count > 0 and approved_count >= approval_count)
        snapshot_count = _first_int(runtime_row.get("snapshot_count"), portfolio_row.get("snapshot_count"))
        snapshot_ready = snapshot_count > 0
        submission_status = _first_text(runtime_row.get("submission_status"), runtime_row.get("lane_status"))
        queue_clear = submission_status.lower() not in {"queued", "planned", "blocked", "rerun_requested"}

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
        depth_ready = all(
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
        depth_status = _depth_status(depth_ready=depth_ready, partial_ready=partial_ready)
        axes_label = " | ".join(
            [
                f"runtime={'yes' if runtime_ready else 'no'}",
                f"submission={'yes' if submission_ready else 'no'}",
                f"writeback={'yes' if writeback_ready else 'no'}",
                f"registry={'yes' if registry_ready else 'no'}",
                f"signature={'yes' if signature_verified else 'no'}",
                f"repro={'yes' if package_reproducible else 'no'}",
                f"approvals={approved_count}/{approval_count}",
                f"snapshots={snapshot_count}",
                f"queue={'clear' if queue_clear else submission_status or 'queued'}",
            ]
        )
        emitted_rows.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "project_id": project_id,
                "project_name": project_name,
                "runtime_writeback_depth_status": depth_status,
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
                "axes_label": axes_label,
                "summary_line": (
                    f"{family_id}: {depth_status.upper()} | runtime={'yes' if runtime_ready else 'no'} | "
                    f"writeback={'yes' if writeback_ready else 'no'} | registry={'yes' if registry_ready else 'no'} | "
                    f"signature={'yes' if signature_verified else 'no'} | repro={'yes' if package_reproducible else 'no'} | "
                    f"approvals={approved_count}/{approval_count} | snapshots={snapshot_count} | "
                    f"queue={'clear' if queue_clear else submission_status or 'queued'}"
                ),
                "artifacts": {
                    "project_registry_json": _first_text(
                        runtime_row.get("artifacts", {}).get("project_registry_json")
                        if isinstance(runtime_row.get("artifacts"), dict)
                        else "",
                        portfolio_row.get("artifacts", {}).get("project_registry_json")
                        if isinstance(portfolio_row.get("artifacts"), dict)
                        else "",
                        registry_row.get("latest_path"),
                    ),
                    "batch_job_report_json": _first_text(
                        runtime_row.get("artifacts", {}).get("batch_job_report_json")
                        if isinstance(runtime_row.get("artifacts"), dict)
                        else "",
                        portfolio_row.get("artifacts", {}).get("batch_job_report_json")
                        if isinstance(portfolio_row.get("artifacts"), dict)
                        else "",
                    ),
                    "project_package_zip": _first_text(
                        runtime_row.get("artifacts", {}).get("project_package_zip")
                        if isinstance(runtime_row.get("artifacts"), dict)
                        else "",
                        portfolio_row.get("artifacts", {}).get("project_package_zip")
                        if isinstance(portfolio_row.get("artifacts"), dict)
                        else "",
                    ),
                    "project_registry_signature": _first_text(
                        runtime_row.get("artifacts", {}).get("project_registry_signature")
                        if isinstance(runtime_row.get("artifacts"), dict)
                        else "",
                        portfolio_row.get("artifacts", {}).get("project_registry_signature")
                        if isinstance(portfolio_row.get("artifacts"), dict)
                        else "",
                    ),
                },
            }
        )

    family_count = len(emitted_rows)
    depth_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("runtime_writeback_depth_status") == "full"))
    targeted_family_count = sum(1 for row in emitted_rows if bool(row.get("runtime_writeback_depth_status") == "targeted"))
    registry_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("registry_ready")))
    signature_verified_family_count = sum(1 for row in emitted_rows if bool(row.get("signature_verified")))
    package_reproducible_family_count = sum(1 for row in emitted_rows if bool(row.get("package_reproducible")))
    approval_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("approvals_ready")))
    snapshot_ready_family_count = sum(1 for row in emitted_rows if bool(row.get("snapshot_ready")))
    queue_clear_family_count = sum(1 for row in emitted_rows if bool(row.get("queue_clear")))
    max_snapshot_count = max((int(row.get("snapshot_count", 0) or 0) for row in emitted_rows), default=0)
    contract_pass = bool(family_count > 0 and depth_ready_family_count >= family_count)
    reason_code = "PASS" if contract_pass else "CHECK" if emitted_rows else "ERR_INPUT"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-native-authoring-runtime-writeback-depth-report",
        "generated_at": timestamp,
        "inputs": {
            "portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "runtime_submission_json": str(runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON),
            "registry_index_json": str(registry_index_path or DEFAULT_REGISTRY_INDEX_JSON),
        },
        "summary": {
            "family_count": int(family_count),
            "depth_ready_family_count": int(depth_ready_family_count),
            "targeted_family_count": int(targeted_family_count),
            "registry_ready_family_count": int(registry_ready_family_count),
            "signature_verified_family_count": int(signature_verified_family_count),
            "package_reproducible_family_count": int(package_reproducible_family_count),
            "approval_ready_family_count": int(approval_ready_family_count),
            "snapshot_ready_family_count": int(snapshot_ready_family_count),
            "queue_clear_family_count": int(queue_clear_family_count),
            "max_snapshot_count": int(max_snapshot_count),
            "runtime_writeback_depth_ready": bool(contract_pass),
            "family_status_label": ", ".join(
                f"{row['family_id']}:{row['runtime_writeback_depth_status']}" for row in emitted_rows
            ),
        },
        "family_rows": emitted_rows,
        "artifacts": {
            "native_authoring_ops_portfolio_json": str(portfolio_path or DEFAULT_PORTFOLIO_JSON),
            "native_authoring_runtime_submission_lane_json": str(
                runtime_submission_path or DEFAULT_RUNTIME_SUBMISSION_JSON
            ),
            "native_authoring_project_registry_index_json": str(
                registry_index_path or DEFAULT_REGISTRY_INDEX_JSON
            ),
            "native_authoring_runtime_writeback_depth_report_json": str(out),
        },
        "summary_line": (
            f"Native authoring runtime writeback depth: {'PASS' if contract_pass else 'CHECK'} | "
            f"families={family_count} | full_depth={depth_ready_family_count} | "
            f"targeted={targeted_family_count} | registry={registry_ready_family_count} | "
            f"signature={signature_verified_family_count} | repro={package_reproducible_family_count} | "
            f"snapshot={snapshot_ready_family_count} | queue_clear={queue_clear_family_count}"
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
    parser.add_argument("--registry-index-json", type=Path, default=DEFAULT_REGISTRY_INDEX_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    portfolio_report = _load_json(args.portfolio_json) if args.portfolio_json.exists() else {}
    runtime_submission_report = (
        _load_json(args.runtime_submission_json) if args.runtime_submission_json.exists() else {}
    )
    registry_index_report = _load_json(args.registry_index_json) if args.registry_index_json.exists() else {}
    payload = build_native_authoring_runtime_writeback_depth_report(
        portfolio_report=portfolio_report,
        runtime_submission_report=runtime_submission_report,
        registry_index_report=registry_index_report,
        portfolio_path=args.portfolio_json,
        runtime_submission_path=args.runtime_submission_json,
        registry_index_path=args.registry_index_json,
        out=args.out,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
