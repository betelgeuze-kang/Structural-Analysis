"""Conservative Phase 1 API slice for canonical model health and provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Integral, Real
from pathlib import Path
from typing import Any

from structural_analysis.analyses.linear_static import (
    AUTHORITATIVE_CPU_SOLVER_ID,
    run_authoritative_linear_static,
)
from structural_analysis.analyses.buckling import (
    AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
    run_authoritative_linear_buckling,
)
from structural_analysis.analyses.modal import (
    AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
    EIGEN_BACKEND,
    run_authoritative_modal,
)
from structural_analysis.assembly.nonlinear_static import (
    axial_chain_mesh_problem_from_canonical_model,
    finite_difference_assembled_jacobian_check,
    mesh_series_force_equilibrium_check,
    solve_axial_chain_mesh,
)
from structural_analysis.io.ifc.loader import load_ifc_step
from structural_analysis.io.midas import load_midas_mgt
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.product_identity import ANALYSIS_ENGINE_VERSION
from structural_analysis.results.schema import (
    CLAIM_BOUNDARY_VERSION as CLAIM_BOUNDARY_VERSION,
    AnalysisResult as AnalysisResult,
    ValidationReport as ValidationReport,
)
from structural_analysis.results.validation import validate as validate
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

MODEL_HEALTH_SOLVER_ID = "developer_preview_model_health"
NONLINEAR_MATERIAL_MESH_SOLVER_ID = (
    "developer_preview_material_mesh_newton_axial_chain"
)
UNSUPPORTED_ANALYSIS_SOLVER_ID = "unsupported_analysis_type"
SUPPORTED_ANALYSIS_TYPES = {
    "linear_buckling",
    "linear_static",
    "modal",
    "model_health",
    "nonlinear_static_material_mesh",
}
LEGACY_SOLVER_HINTS = {
    MODEL_HEALTH_SOLVER_ID,
    "developer_preview_linear_static_axial",
    "developer_preview_linear_static_axial_sparse",
    NONLINEAR_MATERIAL_MESH_SOLVER_ID,
}


@dataclass(frozen=True)
class AnalysisConfig:
    """Explicit numerical configuration shared by Python API and CLI.

    ``solver``, ``developer_preview``, and ``claim_boundary_version`` remain as
    compatibility-only request fields for the v1 API surface. They never control
    result provenance: the engine selects the solver identifier and claim metadata.
    ``reference`` is likewise retained only for legacy construction compatibility;
    validation references belong to :func:`validate` or the CLI ``--reference``
    option.
    """

    analysis_type: str = "model_health"
    solver: str = MODEL_HEALTH_SOLVER_ID
    tolerance: float = 1.0e-8
    max_iterations: int = 0
    load_case: str | None = None
    reference: str | None = None
    matrix_backend: str = "numpy_linalg_solve_dense"
    mode_count: int = 6
    eigen_backend: str = EIGEN_BACKEND
    developer_preview: bool = True
    claim_boundary_version: str = CLAIM_BOUNDARY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_model(path: str | Path) -> CanonicalModel:
    """Load a canonical model or return an explicit unsupported import envelope."""

    model_path = Path(path)
    suffix = model_path.suffix.lower()
    if suffix == ".json":
        return load_neutral_json(model_path)
    if suffix == ".mgt":
        return load_midas_mgt(model_path)
    if suffix == ".ifc":
        return load_ifc_step(model_path)
    raise ValueError(f"Unsupported model input extension: {suffix or '<none>'}")


def _engine_owned_solver_id(analysis_type: str) -> str:
    if analysis_type == "linear_buckling":
        return AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID
    if analysis_type == "linear_static":
        return AUTHORITATIVE_CPU_SOLVER_ID
    if analysis_type == "modal":
        return AUTHORITATIVE_CPU_MODAL_SOLVER_ID
    if analysis_type == "nonlinear_static_material_mesh":
        return NONLINEAR_MATERIAL_MESH_SOLVER_ID
    if analysis_type == "model_health":
        return MODEL_HEALTH_SOLVER_ID
    return UNSUPPORTED_ANALYSIS_SOLVER_ID


def _engine_owned_metadata_warnings(
    config: AnalysisConfig,
    *,
    selected_solver: str,
) -> list[str]:
    warnings: list[str] = []
    requested_solver = str(config.solver or "").strip()
    if (
        requested_solver
        and requested_solver != selected_solver
        and requested_solver not in LEGACY_SOLVER_HINTS
    ):
        warnings.append(
            "Requested solver identifier was ignored; solver provenance is engine-owned."
        )
    if config.developer_preview is not True:
        warnings.append(
            "Requested developer_preview override was ignored; claim metadata is engine-owned."
        )
    if config.claim_boundary_version != CLAIM_BOUNDARY_VERSION:
        warnings.append(
            "Requested claim_boundary_version override was ignored; claim metadata is engine-owned."
        )
    return warnings


def _normalized_positive_tolerance(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0.0:
        return None
    return normalized


def _normalized_nonnegative_iteration_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Integral):
        return None
    normalized = int(value)
    return normalized if normalized >= 0 else None


def _configuration_receipt_value(value: Any) -> Any:
    """Return a deterministic JSON-safe representation for rejected values."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        normalized = float(value)
        if isfinite(normalized):
            return normalized
        if normalized != normalized:
            return "nan"
        return "positive_infinity" if normalized > 0.0 else "negative_infinity"
    value_type = type(value)
    return f"<{value_type.__module__}.{value_type.__qualname__}>"


