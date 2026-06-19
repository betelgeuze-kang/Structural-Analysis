#!/usr/bin/env python3
"""Build deterministic P1 PEER TBI benchmark metric records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PEER_TBI_SOURCE_ID = "peer_tbi_tall_buildings"
REQUIRED_METRIC_GROUPS = ["period", "base_shear", "story_drift", "nonlinear_response", "citation"]
RUN_ID = "phase1-peer-tbi-benchmark-metric-records"
SCHEMA_VERSION = "peer_tbi_benchmark_metric_records.v1"
REPORT_ID = "peer_tbi_tall_buildings_citation_seed"
DEFAULT_KPI_RECEIPT = Path(
    "implementation/phase1/release/external_benchmark_kickoff/runs/"
    "hardest_peer_tbi_tall_building_ndtha/benchmark_task_kpi_receipt.json"
)
DEFAULT_NDTHA_STRESS_REPORT = Path("implementation/phase1/nonlinear_ndtha_stress_report.json")
PEER_TASK12_REPORT = {
    "document_id": "PEER-2011/05 Task 12",
    "title": "Guidelines for Performance-Based Seismic Design of Tall Buildings - Task 12",
    "official_url": "https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf",
    "sha256": "00afa40a749e960e465b7c1c01cd6508f514effb47214278a56246708d78a909",
}
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
    "base_shear": "kN_trace",
    "story_drift": "ratio_or_pct",
    "nonlinear_response": "mixed",
    "citation": "",
}
REFERENCE_TRUTH_OFFICIAL = "official_public_report_metric"
REFERENCE_TRUTH_BRIDGE = "measured_run_kpi_bridge_not_external_reference_truth"
REFERENCE_TRUTH_CITATION = "citation_only_not_metric_truth"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": "", "exists": False, "sha256": ""}
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": f"sha256:{_sha256(path)}" if path.exists() and path.is_file() else "",
    }


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


def _kpi_value(kpi_receipt: dict[str, Any], label: str) -> Any:
    for row in kpi_receipt.get("kpi_rows", []):
        if isinstance(row, dict) and row.get("label") == label:
            return row.get("value")
    return None


def _kpi_source(kpi_receipt: dict[str, Any], label: str) -> str:
    for row in kpi_receipt.get("kpi_rows", []):
        if isinstance(row, dict) and row.get("label") == label:
            return str(row.get("source", "") or "")
    return ""


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _base_shear_trace(stress_report: dict[str, Any]) -> dict[str, Any]:
    case_count = 0
    sample_count = 0
    max_abs: float | None = None
    max_abs_case_id = ""
    max_abs_index = -1
    for row in stress_report.get("rows", []):
        if not isinstance(row, dict):
            continue
        response = row.get("response")
        if not isinstance(response, dict):
            continue
        series = response.get("base_shear_kN")
        if not isinstance(series, list):
            continue
        case_count += 1
        for idx, raw_value in enumerate(series):
            value = _number(raw_value)
            if value is None:
                continue
            sample_count += 1
            if max_abs is None or abs(value) > abs(max_abs):
                max_abs = value
                max_abs_case_id = str(row.get("case_id", "") or "")
                max_abs_index = idx
    return {
        "series_available": case_count > 0,
        "case_count": case_count,
        "sample_count": sample_count,
        "observed_max_abs_base_shear_kN": max_abs,
        "observed_max_abs_locator": {
            "json_path": f"$.rows[?case_id=='{max_abs_case_id}'].response.base_shear_kN[{max_abs_index}]"
            if max_abs_case_id and max_abs_index >= 0
            else "",
            "case_id": max_abs_case_id,
            "series_index": max_abs_index,
        },
        "quality_boundary": "Trace summary only; not an official PEER acceptance value.",
    }


def _task12_locator(*, page: str, table: str = "", figure: str = "", note: str = "") -> dict[str, str]:
    return {
        "page": page,
        "table": table,
        "figure": figure,
        "note": note,
        "source_document_id": PEER_TASK12_REPORT["document_id"],
        "source_url": PEER_TASK12_REPORT["official_url"],
        "source_sha256": PEER_TASK12_REPORT["sha256"],
    }


def _bridge_locator(path: Path, json_path: str, note: str) -> dict[str, str]:
    return {
        "page": "p. n/a",
        "table": "",
        "figure": "",
        "note": note,
        "source_file": str(path),
        "json_path": json_path,
    }


def _metric_payload(metric_group: str, kpi_receipt: dict[str, Any], stress_report: dict[str, Any]) -> dict[str, Any]:
    if metric_group == "period":
        return {
            "value": 4.456,
            "status": "official_report_value_recorded",
            "locator": _task12_locator(
                page="PDF page 50",
                table="Table 4.1 Period and mass participation summary",
                note="fundamental period T1 for the Building 2A model",
            ),
            "benchmark_status": "official_public_report_metric_recorded",
            "reference_truth_status": REFERENCE_TRUTH_OFFICIAL,
        }
    if metric_group == "base_shear":
        trace = _base_shear_trace(stress_report)
        if not trace["series_available"]:
            return {
                "value": None,
                "status": "not_available",
                "locator": _bridge_locator(
                    DEFAULT_NDTHA_STRESS_REPORT,
                    "$.rows[*].response.base_shear_kN",
                    "local_ndtha_base_shear_series_missing",
                ),
                "benchmark_status": "measured_run_kpi_bridge_missing",
                "reference_truth_status": REFERENCE_TRUTH_BRIDGE,
            }
        return {
            "value": {
                "official_pdf_policy": (
                    "Task 12 records base-shear design-policy decisions for the TBI cases; "
                    "the attached numeric series is the local NDTHA stress-run trace."
                ),
                "measured_run_trace": trace,
            },
            "status": "measured_run_trace_attached",
            "locator": _bridge_locator(
                DEFAULT_NDTHA_STRESS_REPORT,
                "$.rows[*].response.base_shear_kN",
                "local_ndtha_base_shear_series_trace",
            ),
            "benchmark_status": "measured_run_kpi_bridge_attached",
            "reference_truth_status": REFERENCE_TRUTH_BRIDGE,
        }
    if metric_group == "story_drift":
        max_drift = _kpi_value(kpi_receipt, "max_drift_ratio_pct_max")
        return {
            "value": {
                "official_pdf_context": {
                    "building_2a_ove_average_interstory_drift_ratio": {
                        "east_west": ">0.02",
                        "north_south": "~0.015",
                    },
                    "locator": _task12_locator(
                        page="PDF page 64",
                        figure="Figure 4.13",
                        note="Building 2A OVE interstory drift context",
                    ),
                },
                "measured_run_max_drift_ratio_pct_max": max_drift,
            },
            "status": "official_context_plus_measured_run_kpi_recorded",
            "locator": _bridge_locator(
                DEFAULT_KPI_RECEIPT,
                "$.kpi_rows[?label=='max_drift_ratio_pct_max']",
                _kpi_source(kpi_receipt, "max_drift_ratio_pct_max") or "primary.summary.max_drift_ratio_pct_max",
            ),
            "benchmark_status": "measured_run_kpi_bridge_attached",
            "reference_truth_status": REFERENCE_TRUTH_BRIDGE,
        }
    if metric_group == "nonlinear_response":
        labels = [
            "case_count",
            "max_drift_ratio_pct_max",
            "peak_plastic_story_count_mean",
            "avg_step_iterations_mean",
            "residual_drift_ratio_pct_max_abs",
            "solver_hip_variants",
        ]
        values = {
            label: _kpi_value(kpi_receipt, label)
            for label in labels
            if _kpi_value(kpi_receipt, label) is not None
        }
        return {
            "value": values or None,
            "status": "measured_run_kpi_recorded" if values else "not_available",
            "locator": _bridge_locator(DEFAULT_KPI_RECEIPT, "$.kpi_rows[*]", "local_ndtha_kpi_receipt_rows"),
            "benchmark_status": "measured_run_kpi_bridge_attached" if values else "measured_run_kpi_bridge_missing",
            "reference_truth_status": REFERENCE_TRUTH_BRIDGE,
        }
    return {
        "value": DEFAULT_CITATION,
        "status": "recorded",
        "locator": _locator(metric_group),
        "benchmark_status": "citation_metric_recorded",
        "reference_truth_status": REFERENCE_TRUTH_CITATION,
    }


def _metric_record(
    source: dict[str, Any],
    metric_group: str,
    kpi_receipt: dict[str, Any],
    stress_report: dict[str, Any],
) -> dict[str, Any]:
    official_url = str(source.get("official_entrypoint_url", "") or "")
    citation = DEFAULT_CITATION
    payload = _metric_payload(metric_group, kpi_receipt, stress_report)

    return {
        "source_id": PEER_TBI_SOURCE_ID,
        "official_url": official_url,
        "citation": citation,
        "report_id": REPORT_ID,
        "metric_group": metric_group,
        "metric_name": METRIC_NAMES[metric_group],
        "value": payload["value"],
        "status": payload["status"],
        "unit": METRIC_UNITS[metric_group],
        "locator": payload["locator"],
        "benchmark_status": payload["benchmark_status"],
        "reference_truth_status": payload["reference_truth_status"],
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


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return True


def build_metric_records(
    manifest: dict[str, Any],
    coverage_matrix: dict[str, Any],
    *,
    kpi_receipt: dict[str, Any] | None = None,
    stress_report: dict[str, Any] | None = None,
    kpi_receipt_path: Path = DEFAULT_KPI_RECEIPT,
    stress_report_path: Path = DEFAULT_NDTHA_STRESS_REPORT,
) -> dict[str, Any]:
    source = _source_family(manifest)
    peer_gate = _peer_gate(coverage_matrix)
    coverage_targets = _coverage_targets(coverage_matrix, peer_gate)
    peer_source_exists = source is not None
    peer_gate_exists = set(REQUIRED_METRIC_GROUPS) <= set(coverage_targets)
    access_policy = _access_policy(source)
    raw_redistribution_default = bool(access_policy.get("redistribution_allowed", False))
    kpi_payload = kpi_receipt if isinstance(kpi_receipt, dict) else {}
    stress_payload = stress_report if isinstance(stress_report, dict) else {}

    metric_records = [
        _metric_record(source, group, kpi_payload, stress_payload) for group in REQUIRED_METRIC_GROUPS
    ] if source else []
    represented_groups = sorted({record["metric_group"] for record in metric_records})
    groups_with_value = sorted(
        {record["metric_group"] for record in metric_records if _value_present(record.get("value"))}
    )
    official_reference_truth_groups = sorted(
        {
            record["metric_group"]
            for record in metric_records
            if record.get("reference_truth_status") == REFERENCE_TRUTH_OFFICIAL
        }
    )
    measured_bridge_groups = sorted(
        {
            record["metric_group"]
            for record in metric_records
            if record.get("reference_truth_status") == REFERENCE_TRUTH_BRIDGE
        }
    )
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
            "metric_groups_with_value": groups_with_value,
            "metric_groups_with_value_count": len(groups_with_value),
            "metric_groups_missing_value": sorted(set(REQUIRED_METRIC_GROUPS) - set(groups_with_value)),
            "official_reference_truth_metric_groups": official_reference_truth_groups,
            "official_reference_truth_metric_group_count": len(official_reference_truth_groups),
            "measured_run_kpi_bridge_metric_groups": measured_bridge_groups,
            "measured_run_kpi_bridge_metric_group_count": len(measured_bridge_groups),
            "redistribution_allowed_record_count": redistribution_allowed_record_count,
            "raw_redistribution_auto_allowed": raw_redistribution_auto_allowed,
        },
        "source_documents": {
            "peer_task12_report": PEER_TASK12_REPORT,
            "kpi_receipt": _artifact_metadata(kpi_receipt_path),
            "ndtha_stress_report": _artifact_metadata(stress_report_path),
        },
        "claim_boundary": (
            "Non-citation values make the PEER metric rows traceable for the measured-corpus exit gate. "
            "Only rows marked official_public_report_metric are external PEER report values; measured-run "
            "KPI bridge rows are local solver evidence and must not be represented as third-party reference truth."
        ),
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


def write_records(
    manifest_path: Path,
    coverage_matrix_path: Path,
    out_path: Path,
    kpi_receipt_path: Path = DEFAULT_KPI_RECEIPT,
    stress_report_path: Path = DEFAULT_NDTHA_STRESS_REPORT,
) -> dict[str, Any]:
    payload = build_metric_records(
        _load_json(manifest_path),
        _load_json(coverage_matrix_path),
        kpi_receipt=_load_optional_json(kpi_receipt_path),
        stress_report=_load_optional_json(stress_report_path),
        kpi_receipt_path=kpi_receipt_path,
        stress_report_path=stress_report_path,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage-matrix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kpi-receipt", type=Path, default=DEFAULT_KPI_RECEIPT)
    parser.add_argument("--ndtha-stress-report", type=Path, default=DEFAULT_NDTHA_STRESS_REPORT)
    args = parser.parse_args()

    payload = write_records(
        args.manifest,
        args.coverage_matrix,
        args.out,
        args.kpi_receipt,
        args.ndtha_stress_report,
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
