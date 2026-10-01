"""Pinned original-file joins for reference-parent-conditioned cost-gate folds.

This reader rebuilds labels and tables; caller-supplied scores are not authority.
Pins establish correspondence, not signed producer/hardware authenticity or data
admission. It writes nothing, fits nothing and executes no structural solves.
"""

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _physical_mismatch_locations,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
)
from structural_analysis.benchmark.rc_control_prior_work_export import (
    _Reader,
    _context,
    _invocations,
    build_generation_prior_work_export,
)
from structural_analysis.benchmark.rc_control_material_features import (
    decode_material_snapshot,
)
from structural_analysis.ai.fiber_frame_warm_start_features import (
    decode_fiber_frame_warm_start_model_features,
)

from audit_rc_nested_switch_labels import label_from_repetitions
from plan_rc_gate_inner_validation import inner_validation_plan
from prepare_rc_nested_switch_labels import nested_plan, require
from rc_connected_split_provenance import (
    require_exact_seed_policy_complement,
    validate_inner_validation_provenance,
)
from rc_gate_validation_rows import assemble_fold
from rc_prior_work_cost_margin_gate import (
    JOIN_PROFILE,
    append_prior_work_inputs,
    fit_prior_work_cost_gate,
    _checked_row_inputs,
)
from rc_switch_prefix_features import prefix_features
from run_rc_nested_switch_labels import LABEL_RULE


PROFILE = "rc-original-policy-prior-work-fold.v1"
_ARMS = ("reference", "secant", "proposal")
_ORDER = [list(_ARMS[i:] + _ARMS[:i]) for i in range(3)]
_ANCHORS = {
    "generation-plan",
    "generation-samples",
    "generation-export",
    "new-seed-plan",
    "new-seed-receipts",
    "retained-seed-plan",
    "retained-seed-receipts",
    "new-label-plan",
    "new-label-outcome",
    "retained-label-plan",
    "retained-label-outcome",
}


@dataclass(frozen=True)
class OriginalSeedStage:
    root: Path
    plan_path: str = "plan.json"
    policy_prefix: str = "seeds"
    receipt_path: str = "seeds/fit-receipts.json"


def _same(left, right, reason):
    require(_bytes(left) == _bytes(right), reason)


def _natural(value, reason):
    require(type(value) is int and value >= 0, reason)
    return value


def _read(reader, path, artifacts, *, pin=None, array=False):
    raw, value = reader.read(path, artifacts, array=array)
    if pin is not None:
        _same(artifacts[path], pin, "predeclared original artifact pin differs")
    return raw, value


def _checked_hash(value, field):
    require(
        value[field] == _sha(_bytes({k: v for k, v in value.items() if k != field})),
        "original self-hash differs",
    )


