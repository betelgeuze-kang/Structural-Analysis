use structural_contracts::product_ir::ResultIdentityV1;
use structural_contracts::spectral_product::{
    build_dense_spectral_report_ir_v1, build_dense_spectral_request_v1,
    build_dense_spectral_result_ir_v1, dense_spectral_execution_hash_v1,
    dense_spectral_model_hash_v1, parse_dense_spectral_report_ir_v1,
    parse_dense_spectral_result_ir_v1, DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1,
    SpectralBackendV1, SpectralGeneralizedEigenConfigV1, SpectralModeV1, SpectralResultSummaryV1,
    DENSE_SPECTRAL_REQUEST_V1,
};

fn request() -> structural_contracts::spectral_product::DenseSpectralAnalysisRequestDocumentV1 {
    build_dense_spectral_request_v1(DenseSpectralAnalysisRequestV1 {
        schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
        operation: "solve_dense_generalized_eigen".to_owned(),
        case_id: "modal-wire".to_owned(),
        analysis_kind: SpectralAnalysisKindV1::Modal,
        backend: SpectralBackendV1::Cpu,
        order: 2,
        stiffness: vec![4.0, 0.0, 0.0, 9.0],
        secondary_matrix: vec![1.0, 0.0, 0.0, 1.0],
        coordinate_recovery_scale: Vec::new(),
        config: SpectralGeneralizedEigenConfigV1 {
            mode_count: 2,
            maximum_sweeps: 128,
            symmetry_relative_tolerance: 1.0e-12,
            positive_semidefinite_relative_tolerance: 1.0e-12,
            mode_relative_tolerance: 1.0e-12,
            cluster_relative_tolerance: 1.0e-10,
            residual_relative_tolerance: 1.0e-10,
            orthogonality_tolerance: 1.0e-10,
            eigensolver_relative_tolerance: 1.0e-14,
        },
    })
    .expect("valid modal request")
}

fn valid_identity(
    request: &structural_contracts::spectral_product::DenseSpectralAnalysisRequestDocumentV1,
) -> ResultIdentityV1 {
    ResultIdentityV1 {
        request_hash: request.request_hash().to_owned(),
        model_hash: dense_spectral_model_hash_v1(request).expect("model identity"),
        state_hash: format!("sha256:{}", "1".repeat(64)),
        execution_hash: dense_spectral_execution_hash_v1(request).expect("execution identity"),
        checkpoint_hash: format!("sha256:{}", "2".repeat(64)),
    }
}

fn result() -> structural_contracts::spectral_product::DenseSpectralResultIrDocumentV1 {
    let request = request();
    build_dense_spectral_result_ir_v1(
        &request,
        valid_identity(&request),
        SpectralResultSummaryV1 {
            mode_count: 2,
            rigid_mode_count: 0,
            finite_positive_eigenvalue_count: 0,
            geometric_stiffness_positive_rank: 0,
            eigensolver_sweeps: 1,
            critical_load_factor: None,
            metric_orthogonality_error_inf: 0.0,
            operator_diagonalization_error_inf: 0.0,
            stiffness_relative_symmetry_error: 0.0,
            secondary_relative_symmetry_error: 0.0,
            stiffness_minimum_eigenvalue: 4.0,
            secondary_minimum_eigenvalue: 1.0,
        },
        vec![
            SpectralModeV1::Modal {
                eigenvalue_rad2_per_s2: 4.0,
                omega_rad_per_s: 2.0,
                frequency_hz: 1.0 / std::f64::consts::PI,
                period_s: std::f64::consts::PI,
                mass_normalized_shape: vec![1.0, 0.0],
                max_component_normalized_shape: vec![1.0, 0.0],
                generalized_mass: 1.0,
                generalized_stiffness: 4.0,
                residual_relative_inf: 0.0,
            },
            SpectralModeV1::Modal {
                eigenvalue_rad2_per_s2: 9.0,
                omega_rad_per_s: 3.0,
                frequency_hz: 3.0 / (2.0 * std::f64::consts::PI),
                period_s: (2.0 * std::f64::consts::PI) / 3.0,
                mass_normalized_shape: vec![0.0, 1.0],
                max_component_normalized_shape: vec![0.0, 1.0],
                generalized_mass: 1.0,
                generalized_stiffness: 9.0,
                residual_relative_inf: 0.0,
            },
        ],
    )
    .expect("valid result")
}

