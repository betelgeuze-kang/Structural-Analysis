#!/usr/bin/env python3
"""Install a built wheel and exercise the public planar-frame CLI contract."""

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
HASH_PREFIX = "sha256:"
PUBLIC_PROFILE = "planar_frame_verified_alpha.v1"
CONSTRAINTS = Path("ci/bounded-planar-wheel-smoke.constraints.txt")
SOURCE_SAMPLES = {
    "member_feature": ROOT / "examples/bounded_planar_frame_alpha.model-ir.v2.json",
    "prescribed_settlement": ROOT / "examples/bounded_planar_settlement.model-ir.v2.json",
}
UNSUPPORTED_CONTROLS = {
    "arc_length": "planar_frame_arc_length_experimental",
    "direct_displacement_control": (
        "planar_frame_direct_displacement_control_experimental"
    ),
}


class PublicPlanarCliWheelError(RuntimeError):
    """Raised when the installed public CLI violates its declared contract."""


def _sha256(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialized(payload), encoding="utf-8")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicPlanarCliWheelError(f"invalid_json:{path.name}") from error
    if not isinstance(payload, dict):
        raise PublicPlanarCliWheelError(f"json_not_object:{path.name}")
    return payload


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    expected_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode not in expected_codes:
        raise PublicPlanarCliWheelError(
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


def _find_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.resolve().glob("structural_analysis-*.whl"))
    if len(wheels) != 1:
        raise PublicPlanarCliWheelError(f"wheel_count_invalid:{len(wheels)}")
    return wheels[0]


