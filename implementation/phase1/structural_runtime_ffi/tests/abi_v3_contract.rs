use std::mem::{align_of, offset_of, size_of};
use std::ptr::{null, null_mut};

use structural_runtime_ffi::{
    phase1_rust_nonlinear_frame_ndtha_solve, phase1_rust_nonlinear_frame_solve,
    phase1_rust_scale_inplace_f32, phase1_rust_track_lf_solve_point_load, phase1_rust_version,
    InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
    NlFrameSolveResult, TrackSolveConfig, TrackSolveResult,
};

fn assert_close(actual: f64, expected: f64, tolerance: f64) {
    assert!(
        (actual - expected).abs() <= tolerance,
        "actual={actual:.17e} expected={expected:.17e} tolerance={tolerance:.3e}"
    );
}

fn track_result() -> TrackSolveResult {
    TrackSolveResult {
        converged: 0,
        iterations: 0,
        residual_inf: 0.0,
        max_abs_displacement_m: 0.0,
        mid_displacement_m: 0.0,
        status_code: 0,
    }
}

fn nonlinear_result() -> NlFrameSolveResult {
    NlFrameSolveResult {
        converged: 0,
        iterations: 0,
        residual_inf: 0.0,
        residual_l2: 0.0,
        max_abs_displacement_m: 0.0,
        top_displacement_m: 0.0,
        base_shear_kn: 0.0,
        plastic_story_count: 0,
        line_search_backtracks: 0,
        status_code: 0,
    }
}

fn ndtha_result() -> NlFrameNdthaResult {
    NlFrameNdthaResult {
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
        status_code: 0,
    }
}

