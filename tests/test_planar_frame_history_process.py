"""Two real workers, then retained-artifact tests; no performance/V&V claim."""

from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import pytest

from structural_analysis.api import nonlinear_frame as nonlinear
from structural_analysis.api import planar_frame as public
from structural_analysis.benchmark import planar_frame_backend_process as process
from structural_analysis.benchmark import planar_frame_history as history_module
from structural_analysis.benchmark.planar_frame_backend_comparison import SI_ROWS
from structural_analysis.benchmark.planar_frame_history_comparison import (
    HISTORY_GROUPS,
    compare_planar_frame_histories,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir import parse_model_ir_v2
from tests.test_planar_frame_backend_process import (
    BACKENDS,
    ROOT,
    _binding,
    _failed_worker,
    _request,
    _synthetic_manifest,
    _validate,
)


REUSE = "STRUCTURAL_PLANAR_HISTORY_TEST_ARTIFACTS"
REVISION = "a" * 40


def _history_request():
    value = _request()
    value.update(
        schema_version="planar-frame-backend-experiment-request.v2",
        backends=[BACKENDS[0], BACKENDS[2]],
        history_tolerances={
            name: {"absolute": 1e-9, "relative": 1e-9} for name in HISTORY_GROUPS
        },
    )
    value["cases"][0]["configuration"]["load_steps"] = 3
    return value


@pytest.fixture(scope="module")
def observed():
    """Exactly two fresh workers once; reuse requires no additional launch."""
    saved = os.environ.get(REUSE)
    if saved:
        directory = Path(saved)
    else:
        directory = Path(tempfile.mkdtemp(prefix="structural-planar-history-tests-"))
        print(f"{REUSE}={directory}", flush=True)
        (directory / "model.json").write_bytes(
            (ROOT / "examples/planar_frame_rc_portal.json").read_bytes()
        )
        request = _history_request()
        (directory / "request.json").write_bytes(process._bytes(request))
        result = process.run_planar_frame_backend_experiment(
            directory / "request.json",
            source_revision=REVISION,
            output_directory=directory / "experiment",
            timeout_seconds=180,
        )
        # A failed worker is retained and stops this test run; no retry is allowed.
        assert result["counts"] == {
            "declared": 2,
            "launched": 2,
            "api_entered": 2,
            "artifact_contract_pass": 2,
            "physical_converged": 2,
            "resource_eligible": 2,
        }, {"retained": str(directory), "rows": result["rows"]}
    output = directory / "experiment"
    return SimpleNamespace(
        directory=directory,
        output=output,
        request=json.loads((output / "request.json").read_bytes()),
        manifest=json.loads((output / "inputs-manifest.json").read_bytes()),
        report=json.loads((output / "experiment.json").read_bytes()),
    )


@pytest.fixture(autouse=True)
def no_additional_solve_or_child(monkeypatch):
    # Module-scoped observed runs before this function-scoped guard. Every test
    # below may reassemble retained states, but may not request another path.
    # Python may invoke uname once to obtain platform metadata; populate that
    # standard-library cache before forbidding all subsequent child launches.
    process.platform.platform()

    def forbidden(*args, **kwargs):
        pytest.fail("only the two module-fixture workers may solve or launch")

    monkeypatch.setattr(process.subprocess, "Popen", forbidden)
    monkeypatch.setattr(public, "analyze_planar_frame", forbidden)
    monkeypatch.setattr(nonlinear, "_run_corotational_path", forbidden)


def _raw_slot(observed, index=0):
    row = observed.report["rows"][index]
    directory = observed.output / row["directory"]
    case = observed.manifest["cases"][row["case_index"]]
    return SimpleNamespace(
        directory=directory,
        row=row,
        case=case,
        slot=observed.manifest["schedule"][index],
        resources=json.loads((directory / "resources.json").read_bytes()),
        result=json.loads((directory / "result.json").read_bytes()),
        history=json.loads((directory / "history.json").read_bytes()),
        checkpoint=(directory / "checkpoint.json").read_bytes(),
    )


def _copy_slot(observed, tmp_path, index=0):
    original = _raw_slot(observed, index)
    bundle = tmp_path / "bundle"
    directory = bundle / original.row["directory"]
    directory.mkdir(parents=True)
    for name in ("slot.json", "resources.json", *original.resources["artifacts"]):
        shutil.copyfile(original.directory / name, directory / name)
    target = bundle / original.case["input_file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(observed.output / original.case["input_file"], target)
    return SimpleNamespace(
        bundle=bundle,
        directory=directory,
        manifest=deepcopy(observed.manifest),
        slot=deepcopy(original.slot),
        resources=deepcopy(original.resources),
        history=deepcopy(original.history),
        result=deepcopy(original.result),
        row=deepcopy(original.row),
    )


def _save_resources(context):
    context.resources["artifacts"] = {
        name: process._file_identity(context.directory / name)
        for name in context.resources["artifacts"]
        if (context.directory / name).is_file()
    }
    (context.directory / "resources.json").write_bytes(
        process._bytes(context.resources)
    )


def _save_history(context):
    value = context.history
    value["history_hash"] = canonical_hash(
        {k: v for k, v in value.items() if k != "history_hash"}
    )
    (context.directory / "history.json").write_bytes(process._bytes(value))
    _save_resources(context)


def _check(context):
    return _validate(
        context.directory,
        context.slot,
        context.manifest,
        context.resources["worker_pid"],
    )


def _inputs(observed, index=0):
    source = _raw_slot(observed, index)
    document = parse_model_ir_v2(
        json.loads((observed.output / source.case["input_file"]).read_bytes()),
        require_analysis_ready=True,
    )
    config = public.PlanarFrameConfig(
        **source.case["configuration"], matrix_backend=source.row["backend"]
    )
    return document, config, process._decode_result(source.result), source.checkpoint


def test_actual_two_workers_cover_every_three_step_history_and_public_terminal(
    observed,
):
    report = observed.report
    assert report["schema_version"] == "planar-frame-backend-experiment.v2"
    assert report["counts"] == {
        name: 2
        for name in (
            "declared",
            "launched",
            "api_entered",
            "artifact_contract_pass",
            "physical_converged",
            "resource_eligible",
        )
    }
    assert (
        report["schedule_complete"]
        and report["source_snapshot_intact"]
        and report["inputs_intact"]
    )
    assert report["history_comparison_counts"] == {
        "expected_pairs": 1,
        "reported_pairs": 1,
        "terminal_si_match": 1,
        "full_history_match": 1,
        "all_required_match": 1,
    }
    assert report["independent_external_vv"] is report["release_eligible"] is False
    assert len({row["worker_pid"] for row in report["rows"]}) == 2
    assert all(row["worker_pid"] != os.getpid() for row in report["rows"])
    for index in range(2):
        source = _raw_slot(observed, index)
        h, result, resource = source.history, source.result, source.resources
        assert h["source_result_hash"] == result["result_hash"]
        assert h["checkpoint_identity"] == result["result_ir"]["checkpoint"]
        assert h["checkpoint_identity"]["artifact_hash"] == process._digest(
            source.checkpoint
        )
        assert h["checkpoint_identity"]["artifact_byte_length"] == len(
            source.checkpoint
        )
        assert h["configuration"] == resource["configuration"]
        assert h["model_identity"] == {
            key: result["result_ir"]["contract_bindings"]["source_model_ir_adapter"][
                key
            ]
            for key in h["model_identity"]
        }
        assert h["root"]["epoch"] == h["root"]["step_index"] == 0
        assert h["root"]["material_states"]
        assert [row["epoch"] for row in h["steps"]] == [1, 2, 3]
        assert [row["load_factor"] for row in h["steps"]] == [1 / 3, 2 / 3, 1.0]
        parent = h["root"]["state_hash"]
        for epoch, step in enumerate(h["steps"], 1):
            assert step["step_index"] == epoch
            assert step["parent_state_hash"] == parent
            assert step["material_states"]
            assert all(step["si_rows"][group] for group in SI_ROWS)
            parent = step["state_hash"]
        for group in SI_ROWS:
            assert process._bytes(h["steps"][-1]["si_rows"][group]) == process._bytes(
                result["result_ir"][group]
            )
        assert h["history_hash"] == canonical_hash(
            {k: v for k, v in h.items() if k != "history_hash"}
        )
        assert resource["schema_version"] == "planar-frame-backend-worker.v2"
        assert resource["history_runtime"]["status"] == "ready"
        assert resource["history_runtime"]["scope"] == process.HISTORY_PHASE_SCOPE
        assert resource["workload_scope"] == process.HISTORY_WORKLOAD_SCOPE
        for unit in ("wall", "cpu"):
            assert 0 < resource["history_runtime"][unit + "_ns"]
            assert (
                resource["analysis_" + unit + "_ns"]
                + resource["history_runtime"][unit + "_ns"]
                <= resource["workload_" + unit + "_ns"]
            )
            assert source.row["parent_artifact_validation_" + unit + "_ns"] > 0
    pair = report["comparisons"][0]
    assert pair["comparison"]["physical_si_match"] is True
    assert pair["history_comparison"]["full_history_match"] is True
    assert pair["history_comparison"]["step_counts"] == {
        "left": 3,
        "right": 3,
        "compared": 3,
    }
    assert pair["paired_workload_wall_difference_ns"] is not None


@pytest.mark.parametrize("index", [0, 1])
def test_parent_rebuilds_history_from_current_model_result_and_original_checkpoint(
    observed, index
):
    source = _raw_slot(observed, index)
    rebuilt = history_module.build_planar_frame_history(*_inputs(observed, index))
    assert process._bytes(rebuilt) == (source.directory / "history.json").read_bytes()
    resource, result, validation = _validate(
        source.directory, source.slot, observed.manifest, source.resources["worker_pid"]
    )
    assert result == source.result and resource == source.resources
    assert validation["artifact_contract_pass"] is True


@pytest.mark.parametrize("field", ["document", "configuration", "result", "checkpoint"])
def test_history_producer_requires_exact_typed_inputs(observed, field):
    values = list(_inputs(observed))
    values[("document", "configuration", "result", "checkpoint").index(field)] = {}
    with pytest.raises(ValueError, match="exact public"):
        history_module.build_planar_frame_history(*values)


@pytest.mark.parametrize(
    "change", ["configuration", "model", "checkpoint", "genesis", "load"]
)
def test_history_producer_rejects_source_or_checkpoint_changes(observed, change):
    document, config, result, raw = _inputs(observed)
    if change == "configuration":
        config = replace(config, residual_tolerance=1e-9)
    elif change == "model":
        value = document.to_dict()
        value["sections"][0]["parameters"]["width_m"] += 0.001
        value["provenance"]["source_sha256"] = canonical_hash(
            {k: v for k, v in value.items() if k != "provenance"}
        )
        document = parse_model_ir_v2(value, require_analysis_ready=True)
    elif change == "checkpoint":
        raw = raw + b"\n"
    else:
        # These raw checkpoint edits test descriptor-byte binding, not a
        # coherently rehashed genesis/schedule proof. Middle-history resealing
        # below independently exercises the parent transition-recovery check.
        value = json.loads(raw)
        if change == "genesis":
            value["checkpoints"][0]["global_displacements"][0] = 0.01
        else:
            value["checkpoints"][1]["load_factor"] = 0.25
        raw = process._bytes(value)
    with pytest.raises(ValueError, match="history source|history checkpoint"):
        history_module.build_planar_frame_history(document, config, result, raw)


@pytest.mark.parametrize("change", ["early_si", "material", "genesis", "state_hash"])
def test_parent_rejects_rehashed_history_even_after_resource_artifact_resealing(
    observed, tmp_path, change
):
    context = _copy_slot(observed, tmp_path)
    h = context.history
    if change == "early_si":
        h["steps"][0]["si_rows"]["node_displacements"][0]["UX_m"] += 0.001
    elif change == "material":
        state = h["steps"][0]["material_states"][0]["state"]
        key = next(key for key, value in state.items() if type(value) is float)
        state[key] += 0.001
    elif change == "genesis":
        h["root"]["global_displacements"][0] += 0.001
    else:
        h["steps"][0]["state_hash"] = canonical_hash({"synthetic_changed_state": 1})
        h["steps"][1]["parent_state_hash"] = h["steps"][0]["state_hash"]
    _save_history(context)
    assert h["steps"][-1] == _raw_slot(observed).history["steps"][-1]
    with pytest.raises(ValueError, match="saved history differs"):
        _check(context)


def test_missing_history_cannot_hide_by_removing_its_artifact_entry(observed, tmp_path):
    context = _copy_slot(observed, tmp_path)
    (context.directory / "history.json").unlink()
    _save_resources(context)
    with pytest.raises(ValueError, match="missing its output"):
        _check(context)


@pytest.mark.parametrize(
    "field,value",
    [
        ("wall_ns", None),
        ("cpu_ns", None),
        ("wall_ns", True),
        ("cpu_ns", -1),
        ("wall_ns", 1.0),
        ("scope", "solver_only"),
        ("status", "not_run"),
        ("reason", "phase_not_reached"),
    ],
)
def test_history_phase_contract_is_strict(observed, tmp_path, field, value):
    context = _copy_slot(observed, tmp_path)
    context.resources["history_runtime"][field] = value
    _save_resources(context)
    with pytest.raises(ValueError, match="history"):
        _check(context)


@pytest.mark.parametrize("unit", ["wall", "cpu"])
@pytest.mark.parametrize("excess", [0, 1])
def test_disjoint_analysis_and_history_costs_must_fit_inside_workload(
    observed, tmp_path, unit, excess
):
    context = _copy_slot(observed, tmp_path)
    context.resources["history_runtime"][unit + "_ns"] = (
        context.resources["workload_" + unit + "_ns"] + excess
    )
    _save_resources(context)
    with pytest.raises(ValueError, match="history"):
        _check(context)


def test_v2_worker_cannot_downgrade_its_schema_or_omit_history_clock(
    observed, tmp_path
):
    context = _copy_slot(observed, tmp_path)
    for change in ("schema", "history", "clock"):
        original = deepcopy(context.resources)
        if change == "schema":
            context.resources["schema_version"] = "planar-frame-backend-worker.v1"
        elif change == "history":
            context.resources.pop("history_runtime")
        else:
            context.resources["history_runtime"].pop("cpu_ns")
        _save_resources(context)
        with pytest.raises(ValueError):
            _check(context)
        context.resources = original


def test_history_failure_preserves_known_attempted_cost_without_physical_credit(
    observed, tmp_path
):
    context = _copy_slot(observed, tmp_path)
    (context.directory / "history.json").unlink()
    error = {"type": "ValueError", "message": "synthetic projection failure"}
    context.resources.update(
        status="worker_error", stage="history_projection", error=error
    )
    context.resources["history_runtime"].update(
        status="failed", reason="history_projection_failed"
    )
    (context.directory / "failure.json").write_bytes(
        process._bytes({"stage": "history_projection", **error})
    )
    context.resources["artifacts"]["failure.json"] = {}
    _save_resources(context)
    resource, result, validation = _check(context)
    assert result is validation is None
    assert resource["api_entered"] is True
    assert resource["history_runtime"]["wall_ns"] > 0
    assert resource["workload_wall_ns"] > 0
    assert resource["worker_cpu_ns"] > 0
    assert (context.directory / "result.json").read_bytes() == (
        _raw_slot(observed).directory / "result.json"
    ).read_bytes()


def test_unexecuted_history_keeps_null_costs_and_legacy_scope_unchanged(tmp_path):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    original = _failed_worker(tmp_path, slot, manifest, pid)
    resource, _, _ = _validate(tmp_path, slot, manifest, pid)
    assert resource == original
    assert "history_runtime" not in resource
    assert resource["schema_version"] == "planar-frame-backend-worker.v1"
    manifest["request"] = _history_request()
    binding = _binding(slot, manifest, pid)
    resource.update(
        **binding,
        schema_version="planar-frame-backend-worker.v2",
        workload_scope=process.HISTORY_WORKLOAD_SCOPE,
        history_runtime={
            "status": "not_run",
            "reason": "phase_not_reached",
            "wall_ns": None,
            "cpu_ns": None,
            "scope": process.HISTORY_PHASE_SCOPE,
        },
    )
    (tmp_path / "started.json").write_bytes(process._bytes(binding))
    context = SimpleNamespace(directory=tmp_path, resources=resource)
    _save_resources(context)
    checked, result, validation = _validate(tmp_path, slot, manifest, pid)
    assert result is validation is None
    assert checked["history_runtime"]["wall_ns"] is None
    assert checked["history_runtime"]["cpu_ns"] is None
    assert checked["worker_cpu_ns"] == original["worker_cpu_ns"]


def test_not_converged_public_artifact_keeps_history_unavailable(observed, tmp_path):
    # A pure unsupported public artifact exercises the converged=None branch.
    # Retained timings below are synthetic transport data, not another API run.
    context = _copy_slot(observed, tmp_path)
    case_index = context.slot["case_index"]
    context.manifest["cases"][case_index]["configuration"]["control"] = "arc_length"
    context.manifest["request"]["cases"][case_index]["configuration"]["control"] = (
        "arc_length"
    )
    context.resources["configuration"]["control"] = "arc_length"
    binding = _binding(context.slot, context.manifest, context.resources["worker_pid"])
    context.resources.update(binding)
    for name in ("started.json", "entered.json"):
        (context.directory / name).write_bytes(process._bytes(binding))
    result = public._not_run_result(
        public.PlanarFrameUnsupportedError(
            "planar_frame_arc_length_experimental",
            "/config/control",
            "Synthetic unsupported-control transport fixture.",
        )
    )
    (context.directory / "result.json").write_bytes(process._bytes(result.to_dict()))
    (context.directory / "validation.json").write_bytes(
        process._bytes(public.validate_planar_frame_result(result).to_dict())
    )
    for name in ("checkpoint.json", "history.json"):
        (context.directory / name).unlink()
    context.resources["history_runtime"].update(
        status="not_run",
        reason="public_result_not_converged",
        wall_ns=None,
        cpu_ns=None,
    )
    _save_resources(context)
    resources, payload, validation = _check(context)
    assert payload["converged"] is None
    assert resources["history_runtime"]["wall_ns"] is None
    assert resources["history_runtime"]["cpu_ns"] is None
    assert validation["engineering_result_authority"] is False
    assert validation["executed"] is False
    # A correctly declined request satisfies the existing execution contract.
    assert validation["execution_contract_pass"] is True


@pytest.mark.parametrize(
    "change", ["missing", "old_schema", "wrong_groups", "boolean", "extra"]
)
def test_history_request_profile_is_explicit_and_strict(change):
    request = _history_request()
    if change == "missing":
        request.pop("history_tolerances")
    elif change == "old_schema":
        request["schema_version"] = "planar-frame-backend-experiment-request.v1"
    elif change == "wrong_groups":
        request["history_tolerances"].pop("material_states")
    elif change == "boolean":
        request["history_tolerances"]["material_states"]["absolute"] = True
    else:
        request["history_tolerances"]["material_states"]["extra"] = 1
    with pytest.raises(ValueError):
        process._decode_request(process._bytes(request))


def test_request_defaults_preserve_v1_and_v2_has_exact_six_history_groups():
    old = _request()
    new = _history_request()
    assert process._decode_request(process._bytes(old)) == old
    assert "history_tolerances" not in old
    assert process._decode_request(process._bytes(new)) == new
    assert set(new["history_tolerances"]) == set(HISTORY_GROUPS)


@pytest.mark.parametrize("matched,expected", [(True, 0), (False, 1)])
def test_cli_requires_history_match_even_when_every_result_converged(
    observed, tmp_path, monkeypatch, matched, expected
):
    report = deepcopy(observed.report)
    report["history_comparison_counts"]["all_required_match"] = int(matched)
    monkeypatch.setattr(
        process, "run_planar_frame_backend_experiment", lambda *args, **kwargs: report
    )
    assert (
        process.main(
            [
                "--request",
                "unused.json",
                "--source-revision",
                REVISION,
                "--output-directory",
                str(tmp_path / "unused"),
            ]
        )
        == expected
    )
    assert not (tmp_path / "unused").exists()


def test_terminal_match_with_middle_history_mismatch_disables_paired_costs(
    observed, tmp_path
):
    # Simulates the pair-comparison boundary after an independently supplied
    # valid history. The parent bundle validator separately rejects this edit.
    contexts = [_copy_slot(observed, tmp_path, index) for index in range(2)]
    other = contexts[1]
    other.history["steps"][0]["si_rows"]["node_displacements"][0]["UX_m"] += 0.01
    _save_history(other)
    rows = deepcopy(observed.report["rows"])
    rows[1]["worker_resources"] = other.resources
    rows[1]["artifacts"] = other.resources["artifacts"]
    results = {
        row["slot_index"]: context.result for row, context in zip(rows, contexts)
    }
    (pair,) = process._comparisons(contexts[0].bundle, observed.request, rows, results)
    assert pair["comparison"]["physical_si_match"] is True
    assert pair["history_comparison"]["full_history_match"] is False
    assert pair["paired_workload_wall_difference_ns"] is None
    assert pair["paired_worker_cpu_difference_ns"] is None
    standalone = compare_planar_frame_histories(
        contexts[0].history,
        other.history,
        tolerances=observed.request["history_tolerances"],
    )
    assert standalone["step_comparisons"][0]["match"] is False
    assert standalone["step_comparisons"][-1]["match"] is True
