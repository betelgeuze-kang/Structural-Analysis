"""Physical duplicate isolation must survive renamed IDs and reordered input."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
    fiber_frame_physical_model_identity,
    fiber_frame_physical_model_payload,
)
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    FiberFrameWarmStartDataError,
    collect_fiber_frame_warm_start_data,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
import structural_analysis.benchmark.fiber_frame_learning_study as study
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)
REVISION = "a" * 40


def _payload():
    """Use distinct properties on both members so bad reference rewrites show up."""
    payload = json.loads(EXAMPLE.read_bytes())
    payload["nodes"].insert(1, {"id": "MID", "coordinates": [1.5, 0.0, 0.0]})
    payload["elements"][0]["nodes"] = ["N1", "MID"]
    member = deepcopy(payload["elements"][0])
    member.update(id="M2", nodes=["MID", "N2"], section="RC2")
    payload["elements"].append(member)
    steel, concrete = deepcopy(payload["materials"])
    steel.update(id="steel2", yield_stress_mpa=260.0)
    concrete.update(id="concrete2", compressive_strength_mpa=31.0)
    payload["materials"].extend([steel, concrete])
    section = deepcopy(payload["sections"][0])
    section.update(
        id="RC2", width_m=0.41, steel_material="steel2", concrete_material="concrete2"
    )
    payload["sections"].append(section)
    load = deepcopy(payload["loads"][0])
    load["node"] = "MID"
    load["components"]["FY"] = -2.0
    payload["loads"].append(load)
    return payload


def _model(payload):
    return load_neutral_json_bytes(json.dumps(payload, allow_nan=False).encode())


def _aliased(payload, kind):
    result = deepcopy(payload)
    if kind in ("nodes", "all"):
        aliases = {
            row["id"]: f"renamed-node-{index}"
            for index, row in enumerate(result["nodes"])
        }
        for row in result["nodes"]:
            row["id"] = aliases[row["id"]]
        for row in result["elements"]:
            row["nodes"] = [aliases[node] for node in row["nodes"]]
        for row in result["loads"] + result["supports"]:
            row["node"] = aliases[row["node"]]
    if kind in ("materials", "all"):
        aliases = {
            row["id"]: f"renamed-material-{index}"
            for index, row in enumerate(result["materials"])
        }
        for row in result["materials"]:
            row["id"] = aliases[row["id"]]
        for row in result["sections"]:
            row["steel_material"] = aliases[row["steel_material"]]
            row["concrete_material"] = aliases[row["concrete_material"]]
    if kind in ("sections", "all"):
        aliases = {
            row["id"]: f"renamed-section-{index}"
            for index, row in enumerate(result["sections"])
        }
        for row in result["sections"]:
            row["id"] = aliases[row["id"]]
        for row in result["elements"]:
            row["section"] = aliases[row["section"]]
    if kind in ("elements", "all"):
        for index, row in enumerate(result["elements"]):
            row["id"] = f"renamed-member-{index}"
    if kind in ("declaration_order", "all"):
        for field in ("nodes", "elements", "materials", "sections", "loads"):
            result[field].reverse()
        result["supports"][0]["dofs"].reverse()
    return result


def _forbidden(*args, **kwargs):
    raise AssertionError("duplicate preflight must not execute analysis or training")


@pytest.mark.parametrize(
    "kind", ["nodes", "materials", "sections", "elements", "declaration_order", "all"]
)
def test_entity_aliases_and_declaration_order_keep_physical_identity(kind, monkeypatch):
    original = _model(_payload())
    renamed = _model(_aliased(_payload(), kind))
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", _forbidden)
    monkeypatch.setattr(public_api, "run_stateful_fiber_frame2d_load_path", _forbidden)
    assert original.canonical_model_checksum != renamed.canonical_model_checksum
    assert original.input_checksum != renamed.input_checksum
    assert fiber_frame_physical_model_payload(
        original
    ) == fiber_frame_physical_model_payload(renamed)
    assert fiber_frame_physical_model_identity(
        original
    ) == fiber_frame_physical_model_identity(renamed)
    assert (
        fiber_frame_physical_model_payload(original)["identity_profile"]
        == PHYSICAL_MODEL_IDENTITY_PROFILE
    )


@pytest.mark.parametrize(
    "kind", ["nodes", "materials", "sections", "elements", "declaration_order", "all"]
)
def test_aliased_train_holdout_is_rejected_before_collection_or_training(
    kind, monkeypatch
):
    original = _payload()
    validation = deepcopy(original)
    validation["sections"][0]["width_m"] += 0.001
    variants = [original, validation, _aliased(original, kind)]
    cases = tuple(
        FiberFrameWarmStartDataCase(
            f"case-{index}",
            f"project-{index}",
            f"geometry-{index}",
            f"history-{index}",
            split,
            _model(payload),
            public_api.PublicRCFiberFrameConfig(load_steps=2),
        )
        for index, (split, payload) in enumerate(
            zip(("train", "validation", "holdout"), variants, strict=True)
        )
    )
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", _forbidden)
    monkeypatch.setattr(public_api, "run_stateful_fiber_frame2d_load_path", _forbidden)
    monkeypatch.setattr(study, "train_fiber_frame_warm_start_policy", _forbidden)
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", _forbidden
    )
    for execute in (
        collect_fiber_frame_warm_start_data,
        study.run_fiber_frame_learning_study,
    ):
        with pytest.raises(FiberFrameWarmStartDataError, match="split_leakage"):
            execute(cases, source_revision=REVISION)


@pytest.mark.parametrize(
    "change",
    ["coordinates", "width", "steel", "concrete", "load", "integration", "orientation"],
)
def test_actual_geometry_material_load_and_integration_changes_remain_distinct(change):
    original = _payload()
    altered = deepcopy(original)
    if change == "coordinates":
        altered["nodes"][1]["coordinates"][0] += 0.01
    elif change == "width":
        altered["sections"][0]["width_m"] += 0.001
    elif change == "steel":
        altered["materials"][0]["yield_stress_mpa"] += 1.0
    elif change == "concrete":
        altered["materials"][1]["compressive_strength_mpa"] += 1.0
    elif change == "load":
        altered["loads"][0]["components"]["FY"] -= 1.0
    elif change == "integration":
        altered["elements"][0]["integration_order"] = 3
    else:
        # Keep oriented member endpoints: reversing them changes local section axes.
        altered["elements"][0]["nodes"].reverse()
    assert fiber_frame_physical_model_identity(
        _model(original)
    ) != fiber_frame_physical_model_identity(_model(altered))


def test_metadata_warnings_integer_float_and_signed_zero_are_not_new_physics():
    original = _payload()
    altered = deepcopy(original)
    altered["metadata"]["case_id"] = "another-import-label"
    altered["warnings"] = ["Imported again"]
    for node in altered["nodes"]:
        node["coordinates"] = [
            int(value) if value.is_integer() else value for value in node["coordinates"]
        ]
        node["coordinates"][2] = -0.0
    altered["loads"][0]["components"]["FY"] = -10
    assert fiber_frame_physical_model_identity(
        _model(original)
    ) == fiber_frame_physical_model_identity(_model(altered))


def test_unsupported_model_does_not_receive_a_supported_physical_identity(monkeypatch):
    payload = _payload()
    payload["elements"][0]["release_i"] = ["RZ"]
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", _forbidden)
    with pytest.raises(ValueError):
        fiber_frame_physical_model_identity(_model(payload))
