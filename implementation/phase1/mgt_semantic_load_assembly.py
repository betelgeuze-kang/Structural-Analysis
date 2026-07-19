#!/usr/bin/env python3
"""Fail-closed assembly of supported authored MIDAS MGT static loads.

The narrow v1 contract consumes parser-preserved nodal loads and uniform
global-direction PLATE/FACE pressure rows. It deliberately blocks selfweight,
projected/nonuniform pressure, envelope combinations, and unknown unit systems
instead of replacing them with benchmark proxies.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

import numpy as np


MGT_SEMANTIC_LOAD_ASSEMBLY_SCHEMA_VERSION = "mgt-semantic-load-assembly.v1"
MGT_SEMANTIC_LOAD_ASSEMBLY_CLAIM_BOUNDARY = (
    "Consumes authored MGT nodal loads and uniform unprojected global-direction "
    "PLATE/FACE pressures in an explicit force/length unit system. Selfweight, "
    "projected or nonuniform pressure, envelope selection, follower loads, "
    "production load recovery, and G1 closure remain outside this contract."
)


class MgtSemanticLoadContractError(ValueError):
    """Stable fail-closed semantic-load error with a machine-readable code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail)
        super().__init__(f"{self.reason_code}: {self.detail}")


def _fail(reason_code: str, detail: str) -> None:
    raise MgtSemanticLoadContractError(reason_code, detail)


def _array_hash(values: np.ndarray, *, dtype: str) -> str:
    canonical = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    return "sha256:" + hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _normalized_name(value: Any) -> str:
    return str(value or "").strip().upper()


def _dict_rows(value: Any, *, path: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", f"{path} must be a list of objects")
    return [dict(row) for row in value]


def _finite_float(value: Any, *, path: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", f"{path} must be numeric")
    if not math.isfinite(result):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", f"{path} must be finite")
    return result


def _model_and_loads(
    model_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(model_payload, Mapping):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", "model_payload must be an object")
    raw_model = model_payload.get("model", model_payload)
    if not isinstance(raw_model, dict):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", "model must be an object")
    loads = raw_model.get("loads")
    if not isinstance(loads, dict):
        _fail("ERR_MGT_SEMANTIC_LOAD_PAYLOAD_INVALID", "model.loads must be an object")
    return raw_model, loads


def _unit_scales(model: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    units = model.get("units")
    if not isinstance(units, dict):
        _fail("ERR_MGT_SEMANTIC_LOAD_UNIT_MISSING", "model.units is required")
    force = _normalized_name(units.get("force"))
    length = _normalized_name(units.get("length"))
    force_scales = {"N": 1.0, "KN": 1000.0}
    if force not in force_scales or length != "M":
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_UNIT_UNSUPPORTED",
            f"supported units are N/M and KN/M, received {force or '?'}"
            f"/{length or '?'}",
        )
    return force_scales[force], 1.0, {
        "source_force_unit": force,
        "source_length_unit": length,
        "force_to_newton": force_scales[force],
        "length_to_metre": 1.0,
        "pressure_to_n_per_m2": force_scales[force],
        "moment_to_n_m": force_scales[force],
    }


def _resolve_target_factors(
    loads: dict[str, Any],
    *,
    load_case: str | None,
    load_combination: str | None,
) -> tuple[dict[str, float], dict[str, Any]]:
    case_target = _normalized_name(load_case)
    combination_target = _normalized_name(load_combination)
    if bool(case_target) == bool(combination_target):
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_TARGET_INVALID",
            "exactly one of load_case or load_combination is required",
        )

    static_rows = _dict_rows(loads.get("static_load_cases"), path="static_load_cases")
    authored_names = {
        _normalized_name(row.get("name")): str(row.get("name", "")).strip()
        for row in static_rows
        if _normalized_name(row.get("name"))
    }
    for collection_name in ("nodal_loads", "selfweight", "pressure_loads"):
        for row in _dict_rows(loads.get(collection_name), path=collection_name):
            normalized = _normalized_name(row.get("load_case"))
            if normalized:
                authored_names.setdefault(normalized, str(row.get("load_case", "")).strip())

    if case_target:
        if case_target not in authored_names:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_CASE_NOT_FOUND",
                f"load case {load_case!r} is not authored",
            )
        return {case_target: 1.0}, {
            "target_kind": "static_load_case",
            "target_name": authored_names[case_target],
            "combination_expansion_mode": None,
        }

    combination_rows = _dict_rows(
        loads.get("load_combinations"),
        path="load_combinations",
    )
    matches = [
        row
        for row in combination_rows
        if _normalized_name(row.get("name")) == combination_target
    ]
    if len(matches) != 1:
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_COMBINATION_NOT_FOUND",
            f"load combination {load_combination!r} did not resolve uniquely",
        )
    combination = matches[0]
    expansion_mode = str(combination.get("expansion_mode") or "").strip()
    if expansion_mode != "linear_combination":
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_ENVELOPE_UNSUPPORTED",
            f"combination expansion mode {expansion_mode or 'missing'} is unsupported",
        )
    raw_factors = combination.get("expanded_factor_map")
    if not isinstance(raw_factors, dict) or not raw_factors:
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_COMBINATION_INVALID",
            "expanded_factor_map is required for a linear combination",
        )
    factors: dict[str, float] = {}
    for raw_name, raw_factor in raw_factors.items():
        normalized = _normalized_name(raw_name)
        if normalized not in authored_names:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_CASE_NOT_FOUND",
                f"combination references unknown case {raw_name!r}",
            )
        factors[normalized] = _finite_float(
            raw_factor,
            path=f"expanded_factor_map.{raw_name}",
        )
    return factors, {
        "target_kind": "linear_load_combination",
        "target_name": str(combination.get("name", "")).strip(),
        "combination_expansion_mode": expansion_mode,
    }


