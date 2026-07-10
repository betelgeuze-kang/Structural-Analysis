"""Single authoritative CPU linear-static analysis entry point."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.linear.static import (
    LinearStaticSolution,
    solve_linear_static,
    solve_linear_static_sparse,
)

AUTHORITATIVE_CPU_SOLVER_ID = "authoritative_cpu_linear_fea_3d_v1"
SUPPORTED_MATRIX_BACKENDS = {
    "numpy_linalg_solve_dense",
    "scipy_sparse_spsolve_cpu",
}
LOAD_COMPONENT_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
FRAME_ELEMENT_TYPES = {"frame", "beam", "column"}


def run_authoritative_linear_static(
    model: CanonicalModel,
    *,
    tolerance: float,
    matrix_backend: str,
    load_case: str | None = None,
) -> LinearStaticSolution:
    if matrix_backend not in SUPPORTED_MATRIX_BACKENDS:
        raise ValueError(f"Unsupported authoritative CPU matrix backend: {matrix_backend}")

    normalized_load_case = load_case.strip() if isinstance(load_case, str) else load_case
    normalized_load_case = normalized_load_case or None
    unsupported = _public_preflight(
        model,
        tolerance=tolerance,
        load_case=normalized_load_case,
    )
    if unsupported:
        return _blocked_solution(model, matrix_backend=matrix_backend, unsupported=unsupported)

    if matrix_backend == "scipy_sparse_spsolve_cpu":
        return solve_linear_static_sparse(
            model,
            tolerance=tolerance,
            load_case=normalized_load_case,
        )
    return solve_linear_static(
        model,
        tolerance=tolerance,
        load_case=normalized_load_case,
    )


def _public_preflight(
    model: CanonicalModel,
    *,
    tolerance: float,
    load_case: str | None,
) -> list[dict[str, Any]]:
    unsupported: list[dict[str, Any]] = []
    if not isfinite(tolerance) or tolerance <= 0.0:
        unsupported.append(
            {
                "kind": "linear_static_tolerance_invalid",
                "tolerance": tolerance,
                "detail": "Authoritative CPU v1 requires a finite positive tolerance.",
            }
        )

    labels = [_load_case_label(load) for load in model.loads]
    named_cases = sorted({label for label in labels if label is not None})
    unlabeled_count = sum(label is None for label in labels)
    if named_cases and unlabeled_count:
        unsupported.append(
            {
                "kind": "linear_static_load_case_labeling_inconsistent",
                "available_load_cases": named_cases,
                "unlabeled_load_count": unlabeled_count,
                "detail": (
                    "Named and unnamed load rows cannot be mixed in the authoritative "
                    "public path because their combination semantics are ambiguous."
                ),
            }
        )
    elif load_case is None and len(named_cases) > 1:
        unsupported.append(
            {
                "kind": "linear_static_load_case_required",
                "available_load_cases": named_cases,
                "detail": (
                    "Multiple named load cases are present. Select one explicitly; "
                    "the authoritative solver never sums named cases implicitly."
                ),
            }
        )

    for load_index, load in enumerate(model.loads):
        detail = _load_component_error(load)
        if detail is not None:
            unsupported.append(
                {
                    "kind": "linear_static_load_components_invalid",
                    "load_index": load_index,
                    "detail": detail,
                }
            )

    for element in model.elements:
        if str(element.get("type", "")).lower() not in FRAME_ELEMENT_TYPES:
            continue
        element_id = str(element.get("id", ""))
        for key in ("local_axis_angle_deg", "angle_deg"):
            if key not in element or element.get(key) is None:
                continue
            try:
                angle = float(element[key])
            except (TypeError, ValueError):
                angle = float("nan")
            if not isfinite(angle):
                unsupported.append(
                    {
                        "kind": "linear_static_element_properties_invalid",
                        "element": element_id,
                        "detail": f"{key} must be finite.",
                    }
                )
            break
        for key in ("offset_i_global_m", "offset_i", "offset_j_global_m", "offset_j"):
            if key not in element or element.get(key) is None:
                continue
            if not _finite_vector3(element[key]):
                unsupported.append(
                    {
                        "kind": "linear_static_element_properties_invalid",
                        "element": element_id,
                        "detail": f"{key} must be a finite three-component vector.",
                    }
                )

    return unsupported


def _load_case_label(load: Mapping[str, Any]) -> str | None:
    raw = load.get("load_case", load.get("case"))
    if raw is None:
        return None
    label = str(raw).strip()
    return label or None


def _load_component_error(load: Mapping[str, Any]) -> str | None:
    raw = load.get("components")
    if raw is None:
        values = [load.get(label, load.get(label.lower(), 0.0)) for label in LOAD_COMPONENT_LABELS]
    elif isinstance(raw, Mapping):
        values = [raw.get(label, raw.get(label.lower(), 0.0)) for label in LOAD_COMPONENT_LABELS]
    elif isinstance(raw, (list, tuple)) and len(raw) in {3, 6}:
        values = list(raw)
        if len(values) == 3:
            values.extend([0.0, 0.0, 0.0])
    else:
        return "components must be a mapping or a three/six-value sequence."

    try:
        numeric = [float(value) for value in values]
    except (TypeError, ValueError):
        return "load components must be numeric."
    if not all(isfinite(value) for value in numeric):
        return "load components must be finite."
    return None


def _finite_vector3(value: Any) -> bool:
    if isinstance(value, Mapping):
        raw = [value.get("x", 0.0), value.get("y", 0.0), value.get("z", 0.0)]
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        raw = list(value)
    else:
        return False
    try:
        numeric = [float(component) for component in raw]
    except (TypeError, ValueError):
        return False
    return all(isfinite(component) for component in numeric)


def _blocked_solution(
    model: CanonicalModel,
    *,
    matrix_backend: str,
    unsupported: list[dict[str, Any]],
) -> LinearStaticSolution:
    sparse_backend_used = matrix_backend == "scipy_sparse_spsolve_cpu"
    element_types = {str(element.get("type", "")).lower() for element in model.elements}
    claim_boundary = (
        "linear_static_axial_truss_preview_only"
        if element_types <= {"truss", "axial"}
        else "linear_static_3d_frame_cpu_reference_v1"
    )
    return LinearStaticSolution(
        status="blocked",
        metrics={
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
            "claim_boundary": claim_boundary,
            "solver_path_id": AUTHORITATIVE_CPU_SOLVER_ID,
            "analysis_fidelity": "cpu_reference_linear_fea",
            "production_fail_closed": True,
            "implicit_property_fallback_used": False,
            "automatic_support_generation_used": False,
            "regularization_used": False,
            "fallback_used": False,
            "stiffness_storage": "scipy_sparse_csr" if sparse_backend_used else "dense_numpy",
            "matrix_backend": matrix_backend,
            "sparse_backend_used": sparse_backend_used,
        },
        convergence_history=[],
        unsupported_features=unsupported,
    )
