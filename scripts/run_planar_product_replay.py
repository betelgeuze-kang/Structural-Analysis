#!/usr/bin/env python3
"""Run the installed public planar CLI and emit a Workbench product-replay case."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "planar_frame_verified_alpha.v1"
CONSTRAINTS = Path("ci/bounded-planar-wheel-smoke.constraints.txt")
DEFAULT_SAMPLE = Path("examples/bounded_planar_frame_alpha.model-ir.v2.json")
CANONICAL_MODEL_SOURCE_PATH = "product-replay/public-model.json"
ADAPTER_PATH = ROOT / "scripts/build_planar_workbench_case.py"


class PlanarProductReplayError(RuntimeError):
    """Raised when an installed-wheel product replay cannot be completed."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanarProductReplayError(f"invalid_json:{path}") from error
    if not isinstance(payload, dict):
        raise PlanarProductReplayError(f"json_not_object:{path}")
    return payload


def _serialized(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_serialized(payload))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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
        raise PlanarProductReplayError(
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
        raise PlanarProductReplayError(f"wheel_count_invalid:{len(wheels)}")
    return wheels[0]


def _load_adapter():
    spec = importlib.util.spec_from_file_location(
        "build_planar_workbench_case",
        ADAPTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise PlanarProductReplayError("workbench_adapter_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _commit_timestamp(repo_root: Path, source_commit_sha: str) -> str:
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%cI", source_commit_sha],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise PlanarProductReplayError("source_commit_timestamp_unavailable")
    return value


def run_product_replay(
    *,
    repo_root: Path,
    wheel_dir: Path,
    sample_path: Path,
    output_root: Path,
    source_commit_sha: str,
    engine_version: str,
    generated_at: str | None,
    os_label: str,
    requested_python_version: str,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if len(source_commit_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_commit_sha
    ):
        raise PlanarProductReplayError("source_commit_sha_invalid")
    generated_at = generated_at or _commit_timestamp(repo_root, source_commit_sha)
    wheel = _find_wheel(wheel_dir)
    constraints = repo_root / CONSTRAINTS
    sample = sample_path if sample_path.is_absolute() else repo_root / sample_path
    if not sample.is_file() or not constraints.is_file():
        raise PlanarProductReplayError("replay_input_missing")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="planar-product-replay-") as raw:
        work = Path(raw)
        environment_root = work / "installed-environment"
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
            raise PlanarProductReplayError("public_planar_cli_missing")

        model = _load_object(sample)
        model["capability_profile"] = PROFILE
        public_model = output_root / "public-model.json"
        _write_json(public_model, model)
        result_path = output_root / "public-result.json"
        report_path = output_root / "public-report.json"
        checkpoint_path = output_root / "public-checkpoint.json"
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
                str(result_path),
                "--report-out",
                str(report_path),
                "--checkpoint-out",
                str(checkpoint_path),
            ],
            cwd=work,
            environment=environment,
        )

    adapter = _load_adapter()
    workbench_case = adapter.build_workbench_case(
        model_path=public_model,
        result_path=result_path,
        report_path=report_path,
        source_commit_sha=source_commit_sha,
        engine_version=engine_version,
        generated_at=generated_at,
        source_path=CANONICAL_MODEL_SOURCE_PATH,
    )
    workbench_case_path = output_root / "workbench-case.json"
    _write_json(workbench_case_path, workbench_case)
    result = _load_object(result_path)
    report = _load_object(report_path)
    receipt = {
        "schema_version": "planar-product-replay.v1",
        "contract_pass": True,
        "profile": PROFILE,
        "source_commit_sha": source_commit_sha,
        "engine_version": engine_version,
        "generated_at": generated_at,
        "coordinate": {
            "os_label": os_label,
            "requested_python_version": requested_python_version,
        },
        "wheel": {
            "filename": wheel.name,
            "sha256": _sha256(wheel),
        },
        "artifacts": {
            "model_sha256": _sha256(public_model),
            "result_sha256": _sha256(result_path),
            "report_sha256": _sha256(report_path),
            "checkpoint_sha256": _sha256(checkpoint_path),
            "workbench_case_sha256": _sha256(workbench_case_path),
        },
        "result_truth": {
            "status": result.get("status"),
            "converged": result.get("converged"),
            "result_hash": result.get("result_hash"),
            "artifact_contract_pass": report.get("artifact_contract_pass"),
            "execution_contract_pass": report.get("execution_contract_pass"),
            "numerical_result_authority": report.get("numerical_result_authority"),
            "engineering_result_authority": report.get("engineering_result_authority"),
        },
        "claim_boundary": (
            "This receipt proves one installed-wheel public planar execution and its "
            "evidence-honest projection into a Workbench v2 case on the declared "
            "coordinate. Browser review/export integrity is recorded separately. It "
            "does not establish external V&V, design authority, or release eligibility."
        ),
    }
    _write_json(output_root / "product-replay.json", receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--engine-version", required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--os-label", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    receipt = run_product_replay(
        repo_root=args.repo_root,
        wheel_dir=args.wheel_dir,
        sample_path=args.sample,
        output_root=args.output_root,
        source_commit_sha=args.source_commit,
        engine_version=args.engine_version,
        generated_at=args.generated_at,
        os_label=args.os_label,
        requested_python_version=args.python_version,
    )
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "planar product replay: pass | "
            f"coordinate={args.os_label}|python-{args.python_version}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
