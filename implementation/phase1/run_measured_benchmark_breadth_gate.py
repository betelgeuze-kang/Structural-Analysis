#!/usr/bin/env python3
"""Aggregate measured benchmark breadth from commercial baseline plus committed OpenSees breadth."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _commercial_measured_baseline(payload: dict[str, Any]) -> tuple[set[str], int, list[dict[str, Any]]]:
    rows = payload.get("model_rows") if isinstance(payload.get("model_rows"), list) else []
    measured_families: set[str] = set()
    measured_case_count = 0
    baseline_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source_provenance") if isinstance(row.get("source_provenance"), dict) else {}
        model_id = str(row.get("model_id", "") or "").strip()
        source_families = [
            str(token).strip()
            for token in (source.get("measured_source_families") or [])
            if str(token).strip()
        ]
        case_count = int(source.get("measured_case_count", 0) or 0)
        measured_case_count += case_count
        measured_families.update(source_families)
        baseline_rows.append(
            {
                "model_id": model_id,
                "measured_source_families": source_families,
                "measured_case_count": case_count,
            }
        )
    return measured_families, measured_case_count, baseline_rows


def _opensees_delta(payload: dict[str, Any]) -> tuple[set[str], int, int, list[dict[str, Any]]]:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    families = {
        f"opensees:{str(row.get('family_id', '')).strip()}"
        for row in rows
        if isinstance(row, dict) and str(row.get("family_id", "")).strip()
    }
    case_count = len([row for row in rows if isinstance(row, dict)])
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    parser_ready = int(summary.get("standalone_parser_ready_case_count", 0) or 0)
    return families, case_count, parser_ready, [row for row in rows if isinstance(row, dict)]


def _authority_delta(payload: dict[str, Any]) -> tuple[set[str], int, list[dict[str, Any]]]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    families: set[str] = set()
    case_count = 0
    rows: list[dict[str, Any]] = []
    if int(summary.get("sac_case_count", 0) or 0) > 0:
        families.add("authority:sac")
        case_count += int(summary.get("sac_case_count", 0) or 0)
        rows.append({"track": "sac", "case_count": int(summary.get("sac_case_count", 0) or 0)})
    if int(summary.get("nheri_case_count", 0) or 0) > 0:
        families.add("authority:nheri")
        case_count += int(summary.get("nheri_case_count", 0) or 0)
        rows.append({"track": "nheri", "case_count": int(summary.get("nheri_case_count", 0) or 0)})
    return families, case_count, rows


def _external_fullcase_delta(payload: dict[str, Any]) -> tuple[set[str], int, list[dict[str, Any]]]:
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    eligible_rows = [
        row
        for row in tasks
        if isinstance(row, dict)
        and str(row.get("source_origin_class", "") or "").strip() == "official_external_benchmark_fullcase"
        and str(row.get("execution_status", "") or "").strip().lower() in {"ready", "completed"}
    ]
    families = {
        f"external:{str(row.get('benchmark_family', '')).strip()}"
        for row in eligible_rows
        if str(row.get("benchmark_family", "")).strip()
    }
    return families, len(eligible_rows), eligible_rows


def _canton_tower_delta(
    conversion_report: dict[str, Any],
    reduced_order_compare: dict[str, Any],
) -> tuple[set[str], int, int, list[dict[str, Any]]]:
    summary = reduced_order_compare.get("summary") if isinstance(reduced_order_compare.get("summary"), dict) else {}
    conversion_outputs = (
        conversion_report.get("outputs") if isinstance(conversion_report.get("outputs"), dict) else {}
    )
    benchmark_case_count = int(
        summary.get("benchmark_case_count", 0) or conversion_outputs.get("benchmark_case_count", 0) or 0
    )
    if benchmark_case_count <= 0:
        return set(), 0, 0, []
    observed_channel_count = int(summary.get("observed_channel_count", 0) or 0)
    rows = [
        {
            "track": "canton_tower_reduced_shm",
            "case_count": benchmark_case_count,
            "observed_channel_count": observed_channel_count,
            "summary_line": str(reduced_order_compare.get("summary_line", "") or ""),
        }
    ]
    return {"measured:canton_tower_reduced_shm"}, benchmark_case_count, observed_channel_count, rows


def _peer_blind_prediction_delta(
    cases_payload: dict[str, Any],
    compare_report: dict[str, Any],
) -> tuple[set[str], int, int, bool, list[dict[str, Any]]]:
    cases = cases_payload.get("cases") if isinstance(cases_payload.get("cases"), list) else []
    compare_summary = compare_report.get("summary") if isinstance(compare_report.get("summary"), dict) else {}
    measured_response_ready = bool(compare_summary.get("measured_response_ready", False))
    compare_contract_ready = bool(compare_report.get("contract_pass", False) and measured_response_ready)
    eligible_rows: list[dict[str, Any]] = []
    for row in cases:
        if not isinstance(row, dict):
            continue
        targets = row.get("blind_prediction_targets") if isinstance(row.get("blind_prediction_targets"), dict) else {}
        source_family = str(row.get("source_family", "") or "").strip()
        if (
            source_family
            and str(row.get("benchmark_case_status", "") or "").strip().lower() == "ready"
            and bool(row.get("compare_ready", False))
            and bool(targets.get("measured_response_present", False))
        ):
            eligible_rows.append(row)
    case_count = len(eligible_rows) if compare_contract_ready else 0
    families = {
        f"peer_blind_prediction:{str(row.get('source_family', '')).strip()}"
        for row in eligible_rows
        if str(row.get("source_family", "")).strip()
    }
    return families, case_count, len(eligible_rows), compare_contract_ready, eligible_rows


def _allocate_case_counts(total_case_count: int, family_ids: list[str]) -> dict[str, int]:
    if not family_ids:
        return {}
    total = max(int(total_case_count), 0)
    base_count = total // len(family_ids)
    remainder = total % len(family_ids)
    return {
        family_id: base_count + (1 if idx < remainder else 0)
        for idx, family_id in enumerate(family_ids)
    }


def _add_family_coverage(
    families: dict[str, dict[str, Any]],
    *,
    family_id: str,
    source_bucket: str,
    measured_case_count: int,
    evidence_ref: dict[str, Any],
) -> None:
    family = str(family_id or "").strip()
    if not family:
        return
    row = families.setdefault(
        family,
        {
            "family_id": family,
            "measured_case_count": 0,
            "source_buckets": [],
            "evidence_refs": [],
        },
    )
    row["measured_case_count"] = int(row.get("measured_case_count", 0) or 0) + max(
        int(measured_case_count or 0),
        0,
    )
    bucket = str(source_bucket or "").strip()
    if bucket and bucket not in row["source_buckets"]:
        row["source_buckets"].append(bucket)
    row["evidence_refs"].append(evidence_ref)


def _family_coverage_rows(
    *,
    baseline_rows: list[dict[str, Any]],
    opensees_rows: list[dict[str, Any]],
    authority_rows: list[dict[str, Any]],
    external_rows: list[dict[str, Any]],
    canton_rows: list[dict[str, Any]],
    peer_blind_prediction_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for row in baseline_rows:
        source_families = [
            str(token).strip()
            for token in row.get("measured_source_families", [])
            if str(token).strip()
        ]
        allocated_counts = _allocate_case_counts(
            int(row.get("measured_case_count", 0) or 0),
            source_families,
        )
        for family_id in source_families:
            _add_family_coverage(
                families,
                family_id=family_id,
                source_bucket="commercial_baseline",
                measured_case_count=allocated_counts.get(family_id, 0),
                evidence_ref={
                    "model_id": str(row.get("model_id", "") or ""),
                    "allocated_from_model_case_count": int(row.get("measured_case_count", 0) or 0),
                },
            )

    for row in opensees_rows:
        family_id = str(row.get("family_id", "") or "").strip()
        if not family_id:
            continue
        _add_family_coverage(
            families,
            family_id=f"opensees:{family_id}",
            source_bucket="opensees_canonical",
            measured_case_count=1,
            evidence_ref={
                "case_id": str(row.get("case_id", "") or ""),
                "path": str(row.get("path", "") or ""),
                "parser_contract_ready": bool(row.get("parser_contract_ready", False)),
            },
        )

    for row in authority_rows:
        track = str(row.get("track", "") or "").strip()
        if not track:
            continue
        _add_family_coverage(
            families,
            family_id=f"authority:{track}",
            source_bucket="global_authority",
            measured_case_count=int(row.get("case_count", 0) or 0),
            evidence_ref={"track": track},
        )

    for row in external_rows:
        benchmark_family = str(row.get("benchmark_family", "") or "").strip()
        if not benchmark_family:
            continue
        _add_family_coverage(
            families,
            family_id=f"external:{benchmark_family}",
            source_bucket="official_external_benchmark_fullcase",
            measured_case_count=1,
            evidence_ref={
                "case_id": str(row.get("case_id", "") or ""),
                "execution_status": str(row.get("execution_status", "") or ""),
                "artifact_path": str(row.get("artifact_path", "") or ""),
            },
        )

    for row in canton_rows:
        _add_family_coverage(
            families,
            family_id="measured:canton_tower_reduced_shm",
            source_bucket="open_data_reduced_order_shm",
            measured_case_count=int(row.get("case_count", 0) or 0),
            evidence_ref={
                "track": str(row.get("track", "") or ""),
                "observed_channel_count": int(row.get("observed_channel_count", 0) or 0),
            },
        )

    for row in peer_blind_prediction_rows:
        source_family = str(row.get("source_family", "") or "").strip()
        case_id = str(row.get("case_id", "") or "").strip()
        if not source_family or not case_id:
            continue
        metrics = row.get("blind_prediction_metrics") if isinstance(row.get("blind_prediction_metrics"), dict) else {}
        _add_family_coverage(
            families,
            family_id=f"peer_blind_prediction:{source_family}",
            source_bucket="peer_blind_prediction_measured_response",
            measured_case_count=1,
            evidence_ref={
                "case_id": case_id,
                "source_member": str(row.get("source_member", "") or ""),
                "measured_channel_count": int(metrics.get("measured_channel_count", 0) or 0),
                "drift_channel_count": int(metrics.get("drift_channel_count", 0) or 0),
            },
        )

    rows = []
    for family_id, row in families.items():
        source_buckets = sorted(str(bucket) for bucket in row.get("source_buckets", []))
        measured_case_count = int(row.get("measured_case_count", 0) or 0)
        rows.append(
            {
                "family_id": family_id,
                "measured_case_count": measured_case_count,
                "source_buckets": source_buckets,
                "source_bucket_count": len(source_buckets),
                "holdout_candidate_count": 1 if measured_case_count > 0 else 0,
                "evidence_refs": row.get("evidence_refs", []),
            }
        )
    return sorted(rows, key=lambda item: str(item.get("family_id", "")))


def _holdout_rows(family_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in family_rows:
        family_id = str(row.get("family_id", "") or "").strip()
        measured_case_count = int(row.get("measured_case_count", 0) or 0)
        if not family_id or measured_case_count <= 0:
            continue
        rows.append(
            {
                "family_id": family_id,
                "holdout_id": f"{family_id}::holdout_001",
                "holdout_case_count": 1,
                "family_measured_case_count": measured_case_count,
                "selection_policy": "deterministic_family_holdout_v1",
                "selection_basis": "stable family_id sort with one retained coverage holdout candidate per measured family",
                "source_buckets": list(row.get("source_buckets", [])),
            }
        )
    return rows


def _coverage_risk_score(row: dict[str, Any], *, has_holdout: bool) -> tuple[float, list[str]]:
    case_count = int(row.get("measured_case_count", 0) or 0)
    source_bucket_count = int(row.get("source_bucket_count", 0) or 0)
    reason_codes: list[str] = []
    if case_count <= 0:
        score = 1.0
        reason_codes.append("ERR_NO_MEASURED_CASES")
    elif case_count == 1:
        score = 0.85
        reason_codes.append("LOW_CASE_COUNT_SINGLETON")
    elif case_count < 5:
        score = 0.65
        reason_codes.append("LOW_CASE_COUNT_LT5")
    elif case_count < 10:
        score = 0.45
        reason_codes.append("MODERATE_CASE_COUNT_LT10")
    else:
        score = 0.25

    if not has_holdout:
        score += 0.2
        reason_codes.append("NO_HOLDOUT_SELECTOR")
    if source_bucket_count <= 1:
        score += 0.1
        reason_codes.append("SINGLE_SOURCE_BUCKET")
    if not reason_codes:
        reason_codes.append("LOWEST_COVERAGE_RISK_BUCKET")
    return min(score, 1.0), reason_codes


def build_benchmark_worst_case_report(measured_payload: dict[str, Any]) -> dict[str, Any]:
    summary = measured_payload.get("summary") if isinstance(measured_payload.get("summary"), dict) else {}
    family_rows = (
        measured_payload.get("family_coverage_rows")
        if isinstance(measured_payload.get("family_coverage_rows"), list)
        else []
    )
    holdout_rows = (
        measured_payload.get("holdout_rows")
        if isinstance(measured_payload.get("holdout_rows"), list)
        else []
    )
    holdout_families = {
        str(row.get("family_id", "") or "").strip()
        for row in holdout_rows
        if isinstance(row, dict) and str(row.get("family_id", "") or "").strip()
    }
    ranked_rows = []
    for row in family_rows:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        score, reason_codes = _coverage_risk_score(row, has_holdout=family_id in holdout_families)
        ranked_rows.append(
            {
                "family_id": family_id,
                "measured_case_count": int(row.get("measured_case_count", 0) or 0),
                "holdout_candidate_count": 1 if family_id in holdout_families else 0,
                "source_buckets": list(row.get("source_buckets", [])),
                "coverage_risk_score": round(score, 4),
                "reason_codes": reason_codes,
            }
        )
    ranked_rows.sort(
        key=lambda row: (
            -float(row.get("coverage_risk_score", 0.0) or 0.0),
            int(row.get("measured_case_count", 0) or 0),
            str(row.get("family_id", "")),
        )
    )
    for idx, row in enumerate(ranked_rows, start=1):
        row["rank"] = idx

    source_contract_pass = bool(measured_payload.get("contract_pass", False))
    checks = {
        "source_measured_benchmark_breadth_contract_pass": source_contract_pass,
        "family_coverage_rows_present": bool(family_rows),
        "holdout_manifest_present": bool(holdout_rows),
        "coverage_worst_case_rows_present": bool(ranked_rows),
        "no_accuracy_claim": True,
    }
    contract_pass = all(checks.values())
    return {
        "schema_version": "benchmark-worst-case-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_WORST_CASE_COVERAGE_REPORT_INCOMPLETE",
        "metric_basis": "coverage_risk_no_accuracy_claim",
        "accuracy_claimed": False,
        "checks": checks,
        "summary": {
            "source_measured_case_count": int(summary.get("measured_case_count", 0) or 0),
            "source_measured_family_count": int(summary.get("measured_family_count", 0) or 0),
            "holdout_family_count": len(holdout_families),
            "worst_case_family_count": len(ranked_rows),
            "highest_coverage_risk_family_id": str(ranked_rows[0].get("family_id", "")) if ranked_rows else "",
            "highest_coverage_risk_score": float(ranked_rows[0].get("coverage_risk_score", 0.0)) if ranked_rows else 0.0,
        },
        "summary_line": (
            "Benchmark worst-case coverage: "
            f"{'PASS' if contract_pass else 'CHECK'} | "
            f"basis=coverage_risk_no_accuracy_claim | "
            f"families={len(ranked_rows)} | "
            f"holdout_families={len(holdout_families)}"
        ),
        "rows": ranked_rows,
    }


def run_measured_benchmark_breadth_gate(
    commercial_readiness: dict[str, Any],
    opensees_canonical_breadth: dict[str, Any],
    authority_report: dict[str, Any],
    external_benchmark_status: dict[str, Any],
    canton_conversion_report: dict[str, Any] | None = None,
    canton_reduced_order_compare: dict[str, Any] | None = None,
    peer_blind_prediction_cases: dict[str, Any] | None = None,
    peer_blind_prediction_compare: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_families, baseline_cases, baseline_rows = _commercial_measured_baseline(commercial_readiness)
    opensees_families, opensees_cases, parser_ready_cases, opensees_rows = _opensees_delta(opensees_canonical_breadth)
    authority_families, authority_cases, authority_rows = _authority_delta(authority_report)
    external_families, external_cases, external_rows = _external_fullcase_delta(external_benchmark_status)
    canton_families, canton_cases, canton_observed_channels, canton_rows = _canton_tower_delta(
        canton_conversion_report or {},
        canton_reduced_order_compare or {},
    )
    (
        peer_blind_prediction_families,
        peer_blind_prediction_cases_count,
        peer_blind_prediction_ready_case_count,
        peer_blind_prediction_compare_ready,
        peer_blind_prediction_rows,
    ) = _peer_blind_prediction_delta(
        peer_blind_prediction_cases or {},
        peer_blind_prediction_compare or {},
    )

    combined_families = set(baseline_families)
    combined_families.update(opensees_families)
    combined_families.update(authority_families)
    combined_families.update(external_families)
    combined_families.update(canton_families)
    combined_families.update(peer_blind_prediction_families)
    combined_case_count = int(
        baseline_cases
        + opensees_cases
        + authority_cases
        + external_cases
        + canton_cases
        + peer_blind_prediction_cases_count
    )
    family_rows = _family_coverage_rows(
        baseline_rows=baseline_rows,
        opensees_rows=opensees_rows,
        authority_rows=authority_rows,
        external_rows=external_rows,
        canton_rows=canton_rows,
        peer_blind_prediction_rows=peer_blind_prediction_rows,
    )
    holdout_rows = _holdout_rows(family_rows)

    contract_pass = len(combined_families) >= 10 and combined_case_count >= 70 and parser_ready_cases >= 3
    reason_code = "PASS" if contract_pass else "ERR_MEASURED_BREADTH_LOW"

    summary = {
        "baseline_measured_family_count": len(baseline_families),
        "baseline_measured_case_count": int(baseline_cases),
        "opensees_incremental_family_count": len(opensees_families),
        "opensees_incremental_case_count": int(opensees_cases),
        "authority_incremental_family_count": len(authority_families),
        "authority_incremental_case_count": int(authority_cases),
        "external_incremental_family_count": len(external_families),
        "external_incremental_case_count": int(external_cases),
        "canton_incremental_family_count": len(canton_families),
        "canton_incremental_case_count": int(canton_cases),
        "canton_observed_channel_count": int(canton_observed_channels),
        "peer_blind_prediction_incremental_family_count": len(peer_blind_prediction_families),
        "peer_blind_prediction_incremental_case_count": int(peer_blind_prediction_cases_count),
        "peer_blind_prediction_ready_case_count": int(peer_blind_prediction_ready_case_count),
        "peer_blind_prediction_compare_ready": bool(peer_blind_prediction_compare_ready),
        "opensees_parser_ready_case_count": int(parser_ready_cases),
        "measured_family_count": len(combined_families),
        "measured_case_count": int(combined_case_count),
        "family_coverage_row_count": len(family_rows),
        "holdout_family_count": len({str(row.get("family_id", "") or "") for row in holdout_rows}),
        "holdout_case_count": sum(int(row.get("holdout_case_count", 0) or 0) for row in holdout_rows),
        "holdout_policy": "deterministic_family_holdout_v1",
    }
    summary_line = (
        f"Measured benchmark breadth: {'PASS' if contract_pass else 'CHECK'} | "
        f"baseline={len(baseline_families)}/{int(baseline_cases)} | "
        f"opensees_delta={len(opensees_families)}/{int(opensees_cases)} | "
        f"authority_delta={len(authority_families)}/{int(authority_cases)} | "
        f"external_delta={len(external_families)}/{int(external_cases)} | "
        f"canton_delta={len(canton_families)}/{int(canton_cases)} | "
        f"peer_blind_delta={len(peer_blind_prediction_families)}/{int(peer_blind_prediction_cases_count)} | "
        f"measured_families={len(combined_families)} | "
        f"measured_cases={int(combined_case_count)} | "
        f"holdout_families={summary['holdout_family_count']} | "
        f"parser_ready={int(parser_ready_cases)}"
    )
    return {
        "schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": (
            "measured benchmark breadth now includes committed OpenSees canonical breadth on top of the commercial baseline"
            if contract_pass
            else "measured benchmark breadth is still below the surfacing floor"
        ),
        "summary": summary,
        "summary_line": summary_line,
        "baseline_rows": baseline_rows,
        "opensees_rows": opensees_rows,
        "authority_rows": authority_rows,
        "external_rows": external_rows,
        "canton_rows": canton_rows,
        "peer_blind_prediction_rows": peer_blind_prediction_rows,
        "family_coverage_rows": family_rows,
        "holdout_rows": holdout_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commercial-readiness",
        default="implementation/phase1/commercial_readiness_report.json",
    )
    parser.add_argument(
        "--opensees-canonical-breadth",
        default="implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
    )
    parser.add_argument(
        "--authority-report",
        default="implementation/phase1/global_authority_gate_report.json",
    )
    parser.add_argument(
        "--external-benchmark-status",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json",
    )
    parser.add_argument(
        "--canton-conversion-report",
        default="implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json",
    )
    parser.add_argument(
        "--canton-reduced-order-compare",
        default="implementation/phase1/release/benchmark_expansion/canton_tower_reduced_order_compare_report.json",
    )
    parser.add_argument(
        "--peer-blind-prediction-cases",
        default="implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json",
    )
    parser.add_argument(
        "--peer-blind-prediction-compare",
        default="implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/release_evidence/productization/measured_benchmark_breadth_report.json",
    )
    parser.add_argument("--worst-case-out", default=None)
    args = parser.parse_args(argv)

    payload = run_measured_benchmark_breadth_gate(
        _load_json(Path(args.commercial_readiness)),
        _load_json(Path(args.opensees_canonical_breadth)),
        _load_json(Path(args.authority_report)),
        _load_json(Path(args.external_benchmark_status)),
        _load_json(Path(args.canton_conversion_report)),
        _load_json(Path(args.canton_reduced_order_compare)),
        _load_json(Path(args.peer_blind_prediction_cases)),
        _load_json(Path(args.peer_blind_prediction_compare)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote measured benchmark breadth gate report: {out}")
    worst_case_out = Path(args.worst_case_out) if args.worst_case_out else out.parent / "worst_case_report.json"
    worst_case_payload = build_benchmark_worst_case_report(payload)
    worst_case_out.parent.mkdir(parents=True, exist_ok=True)
    worst_case_out.write_text(json.dumps(worst_case_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote benchmark worst-case coverage report: {worst_case_out}")
    return 0 if payload.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
