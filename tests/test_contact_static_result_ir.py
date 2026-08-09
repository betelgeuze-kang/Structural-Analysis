from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts.contact_static_result import (
    ContactResultIRError, create_contact_result_ir, validate_contact_result_ir,
)
from structural_analysis.solvers.nonlinear.contact_static import ContactStaticModel, solve_contact_static


def _result():
    model = ContactStaticModel(model_id="contact", dof_ids=("N1.UX", "N2.UX"), contact_ids=("C1", "C2"), stiffness_n_per_m=((1000.0, -200.0), (-200.0, 800.0)), load_n=(150.0, 60.0), gap_upper_m=(0.08, 0.2))
    solved = solve_contact_static(model)
    return create_contact_result_ir(
        result_id="f3.contact", model_ir_content_hash="sha256:" + "1" * 64,
        solver_result_hash=solved.result_hash, stiffness_hash=solved.stiffness_hash,
        load_hash=solved.load_hash, terminal_checkpoint_hash=solved.checkpoint.checkpoint_hash,
        solver_id="active-set.contact.v1", dof_ids=model.dof_ids, contact_ids=model.contact_ids,
        displacement_m=solved.displacement_m, contact_multiplier_n=solved.contact_multiplier_n,
        gap_remaining_m=solved.gap_remaining_m, equilibrium_residual_n=solved.equilibrium_residual_n,
        complementarity_n_m=solved.complementarity_n_m, active_contact_ids=solved.active_contact_ids,
        maximum_equilibrium_residual_n=solved.maximum_equilibrium_residual_n,
        maximum_penetration_m=solved.maximum_penetration_m,
        minimum_contact_multiplier_n=solved.minimum_contact_multiplier_n,
        maximum_complementarity_n_m=solved.maximum_complementarity_n_m,
    )


def test_contact_result_ir_is_authoritative_and_hash_bound() -> None:
    result = _result()
    assert validate_contact_result_ir(result) == result
    assert result.to_manifest()["authority"]["kkt_metrics"] == "authoritative"


def test_contact_result_ir_rejects_tamper() -> None:
    result = _result()
    with pytest.raises(ContactResultIRError, match="result_hash_mismatch"):
        validate_contact_result_ir(replace(result, maximum_penetration_m=1.0))
