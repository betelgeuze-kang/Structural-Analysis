"""Original RC direct-control source and detached artifact integration.

The module fixtures retain every original core return before assertions. Their
materials and fixed targets are not tuned by the tests. Artifact validation is
a fresh numerical invocation and is counted separately from fixture generation.
No public monotonic J1-J5 analysis or independent physical benchmark is invoked.
"""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as monotonic_api
from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig as Config,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import (
    load_neutral_json,
    load_neutral_json_bytes,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


REPO = Path(__file__).resolve().parents[1]
MODEL = REPO / "examples/public_rc_fiber_frame_l_frame_material_history.json"
SMALL_TARGETS = (-1.0e-6, -2.0e-6, -1.5e-6)
# Exact prescribed refined prefix[:15], followed by one unloading target.
PLASTIC_TARGETS = (
    -0.0004,
    -0.0008,
    -0.0012000000000000001,
    -0.0016,
    -0.002,
    -0.0024000000000000002,
    -0.0028,
    -0.0032,
    -0.0036,
    -0.004,
    -0.0044,
    -0.0048000000000000004,
    -0.0052,
    -0.0056,
    -0.006,
    -0.0056,
)
OPTIONS = dict(
    control_global_dof=7,
    allow_reversals=True,
    maximum_reversals=1,
    maximum_targets=255,
)
_DEFAULT = object()


def _bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _forbid(*args, **kwargs):
    pytest.fail("unexpected numerical invocation at a guarded boundary")


def _sources():
    return {
        str(path.relative_to(REPO)): _sha(path.read_bytes())
        for path in (
            Path(api.__file__),
            Path(paths.__file__),
            REPO
            / "src/structural_analysis/assembly/stateful_fiber_frame2d_displacement_control.py",
            REPO / "src/structural_analysis/assembly/stateful_fiber_frame2d.py",
        )
    }


def _capture(directory, name, model, targets, *, restart=None, **overrides):
    """Run one declared invocation and preserve its actual calls on failure too."""
    destination = directory / name
    destination.mkdir()
    before = _sources()
    calls = []
    recoveries = []
    options = OPTIONS | overrides
    original = paths.solve_stateful_fiber_frame2d_displacement_control_step
    original_assembly = api.assemble_stateful_fiber_frame2d
    original_path = api.run_stateful_fiber_frame2d_control_path
    retained_paths = []

    def observed_path(*args, **kwargs):
        result = original_path(*args, **kwargs)
        retained_paths.append(result)
        return result

    def observed_recovery(problem, parent, **kwargs):
        entry = {
            "parent": parent.to_dict(),
            "target_load_factor": kwargs["target_load_factor"],
            "coordinates": np.asarray(kwargs["trial_free_coordinates_m"]).tolist(),
        }
        recoveries.append(entry)
        fresh = original_assembly(problem, parent, **kwargs)
        entry["assembly"] = fresh.to_dict()
        entry["parent_after"] = parent.to_dict()
        return fresh

    def observed(*args, **kwargs):
        entry = {
            "target_m": kwargs["target_control_displacement_m"],
            "parent_before": args[1].to_dict(),
        }
        calls.append(entry)
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            entry["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        entry["step"] = result.to_dict()
        entry["parent_after"] = args[1].to_dict()
        (destination / f"core-{len(calls) - 1:03d}.json").write_bytes(_bytes(entry))
        return result

    (destination / "request.json").write_bytes(
        _bytes(
            {
                "targets_m": list(targets),
                "options": {
                    k: v.to_manifest() if k == "config" else v
                    for k, v in options.items()
                },
                "restart_sha256": None if restart is None else _sha(restart),
            }
        )
    )
    if restart is not None:
        (destination / "input-restart.json").write_bytes(restart)
    started = time.perf_counter()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(monotonic_api, "analyze_public_rc_fiber_frame", _forbid)
            patch.setattr(
                paths,
                "solve_stateful_fiber_frame2d_displacement_control_step",
                observed,
            )
            patch.setattr(api, "assemble_stateful_fiber_frame2d", observed_recovery)
            patch.setattr(api, "run_stateful_fiber_frame2d_control_path", observed_path)
            result = api.analyze_bounded_rc_fiber_direct_control(
                model, targets, restart=restart, **options
            )
        encoded = result.result_artifact_bytes()
        (destination / "result.json").write_bytes(encoded)
        try:
            checkpoint = result.checkpoint_artifact_bytes()
        except ValueError:
            checkpoint = None
        if checkpoint is not None:
            (destination / "checkpoint.json").write_bytes(checkpoint)
        return SimpleNamespace(
            result=result,
            payload=result.to_dict(),
            encoded=encoded,
            checkpoint=checkpoint,
            calls=calls,
            recoveries=recoveries,
            path=retained_paths[0] if retained_paths else None,
            directory=destination,
            model=model,
            targets=targets,
            options=options,
            restart=restart,
        )
    finally:
        after = _sources()
        (destination / "receipt.json").write_bytes(
            _bytes(
                {
                    "actual_core_calls": len(calls),
                    "calls": calls,
                    "recoveries": recoveries,
                    "source_before": before,
                    "source_after": after,
                    "source_unchanged": before == after,
                    "wall_seconds_including_capture": time.perf_counter() - started,
                    "scope": "development correctness; instrumentation included; no performance comparison",
                }
            )
        )
        assert before == after


def _saved_fixture(name, model, targets, *, restart=None, **overrides):
    """Optional local rerun reuse; defaults still create every actual CI fixture.

    Exact source hashes must still match. The saved material fixture is not
    relabeled as a new execution, and original files are never modified.
    """
    base = os.environ.get("STRUCTURAL_RC_CONTROL_API_TEST_ARTIFACTS")
    if not base:
        return None
    directory = Path(base) / name
    receipt = json.loads((directory / "receipt.json").read_bytes())
    assert receipt["source_before"] == receipt["source_after"] == _sources()
    assert (directory.parent / "model.json").read_bytes() == MODEL.read_bytes()
    encoded = (directory / "result.json").read_bytes()
    checkpoint_file = directory / "checkpoint.json"
    checkpoint = checkpoint_file.read_bytes() if checkpoint_file.exists() else None
    result = api.BoundedRCFiberDirectControlResult(encoded, checkpoint)
    options = OPTIONS | overrides
    assert result.to_dict()["request"]["targets_m"] == list(targets)
    assert result.to_dict()["request"]["restart_input_sha256"] == (
        None if restart is None else _sha(restart)
    )
    print(f"Reusing retained original fixture without solve: {directory}", flush=True)
    return SimpleNamespace(
        result=result,
        payload=result.to_dict(),
        encoded=encoded,
        checkpoint=checkpoint,
        calls=receipt["calls"],
        recoveries=receipt["recoveries"],
        path=None,
        directory=directory,
        model=model,
        targets=targets,
        options=options,
        restart=restart,
    )


@pytest.fixture(scope="module")
def retained():
    directory = Path(tempfile.mkdtemp(prefix="structural-rc-control-api-tests-"))
    (directory / "model.json").write_bytes(MODEL.read_bytes())
    print(f"\nRetained RC direct-control API artifacts: {directory}", flush=True)
    return directory


@pytest.fixture(scope="module")
def model():
    return load_neutral_json(MODEL)


@pytest.fixture(scope="module")
def small(retained, model):
    full = _capture(retained, "small-full", model, SMALL_TARGETS)
    assert full.result.status == "ready" and len(full.calls) == 3
    saved_full = _saved_fixture("small-full", model, SMALL_TARGETS)
    if saved_full is not None:
        assert saved_full.encoded == full.encoded
        assert saved_full.checkpoint == full.checkpoint
    prefix = _saved_fixture("small-prefix", model, SMALL_TARGETS[:1]) or _capture(
        retained, "small-prefix", model, SMALL_TARGETS[:1]
    )
    assert prefix.result.status == "ready" and len(prefix.calls) == 1
    resumed = _saved_fixture(
        "small-resumed", model, SMALL_TARGETS[1:], restart=prefix.checkpoint
    ) or _capture(
        retained, "small-resumed", model, SMALL_TARGETS[1:], restart=prefix.checkpoint
    )
    assert resumed.result.status == "ready" and len(resumed.calls) == 3
    return SimpleNamespace(full=full, prefix=prefix, resumed=resumed)


@pytest.fixture(scope="module")
def plastic(retained, model):
    result = _saved_fixture(
        "plastic-prefix-and-unload", model, PLASTIC_TARGETS
    ) or _capture(retained, "plastic-prefix-and-unload", model, PLASTIC_TARGETS)
    assert result.result.status == "ready" and len(result.calls) == 16
    return result


@pytest.fixture(autouse=True)
def no_legacy_public_analysis(monkeypatch):
    monkeypatch.setattr(monotonic_api, "analyze_public_rc_fiber_frame", _forbid)


def _validate(fixture, *, result=_DEFAULT, checkpoint=_DEFAULT, **overrides):
    return api.validate_bounded_rc_fiber_direct_control_artifacts(
        fixture.model,
        fixture.targets,
        result=fixture.encoded if result is _DEFAULT else result,
        checkpoint=fixture.checkpoint if checkpoint is _DEFAULT else checkpoint,
        restart=fixture.restart,
        **(fixture.options | overrides),
    )


def _count_original_calls(monkeypatch):
    observed = []
    original = paths.solve_stateful_fiber_frame2d_displacement_control_step

    def counted(*args, **kwargs):
        observed.append(kwargs["target_control_displacement_m"])
        return original(*args, **kwargs)

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", counted
    )
    return observed


def test_actual_small_full_and_restart_keep_all_original_core_returns(small):
    assert small.full.result.contract_pass is small.resumed.result.contract_pass is True
    assert small.full.checkpoint == small.resumed.checkpoint
    assert [v["target_m"] for v in small.resumed.calls] == list(SMALL_TARGETS)
    for full, resumed in zip(small.full.calls, small.resumed.calls, strict=True):
        assert _bytes(full["step"]) == _bytes(resumed["step"])
        assert _bytes(full["parent_before"]) == _bytes(full["parent_after"])
        assert _bytes(resumed["parent_before"]) == _bytes(resumed["parent_after"])


def test_result_exports_are_detached_and_local_serialization_does_not_solve(
    small, monkeypatch
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    original = small.full.result.result_artifact_bytes()
    decoded = small.full.result.to_dict()
    decoded.clear()
    assert small.full.result.result_artifact_bytes() == original == small.full.encoded
    assert _bytes(small.full.result.to_dict()) == original
    assert json.loads(original)["result_hash"] == small.full.result.result_hash
    assert isinstance(small.full.result.checkpoint_artifact_bytes(), bytes)


@pytest.mark.parametrize("which", ["full", "resumed"])
def test_explicit_artifact_validation_reexecutes_original_requested_source(
    small, monkeypatch, which
):
    fixture = getattr(small, which)
    observed = _count_original_calls(monkeypatch)
    report = _validate(fixture)
    assert observed == list(SMALL_TARGETS)
    assert report.artifact_contract_pass is True
    assert report.contract_pass is True
    assert report.status == "valid_artifact"
    assert report.to_dict()["artifact_contract_pass"] is True
    assert (
        report.to_dict()["replay_control_work"]
        == fixture.payload["metrics"]["control_work"]
    )
    assert report.to_dict()["response_reassembly_attempts"] == 3
    assert report.to_dict()["response_reassembly_verified_count"] == 3


def test_fixed_material_fixture_has_committed_plastic_memory_and_preserved_unload(
    plastic,
):
    checkpoints = [v["step"]["accepted_checkpoint"] for v in plastic.calls]

    def steel(cp):
        return [
            f["accumulated_plastic_strain"]
            for e in cp["element_states"]
            for s in e["integration_point_states"]
            for f in s["fiber_states"]
            if "accumulated_plastic_strain" in f
        ]

    assert len(steel(checkpoints[-1])) == 12
    assert all(max(steel(cp)) == 0 for cp in checkpoints[:14])
    assert max(steel(checkpoints[14])) == pytest.approx(7.86764100277988e-6, rel=1e-12)
    np.testing.assert_allclose(
        steel(checkpoints[15]), steel(checkpoints[14]), rtol=0, atol=1e-15
    )
    assert checkpoints[15]["parent_state_hash"] == checkpoints[14]["state_hash"]
    assert checkpoints[15]["global_displacements"][7] == pytest.approx(
        -0.0056, abs=1e-12
    )


@pytest.mark.parametrize(
    "target", [True, float("nan"), float("inf"), 10**1000, "-.001"]
)
def test_invalid_target_rejects_before_original_solver(model, monkeypatch, target):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises((TypeError, ValueError)):
        api.analyze_bounded_rc_fiber_direct_control(model, [target], **OPTIONS)


@pytest.mark.parametrize("dof", [True, -1, 0, 2, 8, 100])
def test_invalid_or_fixed_control_rejects_before_original_solver(
    model, monkeypatch, dof
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises((TypeError, ValueError)):
        api.analyze_bounded_rc_fiber_direct_control(
            model, [-1e-6], **(OPTIONS | {"control_global_dof": dof})
        )


@pytest.mark.parametrize(
    "targets", [[], [0.0], [-1e-6, -1e-6], [-1e-6, -2e-6, -1.5e-6]]
)
def test_whole_authored_target_preflight_does_not_partially_solve(
    model, monkeypatch, targets
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises((TypeError, ValueError)):
        api.analyze_bounded_rc_fiber_direct_control(
            model, targets, control_global_dof=7
        )


def test_original_material_and_model_are_not_changed_by_analysis(small):
    assert (
        MODEL.read_bytes() == (small.full.directory.parent / "model.json").read_bytes()
    )
    payload = json.loads(MODEL.read_bytes())
    steel, concrete = payload["materials"]
    assert steel["yield_stress_mpa"] == 250.0
    assert concrete["tensile_strength_mpa"] == 3.0
    assert concrete["compressive_strength_mpa"] == 30.0
    assert payload["sections"][0]["concrete_layer_count"] == 12


def test_unsupported_model_is_not_an_attempted_numerical_failure(model, monkeypatch):
    payload = json.loads(MODEL.read_bytes())
    payload["elements"][0]["release_i"] = ["RZ"]
    unsupported_model = load_neutral_json_bytes(_bytes(payload))
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        unsupported_model, [-1e-6], **OPTIONS
    )
    assert result.status == "unsupported"
    assert result.contract_pass is False
    assert result.to_dict()["unsupported_features"]
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


@pytest.mark.parametrize(
    "overrides",
    [
        {"config": {}},
        {"config": False},
        {"allow_reversals": 1},
        {"maximum_reversals": True},
        {"maximum_reversals": -1},
        {"maximum_targets": True},
        {"maximum_targets": 0},
        {"maximum_targets": 256},
        {"maximum_targets": 1},
    ],
)
def test_request_options_and_budget_reject_before_any_partial_solve(
    model, monkeypatch, overrides
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises((TypeError, ValueError)):
        api.analyze_bounded_rc_fiber_direct_control(
            model, SMALL_TARGETS[:2], **(OPTIONS | overrides)
        )


@pytest.mark.parametrize("restart", [{}, "{}", True, b"not json"])
def test_invalid_restart_cannot_enter_original_solver(model, monkeypatch, restart):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    try:
        result = api.analyze_bounded_rc_fiber_direct_control(
            model, SMALL_TARGETS[:1], restart=restart, **OPTIONS
        )
    except (TypeError, ValueError):
        return
    # Structured core restart errors may be preserved as an invalid execution
    # envelope. They must not become a ready source or invent an attempted call.
    assert result.status == "invalid_execution"
    assert result.contract_pass is False
    assert result.to_dict()["failure"] is not None
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


@pytest.fixture(scope="module")
def blocked(retained, model):
    result = _saved_fixture(
        "zero-iteration-blocked",
        model,
        SMALL_TARGETS,
        config=Config(newton=NewtonRaphsonConfig(max_iterations=0)),
    ) or _capture(
        retained,
        "zero-iteration-blocked",
        model,
        SMALL_TARGETS,
        config=Config(newton=NewtonRaphsonConfig(max_iterations=0)),
    )
    assert result.result.status == "blocked"
    assert len(result.calls) == 1
    return result


def test_actual_zero_iteration_budget_failure_is_retained_with_unknown_work(blocked):
    assert blocked.result.contract_pass is False
    call = blocked.calls[0]
    assert call["step"]["committed"] is False
    assert call["step"]["metrics"]["rollback_exact"] is True
    assert _bytes(call["parent_before"]) == _bytes(call["parent_after"])
    assert _bytes(call["step"]["accepted_checkpoint"]) == _bytes(call["parent_before"])
    assert "iteration_count" not in call["step"]["trial_solution"]["metrics"]
    assert blocked.payload["metrics"]["control_work"] == {
        "attempted_step_count": 1,
        "known_linear_solve_count": 0,
        "known_newton_iteration_count": 0,
        "unknown_solver_work_attempt_count": 1,
    }


def test_consistent_blocked_artifacts_are_not_physical_success(blocked, monkeypatch):
    observed = _count_original_calls(monkeypatch)
    report = _validate(blocked)
    assert observed == [SMALL_TARGETS[0]]
    assert report.artifact_contract_pass is True
    assert report.contract_pass is False
    assert report.status == "valid_artifact"
    assert report.to_dict()["physical_path_complete"] is False
    assert report.to_dict()["replay_control_work"]["attempted_step_count"] == 1


def _assert_original_responses(fixture):
    payload = fixture.result.to_dict()
    history = payload["response_history"]
    accepted = [c["step"] for c in fixture.calls if c["step"]["committed"]]
    assert len(history) == len(accepted) == len(fixture.recoveries)
    assert payload["terminal_response"] == history[-1]
    assert payload["metrics"]["response_reassembly_attempts"] == len(accepted)
    assert payload["metrics"]["response_reassembly_verified_count"] == len(accepted)
    assert payload["metrics"]["whole_accepted_history_recovered"] is True
    for epoch, (step, replay, row) in enumerate(
        zip(accepted, fixture.recoveries, history, strict=True), 1
    ):
        assembly = step["trial_assembly"]
        child = step["accepted_checkpoint"]
        z = step["trial_solution"]["augmented_coordinates_m"]
        assert _bytes(replay["parent"]) == _bytes(step["parent_checkpoint"])
        assert _bytes(replay["parent"]) == _bytes(replay["parent_after"])
        assert _bytes(replay["coordinates"]) == _bytes(z[:-1])
        assert replay["target_load_factor"] == child["load_factor"] == z[-1] / 0.001
        assert _bytes(replay["assembly"]) == _bytes(assembly)
        assert row["epoch"] == row["step_index"] == child["epoch"] == epoch
        assert row["checkpoint_hash"] == child["state_hash"]
        assert row["parent_checkpoint_hash"] == child["parent_state_hash"]
        assert row["source_step_hash"] == step["step_hash"]
        assert row["replayed_assembly_hash"] == _sha(_bytes(assembly))
        assert row["material_point_count"] == len(row["fiber_results"]) == 84
        assert len(row["section_results"]) == 6
        assert len(row["member_end_forces"]) == 2
        for index, node in enumerate(row["node_displacements"]):
            q = assembly["global_displacements"][3 * index : 3 * index + 3]
            assert node["node_id"] == f"N{index + 1}"
            assert [node[k] for k in ("UX_m", "UY_m", "RZ_rad")] == q
            assert [node[k] for k in ("UZ_m", "RX_rad", "RY_rad")] == [0.0] * 3
        for reaction, dof in zip(row["support_reactions"], (0, 1, 2), strict=True):
            assert reaction["node_id"] == "N1"
            assert reaction["unit"] == ("N*m" if dof == 2 else "N")
            assert reaction["value_si"] == assembly["reactions_global"][dof] * 1000.0
        for mi, member in enumerate(row["member_end_forces"]):
            response = assembly["member_assemblies"][mi]["element_response"]
            assert member["member_id"] == f"M{mi + 1}"
            actual = [
                member[end][key]
                for end in ("local_end_i", "local_end_j")
                for key in ("FX_N", "FY_N", "MZ_Nm")
            ]
            assert actual == [x * 1000.0 for x in response["internal_force_local"]]
            assert member["dissipated_energy_MJ"] == response["dissipated_energy_mj"]
            for ip, source in enumerate(response["section_responses"]):
                section = row["section_results"][mi * 3 + ip]
                assert (
                    section["axial_force_N"]
                    == source["resultants"]["axial_force_kn"] * 1000.0
                )
                assert (
                    section["moment_z_Nm"]
                    == source["resultants"]["moment_z_kn_m"] * 1000.0
                )
                assert (
                    section["dissipated_energy_MJ_per_m"]
                    == source["dissipated_energy_mj_per_m"]
                )
                assert (
                    section["section_state_hash"] == source["trial_state"]["state_hash"]
                )
                for fi, native in enumerate(source["trial_state"]["fiber_states"]):
                    fiber = row["fiber_results"][(mi * 3 + ip) * 14 + fi]
                    assert fiber["member_id"] == member["member_id"]
                    assert (
                        fiber["integration_point_index"] == ip
                        and fiber["fiber_index"] == fi
                    )
                    assert fiber["strain"] == source["fiber_strains"][fi]
                    assert fiber["stress_MPa"] == source["fiber_stresses_mpa"][fi]
                    assert _bytes(fiber["material_state"]) == _bytes(native)
                    assert (
                        fiber["dissipated_energy_density_MJ_per_m3"]
                        == native["dissipated_energy_density_mj_per_m3"]
                    )


def test_small_original_previous_parent_coordinates_and_all_si_rows(small):
    _assert_original_responses(small.full)
    _assert_original_responses(small.resumed)
    assert _bytes(small.full.payload["response_history"]) == _bytes(
        small.resumed.payload["response_history"]
    )
    assert small.resumed.payload["path"]["metrics"]["prefix_replayed_step_count"] == 1
    assert small.resumed.payload["path"]["metrics"]["accepted_target_count"] == 2
    assert (
        small.resumed.payload["path"]["metrics"]["cumulative_accepted_target_count"]
        == 3
    )


def test_plastic_original_previous_parent_recovery_and_native_material_rows(plastic):
    _assert_original_responses(plastic)
    history = plastic.payload["response_history"]
    assert (
        max(
            f["material_state"].get("accumulated_plastic_strain", 0)
            for f in history[14]["fiber_results"]
        )
        > 0
    )
    assert (
        max(
            f["material_state"].get("tensile_damage", 0)
            for f in history[14]["fiber_results"]
        )
        > 0
    )
    assert plastic.payload["path"]["accepted_reversal_count"] == 1


def test_experimental_scope_cannot_inherit_public_or_independent_authority(
    small, blocked
):
    for fixture in (small.full, small.resumed, blocked):
        claims = fixture.payload["claims"]
        assert claims["experimental_small_displacement_rc_control"] is True
        assert all(
            value is False
            for key, value in claims.items()
            if key != "experimental_small_displacement_rc_control"
        )
        assert (
            fixture.payload["metrics"]["explicit_validation_solver_replay_performed"]
            is False
        )
        assert (
            fixture.payload["metrics"]["response_history_scope"]
            == "cumulative_accepted_prefix"
        )


def _stub_expected_source(fixture, monkeypatch):
    """Saved-source boundary stub. Actual solver replay is tested separately."""
    invocations = []

    def regenerate(model, targets, **kwargs):
        invocations.append((model, tuple(targets), kwargs))
        return fixture.result

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", regenerate)
    return invocations


def _reseal(payload):
    payload["result_hash"] = _sha(
        _bytes({k: v for k, v in payload.items() if k != "result_hash"})
    )
    return _bytes(payload)


def _set_path(payload, path, value):
    current = payload
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


@pytest.mark.parametrize(
    "path,value",
    [
        (("response_history", 0, "node_displacements", 1, "UX_m"), 0.25),
        (("response_history", 0, "node_displacements", 0, "UZ_m"), -0.0),
        (("response_history", 0, "support_reactions", 0, "value_si"), 123.0),
        (("response_history", 0, "member_end_forces", 0, "local_end_i", "FX_N"), 123.0),
        (("response_history", 0, "section_results", 0, "axial_force_N"), 123.0),
        (("response_history", 0, "fiber_results", 0, "stress_MPa"), 123.0),
        (
            (
                "response_history",
                0,
                "fiber_results",
                12,
                "material_state",
                "accumulated_plastic_strain",
            ),
            0.25,
        ),
        (("response_history", 0, "parent_checkpoint_hash"), "sha256:" + "f" * 64),
        (("response_history", 0, "source_step_hash"), "sha256:" + "f" * 64),
        (("claims", "public_j1_j5_authority"), True),
        (("claims", "independent_physical_validation"), True),
        (("metrics", "control_work", "attempted_step_count"), 0),
    ],
)
def test_self_rehashed_early_response_or_claim_mutation_fails_against_complete_source(
    small, monkeypatch, path, value
):
    fixture = small.full
    invocations = _stub_expected_source(fixture, monkeypatch)
    supplied = deepcopy(fixture.payload)
    _set_path(supplied, path, value)
    changed = _reseal(supplied)
    assert changed != fixture.encoded
    report = _validate(fixture, result=changed)
    assert len(invocations) == 1
    assert report.artifact_contract_pass is report.contract_pass is False
    assert report.to_dict()["errors"]


@pytest.mark.parametrize("mutation", ["remove", "swap", "duplicate"])
def test_resealed_full_history_cannot_omit_reorder_or_duplicate_early_epochs(
    small, monkeypatch, mutation
):
    fixture = small.full
    invocations = _stub_expected_source(fixture, monkeypatch)
    supplied = deepcopy(fixture.payload)
    history = supplied["response_history"]
    if mutation == "remove":
        del history[0]
    elif mutation == "swap":
        history[0], history[1] = history[1], history[0]
    else:
        history[0] = deepcopy(history[1])
    report = _validate(fixture, result=_reseal(supplied))
    assert len(invocations) == 1
    assert report.artifact_contract_pass is False


@pytest.mark.parametrize(
    "field",
    [
        "configuration_hash",
        "control_global_dof",
        "targets_m",
        "allow_reversals",
        "maximum_targets",
        "restart_input_sha256",
    ],
)
def test_result_request_binding_cannot_be_stripped_and_rehashed_before_source_execution(
    small, monkeypatch, field
):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    supplied = deepcopy(small.full.payload)
    del supplied["request"][field]
    report = _validate(small.full, result=_reseal(supplied))
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False
    assert report.to_dict()["replay_control_work"]["attempted_step_count"] == 0


@pytest.mark.parametrize(
    "field", ["canonical_model_checksum", "input_checksum", "compiler_profile"]
)
def test_explicit_model_identity_is_required_before_source_reexecution(
    small, monkeypatch, field
):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    supplied = deepcopy(small.full.payload)
    supplied["model"][field] = "detached-model"
    report = _validate(small.full, result=_reseal(supplied))
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False


@pytest.mark.parametrize("as_input", [bytes, bytearray, memoryview, json.loads])
def test_supported_artifact_input_snapshots_preserve_exact_source_bytes(
    small, monkeypatch, as_input
):
    calls = _stub_expected_source(small.full, monkeypatch)
    report = _validate(small.full, result=as_input(small.full.encoded))
    assert len(calls) == 1
    assert report.artifact_contract_pass is True


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b'{"status":"ready","status":"blocked"}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"[]",
        b"\xff",
    ],
)
def test_malformed_result_json_fails_before_any_source_solver(small, monkeypatch, raw):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    report = _validate(small.full, result=raw)
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False
    assert report.to_dict()["replay_control_work"]["attempted_step_count"] == 0


@pytest.mark.parametrize("kind", ["missing", "changed-byte", "other-valid-prefix"])
def test_exact_checkpoint_output_bytes_cannot_be_replaced(small, monkeypatch, kind):
    calls = _stub_expected_source(small.full, monkeypatch)
    checkpoint = {
        "missing": None,
        "changed-byte": small.full.checkpoint + b"\n",
        "other-valid-prefix": small.prefix.checkpoint,
    }[kind]
    report = _validate(small.full, checkpoint=checkpoint)
    assert len(calls) == 1
    assert report.artifact_contract_pass is False


def test_wrong_original_restart_identity_rejects_before_replaying_any_prefix(
    small, monkeypatch
):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    report = api.validate_bounded_rc_fiber_direct_control_artifacts(
        small.resumed.model,
        small.resumed.targets,
        result=small.resumed.encoded,
        checkpoint=small.resumed.checkpoint,
        restart=small.full.checkpoint,
        **small.resumed.options,
    )
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False


def test_same_physical_model_with_different_original_input_bytes_is_not_substitutable(
    small, monkeypatch
):
    model = load_neutral_json_bytes(MODEL.read_bytes() + b"\n")
    assert model.canonical_model_checksum == small.full.model.canonical_model_checksum
    assert model.input_checksum != small.full.model.input_checksum
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    report = api.validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        SMALL_TARGETS,
        result=small.full.encoded,
        checkpoint=small.full.checkpoint,
        **OPTIONS,
    )
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False


def test_explicit_solver_configuration_changes_do_not_reuse_old_validation(
    small, monkeypatch
):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    report = _validate(
        small.full,
        config=Config(newton=replace(NewtonRaphsonConfig(), residual_tolerance=1e-9)),
    )
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False


def test_valid_different_result_cannot_replace_the_requested_complete_path(
    small, monkeypatch
):
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    report = _validate(
        small.full, result=small.prefix.encoded, checkpoint=small.prefix.checkpoint
    )
    assert report.artifact_contract_pass is False
    assert report.to_dict()["solver_replay_performed"] is False


def test_failed_attempt_work_cannot_be_removed_by_rehashing_all_nested_receipts(
    blocked, monkeypatch
):
    calls = _stub_expected_source(blocked, monkeypatch)
    supplied = deepcopy(blocked.payload)
    path = supplied["path"]
    attempt = path["attempts"][0]
    attempt["step"]["trial_solution"]["metrics"]["iteration_count"] = 17
    attempt["step"]["trial_solution"]["metrics"]["linear_solve_count"] = 17
    attempt["solver_work"]["iteration_count"] = 17
    attempt["solver_work"]["linear_solve_count"] = 17
    attempt["step"]["step_hash"] = canonical_hash(
        {k: v for k, v in attempt["step"].items() if k != "step_hash"}
    )
    for key in ("total_work", "suffix_work"):
        path["metrics"][key]["known_newton_iteration_count"] = 17
        path["metrics"][key]["known_linear_solve_count"] = 17
        path["metrics"][key]["unknown_solver_work_attempt_count"] = 0
    supplied["metrics"]["control_work"]["known_newton_iteration_count"] = 17
    supplied["metrics"]["control_work"]["known_linear_solve_count"] = 17
    supplied["metrics"]["control_work"]["unknown_solver_work_attempt_count"] = 0
    path["path_hash"] = _sha(
        _bytes({k: v for k, v in path.items() if k != "path_hash"})
    )
    report = _validate(blocked, result=_reseal(supplied))
    assert len(calls) == 1
    assert report.artifact_contract_pass is False
    assert report.to_dict()["replay_control_work"]["attempted_step_count"] == 1
    assert report.to_dict()["replay_control_work"]["known_newton_iteration_count"] == 0


def test_raised_source_reexecution_cannot_claim_zero_unknown_work(small, monkeypatch):
    def interrupted(*args, **kwargs):
        raise RuntimeError("injected source invocation interruption")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", interrupted)
    report = _validate(small.full)
    assert report.artifact_contract_pass is False
    assert report.to_dict()["fresh_source_execution_invoked"] is True
    assert report.to_dict()["solver_replay_performed"] is None
    assert report.to_dict()["replay_control_work"] is None
    assert report.to_dict()["unavailable_execution_work"] is True


def test_recovery_failure_retains_all_executed_work_without_partial_export_authority(
    small, monkeypatch
):
    # Reuse a genuine completed typed path at the execution boundary. Only the
    # first recovery assembly runs; the second recovery attempt is injected.
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(
        api, "run_stateful_fiber_frame2d_control_path", lambda *a, **kw: small.full.path
    )
    original = api.assemble_stateful_fiber_frame2d
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args[1].epoch)
        if len(calls) == 2:
            raise RuntimeError("injected second recovery failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "assemble_stateful_fiber_frame2d", fail_second)
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.full.model, SMALL_TARGETS, **OPTIONS
    )
    payload = result.to_dict()
    assert calls == [0, 1]
    assert result.status == "invalid_recovery" and result.contract_pass is False
    assert _bytes(payload["path"]) == _bytes(small.full.payload["path"])
    assert (
        payload["metrics"]["control_work"]
        == small.full.payload["metrics"]["control_work"]
    )
    assert payload["metrics"]["response_reassembly_attempts"] == 2
    assert payload["metrics"]["response_reassembly_verified_count"] == 1
    assert payload["response_history"] == [] and payload["terminal_response"] is None
    assert payload["failure"]["stage"] == "whole_accepted_history_recovery"
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