def _public_configuration_preflight(
    config: AnalysisConfig,
) -> tuple[list[dict[str, Any]], float | None, int | None]:
    unsupported: list[dict[str, Any]] = []
    tolerance = _normalized_positive_tolerance(config.tolerance)
    max_iterations = _normalized_nonnegative_iteration_count(
        config.max_iterations
    )

    if config.analysis_type == "linear_static" and tolerance is None:
        unsupported.append(
            {
                "kind": "linear_static_tolerance_invalid",
                "tolerance": _configuration_receipt_value(config.tolerance),
                "detail": (
                    "Authoritative CPU linear static requires a finite positive "
                    "numeric tolerance; boolean gates are not numeric tolerances."
                ),
            }
        )
    if config.analysis_type == "nonlinear_static_material_mesh":
        if tolerance is None:
            unsupported.append(
                {
                    "kind": "nonlinear_static_material_mesh_tolerance_invalid",
                    "tolerance": _configuration_receipt_value(config.tolerance),
                    "detail": (
                        "Material-mesh Newton requires a finite positive numeric "
                        "tolerance; boolean gates are not numeric tolerances."
                    ),
                }
            )
        if max_iterations is None:
            unsupported.append(
                {
                    "kind": (
                        "nonlinear_static_material_mesh_max_iterations_invalid"
                    ),
                    "max_iterations": _configuration_receipt_value(
                        config.max_iterations
                    ),
                    "detail": (
                        "Material-mesh Newton max_iterations must be a "
                        "non-negative integer; zero selects the bounded default."
                    ),
                }
            )

    return unsupported, tolerance, max_iterations


