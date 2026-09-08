"""Opt-in polishing is shared by all arms and bound through full RC recovery."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.ai import offline_counterfactual
from structural_analysis.assembly import stateful_corotational_fiber_frame2d_adaptive
from structural_analysis.benchmark import fiber_frame_runtime as runtime
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark import fiber_frame_strategy_process_suite as suite
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    "rc-fiber-runtime-process-request.v1",
    "rc-fiber-strategy-process-request.v1",
    "rc-fiber-learning-process-request.v1",
    "rc-fiber-learning-process-request.v2",
    "rc-fiber-learning-process-request.v3",
)
POLISHING = (
    "rc-fiber-runtime-process-request.v2",
    "rc-fiber-strategy-process-request.v2",
    "rc-fiber-learning-process-request.v4",
)


def test_existing_newton_configuration_hashes_also_bind_the_enabled_option():
    default = runtime.NewtonRaphsonConfig()
    enabled = runtime.NewtonRaphsonConfig(terminal_polishing=True)
    for encoder in (
        runtime._solver_config_payload,
        offline_counterfactual._newton_config_payload,
        stateful_corotational_fiber_frame2d_adaptive._newton_config_payload,
    ):
        assert encoder(default) == {
            "residual_tolerance": 1e-10,
            "increment_tolerance": 1e-12,
            "max_iterations": 25,
            "matrix_backend": "numpy_linalg_solve_dense",
            "line_search_alphas": [1, 0.5, 0.25, 0.125, 0.0625, 0.03125],
        }
        assert encoder(enabled) == {
            **encoder(default),
            "terminal_polishing": True,
            "terminal_polishing_profile": "newton-vector-terminal-polishing.v1",
        }


@pytest.mark.parametrize("schema", LEGACY)
def test_legacy_requests_keep_identity_and_cannot_enable_polishing(schema):
    config = runtime.FiberFrameRuntimeBenchmarkConfig()
    original = config.to_dict()
    assert "terminal_polishing" not in original
    assert (
        process._decode_benchmark_configuration(
            original, request_schema=schema
        ).to_dict()
        == original
    )
    explicit_default = asdict(config)
    explicit_default["damping_factors"] = list(config.damping_factors)
    assert (
        process._decode_benchmark_configuration(
            explicit_default, request_schema=schema
        ).to_dict()
        == original
    )
    with pytest.raises(ValueError, match="explicit request profile"):
        process._decode_benchmark_configuration(
            {**original, "terminal_polishing": True}, request_schema=schema
        )
    assert "terminal_polishing" not in original


@pytest.mark.parametrize("schema", POLISHING)
def test_polishing_profiles_require_explicit_true_and_bind_identity(schema):
    original = runtime.FiberFrameRuntimeBenchmarkConfig().to_dict()
    enabled = {**original, "terminal_polishing": True}
    decoded = process._decode_benchmark_configuration(enabled, request_schema=schema)
    assert decoded.terminal_polishing is True
    assert decoded.to_dict() == enabled
    assert canonical_hash(decoded.to_dict()) != canonical_hash(original)
    for invalid in (
        original,
        {**original, "terminal_polishing": False},
        {**original, "terminal_polishing": 1},
    ):
        with pytest.raises(ValueError):
            process._decode_benchmark_configuration(invalid, request_schema=schema)


def test_polishing_learning_profile_keeps_train_configuration_contract():
    declared = {
        "ridge": 1e-6,
        "ood_margin": 0.1,
        "model_conditioning": True,
        "learning_target": "secant_correction",
    }
    assert (
        process._decode_learning_configuration(declared, request_schema=POLISHING[-1])
        == declared
    )
    with pytest.raises(ValueError, match="secant_correction"):
        process._decode_learning_configuration(
            {**declared, "learning_target": "other"}, request_schema=POLISHING[-1]
        )


@pytest.mark.parametrize("invalid", (None, 0, 1, "true"))
def test_benchmark_polishing_flag_is_not_coerced(invalid):
    with pytest.raises(ValueError, match="terminal_polishing"):
        runtime.FiberFrameRuntimeBenchmarkConfig(terminal_polishing=invalid)


def test_frozen_inputs_bind_polishing_before_any_worker(tmp_path):
    model = ROOT / "examples/public_rc_fiber_frame_cantilever.json"
    config = PublicRCFiberFrameConfig(load_steps=2)
    request = {
        "schema_version": POLISHING[0],
        "cases": [
            {
                "case_id": "polished",
                "model_file": str(model),
                "configuration": asdict(config),
            }
        ],
        "benchmark_configuration": runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=1, warmup_repetitions=0, terminal_polishing=True
        ).to_dict(),
        "policy_file": None,
    }
    request_path = tmp_path / "request.json"
    request_path.write_bytes(process._bytes(request))
    result = suite._freeze_inputs(request_path, tmp_path)
    snapshot = load_neutral_json(model).detached_analysis_snapshot()
    baseline = suite._runtime_bindings_for_input(snapshot, config)
    expected = suite._runtime_bindings_for_input(
        snapshot, config, terminal_polishing=True
    )
    assert result["case_runtime_bindings"] == [expected]
    assert expected["solver_config_hash"] != baseline["solver_config_hash"]
    assert result["benchmark_configuration"]["terminal_polishing"] is True
    assert request_path.read_bytes() == process._bytes(request)


def test_enabled_fresh_workers_pass_the_parent_collector(tmp_path):
    request = {
        "schema_version": POLISHING[0],
        "cases": [
            {
                "case_id": "polished-process",
                "model_file": str(
                    ROOT / "examples/public_rc_fiber_frame_cantilever.json"
                ),
                "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
            }
        ],
        "benchmark_configuration": runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=1, warmup_repetitions=0, terminal_polishing=True
        ).to_dict(),
        "policy_file": None,
    }
    path = tmp_path / "request.json"
    path.write_bytes(process._bytes(request))
    observed = suite.run_fiber_frame_strategy_process_suite(
        path, source_revision="a" * 40, output_directory=tmp_path / "observed"
    )
    assert observed["status"] == "ready", str(tmp_path / "observed")
    assert observed["measurement_contract_pass"] is True
    for child in sorted((tmp_path / "observed/inputs").glob("request-*.json")):
        declared = process._json(child.read_bytes())
        assert declared["schema_version"] == POLISHING[1]
        assert declared["benchmark_configuration"]["terminal_polishing"] is True


class _ParentPolicy:
    policy_id = "polishing-test-parent"
    policy_version = "v1"
    artifact_hash = "sha256:" + "c" * 64

    def propose(self, value):
        return runtime.FiberFrameWarmStartProposal(
            value.parent_free_coordinates_m, uncertainty=0.0, ood=False
        )


def test_all_three_polished_arms_retain_full_authority_and_attempt_diagnostics(
    tmp_path,
):
    model = load_neutral_json(ROOT / "examples/public_rc_fiber_frame_cantilever.json")
    result = runtime.benchmark_public_rc_fiber_frame_warm_starts(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
        benchmark_config=runtime.FiberFrameRuntimeBenchmarkConfig(
            repetitions=1, warmup_repetitions=0, terminal_polishing=True
        ),
        ai_opt_in=True,
        ai_policy=_ParentPolicy(),
        source_revision="a" * 40,
    )
    report = result.to_dict()
    artifact = tmp_path / "polished-runtime.json"
    artifact.write_bytes(process._bytes(report))
    assert result.status == "ready", str(artifact)
    assert result.measurement_contract_pass is True
    assert report["configuration"]["benchmark"]["terminal_polishing"] is True
    assert len(report["runs"]) == 3
    for run in report["runs"]:
        assert run["authority_verification"]["contract_pass"] is True
        path = result.path(run["strategy"])
        for step, row in zip(path.steps, run["steps"], strict=True):
            assert step.trial_solution.config.terminal_polishing is True
            selected = row["selected_attempt"]
            assert selected["terminal_polishing"] == deepcopy(
                step.trial_solution.metrics["terminal_polishing"]
            )
            assert (
                selected["linear_solve_count"]
                == step.trial_solution.metrics["linear_solve_count"]
            )
            assert selected["terminal_polishing"]["status"] in {
                "accepted",
                "rejected",
                "skipped",
            }
    episodes = report["reference_solver_episode_verification"]["runs"]
    assert len(episodes) == 1
    assert episodes[0]["contract_pass"] is True
