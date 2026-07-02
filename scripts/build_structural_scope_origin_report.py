#!/usr/bin/env python3
"""Build origin evidence for quarantined non-structural scope paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-scope-origin-report.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OWNER_REVIEW = PRODUCTIZATION / "structural_scope_owner_review_packet.json"
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_origin_report.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
COMMIT_FIELD_SEP = "\x1f"


CommitLookup = Callable[[Path, str], dict[str, str]]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _text(row.get(key)) or "unknown"
        _increment(counts, value)
    return dict(sorted(counts.items()))


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        families = [str(item) for item in _as_list(row.get("families")) if str(item)]
        if not families:
            families = ["unknown"]
        for family in families:
            _increment(counts, family)
    return dict(sorted(counts.items()))


def _first_added_commit(repo_root: Path, path: str) -> dict[str, str]:
    try:
        output = subprocess.check_output(
            [
                "git",
                "log",
                "--diff-filter=A",
                f"--format=%H{COMMIT_FIELD_SEP}%cs{COMMIT_FIELD_SEP}%s",
                "--",
                path,
            ],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {"commit_sha": "", "commit_date": "", "commit_subject": ""}
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return {"commit_sha": "", "commit_date": "", "commit_subject": ""}
    commit_sha, commit_date, commit_subject = (lines[-1].split(COMMIT_FIELD_SEP, 2) + ["", ""])[:3]
    return {
        "commit_sha": commit_sha,
        "commit_short_sha": commit_sha[:8],
        "commit_date": commit_date,
        "commit_subject": commit_subject,
    }


def _origin_wave(origin: dict[str, str], row: dict[str, Any]) -> str:
    subject = origin.get("commit_subject", "")
    subject_lower = subject.lower()
    date = origin.get("commit_date", "")
    tokens = {str(item).lower() for item in _as_list(row.get("matched_tokens"))}
    if "Import structural analysis workbench implementation" in subject:
        return "initial_bulk_import_with_md3bead_runtime"
    if "Add locked H-Bond and GPCR evidence surfaces" in subject:
        return "science_release_surface_seed"
    if "Materialize PocketMD Lite product surface" in subject:
        return "pocketmd_release_surface_materialization"
    if "gpcr" in subject_lower or "gpcr" in tokens:
        return "gpcr_productization_evidence_wave"
    if "pocketmd" in subject_lower or "pocketmd" in tokens:
        return "pocketmd_productization_evidence_wave"
    if "public benchmark" in subject_lower or tokens.intersection(
        {
            "public_benchmark_enrichment",
            "public_benchmark_pose",
            "public_benchmark_subset",
            "public_benchmark_vina_gnina",
            "casf_pdbbind",
            "pdbbind",
            "dud_e",
            "lit_pcba",
            "posebusters",
            "symmetry_aware_ligand",
            "ligand_rmsd",
            "vina",
            "gnina",
        }
    ):
        return "molecular_public_benchmark_wave"
    if "h-bond" in subject_lower or "h_bond" in tokens:
        return "h_bond_backmap_science_wave"
    if "science actual" in subject_lower or "science closure" in subject_lower:
        return "science_actual_closure_wave"
    if "md3bead" in tokens:
        return "md3bead_legacy_runtime_surface"
    if date:
        return f"other_non_structural_scope_introduction:{date}"
    return "origin_commit_missing"


def _origin_row(
    *,
    repo_root: Path,
    row: dict[str, Any],
    commit_lookup: CommitLookup,
) -> dict[str, Any]:
    path = _text(row.get("path"))
    origin = commit_lookup(repo_root, path)
    return {
        "path": path,
        "path_area": _text(row.get("path_area")),
        "families": [str(item) for item in _as_list(row.get("families"))],
        "matched_tokens": [str(item) for item in _as_list(row.get("matched_tokens"))],
        "owner_review_state": _text(row.get("owner_review_state")),
        "recommended_owner_decision_primary": _text(
            row.get("recommended_owner_decision_primary")
        ),
        "recommended_owner_decision_alternate": _text(
            row.get("recommended_owner_decision_alternate")
        ),
        "structural_release_claim_eligible": bool(
            row.get("structural_release_claim_eligible")
        ),
        "first_added_commit_sha": _text(origin.get("commit_sha")),
        "first_added_commit_short_sha": _text(origin.get("commit_short_sha")),
        "first_added_commit_date": _text(origin.get("commit_date")),
        "first_added_commit_subject": _text(origin.get("commit_subject")),
        "origin_wave": _origin_wave(origin, row),
    }


def _wave_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            _text(row.get("origin_wave")),
            _text(row.get("first_added_commit_date")),
            _text(row.get("first_added_commit_short_sha")),
            _text(row.get("first_added_commit_subject")),
        )
        group = grouped.setdefault(
            key,
            {
                "origin_wave": key[0],
                "first_added_commit_date": key[1],
                "first_added_commit_short_sha": key[2],
                "first_added_commit_subject": key[3],
                "path_count": 0,
                "paths": [],
                "path_area_counts": {},
                "family_counts": {},
            },
        )
        group["path_count"] += 1
        group["paths"].append(row["path"])
        _increment(group["path_area_counts"], row["path_area"] or "unknown")
        for family in _as_list(row.get("families")) or ["unknown"]:
            _increment(group["family_counts"], str(family))
    return [
        {
            **group,
            "paths": sorted(group["paths"]),
            "path_area_counts": dict(sorted(group["path_area_counts"].items())),
            "family_counts": dict(sorted(group["family_counts"].items())),
        }
        for group in sorted(
            grouped.values(),
            key=lambda item: (
                item["first_added_commit_date"] or "9999-99-99",
                item["origin_wave"],
                item["first_added_commit_short_sha"],
            ),
        )
    ]


def build_origin_report(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OWNER_REVIEW,
    commit_lookup: CommitLookup = _first_added_commit,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    owner_review = _load_json(repo_root, owner_review_packet_path)
    review_rows = [
        row for row in _as_list(owner_review.get("review_rows")) if isinstance(row, dict)
    ]
    origin_rows = [
        _origin_row(repo_root=repo_root, row=row, commit_lookup=commit_lookup)
        for row in review_rows
    ]
    missing_origin_rows = [
        row for row in origin_rows if not row["first_added_commit_sha"]
    ]
    release_surface_rows = [
        row for row in origin_rows if row["path_area"] == "release_surface"
    ]
    wave_rows = _wave_rows(origin_rows)
    blockers: list[str] = []
    if not owner_review:
        blockers.append("structural_scope_owner_review_packet_missing")
    if owner_review and not owner_review.get("contract_pass"):
        blockers.append("structural_scope_owner_review_packet_not_contract_pass")
    if missing_origin_rows:
        blockers.append(f"origin_commit_missing_count={len(missing_origin_rows)}")
    status = (
        "blocked_origin_report"
        if blockers
        else "ready_for_owner_review_origin_evidence"
        if origin_rows
        else "complete_no_non_structural_paths"
    )
    root_cause_summary = (
        "Quarantined non-structural paths entered this structural-analysis "
        "repository through tracked molecular runtime and science productization "
        "waves, then were later excluded from structural release claims by the "
        "scope quarantine manifest."
        if origin_rows
        else "No quarantined non-structural paths are present in the owner review packet."
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_structural_scope_origin_report.py"),
                owner_review_packet_path,
            ],
            reused_evidence=False,
            reuse_policy="structural_scope_origin_report_from_owner_review_and_git_history",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": not blockers,
        "origin_evidence_complete": not missing_origin_rows,
        "summary_line": (
            "Structural scope origin report: "
            f"{status.upper()} | paths={len(origin_rows)} | "
            f"waves={len(wave_rows)} | release_surface={len(release_surface_rows)} | "
            f"missing_origin={len(missing_origin_rows)}"
        ),
        "owner_review_packet": owner_review_packet_path.as_posix(),
        "owner_review_status": _text(owner_review.get("status")),
        "owner_decision_pending_count": int(
            owner_review.get("owner_decision_pending_count", 0) or 0
        ),
        "quarantined_path_count": len(origin_rows),
        "origin_wave_count": len(wave_rows),
        "release_surface_origin_path_count": len(release_surface_rows),
        "release_surface_origin_paths": [row["path"] for row in release_surface_rows],
        "missing_origin_count": len(missing_origin_rows),
        "missing_origin_paths": [row["path"] for row in missing_origin_rows],
        "path_area_counts": _counts_by_key(origin_rows, "path_area"),
        "family_counts": _family_counts(origin_rows),
        "origin_wave_counts": _counts_by_key(origin_rows, "origin_wave"),
        "root_cause_summary": root_cause_summary,
        "release_surface_first_owner_action": (
            "record delete_from_structural_repository or "
            "extract_to_molecular_or_science_repository decisions for the "
            "release-surface-first rows before manual cleanup"
        ),
        "origin_waves": wave_rows,
        "origin_rows": origin_rows,
        "release_surface_origin_rows": release_surface_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This report explains how quarantined non-structural paths entered "
            "the repository. It does not approve retention, delete files, close "
            "owner review, or make any PocketMD/GPCR/MD3Bead artifact eligible "
            "for building structural-analysis release claims."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Origin Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `origin_evidence_complete`: `{payload['origin_evidence_complete']}`",
        f"- `quarantined_path_count`: `{payload['quarantined_path_count']}`",
        f"- `origin_wave_count`: `{payload['origin_wave_count']}`",
        f"- `release_surface_origin_path_count`: `{payload['release_surface_origin_path_count']}`",
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        "",
        "## Root Cause",
        "",
        str(payload["root_cause_summary"]),
        "",
        "## Origin Waves",
        "",
        "| Wave | Date | Commit | Paths | Areas | Families | Subject |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in payload["origin_waves"]:
        lines.append(
            "| "
            f"`{row['origin_wave']}` | "
            f"`{row['first_added_commit_date']}` | "
            f"`{row['first_added_commit_short_sha']}` | "
            f"{row['path_count']} | "
            f"`{row['path_area_counts']}` | "
            f"`{row['family_counts']}` | "
            f"`{row['first_added_commit_subject']}` |"
        )
    lines.extend(
        [
            "",
            "## Release Surface First",
            "",
            "| Path | Origin Wave | First Added | Recommended Primary Decision |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["release_surface_origin_rows"]:
        lines.append(
            "| "
            f"`{row['path']}` | "
            f"`{row['origin_wave']}` | "
            f"`{row['first_added_commit_short_sha']} {row['first_added_commit_date']}` | "
            f"`{row['recommended_owner_decision_primary']}` |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_origin_report(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OWNER_REVIEW,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_origin_report(
        repo_root=repo_root,
        owner_review_packet_path=owner_review_packet_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--owner-review-packet", type=Path, default=DEFAULT_OWNER_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_origin_report(
        repo_root=args.repo_root,
        owner_review_packet_path=args.owner_review_packet,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
