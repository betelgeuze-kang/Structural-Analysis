#!/usr/bin/env python3
"""Build a wheel and execute bounded planar ModelIR samples outside the source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
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
BUILD_COUNT = 2
RUNTIME_CONSTRAINTS = Path("ci/bounded-planar-wheel-smoke.constraints.txt")
BUILD_SYSTEM_REQUIREMENTS = (
    "setuptools==80.9.0",
    "wheel==0.45.1",
    "packaging==26.2",
    "tomli==2.4.1; python_version < '3.11'",
)
SOURCE_ARCHIVE_PATHS = (
    "pyproject.toml",
    "setup.cfg",
    "README.md",
    "LICENSE",
    "src",
    RUNTIME_CONSTRAINTS.as_posix(),
    "examples/bounded_planar_frame_alpha.model-ir.v2.json",
    "examples/bounded_planar_settlement.model-ir.v2.json",
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class BoundedPlanarWheelSmokeError(RuntimeError):
    """Raised when the installed-wheel smoke contract is not satisfied."""


def _sha256(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=destination.parent, delete=False
    ) as handle:
        with source.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, handle)
        temporary = Path(handle.name)
    temporary.replace(destination)


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


def _git_source_identity(repo_root: Path) -> tuple[str, str, int]:
    source_commit_sha = _run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
    ).stdout.strip()
    if not _GIT_SHA_RE.fullmatch(source_commit_sha):
        raise BoundedPlanarWheelSmokeError("source_commit_sha_invalid")

    tracked_changes = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=repo_root,
    ).stdout.strip()
    if tracked_changes:
        raise BoundedPlanarWheelSmokeError("source_worktree_dirty")

    source_tree_sha = _run(
        ["git", "rev-parse", "--verify", f"{source_commit_sha}^{{tree}}"],
        cwd=repo_root,
    ).stdout.strip()
    if not _GIT_SHA_RE.fullmatch(source_tree_sha):
        raise BoundedPlanarWheelSmokeError("source_tree_sha_invalid")

    raw_epoch = _run(
        ["git", "show", "-s", "--format=%ct", source_commit_sha],
        cwd=repo_root,
    ).stdout.strip()
    try:
        source_date_epoch = int(raw_epoch)
    except ValueError as error:
        raise BoundedPlanarWheelSmokeError("source_date_epoch_invalid") from error
    if source_date_epoch <= 0:
        raise BoundedPlanarWheelSmokeError("source_date_epoch_invalid")
    return source_commit_sha, source_tree_sha, source_date_epoch


def _create_git_archive(
    *,
    repo_root: Path,
    source_commit_sha: str,
    archive_path: Path,
) -> None:
    _run(
        [
            "git",
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            source_commit_sha,
            *SOURCE_ARCHIVE_PATHS,
        ],
        cwd=repo_root,
    )
    if not archive_path.is_file() or archive_path.stat().st_size <= 0:
        raise BoundedPlanarWheelSmokeError("source_archive_missing")


def _extract_git_archive(*, archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    destination_root = destination.resolve()
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            members = archive.getmembers()
            for member in members:
                if member.issym() or member.islnk():
                    raise BoundedPlanarWheelSmokeError(
                        f"source_archive_link_not_supported:{member.name}"
                    )
                try:
                    (destination / member.name).resolve().relative_to(destination_root)
                except ValueError as error:
                    raise BoundedPlanarWheelSmokeError(
                        f"source_archive_path_unsafe:{member.name}"
                    ) from error
            archive.extractall(destination, members=members)
    except (OSError, tarfile.TarError) as error:
        raise BoundedPlanarWheelSmokeError("source_archive_invalid") from error


def _build_wheel(
    *,
    source_root: Path,
    wheel_directory: Path,
    working_directory: Path,
    source_date_epoch: int,
) -> Path:
    wheel_directory.mkdir(parents=True, exist_ok=False)
    build_environment = dict(os.environ)
    build_environment["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheel_directory),
            str(source_root),
        ],
        cwd=working_directory,
        environment=build_environment,
    )
    wheels = sorted(wheel_directory.glob("structural_analysis-*.whl"))
    if len(wheels) != 1:
        raise BoundedPlanarWheelSmokeError(
            f"wheel_artifact_count_invalid:{wheel_directory.name}:{len(wheels)}"
        )
    return wheels[0]


def _verify_reproducible_wheels(wheels: Sequence[Path]) -> list[dict[str, Any]]:
    if len(wheels) != BUILD_COUNT:
        raise BoundedPlanarWheelSmokeError(f"wheel_build_count_invalid:{len(wheels)}")
    builds = [
        {
            "build_number": index,
            "wheel_filename": wheel.name,
            "wheel_sha256": _sha256(wheel),
        }
        for index, wheel in enumerate(wheels, start=1)
    ]
    filenames = {str(build["wheel_filename"]) for build in builds}
    hashes = {str(build["wheel_sha256"]) for build in builds}
    if len(filenames) != 1:
        raise BoundedPlanarWheelSmokeError("wheel_filename_not_reproducible")
    if len(hashes) != 1:
        raise BoundedPlanarWheelSmokeError("wheel_hash_not_reproducible")
    return builds


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


def run_wheel_smoke(
    *,
    repo_root: Path = ROOT,
    wheel_out_dir: Path | None = None,
    os_label: str = "local",
    requested_python_version: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_commit_sha, source_tree_sha, source_date_epoch = _git_source_identity(
        repo_root
    )
    requested_python = requested_python_version or (
        f"{sys.version_info.major}.{sys.version_info.minor}"
    )

    with tempfile.TemporaryDirectory(prefix="bounded-planar-wheel-smoke-") as raw:
        work = Path(raw)
        archive_path = work / "exact-source.tar"
        installed_environment = work / "installed-environment"
        output = work / "output"
        output.mkdir()
        _create_git_archive(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            archive_path=archive_path,
        )

        source_roots: list[Path] = []
        wheels: list[Path] = []
        for build_number in range(1, BUILD_COUNT + 1):
            source_root = work / f"source-build-{build_number}"
            _extract_git_archive(
                archive_path=archive_path,
                destination=source_root,
            )
            source_roots.append(source_root)
            wheels.append(
                _build_wheel(
                    source_root=source_root,
                    wheel_directory=work / f"wheel-build-{build_number}",
                    working_directory=work,
                    source_date_epoch=source_date_epoch,
                )
            )

        wheel_builds = _verify_reproducible_wheels(wheels)
        wheel = wheels[0]
        exact_source_root = source_roots[0]
        constraints_path = exact_source_root / RUNTIME_CONSTRAINTS
        if not constraints_path.is_file():
            raise BoundedPlanarWheelSmokeError("runtime_constraints_missing")
        samples = {
            case_id: exact_source_root / sample.relative_to(ROOT)
            for case_id, sample in SAMPLES.items()
        }
        for case_id, sample in samples.items():
            if not sample.is_file():
                raise BoundedPlanarWheelSmokeError(
                    f"bounded_planar_sample_missing:{case_id}"
                )

        venv.EnvBuilder(with_pip=True, clear=True).create(installed_environment)
        installed_python = installed_environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        installed_cli = installed_environment / (
            "Scripts/structural-analysis-nonlinear-frame.exe"
            if os.name == "nt"
            else "bin/structural-analysis-nonlinear-frame"
        )
        _run(
            [
                str(installed_python),
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "--constraint",
                str(constraints_path),
                str(wheel),
            ],
            cwd=work,
        )
        if not installed_cli.is_file():
            raise BoundedPlanarWheelSmokeError("installed_console_script_missing")

        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        probe = _run(
            [
                str(installed_python),
                "-c",
                (
                    "import importlib.metadata as metadata, importlib.resources, json, "
                    "pathlib, platform, structural_analysis, sys; "
                    "schema = importlib.resources.files('structural_analysis').joinpath("
                    "'schemas/model_ir_v2.schema.json'); "
                    "print(json.dumps({'module': str(pathlib.Path("
                    "structural_analysis.__file__).resolve()), "
                    "'schema': str(pathlib.Path(str(schema)).resolve()), "
                    "'environment': str(pathlib.Path(sys.prefix).resolve()), "
                    "'python_version': platform.python_version(), "
                    "'python_implementation': platform.python_implementation(), "
                    "'system': platform.system(), 'platform': platform.platform(), "
                    "'packages': {name: metadata.version(name) for name in "
                    "('pip', 'numpy', 'scipy', 'matplotlib', 'jsonschema')}}))"
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
            runtime_packages = dict(probe_payload["packages"])
            actual_python_version = str(probe_payload["python_version"])
            actual_system = str(probe_payload["system"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise BoundedPlanarWheelSmokeError(
                "installed_package_probe_invalid"
            ) from error
        try:
            if not actual_environment.samefile(installed_environment):
                raise ValueError("installed environment identity changed")
            module_relative_path = module_path.relative_to(actual_environment)
            schema_relative_path = schema_path.relative_to(actual_environment)
            cli_relative_path = installed_cli.resolve().relative_to(actual_environment)
        except (OSError, ValueError) as error:
            raise BoundedPlanarWheelSmokeError(
                "installed_package_resolved_outside_wheel_target"
            ) from error
        if not schema_path.is_file():
            raise BoundedPlanarWheelSmokeError("installed_model_ir_schema_missing")
        if ".".join(actual_python_version.split(".")[:2]) != requested_python:
            raise BoundedPlanarWheelSmokeError("runtime_python_version_mismatch")
        expected_system = {
            "ubuntu-latest": "Linux",
            "windows-latest": "Windows",
        }.get(os_label)
        if expected_system is not None and actual_system != expected_system:
            raise BoundedPlanarWheelSmokeError("runtime_system_mismatch")

        verified_cases: dict[str, dict[str, Any]] = {}
        for case_id, sample in samples.items():
            case_output = output / case_id
            case_output.mkdir()
            result_path = case_output / "result.json"
            report_path = case_output / "report.json"
            checkpoint_path = case_output / "checkpoint.json"
            _run(
                [
                    str(installed_cli),
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
                "sample": sample.relative_to(exact_source_root).as_posix(),
                "sample_sha256": _sha256(sample),
                **validate_installed_wheel_outputs(
                    result=_load_object(result_path),
                    report=_load_object(report_path),
                    checkpoint_path=checkpoint_path,
                ),
            }

        if wheel_out_dir is not None:
            preserved_wheel = wheel_out_dir.resolve() / wheel.name
            _atomic_copy(wheel, preserved_wheel)
            if _sha256(preserved_wheel) != _sha256(wheel):
                raise BoundedPlanarWheelSmokeError("preserved_wheel_hash_mismatch")

        return {
            "schema_version": "bounded-planar-wheel-smoke.v4",
            "contract_pass": True,
            "source_commit_sha": source_commit_sha,
            "source_tree_sha": source_tree_sha,
            "source_date_epoch": source_date_epoch,
            "source_export": "git_archive_exact_commit_paths",
            "source_archive_paths": list(SOURCE_ARCHIVE_PATHS),
            "build_system_requirements": list(BUILD_SYSTEM_REQUIREMENTS),
            "runtime_constraints": {
                "path": RUNTIME_CONSTRAINTS.as_posix(),
                "sha256": _sha256(constraints_path),
            },
            "coordinate": {
                "coordinate_id": f"{os_label}|python-{requested_python}",
                "os_label": os_label,
                "requested_python_version": requested_python,
            },
            "runtime": {
                "python_version": actual_python_version,
                "python_implementation": str(probe_payload["python_implementation"]),
                "system": actual_system,
                "platform": str(probe_payload["platform"]),
                "packages": runtime_packages,
            },
            "same_run_build_count": BUILD_COUNT,
            "same_run_wheel_byte_identical": True,
            "wheel_filename": wheel.name,
            "wheel_sha256": _sha256(wheel),
            "wheel_builds": wheel_builds,
            "installed_module": module_relative_path.as_posix(),
            "installed_schema": schema_relative_path.as_posix(),
            "installed_console_script": cli_relative_path.as_posix(),
            "installed_console_script_executed": True,
            "cases": verified_cases,
            "claim_boundary": (
                "This smoke proves two byte-identical isolated wheel builds from two "
                "independent exports of one exact Git tree in this workflow execution, "
                "then installs one wheel with the committed runtime constraints and "
                "executes the installed bounded planar console script. It does not "
                "establish future-run or cross-platform wheel equality, external V&V, "
                "release eligibility, or design authority."
            ),
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", type=Path, metavar="PATH")
    parser.add_argument("--wheel-out-dir", type=Path, metavar="DIRECTORY")
    parser.add_argument("--os-label", default="local")
    parser.add_argument("--python-version")
    args = parser.parse_args(argv)
    payload = run_wheel_smoke(
        repo_root=args.repo_root,
        wheel_out_dir=args.wheel_out_dir,
        os_label=args.os_label,
        requested_python_version=args.python_version,
    )
    if args.write is not None:
        _atomic_write_json(args.write, payload)
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "bounded planar wheel smoke: pass | "
            f"cases={len(payload['cases'])} | "
            f"wheel={payload['wheel_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
