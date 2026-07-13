#!/usr/bin/env python3
"""Measure the fixed Engine v2 HIPRTC fused CSR kernel scaling envelope.

This is deliberately a kernel-only, unsigned, non-promoting benchmark.  The
parent process re-spawns a clean worker before importing NumPy or any Engine
v2/HIP module so launch-serialization overrides cannot contaminate timings.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import random
import shutil
import statistics
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence


REPORT_SCHEMA_VERSION = "structural-analysis-rtc-kernel-scaling-report.v1"
CLAIM_SCOPE = "hiprtc_fused_csr_residual_jvp_kernel_only"
EVIDENCE_SCOPE = "native_hiprtc_kernel_event_timing"
WORKER_SENTINEL = "ENGINE_V2_RTC_SCALING_WORKER_V1"
SANITIZED_FROM = "ENGINE_V2_RTC_SCALING_SANITIZED_FROM_V1"
SERIALIZATION_ENV_VARS = (
    "HIP_LAUNCH_BLOCKING",
    "AMD_SERIALIZE_KERNEL",
    "AMD_SERIALIZE_COPY",
    "CUDA_LAUNCH_BLOCKING",
)

# Predeclared large-problem regime.  Smaller rows cross launch/occupancy and
# Infinity-Cache regimes on the development gfx1030 and are intentionally not
# used for the default asymptotic fit.
DEFAULT_SIZES = (
    4_194_305,
    6_291_456,
    8_388_608,
    12_582_912,
    16_777_220,
)
DEFAULT_WARMUP_LAUNCHES = 20
DEFAULT_PILOT_LAUNCHES = 4
DEFAULT_TARGET_BATCH_MS = 20.0
DEFAULT_MAX_BATCH_LAUNCHES = 4096
DEFAULT_STABILITY_REPEATS = 3
DEFAULT_REPEATS = 7
DEFAULT_MIN_FREE_DEVICE_BYTES = 2 * 1024**3
DEFAULT_MAX_PAYLOAD_FRACTION = 0.50
DEFAULT_SLOPE_LOWER = 0.85
DEFAULT_SLOPE_UPPER = 1.15
DEFAULT_MIN_R2 = 0.98
DEFAULT_MAX_CV = 0.05
DEFAULT_MAX_BATCH_STABILITY_DELTA = 0.03
DEFAULT_MAX_END_REPEAT_DRIFT = 0.05
DEFAULT_BOOTSTRAP_REPLICATES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260711
REFERENCE_CACHE_BYTES = 128 * 1024**2
REFERENCE_COMPUTE_UNITS = 80
REFERENCE_BLOCK_SIZE = 256
EXPECTED_PROFILE_ARCHITECTURE = "gfx1030"
EXPECTED_PROFILE_DEVICE_NAME_TOKEN = "6900 XT"

_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_HIP_MEMCPY_HOST_TO_DEVICE = 1
_HIP_MEMCPY_DEVICE_TO_HOST = 2
_HIP_STREAM_NON_BLOCKING = 1
_HIP_EVENT_DEFAULT = 0
_MAX_CSR_ROWS = ((1 << 31) - 1 + 2) // 3


class BenchmarkError(RuntimeError):
    """Stable benchmark failure that never triggers a CPU fallback."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure only the fixed HIPRTC fused CSR residual/JVP kernel with "
            "HIP events. No solver, CPU fallback, speedup, or end-to-end O(N) "
            "claim is produced."
        )
    )
    parser.add_argument(
        "--sizes",
        default=",".join(str(value) for value in DEFAULT_SIZES),
        help="Comma-separated, strictly increasing row counts (at least five).",
    )
    parser.add_argument(
        "--warmup-launches", type=int, default=DEFAULT_WARMUP_LAUNCHES
    )
    parser.add_argument("--pilot-launches", type=int, default=DEFAULT_PILOT_LAUNCHES)
    parser.add_argument(
        "--target-batch-ms", type=float, default=DEFAULT_TARGET_BATCH_MS
    )
    parser.add_argument(
        "--max-batch-launches", type=int, default=DEFAULT_MAX_BATCH_LAUNCHES
    )
    parser.add_argument(
        "--stability-repeats", type=int, default=DEFAULT_STABILITY_REPEATS
    )
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--fit-min-n", type=int, default=DEFAULT_SIZES[0])
    parser.add_argument("--fit-max-n", type=int, default=DEFAULT_SIZES[-1])
    parser.add_argument(
        "--slope-lower", type=float, default=DEFAULT_SLOPE_LOWER
    )
    parser.add_argument(
        "--slope-upper", type=float, default=DEFAULT_SLOPE_UPPER
    )
    parser.add_argument("--min-r2", type=float, default=DEFAULT_MIN_R2)
    parser.add_argument("--max-cv", type=float, default=DEFAULT_MAX_CV)
    parser.add_argument(
        "--max-batch-stability-delta",
        type=float,
        default=DEFAULT_MAX_BATCH_STABILITY_DELTA,
    )
    parser.add_argument(
        "--max-end-repeat-drift",
        type=float,
        default=DEFAULT_MAX_END_REPEAT_DRIFT,
    )
    parser.add_argument(
        "--bootstrap-replicates", type=int, default=DEFAULT_BOOTSTRAP_REPLICATES
    )
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    parser.add_argument(
        "--minimum-free-device-bytes",
        type=int,
        default=DEFAULT_MIN_FREE_DEVICE_BYTES,
    )
    parser.add_argument(
        "--max-payload-fraction",
        type=float,
        default=DEFAULT_MAX_PAYLOAD_FRACTION,
    )
    parser.add_argument("--device-ordinal", type=int, default=0)
    parser.add_argument("--agent-enumerator", type=Path)
    parser.add_argument("--runtime-library", type=Path)
    parser.add_argument("--hiprtc-library", type=Path)
    parser.add_argument("--out", type=Path)
    return parser


def _clean_worker_environment(
    environment: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    cleaned = dict(environment)
    removed = tuple(name for name in SERIALIZATION_ENV_VARS if name in cleaned)
    for name in SERIALIZATION_ENV_VARS:
        cleaned.pop(name, None)
    cleaned[WORKER_SENTINEL] = "1"
    cleaned[SANITIZED_FROM] = ",".join(removed)
    return cleaned, removed


def _worker_needs_reexec(environment: Mapping[str, str]) -> bool:
    return environment.get(WORKER_SENTINEL) != "1" or any(
        name in environment for name in SERIALIZATION_ENV_VARS
    )


def _reexec_clean_worker(
    argv: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> int:
    source = os.environ if environment is None else environment
    cleaned, _ = _clean_worker_environment(source)
    completed = runner(
        [sys.executable, str(Path(__file__).resolve()), *argv],
        env=cleaned,
        check=False,
    )
    return int(completed.returncode)


def _parse_sizes(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in raw.split(","))
    except ValueError as exc:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--sizes must contain only comma-separated integers.",
        ) from exc
    if len(values) < 5:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "At least five sizes are required.",
        )
    if any(value <= 0 for value in values):
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid", "Sizes must be positive."
        )
    if any(left >= right for left, right in zip(values, values[1:])):
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Sizes must be unique and strictly increasing.",
        )
    if values[-1] > _MAX_CSR_ROWS:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "The largest 3N-2 CSR nnz exceeds signed int32.",
        )
    return values


