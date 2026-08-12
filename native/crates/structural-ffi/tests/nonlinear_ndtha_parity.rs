use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NdthaResponseV3, NonlinearNdthaCaseV3,
};
use structural_contracts::solver_cpu::{
    parse_nonlinear_ndtha_cpu_case_v1, ExecutionBackendV1, NonlinearNdthaCpuCaseV1,
    NonlinearNdthaCpuResultV1,
};
use structural_ffi::{Api, NonlinearNdthaSolution};
use structural_ffi_sys::{
    SA_ERR_INVALID_ARGUMENT, SA_ERR_NONCONVERGENCE, SA_EXECUTION_BACKEND_CPU,
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

fn product_cases() -> Vec<NonlinearNdthaCpuCaseV1> {
    const FIXTURES: [&str; 5] = [
        "nonlinear_ndtha_one_story_elastic_python_c1.json",
        "nonlinear_ndtha_elastic_pdelta_python_c1.json",
        "nonlinear_ndtha_plastic_backtrack_python_c1.json",
        "nonlinear_ndtha_adaptive_retry_python_c1.json",
        "nonlinear_ndtha_collapse_python_c1.json",
    ];
    FIXTURES
        .iter()
        .map(|name| {
            let bytes = std::fs::read(
                repository_root()
                    .join("native/tests/fixtures/solver_cpu")
                    .join(name),
            )
            .expect("tracked Python C1 fixture");
            parse_nonlinear_ndtha_cpu_case_v1(&bytes)
                .unwrap_or_else(|error| panic!("{name}: {error}"))
        })
        .collect()
}

fn assert_close(actual: f64, expected: f64) {
    assert!(
        (actual - expected).abs() <= 1.0e-15,
        "expected {expected:.17e}, received {actual:.17e}"
    );
}

fn assert_tolerance(label: &str, actual: f64, expected: f64, absolute: f64) {
    assert!(
        (actual - expected).abs() <= absolute,
        "{label}: expected {expected:.17e}, received {actual:.17e}, tolerance {absolute:.1e}"
    );
}

fn assert_vector_tolerance(label: &str, actual: &[f64], expected: &[f64], absolute: f64) {
    assert_eq!(actual.len(), expected.len(), "{label} length");
    for (index, (actual, expected)) in actual.iter().zip(expected).enumerate() {
        assert_tolerance(&format!("{label}[{index}]"), *actual, *expected, absolute);
    }
}

fn assert_product_summary(actual: &NonlinearNdthaSolution, expected: &NonlinearNdthaCpuResultV1) {
    assert_eq!(expected.execution_backend, ExecutionBackendV1::Cpu);
    assert_eq!(actual.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(expected.fallback_count, 0);
    assert_eq!(actual.fallback_count, expected.fallback_count);
    assert_eq!(actual.converged_all_steps, expected.converged_all_steps);
    assert_eq!(actual.collapsed, expected.collapsed);
    assert_eq!(actual.collapse_step, expected.collapse_step);
    assert_eq!(actual.step_count_completed, expected.step_count_completed);
    assert_eq!(
        actual.max_plastic_story_count,
        expected.max_plastic_story_count
    );
    assert_eq!(
        actual.total_line_search_backtracks,
        expected.total_line_search_backtracks
    );
    for (label, actual_value, expected_value, tolerance) in [
        (
            "collapse_time_s",
            actual.collapse_time_s,
            expected.collapse_time_s,
            1.0e-15,
        ),
        (
            "collapse_drift_ratio_pct",
            actual.collapse_drift_ratio_pct,
            expected.collapse_drift_ratio_pct,
            1.0e-10,
        ),
        (
            "collapse_top_displacement_m",
            actual.collapse_top_displacement_m,
            expected.collapse_top_displacement_m,
            1.0e-12,
        ),
        (
            "max_drift_ratio_pct",
            actual.max_drift_ratio_pct,
            expected.max_drift_ratio_pct,
            1.0e-10,
        ),
        (
            "avg_step_iterations",
            actual.avg_step_iterations,
            expected.avg_step_iterations,
            1.0e-15,
        ),
        (
            "residual_top_displacement_m",
            actual.residual_top_displacement_m,
            expected.residual_top_displacement_m,
            1.0e-12,
        ),
        (
            "residual_drift_ratio_pct",
            actual.residual_drift_ratio_pct,
            expected.residual_drift_ratio_pct,
            1.0e-10,
        ),
    ] {
        assert_tolerance(label, actual_value, expected_value, tolerance);
    }
}

fn assert_product_response(actual: &NonlinearNdthaSolution, expected: &NdthaResponseV3) {
    assert_eq!(actual.response.step_converged, expected.step_converged);
    assert_eq!(actual.response.step_iterations, expected.step_iterations);
    assert_eq!(
        actual.response.step_plastic_story_count,
        expected.step_plastic_story_count
    );
    assert_vector_tolerance(
        "top_displacement_m",
        &actual.response.top_displacement_m,
        &expected.top_displacement_m,
        1.0e-12,
    );
    for (label, actual_values, expected_values) in [
        (
            "drift_ratio_pct",
            &actual.response.drift_ratio_pct,
            &expected.drift_ratio_pct,
        ),
        (
            "core_drift_pct",
            &actual.response.core_drift_pct,
            &expected.core_drift_pct,
        ),
        (
            "story_drift_envelope_pct",
            &actual.response.story_drift_envelope_pct,
            &expected.story_drift_envelope_pct,
        ),
        (
            "final_story_drift_pct",
            &actual.response.final_story_drift_pct,
            &expected.final_story_drift_pct,
        ),
    ] {
        assert_vector_tolerance(label, actual_values, expected_values, 1.0e-10);
    }
    for (label, actual_values, expected_values) in [
        (
            "base_shear_kn",
            &actual.response.base_shear_kn,
            &expected.base_shear_kn,
        ),
        (
            "core_shear_kn",
            &actual.response.core_shear_kn,
            &expected.core_shear_kn,
        ),
    ] {
        assert_vector_tolerance(label, actual_values, expected_values, 1.0e-8);
    }
    assert_vector_tolerance(
        "step_residual_inf",
        &actual.response.step_residual_inf,
        &expected.step_residual_inf,
        1.0e-6,
    );
}

fn assert_matches_frozen_legacy(cpp: &NonlinearNdthaSolution, case: &NonlinearNdthaCaseV3) {
    let legacy = &case.result;
    assert_eq!(legacy.status_code, 0);
    assert!(legacy.converged_all_steps);
    assert!(legacy.rust_backend_all_steps);
    assert_eq!(cpp.converged_all_steps, legacy.converged_all_steps);
    assert_eq!(cpp.collapsed, legacy.collapsed);
    assert_eq!(cpp.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(cpp.fallback_count, 0);
    assert_eq!(cpp.collapse_step, legacy.collapse_step);
    assert_eq!(cpp.step_count_completed, legacy.step_count_completed);
    assert_eq!(cpp.max_plastic_story_count, legacy.max_plastic_story_count);
    for (actual, expected) in [
        (cpp.collapse_time_s, legacy.collapse_time_s),
        (
            cpp.collapse_drift_ratio_pct,
            legacy.collapse_drift_ratio_pct,
        ),
        (
            cpp.collapse_top_displacement_m,
            legacy.collapse_top_displacement_m,
        ),
        (cpp.max_drift_ratio_pct, legacy.max_drift_ratio_pct),
        (cpp.avg_step_iterations, legacy.avg_step_iterations),
        (
            cpp.residual_top_displacement_m,
            legacy.residual_top_displacement_m,
        ),
        (
            cpp.residual_drift_ratio_pct,
            legacy.residual_drift_ratio_pct,
        ),
    ] {
        assert_close(actual, expected);
    }
    assert_product_response(cpp, &legacy.response);
}

#[test]
fn safe_v1_4_cpp_path_matches_the_complete_frozen_legacy_rust_result() {
    let case = golden_case();
    let api = Api::load_nonlinear_ndtha().expect("ABI v1.4 nonlinear NDTHA table");
    let cpp = api
        .solve_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("C++ nonlinear NDTHA CPU solve");
    assert_matches_frozen_legacy(&cpp, &case);

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
fn safe_v1_4_cpp_path_matches_the_complete_python_c1_matrix() {
    let api = Api::load_nonlinear_ndtha().expect("ABI v1.4 nonlinear NDTHA table");
    for case in product_cases() {
        let cpp = api
            .solve_nonlinear_ndtha(&case.config, &case.inputs)
            .expect("C++ nonlinear NDTHA CPU solve");
        assert_product_summary(&cpp, &case.result);
        assert_product_response(&cpp, &case.result.response);
    }
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
