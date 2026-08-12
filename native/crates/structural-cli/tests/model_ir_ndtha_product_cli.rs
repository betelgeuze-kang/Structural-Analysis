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
            "structural-model-ir-product-cli-test-{}-{sequence}",
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

fn verify_receipt(directory: &Path, status: &str) {
    let bytes = std::fs::read(directory.join("run-receipt.json")).expect("receipt bytes");
    let mut value: serde_json::Value = serde_json::from_slice(&bytes).expect("receipt JSON");
    assert_eq!(value["status"], status);
    assert_eq!(value["derivation"]["fallback_count"], 0);
    assert_eq!(value["derivation"]["story_stiffness_n_per_m"], 50_000_000.0);
    let receipt_hash = value["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    value
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical receipt");
    assert_eq!(receipt_hash, sha256_identity(unsigned.as_bytes()));
    for artifact in value["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let artifact_bytes = std::fs::read(directory.join(file)).expect("artifact bytes");
        assert_eq!(
            artifact["content_hash"].as_str().expect("artifact hash"),
            sha256_identity(&artifact_bytes)
        );
    }
}

fn verify_frozen_terminal_artifacts(directory: &Path) {
    for (file, byte_length, content_hash) in [
        (
            "model-ir.json",
            2_808,
            "sha256:d0fa14472103a367cf33668f599f7ada56a5296e704d5e44ae5523484315ca2f",
        ),
        (
            "model-analysis-request.json",
            1_021,
            "sha256:adc6ffff10dba456e765c0b1f9061dee16f31bfd48935a9346c85e2ef55588f4",
        ),
        (
            "generated-request.json",
            706,
            "sha256:8a89e4cc96ce23c3cd452695bfc6dd0f3d4685d5b558f7ccf3743b40237ae164",
        ),
        (
            "checkpoint.ndcp",
            909,
            "sha256:3a6b2c6bc42373b1d8b146a16abe12129101ce777889d9876d6b0097eda075bc",
        ),
        (
            "native-run-receipt.json",
            1_678,
            "sha256:c5463cf386dc720ba44baa04cccf02be7b7365a550b1b9fc577480204928acac",
        ),
        (
            "result-ir.json",
            2_526,
            "sha256:f59193c725e236e4d824b9f2422befce5205050677489e6fc13bb8a31d580ceb",
        ),
        (
            "report-ir.json",
            1_234,
            "sha256:34e03d7176f41058322515dd461246e40a2f001434cc734654b53ce273b64a8a",
        ),
        (
            "report.md",
            819,
            "sha256:6b1e4d1ef0913f70f0818fdcfc8be7cadbda213d299bb48a2948a997ad3742a4",
        ),
        (
            "run-receipt.json",
            3_739,
            "sha256:be9eb70f90a42a867e4e621e1985e3246c28b33f02d02e84278b02c2cfde5f43",
        ),
    ] {
        let bytes = std::fs::read(directory.join(file)).expect("frozen artifact");
        assert_eq!(bytes.len(), byte_length, "artifact length drift: {file}");
        assert_eq!(
            sha256_identity(&bytes),
            content_hash,
            "artifact hash drift: {file}"
        );
    }
}

#[test]
fn clean_environment_model_run_resume_is_bitwise_identical() {
    let root = repository_root();
    let model = root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json");
    let request =
        root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json");
    let directory = TestDirectory::create();
    let direct = directory.0.join("direct");
    let partial = directory.0.join("partial");
    let resumed = directory.0.join("resumed");

    let output = run_cli(&[
        text("analysis"),
        text("model-run"),
        &model,
        &request,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&direct, "completed");
    verify_frozen_terminal_artifacts(&direct);

    let output = run_cli(&[
        text("analysis"),
        text("model-run"),
        &model,
        &request,
        text("--output-dir"),
        &partial,
        text("--step-budget"),
        text("2"),
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&partial, "checkpointed");
    assert!(!partial.join("result-ir.json").exists());

    let output = run_cli(&[
        text("analysis"),
        text("model-resume"),
        &model,
        &request,
        &partial.join("checkpoint.ndcp"),
        text("--output-dir"),
        &resumed,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&resumed, "completed");
    for file in [
        "model-ir.json",
        "model-analysis-request.json",
        "generated-request.json",
        "checkpoint.ndcp",
        "native-run-receipt.json",
        "result-ir.json",
        "report-ir.json",
        "report.md",
        "run-receipt.json",
    ] {
        assert_eq!(
            std::fs::read(direct.join(file)).expect("direct artifact"),
            std::fs::read(resumed.join(file)).expect("resumed artifact"),
            "artifact drift: {file}"
        );
    }
}

#[test]
fn model_identity_checkpoint_tamper_and_analysis_drift_publish_nothing() {
    let root = repository_root();
    let model = root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json");
    let request =
        root.join("native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json");
    let directory = TestDirectory::create();
    let partial = directory.0.join("partial");
    let output = run_cli(&[
        text("analysis"),
        text("model-run"),
        &model,
        &request,
        text("--output-dir"),
        &partial,
        text("--step-budget"),
        text("1"),
    ]);
    assert!(output.status.success());

    let mut checkpoint = std::fs::read(partial.join("checkpoint.ndcp")).expect("checkpoint");
    let last = checkpoint.len() - 1;
    checkpoint[last] ^= 1;
    let corrupt = directory.0.join("corrupt.ndcp");
    std::fs::write(&corrupt, checkpoint).expect("corrupt checkpoint");
    let rejected = directory.0.join("corrupt-output");
    let output = run_cli(&[
        text("analysis"),
        text("model-resume"),
        &model,
        &request,
        &corrupt,
        text("--output-dir"),
        &rejected,
    ]);
    assert!(!output.status.success());
    assert!(!rejected.exists());
    assert!(String::from_utf8_lossy(&output.stdout).contains("1301"));

    let mut changed: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&request).expect("request bytes"))
            .expect("request JSON");
    changed["damping_ratio"] = serde_json::json!(0.0003);
    let changed_path = directory.0.join("changed-request.json");
    std::fs::write(
        &changed_path,
        serde_json::to_vec(&changed).expect("changed request"),
    )
    .expect("write changed request");
    let drifted = directory.0.join("drifted-output");
    let output = run_cli(&[
        text("analysis"),
        text("model-resume"),
        &model,
        &changed_path,
        &partial.join("checkpoint.ndcp"),
        text("--output-dir"),
        &drifted,
    ]);
    assert!(!output.status.success());
    assert!(!drifted.exists());
    assert!(String::from_utf8_lossy(&output.stdout).contains("1301"));

    let mut wrong_identity = changed;
    wrong_identity["damping_ratio"] = serde_json::json!(0.00025);
    wrong_identity["model_identity"]["content_hash"] = serde_json::json!(
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    );
    let wrong_identity_path = directory.0.join("wrong-identity.json");
    std::fs::write(
        &wrong_identity_path,
        serde_json::to_vec(&wrong_identity).expect("wrong identity request"),
    )
    .expect("write wrong identity request");
    let identity_output = directory.0.join("identity-output");
    let output = run_cli(&[
        text("analysis"),
        text("model-run"),
        &model,
        &wrong_identity_path,
        text("--output-dir"),
        &identity_output,
    ]);
    assert!(!output.status.success());
    assert!(!identity_output.exists());

    #[cfg(unix)]
    {
        let symlink_model = directory.0.join("model-link.json");
        std::os::unix::fs::symlink(&model, &symlink_model).expect("model symlink");
        let symlink_output = directory.0.join("symlink-output");
        let output = run_cli(&[
            text("analysis"),
            text("model-run"),
            &symlink_model,
            &request,
            text("--output-dir"),
            &symlink_output,
        ]);
        assert!(!output.status.success());
        assert!(!symlink_output.exists());
    }
}
