from __future__ import annotations

import copy
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.diagnostic_ir_v1 import (  # noqa: E402
    DiagnosticIRV1,
    DiagnosticIRV1Counters,
    DiagnosticIRV1Error,
    DiagnosticIRV1Metrics,
    DiagnosticIRV1Policy,
    DiagnosticIRV1RestartRecord,
    DiagnosticIRV1Termination,
    DiagnosticSourceProvenanceV1,
    _linf,
    _numerical_hash_from_manifest,
    _issue_bridge_diagnostic_ir_v1_ready,
    _receipt_hash,
    _stable_l2,
    build_diagnostic_ir_v1,
    validate_diagnostic_ir_v1,
    validate_diagnostic_ir_v1_manifest,
    validate_diagnostic_ir_v1_physics,
)
from structural_analysis.engine_v2.contracts import (  # noqa: E402
    diagnostic_ir_v1 as diagnostic_ir_module,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def sources():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    model = parse_model_ir_v2(payload)
    plan = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_WEAK")
    )
    policy = compile_fgmres_policy_v1(
        restart_dimension=1,
        max_iterations=2,
        absolute_tolerance=0.0,
        relative_tolerance=1.0e-14,
    )
    result = solve_cpu_fgmres_reference_v1(plan, policy)
    assert result.status == "max_iterations"
    assert result.termination_code == "max_iterations_exhausted"
    assert result.solver_tolerance_passed is False
    assert result.authoritative_plan_tolerance_passed is False
    accepted = create_initial_state(plan)
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[plan.array("free_dofs")] = result.reduced_solution
    trial = open_trial_state(
        accepted,
        displacement,
        iteration=result.iteration_count,
        expected_plan=plan,
    )
    return plan, result, accepted, trial, displacement


def _termination(plan, result, displacement) -> DiagnosticIRV1Termination:
    residual = np.asarray(plan.residual(displacement), dtype="<f8")
    free_residual = residual[plan.array("free_dofs")]
    exported = result.true_residual
    rhs = plan.array("global_load")[plan.array("free_dofs")]
    load_scale = max(1.0, _linf(rhs))
    return DiagnosticIRV1Termination(
        policy=DiagnosticIRV1Policy(
            restart_dimension=result.policy.restart_dimension,
            max_iterations=result.policy.max_iterations,
            absolute_tolerance=result.policy.absolute_tolerance,
            relative_tolerance=result.policy.relative_tolerance,
            stagnation_checkpoint_limit=(result.policy.stagnation_checkpoint_limit),
            stagnation_relative_tolerance=(result.policy.stagnation_relative_tolerance),
            divergence_factor=result.policy.divergence_factor,
            policy_hash=result.policy.policy_hash,
        ),
        counters=DiagnosticIRV1Counters(
            iteration_count=result.iteration_count,
            restart_count=result.restart_count,
            operator_apply_count=result.operator_apply_count,
            preconditioner_apply_count=result.preconditioner_apply_count,
        ),
        metrics=DiagnosticIRV1Metrics(
            initial_residual_l2=result.initial_residual_l2,
            solver_tolerance_l2=result.solver_tolerance_l2,
            final_residual_l2=result.final_residual_l2,
            final_residual_linf=result.final_residual_linf,
            scaled_true_residual=result.scaled_true_residual,
            load_scale=load_scale,
            free_residual_l2=_stable_l2(free_residual),
            free_residual_linf=_linf(free_residual),
            scaled_free_residual=_linf(free_residual) / load_scale,
            exported_free_residual_l2=_stable_l2(exported),
            exported_free_residual_linf=_linf(exported),
            scaled_exported_free_residual=_linf(exported) / load_scale,
        ),
        history=tuple(
            DiagnosticIRV1RestartRecord(
                **{
                    name: getattr(row, name)
                    for name in DiagnosticIRV1RestartRecord.__dataclass_fields__
                }
            )
            for row in result.history
        ),
    )


def _provenance(result) -> DiagnosticSourceProvenanceV1:
    return DiagnosticSourceProvenanceV1(
        case_id="frame_single_weak",
        case_parity_receipt_hash=_hash("case-parity"),
        terminal_observation_receipt_hash=_hash("observation-receipt"),
        completion_export_receipt_hash=_hash("export-receipt"),
        completion_export_payload_hash=_hash("export-payload"),
        device_identity_receipt_hash=_hash("device-identity"),
        source_schema_version="structural-analysis-hip-fgmres-model-case-parity.v1",
        cpu_result_hash=result.result_hash,
        terminal_outcome_hash=_hash("terminal-outcome"),
        terminal_observation_id=_hash("observation-id"),
        completion_export_context_id=_hash("export-context-id"),
        source_binding_hash=_hash("source-binding"),
        actual_backend="hip",
        solution_payload_sha256=array_data_hash(result.reduced_solution),
        exported_free_residual_payload_sha256=array_data_hash(result.true_residual),
        solve_record_payload_sha256=_hash("solve-record"),
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex="0123456789abcdef0123456789abcdef",
        device_pci_bdf="0000:03:00.0",
    )


