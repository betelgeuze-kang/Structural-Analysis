"""Original constant-study replay, falsified metadata and physical rows."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.api.nonlinear_fiber_frame import (
    EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    _arithmetic_kwargs,
    RETAINED_LEARNING_ARITHMETIC_PROFILE,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "seed_original_audit", ROOT / "scripts/verify_rc_seed_originals.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    root = tmp_path_factory.mktemp("constant-originals")
    shutil.copyfile(
        ROOT / "examples/public_rc_fiber_frame_cantilever.json", root / "model.json"
    )
    request = BoundedRCFiberDirectControlRequest(
        4,
        (-1e-5, -2e-5, 1e-5),
        allow_reversals=True,
        maximum_reversals=2,
        constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
    )
    request = replace(
        request,
        solver_config=replace(
            request.solver_config,
            newton=replace(request.solver_config.newton, terminal_polishing=True),
        ),
    )
    (root / "request.json").write_bytes(_bytes(request.to_dict()))
    result = benchmark_rc_control_seed_paths(
        load_neutral_json(root / "model.json"),
        request,
        source_revision="a" * 40,
        output_directory=root / "study",
        **_arithmetic_kwargs(RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    assert result["reference_repeat_exact"]
    return root


def verify(root):
    return audit.verify(root / "study", root / "model.json", root / "request.json")


@pytest.fixture(scope="module")
def two_fixed_small_step(tmp_path_factory):
    root = tmp_path_factory.mktemp("two-fixed-small-step")
    shutil.copyfile(
        ROOT / "examples/research/rc_internal_portal_20mm/original-model.json",
        root / "model.json",
    )
    request = BoundedRCFiberDirectControlRequest(
        9,
        (-1e-6,),
        constant_nodal_loads=(
            ("N3", 0.0, -25.0, 0.0),
            ("N4", 0.0, -25.0, 0.0),
        ),
        experimental_two_fixed_endpoints=True,
    )
    request = replace(
        request,
        solver_config=replace(
            request.solver_config,
            newton=replace(request.solver_config.newton, terminal_polishing=True),
        ),
    )
    model = load_neutral_json(root / "model.json")
    rejected = root / "without-opt-in"
    with pytest.raises(ValueError, match="supported RC model required"):
        benchmark_rc_control_seed_paths(
            model,
            replace(request, experimental_two_fixed_endpoints=False),
            source_revision="a" * 40,
            output_directory=rejected,
            **_arithmetic_kwargs(RETAINED_LEARNING_ARITHMETIC_PROFILE),
        )
    assert not rejected.exists()
    (root / "request.json").write_bytes(_bytes(request.to_dict()))
    report = benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="a" * 40,
        output_directory=root / "study",
        **_arithmetic_kwargs(RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    return root


def test_two_fixed_small_step_replays_original_preload_and_six_reactions(
    two_fixed_small_step, monkeypatch
):
    from structural_analysis.assembly import stateful_fiber_frame2d_solver as force
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    report = json.loads(
        (two_fixed_small_step / "study/comparison.json").read_bytes()
    )
    assert report["compiler_profile"] == (
        EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE
    )
    assert report["request"]["experimental_two_fixed_endpoints"] is True
    for name in ("reference", "secant", "fresh-reference"):
        path = json.loads(
            (two_fixed_small_step / "study" / name / "path.json").read_bytes()
        )
        assert path["status"] == "complete"
        for response in (path["preload_response"], *path["response_history"]):
            assert [(row["node_id"], row["dof"]) for row in response["support_reactions"]] == [
                (node, dof)
                for node in ("N1", "N2")
                for dof in ("UX", "UY", "RZ")
            ]

    def forbidden(*args, **kwargs):
        pytest.fail("two-fixed original audit must not run Newton")

    monkeypatch.setattr(force, "newton_raphson_vector", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    result = verify(two_fixed_small_step)
    assert result["original_records_reproduced"] and result["repeat_admissible"]
    assert result["original_work"]["core_calls"] == 6
    assert result["audit_work"]["assembly_replays"] == 6


def test_two_fixed_original_audit_rejects_forged_compiler_profile(
    two_fixed_small_step, tmp_path
):
    root = tmp_path / "forged-profile"
    shutil.copytree(two_fixed_small_step, root)
    report_path = root / "study/comparison.json"
    report = json.loads(report_path.read_bytes())
    report["compiler_profile"] = "single-fixed-endpoint-profile"
    report_path.write_bytes(rehash(report, "report_hash"))
    with pytest.raises(ValueError, match="compiler profile differs"):
        verify(root)


@pytest.fixture(scope="module")
def two_fixed_retry_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("two-fixed-retry-path")
    source = ROOT / "examples/research/rc_internal_portal_20mm"
    shutil.copyfile(source / "original-model.json", root / "model.json")
    request = replace(
        decode_bounded_rc_fiber_direct_control_request(
            (source / "original-request.json").read_bytes()
        ),
        experimental_two_fixed_endpoints=True,
    )
    (root / "request.json").write_bytes(_bytes(request.to_dict()))
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(root / "model.json"),
        request,
        source_revision="a" * 40,
        output_directory=root / "study",
        **_arithmetic_kwargs(RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    assert report["reference_repeat_exact"]
    path = json.loads((root / "study/secant/path.json").read_bytes())
    assert [len(entry["invocations"]) for entry in path["entries"]] == [1, 1, 2]
    assert path["entries"][2]["invocations"][0]["committed"] is False
    assert path["entries"][2]["invocations"][1]["committed"] is True
    return root


def test_failed_seeded_attempt_is_charged_but_not_claimed_as_reassembled(
    two_fixed_retry_path, monkeypatch
):
    from structural_analysis.assembly import stateful_fiber_frame2d_solver as force
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("original retry audit must not run Newton")

    monkeypatch.setattr(force, "newton_raphson_vector", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    result = verify(two_fixed_retry_path)
    assert result["schema_version"] == "rc-constant-seed-original-audit.v2"
    assert result["comparisons"] == {"reference": True, "secant": True}
    assert result["original_records_reproduced"] is False
    assert result["repeat_admissible"] is False
    assert result["original_replay_scope"] == "accepted_transitions_only"
    assert result["accepted_transitions_reassembled"] == 12
    assert result["uncommitted_attempts_record_bound"] == 1
    assert result["uncommitted_attempts_by_arm"] == {
        "reference": 0,
        "secant": 1,
        "fresh-reference": 0,
    }
    assert result["uncommitted_attempts_reassembled"] == 0
    assert result["original_work"]["core_calls"] == 13
    assert result["audit_work"]["assembly_replays"] == 12
    assert result["audit_work"]["newton_solves"] == 0


def test_failed_attempt_rollback_record_cannot_be_forged(two_fixed_retry_path, tmp_path):
    root = tmp_path / "forged-rollback"
    shutil.copytree(two_fixed_retry_path, root)
    step_path = root / "study/secant/002-1-step.json"
    step = json.loads(step_path.read_bytes())
    step["metrics"]["rollback_exact"] = False
    step["step_hash"] = canonical_hash(
        {key: value for key, value in step.items() if key != "step_hash"}
    )
    step_path.write_bytes(_bytes(step))
    with pytest.raises(ValueError, match="did not preserve its parent"):
        verify(root)


def test_actual_preload_and_lateral_replay_counts_no_newton(original, monkeypatch):
    from structural_analysis.assembly import stateful_fiber_frame2d_solver as force
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("original audit must not run Newton")

    monkeypatch.setattr(force, "newton_raphson_vector", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    result = verify(original)
    assert result["original_records_reproduced"] and result["repeat_admissible"]
    assert result["original_work"]["core_calls"] == 12
    assert result["audit_work"]["assembly_replays"] == 12
    assert result["audit_work"]["rational_record_rebuilds"] == 12
    assert (
        result["audit_work"]["newton_solves"]
        == result["audit_work"]["state_commits"]
        == 0
    )
    assert result["audit_work"]["material_integrations"] > 0


def rehash(value, key):
    value[key] = _sha(_bytes({k: v for k, v in value.items() if k != key}))
    return _bytes(value)


@pytest.mark.parametrize(
    "change", ["preload_response", "preload_cost", "tolerance", "parent"]
)
def test_forged_originals_cannot_acquire_repeat_admission(original, tmp_path, change):
    root = tmp_path / "changed"
    shutil.copytree(original, root)
    report_path = root / "study/comparison.json"
    report = json.loads(report_path.read_bytes())
    path_file = root / "study/reference/path.json"
    path = json.loads(path_file.read_bytes())
    if change == "preload_response":
        path["preload_response"]["support_reactions"][0]["value_si"] += 1
    elif change == "preload_cost":
        path["preload_invocations"] = []
    elif change == "tolerance":
        report["absolute_tolerance"] = 1.0
    else:
        step_file = root / "study/reference/000-1-step.json"
        step = json.loads(step_file.read_bytes())
        step["parent_checkpoint"]["state_hash"] = "sha256:" + "b" * 64
        step_file.write_bytes(rehash(step, "step_hash"))
    path_file.write_bytes(rehash(path, "path_hash"))
    report["arms"]["reference"] = {
        k: v
        for k, v in path.items()
        if k not in ("response_history", "terminal_checkpoint", "preload_response")
    }
    report_path.write_bytes(rehash(report, "report_hash"))
    with pytest.raises(ValueError):
        verify(root)
