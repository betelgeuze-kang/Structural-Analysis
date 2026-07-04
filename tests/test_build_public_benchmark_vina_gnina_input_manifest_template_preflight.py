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
    / "build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_vina_gnina_input_manifest_template_preflight",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum(text: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(module.MANIFEST_REQUIRED_FIELDS),
        )
        writer.writeheader()
        writer.writerows(rows)


def test_current_vina_gnina_input_manifest_template_preflight_surfaces_gaps() -> None:
    payload = module.build_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=REPO_ROOT,
    )

    assert payload["schema_version"] == (
        "public-benchmark-vina-gnina-input-manifest-template-preflight.v1"
    )
    assert payload["status"] == "operator_manifest_completion_required"
    assert payload["contract_pass"] is True
    assert payload["manifest_ready"] is False
    assert payload["filled_manifest_detected"] is False
    assert payload["summary"]["template_row_count"] == 12
    assert payload["summary"]["template_case_coverage_complete"] is True
    assert payload["summary"]["missing_expected_case_count"] == 0
    assert payload["summary"]["missing_required_value_count"] > 0
    assert payload["summary"]["missing_local_file_count"] > 0
    assert payload["summary"]["missing_receipt_ref_count"] > 0
    assert payload["summary"]["source_file_requirement_count"] == 24
    assert payload["summary"]["source_file_missing_count"] == 24
    assert payload["summary"]["prepared_input_requirement_count"] == 24
    assert payload["summary"]["prepared_input_missing_count"] == 24
    assert payload["summary"]["receipt_ref_requirement_count"] == 60
    assert payload["summary"]["receipt_ref_missing_count"] == 60
    first_row = payload["case_preflight_rows"][0]
    assert first_row["case_id"] == "casf2016_4llx"
    assert "prepared_receptor_checksum" in first_row["missing_required_fields"]
    assert "prepared_ligand_checksum" in first_row["missing_required_fields"]
    assert "protein_structure_path" in first_row["missing_local_file_fields"]
    assert "vina_config_ref" in first_row["missing_receipt_ref_fields"]
    first_source_file = payload["source_file_acquisition_plan"][0]
    assert first_source_file["case_id"] == "casf2016_4llx"
    assert first_source_file["file_role"] == "source_protein_structure"
    assert first_source_file["path"] == "CASF-2016/coreset/4llx/4llx_protein.pdb"
    assert first_source_file["operator_action"] == (
        "acquire_from_official_casf_archive_and_verify_checksum"
    )
    first_prepared_file = payload["prepared_input_plan"][0]
    assert first_prepared_file["file_role"] == "prepared_receptor"
    assert first_prepared_file["operator_action"] == (
        "prepare_vina_gnina_input_and_record_checksum"
    )
    assert payload["receipt_ref_plan"][0]["operator_action"] == "attach_vina_config_ref"
    markdown = module.render_public_benchmark_vina_gnina_input_manifest_template_preflight_markdown(
        payload
    )
    assert "## Source File Acquisition Plan" in markdown
    assert "CASF-2016/coreset/4llx/4llx_protein.pdb" in markdown
    assert "## Prepared Input Plan" in markdown
    assert "## Receipt Ref Plan" in markdown
    assert "does not promote the template" in payload["claim_boundary"]


