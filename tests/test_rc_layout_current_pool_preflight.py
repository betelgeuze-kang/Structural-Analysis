"""Current-pool admission for learned/combined layout routes; never fit or solve."""

import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_layout_learning as learning
from structural_analysis.benchmark import rc_control_layout_search as search
from structural_analysis.benchmark.rc_control_layout_features import (
    LAYOUT_FEATURE_NAMES,
    control_layout_candidate_features,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ROUTES = ("combined", "learned_full", "learned_pruned", "learned_staged")
DRIFTS = (
    "v1_control_section",
    "v1_control_geometry",
    "v2_preload_section",
    "v3_control_section",
)


def _retained():
    files = json.loads(
        gzip.decompress(
            Path("tests/frontend/fixtures/rc-layout-search.json.gz").read_bytes()
        )
    )["files"]
    return {key: base64.b64decode(value) for key, value in files.items()}


def _raw(profile):
    raw = json.loads(_retained()["pool/baseline.json"])
    if profile == "v1":
        return raw
    raw["nodes"].append({"id": "N4", "coordinates": [2.5, 3.0, 0.0]})
    raw["elements"].append(
        {**deepcopy(raw["elements"][-1]), "id": "M3", "nodes": ["N3", "N4"]}
    )
    if profile == "v2":
        raw["loads"][0]["node"] = "N4"
    else:
        raw["supports"].append({"node": "N4", "dofs": ["UX", "UY", "RZ"]})
    return raw


def _request(profile):
    if profile == "v1":
        return decode_bounded_rc_fiber_direct_control_request(
            study._bytes(json.loads(_retained()["plan.json"])["control_request"])
        )
    return BoundedRCFiberDirectControlRequest(
        10 if profile == "v2" else 7,
        (-1e-5, -2e-5),
        constant_nodal_loads=(("N2", 0.0, -0.01, 0.0),) if profile == "v2" else (),
        experimental_two_fixed_endpoints=profile == "v3",
    )


def _model(raw):
    return load_neutral_json_bytes(study._bytes(raw))


def _rename(raw, names):
    for node in raw["nodes"]:
        node["id"] = names.get(node["id"], node["id"])
    for member in raw["elements"]:
        member["nodes"] = [names.get(node, node) for node in member["nodes"]]
    for row in [*raw["loads"], *raw["supports"]]:
        row["node"] = names.get(row["node"], row["node"])


def _policy(profile, baseline, request):
    """Load a real retained contract or construct a synthetic admission contract.

    The synthetic profile is solely test input: zero weights and zero declared
    work do not represent historical training, labels or benefit measurements.
    Actual policy constructor and report admission remain fully enabled.
    """
    if profile == "v1":
        files = _retained()
        policy = learning.RCControlLayoutPolicy(files["policy.json"].decode())
        report = json.loads(files["historical-training.json"])
        assert policy._json.encode() == files["policy.json"]
    else:
        n, targets = len(LAYOUT_FEATURE_NAMES), len(learning.TARGETS)
        payload = {
            "schema_version": learning.POLICY_SCHEMA,
            "context_hash": control_layout_candidate_features(baseline, request)[
                "context_hash"
            ],
            "features": list(LAYOUT_FEATURE_NAMES),
            "targets": list(learning.TARGETS),
            "mean": [0.0] * n,
            "scale": [1.0] * n,
            "minimum": [-1e6] * n,
            "maximum": [1e6] * n,
            "target_scale": [1.0] * targets,
            "weights": [[0.0] * targets for _ in range(n + 1)],
            "ridge": 1.0,
            "ood_margin": 0.1,
            "training_model_identities": ["sha256:" + h * 64 for h in ("1", "2")],
            "training_sample_hashes": ["sha256:" + h * 64 for h in ("3", "4")],
            "label_comparison_hash": "sha256:" + "5" * 64,
        }
        payload["policy_hash"] = study._sha(study._bytes(payload))
        policy = learning.RCControlLayoutPolicy(study._bytes(payload).decode())
        report = {
            "schema_version": "experimental-rc-control-layout-training.v1",
            "synthetic_admission_test_only": True,
            "labels_report_hash": payload["label_comparison_hash"],
            "policy": {
                "path": "synthetic-policy.json",
                "sha256": study._sha(study._bytes(policy.to_dict())),
                "byte_length": len(study._bytes(policy.to_dict())),
            },
            "sample_count": 2,
            "fit": {
                "status": "completed",
                "unknown_fit_work_until_outcome": False,
                "wall_ns": 0,
            },
            "label_invocations": [
                {
                    "phase": phase,
                    "status": "returned",
                    "unknown_execution_work": False,
                    "wall_ns": 0,
                    "process_cpu_ns": 0,
                    "work": {
                        "attempted_step_count": 0,
                        "known_linear_solve_count": 0,
                        "known_newton_iteration_count": 0,
                        "unknown_solver_work_attempt_count": 0,
                    },
                }
                for phase in ("analysis", "verification") * 2
            ],
            "wall_ns": 0,
            "cpu_ns": 0,
            "label_generation_wall_ns": 0,
        }
        report["report_hash"] = study._sha(study._bytes(report))
    assert type(policy) is learning.RCControlLayoutPolicy
    assert search._training_cost(policy, report) == report
    assert (
        policy.to_dict()["context_hash"]
        == control_layout_candidate_features(baseline, request)["context_hash"]
    )
    return policy, report


def _inputs(change):
    profile = change[:2]
    before = _raw(profile)
    changed = deepcopy(before)
    if change == "v1_control_geometry":
        changed["nodes"][-1]["coordinates"][1] *= 1.1
    else:
        changed["sections"][0]["width_m"] *= 1.1
    if profile == "v2":
        _rename(changed, {"N2": "N3", "N3": "N2"})
    else:
        changed["nodes"][1], changed["nodes"][2] = (
            changed["nodes"][2],
            changed["nodes"][1],
        )
    baseline, alternative, request = _model(before), _model(changed), _request(profile)
    descriptors = [
        control_layout_candidate_features(m, request) for m in (baseline, alternative)
    ]
    assert descriptors[0]["context_hash"] == descriptors[1]["context_hash"]
    assert (
        descriptors[0]["physical_model_identity"]
        != descriptors[1]["physical_model_identity"]
    )
    assert search._price_order_control_binding(
        baseline, request
    ) != search._price_order_control_binding(alternative, request)
    policy, report = _policy(profile, baseline, request)
    return baseline, alternative, request, policy, report


def _run(route, baseline, candidates, request, policy, report, output):
    functions = {
        "combined": search.compare_control_layout_search,
        "learned_full": search.run_control_layout_strategy,
        "learned_pruned": search.run_control_layout_cost_pruned_strategy,
        "learned_staged": search.run_control_layout_staged_strategy,
    }
    return functions[route](
        baseline,
        candidates,
        request,
        policy=policy,
        training_report=report,
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-10-02", "synthetic current-pool admission only"
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
        output_directory=output,
        full_analysis_budget=2,
        **({"strategy": "learned_order"} if route != "combined" else {}),
        **({"prefix_target_count": 1} if route == "learned_staged" else {}),
    )


@pytest.fixture
def no_execution(monkeypatch):
    calls = {"prediction": [], "execution": []}
    original_predict = learning.RCControlLayoutPolicy.predict

    def predict(self, model, request):
        calls["prediction"].append(model)
        return original_predict(self, model, request)

    def forbidden(*args, **kwargs):
        calls["execution"].append("forbidden")
        raise AssertionError("no solver, fit, output directory or artifact writes")

    monkeypatch.setattr(learning.RCControlLayoutPolicy, "predict", predict)
    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(study, "_save", forbidden)
    monkeypatch.setattr(search.Path, "mkdir", forbidden)
    monkeypatch.setattr(learning, "train_control_layout_policy", forbidden)
    monkeypatch.setattr(learning, "generate_control_layout_training_labels", forbidden)
    monkeypatch.setattr(learning, "_candidate_fit_parameters", forbidden)
    return calls


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("change", DRIFTS)
def test_current_pool_rejects_binding_drift_before_prediction_or_output(
    route, change, tmp_path, no_execution
):
    baseline, alternative, request, policy, report = _inputs(change)
    frozen = policy._json
    report_bytes = study._bytes(report)
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="physical control/preload binding mismatch"):
        _run(
            route,
            baseline,
            (search.RCControlLayoutCandidate("drift", alternative),),
            request,
            policy,
            report,
            output,
        )
    assert not output.exists()
    assert no_execution == {"prediction": [], "execution": []}
    assert policy._json == frozen
    assert study._bytes(report) == report_bytes