def _receipt(sources) -> DiagnosticIRV1:
    plan, result, accepted, trial, displacement = sources
    return build_diagnostic_ir_v1(
        plan,
        accepted,
        trial,
        displacement,
        result.true_residual,
        _termination(plan, result, displacement),
        _provenance(result),
    )


def _rehash(receipt: DiagnosticIRV1, **changes) -> DiagnosticIRV1:
    draft = replace(receipt, **changes)
    return replace(draft, diagnostic_ir_hash=_receipt_hash(draft.to_dict()))


def test_build_preserves_three_arrays_history_and_explicit_no_commit(sources) -> None:
    plan, result, accepted, trial, displacement = sources
    receipt = _receipt(sources)

    assert validate_diagnostic_ir_v1(receipt) is receipt
    assert (
        validate_diagnostic_ir_v1_physics(
            receipt,
            expected_plan=plan,
            expected_accepted_state=accepted,
            expected_evaluated_trial_state=trial,
        )
        is receipt
    )
    assert np.array_equal(
        receipt.arrays.partial_displacement_si.values.reshape(-1), displacement
    )
    assert np.array_equal(
        receipt.arrays.residual_si.values.reshape(-1), plan.residual(displacement)
    )
    assert np.array_equal(
        receipt.arrays.exported_free_residual_si.values, result.true_residual
    )
    assert receipt.termination.counters.iteration_count == 2
    assert len(receipt.termination.history) == 2
    assert receipt.input_bindings.committed_state_hash is None
    assert receipt.claims.diagnostic_ready is False
    assert receipt.claims.partial_iterate_preserved is False
    assert receipt.claims.nonconverged_max_iterations_verified is False
    assert receipt.claims.restart_history_preserved is False
    assert receipt.claims.diagnostic_ir_verified is True
    assert receipt.claims.evaluated_trial_state_verified is True
    assert receipt.claims.true_residual_replayed is True
    assert receipt.claims.rollback_to_accepted_state_verified is True
    assert receipt.claims.solution_ready is False
    assert receipt.claims.result_ir_ready is False
    assert receipt.claims.reaction_recovery_verified is False
    assert receipt.claims.member_force_recovery_verified is False
    assert receipt.claims.energy_identities_verified is False
    assert receipt.claims.commercial_ready is False


def test_diagnostic_ready_requires_private_exact_bridge_object_identity(
    sources,
) -> None:
    plan, _, accepted, trial, _ = sources
    receipt = _receipt(sources)
    assert "_issue_bridge_diagnostic_ir_v1_ready" not in diagnostic_ir_module.__all__
    assert receipt.claims.diagnostic_ready is False
    assert validate_diagnostic_ir_v1_manifest(receipt.to_manifest()) is None

    forged_claims = replace(
        receipt.claims,
        diagnostic_ready=True,
        partial_iterate_preserved=True,
        nonconverged_max_iterations_verified=True,
        restart_history_preserved=True,
    )
    coherent_rehash = _rehash(receipt, claims=forged_claims)
    for validator in (
        lambda candidate: validate_diagnostic_ir_v1(candidate),
        lambda candidate: validate_diagnostic_ir_v1_physics(
            candidate,
            expected_plan=plan,
            expected_accepted_state=accepted,
            expected_evaluated_trial_state=trial,
        ),
    ):
        with pytest.raises(DiagnosticIRV1Error) as error:
            validator(coherent_rehash)
        assert error.value.code == "diagnostic_ir_v1_ready_authority_unavailable"

    issued = _issue_bridge_diagnostic_ir_v1_ready(receipt)
    assert issued.claims.diagnostic_ready is True
    assert issued.claims.partial_iterate_preserved is True
    assert issued.claims.nonconverged_max_iterations_verified is True
    assert issued.claims.restart_history_preserved is True
    assert validate_diagnostic_ir_v1(issued) is issued
    assert (
        validate_diagnostic_ir_v1_physics(
            issued,
            expected_plan=plan,
            expected_accepted_state=accepted,
            expected_evaluated_trial_state=trial,
        )
        is issued
    )

    direct = DiagnosticIRV1(
        **{
            name: getattr(issued, name)
            for name, dataclass_field in DiagnosticIRV1.__dataclass_fields__.items()
            if dataclass_field.init
        }
    )
    candidates = (replace(issued), copy.copy(issued), direct)
    assert all(candidate is not issued for candidate in candidates)
    for candidate in candidates:
        for validator in (
            lambda value: validate_diagnostic_ir_v1(value),
            lambda value: validate_diagnostic_ir_v1_physics(
                value,
                expected_plan=plan,
                expected_accepted_state=accepted,
                expected_evaluated_trial_state=trial,
            ),
        ):
            with pytest.raises(DiagnosticIRV1Error) as error:
                validator(candidate)
            assert error.value.code == "diagnostic_ir_v1_ready_authority_unavailable"

    try:
        deep_copied = copy.deepcopy(issued)
    except (TypeError, ValueError):
        pass
    else:
        assert deep_copied is not issued
        for validator in (
            lambda value: validate_diagnostic_ir_v1(value),
            lambda value: validate_diagnostic_ir_v1_physics(
                value,
                expected_plan=plan,
                expected_accepted_state=accepted,
                expected_evaluated_trial_state=trial,
            ),
        ):
            with pytest.raises(DiagnosticIRV1Error) as error:
                validator(deep_copied)
            assert error.value.code == "diagnostic_ir_v1_ready_authority_unavailable"

    with pytest.raises(DiagnosticIRV1Error) as manifest_error:
        validate_diagnostic_ir_v1_manifest(issued.to_manifest())
    assert manifest_error.value.code == "diagnostic_ir_v1_ready_authority_unavailable"


