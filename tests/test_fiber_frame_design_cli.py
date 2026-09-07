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
