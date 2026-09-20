"""Read-only integrity and cost audit of a complete adaptive recovery campaign.

Known failed native paths remain failures. No solver is run, clocks are not
independently authenticated, and this does not qualify physical accuracy.
"""

import argparse
from fnmatch import fnmatch
import json
from pathlib import Path

from scripts.run_rc_adaptive_continuation_campaign import campaign_plan, prepare_cases
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark.rc_control_continuation_replay import _read_study
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
)
from structural_analysis.benchmark.rc_control_frozen_continuation import (
    FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY,
    ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
)
from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    load_stateful_fiber_frame2d_checkpoint_bytes,
    _artifact_json_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive_int(value, description):
    _require(
        type(value) is int and value > 0, "positive integer required: " + description
    )


def _read_object(path, root):
    _require(
        not path.is_symlink() and path.resolve().is_relative_to(root),
        "local original artifact required",
    )
    _require(
        path.stat().st_size <= 16 * 1024**2, "campaign metadata byte budget exceeded"
    )
    return strict_json_object_bytes(path.read_bytes(), maximum_bytes=16 * 1024**2)


def _artifact_bytes(path, root):
    _require(
        not path.is_symlink() and path.resolve().is_relative_to(root),
        "local trial artifact required",
    )
    _require(
        not any(
            fnmatch(path.name, pattern)
            for pattern in (".env", ".env.*", "*.env", "*.env.*")
        ),
        "unsupported artifact filename",
    )
    _require(
        path.stat().st_size <= 256 * 1024**2, "trial artifact byte budget exceeded"
    )
    return path.read_bytes()


def _nonnegative_int(value, description):
    _require(
        type(value) is int and value >= 0,
        "nonnegative integer required: " + description,
    )


def _check_invocation(invocation, native):
    metrics = native["trial_solution"]["metrics"]
    expected = {
        "core_calls": 1,
        "newton_iterations": metrics["iteration_count"],
        "linear_solves": metrics["linear_solve_count"],
    }
    _require(invocation["work"] == expected, "ordinary work differs from native result")
    if "committed" in invocation:
        _require(
            invocation["committed"] == native["committed"],
            "native commit status mismatch",
        )


def _check_path_evidence(data, name, path, request):
    _require(
        path["requested_targets_m"] == list(request.targets_m),
        "original target sequence required",
    )
    _nonnegative_int(path["accepted_target_count"], "accepted target count")
    _require(
        path["accepted_target_count"]
        == len(path["response_history"])
        <= len(request.targets_m),
        "accepted history length mismatch",
    )
    _require(
        (path["status"] == "complete")
        == (
            path["failure"] is None
            and len(path["response_history"]) == len(request.targets_m)
        ),
        "complete path status contradicts original history",
    )
    prefix = data[name + "/preload-step.json"]
    _require(len(path["preload_invocations"]) == 1, "one original preload required")
    _check_invocation(path["preload_invocations"][0], prefix)
    previous = (
        prefix["accepted_checkpoint"]
        if prefix["committed"]
        else prefix["parent_checkpoint"]
    )
    accepted = 0
    for index, entry in enumerate(path["entries"]):
        _require(
            entry["target_index"] == index
            and entry["target_m"] == request.targets_m[index],
            "ordered original target entry required",
        )
        _require(
            entry["parent_hash"] == previous["state_hash"],
            "outer material parent changed",
        )
        committed = None
        for ordinal, invocation in enumerate(entry["invocations"], 1):
            _require(committed is None, "no invocation after an accepted native solve")
            _require(
                invocation["ordinal"] == ordinal,
                "contiguous original invocation order required",
            )
            native = data[f"{name}/{index:03d}-{ordinal}-step.json"]
            _check_invocation(invocation, native)
            _require(
                native["parent_checkpoint"] == previous,
                "invocation parent differs from outer state",
            )
            _require(
                native["metrics"]["target_control_displacement_m"]
                == request.targets_m[index],
                "native target differs from original request",
            )
            if native["committed"]:
                committed = native
        if committed is not None and accepted < len(path["response_history"]):
            response = path["response_history"][accepted]
            _require(
                response["source_step_hash"] == committed["step_hash"]
                and response["parent_checkpoint_hash"] == previous["state_hash"]
                and response["checkpoint_hash"]
                == committed["accepted_checkpoint"]["state_hash"],
                "response is not bound to original committed step",
            )
            previous = committed["accepted_checkpoint"]
            accepted += 1
    _require(
        accepted == len(path["response_history"])
        and path["terminal_checkpoint"] == previous,
        "terminal checkpoint or accepted responses mismatch",
    )


