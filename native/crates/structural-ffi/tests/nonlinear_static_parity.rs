use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearStaticCaseV3,
};
use structural_ffi::Api;
use structural_ffi_sys::{
    SA_ERR_INVALID_ARGUMENT, SA_ERR_NONCONVERGENCE, SA_EXECUTION_BACKEND_CPU,
};
use structural_runtime_ffi::{
    phase1_rust_nonlinear_frame_solve, NlFrameSolveConfig, NlFrameSolveResult,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn golden_case() -> NonlinearStaticCaseV3 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json"),
    )
    .expect("tracked neutral fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict nonlinear static fixture") {
        LegacyRuntimeCaseV3::NonlinearStatic(case) => case,
        _ => panic!("nonlinear static fixture decoded as another family"),
    }
}

fn legacy_config(case: &NonlinearStaticCaseV3) -> NlFrameSolveConfig {
    NlFrameSolveConfig {
        story_count: case.config.story_count,
        tolerance: case.config.tolerance,
        max_iter: case.config.max_iter,
        hardening_ratio: case.config.hardening_ratio,
        line_search_decay: case.config.line_search_decay,
        line_search_min: case.config.line_search_min,
        pdelta_factor: case.config.pdelta_factor,
    }
}

fn assert_close(actual: f64, expected: f64) {
    assert!(
        (actual - expected).abs() <= 1.0e-15,
        "expected {expected:.17e}, received {actual:.17e}"
    );
}

#[test]
fn safe_v1_3_cpp_path_matches_the_frozen_legacy_rust_case() {
    let case = golden_case();
    let api = Api::load_nonlinear_static().expect("ABI v1.3 nonlinear static table");
    let cpp = api
        .solve_nonlinear_static(&case.config, &case.inputs)
        .expect("C++ nonlinear static CPU solve");

    let count = usize::try_from(case.config.story_count).expect("story count");
    let mut legacy_displacement = vec![0.0_f64; count];
    let mut legacy_result = NlFrameSolveResult {
        converged: 0,
        iterations: 0,
        residual_inf: 0.0,
        residual_l2: 0.0,
        max_abs_displacement_m: 0.0,
        top_displacement_m: 0.0,
        base_shear_kn: 0.0,
        plastic_story_count: 0,
        line_search_backtracks: 0,
        status_code: i32::MIN,
    };
    let legacy_status = phase1_rust_nonlinear_frame_solve(
        &legacy_config(&case),
        case.inputs.story_k_n_per_m.as_ptr(),
        case.inputs.story_h_m.as_ptr(),
        case.inputs.story_axial_n.as_ptr(),
        case.inputs.story_yield_drift_m.as_ptr(),
        case.inputs.floor_load_n.as_ptr(),
        legacy_displacement.as_mut_ptr(),
        case.config.story_count,
        &mut legacy_result,
    );

    assert_eq!(legacy_status, 0);
    assert_eq!(legacy_result.status_code, 0);
    assert_eq!(legacy_result.converged, 1);
    assert_eq!(cpp.iterations, legacy_result.iterations);
    assert_eq!(cpp.iterations, case.result.iterations);
    assert_eq!(cpp.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(cpp.fallback_count, 0);
    assert_eq!(cpp.plastic_story_count, legacy_result.plastic_story_count);
    assert_eq!(cpp.plastic_story_count, case.result.plastic_story_count);
    assert_eq!(
        cpp.line_search_backtracks,
        legacy_result.line_search_backtracks
    );
    assert_eq!(
        cpp.line_search_backtracks,
        case.result.line_search_backtracks
    );
    for (cpp_value, legacy_value, golden_value) in cpp
        .displacement_m
        .iter()
        .zip(&legacy_displacement)
        .zip(&case.result.u_story_m)
        .map(|((cpp_value, legacy_value), golden_value)| (cpp_value, legacy_value, golden_value))
    {
        assert_close(*cpp_value, *legacy_value);
        assert_close(*cpp_value, *golden_value);
    }
    for (cpp_value, legacy_value, golden_value) in [
        (
            cpp.residual_inf,
            legacy_result.residual_inf,
            case.result.residual_inf,
        ),
        (
            cpp.residual_l2,
            legacy_result.residual_l2,
            case.result.residual_l2,
        ),
        (
            cpp.max_abs_displacement_m,
            legacy_result.max_abs_displacement_m,
            case.result.max_abs_displacement_m,
        ),
        (
            cpp.top_displacement_m,
            legacy_result.top_displacement_m,
            case.result.top_displacement_m,
        ),
        (
            cpp.base_shear_kn,
            legacy_result.base_shear_kn,
            case.result.base_shear_kn,
        ),
    ] {
        assert_close(cpp_value, legacy_value);
        assert_close(cpp_value, golden_value);
    }
}

#[test]
fn safe_wrapper_preserves_error_taxonomy_without_partial_results() {
    let case = golden_case();
    let api = Api::load_nonlinear_static().expect("ABI v1.3 nonlinear static table");

    let mut invalid = case.config.clone();
    invalid.hardening_ratio = 2.0;
    let error = api
        .solve_nonlinear_static(&invalid, &case.inputs)
        .expect_err("invalid hardening ratio");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut invalid_inputs = case.inputs.clone();
    invalid_inputs.story_k_n_per_m[1] = f64::NAN;
    let error = api
        .solve_nonlinear_static(&case.config, &invalid_inputs)
        .expect_err("non-finite stiffness");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut mismatched = case.inputs.clone();
    mismatched.floor_load_n.pop();
    let error = api
        .solve_nonlinear_static(&case.config, &mismatched)
        .expect_err("mismatched input length");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut nonconverged = case.config.clone();
    nonconverged.max_iter = 1;
    let error = api
        .solve_nonlinear_static(&nonconverged, &case.inputs)
        .expect_err("bounded Newton nonconvergence");
    assert_eq!(error.code, SA_ERR_NONCONVERGENCE);
}

#[test]
fn nonlinear_static_cpu_operation_is_reentrant_and_deterministic() {
    let case = Arc::new(golden_case());
    let expected = Api::load_nonlinear_static()
        .expect("ABI v1.3 nonlinear static table")
        .solve_nonlinear_static(&case.config, &case.inputs)
        .expect("reference solve");
    let workers: Vec<_> = (0..8)
        .map(|_| {
            let case = Arc::clone(&case);
            let expected = expected.clone();
            thread::spawn(move || {
                let api = Api::load_nonlinear_static().expect("thread-local table copy");
                for _ in 0..64 {
                    assert_eq!(
                        api.solve_nonlinear_static(&case.config, &case.inputs)
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