def _generation(root, cases, anchors):
    reader, artifacts = _Reader(root), {}
    _, plan = _read(reader, "plan.json", artifacts, pin=anchors["generation-plan"])
    _, samples = _read(
        reader,
        "training-samples.json",
        artifacts,
        pin=anchors["generation-samples"],
        array=True,
    )
    _, original = _read(
        reader,
        "generation-prior-work-export.json",
        artifacts,
        pin=anchors["generation-export"],
    )
    require(
        type(cases) in (list, tuple)
        and 2 <= len(cases) <= 32
        and all(type(case) is learning.RCControlLearningCase for case in cases),
        "typed original case roster required",
    )
    by_case = {case.case_id: case for case in cases}
    declarations = plan["cases"]
    require(
        len(by_case) == len(cases) == len(declarations)
        and {row["case_id"] for row in declarations} == set(by_case),
        "complete original generation case roster required",
    )
    generation, expected_samples = [], set()
    for row in declarations:
        case = by_case[row["case_id"]]
        require(
            type(case) is learning.RCControlLearningCase, "exact learning case required"
        )
        require(
            row["split"] == case.split
            and row["model_checksum"] == case.model.canonical_model_checksum,
            "original case model and split differ",
        )
        _same(row["request"], case.request.to_dict(), "original case request differs")
        for name in ("project_id", "geometry_family_id", "load_history_id"):
            require(
                row["identities"][name] == getattr(case, name),
                "original grouping identity differs",
            )
        if case.split == "train":
            _, outcome = _read(
                reader, f"{case.case_id}-generation-outcome.json", artifacts
            )
            generation.append(outcome)
            require(
                outcome.get("labels_eligible") is True,
                "HOLD: every declared generation case must have eligible original samples",
            )
            _, original_report = _read(
                reader, f"{case.case_id}/generation/comparison.json", artifacts
            )
            _same(
                outcome["report"],
                original_report,
                "original generation outcome/report differs",
            )
            require(
                original_report["reference_repeat_exact"] is True,
                "HOLD: original generation reference verification unavailable",
            )
            reference = original_report["arms"]["reference"]
            entries = reference["entries"]
            require(
                reference["status"] == "complete"
                and type(reference["accepted_target_count"]) is int
                and reference["accepted_target_count"] == len(case.request.targets_m)
                and type(entries) is list
                and len(entries) == len(case.request.targets_m),
                "complete eligible generation target denominator required",
            )
            for ordinal, entry in enumerate(entries):
                index = entry["target_index"]
                require(
                    type(index) is int
                    and index == ordinal
                    and _bytes(entry["target_m"])
                    == _bytes(case.request.targets_m[index])
                    and type(entry["invocations"]) is list
                    and entry["invocations"]
                    and (index == 0 or entry["invocations"][0]["committed"] is True),
                    "exact original generation target index required",
                )
                if index >= 1:
                    expected_samples.add((case.case_id, index))
    for sample in samples:
        _checked_hash(sample, "sample_hash")
    require(
        len(samples) == len(expected_samples)
        and {(row["case_id"], row["target_index"]) for row in samples}
        == expected_samples,
        "complete eligible noninitial original sample denominator required",
    )
    rebuilt = build_generation_prior_work_export(
        study_root=root,
        declarations=declarations,
        generation=generation,
        samples=samples,
        source_revision=plan["source_revision"],
    )
    _same(rebuilt, original, "original generation export no longer matches originals")
    rows = {
        row["source_sample_hash"]: deepcopy(row)
        for row in rebuilt["rows"]
        if row["source_sample_hash"] is not None
    }
    require(
        len(rows) == len(samples), "complete original generation sample export required"
    )
    return reader, artifacts, plan, samples, rebuilt, rows, by_case


def _normalization(policy, selected):
    payload = policy.to_dict()
    for row in selected:
        for name in ("features", "correction"):
            require(
                type(row[name]) is list
                and row[name]
                and all(
                    type(value) in (int, float) and np.isfinite(value)
                    for value in row[name]
                ),
                "finite exact original fit numbers required",
            )
    x = np.asarray([row["features"] for row in selected], dtype=float)
    y = np.asarray([row["correction"] for row in selected], dtype=float)
    require(x.ndim == y.ndim == 2 and len(x) >= 2, "original fit arrays required")
    require(
        np.isfinite(x).all() and np.isfinite(y).all(),
        "finite original fit arrays required",
    )
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        mean, scale = x.mean(axis=0), x.std(axis=0)
        scale = np.where(scale > 0, scale, 1.0)
        target = y.std(axis=0)
        target = np.where(target > 0, target, 1.0)
        if payload.get("fit_solver_profile") == learning.CONSTANT_SAFE_SVD_FIT_PROFILE:
            constant = x.min(axis=0) == x.max(axis=0)
            mean = np.where(constant, x[0], mean)
            scale = np.where(constant, 1.0, scale)
            target = np.where(y.min(axis=0) == y.max(axis=0), 1.0, target)
    for key, expected in (
        ("feature_mean", mean),
        ("feature_scale", scale),
        ("feature_min", x.min(axis=0)),
        ("feature_max", x.max(axis=0)),
        ("target_scale", target),
    ):
        require(
            np.array_equal(np.asarray(payload[key]), expected),
            "original complement normalization differs",
        )


