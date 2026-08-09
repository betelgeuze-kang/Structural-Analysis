from dataclasses import replace

import pytest

from structural_analysis.solvers.nonlinear.contact_static import (
    ContactStaticError, ContactStaticModel, resume_contact_static, solve_contact_static,
)


def _model(load=(150.0, 60.0)) -> ContactStaticModel:
    return ContactStaticModel(
        model_id="two-gap-contact", dof_ids=("N1.UX", "N2.UX"), contact_ids=("C1", "C2"),
        stiffness_n_per_m=((1000.0, -200.0), (-200.0, 800.0)), load_n=load,
        gap_upper_m=(0.08, 0.20),
    )


def test_contact_active_set_closes_kkt_without_fallback() -> None:
    result = solve_contact_static(_model())
    assert result.active_contact_ids == ("C1",)
    assert result.displacement_m == pytest.approx((0.08, 0.095), abs=1.0e-14)
    assert result.contact_multiplier_n == pytest.approx((89.0, 0.0), abs=1.0e-12)
    assert result.maximum_equilibrium_residual_n <= 1.0e-12
    assert result.maximum_penetration_m == 0.0
    assert result.minimum_contact_multiplier_n >= 0.0
    assert result.maximum_complementarity_n_m <= 1.0e-14
    assert result.active_set_trials == 4
    assert not result.fallback_used and not result.regularization_used and result.contract_pass


@pytest.mark.parametrize(
    ("load", "active"),
    [((10.0, 20.0), ()), ((-10.0, 200.0), ("C2",)), ((200.0, 250.0), ("C1", "C2"))],
)
def test_contact_active_set_breadth(load, active) -> None:
    assert solve_contact_static(_model(load)).active_contact_ids == active


def test_contact_exact_restart_and_tamper_rejection() -> None:
    model = _model(); solved = solve_contact_static(model)
    assert resume_contact_static(model, solved.checkpoint) == solved
    with pytest.raises(ContactStaticError, match="hash mismatch"):
        resume_contact_static(model, replace(solved.checkpoint, active_contact_ids=("C2",)))
