"""Conservative Phase 1 API slice for canonical model health and provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from structural_analysis.analyses.linear_static import (
    AUTHORITATIVE_CPU_SOLVER_ID,
    run_authoritative_linear_static,
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
    "linear_static",
    "model_health",
    "nonlinear_static_material_mesh",
}
LEGACY_SOLVER_HINTS = {
    MODEL_HEALTH_SOLVER_ID,
    "developer_preview_linear_static_axial",
    "developer_preview_linear_static_axial_sparse",
    NONLINEAR_MATERIAL_MESH_SOLVER_ID,
}


def _engine_version() -> str:
    try:
        return metadata.version("structural-optimization-workbench")
    except metadata.PackageNotFoundError:
        return "1.0.0"


ANALYSIS_ENGINE_VERSION = _engine_version()


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
    if analysis_type == "linear_static":
        return AUTHORITATIVE_CPU_SOLVER_ID
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
    unsupported = list(model.unsupported_features)
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
            tolerance=analysis_config.tolerance,
            matrix_backend=analysis_config.matrix_backend,
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
            residual_tolerance=analysis_config.tolerance,
            increment_tolerance=min(analysis_config.tolerance, 1.0e-12),
            max_iterations=(
                analysis_config.max_iterations
                if analysis_config.max_iterations > 0
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
            tolerance=analysis_config.tolerance,
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
        return build_result(
            status="blocked",
            analysis_type=analysis_config.analysis_type,
            solver=engine_solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=analysis_config.tolerance,
            convergence_history=[],
            unsupported_features=unsupported,
            warnings=warnings,
            metrics={
                **_model_health_metrics(model),
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
