"""Benchmark factory helpers for generated analytic Developer Preview cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from structural_analysis.api.core import AnalysisConfig, analyze, load_model


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    lane: str
    payload: dict[str, Any]
    expected_outputs: dict[str, Any]
    license: dict[str, Any]
    truth_class: str = "analytic_truth"
    analysis_type: str = "linear_static"
    structural_family: str = "axial_bar"
    source_id: str = "repo_generated_analytic_axial"
    source_url_or_doi: str = "generated://structural_analysis/analytic_axial_chain"
    version: str = "v1"
    known_modeling_assumptions: tuple[str, ...] = (
        "small_displacement_linear_elastic_axial_response",
        "3d_truss_nodes_with_transverse_dofs_restrained",
        "single_material_single_area_prismatic_bar",
    )

    def checksum(self) -> str:
        return checksum_payload(self.payload)

    def manifest_row(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "lane": self.lane,
            "source_id": self.source_id,
            "source_url_or_doi": self.source_url_or_doi,
            "version": self.version,
            "license": self.license,
            "redistribution_allowed": bool(self.license["redistribution_allowed"]),
            "commercial_use_allowed": bool(self.license["commercial_use_allowed"]),
            "checksum": self.checksum(),
            "file_format": "canonical_json",
            "node_count": len(self.payload["nodes"]),
            "element_count": len(self.payload["elements"]),
            "structural_family": self.structural_family,
            "analysis_type": self.analysis_type,
            "truth_class": self.truth_class,
            "reference_solver_and_version": "closed_form_axial_bar_v1",
            "available_reference_outputs": sorted(self.expected_outputs),
            "expected_outputs": self.expected_outputs,
            "known_modeling_assumptions": list(self.known_modeling_assumptions),
            "known_defects": [],
            "selected_benchmark_lanes": [self.lane],
        }


def checksum_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def generated_analytic_axial_cases() -> list[BenchmarkCase]:
    loads = (10.0, 25.0, 50.0, 75.0, 100.0)
    element_counts = (1, 2, 3, 4)
    specs = [
        (f"axial_chain_e{element_count}_load_{load:g}", element_count, load)
        for element_count in element_counts
        for load in loads
    ]
    return [
        BenchmarkCase(
            case_id=case_id,
            lane="analytic-small",
            payload=build_axial_chain_payload(case_id=case_id, element_count=elements, load_fx=load),
            expected_outputs={
                "tip_ux": load * 2.0 / (200000.0 * 0.01),
                "base_reaction_ux": -load,
            },
            license={
                "id": "repo-generated-analytic-v1",
                "spdx": "CC0-1.0",
                "redistribution_allowed": True,
                "commercial_use_allowed": True,
                "approval_status": "generated_in_repo_no_external_source",
            },
        )
        for case_id, elements, load in specs
    ]


def generated_element_patch_cases() -> list[BenchmarkCase]:
    specs = [
        ("element_patch_x_origin", "X", (0.0, 0.0, 0.0)),
        ("element_patch_x_translated", "X", (10.0, -3.0, 1.5)),
        ("element_patch_y_origin", "Y", (0.0, 0.0, 0.0)),
        ("element_patch_y_translated", "Y", (-2.0, 8.0, 4.0)),
        ("element_patch_z_origin", "Z", (0.0, 0.0, 0.0)),
        ("element_patch_z_translated", "Z", (5.0, 2.0, -7.0)),
    ]
    load = 80.0
    length = 1.6
    expected_displacement = load * length / (200000.0 * 0.01)
    return [
        BenchmarkCase(
            case_id=case_id,
            lane="element-patch",
            payload=build_axis_aligned_axial_payload(
                case_id=case_id,
                axis=axis,
                origin=origin,
                length=length,
                load_fx_equivalent=load,
            ),
            expected_outputs={
                "tip_dof": f"U{axis}",
                "base_reaction_dof": f"U{axis}",
                "tip_displacement": expected_displacement,
                "base_reaction": -load,
            },
            license={
                "id": "repo-generated-analytic-v1",
                "spdx": "CC0-1.0",
                "redistribution_allowed": True,
                "commercial_use_allowed": True,
                "approval_status": "generated_in_repo_no_external_source",
            },
            structural_family="axial_element_patch",
            source_id="repo_generated_element_patch",
            source_url_or_doi="generated://structural_analysis/element_patch_axis_aligned_axial",
        )
        for case_id, axis, origin in specs
    ]


def generated_nonlinear_material_mesh_cases() -> list[BenchmarkCase]:
    specs = [
        ("nonlinear_material_mesh_e1_load_50", 1, 50.0),
        ("nonlinear_material_mesh_e1_load_100", 1, 100.0),
        ("nonlinear_material_mesh_e2_load_50", 2, 50.0),
        ("nonlinear_material_mesh_e2_load_100", 2, 100.0),
    ]
    linear_stiffness = 100.0
    cubic_stiffness = 1000.0
    return [
        BenchmarkCase(
            case_id=case_id,
            lane="nonlinear-material-mesh",
            payload=build_nonlinear_material_mesh_payload(
                case_id=case_id,
                element_count=element_count,
                load_fx=load,
                linear_stiffness=linear_stiffness,
                cubic_stiffness=cubic_stiffness,
            ),
            expected_outputs={
                "tip_displacement_m": element_count
                * solve_cubic_axial_displacement(
                    load_fx=load,
                    linear_stiffness=linear_stiffness,
                    cubic_stiffness=cubic_stiffness,
                ),
                "base_reaction_kn": -load,
                "assembled_jacobian_fd_pass": True,
                "series_force_equilibrium_pass": True,
                "residual_gate_passed": True,
                "increment_gate_passed": True,
            },
            license={
                "id": "repo-generated-analytic-v1",
                "spdx": "CC0-1.0",
                "redistribution_allowed": True,
                "commercial_use_allowed": True,
                "approval_status": "generated_in_repo_no_external_source",
            },
            analysis_type="nonlinear_static_material_mesh",
            structural_family="nonlinear_axial_material_mesh",
            source_id="repo_generated_nonlinear_material_mesh",
            source_url_or_doi=(
                "generated://structural_analysis/nonlinear_material_mesh_axial_chain"
            ),
            known_modeling_assumptions=(
                "1d_axis_aligned_axial_chain_only",
                "cubic_spring_material_law_f_internal_k_u_plus_c_u_cubed",
                "newton_raphson_with_consistent_assembled_jacobian",
                "developer_preview_seed_not_full_mesh_nonlinear_closure",
            ),
        )
        for case_id, element_count, load in specs
    ]


def generated_benchmark_factory_cases() -> list[BenchmarkCase]:
    return [
        *generated_analytic_axial_cases(),
        *generated_element_patch_cases(),
        *generated_nonlinear_material_mesh_cases(),
    ]


def solve_cubic_axial_displacement(
    *,
    load_fx: float,
    linear_stiffness: float,
    cubic_stiffness: float,
) -> float:
    """Solve k*u+c*u^3=P by monotone bisection for generated truth data."""
    if load_fx < 0.0 or linear_stiffness <= 0.0 or cubic_stiffness < 0.0:
        raise ValueError("unsupported cubic axial truth parameters")
    if load_fx == 0.0:
        return 0.0
    upper = max(load_fx / linear_stiffness, 1.0)
    while linear_stiffness * upper + cubic_stiffness * upper**3 < load_fx:
        upper *= 2.0
    lower = 0.0
    for _ in range(100):
        mid = 0.5 * (lower + upper)
        force = linear_stiffness * mid + cubic_stiffness * mid**3
        if force < load_fx:
            lower = mid
        else:
            upper = mid
    return 0.5 * (lower + upper)


def build_axial_chain_payload(*, case_id: str, element_count: int, load_fx: float) -> dict[str, Any]:
    if element_count <= 0:
        raise ValueError("element_count must be positive.")
    length = 2.0
    nodes = [
        {
            "id": f"N{index + 1}",
            "coordinates": [length * index / element_count, 0.0, 0.0],
        }
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index + 1}",
            "type": "truss",
            "nodes": [f"N{index + 1}", f"N{index + 2}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(element_count)
    ]
    supports = [{"id": "SUP1", "node": "N1", "dofs": "all"}]
    supports.extend(
        {
            "id": f"SUP{index + 1}",
            "node": f"N{index + 1}",
            "dofs": ["UY", "UZ"],
        }
        for index in range(1, element_count + 1)
    )
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "bar", "area": 0.01}],
        "loads": [
            {
                "id": "P1",
                "node": f"N{element_count + 1}",
                "components": [load_fx, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": case_id,
            "truth_class": "analytic_truth",
            "license_id": "repo-generated-analytic-v1",
            "claim_boundary": "generated_linear_axial_benchmark_seed_only",
        },
    }


def build_axis_aligned_axial_payload(
    *,
    case_id: str,
    axis: str,
    origin: tuple[float, float, float],
    length: float,
    load_fx_equivalent: float,
) -> dict[str, Any]:
    axis_labels = ("X", "Y", "Z")
    axis = axis.upper()
    if axis not in axis_labels:
        raise ValueError(f"Unsupported axis: {axis}")
    if length <= 0.0:
        raise ValueError("length must be positive.")
    axis_index = axis_labels.index(axis)
    start = list(origin)
    end = list(origin)
    end[axis_index] += length
    components = [0.0, 0.0, 0.0]
    components[axis_index] = load_fx_equivalent
    transverse_dofs = [f"U{label}" for label in axis_labels if label != axis]
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": start},
            {"id": "N2", "coordinates": end},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "truss",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "bar", "area": 0.01}],
        "loads": [{"id": "P1", "node": "N2", "components": components}],
        "supports": [
            {"id": "SUP1", "node": "N1", "dofs": "all"},
            {"id": "SUP2", "node": "N2", "dofs": transverse_dofs},
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": case_id,
            "truth_class": "analytic_truth",
            "axis": axis,
            "license_id": "repo-generated-analytic-v1",
            "claim_boundary": "generated_axis_aligned_axial_element_patch_only",
        },
    }


def build_nonlinear_material_mesh_payload(
    *,
    case_id: str,
    element_count: int,
    load_fx: float,
    linear_stiffness: float,
    cubic_stiffness: float,
) -> dict[str, Any]:
    if element_count <= 0:
        raise ValueError("element_count must be positive.")
    nodes = [
        {"id": f"N{index + 1}", "coordinates": [float(index), 0.0, 0.0]}
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index + 1}",
            "type": "axial",
            "nodes": [f"N{index + 1}", f"N{index + 2}"],
            "material": "M1",
        }
        for index in range(element_count)
    ]
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [
            {
                "id": "M1",
                "type": "cubic_spring",
                "linear_stiffness": linear_stiffness,
                "cubic_stiffness": cubic_stiffness,
            }
        ],
        "sections": [],
        "loads": [
            {
                "id": "P1",
                "node": f"N{element_count + 1}",
                "components": {"FX": load_fx, "FY": 0.0, "FZ": 0.0},
            }
        ],
        "supports": [{"id": "SUP1", "node": "N1", "dofs": ["UX"]}],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": case_id,
            "truth_class": "analytic_truth",
            "license_id": "repo-generated-analytic-v1",
            "claim_boundary": "generated_nonlinear_material_mesh_axial_chain_seed_only",
        },
    }


def run_benchmark_case(case: BenchmarkCase, *, tolerance: float = 1.0e-8) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir) / f"{case.case_id}.json"
        model_path.write_text(
            json.dumps(case.payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        model = load_model(model_path)
        result = analyze(
            model,
            AnalysisConfig(
                analysis_type=case.analysis_type,
                solver="phase3_benchmark_factory",
                tolerance=tolerance,
            ),
        )
    payload = result.to_dict()
    metrics = payload.get("metrics", {})
    if case.analysis_type == "nonlinear_static_material_mesh":
        actual_tip = float(metrics["tip_displacement_m"])
        actual_base_reaction = float(metrics["reactions"][0])
        tip_dof = "UX"
        base_reaction_dof = "UX"
        expected_tip = float(case.expected_outputs["tip_displacement_m"])
        expected_base_reaction = float(case.expected_outputs["base_reaction_kn"])
        nonlinear_checks_pass = bool(
            metrics["residual_gate_passed"] is True
            and metrics["increment_gate_passed"] is True
            and metrics["assembled_jacobian_fd_pass"] is True
            and metrics["series_force_equilibrium_pass"] is True
        )
    else:
        tip_node = f"N{len(case.payload['nodes'])}"
        tip_dof = str(case.expected_outputs.get("tip_dof", "UX"))
        base_reaction_dof = str(case.expected_outputs.get("base_reaction_dof", "UX"))
        expected_tip = float(
            case.expected_outputs.get("tip_displacement", case.expected_outputs.get("tip_ux"))
        )
        expected_base_reaction = float(
            case.expected_outputs.get("base_reaction", case.expected_outputs.get("base_reaction_ux"))
        )
        actual_tip = float(metrics["displacements"][tip_node][tip_dof])
        actual_base_reaction = float(metrics["reactions"]["N1"][base_reaction_dof])
        nonlinear_checks_pass = True
    tip_error = abs(actual_tip - expected_tip)
    reaction_error = abs(actual_base_reaction - expected_base_reaction)
    relative_residual = float(metrics["relative_residual"])
    energy_error = float(metrics.get("energy_balance_error", 0.0))
    expected_output_comparisons = expected_output_comparison_rows(
        case=case,
        actual_tip=actual_tip,
        actual_base_reaction=actual_base_reaction,
        metrics=metrics,
    )
    expected_output_contract_pass = all(
        row["status"] == "pass" for row in expected_output_comparisons
    )
    contract_pass = (
        payload["status"] == "ready"
        and expected_output_contract_pass
        and tip_error <= 1.0e-12
        and reaction_error <= 1.0e-12
        and relative_residual <= tolerance
        and (case.analysis_type == "nonlinear_static_material_mesh" or energy_error <= 1.0e-10)
        and nonlinear_checks_pass
        and metrics["residual_formula"] == "F_internal_minus_F_external"
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": case.case_id,
        "lane": case.lane,
        "status": "pass" if contract_pass else "fail",
        "contract_pass": contract_pass,
        "input_checksum": payload["input_checksum"],
        "manifest_checksum": case.checksum(),
        "analysis_type": case.analysis_type,
        "truth_class": case.truth_class,
        "node_count": len(case.payload["nodes"]),
        "element_count": len(case.payload["elements"]),
        "expected_outputs": case.expected_outputs,
        "expected_output_comparisons": expected_output_comparisons,
        "expected_output_contract_pass": expected_output_contract_pass,
        "convergence_history": scorecard_convergence_history(
            payload.get("convergence_history", [])
        ),
        "actual_outputs": {
            "tip_dof": tip_dof,
            "base_reaction_dof": base_reaction_dof,
            "tip_displacement": actual_tip,
            "base_reaction": actual_base_reaction,
        },
        "errors": {
            "tip_displacement_abs": tip_error,
            "base_reaction_abs": reaction_error,
        },
        "metrics": {
            "relative_residual": relative_residual,
            "energy_balance_error": energy_error,
            "residual_formula": metrics["residual_formula"],
            "regularization_used": metrics["regularization_used"],
            "fallback_used": metrics["fallback_used"],
            "residual_gate_passed": metrics.get("residual_gate_passed"),
            "increment_gate_passed": metrics.get("increment_gate_passed"),
            "assembled_jacobian_fd_pass": metrics.get("assembled_jacobian_fd_pass"),
            "series_force_equilibrium_pass": metrics.get("series_force_equilibrium_pass"),
        },
    }


def expected_output_comparison_rows(
    *,
    case: BenchmarkCase,
    actual_tip: float,
    actual_base_reaction: float,
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, expected in sorted(case.expected_outputs.items()):
        actual = _expected_output_actual_value(
            key=key,
            case=case,
            actual_tip=actual_tip,
            actual_base_reaction=actual_base_reaction,
            metrics=metrics,
        )
        status, abs_error = _expected_output_status(expected, actual)
        row: dict[str, Any] = {
            "field": key,
            "expected": expected,
            "actual": actual,
            "status": status,
        }
        if abs_error is not None:
            row["abs_error"] = abs_error
        rows.append(row)
    return rows


def _expected_output_actual_value(
    *,
    key: str,
    case: BenchmarkCase,
    actual_tip: float,
    actual_base_reaction: float,
    metrics: dict[str, Any],
) -> Any:
    if key in {"tip_ux", "tip_displacement", "tip_displacement_m"}:
        return actual_tip
    if key in {"base_reaction_ux", "base_reaction", "base_reaction_kn"}:
        return actual_base_reaction
    if key == "tip_dof":
        return str(case.expected_outputs.get("tip_dof", "UX"))
    if key == "base_reaction_dof":
        return str(case.expected_outputs.get("base_reaction_dof", "UX"))
    if key in {
        "assembled_jacobian_fd_pass",
        "series_force_equilibrium_pass",
        "residual_gate_passed",
        "increment_gate_passed",
    }:
        return metrics.get(key)
    return metrics.get(key)


def _expected_output_status(expected: Any, actual: Any) -> tuple[str, float | None]:
    if isinstance(expected, bool):
        return ("pass" if actual is expected else "review"), None
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual_number = float(actual)
        except (TypeError, ValueError):
            return "review", None
        abs_error = abs(actual_number - float(expected))
        return ("pass" if abs_error <= 1.0e-12 else "review"), abs_error
    return ("pass" if actual == expected else "review"), None


def scorecard_convergence_history(raw_history: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(raw_history, list):
        return rows
    for index, raw_row in enumerate(raw_history):
        if not isinstance(raw_row, dict):
            continue
        residual_norm = _history_residual_norm(raw_row)
        relative_increment = _history_relative_increment(raw_row)
        rows.append(
            {
                "iteration": int(raw_row.get("iteration", index) or 0),
                "step": str(raw_row.get("step", "analysis")),
                "residual_norm": residual_norm,
                "relative_residual": float(raw_row.get("relative_residual", residual_norm)),
                "relative_increment": relative_increment,
                "residual_gate_passed": raw_row.get("residual_gate_passed"),
                "increment_gate_passed": raw_row.get("increment_gate_passed"),
                "status": str(raw_row.get("status", "")),
            }
        )
    return rows


def _history_residual_norm(row: dict[str, Any]) -> float:
    if "residual_norm" in row:
        return float(row["residual_norm"])
    residual = row.get("residual_kn")
    if isinstance(residual, list) and residual:
        return max(abs(float(value)) for value in residual)
    return abs(float(row.get("relative_residual", 0.0)))


def _history_relative_increment(row: dict[str, Any]) -> float:
    if "relative_increment" in row:
        return float(row["relative_increment"])
    if "increment_abs_m" in row:
        return float(row["increment_abs_m"])
    increment = row.get("newton_increment_m")
    if isinstance(increment, list) and increment:
        return max(abs(float(value)) for value in increment)
    return 0.0


def build_manifest(cases: list[BenchmarkCase]) -> dict[str, Any]:
    rows = [case.manifest_row() for case in cases]
    return {
        "schema_version": "phase3-benchmark-factory-manifest.v1",
        "lane_count": len({case.lane for case in cases}),
        "case_count": len(rows),
        "lanes": sorted({case.lane for case in cases}),
        "rows": rows,
        "claim_boundary": (
            "Generated analytic-small, element-patch, and nonlinear material-mesh seed "
            "manifest only. "
            "This is not the full Phase 3 corpus breadth target."
        ),
    }


def run_benchmark_cases(cases: list[BenchmarkCase]) -> dict[str, Any]:
    rows = [run_benchmark_case(case) for case in cases]
    pass_count = sum(1 for row in rows if row["contract_pass"])
    expected_output_comparison_count = sum(
        len(row["expected_output_comparisons"]) for row in rows
    )
    expected_output_comparison_pass_count = sum(
        1
        for row in rows
        for comparison in row["expected_output_comparisons"]
        if comparison["status"] == "pass"
    )
    return {
        "schema_version": "phase3-benchmark-factory-scorecard.v1",
        "status": "pass" if pass_count == len(rows) else "blocked",
        "contract_pass": pass_count == len(rows),
        "case_count": len(rows),
        "pass_count": pass_count,
        "expected_output_comparison_count": expected_output_comparison_count,
        "expected_output_comparison_pass_count": expected_output_comparison_pass_count,
        "expected_output_contract_pass": (
            expected_output_comparison_count > 0
            and expected_output_comparison_pass_count == expected_output_comparison_count
        ),
        "lanes": sorted({row["lane"] for row in rows}),
        "rows": rows,
        "claim_boundary": (
            "This scorecard proves deterministic generated analytic-small and "
            "element-patch seed runners plus a narrow nonlinear material-mesh axial "
            "chain seed only. It does not close OpenSees, buildingSMART IFC, "
            "commercial cross-solver, large-model, full nonlinear full-mesh, or "
            "full Phase 3 quantity gates."
        ),
    }


def cases_to_jsonable(cases: list[BenchmarkCase]) -> list[dict[str, Any]]:
    return [asdict(case) for case in cases]
