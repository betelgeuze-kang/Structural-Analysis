use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_ffi::{Api, ModelIrLinearReactionRequest};
use structural_ffi_sys::{
    SA_ABI_V1_14, SA_CAPABILITY_MODEL_IR_LINEAR_REACTIONS_CPU, SA_ERR_INVALID_ARGUMENT,
    SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture() -> ModelIrV2Document {
    let bytes = std::fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("fixture bytes");
    parse_model_ir_v2(&bytes).expect("strict fixture")
}

fn equilibrated_axial_request() -> ModelIrLinearReactionRequest {
    let mut displacement = vec![0.0; 12];
    displacement[6] = 0.000_05;
    ModelIrLinearReactionRequest {
        load_pattern_id: "LC_AXIAL".to_owned(),
        displacement,
    }
}

#[test]
fn v1_14_safe_wrapper_recovers_canonical_support_reactions() {
    let source = fixture();
    let api = Api::load_model_ir_linear_reactions().expect("v1.14 API");
    assert_eq!(api.abi_version(), SA_ABI_V1_14);
    assert_ne!(
        api.capabilities() & SA_CAPABILITY_MODEL_IR_LINEAR_REACTIONS_CPU,
        0
    );
    let model = api.create_model_ir(&source).expect("native model");
    let sizes = model.linear_reaction_sizes().expect("checked exact sizes");
    assert_eq!(sizes.global_dof_count, 12);
    assert_eq!(sizes.constrained_dof_count, 6);
    assert_eq!(sizes.model_identity_length, 71);

    let first = model
        .recover_linear_reactions(&equilibrated_axial_request())
        .expect("bounded reaction recovery");
    let repeated = model
        .recover_linear_reactions(&equilibrated_axial_request())
        .expect("deterministic repeat");

    assert_eq!(first, repeated);
    assert_eq!(first.model_content_hash, source.content_hash());
    assert_eq!(first.model_semantic_hash, source.semantic_hash());
    assert_eq!(first.model_provenance_hash, source.provenance_hash());
    assert_eq!(first.load_pattern_index, 0);
    assert_eq!(first.global_dof_count, 12);
    assert_eq!(first.constrained_dof_indices, [0, 1, 2, 3, 4, 5]);
    assert_eq!(first.constrained_external_load, [0.0; 6]);
    assert_eq!(
        first.constrained_internal_force[0].to_bits(),
        (-100_000.0_f64).to_bits()
    );
    assert_eq!(first.reactions[0].to_bits(), (-100_000.0_f64).to_bits());
    assert!(first
        .reactions
        .iter()
        .zip(&first.constrained_internal_force)
        .zip(&first.constrained_external_load)
        .all(|((reaction, internal), external)| {
            reaction.to_bits() == (*internal - *external).to_bits()
        }));
    assert_eq!(first.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(first.fallback_count, 0);
}

#[test]
fn safe_wrapper_rejects_invalid_reaction_requests_before_partial_results_exist() {
    let source = fixture();
    let model = Api::load_model_ir_linear_reactions()
        .expect("v1.14 API")
        .create_model_ir(&source)
        .expect("native model");

    let mut wrong_length = equilibrated_axial_request();
    wrong_length.displacement.pop();
    let error = model
        .recover_linear_reactions(&wrong_length)
        .expect_err("wrong state length fails");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut nonfinite = equilibrated_axial_request();
    nonfinite.displacement[6] = f64::NAN;
    let error = model
        .recover_linear_reactions(&nonfinite)
        .expect_err("nonfinite state fails");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut missing = equilibrated_axial_request();
    missing.load_pattern_id = "LC_MISSING".to_owned();
    let error = model
        .recover_linear_reactions(&missing)
        .expect_err("unknown load pattern fails");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut malformed = equilibrated_axial_request();
    malformed.load_pattern_id = "*invalid".to_owned();
    let error = model
        .recover_linear_reactions(&malformed)
        .expect_err("malformed selector fails before FFI");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
}

#[test]
fn older_model_ir_table_cannot_claim_reaction_slots() {
    let source = fixture();
    let model = Api::load_model_ir_linear_assembly()
        .expect("v1.13 API")
        .create_model_ir(&source)
        .expect("native model");
    let error = model
        .recover_linear_reactions(&equilibrated_axial_request())
        .expect_err("v1.13 table has no v1.14 slots");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}

#[test]
fn immutable_reaction_recovery_is_safe_for_concurrent_reads() {
    let source = fixture();
    let model = Arc::new(
        Api::load_model_ir_linear_reactions()
            .expect("v1.14 API")
            .create_model_ir(&source)
            .expect("native model"),
    );
    let request = Arc::new(equilibrated_axial_request());
    let workers: Vec<_> = (0..8)
        .map(|_| {
            let model = Arc::clone(&model);
            let request = Arc::clone(&request);
            thread::spawn(move || {
                for _ in 0..32 {
                    let result = model
                        .recover_linear_reactions(&request)
                        .expect("concurrent immutable recovery");
                    assert_eq!(result.fallback_count, 0);
                    assert_eq!(result.reactions[0].to_bits(), (-100_000.0_f64).to_bits());
                }
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("worker does not panic");
    }
}
