from pathlib import Path
import pytest
from scripts.nonpromotion_authority_policy import (
    load_authority_policy,
    promoted_authority_violations,
)

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = (
    "same_operator_execution_binding",
    "stored_same_operator_execution_binding",
    "same_operator_supplemental_execution_binding",
    "stored_same_operator_supplemental_execution_binding",
)


def check(payload):
    return promoted_authority_violations(
        payload,
        load_authority_policy(
            ROOT / "canonical/nonpromotion-authority-key-policy.v1.json"
        ),
    )


@pytest.mark.parametrize("binding", BINDINGS)
def test_execution_fact_at_product_state_binding_is_nonpromoting(binding):
    payload = {
        "bounded_planar_external_vv": {
            binding: {
                "actual_external_solver_execution": True,
                "independent_operator_attested": False,
                "product_legal_license_approval": False,
                "verification_level_2": False,
            }
        }
    }
    assert check(payload) == []


@pytest.mark.parametrize("binding", BINDINGS)
@pytest.mark.parametrize(
    "claim",
    [
        "independent_operator_attested",
        "product_legal_license_approval",
        "verification_level_2",
        "release_authority",
        "recommended_matrix_technical_coverage_complete",
    ],
)
def test_execution_fact_cannot_promote_other_authority(binding, claim):
    assert check(
        {
            "bounded_planar_external_vv": {
                binding: {"actual_external_solver_execution": True, claim: True}
            }
        }
    )


@pytest.mark.parametrize("binding", BINDINGS)
@pytest.mark.parametrize("payload_kind", ["root", "unknown_child", "nested", "license"])
def test_known_execution_fact_does_not_allow_transplanted_path(binding, payload_kind):
    fact = {"actual_external_solver_execution": True}
    payloads = {
        "root": {binding: fact},
        "unknown_child": {"bounded_planar_external_vv": {"unknown_binding": fact}},
        "nested": {"bounded_planar_external_vv": {binding: {"nested": fact}}},
        "license": {
            "authority_tracks": {"internal_license_due_diligence": {"claims": fact}}
        },
    }
    assert check(payloads[payload_kind])


@pytest.mark.parametrize("binding", BINDINGS)
@pytest.mark.parametrize(
    "key",
    [
        "actualExternalSolverExecution",
        "Actual_External_Solver_Execution",
        "actual-external-solver-execution",
    ],
)
def test_execution_fact_alias_is_rejected(binding, key):
    assert check({"bounded_planar_external_vv": {binding: {key: True}}})
