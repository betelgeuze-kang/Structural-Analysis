"""Price-order input semantics only: no output, solver or learned-policy execution."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_layout_search as search
from structural_analysis.benchmark.rc_control_layout_features import (
    control_layout_candidate_features,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def _raw(profile="v1"):
    raw = json.loads(
        Path(
            "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ).read_bytes()
    )
    raw["nodes"].append({"id": "N4", "coordinates": [2.0, 3.0, 0.0]})
    raw["elements"].append(
        {**deepcopy(raw["elements"][-1]), "id": "M3", "nodes": ["N3", "N4"]}
    )
    raw["loads"][0]["node"] = "N3" if profile == "v3" else "N4"
    if profile == "v3":
        raw["supports"].append({"node": "N4", "dofs": ["UX", "UY", "RZ"]})
    return raw


def _request(profile="v1"):
    return BoundedRCFiberDirectControlRequest(
        7 if profile == "v3" else 10,
        (-1e-5, -2e-5),
        experimental_two_fixed_endpoints=profile == "v3",
        constant_nodal_loads=(("N2", 0.0, -0.01, 0.0),) if profile == "v2" else (),
    )


def _model(raw):
    return load_neutral_json_bytes(study._bytes(raw))


def _rename_nodes(raw, names):
    for node in raw["nodes"]:
        node["id"] = names.get(node["id"], node["id"])
    for element in raw["elements"]:
        element["nodes"] = [names.get(node, node) for node in element["nodes"]]
    for row in [*raw["loads"], *raw["supports"]]:
        row["node"] = names.get(row["node"], row["node"])


def _run(mode, baseline, alternative, request, output):
    functions = {
        "full": search.run_control_layout_strategy,
        "pruned": search.run_control_layout_cost_pruned_strategy,
        "staged": search.run_control_layout_staged_strategy,
    }
    return functions[mode](
        baseline,
        (search.RCControlLayoutCandidate("alternative", alternative),),
        request,
        strategy="price_order",
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-10-02", "synthetic preflight declarations only"
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
        output_directory=output,
        full_analysis_budget=2,
        **({"prefix_target_count": 1} if mode == "staged" else {}),
    )


@pytest.fixture
def no_execution(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("forbidden")
        raise AssertionError("no numerical execution or artifact writes permitted")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(study, "_save", forbidden)
    return calls


@pytest.mark.parametrize("mode", ["full", "pruned", "staged"])
@pytest.mark.parametrize(
    "change",
    [
        "v1_control_section",
        "v1_control_geometry",
        "v2_preload_section",
        "v3_control_section",
    ],
)
def test_price_order_rejects_changed_physical_binding_before_output(
    mode, change, tmp_path, no_execution
):
    profile = change[:2]
    before = _raw(profile)
    changed = deepcopy(before)
    if change == "v1_control_geometry":
        changed["nodes"][-1]["coordinates"][1] *= 1.1
    else:
        changed["sections"][0]["width_m"] *= 1.1
    if profile == "v2":
        _rename_nodes(changed, {"N2": "N3", "N3": "N2"})
    else:
        i, j = (1, 2) if profile == "v3" else (2, 3)
        changed["nodes"][i], changed["nodes"][j] = (
            changed["nodes"][j],
            changed["nodes"][i],
        )
    baseline, alternative, request = _model(before), _model(changed), _request(profile)
    # Both actual authored inputs pass the existing compiler/context and are
    # distinct physical alternatives. Duplicate-model rejection cannot mask this.
    descriptors = [
        control_layout_candidate_features(model, request)
        for model in (baseline, alternative)
    ]
    assert descriptors[0]["context_hash"] == descriptors[1]["context_hash"]
    assert (
        descriptors[0]["physical_model_identity"]
        != descriptors[1]["physical_model_identity"]
    )
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="physical control/preload binding mismatch"):
        _run(mode, baseline, alternative, request, output)
    assert not output.exists()
    assert no_execution == []


class _PreflightFinished(Exception):
    pass


@pytest.mark.parametrize("mode", ["full", "pruned", "staged"])
@pytest.mark.parametrize("change", ["geometry", "section", "declarations"])
def test_price_order_valid_loaded_layouts_finish_pure_preflight(
    mode, change, tmp_path, monkeypatch, no_execution
):
    before = _raw("v2")
    changed = deepcopy(before)
    if change == "geometry":
        changed["nodes"][-1]["coordinates"][1] *= 1.1
        for node in changed["nodes"]:
            node["coordinates"][0] += 10
            node["coordinates"][1] -= 20
    else:
        changed["sections"][0]["width_m"] *= 1.1
    if change == "declarations":
        changed["nodes"][:3] = [
            changed["nodes"][2],
            changed["nodes"][0],
            changed["nodes"][1],
        ]
        _rename_nodes(
            changed,
            {"N1": "fixed-renamed", "N3": "interior-renamed", "N4": "control-renamed"},
        )
    baseline, alternative, request = _model(before), _model(changed), _request("v2")
    descriptors_before = [
        study._bytes(control_layout_candidate_features(model, request))
        for model in (baseline, alternative)
    ]
    input_bytes = [
        study._bytes(model.canonical_payload()) for model in (baseline, alternative)
    ]
    request_bytes = study._bytes(request.to_dict())
    output = tmp_path / "must-not-exist"
    reached = []

    def stop_before_creation(path, *args, **kwargs):
        assert path == output
        reached.append(path)
        raise _PreflightFinished

    monkeypatch.setattr(search.Path, "mkdir", stop_before_creation)
    with pytest.raises(_PreflightFinished):
        _run(mode, baseline, alternative, request, output)
    assert reached == [output]
    assert not output.exists()
    assert no_execution == []
    assert request_bytes == study._bytes(request.to_dict())
    assert input_bytes == [
        study._bytes(model.canonical_payload()) for model in (baseline, alternative)
    ]
    assert descriptors_before == [
        study._bytes(control_layout_candidate_features(model, request))
        for model in (baseline, alternative)
    ]


@pytest.mark.parametrize("profile", ["v1", "v2", "v3"])
def test_price_order_binding_keeps_component_and_exact_load_values(profile):
    model, request = _model(_raw(profile)), _request(profile)
    original = search._price_order_control_binding(model, request)
    different_component = replace(
        request, control_global_dof=request.control_global_dof - 1
    )
    assert search._price_order_control_binding(model, different_component) != original
    if profile == "v2":
        different_load = replace(
            request, constant_nodal_loads=(("N2", 0.0, -0.0100000000001, 0.0),)
        )
        assert search._price_order_control_binding(model, different_load) != original


@pytest.mark.parametrize("mode", ["full", "pruned", "staged"])
@pytest.mark.parametrize("missing", ["control", "preload"])
def test_price_order_rejects_unresolved_binding_before_output(
    mode, missing, tmp_path, no_execution
):
    raw = _raw()
    alternative = deepcopy(raw)
    alternative["sections"][0]["width_m"] *= 1.1
    request = (
        replace(_request(), control_global_dof=13)
        if missing == "control"
        else replace(_request(), constant_nodal_loads=(("missing", 0.0, -0.01, 0.0),))
    )
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match=f"{missing} node is outside the model"):
        _run(mode, _model(raw), _model(alternative), request, output)
    assert not output.exists()
    assert no_execution == []
