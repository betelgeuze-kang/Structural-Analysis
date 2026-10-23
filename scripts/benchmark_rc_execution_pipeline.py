#!/usr/bin/env python3
"""Source-bound generated public RC API timing and a separate optional diagnostic profile.

The driver never weakens the public solver or its validation gates. Timings include
analyze+validate and exclude input preparation, fingerprinting and report writes.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import copy
import cProfile
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import platform
import pstats
import resource
import signal
import statistics
import subprocess
import sys
import time


DENSE = "numpy_linalg_solve_dense"
SPARSE = "scipy_sparse_spsolve_cpu"
CASES = {"1x2": (1, 2), "2x2": (2, 2), "4x2": (4, 2), "1x16": (1, 16)}
CATEGORIES = ("material", "assembly", "solve", "canonical_json", "schema", "proof_state", "other")
NORMALIZATION = ["result_hash", "configuration.material_execution_backend", "configuration.matrix_backend"]


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def file_identity(path):
    path = Path(path).resolve(strict=True)
    name = path.name
    if name != ".env.example" and (name == ".env" or name.startswith(".env.") or name.endswith(".env") or ".env." in name):
        raise RuntimeError("environment files are outside benchmark source custody")
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def normalize_result(value):
    normalized = copy.deepcopy(value)
    normalized.pop("result_hash", None)
    configuration = normalized.get("configuration", {})
    configuration.pop("material_execution_backend", None)
    configuration.pop("matrix_backend", None)
    return normalized


def fingerprint_result(result):
    numerical = normalize_result(result.to_dict())
    checkpoint = result.checkpoint_artifact()
    return {
        "numerical_sha256": sha(canonical_bytes(numerical)),
        "checkpoint_sha256": sha(checkpoint),
    }, numerical, checkpoint


def execution_configuration(result, requested_matrix_backend):
    configuration = copy.deepcopy(result.to_dict().get("configuration", {}))
    actual = configuration.get("matrix_backend")
    accepted = {DENSE, "numpy_dense_ndarray"} if requested_matrix_backend == DENSE else {SPARSE}
    if actual not in accepted:
        raise RuntimeError("returned matrix backend differs from the requested execution; no fallback")
    return configuration


def loaded_project_sources(source_root, modules=None):
    expected = (Path(source_root) / "src" / "structural_analysis").resolve(strict=True)
    sources = {}
    for name, module in (sys.modules if modules is None else modules).copy().items():
        if name != "structural_analysis" and not name.startswith("structural_analysis."):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            paths = list(getattr(module, "__path__", []))
            if not paths or any(not Path(path).resolve().is_relative_to(expected) for path in paths):
                raise RuntimeError(f"project module has no verified source origin: {name}")
            continue
        path = Path(origin).resolve(strict=True)
        if not path.is_relative_to(expected):
            raise RuntimeError(f"project import came from another source root: {name}: {path}")
        sources[str(path)] = file_identity(path)
    return sources


def verify_unchanged(before, after):
    for path, identity in before.items():
        if path not in after or after[path]["sha256"] != identity["sha256"]:
            raise RuntimeError(f"source changed during measurement: {path}")


def profile_category(filename, function):
    """A function's exclusive self time belongs to exactly one bucket; no caller inference."""
    path = filename.replace("\\", "/").lower()
    name = function.lower()
    if "jsonschema" in path or "/schema/" in path or path.endswith("/schema.py") or path.endswith("_schema.py") or "schema_validation" in name:
        return "schema"
    if any(token in name for token in ("canonical", "sha256", "hexdigest", "json", "_digest")) or "/json/" in path or "_canonical" in path:
        return "canonical_json"
    if any(token in name for token in ("checkpoint", "proof", "replay", "lineage", "binding")) or "/contracts/state" in path:
        return "proof_state"
    if "/materials/" in path:
        return "material"
    if "/assembly/" in path or any(token in name for token in ("assemble", "_assembly", "global_tangent")):
        return "assembly"
    if "/solvers/" in path or "/linalg/" in path or name in ("spsolve", "solve", "splu"):
        return "solve"
    return "other"


def summarize_profile(stats):
    groups = {category: 0.0 for category in CATEGORIES}
    functions = []
    for (filename, line, function), (primitive, calls, self_time, _inclusive, _callers) in stats.stats.items():
        category = profile_category(filename, function)
        groups[category] += self_time
        functions.append({"file": filename, "line": line, "function": function,
                          "primitive_calls": primitive, "calls": calls,
                          "self_seconds": self_time, "category": category})
    summed = sum(groups.values())
    if not math.isclose(summed, stats.total_tt, rel_tol=1e-10, abs_tol=1e-10):
        raise RuntimeError("exclusive profile categories do not sum to total self time")
    functions.sort(key=lambda row: row["self_seconds"], reverse=True)
    return {"total_self_seconds": stats.total_tt, "category_self_seconds": groups,
            "category_self_seconds_sum": summed, "functions": functions,
            "aggregation": "exclusive function self time only; inclusive times are never summed; unclassified/C leaf work remains other"}