#[test]
fn abi_v3_layout_is_frozen() {
    assert_eq!(phase1_rust_version(), 3);

    assert_eq!(
        (
            size_of::<TrackSolveConfig>(),
            align_of::<TrackSolveConfig>()
        ),
        (88, 8)
    );
    assert_eq!(offset_of!(TrackSolveConfig, length_m), 0);
    assert_eq!(offset_of!(TrackSolveConfig, node_count), 8);
    assert_eq!(offset_of!(TrackSolveConfig, support_type), 12);
    assert_eq!(offset_of!(TrackSolveConfig, theory), 16);
    assert_eq!(offset_of!(TrackSolveConfig, bending_stiffness_n_m2), 24);
    assert_eq!(offset_of!(TrackSolveConfig, shear_stiffness_n), 32);
    assert_eq!(offset_of!(TrackSolveConfig, winkler_k_n_per_m2), 40);
    assert_eq!(offset_of!(TrackSolveConfig, pasternak_g_n), 48);
    assert_eq!(offset_of!(TrackSolveConfig, tolerance), 56);
    assert_eq!(offset_of!(TrackSolveConfig, cg_max_iter), 64);
    assert_eq!(offset_of!(TrackSolveConfig, point_force_n), 72);
    assert_eq!(offset_of!(TrackSolveConfig, point_position_m), 80);

    assert_eq!(
        (
            size_of::<TrackSolveResult>(),
            align_of::<TrackSolveResult>()
        ),
        (40, 8)
    );
    assert_eq!(offset_of!(TrackSolveResult, converged), 0);
    assert_eq!(offset_of!(TrackSolveResult, iterations), 4);
    assert_eq!(offset_of!(TrackSolveResult, residual_inf), 8);
    assert_eq!(offset_of!(TrackSolveResult, max_abs_displacement_m), 16);
    assert_eq!(offset_of!(TrackSolveResult, mid_displacement_m), 24);
    assert_eq!(offset_of!(TrackSolveResult, status_code), 32);

    assert_eq!(
        (
            size_of::<InplaceScaleStats>(),
            align_of::<InplaceScaleStats>()
        ),
        (64, 8)
    );
    assert_eq!(offset_of!(InplaceScaleStats, ptr_before), 0);
    assert_eq!(offset_of!(InplaceScaleStats, ptr_after), 8);
    assert_eq!(offset_of!(InplaceScaleStats, len), 16);
    assert_eq!(offset_of!(InplaceScaleStats, alpha), 20);
    assert_eq!(offset_of!(InplaceScaleStats, sum_before), 24);
    assert_eq!(offset_of!(InplaceScaleStats, sum_after), 32);
    assert_eq!(offset_of!(InplaceScaleStats, max_abs_before), 40);
    assert_eq!(offset_of!(InplaceScaleStats, max_abs_after), 48);
    assert_eq!(offset_of!(InplaceScaleStats, status_code), 56);

    assert_eq!(
        (
            size_of::<NlFrameSolveConfig>(),
            align_of::<NlFrameSolveConfig>()
        ),
        (56, 8)
    );
    assert_eq!(offset_of!(NlFrameSolveConfig, story_count), 0);
    assert_eq!(offset_of!(NlFrameSolveConfig, tolerance), 8);
    assert_eq!(offset_of!(NlFrameSolveConfig, max_iter), 16);
    assert_eq!(offset_of!(NlFrameSolveConfig, hardening_ratio), 24);
    assert_eq!(offset_of!(NlFrameSolveConfig, line_search_decay), 32);
    assert_eq!(offset_of!(NlFrameSolveConfig, line_search_min), 40);
    assert_eq!(offset_of!(NlFrameSolveConfig, pdelta_factor), 48);

    assert_eq!(
        (
            size_of::<NlFrameSolveResult>(),
            align_of::<NlFrameSolveResult>()
        ),
        (64, 8)
    );
    assert_eq!(offset_of!(NlFrameSolveResult, converged), 0);
    assert_eq!(offset_of!(NlFrameSolveResult, iterations), 4);
    assert_eq!(offset_of!(NlFrameSolveResult, residual_inf), 8);
    assert_eq!(offset_of!(NlFrameSolveResult, residual_l2), 16);
    assert_eq!(offset_of!(NlFrameSolveResult, max_abs_displacement_m), 24);
    assert_eq!(offset_of!(NlFrameSolveResult, top_displacement_m), 32);
    assert_eq!(offset_of!(NlFrameSolveResult, base_shear_kn), 40);
    assert_eq!(offset_of!(NlFrameSolveResult, plastic_story_count), 48);
    assert_eq!(offset_of!(NlFrameSolveResult, line_search_backtracks), 52);
    assert_eq!(offset_of!(NlFrameSolveResult, status_code), 56);

    assert_eq!(
        (
            size_of::<NlFrameNdthaConfig>(),
            align_of::<NlFrameNdthaConfig>()
        ),
        (112, 8)
    );
    assert_eq!(offset_of!(NlFrameNdthaConfig, story_count), 0);
    assert_eq!(offset_of!(NlFrameNdthaConfig, step_count), 4);
    assert_eq!(offset_of!(NlFrameNdthaConfig, dt_s), 8);
    assert_eq!(offset_of!(NlFrameNdthaConfig, newmark_beta), 16);
    assert_eq!(offset_of!(NlFrameNdthaConfig, newmark_gamma), 24);
    assert_eq!(offset_of!(NlFrameNdthaConfig, tolerance), 32);
    assert_eq!(offset_of!(NlFrameNdthaConfig, max_step_iterations), 40);
    assert_eq!(offset_of!(NlFrameNdthaConfig, adaptive_load_decay), 48);
    assert_eq!(offset_of!(NlFrameNdthaConfig, damping_force_cap_ratio), 56);
    assert_eq!(offset_of!(NlFrameNdthaConfig, newton_max_iter), 64);
    assert_eq!(offset_of!(NlFrameNdthaConfig, line_search_decay), 72);
    assert_eq!(offset_of!(NlFrameNdthaConfig, line_search_min), 80);
    assert_eq!(offset_of!(NlFrameNdthaConfig, hardening_ratio), 88);
    assert_eq!(offset_of!(NlFrameNdthaConfig, pdelta_factor), 96);
    assert_eq!(
        offset_of!(NlFrameNdthaConfig, collapse_drift_threshold_pct),
        104
    );

    assert_eq!(
        (
            size_of::<NlFrameNdthaResult>(),
            align_of::<NlFrameNdthaResult>()
        ),
        (80, 8)
    );
    assert_eq!(offset_of!(NlFrameNdthaResult, converged_all_steps), 0);
    assert_eq!(offset_of!(NlFrameNdthaResult, rust_backend_all_steps), 1);
    assert_eq!(offset_of!(NlFrameNdthaResult, collapsed), 2);
    assert_eq!(offset_of!(NlFrameNdthaResult, collapse_step), 4);
    assert_eq!(offset_of!(NlFrameNdthaResult, collapse_time_s), 8);
    assert_eq!(offset_of!(NlFrameNdthaResult, collapse_drift_ratio_pct), 16);
    assert_eq!(
        offset_of!(NlFrameNdthaResult, collapse_top_displacement_m),
        24
    );
    assert_eq!(offset_of!(NlFrameNdthaResult, step_count_completed), 32);
    assert_eq!(offset_of!(NlFrameNdthaResult, max_plastic_story_count), 36);
    assert_eq!(offset_of!(NlFrameNdthaResult, max_drift_ratio_pct), 40);
    assert_eq!(offset_of!(NlFrameNdthaResult, avg_step_iterations), 48);
    assert_eq!(
        offset_of!(NlFrameNdthaResult, residual_top_displacement_m),
        56
    );
    assert_eq!(offset_of!(NlFrameNdthaResult, residual_drift_ratio_pct), 64);
    assert_eq!(offset_of!(NlFrameNdthaResult, status_code), 72);
}

