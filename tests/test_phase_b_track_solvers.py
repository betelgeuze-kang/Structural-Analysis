"""Phase-B tests: Track LF solver, moving-load integrator, CG solver."""
from __future__ import annotations


import numpy as np
import pytest

from track_lf_solver import (
    TrackLFConfig,
    _validate_config,
    apply_euler_beam_operator,
    cg_solve_matrix_free,
    make_point_load_vector,
    make_uniform_load_vector,
    solve_track_static,
)


# ── Config validation ────────────────────────────────────────────────────────

class TestTrackLFConfigValidation:
    def test_valid_default_config(self):
        cfg = TrackLFConfig()
        _validate_config(cfg)  # should not raise

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="length_m"):
            _validate_config(TrackLFConfig(length_m=-1.0))

    def test_invalid_node_count(self):
        with pytest.raises(ValueError, match="node_count"):
            _validate_config(TrackLFConfig(node_count=3))

    def test_invalid_support_type(self):
        with pytest.raises(ValueError, match="support_type"):
            _validate_config(TrackLFConfig(support_type="free"))

    def test_invalid_theory(self):
        with pytest.raises(ValueError, match="theory"):
            _validate_config(TrackLFConfig(theory="bernoulli"))

    def test_invalid_bending_stiffness(self):
        with pytest.raises(ValueError, match="bending_stiffness"):
            _validate_config(TrackLFConfig(bending_stiffness_n_m2=0.0))

    def test_invalid_relaxation(self):
        with pytest.raises(ValueError, match="relaxation"):
            _validate_config(TrackLFConfig(relaxation=0.0))
        with pytest.raises(ValueError, match="relaxation"):
            _validate_config(TrackLFConfig(relaxation=1.5))


# ── Load vector generation ───────────────────────────────────────────────────

class TestLoadVectors:
    def test_point_load_symmetry(self):
        n = 101
        L = 10.0
        q = make_point_load_vector(n, L, force_n=1000.0, position_m=5.0)
        assert q[0] == 0.0
        assert q[-1] == 0.0
        assert np.max(np.abs(q)) > 0.0

    def test_point_load_at_boundary_is_zero(self):
        q = make_point_load_vector(51, 10.0, force_n=5000.0, position_m=0.0)
        assert q[0] == 0.0

    def test_uniform_load_shape(self):
        q = make_uniform_load_vector(101, 5000.0)
        assert q.shape == (101,)
        assert q[0] == 0.0
        assert q[-1] == 0.0
        assert q[50] == pytest.approx(5000.0)


# ── CG solver ────────────────────────────────────────────────────────────────

class TestCGSolver:
    def test_identity_operator(self):
        """CG with identity operator should return rhs."""
        rhs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        x, iters, res, ok = cg_solve_matrix_free(lambda v: v, rhs, tol=1e-10)
        assert ok is True
        np.testing.assert_allclose(x, rhs, atol=1e-8)

    def test_diagonal_operator(self):
        diag = np.array([2.0, 3.0, 5.0, 7.0])
        rhs = np.array([4.0, 9.0, 25.0, 49.0])
        x, iters, res, ok = cg_solve_matrix_free(lambda v: diag * v, rhs, tol=1e-10)
        assert ok is True
        np.testing.assert_allclose(x, rhs / diag, atol=1e-6)

    def test_zero_rhs_converges_immediately(self):
        rhs = np.zeros(10)
        x, iters, res, ok = cg_solve_matrix_free(lambda v: v, rhs, tol=1e-10)
        assert ok is True
        assert iters == 0


# ── Euler beam operator ──────────────────────────────────────────────────────

class TestEulerBeamOperator:
    def test_zero_displacement_gives_zero_force(self):
        w = np.zeros(21)
        out = apply_euler_beam_operator(
            w, dx=0.5, bending_stiffness_n_m2=1e6,
            winkler_k_n_per_m2=0.0, pasternak_g_n=0.0, support_type="pinned",
        )
        np.testing.assert_allclose(out, 0.0, atol=1e-12)

    def test_output_shape_matches_input(self):
        w = np.random.default_rng(42).standard_normal(51)
        out = apply_euler_beam_operator(
            w, dx=0.2, bending_stiffness_n_m2=1e6,
            winkler_k_n_per_m2=1e4, pasternak_g_n=1e3, support_type="pinned",
        )
        assert out.shape == w.shape


# ── End-to-end solve ─────────────────────────────────────────────────────────

