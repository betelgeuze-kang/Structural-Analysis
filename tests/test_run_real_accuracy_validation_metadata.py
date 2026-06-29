from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "implementation/phase1/run_real_accuracy_validation.py"
)
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("run_real_accuracy_validation", SCRIPT_PATH)
assert SPEC is not None
real_accuracy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(real_accuracy)


def test_real_accuracy_source_tracking_metadata_contract(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.json"

    original_git_head = real_accuracy._git_head
    try:
        real_accuracy._git_head = lambda: "abcdef1234567890"
        metadata = real_accuracy._source_tracking_metadata([source, missing])
    finally:
        real_accuracy._git_head = original_git_head

    assert metadata["source_commit_sha"] == "abcdef1234567890"
    assert metadata["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert metadata["reused_evidence"] is False
    assert metadata["reuse_policy"] == "fresh_real_accuracy_validation_run"
    assert metadata["input_checksums"][source.as_posix()].startswith("sha256:")
    assert metadata["input_checksums"][missing.as_posix()] == "missing"


def test_real_accuracy_source_tracking_excludes_generated_outputs() -> None:
    args = argparse.Namespace(
        zip="implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip",
        cases_out="implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json",
        benchmark_out="implementation/phase1/hf_benchmark_report.rwth_zenodo.json",
        comparison_out="implementation/phase1/topk_comparison_experiment_report.rwth_zenodo.json",
        suite_out="implementation/phase1/topk_precision_suite_report.rwth_zenodo.json",
    )

    paths = {path.as_posix() for path in real_accuracy._source_tracking_paths(args)}

    root = real_accuracy.REPO_ROOT
    assert (root / "implementation/phase1/run_real_accuracy_validation.py").as_posix() in paths
    assert (
        root / "implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip"
    ).as_posix() in paths
    assert (root / "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json").as_posix() not in paths
    assert (root / "implementation/phase1/hf_benchmark_report.rwth_zenodo.json").as_posix() not in paths
    assert (
        root / "implementation/phase1/topk_comparison_experiment_report.rwth_zenodo.json"
    ).as_posix() not in paths
    assert (root / "implementation/phase1/topk_precision_suite_report.rwth_zenodo.json").as_posix() not in paths
