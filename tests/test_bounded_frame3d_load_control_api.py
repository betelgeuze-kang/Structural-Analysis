from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.adapters.bounded_frame3d_load_control_model_ir import (
    BoundedFrame3DLoadControlModelIRAdapterError,
    adapt_bounded_frame3d_load_control_model_ir_v2,
)
from structural_analysis.api.frame3d_load_control import (
    BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_VERSION,
    BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION,
    BoundedFrame3DLoadControlConfig,
    BoundedFrame3DLoadControlError,
    advance_bounded_frame3d_load_control_model_ir,
    analyze_bounded_frame3d_load_control_model_ir,
    bounded_frame3d_load_control_resume_contract_hash,
    parse_bounded_frame3d_load_control_config,
    validate_bounded_frame3d_load_control_result_manifest,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.model_ir.loader import load_model_ir_v2, parse_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "examples/bounded_frame3d_load_control_multimember.model-ir.v2.json"


@pytest.fixture(scope="module")
def document():
    return load_model_ir_v2(MODEL_PATH)


@pytest.fixture(scope="module")
def config() -> BoundedFrame3DLoadControlConfig:
    return BoundedFrame3DLoadControlConfig("LC_MULTI", (0.25, 0.5, 1.0))


@pytest.fixture(scope="module")
def one_shot(document, config):
    return analyze_bounded_frame3d_load_control_model_ir(document, config)


@pytest.fixture(scope="module")
def prefix(document, config):
    return advance_bounded_frame3d_load_control_model_ir(
        document,
        config,
        maximum_new_steps=2,
    )


@pytest.fixture(scope="module")
def resumed(document, config, prefix):
    return analyze_bounded_frame3d_load_control_model_ir(
        document,
        config,
        restart_checkpoint_artifact=prefix.checkpoint_artifact_bytes(),
    )


def _manifest_bytes(payload: dict) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _rehash_result(payload: dict) -> bytes:
    payload = deepcopy(payload)
    payload.pop("result_hash", None)
    payload["result_hash"] = canonical_hash(payload)
    return _manifest_bytes(payload)


def _rehash_checkpoint_artifact(payload: dict) -> bytes:
    payload = deepcopy(payload)
    checkpoint = payload["checkpoint"]
    checkpoint.pop("checkpoint_hash", None)
    checkpoint["checkpoint_hash"] = canonical_hash(checkpoint)
    payload.pop("artifact_hash", None)
    payload["artifact_hash"] = canonical_hash(payload)
    return _manifest_bytes(payload)


def test_multimember_full_load_result_closes_without_promotion(
    document,
    config,
    one_shot,
) -> None:
    payload = one_shot.to_dict()

    assert one_shot.schema_version == BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION
    assert one_shot.contract_pass is True
    assert one_shot.source_binding["model_ir_content_hash"] == document.content_hash
    assert tuple(one_shot.source_binding["node_ids"]) == ("N1", "N2", "N3")
    assert tuple(one_shot.source_binding["member_ids"]) == ("M1A", "M2B")
    assert len(one_shot.member_recovery) == 2
    assert len(one_shot.full_node_equilibrium) == 3
    assert one_shot.metrics["final_load_factor"] == 1.0
    assert one_shot.metrics["accepted_step_count"] == 3
    assert one_shot.metrics["numerical_result_state_epoch"] == 3
    assert one_shot.metrics["fallback_count"] == 0
    assert one_shot.metrics["regularization_count"] == 0
    assert one_shot.solver["full_node_equilibrium"]["contract_pass"] is True
    assert one_shot.numerical_result_ir["bindings"]["state_epoch"] == 3
    assert one_shot.numerical_result_ir["authority"]["reaction"] == "not_evaluated"
    assert one_shot.numerical_result_ir["authority"]["member_force"] == (
        "not_evaluated"
    )
    assert one_shot.authority["numerical_result_ir_reaction_authority"] is False
    assert one_shot.authority["numerical_result_ir_member_force_authority"] is False
    assert one_shot.authority["solver_derived_reaction_recovery"] == (
        "bounded_candidate"
    )
    assert one_shot.authority["solver_derived_member_recovery"] == ("bounded_candidate")
    assert one_shot.authority["capability_registry_public"] is False
    assert one_shot.authority["workbench_execution"] is False
    assert one_shot.authority["public_product_promotion"] is False
    assert one_shot.authority["release_eligible"] is False
    assert payload["checkpoint_artifact"]["request_hash"] == config.request_hash


def test_full_schedule_partial_advance_resumes_to_exact_terminal_state(
    document,
    config,
    one_shot,
    prefix,
    resumed,
) -> None:
    assert prefix.load_factors == config.load_factors
    assert prefix.metrics["completed_prefix_count"] == 2
    assert prefix.metrics["remaining_load_factor_count"] == 1
    assert resumed.metrics["accepted_step_count"] == 1
    assert resumed.metrics["numerical_result_state_epoch"] == 1
    assert resumed.metrics["state_epoch_scope"] == "current_request_suffix"
    assert resumed.metrics["completed_prefix_count"] == 3
    assert resumed.checkpoint_artifact_bytes() == one_shot.checkpoint_artifact_bytes()
    assert resumed.node_displacements == one_shot.node_displacements
    assert resumed.support_reactions == one_shot.support_reactions
    assert resumed.member_recovery == one_shot.member_recovery
    assert resumed.full_node_equilibrium == one_shot.full_node_equilibrium
    assert (
        bounded_frame3d_load_control_resume_contract_hash(document, config)
        == (prefix.checkpoint_artifact["resume_contract_hash"])
    )


def test_config_and_persisted_result_have_exact_public_replay_contract(
    document,
    config,
    resumed,
) -> None:
    assert config.to_dict()["schema_version"] == (
        BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_VERSION
    )
    assert parse_bounded_frame3d_load_control_config(config.to_dict()) == config
    restored = validate_bounded_frame3d_load_control_result_manifest(
        resumed.manifest_bytes(),
        document=document,
        config=config,
        checkpoint_artifact_bytes=resumed.checkpoint_artifact_bytes(),
    )
    assert restored.result_hash == resumed.result_hash
    assert restored.node_displacements == resumed.node_displacements

    integer_alias = config.to_dict()
    integer_alias["load_factors"][-1] = 1
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_config_numeric_domain_mismatch",
    ):
        parse_bounded_frame3d_load_control_config(integer_alias)

    iteration_alias = config.to_dict()
    iteration_alias["solver_config"]["maximum_iterations"] = 20.0
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_schema_invalid",
    ):
        parse_bounded_frame3d_load_control_config(iteration_alias)

    boolean_alias = config.to_dict()
    boolean_alias["load_factors"][0] = True
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_schema_invalid",
    ):
        parse_bounded_frame3d_load_control_config(boolean_alias)


