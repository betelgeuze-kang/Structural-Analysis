#!/usr/bin/env python3
"""Build the G1 consistent-Newton full-load checkpoint runner contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "g1-consistent-newton-full-load-checkpoint-candidate-runner.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_G1_LANE = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_CAUSE_NARROWING = PRODUCTIZATION / "g1_f2g_f2h_cause_narrowing_status.json"
DEFAULT_HIP_PROBE = PRODUCTIZATION / "mgt_residual_jacobian_consistency_hip_required_probe.json"
DEFAULT_GLOBAL_CONNECTIVITY = PRODUCTIZATION / "g1_global_connectivity_load_path_audit.json"
DEFAULT_OUT = PRODUCTIZATION / "g1_consistent_newton_full_load_checkpoint_candidate_runner.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

RUNNER_ID = "build_consistent_newton_full_load_checkpoint_candidate_runner"
PREFERRED_GENERATOR = "consistent_residual_jacobian_newton_rocm_full_load_candidate"
PRIMARY_NEXT_LANE = "consistent_residual_jacobian_newton_rocm_worker"
DISALLOWED_RETRY_ACTION_IDS = [
    "repeat_largest_rows_target128_support8_row_only_retuning",
]
CHECKPOINT_SCHEMA = "mgt-direct-residual-newton-state.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _strings(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item)]


def _find_runner_action(g1_lane: dict[str, Any]) -> dict[str, Any]:
    for row in _as_list(g1_lane.get("lane_next_actions")):
        if isinstance(row, dict) and row.get("id") == RUNNER_ID:
            return row
    return {}


def _cause_primary_next_lane(cause_narrowing: dict[str, Any], action: dict[str, Any]) -> str:
    decision = _as_dict(cause_narrowing.get("decision_record"))
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return str(
        action.get("cause_narrowing_primary_next_lane")
        or decision.get("primary_next_lane")
        or signals.get("global_connectivity_primary_next_lane")
        or ""
    )


def _row_only_loop_stopped(cause_narrowing: dict[str, Any], action: dict[str, Any]) -> bool:
    decision = _as_dict(cause_narrowing.get("decision_record"))
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return bool(
        action.get("cause_narrowing_row_only_correction_loop_stopped") is True
        or decision.get("stop_row_only_support_or_elastic_link_correction_loop") is True
        or signals.get("row_only_correction_loop_stopped_by_global_connectivity") is True
    )


def _support_or_link_gap_disfavored(
    cause_narrowing: dict[str, Any],
    action: dict[str, Any],
) -> bool:
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return bool(
        action.get("cause_narrowing_support_or_link_gap_disfavored") is True
        or signals.get("support_or_link_row_gap_disfavored") is True
    )


def _missing_artifact_blockers(
    *,
    g1_lane: dict[str, Any],
    cause_narrowing: dict[str, Any],
    hip_probe: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not g1_lane:
        blockers.append("g1_full_load_hip_newton_lane_report_missing")
    if not cause_narrowing:
        blockers.append("g1_f2g_f2h_cause_narrowing_status_missing")
    if not hip_probe:
        blockers.append("mgt_residual_jacobian_consistency_hip_required_probe_missing")
    return blockers


def _routing_blockers(
    *,
    action: dict[str, Any],
    cause_narrowing: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not action:
        blockers.append("consistent_newton_runner_next_action_missing")
        return blockers
    if action.get("preferred_candidate_generator") != PREFERRED_GENERATOR:
        blockers.append("consistent_newton_preferred_candidate_generator_missing")
    if _cause_primary_next_lane(cause_narrowing, action) != PRIMARY_NEXT_LANE:
        blockers.append("cause_narrowing_primary_next_lane_not_consistent_newton_rocm")
    if not _row_only_loop_stopped(cause_narrowing, action):
        blockers.append("row_only_correction_loop_not_stopped_by_cause_narrowing")
    if not _support_or_link_gap_disfavored(cause_narrowing, action):
        blockers.append("support_or_link_row_gap_not_disfavored")
    suppressed = set(_strings(action.get("suppressed_retry_action_ids")))
    for retry_id in DISALLOWED_RETRY_ACTION_IDS:
        if retry_id not in suppressed:
            blockers.append(f"disallowed_retry_not_suppressed:{retry_id}")
    return blockers


def _closure_blockers(
    *,
    g1_lane: dict[str, Any],
    hip_probe: dict[str, Any],
    worker: dict[str, Any],
) -> list[str]:
    checkpoint_gate = _as_dict(g1_lane.get("checkpoint_resolution_gate"))
    closure_blockers = [
        str(item) for item in _as_list(g1_lane.get("blockers")) if str(item)
    ]
    closure_blockers.extend(str(item) for item in _as_list(hip_probe.get("blockers")) if str(item))
    if checkpoint_gate.get("passed") is not True:
        closure_blockers.append("full_load_checkpoint_1p0_not_available")
    if hip_probe.get("consistent_residual_jacobian_newton_gate_passed") is not True:
        closure_blockers.append("consistent_residual_jacobian_newton_gate_not_passed")
    if worker.get("g1_closure_gate_ready") is not True:
        closure_blockers.append("production_rocm_hip_worker_g1_closure_gate_not_ready")
    seen: set[str] = set()
    unique: list[str] = []
    for blocker in closure_blockers:
        if blocker and blocker not in seen:
            seen.add(blocker)
            unique.append(blocker)
    return unique


def build_runner_packet(
    *,
    repo_root: Path = ROOT,
    g1_lane_path: Path = DEFAULT_G1_LANE,
    cause_narrowing_path: Path = DEFAULT_CAUSE_NARROWING,
    hip_probe_path: Path = DEFAULT_HIP_PROBE,
    global_connectivity_path: Path = DEFAULT_GLOBAL_CONNECTIVITY,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    g1_lane = _load_json(repo_root, g1_lane_path)
    cause_narrowing = _load_json(repo_root, cause_narrowing_path)
    hip_probe = _load_json(repo_root, hip_probe_path)
    global_connectivity = _load_json(repo_root, global_connectivity_path)
    action = _find_runner_action(g1_lane)
    checkpoint_gate = _as_dict(g1_lane.get("checkpoint_resolution_gate"))
    worker = _as_dict(hip_probe.get("production_rocm_hip_residual_jvp_worker"))
    terminal_partition = _as_dict(worker.get("terminal_gate_partition"))
    routing_blockers = _routing_blockers(action=action, cause_narrowing=cause_narrowing)
    contract_blockers = [
        *_missing_artifact_blockers(
            g1_lane=g1_lane,
            cause_narrowing=cause_narrowing,
            hip_probe=hip_probe,
        ),
        *routing_blockers,
    ]
    if worker and worker.get("residual_jvp_worker_path_ready") is not True:
        contract_blockers.append("production_rocm_hip_residual_jvp_worker_path_not_ready")
    contract_pass = bool(not contract_blockers)
    closure_blockers = _closure_blockers(
        g1_lane=g1_lane,
        hip_probe=hip_probe,
        worker=worker,
    )
    evidence_closure_pass = bool(
        contract_pass
        and checkpoint_gate.get("passed") is True
        and hip_probe.get("consistent_residual_jacobian_newton_gate_passed") is True
        and worker.get("g1_closure_gate_ready") is True
        and not closure_blockers
    )
    status = (
        "complete"
        if evidence_closure_pass
        else "ready_for_runner_implementation"
        if contract_pass
        else "blocked_runner_contract"
    )
    required_load_scale = _as_float(
        checkpoint_gate.get("required_load_scale")
        or action.get("required_load_scale")
        or 1.0,
        1.0,
    )
    highest_observed = _as_float(
        checkpoint_gate.get("highest_observed_load_scale")
        or action.get("highest_observed_load_scale")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py"),
                g1_lane_path,
                cause_narrowing_path,
                hip_probe_path,
                global_connectivity_path,
            ],
            reused_evidence=True,
            reuse_policy=(
                "consistent_newton_full_load_runner_contract_from_g1_lane_and_cause_narrowing"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "evidence_closure_pass": evidence_closure_pass,
        "promotes_g1_closure": False,
        "summary_line": (
            "G1 consistent Newton full-load runner contract: "
            f"{status.upper()} | contract_pass={contract_pass} | "
            f"observed_load={highest_observed:g}/{required_load_scale:g} | "
            f"closure_blockers={len(closure_blockers)}"
        ),
        "runner_contract": {
            "runner_id": RUNNER_ID,
            "preferred_candidate_generator": PREFERRED_GENERATOR,
            "primary_next_lane": PRIMARY_NEXT_LANE,
            "required_checkpoint_schema": CHECKPOINT_SCHEMA,
            "required_load_scale": required_load_scale,
            "disallowed_retry_action_ids": list(DISALLOWED_RETRY_ACTION_IDS),
            "required_inputs": [
                g1_lane_path.as_posix(),
                cause_narrowing_path.as_posix(),
                hip_probe_path.as_posix(),
                global_connectivity_path.as_posix(),
            ],
            "acceptance_criteria": [
                "loadable_checkpoint_schema_mgt_direct_residual_newton_state_v1",
                "checkpoint_load_scale_gte_1p0",
                "no_load_path_provenance_contradiction",
                "direct_residual_gate_passes_without_regularized_fixed_point_substitute",
                "consistent_residual_jacobian_newton_gate_passes",
                "production_rocm_hip_residual_jvp_worker_has_no_cpu_fallback",
                "device_resident_residual_jvp_rows_retained",
                "g1_full_load_hip_newton_lane_report_contract_passes_after_rerun",
            ],
            "prohibited_substitutes": [
                "row_only_largest_rows_retuning_replay",
                "support_or_elastic_link_pin_without_cause_receipt",
                "regularized_fixed_point_residual_used_as_physical_residual",
                "cpu_diagnostic_assembler_or_cpu_fallback_hip_claim",
                "full_load_claim_from_sub_full_load_checkpoint",
            ],
            "rerun_command": (
                action.get("rerun_command")
                or "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
        },
        "routing_evidence": {
            "runner_next_action_present": bool(action),
            "routing_reason": str(action.get("reason") or action.get("routing_reason") or ""),
            "preferred_candidate_generator": str(
                action.get("preferred_candidate_generator") or ""
            ),
            "cause_narrowing_primary_next_lane": _cause_primary_next_lane(
                cause_narrowing,
                action,
            ),
            "row_only_correction_loop_stopped": _row_only_loop_stopped(
                cause_narrowing,
                action,
            ),
            "support_or_link_row_gap_disfavored": _support_or_link_gap_disfavored(
                cause_narrowing,
                action,
            ),
            "suppressed_retry_action_ids": _strings(
                action.get("suppressed_retry_action_ids")
            ),
            "global_connectivity_status": str(global_connectivity.get("status") or ""),
            "cause_narrowing_status": str(cause_narrowing.get("status") or ""),
        },
        "checkpoint_gap": {
            "checkpoint_resolution_passed": checkpoint_gate.get("passed") is True,
            "required_load_scale": required_load_scale,
            "highest_observed_load_scale": highest_observed,
            "highest_observed_gap_to_required_load_scale": _as_float(
                checkpoint_gate.get("highest_observed_gap_to_required_load_scale")
                or action.get("highest_observed_gap_to_required_load_scale")
            ),
            "full_load_candidate_count": _as_int(
                checkpoint_gate.get("full_load_candidate_count")
                or action.get("workspace_full_load_candidate_count")
            ),
            "workspace_candidate_count": _as_int(action.get("workspace_candidate_count")),
            "workspace_scan_root": str(action.get("workspace_scan_root") or ""),
        },
        "hip_worker_contract": {
            "worker_id": str(worker.get("worker_id") or ""),
            "residual_jvp_worker_path_ready": worker.get(
                "residual_jvp_worker_path_ready"
            )
            is True,
            "g1_closure_gate_ready": worker.get("g1_closure_gate_ready") is True,
            "consistent_residual_jacobian_newton_gate_passed": hip_probe.get(
                "consistent_residual_jacobian_newton_gate_passed"
            )
            is True,
            "cpu_diagnostic_assembler_used": hip_probe.get(
                "cpu_diagnostic_assembler_used"
            )
            is True,
            "production_hip_residual_jacobian_path": hip_probe.get(
                "production_hip_residual_jacobian_path"
            )
            is True,
            "terminal_gate_partition": terminal_partition,
            "worker_blockers": _strings(worker.get("blockers")),
        },
        "verification_commands": [
            (
                "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
            (
                "python3 scripts/build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py "
                "--fail-blocked"
            ),
            "python3 scripts/build_structural_product_development_roadmap.py",
        ],
        "blockers": contract_blockers,
        "closure_blockers": closure_blockers,
        "artifacts": {
            "g1_full_load_hip_newton_lane_report": g1_lane_path.as_posix(),
            "g1_f2g_f2h_cause_narrowing_status": cause_narrowing_path.as_posix(),
            "mgt_residual_jacobian_consistency_hip_required_probe": hip_probe_path.as_posix(),
            "g1_global_connectivity_load_path_audit": global_connectivity_path.as_posix(),
        },
        "claim_boundary": (
            "This packet defines the next G1 runner contract for generating a "
            "consistent residual/Jacobian Newton full-load checkpoint candidate. "
            "It does not create the checkpoint, close the consistent Newton gate, "
            "prove full-load 1.0 equilibrium, promote G1 closure, or allow an "
            "exhausted row-only support/link retuning loop to count as progress."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    contract = _as_dict(payload.get("runner_contract"))
    checkpoint = _as_dict(payload.get("checkpoint_gap"))
    hip = _as_dict(payload.get("hip_worker_contract"))
    lines = [
        "# G1 Consistent Newton Full-Load Runner Contract",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `runner_id`: `{contract.get('runner_id')}`",
        f"- `preferred_candidate_generator`: `{contract.get('preferred_candidate_generator')}`",
        f"- `observed_load`: `{checkpoint.get('highest_observed_load_scale')}`",
        f"- `required_load_scale`: `{checkpoint.get('required_load_scale')}`",
        f"- `worker_path_ready`: `{hip.get('residual_jvp_worker_path_ready')}`",
        f"- `worker_g1_closure_gate_ready`: `{hip.get('g1_closure_gate_ready')}`",
        "",
        "## Acceptance Criteria",
        "",
    ]
    for item in _as_list(contract.get("acceptance_criteria")):
        lines.append(f"- `{item}`")
    if payload["blockers"]:
        lines.extend(["", "## Contract Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    if payload["closure_blockers"]:
        lines.extend(["", "## Closure Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["closure_blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_runner_packet(
    *,
    repo_root: Path = ROOT,
    g1_lane_path: Path = DEFAULT_G1_LANE,
    cause_narrowing_path: Path = DEFAULT_CAUSE_NARROWING,
    hip_probe_path: Path = DEFAULT_HIP_PROBE,
    global_connectivity_path: Path = DEFAULT_GLOBAL_CONNECTIVITY,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_runner_packet(
        repo_root=repo_root,
        g1_lane_path=g1_lane_path,
        cause_narrowing_path=cause_narrowing_path,
        hip_probe_path=hip_probe_path,
        global_connectivity_path=global_connectivity_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--g1-lane", type=Path, default=DEFAULT_G1_LANE)
    parser.add_argument("--cause-narrowing", type=Path, default=DEFAULT_CAUSE_NARROWING)
    parser.add_argument("--hip-probe", type=Path, default=DEFAULT_HIP_PROBE)
    parser.add_argument("--global-connectivity", type=Path, default=DEFAULT_GLOBAL_CONNECTIVITY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_runner_packet(
        repo_root=args.repo_root,
        g1_lane_path=args.g1_lane,
        cause_narrowing_path=args.cause_narrowing,
        hip_probe_path=args.hip_probe,
        global_connectivity_path=args.global_connectivity,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
