use structural_ffi_sys::legacy_runtime_v3::{
    NlFrameNdthaConfig, NlFrameSolveConfig, TrackSolveConfig, NDTHA_STATUS_INVALID_ADAPTIVE_DECAY,
    NDTHA_STATUS_INVALID_COLLAPSE_DRIFT, NDTHA_STATUS_INVALID_COUNTS,
    NDTHA_STATUS_INVALID_DAMPING_CAP, NDTHA_STATUS_INVALID_HARDENING,
    NDTHA_STATUS_INVALID_ITERATION_CONTROL, NDTHA_STATUS_INVALID_LINE_SEARCH_DECAY,
    NDTHA_STATUS_INVALID_LINE_SEARCH_MIN, NDTHA_STATUS_INVALID_NEWMARK,
    NDTHA_STATUS_INVALID_PDELTA, NDTHA_STATUS_INVALID_TIME_STEP, NDTHA_STATUS_INVALID_TOLERANCE,
    NONLINEAR_STATIC_STATUS_INVALID_HARDENING, NONLINEAR_STATIC_STATUS_INVALID_ITERATION_CONTROL,
    NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_DECAY,
    NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_MIN, NONLINEAR_STATIC_STATUS_INVALID_PDELTA,
    NONLINEAR_STATIC_STATUS_INVALID_STORY_COUNT, TRACK_STATUS_INVALID_ENUM,
    TRACK_STATUS_INVALID_FOUNDATION, TRACK_STATUS_INVALID_ITERATION_CONTROL,
    TRACK_STATUS_INVALID_LENGTH, TRACK_STATUS_INVALID_NODE_COUNT, TRACK_STATUS_INVALID_STIFFNESS,
};

pub(crate) const EPS: f64 = 1e-12;

pub(crate) fn ghost_at(w: &[f64], idx: isize, support_type: u32) -> f64 {
    let n = w.len() as isize;
    if idx == -1 {
        if support_type == 0 {
            return -w[1];
        }
        return w[1];
    }
    if idx == n {
        if support_type == 0 {
            return -w[(n - 2) as usize];
        }
        return w[(n - 2) as usize];
    }
    if idx < 0 || idx >= n {
        return 0.0;
    }
    w[idx as usize]
}

pub(crate) fn apply_euler_operator(
    w: &[f64],
    out: &mut [f64],
    dx: f64,
    ei: f64,
    kw: f64,
    kg: f64,
    support_type: u32,
) {
    let n = w.len();
    let inv_dx2 = 1.0 / (dx * dx).max(EPS);
    let inv_dx4 = inv_dx2 * inv_dx2;

    for i in 1..(n - 1) {
        let ii = i as isize;
        let d2 = (ghost_at(w, ii + 1, support_type) - 2.0 * ghost_at(w, ii, support_type)
            + ghost_at(w, ii - 1, support_type))
            * inv_dx2;
        let d4 = (ghost_at(w, ii - 2, support_type) - 4.0 * ghost_at(w, ii - 1, support_type)
            + 6.0 * ghost_at(w, ii, support_type)
            - 4.0 * ghost_at(w, ii + 1, support_type)
            + ghost_at(w, ii + 2, support_type))
            * inv_dx4;
        out[i] = ei * d4 - kg * d2 + kw * ghost_at(w, ii, support_type);
    }
    out[0] = w[0];
    out[n - 1] = w[n - 1];
}

pub(crate) fn dot(a: &[f64], b: &[f64]) -> f64 {
    let mut s = 0.0;
    for i in 0..a.len() {
        s += a[i] * b[i];
    }
    s
}

