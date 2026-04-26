#!/usr/bin/env python3
"""Generate a deterministic local reference regression report for representative structural cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_PATH = Path("implementation/phase1/reference_regression_baseline.json")
DEFAULT_REPORT_PATH = Path("implementation/phase1/release/reference_regression/reference_regression_report.json")

REASONS = {
    "PASS": "all deterministic local reference cases match the committed baseline within tolerance",
    "ERR_INVALID_REFERENCE_BASELINE": "reference regression baseline is missing or invalid",
    "ERR_REFERENCE_REGRESSION_FAIL": "one or more deterministic local reference cases drifted beyond tolerance",
}


def _generated_at(value: str | None = None) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return datetime.now(timezone.utc).isoformat()


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _round_float(value: float, digits: int = 12) -> float:
    rounded = round(float(value), digits)
    if abs(rounded) < 10 ** (-(digits + 1)):
        return 0.0
    return rounded


def _normalize_metric_map(metrics: dict[str, float]) -> dict[str, float]:
    return {str(key): _round_float(float(value)) for key, value in sorted(metrics.items())}


def _normalize_parameter_map(parameters: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in sorted(parameters.items()):
        if isinstance(value, dict):
            normalized[str(key)] = _normalize_parameter_map(value)
        elif isinstance(value, list):
            normalized[str(key)] = [
                _round_float(item) if isinstance(item, (int, float)) else item
                for item in value
            ]
        elif isinstance(value, (int, float)):
            normalized[str(key)] = _round_float(value)
        else:
            normalized[str(key)] = value
    return normalized


def _simple_beam_case() -> dict[str, Any]:
    span = 6.0
    uniform_load = 12.0
    flexural_rigidity = 20_000.0
    total_load = uniform_load * span
    reaction = total_load / 2.0
    midspan_moment = uniform_load * span * span / 8.0
    max_deflection = 5.0 * uniform_load * span**4 / (384.0 * flexural_rigidity)
    return {
        "case_id": "simple_beam_uniform_load",
        "reference_class": "simple_beam",
        "description": "Simply supported Euler-Bernoulli beam under a full-span uniform load.",
        "tags": ["beam", "static", "closed_form"],
        "parameters": {
            "span": span,
            "uniform_load": uniform_load,
            "flexural_rigidity": flexural_rigidity,
        },
        "metrics": {
            "left_support_reaction": reaction,
            "right_support_reaction": reaction,
            "midspan_bending_moment": midspan_moment,
            "max_deflection": max_deflection,
        },
    }


def _truss_case() -> dict[str, Any]:
    span = 4.0
    rise = 3.0
    apex_load = 120.0
    axial_rigidity = 30_000.0
    half_span = span / 2.0
    member_length = math.hypot(half_span, rise)
    sin_theta = rise / member_length
    axial_force = apex_load / (2.0 * sin_theta)
    apex_vertical_displacement = apex_load * member_length / (2.0 * axial_rigidity * sin_theta**2)
    support_reaction = apex_load / 2.0
    return {
        "case_id": "two_bar_truss_apex_load",
        "reference_class": "truss",
        "description": "Symmetric two-bar truss with a vertical apex load.",
        "tags": ["truss", "static", "closed_form"],
        "parameters": {
            "span": span,
            "rise": rise,
            "apex_load": apex_load,
            "axial_rigidity": axial_rigidity,
        },
        "metrics": {
            "left_support_vertical_reaction": support_reaction,
            "right_support_vertical_reaction": support_reaction,
            "member_axial_force_abs": axial_force,
            "apex_vertical_displacement": apex_vertical_displacement,
        },
    }


def _portal_frame_case() -> dict[str, Any]:
    story_height = 3.5
    lateral_load = 60.0
    column_flexural_rigidity = 4_200.0
    roof_drift = lateral_load * story_height**3 / (24.0 * column_flexural_rigidity)
    base_moment = lateral_load * story_height / 4.0
    column_shear = lateral_load / 2.0
    return {
        "case_id": "portal_frame_lateral_sway",
        "reference_class": "portal_frame",
        "description": "One-story fixed-base portal frame with a rigid beam under lateral sway.",
        "tags": ["portal_frame", "static", "closed_form"],
        "parameters": {
            "story_height": story_height,
            "lateral_load": lateral_load,
            "column_flexural_rigidity": column_flexural_rigidity,
        },
        "metrics": {
            "roof_drift": roof_drift,
            "left_column_base_moment": base_moment,
            "right_column_base_moment": base_moment,
            "left_column_shear": column_shear,
            "right_column_shear": column_shear,
        },
    }


def _shear_building_case() -> dict[str, Any]:
    story_stiffness = [30_000.0, 20_000.0, 10_000.0]
    floor_forces = [30.0, 20.0, 10.0]
    story_shears = [sum(floor_forces[index:]) for index in range(len(floor_forces))]
    story_drifts = [story_shears[index] / story_stiffness[index] for index in range(len(story_stiffness))]
    roof_displacement = sum(story_drifts)
    return {
        "case_id": "three_story_shear_building_static",
        "reference_class": "shear_building",
        "description": "Three-story shear building under deterministic lateral floor forces.",
        "tags": ["shear_building", "static", "matrix_reduced"],
        "parameters": {
            "story_stiffness": story_stiffness,
            "floor_forces": floor_forces,
        },
        "metrics": {
            "story1_drift": story_drifts[0],
            "story2_drift": story_drifts[1],
            "story3_drift": story_drifts[2],
            "roof_displacement": roof_displacement,
            "base_shear": story_shears[0],
        },
    }


def _shell_patch_case() -> dict[str, Any]:
    youngs_modulus = 30_000.0
    poissons_ratio = 0.2
    thickness = 0.25
    area = 1.0
    strain_x = 0.0015
    strain_y = 0.0008
    gamma_xy = 0.0004
    coeff = youngs_modulus / (1.0 - poissons_ratio**2)
    shear_modulus = youngs_modulus / (2.0 * (1.0 + poissons_ratio))
    stress_x = coeff * (strain_x + poissons_ratio * strain_y)
    stress_y = coeff * (poissons_ratio * strain_x + strain_y)
    shear_stress = shear_modulus * gamma_xy
    membrane_resultant_x = stress_x * thickness
    membrane_resultant_y = stress_y * thickness
    membrane_resultant_xy = shear_stress * thickness
    strain_energy = 0.5 * area * thickness * (
        stress_x * strain_x + stress_y * strain_y + shear_stress * gamma_xy
    )
    return {
        "case_id": "shell_patch_constant_strain",
        "reference_class": "shell_patch",
        "description": "Plane-stress shell patch with a constant membrane strain field.",
        "tags": ["shell_patch", "membrane", "closed_form"],
        "parameters": {
            "youngs_modulus": youngs_modulus,
            "poissons_ratio": poissons_ratio,
            "thickness": thickness,
            "area": area,
            "strain_x": strain_x,
            "strain_y": strain_y,
            "gamma_xy": gamma_xy,
        },
        "metrics": {
            "membrane_stress_x": stress_x,
            "membrane_stress_y": stress_y,
            "membrane_shear_stress": shear_stress,
            "membrane_resultant_x": membrane_resultant_x,
            "membrane_resultant_y": membrane_resultant_y,
            "membrane_resultant_xy": membrane_resultant_xy,
            "strain_energy": strain_energy,
        },
    }


def _buckling_case() -> dict[str, Any]:
    youngs_modulus = 200_000.0
    second_moment = 0.0001
    length = 2.5
    effective_length_factor = 1.0
    effective_length = effective_length_factor * length
    critical_load = math.pi**2 * youngs_modulus * second_moment / effective_length**2
    normalized_critical_load = critical_load / (youngs_modulus * second_moment)
    return {
        "case_id": "euler_column_buckling",
        "reference_class": "buckling",
        "description": "Pinned-pinned Euler column critical load reference.",
        "tags": ["buckling", "eigenvalue", "closed_form"],
        "parameters": {
            "youngs_modulus": youngs_modulus,
            "second_moment": second_moment,
            "length": length,
            "effective_length_factor": effective_length_factor,
        },
        "metrics": {
            "critical_load": critical_load,
            "normalized_critical_load": normalized_critical_load,
        },
    }


def _modal_frequency_case() -> dict[str, Any]:
    # Mass-normalized 2-DOF chain with k = 1 and m = 1 gives closed-form eigenvalues.
    eigenvalue_1 = (3.0 - math.sqrt(5.0)) / 2.0
    eigenvalue_2 = (3.0 + math.sqrt(5.0)) / 2.0
    omega_1 = math.sqrt(eigenvalue_1)
    omega_2 = math.sqrt(eigenvalue_2)
    frequency_1 = omega_1 / (2.0 * math.pi)
    frequency_2 = omega_2 / (2.0 * math.pi)
    return {
        "case_id": "two_dof_modal_frequency",
        "reference_class": "modal_frequency",
        "description": "Closed-form modal frequencies for a 2-DOF unit mass-spring chain.",
        "tags": ["modal_frequency", "eigenvalue", "closed_form"],
        "parameters": {
            "mass_matrix": [[1.0, 0.0], [0.0, 1.0]],
            "stiffness_matrix": [[2.0, -1.0], [-1.0, 1.0]],
        },
        "metrics": {
            "fundamental_frequency_hz": frequency_1,
            "second_frequency_hz": frequency_2,
            "frequency_ratio": frequency_2 / frequency_1,
        },
    }


def _reaction_balance_case() -> dict[str, Any]:
    span = 5.0
    uniform_load = 4.0
    point_load = 10.0
    point_load_location = 2.0
    uniform_total = uniform_load * span
    left_reaction = uniform_total / 2.0 + point_load * (span - point_load_location) / span
    right_reaction = uniform_total / 2.0 + point_load * point_load_location / span
    vertical_balance_error = abs(left_reaction + right_reaction - uniform_total - point_load)
    moment_balance_error = abs(
        right_reaction * span
        - uniform_total * (span / 2.0)
        - point_load * point_load_location
    )
    return {
        "case_id": "beam_reaction_balance_mixed_load",
        "reference_class": "reaction_balance",
        "description": "Static reaction balance for a simply supported beam with point and distributed loads.",
        "tags": ["reaction_balance", "equilibrium", "closed_form"],
        "parameters": {
            "span": span,
            "uniform_load": uniform_load,
            "point_load": point_load,
            "point_load_location": point_load_location,
        },
        "metrics": {
            "left_support_reaction": left_reaction,
            "right_support_reaction": right_reaction,
            "vertical_balance_error": vertical_balance_error,
            "moment_balance_error": moment_balance_error,
        },
    }


def collect_reference_cases() -> list[dict[str, Any]]:
    cases = [
        _simple_beam_case(),
        _truss_case(),
        _portal_frame_case(),
        _shear_building_case(),
        _shell_patch_case(),
        _buckling_case(),
        _modal_frequency_case(),
        _reaction_balance_case(),
    ]
    normalized: list[dict[str, Any]] = []
    for case in cases:
        normalized.append(
            {
                "case_id": str(case["case_id"]),
                "reference_class": str(case["reference_class"]),
                "description": str(case["description"]),
                "tags": sorted(str(tag) for tag in case.get("tags", [])),
                "parameters": _normalize_parameter_map(case.get("parameters", {})),
                "metrics": _normalize_metric_map(case.get("metrics", {})),
            }
        )
    return normalized


def _baseline_case_row(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case["case_id"]),
        "reference_class": str(case["reference_class"]),
        "description": str(case["description"]),
        "tags": list(case.get("tags", [])),
        "parameters": dict(case.get("parameters", {})),
        "expected_metrics": dict(case.get("metrics", {})),
        "abs_tolerance": 1.0e-12,
        "rel_tolerance": 1.0e-10,
    }


def build_reference_baseline(*, generated_at: str | None = None) -> dict[str, Any]:
    cases = [_baseline_case_row(case) for case in collect_reference_cases()]
    reference_classes = sorted({row["reference_class"] for row in cases})
    metric_count = sum(len(row["expected_metrics"]) for row in cases)
    summary_line = (
        f"Reference baseline: cases={len(cases)} | "
        f"classes={len(reference_classes)} | metrics={metric_count}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-reference-regression-baseline",
        "generated_at": _generated_at(generated_at),
        "reference_classes": reference_classes,
        "summary": {
            "case_count": len(cases),
            "reference_class_count": len(reference_classes),
            "metric_count": metric_count,
        },
        "summary_line": summary_line,
        "cases": cases,
    }


def _valid_baseline(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases missing")
        return False, errors
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] invalid")
            continue
        case_id = str(case.get("case_id", "") or "")
        if not case_id:
            errors.append(f"cases[{index}].case_id missing")
            continue
        if case_id in seen:
            errors.append(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        expected_metrics = case.get("expected_metrics")
        if not isinstance(expected_metrics, dict) or not expected_metrics:
            errors.append(f"{case_id}.expected_metrics missing")
    return not errors, errors


def run_reference_regression(
    *,
    baseline_payload: dict[str, Any],
    baseline_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    current_cases = {case["case_id"]: case for case in collect_reference_cases()}
    baseline_ok, baseline_errors = _valid_baseline(baseline_payload)
    if not baseline_ok:
        return {
            "schema_version": "1.0",
            "run_id": "phase1-reference-regression",
            "generated_at": _generated_at(generated_at),
            "inputs": {
                "reference_baseline": str(baseline_path) if baseline_path else "",
            },
            "summary": {
                "case_count": 0,
                "reference_class_count": 0,
                "metric_count": 0,
                "passing_case_count": 0,
                "passing_metric_count": 0,
                "max_abs_error": 0.0,
                "max_normalized_error": 0.0,
            },
            "reference_classes": [],
            "case_rows": [],
            "missing_case_ids": [],
            "unexpected_case_ids": sorted(current_cases.keys()),
            "checks": {
                "baseline_loaded_pass": False,
                "all_case_ids_present": False,
                "all_metric_ids_present": False,
                "all_metrics_within_tolerance": False,
                "reference_class_coverage_pass": False,
            },
            "contract_pass": False,
            "reason_code": "ERR_INVALID_REFERENCE_BASELINE",
            "reason": REASONS["ERR_INVALID_REFERENCE_BASELINE"],
            "errors": baseline_errors,
            "summary_line": "Reference regression: FAIL | invalid baseline",
        }

    baseline_cases = baseline_payload["cases"]
    baseline_ids = {str(case["case_id"]) for case in baseline_cases}
    current_ids = set(current_cases.keys())
    missing_case_ids = sorted(baseline_ids - current_ids)
    unexpected_case_ids = sorted(current_ids - baseline_ids)

    case_rows: list[dict[str, Any]] = []
    passing_case_count = 0
    metric_count = 0
    passing_metric_count = 0
    max_abs_error = 0.0
    max_normalized_error = 0.0
    metric_id_pass = True
    tolerance_pass = True

    for baseline_case in baseline_cases:
        case_id = str(baseline_case["case_id"])
        current_case = current_cases.get(case_id, {})
        expected_metrics = (
            baseline_case.get("expected_metrics")
            if isinstance(baseline_case.get("expected_metrics"), dict)
            else {}
        )
        actual_metrics = (
            current_case.get("metrics")
            if isinstance(current_case.get("metrics"), dict)
            else {}
        )
        expected_metric_ids = set(expected_metrics.keys())
        actual_metric_ids = set(actual_metrics.keys())
        missing_metric_ids = sorted(expected_metric_ids - actual_metric_ids)
        unexpected_metric_ids = sorted(actual_metric_ids - expected_metric_ids)
        if missing_metric_ids or unexpected_metric_ids:
            metric_id_pass = False

        metric_rows: list[dict[str, Any]] = []
        case_passing_metrics = 0
        case_max_abs_error = 0.0
        case_max_normalized_error = 0.0

        abs_tolerance = float(baseline_case.get("abs_tolerance", 1.0e-12) or 1.0e-12)
        rel_tolerance = float(baseline_case.get("rel_tolerance", 1.0e-10) or 1.0e-10)

        for metric_name in sorted(expected_metric_ids | actual_metric_ids):
            metric_count += 1
            expected_value_raw = expected_metrics.get(metric_name)
            actual_value_raw = actual_metrics.get(metric_name)
            metric_present = isinstance(expected_value_raw, (int, float)) and isinstance(actual_value_raw, (int, float))
            if metric_present:
                expected_value = float(expected_value_raw)
                actual_value = float(actual_value_raw)
                abs_error = abs(actual_value - expected_value)
                allowed_error = max(abs_tolerance, rel_tolerance * abs(expected_value))
                rel_error = (
                    abs_error / abs(expected_value)
                    if abs(expected_value) > 1.0e-30
                    else (0.0 if abs_error == 0.0 else math.inf)
                )
                normalized_error = abs_error / allowed_error if allowed_error > 0.0 else math.inf
                passed = abs_error <= allowed_error
            else:
                expected_value = expected_value_raw
                actual_value = actual_value_raw
                abs_error = math.inf
                rel_error = math.inf
                allowed_error = 0.0
                normalized_error = math.inf
                passed = False
                tolerance_pass = False

            if passed:
                passing_metric_count += 1
                case_passing_metrics += 1
            else:
                tolerance_pass = False

            if math.isfinite(abs_error):
                max_abs_error = max(max_abs_error, abs_error)
                case_max_abs_error = max(case_max_abs_error, abs_error)
            if math.isfinite(normalized_error):
                max_normalized_error = max(max_normalized_error, normalized_error)
                case_max_normalized_error = max(case_max_normalized_error, normalized_error)

            metric_rows.append(
                {
                    "metric": metric_name,
                    "expected": expected_value,
                    "actual": actual_value,
                    "abs_error": None if not math.isfinite(abs_error) else _round_float(abs_error),
                    "rel_error": None if not math.isfinite(rel_error) else _round_float(rel_error),
                    "allowed_error": _round_float(allowed_error),
                    "normalized_error": None if not math.isfinite(normalized_error) else _round_float(normalized_error),
                    "contract_pass": bool(passed),
                }
            )

        case_contract_pass = (
            not missing_metric_ids
            and not unexpected_metric_ids
            and case_passing_metrics == len(metric_rows)
            and bool(metric_rows)
        )
        if case_contract_pass:
            passing_case_count += 1

        case_rows.append(
            {
                "case_id": case_id,
                "reference_class": str(
                    current_case.get("reference_class", baseline_case.get("reference_class", ""))
                ),
                "description": str(current_case.get("description", baseline_case.get("description", ""))),
                "tags": list(current_case.get("tags", baseline_case.get("tags", []))),
                "parameters": dict(current_case.get("parameters", baseline_case.get("parameters", {}))),
                "metric_count": len(metric_rows),
                "passing_metric_count": case_passing_metrics,
                "missing_metric_ids": missing_metric_ids,
                "unexpected_metric_ids": unexpected_metric_ids,
                "max_abs_error": _round_float(case_max_abs_error),
                "max_normalized_error": _round_float(case_max_normalized_error),
                "contract_pass": bool(case_contract_pass),
                "metric_rows": metric_rows,
            }
        )

    reference_classes = sorted({str(row["reference_class"]) for row in case_rows})
    baseline_reference_classes = sorted(str(item) for item in baseline_payload.get("reference_classes", []))
    checks = {
        "baseline_loaded_pass": True,
        "all_case_ids_present": not missing_case_ids and not unexpected_case_ids,
        "all_metric_ids_present": bool(metric_id_pass),
        "all_metrics_within_tolerance": bool(tolerance_pass),
        "reference_class_coverage_pass": reference_classes == baseline_reference_classes,
    }
    contract_pass = all(bool(value) for value in checks.values())
    reason_code = "PASS" if contract_pass else "ERR_REFERENCE_REGRESSION_FAIL"
    summary_line = (
        f"Reference regression: {'PASS' if contract_pass else 'FAIL'} | "
        f"cases={passing_case_count}/{len(case_rows)} | "
        f"metrics={passing_metric_count}/{metric_count} | "
        f"classes={len(reference_classes)} | "
        f"max_norm_err={_round_float(max_normalized_error)}"
    )

    inputs: dict[str, Any] = {
        "reference_baseline": str(baseline_path) if baseline_path else "",
    }
    if baseline_path and baseline_path.exists():
        inputs["reference_baseline_sha256"] = _sha256_path(baseline_path)

    return {
        "schema_version": "1.0",
        "run_id": "phase1-reference-regression",
        "generated_at": _generated_at(generated_at),
        "inputs": inputs,
        "summary": {
            "case_count": len(case_rows),
            "reference_class_count": len(reference_classes),
            "metric_count": metric_count,
            "passing_case_count": passing_case_count,
            "passing_metric_count": passing_metric_count,
            "max_abs_error": _round_float(max_abs_error),
            "max_normalized_error": _round_float(max_normalized_error),
        },
        "reference_classes": reference_classes,
        "case_rows": case_rows,
        "missing_case_ids": missing_case_ids,
        "unexpected_case_ids": unexpected_case_ids,
        "checks": checks,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-baseline",
        default=str(DEFAULT_BASELINE_PATH),
        help="Committed baseline JSON describing expected deterministic metrics.",
    )
    parser.add_argument(
        "--emit-reference-baseline",
        default="",
        help="Write a fresh baseline JSON and exit without running comparisons.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_REPORT_PATH),
        help="Reference regression report output path.",
    )
    parser.add_argument(
        "--generated-at",
        default="",
        help="Optional stable timestamp override for reproducible artifact generation.",
    )
    args = parser.parse_args()

    if str(args.emit_reference_baseline).strip():
        payload = build_reference_baseline(generated_at=args.generated_at)
        out_path = Path(args.emit_reference_baseline)
        _write_json(out_path, payload)
        print(f"Wrote reference regression baseline: {out_path}")
        return 0

    baseline_path = Path(args.reference_baseline)
    baseline_payload = _load_json(baseline_path)
    report = run_reference_regression(
        baseline_payload=baseline_payload,
        baseline_path=baseline_path,
        generated_at=args.generated_at,
    )
    out_path = Path(args.out)
    _write_json(out_path, report)
    print(f"Wrote reference regression report: {out_path}")
    return 0 if bool(report.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
