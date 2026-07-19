"""Source-bound closed-form verification for three linear frame families.

The receipt built here is intentionally limited to Level 1 analytic truth.  It
executes the authoritative canonical 6-DOF linear-frame path and compares its
response with independent Euler--Bernoulli and slope-deflection equations.  It
does not create code-to-code, published, experimental, customer, or release
evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from structural_analysis.api.core import AnalysisConfig, analyze, load_model
from structural_analysis.solvers.linear.static import (
    AUTHORITATIVE_CPU_SOLVER_ID,
    RESIDUAL_FORMULA,
)


ANALYTIC_FRAME_SCHEMA_VERSION = "analytic-frame-verification.v1"
ANALYTIC_FRAME_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/analytic_frame_verification_v1.schema.json"
)
ANALYTIC_FRAME_NUMERIC_SERIALIZATION = (
    "binary64_round_trip_decimal_17_significant_digits"
)
ANALYTIC_FRAME_CATEGORIES = (
    "cantilever_beam",
    "simply_supported_beam",
    "portal_frame",
)
ANALYTIC_FRAME_TOLERANCE_POLICY = {
    "comparison_absolute_tolerance": 1.0e-10,
    "comparison_relative_tolerance": 1.0e-10,
    "zero_reference_absolute_tolerance": 1.0e-12,
    "free_relative_residual_tolerance": 1.0e-10,
    "energy_balance_absolute_tolerance": 1.0e-10,
    "stiffness_symmetry_absolute_tolerance": 1.0e-10,
}
ANALYTIC_FRAME_CLAIM_BOUNDARY = (
    "This receipt proves three repository-generated Level 1 analytic frame "
    "families under the narrow small-displacement, linear-elastic, prismatic "
    "Euler-Bernoulli assumptions and the authoritative CPU 6-DOF path. It does "
    "not prove an independent solver comparison, distributed-member loading, "
    "shear deformation, nonlinear response, published or experimental truth, "
    "customer validation, ResultIR authority, or release readiness."
)
_SOURCE_PATHS = (
    Path("src/structural_analysis/benchmark/analytic_frame.py"),
    Path("src/structural_analysis/api/core.py"),
    Path("src/structural_analysis/analyses/linear_static.py"),
    Path("src/structural_analysis/assembly/linear_static.py"),
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/io/neutral/loader.py"),
    Path("src/structural_analysis/materials/elastic.py"),
    Path("src/structural_analysis/model/entities.py"),
    Path("src/structural_analysis/model/schema.py"),
    Path("src/structural_analysis/results/schema.py"),
    Path("src/structural_analysis/results/viewer.py"),
    Path("src/structural_analysis/solvers/linear/static.py"),
    ANALYTIC_FRAME_SCHEMA_PATH,
    Path("scripts/build_analytic_frame_verification_artifact.py"),
    Path("tests/test_analytic_frame_verification.py"),
)


class AnalyticFrameVerificationError(ValueError):
    """Fail-closed analytic-frame receipt error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in _SOURCE_PATHS:
        resolved = repo_root / path
        if not resolved.is_file():
            raise AnalyticFrameVerificationError(
                f"analytic_frame_source_missing:{path.as_posix()}"
            )
        checksums[path.as_posix()] = _file_hash(resolved)
    return checksums


def _record(value: float) -> float:
    return float(format(float(value), ".17g"))


def _base_model() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        "unsupported_features": [],
        "warnings": [],
    }


def build_cantilever_beam_model() -> dict[str, Any]:
    """Return a one-element weak-axis cantilever with a nodal tip load."""

    return {
        **_base_model(),
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [{"id": "P1", "node": "N2", "components": {"FY": -10.0}}],
        "supports": [{"id": "SUP1", "node": "N1", "dofs": "all"}],
        "metadata": {
            "case_id": "analytic_cantilever_tip_load",
            "truth_class": "analytic_truth",
            "claim_boundary": "prismatic_euler_bernoulli_tip_load_only",
        },
    }


