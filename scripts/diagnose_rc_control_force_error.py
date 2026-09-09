"""Read-only force-arithmetic counterfactuals; no constitutive/Newton execution.

Exact finite-input arithmetic is a diagnostic, not a replacement result or
independent equilibrium solution. All stages retain original trial stresses.
"""

from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_coordinate_precision,
    _with_strain_evaluation,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

STAGES = (
    "original",
    "exact_stored_coefficients",
    "exact_geometry_coefficients",
    "exact_stored_stresses",
)
EFFECTS = (
    "force_product_sum_transform_and_si_rounding",
    "geometry_coefficient_rounding",
    "section_resultant_rounding",
    "retained_stress_and_load_difference",
)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def equal(actual, expected, label):
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.all(np.isfinite(a)) or a.tobytes() != b.tobytes():
        raise ValueError("original arithmetic replay differs: " + label)


def rational_b(length, xi):
    L, x = F(float(length)), F(float(xi))
    z = F()
    return [
        [-1 / L, z, z, 1 / L, z, z],
        [z, 6 * x / L**2, (3 * x - 1) / L, z, -6 * x / L**2, (3 * x + 1) / L],
    ]


def section_resultants(section, response):
    stresses = response["fiber_stresses_mpa"]
    if len(stresses) != len(section.fibers) or len(response["fiber_responses"]) != len(
        stresses
    ):
        raise ValueError("original fiber roster differs")
    axial = moment = 0.0
    exact = [F(), F()]
    for fiber, stress, row in zip(
        section.fibers, stresses, response["fiber_responses"], strict=True
    ):
        equal([stress], [row["stress_mpa"]], "fiber stress projection")
        force = float(stress) * fiber.area_m2 * 1000.0
        axial += force
        moment -= force * fiber.y_m
        value = F(stress) * F(fiber.area_m2) * 1000
        exact[0] += value
        exact[1] -= value * F(fiber.y_m)
    saved = [
        response["resultants"]["axial_force_kn"],
        response["resultants"]["moment_z_kn_m"],
    ]
    equal([axial, moment], saved, "section resultants")
    return saved, exact


def member_forces(element, response):
    points, weights = element.quadrature
    equal(points, response["integration_point_xi"], "quadrature points")
    equal(weights, response["integration_point_weights"], "quadrature weights")
    if len(response["section_responses"]) != len(points):
        raise ValueError("original section roster differs")
    original = np.zeros(6)
    stages = {name: [F() for _ in range(6)] for name in STAGES[1:]}
    for xi, weight, section in zip(
        points, weights, response["section_responses"], strict=True
    ):
        saved, exact = section_resultants(element.section, section)
        B = element.strain_displacement_matrix(xi)
        factor = weight * (element.length_m / 2.0)
        original += (B.T @ np.asarray(saved)) * factor
        exact_B = rational_b(element.length_m, xi)
        exact_factor = F(float(weight)) * F(element.length_m) / 2
        for dof in range(6):
            stages["exact_stored_coefficients"][dof] += sum(
                (
                    F(float(B[k, dof])) * F(saved[k]) * F(float(factor))
                    for k in range(2)
                ),
                F(),
            )
            stages["exact_geometry_coefficients"][dof] += sum(
                (exact_B[k][dof] * F(saved[k]) * exact_factor for k in range(2)), F()
            )
            stages["exact_stored_stresses"][dof] += sum(
                (exact_B[k][dof] * exact[k] * exact_factor for k in range(2)), F()
            )
    equal(original, response["internal_force_local"], "member local force")
    return original, stages


