from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_consistent_newton_full_load_checkpoint_candidate_runner", SCRIPT_PATH
)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _g1_lane_payload(*, action_id: str | None = runner.RUNNER_ID) -> dict:
    actions = []
    if action_id is not None:
        actions.append(
            {
                "id": action_id,
                "reason": "row_only_largest_rows_operator_exhausted",
                "preferred_candidate_generator": runner.PREFERRED_GENERATOR,
                "required_load_scale": 1.0,
                "highest_observed_load_scale": 0.656,
                "highest_observed_gap_to_required_load_scale": 0.344,
                "workspace_candidate_count": 357,
                "workspace_full_load_candidate_count": 0,
                "workspace_scan_root": "implementation/phase1/release_evidence/productization",
                "cause_narrowing_primary_next_lane": runner.PRIMARY_NEXT_LANE,
                "cause_narrowing_row_only_correction_loop_stopped": True,
                "cause_narrowing_support_or_link_gap_disfavored": True,
                "cause_narrowing_support_or_link_row_gap_disfavored": True,
                "suppressed_retry_action_ids": runner.DISALLOWED_RETRY_ACTION_IDS,
                "rerun_command": (
                    "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                    "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
                ),
            }
        )
    return {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "status": "blocked",
        "contract_pass": False,
        "blockers": [
            "checkpoint_load_scale_below_required_full_load",
            "checkpoint_resolution_no_full_load_candidate",
            "hip_consistency_proof_gate_not_passed",
        ],
        "checkpoint_resolution_gate": {
            "mode": "auto_select",
            "passed": False,
            "required_load_scale": 1.0,
            "highest_observed_load_scale": 0.656,
            "highest_observed_gap_to_required_load_scale": 0.344,
            "full_load_candidate_count": 0,
        },
        "lane_next_actions": actions,
    }


def _cause_narrowing_payload() -> dict:
    return {
        "schema_version": "g1-f2g-f2h-cause-narrowing-status.v1",
        "status": "ready",
        "contract_pass": True,
        "evidence_signals": {
            "support_or_link_row_gap_disfavored": True,
            "row_only_correction_loop_stopped_by_global_connectivity": True,
            "global_connectivity_primary_next_lane": runner.PRIMARY_NEXT_LANE,
        },
        "decision_record": {
            "schema_version": "g1-f2g-f2h-next-lane-decision.v1",
            "primary_next_lane": runner.PRIMARY_NEXT_LANE,
            "stop_row_only_support_or_elastic_link_correction_loop": True,
            "required_next_receipts": [
                "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
                "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
            ],
        },
    }


def _hip_probe_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "partial",
        "consistent_residual_jacobian_newton_gate_passed": False,
        "cpu_diagnostic_assembler_used": False,
        "production_hip_residual_jacobian_path": True,
        "blockers": [
            "consistent_residual_jacobian::consistent_residual_jacobian_newton_not_proven",
            "production_rocm_hip_residual_jvp_worker::consistent_residual_jacobian_newton_gate_not_passed",
        ],
        "production_rocm_hip_residual_jvp_worker": {
            "schema_version": "production-rocm-hip-residual-jvp-worker-contract.v1",
            "worker_id": runner.PRIMARY_NEXT_LANE,
            "ready": False,
            "status": "blocked",
            "blockers": ["consistent_residual_jacobian_newton_gate_not_passed"],
            "residual_jvp_worker_path_ready": True,
            "residual_jvp_worker_path_blockers": [],
            "g1_closure_gate_ready": False,
            "g1_closure_gate_blockers": [
                "consistent_residual_jacobian_newton_gate_not_passed"
            ],
            "terminal_gate_partition": {
                "checkpoint_gate": {
                    "load_scale": 0.656,
                    "full_load_candidate": False,
                    "gap_to_full_load": 0.344,
                },
                "direct_residual_gate": {
                    "passed": False,
                    "relative_increment_gate_passed": True,
                },
            },
        },
    }


def _global_connectivity_payload() -> dict:
    return {
        "schema_version": "g1-global-connectivity-load-path-audit.v1",
        "status": "ready",
        "decision_record": {
            "primary_next_lane": runner.PRIMARY_NEXT_LANE,
            "row_only_correction_loop_stopped": True,
        },
    }


def _write_inputs(tmp_path: Path, *, action_id: str | None = runner.RUNNER_ID) -> dict[str, Path]:
    paths = {
        "g1_lane": tmp_path / "g1_full_load_hip_newton_lane_report.json",
        "cause": tmp_path / "g1_f2g_f2h_cause_narrowing_status.json",
        "hip": tmp_path / "mgt_residual_jacobian_consistency_hip_required_probe.json",
        "global": tmp_path / "g1_global_connectivity_load_path_audit.json",
    }
    _write_json(paths["g1_lane"], _g1_lane_payload(action_id=action_id))
    _write_json(paths["cause"], _cause_narrowing_payload())
    _write_json(paths["hip"], _hip_probe_payload())
    _write_json(paths["global"], _global_connectivity_payload())
    return paths


def test_runner_packet_is_ready_for_implementation_without_promoting_g1(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
    )

    assert payload["status"] == "ready_for_runner_implementation"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["promotes_g1_closure"] is False
    assert payload["runner_contract"]["runner_id"] == runner.RUNNER_ID
    assert (
        payload["runner_contract"]["preferred_candidate_generator"]
        == runner.PREFERRED_GENERATOR
    )
    assert runner.DISALLOWED_RETRY_ACTION_IDS[0] in payload["runner_contract"][
        "disallowed_retry_action_ids"
    ]
    assert payload["routing_evidence"]["row_only_correction_loop_stopped"] is True
    assert payload["routing_evidence"]["support_or_link_row_gap_disfavored"] is True
    assert payload["checkpoint_gap"]["highest_observed_load_scale"] == 0.656
    assert payload["hip_worker_contract"]["residual_jvp_worker_path_ready"] is True
    assert payload["hip_worker_contract"]["g1_closure_gate_ready"] is False
    assert "checkpoint_load_scale_gte_1p0" in payload["runner_contract"][
        "acceptance_criteria"
    ]
    assert "consistent_residual_jacobian_newton_gate_not_passed" in payload[
        "closure_blockers"
    ]


def test_runner_packet_blocks_when_lane_does_not_route_to_runner(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path, action_id="generate_full_load_1p0_checkpoint_candidate")

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
    )

    assert payload["status"] == "blocked_runner_contract"
    assert payload["contract_pass"] is False
    assert "consistent_newton_runner_next_action_missing" in payload["blockers"]


def test_runner_packet_writes_json_and_markdown(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    out = tmp_path / "runner.json"
    out_md = tmp_path / "runner.md"

    payload = runner.write_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        runner.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# G1 Consistent Newton Full-Load Runner Contract" in markdown
    assert runner.RUNNER_ID in markdown
    assert payload["status"] == "ready_for_runner_implementation"
