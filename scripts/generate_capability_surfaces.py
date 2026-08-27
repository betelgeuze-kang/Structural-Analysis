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
REQUIRED_AUTHORITY_AXES = {
    "representable",
    "implemented",
    "executable",
    "public",
    "numerical_authority",
    "recovery_authority",
    "external_vv_level",
    "release_eligible",
}
RUNTIME_ARTIFACT_REQUIRED_AT = {"verification", "release"}


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
    if registry.get("schema_version") != "structural-analysis-capabilities.v2":
        raise CapabilityRegistryError("unsupported schema_version")
    rows = registry.get("capabilities")
    if not isinstance(rows, list) or not rows:
        raise CapabilityRegistryError("capabilities must be a non-empty list")
    current_state_authority = registry.get("current_state_authority")
    expected_current_state_authority = {
        "profile": "exact-current-ci-artifact.v1",
        "workflow": ".github/workflows/product-state-current.yml",
        "manifest": "artifacts/manifests/product_state.current.v1.json",
        "artifact_name_pattern": "product-state-current-{conclusion}-{source_sha}",
        "source_binding": "exact_commit_sha",
        "attestation_required": True,
        "tracked_snapshots": "historical_only",
        "tracked_self_sha_authority": False,
        "volatile_counts_allowed_in_registry": False,
    }
    if current_state_authority != expected_current_state_authority:
        raise CapabilityRegistryError("current_state_authority contract is invalid")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CapabilityRegistryError(f"capabilities[{index}] must be an object")
        capability_id = str(row.get("id", "")).strip()
        if not capability_id or capability_id in seen:
            raise CapabilityRegistryError(
                f"invalid or duplicate capability id: {capability_id}"
            )
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
        missing_axes = REQUIRED_AUTHORITY_AXES - set(row)
        if missing_axes:
            raise CapabilityRegistryError(
                f"{capability_id}: missing authority axes {sorted(missing_axes)}"
            )
        for axis in (
            "representable",
            "implemented",
            "executable",
            "public",
            "release_eligible",
        ):
            if not isinstance(row.get(axis), bool):
                raise CapabilityRegistryError(
                    f"{capability_id}: {axis} must be boolean"
                )
        if row["implemented"] and not row["representable"]:
            raise CapabilityRegistryError(
                f"{capability_id}: implemented requires representable"
            )
        if row["executable"] and not row["implemented"]:
            raise CapabilityRegistryError(
                f"{capability_id}: executable requires implemented"
            )
        if row["public"] and not row["executable"]:
            raise CapabilityRegistryError(
                f"{capability_id}: public requires executable"
            )
        for axis in ("numerical_authority", "recovery_authority"):
            if not str(row.get(axis, "")).strip():
                raise CapabilityRegistryError(
                    f"{capability_id}: {axis} must be explicit"
                )
        external_vv_level = row.get("external_vv_level")
        if (
            not isinstance(external_vv_level, int)
            or isinstance(external_vv_level, bool)
            or not 0 <= external_vv_level <= 3
        ):
            raise CapabilityRegistryError(
                f"{capability_id}: external_vv_level must be an integer from 0 to 3"
            )
        if row.get("authority") != row["numerical_authority"]:
            raise CapabilityRegistryError(
                f"{capability_id}: compatibility authority must equal numerical_authority"
            )
        interfaces = row.get("interfaces")
        limitations = row.get("limitations")
        evidence = row.get("evidence")
        runtime_artifacts = row.get("runtime_artifacts", [])
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
        if not isinstance(runtime_artifacts, list):
            raise CapabilityRegistryError(
                f"{capability_id}: runtime_artifacts must be a list"
            )
        for artifact_index, artifact in enumerate(runtime_artifacts):
            label = f"{capability_id}: runtime_artifacts[{artifact_index}]"
            if not isinstance(artifact, dict):
                raise CapabilityRegistryError(f"{label} must be an object")
            path = str(artifact.get("path", "")).strip()
            producer = str(artifact.get("producer", "")).strip()
            schema_version = str(artifact.get("schema_version", "")).strip()
            required_at = str(artifact.get("required_at", "")).strip()
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise CapabilityRegistryError(
                    f"{label} path must be repository-relative"
                )
            if not producer or not (repo_root / producer).is_file():
                raise CapabilityRegistryError(
                    f"{label} producer is missing: {producer}"
                )
            if not schema_version:
                raise CapabilityRegistryError(f"{label} schema_version is required")
            if required_at not in RUNTIME_ARTIFACT_REQUIRED_AT:
                raise CapabilityRegistryError(
                    f"{label} required_at must be verification or release"
                )
        if row.get("authority") == "none" and public:
            raise CapabilityRegistryError(
                f"{capability_id}: public capability cannot have authority none"
            )
    authority = registry.get("authority_rules")
    if not isinstance(authority, dict):
        raise CapabilityRegistryError("authority_rules must be an object")
    if authority.get("solver_truth_owner") != "structural_analysis_core":
        raise CapabilityRegistryError(
            "solver truth owner must remain structural_analysis_core"
        )
    if authority.get("workbench_truth_owner") != "none":
        raise CapabilityRegistryError("Workbench cannot own solver truth")
    if authority.get("ai_truth_owner") != "none":
        raise CapabilityRegistryError("AI control cannot own solver truth")
    if authority.get("fallback_promotion_allowed") is not False:
        raise CapabilityRegistryError("fallback promotion must remain disabled")
    if authority.get("implemented_does_not_imply_public") is not True:
        raise CapabilityRegistryError("implemented must not imply public")
    if (
        authority.get("candidate_result_authority_does_not_imply_release_eligibility")
        is not True
    ):
        raise CapabilityRegistryError(
            "candidate result authority must not imply release eligibility"
        )
    release_vv_level = authority.get("release_requires_external_vv_level")
    if not isinstance(release_vv_level, int) or release_vv_level < 1:
        raise CapabilityRegistryError(
            "release external V&V requirement must be a positive integer"
        )
    for row in rows:
        if row["release_eligible"]:
            if authority.get("release_requires_public") is True and not row["public"]:
                raise CapabilityRegistryError(
                    f"{row['id']}: release eligibility requires public"
                )
            if row["external_vv_level"] < release_vv_level:
                raise CapabilityRegistryError(
                    f"{row['id']}: release eligibility lacks external V&V"
                )


