use std::path::{Path, PathBuf};
use std::thread;

use structural_contracts::legacy_runtime::{parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3};
use structural_ffi::Api;
use structural_ffi_sys::{
    SA_ERR_INVALID_ARGUMENT, SA_ERR_NONCONVERGENCE, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
    SA_TRACK_POINT_LOAD_MAX_NODE_COUNT,
};

const PRODUCT_GOLDENS: [&str; 4] = [
    "native/tests/fixtures/solver_cpu/track_point_load_python_c1.json",
    "native/tests/fixtures/solver_cpu/track_point_load_pinned_timoshenko_python_c1.json",
    "native/tests/fixtures/solver_cpu/track_point_load_fixed_euler_python_c1.json",
    "native/tests/fixtures/solver_cpu/track_point_load_fixed_timoshenko_python_c1.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn track_case(relative_path: &str) -> structural_contracts::legacy_runtime::TrackCaseV3 {
    let bytes =
        std::fs::read(repository_root().join(relative_path)).expect("tracked neutral fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict track fixture") {
        LegacyRuntimeCaseV3::Track(case) => case,
        _ => panic!("track fixture decoded as another family"),
    }
}

fn product_golden_case() -> structural_contracts::legacy_runtime::TrackCaseV3 {
    track_case(PRODUCT_GOLDENS[0])
}

fn legacy_golden_case() -> structural_contracts::legacy_runtime::TrackCaseV3 {
    track_case("native/tests/fixtures/legacy_runtime_v3/track_point_load.json")
}

fn assert_close(actual: f64, expected: f64) {
    assert!(
        (actual - expected).abs() <= 1.0e-15,
        "{actual:.17e} differs from {expected:.17e}"
    );
}

fn assert_cpp_matches_product_case(
    api: Api,
    case: &structural_contracts::legacy_runtime::TrackCaseV3,
) {
    let cpp = api
        .solve_track_point_load(&case.config)
        .expect("C++ CPU solve");
    assert_eq!(cpp.iterations, case.result.iterations);
    assert_eq!(cpp.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(cpp.fallback_count, 0);
    assert_close(cpp.residual_inf, case.result.residual_inf);
    assert_close(
        cpp.max_abs_displacement_m,
        case.result.max_abs_displacement_m,
    );
    assert_close(cpp.mid_displacement_m, case.result.mid_displacement_m);
    assert_eq!(cpp.displacement_m.len(), case.result.displacement_m.len());
    assert_eq!(cpp.rotation_rad.len(), case.result.rotation_rad.len());
    for (actual, expected) in cpp.displacement_m.iter().zip(&case.result.displacement_m) {
        assert_close(*actual, *expected);
    }
    for (actual, expected) in cpp.rotation_rad.iter().zip(&case.result.rotation_rad) {
        assert_close(*actual, *expected);
    }
}

#[test]
fn safe_v1_2_cpp_path_matches_the_complete_python_c1_support_theory_matrix() {
    let api = Api::load_track_point_load().expect("ABI v1.2 track table");
    for relative_path in PRODUCT_GOLDENS {
        let case = track_case(relative_path);
        assert_cpp_matches_product_case(api, &case);
    }
}

#[test]
fn safe_v1_2_cpp_path_matches_python_c1_and_the_frozen_neutral_legacy_boundary() {
    let case = product_golden_case();
    let legacy_case = legacy_golden_case();
    assert_eq!(case.config, legacy_case.config);
    let api = Api::load_track_point_load().expect("ABI v1.2 track table");
    let cpp = api
        .solve_track_point_load(&case.config)
        .expect("C++ CPU solve");

    assert_eq!(cpp.iterations, case.result.iterations);
    assert_eq!(cpp.iterations, legacy_case.result.iterations);
    assert_eq!(cpp.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(cpp.fallback_count, 0);
    assert_close(cpp.residual_inf, case.result.residual_inf);
    assert_close(cpp.residual_inf, legacy_case.result.residual_inf);
    assert_close(
        cpp.max_abs_displacement_m,
        legacy_case.result.max_abs_displacement_m,
    );
    assert_close(
        cpp.mid_displacement_m,
        legacy_case.result.mid_displacement_m,
    );
    for ((cpp_value, golden_value), legacy_value) in cpp
        .displacement_m
        .iter()
        .zip(&case.result.displacement_m)
        .zip(&legacy_case.result.displacement_m)
    {
        assert_close(*cpp_value, *golden_value);
        assert_close(*cpp_value, *legacy_value);
    }
    for (index, ((cpp_value, golden_value), legacy_value)) in cpp
        .rotation_rad
        .iter()
        .zip(&case.result.rotation_rad)
        .zip(&legacy_case.result.rotation_rad)
        .enumerate()
    {
        assert_close(*cpp_value, *golden_value);
        if index == 0 || index + 1 == cpp.rotation_rad.len() {
            assert_close((*cpp_value - *legacy_value).abs(), 3.436_580_346_133_486e-5);
        } else {
            assert_close(*cpp_value, *legacy_value);
        }
    }
}

#[test]
fn safe_wrapper_preserves_error_taxonomy_without_hidden_fallback() {
    let case = product_golden_case();
    let api = Api::load_track_point_load().expect("ABI v1.2 track table");

    let mut invalid = case.config.clone();
    invalid.length_m = f64::NAN;
    let error = api
        .solve_track_point_load(&invalid)
        .expect_err("non-finite input");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut oversized = case.config.clone();
    oversized.node_count = SA_TRACK_POINT_LOAD_MAX_NODE_COUNT + 1;
    let error = api
        .solve_track_point_load(&oversized)
        .expect_err("bounded node count");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut nonconverged = case.config.clone();
    nonconverged.cg_max_iter = 1;
    let error = api
        .solve_track_point_load(&nonconverged)
        .expect_err("bounded nonconvergence");
    assert_eq!(error.code, SA_ERR_NONCONVERGENCE);

    let older = Api::load_model_ir().expect("ABI v1.1 table");
    let error = older
        .solve_track_point_load(&case.config)
        .expect_err("v1.1 has no track slot");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}

#[test]
fn track_cpu_operation_is_reentrant_and_deterministic() {
    let config = product_golden_case().config;
    let expected = Api::load_track_point_load()
        .expect("ABI v1.2 track table")
        .solve_track_point_load(&config)
        .expect("reference solve");
    let workers = (0..8)
        .map(|_| {
            let config = config.clone();
            let expected = expected.clone();
            thread::spawn(move || {
                let api = Api::load_track_point_load().expect("thread-local table copy");
                for _ in 0..64 {
                    assert_eq!(
                        api.solve_track_point_load(&config).expect("parallel solve"),
                        expected
                    );
                }
            })
        })
        .collect::<Vec<_>>();
    for worker in workers {
        worker.join().expect("track worker does not panic");
    }
}