class CaseBudgetExceeded(RuntimeError):
    pass


class CaseBudget:
    def __init__(self, seconds):
        self.deadline = time.monotonic() + seconds

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CaseBudgetExceeded("case elapsed budget exceeded; no automatic retry")
        return remaining

    @contextmanager
    def api_call(self):
        remaining = self.remaining()
        if not hasattr(signal, "setitimer"):
            raise RuntimeError("this driver requires a POSIX interval timer for its cooperative API budget")
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if previous_timer != (0.0, 0.0):
            raise RuntimeError("refuse to replace an already active process interval timer")
        previous_handler = signal.getsignal(signal.SIGALRM)

        def expired(_signum, _frame):
            raise CaseBudgetExceeded("case elapsed budget interrupted the API; no automatic retry")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)


class OwnedReport:
    """Create exclusively, then atomically update only this process's new report."""
    def __init__(self, path):
        if Path(path).is_symlink():
            raise FileExistsError("refuse an existing report symlink")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x") as stream:
            stream.write("{}\n")
        self.owner = self._identity()
        self.sequence = 0

    def _identity(self):
        info = self.path.lstat()
        if self.path.is_symlink():
            raise RuntimeError("report path was replaced by a symlink")
        return info.st_dev, info.st_ino

    def save(self, report):
        if self._identity() != self.owner:
            raise RuntimeError("report path was replaced by another writer")
        self.sequence += 1
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{self.sequence}.tmp")
        created = False
        try:
            with temporary.open("x") as stream:
                created = True
                json.dump(report, stream, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, self.path)
            self.owner = self._identity()
        finally:
            if created and temporary.exists():
                temporary.unlink()

    def sidecar(self, case_id, suffix, data):
        path = self.path.with_name(f"{self.path.name}.{case_id}.{suffix}")
        with path.open("xb") as stream:
            stream.write(data)
        return file_identity(path)


