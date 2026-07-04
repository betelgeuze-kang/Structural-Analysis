#!/usr/bin/env python3
"""Materialize Vina/GNINA engine run commands from a ready execution plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_EXECUTION_PLAN = PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_bundle.json"
DEFAULT_COMMANDS_OUT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_commands.sh"
)
DEFAULT_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json"
)
DEFAULT_VINA_GNINA_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
SCHEMA_VERSION = "public-benchmark-vina-gnina-engine-run-bundle.v1"
ENGINE_CONFIG_SCHEMA_VERSION = "public-benchmark-vina-gnina-engine-config.v1"
ENGINE_RECEIPT_TEMPLATE_SCHEMA_VERSION = (
    "public-benchmark-vina-gnina-engine-run-receipt-template.v1"
)
SCORE_DIRECTION_DEFAULT = "lower_is_better"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_output_ref(value: Any) -> tuple[Path | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, "output_ref_missing"
    if text.startswith(("http://", "https://")):
        return None, "output_ref_external"
    path = Path(text)
    if path.is_absolute():
        return None, "output_ref_absolute"
    if any(part in {"", ".", ".."} for part in path.parts):
        return None, "output_ref_unsafe"
    return path, ""


def _engine_status_by_id(execution_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("engine_id") or ""): row
        for row in _as_list(execution_plan.get("engine_execution_statuses"))
        if isinstance(row, dict)
    }


def _quoted(value: Any) -> str:
    return shlex.quote(str(value or ""))


def _run_command(run: dict[str, Any], engine_status: dict[str, Any]) -> str:
    engine_id = str(run.get("engine_id") or "")
    command_prefix = str(engine_status.get("command_prefix") or "").strip()
    if not command_prefix:
        command_prefix = f"<PUBLIC_BENCHMARK_{engine_id.upper()}_BIN_OR_CONTAINER>"
    docking_box = _as_dict(run.get("docking_box"))
    center = _as_dict(docking_box.get("center"))
    size = _as_dict(docking_box.get("size"))
    return " ".join(
        [
            command_prefix,
            "--receptor",
            _quoted(run.get("prepared_receptor_path")),
            "--ligand",
            _quoted(run.get("prepared_ligand_path")),
            "--center_x",
            _quoted(center.get("x")),
            "--center_y",
            _quoted(center.get("y")),
            "--center_z",
            _quoted(center.get("z")),
            "--size_x",
            _quoted(size.get("x")),
            "--size_y",
            _quoted(size.get("y")),
            "--size_z",
            _quoted(size.get("z")),
            "--out",
            _quoted(run.get("expected_predicted_ligand_path_or_pose_ref")),
        ]
    )


def _config_payload(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    docking_box = _as_dict(run.get("docking_box"))
    return {
        "schema_version": ENGINE_CONFIG_SCHEMA_VERSION,
        "case_id": str(case.get("case_id") or ""),
        "complex_id": str(case.get("complex_id") or ""),
        "benchmark_split": str(case.get("benchmark_split") or ""),
        "source_family": str(case.get("source_family") or ""),
        "reference_pose_id": str(case.get("reference_pose_id") or ""),
        "engine_id": str(run.get("engine_id") or ""),
        "docking_run_id": str(run.get("docking_run_id") or ""),
        "prepared_receptor_path": str(run.get("prepared_receptor_path") or ""),
        "prepared_ligand_path": str(run.get("prepared_ligand_path") or ""),
        "expected_predicted_ligand_path_or_pose_ref": str(
            run.get("expected_predicted_ligand_path_or_pose_ref") or ""
        ),
        "docking_box": docking_box,
        "source_license_or_accession": str(
            case.get("source_license_or_accession") or ""
        ),
        "source_checksum": str(case.get("subset_source_checksum") or ""),
        "provenance_ref": str(case.get("provenance_ref") or ""),
        "score_direction": SCORE_DIRECTION_DEFAULT,
        "claim_boundary": (
            "This config is generated from a ready Vina/GNINA execution plan. It "
            "does not prove an engine was run; the paired receipt must be replaced "
            "or completed with real engine output evidence."
        ),
    }


def _receipt_template_payload(
    *,
    case: dict[str, Any],
    run: dict[str, Any],
    command: str,
    config_checksum: str,
    engine_status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ENGINE_RECEIPT_TEMPLATE_SCHEMA_VERSION,
        "status": "operator_run_required",
        "case_id": str(case.get("case_id") or ""),
        "complex_id": str(case.get("complex_id") or ""),
        "engine_id": str(run.get("engine_id") or ""),
        "docking_run_id": str(run.get("docking_run_id") or ""),
        "command": command,
        "prepared_receptor_path": str(run.get("prepared_receptor_path") or ""),
        "prepared_ligand_path": str(run.get("prepared_ligand_path") or ""),
        "predicted_ligand_path_or_pose_ref": str(
            run.get("expected_predicted_ligand_path_or_pose_ref") or ""
        ),
        "predicted_ligand_checksum": "",
        "engine_version": str(engine_status.get("version") or ""),
        "engine_config_checksum": config_checksum,
        "engine_run_provenance_ref": str(
            run.get("expected_engine_run_provenance_ref") or ""
        ),
        "symmetry_aware_rmsd_angstrom": "",
        "pose_success": "",
        "score": "",
        "score_direction": SCORE_DIRECTION_DEFAULT,
        "operator_required_fields": [
            "predicted_ligand_checksum",
            "engine_version",
            "symmetry_aware_rmsd_angstrom",
            "pose_success",
            "score",
        ],
        "claim_boundary": (
            "This is a receipt template, not evidence of a completed Vina/GNINA "
            "run. Public Benchmark Phase 2 requires real predicted ligand output "
            "checksums and comparison metrics before adapter rows can be promoted."
        ),
    }


def _bundle_rows(
    execution_plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    engine_statuses = _engine_status_by_id(execution_plan)
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for case in _as_list(execution_plan.get("case_execution_plans")):
        if not isinstance(case, dict):
            continue
        for run in _as_list(case.get("engine_runs")):
            if not isinstance(run, dict):
                continue
            engine_id = str(run.get("engine_id") or "")
            config_ref = str(run.get("expected_engine_config_ref") or "")
            receipt_ref = str(run.get("expected_engine_run_provenance_ref") or "")
            config_path, config_blocker = _safe_output_ref(config_ref)
            receipt_path, receipt_blocker = _safe_output_ref(receipt_ref)
            run_key = f"{case.get('case_id', '')}::{engine_id}"
            if config_blocker:
                blockers.append(f"{run_key}::{config_blocker}")
            if receipt_blocker:
                blockers.append(f"{run_key}::{receipt_blocker}")
            engine_status = engine_statuses.get(engine_id, {})
            command = _run_command(run, engine_status)
            config = _config_payload(case, run)
            config_text = _json_text(config)
            config_checksum = _sha256_text(config_text)
            receipt = _receipt_template_payload(
                case=case,
                run=run,
                command=command,
                config_checksum=config_checksum,
                engine_status=engine_status,
            )
            rows.append(
                {
                    "case_id": str(case.get("case_id") or ""),
                    "complex_id": str(case.get("complex_id") or ""),
                    "benchmark_split": str(case.get("benchmark_split") or ""),
                    "source_family": str(case.get("source_family") or ""),
                    "reference_pose_id": str(case.get("reference_pose_id") or ""),
                    "engine_id": engine_id,
                    "docking_run_id": str(run.get("docking_run_id") or ""),
                    "config_ref": config_ref,
                    "config_path": str(config_path or ""),
                    "config_checksum": config_checksum,
                    "receipt_template_ref": receipt_ref,
                    "receipt_template_path": str(receipt_path or ""),
                    "predicted_ligand_path_or_pose_ref": str(
                        run.get("expected_predicted_ligand_path_or_pose_ref") or ""
                    ),
                    "command": command,
                    "engine_runtime_available": bool(engine_status.get("available")),
                    "engine_execution_source": str(
                        engine_status.get("execution_source") or ""
                    ),
                    "config_payload": config,
                    "receipt_template_payload": receipt,
                    "blockers": [
                        blocker
                        for blocker in (config_blocker, receipt_blocker)
                        if blocker
                    ],
                }
            )
    return rows, blockers


def _commands_text(bundle_rows: list[dict[str, Any]]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated Vina/GNINA commands. Review runtime paths before execution.",
    ]
    for row in bundle_rows:
        pose_ref = Path(str(row["predicted_ligand_path_or_pose_ref"]))
        config_ref = Path(str(row["config_ref"]))
        receipt_ref = Path(str(row["receipt_template_ref"]))
        output_dirs = sorted(
            {
                str(path.parent)
                for path in (pose_ref, config_ref, receipt_ref)
                if str(path.parent) not in {"", "."}
            }
        )
        if output_dirs:
            lines.append("mkdir -p " + " ".join(_quoted(path) for path in output_dirs))
        lines.append(str(row["command"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def materialize_public_benchmark_vina_gnina_engine_run_bundle(
    *,
    repo_root: Path = ROOT,
    execution_plan: Path = DEFAULT_EXECUTION_PLAN,
    out: Path = DEFAULT_OUT,
    commands_out: Path = DEFAULT_COMMANDS_OUT,
) -> dict[str, Any]:
    plan = _load_json(repo_root, execution_plan)
    bundle_rows, row_blockers = _bundle_rows(plan)
    execution_plan_ready = bool(plan.get("execution_plan_ready"))
    bundle_materialized = False
    write_blockers: list[str] = []
    if execution_plan_ready and not row_blockers:
        for row in bundle_rows:
            config_path = Path(str(row["config_path"]))
            receipt_path = Path(str(row["receipt_template_path"]))
            try:
                _write_json(repo_root, config_path, row["config_payload"])
                _write_json(repo_root, receipt_path, row["receipt_template_payload"])
            except OSError as exc:
                write_blockers.append(
                    f"{row['case_id']}::{row['engine_id']}::{exc.__class__.__name__}"
                )
        if not write_blockers:
            resolved_commands = _resolve(repo_root, commands_out)
            resolved_commands.parent.mkdir(parents=True, exist_ok=True)
            resolved_commands.write_text(_commands_text(bundle_rows), encoding="utf-8")
            resolved_commands.chmod(0o755)
            bundle_materialized = True

    blockers: list[str] = []
    if not execution_plan_ready:
        blockers.append("public_benchmark_vina_gnina_execution_plan_not_ready")
    blockers.extend(row_blockers)
    blockers.extend(write_blockers)
    blockers = list(dict.fromkeys(blockers))
    if bundle_materialized:
        status = "engine_run_bundle_materialized"
    elif execution_plan_ready:
        status = "engine_run_bundle_materialization_blocked"
    else:
        status = "execution_plan_not_ready"
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path(
                    "scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py"
                ),
                execution_plan,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_engine_run_bundle_from_execution_plan",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bundle_materialized,
        "bundle_materialized": bundle_materialized,
        "execution_plan_ready": execution_plan_ready,
        "operator_execution_ready": bool(plan.get("operator_execution_ready")),
        "engine_runtime_ready": not bool(plan.get("missing_engine_ids")),
        "execution_plan_artifact": str(execution_plan),
        "commands_artifact": str(commands_out),
        "out_artifact": str(out),
        "case_count": len(
            [
                row
                for row in _as_list(plan.get("case_execution_plans"))
                if isinstance(row, dict)
            ]
        ),
        "engine_run_count": len(bundle_rows),
        "config_count": len(bundle_rows) if bundle_materialized else 0,
        "receipt_template_count": len(bundle_rows) if bundle_materialized else 0,
        "engine_runtime_missing_ids": [
            str(row) for row in _as_list(plan.get("missing_engine_ids")) if str(row)
        ],
        "bundle_rows": bundle_rows,
        "blockers": blockers,
        "commands": {
            "rerun_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {execution_plan}"
            ),
            "rerun_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py "
                f"--execution-plan {execution_plan} --out {out} "
                f"--commands-out {commands_out}"
            ),
            "materialize_rows_from_completed_template": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py "
                "--fail-blocked"
            ),
            "materialize_rows_from_engine_run_bundle": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py "
                f"--engine-run-bundle {out} "
                f"--out-rows {DEFAULT_VINA_GNINA_ROWS} "
                f"--out-report {DEFAULT_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT} "
                "--fail-blocked"
            ),
        },
        "summary": {
            "execution_plan_ready": execution_plan_ready,
            "operator_execution_ready": bool(plan.get("operator_execution_ready")),
            "engine_runtime_ready": not bool(plan.get("missing_engine_ids")),
            "case_count": len(
                [
                    row
                    for row in _as_list(plan.get("case_execution_plans"))
                    if isinstance(row, dict)
                ]
            ),
            "engine_run_count": len(bundle_rows),
            "bundle_materialized": bundle_materialized,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This helper materializes Vina/GNINA config files, command scripts, "
            "and receipt templates only from a ready execution plan. It does not "
            "run docking engines, compute RMSD, score poses, or promote adapter "
            "rows without real engine output receipts."
        ),
    }
    _write_json(repo_root, out, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--execution-plan", type=Path, default=DEFAULT_EXECUTION_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--commands-out", type=Path, default=DEFAULT_COMMANDS_OUT)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_public_benchmark_vina_gnina_engine_run_bundle(
        repo_root=args.repo_root,
        execution_plan=args.execution_plan,
        out=args.out,
        commands_out=args.commands_out,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-engine-run-bundle: "
            f"{payload['status']} | runs={payload['engine_run_count']} | "
            f"written={payload['bundle_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
