from __future__ import annotations

import ast
from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.ai.projection import (  # noqa: E402
    build_fixed_rank_projection,
)
from structural_analysis.engine_v2.ai.proposal import (  # noqa: E402
    AICorrectionProposalError,
    _array_descriptor,
    _deterministic_proposal_id,
    _proposal_hash,
    build_phase0_ai_proposal,
    validate_phase0_ai_proposal,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    compile_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
    open_trial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/ai_correction_proposal_v1.schema.json"
)
PROPOSAL_SOURCE = SRC_ROOT / "structural_analysis/engine_v2/ai/proposal.py"


def _plan(load_pattern_id: str = "LC_WEAK"):
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    return compile_execution_plan(buffers)


def _projection(plan, *, rank_cap: int = 3):
    n = len(plan.free_dofs)
    first = np.linspace(1.0, 2.0, n, dtype="<f8")
    second = np.linspace(-0.75, 0.5, n, dtype="<f8")
    candidates = np.column_stack((first, second))
    return build_fixed_rank_projection(plan, candidates, rank_cap=rank_cap)


def _proposal(*, trust_radius: float = 1.0):
    plan = _plan()
    state = create_initial_state(plan)
    projection = _projection(plan)
    proposal = build_phase0_ai_proposal(
        plan,
        state,
        projection,
        np.asarray([0.2, -0.1]),
        trust_radius,
    )
    return plan, state, projection, proposal


def _refresh_descriptor(proposal, name: str, value: np.ndarray):
    descriptors = tuple(
        _array_descriptor(row.name, value) if row.name == name else row
        for row in proposal.descriptors
    )
    return descriptors


def test_ai_proposal_schema_is_strict_and_manifest_has_no_commit_authority() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, _, _, proposal = _proposal()
    manifest = proposal.to_dict()

    assert not list(validator.iter_errors(manifest))
    assert manifest["status"] == "unevaluated"
    assert manifest["hook"] == {
        "name": "initial_guess",
        "overlay_only": True,
        "final_result": False,
        "direct_state_commit": False,
        "promotion_authorized": False,
    }
    assert manifest["uncertainty"] == {
        "ood_status": "not_evaluated",
        "statistical_calibration": False,
        "acceptance_eligible": False,
    }
    assert manifest["claim_boundary"] == (
        "phase0_unevaluated_initial_guess_proposal_only"
    )

    with_extra = proposal.to_dict()
    with_extra["hook"]["accepted"] = True
    assert list(validator.iter_errors(with_extra))
    with_values_extra = proposal.to_dict()
    with_values_extra["arrays"]["correction_free"]["device_pointer"] = "0x1"
    assert list(validator.iter_errors(with_values_extra))


def test_ai_proposal_binds_model_buffers_plan_state_and_projection() -> None:
    plan, state, projection, proposal = _proposal()

    assert proposal.model_ir_content_hash == plan.model_ir_content_hash
    assert proposal.solver_numeric_buffer_hash == plan.solver_numeric_buffer_hash
    assert proposal.solver_entity_mapping_hash == plan.solver_entity_mapping_hash
    assert proposal.solver_artifact_hash == plan.solver_artifact_hash
    assert proposal.execution_plan_hash == plan.plan_hash
    assert proposal.operator_hash == plan.operator_hash
    assert proposal.pattern_hash == plan.pattern_hash
    assert proposal.partition_hash == plan.partition_hash
    assert proposal.base_state_hash == state.state_hash
    assert proposal.base_state_epoch == state.epoch
    assert proposal.projection_hash == projection.projection_hash
    assert proposal.retained_rank == projection.retained_rank
    assert proposal.rank_cap == projection.rank_cap <= 16
    validate_phase0_ai_proposal(
        proposal,
        expected_plan=plan,
        expected_accepted_state=state,
        expected_projection=projection,
    )


def test_ai_proposal_computes_qy_and_dqy_in_the_declared_coordinates() -> None:
    _, _, projection, proposal = _proposal()
    expected_scaled = projection.basis_q @ proposal.coefficients_y
    expected_free = projection.scaling_diagonal * expected_scaled
    manifest = proposal.to_dict()

    np.testing.assert_allclose(
        proposal.correction_scaled, expected_scaled, rtol=0.0, atol=1.0e-15
    )
    np.testing.assert_allclose(
        proposal.correction_free, expected_free, rtol=0.0, atol=1.0e-15
    )
    assert proposal.target_vector_space == "scaled_reduced_free_dof"
    expected_units = "sqrt_joule_energy_coordinate"
    assert manifest["target"]["scaled_units"] == expected_units
    assert manifest["trust"]["units"] == expected_units
    assert manifest["arrays"]["coefficients_y"]["units"] == expected_units
    assert manifest["arrays"]["correction_scaled"]["units"] == expected_units
    assert manifest["arrays"]["correction_free"]["units"] == (
        "m_or_rad_by_global_dof"
    )
    assert proposal.basis_gram_condition <= proposal.basis_gram_condition_limit
    assert proposal.coefficient_l2_norm <= (
        proposal.trust_radius + proposal.trust_absolute_tolerance
    )
    assert proposal.correction_scaled_l2_norm <= (
        proposal.trust_radius + proposal.trust_absolute_tolerance
    )


