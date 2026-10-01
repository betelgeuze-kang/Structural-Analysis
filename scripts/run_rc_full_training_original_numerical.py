"""Predeclared authored numerical experiment; no laboratory or release authority.

Run with PYTHONPATH=src:scripts from the repository. Each stage preserves original
producer artifacts and separate enclosing costs. Re-running a completed stage is
rejected, and incomplete stages are never inferred from file presence.
"""

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import subprocess
from time import perf_counter_ns, process_time_ns

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha, _save
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)
from structural_analysis.io.neutral.loader import load_neutral_json

from prepare_rc_nested_switch_labels import fit_declared_seeds, nested_plan
from rc_connected_split_provenance import validate_connected_partition
from rc_prior_work_original_inputs import (
    OriginalSeedStage,
    _context,
    fit_original_prior_work_full_training,
    read_original_prior_work_full_training,
)
from rc_prior_work_cost_margin_gate import (
    FullTrainingPriorWorkCostMarginGate,
    full_training_prior_work_guard_binding,
)
from rc_switch_prefix_features import prefix_features
from run_rc_nested_switch_labels import LABEL_RULE

ARMS = ("reference", "secant", "proposal")
ORDERS = [list(ARMS[i:] + ARMS[:i]) for i in range(3)]
MAX_CALLS = 2048
MAX_SECONDS = 1800
MAX_BYTES = 2 * 1024**3
MAX_FILE_BYTES = 64 * 1024**2
DEFAULT_SOLVER_PROFILE = "default"
EXTENDED_LINE_SEARCH_PROFILE = "extended-backtracking-v1"
SOLVER_PROFILES = (DEFAULT_SOLVER_PROFILE, EXTENDED_LINE_SEARCH_PROFILE)
DEFAULT_ARITHMETIC_PROFILE = "binary64"
ARITHMETIC_PROFILES = (
    DEFAULT_ARITHMETIC_PROFILE,
    learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
)
AUTHORED_RATIOS = (0.55, 0.70, 0.85, 1.0, 1.15, 1.30)


def solver_configuration(profile, *, arithmetic_profile=DEFAULT_ARITHMETIC_PROFILE):
    arithmetic = learning._arithmetic_manifest(arithmetic_profile)
    if type(profile) is not str or profile not in SOLVER_PROFILES:
        raise ValueError("unsupported authored solver profile")
    config = StatefulFiberFrame2DDisplacementControlConfig()
    if profile == EXTENDED_LINE_SEARCH_PROFILE:
        config = replace(
            config,
            newton=replace(
                config.newton,
                line_search_alphas=tuple(2.0**-k for k in range(14)),
            ),
        )
    if arithmetic is not None:
        config = replace(config, newton=replace(config.newton, terminal_polishing=True))
    return config


def arithmetic_profile(plan):
    recipe = plan["seed_recipe"]
    profile = recipe["arithmetic_profile"]
    manifest = learning._arithmetic_manifest(profile)
    assert _bytes(recipe) == _bytes(
        dict(
            ridge=10000.0,
            ood_margin=0.1,
            fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
            feature_profile="legacy",
            arithmetic_profile=profile,
        )
    ), "predeclared arithmetic seed recipe differs"
    assert (
        "arithmetic_profile" not in plan
        if manifest is None
        else _bytes(plan.get("arithmetic_profile")) == _bytes(manifest)
    ), "predeclared arithmetic manifest differs"
    return profile


def authored_case(index, template):
    name, ratio = "authored-" + "ABCDEF"[index], AUTHORED_RATIOS[index]
    payload = deepcopy(template)
    payload["nodes"][1]["coordinates"] = [2.0, 0.0, 0.0]
    payload["nodes"][2]["coordinates"] = [2.0, 2.0 * ratio, 0.0]
    payload["metadata"] = {"case_id": name}
    targets = [
        -0.004,
        -0.008 * (1 + 0.12 * index),
        0.003 * (1 + 0.20 * index),
        0.007 * (1 + 0.08 * index),
        0.0,
        -0.006 * (1 + 0.10 * index),
    ]
    split = "train" if index < 4 else ("validation" if index == 4 else "holdout")
    return name, ratio, payload, targets, split


