"""Conservative Phase 1 API slice for canonical model health and provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from importlib import metadata
from pathlib import Path
from typing import Any

from structural_analysis.io.ifc.loader import load_ifc_step
from structural_analysis.io.midas.loader import load_midas_mgt
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.assembly.nonlinear_static import (
    axial_chain_mesh_problem_from_canonical_model,
    finite_difference_assembled_jacobian_check,
    mesh_series_force_equilibrium_check,
    solve_axial_chain_mesh,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig
from structural_analysis.solvers.linear.static import solve_linear_static, solve_linear_static_sparse

CLAIM_BOUNDARY_VERSION = "developer-preview-core-api-v1"
SUPPORTED_ANALYSIS_TYPES = {
    "linear_static",
    "model_health",
    "nonlinear_static_material_mesh",
}


def _engine_version() -> str:
    try:
        return metadata.version("structural-optimization-workbench")
    except metadata.PackageNotFoundError:
        return "1.0.0"


ANALYSIS_ENGINE_VERSION = _engine_version()


@dataclass(frozen=True)
class AnalysisConfig:
    """Explicit solver configuration shared by Python API and CLI."""

    analysis_type: str = "model_health"
    solver: str = "developer_preview_model_health"
    tolerance: float = 1.0e-8
    max_iterations: int = 0
    load_case: str | None = None
    reference: str | None = None
    matrix_backend: str = "numpy_linalg_solve_dense"
    developer_preview: bool = True
    claim_boundary_version: str = CLAIM_BOUNDARY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisResult:
    """Versioned result envelope; this first slice does not claim solver closure."""

    status: str
    analysis_type: str
    solver: str
    engine_version: str
    input_checksum: str
    tolerance: float
    convergence_history: list[dict[str, Any]]
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    developer_preview: bool = True
    claim_boundary_version: str = CLAIM_BOUNDARY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    """Validation envelope that keeps passed and unsupported fields separate."""

    status: str
    contract_pass: bool
    engine_version: str
    input_checksum: str
    tolerance: float
    convergence_history: list[dict[str, Any]]
    passed_fields: list[str] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    developer_preview_blocked_fields: list[str] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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


def analyze(model: CanonicalModel, config: AnalysisConfig | None = None) -> AnalysisResult:
    """Analyze a canonical model using a conservative Developer Preview contract."""

    analysis_config = config or AnalysisConfig()
    unsupported = list(model.unsupported_features)
    warnings = list(model.warnings)

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
                    "Developer Preview supports dense NumPy and scoped scipy sparse "
                    "CPU backends for the narrow axial linear_static slice only."
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
                "kind": "nonlinear_static_material_mesh_matrix_backend_not_supported",
                "matrix_backend": analysis_config.matrix_backend,
                "detail": (
                    "Developer Preview material mesh Newton seed supports dense NumPy "
                    "and scoped scipy sparse CPU solve only."
                ),
            }
        )

    if not unsupported and analysis_config.analysis_type == "linear_static":
        if analysis_config.matrix_backend == "scipy_sparse_spsolve_cpu":
            solution = solve_linear_static_sparse(model, tolerance=analysis_config.tolerance)
        else:
            solution = solve_linear_static(model, tolerance=analysis_config.tolerance)
        return AnalysisResult(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=analysis_config.solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=analysis_config.tolerance,
            convergence_history=solution.convergence_history,
            unsupported_features=solution.unsupported_features,
            warnings=warnings + solution.warnings,
            metrics=solution.metrics,
            developer_preview=analysis_config.developer_preview,
            claim_boundary_version=analysis_config.claim_boundary_version,
        )

    if not unsupported and analysis_config.analysis_type == "nonlinear_static_material_mesh":
        mesh_problem, mesh_unsupported = axial_chain_mesh_problem_from_canonical_model(model)
        if mesh_unsupported or mesh_problem is None:
            return AnalysisResult(
                status="blocked",
                analysis_type=analysis_config.analysis_type,
                solver=analysis_config.solver,
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
                    "claim_boundary": "nonlinear_material_mesh_seed_unsupported_input",
                },
                developer_preview=analysis_config.developer_preview,
                claim_boundary_version=analysis_config.claim_boundary_version,
            )
        cfg = NewtonRaphsonConfig(
            residual_tolerance=analysis_config.tolerance,
            increment_tolerance=min(analysis_config.tolerance, 1.0e-12),
            max_iterations=analysis_config.max_iterations
            if analysis_config.max_iterations > 0
            else 25,
            matrix_backend=analysis_config.matrix_backend,
        )
        solution, final_state = solve_axial_chain_mesh(mesh_problem, config=cfg)
        jacobian_check = finite_difference_assembled_jacobian_check(
            mesh_problem,
            solution.free_displacements_m,
        )
        series_check = mesh_series_force_equilibrium_check(final_state)
        return AnalysisResult(
            status=solution.status,
            analysis_type=analysis_config.analysis_type,
            solver=analysis_config.solver,
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
                "residual_norm": float(max(abs(value) for value in final_state.residual_kn)),
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
                "claim_boundary": "nonlinear_material_mesh_axial_chain_preview_only",
            },
            developer_preview=analysis_config.developer_preview,
            claim_boundary_version=analysis_config.claim_boundary_version,
        )

    if unsupported:
        return AnalysisResult(
            status="blocked",
            analysis_type=analysis_config.analysis_type,
            solver=analysis_config.solver,
            engine_version=ANALYSIS_ENGINE_VERSION,
            input_checksum=model.input_checksum,
            tolerance=analysis_config.tolerance,
            convergence_history=[],
            unsupported_features=unsupported,
            warnings=warnings,
            metrics={
                "node_count": len(model.nodes),
                "element_count": len(model.elements),
                "load_count": len(model.loads),
                "support_count": len(model.supports),
            },
            developer_preview=analysis_config.developer_preview,
            claim_boundary_version=analysis_config.claim_boundary_version,
        )

    return AnalysisResult(
        status="ready",
        analysis_type=analysis_config.analysis_type,
        solver=analysis_config.solver,
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
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
            "unit_length": model.units.length,
            "unit_force": model.units.force,
            "up_axis": model.coordinate_system.up_axis,
        },
        developer_preview=analysis_config.developer_preview,
        claim_boundary_version=analysis_config.claim_boundary_version,
    )


def validate(
    result: AnalysisResult,
    reference: dict[str, Any] | str | Path | None = None,
) -> ValidationReport:
    """Validate a result while preserving unsupported fields as blockers."""

    reference_payload = _load_reference(reference)
    passed_fields = [
        "engine_version",
        "input_checksum",
        "tolerance",
        "convergence_history",
        "claim_boundary_version",
    ]
    unsupported_fields = [
        item.get("kind", "unsupported_feature") for item in result.unsupported_features
    ]
    warnings = list(result.warnings)
    comparisons: list[dict[str, Any]] = []

    if reference_payload:
        for field_name, expected in reference_payload.items():
            actual = result.metrics.get(field_name)
            comparisons.append(
                {
                    "field": field_name,
                    "expected": expected,
                    "actual": actual,
                    "status": "pass" if actual == expected else "review",
                }
            )
    elif result.analysis_type != "model_health":
        warnings.append("No reference payload supplied for non-model-health analysis.")

    contract_pass = result.status == "ready" and not unsupported_fields
    report_status = "pass" if contract_pass else "blocked"
    blocked_fields = unsupported_fields.copy()
    if result.status != "ready" and not blocked_fields:
        blocked_fields.append(result.analysis_type)

    return ValidationReport(
        status=report_status,
        contract_pass=contract_pass,
        engine_version=result.engine_version,
        input_checksum=result.input_checksum,
        tolerance=result.tolerance,
        convergence_history=result.convergence_history,
        passed_fields=passed_fields if contract_pass else [],
        unsupported_fields=unsupported_fields,
        developer_preview_blocked_fields=blocked_fields,
        comparisons=comparisons,
        warnings=warnings,
        developer_preview=result.developer_preview,
        claim_boundary_version=result.claim_boundary_version,
    )


def _load_reference(reference: dict[str, Any] | str | Path | None) -> dict[str, Any]:
    if reference is None:
        return {}
    if isinstance(reference, dict):
        return reference
    with Path(reference).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Reference payload must be a JSON object.")
    return payload