def test_ai_proposal_arrays_are_immutable_f64_and_descriptor_bound() -> None:
    _, _, _, proposal = _proposal()

    assert tuple(row.name for row in proposal.descriptors) == (
        "coefficients_y",
        "correction_scaled",
        "correction_free",
    )
    for descriptor in proposal.descriptors:
        array = proposal.array(descriptor.name)
        assert array.dtype.str == "<f8"
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        assert descriptor.byte_length == array.nbytes
        assert descriptor.shape == array.shape
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(KeyError):
        proposal.array("dense_projector")


def test_ai_proposal_is_deterministic_and_does_not_change_accepted_state() -> None:
    plan = _plan()
    state = create_initial_state(plan)
    projection = _projection(plan)
    before_hash = state.state_hash
    before_displacement = state.displacement_si.tobytes()
    first = build_phase0_ai_proposal(
        plan, state, projection, [0.2, -0.1], 1.0
    )
    second = build_phase0_ai_proposal(
        plan, state, projection, [0.2, -0.1], 1.0
    )

    assert first.proposal_id == second.proposal_id
    assert first.proposal_hash == second.proposal_hash
    assert first.to_dict() == second.to_dict()
    np.testing.assert_array_equal(first.correction_scaled, second.correction_scaled)
    np.testing.assert_array_equal(first.correction_free, second.correction_free)
    assert state.state_hash == before_hash
    assert state.displacement_si.tobytes() == before_displacement
    assert first._base_state is state


def test_ai_proposal_accepts_boundary_trust_radius_and_rejects_excess() -> None:
    plan = _plan()
    state = create_initial_state(plan)
    projection = _projection(plan)
    boundary = build_phase0_ai_proposal(
        plan, state, projection, [0.3, 0.4], 0.5
    )
    assert boundary.coefficient_l2_norm == pytest.approx(0.5)
    assert boundary.correction_scaled_l2_norm == pytest.approx(0.5)

    with pytest.raises(AICorrectionProposalError) as error:
        build_phase0_ai_proposal(
            plan, state, projection, [0.6, 0.0], 0.5
        )
    assert error.value.code == "ai_proposal_trust_radius_exceeded"


@pytest.mark.parametrize("trust_radius", [0.0, -1.0, np.nan, np.inf, True])
def test_ai_proposal_rejects_invalid_trust_radius(trust_radius: object) -> None:
    plan = _plan()
    state = create_initial_state(plan)
    projection = _projection(plan)

    with pytest.raises(AICorrectionProposalError) as error:
        build_phase0_ai_proposal(
            plan,
            state,
            projection,
            [0.1, 0.0],
            trust_radius,  # type: ignore[arg-type]
        )
    assert error.value.code == "ai_proposal_trust_radius_invalid"


@pytest.mark.parametrize(
    "coefficients",
    [
        [0.1],
        [0.1, 0.2, 0.3],
        [0.1, np.nan],
        [0.1, np.inf],
        [0.1 + 1.0j, 0.2],
        [True, False],
    ],
)
def test_ai_proposal_rejects_invalid_coefficients(coefficients: object) -> None:
    plan = _plan()
    state = create_initial_state(plan)
    projection = _projection(plan)

    with pytest.raises(AICorrectionProposalError):
        build_phase0_ai_proposal(
            plan, state, projection, coefficients, 10.0
        )


def test_ai_proposal_rejects_trial_as_accepted_base_state() -> None:
    plan = _plan()
    state = create_initial_state(plan)
    trial = open_trial_state(
        state,
        np.zeros(plan.dof_count),
        expected_plan=plan,
    )
    projection = _projection(plan)

    with pytest.raises(AICorrectionProposalError) as error:
        build_phase0_ai_proposal(plan, trial, projection, [0.1, 0.0], 1.0)
    assert error.value.code == "ai_proposal_base_state_not_committed"


def test_ai_proposal_rejects_external_plan_state_and_projection_mismatch() -> None:
    plan, state, projection, proposal = _proposal()
    other_plan = _plan("LC_STRONG")
    other_state = create_initial_state(other_plan)
    other_projection = _projection(other_plan)

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(proposal, expected_plan=other_plan)
    assert error.value.code == "ai_proposal_expected_plan_mismatch"

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(
            proposal,
            expected_plan=plan,
            expected_accepted_state=other_state,
        )
    assert error.value.code == "ai_proposal_expected_state_invalid"

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(
            proposal,
            expected_plan=plan,
            expected_accepted_state=state,
            expected_projection=other_projection,
        )
    assert error.value.code == "ai_proposal_expected_projection_invalid"


