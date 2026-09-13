"""Original constant-study replay, falsified metadata and physical rows."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    _arithmetic_kwargs,
    RETAINED_LEARNING_ARITHMETIC_PROFILE,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
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