def _seed_stage(stage, expected_plan, samples, family, anchors):
    require(type(stage) is OriginalSeedStage, "typed original seed stage required")
    reader, artifacts = _Reader(stage.root), {}
    _, stored = _read(
        reader, stage.plan_path, artifacts, pin=anchors[f"{family}-seed-plan"]
    )
    # Metadata such as historical costs is independently pinned, but is not fed
    # into the existing exact planner or the numeric training object.
    _same(
        {key: stored[key] for key in expected_plan},
        expected_plan,
        "original seed plan differs",
    )
    _, receipt = _read(
        reader, stage.receipt_path, artifacts, pin=anchors[f"{family}-seed-receipts"]
    )
    require(
        receipt["gate_trained"] is False
        and type(receipt["structural_solves"]) is int
        and receipt["structural_solves"] == 0
        and receipt["reserved_evaluation_executed"] is False,
        "original seed stage scope differs",
    )
    receipts = receipt["fits"]
    require(
        type(receipts) is list and len(receipts) == len(expected_plan["seed_fits"]),
        "complete seed fit receipts required",
    )
    indexed = {}
    for row in receipts:
        index = _natural(row["fit_index"], "exact fit receipt index required")
        require(index not in indexed, "duplicate seed fit receipt")
        indexed[index] = row
    originals = {row["sample_hash"]: row for row in samples}
    policies, checked = {}, []
    for fit in expected_plan["seed_fits"]:
        index = fit["fit_index"]
        require(index in indexed, "original seed fit receipt missing")
        path = f"{stage.policy_prefix}/fit-{index:03d}-policy.json"
        raw, value = _read(reader, path, artifacts)
        policy = learning.RCControlSeedPolicy(raw.decode())
        row = indexed[index]
        descriptor = dict(artifacts[path], path=f"fit-{index:03d}-policy.json")
        _same(row["artifact"], descriptor, "original seed policy descriptor differs")
        require(
            row["policy_hash"] == policy.policy_hash
            and type(row["sample_count"]) is int
            and row["sample_count"] == len(fit["training_sample_hashes"])
            and row["complement_feature_statistics_exact"] is True
            and row["promoted"] is False,
            "original seed fit receipt differs",
        )
        _natural(row["wall_ns"], "exact fit elapsed cost required")
        complement = require_exact_seed_policy_complement(
            policy=policy, fit=fit, source_samples=samples
        )
        selected = [originals[identity] for identity in fit["training_sample_hashes"]]
        _normalization(policy, selected)
        policies[index] = policy
        checked.append(
            {
                "fit_index": index,
                "policy_hash": policy.policy_hash,
                "complement_check": complement,
                "normalization_checked": True,
            }
        )
    return reader, artifacts, policies, checked


def _legacy(context):
    return {
        key: value
        for key, value in context.items()
        if key not in {"prior_work_binding", "prior_accepted_transition_work"}
    }


def _prefix_core(context):
    return {
        key: value
        for key, value in _legacy(context).items()
        if key != "committed_material_state_json"
    }