def _validate_topology(
    *,
    node_id: np.ndarray,
    node_xyz: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    node_ids = np.asarray(node_id, dtype=np.int64)
    coordinates = np.asarray(node_xyz, dtype=np.float64)
    element_ids = np.asarray(elem_id, dtype=np.int64)
    type_codes = np.asarray(elem_type_code, dtype=np.int32)
    pointers = np.asarray(conn_ptr, dtype=np.int64)
    connectivity = np.asarray(conn_idx, dtype=np.int64)
    if node_ids.ndim != 1 or coordinates.shape != (node_ids.size, 3):
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "node arrays are inconsistent")
    if element_ids.ndim != 1 or type_codes.shape != element_ids.shape:
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "element arrays are inconsistent")
    if pointers.shape != (element_ids.size + 1,):
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "conn_ptr length is invalid")
    if (
        pointers[0] != 0
        or pointers[-1] != connectivity.size
        or np.any(np.diff(pointers) < 0)
    ):
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "connectivity CSR is invalid")
    if not np.all(np.isfinite(coordinates)):
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "node coordinates are non-finite")
    if connectivity.size and (
        int(np.min(connectivity)) < 0 or int(np.max(connectivity)) >= node_ids.size
    ):
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "connectivity index is out of range")
    if np.unique(node_ids).size != node_ids.size or np.unique(element_ids).size != element_ids.size:
        _fail("ERR_MGT_SEMANTIC_LOAD_TOPOLOGY_INVALID", "node and element IDs must be unique")
    return node_ids, coordinates, element_ids, type_codes, pointers, connectivity


def _surface_area_m2(points: np.ndarray) -> float:
    if points.shape[0] == 3:
        return 0.5 * float(
            np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0]))
        )
    if points.shape[0] == 4:
        first = 0.5 * float(
            np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0]))
        )
        second = 0.5 * float(
            np.linalg.norm(np.cross(points[2] - points[0], points[3] - points[0]))
        )
        return first + second
    return 0.0