def test_replayed_original_assembly_field_tampering_is_rejected(small, monkeypatch):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(
        api, "run_stateful_fiber_frame2d_control_path", lambda *a, **kw: small.full.path
    )
    original = api.assemble_stateful_fiber_frame2d

    def changed_force(*args, **kwargs):
        assembly = original(*args, **kwargs)
        changed = assembly.internal_loads_global.copy()
        changed[0] = np.nextafter(changed[0], np.inf)
        return replace(assembly, internal_loads_global=changed)

    monkeypatch.setattr(api, "assemble_stateful_fiber_frame2d", changed_force)
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.full.model, SMALL_TARGETS, **OPTIONS
    )
    assert result.status == "invalid_recovery"
    assert result.to_dict()["metrics"]["response_reassembly_attempts"] == 1
    assert result.to_dict()["metrics"]["response_reassembly_verified_count"] == 0
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


def test_failed_core_attempt_keeps_verified_prefix_unknown_work_and_unattempted_suffix(
    small, monkeypatch
):
    # A retained genuine first core return and an injected second-call error.
    # This tests accounting/control flow; it performs zero new Newton calls.
    seen = []

    def backend_failure(*args, **kwargs):
        seen.append(kwargs["target_control_displacement_m"])
        if len(seen) == 1:
            return small.full.path.steps[0]
        raise RuntimeError("injected backend failure after verified prefix")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", backend_failure
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.full.model, SMALL_TARGETS, **OPTIONS
    )
    payload = result.to_dict()
    assert seen == list(SMALL_TARGETS[:2])
    assert result.status == "blocked" and result.contract_pass is False
    assert len(payload["response_history"]) == 1
    assert (
        payload["terminal_response"]["checkpoint_hash"]
        == small.prefix.payload["terminal_response"]["checkpoint_hash"]
    )
    path = payload["path"]
    assert (
        path["metrics"]["accepted_target_count"]
        == path["metrics"]["failed_target_count"]
        == 1
    )
    assert path["metrics"]["attempted_target_count"] == 2
    assert path["unattempted_targets_m"] == list(SMALL_TARGETS[2:])
    assert payload["metrics"]["control_work"]["attempted_step_count"] == 2
    assert payload["metrics"]["control_work"]["unknown_solver_work_attempt_count"] == 1
    assert path["attempts"][1]["solver_work"] is None
    assert path["attempts"][1]["rollback_exact"] is True
    assert result.checkpoint_artifact_bytes() == small.prefix.checkpoint


