from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_h_bond_backmap_operator_intake_packet.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_h_bond_backmap_operator_intake_packet",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_h_bond_backmap_operator_intake_packet_exposes_required_slots() -> None:
    packet = module.build_h_bond_backmap_operator_intake_packet(repo_root=REPO_ROOT)

    assert packet["schema_version"] == "h-bond-backmap-operator-intake-packet.v1"
    assert packet["status"] == "ready_for_operator_input"
    assert packet["contract_pass"] is True
    assert packet["claim_locked"] is True
    assert packet["owner_input_required"] is True
    assert packet["required_slot_count"] == 3
    assert [slot["slot_id"] for slot in packet["input_slots"]] == [
        "operator_attached_h_bond_backmap_cases",
        "contact_persistence_or_backmap_accuracy_rows",
        "reviewer_reproduction_command",
    ]
    assert packet["current_surface_status"]["status"] == "locked"
    assert packet["current_surface_status"]["locked"] is True
    assert packet["current_surface_status"]["blocker_count"] == 2
    assert packet["current_surface_status"]["required_receipts"] == [
        "operator_attached_h_bond_backmap_cases",
        "contact_persistence_or_backmap_accuracy_rows",
        "reviewer_reproduction_command",
    ]


def test_h_bond_backmap_operator_intake_packet_handoff_sequence() -> None:
    packet = module.build_h_bond_backmap_operator_intake_packet(repo_root=REPO_ROOT)

    assert [step["step_id"] for step in packet["handoff_sequence"]] == [
        "attach_h_bond_backmap_operator_receipts",
        "materialize_h_bond_backmap_evidence_rows",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
        "refresh_pm_release_gate_report",
    ]
    assert packet["acceptance_criteria"] == [
        "h_bond_backmap_evidence_surface.required_receipts are all attached",
        "h_bond_backmap_evidence_surface.blockers == []",
        "h_bond_backmap_evidence_surface.contract_pass == true",
        "h_bond_backmap_evidence_surface.locked == false",
        "h_bond_backmap_evidence_surface.claim_locked == false",
    ]
    assert packet["next_actions"][0] == "fill_h_bond_backmap_operator_intake_packet"
    assert packet["linked_artifacts"]["evidence_surface"] == (
        "implementation/phase1/release_evidence/surface/"
        "h_bond_backmap_evidence_surface.json"
    )


def test_h_bond_backmap_operator_intake_packet_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "h_bond_backmap_operator_intake_packet.json"
    out_md = tmp_path / "h_bond_backmap_operator_intake_packet.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["input_checksums"][
        "scripts/build_h_bond_backmap_operator_intake_packet.py"
    ].startswith("sha256:")
    assert payload["packet_id"] == "h_bond_backmap_operator_intake_packet"
    assert "# H-Bond BackMap Operator Intake Packet" in markdown
    assert "materialize_h_bond_backmap_evidence_rows" in markdown
