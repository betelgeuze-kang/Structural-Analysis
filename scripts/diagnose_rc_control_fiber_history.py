"""Ordered fiber-strain/history attribution of saved forces, without state commits.

Counterfactual material trials use original native parents and the declared law.
They are not a new equilibrium solution or a precision-qualified reference.
"""

from collections import Counter
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
from time import perf_counter_ns

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    _restore_section_state,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_coordinate_precision,
    _with_material_arithmetic,
    _with_strain_evaluation,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.elements.fiber_beam2d_strain import exact_fiber_beam2d_strain
import numpy as np

_spec = importlib.util.spec_from_file_location(
    "_fiber_history_force",
    Path(__file__).with_name("diagnose_rc_control_force_error.py"),
)
force = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(force)

STRAIN_EFFECTS = (
    "reference_fiber_projection_rounding",
    "reference_generalized_strain_evaluation",
    "finite_coordinate_difference",
    "candidate_generalized_strain_evaluation",
    "candidate_fiber_projection_rounding",
)


def fiber_strain_levels(response, point, length, xi, y):
    """Original projection, exact projection, and exact coordinate-to-fiber strain."""
    axial, curvature = response["generalized_strains"][point]
    projected = F(axial) - F(curvature) * F(y)
    local = [
        F(high) + F(low)
        for high, low in zip(
            response["local_displacements"],
            response.get("local_displacement_compensation", [0.0] * 6),
            strict=True,
        )
    ]
    B = force.rational_b(length, xi)
    direct = sum(((B[0][j] - F(y) * B[1][j]) * local[j] for j in range(6)), F())
    return [axial - curvature * y, float(projected), float(direct)]


def ordered_components(values, original_delta, external_delta):
    """Close each order in rational arithmetic, retaining arithmetic and load terms."""
    retained = values[1][5] - values[0][0] - external_delta
    common = {
        "force_and_section_arithmetic": original_delta - retained,
        "external_load_difference": -external_delta,
    }
    orders = {}
    for name, parent, history in (
        ("reference_parent_then_history", 0, values[1][5] - values[0][5]),
        ("history_then_candidate_parent", 1, values[1][0] - values[0][0]),
    ):
        components = common | {"parent_history_difference": history}
        components.update(
            {
                key: values[parent][j + 1] - values[parent][j]
                for j, key in enumerate(STRAIN_EFFECTS)
            }
        )
        if sum(components.values(), F()) != original_delta:
            raise ValueError("fiber/history decomposition does not close")
        orders[name] = {k: float(v) for k, v in components.items()}
    return orders


def trial_force_fields(problem, steps, work):
    """Twelve material calls per fiber; exact force projections of finite stresses."""
    all_fields = [[{} for _ in range(6)] for _ in range(2)]
    internal = [
        [[F() for _ in range(problem.global_dof_count)] for _ in range(6)]
        for _ in range(2)
    ]
    for member_index, member in enumerate(problem.members):
        element, section = member.element, member.element.section
        responses = [
            s["trial_assembly"]["member_assemblies"][member_index]["element_response"]
            for s in steps
        ]
        parent_elements = [
            s["parent_checkpoint"]["element_states"][member_index] for s in steps
        ]
        if any(p["element_id"] != member.member_id for p in parent_elements):
            raise ValueError("original parent member order differs")
        locals_ = [[[F() for _ in range(6)] for _ in range(6)] for _ in range(2)]
        for point, (xi, weight) in enumerate(zip(*element.quadrature, strict=True)):
            parents = [
                _restore_section_state(
                    section.initial_state(),
                    p["integration_point_states"][point],
                    path=f"{member.member_id}/{point}",
                )
                for p in parent_elements
            ]
            for p in parents:
                section.validate_state(p)
            before = [force.canonical(p.to_dict()) for p in parents]
            resultants = [[[F(), F()] for _ in range(6)] for _ in range(2)]
            originals = [r["section_responses"][point] for r in responses]
            for response in responses:
                generalized = (
                    exact_fiber_beam2d_strain(
                        response["local_displacements"],
                        element.length_m,
                        float(xi),
                        response.get("local_displacement_compensation"),
                    )
                    if element.strain_evaluation == "exact-rational"
                    else element.strain_displacement_matrix(xi)
                    @ np.asarray(response["local_displacements"])
                )
                force.equal(
                    response["generalized_strains"][point],
                    generalized,
                    "original generalized strain evaluation",
                )
            for fiber_index, fiber in enumerate(section.fibers):
                levels = [
                    fiber_strain_levels(
                        r, point, element.length_m, float(xi), fiber.y_m
                    )
                    for r in responses
                ]
                for original, strains in zip(originals, levels, strict=True):
                    force.equal(
                        [original["fiber_strains"][fiber_index]],
                        [strains[0]],
                        "original fiber strain projection",
                    )
                strains = levels[0] + list(reversed(levels[1]))
                law = (
                    section.steel
                    if fiber.material_kind == "steel"
                    else section.concrete
                )
                for pindex, parent in enumerate(parents):
                    for stage, strain in enumerate(strains):
                        work["material_trial_calls"] += 1
                        work[f"{fiber.material_kind}_trial_calls"] += 1
                        trial = law.integrate(strain, parent.fiber_states[fiber_index])
                        if (pindex, stage) in ((0, 0), (1, 5)):
                            if force.canonical(trial.to_dict()) != force.canonical(
                                originals[pindex]["fiber_responses"][fiber_index]
                            ):
                                raise ValueError(
                                    "original material response replay differs"
                                )
                            work["original_material_responses_verified"] += 1
                        axial = F(trial.stress_mpa) * F(fiber.area_m2) * 1000
                        resultants[pindex][stage][0] += axial
                        resultants[pindex][stage][1] -= axial * F(fiber.y_m)
            if before != [force.canonical(p.to_dict()) for p in parents]:
                raise ValueError("counterfactual trial mutated original parent")
            B = force.rational_b(element.length_m, float(xi))
            factor = F(float(weight)) * F(element.length_m) / 2
            for parent in range(2):
                for stage in range(6):
                    for j in range(6):
                        locals_[parent][stage][j] += sum(
                            (
                                B[k][j] * resultants[parent][stage][k] * factor
                                for k in range(2)
                            ),
                            F(),
                        )
        T, dofs = (
            problem.member_transformation(member),
            problem.member_global_dofs(member),
        )
        for parent in range(2):
            for stage in range(6):
                for j in range(6):
                    all_fields[parent][stage][f"member/{member.member_id}/{j}"] = (
                        locals_[parent][stage][j] * 1000
                    )
                    internal[parent][stage][dofs[j]] += sum(
                        (
                            F(float(T[k, j])) * locals_[parent][stage][k] * 1000
                            for k in range(6)
                        ),
                        F(),
                    )
    for parent in range(2):
        for stage in range(6):
            for dof in problem.fixed_global_dofs:
                all_fields[parent][stage][f"reaction/{dof}"] = internal[parent][stage][
                    dof
                ]
    return all_fields


