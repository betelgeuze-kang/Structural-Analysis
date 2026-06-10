#!/usr/bin/env python3
"""Build a productization receipt for typed MIDAS boundary entity ingest support."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from parse_mgt_section_material_properties import (
    parse_mgt_boundary_groups,
    parse_mgt_elastic_links,
    parse_mgt_story_eccentricity,
    parse_mgt_support_constraints,
)


SCHEMA_VERSION = "mgt-boundary-entity-support-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_boundary_entity_support_receipt.json"
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


def _parse_node_ids(mgt_text: str) -> set[int]:
    node_ids: set[int] = set()
    for row in _block_data_lines(mgt_text, "NODE"):
        head = row.split(",", 1)[0].strip()
        try:
            node_ids.add(int(float(head)))
        except ValueError:
            continue
    return node_ids


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _get(payload: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _example_constraint_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        node_ids = list(row.get("node_ids") or [])
        out.append(
            {
                "row_index": int(row.get("row_index") or 0),
                "node_count": int(row.get("node_count") or 0),
                "node_ids_head": node_ids[:12],
                "restraint_code": str(row.get("restraint_code") or ""),
                "restrained_dofs": list(row.get("restrained_dofs") or []),
                "group": str(row.get("group") or ""),
            }
        )
    return out


def _example_elastic_link_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            {
                "row_index": int(row.get("row_index") or 0),
                "id": int(row.get("id") or 0),
                "node_i": int(row.get("node_i") or 0),
                "node_j": int(row.get("node_j") or 0),
                "link_type": str(row.get("link_type") or ""),
                "angle_deg": float(row.get("angle_deg") or 0.0),
                "stiffness": row.get("stiffness") or {},
                "b_shear": row.get("b_shear"),
            }
        )
    return out


def _stiffness_summary(links: list[dict[str, Any]]) -> dict[str, Any]:
    maxima: list[float] = []
    nonzero: list[float] = []
    dof_counts: Counter[str] = Counter()
    for link in links:
        stiffness = link.get("stiffness")
        if not isinstance(stiffness, dict):
            continue
        for dof, value in stiffness.items():
            try:
                parsed = abs(float(value))
            except (TypeError, ValueError):
                continue
            maxima.append(parsed)
            if parsed > 0.0:
                nonzero.append(parsed)
                dof_counts[str(dof)] += 1
    return {
        "stiffness_abs_max": float(max(maxima) if maxima else 0.0),
        "stiffness_abs_min_nonzero": float(min(nonzero) if nonzero else 0.0),
        "nonzero_stiffness_dof_counts": {key: int(value) for key, value in sorted(dof_counts.items())},
    }


def build_mgt_boundary_entity_support_receipt(
    mgt_path: Path = DEFAULT_MGT,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
) -> dict[str, Any]:
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    node_ids = _parse_node_ids(text)
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    story_eccentricity = parse_mgt_story_eccentricity(text)
    boundary_groups = parse_mgt_boundary_groups(text)
    roundtrip = _load_json(roundtrip_json)

    constraint_node_refs = [int(node_id) for row in constraints for node_id in row.get("node_ids") or []]
    distinct_constraint_nodes = set(constraint_node_refs)
    link_node_refs = [
        int(node_id)
        for link in elastic_links
        for node_id in (link.get("node_i"), link.get("node_j"))
        if node_id is not None
    ]
    distinct_link_nodes = set(link_node_refs)
    unmatched_constraint_nodes = sorted(distinct_constraint_nodes - node_ids)
    unmatched_link_nodes = sorted(distinct_link_nodes - node_ids)
    restraint_code_counts = Counter(str(row.get("restraint_code") or "UNKNOWN") for row in constraints)
    link_type_counts = Counter(str(link.get("link_type") or "UNKNOWN") for link in elastic_links)
    typed_constraints_ready = bool(constraints and not unmatched_constraint_nodes)
    typed_links_ready = bool(elastic_links and not unmatched_link_nodes)
    story_ready = bool(story_eccentricity)
    roundtrip_constraint_nodes = int(_get(roundtrip, "parser", "constraint_summary", "support_node_count", default=0) or 0)
    roundtrip_coarsening = _get(roundtrip, "parser", "coarsening", default={})
    roundtrip_story_rows = _get(roundtrip, "model", "metadata", "story_eccentricity", default=[])
    roundtrip_boundary_groups = _get(roundtrip, "model", "metadata", "boundary_groups", default=[])

    status = "partial" if typed_constraints_ready and typed_links_ready and story_ready else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source": {
            "path": str(mgt_path),
            "sha256": _sha256(mgt_path),
            "size_bytes": int(mgt_path.stat().st_size),
            "source_family": "midas_mgt",
            "blocks": ["*CONSTRAINT", "*ELASTICLINK", "*STORY-ECCEN", "*BNDR-GROUP"],
            "provenance": "repo_benchmark_bridge",
        },
        "summary": {
            "mgt_node_count": int(len(node_ids)),
            "support_constraint_row_count": int(len(constraints)),
            "support_constraint_node_ref_count": int(len(constraint_node_refs)),
            "distinct_support_constraint_node_count": int(len(distinct_constraint_nodes)),
            "unmatched_support_constraint_node_count": int(len(unmatched_constraint_nodes)),
            "restraint_code_counts": {key: int(value) for key, value in sorted(restraint_code_counts.items())},
            "elastic_link_row_count": int(len(elastic_links)),
            "elastic_link_node_ref_count": int(len(link_node_refs)),
            "distinct_elastic_link_node_count": int(len(distinct_link_nodes)),
            "unmatched_elastic_link_node_count": int(len(unmatched_link_nodes)),
            "elastic_link_type_counts": {key: int(value) for key, value in sorted(link_type_counts.items())},
            "boundary_group_count": int(len(boundary_groups)),
            "story_eccentricity_present": story_ready,
            **_stiffness_summary(elastic_links),
        },
        "story_eccentricity": story_eccentricity,
        "boundary_groups": boundary_groups,
        "support": {
            "typed_mgt_support_constraint_parser_ready": bool(constraints),
            "support_constraint_node_refs_match_mgt_nodes": bool(not unmatched_constraint_nodes),
            "canonical_support_constraint_entity_ready": typed_constraints_ready,
            "typed_mgt_elastic_link_parser_ready": bool(elastic_links),
            "elastic_link_node_refs_match_mgt_nodes": bool(not unmatched_link_nodes),
            "canonical_elastic_link_entity_ready": typed_links_ready,
            "typed_mgt_story_eccentricity_parser_ready": story_ready,
            "typed_mgt_boundary_group_parser_ready": bool(boundary_groups),
            "roundtrip_constraint_summary_ready": bool(roundtrip_constraint_nodes == len(distinct_constraint_nodes)),
            "roundtrip_rigid_like_elastic_link_coarsening_ready": bool(
                isinstance(roundtrip_coarsening, dict)
                and roundtrip_coarsening.get("applied")
                and int(roundtrip_coarsening.get("elastic_link_count") or 0) == len(elastic_links)
            ),
            "roundtrip_story_eccentricity_token_preserved": bool(isinstance(roundtrip_story_rows, list) and roundtrip_story_rows),
            "roundtrip_boundary_group_token_preserved": bool(
                isinstance(roundtrip_boundary_groups, list) and roundtrip_boundary_groups
            ),
            "solver_uses_authored_support_restraint_masks": False,
            "solver_assembles_finite_elastic_link_springs": False,
            "solver_applies_story_eccentricity_load_generation": False,
        },
        "consuming_artifacts": {
            "roundtrip_json": str(roundtrip_json),
            "roundtrip_constraint_support_node_count": roundtrip_constraint_nodes,
            "roundtrip_coarsening": roundtrip_coarsening if isinstance(roundtrip_coarsening, dict) else {},
        },
        "claim_boundary": {
            "closed": [
                "real MGT *CONSTRAINT rows are parsed into typed node restraint entities",
                "real MGT *ELASTICLINK GEN rows are parsed into typed two-node link entities with six stiffness values",
                "real MGT *STORY-ECCEN is parsed into typed seismic/wind eccentricity settings",
                "constraint and elastic-link node references are verified against *NODE ids",
                "roundtrip parser preserves support summary and applies rigid-like elastic-link coarsening metadata",
            ],
            "not_closed": [
                "current sparse solver harnesses still use component base-node auto-restraints instead of authored support masks",
                "finite elastic-link spring elements are not assembled into the global 6-DOF tangent",
                "story eccentricity settings are not yet consumed by seismic/wind load generation or dynamic analysis",
            ],
        },
        "unmatched_support_constraint_node_ids_head": unmatched_constraint_nodes[:20],
        "unmatched_elastic_link_node_ids_head": unmatched_link_nodes[:20],
        "example_constraint_rows": _example_constraint_rows(constraints),
        "example_elastic_link_rows": _example_elastic_link_rows(elastic_links),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_mgt_boundary_entity_support_receipt(
        mgt_path=args.mgt_path,
        roundtrip_json=args.roundtrip_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "mgt-boundary-entity-support: "
        f"status={payload['status']} "
        f"constraints={payload['summary']['support_constraint_row_count']} "
        f"support_nodes={payload['summary']['distinct_support_constraint_node_count']} "
        f"elastic_links={payload['summary']['elastic_link_row_count']} "
        f"story_eccentricity={payload['summary']['story_eccentricity_present']}"
    )
    return 0 if payload["status"] in {"ready", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
