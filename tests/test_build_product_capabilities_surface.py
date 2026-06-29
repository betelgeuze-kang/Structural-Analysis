from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_product_capabilities_surface.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_product_capabilities_surface", SCRIPT_PATH)
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


def _capability_by_id(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["capability_rows"]
    assert isinstance(rows, list)
    return {
        str(row["capability_id"]): row
        for row in rows
        if isinstance(row, dict) and "capability_id" in row
    }


def test_product_capabilities_surface_exposes_science_and_benchmark_rows() -> None:
    surface = module.build_product_capabilities_surface(repo_root=REPO_ROOT)
    rows = _capability_by_id(surface)

    assert surface["schema_version"] == "product-capabilities-surface.v1"
    assert surface["surface_id"] == "product_capabilities_surface"
    assert surface["surface_kind"] == "product_capabilities_surface"
    assert surface["status"] == "ready"
    assert surface["reason_code"] == "PASS"
    assert surface["contract_pass"] is True
    assert surface["locked"] is False
    assert surface["claim_locked"] is False
    assert surface["blockers"] == []
    assert surface["read_model"] == {
        "route": "/product/capabilities",
        "artifact": "implementation/phase1/release_evidence/surface/product_capabilities_surface.json",
        "mutation_allowed": False,
    }

    assert {
        "structural_solver_restricted_alpha_surface",
        "public_benchmark_harness",
        "h_bond_backmap_evidence",
        "gpcr_hard_decoy_evidence",
        "pocketmd_lite_top_k_refinement",
    } <= set(rows)

    public_benchmark = rows["public_benchmark_harness"]
    assert public_benchmark["state"] == "blocked"
    assert public_benchmark["summary"]["public_benchmark_ready"] is False
    assert "attach_dud_e_lit_pcba_enrichment_intake" in public_benchmark["next_actions"]

    pocketmd = rows["pocketmd_lite_top_k_refinement"]
    assert pocketmd["state"] == "blocked"
    assert pocketmd["summary"]["product_surface_ready"] is False
    assert "run_pocketmd_lite_topk_survival_materializer" in pocketmd["next_actions"]

    gpcr = rows["gpcr_hard_decoy_evidence"]
    assert gpcr["state"] == "blocked"
    assert gpcr["summary"]["product_report_route"] == "/product/gpcr-hard-decoy-suite-report"
    assert gpcr["summary"]["broad_gpcr_family_claim_safe"] is False
    assert (
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json"
        in gpcr["evidence_artifacts"]
    )


def test_product_capabilities_surface_cli_writes_pm_visible_ready_surface(
    tmp_path: Path,
) -> None:
    out = tmp_path / "surface" / "product_capabilities_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["input_checksums"][
        "scripts/build_product_capabilities_surface.py"
    ].startswith("sha256:")
    assert payload["surface_id"] == "product_capabilities_surface"

    rows = pm_report._evidence_surface_rows(out.parent)
    assert rows == [
        {
            "surface_id": "product_capabilities_surface",
            "path": str(out),
            "present": True,
            "contract_pass": True,
            "status": "ready",
            "reason_code": "PASS",
            "blocker_count": 0,
            "locked": False,
            "missing": False,
            "summary_line": payload["summary_line"],
            "first_blocked_target": "",
            "root_cause_tags": [],
        }
    ]
