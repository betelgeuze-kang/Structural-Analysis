use std::path::{Path, PathBuf};

use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::product_ir::parse_native_analysis_request_v1;
use structural_ffi::{Api, ModelIrNdthaAdapterRequest};
use structural_ffi_sys::{
    SA_ABI_V1_6, SA_CAPABILITY_MODEL_IR_NDTHA_ADAPTER, SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED,
    SA_EXECUTION_BACKEND_CPU,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn load_model() -> structural_contracts::model_ir::ModelIrV2Document {
    let bytes = std::fs::read(
        repository_root()
            .join("native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json"),
    )
    .expect("adapter ModelIR fixture");
    parse_model_ir_v2(&bytes).expect("strict adapter ModelIR fixture")
}

fn load_golden_request() -> structural_contracts::product_ir::NativeAnalysisRequestV1 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
    )
    .expect("golden product request");
    parse_native_analysis_request_v1(&bytes)
        .expect("strict golden product request")
        .request()
        .clone()
}

fn adapter_request() -> ModelIrNdthaAdapterRequest {
    let golden = load_golden_request();
    ModelIrNdthaAdapterRequest {
        element_id: "COLUMN".to_owned(),
        base_node_id: "BASE".to_owned(),
        floor_node_id: "FLOOR".to_owned(),
        load_pattern_id: "PUSH_X".to_owned(),
        damping_ratio: 0.00025,
        elastic_guard_yield_drift_m: 0.01,
        config: golden.config,
        acceleration_g: golden.inputs.ag_g,
    }
}

fn assert_close(actual: f64, expected: f64) {
    let tolerance = expected.abs().max(1.0) * 1.0e-12;
    assert!(
        (actual - expected).abs() <= tolerance,
        "actual {actual:?}, expected {expected:?}, tolerance {tolerance:?}"
    );
}

fn assert_vectors_close(actual: &[f64], expected: &[f64]) {
    assert_eq!(actual.len(), expected.len());
    for (actual, expected) in actual.iter().zip(expected) {
        assert_close(*actual, *expected);
    }
}

#[test]
fn safe_v1_6_adapter_matches_closed_form_and_golden_product_inputs() {
    let api = Api::load_model_ir_ndtha_adapter().expect("ABI v1.6 adapter table");
    assert_eq!(api.abi_version(), SA_ABI_V1_6);
    assert_ne!(api.capabilities() & SA_CAPABILITY_MODEL_IR_NDTHA_ADAPTER, 0);
    let model = api.create_model_ir(&load_model()).expect("native ModelIR");
    let request = adapter_request();
    let adapted = model
        .adapt_nonlinear_ndtha(&request)
        .expect("bounded native reduction");

    let expected = load_golden_request();
    assert_close(adapted.inputs.story_k_n_per_m[0], 50_000_000.0);
    assert_close(adapted.inputs.story_h_m[0], 3.2);
    assert_eq!(adapted.inputs.story_axial_n, [0.0]);
    assert_eq!(adapted.inputs.story_yield_drift_m, [0.01]);
    assert_close(adapted.inputs.story_mass_kg[0], 5000.0);
    assert_close(adapted.inputs.story_damping_n_s_per_m[0], 250.0);
    assert_eq!(adapted.inputs.floor_load_base_n, [200_000.0]);
    assert_eq!(adapted.inputs.ag_g, expected.inputs.ag_g);
    assert_close(
        adapted.receipt.story_stiffness_n_per_m,
        12.0 * 200_000_000_000.0 * adapted.receipt.section_iy_m4 / 3.2_f64.powi(3),
    );
    assert_close(adapted.receipt.story_mass_kg, 0.5 * 2500.0 * 1.25 * 3.2);
    assert_close(
        adapted.receipt.story_damping_n_s_per_m,
        2.0 * 0.00025
            * (adapted.receipt.story_stiffness_n_per_m * adapted.receipt.story_mass_kg).sqrt(),
    );
    assert_eq!(adapted.receipt.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(adapted.receipt.fallback_count, 0);

    let adapted_solution = api
        .solve_nonlinear_ndtha(&adapted.config, &adapted.inputs)
        .expect("adapter-fed native solve");
    let golden_solution = api
        .solve_nonlinear_ndtha(&expected.config, &expected.inputs)
        .expect("golden-input native solve");
    assert!(adapted_solution.converged_all_steps);
    assert!(!adapted_solution.collapsed);
    assert_eq!(adapted_solution.max_plastic_story_count, 0);
    assert!(adapted_solution
        .response
        .step_plastic_story_count
        .iter()
        .all(|count| *count == 0));
    assert_eq!(adapted_solution.fallback_count, 0);
    assert_vectors_close(
        &adapted_solution.response.top_displacement_m,
        &golden_solution.response.top_displacement_m,
    );
    assert_vectors_close(
        &adapted_solution.response.drift_ratio_pct,
        &golden_solution.response.drift_ratio_pct,
    );
    assert_vectors_close(
        &adapted_solution.response.base_shear_kn,
        &golden_solution.response.base_shear_kn,
    );
}

#[test]
fn adapter_rejects_bad_selectors_and_is_not_exposed_by_v1_1() {
    let document = load_model();
    let legacy_api = Api::load_model_ir().expect("ABI v1.1 ModelIR table");
    let legacy_model = legacy_api
        .create_model_ir(&document)
        .expect("legacy native ModelIR");
    let unsupported = legacy_model
        .adapt_nonlinear_ndtha(&adapter_request())
        .expect_err("v1.1 does not expose adapter");
    assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

    let api = Api::load_model_ir_ndtha_adapter().expect("ABI v1.6 adapter table");
    let model = api.create_model_ir(&document).expect("v1.6 native ModelIR");
    let mut invalid = adapter_request();
    invalid.floor_node_id = "missing/node".to_owned();
    let rejected = model
        .adapt_nonlinear_ndtha(&invalid)
        .expect_err("invalid stable selector is rejected");
    assert_eq!(rejected.code, SA_ERR_INVALID_ARGUMENT);

    model
        .adapt_nonlinear_ndtha(&adapter_request())
        .expect("failed call did not mutate immutable model");
}