def peak_rss():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"raw": raw, "raw_unit": "bytes" if sys.platform == "darwin" else "KiB",
            "bytes": raw if sys.platform == "darwin" else raw * 1024,
            "scope": "process lifetime peak includes imports, inputs, previous cases and any separate profile; not isolated solver working memory"}


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=["1x2"])
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--elapsed-budget-seconds", type=float, default=300.0)
    parser.add_argument("--matrix-backend", choices=(DENSE, SPARSE), default=DENSE)
    parser.add_argument("--steel-library", type=Path)
    parser.add_argument("--steel-workers", type=int, default=1)
    parser.add_argument("--prepared", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args(argv)
    if not 3 <= args.repetitions <= 20 or len(set(args.cases)) != len(args.cases):
        parser.error("repetitions must be 3..20 and cases must be unique")
    if not math.isfinite(args.elapsed_budget_seconds) or not 0 < args.elapsed_budget_seconds <= 3600:
        parser.error("elapsed budget must be finite and in (0,3600] seconds per case")
    if args.steel_workers < 1 or args.steel_workers > min(len(os.sched_getaffinity(0)), 256):
        parser.error("steel-workers must fit observed CPU affinity and be in 1..256")
    if not args.steel_library and (args.prepared or args.steel_workers != 1):
        parser.error("prepared/steel-workers requires an explicit steel library")
    return args


def load_runtime(source_root, matrix_backend):
    root = Path(source_root).resolve(strict=True)
    if not (root / "src/structural_analysis/__init__.py").is_file():
        raise RuntimeError("source-root must contain src/structural_analysis/__init__.py")
    loaded_project_sources(root)  # Reject a wrong preloaded editable import before changing paths.
    sys.path.insert(0, str(root / "src"))
    importlib.invalidate_caches()
    api = importlib.import_module("structural_analysis.api.nonlinear_fiber_frame")
    loader = importlib.import_module("structural_analysis.io.neutral.loader")
    fields = inspect.signature(api.PublicRCFiberFrameConfig).parameters
    options = {"load_steps": 2}
    if "matrix_backend" in fields:
        options["matrix_backend"] = matrix_backend
    elif matrix_backend != DENSE:
        raise RuntimeError("requested sparse backend is unsupported by this source; no dense fallback")
    config = api.PublicRCFiberFrameConfig(**options)
    loaded_project_sources(root)
    return root, api, loader, config, "matrix_backend" in fields


def payload_generator():
    path = Path(__file__).resolve().with_name("benchmark_native_steel_batch.py")
    spec = importlib.util.spec_from_file_location("rc_execution_payload_generator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.public_payload, file_identity(path)


def git_identity(root):
    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()
    return {"source_root": str(root), "head": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"), "dirty": bool(git("status", "--porcelain=v1"))}


def measure_case(args, case_id, api, loader, config, make_payload, owner, report, backend):
    members, layers = CASES[case_id]
    budget = CaseBudget(args.elapsed_budget_seconds)
    row = {"case_id": case_id, "members": members, "concrete_layers": layers, "load_steps": 2,
           "status": "preparing", "samples_ns": [], "sample_fingerprints": [],
           "process_peak_rss_before": peak_rss()}
    report["cases"].append(row)
    owner.save(report)
    payload = make_payload(members, layers)
    row["input"] = payload
    row["input_sha256"] = sha(canonical_bytes(payload))
    model = loader.load_neutral_json_bytes(canonical_bytes(payload))

    def evaluate():
        result = api.analyze_public_rc_fiber_frame(model, config)
        validation = api.validate_public_rc_fiber_frame_result(result)
        if result.status != "ready" or not validation.contract_pass:
            raise RuntimeError("existing public RC analysis and validation gates did not pass")
        return result

    for index in range(args.repetitions + 1):
        row["status"] = "running_first_api_call" if index == 0 else "running_steady_api_call"
        row["active_sample"] = index
        owner.save(report)
        print(json.dumps({"case": case_id, "stage": row["status"], "sample": index}), flush=True)
        with budget.api_call():
            started = time.perf_counter_ns()
            result = evaluate()
            elapsed = time.perf_counter_ns() - started
        fingerprint, numerical, checkpoint = fingerprint_result(result)
        actual_configuration = execution_configuration(result, args.matrix_backend)
        if index == 0:
            row.update(first_call_ns=elapsed, first_fingerprint=fingerprint,
                       first_execution_configuration=actual_configuration,
                       first_normalized_result=numerical,
                       first_checkpoint=owner.sidecar(case_id, "checkpoint.json", checkpoint))
        else:
            row["samples_ns"].append(elapsed)
            row["sample_fingerprints"].append(fingerprint)
            if fingerprint != row["first_fingerprint"]:
                raise RuntimeError("same-backend result/checkpoint fingerprint changed between API calls")
            if actual_configuration != row["first_execution_configuration"]:
                raise RuntimeError("execution configuration changed between API calls")
        row["process_peak_rss_after_latest_api_call"] = peak_rss()
        owner.save(report)
        budget.remaining()
    row["median_ns"] = statistics.median(row["samples_ns"])
    row["stdev_ns"] = statistics.pstdev(row["samples_ns"])
    if args.profile:
        row["status"] = "running_separate_diagnostic_profile"
        owner.save(report)
        profile_path = owner.path.with_name(f"{owner.path.name}.{case_id}.profile.pstats")
        with profile_path.open("xb"):
            pass
        profiler = cProfile.Profile()
        profile_failure = None
        try:
            with budget.api_call():
                diagnostic = profiler.runcall(evaluate)
        except BaseException as error:
            profile_failure = error
            raise
        finally:
            row["profile"] = {
                "status": "interrupted" if profile_failure is not None else "completed",
                "separate_from_steady_measurement": True,
            }
            try:
                profiler.create_stats()
                has_records = bool(profiler.stats)
                profiler.dump_stats(str(profile_path))
                row["profile"]["raw_pstats"] = file_identity(profile_path)
                row["profile"]["has_function_records"] = has_records
                if has_records:
                    row["profile"].update(summarize_profile(pstats.Stats(profiler)))
                else:
                    row["profile"].update(total_self_seconds=0.0, category_self_seconds={key: 0.0 for key in CATEGORIES},
                                          category_self_seconds_sum=0.0, functions=[])
            except Exception as error:
                row["profile"]["diagnostic_error"] = {"type": type(error).__name__, "detail": str(error)}
                if profile_failure is None:
                    raise
            owner.save(report)
        profile_fingerprint, _numerical, _checkpoint = fingerprint_result(diagnostic)
        row["profile"]["fingerprint"] = profile_fingerprint
        if profile_fingerprint != row["first_fingerprint"]:
            raise RuntimeError("profile diagnostic result/checkpoint differs from steady API calls")
        if execution_configuration(diagnostic, args.matrix_backend) != row["first_execution_configuration"]:
            raise RuntimeError("profile diagnostic execution configuration changed")
    budget.remaining()
    row["status"] = "completed"
    row.pop("active_sample", None)
    row["all_steady_samples_match_first"] = True
    row["process_peak_rss_after"] = peak_rss()
    if backend is not None:
        row["native_backend_after"] = backend.metadata()
    owner.save(report)


def run(args):
    owner = OwnedReport(args.output)
    report = {"schema": "public-rc-execution-pipeline-benchmark.v1", "status": "initializing",
              "requested_cases": args.cases, "cases": [], "argv": sys.argv,
              "driver": file_identity(__file__), "process_peak_rss_at_driver_start": peak_rss(),
              "measurement": {"first_calls": 1, "steady_repetitions": args.repetitions,
                              "clock": "perf_counter_ns", "timed_scope": "same public analyze+validate returned API",
                              "excluded": "process startup, imports, model preparation, all fingerprints/source hashes/report writes, and the separate profile diagnostic",
                              "first_call_is_process_cold": False,
                              "normalization_removes_only": NORMALIZATION,
                              "same_backend_exact_repeat_required": True,
                              "cross_backend_parity": "not inferred; separate comparisons must inspect numerical values and all unchanged physical acceptance gates"},
              "budget": {"seconds_per_case": args.elapsed_budget_seconds,
                         "scope": "case preparation+calls+fingerprints+optional diagnostic; cooperative checks and POSIX signal around API calls",
                         "limit": "C extensions may defer Python signal handling; not a hard process kill or external resource limiter; external supervisor may leave the current case unfinished"},
              "thread_environment": {key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OMP_WAIT_POLICY")},
              "machine": {"platform": platform.platform(), "python": platform.python_version(),
                          "cpu_affinity": sorted(os.sched_getaffinity(0))},
              "claim_boundary": "generated bounded public RC API observations only; no experimental, physical, commercial, complete product or release qualification"}
    owner.save(report)
    try:
        root, api, loader, config, supports_matrix = load_runtime(args.source_root, args.matrix_backend)
        make_payload, payload_source = payload_generator()
        report.update(source=git_identity(root), config={"matrix_backend_requested": args.matrix_backend,
                      "source_supports_matrix_backend_option": supports_matrix, "load_steps": 2},
                      payload_generator_source=payload_source,
                      loaded_project_sources_before=loaded_project_sources(root))
        report["dependency_versions"] = {
            name: {"version": getattr(sys.modules.get(name), "__version__", None),
                   "module_file": getattr(sys.modules.get(name), "__file__", None)}
            for name in ("numpy", "scipy", "jsonschema")
        }
        backend = None
        context = nullcontext()
        if args.steel_library:
            native = importlib.import_module("structural_analysis.materials.native_steel_batch")
            options = {"workers": args.steel_workers}
            if "prepared" in inspect.signature(native.NativeSteelBatch).parameters:
                options["prepared"] = args.prepared
            elif args.prepared:
                raise RuntimeError("prepared steel execution is unsupported by this source")
            backend = native.NativeSteelBatch(args.steel_library, **options)
            context = native.use_native_steel_batch(backend)
            report["native_library"] = file_identity(args.steel_library)
            report["native_backend_before"] = backend.metadata()
        report["loaded_project_sources_before"] = loaded_project_sources(root)
        known_sources = dict(report["loaded_project_sources_before"])
        report["status"] = "running"
        owner.save(report)
        with context:
            for case_id in args.cases:
                measure_case(args, case_id, api, loader, config, make_payload, owner, report, backend)
                after = loaded_project_sources(root)
                verify_unchanged(known_sources, after)
                known_sources.update(after)
                report["loaded_project_sources_first_observed"] = known_sources
                report["loaded_project_sources_after"] = after
                if file_identity(__file__) != report["driver"] or file_identity(payload_source["path"]) != payload_source:
                    raise RuntimeError("benchmark driver or payload generator changed during measurement")
                owner.save(report)
        report["status"] = "completed"
        report["all_sources_unchanged"] = True
        return_code = 0
    except Exception as error:
        report["status"] = "time_budget_exceeded" if isinstance(error, CaseBudgetExceeded) else "failed"
        report["error"] = {"type": type(error).__name__, "detail": str(error)}
        if report["cases"] and report["cases"][-1]["status"] != "completed":
            report["cases"][-1]["status"] = report["status"]
        return_code = 124 if isinstance(error, CaseBudgetExceeded) else 1
    finally:
        report["unstarted_cases"] = [case_id for case_id in args.cases
                                    if case_id not in {row["case_id"] for row in report["cases"]}]
        report["process_peak_rss_final"] = peak_rss()
        owner.save(report)
    print(json.dumps({"output": str(owner.path), "status": report["status"],
                      "completed_cases": sum(row["status"] == "completed" for row in report["cases"])}), flush=True)
    return return_code


def main(argv=None):
    args = parse_arguments(argv)
    try:
        return run(args)
    except FileExistsError:
        print("refuse to overwrite an existing report or sidecar", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
