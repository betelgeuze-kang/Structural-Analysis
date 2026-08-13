use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::execute_model_ir_linear_analysis;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{
    parse_sparse_linear_report_ir_v1, parse_sparse_linear_result_ir_v1,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-model-linear-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn run(arguments: &[&Path]) -> Output {
    let mut command = Command::new(binary());
    command.env_clear();
    command.env("PATH", "/nonexistent");
    for argument in arguments {
        command.arg(argument);
    }
    command.output().expect("run CLI")
}

fn text(value: &str) -> &Path {
    Path::new(value)
}

fn model_bytes() -> Vec<u8> {
    fs::read(repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"))
        .expect("ModelIR fixture")
}

fn request_bytes(max_iterations: u32) -> Vec<u8> {
    let bytes = fs::read(
        repository_root()
            .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"),
    )
    .expect("language-neutral request fixture");
    let mut value: Value = serde_json::from_slice(&bytes).expect("request fixture JSON");
    value["config"]["max_iterations"] = json!(max_iterations);
    serde_json::to_vec(&value).expect("request JSON")
}

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let hash = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned
        .as_object_mut()
        .expect("self-hashed object")
        .remove(field);
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical self-hash payload");
    assert_eq!(hash, sha256_identity(canonical.as_bytes()));
}

fn verify_receipt(directory: &Path, expected_status: &str) -> Value {
    let bytes = fs::read(directory.join("run-receipt.json")).expect("run receipt");
    let value: Value = serde_json::from_slice(&bytes).expect("run receipt JSON");
    assert_eq!(value["status"], expected_status);
    verify_self_hash(&value, "receipt_hash");
    for artifact in value["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let artifact_bytes = fs::read(directory.join(file)).expect("artifact bytes");
        assert_eq!(
            artifact["byte_length"].as_u64().expect("artifact length"),
            u64::try_from(artifact_bytes.len()).expect("bounded length")
        );
        assert_eq!(
            artifact["content_hash"].as_str().expect("artifact hash"),
            sha256_identity(&artifact_bytes)
        );
    }
    value
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_environment_direct_and_real_iteration_resume_are_byte_identical() {
    let root = temporary_root("clean-env");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(100)).expect("request");
    let direct = root.join("direct");
    let partial = root.join("partial");
    let resumed = root.join("resumed");

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let direct_receipt = verify_receipt(&direct, "completed");
    assert!(direct_receipt["checkpoint"]["artifact_bytes"]
        .as_u64()
        .is_some());

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &partial,
        text("--iteration-budget"),
        text("1"),
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&partial, "active");
    assert!(partial.join("checkpoint.mlpcp").is_file());
    assert!(partial.join("checkpoint.pcgcp").is_file());
    assert!(!partial.join("result-ir.json").exists());
    assert!(!partial.join("result-recovery-ir.json").exists());

    let output = run(&[
        text("analysis"),
        text("model-linear-resume"),
        &model_path,
        &request_path,
        &partial.join("checkpoint.mlpcp"),
        text("--output-dir"),
        &resumed,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&resumed, "completed");

    for name in [
        "model-ir.json",
        "model-analysis-request.json",
        "assembly-receipt.json",
        "generated-sparse-request.json",
        "checkpoint.mlpcp",
        "model-checkpoint-receipt.json",
        "checkpoint.pcgcp",
        "checkpoint-receipt.json",
        "sparse-run-receipt.json",
        "result-ir.json",
        "result-recovery-ir.json",
        "report-ir.json",
        "report.md",
        "run-receipt.json",
    ] {
        assert_eq!(
            fs::read(direct.join(name)).expect("direct artifact"),
            fs::read(resumed.join(name)).expect("resumed artifact"),
            "artifact drift: {name}"
        );
    }

    let result = parse_sparse_linear_result_ir_v1(
        &fs::read(direct.join("result-ir.json")).expect("ResultIR"),
    )
    .expect("strict ResultIR");
    let report = parse_sparse_linear_report_ir_v1(
        &fs::read(direct.join("report-ir.json")).expect("ReportIR"),
    )
    .expect("strict ReportIR");
    assert_eq!(report.report().source_result_hash, result.result_hash());
    assert_eq!(result.result().backend_receipt.fallback_count, 0);

    let assembly: Value = serde_json::from_slice(
        &fs::read(direct.join("assembly-receipt.json")).expect("assembly receipt"),
    )
    .expect("assembly receipt JSON");
    verify_self_hash(&assembly, "assembly_hash");
    assert_eq!(direct_receipt["assembly_hash"], assembly["assembly_hash"]);

    let recovery: Value = serde_json::from_slice(
        &fs::read(direct.join("result-recovery-ir.json")).expect("recovery"),
    )
    .expect("recovery JSON");
    verify_self_hash(&recovery, "recovery_hash");
    assert_eq!(recovery["source_result_hash"], result.result_hash());
    assert_eq!(recovery["active_dof_indices"], json!([6, 7, 8, 9, 10, 11]));
    assert_eq!(
        recovery["active_internal_force"],
        recovery["same_state_jvp"]
    );
    assert_eq!(recovery["fallback_count"], 0);
    assert_eq!(
        recovery["units"]["global_displacement"],
        "translations_m_rotations_rad"
    );
    assert_eq!(
        recovery["coordinate_frame"]["frame3d_recovery"],
        "element_local"
    );
    assert!(
        recovery["summary"]["active_residual_inf"]
            .as_f64()
            .expect("residual")
            <= 1.0e-8
    );
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn every_checkpoint_byte_and_request_drift_fail_before_resume() {
    let model = model_bytes();
    let request = request_bytes(100);
    let partial = execute_model_ir_linear_analysis(&model, &request, None, 1)
        .expect("one real PCG iteration");
    assert!(!partial.is_complete());
    assert_eq!(
        partial.checkpoint_receipt().schema_version,
        "structural-model-ir-linear-checkpoint-receipt.v1"
    );
    let checkpoint = partial.checkpoint_bytes();
    for index in 0..checkpoint.len() {
        let mut corrupt = checkpoint.to_vec();
        corrupt[index] ^= 1;
        let error = execute_model_ir_linear_analysis(&model, &request, Some(&corrupt), u32::MAX)
            .expect_err("every single-byte mutation fails");
        assert!(
            matches!(
                error,
                structural_cli::ModelIrLinearProductError::Runtime(ref value)
                    if value.code == 1301
            ),
            "mutation {index} returned {error}"
        );
    }

    let drifted = request_bytes(101);
    let error = execute_model_ir_linear_analysis(&model, &drifted, Some(checkpoint), u32::MAX)
        .expect_err("configuration drift fails");
    assert!(matches!(
        error,
        structural_cli::ModelIrLinearProductError::Runtime(ref value) if value.code == 1301
    ));
}

#[test]
fn numerical_failure_publishes_both_terminal_checkpoints_without_result_files() {
    let root = temporary_root("numerical-failure");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(1)).expect("request");
    let failed = root.join("failed");

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &failed,
    ]);
    assert!(!output.status.success());
    let receipt = verify_receipt(&failed, "failed");
    assert_eq!(receipt["solver_status"], "nonconvergence");
    assert!(failed.join("checkpoint.mlpcp").is_file());
    assert!(failed.join("checkpoint.pcgcp").is_file());
    assert!(!failed.join("result-ir.json").exists());
    assert!(!failed.join("result-recovery-ir.json").exists());
    assert!(!failed.join("report-ir.json").exists());
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn symlink_and_existing_destination_fail_without_partial_publication() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(100)).expect("request");
    let rejected = root.join("rejected");

    #[cfg(unix)]
    {
        let model_link = root.join("model-link.json");
        std::os::unix::fs::symlink(&model_path, &model_link).expect("model symlink");
        assert!(!run(&[
            text("analysis"),
            text("model-linear-run"),
            &model_link,
            &request_path,
            text("--output-dir"),
            &rejected,
        ])
        .status
        .success());
        assert!(!rejected.exists());
    }

    fs::create_dir(&rejected).expect("existing destination");
    fs::write(rejected.join("sentinel"), b"owned").expect("sentinel");
    assert!(!run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &rejected,
    ])
    .status
    .success());
    assert_eq!(
        fs::read(rejected.join("sentinel")).expect("sentinel"),
        b"owned"
    );
    fs::remove_dir_all(root).expect("cleanup");
}