class TestTrackStaticSolve:
    def test_euler_pinned_midpoint_load_converges(self):
        cfg = TrackLFConfig(
            theory="euler", support_type="pinned",
            length_m=10.0, node_count=101,
            bending_stiffness_n_m2=1e6,
        )
        q = make_point_load_vector(101, 10.0, force_n=1000.0, position_m=5.0)
        result = solve_track_static(cfg, q)
        assert result.converged is True
        assert len(result.displacement_m) == 101

    def test_euler_midpoint_displacement_matches_analytic(self):
        """Simply-supported beam: δ_mid = PL³/(48EI)"""
        L, EI, P = 10.0, 1e6, 1000.0
        n = 201
        cfg = TrackLFConfig(
            theory="euler", support_type="pinned",
            length_m=L, node_count=n,
            bending_stiffness_n_m2=EI, tolerance=1e-10, cg_max_iter=3000,
        )
        q = make_point_load_vector(n, L, force_n=P, position_m=L / 2)
        result = solve_track_static(cfg, q)
        assert result.converged
        w_mid = abs(result.displacement_m[n // 2])
        analytic = P * L**3 / (48.0 * EI)
        assert w_mid == pytest.approx(analytic, rel=0.05)

    def test_timoshenko_gives_larger_displacement_than_euler(self):
        """Timoshenko correction always increases midpoint displacement."""
        L, n = 10.0, 101
        cfg_e = TrackLFConfig(theory="euler", length_m=L, node_count=n)
        cfg_t = TrackLFConfig(theory="timoshenko", length_m=L, node_count=n)
        q = make_point_load_vector(n, L, force_n=50000.0, position_m=L / 2)
        res_e = solve_track_static(cfg_e, q)
        res_t = solve_track_static(cfg_t, q)
        assert res_e.converged and res_t.converged
        mid_e = abs(res_e.displacement_m[n // 2])
        mid_t = abs(res_t.displacement_m[n // 2])
        assert mid_t >= mid_e

    def test_load_size_mismatch_raises(self):
        cfg = TrackLFConfig(node_count=101)
        q = np.zeros(50)
        with pytest.raises(ValueError, match="load vector size"):
            solve_track_static(cfg, q)

    def test_boundary_displacements_are_zero(self):
        cfg = TrackLFConfig(theory="euler", length_m=10.0, node_count=51)
        q = make_uniform_load_vector(51, 1000.0)
        result = solve_track_static(cfg, q)
        assert result.converged
        assert result.displacement_m[0] == pytest.approx(0.0, abs=1e-12)
        assert result.displacement_m[-1] == pytest.approx(0.0, abs=1e-12)


# ── Moving-load attention ────────────────────────────────────────────────────

class TestMovingLoadAttention:
    def test_peak_at_position(self):
        from moving_load_attention import compute_moving_load_attention
        w = compute_moving_load_attention(
            node_count=101, position_idx=50, speed_m_s=20.0, gain=1.0,
        )
        peak_idx = w.index(max(w))
        assert peak_idx == 50

    def test_gain_bounds(self):
        from moving_load_attention import compute_moving_load_attention
        w = compute_moving_load_attention(
            node_count=51, position_idx=25, speed_m_s=30.0, gain=0.5,
        )
        assert all(0.0 <= v <= 0.5 + 1e-9 for v in w)

    def test_monotonic_decay_from_peak(self):
        from moving_load_attention import compute_moving_load_attention
        w = compute_moving_load_attention(
            node_count=101, position_idx=50, speed_m_s=20.0, gain=1.0,
        )
        # Left of peak: should be non-decreasing
        for i in range(1, 51):
            assert w[i] >= w[i - 1] - 1e-9
        # Right of peak: should be non-increasing
        for i in range(51, 101):
            assert w[i] <= w[i - 1] + 1e-9

    def test_higher_speed_widens_support(self):
        from moving_load_attention import compute_moving_load_attention, _effective_support
        w_lo = compute_moving_load_attention(node_count=101, position_idx=50, speed_m_s=10.0)
        w_hi = compute_moving_load_attention(node_count=101, position_idx=50, speed_m_s=40.0)
        assert _effective_support(w_hi) >= _effective_support(w_lo)

    def test_invalid_node_count_raises(self):
        from moving_load_attention import compute_moving_load_attention
        with pytest.raises(ValueError, match="node_count"):
            compute_moving_load_attention(node_count=2, position_idx=0, speed_m_s=10.0)