def test_invalid_returned_path_retains_snapshot_without_claiming_known_work(
    small, monkeypatch
):
    detached = replace(small.full.path)
    original = type(detached).to_dict

    def invalid_source(self):
        if self is detached:
            raise ValueError("injected retained path source mismatch")
        return original(self)

    monkeypatch.setattr(type(detached), "to_dict", invalid_source)
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(
        api, "run_stateful_fiber_frame2d_control_path", lambda *a, **kw: detached
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.full.model, SMALL_TARGETS, **OPTIONS
    )
    payload = result.to_dict()
    assert result.status == "invalid_execution"
    assert payload["metrics"]["control_work"] is None
    assert payload["metrics"]["unavailable_execution_work"] is True
    assert _bytes(payload["failure"]["unvalidated_path_snapshot"]) == _bytes(
        small.full.payload["path"]
    )
    assert payload["response_history"] == []
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


def test_private_restart_bytes_must_match_original_recovered_path(small, monkeypatch):
    detached = replace(small.full.path, _restart=small.prefix.checkpoint)
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(
        api, "run_stateful_fiber_frame2d_control_path", lambda *a, **kw: detached
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.full.model, SMALL_TARGETS, **OPTIONS
    )
    assert result.status == "invalid_recovery" and result.contract_pass is False
    assert (
        result.to_dict()["metrics"]["control_work"]
        == small.full.payload["metrics"]["control_work"]
    )
    with pytest.raises(ValueError):
        result.checkpoint_artifact_bytes()


