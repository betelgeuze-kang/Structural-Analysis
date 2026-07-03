from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_chembl_activity_rows.py"
IMPORTER_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_gpcr_hard_decoy_operator_template_from_rows.py"
)
SUITE_SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_gpcr_hard_decoy_suite_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_chembl_activity_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

importer_spec = importlib.util.spec_from_file_location(
    "materialize_gpcr_hard_decoy_operator_template_from_rows",
    IMPORTER_SCRIPT_PATH,
)
assert importer_spec is not None
importer_module = importlib.util.module_from_spec(importer_spec)
assert importer_spec.loader is not None
sys.modules[importer_spec.name] = importer_module
importer_spec.loader.exec_module(importer_module)

suite_spec = importlib.util.spec_from_file_location(
    "materialize_gpcr_hard_decoy_suite_report",
    SUITE_SCRIPT_PATH,
)
assert suite_spec is not None
suite_module = importlib.util.module_from_spec(suite_spec)
assert suite_spec.loader is not None
sys.modules[suite_spec.name] = suite_module
suite_spec.loader.exec_module(suite_module)


TARGETS = {
    "DRD2": ("CHEMBL217", 100000),
    "HTR2A": ("CHEMBL224", 200000),
    "OPRM1": ("CHEMBL233", 300000),
}


def _checksum(*parts: object) -> str:
    text = ":".join(str(part) for part in parts)
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _candidate(
    *,
    target_id: str,
    index: int,
    is_positive: bool,
) -> dict[str, object]:
    chembl_target_id, base = TARGETS[target_id]
    activity_id = base + index + (0 if is_positive else 100)
    molecule_id = f"CHEMBL{activity_id}"
    standard_value_nm = float(index) if is_positive else float(100000 + index)
    return {
        "activity_id": str(activity_id),
        "chembl_target_id": chembl_target_id,
        "molecule_id": molecule_id,
        "standard_relation": "=" if is_positive else ">",
        "standard_type": "Ki",
        "standard_units": "nM",
        "standard_value_nm": standard_value_nm,
        "source_checksum": _checksum(target_id, molecule_id, standard_value_nm),
        "provenance_ref": (
            f"https://www.ebi.ac.uk/chembl/api/data/activity/{activity_id}.json"
        ),
    }


def _write_snapshots(tmp_path: Path) -> tuple[Path, Path]:
    positive_path = tmp_path / "positive_snapshot.json"
    decoy_path = tmp_path / "decoy_snapshot.json"
    positive_path.write_text(
        json.dumps(
            {
                "target_snapshots": [
                    {
                        "target_id": target_id,
                        "positive_candidates": [
                            _candidate(
                                target_id=target_id,
                                index=index,
                                is_positive=True,
                            )
                            for index in range(1, 5)
                        ],
                    }
                    for target_id in TARGETS
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    decoy_path.write_text(
        json.dumps(
            {
                "target_snapshots": [
                    {
                        "target_id": target_id,
                        "decoy_candidates": [
                            _candidate(
                                target_id=target_id,
                                index=index,
                                is_positive=False,
                            )
                            for index in range(1, 21)
                        ],
                    }
                    for target_id in TARGETS
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return positive_path, decoy_path


def _build_payload(tmp_path: Path) -> dict[str, object]:
    positive_path, decoy_path = _write_snapshots(tmp_path)
    return module.build_gpcr_hard_decoy_chembl_activity_rows(
        repo_root=REPO_ROOT,
        positive_snapshot_path=positive_path,
        decoy_snapshot_path=decoy_path,
    )


def test_chembl_activity_rows_materialize_source_attached_rows(
    tmp_path: Path,
) -> None:
    payload = _build_payload(tmp_path)

    assert payload["schema_version"] == "gpcr-hard-decoy-chembl-activity-rows.v1"
    assert payload["status"] == "raw_activity_rows_ready"
    assert payload["contract_pass"] is True
    assert payload["raw_rows_ready"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["row_count"] == 72
    assert payload["blockers"] == []
    assert payload["target_counts"] == {
        "DRD2": {"decoy_count": 20, "positive_count": 4, "total_count": 24},
        "HTR2A": {"decoy_count": 20, "positive_count": 4, "total_count": 24},
        "OPRM1": {"decoy_count": 20, "positive_count": 4, "total_count": 24},
    }
    assert payload["suggested_operator_input_source"]["source_id"] == (
        "chembl_gpcr_activity_positive_low_affinity_rows"
    )
    rows = payload["rows"]
    assert isinstance(rows, list)
    drd2_rows = [row for row in rows if row["target_id"] == "DRD2"]
    assert drd2_rows[0]["source_role"] == "chembl_positive_activity_row"
    assert drd2_rows[-1]["source_role"] == "chembl_low_affinity_decoy_activity_row"
    assert drd2_rows[0]["score"] > drd2_rows[-1]["score"]
    assert {row["score_direction"] for row in rows} == {"higher_is_better"}
    assert all(
        str(row["provenance_ref"]).startswith(
            "https://www.ebi.ac.uk/chembl/api/data/activity/"
        )
        for row in rows
    )


def test_chembl_activity_rows_can_feed_importer_and_suite(
    tmp_path: Path,
) -> None:
    payload = _build_payload(tmp_path)
    rows_path = tmp_path / "gpcr_hard_decoy_chembl_activity_rows.json"
    rows_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    template = importer_module.build_gpcr_hard_decoy_operator_template_from_rows(
        rows_path=rows_path,
        repo_root=REPO_ROOT,
        source_id=module.SOURCE_ID,
        source_url=module.CHEMBL_ACTIVITY_API_URL,
        source_license=module.SOURCE_LICENSE,
        source_version=module.SOURCE_VERSION,
    )
    report = suite_module.materialize_gpcr_hard_decoy_suite_report(
        template,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "ready"
    assert report["broad_gpcr_family_claim_safe"] is True
    assert report["target_pass_count"] == 3
    assert report["phase3_exit_gate"]["status"] == "ready"
    assert report["blockers"] == []
    assert report["operator_input_source_receipt"]["status"] == "pass"
    for target_row in report["target_rows"]:
        metrics = target_row["computed_hard_decoy_metrics"]
        assert target_row["status"] == "pass"
        assert metrics["calculation_status"] == "computed"
        assert metrics["ranking_pr_auc_ci_low"] >= 0.45
        assert metrics["top20_hit_rate"] >= 0.2
        assert metrics["decoys_above_positive_count"] == 0
        assert metrics["positive_out_anchored_by_top_decoys"] is False


def test_chembl_activity_rows_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    positive_path, decoy_path = _write_snapshots(tmp_path)
    out = tmp_path / "gpcr_hard_decoy_chembl_activity_rows.json"
    out_md = tmp_path / "gpcr_hard_decoy_chembl_activity_rows.md"

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--positive-snapshot",
                str(positive_path),
                "--decoy-snapshot",
                str(decoy_path),
                "--out",
                str(out),
                "--out-md",
                str(out_md),
            ]
        )
        == 0
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["status"] == "raw_activity_rows_ready"
    assert payload["row_count"] == 72
    assert "# GPCR Hard-Decoy ChEMBL Activity Rows" in markdown
    assert "`DRD2` | 4 | 20 | 24" in markdown
