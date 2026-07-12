#!/usr/bin/env python3
"""Build Phase 1 public API/CLI contract artifacts for model health and the CPU frame core."""

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
DEFAULT_FRAME_MODEL_OUT = PRODUCTIZATION / "phase1_core_api_frame_sample_model.json"
DEFAULT_FRAME_RESULT_OUT = PRODUCTIZATION / "phase1_core_api_frame_result.json"
DEFAULT_FRAME_REPORT_OUT = PRODUCTIZATION / "phase1_core_api_frame_report.json"
DEFAULT_FRAME_CLI_RESULT_OUT = PRODUCTIZATION / "phase1_core_api_frame_cli_result.json"
DEFAULT_FRAME_CLI_REPORT_OUT = PRODUCTIZATION / "phase1_core_api_frame_cli_report.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase1_core_api_contract_summary.json"
SCHEMA_VERSION = "phase1-core-api-contract-artifacts.v2"
AUTHORITATIVE_CPU_SOLVER_ID = "authoritative_cpu_linear_fea_3d_v1"


def sample_model_payload() -> dict[str, Any]:
    """Stable model-health-only sample retained for backward compatibility."""

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


def frame_sample_model_payload() -> dict[str, Any]:
    """Closed-form 3D frame sample used by Python API, CLI, and viewer contracts."""

    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "F1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [
            {
                "node": "N2",
                "load_case": "LC1",
                "components": {"FX": 0.0, "FY": -10.0, "FZ": 0.0},
            }
        ],
        "supports": [{"node": "N1", "dofs": "all"}],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "phase1_authoritative_cpu_frame_contract",
            "claim_boundary": "linear_static_3d_frame_cpu_reference_v1",
        },
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _payload_checksum(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _schema_validation_summary(
    *,
    repo_root: Path,
    payloads: dict[str, tuple[dict[str, Any], str]],
) -> dict[str, Any]:
    result_schema_path = Path("src/structural_analysis/schemas/result.schema.json")
    report_schema_path = Path("src/structural_analysis/schemas/validation_report.schema.json")
    resolved_result_schema = repo_root / result_schema_path
    if not resolved_result_schema.exists():
        resolved_result_schema = ROOT / result_schema_path
    resolved_report_schema = repo_root / report_schema_path
    if not resolved_report_schema.exists():
        resolved_report_schema = ROOT / report_schema_path
    schemas = {
        "result": _read_json(resolved_result_schema),
        "report": _read_json(resolved_report_schema),
    }
    validation_rows: dict[str, dict[str, Any]] = {}
    for name, (payload, schema_kind) in payloads.items():
        errors = sorted(
            Draft202012Validator(schemas[schema_kind]).iter_errors(payload),
            key=str,
        )
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


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_ROOT)
        if not env.get("PYTHONPATH")
        else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    return env


def _run_cli_contract(
    *,
    repo_root: Path,
    model_path: Path,
    analysis_type: str,
    reference_payload: dict[str, Any],
    result_out: Path,
    report_out: Path,
    write_outputs: bool,
    load_case: str | None = None,
    matrix_backend: str = "numpy_linalg_solve_dense",
) -> tuple[dict[str, Any], dict[str, Any]]:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        reference_path = tmp_path / f"{analysis_type}_reference.json"
        reference_path.write_text(_json_text(reference_payload), encoding="utf-8")
        result_path = (
            result_out if result_out.is_absolute() else repo_root / result_out
        ) if write_outputs else tmp_path / result_out.name
        report_path = (
            report_out if report_out.is_absolute() else repo_root / report_out
        ) if write_outputs else tmp_path / report_out.name
        command = [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            analysis_type,
            "--matrix-backend",
            matrix_backend,
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ]
        if load_case:
            command.extend(["--load-case", load_case])
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=_env(),
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{analysis_type} CLI contract failed: returncode={completed.returncode}; "
                f"stderr={completed.stderr.strip()}"
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
            env=_env(),
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
    payload: dict[str, Any],
    write_model: bool,
) -> Iterator[Path]:
    if write_model:
        resolved = model_out if model_out.is_absolute() else repo_root / model_out
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(payload), encoding="utf-8")
        yield resolved
        return
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / model_out.name
        tmp_model.write_text(_json_text(payload), encoding="utf-8")
        yield tmp_model


