#!/usr/bin/env python3
"""Build a non-mutating impact report for structural scope cleanup."""

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


SCHEMA_VERSION = "structural-scope-cleanup-impact-report.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OWNER_REVIEW = PRODUCTIZATION / "structural_scope_owner_review_packet.json"
DEFAULT_ORIGIN_REPORT = PRODUCTIZATION / "structural_scope_origin_report.json"
DEFAULT_OUT = PRODUCTIZATION / "structural_scope_cleanup_impact_report.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
MAX_TEXT_BYTES = 4 * 1024 * 1024
SIGNAL_TOKENS = {
    "casf_pdbbind",
    "delta_g",
    "dud_e",
    "fep",
    "free_energy",
    "gnina",
    "gpcr",
    "h_bond",
    "ligand_rmsd",
    "lit_pcba",
    "md3bead",
    "pdbbind",
    "pocketmd",
    "posebusters",
    "public_benchmark",
    "science_actual",
    "symmetry_aware_ligand",
    "vina",
}
RAW_SCOPE_TOKENS = SIGNAL_TOKENS - {
    # Keep Vina-bearing path terms such as public_benchmark_vina_gnina, but do
    # not treat every incidental "vina" byte sequence in structural text/binary
    # artifacts as a molecular reference.
    "vina",
}
SCOPE_GOVERNANCE_FILES = {
    "scripts/build_structural_scope_cleanup_impact_report.py",
    "scripts/build_structural_scope_origin_report.py",
    "scripts/build_structural_scope_owner_decision_application_plan.py",
    "scripts/build_structural_scope_owner_review_packet.py",
    "scripts/check_structural_scope_contamination.py",
    "tests/test_build_structural_scope_cleanup_impact_report.py",
    "tests/test_build_structural_scope_origin_report.py",
    "tests/test_build_structural_scope_owner_decision_application_plan.py",
    "tests/test_build_structural_scope_owner_review_packet.py",
    "tests/test_check_structural_scope_contamination.py",
}
RELEASE_GOVERNANCE_FILES = {
    "docs/commercialization-gap-current-state.md",
    "docs/pm-release-gate-milestones.md",
    "implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json",
    "implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.md",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.md",
    "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
    "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json",
    "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.md",
    "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
}
REFERENCE_ROLE_PRIORITY = {
    "productization_evidence_reference": 1,
    "implementation_runtime_or_manifest_reference": 2,
    "script_reference": 3,
    "test_reference": 4,
    "documentation_reference": 5,
    "other_reference": 6,
}
REFERENCE_ROLE_CLEANUP_ACTION = {
    "documentation_reference": "rewrite_structural_docs_to_scope_boundary_only",
    "implementation_runtime_or_manifest_reference": (
        "remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts"
    ),
    "other_reference": "remove_non_structural_scope_ignore_or_metadata_reference",
    "productization_evidence_reference": (
        "regenerate_release_evidence_without_molecular_scope_references"
    ),
    "script_reference": "delete_or_extract_molecular_script_or_remove_quarantined_path_refs",
    "test_reference": "delete_or_extract_molecular_tests_or_update_scope_guard_tests",
}
NON_TEXT_SUFFIXES = {
    ".bin",
    ".deb",
    ".gif",
    ".gz",
    ".jpeg",
    ".jpg",
    ".npz",
    ".pdf",
    ".png",
    ".pyc",
    ".rlib",
    ".so",
    ".zip",
}


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


def _git_ls_files(repo_root: Path) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [
        item.decode("utf-8", errors="replace")
        for item in output.split(b"\0")
        if item
    ]


def _candidate_tokens_for_row(row: dict[str, Any]) -> set[str]:
    path = _text(row.get("path"))
    path_obj = Path(path)
    values = {path, path_obj.name}
    parts = [part for part in path_obj.parts if part not in {".", ""}]
    values.update(
        part
        for part in parts
        if any(token in part.lower() for token in SIGNAL_TOKENS)
    )
    stem = path_obj.stem
    if any(token in stem.lower() for token in SIGNAL_TOKENS):
        values.add(stem)
    return {value for value in values if value}


def _reference_index(review_rows: list[dict[str, Any]]) -> tuple[dict[str, set[str]], set[str]]:
    path_by_term: dict[str, set[str]] = {}
    scope_tokens: set[str] = set()
    for row in review_rows:
        path = _text(row.get("path"))
        if not path:
            continue
        for term in _candidate_tokens_for_row(row):
            path_by_term.setdefault(term, set()).add(path)
        for token in _as_list(row.get("matched_tokens")):
            normalized = str(token).lower()
            if normalized in RAW_SCOPE_TOKENS:
                scope_tokens.add(normalized)
    return path_by_term, scope_tokens


