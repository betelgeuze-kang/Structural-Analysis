"""Attribute saved RC section differences without a Newton solve or state commit.

The two telescoping orders expose nonlinear parent/strain interactions. Results
are local counterfactual material evaluations, never replacement solver evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    _restore_section_state,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_strain_evaluation,
    _with_coordinate_precision,
    _with_material_arithmetic,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def exact_coordinate_strain(local, length, xi, compensation=None):
    """Exact rational Hermite strain of finite inputs, rounded once to binary64."""
    values = [*local, length, xi]
    if (
        len(local) != 6
        or any(isinstance(v, (bool, np.bool_)) or not math.isfinite(v) for v in values)
        or length <= 0
        or not -1 <= xi <= 1
    ):
        raise ValueError(
            "six finite coordinates, positive length and bounded xi required"
        )
    u = [Fraction(float(v)) for v in local]
    if compensation is not None:
        if len(compensation) != 6 or not all(math.isfinite(v) for v in compensation):
            raise ValueError("six finite coordinate compensation values required")
        u = [
            value + Fraction(float(low))
            for value, low in zip(u, compensation, strict=True)
        ]

    length, xi = Fraction(float(length)), Fraction(float(xi))
    slope = (u[4] - u[1]) / length
    return np.array(
        [
            float((u[3] - u[0]) / length),
            float(
                ((3 * xi - 1) * (u[2] - slope) + (3 * xi + 1) * (u[5] - slope)) / length
            ),
        ]
    )


def attribute_section(
    section,
    reference_parent,
    candidate_parent,
    reference_strain,
    candidate_strain,
    reference_exact_strain,
    candidate_exact_strain,
):
    """Eight real material integrations, retaining both attribution orders."""
    parents = [reference_parent, candidate_parent]
    before = [canonical(p.to_dict()) for p in parents]
    responses = [
        [
            section.integrate(g, p)
            for g in (
                reference_strain,
                reference_exact_strain,
                candidate_exact_strain,
                candidate_strain,
            )
        ]
        for p in parents
    ]
    if before != [canonical(p.to_dict()) for p in parents]:
        raise ValueError("diagnostic material evaluation mutated a saved parent")
    # kN/kNm -> N/Nm, matching the original full-history comparison fields.
    values = [[r.resultants * 1000 for r in row] for row in responses]
    orders = {}
    for name, links in {
        "reference_parent_then_history": [
            ("reference_kinematic_evaluation", (0, 0), (0, 1)),
            ("finite_coordinate_difference", (0, 1), (0, 2)),
            ("candidate_kinematic_evaluation", (0, 2), (0, 3)),
            ("parent_history_difference", (0, 3), (1, 3)),
        ],
        "history_then_candidate_parent": [
            ("parent_history_difference", (0, 0), (1, 0)),
            ("reference_kinematic_evaluation", (1, 0), (1, 1)),
            ("finite_coordinate_difference", (1, 1), (1, 2)),
            ("candidate_kinematic_evaluation", (1, 2), (1, 3)),
        ],
    }.items():
        components = {}
        for key, (a, b), (c, d) in links:
            components[key] = [
                float(Fraction(float(y)) - Fraction(float(x)))
                for x, y in zip(values[a][b], values[c][d], strict=True)
            ]
        delta = values[1][3] - values[0][0]
        closure = [
            math.fsum(v[i] for v in components.values()) - float(delta[i])
            for i in range(2)
        ]
        orders[name] = {
            "components_N_Nm": components,
            "serialized_sum_residual_N_Nm": closure,
        }
    return {
        "original_reference_response": responses[0][0].to_dict(),
        "original_candidate_response": responses[1][3].to_dict(),
        "reference_resultants_N_Nm": values[0][0].tolist(),
        "candidate_resultants_N_Nm": values[1][3].tolist(),
        "difference_N_Nm": (values[1][3] - values[0][0]).tolist(),
        "orders": orders,
        "section_integrations": 8,
        "fiber_integrations": 8 * len(section.fibers),
    }


def diagnose(study: Path, candidate: str):
    if candidate not in {"secant", "proposal"}:
        raise ValueError("candidate must be secant or proposal")
    start, cpu = perf_counter_ns(), process_time_ns()
    reads = []

    def read(path):
        raw = path.read_bytes()
        reads.append(
            {
                "path": str(path.resolve()),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        return json.loads(raw)

    model_path = study / "model.json"
    read(model_path)
    compiled, blockers, _ = public._compile(load_neutral_json(model_path))
    if compiled is None or blockers:
        raise ValueError("supported original RC model required")
    identity = read(study / "request.json")
    if identity.get("fiber_strain_evaluation", "generalized") != "generalized":
        raise ValueError(
            "this diagnostic requires the generalized fiber strain profile"
        )
    strain_evaluation = identity.get("strain_evaluation", "matrix")
    compiled = _with_strain_evaluation(compiled, strain_evaluation)
    coordinate_precision = identity.get("coordinate_precision", "binary64")
    compiled = _with_coordinate_precision(compiled, coordinate_precision)
    material_arithmetic = identity.get("material_arithmetic", "binary64")
    compiled = _with_material_arithmetic(compiled, material_arithmetic)
    if (
        strain_evaluation != "matrix" or material_arithmetic != "binary64"
    ) and identity.get(
        "compiled_problem_contract_hash"
    ) != compiled.problem.contract_hash:
        raise ValueError("declared strain evaluation contract differs")
    members = {m.member_id: m for m in compiled.problem.members}
    paths = {arm: read(study / arm / "path.json") for arm in ["reference", candidate]}
    for path in paths.values():
        payload = dict(path)
        identity = payload.pop("path_hash")
        if identity != "sha256:" + hashlib.sha256(canonical(payload)).hexdigest():
            raise ValueError("original path hash differs")
        if not path["entries"] or path["accepted_target_count"] != len(path["entries"]):
            raise ValueError("nonempty complete original target roster required")
    if any(p["status"] != "complete" for p in paths.values()):
        raise ValueError("complete original paths required")
    entries = [p["entries"] for p in paths.values()]
    rows, totals, mismatch = [], Counter(), Counter()
    for re, ce in zip(*entries, strict=True):
        if (re["target_index"], re["target_m"]) != (ce["target_index"], ce["target_m"]):
            raise ValueError("original target schedules differ")
        index = re["target_index"]
        if any(
            len(e["invocations"]) != 1 or not e["invocations"][0]["committed"]
            for e in [re, ce]
        ):
            raise ValueError("one committed invocation per target required")
        steps = [
            read(study / arm / f"{index:03d}-1-step.json")
            for arm in ["reference", candidate]
        ]
        if any(
            not s["committed"]
            or s["parent_checkpoint"]["problem_contract_hash"]
            != compiled.problem.contract_hash
            for s in steps
        ):
            raise ValueError("original committed problem binding differs")
        assemblies = [
            {
                m["member_id"]: m["element_response"]
                for m in s["trial_assembly"]["member_assemblies"]
            }
            for s in steps
        ]
        parent_states = [
            {e["element_id"]: e for e in s["parent_checkpoint"]["element_states"]}
            for s in steps
        ]
        for mid, member in members.items():
            element = member.element
            template = element.section.initial_state()
            a, b = [assembly[mid] for assembly in assemblies]
            for point, xi in enumerate(element.quadrature[0]):
                if (
                    a["integration_point_xi"][point] != xi
                    or b["integration_point_xi"][point] != xi
                ):
                    raise ValueError("original quadrature differs")
                parents = [
                    _restore_section_state(
                        template,
                        p[mid]["integration_point_states"][point],
                        path=f"{index}/{mid}/{point}",
                    )
                    for p in parent_states
                ]
                original = [e["section_responses"][point] for e in [a, b]]
                exact = [
                    exact_coordinate_strain(
                        e["local_displacements"],
                        element.length_m,
                        xi,
                        e.get("local_displacement_compensation"),
                    )
                    for e in [a, b]
                ]
                result = attribute_section(
                    element.section,
                    *parents,
                    a["generalized_strains"][point],
                    b["generalized_strains"][point],
                    *exact,
                )
                for key, expected in zip(
                    ["original_reference_response", "original_candidate_response"],
                    original,
                    strict=True,
                ):
                    if canonical(result.pop(key)) != canonical(expected):
                        raise ValueError(
                            f"original section replay differs: {index}/{mid}/{point}"
                        )
                failed = [
                    abs(x - y) > 1e-10 + 1e-8 * max(abs(x), abs(y))
                    for x, y in zip(
                        result["reference_resultants_N_Nm"],
                        result["candidate_resultants_N_Nm"],
                        strict=True,
                    )
                ]
                for field, fail in zip(
                    ["axial_force_N", "moment_z_Nm"], failed, strict=True
                ):
                    mismatch[field] += fail
                totals["original_section_responses_verified"] += 2
                totals["section_integrations"] += result["section_integrations"]
                totals["fiber_integrations"] += result["fiber_integrations"]
                rows.append(
                    {
                        "target_index": index,
                        "member_id": mid,
                        "integration_point_index": point,
                        "original_comparison_failed": failed,
                        "exact_coordinate_generalized_strains": [
                            g.tolist() for g in exact
                        ],
                        **result,
                    }
                )
    for item in reads:
        raw = Path(item["path"]).read_bytes()
        if (
            len(raw) != item["bytes"]
            or hashlib.sha256(raw).hexdigest() != item["sha256"]
        ):
            raise ValueError("original input changed during diagnosis")
    return {
        "schema_version": "rc-control-section-error-attribution.v1",
        "scope": "two order-dependent telescoping decompositions of original section resultants; counterfactual material evaluation only",
        "candidate": candidate,
        "strain_evaluation": strain_evaluation,
        "coordinate_precision": coordinate_precision,
        "material_arithmetic": material_arithmetic,
        "input_files": reads,
        "target_count": len(entries[0]),
        "work": {
            "model_compilations": 1,
            "integration_counts_scope": "eight explicit attribution evaluations per integration point; model compilation and state decoding are separately timed within whole wall/cpu",
            "newton_solves": 0,
            "state_commits": 0,
            **totals,
        },
        "original_section_mismatches": dict(mismatch),
        "rows": rows,
        "wall_ns": perf_counter_ns() - start,
        "cpu_ns": process_time_ns() - cpu,
        "claims": {
            "unique_causal_attribution": False,
            "exact_continuum_solution": False,
            "repaired_solver": False,
            "independent_validation": False,
        },
    }


def main():
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
