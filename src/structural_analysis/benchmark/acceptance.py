"""Scientific acceptance primitives for structural benchmark evidence.

The helpers in this module evaluate numerical observations only.  They do not
create ResultIR authority, approve engineering reviews, or promote a release
gate.  Every public result keeps numerical PASS separate from benchmark credit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import math
import re
from typing import Any


BENCHMARK_ACCEPTANCE_SCHEMA_VERSION = "benchmark-scientific-acceptance.v1"
BENCHMARK_DECISION_SCHEMA_VERSION = "benchmark-scientific-decision.v1"
BENCHMARK_DECISIONS = frozenset({"PASS", "REVIEW", "FAIL"})
_REVIEW_EVIDENCE_REF = re.compile(r"^(?:https|operator-review|ticket|jira)://\S+$")


class BenchmarkAcceptanceError(ValueError):
    """Stable validation failure for benchmark comparison inputs."""

    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(f"{code}@{path}: {message}")
        self.code = code
        self.path = path


def _fail(code: str, path: str, message: str) -> None:
    raise BenchmarkAcceptanceError(code, path, message)


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("benchmark_number_required", path, "A finite numeric value is required.")
    result = float(value)
    if not math.isfinite(result):
        _fail("benchmark_number_non_finite", path, "NaN and infinity are forbidden.")
    return result


def _finite_vector(
    value: Any, path: str, *, allow_empty: bool = False
) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("benchmark_vector_required", path, "A numeric sequence is required.")
    result = tuple(
        _finite_number(item, f"{path}/{index}") for index, item in enumerate(value)
    )
    if not result and not allow_empty:
        _fail("benchmark_vector_empty", path, "The vector must not be empty.")
    return result


def _same_length(reference: Sequence[Any], actual: Sequence[Any], path: str) -> None:
    if len(reference) != len(actual):
        _fail(
            "benchmark_vector_length_mismatch",
            path,
            "Reference and actual vectors must have identical lengths.",
        )


def _l2(values: Sequence[float]) -> float:
    return math.sqrt(math.fsum(value * value for value in values))


def _tolerance(value: Any, path: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        _fail("benchmark_tolerance_required", path, "A tolerance object is required.")
    absolute = _finite_number(value.get("absolute"), f"{path}/absolute")
    relative = _finite_number(value.get("relative"), f"{path}/relative")
    near_zero = _finite_number(
        value.get("near_zero_reference"),
        f"{path}/near_zero_reference",
    )
    if absolute < 0.0 or relative < 0.0 or near_zero < 0.0:
        _fail(
            "benchmark_tolerance_negative",
            path,
            "Tolerance values must be non-negative.",
        )
    if absolute == 0.0 and relative == 0.0:
        _fail(
            "benchmark_tolerance_zero",
            path,
            "At least one absolute or relative tolerance must be positive.",
        )
    return {
        "absolute": absolute,
        "relative": relative,
        "near_zero_reference": near_zero,
    }


def _scalar_row(
    reference: float, actual: float, tolerance: Mapping[str, float]
) -> dict[str, Any]:
    absolute_error = abs(actual - reference)
    near_zero = abs(reference) <= tolerance["near_zero_reference"]
    allowed_error = (
        tolerance["absolute"]
        if near_zero
        else max(
            tolerance["absolute"],
            tolerance["relative"] * abs(reference),
        )
    )
    relative_error = (
        absolute_error / abs(reference)
        if abs(reference) > tolerance["near_zero_reference"]
        else None
    )
    return {
        "reference": reference,
        "actual": actual,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "allowed_error": allowed_error,
        "tolerance_mode": "absolute_near_zero"
        if near_zero
        else "absolute_and_relative",
        "contract_pass": absolute_error <= allowed_error,
    }


def _vector_comparison(
    reference: Any,
    actual: Any,
    *,
    component_tolerance: Any,
    norm_tolerance: Any,
    path: str,
) -> dict[str, Any]:
    reference_vector = _finite_vector(reference, f"{path}/reference")
    actual_vector = _finite_vector(actual, f"{path}/actual")
    _same_length(reference_vector, actual_vector, path)
    component_policy = _tolerance(component_tolerance, f"{path}/component_tolerance")
    norm_policy = _tolerance(norm_tolerance, f"{path}/norm_tolerance")
    component_rows = [
        {"index": index, **_scalar_row(reference_value, actual_value, component_policy)}
        for index, (reference_value, actual_value) in enumerate(
            zip(reference_vector, actual_vector, strict=True)
        )
    ]
    difference = tuple(
        actual_value - reference_value
        for reference_value, actual_value in zip(
            reference_vector, actual_vector, strict=True
        )
    )
    reference_norm = _l2(reference_vector)
    actual_norm = _l2(actual_vector)
    difference_norm = _l2(difference)
    norm_row = _scalar_row(reference_norm, actual_norm, norm_policy)
    norm_row["difference_norm"] = difference_norm
    norm_row["contract_pass"] = difference_norm <= norm_row["allowed_error"]
    return {
        "component_rows": component_rows,
        "component_contract_pass": all(row["contract_pass"] for row in component_rows),
        "norm": norm_row,
        "norm_contract_pass": norm_row["contract_pass"],
    }


def compare_displacements(
    reference: Any,
    actual: Any,
    *,
    component_tolerance: Any,
    norm_tolerance: Any,
) -> dict[str, Any]:
    """Compare displacement DOFs componentwise and by global L2 norm."""

    comparison = _vector_comparison(
        reference,
        actual,
        component_tolerance=component_tolerance,
        norm_tolerance=norm_tolerance,
        path="/displacement",
    )
    contract_pass = bool(
        comparison["component_contract_pass"] and comparison["norm_contract_pass"]
    )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "displacement",
        **comparison,
        "contract_pass": contract_pass,
    }


def compare_reactions(
    reference: Any,
    actual: Any,
    external_resultant: Any,
    *,
    component_tolerance: Any,
    norm_tolerance: Any,
    equilibrium_absolute_tolerance: float,
) -> dict[str, Any]:
    """Compare reactions and independently enforce force/moment equilibrium."""

    comparison = _vector_comparison(
        reference,
        actual,
        component_tolerance=component_tolerance,
        norm_tolerance=norm_tolerance,
        path="/reaction",
    )
    actual_vector = _finite_vector(actual, "/reaction/actual")
    external_vector = _finite_vector(external_resultant, "/reaction/external_resultant")
    _same_length(actual_vector, external_vector, "/reaction/equilibrium")
    equilibrium_tolerance = _finite_number(
        equilibrium_absolute_tolerance,
        "/reaction/equilibrium_absolute_tolerance",
    )
    if equilibrium_tolerance < 0.0:
        _fail(
            "benchmark_tolerance_negative",
            "/reaction/equilibrium_absolute_tolerance",
            "Equilibrium tolerance must be non-negative.",
        )
    imbalance = tuple(
        reaction + load
        for reaction, load in zip(actual_vector, external_vector, strict=True)
    )
    equilibrium_norm = _l2(imbalance)
    equilibrium_pass = equilibrium_norm <= equilibrium_tolerance
    contract_pass = bool(
        comparison["component_contract_pass"]
        and comparison["norm_contract_pass"]
        and equilibrium_pass
    )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "reaction_equilibrium",
        **comparison,
        "equilibrium": {
            "imbalance": list(imbalance),
            "imbalance_norm": equilibrium_norm,
            "absolute_tolerance": equilibrium_tolerance,
            "contract_pass": equilibrium_pass,
        },
        "contract_pass": contract_pass,
    }


def compare_member_forces_local(
    reference: Any,
    actual: Any,
    *,
    component_tolerances: Any,
    norm_tolerance: Any,
) -> dict[str, Any]:
    """Compare member-force arrays in named local-axis components."""

    if not isinstance(reference, Mapping) or not isinstance(actual, Mapping):
        _fail(
            "benchmark_member_force_mapping_required",
            "/member_force_local",
            "Reference and actual local-force mappings are required.",
        )
    if not isinstance(component_tolerances, Mapping):
        _fail(
            "benchmark_tolerance_required",
            "/member_force_local/component_tolerances",
            "Per-component tolerance mappings are required.",
        )
    reference_values = {str(key): value for key, value in reference.items()}
    actual_values = {str(key): value for key, value in actual.items()}
    if len(reference_values) != len(reference) or len(actual_values) != len(actual):
        _fail(
            "benchmark_member_force_component_ambiguous",
            "/member_force_local",
            "Local component names must remain unique after text normalization.",
        )
    reference_components = set(reference_values)
    actual_components = set(actual_values)
    if reference_components != actual_components:
        _fail(
            "benchmark_member_force_component_mismatch",
            "/member_force_local",
            "Reference and actual local component names must match exactly.",
        )
    component_rows: list[dict[str, Any]] = []
    for component in sorted(reference_components):
        if component not in component_tolerances:
            _fail(
                "benchmark_member_force_tolerance_missing",
                f"/member_force_local/component_tolerances/{component}",
                "Every local force component requires its own tolerance.",
            )
        comparison = _vector_comparison(
            reference_values[component],
            actual_values[component],
            component_tolerance=component_tolerances[component],
            norm_tolerance=norm_tolerance,
            path=f"/member_force_local/{component}",
        )
        component_rows.append(
            {
                "local_component": component,
                **comparison,
                "contract_pass": bool(
                    comparison["component_contract_pass"]
                    and comparison["norm_contract_pass"]
                ),
            }
        )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "member_force_local",
        "local_component_rows": component_rows,
        "contract_pass": bool(component_rows)
        and all(row["contract_pass"] for row in component_rows),
    }


def _matrix(value: Any, path: str, size: int) -> tuple[tuple[float, ...], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("benchmark_matrix_required", path, "A square numeric matrix is required.")
    rows = tuple(
        _finite_vector(row, f"{path}/{index}") for index, row in enumerate(value)
    )
    if len(rows) != size or any(len(row) != size for row in rows):
        _fail(
            "benchmark_matrix_shape_mismatch",
            path,
            f"The stiffness matrix must have shape [{size}, {size}].",
        )
    for row_index in range(size):
        for column_index in range(row_index + 1, size):
            left = rows[row_index][column_index]
            right = rows[column_index][row_index]
            scale = max(1.0, abs(left), abs(right))
            if abs(left - right) > 1.0e-12 * scale:
                _fail(
                    "benchmark_stiffness_not_symmetric",
                    f"{path}/{row_index}/{column_index}",
                    "The global energy norm requires a symmetric stiffness matrix.",
                )
    return rows


def _quadratic(vector: Sequence[float], matrix: Sequence[Sequence[float]]) -> float:
    return math.fsum(
        vector[row] * matrix[row][column] * vector[column]
        for row in range(len(vector))
        for column in range(len(vector))
    )


def compare_global_energy_norm(
    reference_displacement: Any,
    actual_displacement: Any,
    stiffness_matrix: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    """Evaluate ``sqrt((u-u_ref)^T K (u-u_ref))`` against a global policy."""

    reference = _finite_vector(reference_displacement, "/global_energy/reference")
    actual = _finite_vector(actual_displacement, "/global_energy/actual")
    _same_length(reference, actual, "/global_energy")
    stiffness = _matrix(
        stiffness_matrix, "/global_energy/stiffness_matrix", len(reference)
    )
    absolute = _finite_number(absolute_tolerance, "/global_energy/absolute_tolerance")
    relative = _finite_number(relative_tolerance, "/global_energy/relative_tolerance")
    if absolute < 0.0 or relative < 0.0 or (absolute == 0.0 and relative == 0.0):
        _fail(
            "benchmark_tolerance_invalid",
            "/global_energy",
            "Energy tolerances must be non-negative and not both zero.",
        )
    difference = tuple(
        actual_value - reference_value
        for reference_value, actual_value in zip(reference, actual, strict=True)
    )
    reference_quadratic = _quadratic(reference, stiffness)
    error_quadratic = _quadratic(difference, stiffness)
    scale = max(1.0, abs(reference_quadratic), abs(error_quadratic))
    if reference_quadratic < -1.0e-12 * scale or error_quadratic < -1.0e-12 * scale:
        _fail(
            "benchmark_energy_norm_negative",
            "/global_energy/stiffness_matrix",
            "The supplied stiffness matrix produced a negative energy quadratic.",
        )
    reference_norm = math.sqrt(max(reference_quadratic, 0.0))
    error_norm = math.sqrt(max(error_quadratic, 0.0))
    allowed_error = max(absolute, relative * reference_norm)
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "global_energy_norm",
        "reference_energy_norm": reference_norm,
        "error_energy_norm": error_norm,
        "relative_energy_error": error_norm / reference_norm
        if reference_norm > 0.0
        else None,
        "allowed_error_energy_norm": allowed_error,
        "contract_pass": error_norm <= allowed_error,
    }


def _modal_rows(
    reference_values: Any,
    actual_values: Any,
    reference_modes: Any,
    actual_modes: Any,
    *,
    value_tolerance: Any,
    minimum_mac: float,
    path: str,
) -> list[dict[str, Any]]:
    references = _finite_vector(reference_values, f"{path}/reference_values")
    actuals = _finite_vector(actual_values, f"{path}/actual_values")
    _same_length(references, actuals, path)
    if (
        isinstance(reference_modes, (str, bytes))
        or isinstance(actual_modes, (str, bytes))
        or not isinstance(reference_modes, Sequence)
        or not isinstance(actual_modes, Sequence)
    ):
        _fail(
            "benchmark_mode_shape_matrix_required",
            path,
            "Mode-shape arrays are required.",
        )
    if len(reference_modes) != len(references) or len(actual_modes) != len(references):
        _fail(
            "benchmark_mode_count_mismatch",
            path,
            "Eigenvalue/frequency and mode-shape counts must match.",
        )
    tolerance = _tolerance(value_tolerance, f"{path}/value_tolerance")
    mac_threshold = _finite_number(minimum_mac, f"{path}/minimum_mac")
    if mac_threshold < 0.0 or mac_threshold > 1.0:
        _fail(
            "benchmark_mac_threshold_invalid",
            f"{path}/minimum_mac",
            "Minimum MAC must be between zero and one.",
        )
    rows: list[dict[str, Any]] = []
    for index, (reference_value, actual_value) in enumerate(
        zip(references, actuals, strict=True)
    ):
        reference_mode = _finite_vector(
            reference_modes[index], f"{path}/reference_modes/{index}"
        )
        actual_mode = _finite_vector(
            actual_modes[index], f"{path}/actual_modes/{index}"
        )
        _same_length(reference_mode, actual_mode, f"{path}/modes/{index}")
        dot = math.fsum(
            left * right
            for left, right in zip(reference_mode, actual_mode, strict=True)
        )
        reference_norm_sq = math.fsum(value * value for value in reference_mode)
        actual_norm_sq = math.fsum(value * value for value in actual_mode)
        if reference_norm_sq <= 0.0 or actual_norm_sq <= 0.0:
            _fail(
                "benchmark_mode_shape_zero",
                f"{path}/modes/{index}",
                "MAC is undefined for a zero mode shape.",
            )
        mac = (dot * dot) / (reference_norm_sq * actual_norm_sq)
        value_row = _scalar_row(reference_value, actual_value, tolerance)
        rows.append(
            {
                "mode_index": index,
                "value": value_row,
                "mac": mac,
                "minimum_mac": mac_threshold,
                "mac_contract_pass": mac >= mac_threshold,
                "contract_pass": value_row["contract_pass"] and mac >= mac_threshold,
            }
        )
    return rows


def compare_modal(
    reference_frequencies: Any,
    actual_frequencies: Any,
    reference_modes: Any,
    actual_modes: Any,
    *,
    frequency_tolerance: Any,
    minimum_mac: float,
) -> dict[str, Any]:
    """Compare modal frequencies and sign-invariant modal assurance criterion."""

    rows = _modal_rows(
        reference_frequencies,
        actual_frequencies,
        reference_modes,
        actual_modes,
        value_tolerance=frequency_tolerance,
        minimum_mac=minimum_mac,
        path="/modal",
    )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "modal_frequency_and_mac",
        "mode_rows": rows,
        "contract_pass": bool(rows) and all(row["contract_pass"] for row in rows),
    }


def compare_buckling(
    reference_eigenvalues: Any,
    actual_eigenvalues: Any,
    reference_modes: Any,
    actual_modes: Any,
    *,
    eigenvalue_tolerance: Any,
    minimum_mac: float,
) -> dict[str, Any]:
    """Compare buckling eigenvalues and sign-invariant mode correlation."""

    rows = _modal_rows(
        reference_eigenvalues,
        actual_eigenvalues,
        reference_modes,
        actual_modes,
        value_tolerance=eigenvalue_tolerance,
        minimum_mac=minimum_mac,
        path="/buckling",
    )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "buckling_eigenvalue_and_mode",
        "mode_rows": rows,
        "contract_pass": bool(rows) and all(row["contract_pass"] for row in rows),
    }


def compare_nonlinear_path(
    reference_points: Any,
    actual_points: Any,
    *,
    load_scale: float,
    response_scale: float,
    maximum_path_distance: float,
    rms_path_distance: float,
) -> dict[str, Any]:
    """Compare aligned load-response points in a dimensionless path metric."""

    if not isinstance(reference_points, Sequence) or not isinstance(
        actual_points, Sequence
    ):
        _fail(
            "benchmark_nonlinear_path_required",
            "/nonlinear_path",
            "Reference and actual point arrays are required.",
        )
    _same_length(reference_points, actual_points, "/nonlinear_path")
    if not reference_points:
        _fail(
            "benchmark_nonlinear_path_empty",
            "/nonlinear_path",
            "Path points are required.",
        )
    load_normalizer = _finite_number(load_scale, "/nonlinear_path/load_scale")
    response_normalizer = _finite_number(
        response_scale, "/nonlinear_path/response_scale"
    )
    maximum_limit = _finite_number(
        maximum_path_distance,
        "/nonlinear_path/maximum_path_distance",
    )
    rms_limit = _finite_number(rms_path_distance, "/nonlinear_path/rms_path_distance")
    if (
        min(load_normalizer, response_normalizer) <= 0.0
        or min(maximum_limit, rms_limit) < 0.0
    ):
        _fail(
            "benchmark_nonlinear_path_policy_invalid",
            "/nonlinear_path",
            "Path scales must be positive and distance limits non-negative.",
        )
    point_rows: list[dict[str, Any]] = []
    distances: list[float] = []
    for index, (reference_point, actual_point) in enumerate(
        zip(reference_points, actual_points, strict=True)
    ):
        reference = _finite_vector(
            reference_point, f"/nonlinear_path/reference/{index}"
        )
        actual = _finite_vector(actual_point, f"/nonlinear_path/actual/{index}")
        if len(reference) != 2 or len(actual) != 2:
            _fail(
                "benchmark_nonlinear_point_shape_invalid",
                f"/nonlinear_path/{index}",
                "Each nonlinear point must be [load, response].",
            )
        distance = math.hypot(
            (actual[0] - reference[0]) / load_normalizer,
            (actual[1] - reference[1]) / response_normalizer,
        )
        distances.append(distance)
        point_rows.append(
            {
                "index": index,
                "reference": list(reference),
                "actual": list(actual),
                "dimensionless_distance": distance,
            }
        )
    maximum = max(distances)
    rms = math.sqrt(math.fsum(value * value for value in distances) / len(distances))
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "nonlinear_load_response_path",
        "point_rows": point_rows,
        "maximum_path_distance": maximum,
        "maximum_path_distance_limit": maximum_limit,
        "rms_path_distance": rms,
        "rms_path_distance_limit": rms_limit,
        "contract_pass": maximum <= maximum_limit and rms <= rms_limit,
    }


def compare_residual_observation(
    *,
    raw_translation_norm: float,
    raw_rotation_norm: float,
    scaled_norm: float,
    maximum_raw_translation_norm: float,
    maximum_raw_rotation_norm: float,
    maximum_scaled_norm: float,
) -> dict[str, Any]:
    """Check dimensioned translation/rotation residuals and the scaled norm."""

    values = {
        "raw_translation_norm": raw_translation_norm,
        "raw_rotation_norm": raw_rotation_norm,
        "scaled_norm": scaled_norm,
    }
    limits = {
        "raw_translation_norm": maximum_raw_translation_norm,
        "raw_rotation_norm": maximum_raw_rotation_norm,
        "scaled_norm": maximum_scaled_norm,
    }
    rows = []
    for name in values:
        actual = _finite_number(values[name], f"/residual/{name}")
        maximum = _finite_number(limits[name], f"/residual/maximum_{name}")
        if actual < 0.0 or maximum < 0.0:
            _fail(
                "benchmark_residual_norm_negative",
                f"/residual/{name}",
                "Residual norms and thresholds must be non-negative.",
            )
        rows.append(
            {
                "norm": name,
                "actual": actual,
                "maximum": maximum,
                "contract_pass": actual <= maximum,
            }
        )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": "residual_observation",
        "norm_rows": rows,
        "contract_pass": all(row["contract_pass"] for row in rows),
    }


def _parse_timestamp(value: Any, path: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        _fail(
            "benchmark_review_timestamp_missing",
            path,
            "A review timestamp is required.",
        )
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("benchmark_review_timestamp_invalid", path, "Timestamp must be ISO 8601.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(
            "benchmark_review_timestamp_timezone_missing",
            path,
            "Review timestamps must be timezone-aware.",
        )
    return parsed.astimezone(timezone.utc)


def _review_status(review: Any, evaluated_at: datetime) -> dict[str, Any]:
    blockers: list[str] = []
    payload = review if isinstance(review, Mapping) else {}
    engineer_id = str(payload.get("engineer_id") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    evidence_ref = str(payload.get("evidence_ref") or "").strip()
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str):
        scope = [raw_scope.strip()] if raw_scope.strip() else []
    elif isinstance(raw_scope, Sequence):
        scope = [str(item).strip() for item in raw_scope if str(item).strip()]
    else:
        scope = []
    scope = list(dict.fromkeys(scope))
    if not engineer_id or engineer_id.upper() in {"TBD", "UNKNOWN"}:
        blockers.append("benchmark_review_engineer_id_missing")
    if not reason:
        blockers.append("benchmark_review_reason_missing")
    if not scope:
        blockers.append("benchmark_review_scope_missing")
    if not _REVIEW_EVIDENCE_REF.match(evidence_ref):
        blockers.append("benchmark_review_evidence_ref_invalid")
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    try:
        approved_at = _parse_timestamp(
            payload.get("approved_at"), "/review/approved_at"
        )
    except BenchmarkAcceptanceError as error:
        blockers.append(error.code)
    try:
        expires_at = _parse_timestamp(payload.get("expires_at"), "/review/expires_at")
    except BenchmarkAcceptanceError as error:
        blockers.append(error.code)
    if approved_at is not None and approved_at > evaluated_at:
        blockers.append("benchmark_review_approval_in_future")
    if expires_at is not None and expires_at <= evaluated_at:
        blockers.append("benchmark_review_expired")
    if approved_at is not None and expires_at is not None and approved_at > expires_at:
        blockers.append("benchmark_review_expiry_before_approval")
    return {
        "engineer_id": engineer_id,
        "reason": reason,
        "scope": scope,
        "evidence_ref": evidence_ref,
        "approved_at": approved_at.isoformat() if approved_at else "",
        "expires_at": expires_at.isoformat() if expires_at else "",
        "contract_pass": not blockers,
        "blockers": sorted(set(blockers)),
    }


def decide_benchmark(
    metric_results: Sequence[Mapping[str, Any]],
    *,
    decision: str,
    review: Mapping[str, Any] | None = None,
    hard_blockers: Sequence[str] = (),
    evaluated_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Resolve PASS/REVIEW/FAIL without allowing REVIEW to hide hard blockers."""

    normalized_decision = str(decision or "").strip().upper()
    if normalized_decision not in BENCHMARK_DECISIONS:
        _fail(
            "benchmark_decision_invalid",
            "/decision",
            "Decision must be PASS, REVIEW, or FAIL.",
        )
    if not metric_results:
        _fail(
            "benchmark_metric_results_empty",
            "/metric_results",
            "At least one metric-family result is required.",
        )
    rows = [dict(row) for row in metric_results]
    metric_families: list[str] = []
    for index, row in enumerate(rows):
        family = str(row.get("metric_family") or "").strip()
        if not family:
            _fail(
                "benchmark_metric_family_missing",
                f"/metric_results/{index}/metric_family",
                "Every metric result requires a stable metric-family identifier.",
            )
        if family in metric_families:
            _fail(
                "benchmark_metric_family_duplicate",
                f"/metric_results/{index}/metric_family",
                "A decision may contain only one result per metric family.",
            )
        metric_families.append(family)
    numerical_pass = all(row.get("contract_pass") is True for row in rows)
    blockers = sorted(
        {str(item).strip() for item in hard_blockers if str(item).strip()}
    )
    if isinstance(evaluated_at, datetime):
        evaluated = evaluated_at
        if evaluated.tzinfo is None or evaluated.utcoffset() is None:
            _fail(
                "benchmark_evaluated_at_timezone_missing",
                "/evaluated_at",
                "Evaluation time must be timezone-aware.",
            )
        evaluated = evaluated.astimezone(timezone.utc)
    elif evaluated_at is None:
        evaluated = datetime.now(timezone.utc)
    else:
        evaluated = _parse_timestamp(evaluated_at, "/evaluated_at")

    review_status: dict[str, Any] | None = None
    decision_blockers: list[str] = []
    benchmark_credit = False
    if normalized_decision == "PASS":
        decision_blockers.extend(blockers)
        if not numerical_pass:
            decision_blockers.append("benchmark_pass_requested_with_metric_failures")
        benchmark_credit = numerical_pass and not blockers
    elif normalized_decision == "REVIEW":
        decision_blockers.extend(blockers)
        review_status = _review_status(review, evaluated)
        decision_blockers.extend(review_status["blockers"])
        failed_families = {
            str(row.get("metric_family") or "").strip()
            for row in rows
            if row.get("contract_pass") is not True
        }
        if not failed_families.issubset(set(review_status["scope"])):
            decision_blockers.append("benchmark_review_scope_incomplete")
        benchmark_credit = review_status["contract_pass"] and not blockers
    else:
        benchmark_credit = False

    decision_contract_pass = not decision_blockers
    return {
        "schema_version": BENCHMARK_DECISION_SCHEMA_VERSION,
        "decision": normalized_decision,
        "evaluated_at": evaluated.isoformat(),
        "metric_family_count": len(rows),
        "metric_families": metric_families,
        "passing_metric_family_count": sum(
            1 for row in rows if row.get("contract_pass") is True
        ),
        "failing_metric_families": [
            str(row["metric_family"])
            for row in rows
            if row.get("contract_pass") is not True
        ],
        "numerical_pass": numerical_pass,
        "review": review_status,
        "hard_blockers": blockers,
        "decision_blockers": sorted(set(decision_blockers)),
        "decision_contract_pass": decision_contract_pass,
        "benchmark_credit": bool(benchmark_credit and decision_contract_pass),
        "claim_boundary": (
            "Benchmark credit records numerical PASS or a scoped, unexpired engineer "
            "REVIEW only. It does not grant release, design, or ResultIR authority. "
            "Crash, OOM, artifact-integrity, source, and license blockers are not reviewable."
        ),
    }


