#!/usr/bin/env python3
"""Build a sparse tangent receipt for MIDAS support masks and elastic links."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, eye
from scipy.sparse.linalg import spsolve

from parse_mgt_section_material_properties import (
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)


SCHEMA_VERSION = "mgt-boundary-spring-tangent-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_boundary_spring_tangent_receipt.json"
)
DOF_LABELS = ("Dx", "Dy", "Dz", "Rx", "Ry", "Rz")
LINK_DOF_LABELS = ("SDx", "SDy", "SDz", "SRx", "SRy", "SRz")
DOF_PER_NODE = 6


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


def _active_node_ids(
    *,
    constraints: list[dict[str, Any]],
    elastic_links: list[dict[str, Any]],
) -> tuple[list[int], set[int], set[int]]:
    support_nodes = {int(node_id) for row in constraints for node_id in row.get("node_ids") or []}
    link_nodes: set[int] = set()
    for link in elastic_links:
        link_nodes.add(int(link["node_i"]))
        link_nodes.add(int(link["node_j"]))
    return sorted(support_nodes | link_nodes), support_nodes, link_nodes


def _restrained_dofs(
    *,
    constraints: list[dict[str, Any]],
    node_index: dict[int, int],
) -> tuple[set[int], dict[str, Any]]:
    dof_index = {label: offset for offset, label in enumerate(DOF_LABELS)}
    restrained: set[int] = set()
    applied_nodes: set[int] = set()
    authored_nodes: set[int] = set()
    code_counts: Counter[str] = Counter()
    applied_code_counts: Counter[str] = Counter()
    dof_counts: Counter[str] = Counter()
    for row in constraints:
        code = str(row.get("restraint_code") or "UNKNOWN")
        code_counts[code] += 1
        mask = row.get("restraint_mask")
        if not isinstance(mask, dict):
            continue
        active_labels = [label for label, active in mask.items() if bool(active) and label in dof_index]
        if not active_labels:
            continue
        row_applied = False
        for node_id_raw in row.get("node_ids") or []:
            node_id = int(node_id_raw)
            authored_nodes.add(node_id)
            local_idx = node_index.get(node_id)
            if local_idx is None:
                continue
            row_applied = True
            applied_nodes.add(node_id)
            base = int(local_idx) * DOF_PER_NODE
            for label in active_labels:
                restrained.add(base + dof_index[label])
                dof_counts[label] += 1
        if row_applied:
            applied_code_counts[code] += 1
    missing_nodes = sorted(authored_nodes - applied_nodes)
    return restrained, {
        "authored_support_constraint_row_count": int(len(constraints)),
        "authored_support_node_count": int(len(authored_nodes)),
        "authored_support_node_count_in_boundary_subsystem": int(len(applied_nodes)),
        "authored_support_node_count_missing_from_boundary_subsystem": int(len(missing_nodes)),
        "authored_support_restrained_dof_count": int(len(restrained)),
        "authored_support_restraint_code_counts": {
            key: int(value) for key, value in sorted(code_counts.items())
        },
        "authored_support_applied_restraint_code_counts": {
            key: int(value) for key, value in sorted(applied_code_counts.items())
        },
        "authored_support_restrained_dof_counts": {
            key: int(value) for key, value in sorted(dof_counts.items())
        },
        "authored_support_missing_node_ids_head": missing_nodes[:32],
    }


def _assemble_link_tangent(
    *,
    elastic_links: list[dict[str, Any]],
    node_index: dict[int, int],
    dof_count: int,
    stiffness_scale: float,
    probe_load: float,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    load = np.zeros(dof_count, dtype=np.float64)
    spring_count = 0
    link_type_counts: Counter[str] = Counter()
    dof_spring_counts: Counter[str] = Counter()
    stiffness_values: list[float] = []
    skipped_links = 0
    for link in elastic_links:
        link_type_counts[str(link.get("link_type") or "UNKNOWN")] += 1
        node_i = node_index.get(int(link["node_i"]))
        node_j = node_index.get(int(link["node_j"]))
        if node_i is None or node_j is None:
            skipped_links += 1
            continue
        stiffness = link.get("stiffness")
        if not isinstance(stiffness, dict):
            skipped_links += 1
            continue
        for offset, label in enumerate(LINK_DOF_LABELS):
            k_value = float(stiffness.get(label) or 0.0) * float(stiffness_scale)
            if k_value <= 0.0:
                continue
            dof_i = int(node_i) * DOF_PER_NODE + offset
            dof_j = int(node_j) * DOF_PER_NODE + offset
            rows.extend([dof_i, dof_i, dof_j, dof_j])
            cols.extend([dof_i, dof_j, dof_i, dof_j])
            vals.extend([k_value, -k_value, -k_value, k_value])
            load[dof_i] += float(probe_load)
            load[dof_j] -= float(probe_load)
            spring_count += 1
            dof_spring_counts[label] += 1
            stiffness_values.append(abs(k_value))
    tangent = coo_matrix((vals, (rows, cols)), shape=(dof_count, dof_count)).tocsr()
    return tangent, load, {
        "elastic_link_row_count": int(len(elastic_links)),
        "elastic_link_rows_skipped": int(skipped_links),
        "finite_spring_component_count": int(spring_count),
        "finite_spring_dof_counts": {key: int(value) for key, value in sorted(dof_spring_counts.items())},
        "elastic_link_type_counts": {key: int(value) for key, value in sorted(link_type_counts.items())},
        "stiffness_abs_min_nonzero_n_per_m_or_nm_per_rad": float(min(stiffness_values) if stiffness_values else 0.0),
        "stiffness_abs_max_n_per_m_or_nm_per_rad": float(max(stiffness_values) if stiffness_values else 0.0),
    }


def _solve_probe(
    *,
    tangent: Any,
    load: np.ndarray,
    restrained: set[int],
    regularization_scale: float,
) -> dict[str, Any]:
    all_dofs = np.arange(load.shape[0], dtype=np.int64)
    restrained_arr = np.asarray(sorted(restrained), dtype=np.int64)
    if restrained_arr.size:
        mask = np.ones(load.shape[0], dtype=bool)
        mask[restrained_arr] = False
        free = all_dofs[mask]
    else:
        free = all_dofs
    k_ff = tangent[free, :][:, free].tocsc()
    f_free = load[free]
    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
    regularization = float(regularization_scale) * max(float(np.mean(np.abs(diag))) if diag.size else 0.0, 1.0)
    k_reg = k_ff + eye(k_ff.shape[0], format="csc") * regularization
    u_free = spsolve(k_reg, f_free)
    residual = k_reg @ u_free - f_free
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    load_inf = float(np.max(np.abs(f_free))) if f_free.size else 0.0
    relative_residual = residual_inf / max(load_inf, 1.0e-12)
    return {
        "free_dof_count": int(free.size),
        "restrained_dof_count": int(len(restrained)),
        "regularization": regularization,
        "residual_inf": residual_inf,
        "relative_residual_inf": relative_residual,
        "max_abs_probe_displacement_or_rotation": float(np.max(np.abs(u_free))) if u_free.size else 0.0,
        "load_inf": load_inf,
    }


def _link_length_summary(
    *,
    nodes: dict[int, tuple[float, float, float]],
    elastic_links: list[dict[str, Any]],
) -> dict[str, float]:
    lengths: list[float] = []
    for link in elastic_links:
        pi = nodes.get(int(link["node_i"]))
        pj = nodes.get(int(link["node_j"]))
        if pi is None or pj is None:
            continue
        lengths.append(float(np.linalg.norm(np.asarray(pj, dtype=np.float64) - np.asarray(pi, dtype=np.float64))))
    return {
        "link_length_min_m": float(min(lengths) if lengths else 0.0),
        "link_length_max_m": float(max(lengths) if lengths else 0.0),
        "link_length_mean_m": float(np.mean(lengths) if lengths else 0.0),
    }


def build_mgt_boundary_spring_tangent_receipt(
    mgt_path: Path = DEFAULT_MGT,
    *,
    stiffness_scale: float = 1000.0,
    probe_load: float = 1.0,
    regularization_scale: float = 1.0e-9,
) -> dict[str, Any]:
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    nodes = _parse_nodes(text)
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    active_nodes, support_nodes, link_nodes = _active_node_ids(
        constraints=constraints,
        elastic_links=elastic_links,
    )
    node_index = {node_id: idx for idx, node_id in enumerate(active_nodes)}
    dof_count = int(len(active_nodes) * DOF_PER_NODE)
    restrained, support_meta = _restrained_dofs(constraints=constraints, node_index=node_index)
    tangent, load, link_meta = _assemble_link_tangent(
        elastic_links=elastic_links,
        node_index=node_index,
        dof_count=dof_count,
        stiffness_scale=stiffness_scale,
        probe_load=probe_load,
    )
    solve = _solve_probe(
        tangent=tangent,
        load=load,
        restrained=restrained,
        regularization_scale=regularization_scale,
    )
    direct_intersection = support_nodes & link_nodes
    finite_ready = bool(
        link_meta["finite_spring_component_count"] == int(len(elastic_links) * len(LINK_DOF_LABELS))
        and tangent.nnz > 0
    )
    support_ready = bool(support_meta["authored_support_restrained_dof_count"] > 0)
    solve_ready = bool(solve["relative_residual_inf"] <= 1.0e-8 and np.isfinite(solve["max_abs_probe_displacement_or_rotation"]))
    status = "ready" if finite_ready and support_ready and solve_ready else "partial"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source": {
            "path": str(mgt_path),
            "sha256": _sha256(mgt_path),
            "size_bytes": int(mgt_path.stat().st_size),
            "source_family": "midas_mgt",
            "blocks": ["*CONSTRAINT", "*ELASTICLINK"],
            "provenance": "repo_benchmark_bridge",
        },
        "unit_policy": {
            "mgt_force_unit": "kN",
            "mgt_length_unit": "m",
            "stiffness_scale_to_si": float(stiffness_scale),
            "probe_load_n_or_nm": float(probe_load),
        },
        "summary": {
            "mgt_node_count": int(len(nodes)),
            "active_boundary_node_count": int(len(active_nodes)),
            "support_node_count": int(len(support_nodes)),
            "elastic_link_node_count": int(len(link_nodes)),
            "direct_support_link_node_intersection_count": int(len(direct_intersection)),
            "dof_count": dof_count,
            "tangent_nnz": int(tangent.nnz),
            **support_meta,
            **link_meta,
            **_link_length_summary(nodes=nodes, elastic_links=elastic_links),
        },
        "support": {
            "authored_support_mask_application_ready": support_ready,
            "finite_elastic_link_spring_tangent_ready": finite_ready,
            "boundary_subsystem_probe_solve_ready": solve_ready,
            "solver_uses_authored_support_restraint_masks": support_ready,
            "solver_assembles_finite_elastic_link_springs": finite_ready,
            "support_and_link_nodes_directly_overlap": bool(direct_intersection),
            "global_frame_shell_tangent_integration_ready": False,
            "story_eccentricity_load_generation_ready": False,
        },
        "probe_solve": solve,
        "claim_boundary": {
            "closed": [
                "real MGT *CONSTRAINT masks are applied as restrained DOFs in a sparse boundary subsystem",
                "real MGT *ELASTICLINK GEN stiffness rows are assembled as finite two-node 6-DOF spring tangent components",
                "a self-equilibrating probe load is solved against the assembled sparse boundary tangent",
            ],
            "not_closed": [
                "this is a boundary subsystem tangent receipt, not the full frame/shell global tangent",
                "support nodes and elastic-link nodes do not directly overlap in this MGT, so full structural connectivity must come from the global element graph",
                "story eccentricity settings are not consumed by this spring tangent receipt",
            ],
        },
        "direct_support_link_node_ids_head": sorted(direct_intersection)[:32],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stiffness-scale", type=float, default=1000.0)
    parser.add_argument("--probe-load", type=float, default=1.0)
    parser.add_argument("--regularization-scale", type=float, default=1.0e-9)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_mgt_boundary_spring_tangent_receipt(
        args.mgt_path,
        stiffness_scale=args.stiffness_scale,
        probe_load=args.probe_load,
        regularization_scale=args.regularization_scale,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "mgt-boundary-spring-tangent: "
        f"status={payload['status']} "
        f"springs={payload['summary']['finite_spring_component_count']} "
        f"restrained_dof={payload['summary']['authored_support_restrained_dof_count']} "
        f"rel_residual={payload['probe_solve']['relative_residual_inf']:.3e}"
    )
    return 0 if payload["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