def test_ai_proposal_rejects_stale_descriptor_after_array_tamper() -> None:
    _, _, _, proposal = _proposal()
    forged_value = proposal.correction_free.copy()
    forged_value[-1] += 1.0
    forged = replace(
        proposal,
        correction_free=immutable_array(forged_value, dtype="<f8"),
    )

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_array_descriptor_mismatch"


def test_ai_proposal_rejects_rehashed_semantic_correction_tamper() -> None:
    _, _, _, proposal = _proposal()
    forged_value = proposal.correction_free.copy()
    forged_value[0] += 1.0e-4
    immutable_value = immutable_array(forged_value, dtype="<f8")
    provisional = replace(
        proposal,
        correction_free=immutable_value,
        descriptors=_refresh_descriptor(
            proposal, "correction_free", immutable_value
        ),
    )
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_free_correction_mismatch"


def test_ai_proposal_rejects_rehashed_coefficient_tamper() -> None:
    _, _, _, proposal = _proposal()
    coefficients = proposal.coefficients_y.copy()
    coefficients[0] += 0.01
    immutable_coefficients = immutable_array(coefficients, dtype="<f8")
    provisional = replace(
        proposal,
        coefficients_y=immutable_coefficients,
        descriptors=_refresh_descriptor(
            proposal, "coefficients_y", immutable_coefficients
        ),
    )
    provisional = replace(
        provisional,
        proposal_id=_deterministic_proposal_id(
            execution_plan_hash=provisional.execution_plan_hash,
            base_state_hash=provisional.base_state_hash,
            projection_hash=provisional.projection_hash,
            coefficients_descriptor=provisional.descriptors[0],
            trust_radius=provisional.trust_radius,
        ),
    )
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_scaled_correction_mismatch"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("final_result", True),
        ("direct_state_commit", True),
        ("promotion_authorized", True),
        ("overlay_only", False),
        ("dense_projector", True),
        ("statistical_calibration", True),
        ("ood_status", "in_distribution"),
        ("full_residual_replay_required", False),
        ("energy_replay_required", False),
        ("boundary_condition_replay_required", False),
        ("constitutive_replay_required", False),
    ],
)
def test_ai_proposal_rejects_authority_and_replay_tamper(
    field: str, value: object
) -> None:
    _, _, _, proposal = _proposal()
    provisional = replace(proposal, **{field: value})
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))

    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_authority_invariant_violated"


def test_ai_proposal_rejects_rehashed_binding_and_trust_receipt_tamper() -> None:
    _, _, _, proposal = _proposal()
    provisional = replace(
        proposal,
        pattern_hash="sha256:" + ("1" * 64),
    )
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))
    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_binding_mismatch"

    provisional = replace(
        proposal,
        correction_scaled_l2_norm=proposal.correction_scaled_l2_norm + 1.0e-6,
    )
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))
    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_trust_receipt_mismatch"


def test_ai_proposal_rejects_rehashed_id_and_mutable_descriptor_tamper() -> None:
    _, _, _, proposal = _proposal()
    provisional = replace(proposal, proposal_id="AIProposal:forged")
    forged = replace(provisional, proposal_hash=_proposal_hash(provisional))
    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged)
    assert error.value.code == "ai_proposal_id_mismatch"

    forged_descriptors = replace(
        proposal,
        descriptors=list(proposal.descriptors),  # type: ignore[arg-type]
    )
    with pytest.raises(AICorrectionProposalError) as error:
        validate_phase0_ai_proposal(forged_descriptors)
    assert error.value.code == "ai_proposal_descriptor_set_invalid"


def test_ai_proposal_requires_all_physics_replay_before_future_promotion() -> None:
    _, _, _, proposal = _proposal()
    replay = proposal.to_dict()["required_replay"]

    assert replay == {
        "full_residual": True,
        "energy": True,
        "boundary_conditions": True,
        "constitutive_admissibility": True,
        "required_before_promotion": True,
    }
    assert proposal.final_result is False
    assert proposal.direct_state_commit is False
    assert proposal.promotion_authorized is False
    assert proposal.acceptance_eligible is False


def test_ai_proposal_module_has_no_ml_framework_or_legacy_imports() -> None:
    source = PROPOSAL_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert not imported_roots.intersection(
        {"torch", "jax", "tensorflow", "autograd"}
    )
    assert "implementation.phase1" not in source
    assert "structural_analysis.ai" not in source
