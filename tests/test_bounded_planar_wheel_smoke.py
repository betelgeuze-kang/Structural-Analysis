from __future__ import annotations

import importlib.util
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
            "bounded_planar_execution_plan": {
                "model_ir_content_hash": _hash("1")
            },
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
        "sha256:"
        "47320987f9a49d5b00119b960f247a956773f57543982b8bfcb6da5bb3afd9ef"
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


def test_wheel_build_is_offline_and_does_not_resolve_build_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def capture(
        command,
        *,
        cwd: Path,
        environment=None,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        raise module.BoundedPlanarWheelSmokeError("stop_after_build_command")

    monkeypatch.setattr(module, "_run", capture)

    with pytest.raises(
        module.BoundedPlanarWheelSmokeError,
        match="stop_after_build_command",
    ):
        module.run_wheel_smoke(repo_root=module.ROOT)

    assert commands
    build_command = commands[0]
    assert build_command[:4] == [sys.executable, "-m", "pip", "wheel"]
    assert "--no-build-isolation" in build_command
    assert "--no-deps" in build_command


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda result, report: report.update(contract_pass=False), "validation_report"),
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
            "bounded_planar_execution_plan": {
                "model_ir_content_hash": _hash("1")
            },
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
