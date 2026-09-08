"""Extended sparse storage through accepted states, source replay and recovery."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import coo_matrix, csc_matrix, csr_matrix

from structural_analysis.api import nonlinear_frame as api
from structural_analysis.api.planar_frame import (
    PlanarFrameConfig,
    analyze_planar_frame,
    validate_planar_frame_result,
)
from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d as dense,
    stateful_corotational_fiber_frame2d_engineering_recovery as recovery,
    stateful_corotational_fiber_frame2d_solver as solver,
    stateful_corotational_fiber_frame2d_sparse as sparse,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_corotational_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    validate_corotational_fiber_frame_general_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse_state import (
    COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE,
    StatefulCorotationalFiberFrame2DSparseAssembly,
    assemble_stateful_corotational_fiber_frame2d_sparse_state,
)
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.solvers.nonlinear import newton
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)
from tests.test_corotational_fiber_frame_sparse import _portal_problem
from tests.test_planar_frame_public_sparse_integration import SI_ROWS
from tests.test_unified_nonlinear_frame_api import _branching_payload, _model


def _forbid_dense(patch):
    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "extended sparse path must not assemble or convert global dense matrices"
        )

    for module in (dense, solver, recovery, sparse):
        patch.setattr(module, "assemble_stateful_corotational_fiber_frame2d", forbidden)
    for matrix in (csr_matrix, csc_matrix, coo_matrix):
        patch.setattr(matrix, "toarray", forbidden)
    # Member constitutive/kinematic matrices remain at most 6 by 6. Reject
    # global square allocation as well as calls to known dense assembly aliases.
    for name in ("zeros", "empty", "ones"):
        original = getattr(np, name)

        def checked(shape, *args, _original=original, **kwargs):
            if isinstance(shape, (tuple, list)) and len(shape) == 2:
                if shape[0] == shape[1] and shape[0] > 6:
                    forbidden()
            return _original(shape, *args, **kwargs)

        patch.setattr(np, name, checked)


@pytest.fixture(scope="module")
def sparse_portal():
    payload = json.loads(
        (
            Path(__file__).parents[1] / "examples/planar_frame_rc_portal.json"
        ).read_bytes()
    )
    document = parse_model_ir_v2(payload, require_analysis_ready=True)
    config = PlanarFrameConfig(
        load_steps=2, matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    )
    captured = {}
    create = api.create_corotational_fiber_frame_general_j1_j5_adapter

    def capture(compilation, path):
        adapter = create(compilation, path)
        captured.update(adapter=adapter, compilation=compilation, path=path)
        return adapter

    with pytest.MonkeyPatch.context() as patch:
        _forbid_dense(patch)
        patch.setattr(
            api, "create_corotational_fiber_frame_general_j1_j5_adapter", capture
        )
        result = analyze_planar_frame(document, config)
        assert result.converged, result.to_dict()
        assert validate_planar_frame_result(result).engineering_result_authority
        validate_corotational_fiber_frame_general_j1_j5_adapter(captured["adapter"])
    return document, config, result, captured


def test_public_extended_path_retains_csr_at_every_accepted_epoch(sparse_portal):
    _, _, result, captured = sparse_portal
    adapter = captured["adapter"]
    rows = adapter.stage_receipts[3].to_dict()["body"]["step_bindings"]
    assert len(rows) == len(captured["path"].steps) == 2
    for step, row in zip(captured["path"].steps, rows, strict=True):
        assembly = step.trial_assembly
        assert type(assembly) is StatefulCorotationalFiberFrame2DSparseAssembly
        assert (
            assembly.storage_profile
            == COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE
        )
        assert row["accepted_assembly"]["assembly_hash"] == assembly.assembly_hash
        assert row["accepted_assembly"]["storage_profile"] == assembly.storage_profile
        serialized = assembly.to_dict()
        assert "jacobian_kn_per_m" not in serialized
        assert "consistent_tangent_global" not in serialized
        for matrix in (
            assembly.jacobian,
            assembly.material_tangent,
            assembly.geometric_tangent,
            assembly.consistent_tangent,
        ):
            assert (
                matrix.values.ndim
                == matrix.row_ptr.ndim
                == matrix.column_indices.ndim
                == 1
            )
            with pytest.raises(ValueError):
                matrix.values.setflags(write=True)
    source = result.to_dict()["result_ir"]
    assert source["metrics"]["regularization_count"] == 0
    assert source["metrics"]["fallback_count"] == 0
    assert source["metrics"]["sparse_factorization_diagnostics_passed"] is True


def test_sparse_prefix_replay_and_engineering_recovery_avoid_dense(sparse_portal):
    document, config, original, captured = sparse_portal
    problem = captured["compilation"]._problem
    chain = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        original.checkpoint_artifact(), problem
    )
    prefix = make_stateful_corotational_fiber_frame2d_checkpoint_chain(
        problem, chain.checkpoints[:2]
    )
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        problem, prefix
    )
    with pytest.MonkeyPatch.context() as patch:
        _forbid_dense(patch)
        resumed = analyze_planar_frame(document, config, restart_checkpoint_chain=raw)
    assert resumed.converged, resumed.to_dict()
    assert resumed.checkpoint_artifact() == original.checkpoint_artifact()
    expected = original.to_dict()["result_ir"]
    actual = resumed.to_dict()["result_ir"]
    assert actual["contract_bindings"] == expected["contract_bindings"]
    assert actual["engineering_result_ir"] == expected["engineering_result_ir"]
    for name in SI_ROWS:
        assert actual[name] == expected[name]
    assert actual["metrics"]["replayed_prefix_step_count"] == 1


def test_replacing_early_epoch_with_valid_but_different_sparse_trial_fails(
    sparse_portal,
):
    _, _, _, captured = sparse_portal
    adapter, path = captured["adapter"], captured["path"]
    first = path.steps[0]
    coordinates = first.trial_solution.free_displacements_m.copy()
    coordinates[0] += 1e-6
    altered = assemble_stateful_corotational_fiber_frame2d_sparse_state(
        captured["compilation"]._problem,
        first.parent_checkpoint,
        target_load_factor=first.accepted_checkpoint.load_factor,
        trial_free_coordinates_m=coordinates,
    )
    # It is a valid, fully hashed sparse trial, but it is not the accepted trial.
    assert altered.to_dict()["assembly_hash"] != first.trial_assembly.assembly_hash
    changed_path = replace(
        path, steps=(replace(first, trial_assembly=altered), *path.steps[1:])
    )
    with pytest.raises(ValueError, match="exact solver state"):
        validate_corotational_fiber_frame_general_j1_j5_adapter(
            replace(adapter, _path=changed_path)
        )


def test_early_sparse_storage_cannot_be_relabelled_as_legacy(sparse_portal):
    _, _, _, captured = sparse_portal
    adapter, path = captured["adapter"], captured["path"]
    first = path.steps[0]
    solution = replace(
        first.trial_solution,
        config=replace(
            first.trial_solution.config, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND
        ),
    )
    changed_path = replace(
        path, steps=(replace(first, trial_solution=solution), *path.steps[1:])
    )
    with pytest.raises(ValueError, match="requires extended backend"):
        validate_corotational_fiber_frame_general_j1_j5_adapter(
            replace(adapter, _path=changed_path)
        )


@pytest.mark.parametrize("changed_field", ("child", "step_metric"))
def test_sparse_acceptance_binds_checkpoint_and_metric_load_factors(
    sparse_portal, changed_field
):
    _, _, _, captured = sparse_portal
    problem = captured["compilation"]._problem
    first = captured["path"].steps[0]
    changed_target = first.accepted_checkpoint.load_factor + 0.1
    if changed_field == "child":
        child = replace(
            first.accepted_checkpoint, load_factor=changed_target, state_hash=""
        )
        assert child.state_hash == child.compute_state_hash()
        changed = replace(first, accepted_checkpoint=child)
    else:
        changed = replace(
            first, metrics={**first.metrics, "target_load_factor": changed_target}
        )
    with pytest.raises(ValueError, match="exact solver state"):
        solver._sparse_accepted_assembly_binding(problem, changed)


@pytest.mark.parametrize(
    "backend", (VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND)
)
def test_default_and_legacy_backends_keep_dense_accepted_state(backend, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("legacy terminal representation must remain unchanged")

    monkeypatch.setattr(
        solver, "assemble_stateful_corotational_fiber_frame2d_sparse_state", forbidden
    )
    path = solver.run_stateful_corotational_fiber_frame2d_load_path(
        _portal_problem(),
        (0.5, 1.0),
        config=NewtonRaphsonConfig(matrix_backend=backend),
    )
    assert path.contract_pass
    for step in path.steps:
        assert (
            type(step.trial_assembly) is dense.StatefulCorotationalFiberFrame2DAssembly
        )
        assert "jacobian_kn_per_m" in step.trial_assembly.to_dict()
        assert "storage_profile" not in step.trial_assembly.to_dict()


def test_failed_extended_step_rolls_back_with_sparse_trial_state():
    problem = _portal_problem()
    parent = dense.initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    original = parent.canonical_bytes()
    with pytest.MonkeyPatch.context() as patch:
        _forbid_dense(patch)
        step = solver.solve_stateful_corotational_fiber_frame2d_load_step(
            problem,
            parent,
            target_load_factor=1.0,
            config=NewtonRaphsonConfig(
                matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND, max_iterations=1
            ),
        )
    assert not step.committed and step.status == "blocked"
    assert step.accepted_checkpoint is parent
    assert parent.canonical_bytes() == original
    assert step.metrics["rollback_exact"] is True
    assert type(step.trial_assembly) is StatefulCorotationalFiberFrame2DSparseAssembly


def test_prescribed_only_sparse_path_uses_no_factorization_or_dense_copy(tmp_path):
    payload = _branching_payload()
    payload["loads"] = []
    payload["supports"] = [
        {
            "node": row["id"],
            "dofs": ["UX", "UY", "RZ"],
            **({"prescribed_values": {"UX": 1e-4}} if row["id"] == "N6" else {}),
        }
        for row in payload["nodes"]
    ]

    def forbidden(*_args, **_kwargs):
        pytest.fail("prescribed-only path must not factorize a Newton system")

    with pytest.MonkeyPatch.context() as patch:
        _forbid_dense(patch)
        patch.setattr(newton, "_solve_vector_increment", forbidden)
        result = api.analyze_nonlinear_frame(
            _model(tmp_path, payload, "prescribed-only.json"),
            api.NonlinearFrameConfig(
                profile=api.COROTATIONAL_GENERAL_PROFILE,
                load_steps=2,
                matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
            ),
        )
    assert result.contract_pass, result.to_dict()
    assert result.metrics["solver_executed"] is False
    assert result.metrics["sparse_factorization_count"] == 0
    assert result.metrics["sparse_factorization_policy_hash"] is None
    assert result.convergence_history == ()
    assert result.node_displacements[-1]["UX_m"] == 1e-4
