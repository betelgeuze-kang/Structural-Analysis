"""Authored original-file joins plus one bounded real producer compatibility test.

The four-group codec fixture does not claim solver-produced accepted states.
Its policies use small algebra fits only; all filesystem correspondence is real.
"""

from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis.ai.fiber_frame_warm_start_features import (
    fiber_frame_warm_start_model_features,
)
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_prior_work import (
    make_rc_control_prior_work_binding,
    make_rc_control_prior_work_record,
)
from structural_analysis.benchmark.rc_control_prior_work_export import (
    build_generation_prior_work_export,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
)
from tests.test_rc_control_learning_split import make
from tests.test_rc_control_prior_work import synthetic_prior_context
from tests.test_rc_control_prior_work_export import _rehash_step

REVISION = "0663fc951eab1f8d49d3dacf53e635b114a3ad2b"
ARMS = ("reference", "secant", "proposal")
ORDERS = [list(ARMS[i:] + ARMS[:i]) for i in range(3)]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_bytes(value))


def _load(path):
    return json.loads(path.read_bytes())


def _seal(value, field):
    value[field] = _sha(_bytes({k: v for k, v in value.items() if k != field}))
    return value


def _descriptor(root, relative):
    raw = (root / relative).read_bytes()
    return {"path": relative, "sha256": _sha(raw), "byte_length": len(raw)}


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("rc_prior_work_original_inputs")


def _generation(tmp_path, *, assembly=True, omitted=None, truncated=False, delta=0.0):
    """Public typed geometry; authored transitions, never numerical observations."""
    root = tmp_path / "generation"
    cases, declarations, generation, samples, originals = [], [], [], [], {}
    template = synthetic_prior_context(retries=1, assembly=assembly)
    for case_index, ratio in enumerate((0.2, 0.3, 0.4, 0.5)):
        name = "ABCD"[case_index]
        case = make(
            tmp_path / "models",
            name,
            "train",
            lengths=(2.0, 2.0 * ratio),
            targets=(1e-4, -(1.0 + ratio) * 1e-4, 0.4e-4),
        )
        cases.append(case)
        compiled, blockers, _ = public._compile(case.model)
        assert compiled is not None and not blockers
        features = fiber_frame_warm_start_model_features(compiled.problem)
        free = compiled.problem.free_global_dofs
        control = free.index(case.request.control_global_dof)
        width = len(free) + 1
        base = root / name / "generation"
        arm = base / "reference"
        sources = {
            "source_revision": REVISION,
            "source_revision_is_attestation": False,
            "scope": "authored codec fixture; no solver producer attestation",
        }
        identity = {
            "schema_version": "experimental-rc-control-seed-comparison.v1",
            "source_revision": REVISION,
            "source_revision_is_attestation": False,
            "model_checksum": case.model.canonical_model_checksum,
            "request": case.request.to_dict(),
            "proposal_requested": False,
            "proposal_identity": None,
            "prior_accepted_transition_work": {
                "profile": "rc-control-prior-accepted-transition-work.v1",
                "sources": sources,
            },
        }
        arm_identity = _sha(
            _bytes(
                {
                    "comparison_identity": _sha(_bytes(identity)),
                    "arm_directory": str(arm),
                }
            )
        )
        checkpoints = []
        for index in range(4):
            checkpoints.append(
                {
                    "schema_version": "stateful-fiber-frame2d-checkpoint.v1",
                    "role": "committed",
                    "case_id": name,
                    "problem_contract_hash": features.problem_contract_hash,
                    "epoch": index,
                    "step_index": index,
                    "state_hash": _sha(f"authored-{name}-{index}".encode()),
                    "parent_state_hash": None
                    if index == 0
                    else checkpoints[-1]["state_hash"],
                    "global_displacements": [0.0] * compiled.problem.global_dof_count,
                    "load_factor": 0.0,
                    "element_states": [],
                }
            )
        coords = [tuple(0.0 for _ in range(width))]
        for target in case.request.targets_m:
            coordinate = [0.0] * width
            coordinate[control] = target
            coordinate[-1] = 0.25
            coords.append(tuple(coordinate))
        entries, preceding = [], []
        for index, target in enumerate(case.request.targets_m):
            context = runtime.RCControlSeedContext(
                features.problem_contract_hash,
                case.request.control_global_dof,
                control,
                target,
                (0.0, *case.request.targets_m[:index]),
                tuple(coords[: index + 1]),
            )
            binding = make_rc_control_prior_work_binding(
                context,
                accepted_checkpoint=SimpleNamespace(
                    **{
                        k: checkpoints[index][k]
                        for k in (
                            "state_hash",
                            "parent_state_hash",
                            "epoch",
                            "step_index",
                        )
                    }
                ),
                arm_identity=arm_identity,
                request_hash=_sha(_bytes(case.request.to_dict())),
                solver_config_hash=case.request.solver_config.contract_hash,
                source_binding_hash=_sha(_bytes(sources)),
            )
            context = replace(
                context,
                prior_work_binding=binding,
                prior_accepted_transition_work=make_rc_control_prior_work_record(
                    binding, preceding
                )
                if preceding
                else None,
            )
            _write(arm / f"{index:03d}-context.json", context.to_dict())
            outcomes, steps, transition = [], [], []
            templates = (
                template.prior_accepted_transition_work["invocations"]
                if index == 0
                else template.prior_accepted_transition_work["invocations"][-1:]
            )
            for ordinal, authored in enumerate(templates, 1):
                step, outcome = (
                    json.loads(authored["step_json"]),
                    json.loads(authored["outcome_json"]),
                )
                committed = ordinal == len(templates)
                step.update(
                    status="ready" if committed else "blocked",
                    committed=committed,
                    parent_checkpoint=checkpoints[index],
                    accepted_checkpoint=checkpoints[index + 1]
                    if committed
                    else checkpoints[index],
                )
                step["metrics"].update(
                    control_global_dof=case.request.control_global_dof,
                    config_hash=case.request.solver_config.contract_hash,
                    target_control_displacement_m=target,
                    rollback_exact=None if committed else True,
                )
                step["trial_solution"]["augmented_coordinates_m"] = list(
                    coords[index + 1]
                )
                outcome.update(
                    ordinal=ordinal,
                    committed=committed,
                    rollback_exact=None if committed else True,
                )
                _rehash_step(step)
                _write(arm / f"{index:03d}-{ordinal}-step.json", step)
                _write(arm / f"{index:03d}-{ordinal}-outcome.json", outcome)
                outcomes.append(outcome)
                steps.append(step)
                transition.append((_bytes(outcome), _bytes(step)))
            preceding = transition
            entry = dict(
                target_index=index,
                target_m=target,
                parent_hash=checkpoints[index]["state_hash"],
                invocations=outcomes,
            )
            entries.append(entry)
            if index:
                legacy = {
                    k: v
                    for k, v in context.to_dict().items()
                    if k not in {"prior_work_binding", "prior_accepted_transition_work"}
                }
                values = learning._features(context, features).tolist()
                correction = [0.0] * width
                if case_index in (0, 1):
                    values[0] += delta
                    correction[-1] += delta
                sample = dict(
                    case_id=name,
                    split="train",
                    target_index=index,
                    parent_hash=checkpoints[index]["state_hash"],
                    context=legacy,
                    original_step_bytes_hash=_sha(_bytes(steps[0])),
                    accepted_coordinates=list(coords[index + 1]),
                    features=values,
                    correction=correction,
                )
                _seal(sample, "sample_hash")
                if (name, index) != omitted:
                    samples.append(sample)
                originals[name, index] = dict(
                    sample=sample,
                    context=context.to_dict(),
                    step=steps[-1],
                    outcome=outcomes[-1],
                    model_features=features,
                    free=free,
                )
        if truncated:
            entries.pop()
        report = {
            **identity,
            "reference_repeat_exact": True,
            "arms": {
                "reference": {
                    "strategy": "reference",
                    "status": "complete",
                    "accepted_target_count": len(entries),
                    "source_problem_hash": features.problem_contract_hash,
                    "requested_targets_m": list(case.request.targets_m),
                    "entries": entries,
                }
            },
        }
        _seal(report, "report_hash")
        declaration = dict(
            case_id=name,
            split="train",
            identities={
                key: getattr(case, key)
                for key in ("project_id", "geometry_family_id", "load_history_id")
            },
            model_checksum=identity["model_checksum"],
            request=case.request.to_dict(),
            model_features=features.to_dict(),
        )
        outcome = dict(case_id=name, labels_eligible=True, report=report)
        declarations.append(declaration)
        generation.append(outcome)
        _write(base / "request.json", identity)
        _write(base / "model.json", case.model.canonical_payload())
        _write(base / "comparison.json", report)
        _write(root / f"{name}-generation-outcome.json", outcome)
    if truncated:
        samples = [row for row in samples if row["target_index"] != 2]
    _write(root / "plan.json", {"source_revision": REVISION, "cases": declarations})
    _write(root / "training-samples.json", samples)
    exported = build_generation_prior_work_export(
        study_root=root,
        declarations=declarations,
        generation=generation,
        samples=samples,
        source_revision=REVISION,
    )
    _write(root / "generation-prior-work-export.json", exported)
    return dict(
        root=root,
        cases=cases,
        declarations=declarations,
        samples=samples,
        generation=generation,
        export=exported,
        originals=originals,
    )


