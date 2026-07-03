from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_public_benchmark_vina_gnina_runtime_readiness.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_vina_gnina_runtime_readiness",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _execution_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "execution_plan_ready": True,
                "case_count": 1,
                "required_engine_run_count": 2,
                "case_execution_plans": [
                    {
                        "case_id": "casf2016_1abc",
                        "complex_id": "1abc",
                        "engine_runs": [
                            {
                                "engine_id": "vina",
                                "docking_run_id": "casf2016_1abc_vina_run",
                                "docking_box": {"status": "ready"},
                                "command_template": (
                                    "<vina> --receptor <prepared/1abc_receptor> "
                                    "--ligand <prepared/1abc_ligand>"
                                ),
                                "expected_predicted_ligand_path_or_pose_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "vina_pose.sdf"
                                ),
                                "expected_engine_config_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "vina_config.json"
                                ),
                                "expected_engine_run_provenance_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "vina_run_receipt.json"
                                ),
                            },
                            {
                                "engine_id": "gnina",
                                "docking_run_id": "casf2016_1abc_gnina_run",
                                "docking_box": {"status": "ready"},
                                "command_template": (
                                    "<gnina> --receptor <prepared/1abc_receptor> "
                                    "--ligand <prepared/1abc_ligand>"
                                ),
                                "expected_predicted_ligand_path_or_pose_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "gnina_pose.sdf"
                                ),
                                "expected_engine_config_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "gnina_config.json"
                                ),
                                "expected_engine_run_provenance_ref": (
                                    "operator_attached/vina_gnina/casf2016_1abc/"
                                    "gnina_run_receipt.json"
                                ),
                            },
                        ],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_runtime_readiness_engine_status_accepts_env_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "custom-gnina"
    binary.write_text("#!/bin/sh\necho 'gnina custom 2.0'\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PUBLIC_BENCHMARK_GNINA_BIN", str(binary))

    status = module._engine_binary_status("gnina")

    assert status["available"] is True
    assert status["executable"] == str(binary)
    assert status["binary_source"] == "env:PUBLIC_BENCHMARK_GNINA_BIN"
    assert status["env_var"] == "PUBLIC_BENCHMARK_GNINA_BIN"
    assert status["version"] == "gnina custom 2.0"
    assert status["blocker"] == ""


def test_runtime_readiness_engine_status_blocks_non_executable_env_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "custom-vina"
    binary.write_text("#!/bin/sh\necho 'vina custom'\n", encoding="utf-8")
    monkeypatch.setenv("PUBLIC_BENCHMARK_VINA_BIN", str(binary))

    status = module._engine_binary_status("vina")

    assert status["available"] is False
    assert status["binary_source"] == "env:PUBLIC_BENCHMARK_VINA_BIN"
    assert status["blocker"] == "vina_binary_not_executable"


def test_runtime_readiness_records_missing_binaries_and_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    _execution_plan(execution_plan)

    monkeypatch.setattr(
        module,
        "_engine_binary_status",
        lambda engine_id: {
            "engine_id": engine_id,
            "available": False,
            "executable": "",
            "version": "",
            "blocker": f"{engine_id}_binary_missing",
        },
    )

    payload = module.build_vina_gnina_runtime_readiness(
        repo_root=tmp_path,
        execution_plan_path=execution_plan,
        vina_gnina_rows_path=rows,
    )

    assert payload["schema_version"] == (
        "public-benchmark-vina-gnina-runtime-readiness.v1"
    )
    assert payload["status"] == "engine_runtime_blocked"
    assert payload["contract_pass"] is True
    assert payload["execution_plan_ready"] is True
    assert payload["runtime_ready_for_engine_execution"] is False
    assert payload["operator_execution_ready"] is False
    assert payload["adapter_rows_ready"] is False
    assert payload["phase2_closure_ready"] is False
    assert payload["missing_engine_ids"] == ["vina", "gnina"]
    assert payload["blockers"] == [
        "vina_binary_missing",
        "gnina_binary_missing",
        "public_benchmark_vina_gnina_rows_not_detected",
        "casf2016_1abc::vina::vina_binary_missing",
        "casf2016_1abc::gnina::gnina_binary_missing",
    ]
    assert payload["summary"] == {
        "adapter_rows_ready": False,
        "available_engine_count": 0,
        "blocker_count": 5,
        "case_count": 1,
        "detected_row_artifact_count": 0,
        "execution_plan_ready": True,
        "missing_engine_count": 2,
        "operator_execution_ready": False,
        "ready_engine_run_slot_count": 0,
        "required_engine_run_count": 2,
        "runtime_ready_for_engine_execution": False,
    }
    assert payload["engine_run_slots"][0]["status"] == "blocked"
    assert payload["engine_run_slots"][0]["required_adapter_engine_run_fields"] == [
        "engine_id",
        "docking_run_id",
        "predicted_ligand_path_or_pose_ref",
        "predicted_ligand_checksum",
        "engine_version",
        "engine_config_checksum",
        "engine_run_provenance_ref",
        "symmetry_aware_rmsd_angstrom",
        "pose_success",
        "score",
        "score_direction",
    ]
    assert "does not run docking engines" in payload["claim_boundary"]


def test_runtime_readiness_detects_ready_engine_slots_and_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    _execution_plan(execution_plan)
    rows.write_text('{"cases":[]}', encoding="utf-8")

    monkeypatch.setattr(
        module,
        "_engine_binary_status",
        lambda engine_id: {
            "engine_id": engine_id,
            "available": True,
            "executable": f"/usr/bin/{engine_id}",
            "version": f"{engine_id} test",
            "blocker": "",
        },
    )

    payload = module.build_vina_gnina_runtime_readiness(
        repo_root=tmp_path,
        execution_plan_path=execution_plan,
        vina_gnina_rows_path=rows,
    )

    assert payload["status"] == "adapter_materialization_ready"
    assert payload["runtime_ready_for_engine_execution"] is True
    assert payload["operator_execution_ready"] is True
    assert payload["adapter_rows_ready"] is True
    assert payload["ready_engine_run_slot_count"] == 2
    assert payload["summary"]["detected_row_artifact_count"] == 1
    assert payload["blockers"] == []


def test_runtime_readiness_cli_writes_artifact(tmp_path: Path, monkeypatch) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    out = tmp_path / "runtime_readiness.json"
    _execution_plan(execution_plan)

    monkeypatch.setattr(
        module,
        "_engine_binary_status",
        lambda engine_id: {
            "engine_id": engine_id,
            "available": False,
            "executable": "",
            "version": "",
            "blocker": f"{engine_id}_binary_missing",
        },
    )

    assert module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-plan",
            str(execution_plan),
            "--vina-gnina-rows",
            str(rows),
            "--out",
            str(out),
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "engine_runtime_blocked"
    assert payload["summary"]["required_engine_run_count"] == 2