def _report(
    reader,
    base,
    record,
    declaration,
    case,
    sample,
    export_row,
    features,
    artifacts,
    revision,
):
    _, report = _read(reader, base + "/comparison.json", artifacts)
    _checked_hash(report, "report_hash")
    require(
        report["report_hash"] == record["report_hash"],
        "original repetition report differs",
    )
    _, identity = _read(reader, base + "/request.json", artifacts)
    for key, value in identity.items():
        _same(report[key], value, "original comparison identity differs")
    request = replace(
        case.request, targets_m=(case.request.targets_m[declaration["target_index"]],)
    )
    require(
        report["source_revision"] == revision
        and report["model_checksum"] == case.model.canonical_model_checksum
        and (
            "compiled_problem_contract_hash" not in report
            or report["compiled_problem_contract_hash"]
            == features.problem_contract_hash
        )
        and report["proposal_identity"] == declaration["policy_hash"]
        and report["proposal_requested"] is True
        and report["initial_parent_hash"] == sample["parent_hash"]
        and type(report["source_target_index"]) is int
        and report["source_target_index"] == sample["target_index"],
        "original label policy model parent or target differs",
    )
    _same(
        report["source_request"],
        case.request.to_dict(),
        "original label history differs",
    )
    _same(
        report["request"], request.to_dict(), "original single-target request differs"
    )
    require(
        report["original_complete_path_executed"] is False
        and report["comparison_scope"]
        == "one_target_from_one_supplied_native_parent_and_accepted_prefix"
        and report["capture_material_state"] is True
        and report["material_capture_scope"] == "proposal-only"
        and type(report["absolute_tolerance"]) is float
        and report["absolute_tolerance"] == 1e-10
        and type(report["relative_tolerance"]) is float
        and report["relative_tolerance"] == 1e-8,
        "original label comparison scope differs",
    )
    _same(
        report["arm_order"],
        _ORDER[record["repetition"]],
        "counterbalanced original arm order differs",
    )
    raw_parent, parent = _read(reader, base + "/parent.json", artifacts)
    raw_context, context = _read(reader, base + "/accepted-context.json", artifacts)
    for key, raw in (
        ("initial_parent_artifact", raw_parent),
        ("accepted_context_artifact", raw_context),
    ):
        name = (
            "parent.json"
            if key == "initial_parent_artifact"
            else "accepted-context.json"
        )
        _same(
            report[key],
            {"path": name, "sha256": _sha(raw), "byte_length": len(raw)},
            "original supplied artifact descriptor differs",
        )
    require(
        parent["state_hash"] == sample["parent_hash"],
        "original supplied parent differs",
    )
    _same(
        _legacy(context), sample["context"], "original supplied accepted prefix differs"
    )
    # Complete original current-parent bytes are independently selected from the
    # generation arm; comparing state_hash alone would permit changed history.
    _same(parent, export_row["current_parent"], "original supplied parent bytes differ")
    _same(
        _legacy(context),
        _legacy(export_row["context"]),
        "generation/label accepted prefix differs",
    )
    if (
        context.get("prior_work_binding") is not None
        or context.get("prior_accepted_transition_work") is not None
    ):
        _same(context, export_row["context"], "original supplied prior context differs")
    require(
        set(report["arms"]) == set(report["comparisons"]) == set(_ARMS),
        "complete original comparison arms required",
    )
    complete = report["all_execution_work_reported"] is True
    all_work = {key: 0 for key in ("core_calls", "newton_iterations", "linear_solves")}
    paths = {}
    for name, arm in {
        **report["arms"],
        "fresh-reference": report["fresh_reference"],
    }.items():
        _, path = _read(reader, base + "/" + name + "/path.json", artifacts)
        _checked_hash(path, "path_hash")
        require(
            path.get("source_problem_hash") == features.problem_contract_hash,
            "original arm problem contract differs",
        )
        _same(
            {
                key: value
                for key, value in path.items()
                if key
                not in {"response_history", "terminal_checkpoint", "preload_response"}
            },
            arm,
            "original arm/path projection differs",
        )
        paths[name] = path
        require(
            not arm.get("preload_invocations", []) and len(arm["entries"]) == 1,
            "one supplied-parent target required",
        )
        entry = arm["entries"][0]
        require(
            entry["parent_hash"] == sample["parent_hash"], "original arm parent differs"
        )
        if arm["status"] != "complete":
            complete = False
            continue
        _, steps = _invocations(
            reader,
            base + "/" + name,
            0,
            entry,
            artifacts,
            features.problem_contract_hash,
            request,
        )
        _same(steps[0]["parent_checkpoint"], parent, "original arm parent bytes differ")
        require(
            type(path["response_history"]) is list
            and len(path["response_history"]) == 1,
            "original response history denominator differs",
        )
        response = path["response_history"][0]
        child = steps[-1]["accepted_checkpoint"]
        require(
            response["source_step_hash"] == steps[-1]["step_hash"]
            and response["checkpoint_hash"] == child["state_hash"]
            and response["parent_checkpoint_hash"] == parent["state_hash"]
            and type(response["epoch"]) is int
            and response["epoch"] == child["epoch"]
            and type(response["step_index"]) is int
            and response["step_index"] == child["step_index"],
            "original response accepted-step lineage differs",
        )
        _same(
            path["terminal_checkpoint"], child, "original terminal checkpoint differs"
        )
        _, arm_context = _read(reader, base + f"/{name}/000-context.json", artifacts)
        _same(
            _prefix_core(arm_context),
            _prefix_core(context),
            "original arm accepted prefix differs",
        )
        snapshot = arm_context.get("committed_material_state_json")
        if name == "proposal":
            decode_material_snapshot(
                snapshot, features.problem_contract_hash, parent["state_hash"]
            )
            capture = entry["committed_material_capture"]
            require(
                type(capture) is dict and set(capture) == {"wall_ns", "cpu_ns"},
                "original charged proposal material capture required",
            )
            for clock in ("wall_ns", "cpu_ns"):
                _natural(capture[clock], "original material capture cost required")
                require(
                    _natural(path[clock], "original arm elapsed cost required")
                    >= capture[clock],
                    "original material capture cost outside arm timing",
                )
            if context.get("committed_material_state_json") is not None:
                _same(
                    snapshot,
                    context["committed_material_state_json"],
                    "original supplied-parent material snapshot differs",
                )
        else:
            require(
                snapshot is None and "committed_material_capture" not in entry,
                "proposal-only material capture scope differs",
            )
        for invocation in entry["invocations"]:
            for counter in all_work:
                all_work[counter] += _natural(
                    invocation["work"][counter], "original work counter required"
                )
    checked_comparisons = {}
    fresh = paths["fresh-reference"]
    for name in _ARMS:
        path = paths[name]
        structure, absolute, relative, within = _numeric_payload_difference(
            fresh["response_history"],
            path["response_history"],
            absolute_tolerance=1e-10,
            relative_tolerance=1e-8,
        )
        checked = {
            "step_response_pass": fresh["status"] == path["status"] == "complete"
            and structure
            and within,
            "structure_match": structure,
            "mismatch_locations": _physical_mismatch_locations(
                fresh["response_history"],
                path["response_history"],
                absolute_tolerance=1e-10,
                relative_tolerance=1e-8,
            ),
            "physical_values_within_tolerance": within,
            "maximum_absolute_difference_mixed_SI_fields": absolute
            if np.isfinite(absolute)
            else None,
            "maximum_relative_difference": relative if np.isfinite(relative) else None,
            "exact_terminal_checkpoint": _bytes(fresh["terminal_checkpoint"])
            == _bytes(path["terminal_checkpoint"]),
        }
        _same(
            report["comparisons"][name], checked, "original response comparison differs"
        )
        checked_comparisons[name] = checked
    reference = checked_comparisons["reference"]
    exact_repeat = (
        reference["step_response_pass"]
        and reference["exact_terminal_checkpoint"]
        and _bytes(paths["reference"]["response_history"])
        == _bytes(fresh["response_history"])
    )
    require(
        report["reference_repeat_exact"] is exact_repeat,
        "original reference repeat verdict differs",
    )
    passed = complete and all(
        item["step_response_pass"] is True for item in checked_comparisons.values()
    )
    proposal, secant = report["arms"]["proposal"], report["arms"]["secant"]
    for arm in (proposal, secant):
        require(
            type(arm["wall_ns"]) is int and arm["wall_ns"] > 0,
            "positive original arm time required",
        )
    return {
        "repetition": record["repetition"],
        "comparison_pass": passed,
        "decision": proposal["entries"][0]["proposal_decision"],
        "path_time_ratio": proposal["wall_ns"] / secant["wall_ns"] if passed else None,
        "report_hash": report["report_hash"],
        "work": all_work if complete else dict.fromkeys(all_work),
        "known_completed_arm_work": all_work,
        "work_complete": complete,
    }


