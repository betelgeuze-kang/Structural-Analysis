#!/usr/bin/env python3
"""Build a receipt for MIDAS *ELEMENT local-axis and opening semantics."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from parse_mgt_section_material_properties import (
    parse_mgt_element_local_axis_rows,
    scan_mgt_opening_source_markers,
)


SCHEMA_VERSION = "mgt-element-local-axis-opening-semantics-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
DEFAULT_FRAME_SOLVE = PRODUCTIZATION / "mgt_full_frame_6dof_sparse_equilibrium.json"
DEFAULT_OUT = PRODUCTIZATION / "mgt_element_local_axis_opening_semantics_receipt.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _row_head(rows: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            {
                "row_index": int(row.get("row_index") or 0),
                "element_id": int(row.get("element_id") or 0),
                "type": str(row.get("type") or ""),
                "family": str(row.get("family") or ""),
                "angle_deg": float(row.get("angle_deg") or 0.0),
                "lcaxis_code": int(row.get("lcaxis_code") or 0),
                "lcaxis_source": str(row.get("lcaxis_source") or ""),
                "raw": str(row.get("raw") or "")[:180],
            }
        )
    return out


def build_mgt_element_local_axis_opening_semantics_receipt(
    *,
    mgt_path: Path = DEFAULT_MGT,
    frame_solve_json: Path = DEFAULT_FRAME_SOLVE,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    axis_rows = parse_mgt_element_local_axis_rows(text)
    opening_scan = scan_mgt_opening_source_markers(text)
    frame_solve = _load(frame_solve_json)
    frame_axis_support = (
        frame_solve.get("frame_local_axis_support")
        if isinstance(frame_solve.get("frame_local_axis_support"), dict)
        else {}
    )

    line_rows = [row for row in axis_rows if row.get("family") == "line"]
    surface_rows = [row for row in axis_rows if row.get("family") == "surface"]
    nonzero_line_rows = [row for row in line_rows if abs(float(row.get("angle_deg") or 0.0)) > 1.0e-12]
    nonzero_surface_rows = [row for row in surface_rows if int(row.get("lcaxis_code") or 0) != 0]
    line_type_counts = Counter(str(row.get("type") or "UNKNOWN") for row in line_rows)
    surface_type_counts = Counter(str(row.get("type") or "UNKNOWN") for row in surface_rows)
    lcaxis_source_counts = Counter(str(row.get("lcaxis_source") or "missing") for row in surface_rows)

    frame_parser_ready = bool(line_rows and all(bool(row.get("angle_token_present")) for row in line_rows))
    surface_parser_ready = bool(
        surface_rows
        and all(str(row.get("lcaxis_source") or "missing") != "missing" for row in surface_rows)
    )
    frame_solver_ready = bool(
        frame_axis_support.get("frame_angle_rows_consumed")
        and frame_axis_support.get("solver_local_axis_roll_transform_ready")
        and int(frame_axis_support.get("frame_nonzero_angle_element_count") or 0) > 0
    )
    opening_rows_present = bool(int(opening_scan.get("opening_marker_row_count") or 0) > 0)
    current_source_opening_noop_ready = not opening_rows_present
    generic_opening_cutout_ready = False
    opening_runtime_ready = current_source_opening_noop_ready or generic_opening_cutout_ready

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if frame_parser_ready and frame_solver_ready and opening_runtime_ready else "blocked",
        "source": {
            "path": str(mgt_path),
            "sha256": _sha256(mgt_path),
            "size_bytes": int(mgt_path.stat().st_size),
            "source_family": "midas_mgt",
            "block": "*ELEMENT",
            "provenance": "repo_benchmark_bridge",
        },
        "summary": {
            "local_axis_row_count": int(len(axis_rows)),
            "line_local_axis_row_count": int(len(line_rows)),
            "line_nonzero_angle_row_count": int(len(nonzero_line_rows)),
            "line_max_abs_angle_deg": float(
                max((abs(float(row.get("angle_deg") or 0.0)) for row in line_rows), default=0.0)
            ),
            "surface_lcaxis_row_count": int(len(surface_rows)),
            "surface_nonzero_lcaxis_row_count": int(len(nonzero_surface_rows)),
            "line_type_counts": {str(k): int(v) for k, v in sorted(line_type_counts.items())},
            "surface_type_counts": {str(k): int(v) for k, v in sorted(surface_type_counts.items())},
            "surface_lcaxis_source_counts": {str(k): int(v) for k, v in sorted(lcaxis_source_counts.items())},
            "opening_marker_block_count": int(opening_scan.get("opening_marker_block_count") or 0),
            "opening_marker_row_count": int(opening_scan.get("opening_marker_row_count") or 0),
            "generic_opening_cutout_source_row_count": int(opening_scan.get("opening_marker_row_count") or 0),
        },
        "support": {
            "frame_angle_parser_ready": frame_parser_ready,
            "frame_angle_source_has_nonzero_rows": bool(nonzero_line_rows),
            "frame_angle_roundtrip_npz_ready": bool(frame_axis_support.get("elem_angle_array_present")),
            "frame_angle_solver_consumption_ready": frame_solver_ready,
            "surface_lcaxis_parser_ready": surface_parser_ready,
            "surface_lcaxis_source_all_default": bool(surface_rows and not nonzero_surface_rows),
            "opening_source_inventory_ready": True,
            "opening_source_rows_present": opening_rows_present,
            "current_source_opening_absence_policy_ready": current_source_opening_noop_ready,
            "current_source_opening_noop_runtime_ready": current_source_opening_noop_ready,
            "opening_runtime_semantics_ready": opening_runtime_ready,
            "generic_opening_cutout_runtime_semantics_ready": generic_opening_cutout_ready,
        },
        "solver_consumption": {
            "frame_solve_json": str(frame_solve_json),
            "frame_solve_status": frame_solve.get("status"),
            "frame_local_axis_support": frame_axis_support,
        },
        "opening_source_scan": opening_scan,
        "example_rows": {
            "nonzero_frame_angle_rows_head": _row_head(nonzero_line_rows),
            "surface_lcaxis_rows_head": _row_head(surface_rows),
        },
        "claim_boundary": {
            "closed": [
                "MGT *ELEMENT frame ANGLE rows are parsed and exported into roundtrip NPZ",
                "6-DOF frame elastic and geometric tangent assembly consumes nonzero frame ANGLE as local y/z roll",
                "PLATE compact local-axis option tokens are inventoried; current source rows are all default zero",
                "benchmark bridge MGT contains no opening/hole/void rows, so current-source opening semantics are a checked no-op instead of an uninspected solver omission",
            ],
            "not_closed": [
                "generic opening/cutout runtime meshing is not claimed because no opening/hole/void source rows are present in the benchmark bridge MGT",
                "surface shell local-axis LCAXIS has only default-zero source coverage in this MGT",
                "diaphragm/member release and full-load nonlinear frame-shell semantics remain outside this receipt",
            ],
        },
        "blockers": []
        if frame_parser_ready and frame_solver_ready and opening_runtime_ready
        else ["frame_local_axis_or_source_opening_semantics_not_ready"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--frame-solve-json", type=Path, default=DEFAULT_FRAME_SOLVE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build_mgt_element_local_axis_opening_semantics_receipt(
        mgt_path=args.mgt,
        frame_solve_json=args.frame_solve_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"mgt-local-axis-opening: {payload['status']} "
        f"nonzero_frame_angles={payload['summary']['line_nonzero_angle_row_count']} "
        f"openings={payload['summary']['opening_marker_row_count']}"
    )


if __name__ == "__main__":
    main()
