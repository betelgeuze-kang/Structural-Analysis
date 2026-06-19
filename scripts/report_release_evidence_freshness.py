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
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_ARTIFACTS = (
    (
        "p0_closure_status",
        Path("implementation/phase1/release_evidence/productization/p0_closure_status.json"),
        Path("scripts/check_p0_closure_status.py"),
    ),
    (
        "p1_readiness_status",
        Path("implementation/phase1/release_evidence/productization/p1_readiness_status.json"),
        Path("scripts/check_p1_readiness_status.py"),
    ),
    (
        "p1_benchmark_breadth_status",
        Path("implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json"),
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
        "fresh_full_validation_lane_status",
        Path("implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json"),
        Path("scripts/build_fresh_full_validation_lane_status.py"),
    ),
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


def _git_diff_name_only(repo_root: Path, source_commit: str, current_commit: str, paths: list[Path]) -> list[str]:
    if not source_commit or not current_commit or not paths:
        return []
    path_args = [str(path if not path.is_absolute() else path.relative_to(repo_root)) for path in paths]
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source_commit}..{current_commit}", "--", *path_args],
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
    sources = (payload, _nested_dict(payload, "summary"), _nested_dict(payload, "inputs"))
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


def _input_checksum_paths(input_checksum: Any) -> list[Path]:
    if isinstance(input_checksum, dict):
        return [Path(str(key)) for key in input_checksum if str(key).strip()]
    return []


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
    paths = [producer_path, *_input_checksum_paths(input_checksum)]
    changed_paths = _git_diff_name_only(repo_root, source, current, paths)
    return not changed_paths, False, changed_paths


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
        ("source_commit_sha", "source_commit", "git_commit", "commit_sha", "our_engine_commit"),
    )
    engine_version = _first_present(payload, ("engine_version", "solver_version", "version"))
    input_checksum = _first_present(
        payload,
        ("input_checksum", "input_checksums", "input_sha256", "input_artifact_checksum", "source_checksum"),
    )
    reuse_marker = _first_present(
        payload,
        ("reused_evidence", "reused_existing", "reuse_existing_if_present", "reuse_policy"),
    )
    source_state_match, source_commit_exact_match, changed_since_source_commit = _source_state_matches(
        repo_root=repo_root,
        source_commit=source_commit,
        current_commit=current_commit,
        producer_path=producer_path,
        input_checksum=input_checksum,
    )
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
    if artifact_exists and producer_exists and artifact_mtime < producer_mtime:
        blockers.append("producer_newer_than_artifact")

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
        "reuse_marker_present": reuse_marker is not None,
        "dependency_mtime_pass": bool(not artifact_exists or not producer_exists or artifact_mtime >= producer_mtime),
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
            artifact_path=(repo_root / artifact_path).resolve() if not artifact_path.is_absolute() else artifact_path,
            producer_path=(repo_root / producer_path).resolve() if not producer_path.is_absolute() else producer_path,
            repo_root=repo_root,
            current_commit=current_commit,
            max_age_days=max_age_days,
            now=now,
        )
        for label, artifact_path, producer_path in artifacts
    ]
    blockers = [f"{row['label']}::{blocker}" for row in rows for blocker in row["blockers"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_RELEASE_EVIDENCE_FRESHNESS",
        "current_source_commit_sha": current_commit,
        "max_age_days": max_age_days,
        "summary": {
            "artifact_count": len(rows),
            "pass_count": sum(1 for row in rows if row["ok"]),
            "blocker_count": len(blockers),
            "source_commit_match_count": sum(1 for row in rows if row["source_commit_match"]),
            "engine_version_present_count": sum(1 for row in rows if row["engine_version_present"]),
            "input_checksum_present_count": sum(1 for row in rows if row["input_checksum_present"]),
            "reuse_marker_present_count": sum(1 for row in rows if row["reuse_marker_present"]),
            "dependency_mtime_pass_count": sum(1 for row in rows if row["dependency_mtime_pass"]),
        },
        "blockers": blockers,
        "rows": rows,
        "claim_boundary": (
            "Freshness audit records whether release evidence exposes source commit, engine version, "
            "input checksum, reuse marker, generated_at, and producer dependency recency. It does not rerun "
            "heavy validation by itself."
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
        "| Artifact | Status | Blockers |",
        "|---|---|---|",
    ]
    for row in payload["rows"]:
        blockers = ", ".join(row["blockers"]) if row["blockers"] else "none"
        lines.append(f"| `{row['label']}` | `{'pass' if row['ok'] else 'blocked'}` | `{blockers}` |")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-days", type=float, default=30.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(max_age_days=args.max_age_days)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(_markdown(payload), encoding="utf-8")
    summary = (
        f"release-evidence-freshness: {'PASS' if payload['contract_pass'] else 'BLOCKED'} "
        f"pass={payload['summary']['pass_count']}/{payload['summary']['artifact_count']} "
        f"blockers={payload['summary']['blocker_count']}"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else summary)
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
