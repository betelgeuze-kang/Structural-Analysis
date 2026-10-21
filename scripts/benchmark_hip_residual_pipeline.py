#!/usr/bin/env python3
"""Compare one generated fixed-linear-operator sequence, not an RC solve.

The v1 host-roundtrip baseline and the new resident path perform exactly
u[k+1] = u[k] - omega*(A*u[k]-f), then return u[S] and A*u[S]-f.
An optimized preassembled-CSR OpenMP implementation is the CPU comparator.
"""

from __future__ import annotations

import argparse
import ctypes as ct
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

if __name__ == "__main__":
    for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[_key] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "fixed_operator_v1", ROOT / "scripts/benchmark_hip_residual_performance.py"
)
BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(BASE)
CLAIM = (
    "Generated fixed-linear-operator explicit state-update sequence only; no "
    "nonlinear material/RC solver, convergence, physical, public GPU backend or "
    "release authority. All methods compute the same sequence and final state/residual. "
    "The CPU uses preassembled CSR; GPU uses existing frame-scatter/CSR kernels. "
    "Operator/output reuse existed in v1. The new change keeps intermediate states "
    "and residuals on GPU between updates. Compare only this sequence's host-roundtrip "
    "baseline, not the different v1 independent-residual benchmark."
)


def reference(case, steps, omega):
    state = case["arrays"]["states"].copy()
    for _ in range(steps):
        residual = (case["operator"] @ state.T).T - case["arrays"]["external"]
        state -= omega * residual
    residual = (case["operator"] @ state.T).T - case["arrays"]["external"]
    return np.ascontiguousarray(state), np.ascontiguousarray(residual)


def check_outputs(state, residual, expected):
    errors = []
    for actual, target in zip((state, residual), expected, strict=True):
        if not np.allclose(actual, target, rtol=1e-11, atol=1e-12):
            raise ValueError("fixed-operator sequence FP64 parity failed")
        errors.append(float(np.max(np.abs(actual - target))))
    return errors


class CpuOperator:
    def __init__(self, library, case):
        self.lib = ct.CDLL(str(library))
        p = ct.c_void_p
        self.lib.structural_cpu_fixed_operator_create_v1.argtypes = [
            ct.c_size_t,
            ct.c_size_t,
            p,
            p,
            p,
            p,
            ct.POINTER(p),
        ]
        self.lib.structural_cpu_fixed_operator_create_v1.restype = ct.c_int
        self.lib.structural_cpu_fixed_residual_sequence_v1.argtypes = [
            p,
            p,
            ct.c_size_t,
            ct.c_int,
            ct.c_int,
            ct.c_double,
            p,
            p,
            ct.POINTER(ct.c_int),
        ]
        self.lib.structural_cpu_fixed_residual_sequence_v1.restype = ct.c_int
        self.lib.structural_cpu_fixed_operator_destroy_v1.argtypes = [p]
        self.lib.structural_cpu_fixed_operator_destroy_v1.restype = ct.c_int
        self.handle = p()
        operator = case["operator"]
        row = operator.indptr.astype(np.int64)
        column = operator.indices.astype(np.int64)
        start = time.perf_counter()
        code = self.lib.structural_cpu_fixed_operator_create_v1(
            case["dimension"],
            operator.nnz,
            row.ctypes.data,
            column.ctypes.data,
            operator.data.ctypes.data,
            case["arrays"]["external"].ctypes.data,
            ct.byref(self.handle),
        )
        self.setup_ms = (time.perf_counter() - start) * 1000
        if code:
            raise ValueError(f"CPU operator admission failed: {code}")

    def evaluate(self, case, steps, omega, workers, state, residual):
        observed = ct.c_int()
        start = time.perf_counter()
        code = self.lib.structural_cpu_fixed_residual_sequence_v1(
            self.handle,
            case["arrays"]["states"].ctypes.data,
            case["batch"],
            steps,
            workers,
            omega,
            state.ctypes.data,
            residual.ctypes.data,
            ct.byref(observed),
        )
        wall = (time.perf_counter() - start) * 1000
        if code:
            raise ValueError(f"CPU fixed-operator sequence rejected: {code}")
        return {"wall_ms": wall, "observed_workers": observed.value}

    def close(self):
        if self.handle:
            code = self.lib.structural_cpu_fixed_operator_destroy_v1(self.handle)
            self.handle = ct.c_void_p()
            if code:
                raise ValueError("CPU operator destroy failed")


