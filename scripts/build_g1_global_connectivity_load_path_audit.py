#!/usr/bin/env python3
"""Build the non-promoting G1 full-structural connectivity/load-path audit."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from parse_mgt_section_material_properties import (  # noqa: E402
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt")
DEFAULT_F2G_AUDIT = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
DEFAULT_OUTPUT = PRODUCTIZATION / "g1_global_connectivity_load_path_audit.json"

SCHEMA_VERSION = "g1-global-connectivity-load-path-audit.v1"
REUSE_POLICY = "non_promoting_full_structural_graph_audit_from_existing_f2g_dominant_rows"

LINE_ELEMENT_TYPES = {"BEAM", "TRUSS", "TENSTR", "COMPTR"}
PLANAR_ELEMENT_TYPES = {"PLATE", "WALL", "PLANE"}
SOLID_ELEMENT_TYPES = {"SOLID"}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
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


def _split_csv(line: str) -> list[str]:
    return [part.strip() for part in line.split(",")]


def _parse_int_token(token: Any) -> int | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    if abs(value - int(value)) <= 1.0e-9:
        return int(value)
    return None


def _parse_nodes(mgt_text: str) -> set[int]:
    nodes: set[int] = set()
    for row in _block_data_lines(mgt_text, "NODE"):
        parts = _split_csv(row)
        if len(parts) < 4:
            continue
        node_id = _parse_int_token(parts[0])
        if node_id is not None and node_id > 0:
            nodes.add(int(node_id))
    return nodes


def _candidate_node_tokens(parts: list[str], element_type: str) -> list[str]:
    if element_type in LINE_ELEMENT_TYPES:
        return parts[4:6]
    if element_type in PLANAR_ELEMENT_TYPES:
        return parts[4:8]
    if element_type in SOLID_ELEMENT_TYPES:
        return parts[4:12]
    return parts[4:]


def _element_family(element_type: str) -> str:
    if element_type in LINE_ELEMENT_TYPES:
        return "line"
    if element_type in PLANAR_ELEMENT_TYPES:
        return "surface"
    if element_type in SOLID_ELEMENT_TYPES:
        return "solid"
    return "unknown"


def _parse_elements(mgt_text: str, node_ids: set[int]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for row_index, line in enumerate(_block_data_lines(mgt_text, "ELEMENT"), start=1):
        parts = _split_csv(line)
        if len(parts) < 6:
            continue
        element_id = _parse_int_token(parts[0])
        if element_id is None:
            continue
        element_type = str(parts[1]).strip().upper()
        connectivity: list[int] = []
        for token in _candidate_node_tokens(parts, element_type):
            node_id = _parse_int_token(token)
            if node_id is None or node_id <= 0 or node_id not in node_ids:
                continue
            if node_id not in connectivity:
                connectivity.append(int(node_id))
        if len(connectivity) < 2:
            continue
        elements.append(
            {
                "row_index": int(row_index),
                "element_id": int(element_id),
                "type": element_type,
                "family": _element_family(element_type),
                "node_ids": connectivity,
                "node_count": int(len(connectivity)),
            }
        )
    return elements


def _support_nodes(constraints: list[dict[str, Any]]) -> set[int]:
    out: set[int] = set()
    for row in constraints:
        for raw_node_id in row.get("node_ids") or []:
            node_id = _parse_int_token(raw_node_id)
            if node_id is not None and node_id > 0:
                out.add(int(node_id))
    return out


def _elastic_link_graph(links: list[dict[str, Any]]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = {}
    for link in links:
        node_i = _parse_int_token(link.get("node_i"))
        node_j = _parse_int_token(link.get("node_j"))
        if node_i is None or node_j is None or node_i <= 0 or node_j <= 0:
            continue
        graph.setdefault(int(node_i), set()).add(int(node_j))
        graph.setdefault(int(node_j), set()).add(int(node_i))
    return graph


def _element_graph(
    elements: list[dict[str, Any]],
) -> tuple[dict[int, set[int]], dict[int, list[dict[str, Any]]]]:
    graph: dict[int, set[int]] = {}
    incident: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for element in elements:
        node_ids = [int(node_id) for node_id in element.get("node_ids") or []]
        for node_id in node_ids:
            graph.setdefault(node_id, set())
            incident[node_id].append(element)
        for node_i, node_j in combinations(node_ids, 2):
            graph.setdefault(node_i, set()).add(node_j)
            graph.setdefault(node_j, set()).add(node_i)
    return graph, dict(incident)


def _merge_graphs(*graphs: dict[int, set[int]]) -> dict[int, set[int]]:
    merged: dict[int, set[int]] = {}
    for graph in graphs:
        for node_id, neighbors in graph.items():
            merged.setdefault(int(node_id), set()).update(int(neighbor) for neighbor in neighbors)
    return merged


def _support_hop_distances(graph: dict[int, set[int]], support_nodes: set[int]) -> dict[int, int]:
    distances: dict[int, int] = {}
    queue: deque[int] = deque()
    for node_id in sorted(support_nodes):
        distances[int(node_id)] = 0
        if node_id in graph:
            queue.append(int(node_id))
    while queue:
        node_id = queue.popleft()
        for neighbor in graph.get(node_id, set()):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[node_id] + 1
            queue.append(neighbor)
    return distances


def _component_index(
    graph: dict[int, set[int]],
    support_nodes: set[int],
) -> tuple[dict[int, int], list[dict[str, Any]]]:
    node_to_component: dict[int, int] = {}
    components: list[dict[str, Any]] = []
    for start in sorted(graph):
        if start in node_to_component:
            continue
        component_id = len(components)
        queue: deque[int] = deque([start])
        node_to_component[start] = component_id
        nodes: list[int] = []
        while queue:
            node_id = queue.popleft()
            nodes.append(node_id)
            for neighbor in graph.get(node_id, set()):
                if neighbor in node_to_component:
                    continue
                node_to_component[neighbor] = component_id
                queue.append(neighbor)
        support_count = sum(1 for node_id in nodes if node_id in support_nodes)
        components.append(
            {
                "component_id": int(component_id),
                "node_count": int(len(nodes)),
                "support_node_count": int(support_count),
                "has_support": bool(support_count > 0),
                "sample_node_ids": [int(node_id) for node_id in nodes[:12]],
            }
        )
    return node_to_component, components


def _dominant_rows(f2g_audit: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in f2g_audit.get("dominant_dof_rows") or []:
        if not isinstance(row, dict):
            continue
        node_id = _parse_int_token(row.get("node_id"))
        if node_id is None or node_id <= 0:
            continue
        out.append(
            {
                "mode_index": int(_parse_int_token(row.get("mode_index")) or 0),
                "rank_in_mode": int(_parse_int_token(row.get("rank_in_mode")) or 0),
                "node_id": int(node_id),
                "dof": str(row.get("dof") or "").upper(),
                "amplitude": row.get("amplitude"),
                "support_member": bool(row.get("support_member")),
                "elastic_link_degree": int(_parse_int_token(row.get("elastic_link_degree")) or 0),
                "elastic_link_support_reachable": bool(row.get("elastic_link_support_reachable")),
            }
        )
    return out


def _component_lookup(
    node_id: int,
    node_to_component: dict[int, int],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    component_id = node_to_component.get(node_id)
    if component_id is None:
        return {
            "component_id": None,
            "component_size": 0,
            "component_has_support": False,
        }
    component = components[component_id]
    return {
        "component_id": int(component_id),
        "component_size": int(component.get("node_count") or 0),
        "component_has_support": bool(component.get("has_support")),
    }


def _dominant_node_summaries(
    dominant_rows: list[dict[str, Any]],
    *,
    support_nodes: set[int],
    incident_elements: dict[int, list[dict[str, Any]]],
    elastic_graph: dict[int, set[int]],
    element_distances: dict[int, int],
    element_plus_elastic_distances: dict[int, int],
    element_node_to_component: dict[int, int],
    element_components: list[dict[str, Any]],
    combined_node_to_component: dict[int, int],
    combined_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_node: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in dominant_rows:
        by_node[int(row["node_id"])].append(row)

    summaries: list[dict[str, Any]] = []
    for node_id in sorted(by_node):
        rows = by_node[node_id]
        type_counts = Counter(str(element.get("type") or "") for element in incident_elements.get(node_id, []))
        element_hops = element_distances.get(node_id)
        combined_hops = element_plus_elastic_distances.get(node_id)
        summaries.append(
            {
                "node_id": int(node_id),
                "dominant_dof_row_count": int(len(rows)),
                "dofs": sorted({str(row.get("dof") or "") for row in rows if str(row.get("dof") or "")}),
                "support_member": bool(node_id in support_nodes),
                "incident_element_count": int(len(incident_elements.get(node_id, []))),
                "incident_element_types": [
                    {"type": element_type, "count": int(count)}
                    for element_type, count in sorted(type_counts.items())
                ],
                "elastic_link_degree": int(len(elastic_graph.get(node_id, set()))),
                "element_graph_hops_to_support": int(element_hops) if element_hops is not None else None,
                "element_graph_support_reachable": bool(element_hops is not None),
                "element_plus_elastic_hops_to_support": (
                    int(combined_hops) if combined_hops is not None else None
                ),
                "element_plus_elastic_support_reachable": bool(combined_hops is not None),
                "element_component": _component_lookup(
                    node_id,
                    element_node_to_component,
                    element_components,
                ),
                "element_plus_elastic_component": _component_lookup(
                    node_id,
                    combined_node_to_component,
                    combined_components,
                ),
            }
        )
    return summaries


def _classification(
    *,
    dominant_node_count: int,
    element_reachable: int,
    combined_reachable: int,
) -> str:
    if dominant_node_count <= 0:
        return "dominant_nodes_missing"
    if element_reachable >= dominant_node_count:
        return "element_graph_connects_dominant_modes_to_supports"
    if element_reachable == 0 and combined_reachable >= dominant_node_count:
        return "elastic_links_bridge_dominant_modes_to_supports"
    if element_reachable == 0:
        return "element_graph_connectivity_gap_detected"
    return "partial_element_graph_connectivity_gap_detected"


def _graph_summary(
    graph: dict[int, set[int]],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    unsupported = [row for row in components if not row.get("has_support")]
    return {
        "node_count": int(len(graph)),
        "edge_count": int(sum(len(neighbors) for neighbors in graph.values()) // 2),
        "component_count": int(len(components)),
        "unsupported_component_count": int(len(unsupported)),
        "largest_component_size": int(max((row.get("node_count") or 0 for row in components), default=0)),
        "largest_unsupported_component_size": int(
            max((row.get("node_count") or 0 for row in unsupported), default=0)
        ),
    }


def _ranked_findings(summary: dict[str, Any]) -> list[dict[str, Any]]:
    dominant = int(summary.get("dominant_node_count") or 0)
    element_reachable = int(summary.get("dominant_nodes_element_reachable_to_support_count") or 0)
    combined_reachable = int(
        summary.get("dominant_nodes_element_plus_elastic_reachable_to_support_count") or 0
    )
    classification = str(summary.get("global_connectivity_classification") or "")
    findings: list[dict[str, Any]] = []
    if dominant <= 0:
        findings.append(
            {
                "rank": 1,
                "finding_id": "dominant_near_null_nodes_missing",
                "severity": "high",
                "evidence": "No dominant near-null nodes were available from the F2g support/elastic-link audit.",
                "interpretation": "Full structural connectivity cannot be audited until F2g dominant rows are present.",
            }
        )
        return findings
    if element_reachable >= dominant:
        findings.append(
            {
                "rank": 1,
                "finding_id": "dominant_near_null_nodes_have_element_path_to_support",
                "severity": "info",
                "evidence": f"{element_reachable}/{dominant} dominant nodes reach authored supports through the structural element graph.",
                "interpretation": "A direct support-row or elastic-link-row absence is further deprioritized; inspect tangent/load-path transfer and Newton consistency.",
            }
        )
    elif element_reachable == 0:
        findings.append(
            {
                "rank": 1,
                "finding_id": "dominant_near_null_nodes_not_reachable_to_support_via_element_graph",
                "severity": "high",
                "evidence": f"{element_reachable}/{dominant} dominant nodes reach authored supports through the structural element graph.",
                "interpretation": "A full structural connectivity gap remains a primary G1 diagnostic candidate.",
            }
        )
    else:
        findings.append(
            {
                "rank": 1,
                "finding_id": "dominant_near_null_nodes_partially_reachable_to_support_via_element_graph",
                "severity": "medium",
                "evidence": f"{element_reachable}/{dominant} dominant nodes reach authored supports through the structural element graph.",
                "interpretation": "The dominant packet spans both supported and unsupported structural components.",
            }
        )
    if combined_reachable > element_reachable:
        findings.append(
            {
                "rank": 2,
                "finding_id": "elastic_links_increase_dominant_node_support_reachability",
                "severity": "medium",
                "evidence": f"element_plus_elastic_reachable={combined_reachable}/{dominant}; element_only_reachable={element_reachable}/{dominant}.",
                "interpretation": "Elastic links may bridge part of the load path, but this audit still does not prove tangent consistency.",
            }
        )
    findings.append(
        {
            "rank": 3,
            "finding_id": "global_connectivity_audit_is_non_promoting",
            "severity": "info",
            "evidence": f"classification={classification}",
            "interpretation": "G1 remains blocked until full-load residual/Jacobian Newton and ROCm/HIP production-lane evidence pass.",
        }
    )
    return sorted(findings, key=lambda row: int(row["rank"]))


def _decision_record(summary: dict[str, Any]) -> dict[str, Any]:
    classification = str(summary.get("global_connectivity_classification") or "")
    dominant = int(summary.get("dominant_node_count") or 0)
    element_reachable = int(
        summary.get("dominant_nodes_element_reachable_to_support_count") or 0
    )
    element_unreachable = int(
        summary.get("dominant_nodes_without_element_path_to_support_count") or 0
    )
    element_graph_closes_dominant_packet = bool(
        dominant > 0
        and element_reachable >= dominant
        and element_unreachable == 0
        and classification == "element_graph_connects_dominant_modes_to_supports"
    )
    if element_graph_closes_dominant_packet:
        row_only_decision = "stop"
        primary_next_lane = "consistent_residual_jacobian_newton_rocm_worker"
        rationale = [
            f"{element_reachable}/{dominant} dominant near-null nodes reach authored supports through structural elements.",
            "A direct support-row or elastic-link-row absence is no longer the leading G1 explanation.",
            "Further G1 progress requires consistent residual/Jacobian Newton evidence and a production ROCm/HIP residual/JVP lane.",
        ]
        required_next_receipts = [
            "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
            "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
        ]
    else:
        row_only_decision = "hold_pending_connectivity_mapping"
        primary_next_lane = "structural_connectivity_load_path_mapping"
        rationale = [
            f"{element_reachable}/{dominant} dominant near-null nodes reach authored supports through structural elements.",
            "Connectivity/load-path mapping remains a primary diagnostic before a G1 promotion decision.",
        ]
        required_next_receipts = [
            "implementation/phase1/release_evidence/productization/g1_global_connectivity_load_path_audit.json",
            "implementation/phase1/release_evidence/productization/g1_f2g_f2h_cause_narrowing_status.json",
        ]
    return {
        "schema_version": "g1-global-connectivity-decision-record.v1",
        "classification": classification,
        "dominant_node_count": dominant,
        "dominant_nodes_element_reachable_to_support_count": element_reachable,
        "dominant_nodes_without_element_path_to_support_count": element_unreachable,
        "element_graph_closes_dominant_packet": element_graph_closes_dominant_packet,
        "row_only_support_or_elastic_link_correction_decision": row_only_decision,
        "row_only_correction_loop_stopped": bool(element_graph_closes_dominant_packet),
        "primary_next_lane": primary_next_lane,
        "required_next_receipts": required_next_receipts,
        "rationale": rationale,
        "claim_boundary": (
            "This decision record only routes the next G1 diagnostic slice. It does "
            "not prove full-load 1.0 equilibrium, material Newton breadth, or "
            "production ROCm/HIP residency."
        ),
    }


def build_audit(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    f2g_audit_path: Path = DEFAULT_F2G_AUDIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_mgt = mgt_path if mgt_path.is_absolute() else repo_root / mgt_path
    f2g_audit = _load_json(repo_root, f2g_audit_path)

    blockers: list[str] = []
    if not resolved_mgt.is_file():
        blockers.append(f"missing_mgt:{mgt_path}")
    if not f2g_audit:
        blockers.append(f"missing_or_invalid_f2g_audit:{f2g_audit_path}")
    elif f2g_audit.get("status") != "ready":
        blockers.append("f2g_support_elastic_reconciliation_not_ready")
    if blockers:
        return {
            "schema_version": SCHEMA_VERSION,
            **release_evidence_metadata(
                input_paths=[
                    Path("scripts/build_g1_global_connectivity_load_path_audit.py"),
                    mgt_path,
                    f2g_audit_path,
                ],
                reused_evidence=True,
                reuse_policy=REUSE_POLICY,
                repo_root=repo_root,
            ),
            "status": "blocked",
            "contract_pass": False,
            "reason_code": "ERR_G1_GLOBAL_CONNECTIVITY_INPUTS_NOT_READY",
            "promotes_g1_closure": False,
            "claim_boundary": "non_promoting_full_structural_connectivity_load_path_audit_only",
            "summary_line": "G1 global connectivity/load-path audit: BLOCKED | required inputs missing",
            "summary": {},
            "dominant_node_summaries": [],
            "dominant_dof_rows": [],
            "ranked_findings": [],
            "blockers": blockers,
        }

    mgt_text = resolved_mgt.read_text(encoding="utf-8", errors="ignore")
    node_ids = _parse_nodes(mgt_text)
    elements = _parse_elements(mgt_text, node_ids)
    constraints = parse_mgt_support_constraints(mgt_text)
    links = parse_mgt_elastic_links(mgt_text)
    support_nodes = _support_nodes(constraints)
    dominant_rows = _dominant_rows(f2g_audit)

    if not node_ids:
        blockers.append("mgt_node_block_empty")
    if not elements:
        blockers.append("mgt_element_connectivity_empty")
    if not support_nodes:
        blockers.append("mgt_support_constraints_empty")
    if not dominant_rows:
        blockers.append("f2g_dominant_dof_rows_missing")

    element_graph, incident_elements = _element_graph(elements)
    elastic_graph = _elastic_link_graph(links)
    combined_graph = _merge_graphs(element_graph, elastic_graph)

    element_distances = _support_hop_distances(element_graph, support_nodes)
    combined_distances = _support_hop_distances(combined_graph, support_nodes)
    element_node_to_component, element_components = _component_index(element_graph, support_nodes)
    combined_node_to_component, combined_components = _component_index(combined_graph, support_nodes)

    dominant_nodes = sorted({int(row["node_id"]) for row in dominant_rows})
    dominant_summaries = _dominant_node_summaries(
        dominant_rows,
        support_nodes=support_nodes,
        incident_elements=incident_elements,
        elastic_graph=elastic_graph,
        element_distances=element_distances,
        element_plus_elastic_distances=combined_distances,
        element_node_to_component=element_node_to_component,
        element_components=element_components,
        combined_node_to_component=combined_node_to_component,
        combined_components=combined_components,
    )
    element_reachable = sum(1 for row in dominant_summaries if row["element_graph_support_reachable"])
    combined_reachable = sum(
        1 for row in dominant_summaries if row["element_plus_elastic_support_reachable"]
    )
    classification = _classification(
        dominant_node_count=len(dominant_nodes),
        element_reachable=element_reachable,
        combined_reachable=combined_reachable,
    )

    summary = {
        "mgt_node_count": int(len(node_ids)),
        "mgt_element_count": int(len(elements)),
        "support_node_count": int(len(support_nodes)),
        "elastic_link_count": int(len(links)),
        "dominant_dof_row_count": int(len(dominant_rows)),
        "dominant_node_count": int(len(dominant_nodes)),
        "dominant_nodes_element_reachable_to_support_count": int(element_reachable),
        "dominant_nodes_without_element_path_to_support_count": int(
            max(len(dominant_nodes) - element_reachable, 0)
        ),
        "dominant_nodes_element_plus_elastic_reachable_to_support_count": int(combined_reachable),
        "dominant_nodes_without_element_plus_elastic_path_to_support_count": int(
            max(len(dominant_nodes) - combined_reachable, 0)
        ),
        "element_graph_connectivity_gap_detected": bool(element_reachable < len(dominant_nodes)),
        "element_plus_elastic_connectivity_gap_detected": bool(combined_reachable < len(dominant_nodes)),
        "global_connectivity_classification": classification,
        "element_graph": _graph_summary(element_graph, element_components),
        "element_plus_elastic_graph": _graph_summary(combined_graph, combined_components),
        "element_type_counts": dict(sorted(Counter(str(row["type"]) for row in elements).items())),
    }
    findings = _ranked_findings(summary)
    decision_record = _decision_record(summary)
    ready = bool(not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_global_connectivity_load_path_audit.py"),
                mgt_path,
                f2g_audit_path,
            ],
            reused_evidence=True,
            reuse_policy=REUSE_POLICY,
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "blocked",
        "contract_pass": ready,
        "reason_code": "PASS" if ready else "ERR_G1_GLOBAL_CONNECTIVITY_AUDIT_NOT_READY",
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This receipt audits full structural element connectivity and load-path reachability from "
            "existing F2g dominant rows. It does not close G1, prove nonlinear tangent consistency, "
            "promote full-load 1.0, or prove ROCm/HIP production residency."
        ),
        "summary_line": (
            "G1 global connectivity/load-path audit: "
            f"{'READY' if ready else 'BLOCKED'} | "
            f"classification={classification} | "
            f"element_reachable={element_reachable}/{len(dominant_nodes)}"
        ),
        "summary": summary,
        "decision_record": decision_record,
        "dominant_node_summaries": dominant_summaries,
        "dominant_dof_rows": [
            {
                **row,
                "element_graph_support_reachable": bool(
                    element_distances.get(int(row["node_id"])) is not None
                ),
                "element_graph_hops_to_support": element_distances.get(int(row["node_id"])),
                "element_plus_elastic_support_reachable": bool(
                    combined_distances.get(int(row["node_id"])) is not None
                ),
                "element_plus_elastic_hops_to_support": combined_distances.get(int(row["node_id"])),
            }
            for row in dominant_rows
        ],
        "ranked_findings": findings,
        "next_actions": [
            "stop_row_only_support_or_elastic_link_correction_loop"
            if decision_record["row_only_correction_loop_stopped"]
            else "inspect_disconnected_structural_components_and_load_path_mapping",
            "if_element_graph_connects_dominant_nodes_shift_to_consistent_residual_jacobian_newton",
            "if_element_graph_gap_detected_inspect_disconnected_structural_components_and_load_path_mapping",
            "keep_G1_full_load_and_rocm_hip_promotions_blocked_until_terminal_receipts_pass",
        ],
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_full_load_1p0_claim",
            "no_rocm_hip_production_residency_claim",
            "no_tangent_consistency_claim_from_connectivity_only",
        ],
        "blockers": blockers,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--f2g-audit-json", type=Path, default=DEFAULT_F2G_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_audit(
        repo_root=args.repo_root,
        mgt_path=args.mgt_path,
        f2g_audit_path=args.f2g_audit_json,
    )
    output = args.out if args.out.is_absolute() else args.repo_root / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(payload), encoding="utf-8")
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
