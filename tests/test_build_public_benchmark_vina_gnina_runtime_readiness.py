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


def test_runtime_readiness_compacts_input_manifest_source_url_probe(
    tmp_path: Path,
) -> None:
    preflight = tmp_path / module.DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT
    preflight.parent.mkdir(parents=True)
    preflight.write_text(
        json.dumps(
            {
                "status": "operator_manifest_completion_required",
                "manifest_ready": False,
                "summary": {
                    "template_row_count": 12,
                    "template_case_coverage_complete": True,
                    "source_url_probe_count": 1,
                    "source_url_probe_network_performed": True,
                    "source_url_reachable_count": 1,
                    "source_url_blocked_count": 0,
                    "source_url_not_run_count": 0,
                    "known_source_url_content_length_bytes": 1_572_660_769,
                    "known_source_url_content_length_gib": 1.465,
                },
                "source_url_probe_plan": [
                    {
                        "source_url": (
                            "https://static.pdbbind-plus.org.cn/download/"
                            "CASF-2016.tar.gz"
                        ),
                        "status": "reachable",
                        "case_ids": ["casf2016_1abc", "casf2016_2abc"],
                        "head_command": "curl --head CASF-2016.tar.gz",
                        "probe": {
                            "content_length_bytes": 1_572_660_769,
                            "http_status": 200,
                        },
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    summary = module._input_manifest_template_preflight_summary(tmp_path)

    assert summary["source_url_probe_network_performed"] is True
    assert summary["known_source_url_content_length_bytes"] == 1_572_660_769
    assert summary["known_source_url_content_length_gib"] == 1.465
    assert summary["source_url_probe_plan"] == [
        {
            "case_count": 2,
            "content_length_bytes": 1_572_660_769,
            "head_command": "curl --head CASF-2016.tar.gz",
            "http_status": 200,
            "source_url": (
                "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz"
            ),
            "status": "reachable",
        }
    ]


def test_runtime_readiness_compacts_input_manifest_completion_action_plan(
    tmp_path: Path,
) -> None:
    preflight = tmp_path / module.DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT
    preflight.parent.mkdir(parents=True)
    preflight.write_text(
        json.dumps(
            {
                "status": "operator_manifest_completion_required",
                "manifest_ready": False,
                "summary": {
                    "template_row_count": 1,
                    "template_case_coverage_complete": True,
                    "missing_required_value_count": 3,
                    "missing_local_file_count": 4,
                    "missing_receipt_ref_count": 5,
                },
                "case_preflight_rows": [
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "status": "operator_completion_required",
                        "missing_required_fields": [
                            "prepared_receptor_checksum",
                            "prepared_ligand_checksum",
                            "input_preparation_provenance_ref",
                        ],
                        "missing_local_file_fields": [
                            "protein_structure_path",
                            "reference_ligand_path",
                            "prepared_receptor_path",
                            "prepared_ligand_path",
                        ],
                        "missing_receipt_ref_fields": [
                            "vina_config_ref",
                            "gnina_config_ref",
                            "vina_run_receipt_ref",
                            "gnina_run_receipt_ref",
                            "input_preparation_provenance_ref",
                        ],
                        "local_file_requirements": [
                            {
                                "case_id": "casf2016_4llx",
                                "complex_id": "4llx",
                                "field": "protein_structure_path",
                                "file_role": "source_protein_structure",
                                "file_group": "official_source_file",
                                "path": "CASF-2016/coreset/4llx/4llx_protein.pdb",
                                "expected_checksum_field": (
                                    "protein_structure_checksum"
                                ),
                                "expected_checksum": "sha256:" + "a" * 64,
                                "source_url": (
                                    "https://static.pdbbind-plus.org.cn/download/"
                                    "CASF-2016.tar.gz"
                                ),
                                "source_license_or_accession": (
                                    "PDBbind+ CASF-2016 official package"
                                ),
                                "status": "operator_completion_required",
                                "blocker": "path_not_found",
                                "operator_action": (
                                    "materialize_source_files_from_casf_archive_"
                                    "and_verify_checksum"
                                ),
                            },
                            {
                                "case_id": "casf2016_4llx",
                                "complex_id": "4llx",
                                "field": "prepared_ligand_path",
                                "file_role": "prepared_ligand",
                                "file_group": "prepared_input_file",
                                "path": "prepared/4llx_ligand",
                                "expected_checksum_field": (
                                    "prepared_ligand_checksum"
                                ),
                                "expected_checksum": "sha256:" + "b" * 64,
                                "source_url": "",
                                "source_license_or_accession": "",
                                "status": "ready",
                                "blocker": "",
                                "operator_action": (
                                    "verify_prepared_input_file_checksum"
                                ),
                            },
                        ],
                        "receipt_ref_requirements": [
                            {
                                "case_id": "casf2016_4llx",
                                "complex_id": "4llx",
                                "field": "vina_config_ref",
                                "ref": (
                                    "operator_attached/vina_gnina/"
                                    "casf2016_4llx/vina_config.json"
                                ),
                                "status": "operator_completion_required",
                                "blocker": "local_ref_not_found",
                                "operator_action": "attach_vina_config_ref",
                            }
                        ],
                        "blockers": [
                            "manifest_required_fields_missing",
                            "manifest_local_files_missing_or_unverified",
                            "manifest_receipt_refs_missing",
                        ],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    summary = module._input_manifest_template_preflight_summary(tmp_path)

    assert summary["input_manifest_completion_action_case_count"] == 1
    assert summary["input_manifest_completion_blocked_case_count"] == 1
    action = summary["input_manifest_completion_action_plan"][0]
    assert action["case_id"] == "casf2016_4llx"
    assert action["operator_completion_action"] == (
        "complete_vina_gnina_input_manifest_row_for_casf2016_4llx"
    )
    assert action["missing_required_field_count"] == 3
    assert action["missing_local_file_count"] == 4
    assert action["missing_receipt_ref_count"] == 5
    assert action["missing_local_file_requirements"] == [
        {
            "case_id": "casf2016_4llx",
            "complex_id": "4llx",
            "field": "protein_structure_path",
            "file_role": "source_protein_structure",
            "file_group": "official_source_file",
            "path": "CASF-2016/coreset/4llx/4llx_protein.pdb",
            "expected_checksum_field": "protein_structure_checksum",
            "expected_checksum": "sha256:" + "a" * 64,
            "source_url": (
                "https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz"
            ),
            "source_license_or_accession": (
                "PDBbind+ CASF-2016 official package"
            ),
            "status": "operator_completion_required",
            "blocker": "path_not_found",
            "operator_action": (
                "materialize_source_files_from_casf_archive_and_verify_checksum"
            ),
        }
    ]
    assert action["missing_receipt_ref_requirements"][0]["field"] == (
        "vina_config_ref"
    )


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
    assert payload["operator_commands"]["materialize_engine_run_bundle"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"
    )
    assert payload["operator_commands"]["build_rows_template_preflight"].startswith(
        "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"
    )
    assert payload["operator_commands"]["materialize_rows_from_template"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"
    )
    assert payload["operator_commands"][
        "materialize_rows_from_engine_run_bundle"
    ].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
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
        "blocked_case_input_slot_count": 0,
        "blocked_engine_run_slot_count": 2,
        "blocker_count": 5,
        "case_count": 1,
        "detected_row_artifact_count": 0,
        "engine_run_bundle_materialized": False,
        "engine_run_bundle_status": "missing",
        "execution_plan_ready": True,
        "first_blocked_case_input_case_id": "",
        "first_blocked_engine_run_case_id": "casf2016_1abc",
        "first_blocked_engine_run_engine_id": "vina",
        "input_manifest_completion_action_case_count": 0,
        "input_manifest_completion_blocked_case_count": 0,
        "input_manifest_template_invalid_source_receipt_count": 0,
        "input_manifest_template_manifest_ready": False,
        "input_manifest_template_missing_local_file_count": 0,
        "input_manifest_template_missing_receipt_ref_count": 0,
        "input_manifest_template_preflight_status": "missing",
        "missing_engine_count": 2,
        "operator_execution_ready": False,
        "operator_blocker_family_blocked_count": 3,
        "operator_blocker_family_count": 7,
        "operator_blocker_family_missing_item_count": 5,
        "ready_engine_run_slot_count": 0,
        "required_engine_run_count": 2,
        "rows_from_engine_run_bundle_materialized": False,
        "rows_from_engine_run_bundle_report_status": "missing",
        "runtime_ready_for_engine_execution": False,
        "selected_row_count": 0,
    }
    assert payload["blocked_case_input_slot_count"] == 0
    assert payload["blocked_engine_run_slot_count"] == 2
    assert payload["first_blocked_case_input_slot"] == {}
    assert payload["first_blocked_engine_run_slot"]["case_id"] == "casf2016_1abc"
    assert payload["first_blocked_engine_run_slot"]["engine_id"] == "vina"
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
    assert unblock["input_manifest_template_preflight_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
    )
    assert unblock["input_manifest_template_preflight_status"] == "missing"
    assert unblock["input_manifest_template_manifest_ready"] is False
    assert unblock["input_manifest_template_preflight_summary"] == {
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
        ),
        "first_blocked_case_preflight": {},
        "input_manifest_completion_action_case_count": 0,
        "input_manifest_completion_action_plan": [],
        "input_manifest_completion_blocked_case_count": 0,
        "invalid_checksum_count": 0,
        "invalid_source_receipt_count": 0,
        "known_source_url_content_length_bytes": 0,
        "known_source_url_content_length_gib": 0.0,
        "manifest_ready": False,
        "markdown_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_vina_gnina_input_manifest_template_preflight.md"
        ),
        "missing_local_file_count": 0,
        "missing_receipt_ref_count": 0,
        "missing_required_value_count": 0,
        "present": False,
        "source_url_blocked_count": 0,
        "source_url_not_run_count": 0,
        "source_url_probe_count": 0,
        "source_url_probe_network_performed": False,
        "source_url_probe_plan": [],
        "source_url_reachable_count": 0,
        "status": "missing",
        "template_case_coverage_complete": False,
        "template_row_count": 0,
        "unsupported_benchmark_field_count": 0,
    }
    assert unblock["input_manifest_completion_action_case_count"] == 0
    assert unblock["input_manifest_completion_blocked_case_count"] == 0
    assert unblock["input_manifest_completion_action_plan"] == []
    assert unblock["rows_template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows_template.csv"
    )
    assert unblock["rows_template_preflight_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows_template_preflight.json"
    )
    assert unblock["engine_run_bundle_status"] == "missing"
    assert unblock["engine_run_bundle_materialized"] is False
    assert unblock["rows_from_engine_run_bundle_status"] == "missing"
    assert unblock["rows_from_engine_run_bundle_materialized"] is False
    assert unblock["engine_run_bundle_summary"]["present"] is False
    assert unblock["rows_from_engine_run_bundle_report_summary"]["present"] is False
    assert unblock["commands"]["build_input_manifest_template_preflight"] == (
        "python3 scripts/"
        "build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
        "--out implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template_preflight.json "
        "--out-md implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_input_manifest_template_preflight.md"
    )
    assert unblock["commands"]["build_rows_template_preflight"] == (
        "python3 scripts/"
        "build_public_benchmark_vina_gnina_rows_template_preflight.py "
        "--out implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows_template_preflight.json "
        "--out-md implementation/phase1/release_evidence/productization/"
        "public_benchmark_vina_gnina_rows_template_preflight.md"
    )
    assert unblock["commands"]["materialize_engine_run_bundle"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"
    )
    assert unblock["commands"]["materialize_rows_from_template"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"
    )
    assert unblock["commands"]["materialize_rows_from_engine_run_bundle"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
    )
    assert unblock["commands"][
        "materialize_input_manifest_from_casf_archive"
    ].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
        "--archive <CASF-2016.tar.gz>"
    )
    assert "--fail-blocked" in unblock["commands"][
        "materialize_input_manifest_from_casf_archive"
    ]
    assert unblock["case_input_slot_count"] == 1
    assert unblock["blocked_case_input_slot_count"] == 0
    assert unblock["required_engine_run_count"] == 2
    assert unblock["ready_engine_run_slot_count"] == 0
    assert unblock["blocked_engine_run_slot_count"] == 2
    assert unblock["missing_engine_ids"] == ["vina", "gnina"]
    assert unblock["first_blocked_engine_run_slot"]["engine_id"] == "vina"
    assert unblock["operator_blocker_family_count"] == 7
    assert unblock["operator_blocker_family_blocked_count"] == 3
    assert unblock["operator_blocker_family_missing_item_count"] == 5
    assert unblock["first_operator_blocker_family"]["family_id"] == "engine_runtime"
    family_plan = {
        row["family_id"]: row for row in unblock["operator_blocker_family_plan"]
    }
    assert family_plan["engine_runtime"]["missing_item_count"] == 2
    assert family_plan["engine_runtime"]["next_action"] == (
        "configure_vina_gnina_binary_or_container_runtime"
    )
    assert family_plan["engine_runtime"]["command_key"] == "rerun_runtime_readiness"
    assert family_plan["engine_runtime"]["materialization_command"] == (
        unblock["commands"]["rerun_runtime_readiness"]
    )
    assert family_plan["engine_run_slots"]["missing_item_count"] == 2
    assert family_plan["adapter_rows"]["missing_item_count"] == 1
    assert family_plan["adapter_rows"]["next_action"] == (
        "attach_or_materialize_public_benchmark_vina_gnina_rows"
    )
    assert family_plan["adapter_rows"]["command_key"] == (
        "materialize_rows_from_engine_run_bundle"
    )
    assert family_plan["adapter_rows"]["materialization_command"] == (
        unblock["commands"]["materialize_rows_from_engine_run_bundle"]
    )
    assert payload["operator_blocker_family_count"] == 7
    assert payload["operator_blocker_family_blocked_count"] == 3
    assert payload["first_operator_blocker_family"]["family_id"] == "engine_runtime"
    assert payload["first_operator_blocker_family"]["materialization_command"] == (
        payload["operator_commands"]["rerun_runtime_readiness"]
    )
    assert unblock["engine_runtime_actions"][0] == {
        "binary_env_var": "PUBLIC_BENCHMARK_VINA_BIN",
        "container_image_env_var": "PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE",
        "engine_id": "vina",
        "operator_action": "configure_vina_runtime",
    }
    assert unblock["operator_sequence"][:3] == [
        "review_public_benchmark_vina_gnina_input_manifest_template_preflight",
        "fill_public_benchmark_vina_gnina_input_manifest_from_template",
        "rerun_public_benchmark_vina_gnina_execution_plan",
    ]
    assert "review_public_benchmark_vina_gnina_rows_template_preflight" in unblock[
        "operator_sequence"
    ]
    assert "materialize_public_benchmark_vina_gnina_engine_run_bundle" in unblock[
        "operator_sequence"
    ]
    assert "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle" in (
        unblock["operator_sequence"]
    )
    assert "materialize_public_benchmark_vina_gnina_rows_from_completed_template" in (
        unblock["operator_sequence"]
    )
    assert "does not run docking engines" in payload["claim_boundary"]


def test_runtime_readiness_groups_manifest_operator_blocker_families() -> None:
    manifest_summary = {
        "input_manifest_completion_action_plan": [
            {
                "case_id": "casf2016_4llx",
                "complex_id": "4llx",
                "operator_completion_action": (
                    "complete_vina_gnina_input_manifest_row_for_casf2016_4llx"
                ),
                "missing_required_fields": [
                    "prepared_receptor_checksum",
                    "prepared_ligand_checksum",
                    "input_preparation_provenance_ref",
                ],
                "missing_local_file_requirements": [
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "protein_structure_path",
                        "file_group": "official_source_file",
                        "operator_action": (
                            "materialize_source_files_from_casf_archive_and_verify_checksum"
                        ),
                    },
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "reference_ligand_path",
                        "file_group": "official_source_file",
                        "operator_action": (
                            "materialize_source_files_from_casf_archive_and_verify_checksum"
                        ),
                    },
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "prepared_receptor_path",
                        "file_group": "prepared_input_file",
                        "operator_action": (
                            "prepare_vina_gnina_input_and_record_checksum"
                        ),
                    },
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "prepared_ligand_path",
                        "file_group": "prepared_input_file",
                        "operator_action": (
                            "prepare_vina_gnina_input_and_record_checksum"
                        ),
                    },
                ],
                "missing_receipt_ref_requirements": [
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "vina_run_receipt_ref",
                        "operator_action": "attach_vina_run_receipt_ref",
                    },
                    {
                        "case_id": "casf2016_4llx",
                        "complex_id": "4llx",
                        "field": "input_preparation_provenance_ref",
                        "operator_action": "attach_input_preparation_provenance_ref",
                    },
                ],
            }
        ],
    }

    family_plan = module._operator_blocker_family_plan(
        case_input_slots=[
            {"case_id": "casf2016_4llx", "status": "blocked"},
        ],
        blocked_engine_run_slots=[
            {
                "case_id": "casf2016_4llx",
                "complex_id": "4llx",
                "engine_id": "vina",
                "docking_run_id": "casf2016_4llx_vina_run",
                "blockers": ["prepared_receptor_path_missing"],
            }
        ],
        current_engine_execution_statuses=[
            {
                "engine_id": "vina",
                "available": False,
                "blocker": "vina_binary_missing",
            }
        ],
        row_status={
            "status": "row_artifact_missing",
            "blocker": "public_benchmark_vina_gnina_rows_not_detected",
            "detected_row_artifact_count": 0,
        },
        input_manifest_template_preflight_summary=manifest_summary,
        adapter_rows_ready=False,
    )

    families = {row["family_id"]: row for row in family_plan}
    assert families["manifest_required_values"]["missing_item_count"] == 3
    assert families["manifest_required_values"]["next_action"] == (
        "complete_vina_gnina_input_manifest_required_values"
    )
    assert families["manifest_required_values"]["materialization_command"].startswith(
        "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"
    )
    assert families["official_source_files"]["missing_item_count"] == 2
    assert families["official_source_files"]["blocked_case_count"] == 1
    assert families["official_source_files"]["command_key"] == (
        "materialize_input_manifest_from_casf_archive"
    )
    assert "--archive <CASF-2016.tar.gz>" in families["official_source_files"][
        "materialization_command"
    ]
    assert families["prepared_input_files"]["missing_item_count"] == 2
    assert families["input_and_engine_receipt_refs"]["missing_item_count"] == 2
    assert families["engine_runtime"]["missing_item_count"] == 1
    assert families["engine_runtime"]["materialization_command"].startswith(
        "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py"
    )
    assert families["engine_run_slots"]["missing_item_count"] == 1
    assert families["adapter_rows"]["missing_item_count"] == 1


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
    assert payload["blocked_case_input_slot_count"] == 1
    assert payload["blocked_engine_run_slot_count"] == 2
    assert payload["first_blocked_case_input_slot"]["case_id"] == "casf2016_1abc"
    assert payload["first_blocked_engine_run_slot"]["case_id"] == "casf2016_1abc"
    assert payload["first_blocked_engine_run_slot"]["engine_id"] == "vina"
    assert payload["summary"]["blocked_case_input_slot_count"] == 1
    assert payload["summary"]["blocked_engine_run_slot_count"] == 2
    assert payload["summary"]["first_blocked_case_input_case_id"] == "casf2016_1abc"
    assert payload["summary"]["first_blocked_engine_run_case_id"] == "casf2016_1abc"
    assert payload["summary"]["first_blocked_engine_run_engine_id"] == "vina"
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