def _check_directory(path, root):
    _require(
        path.is_dir() and not path.is_symlink() and path.resolve().is_relative_to(root),
        "local comparison directory required",
    )
    for item in path.rglob("*.json"):
        _require(
            not any(
                fnmatch(item.name, pattern)
                for pattern in (".env", ".env.*", "*.env", "*.env.*")
            ),
            "unsupported artifact filename",
        )


def audit(campaign_directory):
    try:
        return _audit(campaign_directory)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("incomplete or invalid campaign schema") from exc


def _audit(campaign_directory):
    study = Path(campaign_directory).resolve()
    plan = _read_object(study / "campaign-plan.json", study)
    outcome = _read_object(study / "campaign-outcome.json", study)
    revision = plan["source_revision"]
    cases = prepare_cases()
    _require(
        plan == campaign_plan(revision, cases),
        "Invalid campaign evidence: plan == campaign_plan(revision, cases)",
    )
    _require(
        outcome["plan_hash"] == plan["plan_hash"],
        "Invalid campaign evidence: outcome['plan_hash'] == plan['plan_hash']",
    )
    body = {k: v for (k, v) in outcome.items() if k != "outcome_hash"}
    _require(
        _sha(_bytes(body)) == outcome["outcome_hash"],
        "Invalid campaign evidence: _sha(_bytes(body)) == outcome['outcome_hash']",
    )
    _require(
        outcome["observations_complete"] is True,
        "Invalid campaign evidence: outcome['observations_complete']",
    )
    _require(
        len(outcome["rows"]) == len(cases) * 4,
        "Invalid campaign evidence: len(outcome['rows']) == len(cases) * 4",
    )
    _require(
        {(r["case_id"], r["repeat"], r["mode"]) for r in outcome["rows"]}
        == {
            (name, r, m)
            for (name, _, _) in cases
            for r in range(2)
            for m in ("fixed", "adaptive")
        },
        "Invalid campaign evidence: {(r['case_id'], r['repeat'], r['mode']) for r in outcome['rows']} == {(name, r, m) for (name, _, _) in cases for r in range(2) for m in ('fixed', 'adaptive')}",
    )
    inputs = {name: (m, q) for (name, m, q) in cases}
    studies = {}
    totals = dict(
        paths=0,
        complete_paths=0,
        ordinary_native_calls=0,
        additional_native_calls=0,
        ordinary_newton=0,
        additional_newton=0,
        ordinary_linear_solves=0,
        additional_linear_solves=0,
    )

    def history(path):
        return (
            [path["preload_response"]]
            if path.get("preload_response") is not None
            else []
        ) + path["response_history"]

    for row in outcome["rows"]:
        (name, repeat, mode) = (row["case_id"], row["repeat"], row["mode"])
        identity = f"{name}-r{repeat}-{mode}"
        _require(
            row["status"] == "returned" and (not row["unknown_work"]),
            "Invalid campaign evidence: row['status'] == 'returned' and (not row['unknown_work'])",
        )
        _require(
            _read_object(study / (identity + "-outcome.json"), study) == row,
            "Invalid campaign evidence: _read_object(study / (identity + '-outcome.json'), study) == row",
        )
        _check_directory(study / identity, study)
        data = _read_study(study / identity)
        p = data["comparison.json"]
        (model, q) = inputs[name]
        _require(
            p["report_hash"] == row["report_hash"] and p["source_revision"] == revision,
            "Invalid campaign evidence: p['report_hash'] == row['report_hash'] and p['source_revision'] == revision",
        )
        _require(
            p["request"] == q.to_dict()
            and p["model_checksum"] == model.canonical_model_checksum,
            "Invalid campaign evidence: p['request'] == q.to_dict() and p['model_checksum'] == model.canonical_model_checksum",
        )
        _require(
            p["all_execution_work_reported"],
            "Invalid campaign evidence: p['all_execution_work_reported']",
        )
        _require(
            p["absolute_tolerance"] == 1e-10 and p["relative_tolerance"] == 1e-08,
            "Invalid campaign evidence: p['absolute_tolerance'] == 1e-10 and p['relative_tolerance'] == 1e-08",
        )
        _require(
            p["numerical_proposal"]["identity"]
            == (
                ADAPTIVE_FROZEN_CONTINUATION_IDENTITY
                if mode == "adaptive"
                else FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY
            ),
            "Invalid campaign evidence: p['numerical_proposal']['identity'] == (ADAPTIVE_FROZEN_CONTINUATION_IDENTITY if mode == 'adaptive' else FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY)",
        )
        _require(
            p["numerical_proposal"]["maximum_additional_native_calls"]
            == (64 if mode == "adaptive" else 16) * len(q.targets_m),
            "Invalid campaign evidence: p['numerical_proposal']['maximum_additional_native_calls'] == (64 if mode == 'adaptive' else 16) * len(q.targets_m)",
        )
        _require(
            p["arm_order"] == plan["arm_orders"][repeat]
            and set(p["arms"]) == {"reference", "secant", "proposal"},
            "predeclared arm order and roster required",
        )
        _require(
            p["schema_version"] == "experimental-rc-control-seed-comparison.v2",
            "complete path comparison schema required",
        )
        for field, default in {
            "coordinate_precision": "binary64",
            "strain_evaluation": "matrix",
            "material_arithmetic": "binary64",
            "fiber_strain_evaluation": "generalized",
            "force_accumulation": "binary64",
            "terminal_coordinate_precision": "binary64",
        }.items():
            _require(
                p.get(field, default) == default,
                "predeclared binary64 arithmetic required",
            )
        arms = {**p["arms"], "fresh-reference": p["fresh_reference"]}
        fresh = data["fresh-reference/path.json"]
        for armname, arm in arms.items():
            raw = data[armname + "/path.json"]
            _positive_int(raw["wall_ns"], "path wall time")
            _require(
                {
                    k: v
                    for (k, v) in raw.items()
                    if k
                    not in (
                        "response_history",
                        "terminal_checkpoint",
                        "preload_response",
                    )
                }
                == arm,
                "Invalid campaign evidence: {k: v for (k, v) in raw.items() if k not in ('response_history', 'terminal_checkpoint', 'preload_response')} == arm",
            )
            _require(
                arm["status"] == row["arm_statuses"][armname],
                "Invalid campaign evidence: arm['status'] == row['arm_statuses'][armname]",
            )
            _require(
                p["assembly_phase_work"][armname]["source_path_hash"]
                == raw["path_hash"],
                "Invalid campaign evidence: p['assembly_phase_work'][armname]['source_path_hash'] == raw['path_hash']",
            )
            if armname != "fresh-reference":
                (structure, _, _, within) = _numeric_payload_difference(
                    history(fresh),
                    history(raw),
                    absolute_tolerance=1e-10,
                    relative_tolerance=1e-08,
                )
                _require(
                    p["comparisons"][armname]["full_history_pass"]
                    == (
                        fresh["status"] == raw["status"] == "complete"
                        and structure
                        and within
                    ),
                    "Invalid campaign evidence: p['comparisons'][armname]['full_history_pass'] == (fresh['status'] == raw['status'] == 'complete' and structure and within)",
                )
            _check_path_evidence(data, armname, raw, q)
            inv = arm.get("preload_invocations", []) + [
                i for e in arm["entries"] for i in e["invocations"]
            ]
            _require(
                all((not i["unknown_work"] and i["work"] for i in inv)),
                "Invalid campaign evidence: all((not i['unknown_work'] and i['work'] for i in inv))",
            )
            for item in inv:
                _positive_int(item["work"]["core_calls"], "native core calls")
                for counter in ("newton_iterations", "linear_solves"):
                    _nonnegative_int(item["work"][counter], counter)
            totals["ordinary_linear_solves"] += sum(
                i["work"]["linear_solves"] for i in inv
            )
            totals["paths"] += 1
            totals["complete_paths"] += arm["status"] == "complete"
            totals["ordinary_native_calls"] += sum(
                (i["work"]["core_calls"] for i in inv)
            )
            totals["ordinary_newton"] += sum(
                (i["work"]["newton_iterations"] for i in inv)
            )
        work = p["numerical_proposal_work"]
        for counter in (
            "native_core_calls_attempted",
            "known_newton_iterations",
            "known_linear_solves",
        ):
            _nonnegative_int(work[counter], counter)
        stages = [
            s
            for e in p["arms"]["proposal"]["entries"]
            for s in e["numerical_proposal"].get("stages", [])
        ]
        _require(
            not work["unknown_work"],
            "Invalid campaign evidence: not work['unknown_work']",
        )
        _require(
            work["native_core_calls_attempted"] == len(stages),
            "Invalid campaign evidence: work['native_core_calls_attempted'] == len(stages)",
        )
        _require(
            work["known_newton_iterations"]
            == sum((s["newton_iterations"] for s in stages)),
            "Invalid campaign evidence: work['known_newton_iterations'] == sum((s['newton_iterations'] for s in stages))",
        )
        _require(
            work["known_linear_solves"] == sum(s["linear_solves"] for s in stages),
            "additional linear-solve work mismatch",
        )
        (compiled, unsupported, _) = api._compile(model)
        _require(not unsupported, "Invalid campaign evidence: not unsupported")
        compiled = api._with_constant_loading(compiled, q.constant_nodal_loads)
        for entry in p["arms"]["proposal"]["entries"]:
            parent = None
            seed = None
            fraction = 0.0
            increment = 1 / 16
            if entry["numerical_proposal"].get("stages"):
                _require(
                    not entry["invocations"][0]["committed"]
                    and entry["invocations"][0]["rollback_exact"],
                    "Invalid campaign evidence: not entry['invocations'][0]['committed'] and entry['invocations'][0]['rollback_exact']",
                )
            for index, stage in enumerate(
                entry["numerical_proposal"].get("stages", [])
            ):
                ref = stage["artifact"]
                b = _artifact_bytes(
                    study / identity / "proposal" / ref["path"],
                    study / identity / "proposal",
                )
                _require(
                    len(b) == ref["byte_length"] and _sha(b) == ref["sha256"],
                    "Invalid campaign evidence: len(b) == ref['byte_length'] and _sha(b) == ref['sha256']",
                )
                native = data["proposal/" + ref["path"]]
                for reported, original in (
                    ("newton_iterations", "newton_iteration_count"),
                    ("linear_solves", "linear_solve_count"),
                ):
                    _nonnegative_int(stage[reported], reported)
                    _require(
                        stage[reported]
                        == native["trial_solution"]["metrics"][original],
                        "trial work differs from native result",
                    )
                _require(
                    native["committed"] == stage["committed"],
                    "Invalid campaign evidence: native['committed'] == stage['committed']",
                )
                _require(
                    native["parent_checkpoint"]["state_hash"] == entry["parent_hash"],
                    "Invalid campaign evidence: native['parent_checkpoint']['state_hash'] == entry['parent_hash']",
                )
                _require(
                    stage["parent_hash"] == entry["parent_hash"],
                    "Invalid campaign evidence: stage['parent_hash'] == entry['parent_hash']",
                )
                if parent is None:
                    parent = native["parent_checkpoint"]
                else:
                    _require(
                        native["parent_checkpoint"] == parent,
                        "Invalid campaign evidence: native['parent_checkpoint'] == parent",
                    )
                if seed is None:
                    checkpoint = load_stateful_fiber_frame2d_checkpoint_bytes(
                        _artifact_json_bytes(parent), compiled.problem
                    )
                    adapter = Adapter(
                        compiled.problem,
                        checkpoint,
                        q.control_global_dof,
                        entry["target_m"],
                        q.solver_config,
                    )
                    seed = list(
                        adapter.absolute_coordinates(
                            adapter.initial_free_displacements_m()
                        )[0]
                    )
                _require(
                    native["metrics"]["initial_augmented_coordinates_m"] == seed,
                    "Invalid campaign evidence: native['metrics']['initial_augmented_coordinates_m'] == seed",
                )
                if mode == "adaptive":
                    _require(
                        stage["last_accepted_fraction"] == fraction
                        and stage["fraction_increment"] == increment,
                        "Invalid campaign evidence: stage['last_accepted_fraction'] == fraction and stage['fraction_increment'] == increment",
                    )
                    _require(
                        stage["fraction"] == min(1.0, fraction + increment),
                        "Invalid campaign evidence: stage['fraction'] == min(1.0, fraction + increment)",
                    )
                    if native["committed"]:
                        fraction = stage["fraction"]
                        increment = min(1 / 16, increment * 2)
                    else:
                        increment /= 2
                if native["committed"]:
                    seed = native["trial_solution"]["augmented_coordinates_m"]
            _require(
                len(entry["numerical_proposal"].get("stages", []))
                <= (64 if mode == "adaptive" else 16),
                "Invalid campaign evidence: len(entry['numerical_proposal'].get('stages', [])) <= (64 if mode == 'adaptive' else 16)",
            )
        totals["additional_native_calls"] += work["native_core_calls_attempted"]
        totals["additional_newton"] += work["known_newton_iterations"]
        totals["additional_linear_solves"] += work["known_linear_solves"]
        studies[name, repeat, mode] = {
            "comparison.json": p,
            "proposal/path.json": data["proposal/path.json"],
        }
    _require(
        totals["paths"] == plan["planned_paths"],
        "complete original path roster required",
    )
    _require(
        totals["complete_paths"] == outcome["completed_paths"],
        "Invalid campaign evidence: totals['complete_paths'] == outcome['completed_paths']",
    )
    _require(
        totals["ordinary_native_calls"] + totals["additional_native_calls"]
        <= plan["maximum_native_calls_conservative"],
        "Invalid campaign evidence: totals['ordinary_native_calls'] + totals['additional_native_calls'] <= plan['maximum_native_calls_conservative']",
    )
    case_rows = []
    for name, model, q in cases:
        repeats = {}
        clocks = {}
        counts = {}
        completion = {}
        fresh_gates = {}
        matches = []
        for mode in ("fixed", "adaptive"):
            ds = [studies[name, r, mode] for r in range(2)]
            paths = [d["proposal/path.json"] for d in ds]
            completion[mode] = [p["status"] == "complete" for p in paths]
            repeats[mode] = all(completion[mode]) and all(
                (
                    paths[0][f] == paths[1][f]
                    for f in (
                        "preload_response",
                        "response_history",
                        "terminal_checkpoint",
                    )
                )
            )
            clocks[mode] = sum((p["wall_ns"] for p in paths))
            counts[mode] = sum(
                (
                    d["comparison.json"]["numerical_proposal_work"][
                        "native_core_calls_attempted"
                    ]
                    for d in ds
                )
            )
            fresh_gates[mode] = [
                d["comparison.json"]["comparisons"]["proposal"]["full_history_pass"]
                for d in ds
            ]
        for r in range(2):
            a = studies[name, r, "fixed"]["proposal/path.json"]
            b = studies[name, r, "adaptive"]["proposal/path.json"]
            (same, _, _, within) = _numeric_payload_difference(
                history(a),
                history(b),
                absolute_tolerance=1e-10,
                relative_tolerance=1e-08,
            )
            matches.append(a["status"] == b["status"] == "complete" and same and within)
        qualified = (
            all(matches)
            and all(repeats.values())
            and all((all(v) for v in fresh_gates.values()))
        )
        case_rows.append(
            {
                "case_id": name,
                "complete": completion,
                "complete_repeats_exact": repeats,
                "paired_complete_histories_match": matches,
                "fresh_reference_gates": fresh_gates,
                "summed_proposal_wall_ns": clocks,
                "additional_native_calls": counts,
                "adaptive_over_fixed_ratio": clocks["adaptive"] / clocks["fixed"]
                if qualified
                else None,
            }
        )
    result = {
        "schema_version": "synthetic-adaptive-rc-recovery-audit.v1",
        "source_revision": revision,
        "source_revision_is_attestation": True,
        "totals": totals,
        "cases": case_rows,
        "policy_promoted": False,
        "independent_physical_validation": False,
        "numerical_reexecution_performed": False,
        "original_execution_clocks_authenticated": False,
    }
    result["audit_hash"] = _sha(_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root, output = args.campaign_directory.resolve(), args.output.resolve()
    _require(not output.is_relative_to(root), "separate audit output required")
    result = audit(root)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}))


if __name__ == "__main__":
    main()
