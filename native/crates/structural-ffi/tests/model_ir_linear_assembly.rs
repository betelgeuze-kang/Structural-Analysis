use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use serde_json::json;
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_ffi::{Api, ModelIrLinearAssemblyRequest};
use structural_ffi_sys::{
    SA_ABI_V1_13, SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU, SA_ELEMENT_FRAME_3D,
    SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
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

fn axial_request() -> ModelIrLinearAssemblyRequest {
    ModelIrLinearAssemblyRequest {
        load_pattern_id: "LC_AXIAL".to_owned(),
        displacement: vec![0.0; 12],
        direction: vec![0.0; 12],
    }
}

fn offset_fixture() -> ModelIrV2Document {
    let mut value = fixture().value().clone();
    value["elements"][0]["offsets"]["i_global_m"] = json!([0.0, 0.2, 0.0]);
    value["elements"][0]["offsets"]["j_global_m"] = json!([0.0, -0.1, 0.1]);
    parse_model_ir_v2(&serde_json::to_vec(&value).expect("offset fixture JSON"))
        .expect("strict offset fixture")
}

#[test]
fn v1_13_safe_wrapper_preserves_identity_and_canonical_csr() {
    let source = fixture();
    let api = Api::load_model_ir_linear_assembly().expect("v1.13 API");
    assert_eq!(api.abi_version(), SA_ABI_V1_13);
    assert_ne!(
        api.capabilities() & SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU,
        0
    );
    let model = api.create_model_ir(&source).expect("native model");
    let sizes = model.linear_assembly_sizes().expect("checked exact sizes");
    assert_eq!(sizes.global_dof_count, 12);
    assert_eq!(sizes.active_dof_count, 6);
    assert_eq!(sizes.row_offset_count, 7);
    assert_eq!(sizes.structural_entry_count, 36);
    assert_eq!(sizes.recovery_record_count, 1);
    assert_eq!(sizes.recovery_offset_count, 2);
    assert_eq!(sizes.recovery_value_count, 12);
    assert_eq!(sizes.model_identity_length, 71);
    let first = model
        .assemble_linear_reference(&axial_request())
        .expect("bounded assembly");
    let repeated = model
        .assemble_linear_reference(&axial_request())
        .expect("deterministic repeat");

    assert_eq!(first, repeated);
    assert_eq!(first.model_content_hash, source.content_hash());
    assert_eq!(first.model_semantic_hash, source.semantic_hash());
    assert_eq!(first.model_provenance_hash, source.provenance_hash());
    assert_eq!(first.load_pattern_index, 0);
    assert_eq!(first.global_dof_count, 12);
    assert_eq!(first.active_dof_indices, [6, 7, 8, 9, 10, 11]);
    assert_eq!(first.row_offsets, [0, 6, 12, 18, 24, 30, 36]);
    assert_eq!(
        first.column_indices,
        [0, 1, 2, 3, 4, 5]
            .into_iter()
            .cycle()
            .take(36)
            .collect::<Vec<_>>()
    );
    assert_eq!(first.tangent[0].to_bits(), 2_000_000_000.0_f64.to_bits());
    assert_eq!(first.external_load, [100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
    assert_eq!(first.internal_force, [0.0; 6]);
    assert_eq!(
        first.equilibrium_residual,
        [-100_000.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(first.jvp, [0.0; 6]);
    assert_eq!(first.recovery_stable_indices, [0]);
    assert_eq!(first.recovery_element_types, [SA_ELEMENT_FRAME_3D]);
    assert_eq!(first.recovery_offsets, [0, 12]);
    assert_eq!(first.recovery_values, [0.0; 12]);
    assert_eq!(first.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(first.fallback_count, 0);
}

#[test]
fn safe_wrapper_preserves_frame3d_rigid_offsets_through_native_assembly() {
    let baseline_source = fixture();
    let offset_source = offset_fixture();
    let api = Api::load_model_ir_linear_assembly().expect("v1.13 API");
    let baseline_model = api
        .create_model_ir(&baseline_source)
        .expect("baseline native model");
    let offset_model = api
        .create_model_ir(&offset_source)
        .expect("offset native model");
    let mut request = axial_request();
    request.displacement[7] = 0.002;
    request.displacement[9] = -0.003;
    request.direction[8] = 1.0;
    request.direction[10] = -0.5;

    let baseline = baseline_model
        .assemble_linear_reference(&request)
        .expect("baseline assembly");
    let offset = offset_model
        .assemble_linear_reference(&request)
        .expect("offset assembly");
    let repeated = offset_model
        .assemble_linear_reference(&request)
        .expect("deterministic offset repeat");

    assert_eq!(offset, repeated);
    assert_ne!(offset.tangent, baseline.tangent);
    assert_ne!(offset.consistent_mass, baseline.consistent_mass);
    assert_ne!(offset.internal_force, baseline.internal_force);
    assert_ne!(offset.jvp, baseline.jvp);
    assert_ne!(offset.recovery_values, baseline.recovery_values);
    assert_eq!(offset.model_content_hash, offset_source.content_hash());
    assert_eq!(offset.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(offset.fallback_count, 0);
}

#[test]
fn safe_wrapper_rejects_out_of_profile_requests_without_partial_results() {
    let source = fixture();
    let api = Api::load_model_ir_linear_assembly().expect("v1.13 API");
    let model = api.create_model_ir(&source).expect("native model");

    let mut constrained = axial_request();
    constrained.displacement[0] = 1.0;
    let error = model
        .assemble_linear_reference(&constrained)
        .expect_err("nonzero constrained state fails");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut missing = axial_request();
    missing.load_pattern_id = "LC_MISSING".to_owned();
    let error = model
        .assemble_linear_reference(&missing)
        .expect_err("unknown load pattern fails");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);

    let mut malformed = axial_request();
    malformed.load_pattern_id = "*invalid".to_owned();
    let error = model
        .assemble_linear_reference(&malformed)
        .expect_err("malformed selector fails before FFI");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
}

#[test]
fn older_model_ir_table_cannot_claim_the_appended_operation() {
    let source = fixture();
    let model = Api::load_model_ir()
        .expect("v1.1 API")
        .create_model_ir(&source)
        .expect("native model");
    let error = model
        .assemble_linear_reference(&axial_request())
        .expect_err("v1.1 table has no v1.13 slot");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}

#[test]
fn immutable_model_assembly_is_safe_for_concurrent_reads() {
    let source = fixture();
    let model = Arc::new(
        Api::load_model_ir_linear_assembly()
            .expect("v1.13 API")
            .create_model_ir(&source)
            .expect("native model"),
    );
    let request = Arc::new(axial_request());
    let workers: Vec<_> = (0..8)
        .map(|_| {
            let model = Arc::clone(&model);
            let request = Arc::clone(&request);
            thread::spawn(move || {
                for _ in 0..32 {
                    let result = model
                        .assemble_linear_reference(&request)
                        .expect("concurrent immutable assembly");
                    assert_eq!(result.fallback_count, 0);
                    assert_eq!(result.row_offsets.last(), Some(&36));
                }
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("worker does not panic");
    }
}
