#!/usr/bin/env python3
"""Build UX release evidence for the PM gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any


DEFAULT_VIEWER_QUALITY = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json")
DEFAULT_VIEWER_PERFORMANCE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_SAMPLE_WORKFLOW_SMOKE = Path("implementation/phase1/structure_viewer_sample_workflow_smoke.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ux_release_readiness_report.json")
NATIVE_SAMPLE_WORKFLOW_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "execution_mode",
        "status",
        "source_map_sha256",
        "frontend_contract_receipt_hash",
        "tracked_sources",
        "max_sample_completion_minutes",
        "requested_output",
        "published_output_path",
        "output_disposition",
        "logical_command_template",
        "artifact_schema_version",
        "artifact_sha256",
        "artifact_generated_at",
        "sample_completion_minutes",
        "verified_step_count",
        "step_rows_sha256",
        "significant_pixel_count",
        "browser_error_count",
        "browser_warning_count",
        "runtime_requirements",
        "rust_owned_listener_count",
        "direct_processes_spawned",
        "successful_exit_code",
        "external_network_access_accounting",
        "deterministic_receipt",
        "claim_boundary",
        "receipt_hash",
    }
)
NATIVE_SAMPLE_WORKFLOW_SOURCES = (
    ("viewer_index", "src/structure-viewer/index.html"),
    (
        "sample_workflow_probe",
        "scripts/verify-structure-viewer-sample-workflow.mjs",
    ),
    ("canvas_frame_probe", "scripts/structure-viewer-canvas-frame.mjs"),
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
        or str(payload.get("reason_code", "")).strip().upper() == "PASS_WITH_REVIEW_QUEUE"
    )


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_claim_scoped_review_item(item: dict[str, Any]) -> bool:
    quality_tier = str(item.get("quality_tier", "") or "")
    claim_flags = {str(flag) for flag in item.get("claim_quality_flags", []) if str(flag)}
    action = str(item.get("recommended_action", "") or "").lower()
    quality_flags = {str(flag) for flag in item.get("quality_flags", []) if str(flag)}
    if quality_tier == "ifc_geometry_ready_load_review" and "ifc_load_model_missing" in claim_flags:
        return True
    if "not_solver_exact" in quality_flags and "load" in action and "claim" in action:
        return True
    return False


def _classify_review_queue(viewer_quality: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items = viewer_quality.get("review_queue") if isinstance(viewer_quality.get("review_queue"), list) else []
    claim_scoped: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_claim_scoped_review_item(item):
            claim_scoped.append(item)
        else:
            blocking.append(item)
    return claim_scoped, blocking


def _run_browser_smoke(command: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    receipt = _native_sample_workflow_receipt(proc.stdout or "")
    completion_minutes = _float_or_none(receipt.get("sample_completion_minutes"))
    measured_seconds = (
        completion_minutes * 60.0
        if completion_minutes is not None
        else float(elapsed)
    )
    return {
        "command": shlex.join(command),
        "return_code": int(proc.returncode),
        "elapsed_seconds": measured_seconds,
        "process_elapsed_seconds": float(elapsed),
        "sample_completion_minutes": completion_minutes,
        "browser_error_count": _as_int(receipt.get("browser_error_count"), 1),
        "browser_warning_count": _as_int(receipt.get("browser_warning_count"), 0),
        "reason_code": "PASS" if receipt.get("status") == "passed" else "",
        "schema_version": str(receipt.get("schema_version", "")),
        "native_receipt_valid": bool(receipt),
        "native_receipt_hash": str(receipt.get("receipt_hash", "")),
        "artifact_sha256": str(receipt.get("artifact_sha256", "")),
        "published_output_path": str(receipt.get("published_output_path") or ""),
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def _native_sample_workflow_receipt(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(
                line,
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_nonfinite_json,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        completion_minutes = _float_or_none(payload.get("sample_completion_minutes"))
        maximum_minutes = _float_or_none(
            payload.get("max_sample_completion_minutes")
        )
        sources = payload.get("tracked_sources")
        source_identity = tuple(
            (str(row.get("label", "")), str(row.get("path", "")))
            for row in sources
            if isinstance(row, dict)
        ) if isinstance(sources, list) else ()
        source_rows_valid = bool(
            isinstance(sources, list)
            and len(sources) == len(NATIVE_SAMPLE_WORKFLOW_SOURCES)
            and source_identity == NATIVE_SAMPLE_WORKFLOW_SOURCES
            and all(
                set(row) == {"label", "path", "bytes", "sha256"}
                and _as_int(row.get("bytes"), 0) > 0
                and _is_sha256_identity(row.get("sha256"))
                for row in sources
                if isinstance(row, dict)
            )
        )
        logical_command = payload.get("logical_command_template")
        logical_command_valid = bool(
            isinstance(logical_command, list)
            and logical_command[:6]
            == [
                "node",
                "scripts/verify-structure-viewer-sample-workflow.mjs",
                "--fail-blocked",
                "--out",
                "{workflow_output}",
                "--max-minutes",
            ]
            and len(logical_command) == 7
            and _float_or_none(logical_command[6]) == maximum_minutes
        )
        output_disposition = payload.get("output_disposition")
        requested_output = payload.get("requested_output")
        published_output = payload.get("published_output_path")
        output_valid = bool(
            (
                output_disposition == "temporary_removed_after_verification"
                and requested_output is None
                and published_output is None
            )
            or (
                output_disposition == "operator_path_retained"
                and isinstance(requested_output, str)
                and bool(requested_output)
                and isinstance(published_output, str)
                and bool(published_output)
            )
            or (
                output_disposition == "temporary_path_retained"
                and requested_output is None
                and isinstance(published_output, str)
                and bool(published_output)
            )
        )
        if (
            set(payload) != NATIVE_SAMPLE_WORKFLOW_RECEIPT_KEYS
            or payload.get("schema_version")
            != "structural-native-viewer-sample-workflow-receipt.v1"
            or payload.get("action") != "viewer_sample_workflow"
            or payload.get("execution_mode") != "execute"
            or payload.get("status") != "passed"
            or not _is_sha256_identity(payload.get("receipt_hash"))
            or not _is_sha256_identity(payload.get("source_map_sha256"))
            or not _is_sha256_identity(payload.get("frontend_contract_receipt_hash"))
            or not source_rows_valid
            or not logical_command_valid
            or not output_valid
            or maximum_minutes is None
            or not math.isfinite(maximum_minutes)
            or maximum_minutes <= 0.0
            or completion_minutes is None
            or not math.isfinite(completion_minutes)
            or completion_minutes < 0.0
            or completion_minutes > maximum_minutes
            or payload.get("artifact_schema_version")
            != "structure-viewer-sample-workflow-smoke.v1"
            or not _is_sha256_identity(payload.get("artifact_sha256"))
            or not str(payload.get("artifact_generated_at", "")).strip()
            or not _is_sha256_identity(payload.get("step_rows_sha256"))
            or payload.get("verified_step_count") != 4
            or _as_int(payload.get("significant_pixel_count"), 0) <= 0
            or payload.get("browser_error_count") != 0
            or _as_int(payload.get("browser_warning_count"), -1) < 0
            or payload.get("runtime_requirements")
            != {
                "node_required": True,
                "browser_required": True,
                "retained_node_internal_listener": True,
            }
            or payload.get("rust_owned_listener_count") != 0
            or payload.get("direct_processes_spawned") != 1
            or payload.get("successful_exit_code") != 0
            or payload.get("external_network_access_accounting")
            != "not_instrumented_probe_loopback_and_browser_page_requests"
            or payload.get("deterministic_receipt") is not False
            or not str(payload.get("claim_boundary", "")).strip()
        ):
            continue
        unsigned = dict(payload)
        expected_hash = str(unsigned.pop("receipt_hash"))
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if "sha256:" + hashlib.sha256(canonical).hexdigest() != expected_hash:
            continue
        return payload
    return {}


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _is_sha256_identity(value: Any) -> bool:
    text = str(value or "")
    digest = text.removeprefix("sha256:")
    return (
        text.startswith("sha256:")
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _browser_smoke_from_artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _load_json(path)
    if not payload:
        return {}
    contract_pass = _reason_pass(payload)
    sample_completion_minutes = _float_or_none(payload.get("sample_completion_minutes"))
    return {
        "command": f"artifact:{path}",
        "artifact_path": str(path),
        "return_code": 0 if contract_pass else 1,
        "elapsed_seconds": sample_completion_minutes * 60.0 if sample_completion_minutes is not None else 0.0,
        "sample_completion_minutes": sample_completion_minutes,
        "browser_error_count": _as_int(payload.get("browser_error_count"), 1),
        "browser_warning_count": _as_int(payload.get("browser_warning_count"), 0),
        "reason_code": str(payload.get("reason_code", "")),
        "schema_version": str(payload.get("schema_version", "")),
    }


def build_report(
    *,
    viewer_quality_path: Path,
    viewer_performance_path: Path,
    max_sample_minutes: float,
    sample_workflow_smoke_path: Path | None = None,
    browser_smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    viewer_quality = _load_json(viewer_quality_path)
    viewer_perf = _load_json(viewer_performance_path)
    viewer_summary = _summary(viewer_quality)
    claim_scoped_items, blocking_items = _classify_review_queue(viewer_quality)
    smoke = browser_smoke if isinstance(browser_smoke, dict) else _browser_smoke_from_artifact(sample_workflow_smoke_path)
    smoke_elapsed_seconds = _as_float(smoke.get("elapsed_seconds"), 0.0)
    sample_completion_minutes = _float_or_none(smoke.get("sample_completion_minutes"))
    if sample_completion_minutes is None:
        sample_completion_minutes = smoke_elapsed_seconds / 60.0 if smoke else None
    receipt_valid = smoke.get("native_receipt_valid") if smoke else None
    smoke_pass = bool(
        smoke
        and _as_int(smoke.get("return_code"), 1) == 0
        and receipt_valid is not False
    )
    browser_ready_ms = _as_float((_summary(viewer_perf) or {}).get("ready_ms"), 0.0)
    if browser_ready_ms <= 0.0:
        browser_ready_ms = _as_float((viewer_perf.get("probe") or {}).get("readyMs") if isinstance(viewer_perf.get("probe"), dict) else 0.0, 0.0)

    checks = {
        "viewer_quality_gate_pass": _reason_pass(viewer_quality),
        "viewer_commercial_ready": bool(viewer_quality.get("commercial_viewer_ready", False)),
        "viewer_hard_blockers_zero": _as_int(viewer_summary.get("hard_blocker_count"), 1) == 0,
        "claim_scoped_review_queue_pass": len(blocking_items) == 0,
        "viewer_performance_probe_pass": _reason_pass(viewer_perf),
        "browser_sample_rehearsal_pass": smoke_pass,
        "sample_completion_30min_pass": bool(sample_completion_minutes is not None and sample_completion_minutes <= max_sample_minutes),
    }
    blockers = [key for key, ok in checks.items() if not ok]
    sample_workflow_artifact = (
        str(smoke.get("published_output_path", ""))
        if isinstance(browser_smoke, dict)
        else str(sample_workflow_smoke_path)
        if sample_workflow_smoke_path is not None
        else ""
    )
    return {
        "schema_version": "ux-release-readiness-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_UX_RELEASE_READINESS_BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "sample_completion_minutes": sample_completion_minutes,
            "max_sample_completion_minutes": max_sample_minutes,
            "browser_smoke_elapsed_seconds": smoke_elapsed_seconds if smoke else None,
            "viewer_review_item_count": _as_int(viewer_summary.get("review_item_count"), 0),
            "claim_scoped_review_item_count": len(claim_scoped_items),
            "blocking_review_item_count": len(blocking_items),
            "viewer_hard_blocker_count": _as_int(viewer_summary.get("hard_blocker_count"), 0),
            "viewer_ready_ms": browser_ready_ms,
        },
        "browser_smoke": smoke,
        "claim_scoped_review_items": claim_scoped_items,
        "blocking_review_items": blocking_items,
        "artifacts": {
            "viewer_quality": str(viewer_quality_path),
            "viewer_performance": str(viewer_performance_path),
            "sample_workflow_smoke": sample_workflow_artifact,
        },
        "claim_boundary": (
            "The sample completion evidence is an automated browser rehearsal of the first-run sample workflow, "
            "not a human usability study. Claim-scoped IFC load-model review items remain visible to reviewers "
            "and are excluded from UX hard blockers only while product claims stay engineer-in-loop and review-assist."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer-quality", type=Path, default=DEFAULT_VIEWER_QUALITY)
    parser.add_argument("--viewer-performance", type=Path, default=DEFAULT_VIEWER_PERFORMANCE)
    parser.add_argument("--sample-workflow-smoke", type=Path, default=DEFAULT_SAMPLE_WORKFLOW_SMOKE)
    parser.add_argument("--max-sample-minutes", type=float, default=30.0)
    parser.add_argument("--run-browser-smoke", action="store_true")
    parser.add_argument("--browser-smoke-command", default="npm run verify:viewer-sample-workflow")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke = _run_browser_smoke(shlex.split(args.browser_smoke_command)) if args.run_browser_smoke else None
    payload = build_report(
        viewer_quality_path=args.viewer_quality,
        viewer_performance_path=args.viewer_performance,
        max_sample_minutes=float(args.max_sample_minutes),
        sample_workflow_smoke_path=args.sample_workflow_smoke,
        browser_smoke=smoke,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_blocked and not payload["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
