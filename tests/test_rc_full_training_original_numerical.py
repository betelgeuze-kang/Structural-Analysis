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
import numpy as np

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.materials.stateful_fiber_section import StatefulRCFiberSection

_BENCHMARK_WRAPPER = runtime.benchmark_rc_control_seed_paths


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
        (driver, "fit_declared_seeds"),
        (learning, "_fit"),
        (public, "analyze_public_rc_fiber_frame"),
        (StatefulRCFiberSection, "integrate"),
        (StatefulRCFiberSection, "integrate_with_material_runtime"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    yield
    assert attempts == []


def prepared(
    tmp_path, driver, *, campaign=False, solver_profile=None, arithmetic_profile=None
):
    root = tmp_path / "authored-driver"
    options = {}
    if solver_profile is not None:
        options["solver_profile"] = solver_profile
    if arithmetic_profile is not None:
        options["arithmetic_profile"] = arithmetic_profile
    receipt = driver.prepare(root, **options)
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


def mock_generation_study(root, driver, monkeypatch, *, ready=False):
    """Authored boundary fixtures; never structural or fitted observations."""
    plan, samples, policy, _, _ = _authored_learning_inputs(root, driver)
    rows = [
        dict(
            case_id=case["case_id"],
            labels_eligible=True,
            report=fixture_report(),
        )
        for case in plan["cases"]
        if case["split"] == "train"
    ]
    report = dict(
        generation=rows,
        generation_work=dict(
            known_work=dict(core_calls=12, newton_iterations=24, linear_solves=24),
            unknown_work=False,
        ),
        report_hash=_sha(b"authored-generation-work-fixture"),
        fit=(
            dict(status="completed", policy_hash=policy.policy_hash) if ready else None
        ),
    )

    def mocked_study(*args, **kwargs):
        driver.save(root, "generation/training-samples.json", samples if ready else [])
        if ready:
            driver.save(root, "generation/policy.json", policy.to_dict())
        return deepcopy(report)

    monkeypatch.setattr(learning, "run_rc_control_learning_study", mocked_study)
    return report


@pytest.mark.parametrize("report_value", ["absent", None])
def test_generation_keeps_failed_row_unknown_and_completed_work(
    tmp_path, driver, monkeypatch, report_value
):
    root = prepared(tmp_path, driver)
    report = mock_generation_study(root, driver, monkeypatch)
    failed = dict(
        case_id="authored-B",
        labels_eligible=False,
        exception_kind="ValueError",
        unknown_work=True,
    )
    if report_value is None:
        failed["report"] = None
    report["generation"][1] = failed
    report["generation_work"] = dict(
        known_work=dict(core_calls=9, newton_iterations=18, linear_solves=18),
        unknown_work=True,
    )
    outcome = driver.generate(root)
    assert outcome["status"] == "HOLD"
    assert outcome["unknown_work"] is True
    assert outcome["known_completed_work"] == {
        "core_calls": 9,
        "newton_iterations": 18,
        "linear_solves": 18,
    }
    assert outcome["generation_report_hash"] == report["report_hash"]
    driver.save(root, "generate-result.json", outcome)
    driver.save(root, "campaign-started.json", {"monotonic_ns": perf_counter_ns()})
    with pytest.raises(AssertionError, match="unknown native work; stop budget reuse"):
        driver.check_budget(root)
    with pytest.raises(AssertionError, match="generation HOLD"):
        driver.labels(root)


@pytest.mark.parametrize(
    "counter", ["core_calls", "newton_iterations", "linear_solves"]
)
def test_counted_retains_known_values_and_marks_missing_counter_unknown(
    driver, counter
):
    report = fixture_report()
    del report["arms"]["reference"]["entries"][0]["invocations"][0]["work"][counter]
    outcome = driver.counted([report])
    assert outcome["unknown_work"] is True
    expected = dict(core_calls=3, newton_iterations=6, linear_solves=6)
    expected[counter] -= 1 if counter == "core_calls" else 2
    assert outcome["known_completed_work"] == expected


@pytest.mark.parametrize("source", ["aggregate", "comparison", "row"])
def test_generation_never_lowers_any_recorded_unknown(
    tmp_path, driver, monkeypatch, source
):
    root = prepared(tmp_path, driver)
    report = mock_generation_study(root, driver, monkeypatch, ready=True)
    if source == "aggregate":
        report["generation_work"]["unknown_work"] = True
    elif source == "comparison":
        report["generation"][0]["report"]["all_execution_work_reported"] = False
    else:
        report["generation"][0]["unknown_work"] = True
    outcome = driver.generate(root)
    assert outcome["status"] == "HOLD" and outcome["unknown_work"] is True
    assert outcome["known_completed_work"] == {
        "core_calls": 12,
        "newton_iterations": 24,
        "linear_solves": 24,
    }
    assert report["fit"]["status"] == "completed"  # Cannot excuse unknown native work.


@pytest.mark.parametrize(
    "mutation",
    ["absent", "flag", "missing_counter", "boolean", "negative", "disagreement"],
)
def test_generation_aggregate_integrity_is_required_before_ready(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(tmp_path, driver)
    report = mock_generation_study(root, driver, monkeypatch, ready=True)
    aggregate = report["generation_work"]
    if mutation == "absent":
        del report["generation_work"]
    elif mutation == "flag":
        aggregate["unknown_work"] = 0
    elif mutation == "missing_counter":
        del aggregate["known_work"]["linear_solves"]
    elif mutation == "boolean":
        aggregate["known_work"]["core_calls"] = True
    elif mutation == "negative":
        aggregate["known_work"]["newton_iterations"] = -1
    else:
        aggregate["known_work"]["core_calls"] += 1
    untouched = deepcopy(report)
    outcome = driver.generate(root)
    assert outcome["status"] == "HOLD" and outcome["unknown_work"] is True
    assert outcome["known_completed_work"] == {
        "core_calls": 12,
        "newton_iterations": 24,
        "linear_solves": 24,
    }
    assert report == untouched  # Preserve source claims; do not repair them in place.


@pytest.mark.parametrize("mutation", ["empty", "missing", "duplicate", "foreign"])
def test_generation_requires_the_entire_declared_train_denominator(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(tmp_path, driver)
    report = mock_generation_study(root, driver, monkeypatch, ready=True)
    rows = report["generation"]
    if mutation == "empty":
        rows.clear()
    elif mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[1]["case_id"] = rows[0]["case_id"]
    else:
        rows[1]["case_id"] = "authored-E"  # Declared validation, not TRAIN.
    report["generation_work"] = learning._execution_work(rows)
    outcome = driver.generate(root)
    assert outcome["status"] == "HOLD" and outcome["unknown_work"] is True
    assert outcome["sample_count"] == 20  # Cached sample count cannot prove coverage.


@pytest.mark.parametrize("failure", ["physical", "fit"])
def test_generation_known_failure_remains_hold_without_unknown_native_work(
    tmp_path, driver, monkeypatch, failure
):
    root = prepared(tmp_path, driver)
    report = mock_generation_study(root, driver, monkeypatch, ready=True)
    if failure == "physical":
        report["generation"][0]["labels_eligible"] = False
        report["generation"][0]["report"]["reference_repeat_exact"] = False
        report["generation"][0]["report"]["arms"]["reference"]["status"] = "blocked"
    else:
        report["fit"] = dict(status="failed", unknown_fit_work=True)
    outcome = driver.generate(root)
    assert outcome["status"] == "HOLD" and outcome["unknown_work"] is False
    assert outcome["fit"] == report["fit"]
    assert outcome["known_completed_work"]["core_calls"] == 12


@pytest.mark.parametrize(
    "arithmetic_profile", ["binary64", learning.RETAINED_LEARNING_ARITHMETIC_PROFILE]
)
def test_generation_complete_mocked_receipts_retain_ready_contract(
    tmp_path, driver, monkeypatch, arithmetic_profile
):
    root = prepared(tmp_path, driver, arithmetic_profile=arithmetic_profile)
    report = mock_generation_study(root, driver, monkeypatch, ready=True)
    outcome = driver.generate(root)
    assert outcome["status"] == "ready" and outcome["unknown_work"] is False
    assert outcome["sample_count"] == 20
    assert outcome["known_completed_work"] == report["generation_work"]["known_work"]
    assert outcome["fit"]["policy_hash"] == report["fit"]["policy_hash"]


@pytest.mark.parametrize("value", [None, True, -1, 1.0, "2"])
def test_counted_rejects_unreported_or_invalid_work_without_losing_other_values(
    driver, value
):
    report = fixture_report()
    invocation = report["arms"]["reference"]["entries"][0]["invocations"][0]
    invocation["work"]["newton_iterations"] = value
    outcome = driver.counted([report])
    assert outcome["unknown_work"] is True
    assert outcome["known_completed_work"] == {
        "core_calls": 3,
        "newton_iterations": 4,
        "linear_solves": 6,
    }


def test_counted_accounts_preload_and_marks_missing_work_record_unknown(driver):
    report = fixture_report()
    report["arms"]["reference"]["preload_invocations"] = [
        dict(
            ordinal=0,
            unknown_work=False,
            work=dict(core_calls=2, newton_iterations=5, linear_solves=5),
        )
    ]
    report["arms"]["secant"]["entries"][0]["invocations"][0]["work"] = None
    outcome = driver.counted([report])
    assert outcome["unknown_work"] is True
    assert outcome["known_completed_work"] == {
        "core_calls": 4,
        "newton_iterations": 9,
        "linear_solves": 9,
    }


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


def test_opt_in_alphas_preserve_default_request_and_every_other_solver_knob(
    tmp_path, driver
):
    roots, plans, restored = {}, {}, {}
    for profile in driver.SOLVER_PROFILES:
        folder = tmp_path / profile
        folder.mkdir()
        roots[profile] = prepared(folder, driver, solver_profile=profile)
        plans[profile] = driver.read(roots[profile] / "experiment-plan.json")
        restored[profile] = driver.cases(roots[profile])
    default = plans[driver.DEFAULT_SOLVER_PROFILE]
    extended = plans[driver.EXTENDED_LINE_SEARCH_PROFILE]
    assert default["solver_config"]["newton"]["line_search_alphas"] == [
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    ]
    assert extended["solver_config"]["newton"]["line_search_alphas"] == [
        2.0**-k for k in range(14)
    ]
    without_alphas = deepcopy(extended["solver_config"])
    without_alphas["newton"]["line_search_alphas"] = default["solver_config"]["newton"][
        "line_search_alphas"
    ]
    assert without_alphas == default["solver_config"]
    assert default["solver_config"]["newton"]["max_iterations"] == 25
    assert extended["solver_config_hash"] != default["solver_config_hash"]
    for old, new, row, new_row in zip(
        restored[driver.DEFAULT_SOLVER_PROFILE],
        restored[driver.EXTENDED_LINE_SEARCH_PROFILE],
        default["cases"],
        extended["cases"],
        strict=True,
    ):
        legacy = driver.BoundedRCFiberDirectControlRequest(
            7,
            tuple(row["targets_m"]),
            allow_reversals=True,
            maximum_reversals=2,
        )
        assert _bytes(old.request.to_dict()) == _bytes(legacy.to_dict())
        assert old.request.request_hash != new.request.request_hash
        assert old.model.canonical_model_checksum == new.model.canonical_model_checksum
        assert old.request.targets_m == new.request.targets_m
        assert new.request.solver_config.contract_hash == extended["solver_config_hash"]
        assert new.request.to_dict() == new_row["request"]


def test_cli_requires_explicit_prepare_profile_and_freezes_exact_typed_requests(
    tmp_path, driver, monkeypatch
):
    root = tmp_path / "cli-profile"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "driver",
            "prepare",
            "--output",
            str(root),
            "--solver-profile",
            driver.EXTENDED_LINE_SEARCH_PROFILE,
        ],
    )
    driver.main()
    plan = driver.read(root / "experiment-plan.json")
    assert plan["solver_profile"] == driver.EXTENDED_LINE_SEARCH_PROFILE
    for row, case in zip(plan["cases"], driver.cases(root), strict=True):
        assert _bytes(row["request"]) == _bytes(case.request.to_dict())
        assert row["request_hash"] == case.request.request_hash
    untouched = tmp_path / "non-prepare-option"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "driver",
            "generate",
            "--output",
            str(untouched),
            "--solver-profile",
            driver.EXTENDED_LINE_SEARCH_PROFILE,
        ],
    )
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2 and not untouched.exists()


