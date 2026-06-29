from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_operator_intake_packet.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_operator_intake_packet",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_gpcr_hard_decoy_operator_intake_packet_exposes_required_targets() -> None:
    packet = module.build_gpcr_hard_decoy_operator_intake_packet(repo_root=REPO_ROOT)

    assert packet["schema_version"] == "gpcr-hard-decoy-operator-intake-packet.v1"
    assert packet["status"] == "ready_for_operator_input"
    assert packet["contract_pass"] is True
    assert packet["read_model_ready"] is True
    assert packet["route"] == "/product/gpcr-hard-decoy-suite-report/operator-intake"
    assert packet["read_model"] == {
        "route": "/product/gpcr-hard-decoy-suite-report/operator-intake",
        "alternate_routes": [
            "/product/gpcr-hard-decoy-suite-report",
            "/product/capabilities",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_operator_intake_packet.json"
        ),
        "mutation_allowed": False,
    }
    assert packet["broad_gpcr_family_claim_safe"] is False
    assert packet["owner_input_required"] is True
    assert packet["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert packet["required_operator_fields"] == [
        "target_id",
        "ranking_pr_auc_ci_low",
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
    ]
    assert packet["exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert [slot["target_id"] for slot in packet["target_slots"]] == [
        "DRD2",
        "HTR2A",
        "OPRM1",
    ]
    assert packet["current_suite_status"]["first_blocked_target"] == "DRD2"
    assert packet["current_suite_status"]["blocker_count"] == 12


def test_gpcr_hard_decoy_operator_intake_packet_materialization_sequence() -> None:
    packet = module.build_gpcr_hard_decoy_operator_intake_packet(repo_root=REPO_ROOT)

    assert [step["step_id"] for step in packet["materialization_sequence"]] == [
        "fill_gpcr_hard_decoy_operator_template",
        "materialize_gpcr_hard_decoy_suite_report",
        "refresh_gpcr_hard_decoy_product_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert packet["acceptance_criteria"] == [
        "gpcr_hard_decoy_suite_report.target_pass_count == 3",
        "gpcr_hard_decoy_suite_report.broad_gpcr_family_claim_safe == true",
        "gpcr_hard_decoy_suite_report.blockers == []",
        "gpcr_hard_decoy_product_report.science_claim_status == ready",
        "gpcr_hard_decoy_evidence_surface.locked == false",
    ]
    assert packet["next_actions"][0] == "fill_gpcr_hard_decoy_operator_intake_packet"
    assert packet["linked_artifacts"]["operator_template"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_operator_template.json"
    )


def test_gpcr_hard_decoy_operator_intake_packet_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "gpcr_hard_decoy_operator_intake_packet.json"
    out_md = tmp_path / "gpcr_hard_decoy_operator_intake_packet.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["input_checksums"][
        "scripts/build_gpcr_hard_decoy_operator_intake_packet.py"
    ].startswith("sha256:")
    assert payload["packet_id"] == "gpcr_hard_decoy_operator_intake_packet"
    assert "# GPCR Hard-Decoy Operator Intake Packet" in markdown
    assert "materialize_gpcr_hard_decoy_suite_report" in markdown
