#!/usr/bin/env python3
"""Build a productization receipt for typed MIDAS *OFFSET ingest support."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from parse_mgt_section_material_properties import parse_mgt_beam_end_offsets


SCHEMA_VERSION = "mgt-beam-offset-support-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_beam_offset_support_receipt.json"
)
DEFAULT_FRAME_SOLVE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_full_frame_6dof_sparse_equilibrium.json"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _block_data_lines(mgt_text: str, tag: str) -> list[str]:
    rows: list[str] = []
    in_block = False
    for raw in mgt_text.splitlines():
        stripped = raw.strip()
        if not in_block:
            if stripped.upper().startswith(f"*{tag.upper()}"):
                in_block = True
            continue
        if stripped.startswith("*"):
            break
        if stripped and not stripped.startswith(";"):
            rows.append(stripped)
    return rows


def _parse_element_ids(mgt_text: str) -> set[int]:
    element_ids: set[int] = set()
    for row in _block_data_lines(mgt_text, "ELEMENT"):
        head = row.split(",", 1)[0].strip()
        try:
            element_ids.add(int(float(head)))
        except ValueError:
            continue
    return element_ids


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _abs_values(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in rows:
        for value in row.get("offset_values_m") or []:
            try:
                values.append(abs(float(value)))
            except (TypeError, ValueError):
                continue
    return values


def _component_abs_max(rows: list[dict[str, Any]]) -> dict[str, float]:
    maxima: dict[str, float] = {}
    for row in rows:
        prefix = str(row.get("coordinate_system") or "UNKNOWN").lower()
        for end_name in ("i", "j"):
            offset = row.get(f"{end_name}_offset_m")
            if not isinstance(offset, dict):
                continue
            for axis, value in offset.items():
                key = f"{prefix}_{end_name}_{axis}"
                maxima[key] = max(float(maxima.get(key, 0.0)), abs(float(value)))
    return {key: float(value) for key, value in sorted(maxima.items())}


def _nonzero_component_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        prefix = str(row.get("coordinate_system") or "UNKNOWN").lower()
        for end_name in ("i", "j"):
            offset = row.get(f"{end_name}_offset_m")
            if not isinstance(offset, dict):
                continue
            for axis, value in offset.items():
                if abs(float(value)) > 1.0e-12:
                    counts[f"{prefix}_{end_name}_{axis}"] += 1
    return {key: int(value) for key, value in sorted(counts.items())}


def _top_offset_rows(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: max([abs(float(value)) for value in row.get("offset_values_m") or [0.0]]),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for row in ranked[:limit]:
        out.append(
            {
                "row_index": int(row.get("row_index") or 0),
                "element_ids": list(row.get("element_ids") or []),
                "coordinate_system": str(row.get("coordinate_system") or ""),
                "i_offset_m": row.get("i_offset_m") or {},
                "j_offset_m": row.get("j_offset_m") or {},
                "max_abs_offset_m": float(max(abs(float(value)) for value in row.get("offset_values_m") or [0.0])),
            }
        )
    return out


def build_mgt_beam_offset_support_receipt(
    mgt_path: Path = DEFAULT_MGT,
    frame_solve_json: Path = DEFAULT_FRAME_SOLVE,
) -> dict[str, Any]:
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    offsets = parse_mgt_beam_end_offsets(text)
    frame_solve = _load_json(frame_solve_json)
    frame_offset_support = (
        frame_solve.get("beam_end_offset_support")
        if isinstance(frame_solve.get("beam_end_offset_support"), dict)
        else {}
    )
    element_ids = _parse_element_ids(text)
    flattened_ids = [int(element_id) for row in offsets for element_id in row.get("element_ids") or []]
    distinct_offset_ids = set(flattened_ids)
    unmatched = sorted(element_id for element_id in distinct_offset_ids if element_id not in element_ids)
    abs_values = _abs_values(offsets)
    type_counts = Counter(str(row.get("coordinate_system") or "UNKNOWN") for row in offsets)
    typed_offset_entity_ready = bool(offsets and not unmatched)
    solver_rigid_end_offset_tangent_ready = bool(
        frame_offset_support.get("rigid_end_offset_tangent_ready")
    )
    solver_geometric_stiffness_offset_ready = bool(
        frame_offset_support.get("geometric_tangent_uses_offset_length")
    )
    status = "partial" if typed_offset_entity_ready else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source": {
            "path": str(mgt_path),
            "sha256": _sha256(mgt_path),
            "size_bytes": int(mgt_path.stat().st_size),
            "source_family": "midas_mgt",
            "block": "*OFFSET",
            "provenance": "repo_benchmark_bridge",
        },
        "summary": {
            "offset_row_count": int(len(offsets)),
            "offset_element_ref_count": int(len(flattened_ids)),
            "distinct_offset_element_count": int(len(distinct_offset_ids)),
            "mgt_element_count": int(len(element_ids)),
            "unmatched_offset_element_count": int(len(unmatched)),
            "duplicate_offset_assignment_count": int(len(flattened_ids) - len(distinct_offset_ids)),
            "coordinate_system_counts": {str(key): int(value) for key, value in sorted(type_counts.items())},
            "max_abs_offset_m": float(max(abs_values) if abs_values else 0.0),
            "nonzero_component_counts": _nonzero_component_counts(offsets),
            "component_abs_max_m": _component_abs_max(offsets),
        },
        "support": {
            "typed_mgt_offset_parser_ready": bool(offsets),
            "offset_element_refs_match_mgt_elements": bool(not unmatched),
            "canonical_runtime_entity_ready": typed_offset_entity_ready,
            "global_xyz_offsets_supported": bool(type_counts.get("GLOBAL", 0) > 0),
            "element_local_yz_offsets_supported": bool(type_counts.get("ELEMENT", 0) > 0),
            "solver_rigid_end_offset_tangent_ready": solver_rigid_end_offset_tangent_ready,
            "solver_geometric_stiffness_offset_ready": solver_geometric_stiffness_offset_ready,
            "frame_offset_applied_element_count": int(frame_offset_support.get("applied_element_count") or 0),
            "load_eccentricity_moments_applied": bool(
                frame_offset_support.get("load_eccentricity_moments_applied")
            ),
            "roundtrip_preserves_offset_metadata": False,
        },
        "consuming_artifacts": {
            "frame_solve_json": str(frame_solve_json),
            "frame_solve_status": frame_solve.get("status"),
        },
        "claim_boundary": {
            "closed": [
                "real MGT *OFFSET rows are parsed into typed element end-offset entities",
                "receipt records source SHA256 and verifies offset element references against *ELEMENT ids",
                *(
                    [
                        "6-DOF frame elastic and geometric tangent assembly consumes GLOBAL offsets through rigid-end transformation"
                    ]
                    if solver_rigid_end_offset_tangent_ready
                    else []
                ),
            ],
            "not_closed": [
                "ELEMENT local-yz offset rows are still queued for solver support",
                "roundtrip export and non-frame shell/surface eccentricity semantics have not consumed offsets yet",
            ],
        },
        "unmatched_offset_element_ids_head": unmatched[:20],
        "example_rows": _top_offset_rows(offsets),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--frame-solve-json", type=Path, default=DEFAULT_FRAME_SOLVE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_mgt_beam_offset_support_receipt(
        mgt_path=args.mgt_path,
        frame_solve_json=args.frame_solve_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "mgt-beam-offset-support: "
        f"{payload['status']} rows={payload['summary']['offset_row_count']} "
        f"max_abs={payload['summary']['max_abs_offset_m']:.6g} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