def _is_text_candidate(path: str) -> bool:
    return Path(path).suffix.lower() not in NON_TEXT_SUFFIXES


def _read_text(repo_root: Path, path: str) -> str:
    resolved = repo_root / path
    try:
        if resolved.stat().st_size > MAX_TEXT_BYTES:
            return ""
        return resolved.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _reference_role(path: str) -> str:
    if path in SCOPE_GOVERNANCE_FILES or path.startswith(
        "implementation/phase1/release_evidence/productization/structural_scope_"
    ):
        return "scope_governance_reference"
    if path in RELEASE_GOVERNANCE_FILES:
        return "release_governance_reference"
    if path.startswith("implementation/phase1/release_evidence/productization/"):
        return "productization_evidence_reference"
    if path.startswith("implementation/phase1/release_evidence/surface/"):
        return "release_surface_reference"
    if path.startswith("implementation/phase1/"):
        return "implementation_runtime_or_manifest_reference"
    if path.startswith("scripts/"):
        return "script_reference"
    if path.startswith("tests/"):
        return "test_reference"
    if path.startswith("docs/") or path == "README.md":
        return "documentation_reference"
    return "other_reference"


def _blocking_reference_role(role: str) -> bool:
    return role not in {
        "scope_governance_reference",
        "release_governance_reference",
    }


def _reference_role_priority(role: str) -> int:
    return REFERENCE_ROLE_PRIORITY.get(role, 99)


def _cleanup_action_for_role(role: str) -> str:
    return REFERENCE_ROLE_CLEANUP_ACTION.get(
        role,
        "review_reference_before_owner_cleanup_application",
    )


def _owner_decision_dependency(row: dict[str, Any]) -> str:
    if int(row.get("matched_quarantined_path_count", 0) or 0) > 0:
        return "owner_delete_extract_decision_then_reference_cleanup"
    if row.get("matched_scope_tokens"):
        return "scope_token_review_before_cleanup"
    return "none"


def _scan_references(
    *,
    repo_root: Path,
    review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quarantined_paths = {_text(row.get("path")) for row in review_rows}
    path_by_term, scope_tokens = _reference_index(review_rows)
    rows: list[dict[str, Any]] = []
    for path in _git_ls_files(repo_root):
        if path in quarantined_paths or not _is_text_candidate(path):
            continue
        text = _read_text(repo_root, path)
        if not text:
            continue
        lowered = text.lower()
        matched_terms = sorted(term for term in path_by_term if term and term in text)
        matched_paths = sorted(
            {
                matched_path
                for term in matched_terms
                for matched_path in path_by_term.get(term, set())
            }
        )
        matched_scope_tokens = sorted(
            token for token in scope_tokens if token and token in lowered
        )
        if not matched_terms and not matched_scope_tokens:
            continue
        role = _reference_role(path)
        rows.append(
            {
                "path": path,
                "reference_role": role,
                "blocking_cleanup_reference": _blocking_reference_role(role),
                "reference_role_priority": _reference_role_priority(role),
                "recommended_cleanup_action": _cleanup_action_for_role(role),
                "matched_term_count": len(matched_terms),
                "matched_terms": matched_terms[:50],
                "matched_scope_tokens": matched_scope_tokens,
                "matched_quarantined_path_count": len(matched_paths),
                "matched_quarantined_paths": matched_paths[:50],
            }
        )
        rows[-1]["owner_decision_dependency"] = _owner_decision_dependency(rows[-1])
    return rows


def _cleanup_reference_priority_batches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        role = _text(row.get("reference_role")) or "other_reference"
        action = _text(row.get("recommended_cleanup_action"))
        batch_id = f"cleanup_refs_{_reference_role_priority(role):02d}_{role}"
        group = groups.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "priority": _reference_role_priority(role),
                "reference_role": role,
                "recommended_cleanup_action": action,
                "path_count": 0,
                "paths": [],
                "matched_scope_tokens": set(),
                "matched_quarantined_path_count": 0,
                "owner_decision_dependency_counts": {},
                "post_cleanup_verification": [
                    "python3 scripts/build_structural_scope_cleanup_impact_report.py --fail-blocked",
                    "python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked",
                    "python3 scripts/build_product_readiness_snapshot.py --check",
                ],
            },
        )
        group["path_count"] += 1
        group["paths"].append(row["path"])
        group["matched_quarantined_path_count"] += int(
            row.get("matched_quarantined_path_count", 0) or 0
        )
        for token in _as_list(row.get("matched_scope_tokens")):
            group["matched_scope_tokens"].add(str(token))
        _increment(
            group["owner_decision_dependency_counts"],
            _text(row.get("owner_decision_dependency")) or "none",
        )
    batches: list[dict[str, Any]] = []
    for batch in sorted(groups.values(), key=lambda item: (item["priority"], item["reference_role"])):
        batches.append(
            {
                **batch,
                "paths": sorted(batch["paths"]),
                "matched_scope_tokens": sorted(batch["matched_scope_tokens"]),
                "owner_decision_dependency_counts": dict(
                    sorted(batch["owner_decision_dependency_counts"].items())
                ),
            }
        )
    return batches