def force_fields(problem, step, history):
    assembly = step["trial_assembly"]
    if (
        not step["committed"]
        or step["parent_checkpoint"]["problem_contract_hash"] != problem.contract_hash
    ):
        raise ValueError("original committed problem binding differs")
    if len(assembly["member_assemblies"]) != len(problem.members):
        raise ValueError("original member roster differs")
    fields = {name: {} for name in STAGES}
    internal = np.zeros(problem.global_dof_count)
    exact_internal = {name: [F() for _ in internal] for name in STAGES[1:]}
    if len(history["member_end_forces"]) != len(problem.members):
        raise ValueError("history member roster differs")
    for member, row, saved in zip(
        problem.members,
        assembly["member_assemblies"],
        history["member_end_forces"],
        strict=True,
    ):
        if (
            row["member_id"] != member.member_id
            or saved["member_id"] != member.member_id
        ):
            raise ValueError("original member identity differs")
        dofs = problem.member_global_dofs(member)
        if list(dofs) != row["global_dofs"]:
            raise ValueError("original member DOFs differ")
        T = problem.member_transformation(member)
        equal(T, row["transformation_global_to_local"], "member transformation")
        local, exact_local = member_forces(member.element, row["element_response"])
        global_force = T.T @ local
        equal(global_force, row["internal_load_global"], "member global force")
        internal[list(dofs)] += global_force
        for j in range(6):
            key = f"member/{member.member_id}/{j}"
            end = saved["local_end_i" if j < 3 else "local_end_j"]
            saved_si = end[("FX_N", "FY_N", "MZ_Nm")[j % 3]]
            equal([float(local[j]) * 1000.0], [saved_si], "member SI force")
            fields["original"][key] = F(saved_si)
            for name, vector in exact_local.items():
                fields[name][key] = vector[j] * 1000
                exact_internal[name][dofs[j]] += sum(
                    (F(float(T[k, j])) * vector[k] for k in range(6)), F()
                )
    equal(internal, assembly["internal_loads_global"], "assembled internal forces")
    factor = step["accepted_checkpoint"]["load_factor"]
    equal([factor], [assembly["target_load_factor"]], "load factor")
    loads = problem.reference_external_load_vector()
    external = factor * loads
    equal(external, assembly["external_loads_global"], "external loads")
    residual = internal - external
    reactions = np.zeros(problem.global_dof_count)
    reactions[list(problem.fixed_global_dofs)] = residual[
        list(problem.fixed_global_dofs)
    ]
    equal(reactions, assembly["reactions_global"], "support reactions")
    if len(history["support_reactions"]) != len(problem.fixed_global_dofs):
        raise ValueError("history reaction roster differs")
    for dof, row in zip(
        problem.fixed_global_dofs, history["support_reactions"], strict=True
    ):
        key = f"reaction/{dof}"
        equal([float(reactions[dof]) * 1000.0], [row["value_si"]], "reaction SI value")
        fields["original"][key] = F(row["value_si"])
        for name in STAGES[1:]:
            fields[name][key] = (
                exact_internal[name][dof] - F(factor) * F(float(loads[dof]))
            ) * 1000
    return fields


def attribute(reference, candidate, absolute_tolerance, relative_tolerance):
    rows = []
    for key in reference["original"]:
        values = {name: (reference[name][key], candidate[name][key]) for name in STAGES}
        differences = [b - a for a, b in values.values()]
        components = [differences[i] - differences[i + 1] for i in range(3)] + [
            differences[-1]
        ]
        assert sum(components, F()) == differences[0]
        failed = {}
        for name, (a, b) in values.items():
            a, b = float(a), float(b)
            failed[name] = abs(a - b) > absolute_tolerance + relative_tolerance * max(
                abs(a), abs(b)
            )
        rows.append(
            {
                "field": key,
                "unit": "N*m" if int(key.rsplit("/", 1)[1]) % 3 == 2 else "N",
                "values_si": {
                    name: [float(a), float(b)] for name, (a, b) in values.items()
                },
                "comparison_failed": failed,
                "difference_candidate_minus_reference_si": float(differences[0]),
                "components_si": dict(
                    zip(EFFECTS, map(float, components), strict=True)
                ),
                "exact_rational_decomposition_closes": True,
            }
        )
    return rows


