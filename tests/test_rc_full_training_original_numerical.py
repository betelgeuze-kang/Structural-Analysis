"""Pure authored driver controls; mocked reports carry no numerical credit.

Preparation uses current public typed models and actual connected screening.
All benchmark reports below are control-flow fixtures, not native originals.
"""

from copy import deepcopy
import importlib
from pathlib import Path
import sys
from time import perf_counter_ns

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


@pytest.fixture
def driver(monkeypatch):
    workspace = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(workspace / "scripts"))
    module = importlib.import_module("run_rc_full_training_original_numerical")
    assert Path(module.__file__).resolve() == (
        workspace / "scripts/run_rc_full_training_original_numerical.py"
    )
    return module


@pytest.fixture(autouse=True)
def native_solves_forbidden(monkeypatch, driver):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("pure driver test attempted a structural solve")

    for owner, name in (
        (runtime, "solve_stateful_fiber_frame2d_displacement_control_step"),
        (runtime, "_execute_preload"),
        (runtime, "benchmark_rc_control_seed_paths"),
        (learning, "benchmark_rc_control_seed_paths"),
        (driver, "benchmark_rc_control_seed_paths"),
        (public, "analyze_public_rc_fiber_frame"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    yield
    assert attempts == []


def prepared(tmp_path, driver, *, campaign=False):
    root = tmp_path / "authored-driver"
    receipt = driver.prepare(root)
    driver.save(root, "prepare-result.json", receipt)
    if campaign:
        driver.save(root, "campaign-started.json", {"monotonic_ns": perf_counter_ns()})
    return root


def fixture_report(*, unknown=False):
    # The original benchmark boundary is mocked. These numbers must never be
    # included in an actual campaign's solve/timing/benefit accounting.
    invocation = dict(
        ordinal=1,
        unknown_work=unknown,
        work=dict(
            core_calls=1,
            newton_iterations=None if unknown else 2,
            linear_solves=None if unknown else 2,
        ),
    )
    arm = dict(
        status="complete",
        wall_ns=100,
        cpu_ns=40,
        entries=[{"invocations": [invocation]}],
    )
    return dict(
        report_hash=_sha(_bytes({"authored_mock": True, "unknown": unknown})),
        all_execution_work_reported=not unknown,
        reference_repeat_exact=True,
        arms={"reference": deepcopy(arm), "secant": deepcopy(arm)},
        fresh_reference=deepcopy(arm),
        comparisons={
            name: dict(full_history_pass=True, exact_terminal_checkpoint=True)
            for name in ("reference", "secant")
        },
    )


def test_prepare_supports_metadata_and_four_authored_connected_groups(tmp_path, driver):
    root = prepared(tmp_path, driver)
    plan = driver.read(root / "experiment-plan.json")
    declared = driver.cases(root)
    actual = driver.control_training_exclusion_groups(declared)
    assert len(declared) == 6
    assert [case.split for case in declared] == [
        "train",
        "train",
        "train",
        "train",
        "validation",
        "holdout",
    ]
    assert (
        actual["groups"] == plan["groups"] == [[f"authored-{name}"] for name in "ABCD"]
    )
    assert plan["preflight_pass"] is True
    assert driver.read(root / "prepare-result.json")["structural_solves"] == 0
    assert plan["core_bounds"]["total"] == 1824 < plan["maximum_core_calls"] == 2048
    for row, case in zip(plan["cases"], declared, strict=True):
        model = driver.read(root / row["model_file"])
        assert model["metadata"] == {"case_id": case.case_id}
        assert row["source_role"] == "authored_numerical"
        assert row["model_checksum"] == case.model.canonical_model_checksum
        assert row["request"] == case.request.to_dict()
        assert driver.descriptor(root, row["model_file"]) == row["model_artifact"]
    assert plan["claims"]["independent_physics"] is False


@pytest.mark.parametrize("mutation", ["plan", "model", "driver_descriptor"])
def test_preflight_corruption_stops_before_generate(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(tmp_path, driver)
    plan = driver.read(root / "experiment-plan.json")
    if mutation == "plan":
        plan["cases"][0]["targets_m"][0] -= 0.001
        (root / "experiment-plan.json").write_bytes(_bytes(plan))
        message = "predeclared plan changed"
    elif mutation == "model":
        path = root / plan["cases"][0]["model_file"]
        model = driver.read(path)
        model["metadata"]["case_id"] = "changed-own-fixture"
        path.write_bytes(_bytes(model))
        message = "predeclared model changed"
    else:
        plan["driver_artifact"]["sha256"] = _sha(b"foreign driver bytes")
        (root / "experiment-plan.json").write_bytes(_bytes(plan))
        receipt = driver.read(root / "prepare-result.json")
        receipt["plan_hash"] = _sha(_bytes(plan))
        (root / "prepare-result.json").write_bytes(_bytes(receipt))
        message = "predeclared driver changed"
    callbacks = []

    def generate_must_not_start(*args, **kwargs):
        callbacks.append(True)
        raise AssertionError("generate should be blocked by original pins")

    monkeypatch.setattr(driver, "generate", generate_must_not_start)
    monkeypatch.setattr(sys, "argv", ["driver", "generate", "--output", str(root)])
    with pytest.raises(AssertionError, match=message):
        driver.main()
    assert callbacks == []
    assert not (root / "generate-started.json").exists()
    assert not (root / "generation").exists()


@pytest.mark.parametrize(
    "mutation", ["raw_bytes", "length", "new_descriptor_old_pair_hash", "flattened"]
)
def test_candidate_epoch_or_descriptor_changes_stop_before_benchmark(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(tmp_path, driver, campaign=True)
    # A small packet tests the earlier artifact/hash guard, before typed policy
    # decoding. It is intentionally not a fitted policy or numerical original.
    selected = dict(
        schema_version="rc-original-full-training-seed-prior-work-pair.v1",
        seed_policy_hash=_sha(b"authored seed identity"),
        gate_policy_hash=_sha(b"authored gate identity"),
        reference_parent_conditioned=True,
    )
    selected["pair_hash"] = _sha(_bytes(selected))
    pair = {**selected, "selected_pair": deepcopy(selected), "fit_receipt": {}}
    driver.save(root, "frozen-candidate-pair.json", pair)
    receipt = dict(
        status="completed",
        candidate_fitted=True,
        pair_hash=pair["pair_hash"],
        candidate_artifact=driver.descriptor(root, "frozen-candidate-pair.json"),
    )
    if mutation == "raw_bytes":
        pair["fit_receipt"]["changed"] = True
        message = "completed candidate bytes differ"
    elif mutation == "length":
        receipt["candidate_artifact"]["byte_length"] += 1
        message = "completed candidate bytes differ"
    elif mutation == "new_descriptor_old_pair_hash":
        changed = deepcopy(selected)
        changed["reference_parent_conditioned"] = False
        changed["pair_hash"] = _sha(
            _bytes({key: value for key, value in changed.items() if key != "pair_hash"})
        )
        pair = {**changed, "selected_pair": deepcopy(changed), "fit_receipt": {}}
        message = "completed candidate hash differs"
    else:
        pair["seed_policy_hash"] = _sha(b"different flattened seed")
        message = "flattened candidate differs"
    (root / "frozen-candidate-pair.json").write_bytes(_bytes(pair))
    if mutation in ("new_descriptor_old_pair_hash", "flattened"):
        receipt["candidate_artifact"] = driver.descriptor(
            root, "frozen-candidate-pair.json"
        )
    driver.save(root, "join-fit-result.json", receipt)
    callbacks = []

    def unexpected_benchmark(*args, **kwargs):
        callbacks.append(True)
        raise AssertionError("candidate identity must fail before benchmark")

    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", unexpected_benchmark)
    with pytest.raises(AssertionError, match=message):
        driver.evaluate(root)
    assert callbacks == []
    assert not (root / "full-path-progress.json").exists()


def test_unknown_progress_prevents_a_second_full_path_callback(
    tmp_path, driver, monkeypatch
):
    root = prepared(tmp_path, driver, campaign=True)
    driver.save(
        root, "join-fit-result.json", dict(status="HOLD", candidate_fitted=False)
    )
    callbacks = []

    def mocked_benchmark(*args, **kwargs):
        callbacks.append(kwargs["output_directory"])
        return fixture_report(unknown=True)

    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", mocked_benchmark)
    with pytest.raises(AssertionError, match="unknown native work; stop budget reuse"):
        driver.evaluate(root)
    assert len(callbacks) == 1
    progress = driver.read(root / "full-path-progress.json")
    assert progress["unknown_work"] is True
    assert len(progress["records"]) == 1 and progress["planned"] == 18
    assert progress["records"][0]["comparison_pass"] is False
    assert progress["records"][0]["path_time_ratio"] is None
    assert progress["known_completed_work"]["core_calls"] == 3  # mocked, not native
    assert not (root / "full-path-outcome.json").exists()


def test_baseline_evaluate_accepts_reference_and_secant_without_proposal_decision(
    tmp_path, driver, monkeypatch
):
    root = prepared(tmp_path, driver, campaign=True)
    driver.save(
        root, "join-fit-result.json", dict(status="HOLD", candidate_fitted=False)
    )
    callbacks = []

    def mocked_benchmark(*args, **kwargs):
        assert "proposal" not in kwargs
        callbacks.append(kwargs["output_directory"])
        return fixture_report()

    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", mocked_benchmark)
    result = driver.evaluate(root)
    assert result["status"] == "completed" and result["candidate_evaluated"] is False
    assert len(callbacks) == result["comparisons"] == result["verified"] == 18
    records = driver.read(root / "full-path-outcome.json")["records"]
    assert all(row["path_time_ratio"] is None for row in records)
    assert {row["split"] for row in records} == {"train", "validation", "holdout"}
    assert all(
        arm["decisions"] == {} for row in records for arm in row["arms"].values()
    )


def test_generation_hold_blocks_teacher_fit_and_labels(tmp_path, driver, monkeypatch):
    root = prepared(tmp_path, driver)
    driver.save(root, "generate-result.json", dict(status="HOLD", fit=None))
    fits = []

    def teacher_fit_must_not_start(*args, **kwargs):
        fits.append(True)
        raise AssertionError("generation HOLD must stop teacher fits")

    monkeypatch.setattr(driver, "fit_declared_seeds", teacher_fit_must_not_start)
    with pytest.raises(AssertionError, match="generation HOLD"):
        driver.labels(root)
    assert fits == []
    assert not (root / "retained-seeds").exists()
    assert not (root / "retained-labels").exists()


def test_large_original_read_bound_and_atomic_progress_preserve_immutable_files(
    tmp_path, driver, monkeypatch
):
    root = tmp_path / "owned-progress"
    root.mkdir()
    original = {"padding": "x" * (129 * 1024)}
    driver.save(root, "original.json", original)
    raw = (root / "original.json").read_bytes()
    assert driver.read(root / "original.json") == original
    with pytest.raises(FileExistsError):
        driver.save(root, "original.json", {"replacement": True})
    driver.save_progress(root, "progress.json", {"completed": 1, "unknown_work": False})
    driver.save_progress(root, "progress.json", {"completed": 2, "unknown_work": True})
    assert driver.read(root / "progress.json") == {"completed": 2, "unknown_work": True}
    assert (root / "original.json").read_bytes() == raw
    assert not (root / "progress.json.next").exists()
    monkeypatch.setattr(driver, "MAX_FILE_BYTES", len(raw) - 1)
    with pytest.raises(ValueError, match="bounded numerical original file exceeded"):
        driver.read(root / "original.json")
