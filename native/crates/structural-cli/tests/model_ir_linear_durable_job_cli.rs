use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
}

fn temporary_root(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-model-linear-job-cli-{label}-{}-{nanos}",
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

fn output_json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "CLI output is not JSON: {error}: {}",
            String::from_utf8_lossy(&output.stdout)
        )
    })
}

fn verify_export_receipt(directory: &Path, mut receipt: Value) {
    assert_eq!(receipt["analysis_profile"], "model_ir_linear_cpu_v1");
    assert_eq!(
        receipt["claim_boundary"],
        "single_host_bounded_cpu_model_ir_linear_durable_job_export_with_constrained_reactions_not_distributed_hip_or_release_authority"
    );
    let receipt_hash = receipt["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    receipt
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("canonical receipt");
    assert_eq!(receipt_hash, sha256_identity(unsigned.as_bytes()));
    let artifacts = receipt["artifacts"].as_array().expect("artifact list");
    assert_eq!(artifacts.len(), 6);
    for artifact in artifacts {
        let file = artifact["file"].as_str().expect("artifact file");
        let bytes = fs::read(directory.join(file)).expect("exported artifact");
        assert_eq!(
            artifact["byte_length"].as_u64().expect("artifact length"),
            u64::try_from(bytes.len()).expect("bounded artifact")
        );
        assert_eq!(
            artifact["content_hash"].as_str().expect("artifact hash"),
            sha256_identity(&bytes)
        );
    }
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_process_job_restart_and_export_match_direct_model_product() {
    let root = temporary_root("resume");
    fs::create_dir(&root).expect("root");
    let model =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let request = repository_root()
        .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let store = root.join("store");
    let direct = root.join("direct");
    let exported = root.join("exported");

    let submitted = run(&[
        text("job"),
        text("submit-model-linear"),
        &model,
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("cli-model-linear-resume"),
    ]);
    assert!(
        submitted.status.success(),
        "{}",
        String::from_utf8_lossy(&submitted.stdout)
    );
    let submitted_json = output_json(&submitted);
    let job_id = submitted_json["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();
    assert_eq!(
        submitted_json["job"]["analysis_profile"],
        "model_ir_linear_cpu_v1"
    );

    let partial = run(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("worker-first"),
        text("--lease-ms"),
        text("10000"),
        text("--step-budget"),
        text("1"),
    ]);
    assert!(partial.status.success());
    assert_eq!(output_json(&partial)["job"]["status"], "checkpointed");

    let resumed = run(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("worker-resume"),
    ]);
    assert!(
        resumed.status.success(),
        "{}",
        String::from_utf8_lossy(&resumed.stdout)
    );
    assert_eq!(output_json(&resumed)["job"]["status"], "succeeded");

    let export = run(&[
        text("job"),
        text("export"),
        Path::new(&job_id),
        text("--store"),
        &store,
        text("--output-dir"),
        &exported,
    ]);
    assert!(
        export.status.success(),
        "{}",
        String::from_utf8_lossy(&export.stdout)
    );
    verify_export_receipt(&exported, output_json(&export));

    let direct_run = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model,
        &request,
        text("--output-dir"),
        &direct,
    ]);
    assert!(direct_run.status.success());
    for (export_name, direct_name) in [
        ("checkpoint.mlpcp", "checkpoint.mlpcp"),
        ("result-ir.json", "result-ir.json"),
        ("result-recovery-ir.json", "result-recovery-ir.json"),
        ("reaction-result-ir.json", "reaction-result-ir.json"),
        ("report-ir.json", "report-ir.json"),
        ("report.md", "report.md"),
    ] {
        assert_eq!(
            fs::read(exported.join(export_name)).expect("exported artifact"),
            fs::read(direct.join(direct_name)).expect("direct artifact"),
            "artifact drift: {export_name}"
        );
    }
    assert!(exported.join("job-receipt.json").is_file());
    fs::remove_dir_all(root).expect("cleanup");
}

#[cfg(unix)]
#[test]
fn model_job_submit_rejects_symlink_input_without_store_creation() {
    let root = temporary_root("symlink");
    fs::create_dir(&root).expect("root");
    let model =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let request = repository_root()
        .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let model_link = root.join("model-link.json");
    std::os::unix::fs::symlink(&model, &model_link).expect("model symlink");
    let store = root.join("store");
    let output = run(&[
        text("job"),
        text("submit-model-linear"),
        &model_link,
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("symlink-rejected"),
    ]);
    assert!(!output.status.success());
    assert!(!store.exists());
    fs::remove_dir_all(root).expect("cleanup");
}
