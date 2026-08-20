use structural_contracts::product_ir::sha256_identity;
use structural_contracts::spectral_product::{
    build_dense_spectral_request_v1, DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1,
    SpectralBackendV1, SpectralGeneralizedEigenConfigV1, DENSE_SPECTRAL_REQUEST_V1,
};
use structural_runtime::{ModelIrModalCheckpointBindingsV1, ModelIrModalCheckpointV1, Runtime};

fn bindings() -> ModelIrModalCheckpointBindingsV1 {
    ModelIrModalCheckpointBindingsV1 {
        model_content_hash: sha256_identity(b"content"),
        model_semantic_hash: sha256_identity(b"semantic"),
        model_provenance_hash: sha256_identity(b"provenance"),
        analysis_request_hash: sha256_identity(b"outer-request"),
        assembly_hash: sha256_identity(b"assembly"),
        generated_request_hash: sha256_identity(b"generated-request"),
    }
}

fn checkpoint() -> ModelIrModalCheckpointV1 {
    let request = build_dense_spectral_request_v1(DenseSpectralAnalysisRequestV1 {
        schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
        operation: "solve_dense_generalized_eigen".to_owned(),
        case_id: "model-modal-checkpoint".to_owned(),
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
    .expect("dense request");
    let inner = Runtime::checkpoint_dense_spectral(&request).expect("dense checkpoint");
    ModelIrModalCheckpointV1::create(inner, &bindings()).expect("model checkpoint")
}

#[test]
fn modal_checkpoint_round_trip_preserves_every_outer_and_inner_binding() {
    let checkpoint = checkpoint();
    let parsed = ModelIrModalCheckpointV1::from_bytes(checkpoint.as_bytes()).expect("round trip");
    parsed.verify_bindings(&bindings()).expect("bindings");
    assert_eq!(parsed.as_bytes(), checkpoint.as_bytes());
    assert_eq!(parsed.inner().as_bytes(), checkpoint.inner().as_bytes());
    assert_eq!(parsed.receipt(), checkpoint.receipt());
    assert_eq!(
        parsed.receipt().artifact_bytes,
        u64::try_from(parsed.as_bytes().len()).expect("bounded checkpoint length")
    );
}

#[test]
fn every_modal_checkpoint_byte_and_each_outer_binding_fail_closed() {
    let checkpoint = checkpoint();
    for index in 0..checkpoint.as_bytes().len() {
        let mut corrupt = checkpoint.as_bytes().to_vec();
        corrupt[index] ^= 1;
        assert_eq!(
            ModelIrModalCheckpointV1::from_bytes(&corrupt)
                .expect_err("every mutation must fail")
                .code,
            1301,
            "wrong taxonomy at byte {index}"
        );
    }

    let mut variants = Vec::new();
    let base = bindings();
    for field in 0..6 {
        let mut drift = base.clone();
        let value = sha256_identity(format!("drift-{field}").as_bytes());
        match field {
            0 => drift.model_content_hash = value,
            1 => drift.model_semantic_hash = value,
            2 => drift.model_provenance_hash = value,
            3 => drift.analysis_request_hash = value,
            4 => drift.assembly_hash = value,
            5 => drift.generated_request_hash = value,
            _ => unreachable!(),
        }
        variants.push(drift);
    }
    for drift in variants {
        assert_eq!(
            checkpoint
                .verify_bindings(&drift)
                .expect_err("binding drift must fail")
                .code,
            1301
        );
    }
    assert_eq!(
        ModelIrModalCheckpointV1::from_bytes(
            &checkpoint.as_bytes()[..checkpoint.as_bytes().len() - 1]
        )
        .expect_err("truncation must fail")
        .code,
        1301
    );
    let mut trailing = checkpoint.as_bytes().to_vec();
    trailing.push(0);
    assert_eq!(
        ModelIrModalCheckpointV1::from_bytes(&trailing)
            .expect_err("trailing bytes must fail")
            .code,
        1301
    );
}
