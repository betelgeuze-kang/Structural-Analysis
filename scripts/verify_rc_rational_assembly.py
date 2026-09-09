"""Rebuild original rational RC force/tangent records without material/solver calls."""

from fractions import Fraction as F
import numpy as np

PROFILE = "rational-fiber-to-frame.v1"


def _same(actual, exact, label):
    a = np.asarray(actual, dtype=float)
    b = np.asarray(exact, dtype=float)
    if a.shape != b.shape or a.tobytes() != b.tobytes():
        raise ValueError("rational assembly record differs: " + label)


def _wire(values, exact):
    if isinstance(exact, F):
        if values != [str(exact.numerator), str(exact.denominator)]:
            raise ValueError("rational assembly exact identity differs")
    else:
        if len(values) != len(exact):
            raise ValueError("rational assembly exact shape differs")
        for a, b in zip(values, exact, strict=True):
            _wire(a, b)


def verify_assembly(problem, assembly):
    if assembly.get("force_accumulation") != PROFILE:
        raise ValueError("rational assembly profile required")
    n = problem.global_dof_count
    internal = [F() for _ in range(n)]
    K = [[F() for _ in range(n)] for _ in range(n)]
    sections = 0
    for member, row in zip(problem.members, assembly["member_assemblies"], strict=True):
        e = member.element
        r = row["element_response"]
        L = F(e.length_m)
        if (
            row["member_id"] != member.member_id
            or r.get("force_accumulation") != PROFILE
        ):
            raise ValueError("rational member identity differs")
        local = [F() for _ in range(6)]
        local_K = [[F() for _ in range(6)] for _ in range(6)]
        _same(r["integration_point_xi"], e.quadrature[0], "quadrature")
        _same(r["integration_point_weights"], e.quadrature[1], "weights")
        for xi, w, s in zip(*e.quadrature, r["section_responses"], strict=True):
            if s.get("force_accumulation") != PROFILE:
                raise ValueError("rational section profile differs")
            N = [F(), F()]
            C = [[F(), F()], [F(), F()]]
            for fiber, response, stress in zip(
                e.section.fibers,
                s["fiber_responses"],
                s["fiber_stresses_mpa"],
                strict=True,
            ):
                _same([stress], [response["stress_mpa"]], "material stress")
                h = [F(1), -F(fiber.y_m)]
                a = F(fiber.area_m2) * 1000
                for i in range(2):
                    N[i] += h[i] * F(stress) * a
                    for j in range(2):
                        C[i][j] += (
                            h[i] * F(response["consistent_tangent_mpa"]) * a * h[j]
                        )
            _same(
                [s["resultants"]["axial_force_kn"], s["resultants"]["moment_z_kn_m"]],
                N,
                "section forces",
            )
            _same(s["consistent_tangent"], C, "section tangent")
            sections += 1
            t = (F(float(xi)) + 1) / 2
            B = [
                [-1 / L, F(), F(), 1 / L, F(), F()],
                [
                    F(),
                    (-6 + 12 * t) / L**2,
                    (-4 + 6 * t) / L,
                    F(),
                    (6 - 12 * t) / L**2,
                    (-2 + 6 * t) / L,
                ],
            ]
            weight = F(float(w)) * L / 2
            for i in range(6):
                local[i] += sum((B[a][i] * N[a] for a in range(2)), F()) * weight
                for j in range(6):
                    local_K[i][j] += (
                        sum(
                            (
                                B[a][i] * C[a][b] * B[b][j]
                                for a in range(2)
                                for b in range(2)
                            ),
                            F(),
                        )
                        * weight
                    )
        _wire(r["rational_force_local"], local)
        _wire(r["rational_tangent_local"], local_K)
        _same(r["internal_force_local"], local, "element forces")
        _same(r["consistent_tangent_local"], local_K, "element tangent")
        T = problem.member_transformation(member)
        _same(row["transformation_global_to_local"], T, "transform")
        dofs = problem.member_global_dofs(member)
        if list(dofs) != row["global_dofs"]:
            raise ValueError("rational member dofs differ")
        force = [
            sum((F(float(T[a, i])) * local[a] for a in range(6)), F()) for i in range(6)
        ]
        transformed = [
            [
                sum(
                    (
                        F(float(T[a, i])) * local_K[a][b] * F(float(T[b, j]))
                        for a in range(6)
                        for b in range(6)
                    ),
                    F(),
                )
                for j in range(6)
            ]
            for i in range(6)
        ]
        _same(row["internal_load_global"], force, "global member force")
        _same(row["consistent_tangent_global"], transformed, "global member tangent")
        for i, gi in enumerate(dofs):
            internal[gi] += force[i]
            for j, gj in enumerate(dofs):
                K[gi][gj] += transformed[i][j]
    external = [
        F(assembly["target_load_factor"]) * F(float(v))
        for v in problem.reference_external_load_vector()
    ]
    residual = [a - b for a, b in zip(internal, external, strict=True)]
    scale = problem.physical_coordinate_scale
    free = problem.free_global_dofs
    _same(assembly["internal_loads_global"], internal, "internal")
    _same(assembly["external_loads_global"], external, "external")
    _same(
        assembly["residual_kn"],
        [F(float(scale[i])) * residual[i] for i in free],
        "scaled residual",
    )
    _same(
        assembly["jacobian_kn_per_m"],
        [
            [F(float(scale[i])) * K[i][j] * F(float(scale[j])) for j in free]
            for i in free
        ],
        "scaled tangent",
    )
    _same(
        assembly["reactions_global"],
        [residual[i] if i in problem.fixed_global_dofs else F() for i in range(n)],
        "reactions",
    )
    return {
        "section_replays": sections,
        "member_replays": len(problem.members),
        "material_integrations": 0,
        "newton_solves": 0,
        "state_commits": 0,
    }
