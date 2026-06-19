#!/usr/bin/env python3
"""Per load-step equilibrium residual assembler with frozen external load."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from mgt_equilibrium_geometry_contract import EQUILIBRIUM_GEOMETRY_CONTRACT
from mgt_physical_residual_assembly import (
    assemble_equilibrium_operator_stiffness,
    assemble_physical_internal_forces,
    assemble_physical_internal_forces_batch,
    assemble_physical_residual,
)
from mgt_shell_load_path import (
    surface_pressure_load_path_components,  # noqa: F401 - re-exported for legacy test/import surface.
    surface_pressure_load_path_filter,
)
from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly
from mgt_shell_force_based_assembly import _cached_shell_operator
from run_mgt_direct_residual_newton_probe import _active_free
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE, FrameElement


def _surface_pressure_load_path_filter(
    *,
    frame_elements: list[FrameElement],
    elem_type_code: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    restrained: set[int],
    policy: str,
) -> tuple[set[int] | None, dict[str, Any]]:
    return surface_pressure_load_path_filter(
        frame_elements=frame_elements,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        restrained=restrained,
        policy=policy,
    )


def build_equilibrium_step_assembler(
    *,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    spring_stiffness: Any,
    base_axial_forces: dict[int, float],
    frame_gravity_load_scale: float,
    load_scale: float,
    restrained: set[int],
    shell_pressure_load_path_policy: str = "all_components",
) -> tuple[
    Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    dict[str, Any],
]:
    """Build R(u)=F_int(u)-F_ext with F_ext frozen at u=0 for the load step."""
    reference_holder: dict[str, np.ndarray] = {}
    shell_operator_cache: dict[str, Any] = {}
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    pressure_allowed_surface_elements, pressure_load_path_meta = _surface_pressure_load_path_filter(
        frame_elements=frame_elements,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        restrained=restrained,
        policy=shell_pressure_load_path_policy,
    )
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_force_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    hip_backend_holder: dict[str, Any] = {}

    def assemble_residual(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
        include_component_forces: bool = False,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        if residual_only:
            if external_load_override is not None:
                f_ext = np.asarray(external_load_override, dtype=np.float64)
            elif "reference_f_ext" in reference_holder:
                f_ext = reference_holder["reference_f_ext"]
            else:
                residual_only = False
        if residual_only:
            if free_override is not None:
                free = np.asarray(free_override, dtype=np.int64)
            elif "reference_free" in reference_holder:
                free = np.asarray(reference_holder["reference_free"], dtype=np.int64)
            else:
                residual_only = False
        if residual_only:
            f_int, physical_meta = assemble_physical_internal_forces(
                u=u,
                node_xyz=node_xyz,
                frame_elements=frame_elements,
                elem_type_code=elem_type_code,
                elem_section_id=elem_section_id,
                elem_material_id=elem_material_id,
                conn_ptr=conn_ptr,
                conn_idx=conn_idx,
                section_props=section_props,
                material_props=material_props,
                plate_thickness_props=plate_thickness_props,
                spring_stiffness=spring_stiffness,
                base_axial_forces=base_axial_forces,
                frame_gravity_load_scale=frame_gravity_load_scale,
                load_scale=load_scale,
                include_component_forces=include_component_forces,
                shell_operator_cache=shell_operator_cache,
                frame_force_cache=frame_force_cache,
            )
            residual, rhs = assemble_physical_residual(
                u=u,
                f_ext=f_ext,
                free=free,
                f_int=f_int,
            )
            return None, f_ext, free, residual, rhs, {
                **physical_meta,
                "residual_only_assembly": True,
                "residual_only_free_override": bool(free_override is not None),
                "free_dof_count": int(free.size),
                "frozen_external_load": bool("reference_f_ext" in reference_holder),
                "shell_pressure_load_path_meta": pressure_load_path_meta,
                "shell_operator_cache_size": int(len(shell_operator_cache)),
            }
        stiffness, assembled_f_ext, tangent_meta = assemble_equilibrium_operator_stiffness(
            u=u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            restrained=restrained,
            shell_pressure_load_allowed_surface_elements=pressure_allowed_surface_elements,
        )
        _active, free = _active_free(stiffness, restrained)
        f_int, physical_meta = assemble_physical_internal_forces(
            u=u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            include_component_forces=include_component_forces,
            shell_operator_cache=shell_operator_cache,
            frame_force_cache=frame_force_cache,
        )
        if external_load_override is not None:
            f_ext = np.asarray(external_load_override, dtype=np.float64)
        elif "reference_f_ext" in reference_holder:
            f_ext = reference_holder["reference_f_ext"]
        else:
            f_ext = assembled_f_ext
        residual, rhs = assemble_physical_residual(
            u=u,
            f_ext=f_ext,
            free=free,
            f_int=f_int,
        )
        return stiffness, f_ext, free, residual, rhs, {
            **tangent_meta,
            **physical_meta,
            "shell_pressure_load_path_meta": pressure_load_path_meta,
            "active_dof_count": int(_active.size),
            "free_dof_count": int(free.size),
            "frozen_external_load": bool("reference_f_ext" in reference_holder),
            "shell_operator_cache_size": int(len(shell_operator_cache)),
        }

    _reference_stiffness, reference_f_ext, _reference_free, _reference_residual, _reference_rhs, _ = (
        assemble_residual(np.zeros(n_dof, dtype=np.float64))
    )
    reference_holder["reference_f_ext"] = reference_f_ext
    reference_holder["reference_free"] = _reference_free

    def assemble_with_frozen_external_load(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
        include_component_forces: bool = False,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        override = reference_f_ext if external_load_override is None else external_load_override
        return assemble_residual(
            u,
            external_load_override=override,
            include_component_forces=include_component_forces,
            residual_only=residual_only,
            free_override=free_override,
        )
    assemble_with_frozen_external_load.supports_residual_only = True  # type: ignore[attr-defined]

    def evaluate_residual_batch(
        states: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
        free_override: np.ndarray | None = None,
        backend: str = "cpu",
        hipcc: Path = Path("/opt/rocm/bin/hipcc"),
        force_rebuild_hip: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        state_batch = np.asarray(states, dtype=np.float64)
        if state_batch.ndim != 2:
            raise ValueError("states must be a 2D array shaped (batch, n_dof)")
        if int(state_batch.shape[1]) != int(n_dof):
            raise ValueError(f"state n_dof {state_batch.shape[1]} does not match {n_dof}")
        f_ext = (
            np.asarray(external_load_override, dtype=np.float64)
            if external_load_override is not None
            else np.asarray(reference_holder["reference_f_ext"], dtype=np.float64)
        )
        free = (
            np.asarray(free_override, dtype=np.int64)
            if free_override is not None
            else np.asarray(reference_holder["reference_free"], dtype=np.int64)
        )
        backend_name = str(backend or "cpu")
        if backend_name in {"hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"}:
            from mgt_hip_full_residual_backend import (
                HipFullResidualBatchBackend,
                HipFullResidualResidentWorkerBackend,
                HipFullResidualRustFfiBackend,
            )

            holder_key = f"{backend_name}:{Path(hipcc)}:{bool(force_rebuild_hip)}"
            hip_backend = hip_backend_holder.get(holder_key)
            if hip_backend is None:
                reference_u = (
                    state_batch[0]
                    if int(state_batch.shape[0])
                    else np.zeros(int(n_dof), dtype=np.float64)
                )
                shell_stiffness, _shell_meta, _cache_hit = _cached_shell_operator(
                    u=reference_u,
                    node_xyz=node_xyz,
                    elem_type_code=elem_type_code,
                    elem_section_id=elem_section_id,
                    elem_material_id=elem_material_id,
                    conn_ptr=conn_ptr,
                    conn_idx=conn_idx,
                    material_props=material_props,
                    plate_thickness_props=plate_thickness_props,
                    include_membrane=True,
                    shell_operator_cache=shell_operator_cache,
                )
                backend_cls = (
                    HipFullResidualResidentWorkerBackend
                    if backend_name == "hip_full_residual_resident"
                    else HipFullResidualRustFfiBackend
                    if backend_name == "rust_hip_full_residual_ffi"
                    else HipFullResidualBatchBackend
                )
                hip_backend = backend_cls.prepare(
                    frame_dofs=frame_force_cache.dofs,
                    frame_stiffness=frame_force_cache.element_stiffness,
                    shell_csr=shell_stiffness.tocsr(),
                    spring_csr=spring_stiffness.tocsr(),
                    f_ext=f_ext,
                    free=free,
                    hipcc=Path(hipcc),
                    force_rebuild=bool(force_rebuild_hip),
                )
                hip_backend_holder[holder_key] = hip_backend
            residual_batch, batch_meta = hip_backend.evaluate(state_batch, reps=1)
            rhs = np.asarray(f_ext[free], dtype=np.float64)
            return (
                np.asarray(residual_batch, dtype=np.float64),
                free,
                rhs,
                {
                    **batch_meta,
                    "residual_batch_backend": backend_name,
                    "hip_full_residual_batch_replay": True,
                    "hip_full_residual_resident_worker": bool(
                        backend_name == "hip_full_residual_resident"
                    ),
                    "rust_hip_full_residual_ffi_worker": bool(
                        backend_name == "rust_hip_full_residual_ffi"
                    ),
                    "residual_only_assembly": True,
                    "residual_only_free_override": bool(free_override is not None),
                    "shell_operator_cache_size": int(len(shell_operator_cache)),
                    "external_load_source": "reference_configuration",
                    "used_external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
                },
            )
        f_int_batch, batch_meta = assemble_physical_internal_forces_batch(
            u_batch=state_batch,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            shell_operator_cache=shell_operator_cache,
            frame_force_cache=frame_force_cache,
        )
        residual_batch = np.asarray(f_int_batch[:, free] - f_ext[free], dtype=np.float64)
        rhs = np.asarray(f_ext[free], dtype=np.float64)
        return (
            residual_batch,
            free,
            rhs,
            {
                **batch_meta,
                "residual_batch_backend": "cpu_physical_internal_force_batch",
                "hip_full_residual_batch_replay": False,
                "hip_full_residual_resident_worker": False,
                "residual_only_assembly": True,
                "residual_only_free_override": bool(free_override is not None),
                "shell_operator_cache_size": int(len(shell_operator_cache)),
                "external_load_source": "reference_configuration",
                "used_external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
            },
        )

    assemble_with_frozen_external_load.evaluate_residual_batch = evaluate_residual_batch  # type: ignore[attr-defined]
    assemble_with_frozen_external_load.supports_residual_batch = True  # type: ignore[attr-defined]
    assemble_with_frozen_external_load.supports_hip_full_residual_batch = True  # type: ignore[attr-defined]
    assemble_with_frozen_external_load.supports_hip_full_residual_resident_worker = True  # type: ignore[attr-defined]
    assemble_with_frozen_external_load.supports_rust_hip_full_residual_ffi = True  # type: ignore[attr-defined]

    setup_meta = {
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "frozen_load_scale": float(load_scale),
        "reference_f_ext_inf_n": float(np.max(np.abs(reference_f_ext))) if reference_f_ext.size else 0.0,
        "free_dof_count": int(_reference_free.size),
        "shell_pressure_load_path_meta": pressure_load_path_meta,
        "frame_force_fastpath_prepacked": True,
        "frame_force_fastpath_element_count": int(len(frame_elements)),
    }
    return assemble_with_frozen_external_load, setup_meta