def _cell(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_table(registry: dict[str, Any]) -> str:
    lines = [
        "| Capability | Status | Representable | Implemented | Executable | Public | Numerical authority | Recovery authority | External V&V | Release eligible | Exact profile / boundary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in registry["capabilities"]:
        boundary = f"{row['profile']}; {row['limitations'][0]}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row["title"]),
                    _cell(row["status"]),
                    "yes" if row["representable"] else "no",
                    "yes" if row["implemented"] else "no",
                    "yes" if row["executable"] else "no",
                    "yes" if row["public"] else "no",
                    _cell(row["numerical_authority"]),
                    _cell(row["recovery_authority"]),
                    _cell(row["external_vv_level"]),
                    "yes" if row["release_eligible"] else "no",
                    _cell(boundary),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_current_state_authority(registry: dict[str, Any]) -> str:
    authority = registry["current_state_authority"]
    return (
        "Current status authority is the source-bound, attested exact-commit "
        f"`{authority['manifest']}` contained in the successful "
        f"`{authority['workflow']}` artifact. Checked-in capability and readiness "
        "snapshots are historical/discovery surfaces only; missing or unverifiable "
        "exact-current evidence receives no credit, and volatile coverage counts are "
        "not copied into this registry."
    )


def render_readme_block(registry: dict[str, Any]) -> str:
    return (
        f"{BEGIN_MARKER}\n"
        "## Generated capability support matrix\n\n"
        "This table is generated from the v2 registry at "
        "`artifacts/manifests/capabilities.yaml`. Do not edit it directly. "
        "`implemented` and `executable` do not mean `public`; numerical, "
        "recovery, external-V&V, and release authority remain independent.\n\n"
        f"{render_current_state_authority(registry)}\n\n"
        f"{render_table(registry)}\n"
        f"{END_MARKER}"
    )


def replace_marked_block(text: str, block: str) -> str:
    if BEGIN_MARKER not in text and END_MARKER not in text:
        return text.rstrip() + "\n\n" + block + "\n"
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise CapabilityRegistryError(
            "README capability markers must occur exactly once"
        )
    before, remainder = text.split(BEGIN_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    return before.rstrip() + "\n\n" + block + after.rstrip() + "\n"


def render_api_doc(registry: dict[str, Any]) -> str:
    return (
        "# API Capability Support\n\n"
        "Generated from the v2 registry at artifacts/manifests/capabilities.yaml. "
        "Do not edit directly. Implemented or executable candidate rows are not "
        "public or release-eligible unless those independent axes say so.\n\n"
        + render_current_state_authority(registry)
        + "\n\n"
        + render_table(registry)
        + "\n\n"
        "The Python API exposes the same registry through "
        "structural_analysis.api.capabilities(). The structural-analysis CLI "
        "prints it with --capabilities. Experimental, shadow-only, and blocked "
        "rows are discovery metadata, not executable public support. Workbench "
        "consumes the same generated rows and owns no solver truth.\n"
    )


def render_python(registry: dict[str, Any]) -> str:
    rows = tuple(registry["capabilities"])
    return (
        '"""Generated capability registry. Do not edit directly."""\n\n'
        "from __future__ import annotations\n\n"
        "from copy import deepcopy\n"
        "from typing import Any\n\n"
        f"CAPABILITY_SCHEMA_VERSION = {registry['schema_version']!r}\n"
        "CURRENT_STATE_AUTHORITY: dict[str, Any] = "
        + pprint.pformat(
            registry["current_state_authority"], width=100, sort_dicts=True
        )
        + "\n"
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
        "    return tuple(deepcopy(row) for row in rows)\n"
    )


def render_workbench_json(registry: dict[str, Any]) -> str:
    payload = {
        "schemaVersion": registry["schema_version"],
        "currentStateAuthority": registry["current_state_authority"],
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
        "schema_version": "capability-surface-generation-check.v2",
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