def test_export_size_failure_retains_original_work_and_validator_costs(
    small, monkeypatch
):
    original_limit = api.BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    monkeypatch.setattr(
        api, "run_stateful_fiber_frame2d_control_path", lambda *a, **kw: small.full.path
    )
    monkeypatch.setattr(api, "BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES", 64)
    with pytest.raises(api.BoundedRCFiberDirectControlArtifactError) as caught:
        api.analyze_bounded_rc_fiber_direct_control(
            small.full.model, SMALL_TARGETS, **OPTIONS
        )
    failure = caught.value.to_dict()
    assert failure["status"] == "artifact_export_failed"
    assert failure["state_or_restart_export_available"] is False
    assert (
        failure["execution_metrics"]["control_work"]
        == small.full.payload["metrics"]["control_work"]
    )
    assert failure["execution_metrics"]["response_reassembly_attempts"] == 3
    assert failure["execution_metrics"]["response_reassembly_verified_count"] == 3
    monkeypatch.setattr(
        api, "BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES", original_limit
    )

    def export_failure(*args, **kwargs):
        raise caught.value

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", export_failure)
    report = _validate(small.full)
    assert report.artifact_contract_pass is False
    assert (
        report.to_dict()["replay_control_work"]
        == failure["execution_metrics"]["control_work"]
    )
    assert report.to_dict()["response_reassembly_attempts"] == 3
    assert report.to_dict()["unavailable_execution_work"] is False


