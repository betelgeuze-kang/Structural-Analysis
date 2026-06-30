from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_science_actual_closure_from_rows.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("materialize_science_actual_closure_from_rows", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _write_gpcr_rows(path: Path) -> None:
    fieldnames = [
        "target_id",
        "score_direction",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
    ]
    rows = []
    for target_id in ("DRD2", "HTR2A", "OPRM1"):
        rows.extend(
            [
                [target_id, "higher_is_better", f"{target_id}_positive_1", "0.95", "true", "false"],
                [target_id, "higher_is_better", f"{target_id}_positive_2", "0.90", "true", "false"],
                [target_id, "higher_is_better", f"{target_id}_positive_3", "0.85", "true", "false"],
                [target_id, "higher_is_better", f"{target_id}_decoy_1", "0.40", "false", "true"],
                [target_id, "higher_is_better", f"{target_id}_decoy_2", "0.10", "false", "true"],
            ]
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _pocketmd_row(
    *,
    case_id: str,
    candidate_id: str,
    rank: int,
    local_min_survived: bool,
    contact_rate: float,
    h_bond_rate: float,
    clash_before: int,
    clash_after: int,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind operator intake",
        "top_k_rank": rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": -8.0 + rank,
        "post_refinement_energy_proxy": -8.5 + rank,
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_low": -0.2 + rank / 10,
        "uncertainty_high": 0.2 + rank / 10,
        "uncertainty_unit": "energy_proxy_delta",
        "provenance_ref": f"operator://{case_id}/{candidate_id}",
        "source_checksum": _sha(f"{case_id}:{candidate_id}"),
    }


def _write_pocketmd_rows(path: Path) -> None:
    payload = {
        "top_k_refinement_rows": [
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
            ),
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
            _pocketmd_row(
                case_id="case_b",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=1.0,
                h_bond_rate=0.9,
                clash_before=5,
                clash_after=3,
            ),
        ]
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_science_actual_closure_audit_blocks_without_operator_rows(tmp_path: Path) -> None:
    audit = module.build_science_actual_closure_audit(
        repo_root=REPO_ROOT,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["component_ready_count"] == 0
    assert audit["blockers"] == [
        "gpcr_hard_decoy_actual_closure::gpcr_hard_decoy_rows_not_provided",
        "pocketmd_lite_topk_actual_closure::pocketmd_lite_topk_rows_not_provided",
    ]
    assert not (tmp_path / "gpcr_report.json").exists()
    assert not (tmp_path / "pocketmd_report.json").exists()


def test_science_actual_closure_audit_materializes_both_ready_surfaces(
    tmp_path: Path,
) -> None:
    gpcr_rows = tmp_path / "gpcr_rows.csv"
    pocketmd_rows = tmp_path / "pocketmd_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps({"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}),
        encoding="utf-8",
    )

    audit = module.build_science_actual_closure_audit(
        repo_root=REPO_ROOT,
        gpcr_rows_path=gpcr_rows,
        pocketmd_rows_path=pocketmd_rows,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="unit-test-actual-closure-rows",
        source_url="https://example.invalid/science-actual-closure-rows",
        source_license="fixture-only",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["component_ready_count"] == 2
    assert audit["blockers"] == []

    gpcr = audit["components"][0]
    pocketmd = audit["components"][1]
    assert gpcr["phase3_exit_gate_status"] == "ready"
    assert gpcr["target_pass_count"] == 3
    assert pocketmd["phase4_exit_gate_status"] == "ready"
    assert pocketmd["real_refinement_case_count"] == 2
    assert (tmp_path / "gpcr_surface.json").exists()
    assert (tmp_path / "pocketmd_surface.json").exists()
