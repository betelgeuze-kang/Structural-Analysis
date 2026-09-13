"""Replay one sealed observation; these tests never launch or train anything."""

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_candidate_process as process
from structural_analysis.benchmark import fiber_frame_candidate_review as review
from structural_analysis.benchmark import fiber_frame_runtime_process as codec
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIXTURE = (
    Path(__file__).parent
    / "fixtures/fiber_frame_candidate_review/observed-suite.json.gz"
)
FIXTURE_SHA = "5df1a41f2a5387be864077d5472c9e55f45ca620a1e2b6a987e2f65c2a18ab1f"


def _forbid_execution(patch):
    def forbidden(*args, **kwargs):
        pytest.fail("retained review must not execute, fit, collect, or launch")

    for target, name in (
        (subprocess, "Popen"),
        (subprocess, "run"),
        (public_api, "analyze_public_rc_fiber_frame"),
        (learning, "train_fiber_frame_candidate_policy"),
        (learning, "_fit"),
        (process, "_freeze_inputs"),
        (process, "_launch_worker"),
        (codec, "_run_fiber_frame_process"),
    ):
        patch.setattr(target, name, forbidden)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    _forbid_execution(monkeypatch)


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    encoded = FIXTURE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == FIXTURE_SHA
    fixture = json.loads(gzip.decompress(encoded))
    assert fixture["schema_version"] == "rc-fiber-candidate-review-test-fixture.v1"
    root = tmp_path_factory.mktemp("candidate-review-retained")
    names = set()
    for row in fixture["files"]:
        name = row["path"]
        path = PurePosixPath(name)
        assert not path.is_absolute() and ".." not in path.parts and str(path) == name
        assert name not in names
        names.add(name)
        raw = row["utf8"].encode("utf-8")
        assert row["byte_length"] == len(raw)
        assert row["sha256"] == codec._digest(raw)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    assert len(names) == 71
    return root, fixture


@pytest.fixture(scope="module")
def complete_bundle(retained, tmp_path_factory):
    root, fixture = retained
    destination = tmp_path_factory.mktemp("candidate-review-output") / "bundle"
    with pytest.MonkeyPatch.context() as patch:
        _forbid_execution(patch)
        manifest = review.write_fiber_frame_candidate_process_review_bundle(
            root / fixture["suite_file"], destination
        )
    assert manifest == destination / "manifest.json"
    return destination


@pytest.fixture
def source(retained, tmp_path):
    root, fixture = retained
    destination = tmp_path / "source"
    shutil.copytree(root / "suite", destination)
    return destination / "suite.json"


@pytest.fixture
def bundle(complete_bundle, tmp_path):
    destination = tmp_path / "bundle"
    shutil.copytree(complete_bundle, destination)
    return destination


def _load(path):
    return codec._json(path.read_bytes())


def _write(path, value):
    path.write_bytes(codec._bytes(value))


def _rehash(value, key="report_hash"):
    value[key] = canonical_hash({k: v for k, v in value.items() if k != key})


def _write_suite(path, suite):
    _rehash(suite)
    _write(path, suite)


def _worker_directory(source, slot):
    return source.parent / "workers" / PurePosixPath(slot["worker_directory"]).name


def _reseal_worker(source, suite, index):
    slot = suite["runs"][index]
    directory = _worker_directory(source, slot)
    report, resources, manifest = slot["report"], slot["resources"], slot["manifest"]
    _rehash(report)
    raw = codec._bytes(report)
    resources.update(
        search_sha256=codec._digest(raw),
        search_byte_length=len(raw),
        report_bytes_written=len(raw),
    )
    for name, value in (("search.json", report), ("resources.json", resources)):
        _write(directory / name, value)
        data = (directory / name).read_bytes()
        manifest["artifacts"][name] = review._raw_identity(data)
    _write(directory / "manifest.json", manifest)
    _write_suite(source, suite)