def test_empty_suffix_replays_positive_restart_and_all_accepted_history(
    small, monkeypatch
):
    seen = _count_original_calls(monkeypatch)
    result = api.analyze_bounded_rc_fiber_direct_control(
        small.prefix.model, [], restart=small.prefix.checkpoint, **OPTIONS
    )
    payload = result.to_dict()
    assert seen == list(SMALL_TARGETS[:1])
    assert result.status == "ready" and result.contract_pass is True
    assert payload["path"]["metrics"]["prefix_replayed_step_count"] == 1
    assert payload["path"]["metrics"]["attempted_target_count"] == 0
    assert _bytes(payload["response_history"]) == _bytes(
        small.prefix.payload["response_history"]
    )
    assert result.checkpoint_artifact_bytes() == small.prefix.checkpoint


def test_genesis_only_restart_has_no_positive_physical_contract(blocked, monkeypatch):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        blocked.model, [], restart=blocked.checkpoint, **blocked.options
    )
    assert result.status == "ready" and result.contract_pass is False
    assert result.to_dict()["response_history"] == []
    assert result.to_dict()["terminal_response"] is None
    report = api.validate_bounded_rc_fiber_direct_control_artifacts(
        blocked.model,
        [],
        result=result.result_artifact_bytes(),
        checkpoint=result.checkpoint_artifact_bytes(),
        restart=blocked.checkpoint,
        **blocked.options,
    )
    assert report.artifact_contract_pass is True and report.contract_pass is False
    assert report.to_dict()["physical_path_complete"] is False
    assert report.to_dict()["fresh_source_execution_invoked"] is True
    assert report.to_dict()["solver_replay_performed"] is False
    assert report.to_dict()["replay_control_work"]["attempted_step_count"] == 0