def _labels(root, family, tasks, policies, generation, cases, samples, anchors):
    reader, artifacts = _Reader(root), {}
    _, plan = _read(reader, "plan.json", artifacts, pin=anchors[f"{family}-label-plan"])
    _, outcome = _read(
        reader, "outcome.json", artifacts, pin=anchors[f"{family}-label-outcome"]
    )
    _same(plan["label_rule"], LABEL_RULE, "predeclared fixed label rule differs")
    _same(plan["arm_order_schedule"], _ORDER, "predeclared arm order differs")
    require(
        type(plan["repetitions"]) is int
        and plan["repetitions"] == 3
        and plan["gate_trained"] is False
        and plan["reserved_evaluation"] is False
        and plan["complete_path_claim"] is False
        and plan["feature_capture_charged_to_proposal"] is True,
        "original label declaration scope differs",
    )
    require(
        type(plan["source_revision"]) is str
        and len(plan["source_revision"]) == 40
        and all(c in "0123456789abcdef" for c in plan["source_revision"]),
        "exact label source revision required",
    )
    sample_index = {row["sample_hash"]: row for row in samples}
    expected = []
    for task_index, task in enumerate(tasks):
        for sample_hash in task["label_source_sample_hashes"]:
            sample = sample_index[sample_hash]
            row = {
                "task_index": task_index,
                "case_id": sample["case_id"],
                "target_index": sample["target_index"],
                "seed_fit_index": task["seed_fit_index"],
                "policy_hash": policies[task["seed_fit_index"]].policy_hash,
                "source_sample_hash": sample_hash,
                "parent_hash": sample["parent_hash"],
            }
            if family == "new":
                row["label_group_index"] = task["label_group_index"]
            else:
                row.update(
                    outer_group_index=task["outer_group_index"],
                    inner_group_index=task["inner_group_index"],
                )
            # Features are checked against original context below, and cannot be
            # chosen after inspecting the current target's measured label.
            expected.append(row)
    roster = plan["roster"]
    require(
        type(roster) is list and len(roster) == len(expected),
        "complete original label roster required",
    )
    expected_index = {
        (row["task_index"], row["source_sample_hash"]): row for row in expected
    }
    observed = set()
    for row in roster:
        require(
            type(row["task_index"]) is int and type(row["seed_fit_index"]) is int,
            "exact label task and fit indices required",
        )
        key = (row["task_index"], row["source_sample_hash"])
        require(
            key in expected_index and key not in observed,
            "unique original label declaration required",
        )
        observed.add(key)
        _same(
            {k: row[k] for k in expected_index[key]},
            expected_index[key],
            "original policy/sample label lineage differs",
        )
    records = outcome["records"]
    require(
        type(records) is list and len(records) == 3 * len(roster),
        "complete original repetition roster required",
    )
    indexed = {}
    for record in records:
        pair, repetition = record["pair_index"], record["repetition"]
        require(
            type(pair) is int
            and type(repetition) is int
            and 0 <= pair < len(roster)
            and 0 <= repetition < 3,
            "exact original repetition indices required",
        )
        require((pair, repetition) not in indexed, "duplicate original repetition")
        indexed[pair, repetition] = record
    result = []
    for pair_index, declaration in enumerate(roster):
        sample_hash = declaration["source_sample_hash"]
        sample, source = sample_index[sample_hash], generation[sample_hash]
        model = decode_fiber_frame_warm_start_model_features(source["model_features"])
        _same(
            declaration["guard_features"],
            prefix_features(_context(sample["context"]), model),
            "original pre-label features differ",
        )
        repeats = []
        for repetition in range(3):
            record = indexed[pair_index, repetition]
            _, actual = _read(
                reader, f"record-{pair_index:03d}-{repetition}.json", artifacts
            )
            _same(actual, record, "original completion receipt differs")
            repeats.append(
                _report(
                    reader,
                    f"pair-{pair_index:03d}-repeat-{repetition}",
                    record,
                    declaration,
                    cases[sample["case_id"]],
                    sample,
                    source,
                    model,
                    artifacts,
                    plan["source_revision"],
                )
            )
        result.append(
            {
                **declaration,
                "repetitions": repeats,
                "label_result": label_from_repetitions(repeats),
            }
        )
    return {"pairs": result}, artifacts


