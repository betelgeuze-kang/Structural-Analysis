"""Fail-closed whole-model frame initial-stress assembly for linear buckling."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np

from structural_analysis.assembly.linear_static import assemble_linear_static
from structural_analysis.elements.frame3d import (
    Frame3DProperties,
    frame3d_global_geometric_stiffness,
)
from structural_analysis.model.schema import CanonicalModel


SUPPORTED_BUCKLING_ELEMENT_TYPES = {"frame", "beam", "column"}
GEOMETRIC_STIFFNESS_FORMULATION = (
    "euler_bernoulli_constant_axial_compression_initial_stress_v1"
)
GEOMETRIC_STIFFNESS_SIGN_CONVENTION = (
    "positive_compression_K_minus_lambda_Kg"
)
REFERENCE_AXIAL_FORCE_RELATIVE_TOLERANCE = 1.0e-10
REFERENCE_AXIAL_FORCE_ABSOLUTE_TOLERANCE_KN = 1.0e-12


@dataclass(frozen=True)
class BucklingElementAssemblyRecord:
    element_id: str
    element_type: str
    node_ids: tuple[str, str]
    dofs: tuple[int, ...]
    reference_local_fx_i_kn: float
    reference_local_fx_j_kn: float
    reference_axial_equilibrium_error_kn: float
    reference_compression_force_kn: float
    properties: Frame3DProperties


@dataclass(frozen=True)
class BucklingAssembly:
    stiffness: np.ndarray
    geometric_stiffness: np.ndarray
    constrained_dofs: tuple[int, ...]
    active_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    node_ids: tuple[str, ...]
    node_coordinates: tuple[tuple[float, float, float], ...]
    element_records: tuple[BucklingElementAssemblyRecord, ...]
    reference_load_case: str | None
    reference_compression_scale_kn: float
    warnings: tuple[str, ...]
    geometric_stiffness_formulation: str = GEOMETRIC_STIFFNESS_FORMULATION
    geometric_stiffness_sign_convention: str = GEOMETRIC_STIFFNESS_SIGN_CONVENTION


def assemble_linear_buckling_matrices(
    model: CanonicalModel,
    *,
    reference_member_forces: list[dict[str, Any]],
    load_case: str | None = None,
) -> tuple[BucklingAssembly | None, list[dict[str, Any]]]:
    """Assemble ``K`` and reference-state ``Kg`` from recovered frame forces."""

    unsupported: list[dict[str, Any]] = []
    element_ids: set[str] = set()
    for element in model.elements:
        element_id = str(element.get("id", "")).strip()
        if not element_id or element_id in element_ids:
            unsupported.append(
                {
                    "kind": "buckling_element_id_invalid_or_duplicate",
                    "element": element_id,
                }
            )
        element_ids.add(element_id)
        element_type = str(element.get("type", "")).strip().lower()
        if element_type not in SUPPORTED_BUCKLING_ELEMENT_TYPES:
            unsupported.append(
                {
                    "kind": "buckling_element_not_supported",
                    "element": element_id,
                    "element_type": element.get("type", ""),
                    "detail": (
                        "Whole-model linear buckling v1 assembles initial stress "
                        "for frame/beam/column elements only."
                    ),
                }
            )
    if unsupported:
        return None, unsupported

    linear, linear_unsupported = assemble_linear_static(model, load_case=load_case)
    if linear is None:
        return None, [
            {
                "kind": "buckling_reference_assembly_failed",
                "reference_diagnostics": linear_unsupported,
                "detail": "The reference linear-static assembly did not pass.",
            }
        ]
    if not isinstance(linear.stiffness, np.ndarray):
        return None, [{"kind": "buckling_dense_reference_assembly_required"}]

    force_rows, force_unsupported = _reference_force_rows(reference_member_forces)
    if force_unsupported:
        return None, force_unsupported
    assert force_rows is not None

    axial_rows: list[tuple[Any, float, float, float, float]] = []
    force_scale = 0.0
    for record in linear.element_records:
        if not isinstance(record.properties, Frame3DProperties):
            unsupported.append(
                {
                    "kind": "buckling_element_not_supported",
                    "element": record.element_id,
                    "element_type": record.element_type,
                }
            )
            continue
        row = force_rows.get(record.element_id)
        if row is None:
            unsupported.append(
                {
                    "kind": "buckling_reference_member_force_missing",
                    "element": record.element_id,
                }
            )
            continue
        local = row.get("local_end_forces")
        if not isinstance(local, dict):
            unsupported.append(
                {
                    "kind": "buckling_reference_member_force_invalid",
                    "element": record.element_id,
                }
            )
            continue
        fx_i = _finite_number(local.get("FX_I"))
        fx_j = _finite_number(local.get("FX_J"))
        if fx_i is None or fx_j is None:
            unsupported.append(
                {
                    "kind": "buckling_reference_member_force_invalid",
                    "element": record.element_id,
                    "detail": "Finite local FX_I and FX_J are required.",
                }
            )
            continue
        compression = 0.5 * (fx_i - fx_j)
        equilibrium_error = abs(fx_i + fx_j)
        force_scale = max(force_scale, abs(fx_i), abs(fx_j), abs(compression))
        axial_rows.append(
            (record, fx_i, fx_j, compression, equilibrium_error)
        )
    if unsupported:
        return None, unsupported

    force_tolerance = max(
        REFERENCE_AXIAL_FORCE_ABSOLUTE_TOLERANCE_KN,
        REFERENCE_AXIAL_FORCE_RELATIVE_TOLERANCE * force_scale,
    )
    geometric = np.zeros_like(linear.stiffness, dtype=np.float64)
    records: list[BucklingElementAssemblyRecord] = []
    positive_compression_count = 0
    for record, fx_i, fx_j, compression, equilibrium_error in axial_rows:
        if equilibrium_error > force_tolerance:
            unsupported.append(
                {
                    "kind": "buckling_reference_axial_force_imbalance",
                    "element": record.element_id,
                    "fx_i_kn": fx_i,
                    "fx_j_kn": fx_j,
                    "equilibrium_error_kn": equilibrium_error,
                    "tolerance_kn": force_tolerance,
                }
            )
            continue
        if compression < -force_tolerance:
            unsupported.append(
                {
                    "kind": "buckling_reference_tension_not_supported",
                    "element": record.element_id,
                    "reference_tension_force_kn": -compression,
                    "detail": (
                        "The strict generalized-eigen kernel requires a positive-"
                        "semidefinite compression Kg; tension is not discarded or "
                        "projected."
                    ),
                }
            )
            continue
        effective_compression = compression if compression > force_tolerance else 0.0
        if effective_compression > 0.0:
            positive_compression_count += 1
        element_geometric = frame3d_global_geometric_stiffness(
            record.properties,
            compression_force_kn=effective_compression,
        )
        geometric[np.ix_(record.dofs, record.dofs)] += element_geometric
        records.append(
            BucklingElementAssemblyRecord(
                element_id=record.element_id,
                element_type=record.element_type,
                node_ids=record.node_ids,
                dofs=record.dofs,
                reference_local_fx_i_kn=fx_i,
                reference_local_fx_j_kn=fx_j,
                reference_axial_equilibrium_error_kn=equilibrium_error,
                reference_compression_force_kn=effective_compression,
                properties=record.properties,
            )
        )
    if unsupported:
        return None, unsupported
    if positive_compression_count == 0:
        return None, [
            {
                "kind": "buckling_reference_compression_missing",
                "detail": (
                    "The selected reference load case produces no positive frame "
                    "compression above the force tolerance."
                ),
                "tolerance_kn": force_tolerance,
            }
        ]

    active = set(linear.active_dofs)
    constrained = set(linear.constrained_dofs)
    free_dofs = tuple(sorted(active - constrained))
    if not free_dofs:
        return None, [
            {
                "kind": "buckling_free_active_dofs_missing",
                "active_dof_count": len(active),
                "constrained_dof_count": len(constrained),
            }
        ]
    stiffness = np.asarray(linear.stiffness, dtype=np.float64)
    stiffness = 0.5 * (stiffness + stiffness.T)
    geometric = 0.5 * (geometric + geometric.T)
    return (
        BucklingAssembly(
            stiffness=stiffness,
            geometric_stiffness=geometric,
            constrained_dofs=tuple(sorted(constrained)),
            active_dofs=tuple(sorted(active)),
            free_dofs=free_dofs,
            node_ids=linear.node_ids,
            node_coordinates=linear.node_coordinates,
            element_records=tuple(records),
            reference_load_case=load_case,
            reference_compression_scale_kn=force_scale,
            warnings=(
                "Linear buckling uses axial force from the load-factor-1.0 "
                "small-displacement reference state.",
            ),
        ),
        [],
    )


def _reference_force_rows(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]] | None, list[dict[str, Any]]]:
    result: dict[str, dict[str, Any]] = {}
    unsupported: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            unsupported.append(
                {"kind": "buckling_reference_member_force_invalid", "index": index}
            )
            continue
        element_id = str(row.get("id", "")).strip()
        if not element_id or element_id in result:
            unsupported.append(
                {
                    "kind": "buckling_reference_member_force_id_invalid_or_duplicate",
                    "element": element_id,
                }
            )
            continue
        result[element_id] = row
    return (None if unsupported else result), unsupported


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if np.isfinite(result) else None


def reference_load_vector_hash_payload(
    linear_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Return the stable public load-pattern subset used for provenance hashing."""

    return {
        "external_forces": linear_metrics.get("external_forces", {}),
        "reference_load_factor": 1.0,
        "residual_formula": linear_metrics.get("residual_formula"),
        "solver_path_id": linear_metrics.get("solver_path_id"),
    }


__all__ = [
    "BucklingAssembly",
    "BucklingElementAssemblyRecord",
    "GEOMETRIC_STIFFNESS_FORMULATION",
    "GEOMETRIC_STIFFNESS_SIGN_CONVENTION",
    "SUPPORTED_BUCKLING_ELEMENT_TYPES",
    "assemble_linear_buckling_matrices",
    "reference_load_vector_hash_payload",
]