def _seeds(module, root, plan, generation):
    from prepare_rc_nested_switch_labels import fit_declared_seeds

    first = generation["originals"]["A", 1]
    features = first["model_features"]
    profile = dict(
        model_context_hash=features.context_hash,
        model_feature_names=list(features.feature_names),
        free_global_dofs=list(first["free"]),
        control_free_index=first["sample"]["context"]["control_free_index"],
        solver_config_hash=generation["cases"][0].request.solver_config.contract_hash,
    )
    _write(root / "plan.json", plan)
    fit_declared_seeds(plan, generation["samples"], profile, root / "seeds")
    policies = {
        fit["fit_index"]: _load(
            root / "seeds" / f"fit-{fit['fit_index']:03d}-policy.json"
        )
        for fit in plan["seed_fits"]
    }
    return module.OriginalSeedStage(root), policies


def _comparison(paths):
    fresh, comparisons = paths["fresh-reference"], {}
    for name in ARMS:
        path = paths[name]
        structure, absolute, relative, within = _numeric_payload_difference(
            fresh["response_history"],
            path["response_history"],
            absolute_tolerance=1e-10,
            relative_tolerance=1e-8,
        )
        comparisons[name] = dict(
            step_response_pass=fresh["status"] == path["status"] == "complete"
            and structure
            and within,
            structure_match=structure,
            mismatch_locations=runtime._physical_mismatch_locations(
                fresh["response_history"],
                path["response_history"],
                absolute_tolerance=1e-10,
                relative_tolerance=1e-8,
            ),
            physical_values_within_tolerance=within,
            maximum_absolute_difference_mixed_SI_fields=absolute,
            maximum_relative_difference=relative,
            exact_terminal_checkpoint=_bytes(fresh["terminal_checkpoint"])
            == _bytes(path["terminal_checkpoint"]),
        )
    return comparisons


def _labels(
    root,
    tasks,
    policies,
    generation,
    *,
    family,
    unknown_validation=False,
    unknown_full_teacher=False,
):
    from rc_switch_prefix_features import prefix_features
    from run_rc_nested_switch_labels import LABEL_RULE

    by_hash = {row["sample_hash"]: row for row in generation["samples"]}
    by_case = {case.case_id: case for case in generation["cases"]}
    roster, records = [], []
    for task_index, task in enumerate(tasks):
        for sample_hash in task["label_source_sample_hashes"]:
            sample = by_hash[sample_hash]
            index = sample["target_index"]
            original = generation["originals"][sample["case_id"], index]
            case = by_case[sample["case_id"]]
            declaration = dict(
                task_index=task_index,
                case_id=case.case_id,
                target_index=index,
                seed_fit_index=task["seed_fit_index"],
                policy_hash=policies[task["seed_fit_index"]]["policy_hash"],
                source_sample_hash=sample_hash,
                parent_hash=sample["parent_hash"],
                guard_features=prefix_features(
                    runtime.RCControlSeedContext(
                        **{
                            **sample["context"],
                            "accepted_targets_m": tuple(
                                sample["context"]["accepted_targets_m"]
                            ),
                            "accepted_augmented_coordinates_m": tuple(
                                tuple(row)
                                for row in sample["context"][
                                    "accepted_augmented_coordinates_m"
                                ]
                            ),
                        }
                    ),
                    original["model_features"],
                ),
            )
            if family == "new":
                declaration["label_group_index"] = task["label_group_index"]
            else:
                declaration.update(
                    outer_group_index=task["outer_group_index"],
                    inner_group_index=task["inner_group_index"],
                )
            pair_index = len(roster)
            roster.append(declaration)
            for repetition in range(3):
                base = root / f"pair-{pair_index:03d}-repeat-{repetition}"
                _write(base / "parent.json", original["step"]["parent_checkpoint"])
                _write(base / "accepted-context.json", sample["context"])
                request = replace(
                    case.request, targets_m=(case.request.targets_m[index],)
                )
                identity = dict(
                    schema_version="experimental-rc-control-parent-step-comparison.v1",
                    source_revision=REVISION,
                    source_revision_is_attestation=False,
                    model_checksum=case.model.canonical_model_checksum,
                    compiled_problem_contract_hash=original[
                        "model_features"
                    ].problem_contract_hash,
                    source_request=case.request.to_dict(),
                    request=request.to_dict(),
                    source_target_index=index,
                    proposal_requested=True,
                    proposal_identity=declaration["policy_hash"],
                    initial_parent_hash=sample["parent_hash"],
                    initial_parent_artifact=_descriptor(base, "parent.json"),
                    accepted_context_artifact=_descriptor(
                        base, "accepted-context.json"
                    ),
                    original_complete_path_executed=False,
                    comparison_scope="one_target_from_one_supplied_native_parent_and_accepted_prefix",
                    capture_material_state=True,
                    material_capture_scope="proposal-only",
                    absolute_tolerance=1e-10,
                    relative_tolerance=1e-8,
                    arm_order=ORDERS[repetition],
                )
                _write(base / "request.json", identity)
                paths = {}
                for name in (*ARMS, "fresh-reference"):
                    entry = dict(
                        target_index=0,
                        target_m=case.request.targets_m[index],
                        parent_hash=sample["parent_hash"],
                        invocations=[original["outcome"]],
                        proposal_decision="proposed" if name == "proposal" else name,
                    )
                    arm_context = deepcopy(sample["context"])
                    if name == "proposal":
                        snapshot = dict(
                            schema_version="rc-committed-fiber-inputs.v1",
                            problem_contract_hash=original[
                                "model_features"
                            ].problem_contract_hash,
                            parent_state_hash=sample["parent_hash"],
                            feature_names=["member_0_point_0_fiber_0_steel_strain"],
                            values=[0.0],
                        )
                        arm_context["committed_material_state_json"] = _bytes(
                            _seal(snapshot, "snapshot_hash")
                        ).decode()
                        entry["committed_material_capture"] = {
                            "wall_ns": 1,
                            "cpu_ns": 1,
                        }
                    response = dict(
                        source_step_hash=original["step"]["step_hash"],
                        checkpoint_hash=original["step"]["accepted_checkpoint"][
                            "state_hash"
                        ],
                        parent_checkpoint_hash=sample["parent_hash"],
                        epoch=original["step"]["accepted_checkpoint"]["epoch"],
                        step_index=original["step"]["accepted_checkpoint"][
                            "step_index"
                        ],
                        authored_response=0.0,
                    )
                    if (
                        family == "retained"
                        and name == "proposal"
                        and (
                            (
                                unknown_validation
                                and task["outer_group_index"] == 0
                                and task["inner_group_index"] == 1
                            )
                            or (
                                unknown_full_teacher
                                and (
                                    unknown_full_teacher == "all"
                                    or (
                                        task["outer_group_index"] == 2
                                        and task["inner_group_index"] == 1
                                    )
                                )
                            )
                        )
                    ):
                        response["authored_response"] = 1.0
                    path = dict(
                        schema_version="experimental-rc-control-parent-step-path.v1",
                        strategy=name,
                        status="complete",
                        requested_targets_m=list(request.targets_m),
                        accepted_target_count=1,
                        entries=[entry],
                        response_history=[response],
                        terminal_checkpoint=original["step"]["accepted_checkpoint"],
                        failure=None,
                        wall_ns=98 if name == "proposal" else 100,
                        cpu_ns=10,
                        source_problem_hash=original[
                            "model_features"
                        ].problem_contract_hash,
                    )
                    _seal(path, "path_hash")
                    paths[name] = path
                    _write(base / name / "path.json", path)
                    _write(base / name / "000-context.json", arm_context)
                    _write(base / name / "000-1-step.json", original["step"])
                    _write(base / name / "000-1-outcome.json", original["outcome"])
                report = {
                    **identity,
                    "arms": {
                        name: {
                            k: v
                            for k, v in paths[name].items()
                            if k
                            not in {
                                "response_history",
                                "terminal_checkpoint",
                                "preload_response",
                            }
                        }
                        for name in ARMS
                    },
                    "fresh_reference": {
                        k: v
                        for k, v in paths["fresh-reference"].items()
                        if k
                        not in {
                            "response_history",
                            "terminal_checkpoint",
                            "preload_response",
                        }
                    },
                    "comparisons": _comparison(paths),
                    "reference_repeat_exact": True,
                    "all_execution_work_reported": True,
                    "stale_cost_summary_not_authority": {
                        "label": False,
                        "path_time_ratio": 700.0,
                    },
                }
                _seal(report, "report_hash")
                _write(base / "comparison.json", report)
                record = dict(
                    pair_index=pair_index,
                    repetition=repetition,
                    report_hash=report["report_hash"],
                )
                _write(root / f"record-{pair_index:03d}-{repetition}.json", record)
                records.append(record)
    _write(
        root / "plan.json",
        dict(
            source_revision=REVISION,
            roster=roster,
            label_rule=LABEL_RULE,
            repetitions=3,
            arm_order_schedule=ORDERS,
            gate_trained=False,
            reserved_evaluation=False,
            complete_path_claim=False,
            feature_capture_charged_to_proposal=True,
        ),
    )
    _write(root / "outcome.json", {"records": records})


