from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_prepared_inputs.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_prepared_inputs",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_tool(path: Path, output_arg: str, content: str) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "import sys",
                f"flag = {output_arg!r}",
                "out = Path(sys.argv[sys.argv.index(flag) + 1])",
                "out.parent.mkdir(parents=True, exist_ok=True)",
                f"out.write_text({content!r}, encoding='utf-8')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_materializes_prepared_inputs_and_updates_manifest(tmp_path: Path) -> None:
    protein = tmp_path / "source" / "1abc_protein.pdb"
    ligand = tmp_path / "source" / "1abc_ligand.sdf"
    protein.parent.mkdir(parents=True)
    protein.write_text("ATOM\n", encoding="utf-8")
    ligand.write_text(
        "\n".join(
            [
                "lig",
                "test",
                "",
                "  1  0  0  0  0  0            999 V2000",
                "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0",
                "M  END",
                "$$$$",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.csv"
    header = [
        "case_id",
        "complex_id",
        "protein_structure_path",
        "reference_ligand_path",
        "prepared_receptor_path",
        "prepared_receptor_checksum",
        "prepared_ligand_path",
        "prepared_ligand_checksum",
        "input_preparation_provenance_ref",
    ]
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "casf2016_1abc",
                "complex_id": "1abc",
                "protein_structure_path": "source/1abc_protein.pdb",
                "reference_ligand_path": "source/1abc_ligand.sdf",
            }
        )
    ligand_tool = tmp_path / "mk_prepare_ligand.py"
    receptor_tool = tmp_path / "mk_prepare_receptor.py"
    _write_tool(ligand_tool, "-o", "ligand pdbqt\n")
    _write_tool(receptor_tool, "-p", "receptor pdbqt\n")
    report = tmp_path / "report.json"

    payload = module.materialize_public_benchmark_vina_gnina_prepared_inputs(
        repo_root=tmp_path,
        in_manifest=Path("manifest.csv"),
        out_manifest=Path("manifest.csv"),
        out_report=Path("report.json"),
        prepared_dir=Path("tmp/prepared"),
        ligand_preparer=ligand_tool,
        receptor_preparer=receptor_tool,
    )

    assert payload["status"] == "prepared_inputs_ready"
    assert payload["prepared_inputs_ready"] is True
    assert payload["ready_case_count"] == 1
    assert payload["prepared_input_count"] == 2
    rows = list(csv.DictReader(manifest.open("r", encoding="utf-8", newline="")))
    assert rows[0]["prepared_receptor_path"] == (
        "tmp/prepared/casf2016_1abc/1abc_receptor.pdbqt"
    )
    assert rows[0]["prepared_receptor_checksum"] == _checksum_text("receptor pdbqt\n")
    assert rows[0]["prepared_ligand_path"] == (
        "tmp/prepared/casf2016_1abc/1abc_ligand.pdbqt"
    )
    assert rows[0]["prepared_ligand_checksum"] == _checksum_text("ligand pdbqt\n")
    assert rows[0]["input_preparation_provenance_ref"] == "report.json"
    persisted = json.loads(report.read_text(encoding="utf-8"))
    assert persisted["status"] == "prepared_inputs_ready"
    assert persisted["case_rows"][0]["ligand_normalization"]["status"] == "ready"


def test_blocks_when_source_files_are_missing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    header = [
        "case_id",
        "complex_id",
        "protein_structure_path",
        "reference_ligand_path",
        "prepared_receptor_path",
        "prepared_receptor_checksum",
        "prepared_ligand_path",
        "prepared_ligand_checksum",
        "input_preparation_provenance_ref",
    ]
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "casf2016_1abc",
                "complex_id": "1abc",
                "protein_structure_path": "missing_protein.pdb",
                "reference_ligand_path": "missing_ligand.sdf",
            }
        )
    tool = tmp_path / "tool.py"
    _write_tool(tool, "-o", "unused\n")

    payload = module.materialize_public_benchmark_vina_gnina_prepared_inputs(
        repo_root=tmp_path,
        in_manifest=Path("manifest.csv"),
        out_manifest=Path("manifest.csv"),
        out_report=Path("report.json"),
        prepared_dir=Path("tmp/prepared"),
        ligand_preparer=tool,
        receptor_preparer=tool,
    )

    assert payload["status"] == "prepared_input_materialization_blocked"
    assert payload["contract_pass"] is False
    assert payload["ready_case_count"] == 0
    assert payload["case_rows"][0]["blockers"] == [
        "protein_structure_file_missing",
        "reference_ligand_file_missing",
    ]
