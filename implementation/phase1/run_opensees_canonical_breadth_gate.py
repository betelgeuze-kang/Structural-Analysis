#!/usr/bin/env python3
"""Surface local OpenSees canonical breadth from committed real-source assets."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from parse_opensees_to_csr import (
    _build_csr,
    _build_graph,
    _classify_element_types,
    _degree_entropy,
    _is_synthetic_source,
    _largest_component_ratio,
    _parse_model,
)


CASE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "SCBF16B",
        "family_id": "sac_scbf16b",
        "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
        "format": "tcl",
        "origin": "global_authority",
    },
    {
        "case_id": "SCBF16B_shell_beam_mix",
        "family_id": "sac_scbf16b_shell_beam_mix",
        "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
        "format": "tcl",
        "origin": "global_authority",
        "require_shell_beam_mix": True,
    },
    {
        "case_id": "luxinzheng_megatall_model1",
        "family_id": "luxinzheng_megatall",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/luxinzheng_megatall_tcl_model1_local/opensees.tcl",
        "format": "tcl",
        "origin": "public_lab_download",
    },
    {
        "case_id": "luxinzheng_megatall_model2",
        "family_id": "luxinzheng_megatall",
        "path": (
            "implementation/phase1/open_data/irregular/harvested/"
            "torsionally_eccentric_core_tower/extracted/OpenSees_Model/"
            "Model2/opensees.tcl"
        ),
        "format": "tcl",
        "origin": "public_lab_download",
    },
    {
        "case_id": "nheri_soft_story_podium",
        "family_id": "nheri_soft_story_podium",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/nheri_soft_story_podium_remote/main.tcl",
        "format": "tcl",
        "origin": "designsafe_publication",
    },
    {
        "case_id": "amaelkady_constructbrace",
        "family_id": "amaelkady_constructbrace",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/amaelkady_constructbrace_github_remote/ConstructBrace.tcl",
        "format": "tcl",
        "origin": "github_public",
    },
    {
        "case_id": "amaelkady_scbf16cg",
        "family_id": "amaelkady_scbf16cg",
        "path": "implementation/phase1/open_data/irregular/collected/artifacts/amaelkady_scbf16cg_github_remote/ConstructBrace.tcl",
        "format": "tcl",
        "origin": "github_public",
    },
    {
        "case_id": "luxinzheng_megatall_bundle",
        "family_id": "luxinzheng_megatall",
        "path": "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/OpenSees-Mega-tall-Building.zip",
        "format": "zip",
        "origin": "public_lab_download",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser_contract(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    if str(spec.get("format") or "").lower() != "tcl":
        return {
            "contract_pass": False,
            "reason_code": "ERR_UNSUPPORTED_CANONICAL_FORMAT",
            "metrics": {},
            "checks": {"source_is_opensees_text": False},
        }
    try:
        nodes, elements, parse_counters = _parse_model(path)
        node_ids, edges_raw, element_counter = _build_graph(nodes, elements)
        _idx_map, edges_idx = _to_indexed_local(node_ids, edges_raw)
        n = int(len(node_ids))
        m = int(len(edges_idx))
        reason_code = "PASS"
        degrees = np.array([], dtype=np.int64)
        largest_component_ratio = 0.0
        degree_entropy = 0.0
        if n == 0 or m == 0:
            reason_code = "ERR_PARSE_FAIL"
        else:
            _indptr, _indices, degrees = _build_csr(n, edges_idx)
            largest_component_ratio = _largest_component_ratio(n, edges_idx)
            degree_entropy = _degree_entropy(degrees)

        et_class = _classify_element_types(element_counter)
        shell_count = int(et_class.get("shell", 0))
        beam_count = int(et_class.get("beam", 0))
        shell_beam_mix_pass = bool(shell_count > 0 and beam_count > 0)
        require_shell_beam_mix = bool(spec.get("require_shell_beam_mix", False))
        edge_node_ratio = float(m) / float(max(n, 1))
        unique_element_types = int(len(element_counter))
        checks = {
            "source_is_opensees_text": path.suffix.lower() in {".tcl", ".txt", ".py", ".dat"},
            "synthetic_source_detected": _is_synthetic_source(path),
            "min_nodes_pass": n >= 100,
            "edge_node_ratio_pass": edge_node_ratio >= 0.40,
            "degree_entropy_pass": degree_entropy >= 0.10,
            "element_type_count_pass": unique_element_types >= 1,
            "largest_component_pass": largest_component_ratio >= 0.02,
            "shell_beam_mix_pass": shell_beam_mix_pass,
        }
        checks["real_topology_pass"] = bool(
            checks["source_is_opensees_text"]
            and checks["min_nodes_pass"]
            and checks["edge_node_ratio_pass"]
            and checks["degree_entropy_pass"]
            and checks["element_type_count_pass"]
            and checks["largest_component_pass"]
            and (checks["shell_beam_mix_pass"] or not require_shell_beam_mix)
            and not checks["synthetic_source_detected"]
        )
        if reason_code == "PASS" and checks["synthetic_source_detected"]:
            reason_code = "ERR_SYNTHETIC_SOURCE"
        if reason_code == "PASS" and require_shell_beam_mix and not shell_beam_mix_pass:
            reason_code = "ERR_SHELL_BEAM_MIX"
        if reason_code == "PASS" and not checks["real_topology_pass"]:
            reason_code = "ERR_TOPOLOGY_COMPLEXITY"
        return {
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "parse_counters": parse_counters,
            "metrics": {
                "node_count": n,
                "edge_count_undirected": m,
                "edge_node_ratio": edge_node_ratio,
                "degree_entropy": float(degree_entropy),
                "largest_component_ratio": float(largest_component_ratio),
                "element_type_count": unique_element_types,
                "shell_element_count": shell_count,
                "beam_element_count": beam_count,
            },
            "checks": checks,
        }
    except Exception as exc:
        return {
            "contract_pass": False,
            "reason_code": f"ERR_PARSER_EXCEPTION:{exc.__class__.__name__}",
            "metrics": {},
            "checks": {},
        }


def _to_indexed_local(node_ids: list[int], edges: list[tuple[int, int]]) -> tuple[dict[int, int], list[list[int]]]:
    idx = {nid: i for i, nid in enumerate(node_ids)}
    out: list[list[int]] = []
    for a, b in edges:
        ia = idx.get(int(a))
        ib = idx.get(int(b))
        if ia is None or ib is None or ia == ib:
            continue
        out.append([int(ia), int(ib)])
    return idx, out


def run_opensees_canonical_breadth_gate() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    family_ids: set[str] = set()
    origin_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    parser_ready_count = 0
    for spec in CASE_SPECS:
        path = Path(str(spec["path"]))
        if not path.exists():
            continue
        family_id = str(spec["family_id"])
        origin = str(spec["origin"])
        fmt = str(spec["format"])
        parser_contract = _parser_contract(path, spec)
        parser_ready = bool(parser_contract.get("contract_pass") is True)
        rows.append(
            {
                "case_id": str(spec["case_id"]),
                "family_id": family_id,
                "path": str(path),
                "format": fmt,
                "origin": origin,
                "size_bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
                "parser_contract_ready": parser_ready,
                "parser_contract": parser_contract,
            }
        )
        family_ids.add(family_id)
        origin_counts[origin] += 1
        format_counts[fmt] += 1
        if parser_ready:
            parser_ready_count += 1

    canonical_case_count = len(rows)
    canonical_family_count = len(family_ids)
    reason_code = "PASS"
    if canonical_case_count < 6 or canonical_family_count < 5 or parser_ready_count < 3:
        reason_code = "ERR_OPENSEES_CANONICAL_BREADTH_LOW"
    summary = {
        "canonical_case_count": canonical_case_count,
        "canonical_family_count": canonical_family_count,
        "standalone_parser_ready_case_count": int(parser_ready_count),
        "origin_counts": dict(sorted(origin_counts.items())),
        "format_counts": dict(sorted(format_counts.items())),
    }
    summary_line = (
        f"OpenSees canonical breadth: {'PASS' if reason_code == 'PASS' else 'CHECK'} | "
        f"families={canonical_family_count} | "
        f"cases={canonical_case_count} | "
        f"parser_ready={parser_ready_count} | "
        f"origins={','.join(f'{key}={value}' for key, value in sorted(origin_counts.items())) or 'n/a'}"
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": (
            "committed OpenSees canonical asset breadth is sufficient for P1 breadth surfacing"
            if reason_code == "PASS"
            else "OpenSees canonical asset breadth is still below the current surfacing floor"
        ),
        "summary": summary,
        "summary_line": summary_line,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
    )
    args = parser.parse_args(argv)
    payload = run_opensees_canonical_breadth_gate()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote OpenSees canonical breadth gate report: {out}")
    return 0 if payload.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
