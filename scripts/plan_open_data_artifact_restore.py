#!/usr/bin/env python3
"""Plan restoration of externalized open-data artifacts.

The command never downloads or copies large files. It turns the checksum
manifest into an operator-safe restore plan and can verify a local artifact
cache before heavy validation runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_open_data_external_artifacts_manifest import validate_manifest_structure  # noqa: E402


DEFAULT_MANIFEST = Path("implementation/phase1/open_data_external_artifacts_manifest.json")
SCHEMA_VERSION = "open_data_artifact_restore_plan.v1"


class RestorePlanError(RuntimeError):
    """Raised when a restore plan cannot be built."""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RestorePlanError("manifest root must be an object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_status(path: Path, *, expected_bytes: int, expected_sha256: str) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "ok": False, "path": str(path), "reason": "missing"}
    if not path.is_file():
        return {"exists": True, "ok": False, "path": str(path), "reason": "not_file"}

    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        return {
            "exists": True,
            "ok": False,
            "path": str(path),
            "reason": "bytes_mismatch",
            "actual_bytes": actual_bytes,
        }
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        return {
            "exists": True,
            "ok": False,
            "path": str(path),
            "reason": "sha256_mismatch",
            "actual_sha256": actual_sha256,
        }
    return {"exists": True, "ok": True, "path": str(path), "reason": "ok"}


def _cache_path(cache_root: Path, row: dict[str, Any]) -> Path:
    source_family = str(row["source_family"])
    digest = str(row["sha256"])
    target_name = Path(str(row["path"])).name
    return cache_root / source_family / digest / target_name


def _restore_command(cache_path: Path, target_path: Path) -> str:
    return f"mkdir -p {target_path.parent.as_posix()} && cp {cache_path.as_posix()} {target_path.as_posix()}"


def build_restore_plan(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    errors, rows = validate_manifest_structure(manifest)
    if errors:
        raise RestorePlanError("; ".join(errors))

    artifacts: list[dict[str, Any]] = []
    total_bytes = 0
    cache_ready = 0
    already_restored = 0
    blocked = 0
    source_families: set[str] = set()

    for row in rows:
        target_path = Path(str(row["path"]))
        expected_bytes = int(row["bytes"])
        expected_sha256 = str(row["sha256"])
        source_family = str(row["source_family"])
        source_families.add(source_family)
        total_bytes += expected_bytes

        target = _file_status(
            target_path,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
        )
        cache: dict[str, Any] | None = None
        restore_command = ""
        if cache_root is not None:
            candidate = _cache_path(cache_root, row)
            cache = _file_status(
                candidate,
                expected_bytes=expected_bytes,
                expected_sha256=expected_sha256,
            )
            restore_command = _restore_command(candidate, target_path)

        if target["ok"]:
            status = "already_restored"
            already_restored += 1
        elif cache is not None and cache["ok"]:
            status = "cache_ready"
            cache_ready += 1
        else:
            status = "blocked"
            blocked += 1

        artifacts.append(
            {
                "path": str(target_path),
                "bytes": expected_bytes,
                "sha256": expected_sha256,
                "source_family": source_family,
                "disposition": str(row["disposition"]),
                "status": status,
                "target": target,
                "cache": cache,
                "restore_command": restore_command,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "manifest": str(manifest_path),
        "cache_root": str(cache_root) if cache_root is not None else "",
        "cache_layout": "source_family/sha256/basename",
        "ok": blocked == 0,
        "summary": {
            "artifact_count": len(artifacts),
            "total_bytes": total_bytes,
            "source_family_count": len(source_families),
            "source_families": sorted(source_families),
            "already_restored": already_restored,
            "cache_ready": cache_ready,
            "blocked": blocked,
        },
        "artifacts": artifacts,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_text(plan: dict[str, Any]) -> None:
    summary = plan["summary"]
    print(
        "Open-data restore plan: "
        f"artifacts={summary['artifact_count']} "
        f"already_restored={summary['already_restored']} "
        f"cache_ready={summary['cache_ready']} "
        f"blocked={summary['blocked']} "
        f"total_bytes={summary['total_bytes']}"
    )
    if plan["cache_root"]:
        print(f"cache_root={plan['cache_root']} layout={plan['cache_layout']}")
    for row in plan["artifacts"]:
        print(f"- {row['status']}: {row['path']} ({row['source_family']}, {row['bytes']} bytes)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a restore plan for externalized open-data artifacts.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--cache-root",
        type=Path,
        help="Optional local artifact cache using source_family/sha256/basename layout.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--out", type=Path, help="Write JSON output to this path.")
    parser.add_argument("--fail-unready", action="store_true", help="Exit 1 when any artifact is blocked.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = build_restore_plan(manifest_path=args.manifest, cache_root=args.cache_root)
    except (OSError, json.JSONDecodeError, RestorePlanError) as exc:
        print(f"Open-data restore plan failed: {exc}", file=sys.stderr)
        return 2

    if args.out:
        _write_json(args.out, plan)
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        _print_text(plan)
    return 1 if args.fail_unready and not bool(plan["ok"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