def _frame_reference_payload() -> dict[str, Any]:
    length = 2.0
    load = 10.0
    elastic_modulus = 200.0e6
    weak_axis_inertia = 5.0e-5
    expected_tip = load * length**3 / (3.0 * elastic_modulus * weak_axis_inertia)
    return {
        "solver_path_id": AUTHORITATIVE_CPU_SOLVER_ID,
        "analysis_fidelity": "cpu_reference_linear_fea",
        "production_fail_closed": True,
        "fallback_used": False,
        "implicit_property_fallback_used": False,
        "automatic_support_generation_used": False,
        "node_count": 2,
        "element_count": 1,
        "load_count": 1,
        "support_count": 1,
        "free_dof_count": 6,
        "max_displacement": expected_tip,
        "constrained_reaction_norm": 20.0,
        "claim_boundary": "linear_static_3d_frame_cpu_reference_v1",
    }


def build_contract_artifacts(
    *,
    repo_root: Path = ROOT,
    model_out: Path = DEFAULT_MODEL_OUT,
    result_out: Path = DEFAULT_RESULT_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    cli_result_out: Path = DEFAULT_CLI_RESULT_OUT,
    cli_report_out: Path = DEFAULT_CLI_REPORT_OUT,
    frame_model_out: Path = DEFAULT_FRAME_MODEL_OUT,
    frame_result_out: Path = DEFAULT_FRAME_RESULT_OUT,
    frame_report_out: Path = DEFAULT_FRAME_REPORT_OUT,
    frame_cli_result_out: Path = DEFAULT_FRAME_CLI_RESULT_OUT,
    frame_cli_report_out: Path = DEFAULT_FRAME_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    write_model: bool = False,
    write_cli_outputs: bool = False,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()

    with _model_path_for_generation(
        repo_root=repo_root,
        model_out=model_out,
        payload=sample_model_payload(),
        write_model=write_model,
    ) as model_path:
        model = load_model(model_path)
        config = AnalysisConfig(analysis_type="model_health", tolerance=1.0e-8)
        result = analyze(model, config)
        reference_payload = {"element_count": 1, "node_count": 2}
        cli_result_payload, cli_report_payload = _run_cli_contract(
            repo_root=repo_root,
            model_path=model_path,
            analysis_type="model_health",
            reference_payload=reference_payload,
            result_out=cli_result_out,
            report_out=cli_report_out,
            write_outputs=write_cli_outputs,
        )
        report = validate(result, dict(sorted(reference_payload.items())))
        mismatch_reference_payload = {"element_count": 1, "node_count": 999}
        mismatch_report = validate(result, mismatch_reference_payload)
        cli_mismatch_contract = _run_cli_reference_mismatch_contract(
            repo_root=repo_root,
            model_path=model_path,
            reference_payload=mismatch_reference_payload,
        )

    with _model_path_for_generation(
        repo_root=repo_root,
        model_out=frame_model_out,
        payload=frame_sample_model_payload(),
        write_model=write_model,
    ) as frame_model_path:
        frame_model = load_model(frame_model_path)
        frame_config = AnalysisConfig(
            analysis_type="linear_static",
            tolerance=1.0e-8,
            load_case="LC1",
        )
        frame_result = analyze(frame_model, frame_config)
        frame_reference = dict(sorted(_frame_reference_payload().items()))
        frame_report = validate(frame_result, frame_reference)
        frame_cli_result_payload, frame_cli_report_payload = _run_cli_contract(
            repo_root=repo_root,
            model_path=frame_model_path,
            analysis_type="linear_static",
            reference_payload=frame_reference,
            result_out=frame_cli_result_out,
            report_out=frame_cli_report_out,
            write_outputs=write_cli_outputs,
            load_case="LC1",
        )

    result_payload = result.to_dict()
    report_payload = report.to_dict()
    frame_result_payload = frame_result.to_dict()
    frame_report_payload = frame_report.to_dict()
    mismatch_report_payload = mismatch_report.to_dict()
    cli_mismatch_report_payload = cli_mismatch_contract["report"]

    cli_contract_pass = (
        cli_result_payload == result_payload
        and cli_report_payload == report_payload
        and cli_report_payload.get("contract_pass") is True
    )
    frame_cli_contract_pass = (
        frame_cli_result_payload == frame_result_payload
        and frame_cli_report_payload == frame_report_payload
        and frame_cli_report_payload.get("contract_pass") is True
    )
    frame_viewer = frame_result_payload.get("metrics", {}).get("viewer_payload", {})
    frame_contract_pass = bool(
        frame_result_payload.get("status") == "ready"
        and frame_result_payload.get("solver") == AUTHORITATIVE_CPU_SOLVER_ID
        and frame_report_payload.get("contract_pass") is True
        and frame_cli_contract_pass
        and isinstance(frame_viewer, dict)
        and frame_viewer.get("source") == "authoritative_solver_result"
        and frame_viewer.get("solver_path_id") == AUTHORITATIVE_CPU_SOLVER_ID
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
        payloads={
            "python_api_result": (result_payload, "result"),
            "python_api_validation_report": (report_payload, "report"),
            "cli_result": (cli_result_payload, "result"),
            "cli_validation_report": (cli_report_payload, "report"),
            "frame_python_api_result": (frame_result_payload, "result"),
            "frame_python_api_validation_report": (frame_report_payload, "report"),
            "frame_cli_result": (frame_cli_result_payload, "result"),
            "frame_cli_validation_report": (frame_cli_report_payload, "report"),
        },
    )
    contract_pass = bool(
        report_payload["contract_pass"]
        and cli_contract_pass
        and reference_mismatch_contract_pass
        and frame_contract_pass
        and schema_validation["contract_pass"]
    )

    evidence_source_commit = (
        os.environ.get("EVIDENCE_SOURCE_COMMIT_SHA", "").strip()
        or git_head(repo_root)
    )

    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": evidence_source_commit,
        "source_state_policy": {
            "mode": "source_commit_then_evidence_only_commit",
            "source_commit_sha": evidence_source_commit,
            "exact_head_verification_required": True,
            "allowed_post_source_scope": "generated_phase1_and_readiness_evidence_only",
        },
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "reused_evidence": False,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/analyses/linear_static.py"),
                Path("src/structural_analysis/api/core.py"),
                Path("src/structural_analysis/api/cli.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/assembly/linear_static.py"),
                Path("src/structural_analysis/elements/axial.py"),
                Path("src/structural_analysis/elements/frame3d.py"),
                Path("src/structural_analysis/materials/elastic.py"),
                Path("src/structural_analysis/results/schema.py"),
                Path("src/structural_analysis/results/validation.py"),
                Path("src/structural_analysis/results/viewer.py"),
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
            "linear_static_3d_frame_cpu_reference_v1",
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
        "authoritative_linear_static_contract": {
            "status": "ready" if frame_contract_pass else "blocked",
            "contract_pass": frame_contract_pass,
            "solver_path_id": AUTHORITATIVE_CPU_SOLVER_ID,
            "claim_boundary": frame_result_payload.get("metrics", {}).get("claim_boundary"),
            "degrees_of_freedom": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
            "element_families": ["axial", "truss", "frame", "beam", "column"],
            "matrix_backends": [
                "numpy_linalg_solve_dense",
                "scipy_sparse_spsolve_cpu",
            ],
            "analysis_fidelity": frame_result_payload.get("metrics", {}).get(
                "analysis_fidelity"
            ),
            "production_fail_closed": frame_result_payload.get("metrics", {}).get(
                "production_fail_closed"
            ),
            "fallback_used": frame_result_payload.get("metrics", {}).get("fallback_used"),
            "regularization_used": frame_result_payload.get("metrics", {}).get(
                "regularization_used"
            ),
            "load_case": "LC1",
            "python_api_cli_equal": frame_cli_result_payload == frame_result_payload,
            "viewer_source": frame_viewer.get("source"),
            "viewer_solver_path_id": frame_viewer.get("solver_path_id"),
            "viewer_payload_checksum": _payload_checksum(frame_viewer),
            "result_checksum": _payload_checksum(frame_result_payload),
            "validation_report_checksum": _payload_checksum(frame_report_payload),
            "max_displacement": frame_result_payload.get("metrics", {}).get(
                "max_displacement"
            ),
            "free_residual_norm": frame_result_payload.get("metrics", {}).get(
                "free_residual_norm"
            ),
            "energy_balance_error": frame_result_payload.get("metrics", {}).get(
                "energy_balance_error"
            ),
            "stiffness_symmetry_error": frame_result_payload.get("metrics", {}).get(
                "stiffness_symmetry_error"
            ),
        },
        "model_input_checksum": result_payload["input_checksum"],
        "expected_model_input_checksum": _payload_checksum(sample_model_payload()),
        "frame_model_input_checksum": frame_result_payload["input_checksum"],
        "expected_frame_model_input_checksum": _payload_checksum(
            frame_sample_model_payload()
        ),
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
            "frame_model": str(frame_model_out),
            "frame_result": str(frame_result_out),
            "frame_validation_report": str(frame_report_out),
            "frame_cli_result": str(frame_cli_result_out),
            "frame_cli_validation_report": str(frame_cli_report_out),
            "result_schema": "src/structural_analysis/schemas/result.schema.json",
            "validation_report_schema": "src/structural_analysis/schemas/validation_report.schema.json",
        },
        "claim_boundary": (
            "These artifacts prove the GUI can consume the stable Phase 1 model-health "
            "result and validation report schema, and that the CLI emits the same JSON "
            "envelopes as the Python API. Reference mismatches remain blocking. They also "
            "prove the deterministic fail-closed 6-DOF CPU Euler-Bernoulli frame/truss "
            "reference path used by the Python API, CLI, and viewer payload. This does not "
            "close shell coupling, Timoshenko shear, geometric/material nonlinearity, "
            "dynamics, construction stages, design-code closure, external benchmarks, or "
            "commercial solver readiness."
        ),
    }
    return {
        "model": sample_model_payload(),
        "result": result_payload,
        "report": report_payload,
        "cli_result": cli_result_payload,
        "cli_report": cli_report_payload,
        "frame_model": frame_sample_model_payload(),
        "frame_result": frame_result_payload,
        "frame_report": frame_report_payload,
        "frame_cli_result": frame_cli_result_payload,
        "frame_cli_report": frame_cli_report_payload,
        "summary": summary_payload,
    }


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _targets(
    *,
    model_out: Path,
    result_out: Path,
    report_out: Path,
    cli_result_out: Path,
    cli_report_out: Path,
    frame_model_out: Path,
    frame_result_out: Path,
    frame_report_out: Path,
    frame_cli_result_out: Path,
    frame_cli_report_out: Path,
    summary_out: Path,
) -> dict[str, Path]:
    return {
        "model": model_out,
        "result": result_out,
        "report": report_out,
        "cli_result": cli_result_out,
        "cli_report": cli_report_out,
        "frame_model": frame_model_out,
        "frame_result": frame_result_out,
        "frame_report": frame_report_out,
        "frame_cli_result": frame_cli_result_out,
        "frame_cli_report": frame_cli_report_out,
        "summary": summary_out,
    }


