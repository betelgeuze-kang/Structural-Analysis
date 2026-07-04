from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_engine_run_bundle.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_engine_run_bundle",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _run(engine_id: str) -> dict[str, object]:
    run_root = f"operator_attached/vina_gnina/casf2016_1abc/{engine_id}"
    return {
        "engine_id": engine_id,
        "docking_run_id": f"casf2016_1abc_{engine_id}_run",
        "docking_box": {
            "status": "ready",
            "center": {"x": 1.0, "y": 2.0, "z": 3.0},
            "size": {"x": 20.0, "y": 21.0, "z": 22.0},
        },
        "prepared_receptor_path": "operator_inputs/1abc/receptor.pdbqt",
        "prepared_ligand_path": "operator_inputs/1abc/ligand.pdbqt",
        "expected_predicted_ligand_path_or_pose_ref": f"{run_root}_pose.sdf",
        "expected_engine_config_ref": f"{run_root}_config.json",
        "expected_engine_run_provenance_ref": f"{run_root}_run_receipt.json",
    }


def _write_ready_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "execution_plan_ready": True,
                "operator_execution_ready": False,
                "missing_engine_ids": ["vina", "gnina"],
                "engine_execution_statuses": [
                    {
                        "engine_id": engine_id,
                        "available": False,
                        "command_prefix": "",
                        "version": "",
                    }
                    for engine_id in ("vina", "gnina")
                ],
                "case_execution_plans": [
                    {
                        "case_id": "casf2016_1abc",
                        "complex_id": "1abc",
                        "source_license_or_accession": (
                            "PDBbind+ CASF-2016 official package"
                        ),
                        "subset_source_checksum": "sha256:" + "a" * 64,
                        "provenance_ref": "https://www.pdbbind-plus.org.cn/casf",
                        "engine_runs": [_run("vina"), _run("gnina")],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_materializes_vina_gnina_engine_run_bundle_from_ready_plan(
    tmp_path: Path,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    out = tmp_path / "bundle.json"
    commands_out = tmp_path / "commands.sh"
    _write_ready_plan(execution_plan)

    report = module.materialize_public_benchmark_vina_gnina_engine_run_bundle(
        repo_root=tmp_path,
        execution_plan=execution_plan,
        out=out,
        commands_out=commands_out,
    )

    assert report["status"] == "engine_run_bundle_materialized"
    assert report["contract_pass"] is True
    assert report["bundle_materialized"] is True
    assert report["case_count"] == 1
    assert report["engine_run_count"] == 2
    assert report["config_count"] == 2
    assert report["receipt_template_count"] == 2
    assert report["engine_runtime_ready"] is False
    assert report["engine_runtime_missing_ids"] == ["vina", "gnina"]
    first_row = report["bundle_rows"][0]
    config = json.loads((tmp_path / first_row["config_ref"]).read_text())
    receipt = json.loads((tmp_path / first_row["receipt_template_ref"]).read_text())
    assert config["schema_version"] == "public-benchmark-vina-gnina-engine-config.v1"
    assert config["docking_box"]["center"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert receipt["status"] == "operator_run_required"
    assert receipt["engine_config_checksum"] == first_row["config_checksum"]
    commands = commands_out.read_text(encoding="utf-8")
    assert "--center_x 1.0 --center_y 2.0 --center_z 3.0" in commands
    assert "<PUBLIC_BENCHMARK_VINA_BIN_OR_CONTAINER>" in commands
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "engine_run_bundle_materialized"
    )


def test_vina_gnina_engine_run_bundle_blocks_when_plan_not_ready(
    tmp_path: Path,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    out = tmp_path / "bundle.json"
    commands_out = tmp_path / "commands.sh"
    execution_plan.write_text(
        json.dumps(
            {
                "execution_plan_ready": False,
                "operator_execution_ready": False,
                "missing_engine_ids": ["vina"],
                "blockers": ["casf2016_1abc::prepared_receptor_path_missing"],
                "case_execution_plans": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    report = module.materialize_public_benchmark_vina_gnina_engine_run_bundle(
        repo_root=tmp_path,
        execution_plan=execution_plan,
        out=out,
        commands_out=commands_out,
    )

    assert report["status"] == "execution_plan_not_ready"
    assert report["contract_pass"] is False
    assert report["bundle_materialized"] is False
    assert report["blockers"] == [
        "public_benchmark_vina_gnina_execution_plan_not_ready"
    ]
    assert not commands_out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "execution_plan_not_ready"
    )
