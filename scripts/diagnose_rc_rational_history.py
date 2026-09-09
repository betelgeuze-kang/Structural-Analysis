"""Read-only ordered coordinate/history/stress-rounding attribution of RC records.

Four original-law material trials per fiber retain rational trial inputs and
native parents. Counterfactual forces are not new accepted equilibrium results.
"""

from collections import Counter
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from time import perf_counter_ns

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    _restore_section_state,
    load_stateful_fiber_frame2d_checkpoint_bytes as load,
    dump_stateful_fiber_frame2d_checkpoint_bytes as dump,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_coordinate_precision,
    _with_fiber_strain_evaluation,
    _with_force_accumulation,
    _with_material_arithmetic,
    _with_strain_evaluation,
    _physical_mismatch_locations,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json

spec = importlib.util.spec_from_file_location(
    "_rational_record_verifier",
    Path(__file__).with_name("verify_rc_rational_assembly.py"),
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def check(condition, label):
    if not condition:
        raise ValueError("original rational history differs: " + label)


def checked(value, key):
    payload = dict(value)
    check(payload.pop(key) == canonical_hash(payload), key)
    return value


def basis(length, xi):
    L = F(length)
    t = (F(float(xi)) + 1) / 2
    return [
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


def strains(response, B):
    u = [
        F(h) + F(low)
        for h, low in zip(
            response["local_displacements"],
            response["local_displacement_compensation"],
            strict=True,
        )
    ]
    return [sum((b * x for b, x in zip(row, u, strict=True)), F()) for row in B]


def stress_100(law, kind, strain, parent, trial):
    """Independent declared branch expression; finite 100-digit diagnostic, not truth."""
    with localcontext(
        Context(prec=100, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
    ):

        def D(v):
            v = F(v)
            return Decimal(v.numerator) / Decimal(v.denominator)

        E = D(law.elastic_modulus_mpa)
        e = D(strain)
        rounded = float(strain)
        if kind == "steel":
            if trial.yielded:
                sign = (
                    1
                    if law.elastic_modulus_mpa * (rounded - parent.plastic_strain)
                    - parent.backstress_mpa
                    >= 0
                    else -1
                )
                H = D(law.isotropic_hardening_modulus_mpa) + D(
                    law.kinematic_hardening_modulus_mpa
                )
                value = D(parent.backstress_mpa) + sign * (
                    D(law.yield_stress_mpa)
                    + D(law.isotropic_hardening_modulus_mpa)
                    * D(parent.accumulated_plastic_strain)
                    + H * D(trial.plastic_multiplier_increment)
                )
                if H:
                    value += (e - D(rounded)) / (1 / E + 1 / H)
            else:
                value = E * (e - D(parent.plastic_strain))
        else:
            tension = rounded >= 0
            previous = (
                parent.tensile_history_strain
                if tension
                else parent.compressive_history_strain
            )
            threshold = (
                law.tensile_threshold_strain
                if tension
                else law.compressive_threshold_strain
            )
            rate = (
                law.tensile_softening_rate
                if tension
                else law.compressive_softening_rate
            )
            history = abs(e) if abs(rounded) >= previous else D(previous)
            survival = (
                Decimal(1)
                if max(abs(rounded), previous) <= threshold
                else D(threshold) / history * ((D(threshold) - history) * D(rate)).exp()
            )
            value = E * max(survival, D(1.0 - math.nextafter(1.0, 0.0))) * e
        check(float(value) == trial.stress_mpa, "100-digit stress projection")
        return F(value)


def trial_fields(problem, steps, work):
    # First index: rounded returned stress / independent 100-digit expression.
    result = [[[{} for _ in range(2)] for _ in range(2)] for _ in range(2)]
    internal = [
        [
            [[F() for _ in range(problem.global_dof_count)] for _ in range(2)]
            for _ in range(2)
        ]
        for _ in range(2)
    ]
    for mi, member in enumerate(problem.members):
        e = member.element
        section = e.section
        responses = [
            s["trial_assembly"]["member_assemblies"][mi]["element_response"]
            for s in steps
        ]
        parents = [s["parent_checkpoint"]["element_states"][mi] for s in steps]
        local = [
            [[[F() for _ in range(6)] for _ in range(2)] for _ in range(2)]
            for _ in range(2)
        ]
        for point, (xi, w) in enumerate(zip(*e.quadrature, strict=True)):
            B = basis(e.length_m, xi)
            generalized = [strains(r, B) for r in responses]
            for r, g in zip(responses, generalized, strict=True):
                check(
                    r["generalized_strains"][point] == list(map(float, g)),
                    "generalized strain",
                )
            native = [
                _restore_section_state(
                    section.initial_state(),
                    p["integration_point_states"][point],
                    path=f"{member.member_id}/{point}",
                )
                for p in parents
            ]
            for p in native:
                section.validate_state(p)
            before = [canonical(p.to_dict()) for p in native]
            N = [[[[F(), F()] for _ in range(2)] for _ in range(2)] for _ in range(2)]
            for fi, fiber in enumerate(section.fibers):
                exact = [g[0] - F(fiber.y_m) * g[1] for g in generalized]
                law = (
                    section.steel
                    if fiber.material_kind == "steel"
                    else section.concrete
                )
                for q in range(2):
                    r = responses[q]["section_responses"][point]
                    actual = r["fiber_responses"][fi]
                    ident = actual["stress_trial_strain"]
                    check(
                        exact[q]
                        == F(int(ident["numerator"]), int(ident["denominator"])),
                        "exact fiber strain",
                    )
                    check(
                        r["fiber_strains"][fi] == float(exact[q]),
                        "fiber strain projection",
                    )
                for p in range(2):
                    for q in range(2):
                        work["selected_material_trial_calls"] += 1
                        work["nested_original_base_calls"] += 1
                        work[f"{fiber.material_kind}_selected_calls"] += 1
                        trial = law.integrate(exact[q], native[p].fiber_states[fi])
                        if p == q:
                            check(
                                canonical(trial.to_dict())
                                == canonical(
                                    responses[p]["section_responses"][point][
                                        "fiber_responses"
                                    ][fi]
                                ),
                                "material endpoint replay",
                            )
                            work["original_material_endpoints_verified"] += 1
                        high = stress_100(
                            law,
                            fiber.material_kind,
                            exact[q],
                            native[p].fiber_states[fi],
                            trial,
                        )
                        work["independent_100_digit_stress_evaluations"] += 1
                        for precision, stress in enumerate([F(trial.stress_mpa), high]):
                            force = stress * F(fiber.area_m2) * 1000
                            N[precision][p][q][0] += force
                            N[precision][p][q][1] -= force * F(fiber.y_m)
            check(
                before == [canonical(p.to_dict()) for p in native],
                "immutable native parents",
            )
            for precision in range(2):
                for p in range(2):
                    for q in range(2):
                        for component, value in enumerate(N[precision][p][q]):
                            result[precision][p][q][
                                f"section/{member.member_id}/{point}/{component}"
                            ] = value * 1000
                        for j in range(6):
                            local[precision][p][q][j] += (
                                sum(
                                    (B[a][j] * N[precision][p][q][a] for a in range(2)),
                                    F(),
                                )
                                * F(float(w))
                                * F(e.length_m)
                                / 2
                            )
        T = problem.member_transformation(member)
        dofs = problem.member_global_dofs(member)
        for precision in range(2):
            for p in range(2):
                for q in range(2):
                    for j in range(6):
                        result[precision][p][q][f"member/{member.member_id}/{j}"] = (
                            local[precision][p][q][j] * 1000
                        )
                        internal[precision][p][q][dofs[j]] += (
                            sum(
                                (
                                    F(float(T[a, j])) * local[precision][p][q][a]
                                    for a in range(6)
                                ),
                                F(),
                            )
                            * 1000
                        )
    for precision in range(2):
        for p in range(2):
            for q in range(2):
                for dof in problem.fixed_global_dofs:
                    result[precision][p][q][f"reaction/{dof}"] = internal[precision][p][
                        q
                    ][dof]
    return result


def originals(compiled, step, history, finite):
    """Verify original SI projections of already independently verified assembly."""
    problem = compiled.problem
    result = {}
    for mi, member in enumerate(problem.members):
        m = history["member_end_forces"][mi]
        check(m["member_id"] == member.member_id, "history member")
        er = step["trial_assembly"]["member_assemblies"][mi]["element_response"]
        for j in range(6):
            value = m["local_end_i" if j < 3 else "local_end_j"][
                ("FX_N", "FY_N", "MZ_Nm")[j % 3]
            ]
            key = f"member/{member.member_id}/{j}"
            check(value == float(finite[key] / 1000) * 1000, "member SI projection")
            result[key] = F(value)
        rows = [
            s for s in history["section_results"] if s["member_id"] == member.member_id
        ]
        check(len(rows) == len(er["section_responses"]), "section history count")
        for point, (s, response) in enumerate(
            zip(rows, er["section_responses"], strict=True)
        ):
            check(
                s["integration_point_index"] == point
                and s["section_state_hash"] == response["trial_state"]["state_hash"],
                "section history binding",
            )
            for component, field in enumerate(["axial_force_N", "moment_z_Nm"]):
                key = f"section/{member.member_id}/{point}/{component}"
                check(
                    s[field] == float(finite[key] / 1000) * 1000,
                    "section SI projection",
                )
                result[key] = F(s[field])
    loads = problem.reference_external_load_vector()
    external = {}
    check(
        step["accepted_checkpoint"]["load_factor"]
        == step["trial_assembly"]["target_load_factor"],
        "accepted load factor",
    )
    for dof, row in zip(
        problem.fixed_global_dofs, history["support_reactions"], strict=True
    ):
        key = f"reaction/{dof}"
        external[key] = (
            F(step["accepted_checkpoint"]["load_factor"]) * F(float(loads[dof])) * 1000
        )
        check(
            row["node_id"] == compiled.node_ids[dof // 3]
            and row["dof"] == ("UX", "UY", "RZ")[dof % 3]
            and row["value_si"] == float((finite[key] - external[key]) / 1000) * 1000,
            "reaction SI projection",
        )
        result[key] = F(row["value_si"])
    return result, external


def decompose(finite, high, original_delta, external_delta):
    common = {
        "output_projection_rounding": original_delta
        - (finite[1][1] - finite[0][0] - external_delta),
        "returned_stress_rounding": (finite[1][1] - high[1][1])
        - (finite[0][0] - high[0][0]),
        "external_load_difference": -external_delta,
    }
    orders = {
        "reference_parent_then_history": common
        | {
            "finite_coordinate_difference": high[0][1] - high[0][0],
            "parent_history_difference": high[1][1] - high[0][1],
        },
        "history_then_candidate_parent": common
        | {
            "finite_coordinate_difference": high[1][1] - high[1][0],
            "parent_history_difference": high[1][0] - high[0][0],
        },
    }
    for values in orders.values():
        check(
            sum(values.values(), F()) == original_delta, "exact decomposition closure"
        )
    return orders


def diagnose(study, candidate="secant"):
    check(candidate in ("secant", "proposal"), "candidate")
    start = perf_counter_ns()
    study = Path(study)
    inputs = {}

    def read(path):
        raw = path.read_bytes()
        inputs[path] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    identity = read(study / "request.json")
    check(
        identity.get("force_accumulation") == "rational"
        and identity.get("material_arithmetic") == "retained-strain"
        and identity.get("fiber_strain_evaluation") == "retained-coordinate",
        "profile",
    )
    read(study / "model.json")
    model = load_neutral_json(study / "model.json")
    check(
        model.canonical_model_checksum == identity["model_checksum"], "model checksum"
    )
    compiled, blockers, _ = _compile(model)
    check(compiled is not None and not blockers, "supported model")
    compiled = _with_force_accumulation(
        _with_fiber_strain_evaluation(
            _with_material_arithmetic(
                _with_coordinate_precision(
                    _with_strain_evaluation(compiled, identity["strain_evaluation"]),
                    identity["coordinate_precision"],
                ),
                "retained-strain",
            ),
            "retained-coordinate",
        ),
        "rational",
    )
    problem = compiled.problem
    check(
        problem.contract_hash == identity["compiled_problem_contract_hash"],
        "compiled contract",
    )
    report = checked(read(study / "comparison.json"), "report_hash")
    check(all(report[k] == v for k, v in identity.items()), "comparison identity")
    paths = {
        arm: checked(read(study / arm / "path.json"), "path_hash")
        for arm in ["reference", candidate, "fresh-reference"]
    }
    for arm, p in paths.items():
        check(
            p["source_problem_hash"] == problem.contract_hash
            and p["status"] == "complete"
            and p["entries"]
            and len(p["entries"])
            == p["accepted_target_count"]
            == len(p["response_history"])
            == len(p["requested_targets_m"]),
            "complete path",
        )
        check(
            p["requested_targets_m"] == paths["reference"]["requested_targets_m"],
            "target schedule",
        )
    check(
        paths["reference"]["response_history"]
        == paths["fresh-reference"]["response_history"]
        and paths["reference"]["terminal_checkpoint"]
        == paths["fresh-reference"]["terminal_checkpoint"],
        "fresh reference repeat",
    )
    mismatch = _physical_mismatch_locations(
        paths["fresh-reference"]["response_history"],
        paths[candidate]["response_history"],
        absolute_tolerance=identity["absolute_tolerance"],
        relative_tolerance=identity["relative_tolerance"],
    )
    check(
        mismatch == report["comparisons"][candidate]["mismatch_locations"],
        "full comparison locations",
    )
    work = Counter(
        model_compilations=1,
        section_integrations=0,
        element_integrations=0,
        newton_solves=0,
        state_commits=0,
    )
    rows = []
    previous = [initial_stateful_fiber_frame2d_checkpoint(problem).to_dict()] * 2
    for index in range(len(paths["reference"]["entries"])):
        steps = []
        for ai, arm in enumerate(["reference", candidate]):
            p = paths[arm]
            entry = p["entries"][index]
            check(
                entry["target_index"] == index
                and len(entry["invocations"]) == 1
                and entry["invocations"][0]["committed"],
                "original invocation",
            )
            step = checked(read(study / arm / f"{index:03d}-1-step.json"), "step_hash")
            check(
                step["committed"]
                and step["step_hash"]
                == p["response_history"][index]["source_step_hash"],
                "step history binding",
            )
            if previous[ai] is not None:
                check(step["parent_checkpoint"] == previous[ai], "native parent chain")
            previous[ai] = step["accepted_checkpoint"]
            check(
                step["parent_checkpoint"]["problem_contract_hash"]
                == problem.contract_hash,
                "native problem",
            )
            load(canonical(step["parent_checkpoint"]), problem)
            work["native_parent_checkpoint_loads"] += 1
            check(
                entry["parent_hash"] == step["parent_checkpoint"]["state_hash"],
                "entry parent",
            )
            metrics = step["trial_solution"]["metrics"]
            check(
                all(
                    metrics[k] is True
                    for k in [
                        "contract_pass",
                        "increment_gate_passed",
                        "residual_gate_passed",
                    ]
                ),
                "Newton gates",
            )
            check(
                all(
                    step["metrics"][k] is True
                    for k in [
                        "equilibrium_gate_passed",
                        "control_gate_passed",
                        "parent_checkpoint_immutable",
                        "solver_assembly_coordinate_residual_binding_passed",
                        "section_and_element_parent_binding_passed",
                    ]
                ),
                "original binding gates",
            )
            check(
                entry["invocations"][0]["work"]
                == {
                    "core_calls": 1,
                    "newton_iterations": metrics["iteration_count"],
                    "linear_solves": metrics["linear_solve_count"],
                },
                "original work counts",
            )
            for parent, accepted, row in zip(
                step["parent_checkpoint"]["element_states"],
                step["accepted_checkpoint"]["element_states"],
                step["trial_assembly"]["member_assemblies"],
                strict=True,
            ):
                er = row["element_response"]
                check(
                    er["parent_state_hash"] == parent["state_hash"]
                    and er["trial_state"] == accepted,
                    "accepted element binding",
                )
            verification = verifier.verify_assembly(problem, step["trial_assembly"])
            work["assembly_verifier_material_integrations"] += verification.pop(
                "material_integrations"
            )
            work.update(verification)
            work["original_assembly_verifications"] += 1
            steps.append(step)
        fields = trial_fields(problem, steps, work)
        saved = [
            originals(
                compiled, step, paths[arm]["response_history"][index], fields[0][ai][ai]
            )
            for ai, (arm, step) in enumerate(
                zip(["reference", candidate], steps, strict=True)
            )
        ]
        for key in sorted(saved[0][0]):
            finite = [[fields[0][p][q][key] for q in range(2)] for p in range(2)]
            high = [[fields[1][p][q][key] for q in range(2)] for p in range(2)]
            external = [s[1].get(key, F()) for s in saved]
            actual = [s[0][key] for s in saved]
            orders = decompose(
                finite, high, actual[1] - actual[0], external[1] - external[0]
            )
            values = {
                "original": list(map(float, actual)),
                "unrounded_stress_counterfactual": [
                    float(high[i][i] - external[i]) for i in range(2)
                ],
            }
            failed = {
                name: abs(b - a)
                > identity["absolute_tolerance"]
                + identity["relative_tolerance"] * max(abs(a), abs(b))
                for name, (a, b) in values.items()
            }
            rows.append(
                {
                    "target_index": index,
                    "field": key,
                    "values_si": values,
                    "comparison_failed": failed,
                    "difference_si": float(actual[1] - actual[0]),
                    "orders": {
                        name: {k: float(v) for k, v in terms.items()}
                        for name, terms in orders.items()
                    },
                    "exact_rational_decompositions_close": True,
                    **(
                        {
                            "failed_exact_components": {
                                name: {
                                    k: [str(v.numerator), str(v.denominator)]
                                    for k, v in terms.items()
                                }
                                for name, terms in orders.items()
                            }
                        }
                        if failed["original"]
                        else {}
                    ),
                }
            )
    for ai, arm in enumerate(["reference", candidate]):
        check(
            previous[ai] == paths[arm]["terminal_checkpoint"], "terminal native chain"
        )
        raw = canonical(previous[ai])
        check(dump(problem, load(raw, problem)) == raw, "terminal native reopen")
        work["native_reopens"] += 1
    for path, digest in inputs.items():
        check(
            hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            "input changed during diagnostic",
        )
    work["total_material_integrate_entries"] = (
        work["selected_material_trial_calls"] + work["nested_original_base_calls"]
    )
    return {
        "schema_version": "rc-rational-history-attribution.v2",
        "original_source_revision": identity["source_revision"],
        "compiled_problem_contract_hash": problem.contract_hash,
        "target_count": len(paths["reference"]["entries"]),
        "candidate": candidate,
        "rows": rows,
        "work": dict(work),
        "wall_ns": perf_counter_ns() - start,
        "input_files": [
            {"path": str(p.resolve()), "sha256": h} for p, h in inputs.items()
        ],
        "full_original_mismatch_locations": mismatch,
        "scope": "two ordered rational-coordinate/native-parent counterfactuals with independent 100-digit stress expressions; original rounded native branch updates retained",
        "claims": {
            "unique_causal_attribution": False,
            "repaired_solver": False,
            "independent_validation": False,
            "accepted_force_replacement": False,
        },
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", choices=["secant", "proposal"], default="secant")
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(
        args.study.resolve()
    ):
        parser.error("output must be new and outside the original study")
    result = diagnose(args.study, args.candidate)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("rows", "input_files", "full_original_mismatch_locations")
            }
        )
    )


if __name__ == "__main__":
    main()
