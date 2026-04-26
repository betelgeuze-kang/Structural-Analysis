"""Phase-E tests: Substructuring, vibration attenuation, compliance checker."""
from __future__ import annotations

import math
import json
import tempfile
from pathlib import Path

import pytest

from substructuring_interface import run_substructuring, Subsystem, _dynamic_impedance
from vibration_attenuation_model import run_attenuation


# ── Substructuring interface ─────────────────────────────────────────────────

class TestSubstructuringInterface:
    def test_basic_coupling_passes(self):
        result = run_substructuring(
            f_min_hz=4.0, f_max_hz=60.0, f_count=20, input_force_n=10000.0,
        )
        assert result["contract_pass"] is True
        assert result["reason_code"] == "PASS"

    def test_interface_dof_match(self):
        result = run_substructuring(
            f_min_hz=5.0, f_max_hz=50.0, f_count=15, input_force_n=5000.0,
        )
        assert result["checks"]["interface_dof_match"] is True

    def test_finite_transfer_values(self):
        result = run_substructuring(
            f_min_hz=4.0, f_max_hz=80.0, f_count=30, input_force_n=12000.0,
        )
        assert result["checks"]["finite_transfer"] is True

    def test_invalid_frequency_range_raises(self):
        with pytest.raises(ValueError, match="frequency"):
            run_substructuring(f_min_hz=0.0, f_max_hz=10.0, f_count=10, input_force_n=1000.0)
        with pytest.raises(ValueError, match="frequency"):
            run_substructuring(f_min_hz=50.0, f_max_hz=10.0, f_count=10, input_force_n=1000.0)

    def test_invalid_force_raises(self):
        with pytest.raises(ValueError, match="force"):
            run_substructuring(f_min_hz=4.0, f_max_hz=80.0, f_count=20, input_force_n=-100.0)

    def test_max_condition_number_reported(self):
        result = run_substructuring(
            f_min_hz=4.0, f_max_hz=60.0, f_count=15, input_force_n=10000.0,
        )
        assert "max_condition_number" in result["metrics"]
        assert result["metrics"]["max_condition_number"] > 0

    def test_curve_head_has_expected_keys(self):
        result = run_substructuring(
            f_min_hz=4.0, f_max_hz=60.0, f_count=10, input_force_n=10000.0,
        )
        assert len(result["curve_head"]) > 0
        row = result["curve_head"][0]
        for key in ("f_hz", "track_disp_m", "tunnel_disp_m", "building_disp_m"):
            assert key in row


class TestDynamicImpedance:
    def test_static_case_equals_stiffness(self):
        sys = Subsystem(
            name="test", dof=2,
            mass_diag=(100.0, 100.0),
            damp_diag=(50.0, 50.0),
            stiff_matrix=((1e6, 0.0), (0.0, 1e6)),
        )
        z = _dynamic_impedance(sys, omega=0.0)
        # At omega=0, Z = K
        assert z[0, 0] == pytest.approx(1e6, rel=1e-10)
        assert z[1, 1] == pytest.approx(1e6, rel=1e-10)


# ── Vibration attenuation ────────────────────────────────────────────────────

class TestVibrationAttenuation:
    def test_basic_run_passes(self):
        result = run_attenuation(
            substructuring_report=None,
            distance_min_m=5.0, distance_max_m=60.0, distance_step_m=5.0,
        )
        assert result["contract_pass"] is True

    def test_monotonic_distance_decay(self):
        result = run_attenuation(
            substructuring_report=None,
            distance_min_m=5.0, distance_max_m=100.0, distance_step_m=5.0,
        )
        assert result["checks"]["monotonic_distance_decay"] is True

    def test_high_frequency_decays_faster(self):
        result = run_attenuation(
            substructuring_report=None,
            distance_min_m=5.0, distance_max_m=100.0, distance_step_m=10.0,
        )
        assert result["checks"]["high_frequency_decay_stronger"] is True

    def test_invalid_distance_raises(self):
        with pytest.raises(ValueError, match="distance"):
            run_attenuation(
                substructuring_report=None,
                distance_min_m=-1.0, distance_max_m=50.0, distance_step_m=5.0,
            )


# ── Vibration compliance checker ─────────────────────────────────────────────

class TestVibrationCompliance:
    def test_basic_compliance_run(self):
        """Run compliance checker with a pre-generated attenuation report."""
        # First generate an attenuation report
        attn = run_attenuation(
            substructuring_report=None,
            distance_min_m=5.0, distance_max_m=60.0, distance_step_m=5.0,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(attn, f)
            tmp_path = f.name

        try:
            from vibration_compliance_checker import run_compliance
            result = run_compliance(
                attenuation_report=tmp_path,
                standard="KS_F_2866_RESIDENTIAL_DAY",
                min_pass_ratio=0.5,
            )
            assert "contract_pass" in result
            assert "checks" in result
            assert result["checks"]["standard_supported"] is True
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_unsupported_standard_raises(self):
        from vibration_compliance_checker import run_compliance
        with pytest.raises(ValueError, match="unsupported standard"):
            run_compliance(
                attenuation_report="dummy.json",
                standard="FAKE_STANDARD_999",
                min_pass_ratio=0.5,
            )