def authored_fold_files(tmp_path, module, **options):
    from plan_rc_gate_inner_validation import inner_validation_plan
    from prepare_rc_nested_switch_labels import nested_plan

    (tmp_path / "models").mkdir(parents=True, exist_ok=True)
    generation = _generation(
        tmp_path,
        assembly=options.get("assembly", True),
        delta=options.get("delta", 0.0),
    )
    groups = [[case.case_id] for case in generation["cases"]]
    inner, retained = (
        inner_validation_plan(groups, generation["samples"]),
        nested_plan(groups, generation["samples"]),
    )
    new_stage, new_policies = _seeds(module, tmp_path / "new-seeds", inner, generation)
    retained_stage, retained_policies = _seeds(
        module, tmp_path / "retained-seeds", retained, generation
    )
    new_root, retained_root = tmp_path / "new-labels", tmp_path / "retained-labels"
    _labels(
        new_root,
        inner["unique_new_label_tasks"],
        new_policies,
        generation,
        family="new",
    )
    _labels(
        retained_root,
        retained["label_tasks"],
        retained_policies,
        generation,
        family="retained",
        unknown_validation=options.get("unknown_validation", False),
        unknown_full_teacher=options.get("unknown_full_teacher", False),
    )
    paths = {
        "generation-plan": (generation["root"], "plan.json"),
        "generation-samples": (generation["root"], "training-samples.json"),
        "generation-export": (generation["root"], "generation-prior-work-export.json"),
        "new-seed-plan": (new_stage.root, new_stage.plan_path),
        "new-seed-receipts": (new_stage.root, new_stage.receipt_path),
        "retained-seed-plan": (retained_stage.root, retained_stage.plan_path),
        "retained-seed-receipts": (retained_stage.root, retained_stage.receipt_path),
        "new-label-plan": (new_root, "plan.json"),
        "new-label-outcome": (new_root, "outcome.json"),
        "retained-label-plan": (retained_root, "plan.json"),
        "retained-label-outcome": (retained_root, "outcome.json"),
    }
    evaluation = next(
        fit["fit_index"]
        for fit in retained["seed_fits"]
        if fit["excluded_group_indices"] == [0, 1]
    )
    return (
        dict(
            generation_root=generation["root"],
            cases=generation["cases"],
            new_seed_stage=new_stage,
            retained_seed_stage=retained_stage,
            new_label_root=new_root,
            retained_label_root=retained_root,
            outer=0,
            validation=1,
            evaluation_seed_fit_index=evaluation,
            anchors={
                key: _descriptor(root, path) for key, (root, path) in paths.items()
            },
        ),
        generation,
        paths,
    )


def test_authored_whole_original_reader_preserves_files_and_uses_predecessor_not_target_cost(
    tmp_path, module
):
    args, generation, _ = authored_fold_files(tmp_path, module)
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")
    }
    result = module.read_original_prior_work_fold(**args)
    assert result["status"] == "ready"
    assert result["coverage"] == dict(
        selected_total=6, ready=6, unavailable=0, unknown_label=0
    )
    assert result["generation_coverage"] == dict(
        declared_train_target_count=12,
        available_count=8,
        unavailable_count=4,
        six_counter_usable_count=8,
    )
    assert len(result["generation_rows"]) == 12
    assert all(
        "context" not in row and "current_parent" not in row
        for row in result["generation_rows"]
    )
    assert (
        result["tables"]["training"]["seed_policy_hash"]
        == result["evaluation_seed_policy_hash"]
    )
    for row in result["tables"]["training"]["training_rows"]:
        assert row["label"] is True and row["cost_target"] == pytest.approx(0.02)
        sample = next(
            s
            for s in generation["samples"]
            if s["sample_hash"] == row["source_sample_hash"]
        )
        assert row["values"][-6:] == (
            [2, 5, 3, 6, 2, 2] if sample["target_index"] == 1 else [1, 3, 2, 3, 1, 1]
        )
    assert result["claims"]["original_file_correspondence"] is True
    assert all(
        value is False
        for key, value in result["claims"].items()
        if key != "original_file_correspondence"
    )
    assert before == {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")
    }


