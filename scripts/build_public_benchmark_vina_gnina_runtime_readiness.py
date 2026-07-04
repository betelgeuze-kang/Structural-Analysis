#!/usr/bin/env python3
"""Build a runtime readiness receipt for Public Benchmark Vina/GNINA runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS,
    SUPPORTED_ENGINES,
    materialize_vina_gnina_comparison_adapter,
)
from materialize_public_benchmark_operator_bundle_from_rows import (  # noqa: E402
    _build_vina_gnina_cases,
    _load_rows,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_EXECUTION_PLAN = PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
DEFAULT_ENGINE_RUN_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_bundle.json"
)
DEFAULT_ENGINE_RUN_COMMANDS = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_commands.sh"
)
DEFAULT_VINA_GNINA_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_VINA_GNINA_ROWS_TEMPLATE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template.csv"
)
DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template_preflight.json"
)
DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD = (
    DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT.with_suffix(".md")
)
DEFAULT_VINA_GNINA_ROWS_FROM_TEMPLATE_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_from_template_report.json"
)
DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json"
)
DEFAULT_INPUT_MANIFEST_TEMPLATE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template.csv"
)
DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
)
DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD = (
    DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT.with_suffix(".md")
)
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
SCHEMA_VERSION = "public-benchmark-vina-gnina-runtime-readiness.v1"
DOCKER_BIN_ENV = "PUBLIC_BENCHMARK_DOCKER_BIN"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _engine_binary_env_var(engine_id: str) -> str:
    return f"PUBLIC_BENCHMARK_{engine_id.upper()}_BIN"


def _engine_container_image_env_var(engine_id: str) -> str:
    return f"PUBLIC_BENCHMARK_{engine_id.upper()}_CONTAINER_IMAGE"


def _runtime_setup_requirements() -> dict[str, Any]:
    return {
        "accepted_runtime_sources": [
            "engine binary discovered on PATH",
            "engine binary path supplied by environment variable",
            "local Docker image supplied by environment variable",
        ],
        "binary_env_vars": {
            engine_id: _engine_binary_env_var(engine_id)
            for engine_id in SUPPORTED_ENGINES
        },
        "container_image_env_vars": {
            engine_id: _engine_container_image_env_var(engine_id)
            for engine_id in SUPPORTED_ENGINES
        },
        "docker_bin_env_var": DOCKER_BIN_ENV,
        "container_image_policy": (
            "Container fallback requires a local Docker image reference in the "
            "engine image env var; this readiness check inspects local images and "
            "does not pull images."
        ),
        "rows_artifact_required_after_engine_execution": str(DEFAULT_VINA_GNINA_ROWS),
    }


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _engine_binary_status(engine_id: str) -> dict[str, Any]:
    env_var = _engine_binary_env_var(engine_id)
    env_executable = os.environ.get(env_var, "").strip()
    executable = env_executable or shutil.which(engine_id)
    if not executable:
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": "",
            "binary_source": "",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_missing",
        }
    executable_path = Path(executable)
    if env_executable and not executable_path.is_file():
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": executable,
            "binary_source": f"env:{env_var}",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_not_found",
        }
    if env_executable and not os.access(executable_path, os.X_OK):
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": executable,
            "binary_source": f"env:{env_var}",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_not_executable",
        }
    try:
        version_output = subprocess.check_output(
            [executable, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
    except Exception:
        version_output = ""
    return {
        "engine_id": engine_id,
        "available": True,
        "executable": executable,
        "binary_source": f"env:{env_var}" if env_executable else "PATH",
        "env_var": env_var,
        "version": version_output.splitlines()[0] if version_output else "",
        "blocker": "",
    }


def _docker_cli_status() -> dict[str, Any]:
    env_executable = os.environ.get(DOCKER_BIN_ENV, "").strip()
    executable = env_executable or shutil.which("docker")
    if not executable:
        return {
            "available": False,
            "executable": "",
            "binary_source": "",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_missing",
        }
    executable_path = Path(executable)
    if env_executable and not executable_path.is_file():
        return {
            "available": False,
            "executable": executable,
            "binary_source": f"env:{DOCKER_BIN_ENV}",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_not_found",
        }
    if env_executable and not os.access(executable_path, os.X_OK):
        return {
            "available": False,
            "executable": executable,
            "binary_source": f"env:{DOCKER_BIN_ENV}",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_not_executable",
        }
    return {
        "available": True,
        "executable": executable,
        "binary_source": f"env:{DOCKER_BIN_ENV}" if env_executable else "PATH",
        "env_var": DOCKER_BIN_ENV,
        "blocker": "",
    }


def _docker_daemon_version(executable: str) -> tuple[bool, str]:
    try:
        output = subprocess.check_output(
            [executable, "version", "--format", "{{.Server.Version}}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
    except Exception:
        return False, ""
    return bool(output), output.splitlines()[0] if output else ""


def _container_image_present(executable: str, image: str) -> bool:
    try:
        subprocess.check_output(
            [executable, "image", "inspect", image, "--format", "{{.Id}}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception:
        return False
    return True


def _engine_container_status(
    engine_id: str,
    *,
    docker_cli_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_env_var = _engine_container_image_env_var(engine_id)
    image = os.environ.get(image_env_var, "").strip()
    docker_status = docker_cli_status or _docker_cli_status()
    docker_daemon_available = False
    docker_version = ""
    if docker_status.get("available"):
        executable = str(docker_status.get("executable") or "docker")
        docker_daemon_available, docker_version = _docker_daemon_version(executable)
    base = {
        "engine_id": engine_id,
        "available": False,
        "image": image,
        "image_env_var": image_env_var,
        "docker_executable": str(docker_status.get("executable") or ""),
        "docker_binary_available": bool(docker_status.get("available")),
        "docker_daemon_available": docker_daemon_available,
        "docker_server_version": docker_version,
        "image_present": False,
        "command_prefix": "",
        "blocker": "",
    }
    if not image:
        return {**base, "status": "container_image_not_configured"}
    if not docker_status.get("available"):
        return {
            **base,
            "status": "blocked",
            "blocker": str(docker_status.get("blocker") or "docker_binary_missing"),
        }
    executable = str(docker_status.get("executable") or "docker")
    if not docker_daemon_available:
        return {
            **base,
            "status": "blocked",
            "docker_daemon_available": False,
            "blocker": "docker_daemon_unavailable",
        }
    image_present = _container_image_present(executable, image)
    if not image_present:
        return {
            **base,
            "status": "blocked",
            "docker_daemon_available": True,
            "blocker": f"{engine_id}_container_image_not_present",
        }
    command_prefix = f"{executable} run --rm -v $PWD:/work -w /work {image} {engine_id}"
    return {
        **base,
        "status": "ready",
        "available": True,
        "docker_daemon_available": True,
        "docker_server_version": docker_version,
        "image_present": True,
        "command_prefix": command_prefix,
    }


def _engine_execution_status(
    engine_id: str,
    binary_status: dict[str, Any],
    container_status: dict[str, Any],
) -> dict[str, Any]:
    if binary_status.get("available"):
        return {
            "engine_id": engine_id,
            "available": True,
            "execution_source": "binary",
            "executable": str(binary_status.get("executable") or ""),
            "command_prefix": str(binary_status.get("executable") or engine_id),
            "version": str(binary_status.get("version") or ""),
            "blocker": "",
        }
    if container_status.get("available"):
        return {
            "engine_id": engine_id,
            "available": True,
            "execution_source": "container",
            "executable": str(container_status.get("docker_executable") or ""),
            "command_prefix": str(container_status.get("command_prefix") or ""),
            "version": str(container_status.get("docker_server_version") or ""),
            "container_image": str(container_status.get("image") or ""),
            "blocker": "",
        }
    return {
        "engine_id": engine_id,
        "available": False,
        "execution_source": "",
        "executable": "",
        "command_prefix": "",
        "version": "",
        "container_image": str(container_status.get("image") or ""),
        "blocker": str(binary_status.get("blocker") or f"{engine_id}_runtime_missing"),
    }


def _load_vina_gnina_candidate_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
            return [row for row in payload["cases"] if isinstance(row, dict)]
    return _load_rows(path)


def _row_candidate_status(repo_root: Path, rows_path: Path) -> dict[str, Any]:
    candidates = [
        PRODUCTIZATION / f"public_benchmark_vina_gnina_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv")
    ]
    if rows_path not in candidates:
        candidates.insert(0, rows_path)
    rows = []
    selected_path = ""
    selected_resolved_path: Path | None = None
    for path in candidates:
        resolved = path if path.is_absolute() else repo_root / path
        if resolved.is_file() and selected_resolved_path is None:
            selected_path = str(path)
            selected_resolved_path = resolved
        rows.append(
            {
                "path": str(path),
                "exists": resolved.exists(),
                "is_file": resolved.is_file(),
            }
        )
    detected_row_artifact_count = sum(1 for row in rows if row["is_file"])
    selected_row_count = 0
    adapter_case_count = 0
    adapter_ready = False
    adapter_preflight: dict[str, Any] = {
        "status": "missing",
        "contract_pass": False,
        "case_count": 0,
        "ready_case_count": 0,
        "blocker_count": 0,
        "first_blocked_target": "",
        "engine_summaries": [],
        "blockers": [],
    }
    load_error = ""
    blocker = "public_benchmark_vina_gnina_rows_not_detected"
    status = "row_artifact_missing"
    if selected_resolved_path is not None:
        try:
            raw_rows = _load_vina_gnina_candidate_rows(selected_resolved_path)
            selected_row_count = len(raw_rows)
            cases = _build_vina_gnina_cases(raw_rows)
            adapter_case_count = len(cases)
            adapter = materialize_vina_gnina_comparison_adapter(
                {"cases": cases},
                repo_root=repo_root,
                intake_path=Path(selected_path),
            )
            adapter_ready = bool(adapter.get("public_benchmark_engine_comparison_ready"))
            adapter_summary = adapter.get("summary")
            if not isinstance(adapter_summary, dict):
                adapter_summary = {}
            adapter_preflight = {
                "status": str(adapter.get("status") or ""),
                "contract_pass": bool(adapter.get("contract_pass")),
                "case_count": int(adapter_summary.get("case_count") or 0),
                "ready_case_count": int(adapter_summary.get("ready_case_count") or 0),
                "blocker_count": len(adapter.get("blockers", []))
                if isinstance(adapter.get("blockers"), list)
                else 0,
                "first_blocked_target": str(adapter.get("first_blocked_target") or ""),
                "engine_summaries": adapter.get("engine_summaries")
                if isinstance(adapter.get("engine_summaries"), list)
                else [],
                "blockers": [
                    str(row) for row in adapter.get("blockers", []) if str(row)
                ][:20]
                if isinstance(adapter.get("blockers"), list)
                else [],
            }
            if adapter_ready:
                status = "row_artifact_detected_validated"
                blocker = ""
            elif adapter_case_count == 0:
                status = "row_artifact_detected_empty"
                blocker = "public_benchmark_vina_gnina_rows_empty"
            else:
                status = "row_artifact_detected_adapter_blocked"
                blocker = "public_benchmark_vina_gnina_rows_not_adapter_ready"
        except Exception as exc:
            status = "row_artifact_detected_invalid"
            blocker = "public_benchmark_vina_gnina_rows_invalid"
            load_error = str(exc)
    return {
        "status": status,
        "default_rows_path": str(rows_path),
        "candidate_paths": rows,
        "detected_row_artifact_count": detected_row_artifact_count,
        "selected_path": selected_path,
        "selected_row_count": selected_row_count,
        "adapter_case_count": adapter_case_count,
        "adapter_rows_ready": adapter_ready,
        "adapter_preflight": adapter_preflight,
        "load_error": load_error,
        "blocker": blocker,
    }


def _engine_run_slots(
    execution_plan: dict[str, Any],
    engine_status_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    case_plans = execution_plan.get("case_execution_plans")
    if not isinstance(case_plans, list):
        return slots
    for case_plan in case_plans:
        if not isinstance(case_plan, dict):
            continue
        case_id = str(case_plan.get("case_id") or "")
        complex_id = str(case_plan.get("complex_id") or "")
        engine_runs = case_plan.get("engine_runs")
        if not isinstance(engine_runs, list):
            continue
        raw_case_blockers = case_plan.get("blockers", [])
        case_blockers = (
            [str(row) for row in raw_case_blockers if str(row)]
            if isinstance(raw_case_blockers, list)
            else []
        )
        case_inputs_ready = not case_blockers
        for run in engine_runs:
            if not isinstance(run, dict):
                continue
            engine_id = str(run.get("engine_id") or "")
            engine_status = engine_status_by_id.get(engine_id, {})
            docking_box = run.get("docking_box")
            docking_box_ready = (
                isinstance(docking_box, dict)
                and docking_box.get("status") == "ready"
            )
            engine_available = bool(engine_status.get("available"))
            slot_blockers: list[str] = []
            if not docking_box_ready:
                slot_blockers.append("docking_box_not_ready")
            if not case_inputs_ready:
                slot_blockers.extend(case_blockers)
            if not engine_available:
                slot_blockers.append(
                    str(engine_status.get("blocker") or f"{engine_id}_runtime_missing")
                )
            slots.append(
                {
                    "case_id": case_id,
                    "complex_id": complex_id,
                    "engine_id": engine_id,
                    "docking_run_id": str(run.get("docking_run_id") or ""),
                    "docking_box_ready": docking_box_ready,
                    "engine_available": engine_available,
                    "engine_executable": str(engine_status.get("executable") or ""),
                    "engine_execution_source": str(
                        engine_status.get("execution_source") or ""
                    ),
                    "engine_command_prefix": str(
                        engine_status.get("command_prefix") or ""
                    ),
                    "engine_container_image": str(
                        engine_status.get("container_image") or ""
                    ),
                    "case_inputs_ready": case_inputs_ready,
                    "case_blockers": case_blockers,
                    "command_template": str(run.get("command_template") or ""),
                    "expected_predicted_ligand_path_or_pose_ref": str(
                        run.get("expected_predicted_ligand_path_or_pose_ref") or ""
                    ),
                    "expected_engine_config_ref": str(
                        run.get("expected_engine_config_ref") or ""
                    ),
                    "expected_engine_run_provenance_ref": str(
                        run.get("expected_engine_run_provenance_ref") or ""
                    ),
                    "required_adapter_case_fields": list(REQUIRED_CASE_FIELDS),
                    "required_adapter_engine_run_fields": list(
                        REQUIRED_ENGINE_RUN_FIELDS
                    ),
                    "status": (
                        "ready_for_engine_execution"
                        if docking_box_ready and case_inputs_ready and engine_available
                        else "blocked"
                    ),
                    "blockers": slot_blockers,
                }
            )
    return slots


def _case_input_unblock_slots(
    engine_run_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slots_by_case: dict[str, dict[str, Any]] = {}
    for slot in engine_run_slots:
        case_id = str(slot.get("case_id") or "")
        if not case_id or case_id in slots_by_case:
            continue
        case_blockers = (
            [str(row) for row in slot.get("case_blockers", []) if str(row)]
            if isinstance(slot.get("case_blockers"), list)
            else []
        )
        case_inputs_ready = bool(slot.get("case_inputs_ready"))
        slots_by_case[case_id] = {
            "case_id": case_id,
            "complex_id": str(slot.get("complex_id") or ""),
            "status": "ready" if case_inputs_ready else "blocked",
            "case_inputs_ready": case_inputs_ready,
            "blockers": case_blockers,
            "input_manifest_template_artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE),
            "operator_action": (
                f"review_vina_gnina_case_inputs_for_{case_id}"
                if case_inputs_ready
                else f"fill_vina_gnina_input_manifest_row_for_{case_id}"
            ),
        }
    return list(slots_by_case.values())


def _first_blocked_preflight_row(rows: Any) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and row.get("status") != "ready":
            return {
                "case_id": str(row.get("case_id") or ""),
                "complex_id": str(row.get("complex_id") or ""),
                "status": str(row.get("status") or ""),
                "missing_required_fields": [
                    str(item)
                    for item in row.get("missing_required_fields", [])
                    if str(item)
                ]
                if isinstance(row.get("missing_required_fields"), list)
                else [],
                "unsupported_benchmark_fields": [
                    str(item)
                    for item in row.get("unsupported_benchmark_fields", [])
                    if str(item)
                ]
                if isinstance(row.get("unsupported_benchmark_fields"), list)
                else [],
                "invalid_source_receipt_fields": [
                    str(item)
                    for item in row.get("invalid_source_receipt_fields", [])
                    if str(item)
                ]
                if isinstance(row.get("invalid_source_receipt_fields"), list)
                else [],
                "missing_local_file_fields": [
                    str(item)
                    for item in row.get("missing_local_file_fields", [])
                    if str(item)
                ]
                if isinstance(row.get("missing_local_file_fields"), list)
                else [],
                "missing_receipt_ref_fields": [
                    str(item)
                    for item in row.get("missing_receipt_ref_fields", [])
                    if str(item)
                ]
                if isinstance(row.get("missing_receipt_ref_fields"), list)
                else [],
                "blockers": [
                    str(item) for item in row.get("blockers", []) if str(item)
                ]
                if isinstance(row.get("blockers"), list)
                else [],
            }
    return {}


def _input_manifest_template_preflight_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT),
            "markdown_artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD),
            "status": "missing",
            "manifest_ready": False,
            "template_row_count": 0,
            "template_case_coverage_complete": False,
            "missing_required_value_count": 0,
            "unsupported_benchmark_field_count": 0,
            "invalid_source_receipt_count": 0,
            "invalid_checksum_count": 0,
            "missing_local_file_count": 0,
            "missing_receipt_ref_count": 0,
            "source_url_probe_count": 0,
            "source_url_probe_network_performed": False,
            "source_url_reachable_count": 0,
            "source_url_blocked_count": 0,
            "source_url_not_run_count": 0,
            "known_source_url_content_length_bytes": 0,
            "known_source_url_content_length_gib": 0.0,
            "source_url_probe_plan": [],
            "first_blocked_case_preflight": {},
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "present": True,
        "artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT),
        "markdown_artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD),
        "status": str(payload.get("status") or ""),
        "manifest_ready": bool(payload.get("manifest_ready")),
        "template_row_count": int(summary.get("template_row_count") or 0),
        "template_case_coverage_complete": bool(
            summary.get("template_case_coverage_complete")
        ),
        "missing_required_value_count": int(
            summary.get("missing_required_value_count") or 0
        ),
        "unsupported_benchmark_field_count": int(
            summary.get("unsupported_benchmark_field_count") or 0
        ),
        "invalid_source_receipt_count": int(
            summary.get("invalid_source_receipt_count") or 0
        ),
        "invalid_checksum_count": int(summary.get("invalid_checksum_count") or 0),
        "missing_local_file_count": int(
            summary.get("missing_local_file_count") or 0
        ),
        "missing_receipt_ref_count": int(
            summary.get("missing_receipt_ref_count") or 0
        ),
        "source_url_probe_count": int(summary.get("source_url_probe_count") or 0),
        "source_url_probe_network_performed": bool(
            summary.get("source_url_probe_network_performed")
        ),
        "source_url_reachable_count": int(
            summary.get("source_url_reachable_count") or 0
        ),
        "source_url_blocked_count": int(summary.get("source_url_blocked_count") or 0),
        "source_url_not_run_count": int(summary.get("source_url_not_run_count") or 0),
        "known_source_url_content_length_bytes": int(
            summary.get("known_source_url_content_length_bytes") or 0
        ),
        "known_source_url_content_length_gib": float(
            summary.get("known_source_url_content_length_gib") or 0.0
        ),
        "source_url_probe_plan": [
            {
                "source_url": str(row.get("source_url") or ""),
                "status": str(row.get("status") or ""),
                "case_count": len(row.get("case_ids", []))
                if isinstance(row.get("case_ids"), list)
                else 0,
                "content_length_bytes": int(
                    _as_dict(row.get("probe")).get("content_length_bytes") or 0
                ),
                "http_status": int(_as_dict(row.get("probe")).get("http_status") or 0),
                "head_command": str(row.get("head_command") or ""),
            }
            for row in payload.get("source_url_probe_plan", [])
            if isinstance(row, dict)
        ]
        if isinstance(payload.get("source_url_probe_plan"), list)
        else [],
        "first_blocked_case_preflight": _first_blocked_preflight_row(
            payload.get("case_preflight_rows")
        ),
    }


def _engine_run_bundle_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_ENGINE_RUN_BUNDLE)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_ENGINE_RUN_BUNDLE),
            "commands_artifact": str(DEFAULT_ENGINE_RUN_COMMANDS),
            "status": "missing",
            "contract_pass": False,
            "bundle_materialized": False,
            "case_count": 0,
            "engine_run_count": 0,
            "config_count": 0,
            "receipt_template_count": 0,
            "engine_runtime_ready": False,
            "operator_execution_ready": False,
            "blocker_count": 0,
            "blockers": [],
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        blockers = []
    return {
        "present": True,
        "artifact": str(DEFAULT_ENGINE_RUN_BUNDLE),
        "commands_artifact": str(DEFAULT_ENGINE_RUN_COMMANDS),
        "status": str(payload.get("status") or ""),
        "contract_pass": bool(payload.get("contract_pass")),
        "bundle_materialized": bool(
            payload.get("bundle_materialized")
            or summary.get("bundle_materialized")
        ),
        "case_count": int(payload.get("case_count") or summary.get("case_count") or 0),
        "engine_run_count": int(
            payload.get("engine_run_count") or summary.get("engine_run_count") or 0
        ),
        "config_count": int(payload.get("config_count") or 0),
        "receipt_template_count": int(payload.get("receipt_template_count") or 0),
        "engine_runtime_ready": bool(
            payload.get("engine_runtime_ready") or summary.get("engine_runtime_ready")
        ),
        "operator_execution_ready": bool(
            payload.get("operator_execution_ready")
            or summary.get("operator_execution_ready")
        ),
        "blocker_count": int(summary.get("blocker_count") or len(blockers)),
        "blockers": [str(item) for item in blockers if str(item)],
    }


def _rows_from_engine_run_bundle_report_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT),
            "status": "missing",
            "contract_pass": False,
            "rows_materialized": False,
            "bundle_ready": False,
            "case_count": 0,
            "engine_run_count": 0,
            "ready_engine_run_count": 0,
            "blocker_count": 0,
            "blockers": [],
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        blockers = []
    return {
        "present": True,
        "artifact": str(DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT),
        "status": str(payload.get("status") or ""),
        "contract_pass": bool(payload.get("contract_pass")),
        "rows_materialized": bool(
            payload.get("rows_materialized") or summary.get("rows_materialized")
        ),
        "bundle_ready": bool(summary.get("bundle_ready")),
        "case_count": int(summary.get("case_count") or 0),
        "engine_run_count": int(summary.get("engine_run_count") or 0),
        "ready_engine_run_count": int(summary.get("ready_engine_run_count") or 0),
        "blocker_count": int(summary.get("blocker_count") or len(blockers)),
        "blockers": [str(item) for item in blockers if str(item)],
    }


def _operator_unblock_packet(
    *,
    engine_run_slots: list[dict[str, Any]],
    current_engine_execution_statuses: list[dict[str, Any]],
    row_status: dict[str, Any],
    input_manifest_template_preflight_summary: dict[str, Any],
    engine_run_bundle_summary: dict[str, Any],
    rows_from_engine_run_bundle_report_summary: dict[str, Any],
    ready_engine_run_slot_count: int,
    required_engine_run_count: int,
    runtime_ready: bool,
    adapter_rows_ready: bool,
) -> dict[str, Any]:
    blocked_engine_run_slots = [
        row
        for row in engine_run_slots
        if str(row.get("status") or "") != "ready_for_engine_execution"
    ]
    case_input_slots = _case_input_unblock_slots(engine_run_slots)
    blocked_case_input_slots = [
        row for row in case_input_slots if str(row.get("status") or "") != "ready"
    ]
    missing_engine_ids = [
        str(row.get("engine_id") or "")
        for row in current_engine_execution_statuses
        if not bool(row.get("available")) and str(row.get("engine_id") or "")
    ]
    if blocked_case_input_slots:
        status = "engine_inputs_required"
    elif missing_engine_ids:
        status = "engine_runtime_required"
    elif not runtime_ready:
        status = "engine_run_slots_blocked"
    elif not adapter_rows_ready:
        status = "engine_run_rows_required"
    else:
        status = "adapter_materialization_ready"
    return {
        "status": status,
        "input_manifest_template_artifact": str(DEFAULT_INPUT_MANIFEST_TEMPLATE),
        "input_manifest_template_preflight_artifact": str(
            DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT
        ),
        "input_manifest_template_preflight_markdown_artifact": str(
            DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD
        ),
        "input_manifest_template_preflight_status": str(
            input_manifest_template_preflight_summary.get("status") or ""
        ),
        "input_manifest_template_manifest_ready": bool(
            input_manifest_template_preflight_summary.get("manifest_ready")
        ),
        "input_manifest_template_preflight_summary": (
            input_manifest_template_preflight_summary
        ),
        "expected_rows_artifact": str(DEFAULT_VINA_GNINA_ROWS),
        "engine_run_bundle_summary": engine_run_bundle_summary,
        "engine_run_bundle_status": str(engine_run_bundle_summary.get("status") or ""),
        "engine_run_bundle_materialized": bool(
            engine_run_bundle_summary.get("bundle_materialized")
        ),
        "rows_from_engine_run_bundle_report_summary": (
            rows_from_engine_run_bundle_report_summary
        ),
        "rows_from_engine_run_bundle_status": str(
            rows_from_engine_run_bundle_report_summary.get("status") or ""
        ),
        "rows_from_engine_run_bundle_materialized": bool(
            rows_from_engine_run_bundle_report_summary.get("rows_materialized")
        ),
        "rows_template_artifact": str(DEFAULT_VINA_GNINA_ROWS_TEMPLATE),
        "rows_template_preflight_artifact": str(
            DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT
        ),
        "rows_template_preflight_markdown_artifact": str(
            DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD
        ),
        "case_input_slot_count": len(case_input_slots),
        "blocked_case_input_slot_count": len(blocked_case_input_slots),
        "first_blocked_case_input_slot": (
            blocked_case_input_slots[0] if blocked_case_input_slots else {}
        ),
        "required_engine_run_count": required_engine_run_count,
        "ready_engine_run_slot_count": ready_engine_run_slot_count,
        "blocked_engine_run_slot_count": len(blocked_engine_run_slots),
        "first_blocked_engine_run_slot": (
            blocked_engine_run_slots[0] if blocked_engine_run_slots else {}
        ),
        "missing_engine_ids": missing_engine_ids,
        "engine_runtime_actions": [
            {
                "engine_id": engine_id,
                "binary_env_var": _engine_binary_env_var(engine_id),
                "container_image_env_var": _engine_container_image_env_var(engine_id),
                "operator_action": f"configure_{engine_id}_runtime",
            }
            for engine_id in SUPPORTED_ENGINES
        ],
        "adapter_row_preflight_status": str(row_status.get("status") or ""),
        "detected_row_artifact_count": int(
            row_status.get("detected_row_artifact_count") or 0
        ),
        "selected_row_path": str(row_status.get("selected_path") or ""),
        "operator_sequence": [
            "review_public_benchmark_vina_gnina_input_manifest_template_preflight",
            "fill_public_benchmark_vina_gnina_input_manifest_from_template",
            "rerun_public_benchmark_vina_gnina_execution_plan",
            "configure_vina_gnina_binary_or_container_runtime",
            "rerun_public_benchmark_vina_gnina_runtime_readiness",
            "materialize_public_benchmark_vina_gnina_engine_run_bundle",
            "review_public_benchmark_vina_gnina_rows_template_preflight",
            "attach_public_benchmark_vina_gnina_rows",
            "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle",
            "materialize_public_benchmark_vina_gnina_rows_from_completed_template",
            "materialize_public_benchmark_vina_gnina_comparison_adapter",
        ],
        "commands": {
            "build_input_manifest_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--out {DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT} "
                f"--out-md {DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD}"
            ),
            "build_rows_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py "
                f"--out {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT} "
                f"--out-md {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD}"
            ),
            "materialize_rows_from_template": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py "
                f"--template {DEFAULT_VINA_GNINA_ROWS_TEMPLATE} "
                f"--out-rows {DEFAULT_VINA_GNINA_ROWS} "
                f"--out-report {DEFAULT_VINA_GNINA_ROWS_FROM_TEMPLATE_REPORT}"
            ),
            "materialize_rows_from_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py "
                f"--engine-run-bundle {DEFAULT_ENGINE_RUN_BUNDLE} "
                f"--out-rows {DEFAULT_VINA_GNINA_ROWS} "
                f"--out-report {DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT}"
            ),
            "materialize_input_manifest_from_casf_archive": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
                "--archive <CASF-2016.tar.gz> "
                f"--out-manifest {PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest.csv'} "
                "--out-report "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json'}"
            ),
            "rerun_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {DEFAULT_EXECUTION_PLAN}"
            ),
            "materialize_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py "
                f"--execution-plan {DEFAULT_EXECUTION_PLAN} "
                f"--out {DEFAULT_ENGINE_RUN_BUNDLE} "
                f"--commands-out {DEFAULT_ENGINE_RUN_COMMANDS}"
            ),
            "rerun_runtime_readiness": (
                "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
                f"--out {DEFAULT_OUT}"
            ),
            "materialize_adapter": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {DEFAULT_VINA_GNINA_ROWS} --out-adapter "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                "--out-report "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
        },
        "claim_boundary": (
            "This packet only enumerates the operator steps needed to unblock "
            "Vina/GNINA execution and adapter row materialization. It does not run "
            "engines or synthesize comparison rows."
        ),
    }


def build_vina_gnina_runtime_readiness(
    *,
    repo_root: Path = ROOT,
    execution_plan_path: Path = DEFAULT_EXECUTION_PLAN,
    vina_gnina_rows_path: Path = DEFAULT_VINA_GNINA_ROWS,
) -> dict[str, Any]:
    execution_plan = _load_json(repo_root, execution_plan_path)
    docker_cli_status = _docker_cli_status()
    current_engine_statuses = [
        _engine_binary_status(engine_id) for engine_id in SUPPORTED_ENGINES
    ]
    current_engine_container_statuses = [
        _engine_container_status(engine_id, docker_cli_status=docker_cli_status)
        for engine_id in SUPPORTED_ENGINES
    ]
    container_status_by_id = {
        str(row.get("engine_id") or ""): row
        for row in current_engine_container_statuses
    }
    current_engine_execution_statuses = [
        _engine_execution_status(
            engine_id,
            binary_status,
            container_status_by_id.get(engine_id, {}),
        )
        for engine_id, binary_status in (
            (str(row.get("engine_id") or ""), row) for row in current_engine_statuses
        )
    ]
    engine_status_by_id = {
        str(row.get("engine_id") or ""): row
        for row in current_engine_execution_statuses
    }
    row_status = _row_candidate_status(repo_root, vina_gnina_rows_path)
    engine_run_slots = _engine_run_slots(execution_plan, engine_status_by_id)
    input_manifest_template_preflight = _input_manifest_template_preflight_summary(
        repo_root
    )
    engine_run_bundle = _engine_run_bundle_summary(repo_root)
    rows_from_engine_run_bundle_report = (
        _rows_from_engine_run_bundle_report_summary(repo_root)
    )
    execution_plan_ready = bool(execution_plan.get("execution_plan_ready"))
    all_engines_available = all(
        bool(row.get("available")) for row in current_engine_execution_statuses
    )
    adapter_rows_ready = bool(row_status.get("adapter_rows_ready"))
    slot_blockers = [
        f"{row['case_id']}::{row['engine_id']}::{blocker}"
        for row in engine_run_slots
        for blocker in row["blockers"]
    ]
    blockers: list[str] = []
    if not execution_plan_ready:
        blockers.append("vina_gnina_execution_plan_not_ready")
    blockers.extend(
        str(row.get("blocker"))
        for row in current_engine_statuses
        if str(row.get("blocker") or "")
        and not engine_status_by_id.get(str(row.get("engine_id") or ""), {}).get(
            "available"
        )
    )
    blockers.extend(
        str(row.get("blocker"))
        for row in current_engine_container_statuses
        if str(row.get("blocker") or "")
        and str(row.get("image") or "")
        and not engine_status_by_id.get(str(row.get("engine_id") or ""), {}).get(
            "available"
        )
    )
    row_blocker = str(row_status.get("blocker") or "")
    if row_blocker:
        blockers.append(row_blocker)
    blockers.extend(slot_blockers)
    blockers = list(dict.fromkeys(blockers))
    ready_engine_run_slot_count = sum(
        1 for row in engine_run_slots if row["status"] == "ready_for_engine_execution"
    )
    required_engine_run_count = int(
        execution_plan.get("required_engine_run_count") or len(engine_run_slots)
    )
    all_engine_run_slots_ready = (
        required_engine_run_count > 0
        and ready_engine_run_slot_count == required_engine_run_count
    )
    runtime_ready = (
        execution_plan_ready
        and all_engines_available
        and all_engine_run_slots_ready
    )
    operator_unblock_packet = _operator_unblock_packet(
        engine_run_slots=engine_run_slots,
        current_engine_execution_statuses=current_engine_execution_statuses,
        row_status=row_status,
        input_manifest_template_preflight_summary=input_manifest_template_preflight,
        engine_run_bundle_summary=engine_run_bundle,
        rows_from_engine_run_bundle_report_summary=rows_from_engine_run_bundle_report,
        ready_engine_run_slot_count=ready_engine_run_slot_count,
        required_engine_run_count=required_engine_run_count,
        runtime_ready=runtime_ready,
        adapter_rows_ready=adapter_rows_ready,
    )
    blocked_case_input_slot_count = int(
        operator_unblock_packet.get("blocked_case_input_slot_count") or 0
    )
    blocked_engine_run_slot_count = int(
        operator_unblock_packet.get("blocked_engine_run_slot_count") or 0
    )
    first_blocked_case_input_slot = operator_unblock_packet.get(
        "first_blocked_case_input_slot"
    )
    if not isinstance(first_blocked_case_input_slot, dict):
        first_blocked_case_input_slot = {}
    first_blocked_engine_run_slot = operator_unblock_packet.get(
        "first_blocked_engine_run_slot"
    )
    if not isinstance(first_blocked_engine_run_slot, dict):
        first_blocked_engine_run_slot = {}
    if not execution_plan_ready:
        status = "execution_plan_blocked"
    elif not all_engines_available:
        status = "engine_runtime_blocked"
    elif not all_engine_run_slots_ready:
        status = "engine_input_blocked"
    elif not adapter_rows_ready:
        status = "ready_for_engine_execution"
    else:
        status = "adapter_materialization_ready"
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_runtime_readiness.py"),
                execution_plan_path,
                Path("scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"),
                DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT,
                Path("scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
                DEFAULT_ENGINE_RUN_BUNDLE,
                DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_runtime_readiness_from_current_environment",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": True,
        "execution_plan_ready": execution_plan_ready,
        "runtime_ready_for_engine_execution": runtime_ready,
        "operator_execution_ready": runtime_ready and adapter_rows_ready,
        "adapter_rows_ready": adapter_rows_ready,
        "phase2_closure_ready": False,
        "supported_engines": list(SUPPORTED_ENGINES),
        "runtime_setup_requirements": _runtime_setup_requirements(),
        "container_runtime_status": docker_cli_status,
        "current_engine_binary_statuses": current_engine_statuses,
        "current_engine_container_statuses": current_engine_container_statuses,
        "current_engine_execution_statuses": current_engine_execution_statuses,
        "missing_engine_ids": [
            str(row.get("engine_id") or "")
            for row in current_engine_execution_statuses
            if not row.get("available")
        ],
        "row_candidate_status": row_status,
        "input_manifest_template_preflight": input_manifest_template_preflight,
        "engine_run_bundle_summary": engine_run_bundle,
        "rows_from_engine_run_bundle_report_summary": (
            rows_from_engine_run_bundle_report
        ),
        "engine_run_slots": engine_run_slots,
        "operator_unblock_packet": operator_unblock_packet,
        "required_engine_run_count": required_engine_run_count,
        "ready_engine_run_slot_count": ready_engine_run_slot_count,
        "blocked_case_input_slot_count": blocked_case_input_slot_count,
        "blocked_engine_run_slot_count": blocked_engine_run_slot_count,
        "first_blocked_case_input_slot": first_blocked_case_input_slot,
        "first_blocked_engine_run_slot": first_blocked_engine_run_slot,
        "operator_commands": {
            "build_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {DEFAULT_EXECUTION_PLAN}"
            ),
            "build_input_manifest_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--out {DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT} "
                f"--out-md {DEFAULT_INPUT_MANIFEST_TEMPLATE_PREFLIGHT_MD}"
            ),
            "build_rows_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py "
                f"--out {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT} "
                f"--out-md {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD}"
            ),
            "materialize_rows_from_template": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py "
                f"--template {DEFAULT_VINA_GNINA_ROWS_TEMPLATE} "
                f"--out-rows {vina_gnina_rows_path} "
                f"--out-report {DEFAULT_VINA_GNINA_ROWS_FROM_TEMPLATE_REPORT}"
            ),
            "materialize_rows_from_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py "
                f"--engine-run-bundle {DEFAULT_ENGINE_RUN_BUNDLE} "
                f"--out-rows {vina_gnina_rows_path} "
                f"--out-report {DEFAULT_VINA_GNINA_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT}"
            ),
            "materialize_input_manifest_from_casf_archive": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
                "--archive <CASF-2016.tar.gz> "
                f"--out-manifest {PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest.csv'} "
                "--out-report "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json'}"
            ),
            "set_binary_overrides": (
                "export PUBLIC_BENCHMARK_VINA_BIN=<path-to-vina> "
                "PUBLIC_BENCHMARK_GNINA_BIN=<path-to-gnina>"
            ),
            "set_container_image_overrides": (
                "export PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE=<local-vina-image> "
                "PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE=<local-gnina-image>"
            ),
            "inspect_container_images": (
                "docker image inspect \"$PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE\" "
                "\"$PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE\""
            ),
            "rerun_runtime_readiness": (
                "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
                f"--out {DEFAULT_OUT}"
            ),
            "materialize_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py "
                f"--execution-plan {execution_plan_path} "
                f"--out {DEFAULT_ENGINE_RUN_BUNDLE} "
                f"--commands-out {DEFAULT_ENGINE_RUN_COMMANDS}"
            ),
            "materialize_adapter_from_rows": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {vina_gnina_rows_path} "
                "--out-adapter "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                "--out-report "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
            "run_phase2_row_audit": (
                "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
                "--fail-blocked"
            ),
        },
        "blockers": blockers,
        "summary": {
            "execution_plan_ready": execution_plan_ready,
            "runtime_ready_for_engine_execution": runtime_ready,
            "operator_execution_ready": runtime_ready and adapter_rows_ready,
            "adapter_rows_ready": adapter_rows_ready,
            "case_count": int(execution_plan.get("case_count") or 0),
            "required_engine_run_count": int(
                execution_plan.get("required_engine_run_count")
                or len(engine_run_slots)
            ),
            "ready_engine_run_slot_count": ready_engine_run_slot_count,
            "blocked_case_input_slot_count": blocked_case_input_slot_count,
            "blocked_engine_run_slot_count": blocked_engine_run_slot_count,
            "first_blocked_case_input_case_id": str(
                first_blocked_case_input_slot.get("case_id") or ""
            ),
            "first_blocked_engine_run_case_id": str(
                first_blocked_engine_run_slot.get("case_id") or ""
            ),
            "first_blocked_engine_run_engine_id": str(
                first_blocked_engine_run_slot.get("engine_id") or ""
            ),
            "available_engine_count": sum(
                1 for row in current_engine_execution_statuses if row.get("available")
            ),
            "missing_engine_count": sum(
                1
                for row in current_engine_execution_statuses
                if not row.get("available")
            ),
            "detected_row_artifact_count": row_status[
                "detected_row_artifact_count"
            ],
            "selected_row_count": int(row_status.get("selected_row_count") or 0),
            "adapter_case_count": int(row_status.get("adapter_case_count") or 0),
            "adapter_row_preflight_status": str(row_status.get("status") or ""),
            "engine_run_bundle_status": str(engine_run_bundle.get("status") or ""),
            "engine_run_bundle_materialized": bool(
                engine_run_bundle.get("bundle_materialized")
            ),
            "rows_from_engine_run_bundle_report_status": str(
                rows_from_engine_run_bundle_report.get("status") or ""
            ),
            "rows_from_engine_run_bundle_materialized": bool(
                rows_from_engine_run_bundle_report.get("rows_materialized")
            ),
            "input_manifest_template_preflight_status": str(
                input_manifest_template_preflight.get("status") or ""
            ),
            "input_manifest_template_manifest_ready": bool(
                input_manifest_template_preflight.get("manifest_ready")
            ),
            "input_manifest_template_invalid_source_receipt_count": int(
                input_manifest_template_preflight.get(
                    "invalid_source_receipt_count"
                )
                or 0
            ),
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This receipt reflects current runtime readiness for Vina/GNINA engine "
            "execution and adapter materialization. It does not run docking engines, "
            "create comparison rows, synthesize receipts, or close Public Benchmark "
            "Phase 2 without real engine outputs passing the comparison adapter."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--execution-plan", type=Path, default=DEFAULT_EXECUTION_PLAN)
    parser.add_argument("--vina-gnina-rows", type=Path, default=DEFAULT_VINA_GNINA_ROWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_vina_gnina_runtime_readiness(
        repo_root=args.repo_root,
        execution_plan_path=args.execution_plan,
        vina_gnina_rows_path=args.vina_gnina_rows,
    )
    resolved_out = args.out if args.out.is_absolute() else args.repo_root / args.out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-runtime-readiness: "
            f"{payload['status']} | "
            f"ready_slots={payload['ready_engine_run_slot_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
