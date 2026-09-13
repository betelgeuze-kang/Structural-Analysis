"""Prepare a local synthetic family for the full learning-process example.

The declared split IDs exercise isolation checks, not independent provenance.
No solver executes here; the learning-process worker charges all physical labels.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameSectionChange,
    apply_fiber_frame_section_changes,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameRuntimeBenchmarkConfig,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def prepare(output: Path) -> Path:
    """Write explicit models and request into a new private directory."""
    output.mkdir(mode=0o700, exist_ok=False)
    baseline = load_neutral_json(
        Path(__file__).with_name("public_rc_fiber_frame_cantilever.json")
    )
    cases = []
    for case_id, split, width in (
        ("train-base", "train", 0.400),
        ("train-narrow", "train", 0.390),
        ("validation-width", "validation", 0.401),
        ("holdout-width", "holdout", 0.402),
    ):
        model = (
            baseline
            if width == 0.400
            else apply_fiber_frame_section_changes(
                baseline,
                FiberFrameDesignCandidate(
                    case_id, (FiberFrameSectionChange("RC1", width_m=width),)
                ),
            )
        )
        model_file = case_id + ".json"
        with (output / model_file).open("x", encoding="utf-8") as handle:
            json.dump(model.canonical_payload(), handle, indent=2, allow_nan=False)
            handle.write("\n")
        cases.append(
            {
                "case_id": case_id,
                "project_id": "synthetic-" + case_id,
                "geometry_family_id": "synthetic-" + case_id,
                "load_history_id": "synthetic-" + case_id,
                "split": split,
                "model_file": model_file,
                "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
            }
        )
    request = output / "request.json"
    with request.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": "rc-fiber-learning-process-request.v1",
                "cases": cases,
                "benchmark_configuration": asdict(
                    FiberFrameRuntimeBenchmarkConfig(
                        repetitions=2, warmup_repetitions=0
                    )
                ),
                "learning_configuration": {"ridge": 1e-6, "ood_margin": 0.1},
            },
            handle,
            indent=2,
            allow_nan=False,
        )
        handle.write("\n")
    return request


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output_directory))
