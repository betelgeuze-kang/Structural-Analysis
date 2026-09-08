from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignComparison,
    FiberFrameDesignError,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    main,
    read_design_experiment,
    read_design_experiment_with_history,
    write_fiber_frame_design_bundle,
)


def test_example_does_not_invent_prices_or_engineering_limits():
    example = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_design_experiment.json"
    )
    candidates, prices, limits = read_design_experiment(example)
    assert len(candidates) == 3
    assert prices is None and limits is None


def test_bundle_binds_exact_serialized_bytes_and_preserves_existing_output(tmp_path):
    payload = {
        "identity": {"source_revision": "a" * 40},
        "report_hash": "sha256:" + "b" * 64,
        "experiment_identity_hash": "sha256:" + "c" * 64,
        "value": 1e-9,
    }
    report = FiberFrameDesignComparison(
        "ready", payload["report_hash"], payload["experiment_identity_hash"], payload
    )
    output = tmp_path / "bundle"
    manifest_path = write_fiber_frame_design_bundle(report, output)
    manifest = json.loads(manifest_path.read_bytes())
    encoded = (output / manifest["report_file"]).read_bytes()
    assert manifest["report_byte_length"] == len(encoded)
    assert manifest["report_sha256"] == "sha256:" + hashlib.sha256(encoded).hexdigest()
    assert json.loads(encoded) == payload
    before = manifest_path.read_bytes()
    with pytest.raises(FileExistsError):
        write_fiber_frame_design_bundle(report, output)
    assert manifest_path.read_bytes() == before


@pytest.mark.parametrize(
    "document",
    ['{"candidates": [], "candidates": []}', '{"schema_version": "wrong"}', "[]"],
)
def test_invalid_experiment_json_rejected(tmp_path, document):
    path = tmp_path / "experiment.json"
    path.write_text(document)
    with pytest.raises(FiberFrameDesignError):
        read_design_experiment(path)


def test_cli_rejects_existing_output_before_any_analysis(tmp_path, monkeypatch):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    def unexpected(*args, **kwargs):
        pytest.fail("must reject path before solve")

    monkeypatch.setattr(cli, "compare_public_rc_fiber_frame_designs", unexpected)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--model",
                "unused.json",
                "--experiment",
                "unused.json",
                "--source-revision",
                "a" * 40,
                "--output-directory",
                str(tmp_path),
            ]
        )
    assert exc.value.code == 2


def _history_experiment():
    return {
        "schema_version": "rc-fiber-design-experiment.v2",
        "candidates": [
            {
                "candidate_id": "narrow",
                "changes": [{"section_id": "RC1", "width_m": 0.395}],
            }
        ],
        "prices": None,
        "terminal_limits": {
            "maximum_translation_m": 0.1,
            "maximum_absolute_fiber_strain": 0.01,
        },
        "history_limits": {
            "maximum_translation_m": 0.05,
            "maximum_absolute_fiber_strain": 0.005,
        },
    }


def test_history_reader_requires_explicit_v2_scope_without_silent_legacy_drop(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps(_history_experiment()))
    candidates, prices, terminal, history = read_design_experiment_with_history(path)
    assert candidates[0].candidate_id == "narrow" and prices is None
    assert terminal.maximum_translation_m == 0.1
    assert history.maximum_translation_m == 0.05
    with pytest.raises(FiberFrameDesignError, match="with_history"):
        read_design_experiment(path)


@pytest.mark.parametrize("mutation", ["missing", "null", "boolean", "v1_history"])
def test_invalid_history_declarations_fail_before_execution(tmp_path, mutation):
    value = _history_experiment()
    if mutation == "missing":
        value.pop("history_limits")
    elif mutation == "null":
        value["history_limits"] = None
    elif mutation == "boolean":
        value["history_limits"]["maximum_translation_m"] = True
    else:
        value["schema_version"] = "rc-fiber-design-experiment.v1"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(value))
    with pytest.raises(FiberFrameDesignError):
        read_design_experiment_with_history(path)
