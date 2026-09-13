"""Retained engineering rows with synthetic material assertions; no physical proof.

No solver, policy fitting or child worker is executed. The new memory statistics
are deliberately synthetic, while their stored source/epoch bindings are tested.
"""

from copy import deepcopy
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import subprocess

import pytest

from tests.test_fiber_frame_candidate_process import request_payload
from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.benchmark import fiber_frame_candidate_process as process
from structural_analysis.benchmark import fiber_frame_candidate_review as review
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from structural_analysis.benchmark import fiber_frame_constitutive_history as material
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

SOURCE = "a" * 40
LIMITS = design.FiberFrameMaterialHistoryLimits(0.002, 0.2, 0.2)
FIXTURE = (
    Path(__file__).parent
    / "fixtures/fiber_frame_candidate_review/observed-suite.json.gz"
)


def rehash(value, key="report_hash"):
    value[key] = canonical_hash({k: v for k, v in value.items() if k != key})


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("no analysis, training or subprocess allowed")

    for target, key in (
        (public, "analyze_public_rc_fiber_frame"),
        (learning, "_fit"),
        (learning, "train_fiber_frame_candidate_policy"),
        (subprocess, "Popen"),
        (subprocess, "run"),
    ):
        monkeypatch.setattr(target, key, forbidden)


@pytest.fixture(scope="module")
def retained():
    packed = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    files = {r["path"]: json.loads(r["utf8"]) for r in packed["files"]}
    return files[packed["suite_file"]]


@pytest.fixture
def material_request(tmp_path, retained):
    value = request_payload()
    value["warmups"] = 0
    value["schema_version"] = process.REQUEST_MATERIAL_SCHEMA
    value["cases"][0]["history_limits"] = retained["declaration"]["cases"][0][
        "input_binding"
    ]["history_limits"]
    value["cases"][0]["material_history_limits"] = asdict(LIMITS)
    path = tmp_path / "request.json"
    path.write_bytes(process.process._bytes(value))
    return path, value


def with_material(row, maximum=0.1):
    row = deepcopy(row)
    response, result = row["response_history"], row["result"]
    history = response["history"]
    states = []
    previous = None
    for index in range(history["epoch_count"] + 1):
        step = history["steps"][index - 1] if index else None
        groups = {}
        for kind, fields in material._FIELDS.items():
            count = sum(
                f["material_kind"] == kind for f in history["steps"][0]["fiber_results"]
            )
            stats = {}
            for field, (unit, interpretation) in fields.items():
                number = (
                    maximum * index / history["epoch_count"]
                    if field == "tensile_damage"
                    else 0.0
                )
                changed = count if field == "tensile_damage" and maximum > 0 else 0
                stats[field] = dict(
                    unit=unit,
                    interpretation=interpretation,
                    minimum=number,
                    maximum=number,
                    maximum_absolute=number,
                    positive_value_point_count=count if number > 0 else 0,
                    changed_from_parent_point_count=changed if index else None,
                    increased_from_parent_point_count=changed if index else None,
                    decreased_from_parent_point_count=0 if index else None,
                    parent_comparison_reason=None if index else "genesis_has_no_parent",
                )
            groups[kind] = {"point_count": count, "fields": stats}
        checkpoint_hash = (
            step["bindings"]["checkpoint_state_hash"]
            if index
            else result["checkpoint"]["root_state_hash"]
        )
        states.append(
            dict(
                epoch=index,
                step_index=index,
                load_factor=index / history["epoch_count"],
                checkpoint_state_hash=checkpoint_hash,
                parent_checkpoint_state_hash=previous,
                engineering_recovery_hash=step["recovery_hash"] if index else None,
                total_dissipated_energy_mj=step["metrics"]["total_dissipated_energy_mj"]
                if index
                else None,
                engineering_recovery_reason=None
                if index
                else "genesis_has_no_engineering_recovery",
                material_point_count=sum(g["point_count"] for g in groups.values()),
                materials=groups,
            )
        )
        previous = checkpoint_hash
    report = dict(
        schema_version=material.SCHEMA_VERSION,
        status="ready",
        contract_pass=True,
        accepted_epoch_count=history["epoch_count"],
        states=states,
        claim_boundary=dict(material._CLAIMS),
        scope={
            "validation": "existing_full_public_response_history_accessor_then_retained_material_memory_aggregation",
            "material_point": "member_integration_point_modeled_fiber_not_individual_bar",
            "state_value_counts": "strictly_positive_native_values_not_current_step_yield_events",
            "transition_counts": "exact_comparison_with_immediately_preceding_accepted_state",
            "total_energy": "original_per_epoch_engineering_recovery_MJ_not_density_or_epoch_sum",
        },
        bindings=dict(
            source_result_hash=result["result_hash"],
            canonical_model_checksum=row["model_checksum"],
            input_checksum=result["input_checksum"],
            problem_contract_hash=result["contract_bindings"]["problem_contract_hash"],
            checkpoint_chain_hash=result["checkpoint"]["chain_hash"],
            checkpoint_artifact_hash=result["checkpoint"]["artifact_hash"],
            checkpoint_artifact_byte_length=result["checkpoint"][
                "artifact_byte_length"
            ],
            response_history_report_hash=response["report_hash"],
            engineering_history_hash=history["history_hash"],
        ),
    )
    rehash(report)
    violated = []
    for metric, (limit, kind, field) in design.MATERIAL_HISTORY_METRICS.items():
        observed = max(
            s["materials"][kind]["fields"][field]["maximum"] for s in states[1:]
        )
        row["performance"][metric] = observed
        if observed > getattr(LIMITS, limit):
            violated.append(metric)
    row.update(
        constitutive_history=report,
        full_material_history_verification_pass=True,
        material_history_limit_status="fail" if violated else "pass",
        violated_material_history_limits=violated,
        material_history_failure=None,
    )
    return row


