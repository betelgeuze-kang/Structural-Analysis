from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_developer_preview_final_gate_owner_packet.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_developer_preview_final_gate_owner_packet", SCRIPT_PATH
)
assert SPEC is not None
owner_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = owner_packet
SPEC.loader.exec_module(owner_packet)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rc_status_payload() -> dict:
    return {
        "schema_version": "developer-preview-rc-status.v1",
        "status": "blocked",
        "contract_pass": False,
        "final_gate_count": 5,
        "final_gate_pass_count": 2,
        "final_gates": [
            {
                "item": "benchmark_results_clean_checkout_regenerated",
                "status": "ready",
                "contract_pass": True,
                "blockers": [],
                "evidence": "clean.json",
            },
            {
                "item": "silent_import_loss_zero",
                "status": "ready",
                "contract_pass": True,
                "blockers": [],
                "evidence": "ifc.json",
            },
            {
                "item": "selected_medium_models_pass_or_approved_review",
                "status": "blocked",
                "contract_pass": False,
                "blockers": [
                    "medium_structural_models_current_below_required:0/5",
                    "normalization_receipts_missing",
                ],
                "evidence": "medium.json; scale.json",
            },
            {
                "item": "linux_windows_reproducibility_confirmed",
                "status": "blocked",
                "contract_pass": False,
                "blockers": ["platform_replay_receipt_missing:windows"],
                "evidence": "parity.json",
            },
            {
                "item": "new_user_core_workflow_observation_passed",
                "status": "blocked",
                "contract_pass": False,
                "blockers": ["human_new_user_observation_not_passed"],
                "evidence": "ux_report.json; ux_intake.json",
            },
        ],
    }


def _ux_intake_payload() -> dict:
    return {
        "schema_version": "ux-new-user-observation-intake-packet.v1",
        "status": "blocked",
        "contract_pass": False,
        "release_area_blocker_ids": [
            "pm_release::ux::human_new_user_observation_missing_or_failed",
            "pm_release::ux::human_new_user_30min_sample_evidence_missing",
        ],
        "developer_preview_blocker_ids": [
            "developer_preview_rc::new_user_core_workflow_observation_passed",
        ],
        "product_readiness_blocker_ids": [
            "human_ux::observation_file_missing",
        ],
        "blocker_ids": [
            "developer_preview_rc::new_user_core_workflow_observation_passed",
            "pm_release::ux::human_new_user_observation_missing_or_failed",
            "pm_release::ux::human_new_user_30min_sample_evidence_missing",
            "human_ux::observation_file_missing",
            "ux_new_user_observation::observation_file_missing",
        ],
        "evidence_intake_artifacts": [
            "docs/templates/ux_new_user_observation.template.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json",
            "implementation/phase1/release_evidence/productization/phase6_ux_observation_status.json",
            "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
            "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
            "implementation/phase1/release_evidence/productization/developer_preview_rc_status.json",
        ],
        "human_observation_evidence_policy": {
            "accepted_evidence": [
                "human-observed 30-minute new-user workflow record",
            ],
            "rejected_substitutes": [
                "automated browser smoke or task-based UX rehearsal without human observation",
            ],
            "closure_rule": "Close only from a real human 30-minute new-user sample.",
        },
        "gate_unblock_plan": [
            {
                "slot_id": "attach_observation_record",
                "required_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "ux_new_user_observation.json"
                ),
                "minimum_evidence": ["real human observation record"],
            },
        ],
        "validation_commands": [
            (
                "python3 scripts/build_ux_new_user_observation_intake_packet.py "
                "--out implementation/phase1/release_evidence/productization/"
                "ux_new_user_observation_intake_packet.json"
            ),
        ],
    }


def _write_upstream_handoff_artifacts(repo_root: Path) -> None:
    productization = repo_root / "implementation/phase1/release_evidence/productization"
    _write_json(
        productization / "phase3_medium_model_scorecard_readiness_receipt.json",
        {
            "schema_version": "phase3-medium-model-scorecard-readiness-receipt.v1",
            "status": "blocked",
            "contract_pass": False,
            "summary_line": "Phase 3 medium: BLOCKED",
            "blockers": ["opensees_medium_scorecard_execution_missing"],
            "gate_unblock_plan": [
                {
                    "slot_id": "run_medium_scorecard_receipts",
                    "owner": "benchmark_operator",
                    "minimum_evidence": ["one scorecard receipt per selected case"],
                    "validation_commands": [
                        (
                            "python3 scripts/build_phase3_medium_model_scorecard_"
                            "readiness_receipt.py --check"
                        )
                    ],
                },
            ],
            "validation_commands": [
                "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
            ],
            "missing_evidence_breakdown": [
                {"id": "scorecard_execution", "blocker": "opensees_medium_scorecard_execution_missing"},
            ],
            "runner_command_template": (
                "python3 scripts/run_phase3_medium_model_scorecard_receipt.py "
                "--model OPERATOR_ATTACHED_MODEL.json"
            ),
            "case_input_requirements": {
                "required_case_count": 5,
                "remaining_case_count": 5,
            },
        },
    )
    _write_json(
        productization / "phase6_linux_windows_parity_status.json",
        {
            "schema_version": "phase6-linux-windows-parity-status.v1",
            "status": "blocked",
            "contract_pass": False,
            "summary_line": "Phase 6 Linux/Windows parity: BLOCKED",
            "blockers": ["platform_replay_receipt_missing:windows"],
            "gate_unblock_plan": [
                {
                    "slot_id": "attach_windows_platform_replay_receipt",
                    "platform": "windows",
                    "required_artifact": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase6_windows_platform_replay_receipt.json"
                    ),
                    "minimum_evidence": ["Windows replay receipt exists"],
                },
            ],
            "validation_commands": [
                "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
            ],
        },
    )


