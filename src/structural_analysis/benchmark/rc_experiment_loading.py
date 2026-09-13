"""Exact source-level load-pattern diagnostics, without model or training admission."""

from decimal import Decimal
from fractions import Fraction

from structural_analysis.io.peer_structural_performance import (
    PeerForceDisplacementHistory,
    decode_force_displacement_history,
)


def _bounded_decimal(value):
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("finite original Decimal required")
    parts = value.as_tuple()
    if (
        len(parts.digits) > 128
        or not isinstance(parts.exponent, int)
        or not -308 <= parts.exponent <= 308
    ):
        raise ValueError("source number exceeds exact diagnostic bounds")
    return Fraction(value)


def audit_peer_rc_loading(
    original_history: bytes,
    *,
    declared_constant_axial_kn: str | None = None,
    constant_axial_source: str | None = None,
):
    """Check whether reported lateral/axial values lie on one line through zero.

    A constant axial load is an explicit external declaration, never a fabricated
    measured channel. Measured and declared loads cannot be silently combined.
    Nonzero two-by-two determinants are exact incompatibility witnesses for
    F = lambda * F_ref, independent of units, signs and Decimal context rounding.
    A zero determinant does not establish physical correspondence, licensing,
    source authentication, numerical solvability or experimental validation.
    """
    history: PeerForceDisplacementHistory = decode_force_displacement_history(
        original_history
    )
    if declared_constant_axial_kn is None:
        if constant_axial_source is not None:
            raise ValueError("constant source requires a declared axial value")
        axial = history.axial_load_kn
        basis = "measured-third-column" if axial is not None else "unavailable"
    else:
        if (
            type(declared_constant_axial_kn) is not str
            or not 1 <= len(declared_constant_axial_kn) <= 128
            or type(constant_axial_source) is not str
            or not 1 <= len(constant_axial_source.strip()) <= 2048
        ):
            raise ValueError("bounded constant axial token and source required")
        if history.axial_load_kn is not None:
            raise ValueError("measured axial history cannot be replaced by a constant")
        try:
            number = Decimal(declared_constant_axial_kn)
        except ArithmeticError as error:
            raise ValueError("finite declared axial token required") from error
        _bounded_decimal(number)
        axial = (number,) * history.declared_pair_count
        basis = "externally-declared-constant-not-measured-channel"

    pivot = None
    witness = None
    duplicates = []
    previous_displacement = None
    lateral_values = set()
    for index, (displacement, lateral) in enumerate(history.points_mm_kn):
        d = _bounded_decimal(displacement)
        h = _bounded_decimal(lateral)
        lateral_values.add(h)
        if d == previous_displacement:
            duplicates.append(index)
        previous_displacement = d
        if axial is None:
            continue
        p = _bounded_decimal(axial[index])
        if pivot is None and (h or p):
            pivot = (index, h, p)
        if pivot is not None and witness is None:
            determinant = pivot[1] * p - h * pivot[2]
            if determinant:
                witness = {
                    "observation_indices_zero_based": [pivot[0], index],
                    "source_line_numbers": [pivot[0] + 3, index + 3],
                    "reported_lateral_axial_kn": [
                        [str(history.points_mm_kn[pivot[0]][1]), str(axial[pivot[0]])],
                        [str(lateral), str(axial[index])],
                    ],
                    "determinant_kn2_exact": {
                        "numerator": str(determinant.numerator),
                        "denominator": str(determinant.denominator),
                    },
                }
    status = (
        "AXIAL_UNAVAILABLE"
        if axial is None
        else "INCOMPATIBLE_SINGLE_PROPORTIONAL_PATTERN"
        if witness is not None
        else "ALL_ZERO_REPORTED_LOADS"
        if pivot is None
        else "REPORTED_LOADS_COLLINEAR_THROUGH_ORIGIN"
    )
    return {
        "schema_version": "experimental-peer-rc-load-pattern-audit.v1",
        "source_sha256": history.source_sha256,
        "source_title": history.title,
        "observation_count": history.declared_pair_count,
        "axial_basis": basis,
        "constant_axial_token": declared_constant_axial_kn,
        "constant_axial_source": constant_axial_source,
        "status": status,
        "nonproportional_witness": witness,
        "distinct_reported_lateral_values": len(lateral_values),
        "consecutive_equal_displacement_indices_zero_based": duplicates,
        "first_observation_mm_kn": [str(x) for x in history.points_mm_kn[0]],
        "applied_force_and_p_delta_correspondence_established": False,
        "constant_axial_source_authenticated": False,
        "source_values_modified": False,
        "commanded_loading_inferred": False,
        "physical_model_reconstructed": False,
        "training_admitted": False,
        "structural_solver_calls": 0,
    }
