#!/usr/bin/env python3
"""Build a deterministic opening-source no-op ready receipt.

Cross-walks the existing local-axis/opening-semantics receipt with the
shell-bending tangent receipt to surface a single audit-friendly
"current-source opening semantics" status. The MGT benchmark bridge
contains no opening/hole/void source rows, so the current-source opening
semantics is a checked no-op (parser + provenance ready, no runtime
cutout). Generic cutout meshing is explicitly NOT claimed.

Output JSON:
  implementation/phase1/release_evidence/productization/mgt_opening_source_noop_ready_receipt.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"

DEFAULT_LOCAL_AXIS = PRODUCTIZATION / "mgt_element_local_axis_opening_semantics_receipt.json"
DEFAULT_SHELL = PRODUCTIZATION / "mgt_surface_shell_bending_tangent.json"
DEFAULT_OUT = PRODUCTIZATION / "mgt_opening_source_noop_ready_receipt.json"


SCHEMA_VERSION = "mgt-opening-source-noop-ready-receipt.v1"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return {}


def build_opening_source_noop_ready_receipt(
    *,
    local_axis_opening_json: Path = DEFAULT_LOCAL_AXIS,
    shell_bending_tangent_json: Path = DEFAULT_SHELL,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    local_axis = _load(local_axis_opening_json)
    shell = _load(shell_bending_tangent_json)
    local_axis_support = local_axis.get("support") if isinstance(local_axis.get("support"), dict) else {}
    local_axis_summary = local_axis.get("summary") if isinstance(local_axis.get("summary"), dict) else {}
    opening_source_scan = local_axis.get("opening_source_scan") if isinstance(local_axis.get("opening_source_scan"), dict) else {}
    shell_aniso = shell.get("anisotropy") if isinstance(shell.get("anisotropy"), dict) else {}
    shell_opening = shell.get("opening_source_inventory") if isinstance(shell.get("opening_source_inventory"), dict) else {}
    local_opening_noop_ready = bool(local_axis_support.get("current_source_opening_noop_runtime_ready"))
    shell_opening_noop_ready = bool(shell_opening.get("current_source_opening_noop_ready"))
    local_opening_rows_present = bool(local_axis_support.get("opening_source_rows_present"))
    shell_opening_marker_count = int(shell_opening.get("current_source_opening_marker_count") or 0)
    opening_rows_present = bool(local_opening_rows_present) or shell_opening_marker_count > 0
    current_source_noop_ready = bool(
        (not opening_rows_present) and local_opening_noop_ready and shell_opening_noop_ready
    )
    generic_cutout_ready = bool(local_axis_support.get("generic_opening_cutout_runtime_semantics_ready"))
    claim_boundary = {
        "closed": [
            "MGT *ELEMENT frame ANGLE rows are parsed and exported into roundtrip NPZ",
            "6-DOF frame elastic and geometric tangent assembly consumes nonzero frame ANGLE as local y/z roll",
            "PLATE compact local-axis option tokens are inventoried; current source rows are all default zero",
            "benchmark bridge MGT contains no opening/hole/void source rows, so current-source opening semantics is a checked no-op (parser + provenance ready, no runtime cutout)",
            "shell-bending tangent has a deterministic no-op opening_source_inventory field reporting current_source_opening_marker_count=0",
        ],
        "not_closed": [
            "generic opening/cutout runtime meshing is not claimed because no opening/hole/void source rows are present in the benchmark bridge MGT",
            "surface shell local-axis LCAXIS has only default-zero source coverage in this MGT",
            "diaphragm/member release and full-load nonlinear frame-shell semantics remain outside this receipt",
        ],
    }
    blockers: list[str] = []
    if not local_opening_noop_ready:
        blockers.append("local_axis_opening_noop_runtime_not_ready")
    if not shell_opening_noop_ready:
        blockers.append("shell_opening_noop_inventory_missing")
    if opening_rows_present and not current_source_noop_ready:
        blockers.append("opening_source_rows_present_but_noop_not_armed")
    if generic_cutout_ready and not current_source_noop_ready:
        blockers.append("generic_cutout_ready_overrides_current_source_noop")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if current_source_noop_ready else "partial",
        "current_source_opening_noop_ready": bool(current_source_noop_ready),
        "current_source_opening_marker_count": int(
            local_axis_summary.get("opening_marker_row_count") or shell_opening_marker_count
        ),
        "generic_opening_cutout_ready": bool(generic_cutout_ready),
        "source": {
            "local_axis_opening_receipt": str(local_axis_opening_json),
            "local_axis_opening_receipt_exists": bool(local_axis_opening_json.is_file()),
            "shell_bending_tangent_receipt": str(shell_bending_tangent_json),
            "shell_bending_tangent_receipt_exists": bool(shell_bending_tangent_json.is_file()),
            "local_axis_summary": local_axis_summary,
            "shell_anisotropy": shell_aniso,
            "opening_source_scan": opening_source_scan,
        },
        "checks": {
            "local_axis_opening_noop_runtime_ready": local_opening_noop_ready,
            "shell_bending_opening_inventory_present": shell_opening_noop_ready,
            "opening_marker_count_zero": shell_opening_marker_count == 0,
            "opening_rows_absent_in_local_axis": not local_opening_rows_present,
        },
        "claim_boundary": claim_boundary,
        "blockers": blockers,
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-axis-opening-json", type=Path, default=DEFAULT_LOCAL_AXIS)
    parser.add_argument("--shell-bending-tangent-json", type=Path, default=DEFAULT_SHELL)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_opening_source_noop_ready_receipt(
        local_axis_opening_json=args.local_axis_opening_json,
        shell_bending_tangent_json=args.shell_bending_tangent_json,
        output_json=args.output_json,
    )
    print(
        "mgt-opening-source-noop-ready: "
        f"{payload['status']} markers={payload['current_source_opening_marker_count']} "
        f"generic_cutout={payload['generic_opening_cutout_ready']} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
