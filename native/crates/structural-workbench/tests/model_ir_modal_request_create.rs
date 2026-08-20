use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use structural_cli::execute_model_ir_modal_analysis;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::model_modal_product::parse_model_ir_modal_analysis_request_v1;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::spectral_product::{
    parse_dense_spectral_result_ir_v1, SpectralGeneralizedEigenConfigV1,
};
use structural_workbench::create_model_modal_analysis_request;

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
        "structural-workbench-modal-request-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn config() -> SpectralGeneralizedEigenConfigV1 {
    SpectralGeneralizedEigenConfigV1 {
        mode_count: 3,
        maximum_sweeps: 4_096,
        symmetry_relative_tolerance: 1e-12,
        positive_semidefinite_relative_tolerance: 1e-12,
        mode_relative_tolerance: 1e-10,
        cluster_relative_tolerance: 1e-9,
        residual_relative_tolerance: 1e-9,
        orthogonality_tolerance: 1e-9,
        eigensolver_relative_tolerance: 1e-12,
    }
}

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let expected = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned
        .as_object_mut()
        .expect("self-hashed object")
        .remove(field);
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical unsigned value");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

#[test]
fn workbench_authors_preflighted_request_that_executes_without_rebinding() {
    let model = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("ModelIR fixture");
    let first =
        create_model_modal_analysis_request(&model, "frame-workbench-modal", "LC_WEAK", config())
            .expect("preflighted modal request");
    let second =
        create_model_modal_analysis_request(&model, "frame-workbench-modal", "LC_WEAK", config())
            .expect("repeat preflighted modal request");
    assert_eq!(first, second);

    let request = parse_model_ir_modal_analysis_request_v1(first.analysis_request_json.as_bytes())
        .expect("strict authored request");
    assert_eq!(request.request().config.mode_count, 3);
    let outcome = execute_model_ir_modal_analysis(&model, request.canonical_bytes())
        .expect("authored request execution");
    let result = parse_dense_spectral_result_ir_v1(outcome.result_ir_json().as_bytes())
        .expect("verified modal ResultIR");
    assert_eq!(result.result().summary.mode_count, 3);
    assert_eq!(result.result().backend_receipt.fallback_count, 0);

    let receipt: Value = serde_json::from_str(&first.receipt_json).expect("request receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-modal-request-create-receipt.v1"
    );
    assert_eq!(
        receipt["operation"],
        "create_model_ir_modal_analysis_request"
    );
    assert_eq!(receipt["active_dof_count"], 6);
    assert_eq!(receipt["load_vector_consumed_by_modal"], false);
    assert_eq!(receipt["cpp_semantic_snapshot_verified"], true);
    assert_eq!(receipt["cpp_active_k_m_assembly_preflight_verified"], true);
    assert_eq!(receipt["execution_started"], false);
    verify_self_hash(&receipt, "receipt_hash");

    let planar =
        fs::read(repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json"))
            .expect("planar fixture");
    assert!(create_model_modal_analysis_request(
        &planar,
        "unsupported-planar-modal",
        "LP1",
        config(),
    )
    .is_err());
}

#[test]
fn clean_environment_cli_publishes_byte_identical_request_and_receipt() {
    let root = temporary_root("cli");
    fs::create_dir_all(&root).expect("temporary root");
    let model =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let first = root.join("first");
    let second = root.join("second");
    for output in [&first, &second] {
        let execution = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
            .env_clear()
            .env("PATH", "/nonexistent")
            .args([
                "model-create-modal-analysis-request",
                model.to_str().expect("model path"),
                "--case",
                "frame-workbench-modal",
                "--assembly-load-pattern",
                "LC_WEAK",
                "--mode-count",
                "3",
                "--maximum-sweeps",
                "4096",
                "--symmetry-relative-tolerance",
                "1e-12",
                "--positive-semidefinite-relative-tolerance",
                "1e-12",
                "--mode-relative-tolerance",
                "1e-10",
                "--cluster-relative-tolerance",
                "1e-9",
                "--residual-relative-tolerance",
                "1e-9",
                "--orthogonality-tolerance",
                "1e-9",
                "--eigensolver-relative-tolerance",
                "1e-12",
                "--output-dir",
                output.to_str().expect("output path"),
            ])
            .output()
            .expect("execute structural-workbench");
        assert!(
            execution.status.success(),
            "stdout={} stderr={}",
            String::from_utf8_lossy(&execution.stdout),
            String::from_utf8_lossy(&execution.stderr)
        );
    }
    for file in ["analysis-request.json", "request-receipt.json"] {
        assert_eq!(
            fs::read(first.join(file)).expect("first artifact"),
            fs::read(second.join(file)).expect("second artifact")
        );
    }
    let _ = fs::remove_dir_all(root);
}