pub(crate) fn cg_solve_euler(
    rhs: &[f64],
    x: &mut [f64],
    dx: f64,
    ei: f64,
    kw: f64,
    kg: f64,
    support_type: u32,
    tol: f64,
    max_iter: usize,
) -> (bool, usize, f64) {
    let n = rhs.len();
    let mut r = vec![0.0_f64; n];
    let mut p = vec![0.0_f64; n];
    let mut ap = vec![0.0_f64; n];
    let mut ax = vec![0.0_f64; n];

    apply_euler_operator(x, &mut ax, dx, ei, kw, kg, support_type);
    for i in 0..n {
        r[i] = rhs[i] - ax[i];
        p[i] = r[i];
    }

    let tol2 = tol * tol;
    let mut rr_old = dot(&r, &r);
    if rr_old <= tol2 {
        return (true, 0, rr_old.sqrt());
    }

    let mut rr = rr_old;
    let mut it = 0usize;
    for k in 1..=max_iter {
        apply_euler_operator(&p, &mut ap, dx, ei, kw, kg, support_type);
        let denom = dot(&p, &ap);
        if denom.abs() <= EPS {
            it = k;
            break;
        }
        let alpha = rr_old / denom;
        for i in 0..n {
            x[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        rr = dot(&r, &r);
        it = k;
        if rr <= tol2 {
            return (true, k, rr.sqrt());
        }
        let beta = rr / rr_old;
        for i in 0..n {
            p[i] = r[i] + beta * p[i];
        }
        rr_old = rr;
    }
    (false, it, rr.max(0.0).sqrt())
}

pub(crate) fn fill_point_load(
    rhs: &mut [f64],
    length_m: f64,
    point_force_n: f64,
    point_position_m: f64,
) {
    let n = rhs.len();
    let dx = length_m / ((n - 1) as f64).max(1.0);
    for v in rhs.iter_mut() {
        *v = 0.0;
    }

    let x = point_position_m.max(0.0).min(length_m);
    let xi = x / dx.max(EPS);
    let i0 = xi.floor() as usize;
    let i1 = (i0 + 1).min(n - 1);
    let w1 = xi - (i0 as f64);
    let w0 = 1.0 - w1;
    rhs[i0] += (point_force_n * w0) / dx.max(EPS);
    rhs[i1] += (point_force_n * w1) / dx.max(EPS);
    rhs[0] = 0.0;
    rhs[n - 1] = 0.0;
}

pub(crate) fn displacement_gradient(w: &[f64], dx: f64, out_theta: &mut [f64]) {
    let n = w.len();
    if n < 2 {
        return;
    }
    for i in 1..(n - 1) {
        out_theta[i] = (w[i + 1] - w[i - 1]) / (2.0 * dx.max(EPS));
    }
    out_theta[0] = out_theta[1];
    out_theta[n - 1] = out_theta[n - 2];
}

pub(crate) fn validate_cfg(cfg: &TrackSolveConfig) -> i32 {
    if cfg.length_m <= 0.0 {
        return TRACK_STATUS_INVALID_LENGTH;
    }
    if cfg.node_count < 7 {
        return TRACK_STATUS_INVALID_NODE_COUNT;
    }
    if cfg.bending_stiffness_n_m2 <= 0.0 || cfg.shear_stiffness_n <= 0.0 {
        return TRACK_STATUS_INVALID_STIFFNESS;
    }
    if cfg.winkler_k_n_per_m2 < 0.0 || cfg.pasternak_g_n < 0.0 {
        return TRACK_STATUS_INVALID_FOUNDATION;
    }
    if cfg.tolerance <= 0.0 || cfg.cg_max_iter < 1 {
        return TRACK_STATUS_INVALID_ITERATION_CONTROL;
    }
    if cfg.support_type > 1 || cfg.theory > 1 {
        return TRACK_STATUS_INVALID_ENUM;
    }
    0
}

pub(crate) fn validate_nl_cfg(cfg: &NlFrameSolveConfig) -> i32 {
    if cfg.story_count < 1 {
        return NONLINEAR_STATIC_STATUS_INVALID_STORY_COUNT;
    }
    if cfg.tolerance <= 0.0 || cfg.max_iter < 1 {
        return NONLINEAR_STATIC_STATUS_INVALID_ITERATION_CONTROL;
    }
    if !(0.0..=1.0).contains(&cfg.hardening_ratio) {
        return NONLINEAR_STATIC_STATUS_INVALID_HARDENING;
    }
    if !(0.0 < cfg.line_search_decay && cfg.line_search_decay < 1.0) {
        return NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_DECAY;
    }
    if !(0.0 < cfg.line_search_min && cfg.line_search_min <= 1.0) {
        return NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_MIN;
    }
    if cfg.pdelta_factor < 0.0 {
        return NONLINEAR_STATIC_STATUS_INVALID_PDELTA;
    }
    0
}

pub(crate) fn validate_ndtha_cfg(cfg: &NlFrameNdthaConfig) -> i32 {
    if cfg.story_count < 1 || cfg.step_count < 1 {
        return NDTHA_STATUS_INVALID_COUNTS;
    }
    if cfg.dt_s <= 0.0 {
        return NDTHA_STATUS_INVALID_TIME_STEP;
    }
    if cfg.newmark_beta <= 0.0 || cfg.newmark_gamma <= 0.0 {
        return NDTHA_STATUS_INVALID_NEWMARK;
    }
    if cfg.tolerance <= 0.0 {
        return NDTHA_STATUS_INVALID_TOLERANCE;
    }
    if cfg.max_step_iterations < 1 || cfg.newton_max_iter < 1 {
        return NDTHA_STATUS_INVALID_ITERATION_CONTROL;
    }
    if !(0.0 < cfg.adaptive_load_decay && cfg.adaptive_load_decay <= 1.0) {
        return NDTHA_STATUS_INVALID_ADAPTIVE_DECAY;
    }
    if cfg.damping_force_cap_ratio <= 0.0 {
        return NDTHA_STATUS_INVALID_DAMPING_CAP;
    }
    if !(0.0..=1.0).contains(&cfg.hardening_ratio) {
        return NDTHA_STATUS_INVALID_HARDENING;
    }
    if cfg.pdelta_factor < 0.0 {
        return NDTHA_STATUS_INVALID_PDELTA;
    }
    if !(0.0 < cfg.line_search_decay && cfg.line_search_decay < 1.0) {
        return NDTHA_STATUS_INVALID_LINE_SEARCH_DECAY;
    }
    if !(0.0 < cfg.line_search_min && cfg.line_search_min <= 1.0) {
        return NDTHA_STATUS_INVALID_LINE_SEARCH_MIN;
    }
    if cfg.collapse_drift_threshold_pct <= 0.0 {
        return NDTHA_STATUS_INVALID_COLLAPSE_DRIFT;
    }
    0
}

pub(crate) fn vec_norm_l2(v: &[f64]) -> f64 {
    let mut s = 0.0_f64;
    for x in v {
        s += x * x;
    }
    s.sqrt()
}

pub(crate) fn vec_norm_inf(v: &[f64]) -> f64 {
    let mut m = 0.0_f64;
    for x in v {
        m = m.max(x.abs());
    }
    m
}

pub(crate) fn solve_tridiagonal(
    lower: &[f64],
    diag: &[f64],
    upper: &[f64],
    rhs: &[f64],
    x_out: &mut [f64],
) -> bool {
    let n = diag.len();
    if n == 0 || lower.len() + 1 != n || upper.len() + 1 != n || rhs.len() != n || x_out.len() != n
    {
        return false;
    }
    let mut c_prime = vec![0.0_f64; n];
    let mut d_prime = vec![0.0_f64; n];

    let d0 = diag[0];
    if d0.abs() <= EPS {
        return false;
    }
    c_prime[0] = if n > 1 { upper[0] / d0 } else { 0.0 };
    d_prime[0] = rhs[0] / d0;

    for i in 1..n {
        let denom = diag[i] - lower[i - 1] * c_prime[i - 1];
        if denom.abs() <= EPS {
            return false;
        }
        c_prime[i] = if i < n - 1 { upper[i] / denom } else { 0.0 };
        d_prime[i] = (rhs[i] - lower[i - 1] * d_prime[i - 1]) / denom;
    }

    x_out[n - 1] = d_prime[n - 1];
    for i in (0..(n - 1)).rev() {
        x_out[i] = d_prime[i] - c_prime[i] * x_out[i + 1];
    }
    true
}

pub(crate) fn assemble_internal_and_tangent(
    u: &[f64],
    k_story: &[f64],
    h_story: &[f64],
    p_axial: &[f64],
    y_drift: &[f64],
    hardening_ratio: f64,
    pdelta_factor: f64,
    f_int: &mut [f64],
    lower: &mut [f64],
    diag: &mut [f64],
    upper: &mut [f64],
) -> (f64, u32, f64) {
    let n = u.len();
    let mut spring_force = vec![0.0_f64; n];
    let mut spring_tangent = vec![0.0_f64; n];
    let mut plastic_count = 0_u32;

    for i in 0..n {
        let ui = u[i];
        let uim1 = if i == 0 { 0.0 } else { u[i - 1] };
        let drift = ui - uim1;
        let k0 = k_story[i].max(EPS);
        let dy = y_drift[i].abs().max(1e-9);
        let kh = hardening_ratio * k0;
        let q: f64;
        let kt: f64;

        if drift.abs() <= dy {
            q = k0 * drift;
            kt = k0;
        } else {
            let sgn = if drift >= 0.0 { 1.0 } else { -1.0 };
            q = sgn * (k0 * dy + kh * (drift.abs() - dy));
            kt = kh;
            plastic_count += 1;
        }

        let h = h_story[i].max(EPS);
        let kgeo = pdelta_factor * p_axial[i].abs() / h;
        spring_force[i] = q;
        spring_tangent[i] = kt - kgeo;
    }

    for i in 0..n {
        f_int[i] = if i < n - 1 {
            spring_force[i] - spring_force[i + 1]
        } else {
            spring_force[i]
        };
    }

    for i in 0..lower.len() {
        lower[i] = 0.0;
    }
    for i in 0..diag.len() {
        diag[i] = 0.0;
    }
    for i in 0..upper.len() {
        upper[i] = 0.0;
    }

    for i in 0..n {
        let kii = spring_tangent[i];
        let kip1 = if i < n - 1 {
            spring_tangent[i + 1]
        } else {
            0.0
        };
        diag[i] = kii + kip1;
        if i > 0 {
            lower[i - 1] = -kii;
        }
        if i < n - 1 {
            upper[i] = -kip1;
        }
    }

    // Small diagonal regularization for near-singular states.
    let mut min_diag = f64::INFINITY;
    for v in diag.iter() {
        min_diag = min_diag.min(v.abs());
    }
    if !min_diag.is_finite() || min_diag <= 1e-9 {
        for i in 0..n {
            diag[i] += 1e-6 * k_story[i].max(1.0);
        }
    }

    let base_shear_kn = spring_force[0].abs() / 1000.0;
    (base_shear_kn, plastic_count, spring_tangent[0])
}

pub(crate) fn compute_story_response(
    u: &[f64],
    story_h: &[f64],
    story_k: &[f64],
    out_drift_pct: &mut [f64],
    out_shear_kn: &mut [f64],
) {
    let n = u.len();
    if n == 0 {
        return;
    }
    for i in 0..n {
        let du = if i == 0 { u[0] } else { u[i] - u[i - 1] };
        out_drift_pct[i] = 100.0 * du / story_h[i].max(EPS);
        out_shear_kn[i] = story_k[i] * du / 1000.0;
    }
}

pub(crate) fn max_abs(v: &[f64]) -> f64 {
    let mut m = 0.0_f64;
    for x in v {
        m = m.max(x.abs());
    }
    m
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn solve_ndtha_step(
    cfg: &NlFrameNdthaConfig,
    story_k: &[f64],
    story_h: &[f64],
    story_p: &[f64],
    story_yield_drift: &[f64],
    story_mass: &[f64],
    story_damp: &[f64],
    p_ext: &[f64],
    u_prev: &[f64],
    v_prev: &[f64],
    a_prev: &[f64],
    u_next: &mut [f64],
    v_next: &mut [f64],
    a_next: &mut [f64],
    f_int: &mut [f64],
    lower: &mut [f64],
    diag: &mut [f64],
    upper: &mut [f64],
    residual: &mut [f64],
    du: &mut [f64],
    u_trial: &mut [f64],
    u_cand: &mut [f64],
    p_trial: &mut [f64],
    diag_eff: &mut [f64],
) -> (bool, u32, u32, f64, f64, u32) {
    let n = story_k.len();
    let dt = cfg.dt_s.max(EPS);
    let beta = cfg.newmark_beta.max(EPS);
    let gamma = cfg.newmark_gamma.max(EPS);
    let a0 = 1.0 / (beta * dt * dt);
    let a1 = gamma / (beta * dt);

    let mut u_pred = vec![0.0_f64; n];
    let mut v_pred = vec![0.0_f64; n];
    for i in 0..n {
        u_pred[i] = u_prev[i] + dt * v_prev[i] + dt * dt * (0.5 - beta) * a_prev[i];
        v_pred[i] = v_prev[i] + dt * (1.0 - gamma) * a_prev[i];
        u_trial[i] = u_prev[i];
    }

    let mut load_scale = 1.0_f64;
    let mut step_used = 0_u32;
    let mut last_residual_inf = f64::INFINITY;
    let mut last_base_shear = 0.0_f64;
    let mut last_plastic = 0_u32;
    let mut total_backtracks = 0_u32;

    for attempt in 1..=cfg.max_step_iterations {
        step_used = attempt;
        for i in 0..n {
            p_trial[i] = p_ext[i] * load_scale;
        }

        let mut success = false;
        for _ in 1..=cfg.newton_max_iter {
            let (base_shear_kn, plastic_count, _k0) = assemble_internal_and_tangent(
                u_trial,
                story_k,
                story_h,
                story_p,
                story_yield_drift,
                cfg.hardening_ratio,
                cfg.pdelta_factor,
                f_int,
                lower,
                diag,
                upper,
            );
            last_base_shear = base_shear_kn;
            last_plastic = plastic_count;

            for i in 0..n {
                let a_t = a0 * (u_trial[i] - u_pred[i]);
                let v_t = v_pred[i] + gamma * dt * a_t;
                residual[i] = p_trial[i] - f_int[i] - story_damp[i] * v_t - story_mass[i] * a_t;
            }
            let res_inf = vec_norm_inf(residual);
            last_residual_inf = res_inf;
            if res_inf <= cfg.tolerance {
                for i in 0..n {
                    u_next[i] = u_trial[i];
                    a_next[i] = a0 * (u_next[i] - u_pred[i]);
                    v_next[i] = v_pred[i] + gamma * dt * a_next[i];
                }
                success = true;
                break;
            }

            for i in 0..n {
                diag_eff[i] = diag[i] + story_mass[i] * a0 + story_damp[i] * a1;
            }
            if !solve_tridiagonal(lower, diag_eff, upper, residual, du) {
                break;
            }

            let base_norm = res_inf.max(EPS);
            let mut lambda = 1.0_f64;
            let mut accepted = false;

            while lambda >= cfg.line_search_min {
                for i in 0..n {
                    u_cand[i] = u_trial[i] + lambda * du[i];
                }
                let (_bs2, _pc2, _k02) = assemble_internal_and_tangent(
                    u_cand,
                    story_k,
                    story_h,
                    story_p,
                    story_yield_drift,
                    cfg.hardening_ratio,
                    cfg.pdelta_factor,
                    f_int,
                    lower,
                    diag,
                    upper,
                );
                for i in 0..n {
                    let a_t = a0 * (u_cand[i] - u_pred[i]);
                    let v_t = v_pred[i] + gamma * dt * a_t;
                    residual[i] = p_trial[i] - f_int[i] - story_damp[i] * v_t - story_mass[i] * a_t;
                }
                let cand_norm = vec_norm_inf(residual);
                if cand_norm < base_norm {
                    for i in 0..n {
                        u_trial[i] = u_cand[i];
                    }
                    accepted = true;
                    break;
                }
                lambda *= cfg.line_search_decay;
                total_backtracks += 1;
            }

            if !accepted {
                break;
            }
        }

        if success {
            return (
                true,
                step_used,
                last_plastic,
                last_base_shear,
                last_residual_inf,
                total_backtracks,
            );
        }

        load_scale *= cfg.adaptive_load_decay;
    }

    // Failed to converge: keep previous state.
    for i in 0..n {
        u_next[i] = u_prev[i];
        v_next[i] = v_prev[i];
        a_next[i] = a_prev[i];
    }
    (
        false,
        step_used.max(1),
        last_plastic,
        last_base_shear,
        last_residual_inf,
        total_backtracks,
    )
}