@pytest.fixture
def arguments(material_request):
    path, payload = material_request
    return {
        **process._case_arguments(payload["cases"][0], path.parent),
        "source_revision": SOURCE,
    }


@pytest.fixture
def stub_rows(retained, monkeypatch):
    original = next(
        r["report"]["rows"] for r in retained["runs"] if r["strategy"] == "oracle"
    )
    by_checksum = {r["model_checksum"]: r for r in original}
    calls = []

    def evaluate(candidate_id, model, config, prices, terminal_limits, *args, **kwargs):
        assert (
            kwargs["material_history_limits"] == LIMITS
            and kwargs["history_limits"] is not None
        )
        calls.append(candidate_id)
        row = with_material(
            by_checksum[model.canonical_model_checksum],
            0.1 if candidate_id == "baseline" else 0.4,
        )
        row.pop("analysis_requested", None)
        row.update(candidate_id=candidate_id, reference_and_quantity_wall_ns=0)
        return row

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    return calls


def test_material_limits_change_all_frozen_plans_before_execution(arguments):
    original = arm.prepare_fiber_frame_candidate_search_expectations(**arguments)
    changed = arm.prepare_fiber_frame_candidate_search_expectations(
        **dict(
            arguments,
            material_history_limits=design.FiberFrameMaterialHistoryLimits(
                0.001, 0.3, 0.4
            ),
        )
    )
    assert original["input_binding"]["material_history_limits"] == asdict(LIMITS)
    for strategy in arm.STRATEGIES:
        assert (
            original[strategy]["frozen_plan_hash"]
            != changed[strategy]["frozen_plan_hash"]
        )
        assert (
            original[strategy]["candidate_pool"] == changed[strategy]["candidate_pool"]
        )


