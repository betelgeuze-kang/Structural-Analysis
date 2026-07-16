from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_module(name: str, script_name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / script_name)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


module = _load_module(
    "materialize_pocketmd_lite_gpcr_chembl_refinement_receipts",
    "materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py",
)
rows_module = _load_module(
    "materialize_pocketmd_lite_topk_rows_from_receipt_bundle",
    "materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py",
)


def test_module_import_is_collection_safe_without_rdkit(
    monkeypatch,
) -> None:
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "rdkit" or name.startswith("rdkit."):
            raise ModuleNotFoundError("simulated missing rdkit")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    missing = _load_module(
        "materialize_pocketmd_lite_gpcr_chembl_refinement_receipts_missing_rdkit",
        "materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py",
    )

    assert missing.Chem is None
    assert missing.AllChem is None
    with pytest.raises(RuntimeError, match="RDKit is required"):
        missing._require_rdkit()


def _checksum(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _write_gpcr_rows(path: Path) -> None:
    rows = []
    for target_index, target_id in enumerate(("DRD2", "HTR2A", "OPRM1"), start=1):
        for rank in (1, 2):
            molecule_id = f"CHEMBL{target_index}{rank}"
            rows.append(
                {
                    "activity_id": f"activity-{target_id}-{rank}",
                    "is_positive": True,
                    "molecule_id": molecule_id,
                    "provenance_ref": (
                        "https://www.ebi.ac.uk/chembl/api/data/activity/"
                        f"{target_id}-{rank}.json"
                    ),
                    "score": 100.0 - rank,
                    "source_checksum": _checksum(f"upstream:{target_id}:{rank}"),
                    "target_id": target_id,
                }
            )
    path.write_text(json.dumps({"rows": rows}, sort_keys=True), encoding="utf-8")


def _write_receipt_bundle(path: Path) -> None:
    bundle_rows = []
    for case_index in (1, 2, 3):
        case_id = f"pocketmd_lite_case_{case_index:03d}"
        for rank in (1, 2):
            bundle_rows.append(
                {
                    "case_id": case_id,
                    "top_k_rank": rank,
                    "candidate_id_placeholder": f"{case_id}_rank_{rank:02d}",
                    "source_family": "upstream_ranked_top_k_candidate_set",
                    "receipt_ref": (
                        "operator_receipts/"
                        f"{case_id}/rank_{rank:02d}_refinement_receipt.json"
                    ),
                    "receipt_template_payload": {
                        "case_id": case_id,
                        "top_k_rank": rank,
                        "status": "operator_refinement_receipt_required",
                    },
                }
            )
    path.write_text(
        json.dumps(
            {
                "bundle_materialized": True,
                "bundle_rows": bundle_rows,
                "status": "receipt_bundle_materialized",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _fake_metrics(smiles: str, *, seed_base: int) -> dict[str, object]:
    assert smiles == "CCO"
    return {
        "pre_refinement_energy_proxy": 2.0,
        "post_refinement_energy_proxy": 1.0,
        "energy_proxy_delta": -1.0,
        "local_min_survived": True,
        "contact_persistence_rate": 1.0,
        "h_bond_persistence_rate": 1.0,
        "clash_count_before": 1,
        "clash_count_after": 0,
        "uncertainty_low": -1.1,
        "uncertainty_high": -0.9,
        "uncertainty_unit": "energy_proxy_delta",
        "force_field": "MMFF94s",
        "seed_base": seed_base,
        "conformer_replicates": [],
    }


def test_materializes_gpcr_chembl_refinement_receipts_and_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gpcr_rows = tmp_path / "gpcr_rows.json"
    receipt_bundle = tmp_path / "receipt_bundle.json"
    source_out = tmp_path / "source.json"
    report_out = tmp_path / "report.json"
    out_rows = tmp_path / "pocketmd_rows.json"
    out_report = tmp_path / "rows_report.json"
    _write_gpcr_rows(gpcr_rows)
    _write_receipt_bundle(receipt_bundle)
    monkeypatch.setattr(
        module,
        "_fetch_chembl_molecule",
        lambda molecule_id: {
            "molecule_chembl_id": molecule_id,
            "molecule_structures": {"canonical_smiles": "CCO"},
        },
    )
    monkeypatch.setattr(module, "_refinement_metrics", _fake_metrics)

    report = module.materialize_pocketmd_lite_gpcr_chembl_refinement_receipts(
        repo_root=tmp_path,
        gpcr_rows=gpcr_rows,
        receipt_bundle=receipt_bundle,
        source_out=source_out,
        report_out=report_out,
    )

    assert report["status"] == "receipts_materialized"
    assert report["contract_pass"] is True
    assert report["top_k_refinement_row_count"] == 6
    assert report["completed_receipt_count"] == 6
    assert source_out.is_file()
    receipt = json.loads(
        (
            tmp_path
            / "operator_receipts/pocketmd_lite_case_001/"
            "rank_01_refinement_receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "complete"
    assert receipt["candidate_id"] == "DRD2_CHEMBL11"
    assert receipt["operator_input_source"]["source_artifact_sha256"] == report[
        "source_artifact_sha256"
    ]

    rows_report = rows_module.materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
        repo_root=tmp_path,
        receipt_bundle=receipt_bundle,
        out_rows=out_rows,
        out_report=out_report,
    )
    assert rows_report["status"] == "rows_materialized"
    assert rows_report["contract_pass"] is True
    rows_payload = json.loads(out_rows.read_text(encoding="utf-8"))
    assert rows_payload["top_k_refinement_rows"][0]["candidate_id"] == "DRD2_CHEMBL11"
