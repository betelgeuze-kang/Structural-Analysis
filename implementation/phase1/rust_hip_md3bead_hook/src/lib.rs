use std::slice;

const EPS: f64 = 1e-12;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct TrackSolveConfig {
    pub length_m: f64,
    pub node_count: u32,
    // 0: pinned, 1: fixed
    pub support_type: u32,
    // 0: euler, 1: timoshenko(reduced correction)
    pub theory: u32,
    pub bending_stiffness_n_m2: f64,
    pub shear_stiffness_n: f64,
    pub winkler_k_n_per_m2: f64,
    pub pasternak_g_n: f64,
    pub tolerance: f64,
    pub cg_max_iter: u32,
    pub point_force_n: f64,
    pub point_position_m: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct TrackSolveResult {
    pub converged: u8,
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub mid_displacement_m: f64,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct InplaceScaleStats {
    pub ptr_before: u64,
    pub ptr_after: u64,
    pub len: u32,
    pub alpha: f32,
    pub sum_before: f64,
    pub sum_after: f64,
    pub max_abs_before: f64,
    pub max_abs_after: f64,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameSolveConfig {
    pub story_count: u32,
    pub tolerance: f64,
    pub max_iter: u32,
    pub hardening_ratio: f64,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub pdelta_factor: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameSolveResult {
    pub converged: u8,
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameNdthaConfig {
    pub story_count: u32,
    pub step_count: u32,
    pub dt_s: f64,
    pub newmark_beta: f64,
    pub newmark_gamma: f64,
    pub tolerance: f64,
    // adaptive load-retry loop
    pub max_step_iterations: u32,
    pub adaptive_load_decay: f64,
    pub damping_force_cap_ratio: f64,
    // per-attempt Newton loop
    pub newton_max_iter: u32,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub hardening_ratio: f64,
    pub pdelta_factor: f64,
    pub collapse_drift_threshold_pct: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameNdthaResult {
    pub converged_all_steps: u8,
    pub rust_backend_all_steps: u8,
    pub collapsed: u8,
    pub collapse_step: i32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub step_count_completed: u32,
    pub max_plastic_story_count: u32,
    pub max_drift_ratio_pct: f64,
    pub avg_step_iterations: f64,
    pub residual_top_displacement_m: f64,
    pub residual_drift_ratio_pct: f64,
    pub status_code: i32,
}

fn ghost_at(w: &[f64], idx: isize, support_type: u32) -> f64 {
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

fn apply_euler_operator(
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
        let d2 = (ghost_at(w, ii + 1, support_type) - 2.0 * ghost_at(w, ii, support_type) + ghost_at(w, ii - 1, support_type))
            * inv_dx2;
        let d4 = (ghost_at(w, ii - 2, support_type)
            - 4.0 * ghost_at(w, ii - 1, support_type)
            + 6.0 * ghost_at(w, ii, support_type)
            - 4.0 * ghost_at(w, ii + 1, support_type)
            + ghost_at(w, ii + 2, support_type))
            * inv_dx4;
        out[i] = ei * d4 - kg * d2 + kw * ghost_at(w, ii, support_type);
    }
    out[0] = w[0];
    out[n - 1] = w[n - 1];
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    let mut s = 0.0;
    for i in 0..a.len() {
        s += a[i] * b[i];
    }
    s
}

fn cg_solve_euler(
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

fn fill_point_load(rhs: &mut [f64], length_m: f64, point_force_n: f64, point_position_m: f64) {
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

fn displacement_gradient(w: &[f64], dx: f64, out_theta: &mut [f64]) {
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

fn validate_cfg(cfg: &TrackSolveConfig) -> i32 {
    if cfg.length_m <= 0.0 {
        return -11;
    }
    if cfg.node_count < 7 {
        return -12;
    }
    if cfg.bending_stiffness_n_m2 <= 0.0 || cfg.shear_stiffness_n <= 0.0 {
        return -13;
    }
    if cfg.winkler_k_n_per_m2 < 0.0 || cfg.pasternak_g_n < 0.0 {
        return -14;
    }
    if cfg.tolerance <= 0.0 || cfg.cg_max_iter < 1 {
        return -15;
    }
    if cfg.support_type > 1 || cfg.theory > 1 {
        return -16;
    }
    0
}

fn validate_nl_cfg(cfg: &NlFrameSolveConfig) -> i32 {
    if cfg.story_count < 1 {
        return -31;
    }
    if cfg.tolerance <= 0.0 || cfg.max_iter < 1 {
        return -32;
    }
    if !(0.0..=1.0).contains(&cfg.hardening_ratio) {
        return -33;
    }
    if !(0.0 < cfg.line_search_decay && cfg.line_search_decay < 1.0) {
        return -34;
    }
    if !(0.0 < cfg.line_search_min && cfg.line_search_min <= 1.0) {
        return -35;
    }
    if cfg.pdelta_factor < 0.0 {
        return -36;
    }
    0
}

fn validate_ndtha_cfg(cfg: &NlFrameNdthaConfig) -> i32 {
    if cfg.story_count < 1 || cfg.step_count < 1 {
        return -41;
    }
    if cfg.dt_s <= 0.0 {
        return -42;
    }
    if cfg.newmark_beta <= 0.0 || cfg.newmark_gamma <= 0.0 {
        return -43;
    }
    if cfg.tolerance <= 0.0 {
        return -44;
    }
    if cfg.max_step_iterations < 1 || cfg.newton_max_iter < 1 {
        return -45;
    }
    if !(0.0 < cfg.adaptive_load_decay && cfg.adaptive_load_decay <= 1.0) {
        return -46;
    }
    if cfg.damping_force_cap_ratio <= 0.0 {
        return -47;
    }
    if !(0.0..=1.0).contains(&cfg.hardening_ratio) {
        return -48;
    }
    if cfg.pdelta_factor < 0.0 {
        return -49;
    }
    if !(0.0 < cfg.line_search_decay && cfg.line_search_decay < 1.0) {
        return -50;
    }
    if !(0.0 < cfg.line_search_min && cfg.line_search_min <= 1.0) {
        return -51;
    }
    if cfg.collapse_drift_threshold_pct <= 0.0 {
        return -52;
    }
    0
}

fn vec_norm_l2(v: &[f64]) -> f64 {
    let mut s = 0.0_f64;
    for x in v {
        s += x * x;
    }
    s.sqrt()
}

fn vec_norm_inf(v: &[f64]) -> f64 {
    let mut m = 0.0_f64;
    for x in v {
        m = m.max(x.abs());
    }
    m
}

fn solve_tridiagonal(lower: &[f64], diag: &[f64], upper: &[f64], rhs: &[f64], x_out: &mut [f64]) -> bool {
    let n = diag.len();
    if n == 0 || lower.len() + 1 != n || upper.len() + 1 != n || rhs.len() != n || x_out.len() != n {
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

fn assemble_internal_and_tangent(
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
        let kip1 = if i < n - 1 { spring_tangent[i + 1] } else { 0.0 };
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

fn compute_story_response(u: &[f64], story_h: &[f64], story_k: &[f64], out_drift_pct: &mut [f64], out_shear_kn: &mut [f64]) {
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

fn max_abs(v: &[f64]) -> f64 {
    let mut m = 0.0_f64;
    for x in v {
        m = m.max(x.abs());
    }
    m
}

#[allow(clippy::too_many_arguments)]
fn solve_ndtha_step(
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
            return (true, step_used, last_plastic, last_base_shear, last_residual_inf, total_backtracks);
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

#[no_mangle]
pub extern "C" fn phase1_rust_track_lf_solve_point_load(
    cfg_ptr: *const TrackSolveConfig,
    out_w_ptr: *mut f64,
    out_theta_ptr: *mut f64,
    out_len: u32,
    out_result_ptr: *mut TrackSolveResult,
) -> i32 {
    if cfg_ptr.is_null() || out_w_ptr.is_null() || out_theta_ptr.is_null() || out_result_ptr.is_null() {
        return -1;
    }

    let cfg = unsafe { &*cfg_ptr };
    let status = validate_cfg(cfg);
    if status != 0 {
        unsafe {
            (*out_result_ptr) = TrackSolveResult {
                converged: 0,
                iterations: 0,
                residual_inf: 0.0,
                max_abs_displacement_m: 0.0,
                mid_displacement_m: 0.0,
                status_code: status,
            };
        }
        return status;
    }

    let n = cfg.node_count as usize;
    if (out_len as usize) < n {
        return -2;
    }

    let out_w = unsafe { slice::from_raw_parts_mut(out_w_ptr, n) };
    let out_theta = unsafe { slice::from_raw_parts_mut(out_theta_ptr, n) };

    for i in 0..n {
        out_w[i] = 0.0;
        out_theta[i] = 0.0;
    }

    let mut rhs = vec![0.0_f64; n];
    fill_point_load(
        &mut rhs,
        cfg.length_m,
        cfg.point_force_n,
        cfg.point_position_m,
    );

    let dx = cfg.length_m / ((n - 1) as f64).max(1.0);
    let (converged, iterations, residual_inf) = cg_solve_euler(
        &rhs,
        out_w,
        dx,
        cfg.bending_stiffness_n_m2,
        cfg.winkler_k_n_per_m2,
        cfg.pasternak_g_n,
        cfg.support_type,
        cfg.tolerance,
        cfg.cg_max_iter as usize,
    );

    if cfg.theory == 1 {
        let eta_raw =
            12.0 * cfg.bending_stiffness_n_m2 / (cfg.shear_stiffness_n * cfg.length_m * cfg.length_m).max(EPS);
        let eta = eta_raw.max(0.0).min(0.75);
        let scale = 1.0 + eta;
        for i in 0..n {
            out_w[i] *= scale;
        }
    }

    displacement_gradient(out_w, dx, out_theta);

    let mut max_abs = 0.0_f64;
    for v in out_w.iter() {
        max_abs = max_abs.max(v.abs());
    }
    let mid_disp = out_w[n / 2];

    unsafe {
        (*out_result_ptr) = TrackSolveResult {
            converged: if converged { 1 } else { 0 },
            iterations: iterations as u32,
            residual_inf,
            max_abs_displacement_m: max_abs,
            mid_displacement_m: mid_disp,
            status_code: 0,
        };
    }
    0
}

#[no_mangle]
pub extern "C" fn phase1_rust_scale_inplace_f32(
    data_ptr: *mut f32,
    len: u32,
    alpha: f32,
    out_stats_ptr: *mut InplaceScaleStats,
) -> i32 {
    if data_ptr.is_null() || out_stats_ptr.is_null() || len == 0 {
        return -1;
    }
    let n = len as usize;
    let data = unsafe { slice::from_raw_parts_mut(data_ptr, n) };
    let ptr_before = data_ptr as usize as u64;

    let mut sum_before = 0.0_f64;
    let mut max_abs_before = 0.0_f64;
    for x in data.iter() {
        let v = *x as f64;
        sum_before += v;
        max_abs_before = max_abs_before.max(v.abs());
    }

    for x in data.iter_mut() {
        *x *= alpha;
    }

    let mut sum_after = 0.0_f64;
    let mut max_abs_after = 0.0_f64;
    for x in data.iter() {
        let v = *x as f64;
        sum_after += v;
        max_abs_after = max_abs_after.max(v.abs());
    }

    unsafe {
        (*out_stats_ptr) = InplaceScaleStats {
            ptr_before,
            ptr_after: data_ptr as usize as u64,
            len,
            alpha,
            sum_before,
            sum_after,
            max_abs_before,
            max_abs_after,
            status_code: 0,
        };
    }
    0
}

#[no_mangle]
pub extern "C" fn phase1_rust_nonlinear_frame_solve(
    cfg_ptr: *const NlFrameSolveConfig,
    story_k_ptr: *const f64,
    story_h_ptr: *const f64,
    story_p_ptr: *const f64,
    story_yield_drift_ptr: *const f64,
    floor_load_ptr: *const f64,
    out_u_ptr: *mut f64,
    out_len: u32,
    out_result_ptr: *mut NlFrameSolveResult,
) -> i32 {
    if cfg_ptr.is_null()
        || story_k_ptr.is_null()
        || story_h_ptr.is_null()
        || story_p_ptr.is_null()
        || story_yield_drift_ptr.is_null()
        || floor_load_ptr.is_null()
        || out_u_ptr.is_null()
        || out_result_ptr.is_null()
    {
        return -21;
    }

    let cfg = unsafe { &*cfg_ptr };
    let status = validate_nl_cfg(cfg);
    if status != 0 {
        unsafe {
            (*out_result_ptr) = NlFrameSolveResult {
                converged: 0,
                iterations: 0,
                residual_inf: 0.0,
                residual_l2: 0.0,
                max_abs_displacement_m: 0.0,
                top_displacement_m: 0.0,
                base_shear_kn: 0.0,
                plastic_story_count: 0,
                line_search_backtracks: 0,
                status_code: status,
            };
        }
        return status;
    }

    let n = cfg.story_count as usize;
    if (out_len as usize) < n {
        return -22;
    }

    let story_k = unsafe { slice::from_raw_parts(story_k_ptr, n) };
    let story_h = unsafe { slice::from_raw_parts(story_h_ptr, n) };
    let story_p = unsafe { slice::from_raw_parts(story_p_ptr, n) };
    let story_yield_drift = unsafe { slice::from_raw_parts(story_yield_drift_ptr, n) };
    let floor_load = unsafe { slice::from_raw_parts(floor_load_ptr, n) };
    let out_u = unsafe { slice::from_raw_parts_mut(out_u_ptr, n) };

    for i in 0..n {
        out_u[i] = 0.0;
    }

    let mut f_int = vec![0.0_f64; n];
    let mut lower = vec![0.0_f64; n.saturating_sub(1)];
    let mut diag = vec![0.0_f64; n];
    let mut upper = vec![0.0_f64; n.saturating_sub(1)];
    let mut residual = vec![0.0_f64; n];
    let mut du = vec![0.0_f64; n];
    let mut u_trial = vec![0.0_f64; n];

    let mut converged = false;
    let mut iters = 0_u32;
    let mut backtracks_total = 0_u32;

    for it in 1..=cfg.max_iter {
        let (_bs, _pc, _k0) = assemble_internal_and_tangent(
            out_u,
            story_k,
            story_h,
            story_p,
            story_yield_drift,
            cfg.hardening_ratio,
            cfg.pdelta_factor,
            &mut f_int,
            &mut lower,
            &mut diag,
            &mut upper,
        );

        for i in 0..n {
            residual[i] = floor_load[i] - f_int[i];
        }

        let r_inf = vec_norm_inf(&residual);
        if r_inf <= cfg.tolerance {
            converged = true;
            iters = it;
            break;
        }

        if !solve_tridiagonal(&lower, &diag, &upper, &residual, &mut du) {
            iters = it;
            break;
        }

        let baseline_norm = r_inf.max(EPS);
        let mut lambda = 1.0_f64;
        let mut accepted = false;
        let mut local_backtracks = 0_u32;

        while lambda >= cfg.line_search_min {
            for i in 0..n {
                u_trial[i] = out_u[i] + lambda * du[i];
            }

            let (_bs_t, _pc_t, _k0_t) = assemble_internal_and_tangent(
                &u_trial,
                story_k,
                story_h,
                story_p,
                story_yield_drift,
                cfg.hardening_ratio,
                cfg.pdelta_factor,
                &mut f_int,
                &mut lower,
                &mut diag,
                &mut upper,
            );
            for i in 0..n {
                residual[i] = floor_load[i] - f_int[i];
            }
            let trial_norm = vec_norm_inf(&residual);
            if trial_norm < baseline_norm {
                for i in 0..n {
                    out_u[i] = u_trial[i];
                }
                accepted = true;
                break;
            }
            lambda *= cfg.line_search_decay;
            local_backtracks += 1;
        }

        backtracks_total += local_backtracks;
        iters = it;
        if !accepted {
            break;
        }
    }

    let (base_shear_kn, plastic_count, _k0) = assemble_internal_and_tangent(
        out_u,
        story_k,
        story_h,
        story_p,
        story_yield_drift,
        cfg.hardening_ratio,
        cfg.pdelta_factor,
        &mut f_int,
        &mut lower,
        &mut diag,
        &mut upper,
    );
    for i in 0..n {
        residual[i] = floor_load[i] - f_int[i];
    }
    let residual_inf = vec_norm_inf(&residual);
    let residual_l2 = vec_norm_l2(&residual);

    let mut max_abs = 0.0_f64;
    for x in out_u.iter() {
        max_abs = max_abs.max(x.abs());
    }
    let top = out_u[n - 1];
    if residual_inf <= cfg.tolerance {
        converged = true;
    }

    unsafe {
        (*out_result_ptr) = NlFrameSolveResult {
            converged: if converged { 1 } else { 0 },
            iterations: iters,
            residual_inf,
            residual_l2,
            max_abs_displacement_m: max_abs,
            top_displacement_m: top,
            base_shear_kn,
            plastic_story_count: plastic_count,
            line_search_backtracks: backtracks_total,
            status_code: if converged { 0 } else { -37 },
        };
    }
    if converged {
        0
    } else {
        -37
    }
}

#[no_mangle]
pub extern "C" fn phase1_rust_nonlinear_frame_ndtha_solve(
    cfg_ptr: *const NlFrameNdthaConfig,
    story_k_ptr: *const f64,
    story_h_ptr: *const f64,
    story_p_ptr: *const f64,
    story_yield_drift_ptr: *const f64,
    story_mass_ptr: *const f64,
    story_damp_ptr: *const f64,
    floor_load_base_ptr: *const f64,
    ag_ptr: *const f64,
    out_top_disp_ptr: *mut f64,
    out_drift_ratio_ptr: *mut f64,
    out_base_shear_ptr: *mut f64,
    out_core_drift_ptr: *mut f64,
    out_core_shear_ptr: *mut f64,
    out_step_converged_ptr: *mut u8,
    out_step_iters_ptr: *mut u32,
    out_step_plastic_ptr: *mut u32,
    out_step_residual_ptr: *mut f64,
    out_story_drift_env_ptr: *mut f64,
    out_story_drift_final_ptr: *mut f64,
    out_result_ptr: *mut NlFrameNdthaResult,
) -> i32 {
    if cfg_ptr.is_null()
        || story_k_ptr.is_null()
        || story_h_ptr.is_null()
        || story_p_ptr.is_null()
        || story_yield_drift_ptr.is_null()
        || story_mass_ptr.is_null()
        || story_damp_ptr.is_null()
        || floor_load_base_ptr.is_null()
        || ag_ptr.is_null()
        || out_top_disp_ptr.is_null()
        || out_drift_ratio_ptr.is_null()
        || out_base_shear_ptr.is_null()
        || out_core_drift_ptr.is_null()
        || out_core_shear_ptr.is_null()
        || out_step_converged_ptr.is_null()
        || out_step_iters_ptr.is_null()
        || out_step_plastic_ptr.is_null()
        || out_step_residual_ptr.is_null()
        || out_story_drift_env_ptr.is_null()
        || out_story_drift_final_ptr.is_null()
        || out_result_ptr.is_null()
    {
        return -61;
    }

    let cfg = unsafe { &*cfg_ptr };
    let status = validate_ndtha_cfg(cfg);
    if status != 0 {
        unsafe {
            (*out_result_ptr) = NlFrameNdthaResult {
                converged_all_steps: 0,
                rust_backend_all_steps: 0,
                collapsed: 0,
                collapse_step: -1,
                collapse_time_s: 0.0,
                collapse_drift_ratio_pct: 0.0,
                collapse_top_displacement_m: 0.0,
                step_count_completed: 0,
                max_plastic_story_count: 0,
                max_drift_ratio_pct: 0.0,
                avg_step_iterations: 0.0,
                residual_top_displacement_m: 0.0,
                residual_drift_ratio_pct: 0.0,
                status_code: status,
            };
        }
        return status;
    }

    let n = cfg.story_count as usize;
    let s_count = cfg.step_count as usize;
    let story_k = unsafe { slice::from_raw_parts(story_k_ptr, n) };
    let story_h = unsafe { slice::from_raw_parts(story_h_ptr, n) };
    let story_p = unsafe { slice::from_raw_parts(story_p_ptr, n) };
    let story_yield_drift = unsafe { slice::from_raw_parts(story_yield_drift_ptr, n) };
    let story_mass = unsafe { slice::from_raw_parts(story_mass_ptr, n) };
    let story_damp = unsafe { slice::from_raw_parts(story_damp_ptr, n) };
    let floor_load_base = unsafe { slice::from_raw_parts(floor_load_base_ptr, n) };
    let ag = unsafe { slice::from_raw_parts(ag_ptr, s_count) };

    let out_top_disp = unsafe { slice::from_raw_parts_mut(out_top_disp_ptr, s_count) };
    let out_drift_ratio = unsafe { slice::from_raw_parts_mut(out_drift_ratio_ptr, s_count) };
    let out_base_shear = unsafe { slice::from_raw_parts_mut(out_base_shear_ptr, s_count) };
    let out_core_drift = unsafe { slice::from_raw_parts_mut(out_core_drift_ptr, s_count) };
    let out_core_shear = unsafe { slice::from_raw_parts_mut(out_core_shear_ptr, s_count) };
    let out_step_converged = unsafe { slice::from_raw_parts_mut(out_step_converged_ptr, s_count) };
    let out_step_iters = unsafe { slice::from_raw_parts_mut(out_step_iters_ptr, s_count) };
    let out_step_plastic = unsafe { slice::from_raw_parts_mut(out_step_plastic_ptr, s_count) };
    let out_step_residual = unsafe { slice::from_raw_parts_mut(out_step_residual_ptr, s_count) };
    let out_story_drift_env = unsafe { slice::from_raw_parts_mut(out_story_drift_env_ptr, n) };
    let out_story_drift_final = unsafe { slice::from_raw_parts_mut(out_story_drift_final_ptr, n) };

    for i in 0..s_count {
        out_top_disp[i] = 0.0;
        out_drift_ratio[i] = 0.0;
        out_base_shear[i] = 0.0;
        out_core_drift[i] = 0.0;
        out_core_shear[i] = 0.0;
        out_step_converged[i] = 0;
        out_step_iters[i] = 0;
        out_step_plastic[i] = 0;
        out_step_residual[i] = 0.0;
    }
    for i in 0..n {
        out_story_drift_env[i] = 0.0;
        out_story_drift_final[i] = 0.0;
    }

    let mut u = vec![0.0_f64; n];
    let mut v = vec![0.0_f64; n];
    let mut a = vec![0.0_f64; n];
    let mut u_next = vec![0.0_f64; n];
    let mut v_next = vec![0.0_f64; n];
    let mut a_next = vec![0.0_f64; n];

    let mut f_int = vec![0.0_f64; n];
    let mut lower = vec![0.0_f64; n.saturating_sub(1)];
    let mut diag = vec![0.0_f64; n];
    let mut upper = vec![0.0_f64; n.saturating_sub(1)];
    let mut residual = vec![0.0_f64; n];
    let mut du = vec![0.0_f64; n];
    let mut u_trial = vec![0.0_f64; n];
    let mut u_cand = vec![0.0_f64; n];
    let mut p_ext = vec![0.0_f64; n];
    let mut p_trial = vec![0.0_f64; n];
    let mut diag_eff = vec![0.0_f64; n];
    let mut story_drift_pct = vec![0.0_f64; n];
    let mut story_shear_kn = vec![0.0_f64; n];

    let mut height_shape = vec![0.0_f64; n];
    if n == 1 {
        height_shape[0] = 1.0;
    } else {
        for i in 0..n {
            let phase = (i as f64) * 2.0 * std::f64::consts::PI / (n as f64);
            height_shape[i] = 0.85 + 0.30 * phase.sin();
        }
    }

    let mut converged_all = true;
    let mut rust_ok_all = true;
    let mut collapsed = false;
    let mut collapse_step: i32 = -1;
    let mut collapse_time_s = 0.0_f64;
    let mut collapse_drift = 0.0_f64;
    let mut collapse_top = 0.0_f64;
    let mut max_plastic = 0_u32;
    let mut max_drift = 0.0_f64;
    let mut step_iter_sum = 0_u64;
    let mut step_count_completed = 0_u32;

    for s in 0..s_count {
        let ag_i = ag[s];
        let sign = if ag_i.abs() > 1e-12 { ag_i.signum() } else { 1.0 };
        let env = 1.0 + 0.50 * ((s as f64) / ((s_count.saturating_sub(1)).max(1) as f64));
        for i in 0..n {
            let p_static = floor_load_base[i] * height_shape[i] * env * (0.25 * ag_i + 0.02 * sign);
            let p_inertial = -(story_mass[i] * height_shape[i]) * (ag_i * 9.80665 * 0.05);
            let p_raw = p_static + p_inertial;
            let mut p_damp = story_damp[i] * v[i];
            let damp_cap = (p_raw.abs() * cfg.damping_force_cap_ratio).max(1.0);
            if p_damp > damp_cap {
                p_damp = damp_cap;
            } else if p_damp < -damp_cap {
                p_damp = -damp_cap;
            }
            p_ext[i] = p_raw - p_damp;
        }

        let (ok, step_used, plastic, base_shear_kn, residual_inf, _backtracks) = solve_ndtha_step(
            cfg,
            story_k,
            story_h,
            story_p,
            story_yield_drift,
            story_mass,
            story_damp,
            &p_ext,
            &u,
            &v,
            &a,
            &mut u_next,
            &mut v_next,
            &mut a_next,
            &mut f_int,
            &mut lower,
            &mut diag,
            &mut upper,
            &mut residual,
            &mut du,
            &mut u_trial,
            &mut u_cand,
            &mut p_trial,
            &mut diag_eff,
        );

        out_step_converged[s] = if ok { 1 } else { 0 };
        out_step_iters[s] = step_used;
        out_step_plastic[s] = plastic;
        out_step_residual[s] = residual_inf;
        step_iter_sum += step_used as u64;
        step_count_completed += 1;

        if !ok {
            converged_all = false;
            rust_ok_all = false;
            break;
        }

        for i in 0..n {
            u[i] = u_next[i];
            v[i] = v_next[i];
            a[i] = a_next[i];
        }

        compute_story_response(&u, story_h, story_k, &mut story_drift_pct, &mut story_shear_kn);
        for i in 0..n {
            out_story_drift_final[i] = story_drift_pct[i];
            out_story_drift_env[i] = out_story_drift_env[i].max(story_drift_pct[i].abs());
        }
        let drift_ratio = max_abs(&story_drift_pct);
        let top_m = u[n - 1];
        out_top_disp[s] = top_m;
        out_drift_ratio[s] = drift_ratio;
        out_base_shear[s] = base_shear_kn;
        out_core_drift[s] = story_drift_pct[0];
        out_core_shear[s] = story_shear_kn[0];

        max_plastic = max_plastic.max(plastic);
        max_drift = max_drift.max(drift_ratio);

        if drift_ratio > cfg.collapse_drift_threshold_pct {
            collapsed = true;
            converged_all = false;
            collapse_step = s as i32;
            collapse_time_s = (s as f64) * cfg.dt_s;
            collapse_drift = drift_ratio;
            collapse_top = top_m;
            break;
        }
    }

    let residual_top = if n > 0 { u[n - 1] } else { 0.0 };
    let residual_drift = max_abs(out_story_drift_final);
    let avg_step_iters = if step_count_completed > 0 {
        (step_iter_sum as f64) / (step_count_completed as f64)
    } else {
        0.0
    };

    let final_status = if converged_all && !collapsed { 0 } else { -62 };
    unsafe {
        (*out_result_ptr) = NlFrameNdthaResult {
            converged_all_steps: if converged_all { 1 } else { 0 },
            rust_backend_all_steps: if rust_ok_all { 1 } else { 0 },
            collapsed: if collapsed { 1 } else { 0 },
            collapse_step,
            collapse_time_s,
            collapse_drift_ratio_pct: collapse_drift,
            collapse_top_displacement_m: collapse_top,
            step_count_completed,
            max_plastic_story_count: max_plastic,
            max_drift_ratio_pct: max_drift,
            avg_step_iterations: avg_step_iters,
            residual_top_displacement_m: residual_top,
            residual_drift_ratio_pct: residual_drift,
            status_code: final_status,
        };
    }
    if final_status == 0 {
        0
    } else {
        final_status
    }
}

#[no_mangle]
pub extern "C" fn phase1_rust_version() -> u32 {
    3
}