def solver_payload(config):
    payload = asdict(config)
    payload["newton"]["line_search_alphas"] = list(config.newton.line_search_alphas)
    return payload


def authored_request(targets, config):
    return BoundedRCFiberDirectControlRequest(
        7, tuple(targets), config, allow_reversals=True, maximum_reversals=2
    )


def read(path, *, array=False):
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("bounded numerical original file exceeded")
    value = (
        strict_json_object_bytes(raw, maximum_bytes=MAX_FILE_BYTES)
        if not array
        else learning.json.loads(raw)
    )
    return value


def save(root, name, value):
    return _save(root, name, _bytes(value))


def descriptor(root, name):
    raw = (root / name).read_bytes()
    return dict(path=name, sha256=_sha(raw), byte_length=len(raw))


def cases(root, plan=None):
    if plan is None:
        plan = read(root / "experiment-plan.json")
    profile = arithmetic_profile(plan)
    config = solver_configuration(plan["solver_profile"], arithmetic_profile=profile)
    assert (
        _bytes(plan["solver_config"]) == _bytes(solver_payload(config))
        and plan["solver_config_hash"] == config.contract_hash
    ), "predeclared solver profile differs"
    template = read(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    assert type(plan["cases"]) is list and len(plan["cases"]) == len(AUTHORED_RATIOS), (
        "predeclared authored case roster differs"
    )
    result = []
    for index, row in enumerate(plan["cases"]):
        name, ratio, payload, targets, split = authored_case(index, template)
        assert _bytes(
            [
                row["case_id"],
                row["ratio"],
                row["targets_m"],
                row["split"],
                row["source_role"],
            ]
        ) == _bytes([name, ratio, targets, split, "authored_numerical"]), (
            "predeclared authored case differs"
        )
        assert row["model_file"] == f"models/{name}.json" and _bytes(
            descriptor(root, row["model_file"])
        ) == _bytes(row["model_artifact"]), "predeclared model changed"
        assert _bytes(read(root / row["model_file"])) == _bytes(payload), (
            "predeclared authored model differs"
        )
        request = decode_bounded_rc_fiber_direct_control_request(row["request"])
        assert _bytes(request.to_dict()) == _bytes(row["request"]), (
            "predeclared request is not exact canonical typed payload"
        )
        assert request.request_hash == row["request_hash"] and _bytes(
            request.to_dict()
        ) == _bytes(authored_request(row["targets_m"], config).to_dict()), (
            "predeclared request differs from authored solver profile"
        )
        result.append(
            learning.RCControlLearningCase(
                row["case_id"],
                row["case_id"],
                row["case_id"],
                row["case_id"],
                row["split"],
                load_neutral_json(root / row["model_file"]),
                request,
            )
        )
        assert "model_checksum" not in row or row["model_checksum"] == (
            result[-1].model.canonical_model_checksum
        ), "predeclared model checksum differs"
    return tuple(result)


def prepare(
    root,
    *,
    solver_profile=DEFAULT_SOLVER_PROFILE,
    arithmetic_profile=DEFAULT_ARITHMETIC_PROFILE,
):
    arithmetic = learning._arithmetic_manifest(arithmetic_profile)
    config = solver_configuration(solver_profile, arithmetic_profile=arithmetic_profile)
    root.mkdir(parents=True, exist_ok=False)
    model = read(Path("examples/public_rc_fiber_frame_l_frame_material_history.json"))
    rows = []
    for i in range(len(AUTHORED_RATIOS)):
        name, ratio, payload, targets, split = authored_case(i, model)
        model_file = f"models/{name}.json"
        save(root, model_file, payload)
        rows.append(
            dict(
                case_id=name,
                source_role="authored_numerical",
                split=split,
                model_file=model_file,
                model_artifact=descriptor(root, model_file),
                ratio=ratio,
                targets_m=targets,
            )
        )
        request = authored_request(rows[-1]["targets_m"], config)
        rows[-1].update(request=request.to_dict(), request_hash=request.request_hash)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    plan = dict(
        schema_version="rc-authored-full-training-original-numerical.v1",
        source_revision=revision,
        solver_profile=solver_profile,
        solver_config=solver_payload(config),
        solver_config_hash=config.contract_hash,
        cases=rows,
        groups=[[row["case_id"]] for row in rows[:4]],
        seed_recipe=dict(
            ridge=10000.0,
            ood_margin=0.1,
            fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
            feature_profile="legacy",
            arithmetic_profile=arithmetic_profile,
        ),
        sample_count=20,
        seed_fit_count=6,
        directed_teacher_tasks=12,
        label_pairs=60,
        label_comparisons=180,
        full_path_comparisons=18,
        repetitions=3,
        arm_order_schedule=ORDERS,
        teacher_rule="outer=(canonical connected TRAIN group+1)%G; inner=group",
        label_rule=LABEL_RULE,
        maximum_core_calls=MAX_CALLS,
        maximum_elapsed_seconds=MAX_SECONDS,
        maximum_original_bytes=MAX_BYTES,
        maximum_file_bytes=MAX_FILE_BYTES,
        memory_observation="Linux self VmHWM; separately supervised live VmRSS; no independent hardware attestation",
        maximum_fits=9,
        core_bounds=dict(
            generation=96, original_labels=1080, frozen_full_paths=648, total=1824
        ),
        final_fit_before_evaluation=True,
        evaluation_never_used_for_fit_or_tuning=True,
        incomplete_generation="HOLD; no teacher fit or copied labels; preserve original outcomes",
        unknown_labels="remain in denominator; no forced positive or waived OOD",
        fit_failure="HOLD; repeat deterministic full paths without candidate-performance credit",
        capture_scope="proposal-only in label/full comparison; own-arm predecessor recorded in full paths",
        cost_policy="stage clocks enclose component clocks; never sum nested scopes",
        minimum_full_path_benefit=0.01,
        claims=dict(
            independent_physics=False,
            dataset_admitted=False,
            authenticated_producer=False,
            hardware_attestation=False,
            release_qualified=False,
            learned_gain=False,
        ),
        driver_artifact=dict(
            sha256=_sha(Path(__file__).read_bytes()),
            byte_length=Path(__file__).stat().st_size,
        ),
    )
    if arithmetic is not None:
        plan["arithmetic_profile"] = arithmetic
    declared = cases(root, plan)
    screen = learning._preflight(declared, arithmetic_profile)
    connected = control_training_exclusion_groups(declared)
    assert connected["groups"] == plan["groups"], "predeclared connected groups differ"
    plan["connected_training_screen"] = connected
    for row, case in zip(rows, declared):
        assert descriptor(root, row["model_file"]) == row["model_artifact"]
        row.update(
            model_checksum=case.model.canonical_model_checksum,
            request=case.request.to_dict(),
        )
    plan["cases"] = rows
    plan["preflight_pass"] = True
    plan["case_static_features"] = {
        name: values[2].to_dict() for name, values in screen.items()
    }
    save(root, "experiment-plan.json", plan)
    return dict(status="prepared", plan_hash=_sha(_bytes(plan)), structural_solves=0)


def counted(reports):
    result = Counter(core_calls=0, newton_iterations=0, linear_solves=0)
    unknown = False
    for report in reports:
        unknown |= not report["all_execution_work_reported"]
        for arm in (*report["arms"].values(), report["fresh_reference"]):
            for invocation in [
                *arm.get("preload_invocations", []),
                *(v for entry in arm["entries"] for v in entry["invocations"]),
            ]:
                unknown |= invocation["unknown_work"]
                for key, value in invocation["work"].items():
                    if key in result and type(value) is int and value >= 0:
                        result[key] += value
                    elif key in result:
                        unknown = True
    return dict(known_completed_work=dict(result), unknown_work=unknown)


def save_progress(root, name, value):
    """Replace only the owned convenience index; immutable originals stay separate."""
    temporary = root / (name + ".next")
    with temporary.open("xb") as stream:
        stream.write(_bytes(value))
    temporary.replace(root / name)


def learning_kwargs(profile):
    # Preserve the original default call and binary64 manifest.
    return (
        {}
        if learning._arithmetic_manifest(profile) is None
        else {"arithmetic_profile": profile}
    )


def seed_header(seed, plan, prepared):
    manifest = learning._arithmetic_manifest(arithmetic_profile(plan))
    assert _bytes(seed.get("arithmetic_profile")) == _bytes(manifest), (
        "original seed arithmetic profile differs"
    )
    header = {
        key: seed[key]
        for key in (
            "model_context_hash",
            "model_feature_names",
            "free_global_dofs",
            "control_free_index",
            "solver_config_hash",
        )
    }
    for _, compiled, features, _, _ in prepared.values():
        expected = dict(
            model_context_hash=features.context_hash,
            model_feature_names=list(features.feature_names),
            free_global_dofs=list(compiled.problem.free_global_dofs),
            control_free_index=compiled.problem.free_global_dofs.index(
                plan["cases"][0]["request"]["control_global_dof"]
            ),
            solver_config_hash=plan["solver_config_hash"],
        )
        assert _bytes(header) == _bytes(expected), "original seed native header differs"
    if manifest is not None:
        header["arithmetic_profile"] = deepcopy(manifest)
    return header


def generate(root):
    plan = read(root / "experiment-plan.json")
    profile = arithmetic_profile(plan)
    report = learning.run_rc_control_learning_study(
        cases(root),
        source_revision=plan["source_revision"],
        output_directory=root / "generation",
        ridge=10000.0,
        ood_margin=0.1,
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
        defer_evaluation=True,
        export_generation_prior_work=True,
        record_generation_assembly_work=True,
        **learning_kwargs(profile),
    )
    samples = read(root / "generation/training-samples.json", array=True)
    original = [row["report"] for row in report["generation"] if "report" in row]
    eligible = len(samples) == plan["sample_count"] and all(
        row["labels_eligible"]
        and row["report"]["arms"]["reference"]["status"] == "complete"
        for row in report["generation"]
    )
    eligible = (
        eligible
        and report["fit"] is not None
        and report["fit"]["status"] == "completed"
        and not counted(original)["unknown_work"]
    )
    if eligible:
        policy = learning.RCControlSeedPolicy(
            (root / "generation/policy.json").read_text()
        )
        assert policy.policy_hash == report["fit"]["policy_hash"], (
            "generation fit receipt differs"
        )
        seed_header(policy.to_dict(), plan, learning._preflight(cases(root), profile))
    return dict(
        status="ready" if eligible else "HOLD",
        sample_count=len(samples),
        generation_report_hash=report["report_hash"],
        fit=report["fit"],
        **counted(original),
    )


def labels(root):
    assert read(root / "generate-result.json")["status"] == "ready", "generation HOLD"
    plan = read(root / "experiment-plan.json")
    arithmetic = arithmetic_profile(plan)
    generation = root / "generation"
    samples = read(generation / "training-samples.json", array=True)
    nested = nested_plan(plan["groups"], samples)
    provenance = validate_connected_partition(
        cases=cases(root), source_samples=samples, groups=nested["groups"]
    )
    save(root, "connected-training-provenance.json", provenance)
    stage = root / "retained-seeds"
    save(stage, "plan.json", nested)
    seed = learning.RCControlSeedPolicy(
        (generation / "policy.json").read_text()
    ).to_dict()
    prepared = learning._preflight(cases(root), arithmetic)
    profile = seed_header(seed, plan, prepared)
    if learning._arithmetic_manifest(arithmetic) is not None:
        assert _bytes(read(generation / "plan.json").get("arithmetic_profile")) == (
            _bytes(profile["arithmetic_profile"])
        ), "original generation arithmetic profile differs"
        for sample in samples:
            assert _bytes(sample.get("arithmetic_profile")) == _bytes(
                profile["arithmetic_profile"]
            ) and sample.get("label_representation") == (
                "accepted-high-component-for-binary64-start.v1"
            ), "original sample arithmetic profile differs"
            assert sample["context"]["problem_contract_hash"] == (
                prepared[sample["case_id"]][2].problem_contract_hash
            ), "original sample native problem differs"
    receipts = fit_declared_seeds(nested, samples, profile, stage / "seeds")
    policies = {
        row["fit_index"]: learning.RCControlSeedPolicy(
            (stage / "seeds" / f"fit-{row['fit_index']:03d}-policy.json").read_text()
        )
        for row in receipts
    }
    by_sample = {row["sample_hash"]: row for row in samples}
    by_case = {case.case_id: case for case in cases(root)}
    objects, roster = [], []
    for task_index, task in enumerate(nested["label_tasks"]):
        for sample_hash in task["label_source_sample_hashes"]:
            sample = by_sample[sample_hash]
            case, policy = by_case[sample["case_id"]], policies[task["seed_fit_index"]]
            base = (
                generation
                / case.case_id
                / "generation/reference"
                / f"{sample['target_index']:03d}"
            )
            context = _context(read(Path(str(base) + "-context.json")))
            parent = read(Path(str(base) + "-1-step.json"))["parent_checkpoint"]
            features = prepared[case.case_id][2]
            roster.append(
                dict(
                    task_index=task_index,
                    case_id=case.case_id,
                    target_index=sample["target_index"],
                    seed_fit_index=task["seed_fit_index"],
                    policy_hash=policy.policy_hash,
                    source_sample_hash=sample_hash,
                    parent_hash=sample["parent_hash"],
                    outer_group_index=task["outer_group_index"],
                    inner_group_index=task["inner_group_index"],
                    guard_features=prefix_features(context, features),
                )
            )
            objects.append((case, policy, context, _bytes(parent)))
    label_root = root / "retained-labels"
    save(
        label_root,
        "plan.json",
        dict(
            source_revision=plan["source_revision"],
            roster=roster,
            label_rule=LABEL_RULE,
            repetitions=3,
            gate_trained=False,
            reserved_evaluation=False,
            complete_path_claim=False,
            feature_capture_charged_to_proposal=True,
            arm_order_schedule=ORDERS,
        ),
    )
    records, work = [], []
    for pair_index, (case, policy, context, parent) in enumerate(objects):
        _, compiled, features, _, _ = prepared[case.case_id]

        def propose(current):
            return policy.propose(
                current,
                features,
                compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                **learning_kwargs(arithmetic),
            )

        for repetition in range(3):
            check_budget(root, next_calls=6)
            report = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision=plan["source_revision"],
                output_directory=label_root
                / f"pair-{pair_index:03d}-repeat-{repetition}",
                proposal=propose,
                proposal_identity=policy.policy_hash,
                arm_order=tuple(ORDERS[repetition]),
                parent_checkpoint_bytes=parent,
                accepted_context=context,
                capture_material_state=True,
                material_capture_scope="proposal-only",
                proposal_abstention_strategy="secant",
                **learning._arithmetic_kwargs(arithmetic),
            )
            record = dict(
                pair_index=pair_index,
                repetition=repetition,
                report_hash=report["report_hash"],
            )
            save(label_root, f"record-{pair_index:03d}-{repetition}.json", record)
            records.append(record)
            work.append(counted([report]))
            save_progress(
                root,
                "label-progress.json",
                dict(
                    completed=len(records),
                    planned=180,
                    last=record,
                    unknown_work=any(row["unknown_work"] for row in work),
                    work=dict(
                        sum(
                            (Counter(r["known_completed_work"]) for r in work),
                            Counter(),
                        )
                    ),
                ),
            )
            print(f"label {len(records)}/180", flush=True)
    save(
        label_root,
        "outcome.json",
        dict(records=records, reserved_evaluation=False, gate_trained=False),
    )
    return dict(
        status="completed",
        comparisons=len(records),
        fits=len(receipts),
        known_completed_work=dict(
            sum((Counter(row["known_completed_work"]) for row in work), Counter())
        ),
        unknown_work=any(row["unknown_work"] for row in work),
    )