@pytest.mark.parametrize(
    "key", ["generation-export", "new-seed-receipts", "retained-label-outcome"]
)
def test_predeclared_anchor_mismatch_is_not_a_self_hash_credit(tmp_path, module, key):
    args, _, _ = authored_fold_files(tmp_path, module)
    args["anchors"][key]["sha256"] = _sha(b"different original")
    with pytest.raises(ValueError, match="pin"):
        module.read_original_prior_work_fold(**args)


@pytest.mark.parametrize("field", ["policy_hash", "seed_fit_index", "parent_hash"])
def test_coherently_pinned_foreign_label_lineage_rejects(tmp_path, module, field):
    args, _, paths = authored_fold_files(tmp_path, module)
    root = args["new_label_root"]
    plan = _load(root / "plan.json")
    plan["roster"][0][field] = 999 if field == "seed_fit_index" else _sha(b"foreign")
    _write(root / "plan.json", plan)
    args["anchors"]["new-label-plan"] = _descriptor(*paths["new-label-plan"])
    with pytest.raises(ValueError, match="lineage"):
        module.read_original_prior_work_fold(**args)


@pytest.mark.parametrize("mutation", ["step", "path", "missing_retry", "counter_bool"])
def test_original_step_path_retry_and_exact_counter_links_reject(
    tmp_path, module, mutation
):
    args, _, _ = authored_fold_files(tmp_path, module)
    if mutation in ("step", "path", "counter_bool"):
        base = args["new_label_root"] / "pair-000-repeat-0" / "proposal"
        if mutation == "path":
            path = _load(base / "path.json")
            path["response_history"][0]["authored_response"] = 10.0
            _write(base / "path.json", _seal(path, "path_hash"))
        else:
            name = "step" if mutation == "step" else "outcome"
            value = _load(base / f"000-1-{name}.json")
            if mutation == "step":
                value["trial_solution"]["augmented_coordinates_m"][-1] = 999.0
                _rehash_step(value)
            else:
                value["work"]["core_calls"] = True
            _write(base / f"000-1-{name}.json", value)
    else:
        (args["generation_root"] / "A/generation/reference/000-1-outcome.json").rename(
            args["generation_root"]
            / "A/generation/reference/omitted-outcome-original.json"
        )
    with pytest.raises(ValueError):
        module.read_original_prior_work_fold(**args)


def test_missing_dispatches_hold_without_dropping_generation_or_selected_denominators(
    tmp_path, module
):
    args, _, _ = authored_fold_files(tmp_path, module, assembly=False)
    result = module.read_original_prior_work_fold(**args)
    assert (
        result["status"] == "HOLD"
        and result["tables"] is None
        and result["join_packet"] is None
    )
    assert result["coverage"] == dict(
        selected_total=6, ready=0, unavailable=6, unknown_label=0
    )
    assert (
        len(result["generation_rows"]) == 12
        and result["generation_coverage"]["six_counter_usable_count"] == 0
    )
    assert all(row["unavailable_reason"] for row in result["rows"])
    with pytest.raises(ValueError, match="HOLD"):
        module.fit_original_prior_work_fold(result)


def test_excluded_numeric_perturbation_keeps_training_numbers_and_evaluation_seed_bytes(
    tmp_path, module
):
    first, _, _ = authored_fold_files(tmp_path / "first", module)
    second, _, _ = authored_fold_files(tmp_path / "changed", module, delta=5.0)
    a, b = (
        module.read_original_prior_work_fold(**first),
        module.read_original_prior_work_fold(**second),
    )
    assert a["status"] == b["status"] == "ready"

    # Original directories intentionally give distinct nonnumeric arm bindings.
    # Compare every fitted numeric input/target, not the full mixed evidence packet.
    def fitted_numbers(result):
        table = result["tables"]["training"]
        return {
            "feature_names": table["feature_names"],
            "rows": [
                {
                    key: row[key]
                    for key in ("values", "label", "cost_target", "cost_repetitions")
                }
                for row in table["training_rows"]
            ],
        }

    assert _bytes(fitted_numbers(a)) == _bytes(fitted_numbers(b))
    assert _bytes(a["evaluation_seed_policy"]) == _bytes(b["evaluation_seed_policy"])


def test_tiny_coupled_algebra_fit_freezes_predictions_before_unknown_validation_labels(
    tmp_path, module
):
    args, _, _ = authored_fold_files(tmp_path, module)
    fold = module.read_original_prior_work_fold(**args)
    pair = module.fit_original_prior_work_fold(fold)
    changed = deepcopy(fold)
    for row in changed["tables"]["validation"]["rows"]:
        for repeat in row["cost_repetitions"]:
            repeat["comparison_pass"] = False
            repeat["path_time_ratio"] = None
        row["label"] = None
        row["cost_target"] = None
    _seal(changed, "fold_hash")
    other = module.fit_original_prior_work_fold(changed)
    assert pair["gate_policy_hash"] == other["gate_policy_hash"]
    assert pair["prediction_hash"] == other["prediction_hash"]
    assert pair["validation_scores"]["known_labels"] == 2
    assert other["validation_scores"]["unknown_labels"] == 2
    assert (
        pair["gate_policy"]["ridge"] == 1.0 and pair["gate_policy"]["threshold"] == 0.01
    )
    assert pair["seed_policy_hash"] == pair["gate_policy"]["seed_policy_hash"]
    assert (
        pair["full_training_refit"]
        is pair["original_training_admitted"]
        is pair["full_path_gain"]
        is False
    )
    assert (
        "anchors" not in pair["gate_policy"] and "validation" not in pair["gate_policy"]
    )
    invalid = deepcopy(fold)
    invalid["evaluation_seed_policy_hash"] = _sha(b"foreign seed")
    _seal(invalid, "fold_hash")
    with pytest.raises(ValueError, match="seed binding"):
        module.fit_original_prior_work_fold(invalid)


@pytest.mark.parametrize("kind", ["missing_sample", "truncated_tail"])
def test_coherent_generation_changes_cannot_shrink_full_request_denominator(
    tmp_path, module, kind
):
    (tmp_path / "models").mkdir()
    generation = _generation(
        tmp_path,
        omitted=("A", 2) if kind == "missing_sample" else None,
        truncated=kind == "truncated_tail",
    )
    root = generation["root"]
    # Deliberately absent later-stage files prove rejection occurs at generation.
    dummy = {"path": "must-not-read.json", "sha256": _sha(b"unread"), "byte_length": 1}
    anchors = {key: deepcopy(dummy) for key in module._ANCHORS}
    for key, relative in (
        ("generation-plan", "plan.json"),
        ("generation-samples", "training-samples.json"),
        ("generation-export", "generation-prior-work-export.json"),
    ):
        anchors[key] = _descriptor(root, relative)
    with pytest.raises(ValueError, match="denominator"):
        module.read_original_prior_work_fold(
            generation_root=root,
            cases=generation["cases"],
            new_seed_stage=module.OriginalSeedStage(tmp_path / "uncreated-new"),
            retained_seed_stage=module.OriginalSeedStage(
                tmp_path / "uncreated-retained"
            ),
            new_label_root=tmp_path / "uncreated-new-labels",
            retained_label_root=tmp_path / "uncreated-retained-labels",
            outer=0,
            validation=1,
            evaluation_seed_fit_index=0,
            anchors=anchors,
        )
    assert not (tmp_path / "uncreated-new").exists()