def test_persisted_result_rejects_duplicate_noncanonical_and_embedded_artifact(
    document,
    config,
    one_shot,
) -> None:
    duplicate_key = (
        b'{"schema_version":"bounded-frame3d-load-control-result.v1",'
        + one_shot.manifest_bytes()[1:]
    )
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_result_manifest_json_invalid",
    ):
        validate_bounded_frame3d_load_control_result_manifest(
            duplicate_key,
            document=document,
            config=config,
            checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
        )

    noncanonical = json.dumps(one_shot.to_dict(), indent=2).encode("utf-8")
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_result_manifest_noncanonical",
    ):
        validate_bounded_frame3d_load_control_result_manifest(
            noncanonical,
            document=document,
            config=config,
            checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
        )

    embedded_mismatch = one_shot.to_dict()
    embedded_mismatch["checkpoint_artifact"]["artifact_hash"] = "sha256:" + "2" * 64
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_result_checkpoint_artifact_mismatch",
    ):
        validate_bounded_frame3d_load_control_result_manifest(
            _rehash_result(embedded_mismatch),
            document=document,
            config=config,
            checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
        )


def test_persisted_result_rejects_rehashed_source_and_result_ir_tampering(
    document,
    config,
    one_shot,
) -> None:
    forged_source = one_shot.to_dict()
    receipt = forged_source["solver"]["source_receipt"]
    receipt["steps"][0]["scaled_residual_inf_norm"] *= 0.5
    receipt.pop("result_hash")
    receipt["result_hash"] = canonical_hash(receipt)
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_source_solver_replay_mismatch",
    ):
        validate_bounded_frame3d_load_control_result_manifest(
            _rehash_result(forged_source),
            document=document,
            config=config,
            checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
        )

    for field_name in ("operator_hash", "material_state_bundle_hash"):
        forged_result_ir = one_shot.to_dict()
        numerical = forged_result_ir["numerical_result_ir"]
        numerical["bindings"][field_name] = "sha256:" + "1" * 64
        if field_name == "material_state_bundle_hash":
            descriptor = numerical["displacement_artifact"]
            uri_parts = descriptor["artifact_uri"].split("/")
            uri_parts[-2] = "1" * 16
            descriptor["artifact_uri"] = "/".join(uri_parts)
            descriptor.pop("content_hash")
            descriptor["content_hash"] = canonical_hash(descriptor)
        numerical.pop("result_hash")
        numerical["result_hash"] = canonical_hash(numerical)
        with pytest.raises(
            BoundedFrame3DLoadControlError,
            match="bounded_frame3d_load_numerical_result_ir_binding_mismatch",
        ):
            validate_bounded_frame3d_load_control_result_manifest(
                _rehash_result(forged_result_ir),
                document=document,
                config=config,
                checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
            )

    forged_recovery = one_shot.to_dict()
    forged_recovery["member_recovery"][0]["current_length_m"] += 1.0e-9
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_result_recovery_mismatch",
    ):
        validate_bounded_frame3d_load_control_result_manifest(
            _rehash_result(forged_recovery),
            document=document,
            config=config,
            checkpoint_artifact_bytes=one_shot.checkpoint_artifact_bytes(),
        )


