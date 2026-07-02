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
        "final_gate_count": 4,
        "final_gate_pass_count": 1,
        "final_gates": [
            {
                "item": "benchmark_results_clean_checkout_regenerated",
                "status": "ready",
                "contract_pass": True,
                "blockers": [],
                "evidence": "clean.json",
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
    }


def test_owner_packet_maps_blocked_developer_preview_gates(tmp_path: Path) -> None:
    rc_status = tmp_path / "developer_preview_rc_status.json"
    action_register = tmp_path / "docs/developer_preview_final_gate_action_register.md"
    _write_json(rc_status, _rc_status_payload())
    _write_text(action_register, "# Developer Preview Final Gate Action Register\n")
    _write_json(tmp_path / owner_packet.DEFAULT_UX_OBSERVATION_INTAKE, _ux_intake_payload())

    payload = owner_packet.build_owner_packet(
        repo_root=tmp_path,
        rc_status_path=rc_status,
        action_register_path=action_register,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["blocked_final_gate_count"] == 3
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
    assert "per_case_normalization_receipts" in packets[
        "selected_medium_models_pass_or_approved_review"
    ]["required_owner_evidence"]
    assert packets["linux_windows_reproducibility_confirmed"]["owner"] == (
        "release_reproducibility_owner"
    )
    assert "python3 scripts/build_phase6_linux_windows_parity_status.py --check" in (
        packets["linux_windows_reproducibility_confirmed"]["verification_commands"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "phase6_windows_platform_replay_receipt.json"
    ) in packets["linux_windows_reproducibility_confirmed"][
        "evidence_intake_artifacts"
    ]
    assert packets["new_user_core_workflow_observation_passed"]["owner"] == (
        "ux_research_owner"
    )
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