def test_vina_gnina_input_manifest_template_preflight_accepts_completed_rows(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "operator_inputs" / "1abc"
    input_dir.mkdir(parents=True)
    (input_dir / "protein.pdb").write_text("ATOM\n", encoding="utf-8")
    (input_dir / "reference_ligand.sdf").write_text("ligand\n", encoding="utf-8")
    (input_dir / "receptor.pdbqt").write_text("receptor\n", encoding="utf-8")
    (input_dir / "ligand.pdbqt").write_text("ligand\n", encoding="utf-8")
    receipt_dir = tmp_path / "operator_attached" / "vina_gnina" / "casf2016_1abc"
    receipt_dir.mkdir(parents=True)
    for name in (
        "vina_config.json",
        "gnina_config.json",
        "vina_run_receipt.json",
        "gnina_run_receipt.json",
        "input_prep.json",
    ):
        (receipt_dir / name).write_text("{}", encoding="utf-8")

    execution_plan = tmp_path / "execution_plan.json"
    execution_plan.write_text(
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
    template = tmp_path / "template.csv"
    _write_csv(
        template,
        [
            {
                "case_id": "casf2016_1abc",
                "complex_id": "1abc",
                "benchmark_split": "CASF-core",
                "source_family": "CASF/PDBBind + Vina/GNINA",
                "source_license_or_accession": "PDBbind+ CASF-2016 official package",
                "source_checksum": _checksum("source"),
                "provenance_ref": "https://www.pdbbind-plus.org.cn/casf",
                "protein_structure_path": "operator_inputs/1abc/protein.pdb",
                "protein_structure_checksum": _checksum("ATOM\n"),
                "reference_ligand_path": "operator_inputs/1abc/reference_ligand.sdf",
                "reference_ligand_checksum": _checksum("ligand\n"),
                "prepared_receptor_path": "operator_inputs/1abc/receptor.pdbqt",
                "prepared_receptor_checksum": _checksum("receptor\n"),
                "prepared_ligand_path": "operator_inputs/1abc/ligand.pdbqt",
                "prepared_ligand_checksum": _checksum("ligand\n"),
                "docking_box_center_x": "1.0",
                "docking_box_center_y": "2.0",
                "docking_box_center_z": "3.0",
                "docking_box_size_x": "18.0",
                "docking_box_size_y": "18.0",
                "docking_box_size_z": "18.0",
                "vina_config_ref": (
                    "operator_attached/vina_gnina/casf2016_1abc/vina_config.json"
                ),
                "gnina_config_ref": (
                    "operator_attached/vina_gnina/casf2016_1abc/gnina_config.json"
                ),
                "vina_run_receipt_ref": (
                    "operator_attached/vina_gnina/casf2016_1abc/vina_run_receipt.json"
                ),
                "gnina_run_receipt_ref": (
                    "operator_attached/vina_gnina/casf2016_1abc/gnina_run_receipt.json"
                ),
                "input_preparation_provenance_ref": (
                    "operator_attached/vina_gnina/casf2016_1abc/input_prep.json"
                ),
            }
        ],
    )

    payload = module.build_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=tmp_path,
        execution_plan=execution_plan,
        template=template,
        expected_manifest=tmp_path / "public_benchmark_vina_gnina_input_manifest.csv",
    )

    assert payload["status"] == "operator_manifest_complete"
    assert payload["contract_pass"] is True
    assert payload["manifest_ready"] is True
    assert payload["summary"]["missing_required_value_count"] == 0
    assert payload["summary"]["missing_local_file_count"] == 0
    assert payload["summary"]["missing_receipt_ref_count"] == 0
    assert payload["summary"]["source_file_missing_count"] == 0
    assert payload["summary"]["prepared_input_missing_count"] == 0
    assert payload["summary"]["receipt_ref_missing_count"] == 0
    assert payload["case_preflight_rows"][0]["status"] == "ready"
    assert payload["source_file_acquisition_plan"][0]["status"] == "ready"
    assert payload["prepared_input_plan"][0]["status"] == "ready"
    assert payload["receipt_ref_plan"][0]["status"] == "ready"


def test_vina_gnina_input_manifest_template_preflight_writer_creates_outputs(
    tmp_path: Path,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    execution_plan.write_text(
        json.dumps({"case_execution_plans": []}, sort_keys=True),
        encoding="utf-8",
    )
    template = tmp_path / "template.csv"
    _write_csv(template, [])
    out = tmp_path / "preflight.json"
    out_md = tmp_path / "preflight.md"

    payload = module.write_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=tmp_path,
        execution_plan=execution_plan,
        template=template,
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == payload["status"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Public Benchmark Vina/GNINA Input Manifest Template Preflight" in markdown