def check_contract_artifacts(
    *,
    repo_root: Path = ROOT,
    model_out: Path = DEFAULT_MODEL_OUT,
    result_out: Path = DEFAULT_RESULT_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    cli_result_out: Path = DEFAULT_CLI_RESULT_OUT,
    cli_report_out: Path = DEFAULT_CLI_REPORT_OUT,
    frame_model_out: Path = DEFAULT_FRAME_MODEL_OUT,
    frame_result_out: Path = DEFAULT_FRAME_RESULT_OUT,
    frame_report_out: Path = DEFAULT_FRAME_REPORT_OUT,
    frame_cli_result_out: Path = DEFAULT_FRAME_CLI_RESULT_OUT,
    frame_cli_report_out: Path = DEFAULT_FRAME_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_contract_artifacts(
        repo_root=repo_root,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        frame_model_out=frame_model_out,
        frame_result_out=frame_result_out,
        frame_report_out=frame_report_out,
        frame_cli_result_out=frame_cli_result_out,
        frame_cli_report_out=frame_cli_report_out,
        summary_out=summary_out,
        write_model=False,
        write_cli_outputs=False,
    )
    for key, path in _targets(
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        frame_model_out=frame_model_out,
        frame_result_out=frame_result_out,
        frame_report_out=frame_report_out,
        frame_cli_result_out=frame_cli_result_out,
        frame_cli_report_out=frame_cli_report_out,
        summary_out=summary_out,
    ).items():
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
    frame_model_out: Path = DEFAULT_FRAME_MODEL_OUT,
    frame_result_out: Path = DEFAULT_FRAME_RESULT_OUT,
    frame_report_out: Path = DEFAULT_FRAME_REPORT_OUT,
    frame_cli_result_out: Path = DEFAULT_FRAME_CLI_RESULT_OUT,
    frame_cli_report_out: Path = DEFAULT_FRAME_CLI_REPORT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_contract_artifacts(
        repo_root=repo_root,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        frame_model_out=frame_model_out,
        frame_result_out=frame_result_out,
        frame_report_out=frame_report_out,
        frame_cli_result_out=frame_cli_result_out,
        frame_cli_report_out=frame_cli_report_out,
        summary_out=summary_out,
        write_model=True,
        write_cli_outputs=True,
    )
    for key, path in _targets(
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        frame_model_out=frame_model_out,
        frame_result_out=frame_result_out,
        frame_report_out=frame_report_out,
        frame_cli_result_out=frame_cli_result_out,
        frame_cli_report_out=frame_cli_report_out,
        summary_out=summary_out,
    ).items():
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
    parser.add_argument("--frame-model-out", type=Path, default=DEFAULT_FRAME_MODEL_OUT)
    parser.add_argument("--frame-result-out", type=Path, default=DEFAULT_FRAME_RESULT_OUT)
    parser.add_argument("--frame-report-out", type=Path, default=DEFAULT_FRAME_REPORT_OUT)
    parser.add_argument(
        "--frame-cli-result-out",
        type=Path,
        default=DEFAULT_FRAME_CLI_RESULT_OUT,
    )
    parser.add_argument(
        "--frame-cli-report-out",
        type=Path,
        default=DEFAULT_FRAME_CLI_REPORT_OUT,
    )
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = {
        "repo_root": ROOT,
        "model_out": args.model_out,
        "result_out": args.result_out,
        "report_out": args.report_out,
        "cli_result_out": args.cli_result_out,
        "cli_report_out": args.cli_report_out,
        "frame_model_out": args.frame_model_out,
        "frame_result_out": args.frame_result_out,
        "frame_report_out": args.frame_report_out,
        "frame_cli_result_out": args.frame_cli_result_out,
        "frame_cli_report_out": args.frame_cli_report_out,
        "summary_out": args.summary_out,
    }
    if args.check:
        ok, message = check_contract_artifacts(**kwargs)
        if not ok:
            print(f"Phase 1 core API contract check FAILED: {message}", file=sys.stderr)
            return 2
        print(f"Phase 1 core API contract check: {message}")
        return 0
    artifacts = write_contract_artifacts(**kwargs)
    if args.json:
        print(_json_text(artifacts["summary"]), end="")
    else:
        frame_status = artifacts["summary"]["authoritative_linear_static_contract"][
            "status"
        ]
        print(
            f"Phase 1 core API contract: {artifacts['summary']['status']} | "
            f"authoritative_linear_static={frame_status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
