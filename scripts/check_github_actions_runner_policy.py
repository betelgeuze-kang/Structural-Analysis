#!/usr/bin/env python3
"""Validate GitHub-hosted deterministic lanes and self-hosted hardware lanes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Collection, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_DIR = Path(".github/workflows")
GITHUB_HOSTED_LABEL_RE = re.compile(
    r"\b(?:ubuntu|windows|macos)-(?:latest|\d{2}\.\d{2}|\d{4})\b|"
    r"\b(?:ubuntu|windows|macos)-latest-(?:\d+core|\w+)\b",
    flags=re.IGNORECASE,
)
MATRIX_RUNNER_EXPRESSION_RE = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}$")
DEFAULT_GITHUB_HOSTED_WORKFLOWS = frozenset(
    {
        ".github/workflows/_technical-evidence-attest.yml",
        ".github/workflows/authoritative-core-evidence-resync.yml",
        ".github/workflows/authoritative-linear-core-ci.yml",
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-sealed-technical-attestor.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/core-quality-ci.yml",
        ".github/workflows/current-support-bundle.yml",
        ".github/workflows/current-main-evidence-index.yml",
        ".github/workflows/engine-v2-contract-ci.yml",
        ".github/workflows/engine-v2-determinism-ci.yml",
        ".github/workflows/fiber-frame-execution-topology-ci.yml",
        ".github/workflows/frontend-web-ci.yml",
        ".github/workflows/git-lfs-integrity.yml",
        ".github/workflows/ifc-import-health-current-source.yml",
        ".github/workflows/legacy-evidence-ci.yml",
        ".github/workflows/mgt-import-health-current-source.yml",
        ".github/workflows/mgt-import-health-tenth-source.yml",
        ".github/workflows/medium-scale-current-source.yml",
        ".github/workflows/nightly-full-quality.yml",
        ".github/workflows/native-nightly-quality.yml",
        ".github/workflows/native-pr-fast.yml",
        ".github/workflows/native-frame-alpha-clean-install.yml",
        ".github/workflows/opensees-calculix-clean-runner-attestor.yml",
        ".github/workflows/opensees-calculix-current-source.yml",
        ".github/workflows/p0-canonical-contract.yml",
        ".github/workflows/pr-metadata-ci.yml",
        ".github/workflows/product-state-current.yml",
        ".github/workflows/profile-scoped-product-state.yml",
        ".github/workflows/public-planar-cli-wheel-ci.yml",
        ".github/workflows/python-test-collection.yml",
        ".github/workflows/repository-hygiene-freshness.yml",
        ".github/workflows/runtime-input-viewer-ci.yml",
        ".github/workflows/science-quarantine-ci.yml",
        ".github/workflows/viewer-browser-ci.yml",
        ".github/workflows/workflow-contract-ci.yml",
    }
)
DEFAULT_GITHUB_HOSTED_JOB_ALLOWLIST: dict[tuple[str, str], frozenset[str]] = {
    (
        ".github/workflows/bounded-planar-sealed-technical-attestor.yml",
        "attest",
    ): frozenset({"ubuntu-24.04"}),
    (".github/workflows/deploy-pages.yml", "deploy"): frozenset({"ubuntu-24.04"}),
}


def _workflow_files(workflow_dir: Path) -> list[Path]:
    if not workflow_dir.exists():
        return []
    return sorted(
        path
        for path in workflow_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


def _display_path(path: Path, workflow_dir: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        if workflow_dir.name == "workflows" and workflow_dir.parent.name == ".github":
            return str(Path(".github/workflows") / path.name)
        return str(path)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _clean_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        return ""
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    return value.strip().strip('"').strip("'")


def _collect_nested_list_values(
    *,
    lines: list[str],
    start_index: int,
    parent_indent: int,
) -> tuple[list[str], int]:
    values: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if _indent(line) <= parent_indent:
            break
        if stripped.startswith("- "):
            value = _clean_scalar(stripped[2:])
            if value:
                values.append(value)
        index += 1
    return values, index


def _job_id_at(lines: list[str], index: int) -> str:
    for candidate in reversed(lines[:index]):
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*", candidate)
        if match is not None and match.group(1) != "jobs":
            return match.group(1)
    return ""


def _runs_on_entries(lines: list[str]) -> list[tuple[int, str, str]]:
    entries: list[tuple[int, str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped.startswith("runs-on:"):
            index += 1
            continue
        line_number = index + 1
        runs_on_indent = _indent(line)
        inline_value = _clean_scalar(stripped.split(":", 1)[1])
        if inline_value:
            entries.append((line_number, inline_value, _job_id_at(lines, index)))
            index += 1
            continue

        values: list[str] = []
        child_index = index + 1
        while child_index < len(lines):
            child = lines[child_index]
            child_stripped = child.strip()
            if not child_stripped or child_stripped.startswith("#"):
                child_index += 1
                continue
            child_indent = _indent(child)
            if child_indent <= runs_on_indent:
                break
            if child_stripped.startswith("- "):
                value = _clean_scalar(child_stripped[2:])
                if value:
                    values.append(value)
                child_index += 1
                continue
            if child_stripped.startswith("labels:"):
                label_value = _clean_scalar(child_stripped.split(":", 1)[1])
                if label_value:
                    values.append(label_value)
                    child_index += 1
                    continue
                nested, next_index = _collect_nested_list_values(
                    lines=lines,
                    start_index=child_index + 1,
                    parent_indent=child_indent,
                )
                values.extend(nested)
                child_index = next_index
                continue
            child_index += 1
        entries.append((line_number, ", ".join(values), _job_id_at(lines, index)))
        index = child_index
    return entries


def _resolve_matrix_runner_values(*, lines: list[str], value: str) -> str:
    """Resolve an inline or include-only matrix axis used by ``runs-on``."""

    match = MATRIX_RUNNER_EXPRESSION_RE.fullmatch(value)
    if match is None:
        return value
    axis = re.escape(match.group(1))
    inline_axis = re.compile(rf"^\s*{axis}\s*:\s*\[(?P<values>[^\]]+)\]\s*(?:#.*)?$")
    for line in lines:
        axis_match = inline_axis.match(line)
        if axis_match is None:
            continue
        values = [_clean_scalar(item) for item in axis_match.group("values").split(",")]
        resolved = [item for item in values if item]
        if resolved:
            return ", ".join(resolved)
    include_axis = re.compile(rf"^\s*-\s+{axis}\s*:\s*(?P<value>[^#]+?)\s*(?:#.*)?$")
    resolved = []
    for line in lines:
        axis_match = include_axis.match(line)
        if axis_match is None:
            continue
        item = _clean_scalar(axis_match.group("value"))
        if item and item not in resolved:
            resolved.append(item)
    if resolved:
        return ", ".join(resolved)
    return value


def check_runner_policy(
    *,
    workflow_dir: Path = DEFAULT_WORKFLOW_DIR,
    github_hosted_allowlist: Collection[str] | None = None,
    github_hosted_job_allowlist: Mapping[tuple[str, str], Collection[str]] | None = None,
) -> dict[str, Any]:
    """Require explicit execution classes instead of a repository-wide runner type."""

    workflow_dir = workflow_dir if workflow_dir.is_absolute() else ROOT / workflow_dir
    allowlist = set(
        DEFAULT_GITHUB_HOSTED_WORKFLOWS
        if github_hosted_allowlist is None
        else github_hosted_allowlist
    )
    job_allowlist = {
        key: set(labels)
        for key, labels in (
            DEFAULT_GITHUB_HOSTED_JOB_ALLOWLIST
            if github_hosted_job_allowlist is None
            else github_hosted_job_allowlist
        ).items()
    }
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for workflow in _workflow_files(workflow_dir):
        rel_path = _display_path(workflow, workflow_dir)
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for line_number, value, job_id in _runs_on_entries(lines):
            exact_labels = job_allowlist.get((rel_path, job_id))
            deterministic_hosted = rel_path in allowlist or exact_labels is not None
            resolved_value = _resolve_matrix_runner_values(
                lines=lines,
                value=value,
            )
            github_hosted = bool(GITHUB_HOSTED_LABEL_RE.search(resolved_value))
            self_hosted = "self-hosted" in resolved_value
            if deterministic_hosted:
                ok = github_hosted and not self_hosted
                execution_class = "deterministic_github_hosted"
                if not github_hosted:
                    blockers.append(
                        f"{rel_path}:{line_number}:github_hosted_runner_required:{value}"
                    )
                if self_hosted:
                    blockers.append(
                        f"{rel_path}:{line_number}:deterministic_lane_uses_self_hosted:{value}"
                    )
                if exact_labels is not None:
                    resolved_labels = {
                        item.strip()
                        for item in resolved_value.split(",")
                        if item.strip()
                    }
                    if resolved_labels != exact_labels:
                        ok = False
                        blockers.append(
                            f"{rel_path}:{line_number}:hosted_job_runner_not_exact:{value}"
                        )
            else:
                ok = self_hosted and not github_hosted
                execution_class = "hardware_or_private_self_hosted"
                if github_hosted:
                    blockers.append(
                        f"{rel_path}:{line_number}:unapproved_github_hosted_runner:{value}"
                    )
                if not self_hosted:
                    blockers.append(
                        f"{rel_path}:{line_number}:self_hosted_default_missing:{value}"
                    )
            rows.append(
                {
                    "workflow": rel_path,
                    "job": job_id,
                    "line": line_number,
                    "runs_on": value,
                    "resolved_runs_on": resolved_value,
                    "execution_class": execution_class,
                    "github_hosted_allowlisted": deterministic_hosted,
                    "github_hosted_label": github_hosted,
                    "self_hosted_default": self_hosted,
                    "ok": ok,
                }
            )
    if not rows:
        blockers.append(f"{_display_path(workflow_dir, workflow_dir)}:runs_on_missing")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "github-actions-runner-policy.v2",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "workflow_count": len(_workflow_files(workflow_dir)),
        "runs_on_count": len(rows),
        "github_hosted_allowlist": sorted(allowlist),
        "github_hosted_job_allowlist": {
            f"{workflow}#{job}": sorted(labels)
            for (workflow, job), labels in sorted(job_allowlist.items())
        },
        "deterministic_github_hosted_count": sum(
            row["execution_class"] == "deterministic_github_hosted" for row in rows
        ),
        "hardware_or_private_self_hosted_count": sum(
            row["execution_class"] == "hardware_or_private_self_hosted" for row in rows
        ),
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": (
            "Deterministic structural-core, Engine v2 contract, frontend, viewer, "
            "legacy-evidence, product-state, current support-bundle, repository-hygiene, external technical "
            "V&V, science-quarantine, workflow-contract, and canonical nightly lanes "
            "may use explicitly allowlisted GitHub-hosted runners. "
            "Hardware, GPU, non-public private-corpus, release-publication, and other "
            "non-allowlisted lanes must remain self-hosted. An explicitly allowlisted lane "
            "may use hosted runners for immutable public inputs only when raw inputs are not "
            "uploaded. Science-quarantine execution does not promote "
            "that code into the structural product surface."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path, default=DEFAULT_WORKFLOW_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_runner_policy(workflow_dir=args.workflow_dir)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"GitHub Actions runner policy: {payload['status']}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
