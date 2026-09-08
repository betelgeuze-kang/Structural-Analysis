"""Run and explicitly replay-verify the bounded experimental RC control API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Sequence

from structural_analysis.api import _output_integrity as output
from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    REQUEST_MAX_BYTES,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    CONTROL_RESTART_MAX_BYTES,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

MODEL_MAX_BYTES = 16 * 1024 * 1024
RESULT_MAX_BYTES = 512 * 1024 * 1024
REPORT_SCHEMA_VERSION = "bounded-rc-fiber-direct-control-cli-report.v1"


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError(f"input must contain 1 through {limit} bytes: {path}")
    return raw


def _identity(role, path, raw):
    return {
        "role": role,
        "path": str(path.resolve()),
        "byte_length": len(raw),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def _measured(call):
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    value = call()
    return value, {
        "wall_ns": time.perf_counter_ns() - wall,
        "process_cpu_ns": time.process_time_ns() - cpu,
    }


def _paths(args):
    protected = {"model input": Path(args.model), "request input": Path(args.request)}
    if args.restart is not None:
        protected["restart input"] = Path(args.restart)
    destinations = {"--report": Path(args.report)}
    if args.command == "run":
        destinations["--output"] = Path(args.output)
        if args.checkpoint_output is not None:
            destinations["--checkpoint-output"] = Path(args.checkpoint_output)
    else:
        protected["result input"] = Path(args.result)
        if args.checkpoint is not None:
            protected["checkpoint input"] = Path(args.checkpoint)
    return output.resolve_distinct_output_bundle_paths(
        destinations, protected_paths=protected
    )


def _inputs(args):
    specs = [
        ("request", Path(args.request), REQUEST_MAX_BYTES),
        ("model", Path(args.model), MODEL_MAX_BYTES),
    ]
    if args.restart is not None:
        specs.append(("restart", Path(args.restart), CONTROL_RESTART_MAX_BYTES))
    if args.command == "verify":
        specs.append(("result", Path(args.result), RESULT_MAX_BYTES))
        if args.checkpoint is not None:
            specs.append(
                ("checkpoint", Path(args.checkpoint), CONTROL_RESTART_MAX_BYTES)
            )
    snapshots = []
    for role, path, limit in specs:
        raw = _read_bounded(path, limit)
        snapshots.append((role, path, raw, limit, _identity(role, path, raw)))
    raw_by_role = {role: raw for role, _, raw, _, _ in snapshots}
    request = decode_bounded_rc_fiber_direct_control_request(raw_by_role["request"])
    model_raw = raw_by_role["model"]
    strict_json_object_bytes(model_raw, maximum_bytes=MODEL_MAX_BYTES)
    model = load_neutral_json_bytes(
        model_raw, source_path=str(Path(args.model).resolve())
    )
    if not request.targets_m and args.restart is None:
        raise ValueError("empty targets require an explicit restart")
    if args.restart is None and request.targets_m[0] == 0.0:
        raise ValueError(
            "first target must differ from the unloaded control coordinate"
        )
    # Full target/budget/config/source preflight remains in the unchanged path.
    return model, request, raw_by_role, snapshots


def _unchanged(args, paths, snapshots):
    if _paths(args) != paths:
        raise ValueError("output path bindings changed during execution")
    for role, path, raw, limit, identity in snapshots:
        current = _read_bounded(path, limit)
        if current != raw or _identity(role, path, current) != identity:
            raise ValueError(f"input changed during execution: {role}")


def _write_report(path, report):
    """Reuse shared staging for one atomic report; no multi-file crash claim."""
    text = output._serialize_json(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = output._snapshot_target(path)
    staged = output._stage_text(
        path, text, mode=None if original is None else original.mode
    )
    try:
        os.replace(staged, path)
    finally:
        output._unlink_if_present(staged)


def _seal_report(report):
    raw = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return report | {"report_hash": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _report(args, request, snapshots):
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "operation": args.command,
        "inputs": [identity for _, _, _, _, identity in snapshots],
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "resume_contract_hash": request.resume_contract_hash,
        "result_max_bytes": RESULT_MAX_BYTES,
        "scope": "original API work and mandatory fresh-source verification are separate; unsigned local consistency, not independent physics",
        "timing_scope": "reported function wall/process CPU only; input parsing, report formatting and output writes excluded",
        "claims": {
            "independent_physical_validation": False,
            "public_j1_j5_authority": False,
            "design_authority": False,
            "production_promotion_eligible": False,
            "performance_improvement_claimed": False,
        },
    }


def _run(args, model, request, raw, snapshots, paths):
    report = _report(args, request, snapshots)
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    try:
        result = api.analyze_bounded_rc_fiber_direct_control(
            model, request.targets_m, restart=raw.get("restart"), **request.api_kwargs()
        )
    except api.BoundedRCFiberDirectControlArtifactError as error:
        analysis_time = {
            "wall_ns": time.perf_counter_ns() - wall,
            "process_cpu_ns": time.process_time_ns() - cpu,
        }
        failure = error.to_dict()
        report.update(
            {
                "status": "artifact_export_failed",
                "analysis_status": failure["computed_path_status"],
                "analysis_contract_pass": False,
                "artifact_contract_pass": False,
                "contract_pass": False,
                "analysis_api_timing": analysis_time,
                "analysis_result_hash": None,
                "analysis_metrics": failure["execution_metrics"],
                "analysis_control_work": failure["execution_metrics"].get(
                    "control_work"
                ),
                "analysis_export_failure": failure,
                "verification": None,
                "verification_performed": False,
                "verification_api_timing": None,
                "physical_result_status_unchanged": failure["computed_path_status"],
                "result_output_published": False,
                "checkpoint_output_published": False,
            }
        )
        _unchanged(args, paths, snapshots)
        _write_report(paths["--report"], _seal_report(report))
        return 2
    analysis_time = {
        "wall_ns": time.perf_counter_ns() - wall,
        "process_cpu_ns": time.process_time_ns() - cpu,
    }
    payload = result.to_dict()
    report.update(
        {
            "analysis_status": result.status,
            "analysis_contract_pass": result.contract_pass,
            "analysis_result_hash": result.result_hash,
            "analysis_api_timing": analysis_time,
            "analysis_metrics": payload.get("metrics"),
            "analysis_control_work": (payload.get("metrics") or {}).get("control_work"),
            "analysis_control_accounting": (payload.get("path") or {}).get("metrics"),
        }
    )

    def serialize():
        canonical = result.result_artifact_bytes()
        rendered = output._serialize_json(payload).encode("utf-8")
        try:
            checkpoint = result.checkpoint_artifact_bytes()
        except ValueError:
            if result.status == "ready":
                raise
            checkpoint = None
        return canonical, rendered, checkpoint

    (result_raw, rendered, checkpoint), serialize_time = _measured(serialize)
    report["result_serialization_timing"] = serialize_time
    if len(result_raw) > RESULT_MAX_BYTES or len(rendered) > RESULT_MAX_BYTES:
        report.update(
            {
                "status": "output_limit_exceeded",
                "artifact_contract_pass": False,
                "contract_pass": False,
                "verification": None,
                "verification_performed": False,
                "verification_api_timing": None,
                "output_limit_failure": {
                    "canonical_bytes": len(result_raw),
                    "rendered_bytes": len(rendered),
                },
                "physical_result_status_unchanged": result.status,
                "result_output_published": False,
                "checkpoint_output_published": False,
            }
        )
        _unchanged(args, paths, snapshots)
        _write_report(paths["--report"], _seal_report(report))
        return 2

    validation, verification_time = _measured(
        lambda: api.validate_bounded_rc_fiber_direct_control_artifacts(
            model,
            request.targets_m,
            result=result_raw,
            checkpoint=checkpoint,
            restart=raw.get("restart"),
            **request.api_kwargs(),
        )
    )
    report.update(
        {
            "status": validation.status,
            "artifact_contract_pass": validation.artifact_contract_pass,
            "contract_pass": validation.contract_pass,
            "verification_performed": True,
            "verification": validation.to_dict(),
            "verification_api_timing": verification_time,
            "result_output_published": True,
            "checkpoint_output_published": "--checkpoint-output" in paths
            and checkpoint is not None
            and validation.artifact_contract_pass,
        }
    )
    _unchanged(args, paths, snapshots)
    report = _seal_report(report)
    if "--checkpoint-output" not in paths:
        output.write_json_pair(paths["--output"], payload, paths["--report"], report)
    elif checkpoint is not None and validation.artifact_contract_pass:
        output.write_json_pair_and_bytes(
            paths["--output"],
            payload,
            paths["--report"],
            report,
            paths["--checkpoint-output"],
            checkpoint,
        )
    else:
        output.write_json_pair_and_clear_artifact(
            paths["--output"],
            payload,
            paths["--report"],
            report,
            paths["--checkpoint-output"],
        )
    return (
        0
        if result.status == "ready"
        and result.contract_pass
        and validation.contract_pass
        else 2
    )


def _verify(args, model, request, raw, snapshots, paths):
    # Transport errors must be rejected before the replay validator is entered.
    strict_json_object_bytes(raw["result"], maximum_bytes=RESULT_MAX_BYTES)
    validation, timing = _measured(
        lambda: api.validate_bounded_rc_fiber_direct_control_artifacts(
            model,
            request.targets_m,
            result=raw["result"],
            checkpoint=raw.get("checkpoint"),
            restart=raw.get("restart"),
            **request.api_kwargs(),
        )
    )
    report = _report(args, request, snapshots)
    report.update(
        {
            "status": validation.status,
            "artifact_contract_pass": validation.artifact_contract_pass,
            "contract_pass": validation.contract_pass,
            "verification": validation.to_dict(),
            "verification_performed": True,
            "verification_api_timing": timing,
            "analysis_api_timing": None,
            "analysis_performed_by_cli": False,
        }
    )
    _unchanged(args, paths, snapshots)
    _write_report(paths["--report"], _seal_report(report))
    return 0 if validation.artifact_contract_pass else 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bounded-rc-fiber-direct-control",
        description="Experimental original RC direct control; verification performs fresh source replay.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--request", required=True)
        command.add_argument("--report", required=True)
        command.add_argument("--restart")
        if name == "run":
            command.add_argument("--output", required=True)
            command.add_argument("--checkpoint-output")
        else:
            command.add_argument("--result", required=True)
            command.add_argument("--checkpoint")
    args = parser.parse_args(argv)
    try:
        paths = _paths(args)
        model, request, raw, snapshots = _inputs(args)
        return (_run if args.command == "run" else _verify)(
            args, model, request, raw, snapshots, paths
        )
    except (OSError, ValueError, TypeError, RecursionError) as error:
        parser.error(str(error))
    return 2  # pragma: no cover - argparse.error exits


if __name__ == "__main__":
    raise SystemExit(main())
