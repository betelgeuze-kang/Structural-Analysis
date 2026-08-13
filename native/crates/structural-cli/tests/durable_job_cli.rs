use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create() -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-native-durable-job-cli-test-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated test directory");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).expect("remove isolated test directory");
    }
}

fn text(value: &str) -> &Path {
    Path::new(value)
}

fn run_cli(arguments: &[&Path]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
    command.env_clear();
    for argument in arguments {
        command.arg(argument);
    }
    command.output().expect("execute native CLI")
}

fn successful_json(arguments: &[&Path]) -> serde_json::Value {
    let output = run_cli(arguments);
    assert!(
        output.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("CLI JSON")
}

fn verify_export_receipt(directory: &Path) {
    let bytes = std::fs::read(directory.join("job-receipt.json")).expect("job receipt");
    let mut receipt: serde_json::Value = serde_json::from_slice(&bytes).expect("receipt JSON");
    assert_eq!(receipt["status"], "succeeded");
    assert!(receipt.get("analysis_profile").is_none());
    assert_eq!(
        receipt["claim_boundary"],
        "single_host_bounded_cpu_nonlinear_ndtha_durable_job_export_not_distributed_service_hip_or_release_authority"
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
    for artifact in receipt["artifacts"].as_array().expect("artifact list") {
        let file = artifact["file"].as_str().expect("artifact file");
        let artifact_bytes = std::fs::read(directory.join(file)).expect("artifact bytes");
        assert_eq!(
            artifact["byte_length"].as_u64().expect("byte length"),
            u64::try_from(artifact_bytes.len()).expect("bounded artifact")
        );
        assert_eq!(
            artifact["content_hash"].as_str().expect("content hash"),
            sha256_identity(&artifact_bytes)
        );
    }
}

fn assert_export_matches_direct(request: &Path, exported: &Path, direct: &Path) {
    successful_json(&[
        text("analysis"),
        text("run"),
        request,
        text("--output-dir"),
        direct,
    ]);
    for file in [
        "checkpoint.ndcp",
        "result-ir.json",
        "report-ir.json",
        "report.md",
    ] {
        assert_eq!(
            std::fs::read(exported.join(file)).expect("durable artifact"),
            std::fs::read(direct.join(file)).expect("direct artifact"),
            "durable/direct drift: {file}"
        );
    }
}

#[test]
fn clean_environment_submit_poll_checkpoint_resume_and_export_match_direct_run() {
    let directory = TestDirectory::create();
    let store = directory.0.join("store");
    let exported = directory.0.join("exported");
    let direct = directory.0.join("direct");
    let request =
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");

    let submitted = successful_json(&[
        text("job"),
        text("submit"),
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("cli-resume-e2e"),
    ]);
    let job_id = submitted["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();
    assert_eq!(submitted["job"]["status"], "queued");
    assert!(submitted["job"].get("analysis_profile").is_none());
    assert!(submitted["job"].get("result_recovery_ir").is_none());

    let duplicate = successful_json(&[
        text("job"),
        text("submit"),
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("cli-resume-e2e"),
    ]);
    assert_eq!(duplicate["job"]["job_id"], job_id);
    assert_eq!(duplicate["job"]["revision"], 0);

    let checkpointed = successful_json(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("cli-worker-first"),
        text("--step-budget"),
        text("2"),
    ]);
    assert_eq!(checkpointed["job"]["status"], "checkpointed");
    assert_eq!(checkpointed["job"]["progress_completed"], 2);

    let reopened = successful_json(&[
        text("job"),
        text("poll"),
        Path::new(&job_id),
        text("--store"),
        &store,
    ]);
    assert_eq!(reopened["job"], checkpointed["job"]);

    let succeeded = successful_json(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("cli-worker-resume"),
    ]);
    assert_eq!(succeeded["job"]["status"], "succeeded");
    assert_eq!(succeeded["job"]["attempt"], 2);
    assert_eq!(succeeded["job"]["progress_completed"], 5);

    let receipt = successful_json(&[
        text("job"),
        text("export"),
        Path::new(&job_id),
        text("--store"),
        &store,
        text("--output-dir"),
        &exported,
    ]);
    assert_eq!(receipt["job_id"], job_id);
    verify_export_receipt(&exported);

    assert_export_matches_direct(&request, &exported, &direct);

    let idle = successful_json(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("cli-worker-idle"),
    ]);
    assert_eq!(idle["status"], "idle");
}

#[test]
fn public_cancel_is_terminal_and_cannot_be_claimed() {
    let directory = TestDirectory::create();
    let store = directory.0.join("store");
    let request =
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");
    let submitted = successful_json(&[
        text("job"),
        text("submit"),
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("cli-cancel-e2e"),
    ]);
    let job_id = submitted["job"]["job_id"].as_str().expect("job id");
    let cancelled = successful_json(&[
        text("job"),
        text("cancel"),
        Path::new(job_id),
        text("--store"),
        &store,
    ]);
    assert_eq!(cancelled["job"]["status"], "cancelled");
    let idle = successful_json(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("cli-worker-after-cancel"),
    ]);
    assert_eq!(idle["status"], "idle");
}
