from __future__ import annotations

import importlib.util
import hashlib
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


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _engine_run(engine_id: str, *, rmsd: float, pose_success: bool) -> dict[str, object]:
    return {
        "engine_id": engine_id,
        "docking_run_id": f"casf2016_1abc_{engine_id}_run",
        "predicted_ligand_path_or_pose_ref": (
            f"https://pdbbind.example.org/casf2016/1abc/{engine_id}_pose.sdf"
        ),
        "predicted_ligand_checksum": _checksum(f"1abc:{engine_id}:pose"),
        "engine_version": f"{engine_id} test 1.0",
        "engine_config_checksum": _checksum(f"1abc:{engine_id}:config"),
        "engine_run_provenance_ref": (
            f"https://pdbbind.example.org/casf2016/1abc/{engine_id}_run.json"
        ),
        "symmetry_aware_rmsd_angstrom": rmsd,
        "pose_success": pose_success,
        "score": -7.5,
        "score_direction": "lower_is_better",
    }


def _valid_rows(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "casf2016_1abc",
                        "source_family": "CASF/PDBBind + Vina/GNINA",
                        "benchmark_split": "CASF-core",
                        "complex_id": "1abc",
                        "reference_pose_id": "casf2016_1abc_reference",
                        "source_license_or_accession": "PDBbind+ CASF-2016 official package",
                        "source_checksum": _checksum("1abc:source"),
                        "provenance_ref": (
                            "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz"
                        ),
                        "engine_runs": [
                            _engine_run("vina", rmsd=1.4, pose_success=True),
                            _engine_run("gnina", rmsd=1.6, pose_success=True),
                        ],
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


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


def test_runtime_readiness_container_status_accepts_local_image(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE",
        "ghcr.io/acme/public-benchmark-vina:latest",
    )
    monkeypatch.setattr(module, "_docker_daemon_version", lambda executable: (True, "27.0.0"))
    monkeypatch.setattr(module, "_container_image_present", lambda executable, image: True)

    status = module._engine_container_status(
        "vina",
        docker_cli_status={
            "available": True,
            "executable": "/usr/bin/docker",
            "blocker": "",
        },
    )

    assert status["status"] == "ready"
    assert status["available"] is True
    assert status["image_env_var"] == "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE"
    assert status["docker_daemon_available"] is True
    assert status["image_present"] is True
    assert status["command_prefix"] == (
        "/usr/bin/docker run --rm -v $PWD:/work -w /work "
        "ghcr.io/acme/public-benchmark-vina:latest vina"
    )


def test_runtime_readiness_container_status_records_daemon_without_image(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE", raising=False)
    monkeypatch.setattr(
        module,
        "_docker_daemon_version",
        lambda executable: (True, "29.1.3"),
    )

    status = module._engine_container_status(
        "gnina",
        docker_cli_status={
            "available": True,
            "executable": "/usr/bin/docker",
            "blocker": "",
        },
    )

    assert status["status"] == "container_image_not_configured"
    assert status["available"] is False
    assert status["docker_daemon_available"] is True
    assert status["docker_server_version"] == "29.1.3"
    assert status["image_present"] is False
    assert status["blocker"] == ""


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
    assert payload["runtime_setup_requirements"] == {
        "accepted_runtime_sources": [
            "engine binary discovered on PATH",
            "engine binary path supplied by environment variable",
            "local Docker image supplied by environment variable",
        ],
        "binary_env_vars": {
            "vina": "PUBLIC_BENCHMARK_VINA_BIN",
            "gnina": "PUBLIC_BENCHMARK_GNINA_BIN",
        },
        "container_image_env_vars": {
            "vina": "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE",
            "gnina": "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE",
        },
        "docker_bin_env_var": "PUBLIC_BENCHMARK_DOCKER_BIN",
        "container_image_policy": (
            "Container fallback requires a local Docker image reference in the "
            "engine image env var; this readiness check inspects local images and "
            "does not pull images."
        ),
        "rows_artifact_required_after_engine_execution": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_rows.json"
        ),
    }
    assert payload["operator_commands"]["set_binary_overrides"] == (
        "export PUBLIC_BENCHMARK_VINA_BIN=<path-to-vina> "
        "PUBLIC_BENCHMARK_GNINA_BIN=<path-to-gnina>"
    )
    assert payload["operator_commands"]["set_container_image_overrides"] == (
        "export PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE=<local-vina-image> "
        "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE=<local-gnina-image>"
    )
    assert payload["operator_commands"]["rerun_runtime_readiness"] == (
        "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
        "--out implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_runtime_readiness.json"
    )
    assert payload["blockers"] == [
        "vina_binary_missing",
        "gnina_binary_missing",
        "public_benchmark_vina_gnina_rows_not_detected",
        "casf2016_1abc::vina::vina_binary_missing",
        "casf2016_1abc::gnina::gnina_binary_missing",
    ]
    assert payload["summary"] == {
        "adapter_rows_ready": False,
        "adapter_case_count": 0,
        "adapter_row_preflight_status": "row_artifact_missing",
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
        "selected_row_count": 0,
    }
    assert payload["engine_run_slots"][0]["status"] == "blocked"
    assert payload["engine_run_slots"][0]["engine_execution_source"] == ""
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
    unblock = payload["operator_unblock_packet"]
    assert unblock["status"] == "engine_runtime_required"
    assert unblock["input_manifest_template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template.csv"
    )
    assert unblock["case_input_slot_count"] == 1
    assert unblock["blocked_case_input_slot_count"] == 0
    assert unblock["required_engine_run_count"] == 2
    assert unblock["ready_engine_run_slot_count"] == 0
    assert unblock["blocked_engine_run_slot_count"] == 2
    assert unblock["missing_engine_ids"] == ["vina", "gnina"]
    assert unblock["first_blocked_engine_run_slot"]["engine_id"] == "vina"
    assert unblock["engine_runtime_actions"][0] == {
        "binary_env_var": "PUBLIC_BENCHMARK_VINA_BIN",
        "container_image_env_var": "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE",
        "engine_id": "vina",
        "operator_action": "configure_vina_runtime",
    }
    assert unblock["operator_sequence"][:2] == [
        "fill_public_benchmark_vina_gnina_input_manifest_from_template",
        "rerun_public_benchmark_vina_gnina_execution_plan",
    ]
    assert "does not run docking engines" in payload["claim_boundary"]


def test_runtime_readiness_uses_container_execution_when_binaries_missing(
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

    payload = module.build_vina_gnina_runtime_readiness(
        repo_root=tmp_path,
        execution_plan_path=execution_plan,
        vina_gnina_rows_path=rows,
    )

    assert payload["status"] == "ready_for_engine_execution"
    assert payload["runtime_ready_for_engine_execution"] is True
    assert payload["operator_execution_ready"] is False
    assert payload["missing_engine_ids"] == []
    assert payload["blockers"] == ["public_benchmark_vina_gnina_rows_not_detected"]
    assert payload["ready_engine_run_slot_count"] == 2
    assert payload["summary"]["available_engine_count"] == 2
    assert payload["summary"]["missing_engine_count"] == 0
    assert payload["engine_run_slots"][0]["engine_execution_source"] == "container"
    assert payload["engine_run_slots"][0]["engine_container_image"] == (
        "ghcr.io/acme/vina:latest"
    )
    assert payload["current_engine_execution_statuses"][0]["execution_source"] == (
        "container"
    )


def test_runtime_readiness_detects_ready_engine_slots_and_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    _execution_plan(execution_plan)
    _valid_rows(rows)

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
    assert payload["summary"]["adapter_case_count"] == 1
    assert payload["summary"]["selected_row_count"] == 1
    assert payload["summary"]["adapter_row_preflight_status"] == (
        "row_artifact_detected_validated"
    )
    assert payload["row_candidate_status"]["adapter_preflight"]["contract_pass"] is True
    assert payload["blockers"] == []


def test_runtime_readiness_blocks_empty_row_artifact(
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

    assert payload["status"] == "ready_for_engine_execution"
    assert payload["runtime_ready_for_engine_execution"] is True
    assert payload["operator_execution_ready"] is False
    assert payload["adapter_rows_ready"] is False
    assert payload["blockers"] == ["public_benchmark_vina_gnina_rows_empty"]
    assert payload["row_candidate_status"]["status"] == "row_artifact_detected_empty"
    assert payload["row_candidate_status"]["adapter_preflight"]["blockers"] == [
        "vina_gnina_comparison_cases_missing",
        "vina_gnina_engine_runs_missing",
        "vina_gnina_external_receipts_missing",
    ]


def test_runtime_readiness_blocks_case_input_blockers_with_available_engines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    _execution_plan(execution_plan)
    plan_payload = json.loads(execution_plan.read_text(encoding="utf-8"))
    plan_payload["execution_plan_ready"] = False
    plan_payload["case_execution_plans"][0]["blockers"] = [
        "prepared_receptor_path_missing",
        "prepared_ligand_path_missing",
    ]
    execution_plan.write_text(json.dumps(plan_payload), encoding="utf-8")

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

    assert payload["status"] == "execution_plan_blocked"
    assert payload["runtime_ready_for_engine_execution"] is False
    assert payload["ready_engine_run_slot_count"] == 0
    assert payload["missing_engine_ids"] == []
    assert payload["blockers"] == [
        "vina_gnina_execution_plan_not_ready",
        "public_benchmark_vina_gnina_rows_not_detected",
        "casf2016_1abc::vina::prepared_receptor_path_missing",
        "casf2016_1abc::vina::prepared_ligand_path_missing",
        "casf2016_1abc::gnina::prepared_receptor_path_missing",
        "casf2016_1abc::gnina::prepared_ligand_path_missing",
    ]
    assert payload["engine_run_slots"][0]["case_inputs_ready"] is False
    assert payload["engine_run_slots"][0]["status"] == "blocked"
    unblock = payload["operator_unblock_packet"]
    assert unblock["status"] == "engine_inputs_required"
    assert unblock["blocked_case_input_slot_count"] == 1
    assert unblock["first_blocked_case_input_slot"] == {
        "blockers": [
            "prepared_receptor_path_missing",
            "prepared_ligand_path_missing",
        ],
        "case_id": "casf2016_1abc",
        "case_inputs_ready": False,
        "complex_id": "1abc",
        "input_manifest_template_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_input_manifest_template.csv"
        ),
        "operator_action": (
            "fill_vina_gnina_input_manifest_row_for_casf2016_1abc"
        ),
        "status": "blocked",
    }


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
