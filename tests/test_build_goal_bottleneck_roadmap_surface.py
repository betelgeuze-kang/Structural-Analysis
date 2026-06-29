from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_goal_bottleneck_roadmap_surface.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_goal_bottleneck_roadmap_surface", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _row_by_phase(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["roadmap_rows"]
    assert isinstance(rows, list)
    return {
        str(row["phase_id"]): row
        for row in rows
        if isinstance(row, dict) and "phase_id" in row
    }


def test_goal_bottleneck_roadmap_surface_exposes_goal_release_kpis() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    assert surface["schema_version"] == "goal-bottleneck-roadmap-surface.v1"
    assert surface["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert surface["contract_pass"] is True
    assert surface["read_model_ready"] is True
    assert surface["route"] == "/goal/bottleneck"
    assert surface["read_model"] == {
        "route": "/goal/bottleneck",
        "alternate_routes": ["/goal/roadmap"],
        "artifact": "implementation/phase1/release_evidence/productization/goal_bottleneck_roadmap_surface.json",
        "mutation_allowed": False,
    }

    kpis = surface["release_decision_kpis"]
    assert kpis == {
        "approval_token_count": 7,
        "blocked_release_count": 8,
        "broad_gpcr_family_claim_safe": False,
        "evidence_surface_count": 12,
        "first_blocker": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "locked_evidence_surface_count": 3,
        "operator_action_count": 16,
        "pocketmd_lite_product_surface_ready": False,
        "public_benchmark_ready": False,
        "release_allowed": False,
        "stale_artifact_count": 0,
    }
    assert surface["science_evidence_surface_bottlenecks"] == [
        "h_bond_evidence_surface_locked",
        "broad_gpcr_family_claim_locked",
        "pocketmd_lite_science_product_surface_locked",
    ]


def test_goal_bottleneck_roadmap_surface_links_phase_bottlenecks() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    rows = _row_by_phase(surface)

    assert rows["phase_0_source_of_truth_hardening"]["state"] == "ready"
    assert rows["phase_1_goal_release_cockpit"]["state"] == "ready"
    assert rows["phase_1_goal_release_cockpit"]["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )

    phase_2 = rows["phase_2_public_benchmark_harness"]
    assert phase_2["state"] == "blocked"
    assert phase_2["bottleneck"] == "public_benchmark_source_of_truth_not_ready"
    assert phase_2["first_blocker"] == "casf_pdbbind_source_material_not_attached"
    assert "attach_dud_e_lit_pcba_enrichment_intake" in phase_2["next_actions"]
    assert "attach_vina_gnina_comparison_intake" in phase_2["next_actions"]

    phase_3 = rows["phase_3_gpcr_hard_decoy_closure"]
    assert phase_3["state"] == "blocked"
    assert phase_3["bottleneck"] == "broad_gpcr_family_claim_locked"
    assert phase_3["first_blocked_target"] == "DRD2"
    assert phase_3["root_cause_tags"] == ["operator_values_required"]
    assert phase_3["linked_routes"] == ["/product/gpcr-hard-decoy-suite-report"]
    assert (
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json"
        in phase_3["evidence_artifacts"]
    )
    assert phase_3["summary"]["operator_intake_packet_status"] == "ready_for_operator_input"
    assert phase_3["summary"]["operator_intake_required_slot_count"] == 3
    assert "fill_gpcr_hard_decoy_operator_intake_packet" in phase_3["next_actions"]

    phase_4 = rows["phase_4_pocketmd_lite"]
    assert phase_4["state"] == "blocked"
    assert phase_4["bottleneck"] == "pocketmd_lite_science_product_surface_locked"
    assert phase_4["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_operator_intake_packet.json"
        in phase_4["evidence_artifacts"]
    )
    assert phase_4["summary"]["operator_intake_packet_status"] == (
        "ready_for_operator_input"
    )
    assert phase_4["summary"]["operator_intake_required_slot_count"] == 1
    assert "fill_pocketmd_lite_operator_intake_packet" in phase_4["next_actions"]
    assert "regenerate_goal_bottleneck_action_board" in phase_4["next_actions"]

    assert surface["primary_roadmap_bottleneck"] == "public_benchmark_source_of_truth_not_ready"
    assert surface["primary_roadmap_phase_id"] == "phase_2_public_benchmark_harness"


def test_goal_bottleneck_roadmap_surface_cli_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "productization" / "goal_bottleneck_roadmap_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["input_checksums"][
        "scripts/build_goal_bottleneck_roadmap_surface.py"
    ].startswith("sha256:")
    assert payload["reused_evidence"] is True
    assert payload["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert payload["primary_next_actions"][0] == "attach_checked_casf_pdbbind_subset_source_files"
