#!/usr/bin/env python3
"""Summarize broader surface-style FE interaction benchmark evidence from checked-in contracts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "surface-style FE interaction evidence is present across shell/diaphragm transfer, interface continuity, soil/foundation impedance, transport coupling, tunnel interaction, joint-panel interaction, SSI, and direct contact families",
    "ERR_INVALID_INPUT": "invalid surface interaction benchmark input",
    "ERR_SHELL_SURFACE": "shell/slab surface-coupling evidence is incomplete",
    "ERR_INTERFACE_TRANSFER": "interface transfer evidence is incomplete",
    "ERR_INTERFACE_GAP": "interface gap continuity evidence is incomplete",
    "ERR_FOUNDATION": "foundation/soil interaction evidence is incomplete",
    "ERR_TRACK_SLAB": "track-slab interaction evidence is incomplete",
    "ERR_VEHICLE_TRACK": "vehicle-track interaction evidence is incomplete",
    "ERR_TUNNEL_LINING_SOIL": "tunnel-lining/soil interaction evidence is incomplete",
    "ERR_JOINT_PANEL": "joint-panel interaction evidence is incomplete",
    "ERR_SSI_BOUNDARY": "SSI boundary interaction evidence is incomplete",
    "ERR_SOIL_TUNNEL": "soil-tunnel interaction evidence is incomplete",
    "ERR_DIRECT_CONTACT": "direct structural contact family evidence is incomplete",
    "ERR_GENERAL_FE_COUPLING": "general FE coupling evidence beyond contact-centric interaction is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "flexible_diaphragm_report",
        "substructuring_interface_report",
        "sync_stress_report",
        "foundation_soil_link_gate_report",
        "moving_load_integrator_report",
        "vti_coupled_solver_report",
        "track_dynamics_dataset_report",
        "tunnel_dynamics_dataset_report",
        "panel_zone_clash_report",
        "ssi_boundary_report",
        "soil_tunnel_ssi_report",
        "structural_contact_gate_report",
        "benchmark_cases",
        "out",
    ],
    "properties": {
        "flexible_diaphragm_report": {"type": "string", "minLength": 1},
        "substructuring_interface_report": {"type": "string", "minLength": 1},
        "sync_stress_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_report": {"type": "string", "minLength": 1},
        "vti_coupled_solver_report": {"type": "string", "minLength": 1},
        "track_dynamics_dataset_report": {"type": "string", "minLength": 1},
        "tunnel_dynamics_dataset_report": {"type": "string", "minLength": 1},
        "panel_zone_clash_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "soil_tunnel_ssi_report": {"type": "string", "minLength": 1},
        "structural_contact_gate_report": {"type": "string", "minLength": 1},
        "dynamics_boundary_report": {"type": "string", "minLength": 1},
        "moving_load_attention_report": {"type": "string", "minLength": 1},
        "physics_residual_contract_report": {"type": "string", "minLength": 1},
        "phase_correction_assimilation_report": {"type": "string", "minLength": 1},
        "multiscale_l3_streaming_report": {"type": "string", "minLength": 1},
        "phasee_integrated_summary_report": {"type": "string", "minLength": 1},
        "phasef_resilience_summary_report": {"type": "string", "minLength": 1},
        "benchmark_cases": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
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



def _bool(value: Any) -> bool:
    return bool(value)


def _finite_number(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric)


def _finite_positive(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0.0


def _all_true(payload: dict[str, Any], *keys: str) -> bool:
    return all(_bool(payload.get(key, False)) for key in keys)


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


def _row(label: str, *, ready: bool, source: str, contract: str, note: str) -> dict[str, Any]:
    return {
        "label": str(label),
        "ready": bool(ready),
        "source": str(source),
        "contract": str(contract),
        "note": str(note),
    }


def _direct_contact_contract(category: str) -> str:
    normalized = str(category or "").strip().lower()
    mapping = {
        "gap": "normal_gap_unilateral",
        "uplift": "uplift_seat_unilateral",
        "compression-only": "compression_only_penalty",
        "bearing": "bearing_bilinear",
        "friction": "coulomb_friction",
        "pounding": "kelvin_voigt_pounding",
    }
    return mapping.get(normalized, normalized or "unknown")


def _direct_contact_note(category_row: dict[str, Any]) -> str:
    category = str(category_row.get("category", "") or "unknown").strip()
    implementation_present = bool(category_row.get("implementation_present", False))
    validated = bool(category_row.get("validated", False))
    ready = bool(category_row.get("ready", False))
    return (
        f"category={category} | implementation={'yes' if implementation_present else 'no'} | "
        f"validated={'yes' if validated else 'no'} | ready={'yes' if ready else 'no'}"
    )


def _contact_category_ready(contact_rows_by_name: dict[str, dict[str, Any]], category: str) -> bool:
    return bool(contact_rows_by_name.get(str(category or "").strip().lower(), {}).get("ready", False))


def _foundation_required_link_models_ready(summary: dict[str, Any]) -> bool:
    link_models = {
        str(item).strip()
        for item in (summary.get("foundation_link_model_types") or [])
        if str(item).strip()
    }
    required_models = {
        str(item).strip()
        for item in (summary.get("required_foundation_link_models") or [])
        if str(item).strip()
    }
    missing_models = [
        str(item).strip()
        for item in (summary.get("missing_foundation_link_models") or [])
        if str(item).strip()
    ]
    return bool(required_models and required_models.issubset(link_models) and not missing_models)


def _family_group_key(label: str) -> str:
    value = str(label or "")
    if value.startswith("phase_assimilation_coupling_"):
        return "phase_assimilation_coupling"
    if value.startswith("streaming_partition_coupling_"):
        return "streaming_partition_coupling"
    if value.startswith("integrated_vibration_coupling_"):
        return "integrated_vibration_coupling"
    if value.startswith("resilience_recovery_coupling_"):
        return "resilience_recovery_coupling"
    if value.startswith("modal_transfer_"):
        return "modal_transfer"
    if value.startswith("kinematic_coupling_"):
        return "kinematic_coupling"
    if value.startswith("constraint_bridge_"):
        return "constraint_bridge"
    if value.startswith("wave_radiation_"):
        return "wave_radiation"
    if value.startswith("boundary_absorption_coupling_"):
        return "boundary_absorption_coupling"
    if value.startswith("attention_guided_transfer_"):
        return "attention_guided_transfer"
    if value.startswith("residual_stabilization_coupling_"):
        return "residual_stabilization_coupling"
    if value.startswith("solver_feedback_coupling_"):
        return "solver_feedback_coupling"
    if value.startswith("multiphysics_coupling_"):
        return "multiphysics_coupling"
    if value.startswith("explicit_shear_transfer_"):
        return "explicit_shear_transfer"
    if value.startswith("phase_latency_coupling_"):
        return "phase_latency_coupling"
    if value.startswith("cache_window_coupling_"):
        return "cache_window_coupling"
    if value.startswith("whitebox_feedback_coupling_"):
        return "whitebox_feedback_coupling"
    if value.startswith("recovery_residual_coupling_"):
        return "recovery_residual_coupling"
    if value.startswith("support_contact_modulation_coupling_"):
        return "support_contact_modulation_coupling"
    if value.startswith("lining_recovery_coupling_"):
        return "lining_recovery_coupling"
    if value.startswith("panel_feedback_coupling_"):
        return "panel_feedback_coupling"
    if value.startswith("pressure_mapping_coupling_"):
        return "pressure_mapping_coupling"
    if value.startswith("shell_shell_"):
        return "shell_shell"
    if value.startswith("shell_wall_"):
        return "shell_wall"
    if value.startswith("footing_soil_"):
        return "footing_soil"
    if value.startswith("track_slab_"):
        return "track_slab"
    if value.startswith("vehicle_track_"):
        return "vehicle_track"
    if value.startswith("tunnel_lining_soil_"):
        return "tunnel_lining_soil"
    if value.startswith("joint_panel_"):
        return "joint_panel"
    if value.startswith("direct_contact_"):
        return "direct_structural_contact"
    if value.startswith("ssi_"):
        return "ssi"
    if value.startswith("soil_tunnel_"):
        return "soil_tunnel"
    return "other"


def _family_group_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    order = (
        "phase_assimilation_coupling",
        "streaming_partition_coupling",
        "integrated_vibration_coupling",
        "resilience_recovery_coupling",
        "modal_transfer",
        "kinematic_coupling",
        "constraint_bridge",
        "wave_radiation",
        "boundary_absorption_coupling",
        "attention_guided_transfer",
        "residual_stabilization_coupling",
        "solver_feedback_coupling",
        "multiphysics_coupling",
        "explicit_shear_transfer",
        "phase_latency_coupling",
        "cache_window_coupling",
        "whitebox_feedback_coupling",
        "recovery_residual_coupling",
        "support_contact_modulation_coupling",
        "lining_recovery_coupling",
        "panel_feedback_coupling",
        "pressure_mapping_coupling",
        "shell_shell",
        "shell_wall",
        "footing_soil",
        "track_slab",
        "vehicle_track",
        "tunnel_lining_soil",
        "joint_panel",
        "ssi",
        "soil_tunnel",
        "direct_structural_contact",
    )
    summary: dict[str, dict[str, Any]] = {}
    for key in order:
        group_rows = [row for row in rows if _family_group_key(str(row.get("label", ""))) == key]
        summary[key] = {
            "ready_count": sum(1 for row in group_rows if bool(row.get("ready", False))),
            "total_count": len(group_rows),
            "labels": [str(row.get("label", "")) for row in group_rows],
        }
    return summary


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value))
    return "_".join(part for part in normalized.split("_") if part) or "unknown"


def _numeric_slug(value: Any, unit: str = "") -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _slugify(f"{value}{unit}")
    return _slugify(f"{numeric:g}{unit}")


def _load_benchmark_case_rows(case_paths: list[Path]) -> list[dict[str, Any]]:
    deduped_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in case_paths:
        payload = _load_json(path)
        rows = payload.get("cases")
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            source_family = _infer_source_family(row, payload, path)
            case_id = str(row.get("case_id", "") or "").strip() or f"{path.stem}-{index + 1:04d}"
            topology_type = str(row.get("topology_type", "") or "").strip()
            element_mix = _infer_element_mix(row)
            hazard_type = str(row.get("hazard_type", "") or "").strip()
            split = str(row.get("split", "") or "").strip()
            ood_tag = str(row.get("ood_tag", "") or "").strip()
            metric_source = str(row.get("metric_source", "") or "").strip()
            source_member = str(row.get("source_member", "") or "").strip()
            benchmark_row = {
                "case_id": case_id,
                "case_slug": _slugify(case_id),
                "source_family": source_family,
                "source_slug": _slugify(source_family),
                "topology_type": topology_type,
                "element_mix": element_mix,
                "hazard_type": hazard_type,
                "split": split,
                "ood_tag": ood_tag,
                "metric_source": metric_source,
                "source_member": source_member,
                "path": str(path),
            }
            dedupe_key = (source_family, case_id)
            existing = deduped_rows.get(dedupe_key)
            if existing is None:
                deduped_rows[dedupe_key] = benchmark_row
                continue
            for key, value in benchmark_row.items():
                if not existing.get(key) and value:
                    existing[key] = value
    return sorted(
        deduped_rows.values(),
        key=lambda row: (
            str(row.get("source_family", "")),
            str(row.get("case_id", "")),
            str(row.get("topology_type", "")),
        ),
    )


def _aggregate_source_family_cases(case_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for row in case_rows:
        if not isinstance(row, dict):
            continue
        source_family = str(row.get("source_family", "") or "").strip()
        if not source_family:
            continue
        family = families.setdefault(
            source_family,
            {
                "case_count": 0,
                "element_mix_counts": Counter(),
                "topology_counts": Counter(),
            },
        )
        family["case_count"] += 1
        mix = str(row.get("element_mix", "") or "").strip()
        topology = str(row.get("topology_type", "") or "").strip()
        if mix:
            family["element_mix_counts"][mix] += 1
        if topology:
            family["topology_counts"][topology] += 1
    return families


def _benchmark_case_note(row: dict[str, Any]) -> str:
    fragments = [
        f"case_id={str(row.get('case_id', '') or '')}",
        f"source_family={str(row.get('source_family', '') or '')}",
        f"topology={str(row.get('topology_type', '') or 'n/a')}",
        f"element_mix={str(row.get('element_mix', '') or 'n/a')}",
    ]
    for field in ("hazard_type", "split", "ood_tag", "metric_source"):
        value = str(row.get(field, "") or "").strip()
        if value:
            fragments.append(f"{field}={value}")
    return " | ".join(fragments)


def _case_supports_shell_surface(row: dict[str, Any]) -> bool:
    return str(row.get("element_mix", "") or "").strip() == "shell_beam_mix"


def _case_supports_shell_wall(row: dict[str, Any]) -> bool:
    topology_type = str(row.get("topology_type", "") or "").strip().lower()
    return bool(
        str(row.get("element_mix", "") or "").strip() == "shell_beam_mix"
        or topology_type in {"wall-frame", "shell-wall"}
    )


def _case_supports_footing_soil(row: dict[str, Any]) -> bool:
    return str(row.get("topology_type", "") or "").strip().lower() == "outrigger"


def _family_case_rows(
    case_rows: list[dict[str, Any]],
    *,
    label_prefix: str,
    ready: bool,
    predicate: Callable[[dict[str, Any]], bool],
    contract: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_row in case_rows:
        if not predicate(case_row):
            continue
        rows.append(
            _row(
                f"{label_prefix}_case_{str(case_row.get('source_slug', '') or '')}_{str(case_row.get('case_slug', '') or '')}",
                ready=ready,
                source="commercial_benchmark_cases",
                contract=contract,
                note=_benchmark_case_note(case_row),
            )
        )
    return rows


def _family_dimension_rows(
    case_rows: list[dict[str, Any]],
    *,
    label_prefix: str,
    ready: bool,
    predicate: Callable[[dict[str, Any]], bool],
    field: str,
    label_name: str,
    contract: str,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for case_row in case_rows:
        if not predicate(case_row):
            continue
        value = str(case_row.get(field, "") or "").strip()
        if value:
            counts[value] += 1
    return [
        _row(
            f"{label_prefix}_{label_name}_{_slugify(value)}",
            ready=ready,
            source="commercial_benchmark_cases",
            contract=contract,
            note=f"{label_name}={value} | cases={counts[value]}",
        )
        for value in sorted(counts)
    ]


def _shell_wall_family_ready(
    family_payload: dict[str, Any],
    *,
    interface_transfer_ready: bool,
    interface_gap_ready: bool,
) -> bool:
    topology_counts = family_payload.get("topology_counts", Counter())
    element_mix_counts = family_payload.get("element_mix_counts", Counter())
    return bool(
        (interface_transfer_ready or interface_gap_ready)
        and (
            int(topology_counts.get("wall-frame", 0)) >= 1
            or int(element_mix_counts.get("shell_beam_mix", 0)) >= 1
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flexible-diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    parser.add_argument("--substructuring-interface-report", default="implementation/phase1/substructuring_interface_report.json")
    parser.add_argument("--sync-stress-report", default="implementation/phase1/sync_stress_gate_report.json")
    parser.add_argument("--foundation-soil-link-gate-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    parser.add_argument("--moving-load-integrator-report", default="implementation/phase1/moving_load_integrator_report.json")
    parser.add_argument("--vti-coupled-solver-report", default="implementation/phase1/vti_coupled_solver_report.json")
    parser.add_argument("--track-dynamics-dataset-report", default="implementation/phase1/track_dynamics_dataset_report.json")
    parser.add_argument("--tunnel-dynamics-dataset-report", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    parser.add_argument("--panel-zone-clash-report", default="implementation/phase1/panel_zone_clash_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--soil-tunnel-ssi-report", default="implementation/phase1/soil_tunnel_ssi_report.json")
    parser.add_argument("--structural-contact-gate-report", default="implementation/phase1/structural_contact_gate_report.json")
    parser.add_argument("--dynamics-boundary-report", default="implementation/phase1/dynamics_boundary_report.json")
    parser.add_argument("--moving-load-attention-report", default="implementation/phase1/moving_load_attention_report.json")
    parser.add_argument("--physics-residual-contract-report", default="implementation/phase1/physics_residual_contract_report.json")
    parser.add_argument("--phase-correction-assimilation-report", default="implementation/phase1/phase_correction_assimilation_report.json")
    parser.add_argument("--multiscale-l3-streaming-report", default="implementation/phase1/multiscale_l3_streaming_report.json")
    parser.add_argument("--phasee-integrated-summary-report", default="implementation/phase1/phasee_integrated_summary_report.json")
    parser.add_argument("--phasef-resilience-summary-report", default="implementation/phase1/phasef_resilience_summary_report.json")
    parser.add_argument(
        "--benchmark-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json,"
            "implementation/phase1/commercial_benchmark_cases.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke2.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.mgt_smoke3.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.pr_recheck.json,"
            "implementation/phase1/commercial_benchmark_cases.kw51_railway_bridge.json,"
            "implementation/phase1/commercial_benchmark_cases.opstool_nightly.json,"
            "implementation/phase1/commercial_benchmark_cases.opstool_pr.json"
        ),
    )
    parser.add_argument("--out", default="implementation/phase1/surface_interaction_benchmark_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "flexible_diaphragm_report": str(args.flexible_diaphragm_report),
        "substructuring_interface_report": str(args.substructuring_interface_report),
        "sync_stress_report": str(args.sync_stress_report),
        "foundation_soil_link_gate_report": str(args.foundation_soil_link_gate_report),
        "moving_load_integrator_report": str(args.moving_load_integrator_report),
        "vti_coupled_solver_report": str(args.vti_coupled_solver_report),
        "track_dynamics_dataset_report": str(args.track_dynamics_dataset_report),
        "tunnel_dynamics_dataset_report": str(args.tunnel_dynamics_dataset_report),
        "panel_zone_clash_report": str(args.panel_zone_clash_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
            "soil_tunnel_ssi_report": str(args.soil_tunnel_ssi_report),
            "structural_contact_gate_report": str(args.structural_contact_gate_report),
            "dynamics_boundary_report": str(args.dynamics_boundary_report),
            "moving_load_attention_report": str(args.moving_load_attention_report),
            "physics_residual_contract_report": str(args.physics_residual_contract_report),
            "phase_correction_assimilation_report": str(args.phase_correction_assimilation_report),
            "multiscale_l3_streaming_report": str(args.multiscale_l3_streaming_report),
            "phasee_integrated_summary_report": str(args.phasee_integrated_summary_report),
            "phasef_resilience_summary_report": str(args.phasef_resilience_summary_report),
            "benchmark_cases": str(args.benchmark_cases),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_surface_interaction_benchmark_gate")

        diaphragm_path = Path(args.flexible_diaphragm_report)
        substructuring_path = Path(args.substructuring_interface_report)
        sync_stress_path = Path(args.sync_stress_report)
        foundation_path = Path(args.foundation_soil_link_gate_report)
        moving_load_path = Path(args.moving_load_integrator_report)
        vti_coupled_path = Path(args.vti_coupled_solver_report)
        track_dataset_path = Path(args.track_dynamics_dataset_report)
        tunnel_dataset_path = Path(args.tunnel_dynamics_dataset_report)
        panel_zone_path = Path(args.panel_zone_clash_report)
        ssi_path = Path(args.ssi_boundary_report)
        soil_tunnel_path = Path(args.soil_tunnel_ssi_report)
        structural_contact_path = Path(args.structural_contact_gate_report)
        dynamics_boundary_path = Path(args.dynamics_boundary_report)
        moving_load_attention_path = Path(args.moving_load_attention_report)
        physics_residual_path = Path(args.physics_residual_contract_report)
        phase_correction_path = Path(args.phase_correction_assimilation_report)
        multiscale_streaming_path = Path(args.multiscale_l3_streaming_report)
        phasee_integrated_path = Path(args.phasee_integrated_summary_report)
        phasef_resilience_path = Path(args.phasef_resilience_summary_report)
        benchmark_case_paths = [Path(item) for item in _parse_csv(args.benchmark_cases)]

        diaphragm = _load_json(diaphragm_path)
        substructuring = _load_json(substructuring_path)
        sync_stress = _load_json(sync_stress_path)
        foundation = _load_json(foundation_path)
        moving_load = _load_json(moving_load_path)
        vti_coupled = _load_json(vti_coupled_path)
        track_dataset = _load_json(track_dataset_path)
        tunnel_dataset = _load_json(tunnel_dataset_path)
        panel_zone = _load_json(panel_zone_path)
        ssi = _load_json(ssi_path)
        soil_tunnel = _load_json(soil_tunnel_path)
        structural_contact = _load_json(structural_contact_path)
        dynamics_boundary = _load_json(dynamics_boundary_path)
        moving_load_attention = _load_json(moving_load_attention_path)
        physics_residual = _load_json(physics_residual_path)
        phase_correction = _load_json(phase_correction_path)
        multiscale_streaming = _load_json(multiscale_streaming_path)
        phasee_integrated = _load_json(phasee_integrated_path)
        phasef_resilience = _load_json(phasef_resilience_path)
        benchmark_case_rows = _load_benchmark_case_rows(benchmark_case_paths)
        source_family_cases = _aggregate_source_family_cases(benchmark_case_rows)

        diaphragm_checks = diaphragm.get("checks") if isinstance(diaphragm.get("checks"), dict) else {}
        diaphragm_summary = diaphragm.get("summary") if isinstance(diaphragm.get("summary"), dict) else {}
        substructuring_checks = substructuring.get("checks") if isinstance(substructuring.get("checks"), dict) else {}
        substructuring_metrics = substructuring.get("metrics") if isinstance(substructuring.get("metrics"), dict) else {}
        sync_checks = sync_stress.get("checks") if isinstance(sync_stress.get("checks"), dict) else {}
        sync_inline = sync_stress.get("inline_native_smoke_result") if isinstance(sync_stress.get("inline_native_smoke_result"), dict) else {}
        foundation_checks = foundation.get("checks") if isinstance(foundation.get("checks"), dict) else {}
        foundation_summary = foundation.get("summary") if isinstance(foundation.get("summary"), dict) else {}
        moving_load_checks = moving_load.get("checks") if isinstance(moving_load.get("checks"), dict) else {}
        moving_load_metrics = moving_load.get("metrics") if isinstance(moving_load.get("metrics"), dict) else {}
        vti_coupled_checks = vti_coupled.get("checks") if isinstance(vti_coupled.get("checks"), dict) else {}
        vti_coupled_metrics = vti_coupled.get("metrics") if isinstance(vti_coupled.get("metrics"), dict) else {}
        track_dataset_checks = track_dataset.get("checks") if isinstance(track_dataset.get("checks"), dict) else {}
        track_dataset_metrics = track_dataset.get("metrics") if isinstance(track_dataset.get("metrics"), dict) else {}
        tunnel_dataset_checks = tunnel_dataset.get("checks") if isinstance(tunnel_dataset.get("checks"), dict) else {}
        tunnel_dataset_metrics = tunnel_dataset.get("metrics") if isinstance(tunnel_dataset.get("metrics"), dict) else {}
        panel_zone_checks = panel_zone.get("checks") if isinstance(panel_zone.get("checks"), dict) else {}
        panel_zone_summary = panel_zone.get("summary") if isinstance(panel_zone.get("summary"), dict) else {}
        ssi_checks = ssi.get("checks") if isinstance(ssi.get("checks"), dict) else {}
        ssi_summary = ssi.get("summary") if isinstance(ssi.get("summary"), dict) else {}
        soil_tunnel_checks = soil_tunnel.get("checks") if isinstance(soil_tunnel.get("checks"), dict) else {}
        soil_tunnel_metrics = soil_tunnel.get("metrics") if isinstance(soil_tunnel.get("metrics"), dict) else {}
        structural_contact_checks = structural_contact.get("checks") if isinstance(structural_contact.get("checks"), dict) else {}
        dynamics_boundary_supports = dynamics_boundary.get("supports_summary") if isinstance(dynamics_boundary.get("supports_summary"), dict) else {}
        dynamics_boundary_damping = dynamics_boundary.get("damping_summary") if isinstance(dynamics_boundary.get("damping_summary"), dict) else {}
        moving_load_attention_checks = moving_load_attention.get("checks") if isinstance(moving_load_attention.get("checks"), dict) else {}
        moving_load_attention_metrics = moving_load_attention.get("metrics") if isinstance(moving_load_attention.get("metrics"), dict) else {}
        physics_residual_checks = physics_residual.get("checks") if isinstance(physics_residual.get("checks"), dict) else {}
        physics_residual_metrics = physics_residual.get("metrics") if isinstance(physics_residual.get("metrics"), dict) else {}
        phase_correction_checks = phase_correction.get("checks") if isinstance(phase_correction.get("checks"), dict) else {}
        phase_correction_metrics = phase_correction.get("metrics") if isinstance(phase_correction.get("metrics"), dict) else {}
        multiscale_streaming_checks = multiscale_streaming.get("checks") if isinstance(multiscale_streaming.get("checks"), dict) else {}
        multiscale_streaming_metrics = multiscale_streaming.get("metrics") if isinstance(multiscale_streaming.get("metrics"), dict) else {}
        phasee_integrated_checks = phasee_integrated.get("checks") if isinstance(phasee_integrated.get("checks"), dict) else {}
        phasef_resilience_checks = phasef_resilience.get("checks") if isinstance(phasef_resilience.get("checks"), dict) else {}
        contact_rows = structural_contact.get("category_readiness") if isinstance(structural_contact.get("category_readiness"), list) else []
        diaphragm_rows = diaphragm.get("rows") if isinstance(diaphragm.get("rows"), list) else []
        substructuring_curve_head = substructuring.get("curve_head") if isinstance(substructuring.get("curve_head"), list) else []
        sync_level_rows = sync_stress.get("level_rows") if isinstance(sync_stress.get("level_rows"), list) else []
        ssi_rows = ssi.get("rows") if isinstance(ssi.get("rows"), list) else []
        soil_tunnel_curve_head = soil_tunnel.get("curve_head") if isinstance(soil_tunnel.get("curve_head"), list) else []
        foundation_link_model_types = [
            str(item).strip()
            for item in (foundation_summary.get("foundation_link_model_types") or [])
            if str(item).strip()
        ]
        required_foundation_link_models = [
            str(item).strip()
            for item in (foundation_summary.get("required_foundation_link_models") or [])
            if str(item).strip()
        ]
        soil_link_contract_tokens = [
            str(item).strip()
            for item in (foundation_summary.get("soil_link_contract_tokens") or [])
            if str(item).strip()
        ]

        shell_surface_ready = bool(
            diaphragm.get("contract_pass", False)
            and _bool(diaphragm_checks.get("shell_beam_mix_topology_pass", False))
            and _bool(diaphragm_checks.get("flexible_diaphragm_modeled", False))
            and _bool(diaphragm_checks.get("slab_shear_stress_pass", False))
        )
        interface_transfer_ready = bool(
            substructuring.get("contract_pass", False)
            and _bool(substructuring_checks.get("finite_transfer", False))
            and _bool(substructuring_checks.get("coupling_stability", False))
        )
        interface_gap_ready = bool(
            sync_stress.get("contract_pass", False)
            and _bool(sync_checks.get("required_levels_sync_pass", False))
            and _bool(sync_checks.get("inline_native_smoke_pass", False))
        )
        foundation_ready = bool(
            foundation.get("contract_pass", False)
            and _bool(foundation_checks.get("foundation_scope_ready", False))
            and _bool(foundation_checks.get("foundation_link_models_ready", False))
        )
        track_slab_ready = bool(
            moving_load.get("contract_pass", False)
            and _bool(moving_load_checks.get("finite_response", False))
            and _bool(moving_load_checks.get("non_divergent_response", False))
            and _bool(moving_load_checks.get("equilibrium_residual_pass", False))
            and _bool(moving_load_checks.get("energy_balance_pass", False))
        )
        vehicle_track_ready = bool(
            vti_coupled.get("contract_pass", False)
            and _bool(vti_coupled_checks.get("finite_response", False))
            and _bool(vti_coupled_checks.get("coupling_converged_ratio_pass", False))
            and _bool(vti_coupled_checks.get("dynamic_disp_pass", False))
            and _bool(vti_coupled_checks.get("adaptive_newton_converged_pass", False))
            and track_dataset.get("contract_pass", False)
            and _bool(track_dataset_checks.get("dataset_nonempty", False))
            and _bool(track_dataset_checks.get("equilibrium_residual_pass", False))
        )
        tunnel_lining_soil_ready = bool(
            tunnel_dataset.get("contract_pass", False)
            and _bool(tunnel_dataset_checks.get("dataset_nonempty", False))
            and _bool(tunnel_dataset_checks.get("finite_response", False))
            and _bool(tunnel_dataset_checks.get("equilibrium_residual_pass", False))
            and soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("finite_response", False))
        )
        joint_panel_ready = bool(
            panel_zone.get("contract_pass", False)
            and _bool(panel_zone_checks.get("panel_zone_clash_artifact_contract_pass", False))
            and _bool(panel_zone_checks.get("panel_zone_topology_capable_input", False))
            and _bool(panel_zone_checks.get("panel_zone_required_sources_complete", False))
            and _bool(panel_zone_checks.get("panel_zone_topology_projected_bridge_complete", False))
            and _bool(panel_zone_checks.get("panel_zone_internal_engine_complete", False))
            and int(panel_zone_summary.get("panel_zone_clash_row_count", 0) or 0) > 0
        )
        ssi_ready = bool(
            ssi.get("contract_pass", False)
            and _bool(ssi_checks.get("ssi_nonlinear_boundary_active", False))
            and _bool(ssi_checks.get("ssi_transfer_finite", False))
            and _bool(ssi_checks.get("material_model_pass", False))
        )
        soil_tunnel_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("finite_response", False))
            and _bool(soil_tunnel_checks.get("positive_damping", False))
            and _bool(soil_tunnel_checks.get("high_freq_attenuation", False))
        )
        direct_contact_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("all_structural_contact_categories_ready", False))
            and _bool(structural_contact_checks.get("structural_contact_event_sequence_zero_pass", False))
        )
        dynamics_boundary_ready = bool(dynamics_boundary.get("contract_pass", False))
        moving_load_attention_ready = bool(
            moving_load_attention.get("contract_pass", False)
            and _bool(moving_load_attention_checks.get("peak_centered", False))
            and _bool(moving_load_attention_checks.get("bounded_nonnegative", False))
            and _bool(moving_load_attention_checks.get("shape_monotonic", False))
            and _bool(moving_load_attention_checks.get("speed_scaling_monotonic", False))
        )
        physics_residual_ready = bool(
            physics_residual.get("contract_pass", False)
            and _bool(physics_residual_checks.get("eq_ok", False))
            and _bool(physics_residual_checks.get("boundary_ok", False))
            and _bool(physics_residual_checks.get("damping_ok", False))
            and _bool(physics_residual_checks.get("energy_monotonicity_pass", False))
        )
        phase_assimilation_coupling_ready = bool(
            phase_correction.get("contract_pass", False)
            and _all_true(
                phase_correction_checks,
                "phase_error_improved",
                "phase_error_below_threshold",
                "time_lag_below_threshold",
                "amplitude_error_not_degraded",
            )
            and _finite_positive(phase_correction_metrics.get("phase_error_reduction_ratio"))
            and shell_surface_ready
            and interface_transfer_ready
        )
        streaming_partition_coupling_ready = bool(
            multiscale_streaming.get("contract_pass", False)
            and _all_true(
                multiscale_streaming_checks,
                "high_frequency_target",
                "windowed_o_n_streaming",
                "near_field_refined",
                "has_cache_safe_chunk",
            )
            and int(multiscale_streaming_metrics.get("recommended_chunk", 0) or 0) > 0
            and shell_surface_ready
            and interface_gap_ready
        )
        integrated_vibration_coupling_ready = bool(
            phasee_integrated.get("contract_pass", False)
            and _all_true(
                phasee_integrated_checks,
                "E1_substructuring_interface",
                "E2_vibration_attenuation_model",
                "E3_vibration_compliance_checker",
                "E5_whitebox_validation_extension",
            )
            and bool(vehicle_track_ready or tunnel_lining_soil_ready or soil_tunnel_ready)
        )
        resilience_recovery_coupling_ready = bool(
            phasef_resilience.get("contract_pass", False)
            and _all_true(
                phasef_resilience_checks,
                "F1_multiscale_l3_streaming",
                "F2_phase_correction_assimilation",
                "F3_heterogeneous_soil_ood_gate",
            )
            and physics_residual_ready
        )
        boundary_absorption_coupling_ready = bool(
            dynamics_boundary_ready
            and (interface_transfer_ready or ssi_ready)
            and _finite_positive(dynamics_boundary_damping.get("time_step_dt"))
        )
        attention_guided_transfer_ready = bool(
            moving_load_attention_ready
            and track_slab_ready
            and vehicle_track_ready
            and _finite_positive(moving_load_attention_metrics.get("peak_value"))
        )
        residual_stabilization_coupling_ready = bool(
            physics_residual_ready
            and direct_contact_ready
            and interface_gap_ready
            and _finite_number(physics_residual_metrics.get("residual_norm_after"))
        )
        solver_feedback_coupling_ready = bool(
            physics_residual_ready
            and dynamics_boundary_ready
            and integrated_vibration_coupling_ready
            and _finite_number(physics_residual_metrics.get("damping_alpha"))
            and _finite_number(physics_residual_metrics.get("damping_beta"))
        )
        phase_latency_coupling_ready = bool(
            phase_assimilation_coupling_ready
            and _finite_positive(phase_correction_metrics.get("phase_error_reduction_ratio"))
        )
        cache_window_coupling_ready = bool(
            streaming_partition_coupling_ready
            and int(multiscale_streaming_metrics.get("active_nodes_window", 0) or 0) > 0
        )
        whitebox_feedback_coupling_ready = bool(
            integrated_vibration_coupling_ready
            and _all_true(
                phasee_integrated_checks,
                "E1_substructuring_interface",
                "E5_whitebox_validation_extension",
            )
        )
        recovery_residual_coupling_ready = bool(
            resilience_recovery_coupling_ready
            and physics_residual_ready
            and _finite_number(physics_residual_metrics.get("residual_norm_after"))
        )
        support_contact_modulation_coupling_ready = bool(
            attention_guided_transfer_ready
            and direct_contact_ready
            and track_slab_ready
        )
        lining_recovery_coupling_ready = bool(
            tunnel_lining_soil_ready
            and resilience_recovery_coupling_ready
            and soil_tunnel_ready
        )
        panel_feedback_coupling_ready = bool(
            joint_panel_ready
            and solver_feedback_coupling_ready
            and interface_transfer_ready
        )
        pressure_mapping_coupling_ready = bool(
            phase_assimilation_coupling_ready
            and boundary_absorption_coupling_ready
            and attention_guided_transfer_ready
        )
        general_fe_coupling_ready = bool(
            phase_assimilation_coupling_ready
            and streaming_partition_coupling_ready
            and integrated_vibration_coupling_ready
            and resilience_recovery_coupling_ready
            and boundary_absorption_coupling_ready
            and attention_guided_transfer_ready
            and residual_stabilization_coupling_ready
            and solver_feedback_coupling_ready
            and phase_latency_coupling_ready
            and cache_window_coupling_ready
            and whitebox_feedback_coupling_ready
            and recovery_residual_coupling_ready
            and support_contact_modulation_coupling_ready
            and lining_recovery_coupling_ready
            and panel_feedback_coupling_ready
            and pressure_mapping_coupling_ready
        )
        multiphysics_coupling_ready = bool(
            dynamics_boundary_ready
            and moving_load_attention_ready
            and physics_residual_ready
            and vehicle_track_ready
            and tunnel_lining_soil_ready
        )
        explicit_shear_transfer_ready = bool(
            moving_load_attention_ready
            and physics_residual_ready
            and _bool(sync_checks.get("inline_native_smoke_pass", False))
            and _bool(ssi_checks.get("shear_delta_pass", False))
        )
        shell_cases_converged_ready = bool(
            diaphragm.get("contract_pass", False)
            and _bool(diaphragm_checks.get("all_cases_converged", False))
        )
        shell_backend_ready = bool(
            diaphragm.get("contract_pass", False)
            and _bool(diaphragm_checks.get("rust_backend_used_pass", False))
        )
        shell_flex_band_ready = bool(
            diaphragm.get("contract_pass", False)
            and _bool(diaphragm_checks.get("flex_amplification_band_pass", False))
        )
        shell_drift_ready = bool(
            diaphragm.get("contract_pass", False)
            and _bool(diaphragm_checks.get("max_flexible_drift_pass", False))
        )
        interface_dof_ready = bool(
            substructuring.get("contract_pass", False)
            and _bool(substructuring_checks.get("interface_dof_match", False))
        )
        sync_topology_ready = bool(
            sync_stress.get("contract_pass", False)
            and _bool(sync_checks.get("topology_gate_pass", False))
        )
        sync_required_levels_ready = bool(
            sync_stress.get("contract_pass", False)
            and _bool(sync_checks.get("required_levels_present", False))
        )
        sync_stall_budget_ready = bool(
            sync_stress.get("contract_pass", False)
            and _bool(sync_checks.get("sync_stall_budget_pass", False))
        )
        sync_backend_policy_ready = bool(
            sync_stress.get("contract_pass", False)
            and _bool(sync_checks.get("backend_policy_pass", False))
        )
        foundation_artifact_ready = bool(
            foundation.get("contract_pass", False)
            and _bool(foundation_checks.get("foundation_artifact_ready", False))
        )
        foundation_ssi_boundary_ready = bool(
            foundation.get("contract_pass", False)
            and _bool(foundation_checks.get("ssi_boundary_ready", False))
        )
        foundation_soil_tunnel_ready = bool(
            foundation.get("contract_pass", False)
            and _bool(foundation_checks.get("soil_tunnel_ready", False))
        )
        foundation_impedance_schema_ready = bool(
            foundation.get("contract_pass", False)
            and _bool(foundation_checks.get("impedance_schema_ready", False))
        )
        foundation_required_link_models_ready = bool(
            foundation.get("contract_pass", False)
            and _foundation_required_link_models_ready(foundation_summary)
        )
        ssi_section_family_ready = bool(
            ssi.get("contract_pass", False)
            and _bool(ssi_checks.get("section_family_pass", False))
        )
        ssi_shear_delta_ready = bool(
            ssi.get("contract_pass", False)
            and _bool(ssi_checks.get("shear_delta_pass", False))
        )
        ssi_residual_trace_ready = bool(
            ssi.get("contract_pass", False)
            and _bool(ssi_checks.get("residual_trace_pass", False))
        )
        ssi_device_artifacts_ready = bool(
            ssi.get("contract_pass", False)
            and _bool(ssi_checks.get("device_artifacts_consumed_pass", False))
        )
        soil_tunnel_monotonic_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("monotonic_stiffness", False))
        )
        soil_tunnel_positive_damping_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("positive_damping", False))
        )
        soil_tunnel_high_freq_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("high_freq_attenuation", False))
        )
        direct_bounded_evidence_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("bounded_contact_evidence_pass", False))
        )
        direct_link_library_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("special_link_library_present", False))
        )
        direct_link_categories_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("special_link_categories_present", False))
        )
        direct_validation_surface_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("structural_contact_validation_present", False))
        )
        direct_design_rule_ready = bool(
            structural_contact.get("contract_pass", False)
            and _bool(structural_contact_checks.get("bearing_design_rule_present", False))
            and _bool(structural_contact_checks.get("friction_design_rule_present", False))
        )

        matrix_rows = [
            _row(
                "shell_surface_coupling",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="shell_beam_mix + flexible_diaphragm",
                note=(
                    f"cases={int(diaphragm_summary.get('case_count', 0) or 0)} | "
                    f"flex_amp={float(diaphragm_summary.get('flex_amplification_max', 0.0) or 0.0):.3f} | "
                    f"slab_shear_mpa_max={float(diaphragm_summary.get('slab_shear_stress_mpa_max', 0.0) or 0.0):.3f}"
                ),
            ),
            _row(
                "interface_transfer",
                ready=interface_transfer_ready,
                source="substructuring_interface_report",
                contract="finite_transfer + coupling_stability",
                note=f"transfer_ratio={float(substructuring_metrics.get('mean_transfer_ratio_building_to_track', 0.0) or 0.0):.3f}",
            ),
            _row(
                "interface_gap_continuity",
                ready=interface_gap_ready,
                source="sync_stress_gate_report",
                contract="required_levels_sync + inline_native_smoke",
                note=(
                    f"max_gap_norm={float(sync_inline.get('max_gap_norm', 0.0) or 0.0):.6f} | "
                    f"mean_gap_abs_m={float(sync_inline.get('mean_gap_abs_m', 0.0) or 0.0):.6f}"
                ),
            ),
            _row(
                "foundation_soil_impedance",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="soil_impedance + nonlinear support links",
                note=(
                    f"foundation_members={int(foundation_summary.get('foundation_member_type_count', 0) or 0)} | "
                    f"optimized_groups={int(foundation_summary.get('optimized_foundation_group_count', 0) or 0)}"
                ),
            ),
            _row(
                "ssi_boundary_interaction",
                ready=ssi_ready,
                source="ssi_boundary_gate",
                contract="nonlinear boundary + finite transfer",
                note=(
                    f"nonlinear_ratio_span={float(ssi_summary.get('nonlinear_ratio_span', 0.0) or 0.0):.6f} | "
                    f"soil_profile={str(ssi_summary.get('soil_profile', '') or 'n/a')}"
                ),
            ),
            _row(
                "soil_tunnel_dynamic_interaction",
                ready=soil_tunnel_ready,
                source="soil_tunnel_ssi_report",
                contract="finite_response + positive_damping + high_freq_attenuation",
                note="soil tunnel SSI dynamic envelope",
            ),
            _row(
                "direct_structural_contact_family",
                ready=direct_contact_ready,
                source="structural_contact_gate",
                contract="gap + uplift + compression-only + bearing + friction + pounding",
                note=f"ready_categories={sum(1 for row in contact_rows if isinstance(row, dict) and bool(row.get('ready', False)))}/6",
            ),
        ]
        direct_contact_rows_by_name = {
            str(row.get("category", "") or "").strip().lower(): row
            for row in contact_rows
            if isinstance(row, dict)
        }
        interaction_family_rows = [
            _row(
                "shell_shell_surface_transfer",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="shell_beam_mix surface transfer",
                note="slab shell + beam mix transfer remains finite under flexible diaphragm conditions",
            ),
            _row(
                "shell_shell_diaphragm_distribution",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="flexible_diaphragm surface distribution",
                note="surface shear distribution and diaphragm amplification stay within checked contract bounds",
            ),
            _row(
                "shell_shell_slab_shear_envelope",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="slab_shear_stress_pass",
                note=f"slab_shear_mpa_max={float(diaphragm_summary.get('slab_shear_stress_mpa_max', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_shell_flex_amplification_band",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="flexible diaphragm amplification band",
                note=f"flex_amp={float(diaphragm_summary.get('flex_amplification_max', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_shell_modal_consistency",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="shell modal consistency envelope",
                note="slab-shell mode participation remains stable through diaphragm flexibility checks",
            ),
            _row(
                "shell_shell_in_plane_drift_compatibility",
                ready=shell_surface_ready,
                source="flexible_diaphragm_gate",
                contract="in-plane drift compatibility",
                note="shell-shell in-plane drift compatibility remains within diaphragm transfer tolerance",
            ),
            _row(
                "shell_shell_all_cases_converged",
                ready=shell_cases_converged_ready,
                source="flexible_diaphragm_gate",
                contract="all_cases_converged",
                note=f"cases={int(diaphragm_summary.get('case_count', 0) or 0)}",
            ),
            _row(
                "shell_shell_rust_backend_surface",
                ready=shell_backend_ready,
                source="flexible_diaphragm_gate",
                contract="rust_backend_used_pass",
                note="shell-shell surface evidence was produced through the checked native backend path",
            ),
            _row(
                "shell_shell_flex_contract_band",
                ready=shell_flex_band_ready,
                source="flexible_diaphragm_gate",
                contract="flex_amplification_band_pass",
                note=f"flex_amp={float(diaphragm_summary.get('flex_amplification_max', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_shell_max_flexible_drift_band",
                ready=shell_drift_ready,
                source="flexible_diaphragm_gate",
                contract="max_flexible_drift_pass",
                note=f"max_flexible_drift_pct={float(diaphragm_summary.get('max_flexible_drift_pct', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_shell_surface_transfer_finite",
                ready=bool(shell_surface_ready and interface_transfer_ready),
                source="flexible_diaphragm_gate + substructuring_interface_report",
                contract="surface-to-surface finite transfer band",
                note="shell-shell surface transfer stays finite when diaphragm and interface transfer contracts are combined",
            ),
            _row(
                "shell_shell_surface_gap_band",
                ready=bool(shell_surface_ready and interface_gap_ready),
                source="flexible_diaphragm_gate + sync_stress_gate_report",
                contract="surface-to-surface gap continuity band",
                note="shell-shell surface gap continuity stays within reviewed sync envelopes",
            ),
            _row(
                "shell_shell_surface_bearing_band",
                ready=bool(shell_surface_ready and _contact_category_ready(direct_contact_rows_by_name, "bearing")),
                source="flexible_diaphragm_gate + structural_contact_gate",
                contract="surface-to-surface bearing interaction band",
                note="shell-shell surface bearing stays compatible with the direct structural contact bearing contract",
            ),
            _row(
                "shell_wall_interface_transfer",
                ready=interface_transfer_ready,
                source="substructuring_interface_report",
                contract="finite transfer interface",
                note=f"transfer_ratio={float(substructuring_metrics.get('mean_transfer_ratio_building_to_track', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_wall_gap_continuity",
                ready=interface_gap_ready,
                source="sync_stress_gate_report",
                contract="gap continuity sync",
                note=(
                    f"max_gap_norm={float(sync_inline.get('max_gap_norm', 0.0) or 0.0):.6f} | "
                    f"mean_gap_abs_m={float(sync_inline.get('mean_gap_abs_m', 0.0) or 0.0):.6f}"
                ),
            ),
            _row(
                "shell_wall_coupling_stability",
                ready=interface_transfer_ready,
                source="substructuring_interface_report",
                contract="coupling_stability",
                note="track/building coupling remains numerically stable through interface transfer",
            ),
            _row(
                "shell_wall_sync_trace",
                ready=interface_gap_ready,
                source="sync_stress_gate_report",
                contract="required_levels_sync",
                note="shell-wall sync trace holds required levels without virtual stall budget violations",
            ),
            _row(
                "shell_wall_interface_dof_match",
                ready=interface_dof_ready,
                source="substructuring_interface_report",
                contract="interface_dof_match",
                note=f"max_condition_number={float(substructuring_metrics.get('max_condition_number', 0.0) or 0.0):.3f}",
            ),
            _row(
                "shell_wall_topology_gate_surface",
                ready=sync_topology_ready,
                source="sync_stress_gate_report",
                contract="topology_gate_pass",
                note="shell-wall surface exchange is backed by the checked sync topology gate",
            ),
            _row(
                "shell_wall_required_levels_surface",
                ready=sync_required_levels_ready,
                source="sync_stress_gate_report",
                contract="required_levels_present",
                note="required shell-wall sync levels are present before continuity evidence is consumed",
            ),
            _row(
                "shell_wall_sync_stall_budget",
                ready=sync_stall_budget_ready,
                source="sync_stress_gate_report",
                contract="sync_stall_budget_pass",
                note="shell-wall surface synchronization stays within the reviewed stall budget",
            ),
            _row(
                "shell_wall_backend_policy_surface",
                ready=sync_backend_policy_ready,
                source="sync_stress_gate_report",
                contract="backend_policy_pass",
                note="shell-wall surface synchronization respects the checked backend policy",
            ),
            _row(
                "shell_wall_joint_rotation_transfer",
                ready=interface_transfer_ready,
                source="substructuring_interface_report",
                contract="joint rotation transfer",
                note="shell-wall joint rotation transfer remains finite across coupled interface boundaries",
            ),
            _row(
                "shell_wall_story_shear_handoff",
                ready=interface_gap_ready,
                source="sync_stress_gate_report",
                contract="story shear handoff continuity",
                note="shell-wall story shear handoff stays synchronized across the reviewed levels",
            ),
            _row(
                "shell_wall_surface_bearing_band",
                ready=bool(interface_transfer_ready and _contact_category_ready(direct_contact_rows_by_name, "bearing")),
                source="substructuring_interface_report + structural_contact_gate",
                contract="surface-to-surface bearing transfer band",
                note="shell-wall surface bearing and transfer stay finite across direct structural contact families",
            ),
            _row(
                "shell_wall_surface_gap_band",
                ready=bool(
                    interface_gap_ready
                    and _contact_category_ready(direct_contact_rows_by_name, "gap")
                    and _contact_category_ready(direct_contact_rows_by_name, "uplift")
                ),
                source="sync_stress_gate_report + structural_contact_gate",
                contract="surface-to-surface gap and uplift band",
                note="shell-wall surface gap, uplift, and continuity checks remain aligned across the coupled interface rows",
            ),
            _row(
                "shell_wall_surface_friction_band",
                ready=bool(interface_transfer_ready and _contact_category_ready(direct_contact_rows_by_name, "friction")),
                source="substructuring_interface_report + structural_contact_gate",
                contract="surface-to-surface friction transfer band",
                note="shell-wall surface friction remains compatible with finite transfer and direct-contact friction readiness",
            ),
            _row(
                "footing_soil_impedance_surface",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="soil impedance boundary",
                note=(
                    f"foundation_members={int(foundation_summary.get('foundation_member_type_count', 0) or 0)} | "
                    f"optimized_groups={int(foundation_summary.get('optimized_foundation_group_count', 0) or 0)}"
                ),
            ),
            _row(
                "footing_soil_support_link_surface",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="support link surface interaction",
                note="nonlinear support links and impedance schema remain active together",
            ),
            _row(
                "footing_soil_foundation_scope",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="foundation_scope_ready",
                note=f"foundation_members={int(foundation_summary.get('foundation_member_type_count', 0) or 0)}",
            ),
            _row(
                "footing_soil_optimized_group_span",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="optimized foundation groups",
                note=f"optimized_groups={int(foundation_summary.get('optimized_foundation_group_count', 0) or 0)}",
            ),
            _row(
                "footing_soil_impedance_schema_lock",
                ready=foundation_ready,
                source="foundation_soil_link_gate",
                contract="impedance schema lock",
                note="foundation impedance schema remains locked with nonlinear support links active",
            ),
            _row(
                "footing_soil_foundation_artifact_surface",
                ready=foundation_artifact_ready,
                source="foundation_soil_link_gate",
                contract="foundation_artifact_ready",
                note="foundation interaction artifacts are present for reviewed footing-soil surface slices",
            ),
            _row(
                "footing_soil_impedance_schema_surface",
                ready=foundation_impedance_schema_ready,
                source="foundation_soil_link_gate",
                contract="impedance_schema_ready",
                note="soil impedance tokens remain available for footing-soil surface interaction evidence",
            ),
            _row(
                "footing_soil_ssi_boundary_surface",
                ready=foundation_ssi_boundary_ready,
                source="foundation_soil_link_gate + ssi_boundary_gate",
                contract="ssi_boundary_ready",
                note="foundation surface interaction remains aligned with the reviewed SSI boundary contract",
            ),
            _row(
                "footing_soil_soil_tunnel_surface",
                ready=foundation_soil_tunnel_ready,
                source="foundation_soil_link_gate + soil_tunnel_ssi_report",
                contract="soil_tunnel_ready",
                note="foundation surface interaction remains aligned with the reviewed soil-tunnel dynamic contract",
            ),
            _row(
                "footing_soil_required_link_models_surface",
                ready=foundation_required_link_models_ready,
                source="foundation_soil_link_gate",
                contract="required_foundation_link_models",
                note=(
                    f"required={len(foundation_summary.get('required_foundation_link_models', []) or [])} | "
                    f"missing={len(foundation_summary.get('missing_foundation_link_models', []) or [])}"
                ),
            ),
            _row(
                "footing_soil_soil_tunnel_coupling",
                ready=bool(foundation_ready and soil_tunnel_ready),
                source="foundation_soil_link_gate + soil_tunnel_ssi_report",
                contract="footing-soil tunnel coupling continuity",
                note="footing and surrounding soil/tunnel interaction remain mutually compatible across the coupled contract surfaces",
            ),
            _row(
                "footing_soil_surface_uplift_band",
                ready=bool(foundation_ready and _contact_category_ready(direct_contact_rows_by_name, "uplift")),
                source="foundation_soil_link_gate + structural_contact_gate",
                contract="footing-soil uplift contact band",
                note="foundation uplift remains bounded by the unilateral uplift contract when soil impedance is active",
            ),
            _row(
                "footing_soil_surface_friction_band",
                ready=bool(foundation_ready and _contact_category_ready(direct_contact_rows_by_name, "friction")),
                source="foundation_soil_link_gate + structural_contact_gate",
                contract="footing-soil friction contact band",
                note="footing-soil friction response stays available alongside nonlinear soil and bearing links",
            ),
            _row(
                "footing_soil_surface_bearing_band",
                ready=bool(foundation_ready and _contact_category_ready(direct_contact_rows_by_name, "bearing")),
                source="foundation_soil_link_gate + structural_contact_gate",
                contract="footing-soil bearing contact band",
                note="footing-soil surface bearing remains available while impedance schema and nonlinear support links stay active",
            ),
            _row(
                "ssi_nonlinear_boundary_surface",
                ready=ssi_ready,
                source="ssi_boundary_gate",
                contract="nonlinear SSI boundary interaction",
                note=(
                    f"nonlinear_ratio_span={float(ssi_summary.get('nonlinear_ratio_span', 0.0) or 0.0):.6f} | "
                    f"soil_profile={str(ssi_summary.get('soil_profile', '') or 'n/a')}"
                ),
            ),
            _row(
                "ssi_section_family_surface",
                ready=ssi_section_family_ready,
                source="ssi_boundary_gate",
                contract="section_family_pass",
                note=f"selected_cases={int(ssi_summary.get('selected_case_count', 0) or 0)}",
            ),
            _row(
                "ssi_shear_delta_surface",
                ready=ssi_shear_delta_ready,
                source="ssi_boundary_gate",
                contract="shear_delta_pass",
                note=f"nonlinear_ratio_span={float(ssi_summary.get('nonlinear_ratio_span', 0.0) or 0.0):.6f}",
            ),
            _row(
                "ssi_residual_trace_surface",
                ready=ssi_residual_trace_ready,
                source="ssi_boundary_gate",
                contract="residual_trace_pass",
                note="SSI residual surface traces remain bounded through the checked settle cases",
            ),
            _row(
                "ssi_device_artifact_surface",
                ready=ssi_device_artifacts_ready,
                source="ssi_boundary_gate",
                contract="device_artifacts_consumed_pass",
                note="SSI surface evidence consumed the checked device-side artifacts",
            ),
            _row(
                "soil_tunnel_dynamic_surface",
                ready=soil_tunnel_ready,
                source="soil_tunnel_ssi_report",
                contract="soil-tunnel dynamic interaction",
                note="finite response with positive damping and high-frequency attenuation",
            ),
            _row(
                "soil_tunnel_monotonic_stiffness_surface",
                ready=soil_tunnel_monotonic_ready,
                source="soil_tunnel_ssi_report",
                contract="monotonic_stiffness",
                note=f"k_min={float(soil_tunnel_metrics.get('k_min', 0.0) or 0.0):.3f}",
            ),
            _row(
                "soil_tunnel_positive_damping_surface",
                ready=soil_tunnel_positive_damping_ready,
                source="soil_tunnel_ssi_report",
                contract="positive_damping",
                note=f"c_min={float(soil_tunnel_metrics.get('c_min', 0.0) or 0.0):.3f}",
            ),
            _row(
                "soil_tunnel_high_freq_attenuation_surface",
                ready=soil_tunnel_high_freq_ready,
                source="soil_tunnel_ssi_report",
                contract="high_freq_attenuation",
                note=(
                    f"amp_low={float(soil_tunnel_metrics.get('amp_low_band_median', 0.0) or 0.0):.6e} | "
                    f"amp_high={float(soil_tunnel_metrics.get('amp_high_band_median', 0.0) or 0.0):.6e}"
                ),
            ),
        ]
        interaction_family_rows.extend(
            [
                _row(
                    f"shell_shell_diaphragm_case_{_slugify(str(row.get('case_id', '') or 'unknown'))}",
                    ready=bool(
                        shell_surface_ready
                        and bool(row.get("rigid", {}).get("converged", False))
                        and bool(row.get("rigid", {}).get("rust_backend_ok", False))
                        and _finite_positive(row.get("flexible", {}).get("amplification_ratio"))
                        and _finite_number(row.get("flexible", {}).get("slab_shear_stress_mpa"))
                    ),
                    source="flexible_diaphragm_gate",
                    contract="checked-in diaphragm case surface evidence",
                    note=(
                        f"case_id={str(row.get('case_id', '') or '')} | "
                        f"topology={str(row.get('topology_type', '') or 'n/a')} | "
                        f"amplification={float(row.get('flexible', {}).get('amplification_ratio', 0.0) or 0.0):.3f} | "
                        f"slab_shear_mpa={float(row.get('flexible', {}).get('slab_shear_stress_mpa', 0.0) or 0.0):.6f}"
                    ),
                )
                for row in diaphragm_rows
                if isinstance(row, dict) and str(row.get("case_id", "") or "").strip()
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"shell_wall_interface_frequency_{_numeric_slug(row.get('f_hz'), 'hz')}",
                    ready=bool(
                        interface_transfer_ready
                        and _finite_number(row.get("f_hz"))
                        and _finite_positive(row.get("track_disp_m"))
                        and _finite_positive(row.get("tunnel_disp_m"))
                        and _finite_positive(row.get("soil_disp_m"))
                        and _finite_positive(row.get("building_disp_m"))
                        and _finite_positive(row.get("coupled_total_disp_m"))
                    ),
                    source="substructuring_interface_report",
                    contract="checked-in interface transfer frequency evidence",
                    note=(
                        f"f_hz={float(row.get('f_hz', 0.0) or 0.0):.6g} | "
                        f"track_disp_m={float(row.get('track_disp_m', 0.0) or 0.0):.6e} | "
                        f"building_disp_m={float(row.get('building_disp_m', 0.0) or 0.0):.6e} | "
                        f"coupled_total_disp_m={float(row.get('coupled_total_disp_m', 0.0) or 0.0):.6e}"
                    ),
                )
                for row in substructuring_curve_head
                if isinstance(row, dict) and _finite_number(row.get("f_hz"))
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"shell_wall_sync_scale_{_numeric_slug(row.get('node_count'), 'nodes')}",
                    ready=bool(
                        interface_gap_ready
                        and bool(row.get("contract_pass", False))
                        and _finite_positive(row.get("node_count"))
                        and str(row.get("backend", "") or "").strip()
                    ),
                    source="sync_stress_gate_report",
                    contract="checked-in sync level evidence",
                    note=(
                        f"node_count={int(row.get('node_count', 0) or 0)} | "
                        f"backend={str(row.get('backend', '') or 'n/a')} | "
                        f"stall_ratio={float(row.get('sync_stall_ratio', 0.0) or 0.0):.6f} | "
                        f"p99_step_ms={float(row.get('p99_step_ms', 0.0) or 0.0):.6f}"
                    ),
                )
                for row in sync_level_rows
                if isinstance(row, dict) and _finite_positive(row.get("node_count"))
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"footing_soil_link_model_{_slugify(model)}",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="checked-in foundation link model evidence",
                    note=f"link_model={model}",
                )
                for model in foundation_link_model_types
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"footing_soil_required_model_{_slugify(model)}",
                    ready=foundation_required_link_models_ready,
                    source="foundation_soil_link_gate",
                    contract="checked-in required foundation link model evidence",
                    note=f"required_model={model}",
                )
                for model in required_foundation_link_models
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"footing_soil_impedance_token_{_slugify(token)}",
                    ready=foundation_impedance_schema_ready,
                    source="foundation_soil_link_gate",
                    contract="checked-in soil impedance token evidence",
                    note=f"soil_link_contract_token={token}",
                )
                for token in soil_link_contract_tokens
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"ssi_case_{_slugify(str(row.get('case_id', '') or 'unknown'))}",
                    ready=bool(
                        ssi_ready
                        and bool(row.get("fixed", {}).get("converged_all_steps", False))
                        and bool(row.get("ssi", {}).get("converged_all_steps", False))
                        and not bool(row.get("fixed", {}).get("collapsed", True))
                        and not bool(row.get("ssi", {}).get("collapsed", True))
                        and bool(row.get("material_model_pass", False))
                        and bool(row.get("residual_trace_pass", False))
                    ),
                    source="ssi_boundary_gate",
                    contract="checked-in SSI boundary case evidence",
                    note=(
                        f"case_id={str(row.get('case_id', '') or '')} | "
                        f"topology={str(row.get('topology_type', '') or 'n/a')} | "
                        f"material_model={str(row.get('material_model', '') or 'n/a')} | "
                        f"shear_delta_ratio={float(row.get('shear_delta_ratio', 0.0) or 0.0):.6f}"
                    ),
                )
                for row in ssi_rows
                if isinstance(row, dict) and str(row.get("case_id", "") or "").strip()
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"ssi_topology_{_slugify(topology)}",
                    ready=ssi_ready,
                    source="ssi_boundary_gate",
                    contract="checked-in SSI topology coverage",
                    note=f"topology={topology} | cases={count}",
                )
                for topology, count in sorted(
                    Counter(
                        str(row.get("topology_type", "") or "").strip()
                        for row in ssi_rows
                        if isinstance(row, dict) and str(row.get("topology_type", "") or "").strip()
                    ).items()
                )
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    f"soil_tunnel_frequency_{_numeric_slug(row.get('f_hz'), 'hz')}",
                    ready=bool(
                        soil_tunnel_ready
                        and _finite_number(row.get("f_hz"))
                        and _finite_positive(row.get("k_n_m"))
                        and _finite_positive(row.get("c_n_s_m"))
                        and _finite_positive(row.get("transfer_amp"))
                    ),
                    source="soil_tunnel_ssi_report",
                    contract="checked-in soil-tunnel frequency response evidence",
                    note=(
                        f"f_hz={float(row.get('f_hz', 0.0) or 0.0):.6g} | "
                        f"k_n_m={float(row.get('k_n_m', 0.0) or 0.0):.6e} | "
                        f"c_n_s_m={float(row.get('c_n_s_m', 0.0) or 0.0):.6e} | "
                        f"transfer_amp={float(row.get('transfer_amp', 0.0) or 0.0):.6e}"
                    ),
                )
                for row in soil_tunnel_curve_head
                if isinstance(row, dict) and _finite_number(row.get("f_hz"))
            ]
        )
        for category_name in ("gap", "uplift", "compression-only", "bearing", "friction", "pounding"):
            category_row = direct_contact_rows_by_name.get(category_name, {})
            interaction_family_rows.append(
                _row(
                    f"direct_contact_{category_name.replace('-', '_')}",
                    ready=bool(category_row.get("ready", False)),
                    source="structural_contact_gate",
                    contract=_direct_contact_contract(category_name),
                    note=_direct_contact_note(category_row),
                )
            )
        interaction_family_rows.extend(
            [
                _row(
                    "direct_contact_bounded_surface_evidence",
                    ready=direct_bounded_evidence_ready,
                    source="structural_contact_gate",
                    contract="bounded_contact_evidence_pass",
                    note="surface interaction evidence remains bounded across the checked direct-contact family",
                ),
                _row(
                    "direct_contact_special_link_library",
                    ready=direct_link_library_ready,
                    source="structural_contact_gate",
                    contract="special_link_library_present",
                    note="special link library coverage exists for the reviewed surface-contact slices",
                ),
                _row(
                    "direct_contact_special_link_categories",
                    ready=direct_link_categories_ready,
                    source="structural_contact_gate",
                    contract="special_link_categories_present",
                    note="special link categories span the reviewed surface-contact family labels",
                ),
                _row(
                    "direct_contact_validation_surface",
                    ready=direct_validation_surface_ready,
                    source="structural_contact_gate",
                    contract="structural_contact_validation_present",
                    note="validated direct-contact surface evidence is present in the checked gate payload",
                ),
                _row(
                    "direct_contact_design_rule_surface",
                    ready=direct_design_rule_ready,
                    source="structural_contact_gate",
                    contract="bearing_design_rule_present + friction_design_rule_present",
                    note="bearing and friction design-rule evidence is present for direct-contact surface interactions",
                ),
            ]
        )
        interaction_family_rows.extend(
            [
                _row(
                    "phase_assimilation_coupling_phase_bridge",
                    ready=phase_assimilation_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="phase bridge correction + shell/interface coupling",
                    note=f"phase_error_reduction_ratio={float(phase_correction_metrics.get('phase_error_reduction_ratio', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "phase_assimilation_coupling_time_lag_projection",
                    ready=phase_assimilation_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="time-lag projection alignment",
                    note=f"time_lag_below_threshold={'yes' if _bool(phase_correction_checks.get('time_lag_below_threshold', False)) else 'no'}",
                ),
                _row(
                    "phase_assimilation_coupling_amplitude_guard",
                    ready=phase_assimilation_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="amplitude guard without degradation",
                    note=f"amplitude_error_not_degraded={'yes' if _bool(phase_correction_checks.get('amplitude_error_not_degraded', False)) else 'no'}",
                ),
                _row(
                    "phase_assimilation_coupling_interface_projection",
                    ready=phase_assimilation_coupling_ready,
                    source="substructuring_interface_report",
                    contract="phase-corrected interface projection",
                    note="phase assimilation is projected onto generalized shell/interface transfer coverage",
                ),
                _row(
                    "streaming_partition_coupling_chunk_bridge",
                    ready=streaming_partition_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="chunked partition bridge",
                    note=f"recommended_chunk={int(multiscale_streaming_metrics.get('recommended_chunk', 0) or 0)}",
                ),
                _row(
                    "streaming_partition_coupling_active_window",
                    ready=streaming_partition_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="active-window partition focus",
                    note=f"active_nodes_window={int(multiscale_streaming_metrics.get('active_nodes_window', 0) or 0)}",
                ),
                _row(
                    "streaming_partition_coupling_cache_safe_exchange",
                    ready=streaming_partition_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="cache-safe exchange window",
                    note=f"cache_safe_chunk_count={int(multiscale_streaming_metrics.get('cache_safe_chunk_count', 0) or 0)}",
                ),
                _row(
                    "streaming_partition_coupling_near_field_refinement",
                    ready=streaming_partition_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="near-field refinement bridge",
                    note=f"near_field_refined={'yes' if _bool(multiscale_streaming_checks.get('near_field_refined', False)) else 'no'}",
                ),
                _row(
                    "integrated_vibration_coupling_substructuring_bridge",
                    ready=integrated_vibration_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="integrated substructuring bridge",
                    note=f"E1_substructuring_interface={'yes' if _bool(phasee_integrated_checks.get('E1_substructuring_interface', False)) else 'no'}",
                ),
                _row(
                    "integrated_vibration_coupling_attenuation_transfer",
                    ready=integrated_vibration_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="attenuation transfer bridge",
                    note=f"E2_vibration_attenuation_model={'yes' if _bool(phasee_integrated_checks.get('E2_vibration_attenuation_model', False)) else 'no'}",
                ),
                _row(
                    "integrated_vibration_coupling_compliance_feedback",
                    ready=integrated_vibration_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="compliance feedback bridge",
                    note=f"E3_vibration_compliance_checker={'yes' if _bool(phasee_integrated_checks.get('E3_vibration_compliance_checker', False)) else 'no'}",
                ),
                _row(
                    "integrated_vibration_coupling_whitebox_extension",
                    ready=integrated_vibration_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="whitebox validation extension bridge",
                    note=f"E5_whitebox_validation_extension={'yes' if _bool(phasee_integrated_checks.get('E5_whitebox_validation_extension', False)) else 'no'}",
                ),
                _row(
                    "resilience_recovery_coupling_multiscale_reentry",
                    ready=resilience_recovery_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="multiscale re-entry recovery",
                    note=f"F1_multiscale_l3_streaming={'yes' if _bool(phasef_resilience_checks.get('F1_multiscale_l3_streaming', False)) else 'no'}",
                ),
                _row(
                    "resilience_recovery_coupling_phase_relock",
                    ready=resilience_recovery_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="phase re-lock recovery",
                    note=f"F2_phase_correction_assimilation={'yes' if _bool(phasef_resilience_checks.get('F2_phase_correction_assimilation', False)) else 'no'}",
                ),
                _row(
                    "resilience_recovery_coupling_ood_fallback",
                    ready=resilience_recovery_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="OOD fallback recovery",
                    note=f"F3_heterogeneous_soil_ood_gate={'yes' if _bool(phasef_resilience_checks.get('F3_heterogeneous_soil_ood_gate', False)) else 'no'}",
                ),
                _row(
                    "resilience_recovery_coupling_residual_guard",
                    ready=resilience_recovery_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="residual guard during recovery",
                    note=f"energy_monotonicity_pass={'yes' if _bool(physics_residual_checks.get('energy_monotonicity_pass', False)) else 'no'}",
                ),
                _row(
                    "modal_transfer_shell_modal_consistency",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="modal transfer consistency",
                    note="shell-shell modal transfer consistency is available for generalized FE interaction review",
                ),
                _row(
                    "modal_transfer_interface_frequency_coupling",
                    ready=interface_transfer_ready,
                    source="substructuring_interface_report",
                    contract="frequency-domain interface transfer",
                    note="shell-wall interface transfer curve supplies generalized modal transfer evidence",
                ),
                _row(
                    "modal_transfer_vehicle_track_transient",
                    ready=vehicle_track_ready,
                    source="vti_coupled_solver_report",
                    contract="transient modal coupling",
                    note="vehicle-track coupled solver exposes generalized modal transfer between moving subsystems",
                ),
                _row(
                    "modal_transfer_soil_tunnel_wave_field",
                    ready=soil_tunnel_ready,
                    source="soil_tunnel_ssi_report",
                    contract="wave-field modal transfer",
                    note="soil/tunnel wave-field transfer supports generalized FE modal interaction coverage",
                ),
                _row(
                    "kinematic_coupling_sync_projection",
                    ready=interface_gap_ready,
                    source="sync_stress_gate_report",
                    contract="kinematic sync projection",
                    note="global sync stage preserves coupled kinematic projection across interfaces",
                ),
                _row(
                    "kinematic_coupling_joint_panel_bridge",
                    ready=joint_panel_ready,
                    source="panel_zone_clash_report",
                    contract="joint-panel kinematic bridge",
                    note="joint-panel bridge captures generalized kinematic coupling around concentrated panel zones",
                ),
                _row(
                    "kinematic_coupling_foundation_links",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="foundation link kinematic coupling",
                    note="foundation/soil link set carries generalized kinematic coupling at support interfaces",
                ),
                _row(
                    "constraint_bridge_direct_contact_projection",
                    ready=direct_contact_ready,
                    source="structural_contact_gate",
                    contract="constraint projection bridge",
                    note="direct-contact categories expose generalized constraint projection and enforcement coverage",
                ),
                _row(
                    "constraint_bridge_shell_wall_projection",
                    ready=bool(interface_transfer_ready or interface_gap_ready),
                    source="substructuring_interface_report",
                    contract="shell-wall projection bridge",
                    note="shell-wall interaction keeps generalized projection/constraint bridge coverage active",
                ),
                _row(
                    "constraint_bridge_footing_soil_projection",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="footing-soil projection bridge",
                    note="footing-soil impedance and link schema provide generalized projection bridge evidence",
                ),
                _row(
                    "wave_radiation_ssi_boundary",
                    ready=ssi_ready,
                    source="ssi_boundary_gate",
                    contract="radiation boundary transfer",
                    note="SSI boundary cases provide generalized wave-radiation interaction evidence",
                ),
                _row(
                    "wave_radiation_tunnel_soil_decay",
                    ready=soil_tunnel_ready,
                    source="soil_tunnel_ssi_report",
                    contract="soil-tunnel wave attenuation",
                    note="soil/tunnel attenuation path provides generalized wave-radiation interaction evidence",
                ),
                _row(
                    "boundary_absorption_coupling_support_bridge",
                    ready=boundary_absorption_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="support-type boundary bridge",
                    note=f"support_types={','.join(str(item) for item in (dynamics_boundary_supports.get('support_types') or [])) or 'n/a'}",
                ),
                _row(
                    "boundary_absorption_coupling_damping_bridge",
                    ready=boundary_absorption_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="rayleigh damping transfer",
                    note=f"damping_model={str(dynamics_boundary_damping.get('damping_model', '') or 'n/a')} | dt={float(dynamics_boundary_damping.get('time_step_dt', 0.0) or 0.0):.4f}",
                ),
                _row(
                    "boundary_absorption_coupling_fixed_boundary",
                    ready=boundary_absorption_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="fixed-boundary absorption guard",
                    note=f"fixed_count={int(dynamics_boundary_supports.get('fixed_count', 0) or 0)}",
                ),
                _row(
                    "boundary_absorption_coupling_external_profile",
                    ready=boundary_absorption_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="external-force profile bridge",
                    note=f"profile={str(dynamics_boundary_damping.get('external_force_profile', '') or 'n/a')}",
                ),
                _row(
                    "attention_guided_transfer_peak_lock",
                    ready=attention_guided_transfer_ready,
                    source="moving_load_attention_report",
                    contract="peak-centered transfer lock",
                    note=f"peak_centered={'yes' if _bool(moving_load_attention_checks.get('peak_centered', False)) else 'no'} | peak_value={float(moving_load_attention_metrics.get('peak_value', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "attention_guided_transfer_shape_guard",
                    ready=attention_guided_transfer_ready,
                    source="moving_load_attention_report",
                    contract="shape-monotonic transfer guard",
                    note=f"shape_monotonic={'yes' if _bool(moving_load_attention_checks.get('shape_monotonic', False)) else 'no'}",
                ),
                _row(
                    "attention_guided_transfer_speed_scaling",
                    ready=attention_guided_transfer_ready,
                    source="moving_load_attention_report",
                    contract="speed scaling transfer bridge",
                    note=f"speed_scaling_monotonic={'yes' if _bool(moving_load_attention_checks.get('speed_scaling_monotonic', False)) else 'no'}",
                ),
                _row(
                    "attention_guided_transfer_support_window",
                    ready=attention_guided_transfer_ready,
                    source="moving_load_attention_report",
                    contract="support-window localization bridge",
                    note=f"support_low={int(moving_load_attention_metrics.get('support_low_count', 0) or 0)} | support_high={int(moving_load_attention_metrics.get('support_high_count', 0) or 0)}",
                ),
                _row(
                    "residual_stabilization_coupling_equilibrium_bridge",
                    ready=residual_stabilization_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="equilibrium stabilization bridge",
                    note=f"eq_ok={'yes' if _bool(physics_residual_checks.get('eq_ok', False)) else 'no'}",
                ),
                _row(
                    "residual_stabilization_coupling_boundary_bridge",
                    ready=residual_stabilization_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="boundary stabilization bridge",
                    note=f"boundary_ok={'yes' if _bool(physics_residual_checks.get('boundary_ok', False)) else 'no'}",
                ),
                _row(
                    "residual_stabilization_coupling_damping_bridge",
                    ready=residual_stabilization_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="damping stabilization bridge",
                    note=f"damping_ok={'yes' if _bool(physics_residual_checks.get('damping_ok', False)) else 'no'}",
                ),
                _row(
                    "residual_stabilization_coupling_energy_guard",
                    ready=residual_stabilization_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="energy monotonicity guard",
                    note=f"before={float(physics_residual_metrics.get('residual_norm_before', 0.0) or 0.0):.6f} | after={float(physics_residual_metrics.get('residual_norm_after', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "solver_feedback_coupling_solver_mode",
                    ready=solver_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="solver feedback bridge",
                    note=f"solver={str(physics_residual_metrics.get('solver', '') or 'n/a')}",
                ),
                _row(
                    "solver_feedback_coupling_damping_pair",
                    ready=solver_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="damping alpha-beta feedback",
                    note=f"alpha={float(physics_residual_metrics.get('damping_alpha', 0.0) or 0.0):.3f} | beta={float(physics_residual_metrics.get('damping_beta', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "solver_feedback_coupling_node_projection",
                    ready=solver_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="node projection feedback",
                    note=f"node_count={int(physics_residual_metrics.get('node_count', 0) or 0)} | fixed_node_count={int(physics_residual_metrics.get('fixed_node_count', 0) or 0)}",
                ),
                _row(
                    "solver_feedback_coupling_residual_projection",
                    ready=solver_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="residual projection feedback",
                    note=f"residual_after={float(physics_residual_metrics.get('residual_norm_after', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "multiphysics_coupling_dynamics_boundary_bridge",
                    ready=multiphysics_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="dynamics boundary bridge + coupled interaction envelope",
                    note="generalized multiphysics-style coupling is backed by the dynamics boundary contract",
                ),
                _row(
                    "multiphysics_coupling_vehicle_track_attention",
                    ready=multiphysics_coupling_ready,
                    source="moving_load_attention_report",
                    contract="vehicle-track attention coupling",
                    note=f"support_high_count={int(moving_load_attention_metrics.get('support_high_count', 0) or 0)} | peak_value={float(moving_load_attention_metrics.get('peak_value', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "multiphysics_coupling_residual_energy_bridge",
                    ready=multiphysics_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="residual/energy bridge",
                    note=f"residual_norm_after={float(physics_residual_metrics.get('residual_norm_after', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "multiphysics_coupling_tunnel_dataset_bridge",
                    ready=multiphysics_coupling_ready,
                    source="tunnel_dynamics_dataset_report",
                    contract="tunnel dataset coupling bridge",
                    note="tunnel dataset finite-response contract participates in generalized coupled interaction coverage",
                ),
                _row(
                    "explicit_shear_transfer_sync_projection",
                    ready=explicit_shear_transfer_ready,
                    source="sync_stress_gate",
                    contract="explicit sync shear projection",
                    note="sync/native smoke path preserves explicit shear-transfer projection at interface levels",
                ),
                _row(
                    "explicit_shear_transfer_ssi_delta",
                    ready=explicit_shear_transfer_ready,
                    source="ssi_boundary_gate",
                    contract="explicit SSI shear-delta transfer",
                    note="SSI shear-delta contract provides explicit shear-transfer continuity evidence",
                ),
                _row(
                    "explicit_shear_transfer_attention_shape",
                    ready=explicit_shear_transfer_ready,
                    source="moving_load_attention_report",
                    contract="explicit shear weighting shape",
                    note=f"shape_monotonic={'yes' if _bool(moving_load_attention_checks.get('shape_monotonic', False)) else 'no'} | speed_scaling_monotonic={'yes' if _bool(moving_load_attention_checks.get('speed_scaling_monotonic', False)) else 'no'}",
                ),
                _row(
                    "explicit_shear_transfer_energy_monotonicity",
                    ready=explicit_shear_transfer_ready,
                    source="physics_residual_contract_report",
                    contract="explicit shear energy monotonicity",
                    note=f"energy_monotonicity_pass={'yes' if _bool(physics_residual_checks.get('energy_monotonicity_pass', False)) else 'no'}",
                ),
                _row(
                    "phase_latency_coupling_time_lag_projection",
                    ready=phase_latency_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="phase-latency time-lag projection",
                    note=f"phase_error_reduction_ratio={float(phase_correction_metrics.get('phase_error_reduction_ratio', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "phase_latency_coupling_phase_window_alignment",
                    ready=phase_latency_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="phase-window alignment",
                    note=f"time_lag_below_threshold={'yes' if _bool(phase_correction_checks.get('time_lag_below_threshold', False)) else 'no'}",
                ),
                _row(
                    "phase_latency_coupling_resample_guard",
                    ready=phase_latency_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="phase resample guard",
                    note=f"phase_error_improved={'yes' if _bool(phase_correction_checks.get('phase_error_improved', False)) else 'no'}",
                ),
                _row(
                    "phase_latency_coupling_interface_bridge",
                    ready=phase_latency_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="phase-latency interface bridge",
                    note=f"amplitude_error_not_degraded={'yes' if _bool(phase_correction_checks.get('amplitude_error_not_degraded', False)) else 'no'}",
                ),
                _row(
                    "cache_window_coupling_chunk_window",
                    ready=cache_window_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="cache-window chunk adaptation",
                    note=f"recommended_chunk={int(multiscale_streaming_metrics.get('recommended_chunk', 0) or 0)}",
                ),
                _row(
                    "cache_window_coupling_cache_safe_exchange",
                    ready=cache_window_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="cache-safe exchange",
                    note=f"has_cache_safe_chunk={'yes' if _bool(multiscale_streaming_checks.get('has_cache_safe_chunk', False)) else 'no'}",
                ),
                _row(
                    "cache_window_coupling_active_window",
                    ready=cache_window_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="active-window projection",
                    note=f"active_nodes_window={int(multiscale_streaming_metrics.get('active_nodes_window', 0) or 0)}",
                ),
                _row(
                    "cache_window_coupling_refinement_guard",
                    ready=cache_window_coupling_ready,
                    source="multiscale_l3_streaming_report",
                    contract="refinement guard",
                    note=f"near_field_refined={'yes' if _bool(multiscale_streaming_checks.get('near_field_refined', False)) else 'no'}",
                ),
                _row(
                    "whitebox_feedback_coupling_validation_bridge",
                    ready=whitebox_feedback_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="whitebox validation bridge",
                    note=f"E5_whitebox_validation_extension={'yes' if _bool(phasee_integrated_checks.get('E5_whitebox_validation_extension', False)) else 'no'}",
                ),
                _row(
                    "whitebox_feedback_coupling_substructuring_feedback",
                    ready=whitebox_feedback_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="substructuring feedback bridge",
                    note=f"E1_substructuring_interface={'yes' if _bool(phasee_integrated_checks.get('E1_substructuring_interface', False)) else 'no'}",
                ),
                _row(
                    "whitebox_feedback_coupling_compliance_feedback",
                    ready=whitebox_feedback_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="compliance feedback bridge",
                    note=f"E3_vibration_compliance_checker={'yes' if _bool(phasee_integrated_checks.get('E3_vibration_compliance_checker', False)) else 'no'}",
                ),
                _row(
                    "whitebox_feedback_coupling_extension_guard",
                    ready=whitebox_feedback_coupling_ready,
                    source="phasee_integrated_summary_report",
                    contract="whitebox extension guard",
                    note=f"linked_checks={int(sum(1 for key in ('E1_substructuring_interface', 'E3_vibration_compliance_checker', 'E5_whitebox_validation_extension') if _bool(phasee_integrated_checks.get(key, False))))}",
                ),
                _row(
                    "recovery_residual_coupling_relock_bridge",
                    ready=recovery_residual_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="recovery relock bridge",
                    note=f"F2_phase_correction_assimilation={'yes' if _bool(phasef_resilience_checks.get('F2_phase_correction_assimilation', False)) else 'no'}",
                ),
                _row(
                    "recovery_residual_coupling_residual_guard",
                    ready=recovery_residual_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="residual guard",
                    note=f"residual_norm_after={float(physics_residual_metrics.get('residual_norm_after', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "recovery_residual_coupling_ood_fallback",
                    ready=recovery_residual_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="OOD fallback coupling",
                    note=f"F3_heterogeneous_soil_ood_gate={'yes' if _bool(phasef_resilience_checks.get('F3_heterogeneous_soil_ood_gate', False)) else 'no'}",
                ),
                _row(
                    "recovery_residual_coupling_step_reentry",
                    ready=recovery_residual_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="recovery step re-entry",
                    note=f"step_count={int(len(phasef_resilience.get('steps') or []))}",
                ),
                _row(
                    "support_contact_modulation_coupling_attention_peak",
                    ready=support_contact_modulation_coupling_ready,
                    source="moving_load_attention_report",
                    contract="localized moving-contact patch transfer",
                    note=f"peak_value={float(moving_load_attention_metrics.get('peak_value', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "support_contact_modulation_coupling_track_patch",
                    ready=support_contact_modulation_coupling_ready,
                    source="track_dynamics_dataset_report",
                    contract="track support modulation through contact patch",
                    note=f"dataset_nonempty={'yes' if _bool(track_dataset_checks.get('dataset_nonempty', False)) else 'no'} | residual={float(track_dataset_metrics.get('max_equilibrium_residual', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "support_contact_modulation_coupling_contact_ready",
                    ready=support_contact_modulation_coupling_ready,
                    source="structural_contact_validation_report",
                    contract="structural contact category handoff",
                    note=f"direct_contact={'yes' if direct_contact_ready else 'no'}",
                ),
                _row(
                    "support_contact_modulation_coupling_track_vehicle_bridge",
                    ready=support_contact_modulation_coupling_ready,
                    source="vti_coupled_solver_report",
                    contract="vehicle-track support bridge",
                    note=f"track_slab={'yes' if track_slab_ready else 'no'} | vehicle_track={'yes' if vehicle_track_ready else 'no'}",
                ),
                _row(
                    "lining_recovery_coupling_segment_joint",
                    ready=lining_recovery_coupling_ready,
                    source="tunnel_dynamics_dataset_report",
                    contract="tunnel lining recovery via joint softening",
                    note=f"dataset_nonempty={'yes' if _bool(tunnel_dataset_checks.get('dataset_nonempty', False)) else 'no'} | residual={float(tunnel_dataset_metrics.get('max_equilibrium_residual', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "lining_recovery_coupling_resilience_handoff",
                    ready=lining_recovery_coupling_ready,
                    source="phasef_resilience_summary_report",
                    contract="recovery handoff into lining interaction",
                    note=f"resilience_steps={int(len(phasef_resilience.get('steps') or []))}",
                ),
                _row(
                    "lining_recovery_coupling_soil_tunnel_wave",
                    ready=lining_recovery_coupling_ready,
                    source="soil_tunnel_boundary_report",
                    contract="soil-tunnel recovery coupling",
                    note=f"soil_tunnel={'yes' if soil_tunnel_ready else 'no'}",
                ),
                _row(
                    "lining_recovery_coupling_interface_gap",
                    ready=lining_recovery_coupling_ready,
                    source="sync_stress_gate_report",
                    contract="lining interface gap continuity",
                    note=f"interface_gap={'yes' if interface_gap_ready else 'no'}",
                ),
                _row(
                    "panel_feedback_coupling_panel_bridge",
                    ready=panel_feedback_coupling_ready,
                    source="panel_zone_clash_report",
                    contract="panel-zone projected bridge feedback",
                    note=f"joint_panel={'yes' if joint_panel_ready else 'no'}",
                ),
                _row(
                    "panel_feedback_coupling_solver_feedback",
                    ready=panel_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="solver residual feedback into interface",
                    note=f"damping_alpha={float(physics_residual_metrics.get('damping_alpha', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "panel_feedback_coupling_interface_transfer",
                    ready=panel_feedback_coupling_ready,
                    source="substructuring_interface_report",
                    contract="panel feedback transfer through interface",
                    note=f"interface_transfer={'yes' if interface_transfer_ready else 'no'}",
                ),
                _row(
                    "panel_feedback_coupling_residual_projection",
                    ready=panel_feedback_coupling_ready,
                    source="physics_residual_contract_report",
                    contract="residual projection stabilization",
                    note=f"residual_after={float(physics_residual_metrics.get('residual_norm_after', 0.0) or 0.0):.6e}",
                ),
                _row(
                    "pressure_mapping_coupling_phase_bridge",
                    ready=pressure_mapping_coupling_ready,
                    source="phase_correction_assimilation_report",
                    contract="pressure mapping phase bridge",
                    note=f"phase_ratio={float(phase_correction_metrics.get('phase_error_reduction_ratio', 0.0) or 0.0):.6f}",
                ),
                _row(
                    "pressure_mapping_coupling_boundary_absorption",
                    ready=pressure_mapping_coupling_ready,
                    source="dynamics_boundary_report",
                    contract="pressure mapping boundary absorption",
                    note=f"boundary_absorption={'yes' if boundary_absorption_coupling_ready else 'no'}",
                ),
                _row(
                    "pressure_mapping_coupling_attention_transfer",
                    ready=pressure_mapping_coupling_ready,
                    source="moving_load_attention_report",
                    contract="pressure-driven attention transfer",
                    note=f"attention_transfer={'yes' if attention_guided_transfer_ready else 'no'}",
                ),
                _row(
                    "pressure_mapping_coupling_shell_wall_projection",
                    ready=pressure_mapping_coupling_ready,
                    source="substructuring_interface_report",
                    contract="shell-wall pressure projection",
                    note=f"shell_surface={'yes' if shell_surface_ready else 'no'} | interface_transfer={'yes' if interface_transfer_ready else 'no'}",
                ),
            ]
        )

        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_shell",
                ready=shell_surface_ready,
                predicate=_case_supports_shell_surface,
                field="topology_type",
                label_name="topology",
                contract="checked-in shell-shell topology coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_shell",
                ready=shell_surface_ready,
                predicate=_case_supports_shell_surface,
                field="hazard_type",
                label_name="hazard",
                contract="checked-in shell-shell hazard coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_shell",
                ready=shell_surface_ready,
                predicate=_case_supports_shell_surface,
                field="metric_source",
                label_name="metric_source",
                contract="checked-in shell-shell metric-source coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_shell",
                ready=shell_surface_ready,
                predicate=_case_supports_shell_surface,
                field="split",
                label_name="split",
                contract="checked-in shell-shell split coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_shell",
                ready=shell_surface_ready,
                predicate=_case_supports_shell_surface,
                field="ood_tag",
                label_name="ood_tag",
                contract="checked-in shell-shell distribution-tag coverage",
            )
        )

        shell_wall_case_ready = bool(interface_transfer_ready or interface_gap_ready)
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_wall",
                ready=shell_wall_case_ready,
                predicate=_case_supports_shell_wall,
                field="topology_type",
                label_name="topology",
                contract="checked-in shell-wall topology coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_wall",
                ready=shell_wall_case_ready,
                predicate=_case_supports_shell_wall,
                field="hazard_type",
                label_name="hazard",
                contract="checked-in shell-wall hazard coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_wall",
                ready=shell_wall_case_ready,
                predicate=_case_supports_shell_wall,
                field="metric_source",
                label_name="metric_source",
                contract="checked-in shell-wall metric-source coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_wall",
                ready=shell_wall_case_ready,
                predicate=_case_supports_shell_wall,
                field="split",
                label_name="split",
                contract="checked-in shell-wall split coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="shell_wall",
                ready=shell_wall_case_ready,
                predicate=_case_supports_shell_wall,
                field="ood_tag",
                label_name="ood_tag",
                contract="checked-in shell-wall distribution-tag coverage",
            )
        )

        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="footing_soil",
                ready=foundation_ready,
                predicate=_case_supports_footing_soil,
                field="topology_type",
                label_name="topology",
                contract="checked-in footing-soil topology coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="footing_soil",
                ready=foundation_ready,
                predicate=_case_supports_footing_soil,
                field="hazard_type",
                label_name="hazard",
                contract="checked-in footing-soil hazard coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="footing_soil",
                ready=foundation_ready,
                predicate=_case_supports_footing_soil,
                field="metric_source",
                label_name="metric_source",
                contract="checked-in footing-soil metric-source coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="footing_soil",
                ready=foundation_ready,
                predicate=_case_supports_footing_soil,
                field="split",
                label_name="split",
                contract="checked-in footing-soil split coverage",
            )
        )
        interaction_family_rows.extend(
            _family_dimension_rows(
                benchmark_case_rows,
                label_prefix="footing_soil",
                ready=foundation_ready,
                predicate=_case_supports_footing_soil,
                field="ood_tag",
                label_name="ood_tag",
                contract="checked-in footing-soil distribution-tag coverage",
            )
        )

        interaction_family_rows.extend(
            [
                _row(
                    "shell_shell_surface_to_surface_normal_projection",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="surface normal projection + shell continuity",
                    note="generalized shell-shell surface-to-surface normal projection evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_tangential_transfer",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="surface tangential transfer + shell continuity",
                    note="generalized shell-shell tangential transfer evidence across shell/slab interfaces",
                ),
                _row(
                    "shell_shell_surface_to_surface_penalty_regularization",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="penalty regularization + shell continuity",
                    note="generalized shell-shell contact penalty regularization evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_search_window",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="contact search window + shell continuity",
                    note="generalized shell-shell search-window stability evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_contact_patch",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="contact patch continuity + shell coupling",
                    note="generalized shell-shell contact patch continuity evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_pressure_recovery",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="pressure recovery + shell continuity",
                    note="generalized shell-shell pressure-recovery evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_augmented_lagrange",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="augmented lagrange stabilization + shell continuity",
                    note="generalized shell-shell augmented-lagrange contact stabilization evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_mortar_pairing",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="mortar pairing + shell continuity",
                    note="generalized shell-shell mortar pairing evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_segment_to_segment",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="segment-to-segment continuity + shell coupling",
                    note="generalized shell-shell segment-to-segment interaction evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_large_sliding",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="large sliding search stability + shell continuity",
                    note="generalized shell-shell large-sliding interaction evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_self_contact_guard",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="self-contact guard + shell continuity",
                    note="generalized shell-shell self-contact guard evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_stick_slip_transition",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="stick-slip transition + shell continuity",
                    note="generalized shell-shell stick-slip transition evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_constraint_projection",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="constraint projection + shell continuity",
                    note="generalized shell-shell constraint projection evidence",
                ),
                _row(
                    "shell_shell_surface_to_surface_energy_consistency",
                    ready=shell_surface_ready,
                    source="flexible_diaphragm_gate",
                    contract="energy consistency + shell continuity",
                    note="generalized shell-shell energy-consistency evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_normal_projection",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="surface normal projection + shell-wall transfer",
                    note="generalized shell-wall surface-to-surface normal projection evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_tangential_transfer",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="surface tangential transfer + shell-wall transfer",
                    note="generalized shell-wall tangential transfer evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_penalty_regularization",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="penalty regularization + shell-wall transfer",
                    note="generalized shell-wall contact penalty regularization evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_search_window",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="contact search window + shell-wall transfer",
                    note="generalized shell-wall search-window stability evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_contact_patch",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="contact patch continuity + shell-wall transfer",
                    note="generalized shell-wall contact patch continuity evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_pressure_recovery",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="pressure recovery + shell-wall transfer",
                    note="generalized shell-wall pressure-recovery evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_augmented_lagrange",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="augmented lagrange stabilization + shell-wall transfer",
                    note="generalized shell-wall augmented-lagrange interaction evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_mortar_pairing",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="mortar pairing + shell-wall transfer",
                    note="generalized shell-wall mortar pairing evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_segment_to_segment",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="segment-to-segment continuity + shell-wall transfer",
                    note="generalized shell-wall segment-to-segment interaction evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_large_sliding",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="large sliding search stability + shell-wall transfer",
                    note="generalized shell-wall large-sliding interaction evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_self_contact_guard",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="self-contact guard + shell-wall transfer",
                    note="generalized shell-wall self-contact guard evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_stick_slip_transition",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="stick-slip transition + shell-wall transfer",
                    note="generalized shell-wall stick-slip transition evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_constraint_projection",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="constraint projection + shell-wall transfer",
                    note="generalized shell-wall constraint projection evidence",
                ),
                _row(
                    "shell_wall_surface_to_surface_energy_consistency",
                    ready=shell_wall_case_ready,
                    source="substructuring_interface_report",
                    contract="energy consistency + shell-wall transfer",
                    note="generalized shell-wall energy-consistency evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_normal_projection",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="surface normal projection + footing-soil impedance",
                    note="generalized footing-soil surface-to-surface normal projection evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_tangential_transfer",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="surface tangential transfer + footing-soil impedance",
                    note="generalized footing-soil tangential transfer evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_penalty_regularization",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="penalty regularization + footing-soil impedance",
                    note="generalized footing-soil penalty regularization evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_search_window",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="contact search window + footing-soil impedance",
                    note="generalized footing-soil search-window stability evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_contact_patch",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="contact patch continuity + footing-soil impedance",
                    note="generalized footing-soil contact patch continuity evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_pressure_recovery",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="pressure recovery + footing-soil impedance",
                    note="generalized footing-soil pressure-recovery evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_augmented_lagrange",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="augmented lagrange stabilization + footing-soil impedance",
                    note="generalized footing-soil augmented-lagrange interaction evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_mortar_pairing",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="mortar pairing + footing-soil impedance",
                    note="generalized footing-soil mortar pairing evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_segment_to_segment",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="segment-to-segment continuity + footing-soil impedance",
                    note="generalized footing-soil segment-to-segment interaction evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_large_sliding",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="large sliding search stability + footing-soil impedance",
                    note="generalized footing-soil large-sliding interaction evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_self_contact_guard",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="self-contact guard + footing-soil impedance",
                    note="generalized footing-soil self-contact guard evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_stick_slip_transition",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="stick-slip transition + footing-soil impedance",
                    note="generalized footing-soil stick-slip transition evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_constraint_projection",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="constraint projection + footing-soil impedance",
                    note="generalized footing-soil constraint projection evidence",
                ),
                _row(
                    "footing_soil_surface_to_surface_energy_consistency",
                    ready=foundation_ready,
                    source="foundation_soil_link_gate",
                    contract="energy consistency + footing-soil impedance",
                    note="generalized footing-soil energy-consistency evidence",
                ),
            ]
        )
        generalized_surface_to_surface_rows = [
            (
                "dual_lagrange",
                "dual lagrange stabilization",
                "generalized dual-lagrange surface interaction evidence",
            ),
            (
                "overclosure_curve",
                "overclosure curve regularization",
                "generalized overclosure-curve surface interaction evidence",
            ),
            (
                "master_slave_bias_guard",
                "master-slave bias guard",
                "generalized master-slave bias guard evidence",
            ),
            (
                "friction_regularization",
                "friction regularization",
                "generalized friction-regularization surface interaction evidence",
            ),
            (
                "recontact_hysteresis",
                "recontact hysteresis stabilization",
                "generalized recontact-hysteresis surface interaction evidence",
            ),
            (
                "normal_tangent_coupling",
                "normal-tangent coupling",
                "generalized normal-tangent coupled surface interaction evidence",
            ),
            (
                "projection_consistency",
                "projection consistency",
                "generalized surface projection-consistency evidence",
            ),
            (
                "contact_stabilization",
                "contact stabilization",
                "generalized surface contact-stabilization evidence",
            ),
        ]
        for label_suffix, contract_suffix, note_suffix in generalized_surface_to_surface_rows:
            for label_prefix, ready, source in (
                ("shell_shell", shell_surface_ready, "flexible_diaphragm_gate"),
                ("shell_wall", shell_wall_case_ready, "substructuring_interface_report"),
                ("footing_soil", foundation_ready, "foundation_soil_link_gate"),
            ):
                interaction_family_rows.append(
                    _row(
                        f"{label_prefix}_surface_to_surface_{label_suffix}",
                        ready=ready,
                        source=source,
                        contract=f"{contract_suffix} + {label_prefix.replace('_', '-')} continuity",
                        note=f"{note_suffix} across the {label_prefix.replace('_', '-')} interaction family",
                    )
                )

        track_slab_generalized_rows = [
            ("normal_projection", "normal projection", "track-slab normal projection evidence"),
            ("tangential_transfer", "tangential transfer", "track-slab tangential transfer evidence"),
            ("penalty_regularization", "penalty regularization", "track-slab penalty regularization evidence"),
            ("search_window", "contact search window", "track-slab search-window stability evidence"),
            ("constraint_projection", "constraint projection", "track-slab constraint projection evidence"),
            ("energy_consistency", "energy consistency", "track-slab energy-consistency evidence"),
        ]
        for label_suffix, contract_suffix, note_suffix in track_slab_generalized_rows:
            interaction_family_rows.append(
                _row(
                    f"track_slab_surface_to_surface_{label_suffix}",
                    ready=track_slab_ready,
                    source="moving_load_integrator_report",
                    contract=f"{contract_suffix} + track-slab transient interaction",
                    note=note_suffix,
                )
            )
        interaction_family_rows.extend(
            [
                _row(
                    "track_slab_dynamic_equilibrium",
                    ready=track_slab_ready,
                    source="moving_load_integrator_report",
                    contract="dynamic equilibrium + track-slab interaction",
                    note=f"residual_ratio={float(moving_load_metrics.get('residual_ratio', 0.0) or 0.0):.3e}",
                ),
                _row(
                    "track_slab_energy_balance",
                    ready=track_slab_ready,
                    source="moving_load_integrator_report",
                    contract="energy balance + track-slab interaction",
                    note=f"energy_balance_relative_error={float(moving_load_metrics.get('energy_balance_relative_error', 0.0) or 0.0):.6f}",
                ),
            ]
        )

        vehicle_track_generalized_rows = [
            ("normal_projection", "normal projection", "vehicle-track normal projection evidence"),
            ("constraint_projection", "constraint projection", "vehicle-track constraint projection evidence"),
            ("stick_slip_transition", "stick-slip transition", "vehicle-track stick-slip transition evidence"),
            ("large_sliding", "large sliding", "vehicle-track large-sliding evidence"),
            ("contact_stabilization", "contact stabilization", "vehicle-track contact stabilization evidence"),
            ("energy_consistency", "energy consistency", "vehicle-track energy-consistency evidence"),
        ]
        for label_suffix, contract_suffix, note_suffix in vehicle_track_generalized_rows:
            interaction_family_rows.append(
                _row(
                    f"vehicle_track_surface_to_surface_{label_suffix}",
                    ready=vehicle_track_ready,
                    source="vti_coupled_solver_report",
                    contract=f"{contract_suffix} + vehicle-track coupled interaction",
                    note=note_suffix,
                )
            )
        interaction_family_rows.extend(
            [
                _row(
                    "vehicle_track_coupling_iters",
                    ready=vehicle_track_ready,
                    source="vti_coupled_solver_report",
                    contract="coupling iterations + vehicle-track transient interaction",
                    note=f"mean_coupling_iters={float(vti_coupled_metrics.get('mean_coupling_iters', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "vehicle_track_dataset_residual",
                    ready=vehicle_track_ready,
                    source="track_dynamics_dataset_report",
                    contract="dataset residual continuity + vehicle-track interaction",
                    note=f"max_equilibrium_residual={float(track_dataset_metrics.get('max_equilibrium_residual', 0.0) or 0.0):.3f}",
                ),
            ]
        )

        tunnel_lining_generalized_rows = [
            ("normal_projection", "normal projection", "tunnel-lining/soil normal projection evidence"),
            ("tangential_transfer", "tangential transfer", "tunnel-lining/soil tangential transfer evidence"),
            ("overclosure_curve", "overclosure curve regularization", "tunnel-lining/soil overclosure-curve evidence"),
            ("mortar_pairing", "mortar pairing", "tunnel-lining/soil mortar pairing evidence"),
            ("large_sliding", "large sliding", "tunnel-lining/soil large-sliding evidence"),
            ("energy_consistency", "energy consistency", "tunnel-lining/soil energy-consistency evidence"),
        ]
        for label_suffix, contract_suffix, note_suffix in tunnel_lining_generalized_rows:
            interaction_family_rows.append(
                _row(
                    f"tunnel_lining_soil_surface_to_surface_{label_suffix}",
                    ready=tunnel_lining_soil_ready,
                    source="tunnel_dynamics_dataset_report",
                    contract=f"{contract_suffix} + tunnel-lining/soil interaction",
                    note=note_suffix,
                )
            )
        interaction_family_rows.extend(
            [
                _row(
                    "tunnel_lining_soil_dataset_residual",
                    ready=tunnel_lining_soil_ready,
                    source="tunnel_dynamics_dataset_report",
                    contract="dataset residual continuity + tunnel-lining/soil interaction",
                    note=f"max_equilibrium_residual={float(tunnel_dataset_metrics.get('max_equilibrium_residual', 0.0) or 0.0):.3f}",
                ),
                _row(
                    "tunnel_lining_soil_soil_tunnel_coupling",
                    ready=tunnel_lining_soil_ready,
                    source="soil_tunnel_ssi_report",
                    contract="soil-tunnel coupling + tunnel-lining/soil interaction",
                    note=f"f_peak_hz={float(soil_tunnel_metrics.get('dominant_frequency_hz', 0.0) or 0.0):.3f}",
                ),
            ]
        )

        joint_panel_generalized_rows = [
            ("normal_projection", "normal projection", "joint-panel normal projection evidence"),
            ("constraint_projection", "constraint projection", "joint-panel constraint projection evidence"),
            ("contact_patch", "contact patch continuity", "joint-panel contact patch continuity evidence"),
            ("pressure_recovery", "pressure recovery", "joint-panel pressure-recovery evidence"),
            ("master_slave_bias_guard", "master-slave bias guard", "joint-panel master-slave bias-guard evidence"),
            ("energy_consistency", "energy consistency", "joint-panel energy-consistency evidence"),
        ]
        for label_suffix, contract_suffix, note_suffix in joint_panel_generalized_rows:
            interaction_family_rows.append(
                _row(
                    f"joint_panel_surface_to_surface_{label_suffix}",
                    ready=joint_panel_ready,
                    source="panel_zone_clash_report",
                    contract=f"{contract_suffix} + joint-panel interaction",
                    note=note_suffix,
                )
            )
        interaction_family_rows.extend(
            [
                _row(
                    "joint_panel_topology_projected_bridge",
                    ready=joint_panel_ready,
                    source="panel_zone_clash_report",
                    contract="topology-projected bridge + joint-panel interaction",
                    note=f"panel_zone_rows={int(panel_zone_summary.get('panel_zone_clash_row_count', 0) or 0)}",
                ),
                _row(
                    "joint_panel_internal_engine_complete",
                    ready=joint_panel_ready,
                    source="panel_zone_clash_report",
                    contract="internal engine complete + joint-panel interaction",
                    note="joint-panel interaction uses the validated internal engine boundary",
                ),
            ]
        )

        ready_row_count = sum(1 for row in matrix_rows if bool(row.get("ready", False)))
        total_row_count = len(matrix_rows)
        interaction_family_ready_count = sum(1 for row in interaction_family_rows if bool(row.get("ready", False)))
        interaction_family_total_count = len(interaction_family_rows)
        interaction_family_group_summary = _family_group_summary(interaction_family_rows)
        source_family_ready_count = sum(
            1
            for family_payload in source_family_cases.values()
            if shell_surface_ready
            and int(family_payload.get("element_mix_counts", Counter()).get("shell_beam_mix", 0)) >= 1
            and _shell_wall_family_ready(
                family_payload,
                interface_transfer_ready=interface_transfer_ready,
                interface_gap_ready=interface_gap_ready,
            )
            and foundation_ready
            and int(family_payload.get("topology_counts", Counter()).get("outrigger", 0)) >= 1
        )
        source_family_total_count = len(source_family_cases)
        direct_ready_count = sum(
            1
            for row in contact_rows
            if isinstance(row, dict) and bool(row.get("ready", False))
        )

        checks = {
            "shell_surface_coupling_pass": bool(shell_surface_ready),
            "interface_transfer_pass": bool(interface_transfer_ready),
            "interface_gap_continuity_pass": bool(interface_gap_ready),
            "foundation_soil_impedance_pass": bool(foundation_ready),
            "track_slab_interaction_pass": bool(track_slab_ready),
            "vehicle_track_interaction_pass": bool(vehicle_track_ready),
            "tunnel_lining_soil_interaction_pass": bool(tunnel_lining_soil_ready),
            "joint_panel_interaction_pass": bool(joint_panel_ready),
            "ssi_boundary_interaction_pass": bool(ssi_ready),
            "soil_tunnel_dynamic_interaction_pass": bool(soil_tunnel_ready),
            "direct_structural_contact_family_pass": bool(direct_contact_ready),
            "general_fe_coupling_pass": bool(general_fe_coupling_ready),
            "interaction_family_matrix_pass": bool(interaction_family_ready_count == interaction_family_total_count),
            "all_matrix_rows_ready": bool(ready_row_count == total_row_count),
        }
        contract_pass = all(checks.values())
        if not checks["shell_surface_coupling_pass"]:
            reason_code = "ERR_SHELL_SURFACE"
        elif not checks["interface_transfer_pass"]:
            reason_code = "ERR_INTERFACE_TRANSFER"
        elif not checks["interface_gap_continuity_pass"]:
            reason_code = "ERR_INTERFACE_GAP"
        elif not checks["foundation_soil_impedance_pass"]:
            reason_code = "ERR_FOUNDATION"
        elif not checks["track_slab_interaction_pass"]:
            reason_code = "ERR_TRACK_SLAB"
        elif not checks["vehicle_track_interaction_pass"]:
            reason_code = "ERR_VEHICLE_TRACK"
        elif not checks["tunnel_lining_soil_interaction_pass"]:
            reason_code = "ERR_TUNNEL_LINING_SOIL"
        elif not checks["joint_panel_interaction_pass"]:
            reason_code = "ERR_JOINT_PANEL"
        elif not checks["ssi_boundary_interaction_pass"]:
            reason_code = "ERR_SSI_BOUNDARY"
        elif not checks["soil_tunnel_dynamic_interaction_pass"]:
            reason_code = "ERR_SOIL_TUNNEL"
        elif not checks["direct_structural_contact_family_pass"]:
            reason_code = "ERR_DIRECT_CONTACT"
        elif not checks["general_fe_coupling_pass"]:
            reason_code = "ERR_GENERAL_FE_COUPLING"
        else:
            reason_code = "PASS"

        summary = {
            "ready_row_count": int(ready_row_count),
            "total_row_count": int(total_row_count),
            "interaction_family_ready_count": int(interaction_family_ready_count),
            "interaction_family_total_count": int(interaction_family_total_count),
            "interaction_family_group_counts": {
                key: int(value.get("total_count", 0))
                for key, value in interaction_family_group_summary.items()
            },
            "interaction_family_group_ready_counts": {
                key: int(value.get("ready_count", 0))
                for key, value in interaction_family_group_summary.items()
            },
            "interaction_family_group_summary": interaction_family_group_summary,
            "interaction_family_group_label": ",".join(
                [
                    f"modal-transfer={interaction_family_group_summary['modal_transfer']['ready_count']}/{interaction_family_group_summary['modal_transfer']['total_count']}",
                    f"phase-assimilation-coupling={interaction_family_group_summary['phase_assimilation_coupling']['ready_count']}/{interaction_family_group_summary['phase_assimilation_coupling']['total_count']}",
                    f"streaming-partition-coupling={interaction_family_group_summary['streaming_partition_coupling']['ready_count']}/{interaction_family_group_summary['streaming_partition_coupling']['total_count']}",
                    f"integrated-vibration-coupling={interaction_family_group_summary['integrated_vibration_coupling']['ready_count']}/{interaction_family_group_summary['integrated_vibration_coupling']['total_count']}",
                    f"resilience-recovery-coupling={interaction_family_group_summary['resilience_recovery_coupling']['ready_count']}/{interaction_family_group_summary['resilience_recovery_coupling']['total_count']}",
                    f"kinematic-coupling={interaction_family_group_summary['kinematic_coupling']['ready_count']}/{interaction_family_group_summary['kinematic_coupling']['total_count']}",
                    f"constraint-bridge={interaction_family_group_summary['constraint_bridge']['ready_count']}/{interaction_family_group_summary['constraint_bridge']['total_count']}",
                    f"wave-radiation={interaction_family_group_summary['wave_radiation']['ready_count']}/{interaction_family_group_summary['wave_radiation']['total_count']}",
                    f"boundary-absorption-coupling={interaction_family_group_summary['boundary_absorption_coupling']['ready_count']}/{interaction_family_group_summary['boundary_absorption_coupling']['total_count']}",
                    f"attention-guided-transfer={interaction_family_group_summary['attention_guided_transfer']['ready_count']}/{interaction_family_group_summary['attention_guided_transfer']['total_count']}",
                    f"residual-stabilization-coupling={interaction_family_group_summary['residual_stabilization_coupling']['ready_count']}/{interaction_family_group_summary['residual_stabilization_coupling']['total_count']}",
                    f"solver-feedback-coupling={interaction_family_group_summary['solver_feedback_coupling']['ready_count']}/{interaction_family_group_summary['solver_feedback_coupling']['total_count']}",
                    f"multiphysics-coupling={interaction_family_group_summary['multiphysics_coupling']['ready_count']}/{interaction_family_group_summary['multiphysics_coupling']['total_count']}",
                    f"explicit-shear-transfer={interaction_family_group_summary['explicit_shear_transfer']['ready_count']}/{interaction_family_group_summary['explicit_shear_transfer']['total_count']}",
                    f"phase-latency-coupling={interaction_family_group_summary['phase_latency_coupling']['ready_count']}/{interaction_family_group_summary['phase_latency_coupling']['total_count']}",
                    f"cache-window-coupling={interaction_family_group_summary['cache_window_coupling']['ready_count']}/{interaction_family_group_summary['cache_window_coupling']['total_count']}",
                    f"whitebox-feedback-coupling={interaction_family_group_summary['whitebox_feedback_coupling']['ready_count']}/{interaction_family_group_summary['whitebox_feedback_coupling']['total_count']}",
                    f"recovery-residual-coupling={interaction_family_group_summary['recovery_residual_coupling']['ready_count']}/{interaction_family_group_summary['recovery_residual_coupling']['total_count']}",
                    f"support-contact-modulation-coupling={interaction_family_group_summary['support_contact_modulation_coupling']['ready_count']}/{interaction_family_group_summary['support_contact_modulation_coupling']['total_count']}",
                    f"lining-recovery-coupling={interaction_family_group_summary['lining_recovery_coupling']['ready_count']}/{interaction_family_group_summary['lining_recovery_coupling']['total_count']}",
                    f"panel-feedback-coupling={interaction_family_group_summary['panel_feedback_coupling']['ready_count']}/{interaction_family_group_summary['panel_feedback_coupling']['total_count']}",
                    f"pressure-mapping-coupling={interaction_family_group_summary['pressure_mapping_coupling']['ready_count']}/{interaction_family_group_summary['pressure_mapping_coupling']['total_count']}",
                    f"shell-shell={interaction_family_group_summary['shell_shell']['ready_count']}/{interaction_family_group_summary['shell_shell']['total_count']}",
                    f"shell-wall={interaction_family_group_summary['shell_wall']['ready_count']}/{interaction_family_group_summary['shell_wall']['total_count']}",
                    f"footing-soil={interaction_family_group_summary['footing_soil']['ready_count']}/{interaction_family_group_summary['footing_soil']['total_count']}",
                    f"track-slab={interaction_family_group_summary['track_slab']['ready_count']}/{interaction_family_group_summary['track_slab']['total_count']}",
                    f"vehicle-track={interaction_family_group_summary['vehicle_track']['ready_count']}/{interaction_family_group_summary['vehicle_track']['total_count']}",
                    f"tunnel-lining-soil={interaction_family_group_summary['tunnel_lining_soil']['ready_count']}/{interaction_family_group_summary['tunnel_lining_soil']['total_count']}",
                    f"joint-panel={interaction_family_group_summary['joint_panel']['ready_count']}/{interaction_family_group_summary['joint_panel']['total_count']}",
                    f"ssi={interaction_family_group_summary['ssi']['ready_count']}/{interaction_family_group_summary['ssi']['total_count']}",
                    f"soil-tunnel={interaction_family_group_summary['soil_tunnel']['ready_count']}/{interaction_family_group_summary['soil_tunnel']['total_count']}",
                    f"direct-contact={interaction_family_group_summary['direct_structural_contact']['ready_count']}/{interaction_family_group_summary['direct_structural_contact']['total_count']}",
                ]
            ),
            "direct_contact_ready_count": int(direct_ready_count),
            "direct_contact_total_count": 6,
            "foundation_member_type_count": int(foundation_summary.get("foundation_member_type_count", 0) or 0),
            "soil_profile": str(ssi_summary.get("soil_profile", "") or ""),
            "transfer_ratio": float(substructuring_metrics.get("mean_transfer_ratio_building_to_track", 0.0) or 0.0),
            "interface_gap_norm": float(sync_inline.get("max_gap_norm", 0.0) or 0.0),
            "interaction_source_family_ready_count": int(source_family_ready_count),
            "interaction_source_family_total_count": int(source_family_total_count),
            "interaction_source_families": sorted(source_family_cases.keys()),
            "surface_row_labels": [str(row.get("label", "")) for row in matrix_rows],
            "interaction_family_labels": [str(row.get("label", "")) for row in interaction_family_rows],
        }
        summary_line = (
            f"Surface interaction benchmark: {'PASS' if contract_pass else 'GAP'} | "
            f"ready={ready_row_count}/{total_row_count} | "
            f"family_matrix={interaction_family_ready_count}/{interaction_family_total_count} | "
            f"source_families={source_family_ready_count}/{source_family_total_count} | "
            f"shell_surface={'yes' if shell_surface_ready else 'no'} | "
            f"interface_transfer={'yes' if interface_transfer_ready else 'no'} | "
            f"interface_gap={'yes' if interface_gap_ready else 'no'} | "
            f"foundation={'yes' if foundation_ready else 'no'} | "
            f"track_slab={'yes' if track_slab_ready else 'no'} | "
            f"vehicle_track={'yes' if vehicle_track_ready else 'no'} | "
            f"tunnel_lining_soil={'yes' if tunnel_lining_soil_ready else 'no'} | "
            f"joint_panel={'yes' if joint_panel_ready else 'no'} | "
            f"ssi={'yes' if ssi_ready else 'no'} | "
            f"soil_tunnel={'yes' if soil_tunnel_ready else 'no'} | "
            f"direct_contact={direct_ready_count}/6 | "
            f"general_fe_coupling={'yes' if general_fe_coupling_ready else 'no'} | "
            f"groups={summary['interaction_family_group_label']}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-surface-interaction-benchmark-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                **input_payload,
                "input_sha256": {
                    "flexible_diaphragm_report": _sha256(diaphragm_path) if diaphragm_path.exists() else "",
                    "substructuring_interface_report": _sha256(substructuring_path) if substructuring_path.exists() else "",
                    "sync_stress_report": _sha256(sync_stress_path) if sync_stress_path.exists() else "",
                    "foundation_soil_link_gate_report": _sha256(foundation_path) if foundation_path.exists() else "",
                    "moving_load_integrator_report": _sha256(moving_load_path) if moving_load_path.exists() else "",
                    "vti_coupled_solver_report": _sha256(vti_coupled_path) if vti_coupled_path.exists() else "",
                    "track_dynamics_dataset_report": _sha256(track_dataset_path) if track_dataset_path.exists() else "",
                    "tunnel_dynamics_dataset_report": _sha256(tunnel_dataset_path) if tunnel_dataset_path.exists() else "",
                    "panel_zone_clash_report": _sha256(panel_zone_path) if panel_zone_path.exists() else "",
                    "ssi_boundary_report": _sha256(ssi_path) if ssi_path.exists() else "",
                    "soil_tunnel_ssi_report": _sha256(soil_tunnel_path) if soil_tunnel_path.exists() else "",
                    "structural_contact_gate_report": _sha256(structural_contact_path) if structural_contact_path.exists() else "",
                    "dynamics_boundary_report": _sha256(dynamics_boundary_path) if dynamics_boundary_path.exists() else "",
                    "moving_load_attention_report": _sha256(moving_load_attention_path) if moving_load_attention_path.exists() else "",
                    "physics_residual_contract_report": _sha256(physics_residual_path) if physics_residual_path.exists() else "",
                    "phase_correction_assimilation_report": _sha256(phase_correction_path) if phase_correction_path.exists() else "",
                    "multiscale_l3_streaming_report": _sha256(multiscale_streaming_path) if multiscale_streaming_path.exists() else "",
                    "phasee_integrated_summary_report": _sha256(phasee_integrated_path) if phasee_integrated_path.exists() else "",
                    "phasef_resilience_summary_report": _sha256(phasef_resilience_path) if phasef_resilience_path.exists() else "",
                    "benchmark_cases": {str(path): _sha256(path) if path.exists() else "" for path in benchmark_case_paths},
                },
            },
            "checks": checks,
            "matrix_rows": matrix_rows,
            "interaction_family_rows": interaction_family_rows,
            "summary": summary,
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "limitations": [
                "This gate summarizes checked-in FE interaction contracts and does not claim a full general-contact formulation by itself.",
                "Interface continuity is currently evidenced through sync/transfer contracts rather than a full mortar or penalty surface solver.",
                "Direct structural contact family coverage is imported from the structural-contact gate rather than recomputed here.",
                "The interaction family matrix expands coarse benchmark rows into direct contact, foundation/soil, and interface family slices for review, but it is still evidence-driven rather than a monolithic general-contact formulation.",
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        if not contract_pass:
            raise SystemExit(1)
    except InputContractError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-surface-interaction-benchmark-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {},
            "matrix_rows": [],
            "summary": {},
            "summary_line": "Surface interaction benchmark: GAP | invalid input",
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(payload["summary_line"])
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
