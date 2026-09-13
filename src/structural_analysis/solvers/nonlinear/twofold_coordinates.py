"""Portable, canonical two-binary64 coordinate expansions for bounded vectors.

Rational arithmetic forms each operation, then rounds its high and residual low
components separately. Constitutive and linear algebra precision is unchanged.
"""

from fractions import Fraction
import numpy as np


def vector(value):
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.size > 144 or raw.dtype.kind not in "iuf":
        raise ValueError("bounded finite coordinate vector required")
    if any(isinstance(v, (bool, np.bool_)) for v in value):
        raise ValueError("boolean coordinate is invalid")
    result = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(result)):
        raise ValueError("finite coordinates required")
    return result


def split(values):
    high = []
    low = []
    try:
        for value in values:
            a = float(value)
            b = float(value - Fraction(a))
            # The rounded residual may land on a midpoint: normalize its sum
            # with FastTwoSum (abs(a) >= abs(b)), preserving the represented sum.
            total = a + b
            tail = (a - total) + b
            high.append(0.0 if total == 0 else total)
            low.append(0.0 if tail == 0 else tail)
    except (OverflowError, ValueError) as exc:
        raise ValueError("coordinate expansion exceeds binary64 range") from exc
    a, b = np.array(high), np.array(low)
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("finite coordinate expansion required")
    a.setflags(write=False)
    b.setflags(write=False)
    return a, b


def fractions(high, low):
    a, b = vector(high), vector(low)
    if a.shape != b.shape:
        raise ValueError("coordinate component shapes differ")
    return [Fraction(float(x)) + Fraction(float(y)) for x, y in zip(a, b, strict=True)]


def validate(high, low):
    a, b = vector(high), vector(low)
    x, y = split(fractions(a, b))
    if a.tobytes() != x.tobytes() or b.tobytes() != y.tobytes():
        raise ValueError("coordinate expansion is not canonical")
    return a, b


def add(high, low, increment):
    values = fractions(high, low)
    delta = vector(increment)
    if len(values) != len(delta):
        raise ValueError("coordinate increment shape differs")
    return split(v + Fraction(float(d)) for v, d in zip(values, delta, strict=True))


def transform(matrix, high, low):
    values = fractions(high, low)
    matrix = np.asarray(matrix, dtype=float)
    if (
        matrix.ndim != 2
        or matrix.shape[1] != len(values)
        or matrix.shape[0] > 144
        or not np.all(np.isfinite(matrix))
    ):
        raise ValueError("bounded finite coordinate transform required")
    return split(
        sum(
            (
                Fraction(float(c)) * v
                for c, v in zip(row, values, strict=True)
                if c != 0
            ),
            Fraction(),
        )
        for row in matrix
    )