def test_relocated_review_uses_only_copied_bytes_and_preserves_eight_m2_pairs(
    complete_bundle, retained, monkeypatch
):
    original_open = Path.open
    original_root = "/tmp/structural-candidate-process-observation.5TRGr2"

    def guarded_open(path, *args, **kwargs):
        assert not str(path).startswith(original_root)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(
        process, "_identity", lambda *_: pytest.fail("original identity reader called")
    )
    checked = review.validate_fiber_frame_candidate_process_review_bundle(
        complete_bundle
    )
    manifest, suite = checked["manifest"], checked["suite"]
    assert suite["status"] == "ready" and len(suite["runs"]) == 12
    assert len(manifest["artifacts"]) == 54
    assert len(manifest["comparisons"]) == 8
    assert suite["cost_accounting"]["current_analysis_request_count"] == 28
    assert suite["cost_accounting"]["historical_training_analysis_request_count"] == 4
    assert len(suite["cost_accounting"]["training_artifacts_charged_once"]) == 1
    root, fixture = retained
    assert (complete_bundle / "suite.json").read_bytes() == (
        root / fixture["suite_file"]
    ).read_bytes()
    expected = {
        (row["case_id"], row["phase"], row["repetition"], row["strategy"]): row
        for row in fixture["expected_comparisons"]
    }
    for row in manifest["comparisons"]:
        key = tuple(
            row[name] for name in ("case_id", "phase", "repetition", "strategy")
        )
        old = root / expected.pop(key)["directory"]
        new = (complete_bundle / row["manifest_file"]).parent
        for name in ("manifest.json", "comparison.json"):
            assert (new / name).read_bytes() == (old / name).read_bytes()
    assert not expected
    for row in manifest["artifacts"]:
        relative = PurePosixPath(row["source_path"]).relative_to(
            original_root + "/suite"
        )
        assert (complete_bundle / row["file"]).read_bytes() == (
            root / "suite" / str(relative)
        ).read_bytes()
    checked["suite"]["claims"]["generalized_speedup_claimed"] = True
    assert (
        _load(complete_bundle / "suite.json")["claims"]["generalized_speedup_claimed"]
        is False
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-slot",
        "duplicate-slot",
        "slot-order",
        "aggregate-count",
        "shared-training",
        "parent-type",
        "parent-scope",
        "parent-subset",
        "case-selection",
        "authority",
    ],
)
def test_rehashed_suite_tampering_is_rejected_before_output(source, tmp_path, mutation):
    suite = _load(source)
    if mutation == "missing-slot":
        suite["runs"].pop()
    elif mutation == "duplicate-slot":
        suite["runs"][1] = deepcopy(suite["runs"][0])
    elif mutation == "slot-order":
        suite["runs"][0]["execution_order"].reverse()
    elif mutation == "aggregate-count":
        suite["cost_accounting"]["current_analysis_request_count"] -= 1
    elif mutation == "shared-training":
        suite["cost_accounting"]["historical_training_analysis_request_count"] *= 2
    elif mutation == "parent-type":
        suite["resource_accounting"]["parent_preflight_is_subset"] = 1
    elif mutation == "parent-scope":
        suite["resource_accounting"]["parent_scope"] = "worker_and_parent_combined"
    elif mutation == "parent-subset":
        suite["resource_accounting"]["parent_cpu_time_ns"] = 0
    elif mutation == "case-selection":
        suite["case_summaries"][0]["measured_pairs"][0]["selected_candidate_ids"][
            "learned"
        ] = "narrow"
    else:
        suite["claims"]["production_promotion_eligible"] = True
    _write_suite(source, suite)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError):
        review.write_fiber_frame_candidate_process_review_bundle(source, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation", ["count", "selection", "duplicate-pid", "peak-type"]
)
def test_rehashed_worker_and_outer_bytes_cannot_detach_semantics(
    source, tmp_path, mutation
):
    suite = _load(source)
    slot = suite["runs"][1]
    if mutation == "count":
        slot["report"]["cost_accounting"]["total_analysis_request_count"] = 0
    elif mutation == "selection":
        slot["report"]["arm"]["final_selection"]["candidate_id"] = "narrow"
    elif mutation == "duplicate-pid":
        slot["manifest"]["worker_pid"] = suite["runs"][0]["manifest"]["worker_pid"]
        slot["resources"]["worker_pid"] = slot["manifest"]["worker_pid"]
    else:
        slot["resources"]["peak_memory_bytes"] = float(
            slot["resources"]["peak_memory_bytes"]
        )
    _reseal_worker(source, suite, 1)
    with pytest.raises(ValueError):
        review.write_fiber_frame_candidate_process_review_bundle(
            source, tmp_path / "rejected"
        )


