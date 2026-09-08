"""One public material-history solve shared by source-bound integration checks.

The two explicit report-validator tests repeat the existing full source recovery;
they do not request another public analysis or establish independent material V&V.
"""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_constitutive_history as module
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"


def _bytes(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


@pytest.fixture(scope="module")
def material_history():
    directory = Path(
        tempfile.mkdtemp(prefix="structural-fiber-constitutive-integration-")
    )
    print(f"Constitutive integration artifacts: {directory}", flush=True)
    (directory / "model.json").write_bytes(MODEL.read_bytes())
    model = load_neutral_json(directory / "model.json")
    result = public_api.analyze_public_rc_fiber_frame(
        model, public_api.PublicRCFiberFrameConfig(load_steps=4)
    )
    # Preserve even an unexpected failed result before stopping the fixture.
    public_bytes = _bytes(result.to_dict())
    (directory / "public-result.json").write_bytes(public_bytes)
    assert result.status == "ready" and result.contract_pass is True
    checkpoint_bytes = result.checkpoint_artifact()
    (directory / "checkpoint.json").write_bytes(checkpoint_bytes)
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    report_bytes = _bytes(report.to_dict())
    (directory / "constitutive-history.json").write_bytes(report_bytes)
    assert _bytes(result.to_dict()) == public_bytes
    assert result.checkpoint_artifact() == checkpoint_bytes
    return SimpleNamespace(
        directory=directory,
        result=result,
        report=report,
        payload=report.to_dict(),
        public_bytes=public_bytes,
        checkpoint_bytes=checkpoint_bytes,
        report_bytes=report_bytes,
    )


@pytest.fixture(autouse=True)
def no_additional_public_analysis(material_history, monkeypatch):
    # The module fixture above runs first. Full J1-J5 source replay inside the
    # history accessor remains enabled, as required by the public contract.
    def forbidden(*args, **kwargs):
        pytest.fail("this module permits only its one initial public analysis")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(public_api, "_run_load_path", forbidden)
    yield
    assert _bytes(material_history.result.to_dict()) == material_history.public_bytes
    assert (
        material_history.result.checkpoint_artifact()
        == material_history.checkpoint_bytes
    )
    assert _bytes(material_history.report.to_dict()) == material_history.report_bytes


def test_actual_public_source_retains_complete_j1_j5_chain(material_history):
    result = material_history.result
    source = result._authority_adapter.source_binding
    receipt = source._terminal_receipt
    assert result.status == "ready" and result.contract_pass is True
    assert source.convergence_gate_passed is True
    assert source.residual_gate_passed is True
    assert source.increment_gate_passed is True
    assert source.accepted_step_count == source.terminal_epoch == 4
    assert receipt.converged is True and receipt.terminal_load_factor == 1.0
    assert receipt.fallback_count == receipt.regularization_count == 0
    assert len(receipt.step_receipts) == 4
    assert source.execution_topology_plan_hash == source._topology_plan.plan_hash
    assert source.kinematic_state_chain_hash == source._kinematic_chain.chain_hash
    assert (
        source.material_state_projection_chain_hash == source._material_chain.chain_hash
    )
    assert (
        source.execution_state_binding_hash
        == source._execution_state_binding.binding_hash
    )
    assert source.terminal_receipt_hash == receipt.terminal_receipt_hash
    assert source.checkpoint_chain_hash == result._checkpoint_chain.chain_hash
    assert result.authority["engineering_design"] == "not_authoritative"


def test_complete_genesis_and_four_accepted_epochs_have_bound_material_layout(
    material_history,
):
    result, payload = material_history.result, material_history.payload
    assert payload["schema_version"] == "public-rc-fiber-frame-constitutive-history.v1"
    assert payload["status"] == "ready" and payload["contract_pass"] is True
    assert payload["accepted_epoch_count"] == 4
    assert [row["epoch"] for row in payload["states"]] == list(range(5))
    assert [row["load_factor"] for row in payload["states"]] == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]
    for row, checkpoint in zip(
        payload["states"], result._checkpoint_chain.checkpoints, strict=True
    ):
        assert row["step_index"] == checkpoint.step_index
        assert row["checkpoint_state_hash"] == checkpoint.state_hash
        assert row["parent_checkpoint_state_hash"] == checkpoint.parent_state_hash
        assert row["material_point_count"] == 84
        assert row["materials"]["steel"]["point_count"] == 12
        assert row["materials"]["concrete"]["point_count"] == 72
    binding = payload["bindings"]
    assert binding["source_result_hash"] == result.result_hash
    assert binding["canonical_model_checksum"] == result.canonical_model_checksum
    assert binding["input_checksum"] == result.input_checksum
    assert binding["checkpoint_artifact_byte_length"] == len(
        material_history.checkpoint_bytes
    )
    assert (
        binding["checkpoint_artifact_hash"]
        == "sha256:" + hashlib.sha256(material_history.checkpoint_bytes).hexdigest()
    )
    assert all(value is False for value in payload["claim_boundary"].values())


