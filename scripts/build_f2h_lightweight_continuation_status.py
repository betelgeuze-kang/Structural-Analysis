#!/usr/bin/env python3
"""Build the non-promoting F2h lightweight continuation status receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CONTINUATION = PRODUCTIZATION / "f2h_lightweight_pdelta_0p1_0p2_0p4.local.json"
DEFAULT_F2G_AUDIT = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
DEFAULT_OUTPUT = PRODUCTIZATION / "f2h_lightweight_continuation_status.local.json"
SCHEMA_VERSION = "f2h-lightweight-continuation-status.v1"
REQUIRED_LOAD_SEQUENCE = (0.1, 0.2, 0.4)


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _float_equal(left: float, right: float, *, eps: float = 1.0e-9) -> bool:
    return abs(float(left) - float(right)) <= eps


def _step_load(row: dict[str, Any]) -> float | None:
    value = row.get("load_step", row.get("load_scale", row.get("target_load_scale")))
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _step_rows(continuation: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in continuation.get("step_results") or []:
        if not isinstance(row, dict):
            continue
        load = _step_load(row)
        if load is None:
            continue
        rows.append(
            {
                "load_scale": float(load),
                "ready": bool(row.get("ready", row.get("converged", False))),
                "converged": bool(row.get("converged", row.get("ready", False))),
                "iteration_count": int(row.get("iteration_count") or 0),
                "residual_inf_n": row.get("residual_inf_n"),
                "relative_increment": row.get("relative_increment"),
                "max_translation_m": row.get("max_translation_m"),
                "max_drift_ratio_pct": row.get("max_drift_ratio_pct"),
                "blockers": list(row.get("blockers") or []),
            }
        )
    return rows


def _sequence_matches(rows: list[dict[str, Any]]) -> bool:
    loads = [float(row["load_scale"]) for row in rows]
    return len(loads) == len(REQUIRED_LOAD_SEQUENCE) and all(
        _float_equal(load, required)
        for load, required in zip(loads, REQUIRED_LOAD_SEQUENCE, strict=True)
    )


def _residual_trend(rows: list[dict[str, Any]]) -> str:
    values = [float(row["residual_inf_n"]) for row in rows if row.get("residual_inf_n") is not None]
    if len(values) < 2:
        return "insufficient_points"
    if all(right <= left for left, right in zip(values, values[1:], strict=False)):
        return "nonincreasing"
    if all(right >= left for left, right in zip(values, values[1:], strict=False)):
        return "nondecreasing"
    return "mixed"


def build_status(
    *,
    repo_root: Path = REPO_ROOT,
    continuation_path: Path = DEFAULT_CONTINUATION,
    f2g_audit_path: Path = DEFAULT_F2G_AUDIT,
) -> dict[str, Any]:
    resolved_continuation = continuation_path if continuation_path.is_absolute() else repo_root / continuation_path
    resolved_f2g = f2g_audit_path if f2g_audit_path.is_absolute() else repo_root / f2g_audit_path
    continuation = _load_json(resolved_continuation)
    f2g_audit = _load_json(resolved_f2g)
    blockers: list[str] = []
    if not continuation:
        blockers.append(f"missing_or_invalid_continuation:{resolved_continuation}")
    if not f2g_audit:
        blockers.append(f"missing_or_invalid_f2g_audit:{resolved_f2g}")
    rows = _step_rows(continuation)
    requested_sequence = list(continuation.get("load_steps_requested") or [])
    sequence_ok = _sequence_matches(rows)
    if not sequence_ok:
        blockers.append("required_load_sequence_0p1_0p2_0p4_not_proven")
    if any(not row["ready"] for row in rows):
        blockers.append("one_or_more_lightweight_load_steps_not_ready")
    if any(float(row["load_scale"]) > 0.4 for row in rows):
        blockers.append("load_sequence_exceeds_f2h_lightweight_contract")
    if float(continuation.get("max_converged_load_scale") or 0.0) < 0.4:
        blockers.append("max_converged_load_scale_below_0p4")
    if continuation.get("first_failed_load_scale") is not None:
        blockers.append("first_failed_load_scale_present")
    if f2g_audit.get("status") != "ready":
        blockers.append("f2g_reconciliation_audit_not_ready")
    ready = not blockers
    residual_history = [
        {
            "load_scale": row["load_scale"],
            "residual_inf_n": row["residual_inf_n"],
            "relative_increment": row["relative_increment"],
            "iteration_count": row["iteration_count"],
            "ready": row["ready"],
            "blockers": row["blockers"],
        }
        for row in rows
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(repo_root),
        "status": "ready" if ready else "blocked",
        "reason_code": "PASS" if ready else "ERR_F2H_LIGHTWEIGHT_CONTINUATION_NOT_PROVEN",
        "promotes_g1_closure": False,
        "claim_boundary": "non_promoting_f2h_lightweight_continuation_only",
        "source_inputs": {
            "continuation": {
                "path": str(resolved_continuation),
                "sha256": _sha256(resolved_continuation) if resolved_continuation.is_file() else "missing",
            },
            "f2g_audit": {
                "path": str(resolved_f2g),
                "sha256": _sha256(resolved_f2g) if resolved_f2g.is_file() else "missing",
            },
        },
        "summary": {
            "required_load_sequence": list(REQUIRED_LOAD_SEQUENCE),
            "requested_load_sequence": requested_sequence,
            "observed_load_sequence": [row["load_scale"] for row in rows],
            "required_sequence_proven": bool(sequence_ok),
            "all_steps_ready": bool(rows and all(row["ready"] for row in rows)),
            "max_converged_load_scale": continuation.get("max_converged_load_scale"),
            "first_failed_load_scale": continuation.get("first_failed_load_scale"),
            "load_scale_monotonic_increasing": all(
                right > left for left, right in zip([row["load_scale"] for row in rows], [row["load_scale"] for row in rows][1:], strict=False)
            ),
            "residual_trend_across_increasing_load": _residual_trend(rows),
            "blocker_count": int(len(blockers)),
        },
        "residual_history": residual_history,
        "stop_reasons": [
            {
                "load_scale": row["load_scale"],
                "stop_reason": "accepted" if row["ready"] else "blocked",
                "blockers": row["blockers"],
            }
            for row in rows
        ],
        "mode_comparison": {
            "f2g_audit_status": f2g_audit.get("status", "missing"),
            "baseline_near_null_mode_count": f2g_audit.get("near_null_context", {}).get("near_null_mode_count"),
            "baseline_dominant_dof_row_count": f2g_audit.get("summary", {}).get("dominant_dof_row_count"),
            "direct_support_member_count": f2g_audit.get("summary", {}).get("direct_support_member_count"),
            "direct_elastic_link_endpoint_count": f2g_audit.get("summary", {}).get("direct_elastic_link_endpoint_count"),
            "comparison_boundary": (
                "F2h reuses the F2g baseline near-null/support audit and does not claim a new "
                "load-dependent modal audit at 0.2 or 0.4."
            ),
        },
        "blockers": blockers,
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_full_load_claim",
            "no_0p656_regeneration_claim",
            "no_new_modal_claim_without_load_dependent_near_null_packet",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--continuation-json", type=Path, default=DEFAULT_CONTINUATION)
    parser.add_argument("--f2g-audit-json", type=Path, default=DEFAULT_F2G_AUDIT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_status(
        repo_root=args.repo_root,
        continuation_path=args.continuation_json,
        f2g_audit_path=args.f2g_audit_json,
    )
    output = args.output_json if args.output_json.is_absolute() else args.repo_root / args.output_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "f2h-lightweight-continuation-status: "
        f"status={payload['status']} "
        f"sequence={payload['summary']['observed_load_sequence']} "
        f"blockers={payload['summary']['blocker_count']}"
    )
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
