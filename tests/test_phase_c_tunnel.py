"""Phase-C tests: Soil-tunnel SSI impedance and tunnel graph converter."""
from __future__ import annotations

import numpy as np

from soil_tunnel_ssi import SOIL_PRESETS, _impedance_curve, _transfer_amp


class TestSoilPresets:
    def test_all_presets_have_required_keys(self):
        for name, p in SOIL_PRESETS.items():
            for key in ("k0", "c0", "stiff_exp", "damp_slope"):
                assert key in p, f"Missing {key} in preset {name}"

    def test_stiffness_is_positive(self):
        for name, p in SOIL_PRESETS.items():
            assert p["k0"] > 0, f"k0 <= 0 in {name}"
            assert p["c0"] > 0, f"c0 <= 0 in {name}"


class TestImpedanceCurve:
    def test_stiffness_monotonically_increases(self):
        freq = np.linspace(1.0, 50.0, 200)
        kf, cf = _impedance_curve(
            freq_hz=freq, k0=5e7, c0=1e5,
            stiff_exp=0.35, damp_slope=0.4, ref_hz=5.0,
        )
        assert np.all(np.diff(kf) >= -1e-9), "Stiffness should be non-decreasing"

    def test_damping_is_positive(self):
        freq = np.linspace(0.5, 100.0, 300)
        kf, cf = _impedance_curve(
            freq_hz=freq, k0=5e7, c0=1e5,
            stiff_exp=0.3, damp_slope=0.5, ref_hz=5.0,
        )
        assert np.all(cf > 0), "Damping must be positive"

    def test_finite_output(self):
        freq = np.linspace(0.1, 80.0, 100)
        kf, cf = _impedance_curve(
            freq_hz=freq, k0=1e8, c0=2e5,
            stiff_exp=0.25, damp_slope=0.3, ref_hz=5.0,
        )
        assert np.all(np.isfinite(kf))
        assert np.all(np.isfinite(cf))


class TestTransferAmplitude:
    def test_high_frequency_attenuation(self):
        freq = np.linspace(1.0, 50.0, 200)
        kf, cf = _impedance_curve(
            freq_hz=freq, k0=5e7, c0=1e5,
            stiff_exp=0.35, damp_slope=0.4, ref_hz=5.0,
        )
        amp = _transfer_amp(freq, m=9500.0, kf=kf, cf=cf)
        assert np.all(np.isfinite(amp))
        # Median of high-frequency should be less than low-frequency
        assert float(np.median(amp[-40:])) < float(np.median(amp[:40]))
