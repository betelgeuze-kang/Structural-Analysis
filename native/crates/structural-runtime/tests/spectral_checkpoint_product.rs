use structural_contracts::spectral_product::{
    build_dense_spectral_request_v1, DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1,
    SpectralBackendV1, SpectralGeneralizedEigenConfigV1, SpectralModeV1, DENSE_SPECTRAL_REQUEST_V1,
};
use structural_runtime::{DenseSpectralCheckpointV1, Runtime};

fn modal_request() -> structural_contracts::spectral_product::DenseSpectralAnalysisRequestDocumentV1
{
    build_dense_spectral_request_v1(DenseSpectralAnalysisRequestV1 {
        schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
        operation: "solve_dense_generalized_eigen".to_owned(),
        case_id: "modal-rigid-c4".to_owned(),
        analysis_kind: SpectralAnalysisKindV1::Modal,
        backend: SpectralBackendV1::Cpu,
        order: 3,
        stiffness: vec![0.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 9.0],
        secondary_matrix: vec![1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
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
    .expect("modal request")
}

#[test]
fn phase_checkpoint_round_trip_binds_all_identities_and_exact_request() {
    let request = modal_request();
    let checkpoint = Runtime::checkpoint_dense_spectral(&request).expect("checkpoint");
    let parsed = DenseSpectralCheckpointV1::from_bytes(checkpoint.as_bytes()).expect("decode");
    assert_eq!(parsed.as_bytes(), checkpoint.as_bytes());
    assert_eq!(parsed.receipt(), checkpoint.receipt());
    let receipt = checkpoint.receipt();
    assert_eq!(receipt.phase, "validated_ready_for_atomic_native_solve");
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
    Runtime::restore_dense_spectral(&request, checkpoint.as_bytes()).expect("restore");
}

#[test]
fn every_artifact_region_and_request_drift_fail_closed() {
    let request = modal_request();
    let checkpoint = Runtime::checkpoint_dense_spectral(&request).expect("checkpoint");
    for index in 0..checkpoint.as_bytes().len() {
        let mut corrupt = checkpoint.as_bytes().to_vec();
        corrupt[index] ^= 0x01;
        assert_eq!(
            DenseSpectralCheckpointV1::from_bytes(&corrupt)
                .expect_err("every single-byte mutation must fail")
                .code,
            1301,
            "wrong taxonomy at byte {index}"
        );
    }
    let mut drift = request.request().clone();
    drift.stiffness[4] = 5.0;
    let drift = build_dense_spectral_request_v1(drift).expect("drift request");
    assert_eq!(
        Runtime::restore_dense_spectral(&drift, checkpoint.as_bytes())
            .expect_err("request drift must fail")
            .code,
        1301
    );
}

#[test]
fn direct_and_checkpoint_resume_results_are_bitwise_identical() {
    let request = modal_request();
    let runtime = Runtime::new().expect("runtime");
    let checkpoint = Runtime::checkpoint_dense_spectral(&request).expect("checkpoint");
    let direct = runtime
        .execute_dense_spectral_product(&request, None)
        .expect("direct");
    let resumed = runtime
        .execute_dense_spectral_product(&request, Some(checkpoint.as_bytes()))
        .expect("resumed");
    assert_eq!(direct.checkpoint.as_bytes(), resumed.checkpoint.as_bytes());
    assert_eq!(
        direct.result_ir.canonical_bytes(),
        resumed.result_ir.canonical_bytes()
    );
    assert_eq!(direct.result_ir.result().summary.rigid_mode_count, 1);
    assert_eq!(
        direct
            .result_ir
            .result()
            .summary
            .finite_positive_eigenvalue_count,
        0
    );
    match &direct.result_ir.result().modes[0] {
        SpectralModeV1::Modal {
            eigenvalue_rad2_per_s2,
            mass_normalized_shape,
            ..
        } => {
            assert_eq!(eigenvalue_rad2_per_s2.to_bits(), 4.0_f64.to_bits());
            assert_eq!(mass_normalized_shape, &[0.0, 1.0, 0.0]);
        }
        SpectralModeV1::LinearBuckling { .. } => panic!("wrong mode kind"),
    }
}