def _update_label_report(args, paths, *, pair=0, repetition=0, mutate):
    root = args["new_label_root"]
    base = root / f"pair-{pair:03d}-repeat-{repetition}"
    report = _load(base / "comparison.json")
    mutate(report, base)
    _write(base / "comparison.json", _seal(report, "report_hash"))
    record = dict(
        pair_index=pair, repetition=repetition, report_hash=report["report_hash"]
    )
    _write(root / f"record-{pair:03d}-{repetition}.json", record)
    outcome = _load(root / "outcome.json")
    for index, old in enumerate(outcome["records"]):
        if (old["pair_index"], old["repetition"]) == (pair, repetition):
            outcome["records"][index] = record
    _write(root / "outcome.json", outcome)
    args["anchors"]["new-label-outcome"] = _descriptor(*paths["new-label-outcome"])


def test_rehashed_path_report_receipt_cannot_credit_stale_comparison_verdict(
    tmp_path, module
):
    args, _, paths = authored_fold_files(tmp_path, module)

    def mutate(report, base):
        path = _load(base / "proposal/path.json")
        path["response_history"][0]["authored_response"] = 4.0
        _write(base / "proposal/path.json", _seal(path, "path_hash"))
        report["arms"]["proposal"] = {
            key: value
            for key, value in path.items()
            if key
            not in {"response_history", "terminal_checkpoint", "preload_response"}
        }

    _update_label_report(args, paths, mutate=mutate)
    with pytest.raises(ValueError, match="response comparison"):
        module.read_original_prior_work_fold(**args)


@pytest.mark.parametrize(
    "kind",
    ["foreign_snapshot", "capture_bool", "capture_outside_path", "reference_capture"],
)
def test_actual_proposal_material_extension_is_required_and_charged_to_correct_arm(
    tmp_path, module, kind
):
    args, _, paths = authored_fold_files(tmp_path, module)

    def mutate(report, base):
        name = "reference" if kind == "reference_capture" else "proposal"
        context_path = base / name / "000-context.json"
        context = _load(context_path)
        if kind == "foreign_snapshot":
            snapshot = json.loads(context["committed_material_state_json"])
            snapshot["parent_state_hash"] = _sha(b"foreign material parent")
            context["committed_material_state_json"] = _bytes(
                _seal(snapshot, "snapshot_hash")
            ).decode()
            _write(context_path, context)
            return
        path = _load(base / name / "path.json")
        path["entries"][0]["committed_material_capture"] = {
            "wall_ns": True
            if kind == "capture_bool"
            else 999
            if kind == "capture_outside_path"
            else 0,
            "cpu_ns": 0,
        }
        _write(base / name / "path.json", _seal(path, "path_hash"))
        report["arms"][name] = {
            key: value
            for key, value in path.items()
            if key
            not in {"response_history", "terminal_checkpoint", "preload_response"}
        }

    _update_label_report(args, paths, mutate=mutate)
    with pytest.raises(ValueError, match="material|capture|parent"):
        module.read_original_prior_work_fold(**args)


def test_original_actual_policy_normalization_is_checked_beyond_complement_hashes(
    tmp_path, module
):
    args, _, paths = authored_fold_files(tmp_path, module)
    stage = args["new_seed_stage"]
    policy_path = stage.root / "seeds/fit-000-policy.json"
    policy = _load(policy_path)
    policy["feature_mean"][0] += 1.0
    _write(policy_path, _seal(policy, "policy_hash"))
    receipts = _load(stage.root / stage.receipt_path)
    receipt = next(row for row in receipts["fits"] if row["fit_index"] == 0)
    receipt["policy_hash"] = policy["policy_hash"]
    receipt["artifact"] = _descriptor(stage.root / "seeds", "fit-000-policy.json")
    _write(stage.root / stage.receipt_path, receipts)
    args["anchors"]["new-seed-receipts"] = _descriptor(*paths["new-seed-receipts"])
    with pytest.raises(ValueError, match="normalization"):
        module.read_original_prior_work_fold(**args)


def test_original_unknown_target_label_stays_separate_from_complete_prior_inputs(
    tmp_path, module
):
    args, _, _ = authored_fold_files(tmp_path, module, unknown_validation=True)
    result = module.read_original_prior_work_fold(**args)
    assert result["status"] == "ready"
    assert result["coverage"] == dict(
        selected_total=6, ready=6, unavailable=0, unknown_label=2
    )
    assert all(
        row["label"] is None and row["cost_target"] is None
        for row in result["tables"]["validation"]["rows"]
    )
    pair = module.fit_original_prior_work_fold(result)
    assert (
        pair["validation_scores"]["declared_rows"]
        == pair["validation_scores"]["unknown_labels"]
        == 2
    )


def test_actual_tiny_generation_and_three_proposal_capture_reports_use_current_consumer(
    tmp_path, module
):
    """Actual authored tiny solver outputs; no four-group or physical validation claim."""
    from structural_analysis.ai.fiber_frame_warm_start_features import (
        decode_fiber_frame_warm_start_model_features,
    )
    from tests.test_rc_control_learning_prior_work_export import _authored_cases

    cases = _authored_cases(tmp_path)
    study = tmp_path / "actual-generation"
    learning_report = learning.run_rc_control_learning_study(
        cases,
        source_revision=REVISION,
        output_directory=study,
        defer_evaluation=True,
        fit_solver=learning.CONSTANT_SAFE_SVD_FIT_PROFILE,
        export_generation_prior_work=True,
        record_generation_assembly_work=True,
    )
    assert learning_report["fit"]["status"] == "completed"
    assert all(
        row["status"] == "not_attempted" for row in learning_report["evaluation"]
    )
    plan, samples = _load(study / "plan.json"), _load(study / "training-samples.json")
    exported = _load(study / "generation-prior-work-export.json")
    case = cases[0]
    sample = next(row for row in samples if row["target_index"] == 1)
    source = deepcopy(
        next(
            row
            for row in exported["rows"]
            if row["source_sample_hash"] == sample["sample_hash"]
        )
    )
    source["context"] = _load(
        study / f"{case.case_id}/generation/reference/001-context.json"
    )
    step = _load(study / f"{case.case_id}/generation/reference/001-1-step.json")
    source["current_parent"] = step["parent_checkpoint"]
    context = module._context(source["context"])
    model = decode_fiber_frame_warm_start_model_features(
        plan["cases"][0]["model_features"]
    )
    compiled, blockers, _ = public._compile(case.model)
    assert compiled is not None and not blockers
    policy = learning.RCControlSeedPolicy((study / "policy.json").read_text())

    def propose(current):
        return policy.propose(
            current,
            model,
            compiled.problem.free_global_dofs,
            case.request.solver_config.contract_hash,
        )

    probes = tmp_path / "actual-three-repeats"
    declaration = dict(target_index=1, policy_hash=policy.policy_hash)
    repeats, artifacts = [], {}
    for repetition in range(3):
        base = f"pair-000-repeat-{repetition}"
        report = runtime.benchmark_rc_control_seed_paths(
            case.model,
            case.request,
            source_revision=REVISION,
            output_directory=probes / base,
            proposal=propose,
            proposal_identity=policy.policy_hash,
            arm_order=tuple(ORDERS[repetition]),
            parent_checkpoint_bytes=_bytes(source["current_parent"]),
            accepted_context=context,
            capture_material_state=True,
            material_capture_scope="proposal-only",
            proposal_abstention_strategy="secant",
        )
        record = dict(
            pair_index=0, repetition=repetition, report_hash=report["report_hash"]
        )
        checked = module._report(
            module._Reader(probes),
            base,
            record,
            declaration,
            case,
            sample,
            source,
            model,
            artifacts,
            REVISION,
        )
        assert checked["comparison_pass"] is True
        assert all(
            type(value) is int and value >= 0 for value in checked["work"].values()
        )
        assert "compiled_problem_contract_hash" not in report
        captured = _load(probes / base / "proposal/000-context.json")
        assert captured["committed_material_state_json"] is not None
        assert sample["context"].get("committed_material_state_json") is None
        assert (
            report["arms"]["proposal"]["entries"][0]["committed_material_capture"][
                "wall_ns"
            ]
            >= 0
        )
        repeats.append(checked)
    assert {row["repetition"] for row in repeats} == {0, 1, 2}
    assert len(artifacts) >= 3 * 4 * 5
    assert learning_report["source_revision_is_attestation"] is False
    _write(
        tmp_path / "actual-producer-compatibility-receipt.json",
        {
            "generation_report_hash": learning_report["report_hash"],
            "repetitions": repeats,
            "actual_report_original_artifacts": artifacts,
            "four_group_original_join_executed": False,
            "source_authenticity": False,
            "dataset_admitted": False,
            "independent_physics": False,
            "full_path_gain": False,
            "scope": "one tiny public authored generation and three same-parent proposal-only captures; retained originals",
        },
    )


