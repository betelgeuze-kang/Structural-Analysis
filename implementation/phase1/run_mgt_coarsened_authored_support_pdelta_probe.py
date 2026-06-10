#!/usr/bin/env python3
"""Probe coarsened line-mesh P-Delta behavior with authored MIDAS support masks."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DEFAULT_ROUNDTRIP,
    DOF_PER_NODE,
    PRODUCTIZATION,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _component_restraints,
    _element_angle_array_from_props,
    _select_full_line_mesh,
    _solve_deformed_state_pdelta_fixed_point,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-coarsened-authored-support-pdelta-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_coarsened_authored_support_pdelta_probe.json"
SUPPORT_DOF_OFFSETS = {"Dx": 0, "Dy": 1, "Dz": 2, "Rx": 3, "Ry": 4, "Rz": 5}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _authored_support_restraints(
    *,
    constraints: list[dict[str, Any]],
    node_index: dict[int, int],
) -> tuple[set[int], dict[str, Any]]:
    restrained: set[int] = set()
    authored_nodes: set[int] = set()
    mapped_nodes: set[int] = set()
    code_counts: Counter[str] = Counter()
    mapped_code_counts: Counter[str] = Counter()
    dof_counts: Counter[str] = Counter()
    for row in constraints:
        code = str(row.get("restraint_code") or "UNKNOWN")
        code_counts[code] += 1
        mask = row.get("restraint_mask")
        if not isinstance(mask, dict):
            continue
        active_offsets = [
            (label, SUPPORT_DOF_OFFSETS[label])
            for label, active in mask.items()
            if bool(active) and label in SUPPORT_DOF_OFFSETS
        ]
        row_mapped = False
        for raw_node_id in row.get("node_ids") or []:
            node_id = int(raw_node_id)
            authored_nodes.add(node_id)
            local_node = node_index.get(node_id)
            if local_node is None:
                continue
            mapped_nodes.add(node_id)
            row_mapped = True
            base = int(local_node) * DOF_PER_NODE
            for label, offset in active_offsets:
                restrained.add(base + int(offset))
                dof_counts[label] += 1
        if row_mapped:
            mapped_code_counts[code] += 1
    missing_nodes = sorted(authored_nodes - mapped_nodes)
    return restrained, {
        "support_constraint_row_count": int(len(constraints)),
        "authored_support_node_count": int(len(authored_nodes)),
        "mapped_support_node_count": int(len(mapped_nodes)),
        "missing_support_node_count": int(len(missing_nodes)),
        "authored_support_restrained_dof_count": int(len(restrained)),
        "restraint_code_counts": {key: int(value) for key, value in sorted(code_counts.items())},
        "mapped_restraint_code_counts": {
            key: int(value) for key, value in sorted(mapped_code_counts.items())
        },
        "restrained_dof_counts": {key: int(value) for key, value in sorted(dof_counts.items())},
        "missing_support_node_ids_head": missing_nodes[:32],
    }


def _line_mesh_node_index(
    *,
    node_id: np.ndarray,
    edge_index: np.ndarray,
    elem_type_code: np.ndarray,
    elem_count: int,
) -> tuple[dict[int, int], dict[str, Any]]:
    edge = np.asarray(edge_index[:, :elem_count], dtype=np.int64)
    line_mask = np.asarray(elem_type_code, dtype=np.int32) == 1
    used_nodes = sorted(
        set(edge[0, line_mask].astype(int).tolist())
        | set(edge[1, line_mask].astype(int).tolist())
    )
    node_index = {int(node_id[old]): int(local) for local, old in enumerate(used_nodes)}
    return node_index, {
        "coarsened_line_node_count": int(len(used_nodes)),
        "line_node_id_head": [int(node_id[old]) for old in used_nodes[:16]],
    }


def _elastic_link_mapping_summary(
    *,
    links: list[dict[str, Any]],
    node_index: dict[int, int],
) -> dict[str, Any]:
    link_nodes: set[int] = set()
    mapped_nodes: set[int] = set()
    both_mapped = 0
    one_sided = 0
    for link in links:
        node_i = int(link.get("node_i") or 0)
        node_j = int(link.get("node_j") or 0)
        link_nodes.update([node_i, node_j])
        i_mapped = node_i in node_index
        j_mapped = node_j in node_index
        if i_mapped:
            mapped_nodes.add(node_i)
        if j_mapped:
            mapped_nodes.add(node_j)
        if i_mapped and j_mapped:
            both_mapped += 1
        elif i_mapped or j_mapped:
            one_sided += 1
    return {
        "elastic_link_row_count": int(len(links)),
        "elastic_link_distinct_node_count": int(len(link_nodes)),
        "elastic_link_mapped_node_count": int(len(mapped_nodes)),
        "elastic_link_rows_both_endpoints_mapped_to_line_mesh": int(both_mapped),
        "elastic_link_rows_one_endpoint_mapped_to_line_mesh": int(one_sided),
        "finite_elastic_link_policy": (
            "not_assembled_in_this_coarsened_line_probe_no_link_has_both_endpoints_mapped"
            if both_mapped == 0
            else "not_assembled_in_this_probe_mapping_available_for_follow_up"
        ),
    }


def run_mgt_coarsened_authored_support_pdelta_probe(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
    load_steps: tuple[float, ...] = (0.5, 0.55),
    max_iterations_per_step: int = 28,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_npz.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    if not mgt_path.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    props = load_mgt_section_material_properties(mgt_path)
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_id = np.asarray(archive["node_id"], dtype=np.int64)
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id)
        )
        elements, node_xyz_sub, select_meta = _select_full_line_mesh(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=edge_index,
            elem_id=elem_id,
            elem_type_code=elem_type_code,
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )

    component_restrained, component_count, base_node_count = _component_restraints(elements, node_xyz_sub)
    node_index, line_node_meta = _line_mesh_node_index(
        node_id=node_id,
        edge_index=edge_index,
        elem_type_code=elem_type_code,
        elem_count=int(elem_id.shape[0]),
    )
    authored_restrained, support_meta = _authored_support_restraints(
        constraints=constraints,
        node_index=node_index,
    )
    link_meta = _elastic_link_mapping_summary(links=elastic_links, node_index=node_index)
    axial_forces = _component_gravity_axial_forces(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )

    n_dof = int(node_xyz_sub.shape[0]) * DOF_PER_NODE
    current_u: np.ndarray | None = None
    max_converged = 0.0
    first_failed: float | None = None
    rows: list[dict[str, Any]] = []
    for idx, step in enumerate(load_steps):
        step_started = time.perf_counter()
        result, next_u = _solve_deformed_state_pdelta_fixed_point(
            elements=elements,
            node_xyz=node_xyz_sub,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=axial_forces,
            restrained=authored_restrained,
            target_load_scale=float(step),
            max_iterations=max_iterations_per_step,
            initial_displacement=current_u,
            relaxation_factor=1.0 if idx == 0 else 0.7,
            displacement_cap_m=80.0,
        )
        row = {
            "load_step": float(step),
            "seconds": time.perf_counter() - step_started,
            "ready": bool(result.get("ready")),
            "converged": bool(result.get("converged")),
            "iteration_count": int(result.get("iteration_count") or 0),
            "residual_inf_n": float(result.get("residual_inf_n") or 0.0),
            "relative_increment": float(result.get("relative_increment") or 0.0),
            "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
            "max_translation_m": float(result.get("max_translation_m") or 0.0),
            "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
            "linear_solver_refinement": result.get("linear_solver_refinement") or {},
            "blockers": result.get("blockers") or [],
        }
        rows.append(row)
        if bool(result.get("ready")):
            max_converged = float(step)
            current_u = np.asarray(next_u, dtype=np.float64)
            continue
        first_failed = float(step)
        break

    ready = bool(max_converged >= 1.0)
    partial = bool(rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial" if partial else "blocked",
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": _sha256(mgt_path),
        "solve_scope": "coarsened_line_mesh_pdelta_with_authored_support_masks_probe",
        "boundary_condition_policy": {
            "primary_restraints": "authored_mgt_support_masks_mapped_to_coarsened_line_nodes",
            "component_base_restraints_used": False,
            "component_base_restraints_recorded_for_comparison": True,
            "finite_elastic_links_assembled": False,
            "finite_elastic_link_reason": link_meta["finite_elastic_link_policy"],
        },
        "coarsened_authored_support_pdelta_ready": ready,
        "max_converged_load_scale": float(max_converged),
        "first_failed_load_scale": first_failed,
        "load_steps_requested": [float(value) for value in load_steps],
        "step_results": rows,
        "mesh_fingerprint": {
            **select_meta,
            **line_node_meta,
            "line_elements_solved": int(len(elements)),
            "line_nodes_solved": int(node_xyz_sub.shape[0]),
            "component_count": int(component_count),
            "component_base_node_count": int(base_node_count),
            "component_base_restrained_dof_count": int(len(component_restrained)),
            "dof_count": int(n_dof),
        },
        "support_mapping": support_meta,
        "elastic_link_mapping": link_meta,
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_coarsened_line_pdelta_authored_support_probe",
            "total_seconds": time.perf_counter() - started,
        },
        "claim_boundary": (
            "This diagnostic replaces the coarsened line-only component-base restraints with authored "
            "MIDAS support masks that still map to the coarsened line mesh. It deliberately does not "
            "assemble finite elastic links because no elastic-link row has both endpoints in this "
            "coarsened line mesh. The result is boundary-condition migration evidence, not full-load "
            "nonlinear Newton closure."
        ),
        "blockers": []
        if ready
        else [
            "coarsened_line_authored_support_pdelta_not_converged",
            "uncoarsened_boundary_nonlinear_continuation_required",
            "consistent_newton_jacobian_required",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-iterations-per-step", type=int, default=28)
    parser.add_argument("--load-steps", default="0.5,0.55")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_steps = tuple(float(value.strip()) for value in str(args.load_steps).split(",") if value.strip())
    payload = run_mgt_coarsened_authored_support_pdelta_probe(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
        load_steps=load_steps,
        max_iterations_per_step=int(args.max_iterations_per_step),
    )
    print(
        "mgt-coarsened-authored-support-pdelta: "
        f"{payload['status']} max_load={payload.get('max_converged_load_scale')} "
        f"failed={payload.get('first_failed_load_scale')} -> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