def test_source_tree_l2_one_ulp_roundoff_is_preserved_without_loosening_linf(
    sources,
) -> None:
    plan, result, accepted, trial, displacement = sources
    termination = _termination(plan, result, displacement)
    final = termination.history[-1]
    rounded_source_l2 = float(
        np.nextafter(termination.metrics.final_residual_l2, np.inf)
    )
    termination = replace(
        termination,
        history=(
            *termination.history[:-1],
            replace(final, true_residual_l2=rounded_source_l2),
        ),
    )

    receipt = build_diagnostic_ir_v1(
        plan,
        accepted,
        trial,
        displacement,
        result.true_residual,
        termination,
        _provenance(result),
    )
    assert receipt.termination.history[-1].true_residual_l2 == rounded_source_l2
    assert receipt.termination.metrics.final_residual_l2 != rounded_source_l2


def test_arrays_are_immutable_bytes_and_manifest_is_descriptor_only(sources) -> None:
    receipt = _receipt(sources)
    manifest = receipt.to_manifest()

    validate_diagnostic_ir_v1_manifest(manifest)
    assert manifest["state_lifecycle"]["evaluated_trial_committed"] is False
    assert manifest["state_lifecycle"]["committed_state_hash"] is None
    assert all("values" not in row for row in manifest["arrays"].values())
    for row in receipt.arrays.ordered():
        assert row.values.flags.writeable is False
        with pytest.raises(ValueError):
            row.values.setflags(write=True)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("termination", "status"), "converged"),
        (("termination", "termination_code"), "converged_true_residual"),
        (("input_bindings", "committed_state_hash"), _hash("forbidden-commit")),
        (("claims", "solution_ready"), True),
        (("source_provenance", "additional_solve_count"), 1),
    ),
)
def test_strict_manifest_rejects_promoting_or_extra_state(
    sources, path: tuple[str, str], value: object
) -> None:
    manifest = deepcopy(_receipt(sources).to_manifest())
    manifest[path[0]][path[1]] = value
    with pytest.raises(DiagnosticIRV1Error):
        validate_diagnostic_ir_v1_manifest(manifest)


def test_manifest_rejects_unknown_field_and_stale_hashes(sources) -> None:
    manifest = deepcopy(_receipt(sources).to_manifest())
    manifest["unknown"] = False
    with pytest.raises(DiagnosticIRV1Error):
        validate_diagnostic_ir_v1_manifest(manifest)

    manifest = deepcopy(_receipt(sources).to_manifest())
    manifest["arrays"]["residual_si"]["data_hash"] = _hash("tampered")
    with pytest.raises(DiagnosticIRV1Error) as caught:
        validate_diagnostic_ir_v1_manifest(manifest)
    assert caught.value.code == "diagnostic_ir_v1_numerical_hash_mismatch"


