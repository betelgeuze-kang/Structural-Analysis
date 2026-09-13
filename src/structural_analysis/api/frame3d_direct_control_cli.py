"""Experimental CLI for the existing bounded ModelIR Frame3D control API."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
from typing import Any, Sequence

from structural_analysis.api._output_integrity import (
    resolve_distinct_output_bundle_paths,
    write_json_pair,
    write_json_pair_and_bytes,
    write_json_pair_and_clear_artifact,
)
from structural_analysis.api.frame3d_direct_control import (
    BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES,
    BoundedFrame3DDirectControlConfig,
    BoundedFrame3DDirectControlResult,
    analyze_bounded_frame3d_direct_control_model_ir,
    validate_bounded_frame3d_direct_control_result,
)
from structural_analysis.api.frame3d_direct_control_request import (
    decode_bounded_frame3d_direct_control_request,
    strict_json_object_bytes,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir import parse_model_ir_v2


EXECUTION_REPORT_SCHEMA_VERSION = "bounded-frame3d-direct-control-execution-report.v1"
MODEL_MAX_BYTES = 16 * 1024 * 1024
REQUEST_MAX_BYTES = 128 * 1024
_SOURCE_REVISION = re.compile(r"(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})\Z")


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(maximum_bytes + 1)
    if not raw or len(raw) > maximum_bytes:
        raise ValueError(f"input must contain 1 through {maximum_bytes} bytes: {path}")
    return raw


def _input_identity(role: str, path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "role": role,
        "path": str(path.resolve()),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
    }


def _output_paths(
    args: argparse.Namespace, protected: dict[str, Path]
) -> dict[str, Path]:
    paths = {"--out": Path(args.out), "--report-out": Path(args.report_out)}
    if args.checkpoint_out is not None:
        paths["--checkpoint-out"] = Path(args.checkpoint_out)
    return resolve_distinct_output_bundle_paths(paths, protected_paths=protected)


def _execution_report(
    result: BoundedFrame3DDirectControlResult,
    config: BoundedFrame3DDirectControlConfig,
    source_revision: str,
    inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = result.to_dict()
    report = {
        "schema_version": EXECUTION_REPORT_SCHEMA_VERSION,
        "profile": result.profile,
        "status": result.status,
        "execution_contract_pass": result.contract_pass,
        "result_contract_validation_passed": True,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "inputs": inputs,
        "request_hash": config.request_hash,
        "resume_contract_hash": config.resume_contract_hash,
        "control": config.to_dict(),
        "source_binding": payload["source_binding"],
        "result_schema_version": result.schema_version,
        "result_hash": result.result_hash,
        "model_hash": result.model_hash,
        "solver_result_hash": result.solver_result_hash,
        "terminal_reason_code": result.terminal_reason_code,
        "checkpoint_artifact": payload["checkpoint_artifact"],
        "authority": payload["authority"],
        "claim_boundary": result.claim_boundary,
        "report_scope": (
            "validated_existing_bounded_candidate_api_result_and_exact_input_bytes;"
            "not_independent_solver_validation_or_source_attestation"
        ),
    }
    report["report_hash"] = canonical_hash(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="structural-analysis-bounded-frame3d-control",
        description=(
            "Execute the experimental bounded Frame3D direct-control API from "
            "ModelIR v2 and a typed JSON request. Capability-registry public and "
            "Workbench execution authority remain false."
        ),
    )
    parser.add_argument("model_path", help="bounded Frame3D ModelIR v2 JSON")
    parser.add_argument("--request", required=True, help="bounded control request v1 JSON")
    parser.add_argument(
        "--source-revision",
        required=True,
        help="full source commit or sha256 identity; caller declaration, not attestation",
    )
    parser.add_argument("--restart-checkpoint", help="exact persisted API checkpoint artifact")
    parser.add_argument("--out", required=True, help="existing API result v2 JSON")
    parser.add_argument("--report-out", required=True, help="input-bound execution report JSON")
    parser.add_argument("--checkpoint-out", help="optional exact terminal checkpoint artifact")
    args = parser.parse_args(argv)

    try:
        if not _SOURCE_REVISION.fullmatch(args.source_revision):
            raise ValueError("source revision must be a full lowercase commit or sha256 identity")
        model_path, request_path = Path(args.model_path), Path(args.request)
        protected = {"model input": model_path, "request input": request_path}
        if args.restart_checkpoint is not None:
            protected["restart checkpoint"] = Path(args.restart_checkpoint)
        outputs = _output_paths(args, protected)

        # Parse exactly the bytes bound into the execution report. No second
        # model/config read can silently change the actual solver request.
        request_raw = _read_bounded(request_path, REQUEST_MAX_BYTES)
        config = decode_bounded_frame3d_direct_control_request(request_raw)
        model_raw = _read_bounded(model_path, MODEL_MAX_BYTES)
        document = parse_model_ir_v2(
            strict_json_object_bytes(model_raw, maximum_bytes=MODEL_MAX_BYTES)
        )
        snapshots = [
            ("model", model_path, model_raw, MODEL_MAX_BYTES),
            ("request", request_path, request_raw, REQUEST_MAX_BYTES),
        ]
        restart = None
        if args.restart_checkpoint is not None:
            restart_path = Path(args.restart_checkpoint)
            restart = _read_bounded(
                restart_path, BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES
            )
            snapshots.append(
                (
                    "restart_checkpoint", restart_path, restart,
                    BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES,
                )
            )
        identities = [_input_identity(role, path, raw) for role, path, raw, _ in snapshots]
        result = analyze_bounded_frame3d_direct_control_model_ir(
            document, config, restart_checkpoint_artifact=restart
        )
        validate_bounded_frame3d_direct_control_result(result)
        actual_control = result.to_dict()["control"]
        expected_control = config.to_dict()
        if (
            actual_control.get("request_hash") != config.request_hash
            or canonical_hash({key: actual_control.get(key) for key in expected_control})
            != canonical_hash(expected_control)
            or any(
                result.source_binding[key] != value
                for key, value in (
                    ("model_ir_content_hash", document.content_hash),
                    ("model_ir_semantic_hash", document.semantic_hash),
                    ("model_ir_provenance_hash", document.provenance_hash),
                )
            )
        ):
            raise ValueError("validated result does not bind the actual model/control request")
        report = _execution_report(result, config, args.source_revision, identities)

        # Retain old outputs if inputs or path bindings changed during analysis.
        if _output_paths(args, protected) != outputs:
            raise ValueError("output path bindings changed during analysis")
        for identity, (role, path, raw, maximum_bytes) in zip(
            identities, snapshots, strict=True
        ):
            current = _read_bounded(path, maximum_bytes)
            if current != raw or _input_identity(role, path, current) != identity:
                raise ValueError(f"input changed during analysis: {role}")

        result_payload = result.to_dict()
        result_path, report_path = outputs["--out"], outputs["--report-out"]
        checkpoint_path = outputs.get("--checkpoint-out")
        if checkpoint_path is None:
            write_json_pair(result_path, result_payload, report_path, report)
        else:
            try:
                artifact = result.checkpoint_artifact_bytes()
            except ValueError:
                write_json_pair_and_clear_artifact(
                    result_path, result_payload, report_path, report, checkpoint_path
                )
            else:
                write_json_pair_and_bytes(
                    result_path, result_payload, report_path, report,
                    checkpoint_path, artifact,
                )
    except (OSError, ValueError, TypeError, RecursionError) as error:
        parser.error(str(error))
    return 0 if result.status == "ready" and result.contract_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