def assemble_mgt_semantic_reference_load(
    *,
    model_payload: Mapping[str, Any],
    node_id: np.ndarray,
    node_xyz: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    load_case: str | None = None,
    load_combination: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Assemble one supported authored load target into global SI DOFs."""

    model, loads = _model_and_loads(model_payload)
    force_scale, length_scale, unit_contract = _unit_scales(model)
    factors, target = _resolve_target_factors(
        loads,
        load_case=load_case,
        load_combination=load_combination,
    )
    (
        node_ids,
        coordinates,
        element_ids,
        type_codes,
        pointers,
        connectivity,
    ) = _validate_topology(
        node_id=node_id,
        node_xyz=node_xyz,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
    )
    node_index = {int(value): index for index, value in enumerate(node_ids.tolist())}
    element_index = {
        int(value): index for index, value in enumerate(element_ids.tolist())
    }
    dof_count = int(node_ids.size) * 6
    reference_load_n = np.zeros(dof_count, dtype=np.float64)

    all_nodal_rows = _dict_rows(loads.get("nodal_loads"), path="nodal_loads")
    all_selfweight_rows = _dict_rows(
        loads.get("selfweight"),
        path="selfweight",
    )
    all_pressure_rows = _dict_rows(
        loads.get("pressure_loads"),
        path="pressure_loads",
    )
    unbound_source_row_counts = {
        "nodal_loads": sum(
            not _normalized_name(row.get("load_case"))
            for row in all_nodal_rows
        ),
        "selfweight": sum(
            not _normalized_name(row.get("load_case"))
            for row in all_selfweight_rows
        ),
        "pressure_loads": sum(
            not _normalized_name(row.get("load_case"))
            for row in all_pressure_rows
        ),
    }
    if any(unbound_source_row_counts.values()):
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_UNBOUND_ROWS",
            "unbound authored rows prevent complete static-case accounting",
        )
    selected_selfweight = [
        row
        for row in all_selfweight_rows
        if _normalized_name(row.get("load_case")) in factors
        and factors[_normalized_name(row.get("load_case"))] != 0.0
    ]
    if selected_selfweight:
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_SELFWEIGHT_UNSUPPORTED",
            "selected target contains authored selfweight rows",
        )

    nodal_rows = [
        row
        for row in all_nodal_rows
        if _normalized_name(row.get("load_case")) in factors
    ]
    pressure_rows = [
        row
        for row in all_pressure_rows
        if _normalized_name(row.get("load_case")) in factors
    ]
    nodal_target_count = 0
    pressure_target_count = 0
    pressure_area_m2 = 0.0
    nodal_force_n = np.zeros(3, dtype=np.float64)
    nodal_moment_n_m = np.zeros(3, dtype=np.float64)
    pressure_force_n = np.zeros(3, dtype=np.float64)

    for row_index, row in enumerate(nodal_rows):
        case_name = _normalized_name(row.get("load_case"))
        factor = factors[case_name]
        raw_node_ids = row.get("node_ids")
        if not isinstance(raw_node_ids, list) or not raw_node_ids:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_NODAL_ROW_INVALID",
                f"nodal row {row_index} has no node_ids",
            )
        force = np.asarray(
            [
                _finite_float(row.get(key), path=f"nodal[{row_index}].{key}")
                for key in ("fx", "fy", "fz")
            ],
            dtype=np.float64,
        ) * (factor * force_scale)
        moment = np.asarray(
            [
                _finite_float(row.get(key), path=f"nodal[{row_index}].{key}")
                for key in ("mx", "my", "mz")
            ],
            dtype=np.float64,
        ) * (factor * force_scale * length_scale)
        for raw_node_id in raw_node_ids:
            try:
                index = node_index[int(raw_node_id)]
            except (KeyError, TypeError, ValueError):
                _fail(
                    "ERR_MGT_SEMANTIC_LOAD_NODE_NOT_FOUND",
                    f"nodal row {row_index} references node {raw_node_id!r}",
                )
            base = 6 * index
            reference_load_n[base : base + 3] += force
            reference_load_n[base + 3 : base + 6] += moment
            nodal_force_n += force
            nodal_moment_n_m += moment
            nodal_target_count += 1

    direction_by_name = {
        "GX": np.asarray([1.0, 0.0, 0.0]),
        "GY": np.asarray([0.0, 1.0, 0.0]),
        "GZ": np.asarray([0.0, 0.0, 1.0]),
    }
    for row_index, row in enumerate(pressure_rows):
        signature = (
            _normalized_name(row.get("command")),
            _normalized_name(row.get("element_type")),
            _normalized_name(row.get("load_type")),
        )
        if signature != ("PRES", "PLATE", "FACE"):
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_PRESSURE_TYPE_UNSUPPORTED",
                f"pressure row {row_index} has signature {signature}",
            )
        direction_name = _normalized_name(row.get("direction"))
        if direction_name not in direction_by_name:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_PRESSURE_DIRECTION_UNSUPPORTED",
                f"pressure row {row_index} direction {direction_name or 'missing'} is unsupported",
            )
        if _normalized_name(row.get("projected")) != "NO":
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_PROJECTED_PRESSURE_UNSUPPORTED",
                f"pressure row {row_index} is projected or missing its projection flag",
            )
        pressure = _finite_float(
            row.get("uniform_pressure"),
            path=f"pressure[{row_index}].uniform_pressure",
        )
        corners = row.get("corner_pressures")
        if not isinstance(corners, list) or len(corners) != 4:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_PRESSURE_ROW_INVALID",
                f"pressure row {row_index} has no four-corner contract",
            )
        corner_values = [
            _finite_float(value, path=f"pressure[{row_index}].corner_pressures")
            for value in corners
        ]
        if any(abs(value) > 1.0e-12 for value in corner_values):
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_NONUNIFORM_PRESSURE_UNSUPPORTED",
                f"pressure row {row_index} has nonzero corner values",
            )
        raw_element_ids = row.get("element_ids")
        if not isinstance(raw_element_ids, list) or not raw_element_ids:
            _fail(
                "ERR_MGT_SEMANTIC_LOAD_PRESSURE_ROW_INVALID",
                f"pressure row {row_index} has no element_ids",
            )
        case_name = _normalized_name(row.get("load_case"))
        factor = factors[case_name]
        direction = direction_by_name[direction_name]
        for raw_element_id in raw_element_ids:
            try:
                index = element_index[int(raw_element_id)]
            except (KeyError, TypeError, ValueError):
                _fail(
                    "ERR_MGT_SEMANTIC_LOAD_ELEMENT_NOT_FOUND",
                    f"pressure row {row_index} references element {raw_element_id!r}",
                )
            if int(type_codes[index]) != 2:
                _fail(
                    "ERR_MGT_SEMANTIC_LOAD_PRESSURE_TOPOLOGY_INVALID",
                    f"element {raw_element_id!r} is not a PLATE row",
                )
            connection = np.asarray(
                connectivity[pointers[index] : pointers[index + 1]],
                dtype=np.int64,
            )
            if connection.size not in (3, 4) or np.unique(connection).size != connection.size:
                _fail(
                    "ERR_MGT_SEMANTIC_LOAD_PRESSURE_TOPOLOGY_INVALID",
                    f"element {raw_element_id!r} must have three or four unique nodes",
                )
            points = coordinates[connection]
            area_m2 = _surface_area_m2(points)
            if not math.isfinite(area_m2) or area_m2 <= 1.0e-12:
                _fail(
                    "ERR_MGT_SEMANTIC_LOAD_PRESSURE_TOPOLOGY_INVALID",
                    f"element {raw_element_id!r} has zero surface area",
                )
            total_force = (
                direction
                * pressure
                * factor
                * force_scale
                * area_m2
            )
            nodal_share = total_force / float(connection.size)
            for node in connection.tolist():
                base = 6 * int(node)
                reference_load_n[base : base + 3] += nodal_share
            pressure_force_n += total_force
            pressure_area_m2 += area_m2
            pressure_target_count += 1

    if not np.all(np.isfinite(reference_load_n)):
        _fail("ERR_MGT_SEMANTIC_LOAD_ASSEMBLY_NONFINITE", "assembled vector is non-finite")
    if float(np.linalg.norm(reference_load_n, ord=np.inf)) <= 0.0:
        _fail("ERR_MGT_SEMANTIC_LOAD_ZERO_VECTOR", "selected target assembled a zero vector")
    nodal_dof_matrix = reference_load_n.reshape((-1, 6))
    assembled_force_n = np.sum(nodal_dof_matrix[:, :3], axis=0)
    assembled_applied_moment_n_m = np.sum(nodal_dof_matrix[:, 3:], axis=0)
    expected_force_n = nodal_force_n + pressure_force_n
    force_error_n = assembled_force_n - expected_force_n
    applied_moment_error_n_m = assembled_applied_moment_n_m - nodal_moment_n_m
    resultant_moment_about_origin_n_m = (
        np.sum(np.cross(coordinates, nodal_dof_matrix[:, :3]), axis=0)
        + assembled_applied_moment_n_m
    )
    force_tolerance_n = max(
        1.0e-8,
        float(np.linalg.norm(expected_force_n, ord=np.inf)) * 1.0e-12,
    )
    moment_tolerance_n_m = max(
        1.0e-8,
        float(np.linalg.norm(nodal_moment_n_m, ord=np.inf)) * 1.0e-12,
    )
    resultant_gate = bool(
        float(np.linalg.norm(force_error_n, ord=np.inf)) <= force_tolerance_n
        and float(np.linalg.norm(applied_moment_error_n_m, ord=np.inf))
        <= moment_tolerance_n_m
    )
    if not resultant_gate:
        _fail(
            "ERR_MGT_SEMANTIC_LOAD_RESULTANT_MISMATCH",
            "assembled DOF vector does not reproduce authored resultants",
        )

    sorted_factors = {
        name: float(factors[name]) for name in sorted(factors)
    }
    metadata = {
        "schema_version": MGT_SEMANTIC_LOAD_ASSEMBLY_SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        **target,
        "case_factors": sorted_factors,
        "unit_contract": unit_contract,
        "global_dof_count": dof_count,
        "node_count": int(node_ids.size),
        "element_count": int(element_ids.size),
        "source_row_counts": {
            "nodal_loads": int(len(all_nodal_rows)),
            "selfweight": int(len(all_selfweight_rows)),
            "pressure_loads": int(len(all_pressure_rows)),
        },
        "unbound_source_row_counts": {
            key: int(value)
            for key, value in unbound_source_row_counts.items()
        },
        "selected_target_row_counts": {
            "nodal_loads": int(len(nodal_rows)),
            "selfweight": int(len(selected_selfweight)),
            "pressure_loads": int(len(pressure_rows)),
        },
        "selected_target_rows_consumed": {
            "nodal_loads": int(len(nodal_rows)),
            "selfweight": 0,
            "pressure_loads": int(len(pressure_rows)),
        },
        "selected_case_row_accounting_exact": True,
        "unsupported_selected_row_count": 0,
        "nodal_load_row_count_consumed": int(len(nodal_rows)),
        "nodal_load_target_count_consumed": int(nodal_target_count),
        "pressure_load_row_count_consumed": int(len(pressure_rows)),
        "pressure_load_element_count_consumed": int(pressure_target_count),
        "selfweight_row_count_consumed": 0,
        "pressure_loaded_area_m2": float(pressure_area_m2),
        "nodal_force_resultant_n": nodal_force_n.tolist(),
        "pressure_force_resultant_n": pressure_force_n.tolist(),
        "assembled_force_resultant_n": assembled_force_n.tolist(),
        "authored_nodal_moment_resultant_n_m": nodal_moment_n_m.tolist(),
        "assembled_applied_moment_resultant_n_m": (
            assembled_applied_moment_n_m.tolist()
        ),
        "resultant_moment_about_origin_n_m": (
            resultant_moment_about_origin_n_m.tolist()
        ),
        "resultant_force_error_inf_n": float(
            np.linalg.norm(force_error_n, ord=np.inf)
        ),
        "resultant_applied_moment_error_inf_n_m": float(
            np.linalg.norm(applied_moment_error_n_m, ord=np.inf)
        ),
        "resultant_gate_passed": resultant_gate,
        "reference_load_inf_n": float(
            np.linalg.norm(reference_load_n, ord=np.inf)
        ),
        "reference_load_l1_n": float(np.linalg.norm(reference_load_n, ord=1)),
        "reference_load_hash": _array_hash(reference_load_n, dtype="<f8"),
        "node_id_hash": _array_hash(node_ids, dtype="<i8"),
        "element_id_hash": _array_hash(element_ids, dtype="<i8"),
        "connectivity_pointer_hash": _array_hash(pointers, dtype="<i8"),
        "connectivity_index_hash": _array_hash(connectivity, dtype="<i8"),
        "source_mgt_nodal_load_rows_consumed": bool(nodal_rows),
        "source_mgt_pressure_load_rows_consumed": bool(pressure_rows),
        "source_mgt_selfweight_rows_consumed": False,
        "source_mgt_load_combination_consumed": bool(load_combination),
        "actual_mgt_semantic_load_case_consumed": bool(load_case),
        "actual_mgt_semantic_load_target_consumed": True,
        "production_load_case_claim": False,
        "promotes_g1_closure": False,
        "unsupported_features": [
            "selfweight",
            "projected_pressure",
            "nonuniform_pressure",
            "envelope_selection",
            "follower_load",
        ],
        "claim_boundary": MGT_SEMANTIC_LOAD_ASSEMBLY_CLAIM_BOUNDARY,
    }
    return reference_load_n, metadata


__all__ = [
    "MGT_SEMANTIC_LOAD_ASSEMBLY_CLAIM_BOUNDARY",
    "MGT_SEMANTIC_LOAD_ASSEMBLY_SCHEMA_VERSION",
    "MgtSemanticLoadContractError",
    "assemble_mgt_semantic_reference_load",
]
