#!/usr/bin/env python3
"""Statically audit PM release reproduction commands embedded in handoff evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
from typing import Any


SCHEMA_VERSION = "pm-release-reproduction-command-audit.v1"
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_reproduction_command_audit.json"
)
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_INPUT_PATHS = (
    Path("implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"),
    Path("implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json"),
    Path("implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json"),
    Path("implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json"),
    Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"),
    Path("implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json"),
    Path("implementation/phase1/release_evidence/productization/license_status_intake_packet.json"),
)
DEFAULT_PACKAGE_JSON = Path("package.json")
COMMAND_FIELDS = frozenset(("reproduction_commands", "verification_commands", "validation_commands"))
SHELL_COMPOSITION_MARKERS = ("&&", "||", ";", "|", ">>", ">", "<", "$(", "`", "\n", "\r")
OUTPUT_PATH_FLAGS = frozenset(("--out", "--out-md", "--out-json", "--manifest-out", "--archive-out"))
OUTPUT_DIRECTORY_FLAGS = frozenset(("--bundle-dir",))
EXTERNAL_OWNER_NETWORK_SCRIPTS = frozenset(("build_github_actions_ci_streak_evidence.py",))
NPM_AUDIT_LEVELS = frozenset(("info", "low", "moderate", "high", "critical"))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_npm_scripts(path: Path) -> set[str]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return set()
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return set()
    return {str(key) for key in scripts}


def _iter_command_fields(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    fields: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key in COMMAND_FIELDS:
                fields.append((item_path, key, item))
            else:
                fields.extend(_iter_command_fields(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            fields.extend(_iter_command_fields(item, f"{path}[{index}]"))
    return fields


def _path_inside_repo(path_text: str, *, repo_root: Path) -> bool:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    try:
        candidate.resolve().relative_to(repo_root)
    except ValueError:
        return False
    return True


def _path_parent_exists(path_text: str, *, repo_root: Path) -> bool:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve().parent.exists()


def _script_exists(script_arg: str, *, repo_root: Path) -> bool:
    if not script_arg.startswith("scripts/"):
        return False
    return (repo_root / script_arg).exists()


def _command_output_blockers(argv: list[str], *, repo_root: Path) -> list[str]:
    blockers: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        path_text: str | None = None
        directory_mode = False
        if token in OUTPUT_PATH_FLAGS or token in OUTPUT_DIRECTORY_FLAGS:
            if index + 1 >= len(argv):
                blockers.append("command_unparseable")
                index += 1
                continue
            path_text = argv[index + 1]
            directory_mode = token in OUTPUT_DIRECTORY_FLAGS
            index += 2
        elif any(token.startswith(f"{flag}=") for flag in OUTPUT_PATH_FLAGS):
            path_text = token.split("=", 1)[1]
            index += 1
        elif any(token.startswith(f"{flag}=") for flag in OUTPUT_DIRECTORY_FLAGS):
            path_text = token.split("=", 1)[1]
            directory_mode = True
            index += 1
        else:
            index += 1

        if path_text is None:
            continue
        if not _path_inside_repo(path_text, repo_root=repo_root):
            blockers.append("command_output_path_escapes_repo")
        elif directory_mode:
            if not (repo_root / path_text).resolve().exists():
                blockers.append("command_output_parent_missing")
        elif not _path_parent_exists(path_text, repo_root=repo_root):
            blockers.append("command_output_parent_missing")
    return blockers


def _npm_audit_blockers(argv: list[str]) -> list[str]:
    blockers: list[str] = []
    index = 2
    while index < len(argv):
        token = argv[index]
        if token == "--audit-level":
            if index + 1 >= len(argv) or argv[index + 1] not in NPM_AUDIT_LEVELS:
                blockers.append("command_npm_audit_arg_not_allowlisted")
                index += 1
            else:
                index += 2
        elif token.startswith("--audit-level="):
            if token.split("=", 1)[1] not in NPM_AUDIT_LEVELS:
                blockers.append("command_npm_audit_arg_not_allowlisted")
            index += 1
        elif token in ("--json", "--production"):
            index += 1
        else:
            blockers.append("command_npm_audit_arg_not_allowlisted")
            index += 1
    return blockers


def _validate_command(
    command: Any,
    *,
    artifact_label: str,
    artifact_path: Path,
    field_name: str,
    json_path: str,
    command_index: int,
    repo_root: Path,
    npm_scripts: set[str],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "artifact": artifact_label,
        "artifact_path": str(artifact_path),
        "field": field_name,
        "json_path": f"{json_path}[{command_index}]",
        "command_index": command_index,
        "command": command if isinstance(command, str) else None,
        "parsed_argv": [],
        "execution_class": "unclassified",
        "contract_pass": False,
        "blockers": [],
    }
    blockers: list[str] = []
    if not isinstance(command, str):
        blockers.append("command_non_string")
        row["blockers"] = blockers
        return row
    if not command.strip():
        blockers.append("command_empty")
        row["blockers"] = blockers
        return row
    if any(marker in command for marker in SHELL_COMPOSITION_MARKERS):
        blockers.append("command_shell_composition")
        row["blockers"] = blockers
        return row
    try:
        argv = shlex.split(command)
    except ValueError:
        blockers.append("command_unparseable")
        row["blockers"] = blockers
        return row
    row["parsed_argv"] = argv
    if not argv:
        blockers.append("command_empty")
    elif argv[0] == "python3" and len(argv) >= 2 and argv[1].startswith("scripts/"):
        if not _script_exists(argv[1], repo_root=repo_root):
            blockers.append("command_script_missing")
        script_name = Path(argv[1]).name
        row["execution_class"] = (
            "external_owner_network"
            if script_name in EXTERNAL_OWNER_NETWORK_SCRIPTS
            else "local_static_or_report"
        )
    elif argv[0] == "node" and len(argv) >= 2 and argv[1].startswith("scripts/"):
        if not _script_exists(argv[1], repo_root=repo_root):
            blockers.append("command_script_missing")
        row["execution_class"] = "local_static_or_report"
    elif argv[0] == "./scripts" and len(argv) >= 2:
        blockers.append("command_root_not_allowlisted")
    elif argv[0].startswith("./scripts/") and argv[0].endswith(".sh"):
        script_arg = argv[0][2:]
        if not _script_exists(script_arg, repo_root=repo_root):
            blockers.append("command_script_missing")
        row["execution_class"] = "local_static_or_report"
    elif argv[:2] == ["npm", "run"] and len(argv) >= 3:
        target = argv[2]
        if target not in npm_scripts:
            blockers.append("command_npm_script_missing")
        row["execution_class"] = "local_static_or_report"
    elif argv[:2] == ["npm", "audit"]:
        blockers.extend(_npm_audit_blockers(argv))
        row["execution_class"] = "external_owner_network"
    elif argv[:2] == ["npm", "ci"] and len(argv) == 2:
        row["execution_class"] = "local_static_or_report"
    else:
        blockers.append("command_root_not_allowlisted")
    if argv:
        blockers.extend(_command_output_blockers(argv, repo_root=repo_root))
    row["blockers"] = blockers
    row["contract_pass"] = not blockers
    return row


def _artifact_label(path: Path) -> str:
    return path.stem.replace("-", "_")


def build_report(
    *,
    input_paths: list[Path] | None = None,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    paths = list(input_paths) if input_paths is not None else list(DEFAULT_INPUT_PATHS)
    npm_scripts = _load_npm_scripts(package_json if package_json.is_absolute() else repo_root / package_json)
    artifact_rows: list[dict[str, Any]] = []
    command_rows: list[dict[str, Any]] = []
    artifact_blockers: list[str] = []
    for input_path in paths:
        path = input_path if input_path.is_absolute() else repo_root / input_path
        label = _artifact_label(input_path)
        artifact_row = {
            "artifact": label,
            "path": str(input_path),
            "exists": path.exists(),
            "contract_pass": False,
            "command_count": 0,
            "violation_count": 0,
            "blockers": [],
        }
        payload = _load_json(path)
        if not path.exists():
            artifact_row["blockers"] = ["artifact_missing"]
            artifact_blockers.append(f"{label}:artifact_missing")
            artifact_rows.append(artifact_row)
            continue
        if not isinstance(payload, dict):
            artifact_row["blockers"] = ["artifact_json_unreadable_or_not_object"]
            artifact_blockers.append(f"{label}:artifact_json_unreadable_or_not_object")
            artifact_rows.append(artifact_row)
            continue
        for json_path, field_name, commands in _iter_command_fields(payload):
            if not isinstance(commands, list):
                row = _validate_command(
                    commands,
                    artifact_label=label,
                    artifact_path=input_path,
                    field_name=field_name,
                    json_path=json_path,
                    command_index=0,
                    repo_root=repo_root,
                    npm_scripts=npm_scripts,
                )
                command_rows.append(row)
                continue
            for index, command in enumerate(commands):
                command_rows.append(
                    _validate_command(
                        command,
                        artifact_label=label,
                        artifact_path=input_path,
                        field_name=field_name,
                        json_path=json_path,
                        command_index=index,
                        repo_root=repo_root,
                        npm_scripts=npm_scripts,
                    )
                )
        artifact_commands = [row for row in command_rows if row["artifact"] == label]
        artifact_violations = [blocker for row in artifact_commands for blocker in row["blockers"]]
        artifact_row["command_count"] = len(artifact_commands)
        artifact_row["violation_count"] = len(artifact_violations)
        artifact_row["contract_pass"] = not artifact_row["blockers"] and not artifact_violations
        artifact_rows.append(artifact_row)

    command_blockers = [blocker for row in command_rows for blocker in row["blockers"]]
    blockers = sorted({*artifact_blockers, *command_blockers})
    contract_pass = not blockers
    external_owner_command_count = sum(
        1 for row in command_rows if row.get("execution_class") == "external_owner_network"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "static_command_audit",
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT_BLOCKED",
        "summary_line": (
            f"PM reproduction command audit: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"artifacts={sum(1 for row in artifact_rows if row['contract_pass'])}/{len(artifact_rows)} | "
            f"commands={len(command_rows)} | violations={len(command_blockers)}"
        ),
        "summary": {
            "artifact_count": len(artifact_rows),
            "artifact_pass_count": sum(1 for row in artifact_rows if row["contract_pass"]),
            "command_count": len(command_rows),
            "violation_count": len(command_blockers),
            "external_owner_command_count": external_owner_command_count,
            "npm_script_count": len(npm_scripts),
        },
        "artifact_rows": artifact_rows,
        "command_rows": command_rows,
        "blockers": blockers,
        "validation_commands": [
            (
                "python3 scripts/build_pm_release_reproduction_command_audit.py "
                f"--out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}"
            ),
            "python3 scripts/build_support_bundle.py",
            (
                "python3 scripts/report_pm_release_gate.py "
                " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
                " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md"
            ),
        ],
        "claim_boundary": (
            "This audit is a static allowlist and path-safety check for embedded reproduction commands. "
            "It does not execute commands, contact GitHub/npm, or create owner-provided release evidence."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Reproduction Command Audit",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "## Artifacts",
        "",
        "| Artifact | Pass | Commands | Violations |",
        "|---|---:|---:|---:|",
    ]
    for row in payload["artifact_rows"]:
        lines.append(
            f"| `{row['artifact']}` | `{row['contract_pass']}` | "
            f"`{row['command_count']}` | `{row['violation_count']}` |"
        )
    lines.extend(["", "## Commands", "", "| Artifact | Field | Pass | Class | Blockers | Command |", "|---|---|---:|---|---|---|"])
    for row in payload["command_rows"]:
        blockers = ", ".join(f"`{item}`" for item in row["blockers"]) or "`none`"
        command = str(row.get("command") or "")
        lines.append(
            f"| `{row['artifact']}` | `{row['field']}` | `{row['contract_pass']}` | "
            f"`{row['execution_class']}` | {blockers} | `{command}` |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        for blocker in payload["blockers"]:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, dest="input_paths")
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        input_paths=args.input_paths,
        package_json=args.package_json,
        repo_root=args.repo_root,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
