"""Request and frozen-arm contract checks; no solver or worker execution."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_candidate_process as process
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arms
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameMaterialPrices,
    FiberFrameSectionChange,
    FiberFrameTerminalLimits,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIXTURES = Path(__file__).parent / "fixtures/fiber_frame_candidate_process"
SOURCE = "a" * 40


@pytest.fixture(autouse=True)
def forbid_solver_and_workers(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("contract-only test must not execute a solver or worker")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(learning, "train_fiber_frame_candidate_policy", forbidden)
    return calls


@pytest.fixture
def request_file(tmp_path):
    training_bytes = (FIXTURES / "training.json").read_bytes()
    training = json.loads(training_bytes)
    targets = [row["targets"] for row in training["samples"] if row["split"] == "train"]
    limits = FiberFrameTerminalLimits(
        *(sum(row[index] for row in targets) / len(targets) for index in range(2))
    )
    (tmp_path / "training.json").write_bytes(training_bytes)
    (tmp_path / "model.json").write_bytes((FIXTURES / "base.json").read_bytes())
    payload = {
        "schema_version": "rc-fiber-candidate-process-suite-request.v1",
        "cases": [
            {
                "case_id": "case-a",
                "model_file": "model.json",
                "training_file": "training.json",
                "candidates": [
                    asdict(
                        FiberFrameDesignCandidate(
                            candidate_id,
                            (FiberFrameSectionChange("RC1", width_m=width),),
                        )
                    )
                    for candidate_id, width in (
                        ("candidate-a", 0.36),
                        ("candidate-b", 0.395),
                    )
                ],
                "configuration": asdict(
                    public_api.PublicRCFiberFrameConfig(load_steps=2)
                ),
                "prices": asdict(
                    FiberFrameMaterialPrices(
                        100.0, 1.0, "KRW", "2026-09-08", "contract-only declared prices"
                    )
                ),
                "terminal_limits": asdict(limits),
                "history_limits": None,
                "full_analysis_budget": 2,
                "exploration_slots": 1,
            }
        ],
        "repetitions": 2,
        "warmups": 0,
        "oracle_audit": False,
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _request(path, mutate):
    payload = json.loads(path.read_bytes())
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _freeze(path, output, *, source_revision=SOURCE):
    output.mkdir()
    return process._freeze_inputs(path, output, source_revision=source_revision)


def _typed_case(path):
    """Reconstruct preserved test inputs; fitting and label collection are forbidden."""
    row = json.loads(path.read_bytes())["cases"][0]
    arguments = process._case_arguments(row, path.parent)
    baseline, candidates = arguments.pop("baseline"), arguments.pop("candidates")
    return baseline, candidates, {**arguments, "source_revision": SOURCE}


INVALID_REQUESTS = [
    ("wrong schema", lambda row: row.update(schema_version="unsupported.v1")),
    ("unknown suite field", lambda row: row.update(extra=True)),
    ("missing suite field", lambda row: row.pop("oracle_audit")),
    ("empty cases", lambda row: row.update(cases=[])),
    ("non-list cases", lambda row: row.update(cases={})),
    ("duplicate case", lambda row: row["cases"].append(deepcopy(row["cases"][0]))),
    ("unknown case field", lambda row: row["cases"][0].update(extra=True)),
    ("missing case field", lambda row: row["cases"][0].pop("history_limits")),
    ("unstable case ID", lambda row: row["cases"][0].update(case_id="../case")),
    ("boolean repetitions", lambda row: row.update(repetitions=True)),
    ("float repetitions", lambda row: row.update(repetitions=2.0)),
    ("odd repetitions", lambda row: row.update(repetitions=3)),
    ("zero repetitions", lambda row: row.update(repetitions=0)),
    ("excess repetitions", lambda row: row.update(repetitions=34)),
    ("boolean warmups", lambda row: row.update(warmups=False)),
    ("float warmups", lambda row: row.update(warmups=0.0)),
    ("negative warmups", lambda row: row.update(warmups=-1)),
    ("excess warmups", lambda row: row.update(warmups=6)),
    ("nonboolean oracle", lambda row: row.update(oracle_audit=1)),
    ("boolean budget", lambda row: row["cases"][0].update(full_analysis_budget=True)),
    ("float budget", lambda row: row["cases"][0].update(full_analysis_budget=2.0)),
    (
        "baseline-only budget",
        lambda row: row["cases"][0].update(full_analysis_budget=1),
    ),
    ("boolean exploration", lambda row: row["cases"][0].update(exploration_slots=True)),
    (
        "out of budget exploration",
        lambda row: row["cases"][0].update(exploration_slots=2),
    ),
    ("boolean model path", lambda row: row["cases"][0].update(model_file=True)),
    ("empty model path", lambda row: row["cases"][0].update(model_file="")),
    ("missing model", lambda row: row["cases"][0].update(model_file="missing.json")),
    ("boolean training path", lambda row: row["cases"][0].update(training_file=False)),
    (
        "unknown config field",
        lambda row: row["cases"][0]["configuration"].update(extra=True),
    ),
    (
        "boolean load steps",
        lambda row: row["cases"][0]["configuration"].update(load_steps=True),
    ),
    ("unknown price field", lambda row: row["cases"][0]["prices"].update(extra=True)),
    (
        "boolean price",
        lambda row: row["cases"][0]["prices"].update(concrete_per_m3=True),
    ),
    (
        "unknown limit field",
        lambda row: row["cases"][0]["terminal_limits"].update(extra=True),
    ),
    (
        "unknown candidate field",
        lambda row: row["cases"][0]["candidates"][0].update(extra=True),
    ),
    (
        "duplicate candidate",
        lambda row: row["cases"][0]["candidates"].append(
            deepcopy(row["cases"][0]["candidates"][0])
        ),
    ),
    (
        "unknown section field",
        lambda row: row["cases"][0]["candidates"][0]["changes"][0].update(extra=True),
    ),
    (
        "boolean section count",
        lambda row: row["cases"][0]["candidates"][0]["changes"][0].update(
            top_bar_count=True
        ),
    ),
]


@pytest.mark.parametrize(
    "_name,mutate", INVALID_REQUESTS, ids=[row[0] for row in INVALID_REQUESTS]
)
def test_request_is_rejected_before_worker_launch(
    request_file, tmp_path, mutate, _name
):
    _request(request_file, mutate)
    with pytest.raises((ValueError, OSError)):
        _freeze(request_file, tmp_path / "output")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace("{", '{"warmups":0,', 1),
        lambda raw: raw.replace('"warmups": 0', '"warmups": NaN'),
        lambda raw: raw.replace('"warmups": 0', '"warmups": 1e400'),
        lambda raw: raw[:-1],
    ],
    ids=["duplicate field", "NaN", "infinite exponent", "truncated JSON"],
)
def test_invalid_json_is_rejected_before_worker_launch(request_file, tmp_path, mutate):
    original = request_file.read_text(encoding="utf-8")
    changed = mutate(original)
    assert changed != original
    request_file.write_text(changed, encoding="utf-8")
    with pytest.raises(ValueError):
        _freeze(request_file, tmp_path / "output")


@pytest.mark.parametrize("revision", [True, None, "", "main", "a" * 39, "g" * 40])
def test_invalid_source_revision_cannot_reach_worker(request_file, tmp_path, revision):
    with pytest.raises(ValueError):
        _freeze(request_file, tmp_path / "output", source_revision=revision)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["cost_accounting"].update(training_wall_ns=True),
        lambda row: row["cost_accounting"].update(full_analysis_request_count=4.0),
        lambda row: row["policy"].update(extra=True),
        lambda row: row["samples"][0].update(sample_hash="sha256:" + "0" * 64),
    ],
    ids=["boolean cost", "floating count", "unknown policy field", "sample binding"],
)
def test_rehashed_training_corruption_is_rejected_before_worker(
    request_file, tmp_path, mutate
):
    training_path = tmp_path / "training.json"
    training = json.loads(training_path.read_bytes())
    mutate(training)
    training["report_hash"] = canonical_hash(
        {key: value for key, value in training.items() if key != "report_hash"}
    )
    training_path.write_text(json.dumps(training), encoding="utf-8")
    with pytest.raises(ValueError):
        _freeze(request_file, tmp_path / "output")


def test_frozen_input_paths_preserve_original_bytes_after_caller_files_change(
    request_file, tmp_path, forbid_solver_and_workers
):
    originals = {
        key: (tmp_path / name).read_bytes()
        for key, name in (
            ("model_file", "model.json"),
            ("training_file", "training.json"),
        )
    }
    frozen = _freeze(request_file, tmp_path / "output")
    assert frozen["configuration"] == {
        "repetitions": 2,
        "warmups": 0,
        "oracle_audit": False,
    }
    assert [row["case_id"] for row in frozen["cases"]] == ["case-a"]
    for key, raw in originals.items():
        original_name = "model.json" if key == "model_file" else "training.json"
        original_path = tmp_path / original_name
        snapshot_path = Path(frozen["cases"][0]["request"][key])
        assert snapshot_path != original_path
        assert snapshot_path.is_relative_to(tmp_path / "output")
        assert snapshot_path.read_bytes() == raw
        original_path.write_bytes(b"changed after preflight")
        assert snapshot_path.read_bytes() == raw
        identities = [
            row for row in frozen["identities"] if Path(row["path"]) == snapshot_path
        ]
        assert len(identities) == 1
        assert identities[0]["byte_length"] == len(raw)
        assert identities[0]["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert forbid_solver_and_workers == []


def test_distinct_cases_keep_separate_plans_and_charge_shared_training_once(
    request_file, tmp_path
):
    def declare_second_case(row):
        second = deepcopy(row["cases"][0])
        second["case_id"] = "case-b"
        row["cases"].append(second)
        row.update(repetitions=32, warmups=5, oracle_audit=True)

    _request(request_file, declare_second_case)
    frozen = _freeze(request_file, tmp_path / "output")
    assert frozen["configuration"] == {
        "repetitions": 32,
        "warmups": 5,
        "oracle_audit": True,
    }
    assert [case["case_id"] for case in frozen["cases"]] == ["case-a", "case-b"]
    training = json.loads((tmp_path / "training.json").read_bytes())
    assert frozen["training_artifacts"] == {
        training["report_hash"]: {
            key: training["cost_accounting"][key]
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        }
    }
    first, second = frozen["cases"]
    assert first["request"]["model_file"] != second["request"]["model_file"]
    assert first["request"]["training_file"] != second["request"]["training_file"]
    assert first["expectations"] == second["expectations"]
    first["expectations"]["learned"]["frozen_plan"]["shortlist"].clear()
    assert len(second["expectations"]["learned"]["frozen_plan"]["shortlist"]) == 1


def test_all_plans_are_frozen_before_first_execution_boundary(
    request_file, monkeypatch, forbid_solver_and_workers
):
    """Synthetic boundary stop checks planning order, not numerical execution."""
    baseline, candidates, kwargs = _typed_case(request_file)
    events = []
    original_plan = arms._plan

    def observe_plan(prepared, strategy):
        planned = original_plan(prepared, strategy)
        events.append(strategy)
        return planned

    monkeypatch.setattr(arms, "_plan", observe_plan)
    frozen = arms.prepare_fiber_frame_candidate_search_expectations(
        baseline, candidates, **kwargs
    )
    assert events == ["deterministic", "learned", "oracle"]
    assert set(frozen) == {"input_binding", "deterministic", "learned", "oracle"}
    for strategy in arms.STRATEGIES:
        plan = frozen[strategy]
        assert plan["frozen_plan_hash"] == canonical_hash(plan["frozen_plan"])
        assert plan["frozen_plan"]["pool_hash"] == canonical_hash(
            plan["candidate_pool"]
        )
        assert plan["frozen_plan"]["strategy"] == strategy
        assert len(plan["frozen_plan"]["shortlist"]) == (
            2 if strategy == "oracle" else 1
        )
    before = deepcopy(frozen)

    class ExecutionBoundaryReached(Exception):
        pass

    def stop_at_boundary(**options):
        assert events[:3] == ["deterministic", "learned", "oracle"]
        strategy = options["name"]
        assert options["shortlist_hash"] == frozen[strategy]["frozen_plan_hash"]
        assert options["shortlist"] == frozen[strategy]["frozen_plan"]["shortlist"]
        raise ExecutionBoundaryReached

    monkeypatch.setattr(arms.core, "_execute_search_arm", stop_at_boundary)
    for strategy in ("deterministic", "learned"):
        with pytest.raises(ExecutionBoundaryReached):
            arms.run_fiber_frame_candidate_search_arm(
                baseline,
                candidates,
                strategy=strategy,
                expected_plan_hash=frozen[strategy]["frozen_plan_hash"],
                **kwargs,
            )
    assert frozen == before
    assert forbid_solver_and_workers == []


@pytest.mark.parametrize("strategy", arms.STRATEGIES)
def test_detached_expected_plan_is_rejected_before_execution(
    request_file, monkeypatch, strategy
):
    baseline, candidates, kwargs = _typed_case(request_file)

    def forbidden_execution(*args, **kwargs):
        pytest.fail("a detached expected plan must be rejected before execution")

    monkeypatch.setattr(arms.core, "_execute_search_arm", forbidden_execution)
    monkeypatch.setattr(arms.core, "_execute_search_oracle", forbidden_execution)
    options = {**kwargs, "expected_plan_hash": "sha256:" + "0" * 64}
    with pytest.raises(ValueError, match="plan differs"):
        if strategy == "oracle":
            arms.run_fiber_frame_candidate_search_oracle(
                baseline, candidates, **options
            )
        else:
            arms.run_fiber_frame_candidate_search_arm(
                baseline, candidates, strategy=strategy, **options
            )


@pytest.mark.parametrize("strategy", ["deterministic", "oracle"])
def test_nonlearned_arm_does_not_predict_before_synthetic_execution_stop(
    request_file, monkeypatch, strategy
):
    baseline, candidates, kwargs = _typed_case(request_file)

    def forbidden_prediction(*args, **kwargs):
        pytest.fail("nonlearned arm must not execute policy inference")

    class ExecutionBoundaryReached(Exception):
        pass

    def stop(*args, **kwargs):
        raise ExecutionBoundaryReached

    monkeypatch.setattr(arms.core, "_predict_pool", forbidden_prediction)
    monkeypatch.setattr(arms.core, "_execute_search_arm", stop)
    monkeypatch.setattr(arms.core, "_execute_search_oracle", stop)
    with pytest.raises(ExecutionBoundaryReached):
        if strategy == "oracle":
            arms.run_fiber_frame_candidate_search_oracle(baseline, candidates, **kwargs)
        else:
            arms.run_fiber_frame_candidate_search_arm(
                baseline, candidates, strategy=strategy, **kwargs
            )


def _synthetic_blocked_row(baseline, config, *, executed, marker, bound):
    """Unverified arithmetic fixture; never a physical execution receipt."""
    raw = public_api.PublicRCFiberFrameResult(
        status="blocked",
        contract_pass=False,
        result_hash="sha256:" + "0" * 64,
        canonical_model_checksum=baseline.canonical_model_checksum,
        input_checksum=baseline.input_checksum,
        solver_id=public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
        compiler_profile=public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        configuration={
            "load_steps": config.load_steps,
            "target_load_factors": list(config.target_load_factors),
            "scaled_residual_tolerance": config.residual_tolerance,
            "solver_coordinate_increment_tolerance_m": config.increment_tolerance_m,
            "maximum_iterations": config.maximum_iterations,
            "matrix_backend": "numpy_dense_ndarray",
            "restart_supplied": False,
            "restart_checkpoint_artifact_hash": None,
        },
        contract_bindings={"problem_contract_hash": "sha256:" + "7" * 64}
        if bound
        else {},
        checkpoint={},
        authority={
            key: "not_authoritative"
            for key in public_api.FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES
        },
        node_displacements=(),
        support_reactions=(),
        member_end_forces=(),
        section_results=(),
        fiber_results=(),
        convergence_history=(),
        metrics={
            "solver_executed": executed,
            "exact_engineering_recovery": False,
            "committed_step_count": 0,
            "replayed_prefix_step_count": 0,
            "newly_solved_step_count": 0,
            "fallback_count": 0,
            "regularization_count": 0,
            "rollback_exact": None,
        },
        unsupported_features=({"kind": "rc_fiber_frame_execution_failed"},)
        if marker
        else (),
        warnings=(),
    ).to_dict()
    raw["result_hash"] = canonical_hash(
        {key: value for key, value in raw.items() if key != "result_hash"}
    )
    validation = public_api.PublicRCFiberFrameValidationReport(
        status="blocked",
        contract_pass=False,
        result_hash=raw["result_hash"],
        exact_engineering_recovery=False,
        checkpoint_available=False,
        terminal_epoch=None,
        terminal_load_factor=None,
        unsupported_feature_count=len(raw["unsupported_features"]),
        warning_count=0,
        fallback_count=0,
        regularization_count=0,
    ).to_dict()
    return {
        "candidate_id": "baseline",
        "model_checksum": baseline.canonical_model_checksum,
        "canonical_model": baseline.canonical_payload(),
        "analysis_requested": True,
        "full_reference_verification_pass": False,
        "solver_executed": None if marker and bound else executed,
        "reference_and_quantity_wall_ns": 1,
        "result": raw,
        "validation": validation,
        "status": "blocked",
        "quantities": None,
        "material_estimate": None,
        "performance": None,
        "terminal_limit_status": "unavailable",
        "violated_terminal_limits": [],
        "failure": {"kind": "synthetic_only"},
    }


@pytest.mark.parametrize(
    "executed,marker,bound,changed",
    [
        (True, False, True, False),
        (True, False, True, None),
        (False, False, False, True),
        (False, True, True, False),
        (True, True, True, True),
        (False, True, False, None),
    ],
)
def test_blocked_row_execution_count_must_match_retained_public_receipt(
    request_file,
    executed,
    marker,
    bound,
    changed,
    forbid_solver_and_workers,
):
    baseline, _candidates, options = _typed_case(request_file)
    row = _synthetic_blocked_row(
        baseline,
        options["config"],
        executed=executed,
        marker=marker,
        bound=bound,
    )
    binding = {"configuration": asdict(options["config"])}
    # Both positive and negative branches use synthetic blocked data and invoke
    # only the detached row validator. No label, numerical or resource credit.
    arms._validate_requested_row(
        row, "baseline", baseline.canonical_model_checksum, binding
    )
    row["solver_executed"] = changed
    with pytest.raises(ValueError, match="solver execution receipt mismatch"):
        arms._validate_requested_row(
            row, "baseline", baseline.canonical_model_checksum, binding
        )
    assert not forbid_solver_and_workers
