use structural_contracts::legacy_runtime::{NonlinearStaticConfigV3, StaticStoryInputsV3};
use structural_contracts::product_ir::{sha256_identity, ResultIdentityV1};
use structural_contracts::static_product::{
    build_nonlinear_static_report_ir_v1, build_nonlinear_static_request_v1,
    build_nonlinear_static_result_ir_v1, nonlinear_static_execution_hash_v1,
    nonlinear_static_model_hash_v1, parse_nonlinear_static_report_ir_v1,
    parse_nonlinear_static_request_v1, parse_nonlinear_static_result_ir_v1,
    NonlinearStaticAnalysisRequestV1, NonlinearStaticBackendV1, NonlinearStaticResultSummaryV1,
};

fn request_value() -> NonlinearStaticAnalysisRequestV1 {
    NonlinearStaticAnalysisRequestV1 {
        schema_version: "structural-nonlinear-static-request.v1".to_owned(),
        operation: "solve_nonlinear_static_newton".to_owned(),
        case_id: "static-contract-c4".to_owned(),
        backend: NonlinearStaticBackendV1::Cpu,
        config: NonlinearStaticConfigV3 {
            story_count: 1,
            tolerance: 1.0e-12,
            max_iter: 20,
            hardening_ratio: 0.05,
            line_search_decay: 0.5,
            line_search_min: 0.03125,
            pdelta_factor: 0.0,
        },
        inputs: StaticStoryInputsV3 {
            story_k_n_per_m: vec![10.0],
            story_h_m: vec![3.0],
            story_axial_n: vec![0.0],
            story_yield_drift_m: vec![1.0],
            floor_load_n: vec![5.0],
        },
    }
}

#[test]
fn request_result_and_report_are_canonical_self_hashed_and_bound() {
    let request = build_nonlinear_static_request_v1(request_value()).expect("typed request");
    assert_eq!(
        parse_nonlinear_static_request_v1(request.canonical_bytes())
            .expect("strict request")
            .request_hash(),
        request.request_hash()
    );
    let identity = ResultIdentityV1 {
        request_hash: request.request_hash().to_owned(),
        model_hash: nonlinear_static_model_hash_v1(&request).expect("model hash"),
        state_hash: sha256_identity(b"state"),
        execution_hash: nonlinear_static_execution_hash_v1(&request).expect("execution hash"),
        checkpoint_hash: sha256_identity(b"checkpoint"),
    };
    let result = build_nonlinear_static_result_ir_v1(
        &request,
        identity,
        NonlinearStaticResultSummaryV1 {
            story_count: 1,
            iterations: 2,
            residual_inf: 0.0,
            residual_l2: 0.0,
            max_abs_displacement_m: 0.5,
            top_displacement_m: 0.5,
            base_shear_kn: 0.005,
            plastic_story_count: 0,
            line_search_backtracks: 0,
        },
        vec![0.5],
    )
    .expect("bound ResultIR");
    let parsed_result = parse_nonlinear_static_result_ir_v1(result.canonical_bytes())
        .expect("self-verified ResultIR");
    assert_eq!(parsed_result.result_hash(), result.result_hash());
    let report = build_nonlinear_static_report_ir_v1(&result, b"deterministic document")
        .expect("bound ReportIR");
    let parsed_report = parse_nonlinear_static_report_ir_v1(report.canonical_json().as_bytes())
        .expect("self-verified ReportIR");
    assert_eq!(parsed_report.report_hash(), report.report_hash());
    assert_eq!(
        parsed_report.report().source_result_hash,
        result.result_hash()
    );
}

#[test]
fn duplicate_unknown_nonfinite_dimension_and_recovery_drift_fail_closed() {
    let duplicate = br#"{
        "schema_version":"structural-nonlinear-static-request.v1",
        "schema_version":"structural-nonlinear-static-request.v1"
    }"#;
    assert!(parse_nonlinear_static_request_v1(duplicate).is_err());

    let mut unknown = serde_json::to_value(request_value()).expect("request value");
    unknown["unexpected"] = serde_json::json!(true);
    assert!(parse_nonlinear_static_request_v1(
        &serde_json::to_vec(&unknown).expect("unknown request")
    )
    .is_err());

    let mut invalid = request_value();
    invalid.inputs.story_h_m.pop();
    assert!(build_nonlinear_static_request_v1(invalid).is_err());

    let mut invalid = request_value();
    invalid.config.tolerance = f64::NAN;
    assert!(build_nonlinear_static_request_v1(invalid).is_err());

    let request = build_nonlinear_static_request_v1(request_value()).expect("request");
    let identity = ResultIdentityV1 {
        request_hash: request.request_hash().to_owned(),
        model_hash: nonlinear_static_model_hash_v1(&request).expect("model hash"),
        state_hash: sha256_identity(b"state"),
        execution_hash: nonlinear_static_execution_hash_v1(&request).expect("execution hash"),
        checkpoint_hash: sha256_identity(b"checkpoint"),
    };
    let error = build_nonlinear_static_result_ir_v1(
        &request,
        identity,
        NonlinearStaticResultSummaryV1 {
            story_count: 1,
            iterations: 2,
            residual_inf: f64::from_bits(1),
            residual_l2: 0.0,
            max_abs_displacement_m: 0.5,
            top_displacement_m: 0.5,
            base_shear_kn: 0.005,
            plastic_story_count: 0,
            line_search_backtracks: 0,
        },
        vec![0.5],
    )
    .expect_err("one-bit recovery drift");
    assert_eq!(error.code, "static_result_recovery_invalid");
}