def join_fit(root):
    plan = read(root / "experiment-plan.json")
    arithmetic = arithmetic_profile(plan)
    declared = cases(root)
    original_seed = learning.RCControlSeedPolicy(
        (root / "generation/policy.json").read_text()
    ).to_dict()
    seed_header(original_seed, plan, learning._preflight(declared, arithmetic))
    anchors = {}
    for key, folder, file in (
        ("generation-plan", "generation", "plan.json"),
        ("generation-samples", "generation", "training-samples.json"),
        ("generation-export", "generation", "generation-prior-work-export.json"),
        ("retained-seed-plan", "retained-seeds", "plan.json"),
        ("retained-seed-receipts", "retained-seeds", "seeds/fit-receipts.json"),
        ("retained-label-plan", "retained-labels", "plan.json"),
        ("retained-label-outcome", "retained-labels", "outcome.json"),
    ):
        anchors[key] = descriptor(root / folder, file)
    save(root, "original-input-anchors.json", anchors)
    verified = read_original_prior_work_full_training(
        generation_root=root / "generation",
        cases=declared,
        retained_seed_stage=OriginalSeedStage(root / "retained-seeds"),
        retained_label_root=root / "retained-labels",
        anchors=anchors,
    )
    save(root, "full-training-original-join.json", verified)
    training = verified["training"]
    if verified["status"] != "ready" or not training["training_rows"]:
        return dict(
            status="HOLD", coverage=verified["coverage"], candidate_fitted=False
        )
    fit_wall, fit_cpu = perf_counter_ns(), process_time_ns()
    save(
        root,
        "full-pair-fit-started.json",
        dict(
            seed_fit_reserved=1,
            gate_fit_reserved=1,
            unknown_fit_work_until_outcome=True,
        ),
    )
    try:
        pair = fit_original_prior_work_full_training(verified)
    except Exception as error:
        return dict(
            status="HOLD",
            coverage=verified["coverage"],
            candidate_fitted=False,
            fit_failure=dict(kind=type(error).__name__, message=str(error)),
            unknown_fit_work=True,
            structural_calls=0,
            fit_attempt_wall_ns=perf_counter_ns() - fit_wall,
            fit_attempt_cpu_ns=process_time_ns() - fit_cpu,
        )
    save(root, "frozen-candidate-pair.json", pair)
    return dict(
        status="completed",
        coverage=verified["coverage"],
        candidate_fitted=True,
        positive_count=training["verified_positive_count"],
        negative_count=training["verified_negative_count"],
        pair_hash=pair["pair_hash"],
        candidate_artifact=descriptor(root, "frozen-candidate-pair.json"),
        fit_receipt=pair["fit_receipt"],
        promoted=False,
    )


