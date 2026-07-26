#!/usr/bin/env python3
"""Validate the capability registry and generate all public support surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pprint
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("artifacts/manifests/capabilities.yaml")
README_PATH = Path("README.md")
API_DOC_PATH = Path("docs/api-capabilities.md")
PYTHON_PATH = Path("src/structural_analysis/generated_capabilities.py")
WORKBENCH_PATH = Path("src/workbench-v2/model/generatedCapabilities.json")
BEGIN_MARKER = "<!-- BEGIN GENERATED CAPABILITY SUPPORT -->"
END_MARKER = "<!-- END GENERATED CAPABILITY SUPPORT -->"
ALLOWED_STATUSES = {
    "supported",
    "bounded_public",
    "experimental",
    "shadow_only",
    "blocked",
}
PUBLIC_STATUSES = {"supported", "bounded_public"}


class CapabilityRegistryError(ValueError):
    """Raised when the canonical registry violates its contract."""


def load_registry(repo_root: Path = ROOT) -> dict[str, Any]:
    path = repo_root / REGISTRY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CapabilityRegistryError(f"invalid registry: {error}") from error
    if not isinstance(payload, dict):
        raise CapabilityRegistryError("registry root must be an object")
    validate_registry(payload, repo_root=repo_root)
    return payload


def validate_registry(registry: dict[str, Any], *, repo_root: Path) -> None:
    if registry.get("schema_version") != "structural-analysis-capabilities.v1":
        raise CapabilityRegistryError("unsupported schema_version")
    rows = registry.get("capabilities")
    if not isinstance(rows, list) or not rows:
        raise CapabilityRegistryError("capabilities must be a non-empty list")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CapabilityRegistryError(f"capabilities[{index}] must be an object")
        capability_id = str(row.get("id", "")).strip()
        if not capability_id or capability_id in seen:
            raise CapabilityRegistryError(f"invalid or duplicate capability id: {capability_id}")
        seen.add(capability_id)
        status = str(row.get("status", "")).strip()
        if status not in ALLOWED_STATUSES:
            raise CapabilityRegistryError(f"{capability_id}: invalid status {status}")
        public = row.get("public")
        if not isinstance(public, bool):
            raise CapabilityRegistryError(f"{capability_id}: public must be boolean")
        if public != (status in PUBLIC_STATUSES):
            raise CapabilityRegistryError(
                f"{capability_id}: public flag must match supported/bounded_public status"
            )
        interfaces = row.get("interfaces")
        limitations = row.get("limitations")
        evidence = row.get("evidence")
        if not isinstance(interfaces, list) or not interfaces:
            raise CapabilityRegistryError(f"{capability_id}: interfaces are required")
        if not isinstance(limitations, list) or not limitations:
            raise CapabilityRegistryError(f"{capability_id}: limitations are required")
        if not isinstance(evidence, list) or not evidence:
            raise CapabilityRegistryError(f"{capability_id}: evidence is required")
        for evidence_path in evidence:
            if not (repo_root / str(evidence_path)).exists():
                raise CapabilityRegistryError(
                    f"{capability_id}: missing evidence path {evidence_path}"
                )
        if row.get("authority") == "none" and public:
            raise CapabilityRegistryError(
                f"{capability_id}: public capability cannot have authority none"
            )
    authority = registry.get("authority_rules")
    if not isinstance(authority, dict):
        raise CapabilityRegistryError("authority_rules must be an object")
    if authority.get("solver_truth_owner") != "structural_analysis_core":
        raise CapabilityRegistryError("solver truth owner must remain structural_analysis_core")
    if authority.get("workbench_truth_owner") != "none":
        raise CapabilityRegistryError("Workbench cannot own solver truth")
    if authority.get("ai_truth_owner") != "none":
        raise CapabilityRegistryError("AI control cannot own solver truth")
    if authority.get("fallback_promotion_allowed") is not False:
        raise CapabilityRegistryError("fallback promotion must remain disabled")


def _cell(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_table(registry: dict[str, Any]) -> str:
    lines = [
        "| Capability | Status | Public | Authority | Interfaces | Exact profile / boundary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in registry["capabilities"]:
        boundary = f"{row['profile']}; {row['limitations'][0]}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row["title"]),
                    _cell(row["status"]),
                    "yes" if row["public"] else "no",
                    _cell(row["authority"]),
                    _cell(row["interfaces"]),
                    _cell(boundary),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_readme_block(registry: dict[str, Any]) -> str:
    return (
        f"{BEGIN_MARKER}\n"
        "## Generated capability support matrix\n\n"
        "This table is generated from artifacts/manifests/capabilities.yaml. "
        "Do not edit it directly.\n\n"
        f"{render_table(registry)}\n"
        f"{END_MARKER}"
    )


def replace_marked_block(text: str, block: str) -> str:
    if BEGIN_MARKER not in text and END_MARKER not in text:
        return text.rstrip() + "\n\n" + block + "\n"
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise CapabilityRegistryError("README capability markers must occur exactly once")
    before, remainder = text.split(BEGIN_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    return before.rstrip() + "\n\n" + block + after.rstrip() + "\n"


def render_api_doc(registry: dict[str, Any]) -> str:
    return (
        "# API Capability Support\n\n"
        "Generated from artifacts/manifests/capabilities.yaml. Do not edit directly.\n\n"
        + render_table(registry)
        + "\n\n"
        "The Python API exposes the same registry through "
        "structural_analysis.api.capabilities(). The structural-analysis CLI "
        "prints it with --capabilities. Experimental, shadow-only, and blocked "
        "rows are discovery metadata, not executable public support.\n"
    )


def render_python(registry: dict[str, Any]) -> str:
    rows = tuple(registry["capabilities"])
    return (
        '"""Generated capability registry. Do not edit directly."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        f"CAPABILITY_SCHEMA_VERSION = {registry['schema_version']!r}\n"
        "CAPABILITY_AUTHORITY_RULES: dict[str, Any] = "
        + pprint.pformat(registry["authority_rules"], width=100, sort_dicts=True)
        + "\n"
        "CAPABILITY_ROWS: tuple[dict[str, Any], ...] = "
        + pprint.pformat(rows, width=100, sort_dicts=True)
        + "\n\n"
        "def capabilities(*, public_only: bool = False) -> tuple[dict[str, Any], ...]:\n"
        "    rows = CAPABILITY_ROWS\n"
        "    if public_only:\n"
        "        rows = tuple(row for row in rows if row['public'])\n"
        "    return tuple(dict(row) for row in rows)\n"
    )


