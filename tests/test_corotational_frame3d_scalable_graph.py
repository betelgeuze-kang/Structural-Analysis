"""Actual >256-equation native-sparse 3D frame integration coverage."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
)
from structural_analysis.assembly.corotational_frame3d_graph import (
    COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS,
    CorotationalFrame3DGraphModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    solve_stateful_corotational_frame3d_sparse_load_path,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    ScalableSparseFactorizationDiagnostic,
    ScalableSparseFactorizationPolicy,
)


ROOT = Path(__file__).resolve().parents[1]


def _section() -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=2.0e8,
            g_n_per_m2=8.0e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )


def _large_chain() -> StatefulCorotationalFrame3DSparseModel:
    node_count = 44
    section = _section()
    coordinates = tuple((0.1 * index, 0.0, 0.0) for index in range(node_count))
    members = tuple(
        CorotationalFrame3DMember(
            f"member-{index:03d}",
            index,
            index + 1,
            section,
        )
        for index in range(node_count - 1)
    )
    load = [0.0] * (6 * node_count)
    load[6 * (node_count - 1)] = 1.0
    elastic = CorotationalFrame3DGraphModel(
        node_coordinates_m=coordinates,
        members=members,
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="actual-258-free-equation-chain",
    )
    materials = tuple(
        BilinearCombinedHardeningSteel(
            elastic_modulus_mpa=200_000.0,
            material_id=f"steel-{index:03d}",
        )
        for index in range(node_count - 1)
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, materials)


def test_actual_258_equation_frame_uses_blocked_exact_sparse_diagnostics() -> None:
    model = _large_chain()
    policy = ScalableSparseFactorizationPolicy(
        maximum_equations=COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS,
        inverse_solve_block_size=32,
    )
    config = StatefulCorotationalFrame3DSparseConfig(
        residual_relative_tolerance=1.0e-7,
        residual_absolute_tolerance_kn=1.0e-6,
        maximum_iterations=8,
        factorization_policy=policy,
    )

    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )

    assert len(model.free_dofs) == 258
    assert result.contract_pass is True
    assert result.final_checkpoint.displacement[-6] > 0.0
    assert result.steps[0].checkpoint.converged_iterations == 1
    diagnostics = result.steps[0].factorization_diagnostics
    assert len(diagnostics) == 2
    for diagnostic in diagnostics:
        assert type(diagnostic) is ScalableSparseFactorizationDiagnostic
        assert diagnostic.equation_count == 258
        assert diagnostic.inverse_solve_block_count == 9
        assert diagnostic.condition_estimate_is_exact is True
        assert diagnostic.condition_number_1 < policy.maximum_condition_number_1
        assert diagnostic.contract_pass is True
        assert diagnostic.claims["integrated_nonlinear_3d_backend"] is True
        assert diagnostic.claims["production_scale_sparse_policy"] is False
        assert diagnostic.claims["external_vv"] is False
        assert diagnostic.claims["release_authority"] is False
        assert diagnostic.regularization_used is False
        assert diagnostic.fallback_used is False
        assert diagnostic.to_manifest()["contract_pass"] is True
    assert result.steps[0].equation_scaling.scaled_tangent_condition == pytest.approx(
        diagnostics[-1].condition_number_1
    )

    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result.final_checkpoint.to_dict())


def test_258_equation_graph_requires_explicit_larger_policy() -> None:
    from structural_analysis.assembly import (
        CorotationalFrame3DGraphModel as ExportedCorotationalFrame3DGraphModel,
    )

    model = _large_chain()

    assert ExportedCorotationalFrame3DGraphModel is CorotationalFrame3DGraphModel
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="sparse_condition_diagnostic_scope_exceeded",
    ):
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=StatefulCorotationalFrame3DSparseConfig(maximum_iterations=1),
        )


def test_larger_graph_contract_rejects_disconnected_and_oversized_graphs() -> None:
    section = _section()
    load = [0.0] * 18
    load[12] = 1.0
    disconnected_members = (CorotationalFrame3DMember("member-0", 0, 1, section),)
    with pytest.raises(ValueError, match="connected"):
        CorotationalFrame3DGraphModel(
            node_coordinates_m=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
            members=disconnected_members,
            restrained_dofs=tuple(range(6)),
            reference_load_kn=tuple(load),
        )

    node_count = 129
    with_error_load = [0.0] * (6 * node_count)
    with_error_load[-6] = 1.0
    oversized_coordinates = tuple(
        (float(index), 0.0, 0.0) for index in range(node_count)
    )
    oversized_members = tuple(
        CorotationalFrame3DMember(f"member-{index}", index, index + 1, section)
        for index in range(node_count - 1)
    )
    with pytest.raises(ValueError, match="node count"):
        CorotationalFrame3DGraphModel(
            node_coordinates_m=oversized_coordinates,
            members=oversized_members,
            restrained_dofs=tuple(range(6)),
            reference_load_kn=tuple(with_error_load),
        )