def inspect_benchmark_decision_receipt(
    value: Any,
    *,
    required_metric_families: Sequence[str] = (),
    require_benchmark_credit: bool = True,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Validate a serialized scientific decision without raising on bad evidence."""

    payload = value if isinstance(value, Mapping) else {}
    blockers: list[str] = []
    if isinstance(as_of, datetime):
        inspection_time = as_of
        if inspection_time.tzinfo is None or inspection_time.utcoffset() is None:
            _fail(
                "benchmark_inspection_time_timezone_missing",
                "/as_of",
                "Inspection time must be timezone-aware.",
            )
        inspection_time = inspection_time.astimezone(timezone.utc)
    elif as_of is None:
        inspection_time = datetime.now(timezone.utc)
    else:
        inspection_time = _parse_timestamp(as_of, "/as_of")
    decision = str(payload.get("decision") or "").strip().upper()
    metric_families = (
        [
            str(item).strip()
            for item in payload.get("metric_families", [])
            if isinstance(item, str) and item.strip()
        ]
        if isinstance(payload.get("metric_families"), Sequence)
        and not isinstance(payload.get("metric_families"), (str, bytes))
        else []
    )
    failing_metric_families = (
        [
            str(item).strip()
            for item in payload.get("failing_metric_families", [])
            if isinstance(item, str) and item.strip()
        ]
        if isinstance(payload.get("failing_metric_families"), Sequence)
        and not isinstance(payload.get("failing_metric_families"), (str, bytes))
        else []
    )
    if payload.get("schema_version") != BENCHMARK_DECISION_SCHEMA_VERSION:
        blockers.append("benchmark_decision_receipt_schema_invalid")
    if decision not in BENCHMARK_DECISIONS:
        blockers.append("benchmark_decision_receipt_decision_invalid")
    if not metric_families:
        blockers.append("benchmark_decision_receipt_metric_families_missing")
    if len(metric_families) != len(set(metric_families)):
        blockers.append("benchmark_decision_receipt_metric_families_duplicate")
    if payload.get("metric_family_count") != len(metric_families):
        blockers.append("benchmark_decision_receipt_metric_family_count_mismatch")
    if len(failing_metric_families) != len(set(failing_metric_families)):
        blockers.append("benchmark_decision_receipt_failing_families_duplicate")
    if not set(failing_metric_families).issubset(set(metric_families)):
        blockers.append("benchmark_decision_receipt_failing_families_unknown")
    required = {
        str(item).strip() for item in required_metric_families if str(item).strip()
    }
    blockers.extend(
        f"benchmark_decision_receipt_metric_family_missing:{family}"
        for family in sorted(required - set(metric_families))
    )
    passing_count = payload.get("passing_metric_family_count")
    if (
        isinstance(passing_count, bool)
        or not isinstance(passing_count, int)
        or passing_count < 0
        or passing_count > len(metric_families)
    ):
        blockers.append("benchmark_decision_receipt_passing_count_invalid")
    else:
        expected_failing_count = len(metric_families) - passing_count
        if len(failing_metric_families) != expected_failing_count:
            blockers.append("benchmark_decision_receipt_failing_count_mismatch")
        if payload.get("numerical_pass") is not (passing_count == len(metric_families)):
            blockers.append("benchmark_decision_receipt_numerical_pass_mismatch")

    evaluated: datetime | None = None
    try:
        evaluated = _parse_timestamp(payload.get("evaluated_at"), "/evaluated_at")
    except BenchmarkAcceptanceError as error:
        blockers.append(error.code)
    hard_blockers = (
        [
            str(item).strip()
            for item in payload.get("hard_blockers", [])
            if str(item).strip()
        ]
        if isinstance(payload.get("hard_blockers"), Sequence)
        and not isinstance(payload.get("hard_blockers"), (str, bytes))
        else ["invalid_hard_blocker_shape"]
    )
    decision_blockers = (
        [
            str(item).strip()
            for item in payload.get("decision_blockers", [])
            if str(item).strip()
        ]
        if isinstance(payload.get("decision_blockers"), Sequence)
        and not isinstance(payload.get("decision_blockers"), (str, bytes))
        else ["invalid_decision_blocker_shape"]
    )
    if hard_blockers:
        blockers.append("benchmark_decision_receipt_hard_blockers_present")
    if decision_blockers:
        blockers.append("benchmark_decision_receipt_decision_blockers_present")
    if payload.get("decision_contract_pass") is not True:
        blockers.append("benchmark_decision_receipt_contract_not_passed")

    review_payload = payload.get("review")
    review_status: dict[str, Any] | None = None
    if decision == "PASS":
        if payload.get("numerical_pass") is not True:
            blockers.append("benchmark_decision_receipt_pass_without_numerical_pass")
        if review_payload is not None:
            blockers.append("benchmark_decision_receipt_pass_review_not_null")
    elif decision == "REVIEW":
        if evaluated is None:
            blockers.append("benchmark_decision_receipt_review_time_unusable")
        else:
            review_status = _review_status(review_payload, evaluated)
            blockers.extend(review_status["blockers"])
            if review_status["expires_at"]:
                expires_at = _parse_timestamp(
                    review_status["expires_at"],
                    "/review/expires_at",
                )
                if expires_at <= inspection_time:
                    blockers.append("benchmark_review_expired_at_inspection")
            if not set(failing_metric_families).issubset(set(review_status["scope"])):
                blockers.append("benchmark_review_scope_incomplete")
        if not failing_metric_families:
            blockers.append("benchmark_decision_receipt_review_without_failures")
    elif decision == "FAIL" and payload.get("benchmark_credit") is True:
        blockers.append("benchmark_decision_receipt_fail_has_credit")

    benchmark_credit = payload.get("benchmark_credit") is True
    if require_benchmark_credit and not benchmark_credit:
        blockers.append("benchmark_decision_receipt_credit_missing")
    blockers = sorted(set(blockers))
    return {
        "schema_version": _text_value(payload.get("schema_version")),
        "decision": decision,
        "metric_families": metric_families,
        "failing_metric_families": failing_metric_families,
        "review": review_status,
        "benchmark_credit": benchmark_credit,
        "contract_pass": not blockers,
        "blockers": blockers,
    }


def _text_value(value: Any) -> str:
    return str(value or "").strip()
