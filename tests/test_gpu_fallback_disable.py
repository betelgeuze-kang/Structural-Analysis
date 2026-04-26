from __future__ import annotations

import numpy as np
import pytest

from implementation.phase1 import rust_nonlinear_frame_bridge as nf_bridge
from implementation.phase1 import rust_track_lf_bridge as track_bridge
from implementation.phase1 import run_ssi_boundary_gate as ssi_gate
from implementation.phase1 import run_wind_time_history_gate as wind_gate


def test_ndtha_raises_when_cpu_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PHASE1_DISABLE_CPU_FALLBACK", "1")
    monkeypatch.setattr(nf_bridge, "_load_gpu_torch", lambda: None)
    with pytest.raises(RuntimeError, match="CPU fallback disabled"):
        nf_bridge.solve_nonlinear_frame_ndtha(
            story_k_n_per_m=np.full(4, 1.0e8, dtype=np.float64),
            story_h_m=np.full(4, 3.2, dtype=np.float64),
            story_axial_n=np.full(4, 1.0e6, dtype=np.float64),
            story_yield_drift_m=np.full(4, 0.01, dtype=np.float64),
            story_mass_kg=np.full(4, 2.0e5, dtype=np.float64),
            story_damping_n_s_per_m=np.full(4, 5.0e4, dtype=np.float64),
            floor_load_base_n=np.full(4, 1.0e5, dtype=np.float64),
            ag_g=np.linspace(0.0, 0.1, num=16, dtype=np.float64),
        )


def test_track_and_probe_raise_when_cpu_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PHASE1_DISABLE_CPU_FALLBACK", "1")
    monkeypatch.setattr(track_bridge, "_load_gpu_torch", lambda: None)
    with pytest.raises(RuntimeError, match="CPU fallback disabled"):
        track_bridge.solve_track_point_load(
            track_bridge.RustTrackConfig(
                length_m=25.0,
                node_count=65,
                support_type="pinned",
                theory="euler",
                bending_stiffness_n_m2=6.5e6,
                shear_stiffness_n=2.45e8,
                winkler_k_n_per_m2=0.0,
                pasternak_g_n=0.0,
                tolerance=1e-8,
                cg_max_iter=512,
                point_force_n=100_000.0,
                point_position_m=12.5,
            )
        )
    with pytest.raises(RuntimeError, match="CPU fallback disabled"):
        track_bridge.run_inplace_probe(length=128)


def test_wind_signal_metrics_cpu_path(monkeypatch) -> None:
    monkeypatch.setattr(wind_gate, "_load_gpu_torch", lambda: None)
    dom_freq, reversals, backend = wind_gate._wind_signal_metrics(
        np.asarray([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0], dtype=np.float64),
        1.0,
    )
    assert backend == "cpu_numpy"
    assert reversals >= 1
    assert dom_freq >= 0.0


def test_ssi_preprocess_metrics_cpu_path(monkeypatch) -> None:
    monkeypatch.setattr(ssi_gate, "_load_gpu_torch", lambda: None)
    dom_freq, nonlinear_ratio, backend = ssi_gate._ssi_preprocess_metrics(
        ag=np.asarray([0.0, 0.1, -0.1, 0.12, -0.12, 0.08, -0.08, 0.0], dtype=np.float64),
        dt=0.01,
        transfer=0.8,
        py_y50_m=0.03,
        tz_z50_m=0.02,
    )
    assert backend == "cpu_numpy"
    assert dom_freq >= 0.0
    assert nonlinear_ratio.shape == (8,)
    assert np.all(np.isfinite(nonlinear_ratio))


def test_wind_signal_metrics_strict_requires_gpu(monkeypatch) -> None:
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS", "1")
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS_STRICT", "1")
    monkeypatch.setattr(wind_gate, "_load_gpu_torch", lambda: None)
    with pytest.raises(RuntimeError, match="GPU preprocess required"):
        wind_gate._wind_signal_metrics(
            np.asarray([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0], dtype=np.float64),
            1.0,
        )


def test_ssi_preprocess_metrics_strict_requires_gpu(monkeypatch) -> None:
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS", "1")
    monkeypatch.setenv("PHASE1_GPU_PREPROCESS_STRICT", "1")
    monkeypatch.setattr(ssi_gate, "_load_gpu_torch", lambda: None)
    with pytest.raises(RuntimeError, match="GPU preprocess required"):
        ssi_gate._ssi_preprocess_metrics(
            ag=np.asarray([0.0, 0.1, -0.1, 0.12, -0.12, 0.08, -0.08, 0.0], dtype=np.float64),
            dt=0.01,
            transfer=0.8,
            py_y50_m=0.03,
            tz_z50_m=0.02,
        )
