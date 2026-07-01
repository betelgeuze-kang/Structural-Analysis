#!/usr/bin/env python3
"""Audit tracked files for non-structural product-domain contamination."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_contamination_audit.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_QUARANTINE_MANIFEST = PRODUCTIZATION / "structural_scope_quarantine_manifest.json"
QUARANTINE_SCHEMA_VERSION = "structural-scope-quarantine-manifest.v1"

RULES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "md3bead_molecular_dynamics",
        "family": "molecular_dynamics",
        "tokens": ("md3bead", "all_atom"),
    },
    {
        "rule_id": "pocketmd_product_surface",
        "family": "molecular_dynamics",
        "tokens": ("pocketmd",),
    },
    {
        "rule_id": "gpcr_ligand_benchmark",
        "family": "molecular_docking",
        "tokens": ("gpcr", "ligand", "vina", "gnina"),
    },
    {
        "rule_id": "molecular_public_benchmark",
        "family": "molecular_docking",
        "tokens": (
            "casf_pdbbind",
            "pdbbind",
            "dud_e",
            "lit_pcba",
            "posebusters",
            "symmetry_rmsd",
            "symmetry_aware_ligand",
            "public_benchmark_enrichment",
            "public_benchmark_pose",
            "public_benchmark_subset",
            "public_benchmark_vina_gnina",
        ),
    },
    {
        "rule_id": "molecular_science_closure",
        "family": "molecular_science_evidence",
        "tokens": ("science_actual", "h_bond", "free_energy", "delta_g", "fep"),
    },
    {
        "rule_id": "molecular_platform_claim",
        "family": "molecular_platform",
        "tokens": ("molecular", "alphafold"),
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _git_paths(repo_root: Path, args: list[str]) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", *args],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _git_ls_files(repo_root: Path) -> list[str]:
    return _git_paths(repo_root, ["ls-files"])


def _git_untracked_files(repo_root: Path) -> list[str]:
    return _git_paths(repo_root, ["ls-files", "--others", "--exclude-standard"])


def _matched_rules(path: str) -> list[dict[str, Any]]:
    lowered = path.lower().replace("\\", "/")
    matches: list[dict[str, Any]] = []
    for rule in RULES:
        tokens = tuple(str(token) for token in rule["tokens"])
        matched_tokens = [token for token in tokens if token in lowered]
        if matched_tokens:
            matches.append(
                {
                    "rule_id": str(rule["rule_id"]),
                    "family": str(rule["family"]),
                    "matched_tokens": matched_tokens,
                }
            )
    return matches


def _path_area(path: str) -> str:
    if path.startswith("implementation/phase1/release_evidence/productization/"):
        return "productization_evidence"
    if path.startswith("implementation/phase1/release_evidence/surface/"):
        return "release_surface"
    if path.startswith("implementation/phase1/"):
        return "implementation_phase1"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("tests/"):
        return "test"
    if path.startswith("docs/") or path == "README.md":
        return "documentation"
    return "other"


def _row(path: str, matches: list[dict[str, Any]], *, git_state: str) -> dict[str, Any]:
    families = sorted({str(match["family"]) for match in matches})
    return {
        "path": path,
        "git_state": git_state,
        "path_area": _path_area(path),
        "families": families,
        "rule_ids": [str(match["rule_id"]) for match in matches],
        "matched_tokens": sorted(
            {
                str(token)
                for match in matches
                for token in match.get("matched_tokens", [])
            }
        ),
    }


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _matched_rows(*, repo_root: Path, include_untracked: bool) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    tracked_paths = _git_ls_files(repo_root)
    untracked_paths = _git_untracked_files(repo_root) if include_untracked else []
    rows = [
        _row(path, matches, git_state="tracked")
        for path in tracked_paths
        if (matches := _matched_rules(path))
    ]
    rows.extend(
        _row(path, matches, git_state="untracked")
        for path in untracked_paths
        if (matches := _matched_rules(path))
    )
    return tracked_paths, untracked_paths, rows


def _load_quarantine_manifest(
    *,
    repo_root: Path,
    quarantine_manifest: Path,
) -> tuple[dict[str, Any], set[str], list[str]]:
    resolved = _resolve(repo_root, quarantine_manifest)
    summary: dict[str, Any] = {
        "path": quarantine_manifest.as_posix(),
        "present": resolved.exists(),
        "schema_version": "",
        "active": False,
        "quarantined_path_count": 0,
    }
    if not resolved.exists():
        return summary, set(), []
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return summary, set(), [f"quarantine_manifest_invalid_json:{exc.__class__.__name__}"]
    if not isinstance(payload, dict):
        return summary, set(), ["quarantine_manifest_not_json_object"]
    schema_version = str(payload.get("schema_version", ""))
    active = payload.get("status") == "active"
    summary["schema_version"] = schema_version
    summary["active"] = active
    blockers: list[str] = []
    if schema_version != QUARANTINE_SCHEMA_VERSION:
        blockers.append("quarantine_manifest_schema_version_mismatch")
    if not active:
        blockers.append("quarantine_manifest_not_active")
    raw_rows = payload.get("paths", [])
    if not isinstance(raw_rows, list):
        return summary, set(), [*blockers, "quarantine_manifest_paths_not_list"]
    quarantined_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            blockers.append(f"quarantine_manifest_row_not_object:{index}")
            continue
        path = str(row.get("path", "")).strip()
        if not path:
            blockers.append(f"quarantine_manifest_row_path_missing:{index}")
            continue
        if path in quarantined_paths:
            duplicate_paths.add(path)
        if row.get("excluded_from_structural_release_surface") is not True:
            blockers.append(f"quarantine_manifest_row_not_release_excluded:{path}")
            continue
        quarantined_paths.add(path)
    if duplicate_paths:
        blockers.append(f"quarantine_manifest_duplicate_paths={len(duplicate_paths)}")
    summary["quarantined_path_count"] = len(quarantined_paths)
    return summary, quarantined_paths, blockers


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row[key])
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for family in row["families"]:
            counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _scope_blockers(rows: list[dict[str, Any]], *, prefix: str = "unquarantined") -> list[str]:
    blockers: list[str] = []
    if not rows:
        return blockers
    blockers.append(f"{prefix}_non_structural_path_count={len(rows)}")
    git_state_counts = _counts_by_key(rows, "git_state")
    tracked_count = git_state_counts.get("tracked", 0)
    untracked_count = git_state_counts.get("untracked", 0)
    if tracked_count:
        blockers.append(f"{prefix}_non_structural_git_tracked_path_count={tracked_count}")
    if untracked_count:
        blockers.append(f"{prefix}_non_structural_git_untracked_path_count={untracked_count}")
    area_counts = _counts_by_key(rows, "path_area")
    release_surface_count = area_counts.get("productization_evidence", 0) + area_counts.get(
        "release_surface", 0
    )
    if release_surface_count:
        blockers.append(
            f"{prefix}_non_structural_release_evidence_path_count={release_surface_count}"
        )
    if area_counts.get("script", 0):
        blockers.append(f"{prefix}_non_structural_script_path_count={area_counts['script']}")
    if area_counts.get("test", 0):
        blockers.append(f"{prefix}_non_structural_test_path_count={area_counts['test']}")
    return blockers


def build_audit(
    *,
    repo_root: Path = ROOT,
    include_untracked: bool = True,
    quarantine_manifest: Path = DEFAULT_QUARANTINE_MANIFEST,
) -> dict[str, Any]:
    tracked_paths, untracked_paths, rows = _matched_rows(
        repo_root=repo_root,
        include_untracked=include_untracked,
    )
    quarantine_summary, quarantined_paths, manifest_blockers = _load_quarantine_manifest(
        repo_root=repo_root,
        quarantine_manifest=quarantine_manifest,
    )
    for row in rows:
        quarantined = row["path"] in quarantined_paths
        row["quarantine_status"] = "quarantined" if quarantined else "unquarantined"
        row["excluded_from_structural_release_surface"] = quarantined
    quarantined_rows = [row for row in rows if row["quarantine_status"] == "quarantined"]
    unquarantined_rows = [
        row for row in rows if row["quarantine_status"] == "unquarantined"
    ]

    area_counts = _counts_by_key(rows, "path_area")
    family_counts = _family_counts(rows)
    git_state_counts = _counts_by_key(rows, "git_state")
    unquarantined_area_counts = _counts_by_key(unquarantined_rows, "path_area")
    unquarantined_family_counts = _family_counts(unquarantined_rows)
    unquarantined_git_state_counts = _counts_by_key(unquarantined_rows, "git_state")
    quarantined_area_counts = _counts_by_key(quarantined_rows, "path_area")
    quarantined_family_counts = _family_counts(quarantined_rows)

    blockers = [f"quarantine_manifest::{item}" for item in manifest_blockers]
    tracked_non_structural_count = git_state_counts.get("tracked", 0)
    untracked_non_structural_count = git_state_counts.get("untracked", 0)
    blockers.extend(_scope_blockers(unquarantined_rows))

    contract_pass = not blockers and not unquarantined_rows
    if not rows:
        status = "pass"
    elif contract_pass:
        status = "quarantined"
    else:
        status = "blocked"

    return {
        "schema_version": "structural-scope-contamination-audit.v1",
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/check_structural_scope_contamination.py"),
                quarantine_manifest,
            ],
            reused_evidence=False,
            reuse_policy=(
                "structural_scope_contamination_audit_from_tracked_paths"
                "_with_release_surface_quarantine_manifest"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "tracked_path_count": len(tracked_paths),
        "untracked_path_count": len(untracked_paths),
        "non_structural_path_count": len(rows),
        "non_structural_tracked_path_count": tracked_non_structural_count,
        "non_structural_untracked_path_count": untracked_non_structural_count,
        "quarantined_non_structural_path_count": len(quarantined_rows),
        "unquarantined_non_structural_path_count": len(unquarantined_rows),
        "unquarantined_non_structural_tracked_path_count": unquarantined_git_state_counts.get(
            "tracked",
            0,
        ),
        "unquarantined_non_structural_untracked_path_count": unquarantined_git_state_counts.get(
            "untracked",
            0,
        ),
        "path_area_counts": area_counts,
        "family_counts": family_counts,
        "git_state_counts": git_state_counts,
        "quarantined_path_area_counts": quarantined_area_counts,
        "quarantined_family_counts": quarantined_family_counts,
        "unquarantined_path_area_counts": unquarantined_area_counts,
        "unquarantined_family_counts": unquarantined_family_counts,
        "unquarantined_git_state_counts": unquarantined_git_state_counts,
        "quarantine_manifest": quarantine_summary,
        "blockers": blockers,
        "first_non_structural_path": rows[0]["path"] if rows else "",
        "first_unquarantined_non_structural_path": (
            unquarantined_rows[0]["path"] if unquarantined_rows else ""
        ),
        "non_structural_rows": rows,
        "quarantined_non_structural_rows": quarantined_rows,
        "unquarantined_non_structural_rows": unquarantined_rows,
        "next_actions": (
            [
                "quarantine_or_delete_unquarantined_non_structural_paths_after_owner_review",
                "regenerate_release_freshness_pm_snapshot_after_scope_cleanup",
            ]
            if unquarantined_rows
            else (
                [
                    "keep_quarantine_manifest_exact_until_non_structural_paths_are_deleted_or_extracted",
                    "owner_review_quarantined_paths_for_delete_or_repository_extract_decision",
                ]
                if rows
                else []
            )
        ),
        "claim_boundary": (
            "This audit protects the building structural-analysis product scope. "
            "It does not delete files; it identifies molecular, ligand, GPCR, "
            "PocketMD, and MD paths and requires either deletion/extraction or an "
            "exact quarantine manifest that excludes them from the structural "
            "release surface. Quarantined paths remain visible and must not be "
            "counted as structural solver release evidence."
        ),
    }


def build_quarantine_manifest(
    *,
    repo_root: Path = ROOT,
    include_untracked: bool = False,
) -> dict[str, Any]:
    _, _, rows = _matched_rows(repo_root=repo_root, include_untracked=include_untracked)
    return {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[Path("scripts/check_structural_scope_contamination.py")],
            reused_evidence=False,
            reuse_policy="structural_scope_quarantine_manifest_from_owner_requested_scope_cleanup",
            repo_root=repo_root,
        ),
        "status": "active",
        "quarantine_policy": (
            "Non-structural molecular/PocketMD/GPCR/MD paths are retained only as "
            "quarantined legacy artifacts pending owner delete/extract review. They "
            "are explicitly excluded from the building structural-analysis release "
            "surface and must not support structural solver readiness claims."
        ),
        "owner_review_status": "owner_requested_release_surface_quarantine",
        "path_count": len(rows),
        "paths": [
            {
                "path": row["path"],
                "git_state": row["git_state"],
                "path_area": row["path_area"],
                "families": row["families"],
                "matched_tokens": row["matched_tokens"],
                "excluded_from_structural_release_surface": True,
                "quarantine_reason": "non_structural_product_domain",
                "owner_action_required": "delete_or_extract_from_structural_repository_after_review",
            }
            for row in rows
        ],
    }


def write_quarantine_manifest(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_QUARANTINE_MANIFEST,
    include_untracked: bool = False,
) -> dict[str, Any]:
    payload = build_quarantine_manifest(
        repo_root=repo_root,
        include_untracked=include_untracked,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Contamination Audit",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `non_structural_path_count`: `{payload['non_structural_path_count']}`",
        f"- `non_structural_tracked_path_count`: `{payload['non_structural_tracked_path_count']}`",
        f"- `non_structural_untracked_path_count`: `{payload['non_structural_untracked_path_count']}`",
        f"- `quarantined_non_structural_path_count`: `{payload['quarantined_non_structural_path_count']}`",
        f"- `unquarantined_non_structural_path_count`: `{payload['unquarantined_non_structural_path_count']}`",
        f"- `first_non_structural_path`: `{payload['first_non_structural_path'] or 'none'}`",
        f"- `first_unquarantined_non_structural_path`: `{payload['first_unquarantined_non_structural_path'] or 'none'}`",
        "",
        "## Quarantine",
        "",
        f"- `manifest_present`: `{payload['quarantine_manifest']['present']}`",
        f"- `manifest_path`: `{payload['quarantine_manifest']['path']}`",
        f"- `manifest_quarantined_path_count`: `{payload['quarantine_manifest']['quarantined_path_count']}`",
        "",
        "| Git State | Count |",
        "|---|---:|",
    ]
    for state, count in payload["git_state_counts"].items():
        lines.append(f"| `{state}` | {count} |")
    lines.extend(
        [
            "",
        "| Area | Count |",
        "|---|---:|",
        ]
    )
    for area, count in payload["path_area_counts"].items():
        lines.append(f"| `{area}` | {count} |")
    lines.extend(["", "| Family | Count |", "|---|---:|"])
    for family, count in payload["family_counts"].items():
        lines.append(f"| `{family}` | {count} |")
    lines.extend(
        [
            "",
            "| Path | Git State | Area | Quarantine | Families | Tokens |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in payload["non_structural_rows"]:
        lines.append(
            "| "
            f"`{row['path']}` | "
            f"`{row['git_state']}` | "
            f"`{row['path_area']}` | "
            f"`{row['quarantine_status']}` | "
            f"`{', '.join(row['families'])}` | "
            f"`{', '.join(row['matched_tokens'])}` |"
        )
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_audit(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    include_untracked: bool = True,
    quarantine_manifest: Path = DEFAULT_QUARANTINE_MANIFEST,
) -> dict[str, Any]:
    payload = build_audit(
        repo_root=repo_root,
        include_untracked=include_untracked,
        quarantine_manifest=quarantine_manifest,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--quarantine-manifest", type=Path, default=DEFAULT_QUARANTINE_MANIFEST)
    parser.add_argument(
        "--refresh-quarantine-manifest",
        action="store_true",
        help="Refresh the quarantine manifest from the current matched tracked paths before auditing.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="Only scan tracked files; by default ignored-excluded untracked files are scanned too.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.refresh_quarantine_manifest:
        write_quarantine_manifest(
            repo_root=args.repo_root,
            out=args.quarantine_manifest,
            include_untracked=not args.tracked_only,
        )
    payload = write_audit(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        include_untracked=not args.tracked_only,
        quarantine_manifest=args.quarantine_manifest,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Structural scope contamination audit: "
            f"{payload['status']} | "
            f"non_structural_paths={payload['non_structural_path_count']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
