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


def run_measured_benchmark_breadth_gate(
    commercial_readiness: dict[str, Any],
    opensees_canonical_breadth: dict[str, Any],
    authority_report: dict[str, Any],
    external_benchmark_status: dict[str, Any],
    canton_conversion_report: dict[str, Any] | None = None,
    canton_reduced_order_compare: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_families, baseline_cases, baseline_rows = _commercial_measured_baseline(commercial_readiness)
    opensees_families, opensees_cases, parser_ready_cases, opensees_rows = _opensees_delta(opensees_canonical_breadth)
    authority_families, authority_cases, authority_rows = _authority_delta(authority_report)
    external_families, external_cases, external_rows = _external_fullcase_delta(external_benchmark_status)
    canton_families, canton_cases, canton_observed_channels, canton_rows = _canton_tower_delta(
        canton_conversion_report or {},
        canton_reduced_order_compare or {},
    )

    combined_families = set(baseline_families)
    combined_families.update(opensees_families)
    combined_families.update(authority_families)
    combined_families.update(external_families)
    combined_families.update(canton_families)
    combined_case_count = int(baseline_cases + opensees_cases + authority_cases + external_cases + canton_cases)

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
        "opensees_parser_ready_case_count": int(parser_ready_cases),
        "measured_family_count": len(combined_families),
        "measured_case_count": int(combined_case_count),
    }
    summary_line = (
        f"Measured benchmark breadth: {'PASS' if contract_pass else 'CHECK'} | "
        f"baseline={len(baseline_families)}/{int(baseline_cases)} | "
        f"opensees_delta={len(opensees_families)}/{int(opensees_cases)} | "
        f"authority_delta={len(authority_families)}/{int(authority_cases)} | "
        f"external_delta={len(external_families)}/{int(external_cases)} | "
        f"canton_delta={len(canton_families)}/{int(canton_cases)} | "
        f"measured_families={len(combined_families)} | "
        f"measured_cases={int(combined_case_count)} | "
        f"parser_ready={int(parser_ready_cases)}"
    )
    return {
        "schema_version": "1.0",
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
        "--out",
        default="implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json",
    )
    args = parser.parse_args(argv)

    payload = run_measured_benchmark_breadth_gate(
        _load_json(Path(args.commercial_readiness)),
        _load_json(Path(args.opensees_canonical_breadth)),
        _load_json(Path(args.authority_report)),
        _load_json(Path(args.external_benchmark_status)),
        _load_json(Path(args.canton_conversion_report)),
        _load_json(Path(args.canton_reduced_order_compare)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote measured benchmark breadth gate report: {out}")
    return 0 if payload.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
