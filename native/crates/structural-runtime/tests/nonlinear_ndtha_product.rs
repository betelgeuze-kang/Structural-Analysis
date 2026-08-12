use std::path::{Path, PathBuf};

use structural_contracts::product_ir::{
    parse_native_analysis_request_v1, parse_nonlinear_ndtha_result_ir_v1,
};
use structural_contracts::solver_cpu::parse_nonlinear_ndtha_cpu_case_v1;
use structural_runtime::Runtime;

fn assert_fp64_bits_equal(left: &[f64], right: &[f64]) {
    assert_eq!(left.len(), right.len());
    for (left, right) in left.iter().zip(right) {
        assert_eq!(left.to_bits(), right.to_bits());
    }
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

#[test]
fn terminal_cpp_state_becomes_hash_bound_result_ir_without_recovery_drift() {
    let root = repository_root();
    let request = parse_native_analysis_request_v1(
        &std::fs::read(root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"))
            .expect("tracked request"),
    )
    .expect("strict request");
    let golden = parse_nonlinear_ndtha_cpu_case_v1(
        &std::fs::read(root.join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ))
        .expect("tracked Python C1 golden"),
    )
    .expect("strict Python C1 golden");
    let runtime = Runtime::new().expect("native runtime");
    let mut state = runtime
        .begin_nonlinear_ndtha(&request.request().config, &request.request().inputs)
        .expect("initial native state");
    runtime
        .advance_nonlinear_ndtha(
            &request.request().config,
            &request.request().inputs,
            u32::MAX,
            &mut state,
        )
        .expect("terminal native execution");
    let product = runtime
        .finish_nonlinear_ndtha_product(&request, &state)
        .expect("terminal ResultIR");
    let parsed = parse_nonlinear_ndtha_result_ir_v1(product.result_ir.canonical_bytes())
        .expect("self-validating ResultIR");
    assert_eq!(
        parsed.canonical_bytes(),
        product.result_ir.canonical_bytes()
    );
    let response = &parsed.result().response;
    let native = &state.response;
    assert_fp64_bits_equal(&response.top_displacement_m, &native.top_displacement_m);
    assert_fp64_bits_equal(&response.drift_ratio_pct, &native.drift_ratio_pct);
    assert_fp64_bits_equal(&response.base_shear_kn, &native.base_shear_kn);
    assert_fp64_bits_equal(&response.core_drift_pct, &native.core_drift_pct);
    assert_fp64_bits_equal(&response.core_shear_kn, &native.core_shear_kn);
    assert_fp64_bits_equal(&response.step_residual_inf, &native.step_residual_inf);
    assert_fp64_bits_equal(
        &response.story_drift_envelope_pct,
        &native.story_drift_envelope_pct,
    );
    assert_fp64_bits_equal(
        &response.final_story_drift_pct,
        &native.final_story_drift_pct,
    );
    assert_eq!(response.step_converged, native.step_converged);
    assert_eq!(response.step_iterations, native.step_iterations);
    assert_eq!(
        response.step_plastic_story_count,
        native.step_plastic_story_count
    );
    assert!(
        (parsed.result().summary.max_drift_ratio_pct - golden.result.max_drift_ratio_pct).abs()
            <= 1.0e-10
    );
    assert!(
        (parsed.result().summary.residual_top_displacement_m
            - golden.result.residual_top_displacement_m)
            .abs()
            <= 1.0e-12
    );
    assert_eq!(parsed.result().backend_receipt.fallback_count, 0);
    assert_eq!(
        parsed.result().identity.checkpoint_hash,
        product.checkpoint.receipt().checkpoint_hash
    );
}

#[test]
fn active_state_cannot_be_promoted_to_result_ir() {
    let root = repository_root();
    let request = parse_native_analysis_request_v1(
        &std::fs::read(root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"))
            .expect("tracked request"),
    )
    .expect("strict request");
    let runtime = Runtime::new().expect("native runtime");
    let state = runtime
        .begin_nonlinear_ndtha(&request.request().config, &request.request().inputs)
        .expect("active state");
    let error = runtime
        .finish_nonlinear_ndtha_product(&request, &state)
        .expect_err("active state is not a product result");
    assert_eq!(error.code, 1300);
}
