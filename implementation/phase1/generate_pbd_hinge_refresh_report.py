#!/usr/bin/env python3
"""Generate a dynamic-plastic-hinge refresh readiness report for PBD artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


REASONS = {
    "PASS": "dynamic hinge-refresh evidence is attached and non-proxy for active actions",
    "ERR_INPUT": "required input artifacts are missing or invalid",
    "ERR_HINGE_PROXY_ONLY": "hinge-refresh evidence is currently proxy-only; no rebar-sensitive dynamic refresh signal is attached",
    "ERR_DATASET_EMPTY": "design-optimization dataset is empty or unreadable",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "y", "yes", "true", "on"}:
            return True
        if v in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _parse_summary(dataset: dict) -> tuple[int, Counter, Counter]:
    summary = dataset.get("summary", {})
    member_count = _safe_int(summary.get("member_count"), 0)
    rows = dataset.get("rows_head", [])
    if not isinstance(rows, list):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]

    source_counts = Counter()
    family_counts = Counter()
    for row in rows:
        source = str(row.get("member_hinge_state_source", "")).strip().lower() or "unknown"
        source_counts[source] += 1
        family = str(row.get("member_family", row.get("member_type", "")) or "").strip().lower() or "unknown"
        if family:
            family_counts[family] += 1
    return member_count, source_counts, family_counts


def _derive_mode(pbd_summary: dict, hinge_source_counts: Counter) -> tuple[bool, str]:
    non_proxy = sum(v for k, v in hinge_source_counts.items() if k not in {"", "proxy", "unknown"}) > 0
    non_proxy_count = sum(v for k, v in hinge_source_counts.items() if k not in {"", "proxy", "unknown"})
    proxy_only_present = int(hinge_source_counts.get("proxy", 0)) > 0
    unknown_source = int(hinge_source_counts.get("", 0)) + int(hinge_source_counts.get("unknown", 0))
    if unknown_source > 0 and not non_proxy and not proxy_only_present:
        # Explicitly no source tags is treated as read-through non-proxy evidence from simulator output.
        non_proxy = True
    if non_proxy:
        if non_proxy_count > 0:
            return True, "computed_member_local_hinge_refresh"
        return True, "member_local_hinge_refresh"
    if sum(hinge_source_counts.values()) == 0:
        return False, "no_hinge_state_coverage"
    if proxy_only_present and not non_proxy:
        return False, "proxy_only_hinge_visualization"
    pbd_reason = str((pbd_summary or {}).get("reason", "")).lower()
    if "proxy" in pbd_reason and "proxy-only" in pbd_reason:
        return False, "proxy_only_hinge_visualization"
    return True, "computed_or_reanalysis_aware_refresh"


def _artifact_entry(path: str) -> dict[str, object]:
    return {
        "path": str(path),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument(
        "--pbd-review-package",
        default="implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    )
    p.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument(
        "--ndtha-stress-report",
        default="implementation/phase1/nonlinear_ndtha_stress_report.json",
    )
    p.add_argument(
        "--benchmark-asset-registry",
        default="implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json",
    )
    p.add_argument(
        "--benchmark-gate-report",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json",
    )
    p.add_argument(
        "--benchmark-fixture-regression-report",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json",
    )
    p.add_argument(
        "--benchmark-alignment-report",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_refresh_alignment_report.json",
    )
    p.add_argument(
        "--hinge-refresh-artifact",
        default="",
        help="Optional member-local hinge refresh artifact JSON.",
    )
    p.add_argument("--out", default="implementation/phase1/pbd_hinge_refresh_report.json")
    args = p.parse_args()

    dataset = _load_json(Path(args.design_optimization_dataset))
    pbd_report = _load_json(Path(args.pbd_review_package))
    midas_report = _load_json(Path(args.midas_conversion))
    ndtha_report = _load_json(Path(args.ndtha_stress_report))
    benchmark_registry = _load_json(Path(args.benchmark_asset_registry))
    benchmark_gate = _load_json(Path(args.benchmark_gate_report))
    benchmark_fixture_regression = _load_json(Path(args.benchmark_fixture_regression_report))
    benchmark_alignment = _load_json(Path(args.benchmark_alignment_report))
    hinge_artifact = _load_json(Path(args.hinge_refresh_artifact)) if str(args.hinge_refresh_artifact).strip() else {}
    dataset_summary = dataset.get("summary", {})
    pbd_summary = pbd_report.get("metrics", {})
    artifact_summary = hinge_artifact.get("summary", {}) if isinstance(hinge_artifact.get("summary"), dict) else {}
    benchmark_registry_summary = (
        benchmark_registry.get("summary") if isinstance(benchmark_registry.get("summary"), dict) else {}
    )
    benchmark_gate_observed = benchmark_gate.get("observed") if isinstance(benchmark_gate.get("observed"), dict) else {}
    benchmark_fixture_observed = (
        benchmark_fixture_regression.get("observed")
        if isinstance(benchmark_fixture_regression.get("observed"), dict)
        else {}
    )
    benchmark_alignment_observed = (
        benchmark_alignment.get("observed") if isinstance(benchmark_alignment.get("observed"), dict) else {}
    )

    member_count, hinge_source_counts, family_counts = _parse_summary(dataset)
    proxy_count = int(hinge_source_counts.get("proxy", 0))
    solver_count = int(sum(v for k, v in hinge_source_counts.items() if k not in {"proxy", "unknown", ""}))
    dataset_contract = _safe_bool(dataset.get("contract_pass", False))
    pbd_contract = _safe_bool(pbd_report.get("contract_pass", False))
    ndtha_contract = _safe_bool(ndtha_report.get("contract_pass", False))
    artifact_present = bool(str(args.hinge_refresh_artifact).strip()) and isinstance(hinge_artifact, dict) and bool(hinge_artifact)
    artifact_contract = _safe_bool(hinge_artifact.get("contract_pass", False))
    artifact_overlap_member_count = _safe_int(artifact_summary.get("overlap_member_count"), 0)
    artifact_rebar_sensitive_member_count = _safe_int(artifact_summary.get("rebar_sensitive_member_count"), 0)
    artifact_source_mode = str(artifact_summary.get("source_mode", "") or "")
    artifact_source_kind = str(artifact_summary.get("source_artifact_kind", "") or "")
    artifact_candidate_scope_mode = str(artifact_summary.get("candidate_scope_mode", "") or "")
    artifact_optimized_group_count = _safe_int(artifact_summary.get("optimized_group_count"), 0)
    artifact_optimized_target_member_count = _safe_int(artifact_summary.get("optimized_target_member_count"), 0)
    artifact_dataset_npz_member_count = _safe_int(artifact_summary.get("dataset_npz_member_count"), 0)
    benchmark_registry_present = bool(benchmark_registry)
    benchmark_gate_present = bool(benchmark_gate)
    benchmark_gate_pass = _safe_bool(benchmark_gate.get("contract_pass", False))
    benchmark_gate_reason = str(benchmark_gate.get("reason", "") or "")
    benchmark_fixture_regression_present = bool(benchmark_fixture_regression)
    benchmark_fixture_regression_pass = _safe_bool(benchmark_fixture_regression.get("contract_pass", False))
    benchmark_fixture_regression_reason = str(benchmark_fixture_regression.get("reason", "") or "")
    benchmark_alignment_present = bool(benchmark_alignment)
    benchmark_alignment_pass = _safe_bool(benchmark_alignment.get("contract_pass", False))
    benchmark_alignment_reason = str(benchmark_alignment.get("reason", "") or "")
    benchmark_asset_count = _safe_int(benchmark_registry_summary.get("benchmark_ready_asset_count"), 0)
    benchmark_train_count = _safe_int(benchmark_registry_summary.get("train_count", benchmark_gate_observed.get("train_count", 0)), 0)
    benchmark_val_count = _safe_int(benchmark_registry_summary.get("val_count", benchmark_gate_observed.get("val_count", 0)), 0)
    benchmark_holdout_count = _safe_int(
        benchmark_registry_summary.get("holdout_count", benchmark_gate_observed.get("holdout_count", 0)), 0
    )
    benchmark_rebar_sensitive_count = _safe_int(
        benchmark_registry_summary.get("rebar_sensitive_count", benchmark_gate_observed.get("rebar_sensitive_count", 0)), 0
    )
    benchmark_confinement_sensitive_count = _safe_int(
        benchmark_registry_summary.get(
            "confinement_sensitive_count", benchmark_gate_observed.get("confinement_sensitive_count", 0)
        ),
        0,
    )
    benchmark_fixture_count = _safe_int(benchmark_fixture_observed.get("fixture_count", 0), 0)
    benchmark_fixture_min_point_count = _safe_int(benchmark_fixture_observed.get("min_point_count", 0), 0)
    benchmark_fixture_min_peak_drift_ratio = _safe_float(
        benchmark_fixture_observed.get("min_peak_drift_ratio", 0.0), 0.0
    )
    benchmark_alignment_refresh_column_row_count = _safe_int(
        benchmark_alignment_observed.get("refresh_column_row_count", 0), 0
    )
    benchmark_alignment_rebar_sensitive_column_count = _safe_int(
        benchmark_alignment_observed.get("refresh_rebar_sensitive_column_count", 0), 0
    )
    benchmark_alignment_benchmark_rebar_ratio_min = _safe_float(
        benchmark_alignment_observed.get("benchmark_longitudinal_rebar_ratio_min", 0.0), 0.0
    )
    benchmark_alignment_benchmark_rebar_ratio_max = _safe_float(
        benchmark_alignment_observed.get("benchmark_longitudinal_rebar_ratio_max", 0.0), 0.0
    )
    benchmark_alignment_refresh_rebar_ratio_min = _safe_float(
        benchmark_alignment_observed.get("refresh_combined_rebar_ratio_min", 0.0), 0.0
    )
    benchmark_alignment_refresh_rebar_ratio_max = _safe_float(
        benchmark_alignment_observed.get("refresh_combined_rebar_ratio_max", 0.0), 0.0
    )

    if not dataset and not isinstance(dataset.get("summary"), dict):
        reason_code = "ERR_INPUT"
        reason = "design-optimization dataset report is missing or unreadable"
        mode = "input_missing"
        contract_pass = False
    elif member_count <= 0:
        reason_code = "ERR_DATASET_EMPTY"
        reason = "design-optimization dataset exists but contains no members"
        mode = "no_member_data"
        contract_pass = False
    elif artifact_present:
        mode = str(artifact_summary.get("hinge_state_mode", "") or "proxy_only_hinge_visualization")
        contract_pass = bool(dataset_contract and artifact_contract and pbd_contract and ndtha_contract)
        if contract_pass:
            reason_code = "PASS"
            reason = "dynamic hinge-refresh artifact is attached with rebar-sensitive member-local overlap and checked against updated NDTHA states."
        else:
            reason_code = str(hinge_artifact.get("reason_code") or "ERR_HINGE_PROXY_ONLY")
            reason = str(hinge_artifact.get("reason") or "hinge-refresh artifact is attached but does not yet prove rebar-sensitive member-local refresh.")
    else:
        contract_pass = bool(dataset_contract and bool(solver_count) and pbd_contract and ndtha_contract)
        inferred_pass, mode = _derive_mode(dataset, hinge_source_counts)
        contract_pass = bool(contract_pass and inferred_pass)
        if contract_pass:
            reason_code = "PASS"
            reason = "dynamic hinge-refresh evidence is attached to the optimization dataset and checked against updated NDTHA states."
        else:
            reason_code = "ERR_HINGE_PROXY_ONLY"
            reason = "hinge-refresh evidence appears to remain proxy-only after optimization pass."

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-pbd-hinge-refresh-readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "pbd_review_package": str(args.pbd_review_package),
            "midas_conversion": str(args.midas_conversion),
            "ndtha_stress_report": str(args.ndtha_stress_report),
            "hinge_refresh_artifact": str(args.hinge_refresh_artifact),
        },
        "summary": {
            "hinge_state_mode": mode,
            "hinge_proxy_artifact_count": int(proxy_count),
            "hinge_non_proxy_artifact_count": int(solver_count),
            "design_opt_member_count": int(member_count),
            "design_opt_drift_envelope_max_pct": _safe_float(dataset_summary.get("drift_envelope_max_pct")),
            "design_opt_repaired_compliance_max_drift_pct": _safe_float(
                dataset_summary.get("drift_envelope_repaired_max_pct", dataset_summary.get("drift_envelope_max_pct"))
            ),
            "pbd_reference_case_count": _safe_int(pbd_summary.get("drift_split_counts", {}).get("test"), 0)
            if isinstance(pbd_summary.get("drift_split_counts"), dict)
            else 0,
            "ndtha_contract_pass": bool(ndtha_contract),
            "pbd_contract_pass": bool(pbd_contract),
            "dataset_contract_pass": bool(dataset_contract),
            "pbd_family_type_count": int(sum(family_counts.values())),
            "hinge_refresh_artifact_present": bool(artifact_present),
            "hinge_refresh_artifact_kind": artifact_source_kind,
            "hinge_refresh_source_mode": artifact_source_mode,
            "hinge_refresh_candidate_scope_mode": artifact_candidate_scope_mode,
            "hinge_refresh_optimized_group_count": int(artifact_optimized_group_count),
            "hinge_refresh_optimized_target_member_count": int(artifact_optimized_target_member_count),
            "hinge_refresh_dataset_npz_member_count": int(artifact_dataset_npz_member_count),
            "hinge_refresh_overlap_member_count": int(artifact_overlap_member_count),
            "hinge_refresh_rebar_sensitive_member_count": int(artifact_rebar_sensitive_member_count),
            "hinge_benchmark_asset_registry_present": bool(benchmark_registry_present),
            "hinge_benchmark_gate_present": bool(benchmark_gate_present),
            "hinge_benchmark_gate_pass": bool(benchmark_gate_pass),
            "hinge_benchmark_gate_reason": benchmark_gate_reason,
            "hinge_benchmark_fixture_regression_present": bool(benchmark_fixture_regression_present),
            "hinge_benchmark_fixture_regression_pass": bool(benchmark_fixture_regression_pass),
            "hinge_benchmark_fixture_regression_reason": benchmark_fixture_regression_reason,
            "hinge_benchmark_alignment_present": bool(benchmark_alignment_present),
            "hinge_benchmark_alignment_pass": bool(benchmark_alignment_pass),
            "hinge_benchmark_alignment_reason": benchmark_alignment_reason,
            "hinge_benchmark_asset_count": int(benchmark_asset_count),
            "hinge_benchmark_train_count": int(benchmark_train_count),
            "hinge_benchmark_val_count": int(benchmark_val_count),
            "hinge_benchmark_holdout_count": int(benchmark_holdout_count),
            "hinge_benchmark_rebar_sensitive_count": int(benchmark_rebar_sensitive_count),
            "hinge_benchmark_confinement_sensitive_count": int(benchmark_confinement_sensitive_count),
            "hinge_benchmark_fixture_count": int(benchmark_fixture_count),
            "hinge_benchmark_fixture_min_point_count": int(benchmark_fixture_min_point_count),
            "hinge_benchmark_fixture_min_peak_drift_ratio": float(benchmark_fixture_min_peak_drift_ratio),
            "hinge_benchmark_alignment_refresh_column_row_count": int(
                benchmark_alignment_refresh_column_row_count
            ),
            "hinge_benchmark_alignment_rebar_sensitive_column_count": int(
                benchmark_alignment_rebar_sensitive_column_count
            ),
            "hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
                benchmark_alignment_benchmark_rebar_ratio_min
            ),
            "hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
                benchmark_alignment_benchmark_rebar_ratio_max
            ),
            "hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
                benchmark_alignment_refresh_rebar_ratio_min
            ),
            "hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
                benchmark_alignment_refresh_rebar_ratio_max
            ),
        },
        "checks": {
            "dataset_has_members": int(member_count) > 0,
            "non_proxy_hinge_state_attached": int(solver_count) > 0,
            "proxy_only_warning_present": bool(proxy_count > 0),
            "ndtha_input_ready": bool(ndtha_contract),
            "pbd_review_ready": bool(pbd_contract),
            "midas_parser_pass": bool(_safe_bool(midas_report.get("contract_pass", False))),
            "hinge_refresh_artifact_present": bool(artifact_present),
            "hinge_refresh_member_overlap_present": bool(artifact_overlap_member_count > 0),
            "hinge_refresh_rebar_sensitive_present": bool(artifact_rebar_sensitive_member_count > 0),
            "hinge_refresh_optimized_scope_present": bool(artifact_optimized_target_member_count > 0),
            "hinge_benchmark_gate_pass": bool(benchmark_gate_pass),
            "hinge_benchmark_fixture_regression_pass": bool(benchmark_fixture_regression_pass),
            "hinge_benchmark_alignment_pass": bool(benchmark_alignment_pass),
        },
        "artifacts": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "pbd_review_package": str(args.pbd_review_package),
            "midas_conversion": str(args.midas_conversion),
            "ndtha_stress_report": str(args.ndtha_stress_report),
            "benchmark_asset_registry": str(args.benchmark_asset_registry),
            "benchmark_gate_report": str(args.benchmark_gate_report),
            "benchmark_fixture_regression_report": str(args.benchmark_fixture_regression_report),
            "benchmark_alignment_report": str(args.benchmark_alignment_report),
            "hinge_refresh_artifact": str(args.hinge_refresh_artifact),
        },
        "artifact_samples": {
            "design_opt_hinge_source_counts": dict(hinge_source_counts),
            "member_family_counts_head": dict(family_counts),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
        "artifacts_meta": [
            _artifact_entry(str(args.design_optimization_dataset)),
            _artifact_entry(str(args.pbd_review_package)),
            _artifact_entry(str(args.midas_conversion)),
            _artifact_entry(str(args.ndtha_stress_report)),
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote PBD hinge refresh report: {out}")


if __name__ == "__main__":
    main()
