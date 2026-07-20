from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts.nonlinear_recovery import (
    NonlinearRecoveryError,
    create_nonlinear_recovery_candidate,
    validate_nonlinear_recovery_candidate,
)
from tests.test_engine_v2_nonlinear_result_recovery_v1 import _hash, _result


def _forces():
    external = np.zeros(12, dtype="<f8")
    external[6] = 10.0
    external[11] = 4.0
    internal = external.copy()
    internal[0] = -10.0
    internal[5] = -4.0
    return external, internal


def _candidate(*, split: bool = False):
    result = _result()
    external, internal = _forces()
    base_dofs = np.arange(12, dtype="<i8")
    if split:
        dofs = np.vstack((base_dofs, base_dofs))
        element_force = np.vstack((0.25 * internal, 0.75 * internal)).astype("<f8")
        member_force = np.asarray([-2.5, -7.5], dtype="<f8")
        recovery_id = "recovery.split"
    else:
        dofs = base_dofs.reshape(1, 12)
        element_force = internal.reshape(1, 12)
        member_force = np.asarray([-10.0], dtype="<f8")
        recovery_id = "recovery.single"
    return create_nonlinear_recovery_candidate(
        recovery_id=recovery_id,
        nonlinear_result=result,
        global_external_force_si=external,
        global_internal_force_si=internal,
        element_global_dofs=dofs,
        element_internal_force_si=element_force,
        member_axial_force_si=member_force,
        recovery_law_receipt_hash=_hash("b"),
    )


def test_manifest_binds_external_internal_and_element_source_arrays() -> None:
    candidate = _candidate()
    manifest = candidate.to_manifest()

    assert [row["name"] for row in manifest["source_descriptors"]] == [
        "element_global_dofs",
        "element_internal_force_si",
    ]
    assert [row["name"] for row in manifest["descriptors"]] == [
        "global_external_force_si",
        "global_internal_force_si",
        "reaction_global_si",
        "equilibrium_residual_global_si",
        "member_axial_force_si",
    ]
    assert manifest["claim_boundary"]["element_global_dof_bytes_bound"] is True
    assert manifest["claim_boundary"]["element_internal_force_bytes_bound"] is True
    assert manifest["claim_boundary"]["global_external_force_bytes_bound"] is True
    assert candidate.source_array("element_global_dofs").flags.writeable is False
    assert candidate.source_array("element_internal_force_si").flags.writeable is False
    assert candidate.vector("global_external_force_si").flags.writeable is False


def test_different_element_distribution_has_different_canonical_recovery_hash() -> None:
    single = _candidate(split=False)
    split = _candidate(split=True)

    np.testing.assert_array_equal(
        single.vector("global_internal_force_si"),
        split.vector("global_internal_force_si"),
    )
    np.testing.assert_array_equal(single.reaction_global_si, split.reaction_global_si)
    assert single.recovery_hash != split.recovery_hash
    assert single.source_descriptors != split.source_descriptors
    assert single.element_count == 1
    assert split.element_count == 2


def test_retained_element_dof_or_force_tamper_fails_descriptor_validation() -> None:
    candidate = _candidate()
    changed_dofs = candidate.source_array("element_global_dofs").copy()
    changed_dofs[0, 0], changed_dofs[0, 1] = changed_dofs[0, 1], changed_dofs[0, 0]
    changed_dofs.setflags(write=False)
    tampered_dofs = replace(
        candidate,
        _source_arrays=MappingProxyType(
            {
                "element_global_dofs": changed_dofs,
                "element_internal_force_si": candidate.source_array(
                    "element_internal_force_si"
                ),
            }
        ),
    )
    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_source_descriptor_mismatch",
    ):
        validate_nonlinear_recovery_candidate(tampered_dofs)

    changed_force = candidate.source_array("element_internal_force_si").copy()
    changed_force[0, 0] += 1.0
    changed_force.setflags(write=False)
    tampered_force = replace(
        candidate,
        _source_arrays=MappingProxyType(
            {
                "element_global_dofs": candidate.source_array(
                    "element_global_dofs"
                ),
                "element_internal_force_si": changed_force,
            }
        ),
    )
    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_source_descriptor_mismatch",
    ):
        validate_nonlinear_recovery_candidate(tampered_force)


def test_external_force_tamper_fails_vector_descriptor_validation() -> None:
    candidate = _candidate()
    changed_external = candidate.vector("global_external_force_si").copy()
    changed_external[6] += 1.0
    changed_external.setflags(write=False)
    tampered = replace(
        candidate,
        _vectors=MappingProxyType(
            {
                "global_external_force_si": changed_external,
                "global_internal_force_si": candidate.vector(
                    "global_internal_force_si"
                ),
                "reaction_global_si": candidate.reaction_global_si,
                "equilibrium_residual_global_si": (
                    candidate.equilibrium_residual_global_si
                ),
                "member_axial_force_si": candidate.member_axial_force_si,
            }
        ),
    )
    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_descriptor_mismatch",
    ):
        validate_nonlinear_recovery_candidate(tampered)
