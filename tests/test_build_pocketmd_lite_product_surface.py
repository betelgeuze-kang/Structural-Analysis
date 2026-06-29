from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pocketmd_lite_product_surface.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_pocketmd_lite_product_surface", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

pm_spec = importlib.util.spec_from_file_location("report_pm_release_gate", PM_REPORT_PATH)
assert pm_spec is not None
pm_report = importlib.util.module_from_spec(pm_spec)
assert pm_spec.loader is not None
sys.modules[pm_spec.name] = pm_report
pm_spec.loader.exec_module(pm_report)


def test_pocketmd_lite_contract_keeps_broad_md_and_fep_locked() -> None:
    artifacts = module.build_pocketmd_lite_artifacts(repo_root=REPO_ROOT)
    contract = artifacts["contract"]
    survival = artifacts["topk_survival_report"]
    api = artifacts["readonly_api"]
    handoff = artifacts["delivery_handoff"]
    operator = artifacts["operator_intake_packet"]
    surface = artifacts["surface"]

    assert contract["schema_version"] == "pocketmd-lite-contract.v1"
    assert contract["contract_pass"] is True
    assert contract["product_surface_ready"] is False
    assert contract["scope"] == "top_k_lite_refinement_only"
    assert contract["top_k_policy"]["requires_upstream_ranked_candidates"] is True
    assert {
        "local_min_survival_rate",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_relief_rate",
        "uncertainty_width_median",
    } == {row["metric_id"] for row in contract["reported_metrics"]}
    assert "free_energy_perturbation_claim" in contract["blocked_claims"]
    assert "broad_all_atom_md_claim" in contract["blocked_claims"]
    assert contract["materializer"] == {
        "schema_version": "pocketmd-lite-topk-survival-materialization.v1",
        "script": "scripts/materialize_pocketmd_lite_topk_survival_report.py",
        "status": "ready_for_operator_intake",
        "input_contract": (
            "implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json"
        ),
        "required_intake_key": "cases",
        "outputs": {
            "topk_survival_report": (
                "implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_topk_survival_report.json"
            ),
            "science_product_surface": (
                "implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json"
            ),
        },
        "command": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            "--intake <operator-pocketmd-lite-intake.json> "
            "--contract implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_contract.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_survival_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json "
            "--fail-blocked"
        ),
    }

    assert survival["schema_version"] == "pocketmd-lite-topk-survival-report.v1"
    assert survival["contract_pass"] is False
    assert survival["real_refinement_case_count"] == 0
    assert survival["summary"]["local_min_survival_rate"] is None
    assert "pocketmd_lite_topk_candidate_rows_missing" in survival["blockers"]
    assert "uncertainty_width_median" in survival["required_metrics"]
    assert survival["materializer"]["status"] == "ready_for_operator_intake"

    assert api["schema_version"] == "pocketmd-lite-readonly-api.v1"
    assert api["contract_pass"] is True
    assert api["mutation_allowed"] is False
    assert {row["method"] for row in api["endpoints"]} == {"GET"}
    assert "write_operator_evidence" in api["forbidden_operations"]

    assert handoff["schema_version"] == "pocketmd-lite-delivery-handoff.v1"
    assert handoff["contract_pass"] is True
    assert handoff["evidence_artifacts"]["operator_intake_packet"].endswith(
        "pocketmd_lite_operator_intake_packet.json"
    )
    assert "topk_survival_report.real_refinement_case_count > 0" in handoff[
        "acceptance_criteria"
    ]

    assert operator["schema_version"] == "pocketmd-lite-operator-intake-packet.v1"
    assert operator["status"] == "ready_for_operator_input"
    assert operator["contract_pass"] is True
    assert operator["owner_input_required"] is True
    assert operator["product_surface_ready"] is False
    assert operator["broad_all_atom_md_claim_safe"] is False
    assert operator["broad_fep_claim_safe"] is False
    assert operator["required_slot_count"] == 1
    assert operator["input_slots"][0]["slot_id"] == "top_k_refinement_rows"
    assert operator["current_surface_status"]["first_blocked_target"] == (
        "top_k_refinement_operator_intake"
    )
    assert operator["next_actions"][0] == "fill_pocketmd_lite_operator_intake_packet"
    assert operator["acceptance_criteria"][-1].startswith("broad_all_atom_md_claim")

    assert surface["schema_version"] == "pocketmd-lite-science-product-surface.v1"
    assert surface["surface_id"] == "pocketmd_lite_science_product_surface"
    assert surface["surface_kind"] == "science_product_surface"
    assert surface["science_surface_family"] == "pocketmd_lite"
    assert surface["contract_pass"] is False
    assert surface["locked"] is True
    assert surface["claim_locked"] is True
    assert surface["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert surface["root_cause_tags"] == ["operator_refinement_rows_required"]
    assert surface["goal_roadmap_linkage"] == {
        "phase": "Phase 4",
        "roadmap_item": "PocketMD Lite science product surface",
        "bottleneck": "pocketmd_lite_science_product_surface_locked",
        "next_goal_actions": [
            "fill_pocketmd_lite_operator_intake_packet",
            "run_pocketmd_lite_topk_survival_materializer",
            "publish_pocketmd_lite_readonly_api",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_action_board",
        ],
    }
    assert "Broad all-atom MD, FEP" in surface["claim_boundary"]


def test_pocketmd_lite_cli_writes_pm_visible_surface(tmp_path: Path) -> None:
    contract_out = tmp_path / "pocketmd_lite_contract.json"
    survival_out = tmp_path / "pocketmd_lite_topk_survival_report.json"
    api_out = tmp_path / "pocketmd_lite_readonly_api.json"
    handoff_out = tmp_path / "pocketmd_lite_delivery_handoff.json"
    operator_out = tmp_path / "pocketmd_lite_operator_intake_packet.json"
    operator_md_out = tmp_path / "pocketmd_lite_operator_intake_packet.md"
    surface_out = tmp_path / "surface" / "pocketmd_lite_science_product_surface.json"

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--contract-out",
                str(contract_out),
                "--survival-report-out",
                str(survival_out),
                "--readonly-api-out",
                str(api_out),
                "--handoff-out",
                str(handoff_out),
                "--operator-intake-out",
                str(operator_out),
                "--operator-intake-md-out",
                str(operator_md_out),
                "--surface-out",
                str(surface_out),
            ]
        )
        == 0
    )

    for path in (contract_out, survival_out, api_out, handoff_out, operator_out, surface_out):
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["source_commit_sha"]
        assert payload["input_checksums"][
            "scripts/build_pocketmd_lite_product_surface.py"
        ].startswith("sha256:")
        assert payload["input_checksums"][
            "scripts/materialize_pocketmd_lite_topk_survival_report.py"
        ].startswith("sha256:")
    assert "# PocketMD Lite Operator Intake Packet" in operator_md_out.read_text(
        encoding="utf-8"
    )

    rows = pm_report._evidence_surface_rows(surface_out.parent)
    assert rows == [
        {
            "surface_id": "pocketmd_lite_science_product_surface",
            "path": str(surface_out),
            "present": True,
            "contract_pass": False,
            "status": "locked",
            "reason_code": "ERR_POCKETMD_LITE_PRODUCT_SURFACE_LOCKED",
            "blocker_count": 3,
            "locked": True,
            "missing": False,
            "summary_line": (
                "PocketMD Lite science product surface: LOCKED | "
                "top-k refinement operator rows required"
            ),
            "first_blocked_target": "top_k_refinement_operator_intake",
            "root_cause_tags": ["operator_refinement_rows_required"],
        }
    ]