@pytest.mark.parametrize("strategy", arm.STRATEGIES)
def test_material_arm_oracle_selection_and_denominator(arguments, stub_rows, strategy):
    frozen = arm.prepare_fiber_frame_candidate_search_expectations(**arguments)
    if strategy == "oracle":
        report = arm.run_fiber_frame_candidate_search_oracle(
            **arguments, expected_plan_hash=frozen[strategy]["frozen_plan_hash"]
        )
        arm.validate_fiber_frame_candidate_search_oracle_report(report, frozen)
        assert report["schema_version"] == arm.ORACLE_MATERIAL_SCHEMA_VERSION
        assert report["cost_accounting"]["total_analysis_request_count"] == 3
        audit = search._audit_outcomes(
            frozen["learned"]["candidate_pool"], [], report["rows"], True, True
        )
        assert audit["predicted_material_history_safety_available"] is False
        assert audit["missed_feasible_count"] == 0
    else:
        report = arm.run_fiber_frame_candidate_search_arm(
            **arguments,
            strategy=strategy,
            expected_plan_hash=frozen[strategy]["frozen_plan_hash"],
        )
        arm.validate_fiber_frame_candidate_search_arm_report(
            report, frozen, strategy=strategy
        )
        assert report["schema_version"] == arm.ARM_MATERIAL_SCHEMA_VERSION
        assert report["arm"]["final_selection"]["candidate_id"] == "baseline"
        assert report["arm"]["cost_accounting"]["total_analysis_request_count"] == 2
        assert (
            report["arm"]["design_comparison"]["schema_version"]
            == design.DESIGN_MATERIAL_HISTORY_COMPARISON_SCHEMA
        )
    assert (
        report["cost_accounting"]["training_execution_count"] == 0
        and report["report_contract_pass"] is True
    )
    assert len(stub_rows) == (3 if strategy == "oracle" else 2)


def test_inprocess_suite_validates_nested_v3_and_material_oracle(arguments, stub_rows):
    options = dict(arguments)
    options.pop("source_revision")
    case = suite.FiberFrameCandidateSearchCase("material", **options)
    result = suite.benchmark_fiber_frame_candidate_search_suite(
        (case,), source_revision=SOURCE
    )
    payload = result.to_dict()
    assert payload["schema_version"] == suite.MATERIAL_SCHEMA_VERSION
    assert payload["status"] == "ready", [
        (r.get("failure"), r.get("status")) for r in payload["runs"]
    ]
    assert len(stub_rows) == 14
    for row in payload["runs"]:
        assert (
            row["comparison_report"]["schema_version"]
            == search.SEARCH_MATERIAL_HISTORY_SCHEMA
        )
        assert (
            row["comparison_report"]["arms"][1]["final_selection"]["candidate_id"]
            == "baseline"
        )
    assert (
        result.design_comparison("material", "learned").to_dict()["schema_version"]
        == design.DESIGN_MATERIAL_HISTORY_COMPARISON_SCHEMA
    )


@pytest.fixture
def material_row(retained):
    report = retained["runs"][0]["report"]
    row = with_material(report["arm"]["baseline"])
    binding = deepcopy(report["input_binding"])
    binding["material_history_limits"] = asdict(LIMITS)
    return row, binding


def test_material_available_unavailable_and_selection(material_row):
    row, binding = material_row
    suite._validate_material_history_row(row, binding)
    row.update(
        constitutive_history=None,
        full_material_history_verification_pass=False,
        material_history_limit_status="unavailable",
        material_history_failure={"kind": "material_history_recovery_failed"},
    )
    for key in design.MATERIAL_HISTORY_METRICS:
        row["performance"].pop(key)
    suite._validate_material_history_row(row, binding)
    assert (
        design._verified_for_requested_scopes(row) is False
        and search._winner([row]) is None
    )


MUTATIONS = [
    ("flag", lambda r: r.update(full_material_history_verification_pass=1)),
    ("missing", lambda r: r.update(constitutive_history=None)),
    ("history authority", lambda r: r.update(full_history_verification_pass=False)),
    *[
        (
            field,
            lambda r, field=field: r["constitutive_history"]["bindings"].update(
                {field: "sha256:" + "0" * 64}
            ),
        )
        for field in (
            "source_result_hash",
            "checkpoint_artifact_hash",
            "input_checksum",
            "response_history_report_hash",
        )
    ],
    ("epoch", lambda r: r["constitutive_history"]["states"].pop(1)),
    *[
        (
            field,
            lambda r, field=field: r["constitutive_history"]["states"][1].update(
                {field: "sha256:" + "0" * 64}
            ),
        )
        for field in ("parent_checkpoint_state_hash", "engineering_recovery_hash")
    ],
    (
        "energy",
        lambda r: r["constitutive_history"]["states"][1].update(
            total_dissipated_energy_mj=1.0
        ),
    ),
    (
        "scope",
        lambda r: r["constitutive_history"]["scope"].update(
            independent_physical_validation=True
        ),
    ),
    (
        "claim",
        lambda r: r["constitutive_history"]["claim_boundary"].update(
            state_changes_identify_solver_yield_events=True
        ),
    ),
    (
        "points",
        lambda r: r["constitutive_history"]["states"][1]["materials"]["steel"].update(
            point_count=100
        ),
    ),
    (
        "performance",
        lambda r: r["performance"].update(history_maximum_concrete_tensile_damage=0.0),
    ),
    ("decision", lambda r: r.update(material_history_limit_status="fail")),
    (
        "violation",
        lambda r: r.update(
            violated_material_history_limits=["history_maximum_concrete_tensile_damage"]
        ),
    ),
    ("failure", lambda r: r.update(material_history_failure={"kind": "failed"})),
]


