"""Repeated public planar backend observations in separate Python processes.

Each slot uses frozen model bytes and a copied Python/schema tree. Measurements
describe this local execution only; a content hash is not source authentication,
independent numerical verification, or release authority. Run with ``python -m``
and --request, --source-revision, --output-directory, --timeout-seconds.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
from statistics import median, pstdev
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from typing import Any


REQUEST_SCHEMA = "planar-frame-backend-experiment-request.v1"
HISTORY_REQUEST_SCHEMA = "planar-frame-backend-experiment-request.v2"
HISTORY_WORKLOAD_SCOPE = (
    "api_public_validation_history_reassembly_and_result_checkpoint_history_persistence"
)
HISTORY_PHASE_SCOPE = "source_compile_checkpoint_decode_all_transition_reassembly_terminal_binding_history_encoding_write"
BACKENDS = (
    "numpy_linalg_solve_dense",
    "scipy_sparse_spsolve_cpu",
    "scipy_sparse_splu_cpu_exact_1536",
)
SI_ROWS = (
    "node_displacements",
    "support_reactions",
    "member_end_forces",
    "section_results",
    "fiber_results",
)
CONFIG_FIELDS = {
    "control",
    "load_steps",
    "residual_tolerance",
    "increment_tolerance_m",
    "maximum_iterations",
}
THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
CLAIM_BOUNDARY = (
    "Local public-planar workload observations with internal source-bound solver "
    "validation; no independent external V&V, generalized speedup, physical-disk "
    "traffic, per-API peak memory, final-design or release authority. Copied source "
    "hashes and caller revision labels are not authenticated provenance."
)


def _bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _same_json(left: Any, right: Any) -> bool:
    # Python equality aliases True/1 and 2/2.0; protocol identities do not.
    return _bytes(left) == _bytes(right)


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _json(data: bytes):
    return json.loads(data, object_pairs_hook=_unique, parse_constant=_reject_constant)


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        raise ValueError("fields do not match contract")


def _finite(value, *, positive=False):
    try:
        return (
            type(value) in (int, float)
            and math.isfinite(value)
            and (value > 0 if positive else value >= 0)
        )
    except OverflowError:
        return False


def _decode_request(data: bytes) -> dict:
    value = _json(data)
    history = (
        type(value) is dict and value.get("schema_version") == HISTORY_REQUEST_SCHEMA
    )
    _fields(
        value,
        {"schema_version", "cases", "backends", "repetitions", "warmups", "tolerances"}
        | ({"history_tolerances"} if history else set()),
    )
    if value["schema_version"] not in (REQUEST_SCHEMA, HISTORY_REQUEST_SCHEMA):
        raise ValueError("unsupported experiment schema")
    for name, low in (("repetitions", 1), ("warmups", 0)):
        if type(value[name]) is not int or not low <= value[name] <= 100:
            raise ValueError("invalid repetition count")
    backends = value["backends"]
    if (
        type(backends) is not list
        or not 1 <= len(backends) <= 3
        or any(type(b) is not str or b not in BACKENDS for b in backends)
        or len(set(backends)) != len(backends)
    ):
        raise ValueError("invalid backend declaration")
    cases = value["cases"]
    if type(cases) is not list or not 1 <= len(cases) <= 64:
        raise ValueError("one to 64 cases required")
    names = set()
    for case in cases:
        _fields(case, {"case_id", "model_file", "configuration"})
        if (
            type(case["case_id"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", case["case_id"])
            or case["case_id"] in names
        ):
            raise ValueError("case IDs must be unique safe labels")
        names.add(case["case_id"])
        if type(case["model_file"]) is not str or not case["model_file"]:
            raise ValueError("model_file must be a nonempty path")
        # Only model JSON is an input; this is not an arbitrary file archiver.
        if Path(case["model_file"]).suffix.lower() != ".json":
            raise ValueError("model_file must have .json extension")
        cfg = case["configuration"]
        _fields(cfg, CONFIG_FIELDS)
        if cfg["control"] not in (
            "load_control",
            "arc_length",
            "direct_displacement_control",
        ):
            raise ValueError("unsupported control declaration")
        for key, low, high in (("load_steps", 2, 64), ("maximum_iterations", 1, 200)):
            if type(cfg[key]) is not int or not low <= cfg[key] <= high:
                raise ValueError("invalid integer configuration")
        for key in ("residual_tolerance", "increment_tolerance_m"):
            if not _finite(cfg[key], positive=True):
                raise ValueError("invalid tolerance configuration")
    _fields(value["tolerances"], set(SI_ROWS))
    for tolerance in value["tolerances"].values():
        _fields(tolerance, {"absolute", "relative"})
        if not all(_finite(n) for n in tolerance.values()):
            raise ValueError("comparison tolerances must be finite and nonnegative")
    if history:
        _fields(value["history_tolerances"], {*SI_ROWS, "material_states"})
        for tolerance in value["history_tolerances"].values():
            _fields(tolerance, {"absolute", "relative"})
            if not all(_finite(n) for n in tolerance.values()):
                raise ValueError("history tolerances must be finite and nonnegative")
    if (value["warmups"] + value["repetitions"]) * len(cases) * len(backends) > 4096:
        raise ValueError("experiment exceeds 4096 declared slots")
    return value


def _history_requested(request: dict) -> bool:
    return request["schema_version"] == HISTORY_REQUEST_SCHEMA


def _schedule(request: dict) -> list[dict]:
    slots = []
    backends = request["backends"]
    for phase, count in (
        ("warmup", request["warmups"]),
        ("measurement", request["repetitions"]),
    ):
        for repetition in range(count):
            for case_index, case in enumerate(request["cases"]):
                shift = (case_index + repetition) % len(backends)
                for position, backend in enumerate(backends[shift:] + backends[:shift]):
                    slots.append(
                        {
                            "slot_index": len(slots),
                            "case_index": case_index,
                            "case_id": case["case_id"],
                            "phase": phase,
                            "repetition": repetition,
                            "backend": backend,
                            "backend_position": position,
                        }
                    )
    return slots


def _error(error: Exception) -> dict:
    return {"type": type(error).__name__, "message": str(error)[:2000]}


def _read(path: Path, limit=64 * 1024 * 1024) -> bytes:
    # Reject secret-style names even when a .json suffix has been appended.
    if any(re.search(r"(^|\.)env($|\.)", part) for part in path.parts):
        raise ValueError("environment files are not model inputs")
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a regular nonsymlink file")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit exceeded")
    return data


def _file_identity(path: Path) -> dict:
    data = path.read_bytes()
    return {"sha256": _digest(data), "byte_length": len(data)}


def _observed_identity(path: Path) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return _file_identity(path)
    except OSError:
        return None


def _source_files(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".py", ".json") or "__pycache__" in path.parts:
            continue
        if any(re.search(r"(^|\.)env($|\.)", part) for part in path.parts):
            raise ValueError("environment files cannot enter source snapshot")
        if path.is_symlink():
            raise ValueError("source snapshot does not permit symlinks")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _file_identity(path)
    return result


def _freeze_source(output: Path) -> dict:
    package = Path(__file__).resolve().parents[1]
    snapshot = output / "source" / "structural_analysis"
    before = _source_files(package)
    for relative, identity in before.items():
        original = package / relative
        if original.is_symlink():
            raise ValueError("source snapshot does not permit symlinks")
        data = _read(original)
        if _digest(data) != identity["sha256"]:
            raise ValueError("source changed during freeze")
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _write(target, data)
    if _source_files(package) != before or _source_files(snapshot) != before:
        raise ValueError("source changed during freeze")
    return before


def _model_identity(document) -> dict:
    return {
        key: getattr(document, key)
        for key in (
            "content_hash",
            "semantic_hash",
            "provenance_hash",
            "model_id",
            "capability_profile",
        )
    }


def _freeze_inputs(request: dict, request_path: Path, output: Path) -> list[dict]:
    from structural_analysis.model_ir import parse_model_ir_v2

    directory = output / "inputs"
    directory.mkdir()
    cases = []
    # Read every input before doing validation or starting any solver worker.
    for index, case in enumerate(request["cases"]):
        row = {
            **case,
            "input_file": f"inputs/case-{index:04d}.json",
            "input_identity": None,
            "model_identity": None,
            "preflight_error": None,
        }
        try:
            data = _read(request_path.parent / case["model_file"])
            _write(output / row["input_file"], data)
            row["input_identity"] = {"sha256": _digest(data), "byte_length": len(data)}
        except (OSError, ValueError) as error:
            row["preflight_error"] = _error(error)
        cases.append(row)
    for case in cases:
        if case["preflight_error"] is None:
            try:
                doc = parse_model_ir_v2(
                    _json((output / case["input_file"]).read_bytes()),
                    require_analysis_ready=True,
                )
                if doc.capability_profile != "planar_frame_verified_alpha.v1":
                    raise ValueError("model must use public planar profile")
                case["model_identity"] = _model_identity(doc)
            except (ValueError, TypeError, RecursionError) as error:
                case["preflight_error"] = _error(error)
    return cases


def _peak_rss() -> tuple[int | None, str]:
    if sys.platform == "linux":
        try:
            match = re.search(
                r"^VmHWM:\s+([0-9]+)\s+kB$", Path("/proc/self/status").read_text(), re.M
            )
            if match and int(match[1]) > 0:
                return int(match[1]) * 1024, "linux_proc_vmhwm_post_exec"
        except (OSError, UnicodeError):
            pass
    return None, "post_exec_process_peak_unavailable"


def _runtime_identity() -> dict:
    return {
        "python": sys.version,
        "executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": {
            name: version(name) for name in ("numpy", "scipy", "jsonschema")
        },
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def _module_paths(name: str) -> set[str]:
    if name == "structural_analysis":
        return {"__init__.py"}
    stem = name.removeprefix("structural_analysis.").replace(".", "/")
    return {stem + ".py", stem + "/__init__.py"}


def _import_identity(bundle: Path, sources: dict) -> dict:
    root = bundle / "source" / "structural_analysis"
    imports = {}
    for name, module in sorted(sys.modules.items()):
        if name != "structural_analysis" and not name.startswith(
            "structural_analysis."
        ):
            continue
        filename = getattr(module, "__file__", None)
        if filename is None:
            locations = list(getattr(module, "__path__", ()))
            expected = name.removeprefix("structural_analysis.").replace(".", "/")
            if (
                len(locations) != 1
                or getattr(getattr(module, "__spec__", None), "origin", None)
                is not None
                or Path(locations[0]).resolve() != (root / expected).resolve()
                or not any(path.startswith(expected + "/") for path in sources)
            ):
                raise ValueError(
                    "structural namespace is outside the frozen source tree"
                )
            imports[name] = "namespace:" + expected
            continue
        path = Path(filename).resolve()
        relative = path.relative_to(root.resolve()).as_posix()
        if (
            relative not in _module_paths(name)
            or relative not in sources
            or _file_identity(path) != sources[relative]
        ):
            raise ValueError("imported source differs from frozen tree")
        imports[name] = relative
    if "structural_analysis.api.planar_frame" not in imports:
        raise ValueError("public planar module was not imported")
    return imports


def _worker(
    bundle: Path,
    directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_slot_sha256: str,
) -> int:
    started = perf_counter_ns()
    manifest_bytes = (bundle / "inputs-manifest.json").read_bytes()
    slot_bytes = (directory / "slot.json").read_bytes()
    if (
        _digest(manifest_bytes) != expected_manifest_sha256
        or _digest(slot_bytes) != expected_slot_sha256
    ):
        _write(
            directory / "failure.json",
            _bytes(
                {
                    "stage": "bootstrap_binding",
                    "type": "ValueError",
                    "message": "frozen manifest or slot differs from parent declaration",
                }
            ),
        )
        return 1
    manifest = _json(manifest_bytes)
    slot = _json(slot_bytes)
    with_history = _history_requested(manifest["request"])
    case = manifest["cases"][slot["case_index"]]
    binding = {
        "worker_pid": os.getpid(),
        "slot_sha256": _digest(slot_bytes),
        "manifest_sha256": _digest(manifest_bytes),
        "source_digest": manifest["source_digest"],
    }
    _write(directory / "started.json", _bytes(binding))
    status, stage, error = "worker_error", "source_validation", None
    analysis_wall = analysis_cpu = workload_wall = workload_cpu = None
    imports = runtime = None
    api_entered = False
    history_runtime = {
        "status": "not_run",
        "reason": "phase_not_reached",
        "wall_ns": None,
        "cpu_ns": None,
        "scope": HISTORY_PHASE_SCOPE,
    }
    try:
        if (
            _source_files(bundle / "source" / "structural_analysis")
            != manifest["source_files"]
        ):
            raise ValueError("frozen source tree changed")
        from structural_analysis.api.planar_frame import (
            PlanarFrameConfig,
            analyze_planar_frame,
            validate_planar_frame_result,
        )
        from structural_analysis.model_ir import parse_model_ir_v2

        imports = _import_identity(bundle, manifest["source_files"])
        runtime = _runtime_identity()
        stage = "input_validation"
        data = (bundle / case["input_file"]).read_bytes()
        if {"sha256": _digest(data), "byte_length": len(data)} != case[
            "input_identity"
        ]:
            raise ValueError("frozen model bytes changed")
        doc = parse_model_ir_v2(_json(data), require_analysis_ready=True)
        if _model_identity(doc) != case["model_identity"]:
            raise ValueError("frozen model identity changed")
        config = PlanarFrameConfig(
            **case["configuration"], matrix_backend=slot["backend"]
        )
        stage = "analysis"
        _write(directory / "entered.json", _bytes(binding))
        api_entered = True
        wall, cpu = perf_counter_ns(), process_time_ns()
        try:
            a_wall, a_cpu = perf_counter_ns(), process_time_ns()
            try:
                result = analyze_planar_frame(doc, config)
            finally:
                analysis_wall = perf_counter_ns() - a_wall
                analysis_cpu = process_time_ns() - a_cpu
            stage = "result_persistence"
            _write(directory / "result.json", _bytes(result.to_dict()))
            try:
                checkpoint = result.checkpoint_artifact()
            except ValueError:
                checkpoint = None
            if checkpoint is not None:
                _write(directory / "checkpoint.json", checkpoint)
            stage = "public_validation"
            validation = validate_planar_frame_result(result).to_dict()
            _write(directory / "validation.json", _bytes(validation))
            if with_history:
                if result.converged is True:
                    from structural_analysis.benchmark.planar_frame_history import (
                        build_planar_frame_history,
                    )

                    stage = "history_projection"
                    h_wall, h_cpu = perf_counter_ns(), process_time_ns()
                    history_runtime.update(
                        status="failed", reason="history_projection_failed"
                    )
                    try:
                        history = build_planar_frame_history(
                            doc, config, result, checkpoint
                        )
                        _write(directory / "history.json", _bytes(history))
                        history_runtime.update(status="ready", reason=None)
                    finally:
                        history_runtime["wall_ns"] = perf_counter_ns() - h_wall
                        history_runtime["cpu_ns"] = process_time_ns() - h_cpu
                else:
                    history_runtime["reason"] = "public_result_not_converged"
        finally:
            workload_wall = perf_counter_ns() - wall
            workload_cpu = process_time_ns() - cpu
        stage = "final_source_validation"
        imports = _import_identity(bundle, manifest["source_files"])
        if (
            _source_files(bundle / "source" / "structural_analysis")
            != manifest["source_files"]
        ):
            raise ValueError("frozen source tree changed")
        status = "finished"
    except Exception as failure:
        error = _error(failure)
        _write(directory / "failure.json", _bytes({"stage": stage, **error}))
    artifacts = {
        name: _file_identity(directory / name)
        for name in (
            "started.json",
            "entered.json",
            "result.json",
            "checkpoint.json",
            "validation.json",
            "failure.json",
        )
        + (("history.json",) if with_history else ())
        if (directory / name).is_file()
    }
    peak, peak_method = _peak_rss()
    resources = {
        "schema_version": "planar-frame-backend-worker.v2"
        if with_history
        else "planar-frame-backend-worker.v1",
        **binding,
        "status": status,
        "stage": stage,
        "error": error,
        "api_entered": api_entered,
        "input_identity": case["input_identity"],
        "model_identity": case["model_identity"],
        "configuration": {**case["configuration"], "matrix_backend": slot["backend"]},
        "imports": imports,
        "runtime_identity": runtime,
        "artifacts": artifacts,
        "analysis_wall_ns": analysis_wall,
        "analysis_cpu_ns": analysis_cpu,
        "workload_wall_ns": workload_wall,
        "workload_cpu_ns": workload_cpu,
        "worker_wall_ns": perf_counter_ns() - started,
        "worker_cpu_ns": process_time_ns(),
        "peak_rss_bytes": peak,
        "peak_rss_method": peak_method,
        "analysis_scope": "public_api_including_internal_source_validation",
        "workload_scope": HISTORY_WORKLOAD_SCOPE
        if with_history
        else "api_explicit_public_validation_and_result_checkpoint_report_persistence",
        "worker_scope": "post_exec_cpu_and_peak_through_workload_source_checks_and_artifact_hashing_before_resource_sidecar_encoding;wall_starts_after_stdlib_imports",
        "claim_boundary": CLAIM_BOUNDARY,
        **({"history_runtime": history_runtime} if with_history else {}),
    }
    _write(directory / "resources.json", _bytes(resources))
    return 0 if status == "finished" else 1


def _decode_result(payload: dict):
    from structural_analysis.api.planar_frame import PlanarFrameResult

    expected = {field.name for field in fields(PlanarFrameResult)} - {
        "_checkpoint_bytes"
    }
    _fields(payload, expected | {"schema_version"})
    result = PlanarFrameResult(**{key: payload[key] for key in expected})
    if not _same_json(result.to_dict(), payload):
        raise ValueError("result representation mismatch")
    return result


def _validate_worker_bundle(
    directory: Path, slot: dict, pid: int, manifest: dict, source_digest: str
):
    from structural_analysis.api.planar_frame import validate_planar_frame_result

    with_history = _history_requested(manifest["request"])
    resources = _json(_read(directory / "resources.json"))
    _fields(
        resources,
        {
            "schema_version",
            "worker_pid",
            "slot_sha256",
            "manifest_sha256",
            "source_digest",
            "status",
            "stage",
            "error",
            "api_entered",
            "input_identity",
            "model_identity",
            "configuration",
            "imports",
            "runtime_identity",
            "artifacts",
            "analysis_wall_ns",
            "analysis_cpu_ns",
            "workload_wall_ns",
            "workload_cpu_ns",
            "worker_wall_ns",
            "worker_cpu_ns",
            "peak_rss_bytes",
            "peak_rss_method",
            "analysis_scope",
            "workload_scope",
            "worker_scope",
            "claim_boundary",
        }
        | ({"history_runtime"} if with_history else set()),
    )
    case = manifest["cases"][slot["case_index"]]
    binding = {
        "worker_pid": pid,
        "slot_sha256": _digest(_bytes(slot)),
        "manifest_sha256": _digest(_bytes(manifest)),
        "source_digest": source_digest,
    }
    if (
        resources.get("schema_version")
        != (
            "planar-frame-backend-worker.v2"
            if with_history
            else "planar-frame-backend-worker.v1"
        )
        or any(resources.get(k) != v for k, v in binding.items())
        or type(resources["worker_pid"]) is not int
        or type(pid) is not int
        or pid == os.getpid()
        or not _same_json(resources.get("input_identity"), case["input_identity"])
        or not _same_json(resources.get("model_identity"), case["model_identity"])
        or not _same_json(
            resources.get("configuration"),
            {**case["configuration"], "matrix_backend": slot["backend"]},
        )
    ):
        raise ValueError("worker source/input/configuration/PID binding mismatch")
    if type(resources.get("api_entered")) is not bool or resources.get(
        "status"
    ) not in ("finished", "worker_error"):
        raise ValueError("worker outcome invalid")
    actual = {
        name: _file_identity(directory / name)
        for name in (
            "started.json",
            "entered.json",
            "result.json",
            "checkpoint.json",
            "validation.json",
            "failure.json",
        )
        + (("history.json",) if with_history else ())
        if (directory / name).is_file()
    }
    if not _same_json(actual, resources.get("artifacts")):
        raise ValueError("worker artifact byte binding mismatch")
    if ("entered.json" in actual) != resources["api_entered"]:
        raise ValueError("API entry marker mismatch")
    if not _same_json(_json((directory / "slot.json").read_bytes()), slot):
        raise ValueError("slot declaration mismatch")
    expected_scopes = {
        "analysis_scope": "public_api_including_internal_source_validation",
        "workload_scope": HISTORY_WORKLOAD_SCOPE
        if with_history
        else "api_explicit_public_validation_and_result_checkpoint_report_persistence",
        "worker_scope": "post_exec_cpu_and_peak_through_workload_source_checks_and_artifact_hashing_before_resource_sidecar_encoding;wall_starts_after_stdlib_imports",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if any(resources[key] != value for key, value in expected_scopes.items()):
        raise ValueError("worker measurement scope mismatch")
    if with_history:
        observation = resources["history_runtime"]
        _fields(observation, {"status", "reason", "wall_ns", "cpu_ns", "scope"})
        if observation["scope"] != HISTORY_PHASE_SCOPE or observation["status"] not in (
            "not_run",
            "ready",
            "failed",
        ):
            raise ValueError("history phase scope or status mismatch")
        if observation["status"] == "not_run":
            if (
                observation["reason"]
                not in ("phase_not_reached", "public_result_not_converged")
                or observation["wall_ns"] is not None
                or observation["cpu_ns"] is not None
                or "history.json" in actual
            ):
                raise ValueError(
                    "unexecuted history phase has measured costs or output"
                )
        else:
            for unit in ("wall", "cpu"):
                value, workload = (
                    observation[unit + "_ns"],
                    resources["workload_" + unit + "_ns"],
                )
                if (
                    type(value) is not int
                    or value < 0
                    or type(workload) is not int
                    or value > workload
                ):
                    raise ValueError("history phase costs are not inside workload")
                analysis = resources["analysis_" + unit + "_ns"]
                if type(analysis) is not int or analysis + value > workload:
                    raise ValueError(
                        "disjoint analysis and history costs exceed workload"
                    )
            if observation["reason"] != (
                None
                if observation["status"] == "ready"
                else "history_projection_failed"
            ):
                raise ValueError("history phase failure reason mismatch")
            if observation["status"] == "ready" and "history.json" not in actual:
                raise ValueError("ready history phase is missing its output")
    for name in ("started.json",) + (
        ("entered.json",) if resources["api_entered"] else ()
    ):
        if not _same_json(_json((directory / name).read_bytes()), binding):
            raise ValueError("worker phase binding mismatch")
    for key in ("worker_wall_ns", "worker_cpu_ns"):
        if type(resources.get(key)) is not int or resources[key] < 0:
            raise ValueError("invalid worker timing")
    for unit in ("wall", "cpu"):
        analysis = resources.get(f"analysis_{unit}_ns")
        workload = resources.get(f"workload_{unit}_ns")
        whole = resources[f"worker_{unit}_ns"]
        if resources["api_entered"]:
            if (
                any(type(v) is not int or v < 0 for v in (analysis, workload))
                or not analysis <= workload <= whole
            ):
                raise ValueError("invalid nested workload timing")
        elif analysis is not None or workload is not None:
            raise ValueError("unentered API has workload timing")
    peak = resources.get("peak_rss_bytes")
    if peak is not None and (
        type(peak) is not int
        or peak <= 0
        or resources.get("peak_rss_method") != "linux_proc_vmhwm_post_exec"
    ):
        raise ValueError("invalid peak memory observation")
    if (
        peak is None
        and resources["peak_rss_method"] != "post_exec_process_peak_unavailable"
    ):
        raise ValueError("missing memory reason mismatch")
    if resources["imports"] is not None:
        if type(resources["imports"]) is not dict:
            raise ValueError("source import manifest must be an object")
        for name, path in resources["imports"].items():
            namespace = "namespace:" + name.removeprefix(
                "structural_analysis."
            ).replace(".", "/")
            namespace_valid = path == namespace and any(
                p.startswith(namespace.removeprefix("namespace:") + "/")
                for p in manifest["source_files"]
            )
            if (
                type(path) is not str
                or not (
                    path in manifest["source_files"]
                    and path in _module_paths(name)
                    or namespace_valid
                )
                or name != "structural_analysis"
                and not name.startswith("structural_analysis.")
            ):
                raise ValueError("unfrozen source import")
    if resources["runtime_identity"] is not None:
        expected_runtime = _runtime_identity()
        expected_runtime["thread_environment"] = {key: "1" for key in THREAD_VARIABLES}
        if not _same_json(resources["runtime_identity"], expected_runtime):
            raise ValueError("worker runtime identity mismatch")
    result = validation = None
    if resources["status"] == "finished":
        if (
            resources["api_entered"] is not True
            or resources["error"] is not None
            or "failure.json" in actual
            or resources["imports"] is None
            or "structural_analysis.api.planar_frame" not in resources["imports"]
            or resources["runtime_identity"]["thread_environment"]
            != {key: "1" for key in THREAD_VARIABLES}
        ):
            raise ValueError("finished worker phase contract mismatch")
        result = _json(_read(directory / "result.json"))
        validation = _json(_read(directory / "validation.json"))
        if not _same_json(
            validate_planar_frame_result(_decode_result(result)).to_dict(), validation
        ):
            raise ValueError("public result validation mismatch")
        source = result["result_ir"]
        if source is not None:
            if case["configuration"]["control"] != "load_control":
                raise ValueError("experimental control unexpectedly executed")
            cfg = source["configuration"]
            for key, value in {
                **case["configuration"],
                "matrix_backend": slot["backend"],
            }.items():
                result_key = {
                    "residual_tolerance": "scaled_residual_tolerance",
                    "increment_tolerance_m": "solver_coordinate_increment_tolerance_m",
                }.get(key, key)
                expected_value = (
                    float(value)
                    if key in ("residual_tolerance", "increment_tolerance_m")
                    else value
                )
                if key != "control" and not _same_json(
                    cfg.get(result_key), expected_value
                ):
                    raise ValueError("result configuration mismatch")
            adapter = source["contract_bindings"]["source_model_ir_adapter"]
            for key in ("content_hash", "semantic_hash", "provenance_hash"):
                if adapter.get("model_ir_" + key) != case["model_identity"][key]:
                    raise ValueError("result model identity mismatch")
            checkpoint = source["checkpoint"]
            if checkpoint["available"] is True:
                if not _same_json(
                    actual.get("checkpoint.json"),
                    {
                        "sha256": checkpoint["artifact_hash"],
                        "byte_length": checkpoint["artifact_byte_length"],
                    },
                ):
                    raise ValueError("checkpoint bytes differ from result descriptor")
            elif "checkpoint.json" in actual:
                raise ValueError("unavailable checkpoint has raw bytes")
        else:
            expected_reason = {
                "arc_length": "planar_frame_arc_length_experimental",
                "direct_displacement_control": "planar_frame_direct_displacement_control_experimental",
            }.get(case["configuration"]["control"])
            if (
                validation["unsupported_reason_codes"] != [expected_reason]
                or "checkpoint.json" in actual
            ):
                raise ValueError("unsupported control result mismatch")
        if result["converged"] is True and "checkpoint.json" not in actual:
            raise ValueError("converged result missing checkpoint")
        if with_history:
            if result["converged"] is True:
                if resources["history_runtime"]["status"] != "ready":
                    raise ValueError(
                        "converged v2 worker must complete history recovery"
                    )
                from structural_analysis.api.planar_frame import PlanarFrameConfig
                from structural_analysis.benchmark.planar_frame_history import (
                    build_planar_frame_history,
                )
                from structural_analysis.model_ir import parse_model_ir_v2

                bundle = directory.parent.parent
                model_bytes = _read(bundle / case["input_file"])
                if {
                    "sha256": _digest(model_bytes),
                    "byte_length": len(model_bytes),
                } != case["input_identity"]:
                    raise ValueError("history validation source model bytes changed")
                history = build_planar_frame_history(
                    parse_model_ir_v2(_json(model_bytes), require_analysis_ready=True),
                    PlanarFrameConfig(
                        **case["configuration"], matrix_backend=slot["backend"]
                    ),
                    _decode_result(result),
                    _read(directory / "checkpoint.json"),
                )
                if not _same_json(history, _json(_read(directory / "history.json"))):
                    raise ValueError(
                        "saved history differs from source checkpoint transition recovery"
                    )
            elif resources["history_runtime"] != {
                "status": "not_run",
                "reason": "public_result_not_converged",
                "wall_ns": None,
                "cpu_ns": None,
                "scope": HISTORY_PHASE_SCOPE,
            }:
                raise ValueError("nonconverged worker must retain unavailable history")
    else:
        _fields(resources["error"], {"type", "message"})
        if (
            any(type(value) is not str for value in resources["error"].values())
            or type(resources["stage"]) is not str
            or not resources["stage"]
            or "failure.json" not in actual
            or _json((directory / "failure.json").read_bytes())
            != {"stage": resources["stage"], **resources["error"]}
        ):
            raise ValueError("failed worker error binding mismatch")
        if not resources["api_entered"] and set(actual) & {
            "result.json",
            "checkpoint.json",
            "validation.json",
        }:
            raise ValueError("unentered API cannot produce result artifacts")
    return resources, result, validation


def _terminate(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_slot(
    bundle: Path, slot: dict, manifest: dict, timeout: float
) -> tuple[dict, dict | None]:
    directory = bundle / "slots" / f"{slot['slot_index']:04d}"
    directory.mkdir(parents=True)
    _write(directory / "slot.json", _bytes(slot))
    case = manifest["cases"][slot["case_index"]]
    row = {
        **slot,
        "directory": directory.relative_to(bundle).as_posix(),
        "status": "preflight_error",
        "error": case["preflight_error"],
        "launched": False,
        "worker_pid": None,
        "worker_exit_code": None,
        "api_entered": False,
        "artifact_contract_pass": False,
        "physical_converged": False,
        "resource_eligible": False,
        "parent_wall_ns": None,
        "worker_resources": None,
        "result": None,
        "artifacts": {},
        **(
            {
                "parent_artifact_validation_wall_ns": None,
                "parent_artifact_validation_cpu_ns": None,
                "parent_artifact_validation_scope": "whole_detached_bundle_validation_including_history_reassembly_excluding_launch_wait",
            }
            if _history_requested(manifest["request"])
            else {}
        ),
    }
    if case["preflight_error"] is not None:
        row["artifacts"] = {"slot.json": _file_identity(directory / "slot.json")}
        _write(directory / "row.json", _bytes(row))
        return row, None
    env = os.environ.copy()
    env.update({name: "1" for name in THREAD_VARIABLES})
    env["PYTHONPATH"] = str(bundle / "source")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-B",
        str(
            bundle
            / "source/structural_analysis/benchmark/planar_frame_backend_process.py"
        ),
        "--worker",
        "--output-directory",
        str(bundle),
        "--slot-directory",
        str(directory),
        "--expected-manifest-sha256",
        _digest(_bytes(manifest)),
        "--expected-slot-sha256",
        _digest(_bytes(slot)),
    ]
    started = perf_counter_ns()
    result = None
    process = None
    try:
        with (
            (directory / "stdout.log").open("xb") as stdout,
            (directory / "stderr.log").open("xb") as stderr,
        ):
            process = subprocess.Popen(
                command, cwd=bundle, env=env, stdout=stdout, stderr=stderr
            )
            row.update(launched=True, worker_pid=process.pid)
            try:
                row["worker_exit_code"] = process.wait(timeout=timeout)
                row["status"] = "worker_error"
            except subprocess.TimeoutExpired:
                _terminate(process)
                row.update(status="timeout", worker_exit_code=process.returncode)
            except BaseException:
                _terminate(process)
                raise
            finally:
                row["parent_wall_ns"] = perf_counter_ns() - started
        if row["status"] != "timeout":
            with_history = _history_requested(manifest["request"])
            if with_history:
                v_wall, v_cpu = perf_counter_ns(), process_time_ns()
            try:
                resources, result, validation = _validate_worker_bundle(
                    directory, slot, process.pid, manifest, manifest["source_digest"]
                )
            finally:
                if with_history:
                    row["parent_artifact_validation_wall_ns"] = (
                        perf_counter_ns() - v_wall
                    )
                    row["parent_artifact_validation_cpu_ns"] = process_time_ns() - v_cpu
            if resources["worker_wall_ns"] > row["parent_wall_ns"]:
                raise ValueError("worker wall exceeds observed launch-to-exit interval")
            expected_exit = 0 if resources["status"] == "finished" else 1
            if row["worker_exit_code"] != expected_exit:
                raise ValueError("worker exit/outcome mismatch")
            row.update(
                status=resources["status"],
                error=resources["error"],
                worker_resources=resources,
                resource_eligible=True,
            )
            if result is not None:
                row.update(
                    artifact_contract_pass=validation["contract_pass"] is True,
                    physical_converged=validation["converged"] is True
                    and validation["executed"] is True,
                    result={
                        key: result[key]
                        for key in ("status", "converged", "result_hash")
                    },
                )
        else:
            row["error"] = {
                "type": "TimeoutExpired",
                "message": "worker exceeded declared timeout",
            }
    except KeyboardInterrupt:
        row.update(
            status="cancelled",
            error={"type": "KeyboardInterrupt", "message": "experiment interrupted"},
        )
        if row["parent_wall_ns"] is None:
            row["parent_wall_ns"] = perf_counter_ns() - started
    except Exception as error:
        row.update(
            status="worker_error",
            error=_error(error),
            resource_eligible=False,
            worker_resources=None,
        )
        if row["parent_wall_ns"] is None:
            row["parent_wall_ns"] = perf_counter_ns() - started
        result = None
    finally:
        if process is not None:
            row["worker_exit_code"] = process.returncode
            entered = directory / "entered.json"
            if entered.is_file():
                try:
                    binding = _json(entered.read_bytes())
                    row["api_entered"] = binding == {
                        "worker_pid": process.pid,
                        "slot_sha256": _digest(_bytes(slot)),
                        "manifest_sha256": _digest(_bytes(manifest)),
                        "source_digest": manifest["source_digest"],
                    }
                except (ValueError, UnicodeError, OSError):
                    pass
    row["artifacts"] = {
        path.name: _file_identity(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }
    _write(directory / "row.json", _bytes(row))
    return row, result


def _distribution(values: list[int]) -> dict:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "median": median(values) if values else None,
        "population_standard_deviation": pstdev(values) if values else None,
    }


def _summaries(request: dict, rows: list[dict]) -> list[dict]:
    summary = []
    for case in request["cases"]:
        for backend in request["backends"]:
            selected = [
                r
                for r in rows
                if r["case_id"] == case["case_id"]
                and r["backend"] == backend
                and r["phase"] == "measurement"
            ]
            summary.append(
                {
                    "case_id": case["case_id"],
                    "backend": backend,
                    "declared_count": len(selected),
                    "statuses": dict(Counter(r["status"] for r in selected)),
                    "physical_converged_count": sum(
                        r["physical_converged"] for r in selected
                    ),
                    "parent_launch_to_exit_wall_ns": _distribution(
                        [
                            r["parent_wall_ns"]
                            for r in selected
                            if r["parent_wall_ns"] is not None
                        ]
                    ),
                    "completed_worker_resources_including_valid_failures": {
                        key: _distribution(
                            [
                                r["worker_resources"][key]
                                for r in selected
                                if r["resource_eligible"]
                                and r["worker_resources"][key] is not None
                            ]
                        )
                        for key in (
                            "analysis_wall_ns",
                            "analysis_cpu_ns",
                            "workload_wall_ns",
                            "workload_cpu_ns",
                            "worker_cpu_ns",
                            "peak_rss_bytes",
                        )
                    },
                    "backend_position_counts": dict(
                        Counter(str(r["backend_position"]) for r in selected)
                    ),
                }
            )
    return summary


def _repeat_identity(rows: list[dict], *, include_history: bool = False) -> list[dict]:
    first = {}
    comparisons = []
    for row in rows:
        key = (row["case_id"], row["phase"], row["backend"])
        if key not in first:
            first[key] = row
            continue
        baseline = first[key]
        available = all(
            r["physical_converged"] and r["artifact_contract_pass"]
            for r in (baseline, row)
        )
        comparisons.append(
            {
                "case_id": row["case_id"],
                "phase": row["phase"],
                "backend": row["backend"],
                "baseline_slot": baseline["slot_index"],
                "candidate_slot": row["slot_index"],
                "available": available,
                "raw_artifact_bytes_equal": {
                    name: baseline["artifacts"].get(name) == row["artifacts"].get(name)
                    if available
                    else None
                    for name in ("result.json", "validation.json", "checkpoint.json")
                    + (("history.json",) if include_history else ())
                },
                "scope": "same_backend_same_case_same_phase_original_artifact_hash_and_length;not_external_authentication",
            }
        )
    return comparisons


def _comparisons(
    bundle: Path, request: dict, rows: list[dict], results: dict[int, dict]
) -> list[dict]:
    from structural_analysis.benchmark.planar_frame_backend_comparison import (
        compare_planar_frame_results,
    )

    comparisons = []
    with_history = _history_requested(request)
    by_slot = {
        (r["case_id"], r["phase"], r["repetition"], r["backend"]): r for r in rows
    }
    for right in rows:
        if right["backend"] == request["backends"][0]:
            continue
        left = by_slot[
            (
                right["case_id"],
                right["phase"],
                right["repetition"],
                request["backends"][0],
            )
        ]
        pair = {
            "case_id": right["case_id"],
            "phase": right["phase"],
            "repetition": right["repetition"],
            "baseline_slot": left["slot_index"],
            "candidate_slot": right["slot_index"],
            "comparison": None,
            "paired_workload_wall_difference_ns": None,
            "paired_worker_cpu_difference_ns": None,
            "unavailable_reason": None,
            **({"history_comparison": None} if with_history else {}),
        }
        if not all(
            r["physical_converged"] and r["artifact_contract_pass"]
            for r in (left, right)
        ):
            pair["unavailable_reason"] = "both_slots_must_have_valid_converged_results"
        else:
            try:
                cp = [
                    (bundle / r["directory"] / "checkpoint.json").read_bytes()
                    for r in (left, right)
                ]
                comparison = compare_planar_frame_results(
                    results[left["slot_index"]],
                    results[right["slot_index"]],
                    tolerances=request["tolerances"],
                    left_checkpoint=cp[0],
                    right_checkpoint=cp[1],
                )
                if with_history:
                    from structural_analysis.benchmark.planar_frame_history_comparison import (
                        compare_planar_frame_histories,
                    )

                    histories = []
                    for row in (left, right):
                        data = _read(bundle / row["directory"] / "history.json")
                        if {"sha256": _digest(data), "byte_length": len(data)} != row[
                            "artifacts"
                        ].get("history.json"):
                            raise ValueError(
                                "history bytes changed before paired comparison"
                            )
                        history = _json(data)
                        if (
                            history["source_result_hash"]
                            != results[row["slot_index"]]["result_hash"]
                        ):
                            raise ValueError(
                                "history is detached from paired public result"
                            )
                        histories.append(history)
                    pair["history_comparison"] = compare_planar_frame_histories(
                        *histories, tolerances=request["history_tolerances"]
                    )
            except (OSError, ValueError, KeyError, TypeError) as error:
                pair["unavailable_reason"] = "saved_artifact_comparison_failed"
                pair["error"] = _error(error)
                for row in (left, right):
                    row.update(
                        resource_eligible=False,
                        physical_converged=False,
                        artifact_contract_pass=False,
                    )
                comparisons.append(pair)
                continue
            pair["comparison"] = comparison
            if (
                comparison["physical_si_match"] is True
                and (
                    not with_history
                    or pair["history_comparison"]["full_history_match"] is True
                )
                and all(r["resource_eligible"] for r in (left, right))
            ):
                for target, key in (
                    ("paired_workload_wall_difference_ns", "workload_wall_ns"),
                    ("paired_worker_cpu_difference_ns", "worker_cpu_ns"),
                ):
                    pair[target] = (
                        right["worker_resources"][key] - left["worker_resources"][key]
                    )
        comparisons.append(pair)
    return comparisons


def run_planar_frame_backend_experiment(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict:
    """Freeze declarations first; retain every planned slot, including failures."""
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}|sha256:[0-9a-f]{64}", source_revision
    ):
        raise ValueError("full source revision label required")
    if not _finite(timeout_seconds, positive=True):
        raise ValueError("timeout must be finite and positive")
    request_path = Path(request_path).absolute()
    raw = _read(request_path, 1024 * 1024)
    request = _decode_request(raw)
    output = Path(output_directory).absolute()
    if output.is_symlink():
        raise ValueError("output must be a new directory")
    output.mkdir(mode=0o700, exist_ok=False)
    started, cpu = perf_counter_ns(), process_time_ns()
    _write(output / "request.json", raw)
    sources = _freeze_source(output)
    cases = _freeze_inputs(request, request_path, output)
    slots = _schedule(request)
    manifest = {
        "schema_version": "planar-frame-backend-inputs.v1",
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "request_identity": _file_identity(output / "request.json"),
        "request": request,
        "cases": cases,
        "source_files": sources,
        "source_digest": _digest(_bytes(sources)),
        "schedule": slots,
        "timeout_seconds": timeout_seconds,
        "thread_environment": {key: "1" for key in THREAD_VARIABLES},
    }
    _write(output / "inputs-manifest.json", _bytes(manifest))
    rows, results = [], {}
    cancelled = False
    for slot in slots:
        if cancelled:
            row = {
                **slot,
                "status": "not_launched_after_cancellation",
                "launched": False,
                "api_entered": False,
                "physical_converged": False,
                "artifact_contract_pass": False,
                "resource_eligible": False,
                "parent_wall_ns": None,
                "worker_resources": None,
            }
            result = None
        else:
            row, result = _run_slot(output, slot, manifest, timeout_seconds)
            cancelled = row["status"] == "cancelled"
        rows.append(row)
        if result is not None:
            results[slot["slot_index"]] = result
    try:
        source_intact = (
            _source_files(output / "source" / "structural_analysis") == sources
        )
    except (OSError, ValueError):
        source_intact = False
    try:
        inputs_intact = (
            (output / "inputs-manifest.json").read_bytes() == _bytes(manifest)
            and (output / "request.json").read_bytes() == raw
            and all(
                case["input_identity"] is None
                or _file_identity(output / case["input_file"]) == case["input_identity"]
                for case in cases
            )
        )
    except (OSError, ValueError):
        inputs_intact = False
    if not source_intact or not inputs_intact:
        for row in rows:
            row.update(
                resource_eligible=False,
                physical_converged=False,
                artifact_contract_pass=False,
            )
    for row in rows:
        artifacts = row.get("artifacts", {})
        row["retained_artifacts_intact"] = all(
            _observed_identity(output / row["directory"] / name) == identity
            for name, identity in artifacts.items()
        )
        if not row["retained_artifacts_intact"]:
            row.update(
                resource_eligible=False,
                physical_converged=False,
                artifact_contract_pass=False,
            )
            row["retention_error"] = "saved_slot_artifacts_changed_or_missing"
    comparisons = _comparisons(output, request, rows, results)
    report = {
        "schema_version": "planar-frame-backend-experiment.v2"
        if _history_requested(request)
        else "planar-frame-backend-experiment.v1",
        "source_revision": source_revision,
        "source_digest": manifest["source_digest"],
        "manifest_identity": {
            "sha256": _digest(_bytes(manifest)),
            "byte_length": len(_bytes(manifest)),
        },
        "observed_manifest_identity": _observed_identity(
            output / "inputs-manifest.json"
        ),
        "status": "cancelled"
        if cancelled
        else "finished"
        if source_intact and inputs_intact
        else "invalidated",
        "schedule_complete": len(rows) == len(slots),
        "source_snapshot_intact": source_intact,
        "inputs_intact": inputs_intact,
        "counts": {
            "declared": len(slots),
            "launched": sum(r["launched"] for r in rows),
            "api_entered": sum(r["api_entered"] for r in rows),
            "artifact_contract_pass": sum(r["artifact_contract_pass"] for r in rows),
            "physical_converged": sum(r["physical_converged"] for r in rows),
            "resource_eligible": sum(r["resource_eligible"] for r in rows),
        },
        "rows": rows,
        "summaries": _summaries(request, rows),
        "comparisons": comparisons,
        "repeat_artifact_identity": _repeat_identity(
            rows, **({"include_history": True} if _history_requested(request) else {})
        ),
        "backend_order_policy": "round_major_rotating_by_case_index_plus_repetition_with_phase_reset",
        "parent_cpu_ns": process_time_ns() - cpu,
        "experiment_wall_ns": perf_counter_ns() - started,
        "parent_scope": "freeze_preflight_all_launches_waits_and_detached_artifact_validation_comparison_before_experiment_report_encoding",
        "resource_distribution_scope": "per_case_backend_measured_repetitions;warmups_excluded;failures_retained_with_null_unavailable_costs",
        "generalized_speedup_claimed": False,
        "independent_external_vv": False,
        "release_eligible": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if _history_requested(request):
        report["history_comparison_counts"] = {
            "expected_pairs": len(slots)
            // len(request["backends"])
            * (len(request["backends"]) - 1),
            "reported_pairs": len(comparisons),
            "terminal_si_match": sum(
                bool(p["comparison"] and p["comparison"]["physical_si_match"] is True)
                for p in comparisons
            ),
            "full_history_match": sum(
                bool(
                    p["history_comparison"]
                    and p["history_comparison"]["full_history_match"] is True
                )
                for p in comparisons
            ),
            "all_required_match": sum(
                bool(
                    p["comparison"]
                    and p["comparison"]["physical_si_match"] is True
                    and p["history_comparison"]
                    and p["history_comparison"]["full_history_match"] is True
                )
                for p in comparisons
            ),
        }
        report["history_scope"] = (
            "all_configured_accepted_epochs_and_genesis_material_state;each_worker_and_parent_reassembles_checkpoint_transitions_without_newton"
        )
    _write(output / "experiment.json", _bytes(report))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--slot-directory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-manifest-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--expected-slot-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(
            args.output_directory,
            args.slot_directory,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_slot_sha256=args.expected_slot_sha256,
        )
    if args.request is None or args.source_revision is None:
        parser.error("--request and --source-revision required")
    report = run_planar_frame_backend_experiment(
        args.request,
        source_revision=args.source_revision,
        output_directory=args.output_directory,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps({"output": str(args.output_directory), "counts": report["counts"]})
    )
    return (
        0
        if report["counts"]["physical_converged"] == report["counts"]["declared"]
        and (
            "history_comparison_counts" not in report
            or report["history_comparison_counts"]["all_required_match"]
            == report["history_comparison_counts"]["expected_pairs"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
