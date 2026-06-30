from __future__ import annotations

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


def _sha(char: str) -> str:
    return "sha256:" + char * 64


def _subset_row(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_license_or_accession": f"CASF/PDBBind:{case_id}",
        "source_checksum": _sha("a"),
        "provenance_ref": f"operator://subset/{case_id}",
        "source_file_checksums": {
            f"{case_id}/protein.pdb": _sha("b"),
            f"{case_id}/ligand.sdf": _sha("c"),
            f"{case_id}/pose.sdf": _sha("d"),
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


def test_external_receipts_pass_for_complete_rows() -> None:
    result = module.validate_external_receipts(
        subset_manifest={"case_rows": [_subset_row("case_a")]},
        enrichment_scorecard={
            "target_rows": [
                {
                    "target_id": "target_a",
                    "source_license_or_accession": "DUD-E:target_a",
                    "source_checksum": _sha("e"),
                    "provenance_ref": "operator://enrichment/target_a",
                }
            ]
        },
        vina_gnina_comparison_adapter={
            "case_rows": [
                {
                    "case_id": "case_a",
                    "source_license_or_accession": "CASF/PDBBind:case_a",
                    "source_checksum": _sha("f"),
                    "provenance_ref": "operator://vina-gnina/case_a",
                }
            ]
        },
    )

    assert result["status"] == "ready"
    assert result["public_benchmark_external_receipts_ready"] is True
    assert result["materialized_row_count"] == 3
    assert result["receipt_complete_row_count"] == 3
    assert result["blockers"] == []


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
