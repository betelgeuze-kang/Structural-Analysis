from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import statistics
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/benchmark_engine_v2_rtc_kernel_scaling.py"
SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/rtc_kernel_scaling_report_v1.schema.json"
)
SPEC = importlib.util.spec_from_file_location("rtc_kernel_scaling_v1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def _fit_sample(row_count: int, per_launch_ms: float) -> dict[str, Any]:
    factors = (0.996, 0.998, 1.0, 1.0, 1.002, 1.004, 1.0)
    trials = [
        {
            "trial_index": index,
            "batch_elapsed_ms": 25 * per_launch_ms * factor,
            "per_launch_ms": per_launch_ms * factor,
        }
        for index, factor in enumerate(factors)
    ]
    work = benchmark._logical_work(row_count)
    return {
        "row_count": row_count,
        **work,
        "median_per_launch_ms": per_launch_ms,
        "median_batch_elapsed_ms": 25.0,
        "batch_length_stability_relative_delta": 0.002,
        "coefficient_of_variation": 0.003,
        "end_repeat_relative_drift": 0.004,
        "correctness": {"passed": True},
        "timed_region_h2d_operation_count": 0,
        "timed_region_d2h_operation_count": 0,
        "timed_region_allocation_count": 0,
        "fallback_count": 0,
        "raw_trials": trials,
    }


def _complete_sample(row_count: int, per_launch_ms: float) -> dict[str, Any]:
    sample = _fit_sample(row_count, per_launch_ms)
    k = 25
    per_launch = [float(item["per_launch_ms"]) for item in sample["raw_trials"]]
    batch = [float(item["batch_elapsed_ms"]) for item in sample["raw_trials"]]
    median = float(statistics.median(per_launch))
    mean = float(statistics.fmean(per_launch))
    deviation = float(statistics.stdev(per_launch))
    stability_k = [k * per_launch_ms] * 3
    stability_2k = [2 * k * per_launch_ms] * 3
    sample.update(
        allocated_device_payload_bytes=benchmark._allocated_payload_bytes(row_count),
        allocation_count=8,
        initial_h2d_operation_count=6,
        initial_h2d_bytes=benchmark._initial_h2d_bytes(row_count),
        outside_timed_region_d2h_operation_count=2,
        outside_timed_region_d2h_bytes=16 * row_count,
        warmup_launch_count=20,
        pilot_launch_count=4,
        pilot_batch_elapsed_ms=4 * per_launch_ms,
        calibration_trials=[
            {
                "calibration_index": 0,
                "launch_count": k,
                "median_batch_elapsed_ms": k * per_launch_ms,
                "raw_batch_elapsed_ms": stability_k,
            }
        ],
        timed_batch_launch_count=k,
        double_batch_launch_count=2 * k,
        batch_length_stability_k_per_launch_ms=per_launch_ms,
        batch_length_stability_2k_per_launch_ms=per_launch_ms,
        batch_length_stability_relative_delta=0.0,
        batch_length_stability_k_raw_batch_elapsed_ms=stability_k,
        batch_length_stability_2k_raw_batch_elapsed_ms=stability_2k,
        timed_trial_count=7,
        fit_trial_kernel_launch_count=k * 7,
        event_timed_kernel_launch_count_total=4 + k * 3 + 2 * k * 3 + k * 7 + k,
        median_batch_elapsed_ms=float(statistics.median(batch)),
        median_per_launch_ms=median,
        minimum_per_launch_ms=min(per_launch),
        maximum_per_launch_ms=max(per_launch),
        mean_per_launch_ms=mean,
        standard_deviation_per_launch_ms=deviation,
        median_absolute_deviation_per_launch_ms=float(
            statistics.median(abs(value - median) for value in per_launch)
        ),
        coefficient_of_variation=deviation / mean,
        end_repeat_batch_elapsed_ms=k * median,
        end_repeat_per_launch_ms=median,
        end_repeat_relative_drift=0.0,
        event_timing_scope="steady_state_stream_dispatch_plus_kernel",
        correctness={
            "performed_outside_timed_region": True,
            "finite": True,
            "residual_max_abs_error": 0.0,
            "residual_relative_l2_error": 0.0,
            "jvp_max_abs_error": 0.0,
            "jvp_relative_l2_error": 0.0,
            "absolute_tolerance": 1.0e-10,
            "relative_l2_tolerance": 1.0e-10,
            "passed": True,
        },
    )
    return sample


class _FakeRuntime:
    def __init__(self) -> None:
        self.next_pointer = 1
        self.buffers: dict[int, np.ndarray] = {}
        self.launch_count = 0
        self.event_positions: dict[int, int] = {}
        self.next_event = 100
        self.freed: list[int] = []

    def malloc(self, byte_length: int) -> int:
        assert byte_length > 0
        pointer = self.next_pointer
        self.next_pointer += 1
        return pointer

    def free(self, pointer: int) -> None:
        self.freed.append(pointer)

    def copy_h2d_async(
        self, pointer: int, array: np.ndarray, stream: object
    ) -> None:
        assert stream == "stream"
        self.buffers[pointer] = array.copy()

    def copy_d2h_async(
        self, array: np.ndarray, pointer: int, stream: object
    ) -> None:
        assert stream == "stream"
        state = self.buffers[4]
        load = self.buffers[5]
        direction = self.buffers[6]
        source = state if pointer == 7 else direction
        expected = 2.5 * source
        expected[1:] -= 0.25 * source[:-1]
        expected[:-1] -= 0.25 * source[1:]
        if pointer == 7:
            expected -= load
        array[:] = expected

    def synchronize_stream(self, stream: object) -> None:
        assert stream == "stream"

    def create_event(self) -> int:
        event = self.next_event
        self.next_event += 1
        return event

    def record_event(self, event: int, stream: object) -> None:
        assert stream == "stream"
        self.event_positions[event] = self.launch_count

    def synchronize_event(self, event: int) -> None:
        assert event in self.event_positions

    def elapsed_ms(self, start: int, stop: int) -> float:
        return float(self.event_positions[stop] - self.event_positions[start])

    def destroy_event(self, event: int) -> None:
        assert event in (100, 101)


class _FakeKernel:
    def __init__(self, runtime: _FakeRuntime) -> None:
        self.runtime = runtime

    def launch_residual_jvp(self, *args: Any) -> None:
        assert args[0] == "stream"
        self.runtime.launch_count += 1


def test_clean_worker_reexec_removes_serialization_before_child() -> None:
    environment = {
        "PATH": "/bin",
        "HIP_LAUNCH_BLOCKING": "1",
        "AMD_SERIALIZE_KERNEL": "3",
        "AMD_SERIALIZE_COPY": "3",
        "CUDA_LAUNCH_BLOCKING": "1",
    }
    observed: dict[str, Any] = {}

    def fake_runner(command: list[str], **kwargs: Any) -> Any:
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        assert kwargs["check"] is False
        return SimpleNamespace(returncode=17)

    result = benchmark._reexec_clean_worker(
        ["--repeats", "9"], environment=environment, runner=fake_runner
    )
    assert result == 17
    child_environment = observed["environment"]
    assert child_environment[benchmark.WORKER_SENTINEL] == "1"
    for name in benchmark.SERIALIZATION_ENV_VARS:
        assert name not in child_environment
    assert set(child_environment[benchmark.SANITIZED_FROM].split(",")) == set(
        benchmark.SERIALIZATION_ENV_VARS
    )
    assert observed["command"][-2:] == ["--repeats", "9"]


def test_configuration_rejects_zero_k_and_requires_off_cache_span() -> None:
    args = benchmark._parser().parse_args(["--max-batch-launches", "1"])
    sizes = benchmark._parse_sizes(args.sizes)
    with pytest.raises(benchmark.BenchmarkError) as error:
        benchmark._validate_configuration(args, sizes)
    assert error.value.code == "rtc_scaling_configuration_invalid"

    short = benchmark._parser().parse_args(
        ["--sizes", "100,200,300,350,399", "--fit-min-n", "100", "--fit-max-n", "399"]
    )
    with pytest.raises(benchmark.BenchmarkError):
        benchmark._validate_configuration(short, benchmark._parse_sizes(short.sizes))

    zero_fit = benchmark._parser().parse_args(["--fit-min-n", "0"])
    with pytest.raises(benchmark.BenchmarkError):
        benchmark._validate_configuration(
            zero_fit, benchmark._parse_sizes(zero_fit.sizes)
        )
    with pytest.raises(benchmark.BenchmarkError):
        benchmark._parse_sizes(
            "1,2,3,4," + str(benchmark._MAX_CSR_ROWS + 1)
        )


def test_fixed_degree_sorted_csr_and_exact_work_accounting() -> None:
    row_ptr, columns, values, *vectors = benchmark._build_tridiagonal_csr(7)
    assert row_ptr.tolist() == [0, 2, 5, 8, 11, 14, 17, 19]
    for row in range(7):
        actual = columns[row_ptr[row] : row_ptr[row + 1]].tolist()
        assert actual == list(range(max(0, row - 1), min(7, row + 2)))
    assert values.dtype == np.dtype("<f8")
    assert columns.dtype == np.dtype("<i4")
    assert all(vector.dtype == np.dtype("<f8") for vector in vectors)
    assert sum(array.nbytes for array in (row_ptr, columns, values, *vectors)) == (
        benchmark._allocated_payload_bytes(7)
    )

    n = benchmark.DEFAULT_SIZES[0]
    z = 3 * n - 2
    work = benchmark._logical_work(n)
    assert work["fp64_equivalent_operations_per_launch"] == 4 * z + n
    assert work["source_logical_bytes_per_launch"] == 28 * z + 32 * n
    assert work["unique_read_bytes"] == 12 * z + 28 * n + 4
    assert work["resident_touched_bytes"] == 12 * z + 44 * n + 4
    assert work["unique_read_bytes"] >= 2 * benchmark.REFERENCE_CACHE_BYTES
    assert benchmark.DEFAULT_SIZES[-1] == 4 * benchmark.DEFAULT_SIZES[0]


def test_adaptive_event_measurement_counts_all_launches_and_checks_outside() -> None:
    runtime = _FakeRuntime()
    kernel = _FakeKernel(runtime)
    sample = benchmark._measure_one_size(
        row_count=1024,
        runtime=runtime,
        kernel=kernel,
        stream="stream",
        warmup_launches=20,
        pilot_launches=4,
        target_batch_ms=20.0,
        max_batch_launches=128,
        stability_repeats=3,
        repeats=7,
    )
    assert sample["timed_batch_launch_count"] == 20
    assert sample["double_batch_launch_count"] == 40
    assert sample["median_batch_elapsed_ms"] == 20.0
    assert sample["batch_length_stability_relative_delta"] == 0.0
    assert sample["coefficient_of_variation"] == 0.0
    assert sample["end_repeat_relative_drift"] == 0.0
    assert sample["correctness"]["passed"]
    assert sample["timed_region_d2h_operation_count"] == 0
    assert sample["outside_timed_region_d2h_operation_count"] == 2
    expected_event_launches = (
        4 + 20 * 3 + 40 * 3 + 20 * 7 + 20
    )
    assert sample["event_timed_kernel_launch_count_total"] == expected_event_launches
    assert sample["fit_trial_kernel_launch_count"] == 20 * 7
    assert runtime.launch_count == 20 + expected_event_launches
    assert sorted(runtime.freed) == list(range(1, 9))


def test_robust_fit_bootstrap_and_acceptance_are_kernel_scope_only() -> None:
    sizes = benchmark.DEFAULT_SIZES
    samples = [
        _fit_sample(n, 0.4 * n / sizes[0])
        for n in sizes
    ]
    fit = benchmark._fit_log_log(
        samples, bootstrap_replicates=400, bootstrap_seed=11
    )
    assert fit["robust_slope"] == pytest.approx(1.0, abs=2.0e-3)
    assert fit["ols_slope"] == pytest.approx(1.0, abs=2.0e-3)
    assert fit["ols_r2"] > 0.999
    assert 0.99 < fit["bootstrap_slope_ci95_lower"]
    assert fit["bootstrap_slope_ci95_upper"] < 1.01
    accepted = benchmark._acceptance(
        fit,
        samples=samples,
        slope_lower=0.85,
        slope_upper=1.15,
        min_r2=0.98,
        hardware_profile_matched=True,
    )
    assert accepted["accepted"]
    assert accepted["outcome"] == "accepted"
    assert accepted["scope"] == benchmark.CLAIM_SCOPE

    foreign_device = benchmark._acceptance(
        fit,
        samples=samples,
        slope_lower=0.85,
        slope_upper=1.15,
        min_r2=0.98,
        hardware_profile_matched=False,
    )
    assert foreign_device["outcome"] == "inconclusive"
    assert not foreign_device["off_cache_occupancy_precondition_passed"]

    steep = dict(fit)
    steep.update(
        robust_slope=1.30,
        ols_slope=1.30,
        ols_r2=0.999,
        bootstrap_slope_ci95_lower=1.25,
        bootstrap_slope_ci95_upper=1.35,
    )
    steep_decision = benchmark._acceptance(
        steep,
        samples=samples,
        slope_lower=0.85,
        slope_upper=1.15,
        min_r2=0.98,
        hardware_profile_matched=True,
    )
    assert steep_decision["outcome"] == "rejected"

    wide_confidence = dict(fit)
    wide_confidence.update(
        bootstrap_slope_ci95_lower=0.80,
        bootstrap_slope_ci95_upper=1.20,
    )
    confidence_decision = benchmark._acceptance(
        wide_confidence,
        samples=samples,
        slope_lower=0.85,
        slope_upper=1.15,
        min_r2=0.98,
        hardware_profile_matched=True,
    )
    assert confidence_decision["outcome"] == "inconclusive"


def test_bootstrap_never_synthesizes_missing_raw_trials() -> None:
    samples = [
        {"row_count": n, "median_per_launch_ms": float(index + 1), "raw_trials": []}
        for index, n in enumerate(benchmark.DEFAULT_SIZES)
    ]
    with pytest.raises(benchmark.BenchmarkError) as error:
        benchmark._fit_log_log(samples, bootstrap_replicates=200)
    assert error.value.code == "rtc_scaling_fit_invalid"


def test_strict_unavailable_report_schema_and_nonpromotion(monkeypatch: Any) -> None:
    monkeypatch.setenv(benchmark.WORKER_SENTINEL, "1")
    for name in benchmark.SERIALIZATION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    args = benchmark._parser().parse_args([])
    sizes = benchmark._parse_sizes(args.sizes)
    report = benchmark._base_report(
        args=args,
        sizes=sizes,
        architecture=None,
        detected_architectures=(),
        enumerator=None,
    )
    report["reason"] = {
        "code": "rtc_scaling_real_gfx_unavailable",
        "detail": "No real gfx target was detected and no fallback ran.",
    }
    report = benchmark._finalize_report(report)
    benchmark._validate_report_invariants(report)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(report))
    assert report["promotion_eligible"] is False
    assert report["claims"]["end_to_end_o_n"] is False
    assert report["claims"]["solver_speedup"] is False

    tampered = copy.deepcopy(report)
    tampered["claims"]["end_to_end_o_n"] = True
    assert list(validator.iter_errors(tampered))

    rehashed = copy.deepcopy(report)
    rehashed["report_hash"] = "sha256:" + "1" * 64
    with pytest.raises(benchmark.BenchmarkError) as error:
        benchmark._validate_report_invariants(rehashed)
    assert error.value.code == "rtc_scaling_report_invariant_invalid"


