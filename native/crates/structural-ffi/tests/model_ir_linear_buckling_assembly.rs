use std::path::{Path, PathBuf};

use serde_json::json;
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_ffi::{Api, ModelIrLinearBucklingAssemblyRequest};
use structural_ffi_sys::{
    SA_ABI_V1_15, SA_CAPABILITY_MODEL_IR_LINEAR_BUCKLING_ASSEMBLY_CPU, SA_ERR_INDEFINITE_OPERATOR,
    SA_ERR_RESIDUAL_LIMIT, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
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

fn compression_fixture() -> ModelIrV2Document {
    let mut value = fixture().value().clone();
    value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(-100_000.0);
    parse_model_ir_v2(&serde_json::to_vec(&value).expect("compression fixture JSON"))
        .expect("strict compression fixture")
}

fn equilibrated_request() -> ModelIrLinearBucklingAssemblyRequest {
    let mut equilibrium_displacement = vec![0.0; 12];
    equilibrium_displacement[6] = -0.000_05;
    ModelIrLinearBucklingAssemblyRequest {
        load_pattern_id: "LC_AXIAL".to_owned(),
        equilibrium_displacement,
    }
}

#[test]
fn v1_15_safe_wrapper_matches_the_independent_cantilever_oracle() {
    let source = compression_fixture();
    let api = Api::load_model_ir_linear_buckling_assembly().expect("v1.15 API");
    assert_eq!(api.abi_version(), SA_ABI_V1_15);
    assert_ne!(
        api.capabilities() & SA_CAPABILITY_MODEL_IR_LINEAR_BUCKLING_ASSEMBLY_CPU,
        0
    );
    let model = api.create_model_ir(&source).expect("native model");
    let first = model
        .assemble_linear_buckling_reference(&equilibrated_request())
        .expect("bounded geometric assembly");
    let repeated = model
        .assemble_linear_buckling_reference(&equilibrated_request())
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

    // Independent j-end submatrix of P/(30 L) times the standard beam-column coefficients.
    let scale = 100_000.0 / (30.0 * 2.0);
    let mut oracle = vec![0.0; 36];
    let index = |row: usize, column: usize| row * 6 + column;
    oracle[index(1, 1)] = 36.0 * scale;
    oracle[index(1, 5)] = -6.0 * scale;
    oracle[index(5, 1)] = -6.0 * scale;
    oracle[index(5, 5)] = 16.0 * scale;
    oracle[index(2, 2)] = 36.0 * scale;
    oracle[index(2, 4)] = 6.0 * scale;
    oracle[index(4, 2)] = 6.0 * scale;
    oracle[index(4, 4)] = 16.0 * scale;
    assert_eq!(first.geometric_stiffness, oracle);
    assert_eq!(first.frame_stable_indices, [0]);
    assert_eq!(first.frame_axial_compression_n, [100_000.0]);
    assert_eq!(
        first.equilibrium_residual_inf_n.to_bits(),
        0.0_f64.to_bits()
    );
    assert_eq!(first.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(first.fallback_count, 0);
}

#[test]
fn wrapper_fails_closed_for_non_equilibrium_tension_and_old_tables() {
    let compression = compression_fixture();
    let model = Api::load_model_ir_linear_buckling_assembly()
        .expect("v1.15 API")
        .create_model_ir(&compression)
        .expect("compression model");
    let mut non_equilibrium = equilibrated_request();
    non_equilibrium.equilibrium_displacement.fill(0.0);
    let error = model
        .assemble_linear_buckling_reference(&non_equilibrium)
        .expect_err("non-equilibrium state fails");
    assert_eq!(error.code, SA_ERR_RESIDUAL_LIMIT);

    let tension = fixture();
    let tension_model = Api::load_model_ir_linear_buckling_assembly()
        .expect("v1.15 API")
        .create_model_ir(&tension)
        .expect("tension model");
    let mut tension_request = equilibrated_request();
    tension_request.equilibrium_displacement[6] = 0.000_05;
    let error = tension_model
        .assemble_linear_buckling_reference(&tension_request)
        .expect_err("tensile prestress fails");
    assert_eq!(error.code, SA_ERR_INDEFINITE_OPERATOR);

    let old_model = Api::load_model_ir_linear_reactions()
        .expect("v1.14 API")
        .create_model_ir(&compression)
        .expect("old-table model");
    let error = old_model
        .assemble_linear_buckling_reference(&equilibrated_request())
        .expect_err("v1.14 table cannot claim v1.15 operation");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}
