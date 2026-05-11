#!/usr/bin/env python3
"""Build release-safe proxy structural graphs from private-corpus IFC files."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_PRIVATE_MANIFEST = Path("private_corpus/real_drawings/private_real_drawing_corpus_manifest.json")
DEFAULT_REDACTED_MANIFEST = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")
DEFAULT_OUT_DIR = Path("tmp/real_drawing_private_corpus/ifc_adapter")
ADAPTER_SCHEMA_VERSION = "real-drawing-ifc-structural-proxy-graph.v1"
ADAPTER_MODE = "entity_proxy_graph"
AGGREGATE_RELATIONSHIP = "aggregates_decomposition"
CONTAINED_RELATIONSHIP = "contained_in_spatial_structure"

STRUCTURAL_ENTITY_TYPES = {
    "IFCBEAM",
    "IFCCOLUMN",
    "IFCSLAB",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
    "IFCMEMBER",
    "IFCPLATE",
    "IFCFOOTING",
    "IFCPILE",
}
SPATIAL_ENTITY_TYPES = {"IFCBUILDINGSTOREY"}
COUNTED_ENTITY_TYPES = STRUCTURAL_ENTITY_TYPES | SPATIAL_ENTITY_TYPES
ENTITY_RE = re.compile(r"^\s*#(?P<id>\d+)\s*=\s*(?P<type>[A-Z0-9_]+)\s*\((?P<args>.*)\)\s*;\s*$", re.I | re.S)
REF_RE = re.compile(r"#(\d+)")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_report_stem(file_id: str, file_name: str) -> str:
    stem = str(file_id or "").strip() or Path(file_name).stem
    chars = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem]
    return "".join(chars).strip("._") or "ifc_model"


def _manifest_ifc_rows(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("project_id", "") or "")
        for file_row in project.get("files", []):
            if not isinstance(file_row, dict):
                continue
            if str(file_row.get("file_type", "") or "").lower() != ".ifc":
                continue
            if file_row.get("model_optimization_candidate") is not True:
                continue
            file_id = str(file_row.get("file_id", "") or "")
            rows[(project_id, file_id)] = {"project": project, "file": file_row}
    return rows


def _records(path: Path) -> list[str]:
    records: list[str] = []
    current: list[str] = []
    in_data = False
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            stripped = line.strip()
            upper = stripped.upper()
            if upper == "DATA;":
                in_data = True
                continue
            if upper == "ENDSEC;" and in_data:
                break
            if not in_data:
                continue
            if current:
                current.append(stripped)
            elif stripped.startswith("#"):
                current.append(stripped)
            else:
                continue
            if stripped.endswith(";"):
                records.append(" ".join(current))
                current = []
    return records


def _split_step_args(text: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            buf.append(ch)
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                buf.append(text[i + 1])
                i += 2
                continue
            in_string = not in_string
        elif not in_string and ch == "(":
            depth += 1
            buf.append(ch)
        elif not in_string and ch == ")":
            depth = max(depth - 1, 0)
            buf.append(ch)
        elif not in_string and ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    args.append("".join(buf).strip())
    return args


def _record_args(record: str) -> tuple[str, str, list[str]] | None:
    match = ENTITY_RE.match(record)
    if not match:
        return None
    entity_id = f"#{match.group('id')}"
    entity_type = match.group("type").upper()
    return entity_id, entity_type, _split_step_args(match.group("args"))


def _entity_label(entity_type: str, _args: list[str], entity_id: str) -> str:
    return f"{entity_type}:{entity_id}"


def _relationship_group_id(entity_type: str, entity_id: str) -> str:
    return f"relationship:{entity_type}:{entity_id}"


def _append_unique_edge(
    edges: list[dict[str, str]],
    seen_edges: set[tuple[str, str, str]],
    *,
    source: str,
    target: str,
    relationship: str,
) -> bool:
    if not source or not target or source == target:
        return False
    key = (source, target, relationship)
    if key in seen_edges:
        return False
    seen_edges.add(key)
    edges.append({"source": source, "target": target, "relationship": relationship})
    return True


def parse_ifc_proxy_graph(path: Path) -> dict[str, Any]:
    entity_counts: Counter[str] = Counter()
    nodes: dict[str, dict[str, Any]] = {}
    records = _records(path)
    parsed_records: list[tuple[str, str, list[str]]] = []

    for record in records:
        parsed = _record_args(record)
        if parsed is None:
            continue
        entity_id, entity_type, args = parsed
        parsed_records.append(parsed)
        entity_counts[entity_type] += 1
        if entity_type in COUNTED_ENTITY_TYPES:
            nodes[entity_id] = {
                "id": entity_id,
                "ifc_entity_type": entity_type,
                "label": _entity_label(entity_type, args, entity_id),
                "proxy_node_kind": "storey" if entity_type in SPATIAL_ENTITY_TYPES else "structural_element",
            }

    structural_entity_count = sum(entity_counts[entity_type] for entity_type in STRUCTURAL_ENTITY_TYPES)
    storey_count = entity_counts["IFCBUILDINGSTOREY"]
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    aggregate_group_candidates: list[tuple[str, list[str]]] = []

    for entity_id, entity_type, args in parsed_records:
        if len(args) < 6:
            continue
        if entity_type == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
            related_ids = [f"#{ref}" for ref in REF_RE.findall(args[4])]
            container_ids = [f"#{ref}" for ref in REF_RE.findall(args[5])]
            for source in related_ids:
                for target in container_ids:
                    if source in nodes and target in nodes:
                        _append_unique_edge(
                            edges,
                            seen_edges,
                            source=source,
                            target=target,
                            relationship=CONTAINED_RELATIONSHIP,
                        )
        elif entity_type == "IFCRELAGGREGATES":
            parent_ids = [f"#{ref}" for ref in REF_RE.findall(args[4])]
            child_ids = [f"#{ref}" for ref in REF_RE.findall(args[5])]
            counted_children = [child_id for child_id in child_ids if child_id in nodes]
            counted_parents = [parent_id for parent_id in parent_ids if parent_id in nodes]
            for source in counted_children:
                for target in counted_parents:
                    _append_unique_edge(
                        edges,
                        seen_edges,
                        source=source,
                        target=target,
                        relationship=AGGREGATE_RELATIONSHIP,
                    )
            if counted_children and not counted_parents:
                aggregate_group_candidates.append((entity_id, counted_children))

    direct_edge_count = len(edges)
    if structural_entity_count > 0 and direct_edge_count < structural_entity_count:
        for entity_id, counted_children in aggregate_group_candidates:
            group_id = _relationship_group_id("IFCRELAGGREGATES", entity_id)
            nodes[group_id] = {
                "id": group_id,
                "ifc_entity_type": "IFCRELAGGREGATES",
                "label": f"IFCRELAGGREGATES:{entity_id}",
                "proxy_node_kind": "relationship_group",
                "relationship": AGGREGATE_RELATIONSHIP,
            }
            for source in counted_children:
                _append_unique_edge(
                    edges,
                    seen_edges,
                    source=source,
                    target=group_id,
                    relationship=AGGREGATE_RELATIONSHIP,
                )

    relationship_counts = Counter(edge["relationship"] for edge in edges)
    relationship_group_node_count = sum(
        1 for node in nodes.values() if node.get("proxy_node_kind") == "relationship_group"
    )
    relationship_extraction_modes = []
    if direct_edge_count > 0:
        relationship_extraction_modes.append("direct_counted_entity_edges")
    if relationship_group_node_count > 0:
        relationship_extraction_modes.append("release_safe_aggregate_group_edges")
    return {
        "adapter_mode": ADAPTER_MODE,
        "entity_counts": {entity_type: int(entity_counts[entity_type]) for entity_type in sorted(COUNTED_ENTITY_TYPES)},
        "metrics": {
            "record_count": len(records),
            "proxy_node_count": len(nodes),
            "proxy_edge_count": len(edges),
            "direct_relationship_edge_count": direct_edge_count,
            "relationship_group_node_count": relationship_group_node_count,
            "structural_entity_count": int(structural_entity_count),
            "storey_count": int(storey_count),
        },
        "proxy_relationship_counts": dict(sorted(relationship_counts.items())),
        "relationship_extraction_modes": relationship_extraction_modes,
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def _release_safe_source(project: dict[str, Any], file_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": str(project.get("project_id", "") or ""),
        "project_title": str(project.get("project_title", "") or ""),
        "source_family": str(project.get("source_family", "") or ""),
        "file_id": str(file_row.get("file_id", "") or ""),
        "file_name": str(file_row.get("file_name", "") or ""),
        "file_type": str(file_row.get("file_type", "") or ""),
        "role": str(file_row.get("role", "") or ""),
        "bytes": int(file_row.get("bytes", 0) or 0),
        "sha256": str(file_row.get("sha256", "") or ""),
        "source_url": str(file_row.get("source_url", "") or ""),
        "raw_redistribution_allowed": bool(file_row.get("raw_redistribution_allowed", False)),
        "release_surface_allowed": bool(file_row.get("release_surface_allowed", False)),
    }


def convert_ifc_corpus(
    *,
    private_manifest_path: Path,
    redacted_manifest_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    private_rows = _manifest_ifc_rows(_load_json(private_manifest_path))
    redacted_rows = _manifest_ifc_rows(_load_json(redacted_manifest_path))
    reports: list[dict[str, Any]] = []
    errors: list[str] = []

    for key, redacted_entry in sorted(redacted_rows.items()):
        private_entry = private_rows.get(key)
        project = redacted_entry["project"]
        file_row = redacted_entry["file"]
        file_id = str(file_row.get("file_id", "") or "")
        file_name = str(file_row.get("file_name", "") or "")
        stem = _safe_report_stem(file_id, file_name)
        report_path = out_dir / f"{stem}.report.json"
        graph_path = out_dir / f"{stem}.graph.json"
        source = _release_safe_source(project, file_row)
        if not private_entry:
            report = {
                "schema_version": ADAPTER_SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contract_pass": False,
                "reason_code": "ERR_PRIVATE_MANIFEST_ROW_MISSING",
                "adapter_mode": ADAPTER_MODE,
                "source": source,
            }
            errors.append(f"{source['project_id']}/{source['file_id']}: private manifest row missing")
        else:
            private_file_row = private_entry["file"]
            raw_path = Path(str(private_file_row.get("private_path", "") or ""))
            if not raw_path.exists():
                report = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "contract_pass": False,
                    "reason_code": "ERR_PRIVATE_IFC_FILE_MISSING",
                    "adapter_mode": ADAPTER_MODE,
                    "source": source,
                }
                errors.append(f"{source['project_id']}/{source['file_id']}: private IFC file missing")
            else:
                graph = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": source,
                    **parse_ifc_proxy_graph(raw_path),
                }
                _write_json(graph_path, graph)
                metrics = graph["metrics"]
                report = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": graph["generated_at"],
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "adapter_mode": ADAPTER_MODE,
                    "source": source,
                    "graph_json": str(graph_path),
                    "metrics": metrics,
                    "entity_counts": graph["entity_counts"],
                    "solver_exact": False,
                    "optimization_readiness": "ifc_proxy_graph_ready",
                    "readiness_note": (
                        "Entity-count proxy graph only; exact member geometry, material/section binding, "
                        "load extraction, and solver-native connectivity are not asserted."
                    ),
                }
        _write_json(report_path, report)
        reports.append({**report, "report_json": str(report_path)})

    ready_reports = [report for report in reports if report.get("contract_pass") is True]
    summary = {
        "ifc_candidate_count": len(reports),
        "ifc_proxy_graph_ready_count": len(ready_reports),
        "failed_count": len(reports) - len(ready_reports),
        "adapter_mode": ADAPTER_MODE,
        "solver_exact": False,
        "proxy_node_count_total": sum(int(report.get("metrics", {}).get("proxy_node_count", 0) or 0) for report in ready_reports),
        "proxy_edge_count_total": sum(int(report.get("metrics", {}).get("proxy_edge_count", 0) or 0) for report in ready_reports),
        "structural_entity_count_total": sum(
            int(report.get("metrics", {}).get("structural_entity_count", 0) or 0) for report in ready_reports
        ),
    }
    manifest = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not errors,
        "reason_code": "PASS" if not errors else "ERR_IFC_PROXY_GRAPH_CONVERSION",
        "source_redacted_manifest": str(redacted_manifest_path),
        "private_manifest_used": True,
        "output_dir": str(out_dir),
        "summary": summary,
        "reports": [
            {
                "project_id": report["source"]["project_id"],
                "file_id": report["source"]["file_id"],
                "file_name": report["source"]["file_name"],
                "contract_pass": bool(report.get("contract_pass", False)),
                "reason_code": str(report.get("reason_code", "") or ""),
                "report_json": report["report_json"],
                "graph_json": str(report.get("graph_json", "") or ""),
                "adapter_mode": ADAPTER_MODE,
                "solver_exact": False,
                "metrics": report.get("metrics", {}),
            }
            for report in reports
        ],
        "errors": errors,
    }
    _write_json(out_dir / "ifc_adapter_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-manifest", type=Path, default=DEFAULT_PRIVATE_MANIFEST)
    parser.add_argument("--redacted-manifest", type=Path, default=DEFAULT_REDACTED_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest = convert_ifc_corpus(
        private_manifest_path=args.private_manifest,
        redacted_manifest_path=args.redacted_manifest,
        out_dir=args.out_dir,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = manifest["summary"]
        print(
            "IFC private corpus adapter: "
            f"{manifest['reason_code']} | candidates={summary['ifc_candidate_count']} | "
            f"proxy_ready={summary['ifc_proxy_graph_ready_count']} | "
            f"structural_entities={summary['structural_entity_count_total']}"
        )
    return 0 if manifest["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
