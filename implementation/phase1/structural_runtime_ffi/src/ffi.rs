use std::slice;

use crate::runtime::{
    assemble_internal_and_tangent, cg_solve_euler, compute_story_response, displacement_gradient,
    fill_point_load, max_abs, solve_ndtha_step, solve_tridiagonal, validate_cfg,
    validate_ndtha_cfg, validate_nl_cfg, vec_norm_inf, vec_norm_l2, EPS,
};
use structural_ffi_sys::legacy_runtime_v3::{
    InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
    NlFrameSolveResult, TrackSolveConfig, TrackSolveResult, INPLACE_SCALE_STATUS_INVALID_ARGUMENT,
    NDTHA_STATUS_NONCONVERGENCE_OR_COLLAPSE, NDTHA_STATUS_NULL_ARGUMENT,
    NONLINEAR_STATIC_STATUS_NONCONVERGENCE, NONLINEAR_STATIC_STATUS_NULL_ARGUMENT,
    NONLINEAR_STATIC_STATUS_OUTPUT_TOO_SMALL, STRUCTURAL_RUNTIME_ABI_V3,
    TRACK_STATUS_NULL_ARGUMENT, TRACK_STATUS_OUTPUT_TOO_SMALL,
};

#[no_mangle]
pub extern "C" fn phase1_rust_track_lf_solve_point_load(
    cfg_ptr: *const TrackSolveConfig,
    out_w_ptr: *mut f64,
    out_theta_ptr: *mut f64,
    out_len: u32,
    out_result_ptr: *mut TrackSolveResult,
) -> i32 {
    if cfg_ptr.is_null()
        || out_w_ptr.is_null()
        || out_theta_ptr.is_null()
        || out_result_ptr.is_null()
    {
        return TRACK_STATUS_NULL_ARGUMENT;
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
        return TRACK_STATUS_OUTPUT_TOO_SMALL;
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
        let eta_raw = 12.0 * cfg.bending_stiffness_n_m2
            / (cfg.shear_stiffness_n * cfg.length_m * cfg.length_m).max(EPS);
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
        return INPLACE_SCALE_STATUS_INVALID_ARGUMENT;
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
        return NONLINEAR_STATIC_STATUS_NULL_ARGUMENT;
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
        return NONLINEAR_STATIC_STATUS_OUTPUT_TOO_SMALL;
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
            status_code: if converged {
                0
            } else {
                NONLINEAR_STATIC_STATUS_NONCONVERGENCE
            },
        };
    }
    if converged {
        0
    } else {
        NONLINEAR_STATIC_STATUS_NONCONVERGENCE
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
        return NDTHA_STATUS_NULL_ARGUMENT;
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
        let sign = if ag_i.abs() > 1e-12 {
            ag_i.signum()
        } else {
            1.0
        };
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

        compute_story_response(
            &u,
            story_h,
            story_k,
            &mut story_drift_pct,
            &mut story_shear_kn,
        );
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

    let final_status = if converged_all && !collapsed {
        0
    } else {
        NDTHA_STATUS_NONCONVERGENCE_OR_COLLAPSE
    };
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
    STRUCTURAL_RUNTIME_ABI_V3
}