def test_actual_concrete_damage_and_energy_are_positive_without_steel_plastic_memory(
    material_history,
):
    states = material_history.payload["states"]
    assert states[0]["total_dissipated_energy_mj"] is None
    assert states[0]["engineering_recovery_hash"] is None
    assert (
        states[0]["engineering_recovery_reason"]
        == "genesis_has_no_engineering_recovery"
    )
    final_concrete = states[-1]["materials"]["concrete"]["fields"]
    assert final_concrete["tensile_damage"]["maximum"] > 0.0
    assert final_concrete["tensile_damage"]["positive_value_point_count"] > 0
    assert final_concrete["dissipated_energy_density_mj_per_m3"]["maximum"] > 0.0
    energies = [row["total_dissipated_energy_mj"] for row in states[1:]]
    assert all(math.isfinite(value) and value >= 0.0 for value in energies)
    assert energies == sorted(energies) and energies[-1] > 0.0
    assert energies[-1] == material_history.result.metrics["total_dissipated_energy_mj"]
    for row in states:
        steel = row["materials"]["steel"]["fields"]["accumulated_plastic_strain"]
        assert steel["maximum"] == 0.0 and steel["positive_value_point_count"] == 0
        assert steel["increased_from_parent_point_count"] == (
            None if row["epoch"] == 0 else 0
        )


def test_retained_memory_and_step_increases_match_distinct_checkpoint_observations(
    material_history,
):
    # Read the committed storage directly, without the production summarizer.
    # No claim is made about rejected Newton trials or inferred yield events.
    previous = None
    for row, checkpoint in zip(
        material_history.payload["states"],
        material_history.result._checkpoint_chain.checkpoints,
        strict=True,
    ):
        current = {"steel": [], "concrete": []}
        for member, element in zip(
            material_history.result._problem.members,
            checkpoint.element_states,
            strict=True,
        ):
            for section in element.integration_point_states:
                for fiber, state in zip(
                    member.element.section.fibers, section.fiber_states, strict=True
                ):
                    current[fiber.material_kind].append(state)
        for kind, names in (
            ("steel", ("accumulated_plastic_strain",)),
            (
                "concrete",
                ("tensile_history_strain", "tensile_damage", "compressive_damage"),
            ),
        ):
            for name in names:
                values = [getattr(state, name) for state in current[kind]]
                stats = row["materials"][kind]["fields"][name]
                assert stats["positive_value_point_count"] == sum(
                    value > 0.0 for value in values
                )
                if previous is None:
                    assert stats["increased_from_parent_point_count"] is None
                    assert stats["parent_comparison_reason"] == "genesis_has_no_parent"
                else:
                    old = [getattr(state, name) for state in previous[kind]]
                    assert stats["increased_from_parent_point_count"] == sum(
                        a > b for a, b in zip(values, old, strict=True)
                    )
                    assert stats["decreased_from_parent_point_count"] == 0
                    assert stats["parent_comparison_reason"] is None
        previous = current


def test_exact_source_validator_accepts_original_report_once(material_history):
    assert (
        module.validate_public_rc_fiber_frame_constitutive_history(
            material_history.report, material_history.result
        )
        is material_history.report
    )


def test_rehashed_statistics_do_not_replace_fresh_source_recovery(material_history):
    payload = deepcopy(material_history.payload)
    stat = payload["states"][-1]["materials"]["concrete"]["fields"]["tensile_damage"]
    stat["maximum"] = math.nextafter(stat["maximum"], math.inf)
    stat["maximum_absolute"] = stat["maximum"]
    payload["report_hash"] = canonical_hash(
        {k: v for k, v in payload.items() if k != "report_hash"}
    )
    changed = module.FiberFrameConstitutiveHistory(
        "ready",
        True,
        payload["report_hash"],
        json.dumps(payload, sort_keys=True, allow_nan=False),
    )
    assert changed.to_dict()["report_hash"] == payload["report_hash"]
    with pytest.raises(ValueError):
        module.validate_public_rc_fiber_frame_constitutive_history(
            changed, material_history.result
        )


@pytest.mark.parametrize(
    "missing", ["_problem", "_checkpoint_chain", "_authority_adapter"]
)
def test_detached_typed_result_cannot_supply_material_history(
    material_history, missing
):
    detached = replace(material_history.result, **{missing: None})
    with pytest.raises(ValueError):
        module.inspect_public_rc_fiber_frame_constitutive_history(detached)


@pytest.mark.parametrize("value", [None, {}, "partial"])
def test_untyped_or_partial_input_cannot_receive_constitutive_authority(value):
    with pytest.raises(ValueError, match="exact PublicRCFiberFrameResult"):
        module.inspect_public_rc_fiber_frame_constitutive_history(value)