@pytest.mark.parametrize(
    "mutation",
    ["alpha", "residual", "increment", "control", "max_iterations", "missing_default"],
)
def test_rehashed_request_mutation_is_rejected_before_benchmark(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(
        tmp_path,
        driver,
        campaign=True,
        solver_profile=driver.EXTENDED_LINE_SEARCH_PROFILE,
    )
    plan = driver.read(root / "experiment-plan.json")
    row = plan["cases"][0]
    newton = row["request"]["solver_config"]["newton"]
    if mutation == "alpha":
        newton["line_search_alphas"].pop()
    elif mutation == "residual":
        newton["residual_tolerance"] *= 10
    elif mutation == "increment":
        newton["increment_tolerance"] *= 10
    elif mutation == "control":
        row["request"]["solver_config"]["control_tolerance_m"] *= 10
    elif mutation == "max_iterations":
        newton["max_iterations"] += 1
    else:
        del row["request"]["maximum_targets"]
    restored = driver.decode_bounded_rc_fiber_direct_control_request(row["request"])
    row["request_hash"] = restored.request_hash
    (root / "experiment-plan.json").write_bytes(_bytes(plan))
    driver.save(
        root, "join-fit-result.json", dict(status="HOLD", candidate_fitted=False)
    )
    callbacks = []

    def unexpected(*args, **kwargs):
        callbacks.append(True)
        raise AssertionError("modified request crossed the benchmark boundary")

    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", unexpected)
    with pytest.raises(AssertionError, match="predeclared request"):
        driver.evaluate(root)
    assert callbacks == []


def test_rehashed_solver_profile_declaration_cannot_authorize_other_tolerances(
    tmp_path, driver
):
    root = prepared(
        tmp_path, driver, solver_profile=driver.EXTENDED_LINE_SEARCH_PROFILE
    )
    plan = driver.read(root / "experiment-plan.json")
    payload = plan["cases"][0]["request"]
    payload["solver_config"]["newton"]["residual_tolerance"] *= 10
    changed = driver.decode_bounded_rc_fiber_direct_control_request(payload)
    plan["solver_config"] = changed.to_dict()["solver_config"]
    plan["solver_config_hash"] = changed.solver_config.contract_hash
    plan["cases"][0]["request_hash"] = changed.request_hash
    with pytest.raises(AssertionError, match="predeclared solver profile differs"):
        driver.cases(root, plan)


@pytest.mark.parametrize("stage", ["generate", "labels", "evaluate"])
def test_each_stage_receives_the_frozen_extended_typed_request(
    tmp_path, driver, monkeypatch, stage
):
    root = prepared(
        tmp_path,
        driver,
        campaign=True,
        solver_profile=driver.EXTENDED_LINE_SEARCH_PROFILE,
    )
    expected = tuple(case.request for case in driver.cases(root))
    seen = []

    class BoundaryReached(Exception):
        pass

    def inspect_cases(values):
        actual = tuple(case.request for case in values)
        assert actual == expected
        assert all(
            r.solver_config.newton.line_search_alphas
            == tuple(2.0**-k for k in range(14))
            for r in actual
        )
        seen.append(actual)
        raise BoundaryReached

    if stage == "generate":
        monkeypatch.setattr(
            learning,
            "run_rc_control_learning_study",
            lambda values, **kwargs: inspect_cases(values),
        )
    elif stage == "labels":
        driver.save(root, "generate-result.json", dict(status="ready"))
        driver.save(
            root,
            "generation/training-samples.json",
            [
                dict(
                    case_id=f"authored-{name}",
                    split="train",
                    sample_hash=_sha(name.encode()),
                )
                for name in "ABCD"
            ],
        )
        monkeypatch.setattr(
            driver,
            "validate_connected_partition",
            lambda *, cases, **kwargs: inspect_cases(cases),
        )
    else:
        driver.save(
            root, "join-fit-result.json", dict(status="HOLD", candidate_fitted=False)
        )

        def inspect_benchmark(model, request, **kwargs):
            assert request == expected[0]
            seen.append(request)
            raise BoundaryReached

        monkeypatch.setattr(
            driver, "benchmark_rc_control_seed_paths", inspect_benchmark
        )
    with pytest.raises(BoundaryReached):
        getattr(driver, stage)(root)
    assert len(seen) == 1


def test_actual_runtime_wrapper_passes_same_profile_to_arms_and_fresh_reference(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path, driver, solver_profile=driver.EXTENDED_LINE_SEARCH_PROFILE
    )
    case = driver.cases(root)[0]
    seen = []

    def mocked_path(compiled, request, name, callback, directory, *args):
        # Only the wrapper dispatch is real; empty path responses are synthetic.
        seen.append((directory.name, request.to_dict()))
        assert request == case.request
        return dict(
            status="complete", response_history=[], terminal_checkpoint={}, entries=[]
        )

    monkeypatch.setattr(runtime, "_path", mocked_path)
    report = _BENCHMARK_WRAPPER(
        case.model,
        case.request,
        source_revision=driver.read(root / "experiment-plan.json")["source_revision"],
        output_directory=tmp_path / "mocked-wrapper-dispatch",
        arm_order=("secant", "reference"),
    )
    assert [name for name, _ in seen] == ["secant", "reference", "fresh-reference"]
    assert all(payload == case.request.to_dict() for _, payload in seen)
    assert report["request"] == case.request.to_dict()


def _codec_policy(header, samples):
    """Author a zero-weight codec fixture; no ridge/SVD fit is performed."""
    x = np.asarray([row["features"] for row in samples])
    count = len(header["free_global_dofs"]) + 1
    scale = x.std(axis=0)
    payload = dict(
        schema_version="experimental-rc-control-secant-correction-policy.v2"
        if "arithmetic_profile" in header
        else "experimental-rc-control-secant-correction-policy.v1",
        **deepcopy(header),
        feature_mean=x.mean(axis=0).tolist(),
        feature_scale=np.where(scale > 0, scale, 1.0).tolist(),
        feature_min=x.min(axis=0).tolist(),
        feature_max=x.max(axis=0).tolist(),
        target_scale=[1.0] * count,
        weights=[[0.0] * count for _ in range(x.shape[1] + 1)],
        training_sample_hashes=[row["sample_hash"] for row in samples],
        ridge=10000.0,
        ood_margin=0.1,
    )
    payload["policy_hash"] = _sha(_bytes(payload))
    return learning.RCControlSeedPolicy(_bytes(payload).decode())


def _authored_learning_inputs(root, driver, *, write=False):
    """Typed prefix/file fixtures, never solver-produced training observations."""
    plan = driver.read(root / "experiment-plan.json")
    profile = driver.arithmetic_profile(plan)
    manifest = learning._arithmetic_manifest(profile)
    values = learning._preflight(driver.cases(root), profile)
    samples, contexts, header = [], {}, None
    for case in driver.cases(root):
        if case.split != "train":
            continue
        _, compiled, features, _, _ = values[case.case_id]
        count = len(compiled.problem.free_global_dofs) + 1
        control = compiled.problem.free_global_dofs.index(
            case.request.control_global_dof
        )
        current = dict(
            model_context_hash=features.context_hash,
            model_feature_names=list(features.feature_names),
            free_global_dofs=list(compiled.problem.free_global_dofs),
            control_free_index=control,
            solver_config_hash=case.request.solver_config.contract_hash,
        )
        if manifest is not None:
            current["arithmetic_profile"] = deepcopy(manifest)
        assert header is None or header == current
        header = current
        for index in range(1, len(case.request.targets_m)):
            accepted = (0.0, *case.request.targets_m[:index])
            coordinates = []
            for target in accepted:
                row = [0.0] * count
                row[control] = target
                coordinates.append(tuple(row))
            context = runtime.RCControlSeedContext(
                features.problem_contract_hash,
                case.request.control_global_dof,
                control,
                case.request.targets_m[index],
                accepted,
                tuple(coordinates),
            )
            sample = dict(
                case_id=case.case_id,
                split="train",
                target_index=index,
                parent_hash=_sha(f"codec-parent:{case.case_id}:{index}".encode()),
                context=context.to_dict(),
                features=learning._features(context, features).tolist(),
                correction=[0.0] * count,
            )
            if manifest is not None:
                sample.update(
                    arithmetic_profile=deepcopy(manifest),
                    label_representation="accepted-high-component-for-binary64-start.v1",
                    accepted_coordinate_compensation_m=[0.0] * count,
                )
            sample["sample_hash"] = _sha(_bytes(sample))
            samples.append(sample)
            contexts[case.case_id, index] = context
            if write:
                base = f"generation/{case.case_id}/generation/reference/{index:03d}"
                (root / base).parent.mkdir(parents=True, exist_ok=True)
                driver.save(root, base + "-context.json", context.to_dict())
                driver.save(
                    root,
                    base + "-1-step.json",
                    {"parent_checkpoint": {"state_hash": sample["parent_hash"]}},
                )
    policy = _codec_policy(header, samples)
    if write:
        driver.save(root, "generate-result.json", {"status": "ready"})
        driver.save(root, "generation/training-samples.json", samples)
        driver.save(root, "generation/policy.json", policy.to_dict())
        driver.save(
            root,
            "generation/plan.json",
            {"arithmetic_profile": manifest} if manifest is not None else {},
        )
    return plan, samples, policy, contexts, values


@pytest.mark.parametrize("solver_profile", ["default", "extended-backtracking-v1"])
def test_retained_prepare_changes_only_polishing_and_native_profile(
    tmp_path, driver, solver_profile
):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    old = prepared(old_dir, driver, solver_profile=solver_profile)
    new = prepared(
        new_dir,
        driver,
        solver_profile=solver_profile,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    binary, retained = (
        driver.read(old / "experiment-plan.json"),
        driver.read(new / "experiment-plan.json"),
    )
    assert (
        "arithmetic_profile" not in binary and driver.learning_kwargs("binary64") == {}
    )
    assert retained["arithmetic_profile"] == learning._arithmetic_manifest(
        learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    )
    assert retained["arithmetic_profile"]["terminal_refinement_limit"] == 2
    modified = deepcopy(retained["solver_config"])
    assert modified["newton"]["terminal_polishing"] is True
    modified["newton"]["terminal_polishing"] = binary["solver_config"]["newton"][
        "terminal_polishing"
    ]
    assert _bytes(modified) == _bytes(binary["solver_config"])
    for first, second in zip(binary["cases"], retained["cases"], strict=True):
        assert _bytes(first["model_artifact"]) == _bytes(second["model_artifact"])
        assert first["targets_m"] == second["targets_m"]
        assert first["request_hash"] != second["request_hash"]
        name = first["case_id"]
        assert (
            binary["case_static_features"][name]["values"]
            == retained["case_static_features"][name]["values"]
        )
        assert (
            binary["case_static_features"][name]["problem_contract_hash"]
            != retained["case_static_features"][name]["problem_contract_hash"]
        )


@pytest.mark.parametrize("stage", ["generate", "labels", "join-fit", "evaluate"])
def test_arithmetic_cli_cannot_override_non_prepare_stage(
    tmp_path, driver, monkeypatch, stage
):
    root = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        ["driver", stage, "--output", str(root), "--arithmetic-profile", "binary64"],
    )
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2 and not root.exists()


@pytest.mark.parametrize(
    "mutation",
    ["refinement1", "floatlimit", "boollimit", "force", "model", "polishing", "target"],
)
def test_coherently_rehashed_retained_mutation_fails_before_work(
    tmp_path, driver, monkeypatch, mutation
):
    root = prepared(
        tmp_path,
        driver,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    plan = driver.read(root / "experiment-plan.json")
    row = plan["cases"][0]
    if mutation in {"refinement1", "floatlimit", "boollimit"}:
        plan["arithmetic_profile"]["terminal_refinement_limit"] = {
            "refinement1": 1,
            "floatlimit": 2.0,
            "boollimit": True,
        }[mutation]
        message = "arithmetic manifest"
    elif mutation == "force":
        plan["arithmetic_profile"]["force_accumulation"] = "binary64"
        message = "arithmetic manifest"
    elif mutation == "model":
        path = root / row["model_file"]
        payload = driver.read(path)
        payload["sections"][0]["width_m"] *= 0.9
        path.write_bytes(_bytes(payload))
        row["model_artifact"] = driver.descriptor(root, row["model_file"])
        row["model_checksum"] = driver.load_neutral_json(path).canonical_model_checksum
        message = "authored model"
    elif mutation == "target":
        row["targets_m"][1] *= 0.9
        row["request"]["targets_m"] = deepcopy(row["targets_m"])
        message = "authored case"
    else:
        row["request"]["solver_config"]["newton"]["terminal_polishing"] = False
        changed = driver.decode_bounded_rc_fiber_direct_control_request(row["request"])
        row["request_hash"] = changed.request_hash
        plan["solver_config"] = changed.to_dict()["solver_config"]
        plan["solver_config_hash"] = changed.solver_config.contract_hash
        message = "solver profile"
    (root / "experiment-plan.json").write_bytes(_bytes(plan))
    receipt = driver.read(root / "prepare-result.json")
    receipt["plan_hash"] = _sha(_bytes(plan))
    (root / "prepare-result.json").write_bytes(_bytes(receipt))
    callbacks = []
    monkeypatch.setattr(driver, "generate", lambda *a, **k: callbacks.append(True))
    monkeypatch.setattr(sys, "argv", ["driver", "generate", "--output", str(root)])
    with pytest.raises(AssertionError, match=message):
        driver.main()
    assert callbacks == [] and not (root / "generate-started.json").exists()


def test_generation_forwards_retained_profile_and_defers_evaluation(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    seen = []

    class Reached(Exception):
        pass

    def mocked_study(cases, **kwargs):
        assert (
            kwargs["arithmetic_profile"]
            == learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        )
        assert kwargs["defer_evaluation"] is True
        assert kwargs["export_generation_prior_work"] is True
        assert kwargs["record_generation_assembly_work"] is True
        assert all(
            case.request.solver_config.newton.terminal_polishing is True
            for case in cases
        )
        seen.append(kwargs)
        raise Reached

    monkeypatch.setattr(learning, "run_rc_control_learning_study", mocked_study)
    with pytest.raises(Reached):
        driver.generate(root)
    assert len(seen) == 1


def test_retained_policy_requires_explicit_matching_inference_profile(tmp_path, driver):
    root = prepared(
        tmp_path,
        driver,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    plan, samples, policy, contexts, values = _authored_learning_inputs(root, driver)
    _, compiled, features, _, _ = values["authored-A"]
    args = (
        contexts["authored-A", 1],
        features,
        compiled.problem.free_global_dofs,
        plan["solver_config_hash"],
    )
    assert policy.propose(*args) is None
    assert policy.propose(*args, arithmetic_profile="binary64") is None
    assert (
        policy.propose(
            *args,
            arithmetic_profile="coherent-benchmark-retained-twofold-refinement1.v1",
        )
        is None
    )
    assert (
        policy.propose(*args, **driver.learning_kwargs(driver.arithmetic_profile(plan)))
        is not None
    )
    bad = policy.to_dict()
    bad["arithmetic_profile"]["terminal_refinement_limit"] = 1
    bad["policy_hash"] = _sha(
        _bytes({k: v for k, v in bad.items() if k != "policy_hash"})
    )
    with pytest.raises(ValueError, match="arithmetic profile"):
        learning.RCControlSeedPolicy(_bytes(bad).decode())


def test_actual_wrapper_compiles_one_retained_problem_for_every_arm(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        solver_profile=driver.EXTENDED_LINE_SEARCH_PROFILE,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    case = driver.cases(root)[0]
    _, compiled, features, _, _ = learning._preflight(
        driver.cases(root), learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    )[case.case_id]
    seen = []

    def mocked_path(native, request, name, callback, directory, *args):
        assert (
            native.problem.contract_hash
            == compiled.problem.contract_hash
            == features.problem_contract_hash
        )
        assert native.problem.coordinate_precision == "twofold-increment"
        assert native.problem.terminal_coordinate_precision == "twofold"
        assert native.problem.terminal_refinement_limit == 2
        assert request == case.request
        seen.append(directory.name)
        return dict(
            strategy=name,
            status="complete",
            response_history=[],
            terminal_checkpoint={},
            entries=[],
            source_problem_hash=native.problem.contract_hash,
            requested_targets_m=list(request.targets_m),
        )

    monkeypatch.setattr(runtime, "_path", mocked_path)
    output = tmp_path / "mocked-retained-wrapper"
    report = _BENCHMARK_WRAPPER(
        case.model,
        case.request,
        source_revision="c" * 40,
        output_directory=output,
        proposal=lambda _: None,
        proposal_identity=_sha(b"codec-only"),
        arm_order=("secant", "proposal", "reference"),
        **learning._arithmetic_kwargs(learning.RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    assert seen == ["secant", "proposal", "reference", "fresh-reference"]
    identity = driver.read(output / "request.json")
    assert (
        identity["terminal_refinement_limit"]
        == report["terminal_refinement_limit"]
        == 2
    )
    for key, value in learning._arithmetic_kwargs(
        learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    ).items():
        assert _bytes(identity[key]) == _bytes(value)
    assert identity["compiled_problem_contract_hash"] == compiled.problem.contract_hash
    # Obtain an actual generation identity from the wrapper instead of authoring
    # conditional runtime fields from the learning manifest in this test.
    from structural_analysis.benchmark import rc_control_prior_work_export as export

    study = tmp_path / "mocked-generation-identity"
    generation_report = _BENCHMARK_WRAPPER(
        case.model,
        case.request,
        source_revision="c" * 40,
        output_directory=study / case.case_id / "generation",
        record_prior_accepted_transition_work=True,
        **learning._arithmetic_kwargs(learning.RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    declaration = dict(
        case_id=case.case_id,
        split="train",
        request=case.request.to_dict(),
        model_features=features.to_dict(),
        model_checksum=case.model.canonical_model_checksum,
    )
    checked = export._case(
        export._Reader(study),
        declaration,
        {"report": generation_report, "labels_eligible": True},
        "c" * 40,
        {},
        learning._arithmetic_manifest(learning.RETAINED_LEARNING_ARITHMETIC_PROFILE),
    )
    assert checked[1].problem_contract_hash == compiled.problem.contract_hash


def test_original_oof_fitter_and_every_label_proposal_preserve_manifest(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        campaign=True,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    plan, samples, seed, contexts, values = _authored_learning_inputs(
        root, driver, write=True
    )
    fits, proposals, comparisons = [], [], []
    import prepare_rc_nested_switch_labels as fitter

    real_propose = learning.RCControlSeedPolicy.propose

    def mock_fit(selected, header, ridge, margin, *, fit_solver):
        assert header["arithmetic_profile"] == plan["arithmetic_profile"]
        assert (
            ridge == 10000.0
            and margin == 0.1
            and fit_solver == learning.SVD_RIDGE_FIT_PROFILE
        )
        fits.append([row["sample_hash"] for row in selected])
        return _codec_policy(header, selected)

    def tracked_proposal(self, context, features, dofs, solver, **kwargs):
        assert kwargs == {
            "arithmetic_profile": learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        }
        proposals.append(context.problem_contract_hash)
        return real_propose(self, context, features, dofs, solver, **kwargs)

    def mock_comparison(model, request, **kwargs):
        for key, value in learning._arithmetic_kwargs(
            learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        ).items():
            assert kwargs[key] == value
        assert request.solver_config.newton.terminal_polishing is True
        kwargs["proposal"](kwargs["accepted_context"])
        comparisons.append(kwargs["output_directory"])
        return fixture_report()

    monkeypatch.setattr(driver, "fit_declared_seeds", fitter.fit_declared_seeds)
    monkeypatch.setattr(learning, "_fit", mock_fit)
    monkeypatch.setattr(learning.RCControlSeedPolicy, "propose", tracked_proposal)
    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", mock_comparison)
    result = driver.labels(root)
    assert len(fits) == 6 and result["fits"] == 6
    assert len(comparisons) == len(proposals) == result["comparisons"] == 180


def test_retained_generation_header_mismatch_stops_before_teacher_fit(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    _, samples, seed, _, values = _authored_learning_inputs(root, driver, write=True)
    # A coherent legacy policy hash still cannot relabel the current native profile.
    payload = seed.to_dict()
    del payload["arithmetic_profile"]
    payload["schema_version"] = "experimental-rc-control-secant-correction-policy.v1"
    payload["policy_hash"] = _sha(
        _bytes({k: v for k, v in payload.items() if k != "policy_hash"})
    )
    (root / "generation/policy.json").write_bytes(_bytes(payload))
    with pytest.raises(AssertionError, match="original seed arithmetic profile"):
        driver.labels(root)
    assert not (root / "retained-labels").exists()


def test_fallback_full_paths_use_retained_profile_even_without_fitted_pair(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        campaign=True,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    driver.save(
        root, "join-fit-result.json", dict(status="HOLD", candidate_fitted=False)
    )
    calls = []

    def mocked_comparison(model, request, **kwargs):
        assert "proposal" not in kwargs
        assert request.solver_config.newton.terminal_polishing is True
        for key, value in learning._arithmetic_kwargs(
            learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        ).items():
            assert kwargs[key] == value
        calls.append(kwargs["arm_order"])
        return fixture_report()

    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", mocked_comparison)
    result = driver.evaluate(root)
    assert (
        result["comparisons"] == len(calls) == 18
        and result["candidate_evaluated"] is False
    )


def test_frozen_candidate_full_paths_pass_profile_to_policy_and_all_arms(
    tmp_path, driver, monkeypatch
):
    root = prepared(
        tmp_path,
        driver,
        campaign=True,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
    )
    plan, samples, policy, contexts, values = _authored_learning_inputs(root, driver)
    selected = dict(
        seed_policy=policy.to_dict(), gate_policy={"authored_gate_codec": True}
    )
    selected["pair_hash"] = _sha(_bytes(selected))
    pair = dict(selected, selected_pair=deepcopy(selected))
    driver.save(root, "frozen-candidate-pair.json", pair)
    driver.save(
        root,
        "join-fit-result.json",
        dict(
            candidate_fitted=True,
            pair_hash=pair["pair_hash"],
            candidate_artifact=driver.descriptor(root, "frozen-candidate-pair.json"),
        ),
    )
    bindings, calls, proposals = [], [], []
    real_propose = learning.RCControlSeedPolicy.propose

    def tracked(self, context, features, dofs, solver_hash, **kwargs):
        assert kwargs == {
            "arithmetic_profile": learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        }
        proposals.append(context.problem_contract_hash)
        return real_propose(self, context, features, dofs, solver_hash, **kwargs)

    def binding(gate, *, policy, model_features):
        assert policy.policy_hash == selected["seed_policy"]["policy_hash"]
        assert model_features.problem_contract_hash in {
            v[2].problem_contract_hash for v in values.values()
        }
        bindings.append(model_features.problem_contract_hash)
        return dict(guard=lambda _: False, guard_identity=_sha(b"codec-guard"))

    def mocked_comparison(model, request, **kwargs):
        for key, value in learning._arithmetic_kwargs(
            learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        ).items():
            assert kwargs[key] == value
        assert kwargs["record_prior_accepted_transition_work"] is True
        assert kwargs["material_capture_scope"] == "proposal-only"
        name = kwargs["output_directory"].name.rsplit("-", 1)[0]
        _, compiled, features, _, _ = values[name]
        count = len(compiled.problem.free_global_dofs) + 1
        control = compiled.problem.free_global_dofs.index(request.control_global_dof)
        accepted = [0.0] * count
        accepted[control] = request.targets_m[0]
        context = runtime.RCControlSeedContext(
            features.problem_contract_hash,
            request.control_global_dof,
            control,
            request.targets_m[1],
            (0.0, request.targets_m[0]),
            (tuple([0.0] * count), tuple(accepted)),
        )
        kwargs["proposal"](context)
        calls.append(kwargs["arm_order"])
        report = fixture_report()
        report["arms"]["proposal"] = deepcopy(report["arms"]["secant"])
        report["comparisons"]["proposal"] = deepcopy(report["comparisons"]["secant"])
        report["prior_work_source_setup_cost"] = {"wall_ns": 2, "cpu_ns": 1}
        return report

    monkeypatch.setattr(
        driver, "FullTrainingPriorWorkCostMarginGate", lambda _: object()
    )
    monkeypatch.setattr(driver, "full_training_prior_work_guard_binding", binding)
    monkeypatch.setattr(learning.RCControlSeedPolicy, "propose", tracked)
    monkeypatch.setattr(driver, "benchmark_rc_control_seed_paths", mocked_comparison)
    result = driver.evaluate(root)
    assert len(bindings) == len(calls) == len(proposals) == result["comparisons"] == 18
    assert result["candidate_evaluated"] is True