def evaluate(root):
    plan = read(root / "experiment-plan.json")
    arithmetic = arithmetic_profile(plan)
    result = read(root / "join-fit-result.json")
    pair = (
        read(root / "frozen-candidate-pair.json")
        if result["candidate_fitted"]
        else None
    )
    if pair:
        assert (
            descriptor(root, "frozen-candidate-pair.json")
            == result["candidate_artifact"]
        ), "completed candidate bytes differ"
        selected = deepcopy(pair["selected_pair"])
        pair_hash = selected.pop("pair_hash")
        assert (
            _sha(_bytes(selected))
            == pair_hash
            == result["pair_hash"]
            == pair["pair_hash"]
        ), "completed candidate hash differs"
        assert all(
            _bytes(pair[key]) == _bytes(value)
            for key, value in pair["selected_pair"].items()
        ), "flattened candidate differs"
    frozen = _bytes(pair) if pair else None
    policy = (
        learning.RCControlSeedPolicy(_bytes(pair["seed_policy"]).decode())
        if pair
        else None
    )
    gate = (
        FullTrainingPriorWorkCostMarginGate(_bytes(pair["gate_policy"]).decode())
        if pair
        else None
    )
    prepared = learning._preflight(cases(root), arithmetic)
    if policy is not None:
        seed_header(policy.to_dict(), plan, prepared)
    records, reports = [], []
    for case in cases(root):
        _, compiled, features, _, _ = prepared[case.case_id]

        def propose(context):
            return policy.propose(
                context,
                features,
                compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                **learning_kwargs(arithmetic),
            )

        for repetition in range(3):
            check_budget(root, next_calls=36)
            options, binding_wall = {}, 0
            if pair:
                binding_started = perf_counter_ns()
                binding = full_training_prior_work_guard_binding(
                    gate, policy=policy, model_features=features
                )
                binding_wall = perf_counter_ns() - binding_started
                options = dict(
                    proposal=propose,
                    proposal_identity=policy.policy_hash,
                    proposal_guard=binding["guard"],
                    proposal_guard_identity=binding["guard_identity"],
                    capture_material_state=True,
                    material_capture_scope="proposal-only",
                    proposal_abstention_strategy="secant",
                    record_prior_accepted_transition_work=True,
                    record_assembly_work=True,
                    record_assembly_timing=True,
                )
            order = (
                tuple(ORDERS[repetition])
                if pair
                else (
                    ("reference", "secant")
                    if repetition % 2 == 0
                    else ("secant", "reference")
                )
            )
            report = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision=plan["source_revision"],
                output_directory=root / "full-paths" / f"{case.case_id}-{repetition}",
                arm_order=order,
                **options,
                **learning._arithmetic_kwargs(arithmetic),
            )
            assert (
                pair is None
                or _bytes(read(root / "frozen-candidate-pair.json")) == frozen
            )
            comparisons = report["comparisons"]
            eligible = (
                report["all_execution_work_reported"]
                and report["reference_repeat_exact"]
                and all(row["full_history_pass"] for row in comparisons.values())
            )
            records.append(
                dict(
                    case_id=case.case_id,
                    split=case.split,
                    repetition=repetition,
                    report_hash=report["report_hash"],
                    comparison_pass=eligible,
                    exact_terminal={
                        k: v["exact_terminal_checkpoint"]
                        for k, v in comparisons.items()
                    },
                    arms={
                        k: {
                            "wall_ns": v["wall_ns"],
                            "cpu_ns": v["cpu_ns"],
                            "status": v["status"],
                            "decisions": dict(
                                Counter(
                                    e["proposal_decision"]
                                    for e in v["entries"]
                                    if "proposal_decision" in e
                                )
                            ),
                        }
                        for k, v in report["arms"].items()
                    },
                    path_time_ratio=(
                        report["arms"]["proposal"]["wall_ns"]
                        / report["arms"]["secant"]["wall_ns"]
                    )
                    if pair and eligible
                    else None,
                    path_time_ratio_scope="proposal arm including capture/guard/inference/solve/io divided by secant arm; excludes setup and offline costs",
                    guard_binding_wall_ns=binding_wall,
                    prior_work_source_setup_cost=report.get(
                        "prior_work_source_setup_cost"
                    ),
                    conservative_online_time_ratio=(
                        report["arms"]["proposal"]["wall_ns"]
                        + binding_wall
                        + report["prior_work_source_setup_cost"]["wall_ns"]
                    )
                    / report["arms"]["secant"]["wall_ns"]
                    if pair and eligible
                    else None,
                    online_score_scope="entire shared causal source setup charged to candidate plus binding and whole candidate arm; offline costs separate",
                )
            )
            reports.append(report)
            save_progress(
                root,
                "full-path-progress.json",
                dict(records=records, planned=18, **counted(reports)),
            )
            print(f"full path {len(records)}/18", flush=True)
    save(
        root,
        "full-path-outcome.json",
        dict(
            records=records,
            candidate_frozen_before_evaluation=bool(pair),
            no_selection_or_refit_from_validation_or_holdout=True,
        ),
    )
    return dict(
        status="completed",
        candidate_evaluated=bool(pair),
        comparisons=len(records),
        verified=sum(row["comparison_pass"] for row in records),
        **counted(reports),
    )


