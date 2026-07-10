"""Tolerance-aware validation for public structural-analysis results."""

from __future__ import annotations

import json
from math import isclose, isfinite
from numbers import Real
from pathlib import Path
from typing import Any

from structural_analysis.results.schema import AnalysisResult, ValidationReport


def validate(
    result: AnalysisResult,
    reference: dict[str, Any] | str | Path | None = None,
) -> ValidationReport:
    """Validate a result without requiring bitwise-identical floating-point output."""

    reference_payload = _load_reference(reference)
    passed_fields = [
        "engine_version",
        "input_checksum",
        "tolerance",
        "convergence_history",
        "claim_boundary_version",
    ]
    unsupported_fields = [
        item.get("kind", "unsupported_feature") for item in result.unsupported_features
    ]
    warnings = list(result.warnings)
    comparisons: list[dict[str, Any]] = []
    comparison_tolerance = (
        float(result.tolerance)
        if isinstance(result.tolerance, Real)
        and not isinstance(result.tolerance, bool)
        and isfinite(float(result.tolerance))
        and float(result.tolerance) >= 0.0
        else 0.0
    )

    if reference_payload:
        for field_name, expected in reference_payload.items():
            actual = result.metrics.get(field_name)
            comparison_status = (
                "pass"
                if _values_match(
                    actual,
                    expected,
                    relative_tolerance=comparison_tolerance,
                    absolute_tolerance=comparison_tolerance,
                )
                else "review"
            )
            comparisons.append(
                {
                    "field": field_name,
                    "expected": expected,
                    "actual": actual,
                    "status": comparison_status,
                }
            )
    elif result.analysis_type != "model_health":
        warnings.append("No reference payload supplied for non-model-health analysis.")

    reference_mismatches = [
        str(row["field"]) for row in comparisons if row.get("status") != "pass"
    ]
    contract_pass = (
        result.status == "ready"
        and not unsupported_fields
        and not reference_mismatches
    )
    report_status = "pass" if contract_pass else "blocked"
    blocked_fields = unsupported_fields.copy()
    blocked_fields.extend(
        f"reference_mismatch:{field_name}" for field_name in reference_mismatches
    )
    if result.status != "ready" and not blocked_fields:
        blocked_fields.append(result.analysis_type)

    return ValidationReport(
        status=report_status,
        contract_pass=contract_pass,
        engine_version=result.engine_version,
        input_checksum=result.input_checksum,
        tolerance=result.tolerance,
        convergence_history=result.convergence_history,
        passed_fields=passed_fields if contract_pass else [],
        unsupported_fields=unsupported_fields,
        developer_preview_blocked_fields=blocked_fields,
        comparisons=comparisons,
        warnings=warnings,
        developer_preview=result.developer_preview,
        claim_boundary_version=result.claim_boundary_version,
    )


def _values_match(
    actual: Any,
    expected: Any,
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, Real) and isinstance(expected, Real):
        actual_value = float(actual)
        expected_value = float(expected)
        if not isfinite(actual_value) or not isfinite(expected_value):
            return False
        return isclose(
            actual_value,
            expected_value,
            rel_tol=relative_tolerance,
            abs_tol=absolute_tolerance,
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            return False
        return all(
            _values_match(
                actual[key],
                expected[key],
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )
            for key in expected
        )
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        if len(actual) != len(expected):
            return False
        return all(
            _values_match(
                actual_value,
                expected_value,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )
            for actual_value, expected_value in zip(actual, expected, strict=True)
        )
    return actual == expected


def _load_reference(reference: dict[str, Any] | str | Path | None) -> dict[str, Any]:
    if reference is None:
        return {}
    if isinstance(reference, dict):
        return reference
    with Path(reference).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Reference payload must be a JSON object.")
    return payload