def analyze(
    model: CanonicalModel,
    config: AnalysisConfig | None = None,
) -> AnalysisResult:
    """Analyze one detached canonical snapshot under the Developer Preview contract."""

    analysis_config = config or AnalysisConfig()
    model = model.detached_analysis_snapshot()
    canonical_model_checksum = model.canonical_model_checksum

    def build_result(**kwargs: Any) -> AnalysisResult:
        return AnalysisResult(
            canonical_model_checksum=canonical_model_checksum,
            **kwargs,
        )

    engine_solver = _engine_owned_solver_id(analysis_config.analysis_type)
    (
        configuration_unsupported,
        normalized_tolerance,
        normalized_max_iterations,
    ) = _public_configuration_preflight(analysis_config)
    unsupported = [*configuration_unsupported, *model.unsupported_features]
    warnings = [
        *model.warnings,
        *_engine_owned_metadata_warnings(
            analysis_config,
            selected_solver=engine_solver,
        ),
    ]

    if analysis_config.analysis_type not in SUPPORTED_ANALYSIS_TYPES:
        unsupported.append(
            {
                "kind": "analysis_type_not_implemented",
                "analysis_type": analysis_config.analysis_type,
                "detail": (
                    "Deterministic solver closure is still tracked outside this "
                    "first core API slice."
                ),
            }
        )
    if (
        analysis_config.analysis_type == "linear_static"
        and analysis_config.matrix_backend
        not in {"numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"}
    ):
        unsupported.append(
            {
                "kind": "linear_static_matrix_backend_not_supported",
                "matrix_backend": analysis_config.matrix_backend,
                "detail": (
                    "Authoritative CPU linear static supports dense NumPy and scoped "
                    "SciPy sparse CPU backends for frame/truss models."
                ),
            }
        )
    if (
        analysis_config.analysis_type == "nonlinear_static_material_mesh"
        and analysis_config.matrix_backend
        not in {"numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"}
    ):
        unsupported.append(
            {
                "kind": (
                    "nonlinear_static_material_mesh_matrix_backend_not_supported"
                ),
                "matrix_backend": analysis_config.matrix_backend,
                "detail": (
                    "Developer Preview material mesh Newton seed supports dense NumPy "
                    "and scoped scipy sparse CPU solve only."
                ),
            }
        )

    if not unsupported and analysis_config.analysis_type == "linear_static":
        solution = run_authoritative_linear_static(
            model,
            tolerance=normalized_tolerance,
            matrix_backend=analysis_config.matrix_backend,
            load_case=analysis_config.load_case,
        )
        return build_result(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=normalized_tolerance,
            convergence_history=solution.convergence_history,
            unsupported_features=solution.unsupported_features,
            warnings=warnings + solution.warnings,
            metrics={
                **solution.metrics,
                "provenance_policy": "engine_owned",
                "analysis_input_snapshot": "detached_canonical_model_v1",
            },
            developer_preview=True,
            claim_boundary_version=CLAIM_BOUNDARY_VERSION,
        )

    if not unsupported and analysis_config.analysis_type == "modal":
        solution = run_authoritative_modal(
            model,
            tolerance=analysis_config.tolerance,
            mode_count=analysis_config.mode_count,
            eigen_backend=analysis_config.eigen_backend,
        )
        return build_result(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=analysis_config.tolerance,
            convergence_history=solution.convergence_history,
            unsupported_features=solution.unsupported_features,
            warnings=warnings + solution.warnings,
            metrics={
                **solution.metrics,
                "provenance_policy": "engine_owned",
                "analysis_input_snapshot": "detached_canonical_model_v1",
            },
            developer_preview=True,
            claim_boundary_version=CLAIM_BOUNDARY_VERSION,
        )

    if not unsupported and analysis_config.analysis_type == "linear_buckling":
        solution = run_authoritative_linear_buckling(
            model,
            tolerance=analysis_config.tolerance,
            mode_count=analysis_config.mode_count,
            eigen_backend=analysis_config.eigen_backend,
            load_case=analysis_config.load_case,
        )
        return build_result(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=analysis_config.tolerance,
            convergence_history=solution.convergence_history,
            unsupported_features=solution.unsupported_features,
            warnings=warnings + solution.warnings,
            metrics={
                **solution.metrics,
                "provenance_policy": "engine_owned",
                "analysis_input_snapshot": "detached_canonical_model_v1",
            },
            developer_preview=True,
            claim_boundary_version=CLAIM_BOUNDARY_VERSION,
        )

    if (
        not unsupported
        and analysis_config.analysis_type == "nonlinear_static_material_mesh"
    ):
        mesh_problem, mesh_unsupported = (
            axial_chain_mesh_problem_from_canonical_model(model)
        )
        if mesh_unsupported or mesh_problem is None:
            return build_result(
                status="blocked",
                analysis_type=analysis_config.analysis_type,
                solver=engine_solver,
                engine_version=ANALYSIS_ENGINE_VERSION,
                input_checksum=model.input_checksum,
                tolerance=analysis_config.tolerance,
                convergence_history=[],
                unsupported_features=mesh_unsupported,
                warnings=warnings,
                metrics={
                    "node_count": len(model.nodes),
                    "element_count": len(model.elements),
                    "load_count": len(model.loads),
                    "support_count": len(model.supports),
                    "claim_boundary": (
                        "nonlinear_material_mesh_seed_unsupported_input"
                    ),
                    "provenance_policy": "engine_owned",
                    "analysis_input_snapshot": "detached_canonical_model_v1",
                },
                developer_preview=True,
                claim_boundary_version=CLAIM_BOUNDARY_VERSION,
            )
        cfg = NewtonRaphsonConfig(
            residual_tolerance=normalized_tolerance,
            increment_tolerance=min(normalized_tolerance, 1.0e-12),
            max_iterations=(
                normalized_max_iterations
                if normalized_max_iterations > 0
                else 25
            ),
            matrix_backend=analysis_config.matrix_backend,
        )
        solution, final_state = solve_axial_chain_mesh(mesh_problem, config=cfg)
        jacobian_check = finite_difference_assembled_jacobian_check(
            mesh_problem,
            solution.free_displacements_m,
        )
        series_check = mesh_series_force_equilibrium_check(final_state)
        return build_result(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=normalized_tolerance,
            convergence_history=solution.convergence_history,
            unsupported_features=solution.unsupported_features,
            warnings=warnings + solution.warnings,
            metrics={
                **solution.metrics,
                "node_count": mesh_problem.node_count,
                "element_count": len(mesh_problem.elements),
                "free_dof_count": len(final_state.free_node_indices),
                "residual_norm": float(
                    max(abs(value) for value in final_state.residual_kn)
                ),
                "tip_displacement_m": float(final_state.displacements_m[-1]),
                "reactions": final_state.reactions_kn.tolist(),
                "internal_forces": final_state.internal_forces_kn.tolist(),
                "external_forces": final_state.external_forces_kn.tolist(),
                "element_forces": list(final_state.element_forces_kn),
                "assembled_jacobian": final_state.jacobian_kn_per_m.tolist(),
                "assembled_jacobian_fd_pass": bool(jacobian_check["pass"]),
                "series_force_equilibrium_pass": bool(series_check["pass"]),
                "regularization_used": solution.metrics.get("regularization_used"),
                "fallback_used": solution.metrics.get("fallback_used"),
                "claim_boundary": (
                    "nonlinear_material_mesh_axial_chain_preview_only"
                ),
                "provenance_policy": "engine_owned",
                "analysis_input_snapshot": "detached_canonical_model_v1",
            },
            developer_preview=True,
            claim_boundary_version=CLAIM_BOUNDARY_VERSION,
        )

    if unsupported:
        blocked_tolerance = analysis_config.tolerance
        if analysis_config.analysis_type in {
            "linear_static",
            "nonlinear_static_material_mesh",
        }:
            blocked_tolerance = (
                normalized_tolerance
                if normalized_tolerance is not None
                else 0.0
            )
        return build_result(
            status="blocked",
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=blocked_tolerance,
            convergence_history=[],
            unsupported_features=unsupported,
            warnings=warnings,
            metrics={
                **_model_health_metrics(model),
                **(
                    {
                        "claim_boundary": "public_analysis_configuration_invalid",
                        "configuration_error_count": len(
                            configuration_unsupported
                        ),
                        "solver_executed": False,
                        "convergence_claim": False,
                        "regularization_used": False,
                        "fallback_used": False,
                    }
                    if configuration_unsupported
                    else {}
                ),
                "provenance_policy": "engine_owned",
                "analysis_input_snapshot": "detached_canonical_model_v1",
            },
            developer_preview=True,
            claim_boundary_version=CLAIM_BOUNDARY_VERSION,
        )

    return build_result(
        status="ready",
        analysis_type=analysis_config.analysis_type,
        solver=engine_solver,
        engine_version=ANALYSIS_ENGINE_VERSION,
        input_checksum=model.input_checksum,
        tolerance=analysis_config.tolerance,
        convergence_history=[
            {
                "step": "model_health",
                "iteration": 0,
                "residual_norm": 0.0,
                "relative_increment": 0.0,
                "status": "ready",
            }
        ],
        warnings=warnings,
        metrics={
            **_model_health_metrics(model),
            "unit_length": model.units.length,
            "unit_force": model.units.force,
            "up_axis": model.coordinate_system.up_axis,
            "provenance_policy": "engine_owned",
            "analysis_input_snapshot": "detached_canonical_model_v1",
        },
        developer_preview=True,
        claim_boundary_version=CLAIM_BOUNDARY_VERSION,
    )


def _model_health_metrics(model: CanonicalModel) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "node_count": len(model.nodes),
        "element_count": len(model.elements),
        "load_count": len(model.loads),
        "support_count": len(model.supports),
    }
    metadata_payload = model.metadata if isinstance(model.metadata, dict) else {}
    for key in (
        "record_count",
        "parsed_record_count",
        "entity_counts",
        "structural_entity_count",
        "material_entity_count",
        "section_entity_count",
        "load_related_entity_count",
        "text_scan_only",
        "adapter_scope",
    ):
        if key in metadata_payload:
            metrics[key] = metadata_payload[key]
    return metrics