@pytest.mark.parametrize("label,mutate", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_rehashed_material_contradictions_rejected(material_row, label, mutate):
    row, binding = material_row
    mutate(row)
    if row["constitutive_history"] is not None:
        rehash(row["constitutive_history"])
    with pytest.raises((ValueError, KeyError, TypeError)):
        suite._validate_material_history_row(row, binding)


@pytest.mark.parametrize(
    "key,value",
    [
        ("increased_from_parent_point_count", 999),
        ("decreased_from_parent_point_count", 1),
        ("maximum", 0),
        ("positive_value_point_count", True),
        ("positive_value_point_count", 0),
        ("extra", 1),
    ],
)
def test_material_native_statistics_consistency(material_row, key, value):
    row, binding = material_row
    row["constitutive_history"]["states"][1]["materials"]["concrete"]["fields"][
        "tensile_damage"
    ][key] = value
    rehash(row["constitutive_history"])
    with pytest.raises(ValueError):
        suite._validate_material_history_row(row, binding)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(schema_version=process.REQUEST_SCHEMA),
        lambda p: p["cases"][0].update(history_limits=None),
        lambda p: p["cases"][0].update(material_history_limits=None),
        lambda p: p["cases"][0]["material_history_limits"].update(
            maximum_concrete_tensile_damage=1.01
        ),
        lambda p: p["cases"][0]["material_history_limits"].pop(
            "maximum_steel_accumulated_plastic_strain"
        ),
    ],
)
def test_bad_request_rejected_before_launch(material_request, tmp_path, mutation):
    path, payload = material_request
    mutation(payload)
    path.write_bytes(process.process._bytes(payload))
    output = tmp_path / "invalid"
    output.mkdir()
    with pytest.raises((ValueError, KeyError, TypeError)):
        process._freeze_inputs(path, output, source_revision=SOURCE)


def test_mixed_versions_and_worker_downgrade(material_request, tmp_path):
    path, payload = material_request
    legacy = deepcopy(payload["cases"][0])
    legacy["case_id"] = "legacy"
    legacy.pop("material_history_limits")
    payload["cases"].append(legacy)
    path.write_bytes(process.process._bytes(payload))
    output = tmp_path / "mixed"
    output.mkdir()
    frozen = process._freeze_inputs(path, output, source_revision=SOURCE)
    assert [process._worker_schema(c["request"]) for c in frozen["cases"]] == [
        process.WORKER_MATERIAL_SCHEMA,
        process.WORKER_SCHEMA,
    ]
    case = frozen["cases"][0]
    worker = dict(
        schema_version=process.WORKER_SCHEMA,
        case=case["request"],
        strategy="learned",
        expected_plan_hash=case["expectations"]["learned"]["frozen_plan_hash"],
        expected_inputs=[],
        online_completion_hashes={},
    )
    target = tmp_path / "worker-request.json"
    target.write_bytes(process.process._bytes(worker))
    checked = process._validate_worker(
        tmp_path / "missing", target, case["expectations"], source_revision=SOURCE
    )
    assert (
        checked["report_contract_pass"] is False
        and "schema mismatch" in checked["failure"]["report"]
    )