FULL_ANCHOR_KEYS = {
    "generation-plan",
    "generation-samples",
    "generation-export",
    "retained-seed-plan",
    "retained-seed-receipts",
    "retained-label-plan",
    "retained-label-outcome",
}


@pytest.fixture(autouse=True)
def _full_training_contracts_do_not_execute_physics(request, monkeypatch):
    if "full_training" not in request.node.name:
        return

    def forbidden(*args, **kwargs):
        raise AssertionError("pure full-training codec contract attempted a solve")

    for owner, name in (
        (runtime, "solve_stateful_fiber_frame2d_displacement_control_step"),
        (runtime, "_execute_preload"),
        (runtime, "benchmark_rc_control_seed_paths"),
        (learning, "benchmark_rc_control_seed_paths"),
        (public, "analyze_public_rc_fiber_frame"),
    ):
        monkeypatch.setattr(owner, name, forbidden)


def _full_training_files(tmp_path, module, **options):
    fold, generation, paths = authored_fold_files(tmp_path, module, **options)
    return (
        {
            key: fold[key]
            for key in (
                "generation_root",
                "cases",
                "retained_seed_stage",
                "retained_label_root",
            )
        }
        | {
            "anchors": {key: deepcopy(fold["anchors"][key]) for key in FULL_ANCHOR_KEYS}
        },
        generation,
        paths,
    )


def _full_training_seed(generation, *, fit_solver=learning.SVD_RIDGE_FIT_PROFILE):
    original = generation["originals"]["A", 1]
    model = original["model_features"]
    profile = dict(
        model_context_hash=model.context_hash,
        model_feature_names=list(model.feature_names),
        free_global_dofs=list(original["free"]),
        control_free_index=original["sample"]["context"]["control_free_index"],
        solver_config_hash=generation["cases"][0].request.solver_config.contract_hash,
    )
    return learning._fit(
        generation["samples"],
        profile,
        10000.0,
        0.1,
        fit_solver=fit_solver,
    )


def test_full_training_all_original_samples_have_one_predeclared_oof_teacher(
    tmp_path, module
):
    args, generation, _ = _full_training_files(tmp_path, module)
    result = module.read_original_prior_work_full_training(**args)
    assert result["status"] == "ready"
    assert result["coverage"]["selected_total"] == 8
    assert result["coverage"]["ready"] == 8 and result["coverage"]["unavailable"] == 0
    assert len(result["generation_rows"]) == 12
    hashes = [row["sample_hash"] for row in generation["samples"]]
    assert len(result["rows"]) == len(hashes)
    assert {row["source_sample_hash"] for row in result["rows"]} == set(hashes)
    assert len({row["source_sample_hash"] for row in result["rows"]}) == 8
    training = result["training"]
    assert training["training_scope"] == "declared_training_only"
    assert training["declared_training_sample_hashes"] == hashes
    assert (
        "outer_group_index" not in training and "validation_group_index" not in training
    )
    assert training["excluded_case_ids"] == []
    assert all(
        row["label"] is True and row["cost_target"] == pytest.approx(0.02)
        for row in training["training_rows"]
    )
    assert result["reference_parent_conditioned"] is True


@pytest.mark.parametrize("key", sorted(FULL_ANCHOR_KEYS))
def test_full_training_each_of_seven_original_pins_is_required(tmp_path, module, key):
    args, _, _ = _full_training_files(tmp_path, module)
    args["anchors"][key]["sha256"] = _sha(b"foreign full-training original")
    with pytest.raises(ValueError, match="pin"):
        module.read_original_prior_work_full_training(**args)


def test_full_training_unknown_prior_inputs_hold_without_reducing_all_train_coverage(
    tmp_path, module
):
    args, _, _ = _full_training_files(tmp_path, module, assembly=False)
    result = module.read_original_prior_work_full_training(**args)
    assert result["status"] == "HOLD"
    assert result["coverage"]["selected_total"] == 8
    assert result["coverage"]["ready"] == 0 and result["coverage"]["unavailable"] == 8
    assert len(result["generation_rows"]) == 12
    assert all(row["unavailable_reason"] for row in result["rows"])
    with pytest.raises(ValueError, match="HOLD"):
        module.fit_original_prior_work_full_training(result)


def test_full_training_teacher_policy_and_fit_are_the_predeclared_directed_complement(
    tmp_path, module
):
    args, generation, _ = _full_training_files(tmp_path, module)
    result = module.read_original_prior_work_full_training(**args)
    roster = _load(args["retained_label_root"] / "plan.json")["roster"]
    groups = _load(args["retained_seed_stage"].root / "plan.json")["groups"]
    expected = {}
    for group, names in enumerate(groups):
        for row in roster:
            if row["inner_group_index"] == group and row["outer_group_index"] == (
                group + 1
            ) % len(groups):
                assert row["case_id"] in names
                expected[row["source_sample_hash"]] = row
    assert len(expected) == len(generation["samples"]) == 8
    for row in result["rows"]:
        original = expected[row["source_sample_hash"]]
        for key in ("case_id", "parent_hash", "policy_hash", "seed_fit_index"):
            assert row[key] == original[key]
    assert {row["source_sample_hash"] for row in result["rows"]} == set(expected)


def _add_unexecuted_nontraining_declarations(args, generation, tmp_path):
    for name, split, ratio, targets in (
        ("authored-validation-unused", "validation", 1.7, (-0.8e-4, 1.3e-4, -0.9e-4)),
        ("authored-holdout-unused", "holdout", 1.9, (-1.2e-4, 0.7e-4, -1.1e-4)),
    ):
        case = make(
            tmp_path / "models",
            name,
            split,
            lengths=(3.0, 3.0 * ratio),
            targets=targets,
        )
        compiled, blockers, _ = public._compile(case.model)
        assert compiled is not None and not blockers
        generation["cases"].append(case)
        generation["declarations"].append(
            dict(
                case_id=name,
                split=split,
                identities={
                    key: getattr(case, key)
                    for key in ("project_id", "geometry_family_id", "load_history_id")
                },
                model_checksum=case.model.canonical_model_checksum,
                request=case.request.to_dict(),
                model_features=fiber_frame_warm_start_model_features(
                    compiled.problem
                ).to_dict(),
            )
        )
    args["cases"] = generation["cases"]
    _refresh_generation_originals(args, generation)


