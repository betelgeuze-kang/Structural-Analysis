"""Actual seven-target labels and one fresh learned worker, without speed claims.

Four public training/validation/holdout requests and two worker requests exercise
the complete source-bound path. The single low-load family is a correctness
fixture; its declared split names do not establish independent provenance.
"""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_candidate_process as process
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "terminal_and_committed_material_history.v1"


def _bytes(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def _source_identity():
    names = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "src/structural_analysis"], text=True
    ).splitlines()
    assert all(".env" not in Path(name).name for name in names)
    return canonical_hash(
        {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    )


@pytest.fixture(scope="module")
def actual_history_worker():
    directory = Path(
        tempfile.mkdtemp(prefix="structural-candidate-history-integration-")
    )
    print(f"Seven-target correctness artifacts: {directory}", flush=True)
    source = _source_identity()
    base = json.loads(
        (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_bytes()
    )
    base["loads"][0]["components"]["FY"] = -1.0
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    cases = []
    for index, (width, split) in enumerate(
        ((0.34, "train"), (0.46, "train"), (0.37, "validation"), (0.43, "holdout"))
    ):
        payload = deepcopy(base)
        payload["sections"][0]["width_m"] = width
        raw = _bytes(payload)
        (directory / f"training-model-{index}.json").write_bytes(raw)
        cases.append(
            FiberFrameWarmStartDataCase(
                f"case-{index}",
                f"project-{index}",
                f"geometry-{index}",
                f"history-{index}",
                split,
                load_neutral_json_bytes(raw),
                config,
            )
        )
    original = public_api.analyze_public_rc_fiber_frame
    captured = []

    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        index = len(captured)
        (directory / f"training-public-{index}.json").write_bytes(
            _bytes(result.to_dict())
        )
        (directory / f"training-checkpoint-{index}.json").write_bytes(
            result.checkpoint_artifact()
        )
        captured.append(result)
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(public_api, "analyze_public_rc_fiber_frame", observed)
        training = learning.train_fiber_frame_candidate_policy(
            cases,
            source_revision=source,
            target_profile=PROFILE,
        )
    payload = training.to_dict()
    (directory / "training.json").write_bytes(_bytes(payload))
    assert training.status == "ready", payload.get("failure")
    assert len(captured) == 4
    (directory / "model.json").write_bytes(_bytes(base))
    case = {
        "case_id": "history-scope",
        "model_file": str(directory / "model.json"),
        "training_file": str(directory / "training.json"),
        "candidates": [
            asdict(
                design.FiberFrameDesignCandidate(
                    "interior-width",
                    (design.FiberFrameSectionChange("RC1", width_m=0.395),),
                )
            )
        ],
        "configuration": asdict(config),
        "prices": asdict(
            design.FiberFrameMaterialPrices(
                100.0,
                1.0,
                "KRW",
                "2026-09-09",
                "synthetic test prices; not a quote",
            )
        ),
        "terminal_limits": asdict(design.FiberFrameTerminalLimits(1.0, 1.0)),
        "history_limits": asdict(design.FiberFrameHistoryLimits(1.0, 1.0)),
        "material_history_limits": asdict(
            design.FiberFrameMaterialHistoryLimits(1.0, 1.0, 1.0)
        ),
        "full_analysis_budget": 2,
        "exploration_slots": 0,
    }
    request = {
        "schema_version": process.REQUEST_MATERIAL_SCHEMA,
        "cases": [case],
        "repetitions": 2,
        "warmups": 0,
        "oracle_audit": False,
    }
    request_path = directory / "request.json"
    request_path.write_bytes(_bytes(request))
    preparation = directory / "preparation"
    preparation.mkdir()
    frozen = process._freeze_inputs(request_path, preparation, source_revision=source)
    frozen_case = frozen["cases"][0]
    arguments = process._case_arguments(frozen_case["request"], preparation)
    assert arguments["training"].policy.artifact_hash == training.policy.artifact_hash
    worker_request = {
        "schema_version": process.WORKER_MATERIAL_SCHEMA,
        "case": frozen_case["request"],
        "strategy": "learned",
        "expected_plan_hash": frozen_case["expectations"]["learned"][
            "frozen_plan_hash"
        ],
        "expected_inputs": [
            next(
                row
                for row in frozen["identities"]
                if row["path"] == frozen_case["request"][key]
            )
            for key in ("model_file", "training_file")
        ],
        "online_completion_hashes": {},
    }
    worker_request_path = directory / "worker-request.json"
    worker_request_path.write_bytes(_bytes(worker_request))
    worker = directory / "worker"
    launch = process._launch_worker(
        worker_request_path,
        source_revision=source,
        output_directory=worker,
        timeout_seconds=300.0,
    )
    assert launch["worker_exit_code"] == 0, launch
    checked = process._validate_worker(
        worker,
        worker_request_path,
        frozen_case["expectations"],
        source_revision=source,
    )
    assert checked["report_contract_pass"], checked["failure"]
    assert checked["resource_contract_pass"], checked["failure"]
    assert _source_identity() == source
    return SimpleNamespace(
        directory=directory,
        source=source,
        training=training,
        captured=captured,
        case=case,
        frozen=frozen,
        checked=checked,
    )


def test_real_history_labels_retain_original_sources_and_train_only_membership(
    actual_history_worker,
):
    observed = actual_history_worker
    report = observed.training.to_dict()
    assert report["schema_version"] == "fiber-frame-candidate-learning.v3"
    assert report["cost_accounting"]["full_analysis_request_count"] == 4
    assert report["claims"]["independent_project_generalization_verified"] is False
    assert observed.training.policy.training_sample_hashes == tuple(
        sorted(
            row["sample_hash"] for row in report["samples"] if row["split"] == "train"
        )
    )
    for sample, result in zip(report["samples"], observed.captured, strict=True):
        assert len(sample["targets"]) == 7
        assert sample["public_result_hash"] == result.result_hash
        assert (
            sample["checkpoint_chain_hash"]
            == result.contract_bindings["checkpoint_chain_hash"]
        )
        assert sample["targets"][2] >= sample["targets"][0]
        assert sample["targets"][3] >= sample["targets"][1]
        assert sample["targets"][4:] == [0.0, 0.0, 0.0]


def test_fresh_worker_confirms_all_requested_scopes_with_original_budget(
    actual_history_worker,
):
    report = actual_history_worker.checked["report"]
    assert report["candidate_target_profile"] == PROFILE
    assert report["input_binding"]["candidate_target_profile"] == PROFILE
    arm = report["arm"]
    assert arm["cost_accounting"]["total_analysis_request_count"] == 2
    assert arm["final_selection"]["candidate_id"] == "interior-width"
    for row in [arm["baseline"], *arm["candidate_outcomes"]]:
        assert row["full_reference_verification_pass"]
        assert row["full_history_verification_pass"]
        assert row["full_material_history_verification_pass"]
    prediction = report["candidate_pool"][0]
    assert prediction["predicted_requested_limits_safe"] is True
    assert prediction["prediction"]["target_profile"] == PROFILE
    assert len(prediction["prediction"]["history_prediction"]) == 5


@pytest.mark.parametrize("mutation", ["remove-profile", "downgrade-profile"])
def test_frozen_training_profile_cannot_be_reinterpreted_before_worker(
    actual_history_worker, tmp_path, monkeypatch, mutation
):
    report = actual_history_worker.training.to_dict()
    if mutation == "remove-profile":
        del report["policy"]["target_profile"]
    else:
        report["policy"]["target_profile"] = "terminal_response.v1"
    report["policy"]["artifact_hash"] = canonical_hash(
        {
            key: value
            for key, value in report["policy"].items()
            if key != "artifact_hash"
        }
    )
    report["report_hash"] = canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )
    training_path = tmp_path / "training.json"
    training_path.write_bytes(_bytes(report))
    case = {**actual_history_worker.case, "training_file": str(training_path)}

    def forbidden(*args, **kwargs):
        pytest.fail("a profile downgrade must fail before numerical work")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises((KeyError, ValueError)):
        process._case_arguments(case, tmp_path)
