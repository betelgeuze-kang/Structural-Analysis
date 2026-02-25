#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

VALID_BC = {"fixed", "pinned", "roller", "free"}
VALID_UNITS = {"SI", "N-mm", "kN-m"}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_payload(data: dict) -> None:
    _assert(isinstance(data, dict), "root must be an object")
    for field in ("nodes", "edges", "meta"):
        _assert(field in data, f"missing '{field}'")

    nodes = data["nodes"]
    _assert(isinstance(nodes, list) and len(nodes) > 0, "nodes must be non-empty list")
    for i, node in enumerate(nodes):
        for f in ("node_id", "ux", "uy", "uz", "f_unbalanced", "bc_type"):
            _assert(f in node, f"nodes[{i}] missing '{f}'")
        _assert(isinstance(node["node_id"], str), f"nodes[{i}].node_id must be string")
        for comp in ("ux", "uy", "uz"):
            _assert(_is_number(node[comp]), f"nodes[{i}].{comp} must be number")
        fu = node["f_unbalanced"]
        _assert(isinstance(fu, dict), f"nodes[{i}].f_unbalanced must be object")
        for c in ("fx", "fy", "fz", "norm"):
            _assert(c in fu and _is_number(fu[c]), f"nodes[{i}].f_unbalanced.{c} must be number")
        _assert(fu["norm"] >= 0, f"nodes[{i}].f_unbalanced.norm must be >= 0")
        _assert(node["bc_type"] in VALID_BC, f"nodes[{i}].bc_type invalid")

    edges = data["edges"]
    _assert(isinstance(edges, list) and len(edges) > 0, "edges must be non-empty list")
    for i, edge in enumerate(edges):
        for f in ("edge_id", "from", "to", "axial_force", "shear_force", "moment", "local_stiffness", "yield_index"):
            _assert(f in edge, f"edges[{i}] missing '{f}'")
        for f in ("edge_id", "from", "to"):
            _assert(isinstance(edge[f], str), f"edges[{i}].{f} must be string")
        for f in ("axial_force", "shear_force", "moment", "local_stiffness", "yield_index"):
            _assert(_is_number(edge[f]), f"edges[{i}].{f} must be number")
        _assert(edge["local_stiffness"] >= 0, f"edges[{i}].local_stiffness must be >= 0")
        _assert(edge["yield_index"] >= 0, f"edges[{i}].yield_index must be >= 0")

    meta = data["meta"]
    _assert(isinstance(meta, dict), "meta must be object")
    for f in ("unit_system", "residual_force_tolerance", "solver", "converged", "steps"):
        _assert(f in meta, f"meta missing '{f}'")
    _assert(meta["unit_system"] in VALID_UNITS, "meta.unit_system invalid")
    _assert(_is_number(meta["residual_force_tolerance"]) and meta["residual_force_tolerance"] >= 0,
            "meta.residual_force_tolerance must be number >= 0")
    _assert(isinstance(meta["solver"], str), "meta.solver must be string")
    _assert(isinstance(meta["converged"], bool), "meta.converged must be boolean")
    _assert(isinstance(meta["steps"], int) and meta["steps"] >= 1, "meta.steps must be int >= 1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="implementation/phase1/lf_output_schema.json")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    # Keep schema argument for CLI compatibility/documentation traceability.
    _ = Path(args.schema).read_text(encoding="utf-8")
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    validate_payload(data)
    print(f"Validation passed: {args.input}")


if __name__ == "__main__":
    main()
