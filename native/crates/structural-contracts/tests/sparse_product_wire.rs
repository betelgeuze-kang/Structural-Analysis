use structural_contracts::product_ir::{ProductIrContractError, ResultIdentityV1};
use structural_contracts::sparse_product::{
    build_sparse_linear_report_ir_v1, build_sparse_linear_request_v1,
    build_sparse_linear_result_ir_v1, parse_sparse_linear_report_ir_v1,
    parse_sparse_linear_request_v1, parse_sparse_linear_result_ir_v1,
    sparse_linear_execution_hash_v1, sparse_linear_model_hash_v1, SparseLinearAnalysisRequestV1,
    SparseLinearBackendV1, SparseLinearConfigV1, SparseLinearResultSummaryV1,
    SPARSE_LINEAR_REQUEST_V1,
};

fn request_value() -> SparseLinearAnalysisRequestV1 {
    SparseLinearAnalysisRequestV1 {
        schema_version: SPARSE_LINEAR_REQUEST_V1.to_owned(),
        operation: "solve_sparse_spd_pcg".to_owned(),
        case_id: "sparse-c4-c5".to_owned(),
        backend: SparseLinearBackendV1::Cpu,
        order: 5,
        row_offsets: vec![0, 2, 5, 8, 11, 13],
        column_indices: vec![0, 1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4],
        values: vec![
            4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 3.0, -1.0, -1.0, 2.0,
        ],
        right_hand_side: vec![6.0, -12.0, 18.0, -20.0, 14.0],
        initial_guess: Vec::new(),
        config: SparseLinearConfigV1 {
            max_iterations: 100,
            absolute_residual_tolerance: 1.0e-13,
            relative_residual_tolerance: 1.0e-13,
            maximum_increment: 0.0,
        },
    }
}

fn identity(
    request: &structural_contracts::sparse_product::SparseLinearAnalysisRequestDocumentV1,
) -> Result<ResultIdentityV1, ProductIrContractError> {
    Ok(ResultIdentityV1 {
        request_hash: request.request_hash().to_owned(),
        model_hash: sparse_linear_model_hash_v1(request)?,
        state_hash: format!("sha256:{}", "1".repeat(64)),
        execution_hash: sparse_linear_execution_hash_v1(request)?,
        checkpoint_hash: format!("sha256:{}", "2".repeat(64)),
    })
}

#[test]
#[allow(clippy::manual_pattern_char_comparison)] // Keep this test compatible with Rust 1.77.
fn request_is_strict_canonical_and_identity_stable() {
    let built = build_sparse_linear_request_v1(request_value()).expect("typed request");
    let parsed = parse_sparse_linear_request_v1(built.canonical_bytes()).expect("wire request");
    assert_eq!(parsed.canonical_bytes(), built.canonical_bytes());
    assert_eq!(parsed.request_hash(), built.request_hash());
    assert_eq!(
        sparse_linear_model_hash_v1(&parsed).expect("model hash"),
        sparse_linear_model_hash_v1(&built).expect("model hash")
    );
    assert_eq!(
        sparse_linear_execution_hash_v1(&parsed).expect("execution hash"),
        sparse_linear_execution_hash_v1(&built).expect("execution hash")
    );

    let duplicate = built.canonical_json().replace(
        "\"backend\":\"cpu\"",
        "\"backend\":\"cpu\",\"backend\":\"cpu\"",
    );
    assert!(parse_sparse_linear_request_v1(duplicate.as_bytes()).is_err());
    let unknown = built
        .canonical_json()
        .strip_suffix('}')
        .map(|prefix| format!("{prefix},\"unknown\":0}}"))
        .expect("object suffix");
    assert!(parse_sparse_linear_request_v1(unknown.as_bytes()).is_err());
    let mut nonfinite = built.canonical_json().to_owned();
    let value_start = nonfinite
        .find("\"maximum_increment\":")
        .map(|index| index + "\"maximum_increment\":".len())
        .expect("maximum increment field");
    let value_end = nonfinite[value_start..]
        .find(|character| character == ',' || character == '}')
        .map(|index| value_start + index)
        .expect("maximum increment terminator");
    nonfinite.replace_range(value_start..value_end, "NaN");
    assert!(parse_sparse_linear_request_v1(nonfinite.as_bytes()).is_err());

    let mut noncanonical_csr = request_value();
    noncanonical_csr.column_indices[2] = 1;
    assert!(build_sparse_linear_request_v1(noncanonical_csr).is_err());
}

#[test]
fn result_and_report_are_self_hashed_and_bound_to_true_residual() {
    let request = build_sparse_linear_request_v1(request_value()).expect("request");
    let result = build_sparse_linear_result_ir_v1(
        &request,
        identity(&request).expect("identity"),
        SparseLinearResultSummaryV1 {
            order: 5,
            nonzero_count: 13,
            iterations: 5,
            initial_residual_inf: 20.0,
            final_residual_inf: 0.0,
            final_residual_l2: 0.0,
            last_increment_inf: 0.25,
        },
        vec![1.0, -2.0, 3.0, -4.0, 5.0],
    )
    .expect("result");
    let parsed = parse_sparse_linear_result_ir_v1(result.canonical_bytes()).expect("parse result");
    assert_eq!(parsed.canonical_bytes(), result.canonical_bytes());
    assert_eq!(parsed.result_hash(), result.result_hash());

    let document = b"# Sparse linear result\n\nConverged.\n";
    let report = build_sparse_linear_report_ir_v1(&result, document).expect("report");
    let parsed_report =
        parse_sparse_linear_report_ir_v1(report.canonical_json().as_bytes()).expect("parse report");
    assert_eq!(parsed_report.canonical_json(), report.canonical_json());
    assert_eq!(parsed_report.report_hash(), report.report_hash());

    let mut tampered: serde_json::Value =
        serde_json::from_str(result.canonical_json()).expect("result JSON");
    tampered["solution"][0] = serde_json::json!(2.0);
    let tampered = serde_json::to_vec(&tampered).expect("tampered result JSON");
    assert!(parse_sparse_linear_result_ir_v1(&tampered).is_err());

    let wrong_residual = build_sparse_linear_result_ir_v1(
        &request,
        identity(&request).expect("identity"),
        SparseLinearResultSummaryV1 {
            order: 5,
            nonzero_count: 13,
            iterations: 5,
            initial_residual_inf: 20.0,
            final_residual_inf: 1.0,
            final_residual_l2: 1.0,
            last_increment_inf: 0.25,
        },
        vec![1.0, -2.0, 3.0, -4.0, 5.0],
    );
    assert!(wrong_residual.is_err());
}