class HipSequence(BASE.HipResidual):
    def __init__(self, library):
        super().__init__(library)
        p = ct.c_void_p
        self.lib.structural_hip_fixed_residual_sequence_v1.argtypes = [
            p,
            p,
            ct.c_longlong,
            ct.c_int,
            ct.c_double,
            p,
            p,
            p,
        ]
        self.lib.structural_hip_fixed_residual_sequence_v1.restype = ct.c_int

    def resident(self, handle, case, steps, omega, state, residual):
        phases = np.empty(6, dtype=np.float64)
        start = time.perf_counter()
        code = self.lib.structural_hip_fixed_residual_sequence_v1(
            handle,
            case["arrays"]["states"].ctypes.data,
            case["batch"],
            steps,
            omega,
            state.ctypes.data,
            residual.ctypes.data,
            phases.ctypes.data,
        )
        wall = (time.perf_counter() - start) * 1000
        self.checked(code)
        return {
            "wall_ms": wall,
            "phases_ms": dict(zip(BASE.PHASE_NAMES, phases.tolist())),
        }

    def host_roundtrip(self, handle, case, steps, omega, state, residual, scratch):
        live = {**case, "arrays": {**case["arrays"], "states": state}}
        phase_rows = []
        start = time.perf_counter()
        np.copyto(state, case["arrays"]["states"])
        for _ in range(steps):
            phase, _ = self.evaluate(handle, live, residual)
            phase_rows.append(phase)
            np.multiply(residual, omega, out=scratch)
            np.subtract(state, scratch, out=state)
        phase, _ = self.evaluate(handle, live, residual)
        phase_rows.append(phase)
        wall = (time.perf_counter() - start) * 1000
        summed = np.sum(phase_rows, axis=0)
        return {
            "wall_ms": wall,
            "phases_ms": dict(zip(BASE.PHASE_NAMES, summed.tolist())),
        }


def validate_scope(dimensions, batches, steps, workers):
    if any(type(n) is not int or n < 12 or n > 196608 or n % 6 for n in dimensions):
        raise ValueError("dimensions must be multiples of six in [12,196608]")
    if any(type(b) is not int or b < 1 or b > 64 for b in batches):
        raise ValueError("batches must be in [1,64]")
    if any(type(s) is not int or s < 1 or s > 128 for s in steps):
        raise ValueError("steps must be in [1,128]")
    if any(type(w) is not int or w < 1 or w > 12 for w in workers) or 1 not in workers:
        raise ValueError("CPU workers must include 1 and lie in [1,12]")
    if (
        not dimensions
        or not batches
        or not steps
        or len(dimensions) * len(batches) * len(steps) > 24
    ):
        raise ValueError("require a nonempty sweep of at most 24 sequence cases")
    if any(
        len(set(values)) != len(values)
        for values in (dimensions, batches, steps, workers)
    ):
        raise ValueError("sweep entries must be unique")