def _refresh_generation_originals(args, generation):
    root = generation["root"]
    _write(
        root / "plan.json",
        dict(source_revision=REVISION, cases=generation["declarations"]),
    )
    _write(root / "training-samples.json", generation["samples"])
    exported = build_generation_prior_work_export(
        study_root=root,
        declarations=generation["declarations"],
        generation=generation["generation"],
        samples=generation["samples"],
        source_revision=REVISION,
    )
    _write(root / "generation-prior-work-export.json", exported)
    for key, relative in (
        ("generation-plan", "plan.json"),
        ("generation-samples", "training-samples.json"),
        ("generation-export", "generation-prior-work-export.json"),
    ):
        args["anchors"][key] = _descriptor(root, relative)


def test_full_training_unexecuted_validation_and_holdout_numbers_cannot_enter_training(
    tmp_path, module
):
    args, generation, _ = _full_training_files(tmp_path, module)
    _add_unexecuted_nontraining_declarations(args, generation, tmp_path)
    first = module.read_original_prior_work_full_training(**args)
    for declaration in generation["declarations"]:
        if declaration["split"] != "train":
            declaration["model_features"]["values"][0] += 1e6
            declaration["unscored_authored_label"] = {"gain": -1e9, "cost": 1e9}
    _refresh_generation_originals(args, generation)
    second = module.read_original_prior_work_full_training(**args)
    assert first["status"] == second["status"] == "ready"
    assert (
        first["coverage"]["selected_total"] == second["coverage"]["selected_total"] == 8
    )
    assert _bytes(first["training"]) == _bytes(second["training"])
    assert (
        first["full_training_pair_factory_identity"]
        == second["full_training_pair_factory_identity"]
    )
    assert all(row["case_id"] in "ABCD" for row in second["rows"])
    # No generation/evaluation original is ever created for these authored declarations.
    assert not list(generation["root"].glob("authored-*-generation-outcome.json"))
    assert not list(generation["root"].glob("authored-*-evaluation*"))


@pytest.mark.parametrize(
    "kind", ["eligible_sample_omitted", "reference_tail_truncated"]
)
def test_full_training_original_request_denominator_cannot_be_coherently_shrunk(
    tmp_path, module, kind
):
    args, generation, _ = _full_training_files(tmp_path, module)
    generation["samples"] = [
        row
        for row in generation["samples"]
        if (row["case_id"], row["target_index"]) != ("A", 2)
    ]
    if kind == "reference_tail_truncated":
        outcome = generation["generation"][0]
        report = outcome["report"]
        report["arms"]["reference"]["entries"].pop()
        report["arms"]["reference"]["accepted_target_count"] = 2
        _seal(report, "report_hash")
        _write(generation["root"] / "A/generation/comparison.json", report)
        _write(generation["root"] / "A-generation-outcome.json", outcome)
    _refresh_generation_originals(args, generation)
    with pytest.raises(ValueError, match="denominator"):
        module.read_original_prior_work_full_training(**args)


def test_full_training_standalone_and_supplied_seed_share_one_exact_immutable_pair(
    tmp_path, module
):
    from rc_prior_work_cost_margin_gate import FullTrainingPriorWorkCostMarginGate

    args, generation, _ = _full_training_files(tmp_path, module)
    verified = module.read_original_prior_work_full_training(**args)
    before = _bytes(verified)
    supplied = _full_training_seed(generation)
    standalone = module.fit_original_prior_work_full_training(verified)
    reused = module.fit_original_prior_work_full_training(verified, policy=supplied)
    assert _bytes(verified) == before
    assert verified["training"]["seed_policy_hash"] is None
    assert standalone["selected_pair"] == reused["selected_pair"]
    assert standalone["seed_policy"] == supplied.to_dict()
    assert standalone["fit_receipt"]["seed_fit_count"] == 1
    assert standalone["fit_receipt"]["gate_fit_count"] == 1
    assert reused["fit_receipt"]["seed_fit_count"] == 0
    assert reused["fit_receipt"]["gate_fit_count"] == 1
    assert reused["fit_receipt"]["seed_supplied_by_selector"] is True
    pair = standalone["selected_pair"]
    assert pair["pair_hash"] == _sha(
        _bytes({key: value for key, value in pair.items() if key != "pair_hash"})
    )
    assert pair["training_sample_hashes"] == [
        row["sample_hash"] for row in generation["samples"]
    ]
    assert pair["seed_policy_hash"] == pair["gate_policy"]["seed_policy_hash"]
    assert pair["seed_policy"]["fit_solver_profile"] == learning.SVD_RIDGE_FIT_PROFILE
    assert pair["seed_policy"]["schema_version"].endswith(".v5")
    assert pair["teacher_roster_hash"] == verified["teacher_roster_hash"]
    assert pair["excluded_case_ids"] == []
    assert pair["full_training_refit"] is True
    assert pair["reference_parent_conditioned"] is True
    assert (
        pair["original_training_admitted"]
        is pair["source_authenticity"]
        is pair["full_path_gain"]
        is pair["independent_validation"]
        is False
    )
    assert (
        not {
            "outer_group_index",
            "validation_group_index",
            "validation_predictions",
            "validation_scores",
        }
        & pair.keys()
    )
    gate = FullTrainingPriorWorkCostMarginGate(_bytes(pair["gate_policy"]).decode())
    assert gate.policy_hash == pair["gate_policy_hash"]
    detached = gate.to_dict()
    detached["weights"][0] += 100.0
    assert gate.to_dict() == pair["gate_policy"]
    detached_seed = supplied.to_dict()
    detached_seed["feature_mean"][0] += 100.0
    assert supplied.to_dict() == pair["seed_policy"]
    for key in (
        "seed_check_wall_ns",
        "seed_check_cpu_ns",
        "gate_fit_wall_ns",
        "gate_fit_cpu_ns",
        "paired_fit_wall_ns",
        "paired_fit_cpu_ns",
    ):
        assert type(reused["fit_receipt"][key]) is int
        assert reused["fit_receipt"][key] >= 0


def test_full_training_unknown_current_labels_remain_in_seed_and_gate_denominators(
    tmp_path, module
):
    args, generation, _ = _full_training_files(
        tmp_path, module, unknown_full_teacher=True
    )
    verified = module.read_original_prior_work_full_training(**args)
    assert verified["status"] == "ready"
    assert verified["coverage"] == dict(
        selected_total=8, ready=8, unavailable=0, unknown_label=2
    )
    assert len(verified["training"]["training_rows"]) == 6
    unknown = verified["training"]["unverified_rows"]
    assert len(unknown) == 2 and all(row["case_id"] == "B" for row in unknown)
    assert all(row["label"] is None and row["cost_target"] is None for row in unknown)
    fitted = module.fit_original_prior_work_full_training(verified)
    assert fitted["training_sample_hashes"] == [
        row["sample_hash"] for row in generation["samples"]
    ]
    gate = fitted["gate_policy"]
    assert gate["declared_training_sample_hashes"] == fitted["training_sample_hashes"]
    assert gate["unverified_sample_hashes"] == [
        row["source_sample_hash"] for row in unknown
    ]
    assert gate["unverified_count"] == 2
    assert len(gate["training_sample_hashes"]) == 6
    assert fitted["fit_receipt"]["declared_rows"] == 8
    assert (
        fitted["seed_policy"]["training_sample_hashes"]
        == fitted["training_sample_hashes"]
    )


