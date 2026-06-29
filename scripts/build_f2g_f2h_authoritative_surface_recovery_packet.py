#!/usr/bin/env python3
"""Build the F2g/F2h authoritative surface recovery packet."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREFLIGHT = Path(".betelgeuze/f2g_f2h_surface_preflight.local.json")
DEFAULT_OUTPUT = Path(".betelgeuze/f2g_f2h_authoritative_surface_recovery_packet.local.json")
SCHEMA_VERSION = "f2g-f2h-authoritative-surface-recovery-packet.v1"


def _load_preflight_module():
    path = REPO_ROOT / "scripts" / "build_f2g_f2h_surface_preflight.py"
    spec = importlib.util.spec_from_file_location("build_f2g_f2h_surface_preflight", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load build_f2g_f2h_surface_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_recovery_packet(
    *,
    repo_root: Path = REPO_ROOT,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> dict[str, Any]:
    resolved_preflight = preflight_path if preflight_path.is_absolute() else repo_root / preflight_path
    preflight = _load_json(resolved_preflight)
    if not preflight:
        preflight = _load_preflight_module().build_preflight(repo_root=repo_root)
    rows = list(preflight.get("surfaces") or [])
    recovery_items = [
        {
            "surface_id": str(row.get("surface_id") or ""),
            "blocker": str(row.get("blocker") or ""),
            "recovery_action": str(row.get("recovery_action") or ""),
            "candidate_paths": [
                str(item.get("path") or "")
                for item in row.get("candidate_checks") or []
                if isinstance(item, dict)
            ],
        }
        for row in rows
        if not bool(row.get("ready"))
    ]
    ready = len(recovery_items) == 0
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "blocked",
        "reason_code": "PASS" if ready else "ERR_AUTHORITATIVE_SURFACES_REQUIRE_RECOVERY",
        "promotes_g1_closure": False,
        "claim_boundary": "surface_recovery_planning_only",
        "preflight_status": preflight.get("status", "unknown"),
        "preflight_blocker_count": int(preflight.get("summary", {}).get("blocker_count", len(recovery_items)) or 0),
        "surface_count": int(len(rows)),
        "ready_surface_count": int(sum(1 for row in rows if row.get("ready"))),
        "recovery_item_count": int(len(recovery_items)),
        "recovery_items": recovery_items,
        "next_actions": (
            ["run_f2g_support_elastic_link_reconciliation_audit"]
            if ready
            else ["recover_or_regenerate_listed_authoritative_surfaces", "rerun_f2g_f2h_surface_preflight"]
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--preflight-json", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_recovery_packet(repo_root=args.repo_root, preflight_path=args.preflight_json)
    output = args.output_json if args.output_json.is_absolute() else args.repo_root / args.output_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "f2g-f2h-authoritative-surface-recovery: "
        f"status={payload['status']} recovery_items={payload['recovery_item_count']}"
    )
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
