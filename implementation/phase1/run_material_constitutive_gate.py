#!/usr/bin/env python3
"""Summarize constitutive-material evidence as a calibration benchmark matrix."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.runtime_contracts import InputContractError, validate_input_contract
    from implementation.phase1.rc_constitutive_library import (
        BondSlipMaterial,
        bond_slip_cyclic_probe,
        ConcreteMaterial,
        bond_slip_response,
        concrete_cyclic_probe,
        concrete_cyclic_step_series_evidence,
        concrete_response,
    )
except ImportError:  # pragma: no cover - script execution fallback
    from runtime_contracts import InputContractError, validate_input_contract
    from rc_constitutive_library import (
        BondSlipMaterial,
        bond_slip_cyclic_probe,
        ConcreteMaterial,
        bond_slip_response,
        concrete_cyclic_probe,
        concrete_cyclic_step_series_evidence,
        concrete_response,
    )


REASONS = {
    "PASS": "constitutive material evidence is present for concrete damage, cyclic degradation, bond interface, creep-shrinkage, soil-boundary nonlinearity, device dissipation, and transport/serviceability families",
    "ERR_INVALID_INPUT": "invalid material constitutive gate input",
    "ERR_CONCRETE_DAMAGE": "concrete damage evidence is incomplete",
    "ERR_CYCLIC_DEGRADATION": "cyclic degradation evidence is incomplete",
    "ERR_BOND_INTERFACE": "bond interface evidence is incomplete",
    "ERR_FOUNDATION_IMPEDANCE": "foundation impedance evidence is incomplete",
    "ERR_CONTACT_HYSTERESIS": "contact link hysteresis evidence is incomplete",
    "ERR_PANEL_ZONE_RESPONSE": "panel zone joint response evidence is incomplete",
    "ERR_WIND_DYNAMIC_RESPONSE": "wind dynamic response evidence is incomplete",
    "ERR_TRACK_SUPPORT_VISCOELASTICITY": "track-support viscoelasticity evidence is incomplete",
    "ERR_VEHICLE_TRACK_TRANSIENT_COUPLING": "vehicle-track transient coupling evidence is incomplete",
    "ERR_TUNNEL_SOIL_WAVE_ATTENUATION": "tunnel-soil wave attenuation evidence is incomplete",
    "ERR_SERVICEABILITY_VELOCITY_RESPONSE": "serviceability velocity-response evidence is incomplete",
    "ERR_CONSTRUCTION_STAGE_REDISTRIBUTION": "construction-stage redistribution evidence is incomplete",
    "ERR_JOINT_CONSTRAINT_TRANSFER": "joint constraint-transfer evidence is incomplete",
    "ERR_AEROELASTIC_SERVICEABILITY": "aeroelastic serviceability evidence is incomplete",
    "ERR_HETEROGENEOUS_SOIL_ADAPTATION": "heterogeneous-soil adaptation evidence is incomplete",
    "ERR_SEGMENT_JOINT_SOFTENING": "segment-joint softening evidence is incomplete",
    "ERR_LONGITUDINAL_WAVE_STRAIN_TRANSFER": "longitudinal wave/strain transfer evidence is incomplete",
    "ERR_RAW_PRESSURE_FIELD_MAPPING": "raw pressure-field mapping evidence is incomplete",
    "ERR_PHASE_ASSIMILATION_CORRECTION": "phase-assimilation correction evidence is incomplete",
    "ERR_MULTISCALE_STREAMING_REFINEMENT": "multi-scale streaming refinement evidence is incomplete",
    "ERR_INTEGRATED_VIBRATION_TRANSFER": "integrated vibration-transfer evidence is incomplete",
    "ERR_RESILIENCE_OOD_RECOVERY": "resilience/OOD recovery evidence is incomplete",
}

_WALL_SLAB_TOPOLOGIES = {"wall-frame", "shell-wall", "wall_slab", "slab-wall", "slab_wall"}
_RC_STEP_SERIES_FAMILIES = {"cyclic_wall_cracking", "slab_wall_interaction"}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "pushover_stress_report",
        "ndtha_stress_report",
        "rc_benchmark_lock_report",
        "construction_sequence_report",
        "benchmark_cases",
        "min_concrete_damage_rows",
        "min_cyclic_rows",
        "min_bond_interface_rows",
        "out",
    ],
    "properties": {
        "pushover_stress_report": {"type": "string", "minLength": 1},
        "ndtha_stress_report": {"type": "string", "minLength": 1},
        "rc_benchmark_lock_report": {"type": "string", "minLength": 1},
        "rc_benchmark_lock_cases": {"type": "string", "minLength": 1},
        "construction_sequence_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "damper_validation_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "structural_contact_validation_report": {"type": "string", "minLength": 1},
        "panel_zone_clash_report": {"type": "string", "minLength": 1},
        "wind_time_history_gate_report": {"type": "string", "minLength": 1},
        "vibration_attenuation_report": {"type": "string", "minLength": 1},
        "vibration_compliance_report": {"type": "string", "minLength": 1},
        "track_lf_solver_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_report": {"type": "string", "minLength": 1},
        "vti_coupled_solver_report": {"type": "string", "minLength": 1},
        "track_irregularity_report": {"type": "string", "minLength": 1},
        "track_dynamics_dataset_report": {"type": "string", "minLength": 1},
        "tunnel_dynamics_dataset_report": {"type": "string", "minLength": 1},
        "heterogeneous_soil_ood_report": {"type": "string", "minLength": 1},
        "tunnel_segment_joint_report": {"type": "string", "minLength": 1},
        "tunnel_seismic_longitudinal_report": {"type": "string", "minLength": 1},
        "wind_tunnel_raw_mapping_report": {"type": "string", "minLength": 1},
        "phase_correction_assimilation_report": {"type": "string", "minLength": 1},
        "multiscale_l3_streaming_report": {"type": "string", "minLength": 1},
        "phasee_integrated_summary_report": {"type": "string", "minLength": 1},
        "phasef_resilience_summary_report": {"type": "string", "minLength": 1},
        "dynamics_boundary_report": {"type": "string", "minLength": 1},
        "moving_load_attention_report": {"type": "string", "minLength": 1},
        "physics_residual_contract_report": {"type": "string", "minLength": 1},
        "benchmark_cases": {"type": "string", "minLength": 1},
        "min_concrete_damage_rows": {"type": "integer", "minimum": 1},
        "min_cyclic_rows": {"type": "integer", "minimum": 1},
        "min_bond_interface_rows": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _parse_csv(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _infer_source_family(row: dict[str, Any], payload: dict[str, Any], path: Path) -> str:
    direct = str(row.get("source_family", "") or "").strip()
    if direct:
        return direct
    payload_direct = str(payload.get("source_family", "") or "").strip()
    if payload_direct:
        return payload_direct
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary_direct = str(summary.get("source_family", "") or summary.get("source_name", "") or "").strip()
        if summary_direct:
            return summary_direct
    case_id = str(row.get("case_id", "") or "").strip().lower()
    if case_id.startswith("rwth-"):
        return "rwth_zenodo"
    if case_id.startswith("c-"):
        return "commercial_export"
    stem = path.stem
    prefix = "commercial_benchmark_cases."
    if stem.startswith(prefix):
        stem = stem[len(prefix):]
    return stem or "unclassified"


def _infer_element_mix(row: dict[str, Any]) -> str:
    direct = str(row.get("element_mix", "") or "").strip()
    if direct:
        return direct
    topology_type = str(row.get("topology_type", "") or "").strip().lower()
    if topology_type in {"outrigger", "wall-frame", "shell-wall"}:
        return "shell_beam_mix"
    return "beam_only"


def _benchmark_case_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("cases", "public_benchmark_cases"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _payload_source_family_labels(payload: dict[str, Any]) -> set[str]:
    labels: set[str] = set()

    def _add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            labels.add(text)

    _add(payload.get("source_family"))

    summary = payload.get("summary")
    if isinstance(summary, dict):
        _add(summary.get("source_family"))
        _add(summary.get("source_name"))

    source = payload.get("source")
    if isinstance(source, dict):
        _add(source.get("source_family"))
        _add(source.get("candidate_id"))
        catalog_entry = source.get("catalog_entry")
        if isinstance(catalog_entry, dict):
            _add(catalog_entry.get("source_family"))
            _add(catalog_entry.get("id"))

    source_family_summary = payload.get("source_family_summary")
    if isinstance(source_family_summary, dict):
        for key in ("source_families", "distinct_source_families"):
            values = source_family_summary.get(key)
            if isinstance(values, list):
                for value in values:
                    _add(value)

    return labels


def _aggregate_source_family_cases(case_paths: list[Path]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    families: dict[str, dict[str, Any]] = {}
    coverage_labels: set[str] = set()
    for path in case_paths:
        payload = _load_json(path)
        coverage_labels.update(_payload_source_family_labels(payload))
        rows = _benchmark_case_rows(payload)
        for row in rows:
            source_family = _infer_source_family(row, payload, path)
            if not source_family:
                continue
            coverage_labels.add(source_family)
            family = families.setdefault(
                source_family,
                {
                    "case_count": 0,
                    "element_mix_counts": {},
                    "topology_counts": {},
                },
            )
            family["case_count"] += 1
            element_mix = _infer_element_mix(row)
            topology_type = str(row.get("topology_type", "") or "").strip()
            if element_mix:
                family["element_mix_counts"][element_mix] = int(family["element_mix_counts"].get(element_mix, 0)) + 1
            if topology_type:
                family["topology_counts"][topology_type] = int(family["topology_counts"].get(topology_type, 0)) + 1
    return families, coverage_labels


def _load_rc_lock_physical_families(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("cases")
    if not isinstance(rows, list):
        return {}
    families: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        family = str(row.get("benchmark_family", "") or "").strip()
        if not family:
            continue
        expected_ranges = row.get("expected_ranges")
        family_payload = families.setdefault(
            family,
            {
                "case_count": 0,
                "expected_metric_labels": set(),
                "case_ids": [],
            },
        )
        family_payload["case_count"] += 1
        case_id = str(row.get("case_id", "") or "").strip()
        if case_id:
            family_payload["case_ids"].append(case_id)
        if isinstance(expected_ranges, dict):
            for metric in expected_ranges:
                label = str(metric or "").strip()
                if label:
                    family_payload["expected_metric_labels"].add(label)
    return families


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return math.nan


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return 0


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unclassified"
    out: list[str] = []
    last_dash = False
    for char in text:
        if char.isalnum():
            out.append(char)
            last_dash = False
            continue
        if not last_dash:
            out.append("-")
            last_dash = True
    return "".join(out).strip("-") or "unclassified"


def _iter_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _iter_authority_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("authority_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("summary")
    return summary if isinstance(summary, dict) else {}


def _material_indices(row: dict[str, Any]) -> dict[str, Any]:
    summary = _row_summary(row)
    material_indices = summary.get("material_indices")
    return material_indices if isinstance(material_indices, dict) else {}


def _compression_damage_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _iter_rows(payload):
        compression_damage_mean = _safe_float(_material_indices(row).get("compression_damage_mean"))
        if math.isfinite(compression_damage_mean) and compression_damage_mean > 0.0:
            out.append(
                {
                    "case_id": str(row.get("case_id", "") or ""),
                    "topology_type": str(row.get("topology_type", "") or ""),
                    "hazard_type": str(row.get("hazard_type", "") or ""),
                    "compression_damage_mean": compression_damage_mean,
                }
            )
    return out


def _bond_interface_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _iter_rows(payload):
        bond_slip_index_mean = _safe_float(_material_indices(row).get("bond_slip_index_mean"))
        if math.isfinite(bond_slip_index_mean) and bond_slip_index_mean > 0.0:
            out.append(
                {
                    "case_id": str(row.get("case_id", "") or ""),
                    "topology_type": str(row.get("topology_type", "") or ""),
                    "hazard_type": str(row.get("hazard_type", "") or ""),
                    "bond_slip_index_mean": bond_slip_index_mean,
                }
            )
    return out


def _cyclic_degradation_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _iter_rows(payload):
        summary = _row_summary(row)
        residual_drift_ratio_pct = _safe_float(summary.get("residual_drift_ratio_pct"))
        raw_residual_drift_ratio_pct = _safe_float(summary.get("raw_residual_drift_ratio_pct"))
        response_storage = str((row.get("artifacts") or {}).get("response_storage", "") or summary.get("response_storage", "") or "").strip()
        if not math.isfinite(residual_drift_ratio_pct):
            continue
        if abs(residual_drift_ratio_pct) <= 0.0 and abs(raw_residual_drift_ratio_pct if math.isfinite(raw_residual_drift_ratio_pct) else 0.0) <= 0.0:
            continue
        out.append(
            {
                "case_id": str(row.get("case_id", "") or ""),
                "topology_type": str(row.get("topology_type", "") or ""),
                "hazard_type": str(row.get("hazard_type", "") or ""),
                "residual_drift_ratio_pct": residual_drift_ratio_pct,
                "raw_residual_drift_ratio_pct": raw_residual_drift_ratio_pct if math.isfinite(raw_residual_drift_ratio_pct) else 0.0,
                "response_storage": response_storage or "n/a",
            }
        )
    return out


def _load_manifest_source_family(path_value: Any) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    manifest = _load_json(Path(path_text))
    return str(manifest.get("source_family", "") or manifest.get("source_name", "") or "").strip()


def _summary_dict(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _joint_constraint_transfer_panel_zone_evidence(
    panel_zone_checks: dict[str, Any],
    panel_zone_summary: dict[str, Any],
) -> dict[str, Any]:
    source_valid_row_counts = panel_zone_summary.get("panel_zone_source_valid_row_counts")
    if not isinstance(source_valid_row_counts, dict):
        source_valid_row_counts = {}

    source_row_count_from_map = sum(max(_safe_int(value), 0) for value in source_valid_row_counts.values())
    validated_source_count_from_map = sum(1 for value in source_valid_row_counts.values() if _safe_int(value) > 0)
    explicit_source_row_count = max(_safe_int(panel_zone_summary.get("panel_zone_validated_source_row_count_total")), 0)
    external_validated_row_count = max(_safe_int(panel_zone_summary.get("panel_zone_external_validation_validated_row_count_total")), 0)
    clash_row_count = max(_safe_int(panel_zone_summary.get("panel_zone_clash_row_count")), 0)
    external_validated_source_count = max(_safe_int(panel_zone_summary.get("panel_zone_external_validation_validated_source_count")), 0)
    validated_source_count = max(validated_source_count_from_map, external_validated_source_count)
    missing_source_count = max(_safe_int(panel_zone_summary.get("panel_zone_external_validation_missing_source_count")), 0)

    artifact_closed = bool(panel_zone_summary.get("panel_zone_external_validation_artifact_closed", False))
    pending_input = bool(panel_zone_summary.get("panel_zone_solver_verified_pending_input", False))
    latest_consume_present = bool(panel_zone_summary.get("panel_zone_solver_verified_latest_consume_report_present", False))
    latest_consume_pass = bool(panel_zone_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False))
    validation_boundary = str(panel_zone_summary.get("panel_zone_validation_boundary", "") or "").strip().lower()
    closure_mode = str(panel_zone_summary.get("panel_zone_external_validation_closure_mode", "") or "").strip().lower()
    local_closure_state = str(panel_zone_summary.get("panel_zone_external_validation_local_closure_state", "") or "").strip().lower()
    recommended_action = str(panel_zone_summary.get("panel_zone_solver_verified_recommended_action", "") or "").strip().lower()

    required_sources_complete = bool(
        panel_zone_checks.get("panel_zone_required_sources_complete", False)
        or panel_zone_summary.get("panel_zone_required_sources_complete", False)
        or (artifact_closed and missing_source_count == 0 and validated_source_count > 0)
    )
    topology_projected_bridge_complete = bool(
        panel_zone_checks.get("panel_zone_topology_projected_bridge_complete", False)
        or panel_zone_summary.get("panel_zone_topology_projected_bridge_complete", False)
        or (
            required_sources_complete
            and bool(
                panel_zone_checks.get("panel_zone_solver_verified_bridge_complete", False)
                or panel_zone_summary.get("panel_zone_solver_verified_bridge_complete", False)
            )
            and artifact_closed
            and not pending_input
            and validation_boundary == "solver_verified"
            and latest_consume_present
            and latest_consume_pass
        )
    )
    internal_engine_complete = bool(
        panel_zone_checks.get("panel_zone_internal_engine_complete", False)
        or panel_zone_summary.get("panel_zone_internal_engine_complete", False)
        or (
            artifact_closed
            and not pending_input
            and latest_consume_present
            and latest_consume_pass
            and (
                validation_boundary == "solver_verified"
                or closure_mode.startswith("closed")
                or local_closure_state.startswith("closed")
                or recommended_action == "local_closeout_closed"
            )
        )
    )

    if (
        artifact_closed
        and clash_row_count > 0
        and validated_source_count > 0
        and (
            closure_mode == "closed_exact_validated"
            or local_closure_state == "closed_with_solver_verified_artifact"
        )
    ):
        source_row_count = max(
            explicit_source_row_count,
            external_validated_row_count,
            source_row_count_from_map,
            clash_row_count * validated_source_count,
        )
    else:
        source_row_count = max(
            explicit_source_row_count,
            external_validated_row_count,
            source_row_count_from_map,
        )

    return {
        "required_sources_complete": required_sources_complete,
        "topology_projected_bridge_complete": topology_projected_bridge_complete,
        "internal_engine_complete": internal_engine_complete,
        "source_row_count": int(source_row_count),
    }


def _append_constitutive_family_evidence(
    coverage: dict[str, dict[str, dict[str, Any]]],
    family_key: str,
    family_name: str,
    *,
    kind: str,
    source: str,
    metric: str,
    case_id: str,
    passed: bool,
    extra_context: dict[str, Any] | None = None,
) -> None:
    scoped = coverage.setdefault(family_key, {})
    entry = scoped.setdefault(
        family_name,
        {
            "kind": kind,
            "source": source,
            "metric": metric,
            "passed": True,
            "case_count": 0,
            "case_ids": [],
            "metric_names": set(),
            "authority_families": set(),
            "manifest_paths": set(),
        },
    )
    entry["passed"] = bool(entry["passed"] and passed)
    entry["case_count"] = int(entry["case_count"]) + 1
    if case_id:
        entry["case_ids"].append(case_id)
    context = extra_context or {}
    for metric_name in context.get("metric_names", []):
        label = str(metric_name or "").strip()
        if label:
            entry["metric_names"].add(label)
    for authority_family in context.get("authority_families", []):
        label = str(authority_family or "").strip()
        if label:
            entry["authority_families"].add(label)
    for manifest_path in context.get("manifest_paths", []):
        label = str(manifest_path or "").strip()
        if label:
            entry["manifest_paths"].add(label)


def _collect_constitutive_family_evidence(rc_lock: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    coverage: dict[str, dict[str, dict[str, Any]]] = {
        "concrete_damage": {},
        "cyclic_degradation": {},
        "bond_interface": {},
        "creep_shrinkage": {},
    }
    for row in _iter_rows(rc_lock):
        benchmark_family = str(row.get("benchmark_family", "") or "").strip()
        case_id = str(row.get("case_id", "") or "").strip()
        if not benchmark_family:
            continue
        metric_values = row.get("metric_values")
        if not isinstance(metric_values, dict):
            metric_values = {}
        metric_checks = row.get("metric_checks")
        if not isinstance(metric_checks, dict):
            metric_checks = {}
        passed = bool(
            row.get("case_pass", False)
            and (not metric_checks or all(bool(value) for value in metric_checks.values()))
        )
        metric_names = sorted(str(name).strip() for name in metric_values.keys() if str(name).strip())
        common_context = {"metric_names": metric_names}
        if "cracking_index_mean" in metric_values or "creep_index_mean" in metric_values:
            _append_constitutive_family_evidence(
                coverage,
                "concrete_damage",
                benchmark_family,
                kind="benchmark_family",
                source="rc_benchmark_lock_report",
                metric="benchmark_family_lock",
                case_id=case_id,
                passed=passed,
                extra_context=common_context,
            )
        if "creep_index_mean" in metric_values:
            _append_constitutive_family_evidence(
                coverage,
                "creep_shrinkage",
                benchmark_family,
                kind="benchmark_family",
                source="rc_benchmark_lock_report",
                metric="benchmark_family_lock",
                case_id=case_id,
                passed=passed,
                extra_context=common_context,
            )
        if "bond_slip_index_mean" in metric_values:
            _append_constitutive_family_evidence(
                coverage,
                "bond_interface",
                benchmark_family,
                kind="benchmark_family",
                source="rc_benchmark_lock_report",
                metric="benchmark_family_lock",
                case_id=case_id,
                passed=passed,
                extra_context=common_context,
            )
        if benchmark_family == "cyclic_wall_cracking":
            _append_constitutive_family_evidence(
                coverage,
                "cyclic_degradation",
                benchmark_family,
                kind="benchmark_family",
                source="rc_benchmark_lock_report",
                metric="benchmark_family_lock",
                case_id=case_id,
                passed=passed,
                extra_context=common_context,
            )
    for row in _iter_authority_rows(rc_lock):
        case_id = str(row.get("case_id", "") or "").strip()
        authority_family = str(row.get("authority_family", "") or "").strip()
        manifest_path = str(row.get("source_manifest_path", "") or "").strip()
        source_family = _load_manifest_source_family(manifest_path) or authority_family
        if not source_family:
            continue
        metric_checks = row.get("metric_checks")
        if not isinstance(metric_checks, dict):
            metric_checks = {}
        integrity_checks = row.get("integrity_checks")
        if not isinstance(integrity_checks, dict):
            integrity_checks = {}
        passed = bool(
            row.get("case_pass", False)
            and (not metric_checks or all(bool(value) for value in metric_checks.values()))
            and (not integrity_checks or all(bool(value) for value in integrity_checks.values()))
        )
        _append_constitutive_family_evidence(
            coverage,
            "cyclic_degradation",
            source_family,
            kind="authority_source_family",
            source="rc_benchmark_lock_report",
            metric="authority_waveform_lock",
            case_id=case_id,
            passed=passed,
            extra_context={
                "authority_families": [authority_family],
                "manifest_paths": [manifest_path],
            },
        )
    return coverage


def _bool_row(
    *,
    row_id: str,
    family: str,
    source: str,
    metric: str,
    value: Any,
    passed: bool,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "family": family,
        "source": source,
        "metric": metric,
        "value": value,
        "pass": bool(passed),
        "context": context or {},
    }


def _all_true(payload: dict[str, Any], *keys: str) -> bool:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    return bool(payload.get("contract_pass", False) and all(bool(checks.get(key, False)) for key in keys))


def _panel_zone_joint_response_surface(
    panel_zone_contract_pass: bool,
    panel_zone_checks: dict[str, Any],
    panel_zone_summary: dict[str, Any],
) -> dict[str, Any]:
    panel_zone_contract_pass = bool(panel_zone_contract_pass)
    artifact_contract_pass = bool(panel_zone_checks.get("panel_zone_clash_artifact_contract_pass", False))
    topology_capable_input = bool(panel_zone_checks.get("panel_zone_topology_capable_input", False))
    required_sources_complete = bool(
        panel_zone_checks.get(
            "panel_zone_required_sources_complete",
            panel_zone_summary.get("panel_zone_required_sources_complete", False),
        )
    )
    topology_projected_bridge_complete = bool(
        panel_zone_checks.get(
            "panel_zone_topology_projected_bridge_complete",
            panel_zone_summary.get("panel_zone_topology_projected_bridge_complete", False),
        )
    )
    solver_verified_bridge_complete = bool(
        panel_zone_checks.get(
            "panel_zone_solver_verified_bridge_complete",
            panel_zone_summary.get("panel_zone_solver_verified_bridge_complete", False),
        )
    )
    true_3d_bridge_complete = bool(
        panel_zone_checks.get(
            "panel_zone_true_3d_bridge_complete",
            panel_zone_summary.get("panel_zone_true_3d_bridge_complete", False),
        )
    )
    internal_engine_complete = bool(
        panel_zone_checks.get(
            "panel_zone_internal_engine_complete",
            panel_zone_summary.get("panel_zone_internal_engine_complete", False),
        )
    )
    true_3d_clash_verified = bool(
        panel_zone_checks.get(
            "panel_zone_true_3d_clash_verified",
            panel_zone_summary.get("panel_zone_true_3d_clash_verified", False),
        )
    )
    true_3d_anchorage_verified = bool(
        panel_zone_checks.get(
            "panel_zone_true_3d_anchorage_verified",
            panel_zone_summary.get("panel_zone_true_3d_anchorage_verified", False),
        )
    )
    external_validation_artifact_closed = bool(
        panel_zone_summary.get("panel_zone_external_validation_artifact_closed", False)
    )
    dataset_contract_pass = bool(panel_zone_checks.get("dataset_contract_pass", False))
    pbd_contract_pass = bool(panel_zone_checks.get("pbd_contract_pass", False))
    row_count = int(panel_zone_summary.get("panel_zone_clash_row_count", 0) or 0)
    source_contract_mode = str(
        panel_zone_summary.get("panel_zone_source_contract_mode", "")
        or panel_zone_summary.get("constructability_mode", "")
        or ""
    ).strip()

    bridge_complete = bool(
        topology_projected_bridge_complete or true_3d_bridge_complete or solver_verified_bridge_complete
    )
    if topology_projected_bridge_complete:
        bridge_mode = "topology_projected"
    elif true_3d_bridge_complete:
        bridge_mode = "true_3d_verified"
    elif solver_verified_bridge_complete:
        bridge_mode = "solver_verified"
    else:
        bridge_mode = "missing"

    exact_verified_complete = bool(
        required_sources_complete
        and true_3d_clash_verified
        and true_3d_anchorage_verified
        and (true_3d_bridge_complete or solver_verified_bridge_complete or external_validation_artifact_closed)
    )
    material_evidence_complete = bool(internal_engine_complete or exact_verified_complete)
    if internal_engine_complete:
        material_evidence_mode = "internal_engine"
    elif exact_verified_complete:
        material_evidence_mode = "true_3d_verified"
    else:
        material_evidence_mode = "missing"

    family_pass = bool(
        panel_zone_contract_pass
        and artifact_contract_pass
        and topology_capable_input
        and required_sources_complete
        and bridge_complete
        and material_evidence_complete
        and dataset_contract_pass
        and pbd_contract_pass
        and row_count > 0
    )
    return {
        "panel_zone_contract_pass": panel_zone_contract_pass,
        "artifact_contract_pass": artifact_contract_pass,
        "topology_capable_input": topology_capable_input,
        "required_sources_complete": required_sources_complete,
        "topology_projected_bridge_complete": topology_projected_bridge_complete,
        "solver_verified_bridge_complete": solver_verified_bridge_complete,
        "true_3d_bridge_complete": true_3d_bridge_complete,
        "bridge_complete": bridge_complete,
        "bridge_mode": bridge_mode,
        "internal_engine_complete": internal_engine_complete,
        "true_3d_clash_verified": true_3d_clash_verified,
        "true_3d_anchorage_verified": true_3d_anchorage_verified,
        "external_validation_artifact_closed": external_validation_artifact_closed,
        "exact_verified_complete": exact_verified_complete,
        "material_evidence_complete": material_evidence_complete,
        "material_evidence_mode": material_evidence_mode,
        "dataset_contract_pass": dataset_contract_pass,
        "pbd_contract_pass": pbd_contract_pass,
        "row_count": row_count,
        "source_contract_mode": source_contract_mode,
        "family_pass": family_pass,
    }


def _dimension_counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key, "") or "").strip() or "unclassified"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _concrete_damage_library_summary(mat: Any | None = None) -> dict[str, Any]:
    if mat is None:
        mat = ConcreteMaterial(fc_mpa=36.0, eps_c0=0.0021, eps_cu=0.0038)

    sample_strains = (5.0e-5, 3.0e-4, -1.2e-3, -2.8e-3, -4.2e-3)
    snapshots = [concrete_response(strain, mat) for strain in sample_strains]
    sample_rows = [
        {
            "strain": float(snapshot.strain),
            "stress_mpa": float(snapshot.stress_mpa),
            "tangent_mpa": float(snapshot.tangent_mpa),
            "state_tag": str(snapshot.state_tag),
        }
        for snapshot in snapshots
    ]
    unique_state_tags = sorted({str(snapshot.state_tag) for snapshot in snapshots if str(snapshot.state_tag).strip()})
    max_tension_strain_ratio = max(
        (
            float(snapshot.strain) / max(float(mat.tension_softening_strain), 1.0e-9)
            for snapshot in snapshots
            if float(snapshot.strain) > 0.0
        ),
        default=0.0,
    )
    max_compression_strain_ratio = max(
        (
            abs(float(snapshot.strain)) / max(float(mat.eps_cu), 1.0e-9)
            for snapshot in snapshots
            if float(snapshot.strain) < 0.0
        ),
        default=0.0,
    )
    residual_strength_ratio = max(
        (
            abs(float(snapshot.stress_mpa)) / max(float(mat.confined_fc_mpa), 1.0e-9)
            for snapshot in snapshots
            if str(snapshot.state_tag) == "compression_crushed"
        ),
        default=0.0,
    )
    state_coverage_pass = {
        "tension_softening",
        "compression_hardening",
        "compression_softening",
        "compression_crushed",
    }.issubset(set(unique_state_tags))
    residual_ratio_pass = bool(
        math.isfinite(residual_strength_ratio)
        and abs(residual_strength_ratio - float(mat.residual_comp_ratio)) <= 1.0e-6
    )
    return {
        "source": "implementation.phase1.rc_constitutive_library.concrete_response",
        "sample_strains": list(sample_strains),
        "samples": sample_rows,
        "state_tags": unique_state_tags,
        "state_tag_count": int(len(unique_state_tags)),
        "max_tension_strain_ratio": float(max_tension_strain_ratio),
        "max_compression_strain_ratio": float(max_compression_strain_ratio),
        "residual_strength_ratio": float(residual_strength_ratio),
        "state_coverage_pass": bool(state_coverage_pass),
        "residual_ratio_pass": bool(residual_ratio_pass),
        "library_evidence_pass": bool(state_coverage_pass and residual_ratio_pass),
    }


def _cyclic_library_evidence_summary(probe: Any | None = None) -> dict[str, Any]:
    if probe is None:
        probe = concrete_cyclic_probe()
    restoring_state_tags = [str(tag) for tag in probe.restoring_state_tags if str(tag).strip()]
    envelope_state_tags = [str(tag) for tag in probe.envelope_state_tags if str(tag).strip()]
    unique_restoring_state_tags = sorted(set(restoring_state_tags))
    unique_envelope_state_tags = sorted(set(envelope_state_tags))
    return {
        "source": "implementation.phase1.rc_constitutive_library.concrete_cyclic_probe",
        "probe_id": probe.probe_id,
        "strain_history": list(probe.strain_history),
        "restoring_state_tags": restoring_state_tags,
        "restoring_state_tag_count": int(len(unique_restoring_state_tags)),
        "envelope_state_tags": envelope_state_tags,
        "envelope_state_tag_count": int(len(unique_envelope_state_tags)),
        "evidence_tags": list(probe.evidence_tags),
        "reversal_count": int(probe.reversal_count),
        "crack_open": bool(probe.crack_open),
        "pinching_observed": bool(probe.pinching_observed),
        "crushing_observed": bool(probe.crushing_observed),
        "degradation_observed": bool(probe.degradation_observed),
        "min_pinching_ratio": float(probe.min_pinching_ratio),
        "max_crushing_ratio": float(probe.max_crushing_ratio),
        "max_stiffness_degradation": float(probe.max_stiffness_degradation),
        "max_strength_degradation": float(probe.max_strength_degradation),
        "final_history_tag": str(probe.final_history_tag),
        "library_evidence_pass": bool(
            probe.reversal_count >= 1
            and probe.pinching_observed
            and probe.crushing_observed
            and probe.degradation_observed
        ),
    }


def _bond_interface_library_summary(mat: Any | None = None) -> dict[str, Any]:
    if mat is None:
        mat = BondSlipMaterial()

    sample_slips = (0.25, 1.0, 4.0, -1.0)
    snapshots = [(float(slip), bond_slip_response(float(slip), mat)) for slip in sample_slips]
    sample_rows = [
        {
            "slip_mm": float(slip),
            "stress_kn": float(snapshot.stress_mpa),
            "tangent_kn_per_mm": float(snapshot.tangent_mpa),
            "state_tag": str(snapshot.state_tag),
        }
        for slip, snapshot in snapshots
    ]
    unique_state_tags = sorted({str(snapshot.state_tag) for _, snapshot in snapshots if str(snapshot.state_tag).strip()})
    peak_force = max(float(mat.peak_force_kn), 1.0e-9)
    max_slip_ratio = max((abs(float(slip)) / max(float(mat.slip_u_mm), 1.0e-9) for slip, _ in snapshots), default=0.0)
    residual_force_ratio = max(
        (
            abs(float(snapshot.stress_mpa)) / peak_force
            for _, snapshot in snapshots
            if str(snapshot.state_tag) == "bond_residual"
        ),
        default=0.0,
    )
    softening_tangent_ratio = max(
        (
            abs(float(snapshot.tangent_mpa)) / max(float(mat.k0_kn_per_mm), 1.0e-9)
            for _, snapshot in snapshots
            if str(snapshot.state_tag) == "bond_softening"
        ),
        default=0.0,
    )
    positive_softening = next((snapshot for slip, snapshot in snapshots if float(slip) > 0.0 and str(snapshot.state_tag) == "bond_softening"), None)
    negative_softening = next((snapshot for slip, snapshot in snapshots if float(slip) < 0.0 and str(snapshot.state_tag) == "bond_softening"), None)
    symmetry_error_ratio = 0.0
    if positive_softening is not None and negative_softening is not None:
        symmetry_error_ratio = abs(float(positive_softening.stress_mpa) + float(negative_softening.stress_mpa)) / peak_force
    state_coverage_pass = {"bond_elastic", "bond_softening", "bond_residual"}.issubset(set(unique_state_tags))
    residual_ratio_pass = bool(
        math.isfinite(residual_force_ratio)
        and abs(residual_force_ratio - float(mat.residual_ratio)) <= 1.0e-6
    )
    symmetry_pass = bool(math.isfinite(symmetry_error_ratio) and symmetry_error_ratio <= 1.0e-9)
    return {
        "source": "implementation.phase1.rc_constitutive_library.bond_slip_response",
        "sample_slips_mm": list(sample_slips),
        "samples": sample_rows,
        "state_tags": unique_state_tags,
        "state_tag_count": int(len(unique_state_tags)),
        "max_slip_ratio": float(max_slip_ratio),
        "residual_force_ratio": float(residual_force_ratio),
        "softening_tangent_ratio": float(softening_tangent_ratio),
        "symmetry_error_ratio": float(symmetry_error_ratio),
        "state_coverage_pass": bool(state_coverage_pass),
        "residual_ratio_pass": bool(residual_ratio_pass),
        "symmetry_pass": bool(symmetry_pass),
        "library_evidence_pass": bool(state_coverage_pass and residual_ratio_pass and symmetry_pass),
    }


def _bond_interface_cyclic_evidence_summary(probe: Any | None = None) -> dict[str, Any]:
    if probe is None:
        probe = bond_slip_cyclic_probe()
    restoring_state_tags = [str(tag) for tag in probe.restoring_state_tags if str(tag).strip()]
    envelope_state_tags = [str(tag) for tag in probe.envelope_state_tags if str(tag).strip()]
    return {
        "source": "implementation.phase1.rc_constitutive_library.bond_slip_cyclic_probe",
        "probe_id": probe.probe_id,
        "slip_history_mm": list(probe.slip_history_mm),
        "restoring_state_tags": restoring_state_tags,
        "restoring_state_tag_count": int(len(set(restoring_state_tags))),
        "envelope_state_tags": envelope_state_tags,
        "envelope_state_tag_count": int(len(set(envelope_state_tags))),
        "evidence_tags": list(probe.evidence_tags),
        "reversal_count": int(probe.reversal_count),
        "unloading_observed": bool(probe.unloading_observed),
        "residual_observed": bool(probe.residual_observed),
        "degradation_observed": bool(probe.degradation_observed),
        "min_unloading_stiffness_ratio": float(probe.min_unloading_stiffness_ratio),
        "max_strength_degradation": float(probe.max_strength_degradation),
        "max_slip_ratio": float(probe.max_slip_ratio),
        "terminal_residual_force_ratio": float(probe.terminal_residual_force_ratio),
        "final_history_tag": str(probe.final_history_tag),
        "library_evidence_pass": bool(
            probe.reversal_count >= 1
            and probe.unloading_observed
            and probe.residual_observed
            and probe.degradation_observed
            and probe.min_unloading_stiffness_ratio < 1.0
        ),
    }


def _cyclic_step_series_evidence_summary(
    ndtha: dict[str, Any],
    ndtha_cyclic_rows: list[dict[str, Any]],
    rc_lock: dict[str, Any],
    *,
    cyclic_probe: Any | None = None,
) -> dict[str, Any]:
    ndtha_summary = _summary_dict(ndtha)
    response_npz = ndtha.get("response_npz") if isinstance(ndtha.get("response_npz"), dict) else {}
    solver_control = ndtha.get("solver_control") if isinstance(ndtha.get("solver_control"), dict) else {}

    response_storage_modes = sorted(
        {
            str(row.get("response_storage", "") or "").strip()
            for row in ndtha_cyclic_rows
            if str(row.get("response_storage", "") or "").strip() and str(row.get("response_storage", "") or "").strip() != "n/a"
        }
    )
    if not response_storage_modes:
        for candidate in (
            response_npz.get("storage"),
            ndtha_summary.get("response_storage"),
        ):
            label = str(candidate or "").strip()
            if label:
                response_storage_modes.append(label)
    response_case_count = int(
        response_npz.get("case_count")
        or ndtha_summary.get("response_npz_case_count")
        or len([row for row in ndtha_cyclic_rows if str(row.get("response_storage", "") or "").strip() != "n/a"])
        or len(ndtha_cyclic_rows)
    )
    series_case_count = int(
        response_npz.get("series_case_count")
        or len([row for row in ndtha_cyclic_rows if str(row.get("response_storage", "") or "").strip() != "n/a"])
        or len(ndtha_cyclic_rows)
    )
    step_series_depth = int(
        response_npz.get("full_step_count_max")
        or response_npz.get("inline_step_count_max")
        or series_case_count
        or len(ndtha_cyclic_rows)
    )
    solver_event_count_total = int(
        solver_control.get("event_count_total")
        or ndtha_summary.get("solver_control_event_count_total")
        or 0
    )
    recommended_dt_scale_min = _safe_float(
        solver_control.get("recommended_dt_scale_min")
        if solver_control
        else ndtha_summary.get("solver_control_recommended_dt_scale_min")
    )
    if not math.isfinite(recommended_dt_scale_min):
        recommended_dt_scale_min = _safe_float(ndtha_summary.get("solver_control_recommended_dt_scale_min"))
    if not math.isfinite(recommended_dt_scale_min):
        recommended_dt_scale_min = 1.0

    wall_slab_case_count = sum(
        1
        for row in ndtha_cyclic_rows
        if str(row.get("topology_type", "") or "").strip().lower() in _WALL_SLAB_TOPOLOGIES
    )
    rc_case_count = 0
    rc_family_labels: set[str] = set()
    for row in _iter_rows(rc_lock):
        family = str(row.get("benchmark_family", "") or "").strip()
        if family in _RC_STEP_SERIES_FAMILIES:
            rc_case_count += 1
            rc_family_labels.add(family)

    source_mode = "ndtha_response_npz" if response_npz else "ndtha_row_fallback"
    evidence = concrete_cyclic_step_series_evidence(
        probe=cyclic_probe,
        cyclic_case_count=len(ndtha_cyclic_rows),
        wall_slab_case_count=wall_slab_case_count,
        rc_case_count=rc_case_count,
        response_case_count=response_case_count,
        series_case_count=series_case_count,
        step_series_depth=step_series_depth,
        solver_event_count_total=solver_event_count_total,
        recommended_dt_scale_min=float(recommended_dt_scale_min),
        response_storage_modes=tuple(response_storage_modes),
        source_mode=source_mode,
    )
    return {
        "source": "nonlinear_ndtha_stress_report",
        "source_mode": evidence.source_mode,
        "response_case_count": int(evidence.response_case_count),
        "series_case_count": int(evidence.series_case_count),
        "cyclic_case_count": int(evidence.cyclic_case_count),
        "wall_slab_case_count": int(evidence.wall_slab_case_count),
        "rc_case_count": int(evidence.rc_case_count),
        "step_series_depth": int(evidence.step_series_depth),
        "response_coverage_ratio": float(evidence.response_coverage_ratio),
        "wall_slab_coverage_ratio": float(evidence.wall_slab_coverage_ratio),
        "rc_step_density": float(evidence.rc_step_density),
        "solver_event_count_total": int(evidence.solver_event_count_total),
        "solver_event_density": float(evidence.solver_event_density),
        "recommended_dt_scale_min": float(evidence.recommended_dt_scale_min),
        "response_storage_modes": list(evidence.response_storage_modes),
        "rc_family_labels": sorted(rc_family_labels),
        "evidence_tags": list(evidence.evidence_tags),
        "series_link_pass": bool(evidence.series_link_pass),
        "wall_slab_series_pass": bool(evidence.wall_slab_series_pass),
        "rc_series_link_pass": bool(evidence.rc_series_link_pass),
    }


def _calibration_matrix(
    *,
    pushover_concrete_rows: list[dict[str, Any]],
    ndtha_concrete_rows: list[dict[str, Any]],
    ndtha_cyclic_rows: list[dict[str, Any]],
    pushover_bond_rows: list[dict[str, Any]],
    ndtha_bond_rows: list[dict[str, Any]],
    pushover_contract_pass: bool,
    ndtha_contract_pass: bool,
    rc_lock_contract_pass: bool,
    construction_contract_pass: bool,
    ssi_contract_pass: bool,
    damper_contract_pass: bool,
    pushover_checks: dict[str, Any],
    ndtha_checks: dict[str, Any],
    rc_lock_checks: dict[str, Any],
    construction_checks: dict[str, Any],
    ssi_checks: dict[str, Any],
    damper_checks: dict[str, Any],
    construction_summary: dict[str, Any],
    ssi_summary: dict[str, Any],
    damper_summary: dict[str, Any],
    foundation_contract_pass: bool,
    contact_contract_pass: bool,
    panel_zone_contract_pass: bool,
    wind_contract_pass: bool,
    foundation_checks: dict[str, Any],
    panel_zone_checks: dict[str, Any],
    wind_checks: dict[str, Any],
    foundation_summary: dict[str, Any],
    contact_summary: dict[str, Any],
    panel_zone_summary: dict[str, Any],
    wind_summary: dict[str, Any],
    ssi_rows: list[dict[str, Any]],
    wind_rows: list[dict[str, Any]],
    contact_categories: dict[str, Any],
    source_family_cases: dict[str, dict[str, Any]],
    supplemental_family_evidence: dict[str, dict[str, dict[str, Any]]],
    vibration_attenuation_contract_pass: bool,
    vibration_compliance_contract_pass: bool,
    track_lf_contract_pass: bool,
    moving_load_contract_pass: bool,
    vti_coupled_contract_pass: bool,
    track_dataset_contract_pass: bool,
    tunnel_dataset_contract_pass: bool,
    vibration_attenuation_checks: dict[str, Any],
    vibration_compliance_checks: dict[str, Any],
    track_lf_checks: dict[str, Any],
    moving_load_checks: dict[str, Any],
    vti_coupled_checks: dict[str, Any],
    track_dataset_checks: dict[str, Any],
    tunnel_dataset_checks: dict[str, Any],
    vibration_attenuation_metrics: dict[str, Any],
    vibration_compliance_metrics: dict[str, Any],
    track_lf_summary: dict[str, Any],
    moving_load_metrics: dict[str, Any],
    vti_coupled_metrics: dict[str, Any],
    track_irregularity_metrics: dict[str, Any],
    track_dataset_metrics: dict[str, Any],
    tunnel_dataset_metrics: dict[str, Any],
    heterogeneous_soil_contract_pass: bool,
    segment_joint_contract_pass: bool,
    tunnel_longitudinal_contract_pass: bool,
    wind_tunnel_mapping_contract_pass: bool,
    heterogeneous_soil_checks: dict[str, Any],
    heterogeneous_soil_metrics: dict[str, Any],
    segment_joint_checks: dict[str, Any],
    segment_joint_metrics: dict[str, Any],
    tunnel_longitudinal_checks: dict[str, Any],
    tunnel_longitudinal_metrics: dict[str, Any],
    wind_tunnel_mapping_checks: dict[str, Any],
    wind_tunnel_mapping_summary: dict[str, Any],
    phase_correction_contract_pass: bool,
    phase_correction_checks: dict[str, Any],
    phase_correction_metrics: dict[str, Any],
    multiscale_streaming_contract_pass: bool,
    multiscale_streaming_checks: dict[str, Any],
    multiscale_streaming_metrics: dict[str, Any],
    phasee_integrated_contract_pass: bool,
    phasee_integrated_checks: dict[str, Any],
    phasef_resilience_contract_pass: bool,
    phasef_resilience_checks: dict[str, Any],
    phasef_resilience_step_count: int,
    dynamics_boundary_contract_pass: bool,
    dynamics_boundary_supports_summary: dict[str, Any],
    dynamics_boundary_damping_summary: dict[str, Any],
    moving_load_attention_contract_pass: bool,
    moving_load_attention_checks: dict[str, Any],
    moving_load_attention_metrics: dict[str, Any],
    physics_residual_contract_pass: bool,
    physics_residual_checks: dict[str, Any],
    physics_residual_metrics: dict[str, Any],
    min_concrete_damage_rows: int,
    min_cyclic_rows: int,
    min_bond_interface_rows: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    concrete_rows = [*pushover_concrete_rows, *ndtha_concrete_rows]
    bond_rows = [*pushover_bond_rows, *ndtha_bond_rows]

    for row in pushover_concrete_rows:
        rows.append(
            _bool_row(
                row_id=f"concrete_damage:pushover:{row['case_id']}",
                family="concrete_damage",
                source="nonlinear_pushover_stress_report",
                metric="compression_damage_mean",
                value=row["compression_damage_mean"],
                passed=bool(row["compression_damage_mean"] > 0.0),
                context={
                    "case_id": row["case_id"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                },
            )
        )
    for row in ndtha_concrete_rows:
        rows.append(
            _bool_row(
                row_id=f"concrete_damage:ndtha:{row['case_id']}",
                family="concrete_damage",
                source="nonlinear_ndtha_stress_report",
                metric="compression_damage_mean",
                value=row["compression_damage_mean"],
                passed=bool(row["compression_damage_mean"] > 0.0),
                context={
                    "case_id": row["case_id"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                },
            )
        )
    rows.extend(
        [
            _bool_row(
                row_id="concrete_damage:gate:pushover_material_model",
                family="concrete_damage",
                source="nonlinear_pushover_stress_report",
                metric="material_model_pass",
                value=bool(pushover_checks.get("material_model_pass", False)),
                passed=bool(pushover_contract_pass and pushover_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="concrete_damage:gate:ndtha_material_model",
                family="concrete_damage",
                source="nonlinear_ndtha_stress_report",
                metric="material_model_pass",
                value=bool(ndtha_checks.get("material_model_pass", False)),
                passed=bool(ndtha_contract_pass and ndtha_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="concrete_damage:benchmark:rc_cracking_lock",
                family="concrete_damage",
                source="rc_benchmark_lock_report",
                metric="cracking_case_pass",
                value=bool(rc_lock_checks.get("cracking_case_pass", False)),
                passed=bool(rc_lock_contract_pass and rc_lock_checks.get("cracking_case_pass", False)),
            ),
            _bool_row(
                row_id="concrete_damage:threshold:min_case_coverage",
                family="concrete_damage",
                source="material_constitutive_gate",
                metric="min_case_coverage",
                value={
                    "pushover": len(pushover_concrete_rows),
                    "ndtha": len(ndtha_concrete_rows),
                    "required_per_source": int(min_concrete_damage_rows),
                },
                passed=bool(
                    len(pushover_concrete_rows) >= int(min_concrete_damage_rows)
                    and len(ndtha_concrete_rows) >= int(min_concrete_damage_rows)
                ),
            ),
        ]
    )
    concrete_topologies = _dimension_counter(concrete_rows, "topology_type")
    concrete_hazards = _dimension_counter(concrete_rows, "hazard_type")
    rows.append(
        _bool_row(
            row_id="concrete_damage:coverage:source_balance",
            family="concrete_damage",
            source="material_constitutive_gate",
            metric="source_balance",
            value={
                "pushover_cases": len(pushover_concrete_rows),
                "ndtha_cases": len(ndtha_concrete_rows),
                "sources_present": [
                    source
                    for source, count in (
                        ("pushover", len(pushover_concrete_rows)),
                        ("ndtha", len(ndtha_concrete_rows)),
                    )
                    if count > 0
                ],
            },
            passed=bool(pushover_concrete_rows and ndtha_concrete_rows),
        )
    )
    for topology_type, count in sorted(concrete_topologies.items()):
        rows.append(
            _bool_row(
                row_id=f"concrete_damage:coverage:topology:{_slug(topology_type)}",
                family="concrete_damage",
                source="material_constitutive_gate",
                metric="topology_coverage",
                value=topology_type,
                passed=bool(count > 0),
                context={"topology_type": topology_type, "case_count": count},
            )
        )
    for hazard_type, count in sorted(concrete_hazards.items()):
        rows.append(
            _bool_row(
                row_id=f"concrete_damage:coverage:hazard:{_slug(hazard_type)}",
                family="concrete_damage",
                source="material_constitutive_gate",
                metric="hazard_coverage",
                value=hazard_type,
                passed=bool(count > 0),
                context={"hazard_type": hazard_type, "case_count": count},
            )
        )
    for source_family, family_payload in sorted(source_family_cases.items()):
        case_count = int(family_payload.get("case_count", 0) or 0)
        topology_counts = family_payload.get("topology_counts") if isinstance(family_payload.get("topology_counts"), dict) else {}
        element_mix_counts = family_payload.get("element_mix_counts") if isinstance(family_payload.get("element_mix_counts"), dict) else {}
        wall_or_outrigger_count = int(topology_counts.get("wall-frame", 0)) + int(topology_counts.get("outrigger", 0))
        rows.extend(
            [
                _bool_row(
                    row_id=f"concrete_damage:source_family:{_slug(source_family)}:case_volume",
                    family="concrete_damage",
                    source="commercial_benchmark_cases",
                    metric="source_family_case_volume",
                    value=source_family,
                    passed=bool(case_count >= 2),
                    context={"source_family": source_family, "case_count": case_count},
                ),
                _bool_row(
                    row_id=f"concrete_damage:source_family:{_slug(source_family)}:wall_or_outrigger",
                    family="concrete_damage",
                    source="commercial_benchmark_cases",
                    metric="source_family_interaction_topology",
                    value=source_family,
                    passed=bool(wall_or_outrigger_count >= 1 and int(element_mix_counts.get("shell_beam_mix", 0)) >= 1),
                    context={
                        "source_family": source_family,
                        "wall_frame_count": int(topology_counts.get("wall-frame", 0)),
                        "outrigger_count": int(topology_counts.get("outrigger", 0)),
                        "shell_beam_mix_count": int(element_mix_counts.get("shell_beam_mix", 0)),
                    },
                ),
            ]
        )
    for benchmark_family, evidence in sorted(supplemental_family_evidence.get("concrete_damage", {}).items()):
        rows.append(
            _bool_row(
                row_id=f"concrete_damage:benchmark_family:{_slug(benchmark_family)}:rc_lock",
                family="concrete_damage",
                source=str(evidence.get("source", "rc_benchmark_lock_report")),
                metric=str(evidence.get("metric", "benchmark_family_lock")),
                value=benchmark_family,
                passed=bool(evidence.get("passed", False)),
                context={
                    "benchmark_family": benchmark_family,
                    "case_count": int(evidence.get("case_count", 0) or 0),
                    "case_ids": sorted({str(case_id) for case_id in evidence.get("case_ids", []) if str(case_id)}),
                    "metric_names": sorted(
                        {str(metric_name) for metric_name in evidence.get("metric_names", set()) if str(metric_name)}
                    ),
                },
            )
        )

    for row in ndtha_cyclic_rows:
        rows.append(
            _bool_row(
                row_id=f"cyclic_degradation:ndtha:{row['case_id']}",
                family="cyclic_degradation",
                source="nonlinear_ndtha_stress_report",
                metric="residual_drift_ratio_pct",
                value=row["residual_drift_ratio_pct"],
                passed=bool(abs(float(row["residual_drift_ratio_pct"])) > 0.0),
                context={
                    "case_id": row["case_id"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                    "response_storage": row["response_storage"],
                },
            )
        )
    rows.extend(
        [
            _bool_row(
                row_id="cyclic_degradation:gate:dynamic_reversal",
                family="cyclic_degradation",
                source="nonlinear_ndtha_stress_report",
                metric="dynamic_reversal_pass",
                value=bool(ndtha_checks.get("dynamic_reversal_pass", False)),
                passed=bool(ndtha_contract_pass and ndtha_checks.get("dynamic_reversal_pass", False)),
            ),
            _bool_row(
                row_id="cyclic_degradation:gate:plasticity_triggered",
                family="cyclic_degradation",
                source="nonlinear_ndtha_stress_report",
                metric="plasticity_triggered_all_cases",
                value=bool(ndtha_checks.get("plasticity_triggered_all_cases", False)),
                passed=bool(ndtha_contract_pass and ndtha_checks.get("plasticity_triggered_all_cases", False)),
            ),
            _bool_row(
                row_id="cyclic_degradation:gate:residual_metric_sanity",
                family="cyclic_degradation",
                source="nonlinear_ndtha_stress_report",
                metric="residual_metric_sanity_pass",
                value=bool(ndtha_checks.get("residual_metric_sanity_pass", False)),
                passed=bool(ndtha_contract_pass and ndtha_checks.get("residual_metric_sanity_pass", False)),
            ),
            _bool_row(
                row_id="cyclic_degradation:benchmark:rc_cracking_lock",
                family="cyclic_degradation",
                source="rc_benchmark_lock_report",
                metric="cracking_case_pass",
                value=bool(rc_lock_checks.get("cracking_case_pass", False)),
                passed=bool(rc_lock_contract_pass and rc_lock_checks.get("cracking_case_pass", False)),
            ),
            _bool_row(
                row_id="cyclic_degradation:threshold:min_case_coverage",
                family="cyclic_degradation",
                source="material_constitutive_gate",
                metric="min_case_coverage",
                value={
                    "ndtha": len(ndtha_cyclic_rows),
                    "required": int(min_cyclic_rows),
                },
                passed=bool(len(ndtha_cyclic_rows) >= int(min_cyclic_rows)),
            ),
        ]
    )
    cyclic_topologies = _dimension_counter(ndtha_cyclic_rows, "topology_type")
    cyclic_hazards = _dimension_counter(ndtha_cyclic_rows, "hazard_type")
    cyclic_response_storage = _dimension_counter(ndtha_cyclic_rows, "response_storage")
    rows.append(
        _bool_row(
            row_id="cyclic_degradation:coverage:source_balance",
            family="cyclic_degradation",
            source="material_constitutive_gate",
            metric="source_balance",
            value={
                "ndtha_cases": len(ndtha_cyclic_rows),
                "sources_present": ["ndtha"] if ndtha_cyclic_rows else [],
            },
            passed=bool(ndtha_cyclic_rows),
        )
    )
    for topology_type, count in sorted(cyclic_topologies.items()):
        rows.append(
            _bool_row(
                row_id=f"cyclic_degradation:coverage:topology:{_slug(topology_type)}",
                family="cyclic_degradation",
                source="material_constitutive_gate",
                metric="topology_coverage",
                value=topology_type,
                passed=bool(count > 0),
                context={"topology_type": topology_type, "case_count": count},
            )
        )
    for hazard_type, count in sorted(cyclic_hazards.items()):
        rows.append(
            _bool_row(
                row_id=f"cyclic_degradation:coverage:hazard:{_slug(hazard_type)}",
                family="cyclic_degradation",
                source="material_constitutive_gate",
                metric="hazard_coverage",
                value=hazard_type,
                passed=bool(count > 0),
                context={"hazard_type": hazard_type, "case_count": count},
            )
        )
    for response_storage, count in sorted(cyclic_response_storage.items()):
        rows.append(
            _bool_row(
                row_id=f"cyclic_degradation:coverage:response_storage:{_slug(response_storage)}",
                family="cyclic_degradation",
                source="material_constitutive_gate",
                metric="response_storage_coverage",
                value=response_storage,
                passed=bool(count > 0),
                context={"response_storage": response_storage, "case_count": count},
            )
        )
    for source_family, family_payload in sorted(source_family_cases.items()):
        case_count = int(family_payload.get("case_count", 0) or 0)
        topology_counts = family_payload.get("topology_counts") if isinstance(family_payload.get("topology_counts"), dict) else {}
        dynamic_topology_count = sum(int(topology_counts.get(key, 0)) for key in ("rahmen", "wall-frame", "outrigger", "truss"))
        rows.extend(
            [
                _bool_row(
                    row_id=f"cyclic_degradation:source_family:{_slug(source_family)}:case_volume",
                    family="cyclic_degradation",
                    source="commercial_benchmark_cases",
                    metric="source_family_case_volume",
                    value=source_family,
                    passed=bool(case_count >= 2),
                    context={"source_family": source_family, "case_count": case_count},
                ),
                _bool_row(
                    row_id=f"cyclic_degradation:source_family:{_slug(source_family)}:dynamic_topology",
                    family="cyclic_degradation",
                    source="commercial_benchmark_cases",
                    metric="source_family_dynamic_topology",
                    value=source_family,
                    passed=bool(dynamic_topology_count >= 2),
                    context={
                        "source_family": source_family,
                        "dynamic_topology_count": int(dynamic_topology_count),
                        "topology_counts": topology_counts,
                    },
                ),
            ]
        )
    for coverage_family, evidence in sorted(supplemental_family_evidence.get("cyclic_degradation", {}).items()):
        evidence_kind = str(evidence.get("kind", "benchmark_family"))
        suffix = "waveform_lock" if evidence_kind == "authority_source_family" else "rc_lock"
        rows.append(
            _bool_row(
                row_id=f"cyclic_degradation:{evidence_kind}:{_slug(coverage_family)}:{suffix}",
                family="cyclic_degradation",
                source=str(evidence.get("source", "rc_benchmark_lock_report")),
                metric=str(evidence.get("metric", "benchmark_family_lock")),
                value=coverage_family,
                passed=bool(evidence.get("passed", False)),
                context={
                    "coverage_family": coverage_family,
                    "case_count": int(evidence.get("case_count", 0) or 0),
                    "case_ids": sorted({str(case_id) for case_id in evidence.get("case_ids", []) if str(case_id)}),
                    "authority_families": sorted(
                        {str(label) for label in evidence.get("authority_families", set()) if str(label)}
                    ),
                    "manifest_paths": sorted(
                        {str(path) for path in evidence.get("manifest_paths", set()) if str(path)}
                    ),
                    "metric_names": sorted(
                        {str(metric_name) for metric_name in evidence.get("metric_names", set()) if str(metric_name)}
                    ),
                },
            )
        )

    for row in pushover_bond_rows:
        rows.append(
            _bool_row(
                row_id=f"bond_interface:pushover:{row['case_id']}",
                family="bond_interface",
                source="nonlinear_pushover_stress_report",
                metric="bond_slip_index_mean",
                value=row["bond_slip_index_mean"],
                passed=bool(row["bond_slip_index_mean"] > 0.0),
                context={
                    "case_id": row["case_id"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                },
            )
        )
    for row in ndtha_bond_rows:
        rows.append(
            _bool_row(
                row_id=f"bond_interface:ndtha:{row['case_id']}",
                family="bond_interface",
                source="nonlinear_ndtha_stress_report",
                metric="bond_slip_index_mean",
                value=row["bond_slip_index_mean"],
                passed=bool(row["bond_slip_index_mean"] > 0.0),
                context={
                    "case_id": row["case_id"],
                    "topology_type": row["topology_type"],
                    "hazard_type": row["hazard_type"],
                },
            )
        )
    rows.extend(
        [
            _bool_row(
                row_id="bond_interface:gate:pushover_material_model",
                family="bond_interface",
                source="nonlinear_pushover_stress_report",
                metric="material_model_pass",
                value=bool(pushover_checks.get("material_model_pass", False)),
                passed=bool(pushover_contract_pass and pushover_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="bond_interface:gate:ndtha_material_model",
                family="bond_interface",
                source="nonlinear_ndtha_stress_report",
                metric="material_model_pass",
                value=bool(ndtha_checks.get("material_model_pass", False)),
                passed=bool(ndtha_contract_pass and ndtha_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="bond_interface:benchmark:bond_slip_lock",
                family="bond_interface",
                source="rc_benchmark_lock_report",
                metric="bond_slip_case_pass",
                value=bool(rc_lock_checks.get("bond_slip_case_pass", False)),
                passed=bool(rc_lock_contract_pass and rc_lock_checks.get("bond_slip_case_pass", False)),
            ),
            _bool_row(
                row_id="bond_interface:benchmark:construction_continuity",
                family="bond_interface",
                source="construction_sequence_gate_report",
                metric="creep_shrinkage_applied",
                value=bool(construction_checks.get("creep_shrinkage_applied", False)),
                passed=bool(construction_contract_pass and construction_checks.get("creep_shrinkage_applied", False)),
            ),
            _bool_row(
                row_id="bond_interface:threshold:min_case_coverage",
                family="bond_interface",
                source="material_constitutive_gate",
                metric="min_case_coverage",
                value={
                    "pushover": len(pushover_bond_rows),
                    "ndtha": len(ndtha_bond_rows),
                    "required_per_source": int(min_bond_interface_rows),
                },
                passed=bool(
                    len(pushover_bond_rows) >= int(min_bond_interface_rows)
                    and len(ndtha_bond_rows) >= int(min_bond_interface_rows)
                ),
            ),
        ]
    )
    bond_topologies = _dimension_counter(bond_rows, "topology_type")
    bond_hazards = _dimension_counter(bond_rows, "hazard_type")
    rows.append(
        _bool_row(
            row_id="bond_interface:coverage:source_balance",
            family="bond_interface",
            source="material_constitutive_gate",
            metric="source_balance",
            value={
                "pushover_cases": len(pushover_bond_rows),
                "ndtha_cases": len(ndtha_bond_rows),
                "sources_present": [
                    source
                    for source, count in (
                        ("pushover", len(pushover_bond_rows)),
                        ("ndtha", len(ndtha_bond_rows)),
                    )
                    if count > 0
                ],
            },
            passed=bool(pushover_bond_rows and ndtha_bond_rows),
        )
    )
    for topology_type, count in sorted(bond_topologies.items()):
        rows.append(
            _bool_row(
                row_id=f"bond_interface:coverage:topology:{_slug(topology_type)}",
                family="bond_interface",
                source="material_constitutive_gate",
                metric="topology_coverage",
                value=topology_type,
                passed=bool(count > 0),
                context={"topology_type": topology_type, "case_count": count},
            )
        )
    for hazard_type, count in sorted(bond_hazards.items()):
        rows.append(
            _bool_row(
                row_id=f"bond_interface:coverage:hazard:{_slug(hazard_type)}",
                family="bond_interface",
                source="material_constitutive_gate",
                metric="hazard_coverage",
                value=hazard_type,
                passed=bool(count > 0),
                context={"hazard_type": hazard_type, "case_count": count},
            )
        )
    for source_family, family_payload in sorted(source_family_cases.items()):
        case_count = int(family_payload.get("case_count", 0) or 0)
        topology_counts = family_payload.get("topology_counts") if isinstance(family_payload.get("topology_counts"), dict) else {}
        element_mix_counts = family_payload.get("element_mix_counts") if isinstance(family_payload.get("element_mix_counts"), dict) else {}
        rows.extend(
            [
                _bool_row(
                    row_id=f"bond_interface:source_family:{_slug(source_family)}:case_volume",
                    family="bond_interface",
                    source="commercial_benchmark_cases",
                    metric="source_family_case_volume",
                    value=source_family,
                    passed=bool(case_count >= 2),
                    context={"source_family": source_family, "case_count": case_count},
                ),
                _bool_row(
                    row_id=f"bond_interface:source_family:{_slug(source_family)}:shell_mix",
                    family="bond_interface",
                    source="commercial_benchmark_cases",
                    metric="source_family_shell_beam_mix",
                    value=source_family,
                    passed=bool(
                        int(element_mix_counts.get("shell_beam_mix", 0)) >= 1
                        and (int(topology_counts.get("wall-frame", 0)) + int(topology_counts.get("outrigger", 0))) >= 1
                    ),
                    context={
                        "source_family": source_family,
                        "shell_beam_mix_count": int(element_mix_counts.get("shell_beam_mix", 0)),
                        "wall_frame_count": int(topology_counts.get("wall-frame", 0)),
                        "outrigger_count": int(topology_counts.get("outrigger", 0)),
                    },
                ),
            ]
        )
    for benchmark_family, evidence in sorted(supplemental_family_evidence.get("bond_interface", {}).items()):
        rows.append(
            _bool_row(
                row_id=f"bond_interface:benchmark_family:{_slug(benchmark_family)}:rc_lock",
                family="bond_interface",
                source=str(evidence.get("source", "rc_benchmark_lock_report")),
                metric=str(evidence.get("metric", "benchmark_family_lock")),
                value=benchmark_family,
                passed=bool(evidence.get("passed", False)),
                context={
                    "benchmark_family": benchmark_family,
                    "case_count": int(evidence.get("case_count", 0) or 0),
                    "case_ids": sorted({str(case_id) for case_id in evidence.get("case_ids", []) if str(case_id)}),
                    "metric_names": sorted(
                        {str(metric_name) for metric_name in evidence.get("metric_names", set()) if str(metric_name)}
                    ),
                },
            )
        )

    creep_index_mean = _safe_float(construction_summary.get("mean_creep_index"))
    shrinkage_index_mean = _safe_float(construction_summary.get("mean_shrinkage_index"))
    differential_shortening_mm = _safe_float(construction_summary.get("max_differential_shortening_mm"))
    rows.extend(
        [
            _bool_row(
                row_id="creep_shrinkage:gate:construction_sequence_contract",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="construction_sequence_contract",
                value=bool(construction_contract_pass),
                passed=bool(construction_contract_pass),
            ),
            _bool_row(
                row_id="creep_shrinkage:gate:creep_shrinkage_applied",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="creep_shrinkage_applied",
                value=bool(construction_checks.get("creep_shrinkage_applied", False)),
                passed=bool(construction_contract_pass and construction_checks.get("creep_shrinkage_applied", False)),
            ),
            _bool_row(
                row_id="creep_shrinkage:gate:differential_shortening_detected",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="differential_shortening_detected",
                value=bool(construction_checks.get("differential_shortening_detected", False)),
                passed=bool(construction_contract_pass and construction_checks.get("differential_shortening_detected", False)),
            ),
            _bool_row(
                row_id="creep_shrinkage:summary:mean_creep_index",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="mean_creep_index",
                value=creep_index_mean,
                passed=bool(math.isfinite(creep_index_mean) and creep_index_mean > 0.0),
            ),
            _bool_row(
                row_id="creep_shrinkage:summary:mean_shrinkage_index",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="mean_shrinkage_index",
                value=shrinkage_index_mean,
                passed=bool(math.isfinite(shrinkage_index_mean) and shrinkage_index_mean > 0.0),
            ),
            _bool_row(
                row_id="creep_shrinkage:summary:max_differential_shortening_mm",
                family="creep_shrinkage",
                source="construction_sequence_gate_report",
                metric="max_differential_shortening_mm",
                value=differential_shortening_mm,
                passed=bool(math.isfinite(differential_shortening_mm) and differential_shortening_mm > 0.0),
            ),
        ]
    )
    for benchmark_family, evidence in sorted(supplemental_family_evidence.get("creep_shrinkage", {}).items()):
        rows.append(
            _bool_row(
                row_id=f"creep_shrinkage:benchmark_family:{_slug(benchmark_family)}:rc_lock",
                family="creep_shrinkage",
                source=str(evidence.get("source", "rc_benchmark_lock_report")),
                metric=str(evidence.get("metric", "benchmark_family_lock")),
                value=benchmark_family,
                passed=bool(evidence.get("passed", False)),
                context={
                    "benchmark_family": benchmark_family,
                    "case_count": int(evidence.get("case_count", 0) or 0),
                    "case_ids": sorted({str(case_id) for case_id in evidence.get("case_ids", []) if str(case_id)}),
                },
            )
        )

    soil_profile = str(ssi_summary.get("soil_profile", "") or "").strip()
    nonlinear_ratio_span = _safe_float(ssi_summary.get("nonlinear_ratio_span"))
    rows.extend(
        [
            _bool_row(
                row_id="soil_boundary_nonlinear:gate:ssi_contract",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="ssi_contract",
                value=bool(ssi_contract_pass),
                passed=bool(ssi_contract_pass),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:gate:ssi_nonlinear_boundary_active",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="ssi_nonlinear_boundary_active",
                value=bool(ssi_checks.get("ssi_nonlinear_boundary_active", False)),
                passed=bool(ssi_contract_pass and ssi_checks.get("ssi_nonlinear_boundary_active", False)),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:gate:ssi_transfer_finite",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="ssi_transfer_finite",
                value=bool(ssi_checks.get("ssi_transfer_finite", False)),
                passed=bool(ssi_contract_pass and ssi_checks.get("ssi_transfer_finite", False)),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:gate:residual_trace_pass",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="residual_trace_pass",
                value=bool(ssi_checks.get("residual_trace_pass", False)),
                passed=bool(ssi_contract_pass and ssi_checks.get("residual_trace_pass", False)),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:gate:material_model_pass",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="material_model_pass",
                value=bool(ssi_checks.get("material_model_pass", False)),
                passed=bool(ssi_contract_pass and ssi_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:summary:soil_profile",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="soil_profile",
                value=soil_profile or "n/a",
                passed=bool(soil_profile),
            ),
            _bool_row(
                row_id="soil_boundary_nonlinear:summary:nonlinear_ratio_span",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="nonlinear_ratio_span",
                value=nonlinear_ratio_span,
                passed=bool(math.isfinite(nonlinear_ratio_span) and nonlinear_ratio_span > 0.0),
            ),
        ]
    )
    for topology_type, count in sorted(_dimension_counter(ssi_rows, "topology_type").items()):
        rows.append(
            _bool_row(
                row_id=f"soil_boundary_nonlinear:coverage:topology:{_slug(topology_type)}",
                family="soil_boundary_nonlinear",
                source="ssi_boundary_gate_report",
                metric="topology_coverage",
                value=topology_type,
                passed=bool(count > 0),
                context={"topology_type": topology_type, "case_count": count},
            )
        )

    damper_types = [str(item).strip() for item in (damper_summary.get("damper_types") or []) if str(item).strip()]
    waveform_corr_min = _safe_float(damper_summary.get("waveform_corr_min"))
    residual_drift_mm_max = _safe_float(damper_summary.get("residual_drift_mm_max"))
    rows.extend(
        [
            _bool_row(
                row_id="device_dissipation:gate:damper_contract",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="damper_contract",
                value=bool(damper_contract_pass),
                passed=bool(damper_contract_pass),
            ),
            _bool_row(
                row_id="device_dissipation:gate:damper_type_diversity_pass",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="damper_type_diversity_pass",
                value=bool(damper_checks.get("damper_type_diversity_pass", False)),
                passed=bool(damper_contract_pass and damper_checks.get("damper_type_diversity_pass", False)),
            ),
            _bool_row(
                row_id="device_dissipation:gate:waveform_corr_pass",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="waveform_corr_pass",
                value=bool(damper_checks.get("waveform_corr_pass", False)),
                passed=bool(damper_contract_pass and damper_checks.get("waveform_corr_pass", False)),
            ),
            _bool_row(
                row_id="device_dissipation:gate:residual_drift_pass",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="residual_drift_pass",
                value=bool(damper_checks.get("residual_drift_pass", False)),
                passed=bool(damper_contract_pass and damper_checks.get("residual_drift_pass", False)),
            ),
            _bool_row(
                row_id="device_dissipation:gate:material_model_pass",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="material_model_pass",
                value=bool(damper_checks.get("material_model_pass", False)),
                passed=bool(damper_contract_pass and damper_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="device_dissipation:summary:waveform_corr_min",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="waveform_corr_min",
                value=waveform_corr_min,
                passed=bool(math.isfinite(waveform_corr_min) and waveform_corr_min > 0.0),
            ),
            _bool_row(
                row_id="device_dissipation:summary:residual_drift_mm_max",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="residual_drift_mm_max",
                value=residual_drift_mm_max,
                passed=bool(math.isfinite(residual_drift_mm_max) and residual_drift_mm_max >= 0.0),
            ),
        ]
    )
    for damper_type in damper_types:
        rows.append(
            _bool_row(
                row_id=f"device_dissipation:damper_type:{_slug(damper_type)}",
                family="device_dissipation",
                source="damper_validation_gate_report",
                metric="damper_type_coverage",
                value=damper_type,
                passed=True,
                context={"damper_type": damper_type},
            )
        )

    foundation_member_type_count = int(foundation_summary.get("foundation_member_type_count", 0) or 0)
    optimized_foundation_group_count = int(foundation_summary.get("optimized_foundation_group_count", 0) or 0)
    soil_link_contract_tokens = [
        str(item).strip() for item in (foundation_summary.get("soil_link_contract_tokens") or []) if str(item).strip()
    ]
    foundation_link_model_types = [
        str(item).strip() for item in (foundation_summary.get("foundation_link_model_types") or []) if str(item).strip()
    ]
    rows.extend(
        [
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:foundation_contract",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_contract",
                value=bool(foundation_contract_pass),
                passed=bool(foundation_contract_pass),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:foundation_scope_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_scope_ready",
                value=bool(foundation_checks.get("foundation_scope_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("foundation_scope_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:foundation_artifact_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_artifact_ready",
                value=bool(foundation_checks.get("foundation_artifact_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("foundation_artifact_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:ssi_boundary_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="ssi_boundary_ready",
                value=bool(foundation_checks.get("ssi_boundary_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("ssi_boundary_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:soil_tunnel_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="soil_tunnel_ready",
                value=bool(foundation_checks.get("soil_tunnel_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("soil_tunnel_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:impedance_schema_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="impedance_schema_ready",
                value=bool(foundation_checks.get("impedance_schema_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("impedance_schema_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:gate:foundation_link_models_ready",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_link_models_ready",
                value=bool(foundation_checks.get("foundation_link_models_ready", False)),
                passed=bool(foundation_contract_pass and foundation_checks.get("foundation_link_models_ready", False)),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:summary:foundation_member_type_count",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_member_type_count",
                value=foundation_member_type_count,
                passed=bool(foundation_member_type_count > 0),
            ),
            _bool_row(
                row_id="foundation_impedance_nonlinear:summary:optimized_foundation_group_count",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="optimized_foundation_group_count",
                value=optimized_foundation_group_count,
                passed=bool(optimized_foundation_group_count > 0),
            ),
        ]
    )
    for token in soil_link_contract_tokens:
        rows.append(
            _bool_row(
                row_id=f"foundation_impedance_nonlinear:soil_link_token:{_slug(token)}",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="soil_link_contract_token",
                value=token,
                passed=True,
                context={"soil_link_contract_token": token},
            )
        )
    for link_model in foundation_link_model_types:
        rows.append(
            _bool_row(
                row_id=f"foundation_impedance_nonlinear:link_model:{_slug(link_model)}",
                family="foundation_impedance_nonlinear",
                source="foundation_soil_link_gate_report",
                metric="foundation_link_model_type",
                value=link_model,
                passed=True,
                context={"foundation_link_model_type": link_model},
            )
        )

    contact_validated_category_count = int(contact_summary.get("validated_category_count", 0) or 0)
    contact_required_category_count = int(contact_summary.get("required_category_count", 0) or 0)
    contact_event_sequence_mismatch = int(contact_summary.get("contact_uplift_event_sequence_mismatch", 0) or 0)
    contact_link_model_types = [
        str(item).strip() for item in (contact_summary.get("link_model_types") or []) if str(item).strip()
    ]
    rows.extend(
        [
            _bool_row(
                row_id="contact_link_hysteresis:gate:contact_contract",
                family="contact_link_hysteresis",
                source="structural_contact_validation_report",
                metric="contact_contract",
                value=bool(contact_contract_pass),
                passed=bool(contact_contract_pass),
            ),
            _bool_row(
                row_id="contact_link_hysteresis:summary:validated_category_count",
                family="contact_link_hysteresis",
                source="structural_contact_validation_report",
                metric="validated_category_count",
                value=contact_validated_category_count,
                passed=bool(contact_validated_category_count >= max(contact_required_category_count, 1)),
            ),
            _bool_row(
                row_id="contact_link_hysteresis:summary:event_sequence_mismatch",
                family="contact_link_hysteresis",
                source="structural_contact_validation_report",
                metric="contact_uplift_event_sequence_mismatch",
                value=contact_event_sequence_mismatch,
                passed=bool(contact_event_sequence_mismatch == 0),
            ),
        ]
    )
    for category_name, category_payload in sorted(contact_categories.items()):
        category_dict = category_payload if isinstance(category_payload, dict) else {}
        category_checks = category_dict.get("checks") if isinstance(category_dict.get("checks"), dict) else {}
        rows.append(
            _bool_row(
                row_id=f"contact_link_hysteresis:category:{_slug(category_name)}",
                family="contact_link_hysteresis",
                source="structural_contact_validation_report",
                metric="validated_category",
                value=category_name,
                passed=bool(
                    category_dict.get("validated", False)
                    and (not category_checks or all(bool(value) for value in category_checks.values()))
                ),
                context={
                    "category": category_name,
                    "link_name": str(category_dict.get("link_name", "") or ""),
                },
            )
        )
    for link_model in contact_link_model_types:
        rows.append(
            _bool_row(
                row_id=f"contact_link_hysteresis:link_model:{_slug(link_model)}",
                family="contact_link_hysteresis",
                source="structural_contact_validation_report",
                metric="link_model_type",
                value=link_model,
                passed=True,
                context={"link_model_type": link_model},
            )
        )

    panel_zone_surface = _panel_zone_joint_response_surface(
        panel_zone_contract_pass,
        panel_zone_checks,
        panel_zone_summary,
    )
    panel_zone_row_count = int(panel_zone_surface.get("row_count", 0) or 0)
    panel_zone_source_valid_row_counts = panel_zone_summary.get("panel_zone_source_valid_row_counts")
    if not isinstance(panel_zone_source_valid_row_counts, dict):
        panel_zone_source_valid_row_counts = {}
    rows.extend(
        [
            _bool_row(
                row_id="panel_zone_joint_response:gate:panel_zone_contract",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_contract",
                value=bool(panel_zone_contract_pass),
                passed=bool(panel_zone_contract_pass),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:artifact_contract_pass",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_clash_artifact_contract_pass",
                value=bool(panel_zone_checks.get("panel_zone_clash_artifact_contract_pass", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_checks.get("panel_zone_clash_artifact_contract_pass", False)),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:topology_capable_input",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_topology_capable_input",
                value=bool(panel_zone_checks.get("panel_zone_topology_capable_input", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_checks.get("panel_zone_topology_capable_input", False)),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:required_sources_complete",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_required_sources_complete",
                value=bool(panel_zone_checks.get("panel_zone_required_sources_complete", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_checks.get("panel_zone_required_sources_complete", False)),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:topology_projected_bridge_complete",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_bridge_complete",
                value=bool(panel_zone_surface.get("bridge_complete", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_surface.get("bridge_complete", False)),
                context={
                    "bridge_mode": str(panel_zone_surface.get("bridge_mode", "") or ""),
                    "source_contract_mode": str(panel_zone_surface.get("source_contract_mode", "") or ""),
                    "topology_projected_bridge_complete": bool(
                        panel_zone_surface.get("topology_projected_bridge_complete", False)
                    ),
                    "true_3d_bridge_complete": bool(panel_zone_surface.get("true_3d_bridge_complete", False)),
                    "solver_verified_bridge_complete": bool(
                        panel_zone_surface.get("solver_verified_bridge_complete", False)
                    ),
                },
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:internal_engine_complete",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_joint_material_evidence_complete",
                value=bool(panel_zone_surface.get("material_evidence_complete", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_surface.get("material_evidence_complete", False)),
                context={
                    "material_evidence_mode": str(panel_zone_surface.get("material_evidence_mode", "") or ""),
                    "source_contract_mode": str(panel_zone_surface.get("source_contract_mode", "") or ""),
                    "internal_engine_complete": bool(panel_zone_surface.get("internal_engine_complete", False)),
                    "true_3d_clash_verified": bool(panel_zone_surface.get("true_3d_clash_verified", False)),
                    "true_3d_anchorage_verified": bool(panel_zone_surface.get("true_3d_anchorage_verified", False)),
                    "external_validation_artifact_closed": bool(
                        panel_zone_surface.get("external_validation_artifact_closed", False)
                    ),
                    "exact_verified_complete": bool(panel_zone_surface.get("exact_verified_complete", False)),
                },
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:dataset_contract_pass",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="dataset_contract_pass",
                value=bool(panel_zone_checks.get("dataset_contract_pass", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_checks.get("dataset_contract_pass", False)),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:gate:pbd_contract_pass",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="pbd_contract_pass",
                value=bool(panel_zone_checks.get("pbd_contract_pass", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_checks.get("pbd_contract_pass", False)),
            ),
            _bool_row(
                row_id="panel_zone_joint_response:summary:panel_zone_clash_row_count",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="panel_zone_clash_row_count",
                value=panel_zone_row_count,
                passed=bool(panel_zone_row_count > 0),
            ),
        ]
    )
    for source_name, valid_row_count in sorted(panel_zone_source_valid_row_counts.items()):
        rows.append(
            _bool_row(
                row_id=f"panel_zone_joint_response:source_valid_rows:{_slug(source_name)}",
                family="panel_zone_joint_response",
                source="panel_zone_clash_report",
                metric="source_valid_row_count",
                value=source_name,
                passed=bool(int(valid_row_count or 0) > 0),
                context={"source_name": source_name, "valid_row_count": int(valid_row_count or 0)},
            )
        )

    wind_duration_hours = _safe_float(wind_summary.get("duration_hours"))
    wind_load_reversal_count = int(wind_summary.get("load_reversal_count", 0) or 0)
    wind_section_family_coverage_min = _safe_float(wind_summary.get("section_family_coverage_min"))
    wind_response_storage = str(wind_summary.get("response_storage", "") or "").strip()
    wind_material_model_types = [
        str(item).strip() for item in (wind_summary.get("material_model_types") or []) if str(item).strip()
    ]
    rows.extend(
        [
            _bool_row(
                row_id="wind_dynamic_response:gate:wind_contract",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="wind_contract",
                value=bool(wind_contract_pass),
                passed=bool(wind_contract_pass),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:wind_duration_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="wind_duration_pass",
                value=bool(wind_checks.get("wind_duration_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("wind_duration_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:wind_reversal_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="wind_reversal_pass",
                value=bool(wind_checks.get("wind_reversal_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("wind_reversal_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:long_series_chunked_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="long_series_chunked_pass",
                value=bool(wind_checks.get("long_series_chunked_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("long_series_chunked_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:material_model_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="material_model_pass",
                value=bool(wind_checks.get("material_model_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("material_model_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:residual_trace_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="residual_trace_pass",
                value=bool(wind_checks.get("residual_trace_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("residual_trace_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:gate:device_artifacts_consumed_pass",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="device_artifacts_consumed_pass",
                value=bool(wind_checks.get("device_artifacts_consumed_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("device_artifacts_consumed_pass", False)),
            ),
            _bool_row(
                row_id="wind_dynamic_response:summary:duration_hours",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="duration_hours",
                value=wind_duration_hours,
                passed=bool(math.isfinite(wind_duration_hours) and wind_duration_hours > 0.0),
            ),
            _bool_row(
                row_id="wind_dynamic_response:summary:load_reversal_count",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="load_reversal_count",
                value=wind_load_reversal_count,
                passed=bool(wind_load_reversal_count > 0),
            ),
            _bool_row(
                row_id="wind_dynamic_response:summary:section_family_coverage_min",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="section_family_coverage_min",
                value=wind_section_family_coverage_min,
                passed=bool(math.isfinite(wind_section_family_coverage_min) and wind_section_family_coverage_min > 0.0),
            ),
            _bool_row(
                row_id="wind_dynamic_response:summary:response_storage",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="response_storage",
                value=wind_response_storage or "n/a",
                passed=bool(wind_response_storage),
            ),
        ]
    )
    for material_model in wind_material_model_types:
        rows.append(
            _bool_row(
                row_id=f"wind_dynamic_response:material_model:{_slug(material_model)}",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="material_model_type",
                value=material_model,
                passed=True,
                context={"material_model_type": material_model},
            )
        )
    for topology_type, count in sorted(_dimension_counter(wind_rows, "topology_type").items()):
        rows.append(
            _bool_row(
                row_id=f"wind_dynamic_response:coverage:topology:{_slug(topology_type)}",
                family="wind_dynamic_response",
                source="wind_time_history_gate_report",
                metric="topology_coverage",
                value=topology_type,
                passed=bool(count > 0),
                context={"topology_type": topology_type, "case_count": count},
            )
        )

    vibration_distance_count = int(vibration_attenuation_metrics.get("distance_count", 0) or 0)
    vibration_sample_count = int(vibration_compliance_metrics.get("sample_count", 0) or 0)
    track_node_count = int(track_irregularity_metrics.get("node_count", 0) or 0)
    track_profile_class = str(track_irregularity_metrics.get("class", "") or "").strip()
    track_backend = str(track_irregularity_metrics.get("preprocess_backend", "") or "").strip()
    track_response_storage = str(track_lf_summary.get("response_storage", "") or "").strip()
    track_response_consumer = str(track_lf_summary.get("response_binary_consumer", "") or "").strip()
    track_dataset_max_residual = _safe_float(track_dataset_metrics.get("max_equilibrium_residual"))
    tunnel_dataset_max_residual = _safe_float(tunnel_dataset_metrics.get("max_equilibrium_residual"))
    vti_mean_coupling_iters = _safe_float(vti_coupled_metrics.get("mean_coupling_iters"))
    moving_load_energy_balance_error = _safe_float(moving_load_metrics.get("energy_balance_relative_error"))
    moving_load_max_acceleration = _safe_float(moving_load_metrics.get("max_acceleration_mps2"))
    vibration_pass_ratio = _safe_float(vibration_compliance_metrics.get("pass_ratio"))
    vibration_max_velocity = _safe_float(vibration_compliance_metrics.get("max_velocity_mm_s"))
    attenuation_far_field_ratio = _safe_float(vibration_attenuation_metrics.get("far_field_ratio_63_to_8"))

    rows.extend(
        [
            _bool_row(
                row_id="track_support_viscoelasticity:gate:track_lf_contract",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="track_lf_contract",
                value=bool(track_lf_contract_pass),
                passed=bool(track_lf_contract_pass),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:gate:accuracy_pass",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="accuracy_pass",
                value=bool(track_lf_checks.get("accuracy_pass", False)),
                passed=bool(track_lf_contract_pass and track_lf_checks.get("accuracy_pass", False)),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:gate:rust_kernel_used",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="rust_kernel_used",
                value=bool(track_lf_checks.get("rust_kernel_used", False)),
                passed=bool(track_lf_contract_pass and track_lf_checks.get("rust_kernel_used", False)),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:gate:o_n_operator",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="o_n_operator",
                value=bool(track_lf_checks.get("o_n_operator", False)),
                passed=bool(track_lf_contract_pass and track_lf_checks.get("o_n_operator", False)),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:gate:matrix_free_euler",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="matrix_free_euler",
                value=bool(track_lf_checks.get("matrix_free_euler", False)),
                passed=bool(track_lf_contract_pass and track_lf_checks.get("matrix_free_euler", False)),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:summary:track_irregularity_contract",
                family="track_support_viscoelasticity",
                source="track_irregularity_report",
                metric="track_irregularity_contract",
                value=bool(track_irregularity_metrics),
                passed=bool(track_irregularity_metrics),
            ),
            _bool_row(
                row_id="track_support_viscoelasticity:summary:track_node_count",
                family="track_support_viscoelasticity",
                source="track_irregularity_report",
                metric="track_node_count",
                value=track_node_count,
                passed=bool(track_node_count > 0),
            ),
            _bool_row(
                row_id=f"track_support_viscoelasticity:coverage:irregularity_class:{_slug(track_profile_class or 'unknown')}",
                family="track_support_viscoelasticity",
                source="track_irregularity_report",
                metric="irregularity_class",
                value=track_profile_class or "unknown",
                passed=bool(track_profile_class),
            ),
            _bool_row(
                row_id=f"track_support_viscoelasticity:coverage:preprocess_backend:{_slug(track_backend or 'unknown')}",
                family="track_support_viscoelasticity",
                source="track_irregularity_report",
                metric="preprocess_backend",
                value=track_backend or "unknown",
                passed=bool(track_backend),
            ),
            _bool_row(
                row_id=f"track_support_viscoelasticity:coverage:response_storage:{_slug(track_response_storage or 'unknown')}",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="response_storage",
                value=track_response_storage or "unknown",
                passed=bool(track_response_storage),
            ),
            _bool_row(
                row_id=f"track_support_viscoelasticity:coverage:response_consumer:{_slug(track_response_consumer or 'unknown')}",
                family="track_support_viscoelasticity",
                source="track_lf_solver_report",
                metric="response_binary_consumer",
                value=track_response_consumer or "unknown",
                passed=bool(track_response_consumer),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:moving_load_contract",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="moving_load_contract",
                value=bool(moving_load_contract_pass),
                passed=bool(moving_load_contract_pass),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:finite_response",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="finite_response",
                value=bool(moving_load_checks.get("finite_response", False)),
                passed=bool(moving_load_contract_pass and moving_load_checks.get("finite_response", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:non_divergent_response",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="non_divergent_response",
                value=bool(moving_load_checks.get("non_divergent_response", False)),
                passed=bool(moving_load_contract_pass and moving_load_checks.get("non_divergent_response", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:linear_solver_converged",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="linear_solver_converged",
                value=bool(moving_load_checks.get("linear_solver_converged", False)),
                passed=bool(moving_load_contract_pass and moving_load_checks.get("linear_solver_converged", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:equilibrium_residual_pass",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="equilibrium_residual_pass",
                value=bool(moving_load_checks.get("equilibrium_residual_pass", False)),
                passed=bool(moving_load_contract_pass and moving_load_checks.get("equilibrium_residual_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:energy_balance_pass",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="energy_balance_pass",
                value=bool(moving_load_checks.get("energy_balance_pass", False)),
                passed=bool(moving_load_contract_pass and moving_load_checks.get("energy_balance_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:vti_contract",
                family="vehicle_track_transient_coupling",
                source="vti_coupled_solver_report",
                metric="vti_contract",
                value=bool(vti_coupled_contract_pass),
                passed=bool(vti_coupled_contract_pass),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:coupling_converged_ratio_pass",
                family="vehicle_track_transient_coupling",
                source="vti_coupled_solver_report",
                metric="coupling_converged_ratio_pass",
                value=bool(vti_coupled_checks.get("coupling_converged_ratio_pass", False)),
                passed=bool(vti_coupled_contract_pass and vti_coupled_checks.get("coupling_converged_ratio_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:dynamic_disp_pass",
                family="vehicle_track_transient_coupling",
                source="vti_coupled_solver_report",
                metric="dynamic_disp_pass",
                value=bool(vti_coupled_checks.get("dynamic_disp_pass", False)),
                passed=bool(vti_coupled_contract_pass and vti_coupled_checks.get("dynamic_disp_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:adaptive_newton_converged_pass",
                family="vehicle_track_transient_coupling",
                source="vti_coupled_solver_report",
                metric="adaptive_newton_converged_pass",
                value=bool(vti_coupled_checks.get("adaptive_newton_converged_pass", False)),
                passed=bool(vti_coupled_contract_pass and vti_coupled_checks.get("adaptive_newton_converged_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:track_dataset_contract",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="track_dataset_contract",
                value=bool(track_dataset_contract_pass),
                passed=bool(track_dataset_contract_pass),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:dataset_nonempty",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="dataset_nonempty",
                value=bool(track_dataset_checks.get("dataset_nonempty", False)),
                passed=bool(track_dataset_contract_pass and track_dataset_checks.get("dataset_nonempty", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:split_has_val_test",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="split_has_val_test",
                value=bool(track_dataset_checks.get("split_has_val_test", False)),
                passed=bool(track_dataset_contract_pass and track_dataset_checks.get("split_has_val_test", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:dataset_finite_response",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="finite_response",
                value=bool(track_dataset_checks.get("finite_response", False)),
                passed=bool(track_dataset_contract_pass and track_dataset_checks.get("finite_response", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:gate:dataset_equilibrium_residual_pass",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="equilibrium_residual_pass",
                value=bool(track_dataset_checks.get("equilibrium_residual_pass", False)),
                passed=bool(track_dataset_contract_pass and track_dataset_checks.get("equilibrium_residual_pass", False)),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:summary:mean_coupling_iters",
                family="vehicle_track_transient_coupling",
                source="vti_coupled_solver_report",
                metric="mean_coupling_iters",
                value=vti_mean_coupling_iters,
                passed=bool(math.isfinite(vti_mean_coupling_iters) and vti_mean_coupling_iters > 0.0),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:summary:energy_balance_relative_error",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="energy_balance_relative_error",
                value=moving_load_energy_balance_error,
                passed=bool(math.isfinite(moving_load_energy_balance_error) and moving_load_energy_balance_error <= 0.05),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:summary:max_acceleration_mps2",
                family="vehicle_track_transient_coupling",
                source="moving_load_integrator_report",
                metric="max_acceleration_mps2",
                value=moving_load_max_acceleration,
                passed=bool(math.isfinite(moving_load_max_acceleration) and moving_load_max_acceleration > 0.0),
            ),
            _bool_row(
                row_id="vehicle_track_transient_coupling:summary:dataset_max_equilibrium_residual",
                family="vehicle_track_transient_coupling",
                source="track_dynamics_dataset_report",
                metric="max_equilibrium_residual",
                value=track_dataset_max_residual,
                passed=bool(math.isfinite(track_dataset_max_residual) and track_dataset_max_residual < 1.0),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:vibration_attenuation_contract",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="vibration_attenuation_contract",
                value=bool(vibration_attenuation_contract_pass),
                passed=bool(vibration_attenuation_contract_pass),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:substructuring_linked",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="substructuring_linked",
                value=bool(vibration_attenuation_checks.get("substructuring_linked", False)),
                passed=bool(vibration_attenuation_contract_pass and vibration_attenuation_checks.get("substructuring_linked", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:finite_values",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="finite_values",
                value=bool(vibration_attenuation_checks.get("finite_values", False)),
                passed=bool(vibration_attenuation_contract_pass and vibration_attenuation_checks.get("finite_values", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:monotonic_distance_decay",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="monotonic_distance_decay",
                value=bool(vibration_attenuation_checks.get("monotonic_distance_decay", False)),
                passed=bool(vibration_attenuation_contract_pass and vibration_attenuation_checks.get("monotonic_distance_decay", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:high_frequency_decay_stronger",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="high_frequency_decay_stronger",
                value=bool(vibration_attenuation_checks.get("high_frequency_decay_stronger", False)),
                passed=bool(vibration_attenuation_contract_pass and vibration_attenuation_checks.get("high_frequency_decay_stronger", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:tunnel_dataset_contract",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="tunnel_dataset_contract",
                value=bool(tunnel_dataset_contract_pass),
                passed=bool(tunnel_dataset_contract_pass),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:tunnel_dataset_nonempty",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="dataset_nonempty",
                value=bool(tunnel_dataset_checks.get("dataset_nonempty", False)),
                passed=bool(tunnel_dataset_contract_pass and tunnel_dataset_checks.get("dataset_nonempty", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:tunnel_dataset_split_has_val_test",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="split_has_val_test",
                value=bool(tunnel_dataset_checks.get("split_has_val_test", False)),
                passed=bool(tunnel_dataset_contract_pass and tunnel_dataset_checks.get("split_has_val_test", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:tunnel_dataset_finite_response",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="finite_response",
                value=bool(tunnel_dataset_checks.get("finite_response", False)),
                passed=bool(tunnel_dataset_contract_pass and tunnel_dataset_checks.get("finite_response", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:gate:tunnel_dataset_equilibrium_residual_pass",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="equilibrium_residual_pass",
                value=bool(tunnel_dataset_checks.get("equilibrium_residual_pass", False)),
                passed=bool(tunnel_dataset_contract_pass and tunnel_dataset_checks.get("equilibrium_residual_pass", False)),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:summary:distance_count",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="distance_count",
                value=vibration_distance_count,
                passed=bool(vibration_distance_count >= 1),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:summary:far_field_ratio_63_to_8",
                family="tunnel_soil_wave_attenuation",
                source="vibration_attenuation_report",
                metric="far_field_ratio_63_to_8",
                value=attenuation_far_field_ratio,
                passed=bool(math.isfinite(attenuation_far_field_ratio) and attenuation_far_field_ratio >= 0.0),
            ),
            _bool_row(
                row_id="tunnel_soil_wave_attenuation:summary:tunnel_dataset_max_equilibrium_residual",
                family="tunnel_soil_wave_attenuation",
                source="tunnel_dynamics_dataset_report",
                metric="max_equilibrium_residual",
                value=tunnel_dataset_max_residual,
                passed=bool(math.isfinite(tunnel_dataset_max_residual) and tunnel_dataset_max_residual < 1.0),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:gate:vibration_compliance_contract",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="vibration_compliance_contract",
                value=bool(vibration_compliance_contract_pass),
                passed=bool(vibration_compliance_contract_pass),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:gate:standard_supported",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="standard_supported",
                value=bool(vibration_compliance_checks.get("standard_supported", False)),
                passed=bool(vibration_compliance_contract_pass and vibration_compliance_checks.get("standard_supported", False)),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:gate:finite_values",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="finite_values",
                value=bool(vibration_compliance_checks.get("finite_values", False)),
                passed=bool(vibration_compliance_contract_pass and vibration_compliance_checks.get("finite_values", False)),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:gate:compliance_ratio_pass",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="compliance_ratio_pass",
                value=bool(vibration_compliance_checks.get("compliance_ratio_pass", False)),
                passed=bool(vibration_compliance_contract_pass and vibration_compliance_checks.get("compliance_ratio_pass", False)),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:summary:sample_count",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="sample_count",
                value=vibration_sample_count,
                passed=bool(vibration_sample_count > 0),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:summary:pass_ratio",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="pass_ratio",
                value=vibration_pass_ratio,
                passed=bool(math.isfinite(vibration_pass_ratio) and vibration_pass_ratio >= 0.95),
            ),
            _bool_row(
                row_id="serviceability_velocity_response:summary:max_velocity_mm_s",
                family="serviceability_velocity_response",
                source="vibration_compliance_report",
                metric="max_velocity_mm_s",
                value=vibration_max_velocity,
                passed=bool(math.isfinite(vibration_max_velocity) and vibration_max_velocity > 0.0),
            ),
            _bool_row(
                row_id=f"serviceability_velocity_response:coverage:irregularity_class:{_slug(track_profile_class or 'unknown')}",
                family="serviceability_velocity_response",
                source="track_irregularity_report",
                metric="irregularity_class",
                value=track_profile_class or "unknown",
                passed=bool(track_profile_class),
            ),
        ]
    )

    construction_stage_count = int(construction_summary.get("stage_count", 0) or 0)
    joint_constraint_transfer_evidence = _joint_constraint_transfer_panel_zone_evidence(
        panel_zone_checks=panel_zone_checks,
        panel_zone_summary=panel_zone_summary,
    )
    panel_zone_source_row_count = int(joint_constraint_transfer_evidence["source_row_count"])
    rows.extend(
        [
            _bool_row(
                row_id="construction_stage_redistribution:gate:construction_contract",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="construction_contract",
                value=bool(construction_contract_pass),
                passed=bool(construction_contract_pass),
            ),
            _bool_row(
                row_id="construction_stage_redistribution:gate:creep_shrinkage_applied",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="creep_shrinkage_applied",
                value=bool(construction_checks.get("creep_shrinkage_applied", False)),
                passed=bool(construction_contract_pass and construction_checks.get("creep_shrinkage_applied", False)),
            ),
            _bool_row(
                row_id="construction_stage_redistribution:gate:differential_shortening_detected",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="differential_shortening_detected",
                value=bool(construction_checks.get("differential_shortening_detected", False)),
                passed=bool(construction_contract_pass and construction_checks.get("differential_shortening_detected", False)),
            ),
            _bool_row(
                row_id="construction_stage_redistribution:summary:mean_creep_index",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="mean_creep_index",
                value=_safe_float(construction_summary.get("mean_creep_index")),
                passed=bool(math.isfinite(_safe_float(construction_summary.get("mean_creep_index")))),
            ),
            _bool_row(
                row_id="construction_stage_redistribution:summary:mean_shrinkage_index",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="mean_shrinkage_index",
                value=_safe_float(construction_summary.get("mean_shrinkage_index")),
                passed=bool(math.isfinite(_safe_float(construction_summary.get("mean_shrinkage_index")))),
            ),
            _bool_row(
                row_id="construction_stage_redistribution:summary:stage_count",
                family="construction_stage_redistribution",
                source="construction_sequence_report",
                metric="stage_count",
                value=construction_stage_count,
                passed=bool(construction_stage_count >= 0),
            ),
            _bool_row(
                row_id="joint_constraint_transfer:gate:panel_zone_contract",
                family="joint_constraint_transfer",
                source="panel_zone_clash_report",
                metric="panel_zone_contract",
                value=bool(panel_zone_contract_pass),
                passed=bool(panel_zone_contract_pass),
            ),
            _bool_row(
                row_id="joint_constraint_transfer:gate:topology_projected_bridge_complete",
                family="joint_constraint_transfer",
                source="panel_zone_clash_report",
                metric="panel_zone_topology_projected_bridge_complete",
                value=bool(joint_constraint_transfer_evidence["topology_projected_bridge_complete"]),
                passed=bool(panel_zone_contract_pass and joint_constraint_transfer_evidence["topology_projected_bridge_complete"]),
            ),
            _bool_row(
                row_id="joint_constraint_transfer:gate:internal_engine_complete",
                family="joint_constraint_transfer",
                source="panel_zone_clash_report",
                metric="panel_zone_internal_engine_complete",
                value=bool(joint_constraint_transfer_evidence["internal_engine_complete"]),
                passed=bool(panel_zone_contract_pass and joint_constraint_transfer_evidence["internal_engine_complete"]),
            ),
            _bool_row(
                row_id="joint_constraint_transfer:summary:validated_source_row_count_total",
                family="joint_constraint_transfer",
                source="panel_zone_clash_report",
                metric="validated_source_row_count_total",
                value=panel_zone_source_row_count,
                passed=bool(panel_zone_source_row_count > 0),
            ),
            _bool_row(
                row_id="joint_constraint_transfer:summary:required_sources_complete",
                family="joint_constraint_transfer",
                source="panel_zone_clash_report",
                metric="panel_zone_required_sources_complete",
                value=bool(joint_constraint_transfer_evidence["required_sources_complete"]),
                passed=bool(panel_zone_contract_pass and joint_constraint_transfer_evidence["required_sources_complete"]),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:gate:wind_contract",
                family="aeroelastic_serviceability",
                source="wind_time_history_gate_report",
                metric="wind_contract",
                value=bool(wind_contract_pass),
                passed=bool(wind_contract_pass),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:gate:vibration_compliance_contract",
                family="aeroelastic_serviceability",
                source="vibration_compliance_report",
                metric="vibration_compliance_contract",
                value=bool(vibration_compliance_contract_pass),
                passed=bool(vibration_compliance_contract_pass),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:gate:wind_duration_pass",
                family="aeroelastic_serviceability",
                source="wind_time_history_gate_report",
                metric="wind_duration_pass",
                value=bool(wind_checks.get("wind_duration_pass", False)),
                passed=bool(wind_contract_pass and wind_checks.get("wind_duration_pass", False)),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:gate:standard_supported",
                family="aeroelastic_serviceability",
                source="vibration_compliance_report",
                metric="standard_supported",
                value=bool(vibration_compliance_checks.get("standard_supported", False)),
                passed=bool(vibration_compliance_contract_pass and vibration_compliance_checks.get("standard_supported", False)),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:gate:compliance_ratio_pass",
                family="aeroelastic_serviceability",
                source="vibration_compliance_report",
                metric="compliance_ratio_pass",
                value=bool(vibration_compliance_checks.get("compliance_ratio_pass", False)),
                passed=bool(vibration_compliance_contract_pass and vibration_compliance_checks.get("compliance_ratio_pass", False)),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:summary:duration_hours",
                family="aeroelastic_serviceability",
                source="wind_time_history_gate_report",
                metric="duration_hours",
                value=wind_duration_hours,
                passed=bool(math.isfinite(wind_duration_hours) and wind_duration_hours > 0.0),
            ),
            _bool_row(
                row_id="aeroelastic_serviceability:summary:pass_ratio",
                family="aeroelastic_serviceability",
                source="vibration_compliance_report",
                metric="pass_ratio",
                value=vibration_pass_ratio,
                passed=bool(math.isfinite(vibration_pass_ratio) and vibration_pass_ratio >= 0.95),
            ),
            _bool_row(
                row_id="heterogeneous_soil_adaptation:gate:ood_contract",
                family="heterogeneous_soil_adaptation",
                source="heterogeneous_soil_ood_report",
                metric="ood_contract",
                value=bool(heterogeneous_soil_contract_pass),
                passed=bool(heterogeneous_soil_contract_pass),
            ),
            _bool_row(
                row_id="heterogeneous_soil_adaptation:gate:ood_recall_pass",
                family="heterogeneous_soil_adaptation",
                source="heterogeneous_soil_ood_report",
                metric="ood_recall_pass",
                value=bool(heterogeneous_soil_checks.get("ood_recall_pass", False)),
                passed=bool(heterogeneous_soil_contract_pass and heterogeneous_soil_checks.get("ood_recall_pass", False)),
            ),
            _bool_row(
                row_id="heterogeneous_soil_adaptation:gate:false_negative_gate_pass",
                family="heterogeneous_soil_adaptation",
                source="heterogeneous_soil_ood_report",
                metric="false_negative_gate_pass",
                value=bool(heterogeneous_soil_checks.get("false_negative_gate_pass", False)),
                passed=bool(heterogeneous_soil_contract_pass and heterogeneous_soil_checks.get("false_negative_gate_pass", False)),
            ),
            _bool_row(
                row_id="heterogeneous_soil_adaptation:gate:fallback_route_on_ood_pass",
                family="heterogeneous_soil_adaptation",
                source="heterogeneous_soil_ood_report",
                metric="fallback_route_on_ood_pass",
                value=bool(heterogeneous_soil_checks.get("fallback_route_on_ood_pass", False)),
                passed=bool(heterogeneous_soil_contract_pass and heterogeneous_soil_checks.get("fallback_route_on_ood_pass", False)),
            ),
            _bool_row(
                row_id="heterogeneous_soil_adaptation:summary:md_uncertainty_corr",
                family="heterogeneous_soil_adaptation",
                source="heterogeneous_soil_ood_report",
                metric="md_uncertainty_corr",
                value=_safe_float(heterogeneous_soil_metrics.get("md_uncertainty_corr")),
                passed=bool(heterogeneous_soil_contract_pass and heterogeneous_soil_checks.get("uncertainty_calibrated", False)),
            ),
            _bool_row(
                row_id="segment_joint_softening:gate:segment_joint_contract",
                family="segment_joint_softening",
                source="tunnel_segment_joint_report",
                metric="segment_joint_contract",
                value=bool(segment_joint_contract_pass),
                passed=bool(segment_joint_contract_pass),
            ),
            _bool_row(
                row_id="segment_joint_softening:gate:yield_detected",
                family="segment_joint_softening",
                source="tunnel_segment_joint_report",
                metric="yield_detected",
                value=bool(segment_joint_checks.get("yield_detected", False)),
                passed=bool(segment_joint_contract_pass and segment_joint_checks.get("yield_detected", False)),
            ),
            _bool_row(
                row_id="segment_joint_softening:gate:post_yield_softening_pass",
                family="segment_joint_softening",
                source="tunnel_segment_joint_report",
                metric="post_yield_softening_pass",
                value=bool(segment_joint_checks.get("post_yield_softening_pass", False)),
                passed=bool(segment_joint_contract_pass and segment_joint_checks.get("post_yield_softening_pass", False)),
            ),
            _bool_row(
                row_id="segment_joint_softening:gate:energy_dissipation_pass",
                family="segment_joint_softening",
                source="tunnel_segment_joint_report",
                metric="energy_dissipation_pass",
                value=bool(segment_joint_checks.get("energy_dissipation_pass", False)),
                passed=bool(segment_joint_contract_pass and segment_joint_checks.get("energy_dissipation_pass", False)),
            ),
            _bool_row(
                row_id="segment_joint_softening:summary:dissipated_energy_like",
                family="segment_joint_softening",
                source="tunnel_segment_joint_report",
                metric="dissipated_energy_like",
                value=_safe_float(segment_joint_metrics.get("dissipated_energy_like")),
                passed=bool(_safe_float(segment_joint_metrics.get("dissipated_energy_like")) > 0.0),
            ),
            _bool_row(
                row_id="longitudinal_wave_strain_transfer:gate:tunnel_longitudinal_contract",
                family="longitudinal_wave_strain_transfer",
                source="tunnel_seismic_longitudinal_report",
                metric="tunnel_longitudinal_contract",
                value=bool(tunnel_longitudinal_contract_pass),
                passed=bool(tunnel_longitudinal_contract_pass),
            ),
            _bool_row(
                row_id="longitudinal_wave_strain_transfer:gate:finite_response",
                family="longitudinal_wave_strain_transfer",
                source="tunnel_seismic_longitudinal_report",
                metric="finite_response",
                value=bool(tunnel_longitudinal_checks.get("finite_response", False)),
                passed=bool(tunnel_longitudinal_contract_pass and tunnel_longitudinal_checks.get("finite_response", False)),
            ),
            _bool_row(
                row_id="longitudinal_wave_strain_transfer:gate:displacement_limit_pass",
                family="longitudinal_wave_strain_transfer",
                source="tunnel_seismic_longitudinal_report",
                metric="displacement_limit_pass",
                value=bool(tunnel_longitudinal_checks.get("displacement_limit_pass", False)),
                passed=bool(tunnel_longitudinal_contract_pass and tunnel_longitudinal_checks.get("displacement_limit_pass", False)),
            ),
            _bool_row(
                row_id="longitudinal_wave_strain_transfer:gate:strain_limit_pass",
                family="longitudinal_wave_strain_transfer",
                source="tunnel_seismic_longitudinal_report",
                metric="strain_limit_pass",
                value=bool(tunnel_longitudinal_checks.get("strain_limit_pass", False)),
                passed=bool(tunnel_longitudinal_contract_pass and tunnel_longitudinal_checks.get("strain_limit_pass", False)),
            ),
            _bool_row(
                row_id="longitudinal_wave_strain_transfer:summary:max_longitudinal_strain",
                family="longitudinal_wave_strain_transfer",
                source="tunnel_seismic_longitudinal_report",
                metric="max_longitudinal_strain",
                value=_safe_float(tunnel_longitudinal_metrics.get("max_longitudinal_strain")),
                passed=bool(math.isfinite(_safe_float(tunnel_longitudinal_metrics.get("max_longitudinal_strain")))),
            ),
            _bool_row(
                row_id="raw_pressure_field_mapping:gate:wind_tunnel_mapping_contract",
                family="raw_pressure_field_mapping",
                source="wind_tunnel_raw_mapping_report",
                metric="wind_tunnel_mapping_contract",
                value=bool(wind_tunnel_mapping_contract_pass),
                passed=bool(wind_tunnel_mapping_contract_pass),
            ),
            _bool_row(
                row_id="raw_pressure_field_mapping:gate:raw_wind_data_exists",
                family="raw_pressure_field_mapping",
                source="wind_tunnel_raw_mapping_report",
                metric="raw_wind_data_exists",
                value=bool(wind_tunnel_mapping_checks.get("raw_wind_data_exists", False)),
                passed=bool(wind_tunnel_mapping_contract_pass and wind_tunnel_mapping_checks.get("raw_wind_data_exists", False)),
            ),
            _bool_row(
                row_id="raw_pressure_field_mapping:gate:raw_wind_manifest_verified",
                family="raw_pressure_field_mapping",
                source="wind_tunnel_raw_mapping_report",
                metric="raw_wind_manifest_verified",
                value=bool(wind_tunnel_mapping_checks.get("raw_wind_manifest_verified", False)),
                passed=bool(wind_tunnel_mapping_contract_pass and wind_tunnel_mapping_checks.get("raw_wind_manifest_verified", False)),
            ),
            _bool_row(
                row_id="raw_pressure_field_mapping:gate:midas_traceability_ready",
                family="raw_pressure_field_mapping",
                source="wind_tunnel_raw_mapping_report",
                metric="midas_traceability_ready",
                value=bool(wind_tunnel_mapping_checks.get("midas_traceability_ready", False)),
                passed=bool(wind_tunnel_mapping_contract_pass and wind_tunnel_mapping_checks.get("midas_traceability_ready", False)),
            ),
            _bool_row(
                row_id="raw_pressure_field_mapping:summary:mapping_row_count",
                family="raw_pressure_field_mapping",
                source="wind_tunnel_raw_mapping_report",
                metric="mapping_row_count",
                value=int(wind_tunnel_mapping_summary.get("mapping_row_count", 0) or 0),
                passed=bool(int(wind_tunnel_mapping_summary.get("mapping_row_count", 0) or 0) > 0),
            ),
            _bool_row(
                row_id="phase_assimilation_correction:gate:phase_correction_contract",
                family="phase_assimilation_correction",
                source="phase_correction_assimilation_report",
                metric="phase_correction_contract",
                value=bool(phase_correction_contract_pass),
                passed=bool(phase_correction_contract_pass),
            ),
            _bool_row(
                row_id="phase_assimilation_correction:gate:phase_error_improved",
                family="phase_assimilation_correction",
                source="phase_correction_assimilation_report",
                metric="phase_error_improved",
                value=bool(phase_correction_checks.get("phase_error_improved", False)),
                passed=bool(phase_correction_contract_pass and phase_correction_checks.get("phase_error_improved", False)),
            ),
            _bool_row(
                row_id="phase_assimilation_correction:gate:phase_error_below_threshold",
                family="phase_assimilation_correction",
                source="phase_correction_assimilation_report",
                metric="phase_error_below_threshold",
                value=bool(phase_correction_checks.get("phase_error_below_threshold", False)),
                passed=bool(phase_correction_contract_pass and phase_correction_checks.get("phase_error_below_threshold", False)),
            ),
            _bool_row(
                row_id="phase_assimilation_correction:gate:time_lag_below_threshold",
                family="phase_assimilation_correction",
                source="phase_correction_assimilation_report",
                metric="time_lag_below_threshold",
                value=bool(phase_correction_checks.get("time_lag_below_threshold", False)),
                passed=bool(phase_correction_contract_pass and phase_correction_checks.get("time_lag_below_threshold", False)),
            ),
            _bool_row(
                row_id="phase_assimilation_correction:summary:phase_error_reduction_ratio",
                family="phase_assimilation_correction",
                source="phase_correction_assimilation_report",
                metric="phase_error_reduction_ratio",
                value=_safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")),
                passed=bool(
                    phase_correction_contract_pass
                    and phase_correction_checks.get("amplitude_error_not_degraded", False)
                    and math.isfinite(_safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")))
                    and _safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")) >= 0.9
                ),
            ),
            _bool_row(
                row_id="multiscale_streaming_refinement:gate:streaming_contract",
                family="multiscale_streaming_refinement",
                source="multiscale_l3_streaming_report",
                metric="streaming_contract",
                value=bool(multiscale_streaming_contract_pass),
                passed=bool(multiscale_streaming_contract_pass),
            ),
            _bool_row(
                row_id="multiscale_streaming_refinement:gate:high_frequency_target",
                family="multiscale_streaming_refinement",
                source="multiscale_l3_streaming_report",
                metric="high_frequency_target",
                value=bool(multiscale_streaming_checks.get("high_frequency_target", False)),
                passed=bool(multiscale_streaming_contract_pass and multiscale_streaming_checks.get("high_frequency_target", False)),
            ),
            _bool_row(
                row_id="multiscale_streaming_refinement:gate:windowed_o_n_streaming",
                family="multiscale_streaming_refinement",
                source="multiscale_l3_streaming_report",
                metric="windowed_o_n_streaming",
                value=bool(multiscale_streaming_checks.get("windowed_o_n_streaming", False)),
                passed=bool(multiscale_streaming_contract_pass and multiscale_streaming_checks.get("windowed_o_n_streaming", False)),
            ),
            _bool_row(
                row_id="multiscale_streaming_refinement:gate:near_field_refined",
                family="multiscale_streaming_refinement",
                source="multiscale_l3_streaming_report",
                metric="near_field_refined",
                value=bool(multiscale_streaming_checks.get("near_field_refined", False)),
                passed=bool(multiscale_streaming_contract_pass and multiscale_streaming_checks.get("near_field_refined", False)),
            ),
            _bool_row(
                row_id="multiscale_streaming_refinement:summary:recommended_chunk",
                family="multiscale_streaming_refinement",
                source="multiscale_l3_streaming_report",
                metric="recommended_chunk",
                value=int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0),
                passed=bool(
                    multiscale_streaming_contract_pass
                    and multiscale_streaming_checks.get("has_cache_safe_chunk", False)
                    and int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0) > 0
                ),
            ),
            _bool_row(
                row_id="integrated_vibration_transfer:gate:phasee_integrated_contract",
                family="integrated_vibration_transfer",
                source="phasee_integrated_summary_report",
                metric="phasee_integrated_contract",
                value=bool(phasee_integrated_contract_pass),
                passed=bool(phasee_integrated_contract_pass),
            ),
            _bool_row(
                row_id="integrated_vibration_transfer:gate:substructuring_interface",
                family="integrated_vibration_transfer",
                source="phasee_integrated_summary_report",
                metric="substructuring_interface",
                value=bool(phasee_integrated_checks.get("E1_substructuring_interface", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E1_substructuring_interface", False)),
            ),
            _bool_row(
                row_id="integrated_vibration_transfer:gate:vibration_attenuation_model",
                family="integrated_vibration_transfer",
                source="phasee_integrated_summary_report",
                metric="vibration_attenuation_model",
                value=bool(phasee_integrated_checks.get("E2_vibration_attenuation_model", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E2_vibration_attenuation_model", False)),
            ),
            _bool_row(
                row_id="integrated_vibration_transfer:gate:vibration_compliance_checker",
                family="integrated_vibration_transfer",
                source="phasee_integrated_summary_report",
                metric="vibration_compliance_checker",
                value=bool(phasee_integrated_checks.get("E3_vibration_compliance_checker", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E3_vibration_compliance_checker", False)),
            ),
            _bool_row(
                row_id="integrated_vibration_transfer:summary:whitebox_validation_extension",
                family="integrated_vibration_transfer",
                source="phasee_integrated_summary_report",
                metric="whitebox_validation_extension",
                value=bool(phasee_integrated_checks.get("E5_whitebox_validation_extension", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E5_whitebox_validation_extension", False)),
            ),
            _bool_row(
                row_id="resilience_ood_recovery:gate:phasef_resilience_contract",
                family="resilience_ood_recovery",
                source="phasef_resilience_summary_report",
                metric="phasef_resilience_contract",
                value=bool(phasef_resilience_contract_pass),
                passed=bool(phasef_resilience_contract_pass),
            ),
            _bool_row(
                row_id="resilience_ood_recovery:gate:multiscale_l3_streaming",
                family="resilience_ood_recovery",
                source="phasef_resilience_summary_report",
                metric="multiscale_l3_streaming",
                value=bool(phasef_resilience_checks.get("F1_multiscale_l3_streaming", False)),
                passed=bool(phasef_resilience_contract_pass and phasef_resilience_checks.get("F1_multiscale_l3_streaming", False)),
            ),
            _bool_row(
                row_id="resilience_ood_recovery:gate:phase_correction_assimilation",
                family="resilience_ood_recovery",
                source="phasef_resilience_summary_report",
                metric="phase_correction_assimilation",
                value=bool(phasef_resilience_checks.get("F2_phase_correction_assimilation", False)),
                passed=bool(phasef_resilience_contract_pass and phasef_resilience_checks.get("F2_phase_correction_assimilation", False)),
            ),
            _bool_row(
                row_id="resilience_ood_recovery:gate:heterogeneous_soil_ood_gate",
                family="resilience_ood_recovery",
                source="phasef_resilience_summary_report",
                metric="heterogeneous_soil_ood_gate",
                value=bool(phasef_resilience_checks.get("F3_heterogeneous_soil_ood_gate", False)),
                passed=bool(phasef_resilience_contract_pass and phasef_resilience_checks.get("F3_heterogeneous_soil_ood_gate", False)),
            ),
            _bool_row(
                row_id="resilience_ood_recovery:summary:step_count",
                family="resilience_ood_recovery",
                source="phasef_resilience_summary_report",
                metric="step_count",
                value=int(phasef_resilience_step_count),
                passed=bool(phasef_resilience_contract_pass and int(phasef_resilience_step_count) >= 3),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:gate:dynamics_boundary_contract",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="dynamics_boundary_contract",
                value=bool(dynamics_boundary_contract_pass),
                passed=bool(dynamics_boundary_contract_pass),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:gate:support_types_present",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="support_types_present",
                value=int(len(dynamics_boundary_supports_summary.get("support_types") or [])),
                passed=bool(dynamics_boundary_contract_pass and len(dynamics_boundary_supports_summary.get("support_types") or []) > 0),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:gate:fixed_boundary_present",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="fixed_boundary_present",
                value=int(dynamics_boundary_supports_summary.get("fixed_count", 0) or 0),
                passed=bool(dynamics_boundary_contract_pass and int(dynamics_boundary_supports_summary.get("fixed_count", 0) or 0) > 0),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:gate:damping_model_present",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="damping_model_present",
                value=str(dynamics_boundary_damping_summary.get("damping_model", "") or ""),
                passed=bool(dynamics_boundary_contract_pass and str(dynamics_boundary_damping_summary.get("damping_model", "") or "").strip()),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:gate:time_step_positive",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="time_step_positive",
                value=_safe_float(dynamics_boundary_damping_summary.get("time_step_dt")),
                passed=bool(dynamics_boundary_contract_pass and _safe_float(dynamics_boundary_damping_summary.get("time_step_dt")) > 0.0),
            ),
            _bool_row(
                row_id="boundary_absorption_nonlinear:summary:rayleigh_pair_finite",
                family="boundary_absorption_nonlinear",
                source="dynamics_boundary_report",
                metric="rayleigh_pair_finite",
                value=f"alpha={_safe_float(dynamics_boundary_damping_summary.get('alpha_m')):.3f},beta={_safe_float(dynamics_boundary_damping_summary.get('beta_k')):.3f}",
                passed=bool(
                    dynamics_boundary_contract_pass
                    and math.isfinite(_safe_float(dynamics_boundary_damping_summary.get("alpha_m")))
                    and math.isfinite(_safe_float(dynamics_boundary_damping_summary.get("beta_k")))
                ),
            ),
            _bool_row(
                row_id="attention_load_localization:gate:moving_load_attention_contract",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="moving_load_attention_contract",
                value=bool(moving_load_attention_contract_pass),
                passed=bool(moving_load_attention_contract_pass),
            ),
            _bool_row(
                row_id="attention_load_localization:gate:peak_centered",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="peak_centered",
                value=bool(moving_load_attention_checks.get("peak_centered", False)),
                passed=bool(moving_load_attention_contract_pass and moving_load_attention_checks.get("peak_centered", False)),
            ),
            _bool_row(
                row_id="attention_load_localization:gate:shape_monotonic",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="shape_monotonic",
                value=bool(moving_load_attention_checks.get("shape_monotonic", False)),
                passed=bool(moving_load_attention_contract_pass and moving_load_attention_checks.get("shape_monotonic", False)),
            ),
            _bool_row(
                row_id="attention_load_localization:gate:speed_scaling_monotonic",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="speed_scaling_monotonic",
                value=bool(moving_load_attention_checks.get("speed_scaling_monotonic", False)),
                passed=bool(moving_load_attention_contract_pass and moving_load_attention_checks.get("speed_scaling_monotonic", False)),
            ),
            _bool_row(
                row_id="attention_load_localization:gate:support_window_expanded",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="support_window_expanded",
                value=f"{int(moving_load_attention_metrics.get('support_low_count', 0) or 0)}->{int(moving_load_attention_metrics.get('support_high_count', 0) or 0)}",
                passed=bool(
                    moving_load_attention_contract_pass
                    and int(moving_load_attention_metrics.get("support_high_count", 0) or 0)
                    >= int(moving_load_attention_metrics.get("support_low_count", 0) or 0)
                ),
            ),
            _bool_row(
                row_id="attention_load_localization:summary:peak_value",
                family="attention_load_localization",
                source="moving_load_attention_report",
                metric="peak_value",
                value=_safe_float(moving_load_attention_metrics.get("peak_value")),
                passed=bool(moving_load_attention_contract_pass and _safe_float(moving_load_attention_metrics.get("peak_value")) > 0.0),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:gate:physics_residual_contract",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="physics_residual_contract",
                value=bool(physics_residual_contract_pass),
                passed=bool(physics_residual_contract_pass),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:gate:eq_ok",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="eq_ok",
                value=bool(physics_residual_checks.get("eq_ok", False)),
                passed=bool(physics_residual_contract_pass and physics_residual_checks.get("eq_ok", False)),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:gate:boundary_ok",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="boundary_ok",
                value=bool(physics_residual_checks.get("boundary_ok", False)),
                passed=bool(physics_residual_contract_pass and physics_residual_checks.get("boundary_ok", False)),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:gate:damping_ok",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="damping_ok",
                value=bool(physics_residual_checks.get("damping_ok", False)),
                passed=bool(physics_residual_contract_pass and physics_residual_checks.get("damping_ok", False)),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:gate:energy_monotonicity_pass",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="energy_monotonicity_pass",
                value=bool(physics_residual_checks.get("energy_monotonicity_pass", False)),
                passed=bool(physics_residual_contract_pass and physics_residual_checks.get("energy_monotonicity_pass", False)),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:summary:residual_reduction",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="residual_reduction",
                value=_safe_float(physics_residual_metrics.get("residual_norm_before")) - _safe_float(physics_residual_metrics.get("residual_norm_after")),
                passed=bool(
                    physics_residual_contract_pass
                    and _safe_float(physics_residual_metrics.get("residual_norm_after"))
                    <= _safe_float(physics_residual_metrics.get("residual_norm_before"))
                ),
            ),
            _bool_row(
                row_id="residual_energy_stabilization:summary:solver_present",
                family="residual_energy_stabilization",
                source="physics_residual_contract_report",
                metric="solver_present",
                value=str(physics_residual_metrics.get("solver", "") or ""),
                passed=bool(physics_residual_contract_pass and str(physics_residual_metrics.get("solver", "") or "").strip()),
            ),
            _bool_row(
                row_id="phase_latency_projection:gate:phase_correction_contract",
                family="phase_latency_projection",
                source="phase_correction_assimilation_report",
                metric="phase_correction_contract",
                value=bool(phase_correction_contract_pass),
                passed=bool(phase_correction_contract_pass),
            ),
            _bool_row(
                row_id="phase_latency_projection:gate:time_lag_below_threshold",
                family="phase_latency_projection",
                source="phase_correction_assimilation_report",
                metric="time_lag_below_threshold",
                value=bool(phase_correction_checks.get("time_lag_below_threshold", False)),
                passed=bool(phase_correction_contract_pass and phase_correction_checks.get("time_lag_below_threshold", False)),
            ),
            _bool_row(
                row_id="phase_latency_projection:gate:phase_error_improved",
                family="phase_latency_projection",
                source="phase_correction_assimilation_report",
                metric="phase_error_improved",
                value=bool(phase_correction_checks.get("phase_error_improved", False)),
                passed=bool(phase_correction_contract_pass and phase_correction_checks.get("phase_error_improved", False)),
            ),
            _bool_row(
                row_id="phase_latency_projection:summary:phase_error_reduction_ratio",
                family="phase_latency_projection",
                source="phase_correction_assimilation_report",
                metric="phase_error_reduction_ratio",
                value=_safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")),
                passed=bool(phase_correction_contract_pass and _safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")) >= 0.9),
            ),
            _bool_row(
                row_id="phase_latency_projection:summary:post_phase_error_deg",
                family="phase_latency_projection",
                source="phase_correction_assimilation_report",
                metric="post_phase_error_deg",
                value=_safe_float(phase_correction_metrics.get("post_phase_error_deg")),
                passed=bool(phase_correction_contract_pass and math.isfinite(_safe_float(phase_correction_metrics.get("post_phase_error_deg")))),
            ),
            _bool_row(
                row_id="cache_window_adaptation:gate:multiscale_streaming_contract",
                family="cache_window_adaptation",
                source="multiscale_l3_streaming_report",
                metric="multiscale_streaming_contract",
                value=bool(multiscale_streaming_contract_pass),
                passed=bool(multiscale_streaming_contract_pass),
            ),
            _bool_row(
                row_id="cache_window_adaptation:gate:windowed_o_n_streaming",
                family="cache_window_adaptation",
                source="multiscale_l3_streaming_report",
                metric="windowed_o_n_streaming",
                value=bool(multiscale_streaming_checks.get("windowed_o_n_streaming", False)),
                passed=bool(multiscale_streaming_contract_pass and multiscale_streaming_checks.get("windowed_o_n_streaming", False)),
            ),
            _bool_row(
                row_id="cache_window_adaptation:gate:has_cache_safe_chunk",
                family="cache_window_adaptation",
                source="multiscale_l3_streaming_report",
                metric="has_cache_safe_chunk",
                value=bool(multiscale_streaming_checks.get("has_cache_safe_chunk", False)),
                passed=bool(multiscale_streaming_contract_pass and multiscale_streaming_checks.get("has_cache_safe_chunk", False)),
            ),
            _bool_row(
                row_id="cache_window_adaptation:summary:recommended_chunk",
                family="cache_window_adaptation",
                source="multiscale_l3_streaming_report",
                metric="recommended_chunk",
                value=int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0),
                passed=bool(multiscale_streaming_contract_pass and int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0) > 0),
            ),
            _bool_row(
                row_id="cache_window_adaptation:summary:active_nodes_window",
                family="cache_window_adaptation",
                source="multiscale_l3_streaming_report",
                metric="active_nodes_window",
                value=int(multiscale_streaming_metrics.get("active_nodes_window", 0) or 0),
                passed=bool(multiscale_streaming_contract_pass and int(multiscale_streaming_metrics.get("active_nodes_window", 0) or 0) > 0),
            ),
            _bool_row(
                row_id="whitebox_feedback_stitching:gate:phasee_integrated_contract",
                family="whitebox_feedback_stitching",
                source="phasee_integrated_summary_report",
                metric="phasee_integrated_contract",
                value=bool(phasee_integrated_contract_pass),
                passed=bool(phasee_integrated_contract_pass),
            ),
            _bool_row(
                row_id="whitebox_feedback_stitching:gate:substructuring_interface",
                family="whitebox_feedback_stitching",
                source="phasee_integrated_summary_report",
                metric="substructuring_interface",
                value=bool(phasee_integrated_checks.get("E1_substructuring_interface", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E1_substructuring_interface", False)),
            ),
            _bool_row(
                row_id="whitebox_feedback_stitching:gate:vibration_compliance_checker",
                family="whitebox_feedback_stitching",
                source="phasee_integrated_summary_report",
                metric="vibration_compliance_checker",
                value=bool(phasee_integrated_checks.get("E3_vibration_compliance_checker", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E3_vibration_compliance_checker", False)),
            ),
            _bool_row(
                row_id="whitebox_feedback_stitching:gate:whitebox_validation_extension",
                family="whitebox_feedback_stitching",
                source="phasee_integrated_summary_report",
                metric="whitebox_validation_extension",
                value=bool(phasee_integrated_checks.get("E5_whitebox_validation_extension", False)),
                passed=bool(phasee_integrated_contract_pass and phasee_integrated_checks.get("E5_whitebox_validation_extension", False)),
            ),
            _bool_row(
                row_id="whitebox_feedback_stitching:summary:linked_check_count",
                family="whitebox_feedback_stitching",
                source="phasee_integrated_summary_report",
                metric="linked_check_count",
                value=int(sum(1 for key in ("E1_substructuring_interface", "E3_vibration_compliance_checker", "E5_whitebox_validation_extension") if bool(phasee_integrated_checks.get(key, False)))),
                passed=bool(phasee_integrated_contract_pass and sum(1 for key in ("E1_substructuring_interface", "E3_vibration_compliance_checker", "E5_whitebox_validation_extension") if bool(phasee_integrated_checks.get(key, False))) >= 3),
            ),
            _bool_row(
                row_id="recovery_residual_relock:gate:phasef_resilience_contract",
                family="recovery_residual_relock",
                source="phasef_resilience_summary_report",
                metric="phasef_resilience_contract",
                value=bool(phasef_resilience_contract_pass),
                passed=bool(phasef_resilience_contract_pass),
            ),
            _bool_row(
                row_id="recovery_residual_relock:gate:physics_residual_contract",
                family="recovery_residual_relock",
                source="physics_residual_contract_report",
                metric="physics_residual_contract",
                value=bool(physics_residual_contract_pass),
                passed=bool(physics_residual_contract_pass),
            ),
            _bool_row(
                row_id="recovery_residual_relock:gate:phase_correction_assimilation",
                family="recovery_residual_relock",
                source="phasef_resilience_summary_report",
                metric="phase_correction_assimilation",
                value=bool(phasef_resilience_checks.get("F2_phase_correction_assimilation", False)),
                passed=bool(phasef_resilience_contract_pass and phasef_resilience_checks.get("F2_phase_correction_assimilation", False)),
            ),
            _bool_row(
                row_id="recovery_residual_relock:summary:residual_reduction",
                family="recovery_residual_relock",
                source="physics_residual_contract_report",
                metric="residual_reduction",
                value=_safe_float(physics_residual_metrics.get("residual_norm_before")) - _safe_float(physics_residual_metrics.get("residual_norm_after")),
                passed=bool(physics_residual_contract_pass and _safe_float(physics_residual_metrics.get("residual_norm_after")) <= _safe_float(physics_residual_metrics.get("residual_norm_before"))),
            ),
            _bool_row(
                row_id="recovery_residual_relock:summary:node_count",
                family="recovery_residual_relock",
                source="physics_residual_contract_report",
                metric="node_count",
                value=int(physics_residual_metrics.get("node_count", 0) or 0),
                passed=bool(physics_residual_contract_pass and int(physics_residual_metrics.get("node_count", 0) or 0) > 0),
            ),
            _bool_row(
                row_id="rail_support_contact_modulation:gate:track_lf_contract",
                family="rail_support_contact_modulation",
                source="track_lf_solver_report",
                metric="track_lf_contract",
                value=bool(track_lf_contract_pass),
                passed=bool(track_lf_contract_pass),
            ),
            _bool_row(
                row_id="rail_support_contact_modulation:gate:moving_load_attention_contract",
                family="rail_support_contact_modulation",
                source="moving_load_attention_report",
                metric="moving_load_attention_contract",
                value=bool(moving_load_attention_contract_pass),
                passed=bool(moving_load_attention_contract_pass),
            ),
            _bool_row(
                row_id="rail_support_contact_modulation:gate:attention_peak_centered",
                family="rail_support_contact_modulation",
                source="moving_load_attention_report",
                metric="peak_centered",
                value=bool(moving_load_attention_checks.get("peak_centered", False)),
                passed=bool(moving_load_attention_contract_pass and moving_load_attention_checks.get("peak_centered", False)),
            ),
            _bool_row(
                row_id="rail_support_contact_modulation:gate:track_solver_accuracy",
                family="rail_support_contact_modulation",
                source="track_lf_solver_report",
                metric="accuracy_pass",
                value=bool(track_lf_checks.get("accuracy_pass", False)),
                passed=bool(track_lf_contract_pass and track_lf_checks.get("accuracy_pass", False)),
            ),
            _bool_row(
                row_id="rail_support_contact_modulation:summary:support_window_class",
                family="rail_support_contact_modulation",
                source="track_irregularity_report",
                metric="support_window_class",
                value=str(track_irregularity_metrics.get("class", "") or ""),
                passed=bool(str(track_irregularity_metrics.get("class", "") or "").strip()),
            ),
            _bool_row(
                row_id="tunnel_lining_interface_recovery:gate:segment_joint_contract",
                family="tunnel_lining_interface_recovery",
                source="tunnel_segment_joint_report",
                metric="segment_joint_contract",
                value=bool(segment_joint_contract_pass),
                passed=bool(segment_joint_contract_pass),
            ),
            _bool_row(
                row_id="tunnel_lining_interface_recovery:gate:tunnel_longitudinal_contract",
                family="tunnel_lining_interface_recovery",
                source="tunnel_seismic_longitudinal_report",
                metric="tunnel_longitudinal_contract",
                value=bool(tunnel_longitudinal_contract_pass),
                passed=bool(tunnel_longitudinal_contract_pass),
            ),
            _bool_row(
                row_id="tunnel_lining_interface_recovery:gate:heterogeneous_soil_contract",
                family="tunnel_lining_interface_recovery",
                source="heterogeneous_soil_ood_report",
                metric="heterogeneous_soil_contract",
                value=bool(heterogeneous_soil_contract_pass),
                passed=bool(heterogeneous_soil_contract_pass),
            ),
            _bool_row(
                row_id="tunnel_lining_interface_recovery:gate:energy_dissipation_pass",
                family="tunnel_lining_interface_recovery",
                source="tunnel_segment_joint_report",
                metric="energy_dissipation_pass",
                value=bool(segment_joint_checks.get("energy_dissipation_pass", False)),
                passed=bool(segment_joint_contract_pass and segment_joint_checks.get("energy_dissipation_pass", False)),
            ),
            _bool_row(
                row_id="tunnel_lining_interface_recovery:summary:strain_limit_pass",
                family="tunnel_lining_interface_recovery",
                source="tunnel_seismic_longitudinal_report",
                metric="strain_limit_pass",
                value=bool(tunnel_longitudinal_checks.get("strain_limit_pass", False)),
                passed=bool(tunnel_longitudinal_contract_pass and tunnel_longitudinal_checks.get("strain_limit_pass", False)),
            ),
            _bool_row(
                row_id="panel_feedback_residual_transfer:gate:panel_zone_contract",
                family="panel_feedback_residual_transfer",
                source="panel_zone_clash_report",
                metric="panel_zone_contract",
                value=bool(panel_zone_contract_pass),
                passed=bool(panel_zone_contract_pass),
            ),
            _bool_row(
                row_id="panel_feedback_residual_transfer:gate:phasee_integrated_contract",
                family="panel_feedback_residual_transfer",
                source="phasee_integrated_summary_report",
                metric="phasee_integrated_contract",
                value=bool(phasee_integrated_contract_pass),
                passed=bool(phasee_integrated_contract_pass),
            ),
            _bool_row(
                row_id="panel_feedback_residual_transfer:gate:physics_residual_contract",
                family="panel_feedback_residual_transfer",
                source="physics_residual_contract_report",
                metric="physics_residual_contract",
                value=bool(physics_residual_contract_pass),
                passed=bool(physics_residual_contract_pass),
            ),
            _bool_row(
                row_id="panel_feedback_residual_transfer:gate:feedback_bridge_complete",
                family="panel_feedback_residual_transfer",
                source="panel_zone_clash_report",
                metric="panel_feedback_bridge_complete",
                value=bool(panel_zone_surface.get("bridge_complete", False)),
                passed=bool(panel_zone_contract_pass and panel_zone_surface.get("bridge_complete", False)),
                context={
                    "bridge_mode": str(panel_zone_surface.get("bridge_mode", "") or ""),
                    "source_contract_mode": str(panel_zone_surface.get("source_contract_mode", "") or ""),
                    "topology_projected_bridge_complete": bool(
                        panel_zone_surface.get("topology_projected_bridge_complete", False)
                    ),
                    "true_3d_bridge_complete": bool(panel_zone_surface.get("true_3d_bridge_complete", False)),
                    "solver_verified_bridge_complete": bool(
                        panel_zone_surface.get("solver_verified_bridge_complete", False)
                    ),
                },
            ),
            _bool_row(
                row_id="panel_feedback_residual_transfer:summary:residual_reduction",
                family="panel_feedback_residual_transfer",
                source="physics_residual_contract_report",
                metric="residual_reduction",
                value=_safe_float(physics_residual_metrics.get("residual_norm_before")) - _safe_float(physics_residual_metrics.get("residual_norm_after")),
                passed=bool(
                    physics_residual_contract_pass
                    and _safe_float(physics_residual_metrics.get("residual_norm_after"))
                    <= _safe_float(physics_residual_metrics.get("residual_norm_before"))
                ),
            ),
            _bool_row(
                row_id="wind_pressure_coupled_transfer:gate:wind_tunnel_mapping_contract",
                family="wind_pressure_coupled_transfer",
                source="wind_tunnel_raw_mapping_report",
                metric="wind_tunnel_mapping_contract",
                value=bool(wind_tunnel_mapping_contract_pass),
                passed=bool(wind_tunnel_mapping_contract_pass),
            ),
            _bool_row(
                row_id="wind_pressure_coupled_transfer:gate:wind_contract",
                family="wind_pressure_coupled_transfer",
                source="wind_time_history_gate_report",
                metric="wind_contract",
                value=bool(wind_contract_pass),
                passed=bool(wind_contract_pass),
            ),
            _bool_row(
                row_id="wind_pressure_coupled_transfer:gate:phase_correction_contract",
                family="wind_pressure_coupled_transfer",
                source="phase_correction_assimilation_report",
                metric="phase_correction_contract",
                value=bool(phase_correction_contract_pass),
                passed=bool(phase_correction_contract_pass),
            ),
            _bool_row(
                row_id="wind_pressure_coupled_transfer:gate:midas_traceability_ready",
                family="wind_pressure_coupled_transfer",
                source="wind_tunnel_raw_mapping_report",
                metric="midas_traceability_ready",
                value=bool(wind_tunnel_mapping_checks.get("midas_traceability_ready", False)),
                passed=bool(wind_tunnel_mapping_contract_pass and wind_tunnel_mapping_checks.get("midas_traceability_ready", False)),
            ),
            _bool_row(
                row_id="wind_pressure_coupled_transfer:summary:mapping_row_count",
                family="wind_pressure_coupled_transfer",
                source="wind_tunnel_raw_mapping_report",
                metric="mapping_row_count",
                value=int(wind_tunnel_mapping_summary.get("mapping_row_count", 0) or 0),
                passed=bool(int(wind_tunnel_mapping_summary.get("mapping_row_count", 0) or 0) > 0),
            ),
        ]
    )

    families = (
        "concrete_damage",
        "cyclic_degradation",
        "bond_interface",
        "creep_shrinkage",
        "soil_boundary_nonlinear",
        "device_dissipation",
        "foundation_impedance_nonlinear",
        "contact_link_hysteresis",
        "panel_zone_joint_response",
        "wind_dynamic_response",
        "track_support_viscoelasticity",
        "vehicle_track_transient_coupling",
        "tunnel_soil_wave_attenuation",
        "serviceability_velocity_response",
        "construction_stage_redistribution",
        "joint_constraint_transfer",
        "aeroelastic_serviceability",
        "heterogeneous_soil_adaptation",
        "segment_joint_softening",
        "longitudinal_wave_strain_transfer",
        "raw_pressure_field_mapping",
        "phase_assimilation_correction",
        "multiscale_streaming_refinement",
        "integrated_vibration_transfer",
        "resilience_ood_recovery",
        "boundary_absorption_nonlinear",
        "attention_load_localization",
        "residual_energy_stabilization",
        "phase_latency_projection",
        "cache_window_adaptation",
        "whitebox_feedback_stitching",
        "recovery_residual_relock",
        "rail_support_contact_modulation",
        "tunnel_lining_interface_recovery",
        "panel_feedback_residual_transfer",
        "wind_pressure_coupled_transfer",
    )
    family_counts: dict[str, int] = {}
    family_pass_counts: dict[str, int] = {}
    family_rows: dict[str, list[dict[str, Any]]] = {}
    for family in families:
        scoped = [row for row in rows if row["family"] == family]
        family_rows[family] = scoped
        family_counts[family] = len(scoped)
        family_pass_counts[family] = sum(1 for row in scoped if row["pass"])

    return {
        "rows": rows,
        "families": family_rows,
        "family_counts": family_counts,
        "family_pass_counts": family_pass_counts,
        "total_rows": len(rows),
        "total_pass_rows": sum(1 for row in rows if row["pass"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    parser.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument("--rc-benchmark-lock-report", default="implementation/phase1/rc_benchmark_lock_report.json")
    parser.add_argument("--rc-benchmark-lock-cases", default="implementation/phase1/open_data/rc/rc_benchmark_lock_cases.json")
    parser.add_argument("--construction-sequence-report", default="implementation/phase1/construction_sequence_gate_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--damper-validation-report", default="implementation/phase1/damper_validation_gate_report.json")
    parser.add_argument("--foundation-soil-link-gate-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    parser.add_argument("--structural-contact-validation-report", default="implementation/phase1/structural_contact_validation_report.json")
    parser.add_argument("--panel-zone-clash-report", default="implementation/phase1/panel_zone_clash_report.json")
    parser.add_argument("--wind-time-history-gate-report", default="implementation/phase1/wind_time_history_gate_report.json")
    parser.add_argument("--vibration-attenuation-report", default="implementation/phase1/vibration_attenuation_report.json")
    parser.add_argument("--vibration-compliance-report", default="implementation/phase1/vibration_compliance_report.json")
    parser.add_argument("--track-lf-solver-report", default="implementation/phase1/track_lf_solver_report.json")
    parser.add_argument("--moving-load-integrator-report", default="implementation/phase1/moving_load_integrator_report.json")
    parser.add_argument("--vti-coupled-solver-report", default="implementation/phase1/vti_coupled_solver_report.json")
    parser.add_argument("--track-irregularity-report", default="implementation/phase1/track_irregularity_report.json")
    parser.add_argument("--track-dynamics-dataset-report", default="implementation/phase1/track_dynamics_dataset_report.json")
    parser.add_argument("--tunnel-dynamics-dataset-report", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    parser.add_argument("--heterogeneous-soil-ood-report", default="implementation/phase1/heterogeneous_soil_ood_report.json")
    parser.add_argument("--tunnel-segment-joint-report", default="implementation/phase1/tunnel_segment_joint_report.json")
    parser.add_argument("--tunnel-seismic-longitudinal-report", default="implementation/phase1/tunnel_seismic_longitudinal_report.json")
    parser.add_argument("--wind-tunnel-raw-mapping-report", default="implementation/phase1/wind_tunnel_raw_mapping_report.json")
    parser.add_argument("--phase-correction-assimilation-report", default="implementation/phase1/phase_correction_assimilation_report.json")
    parser.add_argument("--multiscale-l3-streaming-report", default="implementation/phase1/multiscale_l3_streaming_report.json")
    parser.add_argument("--phasee-integrated-summary-report", default="implementation/phase1/phasee_integrated_summary_report.json")
    parser.add_argument("--phasef-resilience-summary-report", default="implementation/phase1/phasef_resilience_summary_report.json")
    parser.add_argument("--dynamics-boundary-report", default="implementation/phase1/dynamics_boundary_report.json")
    parser.add_argument("--moving-load-attention-report", default="implementation/phase1/moving_load_attention_report.json")
    parser.add_argument("--physics-residual-contract-report", default="implementation/phase1/physics_residual_contract_report.json")
    parser.add_argument(
        "--benchmark-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json,"
            "implementation/phase1/commercial_benchmark_cases.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json,"
            "implementation/phase1/experiments/by_test/phase3_pipeline_nightly/20260301T111849Z/artifacts/commercial_benchmark_cases.atwood_open.json,"
            "implementation/phase1/experiments/by_test/solver_breadth_gate/20260328T152545Z/artifacts/commercial_benchmark_cases.atwood_open.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke2.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke3.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.pr_recheck.json,"
            "implementation/phase1/commercial_benchmark_cases.kw51_railway_bridge.json,"
            "implementation/phase1/commercial_benchmark_cases.opstool_nightly.json,"
            "implementation/phase1/commercial_benchmark_cases.opstool_pr.json,"
            "implementation/phase1/experiments/legacy_cleanup/20260301T111404Z/phase1_root/commercial_benchmark_cases.atwood_open.sample.json,"
            "implementation/phase1/experiments/legacy_cleanup/20260301T111404Z/phase1_root/commercial_benchmark_cases.atwood_open.sample_pipeline.json,"
            "implementation/phase1/experiments/legacy_cleanup/20260301T111404Z/phase1_root/commercial_benchmark_cases.atwood_open.sample_scaleout.json"
        ),
    )
    parser.add_argument("--min-concrete-damage-rows", type=int, default=1)
    parser.add_argument("--min-cyclic-rows", type=int, default=1)
    parser.add_argument("--min-bond-interface-rows", type=int, default=1)
    parser.add_argument("--out", default="implementation/phase1/material_constitutive_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "pushover_stress_report": str(args.pushover_stress_report),
        "ndtha_stress_report": str(args.ndtha_stress_report),
        "rc_benchmark_lock_report": str(args.rc_benchmark_lock_report),
        "rc_benchmark_lock_cases": str(args.rc_benchmark_lock_cases),
        "construction_sequence_report": str(args.construction_sequence_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "damper_validation_report": str(args.damper_validation_report),
        "foundation_soil_link_gate_report": str(args.foundation_soil_link_gate_report),
        "structural_contact_validation_report": str(args.structural_contact_validation_report),
        "panel_zone_clash_report": str(args.panel_zone_clash_report),
        "wind_time_history_gate_report": str(args.wind_time_history_gate_report),
        "vibration_attenuation_report": str(args.vibration_attenuation_report),
        "vibration_compliance_report": str(args.vibration_compliance_report),
        "track_lf_solver_report": str(args.track_lf_solver_report),
        "moving_load_integrator_report": str(args.moving_load_integrator_report),
        "vti_coupled_solver_report": str(args.vti_coupled_solver_report),
        "track_irregularity_report": str(args.track_irregularity_report),
        "track_dynamics_dataset_report": str(args.track_dynamics_dataset_report),
        "tunnel_dynamics_dataset_report": str(args.tunnel_dynamics_dataset_report),
            "heterogeneous_soil_ood_report": str(args.heterogeneous_soil_ood_report),
            "tunnel_segment_joint_report": str(args.tunnel_segment_joint_report),
            "tunnel_seismic_longitudinal_report": str(args.tunnel_seismic_longitudinal_report),
            "wind_tunnel_raw_mapping_report": str(args.wind_tunnel_raw_mapping_report),
            "phase_correction_assimilation_report": str(args.phase_correction_assimilation_report),
            "multiscale_l3_streaming_report": str(args.multiscale_l3_streaming_report),
            "phasee_integrated_summary_report": str(args.phasee_integrated_summary_report),
            "phasef_resilience_summary_report": str(args.phasef_resilience_summary_report),
            "dynamics_boundary_report": str(args.dynamics_boundary_report),
            "moving_load_attention_report": str(args.moving_load_attention_report),
            "physics_residual_contract_report": str(args.physics_residual_contract_report),
            "benchmark_cases": str(args.benchmark_cases),
            "min_concrete_damage_rows": int(args.min_concrete_damage_rows),
            "min_cyclic_rows": int(args.min_cyclic_rows),
        "min_bond_interface_rows": int(args.min_bond_interface_rows),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_material_constitutive_gate")

        pushover_path = Path(args.pushover_stress_report)
        ndtha_path = Path(args.ndtha_stress_report)
        rc_lock_path = Path(args.rc_benchmark_lock_report)
        rc_lock_cases_path = Path(args.rc_benchmark_lock_cases)
        construction_path = Path(args.construction_sequence_report)
        ssi_path = Path(args.ssi_boundary_report)
        damper_path = Path(args.damper_validation_report)
        foundation_path = Path(args.foundation_soil_link_gate_report)
        contact_path = Path(args.structural_contact_validation_report)
        panel_zone_path = Path(args.panel_zone_clash_report)
        wind_path = Path(args.wind_time_history_gate_report)
        vibration_attenuation_path = Path(args.vibration_attenuation_report)
        vibration_compliance_path = Path(args.vibration_compliance_report)
        track_lf_path = Path(args.track_lf_solver_report)
        moving_load_path = Path(args.moving_load_integrator_report)
        vti_coupled_path = Path(args.vti_coupled_solver_report)
        track_irregularity_path = Path(args.track_irregularity_report)
        track_dataset_path = Path(args.track_dynamics_dataset_report)
        tunnel_dataset_path = Path(args.tunnel_dynamics_dataset_report)
        heterogeneous_soil_path = Path(args.heterogeneous_soil_ood_report)
        segment_joint_path = Path(args.tunnel_segment_joint_report)
        tunnel_longitudinal_path = Path(args.tunnel_seismic_longitudinal_report)
        wind_tunnel_mapping_path = Path(args.wind_tunnel_raw_mapping_report)
        phase_correction_path = Path(args.phase_correction_assimilation_report)
        multiscale_streaming_path = Path(args.multiscale_l3_streaming_report)
        phasee_integrated_path = Path(args.phasee_integrated_summary_report)
        phasef_resilience_path = Path(args.phasef_resilience_summary_report)
        dynamics_boundary_path = Path(args.dynamics_boundary_report)
        moving_load_attention_path = Path(args.moving_load_attention_report)
        physics_residual_path = Path(args.physics_residual_contract_report)
        benchmark_case_paths = [Path(item) for item in _parse_csv(args.benchmark_cases)]

        pushover = _load_json(pushover_path)
        ndtha = _load_json(ndtha_path)
        rc_lock = _load_json(rc_lock_path)
        construction = _load_json(construction_path)
        ssi = _load_json(ssi_path)
        damper = _load_json(damper_path)
        foundation = _load_json(foundation_path)
        contact = _load_json(contact_path)
        panel_zone = _load_json(panel_zone_path)
        wind = _load_json(wind_path)
        vibration_attenuation = _load_json(vibration_attenuation_path)
        vibration_compliance = _load_json(vibration_compliance_path)
        track_lf = _load_json(track_lf_path)
        moving_load = _load_json(moving_load_path)
        vti_coupled = _load_json(vti_coupled_path)
        track_irregularity = _load_json(track_irregularity_path)
        track_dataset = _load_json(track_dataset_path)
        tunnel_dataset = _load_json(tunnel_dataset_path)
        heterogeneous_soil = _load_json(heterogeneous_soil_path)
        segment_joint = _load_json(segment_joint_path)
        tunnel_longitudinal = _load_json(tunnel_longitudinal_path)
        wind_tunnel_mapping = _load_json(wind_tunnel_mapping_path)
        phase_correction = _load_json(phase_correction_path)
        multiscale_streaming = _load_json(multiscale_streaming_path)
        phasee_integrated = _load_json(phasee_integrated_path)
        phasef_resilience = _load_json(phasef_resilience_path)
        dynamics_boundary = _load_json(dynamics_boundary_path)
        moving_load_attention = _load_json(moving_load_attention_path)
        physics_residual = _load_json(physics_residual_path)
        source_family_cases, source_family_labels = _aggregate_source_family_cases(benchmark_case_paths)
        rc_lock_physical_families = _load_rc_lock_physical_families(rc_lock_cases_path)
        supplemental_family_evidence = _collect_constitutive_family_evidence(rc_lock)
        family_source_families = {
            family: sorted(set(source_family_labels) | set(scoped.keys()))
            for family, scoped in supplemental_family_evidence.items()
        }
        family_source_families.setdefault("creep_shrinkage", sorted(set(source_family_labels) | set(supplemental_family_evidence.get("creep_shrinkage", {}).keys())))
        family_source_families.setdefault("soil_boundary_nonlinear", sorted(set(source_family_labels) | ({str(_summary_dict(ssi).get('soil_profile', '')).strip()} - {''})))
        family_source_families.setdefault("device_dissipation", sorted(set(source_family_labels) | {f"damper_{str(item).strip()}" for item in (_summary_dict(damper).get('damper_types') or []) if str(item).strip()}))
        family_source_families.setdefault("foundation_impedance_nonlinear", sorted(set(source_family_labels) | {"foundation_soil_link", "foundation_impedance_schema", "soil_support_links", "ssi_boundary", "soil_tunnel"}))
        family_source_families.setdefault("contact_link_hysteresis", sorted(set(source_family_labels) | {f"contact_{str(item).strip()}" for item in (_summary_dict(contact).get('link_model_types') or []) if str(item).strip()}))
        family_source_families.setdefault("panel_zone_joint_response", sorted(set(source_family_labels) | {str(item).strip() for item in (_summary_dict(panel_zone).get('panel_zone_source_valid_row_counts') or {}).keys() if str(item).strip()}))
        family_source_families.setdefault("wind_dynamic_response", sorted(set(source_family_labels) | {"wind_time_history", *{f"wind_{str(item).strip()}" for item in (_summary_dict(wind).get('material_model_types') or []) if str(item).strip()}}))
        family_source_families.setdefault("track_support_viscoelasticity", sorted(set(source_family_labels) | {
            "track_lf_solver",
            "track_irregularity",
            str(_summary_dict(track_irregularity).get("class", "") or "").strip(),
            str(_summary_dict(track_irregularity).get("preprocess_backend", "") or "").strip(),
        } - {""}))
        family_source_families.setdefault("vehicle_track_transient_coupling", sorted(set(source_family_labels) | {
            "moving_load_integrator",
            "vti_coupled_solver",
            "track_dynamics_dataset",
            "vehicle_track_coupling",
        }))
        family_source_families.setdefault("tunnel_soil_wave_attenuation", sorted(set(source_family_labels) | {
            "vibration_attenuation",
            "tunnel_dynamics_dataset",
            "soil_tunnel_wave_field",
            str(_summary_dict(ssi).get("soil_profile", "") or "").strip(),
        } - {""}))
        family_source_families.setdefault("serviceability_velocity_response", sorted(set(source_family_labels) | {
            "vibration_compliance",
            "serviceability_velocity",
            "track_irregularity",
        }))
        family_source_families.setdefault("construction_stage_redistribution", sorted(set(source_family_labels) | {
            "construction_sequence",
            "construction_stage_redistribution",
            "differential_shortening",
            "creep_shrinkage_column",
        }))
        family_source_families.setdefault("joint_constraint_transfer", sorted(set(source_family_labels) | {
            "joint_constraint_transfer",
            "panel_zone_joint_geometry_3d",
            "panel_zone_rebar_anchorage_3d",
            "panel_zone_clash_verification_3d",
            "constraint_projection_bridge",
        }))
        family_source_families.setdefault("aeroelastic_serviceability", sorted(set(source_family_labels) | {
            "aeroelastic_serviceability",
            "wind_time_history",
            "vibration_compliance",
            "serviceability_velocity",
            *{f"wind_{str(item).strip()}" for item in (_summary_dict(wind).get("material_model_types") or []) if str(item).strip()},
        }))
        family_source_families.setdefault("heterogeneous_soil_adaptation", sorted(set(source_family_labels) | {
            "heterogeneous_soil_ood",
            "soil_boundary_adaptation",
            "soil_profile_shift",
            "ood_fallback_route",
        }))
        family_source_families.setdefault("segment_joint_softening", sorted(set(source_family_labels) | {
            "tunnel_segment_joint",
            "segment_joint_softening",
            "joint_post_peak_softening",
            "joint_energy_dissipation",
        }))
        family_source_families.setdefault("longitudinal_wave_strain_transfer", sorted(set(source_family_labels) | {
            "tunnel_longitudinal_seismic",
            "longitudinal_wave_transfer",
            "wave_strain_transfer",
            "soil_tunnel_longitudinal",
        }))
        family_source_families.setdefault("raw_pressure_field_mapping", sorted(set(source_family_labels) | {
            "wind_tunnel_raw_mapping",
            "pressure_field_mapping",
            "raw_pressure_binding",
            "midas_pressure_traceability",
        }))
        family_source_families.setdefault("phase_assimilation_correction", sorted(set(source_family_labels) | {
            "phase_correction_assimilation",
            "transient_phase_alignment",
            "sensor_correction_state_update",
        }))
        family_source_families.setdefault("multiscale_streaming_refinement", sorted(set(source_family_labels) | {
            "multiscale_l3_streaming",
            "windowed_o_n_streaming",
            "near_field_refinement",
        }))
        family_source_families.setdefault("integrated_vibration_transfer", sorted(set(source_family_labels) | {
            "substructuring_interface",
            "vibration_attenuation",
            "vibration_compliance",
            "whitebox_validation",
        }))
        family_source_families.setdefault("resilience_ood_recovery", sorted(set(source_family_labels) | {
            "multiscale_l3_streaming",
            "phase_correction_assimilation",
            "heterogeneous_soil_ood",
        }))
        family_source_families.setdefault("boundary_absorption_nonlinear", sorted(set(source_family_labels) | {
            "dynamics_boundary",
            f"domain_{str(dynamics_boundary.get('domain_type', '') or '').strip()}",
            f"damping_{str(((dynamics_boundary.get('damping_summary') or {}) if isinstance(dynamics_boundary.get('damping_summary'), dict) else {}).get('damping_model', '') or '').strip()}",
            *{
                f"support_{str(item).strip()}"
                for item in (((dynamics_boundary.get('supports_summary') or {}) if isinstance(dynamics_boundary.get('supports_summary'), dict) else {}).get('support_types') or [])
                if str(item).strip()
            },
        } - {""}))
        family_source_families.setdefault("attention_load_localization", sorted(set(source_family_labels) | {
            "moving_load_attention",
            "attention_shape_localization",
            "speed_scaling_attention",
            "support_window_localization",
        }))
        family_source_families.setdefault("residual_energy_stabilization", sorted(set(source_family_labels) | {
            "physics_residual_contract",
            f"solver_{str(((physics_residual.get('metrics') or {}) if isinstance(physics_residual.get('metrics'), dict) else {}).get('solver', '') or '').strip()}",
            f"mode_{str(((physics_residual.get('source') or {}) if isinstance(physics_residual.get('source'), dict) else {}).get('mode', '') or '').strip()}",
            "energy_monotonicity_guard",
            "boundary_residual_stabilization",
        } - {""}))
        family_source_families.setdefault("phase_latency_projection", sorted(set(source_family_labels) | {
            "phase_correction_assimilation",
            "phase_latency_projection",
            "time_lag_projection",
            "phase_window_alignment",
        }))
        family_source_families.setdefault("cache_window_adaptation", sorted(set(source_family_labels) | {
            "multiscale_l3_streaming",
            "cache_window_adaptation",
            "streaming_cache_guard",
            "active_window_projection",
        }))
        family_source_families.setdefault("whitebox_feedback_stitching", sorted(set(source_family_labels) | {
            "phasee_integrated",
            "whitebox_feedback_stitching",
            "substructuring_feedback_bridge",
            "validation_extension_feedback",
        }))
        family_source_families.setdefault("recovery_residual_relock", sorted(set(source_family_labels) | {
            "phasef_resilience",
            "physics_residual_contract",
            "recovery_residual_relock",
            "residual_reentry_guard",
        }))
        family_source_families.setdefault("rail_support_contact_modulation", sorted(set(source_family_labels) | {
            "track_lf_solver",
            "moving_load_attention",
            "track_irregularity",
            "rail_support_contact_modulation",
            str((((track_irregularity.get("metrics") if isinstance(track_irregularity.get("metrics"), dict) else {}) or {}).get("class", "")) or "").strip(),
        } - {""}))
        family_source_families.setdefault("tunnel_lining_interface_recovery", sorted(set(source_family_labels) | {
            "tunnel_segment_joint",
            "tunnel_longitudinal_seismic",
            "heterogeneous_soil_ood",
            "tunnel_lining_interface_recovery",
            "segment_joint_relocking",
        }))
        family_source_families.setdefault("panel_feedback_residual_transfer", sorted(set(source_family_labels) | {
            "panel_zone_joint_geometry_3d",
            "phasee_integrated",
            "physics_residual_contract",
            "panel_feedback_residual_transfer",
            "substructure_feedback_bridge",
        }))
        family_source_families.setdefault("wind_pressure_coupled_transfer", sorted(set(source_family_labels) | {
            "wind_tunnel_raw_mapping",
            "wind_time_history",
            "phase_correction_assimilation",
            "wind_pressure_coupled_transfer",
            "pressure_field_mapping",
        }))

        pushover_checks = pushover.get("checks") if isinstance(pushover.get("checks"), dict) else {}
        ndtha_checks = ndtha.get("checks") if isinstance(ndtha.get("checks"), dict) else {}
        rc_lock_checks = rc_lock.get("checks") if isinstance(rc_lock.get("checks"), dict) else {}
        construction_checks = construction.get("checks") if isinstance(construction.get("checks"), dict) else {}
        ssi_checks = ssi.get("checks") if isinstance(ssi.get("checks"), dict) else {}
        damper_checks = damper.get("checks") if isinstance(damper.get("checks"), dict) else {}
        foundation_checks = foundation.get("checks") if isinstance(foundation.get("checks"), dict) else {}
        panel_zone_checks = panel_zone.get("checks") if isinstance(panel_zone.get("checks"), dict) else {}
        wind_checks = wind.get("checks") if isinstance(wind.get("checks"), dict) else {}
        construction_summary = _summary_dict(construction)
        ssi_summary = _summary_dict(ssi)
        damper_summary = _summary_dict(damper)
        foundation_summary = _summary_dict(foundation)
        contact_summary = _summary_dict(contact)
        panel_zone_summary = _summary_dict(panel_zone)
        wind_summary = _summary_dict(wind)
        joint_constraint_transfer_evidence = _joint_constraint_transfer_panel_zone_evidence(
            panel_zone_checks=panel_zone_checks,
            panel_zone_summary=panel_zone_summary,
        )
        vibration_attenuation_checks = vibration_attenuation.get("checks") if isinstance(vibration_attenuation.get("checks"), dict) else {}
        vibration_compliance_checks = vibration_compliance.get("checks") if isinstance(vibration_compliance.get("checks"), dict) else {}
        track_lf_checks = track_lf.get("checks") if isinstance(track_lf.get("checks"), dict) else {}
        moving_load_checks = moving_load.get("checks") if isinstance(moving_load.get("checks"), dict) else {}
        vti_coupled_checks = vti_coupled.get("checks") if isinstance(vti_coupled.get("checks"), dict) else {}
        track_dataset_checks = track_dataset.get("checks") if isinstance(track_dataset.get("checks"), dict) else {}
        tunnel_dataset_checks = tunnel_dataset.get("checks") if isinstance(tunnel_dataset.get("checks"), dict) else {}
        vibration_attenuation_metrics = vibration_attenuation.get("metrics") if isinstance(vibration_attenuation.get("metrics"), dict) else {}
        vibration_compliance_metrics = vibration_compliance.get("metrics") if isinstance(vibration_compliance.get("metrics"), dict) else {}
        track_lf_summary = track_lf.get("summary") if isinstance(track_lf.get("summary"), dict) else {}
        moving_load_metrics = moving_load.get("metrics") if isinstance(moving_load.get("metrics"), dict) else {}
        vti_coupled_metrics = vti_coupled.get("metrics") if isinstance(vti_coupled.get("metrics"), dict) else {}
        track_irregularity_metrics = track_irregularity.get("metrics") if isinstance(track_irregularity.get("metrics"), dict) else {}
        track_dataset_metrics = track_dataset.get("metrics") if isinstance(track_dataset.get("metrics"), dict) else {}
        tunnel_dataset_metrics = tunnel_dataset.get("metrics") if isinstance(tunnel_dataset.get("metrics"), dict) else {}
        heterogeneous_soil_checks = heterogeneous_soil.get("checks") if isinstance(heterogeneous_soil.get("checks"), dict) else {}
        heterogeneous_soil_metrics = heterogeneous_soil.get("metrics") if isinstance(heterogeneous_soil.get("metrics"), dict) else {}
        segment_joint_checks = segment_joint.get("checks") if isinstance(segment_joint.get("checks"), dict) else {}
        segment_joint_metrics = segment_joint.get("metrics") if isinstance(segment_joint.get("metrics"), dict) else {}
        tunnel_longitudinal_checks = tunnel_longitudinal.get("checks") if isinstance(tunnel_longitudinal.get("checks"), dict) else {}
        tunnel_longitudinal_metrics = tunnel_longitudinal.get("metrics") if isinstance(tunnel_longitudinal.get("metrics"), dict) else {}
        wind_tunnel_mapping_checks = wind_tunnel_mapping.get("checks") if isinstance(wind_tunnel_mapping.get("checks"), dict) else {}
        wind_tunnel_mapping_summary = wind_tunnel_mapping.get("summary") if isinstance(wind_tunnel_mapping.get("summary"), dict) else {}
        phase_correction_checks = phase_correction.get("checks") if isinstance(phase_correction.get("checks"), dict) else {}
        phase_correction_metrics = phase_correction.get("metrics") if isinstance(phase_correction.get("metrics"), dict) else {}
        multiscale_streaming_checks = multiscale_streaming.get("checks") if isinstance(multiscale_streaming.get("checks"), dict) else {}
        multiscale_streaming_metrics = multiscale_streaming.get("metrics") if isinstance(multiscale_streaming.get("metrics"), dict) else {}
        phasee_integrated_checks = phasee_integrated.get("checks") if isinstance(phasee_integrated.get("checks"), dict) else {}
        phasef_resilience_checks = phasef_resilience.get("checks") if isinstance(phasef_resilience.get("checks"), dict) else {}
        dynamics_boundary_summary = _summary_dict(dynamics_boundary)
        dynamics_boundary_supports_summary = dynamics_boundary.get("supports_summary") if isinstance(dynamics_boundary.get("supports_summary"), dict) else {}
        dynamics_boundary_damping_summary = dynamics_boundary.get("damping_summary") if isinstance(dynamics_boundary.get("damping_summary"), dict) else {}
        moving_load_attention_checks = moving_load_attention.get("checks") if isinstance(moving_load_attention.get("checks"), dict) else {}
        moving_load_attention_metrics = moving_load_attention.get("metrics") if isinstance(moving_load_attention.get("metrics"), dict) else {}
        physics_residual_checks = physics_residual.get("checks") if isinstance(physics_residual.get("checks"), dict) else {}
        physics_residual_metrics = physics_residual.get("metrics") if isinstance(physics_residual.get("metrics"), dict) else {}
        physics_residual_source = physics_residual.get("source") if isinstance(physics_residual.get("source"), dict) else {}
        ssi_rows = _iter_rows(ssi)
        wind_rows = _iter_rows(wind)
        contact_categories = contact.get("categories") if isinstance(contact.get("categories"), dict) else {}

        pushover_concrete_rows = _compression_damage_rows(pushover)
        ndtha_concrete_rows = _compression_damage_rows(ndtha)
        pushover_bond_rows = _bond_interface_rows(pushover)
        ndtha_bond_rows = _bond_interface_rows(ndtha)
        ndtha_cyclic_rows = _cyclic_degradation_rows(ndtha)

        concrete_damage_library_evidence = _concrete_damage_library_summary()
        concrete_damage_library_state_pass = bool(concrete_damage_library_evidence["state_coverage_pass"])
        concrete_damage_library_residual_pass = bool(concrete_damage_library_evidence["residual_ratio_pass"])

        concrete_damage_pass = bool(
            pushover.get("contract_pass", False)
            and ndtha.get("contract_pass", False)
            and bool(pushover_checks.get("material_model_pass", False))
            and bool(ndtha_checks.get("material_model_pass", False))
            and bool(rc_lock.get("contract_pass", False))
            and bool(rc_lock_checks.get("cracking_case_pass", False))
            and len(pushover_concrete_rows) >= int(args.min_concrete_damage_rows)
            and len(ndtha_concrete_rows) >= int(args.min_concrete_damage_rows)
            and concrete_damage_library_state_pass
            and concrete_damage_library_residual_pass
        )
        bond_interface_library_evidence = _bond_interface_library_summary()
        bond_interface_cyclic_evidence = _bond_interface_cyclic_evidence_summary()
        bond_interface_library_state_pass = bool(bond_interface_library_evidence["state_coverage_pass"])
        bond_interface_library_residual_pass = bool(bond_interface_library_evidence["residual_ratio_pass"])
        bond_interface_library_symmetry_pass = bool(bond_interface_library_evidence["symmetry_pass"])
        bond_interface_library_cyclic_reversal_pass = bool(
            int(bond_interface_cyclic_evidence["reversal_count"]) >= 1
            and bool(bond_interface_cyclic_evidence["unloading_observed"])
        )
        bond_interface_library_cyclic_deterioration_pass = bool(
            bool(bond_interface_cyclic_evidence["residual_observed"])
            and bool(bond_interface_cyclic_evidence["degradation_observed"])
            and float(bond_interface_cyclic_evidence["min_unloading_stiffness_ratio"]) < 1.0
            and bool(bond_interface_cyclic_evidence["library_evidence_pass"])
        )

        bond_interface_pass = bool(
            pushover.get("contract_pass", False)
            and ndtha.get("contract_pass", False)
            and bool(pushover_checks.get("material_model_pass", False))
            and bool(ndtha_checks.get("material_model_pass", False))
            and bool(rc_lock.get("contract_pass", False))
            and bool(rc_lock_checks.get("bond_slip_case_pass", False))
            and bool(construction.get("contract_pass", False))
            and bool(construction_checks.get("creep_shrinkage_applied", False))
            and len(pushover_bond_rows) >= int(args.min_bond_interface_rows)
            and len(ndtha_bond_rows) >= int(args.min_bond_interface_rows)
            and bond_interface_library_state_pass
            and bond_interface_library_residual_pass
            and bond_interface_library_symmetry_pass
            and bond_interface_library_cyclic_reversal_pass
            and bond_interface_library_cyclic_deterioration_pass
        )
        creep_shrinkage_pass = bool(
            construction.get("contract_pass", False)
            and bool(construction_checks.get("creep_shrinkage_applied", False))
            and bool(construction_checks.get("differential_shortening_detected", False))
            and math.isfinite(_safe_float(construction_summary.get("mean_creep_index")))
            and _safe_float(construction_summary.get("mean_creep_index")) > 0.0
            and math.isfinite(_safe_float(construction_summary.get("mean_shrinkage_index")))
            and _safe_float(construction_summary.get("mean_shrinkage_index")) > 0.0
        )
        soil_boundary_nonlinear_pass = bool(
            ssi.get("contract_pass", False)
            and bool(ssi_checks.get("ssi_nonlinear_boundary_active", False))
            and bool(ssi_checks.get("ssi_transfer_finite", False))
            and bool(ssi_checks.get("residual_trace_pass", False))
            and bool(ssi_checks.get("material_model_pass", False))
        )
        device_dissipation_pass = bool(
            damper.get("contract_pass", False)
            and bool(damper_checks.get("damper_type_diversity_pass", False))
            and bool(damper_checks.get("waveform_corr_pass", False))
            and bool(damper_checks.get("residual_drift_pass", False))
            and bool(damper_checks.get("material_model_pass", False))
        )
        foundation_impedance_nonlinear_pass = bool(
            foundation.get("contract_pass", False)
            and bool(foundation_checks.get("foundation_scope_ready", False))
            and bool(foundation_checks.get("foundation_artifact_ready", False))
            and bool(foundation_checks.get("ssi_boundary_ready", False))
            and bool(foundation_checks.get("soil_tunnel_ready", False))
            and bool(foundation_checks.get("impedance_schema_ready", False))
            and bool(foundation_checks.get("foundation_link_models_ready", False))
        )
        contact_link_hysteresis_pass = bool(
            contact.get("contract_pass", False)
            and int(contact_summary.get("validated_category_count", 0) or 0) >= int(contact_summary.get("required_category_count", 0) or 0)
            and int(contact_summary.get("contact_uplift_event_sequence_mismatch", 0) or 0) == 0
            and bool(contact_categories)
            and all(
                isinstance(row, dict)
                and bool(row.get("validated", False))
                and (
                    not isinstance(row.get("checks"), dict)
                    or all(bool(value) for value in row.get("checks", {}).values())
                )
                for row in contact_categories.values()
            )
        )
        panel_zone_surface = _panel_zone_joint_response_surface(
            bool(panel_zone.get("contract_pass", False)),
            panel_zone_checks,
            panel_zone_summary,
        )
        panel_zone_joint_response_pass = bool(panel_zone_surface.get("family_pass", False))
        wind_dynamic_response_pass = bool(
            wind.get("contract_pass", False)
            and bool(wind_checks.get("wind_duration_pass", False))
            and bool(wind_checks.get("wind_reversal_pass", False))
            and bool(wind_checks.get("long_series_chunked_pass", False))
            and bool(wind_checks.get("material_model_pass", False))
            and bool(wind_checks.get("residual_trace_pass", False))
            and bool(wind_checks.get("device_artifacts_consumed_pass", False))
        )
        track_support_viscoelasticity_pass = bool(
            track_lf.get("contract_pass", False)
            and bool(track_lf_checks.get("accuracy_pass", False))
            and bool(track_lf_checks.get("rust_kernel_used", False))
            and bool(track_lf_checks.get("o_n_operator", False))
            and bool(track_lf_checks.get("matrix_free_euler", False))
            and bool(track_irregularity_metrics)
        )
        vehicle_track_transient_coupling_pass = bool(
            moving_load.get("contract_pass", False)
            and bool(moving_load_checks.get("finite_response", False))
            and bool(moving_load_checks.get("non_divergent_response", False))
            and bool(moving_load_checks.get("equilibrium_residual_pass", False))
            and bool(moving_load_checks.get("energy_balance_pass", False))
            and bool(vti_coupled.get("contract_pass", False))
            and bool(vti_coupled_checks.get("coupling_converged_ratio_pass", False))
            and bool(vti_coupled_checks.get("dynamic_disp_pass", False))
            and bool(vti_coupled_checks.get("adaptive_newton_converged_pass", False))
            and bool(track_dataset.get("contract_pass", False))
            and bool(track_dataset_checks.get("dataset_nonempty", False))
            and bool(track_dataset_checks.get("equilibrium_residual_pass", False))
        )
        tunnel_soil_wave_attenuation_pass = bool(
            vibration_attenuation.get("contract_pass", False)
            and bool(vibration_attenuation_checks.get("substructuring_linked", False))
            and bool(vibration_attenuation_checks.get("finite_values", False))
            and bool(vibration_attenuation_checks.get("monotonic_distance_decay", False))
            and bool(vibration_attenuation_checks.get("high_frequency_decay_stronger", False))
            and bool(tunnel_dataset.get("contract_pass", False))
            and bool(tunnel_dataset_checks.get("dataset_nonempty", False))
            and bool(tunnel_dataset_checks.get("equilibrium_residual_pass", False))
        )
        serviceability_velocity_response_pass = bool(
            vibration_compliance.get("contract_pass", False)
            and bool(vibration_compliance_checks.get("standard_supported", False))
            and bool(vibration_compliance_checks.get("finite_values", False))
            and bool(vibration_compliance_checks.get("compliance_ratio_pass", False))
            and math.isfinite(_safe_float(vibration_compliance_metrics.get("pass_ratio")))
            and _safe_float(vibration_compliance_metrics.get("pass_ratio")) >= 0.95
        )
        construction_stage_redistribution_pass = bool(
            construction.get("contract_pass", False)
            and bool(construction_checks.get("creep_shrinkage_applied", False))
            and bool(construction_checks.get("differential_shortening_detected", False))
            and math.isfinite(_safe_float(construction_summary.get("mean_creep_index")))
            and math.isfinite(_safe_float(construction_summary.get("mean_shrinkage_index")))
        )
        joint_constraint_transfer_pass = bool(
            panel_zone.get("contract_pass", False)
            and bool(joint_constraint_transfer_evidence["required_sources_complete"])
            and bool(joint_constraint_transfer_evidence["topology_projected_bridge_complete"])
            and bool(joint_constraint_transfer_evidence["internal_engine_complete"])
            and int(joint_constraint_transfer_evidence["source_row_count"]) > 0
        )
        aeroelastic_serviceability_pass = bool(
            wind.get("contract_pass", False)
            and vibration_compliance.get("contract_pass", False)
            and bool(wind_checks.get("wind_duration_pass", False))
            and bool(wind_checks.get("residual_trace_pass", False))
            and bool(vibration_compliance_checks.get("standard_supported", False))
            and bool(vibration_compliance_checks.get("compliance_ratio_pass", False))
            and math.isfinite(_safe_float(vibration_compliance_metrics.get("pass_ratio")))
            and _safe_float(vibration_compliance_metrics.get("pass_ratio")) >= 0.95
        )
        heterogeneous_soil_adaptation_pass = bool(
            heterogeneous_soil.get("contract_pass", False)
            and bool(heterogeneous_soil_checks.get("ood_recall_pass", False))
            and bool(heterogeneous_soil_checks.get("false_negative_gate_pass", False))
            and bool(heterogeneous_soil_checks.get("fallback_route_on_ood_pass", False))
            and bool(heterogeneous_soil_checks.get("uncertainty_calibrated", False))
        )
        segment_joint_softening_pass = bool(
            segment_joint.get("contract_pass", False)
            and bool(segment_joint_checks.get("yield_detected", False))
            and bool(segment_joint_checks.get("post_yield_softening_pass", False))
            and bool(segment_joint_checks.get("energy_dissipation_pass", False))
        )
        longitudinal_wave_strain_transfer_pass = bool(
            tunnel_longitudinal.get("contract_pass", False)
            and bool(tunnel_longitudinal_checks.get("finite_response", False))
            and bool(tunnel_longitudinal_checks.get("displacement_limit_pass", False))
            and bool(tunnel_longitudinal_checks.get("strain_limit_pass", False))
        )
        raw_pressure_field_mapping_pass = bool(
            wind_tunnel_mapping.get("contract_pass", False)
            and bool(wind_tunnel_mapping_checks.get("raw_wind_data_exists", False))
            and bool(wind_tunnel_mapping_checks.get("raw_wind_manifest_verified", False))
            and bool(wind_tunnel_mapping_checks.get("wind_raw_mapping_available", False))
            and bool(wind_tunnel_mapping_checks.get("midas_traceability_ready", False))
        )
        phase_assimilation_correction_pass = bool(
            phase_correction.get("contract_pass", False)
            and bool(phase_correction_checks.get("phase_error_improved", False))
            and bool(phase_correction_checks.get("phase_error_below_threshold", False))
            and bool(phase_correction_checks.get("time_lag_below_threshold", False))
            and bool(phase_correction_checks.get("amplitude_error_not_degraded", False))
            and math.isfinite(_safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")))
            and _safe_float(phase_correction_metrics.get("phase_error_reduction_ratio")) >= 0.9
        )
        multiscale_streaming_refinement_pass = bool(
            multiscale_streaming.get("contract_pass", False)
            and bool(multiscale_streaming_checks.get("high_frequency_target", False))
            and bool(multiscale_streaming_checks.get("windowed_o_n_streaming", False))
            and bool(multiscale_streaming_checks.get("near_field_refined", False))
            and bool(multiscale_streaming_checks.get("has_cache_safe_chunk", False))
            and int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0) > 0
        )
        integrated_vibration_transfer_pass = bool(
            phasee_integrated.get("contract_pass", False)
            and bool(phasee_integrated_checks.get("E1_substructuring_interface", False))
            and bool(phasee_integrated_checks.get("E2_vibration_attenuation_model", False))
            and bool(phasee_integrated_checks.get("E3_vibration_compliance_checker", False))
            and bool(phasee_integrated_checks.get("E5_whitebox_validation_extension", False))
        )
        resilience_ood_recovery_pass = bool(
            phasef_resilience.get("contract_pass", False)
            and bool(phasef_resilience_checks.get("F1_multiscale_l3_streaming", False))
            and bool(phasef_resilience_checks.get("F2_phase_correction_assimilation", False))
            and bool(phasef_resilience_checks.get("F3_heterogeneous_soil_ood_gate", False))
        )
        boundary_absorption_nonlinear_pass = bool(
            dynamics_boundary.get("contract_pass", False)
            and len(dynamics_boundary_supports_summary.get("support_types") or []) > 0
            and int(dynamics_boundary_supports_summary.get("fixed_count", 0) or 0) > 0
            and str(dynamics_boundary_damping_summary.get("damping_model", "") or "").strip()
            and _safe_float(dynamics_boundary_damping_summary.get("time_step_dt")) > 0.0
            and math.isfinite(_safe_float(dynamics_boundary_damping_summary.get("alpha_m")))
            and math.isfinite(_safe_float(dynamics_boundary_damping_summary.get("beta_k")))
        )
        attention_load_localization_pass = bool(
            moving_load_attention.get("contract_pass", False)
            and bool(moving_load_attention_checks.get("peak_centered", False))
            and bool(moving_load_attention_checks.get("bounded_nonnegative", False))
            and bool(moving_load_attention_checks.get("shape_monotonic", False))
            and bool(moving_load_attention_checks.get("speed_scaling_monotonic", False))
            and _safe_float(moving_load_attention_metrics.get("peak_value")) > 0.0
            and int(moving_load_attention_metrics.get("support_high_count", 0) or 0)
            >= int(moving_load_attention_metrics.get("support_low_count", 0) or 0)
        )
        residual_energy_stabilization_pass = bool(
            physics_residual.get("contract_pass", False)
            and bool(physics_residual_checks.get("eq_ok", False))
            and bool(physics_residual_checks.get("boundary_ok", False))
            and bool(physics_residual_checks.get("damping_ok", False))
            and bool(physics_residual_checks.get("energy_monotonicity_pass", False))
            and _safe_float(physics_residual_metrics.get("residual_norm_after"))
            <= _safe_float(physics_residual_metrics.get("residual_norm_before"))
            and int(physics_residual_metrics.get("node_count", 0) or 0) > 0
        )

        calibration_matrix = _calibration_matrix(
            pushover_concrete_rows=pushover_concrete_rows,
            ndtha_concrete_rows=ndtha_concrete_rows,
            ndtha_cyclic_rows=ndtha_cyclic_rows,
            pushover_bond_rows=pushover_bond_rows,
            ndtha_bond_rows=ndtha_bond_rows,
            pushover_contract_pass=bool(pushover.get("contract_pass", False)),
            ndtha_contract_pass=bool(ndtha.get("contract_pass", False)),
            rc_lock_contract_pass=bool(rc_lock.get("contract_pass", False)),
            construction_contract_pass=bool(construction.get("contract_pass", False)),
            ssi_contract_pass=bool(ssi.get("contract_pass", False)),
            damper_contract_pass=bool(damper.get("contract_pass", False)),
            pushover_checks=pushover_checks,
            ndtha_checks=ndtha_checks,
            rc_lock_checks=rc_lock_checks,
            construction_checks=construction_checks,
            ssi_checks=ssi_checks,
            damper_checks=damper_checks,
            construction_summary=construction_summary,
            ssi_summary=ssi_summary,
            damper_summary=damper_summary,
            foundation_contract_pass=bool(foundation.get("contract_pass", False)),
            contact_contract_pass=bool(contact.get("contract_pass", False)),
            panel_zone_contract_pass=bool(panel_zone.get("contract_pass", False)),
            wind_contract_pass=bool(wind.get("contract_pass", False)),
            foundation_checks=foundation_checks,
            panel_zone_checks=panel_zone_checks,
            wind_checks=wind_checks,
            foundation_summary=foundation_summary,
            contact_summary=contact_summary,
            panel_zone_summary=panel_zone_summary,
            wind_summary=wind_summary,
            ssi_rows=ssi_rows,
            wind_rows=wind_rows,
            contact_categories=contact_categories,
            source_family_cases=source_family_cases,
            supplemental_family_evidence=supplemental_family_evidence,
            vibration_attenuation_contract_pass=bool(vibration_attenuation.get("contract_pass", False)),
            vibration_compliance_contract_pass=bool(vibration_compliance.get("contract_pass", False)),
            track_lf_contract_pass=bool(track_lf.get("contract_pass", False)),
            moving_load_contract_pass=bool(moving_load.get("contract_pass", False)),
            vti_coupled_contract_pass=bool(vti_coupled.get("contract_pass", False)),
            track_dataset_contract_pass=bool(track_dataset.get("contract_pass", False)),
            tunnel_dataset_contract_pass=bool(tunnel_dataset.get("contract_pass", False)),
            vibration_attenuation_checks=vibration_attenuation_checks,
            vibration_compliance_checks=vibration_compliance_checks,
            track_lf_checks=track_lf_checks,
            moving_load_checks=moving_load_checks,
            vti_coupled_checks=vti_coupled_checks,
            track_dataset_checks=track_dataset_checks,
            tunnel_dataset_checks=tunnel_dataset_checks,
            vibration_attenuation_metrics=vibration_attenuation_metrics,
            vibration_compliance_metrics=vibration_compliance_metrics,
            track_lf_summary=track_lf_summary,
            moving_load_metrics=moving_load_metrics,
            vti_coupled_metrics=vti_coupled_metrics,
            track_irregularity_metrics=track_irregularity_metrics,
            track_dataset_metrics=track_dataset_metrics,
            tunnel_dataset_metrics=tunnel_dataset_metrics,
            heterogeneous_soil_contract_pass=bool(heterogeneous_soil.get("contract_pass", False)),
            segment_joint_contract_pass=bool(segment_joint.get("contract_pass", False)),
            tunnel_longitudinal_contract_pass=bool(tunnel_longitudinal.get("contract_pass", False)),
            wind_tunnel_mapping_contract_pass=bool(wind_tunnel_mapping.get("contract_pass", False)),
            heterogeneous_soil_checks=heterogeneous_soil_checks,
            heterogeneous_soil_metrics=heterogeneous_soil_metrics,
            segment_joint_checks=segment_joint_checks,
            segment_joint_metrics=segment_joint_metrics,
            tunnel_longitudinal_checks=tunnel_longitudinal_checks,
            tunnel_longitudinal_metrics=tunnel_longitudinal_metrics,
            wind_tunnel_mapping_checks=wind_tunnel_mapping_checks,
            wind_tunnel_mapping_summary=wind_tunnel_mapping_summary,
            phase_correction_contract_pass=bool(phase_correction.get("contract_pass", False)),
            phase_correction_checks=phase_correction_checks,
            phase_correction_metrics=phase_correction_metrics,
            multiscale_streaming_contract_pass=bool(multiscale_streaming.get("contract_pass", False)),
            multiscale_streaming_checks=multiscale_streaming_checks,
            multiscale_streaming_metrics=multiscale_streaming_metrics,
            phasee_integrated_contract_pass=bool(phasee_integrated.get("contract_pass", False)),
            phasee_integrated_checks=phasee_integrated_checks,
            phasef_resilience_contract_pass=bool(phasef_resilience.get("contract_pass", False)),
            phasef_resilience_checks=phasef_resilience_checks,
            phasef_resilience_step_count=int(len(phasef_resilience.get("steps") or [])),
            dynamics_boundary_contract_pass=bool(dynamics_boundary.get("contract_pass", False)),
            dynamics_boundary_supports_summary=dynamics_boundary_supports_summary,
            dynamics_boundary_damping_summary=dynamics_boundary_damping_summary,
            moving_load_attention_contract_pass=bool(moving_load_attention.get("contract_pass", False)),
            moving_load_attention_checks=moving_load_attention_checks,
            moving_load_attention_metrics=moving_load_attention_metrics,
            physics_residual_contract_pass=bool(physics_residual.get("contract_pass", False)),
            physics_residual_checks=physics_residual_checks,
            physics_residual_metrics=physics_residual_metrics,
            min_concrete_damage_rows=int(args.min_concrete_damage_rows),
            min_cyclic_rows=int(args.min_cyclic_rows),
            min_bond_interface_rows=int(args.min_bond_interface_rows),
        )

        cyclic_probe = concrete_cyclic_probe()
        cyclic_library_evidence = _cyclic_library_evidence_summary(cyclic_probe)
        cyclic_library_state_coverage_pass = bool(
            {
                "compression_hardening",
                "compression_softening",
                "compression_crushed",
                "tension_softening",
            }.issubset(set(cyclic_library_evidence["envelope_state_tags"]))
            and int(cyclic_library_evidence["restoring_state_tag_count"]) >= 4
        )
        cyclic_library_damage_tags_pass = bool(
            {"crack_open", "crushing", "degradation", "pinching", "reversal"}.issubset(set(cyclic_library_evidence["evidence_tags"]))
            and bool(cyclic_library_evidence["library_evidence_pass"])
        )
        cyclic_step_series_evidence = _cyclic_step_series_evidence_summary(
            ndtha,
            ndtha_cyclic_rows,
            rc_lock,
            cyclic_probe=cyclic_probe,
        )
        cyclic_degradation_pass = bool(
            ndtha.get("contract_pass", False)
            and bool(ndtha_checks.get("dynamic_reversal_pass", False))
            and bool(ndtha_checks.get("plasticity_triggered_all_cases", False))
            and bool(ndtha_checks.get("residual_metric_sanity_pass", False))
            and bool(rc_lock.get("contract_pass", False))
            and bool(rc_lock_checks.get("cracking_case_pass", False))
            and len(ndtha_cyclic_rows) >= int(args.min_cyclic_rows)
            and cyclic_library_state_coverage_pass
            and cyclic_library_damage_tags_pass
            and bool(cyclic_step_series_evidence["series_link_pass"])
            and bool(cyclic_step_series_evidence["wall_slab_series_pass"])
            and bool(cyclic_step_series_evidence["rc_series_link_pass"])
        )

        checks = {
            "concrete_damage_pass": bool(concrete_damage_pass),
            "concrete_damage_library_state_pass": bool(concrete_damage_library_state_pass),
            "concrete_damage_library_residual_pass": bool(concrete_damage_library_residual_pass),
            "cyclic_degradation_pass": bool(cyclic_degradation_pass),
            "cyclic_library_state_coverage_pass": bool(cyclic_library_state_coverage_pass),
            "cyclic_library_damage_tags_pass": bool(cyclic_library_damage_tags_pass),
            "cyclic_step_series_pass": bool(cyclic_step_series_evidence["series_link_pass"]),
            "cyclic_wall_slab_step_series_pass": bool(cyclic_step_series_evidence["wall_slab_series_pass"]),
            "cyclic_rc_step_series_pass": bool(cyclic_step_series_evidence["rc_series_link_pass"]),
            "bond_interface_pass": bool(bond_interface_pass),
            "bond_interface_library_state_pass": bool(bond_interface_library_state_pass),
            "bond_interface_library_residual_pass": bool(bond_interface_library_residual_pass),
            "bond_interface_library_symmetry_pass": bool(bond_interface_library_symmetry_pass),
            "bond_interface_library_cyclic_reversal_pass": bool(bond_interface_library_cyclic_reversal_pass),
            "bond_interface_library_cyclic_deterioration_pass": bool(bond_interface_library_cyclic_deterioration_pass),
            "creep_shrinkage_pass": bool(creep_shrinkage_pass),
            "soil_boundary_nonlinear_pass": bool(soil_boundary_nonlinear_pass),
            "device_dissipation_pass": bool(device_dissipation_pass),
            "foundation_impedance_nonlinear_pass": bool(foundation_impedance_nonlinear_pass),
            "contact_link_hysteresis_pass": bool(contact_link_hysteresis_pass),
            "panel_zone_joint_response_pass": bool(panel_zone_joint_response_pass),
            "panel_zone_joint_response_bridge_ready_pass": bool(panel_zone_surface.get("bridge_complete", False)),
            "panel_zone_joint_response_material_evidence_pass": bool(
                panel_zone_surface.get("material_evidence_complete", False)
            ),
            "wind_dynamic_response_pass": bool(wind_dynamic_response_pass),
            "track_support_viscoelasticity_pass": bool(track_support_viscoelasticity_pass),
            "vehicle_track_transient_coupling_pass": bool(vehicle_track_transient_coupling_pass),
            "tunnel_soil_wave_attenuation_pass": bool(tunnel_soil_wave_attenuation_pass),
            "serviceability_velocity_response_pass": bool(serviceability_velocity_response_pass),
            "construction_stage_redistribution_pass": bool(construction_stage_redistribution_pass),
            "joint_constraint_transfer_pass": bool(joint_constraint_transfer_pass),
            "aeroelastic_serviceability_pass": bool(aeroelastic_serviceability_pass),
            "heterogeneous_soil_adaptation_pass": bool(heterogeneous_soil_adaptation_pass),
            "segment_joint_softening_pass": bool(segment_joint_softening_pass),
            "longitudinal_wave_strain_transfer_pass": bool(longitudinal_wave_strain_transfer_pass),
            "raw_pressure_field_mapping_pass": bool(raw_pressure_field_mapping_pass),
            "phase_assimilation_correction_pass": bool(phase_assimilation_correction_pass),
            "multiscale_streaming_refinement_pass": bool(multiscale_streaming_refinement_pass),
            "integrated_vibration_transfer_pass": bool(integrated_vibration_transfer_pass),
            "resilience_ood_recovery_pass": bool(resilience_ood_recovery_pass),
            "boundary_absorption_nonlinear_pass": bool(boundary_absorption_nonlinear_pass),
            "attention_load_localization_pass": bool(attention_load_localization_pass),
            "residual_energy_stabilization_pass": bool(residual_energy_stabilization_pass),
            "rc_benchmark_lock_pass": bool(rc_lock.get("contract_pass", False)),
            "construction_sequence_pass": bool(construction.get("contract_pass", False)),
            "ssi_boundary_pass": bool(ssi.get("contract_pass", False)),
            "damper_validation_pass": bool(damper.get("contract_pass", False)),
            "foundation_soil_link_pass": bool(foundation.get("contract_pass", False)),
            "structural_contact_validation_pass": bool(contact.get("contract_pass", False)),
            "panel_zone_clash_pass": bool(panel_zone.get("contract_pass", False)),
            "wind_time_history_pass": bool(wind.get("contract_pass", False)),
            "calibration_matrix_pass": bool(calibration_matrix["total_rows"] == calibration_matrix["total_pass_rows"]),
        }
        contract_pass = bool(all(checks.values()))
        if not concrete_damage_pass:
            reason_code = "ERR_CONCRETE_DAMAGE"
        elif not cyclic_degradation_pass:
            reason_code = "ERR_CYCLIC_DEGRADATION"
        elif not bond_interface_pass:
            reason_code = "ERR_BOND_INTERFACE"
        elif not foundation_impedance_nonlinear_pass:
            reason_code = "ERR_FOUNDATION_IMPEDANCE"
        elif not contact_link_hysteresis_pass:
            reason_code = "ERR_CONTACT_HYSTERESIS"
        elif not panel_zone_joint_response_pass:
            reason_code = "ERR_PANEL_ZONE_RESPONSE"
        elif not wind_dynamic_response_pass:
            reason_code = "ERR_WIND_DYNAMIC_RESPONSE"
        elif not track_support_viscoelasticity_pass:
            reason_code = "ERR_TRACK_SUPPORT_VISCOELASTICITY"
        elif not vehicle_track_transient_coupling_pass:
            reason_code = "ERR_VEHICLE_TRACK_TRANSIENT_COUPLING"
        elif not tunnel_soil_wave_attenuation_pass:
            reason_code = "ERR_TUNNEL_SOIL_WAVE_ATTENUATION"
        elif not serviceability_velocity_response_pass:
            reason_code = "ERR_SERVICEABILITY_VELOCITY_RESPONSE"
        elif not construction_stage_redistribution_pass:
            reason_code = "ERR_CONSTRUCTION_STAGE_REDISTRIBUTION"
        elif not joint_constraint_transfer_pass:
            reason_code = "ERR_JOINT_CONSTRAINT_TRANSFER"
        elif not aeroelastic_serviceability_pass:
            reason_code = "ERR_AEROELASTIC_SERVICEABILITY"
        elif not heterogeneous_soil_adaptation_pass:
            reason_code = "ERR_HETEROGENEOUS_SOIL_ADAPTATION"
        elif not segment_joint_softening_pass:
            reason_code = "ERR_SEGMENT_JOINT_SOFTENING"
        elif not longitudinal_wave_strain_transfer_pass:
            reason_code = "ERR_LONGITUDINAL_WAVE_STRAIN_TRANSFER"
        elif not raw_pressure_field_mapping_pass:
            reason_code = "ERR_RAW_PRESSURE_FIELD_MAPPING"
        elif not phase_assimilation_correction_pass:
            reason_code = "ERR_PHASE_ASSIMILATION_CORRECTION"
        elif not multiscale_streaming_refinement_pass:
            reason_code = "ERR_MULTISCALE_STREAMING_REFINEMENT"
        elif not integrated_vibration_transfer_pass:
            reason_code = "ERR_INTEGRATED_VIBRATION_TRANSFER"
        elif not resilience_ood_recovery_pass:
            reason_code = "ERR_RESILIENCE_OOD_RECOVERY"
        elif not boundary_absorption_nonlinear_pass:
            reason_code = "ERR_BOUNDARY_ABSORPTION_NONLINEAR"
        elif not attention_load_localization_pass:
            reason_code = "ERR_ATTENTION_LOAD_LOCALIZATION"
        elif not residual_energy_stabilization_pass:
            reason_code = "ERR_RESIDUAL_ENERGY_STABILIZATION"
        else:
            reason_code = "PASS"

        summary = {
            "concrete_damage_row_count": int(len(pushover_concrete_rows) + len(ndtha_concrete_rows)),
            "concrete_damage_pushover_row_count": int(len(pushover_concrete_rows)),
            "concrete_damage_ndtha_row_count": int(len(ndtha_concrete_rows)),
            "concrete_damage_library_state_tag_count": int(concrete_damage_library_evidence["state_tag_count"]),
            "concrete_damage_library_state_tags": list(concrete_damage_library_evidence["state_tags"]),
            "concrete_damage_library_max_tension_strain_ratio": float(concrete_damage_library_evidence["max_tension_strain_ratio"]),
            "concrete_damage_library_max_compression_strain_ratio": float(concrete_damage_library_evidence["max_compression_strain_ratio"]),
            "concrete_damage_library_residual_strength_ratio": float(concrete_damage_library_evidence["residual_strength_ratio"]),
            "cyclic_degradation_row_count": int(len(ndtha_cyclic_rows)),
            "cyclic_library_evidence_present": bool(cyclic_library_evidence["library_evidence_pass"]),
            "cyclic_library_probe_id": str(cyclic_library_evidence["probe_id"]),
            "cyclic_library_reversal_count": int(cyclic_library_evidence["reversal_count"]),
            "cyclic_library_restoring_state_tag_count": int(cyclic_library_evidence["restoring_state_tag_count"]),
            "cyclic_library_restoring_state_tags": list(cyclic_library_evidence["restoring_state_tags"]),
            "cyclic_library_envelope_state_tag_count": int(cyclic_library_evidence["envelope_state_tag_count"]),
            "cyclic_library_envelope_state_tags": list(cyclic_library_evidence["envelope_state_tags"]),
            "cyclic_library_min_pinching_ratio": float(cyclic_library_evidence["min_pinching_ratio"]),
            "cyclic_library_max_crushing_ratio": float(cyclic_library_evidence["max_crushing_ratio"]),
            "cyclic_library_max_stiffness_degradation": float(cyclic_library_evidence["max_stiffness_degradation"]),
            "cyclic_library_max_strength_degradation": float(cyclic_library_evidence["max_strength_degradation"]),
            "cyclic_library_evidence_tag_count": int(len(cyclic_library_evidence["evidence_tags"])),
            "cyclic_library_evidence_tags": list(cyclic_library_evidence["evidence_tags"]),
            "cyclic_step_series_evidence_present": bool(cyclic_step_series_evidence["series_link_pass"]),
            "cyclic_step_series_source_mode": str(cyclic_step_series_evidence["source_mode"]),
            "cyclic_step_series_response_case_count": int(cyclic_step_series_evidence["response_case_count"]),
            "cyclic_step_series_case_count": int(cyclic_step_series_evidence["series_case_count"]),
            "cyclic_step_series_depth": int(cyclic_step_series_evidence["step_series_depth"]),
            "cyclic_step_series_coverage_ratio": float(cyclic_step_series_evidence["response_coverage_ratio"]),
            "cyclic_step_series_solver_event_density": float(cyclic_step_series_evidence["solver_event_density"]),
            "cyclic_step_series_solver_event_count": int(cyclic_step_series_evidence["solver_event_count_total"]),
            "cyclic_step_series_recommended_dt_scale_min": float(cyclic_step_series_evidence["recommended_dt_scale_min"]),
            "cyclic_step_series_storage_mode_count": int(len(cyclic_step_series_evidence["response_storage_modes"])),
            "cyclic_step_series_storage_modes": list(cyclic_step_series_evidence["response_storage_modes"]),
            "cyclic_step_series_evidence_tag_count": int(len(cyclic_step_series_evidence["evidence_tags"])),
            "cyclic_step_series_evidence_tags": list(cyclic_step_series_evidence["evidence_tags"]),
            "cyclic_wall_slab_step_series_case_count": int(cyclic_step_series_evidence["wall_slab_case_count"]),
            "cyclic_wall_slab_step_series_coverage_ratio": float(cyclic_step_series_evidence["wall_slab_coverage_ratio"]),
            "cyclic_rc_step_series_case_count": int(cyclic_step_series_evidence["rc_case_count"]),
            "cyclic_rc_step_series_density": float(cyclic_step_series_evidence["rc_step_density"]),
            "cyclic_rc_step_series_family_labels": list(cyclic_step_series_evidence["rc_family_labels"]),
            "bond_interface_row_count": int(len(pushover_bond_rows) + len(ndtha_bond_rows)),
            "bond_interface_pushover_row_count": int(len(pushover_bond_rows)),
            "bond_interface_ndtha_row_count": int(len(ndtha_bond_rows)),
            "bond_interface_library_state_tag_count": int(bond_interface_library_evidence["state_tag_count"]),
            "bond_interface_library_state_tags": list(bond_interface_library_evidence["state_tags"]),
            "bond_interface_library_max_slip_ratio": float(bond_interface_library_evidence["max_slip_ratio"]),
            "bond_interface_library_residual_force_ratio": float(bond_interface_library_evidence["residual_force_ratio"]),
            "bond_interface_library_softening_tangent_ratio": float(bond_interface_library_evidence["softening_tangent_ratio"]),
            "bond_interface_library_symmetry_error_ratio": float(bond_interface_library_evidence["symmetry_error_ratio"]),
            "bond_interface_cyclic_evidence_present": bool(bond_interface_cyclic_evidence["library_evidence_pass"]),
            "bond_interface_cyclic_probe_id": str(bond_interface_cyclic_evidence["probe_id"]),
            "bond_interface_cyclic_reversal_count": int(bond_interface_cyclic_evidence["reversal_count"]),
            "bond_interface_cyclic_restoring_state_tag_count": int(
                bond_interface_cyclic_evidence["restoring_state_tag_count"]
            ),
            "bond_interface_cyclic_restoring_state_tags": list(
                bond_interface_cyclic_evidence["restoring_state_tags"]
            ),
            "bond_interface_cyclic_envelope_state_tag_count": int(
                bond_interface_cyclic_evidence["envelope_state_tag_count"]
            ),
            "bond_interface_cyclic_envelope_state_tags": list(
                bond_interface_cyclic_evidence["envelope_state_tags"]
            ),
            "bond_interface_cyclic_unloading_observed": bool(
                bond_interface_cyclic_evidence["unloading_observed"]
            ),
            "bond_interface_cyclic_residual_observed": bool(
                bond_interface_cyclic_evidence["residual_observed"]
            ),
            "bond_interface_cyclic_degradation_observed": bool(
                bond_interface_cyclic_evidence["degradation_observed"]
            ),
            "bond_interface_cyclic_min_unloading_stiffness_ratio": float(
                bond_interface_cyclic_evidence["min_unloading_stiffness_ratio"]
            ),
            "bond_interface_cyclic_max_strength_degradation": float(
                bond_interface_cyclic_evidence["max_strength_degradation"]
            ),
            "bond_interface_cyclic_max_slip_ratio": float(
                bond_interface_cyclic_evidence["max_slip_ratio"]
            ),
            "bond_interface_cyclic_terminal_residual_force_ratio": float(
                bond_interface_cyclic_evidence["terminal_residual_force_ratio"]
            ),
            "bond_interface_cyclic_evidence_tag_count": int(
                len(bond_interface_cyclic_evidence["evidence_tags"])
            ),
            "bond_interface_cyclic_evidence_tags": list(
                bond_interface_cyclic_evidence["evidence_tags"]
            ),
            "creep_shrinkage_row_count": int(calibration_matrix["family_counts"].get("creep_shrinkage", 0)),
            "soil_boundary_nonlinear_row_count": int(calibration_matrix["family_counts"].get("soil_boundary_nonlinear", 0)),
            "device_dissipation_row_count": int(calibration_matrix["family_counts"].get("device_dissipation", 0)),
            "foundation_impedance_nonlinear_row_count": int(calibration_matrix["family_counts"].get("foundation_impedance_nonlinear", 0)),
            "contact_link_hysteresis_row_count": int(calibration_matrix["family_counts"].get("contact_link_hysteresis", 0)),
            "panel_zone_joint_response_row_count": int(calibration_matrix["family_counts"].get("panel_zone_joint_response", 0)),
            "panel_zone_joint_response_bridge_mode": str(panel_zone_surface.get("bridge_mode", "") or ""),
            "panel_zone_joint_response_material_evidence_mode": str(
                panel_zone_surface.get("material_evidence_mode", "") or ""
            ),
            "panel_zone_joint_response_exact_verified_complete": bool(
                panel_zone_surface.get("exact_verified_complete", False)
            ),
            "panel_zone_joint_response_source_contract_mode": str(
                panel_zone_surface.get("source_contract_mode", "") or ""
            ),
            "panel_feedback_residual_transfer_row_count": int(
                calibration_matrix["family_counts"].get("panel_feedback_residual_transfer", 0)
            ),
            "panel_feedback_residual_transfer_pass_row_count": int(
                calibration_matrix["family_pass_counts"].get("panel_feedback_residual_transfer", 0)
            ),
            "panel_feedback_residual_transfer_bridge_mode": str(
                panel_zone_surface.get("bridge_mode", "") or ""
            ),
            "panel_feedback_residual_transfer_bridge_ready": bool(
                panel_zone_surface.get("bridge_complete", False)
            ),
            "wind_dynamic_response_row_count": int(calibration_matrix["family_counts"].get("wind_dynamic_response", 0)),
            "track_support_viscoelasticity_row_count": int(calibration_matrix["family_counts"].get("track_support_viscoelasticity", 0)),
            "vehicle_track_transient_coupling_row_count": int(calibration_matrix["family_counts"].get("vehicle_track_transient_coupling", 0)),
            "tunnel_soil_wave_attenuation_row_count": int(calibration_matrix["family_counts"].get("tunnel_soil_wave_attenuation", 0)),
            "serviceability_velocity_response_row_count": int(calibration_matrix["family_counts"].get("serviceability_velocity_response", 0)),
            "construction_stage_redistribution_row_count": int(calibration_matrix["family_counts"].get("construction_stage_redistribution", 0)),
            "joint_constraint_transfer_row_count": int(calibration_matrix["family_counts"].get("joint_constraint_transfer", 0)),
            "aeroelastic_serviceability_row_count": int(calibration_matrix["family_counts"].get("aeroelastic_serviceability", 0)),
            "heterogeneous_soil_adaptation_row_count": int(calibration_matrix["family_counts"].get("heterogeneous_soil_adaptation", 0)),
            "segment_joint_softening_row_count": int(calibration_matrix["family_counts"].get("segment_joint_softening", 0)),
            "longitudinal_wave_strain_transfer_row_count": int(calibration_matrix["family_counts"].get("longitudinal_wave_strain_transfer", 0)),
            "raw_pressure_field_mapping_row_count": int(calibration_matrix["family_counts"].get("raw_pressure_field_mapping", 0)),
            "phase_assimilation_correction_row_count": int(calibration_matrix["family_counts"].get("phase_assimilation_correction", 0)),
            "multiscale_streaming_refinement_row_count": int(calibration_matrix["family_counts"].get("multiscale_streaming_refinement", 0)),
            "integrated_vibration_transfer_row_count": int(calibration_matrix["family_counts"].get("integrated_vibration_transfer", 0)),
            "resilience_ood_recovery_row_count": int(calibration_matrix["family_counts"].get("resilience_ood_recovery", 0)),
            "boundary_absorption_nonlinear_row_count": int(calibration_matrix["family_counts"].get("boundary_absorption_nonlinear", 0)),
            "attention_load_localization_row_count": int(calibration_matrix["family_counts"].get("attention_load_localization", 0)),
            "residual_energy_stabilization_row_count": int(calibration_matrix["family_counts"].get("residual_energy_stabilization", 0)),
            "calibration_matrix_row_count": int(calibration_matrix["total_rows"]),
            "calibration_matrix_pass_row_count": int(calibration_matrix["total_pass_rows"]),
            "calibration_matrix_family_counts": calibration_matrix["family_counts"],
            "calibration_matrix_family_pass_counts": calibration_matrix["family_pass_counts"],
            "calibration_matrix_group_label": ",".join(
                f"{family}={int(calibration_matrix['family_pass_counts'].get(family, 0))}/{int(calibration_matrix['family_counts'].get(family, 0))}"
                for family in (
                    "concrete_damage",
                    "cyclic_degradation",
                    "bond_interface",
                    "creep_shrinkage",
                    "soil_boundary_nonlinear",
                    "device_dissipation",
                    "foundation_impedance_nonlinear",
                    "contact_link_hysteresis",
                    "panel_zone_joint_response",
                    "wind_dynamic_response",
                    "track_support_viscoelasticity",
                    "vehicle_track_transient_coupling",
                    "tunnel_soil_wave_attenuation",
                    "serviceability_velocity_response",
                    "construction_stage_redistribution",
                    "joint_constraint_transfer",
                    "aeroelastic_serviceability",
                    "heterogeneous_soil_adaptation",
                    "segment_joint_softening",
                    "longitudinal_wave_strain_transfer",
                    "raw_pressure_field_mapping",
                    "phase_assimilation_correction",
                    "multiscale_streaming_refinement",
                    "integrated_vibration_transfer",
                    "resilience_ood_recovery",
                    "boundary_absorption_nonlinear",
                    "attention_load_localization",
                    "residual_energy_stabilization",
                    "phase_latency_projection",
                    "cache_window_adaptation",
                    "whitebox_feedback_stitching",
                    "recovery_residual_relock",
                    "rail_support_contact_modulation",
                    "tunnel_lining_interface_recovery",
                    "panel_feedback_residual_transfer",
                    "wind_pressure_coupled_transfer",
                )
            ),
            "source_family_labels": sorted(set(source_family_labels) | set(rc_lock_physical_families.keys())),
            "benchmark_lock_physical_family_labels": sorted(rc_lock_physical_families.keys()),
            "calibration_matrix_family_source_families": family_source_families,
            "calibration_matrix_family_coverage": {
                "concrete_damage": {
                    "source_count": int(bool(pushover_concrete_rows)) + int(bool(ndtha_concrete_rows)),
                    "source_family_count": int(len(family_source_families["concrete_damage"])),
                    "topology_count": len(_dimension_counter([*pushover_concrete_rows, *ndtha_concrete_rows], "topology_type")),
                    "hazard_count": len(_dimension_counter([*pushover_concrete_rows, *ndtha_concrete_rows], "hazard_type")),
                },
                "cyclic_degradation": {
                    "source_count": int(bool(ndtha_cyclic_rows)),
                    "source_family_count": int(len(family_source_families["cyclic_degradation"])),
                    "topology_count": len(_dimension_counter(ndtha_cyclic_rows, "topology_type")),
                    "hazard_count": len(_dimension_counter(ndtha_cyclic_rows, "hazard_type")),
                    "response_storage_count": len(_dimension_counter(ndtha_cyclic_rows, "response_storage")),
                    "library_probe_present": int(bool(cyclic_library_evidence["library_evidence_pass"])),
                    "library_tag_count": int(len(cyclic_library_evidence["evidence_tags"])),
                    "library_reversal_count": int(cyclic_library_evidence["reversal_count"]),
                    "step_series_case_count": int(cyclic_step_series_evidence["series_case_count"]),
                    "step_series_depth": int(cyclic_step_series_evidence["step_series_depth"]),
                    "wall_slab_case_count": int(cyclic_step_series_evidence["wall_slab_case_count"]),
                    "rc_case_count": int(cyclic_step_series_evidence["rc_case_count"]),
                    "step_series_storage_mode_count": int(len(cyclic_step_series_evidence["response_storage_modes"])),
                },
                "bond_interface": {
                    "source_count": int(bool(pushover_bond_rows)) + int(bool(ndtha_bond_rows)),
                    "source_family_count": int(len(family_source_families["bond_interface"])),
                    "topology_count": len(_dimension_counter([*pushover_bond_rows, *ndtha_bond_rows], "topology_type")),
                    "hazard_count": len(_dimension_counter([*pushover_bond_rows, *ndtha_bond_rows], "hazard_type")),
                },
                "creep_shrinkage": {
                    "source_count": int(bool(construction.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["creep_shrinkage"])),
                    "stage_count": int(construction_summary.get("stage_count", 0) or 0),
                },
                "soil_boundary_nonlinear": {
                    "source_count": int(bool(ssi.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["soil_boundary_nonlinear"])),
                    "topology_count": len(_dimension_counter(ssi_rows, "topology_type")),
                },
                "device_dissipation": {
                    "source_count": int(bool(damper.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["device_dissipation"])),
                    "damper_type_count": len([item for item in (damper_summary.get("damper_types") or []) if str(item).strip()]),
                },
                "foundation_impedance_nonlinear": {
                    "source_count": int(bool(foundation.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["foundation_impedance_nonlinear"])),
                    "link_model_type_count": len([item for item in (foundation_summary.get("foundation_link_model_types") or []) if str(item).strip()]),
                    "soil_link_token_count": len([item for item in (foundation_summary.get("soil_link_contract_tokens") or []) if str(item).strip()]),
                },
                "contact_link_hysteresis": {
                    "source_count": int(bool(contact.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["contact_link_hysteresis"])),
                    "category_count": len([key for key in contact_categories.keys() if str(key).strip()]),
                    "link_model_type_count": len([item for item in (contact_summary.get("link_model_types") or []) if str(item).strip()]),
                },
                "panel_zone_joint_response": {
                    "source_count": int(bool(panel_zone.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["panel_zone_joint_response"])),
                    "source_row_count": int(panel_zone_summary.get("panel_zone_validated_source_row_count_total", 0) or 0),
                },
                "wind_dynamic_response": {
                    "source_count": int(bool(wind.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["wind_dynamic_response"])),
                    "topology_count": len(_dimension_counter(wind_rows, "topology_type")),
                    "material_model_count": len([item for item in (wind_summary.get("material_model_types") or []) if str(item).strip()]),
                },
                "track_support_viscoelasticity": {
                    "source_count": int(bool(track_lf.get("contract_pass", False))) + int(bool(track_irregularity_metrics)),
                    "source_family_count": int(len(family_source_families["track_support_viscoelasticity"])),
                    "irregularity_class_count": int(bool(str(track_irregularity_metrics.get("class", "") or "").strip())),
                    "backend_count": int(bool(str(track_irregularity_metrics.get("preprocess_backend", "") or "").strip())),
                },
                "vehicle_track_transient_coupling": {
                    "source_count": int(bool(moving_load.get("contract_pass", False))) + int(bool(vti_coupled.get("contract_pass", False))) + int(bool(track_dataset.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["vehicle_track_transient_coupling"])),
                    "dataset_source_count": int(bool(track_dataset.get("contract_pass", False))),
                    "coupling_metric_count": int(bool(vti_coupled_metrics)),
                },
                "tunnel_soil_wave_attenuation": {
                    "source_count": int(bool(vibration_attenuation.get("contract_pass", False))) + int(bool(tunnel_dataset.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["tunnel_soil_wave_attenuation"])),
                    "distance_count": int(vibration_attenuation_metrics.get("distance_count", 0) or 0),
                    "dataset_source_count": int(bool(tunnel_dataset.get("contract_pass", False))),
                },
                "serviceability_velocity_response": {
                    "source_count": int(bool(vibration_compliance.get("contract_pass", False))) + int(bool(track_irregularity_metrics)),
                    "source_family_count": int(len(family_source_families["serviceability_velocity_response"])),
                    "standard_count": int(bool(vibration_compliance_checks.get("standard_supported", False))),
                    "irregularity_class_count": int(bool(str(track_irregularity_metrics.get("class", "") or "").strip())),
                },
                "construction_stage_redistribution": {
                    "source_count": int(bool(construction.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["construction_stage_redistribution"])),
                    "stage_count": int(construction_summary.get("stage_count", 0) or 0),
                    "differential_shortening_count": int(bool(construction_checks.get("differential_shortening_detected", False))),
                },
                "joint_constraint_transfer": {
                    "source_count": int(bool(panel_zone.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["joint_constraint_transfer"])),
                    "source_row_count": int(joint_constraint_transfer_evidence["source_row_count"]),
                },
                "aeroelastic_serviceability": {
                    "source_count": int(bool(wind.get("contract_pass", False))) + int(bool(vibration_compliance.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["aeroelastic_serviceability"])),
                    "duration_hours": float(_safe_float(wind_summary.get("duration_hours"))),
                    "pass_ratio": float(_safe_float(vibration_compliance_metrics.get("pass_ratio"))),
                },
                "heterogeneous_soil_adaptation": {
                    "source_count": int(bool(heterogeneous_soil.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["heterogeneous_soil_adaptation"])),
                    "recall": float(_safe_float(heterogeneous_soil_metrics.get("recall"))),
                    "fallback_ratio": float(_safe_float(heterogeneous_soil_metrics.get("fallback_ratio_on_ood"))),
                },
                "segment_joint_softening": {
                    "source_count": int(bool(segment_joint.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["segment_joint_softening"])),
                    "yield_index": float(_safe_float(segment_joint_metrics.get("yield_index"))),
                    "energy_like": float(_safe_float(segment_joint_metrics.get("dissipated_energy_like"))),
                },
                "longitudinal_wave_strain_transfer": {
                    "source_count": int(bool(tunnel_longitudinal.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["longitudinal_wave_strain_transfer"])),
                    "step_count": int(tunnel_longitudinal_metrics.get("step_count", 0) or 0),
                    "max_longitudinal_strain": float(_safe_float(tunnel_longitudinal_metrics.get("max_longitudinal_strain"))),
                },
                "raw_pressure_field_mapping": {
                    "source_count": int(bool(wind_tunnel_mapping.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["raw_pressure_field_mapping"])),
                    "raw_row_count": int(wind_tunnel_mapping_summary.get("raw_row_count", 0) or 0),
                    "mapping_row_count": int(wind_tunnel_mapping_summary.get("mapping_row_count", 0) or 0),
                },
                "phase_assimilation_correction": {
                    "source_count": int(bool(phase_correction.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["phase_assimilation_correction"])),
                    "phase_error_reduction_ratio": float(_safe_float(phase_correction_metrics.get("phase_error_reduction_ratio"))),
                    "post_phase_error_deg": float(_safe_float(phase_correction_metrics.get("post_phase_error_deg"))),
                },
                "multiscale_streaming_refinement": {
                    "source_count": int(bool(multiscale_streaming.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["multiscale_streaming_refinement"])),
                    "recommended_chunk": int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0),
                    "active_nodes_window": int(multiscale_streaming_metrics.get("active_nodes_window", 0) or 0),
                },
                "integrated_vibration_transfer": {
                    "source_count": int(bool(phasee_integrated.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["integrated_vibration_transfer"])),
                    "linked_check_count": int(sum(1 for key in (
                        "E1_substructuring_interface",
                        "E2_vibration_attenuation_model",
                        "E3_vibration_compliance_checker",
                        "E5_whitebox_validation_extension",
                    ) if bool(phasee_integrated_checks.get(key, False)))),
                },
                "resilience_ood_recovery": {
                    "source_count": int(bool(phasef_resilience.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["resilience_ood_recovery"])),
                    "step_count": int(len(phasef_resilience.get("steps") or [])),
                    "linked_check_count": int(sum(1 for key in (
                        "F1_multiscale_l3_streaming",
                        "F2_phase_correction_assimilation",
                        "F3_heterogeneous_soil_ood_gate",
                    ) if bool(phasef_resilience_checks.get(key, False)))),
                },
                "boundary_absorption_nonlinear": {
                    "source_count": int(bool(dynamics_boundary.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["boundary_absorption_nonlinear"])),
                    "support_type_count": len([item for item in (dynamics_boundary_supports_summary.get("support_types") or []) if str(item).strip()]),
                    "fixed_count": int(dynamics_boundary_supports_summary.get("fixed_count", 0) or 0),
                },
                "attention_load_localization": {
                    "source_count": int(bool(moving_load_attention.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["attention_load_localization"])),
                    "support_span": int(moving_load_attention_metrics.get("support_high_count", 0) or 0) - int(moving_load_attention_metrics.get("support_low_count", 0) or 0),
                    "peak_value": float(_safe_float(moving_load_attention_metrics.get("peak_value"))),
                },
                "residual_energy_stabilization": {
                    "source_count": int(bool(physics_residual.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["residual_energy_stabilization"])),
                    "solver_count": int(bool(str(physics_residual_metrics.get("solver", "") or "").strip())),
                    "node_count": int(physics_residual_metrics.get("node_count", 0) or 0),
                },
                "panel_feedback_residual_transfer": {
                    "source_count": int(bool(panel_zone.get("contract_pass", False)))
                    + int(bool(phasee_integrated.get("contract_pass", False)))
                    + int(bool(physics_residual.get("contract_pass", False))),
                    "source_family_count": int(len(family_source_families["panel_feedback_residual_transfer"])),
                    "bridge_ready": int(bool(panel_zone_surface.get("bridge_complete", False))),
                    "bridge_mode": str(panel_zone_surface.get("bridge_mode", "") or ""),
                    "validated_row_count": int(panel_zone_summary.get("panel_zone_validated_source_row_count_total", 0) or 0),
                    "residual_reduction": float(
                        _safe_float(physics_residual_metrics.get("residual_norm_before"))
                        - _safe_float(physics_residual_metrics.get("residual_norm_after"))
                    ),
                },
            },
            "max_concrete_damage_mean": float(
                max(
                    [row["compression_damage_mean"] for row in [*pushover_concrete_rows, *ndtha_concrete_rows]]
                    or [0.0]
                )
            ),
            "max_bond_slip_index_mean": float(
                max(
                    [row["bond_slip_index_mean"] for row in [*pushover_bond_rows, *ndtha_bond_rows]]
                    or [0.0]
                )
            ),
            "max_cyclic_residual_drift_ratio_pct": float(
                max((abs(float(row["residual_drift_ratio_pct"])) for row in ndtha_cyclic_rows), default=0.0)
            ),
            "mean_creep_index": float(_safe_float(construction_summary.get("mean_creep_index"))),
            "mean_shrinkage_index": float(_safe_float(construction_summary.get("mean_shrinkage_index"))),
            "soil_boundary_soil_profile": str(ssi_summary.get("soil_profile", "") or ""),
            "device_damper_type_count": len([item for item in (damper_summary.get("damper_types") or []) if str(item).strip()]),
        }

        summary_line = (
            f"Material constitutive gate: {'PASS' if contract_pass else 'CHECK'} | "
            f"concrete_damage={'yes' if concrete_damage_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['concrete_damage']}/{calibration_matrix['family_counts']['concrete_damage']},"
            f"max={summary['max_concrete_damage_mean']:.3f}) | "
            f"cyclic_degradation={'yes' if cyclic_degradation_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['cyclic_degradation']}/{calibration_matrix['family_counts']['cyclic_degradation']},"
            f"residual_max={summary['max_cyclic_residual_drift_ratio_pct']:.3f}%,"
            f"lib=rev{summary['cyclic_library_reversal_count']}/"
            f"pinch{summary['cyclic_library_min_pinching_ratio']:.2f}/"
            f"crush{summary['cyclic_library_max_crushing_ratio']:.2f}/"
            f"series={summary['cyclic_step_series_case_count']}/{summary['cyclic_step_series_response_case_count']}"
            f"@{summary['cyclic_step_series_depth']}/"
            f"wall={summary['cyclic_wall_slab_step_series_case_count']}/"
            f"rc={summary['cyclic_rc_step_series_case_count']}) | "
            f"bond_interface={'yes' if bond_interface_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['bond_interface']}/{calibration_matrix['family_counts']['bond_interface']},"
            f"bond_max={summary['max_bond_slip_index_mean']:.3f}) | "
            f"creep_shrinkage={'yes' if creep_shrinkage_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['creep_shrinkage']}/{calibration_matrix['family_counts']['creep_shrinkage']},"
            f"mean={summary['mean_creep_index']:.3f}/{summary['mean_shrinkage_index']:.3f}) | "
            f"soil_boundary_nonlinear={'yes' if soil_boundary_nonlinear_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['soil_boundary_nonlinear']}/{calibration_matrix['family_counts']['soil_boundary_nonlinear']},"
            f"profile={summary['soil_boundary_soil_profile'] or 'n/a'}) | "
            f"device_dissipation={'yes' if device_dissipation_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['device_dissipation']}/{calibration_matrix['family_counts']['device_dissipation']},"
            f"types={summary['device_damper_type_count']}) | "
            f"foundation_impedance_nonlinear={'yes' if foundation_impedance_nonlinear_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['foundation_impedance_nonlinear']}/{calibration_matrix['family_counts']['foundation_impedance_nonlinear']},"
            f"links={summary['calibration_matrix_family_coverage']['foundation_impedance_nonlinear']['link_model_type_count']}) | "
            f"contact_link_hysteresis={'yes' if contact_link_hysteresis_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['contact_link_hysteresis']}/{calibration_matrix['family_counts']['contact_link_hysteresis']},"
            f"cats={summary['calibration_matrix_family_coverage']['contact_link_hysteresis']['category_count']}) | "
            f"panel_zone_joint_response={'yes' if panel_zone_joint_response_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['panel_zone_joint_response']}/{calibration_matrix['family_counts']['panel_zone_joint_response']},"
            f"rows={summary['panel_zone_joint_response_row_count']}) | "
            f"wind_dynamic_response={'yes' if wind_dynamic_response_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['wind_dynamic_response']}/{calibration_matrix['family_counts']['wind_dynamic_response']},"
            f"topo={summary['calibration_matrix_family_coverage']['wind_dynamic_response']['topology_count']}) | "
            f"track_support_viscoelasticity={'yes' if track_support_viscoelasticity_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['track_support_viscoelasticity']}/{calibration_matrix['family_counts']['track_support_viscoelasticity']},"
            f"class={str(track_irregularity_metrics.get('class', '') or 'n/a')}) | "
            f"vehicle_track_transient_coupling={'yes' if vehicle_track_transient_coupling_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['vehicle_track_transient_coupling']}/{calibration_matrix['family_counts']['vehicle_track_transient_coupling']},"
            f"iters={_safe_float(vti_coupled_metrics.get('mean_coupling_iters')):.2f}) | "
            f"tunnel_soil_wave_attenuation={'yes' if tunnel_soil_wave_attenuation_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['tunnel_soil_wave_attenuation']}/{calibration_matrix['family_counts']['tunnel_soil_wave_attenuation']},"
            f"dist={int(vibration_attenuation_metrics.get('distance_count', 0) or 0)}) | "
            f"serviceability_velocity_response={'yes' if serviceability_velocity_response_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['serviceability_velocity_response']}/{calibration_matrix['family_counts']['serviceability_velocity_response']},"
            f"pass_ratio={_safe_float(vibration_compliance_metrics.get('pass_ratio')):.3f}) | "
            f"construction_stage_redistribution={'yes' if construction_stage_redistribution_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['construction_stage_redistribution']}/{calibration_matrix['family_counts']['construction_stage_redistribution']},"
            f"diff={int(bool(construction_checks.get('differential_shortening_detected', False)))}) | "
            f"joint_constraint_transfer={'yes' if joint_constraint_transfer_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['joint_constraint_transfer']}/{calibration_matrix['family_counts']['joint_constraint_transfer']},"
            f"rows={int(joint_constraint_transfer_evidence['source_row_count'])}) | "
            f"aeroelastic_serviceability={'yes' if aeroelastic_serviceability_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['aeroelastic_serviceability']}/{calibration_matrix['family_counts']['aeroelastic_serviceability']},"
            f"pass_ratio={_safe_float(vibration_compliance_metrics.get('pass_ratio')):.3f}) | "
            f"heterogeneous_soil_adaptation={'yes' if heterogeneous_soil_adaptation_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['heterogeneous_soil_adaptation']}/{calibration_matrix['family_counts']['heterogeneous_soil_adaptation']},"
            f"recall={_safe_float(heterogeneous_soil_metrics.get('recall')):.3f}) | "
            f"segment_joint_softening={'yes' if segment_joint_softening_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['segment_joint_softening']}/{calibration_matrix['family_counts']['segment_joint_softening']},"
            f"yield={_safe_float(segment_joint_metrics.get('yield_index')):.3f}) | "
            f"longitudinal_wave_strain_transfer={'yes' if longitudinal_wave_strain_transfer_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['longitudinal_wave_strain_transfer']}/{calibration_matrix['family_counts']['longitudinal_wave_strain_transfer']},"
            f"strain={_safe_float(tunnel_longitudinal_metrics.get('max_longitudinal_strain')):.6f}) | "
            f"raw_pressure_field_mapping={'yes' if raw_pressure_field_mapping_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['raw_pressure_field_mapping']}/{calibration_matrix['family_counts']['raw_pressure_field_mapping']},"
            f"mapped={int(wind_tunnel_mapping_summary.get('mapping_row_count', 0) or 0)}) | "
            f"phase_assimilation_correction={'yes' if phase_assimilation_correction_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['phase_assimilation_correction']}/{calibration_matrix['family_counts']['phase_assimilation_correction']},"
            f"ratio={_safe_float(phase_correction_metrics.get('phase_error_reduction_ratio')):.3f}) | "
            f"multiscale_streaming_refinement={'yes' if multiscale_streaming_refinement_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['multiscale_streaming_refinement']}/{calibration_matrix['family_counts']['multiscale_streaming_refinement']},"
            f"chunk={int(multiscale_streaming_metrics.get('recommended_chunk', 0) or 0)}) | "
            f"integrated_vibration_transfer={'yes' if integrated_vibration_transfer_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['integrated_vibration_transfer']}/{calibration_matrix['family_counts']['integrated_vibration_transfer']},"
            f"checks={summary['calibration_matrix_family_coverage']['integrated_vibration_transfer']['linked_check_count']}) | "
            f"resilience_ood_recovery={'yes' if resilience_ood_recovery_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['resilience_ood_recovery']}/{calibration_matrix['family_counts']['resilience_ood_recovery']},"
            f"steps={summary['calibration_matrix_family_coverage']['resilience_ood_recovery']['step_count']}) | "
            f"boundary_absorption_nonlinear={'yes' if boundary_absorption_nonlinear_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['boundary_absorption_nonlinear']}/{calibration_matrix['family_counts']['boundary_absorption_nonlinear']},"
            f"supports={summary['calibration_matrix_family_coverage']['boundary_absorption_nonlinear']['support_type_count']}) | "
            f"attention_load_localization={'yes' if attention_load_localization_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['attention_load_localization']}/{calibration_matrix['family_counts']['attention_load_localization']},"
            f"peak={_safe_float(moving_load_attention_metrics.get('peak_value')):.3f}) | "
            f"residual_energy_stabilization={'yes' if residual_energy_stabilization_pass else 'no'}"
            f"(matrix={calibration_matrix['family_pass_counts']['residual_energy_stabilization']}/{calibration_matrix['family_counts']['residual_energy_stabilization']},"
            f"solver={str(physics_residual_metrics.get('solver', '') or 'n/a')}) | "
            f"matrix={calibration_matrix['total_pass_rows']}/{calibration_matrix['total_rows']} | "
            f"groups={summary['calibration_matrix_group_label']} | "
            "coverage="
            f"cd[t={summary['calibration_matrix_family_coverage']['concrete_damage']['topology_count']},"
            f"h={summary['calibration_matrix_family_coverage']['concrete_damage']['hazard_count']},"
            f"s={summary['calibration_matrix_family_coverage']['concrete_damage']['source_count']},"
            f"sf={summary['calibration_matrix_family_coverage']['concrete_damage']['source_family_count']}],"
            f"cyc[t={summary['calibration_matrix_family_coverage']['cyclic_degradation']['topology_count']},"
            f"h={summary['calibration_matrix_family_coverage']['cyclic_degradation']['hazard_count']},"
            f"store={summary['calibration_matrix_family_coverage']['cyclic_degradation']['response_storage_count']},"
            f"sf={summary['calibration_matrix_family_coverage']['cyclic_degradation']['source_family_count']}],"
            f"bond[t={summary['calibration_matrix_family_coverage']['bond_interface']['topology_count']},"
            f"h={summary['calibration_matrix_family_coverage']['bond_interface']['hazard_count']},"
            f"s={summary['calibration_matrix_family_coverage']['bond_interface']['source_count']},"
            f"sf={summary['calibration_matrix_family_coverage']['bond_interface']['source_family_count']}] | "
            "core="
            f"cd[states={summary['concrete_damage_library_state_tag_count']},res={summary['concrete_damage_library_residual_strength_ratio']:.2f}],"
            f"cyc[states={summary['cyclic_library_restoring_state_tag_count']},tags={summary['cyclic_library_evidence_tag_count']}],"
            f"bond[states={summary['bond_interface_library_state_tag_count']},slip={summary['bond_interface_library_max_slip_ratio']:.2f},res={summary['bond_interface_library_residual_force_ratio']:.2f}]"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-material-constitutive-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                **input_payload,
                "input_sha256": {
                    "pushover_stress_report": _sha256(pushover_path) if pushover_path.exists() else "",
                    "ndtha_stress_report": _sha256(ndtha_path) if ndtha_path.exists() else "",
                    "rc_benchmark_lock_report": _sha256(rc_lock_path) if rc_lock_path.exists() else "",
                    "construction_sequence_report": _sha256(construction_path) if construction_path.exists() else "",
                    "ssi_boundary_report": _sha256(ssi_path) if ssi_path.exists() else "",
                    "damper_validation_report": _sha256(damper_path) if damper_path.exists() else "",
                    "foundation_soil_link_gate_report": _sha256(foundation_path) if foundation_path.exists() else "",
                    "structural_contact_validation_report": _sha256(contact_path) if contact_path.exists() else "",
                    "panel_zone_clash_report": _sha256(panel_zone_path) if panel_zone_path.exists() else "",
                    "wind_time_history_gate_report": _sha256(wind_path) if wind_path.exists() else "",
                    "vibration_attenuation_report": _sha256(vibration_attenuation_path) if vibration_attenuation_path.exists() else "",
                    "vibration_compliance_report": _sha256(vibration_compliance_path) if vibration_compliance_path.exists() else "",
                    "track_lf_solver_report": _sha256(track_lf_path) if track_lf_path.exists() else "",
                    "moving_load_integrator_report": _sha256(moving_load_path) if moving_load_path.exists() else "",
                    "vti_coupled_solver_report": _sha256(vti_coupled_path) if vti_coupled_path.exists() else "",
                    "track_irregularity_report": _sha256(track_irregularity_path) if track_irregularity_path.exists() else "",
                    "track_dynamics_dataset_report": _sha256(track_dataset_path) if track_dataset_path.exists() else "",
                    "tunnel_dynamics_dataset_report": _sha256(tunnel_dataset_path) if tunnel_dataset_path.exists() else "",
                    "heterogeneous_soil_ood_report": _sha256(heterogeneous_soil_path) if heterogeneous_soil_path.exists() else "",
                    "tunnel_segment_joint_report": _sha256(segment_joint_path) if segment_joint_path.exists() else "",
                    "tunnel_seismic_longitudinal_report": _sha256(tunnel_longitudinal_path) if tunnel_longitudinal_path.exists() else "",
                    "wind_tunnel_raw_mapping_report": _sha256(wind_tunnel_mapping_path) if wind_tunnel_mapping_path.exists() else "",
                    "phase_correction_assimilation_report": _sha256(phase_correction_path) if phase_correction_path.exists() else "",
                    "multiscale_l3_streaming_report": _sha256(multiscale_streaming_path) if multiscale_streaming_path.exists() else "",
                    "phasee_integrated_summary_report": _sha256(phasee_integrated_path) if phasee_integrated_path.exists() else "",
                    "phasef_resilience_summary_report": _sha256(phasef_resilience_path) if phasef_resilience_path.exists() else "",
                    "dynamics_boundary_report": _sha256(dynamics_boundary_path) if dynamics_boundary_path.exists() else "",
                    "moving_load_attention_report": _sha256(moving_load_attention_path) if moving_load_attention_path.exists() else "",
                    "physics_residual_contract_report": _sha256(physics_residual_path) if physics_residual_path.exists() else "",
                    "rc_benchmark_lock_cases": _sha256(rc_lock_cases_path) if rc_lock_cases_path.exists() else "",
                    "benchmark_cases": {str(path): _sha256(path) if path.exists() else "" for path in benchmark_case_paths},
                },
            },
            "checks": checks,
            "summary": summary,
            "evidence": {
                "concrete_damage_rows": [*pushover_concrete_rows, *ndtha_concrete_rows],
                "concrete_damage_library_evidence": concrete_damage_library_evidence,
                "cyclic_degradation_rows": ndtha_cyclic_rows,
                "bond_interface_rows": [*pushover_bond_rows, *ndtha_bond_rows],
                "cyclic_library_evidence": cyclic_library_evidence,
                "cyclic_step_series_evidence": cyclic_step_series_evidence,
                "bond_interface_library_evidence": bond_interface_library_evidence,
                "bond_interface_cyclic_evidence": bond_interface_cyclic_evidence,
                "creep_shrinkage_summary": construction_summary,
                "soil_boundary_rows": ssi_rows,
                "device_dissipation_summary": damper_summary,
                "foundation_impedance_summary": foundation_summary,
                "contact_link_validation_summary": contact_summary,
                "panel_zone_joint_response_summary": panel_zone_summary,
                "panel_zone_joint_response_gate_surface": panel_zone_surface,
                "wind_dynamic_response_summary": wind_summary,
                "vibration_attenuation_summary": {
                    "checks": vibration_attenuation_checks,
                    "metrics": vibration_attenuation_metrics,
                },
                "vibration_compliance_summary": {
                    "checks": vibration_compliance_checks,
                    "metrics": vibration_compliance_metrics,
                },
                "track_support_viscoelasticity_summary": {
                    "checks": track_lf_checks,
                    "summary": track_lf_summary,
                    "track_irregularity_metrics": track_irregularity_metrics,
                },
                "vehicle_track_transient_coupling_summary": {
                    "moving_load_checks": moving_load_checks,
                    "moving_load_metrics": moving_load_metrics,
                    "vti_coupled_checks": vti_coupled_checks,
                    "vti_coupled_metrics": vti_coupled_metrics,
                    "track_dataset_checks": track_dataset_checks,
                    "track_dataset_metrics": track_dataset_metrics,
                },
                "tunnel_soil_wave_attenuation_summary": {
                    "tunnel_dataset_checks": tunnel_dataset_checks,
                    "tunnel_dataset_metrics": tunnel_dataset_metrics,
                },
                "heterogeneous_soil_adaptation_summary": {
                    "checks": heterogeneous_soil_checks,
                    "metrics": heterogeneous_soil_metrics,
                },
                "segment_joint_softening_summary": {
                    "checks": segment_joint_checks,
                    "metrics": segment_joint_metrics,
                },
                "longitudinal_wave_strain_transfer_summary": {
                    "checks": tunnel_longitudinal_checks,
                    "metrics": tunnel_longitudinal_metrics,
                },
                "raw_pressure_field_mapping_summary": {
                    "checks": wind_tunnel_mapping_checks,
                    "summary": wind_tunnel_mapping_summary,
                },
                "phase_assimilation_correction_summary": {
                    "checks": phase_correction_checks,
                    "metrics": phase_correction_metrics,
                },
                "multiscale_streaming_refinement_summary": {
                    "checks": multiscale_streaming_checks,
                    "metrics": multiscale_streaming_metrics,
                },
                "integrated_vibration_transfer_summary": {
                    "checks": phasee_integrated_checks,
                },
                "resilience_ood_recovery_summary": {
                    "checks": phasef_resilience_checks,
                    "steps": phasef_resilience.get("steps") or [],
                },
                "boundary_absorption_nonlinear_summary": {
                    "supports_summary": dynamics_boundary_supports_summary,
                    "damping_summary": dynamics_boundary_damping_summary,
                },
                "attention_load_localization_summary": {
                    "checks": moving_load_attention_checks,
                    "metrics": moving_load_attention_metrics,
                },
                "residual_energy_stabilization_summary": {
                    "checks": physics_residual_checks,
                    "metrics": physics_residual_metrics,
                    "source": physics_residual_source,
                },
                "wind_dynamic_response_rows": wind_rows,
                "calibration_matrix": calibration_matrix,
                "calibration_benchmark_matrix": calibration_matrix,
            },
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "limitations": [
                "This gate summarizes checked-in constitutive evidence and does not claim full UMAT/VUMAT parity.",
                "Cyclic degradation is evidenced through dynamic reversal, residual-drift traces, nonlinear response storage, and a bounded library-backed cyclic concrete probe rather than a standalone constitutive calibration package.",
                "Bond interface is evidenced through benchmark lock, construction-sequence continuity, and bond-slip indices rather than a separate contact-interface finite element formulation.",
                "Expanded families such as creep-shrinkage, soil-boundary nonlinearity, and device dissipation are surfaced through checked-in gate evidence rather than full standalone calibration notebooks.",
                "Foundation/contact/panel-zone/wind families summarize checked-in physical-response contracts and do not claim full standalone constitutive subroutine parity.",
                "Panel-zone joint response is topology-projected/internal-engine verified evidence; true external 3D clash validation remains a separate boundary.",
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        if not contract_pass:
            raise SystemExit(1)
    except InputContractError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-material-constitutive-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {},
            "summary": {},
            "summary_line": "Material constitutive gate: CHECK | invalid input",
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(payload["summary_line"])
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
