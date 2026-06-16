#!/usr/bin/env python3
"""Build UX release evidence for the PM gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any


DEFAULT_VIEWER_QUALITY = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json")
DEFAULT_VIEWER_PERFORMANCE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ux_release_readiness_report.json")


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
    return {
        "command": shlex.join(command),
        "return_code": int(proc.returncode),
        "elapsed_seconds": float(elapsed),
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def build_report(
    *,
    viewer_quality_path: Path,
    viewer_performance_path: Path,
    max_sample_minutes: float,
    browser_smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    viewer_quality = _load_json(viewer_quality_path)
    viewer_perf = _load_json(viewer_performance_path)
    viewer_summary = _summary(viewer_quality)
    claim_scoped_items, blocking_items = _classify_review_queue(viewer_quality)
    smoke = browser_smoke if isinstance(browser_smoke, dict) else {}
    smoke_elapsed_seconds = _as_float(smoke.get("elapsed_seconds"), 0.0)
    sample_completion_minutes = smoke_elapsed_seconds / 60.0 if smoke else None
    smoke_pass = bool(smoke and _as_int(smoke.get("return_code"), 1) == 0)
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