def check_budget(root, *, next_calls=0):
    started = read(root / "campaign-started.json")["monotonic_ns"]
    assert (perf_counter_ns() - started) / 1e9 < MAX_SECONDS, (
        "predeclared time budget reached"
    )
    assert sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) < MAX_BYTES, (
        "original byte budget reached"
    )
    used = 0
    for complete, progress in (
        ("generate-result.json", None),
        ("labels-result.json", "label-progress.json"),
        ("evaluate-result.json", "full-path-progress.json"),
    ):
        path = root / complete
        if not path.exists() and progress is not None:
            path = root / progress
        if path.exists():
            receipt = read(path)
            assert not receipt.get("unknown_work", False), (
                "unknown native work; stop budget reuse"
            )
            used += receipt.get("known_completed_work", receipt.get("work", {})).get(
                "core_calls", 0
            )
    assert used + next_calls <= MAX_CALLS, "predeclared native call budget reached"
    assert peak_rss_bytes() < MAX_BYTES, "memory observation budget reached"


def peak_rss_bytes():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) * 1024
    raise ValueError("Linux process memory observation unavailable")


def main():
    if not __debug__:
        raise ValueError("optimized Python cannot run assertion-bound research stages")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=("prepare", "generate", "labels", "join-fit", "evaluate")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver-profile", choices=SOLVER_PROFILES)
    parser.add_argument("--arithmetic-profile", choices=ARITHMETIC_PROFILES)
    args = parser.parse_args()
    if args.stage != "prepare" and args.solver_profile is not None:
        parser.error("--solver-profile is only available for prepare")
    if args.stage != "prepare" and args.arithmetic_profile is not None:
        parser.error("--arithmetic-profile is only available for prepare")
    root = args.output.resolve()
    if args.stage != "prepare":
        assert not (root / f"{args.stage}-started.json").exists(), (
            "stage already attempted; inspect original status"
        )
        plan = read(root / "experiment-plan.json")
        assert _sha(_bytes(plan)) == read(root / "prepare-result.json")["plan_hash"], (
            "predeclared plan changed"
        )
        assert descriptor(Path(__file__).parent, Path(__file__).name) == dict(
            path=Path(__file__).name, **plan["driver_artifact"]
        ), "predeclared driver changed"
        for row in plan["cases"]:
            assert descriptor(root, row["model_file"]) == row["model_artifact"], (
                "predeclared model changed"
            )
        cases(root, plan)
        assert (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            == plan["source_revision"]
        )
        if args.stage == "generate":
            save(root, "campaign-started.json", dict(monotonic_ns=perf_counter_ns()))
        check_budget(root, next_calls=96 if args.stage == "generate" else 0)
        save(
            root,
            f"{args.stage}-started.json",
            dict(status="started", unknown_work_until_outcome=True),
        )
    wall, cpu = perf_counter_ns(), process_time_ns()
    try:
        function = globals()[args.stage.replace("-", "_")]
        result = (
            function(
                root,
                solver_profile=args.solver_profile or DEFAULT_SOLVER_PROFILE,
                arithmetic_profile=args.arithmetic_profile
                or DEFAULT_ARITHMETIC_PROFILE,
            )
            if args.stage == "prepare"
            else function(root)
        )
        result.update(
            stage_wall_ns=perf_counter_ns() - wall,
            stage_cpu_ns=process_time_ns() - cpu,
            timing_scope="enclosing stage includes component read/preparation/fit/solve/io; excludes final receipt",
            process_peak_rss_bytes=peak_rss_bytes(),
        )
        save(root, f"{args.stage}-result.json", result)
        print(learning.json.dumps(result), flush=True)
    except Exception as error:
        save(
            root,
            f"{args.stage}-failure.json",
            dict(
                kind=type(error).__name__,
                message=str(error),
                unknown_unreported_work=True,
                stage_wall_ns=perf_counter_ns() - wall,
                stage_cpu_ns=process_time_ns() - cpu,
            ),
        )
        raise


if __name__ == "__main__":
    main()
