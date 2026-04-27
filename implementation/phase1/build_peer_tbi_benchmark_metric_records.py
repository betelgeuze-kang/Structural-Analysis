#!/usr/bin/env python3
"""Build deterministic P1 PEER TBI benchmark metric records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PEER_TBI_SOURCE_ID = "peer_tbi_tall_buildings"
REQUIRED_METRIC_GROUPS = ["period", "base_shear", "story_drift", "nonlinear_response", "citation"]
RUN_ID = "phase1-peer-tbi-benchmark-metric-records"
SCHEMA_VERSION = "peer_tbi_benchmark_metric_records.v1"
REPORT_ID = "peer_tbi_tall_buildings_citation_seed"
DEFAULT_CITATION = (
    "Pacific Earthquake Engineering Research Center (PEER), Tall Buildings Initiative, "
    "public research and benchmark materials."
)
METRIC_NAMES = {
    "period": "fundamental_period",
    "base_shear": "base_shear",
    "story_drift": "story_drift",
    "nonlinear_response": "nonlinear_response",
    "citation": "benchmark_citation",
}
METRIC_UNITS = {
    "period": "s",
    "base_shear": "kN",
    "story_drift": "ratio",
    "nonlinear_response": "",
    "citation": "",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_family(manifest: dict[str, Any]) -> dict[str, Any] | None:
    for source in manifest.get("source_families", []):
        if isinstance(source, dict) and source.get("source_id") == PEER_TBI_SOURCE_ID:
            return source
    return None


def _peer_gate(coverage_matrix: dict[str, Any]) -> dict[str, Any] | None:
    for row in coverage_matrix.get("p1_gate_rows", []):
        if isinstance(row, dict) and row.get("gate_id") == "P1_PEER_TBI_BENCHMARK_METRICS":
            return row
    return None


def _coverage_targets(coverage_matrix: dict[str, Any], gate: dict[str, Any] | None) -> list[str]:
    if gate is not None:
        return [str(target) for target in gate.get("required_targets", []) if isinstance(target, str)]

    for row in coverage_matrix.get("source_rows", []):
        if isinstance(row, dict) and row.get("source_id") == PEER_TBI_SOURCE_ID:
            targets = row.get("benchmark_metric_targets", [])
            return [
                str(target.get("metric"))
                for target in targets
                if isinstance(target, dict) and isinstance(target.get("metric"), str)
            ]
    return []


def _access_policy(source: dict[str, Any] | None) -> dict[str, Any]:
    if not source:
        return {}
    access_policy = source.get("access_policy")
    return access_policy if isinstance(access_policy, dict) else {}


def _locator(metric_group: str) -> dict[str, str]:
    return {
        "page": "p. n/a",
        "table": "",
        "figure": "",
        "note": f"citation_seed:{metric_group}",
    }


def _metric_record(source: dict[str, Any], metric_group: str) -> dict[str, Any]:
    official_url = str(source.get("official_entrypoint_url", "") or "")
    citation = DEFAULT_CITATION
    status = "recorded" if metric_group == "citation" else "not_available"
    value: str | None = citation if metric_group == "citation" else None

    return {
        "source_id": PEER_TBI_SOURCE_ID,
        "official_url": official_url,
        "citation": citation,
        "report_id": REPORT_ID,
        "metric_group": metric_group,
        "metric_name": METRIC_NAMES[metric_group],
        "value": value,
        "status": status,
        "unit": METRIC_UNITS[metric_group],
        "locator": _locator(metric_group),
        "benchmark_status": "citation_metric_recorded",
        "redistribution_allowed": False,
        "raw_model_redistribution_review_required": True,
    }


def _reason_code(
    peer_source_exists: bool,
    peer_gate_exists: bool,
    required_groups_represented: bool,
    raw_redistribution_default: bool,
) -> str:
    if peer_source_exists and peer_gate_exists and required_groups_represented and not raw_redistribution_default:
        return "PASS"
    if not peer_source_exists:
        return "ERR_PEER_TBI_SOURCE_FAMILY_MISSING"
    if not peer_gate_exists:
        return "ERR_PEER_TBI_BENCHMARK_TARGETS_MISSING"
    if raw_redistribution_default:
        return "ERR_PEER_TBI_RAW_REDISTRIBUTION_NOT_BLOCKED"
    return "ERR_REQUIRED_METRIC_GROUPS_MISSING"


def build_metric_records(manifest: dict[str, Any], coverage_matrix: dict[str, Any]) -> dict[str, Any]:
    source = _source_family(manifest)
    peer_gate = _peer_gate(coverage_matrix)
    coverage_targets = _coverage_targets(coverage_matrix, peer_gate)
    peer_source_exists = source is not None
    peer_gate_exists = set(REQUIRED_METRIC_GROUPS) <= set(coverage_targets)
    access_policy = _access_policy(source)
    raw_redistribution_default = bool(access_policy.get("redistribution_allowed", False))

    metric_records = [_metric_record(source, group) for group in REQUIRED_METRIC_GROUPS] if source else []
    represented_groups = sorted({record["metric_group"] for record in metric_records})
    required_groups_represented = set(REQUIRED_METRIC_GROUPS) <= set(represented_groups)
    contract_pass = (
        peer_source_exists
        and peer_gate_exists
        and required_groups_represented
        and not raw_redistribution_default
    )
    raw_redistribution_auto_allowed = False
    redistribution_allowed_record_count = sum(1 for record in metric_records if record["redistribution_allowed"])

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "source_manifest_schema_version": manifest.get("schema_version"),
        "source_id": PEER_TBI_SOURCE_ID,
        "contract_pass": contract_pass,
        "reason_code": _reason_code(
            peer_source_exists,
            peer_gate_exists,
            required_groups_represented,
            raw_redistribution_default,
        ),
        "raw_redistribution_default": raw_redistribution_default,
        "p0_upstream_hard_gate": True,
        "required_metric_groups": REQUIRED_METRIC_GROUPS,
        "summary": {
            "peer_tbi_source_family_exists": peer_source_exists,
            "coverage_matrix_has_peer_tbi_benchmark_targets": peer_gate_exists,
            "required_metric_groups": sorted(REQUIRED_METRIC_GROUPS),
            "represented_metric_groups": represented_groups,
            "metric_record_count": len(metric_records),
            "required_metric_group_count": len(REQUIRED_METRIC_GROUPS),
            "recorded_metric_group_count": len(represented_groups),
            "redistribution_allowed_record_count": redistribution_allowed_record_count,
            "raw_redistribution_auto_allowed": raw_redistribution_auto_allowed,
        },
        "metric_records": metric_records,
        "p1_gate_rows": [
            {
                "gate_id": "P1_PEER_TBI_BENCHMARK_METRICS",
                "source_id": PEER_TBI_SOURCE_ID,
                "required_metric_groups": REQUIRED_METRIC_GROUPS,
                "coverage_matrix_targets": coverage_targets,
                "represented_metric_groups": represented_groups,
                "contract_pass": peer_gate_exists and required_groups_represented,
            },
            {
                "gate_id": "P1_RAW_REDISTRIBUTION_SAFETY",
                "raw_redistribution_auto_allowed": raw_redistribution_auto_allowed,
                "redistribution_allowed": False,
                "raw_model_redistribution_review_required": True,
                "contract_pass": not raw_redistribution_default and redistribution_allowed_record_count == 0,
            },
        ],
    }


def write_records(manifest_path: Path, coverage_matrix_path: Path, out_path: Path) -> dict[str, Any]:
    payload = build_metric_records(_load_json(manifest_path), _load_json(coverage_matrix_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage-matrix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = write_records(args.manifest, args.coverage_matrix, args.out)
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