def test_manifest_rejects_coherently_rehashed_impossible_termination(sources) -> None:
    manifest = deepcopy(_receipt(sources).to_manifest())
    manifest["termination"]["metrics"]["solver_tolerance_l2"] = 0.0
    manifest["numerical_diagnostic_hash"] = _numerical_hash_from_manifest(manifest)
    manifest["diagnostic_ir_hash"] = _receipt_hash(manifest)
    with pytest.raises(DiagnosticIRV1Error) as caught:
        validate_diagnostic_ir_v1_manifest(manifest)
    assert caught.value.code == "diagnostic_ir_v1_solver_tolerance_mismatch"

    manifest = deepcopy(_receipt(sources).to_manifest())
    policy = manifest["termination"]["policy"]
    policy["restart_dimension"] = 2
    policy_payload = dict(policy)
    del policy_payload["policy_hash"]
    policy["policy_hash"] = canonical_hash(policy_payload)
    manifest["numerical_diagnostic_hash"] = _numerical_hash_from_manifest(manifest)
    manifest["diagnostic_ir_hash"] = _receipt_hash(manifest)
    with pytest.raises(DiagnosticIRV1Error) as caught:
        validate_diagnostic_ir_v1_manifest(manifest)
    assert caught.value.code == "diagnostic_ir_v1_counter_invariant_invalid"


def test_builder_rejects_wrong_residual_sign_and_noncanonical_accepted_state(
    sources,
) -> None:
    plan, result, accepted, trial, displacement = sources
    termination = _termination(plan, result, displacement)
    provenance = _provenance(result)
    with pytest.raises(DiagnosticIRV1Error) as caught:
        build_diagnostic_ir_v1(
            plan,
            accepted,
            trial,
            displacement,
            -result.true_residual,
            termination,
            provenance,
        )
    assert caught.value.code == "diagnostic_ir_v1_exported_residual_sign_mismatch"

    noncanonical = create_initial_state(plan, state_id="state.custom.initial")
    custom_trial = open_trial_state(
        noncanonical,
        displacement,
        iteration=result.iteration_count,
        expected_plan=plan,
    )
    with pytest.raises(DiagnosticIRV1Error) as caught:
        build_diagnostic_ir_v1(
            plan,
            noncanonical,
            custom_trial,
            displacement,
            result.true_residual,
            termination,
            provenance,
        )
    assert caught.value.code == (
        "diagnostic_ir_v1_accepted_state_not_canonical_initial"
    )


def test_exact_types_counters_history_and_policy_hash_fail_closed(sources) -> None:
    plan, result, accepted, trial, displacement = sources
    termination = _termination(plan, result, displacement)
    provenance = _provenance(result)
    bad_counter = replace(
        termination,
        counters=replace(termination.counters, iteration_count=1),
    )
    with pytest.raises(DiagnosticIRV1Error):
        build_diagnostic_ir_v1(
            plan,
            accepted,
            trial,
            displacement,
            result.true_residual,
            bad_counter,
            provenance,
        )
    bad_history = replace(termination, history=termination.history[:-1])
    with pytest.raises(DiagnosticIRV1Error):
        build_diagnostic_ir_v1(
            plan,
            accepted,
            trial,
            displacement,
            result.true_residual,
            bad_history,
            provenance,
        )
    bad_policy = replace(
        termination,
        policy=replace(termination.policy, policy_hash=_hash("wrong-policy")),
    )
    with pytest.raises(DiagnosticIRV1Error):
        build_diagnostic_ir_v1(
            plan,
            accepted,
            trial,
            displacement,
            result.true_residual,
            bad_policy,
            provenance,
        )

    class StringAlias(str):
        pass

    bad_source_kind = replace(
        provenance,
        source_kind=StringAlias("fgmres_partial_iterate"),
    )
    with pytest.raises(DiagnosticIRV1Error) as source_kind_error:
        build_diagnostic_ir_v1(
            plan,
            accepted,
            trial,
            displacement,
            result.true_residual,
            termination,
            bad_source_kind,
        )
    assert source_kind_error.value.code == "diagnostic_ir_v1_source_kind_invalid"

    class DiagnosticAlias(DiagnosticIRV1):
        pass

    alias = DiagnosticAlias(
        **{
            name: getattr(_receipt(sources), name)
            for name, dataclass_field in DiagnosticIRV1.__dataclass_fields__.items()
            if dataclass_field.init
        }
    )
    with pytest.raises(DiagnosticIRV1Error) as caught:
        validate_diagnostic_ir_v1(alias)
    assert caught.value.code == "diagnostic_ir_v1_type_invalid"
