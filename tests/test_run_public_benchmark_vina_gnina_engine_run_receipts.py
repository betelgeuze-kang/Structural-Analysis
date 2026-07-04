from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import stat
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_public_benchmark_vina_gnina_engine_run_receipts.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "run_public_benchmark_vina_gnina_engine_run_receipts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sdf_with_property(prop_name: str, prop_value: str) -> str:
    return "\n".join(
        [
            "pose",
            "test",
            "",
            "  1  0  0  0  0  0            999 V2000",
            "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0",
            "M  END",
            f">  <{prop_name}>",
            prop_value,
            "",
            "$$$$",
            "",
        ]
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(module._json_text(payload), encoding="utf-8")


def _write_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "reference_ligand_path",
                "prepared_ligand_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "case_a",
                "reference_ligand_path": "source/case_a_ligand.sdf",
                "prepared_ligand_path": "tmp/prepared/case_a/case_a_ligand.pdbqt",
            }
        )


def test_runs_bundle_command_and_completes_receipt(tmp_path: Path) -> None:
    reference = tmp_path / "tmp" / "prepared" / "case_a" / "case_a_ligand_query_free.sdf"
    reference.parent.mkdir(parents=True)
    reference.write_text(_sdf_with_property("unused", "0"), encoding="utf-8")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest)

    pose_ref = Path("operator_attached/vina_gnina/case_a/vina_pose.sdf")
    fake_engine = tmp_path / "fake_engine.py"
    fake_engine.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "import sys",
                "out = Path(sys.argv[sys.argv.index('--out') + 1])",
                "out.parent.mkdir(parents=True, exist_ok=True)",
                f"out.write_text({_sdf_with_property('meeko', json.dumps({'free_energy': -7.25}))!r}, encoding='utf-8')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_engine.chmod(fake_engine.stat().st_mode | stat.S_IEXEC)

    config_ref = Path("operator_attached/vina_gnina/case_a/vina_config.json")
    receipt_ref = Path("operator_attached/vina_gnina/case_a/vina_run_receipt.json")
    config_payload = {
        "case_id": "case_a",
        "complex_id": "case_a",
        "engine_id": "vina",
    }
    _write_json(tmp_path / config_ref, config_payload)
    config_checksum = module._sha256_text(module._json_text(config_payload))
    _write_json(
        tmp_path / receipt_ref,
        {
            "status": "operator_run_required",
            "case_id": "case_a",
            "complex_id": "case_a",
            "engine_id": "vina",
            "docking_run_id": "case_a_vina_run",
            "command": f"{sys.executable} {fake_engine} --out {pose_ref}",
            "predicted_ligand_path_or_pose_ref": str(pose_ref),
            "engine_config_checksum": config_checksum,
            "engine_version": "fake-vina",
            "score_direction": "lower_is_better",
        },
    )
    bundle = tmp_path / "bundle.json"
    _write_json(
        bundle,
        {
            "bundle_materialized": True,
            "bundle_rows": [
                {
                    "case_id": "case_a",
                    "complex_id": "case_a",
                    "engine_id": "vina",
                    "docking_run_id": "case_a_vina_run",
                    "command": f"{sys.executable} {fake_engine} --out {pose_ref}",
                    "config_ref": str(config_ref),
                    "config_checksum": config_checksum,
                    "receipt_template_ref": str(receipt_ref),
                    "predicted_ligand_path_or_pose_ref": str(pose_ref),
                    "prepared_ligand_path": "tmp/prepared/case_a/case_a_ligand.pdbqt",
                }
            ],
        },
    )

    report = module.run_public_benchmark_vina_gnina_engine_run_receipts(
        repo_root=tmp_path,
        engine_run_bundle=Path("bundle.json"),
        input_manifest=Path("manifest.csv"),
        out_report=Path("report.json"),
        timeout_seconds=30,
    )

    assert report["status"] == "engine_run_receipts_complete"
    assert report["completed_run_count"] == 1
    receipt = json.loads((tmp_path / receipt_ref).read_text(encoding="utf-8"))
    assert receipt["status"] == "engine_run_complete"
    assert receipt["predicted_ligand_checksum"].startswith("sha256:")
    assert receipt["score"] == -7.25
    assert receipt["score_source"] == "sdf_property:meeko.free_energy"
    assert receipt["pose_success"] is True
    assert receipt["symmetry_aware_rmsd_angstrom"] == 0.0


def test_extracts_gnina_minimized_affinity_from_first_pose(tmp_path: Path) -> None:
    pose = tmp_path / "gnina_pose.sdf"
    pose.write_text(_sdf_with_property("minimizedAffinity", "-5.5"), encoding="utf-8")

    score, source = module._score_from_pose_sdf(pose, "gnina")

    assert score == -5.5
    assert source == "sdf_property:minimizedAffinity"