def test_owner_packet_maps_blocked_developer_preview_gates(tmp_path: Path) -> None:
    rc_status = tmp_path / "developer_preview_rc_status.json"
    action_register = tmp_path / "docs/developer_preview_final_gate_action_register.md"
    _write_json(rc_status, _rc_status_payload())
    _write_text(action_register, "# Developer Preview Final Gate Action Register\n")
    _write_json(tmp_path / owner_packet.DEFAULT_UX_OBSERVATION_INTAKE, _ux_intake_payload())
    _write_upstream_handoff_artifacts(tmp_path)

    payload = owner_packet.build_owner_packet(
        repo_root=tmp_path,
        rc_status_path=rc_status,
        action_register_path=action_register,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["blocked_final_gate_count"] == 3
    assert payload["nearest_abf_slice_summary"] == {
        "slice_count": 3,
        "ready_count": 2,
        "blocked_count": 1,
        "ready_slice_ids": ["A", "B"],
        "blocked_slice_ids": ["F"],
        "blocked_gates": ["new_user_core_workflow_observation_passed"],
        "completion_ratio": 0.6667,
        "claim_boundary": (
            "A/B/F slice tracking only reports current DP final-gate state. "
            "It does not create missing human observation, benchmark, or "
            "platform replay evidence and does not promote Developer Preview."
        ),
    }
    nearest = {
        row["slice_id"]: row for row in payload["nearest_abf_slice"]
    }
    assert nearest["A"]["ready_for_dp_final_gate"] is True
    assert nearest["B"]["ready_for_dp_final_gate"] is True
    assert nearest["F"]["ready_for_dp_final_gate"] is False
    assert nearest["F"]["owner_review_required"] is True
    assert nearest["F"]["owner"] == "ux_research_owner"
    assert nearest["F"]["owner_unblock_slot_ids"] == ["attach_observation_record"]
    assert payload["owner_packet_count"] == 3
    assert payload["owner_packet_gate_ids"] == [
        "selected_medium_models_pass_or_approved_review",
        "linux_windows_reproducibility_confirmed",
        "new_user_core_workflow_observation_passed",
    ]
    assert payload["owner_packet_blocker_id_count"] == 10
    assert "developer_preview_rc::new_user_core_workflow_observation_passed" in (
        payload["owner_packet_blocker_ids"]
    )
    assert payload["release_surface_impact_count"] == 8
    assert payload["evidence_intake_artifact_count"] == 12
    assert payload["evidence_refresh_command_count"] == 12
    assert payload["owner_unblock_plan_count"] == 3
    packets = {packet["gate"]: packet for packet in payload["owner_packets"]}
    assert packets["selected_medium_models_pass_or_approved_review"]["gate_id"] == (
        "selected_medium_models_pass_or_approved_review"
    )
    assert packets["selected_medium_models_pass_or_approved_review"][
        "current_evidence_gap_state"
    ] == "owner_evidence_required"
    assert packets["selected_medium_models_pass_or_approved_review"][
        "current_blocker_count"
    ] == 2
    assert packets["selected_medium_models_pass_or_approved_review"]["owner"] == (
        "benchmark_validation_owner"
    )
    assert packets["selected_medium_models_pass_or_approved_review"][
        "upstream_handoff_source_count"
    ] == 1
    assert packets["selected_medium_models_pass_or_approved_review"][
        "upstream_handoff_sources"
    ][0]["present"] is True
    assert packets["selected_medium_models_pass_or_approved_review"][
        "owner_unblock_slot_ids"
    ] == ["run_medium_scorecard_receipts"]
    assert "run_phase3_medium_model_scorecard_receipt.py" in packets[
        "selected_medium_models_pass_or_approved_review"
    ]["upstream_handoff_sources"][0]["runner_command_template"]
    assert "per_case_normalization_receipts" in packets[
        "selected_medium_models_pass_or_approved_review"
    ]["required_owner_evidence"]
    assert packets["linux_windows_reproducibility_confirmed"]["owner"] == (
        "release_reproducibility_owner"
    )
    assert "python3 scripts/build_phase6_linux_windows_parity_status.py --check" in (
        packets["linux_windows_reproducibility_confirmed"]["verification_commands"]
    )
    assert packets["linux_windows_reproducibility_confirmed"][
        "owner_unblock_slot_ids"
    ] == ["attach_windows_platform_replay_receipt"]
    assert (
        "implementation/phase1/release_evidence/productization/"
        "phase6_windows_platform_replay_receipt.json"
    ) in packets["linux_windows_reproducibility_confirmed"][
        "evidence_intake_artifacts"
    ]
    assert packets["new_user_core_workflow_observation_passed"]["owner"] == (
        "ux_research_owner"
    )
    assert packets["new_user_core_workflow_observation_passed"][
        "owner_unblock_slot_ids"
    ] == ["attach_observation_record"]
    assert "automated_browser_smoke_without_human_observation" in packets[
        "new_user_core_workflow_observation_passed"
    ]["prohibited_substitutes"]
    assert "pm_release::ux::human_new_user_observation_missing_or_failed" in packets[
        "new_user_core_workflow_observation_passed"
    ]["release_surface_impacts"]
    assert "pm_release::ux::human_new_user_30min_sample_evidence_missing" in packets[
        "new_user_core_workflow_observation_passed"
    ]["release_surface_impacts"]
    assert "pm_release::ux::human_new_user_30min_sample_evidence_missing" in packets[
        "new_user_core_workflow_observation_passed"
    ]["blocker_ids"]
    assert "human_ux::observation_file_missing" in packets[
        "new_user_core_workflow_observation_passed"
    ]["blocker_ids"]
    assert "ux_new_user_observation::observation_file_missing" in packets[
        "new_user_core_workflow_observation_passed"
    ]["blocker_ids"]
    assert "docs/templates/ux_new_user_observation.template.json" in packets[
        "new_user_core_workflow_observation_passed"
    ]["evidence_intake_artifacts"]
    assert (
        "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json"
        in packets["new_user_core_workflow_observation_passed"]["evidence_intake_artifacts"]
    )
    assert packets["new_user_core_workflow_observation_passed"]["upstream_intake_status"] == "blocked"
    assert packets["new_user_core_workflow_observation_passed"]["upstream_intake_blocker_id_count"] == 5
    assert packets["new_user_core_workflow_observation_passed"]["human_observation_evidence_policy"][
        "closure_rule"
    ] == "Close only from a real human 30-minute new-user sample."


def test_owner_packet_blocks_missing_action_register(tmp_path: Path) -> None:
    rc_status = tmp_path / "developer_preview_rc_status.json"
    _write_json(rc_status, _rc_status_payload())

    payload = owner_packet.build_owner_packet(
        repo_root=tmp_path,
        rc_status_path=rc_status,
        action_register_path=tmp_path / "missing.md",
    )

    assert payload["status"] == "blocked_handoff"
    assert payload["contract_pass"] is False
    assert "developer_preview_final_gate_action_register_missing" in payload["blockers"]


def test_owner_packet_writes_json_and_markdown(tmp_path: Path) -> None:
    rc_status = tmp_path / "developer_preview_rc_status.json"
    action_register = tmp_path / "docs/developer_preview_final_gate_action_register.md"
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"
    _write_json(rc_status, _rc_status_payload())
    _write_text(action_register, "# Developer Preview Final Gate Action Register\n")
    _write_json(tmp_path / owner_packet.DEFAULT_UX_OBSERVATION_INTAKE, _ux_intake_payload())
    _write_upstream_handoff_artifacts(tmp_path)

    payload = owner_packet.write_owner_packet(
        repo_root=tmp_path,
        rc_status_path=rc_status,
        action_register_path=action_register,
        out=out,
        out_md=out_md,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        owner_packet.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Developer Preview Final Gate Owner Packet" in markdown
    assert "selected_medium_models_pass_or_approved_review" in markdown
    assert "## Evidence Intake Artifacts" in markdown
    assert "## Human Observation Evidence Policy" in markdown
    assert "## Blocker IDs" in markdown
    assert "## Release Surface Impacts" in markdown
    assert "## Evidence Refresh Commands" in markdown
    assert "## Nearest A/B/F Slice" in markdown
    assert "`nearest_abf_ready_count`: `2/3`" in markdown
    assert "## Gate Unblock Plan" in markdown
    assert "## Upstream Handoff Sources" in markdown