def build_cleanup_impact_report(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OWNER_REVIEW,
    origin_report_path: Path = DEFAULT_ORIGIN_REPORT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    owner_review = _load_json(repo_root, owner_review_packet_path)
    origin_report = _load_json(repo_root, origin_report_path)
    review_rows = [
        row for row in _as_list(owner_review.get("review_rows")) if isinstance(row, dict)
    ]
    reference_rows = _scan_references(repo_root=repo_root, review_rows=review_rows)
    blocking_rows = [
        row for row in reference_rows if row["blocking_cleanup_reference"] is True
    ]
    release_surface_paths = [
        _text(row.get("path"))
        for row in review_rows
        if _text(row.get("path_area")) == "release_surface"
    ]
    release_surface_reference_rows = [
        row
        for row in reference_rows
        if set(row["matched_quarantined_paths"]).intersection(release_surface_paths)
    ]
    release_surface_blocking_reference_rows = [
        row
        for row in release_surface_reference_rows
        if row["blocking_cleanup_reference"] is True
    ]
    cleanup_reference_priority_batches = _cleanup_reference_priority_batches(
        blocking_rows
    )
    owner_decision_pending_count = int(
        owner_review.get("owner_decision_pending_count", 0) or 0
    )
    blockers: list[str] = []
    if not owner_review:
        blockers.append("structural_scope_owner_review_packet_missing")
    if owner_review and not owner_review.get("contract_pass"):
        blockers.append("structural_scope_owner_review_packet_not_contract_pass")
    if not origin_report:
        blockers.append("structural_scope_origin_report_missing")
    if origin_report and not origin_report.get("contract_pass"):
        blockers.append("structural_scope_origin_report_not_contract_pass")
    if owner_decision_pending_count:
        blockers.append(f"owner_decision_pending_count={owner_decision_pending_count}")
    if blocking_rows:
        blockers.append(f"blocking_cleanup_reference_path_count={len(blocking_rows)}")
    cleanup_impact_clear = bool(review_rows and not blocking_rows)
    if blockers:
        status = "blocked_cleanup_impact"
    elif cleanup_impact_clear:
        status = "ready_for_owner_cleanup_decisions"
    else:
        status = "complete_no_quarantined_paths"
    next_actions = []
    if owner_decision_pending_count:
        next_actions.append(
            "record owner delete/extract decisions for quarantined non-structural paths"
        )
    if blocking_rows:
        next_actions.append(
            "resolve non-governance references before applying delete/extract cleanup"
        )
    if cleanup_reference_priority_batches:
        next_actions.append(
            "start blocking reference cleanup with "
            f"{cleanup_reference_priority_batches[0]['batch_id']}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_structural_scope_cleanup_impact_report.py"),
                owner_review_packet_path,
                origin_report_path,
            ],
            reused_evidence=False,
            reuse_policy=(
                "structural_scope_cleanup_impact_report_from_owner_review_and_tracked_references"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(owner_review and origin_report and not blockers),
        "cleanup_impact_clear": cleanup_impact_clear,
        "summary_line": (
            "Structural scope cleanup impact report: "
            f"{status.upper()} | quarantined={len(review_rows)} | "
            f"references={len(reference_rows)} | blocking={len(blocking_rows)} | "
            f"owner_pending={owner_decision_pending_count}"
        ),
        "owner_review_packet": owner_review_packet_path.as_posix(),
        "origin_report": origin_report_path.as_posix(),
        "quarantined_path_count": len(review_rows),
        "owner_decision_pending_count": owner_decision_pending_count,
        "release_surface_path_count": len(release_surface_paths),
        "release_surface_paths": release_surface_paths,
        "reference_path_count": len(reference_rows),
        "blocking_cleanup_reference_path_count": len(blocking_rows),
        "governance_reference_path_count": len(reference_rows) - len(blocking_rows),
        "reference_role_counts": _counts_by_key(reference_rows, "reference_role"),
        "blocking_reference_role_counts": _counts_by_key(
            blocking_rows, "reference_role"
        ),
        "release_surface_reference_path_count": len(release_surface_reference_rows),
        "release_surface_blocking_reference_path_count": len(
            release_surface_blocking_reference_rows
        ),
        "release_surface_reference_rows": release_surface_reference_rows[:50],
        "release_surface_blocking_reference_rows": (
            release_surface_blocking_reference_rows[:50]
        ),
        "blocking_reference_cleanup_batch_count": len(
            cleanup_reference_priority_batches
        ),
        "blocking_reference_cleanup_batches": cleanup_reference_priority_batches,
        "next_reference_cleanup_batch": (
            cleanup_reference_priority_batches[0]
            if cleanup_reference_priority_batches
            else {}
        ),
        "blocking_reference_cleanup_action_counts": _counts_by_key(
            blocking_rows,
            "recommended_cleanup_action",
        ),
        "reference_rows": reference_rows,
        "blocking_reference_rows": blocking_rows,
        "next_actions": next_actions,
        "blockers": blockers,
        "claim_boundary": (
            "This impact report is non-mutating. It does not approve owner "
            "decisions, delete files, or close scope cleanup. It only identifies "
            "non-quarantined tracked references that must be reviewed before "
            "PocketMD/GPCR/MD3Bead-family artifacts are deleted or extracted from "
            "the structural-analysis repository."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Structural Scope Cleanup Impact Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `cleanup_impact_clear`: `{payload['cleanup_impact_clear']}`",
        f"- `quarantined_path_count`: `{payload['quarantined_path_count']}`",
        f"- `reference_path_count`: `{payload['reference_path_count']}`",
        f"- `blocking_cleanup_reference_path_count`: `{payload['blocking_cleanup_reference_path_count']}`",
        f"- `owner_decision_pending_count`: `{payload['owner_decision_pending_count']}`",
        f"- `blocking_reference_cleanup_batch_count`: `{payload['blocking_reference_cleanup_batch_count']}`",
        "",
        "## Reference Roles",
        "",
        f"- `reference_role_counts`: `{payload['reference_role_counts']}`",
        f"- `blocking_reference_role_counts`: `{payload['blocking_reference_role_counts']}`",
        f"- `blocking_reference_cleanup_action_counts`: `{payload['blocking_reference_cleanup_action_counts']}`",
        "",
        "## Cleanup Batches",
        "",
        "| Batch | Priority | Role | Paths | Action |",
        "|---|---:|---|---:|---|",
    ]
    for batch in payload["blocking_reference_cleanup_batches"]:
        lines.append(
            "| "
            f"`{batch['batch_id']}` | "
            f"{batch['priority']} | "
            f"`{batch['reference_role']}` | "
            f"{batch['path_count']} | "
            f"`{batch['recommended_cleanup_action']}` |"
        )
    lines.extend(
        [
        "",
        "## Blocking References",
        "",
        "| Path | Role | Terms | Scope Tokens | Quarantined Paths |",
        "|---|---|---:|---|---:|",
        ]
    )
    for row in payload["blocking_reference_rows"][:80]:
        lines.append(
            "| "
            f"`{row['path']}` | "
            f"`{row['reference_role']}` | "
            f"{row['matched_term_count']} | "
            f"`{', '.join(row['matched_scope_tokens'])}` | "
            f"{row['matched_quarantined_path_count']} |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    if payload["next_actions"]:
        lines.extend(["", "## Next Actions", ""])
        lines.extend(f"- `{item}`" for item in payload["next_actions"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_cleanup_impact_report(
    *,
    repo_root: Path = ROOT,
    owner_review_packet_path: Path = DEFAULT_OWNER_REVIEW,
    origin_report_path: Path = DEFAULT_ORIGIN_REPORT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_cleanup_impact_report(
        repo_root=repo_root,
        owner_review_packet_path=owner_review_packet_path,
        origin_report_path=origin_report_path,
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
    parser.add_argument("--origin-report", type=Path, default=DEFAULT_ORIGIN_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_cleanup_impact_report(
        repo_root=args.repo_root,
        owner_review_packet_path=args.owner_review_packet,
        origin_report_path=args.origin_report,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["cleanup_impact_clear"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