#[test]
fn result_and_report_round_trip_as_exact_self_hashed_wire_documents() {
    let result = result();
    let parsed = parse_dense_spectral_result_ir_v1(result.canonical_bytes()).expect("parse result");
    assert_eq!(parsed.canonical_bytes(), result.canonical_bytes());

    let report = build_dense_spectral_report_ir_v1(&result, b"deterministic markdown")
        .expect("build report");
    let parsed_report = parse_dense_spectral_report_ir_v1(report.canonical_json().as_bytes())
        .expect("parse report");
    assert_eq!(parsed_report.canonical_json(), report.canonical_json());
}

#[test]
fn identity_derived_values_variants_and_self_hashes_fail_closed() {
    let request = request();
    let mut identity = valid_identity(&request);
    identity.model_hash = format!("sha256:{}", "3".repeat(64));
    assert_eq!(
        build_dense_spectral_result_ir_v1(
            &request,
            identity,
            SpectralResultSummaryV1 {
                mode_count: 1,
                rigid_mode_count: 0,
                finite_positive_eigenvalue_count: 0,
                geometric_stiffness_positive_rank: 0,
                eigensolver_sweeps: 0,
                critical_load_factor: None,
                metric_orthogonality_error_inf: 0.0,
                operator_diagonalization_error_inf: 0.0,
                stiffness_relative_symmetry_error: 0.0,
                secondary_relative_symmetry_error: 0.0,
                stiffness_minimum_eigenvalue: 1.0,
                secondary_minimum_eigenvalue: 1.0,
            },
            Vec::new(),
        )
        .expect_err("model drift must fail")
        .code,
        "spectral_result_model_hash_mismatch"
    );

    let result = result();
    let mut tampered: serde_json::Value =
        serde_json::from_str(result.canonical_json()).expect("result JSON");
    tampered["modes"][0]["frequency_hz"] = serde_json::json!(7.0);
    assert_eq!(
        parse_dense_spectral_result_ir_v1(
            serde_json::to_string(&tampered)
                .expect("serialize tamper")
                .as_bytes()
        )
        .expect_err("derived value drift must fail")
        .code,
        "spectral_result_modal_derived_value_invalid"
    );

    let mut forged_shape: serde_json::Value =
        serde_json::from_str(result.canonical_json()).expect("result JSON");
    forged_shape["modes"][0]["max_component_normalized_shape"] = serde_json::json!([0.0, 1.0]);
    assert_eq!(
        parse_dense_spectral_result_ir_v1(
            serde_json::to_string(&forged_shape)
                .expect("serialize forged shape")
                .as_bytes()
        )
        .expect_err("unrelated normalized shape must fail")
        .code,
        "spectral_result_max_shape_invalid"
    );

    let mut variant: serde_json::Value =
        serde_json::from_str(result.canonical_json()).expect("result JSON");
    variant["modes"][0]["mode_kind"] = serde_json::json!("linear_buckling");
    assert_eq!(
        parse_dense_spectral_result_ir_v1(
            serde_json::to_string(&variant)
                .expect("serialize variant")
                .as_bytes()
        )
        .expect_err("variant drift must fail")
        .code,
        "spectral_result_decode_failed"
    );

    let report = build_dense_spectral_report_ir_v1(&result, b"report").expect("build valid report");
    let mut report_tamper: serde_json::Value =
        serde_json::from_str(report.canonical_json()).expect("report JSON");
    report_tamper["summary"]["primary_value"] = serde_json::json!(5.0);
    assert_eq!(
        parse_dense_spectral_report_ir_v1(
            serde_json::to_string(&report_tamper)
                .expect("serialize report tamper")
                .as_bytes()
        )
        .expect_err("report self-hash drift must fail")
        .code,
        "spectral_report_hash_mismatch"
    );
}
