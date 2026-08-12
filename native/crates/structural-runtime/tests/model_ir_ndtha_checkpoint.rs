use std::path::{Path, PathBuf};

use structural_contracts::product_ir::{
    parse_model_ir_ndtha_analysis_request_v1, parse_native_analysis_request_v1,
};
use structural_runtime::{ModelIrNdthaCheckpointBindingsV1, ModelIrNdthaCheckpointV1, Runtime};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture(path: &str) -> Vec<u8> {
    std::fs::read(repository_root().join(path)).expect("fixture bytes")
}

fn checkpoint() -> (ModelIrNdthaCheckpointV1, ModelIrNdthaCheckpointBindingsV1) {
    let native = parse_native_analysis_request_v1(&fixture(
        "native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json",
    ))
    .expect("native request");
    let adapter = parse_model_ir_ndtha_analysis_request_v1(&fixture(
        "native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json",
    ))
    .expect("adapter request");
    let runtime = Runtime::new().expect("runtime");
    let request = native.request();
    let mut state = runtime
        .begin_nonlinear_ndtha(&request.config, &request.inputs)
        .expect("initial state");
    runtime
        .advance_nonlinear_ndtha(&request.config, &request.inputs, 2, &mut state)
        .expect("partial advance");
    let inner = runtime
        .checkpoint_nonlinear_ndtha(&request.config, &request.inputs, &state)
        .expect("inner checkpoint");
    let bindings = ModelIrNdthaCheckpointBindingsV1 {
        model_content_hash:
            "sha256:d0fa14472103a367cf33668f599f7ada56a5296e704d5e44ae5523484315ca2f".to_owned(),
        model_semantic_hash:
            "sha256:73d45b031624262686c57c86a9bd3406be2efdbdf5ca3a6175aedc7b71c13d63".to_owned(),
        model_provenance_hash:
            "sha256:719254d5ad9b543a1a15d77b7a96a8b7ec7b9f20108660fc022a67208260eda9".to_owned(),
        adapter_request_hash: adapter.request_hash().to_owned(),
        generated_request_hash: native.request_hash().to_owned(),
    };
    let outer = ModelIrNdthaCheckpointV1::create(inner, &bindings).expect("outer checkpoint");
    (outer, bindings)
}

#[test]
fn model_checkpoint_round_trip_preserves_all_five_external_bindings() {
    let (checkpoint, bindings) = checkpoint();
    let decoded = ModelIrNdthaCheckpointV1::from_bytes(checkpoint.as_bytes()).expect("decode");
    decoded.verify_bindings(&bindings).expect("exact bindings");
    assert_eq!(decoded.as_bytes(), checkpoint.as_bytes());
    assert_eq!(decoded.inner().as_bytes(), checkpoint.inner().as_bytes());
    let receipt = decoded.receipt();
    assert_eq!(receipt.model_content_hash, bindings.model_content_hash);
    assert_eq!(receipt.model_semantic_hash, bindings.model_semantic_hash);
    assert_eq!(
        receipt.model_provenance_hash,
        bindings.model_provenance_hash
    );
    assert_eq!(receipt.adapter_request_hash, bindings.adapter_request_hash);
    assert_eq!(
        receipt.generated_request_hash,
        bindings.generated_request_hash
    );
}

#[test]
fn every_single_byte_mutation_and_binding_drift_fails_closed() {
    let (checkpoint, bindings) = checkpoint();
    for index in 0..checkpoint.as_bytes().len() {
        let mut mutated = checkpoint.as_bytes().to_vec();
        mutated[index] ^= 1;
        assert!(
            ModelIrNdthaCheckpointV1::from_bytes(&mutated).is_err(),
            "single-byte mutation accepted at {index}"
        );
    }

    let decoded = ModelIrNdthaCheckpointV1::from_bytes(checkpoint.as_bytes()).expect("decode");
    let mut mismatched = bindings;
    mismatched.adapter_request_hash =
        "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_owned();
    let error = decoded
        .verify_bindings(&mismatched)
        .expect_err("binding mismatch");
    assert_eq!(error.code, 1301);
}
