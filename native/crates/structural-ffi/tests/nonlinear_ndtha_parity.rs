use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearNdthaCaseV3,
};
use structural_ffi::{Api, NonlinearNdthaSolution};
use structural_ffi_sys::{
    SA_ERR_INVALID_ARGUMENT, SA_ERR_NONCONVERGENCE, SA_EXECUTION_BACKEND_CPU,
};
use structural_runtime_ffi::{
    phase1_rust_nonlinear_frame_ndtha_solve, NlFrameNdthaConfig, NlFrameNdthaResult,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn golden_case() -> NonlinearNdthaCaseV3 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json"),
    )
    .expect("tracked neutral fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict nonlinear NDTHA fixture") {
        LegacyRuntimeCaseV3::NonlinearNdtha(case) => *case,
        _ => panic!("nonlinear NDTHA fixture decoded as another family"),
    }
}

fn legacy_config(case: &NonlinearNdthaCaseV3) -> NlFrameNdthaConfig {
    NlFrameNdthaConfig {
        story_count: case.config.story_count,
        step_count: case.config.step_count,
        dt_s: case.config.dt_s,
        newmark_beta: case.config.newmark_beta,
        newmark_gamma: case.config.newmark_gamma,
        tolerance: case.config.tolerance,
        max_step_iterations: case.config.max_step_iterations,
        adaptive_load_decay: case.config.adaptive_load_decay,
        damping_force_cap_ratio: case.config.damping_force_cap_ratio,
        newton_max_iter: case.config.newton_max_iter,
        line_search_decay: case.config.line_search_decay,
        line_search_min: case.config.line_search_min,
        hardening_ratio: case.config.hardening_ratio,
        pdelta_factor: case.config.pdelta_factor,
        collapse_drift_threshold_pct: case.config.collapse_drift_threshold_pct,
    }
}

struct LegacySolution {
    status: i32,
    result: NlFrameNdthaResult,
    top_displacement_m: Vec<f64>,
    drift_ratio_pct: Vec<f64>,
    base_shear_kn: Vec<f64>,
    core_drift_pct: Vec<f64>,
    core_shear_kn: Vec<f64>,
    step_converged: Vec<u8>,
    step_iterations: Vec<u32>,
    step_plastic_story_count: Vec<u32>,
    step_residual_inf: Vec<f64>,
    story_drift_envelope_pct: Vec<f64>,
    final_story_drift_pct: Vec<f64>,
}

fn solve_legacy(case: &NonlinearNdthaCaseV3) -> LegacySolution {
    let story_count = usize::try_from(case.config.story_count).expect("story count");
    let step_count = usize::try_from(case.config.step_count).expect("step count");
    let mut solution = LegacySolution {
        status: i32::MIN,
        result: NlFrameNdthaResult {
            converged_all_steps: 0,
            rust_backend_all_steps: 0,
            collapsed: 0,
            collapse_step: i32::MIN,
            collapse_time_s: 0.0,
            collapse_drift_ratio_pct: 0.0,
            collapse_top_displacement_m: 0.0,
            step_count_completed: 0,
            max_plastic_story_count: 0,
            max_drift_ratio_pct: 0.0,
            avg_step_iterations: 0.0,
            residual_top_displacement_m: 0.0,
            residual_drift_ratio_pct: 0.0,
            status_code: i32::MIN,
        },
        top_displacement_m: vec![0.0; step_count],
        drift_ratio_pct: vec![0.0; step_count],
        base_shear_kn: vec![0.0; step_count],
        core_drift_pct: vec![0.0; step_count],
        core_shear_kn: vec![0.0; step_count],
        step_converged: vec![0; step_count],
        step_iterations: vec![0; step_count],
        step_plastic_story_count: vec![0; step_count],
        step_residual_inf: vec![0.0; step_count],
        story_drift_envelope_pct: vec![0.0; story_count],
        final_story_drift_pct: vec![0.0; story_count],
    };
    solution.status = phase1_rust_nonlinear_frame_ndtha_solve(
        &legacy_config(case),
        case.inputs.story_k_n_per_m.as_ptr(),
        case.inputs.story_h_m.as_ptr(),
        case.inputs.story_axial_n.as_ptr(),
        case.inputs.story_yield_drift_m.as_ptr(),
        case.inputs.story_mass_kg.as_ptr(),
        case.inputs.story_damping_n_s_per_m.as_ptr(),
        case.inputs.floor_load_base_n.as_ptr(),
        case.inputs.ag_g.as_ptr(),
        solution.top_displacement_m.as_mut_ptr(),
        solution.drift_ratio_pct.as_mut_ptr(),
        solution.base_shear_kn.as_mut_ptr(),
        solution.core_drift_pct.as_mut_ptr(),
        solution.core_shear_kn.as_mut_ptr(),
        solution.step_converged.as_mut_ptr(),
        solution.step_iterations.as_mut_ptr(),
        solution.step_plastic_story_count.as_mut_ptr(),
        solution.step_residual_inf.as_mut_ptr(),
        solution.story_drift_envelope_pct.as_mut_ptr(),
        solution.final_story_drift_pct.as_mut_ptr(),
        &mut solution.result,
    );
    solution
}