def compare_case(
    cpu_library,
    gpu,
    dimension,
    batch,
    steps,
    omega,
    workers,
    warmups,
    samples,
    correctness,
):
    start = time.perf_counter()
    case = BASE.generated_case(dimension, batch)
    generation_ms = (time.perf_counter() - start) * 1000
    if not np.all(np.isfinite(case["arrays"]["states"])):
        raise ValueError("sequence input states must be finite")
    expected = reference(case, steps, omega)
    cpu = CpuOperator(cpu_library, case)
    handle = None
    state, residual, scratch = [np.empty_like(expected[0]) for _ in range(3)]
    try:
        handle, gpu_setup = gpu.create(case)
        methods = {
            f"cpu_openmp_{w}": (
                lambda w=w: cpu.evaluate(case, steps, omega, w, state, residual)
            )
            for w in workers
        }
        methods["gpu_host_roundtrip"] = lambda: gpu.host_roundtrip(
            handle, case, steps, omega, state, residual, scratch
        )
        methods["gpu_resident_sequence"] = lambda: gpu.resident(
            handle, case, steps, omega, state, residual
        )
        rows = {name: [] for name in methods}
        maxima = {name: [0.0, 0.0] for name in methods}
        warm_count = 0 if correctness else warmups
        sample_count = 1 if correctness else samples
        for ordinal in range(warm_count + sample_count):
            names = list(methods)
            shift = ordinal % len(names)
            for name in names[shift:] + names[:shift]:
                timing = methods[name]()
                errors = check_outputs(state, residual, expected)
                maxima[name] = [
                    max(a, b) for a, b in zip(maxima[name], errors, strict=True)
                ]
                if ordinal >= warm_count:
                    rows[name].append(timing)
        phases = {}
        summary = {}
        for name, observations in rows.items():
            item = {
                "wall_ms": BASE.summarize([row["wall_ms"] for row in observations]),
                "parity": {
                    "pass": True,
                    "maximum_state_absolute_error": maxima[name][0],
                    "maximum_residual_absolute_error": maxima[name][1],
                },
            }
            if name.startswith("cpu"):
                item["observed_workers"] = [
                    row["observed_workers"] for row in observations
                ]
            else:
                phases[name] = {
                    key: BASE.summarize([row["phases_ms"][key] for row in observations])
                    for key in BASE.PHASE_NAMES
                }
                item["phases_ms"] = phases[name]
            summary[name] = item
        best = min(
            (f"cpu_openmp_{w}" for w in workers),
            key=lambda name: summary[name]["wall_ms"]["median"],
        )
        result = {
            "dimension": dimension,
            "batch": batch,
            "steps": steps,
            "omega": omega,
            "input_hash": case["input_hash"],
            "sequence_contract_hash": BASE.digest(
                json.dumps(
                    {
                        "input_hash": case["input_hash"],
                        "steps": steps,
                        "omega": omega,
                        "update": "u[k+1]=u[k]-omega*(A*u[k]-f);final=(u[S],A*u[S]-f)",
                    },
                    sort_keys=True,
                ).encode()
            ),
            "input_bytes": case["input_bytes"],
            "input_generation_and_cpu_csr_preassembly_ms": generation_ms,
            "cpu_operator_copy_setup_ms": cpu.setup_ms,
            "gpu_operator_setup_ms": gpu_setup,
            "methods": summary,
            "expected_final_state_hash": BASE.digest(expected[0].tobytes()),
            "expected_final_residual_hash": BASE.digest(expected[1].tobytes()),
            "sequence_residual_evaluations": steps + 1,
            "transfer_contract": {
                "copy_counts_are_source_contract_not_profiler_observations": True,
                "host_roundtrip_h2d_calls": steps + 1,
                "host_roundtrip_d2h_calls": steps + 1,
                "resident_h2d_calls": 1,
                "resident_d2h_calls": 2,
                "host_roundtrip_transfer_bytes": 2
                * (steps + 1)
                * dimension
                * batch
                * 8,
                "resident_transfer_bytes": 3 * dimension * batch * 8,
                "expected_host_roundtrip_explicit_kernel_launches": 2 * (steps + 1),
                "expected_resident_explicit_kernel_launches": 3 * steps + 2,
                "frame_output_zero_operations": steps + 1,
            },
        }
        if not correctness:
            resident = summary["gpu_resident_sequence"]["wall_ms"]["median"]
            result["resident_speedup_vs_same_sequence_host_roundtrip"] = (
                summary["gpu_host_roundtrip"]["wall_ms"]["median"] / resident
            )
            result["best_cpu_method"] = best
            result["best_cpu_time_over_resident_gpu_time"] = (
                summary[best]["wall_ms"]["median"] / resident
            )
        return result
    finally:
        cpu.close()
        if handle:
            gpu.checked(gpu.lib.mgt_hip_full_residual_destroy(handle))


