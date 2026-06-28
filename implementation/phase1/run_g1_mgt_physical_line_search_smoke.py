#!/usr/bin/env python3
"""Non-promoting real-MGT physical-consistent line-search smoke (F2a).

Checks whether the opt-in physical-consistent global Newton operator and the
physical-residual line-search preview can be *wired up* against a real MGT model
(not the representative system from F1), in a fail-closed, non-promoting form.

F2a is NOT a 0.656 breakthrough and does NOT regenerate the 0.656 continuation
checkpoint (that is F2b). It builds the physical residual closure from an available
real MGT model at a lightweight reference state and attempts:
  - physical residual evaluation,
  - matrix-free physical-consistent JVP + parity,
  - a bounded matrix-free Newton direction solve + physical-residual line-search.

Every failure mode is reported as an explicit machine-readable ``reason_code``
rather than crashing. Output is an untracked ``*.local.json``; the default solver
path is unchanged and no G1 gate is promoted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from g1_global_newton_operator import (
    DEFAULT_GLOBAL_NEWTON_OPERATOR,
    GLOBAL_NEWTON_OPERATOR_CURRENT,
    GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    jvp_parity_report,
    normalize_global_newton_operator,
    operator_uses_solver_normalization_lambda,
    physical_consistent_jvp,
)
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
    solve_physical_newton_direction,
)


SCHEMA_VERSION = "g1-mgt-physical-line-search-smoke.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_mgt_physical_line_search_smoke.local.json"
DEFAULT_MGT_MODEL = HERE / "open_data" / "midas" / "midas_generator_33.optimized.mgt"

# Reason codes (machine-readable, fail-closed).
PASS = "PASS"
ERR_MGT_INPUT_MISSING = "ERR_MGT_INPUT_MISSING"
ERR_MGT_STATE_BUILD_FAILED = "ERR_MGT_STATE_BUILD_FAILED"
ERR_PHYSICAL_RESIDUAL_CLOSURE_FAILED = "ERR_PHYSICAL_RESIDUAL_CLOSURE_FAILED"
ERR_JVP_PARITY_FAILED = "ERR_JVP_PARITY_FAILED"
ERR_LINE_SEARCH_NO_DESCENT = "ERR_LINE_SEARCH_NO_DESCENT"
ERR_MEMORY_BUDGET_EXCEEDED = "ERR_MEMORY_BUDGET_EXCEEDED"
ERR_NAN_RESIDUAL = "ERR_NAN_RESIDUAL"
ERR_OPERATOR_SHAPE_MISMATCH = "ERR_OPERATOR_SHAPE_MISMATCH"
ERR_DIRECTION_SOLVE_BLOCKED = "ERR_DIRECTION_SOLVE_BLOCKED"

# Lightweight smoke budget: refuse to build dense operators beyond this size.
DEFAULT_FREE_DOF_BUDGET = 250_000

ReducedResidualFn = Callable[[np.ndarray], np.ndarray]


def _empty_jvp_parity(reason: str | None = None) -> dict[str, Any]:
    return {"attempted": bool(reason is not None), "pass": False, "reason_code": reason}


def _empty_line_search(reason: str | None = None) -> dict[str, Any]:
    return {
        "attempted": bool(reason is not None),
        "status": "blocked" if reason else "not_attempted",
        "accepted_alpha": None,
        "residual_reduction_ratio": None,
        "reason_code": reason,
    }


def _report(
    *,
    status: str,
    reason_code: str,
    uses_real_mgt_model: bool,
    mgt_source: str | None,
    operator: str,
    load_scale: float | None = None,
    checkpoint_kind: str = "none_or_lightweight_state",
    jvp_parity: dict[str, Any] | None = None,
    line_search_preview: dict[str, Any] | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_smoke_only": True,
        "promotes_g1_closure": False,
        "status": status,
        "reason_code": reason_code,
        "uses_real_mgt_model": bool(uses_real_mgt_model),
        "mgt_source": mgt_source,
        "global_newton_operator": operator,
        "baseline_operator": GLOBAL_NEWTON_OPERATOR_CURRENT,
        "default_global_newton_operator": DEFAULT_GLOBAL_NEWTON_OPERATOR,
        "physical_residual_formula": "R(u, lambda)=F_int(u)-lambda*F_ext",
        "uses_solver_normalization_lambda": operator_uses_solver_normalization_lambda(operator),
        "normalization_lambda_excluded": not operator_uses_solver_normalization_lambda(operator),
        "load_scale": load_scale,
        "checkpoint_kind": checkpoint_kind,
        "jvp_parity": jvp_parity or _empty_jvp_parity(),
        "line_search_preview": line_search_preview or _empty_line_search(),
        "resource_usage": resource_usage or {
            "dof_count": None, "node_count": None,
            "element_count": None, "peak_memory_mb": None,
        },
        "f2b_scope_note": (
            "0.656 continuation checkpoint regeneration/application is F2b; not done here"
        ),
        "claim_boundary": "non_promoting_real_mgt_smoke_only",
    }


def run_smoke_from_closure(
    residual_fn: ReducedResidualFn,
    x0: np.ndarray,
    *,
    operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    checkpoint_kind: str = "none_or_lightweight_state",
    direction_mode: str = "matrix_free_gmres",
    gmres_maxiter: int = 150,
    free_dof_budget: int = DEFAULT_FREE_DOF_BUDGET,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the fail-closed smoke given a reduced-space physical residual closure.

    ``residual_fn(x)`` must accept and return arrays of the same length (the free
    DOF count). This is the testable core: synthetic closures exercise every
    fail-closed branch without depending on a real MGT file.
    """
    operator = normalize_global_newton_operator(operator)
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)

    if n > int(free_dof_budget) and direction_mode == "representative_direct":
        return _report(
            status="blocked", reason_code=ERR_MEMORY_BUDGET_EXCEEDED,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            resource_usage=resource_usage,
        )

    # 1) base physical residual: finiteness + shape contract
    try:
        r0 = np.asarray(residual_fn(x0), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 - fail closed with reason
        return _report(
            status="blocked", reason_code=ERR_PHYSICAL_RESIDUAL_CLOSURE_FAILED,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=_empty_jvp_parity(f"closure_eval_raised:{type(exc).__name__}"),
            resource_usage=resource_usage,
        )
    if r0.shape != x0.shape:
        return _report(
            status="blocked", reason_code=ERR_OPERATOR_SHAPE_MISMATCH,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=_empty_jvp_parity("residual_shape_ne_state_shape"),
            resource_usage=resource_usage,
        )
    if not bool(np.all(np.isfinite(r0))):
        return _report(
            status="blocked", reason_code=ERR_NAN_RESIDUAL,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=_empty_jvp_parity("nan_in_base_residual"),
            resource_usage=resource_usage,
        )

    # 2) physical-consistent JVP parity
    rng = np.random.default_rng(0)
    v = rng.standard_normal(n)
    v = v / max(float(np.linalg.norm(v)), 1.0e-30)
    try:
        parity = jvp_parity_report(residual_fn, x0, v)
        parity["attempted"] = True
    except Exception as exc:  # noqa: BLE001
        return _report(
            status="blocked", reason_code=ERR_JVP_PARITY_FAILED,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=_empty_jvp_parity(f"jvp_raised:{type(exc).__name__}"),
            resource_usage=resource_usage,
        )
    if not bool(np.all(np.isfinite(physical_consistent_jvp(residual_fn, x0, v)))):
        parity["reason_code"] = "nonfinite_jvp"
        return _report(
            status="blocked", reason_code=ERR_JVP_PARITY_FAILED,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=parity, resource_usage=resource_usage,
        )

    # 3) bounded matrix-free Newton direction solve
    p, solve_meta = solve_physical_newton_direction(
        residual_fn, x0, mode=direction_mode, gmres_maxiter=gmres_maxiter,
    )
    if p is None or not solve_meta.get("converged", False):
        ls = _empty_line_search(solve_meta.get("reason_code", "direction_solve_failed"))
        ls["status"] = "blocked"
        return _report(
            status="blocked", reason_code=ERR_DIRECTION_SOLVE_BLOCKED,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=parity, line_search_preview=ls, resource_usage=resource_usage,
        )

    # 4) physical-residual backtracking line-search
    jvp_action = physical_consistent_jvp(residual_fn, x0, p)
    ls_raw = physical_residual_backtracking_line_search(
        residual_fn, x0, p, jvp_action=jvp_action, alphas=DEFAULT_ALPHAS,
    )
    line_search = {
        "attempted": True,
        "status": ls_raw.get("status"),
        "accepted_alpha": ls_raw.get("accepted_alpha"),
        "residual_before_n": ls_raw.get("residual_before_n"),
        "residual_after_n": ls_raw.get("residual_after_n"),
        "residual_reduction_ratio": ls_raw.get("residual_reduction_ratio"),
        "beats_d_tiny_alpha_threshold": ls_raw.get("beats_d_tiny_alpha_threshold"),
        "beats_d_residual_reduction_baseline": ls_raw.get("beats_d_residual_reduction_baseline"),
        "accepted_predicted_over_actual_mismatch_ratio": ls_raw.get(
            "accepted_predicted_over_actual_mismatch_ratio"
        ),
        "reason_code": ls_raw.get("reason_code"),
    }
    if ls_raw.get("status") != "ready":
        return _report(
            status="review", reason_code=ERR_LINE_SEARCH_NO_DESCENT,
            uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
            operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
            jvp_parity=parity, line_search_preview=line_search, resource_usage=resource_usage,
        )
    return _report(
        status="ready", reason_code=PASS,
        uses_real_mgt_model=uses_real_mgt_model, mgt_source=mgt_source,
        operator=operator, load_scale=load_scale, checkpoint_kind=checkpoint_kind,
        jvp_parity=parity, line_search_preview=line_search, resource_usage=resource_usage,
    )


def build_mgt_physical_residual_closure(
    *,
    mgt_path: Path,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    apply_shell_material_tangent: bool = False,
    frame_service_tangent_source: str = "real_per_element",
) -> tuple[ReducedResidualFn, np.ndarray, dict[str, Any]]:
    """Build a reduced free-space physical residual closure from a real MGT model.

    Returns ``(residual_fn, x0_free, meta)``. Not unit tested (exercised locally);
    the orchestrator maps any failure here to a fail-closed reason code.
    """
    # Imports are local so the testable core does not require the heavy solver stack.
    from parse_mgt_section_material_properties import (
        load_mgt_section_material_properties,
        parse_mgt_elastic_links,
        parse_mgt_support_constraints,
    )
    from run_mgt_coupled_frame_surface_sparse_equilibrium import _select_frame_elements
    from run_mgt_full_frame_6dof_sparse_equilibrium import (
        DOF_PER_NODE,
        _beam_end_offset_lookup,
        _component_gravity_axial_forces,
        _element_angle_array_from_props,
    )
    from run_mgt_uncoarsened_boundary_global_equilibrium import (
        _assemble_elastic_link_springs,
        _authored_support_restraints,
    )
    from mgt_physical_residual_assembly import (
        assemble_newton_tangent_stiffness,
        assemble_physical_internal_forces,
        assemble_physical_residual,
    )
    from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly
    from mgt_shell_load_path import surface_pressure_load_path_filter

    roundtrip_npz = roundtrip_npz or mgt_path.with_suffix(".roundtrip.npz")
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    props = load_mgt_section_material_properties(mgt_path)
    section_props = props.get("sections") or {}
    material_props = props.get("materials") or {}
    plate_thickness_props = props.get("plate_thicknesses") or {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

    with np.load(roundtrip_npz, allow_pickle=False) as ar:
        node_id = np.asarray(ar["node_id"], dtype=np.int64)
        node_xyz = np.asarray(ar["node_xyz"], dtype=np.float64)
        edge_index = np.asarray(ar["edge_index"], dtype=np.int64)
        elem_id = np.asarray(ar["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(ar["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(ar["elem_section_id"], dtype=np.int32)
        elem_material_id = np.asarray(ar["elem_material_id"], dtype=np.int32)
        elem_angle_deg = (
            np.asarray(ar["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in ar.files
            else _element_angle_array_from_props(props, elem_id)
        )
        conn_ptr = np.asarray(ar["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(ar["elem_conn_idx"], dtype=np.int64)

    frame_elements, _ = _select_frame_elements(
        node_xyz=node_xyz, edge_index=edge_index, elem_id=elem_id,
        elem_type_code=elem_type_code, elem_section_id=elem_section_id,
        elem_material_id=elem_material_id, elem_angle_deg=elem_angle_deg,
        beam_end_offsets=beam_end_offsets,
    )
    node_index = {int(n): i for i, n in enumerate(node_id.tolist())}
    restrained_raw, _ = _authored_support_restraints(constraints=constraints, node_index=node_index)
    restrained = {int(x) for x in restrained_raw}
    spring_stiffness, _ = _assemble_elastic_link_springs(
        links=elastic_links, node_index=node_index,
        dof_count=int(node_xyz.shape[0]) * DOF_PER_NODE,
        stiffness_scale_to_si=stiffness_scale_to_si,
    )
    pressure_allowed, _ = surface_pressure_load_path_filter(
        frame_elements=frame_elements, elem_type_code=elem_type_code,
        conn_ptr=conn_ptr, conn_idx=conn_idx, restrained=restrained, policy="all_components",
    )
    base_axial = _component_gravity_axial_forces(
        elements=frame_elements, node_xyz=node_xyz,
        section_props=section_props, material_props=material_props,
    )
    shell_cache: dict[str, Any] = {}
    ffa = {int(e): float(f) * frame_gravity_load_scale * load_scale for e, f in base_axial.items()}
    frame_force_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz, frame_elements=frame_elements,
        section_props=section_props, material_props=material_props,
        element_axial_forces=ffa, include_geometric=True,
    )
    ndof = int(node_xyz.shape[0]) * DOF_PER_NODE
    u0 = np.zeros(ndof, dtype=np.float64)

    service_tangent_source = str(frame_service_tangent_source)
    if service_tangent_source == "placeholder_1mpa":
        service_tangent = {int(e.elem_id): 1.0 for e in frame_elements}
    elif service_tangent_source == "real_per_element":
        from run_mgt_direct_residual_newton_probe import _service_tangent_by_element

        service_tangent, _svc_meta = _service_tangent_by_element(
            elements=frame_elements, node_xyz=node_xyz, u=u0, material_props=material_props,
        )
    else:
        raise ValueError(
            f"unknown frame_service_tangent_source {frame_service_tangent_source!r}; "
            "expected 'real_per_element' or 'placeholder_1mpa'"
        )
    _svc_values = np.asarray(list(service_tangent.values()), dtype=np.float64)
    stiffness, assembled_f_ext, _ = assemble_newton_tangent_stiffness(
        u=u0, node_xyz=node_xyz, frame_elements=frame_elements,
        elem_type_code=elem_type_code, elem_section_id=elem_section_id,
        elem_material_id=elem_material_id, conn_ptr=conn_ptr, conn_idx=conn_idx,
        section_props=section_props, material_props=material_props,
        plate_thickness_props=plate_thickness_props, spring_stiffness=spring_stiffness,
        base_axial_forces=base_axial, frame_gravity_load_scale=frame_gravity_load_scale,
        load_scale=load_scale, service_tangent_by_element=service_tangent,
        service_material_meta={}, shell_pressure_load_allowed_surface_elements=pressure_allowed,
    )
    diag = np.asarray(stiffness.diagonal(), dtype=np.float64)
    active = np.where(np.abs(diag) > 1.0e-9)[0]
    free = np.asarray([i for i in active.tolist() if i not in restrained], dtype=np.int64)
    f_ext = np.asarray(assembled_f_ext, dtype=np.float64)
    # free-space assembled tangent (for F2b-ii-a sparse-direct / ILU solves)
    tangent_csr = stiffness.tocsr()
    tangent_free_csr = tangent_csr[free][:, free].tocsr()

    def residual_fn(x_free: np.ndarray) -> np.ndarray:
        u = u0.copy()
        u[free] = np.asarray(x_free, dtype=np.float64)
        f_int, _ = assemble_physical_internal_forces(
            u=u, node_xyz=node_xyz, frame_elements=frame_elements,
            elem_type_code=elem_type_code, elem_section_id=elem_section_id,
            elem_material_id=elem_material_id, conn_ptr=conn_ptr, conn_idx=conn_idx,
            section_props=section_props, material_props=material_props,
            plate_thickness_props=plate_thickness_props, spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial, frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale, apply_shell_material_tangent=apply_shell_material_tangent,
            shell_operator_cache=shell_cache, frame_force_cache=frame_force_cache,
        )
        residual, _rhs = assemble_physical_residual(u=u, f_ext=f_ext, free=free, f_int=f_int)
        return np.asarray(residual, dtype=np.float64)

    component_shell_cache: dict[str, Any] = {}

    def component_residual_fn(x_free: np.ndarray) -> dict[str, np.ndarray]:
        """Return free-space component internal forces (frame/spring/shell/...).

        The physical residual is sum(components) - load_scale*F_ext; F_ext is
        constant, so component directional derivatives sum to the total JVP.
        """
        u = u0.copy()
        u[free] = np.asarray(x_free, dtype=np.float64)
        _f_int, cmeta = assemble_physical_internal_forces(
            u=u, node_xyz=node_xyz, frame_elements=frame_elements,
            elem_type_code=elem_type_code, elem_section_id=elem_section_id,
            elem_material_id=elem_material_id, conn_ptr=conn_ptr, conn_idx=conn_idx,
            section_props=section_props, material_props=material_props,
            plate_thickness_props=plate_thickness_props, spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial, frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale, apply_shell_material_tangent=apply_shell_material_tangent,
            include_component_forces=True, split_shell_components=True,
            shell_operator_cache=component_shell_cache, frame_force_cache=frame_force_cache,
        )
        comps = cmeta.get("component_forces", {})
        return {name: np.asarray(vals, dtype=np.float64)[free] for name, vals in comps.items()}

    spring_free_csr = spring_stiffness.tocsr()[free][:, free].tocsr()

    def tangent_rebuild_fn(x_free: np.ndarray) -> Any:
        """Re-assemble the regularizable free-space Newton tangent at an arbitrary state.

        Recomputes the per-element service material tangent at the deformed state
        (true-Newton re-linearization) and restricts to the reference free DOF set.
        """
        from run_mgt_direct_residual_newton_probe import _service_tangent_by_element

        u = u0.copy()
        u[free] = np.asarray(x_free, dtype=np.float64)
        state_service_tangent, _m = _service_tangent_by_element(
            elements=frame_elements, node_xyz=node_xyz, u=u, material_props=material_props,
        )
        k_state, _fext, _meta = assemble_newton_tangent_stiffness(
            u=u, node_xyz=node_xyz, frame_elements=frame_elements,
            elem_type_code=elem_type_code, elem_section_id=elem_section_id,
            elem_material_id=elem_material_id, conn_ptr=conn_ptr, conn_idx=conn_idx,
            section_props=section_props, material_props=material_props,
            plate_thickness_props=plate_thickness_props, spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial, frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale, service_tangent_by_element=state_service_tangent,
            service_material_meta={}, shell_pressure_load_allowed_surface_elements=pressure_allowed,
        )
        return k_state.tocsr()[free][:, free].tocsr()

    meta = {
        "dof_count": int(ndof),
        "node_count": int(node_xyz.shape[0]),
        "element_count": int(elem_id.shape[0]),
        "free_dof_count": int(free.size),
        "external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
        "diag_free": np.asarray(diag[free], dtype=np.float64),
        "tangent_free_csr": tangent_free_csr,
        "tangent_free_nnz": int(tangent_free_csr.nnz),
        "component_residual_fn": component_residual_fn,
        "spring_free_csr": spring_free_csr,
        "tangent_rebuild_fn": tangent_rebuild_fn,
        "frame_inputs": {
            "frame_elements": frame_elements,
            "node_xyz": node_xyz,
            "section_props": section_props,
            "material_props": material_props,
            "base_axial": base_axial,
            "frame_gravity_load_scale": float(frame_gravity_load_scale),
            "load_scale": float(load_scale),
            "free": free,
            "u0": u0,
        },
        "frame_service_tangent_source": service_tangent_source,
        "node_id": node_id,
        "free": free,
        "dof_per_node": int(DOF_PER_NODE),
        "frame_service_tangent_stats_mpa": {
            "min": float(np.min(_svc_values)) if _svc_values.size else None,
            "max": float(np.max(_svc_values)) if _svc_values.size else None,
            "mean": float(np.mean(_svc_values)) if _svc_values.size else None,
        },
    }
    return residual_fn, u0[free].copy(), meta


def run_g1_mgt_physical_line_search_smoke(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    load_scale: float = 0.1,
    gmres_maxiter: int = 150,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    operator = normalize_global_newton_operator(global_newton_operator)
    mgt_model = Path(mgt_model)

    if not mgt_model.is_file():
        payload = _report(
            status="blocked", reason_code=ERR_MGT_INPUT_MISSING,
            uses_real_mgt_model=False, mgt_source=str(mgt_model), operator=operator,
        )
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
            )
        except FileNotFoundError as exc:
            payload = _report(
                status="blocked", reason_code=ERR_MGT_STATE_BUILD_FAILED,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), operator=operator,
                jvp_parity=_empty_jvp_parity(f"missing_input:{exc}"),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with reason
            payload = _report(
                status="blocked", reason_code=ERR_MGT_STATE_BUILD_FAILED,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), operator=operator,
                jvp_parity=_empty_jvp_parity(f"{type(exc).__name__}:{exc}"),
            )
        else:
            payload = run_smoke_from_closure(
                residual_fn, x0, operator=operator, uses_real_mgt_model=True,
                mgt_source=str(mgt_model), load_scale=load_scale,
                gmres_maxiter=gmres_maxiter,
                resource_usage={
                    "dof_count": meta["dof_count"], "node_count": meta["node_count"],
                    "element_count": meta["element_count"], "peak_memory_mb": None,
                    "free_dof_count": meta["free_dof_count"],
                },
            )

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument(
        "--global-newton-operator",
        choices=[GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL],
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    )
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument("--gmres-maxiter", type=int, default=150)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_mgt_physical_line_search_smoke(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        global_newton_operator=args.global_newton_operator,
        load_scale=args.load_scale, gmres_maxiter=args.gmres_maxiter,
        output_json=args.output_json,
    )
    print(
        "g1-mgt-physical-line-search-smoke: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"real_mgt={payload['uses_real_mgt_model']} "
        f"jvp_pass={payload['jvp_parity'].get('pass')} "
        f"ls_status={payload['line_search_preview'].get('status')} "
        f"-> {args.output_json}"
    )
    # Smoke is non-promoting: a fail-closed reason is still a successful smoke run.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
