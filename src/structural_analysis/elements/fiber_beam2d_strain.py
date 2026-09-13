"""Correctly rounded Hermite strains of the supplied finite coordinates.

This optional development arithmetic profile removes intermediate kinematic
rounding; it does not recover precision absent from accepted coordinates or
change the binary64 constitutive, tangent, assembly or Newton arithmetic.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
import math

import numpy as np

STRAIN_EVALUATIONS = ("matrix", "exact-rational")


@lru_cache(maxsize=1024)
def _coefficients(length: float, xi: float):
    length, xi = Fraction(length), Fraction(xi)
    return (
        1 / length,
        6 * xi / length**2,
        (3 * xi - 1) / length,
        (3 * xi + 1) / length,
    )


def exact_fiber_beam2d_strain(
    local, length: float, xi: float, compensation=None
) -> np.ndarray:
    """Return exact-rational axial/curvature expressions rounded once each."""
    raw = np.asarray(local)
    if raw.shape != (6,) or raw.dtype.kind not in "iuf":
        raise ValueError("finite six-vector required")
    if any(isinstance(v, (bool, np.bool_)) for v in local):
        raise ValueError("finite six-vector required")
    if any(
        isinstance(v, (bool, np.bool_))
        or not isinstance(v, (int, float, np.integer, np.floating))
        or not math.isfinite(v)
        for v in [*raw, length, xi]
    ):
        raise ValueError("finite real kinematic inputs required")
    length, xi = float(length), float(xi)
    if length <= 0 or not -1 <= xi <= 1:
        raise ValueError("positive length and xi in [-1, 1] required")
    u = [Fraction(float(v)) for v in raw]
    if compensation is not None:
        from structural_analysis.solvers.nonlinear.twofold_coordinates import (
            validate,
            fractions,
        )

        validate(local, compensation)
        u = fractions(local, compensation)

    inverse, shear, left, right = _coefficients(length, xi)
    try:
        result = np.array(
            [
                float((u[3] - u[0]) * inverse),
                float((u[1] - u[4]) * shear + u[2] * left + u[5] * right),
            ]
        )
    except OverflowError as exc:
        raise ValueError("generalized strain exceeds finite binary64 range") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError("generalized strain exceeds finite binary64 range")
    result.setflags(write=False)
    return result
