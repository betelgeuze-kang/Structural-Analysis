use structural_contracts::sparse_product::{
    build_sparse_linear_request_v1, SparseLinearAnalysisRequestDocumentV1,
    SparseLinearAnalysisRequestV1, SparseLinearBackendV1, SparseLinearConfigV1,
    SPARSE_LINEAR_REQUEST_V1,
};
use structural_runtime::{
    Runtime, SparseLinearCheckpointV1, SparseLinearExecutionStatus, SparseLinearSolverStatus,
};

fn request() -> SparseLinearAnalysisRequestDocumentV1 {
    build_sparse_linear_request_v1(SparseLinearAnalysisRequestV1 {
        schema_version: SPARSE_LINEAR_REQUEST_V1.to_owned(),
        operation: "solve_sparse_spd_pcg".to_owned(),
        case_id: "sparse-real-pcg-c4".to_owned(),
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
    })
    .expect("request")
}

#[test]
fn checkpoint_round_trip_contains_the_actual_iteration_state_and_all_hashes() {
    let request = request();
    let runtime = Runtime::new().expect("runtime");
    let progress = runtime
        .advance_sparse_linear_product(&request, None, 1)
        .expect("one PCG boundary");
    assert!(progress.result_ir.is_none());
    assert_eq!(
        progress.checkpoint.state().execution_status,
        SparseLinearExecutionStatus::Active
    );
    assert_eq!(progress.checkpoint.state().iterations, 1);
    assert_eq!(progress.checkpoint.state().solution.len(), 5);
    assert_eq!(progress.checkpoint.state().residual.len(), 5);
    assert_eq!(progress.checkpoint.state().direction.len(), 5);
    assert_eq!(progress.checkpoint.state().diagonal_inverse.len(), 5);

    let decoded = SparseLinearCheckpointV1::from_bytes(progress.checkpoint.as_bytes())
        .expect("checkpoint decode");
    assert_eq!(decoded, progress.checkpoint);
    let receipt = decoded.receipt();
    assert_eq!(receipt.phase, "pcg_iteration_boundary");
    assert_eq!(receipt.execution_status, "active");
    assert_eq!(receipt.solver_status, "nonconvergence");
    assert_eq!(receipt.iterations, 1);
    for identity in [
        receipt.request_hash,
        receipt.model_hash,
        receipt.state_hash,
        receipt.execution_hash,
        receipt.checkpoint_hash,
    ] {
        assert_eq!(identity.len(), 71);
        assert!(identity.starts_with("sha256:"));
    }
}

#[test]
fn every_checkpoint_byte_and_request_drift_fail_closed() {
    let request = request();
    let runtime = Runtime::new().expect("runtime");
    let checkpoint = runtime
        .advance_sparse_linear_product(&request, None, 1)
        .expect("checkpoint")
        .checkpoint;
    for index in 0..checkpoint.as_bytes().len() {
        let mut corrupt = checkpoint.as_bytes().to_vec();
        corrupt[index] ^= 0x01;
        assert_eq!(
            SparseLinearCheckpointV1::from_bytes(&corrupt)
                .expect_err("every single-byte mutation must fail")
                .code,
            1301,
            "wrong taxonomy at byte {index}"
        );
    }

    let mut drift = request.request().clone();
    drift.values[0] = 5.0;
    let drift = build_sparse_linear_request_v1(drift).expect("drift request");
    assert_eq!(
        Runtime::restore_sparse_linear(&drift, checkpoint.as_bytes())
            .expect_err("operator drift must fail")
            .code,
        1301
    );
}

#[test]
fn segmented_resume_and_direct_execution_publish_identical_terminal_artifacts() {
    let request = request();
    let runtime = Runtime::new().expect("runtime");
    let direct = runtime
        .advance_sparse_linear_product(&request, None, u32::MAX)
        .expect("direct completion");
    let first = runtime
        .advance_sparse_linear_product(&request, None, 1)
        .expect("first segment");
    let resumed = runtime
        .advance_sparse_linear_product(&request, Some(first.checkpoint.as_bytes()), u32::MAX)
        .expect("resumed completion");

    assert_eq!(direct.checkpoint.as_bytes(), resumed.checkpoint.as_bytes());
    assert_eq!(
        direct
            .result_ir
            .as_ref()
            .expect("direct ResultIR")
            .canonical_bytes(),
        resumed
            .result_ir
            .as_ref()
            .expect("resumed ResultIR")
            .canonical_bytes()
    );
    assert_eq!(
        direct.checkpoint.state().execution_status,
        SparseLinearExecutionStatus::Terminal
    );
    assert_eq!(
        direct.checkpoint.state().solver_status,
        SparseLinearSolverStatus::Converged
    );
}

#[test]
fn numerical_failure_is_a_durable_terminal_checkpoint_not_lost_partial_state() {
    let mut bounded = request().request().clone();
    bounded.case_id = "sparse-nonconvergence-c4".to_owned();
    bounded.right_hand_side = vec![1.0; 5];
    bounded.config.max_iterations = 1;
    let bounded = build_sparse_linear_request_v1(bounded).expect("bounded request");
    let runtime = Runtime::new().expect("runtime");
    let progress = runtime
        .advance_sparse_linear_product(&bounded, None, u32::MAX)
        .expect("terminal nonconvergence state");
    assert!(progress.result_ir.is_none());
    assert_eq!(
        progress.checkpoint.state().execution_status,
        SparseLinearExecutionStatus::Terminal
    );
    assert_eq!(
        progress.checkpoint.state().solver_status,
        SparseLinearSolverStatus::Nonconvergence
    );
    assert_eq!(progress.checkpoint.state().iterations, 1);
    let restored = Runtime::restore_sparse_linear(&bounded, progress.checkpoint.as_bytes())
        .expect("failure checkpoint restores");
    assert_eq!(restored, progress.checkpoint);
}
