"""Exact witnesses distinguish fixed axial load from a proportional load path."""

from decimal import localcontext

import pytest

from structural_analysis.benchmark.rc_experiment_loading import audit_peer_rc_loading


def test_fixed_axial_and_reversing_lateral_require_separate_load_patterns():
    source = b"fixture\n4\n0 -12.17\n1 20\n1 21\n-1 -20\n"
    with localcontext() as context:
        context.prec = 2
        result = audit_peer_rc_loading(
            source, declared_constant_axial_kn="600", constant_axial_source="fixture"
        )
    assert result["status"] == "INCOMPATIBLE_SINGLE_PROPORTIONAL_PATTERN"
    witness = result["nonproportional_witness"]
    assert witness["source_line_numbers"] == [3, 4]
    assert witness["determinant_kn2_exact"] == {
        "numerator": "-19302",
        "denominator": "1",
    }
    assert result["first_observation_mm_kn"] == ["0", "-12.17"]
    assert result["consecutive_equal_displacement_indices_zero_based"] == [2]
    assert result["axial_basis"] == "externally-declared-constant-not-measured-channel"
    assert result["training_admitted"] is False
    assert result["structural_solver_calls"] == 0


def test_missing_axial_is_not_zero_and_zero_axial_is_explicit():
    source = b"fixture\n3\n0 0\n1 2\n-1 -2\n"
    missing = audit_peer_rc_loading(source)
    explicit = audit_peer_rc_loading(
        source, declared_constant_axial_kn="0", constant_axial_source="fixture"
    )
    assert missing["status"] == "AXIAL_UNAVAILABLE"
    assert explicit["status"] == "REPORTED_LOADS_COLLINEAR_THROUGH_ORIGIN"
    assert explicit["training_admitted"] is False
    assert explicit["source_sha256"] == missing["source_sha256"]


def test_measured_axial_is_used_without_constant_substitution():
    source = b"fixture\n4\n0 0 0\n1 2 6\n-1 -2 -6\n0 0 0\n"
    result = audit_peer_rc_loading(source)
    assert result["status"] == "REPORTED_LOADS_COLLINEAR_THROUGH_ORIGIN"
    assert result["axial_basis"] == "measured-third-column"
    with pytest.raises(ValueError, match="cannot be replaced"):
        audit_peer_rc_loading(
            source, declared_constant_axial_kn="6", constant_axial_source="fixture"
        )
    assert (
        audit_peer_rc_loading(b"fixture\n1\n0 0 0\n")["status"]
        == "ALL_ZERO_REPORTED_LOADS"
    )


def test_exact_witness_survives_rounded_binary64_and_low_decimal_precision():
    source = b"fixture\n2\n0 1.00000000000000000001 2\n1 1.00000000000000000002 2\n"
    with localcontext() as context:
        context.prec = 2
        result = audit_peer_rc_loading(source)
    assert result["nonproportional_witness"]["determinant_kn2_exact"] == {
        "numerator": "-1",
        "denominator": "50000000000000000000",
    }


@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e999999", "x", "", True])
def test_invalid_or_unbounded_constant_rejected(token):
    with pytest.raises(ValueError):
        audit_peer_rc_loading(
            b"fixture\n1\n0 1\n",
            declared_constant_axial_kn=token,
            constant_axial_source="fixture",
        )


def test_missing_source_and_invalid_late_row_reject():
    with pytest.raises(ValueError, match="source required"):
        audit_peer_rc_loading(b"fixture\n1\n0 1\n", declared_constant_axial_kn="1")
    with pytest.raises(ValueError, match="requires a declared"):
        audit_peer_rc_loading(b"fixture\n1\n0 1\n", constant_axial_source="fixture")
    # Continue validating the full input after finding a nonproportional witness.
    with pytest.raises(ValueError, match="bounds"):
        audit_peer_rc_loading(b"fixture\n3\n0 1 2\n1 2 2\n2 1e999999 2\n")
