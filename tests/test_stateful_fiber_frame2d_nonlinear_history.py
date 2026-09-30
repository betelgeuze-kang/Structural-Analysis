"""Committed-epoch recovery binds exact source history and original coordinates."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_history as history_module,
    stateful_fiber_frame2d_nonlinear_recovery as recovery_module,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    physical_3dof_to_canonical_6dof,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.fixture(scope="module")
def recovered_history():
    """One two-step public solve is shared by all physical and tamper assertions."""
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    model.sections[0]["width_m"] = 0.401
    model.loads[0]["components"]["FY"] = -1.0
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    compiled, unsupported, _ = public_api._compile(model)
    assert compiled is not None and unsupported == []
    execution = public_api._run_load_path(
        compiled, config, restart_checkpoint_chain=None
    )
    assert execution.path.contract_pass is True
    authority = public_api._create_authority_artifacts(
        model, compiled, execution, config
    )
    validate = history_module.validate_fiber_frame_nonlinear_numerical_result_adapter
    assemble = recovery_module.assemble_stateful_fiber_frame2d
    validation_inputs = []
    replay_inputs = []

    def counted_validation(adapter):
        validation_inputs.append(adapter)
        return validate(adapter)

    def recorded_assembly(problem, parent, **kwargs):
        replay_inputs.append((parent, kwargs))
        return assemble(problem, parent, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            history_module,
            "validate_fiber_frame_nonlinear_numerical_result_adapter",
            counted_validation,
        )
        patch.setattr(
            recovery_module, "assemble_stateful_fiber_frame2d", recorded_assembly
        )
        history = history_module.create_fiber_frame_nonlinear_engineering_history(
            authority.adapter
        )
    return {
        "compiled": compiled,
        "execution": execution,
        "adapter": authority.adapter,
        "operator": authority.engineering_result._recovery_operator,
        "history": history,
        "validation_inputs": validation_inputs,
        "replay_inputs": replay_inputs,
    }


def test_history_has_complete_source_and_per_epoch_bindings(recovered_history):
    adapter = recovered_history["adapter"]
    source = adapter.source_binding
    history = recovered_history["history"]
    payload = history.to_dict()
    assert payload["schema_version"] == (
        "stateful-fiber-frame2d-nonlinear-engineering-history.v1"
    )
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["history_hash"] == history.history_hash
    assert payload["history_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "history_hash"}
    )
    assert payload["epoch_count"] == 2
    assert payload["terminal_epoch"] == source.terminal_epoch == 2
    assert payload["terminal_load_factor"] == source.terminal_load_factor == 1.0
    assert payload["scope"] == {
        "committed_epochs_only": True,
        "genesis_included": False,
        "genesis_exclusion_reason": (
            "zero_unforced_initial_state_has_no_accepted_transition"
        ),
        "complete_monotonic_static_load_path": True,
        "between_step_extrema_verified": False,
        "cyclic_or_dynamic_history_verified": False,
        "constitutive_law_independently_verified": False,
        "engineering_design_verified": False,
        "code_compliance_verified": False,
        "production_promotion_eligible": False,
    }
    bindings = payload["bindings"]
    assert bindings["source_result_adapter_hash"] == adapter.adapter_hash
    assert bindings["source_binding_hash"] == source.binding_hash
    assert bindings["source_numerical_result_hash"] == (
        adapter.numerical_result.result_hash
    )
    for name in (
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_hash",
        "physical_equation_scaling_binding_hash",
        "execution_state_binding_hash",
        "checkpoint_chain_hash",
        "kinematic_state_chain_hash",
        "material_state_projection_chain_hash",
        "terminal_receipt_hash",
        "path_history_hash",
        "terminal_checkpoint_state_hash",
    ):
        assert bindings[name] == getattr(source, name)
    assert bindings["root_checkpoint_state_hash"] == (
        source._checkpoint_chain.root_checkpoint.state_hash
    )
    assert payload["source_terminal_receipt"] == source._terminal_receipt.to_manifest()
    assert [row["epoch"] for row in payload["steps"]] == [1, 2]
    assert [row["target_load_factor"] for row in payload["steps"]] == [0.5, 1.0]
    for epoch, row in enumerate(payload["steps"], start=1):
        checkpoint = source._checkpoint_chain.checkpoints[epoch]
        kinematic = source._kinematic_chain.committed_states[epoch]
        material = source._material_chain.projections[epoch]
        execution = source._execution_state_binding.epoch_bindings[epoch]
        receipt = source._terminal_receipt.step_receipts[epoch - 1]
        assert row["step_index"] == checkpoint.step_index
        assert row["bindings"] == {
            "checkpoint_state_hash": checkpoint.state_hash,
            "parent_checkpoint_state_hash": checkpoint.parent_state_hash,
            "kinematic_state_hash": kinematic.state_hash,
            "material_projection_receipt_hash": material.receipt.receipt_hash,
            "material_state_bundle_hash": material.bundle.bundle_hash,
            "execution_epoch_binding_hash": execution.epoch_binding_hash,
            "step_receipt_hash": receipt.step_receipt_hash,
            "source_solution_data_hash": receipt.source_solution_data_hash,
        }
        assert row["recovery_hash"] == canonical_hash(
            {key: value for key, value in row.items() if key != "recovery_hash"}
        )
        assert row["metrics"]["state_bytes_exact"] is True
        np.testing.assert_array_equal(
            row["displacement_canonical_si"],
            kinematic.array("canonical_displacement_si"),
        )
        assert row["displacement_array_descriptor"] == next(
            descriptor.to_dict()
            for descriptor in kinematic.descriptors
            if descriptor.name == "canonical_displacement_si"
        )


def test_terminal_history_preserves_existing_recovery_arrays_and_hashes(
    recovered_history,
):
    operator = recovered_history["operator"]
    terminal = recovered_history["history"].to_dict()["steps"][-1]
    assert terminal["array_bundle_hash"] == operator.array_bundle_hash
    assert terminal["recovery_array_descriptors"] == [
        descriptor.to_dict() for descriptor in operator.descriptors
    ]
    assert set(terminal["recovery_arrays"]) == {
        descriptor.name for descriptor in operator.descriptors
    }
    for descriptor in operator.descriptors:
        np.testing.assert_array_equal(
            terminal["recovery_arrays"][descriptor.name],
            operator.array(descriptor.name),
        )
    for name, value in terminal["orders"].items():
        assert value == getattr(operator, name)
    for name, value in terminal["metrics"].items():
        assert value == getattr(operator, name)


def test_each_epoch_recovers_its_own_physical_and_fiber_response(recovered_history):
    source = recovered_history["adapter"].source_binding
    rows = recovered_history["history"].to_dict()["steps"]
    for step, row in zip(source._load_path.steps, rows, strict=True):
        displacement = physical_3dof_to_canonical_6dof(
            source._topology_plan, step.accepted_checkpoint.global_displacements
        ).reshape((-1, 6))
        assert [node["node_id"] for node in row["node_displacements"]] == list(
            source._topology_plan.node_ids
        )
        np.testing.assert_array_equal(
            [
                [
                    node[key]
                    for key in ("UX_m", "UY_m", "UZ_m", "RX_rad", "RY_rad", "RZ_rad")
                ]
                for node in row["node_displacements"]
            ],
            displacement,
        )
        expected_fibers = [
            (member.member_id, ip_index, fiber_index, fiber.fiber_id, strain, stress)
            for member, assembly in zip(
                source._problem.members,
                step.trial_assembly.member_assemblies,
                strict=True,
            )
            for ip_index, section in enumerate(assembly.response.section_responses)
            for fiber_index, (fiber, strain, stress) in enumerate(
                zip(
                    member.element.section.fibers,
                    section.fiber_strains,
                    section.fiber_stresses_mpa,
                    strict=True,
                )
            )
        ]
        assert [
            (
                fiber["member_id"],
                fiber["integration_point_index"],
                fiber["fiber_index"],
                fiber["fiber_id"],
                fiber["strain"],
                fiber["stress_MPa"],
            )
            for fiber in row["fiber_results"]
        ] == expected_fibers
    assert rows[0]["node_displacements"] != rows[1]["node_displacements"]
    assert (
        rows[0]["recovery_arrays"]["fiber_strain"]
        != (rows[1]["recovery_arrays"]["fiber_strain"])
    )
    assert rows[0]["array_bundle_hash"] != rows[1]["array_bundle_hash"]


def test_envelope_matches_all_committed_epoch_rows_and_governing_entities(
    recovered_history,
):
    payload = recovered_history["history"].to_dict()
    translations = [
        (
            math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"]),
            step["epoch"],
            node,
        )
        for step in payload["steps"]
        for node in step["node_displacements"]
    ]
    strains = [
        (abs(fiber["strain"]), step["epoch"], fiber)
        for step in payload["steps"]
        for fiber in step["fiber_results"]
    ]
    maximum_translation, translation_epoch, node = max(
        translations, key=lambda item: item[0]
    )
    maximum_strain, strain_epoch, fiber = max(strains, key=lambda item: item[0])
    envelope = payload["envelope"]
    assert envelope["maximum_translation_m"] == pytest.approx(
        maximum_translation, rel=1e-15, abs=0.0
    )
    assert envelope["maximum_absolute_fiber_strain"] == maximum_strain
    assert envelope["governing_translation"]["epoch"] == translation_epoch
    assert envelope["governing_translation"]["node_id"] == node["node_id"]
    assert envelope["governing_fiber_strain"]["epoch"] == strain_epoch
    for name in ("member_id", "integration_point_index", "fiber_index", "fiber_id"):
        assert envelope["governing_fiber_strain"][name] == fiber[name]
    for step in payload["steps"]:
        assert step["envelope"]["maximum_translation_m"] == max(
            value for value, epoch, _ in translations if epoch == step["epoch"]
        )
        assert step["envelope"]["maximum_absolute_fiber_strain"] == max(
            value for value, epoch, _ in strains if epoch == step["epoch"]
        )


def test_create_validates_complete_source_once_and_replays_original_coordinates(
    recovered_history,
):
    adapter = recovered_history["adapter"]
    source = adapter.source_binding
    assert recovered_history["validation_inputs"] == [adapter]
    inputs = recovered_history["replay_inputs"]
    assert len(inputs) == len(source._load_path.steps) == 2
    assert source._problem.rotation_coordinate_scale_m != 1.0
    # An independent IEEE witness explains why inverse scaling is not exact.
    # It is not asserted to be a displacement from this physical fixture.
    witness = np.float64(float.fromhex("-0x1.7769c79c3070ep-16"))
    roundtrip = (witness * np.float64(3.0)) * np.float64(1.0 / 3.0)
    assert abs(witness - roundtrip) == abs(np.spacing(witness))
    for epoch, ((parent, kwargs), step) in enumerate(
        zip(inputs, source._load_path.steps, strict=True)
    ):
        assert parent is source._checkpoint_chain.checkpoints[epoch]
        assert kwargs["target_load_factor"] == step.accepted_checkpoint.load_factor
        assert kwargs["trial_free_coordinates_m"] is (
            step.trial_solution.free_displacements_m
        )
        physical = np.asarray(step.accepted_checkpoint.global_displacements)
        assert np.any(physical[2::3] != 0.0)


def test_early_peak_reducer_uses_all_epochs_with_contract_only_inputs(monkeypatch):
    """Synthetic reducer inputs test aggregation only, with no physical authority."""
    source_hashes = {
        name: canonical_hash({"synthetic_binding": name})
        for name in (
            "binding_hash",
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_hash",
            "physical_equation_scaling_binding_hash",
            "execution_state_binding_hash",
            "checkpoint_chain_hash",
            "terminal_checkpoint_state_hash",
            "kinematic_state_chain_hash",
            "material_state_projection_chain_hash",
            "terminal_receipt_hash",
            "path_history_hash",
        )
    }
    source = SimpleNamespace(
        **source_hashes,
        terminal_epoch=2,
        terminal_load_factor=1.0,
        _checkpoint_chain=SimpleNamespace(
            root_checkpoint=SimpleNamespace(
                state_hash=canonical_hash({"synthetic_root": True})
            )
        ),
        _terminal_receipt=SimpleNamespace(
            to_manifest=lambda: {"synthetic_contract_only": True}
        ),
    )
    adapter = SimpleNamespace(
        source_binding=source,
        adapter_hash=canonical_hash({"synthetic_adapter": True}),
        numerical_result=SimpleNamespace(
            result_hash=canonical_hash({"synthetic_result": True})
        ),
    )
    synthetic_steps = [
        {
            "epoch": epoch,
            "envelope": {
                "maximum_translation_m": translation,
                "maximum_absolute_fiber_strain": strain,
                "governing_translation": {"epoch": epoch, "node_id": "N2"},
                "governing_fiber_strain": {
                    "epoch": epoch,
                    "member_id": "M1",
                    "integration_point_index": 0,
                    "fiber_index": 1,
                    "fiber_id": "synthetic-fiber",
                },
            },
        }
        for epoch, translation, strain in ((1, 0.02, 0.004), (2, 0.01, 0.002))
    ]
    recovered_epochs = []

    def identity_validation(candidate):
        assert candidate is adapter
        return candidate

    def synthetic_recovery(candidate, epoch):
        assert candidate is adapter
        recovered_epochs.append(epoch)
        return deepcopy(synthetic_steps[epoch - 1])

    monkeypatch.setattr(
        history_module,
        "validate_fiber_frame_nonlinear_numerical_result_adapter",
        identity_validation,
    )
    monkeypatch.setattr(history_module, "_recover_step", synthetic_recovery)
    payload = history_module.create_fiber_frame_nonlinear_engineering_history(
        adapter
    ).to_dict()
    assert recovered_epochs == [1, 2]
    assert payload["steps"] == synthetic_steps
    assert payload["envelope"] == synthetic_steps[0]["envelope"]
    assert payload["envelope"]["governing_translation"]["epoch"] == 1
    assert payload["envelope"]["governing_fiber_strain"]["epoch"] == 1


def test_history_snapshots_are_detached_and_object_is_frozen(recovered_history):
    history = recovered_history["history"]
    expected = history.to_dict()
    changed = history.to_dict()
    changed["steps"][0]["recovery_arrays"]["fiber_strain"][0] = 999.0
    changed["steps"][0]["bindings"]["checkpoint_state_hash"] = "unbound"
    changed["envelope"]["maximum_translation_m"] = 999.0
    assert history.to_dict() == expected
    with pytest.raises(FrozenInstanceError):
        history.history_hash = "sha256:" + "0" * 64
    changed_hash = replace(history, history_hash="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="fiber_frame_history_hash_mismatch"):
        changed_hash.to_dict()
    changed_payload = replace(
        history,
        _payload_json=history._payload_json.replace('"ready"', '"unverified"', 1),
    )
    with pytest.raises(ValueError, match="fiber_frame_history_hash_mismatch"):
        changed_payload.to_dict()


@pytest.mark.parametrize("tamper", ["checkpoint", "material", "kinematic", "j4"])
def test_earlier_epoch_tampering_is_rejected_before_history_replay(
    recovered_history, monkeypatch, tamper
):
    adapter = recovered_history["adapter"]
    source = adapter.source_binding
    early_epoch = 1
    if tamper == "checkpoint":
        target = source._checkpoint_chain.checkpoints[early_epoch]
        values = list(target.global_displacements)
        values[-1] = float(np.nextafter(values[-1], math.inf))
        attribute, changed = "global_displacements", tuple(values)
    elif tamper == "material":
        target = source._material_chain.projections[early_epoch].bundle
        values = list(target._state_bytes)
        values[0] = bytes([values[0][0] ^ 1]) + values[0][1:]
        attribute, changed = "_state_bytes", tuple(values)
    elif tamper == "kinematic":
        target = source._kinematic_chain.committed_states[early_epoch]
        attribute, changed = "checkpoint_state_hash", "sha256:" + "e" * 64
    else:
        target = source._execution_state_binding
        values = list(target.epoch_bindings)
        values[early_epoch] = replace(
            values[early_epoch], checkpoint_state_hash="sha256:" + "e" * 64
        )
        attribute, changed = "epoch_bindings", tuple(values)
    # Frozen source objects retain MappingProxy arrays; restore exactly in place.
    monkeypatch.setitem(target.__dict__, attribute, changed)

    def forbidden_replay(*args, **kwargs):
        pytest.fail("Invalid earlier source epoch reached engineering recovery")

    monkeypatch.setattr(
        history_module, "_replay_epoch_engineering_outputs", forbidden_replay
    )
    with pytest.raises(ValueError):
        history_module.create_fiber_frame_nonlinear_engineering_history(adapter)