#[test]
fn legacy_error_codes_and_failure_atomicity_are_frozen() {
    assert_eq!(
        phase1_rust_track_lf_solve_point_load(null(), null_mut(), null_mut(), 0, null_mut(),),
        -1
    );
    assert_eq!(
        phase1_rust_scale_inplace_f32(null_mut(), 0, 1.0, null_mut()),
        -1
    );
    assert_eq!(
        phase1_rust_nonlinear_frame_solve(
            null(),
            null(),
            null(),
            null(),
            null(),
            null(),
            null_mut(),
            0,
            null_mut(),
        ),
        -21
    );
    assert_eq!(
        phase1_rust_nonlinear_frame_ndtha_solve(
            null(),
            null(),
            null(),
            null(),
            null(),
            null(),
            null(),
            null(),
            null(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
            null_mut(),
        ),
        -61
    );

    let invalid_track = TrackSolveConfig {
        length_m: 0.0,
        node_count: 9,
        support_type: 0,
        theory: 0,
        bending_stiffness_n_m2: 1.0,
        shear_stiffness_n: 1.0,
        winkler_k_n_per_m2: 0.0,
        pasternak_g_n: 0.0,
        tolerance: 1.0e-9,
        cg_max_iter: 1,
        point_force_n: 1.0,
        point_position_m: 0.0,
    };
    let mut displacement = [17.0; 9];
    let mut rotation = [19.0; 9];
    let mut result = track_result();
    assert_eq!(
        phase1_rust_track_lf_solve_point_load(
            &invalid_track,
            displacement.as_mut_ptr(),
            rotation.as_mut_ptr(),
            9,
            &mut result,
        ),
        -11
    );
    assert_eq!(result.status_code, -11);
    assert!(displacement
        .iter()
        .all(|value| value.to_bits() == 17.0_f64.to_bits()));
    assert!(rotation
        .iter()
        .all(|value| value.to_bits() == 19.0_f64.to_bits()));
}

#[test]
fn track_and_inplace_golden_vectors_are_frozen() {
    let config = TrackSolveConfig {
        length_m: 10.0,
        node_count: 9,
        support_type: 0,
        theory: 0,
        bending_stiffness_n_m2: 1.0e8,
        shear_stiffness_n: 1.0e9,
        winkler_k_n_per_m2: 1.0e5,
        pasternak_g_n: 1.0e4,
        tolerance: 1.0e-9,
        cg_max_iter: 500,
        point_force_n: -10_000.0,
        point_position_m: 5.0,
    };
    let mut displacement = [0.0; 9];
    let mut rotation = [0.0; 9];
    let mut result = track_result();
    assert_eq!(
        phase1_rust_track_lf_solve_point_load(
            &config,
            displacement.as_mut_ptr(),
            rotation.as_mut_ptr(),
            9,
            &mut result,
        ),
        0
    );
    assert_eq!(result.converged, 1);
    assert_eq!(result.iterations, 4);
    assert_eq!(result.status_code, 0);
    assert_close(result.residual_inf, 7.657_748_132_248_844e-10, 1.0e-20);
    assert_close(
        result.max_abs_displacement_m,
        0.001_945_845_157_517_316,
        1.0e-16,
    );
    assert_close(
        result.mid_displacement_m,
        -0.001_945_845_157_517_316,
        1.0e-16,
    );
    let expected_displacement = [
        0.0,
        -0.000_703_792_692_632_069_1,
        -0.001_321_670_876_610_801,
        -0.001_765_988_375_262_38,
        -0.001_945_845_157_517_316,
        -0.001_765_988_375_262_380_7,
        -0.001_321_670_876_610_801_4,
        -0.000_703_792_692_632_069_1,
        0.0,
    ];
    for (actual, expected) in displacement.iter().zip(expected_displacement) {
        assert_close(*actual, expected, 1.0e-16);
    }

    let mut values = [1.0_f32, -2.0, 0.5, 4.0];
    let pointer = values.as_mut_ptr() as usize as u64;
    let mut stats = InplaceScaleStats {
        ptr_before: 0,
        ptr_after: 0,
        len: 0,
        alpha: 0.0,
        sum_before: 0.0,
        sum_after: 0.0,
        max_abs_before: 0.0,
        max_abs_after: 0.0,
        status_code: -1,
    };
    assert_eq!(
        phase1_rust_scale_inplace_f32(values.as_mut_ptr(), 4, 1.25, &mut stats),
        0
    );
    assert_eq!(
        values.map(f32::to_bits),
        [1.25_f32, -2.5, 0.625, 5.0].map(f32::to_bits)
    );
    assert_eq!(stats.ptr_before, pointer);
    assert_eq!(stats.ptr_after, pointer);
    assert_eq!(stats.len, 4);
    assert_close(stats.sum_before, 3.5, 0.0);
    assert_close(stats.sum_after, 4.375, 0.0);
    assert_close(stats.max_abs_before, 4.0, 0.0);
    assert_close(stats.max_abs_after, 5.0, 0.0);
    assert_eq!(stats.status_code, 0);
}

#[test]
fn nonlinear_static_golden_vector_is_frozen() {
    let config = NlFrameSolveConfig {
        story_count: 3,
        tolerance: 1.0e-7,
        max_iter: 60,
        hardening_ratio: 0.04,
        line_search_decay: 0.5,
        line_search_min: 0.031_25,
        pdelta_factor: 1.0,
    };
    let stiffness = [1.0e8, 9.0e7, 8.0e7];
    let heights = [3.0, 3.0, 3.0];
    let axial = [1.0e6, 8.0e5, 6.0e5];
    let yield_drift = [0.02, 0.02, 0.02];
    let loads = [10_000.0, 8_000.0, 6_000.0];
    let mut displacement = [0.0; 3];
    let mut result = nonlinear_result();

    assert_eq!(
        phase1_rust_nonlinear_frame_solve(
            &config,
            stiffness.as_ptr(),
            heights.as_ptr(),
            axial.as_ptr(),
            yield_drift.as_ptr(),
            loads.as_ptr(),
            displacement.as_mut_ptr(),
            3,
            &mut result,
        ),
        0
    );
    assert_eq!(result.converged, 1);
    assert_eq!(result.iterations, 6);
    assert_eq!(result.plastic_story_count, 0);
    assert_eq!(result.line_search_backtracks, 0);
    assert_eq!(result.status_code, 0);
    assert_close(result.residual_inf, 6.795_744_411_647_32e-9, 1.0e-16);
    assert_close(result.residual_l2, 7.319_227_424_693_27e-9, 1.0e-16);
    assert_close(result.base_shear_kn, 24.000_000_000_010_04, 1.0e-10);
    let expected = [
        0.000_240_000_000_000_100_4,
        0.000_395_555_555_555_692,
        0.000_470_555_555_555_699_4,
    ];
    for (actual, expected) in displacement.iter().zip(expected) {
        assert_close(*actual, expected, 1.0e-16);
    }
    assert_close(result.top_displacement_m, expected[2], 1.0e-16);
    assert_close(result.max_abs_displacement_m, expected[2], 1.0e-16);
}

#[test]
fn nonlinear_ndtha_golden_vector_is_frozen() {
    let config = NlFrameNdthaConfig {
        story_count: 2,
        step_count: 3,
        dt_s: 0.01,
        newmark_beta: 0.25,
        newmark_gamma: 0.5,
        tolerance: 1.0e-5,
        max_step_iterations: 16,
        adaptive_load_decay: 0.82,
        damping_force_cap_ratio: 0.6,
        newton_max_iter: 120,
        line_search_decay: 0.5,
        line_search_min: 0.031_25,
        hardening_ratio: 0.2,
        pdelta_factor: 1.0,
        collapse_drift_threshold_pct: 10.0,
    };
    let stiffness = [1.0e8, 9.0e7];
    let heights = [3.0, 3.0];
    let axial = [1.0e6, 8.0e5];
    let yield_drift = [0.02, 0.02];
    let mass = [10_000.0, 8_000.0];
    let damping = [1_000.0, 900.0];
    let loads = [10_000.0, 8_000.0];
    let acceleration = [0.0, 0.01, -0.005];
    let mut top = [0.0; 3];
    let mut drift = [0.0; 3];
    let mut base = [0.0; 3];
    let mut core_drift = [0.0; 3];
    let mut core_shear = [0.0; 3];
    let mut step_converged = [0_u8; 3];
    let mut step_iterations = [0_u32; 3];
    let mut step_plastic = [0_u32; 3];
    let mut step_residual = [0.0; 3];
    let mut drift_envelope = [0.0; 2];
    let mut drift_final = [0.0; 2];
    let mut result = ndtha_result();

    assert_eq!(
        phase1_rust_nonlinear_frame_ndtha_solve(
            &config,
            stiffness.as_ptr(),
            heights.as_ptr(),
            axial.as_ptr(),
            yield_drift.as_ptr(),
            mass.as_ptr(),
            damping.as_ptr(),
            loads.as_ptr(),
            acceleration.as_ptr(),
            top.as_mut_ptr(),
            drift.as_mut_ptr(),
            base.as_mut_ptr(),
            core_drift.as_mut_ptr(),
            core_shear.as_mut_ptr(),
            step_converged.as_mut_ptr(),
            step_iterations.as_mut_ptr(),
            step_plastic.as_mut_ptr(),
            step_residual.as_mut_ptr(),
            drift_envelope.as_mut_ptr(),
            drift_final.as_mut_ptr(),
            &mut result,
        ),
        0
    );
    assert_eq!(step_converged, [1, 1, 1]);
    assert_eq!(step_iterations, [1, 1, 1]);
    assert_eq!(step_plastic, [0, 0, 0]);
    assert_eq!(result.converged_all_steps, 1);
    assert_eq!(result.rust_backend_all_steps, 1);
    assert_eq!(result.collapsed, 0);
    assert_eq!(result.collapse_step, -1);
    assert_eq!(result.step_count_completed, 3);
    assert_eq!(result.max_plastic_story_count, 0);
    assert_eq!(result.status_code, 0);

    let expected_top = [
        4.084_273_705_964_167e-7,
        2.008_674_095_445_957e-6,
        3.795_754_248_884_991e-6,
    ];
    let expected_drift = [
        1.167_731_071_112_621_1e-5,
        5.301_851_826_285_648e-5,
        8.560_401_406_754_784e-5,
    ];
    let expected_base = [
        0.035_031_932_133_378_636,
        0.159_055_554_788_569_42,
        0.256_812_042_202_643_6,
    ];
    let expected_residual = [
        9.752_318_419_486_983e-8,
        2.736_757_522_825_428e-7,
        4.408_786_935_528_042e-8,
    ];
    for (actual, expected) in top.iter().zip(expected_top) {
        assert_close(*actual, expected, 1.0e-16);
    }
    for (actual, expected) in drift.iter().zip(expected_drift) {
        assert_close(*actual, expected, 1.0e-15);
    }
    for (actual, expected) in base.iter().zip(expected_base) {
        assert_close(*actual, expected, 1.0e-12);
    }
    for (actual, expected) in step_residual.iter().zip(expected_residual) {
        assert_close(*actual, expected, 1.0e-15);
    }
    assert_close(drift_final[0], 8.560_401_406_754_784e-5, 1.0e-15);
    assert_close(drift_final[1], 4.092_112_756_195_183_6e-5, 1.0e-15);
    for (envelope, final_value) in drift_envelope.iter().zip(drift_final) {
        assert_close(*envelope, final_value, 0.0);
    }
    assert_close(result.max_drift_ratio_pct, expected_drift[2], 1.0e-15);
    assert_close(result.avg_step_iterations, 1.0, 0.0);
    assert_close(result.residual_top_displacement_m, expected_top[2], 1.0e-16);
    assert_close(result.residual_drift_ratio_pct, expected_drift[2], 1.0e-15);
}
