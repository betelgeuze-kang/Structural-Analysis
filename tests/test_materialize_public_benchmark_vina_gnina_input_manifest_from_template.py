from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_input_manifest_from_template.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_input_manifest_from_template",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_execution_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "case_execution_plans": [
                    {"case_id": "casf2016_1abc", "complex_id": "1abc"}
                ],
                "input_manifest_status": {
                    "status": "not_detected",
                    "detected_manifest_artifact_count": 0,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {field: "" for field in module.MANIFEST_REQUIRED_FIELDS}
    row.update(
        {
            "case_id": "casf2016_1abc",
            "complex_id": "1abc",
            "benchmark_split": "CASF-core",
            "source_family": "CASF/PDBBind + Vina/GNINA",
            "source_license_or_accession": "PDBbind+ CASF-2016 official package",
            "source_checksum": "sha256:" + "1" * 64,
            "provenance_ref": "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz",
            "protein_structure_path": "CASF-2016/coreset/1abc/1abc_protein.pdb",
            "protein_structure_checksum": "sha256:" + "2" * 64,
            "reference_ligand_path": "CASF-2016/coreset/1abc/1abc_ligand.sdf",
            "reference_ligand_checksum": "sha256:" + "3" * 64,
            "prepared_receptor_path": "prepared/1abc_receptor.pdbqt",
            "prepared_ligand_path": "prepared/1abc_ligand.pdbqt",
            "docking_box_center_x": "1.0",
            "docking_box_center_y": "2.0",
            "docking_box_center_z": "3.0",
            "docking_box_size_x": "18.0",
            "docking_box_size_y": "18.0",
            "docking_box_size_z": "18.0",
            "vina_config_ref": "operator_attached/vina_gnina/casf2016_1abc/vina_config.json",
            "gnina_config_ref": "operator_attached/vina_gnina/casf2016_1abc/gnina_config.json",
            "vina_run_receipt_ref": "operator_attached/vina_gnina/casf2016_1abc/vina_run_receipt.json",
            "gnina_run_receipt_ref": "operator_attached/vina_gnina/casf2016_1abc/gnina_run_receipt.json",
        }
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(module.MANIFEST_REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerow(row)


def test_materializes_vina_gnina_input_manifest_working_copy(
    tmp_path: Path,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    template = tmp_path / "template.csv"
    out_manifest = tmp_path / "public_benchmark_vina_gnina_input_manifest.csv"
    out_report = tmp_path / "report.json"
    _write_execution_plan(execution_plan)
    _write_template(template)

    payload = module.materialize_public_benchmark_vina_gnina_input_manifest_from_template(
        repo_root=tmp_path,
        template=template,
        out_manifest=out_manifest,
        out_report=out_report,
    )

    assert payload["status"] == "manifest_working_copy_materialized"
    assert payload["contract_pass"] is True
    assert payload["manifest_materialized"] is True
    assert payload["wrote_manifest"] is True
    assert payload["manifest_ready"] is False
    assert payload["row_count"] == 1
    rows = list(csv.DictReader(out_manifest.open(encoding="utf-8", newline="")))
    assert rows[0]["case_id"] == "casf2016_1abc"
    assert rows[0]["prepared_receptor_checksum"] == ""
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "manifest_working_copy_materialized"
    )


def test_vina_gnina_input_manifest_working_copy_preserves_existing_manifest(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template.csv"
    out_manifest = tmp_path / "public_benchmark_vina_gnina_input_manifest.csv"
    _write_template(template)
    out_manifest.write_text("case_id\noperator_case\n", encoding="utf-8")

    payload = module.materialize_public_benchmark_vina_gnina_input_manifest_from_template(
        repo_root=tmp_path,
        template=template,
        out_manifest=out_manifest,
        out_report=tmp_path / "report.json",
    )

    assert payload["status"] == "manifest_already_exists"
    assert payload["contract_pass"] is True
    assert payload["wrote_manifest"] is False
    assert payload["skipped_existing"] is True
    assert out_manifest.read_text(encoding="utf-8") == "case_id\noperator_case\n"
