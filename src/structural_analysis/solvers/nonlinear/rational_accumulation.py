"""Finite-input rational force/tangent accumulation for explicit RC trials."""

from fractions import Fraction as F
from functools import lru_cache
import numpy as np

PROFILE = "rational-fiber-to-frame.v1"


def encode(values):
    if isinstance(values, F):
        return [str(values.numerator), str(values.denominator)]
    return [encode(v) for v in values]


def rounded(values):
    def convert(v):
        return float(v) if isinstance(v, F) else [convert(x) for x in v]

    result = np.asarray(convert(values), dtype=float)
    if not np.all(np.isfinite(result)):
        raise ValueError("rational accumulation exceeds finite binary64 range")
    return result


def section_values(fibers, responses):
    force = [F(), F()]
    tangent = [[F(), F()], [F(), F()]]
    for fiber, response in zip(fibers, responses, strict=True):
        area = F(fiber.area_m2) * 1000
        y = F(fiber.y_m)
        n = F(response.stress_mpa) * area
        k = F(response.consistent_tangent_mpa) * area
        force[0] += n
        force[1] -= n * y
        tangent[0][0] += k
        tangent[0][1] -= k * y
        tangent[1][0] -= k * y
        tangent[1][1] += k * y * y
    return force, tangent


@lru_cache(maxsize=1024)
def coefficients(length, xi):
    L, x = F(length), F(xi)
    z = F()
    return (
        (-1 / L, z, z, 1 / L, z, z),
        (z, 6 * x / L**2, (3 * x - 1) / L, z, -6 * x / L**2, (3 * x + 1) / L),
    )


def element_values(element, responses):
    force = [F() for _ in range(6)]
    tangent = [[F() for _ in range(6)] for _ in range(6)]
    for xi, weight, response in zip(*element.quadrature, responses, strict=True):
        n, k = section_values(element.section.fibers, response.fiber_responses)
        B = coefficients(element.length_m, float(xi))
        factor = F(float(weight)) * F(element.length_m) / 2
        columns = [[(a, B[a][j]) for a in range(2) if B[a][j]] for j in range(6)]
        for i in range(6):
            force[i] += sum((v * n[a] for a, v in columns[i]), F()) * factor
            for j in range(6):
                tangent[i][j] += (
                    sum(
                        (v * k[a][b] * w for a, v in columns[i] for b, w in columns[j]),
                        F(),
                    )
                    * factor
                )
    return tuple(force), tuple(tuple(row) for row in tangent)


def transformed(T, force, tangent):
    columns = [
        [(i, F(float(T[i, j]))) for i in range(6) if T[i, j] != 0] for j in range(6)
    ]
    f = [sum((v * force[i] for i, v in column), F()) for column in columns]
    k = [
        [
            sum((v * tangent[i][j] * w for i, v in left for j, w in right), F())
            for right in columns
        ]
        for left in columns
    ]
    return f, k
