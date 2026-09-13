"""Contract tests use synthetic executions; no physical solver is dispatched."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint as _Checkpoint,
)
import structural_analysis.benchmark.fiber_frame_runtime as runtime
from structural_analysis.benchmark.fiber_frame_runtime_suite import FiberFrameRuntimeCase
from structural_analysis.elements.stateful_fiber_beam2d_state import StatefulFiberBeam2DState
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials.stateful_fiber_section import StatefulFiberSectionState
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState


REVISION = "1" * 40
MEASURE = runtime.FiberFrameRuntimeBenchmarkConfig(repetitions=2, warmup_repetitions=1)


@dataclass
class _Payload:
    value: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.value)


@dataclass
class _Path:
    initial_checkpoint: _Checkpoint
    steps: list[Any]
    status: str = "ready"
    contract_pass: bool = True

    @property
    def final_checkpoint(self) -> _Checkpoint:
        return next(
            (step.accepted_checkpoint for step in reversed(self.steps) if step.committed),
            self.initial_checkpoint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "steps": [
                {
                    "committed": step.committed,
                    "checkpoint": step.accepted_checkpoint.to_dict(),
                    "trial_assembly": step.trial_assembly.to_dict(),
                }
                for step in self.steps
            ],
        }


def _path() -> _Path:
    checkpoints = []
    for epoch in range(3):
        fiber = UniaxialPlasticityState(
            plastic_strain=epoch * 0.001,
            accumulated_plastic_strain=epoch * 0.001,
        )
        section = StatefulFiberSectionState(
            section_id="section-1", section_contract_hash="sha256:" + "2" * 64,
            step_index=epoch, axial_strain=epoch * 0.002, curvature_z_per_m=0.0,
            fiber_states=(fiber,),
        )
        beam = StatefulFiberBeam2DState(
            element_id="beam-1", element_contract_hash="sha256:" + "3" * 64,
            step_index=epoch, local_displacements=(0.0,) * 6,
            integration_point_states=(section,),
        )
        checkpoints.append(_Checkpoint(
            case_id="synthetic", problem_contract_hash="sha256:" + "4" * 64,
            epoch=epoch, step_index=epoch, load_factor=epoch / 2,
            parent_state_hash=checkpoints[-1].state_hash if checkpoints else None,
            global_displacements=(0.0, epoch * 1.0e-3, -epoch * 2.0e-3),
            element_states=(beam,),
        ))
    return _Path(
        checkpoints[0],
        [
            SimpleNamespace(
                committed=True,
                accepted_checkpoint=checkpoint,
                trial_assembly=_Payload(
                    {
                        "result_hash": "sha256:" + str(checkpoint.epoch) * 64,
                        "internal_force": [checkpoint.epoch * 3.0, -1.0],
                        "material_response": {"stress": checkpoint.epoch * 2.0},
                    }
                ),
                trial_solution=SimpleNamespace(convergence_history=[{}, {}]),
            )
            for checkpoint in checkpoints[1:]
        ],
    )


def _execution(path: _Path | None = None) -> runtime._VariantExecution:
    return runtime._VariantExecution(
        path=_path() if path is None else path,
        wall_ns=101,
        selected_solve_wall_ns=61,
        attempted_solve_wall_ns=71,
        inference_wall_ns=3,
        guard_wall_ns=5,
        seeded_attempt_wall_ns=7,
        baseline_recovery_wall_ns=11,
        guard_assembly_call_count=2,
        attempted_newton_iteration_count=6,
        attempted_line_search_evaluation_count=8,
        selected_stateful_runtime={"total_wall_ns": 61},
        attempted_stateful_runtime={"total_wall_ns": 71},
        selected_newton_runtime={"total_wall_ns": 41},
        attempted_newton_runtime={"total_wall_ns": 51},
        step_rows=({"step_index": 0, "seeded_attempt": None, "baseline_recovery": None},),
    )


class _Policy:
    policy_id = "test.caller-owned"
    policy_version = "v1"
    artifact_hash = "sha256:" + "a" * 64

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def propose(self, value: Any) -> runtime.FiberFrameWarmStartProposal:
        self.calls.append(value)
        return runtime.FiberFrameWarmStartProposal((0.0,), uncertainty=0.0, ood=False)


@pytest.fixture
def cases() -> tuple[FiberFrameRuntimeCase, ...]:
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    variant = model.detached_analysis_snapshot()
    variant.sections[0]["depth_m"] = 0.7
    return (
        FiberFrameRuntimeCase("baseline", model, PublicRCFiberFrameConfig(load_steps=2)),
        FiberFrameRuntimeCase("variant", variant, PublicRCFiberFrameConfig(load_steps=2)),
    )


@pytest.fixture
def strategy_module() -> Any:
    return importlib.import_module(
        "structural_analysis.benchmark.fiber_frame_runtime_strategy"
    )


@pytest.fixture
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> Any:
    calls = SimpleNamespace(compile=[], execute=[], verify=[], episode=[])

    def compile_model(model: Any) -> tuple[Any, list[Any], list[Any]]:
        calls.compile.append(model)
        problem = SimpleNamespace(
            contract_hash=canonical_hash({"model": model.canonical_model_checksum}),
            free_global_dofs=(0, 1, 2),
            physical_coordinate_scale=np.ones(3),
        )
        return SimpleNamespace(problem=problem), [], ["synthetic compile warning"]

    def execute(strategy: str, problem: Any, *args: Any, **kwargs: Any) -> Any:
        calls.execute.append((strategy, problem, args, kwargs))
        if kwargs["ai_policy"] is not None:
            kwargs["ai_policy"].propose(len(calls.execute))
        return _execution()

    def verify(model: Any, compiled: Any, path: Any) -> tuple[Any, Any]:
        calls.verify.append((model, compiled, path))
        return {
            "status": "ready",
            "contract_pass": True,
            "reason_code": "full_j1_j5_recovery_passed",
            "terminal_receipt_hash": "sha256:" + "b" * 64,
        }, path

    def episode(source: Any) -> dict[str, Any]:
        calls.episode.append(source)
        return {
            "status": "ready",
            "contract_pass": True,
            "reason_code": "reference_baseline_solver_episode_replay_passed",
            "solver_episode_adapter_hash": "sha256:" + "c" * 64,
            "solver_episode_hash": "sha256:" + "d" * 64,
        }

    monkeypatch.setattr(runtime.public_api, "_compile", compile_model)
    monkeypatch.setattr(runtime, "_run_strategy", execute)
    monkeypatch.setattr(runtime, "_verify_selected_path", verify)
    monkeypatch.setattr(runtime, "_verify_reference_solver_episode", episode)
    return calls


def _report(module: Any, cases: Any, **kwargs: Any) -> dict[str, Any]:
    return module.benchmark_public_rc_fiber_frame_runtime_strategy(
        cases,
        strategy=kwargs.pop("strategy", runtime.FIBER_FRAME_NON_AI_STRATEGY),
        source_revision=kwargs.pop("source_revision", REVISION),
        benchmark_config=kwargs.pop("benchmark_config", MEASURE),
        **kwargs,
    )


@pytest.mark.parametrize(
    "mutation,matched",
    [
        ("none", True),
        ("initial_displacement", False),
        ("intermediate_displacement", False),
        ("terminal_displacement", False),
        ("intermediate_material", False),
        ("material_structure", False),
        ("initial_material", False),
        ("intermediate_trial_force", False),
        ("terminal_trial_material", False),
        ("trial_structure", False),
        ("trial_hash_only", True),
        ("checkpoint_schedule", False),
        ("missing_checkpoint", False),
        ("extra_uncommitted_trial", False),
        ("unready_status", False),
        ("false_contract", False),
        ("within_tolerance", True),
        ("signed_zero", True),
    ],
)
def test_snapshot_preserves_complete_legacy_comparison_body(
    mutation: str, matched: bool,
) -> None:
    reference = _path()
    candidate = deepcopy(reference)
    checkpoints = [candidate.initial_checkpoint] + [
        step.accepted_checkpoint for step in candidate.steps
    ]
    if mutation.endswith("_displacement"):
        index = {"initial_displacement": 0, "intermediate_displacement": 1,
                 "terminal_displacement": 2}[mutation]
        values = list(checkpoints[index].global_displacements)
        values[1] += 0.25
        checkpoints[index] = replace(
            checkpoints[index], global_displacements=tuple(values), state_hash="",
        )
    elif mutation in {"initial_material", "intermediate_material"}:
        index = int(mutation == "intermediate_material")
        beam = checkpoints[index].element_states[0]
        section = beam.integration_point_states[0]
        fiber = replace(section.fiber_states[0], plastic_strain=0.2)
        section = replace(section, fiber_states=(fiber,))
        beam = replace(beam, integration_point_states=(section,))
        checkpoints[index] = replace(checkpoints[index], element_states=(beam,), state_hash="")
    elif mutation == "material_structure":
        beam = checkpoints[1].element_states[0]
        checkpoints[1] = replace(checkpoints[1], element_states=(beam, beam), state_hash="")
    elif mutation == "intermediate_trial_force":
        candidate.steps[0].trial_assembly.value["internal_force"][0] += 0.25
    elif mutation == "terminal_trial_material":
        candidate.steps[1].trial_assembly.value["material_response"]["stress"] += 0.25
    elif mutation == "trial_structure":
        candidate.steps[0].trial_assembly.value["extra_force"] = 2.0
    elif mutation == "trial_hash_only":
        candidate.steps[0].trial_assembly.value["result_hash"] = "sha256:" + "f" * 64
    elif mutation == "checkpoint_schedule":
        checkpoints[1] = replace(checkpoints[1], load_factor=0.4, state_hash="")
    elif mutation == "missing_checkpoint":
        candidate.steps.pop(0)
    elif mutation == "extra_uncommitted_trial":
        candidate.steps.append(deepcopy(candidate.steps[0]))
        candidate.steps[-1].committed = False
    elif mutation == "unready_status":
        candidate.status = "blocked"
    elif mutation == "false_contract":
        candidate.contract_pass = False
    elif mutation == "within_tolerance":
        values = list(checkpoints[1].global_displacements)
        values[1] += 1.0e-13
        checkpoints[1] = replace(
            checkpoints[1], global_displacements=tuple(values), state_hash="",
        )
    elif mutation == "signed_zero":
        checkpoints[0] = replace(
            checkpoints[0], global_displacements=(-0.0, 0.0, 0.0), state_hash="",
        )
    candidate.initial_checkpoint = checkpoints[0]
    for step in candidate.steps:
        step.accepted_checkpoint = checkpoints[step.accepted_checkpoint.epoch]

    tolerances = {"absolute_tolerance": 1.0e-10, "relative_tolerance": 1.0e-8}
    expected = _legacy_compare_paths(reference, candidate, **tolerances)
    reference_snapshot = runtime._path_comparison_snapshot(reference)
    candidate_snapshot = runtime._path_comparison_snapshot(candidate)
    # A detached JSON roundtrip must preserve byte equality semantics too.
    actual = runtime._compare_path_comparison_snapshots(
        json.loads(json.dumps(reference_snapshot)),
        json.loads(json.dumps(candidate_snapshot)),
        **tolerances,
    )
    assert actual == expected
    assert runtime._compare_paths(reference, candidate, **tolerances) == expected
    assert actual["full_history_response_match"] is matched
    if mutation == "signed_zero":
        assert actual["checkpoint_bytes_exact"] is False
        assert actual["displacement_max_abs_difference"] == 0.0


def test_snapshot_is_detached_from_later_path_mutation() -> None:
    path = _path()
    snapshot = runtime._path_comparison_snapshot(path)
    before = deepcopy(snapshot)
    path.initial_checkpoint = replace(
        path.initial_checkpoint, global_displacements=(100.0, 0.0, 0.0), state_hash="",
    )
    path.steps[0].trial_assembly.value["internal_force"][0] = 500.0
    assert snapshot == before


@pytest.mark.parametrize(
    "mutation",
    [
        "hash", "canonical_bytes", "displacement", "load_factor", "epoch",
        "nested_material", "nested_hash", "status_type", "contract_type",
        "trial_type", "missing_field", "extra_field", "invalid_schema",
        "nan_trial", "boolean_epoch",
    ],
)
def test_snapshot_rehash_does_not_admit_invalid_or_contradictory_transport(
    mutation: str,
) -> None:
    reference = runtime._path_comparison_snapshot(_path())
    candidate = deepcopy(reference)
    checkpoint = candidate["checkpoints"][1]
    if mutation == "hash":
        candidate["snapshot_hash"] = "sha256:" + "f" * 64
    elif mutation == "canonical_bytes":
        checkpoint["canonical_bytes_hex"] = checkpoint["canonical_bytes_hex"][:-2] + "ff"
    elif mutation == "displacement":
        checkpoint["global_displacements"][1] += 0.25
    elif mutation == "load_factor":
        checkpoint["load_factor"] += 0.1
    elif mutation == "epoch":
        checkpoint["epoch"] = 2
        checkpoint["step_index"] = 2
    elif mutation in {"nested_material", "nested_hash"}:
        state = checkpoint["element_states"][0]["integration_point_states"][0][
            "fiber_states"
        ][0]
        if mutation == "nested_material":
            state["plastic_strain"] = 0.2
        else:
            state["state_hash"] = "sha256:" + "f" * 64
    elif mutation == "status_type":
        candidate["status"] = True
    elif mutation == "contract_type":
        candidate["contract_pass"] = 1
    elif mutation == "trial_type":
        candidate["trial_assemblies"][0] = [1, 2, 3]
    elif mutation == "missing_field":
        del candidate["trial_assemblies"]
    elif mutation == "extra_field":
        candidate["unbound_field"] = "extra"
    elif mutation == "invalid_schema":
        candidate["schema_version"] = "invalid.v1"
    elif mutation == "nan_trial":
        candidate["trial_assemblies"][0]["internal_force"][0] = float("nan")
    elif mutation == "boolean_epoch":
        checkpoint["epoch"] = True
        checkpoint["step_index"] = True
    if mutation not in {"hash", "nan_trial"}:
        candidate["snapshot_hash"] = canonical_hash(
            {key: value for key, value in candidate.items() if key != "snapshot_hash"}
        )
    with pytest.raises(ValueError):
        runtime._compare_path_comparison_snapshots(
            reference, candidate, absolute_tolerance=1.0e-10, relative_tolerance=1.0e-8,
        )


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), True])
@pytest.mark.parametrize("name", ["absolute_tolerance", "relative_tolerance"])
def test_snapshot_comparison_rejects_invalid_tolerances(name: str, value: Any) -> None:
    snapshot = runtime._path_comparison_snapshot(_path())
    tolerances = {"absolute_tolerance": 1.0e-10, "relative_tolerance": 1.0e-8}
    tolerances[name] = value
    with pytest.raises(ValueError, match="tolerance"):
        runtime._compare_path_comparison_snapshots(snapshot, snapshot, **tolerances)


@pytest.mark.parametrize(
    "selected_strategy",
    [runtime.FIBER_FRAME_REFERENCE_STRATEGY, runtime.FIBER_FRAME_NON_AI_STRATEGY,
     runtime.FIBER_FRAME_AI_STRATEGY],
)
def test_batch_runs_one_declared_strategy_with_separate_warmup_and_authority_costs(
    cases: Any, strategy_module: Any, fake_runtime: Any, selected_strategy: str,
) -> None:
    policy = _Policy() if selected_strategy == runtime.FIBER_FRAME_AI_STRATEGY else None
    report = _report(strategy_module, cases, strategy=selected_strategy, ai_policy=policy)
    assert report["schema_version"] == "public-rc-fiber-frame-runtime-strategy.v1"
    assert report["status"] == "ready"
    assert report["measurement_contract_pass"] is True
    assert [row["case_id"] for row in report["cases"]] == ["baseline", "variant"]
    assert len(fake_runtime.compile) == 2
    assert len(fake_runtime.execute) == 6
    assert len(fake_runtime.verify) == 4
    assert len(fake_runtime.episode) == (
        4 if selected_strategy == runtime.FIBER_FRAME_REFERENCE_STRATEGY else 0
    )
    assert {call[0] for call in fake_runtime.execute} == {selected_strategy}
    assert all(call[3]["ai_policy"] is policy for call in fake_runtime.execute)
    if policy is not None:
        assert policy.calls == list(range(1, 7))
    assert report["reference_comparison"]["status"] == "not_run"
    assert report["reference_comparison"]["full_history_response_match"] is None
    for row in report["cases"]:
        assert row["measurement_contract_pass"] is True
        assert len(row["warmups"]) == 1
        assert len(row["runs"]) == 2
        assert type(row["compile_wall_ns"]) is int
        assert type(row["compile_cpu_process_time_ns"]) is int
        for run in row["runs"]:
            assert run["strategy"] == selected_strategy
            assert run["wall_ns"] == 101
            assert run["attempted_solve_wall_ns"] == 71
            assert run["attempted_newton_iteration_count"] == 6
            assert run["attempted_line_search_evaluation_count"] == 8
            assert run["authority_verification"]["contract_pass"] is True
            assert run["comparison_snapshot"] == runtime._path_comparison_snapshot(_path())
            for name in (
                "execution_cpu_process_time_ns", "verification_cpu_process_time_ns",
                "execution_and_authority_verification_cpu_process_time_ns",
            ):
                assert type(run[name]) is int and run[name] >= 0
            assert "reference_comparison" not in run
            assert "comparison_wall_ns" not in run
            assert "verified_end_to_end_wall_ns" not in run
        episodes = row["reference_solver_episode_verification"]["runs"]
        assert len(episodes) == (
            2 if selected_strategy == runtime.FIBER_FRAME_REFERENCE_STRATEGY else 0
        )
        for episode in episodes:
            assert episode["contract_pass"] is True
            assert episode["wall_ns"] >= 0
            assert episode["cpu_process_time_ns"] >= 0
    assert report["report_hash"] == canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )


def test_failed_warmup_is_retained_and_disqualifies_case(
    cases: Any, strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = runtime._run_strategy
    attempts = 0

    def execute(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        result = original(*args, **kwargs)
        attempts += 1
        if attempts == 1:
            result.path.status = "blocked"
            result.path.contract_pass = False
        return result

    monkeypatch.setattr(runtime, "_run_strategy", execute)
    report = _report(strategy_module, cases)
    first, second = report["cases"]
    assert report["measurement_contract_pass"] is False
    assert first["measurement_contract_pass"] is False
    assert len(first["warmups"]) == 1
    assert first["warmups"][0]["contract_pass"] is False
    assert first["warmups"][0]["wall_ns"] == 101
    assert first["warmups"][0]["attempted_newton_iteration_count"] == 6
    assert len(first["runs"]) == 2
    assert second["measurement_contract_pass"] is True
    assert len(fake_runtime.verify) == 4


@pytest.mark.parametrize("phase", ["execution", "authority", "episode"])
def test_exception_retains_prior_measured_run_and_later_case(
    cases: Any, strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    name = {
        "execution": "_run_strategy", "authority": "_verify_selected_path",
        "episode": "_verify_reference_solver_episode",
    }[phase]
    original = getattr(runtime, name)
    calls = 0

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic second-run failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime, name, fail_second)
    report = _report(
        strategy_module, cases, strategy=runtime.FIBER_FRAME_REFERENCE_STRATEGY,
        benchmark_config=runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=2, warmup_repetitions=0,
        ),
    )
    first, second = report["cases"]
    assert report["measurement_contract_pass"] is False
    assert first["measurement_contract_pass"] is False
    assert len(first["runs"]) >= 1
    assert first["runs"][0]["wall_ns"] == 101
    assert first["runs"][0]["authority_verification"]["contract_pass"] is True
    failed_row = (
        first["reference_solver_episode_verification"]["runs"][1]
        if phase == "episode" else first["runs"][1]
    )
    assert failed_row["failure"]["exception_type"] == "RuntimeError"
    assert "synthetic second-run failure" in failed_row["failure"]["detail"]
    assert len(second["runs"]) == 2
    assert second["measurement_contract_pass"] is True


@pytest.mark.parametrize("unsupported", [False, True])
def test_compile_failure_does_not_drop_declared_case(
    cases: Any, strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
    unsupported: bool,
) -> None:
    original = runtime.public_api._compile
    calls = 0

    def compile_model(model: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            if unsupported:
                return None, [{"kind": "synthetic_unsupported_profile"}], []
            raise ValueError("synthetic compile failure")
        return original(model)

    monkeypatch.setattr(runtime.public_api, "_compile", compile_model)
    report = _report(strategy_module, cases)
    assert len(report["cases"]) == 2
    assert report["measurement_contract_pass"] is False
    first, second = report["cases"]
    assert first["case_id"] == "baseline"
    assert first["status"] == ("unsupported" if unsupported else "error")
    assert first["measurement_contract_pass"] is False
    assert len(first["runs"]) == MEASURE.repetitions
    assert all(run["status"] == "not_run" for run in first["runs"])
    assert all(run["wall_ns"] is None for run in first["runs"])
    assert all(run["attempted_newton_iteration_count"] is None for run in first["runs"])
    assert all(
        run["execution_and_authority_verification_wall_ns"] is None
        and run["execution_and_authority_verification_cpu_process_time_ns"] is None
        for run in first["runs"]
    )
    assert first["failure"] is not None
    assert second["measurement_contract_pass"] is True
    assert report["coverage"]["declared_case_count"] == 2
    assert report["coverage"]["ready_case_count"] == 1
    assert report["coverage"]["expected_measured_run_count"] == 4
    assert report["coverage"]["attempted_measured_run_count"] == 2


@pytest.mark.parametrize("phase", ["authority", "episode"])
def test_blocked_verification_retains_measured_cost_without_promoting_case(
    cases: Any, strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    name = {"authority": "_verify_selected_path",
            "episode": "_verify_reference_solver_episode"}[phase]
    original = getattr(runtime, name)

    def blocked(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        proof = result[0] if phase == "authority" else result
        proof["status"] = "blocked"
        proof["contract_pass"] = False
        proof["reason_code"] = "synthetic_replay_failure"
        return result

    monkeypatch.setattr(runtime, name, blocked)
    report = _report(strategy_module, cases, strategy=runtime.FIBER_FRAME_REFERENCE_STRATEGY)
    assert report["measurement_contract_pass"] is False
    for case in report["cases"]:
        assert case["measurement_contract_pass"] is False
        assert len(case["runs"]) == 2
        assert all(run["wall_ns"] == 101 for run in case["runs"])


def test_all_case_inputs_are_snapshotted_before_policy_execution(
    cases: Any, strategy_module: Any, fake_runtime: Any,
) -> None:
    expected_checksum = cases[1].model.canonical_model_checksum

    class MutateCallerInput(_Policy):
        def propose(self, value: Any) -> runtime.FiberFrameWarmStartProposal:
            cases[1].model.sections[0]["depth_m"] = 7.0
            return super().propose(value)

    report = _report(
        strategy_module, cases, strategy=runtime.FIBER_FRAME_AI_STRATEGY,
        ai_policy=MutateCallerInput(),
    )
    assert report["measurement_contract_pass"] is True
    assert cases[1].model.canonical_model_checksum != expected_checksum
    assert fake_runtime.compile[1].canonical_model_checksum == expected_checksum
    assert report["cases"][1]["binding"]["canonical_model_checksum"] == expected_checksum


def test_policy_identity_change_during_execution_cannot_pass(
    cases: Any, strategy_module: Any, fake_runtime: Any,
) -> None:
    class MutateIdentity(_Policy):
        def propose(self, value: Any) -> runtime.FiberFrameWarmStartProposal:
            self.artifact_hash = "sha256:" + "e" * 64
            return super().propose(value)

    report = _report(
        strategy_module, cases, strategy=runtime.FIBER_FRAME_AI_STRATEGY,
        ai_policy=MutateIdentity(),
    )
    assert report["measurement_contract_pass"] is False
    assert report["status"] != "ready"
    assert report["policy_execution_contract"]["policy_identity_unchanged"] is False
    assert report["coverage"]["declared_case_count"] == 2
    assert report["coverage"]["expected_measured_run_count"] == 4
    assert report["cases"][1]["failure"]["exception_type"] == "PolicyIdentityChanged"
    assert all(run["status"] == "not_run" for run in report["cases"][1]["runs"])


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"cases": []}, "non-empty"),
        ({"source_revision": "main"}, "source_revision"),
        ({"strategy": "another_strategy"}, "strategy"),
        ({"benchmark_config": {}}, "benchmark_config"),
        ({"strategy": runtime.FIBER_FRAME_AI_STRATEGY}, "ai_policy"),
        ({"ai_policy": _Policy()}, "ai_policy"),
    ],
)
def test_invalid_declarations_fail_before_compile(
    cases: Any, strategy_module: Any, fake_runtime: Any, changes: dict[str, Any],
    match: str,
) -> None:
    changes = dict(changes)
    with pytest.raises(ValueError, match=match):
        _report(strategy_module, changes.pop("cases", cases), **changes)
    assert fake_runtime.compile == []
    assert fake_runtime.execute == []


def test_duplicate_case_identifiers_fail_before_compile(
    cases: Any, strategy_module: Any, fake_runtime: Any,
) -> None:
    with pytest.raises(ValueError, match="unique"):
        _report(strategy_module, (cases[0], cases[0]))
    assert fake_runtime.compile == []


def test_identity_binds_declaration_but_excludes_volatile_observations(
    cases: Any, strategy_module: Any, fake_runtime: Any,
) -> None:
    first = _report(strategy_module, cases)
    second = _report(strategy_module, cases)
    assert first["strategy_identity_hash"] == second["strategy_identity_hash"]
    assert first["report_hash"] != second["report_hash"]
    assert first["strategy_identity_hash"] == canonical_hash(first["declaration"])
    declaration = first["declaration"]
    assert declaration["source_revision"] == REVISION
    assert declaration["strategy"] == runtime.FIBER_FRAME_NON_AI_STRATEGY
    assert declaration["benchmark_configuration"] == MEASURE.to_dict()
    assert declaration["policy"] is None
    assert [row["case_id"] for row in declaration["cases_in_execution_order"]] == [
        "baseline", "variant",
    ]
    for binding, case in zip(declaration["cases_in_execution_order"], cases, strict=True):
        assert binding["canonical_model_checksum"] == case.model.canonical_model_checksum
        assert binding["target_load_factors"] == list(case.config.target_load_factors)


@pytest.mark.parametrize("change", ["order", "revision", "configuration", "strategy"])
def test_experiment_changes_change_identity(
    cases: Any, strategy_module: Any, fake_runtime: Any, change: str,
) -> None:
    first = _report(strategy_module, cases)
    kwargs = {}
    if change == "order":
        cases = tuple(reversed(cases))
    elif change == "revision":
        kwargs["source_revision"] = "2" * 40
    elif change == "configuration":
        kwargs["benchmark_config"] = replace(MEASURE, warmup_repetitions=0)
    elif change == "strategy":
        kwargs["strategy"] = runtime.FIBER_FRAME_REFERENCE_STRATEGY
    second = _report(strategy_module, cases, **kwargs)
    assert first["strategy_identity_hash"] != second["strategy_identity_hash"]


def test_nested_cpu_intervals_and_unmeasured_claims_are_explicit(
    cases: Any, strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ticking(step: int) -> Any:
        value = 0

        def tick() -> int:
            nonlocal value
            value += step
            return value

        return tick

    monkeypatch.setattr(strategy_module, "perf_counter_ns", ticking(17))
    monkeypatch.setattr(strategy_module, "process_time_ns", ticking(3))
    report = _report(strategy_module, cases, strategy=runtime.FIBER_FRAME_REFERENCE_STRATEGY)
    for case in report["cases"]:
        assert case["compile_wall_ns"] == 17
        assert case["compile_cpu_process_time_ns"] == 3
        for warmup in case["warmups"]:
            assert warmup["execution_call_wall_ns"] == 17
            assert warmup["execution_cpu_process_time_ns"] == 3
            assert warmup["authority_verification"]["status"] == "not_run"
        for run in case["runs"]:
            assert run["execution_call_wall_ns"] == 17
            assert run["execution_cpu_process_time_ns"] == 3
            assert run["verification_wall_ns"] == 17
            assert run["verification_cpu_process_time_ns"] == 3
            assert run["execution_and_authority_verification_cpu_process_time_ns"] >= (
                run["execution_cpu_process_time_ns"]
                + run["verification_cpu_process_time_ns"]
            )
            assert run["execution_and_authority_verification_wall_ns"] >= (
                run["execution_call_wall_ns"] + run["verification_wall_ns"]
            )
        for episode in case["reference_solver_episode_verification"]["runs"]:
            assert episode["wall_ns"] == 17
            assert episode["cpu_process_time_ns"] == 3
    assert report["measurement_scope"]["cross_strategy_comparison_included"] is False
    assert report["measurement_scope"]["per_phase_peak_memory_bytes"] is None
    assert report["measurement_scope"]["training_executed"] is False
    assert report["reference_comparison"]["full_history_response_match"] is None


@pytest.fixture
def accounted_phases(
    strategy_module: Any, fake_runtime: Any, monkeypatch: pytest.MonkeyPatch,
) -> Any:
    # Clock reads do not consume time. Each operation advances independent wall
    # and CPU clocks by a known cost, including work between nested intervals.
    ledger = SimpleNamespace(
        wall=0,
        cpu=0,
        seen=[],
        fail_phase=None,
        costs={
            "execution": (1010, 101),
            "metadata": (409, 41),
            "snapshot": (307, 31),
            "authority": (2030, 203),
        },
    )
    monkeypatch.setattr(strategy_module, "perf_counter_ns", lambda: ledger.wall)
    monkeypatch.setattr(strategy_module, "process_time_ns", lambda: ledger.cpu)

    def wrap(owner: Any, name: str, phase: str) -> None:
        original = getattr(owner, name)

        def operation(*args: Any, **kwargs: Any) -> Any:
            wall, cpu = ledger.costs[phase]
            ledger.wall += wall
            ledger.cpu += cpu
            ledger.seen.append(phase)
            if ledger.fail_phase == phase:
                raise RuntimeError(f"synthetic {phase} failure after measured work")
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, operation)

    wrap(runtime, "_run_strategy", "execution")
    wrap(strategy_module, "_execution_fields", "metadata")
    wrap(runtime, "_path_comparison_snapshot", "snapshot")
    wrap(runtime, "_verify_selected_path", "authority")
    return ledger


def test_inclusive_interval_contains_metadata_and_snapshot_preparation(
    cases: Any, strategy_module: Any, accounted_phases: Any,
) -> None:
    report = _report(
        strategy_module, cases[:1],
        benchmark_config=runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=1, warmup_repetitions=0,
        ),
    )
    run = report["cases"][0]["runs"][0]
    assert report["measurement_contract_pass"] is True
    assert accounted_phases.seen == ["execution", "metadata", "snapshot", "authority"]
    assert run["execution_call_wall_ns"] == 1010
    assert run["execution_cpu_process_time_ns"] == 101
    assert run["verification_wall_ns"] == 2030
    assert run["verification_cpu_process_time_ns"] == 203
    # The separately charged preparation cost must not disappear from the
    # inclusive interval or be silently attributed to solver/replay time.
    assert run["execution_and_authority_verification_wall_ns"] == 3756
    assert run["execution_and_authority_verification_cpu_process_time_ns"] == 376
    assert run["execution_and_authority_verification_wall_ns"] > (
        run["execution_call_wall_ns"] + run["verification_wall_ns"]
    )
    assert run["execution_and_authority_verification_cpu_process_time_ns"] > (
        run["execution_cpu_process_time_ns"] + run["verification_cpu_process_time_ns"]
    )
    assert report["measurement_scope"][
        "comparison_snapshot_preparation_included_in_verified_run_interval"
    ] is True


@pytest.mark.parametrize("phase", ["execution", "metadata", "snapshot", "authority"])
def test_failed_actual_call_retains_known_inclusive_cost(
    cases: Any, strategy_module: Any, accounted_phases: Any, phase: str,
) -> None:
    accounted_phases.fail_phase = phase
    report = _report(
        strategy_module, cases[:1],
        benchmark_config=runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=1, warmup_repetitions=0,
        ),
    )
    run = report["cases"][0]["runs"][0]
    assert report["measurement_contract_pass"] is False
    assert run["failure"]["exception_type"] == "RuntimeError"
    assert phase in run["failure"]["detail"]
    assert run["execution_call_wall_ns"] == 1010
    assert run["execution_cpu_process_time_ns"] == 101
    attempted_phases = list(accounted_phases.costs)
    attempted_phases = attempted_phases[:attempted_phases.index(phase) + 1]
    assert accounted_phases.seen == attempted_phases
    assert run["execution_and_authority_verification_wall_ns"] == sum(
        accounted_phases.costs[name][0] for name in attempted_phases
    )
    assert run["execution_and_authority_verification_cpu_process_time_ns"] == sum(
        accounted_phases.costs[name][1] for name in attempted_phases
    )
    if phase == "authority":
        assert run["verification_wall_ns"] == 2030
        assert run["verification_cpu_process_time_ns"] == 203
    else:
        assert run["verification_wall_ns"] is None
        assert run["verification_cpu_process_time_ns"] is None
    assert report["coverage"]["attempted_measured_run_count"] == 1
    assert report["coverage"]["selected_path_authority_pass_count"] == 0


# Frozen pre-extraction comparator: keep independent of the snapshot adapter.
def _legacy_compare_paths(
    reference: _Path,
    candidate: _Path,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    reference_checkpoints = (
        reference.initial_checkpoint,
        *(step.accepted_checkpoint for step in reference.steps if step.committed),
    )
    candidate_checkpoints = (
        candidate.initial_checkpoint,
        *(step.accepted_checkpoint for step in candidate.steps if step.committed),
    )
    schedule_match = tuple(
        (checkpoint.epoch, checkpoint.load_factor)
        for checkpoint in reference_checkpoints
    ) == tuple(
        (checkpoint.epoch, checkpoint.load_factor)
        for checkpoint in candidate_checkpoints
    )
    structure_match = len(reference_checkpoints) == len(candidate_checkpoints)
    exact_checkpoint_match = structure_match and all(
        left.canonical_bytes() == right.canonical_bytes()
        for left, right in zip(
            reference_checkpoints, candidate_checkpoints, strict=True
        )
    )
    displacement_max_abs = 0.0
    displacement_max_rel = 0.0
    material_max_abs = 0.0
    material_max_rel = 0.0
    material_structure_match = structure_match
    displacement_tolerance_match = structure_match
    material_tolerance_match = structure_match
    if structure_match:
        for left, right in zip(
            reference_checkpoints, candidate_checkpoints, strict=True
        ):
            left_displacement = np.asarray(left.global_displacements, dtype=np.float64)
            right_displacement = np.asarray(
                right.global_displacements, dtype=np.float64
            )
            abs_difference, rel_difference = runtime._array_difference(
                left_displacement,
                right_displacement,
            )
            displacement_max_abs = max(displacement_max_abs, abs_difference)
            displacement_max_rel = max(displacement_max_rel, rel_difference)
            displacement_tolerance_match = bool(
                displacement_tolerance_match
                and np.allclose(
                    left_displacement,
                    right_displacement,
                    rtol=relative_tolerance,
                    atol=absolute_tolerance,
                )
            )
            (
                compatible,
                abs_difference,
                rel_difference,
                within_tolerance,
            ) = runtime._numeric_payload_difference(
                [row.to_dict() for row in left.element_states],
                [row.to_dict() for row in right.element_states],
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            material_structure_match = material_structure_match and compatible
            material_tolerance_match = material_tolerance_match and within_tolerance
            material_max_abs = max(material_max_abs, abs_difference)
            material_max_rel = max(material_max_rel, rel_difference)
    trial_response_structure_match = len(reference.steps) == len(candidate.steps)
    trial_response_tolerance_match = trial_response_structure_match
    trial_response_max_abs = 0.0
    trial_response_max_rel = 0.0
    if trial_response_structure_match:
        for left_step, right_step in zip(
            reference.steps,
            candidate.steps,
            strict=True,
        ):
            (
                compatible,
                abs_difference,
                rel_difference,
                within_tolerance,
            ) = runtime._numeric_payload_difference(
                left_step.trial_assembly.to_dict(),
                right_step.trial_assembly.to_dict(),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            trial_response_structure_match = (
                trial_response_structure_match and compatible
            )
            trial_response_tolerance_match = (
                trial_response_tolerance_match and within_tolerance
            )
            trial_response_max_abs = max(
                trial_response_max_abs,
                abs_difference,
            )
            trial_response_max_rel = max(
                trial_response_max_rel,
                rel_difference,
            )
    response_match = bool(
        reference.status == candidate.status == "ready"
        and reference.contract_pass
        and candidate.contract_pass
        and schedule_match
        and structure_match
        and material_structure_match
        and trial_response_structure_match
        and displacement_tolerance_match
        and material_tolerance_match
        and trial_response_tolerance_match
    )
    return {
        "same_object_identity_required": False,
        "load_schedule_match": schedule_match,
        "checkpoint_count_match": structure_match,
        "checkpoint_bytes_exact": exact_checkpoint_match,
        "displacement_max_abs_difference": displacement_max_abs,
        "displacement_max_relative_difference": displacement_max_rel,
        "displacement_within_elementwise_tolerance": (displacement_tolerance_match),
        "material_state_structure_match": material_structure_match,
        "material_state_max_abs_difference": material_max_abs,
        "material_state_max_relative_difference": material_max_rel,
        "material_state_within_elementwise_tolerance": material_tolerance_match,
        "trial_force_response_structure_match": trial_response_structure_match,
        "trial_force_response_max_abs_difference": trial_response_max_abs,
        "trial_force_response_max_relative_difference": trial_response_max_rel,
        "trial_force_response_within_elementwise_tolerance": (
            trial_response_tolerance_match
        ),
        "tolerance_rule": "abs_delta <= atol + rtol * max(abs(left), abs(right))",
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "full_history_response_match": response_match,
    }
