"""Static model conditioning must not enter any response or material operation."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_warm_start_features import (
    MAX_MODEL_FEATURE_COUNT,
    MODEL_FEATURE_PROFILE,
    FiberFrameWarmStartModelFeatures,
    decode_fiber_frame_warm_start_model_features,
    fiber_frame_warm_start_model_features,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import stateful_fiber_frame2d as assembly
from structural_analysis.assembly import stateful_fiber_frame2d_solver as solver
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import StatefulRCFiberSection
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)


@pytest.fixture(autouse=True)
def forbid_response(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("model feature extraction must not evaluate a response")

    for owner, names in (
        (
            public_api,
            ("analyze_public_rc_fiber_frame", "run_stateful_fiber_frame2d_load_path"),
        ),
        (
            solver,
            (
                "solve_stateful_fiber_frame2d_load_step",
                "run_stateful_fiber_frame2d_load_path",
            ),
        ),
        (assembly, ("assemble_stateful_fiber_frame2d",)),
        (
            StatefulFiberBeam2D,
            ("integrate", "initial_state", "strain_displacement_matrix"),
        ),
        (
            StatefulRCFiberSection,
            ("integrate", "integrate_with_material_runtime", "initial_state"),
        ),
        (BilinearCombinedHardeningSteel, ("integrate", "initial_state")),
        (AsymmetricConcreteDamageMaterial, ("integrate", "initial_state")),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield calls
    assert calls == []


def _payload():
    return json.loads(EXAMPLE.read_bytes())


def _problem(payload=None):
    model = load_neutral_json_bytes(
        json.dumps(payload or _payload(), allow_nan=False).encode()
    )
    compiled, blockers, _ = public_api._compile(model.detached_analysis_snapshot())
    assert compiled is not None and not blockers
    return compiled.problem


def test_compiled_feature_values_follow_actual_solver_order_and_units():
    payload = _payload()
    payload["loads"][0]["components"].update(FX=2.5, FY=-4.0, MZ=7.0)
    problem = _problem(payload)
    result = fiber_frame_warm_start_model_features(problem)
    values = dict(zip(result.feature_names, result.values, strict=True))
    assert result.problem_contract_hash == problem.contract_hash
    assert values["node_0_x_m"] == problem.node_coordinates_m[0][0]
    assert values["node_1_x_m"] == problem.node_coordinates_m[1][0]
    assert values["node_0_reference_fx_kn"] == 0.0
    assert values["node_1_reference_fx_kn"] == 2.5
    assert values["node_1_reference_fy_kn"] == -4.0
    assert values["node_1_reference_mz_kn_m"] == 7.0
    assert values["rotation_coordinate_scale_m"] == problem.rotation_coordinate_scale_m
    for member_index, member in enumerate(problem.members):
        assert values[f"member_{member_index}_length_m"] == member.element.length_m
        for fiber_index, fiber in enumerate(member.element.section.fibers):
            prefix = f"member_{member_index}_fiber_{fiber_index}"
            assert values[prefix + "_y_m"] == fiber.y_m
            assert values[prefix + "_area_m2"] == fiber.area_m2
    assert result.to_dict()["feature_profile"] == MODEL_FEATURE_PROFILE
    assert all(
        "stress" not in name and "displacement" not in name and "checkpoint" not in name
        for name in result.feature_names
    )


@pytest.mark.parametrize(
    "change",
    [
        "span",
        "inclination",
        "load",
        "load_component",
        "width",
        "depth",
        "cover",
        "bars",
        "bar_area",
        "rotation_scale",
    ],
)
def test_geometry_section_and_load_changes_condition_genesis_without_context_change(
    change,
):
    original = _problem()
    payload = _payload()
    if change == "span":
        payload["nodes"][1]["coordinates"][0] = 4.0
    elif change == "inclination":
        payload["nodes"][1]["coordinates"][1] = 0.5
    elif change == "load":
        payload["loads"][0]["components"]["FY"] = -2.0
    elif change == "load_component":
        payload["loads"][0]["components"].update(FY=0.0, FX=1.0)
    elif change == "width":
        payload["sections"][0]["width_m"] = 0.45
    elif change == "depth":
        payload["sections"][0]["depth_m"] = 0.65
    elif change == "cover":
        payload["sections"][0]["cover_m"] = 0.06
    elif change == "bars":
        payload["sections"][0]["top_bar_count"] += 1
    elif change == "bar_area":
        payload["sections"][0]["bar_area_m2"] *= 1.1
    changed = (
        replace(original, rotation_coordinate_scale_m=4.0)
        if change == "rotation_scale"
        else _problem(payload)
    )
    first = fiber_frame_warm_start_model_features(original)
    second = fiber_frame_warm_start_model_features(changed)
    assert first.context_hash == second.context_hash
    assert first.feature_names == second.feature_names
    assert first.values != second.values
    assert first.problem_contract_hash != second.problem_contract_hash
    assert first.feature_hash != second.feature_hash


def test_load_location_on_a_two_member_chain_is_an_explicit_feature():
    payload = _payload()
    payload["nodes"].insert(1, {"id": "MID", "coordinates": [1.5, 0.0, 0.0]})
    payload["elements"][0]["nodes"] = ["N1", "MID"]
    member = deepcopy(payload["elements"][0])
    member.update(id="M2", nodes=["MID", "N2"])
    payload["elements"].append(member)
    first = fiber_frame_warm_start_model_features(_problem(payload))
    payload["loads"][0]["node"] = "MID"
    second = fiber_frame_warm_start_model_features(_problem(payload))
    assert first.context_hash == second.context_hash
    assert first.feature_names == second.feature_names
    assert first.values != second.values


@pytest.mark.parametrize(
    "change",
    [
        "member_count",
        "orientation",
        "steel",
        "concrete",
        "integration",
        "fiber_count",
        "fiber_kind_order",
        "fixed_dofs",
    ],
)
def test_topology_material_and_discrete_fiber_layout_change_context(change):
    original = _problem()
    payload = _payload()
    if change == "member_count":
        payload["nodes"].insert(1, {"id": "MID", "coordinates": [1.5, 0.0, 0.0]})
        payload["elements"][0]["nodes"] = ["N1", "MID"]
        member = deepcopy(payload["elements"][0])
        member.update(id="M2", nodes=["MID", "N2"])
        payload["elements"].append(member)
    elif change == "orientation":
        payload["elements"][0]["nodes"].reverse()
    elif change == "steel":
        payload["materials"][0]["yield_stress_mpa"] += 1.0
    elif change == "concrete":
        payload["materials"][1]["history_tolerance"] *= 2.0
    elif change == "integration":
        payload["elements"][0]["integration_order"] = 3
    elif change == "fiber_count":
        payload["sections"][0]["concrete_layer_count"] += 1
    changed = _problem(payload)
    if change == "fiber_kind_order":
        member = original.members[0]
        section = member.element.section
        fibers = list(section.fibers)
        fibers[0], fibers[-1] = fibers[-1], fibers[0]
        changed = replace(
            original,
            members=(
                replace(
                    member,
                    element=replace(
                        member.element, section=replace(section, fibers=tuple(fibers))
                    ),
                ),
            ),
        )
    elif change == "fixed_dofs":
        changed = replace(original, fixed_global_dofs=(3, 4, 5))
    assert (
        fiber_frame_warm_start_model_features(original).context_hash
        != fiber_frame_warm_start_model_features(changed).context_hash
    )


def test_authored_aliases_preserve_features_only_when_actual_order_is_retained():
    original = _problem()
    member = original.members[0]
    section = member.element.section
    renamed_section = replace(
        section,
        section_id="aliased-section",
        fibers=tuple(
            replace(fiber, fiber_id=f"alias-{index}")
            for index, fiber in enumerate(section.fibers)
        ),
        steel=replace(section.steel, material_id="aliased-steel"),
        concrete=replace(section.concrete, material_id="aliased-concrete"),
    )
    changed = replace(
        original,
        case_id="alias-case",
        members=(
            replace(
                member,
                member_id="alias-member",
                element=replace(
                    member.element, element_id="alias-member", section=renamed_section
                ),
            ),
        ),
    )
    first = fiber_frame_warm_start_model_features(original)
    second = fiber_frame_warm_start_model_features(changed)
    assert first.context_hash == second.context_hash
    assert first.feature_names == second.feature_names
    assert first.values == second.values
    assert first.problem_contract_hash != second.problem_contract_hash
    assert first.feature_hash != second.feature_hash
    reordered = replace(
        original,
        node_coordinates_m=tuple(reversed(original.node_coordinates_m)),
        members=(replace(member, node_i=1, node_j=0),),
        fixed_global_dofs=(3, 4, 5),
        reference_external_loads=((1, -1.0),),
    )
    assert (
        fiber_frame_warm_start_model_features(reordered).context_hash
        != first.context_hash
    )


def test_feature_snapshot_and_decoded_artifact_are_immutable_and_detached():
    result = fiber_frame_warm_start_model_features(_problem())
    exported = result.to_dict()
    restored = decode_fiber_frame_warm_start_model_features(exported)
    assert restored == result
    exported["values"][0] = 888.0
    exported["feature_names"][0] = "changed"
    assert restored == result
    with pytest.raises(FrozenInstanceError):
        result.context_hash = "sha256:" + "1" * 64
    assert result.feature_hash == canonical_hash(
        {k: v for k, v in result.to_dict().items() if k != "feature_hash"}
    )


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "profile",
        "extra",
        "missing",
        "hash",
        "value",
        "name",
        "boolean",
        "string",
        "nonfinite",
        "duplicate",
        "mutable_tuple",
    ],
)
def test_detached_artifact_decoder_rejects_invalid_or_inconsistent_values(change):
    payload = fiber_frame_warm_start_model_features(_problem()).to_dict()
    if change == "schema":
        payload["schema_version"] = "future.v2"
    elif change == "profile":
        payload["feature_profile"] = "future.v2"
    elif change == "extra":
        payload["stress"] = 0.0
    elif change == "missing":
        del payload["context_hash"]
    elif change == "hash":
        payload["feature_hash"] = "sha256:" + "0" * 64
    elif change == "value":
        payload["values"][0] += 0.1
    elif change == "name":
        payload["feature_names"][0] = "changed"
    elif change == "boolean":
        payload["values"][0] = False
    elif change == "string":
        payload["values"][0] = "0.0"
    elif change == "nonfinite":
        payload["values"][0] = float("inf")
    elif change == "duplicate":
        payload["feature_names"][1] = payload["feature_names"][0]
    else:
        payload["values"] = tuple(payload["values"])
    with pytest.raises(ValueError):
        decode_fiber_frame_warm_start_model_features(payload)


def test_bounded_feature_count_and_exact_types_fail_before_response():
    result = fiber_frame_warm_start_model_features(_problem())
    with pytest.raises(ValueError, match="bounded"):
        replace(
            result,
            feature_names=tuple(
                f"value_{i}" for i in range(MAX_MODEL_FEATURE_COUNT + 1)
            ),
            values=(0.0,) * (MAX_MODEL_FEATURE_COUNT + 1),
        )
    with pytest.raises(ValueError, match="immutable"):
        FiberFrameWarmStartModelFeatures(
            result.problem_contract_hash,
            result.context_hash,
            list(result.feature_names),
            result.values,
        )
    for bad in (None, {}, object()):
        with pytest.raises(ValueError, match="exact Stateful"):
            fiber_frame_warm_start_model_features(bad)
    original = _problem()
    member = original.members[0]
    section = member.element.section
    fibers = tuple(
        replace(section.fibers[i % len(section.fibers)], fiber_id=f"fiber-{i}")
        for i in range(MAX_MODEL_FEATURE_COUNT)
    )
    oversized = replace(
        original,
        members=(
            replace(
                member,
                element=replace(
                    member.element, section=replace(section, fibers=fibers)
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="bounded feature count"):
        fiber_frame_warm_start_model_features(oversized)


@pytest.mark.parametrize(
    "change",
    [
        "nonfinite_coordinate",
        "mutable_coordinates",
        "unsupported_section",
        "nonfinite_material",
    ],
)
def test_forged_frozen_metadata_is_not_silently_encoded(change):
    original = _problem()
    changed = deepcopy(original)
    if change == "nonfinite_coordinate":
        object.__setattr__(
            changed, "node_coordinates_m", ((float("nan"), 0.0), (3.0, 0.0))
        )
    elif change == "mutable_coordinates":
        object.__setattr__(changed, "node_coordinates_m", [[0.0, 0.0], [3.0, 0.0]])
    elif change == "unsupported_section":
        object.__setattr__(changed.members[0].element, "section", object())
    else:
        object.__setattr__(
            changed.members[0].element.section.steel, "yield_stress_mpa", float("nan")
        )
    with pytest.raises(ValueError):
        fiber_frame_warm_start_model_features(changed)
