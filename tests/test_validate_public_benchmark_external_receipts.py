from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_public_benchmark_external_receipts.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "validate_public_benchmark_external_receipts", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _subset_row(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_license_or_accession": f"PDBBind-CASF-2016-core:{case_id}",
        "source_checksum": _sha(f"PDBBind-CASF-2016-core:{case_id}"),
        "provenance_ref": f"local-evidence://public-benchmark/subset/{case_id}",
        "source_file_checksums": {
            f"{case_id}/protein.pdb": _sha(f"{case_id}:protein"),
            f"{case_id}/ligand.sdf": _sha(f"{case_id}:ligand"),
            f"{case_id}/pose.sdf": _sha(f"{case_id}:pose"),
        },
    }


def test_external_receipts_block_when_no_materialized_rows() -> None:
    result = module.validate_external_receipts(
        subset_manifest={"case_rows": []},
        enrichment_scorecard={"target_rows": []},
        vina_gnina_comparison_adapter={"case_rows": []},
    )

    assert result["contract_pass"] is True
    assert result["public_benchmark_external_receipts_ready"] is False
    assert result["blockers"] == ["public_benchmark_external_receipts_missing"]
    assert result["materialized_row_count"] == 0
    coverage = result["receipt_coverage"]
    assert coverage["expected_artifact_role_count"] == 3
    assert coverage["materialized_artifact_role_count"] == 0
    assert coverage["receipt_complete_artifact_role_count"] == 0
    assert coverage["missing_expected_artifact_roles"] == [
        "casf_pdbbind_subset_manifest",
        "dud_e_lit_pcba_enrichment_scorecard",
        "vina_gnina_comparison_adapter",
    ]


def test_external_receipts_pass_for_complete_rows() -> None:
    result = module.validate_external_receipts(
        subset_manifest={"case_rows": [_subset_row("case_a")]},
        enrichment_scorecard={
            "target_rows": [
                {
                    "target_id": "target_a",
                    "source_license_or_accession": "DUD-E:target_a:release-2015",
                    "source_checksum": _sha("DUD-E:target_a:release-2015"),
                    "provenance_ref": "local-evidence://public-benchmark/enrichment/target_a",
                }
            ]
        },
        vina_gnina_comparison_adapter={
            "case_rows": [
                {
                    "case_id": "case_a",
                    "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                    "source_checksum": _sha("vina-gnina:case_a"),
                    "provenance_ref": "local-evidence://public-benchmark/vina-gnina/case_a",
                }
            ]
        },
    )

    assert result["status"] == "ready"
    assert result["public_benchmark_external_receipts_ready"] is True
    assert result["materialized_row_count"] == 3
    assert result["receipt_complete_row_count"] == 3
    assert result["blockers"] == []
    coverage = result["receipt_coverage"]
    assert coverage["materialized_artifact_role_count"] == 3
    assert coverage["receipt_complete_artifact_role_count"] == 3
    assert coverage["missing_expected_artifact_roles"] == []
    role_summaries = {
        row["artifact_role"]: row for row in coverage["role_summaries"]
    }
    assert role_summaries["casf_pdbbind_subset_manifest"][
        "required_receipt_fields"
    ] == [
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
        "source_file_checksums",
    ]


def test_external_receipts_require_subset_provenance_and_valid_checksums() -> None:
    row = _subset_row("case_a")
    row["provenance_ref"] = ""
    row["source_file_checksums"] = {"case_a/protein.pdb": "sha256:not-real"}

    result = module.validate_external_receipts(
        subset_manifest={"case_rows": [row]},
        enrichment_scorecard={"target_rows": []},
        vina_gnina_comparison_adapter={"case_rows": []},
    )

    assert result["public_benchmark_external_receipts_ready"] is False
    assert result["blockers"] == [
        "subset_manifest:case_a:provenance_ref_blank",
        "subset_manifest:case_a:source_file_checksum_0_invalid",
    ]
    coverage = result["receipt_coverage"]
    assert coverage["materialized_artifact_role_count"] == 1
    assert coverage["receipt_complete_artifact_role_count"] == 0
    assert coverage["missing_expected_artifact_roles"] == [
        "dud_e_lit_pcba_enrichment_scorecard",
        "vina_gnina_comparison_adapter",
    ]


def test_external_receipts_reject_placeholder_source_receipts() -> None:
    row = _subset_row("case_a")
    row["source_license_or_accession"] = "CASF/PDBBind:test-accession"
    row["source_checksum"] = "sha256:" + "a" * 64
    row["provenance_ref"] = "operator://subset/case_a"
    row["source_file_checksums"] = {"case_a/protein.pdb": "sha256:" + "b" * 64}

    result = module.validate_external_receipts(
        subset_manifest={"case_rows": [row]},
        enrichment_scorecard={"target_rows": []},
        vina_gnina_comparison_adapter={"case_rows": []},
    )

    assert result["public_benchmark_external_receipts_ready"] is False
    assert "subset_manifest:case_a:source_license_or_accession_placeholder" in result["blockers"]
    assert "subset_manifest:case_a:source_checksum_placeholder_digest" in result["blockers"]
    assert "subset_manifest:case_a:provenance_ref_placeholder" in result["blockers"]
    assert "subset_manifest:case_a:source_file_checksum_0_placeholder_digest" in result["blockers"]
    assert result["source_actuality_policy"]["placeholder_provenance_prefixes_rejected"] == [
        "operator://"
    ]


def test_external_receipts_cli_writes_result(tmp_path: Path) -> None:
    subset = tmp_path / "subset.json"
    enrichment = tmp_path / "enrichment.json"
    vina_gnina = tmp_path / "vina_gnina.json"
    out = tmp_path / "receipts.json"
    subset.write_text(json.dumps({"case_rows": [_subset_row("case_a")]}), encoding="utf-8")
    enrichment.write_text(json.dumps({"target_rows": []}), encoding="utf-8")
    vina_gnina.write_text(json.dumps({"case_rows": []}), encoding="utf-8")

    assert (
        module.main(
            [
                "--subset-manifest",
                str(subset),
                "--enrichment-scorecard",
                str(enrichment),
                "--vina-gnina-comparison-adapter",
                str(vina_gnina),
                "--out",
                str(out),
                "--fail-blocked",
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["public_benchmark_external_receipts_ready"] is True