@pytest.mark.parametrize(
    "mutation", ["partial", "reordered", "recipe_v6", "ridge", "normalization"]
)
def test_full_training_supplied_seed_must_match_original_recipe_order_and_statistics(
    tmp_path, module, mutation
):
    args, generation, _ = _full_training_files(tmp_path, module)
    verified = module.read_original_prior_work_full_training(**args)
    if mutation in ("partial", "reordered"):
        modified = deepcopy(generation)
        modified["samples"] = (
            modified["samples"][:-1]
            if mutation == "partial"
            else list(reversed(modified["samples"]))
        )
        supplied = _full_training_seed(modified)
    elif mutation == "recipe_v6":
        supplied = _full_training_seed(
            generation, fit_solver=learning.CONSTANT_SAFE_SVD_FIT_PROFILE
        )
    else:
        supplied = _full_training_seed(generation)
        payload = supplied.to_dict()
        if mutation == "ridge":
            payload["ridge"] = 3.0
        else:
            payload["feature_mean"][0] += 1.0
        supplied = learning.RCControlSeedPolicy(
            _bytes(_seal(payload, "policy_hash")).decode()
        )
    with pytest.raises(ValueError):
        module.fit_original_prior_work_full_training(verified, policy=supplied)


def test_full_training_factory_freezes_originals_and_returns_detached_exact_binding(
    tmp_path, module
):
    args, generation, _ = _full_training_files(tmp_path, module)
    verified = module.read_original_prior_work_full_training(**args)
    factory = module.make_original_full_training_pair_factory(verified)
    supplied = _full_training_seed(generation)
    samples = deepcopy(generation["samples"])
    first = factory(policy=supplied, training_samples=samples)
    assert set(first) == {
        "training_scope",
        "seed_policy_hash",
        "gate_policy_hash",
        "gate_policy",
        "training_sample_hashes",
        "fit_receipt",
    }
    assert first["training_scope"] == "declared_training_only"
    assert first["seed_policy_hash"] == supplied.policy_hash
    assert first["gate_policy_hash"] == first["gate_policy"]["policy_hash"]
    assert first["fit_receipt"]["seed_fit_count"] == 0
    assert first["fit_receipt"]["gate_fit_count"] == 1
    verified["training_samples"][0]["features"][0] += 100.0
    verified["training"]["training_rows"][0]["values"][0] += 100.0
    first["gate_policy"]["weights"][0] += 100.0
    first["training_sample_hashes"].clear()
    first["fit_receipt"]["seed_fit_count"] = 999
    second = factory(policy=supplied, training_samples=samples)
    assert second["training_sample_hashes"] == [row["sample_hash"] for row in samples]
    assert second["gate_policy"]["policy_hash"] == second["gate_policy_hash"]
    assert second["gate_policy"]["weights"][0] != first["gate_policy"]["weights"][0]
    assert second["fit_receipt"]["seed_fit_count"] == 0


@pytest.mark.parametrize(
    "mutation", ["omitted", "duplicate", "reordered", "numeric", "foreign_identity"]
)
def test_full_training_factory_rejects_changed_selector_samples(
    tmp_path, module, mutation
):
    args, generation, _ = _full_training_files(tmp_path, module)
    verified = module.read_original_prior_work_full_training(**args)
    factory = module.make_original_full_training_pair_factory(verified)
    samples = deepcopy(generation["samples"])
    if mutation == "omitted":
        samples.pop()
    elif mutation == "duplicate":
        samples[-1] = deepcopy(samples[0])
    elif mutation == "reordered":
        samples.reverse()
    elif mutation == "numeric":
        samples[0]["features"][0] += 1.0
    else:
        samples[0]["case_id"] = "foreign"
    with pytest.raises(ValueError, match="samples differ"):
        factory(policy=_full_training_seed(generation), training_samples=samples)


def test_full_training_fold_result_and_fake_outer_marker_are_rejected(tmp_path, module):
    fold_args, _, _ = authored_fold_files(tmp_path, module)
    fold = module.read_original_prior_work_fold(**fold_args)
    with pytest.raises(ValueError, match="full-training reader"):
        module.fit_original_prior_work_full_training(fold)
    full_args = {
        key: fold_args[key]
        for key in (
            "generation_root",
            "cases",
            "retained_seed_stage",
            "retained_label_root",
        )
    }
    full_args["anchors"] = {key: fold_args["anchors"][key] for key in FULL_ANCHOR_KEYS}
    verified = module.read_original_prior_work_full_training(**full_args)
    verified["training"]["outer_group_index"] = 0
    _seal(verified, "full_training_hash")
    with pytest.raises(ValueError, match="scope"):
        module.fit_original_prior_work_full_training(verified)


def test_full_training_exact_seven_pins_do_not_admit_extra_fold_originals(
    tmp_path, module
):
    args, _, _ = _full_training_files(tmp_path, module)
    args["anchors"]["new-label-plan"] = deepcopy(args["anchors"]["retained-label-plan"])
    with pytest.raises(ValueError, match="predeclared original pins"):
        module.read_original_prior_work_full_training(**args)


@pytest.mark.parametrize(
    "mutation", ["duplicate_sample", "foreign_policy", "foreign_fit", "foreign_parent"]
)
def test_full_training_repinned_label_roster_cannot_substitute_original_teachers(
    tmp_path, module, mutation
):
    args, _, _ = _full_training_files(tmp_path, module)
    label_root = args["retained_label_root"]
    plan = _load(label_root / "plan.json")
    row = plan["roster"][0]
    if mutation == "duplicate_sample":
        plan["roster"][1] = deepcopy(row)
    elif mutation == "foreign_policy":
        row["policy_hash"] = _sha(b"foreign teacher")
    elif mutation == "foreign_fit":
        row["seed_fit_index"] += 1
    else:
        row["parent_hash"] = _sha(b"foreign predecessor")
    _write(label_root / "plan.json", plan)
    args["anchors"]["retained-label-plan"] = _descriptor(label_root, "plan.json")
    with pytest.raises(ValueError):
        module.read_original_prior_work_full_training(**args)


def test_full_training_all_unknown_labels_keep_denominator_and_refuse_fit(
    tmp_path, module
):
    args, generation, _ = _full_training_files(
        tmp_path, module, unknown_full_teacher="all"
    )
    verified = module.read_original_prior_work_full_training(**args)
    assert verified["status"] == "ready"
    assert verified["coverage"] == dict(
        selected_total=8, ready=8, unavailable=0, unknown_label=8
    )
    assert verified["training"]["training_rows"] == []
    assert len(verified["training"]["unverified_rows"]) == 8
    assert verified["training"]["declared_training_sample_hashes"] == [
        row["sample_hash"] for row in generation["samples"]
    ]
    with pytest.raises(ValueError, match="HOLD"):
        module.fit_original_prior_work_full_training(verified)
    with pytest.raises(ValueError, match="HOLD"):
        module.make_original_full_training_pair_factory(verified)


def test_full_training_reader_does_not_read_unselected_triple_stage_files(
    tmp_path, module, monkeypatch
):
    args, _, _ = _full_training_files(tmp_path, module)
    read = module._Reader.read
    observed = []

    def observed_read(reader, relative, artifacts, *, array=False):
        assert reader.root.name not in ("new-seeds", "new-labels")
        observed.append((reader.root, relative))
        return read(reader, relative, artifacts, array=array)

    monkeypatch.setattr(module._Reader, "read", observed_read)
    result = module.read_original_prior_work_full_training(**args)
    assert result["status"] == "ready"
    assert observed
    assert set(result["artifacts"]) == {
        "generation",
        "retained_seeds",
        "retained_labels",
    }
