from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_science_evidence_surface_seeds.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_science_evidence_surface_seeds", SCRIPT_PATH)
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


def test_science_evidence_surface_seeds_are_locked_not_passing() -> None:
    surfaces = module.build_science_evidence_surface_seeds(repo_root=REPO_ROOT)

    h_bond = surfaces["h_bond_backmap"]
    gpcr = surfaces["gpcr_hard_decoy"]
    assert h_bond["surface_id"] == "h_bond_backmap_evidence_surface"
    assert h_bond["contract_pass"] is False
    assert h_bond["claim_locked"] is True
    assert "h_bond_backmap_authoritative_receipts_required" in h_bond["blockers"]
    assert gpcr["surface_id"] == "gpcr_hard_decoy_evidence_surface"
    assert gpcr["contract_pass"] is False
    assert gpcr["reason_code"] == "ERR_BROAD_GPCR_CLAIM_LOCKED"
    assert gpcr["exit_criteria"] == {
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.20,
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
    }


def test_science_evidence_surface_seed_cli_writes_pm_visible_surfaces(
    tmp_path: Path,
) -> None:
    surface_dir = tmp_path / "surface"

    assert (
        module.main(
            [
                "--surface-dir",
                str(surface_dir),
                "--repo-root",
                str(REPO_ROOT),
            ]
        )
        == 0
    )

    h_bond_path = surface_dir / "h_bond_backmap_evidence_surface.json"
    gpcr_path = surface_dir / "gpcr_hard_decoy_evidence_surface.json"
    assert h_bond_path.exists()
    assert gpcr_path.exists()
    h_bond_payload = json.loads(h_bond_path.read_text(encoding="utf-8"))
    gpcr_payload = json.loads(gpcr_path.read_text(encoding="utf-8"))
    assert h_bond_payload["source_commit_sha"]
    assert gpcr_payload["input_checksums"][
        "scripts/build_science_evidence_surface_seeds.py"
    ].startswith("sha256:")

    rows = pm_report._evidence_surface_rows(surface_dir)
    rows_by_id = {row["surface_id"]: row for row in rows}
    assert rows_by_id["h_bond_backmap_evidence_surface"]["locked"] is True
    assert rows_by_id["gpcr_hard_decoy_evidence_surface"]["locked"] is True
    assert rows_by_id["h_bond_backmap_evidence_surface"]["contract_pass"] is False
    assert rows_by_id["gpcr_hard_decoy_evidence_surface"]["contract_pass"] is False
