use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::{
    parse_nonlinear_ndtha_report_ir_v1, parse_nonlinear_ndtha_result_ir_v1, sha256_identity,
};

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
            "structural-native-product-cli-test-{}-{sequence}",
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

fn run_cli(arguments: &[&Path]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
    command.env_clear();
    for argument in arguments {
        command.arg(argument);
    }
    command.output().expect("execute native CLI")
}

fn text(value: &str) -> &Path {
    Path::new(value)
}

fn verify_run_receipt(directory: &Path, expected_status: &str) {
    let bytes = std::fs::read(directory.join("run-receipt.json")).expect("run receipt bytes");
    let mut value: serde_json::Value = serde_json::from_slice(&bytes).expect("run receipt JSON");
    assert_eq!(value["status"], expected_status);
    let receipt_hash = value["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    value
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).expect("canonical unsigned receipt");
    assert_eq!(receipt_hash, sha256_identity(canonical.as_bytes()));
    for artifact in value["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let artifact_bytes = std::fs::read(directory.join(file)).expect("published artifact");
        assert_eq!(
            artifact["byte_length"].as_u64().expect("artifact length"),
            u64::try_from(artifact_bytes.len()).expect("bounded artifact length")
        );
        assert_eq!(
            artifact["content_hash"].as_str().expect("artifact hash"),
            sha256_identity(&artifact_bytes)
        );
    }
}

fn verify_frozen_terminal_artifacts(directory: &Path) {
    for (file, byte_length, hash) in [
        (
            "checkpoint.ndcp",
            661_usize,
            "sha256:dea34ac4c5fcb4dc0970d18d021c5b9cfae86dcb3498fe1151d93f428cdfb81d",
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
            1_678,
            "sha256:c5463cf386dc720ba44baa04cccf02be7b7365a550b1b9fc577480204928acac",
        ),
    ] {
        let bytes = std::fs::read(directory.join(file)).expect("frozen product artifact");
        assert_eq!(bytes.len(), byte_length, "artifact length drift: {file}");
        assert_eq!(sha256_identity(&bytes), hash, "artifact hash drift: {file}");
    }
    let result = parse_nonlinear_ndtha_result_ir_v1(
        &std::fs::read(directory.join("result-ir.json")).expect("direct ResultIR"),
    )
    .expect("valid direct ResultIR");
    let report = parse_nonlinear_ndtha_report_ir_v1(
        &std::fs::read(directory.join("report-ir.json")).expect("direct ReportIR"),
    )
    .expect("valid direct ReportIR");
    assert_eq!(report.report().source_result_hash, result.result_hash());
    assert_eq!(
        result.result_hash(),
        "sha256:c1b33678e4f3437c68cfc4cfee8d7a8678174bf84edb8c601f84c5290ca5157b"
    );
    assert_eq!(
        report.report_hash(),
        "sha256:5385ca3f47fa22289c0ec5416ab24c1f0f4ac8cb2670ddd1e22b1578af75a780"
    );
    assert_eq!(
        report.report().document_source_hash,
        sha256_identity(&std::fs::read(directory.join("report.md")).expect("report source"))
    );
}

#[test]
fn python_and_node_free_cli_run_resume_are_bitwise_identical() {
    let root = repository_root();
    let request = root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");
    let directory = TestDirectory::create();
    let direct = directory.0.join("direct");
    let partial = directory.0.join("partial");
    let resumed = directory.0.join("resumed");

    let output = run_cli(&[
        text("analysis"),
        text("run"),
        &request,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_run_receipt(&direct, "completed");
    verify_frozen_terminal_artifacts(&direct);

    let output = run_cli(&[
        text("analysis"),
        text("run"),
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
    verify_run_receipt(&partial, "checkpointed");
    assert!(partial.join("checkpoint.ndcp").is_file());
    assert!(!partial.join("result-ir.json").exists());
    assert!(!partial.join("report-ir.json").exists());

    let output = run_cli(&[
        text("analysis"),
        text("resume"),
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
    verify_run_receipt(&resumed, "completed");
    for file in [
        "checkpoint.ndcp",
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
fn tampered_checkpoint_and_existing_destination_fail_without_publication() {
    let root = repository_root();
    let request = root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");
    let directory = TestDirectory::create();
    let partial = directory.0.join("partial");
    let output = run_cli(&[
        text("analysis"),
        text("run"),
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
    std::fs::write(&corrupt, checkpoint).expect("corrupt checkpoint fixture");
    let rejected = directory.0.join("rejected");
    let output = run_cli(&[
        text("analysis"),
        text("resume"),
        &request,
        &corrupt,
        text("--output-dir"),
        &rejected,
    ]);
    assert!(!output.status.success());
    assert!(!rejected.exists());
    assert!(String::from_utf8_lossy(&output.stdout).contains("1301"));

    let existing = directory.0.join("existing");
    std::fs::create_dir(&existing).expect("existing destination");
    std::fs::write(existing.join("sentinel"), b"preserve").expect("sentinel");
    let output = run_cli(&[
        text("analysis"),
        text("run"),
        &request,
        text("--output-dir"),
        &existing,
    ]);
    assert!(!output.status.success());
    assert_eq!(
        std::fs::read(existing.join("sentinel")).expect("preserved sentinel"),
        b"preserve"
    );
}