def test_oracle_request_binds_its_own_online_predecessors(source, tmp_path):
    suite = _load(source)
    slot = suite["runs"][2]
    request = source.parent / "requests" / PurePosixPath(slot["request_file"]).name
    payload = _load(request)
    payload["online_completion_hashes"]["learned"] = "sha256:" + "0" * 64
    _write(request, payload)
    slot["request_identity"].update(review._raw_identity(request.read_bytes()))
    _write_suite(source, suite)
    with pytest.raises(ValueError, match="worker request"):
        review.write_fiber_frame_candidate_process_review_bundle(
            source, tmp_path / "rejected"
        )


def test_changed_frozen_bytes_are_rejected_without_reading_external_originals(
    source, tmp_path
):
    model = source.parent / "inputs/model-000.json"
    model.write_bytes(model.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="frozen declaration"):
        review.write_fiber_frame_candidate_process_review_bundle(
            source, tmp_path / "rejected"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "traversal",
        "absolute",
        "symlink",
        "source-escape",
        "duplicate",
        "missing",
        "suite-duplicate",
        "length-type",
        "comparison-missing",
        "comparison-swap",
        "comparison-worker",
    ],
)
def test_portable_manifest_tampering_is_rejected(bundle, tmp_path, mutation):
    path = bundle / "manifest.json"
    manifest = _load(path)
    artifact = manifest["artifacts"][0]
    if mutation == "traversal":
        artifact["file"] = "../outside.json"
    elif mutation == "absolute":
        artifact["file"] = "/tmp/outside.json"
    elif mutation == "symlink":
        target = bundle / artifact["file"]
        outside = tmp_path / "outside.json"
        target.replace(outside)
        target.symlink_to(outside)
    elif mutation == "source-escape":
        artifact["source_path"] = "/elsewhere/input.json"
    elif mutation == "duplicate":
        manifest["artifacts"].append(deepcopy(artifact))
    elif mutation == "missing":
        manifest["artifacts"].pop()
    elif mutation == "suite-duplicate":
        artifact["file"] = "suite.json"
    elif mutation == "length-type":
        artifact["byte_length"] = float(artifact["byte_length"])
    elif mutation == "comparison-missing":
        manifest["comparisons"].pop()
    elif mutation == "comparison-swap":
        manifest["comparisons"][0], manifest["comparisons"][1] = (
            manifest["comparisons"][1],
            manifest["comparisons"][0],
        )
    else:
        manifest["comparisons"][0]["worker_report_hash"] = "sha256:" + "0" * 64
    _write(path, manifest)
    with pytest.raises(ValueError):
        review.validate_fiber_frame_candidate_process_review_bundle(bundle)


def test_nested_comparison_raw_corruption_is_rejected(bundle):
    manifest = _load(bundle / "manifest.json")
    path = (
        bundle / manifest["comparisons"][0]["manifest_file"]
    ).parent / "comparison.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="comparison bytes"):
        review.validate_fiber_frame_candidate_process_review_bundle(bundle)