def build_simply_supported_beam_model() -> dict[str, Any]:
    """Return a two-element simply supported beam with a midpoint nodal load."""

    return {
        **_base_model(),
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [3.0, 0.0, 0.0]},
            {"id": "N3", "coordinates": [6.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            },
            {
                "id": "E2",
                "type": "frame",
                "nodes": ["N2", "N3"],
                "section": "S1",
                "material": "M1",
            },
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [{"id": "P1", "node": "N2", "components": {"FY": -30.0}}],
        "supports": [
            {"id": "PIN", "node": "N1", "dofs": ["UX", "UY", "UZ", "RX"]},
            {"id": "ROLLER", "node": "N3", "dofs": ["UY", "UZ"]},
        ],
        "metadata": {
            "case_id": "analytic_simply_supported_midpoint_load",
            "truth_class": "analytic_truth",
            "claim_boundary": "prismatic_euler_bernoulli_midpoint_nodal_load_only",
        },
    }


def build_portal_frame_model() -> dict[str, Any]:
    """Return a fixed-base, one-bay, three-member portal under roof shear."""

    return {
        **_base_model(),
        "nodes": [
            {"id": "A", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "B", "coordinates": [0.0, 3.0, 0.0]},
            {"id": "C", "coordinates": [4.0, 3.0, 0.0]},
            {"id": "D", "coordinates": [4.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "COL_L",
                "type": "frame",
                "nodes": ["A", "B"],
                "section": "SC",
                "material": "M1",
            },
            {
                "id": "BEAM",
                "type": "frame",
                "nodes": ["B", "C"],
                "section": "SB",
                "material": "M1",
            },
            {
                "id": "COL_R",
                "type": "frame",
                "nodes": ["D", "C"],
                "section": "SC",
                "material": "M1",
            },
        ],
        "sections": [
            {
                "id": "SC",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            },
            {
                "id": "SB",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 9.0e-5,
                "torsional_constant": 1.0e-5,
            },
        ],
        "loads": [
            {"id": "P_B", "node": "B", "components": {"FX": 10.0}},
            {"id": "P_C", "node": "C", "components": {"FX": 10.0}},
        ],
        "supports": [
            {"id": "FIX_A", "node": "A", "dofs": "all"},
            {"id": "FIX_D", "node": "D", "dofs": "all"},
        ],
        "metadata": {
            "case_id": "analytic_fixed_base_portal_roof_shear",
            "truth_class": "analytic_truth",
            "claim_boundary": "one_bay_prismatic_slope_deflection_roof_shear_only",
        },
    }


def _solve_model(model: dict[str, Any]) -> dict[str, Any]:
    with TemporaryDirectory(prefix="analytic-frame-verification-") as temporary:
        path = Path(temporary) / "model.json"
        path.write_text(
            json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = analyze(
            load_model(path),
            AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-10),
        )
    return result.to_dict()


def _comparison(
    *,
    quantity: str,
    unit: str,
    expected: float,
    actual: float,
) -> dict[str, Any]:
    expected_value = _record(expected)
    actual_value = _record(actual)
    absolute_error = _record(abs(actual_value - expected_value))
    if expected_value == 0.0:
        tolerance = ANALYTIC_FRAME_TOLERANCE_POLICY[
            "zero_reference_absolute_tolerance"
        ]
        relative_error = 0.0 if absolute_error == 0.0 else absolute_error / tolerance
    else:
        tolerance = (
            ANALYTIC_FRAME_TOLERANCE_POLICY["comparison_absolute_tolerance"]
            + ANALYTIC_FRAME_TOLERANCE_POLICY["comparison_relative_tolerance"]
            * abs(expected_value)
        )
        relative_error = absolute_error / abs(expected_value)
    return {
        "quantity": quantity,
        "unit": unit,
        "expected": expected_value,
        "actual": actual_value,
        "absolute_error": absolute_error,
        "relative_error": _record(relative_error),
        "absolute_tolerance": ANALYTIC_FRAME_TOLERANCE_POLICY[
            "comparison_absolute_tolerance"
        ],
        "relative_tolerance": ANALYTIC_FRAME_TOLERANCE_POLICY[
            "comparison_relative_tolerance"
        ],
        "zero_reference_absolute_tolerance": ANALYTIC_FRAME_TOLERANCE_POLICY[
            "zero_reference_absolute_tolerance"
        ],
        "contract_pass": absolute_error <= tolerance,
    }


def _case_payload(
    *,
    case_id: str,
    category: str,
    structural_family: str,
    formula_profile: str,
    formula: str,
    parameters: dict[str, float],
    model: dict[str, Any],
    comparisons: list[tuple[str, str, float, float]],
    result: dict[str, Any],
) -> dict[str, Any]:
    metrics = result["metrics"]
    rows = [
        _comparison(
            quantity=quantity,
            unit=unit,
            expected=expected,
            actual=actual,
        )
        for quantity, unit, expected, actual in comparisons
    ]
    residual = _record(metrics["relative_residual"])
    energy = _record(metrics["energy_balance_error"])
    symmetry = _record(metrics["stiffness_symmetry_error"])
    numerical_pass = bool(
        residual
        <= ANALYTIC_FRAME_TOLERANCE_POLICY["free_relative_residual_tolerance"]
        and energy
        <= ANALYTIC_FRAME_TOLERANCE_POLICY[
            "energy_balance_absolute_tolerance"
        ]
        and symmetry
        <= ANALYTIC_FRAME_TOLERANCE_POLICY[
            "stiffness_symmetry_absolute_tolerance"
        ]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
        and metrics["residual_formula"] == RESIDUAL_FORMULA
    )
    contract_pass = bool(
        result["status"] == "ready"
        and result["solver"] == AUTHORITATIVE_CPU_SOLVER_ID
        and result["analysis_type"] == "linear_static"
        and metrics["claim_boundary"] == "linear_static_3d_frame_cpu_reference_v1"
        and rows
        and all(row["contract_pass"] for row in rows)
        and numerical_pass
    )
    return {
        "case_id": case_id,
        "category": category,
        "structural_family": structural_family,
        "truth_basis": "analytic_closed_form",
        "formula_profile": formula_profile,
        "formula": formula,
        "parameters": {key: _record(value) for key, value in sorted(parameters.items())},
        "model_payload_hash": _hash_value(model),
        "solver_input_checksum": result["input_checksum"],
        "canonical_model_checksum": result["canonical_model_checksum"],
        "solver_id": result["solver"],
        "analysis_type": result["analysis_type"],
        "status": result["status"],
        "comparisons": rows,
        "numerical_checks": {
            "relative_residual": residual,
            "energy_balance_error": energy,
            "stiffness_symmetry_error": symmetry,
            "residual_formula": metrics["residual_formula"],
            "regularization_used": metrics["regularization_used"],
            "fallback_used": metrics["fallback_used"],
            "contract_pass": numerical_pass,
        },
        "contract_pass": contract_pass,
    }


def _cantilever_case() -> dict[str, Any]:
    model = build_cantilever_beam_model()
    result = _solve_model(model)
    metrics = result["metrics"]
    elastic_modulus = 200.0e6
    inertia_z = 5.0e-5
    length = 2.0
    load = -10.0
    return _case_payload(
        case_id="analytic_cantilever_tip_load",
        category="cantilever_beam",
        structural_family="cantilever_frame_beam",
        formula_profile="euler_bernoulli_cantilever_tip_load.v1",
        formula="delta=P*L^3/(3*E*Iz); reaction_y=-P; reaction_mz=-P*L",
        parameters={"E_kN_per_m2": elastic_modulus, "Iz_m4": inertia_z, "L_m": length, "P_kN": load},
        model=model,
        result=result,
        comparisons=[
            (
                "tip_displacement_UY",
                "m",
                load * length**3 / (3.0 * elastic_modulus * inertia_z),
                metrics["displacements"]["N2"]["UY"],
            ),
            ("base_reaction_UY", "kN", -load, metrics["reactions"]["N1"]["UY"]),
            (
                "base_reaction_RZ",
                "kN*m",
                -load * length,
                metrics["reactions"]["N1"]["RZ"],
            ),
        ],
    )


def _simply_supported_case() -> dict[str, Any]:
    model = build_simply_supported_beam_model()
    result = _solve_model(model)
    metrics = result["metrics"]
    elastic_modulus = 200.0e6
    inertia_z = 5.0e-5
    length = 6.0
    load = -30.0
    reaction = -0.5 * load
    return _case_payload(
        case_id="analytic_simply_supported_midpoint_load",
        category="simply_supported_beam",
        structural_family="simply_supported_frame_beam",
        formula_profile="euler_bernoulli_simply_supported_midpoint_load.v1",
        formula="delta_mid=P*L^3/(48*E*Iz); reaction_left=reaction_right=-P/2",
        parameters={"E_kN_per_m2": elastic_modulus, "Iz_m4": inertia_z, "L_m": length, "P_kN": load},
        model=model,
        result=result,
        comparisons=[
            (
                "midpoint_displacement_UY",
                "m",
                load * length**3 / (48.0 * elastic_modulus * inertia_z),
                metrics["displacements"]["N2"]["UY"],
            ),
            ("left_reaction_UY", "kN", reaction, metrics["reactions"]["N1"]["UY"]),
            ("right_reaction_UY", "kN", reaction, metrics["reactions"]["N3"]["UY"]),
        ],
    )


def _portal_case() -> dict[str, Any]:
    model = build_portal_frame_model()
    result = _solve_model(model)
    metrics = result["metrics"]
    elastic_modulus = 200.0e6
    area = 0.02
    column_inertia = 5.0e-5
    beam_inertia = 9.0e-5
    height = 3.0
    span = 4.0
    total_load = 20.0
    denominator = (
        6.0 * area * height * beam_inertia * span**2
        + area * column_inertia * span**3
        + 24.0 * height * beam_inertia * column_inertia
    )
    sway = (
        height**3
        * total_load
        * (
            3.0 * area * height * beam_inertia * span**2
            + 2.0 * area * column_inertia * span**3
            + 48.0 * height * beam_inertia * column_inertia
        )
        / (12.0 * elastic_modulus * column_inertia * denominator)
    )
    vertical = (
        3.0
        * height**3
        * beam_inertia
        * span
        * total_load
        / (elastic_modulus * denominator)
    )
    rotation = (
        -height**2
        * total_load
        * (area * span**3 + 24.0 * height * beam_inertia)
        / (4.0 * elastic_modulus * denominator)
    )
    base_vertical = (
        -3.0
        * area
        * height**2
        * beam_inertia
        * span
        * total_load
        / denominator
    )
    base_moment = (
        height
        * total_load
        * (
            3.0 * area * height * beam_inertia * span**2
            + area * column_inertia * span**3
            + 24.0 * height * beam_inertia * column_inertia
        )
        / (2.0 * denominator)
    )
    comparisons = [
        ("left_roof_sway_UX", "m", sway, metrics["displacements"]["B"]["UX"]),
        ("right_roof_sway_UX", "m", sway, metrics["displacements"]["C"]["UX"]),
        ("left_roof_vertical_UY", "m", vertical, metrics["displacements"]["B"]["UY"]),
        ("right_roof_vertical_UY", "m", -vertical, metrics["displacements"]["C"]["UY"]),
        ("left_joint_rotation_RZ", "rad", rotation, metrics["displacements"]["B"]["RZ"]),
        ("right_joint_rotation_RZ", "rad", rotation, metrics["displacements"]["C"]["RZ"]),
        ("left_base_reaction_UX", "kN", -total_load / 2.0, metrics["reactions"]["A"]["UX"]),
        ("right_base_reaction_UX", "kN", -total_load / 2.0, metrics["reactions"]["D"]["UX"]),
        ("left_base_reaction_UY", "kN", base_vertical, metrics["reactions"]["A"]["UY"]),
        ("right_base_reaction_UY", "kN", -base_vertical, metrics["reactions"]["D"]["UY"]),
        ("left_base_reaction_RZ", "kN*m", base_moment, metrics["reactions"]["A"]["RZ"]),
        ("right_base_reaction_RZ", "kN*m", base_moment, metrics["reactions"]["D"]["RZ"]),
    ]
    return _case_payload(
        case_id="analytic_fixed_base_portal_roof_shear",
        category="portal_frame",
        structural_family="one_bay_fixed_base_portal_frame",
        formula_profile="finite_ea_ei_portal_slope_deflection.v1",
        formula=(
            "closed_form_6dof_slope_deflection_with_finite_column_EA_and_"
            "column_beam_EI; symmetric_roof_shear"
        ),
        parameters={
            "E_kN_per_m2": elastic_modulus,
            "A_m2": area,
            "Ic_m4": column_inertia,
            "Ib_m4": beam_inertia,
            "H_m": height,
            "L_m": span,
            "P_total_kN": total_load,
        },
        model=model,
        result=result,
        comparisons=comparisons,
    )


def _artifact_hash(payload: dict[str, Any]) -> str:
    without_hash = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return _hash_value(without_hash)


def build_analytic_frame_verification_artifact(
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Execute all three cases and return their deterministic source-bound receipt."""

    cases = [_cantilever_case(), _simply_supported_case(), _portal_case()]
    checksums = _source_checksums(repo_root)
    contract_pass = bool(
        tuple(row["category"] for row in cases) == ANALYTIC_FRAME_CATEGORIES
        and all(row["contract_pass"] for row in cases)
    )
    payload = {
        "schema_version": ANALYTIC_FRAME_SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "numeric_serialization_profile": ANALYTIC_FRAME_NUMERIC_SERIALIZATION,
        "source": {
            "input_checksums": checksums,
            "source_set_hash": _hash_value(checksums),
        },
        "tolerance_policy": dict(ANALYTIC_FRAME_TOLERANCE_POLICY),
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "passing_case_count": sum(row["contract_pass"] is True for row in cases),
            "categories": list(ANALYTIC_FRAME_CATEGORIES),
            "contract_pass": contract_pass,
        },
        "claims": {
            "cantilever_beam_analytic_evidence": cases[0]["contract_pass"],
            "simply_supported_beam_analytic_evidence": cases[1]["contract_pass"],
            "portal_frame_analytic_evidence": cases[2]["contract_pass"],
            "code_to_code_evidence": False,
            "published_benchmark_evidence": False,
            "experimental_evidence": False,
            "customer_shadow_evidence": False,
            "release_readiness": False,
        },
        "blockers_remaining": [
            "independent_code_to_code_evidence_not_included",
            "published_benchmark_evidence_not_included",
            "experimental_evidence_not_included",
            "customer_shadow_evidence_not_included",
            "release_readiness_not_established",
        ],
        "claim_boundary": ANALYTIC_FRAME_CLAIM_BOUNDARY,
        "contract_pass": contract_pass,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    _validate_schema_and_semantics(payload, repo_root=repo_root)
    return payload


def _validate_schema_and_semantics(
    payload: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    schema = json.loads(
        (repo_root / ANALYTIC_FRAME_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise AnalyticFrameVerificationError(
            "analytic_frame_schema_invalid"
        ) from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise AnalyticFrameVerificationError("analytic_frame_artifact_hash_mismatch")
    checksums = payload["source"]["input_checksums"]
    if payload["source"]["source_set_hash"] != _hash_value(checksums):
        raise AnalyticFrameVerificationError("analytic_frame_source_set_hash_mismatch")
    cases = payload["cases"]
    if tuple(row["category"] for row in cases) != ANALYTIC_FRAME_CATEGORIES:
        raise AnalyticFrameVerificationError("analytic_frame_category_order_invalid")
    for case in cases:
        for row in case["comparisons"]:
            absolute_error = abs(float(row["actual"]) - float(row["expected"]))
            expected_relative = (
                absolute_error
                / ANALYTIC_FRAME_TOLERANCE_POLICY[
                    "zero_reference_absolute_tolerance"
                ]
                if float(row["expected"]) == 0.0 and absolute_error != 0.0
                else 0.0
                if float(row["expected"]) == 0.0
                else absolute_error / abs(float(row["expected"]))
            )
            if not math.isclose(
                float(row["absolute_error"]),
                absolute_error,
                rel_tol=1.0e-14,
                abs_tol=1.0e-30,
            ) or not math.isclose(
                float(row["relative_error"]),
                expected_relative,
                rel_tol=1.0e-14,
                abs_tol=1.0e-30,
            ):
                raise AnalyticFrameVerificationError(
                    "analytic_frame_comparison_error_invalid"
                )
            tolerance = (
                float(row["zero_reference_absolute_tolerance"])
                if float(row["expected"]) == 0.0
                else float(row["absolute_tolerance"])
                + float(row["relative_tolerance"])
                * abs(float(row["expected"]))
            )
            if row["contract_pass"] is not (absolute_error <= tolerance):
                raise AnalyticFrameVerificationError(
                    "analytic_frame_comparison_pass_invalid"
                )
        checks = case["numerical_checks"]
        numerical_pass = bool(
            checks["relative_residual"]
            <= ANALYTIC_FRAME_TOLERANCE_POLICY[
                "free_relative_residual_tolerance"
            ]
            and checks["energy_balance_error"]
            <= ANALYTIC_FRAME_TOLERANCE_POLICY[
                "energy_balance_absolute_tolerance"
            ]
            and checks["stiffness_symmetry_error"]
            <= ANALYTIC_FRAME_TOLERANCE_POLICY[
                "stiffness_symmetry_absolute_tolerance"
            ]
            and checks["regularization_used"] is False
            and checks["fallback_used"] is False
            and checks["residual_formula"] == RESIDUAL_FORMULA
        )
        if checks["contract_pass"] is not numerical_pass:
            raise AnalyticFrameVerificationError(
                "analytic_frame_numerical_pass_invalid"
            )
        expected_case_pass = bool(
            case["status"] == "ready"
            and case["solver_id"] == AUTHORITATIVE_CPU_SOLVER_ID
            and all(row["contract_pass"] for row in case["comparisons"])
            and numerical_pass
        )
        if case["contract_pass"] is not expected_case_pass:
            raise AnalyticFrameVerificationError(
                "analytic_frame_case_pass_invalid"
            )
    if payload["contract_pass"] is not all(row["contract_pass"] for row in cases):
        raise AnalyticFrameVerificationError("analytic_frame_contract_pass_invalid")
    expected_passing = sum(row["contract_pass"] is True for row in cases)
    if payload["summary"] != {
        "case_count": 3,
        "passing_case_count": expected_passing,
        "categories": list(ANALYTIC_FRAME_CATEGORIES),
        "contract_pass": payload["contract_pass"],
    }:
        raise AnalyticFrameVerificationError("analytic_frame_summary_invalid")


def validate_analytic_frame_verification_artifact(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    require_current_sources: bool = True,
    rerun: bool = True,
) -> dict[str, Any]:
    """Validate hashes and optionally reproduce the three current-source cases."""

    _validate_schema_and_semantics(payload, repo_root=repo_root)
    if require_current_sources:
        current = _source_checksums(repo_root)
        if payload["source"]["input_checksums"] != current:
            raise AnalyticFrameVerificationError("analytic_frame_sources_stale")
    if rerun:
        expected = build_analytic_frame_verification_artifact(repo_root=repo_root)
        for stored_case, current_case in zip(
            payload["cases"], expected["cases"], strict=True
        ):
            for key in (
                "case_id",
                "category",
                "structural_family",
                "truth_basis",
                "formula_profile",
                "formula",
                "parameters",
                "model_payload_hash",
                "solver_id",
                "analysis_type",
            ):
                if stored_case[key] != current_case[key]:
                    raise AnalyticFrameVerificationError(
                        "analytic_frame_artifact_stale"
                    )
            if current_case["contract_pass"] is not True:
                raise AnalyticFrameVerificationError(
                    "analytic_frame_current_reproduction_failed"
                )
            current_by_quantity = {
                row["quantity"]: row for row in current_case["comparisons"]
            }
            for stored_row in stored_case["comparisons"]:
                current_row = current_by_quantity.get(stored_row["quantity"])
                if current_row is None:
                    raise AnalyticFrameVerificationError(
                        "analytic_frame_artifact_stale"
                    )
                reproduction_error = abs(
                    float(stored_row["actual"]) - float(current_row["actual"])
                )
                reproduction_tolerance = (
                    float(stored_row["absolute_tolerance"])
                    + float(stored_row["relative_tolerance"])
                    * abs(float(current_row["actual"]))
                )
                if reproduction_error > reproduction_tolerance:
                    raise AnalyticFrameVerificationError(
                        "analytic_frame_current_reproduction_mismatch"
                    )
    return payload


__all__ = [
    "ANALYTIC_FRAME_CATEGORIES",
    "ANALYTIC_FRAME_SCHEMA_PATH",
    "ANALYTIC_FRAME_SCHEMA_VERSION",
    "AnalyticFrameVerificationError",
    "build_analytic_frame_verification_artifact",
    "build_cantilever_beam_model",
    "build_portal_frame_model",
    "build_simply_supported_beam_model",
    "validate_analytic_frame_verification_artifact",
]
