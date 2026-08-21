use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::{
    execute_model_ir_linear_buckling_analysis,
    execute_model_ir_linear_buckling_analysis_with_checkpoint,
    publish_model_ir_linear_buckling_analysis,
};
use structural_contracts::model_buckling_product::{
    build_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
    ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
};
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::sparse_product::SparseLinearConfigV1;
use structural_contracts::spectral_product::{
    parse_dense_spectral_result_ir_v1, SpectralGeneralizedEigenConfigV1, SpectralModeV1,
};
use structural_runtime::{
    ModelIrLinearBucklingCheckpointBindingsV1, ModelIrLinearBucklingCheckpointV1,
};

const PRODUCT_FILES: [&str; 18] = [
    "buckling-assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mbcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "generated-reference-request.json",
    "model-buckling-request.json",
    "model-ir.json",
    "reference-assembly-receipt.json",
    "reference-checkpoint.mlpcp",
    "reference-checkpoint.pcgcp",
    "reference-reaction-ir.json",
    "reference-recovery-ir.json",
    "reference-result-ir.json",
    "report-ir.json",
    "report.md",
    "result-ir.json",
    "run-receipt.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-model-buckling-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn compression_model() -> structural_contracts::model_ir::ModelIrV2Document {
    let source = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("fixture");
    let source = parse_model_ir_v2(&source).expect("strict source");
    let mut value = source.value().clone();
    value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(-100_000.0);
    parse_model_ir_v2(&serde_json::to_vec(&value).expect("compression JSON"))
        .expect("strict compression model")
}