def test_checkpoint_rejects_nonfinite_numeric_alias_and_cross_schedule(
    document,
    config,
    one_shot,
) -> None:
    alias = json.loads(one_shot.checkpoint_artifact_bytes())
    alias["checkpoint"]["load_factor"] = 1
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_checkpoint_numeric_domain_mismatch",
    ):
        analyze_bounded_frame3d_load_control_model_ir(
            document,
            config,
            restart_checkpoint_artifact=_rehash_checkpoint_artifact(alias),
        )

    nonfinite = one_shot.checkpoint_artifact_bytes().replace(
        b'"load_factor":1.0',
        b'"load_factor":NaN',
        1,
    )
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_checkpoint_json_invalid",
    ):
        analyze_bounded_frame3d_load_control_model_ir(
            document,
            config,
            restart_checkpoint_artifact=nonfinite,
        )

    other_config = BoundedFrame3DLoadControlConfig("LC_MULTI", (0.25, 0.75, 1.0))
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_checkpoint_binding_mismatch",
    ):
        analyze_bounded_frame3d_load_control_model_ir(
            document,
            other_config,
            restart_checkpoint_artifact=one_shot.checkpoint_artifact_bytes(),
        )

    other_payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    other_payload["nodes"][2]["coordinates_m"][0] = 4.1
    other_document = parse_model_ir_v2(other_payload)
    with pytest.raises(
        BoundedFrame3DLoadControlError,
        match="bounded_frame3d_load_checkpoint_binding_mismatch",
    ):
        analyze_bounded_frame3d_load_control_model_ir(
            other_document,
            config,
            restart_checkpoint_artifact=one_shot.checkpoint_artifact_bytes(),
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda payload: payload["nodes"][2]["coordinates_m"].__setitem__(0, 1.0e10),
            "bounded_frame3d_load_coordinate_magnitude_out_of_range",
        ),
        (
            lambda payload: payload["load_patterns"][0]["nodal_loads"][0][
                "components_si"
            ].__setitem__("FY", 1.0e19),
            "bounded_frame3d_load_magnitude_out_of_range",
        ),
    ],
)
def test_adapter_rejects_oversized_arithmetic_sources(mutate, reason) -> None:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    document = parse_model_ir_v2(payload)
    with pytest.raises(BoundedFrame3DLoadControlModelIRAdapterError, match=reason):
        adapt_bounded_frame3d_load_control_model_ir_v2(
            document,
            load_pattern_id="LC_MULTI",
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda payload: payload["elements"][0]["offsets"]["i_global_m"].__setitem__(
                0, 0.1
            ),
            "bounded_frame3d_load_member_offset_unsupported",
        ),
        (
            lambda payload: payload["elements"][0]["releases"].__setitem__("i", ["RZ"]),
            "bounded_frame3d_load_member_release_unsupported",
        ),
    ],
)
def test_adapter_rejects_unsupported_member_features(mutate, reason) -> None:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    document = parse_model_ir_v2(payload)
    with pytest.raises(BoundedFrame3DLoadControlModelIRAdapterError, match=reason):
        adapt_bounded_frame3d_load_control_model_ir_v2(
            document,
            load_pattern_id="LC_MULTI",
        )
