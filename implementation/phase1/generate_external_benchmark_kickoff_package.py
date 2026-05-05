from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_READINESS_REPORT = Path("implementation/phase1/release/external_benchmark_submission_readiness.json")
DEFAULT_WIND_REGISTRY = Path("implementation/phase1/open_data/wind/wind_benchmark_asset_registry.json")
DEFAULT_TPU_GATE_REPORT = Path("implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json")
DEFAULT_HINGE_REGISTRY = Path("implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json")
DEFAULT_HINGE_GATE_REPORT = Path("implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json")
DEFAULT_HINGE_FIXTURE_REGRESSION_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json"
)
DEFAULT_HINGE_ALIGNMENT_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_refresh_alignment_report.json"
)
DEFAULT_AUDIT_QUEUE_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json"
)
DEFAULT_FRAME_REPORT = Path("implementation/phase1/nonlinear_frame_engine_report.json")
DEFAULT_WIND_SYSTEM_REPORT = Path("implementation/phase1/wind_time_history_gate_report.json")
DEFAULT_SSI_REPORT = Path("implementation/phase1/ssi_boundary_gate_report.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _format_label_counts(label_to_count: dict[str, int]) -> str:
    if not label_to_count:
        return "none"
    return ", ".join(f"{key}={int(value)}" for key, value in sorted(label_to_count.items()))


def _build_system_track(report: dict[str, Any], *, track_id: str, label: str, report_path: str) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "track_id": track_id,
        "label": label,
        "contract_pass": bool(report.get("contract_pass", False)),
        "reason_code": str(report.get("reason_code", "") or ""),
        "report_path": report_path,
        "case_count": int(summary.get("case_count", summary.get("selected_case_count", 0)) or 0),
        "summary": summary,
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    wind_assets = payload.get("wind_component_assets", [])
    hinge_assets = payload.get("hinge_component_assets", [])
    system_tracks = payload.get("system_benchmarks", [])
    submission_queue = payload.get("submission_queue", [])
    pending_packets = payload.get("review_boundary", {}).get("pending_packets", [])
    lines = [
        "# External Benchmark Kickoff Package",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `reason_code`: `{payload.get('reason_code', '')}`",
        f"- `recommended_start_mode`: `{summary.get('recommended_start_mode', '')}`",
        f"- `recommended_submission_scope`: `{summary.get('recommended_submission_scope', '')}`",
        f"- `ready_to_start_now`: `{bool(summary.get('ready_to_start_now', False))}`",
        f"- `ready_to_start_full_submission_now`: `{bool(summary.get('ready_to_start_full_submission_now', False))}`",
        f"- `caution_label`: `{summary.get('caution_label', '') or 'none'}`",
        f"- Commercial scope: `{str(summary.get('commercial_scope_summary_line', '') or '').strip()}`",
        (
            "- Commercial reliability breadth: "
            f"`{str(summary.get('commercial_reliability_breadth_summary_line', '') or '').strip()}`"
        ),
        (
            "- MIDAS/KDS exact row coverage: "
            f"`{str(summary.get('midas_kds_row_provenance_exact_row_coverage_label', '') or '').strip()}`"
        ),
        f"- `onepage_attestation_status`: `{summary.get('onepage_attestation_status', '') or 'unknown'}`",
        "",
        "## Component Benchmarks",
        "",
        f"- `wind_component_asset_count`: `{len(wind_assets)}`",
        f"- `hinge_component_asset_count`: `{len(hinge_assets)}`",
        "",
        "### Wind",
        "",
    ]
    for row in wind_assets:
        lines.append(
            f"- `{row.get('benchmark_seed_id', '')}` | role=`{row.get('case_role', '')}` | "
            f"split=`{row.get('holdout_split', '')}` | signals=`{int(row.get('signal_column_count', 0))}` | "
            f"manifest=`{row.get('source_manifest_path', '')}`"
        )
    lines.extend(["", "### Hinge", ""])
    for row in hinge_assets:
        lines.append(
            f"- `{row.get('seed_id', '')}` | split=`{row.get('holdout_split', '')}` | "
            f"specimen=`{row.get('specimen_id', '')}` | points=`{int(row.get('point_count', 0))}` | "
            f"fixture=`{row.get('fixture_path', '')}`"
        )
    lines.extend(["", "## System Anchors", ""])
    for row in system_tracks:
        lines.append(
            f"- `{row.get('track_id', '')}` | pass=`{bool(row.get('contract_pass', False))}` | "
            f"cases=`{int(row.get('case_count', 0))}` | report=`{row.get('report_path', '')}`"
        )
    lines.extend(["", "## Submission Queue", ""])
    for row in submission_queue:
        lines.append(
            f"- `{row.get('queue_id', '')}` | scope=`{row.get('submission_scope', '')}` | "
            f"owner=`{row.get('owner', '')}` | status=`{row.get('status', '')}` | "
            f"onepage=`{row.get('onepage_attestation', '')}` | "
            f"onepage_status=`{row.get('onepage_attestation_status', '') or 'unknown'}` | "
            f"dry_run_evidence=`{row.get('dry_run_evidence', '') or 'n/a'}`"
        )
    lines.extend(["", "## Review Boundary", ""])
    lines.append(
        f"- `pending_packet_count`: `{int(payload.get('review_boundary', {}).get('pending_packet_count', 0))}`"
    )
    lines.append(
        f"- `pending_packet_label`: `{payload.get('review_boundary', {}).get('pending_packet_label', '') or 'none'}`"
    )
    for row in pending_packets:
        lines.append(
            f"- `{row.get('packet_id', '')}` | family=`{row.get('action_family', '')}` | "
            f"priority=`{row.get('review_priority', '')}` | owner=`{row.get('review_owner', '')}` | "
            f"queue_status={row.get('queue_status', '')}"
        )
    lines.extend(["", "## Next Actions", ""])
    for row in payload.get("next_actions", []):
        lines.append(f"- {row}")
    return "\n".join(lines) + "\n"


def build_kickoff_package(
    *,
    readiness_report: dict[str, Any],
    wind_registry: dict[str, Any],
    tpu_gate_report: dict[str, Any],
    hinge_registry: dict[str, Any],
    hinge_gate_report: dict[str, Any],
    hinge_fixture_regression_report: dict[str, Any],
    hinge_alignment_report: dict[str, Any],
    audit_queue_manifest: dict[str, Any],
    frame_report: dict[str, Any],
    wind_system_report: dict[str, Any],
    ssi_report: dict[str, Any],
    paths: dict[str, str],
) -> dict[str, Any]:
    readiness_summary = (
        readiness_report.get("summary")
        if isinstance(readiness_report.get("summary"), dict)
        else {}
    )
    wind_rows = wind_registry.get("benchmark_ready_assets") or wind_registry.get("rows") or []
    wind_assets = [
        {
            "benchmark_seed_id": str(row.get("benchmark_seed_id", "") or ""),
            "case_role": str(row.get("case_role", "") or ""),
            "holdout_split": str(row.get("holdout_split", "") or ""),
            "signal_column_count": int(row.get("signal_column_count", 0) or 0),
            "source_manifest_path": str(
                row.get("source_manifest_path", row.get("path", "")) or ""
            ),
            "source_origin_class": str(row.get("source_origin_class", "") or ""),
            "raw_hffb_mapping_eligible": bool(row.get("raw_hffb_mapping_eligible", False)),
        }
        for row in wind_rows
        if isinstance(row, dict)
        and str(row.get("source_origin_class", "") or "") == "official_external_benchmark"
        and bool(row.get("raw_hffb_mapping_eligible", False))
    ]
    hinge_rows = hinge_registry.get("rows") or []
    hinge_assets = [
        {
            "seed_id": str(row.get("seed_id", "") or ""),
            "holdout_split": str(row.get("holdout_split", "") or ""),
            "fixture_path": str(row.get("fixture_path", "") or ""),
            "specimen_id": str(row.get("specimen_id", "") or ""),
            "point_count": int(row.get("point_count", 0) or 0),
            "rebar_sensitive_expected": bool(row.get("rebar_sensitive_expected", False)),
            "confinement_sensitive_expected": bool(row.get("confinement_sensitive_expected", False)),
        }
        for row in hinge_rows
        if isinstance(row, dict) and bool(row.get("benchmark_ready", False))
    ]
    pending_packets = []
    for row in audit_queue_manifest.get("audit_review_queue_items", []) or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("queue_status", "") or "") != "pending_review":
            continue
        pending_packets.append(
            {
                "packet_id": str(row.get("packet_id", "") or ""),
                "action_family": str(row.get("action_family", "") or ""),
                "review_priority": str(row.get("review_priority", "") or ""),
                "review_owner": str(row.get("review_owner", "licensed_engineer") or "licensed_engineer"),
                "queue_status": str(row.get("queue_status", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
            }
        )
    pending_family_counts: dict[str, int] = {}
    for row in pending_packets:
        family = str(row.get("action_family", "") or "")
        pending_family_counts[family] = pending_family_counts.get(family, 0) + 1
    system_tracks = [
        _build_system_track(
            frame_report,
            track_id="nonlinear_frame",
            label="Nonlinear frame benchmark",
            report_path=paths["frame_report"],
        ),
        _build_system_track(
            wind_system_report,
            track_id="wind_time_history",
            label="Wind time-history gate",
            report_path=paths["wind_system_report"],
        ),
        _build_system_track(
            ssi_report,
            track_id="ssi_boundary",
            label="SSI boundary gate",
            report_path=paths["ssi_report"],
        ),
    ]
    submission_queue = [
        row
        for row in (readiness_report.get("submission_queue") or [])
        if isinstance(row, dict)
    ]
    onepage_attestation_status = str(readiness_summary.get("onepage_attestation_status", "") or "")
    next_actions = list(readiness_summary.get("next_actions", []) or [])
    if wind_assets:
        next_actions.append("start TPU raw HFFB benchmark execution on isolated/interference official cases")
    if hinge_assets:
        next_actions.append("start PEER hinge benchmark execution across train/val/holdout fixture set")
    if pending_packets:
        next_actions.append("close pending audit-review packets before final external submission package")
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reason_code": str(readiness_report.get("reason_code", "") or ""),
        "contract_pass": bool(readiness_report.get("contract_pass", False)),
        "summary": {
            "recommended_start_mode": str(readiness_summary.get("recommended_start_mode", "") or ""),
            "recommended_submission_scope": str(
                readiness_summary.get("recommended_submission_scope", "") or ""
            ),
            "ready_to_start_now": bool(readiness_summary.get("ready_to_start_now", False)),
            "ready_to_start_full_submission_now": bool(
                readiness_summary.get("ready_to_start_full_submission_now", False)
            ),
            "caution_label": str(readiness_summary.get("caution_label", "") or ""),
            "blocker_label": str(readiness_summary.get("blocker_label", "") or ""),
            "wind_component_asset_count": int(len(wind_assets)),
            "hinge_component_asset_count": int(len(hinge_assets)),
            "system_benchmark_count": int(len(system_tracks)),
            "pending_packet_count": int(len(pending_packets)),
            "pending_packet_label": _format_label_counts(pending_family_counts),
            "submission_queue_count": int(
                readiness_summary.get("submission_queue_count", len(submission_queue)) or 0
            ),
            "submission_queue_ready_count": int(
                readiness_summary.get("submission_queue_ready_count", 0) or 0
            ),
            "submission_queue_review_pending_count": int(
                readiness_summary.get("submission_queue_review_pending_count", 0) or 0
            ),
            "submission_queue_blocked_count": int(
                readiness_summary.get("submission_queue_blocked_count", 0) or 0
            ),
            "onepage_attestation_status": onepage_attestation_status,
            "onepage_attestation_required_count": int(
                readiness_summary.get("onepage_attestation_required_count", len(submission_queue)) or 0
            ),
            "onepage_attestation_ready_count": int(
                readiness_summary.get("onepage_attestation_ready_count", 0) or 0
            ),
            "commercial_scope_summary_line": str(readiness_summary.get("commercial_scope_summary_line", "") or ""),
            "commercial_reliability_breadth_summary_line": str(
                readiness_summary.get("commercial_reliability_breadth_summary_line", "") or ""
            ),
            "midas_kds_row_provenance_exact_row_coverage_label": str(
                readiness_summary.get("midas_kds_row_provenance_exact_row_coverage_label", "") or ""
            ),
            "midas_kds_row_provenance_preview_rows_present": bool(
                readiness_summary.get("midas_kds_row_provenance_preview_rows_present", False)
            ),
        },
        "wind_component_assets": wind_assets,
        "hinge_component_assets": hinge_assets,
        "system_benchmarks": system_tracks,
        "submission_queue": submission_queue,
        "review_boundary": {
            "pending_packet_count": int(len(pending_packets)),
            "pending_packet_label": _format_label_counts(pending_family_counts),
            "pending_packets": pending_packets,
            "panel_zone_validation_boundary": str(
                readiness_summary.get("panel_zone_validation_boundary", "") or ""
            ),
        },
        "benchmark_contracts": {
            "tpu_hffb_benchmark_gate_pass": bool(tpu_gate_report.get("contract_pass", False)),
            "peer_spd_hinge_benchmark_gate_pass": bool(hinge_gate_report.get("contract_pass", False)),
            "peer_spd_hinge_fixture_regression_pass": bool(
                hinge_fixture_regression_report.get("contract_pass", False)
            ),
            "peer_spd_hinge_refresh_alignment_pass": bool(
                hinge_alignment_report.get("contract_pass", False)
            ),
        },
        "next_actions": next_actions,
        "artifacts": paths,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-report", default=str(DEFAULT_READINESS_REPORT))
    parser.add_argument("--wind-registry", default=str(DEFAULT_WIND_REGISTRY))
    parser.add_argument("--tpu-gate-report", default=str(DEFAULT_TPU_GATE_REPORT))
    parser.add_argument("--hinge-registry", default=str(DEFAULT_HINGE_REGISTRY))
    parser.add_argument("--hinge-gate-report", default=str(DEFAULT_HINGE_GATE_REPORT))
    parser.add_argument(
        "--hinge-fixture-regression-report",
        default=str(DEFAULT_HINGE_FIXTURE_REGRESSION_REPORT),
    )
    parser.add_argument("--hinge-alignment-report", default=str(DEFAULT_HINGE_ALIGNMENT_REPORT))
    parser.add_argument("--audit-review-queue-manifest", default=str(DEFAULT_AUDIT_QUEUE_MANIFEST))
    parser.add_argument("--frame-report", default=str(DEFAULT_FRAME_REPORT))
    parser.add_argument("--wind-system-report", default=str(DEFAULT_WIND_SYSTEM_REPORT))
    parser.add_argument("--ssi-report", default=str(DEFAULT_SSI_REPORT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    paths = {
        "readiness_report": str(args.readiness_report),
        "wind_registry": str(args.wind_registry),
        "tpu_gate_report": str(args.tpu_gate_report),
        "hinge_registry": str(args.hinge_registry),
        "hinge_gate_report": str(args.hinge_gate_report),
        "hinge_fixture_regression_report": str(args.hinge_fixture_regression_report),
        "hinge_alignment_report": str(args.hinge_alignment_report),
        "audit_review_queue_manifest": str(args.audit_review_queue_manifest),
        "frame_report": str(args.frame_report),
        "wind_system_report": str(args.wind_system_report),
        "ssi_report": str(args.ssi_report),
    }
    payload = build_kickoff_package(
        readiness_report=_load_json(Path(args.readiness_report)),
        wind_registry=_load_json(Path(args.wind_registry)),
        tpu_gate_report=_load_json(Path(args.tpu_gate_report)),
        hinge_registry=_load_json(Path(args.hinge_registry)),
        hinge_gate_report=_load_json(Path(args.hinge_gate_report)),
        hinge_fixture_regression_report=_load_json(Path(args.hinge_fixture_regression_report)),
        hinge_alignment_report=_load_json(Path(args.hinge_alignment_report)),
        audit_queue_manifest=_load_json(Path(args.audit_review_queue_manifest)),
        frame_report=_load_json(Path(args.frame_report)),
        wind_system_report=_load_json(Path(args.wind_system_report)),
        ssi_report=_load_json(Path(args.ssi_report)),
        paths=paths,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "external_benchmark_kickoff_package.json"
    md_path = out_dir / "external_benchmark_kickoff_package.md"
    _write_json(json_path, payload)
    md_path.write_text(_build_markdown(payload), encoding="utf-8")
    print(f"Wrote external benchmark kickoff package: {json_path}")
    print(f"Wrote external benchmark kickoff markdown: {md_path}")


if __name__ == "__main__":
    main()
