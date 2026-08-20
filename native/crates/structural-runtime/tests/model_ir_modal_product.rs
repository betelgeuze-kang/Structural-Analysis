use std::fs;
use std::path::{Path, PathBuf};

use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_modal_product::{
    build_model_ir_modal_analysis_request_v1, ModelIrModalAnalysisRequestV1, ModelIrModalBackendV1,
    MODEL_IR_MODAL_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::ModelIrIdentityV1;
use structural_contracts::spectral_product::{SpectralGeneralizedEigenConfigV1, SpectralModeV1};
use structural_runtime::Runtime;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn model() -> structural_contracts::model_ir::ModelIrV2Document {
    let bytes = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("ModelIR fixture");
    parse_model_ir_v2(&bytes).expect("strict ModelIR")
}

fn request(
    model: &structural_contracts::model_ir::ModelIrV2Document,
) -> structural_contracts::model_modal_product::ModelIrModalAnalysisRequestDocumentV1 {
    build_model_ir_modal_analysis_request_v1(ModelIrModalAnalysisRequestV1 {
        schema_version: MODEL_IR_MODAL_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_modal".to_owned(),
        case_id: "frame-cantilever-modal".to_owned(),
        backend: ModelIrModalBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: model.content_hash().to_owned(),
            semantic_hash: model.semantic_hash().to_owned(),
            provenance_hash: model.provenance_hash().to_owned(),
        },
        assembly_load_pattern_id: "LC_WEAK".to_owned(),
        config: SpectralGeneralizedEigenConfigV1 {
            mode_count: 3,
            maximum_sweeps: 4_096,
            symmetry_relative_tolerance: 1e-12,
            positive_semidefinite_relative_tolerance: 1e-12,
            mode_relative_tolerance: 1e-10,
            cluster_relative_tolerance: 1e-9,
            residual_relative_tolerance: 1e-9,
            orthogonality_tolerance: 1e-9,
            eigensolver_relative_tolerance: 1e-12,
        },
    })
    .expect("modal request")
}

fn one_element_cantilever_bending_eigenvalue(second_moment_m4: f64) -> f64 {
    let elastic_modulus_pa = 200.0e9;
    let density_kg_m3 = 7_850.0;
    let area_m2 = 0.02;
    let length_m = 2.0_f64;
    let ei = elastic_modulus_pa * second_moment_m4;
    let k11 = 12.0 * ei / length_m.powi(3);
    let k12 = -6.0 * ei / length_m.powi(2);
    let k22 = 4.0 * ei / length_m;
    let mass_scale = density_kg_m3 * area_m2 * length_m / 420.0;
    let m11 = mass_scale * 156.0;
    let m12 = -mass_scale * 22.0 * length_m;
    let m22 = mass_scale * 4.0 * length_m.powi(2);
    let quadratic = m11 * m22 - m12 * m12;
    let linear = -(k11 * m22 + k22 * m11 - 2.0 * k12 * m12);
    let constant = k11 * k22 - k12 * k12;
    let discriminant = linear * linear - 4.0 * quadratic * constant;
    (-linear - discriminant.sqrt()) / (2.0 * quadratic)
}

#[test]
fn typed_model_ir_assembly_drives_existing_native_modal_product() {
    let model = model();
    let request = request(&model);
    let runtime = Runtime::new().expect("runtime");
    let first = runtime
        .prepare_model_ir_modal_product(&model, &request)
        .expect("ModelIR modal adapter");
    let second = runtime
        .prepare_model_ir_modal_product(&model, &request)
        .expect("repeat ModelIR modal adapter");

    assert_eq!(first.assembly_receipt_json, second.assembly_receipt_json);
    assert_eq!(first.assembly_hash, second.assembly_hash);
    assert_eq!(
        first.generated_request.canonical_json(),
        second.generated_request.canonical_json()
    );
    assert_eq!(first.generated_request.request().order, 6);
    assert_eq!(first.assembly.active_dof_indices, vec![6, 7, 8, 9, 10, 11]);

    let product = runtime
        .execute_dense_spectral_product(&first.generated_request, None)
        .expect("native modal product");
    assert_eq!(product.result_ir.result().modes.len(), 3);
    assert!(product.result_ir.result().modes.iter().all(|mode| {
        matches!(
            mode,
            SpectralModeV1::Modal {
                eigenvalue_rad2_per_s2,
                residual_relative_inf,
                ..
            } if *eigenvalue_rad2_per_s2 > 0.0 && *residual_relative_inf <= 1e-9
        )
    }));
    let eigenvalues = product
        .result_ir
        .result()
        .modes
        .iter()
        .map(|mode| match mode {
            SpectralModeV1::Modal {
                eigenvalue_rad2_per_s2,
                ..
            } => *eigenvalue_rad2_per_s2,
            SpectralModeV1::LinearBuckling { .. } => panic!("modal adapter returned buckling"),
        })
        .collect::<Vec<_>>();
    for (actual, expected) in eigenvalues[..2].iter().zip([
        one_element_cantilever_bending_eigenvalue(5.0e-5),
        one_element_cantilever_bending_eigenvalue(8.0e-5),
    ]) {
        assert!((actual - expected).abs() / expected <= 5.0e-15);
    }
    assert_eq!(product.result_ir.result().backend_receipt.fallback_count, 0);
}

#[test]
fn identity_drift_and_excess_mode_request_fail_closed() {
    let model = model();
    let mut wrong = request(&model).request().clone();
    wrong.model_identity.content_hash = format!("sha256:{}", "0".repeat(64));
    let wrong = build_model_ir_modal_analysis_request_v1(wrong).expect("typed wrong identity");
    assert!(Runtime::new()
        .expect("runtime")
        .prepare_model_ir_modal_product(&model, &wrong)
        .is_err());

    let mut excessive = request(&model).request().clone();
    excessive.config.mode_count = 7;
    let excessive =
        build_model_ir_modal_analysis_request_v1(excessive).expect("typed excessive request");
    assert!(Runtime::new()
        .expect("runtime")
        .prepare_model_ir_modal_product(&model, &excessive)
        .is_err());
}
