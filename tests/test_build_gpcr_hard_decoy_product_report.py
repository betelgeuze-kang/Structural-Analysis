from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_product_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_gpcr_hard_decoy_product_report", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_gpcr_hard_decoy_product_report_is_readonly_and_science_blocked() -> None:
    report = module.build_gpcr_hard_decoy_product_report(repo_root=REPO_ROOT)

    assert report["schema_version"] == "gpcr-hard-decoy-product-report.v1"
    assert report["status"] == "ready_science_claim_blocked"
    assert report["reason_code"] == "PASS_READ_MODEL"
    assert report["contract_pass"] is True
    assert report["read_model_ready"] is True
    assert report["mutation_allowed"] is False
    assert report["route"] == "/product/gpcr-hard-decoy-suite-report"
    assert report["broad_gpcr_family_claim_safe"] is False
    assert report["science_claim_status"] == "blocked"
    assert report["target_count"] == 3
    assert report["target_pass_count"] == 0
    assert report["first_blocked_target"] == "DRD2"
    assert report["root_cause_tags"] == ["operator_values_required"]
    assert report["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert report["required_operator_fields"] == [
        "target_id",
        "ranking_pr_auc_ci_low",
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
    ]
    assert "DRD2:ranking_pr_auc_ci_low_required" in report["science_blockers"]
    assert report["linked_artifacts"] == {
        "evidence_surface": "implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json",
        "operator_template": "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json",
        "suite_report": "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json",
    }
    assert {row["method"] for row in report["endpoints"]} == {"GET"}
    assert "promote_broad_gpcr_claim" in report["forbidden_operations"]
    assert "fill_drd2_htr2a_oprm1_operator_template_values" in report["next_actions"]


def test_gpcr_hard_decoy_product_report_cli_writes_contract(tmp_path: Path) -> None:
    out = tmp_path / "gpcr_hard_decoy_product_report.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["route"] == "/product/gpcr-hard-decoy-suite-report"
    assert payload["input_checksums"][
        "scripts/build_gpcr_hard_decoy_product_report.py"
    ].startswith("sha256:")
    assert payload["input_checksums"][
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json"
    ].startswith("sha256:")