fn request(
    model: &structural_contracts::model_ir::ModelIrV2Document,
) -> structural_contracts::model_buckling_product::ModelIrLinearBucklingAnalysisRequestDocumentV1 {
    build_model_ir_linear_buckling_analysis_request_v1(ModelIrLinearBucklingAnalysisRequestV1 {
        schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_linear_buckling".to_owned(),
        case_id: "frame-cantilever-buckling".to_owned(),
        backend: ModelIrLinearBucklingBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: model.content_hash().to_owned(),
            semantic_hash: model.semantic_hash().to_owned(),
            provenance_hash: model.provenance_hash().to_owned(),
        },
        reference_load_pattern_id: "LC_AXIAL".to_owned(),
        reference_linear_config: SparseLinearConfigV1 {
            max_iterations: 64,
            absolute_residual_tolerance: 1e-12,
            relative_residual_tolerance: 1e-12,
            maximum_increment: 0.0,
        },
        buckling_config: SpectralGeneralizedEigenConfigV1 {
            mode_count: 2,
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
    .expect("buckling request")
}

fn one_element_cantilever_factor(second_moment_m4: f64) -> f64 {
    let elastic_modulus_pa = 200.0e9;
    let length_m = 2.0_f64;
    let compression_n = 100_000.0;
    let ei = elastic_modulus_pa * second_moment_m4;
    let k11 = 12.0 * ei / length_m.powi(3);
    let k12 = -6.0 * ei / length_m.powi(2);
    let k22 = 4.0 * ei / length_m;
    let scale = compression_n / (30.0 * length_m);
    let g11 = 36.0 * scale;
    let g12 = -3.0 * length_m * scale;
    let g22 = 4.0 * length_m.powi(2) * scale;
    let quadratic = g11 * g22 - g12 * g12;
    let linear = -(k11 * g22 + k22 * g11 - 2.0 * k12 * g12);
    let constant = k11 * k22 - k12 * k12;
    let discriminant = linear * linear - 4.0 * quadratic * constant;
    (-linear - discriminant.sqrt()) / (2.0 * quadratic)
}

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let expected = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned
        .as_object_mut()
        .expect("self-hashed object")
        .remove(field);
    let canonical = structural_contracts::model_ir::canonicalize_model_ir_v2(&unsigned)
        .expect("canonical unsigned value");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

#[test]
fn reference_equilibrium_to_buckling_product_is_independent_restartable_and_bound() {
    let root = temporary_root("product");
    fs::create_dir_all(&root).expect("temporary root");
    let model = compression_model();
    let request = request(&model);
    let first = execute_model_ir_linear_buckling_analysis(
        model.canonical_bytes(),
        request.canonical_bytes(),
    )
    .expect("first product");
    let second = execute_model_ir_linear_buckling_analysis(
        model.canonical_bytes(),
        request.canonical_bytes(),
    )
    .expect("repeat product");
    let resumed = execute_model_ir_linear_buckling_analysis_with_checkpoint(
        model.canonical_bytes(),
        request.canonical_bytes(),
        Some(first.checkpoint_bytes()),
    )
    .expect("resumed product");
    let first_dir = root.join("first");
    let second_dir = root.join("second");
    let resumed_dir = root.join("resumed");
    publish_model_ir_linear_buckling_analysis(&first_dir, &first).expect("first publication");
    publish_model_ir_linear_buckling_analysis(&second_dir, &second).expect("second publication");
    publish_model_ir_linear_buckling_analysis(&resumed_dir, &resumed).expect("resumed publication");

    for file in PRODUCT_FILES {
        let first_bytes = fs::read(first_dir.join(file)).expect("first artifact");
        assert_eq!(
            first_bytes,
            fs::read(second_dir.join(file)).expect("repeat artifact"),
            "repeat artifact drifted: {file}"
        );
        assert_eq!(
            first_bytes,
            fs::read(resumed_dir.join(file)).expect("resumed artifact"),
            "resumed artifact drifted: {file}"
        );
    }

    let result = parse_dense_spectral_result_ir_v1(
        &fs::read(first_dir.join("result-ir.json")).expect("result"),
    )
    .expect("verified buckling ResultIR");
    let actual = result
        .result()
        .modes
        .iter()
        .map(|mode| match mode {
            SpectralModeV1::LinearBuckling {
                load_factor,
                residual_relative_inf,
                ..
            } => {
                assert!(*residual_relative_inf <= 1e-9);
                *load_factor
            }
            SpectralModeV1::Modal { .. } => panic!("buckling product returned modal mode"),
        })
        .collect::<Vec<_>>();
    let mut expected = vec![
        one_element_cantilever_factor(5.0e-5),
        one_element_cantilever_factor(8.0e-5),
    ];
    expected.sort_by(f64::total_cmp);
    for (actual, expected) in actual.iter().zip(expected) {
        assert!((actual - expected).abs() / expected <= 5e-14);
    }
    assert_eq!(result.result().backend_receipt.fallback_count, 0);

    let recovery: Value = serde_json::from_slice(
        &fs::read(first_dir.join("reference-recovery-ir.json")).expect("recovery"),
    )
    .expect("recovery JSON");
    assert_eq!(recovery["global_displacement"][6], -0.000_05);
    assert_eq!(recovery["summary"]["active_residual_inf"], 0.0);
    let assembly: Value = serde_json::from_slice(
        &fs::read(first_dir.join("buckling-assembly-receipt.json")).expect("assembly"),
    )
    .expect("assembly JSON");
    assert_eq!(assembly["frame_axial_compression_n"][0], 100_000.0);
    assert_eq!(assembly["reference_equilibrium_residual_inf_n"], 0.0);

    let receipt: Value =
        serde_json::from_slice(&fs::read(first_dir.join("run-receipt.json")).expect("run receipt"))
            .expect("run receipt JSON");
    assert_eq!(receipt["status"], "completed");
    assert_eq!(receipt["fallback_count"], 0);
    verify_self_hash(&receipt, "receipt_hash");
    for artifact in receipt["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let bytes = fs::read(first_dir.join(file)).expect("bound artifact");
        assert_eq!(artifact["content_hash"], sha256_identity(&bytes));
        assert_eq!(artifact["byte_length"], bytes.len());
    }

    let _ = fs::remove_dir_all(root);
}

#[test]
fn checkpoint_tamper_and_tension_fail_closed_without_publication() {
    let model = compression_model();
    let direct_request = request(&model);
    let direct = execute_model_ir_linear_buckling_analysis(
        model.canonical_bytes(),
        direct_request.canonical_bytes(),
    )
    .expect("direct product");
    let mut tampered = direct.checkpoint_bytes().to_vec();
    *tampered.last_mut().expect("checkpoint byte") ^= 1;
    assert!(execute_model_ir_linear_buckling_analysis_with_checkpoint(
        model.canonical_bytes(),
        direct_request.canonical_bytes(),
        Some(&tampered),
    )
    .is_err());

    let mut tension_value = model.value().clone();
    tension_value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(100_000.0);
    let tension = parse_model_ir_v2(&serde_json::to_vec(&tension_value).expect("tension JSON"))
        .expect("strict tension model");
    let tension_request = request(&tension);
    assert!(execute_model_ir_linear_buckling_analysis(
        tension.canonical_bytes(),
        tension_request.canonical_bytes(),
    )
    .is_err());
}

#[test]
fn every_aggregate_checkpoint_byte_and_derivation_binding_fail_closed() {
    let model = compression_model();
    let request = request(&model);
    let outcome = execute_model_ir_linear_buckling_analysis(
        model.canonical_bytes(),
        request.canonical_bytes(),
    )
    .expect("direct product");
    let receipt = outcome.checkpoint_receipt();
    let bindings = ModelIrLinearBucklingCheckpointBindingsV1 {
        model_content_hash: receipt.model_content_hash.clone(),
        model_semantic_hash: receipt.model_semantic_hash.clone(),
        model_provenance_hash: receipt.model_provenance_hash.clone(),
        analysis_request_hash: receipt.analysis_request_hash.clone(),
        generated_reference_request_hash: receipt.generated_reference_request_hash.clone(),
        reference_assembly_hash: receipt.reference_assembly_hash.clone(),
        buckling_assembly_hash: receipt.buckling_assembly_hash.clone(),
        generated_spectral_request_hash: receipt.generated_spectral_request_hash.clone(),
        reference_result_hash: receipt.reference_result_hash.clone(),
        reference_recovery_hash: receipt.reference_recovery_hash.clone(),
    };
    let checkpoint = ModelIrLinearBucklingCheckpointV1::from_bytes(outcome.checkpoint_bytes())
        .expect("aggregate checkpoint");
    checkpoint.verify_bindings(&bindings).expect("bindings");
    assert_eq!(checkpoint.receipt(), *receipt);

    for index in 0..outcome.checkpoint_bytes().len() {
        let mut corrupt = outcome.checkpoint_bytes().to_vec();
        corrupt[index] ^= 1;
        assert_eq!(
            ModelIrLinearBucklingCheckpointV1::from_bytes(&corrupt)
                .expect_err("every mutation must fail")
                .code,
            1301,
            "wrong taxonomy at byte {index}"
        );
    }

    for field in 0..10 {
        let mut drift = bindings.clone();
        let value = sha256_identity(format!("drift-{field}").as_bytes());
        match field {
            0 => drift.model_content_hash = value,
            1 => drift.model_semantic_hash = value,
            2 => drift.model_provenance_hash = value,
            3 => drift.analysis_request_hash = value,
            4 => drift.generated_reference_request_hash = value,
            5 => drift.reference_assembly_hash = value,
            6 => drift.buckling_assembly_hash = value,
            7 => drift.generated_spectral_request_hash = value,
            8 => drift.reference_result_hash = value,
            9 => drift.reference_recovery_hash = value,
            _ => unreachable!(),
        }
        assert_eq!(
            checkpoint
                .verify_bindings(&drift)
                .expect_err("binding drift must fail")
                .code,
            1301
        );
    }
}

#[test]
fn cli_run_and_resume_are_python_node_free_and_byte_identical() {
    let root = temporary_root("cli");
    fs::create_dir_all(&root).expect("temporary root");
    let model = compression_model();
    let request = request(&model);
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    fs::write(&model_path, model.canonical_bytes()).expect("model file");
    fs::write(&request_path, request.canonical_bytes()).expect("request file");
    let direct = root.join("direct");
    let resumed = root.join("resumed");

    let execution = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "analysis",
            "model-buckling-run",
            model_path.to_str().expect("model path"),
            request_path.to_str().expect("request path"),
            "--output-dir",
            direct.to_str().expect("direct path"),
        ])
        .output()
        .expect("run structural-cli");
    assert!(
        execution.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&execution.stdout),
        String::from_utf8_lossy(&execution.stderr)
    );
    let run_stdout: Value = serde_json::from_slice(&execution.stdout).expect("run stdout receipt");
    assert_eq!(run_stdout["status"], "completed");

    let resume = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "analysis",
            "model-buckling-resume",
            model_path.to_str().expect("model path"),
            request_path.to_str().expect("request path"),
            direct
                .join("checkpoint.mbcp")
                .to_str()
                .expect("checkpoint path"),
            "--output-dir",
            resumed.to_str().expect("resumed path"),
        ])
        .output()
        .expect("resume structural-cli");
    assert!(
        resume.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&resume.stdout),
        String::from_utf8_lossy(&resume.stderr)
    );
    assert_eq!(execution.stdout, resume.stdout);
    for file in PRODUCT_FILES {
        assert_eq!(
            fs::read(direct.join(file)).expect("direct artifact"),
            fs::read(resumed.join(file)).expect("resumed artifact"),
            "CLI resume artifact drifted: {file}"
        );
    }

    let _ = fs::remove_dir_all(root);
}
