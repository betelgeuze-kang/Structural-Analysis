#!/usr/bin/env python3
"""Run a fresh full-validation lane command and write a schema-valid receipt.

The built receipt conforms to
``implementation/phase1/fresh_validation_receipt.schema.json`` and is
validated with ``validate_fresh_validation_receipt.validate_payload``
before it is written to disk. A failing validation command produces
no passing receipt and returns a nonzero exit code; an optional
``--out-result`` path receives a concise blocker/result payload in
that case.

The default and only passing behaviour runs the supplied
``--validation-command`` as a real subprocess so the receipt records a
real, freshly-run lane. Metadata-only receipt construction is blocked:
``reused_evidence=false`` must mean a validation command actually ran.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PHASE1_DIR = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    now_utc_iso,
)
from validate_fresh_validation_receipt import (  # noqa: E402
    validate_payload as validate_receipt_payload,
)

DEFAULT_RECEIPT_SCHEMA = PHASE1_DIR / "fresh_validation_receipt.schema.json"
DEFAULT_CLAIM_BOUNDARY = (
    "Receipt attests that the named lane produced real, freshly-run evidence "
    "(reused_evidence=false) and that the runner's own contract checks passed "
    "(contract_pass=true, reason_code=PASS). It does not authorize Level 3 "
    "promotion, release publication, or any external claim. Promotion, "
    "claim-boundary review, and release decisions remain with the human owner."
)
SCHEMA_VERSION = "fresh-validation-receipt.v1"
BUILDER_SCHEMA_VERSION = "fresh-validation-receipt-builder.v1"
PYTHON_EXECUTABLE_NAMES = {"python", "python3"}
RUNNER_COMMAND_PREFIXES: dict[str, tuple[tuple[str, ...], ...]] = {
    "torch_capable_benchmark_validation": (
        ("python3", "scripts/report_commercial_solver_cross_validation.py"),
    ),
    "gpu_capable_rocm_hip_validation": (
        ("python3", "implementation/phase1/run_solver_hip_e2e_contract.py"),
        (
            "python3",
            "implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py",
            "--component-only",
            "--require-hip-residual-engine",
        ),
    ),
    "performance_validation": (
        ("python3", "implementation/phase1/run_performance_profiling_gate.py"),
    ),
    "heavy_surface_material_contact_validation": (
        ("python3", "implementation/phase1/run_general_fe_contact_benchmark_gate.py"),
        ("python3", "implementation/phase1/run_mgt_surface_membrane_tangent.py"),
        ("python3", "implementation/phase1/run_mgt_surface_shell_bending_tangent.py"),
        ("python3", "implementation/phase1/run_mgt_coupled_frame_surface_sparse_equilibrium.py"),
    ),
    "midas_validation": (
        ("python3", "implementation/phase1/run_midas_exact_roundtrip_closure_gate.py"),
        ("python3", "implementation/phase1/run_midas_interoperability_gate.py"),
    ),
    "heavy_productization_validation": (
        ("python3", "implementation/phase1/run_productization_gate.py"),
        ("python3", "implementation/phase1/run_ndtha_residual_gate.py"),
    ),
    "benchmark_productization_validation": (
        ("python3", "implementation/phase1/start_external_benchmark_task.py"),
        ("python3", "implementation/phase1/run_external_benchmark_refresh_lane.py"),
    ),
    "design_optimization_validation": (
        ("python3", "implementation/phase1/run_design_optimization_solver_loop_long.py"),
    ),
}


class CommandRunError(RuntimeError):
    """Raised when the validation command exits nonzero or cannot be launched."""


class ReceiptBuildError(RuntimeError):
    """Raised when required receipt provenance cannot be represented safely."""


def _split_command(raw: str) -> list[str]:
    try:
        return shlex.split(raw, posix=True)
    except ValueError as exc:
        raise CommandRunError(f"validation_command_unparseable:{exc}") from exc


def _is_python_executable(token: str) -> bool:
    text = str(token).strip()
    if not text:
        return False
    if text == sys.executable:
        return True
    return os.path.basename(text) in PYTHON_EXECUTABLE_NAMES


def _argv_matches_prefix(argv: list[str], prefix: tuple[str, ...]) -> bool:
    if len(argv) < len(prefix):
        return False
    for index, expected in enumerate(prefix):
        actual = argv[index]
        if index == 0 and expected in PYTHON_EXECUTABLE_NAMES:
            if not _is_python_executable(actual):
                return False
            continue
        if actual != expected:
            return False
    return True


def _runner_command_blockers(
    *,
    runner: str,
    validation_command: str,
    runner_command_prefixes: dict[str, tuple[tuple[str, ...], ...]] | None = None,
) -> list[str]:
    registry = (
        RUNNER_COMMAND_PREFIXES
        if runner_command_prefixes is None
        else runner_command_prefixes
    )
    runner_id = str(runner).strip()
    prefixes = registry.get(runner_id)
    if not prefixes:
        return [f"fresh_validation_runner_not_registered:{runner_id or '<empty>'}"]
    try:
        argv = _split_command(validation_command)
    except CommandRunError as exc:
        return [str(exc)]
    if not argv:
        return ["validation_command_empty"]
    if any(_argv_matches_prefix(argv, prefix) for prefix in prefixes):
        return []
    return [f"fresh_validation_command_not_allowed_for_runner:{runner_id}"]


def _run_validation_command(
    command: str,
    *,
    cwd: Path,
    timeout: float | None,
) -> dict[str, Any]:
    argv = _split_command(command)
    if not argv:
        raise CommandRunError("validation_command_empty")
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CommandRunError(f"validation_command_not_found:{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandRunError(f"validation_command_timeout:{exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise CommandRunError(f"validation_command_launch_failed:{exc}") from exc
    return {
        "returncode": int(completed.returncode),
        "stdout_tail": (completed.stdout or "")[-2048:],
        "stderr_tail": (completed.stderr or "")[-2048:],
    }


def _parse_artifact_spec(value: str) -> tuple[str, str | None]:
    text = str(value).strip()
    if not text:
        return "", None
    if ":" in text:
        path, _, kind = text.partition(":")
        kind = kind.strip() or None
    else:
        path, kind = text, None
    return path.strip(), kind


def _resolve_target(path_text: str, repo_root: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _digest_for(path: Path, *, label: str) -> str:
    if not path.exists():
        raise ReceiptBuildError(f"{label}_missing:{path}")
    if not path.is_file():
        raise ReceiptBuildError(f"{label}_not_file:{path}")
    return file_sha256(path)


def _build_input_checksums(
    paths: list[str], *, repo_root: Path
) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw in paths:
        text = str(raw).strip()
        if not text:
            continue
        target = _resolve_target(text, repo_root)
        checksums[text] = _digest_for(target, label="input")
    return dict(sorted(checksums.items()))


def _build_artifact_entries(
    artifacts: list[tuple[str, str | None]], *, repo_root: Path
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path_text, kind in artifacts:
        target = _resolve_target(path_text, repo_root)
        digest = _digest_for(target, label="receipt_artifact")
        entry: dict[str, str] = {"path": path_text, "sha256": digest}
        if kind:
            entry["kind"] = kind
        entries.append(entry)
    return entries


def _build_summary(
    *,
    case_count: int | None,
    passed_case_count: int | None,
    duration_seconds: float | None,
    actual_duration: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_count": int(case_count) if case_count is not None else 0,
        "passed_case_count": int(passed_case_count) if passed_case_count is not None else 0,
    }
    payload["duration_seconds"] = (
        float(duration_seconds)
        if duration_seconds is not None
        else float(actual_duration)
    )
    return payload


def _lane_summary_metadata(*, lane_id: str, runner: str) -> dict[str, Any]:
    if lane_id == "gpu_hip_solver" or runner == "gpu_capable_rocm_hip_validation":
        return {
            "readiness_group": "fresh_validation",
            "developer_preview_category": "benchmark",
            "blocker_group": "fresh_receipt_presence",
            "lane_scope": "performance_track_after_cpu_reference_parity",
            "claim_boundary_tag": "gpu_hip_after_cpu_reference_parity_non_promoting",
            "promotes_g1_cpu_parity": False,
        }
    return {}


def build_receipt(
    *,
    lane_id: str,
    runner: str,
    validation_command: str,
    input_paths: list[str],
    artifacts: list[tuple[str, str | None]],
    case_count: int | None,
    passed_case_count: int | None,
    duration_seconds: float | None,
    claim_boundary: str,
    repo_root: Path,
    actual_duration: float = 0.0,
) -> dict[str, Any]:
    source_commit = git_head(repo_root)
    if not source_commit:
        raise ReceiptBuildError("source_commit_sha_missing_git_head")
    engine = engine_version(repo_root)
    summary = _build_summary(
        case_count=case_count,
        passed_case_count=passed_case_count,
        duration_seconds=duration_seconds,
        actual_duration=actual_duration,
    )
    summary.update(_lane_summary_metadata(lane_id=lane_id, runner=runner))
    return {
        "schema_version": SCHEMA_VERSION,
        "lane_id": lane_id,
        "runner": runner,
        "generated_at": now_utc_iso(),
        "source_commit_sha": source_commit,
        "engine_version": engine,
        "input_checksums": _build_input_checksums(input_paths, repo_root=repo_root),
        "reused_evidence": False,
        "contract_pass": True,
        "reason_code": "PASS",
        "validation_command": validation_command,
        "receipt_artifacts": _build_artifact_entries(artifacts, repo_root=repo_root),
        "summary": summary,
        "claim_boundary": claim_boundary,
    }


def _write_result(
    path: Path | None,
    *,
    contract_pass: bool,
    reason_code: str,
    blockers: list[str],
    receipt_path: Path | None,
    command_result: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> None:
    if path is None:
        return
    payload: dict[str, Any] = {
        "schema_version": BUILDER_SCHEMA_VERSION,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "blockers": sorted(set(blockers)),
        "receipt_path": str(receipt_path) if receipt_path else "",
    }
    if command_result is not None:
        payload["command_result"] = {
            "returncode": command_result.get("returncode"),
            "stdout_tail": command_result.get("stdout_tail", ""),
            "stderr_tail": command_result.get("stderr_tail", ""),
        }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane-id", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Input path whose SHA256 should be recorded (repeatable).",
    )
    parser.add_argument(
        "--receipt-artifact",
        action="append",
        default=[],
        help="Receipt artifact path, optionally suffixed with ':kind' (repeatable).",
    )
    parser.add_argument("--output-receipt", type=Path, required=True)
    parser.add_argument("--case-count", type=int, default=None)
    parser.add_argument("--passed-case-count", type=int, default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--claim-boundary", default=DEFAULT_CLAIM_BOUNDARY)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used for relative path resolution and git HEAD.",
    )
    parser.add_argument(
        "--receipt-schema",
        type=Path,
        default=DEFAULT_RECEIPT_SCHEMA,
    )
    parser.add_argument(
        "--command-cwd",
        type=Path,
        default=None,
        help="Working directory for the validation command (defaults to --repo-root).",
    )
    parser.add_argument(
        "--command-timeout",
        type=float,
        default=None,
        help="Optional timeout in seconds for the validation command.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help=(
            "Forbidden for passing receipts. Retained only to return an explicit "
            "blocker for older tooling that still passes the flag."
        ),
    )
    parser.add_argument(
        "--out-result",
        type=Path,
        default=None,
        help="Optional path for a concise result payload (written even on failure).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a concise JSON summary to stdout on success.",
    )
    parser.add_argument(
        "--fail-blocked",
        action="store_true",
        help="Return nonzero exit code when the receipt does not validate.",
    )
    return parser


def _build_artifacts(values: list[str]) -> list[tuple[str, str | None]]:
    return [
        pair
        for pair in (_parse_artifact_spec(value) for value in values)
        if pair[0]
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    artifacts = _build_artifacts(args.receipt_artifact)
    repo_root = args.repo_root.resolve()
    command_cwd = (args.command_cwd or repo_root).resolve()
    receipt_path = args.output_receipt

    if not artifacts:
        _write_result(
            args.out_result,
            contract_pass=False,
            reason_code="ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            blockers=["receipt_artifacts_missing_or_empty"],
            receipt_path=None,
            command_result=None,
        )
        print(
            "fresh-validation-receipt: BLOCKED | "
            "reason=receipt_artifacts_missing_or_empty"
        )
        return 2

    command_result: dict[str, Any] | None = None
    started = datetime.now(timezone.utc)
    if args.metadata_only:
        blocker = "metadata_only_cannot_assert_fresh_validation"
        _write_result(
            args.out_result,
            contract_pass=False,
            reason_code="ERR_FRESH_VALIDATION_COMMAND_REQUIRED",
            blockers=[blocker],
            receipt_path=None,
            command_result=None,
        )
        print(f"fresh-validation-receipt: BLOCKED | reason={blocker}")
        return 7
    else:
        command_policy_blockers = _runner_command_blockers(
            runner=args.runner,
            validation_command=args.validation_command,
        )
        if command_policy_blockers:
            _write_result(
                args.out_result,
                contract_pass=False,
                reason_code="ERR_FRESH_VALIDATION_COMMAND_NOT_ALLOWED",
                blockers=command_policy_blockers,
                receipt_path=None,
                command_result=None,
            )
            print(
                "fresh-validation-receipt: BLOCKED | "
                f"reason={command_policy_blockers[0]}"
            )
            return 9
        try:
            command_result = _run_validation_command(
                args.validation_command,
                cwd=command_cwd,
                timeout=args.command_timeout,
            )
        except CommandRunError as exc:
            _write_result(
                args.out_result,
                contract_pass=False,
                reason_code="ERR_FRESH_VALIDATION_COMMAND_FAILED",
                blockers=[str(exc)],
                receipt_path=None,
                command_result=None,
            )
            print(f"fresh-validation-receipt: BLOCKED | reason={exc}")
            return 3
        if command_result["returncode"] != 0:
            blocker = f"validation_command_exit_{command_result['returncode']}"
            _write_result(
                args.out_result,
                contract_pass=False,
                reason_code="ERR_FRESH_VALIDATION_COMMAND_FAILED",
                blockers=[blocker],
                receipt_path=None,
                command_result=command_result,
            )
            print(f"fresh-validation-receipt: BLOCKED | reason={blocker}")
            return 4

    actual_duration = (
        datetime.now(timezone.utc) - started
    ).total_seconds()

    try:
        receipt = build_receipt(
            lane_id=args.lane_id,
            runner=args.runner,
            validation_command=args.validation_command,
            input_paths=args.input,
            artifacts=artifacts,
            case_count=args.case_count,
            passed_case_count=args.passed_case_count,
            duration_seconds=args.duration_seconds,
            claim_boundary=args.claim_boundary,
            repo_root=repo_root,
            actual_duration=actual_duration,
        )
    except ReceiptBuildError as exc:
        _write_result(
            args.out_result,
            contract_pass=False,
            reason_code="ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            blockers=[str(exc)],
            receipt_path=None,
            command_result=command_result,
        )
        print(f"fresh-validation-receipt: BLOCKED | reason={exc}")
        return 8

    try:
        schema = json.loads(args.receipt_schema.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        _write_result(
            args.out_result,
            contract_pass=False,
            reason_code="ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            blockers=[f"schema_unreadable:{exc}"],
            receipt_path=None,
            command_result=command_result,
        )
        print(f"fresh-validation-receipt: BLOCKED | reason=schema_unreadable:{exc}")
        return 5

    validation = validate_receipt_payload(receipt, schema)

    if not validation.get("contract_pass"):
        _write_result(
            args.out_result,
            contract_pass=False,
            reason_code=validation.get(
                "reason_code", "ERR_FRESH_VALIDATION_RECEIPT_INVALID"
            ),
            blockers=list(validation.get("blockers", [])),
            receipt_path=None,
            command_result=command_result,
        )
        print(
            "fresh-validation-receipt: BLOCKED | "
            f"reason={validation.get('reason_code')} | "
            f"blockers={len(validation.get('blockers', []))}"
        )
        return 1 if args.fail_blocked else 6

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _write_result(
        args.out_result,
        contract_pass=True,
        reason_code="PASS",
        blockers=[],
        receipt_path=receipt_path,
        command_result=command_result,
    )

    summary = {
        "schema_version": BUILDER_SCHEMA_VERSION,
        "contract_pass": True,
        "reason_code": "PASS",
        "receipt_path": str(receipt_path),
        "lane_id": args.lane_id,
        "runner": args.runner,
        "summary": receipt.get("summary", {}),
        "claim_boundary": args.claim_boundary,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "fresh-validation-receipt: PASS | "
            f"receipt={receipt_path} | lane_id={args.lane_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
