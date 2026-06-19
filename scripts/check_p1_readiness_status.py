#!/usr/bin/env python3
"""Summarize P1 readiness without bypassing the P0 release gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p0_closure_status import build_status as build_p0_status  # noqa: E402
from check_p0_closure_status import DEFAULT_PUBLICATION_EVIDENCE_INDEX  # noqa: E402
from plan_open_data_artifact_restore import build_restore_plan  # noqa: E402
from plan_open_data_artifact_restore import DEFAULT_MANIFEST as DEFAULT_OPEN_DATA_MANIFEST  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


DEFAULT_COVERAGE_MATRIX = Path("implementation/phase1/real_project_parser_coverage_matrix.json")
DEFAULT_PEER_METRIC_RECORDS = Path("implementation/phase1/peer_tbi_benchmark_metric_records.json")
DEFAULT_ROW_PROVENANCE = Path("implementation/phase1/real_project_row_provenance_report.json")
MIDAS_KDS_VALIDATION_SOURCE_ID = "midas_kds_geometry_bridge_validation"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _status(ok: bool) -> str:
    return "ready" if ok else "blocked"


def _p0_gate(payload: dict[str, Any]) -> dict[str, Any]:
    p0_closed = bool(payload.get("p0_closed", False))
    core_evidence_closed = bool(payload.get("core_evidence_closed", False))
    release_publication_closed = bool(payload.get("release_publication_closed", False))
    return {
        "label": "P0 release publication",
        "status": _status(p0_closed),
        "ok": p0_closed,
        "core_evidence_closed": core_evidence_closed,
        "release_publication_closed": release_publication_closed,
        "blocks_p1_execution": not p0_closed,
    }


def _open_data_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    ok = bool(payload.get("ok", False))
    return {
        "label": "Open-data artifact restore",
        "status": _status(ok),
        "ok": ok,
        "artifact_count": int(summary.get("artifact_count", 0) or 0),
        "already_restored": int(summary.get("already_restored", 0) or 0),
        "cache_ready": int(summary.get("cache_ready", 0) or 0),
        "blocked": int(summary.get("blocked", 0) or 0),
        "total_bytes": int(summary.get("total_bytes", 0) or 0),
    }


def _coverage_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    raw_allowed = bool(summary.get("raw_redistribution_auto_allowed_after_p0", True))
    koneps_targets = int(summary.get("koneps_parser_target_count", 0) or 0)
    peer_targets = int(summary.get("peer_tbi_benchmark_metric_target_count", 0) or 0)
    ok = bool(payload.get("contract_pass", False)) and not raw_allowed and koneps_targets >= 7 and peer_targets >= 5
    return {
        "label": "Real-project parser coverage",
        "status": _status(ok),
        "ok": ok,
        "koneps_parser_target_count": koneps_targets,
        "peer_tbi_benchmark_metric_target_count": peer_targets,
        "raw_redistribution_auto_allowed_after_p0": raw_allowed,
    }


def _peer_metric_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    raw_allowed = bool(summary.get("raw_redistribution_auto_allowed", True))
    metric_records = int(summary.get("metric_record_count", 0) or 0)
    required_groups = int(summary.get("required_metric_group_count", 0) or 0)
    recorded_groups = int(summary.get("recorded_metric_group_count", 0) or 0)
    ok = (
        bool(payload.get("contract_pass", False))
        and not raw_allowed
        and metric_records >= 5
        and required_groups >= 5
        and recorded_groups >= required_groups
    )
    return {
        "label": "PEER TBI benchmark metric records",
        "status": _status(ok),
        "ok": ok,
        "metric_record_count": metric_records,
        "required_metric_group_count": required_groups,
        "recorded_metric_group_count": recorded_groups,
        "raw_redistribution_auto_allowed": raw_allowed,
    }


def _row_provenance_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = payload.get("source_provenance_rows") if isinstance(payload.get("source_provenance_rows"), list) else []
    midas_kds_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("source_id", "") or "") == MIDAS_KDS_VALIDATION_SOURCE_ID
    ]
    midas_kds_validation_row_present = any(
        row.get("release_surface_allowed") is False
        and isinstance(row.get("parser_contract"), dict)
        and bool((row.get("parser_contract") or {}).get("contract_pass", False))
        for row in midas_kds_rows
    )
    row_count = int(summary.get("row_count", 0) or 0)
    release_surface_allowed_count = int(summary.get("release_surface_allowed_count", 0) or 0)
    midas_kds_validation_present = bool(summary.get("midas_kds_validation_present", False))
    midas_kds_validation_artifact_count = int(summary.get("midas_kds_validation_artifact_count", 0) or 0)
    midas_kds_exact_geometry_bridge_pass_count = int(
        summary.get("midas_kds_exact_geometry_bridge_pass_count", 0) or 0
    )
    midas_kds_exact_row_provenance_count = int(summary.get("midas_kds_exact_row_provenance_count", 0) or 0)
    midas_kds_review_row_count = int(summary.get("midas_kds_review_row_count", 0) or 0)
    midas_kds_row_provenance_complete = bool(
        midas_kds_validation_present
        and midas_kds_validation_row_present
        and midas_kds_validation_artifact_count >= 1
        and midas_kds_exact_geometry_bridge_pass_count >= midas_kds_validation_artifact_count
        and midas_kds_review_row_count >= 1
        and midas_kds_exact_row_provenance_count >= midas_kds_review_row_count
    )
    ok = (
        bool(payload.get("contract_pass", False))
        and float(payload.get("row_provenance_coverage", 0.0) or 0.0) >= 1.0
        and bool(payload.get("raw_redistribution_default_blocked", False))
        and bool(summary.get("required_source_families_present", False))
        and bool(summary.get("all_rows_have_required_fields", False))
        and row_count >= 3
        and release_surface_allowed_count == 0
        and midas_kds_row_provenance_complete
    )
    return {
        "label": "Real-project row provenance",
        "status": _status(ok),
        "ok": ok,
        "row_count": row_count,
        "release_surface_allowed_count": release_surface_allowed_count,
        "row_provenance_coverage": float(payload.get("row_provenance_coverage", 0.0) or 0.0),
        "raw_redistribution_default_blocked": bool(payload.get("raw_redistribution_default_blocked", False)),
        "midas_kds_validation_present": midas_kds_validation_present,
        "midas_kds_validation_row_present": midas_kds_validation_row_present,
        "midas_kds_validation_artifact_count": midas_kds_validation_artifact_count,
        "midas_kds_exact_geometry_bridge_pass_count": midas_kds_exact_geometry_bridge_pass_count,
        "midas_kds_exact_row_provenance_count": midas_kds_exact_row_provenance_count,
        "midas_kds_review_row_count": midas_kds_review_row_count,
        "midas_kds_row_provenance_complete": midas_kds_row_provenance_complete,
    }


def _read_or_build_p0(path: Path | None, publication_evidence_index: Path | None) -> dict[str, Any]:
    if path is not None:
        return _load_json(path)
    return build_p0_status(publication_evidence_index=publication_evidence_index)


def _read_or_build_open_data(path: Path | None, cache_root: Path | None) -> dict[str, Any]:
    if path is not None:
        return _load_json(path)
    return build_restore_plan(cache_root=cache_root)


def build_status(
    *,
    p0_status: Path | None = None,
    publication_evidence_index: Path | None = None,
    open_data_restore_plan: Path | None = None,
    coverage_matrix: Path = DEFAULT_COVERAGE_MATRIX,
    peer_metric_records: Path = DEFAULT_PEER_METRIC_RECORDS,
    row_provenance: Path = DEFAULT_ROW_PROVENANCE,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    p0_payload = _read_or_build_p0(p0_status, publication_evidence_index)
    p0_gate = _p0_gate(p0_payload)
    gates = [
        p0_gate,
        _open_data_gate(_read_or_build_open_data(open_data_restore_plan, cache_root)),
        _coverage_gate(_load_json(coverage_matrix)),
        _peer_metric_gate(_load_json(peer_metric_records)),
        _row_provenance_gate(_load_json(row_provenance)),
    ]
    input_gates = gates[1:]
    p1_inputs_ready = bool(p0_gate["core_evidence_closed"]) and all(bool(gate["ok"]) for gate in input_gates)
    p0_release_blocker = not bool(p0_gate["ok"])
    p1_execution_unblocked = p1_inputs_ready and not p0_release_blocker
    if not p1_inputs_ready:
        next_action = "fix blocked P1 input gates"
    elif p0_release_blocker:
        next_action = "close P0-1 release publication before starting P1 execution"
    else:
        next_action = "start P1 quality/fallback/benchmark breadth"
    return {
        "schema_version": "p1-readiness-status.v1",
        **release_evidence_metadata(
            input_paths=[
                *( [p0_status] if p0_status is not None else [] ),
                publication_evidence_index or Path(str(p0_payload.get("publication_evidence_index", "") or DEFAULT_PUBLICATION_EVIDENCE_INDEX)),
                open_data_restore_plan or DEFAULT_OPEN_DATA_MANIFEST,
                coverage_matrix,
                peer_metric_records,
                row_provenance,
            ],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_p0_open_data_parser_peer_and_row_provenance_receipts",
        ),
        "status": "ready" if p1_execution_unblocked else "blocked",
        "p0_core_evidence_closed": bool(p0_gate["core_evidence_closed"]),
        "p1_inputs_ready": p1_inputs_ready,
        "p1_execution_unblocked": p1_execution_unblocked,
        "p0_release_blocker": p0_release_blocker,
        "publication_evidence_index": str(
            publication_evidence_index or p0_payload.get("publication_evidence_index", "")
        ),
        "default_publication_evidence_index": str(DEFAULT_PUBLICATION_EVIDENCE_INDEX),
        "gates": gates,
        "next_action": next_action,
    }


def _markdown(status: dict[str, Any]) -> str:
    lines = [
        "# P1 Readiness Status",
        "",
        f"- P1 inputs ready: `{bool(status['p1_inputs_ready'])}`",
        f"- P1 execution unblocked: `{bool(status['p1_execution_unblocked'])}`",
        f"- P0 release blocker: `{bool(status['p0_release_blocker'])}`",
        "- P1 work slice: `quality/fallback/benchmark breadth`",
        f"- Next action: `{status['next_action']}`",
        "",
        "| Gate | Status |",
        "| --- | --- |",
    ]
    for gate in status["gates"]:
        lines.append(f"| {gate['label']} | `{gate['status']}` |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize P1 readiness while preserving the P0 release blocker.")
    parser.add_argument("--p0-status", type=Path)
    parser.add_argument(
        "--publication-evidence-index",
        type=Path,
        help="Release publication evidence index used when --p0-status is omitted.",
    )
    parser.add_argument("--open-data-restore-plan", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--coverage-matrix", type=Path, default=DEFAULT_COVERAGE_MATRIX)
    parser.add_argument("--peer-metric-records", type=Path, default=DEFAULT_PEER_METRIC_RECORDS)
    parser.add_argument("--row-provenance", type=Path, default=DEFAULT_ROW_PROVENANCE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument(
        "--fail-core-open",
        action="store_true",
        help="Fail only when the P0 core evidence prerequisite is open.",
    )
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = build_status(
            p0_status=args.p0_status,
            publication_evidence_index=args.publication_evidence_index,
            open_data_restore_plan=args.open_data_restore_plan,
            coverage_matrix=args.coverage_matrix,
            peer_metric_records=args.peer_metric_records,
            row_provenance=args.row_provenance,
            cache_root=args.cache_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P1 readiness status check failed: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(status), encoding="utf-8")
    print(payload if args.json else _markdown(status))
    if args.fail_core_open and not bool(status["p0_core_evidence_closed"]):
        return 1
    return 1 if args.fail_blocked and not bool(status["p1_execution_unblocked"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