def diagnose(study, candidate="secant"):
    start = perf_counter_ns()
    # Complete original force/path/step/history arithmetic and input hashes first.
    original = force.diagnose(study, candidate)
    identity = json.loads((study / "request.json").read_text())
    if identity.get("fiber_strain_evaluation", "generalized") != "generalized":
        raise ValueError(
            "this diagnostic requires the generalized fiber strain profile"
        )
    compiled, blockers, _ = public._compile(load_neutral_json(study / "model.json"))
    if blockers or compiled is None:
        raise ValueError("supported original model required")
    compiled = _with_material_arithmetic(
        _with_coordinate_precision(
            _with_strain_evaluation(
                compiled, identity.get("strain_evaluation", "matrix")
            ),
            identity.get("coordinate_precision", "binary64"),
        ),
        identity.get("material_arithmetic", "binary64"),
    )
    problem = compiled.problem
    if problem.contract_hash != original["compiled_problem_contract_hash"]:
        raise ValueError("original problem contract differs")
    work = Counter(
        model_compilations=2,
        original_step_force_replays=original["work"]["original_step_force_replays"],
        section_integrations=0,
        element_integrations=0,
        newton_solves=0,
        state_commits=0,
    )
    histories = {
        arm: json.loads((study / arm / "path.json").read_text())["response_history"]
        for arm in ("reference", candidate)
    }
    rows = []
    previous = [None, None]
    for index in range(original["target_count"]):
        steps = [
            json.loads((study / arm / f"{index:03d}-1-step.json").read_text())
            for arm in ("reference", candidate)
        ]
        for arm, step in enumerate(steps):
            payload = dict(step)
            if payload.pop("step_hash") != canonical_hash(payload):
                raise ValueError("original step hash differs")
            if previous[arm] is not None and step["parent_checkpoint"] != previous[arm]:
                raise ValueError("original parent chain differs")
            previous[arm] = step["accepted_checkpoint"]
        trial = trial_force_fields(problem, steps, work)
        loads = problem.reference_external_load_vector()
        external = [
            {
                f"reaction/{dof}": F(s["accepted_checkpoint"]["load_factor"])
                * F(float(loads[dof]))
                * 1000
                for dof in problem.fixed_global_dofs
            }
            for s in steps
        ]
        selected = [r for r in original["rows"] if r["target_index"] == index]
        # Recompute exact endpoints, rather than relying on rounded diagnostic JSON.
        exact = [
            force.force_fields(
                problem,
                s,
                histories[arm][index],
            )
            for s, arm in zip(steps, ("reference", candidate), strict=True)
        ]
        work["additional_original_step_force_replays"] += 2
        for row in selected:
            key = row["field"]
            values = [[stage[key] for stage in p] for p in trial]
            for parent, stage in ((0, 0), (1, 5)):
                if (
                    values[parent][stage] - external[parent].get(key, F())
                    != exact[parent]["exact_stored_stresses"][key]
                ):
                    raise ValueError("original exact stress endpoint differs")
            delta = exact[1]["original"][key] - exact[0]["original"][key]
            orders = ordered_components(
                values, delta, external[1].get(key, F()) - external[0].get(key, F())
            )
            rows.append(
                {
                    "target_index": index,
                    "field": key,
                    "original_comparison_failed": row["comparison_failed"]["original"],
                    "original_difference_si": float(delta),
                    "orders": orders,
                    "exact_rational_decompositions_close": True,
                }
            )
    import hashlib

    for item in original["input_files"]:
        if (
            hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
            != item["sha256"]
        ):
            raise ValueError("original input changed during diagnostic")
    return {
        "schema_version": "rc-control-fiber-history-attribution.v1",
        "original_source_revision": original["original_source_revision"],
        "compiled_problem_contract_hash": problem.contract_hash,
        "target_count": original["target_count"],
        "rows": rows,
        "work": dict(work),
        "input_files": original["input_files"],
        "wall_ns": perf_counter_ns() - start,
        "scope": "two ordered original-law counterfactuals; finite single-round fiber inputs and unchanged native parents; no solve or commit",
        "claims": {
            "unique_causal_attribution": False,
            "repaired_solver": False,
            "independent_validation": False,
        },
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
