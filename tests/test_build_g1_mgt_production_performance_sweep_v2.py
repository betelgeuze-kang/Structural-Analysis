from __future__ import annotations

from copy import deepcopy
import importlib.util
import math
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_production_performance_sweep_v2.py"
SPEC = importlib.util.spec_from_file_location("g1_performance_sweep_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _sample(architecture: str, repetition: int, **overrides):
    values = {
        "architecture": architecture,
        "source_commit_sha": "a" * 40,
        "wheel_sha256": "sha256:" + "b" * 64,
        "workload_hash": "sha256:" + "c" * 64,
        "checkpoint_sha256": "sha256:" + "d" * 64,
        "terminal_parity_digest": "sha256:" + "e" * 64,
        "repetition_index": repetition,
        "production_mgt_workload": True,
        "synthetic_fixture": False,
        "krylov_iteration_count": 6,
        "matvec_count": 7,
        "preconditioner_apply_count": 6,
        "h2d_bytes": 240_000_000,
        "d2h_bytes": 4_000_000,
        "mid_step_d2h_bytes": 0,
        "peak_vram_bytes": 261_000_000,
        "checkpoint_overhead_seconds": 0.01 + repetition * 0.001,
        "end_to_end_wall_seconds": 5.0 + repetition * 0.1,
        "cpu_baseline_wall_seconds": 5.5,
        "speedup_vs_cpu": 1.1 - repetition * 0.01,
    }
    values.update(overrides)
    return module.create_sample(**values)


def test_missing_samples_stays_partial_and_fail_closed() -> None:
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    module.validate(payload, root=ROOT)
    assert payload["status"] == "partial"
    assert payload["claims"]["cross_device_production_performance_sweep"] is False
    assert (
        "three_repetitions_per_architecture_not_available"
        in payload["blockers_remaining"]
    )


def test_same_identity_repeated_cross_device_samples_report_all_kpis() -> None:
    samples = [
        _sample(architecture, repetition)
        for architecture in module.ARCHITECTURES
        for repetition in range(3)
    ]
    payload = module.build(
        samples=samples, root=ROOT, generated_at="2026-08-09T00:00:00Z"
    )
    module.validate(payload, root=ROOT)
    assert payload["status"] == "ready"
    assert payload["claims"]["cross_device_production_performance_sweep"] is True
    for summary in payload["architecture_summaries"].values():
        assert summary["sample_count"] == 3
        assert set(summary["kpis"]) == set(module.KPI_FIELDS)
        assert (
            summary["kpis"]["end_to_end_wall_seconds"]["p95"]
            >= summary["kpis"]["end_to_end_wall_seconds"]["p50"]
        )


def test_source_or_workload_drift_and_duplicate_repetition_fail() -> None:
    samples = [_sample("gfx1030", repetition) for repetition in range(3)]
    samples += [_sample("gfx1100", repetition) for repetition in range(3)]
    drifted = deepcopy(samples)
    drifted[-1] = _sample("gfx1100", 2, workload_hash="sha256:" + "f" * 64)
    payload = module.build(
        samples=drifted, root=ROOT, generated_at="2026-08-09T00:00:00Z"
    )
    assert payload["claims"]["same_source_wheel_workload_checkpoint"] is False
    with pytest.raises(ValueError, match="duplicate_repetition"):
        module.build(samples=[samples[0], samples[0]], root=ROOT)


def test_synthetic_and_nonfinite_samples_cannot_claim_production() -> None:
    with pytest.raises(ValueError, match="synthetic_fixture_cannot_claim_production"):
        _sample("gfx1030", 0, synthetic_fixture=True)
    with pytest.raises(ValueError, match="end_to_end_wall_seconds_invalid"):
        _sample("gfx1030", 0, end_to_end_wall_seconds=math.nan)

    samples = [
        _sample(architecture, repetition)
        for architecture in module.ARCHITECTURES
        for repetition in range(3)
    ]
    synthetic = _sample(
        "gfx1030",
        9,
        production_mgt_workload=False,
        synthetic_fixture=True,
    )
    payload = module.build(samples=[*samples, synthetic], root=ROOT)
    module.validate(payload, root=ROOT)
    assert payload["status"] == "partial"
    assert payload["claims"]["cross_device_production_performance_sweep"] is False
