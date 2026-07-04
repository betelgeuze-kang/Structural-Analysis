from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _template_row(
    *,
    protein_checksum: str,
    ligand_checksum: str,
) -> dict[str, str]:
    row = {field: "" for field in module.MANIFEST_REQUIRED_FIELDS}
    row.update(
        {
            "case_id": "casf2016_1abc",
            "complex_id": "1abc",
            "benchmark_split": "CASF-core",
            "source_family": "CASF/PDBBind + Vina/GNINA",
            "source_license_or_accession": "PDBbind+ CASF-2016 official package",
            "source_checksum": _checksum_bytes(b"source"),
            "provenance_ref": "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz",
            "protein_structure_path": "CASF-2016/coreset/1abc/1abc_protein.pdb",
            "protein_structure_checksum": protein_checksum,
            "reference_ligand_path": "CASF-2016/coreset/1abc/1abc_ligand.sdf",
            "reference_ligand_checksum": ligand_checksum,
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
    return row


def _write_template(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(module.MANIFEST_REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def _write_tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_materialize_vina_gnina_input_manifest_from_casf_archive_extracts_sources(
    tmp_path: Path,
) -> None:
    protein = b"ATOM\n"
    ligand = b"ligand\n"
    archive = tmp_path / "CASF-2016.tar.gz"
    _write_tar(
        archive,
        {
            "outer/CASF-2016/coreset/1abc/1abc_protein.pdb": protein,
            "outer/CASF-2016/coreset/1abc/1abc_ligand.sdf": ligand,
        },
    )
    template = tmp_path / "template.csv"
    _write_template(
        template,
        [
            _template_row(
                protein_checksum=_checksum_bytes(protein),
                ligand_checksum=_checksum_bytes(ligand),
            )
        ],
    )
    manifest = tmp_path / "public_benchmark_vina_gnina_input_manifest.csv"
    report = tmp_path / "report.json"

    payload = module.materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive(
        repo_root=tmp_path,
        archive_path=archive,
        template=template,
        extract_dir=Path("tmp/extracted"),
        out_manifest=manifest,
        out_report=report,
    )

    assert payload["status"] == "source_files_verified_prepared_inputs_required"
    assert payload["source_files_ready"] is True
    assert payload["manifest_ready"] is False
    assert payload["summary"]["source_file_verified_count"] == 2
    assert payload["summary"]["source_file_blocker_count"] == 0
    assert payload["summary"]["prepared_input_gap_count"] == 2
    assert payload["archive_index_summary"]["file_member_count"] == 2
    assert "does not download CASF payloads" in payload["claim_boundary"]
    rows = list(csv.DictReader(manifest.open("r", encoding="utf-8", newline="")))
    assert rows[0]["protein_structure_path"] == (
        "tmp/extracted/CASF-2016/coreset/1abc/1abc_protein.pdb"
    )
    assert rows[0]["reference_ligand_path"] == (
        "tmp/extracted/CASF-2016/coreset/1abc/1abc_ligand.sdf"
    )
    assert rows[0]["prepared_receptor_checksum"] == ""
    assert rows[0]["prepared_ligand_checksum"] == ""
    assert (
        tmp_path / "tmp/extracted/CASF-2016/coreset/1abc/1abc_protein.pdb"
    ).read_bytes() == protein
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == payload["status"]


def test_materialize_vina_gnina_input_manifest_blocks_checksum_mismatch(
    tmp_path: Path,
) -> None:
    protein = b"ATOM\n"
    ligand = b"ligand\n"
    archive = tmp_path / "CASF-2016.tar.gz"
    _write_tar(
        archive,
        {
            "CASF-2016/coreset/1abc/1abc_protein.pdb": b"WRONG\n",
            "CASF-2016/coreset/1abc/1abc_ligand.sdf": ligand,
        },
    )
    template = tmp_path / "template.csv"
    _write_template(
        template,
        [
            _template_row(
                protein_checksum=_checksum_bytes(protein),
                ligand_checksum=_checksum_bytes(ligand),
            )
        ],
    )

    payload = module.materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive(
        repo_root=tmp_path,
        archive_path=archive,
        template=template,
        extract_dir=Path("tmp/extracted"),
        out_manifest=tmp_path / "manifest.csv",
        out_report=tmp_path / "report.json",
    )

    assert payload["status"] == "source_file_extraction_blocked"
    assert payload["source_files_ready"] is False
    assert payload["summary"]["source_file_verified_count"] == 1
    assert payload["summary"]["source_file_blocker_count"] == 1
    blocked = [
        row
        for row in payload["source_file_rows"]
        if row["field"] == "protein_structure_path"
    ][0]
    assert blocked["blocker"] == "checksum_mismatch"


def test_materialize_vina_gnina_input_manifest_ignores_unsafe_tar_members(
    tmp_path: Path,
) -> None:
    protein = b"ATOM\n"
    ligand = b"ligand\n"
    archive = tmp_path / "CASF-2016.tar.gz"
    _write_tar(
        archive,
        {
            "../CASF-2016/coreset/1abc/1abc_protein.pdb": protein,
            "CASF-2016/coreset/1abc/1abc_ligand.sdf": ligand,
        },
    )
    template = tmp_path / "template.csv"
    _write_template(
        template,
        [
            _template_row(
                protein_checksum=_checksum_bytes(protein),
                ligand_checksum=_checksum_bytes(ligand),
            )
        ],
    )

    payload = module.materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive(
        repo_root=tmp_path,
        archive_path=archive,
        template=template,
        extract_dir=Path("tmp/extracted"),
        out_manifest=tmp_path / "manifest.csv",
        out_report=tmp_path / "report.json",
    )

    assert payload["status"] == "source_file_extraction_blocked"
    assert payload["archive_index_summary"]["unsafe_member_count"] == 1
    protein_row = [
        row
        for row in payload["source_file_rows"]
        if row["field"] == "protein_structure_path"
    ][0]
    assert protein_row["blocker"] == "archive_member_missing"