def _validate_configuration(
    args: argparse.Namespace, sizes: tuple[int, ...]
) -> None:
    integer_values = (
        ("warmup_launches", args.warmup_launches),
        ("pilot_launches", args.pilot_launches),
        ("max_batch_launches", args.max_batch_launches),
        ("stability_repeats", args.stability_repeats),
        ("repeats", args.repeats),
        ("bootstrap_replicates", args.bootstrap_replicates),
    )
    if any(isinstance(value, bool) or value <= 0 for _, value in integer_values):
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Warmups, calibration, repeats, and bootstrap counts must be positive.",
        )
    if args.repeats < 3:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "At least three raw timing trials are required per size.",
        )
    if args.warmup_launches < 20:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "At least 20 warmup launches are required.",
        )
    if args.max_batch_launches < 2:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--max-batch-launches must be at least 2 for the K/2K check.",
        )
    if args.stability_repeats < 3:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "At least three K and 2K stability trials are required.",
        )
    if args.bootstrap_replicates < 200:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "At least 200 stratified bootstrap replicates are required.",
        )
    if args.device_ordinal < 0:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Device ordinal must be non-negative.",
        )
    if not 0.0 < args.max_payload_fraction <= 0.75:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--max-payload-fraction must be in (0, 0.75].",
        )
    if args.minimum_free_device_bytes < 0:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--minimum-free-device-bytes must be non-negative.",
        )
    finite = (
        args.slope_lower,
        args.slope_upper,
        args.min_r2,
        args.target_batch_ms,
        args.max_cv,
        args.max_batch_stability_delta,
        args.max_end_repeat_drift,
    )
    if not all(math.isfinite(value) for value in finite):
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Slope and R2 thresholds must be finite.",
        )
    if not 0.0 < args.slope_lower < args.slope_upper:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Slope bounds must satisfy 0 < lower < upper.",
        )
    if not 0.0 <= args.min_r2 <= 1.0:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--min-r2 must be in [0, 1].",
        )
    if args.target_batch_ms < 20.0:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "--target-batch-ms must be at least 20 ms.",
        )
    for label, value in (
        ("max_cv", args.max_cv),
        ("max_batch_stability_delta", args.max_batch_stability_delta),
        ("max_end_repeat_drift", args.max_end_repeat_drift),
    ):
        if not 0.0 < value <= 0.25:
            raise BenchmarkError(
                "rtc_scaling_configuration_invalid",
                f"--{label.replace('_', '-')} must be in (0, 0.25].",
            )
    if args.fit_min_n > args.fit_max_n:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Fit minimum must not exceed fit maximum.",
        )
    if args.fit_min_n <= 0 or args.fit_max_n <= 0:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "Fit bounds must be positive.",
        )
    fit_sizes = tuple(
        value for value in sizes if args.fit_min_n <= value <= args.fit_max_n
    )
    if len(fit_sizes) < 5:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "The explicit fit range must include at least five measured sizes.",
        )
    if fit_sizes[-1] < 4 * fit_sizes[0]:
        raise BenchmarkError(
            "rtc_scaling_configuration_invalid",
            "The explicit fit range must span at least 4x in row count.",
        )


def _resolve_enumerator(explicit: Path | None) -> str | None:
    if explicit is not None:
        return str(explicit) if explicit.is_file() else None
    discovered = shutil.which("rocm_agent_enumerator")
    if discovered is not None:
        return discovered
    for candidate in (
        Path("/opt/rocm/bin/rocm_agent_enumerator"),
        Path("/opt/rocm-6.0.2/bin/rocm_agent_enumerator"),
    ):
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate)
    return None