def test_accepted_report_replays_derived_fields_and_rejects_rehashed_tamper(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv(benchmark.WORKER_SENTINEL, "1")
    for name in benchmark.SERIALIZATION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    args = benchmark._parser().parse_args(["--bootstrap-replicates", "200"])
    sizes = benchmark._parse_sizes(args.sizes)
    samples = [
        _complete_sample(row_count, 0.8 * row_count / sizes[0])
        for row_count in sizes
    ]
    fit = benchmark._fit_log_log(
        samples,
        bootstrap_replicates=args.bootstrap_replicates,
        bootstrap_seed=args.bootstrap_seed,
    )
    acceptance = benchmark._acceptance(
        fit,
        samples=samples,
        slope_lower=args.slope_lower,
        slope_upper=args.slope_upper,
        min_r2=args.min_r2,
        max_cv=args.max_cv,
        max_batch_stability_delta=args.max_batch_stability_delta,
        max_end_repeat_drift=args.max_end_repeat_drift,
        hardware_profile_matched=True,
    )
    assert acceptance["accepted"]
    report = benchmark._base_report(
        args=args,
        sizes=sizes,
        architecture="gfx1030",
        detected_architectures=("gfx1030",),
        enumerator="/opt/rocm/bin/rocm_agent_enumerator",
    )
    hash_value = "sha256:" + "a" * 64
    report.update(
        status="accepted",
        decision="accepted",
        actual_backend="hip",
        reason=None,
        device={
            "name": "AMD Radeon RX 6900 XT",
            "free_memory_bytes_before": 12 * 1024**3,
            "total_memory_bytes": 16 * 1024**3,
            "runtime_version_raw": 60032831,
            "driver_version_raw": 60032831,
            "capability_receipt_hash": hash_value,
            "hardware_profile_matched": True,
        },
        kernel_identity={
            "kernel_symbol": "engine_v2_csr_residual_jvp_v1",
            "architecture": "gfx1030",
            "source_sha256": hash_value,
            "code_object_sha256": hash_value,
            "identity_hash": hash_value,
            "hiprtc_version_major": 6,
            "hiprtc_version_minor": 0,
            "runtime_library_sha256": hash_value,
            "hiprtc_library_sha256": hash_value,
        },
        samples=samples,
        fit=fit,
        acceptance=acceptance,
    )
    report["claims"].update(
        kernel_scope_timing_measured=True,
        kernel_scope_initial_linear_scaling_accepted=True,
    )
    report = benchmark._finalize_report(report)
    benchmark._validate_report_invariants(report)

    def assert_rehashed_tamper_rejected(mutator: Any) -> None:
        changed = copy.deepcopy(report)
        mutator(changed)
        benchmark._finalize_report(changed)
        with pytest.raises(benchmark.BenchmarkError):
            benchmark._validate_report_invariants(changed)

    assert_rehashed_tamper_rejected(
        lambda payload: payload["samples"][0].__setitem__(
            "median_per_launch_ms",
            payload["samples"][0]["median_per_launch_ms"] * 1.1,
        )
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["samples"][0].__setitem__(
            "source_logical_bytes_per_launch", 1
        )
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["fit"].__setitem__("ols_slope", 1.12)
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["samples"][0]["correctness"].update(
            residual_max_abs_error=1.0, passed=True
        )
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload.update(status="rejected")
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["device"].__setitem__(
            "hardware_profile_matched", False
        )
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["configuration"]["measurement_order"].reverse()
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["harness_identity"].__setitem__(
            "benchmark_script_sha256", "sha256:" + "b" * 64
        )
    )
    assert_rehashed_tamper_rejected(
        lambda payload: payload["kernel_identity"].__setitem__(
            "architecture", "gfx1100"
        )
    )
