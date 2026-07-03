from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_public_benchmark_vina_gnina_execution_plan.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_vina_gnina_execution_plan", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_rows(root: Path) -> tuple[Path, Path]:
    subset_rows = root / "subset_rows.json"
    pose_rows = root / "pose_rows.json"
    subset_rows.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": "casf2016_1abc",
                        "complex_id": "1abc",
                        "benchmark_split": "CASF-core",
                        "protein_structure_path": "CASF-2016/coreset/1abc/1abc_protein.pdb",
                        "reference_ligand_path": "CASF-2016/coreset/1abc/1abc_ligand.sdf",
                        "source_checksum": "sha256:" + "1" * 64,
                        "source_license_or_accession": "PDBbind+ CASF-2016 official package",
                        "provenance_ref": "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz",
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pose_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "casf2016_1abc",
                        "reference_atoms": [
                            {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
                            {"element": "O", "x": 2.0, "y": 1.0, "z": 0.5},
                        ],
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return subset_rows, pose_rows


def test_vina_gnina_execution_plan_engine_status_accepts_env_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "custom-vina"
    binary.write_text("#!/bin/sh\necho 'vina custom 1.2.3'\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PUBLIC_BENCHMARK_VINA_BIN", str(binary))

    status = module._engine_binary_status("vina")

    assert status["available"] is True
    assert status["executable"] == str(binary)
    assert status["binary_source"] == "env:PUBLIC_BENCHMARK_VINA_BIN"
    assert status["env_var"] == "PUBLIC_BENCHMARK_VINA_BIN"
    assert status["version"] == "vina custom 1.2.3"
    assert status["blocker"] == ""


def test_vina_gnina_execution_plan_engine_status_blocks_bad_env_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PUBLIC_BENCHMARK_GNINA_BIN", str(tmp_path / "missing-gnina"))

    status = module._engine_binary_status("gnina")

    assert status["available"] is False
    assert status["binary_source"] == "env:PUBLIC_BENCHMARK_GNINA_BIN"
    assert status["blocker"] == "gnina_binary_not_found"


def test_vina_gnina_execution_plan_builds_case_run_specs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subset_rows, pose_rows = _write_rows(tmp_path)

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

    payload = module.build_vina_gnina_execution_plan(
        repo_root=tmp_path,
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
        vina_gnina_rows_out=tmp_path / "vina_gnina_rows.json",
    )

    assert payload["schema_version"] == "public-benchmark-vina-gnina-execution-plan.v1"
    assert payload["status"] == "ready_for_engine_execution"
    assert payload["contract_pass"] is True
    assert payload["execution_plan_ready"] is True
    assert payload["operator_execution_ready"] is True
    assert payload["adapter_rows_ready"] is False
    assert payload["case_count"] == 1
    assert payload["required_engine_run_count"] == 2
    assert payload["missing_engine_ids"] == []
    case_plan = payload["case_execution_plans"][0]
    assert case_plan["case_id"] == "casf2016_1abc"
    assert case_plan["reference_pose_id"] == "casf2016_1abc_reference"
    assert case_plan["docking_box"]["status"] == "ready"
    assert case_plan["docking_box"]["center"] == {"x": 1.0, "y": 0.5, "z": 0.25}
    assert case_plan["docking_box"]["size"] == {"x": 18.0, "y": 17.0, "z": 16.5}
    assert [run["engine_id"] for run in case_plan["engine_runs"]] == ["vina", "gnina"]
    assert case_plan["engine_runs"][0]["expected_adapter_engine_run_fields"] == list(
        module.REQUIRED_ENGINE_RUN_FIELDS
    )
    assert "does not run Vina or GNINA" in payload["claim_boundary"]


def test_vina_gnina_execution_plan_records_missing_engine_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subset_rows, pose_rows = _write_rows(tmp_path)

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

    payload = module.build_vina_gnina_execution_plan(
        repo_root=tmp_path,
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
    )

    assert payload["status"] == "engine_execution_required"
    assert payload["execution_plan_ready"] is True
    assert payload["operator_execution_ready"] is False
    assert payload["missing_engine_ids"] == ["vina", "gnina"]
    assert payload["blockers"] == ["vina_binary_missing", "gnina_binary_missing"]
    assert payload["summary"]["required_engine_run_count"] == 2
    assert payload["summary"]["missing_engine_count"] == 2


def test_vina_gnina_execution_plan_accepts_container_execution_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subset_rows, pose_rows = _write_rows(tmp_path)

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
    monkeypatch.setattr(
        module,
        "_engine_container_status",
        lambda engine_id, docker_cli_status=None: {
            "engine_id": engine_id,
            "available": True,
            "image": f"ghcr.io/acme/{engine_id}:latest",
            "docker_executable": "/usr/bin/docker",
            "docker_daemon_available": True,
            "docker_server_version": "27.0.0",
            "image_present": True,
            "command_prefix": (
                f"/usr/bin/docker run --rm -v $PWD:/work -w /work "
                f"ghcr.io/acme/{engine_id}:latest {engine_id}"
            ),
            "blocker": "",
        },
    )

    payload = module.build_vina_gnina_execution_plan(
        repo_root=tmp_path,
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
    )

    assert payload["status"] == "ready_for_engine_execution"
    assert payload["operator_execution_ready"] is True
    assert payload["missing_engine_ids"] == []
    assert payload["blockers"] == []
    assert payload["summary"]["available_engine_count"] == 2
    assert payload["engine_execution_statuses"][0]["execution_source"] == "container"
    assert payload["engine_execution_statuses"][0]["container_image"] == (
        "ghcr.io/acme/vina:latest"
    )
    case_plan = payload["case_execution_plans"][0]
    assert case_plan["engine_runs"][0]["container_image_env_var"] == (
        "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE"
    )
    assert "docker run --rm" in case_plan["engine_runs"][0][
        "container_command_template"
    ]


def test_vina_gnina_execution_plan_cli_writes_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subset_rows, pose_rows = _write_rows(tmp_path)
    out = tmp_path / "execution_plan.json"

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

    assert (
        module.main(
            [
                "--repo-root",
                str(tmp_path),
                "--subset-rows",
                str(subset_rows),
                "--pose-rows",
                str(pose_rows),
                "--out",
                str(out),
            ]
        )
        == 0
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["case_count"] == 1
    assert payload["required_engine_run_count"] == 2
