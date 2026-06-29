#!/usr/bin/env python3
"""Build the non-promoting G1 support/elastic-link reconciliation audit."""

from __future__ import annotations

import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
from math import dist
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from parse_mgt_section_material_properties import (  # noqa: E402
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt")
DEFAULT_NEAR_NULL = PRODUCTIZATION / "g1_null_space_mode_audit.local.json"
DEFAULT_SUPPORT_ENTITY = PRODUCTIZATION / "mgt_boundary_entity_support_receipt.json"
DEFAULT_SUPPORT_SPRING = PRODUCTIZATION / "mgt_boundary_spring_tangent_receipt.json"
DEFAULT_PREFLIGHT = Path(".betelgeuze/f2g_f2h_surface_preflight.local.json")
DEFAULT_OUTPUT = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
SCHEMA_VERSION = "g1-support-elastic-link-reconciliation-audit.v1"
DOF_MAP = {
    "DX": "UX",
    "DY": "UY",
    "DZ": "UZ",
    "RX": "RX",
    "RY": "RY",
    "RZ": "RZ",
}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _parse_nodes(mgt_text: str) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    for row in _block_data_lines(mgt_text, "NODE"):
        parts = [part.strip() for part in row.split(",")]
        if len(parts) < 4:
            continue
        try:
            nodes[int(float(parts[0]))] = (float(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError:
            continue
    return nodes


def _support_maps(constraints: list[dict[str, Any]]) -> tuple[set[int], dict[int, set[str]]]:
    support_nodes: set[int] = set()
    restrained_by_node: dict[int, set[str]] = {}
    for row in constraints:
        mask = row.get("restraint_mask")
        if not isinstance(mask, dict):
            continue
        restrained = {DOF_MAP.get(str(key).upper(), str(key).upper()) for key, value in mask.items() if value}
        for raw_node_id in row.get("node_ids") or []:
            node_id = int(raw_node_id)
            support_nodes.add(node_id)
            restrained_by_node.setdefault(node_id, set()).update(restrained)
    return support_nodes, restrained_by_node


def _link_maps(links: list[dict[str, Any]]) -> tuple[dict[int, set[int]], dict[int, int], dict[str, Any]]:
    graph: dict[int, set[int]] = {}
    degree: Counter[int] = Counter()
    stiffness_values: list[float] = []
    unmatched_rows = 0
    for link in links:
        try:
            node_i = int(link["node_i"])
            node_j = int(link["node_j"])
        except Exception:
            unmatched_rows += 1
            continue
        graph.setdefault(node_i, set()).add(node_j)
        graph.setdefault(node_j, set()).add(node_i)
        degree[node_i] += 1
        degree[node_j] += 1
        stiffness = link.get("stiffness")
        if isinstance(stiffness, dict):
            for value in stiffness.values():
                try:
                    parsed = abs(float(value))
                except (TypeError, ValueError):
                    continue
                if parsed > 0.0:
                    stiffness_values.append(parsed)
    return graph, {node_id: int(count) for node_id, count in degree.items()}, {
        "elastic_link_row_count": int(len(links)),
        "malformed_link_row_count": int(unmatched_rows),
        "elastic_link_node_count": int(len(degree)),
        "stiffness_abs_min_nonzero": float(min(stiffness_values) if stiffness_values else 0.0),
        "stiffness_abs_max": float(max(stiffness_values) if stiffness_values else 0.0),
    }


def _hops_to_support(start: int, graph: dict[int, set[int]], support_nodes: set[int], *, limit: int = 12) -> int | None:
    if start in support_nodes:
        return 0
    if start not in graph:
        return None
    seen = {start}
    queue: deque[tuple[int, int]] = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= limit:
            continue
        for nxt in graph.get(node, set()):
            if nxt in seen:
                continue
            if nxt in support_nodes:
                return depth + 1
            seen.add(nxt)
            queue.append((nxt, depth + 1))
    return None


def _distance_to_support(
    node_id: int,
    nodes: dict[int, tuple[float, float, float]],
    support_nodes: set[int],
) -> float | None:
    point = nodes.get(node_id)
    if point is None or not support_nodes:
        return None
    best: float | None = None
    for support_id in support_nodes:
        support_point = nodes.get(support_id)
        if support_point is None:
            continue
        value = float(dist(point, support_point))
        if best is None or value < best:
            best = value
    return best


def _dominant_rows(
    near_null: dict[str, Any],
    *,
    nodes: dict[int, tuple[float, float, float]],
    support_nodes: set[int],
    restrained_by_node: dict[int, set[str]],
    link_graph: dict[int, set[int]],
    link_degree: dict[int, int],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for mode in near_null.get("mode_rows") or []:
        if not isinstance(mode, dict):
            continue
        mode_index = int(mode.get("mode_index", len(out)))
        for rank, row in enumerate(mode.get("dominant_nodes") or [], start=1):
            if not isinstance(row, dict):
                continue
            node_id = int(row.get("node_id") or 0)
            dof = str(row.get("dof") or "").upper()
            key = (mode_index, node_id, dof)
            if node_id <= 0 or not dof or key in seen:
                continue
            seen.add(key)
            restrained = restrained_by_node.get(node_id, set())
            hops = _hops_to_support(node_id, link_graph, support_nodes)
            distance_m = _distance_to_support(node_id, nodes, support_nodes)
            out.append(
                {
                    "mode_index": mode_index,
                    "rank_in_mode": int(rank),
                    "node_id": node_id,
                    "dof": dof,
                    "amplitude": float(row.get("amplitude") or 0.0),
                    "diagnosis": str(mode.get("diagnosis") or ""),
                    "node_in_mgt": node_id in nodes,
                    "support_member": node_id in support_nodes,
                    "dof_restrained_by_authored_support": dof in restrained,
                    "constrained_free_state": "constrained" if dof in restrained else "free",
                    "authored_restrained_dofs": sorted(restrained),
                    "elastic_link_degree": int(link_degree.get(node_id, 0)),
                    "elastic_link_hops_to_support": hops,
                    "elastic_link_support_reachable": hops is not None,
                    "nearest_support_distance_m": distance_m,
                }
            )
    return out


def _ranked_findings(
    rows: list[dict[str, Any]],
    *,
    support_spring: dict[str, Any],
    link_stats: dict[str, Any],
    near_null: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    total = max(len(rows), 1)
    support_hits = sum(1 for row in rows if row["support_member"])
    link_hits = sum(1 for row in rows if row["elastic_link_degree"] > 0)
    reachable = sum(1 for row in rows if row["elastic_link_support_reachable"])
    if support_hits == 0:
        findings.append(
            {
                "rank": 1,
                "finding_id": "dominant_near_null_dofs_are_not_authored_support_nodes",
                "severity": "high",
                "evidence": f"0/{total} dominant near-null DOF rows are on authored support nodes.",
                "interpretation": "Weak restraint or global connectivity, not a direct missing support row, is the leading audit hypothesis.",
            }
        )
    if link_hits == 0:
        findings.append(
            {
                "rank": 2,
                "finding_id": "dominant_near_null_dofs_have_no_direct_elastic_link_degree",
                "severity": "high",
                "evidence": f"0/{total} dominant near-null DOF rows touch an elastic-link endpoint.",
                "interpretation": "Elastic links are unlikely to restrain the dominant modes directly; inspect graph/load-path transfer.",
            }
        )
    if reachable == 0:
        findings.append(
            {
                "rank": 3,
                "finding_id": "dominant_near_null_dofs_not_reachable_to_support_via_elastic_links",
                "severity": "medium",
                "evidence": f"0/{total} dominant rows reach an authored support through the elastic-link graph.",
                "interpretation": "The elastic-link graph alone does not explain support transfer for the near-null modes.",
            }
        )
    if support_spring.get("support", {}).get("global_frame_shell_tangent_integration_ready") is False:
        findings.append(
            {
                "rank": 4,
                "finding_id": "boundary_spring_context_not_full_global_tangent",
                "severity": "medium",
                "evidence": "Boundary spring tangent receipt is ready for the boundary subsystem but explicitly not global frame/shell integration.",
                "interpretation": "F2h should not treat boundary subsystem readiness as full nonlinear solver closure.",
            }
        )
    mode_count = int(near_null.get("singularity_indicators", {}).get("near_null_mode_count") or 0)
    if mode_count:
        findings.append(
            {
                "rank": 5,
                "finding_id": "near_null_packet_is_distributed_translation_rotation",
                "severity": "medium",
                "evidence": f"near_null_mode_count={mode_count}, link_nodes={link_stats.get('elastic_link_node_count', 0)}.",
                "interpretation": "The audit supports weak-restraint/geometric-softening investigation over single DOF pinning.",
            }
        )
    return sorted(findings, key=lambda item: int(item["rank"]))


def build_audit(
    *,
    repo_root: Path = REPO_ROOT,
    mgt_path: Path = DEFAULT_MGT,
    near_null_path: Path = DEFAULT_NEAR_NULL,
    support_entity_path: Path = DEFAULT_SUPPORT_ENTITY,
    support_spring_path: Path = DEFAULT_SUPPORT_SPRING,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> dict[str, Any]:
    resolved_mgt = mgt_path if mgt_path.is_absolute() else repo_root / mgt_path
    resolved_near_null = near_null_path if near_null_path.is_absolute() else repo_root / near_null_path
    resolved_entity = support_entity_path if support_entity_path.is_absolute() else repo_root / support_entity_path
    resolved_spring = support_spring_path if support_spring_path.is_absolute() else repo_root / support_spring_path
    resolved_preflight = preflight_path if preflight_path.is_absolute() else repo_root / preflight_path

    blockers: list[str] = []
    for label, path in (
        ("mgt", resolved_mgt),
        ("near_null", resolved_near_null),
        ("support_entity", resolved_entity),
        ("support_spring", resolved_spring),
    ):
        if not path.is_file():
            blockers.append(f"missing_{label}:{path}")
    if blockers:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": _git_head(repo_root),
            "status": "blocked",
            "reason_code": "ERR_REQUIRED_INPUTS_MISSING",
            "promotes_g1_closure": False,
            "claim_boundary": "non_promoting_support_elastic_link_reconciliation_audit_only",
            "blockers": blockers,
            "dominant_dof_rows": [],
        }

    mgt_text = resolved_mgt.read_text(encoding="utf-8", errors="ignore")
    near_null = _load_json(resolved_near_null)
    support_entity = _load_json(resolved_entity)
    support_spring = _load_json(resolved_spring)
    preflight = _load_json(resolved_preflight)
    nodes = _parse_nodes(mgt_text)
    constraints = parse_mgt_support_constraints(mgt_text)
    links = parse_mgt_elastic_links(mgt_text)
    support_nodes, restrained_by_node = _support_maps(constraints)
    link_graph, link_degree, link_stats = _link_maps(links)
    dominant = _dominant_rows(
        near_null,
        nodes=nodes,
        support_nodes=support_nodes,
        restrained_by_node=restrained_by_node,
        link_graph=link_graph,
        link_degree=link_degree,
    )
    findings = _ranked_findings(
        dominant,
        support_spring=support_spring,
        link_stats=link_stats,
        near_null=near_null,
    )
    direct_support_hits = sum(1 for row in dominant if row["support_member"])
    direct_link_hits = sum(1 for row in dominant if row["elastic_link_degree"] > 0)
    reachable_hits = sum(1 for row in dominant if row["elastic_link_support_reachable"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(repo_root),
        "status": "ready" if dominant else "blocked",
        "reason_code": "PASS" if dominant else "ERR_NEAR_NULL_DOMINANT_ROWS_MISSING",
        "promotes_g1_closure": False,
        "claim_boundary": "non_promoting_support_elastic_link_reconciliation_audit_only",
        "source_inputs": {
            "mgt": {"path": str(resolved_mgt), "sha256": _sha256(resolved_mgt)},
            "near_null_packet": {"path": str(resolved_near_null), "sha256": _sha256(resolved_near_null)},
            "support_entity_receipt": {"path": str(resolved_entity), "sha256": _sha256(resolved_entity)},
            "support_spring_receipt": {"path": str(resolved_spring), "sha256": _sha256(resolved_spring)},
            "preflight": {"path": str(resolved_preflight), "status": preflight.get("status", "missing")},
        },
        "summary": {
            "dominant_dof_row_count": int(len(dominant)),
            "mode_count": int(len({row["mode_index"] for row in dominant})),
            "direct_support_member_count": int(direct_support_hits),
            "direct_elastic_link_endpoint_count": int(direct_link_hits),
            "elastic_link_reachable_to_support_count": int(reachable_hits),
            "support_node_count": int(len(support_nodes)),
            "elastic_link_node_count": int(link_stats["elastic_link_node_count"]),
            "support_link_direct_intersection_count": int(
                support_spring.get("summary", {}).get("direct_support_link_node_intersection_count", 0) or 0
            ),
            "global_frame_shell_tangent_integration_ready": bool(
                support_spring.get("support", {}).get("global_frame_shell_tangent_integration_ready", False)
            ),
        },
        "near_null_context": {
            "load_scale": near_null.get("load_scale"),
            "frame_service_tangent_source": near_null.get("frame_service_tangent_source"),
            "near_null_mode_count": near_null.get("singularity_indicators", {}).get("near_null_mode_count"),
            "assembled_tangent": near_null.get("assembled_tangent", {}),
        },
        "support_context": {
            "entity_status": support_entity.get("status"),
            "spring_status": support_spring.get("status"),
            "support_entity_summary": support_entity.get("summary", {}),
            "spring_tangent_summary": support_spring.get("summary", {}),
            "link_stats_from_mgt": link_stats,
        },
        "dominant_dof_rows": dominant,
        "ranked_findings": findings,
        "next_actions": [
            "review weak-restraint/geometric-softening hypothesis against full structural graph",
            "only then run non-promoting F2h lightweight continuation",
        ],
        "disallowed_promotions": [
            "no_pinning_applied_by_this_audit",
            "no_G1_claim",
            "no_0p656_regeneration_claim",
            "no_boundary_subsystem_receipt_as_full_global_tangent_closure",
        ],
        "blockers": [] if dominant else ["near_null_dominant_rows_missing"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--near-null-json", type=Path, default=DEFAULT_NEAR_NULL)
    parser.add_argument("--support-entity-json", type=Path, default=DEFAULT_SUPPORT_ENTITY)
    parser.add_argument("--support-spring-json", type=Path, default=DEFAULT_SUPPORT_SPRING)
    parser.add_argument("--preflight-json", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_audit(
        repo_root=args.repo_root,
        mgt_path=args.mgt_path,
        near_null_path=args.near_null_json,
        support_entity_path=args.support_entity_json,
        support_spring_path=args.support_spring_json,
        preflight_path=args.preflight_json,
    )
    output = args.output_json if args.output_json.is_absolute() else args.repo_root / args.output_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "g1-support-elastic-link-reconciliation-audit: "
        f"status={payload['status']} "
        f"dominant_rows={len(payload.get('dominant_dof_rows') or [])} "
        f"findings={len(payload.get('ranked_findings') or [])}"
    )
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
