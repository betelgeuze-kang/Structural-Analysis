from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_positive_source_snapshot.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_positive_source_snapshot",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _activity(
    *,
    molecule: str,
    activity_id: int,
    value: float,
    standard_type: str = "Ki",
) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "assay_chembl_id": f"CHEMBL_A_{activity_id}",
        "document_chembl_id": f"CHEMBL_D_{activity_id}",
        "molecule_chembl_id": molecule,
        "standard_relation": "=",
        "standard_type": standard_type,
        "standard_units": "nM",
        "standard_value": value,
    }


def _fixture_payload() -> dict[str, object]:
    return {
        "DRD2": {
            "page_meta": {"total_count": 10},
            "activities": [
                _activity(molecule="CHEMBL_D2_003", activity_id=103, value=30.0),
                _activity(molecule="CHEMBL_D2_001", activity_id=101, value=10.0),
                _activity(molecule="CHEMBL_D2_001", activity_id=102, value=15.0),
                _activity(molecule="CHEMBL_D2_004", activity_id=104, value=40.0),
                _activity(molecule="CHEMBL_D2_002", activity_id=105, value=20.0),
            ],
        },
        "HTR2A": [
            _activity(molecule="CHEMBL_H2A_004", activity_id=204, value=4.0),
            _activity(molecule="CHEMBL_H2A_001", activity_id=201, value=1.0),
            _activity(molecule="CHEMBL_H2A_003", activity_id=203, value=3.0),
            _activity(molecule="CHEMBL_H2A_002", activity_id=202, value=2.0),
        ],
        "OPRM1": [
            _activity(molecule="CHEMBL_OPR_002", activity_id=302, value=200.0),
            _activity(molecule="CHEMBL_OPR_004", activity_id=304, value=400.0),
            _activity(molecule="CHEMBL_OPR_001", activity_id=301, value=100.0),
            _activity(molecule="CHEMBL_OPR_003", activity_id=303, value=300.0),
        ],
    }


def test_gpcr_positive_source_snapshot_materializes_chembl_candidates(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "chembl_fixture.json"
    fixture.write_text(json.dumps(_fixture_payload()), encoding="utf-8")

    payload = module.build_gpcr_hard_decoy_positive_source_snapshot(
        repo_root=REPO_ROOT,
        fixture_path=fixture,
        candidate_limit=4,
    )
    targets = {row["target_id"]: row for row in payload["target_snapshots"]}

    assert payload["schema_version"] == (
        "gpcr-hard-decoy-positive-source-snapshot.v1"
    )
    assert payload["status"] == "positive_sources_ready"
    assert payload["contract_pass"] is True
    assert payload["positive_source_ready"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert payload["target_candidate_counts"] == {
        "DRD2": 4,
        "HTR2A": 4,
        "OPRM1": 4,
    }
    assert payload["total_positive_candidate_count"] == 12
    assert payload["closure_blockers"] == [
        "target_specific_hard_decoy_source_not_attached",
        "gpcr_scoring_protocol_receipts_not_attached",
        "gpcr_hard_decoy_rows_not_materialized",
    ]
    assert payload["blockers"] == []

    drd2 = targets["DRD2"]
    assert drd2["positive_candidate_count"] == 4
    assert drd2["activity_total_count"] == 10
    assert [row["molecule_id"] for row in drd2["positive_candidates"]] == [
        "CHEMBL_D2_001",
        "CHEMBL_D2_002",
        "CHEMBL_D2_003",
        "CHEMBL_D2_004",
    ]
    first = drd2["positive_candidates"][0]
    assert first["activity_id"] == "101"
    assert first["closure_role"] == "positive_ligand_candidate_only"
    assert first["provenance_ref"].endswith("/activity/101.json")
    assert first["source_checksum"].startswith("sha256:")
    assert "target-linked positive ligand candidates only" in drd2["claim_boundary"]


def test_gpcr_positive_source_snapshot_cli_writes_markdown(tmp_path: Path) -> None:
    fixture = tmp_path / "chembl_fixture.json"
    out = tmp_path / "gpcr_hard_decoy_positive_source_snapshot.json"
    out_md = tmp_path / "gpcr_hard_decoy_positive_source_snapshot.md"
    fixture.write_text(json.dumps(_fixture_payload()), encoding="utf-8")

    assert module.main(
        [
            "--repo-root",
            str(REPO_ROOT),
            "--fixture",
            str(fixture),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--candidate-limit",
            "4",
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["positive_source_ready"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["summary"]["total_positive_candidate_count"] == 12
    assert "# GPCR Hard-Decoy Positive Source Snapshot" in markdown
    assert "`DRD2` | `CHEMBL217` | 4" in markdown
