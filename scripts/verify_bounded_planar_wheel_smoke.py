#!/usr/bin/env python3
"""Build a wheel and execute bounded planar ModelIR samples outside the source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {
    "member_feature": ROOT / "examples/bounded_planar_frame_alpha.model-ir.v2.json",
    "prescribed_settlement": ROOT
    / "examples/bounded_planar_settlement.model-ir.v2.json",
}
PROFILE = "corotational_connected_frame2d.v1"
HASH_PREFIX = "sha256:"


class BoundedPlanarWheelSmokeError(RuntimeError):
    """Raised when the installed-wheel smoke contract is not satisfied."""


def _sha256(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=None if environment is None else dict(environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise BoundedPlanarWheelSmokeError(
            "command_failed:"
            + str(completed.returncode)
            + ":"
            + " ".join(command)
            + "\nstdout:\n"
            + completed.stdout[-4000:]
            + "\nstderr:\n"
            + completed.stderr[-4000:]
        )
    return completed


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoundedPlanarWheelSmokeError(
            f"json_artifact_invalid:{path.name}"
        ) from error
    if not isinstance(payload, dict):
        raise BoundedPlanarWheelSmokeError(f"json_artifact_not_object:{path.name}")
    return payload


def _hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(HASH_PREFIX)
        and len(value) == len(HASH_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def validate_installed_wheel_outputs(
    *,
    result: Mapping[str, Any],
    report: Mapping[str, Any],
    checkpoint_path: Path,
) -> dict[str, Any]:
    if report.get("contract_pass") is not True:
        raise BoundedPlanarWheelSmokeError("validation_report_contract_blocked")
    if result.get("status") != "ready":
        raise BoundedPlanarWheelSmokeError("unified_result_not_ready")
    if result.get("profile") != PROFILE:
        raise BoundedPlanarWheelSmokeError("unified_result_profile_changed")

    bindings = result.get("contract_bindings")
    if not isinstance(bindings, Mapping):
        raise BoundedPlanarWheelSmokeError("contract_bindings_missing")
    adapter = bindings.get("source_model_ir_adapter")
    if not isinstance(adapter, Mapping):
        raise BoundedPlanarWheelSmokeError("source_model_ir_adapter_missing")
    if adapter.get("model_ir_content_hash") != result.get("input_checksum"):
        raise BoundedPlanarWheelSmokeError("source_model_ir_content_binding_changed")

    execution_plan = bindings.get("bounded_planar_execution_plan")
    if not isinstance(execution_plan, Mapping):
        raise BoundedPlanarWheelSmokeError("bounded_execution_plan_missing")
    if execution_plan.get("model_ir_content_hash") != result.get("input_checksum"):
        raise BoundedPlanarWheelSmokeError("bounded_execution_plan_source_detached")

    engineering_result = result.get("engineering_result_ir")
    if not isinstance(engineering_result, Mapping):
        raise BoundedPlanarWheelSmokeError("engineering_result_ir_missing")
    engineering_hash = engineering_result.get("engineering_result_hash")
    if not _hash(engineering_hash):
        raise BoundedPlanarWheelSmokeError("engineering_result_hash_invalid")
    if bindings.get("engineering_result_hash") != engineering_hash:
        raise BoundedPlanarWheelSmokeError("engineering_result_binding_changed")

    result_hash = result.get("result_hash")
    if not _hash(result_hash):
        raise BoundedPlanarWheelSmokeError("unified_result_hash_invalid")
    if report.get("exact_checkpoint_chain_replay") is not True:
        raise BoundedPlanarWheelSmokeError("checkpoint_replay_not_exact")
    if report.get("exact_engineering_recovery") is not True:
        raise BoundedPlanarWheelSmokeError("engineering_recovery_not_exact")
    if not checkpoint_path.is_file() or checkpoint_path.stat().st_size <= 0:
        raise BoundedPlanarWheelSmokeError("checkpoint_artifact_missing")

    return {
        "result_hash": result_hash,
        "engineering_result_hash": engineering_hash,
        "checkpoint_sha256": _sha256(checkpoint_path),
        "checkpoint_byte_length": checkpoint_path.stat().st_size,
    }


def run_wheel_smoke(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    samples = {
        case_id: repo_root / sample.relative_to(ROOT)
        for case_id, sample in SAMPLES.items()
    }
    for case_id, sample in samples.items():
        if not sample.is_file():
            raise BoundedPlanarWheelSmokeError(
                f"bounded_planar_sample_missing:{case_id}"
            )

    with tempfile.TemporaryDirectory(prefix="bounded-planar-wheel-smoke-") as raw:
        work = Path(raw)
        wheel_dir = work / "wheel"
        installed_environment = work / "installed-environment"
        output = work / "output"
        wheel_dir.mkdir()
        output.mkdir()

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(repo_root),
            ],
            cwd=work,
        )
        wheels = sorted(wheel_dir.glob("structural_analysis-*.whl"))
        if len(wheels) != 1:
            raise BoundedPlanarWheelSmokeError(
                f"wheel_artifact_count_invalid:{len(wheels)}"
            )
        wheel = wheels[0]
        venv.EnvBuilder(with_pip=True, clear=True).create(installed_environment)
        installed_python = installed_environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        _run(
            [
                str(installed_python),
                "-m",
                "pip",
                "install",
                str(wheel),
            ],
            cwd=work,
        )

        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        probe = _run(
            [
                str(installed_python),
                "-c",
                (
                    "import importlib.resources, json, pathlib, structural_analysis, "
                    "sys; "
                    "schema = importlib.resources.files('structural_analysis').joinpath("
                    "'schemas/model_ir_v2.schema.json'); "
                    "print(json.dumps({'module': str(pathlib.Path("
                    "structural_analysis.__file__).resolve()), "
                    "'schema': str(pathlib.Path(str(schema)).resolve()), "
                    "'environment': str(pathlib.Path(sys.prefix).resolve())}))"
                ),
            ],
            cwd=work,
            environment=environment,
        )
        try:
            probe_payload = json.loads(probe.stdout)
            module_path = Path(probe_payload["module"]).resolve()
            schema_path = Path(probe_payload["schema"]).resolve()
            actual_environment = Path(probe_payload["environment"]).resolve()
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise BoundedPlanarWheelSmokeError(
                "installed_package_probe_invalid"
            ) from error
        try:
            if not actual_environment.samefile(installed_environment):
                raise ValueError("installed environment identity changed")
            module_relative_path = module_path.relative_to(actual_environment)
            schema_relative_path = schema_path.relative_to(actual_environment)
        except (OSError, ValueError) as error:
            raise BoundedPlanarWheelSmokeError(
                "installed_package_resolved_outside_wheel_target"
            ) from error
        if not schema_path.is_file():
            raise BoundedPlanarWheelSmokeError("installed_model_ir_schema_missing")

        verified_cases: dict[str, dict[str, Any]] = {}
        for case_id, sample in samples.items():
            case_output = output / case_id
            case_output.mkdir()
            result_path = case_output / "result.json"
            report_path = case_output / "report.json"
            checkpoint_path = case_output / "checkpoint.json"
            _run(
                [
                    str(installed_python),
                    "-m",
                    "structural_analysis.api.nonlinear_frame_cli",
                    str(sample),
                    "--profile",
                    PROFILE,
                    "--load-steps",
                    "2",
                    "--residual-tolerance",
                    "1e-9",
                    "--max-iterations",
                    "60",
                    "--out",
                    str(result_path),
                    "--report-out",
                    str(report_path),
                    "--checkpoint-out",
                    str(checkpoint_path),
                ],
                cwd=work,
                environment=environment,
            )
            verified_cases[case_id] = {
                "sample": sample.relative_to(repo_root).as_posix(),
                **validate_installed_wheel_outputs(
                    result=_load_object(result_path),
                    report=_load_object(report_path),
                    checkpoint_path=checkpoint_path,
                ),
            }
        return {
            "schema_version": "bounded-planar-wheel-smoke.v2",
            "contract_pass": True,
            "wheel_filename": wheel.name,
            "wheel_sha256": _sha256(wheel),
            "installed_module": module_relative_path.as_posix(),
            "installed_schema": schema_relative_path.as_posix(),
            "cases": verified_cases,
            "claim_boundary": (
                "This smoke proves that the current wheel contains the bounded planar "
                "adapter and schemas and executes the repository member-feature and "
                "prescribed-settlement samples outside the source tree. It does not "
                "establish cross-platform equality, external V&V, release eligibility, "
                "or design authority."
            ),
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run_wheel_smoke(repo_root=args.repo_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "bounded planar wheel smoke: pass | "
            f"cases={len(payload['cases'])} | "
            f"wheel={payload['wheel_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
