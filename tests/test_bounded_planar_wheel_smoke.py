from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_bounded_planar_wheel_smoke.py"
SPEC = importlib.util.spec_from_file_location("bounded_planar_wheel_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def test_installed_wheel_output_contract_accepts_exact_result_pair(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"checkpoint")
    engineering_hash = _hash("e")
    result = {
        "status": "ready",
        "profile": module.PROFILE,
        "input_checksum": _hash("1"),
        "result_hash": _hash("2"),
        "contract_bindings": {
            "source_model_ir_adapter": {"model_ir_content_hash": _hash("1")},
            "bounded_planar_execution_plan": {"model_ir_content_hash": _hash("1")},
            "engineering_result_hash": engineering_hash,
        },
        "engineering_result_ir": {
            "engineering_result_hash": engineering_hash,
        },
    }
    report = {
        "contract_pass": True,
        "exact_checkpoint_chain_replay": True,
        "exact_engineering_recovery": True,
    }

    verified = module.validate_installed_wheel_outputs(
        result=result,
        report=report,
        checkpoint_path=checkpoint,
    )

    assert verified["result_hash"] == _hash("2")
    assert verified["engineering_result_hash"] == engineering_hash
    assert verified["checkpoint_sha256"] == (
        "sha256:47320987f9a49d5b00119b960f247a956773f57543982b8bfcb6da5bb3afd9ef"
    )
    assert verified["checkpoint_byte_length"] == len(b"checkpoint")


def test_wheel_smoke_declares_member_feature_and_settlement_cases() -> None:
    assert set(module.SAMPLES) == {
        "member_feature",
        "prescribed_settlement",
    }
    assert module.SAMPLES["member_feature"].name == (
        "bounded_planar_frame_alpha.model-ir.v2.json"
    )
    assert module.SAMPLES["prescribed_settlement"].name == (
        "bounded_planar_settlement.model-ir.v2.json"
    )


def test_wheel_build_uses_pep517_isolation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str] | None] = []

    def capture(
        command,
        *,
        cwd: Path,
        environment=None,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        environments.append(environment)
        (tmp_path / "wheel" / "structural_analysis-0.3.0-py3-none-any.whl").write_bytes(
            b"wheel"
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", capture)
    source_root = tmp_path / "source"
    source_root.mkdir()

    wheel = module._build_wheel(
        source_root=source_root,
        wheel_directory=tmp_path / "wheel",
        working_directory=tmp_path,
        source_date_epoch=1700000000,
    )

    assert wheel.name == "structural_analysis-0.3.0-py3-none-any.whl"
    assert len(commands) == 1
    build_command = commands[0]
    assert build_command[:4] == [sys.executable, "-m", "pip", "wheel"]
    assert "--no-build-isolation" not in build_command
    assert "--no-deps" in build_command
    assert build_command[-1] == str(source_root)
    assert environments[0] is not None
    assert environments[0]["SOURCE_DATE_EPOCH"] == "1700000000"


def test_git_source_identity_binds_epoch_to_exact_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def capture(
        command,
        *,
        cwd: Path,
        environment=None,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            stdout = "b" * 40 + "\n"
        elif command == [
            "git",
            "rev-parse",
            "--verify",
            "b" * 40 + "^{tree}",
        ]:
            stdout = "c" * 40 + "\n"
        elif command == [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
        ]:
            stdout = ""
        else:
            stdout = "1700000001\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module, "_run", capture)

    source_sha, source_tree_sha, source_date_epoch = module._git_source_identity(
        module.ROOT
    )

    assert source_sha == "b" * 40
    assert source_tree_sha == "c" * 40
    assert source_date_epoch == 1700000001
    assert commands == [
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        ["git", "rev-parse", "--verify", "b" * 40 + "^{tree}"],
        ["git", "show", "-s", "--format=%ct", "b" * 40],
    ]


def test_git_source_identity_rejects_tracked_worktree_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def capture(
        command,
        *,
        cwd: Path,
        environment=None,
    ) -> subprocess.CompletedProcess[str]:
        stdout = (
            "c" * 40 + "\n"
            if command[:3] == ["git", "rev-parse", "--verify"]
            else " M src/structural_analysis/api/nonlinear_frame.py\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module, "_run", capture)

    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="source_worktree_dirty",
    ):
        module._git_source_identity(module.ROOT)


def test_reproducible_wheel_contract_requires_same_filename_and_hash(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "structural_analysis-0.3.0-py3-none-any.whl"
    second = second_dir / first.name
    first.write_bytes(b"same-wheel")
    second.write_bytes(b"same-wheel")

    builds = module._verify_reproducible_wheels([first, second])

    assert len(builds) == module.BUILD_COUNT == 2
    assert builds[0]["wheel_filename"] == builds[1]["wheel_filename"]
    assert builds[0]["wheel_sha256"] == builds[1]["wheel_sha256"]

    second.write_bytes(b"changed-wheel")
    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="wheel_hash_not_reproducible",
    ):
        module._verify_reproducible_wheels([first, second])


def test_cli_atomically_writes_exact_receipt_and_retains_json_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = {
        "schema_version": "bounded-planar-wheel-smoke.v4",
        "source_commit_sha": "c" * 40,
        "source_tree_sha": "d" * 40,
        "source_date_epoch": 1700000002,
        "same_run_build_count": 2,
        "same_run_wheel_byte_identical": True,
        "contract_pass": True,
        "wheel_sha256": _hash("a"),
        "cases": {},
    }
    output = tmp_path / "nested" / "receipt.json"
    calls: list[dict] = []

    def fake_smoke(**kwargs):
        calls.append(kwargs)
        return receipt

    monkeypatch.setattr(module, "run_wheel_smoke", fake_smoke)

    wheel_out = tmp_path / "wheel"
    assert (
        module.main(
            [
                "--write",
                str(output),
                "--wheel-out-dir",
                str(wheel_out),
                "--os-label",
                "ubuntu-latest",
                "--python-version",
                "3.12",
                "--json",
            ]
        )
        == 0
    )

    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert json.loads(capsys.readouterr().out) == receipt
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert calls == [
        {
            "repo_root": module.ROOT,
            "wheel_out_dir": wheel_out,
            "os_label": "ubuntu-latest",
            "requested_python_version": "3.12",
        }
    ]


def test_build_system_and_runtime_constraints_are_exactly_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    build_section = pyproject.split("[build-system]", 1)[1].split("[project]", 1)[0]
    assert '"setuptools==80.9.0"' in build_section
    assert '"wheel==0.45.1"' in build_section
    assert '"packaging==26.2"' in build_section
    assert "\"tomli==2.4.1; python_version < '3.11'\"" in build_section
    assert "setuptools>=" not in build_section

    constraints = (ROOT / "ci/bounded-planar-wheel-smoke.constraints.txt").read_text(
        encoding="utf-8"
    )
    pins = {
        line for line in constraints.splitlines() if line and not line.startswith("#")
    }
    assert pins == {
        "numpy==1.26.4",
        "scipy==1.12.0",
        "matplotlib==3.10.3",
        "jsonschema==4.24.0",
    }
    assert tuple(module.BUILD_SYSTEM_REQUIREMENTS) == (
        "setuptools==80.9.0",
        "wheel==0.45.1",
        "packaging==26.2",
        "tomli==2.4.1; python_version < '3.11'",
    )
    assert tuple(module.SOURCE_ARCHIVE_PATHS) == (
        "pyproject.toml",
        "setup.cfg",
        "README.md",
        "LICENSE",
        "src",
        "ci/bounded-planar-wheel-smoke.constraints.txt",
        "examples/bounded_planar_frame_alpha.model-ir.v2.json",
        "examples/bounded_planar_settlement.model-ir.v2.json",
    )


def test_atomic_wheel_copy_preserves_exact_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.whl"
    destination = tmp_path / "nested" / "retained.whl"
    source.write_bytes(b"exact-wheel")

    module._atomic_copy(source, destination)

    assert destination.read_bytes() == b"exact-wheel"


def test_dual_mode_dispatch_preserves_exact_and_prebuilt_contracts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    exact_calls: list[dict] = []
    prebuilt_calls: list[dict] = []

    def exact_runner(**kwargs):
        exact_calls.append(kwargs)
        return {"mode": "exact-source"}

    def prebuilt_runner(**kwargs):
        prebuilt_calls.append(kwargs)
        return {"mode": "prebuilt"}

    monkeypatch.setattr(module, "_run_exact_source_wheel_smoke", exact_runner)
    monkeypatch.setattr(module, "_run_prebuilt_wheel_smoke", prebuilt_runner)
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"

    assert module.run_wheel_smoke(
        repo_root=module.ROOT,
        wheel_out_dir=tmp_path / "retained",
        os_label="ubuntu-latest",
        requested_python_version="3.12",
    ) == {"mode": "exact-source"}
    assert module.run_wheel_smoke(
        repo_root=module.ROOT,
        wheel_path=wheel,
        expected_wheel_sha256=_hash("a"),
        inherit_runtime=True,
        expected_source_sha="b" * 40,
        expected_source_date_epoch=1700000000,
    ) == {"mode": "prebuilt"}

    assert exact_calls == [
        {
            "repo_root": module.ROOT,
            "wheel_out_dir": tmp_path / "retained",
            "os_label": "ubuntu-latest",
            "requested_python_version": "3.12",
        }
    ]
    assert prebuilt_calls == [
        {
            "repo_root": module.ROOT,
            "wheel_path": wheel,
            "expected_wheel_sha256": _hash("a"),
            "inherit_runtime": True,
            "expected_source_sha": "b" * 40,
            "expected_source_date_epoch": 1700000000,
        }
    ]


def test_dual_mode_dispatch_rejects_mixed_or_incomplete_prebuilt_options(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="wheel_smoke_mode_conflict",
    ):
        module.run_wheel_smoke(wheel_path=wheel, wheel_out_dir=tmp_path / "retained")

    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="prebuilt_wheel_required",
    ):
        module.run_wheel_smoke(expected_wheel_sha256=_hash("a"))


def test_prebuilt_wheel_hash_is_verified_before_install(tmp_path: Path) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="prebuilt_wheel_sha256_mismatch",
    ):
        module.run_wheel_smoke(
            repo_root=module.ROOT,
            wheel_path=wheel,
            expected_wheel_sha256=_hash("0"),
            inherit_runtime=True,
            expected_source_sha="a" * 40,
            expected_source_date_epoch=123,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda result, report: report.update(contract_pass=False),
            "validation_report",
        ),
        (
            lambda result, report: result["contract_bindings"][
                "source_model_ir_adapter"
            ].update(model_ir_content_hash=_hash("9")),
            "source_model_ir_content_binding",
        ),
        (
            lambda result, report: result["contract_bindings"].update(
                engineering_result_hash=_hash("8")
            ),
            "engineering_result_binding",
        ),
    ],
)
def test_installed_wheel_output_contract_fails_closed(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"checkpoint")
    engineering_hash = _hash("e")
    result = {
        "status": "ready",
        "profile": module.PROFILE,
        "input_checksum": _hash("1"),
        "result_hash": _hash("2"),
        "contract_bindings": {
            "source_model_ir_adapter": {"model_ir_content_hash": _hash("1")},
            "bounded_planar_execution_plan": {"model_ir_content_hash": _hash("1")},
            "engineering_result_hash": engineering_hash,
        },
        "engineering_result_ir": {
            "engineering_result_hash": engineering_hash,
        },
    }
    report = {
        "contract_pass": True,
        "exact_checkpoint_chain_replay": True,
        "exact_engineering_recovery": True,
    }
    mutation(result, report)

    with pytest.raises(module.BoundedPlanarWheelSmokeError, match=message):
        module.validate_installed_wheel_outputs(
            result=result,
            report=report,
            checkpoint_path=checkpoint,
        )
