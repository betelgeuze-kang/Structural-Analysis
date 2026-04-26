#!/usr/bin/env python3
"""Evaluate direct steel/composite constitutive evidence for the closure gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.runtime_contracts import InputContractError, validate_input_contract
    from implementation.phase1.composite_constitutive_library import CompositeActionMaterial, composite_action_response
    from implementation.phase1.steel_constitutive_library import SteelMaterial, steel_response
except ImportError:  # pragma: no cover - script execution fallback
    from runtime_contracts import InputContractError, validate_input_contract
    from composite_constitutive_library import CompositeActionMaterial, composite_action_response
    from steel_constitutive_library import SteelMaterial, steel_response


DEFAULT_OUT = "implementation/phase1/steel_composite_constitutive_gate_report.json"

REASONS = {
    "PASS": "steel/composite constitutive benchmark matrix satisfies the active closure gate",
    "ERR_INVALID_INPUT": "invalid steel/composite constitutive gate input",
    "ERR_STEEL_CONSTITUTIVE": "steel constitutive benchmark coverage is incomplete",
    "ERR_COMPOSITE_CONSTITUTIVE": "composite constitutive benchmark coverage is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["min_steel_rows", "min_composite_rows", "out"],
    "properties": {
        "min_steel_rows": {"type": "integer", "minimum": 1},
        "min_composite_rows": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _row(
    *,
    family: str,
    case_id: str,
    metric: str,
    value: Any,
    passed: bool,
    detail: str,
    **metadata: Any,
) -> dict[str, Any]:
    row = {
        "family": family,
        "case_id": case_id,
        "metric": metric,
        "value": value,
        "passed": bool(passed),
        "detail": detail,
    }
    row.update(metadata)
    return row


def _collect_steel_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = SteelMaterial(fy_mpa=355.0, hardening_ratio=0.02, fu_mpa=540.0, fracture_strain=0.12)
    elastic = steel_response(0.0005, base)
    plastic = steel_response(0.01, base)
    rows.append(
        _row(
            family="steel",
            case_id="yield_transition",
            metric="elastic_state",
            value=elastic.state_tag,
            passed=elastic.state_tag == "elastic",
            detail="small tensile strain should remain elastic",
            observed_state_tag=elastic.state_tag,
            strain_ratio=abs(float(elastic.strain)) / max(float(base.eps_y), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="yield_transition",
            metric="plastic_state",
            value=plastic.state_tag,
            passed=plastic.state_tag.startswith("plastic"),
            detail="post-yield tensile strain should enter plastic hardening/cap",
            observed_state_tag=plastic.state_tag,
            strain_ratio=abs(float(plastic.strain)) / max(float(base.eps_y), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="yield_transition",
            metric="yield_ratio",
            value=abs(float(plastic.strain)) / max(float(base.eps_y), 1.0e-12),
            passed=abs(float(plastic.strain)) / max(float(base.eps_y), 1.0e-12) > 1.0,
            detail="post-yield tensile probe should exceed the elastic yield strain",
            observed_state_tag=plastic.state_tag,
            strain_ratio=abs(float(plastic.strain)) / max(float(base.eps_y), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="yield_transition",
            metric="stress_growth",
            value=abs(plastic.stress_mpa) - abs(elastic.stress_mpa),
            passed=abs(plastic.stress_mpa) > abs(elastic.stress_mpa) and 0.0 < plastic.tangent_mpa < elastic.tangent_mpa,
            detail="plastic branch should grow stress while reducing tangent from the elastic slope",
            observed_state_tag=plastic.state_tag,
            tangent_ratio=float(plastic.tangent_mpa) / max(float(elastic.tangent_mpa), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="yield_transition",
            metric="tangent_ratio",
            value=float(plastic.tangent_mpa) / max(float(elastic.tangent_mpa), 1.0e-12),
            passed=0.0 < float(plastic.tangent_mpa) / max(float(elastic.tangent_mpa), 1.0e-12) < 1.0,
            detail="post-yield tangent should remain positive but below the elastic slope",
            observed_state_tag=plastic.state_tag,
        )
    )

    buckling = SteelMaterial(
        fy_mpa=355.0,
        hardening_ratio=0.02,
        fu_mpa=540.0,
        fracture_strain=0.12,
        local_buckling_strain=0.025,
        post_buckling_residual_ratio=0.35,
    )
    unbuckled = steel_response(-0.05, base)
    buckled = steel_response(-0.05, buckling)
    rows.append(
        _row(
            family="steel",
            case_id="compression_local_buckling",
            metric="buckling_state",
            value=buckled.state_tag,
            passed=buckled.state_tag == "compression_local_buckling",
            detail="compressive response past the buckling strain should enter the post-buckling branch",
            observed_state_tag=buckled.state_tag,
            strain_ratio=abs(float(buckled.strain)) / max(float(buckling.local_buckling_strain), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="compression_local_buckling",
            metric="softened_strength",
            value=abs(unbuckled.stress_mpa) - abs(buckled.stress_mpa),
            passed=abs(buckled.stress_mpa) < abs(unbuckled.stress_mpa),
            detail="local buckling should reduce the available compressive stress",
            observed_state_tag=buckled.state_tag,
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="compression_local_buckling",
            metric="negative_tangent",
            value=buckled.tangent_mpa,
            passed=buckled.tangent_mpa < 0.0,
            detail="post-buckling branch should soften with a negative tangent",
            observed_state_tag=buckled.state_tag,
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="compression_local_buckling",
            metric="strength_retention_ratio",
            value=abs(float(buckled.stress_mpa)) / max(abs(float(unbuckled.stress_mpa)), 1.0e-12),
            passed=0.0 < abs(float(buckled.stress_mpa)) / max(abs(float(unbuckled.stress_mpa)), 1.0e-12) < 1.0,
            detail="post-buckling strength should remain positive but below the unbuckled plastic branch",
            observed_state_tag=buckled.state_tag,
        )
    )

    fractured = steel_response(0.15, base)
    rows.append(
        _row(
            family="steel",
            case_id="fracture_limit",
            metric="fracture_state",
            value=fractured.state_tag,
            passed=fractured.state_tag == "fracture_limit",
            detail="strain beyond the fracture limit should clamp the response",
            observed_state_tag=fractured.state_tag,
            strain_ratio=abs(float(fractured.strain)) / max(float(base.fracture_strain), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="fracture_limit",
            metric="zero_tangent",
            value=fractured.tangent_mpa,
            passed=abs(fractured.tangent_mpa) <= 1.0e-12,
            detail="fracture-limited response should not continue hardening",
            observed_state_tag=fractured.state_tag,
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="fracture_limit",
            metric="capped_strength",
            value=abs(fractured.stress_mpa),
            passed=abs(fractured.stress_mpa) <= float(base.fu_mpa) + 1.0e-9,
            detail="fracture response should remain capped by the ultimate strength",
            observed_state_tag=fractured.state_tag,
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="fracture_limit",
            metric="fracture_strain_ratio",
            value=abs(float(fractured.strain)) / max(float(base.fracture_strain), 1.0e-12),
            passed=abs(float(fractured.strain)) / max(float(base.fracture_strain), 1.0e-12) >= 1.0,
            detail="fracture probe should meet or exceed the fracture strain threshold",
            observed_state_tag=fractured.state_tag,
        )
    )

    compression = steel_response(-0.01, base)
    rows.append(
        _row(
            family="steel",
            case_id="compressive_plasticity",
            metric="compressive_sign",
            value=compression.stress_mpa,
            passed=compression.stress_mpa < 0.0,
            detail="compressive strain should produce compressive stress",
            observed_state_tag=compression.state_tag,
            strain_ratio=abs(float(compression.strain)) / max(float(base.eps_y), 1.0e-12),
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="compressive_plasticity",
            metric="yield_exceeded",
            value=abs(compression.stress_mpa),
            passed=abs(compression.stress_mpa) > float(base.fy_mpa),
            detail="compressive plasticity should develop stress beyond the yield point",
            observed_state_tag=compression.state_tag,
        )
    )
    rows.append(
        _row(
            family="steel",
            case_id="compressive_plasticity",
            metric="plastic_state",
            value=compression.state_tag,
            passed=compression.state_tag.startswith("plastic"),
            detail="compressive post-yield response should remain on the plastic branch",
            observed_state_tag=compression.state_tag,
        )
    )
    return rows


def _collect_composite_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mat = CompositeActionMaterial(
        steel=SteelMaterial(fy_mpa=355.0, hardening_ratio=0.02, fu_mpa=540.0, fracture_strain=0.12),
        connector_slip_y_strain=8.0e-4,
        connector_slip_u_strain=4.0e-3,
        residual_action_ratio=0.25,
        concrete_tension_carry_ratio=0.10,
    )
    full = composite_action_response(
        steel_strain=-0.0025,
        concrete_strain=-0.0012,
        slip_strain=1.0e-4,
        mat=mat,
    )
    partial = composite_action_response(
        steel_strain=-0.0025,
        concrete_strain=-0.0012,
        slip_strain=2.0e-3,
        mat=mat,
    )
    slipped = composite_action_response(
        steel_strain=-0.0025,
        concrete_strain=-0.0012,
        slip_strain=6.0e-3,
        mat=mat,
    )
    rows.append(
        _row(
            family="composite",
            case_id="connector_slip_transition",
            metric="full_interaction_state",
            value=full.connector_state_tag,
            passed=full.connector_state_tag == "full_interaction" and abs(full.action_ratio - 1.0) <= 1.0e-12,
            detail="small connector slip should preserve full interaction",
            connector_state_tag=full.connector_state_tag,
            composite_state_tag=full.state_tag,
            concrete_state_tag=getattr(full.concrete, "state_tag", ""),
            steel_state_tag=full.steel.state_tag,
            action_ratio=float(full.action_ratio),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="connector_slip_transition",
            metric="partial_interaction_state",
            value=partial.connector_state_tag,
            passed=partial.connector_state_tag == "partial_interaction",
            detail="mid-range connector slip should enter the partial interaction branch",
            connector_state_tag=partial.connector_state_tag,
            composite_state_tag=partial.state_tag,
            concrete_state_tag=getattr(partial.concrete, "state_tag", ""),
            steel_state_tag=partial.steel.state_tag,
            action_ratio=float(partial.action_ratio),
            slip_ratio=abs(float(partial.slip_strain)) / max(float(mat.connector_slip_u_strain), 1.0e-12),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="connector_slip_transition",
            metric="residual_interaction_state",
            value=slipped.connector_state_tag,
            passed=slipped.connector_state_tag == "residual_interaction"
            and abs(slipped.action_ratio - float(mat.residual_action_ratio)) <= 1.0e-12,
            detail="large connector slip should clamp to the residual interaction ratio",
            connector_state_tag=slipped.connector_state_tag,
            composite_state_tag=slipped.state_tag,
            concrete_state_tag=getattr(slipped.concrete, "state_tag", ""),
            steel_state_tag=slipped.steel.state_tag,
            action_ratio=float(slipped.action_ratio),
            slip_ratio=abs(float(slipped.slip_strain)) / max(float(mat.connector_slip_u_strain), 1.0e-12),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="connector_slip_transition",
            metric="partial_action_ratio",
            value=float(partial.action_ratio),
            passed=float(mat.residual_action_ratio) < float(partial.action_ratio) < 1.0,
            detail="partial interaction should retain more than residual action but less than full composite action",
            connector_state_tag=partial.connector_state_tag,
            composite_state_tag=partial.state_tag,
            action_ratio=float(partial.action_ratio),
            slip_ratio=abs(float(partial.slip_strain)) / max(float(mat.connector_slip_u_strain), 1.0e-12),
        )
    )

    rows.append(
        _row(
            family="composite",
            case_id="compression_capacity",
            metric="stress_drop_partial",
            value=abs(full.stress_mpa) - abs(partial.stress_mpa),
            passed=abs(full.stress_mpa) > abs(partial.stress_mpa),
            detail="partial interaction should reduce the compression-carrying capacity from the full interaction limit",
            connector_state_tag=partial.connector_state_tag,
            composite_state_tag=partial.state_tag,
            action_ratio=float(partial.action_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="compression_capacity",
            metric="stress_drop_with_slip",
            value=abs(full.stress_mpa) - abs(slipped.stress_mpa),
            passed=abs(full.stress_mpa) > abs(slipped.stress_mpa),
            detail="connector slip should reduce the compression-carrying capacity",
            connector_state_tag=slipped.connector_state_tag,
            composite_state_tag=slipped.state_tag,
            action_ratio=float(slipped.action_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="compression_capacity",
            metric="tangent_drop_with_slip",
            value=abs(full.tangent_mpa) - abs(slipped.tangent_mpa),
            passed=abs(full.tangent_mpa) > abs(slipped.tangent_mpa),
            detail="connector slip should reduce the effective composite tangent",
            connector_state_tag=slipped.connector_state_tag,
            composite_state_tag=slipped.state_tag,
            action_ratio=float(slipped.action_ratio),
        )
    )

    limited = composite_action_response(
        steel_strain=0.0015,
        concrete_strain=0.0010,
        slip_strain=1.0e-4,
        mat=mat,
    )
    carried = composite_action_response(
        steel_strain=0.0015,
        concrete_strain=0.0010,
        slip_strain=1.0e-4,
        mat=CompositeActionMaterial(
            steel=mat.steel,
            concrete=mat.concrete,
            connector_slip_y_strain=mat.connector_slip_y_strain,
            connector_slip_u_strain=mat.connector_slip_u_strain,
            residual_action_ratio=mat.residual_action_ratio,
            concrete_tension_carry_ratio=1.0,
        ),
    )
    rows.append(
        _row(
            family="composite",
            case_id="tension_participation_limit",
            metric="concrete_tension_state",
            value=limited.concrete.state_tag,
            passed=limited.concrete.state_tag == "tension_softening",
            detail="positive concrete strain should move the concrete branch into tension softening",
            connector_state_tag=limited.connector_state_tag,
            composite_state_tag=limited.state_tag,
            concrete_state_tag=getattr(limited.concrete, "state_tag", ""),
            steel_state_tag=limited.steel.state_tag,
            action_ratio=float(limited.action_ratio),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="tension_participation_limit",
            metric="reduced_tension_carry",
            value=carried.stress_mpa - limited.stress_mpa,
            passed=limited.stress_mpa < carried.stress_mpa,
            detail="reduced concrete tension carry ratio should lower the composite tensile stress",
            connector_state_tag=limited.connector_state_tag,
            composite_state_tag=limited.state_tag,
            concrete_state_tag=getattr(limited.concrete, "state_tag", ""),
            steel_state_tag=limited.steel.state_tag,
            action_ratio=float(limited.action_ratio),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="tension_participation_limit",
            metric="tension_carry_ratio",
            value=float(mat.concrete_tension_carry_ratio),
            passed=0.0 < float(mat.concrete_tension_carry_ratio) < 1.0,
            detail="concrete tension contribution should be explicitly reduced below full carry for the limited case",
            connector_state_tag=limited.connector_state_tag,
            composite_state_tag=limited.state_tag,
            concrete_state_tag=getattr(limited.concrete, "state_tag", ""),
            steel_state_tag=limited.steel.state_tag,
            action_ratio=float(limited.action_ratio),
            tension_carry_ratio=float(mat.concrete_tension_carry_ratio),
        )
    )

    steel_only = steel_response(-0.0025, mat.steel)
    rows.append(
        _row(
            family="composite",
            case_id="composite_gain",
            metric="full_interaction_gain",
            value=abs(full.stress_mpa) - abs(steel_only.stress_mpa),
            passed=abs(full.stress_mpa) > abs(steel_only.stress_mpa),
            detail="full interaction should exceed the standalone steel contribution in compression",
            connector_state_tag=full.connector_state_tag,
            composite_state_tag=full.state_tag,
            steel_state_tag=full.steel.state_tag,
            concrete_state_tag=getattr(full.concrete, "state_tag", ""),
            action_ratio=float(full.action_ratio),
        )
    )
    rows.append(
        _row(
            family="composite",
            case_id="composite_gain",
            metric="residual_interaction_gain",
            value=abs(slipped.stress_mpa) - abs(steel_only.stress_mpa),
            passed=abs(slipped.stress_mpa) > abs(steel_only.stress_mpa),
            detail="even residual interaction should retain some concrete compression participation",
            connector_state_tag=slipped.connector_state_tag,
            composite_state_tag=slipped.state_tag,
            steel_state_tag=slipped.steel.state_tag,
            concrete_state_tag=getattr(slipped.concrete, "state_tag", ""),
            action_ratio=float(slipped.action_ratio),
        )
    )
    return rows


def _family_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_ids = sorted({str(row.get("case_id", "")) for row in rows if str(row.get("case_id", ""))})
    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    return {
        "row_count": len(rows),
        "pass_count": pass_count,
        "fail_count": len(rows) - pass_count,
        "case_count": len(case_ids),
        "case_ids": case_ids,
    }


def _numeric_metric_values(rows: list[dict[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if str(row.get("metric", "")) != str(metric):
            continue
        value = row.get("value")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _label_set(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(row.get(key, "")).strip() for row in rows if str(row.get(key, "")).strip()})


def build_report(*, min_steel_rows: int = 12, min_composite_rows: int = 8) -> dict[str, Any]:
    steel_rows = _collect_steel_rows()
    composite_rows = _collect_composite_rows()
    steel_summary = _family_summary(steel_rows)
    composite_summary = _family_summary(composite_rows)
    steel_state_tags = _label_set(steel_rows, "observed_state_tag")
    connector_state_tags = _label_set(composite_rows, "connector_state_tag")
    composite_state_tags = _label_set(composite_rows, "composite_state_tag")
    concrete_state_tags = _label_set(composite_rows, "concrete_state_tag")
    steel_yield_ratio_values = _numeric_metric_values(steel_rows, "yield_ratio")
    steel_tangent_ratio_values = _numeric_metric_values(steel_rows, "tangent_ratio")
    steel_retention_values = _numeric_metric_values(steel_rows, "strength_retention_ratio")
    steel_fracture_ratio_values = _numeric_metric_values(steel_rows, "fracture_strain_ratio")
    steel_negative_tangent_values = _numeric_metric_values(steel_rows, "negative_tangent")
    composite_partial_action_values = _numeric_metric_values(composite_rows, "partial_action_ratio")
    composite_tension_ratio_values = _numeric_metric_values(composite_rows, "tension_carry_ratio")
    composite_stress_drop_values = _numeric_metric_values(composite_rows, "stress_drop_with_slip")
    composite_action_values = [
        float(row["action_ratio"])
        for row in composite_rows
        if isinstance(row.get("action_ratio"), (int, float)) and not isinstance(row.get("action_ratio"), bool)
    ]
    steel_state_coverage_pass = {
        "elastic",
        "plastic_hardening",
        "compression_local_buckling",
        "fracture_limit",
    }.issubset(set(steel_state_tags))
    composite_state_coverage_pass = {
        "full_interaction",
        "partial_interaction",
        "residual_interaction",
    }.issubset(set(connector_state_tags))
    steel_yield_ratio_pass = bool(steel_yield_ratio_values and max(steel_yield_ratio_values) > 1.0)
    steel_post_yield_tangent_pass = bool(
        steel_tangent_ratio_values and 0.0 < max(steel_tangent_ratio_values) < 1.0
    )
    steel_fracture_ratio_pass = bool(
        steel_fracture_ratio_values and max(steel_fracture_ratio_values) >= 1.0
    )
    composite_partial_interaction_pass = bool(
        composite_partial_action_values
        and float(composite_summary["pass_count"]) >= 1
        and max(composite_partial_action_values) < 1.0
        and min(composite_partial_action_values) > 0.0
    )
    composite_tension_ratio_pass = bool(
        composite_tension_ratio_values and 0.0 < min(composite_tension_ratio_values) < 1.0
    )
    steel_row_count = int(steel_summary["row_count"])
    composite_row_count = int(composite_summary["row_count"])
    steel_pass = bool(
        steel_row_count >= int(min_steel_rows)
        and int(steel_summary["pass_count"]) == steel_row_count
        and steel_state_coverage_pass
        and steel_yield_ratio_pass
        and steel_post_yield_tangent_pass
        and steel_fracture_ratio_pass
    )
    composite_pass = bool(
        composite_row_count >= int(min_composite_rows)
        and int(composite_summary["pass_count"]) == composite_row_count
        and composite_state_coverage_pass
        and composite_partial_interaction_pass
        and composite_tension_ratio_pass
    )
    if not steel_pass:
        reason_code = "ERR_STEEL_CONSTITUTIVE"
    elif not composite_pass:
        reason_code = "ERR_COMPOSITE_CONSTITUTIVE"
    else:
        reason_code = "PASS"

    summary = {
        "steel": {
            **steel_summary,
            "min_required_rows": int(min_steel_rows),
            "state_tag_count": len(steel_state_tags),
            "state_tags": steel_state_tags,
            "yield_ratio_max": float(max(steel_yield_ratio_values) if steel_yield_ratio_values else 0.0),
            "post_yield_tangent_ratio_max": float(max(steel_tangent_ratio_values) if steel_tangent_ratio_values else 0.0),
            "buckling_strength_retention_ratio_min": float(min(steel_retention_values) if steel_retention_values else 0.0),
            "fracture_strain_ratio_max": float(max(steel_fracture_ratio_values) if steel_fracture_ratio_values else 0.0),
            "negative_tangent_min_mpa": float(min(steel_negative_tangent_values) if steel_negative_tangent_values else 0.0),
        },
        "composite": {
            **composite_summary,
            "min_required_rows": int(min_composite_rows),
            "connector_state_count": len(connector_state_tags),
            "connector_state_tags": connector_state_tags,
            "state_tag_count": len(composite_state_tags),
            "state_tags": composite_state_tags,
            "concrete_state_tags": concrete_state_tags,
            "action_ratio_min": float(min(composite_action_values) if composite_action_values else 0.0),
            "action_ratio_max": float(max(composite_action_values) if composite_action_values else 0.0),
            "partial_action_ratio_max": float(max(composite_partial_action_values) if composite_partial_action_values else 0.0),
            "tension_carry_ratio_min": float(min(composite_tension_ratio_values) if composite_tension_ratio_values else 0.0),
            "stress_drop_with_slip_max_mpa": float(max(composite_stress_drop_values) if composite_stress_drop_values else 0.0),
        },
        "source": "constitutive_library_benchmarks",
        "libraries": [
            "steel_constitutive_library",
            "composite_constitutive_library",
            "bond_slip_interface",
        ],
    }
    checks = {
        "steel_rows_sufficient": steel_row_count >= int(min_steel_rows),
        "steel_all_rows_pass": int(steel_summary["pass_count"]) == steel_row_count,
        "steel_state_coverage_pass": steel_state_coverage_pass,
        "steel_yield_ratio_pass": steel_yield_ratio_pass,
        "steel_post_yield_tangent_pass": steel_post_yield_tangent_pass,
        "steel_local_buckling_pass": any(
            row["case_id"] == "compression_local_buckling" and row["metric"] == "softened_strength" and row["passed"]
            for row in steel_rows
        ),
        "steel_fracture_pass": any(
            row["case_id"] == "fracture_limit" and row["metric"] == "zero_tangent" and row["passed"]
            for row in steel_rows
        ),
        "steel_fracture_ratio_pass": steel_fracture_ratio_pass,
        "composite_rows_sufficient": composite_row_count >= int(min_composite_rows),
        "composite_all_rows_pass": int(composite_summary["pass_count"]) == composite_row_count,
        "composite_state_coverage_pass": composite_state_coverage_pass,
        "composite_partial_interaction_pass": composite_partial_interaction_pass,
        "composite_slip_pass": any(
            row["case_id"] == "connector_slip_transition" and row["metric"] == "residual_interaction_state" and row["passed"]
            for row in composite_rows
        ),
        "composite_tension_limit_pass": any(
            row["case_id"] == "tension_participation_limit" and row["metric"] == "reduced_tension_carry" and row["passed"]
            for row in composite_rows
        ),
        "composite_tension_ratio_pass": composite_tension_ratio_pass,
        "composite_residual_gain_pass": any(
            row["case_id"] == "composite_gain" and row["metric"] == "residual_interaction_gain" and row["passed"]
            for row in composite_rows
        ),
    }
    contract_pass = bool(steel_pass and composite_pass)
    summary_line = (
        f"Steel/composite constitutive gate: {'PASS' if contract_pass else 'CHECK'}"
        f" | steel={steel_summary['pass_count']}/{steel_row_count}"
        f"(states={len(steel_state_tags)},yield={summary['steel']['yield_ratio_max']:.2f},"
        f"buckling={summary['steel']['buckling_strength_retention_ratio_min']:.2f},"
        f"fracture={summary['steel']['fracture_strain_ratio_max']:.2f})"
        f" | composite={composite_summary['pass_count']}/{composite_row_count}"
        f"(conn={len(connector_state_tags)},action={summary['composite']['action_ratio_min']:.2f}-{summary['composite']['action_ratio_max']:.2f},"
        f"tension={summary['composite']['tension_carry_ratio_min']:.2f})"
        f" | steel_cases={steel_summary['case_count']}"
        f" | composite_cases={composite_summary['case_count']}"
        f" | source={summary['source']}"
    )
    return {
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
        "summary": summary,
        "checks": checks,
        "benchmark_rows": steel_rows + composite_rows,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-steel-rows", type=int, default=12)
    parser.add_argument("--min-composite-rows", type=int, default=8)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_payload = {
        "min_steel_rows": int(args.min_steel_rows),
        "min_composite_rows": int(args.min_composite_rows),
        "out": str(args.out),
    }
    try:
        validate_input_contract(
            input_payload,
            INPUT_SCHEMA,
            label="phase1.run_steel_composite_constitutive_gate",
        )
    except InputContractError as exc:
        report = {
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
            "summary_line": "Steel/composite constitutive gate: CHECK | invalid_input",
            "inputs": input_payload,
        }
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    report = build_report(
        min_steel_rows=int(args.min_steel_rows),
        min_composite_rows=int(args.min_composite_rows),
    )
    report["inputs"] = input_payload
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote steel/composite constitutive gate report: {args.out}")
    return 0 if bool(report.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