def test_writer_does_not_walk_unrelated_directories_or_overwrite(
    source, tmp_path, monkeypatch
):
    irrelevant = source.parent / "unrelated"
    irrelevant.mkdir()
    (irrelevant / "ignored.json").write_bytes(b"not JSON")
    (source.parent / ".betelgeuze").mkdir()
    original_read = review._read

    def bounded_read(path, *args, **kwargs):
        assert (
            "unrelated" not in Path(path).parts
            and ".betelgeuze" not in Path(path).parts
        )
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(review, "_read", bounded_read)
    output = tmp_path / "published"
    manifest = review.write_fiber_frame_candidate_process_review_bundle(source, output)
    before = manifest.read_bytes()
    with pytest.raises(ValueError, match="new"):
        review.write_fiber_frame_candidate_process_review_bundle(source, output)
    assert manifest.read_bytes() == before


def test_cli_calls_only_review_exporter(source, tmp_path, capsys):
    output = tmp_path / "cli"
    assert review.main(["--suite", str(source), "--output-directory", str(output)]) == 0
    assert str(output / "manifest.json") in capsys.readouterr().out


def test_default_worker_reader_seam_preserves_monkeypatch_lookup(monkeypatch):
    calls = []

    def missing(path, limit=0):
        calls.append(path)
        raise ValueError("synthetic default reader stop")

    monkeypatch.setattr(process, "_read_bounded", missing)
    result = process._validate_worker(
        Path("unused"), Path("request.json"), {}, source_revision="a" * 40
    )
    assert calls == [Path("request.json")]
    assert result["report_contract_pass"] is False
    assert result["failure"]["report"] == "synthetic default reader stop"


def _reaggregate_synthetic(source, suite):
    """Contract-only altered failure scopes, not a physical failure observation."""
    frozen = _load(source.parent / "inputs/declaration.json")
    costs, resources = process._aggregate(frozen, suite["runs"])
    old = suite["resource_accounting"]
    for key in (
        "parent_cpu_time_ns",
        "parent_wall_ns",
        "parent_preflight_cpu_ns",
        "parent_preflight_wall_ns",
        "parent_preflight_is_subset",
        "parent_scope",
        "parent_peak_memory_bytes",
        "parent_peak_memory_reason",
    ):
        resources[key] = old[key]
    resources["current_parent_plus_workers_cpu_time_ns"] = (
        old["parent_cpu_time_ns"] + resources["worker_cpu_process_time_ns"]
        if resources["worker_cpu_process_time_ns"] is not None
        else None
    )
    for key in (
        "current_parent_wall_ns_through_aggregation",
        "accounted_wall_ns_including_historical_generation_and_fit",
        "historical_cpu_time_ns",
        "historical_cpu_reason",
    ):
        costs[key] = suite["cost_accounting"][key]
    suite["resource_accounting"] = resources
    suite["cost_accounting"] = costs
    suite["case_summaries"] = process._summarize_cases(frozen, suite["runs"])
    suite["status"] = "incomplete"
    suite["claims"]["report_contract_pass"] = False
    suite["claims"]["local_timing_evidence_eligible"] = False
    _write_suite(source, suite)


