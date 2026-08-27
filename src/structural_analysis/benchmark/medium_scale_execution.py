"""Deterministic current-source medium-scale execution profile.

This profile exercises the public Python 6-DOF linear-static path beyond the
Native Frame Alpha 60-equation bound.  It is intentionally a scale and
cross-backend receipt, not a replacement for the five-case scientific medium
benchmark contract: the generated cases have no independent reference solver,
source licence receipt, or engineer decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from importlib import resources
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence

import jsonschema
import numpy as np
from scipy import __version__ as scipy_version
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh, splu

from structural_analysis import ANALYSIS_ENGINE_VERSION
from structural_analysis.api.core import AnalysisConfig, analyze
from structural_analysis.assembly.linear_static import (
    DOF_LABELS,
    assemble_linear_static_sparse,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.equation_scaling_6dof import (
    create_equation_scaling_6dof,
    scale_linear_system_6dof,
)
from structural_analysis.units.schema import CoordinateSystem, UnitSystem

if sys.platform != "win32":
    import resource
else:  # pragma: no cover - exercised by the separate Windows runner
    resource = None  # type: ignore[assignment]


SCHEMA_VERSION = "medium-scale-current-source-execution.v1"
PROFILE_ID = "python-reference-medium-scale.v1"
GENERATOR_POLICY = "deterministic-generated-frame-truss-five-archetype.v1"
SCHEMA_FILE = "medium_scale_current_source_execution_v1.schema.json"
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NATIVE_FRAME_ALPHA_MAX_FREE_EQUATIONS = 60
MINIMUM_MEDIUM_FREE_EQUATIONS = 257
MAXIMUM_PROFILE_FREE_EQUATIONS = 2_048
RUNTIME_LIMIT_SECONDS = 30.0
WORKER_WALL_LIMIT_SECONDS = 45.0
PEAK_MEMORY_LIMIT_BYTES = 1_073_741_824
CONDITION_ESTIMATE_LIMIT = 1.0e9
SOLVER_TOLERANCE = 1.0e-8


@dataclass(frozen=True)
class MediumScaleCaseSpec:
    case_id: str
    archetype_id: str
    generator: str
    scale_basis: str
    semantic_boundary: str


CASE_SPECS = (
    MediumScaleCaseSpec(
        case_id="generated_steel_moment_frame_3d",
        archetype_id="steel_moment_frame_3d",
        generator="moment_frame",
        scale_basis="4x4 bays-by-grid, 5 stories, 480 free equations",
        semantic_boundary="Generated prismatic 3D frame; no connection or design-code authority.",
    ),
    MediumScaleCaseSpec(
        case_id="generated_braced_truss_tower",
        archetype_id="braced_frame_or_truss_tower",
        generator="truss_tower",
        scale_basis="four-leg, 24-level spatial truss, 288 free equations",
        semantic_boundary="Generated elastic spatial truss; no joint, buckling, or design authority.",
    ),
    MediumScaleCaseSpec(
        case_id="generated_irregular_multistory_frame",
        archetype_id="irregular_multistory_frame",
        generator="irregular_frame",
        scale_basis="3x3 grid, 8 shifted stories, 432 free equations",
        semantic_boundary="Generated geometrically irregular elastic frame; no external validation.",
    ),
    MediumScaleCaseSpec(
        case_id="generated_frame_diaphragm_surrogate",
        archetype_id="frame_shell_diaphragm",
        generator="diaphragm_surrogate",
        scale_basis="4x3 grid, 5 stories, frame plus in-plane truss ties, 360 free equations",
        semantic_boundary=(
            "Frame/truss diaphragm surrogate only; it does not execute or validate a shell element."
        ),
    ),
    MediumScaleCaseSpec(
        case_id="generated_mixed_frame_truss_foundation_surrogate",
        archetype_id="foundation_link_or_mixed_element",
        generator="mixed_frame_truss",
        scale_basis="3x3 grid, 7 stories, frame plus perimeter truss braces, 378 free equations",
        semantic_boundary=(
            "Mixed frame/truss fixed-base surrogate only; no link, spring, soil, or foundation element authority."
        ),
    ),
)


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _frame_materials_and_sections() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]]
]:
    return (
        [
            {
                "id": "STEEL",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        [
            {
                "id": "FRAME",
                "type": "frame",
                "area": 0.025,
                "iy": 1.25e-4,
                "iz": 8.0e-5,
                "torsional_constant": 2.0e-5,
            },
            {"id": "TRUSS", "type": "axial", "area": 0.012},
        ],
    )


def _grid_frame_payload(
    *,
    nx: int,
    ny: int,
    stories: int,
    coordinate: Callable[[int, int, int], tuple[float, float, float]],
    floor_ties: bool = False,
    perimeter_braces: bool = False,
) -> dict[str, Any]:
    nodes = [
        {
            "id": f"N{i}_{j}_{level}",
            "coordinates": list(coordinate(i, j, level)),
        }
        for level in range(stories + 1)
        for j in range(ny)
        for i in range(nx)
    ]
    elements: list[dict[str, Any]] = []
    pairs: set[tuple[str, str, str]] = set()

    def add(first: str, second: str, element_type: str = "frame") -> None:
        pair = tuple(sorted((first, second)))
        identity = (pair[0], pair[1], element_type)
        if identity in pairs:
            return
        pairs.add(identity)
        elements.append(
            {
                "id": f"E{len(elements) + 1:04d}",
                "type": element_type,
                "nodes": [first, second],
                "section": "FRAME" if element_type == "frame" else "TRUSS",
                "material": "STEEL",
            }
        )

    for level in range(1, stories + 1):
        for j in range(ny):
            for i in range(nx):
                add(f"N{i}_{j}_{level - 1}", f"N{i}_{j}_{level}")
        for j in range(ny):
            for i in range(nx - 1):
                add(f"N{i}_{j}_{level}", f"N{i + 1}_{j}_{level}")
        for i in range(nx):
            for j in range(ny - 1):
                add(f"N{i}_{j}_{level}", f"N{i}_{j + 1}_{level}")
        if floor_ties:
            for j in range(ny - 1):
                for i in range(nx - 1):
                    add(
                        f"N{i}_{j}_{level}",
                        f"N{i + 1}_{j + 1}_{level}",
                        "truss",
                    )
        if perimeter_braces:
            for i in range(nx - 1):
                add(
                    f"N{i}_0_{level - 1}",
                    f"N{i + 1}_0_{level}",
                    "truss",
                )
                add(
                    f"N{i}_{ny - 1}_{level}",
                    f"N{i + 1}_{ny - 1}_{level - 1}",
                    "truss",
                )
            for j in range(ny - 1):
                add(
                    f"N0_{j}_{level - 1}",
                    f"N0_{j + 1}_{level}",
                    "truss",
                )
                add(
                    f"N{nx - 1}_{j}_{level}",
                    f"N{nx - 1}_{j + 1}_{level - 1}",
                    "truss",
                )

    top_nodes = [f"N{i}_{j}_{stories}" for j in range(ny) for i in range(nx)]
    loads = [
        {
            "node": node_id,
            "components": {
                "FX": 8.0 + (index % nx),
                "FY": -3.0 - (index % ny),
                "FZ": -12.0,
                "MX": 0.0,
                "MY": 0.0,
                "MZ": 0.0,
            },
        }
        for index, node_id in enumerate(top_nodes)
    ]
    return {
        "nodes": nodes,
        "elements": elements,
        "loads": loads,
        "supports": [
            {"node": f"N{i}_{j}_0", "dofs": "all"} for j in range(ny) for i in range(nx)
        ],
    }


def _moment_frame_payload() -> dict[str, Any]:
    return _grid_frame_payload(
        nx=4,
        ny=4,
        stories=5,
        coordinate=lambda i, j, level: (6.0 * i, 6.0 * j, 3.5 * level),
    )


def _irregular_frame_payload() -> dict[str, Any]:
    return _grid_frame_payload(
        nx=3,
        ny=3,
        stories=8,
        coordinate=lambda i, j, level: (
            6.2 * i + 0.18 * level + (0.12 if level >= 5 and i == 2 else 0.0),
            5.4 * j - 0.11 * level + (0.15 if level >= 3 and j == 0 else 0.0),
            3.2 * level + 0.04 * level * level,
        ),
    )


def _diaphragm_surrogate_payload() -> dict[str, Any]:
    return _grid_frame_payload(
        nx=4,
        ny=3,
        stories=5,
        coordinate=lambda i, j, level: (5.5 * i, 6.0 * j, 3.4 * level),
        floor_ties=True,
    )


def _mixed_frame_truss_payload() -> dict[str, Any]:
    return _grid_frame_payload(
        nx=3,
        ny=3,
        stories=7,
        coordinate=lambda i, j, level: (6.0 * i, 5.5 * j, 3.6 * level),
        perimeter_braces=True,
    )


def _truss_tower_payload() -> dict[str, Any]:
    levels = 24
    nodes: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()

    def node_id(corner: int, level: int) -> str:
        return f"N{corner}_{level}"

    def add(first: str, second: str) -> None:
        pair = tuple(sorted((first, second)))
        if pair in pairs:
            return
        pairs.add(pair)
        elements.append(
            {
                "id": f"E{len(elements) + 1:04d}",
                "type": "truss",
                "nodes": [first, second],
                "section": "TRUSS",
                "material": "STEEL",
            }
        )

    for level in range(levels + 1):
        half_width = 4.5 - 1.5 * level / levels
        z = 2.4 * level
        coordinates = (
            (-half_width, -half_width, z),
            (half_width, -half_width, z),
            (half_width, half_width, z),
            (-half_width, half_width, z),
        )
        for corner, coordinate in enumerate(coordinates):
            nodes.append(
                {"id": node_id(corner, level), "coordinates": list(coordinate)}
            )
        for first, second in ((0, 1), (1, 2), (2, 3), (3, 0), (0, 2), (1, 3)):
            add(node_id(first, level), node_id(second, level))
        if level == 0:
            continue
        for corner in range(4):
            add(node_id(corner, level - 1), node_id(corner, level))
        for first, second in ((0, 1), (1, 2), (2, 3), (3, 0)):
            add(node_id(first, level - 1), node_id(second, level))
            add(node_id(second, level - 1), node_id(first, level))

    return {
        "nodes": nodes,
        "elements": elements,
        "loads": [
            {
                "node": node_id(corner, levels),
                "components": {
                    "FX": 6.0 + corner,
                    "FY": -4.0 + 0.5 * corner,
                    "FZ": -10.0,
                },
            }
            for corner in range(4)
        ],
        "supports": [
            {"node": node_id(corner, 0), "dofs": "all"} for corner in range(4)
        ],
    }


_GENERATORS: Mapping[str, Callable[[], dict[str, Any]]] = {
    "moment_frame": _moment_frame_payload,
    "truss_tower": _truss_tower_payload,
    "irregular_frame": _irregular_frame_payload,
    "diaphragm_surrogate": _diaphragm_surrogate_payload,
    "mixed_frame_truss": _mixed_frame_truss_payload,
}


def case_spec(case_id: str) -> MediumScaleCaseSpec:
    for spec in CASE_SPECS:
        if spec.case_id == case_id:
            return spec
    raise ValueError(f"unknown medium-scale case: {case_id}")


def build_medium_scale_model(case_id: str) -> CanonicalModel:
    """Build one deterministic generated case without tracked large fixtures."""

    spec = case_spec(case_id)
    geometry = _GENERATORS[spec.generator]()
    materials, sections = _frame_materials_and_sections()
    source_payload = {
        "generator_policy": GENERATOR_POLICY,
        "case": asdict(spec),
        **geometry,
        "materials": materials,
        "sections": sections,
    }
    return CanonicalModel(
        schema_version="structural-analysis-canonical-model.v1",
        source_path=f"generated://{PROFILE_ID}/{case_id}",
        source_format="deterministic_generated_medium_scale",
        input_checksum=_sha256_json(source_payload),
        units=UnitSystem(length="m", force="kN"),
        coordinate_system=CoordinateSystem(
            axis_order=("X", "Y", "Z"),
            up_axis="Z",
        ),
        nodes=geometry["nodes"],
        elements=geometry["elements"],
        materials=materials,
        sections=sections,
        loads=geometry["loads"],
        supports=geometry["supports"],
        unsupported_features=[],
        warnings=[],
        metadata={
            "profile_id": PROFILE_ID,
            "generator_policy": GENERATOR_POLICY,
            "archetype_id": spec.archetype_id,
            "scientific_medium_benchmark_credit": False,
            "semantic_boundary": spec.semantic_boundary,
        },
    )


def _response_projection(result: Any) -> dict[str, Any]:
    metrics = result.metrics
    vector_families: dict[str, list[float]] = {}
    for family in ("displacements", "reactions"):
        rows = metrics.get(family, {})
        vector_families[family] = [
            float(rows[node_id][label])
            for node_id in sorted(rows)
            for label in DOF_LABELS
        ]
    member_values: list[float] = []
    for member in sorted(
        metrics.get("member_forces", []), key=lambda row: str(row["id"])
    ):
        local = member.get("local_end_forces", {})
        member_values.extend(float(local[key]) for key in sorted(local))
    vector_families["member_forces"] = member_values
    return {
        **vector_families,
        "strain_energy": float(metrics["strain_energy"]),
        "relative_residual": float(metrics["relative_residual"]),
        "free_dof_count": int(metrics["free_dof_count"]),
        "canonical_model_checksum": result.canonical_model_checksum,
    }


def _family_comparison(
    reference: Sequence[float],
    observed: Sequence[float],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    if len(reference) != len(observed):
        return {
            "value_count": len(reference),
            "observed_value_count": len(observed),
            "max_absolute_difference": math.inf,
            "relative_linf_difference": math.inf,
            "absolute_tolerance": absolute_tolerance,
            "relative_tolerance": relative_tolerance,
            "contract_pass": False,
        }
    reference_array = np.asarray(reference, dtype=np.float64)
    observed_array = np.asarray(observed, dtype=np.float64)
    difference = np.abs(reference_array - observed_array)
    max_absolute = float(np.max(difference)) if difference.size else 0.0
    reference_norm = (
        float(np.max(np.abs(reference_array))) if reference_array.size else 0.0
    )
    relative = max_absolute / max(reference_norm, absolute_tolerance)
    return {
        "value_count": len(reference),
        "observed_value_count": len(observed),
        "max_absolute_difference": max_absolute,
        "relative_linf_difference": relative,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "contract_pass": bool(
            np.all(np.isfinite(reference_array))
            and np.all(np.isfinite(observed_array))
            and max_absolute <= absolute_tolerance + relative_tolerance * reference_norm
        ),
    }


def _cross_backend_comparison(
    sparse_projection: Mapping[str, Any],
    dense_projection: Mapping[str, Any],
) -> dict[str, Any]:
    tolerances = {
        "displacements": (1.0e-10, 1.0e-8),
        "reactions": (1.0e-7, 1.0e-8),
        "member_forces": (1.0e-7, 1.0e-8),
        "strain_energy": (1.0e-9, 1.0e-8),
    }
    families: dict[str, Any] = {}
    for family, (absolute, relative) in tolerances.items():
        sparse_value = sparse_projection[family]
        dense_value = dense_projection[family]
        if family == "strain_energy":
            sparse_value = [float(sparse_value)]
            dense_value = [float(dense_value)]
        families[family] = _family_comparison(
            dense_value,
            sparse_value,
            absolute_tolerance=absolute,
            relative_tolerance=relative,
        )
    return {
        "reference_backend": "numpy_linalg_solve_dense",
        "observed_backend": "scipy_sparse_spsolve_cpu",
        "families": families,
        "contract_pass": all(row["contract_pass"] for row in families.values()),
        "authority_boundary": (
            "Cross-backend same-implementation comparison; not an independent solver reference."
        ),
    }


def _assembly_and_conditioning(model: CanonicalModel) -> dict[str, Any]:
    assembly, unsupported = assemble_linear_static_sparse(model)
    if assembly is None or unsupported:
        raise RuntimeError(f"medium sparse assembly blocked: {unsupported}")
    constrained = set(assembly.constrained_dofs)
    active = set(assembly.active_dofs)
    free = sorted(active - constrained)
    free_stiffness = assembly.stiffness[np.ix_(free, free)]
    assert isinstance(free_stiffness, csr_matrix)
    free_loads = assembly.loads[free]
    scaling = create_equation_scaling_6dof(
        source_identity_hash=model.canonical_model_checksum,
        node_coordinates_m=assembly.node_coordinates,
        reference_equation_load=assembly.loads,
        free_dofs=free,
    )
    scaled, _, _ = scale_linear_system_6dof(
        free_stiffness,
        free_loads,
        free,
        scaling,
    )
    assert isinstance(scaled, csr_matrix)
    scaled = scaled.tocsr()
    scaled.sort_indices()
    symmetry_difference = scaled - scaled.T
    symmetry_error = (
        float(np.max(np.abs(symmetry_difference.data)))
        if symmetry_difference.nnz
        else 0.0
    )
    factorization_start = time.perf_counter()
    factorization = splu(scaled.tocsc())
    factorization_seconds = time.perf_counter() - factorization_start
    u_diagonal = np.abs(np.asarray(factorization.U.diagonal(), dtype=np.float64))
    pivot_ratio = float(np.min(u_diagonal) / np.max(u_diagonal))
    initial_vector = np.ones(scaled.shape[0], dtype=np.float64)
    minimum_eigenvalue = float(
        eigsh(
            scaled,
            k=1,
            sigma=0.0,
            which="LM",
            return_eigenvectors=False,
            v0=initial_vector,
            tol=1.0e-6,
            maxiter=20_000,
        )[0]
    )
    maximum_eigenvalue = float(
        eigsh(
            scaled,
            k=1,
            which="LA",
            return_eigenvectors=False,
            v0=initial_vector,
            tol=1.0e-6,
            maxiter=20_000,
        )[0]
    )
    condition_estimate = maximum_eigenvalue / minimum_eigenvalue
    sparse_assembly_pass = bool(
        assembly.stiffness_storage == "scipy_sparse_csr"
        and scaled.nnz > scaled.shape[0]
        and symmetry_error <= 1.0e-9
    )
    factorization_pass = bool(
        factorization.L.nnz > 0
        and factorization.U.nnz > 0
        and np.all(np.isfinite(u_diagonal))
        and pivot_ratio > 0.0
    )
    conditioning_pass = bool(
        math.isfinite(condition_estimate)
        and minimum_eigenvalue > 0.0
        and condition_estimate <= CONDITION_ESTIMATE_LIMIT
    )
    return {
        "global_equation_count": int(assembly.stiffness.shape[0]),
        "active_equation_count": len(active),
        "free_equation_count": len(free),
        "sparse_storage": assembly.stiffness_storage,
        "free_matrix_nonzero_count": int(free_stiffness.nnz),
        "scaled_matrix_nonzero_count": int(scaled.nnz),
        "scaled_symmetry_linf": symmetry_error,
        "factorization_backend": "scipy_superlu_splu",
        "factorization_seconds": factorization_seconds,
        "factor_l_nonzero_count": int(factorization.L.nnz),
        "factor_u_nonzero_count": int(factorization.U.nnz),
        "superlu_u_diagonal_pivot_ratio": pivot_ratio,
        "condition_estimator": "scaled_spd_shift_invert_extreme_eigenvalue_ratio_arpack",
        "minimum_scaled_eigenvalue": minimum_eigenvalue,
        "maximum_scaled_eigenvalue": maximum_eigenvalue,
        "scaled_condition_estimate_2": condition_estimate,
        "scaled_condition_estimate_limit": CONDITION_ESTIMATE_LIMIT,
        "exact_condition_number_status": "unsupported_exact_system_over_256_equations",
        "sparse_assembly_gate_pass": sparse_assembly_pass,
        "factorization_gate_pass": factorization_pass,
        "conditioning_gate_pass": conditioning_pass,
        "contract_pass": sparse_assembly_pass
        and factorization_pass
        and conditioning_pass,
    }


def _peak_memory() -> tuple[int, str]:
    if resource is not None:
        maximum_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        memory_bytes = maximum_rss if sys.platform == "darwin" else maximum_rss * 1024
        return memory_bytes, "resource.getrusage(RUSAGE_SELF).ru_maxrss"

    import ctypes  # pragma: no cover - Windows-only stdlib path
    from ctypes import wintypes  # pragma: no cover - Windows-only stdlib path

    class ProcessMemoryCounters(ctypes.Structure):  # pragma: no cover
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()  # pragma: no cover
    counters.cb = ctypes.sizeof(counters)  # pragma: no cover
    process = ctypes.windll.kernel32.GetCurrentProcess()  # pragma: no cover
    if not ctypes.windll.psapi.GetProcessMemoryInfo(  # pragma: no cover
        process, ctypes.byref(counters), counters.cb
    ):
        raise OSError("GetProcessMemoryInfo failed")  # pragma: no cover
    return int(
        counters.PeakWorkingSetSize
    ), "Windows GetProcessMemoryInfo PeakWorkingSetSize"


def execute_medium_scale_case(case_id: str) -> dict[str, Any]:
    """Execute a case inside one isolated worker process."""

    spec = case_spec(case_id)
    started = time.perf_counter()
    model = build_medium_scale_model(case_id)
    diagnostics = _assembly_and_conditioning(model)
    config_sparse = AnalysisConfig(
        analysis_type="linear_static",
        matrix_backend="scipy_sparse_spsolve_cpu",
        tolerance=SOLVER_TOLERANCE,
    )
    config_dense = AnalysisConfig(
        analysis_type="linear_static",
        matrix_backend="numpy_linalg_solve_dense",
        tolerance=SOLVER_TOLERANCE,
    )

    sparse_started = time.perf_counter()
    sparse_first = analyze(model, config_sparse)
    sparse_first_seconds = time.perf_counter() - sparse_started
    repeat_started = time.perf_counter()
    sparse_repeat = analyze(model, config_sparse)
    sparse_repeat_seconds = time.perf_counter() - repeat_started
    dense_started = time.perf_counter()
    dense = analyze(model, config_dense)
    dense_seconds = time.perf_counter() - dense_started

    sparse_projection = _response_projection(sparse_first)
    repeat_projection = _response_projection(sparse_repeat)
    dense_projection = _response_projection(dense)
    sparse_digest = _sha256_json(sparse_projection)
    repeat_digest = _sha256_json(repeat_projection)
    comparison = _cross_backend_comparison(sparse_projection, dense_projection)
    deterministic_pass = sparse_digest == repeat_digest
    solver_runs = (sparse_first, sparse_repeat, dense)
    solver_gate_pass = all(
        result.status == "ready"
        and not result.unsupported_features
        and result.metrics.get("fallback_used") is False
        and result.metrics.get("regularization_used") is False
        and float(result.metrics.get("relative_residual", math.inf)) <= SOLVER_TOLERANCE
        for result in solver_runs
    )
    sparse_path_gate_pass = all(
        result.metrics.get("matrix_backend") == "scipy_sparse_spsolve_cpu"
        and result.metrics.get("sparse_backend_used") is True
        and result.metrics.get("stiffness_storage") == "scipy_sparse_csr"
        for result in (sparse_first, sparse_repeat)
    )
    size_gate_pass = (
        MINIMUM_MEDIUM_FREE_EQUATIONS
        <= diagnostics["free_equation_count"]
        <= MAXIMUM_PROFILE_FREE_EQUATIONS
    )
    execution_seconds = time.perf_counter() - started
    runtime_gate_pass = bool(
        execution_seconds <= RUNTIME_LIMIT_SECONDS
        and sparse_first_seconds <= RUNTIME_LIMIT_SECONDS
        and sparse_repeat_seconds <= RUNTIME_LIMIT_SECONDS
        and dense_seconds <= RUNTIME_LIMIT_SECONDS
    )
    peak_memory_bytes, peak_memory_measurement = _peak_memory()
    memory_gate_pass = peak_memory_bytes <= PEAK_MEMORY_LIMIT_BYTES
    gates = {
        "medium_size": size_gate_pass,
        "sparse_assembly": diagnostics["sparse_assembly_gate_pass"],
        "sparse_factorization": diagnostics["factorization_gate_pass"],
        "conditioning": diagnostics["conditioning_gate_pass"],
        "solver_residual_and_status": solver_gate_pass,
        "sparse_product_path": sparse_path_gate_pass,
        "dense_sparse_comparison": comparison["contract_pass"],
        "deterministic_result": deterministic_pass,
        "runtime": runtime_gate_pass,
        "peak_memory": memory_gate_pass,
        "crash_free": True,
        "oom_free": True,
    }
    contract_pass = all(gates.values())
    return {
        "schema_version": "medium-scale-current-source-case.v1",
        "profile_id": PROFILE_ID,
        "case_id": case_id,
        "archetype_id": spec.archetype_id,
        "generator_policy": GENERATOR_POLICY,
        "scale_basis": spec.scale_basis,
        "semantic_boundary": spec.semantic_boundary,
        "model": {
            "input_checksum": model.input_checksum,
            "canonical_model_checksum": model.canonical_model_checksum,
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
        },
        "assembly_and_conditioning": diagnostics,
        "solver": {
            "solver_id": sparse_first.solver,
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "tolerance": SOLVER_TOLERANCE,
            "sparse_backend": "scipy_sparse_spsolve_cpu",
            "dense_reference_backend": "numpy_linalg_solve_dense",
            "sparse_first_seconds": sparse_first_seconds,
            "sparse_repeat_seconds": sparse_repeat_seconds,
            "dense_seconds": dense_seconds,
            "sparse_first_relative_residual": float(
                sparse_first.metrics["relative_residual"]
            ),
            "sparse_repeat_relative_residual": float(
                sparse_repeat.metrics["relative_residual"]
            ),
            "dense_relative_residual": float(dense.metrics["relative_residual"]),
        },
        "comparison": comparison,
        "determinism": {
            "projection": (
                "displacements_reactions_member_local_forces_energy_residual.v1"
            ),
            "first_sha256": sparse_digest,
            "repeat_sha256": repeat_digest,
            "exact_match": deterministic_pass,
        },
        "resources": {
            "execution_seconds": execution_seconds,
            "runtime_limit_seconds": RUNTIME_LIMIT_SECONDS,
            "peak_memory_bytes": peak_memory_bytes,
            "peak_memory_limit_bytes": PEAK_MEMORY_LIMIT_BYTES,
            "measurement": peak_memory_measurement,
        },
        "gates": gates,
        "crashed": False,
        "oom": False,
        "technical_execution_credit": contract_pass,
        "scientific_medium_benchmark_credit": False,
        "native_medium_product_authority": False,
        "contract_pass": contract_pass,
        "authority_blockers": [
            "independent_reference_solver_receipt_missing",
            "scientific_medium_artifact_chain_missing",
            "engineer_decision_receipt_missing",
            "native_frame_alpha_free_equation_limit_exceeded",
        ],
    }


def _worker_failure(
    case_id: str, *, kind: str, detail: str, wall_seconds: float
) -> dict[str, Any]:
    return {
        "schema_version": "medium-scale-current-source-case.v1",
        "profile_id": PROFILE_ID,
        "case_id": case_id,
        "worker_failure": {"kind": kind, "detail": detail},
        "worker_wall_seconds": wall_seconds,
        "crashed": kind in {"worker_nonzero_exit", "worker_signal"},
        "oom": "memory" in detail.lower() or "oom" in detail.lower(),
        "technical_execution_credit": False,
        "scientific_medium_benchmark_credit": False,
        "native_medium_product_authority": False,
        "contract_pass": False,
        "authority_blockers": [kind],
    }


def run_isolated_case(
    *,
    case_id: str,
    worker_command: Sequence[str],
    timeout_seconds: float = WORKER_WALL_LIMIT_SECONDS,
) -> dict[str, Any]:
    """Run one case in a child so crash, timeout, and peak RSS are observable."""

    environment = dict(os.environ)
    environment.update(
        {
            "OPENBLAS_CORETYPE": "Haswell",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        }
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [*worker_command, "--worker", case_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        return _worker_failure(
            case_id,
            kind="worker_timeout",
            detail=str(exc),
            wall_seconds=time.perf_counter() - started,
        )
    wall_seconds = time.perf_counter() - started
    if completed.returncode != 0:
        kind = "worker_signal" if completed.returncode < 0 else "worker_nonzero_exit"
        return _worker_failure(
            case_id,
            kind=kind,
            detail=(completed.stderr or completed.stdout)[-2_000:],
            wall_seconds=wall_seconds,
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _worker_failure(
            case_id,
            kind="worker_output_invalid",
            detail=str(exc),
            wall_seconds=wall_seconds,
        )
    if not isinstance(payload, dict) or payload.get("case_id") != case_id:
        return _worker_failure(
            case_id,
            kind="worker_identity_mismatch",
            detail="worker receipt is not an object bound to the requested case",
            wall_seconds=wall_seconds,
        )
    payload["worker_wall_seconds"] = wall_seconds
    payload.setdefault("gates", {})["worker_wall_runtime"] = (
        wall_seconds <= timeout_seconds
    )
    payload["contract_pass"] = bool(
        payload.get("contract_pass")
        and payload["gates"]["worker_wall_runtime"]
        and payload.get("crashed") is False
        and payload.get("oom") is False
    )
    payload["technical_execution_credit"] = payload["contract_pass"]
    return payload


def validate_medium_scale_execution_receipt(payload: Mapping[str, Any]) -> None:
    schema = json.loads(
        resources.files("structural_analysis")
        .joinpath("schemas", SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(payload)
    errors: list[str] = []
    cases = payload["cases"]
    expected_case_ids = [spec.case_id for spec in CASE_SPECS]
    observed_case_ids = [row["case_id"] for row in cases]
    if observed_case_ids != expected_case_ids:
        errors.append("case_identity_or_order_mismatch")
    technical_count = sum(row["technical_execution_credit"] is True for row in cases)
    scientific_count = sum(
        row["scientific_medium_benchmark_credit"] is True for row in cases
    )
    native_count = sum(row["native_medium_product_authority"] is True for row in cases)
    summary = payload["summary"]
    expected_summary_counts = {
        "executed_case_count": len(cases),
        "technical_execution_credit_count": technical_count,
        "scientific_medium_benchmark_credit_count": scientific_count,
        "native_medium_product_authority_count": native_count,
    }
    for key, expected in expected_summary_counts.items():
        if summary[key] != expected:
            errors.append(f"summary_count_mismatch:{key}")
    for row in cases:
        if row["contract_pass"] is True:
            if row["technical_execution_credit"] is not True:
                errors.append(f"case_contract_without_credit:{row['case_id']}")
            if not all(row["gates"].values()):
                errors.append(f"case_contract_with_failed_gate:{row['case_id']}")
            diagnostics = row["assembly_and_conditioning"]
            if not (
                payload["policy"]["minimum_medium_free_equations"]
                <= diagnostics["free_equation_count"]
                <= payload["policy"]["maximum_profile_free_equations"]
            ):
                errors.append(f"case_medium_size_out_of_policy:{row['case_id']}")
            if (
                diagnostics["scaled_condition_estimate_2"]
                > payload["policy"]["scaled_condition_estimate_limit"]
            ):
                errors.append(f"case_condition_limit_exceeded:{row['case_id']}")
            if (
                row["resources"]["execution_seconds"]
                > payload["policy"]["runtime_limit_seconds"]
            ):
                errors.append(f"case_runtime_limit_exceeded:{row['case_id']}")
            if (
                row["resources"]["peak_memory_bytes"]
                > payload["policy"]["peak_memory_limit_bytes"]
            ):
                errors.append(f"case_memory_limit_exceeded:{row['case_id']}")
        elif row["technical_execution_credit"] is True:
            errors.append(f"case_credit_without_contract:{row['case_id']}")
    aggregate_should_pass = bool(
        payload["source_tree_clean"]
        and observed_case_ids == expected_case_ids
        and technical_count == len(CASE_SPECS)
        and all(row["contract_pass"] is True for row in cases)
    )
    if payload["contract_pass"] is not aggregate_should_pass:
        errors.append("aggregate_contract_pass_mismatch")
    expected_status = (
        "technical_execution_ready_authority_blocked"
        if aggregate_should_pass
        else "technical_execution_blocked"
    )
    if payload["status"] != expected_status:
        errors.append("aggregate_status_mismatch")
    if summary["all_case_ids_match_policy"] is not (
        observed_case_ids == expected_case_ids
    ):
        errors.append("summary_case_identity_mismatch")
    if summary["all_technical_execution_gates_pass"] is not (
        technical_count == len(CASE_SPECS)
    ):
        errors.append("summary_technical_gate_mismatch")
    if errors:
        raise ValueError("medium-scale receipt semantic mismatch: " + ",".join(errors))


def build_medium_scale_execution_receipt(
    *,
    source_commit_sha: str,
    source_tree_clean: bool,
    worker_command: Sequence[str],
) -> dict[str, Any]:
    if not SOURCE_SHA_RE.fullmatch(source_commit_sha):
        raise ValueError("source_commit_sha must be a lowercase 40-character Git SHA")
    cases = [
        run_isolated_case(case_id=spec.case_id, worker_command=worker_command)
        for spec in CASE_SPECS
    ]
    technical_count = sum(
        row.get("technical_execution_credit") is True for row in cases
    )
    scientific_count = sum(
        row.get("scientific_medium_benchmark_credit") is True for row in cases
    )
    native_count = sum(
        row.get("native_medium_product_authority") is True for row in cases
    )
    all_case_ids_match = [row.get("case_id") for row in cases] == [
        spec.case_id for spec in CASE_SPECS
    ]
    contract_pass = bool(
        source_tree_clean
        and all_case_ids_match
        and technical_count == len(CASE_SPECS)
        and all(row.get("contract_pass") is True for row in cases)
    )
    blockers = [
        "independent_reference_solver_receipts_missing",
        "scientific_medium_benchmark_artifact_chains_missing",
        "native_frame_alpha_free_equation_limit_60",
        "native_sparse_production_profile_missing",
        "shell_link_foundation_product_paths_unsupported",
    ]
    if not source_tree_clean:
        blockers.append("source_tree_not_clean")
    if technical_count != len(CASE_SPECS):
        blockers.append(
            f"technical_medium_scale_execution_incomplete:{technical_count}/{len(CASE_SPECS)}"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "generator_policy": GENERATOR_POLICY,
        "source_commit_sha": source_commit_sha,
        "source_tree_clean": source_tree_clean,
        "environment": {
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "numpy_version": np.__version__,
            "scipy_version": scipy_version,
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "threading_policy": {
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "PYTHONHASHSEED": "0",
            },
        },
        "policy": {
            "required_case_count": len(CASE_SPECS),
            "minimum_medium_free_equations": MINIMUM_MEDIUM_FREE_EQUATIONS,
            "maximum_profile_free_equations": MAXIMUM_PROFILE_FREE_EQUATIONS,
            "native_frame_alpha_max_free_equations": NATIVE_FRAME_ALPHA_MAX_FREE_EQUATIONS,
            "runtime_limit_seconds": RUNTIME_LIMIT_SECONDS,
            "worker_wall_limit_seconds": WORKER_WALL_LIMIT_SECONDS,
            "peak_memory_limit_bytes": PEAK_MEMORY_LIMIT_BYTES,
            "scaled_condition_estimate_limit": CONDITION_ESTIMATE_LIMIT,
            "solver_tolerance": SOLVER_TOLERANCE,
        },
        "cases": cases,
        "summary": {
            "required_case_count": len(CASE_SPECS),
            "executed_case_count": len(cases),
            "technical_execution_credit_count": technical_count,
            "scientific_medium_benchmark_credit_count": scientific_count,
            "native_medium_product_authority_count": native_count,
            "all_case_ids_match_policy": all_case_ids_match,
            "all_technical_execution_gates_pass": technical_count == len(CASE_SPECS),
            "scientific_medium_benchmark_5_of_5": scientific_count == len(CASE_SPECS),
            "native_medium_product_authority_5_of_5": native_count == len(CASE_SPECS),
        },
        "status": (
            "technical_execution_ready_authority_blocked"
            if contract_pass
            else "technical_execution_blocked"
        ),
        "contract_pass": contract_pass,
        "release_authority": False,
        "blockers_remaining": sorted(set(blockers)),
        "claim_boundary": (
            "Five deterministic generated medium-scale cases exercise current-source Python "
            "linear Frame/Truss sparse assembly, SuperLU factorization, scaled conditioning, "
            "dense/sparse response agreement, repeat determinism, runtime, peak-memory, crash, "
            "and OOM gates. The dense comparison is the same implementation and is not external "
            "V&V. The generated shell/foundation archetype rows are explicit frame/truss "
            "surrogates. This receipt grants no scientific medium-benchmark, Native medium, "
            "shell, link/foundation, design, commercial-equivalence, or release authority."
        ),
    }
    validate_medium_scale_execution_receipt(payload)
    return payload


def json_text(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


__all__ = [
    "CASE_SPECS",
    "GENERATOR_POLICY",
    "PROFILE_ID",
    "SCHEMA_VERSION",
    "build_medium_scale_execution_receipt",
    "build_medium_scale_model",
    "execute_medium_scale_case",
    "json_text",
    "run_isolated_case",
    "validate_medium_scale_execution_receipt",
]