def _detect_architectures(executable: str | None) -> tuple[str, ...]:
    if executable is None:
        return ()
    try:
        completed = subprocess.run(
            [executable],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0:
        return ()
    targets: list[str] = []
    for token in completed.stdout.split():
        target = token.strip().lower()
        if (
            target != "gfx000"
            and _ARCH_PATTERN.fullmatch(target)
            and target not in targets
        ):
            targets.append(target)
    return tuple(targets)


def _csr_nnz(row_count: int) -> int:
    return 1 if row_count == 1 else 3 * row_count - 2


def _logical_work(row_count: int) -> dict[str, int]:
    nnz = _csr_nnz(row_count)
    return {
        "csr_nnz": nnz,
        "fp64_equivalent_operations_per_launch": 4 * nnz + row_count,
        "source_logical_bytes_per_launch": 28 * nnz + 32 * row_count,
        "unique_read_bytes": 12 * nnz + 28 * row_count + 4,
        "resident_touched_bytes": 12 * nnz + 44 * row_count + 4,
        "physical_dram_bytes": "not_instrumented",
        "grid_block_count": (row_count + REFERENCE_BLOCK_SIZE - 1)
        // REFERENCE_BLOCK_SIZE,
    }


def _allocated_payload_bytes(row_count: int) -> int:
    """Eight data allocations: CSR triplet and five FP64 full vectors."""

    nnz = _csr_nnz(row_count)
    return 4 * (row_count + 1) + 4 * nnz + 8 * nnz + 5 * 8 * row_count


def _initial_h2d_bytes(row_count: int) -> int:
    """CSR triplet plus state, load, and direction uploaded once."""

    nnz = _csr_nnz(row_count)
    return 4 * (row_count + 1) + 4 * nnz + 8 * nnz + 3 * 8 * row_count


def _build_tridiagonal_csr(row_count: int) -> tuple[Any, ...]:
    import numpy as np

    nnz = _csr_nnz(row_count)
    row_ptr = np.empty(row_count + 1, dtype="<i4")
    row_ptr[0] = 0
    if row_count == 1:
        row_ptr[1] = 1
        columns = np.array([0], dtype="<i4")
        values = np.array([2.5], dtype="<f8")
    else:
        row_ptr[1:-1] = 3 * np.arange(1, row_count, dtype="<i4") - 1
        row_ptr[-1] = nnz
        columns = np.empty(nnz, dtype="<i4")
        values = np.empty(nnz, dtype="<f8")
        columns[:2] = (0, 1)
        values[:2] = (2.5, -0.25)
        columns[-2:] = (row_count - 2, row_count - 1)
        values[-2:] = (-0.25, 2.5)
        if row_count > 2:
            rows = np.arange(1, row_count - 1, dtype="<i4")
            interior_columns = columns[2:-2].reshape(-1, 3)
            interior_values = values[2:-2].reshape(-1, 3)
            interior_columns[:, 0] = rows - 1
            interior_columns[:, 1] = rows
            interior_columns[:, 2] = rows + 1
            interior_values[:] = (-0.25, 2.5, -0.25)
    indices = np.arange(row_count, dtype=np.float64)
    state = np.ascontiguousarray((indices % 97.0 - 48.0) * 1.0e-7, dtype="<f8")
    load = np.ascontiguousarray((indices % 31.0 - 15.0) * 1.0e-5, dtype="<f8")
    direction = np.ascontiguousarray(
        ((indices % 2.0) * 2.0 - 1.0) * (indices % 53.0 + 1.0) * 1.0e-8,
        dtype="<f8",
    )
    residual = np.empty(row_count, dtype="<f8")
    jvp = np.empty(row_count, dtype="<f8")
    arrays = (
        row_ptr,
        columns,
        values,
        state,
        load,
        direction,
        residual,
        jvp,
    )
    if sum(int(array.nbytes) for array in arrays) != _allocated_payload_bytes(
        row_count
    ):
        raise AssertionError("Allocated payload formula drifted from arrays.")
    return arrays


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _theil_sen_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    return float(
        statistics.median(
            (ys[right] - ys[left]) / (xs[right] - xs[left])
            for left in range(len(xs))
            for right in range(left + 1, len(xs))
        )
    )


def _fit_log_log(
    samples: Sequence[Mapping[str, Any]],
    *,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if len(samples) < 5:
        raise BenchmarkError(
            "rtc_scaling_fit_invalid", "At least five fit samples are required."
        )
    xs = [math.log(float(sample["row_count"])) for sample in samples]
    ys = [math.log(float(sample["median_per_launch_ms"])) for sample in samples]
    if any(not math.isfinite(value) for value in (*xs, *ys)):
        raise BenchmarkError(
            "rtc_scaling_fit_invalid", "Fit inputs must be finite and positive."
        )
    pairwise = [
        (ys[right] - ys[left]) / (xs[right] - xs[left])
        for left in range(len(xs))
        for right in range(left + 1, len(xs))
    ]
    robust_slope = float(statistics.median(pairwise))
    robust_intercept = float(
        statistics.median(
            y_value - robust_slope * x_value
            for x_value, y_value in zip(xs, ys)
        )
    )
    robust_predictions = [
        robust_intercept + robust_slope * value for value in xs
    ]
    mean_y = statistics.fmean(ys)
    total_sum_squares = sum((value - mean_y) ** 2 for value in ys)
    robust_residual_sum_squares = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(ys, robust_predictions)
    )
    robust_r2 = (
        1.0 - robust_residual_sum_squares / total_sum_squares
        if total_sum_squares > 0.0
        else 1.0
    )

    mean_x = statistics.fmean(xs)
    covariance = sum(
        (x_value - mean_x) * (y_value - mean_y)
        for x_value, y_value in zip(xs, ys)
    )
    variance_x = sum((value - mean_x) ** 2 for value in xs)
    ols_slope = covariance / variance_x
    ols_intercept = mean_y - ols_slope * mean_x
    ols_residual_sum_squares = sum(
        (y_value - (ols_intercept + ols_slope * x_value)) ** 2
        for x_value, y_value in zip(xs, ys)
    )
    ols_r2 = (
        1.0 - ols_residual_sum_squares / total_sum_squares
        if total_sum_squares > 0.0
        else 1.0
    )
    rng = random.Random(bootstrap_seed)
    bootstrap_slopes: list[float] = []
    for _ in range(bootstrap_replicates):
        bootstrap_ys: list[float] = []
        for sample in samples:
            trials = [
                float(trial["per_launch_ms"])
                for trial in sample.get("raw_trials", ())
            ]
            if len(trials) < 3:
                raise BenchmarkError(
                    "rtc_scaling_fit_invalid",
                    "Every bootstrap stratum requires at least three raw trials.",
                )
            resampled = [trials[rng.randrange(len(trials))] for _ in trials]
            bootstrap_ys.append(math.log(float(statistics.median(resampled))))
        bootstrap_slopes.append(_theil_sen_slope(xs, bootstrap_ys))
    return {
        "method": "theil_sen_log_log_with_ols_diagnostic",
        "point_count": len(samples),
        "row_count_min": int(samples[0]["row_count"]),
        "row_count_max": int(samples[-1]["row_count"]),
        "robust_slope": robust_slope,
        "robust_intercept_log_ms": robust_intercept,
        "robust_r2": float(robust_r2),
        "ols_slope": float(ols_slope),
        "ols_intercept_log_ms": float(ols_intercept),
        "ols_r2": float(ols_r2),
        "pairwise_slope_count": len(pairwise),
        "bootstrap_method": "stratified_trial_resample_theil_sen",
        "bootstrap_replicates": bootstrap_replicates,
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_slope_ci95_lower": _percentile(bootstrap_slopes, 0.025),
        "bootstrap_slope_ci95_upper": _percentile(bootstrap_slopes, 0.975),
    }


def _acceptance(
    fit: Mapping[str, Any] | None,
    *,
    samples: Sequence[Mapping[str, Any]] = (),
    slope_lower: float,
    slope_upper: float,
    min_r2: float,
    max_cv: float = DEFAULT_MAX_CV,
    max_batch_stability_delta: float = DEFAULT_MAX_BATCH_STABILITY_DELTA,
    max_end_repeat_drift: float = DEFAULT_MAX_END_REPEAT_DRIFT,
    hardware_profile_matched: bool = False,
) -> dict[str, Any]:
    if fit is None:
        return {
            "evaluated": False,
            "accepted": False,
            "scope": CLAIM_SCOPE,
            "slope_lower_inclusive": slope_lower,
            "slope_upper_inclusive": slope_upper,
            "minimum_ols_r2": min_r2,
            "robust_slope_passed": False,
            "ols_slope_passed": False,
            "r2_passed": False,
            "bootstrap_ci_passed": False,
            "hardware_profile_matched": False,
            "off_cache_occupancy_precondition_passed": False,
            "batch_duration_passed": False,
            "batch_length_stability_passed": False,
            "coefficient_of_variation_passed": False,
            "end_repeat_drift_passed": False,
            "correctness_passed": False,
            "timed_region_clean": False,
            "outcome": "not_evaluated",
        }
    robust_slope_passed = (
        slope_lower <= float(fit["robust_slope"]) <= slope_upper
    )
    ols_slope_passed = slope_lower <= float(fit["ols_slope"]) <= slope_upper
    r2_passed = float(fit["ols_r2"]) >= min_r2
    bootstrap_ci_passed = (
        float(fit["bootstrap_slope_ci95_lower"]) >= slope_lower
        and float(fit["bootstrap_slope_ci95_upper"]) <= slope_upper
    )
    off_cache = hardware_profile_matched and all(
        int(sample["unique_read_bytes"]) >= 2 * REFERENCE_CACHE_BYTES
        and int(sample["grid_block_count"])
        >= 8 * REFERENCE_COMPUTE_UNITS
        for sample in samples
    )
    duration = all(
        float(sample["median_batch_elapsed_ms"]) >= 20.0 for sample in samples
    )
    batch_stability = all(
        float(sample["batch_length_stability_relative_delta"])
        <= max_batch_stability_delta
        for sample in samples
    )
    cv = all(
        float(sample["coefficient_of_variation"]) <= max_cv
        for sample in samples
    )
    drift = all(
        float(sample["end_repeat_relative_drift"]) <= max_end_repeat_drift
        for sample in samples
    )
    correctness = all(bool(sample["correctness"]["passed"]) for sample in samples)
    timed_clean = all(
        int(sample["timed_region_h2d_operation_count"]) == 0
        and int(sample["timed_region_d2h_operation_count"]) == 0
        and int(sample["timed_region_allocation_count"]) == 0
        and int(sample["fallback_count"]) == 0
        for sample in samples
    )
    quality_passed = all((off_cache, duration, batch_stability, cv, drift))
    scaling_passed = all(
        (
            robust_slope_passed,
            ols_slope_passed,
            r2_passed,
        )
    )
    accepted = (
        correctness
        and timed_clean
        and quality_passed
        and scaling_passed
        and bootstrap_ci_passed
    )
    if not correctness or not timed_clean:
        outcome = "rejected"
    elif not quality_passed:
        outcome = "inconclusive"
    elif not scaling_passed:
        outcome = "rejected"
    elif not bootstrap_ci_passed:
        outcome = "inconclusive"
    else:
        outcome = "accepted"
    return {
        "evaluated": True,
        "accepted": bool(accepted),
        "scope": CLAIM_SCOPE,
        "slope_lower_inclusive": slope_lower,
        "slope_upper_inclusive": slope_upper,
        "minimum_ols_r2": min_r2,
        "robust_slope_passed": bool(robust_slope_passed),
        "ols_slope_passed": bool(ols_slope_passed),
        "r2_passed": bool(r2_passed),
        "bootstrap_ci_passed": bool(bootstrap_ci_passed),
        "hardware_profile_matched": bool(hardware_profile_matched),
        "off_cache_occupancy_precondition_passed": bool(off_cache),
        "batch_duration_passed": bool(duration),
        "batch_length_stability_passed": bool(batch_stability),
        "coefficient_of_variation_passed": bool(cv),
        "end_repeat_drift_passed": bool(drift),
        "correctness_passed": bool(correctness),
        "timed_region_clean": bool(timed_clean),
        "outcome": outcome,
    }


class _HipBenchmarkRuntime:
    """Process-local HIP allocation, stream, and event surface."""

    def __init__(self, loaded_runtime: Any) -> None:
        self._loaded = loaded_runtime
        bind = loaded_runtime.bind
        self._set_device = bind("hipSetDevice", [ctypes.c_int], ctypes.c_int)
        self._mem_info = bind(
            "hipMemGetInfo",
            [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)],
            ctypes.c_int,
        )
        self._stream_create = bind(
            "hipStreamCreateWithFlags",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint],
            ctypes.c_int,
        )
        self._stream_destroy = bind(
            "hipStreamDestroy", [ctypes.c_void_p], ctypes.c_int
        )
        self._malloc = bind(
            "hipMalloc",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t],
            ctypes.c_int,
        )
        self._free = bind("hipFree", [ctypes.c_void_p], ctypes.c_int)
        self._memcpy_async = bind(
            "hipMemcpyAsync",
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_int,
                ctypes.c_void_p,
            ],
            ctypes.c_int,
        )
        self._stream_sync = bind(
            "hipStreamSynchronize", [ctypes.c_void_p], ctypes.c_int
        )
        self._event_create = bind(
            "hipEventCreateWithFlags",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint],
            ctypes.c_int,
        )
        self._event_record = bind(
            "hipEventRecord", [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_int
        )
        self._event_sync = bind(
            "hipEventSynchronize", [ctypes.c_void_p], ctypes.c_int
        )
        self._event_elapsed = bind(
            "hipEventElapsedTime",
            [
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_void_p,
                ctypes.c_void_p,
            ],
            ctypes.c_int,
        )
        self._event_destroy = bind(
            "hipEventDestroy", [ctypes.c_void_p], ctypes.c_int
        )

    def _check(self, status: int, where: str) -> None:
        if int(status) != 0:
            raise BenchmarkError(
                "rtc_scaling_hip_call_failed",
                f"{where}: {self._loaded.hip_error_string(int(status))}",
            )

    def set_device(self, ordinal: int) -> None:
        self._check(self._set_device(ordinal), "hipSetDevice")

    def mem_info(self) -> tuple[int, int]:
        free = ctypes.c_size_t()
        total = ctypes.c_size_t()
        self._check(
            self._mem_info(ctypes.byref(free), ctypes.byref(total)),
            "hipMemGetInfo",
        )
        return int(free.value), int(total.value)

    def create_stream(self) -> ctypes.c_void_p:
        stream = ctypes.c_void_p()
        self._check(
            self._stream_create(ctypes.byref(stream), _HIP_STREAM_NON_BLOCKING),
            "hipStreamCreateWithFlags",
        )
        if not stream.value:
            raise BenchmarkError(
                "rtc_scaling_hip_call_failed", "HIP returned a null stream."
            )
        return stream

    def destroy_stream(self, stream: ctypes.c_void_p) -> None:
        self._check(self._stream_destroy(stream), "hipStreamDestroy")

    def malloc(self, byte_length: int) -> ctypes.c_void_p:
        pointer = ctypes.c_void_p()
        self._check(
            self._malloc(ctypes.byref(pointer), int(byte_length)), "hipMalloc"
        )
        if not pointer.value:
            raise BenchmarkError(
                "rtc_scaling_hip_call_failed", "HIP returned a null allocation."
            )
        return pointer

    def free(self, pointer: ctypes.c_void_p) -> None:
        self._check(self._free(pointer), "hipFree")

    def copy_h2d_async(
        self, pointer: ctypes.c_void_p, array: Any, stream: ctypes.c_void_p
    ) -> None:
        self._check(
            self._memcpy_async(
                pointer,
                ctypes.c_void_p(int(array.ctypes.data)),
                int(array.nbytes),
                _HIP_MEMCPY_HOST_TO_DEVICE,
                stream,
            ),
            "hipMemcpyAsync(H2D)",
        )

    def copy_d2h_async(
        self, array: Any, pointer: ctypes.c_void_p, stream: ctypes.c_void_p
    ) -> None:
        self._check(
            self._memcpy_async(
                ctypes.c_void_p(int(array.ctypes.data)),
                pointer,
                int(array.nbytes),
                _HIP_MEMCPY_DEVICE_TO_HOST,
                stream,
            ),
            "hipMemcpyAsync(D2H)",
        )

    def synchronize_stream(self, stream: ctypes.c_void_p) -> None:
        self._check(self._stream_sync(stream), "hipStreamSynchronize")

    def create_event(self) -> ctypes.c_void_p:
        event = ctypes.c_void_p()
        self._check(
            self._event_create(ctypes.byref(event), _HIP_EVENT_DEFAULT),
            "hipEventCreateWithFlags",
        )
        if not event.value:
            raise BenchmarkError(
                "rtc_scaling_hip_call_failed", "HIP returned a null event."
            )
        return event

    def record_event(
        self, event: ctypes.c_void_p, stream: ctypes.c_void_p
    ) -> None:
        self._check(self._event_record(event, stream), "hipEventRecord")

    def synchronize_event(self, event: ctypes.c_void_p) -> None:
        self._check(self._event_sync(event), "hipEventSynchronize")

    def elapsed_ms(
        self, start: ctypes.c_void_p, stop: ctypes.c_void_p
    ) -> float:
        elapsed = ctypes.c_float()
        self._check(
            self._event_elapsed(ctypes.byref(elapsed), start, stop),
            "hipEventElapsedTime",
        )
        value = float(elapsed.value)
        if not math.isfinite(value) or value <= 0.0:
            raise BenchmarkError(
                "rtc_scaling_event_timing_invalid",
                "HIP event elapsed time must be finite and positive.",
            )
        return value

    def destroy_event(self, event: ctypes.c_void_p) -> None:
        self._check(self._event_destroy(event), "hipEventDestroy")


def _time_launch_batch(
    *,
    runtime: _HipBenchmarkRuntime,
    kernel: Any,
    stream: ctypes.c_void_p,
    start: ctypes.c_void_p,
    stop: ctypes.c_void_p,
    launch_args: tuple[Any, ...],
    launch_count: int,
) -> float:
    runtime.record_event(start, stream)
    for _ in range(launch_count):
        kernel.launch_residual_jvp(*launch_args)
    runtime.record_event(stop, stream)
    runtime.synchronize_event(stop)
    return runtime.elapsed_ms(start, stop)


def _verify_outputs(arrays: tuple[Any, ...]) -> dict[str, Any]:
    import numpy as np

    state, load, direction, residual, jvp = arrays[3:]
    row_count = int(state.size)
    chunk_rows = 1_048_576
    residual_error_sq = 0.0
    residual_reference_sq = 0.0
    jvp_error_sq = 0.0
    jvp_reference_sq = 0.0
    residual_max_abs = 0.0
    jvp_max_abs = 0.0
    finite = True
    for lower in range(0, row_count, chunk_rows):
        upper = min(row_count, lower + chunk_rows)
        expected_residual = 2.5 * state[lower:upper] - load[lower:upper]
        expected_jvp = 2.5 * direction[lower:upper]
        if lower > 0:
            expected_residual -= 0.25 * state[lower - 1 : upper - 1]
            expected_jvp -= 0.25 * direction[lower - 1 : upper - 1]
        elif upper > 1:
            expected_residual[1:] -= 0.25 * state[: upper - 1]
            expected_jvp[1:] -= 0.25 * direction[: upper - 1]
        if upper < row_count:
            expected_residual -= 0.25 * state[lower + 1 : upper + 1]
            expected_jvp -= 0.25 * direction[lower + 1 : upper + 1]
        elif upper - lower > 1:
            expected_residual[:-1] -= 0.25 * state[lower + 1 : upper]
            expected_jvp[:-1] -= 0.25 * direction[lower + 1 : upper]
        actual_residual = residual[lower:upper]
        actual_jvp = jvp[lower:upper]
        finite = finite and bool(
            np.isfinite(actual_residual).all() and np.isfinite(actual_jvp).all()
        )
        residual_error = actual_residual - expected_residual
        jvp_error = actual_jvp - expected_jvp
        residual_max_abs = max(
            residual_max_abs, float(np.max(np.abs(residual_error)))
        )
        jvp_max_abs = max(jvp_max_abs, float(np.max(np.abs(jvp_error))))
        residual_error_sq += float(np.dot(residual_error, residual_error))
        residual_reference_sq += float(
            np.dot(expected_residual, expected_residual)
        )
        jvp_error_sq += float(np.dot(jvp_error, jvp_error))
        jvp_reference_sq += float(np.dot(expected_jvp, expected_jvp))
    tiny = float(np.finfo(np.float64).tiny)
    residual_relative_l2 = math.sqrt(
        residual_error_sq / max(residual_reference_sq, tiny)
    )
    jvp_relative_l2 = math.sqrt(jvp_error_sq / max(jvp_reference_sq, tiny))
    passed = bool(
        finite
        and residual_max_abs <= 1.0e-10
        and jvp_max_abs <= 1.0e-10
        and residual_relative_l2 <= 1.0e-10
        and jvp_relative_l2 <= 1.0e-10
    )
    return {
        "performed_outside_timed_region": True,
        "finite": finite,
        "residual_max_abs_error": residual_max_abs,
        "residual_relative_l2_error": residual_relative_l2,
        "jvp_max_abs_error": jvp_max_abs,
        "jvp_relative_l2_error": jvp_relative_l2,
        "absolute_tolerance": 1.0e-10,
        "relative_l2_tolerance": 1.0e-10,
        "passed": passed,
    }


def _measure_one_size(
    *,
    row_count: int,
    runtime: _HipBenchmarkRuntime,
    kernel: Any,
    stream: ctypes.c_void_p,
    warmup_launches: int,
    pilot_launches: int,
    target_batch_ms: float,
    max_batch_launches: int,
    stability_repeats: int,
    repeats: int,
) -> dict[str, Any]:
    arrays = _build_tridiagonal_csr(row_count)
    pointers: list[ctypes.c_void_p] = []
    start: ctypes.c_void_p | None = None
    stop: ctypes.c_void_p | None = None
    primary: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        for array in arrays:
            pointers.append(runtime.malloc(int(array.nbytes)))
        for pointer, array in zip(pointers[:6], arrays[:6]):
            runtime.copy_h2d_async(pointer, array, stream)
        runtime.synchronize_stream(stream)
        start = runtime.create_event()
        stop = runtime.create_event()

        launch_args = (
            stream,
            row_count,
            *pointers,
        )
        for _ in range(warmup_launches):
            kernel.launch_residual_jvp(*launch_args)
        runtime.synchronize_stream(stream)

        pilot_elapsed_ms = _time_launch_batch(
            runtime=runtime,
            kernel=kernel,
            stream=stream,
            start=start,
            stop=stop,
            launch_args=launch_args,
            launch_count=pilot_launches,
        )
        pilot_per_launch_ms = pilot_elapsed_ms / pilot_launches
        batch_launches = max(
            1, int(math.ceil(target_batch_ms / pilot_per_launch_ms))
        )
        batch_launches = min(batch_launches, max_batch_launches // 2)
        calibration_trials: list[dict[str, Any]] = []
        stability_k_elapsed: list[float] = []
        for calibration_index in range(4):
            stability_k_elapsed = [
                _time_launch_batch(
                    runtime=runtime,
                    kernel=kernel,
                    stream=stream,
                    start=start,
                    stop=stop,
                    launch_args=launch_args,
                    launch_count=batch_launches,
                )
                for _ in range(stability_repeats)
            ]
            median_elapsed = float(statistics.median(stability_k_elapsed))
            calibration_trials.append(
                {
                    "calibration_index": calibration_index,
                    "launch_count": batch_launches,
                    "median_batch_elapsed_ms": median_elapsed,
                    "raw_batch_elapsed_ms": stability_k_elapsed,
                }
            )
            if median_elapsed >= target_batch_ms:
                break
            multiplier = max(2, int(math.ceil(target_batch_ms / median_elapsed)))
            next_count = min(
                max_batch_launches // 2, batch_launches * multiplier
            )
            if next_count == batch_launches:
                break
            batch_launches = next_count
        double_batch_launches = 2 * batch_launches
        stability_2k_elapsed = [
            _time_launch_batch(
                runtime=runtime,
                kernel=kernel,
                stream=stream,
                start=start,
                stop=stop,
                launch_args=launch_args,
                launch_count=double_batch_launches,
            )
            for _ in range(stability_repeats)
        ]
        median_k_per_launch = float(statistics.median(stability_k_elapsed)) / (
            batch_launches
        )
        median_2k_per_launch = float(
            statistics.median(stability_2k_elapsed)
        ) / double_batch_launches
        batch_stability_delta = abs(
            median_2k_per_launch - median_k_per_launch
        ) / median_k_per_launch

        raw_trials: list[dict[str, float | int]] = []
        for trial_index in range(repeats):
            total_ms = _time_launch_batch(
                runtime=runtime,
                kernel=kernel,
                stream=stream,
                start=start,
                stop=stop,
                launch_args=launch_args,
                launch_count=batch_launches,
            )
            raw_trials.append(
                {
                    "trial_index": trial_index,
                    "batch_elapsed_ms": total_ms,
                    "per_launch_ms": total_ms / batch_launches,
                }
            )
        end_repeat_elapsed_ms = _time_launch_batch(
            runtime=runtime,
            kernel=kernel,
            stream=stream,
            start=start,
            stop=stop,
            launch_args=launch_args,
            launch_count=batch_launches,
        )
        per_launch = [float(trial["per_launch_ms"]) for trial in raw_trials]
        median_per_launch = float(statistics.median(per_launch))
        mean_per_launch = float(statistics.fmean(per_launch))
        standard_deviation = float(statistics.stdev(per_launch))
        coefficient_of_variation = standard_deviation / mean_per_launch
        median_absolute_deviation = float(
            statistics.median(abs(value - median_per_launch) for value in per_launch)
        )
        end_repeat_per_launch_ms = end_repeat_elapsed_ms / batch_launches
        end_repeat_relative_drift = abs(
            end_repeat_per_launch_ms - median_per_launch
        ) / median_per_launch

        # Correctness download and oracle are deliberately after every event-
        # timed launch.  They do not contribute to any timing or slope input.
        runtime.copy_d2h_async(arrays[6], pointers[6], stream)
        runtime.copy_d2h_async(arrays[7], pointers[7], stream)
        runtime.synchronize_stream(stream)
        correctness = _verify_outputs(arrays)
        work = _logical_work(row_count)
        result = {
            "row_count": row_count,
            **work,
            "allocated_device_payload_bytes": _allocated_payload_bytes(row_count),
            "allocation_count": 8,
            "initial_h2d_operation_count": 6,
            "initial_h2d_bytes": _initial_h2d_bytes(row_count),
            "outside_timed_region_d2h_operation_count": 2,
            "outside_timed_region_d2h_bytes": 16 * row_count,
            "warmup_launch_count": warmup_launches,
            "pilot_launch_count": pilot_launches,
            "pilot_batch_elapsed_ms": pilot_elapsed_ms,
            "calibration_trials": calibration_trials,
            "timed_batch_launch_count": batch_launches,
            "double_batch_launch_count": double_batch_launches,
            "batch_length_stability_k_per_launch_ms": median_k_per_launch,
            "batch_length_stability_2k_per_launch_ms": median_2k_per_launch,
            "batch_length_stability_relative_delta": batch_stability_delta,
            "batch_length_stability_k_raw_batch_elapsed_ms": (
                stability_k_elapsed
            ),
            "batch_length_stability_2k_raw_batch_elapsed_ms": (
                stability_2k_elapsed
            ),
            "timed_trial_count": repeats,
            "fit_trial_kernel_launch_count": batch_launches * repeats,
            "event_timed_kernel_launch_count_total": (
                pilot_launches
                + sum(
                    int(item["launch_count"]) * stability_repeats
                    for item in calibration_trials
                )
                + double_batch_launches * stability_repeats
                + batch_launches * repeats
                + batch_launches
            ),
            "timed_region_h2d_operation_count": 0,
            "timed_region_d2h_operation_count": 0,
            "timed_region_allocation_count": 0,
            "fallback_count": 0,
            "raw_trials": raw_trials,
            "median_batch_elapsed_ms": float(
                statistics.median(
                    float(trial["batch_elapsed_ms"]) for trial in raw_trials
                )
            ),
            "median_per_launch_ms": median_per_launch,
            "minimum_per_launch_ms": min(per_launch),
            "maximum_per_launch_ms": max(per_launch),
            "mean_per_launch_ms": mean_per_launch,
            "standard_deviation_per_launch_ms": standard_deviation,
            "median_absolute_deviation_per_launch_ms": median_absolute_deviation,
            "coefficient_of_variation": coefficient_of_variation,
            "end_repeat_batch_elapsed_ms": end_repeat_elapsed_ms,
            "end_repeat_per_launch_ms": end_repeat_per_launch_ms,
            "end_repeat_relative_drift": end_repeat_relative_drift,
            "event_timing_scope": "steady_state_stream_dispatch_plus_kernel",
            "correctness": correctness,
        }
    except BaseException as exc:
        primary = exc

    cleanup_errors: list[str] = []
    for event, label in ((stop, "stop_event"), (start, "start_event")):
        if event is not None:
            try:
                runtime.destroy_event(event)
            except Exception as exc:  # pragma: no cover - hardware failure
                cleanup_errors.append(f"{label}:{type(exc).__name__}")
    for index, pointer in reversed(list(enumerate(pointers))):
        try:
            runtime.free(pointer)
        except Exception as exc:  # pragma: no cover - hardware failure
            cleanup_errors.append(f"allocation_{index}:{type(exc).__name__}")
    if cleanup_errors:
        raise BenchmarkError(
            "rtc_scaling_cleanup_failed", ",".join(cleanup_errors)
        ) from primary
    if primary is not None:
        raise primary
    if result is None:
        raise AssertionError("Measurement completed without a result.")
    return result


def _balanced_measurement_order(sizes: tuple[int, ...]) -> tuple[int, ...]:
    result: list[int] = []
    lower = 0
    upper = len(sizes) - 1
    while lower <= upper:
        result.append(sizes[lower])
        lower += 1
        if lower <= upper:
            result.append(sizes[upper])
            upper -= 1
    return tuple(result)


def _configuration_payload(
    args: argparse.Namespace, sizes: tuple[int, ...]
) -> dict[str, Any]:
    default_regime = sizes == DEFAULT_SIZES and (
        args.fit_min_n == DEFAULT_SIZES[0]
        and args.fit_max_n == DEFAULT_SIZES[-1]
    )
    return {
        "sizes": list(sizes),
        "measurement_order": list(_balanced_measurement_order(sizes)),
        "measurement_order_policy": "alternating_low_high_predeclared",
        "warmup_launches": args.warmup_launches,
        "pilot_launches": args.pilot_launches,
        "target_batch_ms": args.target_batch_ms,
        "max_batch_launches": args.max_batch_launches,
        "stability_repeats": args.stability_repeats,
        "repeats": args.repeats,
        "fit_min_n": args.fit_min_n,
        "fit_max_n": args.fit_max_n,
        "slope_lower_inclusive": args.slope_lower,
        "slope_upper_inclusive": args.slope_upper,
        "minimum_ols_r2": args.min_r2,
        "maximum_coefficient_of_variation": args.max_cv,
        "maximum_batch_length_stability_relative_delta": (
            args.max_batch_stability_delta
        ),
        "maximum_end_repeat_relative_drift": args.max_end_repeat_drift,
        "bootstrap_replicates": args.bootstrap_replicates,
        "bootstrap_seed": args.bootstrap_seed,
        "minimum_free_device_bytes": args.minimum_free_device_bytes,
        "maximum_payload_fraction_of_free_memory": args.max_payload_fraction,
        "fit_regime": (
            "predeclared_dram_resident_large_problem"
            if default_regime
            else "explicit_user_configured"
        ),
        "fit_regime_rationale": (
            "Lower row counts are excluded a priori from the default fit "
            "because launch, occupancy, and cache-capacity transitions are "
            "non-asymptotic kernel regimes."
        ),
        "off_cache_precondition": {
            "hardware_profile_source": "predeclared_rx6900xt_gfx1030",
            "expected_architecture": EXPECTED_PROFILE_ARCHITECTURE,
            "expected_device_name_token": EXPECTED_PROFILE_DEVICE_NAME_TOKEN,
            "reference_cache_bytes": REFERENCE_CACHE_BYTES,
            "minimum_unique_read_multiple": 2,
            "reference_compute_units": REFERENCE_COMPUTE_UNITS,
            "minimum_blocks_per_compute_unit": 8,
            "kernel_block_size": REFERENCE_BLOCK_SIZE,
        },
        "end_repeat_definition": (
            "same_allocation_same_size_after_main_trials_before_correctness_download"
        ),
        "automatic_size_downscaling": False,
    }


def _environment_payload() -> dict[str, Any]:
    present = [name for name in SERIALIZATION_ENV_VARS if name in os.environ]
    removed = tuple(
        name
        for name in os.environ.get(SANITIZED_FROM, "").split(",")
        if name
    )
    return {
        "clean_worker_reexec": os.environ.get(WORKER_SENTINEL) == "1",
        "serialization_overrides_removed_before_runtime_init": list(removed),
        "serialization_overrides_present_in_worker": present,
        "hip_launch_blocking": os.environ.get("HIP_LAUNCH_BLOCKING"),
        "amd_serialize_kernel": os.environ.get("AMD_SERIALIZE_KERNEL"),
        "amd_serialize_copy": os.environ.get("AMD_SERIALIZE_COPY"),
        "timing_api": "hip_event_elapsed_time",
        "host_wall_clock_used_for_acceptance": False,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _harness_identity() -> dict[str, Any]:
    import numpy as np

    repo_root = Path(__file__).resolve().parents[1]
    script_path = Path(__file__).resolve()
    schema_path = (
        repo_root
        / "src/structural_analysis/schemas/rtc_kernel_scaling_report_v1.schema.json"
    )
    return {
        "benchmark_script_resource": (
            "scripts/benchmark_engine_v2_rtc_kernel_scaling.py"
        ),
        "benchmark_script_sha256": _sha256_file(script_path),
        "report_schema_resource": (
            "src/structural_analysis/schemas/rtc_kernel_scaling_report_v1.schema.json"
        ),
        "report_schema_sha256": _sha256_file(schema_path),
        "python_implementation": sys.implementation.name,
        "python_version": ".".join(str(value) for value in sys.version_info[:3]),
        "numpy_version": str(np.__version__),
    }


def _base_report(
    *,
    args: argparse.Namespace,
    sizes: tuple[int, ...],
    architecture: str | None,
    detected_architectures: tuple[str, ...],
    enumerator: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "unavailable",
        "decision": "not_evaluated",
        "reason": None,
        "requested_backend": "hip",
        "actual_backend": None,
        "evidence_scope": EVIDENCE_SCOPE,
        "claim_scope": CLAIM_SCOPE,
        "evidence_authenticity": "unsigned_local_measurement",
        "signature": None,
        "promotion_eligible": False,
        "nonpromoting": True,
        "fallback_policy": "forbidden",
        "fallback_count": 0,
        "device_ordinal": args.device_ordinal,
        "architecture": architecture,
        "agent_enumerator": enumerator,
        "detected_architectures": list(detected_architectures),
        "environment": _environment_payload(),
        "harness_identity": _harness_identity(),
        "configuration": _configuration_payload(args, sizes),
        "device": None,
        "kernel_identity": None,
        "samples": [],
        "fit": None,
        "acceptance": _acceptance(
            None,
            slope_lower=args.slope_lower,
            slope_upper=args.slope_upper,
            min_r2=args.min_r2,
            max_cv=args.max_cv,
            max_batch_stability_delta=args.max_batch_stability_delta,
            max_end_repeat_drift=args.max_end_repeat_drift,
        ),
        "claims": {
            "kernel_scope_timing_measured": False,
            "kernel_scope_initial_linear_scaling_accepted": False,
            "physical_dram_bytes_measured": False,
            "numerical_parity_measured_in_timed_region": False,
            "end_to_end_o_n": False,
            "solver_o_n": False,
            "solver_speedup": False,
            "structural_solver_executed": False,
            "commercial_readiness": False,
        },
        "report_hash": "sha256:" + "0" * 64,
    }


def _kernel_identity_payload(identity: Any) -> dict[str, Any]:
    return {
        "kernel_symbol": str(identity.kernel_symbol),
        "architecture": str(identity.architecture),
        "source_sha256": str(identity.source_sha256),
        "code_object_sha256": str(identity.code_object_sha256),
        "identity_hash": str(identity.identity_hash),
        "hiprtc_version_major": int(identity.hiprtc_version_major),
        "hiprtc_version_minor": int(identity.hiprtc_version_minor),
        "runtime_library_sha256": str(identity.runtime_library.sha256),
        "hiprtc_library_sha256": str(identity.hiprtc_library.sha256),
    }


def _finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload.pop("report_hash", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    report["report_hash"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return report


def _invariant(condition: bool, detail: str) -> None:
    if not condition:
        raise BenchmarkError("rtc_scaling_report_invariant_invalid", detail)


def _float_matches(actual: Any, expected: Any) -> bool:
    return math.isclose(
        float(actual), float(expected), rel_tol=1.0e-12, abs_tol=1.0e-15
    )


def _validate_sample_invariants(sample: Mapping[str, Any]) -> None:
    n = int(sample["row_count"])
    expected_work = _logical_work(n)
    for key, expected in expected_work.items():
        _invariant(sample[key] == expected, f"sample_{n}_{key}_mismatch")
    _invariant(
        int(sample["allocated_device_payload_bytes"])
        == _allocated_payload_bytes(n),
        f"sample_{n}_payload_mismatch",
    )
    _invariant(
        int(sample["allocated_device_payload_bytes"])
        == int(sample["resident_touched_bytes"]),
        f"sample_{n}_resident_payload_mismatch",
    )
    _invariant(
        int(sample["initial_h2d_bytes"]) == _initial_h2d_bytes(n),
        f"sample_{n}_h2d_mismatch",
    )
    _invariant(
        int(sample["outside_timed_region_d2h_bytes"]) == 16 * n,
        f"sample_{n}_d2h_mismatch",
    )
    k = int(sample["timed_batch_launch_count"])
    repeats = int(sample["timed_trial_count"])
    raw = list(sample["raw_trials"])
    _invariant(len(raw) == repeats, f"sample_{n}_raw_trial_count_mismatch")
    for index, trial in enumerate(raw):
        _invariant(
            int(trial["trial_index"]) == index,
            f"sample_{n}_trial_index_mismatch",
        )
        _invariant(
            _float_matches(
                trial["batch_elapsed_ms"], float(trial["per_launch_ms"]) * k
            ),
            f"sample_{n}_trial_ratio_mismatch",
        )
    per_launch = [float(trial["per_launch_ms"]) for trial in raw]
    batch_elapsed = [float(trial["batch_elapsed_ms"]) for trial in raw]
    median = float(statistics.median(per_launch))
    mean = float(statistics.fmean(per_launch))
    standard_deviation = float(statistics.stdev(per_launch))
    expected_statistics = {
        "median_batch_elapsed_ms": statistics.median(batch_elapsed),
        "median_per_launch_ms": median,
        "minimum_per_launch_ms": min(per_launch),
        "maximum_per_launch_ms": max(per_launch),
        "mean_per_launch_ms": mean,
        "standard_deviation_per_launch_ms": standard_deviation,
        "median_absolute_deviation_per_launch_ms": statistics.median(
            abs(value - median) for value in per_launch
        ),
        "coefficient_of_variation": standard_deviation / mean,
    }
    for key, expected in expected_statistics.items():
        _invariant(
            _float_matches(sample[key], expected),
            f"sample_{n}_{key}_mismatch",
        )
    _invariant(
        int(sample["double_batch_launch_count"]) == 2 * k,
        f"sample_{n}_double_batch_mismatch",
    )
    k_raw = [
        float(value)
        for value in sample["batch_length_stability_k_raw_batch_elapsed_ms"]
    ]
    double_raw = [
        float(value)
        for value in sample["batch_length_stability_2k_raw_batch_elapsed_ms"]
    ]
    k_per_launch = float(statistics.median(k_raw)) / k
    double_per_launch = float(statistics.median(double_raw)) / (2 * k)
    stability_delta = abs(double_per_launch - k_per_launch) / k_per_launch
    for key, expected in (
        ("batch_length_stability_k_per_launch_ms", k_per_launch),
        ("batch_length_stability_2k_per_launch_ms", double_per_launch),
        ("batch_length_stability_relative_delta", stability_delta),
    ):
        _invariant(
            _float_matches(sample[key], expected),
            f"sample_{n}_{key}_mismatch",
        )
    _invariant(
        list(sample["calibration_trials"])[-1]["raw_batch_elapsed_ms"]
        == list(sample["batch_length_stability_k_raw_batch_elapsed_ms"]),
        f"sample_{n}_calibration_binding_mismatch",
    )
    end_per_launch = float(sample["end_repeat_batch_elapsed_ms"]) / k
    _invariant(
        _float_matches(sample["end_repeat_per_launch_ms"], end_per_launch),
        f"sample_{n}_end_repeat_ratio_mismatch",
    )
    _invariant(
        _float_matches(
            sample["end_repeat_relative_drift"],
            abs(end_per_launch - median) / median,
        ),
        f"sample_{n}_end_repeat_drift_mismatch",
    )
    _invariant(
        int(sample["fit_trial_kernel_launch_count"]) == k * repeats,
        f"sample_{n}_fit_launch_count_mismatch",
    )
    calibration_launches = sum(
        int(item["launch_count"]) * len(item["raw_batch_elapsed_ms"])
        for item in sample["calibration_trials"]
    )
    expected_event_launches = (
        int(sample["pilot_launch_count"])
        + calibration_launches
        + 2 * k * len(double_raw)
        + k * repeats
        + k
    )
    _invariant(
        int(sample["event_timed_kernel_launch_count_total"])
        == expected_event_launches,
        f"sample_{n}_event_launch_count_mismatch",
    )
    correctness = sample["correctness"]
    expected_correctness = bool(
        correctness["finite"]
        and float(correctness["residual_max_abs_error"])
        <= float(correctness["absolute_tolerance"])
        and float(correctness["jvp_max_abs_error"])
        <= float(correctness["absolute_tolerance"])
        and float(correctness["residual_relative_l2_error"])
        <= float(correctness["relative_l2_tolerance"])
        and float(correctness["jvp_relative_l2_error"])
        <= float(correctness["relative_l2_tolerance"])
    )
    _invariant(
        bool(correctness["passed"]) is expected_correctness,
        f"sample_{n}_correctness_decision_mismatch",
    )


def _validate_report_invariants(report: Mapping[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator

        schema_path = (
            Path(__file__).resolve().parents[1]
            / "src/structural_analysis/schemas/rtc_kernel_scaling_report_v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema).iter_errors(dict(report)),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except Exception as exc:
        if isinstance(exc, BenchmarkError):
            raise
        raise BenchmarkError(
            "rtc_scaling_report_schema_unavailable",
            f"Could not validate report schema: {type(exc).__name__}.",
        ) from exc
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise BenchmarkError(
            "rtc_scaling_report_schema_invalid", f"{path}: {error.message}"
        )
    expected = dict(report)
    actual_hash = str(expected.pop("report_hash"))
    encoded = json.dumps(
        expected,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected_hash = "sha256:" + hashlib.sha256(encoded).hexdigest()
    _invariant(actual_hash == expected_hash, "report_hash_mismatch")
    _invariant(bool(_SHA256_PATTERN.fullmatch(actual_hash)), "report_hash_invalid")
    _invariant(
        dict(report["harness_identity"]) == _harness_identity(),
        "harness_identity_current_bytes_mismatch",
    )

    configuration = report["configuration"]
    sizes = tuple(int(value) for value in configuration["sizes"])
    order = tuple(int(value) for value in configuration["measurement_order"])
    _invariant(
        order == _balanced_measurement_order(sizes),
        "measurement_order_policy_mismatch",
    )
    device = report["device"]
    if isinstance(device, Mapping):
        ordinal = int(report["device_ordinal"])
        detected = list(report["detected_architectures"])
        _invariant(
            ordinal < len(detected)
            and report["architecture"] == detected[ordinal],
            "selected_architecture_detection_mismatch",
        )
        kernel_identity = report["kernel_identity"]
        if isinstance(kernel_identity, Mapping):
            _invariant(
                kernel_identity["architecture"] == report["architecture"],
                "kernel_architecture_mismatch",
            )
        expected_profile_match = bool(
            report["architecture"] == EXPECTED_PROFILE_ARCHITECTURE
            and EXPECTED_PROFILE_DEVICE_NAME_TOKEN.lower()
            in str(device["name"]).lower()
        )
        _invariant(
            bool(device["hardware_profile_matched"]) is expected_profile_match,
            "hardware_profile_match_mismatch",
        )
    samples = list(report["samples"])
    if samples:
        _invariant(
            [int(sample["row_count"]) for sample in samples] == list(sizes),
            "sample_sizes_mismatch",
        )
        for sample in samples:
            _validate_sample_invariants(sample)
        fit_samples = [
            sample
            for sample in samples
            if int(configuration["fit_min_n"])
            <= int(sample["row_count"])
            <= int(configuration["fit_max_n"])
        ]
        expected_fit = _fit_log_log(
            fit_samples,
            bootstrap_replicates=int(configuration["bootstrap_replicates"]),
            bootstrap_seed=int(configuration["bootstrap_seed"]),
        )
        observed_fit = report["fit"]
        _invariant(isinstance(observed_fit, Mapping), "fit_missing")
        for key, expected_value in expected_fit.items():
            observed_value = observed_fit[key]
            if isinstance(expected_value, float):
                matches = _float_matches(observed_value, expected_value)
            else:
                matches = observed_value == expected_value
            _invariant(matches, f"fit_{key}_mismatch")
        profile_matched = bool(
            isinstance(device, Mapping) and device["hardware_profile_matched"]
        )
        expected_acceptance = _acceptance(
            expected_fit,
            samples=fit_samples,
            slope_lower=float(configuration["slope_lower_inclusive"]),
            slope_upper=float(configuration["slope_upper_inclusive"]),
            min_r2=float(configuration["minimum_ols_r2"]),
            max_cv=float(configuration["maximum_coefficient_of_variation"]),
            max_batch_stability_delta=float(
                configuration["maximum_batch_length_stability_relative_delta"]
            ),
            max_end_repeat_drift=float(
                configuration["maximum_end_repeat_relative_drift"]
            ),
            hardware_profile_matched=profile_matched,
        )
    else:
        _invariant(report["fit"] is None, "fit_without_samples")
        expected_acceptance = _acceptance(
            None,
            slope_lower=float(configuration["slope_lower_inclusive"]),
            slope_upper=float(configuration["slope_upper_inclusive"]),
            min_r2=float(configuration["minimum_ols_r2"]),
            max_cv=float(configuration["maximum_coefficient_of_variation"]),
            max_batch_stability_delta=float(
                configuration["maximum_batch_length_stability_relative_delta"]
            ),
            max_end_repeat_drift=float(
                configuration["maximum_end_repeat_relative_drift"]
            ),
        )
    _invariant(
        dict(report["acceptance"]) == expected_acceptance,
        "acceptance_recalculation_mismatch",
    )


def _emit(report: dict[str, Any], out: Path | None) -> None:
    finalized = _finalize_report(report)
    _validate_report_invariants(finalized)
    rendered = json.dumps(
        finalized,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    if out is None:
        print(rendered)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")


def _worker_main(args: argparse.Namespace, sizes: tuple[int, ...]) -> int:
    enumerator = _resolve_enumerator(args.agent_enumerator)
    architectures = _detect_architectures(enumerator)
    architecture = (
        architectures[args.device_ordinal]
        if args.device_ordinal < len(architectures)
        else None
    )
    report = _base_report(
        args=args,
        sizes=sizes,
        architecture=architecture,
        detected_architectures=architectures,
        enumerator=enumerator,
    )
    if report["environment"]["serialization_overrides_present_in_worker"]:
        report["reason"] = {
            "code": "rtc_scaling_serialized_environment",
            "detail": "A launch-serialization override remained in the worker.",
        }
        _emit(report, args.out)
        return 2
    if architecture is None:
        report["reason"] = {
            "code": "rtc_scaling_real_gfx_unavailable",
            "detail": (
                "rocm_agent_enumerator did not report a real gfx target for "
                "the requested ordinal; no CPU fallback or synthetic timing ran."
            ),
        }
        _emit(report, args.out)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from structural_analysis.engine_v2.backends.hip.native import (
            LoadedHipRuntime,
            load_hip_native_runtime,
            probe_hip_capability,
        )
        from structural_analysis.engine_v2.rtc_backend.rtc import (
            HipRtcCsrKernel,
            compile_hip_rtc_csr_kernel,
        )

        loaded = load_hip_native_runtime(args.runtime_library)
        if type(loaded) is not LoadedHipRuntime:
            raise BenchmarkError(
                "rtc_scaling_native_runtime_type_invalid",
                "Native evidence requires the exact LoadedHipRuntime owner.",
            )
        capability = probe_hip_capability(
            runtime=loaded, device_ordinal=args.device_ordinal
        )
        if capability.status != "ready":
            report["reason"] = {
                "code": capability.status_code,
                "detail": capability.message,
            }
            _emit(report, args.out)
            return 2
        runtime = _HipBenchmarkRuntime(loaded)
        runtime.set_device(args.device_ordinal)
        free_bytes, total_bytes = runtime.mem_info()
        hardware_profile_matched = bool(
            architecture == EXPECTED_PROFILE_ARCHITECTURE
            and capability.device.name is not None
            and EXPECTED_PROFILE_DEVICE_NAME_TOKEN.lower()
            in capability.device.name.lower()
        )
        report["device"] = {
            "name": capability.device.name,
            "free_memory_bytes_before": free_bytes,
            "total_memory_bytes": total_bytes,
            "runtime_version_raw": capability.versions.runtime,
            "driver_version_raw": capability.versions.driver,
            "capability_receipt_hash": capability.receipt_hash,
            "hardware_profile_matched": hardware_profile_matched,
        }
        largest_payload = _allocated_payload_bytes(sizes[-1])
        if free_bytes < args.minimum_free_device_bytes or largest_payload > int(
            free_bytes * args.max_payload_fraction
        ):
            report["reason"] = {
                "code": "rtc_scaling_device_memory_preflight_failed",
                "detail": (
                    "The predeclared sizes do not fit the configured free-memory "
                    "envelope; sizes were not automatically reduced."
                ),
            }
            _emit(report, args.out)
            return 2

        kernel = compile_hip_rtc_csr_kernel(
            loaded,
            architecture,
            hiprtc_library=args.hiprtc_library,
        )
        if type(kernel) is not HipRtcCsrKernel:
            raise BenchmarkError(
                "rtc_scaling_native_kernel_type_invalid",
                "Native evidence requires the exact HipRtcCsrKernel owner.",
            )
        report["kernel_identity"] = _kernel_identity_payload(kernel.identity)
        stream: ctypes.c_void_p | None = None
        primary: BaseException | None = None
        try:
            stream = runtime.create_stream()
            samples = [
                _measure_one_size(
                    row_count=row_count,
                    runtime=runtime,
                    kernel=kernel,
                    stream=stream,
                    warmup_launches=args.warmup_launches,
                    pilot_launches=args.pilot_launches,
                    target_batch_ms=args.target_batch_ms,
                    max_batch_launches=args.max_batch_launches,
                    stability_repeats=args.stability_repeats,
                    repeats=args.repeats,
                )
                for row_count in _balanced_measurement_order(sizes)
            ]
            samples.sort(key=lambda sample: int(sample["row_count"]))
            fit_samples = [
                sample
                for sample in samples
                if args.fit_min_n <= sample["row_count"] <= args.fit_max_n
            ]
            fit = _fit_log_log(
                fit_samples,
                bootstrap_replicates=args.bootstrap_replicates,
                bootstrap_seed=args.bootstrap_seed,
            )
            acceptance = _acceptance(
                fit,
                samples=fit_samples,
                slope_lower=args.slope_lower,
                slope_upper=args.slope_upper,
                min_r2=args.min_r2,
                max_cv=args.max_cv,
                max_batch_stability_delta=args.max_batch_stability_delta,
                max_end_repeat_drift=args.max_end_repeat_drift,
                hardware_profile_matched=hardware_profile_matched,
            )
            outcome = str(acceptance["outcome"])
            if outcome == "accepted":
                reason = None
            elif not acceptance["correctness_passed"]:
                reason = {
                    "code": "rtc_scaling_correctness_contract_failed",
                    "detail": (
                        "An outside-timed-region fused residual/JVP finiteness "
                        "or numerical parity check failed."
                    ),
                }
            elif not acceptance["timed_region_clean"]:
                reason = {
                    "code": "rtc_scaling_timed_region_contract_failed",
                    "detail": (
                        "A timed region contained a transfer, allocation, or "
                        "fallback operation."
                    ),
                }
            elif outcome == "inconclusive":
                reason = {
                    "code": "rtc_scaling_measurement_quality_inconclusive",
                    "detail": (
                        "Cache/occupancy coverage, batch duration/stability, "
                        "CV, drift, or bootstrap confidence was insufficient."
                    ),
                }
            else:
                reason = {
                    "code": "rtc_scaling_slope_gate_rejected",
                    "detail": (
                        "A clean conclusive kernel-only fit failed the OLS/"
                        "Theil-Sen slope or OLS R2 acceptance target."
                    ),
                }
            report.update(
                status=outcome,
                decision=outcome,
                actual_backend="hip",
                reason=reason,
                samples=samples,
                fit=fit,
                acceptance=acceptance,
            )
            report["claims"].update(
                kernel_scope_timing_measured=True,
                kernel_scope_initial_linear_scaling_accepted=bool(
                    acceptance["accepted"]
                ),
            )
        except BaseException as exc:
            primary = exc
        cleanup_errors: list[str] = []
        if stream is not None:
            try:
                runtime.destroy_stream(stream)
            except Exception as exc:  # pragma: no cover - hardware failure
                cleanup_errors.append(f"stream:{type(exc).__name__}")
        try:
            kernel.close()
        except Exception as exc:  # pragma: no cover - hardware failure
            cleanup_errors.append(f"kernel:{type(exc).__name__}")
        if cleanup_errors:
            raise BenchmarkError(
                "rtc_scaling_cleanup_failed", ",".join(cleanup_errors)
            ) from primary
        if primary is not None:
            raise primary
    except Exception as exc:
        code = getattr(exc, "code", "rtc_scaling_unexpected_failure")
        detail = getattr(exc, "detail", None) or getattr(exc, "message", None)
        if not detail:
            detail = f"{type(exc).__name__} during native HIPRTC benchmark."
        report.update(status="error", decision="not_evaluated", actual_backend=None)
        report["reason"] = {"code": str(code), "detail": str(detail)[:1024]}
        report["samples"] = []
        report["fit"] = None
        report["acceptance"] = _acceptance(
            None,
            slope_lower=args.slope_lower,
            slope_upper=args.slope_upper,
            min_r2=args.min_r2,
            max_cv=args.max_cv,
            max_batch_stability_delta=args.max_batch_stability_delta,
            max_end_repeat_drift=args.max_end_repeat_drift,
        )
        report["claims"]["kernel_scope_timing_measured"] = False
        report["claims"][
            "kernel_scope_initial_linear_scaling_accepted"
        ] = False
        _emit(report, args.out)
        return 1

    _emit(report, args.out)
    return 0 if report["status"] == "accepted" else 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _worker_needs_reexec(os.environ):
        return _reexec_clean_worker(arguments)
    args = _parser().parse_args(arguments)
    try:
        sizes = _parse_sizes(args.sizes)
        _validate_configuration(args, sizes)
    except BenchmarkError as exc:
        print(f"{exc.code}: {exc.detail}", file=sys.stderr)
        return 2
    return _worker_main(args, sizes)


if __name__ == "__main__":
    raise SystemExit(main())
