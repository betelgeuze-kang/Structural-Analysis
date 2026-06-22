#!/usr/bin/env python3
"""Build Phase 1 core API contract artifacts consumed by the GUI."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import (  # noqa: E402
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    analyze,
    load_model,
    validate,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MODEL_OUT = PRODUCTIZATION / "phase1_core_api_sample_model.json"
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase1_core_api_model_health_result.json"
DEFAULT_REPORT_OUT = PRODUCTIZATION / "phase1_core_api_model_health_report.json"
DEFAULT_CLI_RESULT_OUT = PRODUCTIZATION / "phase1_core_api_cli_model_health_result.json"
DEFAULT_CLI_REPORT_OUT = PRODUCTIZATION / "phase1_core_api_cli_model_health_report.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase1_core_api_contract_summary.json"
SCHEMA_VERSION = "phase1-core-api-contract-artifacts.v1"


def sample_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [1.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "rectangular"}],
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "phase1_core_api_contract_sample",
            "claim_boundary": "model_health_schema_contract_only",
        },
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _payload_checksum(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _schema_validation_summary(
    *,
    repo_root: Path,
    result_payload: dict[str, Any],
    report_payload: dict[str, Any],
    cli_result_payload: dict[str, Any],
    cli_report_payload: dict[str, Any],
) -> dict[str, Any]:
    result_schema_path = Path("src/structural_analysis/schemas/result.schema.json")
    report_schema_path = Path("src/structural_analysis/schemas/validation_report.schema.json")
    resolved_result_schema = repo_root / result_schema_path
    if not resolved_result_schema.exists():
        resolved_result_schema = ROOT / result_schema_path
    resolved_report_schema = repo_root / report_schema_path
    if not resolved_report_schema.exists():
        resolved_report_schema = ROOT / report_schema_path
    result_schema = _read_json(resolved_result_schema)
    report_schema = _read_json(resolved_report_schema)
    checks = {
        "python_api_result": (result_payload, result_schema),
        "python_api_validation_report": (report_payload, report_schema),
        "cli_result": (cli_result_payload, result_schema),
        "cli_validation_report": (cli_report_payload, report_schema),
    }
    validation_rows: dict[str, dict[str, Any]] = {}
    for name, (payload, schema) in checks.items():
        errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
        validation_rows[name] = {
            "schema_valid": not errors,
            "error_count": len(errors),
            "errors": [error.message for error in errors[:5]],
        }
    return {
        "contract_pass": all(row["schema_valid"] for row in validation_rows.values()),
        "result_schema": result_schema_path.as_posix(),
        "validation_report_schema": report_schema_path.as_posix(),
        "checks": validation_rows,
    }


def _run_cli_contract(
    *,
    repo_root: Path,
    model_path: Path,
    reference_payload: dict[str, Any],
    cli_result_out: Path,
    cli_report_out: Path,
    write_outputs: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        reference_path = tmp_path / "phase1_core_api_reference.json"
        reference_path.write_text(_json_text(reference_payload), encoding="utf-8")
        result_path = (
            cli_result_out
            if cli_result_out.is_absolute()
            else repo_root / cli_result_out
        ) if write_outputs else tmp_path / cli_result_out.name
        report_path = (
            cli_report_out
            if cli_report_out.is_absolute()
            else repo_root / cli_report_out
        ) if write_outputs else tmp_path / cli_report_out.name
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(SRC_ROOT)
            if not env.get("PYTHONPATH")
            else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "structural_analysis.api.cli",
                str(model_path),
                "--analysis-type",
                "model_health",
                "--reference",
                str(reference_path),
                "--out",
                str(result_path),
                "--report-out",
                str(report_path),
            ],
            cwd=repo_root,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "phase1 core API CLI contract failed: "
                f"returncode={completed.returncode}; stderr={completed.stderr.strip()}"
            )
        return _read_json(result_path), _read_json(report_path)


def _run_cli_reference_mismatch_contract(
    *,
    repo_root: Path,
    model_path: Path,
    reference_payload: dict[str, Any],
) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        reference_path = tmp_path / "phase1_core_api_mismatch_reference.json"
        result_path = tmp_path / "phase1_core_api_mismatch_result.json"
        report_path = tmp_path / "phase1_core_api_mismatch_report.json"
        reference_path.write_text(_json_text(reference_payload), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(SRC_ROOT)
            if not env.get("PYTHONPATH")
            else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "structural_analysis.api.cli",
                str(model_path),
                "--analysis-type",
                "model_health",
                "--reference",
                str(reference_path),
                "--out",
                str(result_path),
                "--report-out",
                str(report_path),
            ],
            cwd=repo_root,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
        report_payload = _read_json(report_path) if report_path.exists() else {}
        return {
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
            "report": report_payload,
        }


@contextmanager
def _model_path_for_generation(
    *,
    repo_root: Path,
    model_out: Path,
    write_model: bool,
) -> Iterator[Path]:
    model_payload = sample_model_payload()
    if write_model:
        resolved = model_out if model_out.is_absolute() else repo_root / model_out
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(model_payload), encoding="utf-8")
        yield resolved
        return
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / model_out.name
        tmp_model.write_text(_json_text(model_payload), encoding="utf-8")
        yield tmp_model


def build_contract_artifacts(
    *,
    repo_root: Path = ROOT,
    model_out: Path = DEFAULT_MODEL_OUT,
    result_out: Path = DEFAULT_RESULT_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    cli_result_out: Path = DEFAULT_CLI_RESULT_OUT,
    cli_report_out: Path = DEFAULT_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    write_model: bool = False,
    write_cli_outputs: bool = False,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    with _model_path_for_generation(
        repo_root=repo_root,
        model_out=model_out,
        write_model=write_model,
    ) as model_path:
        model = load_model(model_path)
        config = AnalysisConfig(analysis_type="model_health", tolerance=1.0e-8)
        result = analyze(model, config)
        reference_payload = {"element_count": 1, "node_count": 2}
        cli_result_payload, cli_report_payload = _run_cli_contract(
            repo_root=repo_root,
            model_path=model_path,
            reference_payload=reference_payload,
            cli_result_out=cli_result_out,
            cli_report_out=cli_report_out,
            write_outputs=write_cli_outputs,
        )
        sorted_reference_payload = {
            key: reference_payload[key] for key in sorted(reference_payload)
        }
        report = validate(result, sorted_reference_payload)
        mismatch_reference_payload = {"element_count": 1, "node_count": 999}
        mismatch_report = validate(result, mismatch_reference_payload)
        cli_mismatch_contract = _run_cli_reference_mismatch_contract(
            repo_root=repo_root,
            model_path=model_path,
            reference_payload=mismatch_reference_payload,
        )

    result_payload = result.to_dict()
    report_payload = report.to_dict()
    mismatch_report_payload = mismatch_report.to_dict()
    cli_mismatch_report_payload = cli_mismatch_contract["report"]
    cli_contract_pass = (
        cli_result_payload == result_payload
        and cli_report_payload == report_payload
        and cli_report_payload.get("contract_pass") is True
    )
    reference_mismatch_contract_pass = bool(
        mismatch_report_payload.get("contract_pass") is False
        and mismatch_report_payload.get("status") == "blocked"
        and "reference_mismatch:node_count"
        in mismatch_report_payload.get("developer_preview_blocked_fields", [])
        and cli_mismatch_contract["returncode"] == 2
        and cli_mismatch_report_payload.get("contract_pass") is False
        and cli_mismatch_report_payload.get("status") == "blocked"
        and "reference_mismatch:node_count"
        in cli_mismatch_report_payload.get("developer_preview_blocked_fields", [])
    )
    schema_validation = _schema_validation_summary(
        repo_root=repo_root,
        result_payload=result_payload,
        report_payload=report_payload,
        cli_result_payload=cli_result_payload,
        cli_report_payload=cli_report_payload,
    )
    contract_pass = bool(
        report_payload["contract_pass"]
        and cli_contract_pass
        and reference_mismatch_contract_pass
        and schema_validation["contract_pass"]
    )
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/api/core.py"),
                Path("src/structural_analysis/api/cli.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/assembly/linear_static.py"),
                Path("src/structural_analysis/elements/axial.py"),
                Path("src/structural_analysis/schemas/result.schema.json"),
                Path("src/structural_analysis/schemas/validation_report.schema.json"),
                Path("src/structural_analysis/solvers/linear/static.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
            ],
            repo_root=repo_root,
        ),
        "contract_pass": contract_pass,
        "status": "ready" if contract_pass else "blocked",
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "invocation_surfaces": ["python_api", "cli", "gui_json_consumption"],
        "analysis_type": result_payload["analysis_type"],
        "supported_preview_analysis_types": [
            "model_health",
            "linear_static_axial_truss",
            "nonlinear_static_material_mesh_axial_chain",
        ],
        "result_status": result_payload["status"],
        "report_status": report_payload["status"],
        "schema_validation": schema_validation,
        "cli_contract": {
            "status": "ready" if cli_contract_pass else "blocked",
            "contract_pass": cli_contract_pass,
            "entry_point": "structural-analysis = structural_analysis.api.cli:main",
            "module_command": "python -m structural_analysis.api.cli",
            "same_result_schema_as_python_api": cli_result_payload == result_payload,
            "same_validation_report_schema_as_python_api": cli_report_payload == report_payload,
            "api_result_checksum": _payload_checksum(result_payload),
            "cli_result_checksum": _payload_checksum(cli_result_payload),
            "api_validation_report_checksum": _payload_checksum(report_payload),
            "cli_validation_report_checksum": _payload_checksum(cli_report_payload),
            "result_input_checksum": cli_result_payload.get("input_checksum"),
            "report_input_checksum": cli_report_payload.get("input_checksum"),
            "result_claim_boundary_version": cli_result_payload.get("claim_boundary_version"),
            "report_claim_boundary_version": cli_report_payload.get("claim_boundary_version"),
        },
        "reference_validation_contract": {
            "status": "ready" if reference_mismatch_contract_pass else "blocked",
            "contract_pass": reference_mismatch_contract_pass,
            "python_api_blocks_reference_mismatch": mismatch_report_payload.get("contract_pass") is False,
            "cli_blocks_reference_mismatch": cli_mismatch_contract["returncode"] == 2,
            "python_api_blocked_fields": mismatch_report_payload.get(
                "developer_preview_blocked_fields", []
            ),
            "cli_blocked_fields": cli_mismatch_report_payload.get(
                "developer_preview_blocked_fields", []
            ),
            "mismatch_field": "node_count",
        },
        "model_input_checksum": result_payload["input_checksum"],
        "expected_model_input_checksum": _payload_checksum(sample_model_payload()),
        "tolerance": result_payload["tolerance"],
        "convergence_history_count": len(result_payload["convergence_history"]),
        "unsupported_feature_count": len(result_payload.get("unsupported_features", [])),
        "developer_preview_blocked_field_count": len(
            report_payload.get("developer_preview_blocked_fields", [])
        ),
        "metrics": result_payload.get("metrics", {}),
        "artifacts": {
            "model": str(model_out),
            "result": str(result_out),
            "validation_report": str(report_out),
            "cli_result": str(cli_result_out),
            "cli_validation_report": str(cli_report_out),
            "result_schema": "src/structural_analysis/schemas/result.schema.json",
            "validation_report_schema": "src/structural_analysis/schemas/validation_report.schema.json",
        },
        "claim_boundary": (
            "These artifacts prove the GUI can consume the stable Phase 1 core API "
            "model_health result and validation report schema, and that the CLI emits "
            "the same JSON envelopes as the Python API for the same canonical model. "
            "Reference mismatches are blocking validation outcomes in both surfaces. "
            "The package also has narrow axial-truss linear_static and 1D material-mesh "
            "nonlinear_static preview paths, but these artifacts do not close general "
            "linear frame/shell, modal, buckling, nonlinear, external benchmark, or "
            "commercial solver readiness blockers."
        ),
    }
    return {
        "model": sample_model_payload(),
        "result": result_payload,
        "report": report_payload,
        "cli_result": cli_result_payload,
        "cli_report": cli_report_payload,
        "summary": summary_payload,
    }


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def check_contract_artifacts(
    *,
    repo_root: Path = ROOT,
    model_out: Path = DEFAULT_MODEL_OUT,
    result_out: Path = DEFAULT_RESULT_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    cli_result_out: Path = DEFAULT_CLI_RESULT_OUT,
    cli_report_out: Path = DEFAULT_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_contract_artifacts(
        repo_root=repo_root,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
        write_model=False,
        write_cli_outputs=False,
    )
    targets = {
        "model": model_out,
        "result": result_out,
        "report": report_out,
        "cli_result": cli_result_out,
        "cli_report": cli_report_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase1_core_api_contract_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase1_core_api_contract_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase1_core_api_contract_mismatch:{key}"
    return True, "phase1_core_api_contract_consistent"


def write_contract_artifacts(
    *,
    repo_root: Path = ROOT,
    model_out: Path = DEFAULT_MODEL_OUT,
    result_out: Path = DEFAULT_RESULT_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    cli_result_out: Path = DEFAULT_CLI_RESULT_OUT,
    cli_report_out: Path = DEFAULT_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_contract_artifacts(
        repo_root=repo_root,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
        write_model=True,
        write_cli_outputs=True,
    )
    for key, path in {
        "result": result_out,
        "report": report_out,
        "cli_result": cli_result_out,
        "cli_report": cli_report_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_OUT)
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--cli-result-out", type=Path, default=DEFAULT_CLI_RESULT_OUT)
    parser.add_argument("--cli-report-out", type=Path, default=DEFAULT_CLI_REPORT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_contract_artifacts(
            repo_root=ROOT,
            model_out=args.model_out,
            result_out=args.result_out,
            report_out=args.report_out,
            cli_result_out=args.cli_result_out,
            cli_report_out=args.cli_report_out,
            summary_out=args.summary_out,
        )
        if not ok:
            print(f"Phase 1 core API contract check FAILED: {message}", file=sys.stderr)
            return 2
        print(f"Phase 1 core API contract check: {message}")
        return 0
    artifacts = write_contract_artifacts(
        repo_root=ROOT,
        model_out=args.model_out,
        result_out=args.result_out,
        report_out=args.report_out,
        cli_result_out=args.cli_result_out,
        cli_report_out=args.cli_report_out,
        summary_out=args.summary_out,
    )
    if args.json:
        print(json.dumps(artifacts["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Phase 1 core API contract: {artifacts['summary']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
