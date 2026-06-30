#!/usr/bin/env python3
"""Audit release evidence freshness and provenance metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "release-evidence-freshness-report.v1"
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json"
)
DEFAULT_ARTIFACTS = (
    (
        "p0_closure_status",
        Path(
            "implementation/phase1/release_evidence/productization/p0_closure_status.json"
        ),
        Path("scripts/check_p0_closure_status.py"),
    ),
    (
        "p1_readiness_status",
        Path(
            "implementation/phase1/release_evidence/productization/p1_readiness_status.json"
        ),
        Path("scripts/check_p1_readiness_status.py"),
    ),
    (
        "p1_benchmark_breadth_status",
        Path(
            "implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json"
        ),
        Path("scripts/check_p1_benchmark_breadth_status.py"),
    ),
    (
        "real_project_corpus_measured_status",
        Path("implementation/phase1/real_project_corpus_measured_status.json"),
        Path("implementation/phase1/check_real_project_corpus_measured_status.py"),
    ),
    (
        "customer_shadow_evidence_status",
        Path("implementation/phase1/customer_shadow_evidence_status.json"),
        Path("implementation/phase1/check_customer_shadow_evidence_status.py"),
    ),
    (
        "customer_shadow_evidence_intake_packet",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "customer_shadow_evidence_intake_packet.json"
        ),
        Path("scripts/build_customer_shadow_evidence_intake_packet.py"),
    ),
    (
        "fresh_full_validation_lane_status",
        Path(
            "implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json"
        ),
        Path("scripts/build_fresh_full_validation_lane_status.py"),
    ),
    (
        "residual_level3_status",
        Path(
            "implementation/phase1/release_evidence/productization/residual_level3_status.json"
        ),
        Path("implementation/phase1/check_residual_level3_status.py"),
    ),
    (
        "g1_direct_residual_terminal_gate_report",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "mgt_g1_direct_residual_terminal_gate_report.json"
        ),
        Path("scripts/build_mgt_g1_direct_residual_terminal_gate_report.py"),
    ),
    (
        "g1_shell_material_budgeted_continuation_status",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "mgt_g1_followup387_shell_material_budgeted_continuation_status.json"
        ),
        Path("scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py"),
    ),
    (
        "evidence_console_scope_status",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "evidence_console_scope_status.json"
        ),
        Path("scripts/build_evidence_console_scope_status.py"),
    ),
    (
        "developer_preview_rc_status",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "developer_preview_rc_status.json"
        ),
        Path("scripts/build_developer_preview_rc_status.py"),
    ),
    (
        "public_benchmark_source_of_truth",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_source_of_truth.json"
        ),
        Path("scripts/build_public_benchmark_source_of_truth.py"),
    ),
    (
        "public_benchmark_harness_bundle",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_harness_bundle.json"
        ),
        Path("scripts/materialize_public_benchmark_harness_bundle.py"),
    ),
    (
        "accuracy_parity_scorecard",
        Path("implementation/phase1/real_accuracy_validation_report.json"),
        Path("implementation/phase1/run_real_accuracy_validation.py"),
    ),
    (
        "product_production_ai_checkpoint_readiness",
        Path(
            "implementation/phase1/release_evidence/productization/"
            "ai_engine_productization_contracts.json"
        ),
        Path("scripts/build_ai_engine_productization_contracts.py"),
    ),
)

SOURCE_OF_TRUTH_GAP_CLASSIFICATION: tuple[dict[str, str], ...] = (
    {
        "candidate": "accuracy_parity_scorecard",
        "classification": "fix",
        "freshness_policy": "direct_leaf_row",
        "freshness_label": "accuracy_parity_scorecard",
        "current_repo_match": "implementation/phase1/real_accuracy_validation_report.json",
        "decision": "Direct validation receipt with source tracking in freshness audit.",
    },
    {
        "candidate": "product_production_ai_checkpoint_readiness",
        "classification": "fix",
        "freshness_policy": "direct_leaf_row",
        "freshness_label": "product_production_ai_checkpoint_readiness",
        "current_repo_match": (
            "implementation/phase1/release_evidence/productization/"
            "ai_engine_productization_contracts.json"
        ),
        "decision": "Direct productization receipt with checkpoint source tracking in freshness audit.",
    },
    {
        "candidate": "goal_readiness_rollup",
        "classification": "aggregator-review",
        "freshness_policy": "aggregator_source_tracking_only",
        "freshness_label": "",
        "current_repo_match": (
            "implementation/phase1/release_evidence/productization/"
            "product_readiness_snapshot.json"
        ),
        "decision": "Keep snapshot-level upstream stale/inconsistent policy instead of a leaf row.",
    },
    {
        "candidate": "product_goal_completion_audit",
        "classification": "aggregator-review",
        "freshness_policy": "aggregator_source_tracking_only",
        "freshness_label": "",
        "current_repo_match": (
            "implementation/phase1/release_evidence/productization/"
            "pm_release_gate_completion_audit.json"
        ),
        "decision": "Track PM report and closure-board inputs rather than treating the audit as heavy evidence.",
    },
    {
        "candidate": "goal_operator_action_board",
        "classification": "aggregator-review",
        "freshness_policy": "aggregator_source_tracking_only",
        "freshness_label": "",
        "current_repo_match": (
            "implementation/phase1/release_evidence/productization/"
            "pm_release_blocker_action_register.json; "
            "implementation/phase1/release_evidence/productization/"
            "pm_release_blocker_closure_board.json"
        ),
        "decision": "Keep operator boards as sourced rollups of PM/freshness inputs, not closure evidence.",
    },
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_utc_iso() -> str:
    return _now_utc().isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_key(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path)


def _report_input_checksums(repo_root: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for row in rows:
        for key in ("artifact_path", "producer_path"):
            path = Path(str(row.get(key, "")))
            checksums[_path_key(repo_root, path)] = (
                f"sha256:{_sha256(path)}" if path.exists() else "missing"
            )
    return checksums


def _classification_count(classification: str) -> int:
    return sum(
        1
        for row in SOURCE_OF_TRUTH_GAP_CLASSIFICATION
        if row["classification"] == classification
    )


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_rev_parse(repo_root: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", text],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_diff_name_only(
    repo_root: Path, source_commit: str, current_commit: str, paths: list[Path]
) -> list[str]:
    if not source_commit or not current_commit or not paths:
        return []
    path_args: list[str] = []
    for path in paths:
        try:
            path_args.append(str(path if not path.is_absolute() else path.relative_to(repo_root)))
        except ValueError:
            continue
    if not path_args:
        return []
    try:
        output = subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                f"{source_commit}..{current_commit}",
                "--",
                *path_args,
            ],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    sources = (
        payload,
        _nested_dict(payload, "summary"),
        _nested_dict(payload, "inputs"),
    )
    for source in sources:
        for key in keys:
            if key in source:
                return source.get(key)
    return None


def _commit_matches(value: Any, current_commit: str) -> bool:
    text = str(value or "").strip()
    if not text or not current_commit:
        return False
    return current_commit.startswith(text) or text.startswith(current_commit)


def _input_checksum_paths(repo_root: Path, input_checksum: Any) -> list[Path]:
    if not isinstance(input_checksum, dict):
        return []
    paths: list[Path] = []
    for key in input_checksum:
        text = str(key).strip()
        if not text:
            continue
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            paths.append(candidate)
    return paths


def _receipt_commit_allowed_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").lstrip("./")
    if normalized.startswith("implementation/phase1/release_evidence/productization/"):
        return True
    return normalized in {
        "implementation/phase1/customer_shadow_evidence_status.json",
        "implementation/phase1/release_evidence/surface/product_capabilities_surface.json",
    }


def _source_state_matches(
    *,
    repo_root: Path,
    source_commit: Any,
    current_commit: str,
    producer_path: Path,
    input_checksum: Any,
) -> tuple[bool, bool, list[str]]:
    if _commit_matches(source_commit, current_commit):
        return True, True, []
    source = _git_rev_parse(repo_root, str(source_commit or ""))
    current = _git_rev_parse(repo_root, current_commit)
    if not source or not current:
        return False, False, []
    paths = [producer_path, *_input_checksum_paths(repo_root, input_checksum)]
    changed_paths = _git_diff_name_only(repo_root, source, current, paths)
    non_receipt_paths = [
        path for path in changed_paths if not _receipt_commit_allowed_path(path)
    ]
    return not non_receipt_paths, False, non_receipt_paths


def _dependency_mtime_check(
    *,
    artifact_exists: bool,
    artifact_mtime: float,
    producer_exists: bool,
    producer_mtime: float,
    input_dependency_paths: list[Path],
) -> tuple[bool, list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    if producer_exists:
        details.append(
            {
                "dependency_kind": "producer",
                "dependency_path": "<producer>",
                "dependency_mtime": producer_mtime,
                "newer_than_artifact": artifact_mtime < producer_mtime,
            }
        )
    for dep_path in input_dependency_paths:
        dep_mtime = dep_path.stat().st_mtime
        details.append(
            {
                "dependency_kind": "input_checksum",
                "dependency_path": str(dep_path),
                "dependency_mtime": dep_mtime,
                "newer_than_artifact": artifact_mtime < dep_mtime,
            }
        )
    if not artifact_exists or not producer_exists:
        return False, details
    return (not any(detail["newer_than_artifact"] for detail in details), details)


def _truthy_presence(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _row(
    *,
    label: str,
    artifact_path: Path,
    producer_path: Path,
    repo_root: Path,
    current_commit: str,
    max_age_days: float,
    now: datetime,
) -> dict[str, Any]:
    payload = _load_json(artifact_path)
    generated_at_raw = _first_present(payload, ("generated_at", "created_at"))
    generated_at = _parse_iso(generated_at_raw)
    source_commit = _first_present(
        payload,
        (
            "source_commit_sha",
            "source_commit",
            "git_commit",
            "commit_sha",
            "our_engine_commit",
        ),
    )
    engine_version = _first_present(
        payload, ("engine_version", "solver_version", "version")
    )
    input_checksum = _first_present(
        payload,
        (
            "input_checksum",
            "input_checksums",
            "input_sha256",
            "input_artifact_checksum",
            "source_checksum",
        ),
    )
    reuse_marker = _first_present(
        payload,
        (
            "reused_evidence",
            "reused_existing",
            "reuse_existing_if_present",
            "reuse_policy",
        ),
    )
    source_state_match, source_commit_exact_match, changed_since_source_commit = (
        _source_state_matches(
            repo_root=repo_root,
            source_commit=source_commit,
            current_commit=current_commit,
            producer_path=producer_path,
            input_checksum=input_checksum,
        )
    )
    input_dependency_paths = _input_checksum_paths(repo_root, input_checksum)
    blockers: list[str] = []
    artifact_exists = artifact_path.exists()
    producer_exists = producer_path.exists()
    generated_age_days: float | None = None
    if not artifact_exists:
        blockers.append("artifact_missing")
    if not producer_exists:
        blockers.append("producer_missing")
    if generated_at is None:
        blockers.append("generated_at_missing_or_invalid")
    else:
        generated_age_days = (now - generated_at).total_seconds() / 86400.0
        if generated_age_days < 0 or generated_age_days > max_age_days:
            blockers.append("generated_at_outside_allowed_window")
    if not _truthy_presence(source_commit):
        blockers.append("source_commit_missing")
    elif not source_state_match:
        blockers.append("source_commit_mismatch")
    if not _truthy_presence(engine_version):
        blockers.append("engine_version_missing")
    if not _truthy_presence(input_checksum):
        blockers.append("input_checksum_missing")
    if reuse_marker is None:
        blockers.append("reuse_marker_missing")

    artifact_mtime = artifact_path.stat().st_mtime if artifact_exists else 0.0
    producer_mtime = producer_path.stat().st_mtime if producer_exists else 0.0
    dependency_mtime_pass, dependency_mtime_details = _dependency_mtime_check(
        artifact_exists=artifact_exists,
        artifact_mtime=artifact_mtime,
        producer_exists=producer_exists,
        producer_mtime=producer_mtime,
        input_dependency_paths=input_dependency_paths,
    )
    producer_newer = any(
        detail["dependency_kind"] == "producer" and detail["newer_than_artifact"]
        for detail in dependency_mtime_details
    )
    input_dependency_newer = any(
        detail["dependency_kind"] == "input_checksum" and detail["newer_than_artifact"]
        for detail in dependency_mtime_details
    )
    if producer_newer:
        blockers.append("producer_newer_than_artifact")
    if input_dependency_newer:
        blockers.append("input_dependency_newer_than_artifact")

    return {
        "label": label,
        "artifact_path": str(artifact_path),
        "producer_path": str(producer_path),
        "artifact_exists": artifact_exists,
        "producer_exists": producer_exists,
        "artifact_sha256": _sha256(artifact_path) if artifact_exists else "",
        "generated_at": str(generated_at_raw or ""),
        "generated_age_days": generated_age_days,
        "max_age_days": max_age_days,
        "source_commit": str(source_commit or ""),
        "source_commit_match": source_state_match,
        "source_commit_exact_match": source_commit_exact_match,
        "changed_paths_since_source_commit": changed_since_source_commit,
        "engine_version": str(engine_version or ""),
        "engine_version_present": _truthy_presence(engine_version),
        "input_checksum_present": _truthy_presence(input_checksum),
        "input_dependency_paths": [str(path) for path in input_dependency_paths],
        "reuse_marker_present": reuse_marker is not None,
        "dependency_mtime_details": dependency_mtime_details,
        "dependency_mtime_pass": dependency_mtime_pass,
        "blockers": blockers,
        "ok": not blockers,
    }


def build_report(
    *,
    repo_root: Path = Path("."),
    artifacts: tuple[tuple[str, Path, Path], ...] = DEFAULT_ARTIFACTS,
    max_age_days: float = 30.0,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    current_commit = _git_head(repo_root)
    now = _now_utc()
    rows = [
        _row(
            label=label,
            artifact_path=(repo_root / artifact_path).resolve()
            if not artifact_path.is_absolute()
            else artifact_path,
            producer_path=(repo_root / producer_path).resolve()
            if not producer_path.is_absolute()
            else producer_path,
            repo_root=repo_root,
            current_commit=current_commit,
            max_age_days=max_age_days,
            now=now,
        )
        for label, artifact_path, producer_path in artifacts
    ]
    blockers = [
        f"{row['label']}::{blocker}" for row in rows for blocker in row["blockers"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": current_commit,
        "engine_version": "structural-optimization-workbench@1.0.0",
        "input_checksums": _report_input_checksums(repo_root, rows),
        "reused_evidence": True,
        "reuse_policy": "status_rebuilt_from_release_evidence_artifact_metadata",
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_RELEASE_EVIDENCE_FRESHNESS",
        "current_source_commit_sha": current_commit,
        "max_age_days": max_age_days,
        "summary": {
            "artifact_count": len(rows),
            "pass_count": sum(1 for row in rows if row["ok"]),
            "blocker_count": len(blockers),
            "source_of_truth_gap_candidate_count": len(
                SOURCE_OF_TRUTH_GAP_CLASSIFICATION
            ),
            "source_of_truth_gap_fix_count": _classification_count("fix"),
            "source_of_truth_gap_fixed_count": _classification_count("fix"),
            "source_of_truth_gap_no_op_count": _classification_count("no-op"),
            "source_of_truth_gap_aggregator_review_count": _classification_count(
                "aggregator-review"
            ),
            "source_commit_match_count": sum(
                1 for row in rows if row["source_commit_match"]
            ),
            "engine_version_present_count": sum(
                1 for row in rows if row["engine_version_present"]
            ),
            "input_checksum_present_count": sum(
                1 for row in rows if row["input_checksum_present"]
            ),
            "reuse_marker_present_count": sum(
                1 for row in rows if row["reuse_marker_present"]
            ),
            "dependency_mtime_pass_count": sum(
                1 for row in rows if row["dependency_mtime_pass"]
            ),
        },
        "blockers": blockers,
        "rows": rows,
        "source_of_truth_gap_classification": [
            dict(row) for row in SOURCE_OF_TRUTH_GAP_CLASSIFICATION
        ],
        "claim_boundary": (
            "Freshness audit records whether release evidence exposes source commit, engine version, "
            "input checksum, reuse marker, generated_at, producer dependency mtime, and declared "
            "input-checksum file dependency mtime. It does not rerun heavy validation by itself."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Release Evidence Freshness",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `current_source_commit_sha`: `{payload['current_source_commit_sha']}`",
        f"- `blockers`: `{', '.join(payload['blockers']) if payload['blockers'] else 'none'}`",
        "",
        "| Artifact | Status | Blockers | Newer Dependencies |",
        "|---|---|---|---|",
    ]
    for row in payload["rows"]:
        blockers = ", ".join(row["blockers"]) if row["blockers"] else "none"
        newer = [
            detail["dependency_path"]
            for detail in row.get("dependency_mtime_details", [])
            if detail.get("newer_than_artifact")
        ]
        newer_label = ", ".join(f"`{path}`" for path in newer) if newer else "none"
        lines.append(
            f"| `{row['label']}` | `{'pass' if row['ok'] else 'blocked'}` | `{blockers}` | {newer_label} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-days", type=float, default=30.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def _resolve_out_md(out: Path, out_md: Path | None) -> Path:
    return out_md if out_md is not None else out.with_suffix(".md")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_md = _resolve_out_md(args.out, args.out_md)
    payload = build_report(max_age_days=args.max_age_days)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_markdown(payload), encoding="utf-8")
    summary = (
        f"release-evidence-freshness: {'PASS' if payload['contract_pass'] else 'BLOCKED'} "
        f"pass={payload['summary']['pass_count']}/{payload['summary']['artifact_count']} "
        f"blockers={payload['summary']['blocker_count']}"
    )
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else summary
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
