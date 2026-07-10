from __future__ import annotations

from structural_analysis import AnalysisResult, validate


def _result(*, tolerance: float, metrics: dict[str, object]) -> AnalysisResult:
    return AnalysisResult(
        status="ready",
        analysis_type="linear_static",
        solver="authoritative_cpu_linear_fea_3d_v1",
        engine_version="test-engine",
        input_checksum="sha256:test",
        tolerance=tolerance,
        convergence_history=[
            {
                "step": "linear_static",
                "iteration": 1,
                "residual_norm": 0.0,
                "status": "ready",
            }
        ],
        metrics=metrics,
    )


def test_numeric_reference_values_pass_within_configured_tolerance() -> None:
    result = _result(
        tolerance=1.0e-6,
        metrics={
            "tip_displacement": 1.0,
            "reactions": {"N1": [10.0, 20.0]},
        },
    )

    report = validate(
        result,
        {
            "tip_displacement": 1.0 + 5.0e-7,
            "reactions": {"N1": [10.0 - 5.0e-7, 20.0 + 5.0e-7]},
        },
    )

    assert report.status == "pass"
    assert report.contract_pass is True
    assert all(row["status"] == "pass" for row in report.comparisons)


def test_numeric_reference_values_block_outside_configured_tolerance() -> None:
    result = _result(tolerance=1.0e-8, metrics={"tip_displacement": 1.0})

    report = validate(result, {"tip_displacement": 1.0 + 1.0e-5})

    assert report.status == "blocked"
    assert report.contract_pass is False
    assert report.developer_preview_blocked_fields == [
        "reference_mismatch:tip_displacement"
    ]
    assert report.comparisons == [
        {
            "field": "tip_displacement",
            "expected": 1.0 + 1.0e-5,
            "actual": 1.0,
            "status": "review",
        }
    ]


def test_boolean_and_structural_shapes_remain_exact() -> None:
    result = _result(
        tolerance=1.0,
        metrics={
            "sparse_backend_used": True,
            "vector": [1.0, 2.0],
        },
    )

    report = validate(
        result,
        {
            "sparse_backend_used": 1,
            "vector": [1.0, 2.0, 3.0],
        },
    )

    assert report.status == "blocked"
    assert {row["field"] for row in report.comparisons if row["status"] == "review"} == {
        "sparse_backend_used",
        "vector",
    }


def test_non_finite_reference_values_never_pass() -> None:
    result = _result(tolerance=1.0, metrics={"value": float("nan")})

    report = validate(result, {"value": float("nan")})

    assert report.status == "blocked"
    assert report.comparisons[0]["status"] == "review"