def _public_sample(source: Path, destination: Path) -> None:
    payload = _load_object(source)
    payload["capability_profile"] = PUBLIC_PROFILE
    _write_json(destination, payload)


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(HASH_PREFIX)
        and len(value) == len(HASH_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _engineering_hash(result: Mapping[str, Any]) -> str:
    result_ir = result.get("result_ir")
    if not isinstance(result_ir, Mapping):
        raise PublicPlanarCliWheelError("public_result_ir_missing")
    engineering = result_ir.get("engineering_result_ir")
    if not isinstance(engineering, Mapping):
        raise PublicPlanarCliWheelError("engineering_result_ir_missing")
    value = engineering.get("engineering_result_hash")
    if not _is_hash(value):
        raise PublicPlanarCliWheelError("engineering_result_hash_invalid")
    return str(value)


def _terminal_state_hash(checkpoint_path: Path) -> str:
    checkpoint = _load_object(checkpoint_path)
    value = checkpoint.get("terminal_state_hash")
    if not _is_hash(value):
        rows = checkpoint.get("checkpoints")
        if isinstance(rows, list) and rows and isinstance(rows[-1], Mapping):
            value = rows[-1].get("state_hash")
    if not _is_hash(value):
        raise PublicPlanarCliWheelError("checkpoint_terminal_state_hash_invalid")
    return str(value)


def _validate_converged(
    *,
    result_path: Path,
    report_path: Path,
    checkpoint_path: Path,
) -> dict[str, Any]:
    result = _load_object(result_path)
    report = _load_object(report_path)
    if result.get("profile") != PUBLIC_PROFILE:
        raise PublicPlanarCliWheelError("public_profile_changed")
    if result.get("status") != "converged" or result.get("converged") is not True:
        raise PublicPlanarCliWheelError("public_result_not_converged")
    if report.get("contract_pass") is not True:
        raise PublicPlanarCliWheelError("public_report_contract_blocked")
    for key in ("artifact_contract_pass", "execution_contract_pass", "executed"):
        if report.get(key) is not True:
            raise PublicPlanarCliWheelError(f"public_report_{key}_blocked")
    for key in ("numerical_result_authority", "engineering_result_authority"):
        if report.get(key) is not True:
            raise PublicPlanarCliWheelError(f"public_report_{key}_missing")
    if not _is_hash(result.get("result_hash")):
        raise PublicPlanarCliWheelError("public_result_hash_invalid")
    if not checkpoint_path.is_file() or checkpoint_path.stat().st_size <= 0:
        raise PublicPlanarCliWheelError("public_checkpoint_missing")
    return {
        "result_hash": str(result["result_hash"]),
        "engineering_result_hash": _engineering_hash(result),
        "terminal_state_hash": _terminal_state_hash(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "checkpoint_byte_length": checkpoint_path.stat().st_size,
    }


def _validate_not_run(
    *,
    result_path: Path,
    report_path: Path,
    reason_code: str,
) -> dict[str, Any]:
    result = _load_object(result_path)
    report = _load_object(report_path)
    if result.get("profile") != PUBLIC_PROFILE:
        raise PublicPlanarCliWheelError("unsupported_profile_changed")
    if result.get("status") != "not_run" or result.get("converged") is not None:
        raise PublicPlanarCliWheelError("unsupported_result_truth_changed")
    rows = result.get("unsupported_features")
    if not isinstance(rows, list) or not rows:
        raise PublicPlanarCliWheelError("unsupported_reason_missing")
    if rows[0].get("reason_code") != reason_code:
        raise PublicPlanarCliWheelError("unsupported_reason_changed")
    if report.get("contract_pass") is not True:
        raise PublicPlanarCliWheelError("unsupported_artifact_contract_blocked")
    if report.get("artifact_contract_pass") is not True:
        raise PublicPlanarCliWheelError("unsupported_artifact_invalid")
    if report.get("execution_contract_pass") is not True:
        raise PublicPlanarCliWheelError("unsupported_routing_contract_invalid")
    if report.get("executed") is not False:
        raise PublicPlanarCliWheelError("unsupported_execution_truth_changed")
    if report.get("diagnostic_authority") is not True:
        raise PublicPlanarCliWheelError("unsupported_diagnostic_authority_missing")
    if report.get("numerical_result_authority") is not False:
        raise PublicPlanarCliWheelError("unsupported_numerical_authority_exposed")
    return {
        "result_hash": str(result.get("result_hash", "")),
        "reason_code": reason_code,
    }


def run_public_cli_smoke(
    *,
    repo_root: Path,
    wheel_dir: Path,
    os_label: str,
    requested_python_version: str,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    wheel = _find_wheel(wheel_dir)
    constraints = repo_root / CONSTRAINTS
    if not constraints.is_file():
        raise PublicPlanarCliWheelError("runtime_constraints_missing")

    with tempfile.TemporaryDirectory(prefix="public-planar-cli-wheel-") as raw:
        work = Path(raw)
        environment_root = work / "installed-environment"
        samples_root = work / "samples"
        outputs_root = work / "outputs"
        samples_root.mkdir()
        outputs_root.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(environment_root)
        python = environment_root / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        cli = environment_root / (
            "Scripts/structural-analysis-planar-frame.exe"
            if os.name == "nt"
            else "bin/structural-analysis-planar-frame"
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "--constraint",
                str(constraints),
                str(wheel),
            ],
            cwd=work,
            environment=environment,
        )
        if not cli.is_file():
            raise PublicPlanarCliWheelError("public_console_script_missing")
        _run([str(cli), "--help"], cwd=work, environment=environment)

        cases: dict[str, Any] = {}
        for case_id, source in SOURCE_SAMPLES.items():
            public_model = samples_root / f"{case_id}.json"
            _public_sample(source, public_model)
            initial = outputs_root / case_id / "initial"
            restart = outputs_root / case_id / "restart"
            initial.mkdir(parents=True)
            restart.mkdir(parents=True)
            initial_result = initial / "result.json"
            initial_report = initial / "report.json"
            initial_checkpoint = initial / "checkpoint.json"
            _run(
                [
                    str(cli),
                    str(public_model),
                    "--load-steps",
                    "2",
                    "--residual-tolerance",
                    "1e-9",
                    "--max-iterations",
                    "60",
                    "--out",
                    str(initial_result),
                    "--report-out",
                    str(initial_report),
                    "--checkpoint-out",
                    str(initial_checkpoint),
                ],
                cwd=work,
                environment=environment,
            )
            initial_summary = _validate_converged(
                result_path=initial_result,
                report_path=initial_report,
                checkpoint_path=initial_checkpoint,
            )
            restart_result = restart / "result.json"
            restart_report = restart / "report.json"
            restart_checkpoint = restart / "checkpoint.json"
            _run(
                [
                    str(cli),
                    str(public_model),
                    "--load-steps",
                    "2",
                    "--residual-tolerance",
                    "1e-9",
                    "--max-iterations",
                    "60",
                    "--restart-checkpoint",
                    str(initial_checkpoint),
                    "--out",
                    str(restart_result),
                    "--report-out",
                    str(restart_report),
                    "--checkpoint-out",
                    str(restart_checkpoint),
                ],
                cwd=work,
                environment=environment,
            )
            restart_summary = _validate_converged(
                result_path=restart_result,
                report_path=restart_report,
                checkpoint_path=restart_checkpoint,
            )
            if (
                initial_summary["engineering_result_hash"]
                != restart_summary["engineering_result_hash"]
            ):
                raise PublicPlanarCliWheelError(
                    f"public_restart_engineering_result_mismatch:{case_id}"
                )
            if (
                initial_summary["terminal_state_hash"]
                != restart_summary["terminal_state_hash"]
            ):
                raise PublicPlanarCliWheelError(
                    f"public_restart_terminal_state_mismatch:{case_id}"
                )
            cases[case_id] = {
                "model_sha256": _sha256(public_model),
                "initial": initial_summary,
                "restart": restart_summary,
                "engineering_result_parity": True,
                "terminal_state_parity": True,
                "result_hash_equal": (
                    initial_summary["result_hash"] == restart_summary["result_hash"]
                ),
                "checkpoint_bytes_equal": (
                    initial_summary["checkpoint_sha256"]
                    == restart_summary["checkpoint_sha256"]
                ),
            }

        unsupported: dict[str, Any] = {}
        public_model = samples_root / "unsupported-controls.json"
        _public_sample(SOURCE_SAMPLES["member_feature"], public_model)
        for control, reason_code in UNSUPPORTED_CONTROLS.items():
            case_root = outputs_root / f"unsupported-{control}"
            case_root.mkdir()
            result_path = case_root / "result.json"
            report_path = case_root / "report.json"
            completed = _run(
                [
                    str(cli),
                    str(public_model),
                    "--control",
                    control,
                    "--out",
                    str(result_path),
                    "--report-out",
                    str(report_path),
                ],
                cwd=work,
                environment=environment,
                expected_codes=(2,),
            )
            unsupported[control] = {
                "exit_code": completed.returncode,
                **_validate_not_run(
                    result_path=result_path,
                    report_path=report_path,
                    reason_code=reason_code,
                ),
            }

        return {
            "schema_version": "public-planar-cli-wheel-smoke.v2",
            "contract_pass": True,
            "profile": PUBLIC_PROFILE,
            "wheel_filename": wheel.name,
            "wheel_sha256": _sha256(wheel),
            "coordinate": {
                "os_label": os_label,
                "requested_python_version": requested_python_version,
            },
            "installed_console_script": cli.name,
            "help_executed": True,
            "cases": cases,
            "unsupported_controls": unsupported,
            "claim_boundary": (
                "This receipt proves installed-wheel execution of the public bounded "
                "planar CLI, terminal state and engineering-result parity after "
                "checkpoint restart, and stable fail-closed routing for experimental "
                "controls. Checkpoint and result bytes may differ when restart lineage "
                "is represented explicitly. It does not establish external V&V, design "
                "authority, release eligibility, or future-run wheel equality."
            ),
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--os-label", default="local")
    parser.add_argument(
        "--python-version",
        default=f"{sys.version_info.major}.{sys.version_info.minor}",
    )
    parser.add_argument("--write", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run_public_cli_smoke(
        repo_root=args.repo_root,
        wheel_dir=args.wheel_dir,
        os_label=args.os_label,
        requested_python_version=args.python_version,
    )
    if args.write is not None:
        _write_json(args.write, payload)
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "public planar CLI wheel smoke: pass | "
            f"cases={len(payload['cases'])} | "
            f"wheel={payload['wheel_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