@pytest.mark.parametrize(
    "mode", ["missing-resources", "timeout-partial", "invalid-report-known-cpu"]
)
def test_synthetic_partial_slots_keep_unknown_costs_and_opaque_original_bytes(
    source, tmp_path, mode
):
    suite = _load(source)
    slot = suite["runs"][-1]  # Later oracle: does not change any online predecessor.
    directory = _worker_directory(source, slot)
    manifest = slot["manifest"]
    if mode == "missing-resources":
        (directory / "resources.json").unlink()
        manifest["artifacts"].pop("resources.json")
        manifest.update(
            status="blocked",
            worker_measurements_available=False,
            worker_resource_validation_failure="worker_resources_missing",
        )
        slot.update(resource_contract_pass=False, resources=None)
        slot["failure"]["resources"] = "synthetic resource file unavailable"
    elif mode == "timeout-partial":
        for name in ("search.json", "resources.json"):
            raw = b'{"synthetic_partial":'
            (directory / name).write_bytes(raw)
            manifest["artifacts"][name] = review._raw_identity(raw)
        manifest.update(
            status="timeout",
            worker_exit_code=-15,
            worker_measurements_available=False,
            worker_resource_validation_failure="worker_timeout",
        )
        slot.update(
            report_contract_pass=False,
            resource_contract_pass=False,
            report=None,
            resources=None,
            failure={"report": "synthetic timeout", "resources": "synthetic timeout"},
        )
    else:
        slot["report"]["schema_version"] = "synthetic-invalid-report.v1"
        _reseal_worker(source, suite, len(suite["runs"]) - 1)
        slot.update(report_contract_pass=False, report=None)
        slot["failure"]["report"] = "synthetic report contract unavailable"
    _write(directory / "manifest.json", manifest)
    _reaggregate_synthetic(source, suite)
    destination = tmp_path / "partial-review"
    review.write_fiber_frame_candidate_process_review_bundle(source, destination)
    checked = review.validate_fiber_frame_candidate_process_review_bundle(destination)
    restored = checked["suite"]
    assert len(restored["runs"]) == 12 and restored["status"] == "incomplete"
    assert len(checked["manifest"]["comparisons"]) == 8
    assert restored["claims"]["local_timing_evidence_eligible"] is False
    resources = restored["resource_accounting"]
    costs = restored["cost_accounting"]
    assert costs["historical_training_analysis_request_count"] == 4
    if mode == "missing-resources":
        assert costs["current_analysis_request_count"] == 28
        assert resources["worker_cpu_process_time_ns"] is None
        assert resources["validated_resource_worker_count"] == 11
    elif mode == "timeout-partial":
        assert costs["current_analysis_request_count"] is None
        assert costs["phases"]["measured"]["unknown_request_slots"] == 1
        assert resources["worker_cpu_process_time_ns"] is None
        paths = {
            row["source_path"]: row["file"] for row in checked["manifest"]["artifacts"]
        }
        for name in ("search.json", "resources.json"):
            original = slot["worker_directory"] + "/" + name
            assert (
                destination / paths[original]
            ).read_bytes() == b'{"synthetic_partial":'
    else:
        assert costs["current_analysis_request_count"] is None
        assert costs["phases"]["measured"]["unknown_request_slots"] == 1
        assert resources["validated_resource_worker_count"] == 12
        assert (
            resources["worker_cpu_process_time_ns"]
            == resources["worker_cpu_process_time_ns_subtotal"]
        )
        assert resources["worker_cpu_process_time_ns"] == sum(
            row["resources"]["cpu_process_time_ns"] for row in restored["runs"]
        )


def test_comparison_coverage_includes_valid_warmups_even_without_resource_credit(
    retained,
):
    """Synthetic reducer input checks warmup inclusion, not a warmup observation."""
    root, fixture = retained
    suite = _load(root / fixture["suite_file"])
    suite["runs"][0]["phase"] = "warmup"
    suite["runs"][0]["resource_contract_pass"] = False
    rows, files = review._comparisons(suite)
    assert len(rows) == 8 and len(files) == 16
    assert rows[0]["phase"] == "warmup"


@pytest.mark.parametrize("raw", [b"{}", b"[]", b'{"x":1,"x":2}', b'{"x":1e999}'])
def test_invalid_suite_shape_or_json_cannot_publish(tmp_path, raw):
    source = tmp_path / "bad.json"
    source.write_bytes(raw)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError):
        review.write_fiber_frame_candidate_process_review_bundle(source, output)
    assert not output.exists()


def test_export_limits_match_portable_consumer():
    assert review._FILE_LIMIT == 64 * 1024 * 1024
    assert review._TOTAL_LIMIT == 256 * 1024 * 1024
    assert review._FILE_COUNT_LIMIT == 32768