@pytest.mark.parametrize("route", ROUTES)
def test_current_pool_checks_even_alternative_beyond_shortlist_budget(
    route, tmp_path, no_execution
):
    baseline, drift, request, policy, report = _inputs("v1_control_section")
    valid_raw = _raw("v1")
    valid_raw["sections"][0]["width_m"] *= 0.9
    valid = _model(valid_raw)
    candidates = (
        search.RCControlLayoutCandidate("cheap_valid", valid),
        search.RCControlLayoutCandidate("expensive_drift", drift),
    )
    assert (
        design.calculate_fiber_frame_member_quantities(valid)["totals"][
            "gross_concrete_volume_m3"
        ]
        < design.calculate_fiber_frame_member_quantities(drift)["totals"][
            "gross_concrete_volume_m3"
        ]
    )
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="physical control/preload binding mismatch"):
        _run(route, baseline, candidates, request, policy, report, output)
    assert not output.exists()
    assert no_execution == {"prediction": [], "execution": []}


class _PreflightFinished(Exception):
    pass


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "change",
    ["v1_geometry", "v1_declarations", "v2_geometry", "v2_declarations", "v3_geometry"],
)
def test_valid_current_pool_completes_admission_without_changing_contract_bytes(
    route, change, tmp_path, monkeypatch, no_execution
):
    profile = change[:2]
    before = _raw(profile)
    changed = deepcopy(before)
    if change.endswith("geometry"):
        changed["nodes"][-1]["coordinates"][1] *= 1.1
        for node in changed["nodes"]:
            node["coordinates"][0] += 10
            node["coordinates"][1] -= 20
    else:
        changed["sections"][0]["width_m"] *= 1.1
        control_index = _request(profile).control_global_dof // 3
        others = [i for i in range(len(changed["nodes"])) if i != control_index]
        rotated = [changed["nodes"][i] for i in others[1:] + others[:1]]
        for i, node in zip(others, rotated, strict=True):
            changed["nodes"][i] = node
        _rename(
            changed,
            {
                "N1": "fixed-renamed",
                "N3": "control-or-interior-renamed",
                "N4": "control-renamed",
            },
        )
    baseline, alternative, request = _model(before), _model(changed), _request(profile)
    policy, report = _policy(profile, baseline, request)
    descriptors = [
        study._bytes(control_layout_candidate_features(m, request))
        for m in (baseline, alternative)
    ]
    assert (
        json.loads(descriptors[0])["context_hash"]
        == json.loads(descriptors[1])["context_hash"]
    )
    assert search._price_order_control_binding(
        baseline, request
    ) == search._price_order_control_binding(alternative, request)
    inputs = [study._bytes(m.canonical_payload()) for m in (baseline, alternative)]
    request_bytes, report_bytes, frozen = (
        study._bytes(request.to_dict()),
        study._bytes(report),
        policy._json,
    )
    output = tmp_path / "must-not-exist"
    reached = []

    def stop_before_creation(path, *args, **kwargs):
        assert path == output
        reached.append(path)
        raise _PreflightFinished

    monkeypatch.setattr(search.Path, "mkdir", stop_before_creation)
    with pytest.raises(_PreflightFinished):
        _run(
            route,
            baseline,
            (search.RCControlLayoutCandidate("valid", alternative),),
            request,
            policy,
            report,
            output,
        )
    assert reached == [output]
    assert not output.exists()
    assert len(no_execution["prediction"]) == 1
    assert no_execution["execution"] == []
    assert policy._json == frozen
    assert study._bytes(report) == report_bytes
    assert study._bytes(request.to_dict()) == request_bytes
    assert [
        study._bytes(m.canonical_payload()) for m in (baseline, alternative)
    ] == inputs
    assert [
        study._bytes(control_layout_candidate_features(m, request))
        for m in (baseline, alternative)
    ] == descriptors