def diagnose(study, candidate="secant"):
    if candidate not in ("secant", "proposal"):
        raise ValueError("supported original candidate required")
    start = perf_counter_ns()
    study = Path(study)
    inputs = {}

    def read(path):
        raw = path.read_bytes()
        inputs[path] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    model = study / "model.json"
    read(model)
    compiled, blockers, _ = public._compile(load_neutral_json(model))
    if compiled is None or blockers:
        raise ValueError("supported original model required")
    identity = read(study / "request.json")
    compiled = _with_coordinate_precision(
        _with_strain_evaluation(compiled, identity.get("strain_evaluation", "matrix")),
        identity.get("coordinate_precision", "binary64"),
    )
    expected = identity.get(
        "compiled_problem_contract_hash", compiled.problem.contract_hash
    )
    if expected != compiled.problem.contract_hash:
        raise ValueError("declared arithmetic contract differs")
    paths = {arm: read(study / arm / "path.json") for arm in ("reference", candidate)}
    for path in paths.values():
        payload = dict(path)
        if (
            payload.pop("path_hash")
            != "sha256:" + hashlib.sha256(canonical(payload)).hexdigest()
        ):
            raise ValueError("original path hash differs")
        if path["source_problem_hash"] != compiled.problem.contract_hash:
            raise ValueError("original path problem differs")
        if len(path["response_history"]) != len(path["entries"]) or len(
            path["requested_targets_m"]
        ) != len(path["entries"]):
            raise ValueError("original path roster differs")
        if (
            path["status"] != "complete"
            or not path["entries"]
            or path["accepted_target_count"] != len(path["entries"])
        ):
            raise ValueError("complete nonempty original path required")
    if (
        paths["reference"]["requested_targets_m"]
        != paths[candidate]["requested_targets_m"]
    ):
        raise ValueError("original target schedules differ")
    absolute = identity["absolute_tolerance"]
    relative = identity["relative_tolerance"]
    rows = []
    for index, (a, b) in enumerate(
        zip(paths["reference"]["entries"], paths[candidate]["entries"], strict=True)
    ):
        fields = []
        for arm, entry in zip(("reference", candidate), (a, b), strict=True):
            if (
                entry["target_index"] != index
                or len(entry["invocations"]) != 1
                or not entry["invocations"][0]["committed"]
            ):
                raise ValueError(
                    "one original committed invocation per target required"
                )
            step = read(study / arm / f"{index:03d}-1-step.json")
            payload = dict(step)
            if payload.pop("step_hash") != canonical_hash(payload):
                raise ValueError("original step hash differs")
            if (
                step["step_hash"]
                != paths[arm]["response_history"][index]["source_step_hash"]
            ):
                raise ValueError("original step-to-history binding differs")
            fields.append(
                force_fields(
                    compiled.problem, step, paths[arm]["response_history"][index]
                )
            )
        rows.extend(
            dict(target_index=index, **row)
            for row in attribute(*fields, absolute, relative)
        )
    counts = {
        stage: Counter(
            row["field"].split("/")[0]
            for row in rows
            if row["comparison_failed"][stage]
        )
        for stage in STAGES
    }
    for path, digest in inputs.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("original input changed during diagnostic")
    return {
        "schema_version": "rc-control-force-arithmetic-diagnostic.v1",
        "study": str(study.resolve()),
        "candidate": candidate,
        "original_source_revision": identity["source_revision"],
        "compiled_problem_contract_hash": compiled.problem.contract_hash,
        "target_count": len(paths["reference"]["entries"]),
        "stage_order": list(STAGES),
        "effect_order": list(EFFECTS),
        "absolute_tolerance": absolute,
        "relative_tolerance": relative,
        "counterfactual_force_mismatch_counts": {
            name: dict(counts[name]) for name in STAGES
        },
        "rows": rows,
        "work": {
            "model_compilations": 1,
            "original_step_force_replays": len(paths["reference"]["entries"]) * 2,
            "section_integrations": 0,
            "constituent_integrations": 0,
            "newton_solves": 0,
            "state_commits": 0,
        },
        "wall_ns": perf_counter_ns() - start,
        "input_files": [
            {"path": str(p.resolve()), "sha256": digest} for p, digest in inputs.items()
        ],
        "claim_boundary": "Original stored-stress arithmetic attribution only. Stage order is explicit; counterfactual forces are not equilibrium solutions, accepted outputs or an independent reference.",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--candidate", choices=["secant", "proposal"], default="secant")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(
        args.study.resolve()
    ):
        parser.error("output must be new and outside the original study")
    report = diagnose(args.study, args.candidate)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"rows", "input_files"}}
        )
    )


if __name__ == "__main__":
    main()