def render_workbench_json(registry: dict[str, Any]) -> str:
    payload = {
        "schemaVersion": registry["schema_version"],
        "authorityRules": registry["authority_rules"],
        "capabilities": registry["capabilities"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def expected_outputs(repo_root: Path = ROOT) -> dict[Path, str]:
    registry = load_registry(repo_root)
    readme = (repo_root / README_PATH).read_text(encoding="utf-8")
    return {
        README_PATH: replace_marked_block(readme, render_readme_block(registry)),
        API_DOC_PATH: render_api_doc(registry),
        PYTHON_PATH: render_python(registry),
        WORKBENCH_PATH: render_workbench_json(registry),
    }


def check_outputs(repo_root: Path = ROOT) -> list[str]:
    mismatches: list[str] = []
    for relative, expected in expected_outputs(repo_root).items():
        path = repo_root / relative
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != expected:
            mismatches.append(relative.as_posix())
    return mismatches


def write_outputs(repo_root: Path = ROOT) -> None:
    for relative, content in expected_outputs(repo_root).items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        write_outputs(args.repo_root)
    mismatches = check_outputs(args.repo_root)
    report = {
        "schema_version": "capability-surface-generation-check.v1",
        "status": "pass" if not mismatches else "blocked",
        "contract_pass": not mismatches,
        "registry": REGISTRY_PATH.as_posix(),
        "generated_surfaces": [
            README_PATH.as_posix(),
            API_DOC_PATH.as_posix(),
            PYTHON_PATH.as_posix(),
            WORKBENCH_PATH.as_posix(),
        ],
        "mismatches": mismatches,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"capability surfaces: {report['status']}")
        for mismatch in mismatches:
            print(f"- stale_or_missing:{mismatch}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
