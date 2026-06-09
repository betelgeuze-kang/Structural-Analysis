#!/usr/bin/env python3
"""Run an uncoarsened MGT global frame-shell solve with authored boundary springs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof
from run_mgt_coupled_frame_surface_sparse_equilibrium import (
    _combined_restraints,
    _select_frame_elements,
    _solve_active_system,
    _translation_metrics,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
)


SCHEMA_VERSION = "mgt-uncoarsened-boundary-global-equilibrium.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
DEFAULT_OUT = PRODUCTIZATION / "mgt_uncoarsened_boundary_global_equilibrium.json"
PARSER = REPO_ROOT / "implementation/phase1/parse_midas_mgt_to_json_npz.py"
SUPPORT_DOF_OFFSETS = {"Dx": 0, "Dy": 1, "Dz": 2, "Rx": 3, "Ry": 4, "Rz": 5}
LINK_DOF_LABELS = ("SDx", "SDy", "SDz", "SRx", "SRy", "SRz")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _run_uncoarsened_parser(*, mgt_path: Path, work_dir: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    json_out = work_dir / "mgt_uncoarsened.roundtrip.json"
    npz_out = work_dir / "mgt_uncoarsened.roundtrip.npz"
    report_out = work_dir / "mgt_uncoarsened.report.json"
    command = [
        sys.executable,
        str(PARSER),
        "--mgt",
        str(mgt_path),
        "--json-out",
        str(json_out),
        "--npz-out",
        str(npz_out),
        "--report-out",
        str(report_out),
        "--no-resolve-rigid-links",
        "--no-drop-unreferenced-nodes",
        "--no-strict-unknown-sections",
        "--max-element-skip-ratio",
        "0.20",
        "--max-element-skip-count",
        "10000",
    ]
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    parser_run = {
        "command": command,
        "return_code": int(proc.returncode),
        "stdout_excerpt": (proc.stdout or "")[:4000],
        "stderr_excerpt": (proc.stderr or "")[:4000],
    }
    if proc.returncode != 0:
        raise RuntimeError(f"uncoarsened MGT parser failed: {proc.stderr or proc.stdout}")
    return json_out, npz_out, _load_json(report_out), parser_run


def _authored_support_restraints(
    *,
    constraints: list[dict[str, Any]],
    node_index: dict[int, int],
) -> tuple[set[int], dict[str, Any]]:
    restrained: set[int] = set()
    authored_nodes: set[int] = set()
    mapped_nodes: set[int] = set()
    restraint_code_counts: Counter[str] = Counter()
    dof_counts: Counter[str] = Counter()
    for row in constraints:
        code = str(row.get("restraint_code") or "UNKNOWN")
        restraint_code_counts[code] += 1
        mask = row.get("restraint_mask")
        if not isinstance(mask, dict):
            continue
        active_offsets = [
            (label, SUPPORT_DOF_OFFSETS[label])
            for label, active in mask.items()
            if bool(active) and label in SUPPORT_DOF_OFFSETS
        ]
        for raw_node_id in row.get("node_ids") or []:
            node_id = int(raw_node_id)
            authored_nodes.add(node_id)
            local_node = node_index.get(node_id)
            if local_node is None:
                continue
            mapped_nodes.add(node_id)
            base = int(local_node) * DOF_PER_NODE
            for label, offset in active_offsets:
                restrained.add(base + int(offset))
                dof_counts[label] += 1
    missing_nodes = sorted(authored_nodes - mapped_nodes)
    return restrained, {
        "support_constraint_row_count": int(len(constraints)),
        "authored_support_node_count": int(len(authored_nodes)),
        "mapped_support_node_count": int(len(mapped_nodes)),
        "missing_support_node_count": int(len(missing_nodes)),
        "authored_support_restrained_dof_count": int(len(restrained)),
        "restraint_code_counts": {key: int(value) for key, value in sorted(restraint_code_counts.items())},
        "restrained_dof_counts": {key: int(value) for key, value in sorted(dof_counts.items())},
        "missing_support_node_ids_head": missing_nodes[:32],
    }


def _assemble_elastic_link_springs(
    *,
    links: list[dict[str, Any]],
    node_index: dict[int, int],
    dof_count: int,
    stiffness_scale_to_si: float,
) -> tuple[Any, dict[str, Any]]:
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    skipped_links = 0
    component_count = 0
    link_type_counts: Counter[str] = Counter()
    dof_counts: Counter[str] = Counter()
    link_nodes: set[int] = set()
    mapped_link_nodes: set[int] = set()
    stiffness_values: list[float] = []
    for link in links:
        link_type_counts[str(link.get("link_type") or "UNKNOWN")] += 1
        node_i_id = int(link.get("node_i") or 0)
        node_j_id = int(link.get("node_j") or 0)
        link_nodes.update([node_i_id, node_j_id])
        node_i = node_index.get(node_i_id)
        node_j = node_index.get(node_j_id)
        if node_i is None or node_j is None:
            skipped_links += 1
            continue
        mapped_link_nodes.update([node_i_id, node_j_id])
        stiffness = link.get("stiffness")
        if not isinstance(stiffness, dict):
            skipped_links += 1
            continue
        for offset, label in enumerate(LINK_DOF_LABELS):
            k_value = float(stiffness.get(label) or 0.0) * float(stiffness_scale_to_si)
            if k_value <= 0.0:
                continue
            dof_i = int(node_i) * DOF_PER_NODE + int(offset)
            dof_j = int(node_j) * DOF_PER_NODE + int(offset)
            rows.extend([dof_i, dof_i, dof_j, dof_j])
            cols.extend([dof_i, dof_j, dof_i, dof_j])
            vals.extend([k_value, -k_value, -k_value, k_value])
            component_count += 1
            dof_counts[label] += 1
            stiffness_values.append(abs(k_value))
    tangent = coo_matrix((vals, (rows, cols)), shape=(dof_count, dof_count)).tocsr()
    return tangent, {
        "elastic_link_row_count": int(len(links)),
        "elastic_link_rows_skipped": int(skipped_links),
        "distinct_elastic_link_node_count": int(len(link_nodes)),
        "mapped_elastic_link_node_count": int(len(mapped_link_nodes)),
        "missing_elastic_link_node_count": int(len(link_nodes - mapped_link_nodes)),
        "finite_spring_component_count": int(component_count),
        "finite_spring_dof_counts": {key: int(value) for key, value in sorted(dof_counts.items())},
        "elastic_link_type_counts": {key: int(value) for key, value in sorted(link_type_counts.items())},
        "stiffness_abs_min_nonzero_n_per_m_or_nm_per_rad": float(min(stiffness_values) if stiffness_values else 0.0),
        "stiffness_abs_max_n_per_m_or_nm_per_rad": float(max(stiffness_values) if stiffness_values else 0.0),
    }


def run_mgt_uncoarsened_boundary_global_equilibrium(
    *,
    mgt_path: Path = DEFAULT_MGT,
    output_json: Path | None = None,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    retain_uncoarsened_artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    if not mgt_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    try:
        if retain_uncoarsened_artifacts_dir is None:
            temp_context = tempfile.TemporaryDirectory(prefix="mgt-uncoarsened-boundary-")
            work_dir = Path(temp_context.name)
            retained = False
        else:
            work_dir = retain_uncoarsened_artifacts_dir
            work_dir.mkdir(parents=True, exist_ok=True)
            retained = True
        roundtrip_json, roundtrip_npz, parser_report, parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=work_dir,
        )

        props = load_mgt_section_material_properties(mgt_path)
        section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
        material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
        plate_thickness_props = props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
        beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

        with np.load(roundtrip_npz, allow_pickle=False) as archive:
            node_id = np.asarray(archive["node_id"], dtype=np.int64)
            node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
            edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
            elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
            elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
            elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
            elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
            elem_angle_deg = (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(props, elem_id)
            )
            conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
            conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

        frame_elements, frame_select_meta = _select_frame_elements(
            node_xyz=node_xyz,
            edge_index=edge_index,
            elem_id=elem_id,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )
        frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
            elements=frame_elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
        )
        shell_stiffness, shell_f, shell_meta, surface_conns = _assemble_surface_shell_6dof(
            node_xyz=node_xyz,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
        )
        node_index = {int(raw_node_id): int(index) for index, raw_node_id in enumerate(node_id.tolist())}
        restrained, support_meta = _authored_support_restraints(
            constraints=constraints,
            node_index=node_index,
        )
        spring_stiffness, spring_meta = _assemble_elastic_link_springs(
            links=elastic_links,
            node_index=node_index,
            dof_count=int(node_xyz.shape[0]) * DOF_PER_NODE,
            stiffness_scale_to_si=stiffness_scale_to_si,
        )
        supplemental_restrained, supplemental_meta = _combined_restraints(
            n_nodes=int(node_xyz.shape[0]),
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            surface_conns=surface_conns,
        )
        stiffness = frame_stiffness + shell_stiffness + spring_stiffness
        f_ext = frame_f * float(frame_gravity_load_scale) + shell_f
        active, free, u_free, residual_inf, rhs_inf, regularization = _solve_active_system(
            stiffness=stiffness,
            f_ext=f_ext,
            restrained=restrained,
        )
        u = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
        u[free] = np.asarray(u_free, dtype=np.float64)
        metrics = _translation_metrics(u, node_xyz)
        relative = residual_inf / max(rhs_inf, 1.0)
        coarsening = parser_report.get("coarsening") if isinstance(parser_report.get("coarsening"), dict) else {}
        ready = bool(
            parser_report.get("contract_pass")
            and not bool(coarsening.get("applied"))
            and support_meta["missing_support_node_count"] == 0
            and spring_meta["elastic_link_rows_skipped"] == 0
            and spring_meta["finite_spring_component_count"] == len(elastic_links) * len(LINK_DOF_LABELS)
            and len(restrained) > 0
            and free.size > 0
            and np.all(np.isfinite(u_free))
            and residual_inf <= 5.0e-4
            and relative <= 2.0e-8
            and metrics["max_translation_m"] <= 5.0
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "ready" if ready else "partial",
            "uncoarsened_boundary_global_equilibrium_ready": ready,
            "global_frame_shell_tangent_integration_ready": ready,
            "roundtrip_policy": {
                "resolve_rigid_links": False,
                "drop_unreferenced_nodes": False,
                "retained_uncoarsened_artifacts": retained,
                "roundtrip_json": str(roundtrip_json) if retained else "",
                "roundtrip_npz": str(roundtrip_npz) if retained else "",
                "parser_report_contract_pass": bool(parser_report.get("contract_pass")),
                "parser_coarsening": coarsening,
                "parser_run": parser_run,
            },
            "source": {
                "mgt_path": str(mgt_path),
                "source_family": "midas_mgt",
                "provenance": "repo_benchmark_bridge",
                "blocks": ["*CONSTRAINT", "*ELASTICLINK", "*ELEMENT", "*THICKNESS"],
            },
            "unit_policy": {
                "mgt_force_unit": "kN",
                "mgt_length_unit": "m",
                "elastic_link_stiffness_scale_to_si": float(stiffness_scale_to_si),
                "frame_gravity_load_scale": float(frame_gravity_load_scale),
            },
            "mesh_fingerprint": {
                **frame_select_meta,
                **shell_meta,
                "node_count": int(node_xyz.shape[0]),
                "dof_count": int(node_xyz.shape[0]) * DOF_PER_NODE,
                "element_count": int(elem_id.shape[0]),
                "active_dof_count": int(active.size),
                "free_dof_count": int(free.size),
                "authored_restrained_dof_count": int(len(restrained)),
                "supplemental_component_base_restrained_dof_count": int(len(supplemental_restrained)),
                "supplemental_component_base_intersection_dof_count": int(len(restrained & supplemental_restrained)),
                "frame_stiffness_nnz": int(frame_stiffness.nnz),
                "shell_stiffness_nnz": int(shell_stiffness.nnz),
                "elastic_link_spring_stiffness_nnz": int(spring_stiffness.nnz),
                "global_stiffness_nnz": int(stiffness.nnz),
            },
            "boundary_summary": {
                **support_meta,
                **spring_meta,
                "support_link_node_intersection_count": int(
                    len(
                        {
                            int(node_id_raw)
                            for row in constraints
                            for node_id_raw in row.get("node_ids") or []
                        }
                        & {
                            int(node_id_raw)
                            for link in elastic_links
                            for node_id_raw in (link.get("node_i"), link.get("node_j"))
                            if node_id_raw is not None
                        }
                    )
                ),
            },
            "frame_section_material_coverage": frame_meta,
            "supplemental_component_restraint_meta": supplemental_meta,
            "equilibrium_metrics": {
                "residual_inf_n": float(residual_inf),
                "relative_residual_inf": float(relative),
                "rhs_inf_n": float(rhs_inf),
                "regularization": float(regularization),
                "max_abs_displacement_m": float(metrics["max_abs_displacement_m"]),
                "max_translation_m": float(metrics["max_translation_m"]),
                "max_drift_ratio_pct": float(metrics["max_drift_ratio_pct"]),
            },
            "runtime_metrics": {
                "backend": "scipy_sparse_spsolve_cpu_uncoarsened_boundary_global_frame_shell",
                "total_seconds": time.perf_counter() - started,
            },
            "support": {
                "solver_uses_authored_support_restraint_masks": ready,
                "solver_assembles_finite_elastic_link_springs": ready,
                "uncoarsened_elastic_link_endpoints_preserved": spring_meta["elastic_link_rows_skipped"] == 0,
                "global_solver_consumes_authored_boundary_conditions": ready,
                "full_load_nonlinear_newton_ready": False,
                "calibrated_shell_benchmark_ready": False,
                "material_nonlinear_tangent_ready": False,
            },
            "claim_boundary": {
                "closed": [
                    "uncoarsened MGT roundtrip preserves elastic-link endpoints instead of rigid-link coarsening",
                    "real MGT *CONSTRAINT masks are applied as authored restrained DOFs in the global frame-shell solve",
                    "real MGT *ELASTICLINK GEN stiffness rows are assembled as finite springs in the global 6-DOF tangent",
                    "the coupled frame plus source-thickness shell tangent solves with authored supports and finite link springs",
                ],
                "not_closed": [
                    "this remains a linear sparse equilibrium smoke solve, not full-load nonlinear Newton",
                    "shell formulation calibration, openings/local axes, diaphragms, and material nonlinear tangent remain open",
                    "licensed external benchmark and operator-attached real corpus closure are separate external tracks",
                ],
            },
            "blockers": []
            if ready
            else [
                "uncoarsened_boundary_global_equilibrium_not_ready",
            ],
        }
    finally:
        if temp_context is not None:
            temp_context.cleanup()
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--frame-gravity-load-scale", type=float, default=0.01)
    parser.add_argument("--stiffness-scale-to-si", type=float, default=1000.0)
    parser.add_argument("--retain-uncoarsened-artifacts-dir", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_uncoarsened_boundary_global_equilibrium(
        mgt_path=args.mgt_path,
        output_json=args.output_json,
        frame_gravity_load_scale=args.frame_gravity_load_scale,
        stiffness_scale_to_si=args.stiffness_scale_to_si,
        retain_uncoarsened_artifacts_dir=args.retain_uncoarsened_artifacts_dir,
    )
    metrics = payload.get("equilibrium_metrics") if isinstance(payload.get("equilibrium_metrics"), dict) else {}
    boundary = payload.get("boundary_summary") if isinstance(payload.get("boundary_summary"), dict) else {}
    print(
        "mgt-uncoarsened-boundary-global: "
        f"status={payload['status']} springs={boundary.get('finite_spring_component_count')} "
        f"restrained_dof={boundary.get('authored_support_restrained_dof_count')} "
        f"rel={metrics.get('relative_residual_inf')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
