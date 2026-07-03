from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_decoy_source_snapshot.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_decoy_source_snapshot",
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
    relation: str = "=",
    standard_type: str = "Ki",
) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "assay_chembl_id": f"CHEMBL_A_{activity_id}",
        "document_chembl_id": f"CHEMBL_D_{activity_id}",
        "molecule_chembl_id": molecule,
        "standard_relation": relation,
        "standard_type": standard_type,
        "standard_units": "nM",
        "standard_value": value,
    }


def _weak_rows(prefix: str, *, start: int, base_value: float) -> list[dict[str, object]]:
    return [
        _activity(
            molecule=f"CHEMBL_{prefix}_{index:03d}",
            activity_id=start + index,
            value=base_value - index,
            relation=">" if index % 2 else "=",
        )
        for index in range(1, 21)
    ]


def _fixture_payload() -> dict[str, object]:
    drd2_rows = [
        _activity(molecule="CHEMBL_D2_TOP", activity_id=101, value=60000.0),
        _activity(molecule="CHEMBL_D2_TOP", activity_id=102, value=20000.0),
        _activity(molecule="CHEMBL_D2_LOW", activity_id=103, value=9999.0),
        _activity(
            molecule="CHEMBL_D2_STRONG_BOUND",
            activity_id=104,
            value=50000.0,
            relation="<=",
        ),
        *_weak_rows("D2C", start=110, base_value=50000.0),
    ]
    return {
        "DRD2": {
            "page_meta": {"total_count": len(drd2_rows)},
            "activities": drd2_rows,
        },
        "HTR2A": _weak_rows("H2A", start=200, base_value=40000.0),
        "OPRM1": _weak_rows("OPR", start=300, base_value=30000.0),
    }


def test_gpcr_decoy_source_snapshot_materializes_chembl_candidates(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "chembl_fixture.json"
    fixture.write_text(json.dumps(_fixture_payload()), encoding="utf-8")

    payload = module.build_gpcr_hard_decoy_decoy_source_snapshot(
        repo_root=REPO_ROOT,
        fixture_path=fixture,
        candidate_limit=20,
    )
    targets = {row["target_id"]: row for row in payload["target_snapshots"]}

    assert payload["schema_version"] == "gpcr-hard-decoy-decoy-source-snapshot.v1"
    assert payload["status"] == "decoy_candidate_sources_ready"
    assert payload["contract_pass"] is True
    assert payload["decoy_candidate_source_ready"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert payload["target_candidate_counts"] == {
        "DRD2": 20,
        "HTR2A": 20,
        "OPRM1": 20,
    }
    assert payload["total_decoy_candidate_count"] == 60
    assert payload["minimum_decoy_standard_value_nm"] == 10000.0
    assert payload["closure_blockers"] == [
        "target_specific_hard_decoy_source_not_attached",
        "gpcr_scoring_protocol_receipts_not_attached",
        "gpcr_hard_decoy_rows_not_materialized",
    ]
    assert payload["blockers"] == []

    drd2 = targets["DRD2"]
    assert drd2["decoy_candidate_count"] == 20
    assert drd2["activity_total_count"] == 24
    assert [row["molecule_id"] for row in drd2["decoy_candidates"][:3]] == [
        "CHEMBL_D2_TOP",
        "CHEMBL_D2C_001",
        "CHEMBL_D2C_002",
    ]

    first = drd2["decoy_candidates"][0]
    assert first["molecule_id"] == "CHEMBL_D2_TOP"
    assert first["activity_id"] == "101"
    assert first["closure_role"] == "decoy_candidate_source_only"
    assert first["provenance_ref"].endswith("/activity/101.json")
    assert first["source_checksum"].startswith("sha256:")
    assert "weak/low-affinity ligand candidates only" in drd2["claim_boundary"]
    assert all(
        row["standard_value_nm"] >= 10000.0
        for row in drd2["decoy_candidates"]
    )
    assert "CHEMBL_D2_LOW" not in {
        row["molecule_id"] for row in drd2["decoy_candidates"]
    }
    assert "CHEMBL_D2_STRONG_BOUND" not in {
        row["molecule_id"] for row in drd2["decoy_candidates"]
    }
    assert [row["molecule_id"] for row in drd2["decoy_candidates"]].count(
        "CHEMBL_D2_TOP"
    ) == 1


def test_gpcr_decoy_source_snapshot_cli_writes_markdown(tmp_path: Path) -> None:
    fixture = tmp_path / "chembl_fixture.json"
    out = tmp_path / "gpcr_hard_decoy_decoy_source_snapshot.json"
    out_md = tmp_path / "gpcr_hard_decoy_decoy_source_snapshot.md"
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
            "20",
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["decoy_candidate_source_ready"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["summary"]["total_decoy_candidate_count"] == 60
    assert "# GPCR Hard-Decoy Decoy Source Snapshot" in markdown
    assert "`DRD2` | `CHEMBL217` | 20" in markdown
