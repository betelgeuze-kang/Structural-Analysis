from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_fresh_validation_receipt.py"
SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "implementation"
    / "phase1"
    / "fresh_validation_receipt.schema.json"
)
ALLOWED_GPU_COMMAND = (
    "python3 implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py "
    "--component-only --require-hip-residual-engine"
)
SPEC = importlib.util.spec_from_file_location("build_fresh_validation_receipt", SCRIPT_PATH)
assert SPEC is not None
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_fixture_gpu_runner(repo_root: Path, *, exit_code: int = 0) -> Path:
    return _write_text(
        repo_root / "implementation" / "phase1" / "run_mgt_residual_jacobian_consistency_probe.py",
        "\n".join(
            [
                "from __future__ import annotations",
                "import sys",
                "print('fixture gpu hip validation runner')",
                f"raise SystemExit({exit_code})",
                "",
            ]
        ),
    )


FAKE_RUNNER_SCRIPT_FAIL_EXIT = 7


def _fake_runner_script_body(fail_flag: str = "--fail") -> str:
    return (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"if {fail_flag!r} in sys.argv:\n"
        f"    sys.exit({FAKE_RUNNER_SCRIPT_FAIL_EXIT})\n"
        "sys.exit(0)\n"
    )


def _install_fake_runner_scripts(repo_root: Path) -> None:
    """Create lightweight stub scripts in the fake repo for registered runner prefixes.

    The stubs honour a ``--fail`` flag by exiting with
    ``FAKE_RUNNER_SCRIPT_FAIL_EXIT`` so failure-path tests can exercise
    a registered command that returns nonzero.
    """
    script_names = [
        "run_solver_hip_e2e_contract.py",
        "run_mgt_residual_jacobian_consistency_probe.py",
        "report_commercial_solver_cross_validation.py",
        "run_performance_profiling_gate.py",
        "run_general_fe_contact_benchmark_gate.py",
        "run_mgt_surface_membrane_tangent.py",
        "run_mgt_surface_shell_bending_tangent.py",
        "run_mgt_coupled_frame_surface_sparse_equilibrium.py",
        "run_midas_exact_roundtrip_closure_gate.py",
        "run_midas_interoperability_gate.py",
        "run_productization_gate.py",
        "run_ndtha_residual_gate.py",
        "start_external_benchmark_task.py",
        "run_design_optimization_solver_loop_long.py",
    ]
    body = _fake_runner_script_body()
    for name in script_names:
        path = repo_root / "implementation" / "phase1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _init_git_repo(repo_root: Path, *, name: str, version: str) -> None:
    """Create a deterministic fake git repo + package.json + runner script stubs for receipt provenance."""
    repo_root.mkdir(parents=True, exist_ok=True)
    _write_json(repo_root / "package.json", {"name": name, "version": version})
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo_root, check=True)
    _write_text(repo_root / "marker.txt", "fresh-validation-receipt-builder-test")
    _install_fake_runner_scripts(repo_root)
    subprocess.run(
        ["git", "add", "marker.txt", "implementation/"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)


def _expected_engine_version(name: str, version: str) -> str:
    return f"{name}@{version}"


def _build_cli_args(
    tmp_path: Path,
    *,
    repo_root: Path,
    validation_command: str = ALLOWED_GPU_COMMAND,
    artifact_paths: list[Path],
    extra: list[str] | None = None,
    output_receipt: Path | None = None,
    case_count: int | None = 1,
    passed_case_count: int | None = 1,
) -> list[str]:
    args = [
        "--lane-id",
        "gpu_hip_solver",
        "--runner",
        "gpu_capable_rocm_hip_validation",
        "--validation-command",
        validation_command,
        "--repo-root",
        str(repo_root),
        "--receipt-schema",
        str(SCHEMA_PATH),
        "--case-count",
        str(case_count) if case_count is not None else "0",
        "--passed-case-count",
        str(passed_case_count) if passed_case_count is not None else "0",
        "--input",
        "marker.txt",
    ]
    for artifact in artifact_paths:
        args.extend(["--receipt-artifact", f"{artifact}:report"])
    args.extend(["--output-receipt", str(output_receipt or (tmp_path / "receipt.json"))])
    if extra:
        args.extend(extra)
    return args


def test_build_receipt_runs_real_command_and_writes_valid_receipt(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_dir = repo_root / "artifacts"
    artifact_path = _write_text(artifact_dir / "report.json", json.dumps({"contract_pass": True}))

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                artifact_paths=[artifact_path],
                output_receipt=tmp_path / "out" / "gpu_hip_solver.fresh_validation_receipt.json",
            ),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    receipt_path = tmp_path / "out" / "gpu_hip_solver.fresh_validation_receipt.json"
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "fresh-validation-receipt.v1"
    assert receipt["lane_id"] == "gpu_hip_solver"
    assert receipt["runner"] == "gpu_capable_rocm_hip_validation"
    assert receipt["reused_evidence"] is False
    assert receipt["contract_pass"] is True
    assert receipt["reason_code"] == "PASS"
    assert receipt["engine_version"] == _expected_engine_version("builder-pkg", "9.9.9")
    assert receipt["source_commit_sha"] != "0" * 7
    assert len(receipt["source_commit_sha"]) >= 7
    assert all(ch in "0123456789abcdef" for ch in receipt["source_commit_sha"])
    assert "marker.txt" in receipt["input_checksums"]
    assert receipt["input_checksums"]["marker.txt"].startswith("sha256:")
    assert receipt["validation_command"] == ALLOWED_GPU_COMMAND
    assert len(receipt["receipt_artifacts"]) == 1
    artifact_entry = receipt["receipt_artifacts"][0]
    assert artifact_entry["path"] == str(artifact_path)
    assert artifact_entry["sha256"].startswith("sha256:")
    assert artifact_entry["kind"] == "report"
    assert receipt["summary"]["case_count"] == 1
    assert receipt["summary"]["passed_case_count"] == 1
    assert receipt["summary"]["duration_seconds"] >= 0.0
    assert "Level 3" in receipt["claim_boundary"]

    validation = builder.validate_receipt_payload(receipt, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    assert validation["contract_pass"] is True, validation["blockers"]
    assert validation["reason_code"] == "PASS"
    assert validation["blockers"] == []

    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is True
    assert result["reason_code"] == "PASS"
    assert result["receipt_path"] == str(receipt_path)
    assert result["command_result"]["returncode"] == 0


def test_build_receipt_does_not_write_passing_receipt_when_command_fails(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    _write_fixture_gpu_runner(repo_root, exit_code=7)
    artifact_path = _write_text(repo_root / "report.json", json.dumps({"contract_pass": True}))

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                artifact_paths=[artifact_path],
            ),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "BLOCKED" in completed.stdout
    receipt_path = tmp_path / "receipt.json"
    assert not receipt_path.exists()

    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert result["reason_code"] == "ERR_FRESH_VALIDATION_COMMAND_FAILED"
    assert any("validation_command_exit_7" in blocker for blocker in result["blockers"])
    assert result["command_result"]["returncode"] == 7


def test_build_receipt_blocks_arbitrary_command_for_runner(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", json.dumps({"contract_pass": True}))

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                validation_command="python3 -c \"pass\"",
                artifact_paths=[artifact_path],
            ),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "BLOCKED" in completed.stdout
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert result["reason_code"] == "ERR_FRESH_VALIDATION_COMMAND_NOT_ALLOWED"
    assert "command_result" not in result
    assert result["blockers"] == [
        "fresh_validation_command_not_allowed_for_runner:gpu_capable_rocm_hip_validation"
    ]


def test_build_receipt_blocks_unregistered_runner(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", json.dumps({"contract_pass": True}))

    args = _build_cli_args(
        tmp_path,
        repo_root=repo_root,
        validation_command=ALLOWED_GPU_COMMAND,
        artifact_paths=[artifact_path],
    )
    runner_index = args.index("--runner") + 1
    args[runner_index] = "unregistered_validation_runner"

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *args,
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert result["reason_code"] == "ERR_FRESH_VALIDATION_COMMAND_NOT_ALLOWED"
    assert result["blockers"] == [
        "fresh_validation_runner_not_registered:unregistered_validation_runner"
    ]


def test_build_receipt_metadata_only_is_blocked(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", json.dumps({"contract_pass": True}))

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                validation_command="definitely-not-a-real-command-1234",
                artifact_paths=[artifact_path],
            ),
            "--metadata-only",
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    receipt_path = tmp_path / "receipt.json"
    assert not receipt_path.exists()

    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert result["reason_code"] == "ERR_FRESH_VALIDATION_COMMAND_REQUIRED"
    assert "metadata_only_cannot_assert_fresh_validation" in result["blockers"]


def test_build_receipt_blocks_when_no_artifacts_are_supplied(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--lane-id",
            "gpu_hip_solver",
            "--runner",
            "gpu_capable_rocm_hip_validation",
            "--validation-command",
            ALLOWED_GPU_COMMAND,
            "--repo-root",
            str(repo_root),
            "--receipt-schema",
            str(SCHEMA_PATH),
            "--output-receipt",
            str(tmp_path / "receipt.json"),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert "receipt_artifacts_missing_or_empty" in result["blockers"]


def test_build_receipt_artifact_kind_syntax_propagates_kind(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", json.dumps({"contract_pass": True}))

    args = [
        "--lane-id",
        "gpu_hip_solver",
        "--runner",
        "gpu_capable_rocm_hip_validation",
        "--validation-command",
        ALLOWED_GPU_COMMAND,
        "--repo-root",
        str(repo_root),
        "--receipt-schema",
        str(SCHEMA_PATH),
        "--input",
        "marker.txt",
        "--output-receipt",
        str(tmp_path / "receipt.json"),
        "--receipt-artifact",
        f"{artifact_path}:solver_contract_report",
    ]
    completed = subprocess.run(
        ["python3", str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["receipt_artifacts"][0]["kind"] == "solver_contract_report"


def test_build_receipt_blocks_when_git_head_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "no_git_repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _write_json(repo_root / "package.json", {"name": "plain", "version": "0.0.1"})
    _write_fixture_gpu_runner(repo_root)
    artifact_path = _write_text(repo_root / "report.json", "{}")

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--lane-id",
            "gpu_hip_solver",
            "--runner",
            "gpu_capable_rocm_hip_validation",
            "--validation-command",
            ALLOWED_GPU_COMMAND,
            "--repo-root",
            str(repo_root),
            "--receipt-schema",
            str(SCHEMA_PATH),
            "--output-receipt",
            str(tmp_path / "receipt.json"),
            "--receipt-artifact",
            str(artifact_path),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert "source_commit_sha_missing_git_head" in result["blockers"]


def test_build_receipt_uses_provided_case_counts_and_duration(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", "{}")

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--lane-id",
            "gpu_hip_solver",
            "--runner",
            "gpu_capable_rocm_hip_validation",
            "--validation-command",
            ALLOWED_GPU_COMMAND,
            "--repo-root",
            str(repo_root),
        "--receipt-schema",
        str(SCHEMA_PATH),
        "--input",
        "marker.txt",
        "--case-count",
        "12",
            "--passed-case-count",
            "10",
            "--duration-seconds",
            "42.5",
            "--output-receipt",
            str(tmp_path / "receipt.json"),
            "--receipt-artifact",
            str(artifact_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["summary"] == {
        "case_count": 12,
        "passed_case_count": 10,
        "duration_seconds": 42.5,
    }


def test_build_receipt_records_real_artifact_sha256(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", '{"contract_pass": true}')

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--lane-id",
            "gpu_hip_solver",
            "--runner",
            "gpu_capable_rocm_hip_validation",
            "--validation-command",
            ALLOWED_GPU_COMMAND,
            "--repo-root",
            str(repo_root),
        "--receipt-schema",
        str(SCHEMA_PATH),
        "--input",
        "marker.txt",
        "--output-receipt",
        str(tmp_path / "receipt.json"),
            "--receipt-artifact",
            str(artifact_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    expected = builder.file_sha256(artifact_path)
    assert receipt["receipt_artifacts"][0]["sha256"] == expected


def test_build_receipt_blocks_when_artifact_file_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    missing_artifact = repo_root / "missing-report.json"

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                artifact_paths=[missing_artifact],
            ),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert any(blocker.startswith("receipt_artifact_missing:") for blocker in result["blockers"])


def test_build_receipt_blocks_when_input_is_directory(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", "{}")

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--lane-id",
            "gpu_hip_solver",
            "--runner",
            "gpu_capable_rocm_hip_validation",
            "--validation-command",
            ALLOWED_GPU_COMMAND,
            "--repo-root",
            str(repo_root),
            "--receipt-schema",
            str(SCHEMA_PATH),
            "--input",
            ".",
            "--output-receipt",
            str(tmp_path / "receipt.json"),
            "--receipt-artifact",
            str(artifact_path),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert any(blocker.startswith("input_not_file:") for blocker in result["blockers"])


def test_build_receipt_blocks_when_artifact_is_directory(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_dir = repo_root / "artifact-dir"
    artifact_dir.mkdir()

    completed = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            *_build_cli_args(
                tmp_path,
                repo_root=repo_root,
                artifact_paths=[artifact_dir],
            ),
            "--out-result",
            str(tmp_path / "result.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["contract_pass"] is False
    assert any(blocker.startswith("receipt_artifact_not_file:") for blocker in result["blockers"])


def test_build_receipt_module_helpers_produce_schema_valid_payload(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, name="builder-pkg", version="9.9.9")
    artifact_path = _write_text(repo_root / "report.json", "{}")

    receipt = builder.build_receipt(
        lane_id="gpu_hip_solver",
        runner="gpu_capable_rocm_hip_validation",
        validation_command=ALLOWED_GPU_COMMAND,
        input_paths=["marker.txt"],
        artifacts=[(str(artifact_path), "solver_contract_report")],
        case_count=3,
        passed_case_count=3,
        duration_seconds=1.25,
        claim_boundary="Test claim boundary",
        repo_root=repo_root,
        actual_duration=1.0,
    )
    validation = builder.validate_receipt_payload(
        receipt, json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    assert validation["contract_pass"] is True, validation["blockers"]


def test_build_receipt_module_run_command_records_returncode(tmp_path: Path) -> None:
    result = builder._run_validation_command(
        "python3 -c \"print('ok'); import sys; sys.exit(0)\"",
        cwd=tmp_path,
        timeout=10.0,
    )
    assert result["returncode"] == 0
    assert "ok" in result["stdout_tail"]


def test_build_receipt_module_run_command_returns_nonzero_returncode() -> None:
    result = builder._run_validation_command(
        "python3 -c \"import sys; sys.exit(3)\"",
        cwd=Path("/tmp"),
        timeout=10.0,
    )
    assert result["returncode"] == 3


def test_build_receipt_module_run_command_raises_on_missing_executable() -> None:
    with pytest.raises(builder.CommandRunError):
        builder._run_validation_command(
            "definitely-not-a-real-binary-xyz",
            cwd=Path("/tmp"),
            timeout=5.0,
        )