def read_original_prior_work_fold(
    *,
    generation_root,
    cases,
    new_seed_stage,
    retained_seed_stage,
    new_label_root,
    retained_label_root,
    outer,
    validation,
    evaluation_seed_fit_index,
    anchors,
):
    """Reconstruct a complete fold or keep mandatory unavailable inputs HOLD.

    Invalid global pins, plans, policy lineage or originals raise ValueError.
    Genuine missing predecessor counters stay distinct from unknown labels and
    produce HOLD without filtering any selected row. Unselected origin targets
    remain in generation coverage and do not falsely block otherwise-ready folds.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    require(
        type(anchors) is dict and set(anchors) == _ANCHORS,
        "complete predeclared original pins required",
    )
    for value in anchors.values():
        require(
            type(value) is dict and set(value) == {"path", "sha256", "byte_length"},
            "exact original artifact pins required",
        )
    require(
        type(outer) is int and type(validation) is int and outer != validation,
        "distinct exact fold indices required",
    )
    require(
        type(evaluation_seed_fit_index) is int and evaluation_seed_fit_index >= 0,
        "exact evaluation seed fit index required",
    )
    require(
        type(new_seed_stage) is OriginalSeedStage
        and type(retained_seed_stage) is OriginalSeedStage,
        "typed original seed stages required",
    )
    gen_reader, gen_artifacts, gen_plan, samples, export, sources, by_case = (
        _generation(generation_root, cases, anchors)
    )
    _, inner_stored = _read(
        _Reader(new_seed_stage.root),
        new_seed_stage.plan_path,
        {},
        pin=anchors["new-seed-plan"],
    )
    groups = inner_stored["groups"]
    inner, retained = (
        inner_validation_plan(groups, samples),
        nested_plan(groups, samples),
    )
    provenance = validate_inner_validation_provenance(
        cases=cases,
        source_samples=samples,
        groups=groups,
        inner_plan=inner,
        retained_seed_plan=retained,
    )
    _, new_artifacts, new_policies, new_checks = _seed_stage(
        new_seed_stage, inner, samples, "new", anchors
    )
    _, retained_artifacts, retained_policies, retained_checks = _seed_stage(
        retained_seed_stage, retained, samples, "retained", anchors
    )
    folds = [
        fold
        for fold in inner["gate_folds"]
        if (fold["outer_group_index"], fold["validation_group_index"])
        == (outer, validation)
    ]
    require(len(folds) == 1, "declared original fold required")
    evaluation = [
        fit
        for fit in retained["seed_fits"]
        if fit["fit_index"] == evaluation_seed_fit_index
    ]
    require(
        len(evaluation) == 1
        and evaluation[0]["excluded_group_indices"] == sorted([outer, validation]),
        "evaluation seed must exclude exact outer and validation groups",
    )
    # Resolve descriptors against original generation files even for unavailable
    # prior counters: label lineage and feature availability are separate axes.
    for sample in samples:
        source = sources[sample["sample_hash"]]
        base = f"{sample['case_id']}/generation/reference/{sample['target_index']:03d}"
        _, context = _read(gen_reader, base + "-context.json", gen_artifacts)
        _, step = _read(gen_reader, base + "-1-step.json", gen_artifacts)
        source["context"] = context
        source["current_parent"] = step["parent_checkpoint"]
    new_audit, new_labels = _labels(
        new_label_root,
        "new",
        inner["unique_new_label_tasks"],
        new_policies,
        sources,
        by_case,
        samples,
        anchors,
    )
    retained_audit, retained_labels = _labels(
        retained_label_root,
        "retained",
        retained["label_tasks"],
        retained_policies,
        sources,
        by_case,
        samples,
        anchors,
    )
    tables = assemble_fold(
        new_audit,
        retained_audit,
        inner,
        outer,
        validation,
        new_policy_hashes={i: p.policy_hash for i, p in new_policies.items()},
        old_policy_hashes={i: p.policy_hash for i, p in retained_policies.items()},
    )
    rows, join_rows = [], []
    for table, collections in (
        (tables["training"], ("training_rows", "unverified_rows")),
        (tables["validation"], ("rows",)),
    ):
        for collection in collections:
            for row in table[collection]:
                source = sources[row["source_sample_hash"]]
                usable = (
                    source["status"] == "available"
                    and source["six_counter_profile_usable"] is True
                )
                rows.append(
                    {
                        "case_id": row["case_id"],
                        "source_sample_hash": row["source_sample_hash"],
                        "policy_hash": row["policy_hash"],
                        "seed_fit_index": row["seed_fit_index"],
                        "parent_hash": row["parent_hash"],
                        "status": "ready" if usable else "unavailable",
                        "unavailable_reason": None
                        if usable
                        else (
                            source["unavailable_reason"]
                            or source["optional_counter_reason"]
                        ),
                        "label_known": row["label"] is not None,
                    }
                )
                if usable:
                    join_rows.append(
                        {
                            **{
                                key: row[key]
                                for key in (
                                    "case_id",
                                    "source_sample_hash",
                                    "policy_hash",
                                    "seed_fit_index",
                                    "parent_hash",
                                )
                            },
                            "prior_work_context": deepcopy(source["context"]),
                            "model_features": deepcopy(source["model_features"]),
                        }
                    )
    ready = all(row["status"] == "ready" for row in rows)
    packet = {"schema_version": JOIN_PROFILE, "rows": join_rows} if ready else None
    guarded_tables = (
        append_prior_work_inputs(
            tables,
            packet,
            seed_policy_hash=retained_policies[evaluation_seed_fit_index].policy_hash,
        )
        if ready
        else None
    )
    payload = {
        "schema_version": PROFILE,
        "status": "ready" if ready else "HOLD",
        "outer_group_index": outer,
        "validation_group_index": validation,
        "evaluation_seed_policy_hash": retained_policies[
            evaluation_seed_fit_index
        ].policy_hash,
        "evaluation_seed_policy": retained_policies[
            evaluation_seed_fit_index
        ].to_dict(),
        "rows": rows,
        "coverage": {
            "selected_total": len(rows),
            "ready": sum(row["status"] == "ready" for row in rows),
            "unavailable": sum(row["status"] != "ready" for row in rows),
            "unknown_label": sum(not row["label_known"] for row in rows),
        },
        "tables": guarded_tables,
        "join_packet": packet,
        "generation_coverage": deepcopy(export["coverage"]),
        "generation_rows": deepcopy(export["rows"]),
        "provenance": provenance,
        "seed_checks": {"new": new_checks, "retained": retained_checks},
        "artifacts": {
            "generation": gen_artifacts,
            "new_seeds": new_artifacts,
            "retained_seeds": retained_artifacts,
            "new_labels": new_labels,
            "retained_labels": retained_labels,
        },
        "anchors": deepcopy(anchors),
        "source_revision": gen_plan["source_revision"],
        "reference_parent_conditioned": True,
        "claims": {
            "original_file_correspondence": True,
            "source_authenticity": False,
            "dataset_admitted": False,
            "proposal_arm_predecessor_provenance": False,
            "independent_physics": False,
            "full_path_gain": False,
            "coupled_full_training_refit": False,
            "release_qualified": False,
        },
        "read_check_join_wall_ns": perf_counter_ns() - wall,
        "read_check_join_cpu_ns": process_time_ns() - cpu,
        "cost_scope": "original reads and audits and fold join only; excludes caller pin preparation, output serialization/writes, fits and solves",
    }
    payload["fold_hash"] = _sha(_bytes(payload))
    return payload


def fit_original_prior_work_fold(verified_fold):
    """Fit a fixed development fold pair after this reader, never a full refit.

    The caller must use the just-read result, not treat an arbitrary self-hashed
    JSON object as authenticated originals. Only the training table enters the
    fitter; validation predictions freeze before labels are inspected. Full-path
    costs and own proposal-arm predecessor provenance remain separate work.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    require(
        type(verified_fold) is dict and verified_fold.get("schema_version") == PROFILE,
        "original fold reader result required",
    )
    _checked_hash(verified_fold, "fold_hash")
    require(
        verified_fold["status"] == "ready"
        and verified_fold["coverage"]["unavailable"] == 0,
        "HOLD: complete original prior inputs required before fitting",
    )
    tables = verified_fold["tables"]
    seed = learning.RCControlSeedPolicy(
        _bytes(verified_fold["evaluation_seed_policy"]).decode()
    )
    require(
        seed.policy_hash
        == verified_fold["evaluation_seed_policy_hash"]
        == tables["training"]["seed_policy_hash"],
        "original evaluation seed binding differs",
    )
    # Do not pass the mixed packet's hash, original inventories, validation or
    # outer-row metadata into normalization, targets or training identity.
    gate, receipt = fit_prior_work_cost_gate(deepcopy(tables["training"]))
    frozen = []
    for row in tables["validation"]["rows"]:
        _, _, features = _checked_row_inputs(row)
        _same(
            features["feature_names"],
            tables["validation"]["feature_names"],
            "original validation feature names differ",
        )
        _same(
            features["values"],
            row["values"],
            "original validation feature values differ",
        )
        frozen.append(
            {
                "source_sample_hash": row["source_sample_hash"],
                "policy_hash": row["policy_hash"],
                "seed_fit_index": row["seed_fit_index"],
                "selected_proposal": gate.decision(features),
            }
        )
    prediction_hash = _sha(_bytes(frozen))
    scores = {
        "declared_rows": len(frozen),
        "known_labels": 0,
        "unknown_labels": 0,
        "selected_proposal": sum(row["selected_proposal"] for row in frozen),
        "false_positive": 0,
        "false_negative": 0,
    }
    for row, prediction in zip(tables["validation"]["rows"], frozen, strict=True):
        expected = label_from_repetitions(row["cost_repetitions"])["label"]
        require(row["label"] is expected, "original validation label differs")
        if expected is None:
            scores["unknown_labels"] += 1
        else:
            scores["known_labels"] += 1
            scores["false_positive"] += prediction["selected_proposal"] and not expected
            scores["false_negative"] += not prediction["selected_proposal"] and expected
    require(
        prediction_hash == _sha(_bytes(frozen)), "frozen validation predictions changed"
    )
    payload = {
        "schema_version": "rc-original-fold-seed-prior-work-pair.v1",
        "seed_policy": seed.to_dict(),
        "gate_policy": strict_json_object_bytes(
            gate._json.encode(), maximum_bytes=1024 * 1024
        ),
        "seed_policy_hash": seed.policy_hash,
        "gate_policy_hash": gate.policy_hash,
        "outer_group_index": verified_fold["outer_group_index"],
        "validation_group_index": verified_fold["validation_group_index"],
        "excluded_case_ids": list(gate.excluded_case_ids),
        "fit_receipt": receipt,
        "validation_predictions": frozen,
        "prediction_hash": prediction_hash,
        "validation_scores": scores,
        "reference_parent_conditioned": True,
        "full_training_refit": False,
        "original_training_admitted": False,
        "source_authenticity": False,
        "full_path_gain": False,
        "independent_validation": False,
        "paired_fit_prediction_score_wall_ns": perf_counter_ns() - wall,
        "paired_fit_prediction_score_cpu_ns": process_time_ns() - cpu,
        "cost_scope": "this fold fit, frozen validation prediction and label scoring; excludes preceding original reads/join, external source pin preparation and output serialization/writes",
    }
    payload["pair_hash"] = _sha(_bytes(payload))
    return payload