def test_unlaunched_v2_suite_keeps_denominators_and_review(
    material_request, tmp_path, monkeypatch
):
    path, _ = material_request
    monkeypatch.setattr(process, "_unchanged", lambda *_: False)
    result = process.run_fiber_frame_candidate_process_suite(
        path, source_revision=SOURCE, output_directory=tmp_path / "suite"
    )
    assert (
        result["schema_version"] == process.MATERIAL_SCHEMA_VERSION
        and result["status"] == "incomplete"
    )
    assert len(result["runs"]) == 6 and all(not r["attempted"] for r in result["runs"])
    assert result["cost_accounting"]["current_analysis_request_count"] == 0
    manifest = review.write_fiber_frame_candidate_process_review_bundle(
        tmp_path / "suite/suite.json", tmp_path / "review"
    )
    assert (
        json.loads(manifest.read_bytes())["schema_version"]
        == review.MATERIAL_SCHEMA_VERSION
    )
    assert (
        review.validate_fiber_frame_candidate_process_review_bundle(
            tmp_path / "review"
        )["suite"]["status"]
        == "incomplete"
    )
    damaged = json.loads(manifest.read_bytes())
    damaged["schema_version"] = review.SCHEMA_VERSION
    manifest.write_bytes(process.process._bytes(damaged))
    with pytest.raises(ValueError, match="review schema"):
        review.validate_fiber_frame_candidate_process_review_bundle(tmp_path / "review")


def test_integer_material_limits_keep_raw_bytes_and_normalize_semantic_binding(
    material_request, tmp_path
):
    path, payload = material_request
    raw_limits = {key: (0 if "plastic" in key else 1) for key in asdict(LIMITS)}
    payload["cases"][0]["material_history_limits"] = raw_limits
    path.write_bytes(process.process._bytes(payload))
    output = tmp_path / "integers"
    output.mkdir()
    frozen = process._freeze_inputs(path, output, source_revision=SOURCE)
    case = frozen["cases"][0]
    assert case["request"]["material_history_limits"] == raw_limits
    expected = case["expectations"]["input_binding"]["material_history_limits"]
    assert all(type(v) is float for v in expected.values())
    worker = dict(
        schema_version=process.WORKER_MATERIAL_SCHEMA,
        case=case["request"],
        strategy="learned",
        expected_plan_hash=case["expectations"]["learned"]["frozen_plan_hash"],
        expected_inputs=[],
        online_completion_hashes={},
    )
    target = tmp_path / "worker.json"
    reads = []

    def read(file, limit):
        reads.append(file)
        if file == target:
            return process.process._bytes(worker)
        raise ValueError("reached manifest after normalized material binding")

    checked = process._validate_worker(
        tmp_path / "worker",
        target,
        case["expectations"],
        source_revision=SOURCE,
        read=read,
    )
    assert len(reads) == 2 and reads[-1].name == "manifest.json"
    assert (
        checked["failure"]["report"]
        == "reached manifest after normalized material binding"
    )


@pytest.mark.parametrize(
    "mutation",
    ["schema", "selection", "bundle schema", "bundle limits", "frozen material"],
)
def test_rehashed_arm_material_downgrades_and_selection_rejected(
    arguments, stub_rows, mutation
):
    frozen = arm.prepare_fiber_frame_candidate_search_expectations(**arguments)
    report = arm.run_fiber_frame_candidate_search_arm(**arguments, strategy="learned")
    if mutation == "schema":
        report["schema_version"] = arm.ARM_SCHEMA_VERSION
    elif mutation == "selection":
        report["arm"]["final_selection"] = next(
            r for r in report["arm"]["candidate_outcomes"] if r["analysis_requested"]
        )
    elif mutation == "frozen material":
        report["input_binding"]["material_history_limits"][
            "maximum_concrete_tensile_damage"
        ] = 0.9
    else:
        bundle = report["arm"]["design_comparison"]
        if mutation == "bundle schema":
            bundle["schema_version"] = design.DESIGN_HISTORY_COMPARISON_SCHEMA
        else:
            bundle["identity"]["material_history_limits"][
                "maximum_concrete_tensile_damage"
            ] = 0.9
        bundle["experiment_identity_hash"] = canonical_hash(bundle["identity"])
        rehash(bundle)
    rehash(report)
    with pytest.raises(ValueError):
        arm.validate_fiber_frame_candidate_search_arm_report(
            report, frozen, strategy="learned"
        )
