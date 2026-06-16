#!/usr/bin/env python3
"""Build an OpenSees topology roundtrip trace report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_TOPOLOGY = Path("implementation/phase1/opensees_topology_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/opensees_roundtrip_trace_report.json")
DEFAULT_CANONICAL_OUT = Path("implementation/phase1/release_evidence/productization/opensees_roundtrip_canonical_edges.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _canonical_edges(edges: Any) -> list[list[int]]:
    out: set[tuple[int, int]] = set()
    if not isinstance(edges, list):
        return []
    for edge in edges:
        if not isinstance(edge, list | tuple) or len(edge) < 2:
            continue
        try:
            a = int(edge[0])
            b = int(edge[1])
        except Exception:
            continue
        if a == b:
            continue
        lo, hi = sorted((a, b))
        out.add((lo, hi))
    return [[a, b] for a, b in sorted(out)]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_report(*, topology_path: Path, canonical_out: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    topology = _load_json(topology_path)
    artifacts = topology.get("artifacts") if isinstance(topology.get("artifacts"), dict) else {}
    metrics = topology.get("metrics") if isinstance(topology.get("metrics"), dict) else {}
    inputs = topology.get("inputs") if isinstance(topology.get("inputs"), dict) else {}
    source_provenance = (
        topology.get("source_provenance") if isinstance(topology.get("source_provenance"), dict) else {}
    )
    edges_path = Path(str(artifacts.get("edges_json", "")))
    edges_payload = _load_json(edges_path)
    canonical_edges = _canonical_edges(edges_payload.get("edges"))
    canonical_payload = {
        "schema_version": "opensees-roundtrip-canonical-edges.v1",
        "source": str(edges_payload.get("source", "")),
        "node_count": int(edges_payload.get("node_count", 0) or 0),
        "edge_count": len(canonical_edges),
        "edges": canonical_edges,
    }
    canonical_text = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    reloaded = json.loads(canonical_text)
    reloaded_text = json.dumps(reloaded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report_edge_count = int(metrics.get("edge_count_undirected", -1))
    report_node_count = int(metrics.get("node_count", -1))
    source_path = str(source_provenance.get("source_path", inputs.get("model", "")))
    checks = {
        "topology_gate_pass": _reason_pass(topology),
        "edges_json_present": bool(edges_path.exists()),
        "source_trace_pass": bool(edges_payload.get("source") == source_path),
        "node_count_match": int(canonical_payload["node_count"]) == report_node_count,
        "edge_count_match": len(canonical_edges) == report_edge_count,
        "serialize_reload_exact_pass": canonical_text == reloaded_text,
        "no_lossy_rewrite_pass": len(canonical_edges) == len(edges_payload.get("edges", [])),
    }
    checks["roundtrip_trace_pass"] = all(checks.values())
    blockers = [key for key, ok in checks.items() if not ok]
    report = {
        "schema_version": "opensees-roundtrip-trace-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "source_path": source_path,
            "source_sha256": str(source_provenance.get("source_sha256", "")),
            "node_count": canonical_payload["node_count"],
            "edge_count": len(canonical_edges),
            "roundtrip_exact_entry_row_coverage_min": 1.0 if not blockers else 0.0,
            "canonical_sha256": _sha256_text(canonical_text),
        },
        "artifacts": {
            "opensees_topology": str(topology_path),
            "edges_json": str(edges_path),
            "canonical_edges": str(canonical_out) if canonical_out else "",
        },
        "claim_boundary": (
            "OpenSees roundtrip trace covers topology edge-list canonicalization and exact JSON reload. It is "
            "not a full OpenSees solver execution roundtrip."
        ),
    }
    return report, canonical_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--canonical-out", type=Path, default=DEFAULT_CANONICAL_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report, canonical = build_report(topology_path=args.topology, canonical_out=args.canonical_out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.canonical_out.parent.mkdir(parents=True, exist_ok=True)
    args.canonical_out.write_text(json.dumps(canonical, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) if args.json else report["reason_code"])
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