def build(out, reuse):
    sources = [
        ROOT / path
        for path in (
            "native/hip/hip_residual_pipeline.cpp",
            "native/hip/hip_residual_timing.cpp",
            "implementation/phase1/hip_full_residual_ffi.cpp",
            "native/hip/residual_pipeline_cpu.cpp",
        )
    ]
    hashes = {
        str(path.relative_to(ROOT)): BASE.digest(path.read_bytes()) for path in sources
    }
    gpu, cpu = out / "libfixed_sequence_hip.so", out / "libfixed_sequence_cpu.so"
    manifest_path = out / "build-manifest.json"
    if reuse:
        manifest = json.loads(manifest_path.read_text())
        if manifest["source_files"] != hashes or manifest["binaries"] != {
            path.name: BASE.digest(path.read_bytes()) for path in (gpu, cpu)
        }:
            raise ValueError("pipeline source/binary build binding changed")
        return gpu, cpu, manifest
    device = (
        ROOT
        / "implementation/phase1/third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
    )
    commands = [
        [
            "/opt/rocm/bin/hipcc",
            "-O3",
            "-std=c++17",
            "-ffp-contract=off",
            "--offload-arch=gfx1030",
            f"--rocm-device-lib-path={device}",
            "-fPIC",
            "-shared",
            str(sources[0]),
            "-o",
            str(gpu),
        ],
        [
            "g++",
            "-O3",
            "-std=c++20",
            "-ffp-contract=off",
            "-fopenmp",
            "-fPIC",
            "-shared",
            str(sources[3]),
            "-o",
            str(cpu),
        ],
    ]
    builds = []
    for index, command in enumerate(commands):
        start = time.perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, timeout=240)
        (out / f"build-{index}.log").write_text(process.stdout + process.stderr)
        builds.append(
            {
                "command": command,
                "returncode": process.returncode,
                "seconds": time.perf_counter() - start,
            }
        )
        if process.returncode:
            (out / "failed-build.json").write_text(json.dumps(builds, indent=2))
            raise ValueError(f"sequence native build {index} failed")
    manifest = {
        "source_files": hashes,
        "builds": builds,
        "binaries": {path.name: BASE.digest(path.read_bytes()) for path in (gpu, cpu)},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return gpu, cpu, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--reuse-library", action="store_true")
    parser.add_argument("--correctness-only", action="store_true")
    parser.add_argument(
        "--dimensions", nargs="+", type=int, default=[1536, 12288, 49152]
    )
    parser.add_argument("--batches", nargs="+", type=int, default=[1, 8, 32])
    parser.add_argument("--steps", nargs="+", type=int, default=[8, 32])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4, 8, 12])
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--omega", type=float, default=0.05)
    args = parser.parse_args(argv)
    validate_scope(args.dimensions, args.batches, args.steps, args.workers)
    if (
        not 3 <= args.samples <= 15
        or not 0 <= args.warmups <= 5
        or not 0 < args.omega <= 1
    ):
        parser.error("bounded samples/warmups/omega exceeded")
    args.out.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": "structural-fixed-operator-resident-sequence.v1",
        "claim_boundary": CLAIM,
        "driver_hash": BASE.digest(Path(__file__).read_bytes()),
        "base_driver_hash": BASE.digest(
            (ROOT / "scripts/benchmark_hip_residual_performance.py").read_bytes()
        ),
        "cpu_threads": {
            key: os.environ.get(key)
            for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "cases": [],
        "status": "started",
        "timing_contract": "Preallocated outputs for CPU/GPU/host-roundtrip. Input generation, CPU CSR preassembly, CPU plan copy/GPU operator setup outside steady timing and separately reported. Python wall includes FFI and GPU event creation/destruction; device phases exclude event creation/destruction. Final state and residual copies are included. No pinned/async changes. Warmup and parity/hash calculations outside timing; method order rotates per sample.",
    }
    path = args.out / (
        "correctness.json" if args.correctness_only else "performance.json"
    )
    try:
        gpu_library, cpu_library, receipt["build"] = build(args.out, args.reuse_library)
        if args.build_only:
            receipt["status"] = "compiled_not_executed"
        else:
            gpu = HipSequence(gpu_library)
            receipt["device"] = gpu.device()
            if receipt["device"]["architecture"].split(":")[0] != "gfx1030":
                raise ValueError("compiled/actual architecture mismatch")
            receipt["device_properties_hash"] = BASE.digest(
                json.dumps(receipt["device"], sort_keys=True).encode()
            )
            for n in args.dimensions:
                for b in args.batches:
                    for s in args.steps:
                        receipt["cases"].append(
                            compare_case(
                                cpu_library,
                                gpu,
                                n,
                                b,
                                s,
                                args.omega,
                                args.workers,
                                args.warmups,
                                args.samples,
                                args.correctness_only,
                            )
                        )
                        path.write_text(json.dumps(receipt, indent=2))
            receipt["status"] = (
                "correctness_passed_no_steady_measurement"
                if args.correctness_only
                else "passed"
            )
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    path.write_text(json.dumps(receipt, indent=2))
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "cases": len(receipt["cases"]),
                "receipt": str(path),
                "error": receipt.get("error"),
            }
        )
    )
    return int(receipt["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
