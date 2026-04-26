#!/usr/bin/env python3
"""Archive and organize phase1 experiment artifacts by test run.

This utility supports two workflows:
1) archive-run: bundle generated files/dirs into experiments/by_test/<test>/<timestamp>
2) cleanup-legacy: move stale sample/seed artifacts from phase1 root into legacy archive
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


DEFAULT_LEGACY_PATTERNS = (
    "*.seed_*.json",
    "*.sample*.json",
    "*.sample*.jsonl",
    "*.sample*.csv",
    "ci_gate_report.pass.sample.json",
    "ci_gate_report.fail.sample.json",
    "priority3_summary.pass.sample.json",
    "priority3_summary.fail.sample.json",
)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_label(text: str) -> str:
    s = "".join(ch if (ch.isalnum() or ch in {"-", "_", "."}) else "-" for ch in str(text))
    return s.strip("-_") or "unnamed"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _dir_stats(path: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        file_count += 1
        total_bytes += p.stat().st_size
    return file_count, total_bytes


def _copy_or_move(src: Path, dst: Path, move: bool) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if move:
            shutil.move(str(src), str(dst))
        else:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        file_count, total_bytes = _dir_stats(dst)
        return {
            "src": str(src),
            "dst": str(dst),
            "kind": "directory",
            "file_count": int(file_count),
            "bytes": int(total_bytes),
            "mode": "move" if move else "copy",
        }

    if move:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(src, dst)
    return {
        "src": str(src),
        "dst": str(dst),
        "kind": "file",
        "bytes": int(dst.stat().st_size),
        "sha256": _sha256(dst),
        "mode": "move" if move else "copy",
    }


def archive_test_outputs(
    *,
    test_name: str,
    paths: Iterable[str],
    run_root: str = "implementation/phase1/experiments/by_test",
    move: bool = False,
    report_out: str | None = None,
) -> str:
    ts = _utc_ts()
    safe_name = _safe_label(test_name)
    run_dir = Path(run_root) / safe_name / ts
    bundle_dir = run_dir / "artifacts"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    archived: list[dict] = []
    seen: set[str] = set()
    for raw in paths:
        src = Path(str(raw))
        src_key = str(src.resolve()) if src.exists() else str(src)
        if src_key in seen:
            continue
        seen.add(src_key)
        if not src.exists():
            continue
        if src.is_dir():
            dst = bundle_dir / src.name
        else:
            # Keep basename to avoid deep path coupling in archived bundles.
            dst = bundle_dir / src.name
        archived.append(_copy_or_move(src, dst, move=move))

    manifest = {
        "schema_version": "1.0",
        "run_id": "phase1-experiment-artifact-archive",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_name": safe_name,
        "run_dir": str(run_dir),
        "mode": "move" if move else "copy",
        "archived_count": len(archived),
        "artifacts": archived,
    }
    manifest_path = run_dir / "artifact_archive_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    latest_ptr = Path(run_root) / safe_name / "latest_manifest.json"
    latest_ptr.parent.mkdir(parents=True, exist_ok=True)
    latest_ptr.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "test_name": safe_name,
                "latest_run_dir": str(run_dir),
                "latest_manifest": str(manifest_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if report_out:
        ro = Path(report_out)
        ro.parent.mkdir(parents=True, exist_ok=True)
        ro.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "run_id": "phase1-experiment-archive-report",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "test_name": safe_name,
                    "manifest": str(manifest_path),
                    "archived_count": len(archived),
                    "mode": "move" if move else "copy",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return str(manifest_path)


def cleanup_legacy_outputs(
    *,
    phase1_root: str = "implementation/phase1",
    archive_root: str = "implementation/phase1/experiments/legacy_cleanup",
    patterns: Iterable[str] = DEFAULT_LEGACY_PATTERNS,
    dry_run: bool = False,
) -> dict:
    root = Path(phase1_root)
    ts = _utc_ts()
    cleanup_dir = Path(archive_root) / ts / "phase1_root"
    cleanup_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[Path] = []
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file():
                candidates.append(p)

    # deterministic, unique
    uniq = sorted({str(p.resolve()): p for p in candidates}.values(), key=lambda p: p.name.lower())
    moved: list[dict] = []
    skipped = 0
    for src in uniq:
        dst = cleanup_dir / src.name
        if dry_run:
            moved.append(
                {
                    "src": str(src),
                    "dst": str(dst),
                    "kind": "file",
                    "mode": "dry_run",
                }
            )
            continue
        if dst.exists():
            dst = cleanup_dir / f"{src.stem}__{_utc_ts()}{src.suffix}"
        try:
            moved.append(_copy_or_move(src, dst, move=True))
        except Exception:
            skipped += 1

    report = {
        "schema_version": "1.0",
        "run_id": "phase1-legacy-cleanup",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase1_root": str(root),
        "archive_dir": str(cleanup_dir),
        "dry_run": bool(dry_run),
        "candidate_count": len(uniq),
        "moved_count": len(moved),
        "skipped_count": int(skipped),
        "patterns": list(patterns),
        "moved": moved,
    }
    report_path = cleanup_dir.parent / "legacy_cleanup_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"report_path": str(report_path), "archive_dir": str(cleanup_dir), "moved_count": len(moved), "candidate_count": len(uniq)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--test-name", default="")
    p.add_argument("--path", action="append", default=[])
    p.add_argument("--run-root", default="implementation/phase1/experiments/by_test")
    p.add_argument("--move", action="store_true")
    p.add_argument("--report-out", default="")

    p.add_argument("--cleanup-legacy", action="store_true")
    p.add_argument("--phase1-root", default="implementation/phase1")
    p.add_argument("--legacy-archive-root", default="implementation/phase1/experiments/legacy_cleanup")
    p.add_argument("--legacy-pattern", action="append", default=[])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if bool(args.cleanup_legacy):
        patterns = args.legacy_pattern if args.legacy_pattern else list(DEFAULT_LEGACY_PATTERNS)
        result = cleanup_legacy_outputs(
            phase1_root=str(args.phase1_root),
            archive_root=str(args.legacy_archive_root),
            patterns=patterns,
            dry_run=bool(args.dry_run),
        )
        print(f"Wrote legacy cleanup report: {result['report_path']}")
        return

    if not str(args.test_name).strip():
        raise SystemExit("--test-name is required unless --cleanup-legacy is set")
    manifest = archive_test_outputs(
        test_name=str(args.test_name),
        paths=[str(x) for x in args.path],
        run_root=str(args.run_root),
        move=bool(args.move),
        report_out=(str(args.report_out) if str(args.report_out).strip() else None),
    )
    print(f"Wrote artifact archive manifest: {manifest}")


if __name__ == "__main__":
    main()

