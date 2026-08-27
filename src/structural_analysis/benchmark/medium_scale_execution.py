"""Deterministic current-source medium-scale execution profile.

This profile exercises the public Python 6-DOF linear-static path beyond the
Native Frame Alpha 60-equation bound.  It is intentionally a scale and
cross-backend receipt, not a replacement for the five-case scientific medium
benchmark contract: the generated cases have no independent reference solver,
source licence receipt, or engineer decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
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
from scipy.linalg import eigh
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import splu

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
EIGENPAIR_RESIDUAL_LIMIT = 1.0e-6
SOLVER_TOLERANCE = 1.0e-8
WORKER_FAILURE_KINDS = frozenset(
    {
        "worker_timeout",
        "worker_signal",
        "worker_nonzero_exit",
        "worker_output_invalid",
        "worker_identity_mismatch",
        "worker_contract_invalid",
    }
)
WORKER_CRASH_FAILURE_KINDS = frozenset({"worker_signal", "worker_nonzero_exit"})
RESOURCE_OBSERVATION_AUTHORITY = "non_authoritative_pre_attestation_observation"
RESOURCE_AUTHORITY_REQUIRES = (
    "verified_exact_source_github_provenance_attestation"
)
CLAIM_BOUNDARY = (
    "Five deterministic generated medium-scale cases exercise current-source Python "
    "linear Frame/Truss sparse assembly, SuperLU factorization, scaled conditioning, "
    "dense/sparse response agreement, repeat determinism, runtime, peak-memory, crash, "
    "and OOM gates. The dense comparison is the same implementation and is not external "
    "V&V. The generated shell/foundation archetype rows are explicit frame/truss "
    "surrogates. This receipt grants no scientific medium-benchmark, Native medium, "
    "shell, link/foundation, design, commercial-equivalence, or release authority."
)


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


@lru_cache(maxsize=1)
def _execution_schema() -> dict[str, Any]:
    return json.loads(
        resources.files("structural_analysis")
        .joinpath("schemas", SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )


def _validate_successful_case_schema(payload: Mapping[str, Any]) -> None:
    root_schema = _execution_schema()
    schema = {
        "$schema": root_schema["$schema"],
        "$defs": root_schema["$defs"],
        **root_schema["$defs"]["successfulCase"],
    }
    jsonschema.Draft202012Validator(schema).validate(payload)


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
        "reference_linf_norm": reference_norm,
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


def _symmetric_extreme_eigen_diagnostics(
    matrix: csr_matrix,
) -> tuple[float, float, float, float]:
    """Return algebraic extremes and normalized residuals for a bounded matrix."""

    dense = np.asarray(matrix.toarray(), dtype=np.float64)
    eigenvalues, eigenvectors = eigh(
        dense,
        check_finite=True,
        driver="evd",
    )
    minimum = float(eigenvalues[0])
    maximum = float(eigenvalues[-1])

    def residual(value: float, vector: np.ndarray) -> float:
        applied = np.asarray(matrix @ vector, dtype=np.float64)
        remainder = applied - value * vector
        scale = max(float(np.linalg.norm(applied)), abs(value), 1.0)
        return float(np.linalg.norm(remainder) / scale)

    return (
        minimum,
        maximum,
        residual(minimum, eigenvectors[:, 0]),
        residual(maximum, eigenvectors[:, -1]),
    )


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
    # The generated profile is bounded to 2,048 equations and already executes
    # a dense cross-backend solve.  A symmetric dense eigensolve is therefore a
    # deliberate diagnostic path: unlike shift-invert ARPACK near zero, it
    # cannot silently report the smallest *positive* eigenvalue when a more
    # negative algebraic eigenvalue exists.
    (
        minimum_eigenvalue,
        maximum_eigenvalue,
        minimum_eigenpair_residual,
        maximum_eigenpair_residual,
    ) = _symmetric_extreme_eigen_diagnostics(scaled)
    condition_estimate = (
        maximum_eigenvalue / minimum_eigenvalue
        if minimum_eigenvalue != 0.0
        else sys.float_info.max
    )
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
        and maximum_eigenvalue >= minimum_eigenvalue
        and condition_estimate <= CONDITION_ESTIMATE_LIMIT
        and minimum_eigenpair_residual <= EIGENPAIR_RESIDUAL_LIMIT
        and maximum_eigenpair_residual <= EIGENPAIR_RESIDUAL_LIMIT
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
        "condition_estimator": "scaled_symmetric_algebraic_extreme_eigenvalue_ratio_scipy_eigh",
        "minimum_scaled_eigenvalue": minimum_eigenvalue,
        "maximum_scaled_eigenvalue": maximum_eigenvalue,
        "minimum_eigenpair_relative_residual": minimum_eigenpair_residual,
        "maximum_eigenpair_relative_residual": maximum_eigenpair_residual,
        "eigenpair_relative_residual_limit": EIGENPAIR_RESIDUAL_LIMIT,
        "scaled_condition_estimate_2": condition_estimate,
        "scaled_condition_estimate_limit": CONDITION_ESTIMATE_LIMIT,
        "exact_condition_number_status": "symmetric_dense_eigenvalue_ratio_diagnostic",
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
    run_observations = [
        {
            "run_id": run_id,
            "status": result.status,
            "unsupported_feature_count": len(result.unsupported_features),
            "fallback_used": result.metrics.get("fallback_used"),
            "regularization_used": result.metrics.get("regularization_used"),
            "matrix_backend": result.metrics.get("matrix_backend"),
            "sparse_backend_used": result.metrics.get("sparse_backend_used"),
            "stiffness_storage": result.metrics.get("stiffness_storage"),
            "relative_residual": float(
                result.metrics.get("relative_residual", math.inf)
            ),
        }
        for run_id, result in zip(
            ("sparse_first", "sparse_repeat", "dense_reference"),
            solver_runs,
            strict=True,
        )
    ]
    solver_gate_pass = all(
        row["status"] == "ready"
        and row["unsupported_feature_count"] == 0
        and row["fallback_used"] is False
        and row["regularization_used"] is False
        and row["relative_residual"] <= SOLVER_TOLERANCE
        for row in run_observations
    )
    sparse_path_gate_pass = all(
        row["matrix_backend"] == "scipy_sparse_spsolve_cpu"
        and row["sparse_backend_used"] is True
        and row["stiffness_storage"] == "scipy_sparse_csr"
        for row in run_observations[:2]
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
            "run_observations": run_observations,
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
            "observation_authority": RESOURCE_OBSERVATION_AUTHORITY,
            "authority_requires": RESOURCE_AUTHORITY_REQUIRES,
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


_REPLAY_GATE_KEYS = (
    "medium_size",
    "sparse_assembly",
    "sparse_factorization",
    "conditioning",
    "solver_residual_and_status",
    "sparse_product_path",
    "dense_sparse_comparison",
    "deterministic_result",
    "crash_free",
    "oom_free",
)


def _stable_case_replay_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = payload["assembly_and_conditioning"]
    solver = payload["solver"]
    return {
        "model": payload["model"],
        "assembly_and_conditioning": {
            key: value
            for key, value in diagnostics.items()
            if key != "factorization_seconds"
        },
        "solver": {
            key: value
            for key, value in solver.items()
            if key
            not in {
                "sparse_first_seconds",
                "sparse_repeat_seconds",
                "dense_seconds",
            }
        },
        "comparison": payload["comparison"],
        "determinism": payload["determinism"],
        "gates": {key: payload["gates"][key] for key in _REPLAY_GATE_KEYS},
        "crashed": payload["crashed"],
        "oom": payload["oom"],
    }


def _replay_values_match(observed: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return observed == expected
    if isinstance(expected, int):
        return isinstance(observed, int) and not isinstance(observed, bool) and observed == expected
    if isinstance(expected, float):
        return isinstance(observed, (int, float)) and not isinstance(
            observed, bool
        ) and math.isfinite(float(observed)) and math.isclose(
            float(observed), expected, rel_tol=1.0e-8, abs_tol=1.0e-12
        )
    if isinstance(expected, list):
        return isinstance(observed, list) and len(observed) == len(expected) and all(
            _replay_values_match(left, right)
            for left, right in zip(observed, expected, strict=True)
        )
    if isinstance(expected, Mapping):
        return (
            isinstance(observed, Mapping)
            and set(observed) == set(expected)
            and all(
                _replay_values_match(observed[key], value)
                for key, value in expected.items()
            )
        )
    return observed == expected


@lru_cache(maxsize=len(CASE_SPECS))
def _expected_stable_case_replay(case_id: str) -> dict[str, Any]:
    return _stable_case_replay_projection(execute_medium_scale_case(case_id))


def _failure_indicates_oom(
    *, kind: str, detail: str, returncode: int | None
) -> bool:
    if kind not in WORKER_CRASH_FAILURE_KINDS:
        return False
    # On POSIX a subprocess return code of -9 means SIGKILL.  The kernel's OOM
    # killer is not the only possible source of SIGKILL, but treating it as a
    # possible OOM is the fail-closed resource-accounting choice: the receipt
    # must never claim oom_free after an otherwise silent hard kill.
    if kind == "worker_signal" and returncode == -9:
        return True
    normalized = detail.casefold()
    return any(
        marker in normalized
        for marker in (
            "out of memory",
            "memoryerror",
            "cannot allocate memory",
            "oom",
        )
    )


def _worker_failure(
    case_id: str,
    *,
    kind: str,
    detail: str,
    wall_seconds: float,
    timeout_seconds: float,
    returncode: int | None = None,
) -> dict[str, Any]:
    if kind not in WORKER_FAILURE_KINDS:
        raise ValueError(f"unsupported worker failure kind: {kind}")
    normalized_detail = (
        detail.strip() or f"{kind} without worker output detail"
    )[-4_000:]
    normalized_wall_seconds = max(float(wall_seconds), sys.float_info.epsilon)
    return {
        "schema_version": "medium-scale-current-source-case.v1",
        "profile_id": PROFILE_ID,
        "case_id": case_id,
        "worker_failure": {
            "kind": kind,
            "detail": normalized_detail,
            "returncode": returncode,
        },
        "worker_wall_seconds": normalized_wall_seconds,
        "worker_timeout_limit_seconds": float(timeout_seconds),
        "crashed": kind in WORKER_CRASH_FAILURE_KINDS,
        "oom": _failure_indicates_oom(
            kind=kind,
            detail=normalized_detail,
            returncode=returncode,
        ),
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
            timeout_seconds=timeout_seconds,
        )
    wall_seconds = time.perf_counter() - started
    if wall_seconds > timeout_seconds:
        return _worker_failure(
            case_id,
            kind="worker_timeout",
            detail="worker completed after the configured wall-time limit",
            wall_seconds=wall_seconds,
            timeout_seconds=timeout_seconds,
            returncode=completed.returncode,
        )
    if completed.returncode < 0:
        kind = "worker_signal"
        return _worker_failure(
            case_id,
            kind=kind,
            detail=(completed.stderr or completed.stdout)[-2_000:]
            or f"worker exited with return code {completed.returncode}",
            wall_seconds=wall_seconds,
            timeout_seconds=timeout_seconds,
            returncode=completed.returncode,
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        if completed.returncode != 0:
            return _worker_failure(
                case_id,
                kind="worker_nonzero_exit",
                detail=(completed.stderr or completed.stdout)[-2_000:]
                or f"worker exited with return code {completed.returncode}",
                wall_seconds=wall_seconds,
                timeout_seconds=timeout_seconds,
                returncode=completed.returncode,
            )
        return _worker_failure(
            case_id,
            kind="worker_output_invalid",
            detail=str(exc),
            wall_seconds=wall_seconds,
            timeout_seconds=timeout_seconds,
            returncode=completed.returncode,
        )
    if not isinstance(payload, dict) or payload.get("case_id") != case_id:
        return _worker_failure(
            case_id,
            kind="worker_identity_mismatch",
            detail="worker receipt is not an object bound to the requested case",
            wall_seconds=wall_seconds,
            timeout_seconds=timeout_seconds,
            returncode=completed.returncode,
        )
    try:
        worker_contract_pass = payload.get("contract_pass") is True
        gates = payload.get("gates")
        if not isinstance(gates, dict):
            raise TypeError("worker success receipt gates must be an object")
        payload = dict(payload)
        payload["gates"] = dict(gates)
        payload["worker_wall_seconds"] = wall_seconds
        payload["gates"]["worker_wall_runtime"] = wall_seconds <= timeout_seconds
        payload["contract_pass"] = bool(
            payload.get("contract_pass") is True
            and payload["gates"]["worker_wall_runtime"]
            and payload.get("crashed") is False
            and payload.get("oom") is False
        )
        payload["technical_execution_credit"] = payload["contract_pass"]
        _validate_successful_case_schema(payload)
        expected_returncode = 0 if worker_contract_pass else 1
        if completed.returncode != expected_returncode:
            raise ValueError(
                "worker return code does not match its receipt contract_pass"
            )
    except (jsonschema.ValidationError, KeyError, TypeError, ValueError) as exc:
        return _worker_failure(
            case_id,
            kind="worker_contract_invalid",
            detail=f"{type(exc).__name__}: {exc}",
            wall_seconds=wall_seconds,
            timeout_seconds=timeout_seconds,
            returncode=completed.returncode,
        )
    return payload


def validate_medium_scale_execution_receipt(payload: Mapping[str, Any]) -> None:
    schema = _execution_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(payload)
    errors: list[str] = []
    digest_subject = dict(payload)
    observed_payload_digest = digest_subject.pop("receipt_payload_sha256")
    if observed_payload_digest != _sha256_json(digest_subject):
        errors.append("receipt_payload_digest_mismatch")
    expected_policy = {
        "required_case_count": len(CASE_SPECS),
        "minimum_medium_free_equations": MINIMUM_MEDIUM_FREE_EQUATIONS,
        "maximum_profile_free_equations": MAXIMUM_PROFILE_FREE_EQUATIONS,
        "native_frame_alpha_max_free_equations": (
            NATIVE_FRAME_ALPHA_MAX_FREE_EQUATIONS
        ),
        "runtime_limit_seconds": RUNTIME_LIMIT_SECONDS,
        "worker_wall_limit_seconds": WORKER_WALL_LIMIT_SECONDS,
        "peak_memory_limit_bytes": PEAK_MEMORY_LIMIT_BYTES,
        "scaled_condition_estimate_limit": CONDITION_ESTIMATE_LIMIT,
        "eigenpair_relative_residual_limit": EIGENPAIR_RESIDUAL_LIMIT,
        "solver_tolerance": SOLVER_TOLERANCE,
    }
    if payload["policy"] != expected_policy:
        errors.append("execution_policy_mismatch")
    if payload["environment"]["analysis_engine_version"] != ANALYSIS_ENGINE_VERSION:
        errors.append("environment_engine_version_mismatch")
    expected_environment = {
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
    }
    if payload["environment"] != expected_environment:
        errors.append("execution_environment_mismatch")
    expected_resource_measurement = (
        "Windows GetProcessMemoryInfo PeakWorkingSetSize"
        if sys.platform == "win32"
        else "resource.getrusage(RUSAGE_SELF).ru_maxrss"
    )
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        errors.append("claim_boundary_mismatch")
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
    specifications = {spec.case_id: spec for spec in CASE_SPECS}
    comparison_tolerances = {
        "displacements": (1.0e-10, 1.0e-8),
        "reactions": (1.0e-7, 1.0e-8),
        "member_forces": (1.0e-7, 1.0e-8),
        "strain_energy": (1.0e-9, 1.0e-8),
    }
    expected_authority_blockers = {
        "independent_reference_solver_receipt_missing",
        "scientific_medium_artifact_chain_missing",
        "engineer_decision_receipt_missing",
        "native_frame_alpha_free_equation_limit_exceeded",
    }

    def finite(value: object) -> bool:
        return isinstance(value, (int, float)) and math.isfinite(float(value))

    def close(left: object, right: object) -> bool:
        return finite(left) and finite(right) and math.isclose(
            float(left), float(right), rel_tol=1.0e-10, abs_tol=1.0e-14
        )

    for row in cases:
        case_id = str(row["case_id"])
        if "worker_failure" in row:
            failure = row["worker_failure"]
            kind = failure["kind"]
            detail = failure["detail"]
            returncode = failure["returncode"]
            expected_oom = _failure_indicates_oom(
                kind=kind,
                detail=detail,
                returncode=returncode,
            )
            returncode_semantics_match = bool(
                (kind == "worker_signal" and isinstance(returncode, int) and returncode < 0)
                or (
                    kind == "worker_nonzero_exit"
                    and isinstance(returncode, int)
                    and returncode > 0
                )
                or (
                    kind not in {"worker_signal", "worker_nonzero_exit"}
                    and (returncode is None or (isinstance(returncode, int) and returncode >= 0))
                )
            )
            wall_seconds = row["worker_wall_seconds"]
            timeout_limit = row["worker_timeout_limit_seconds"]
            wall_semantics_match = bool(
                finite(wall_seconds)
                and timeout_limit == WORKER_WALL_LIMIT_SECONDS
                and (
                    float(wall_seconds) >= float(timeout_limit)
                    if kind == "worker_timeout"
                    else float(wall_seconds) <= float(timeout_limit)
                )
            )
            if (
                row["contract_pass"] is not False
                or row["technical_execution_credit"] is not False
                or kind not in WORKER_FAILURE_KINDS
                or row["crashed"] is not (kind in WORKER_CRASH_FAILURE_KINDS)
                or row["oom"] is not expected_oom
                or not returncode_semantics_match
                or row["authority_blockers"] != [kind]
                or not wall_semantics_match
            ):
                errors.append(f"failed_case_semantics_invalid:{case_id}")
            continue
        spec = specifications.get(case_id)
        if spec is None:
            errors.append(f"case_specification_missing:{case_id}")
            continue
        if (
            row["archetype_id"] != spec.archetype_id
            or row["scale_basis"] != spec.scale_basis
            or row["semantic_boundary"] != spec.semantic_boundary
            or row["generator_policy"] != GENERATOR_POLICY
        ):
            errors.append(f"case_static_identity_mismatch:{case_id}")

        expected_model = build_medium_scale_model(case_id)
        expected_model_binding = {
            "input_checksum": expected_model.input_checksum,
            "canonical_model_checksum": expected_model.canonical_model_checksum,
            "node_count": len(expected_model.nodes),
            "element_count": len(expected_model.elements),
            "load_count": len(expected_model.loads),
            "support_count": len(expected_model.supports),
        }
        if row["model"] != expected_model_binding:
            errors.append(f"case_model_binding_mismatch:{case_id}")
        observed_replay = _stable_case_replay_projection(row)
        expected_replay = _expected_stable_case_replay(case_id)
        if not _replay_values_match(observed_replay, expected_replay):
            errors.append(f"case_current_source_replay_mismatch:{case_id}")

        expected_assembly, expected_unsupported = assemble_linear_static_sparse(
            expected_model
        )
        if expected_assembly is None or expected_unsupported:
            errors.append(f"case_expected_assembly_unavailable:{case_id}")
            continue
        expected_active = set(expected_assembly.active_dofs)
        expected_free = sorted(
            expected_active - set(expected_assembly.constrained_dofs)
        )
        expected_free_stiffness = expected_assembly.stiffness[
            np.ix_(expected_free, expected_free)
        ]
        expected_scaling = create_equation_scaling_6dof(
            source_identity_hash=expected_model.canonical_model_checksum,
            node_coordinates_m=expected_assembly.node_coordinates,
            reference_equation_load=expected_assembly.loads,
            free_dofs=expected_free,
        )
        expected_scaled, _, _ = scale_linear_system_6dof(
            expected_free_stiffness,
            expected_assembly.loads[expected_free],
            expected_free,
            expected_scaling,
        )
        expected_assembly_binding = {
            "global_equation_count": int(expected_assembly.stiffness.shape[0]),
            "active_equation_count": len(expected_active),
            "free_equation_count": len(expected_free),
            "sparse_storage": expected_assembly.stiffness_storage,
            "free_matrix_nonzero_count": int(expected_free_stiffness.nnz),
            "scaled_matrix_nonzero_count": int(expected_scaled.nnz),
        }

        diagnostics = row["assembly_and_conditioning"]
        if any(
            diagnostics[key] != expected
            for key, expected in expected_assembly_binding.items()
        ):
            errors.append(f"case_assembly_binding_mismatch:{case_id}")
        symmetry_error = diagnostics["scaled_symmetry_linf"]
        pivot_ratio = diagnostics["superlu_u_diagonal_pivot_ratio"]
        minimum = diagnostics["minimum_scaled_eigenvalue"]
        maximum = diagnostics["maximum_scaled_eigenvalue"]
        estimate = diagnostics["scaled_condition_estimate_2"]
        minimum_residual = diagnostics["minimum_eigenpair_relative_residual"]
        maximum_residual = diagnostics["maximum_eigenpair_relative_residual"]
        medium_size = (
            MINIMUM_MEDIUM_FREE_EQUATIONS
            <= diagnostics["free_equation_count"]
            <= MAXIMUM_PROFILE_FREE_EQUATIONS
        )
        sparse_assembly = bool(
            diagnostics["sparse_storage"] == "scipy_sparse_csr"
            and diagnostics["scaled_matrix_nonzero_count"]
            > diagnostics["free_equation_count"]
            and finite(symmetry_error)
            and float(symmetry_error) <= 1.0e-9
        )
        factorization = bool(
            diagnostics["factorization_backend"] == "scipy_superlu_splu"
            and diagnostics["factor_l_nonzero_count"] > 0
            and diagnostics["factor_u_nonzero_count"] > 0
            and finite(pivot_ratio)
            and float(pivot_ratio) > 0.0
            and finite(diagnostics["factorization_seconds"])
            and diagnostics["factorization_seconds"] >= 0.0
        )
        conditioning = bool(
            diagnostics["condition_estimator"]
            == "scaled_symmetric_algebraic_extreme_eigenvalue_ratio_scipy_eigh"
            and diagnostics["exact_condition_number_status"]
            == "symmetric_dense_eigenvalue_ratio_diagnostic"
            and diagnostics["scaled_condition_estimate_limit"]
            == CONDITION_ESTIMATE_LIMIT
            and diagnostics["eigenpair_relative_residual_limit"]
            == EIGENPAIR_RESIDUAL_LIMIT
            and all(
                finite(value)
                for value in (
                    minimum,
                    maximum,
                    estimate,
                    minimum_residual,
                    maximum_residual,
                )
            )
            and float(minimum) > 0.0
            and float(maximum) >= float(minimum)
            and close(estimate, float(maximum) / float(minimum))
            and float(estimate) <= CONDITION_ESTIMATE_LIMIT
            and float(minimum_residual) <= EIGENPAIR_RESIDUAL_LIMIT
            and float(maximum_residual) <= EIGENPAIR_RESIDUAL_LIMIT
        )
        diagnostics_contract = sparse_assembly and factorization and conditioning
        if diagnostics["sparse_assembly_gate_pass"] is not sparse_assembly:
            errors.append(f"case_sparse_assembly_gate_mismatch:{case_id}")
        if diagnostics["factorization_gate_pass"] is not factorization:
            errors.append(f"case_factorization_gate_mismatch:{case_id}")
        if diagnostics["conditioning_gate_pass"] is not conditioning:
            errors.append(f"case_conditioning_gate_mismatch:{case_id}")
        if diagnostics["contract_pass"] is not diagnostics_contract:
            errors.append(f"case_diagnostics_contract_mismatch:{case_id}")

        solver = row["solver"]
        observations = solver["run_observations"]
        expected_run_ids = ["sparse_first", "sparse_repeat", "dense_reference"]
        run_ids_match = [item["run_id"] for item in observations] == expected_run_ids
        solver_contract = bool(
            run_ids_match
            and solver["analysis_engine_version"] == ANALYSIS_ENGINE_VERSION
            and solver["tolerance"] == SOLVER_TOLERANCE
            and solver["sparse_backend"] == "scipy_sparse_spsolve_cpu"
            and solver["dense_reference_backend"] == "numpy_linalg_solve_dense"
            and all(
                item["status"] == "ready"
                and item["unsupported_feature_count"] == 0
                and item["fallback_used"] is False
                and item["regularization_used"] is False
                and finite(item["relative_residual"])
                and item["relative_residual"] <= SOLVER_TOLERANCE
                for item in observations
            )
        )
        sparse_path = bool(
            run_ids_match
            and all(
                item["matrix_backend"] == "scipy_sparse_spsolve_cpu"
                and item["sparse_backend_used"] is True
                and item["stiffness_storage"] == "scipy_sparse_csr"
                for item in observations[:2]
            )
            and observations[2]["matrix_backend"] == "numpy_linalg_solve_dense"
            and observations[2]["sparse_backend_used"] is False
            and observations[2]["stiffness_storage"] == "dense_numpy"
        )
        residual_keys = (
            "sparse_first_relative_residual",
            "sparse_repeat_relative_residual",
            "dense_relative_residual",
        )
        if any(
            not close(solver[key], observations[index]["relative_residual"])
            for index, key in enumerate(residual_keys)
        ):
            errors.append(f"case_solver_residual_binding_mismatch:{case_id}")

        comparison = row["comparison"]
        comparison_families = comparison["families"]
        comparison_passes: list[bool] = []
        if (
            comparison["reference_backend"] != "numpy_linalg_solve_dense"
            or comparison["observed_backend"] != "scipy_sparse_spsolve_cpu"
            or set(comparison_families) != set(comparison_tolerances)
        ):
            errors.append(f"case_comparison_identity_mismatch:{case_id}")
        else:
            for family, tolerances in comparison_tolerances.items():
                metric = comparison_families[family]
                absolute_tolerance, relative_tolerance = tolerances
                values_finite = all(
                    finite(metric[key])
                    for key in (
                        "max_absolute_difference",
                        "reference_linf_norm",
                        "relative_linf_difference",
                    )
                )
                expected_relative = (
                    float(metric["max_absolute_difference"])
                    / max(float(metric["reference_linf_norm"]), absolute_tolerance)
                    if values_finite
                    else math.inf
                )
                metric_pass = bool(
                    metric["value_count"] == metric["observed_value_count"]
                    and metric["absolute_tolerance"] == absolute_tolerance
                    and metric["relative_tolerance"] == relative_tolerance
                    and values_finite
                    and float(metric["reference_linf_norm"]) >= 0.0
                    and close(metric["relative_linf_difference"], expected_relative)
                    and float(metric["max_absolute_difference"])
                    <= absolute_tolerance
                    + relative_tolerance * float(metric["reference_linf_norm"])
                )
                comparison_passes.append(metric_pass)
                if metric["contract_pass"] is not metric_pass:
                    errors.append(
                        f"case_comparison_family_gate_mismatch:{case_id}:{family}"
                    )
        comparison_contract = bool(
            len(comparison_passes) == len(comparison_tolerances)
            and all(comparison_passes)
        )
        if comparison["contract_pass"] is not comparison_contract:
            errors.append(f"case_comparison_contract_mismatch:{case_id}")

        determinism = row["determinism"]
        deterministic = (
            determinism["first_sha256"] == determinism["repeat_sha256"]
        )
        if determinism["projection"] != (
            "displacements_reactions_member_local_forces_energy_residual.v1"
        ):
            errors.append(f"case_determinism_projection_mismatch:{case_id}")
        if determinism["exact_match"] is not deterministic:
            errors.append(f"case_determinism_gate_mismatch:{case_id}")
        resources_row = row["resources"]
        solver_times = [
            solver["sparse_first_seconds"],
            solver["sparse_repeat_seconds"],
            solver["dense_seconds"],
        ]
        runtime = bool(
            all(
                finite(value) and 0.0 <= value <= RUNTIME_LIMIT_SECONDS
                for value in solver_times
            )
            and finite(resources_row["execution_seconds"])
            and sum(float(value) for value in solver_times)
            <= float(resources_row["execution_seconds"])
            <= RUNTIME_LIMIT_SECONDS
            and float(diagnostics["factorization_seconds"])
            + sum(float(value) for value in solver_times)
            <= float(resources_row["execution_seconds"])
            and resources_row["runtime_limit_seconds"] == RUNTIME_LIMIT_SECONDS
        )
        peak_memory = bool(
            resources_row["measurement"] == expected_resource_measurement
            and resources_row["observation_authority"]
            == RESOURCE_OBSERVATION_AUTHORITY
            and resources_row["authority_requires"] == RESOURCE_AUTHORITY_REQUIRES
            and isinstance(resources_row["peak_memory_bytes"], int)
            and 0 < resources_row["peak_memory_bytes"] <= PEAK_MEMORY_LIMIT_BYTES
            and resources_row["peak_memory_limit_bytes"] == PEAK_MEMORY_LIMIT_BYTES
        )
        worker_wall = bool(
            finite(row["worker_wall_seconds"])
            and float(resources_row["execution_seconds"])
            <= row["worker_wall_seconds"]
            <= WORKER_WALL_LIMIT_SECONDS
        )
        expected_gates = {
            "medium_size": medium_size,
            "sparse_assembly": sparse_assembly,
            "sparse_factorization": factorization,
            "conditioning": conditioning,
            "solver_residual_and_status": solver_contract,
            "sparse_product_path": sparse_path,
            "dense_sparse_comparison": comparison_contract,
            "deterministic_result": deterministic,
            "runtime": runtime,
            "peak_memory": peak_memory,
            "crash_free": row["crashed"] is False,
            "oom_free": row["oom"] is False,
            "worker_wall_runtime": worker_wall,
        }
        if row["gates"] != expected_gates:
            errors.append(f"case_gate_derivation_mismatch:{case_id}")
        case_contract = all(expected_gates.values())
        if row["contract_pass"] is not case_contract:
            errors.append(f"case_contract_derivation_mismatch:{case_id}")
        if row["technical_execution_credit"] is not case_contract:
            errors.append(f"case_credit_derivation_mismatch:{case_id}")
        if set(row["authority_blockers"]) != expected_authority_blockers:
            errors.append(f"case_authority_boundary_mismatch:{case_id}")
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
    expected_blockers = {
        "independent_reference_solver_receipts_missing",
        "scientific_medium_benchmark_artifact_chains_missing",
        "native_frame_alpha_free_equation_limit_60",
        "native_sparse_production_profile_missing",
        "shell_link_foundation_product_paths_unsupported",
    }
    if not payload["source_tree_clean"]:
        expected_blockers.add("source_tree_not_clean")
    if technical_count != len(CASE_SPECS):
        expected_blockers.add(
            f"technical_medium_scale_execution_incomplete:{technical_count}/{len(CASE_SPECS)}"
        )
    expected_blockers.update(
        f"medium_scale_case_failure:{row['case_id']}:{row['worker_failure']['kind']}"
        for row in cases
        if "worker_failure" in row
    )
    if set(payload["blockers_remaining"]) != expected_blockers:
        errors.append("aggregate_authority_boundary_mismatch")
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
    blockers.extend(
        f"medium_scale_case_failure:{row['case_id']}:{row['worker_failure']['kind']}"
        for row in cases
        if "worker_failure" in row
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
            "eigenpair_relative_residual_limit": EIGENPAIR_RESIDUAL_LIMIT,
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
            CLAIM_BOUNDARY
        ),
    }
    payload["receipt_payload_sha256"] = _sha256_json(payload)
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
