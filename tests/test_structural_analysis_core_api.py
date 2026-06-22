from __future__ import annotations

import json
import os
import importlib
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

structural_analysis = importlib.import_module("structural_analysis")
core_api = importlib.import_module("structural_analysis.api.core")
AnalysisConfig = structural_analysis.AnalysisConfig
analyze = structural_analysis.analyze
load_model = structural_analysis.load_model
validate = structural_analysis.validate
CLAIM_BOUNDARY_VERSION = core_api.CLAIM_BOUNDARY_VERSION


def _write_neutral_model(path: Path) -> None:
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [1.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "rectangular"}],
        "loads": [],
        "supports": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_linear_static_truss_model(path: Path) -> None:
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "T1",
                "type": "truss",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "axial", "area": 0.01}],
        "loads": [{"node": "N2", "components": {"FX": 10.0, "FY": 0.0, "FZ": 0.0}}],
        "supports": [
            {"node": "N1", "dofs": ["UX", "UY", "UZ"]},
            {"node": "N2", "dofs": ["UY", "UZ"]},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_nonlinear_material_mesh_model(path: Path) -> None:
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [1.0, 0.0, 0.0]},
            {"id": "N3", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "axial",
                "nodes": ["N1", "N2"],
                "material": "M1",
            },
            {
                "id": "E2",
                "type": "axial",
                "nodes": ["N2", "N3"],
                "material": "M1",
            },
        ],
        "materials": [
            {
                "id": "M1",
                "type": "cubic_spring",
                "linear_stiffness": 100.0,
                "cubic_stiffness": 1000.0,
            }
        ],
        "sections": [],
        "loads": [{"node": "N3", "components": {"FX": 100.0, "FY": 0.0, "FZ": 0.0}}],
        "supports": [{"node": "N1", "dofs": ["UX"]}],
        "metadata": {"case_id": "test_api_material_mesh_newton"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pyproject_discovers_structural_analysis_package() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '[project.scripts]\nstructural-analysis = "structural_analysis.api.cli:main"' in (
        pyproject_text
    )
    assert '[tool.setuptools.packages.find]\nwhere = ["src"]' in pyproject_text
    assert 'include = ["structural_analysis*"]' in pyproject_text
    assert "py-modules" not in pyproject_text


def test_core_api_model_health_result_keeps_provenance(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    _write_neutral_model(model_path)

    model = load_model(model_path)
    result = analyze(model, AnalysisConfig(analysis_type="model_health", tolerance=1e-7))
    report = validate(result, {"node_count": 2, "element_count": 1})

    assert model.schema_version == "structural-analysis-canonical-model.v1"
    assert model.units.length == "m"
    assert model.coordinate_system.up_axis == "Z"
    assert result.status == "ready"
    assert result.engine_version
    assert result.input_checksum.startswith("sha256:")
    assert result.tolerance == 1e-7
    assert result.convergence_history[0]["status"] == "ready"
    assert result.claim_boundary_version == CLAIM_BOUNDARY_VERSION
    assert report.status == "pass"
    assert report.contract_pass is True
    assert report.unsupported_fields == []
    assert report.comparisons[0]["status"] == "pass"


def test_linear_static_axial_truss_uses_canonical_solver_path(tmp_path: Path) -> None:
    model_path = tmp_path / "truss.json"
    _write_linear_static_truss_model(model_path)

    model = load_model(model_path)
    result = analyze(
        model,
        AnalysisConfig(
            analysis_type="linear_static",
            solver="developer_preview_linear_static_axial",
            tolerance=1e-9,
        ),
    )
    report = validate(
        result,
        {
            "residual_norm": 0.0,
            "residual_formula": "F_internal_minus_F_external",
            "max_displacement": 0.01,
            "claim_boundary": "linear_static_axial_truss_preview_only",
        },
    )

    assert result.status == "ready"
    assert result.unsupported_features == []
    assert result.metrics["free_dof_count"] == 1
    assert result.metrics["constrained_dof_count"] == 5
    assert result.metrics["residual_formula"] == "F_internal_minus_F_external"
    assert result.metrics["residual_norm"] == 0.0
    assert result.metrics["free_residual_norm"] == 0.0
    assert result.metrics["relative_residual"] == 0.0
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.metrics["stiffness_storage"] == "dense_numpy"
    assert result.metrics["matrix_backend"] == "numpy_linalg_solve_dense"
    assert result.metrics["sparse_backend_used"] is False
    assert result.metrics["energy_balance_error"] == 0.0
    assert result.metrics["external_forces"]["N2"]["UX"] == 10.0
    assert result.metrics["internal_forces"]["N2"]["UX"] == 10.0
    assert result.metrics["displacements"]["N2"]["UX"] == 0.01
    assert result.metrics["reactions"]["N1"]["UX"] == -10.0
    assert result.convergence_history[0]["step"] == "linear_static"
    assert report.status == "pass"
    assert report.contract_pass is True
    assert all(row["status"] == "pass" for row in report.comparisons)


def test_linear_static_sparse_backend_is_selectable_via_analysis_config(tmp_path: Path) -> None:
    model_path = tmp_path / "truss.json"
    _write_linear_static_truss_model(model_path)

    model = load_model(model_path)
    result = analyze(
        model,
        AnalysisConfig(
            analysis_type="linear_static",
            solver="developer_preview_linear_static_axial_sparse",
            tolerance=1e-9,
            matrix_backend="scipy_sparse_spsolve_cpu",
        ),
    )
    report = validate(
        result,
        {
            "residual_norm": 0.0,
            "matrix_backend": "scipy_sparse_spsolve_cpu",
            "sparse_backend_used": True,
            "stiffness_storage": "scipy_sparse_csr",
        },
    )

    assert result.status == "ready"
    assert result.metrics["matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert result.metrics["sparse_backend_used"] is True
    assert result.metrics["stiffness_storage"] == "scipy_sparse_csr"
    assert result.metrics["displacements"]["N2"]["UX"] == 0.01
    assert result.metrics["reactions"]["N1"]["UX"] == -10.0
    assert report.status == "pass"
    assert report.contract_pass is True
    assert all(row["status"] == "pass" for row in report.comparisons)


def test_nonlinear_material_mesh_uses_canonical_api_path(tmp_path: Path) -> None:
    model_path = tmp_path / "material_mesh.json"
    _write_nonlinear_material_mesh_model(model_path)

    model = load_model(model_path)
    result = analyze(
        model,
        AnalysisConfig(
            analysis_type="nonlinear_static_material_mesh",
            solver="developer_preview_material_mesh_newton_axial_chain",
            tolerance=1.0e-10,
            max_iterations=25,
        ),
    )
    report = validate(
        result,
        {
            "residual_formula": "F_internal_minus_F_external",
            "node_count": 3,
            "element_count": 2,
            "assembled_jacobian_fd_pass": True,
            "series_force_equilibrium_pass": True,
            "regularization_used": False,
            "fallback_used": False,
            "claim_boundary": "nonlinear_material_mesh_axial_chain_preview_only",
        },
    )

    assert result.status == "ready"
    assert result.unsupported_features == []
    assert result.metrics["matrix_backend"] == "numpy_linalg_solve_dense"
    assert result.metrics["sparse_backend_used"] is False
    assert result.metrics["residual_formula"] == "F_internal_minus_F_external"
    assert result.metrics["residual_gate_passed"] is True
    assert result.metrics["increment_gate_passed"] is True
    assert result.metrics["assembled_jacobian_fd_pass"] is True
    assert result.metrics["series_force_equilibrium_pass"] is True
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert abs(result.metrics["reactions"][0] + 100.0) <= 1.0e-10
    assert len(result.convergence_history) >= 1
    assert report.status == "pass"
    assert report.contract_pass is True
    assert all(row["status"] == "pass" for row in report.comparisons)


def test_nonlinear_material_mesh_sparse_backend_is_selectable(tmp_path: Path) -> None:
    model_path = tmp_path / "material_mesh.json"
    _write_nonlinear_material_mesh_model(model_path)

    model = load_model(model_path)
    dense_result = analyze(
        model,
        AnalysisConfig(
            analysis_type="nonlinear_static_material_mesh",
            solver="developer_preview_material_mesh_newton_axial_chain",
            tolerance=1.0e-10,
            max_iterations=25,
        ),
    )
    sparse_result = analyze(
        model,
        AnalysisConfig(
            analysis_type="nonlinear_static_material_mesh",
            solver="developer_preview_material_mesh_newton_axial_chain_sparse",
            tolerance=1.0e-10,
            max_iterations=25,
            matrix_backend="scipy_sparse_spsolve_cpu",
        ),
    )
    report = validate(
        sparse_result,
        {
            "matrix_backend": "scipy_sparse_spsolve_cpu",
            "sparse_backend_used": True,
            "stiffness_storage": "scipy_sparse_csr",
            "assembled_jacobian_fd_pass": True,
            "series_force_equilibrium_pass": True,
            "regularization_used": False,
            "fallback_used": False,
        },
    )

    assert sparse_result.status == "ready"
    assert sparse_result.unsupported_features == []
    assert sparse_result.metrics["matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert sparse_result.metrics["sparse_backend_used"] is True
    assert sparse_result.metrics["stiffness_storage"] == "scipy_sparse_csr"
    assert sparse_result.metrics["regularization_used"] is False
    assert sparse_result.metrics["fallback_used"] is False
    assert sparse_result.metrics["residual_gate_passed"] is True
    assert sparse_result.metrics["increment_gate_passed"] is True
    assert sparse_result.metrics["tip_displacement_m"] == dense_result.metrics["tip_displacement_m"]
    assert sparse_result.metrics["reactions"] == dense_result.metrics["reactions"]
    assert report.status == "pass"
    assert report.contract_pass is True
    assert all(row["status"] == "pass" for row in report.comparisons)


def test_nonlinear_material_mesh_cli_matches_python_api(tmp_path: Path) -> None:
    model_path = tmp_path / "material_mesh.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    reference_path = tmp_path / "reference.json"
    _write_nonlinear_material_mesh_model(model_path)
    reference_path.write_text(
        json.dumps(
            {
                "assembled_jacobian_fd_pass": True,
                "claim_boundary": "nonlinear_material_mesh_axial_chain_preview_only",
                "element_count": 2,
                "fallback_used": False,
                "node_count": 3,
                "regularization_used": False,
                "residual_formula": "F_internal_minus_F_external",
                "series_force_equilibrium_pass": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    model = load_model(model_path)
    expected_result = analyze(
        model,
        AnalysisConfig(
            analysis_type="nonlinear_static_material_mesh",
            solver="developer_preview_material_mesh_newton_axial_chain",
            tolerance=1.0e-10,
            max_iterations=25,
        ),
    )
    expected_report = validate(expected_result, json.loads(reference_path.read_text(encoding="utf-8")))
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_ROOT)
        if not env.get("PYTHONPATH")
        else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "nonlinear_static_material_mesh",
            "--solver",
            "developer_preview_material_mesh_newton_axial_chain",
            "--tolerance",
            "1e-10",
            "--max-iterations",
            "25",
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(result_path.read_text(encoding="utf-8")) == expected_result.to_dict()
    assert json.loads(report_path.read_text(encoding="utf-8")) == expected_report.to_dict()


def test_cli_nonlinear_material_mesh_sparse_backend_uses_configured_backend(tmp_path: Path) -> None:
    model_path = tmp_path / "material_mesh.json"
    result_path = tmp_path / "sparse_result.json"
    report_path = tmp_path / "sparse_report.json"
    reference_path = tmp_path / "sparse_reference.json"
    _write_nonlinear_material_mesh_model(model_path)
    reference_path.write_text(
        json.dumps(
            {
                "fallback_used": False,
                "matrix_backend": "scipy_sparse_spsolve_cpu",
                "regularization_used": False,
                "sparse_backend_used": True,
                "stiffness_storage": "scipy_sparse_csr",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_ROOT)
        if not env.get("PYTHONPATH")
        else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "nonlinear_static_material_mesh",
            "--solver",
            "developer_preview_material_mesh_newton_axial_chain_sparse",
            "--tolerance",
            "1e-10",
            "--max-iterations",
            "25",
            "--matrix-backend",
            "scipy_sparse_spsolve_cpu",
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["metrics"]["matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert result["metrics"]["sparse_backend_used"] is True
    assert result["metrics"]["stiffness_storage"] == "scipy_sparse_csr"
    assert report["status"] == "pass"
    assert report["contract_pass"] is True


def test_linear_static_blocks_unsupported_frame_without_false_pass(tmp_path: Path) -> None:
    model_path = tmp_path / "frame.json"
    _write_neutral_model(model_path)

    model = load_model(model_path)
    result = analyze(model, AnalysisConfig(analysis_type="linear_static"))
    report = validate(result)

    assert result.status == "blocked"
    unsupported_kinds = {row["kind"] for row in result.unsupported_features}
    assert "linear_static_element_not_supported" in unsupported_kinds
    assert "linear_static_loads_missing" in unsupported_kinds
    assert "linear_static_supports_missing" in unsupported_kinds
    assert report.status == "blocked"
    assert report.contract_pass is False


def test_ifc_entity_scan_does_not_return_false_solver_pass(tmp_path: Path) -> None:
    ifc_path = tmp_path / "model.ifc"
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#10=IFCBUILDINGSTOREY('id1',$,'L1',$,$,$,$,$);",
                "#20=IFCBEAM('b1',$,'B1',$,$,$,$,$);",
                "#21=IFCCOLUMN('c1',$,'C1',$,$,$,$,$);",
                "#22=IFCSLAB('s1',$,'S1',$,$,$,$,.FLOOR.);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    model = load_model(ifc_path)
    result = analyze(model, AnalysisConfig(analysis_type="linear_static"))
    report = validate(result)

    assert model.source_format == "ifc_step"
    assert len(model.elements) == 3
    assert model.metadata["structural_entity_count"] == 3
    assert model.metadata["storeys"][0]["name"] == "L1"
    assert result.status == "blocked"
    assert result.convergence_history == []
    unsupported_kinds = {item["kind"] for item in result.unsupported_features}
    assert "ifc_geometry_not_canonicalized" in unsupported_kinds
    assert "ifc_load_model_missing" in unsupported_kinds
    assert "ifc_material_binding_missing" in unsupported_kinds
    assert "ifc_section_binding_missing" in unsupported_kinds
    assert report.status == "blocked"
    assert report.contract_pass is False
    assert "ifc_geometry_not_canonicalized" in report.developer_preview_blocked_fields


def test_ifc_load_related_entities_are_visible_but_still_blocked(tmp_path: Path) -> None:
    ifc_path = tmp_path / "loads.ifc"
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#1=IFCBEAM('b1',$,'B1',$,$,$,$,$);",
                "#2=IFCMATERIAL('STEEL');",
                "#3=IFCISHAPEPROFILEDEF(.AREA.,'WIDE_FLANGE',$,$,$);",
                "#4=IFCSTRUCTURALLOADSINGLEDISPLACEMENT('load',$,$,$,$,$,$);",
                "#5=IFCSTRUCTURALCURVEACTION('action',$,$,$,$,$,$,$,$);",
                "#6=IFCSTRUCTURALLOADGROUP('case',$,'LC1',$,$,$,.LOAD_CASE.);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    model = load_model(ifc_path)
    result = analyze(model, AnalysisConfig(analysis_type="model_health"))

    assert len(model.elements) == 1
    assert len(model.materials) == 1
    assert len(model.sections) == 1
    assert len(model.loads) == 3
    assert model.metadata["load_related_entity_count"] == 3
    unsupported_kinds = {item["kind"] for item in result.unsupported_features}
    assert "ifc_geometry_not_canonicalized" in unsupported_kinds
    assert "ifc_load_model_missing" not in unsupported_kinds
    assert result.status == "blocked"


def test_mgt_load_model_maps_topology_without_solver_claim() -> None:
    model_path = REPO_ROOT / "tests/fixtures/foundation_realish/foundation_deep_small.mgt"

    model = load_model(model_path)
    result = analyze(model, AnalysisConfig(analysis_type="model_health"))
    report = validate(result, {"node_count": 10, "element_count": 4, "support_count": 0})

    assert model.source_format == "midas_mgt"
    assert model.units.length == "m"
    assert model.units.force == "kN"
    assert len(model.nodes) == 10
    assert len(model.elements) == 4
    assert {element["type"] for element in model.elements} == {"frame", "shell"}
    assert model.metadata["adapter_scope"].startswith("topology/model-health import only")
    assert model.unsupported_features == []
    assert result.status == "ready"
    assert result.metrics["node_count"] == 10
    assert result.metrics["element_count"] == 4
    assert report.status == "pass"
    assert report.contract_pass is True


def test_mgt_skipped_elements_are_blocked_not_silently_dropped(tmp_path: Path) -> None:
    mgt_path = tmp_path / "bad_element.mgt"
    mgt_path.write_text(
        """*UNIT
KN, M, C
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
*ELEMENT
1, UNKNOWN, 1, 1, 1, 2, 0, 0
""",
        encoding="utf-8",
    )

    model = load_model(mgt_path)
    result = analyze(model, AnalysisConfig(analysis_type="model_health"))
    report = validate(result)

    assert result.status == "blocked"
    unsupported_kinds = {row["kind"] for row in result.unsupported_features}
    assert "mgt_element_rows_skipped" in unsupported_kinds
    assert "mgt_elements_missing" in unsupported_kinds
    assert report.status == "blocked"
    assert report.contract_pass is False


def test_mgt_structural_sections_preserved_as_blockers(tmp_path: Path) -> None:
    mgt_path = tmp_path / "offset_link.mgt"
    mgt_path.write_text(
        """*UNIT
KN, M, C
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
*MATERIAL
1, STEEL
*SECTION
1, H-100x100
*ELEMENT
1, BEAM, 1, 1, 1, 2, 0, 0
*OFFSET
1, START, 0.1, 0.0, 0.0
*ELASTICLINK
1, 1, 2, RIGID, 1.0e9
""",
        encoding="utf-8",
    )

    model = load_model(mgt_path)
    result = analyze(model, AnalysisConfig(analysis_type="model_health"))

    assert result.status == "blocked"
    unsupported_kinds = {row["kind"] for row in result.unsupported_features}
    assert "mgt_beam_offset_unsupported" in unsupported_kinds
    assert "mgt_elastic_link_unsupported" in unsupported_kinds
    assert model.metadata["unsupported_structural_sections"] == {
        "ELASTICLINK": 1,
        "OFFSET": 1,
    }


def test_cli_uses_same_result_and_report_schema(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    _write_neutral_model(model_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "model_health",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result["status"] == "ready"
    assert result["input_checksum"].startswith("sha256:")
    assert result["convergence_history"]
    assert result["claim_boundary_version"] == CLAIM_BOUNDARY_VERSION
    assert report["status"] == "pass"
    assert report["contract_pass"] is True


def test_cli_linear_static_uses_same_axial_solver_schema(tmp_path: Path) -> None:
    model_path = tmp_path / "truss.json"
    result_path = tmp_path / "linear_result.json"
    report_path = tmp_path / "linear_report.json"
    _write_linear_static_truss_model(model_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(
        json.dumps(
            {
                "residual_norm": 0.0,
                "max_displacement": 0.01,
                "claim_boundary": "linear_static_axial_truss_preview_only",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "linear_static",
            "--solver",
            "developer_preview_linear_static_axial",
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result["status"] == "ready"
    assert result["analysis_type"] == "linear_static"
    assert result["metrics"]["displacements"]["N2"]["UX"] == 0.01
    assert result["metrics"]["claim_boundary"] == "linear_static_axial_truss_preview_only"
    assert report["status"] == "pass"
    assert report["contract_pass"] is True


def test_cli_linear_static_sparse_backend_uses_configured_backend(tmp_path: Path) -> None:
    model_path = tmp_path / "truss.json"
    result_path = tmp_path / "sparse_result.json"
    report_path = tmp_path / "sparse_report.json"
    _write_linear_static_truss_model(model_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(
        json.dumps(
            {
                "matrix_backend": "scipy_sparse_spsolve_cpu",
                "sparse_backend_used": True,
                "stiffness_storage": "scipy_sparse_csr",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "linear_static",
            "--solver",
            "developer_preview_linear_static_axial_sparse",
            "--matrix-backend",
            "scipy_sparse_spsolve_cpu",
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result["status"] == "ready"
    assert result["metrics"]["matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert result["metrics"]["sparse_backend_used"] is True
    assert result["metrics"]["stiffness_storage"] == "scipy_sparse_csr"
    assert report["status"] == "pass"
    assert report["contract_pass"] is True


def test_cli_ifc_writes_blocked_result_without_false_pass(tmp_path: Path) -> None:
    ifc_path = tmp_path / "model.ifc"
    result_path = tmp_path / "ifc_result.json"
    report_path = tmp_path / "ifc_report.json"
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#1=IFCBEAM('b1',$,'B1',$,$,$,$,$);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(ifc_path),
            "--analysis-type",
            "model_health",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    unsupported_kinds = {row["kind"] for row in result["unsupported_features"]}
    assert result["status"] == "blocked"
    assert "ifc_geometry_not_canonicalized" in unsupported_kinds
    assert report["status"] == "blocked"
    assert report["contract_pass"] is False