fn assert_close(actual: f64, expected: f64) {
    assert!(
        (actual - expected).abs() <= 1.0e-15,
        "expected {expected:.17e}, received {actual:.17e}"
    );
}

fn assert_vector_close(actual: &[f64], expected: &[f64]) {
    assert_eq!(actual.len(), expected.len());
    for (actual, expected) in actual.iter().zip(expected) {
        assert_close(*actual, *expected);
    }
}

fn assert_matches_legacy(cpp: &NonlinearNdthaSolution, legacy: &LegacySolution) {
    assert_eq!(legacy.status, 0);
    assert_eq!(legacy.result.status_code, 0);
    assert_eq!(legacy.result.converged_all_steps, 1);
    assert_eq!(legacy.result.rust_backend_all_steps, 1);
    assert!(cpp.converged_all_steps);
    assert!(!cpp.collapsed);
    assert_eq!(cpp.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(cpp.fallback_count, 0);
    assert_eq!(cpp.collapse_step, legacy.result.collapse_step);
    assert_eq!(cpp.step_count_completed, legacy.result.step_count_completed);
    assert_eq!(
        cpp.max_plastic_story_count,
        legacy.result.max_plastic_story_count
    );
    for (actual, expected) in [
        (cpp.collapse_time_s, legacy.result.collapse_time_s),
        (
            cpp.collapse_drift_ratio_pct,
            legacy.result.collapse_drift_ratio_pct,
        ),
        (
            cpp.collapse_top_displacement_m,
            legacy.result.collapse_top_displacement_m,
        ),
        (cpp.max_drift_ratio_pct, legacy.result.max_drift_ratio_pct),
        (cpp.avg_step_iterations, legacy.result.avg_step_iterations),
        (
            cpp.residual_top_displacement_m,
            legacy.result.residual_top_displacement_m,
        ),
        (
            cpp.residual_drift_ratio_pct,
            legacy.result.residual_drift_ratio_pct,
        ),
    ] {
        assert_close(actual, expected);
    }
    assert_vector_close(&cpp.response.top_displacement_m, &legacy.top_displacement_m);
    assert_vector_close(&cpp.response.drift_ratio_pct, &legacy.drift_ratio_pct);
    assert_vector_close(&cpp.response.base_shear_kn, &legacy.base_shear_kn);
    assert_vector_close(&cpp.response.core_drift_pct, &legacy.core_drift_pct);
    assert_vector_close(&cpp.response.core_shear_kn, &legacy.core_shear_kn);
    assert_eq!(
        cpp.response.step_converged,
        legacy
            .step_converged
            .iter()
            .map(|value| *value == 1)
            .collect::<Vec<_>>()
    );
    assert_eq!(cpp.response.step_iterations, legacy.step_iterations);
    assert_eq!(
        cpp.response.step_plastic_story_count,
        legacy.step_plastic_story_count
    );
    assert_vector_close(&cpp.response.step_residual_inf, &legacy.step_residual_inf);
    assert_vector_close(
        &cpp.response.story_drift_envelope_pct,
        &legacy.story_drift_envelope_pct,
    );
    assert_vector_close(
        &cpp.response.final_story_drift_pct,
        &legacy.final_story_drift_pct,
    );
}

#[test]
fn safe_v1_4_cpp_path_matches_the_complete_frozen_legacy_rust_result() {
    let case = golden_case();
    let api = Api::load_nonlinear_ndtha().expect("ABI v1.4 nonlinear NDTHA table");
    let cpp = api
        .solve_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("C++ nonlinear NDTHA CPU solve");
    let legacy = solve_legacy(&case);
    assert_matches_legacy(&cpp, &legacy);

    assert_eq!(
        cpp.response.top_displacement_m,
        case.result.response.top_displacement_m
    );
    assert_eq!(
        cpp.response.drift_ratio_pct,
        case.result.response.drift_ratio_pct
    );
    assert_eq!(
        cpp.response.base_shear_kn,
        case.result.response.base_shear_kn
    );
    assert_eq!(
        cpp.response.core_drift_pct,
        case.result.response.core_drift_pct
    );
    assert_eq!(
        cpp.response.core_shear_kn,
        case.result.response.core_shear_kn
    );
    assert_eq!(
        cpp.response.step_converged,
        case.result.response.step_converged
    );
    assert_eq!(
        cpp.response.step_iterations,
        case.result.response.step_iterations
    );
    assert_eq!(
        cpp.response.step_plastic_story_count,
        case.result.response.step_plastic_story_count
    );
    assert_eq!(
        cpp.response.step_residual_inf,
        case.result.response.step_residual_inf
    );
    assert_eq!(
        cpp.response.story_drift_envelope_pct,
        case.result.response.story_drift_envelope_pct
    );
    assert_eq!(
        cpp.response.final_story_drift_pct,
        case.result.response.final_story_drift_pct
    );
}

#[test]
fn safe_wrapper_preserves_invalid_nonconvergence_and_collapse_taxonomy() {
    let case = golden_case();
    let api = Api::load_nonlinear_ndtha().expect("ABI v1.4 nonlinear NDTHA table");

    let mut invalid = case.config.clone();
    invalid.hardening_ratio = 2.0;
    let error = api
        .solve_nonlinear_ndtha(&invalid, &case.inputs)
        .expect_err("invalid hardening ratio");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut invalid_inputs = case.inputs.clone();
    invalid_inputs.story_mass_kg[0] = f64::NAN;
    let error = api
        .solve_nonlinear_ndtha(&case.config, &invalid_inputs)
        .expect_err("non-finite mass");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut mismatched = case.inputs.clone();
    mismatched.ag_g.pop();
    let error = api
        .solve_nonlinear_ndtha(&case.config, &mismatched)
        .expect_err("mismatched acceleration length");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut nonconverged = case.config.clone();
    nonconverged.max_step_iterations = 1;
    nonconverged.newton_max_iter = 1;
    nonconverged.tolerance = 1.0e-30;
    let error = api
        .solve_nonlinear_ndtha(&nonconverged, &case.inputs)
        .expect_err("bounded Newmark/Newton nonconvergence");
    assert_eq!(error.code, SA_ERR_NONCONVERGENCE);

    let mut collapse = case.config.clone();
    collapse.collapse_drift_threshold_pct = 1.0e-6;
    let collapsed = api
        .solve_nonlinear_ndtha(&collapse, &case.inputs)
        .expect("physical collapse is a complete terminal result");
    assert!(!collapsed.converged_all_steps);
    assert!(collapsed.collapsed);
    assert_eq!(collapsed.collapse_step, 0);
    assert_eq!(collapsed.step_count_completed, 1);
}

#[test]
fn nonlinear_ndtha_cpu_operation_is_reentrant_and_deterministic() {
    let case = Arc::new(golden_case());
    let expected = Api::load_nonlinear_ndtha()
        .expect("ABI v1.4 nonlinear NDTHA table")
        .solve_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("reference solve");
    let workers: Vec<_> = (0..8)
        .map(|_| {
            let case = Arc::clone(&case);
            let expected = expected.clone();
            thread::spawn(move || {
                let api = Api::load_nonlinear_ndtha().expect("thread-local table copy");
                for _ in 0..64 {
                    assert_eq!(
                        api.solve_nonlinear_ndtha(&case.config, &case.inputs)
                            .expect("concurrent solve"),
                        expected
                    );
                }
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("worker does not panic");
    }
}
