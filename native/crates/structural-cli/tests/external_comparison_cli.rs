use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::external_comparison::{
    parse_external_comparison_ir_v1, ExternalComparisonStatusV1,
};
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
            "structural-native-comparison-cli-test-{}-{sequence}",
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

fn build_result(directory: &Path) -> PathBuf {
    let request =
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");
    let output = run_cli(&[
        text("analysis"),
        text("run"),
        &request,
        text("--output-dir"),
        directory,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    directory.join("result-ir.json")
}

fn build_model_linear_result(directory: &Path) -> (PathBuf, PathBuf) {
    let root = repository_root();
    let model = root.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let request =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    build_model_linear_result_from(&model, &request, directory)
}

fn build_model_linear_result_from(
    model: &Path,
    request: &Path,
    directory: &Path,
) -> (PathBuf, PathBuf) {
    let output = run_cli(&[
        text("analysis"),
        text("model-linear-run"),
        model,
        request,
        text("--output-dir"),
        directory,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    (
        directory.join("result-ir.json"),
        directory.join("result-recovery-ir.json"),
    )
}

fn verify_receipt(directory: &Path, expected_status: &str) {
    let receipt_bytes =
        std::fs::read(directory.join("comparison-receipt.json")).expect("comparison receipt");
    let mut receipt: Value = serde_json::from_slice(&receipt_bytes).expect("receipt JSON");
    assert_eq!(receipt["status"], expected_status);
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
    let artifact = &receipt["artifacts"][0];
    let comparison_bytes =
        std::fs::read(directory.join("external-comparison-ir.json")).expect("comparison IR");
    assert_eq!(
        artifact["byte_length"].as_u64().expect("artifact length"),
        u64::try_from(comparison_bytes.len()).expect("bounded artifact length")
    );
    assert_eq!(
        artifact["content_hash"].as_str().expect("artifact hash"),
        sha256_identity(&comparison_bytes)
    );
}

#[test]
fn python_and_node_free_external_comparison_is_deterministic() {
    let root = repository_root();
    let external =
        root.join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json");
    let source = root
        .join("native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json");
    let temporary = TestDirectory::create();
    let result = build_result(&temporary.0.join("analysis"));
    let first = temporary.0.join("comparison-first");
    let second = temporary.0.join("comparison-second");

    for output_directory in [&first, &second] {
        let output = run_cli(&[
            text("comparison"),
            text("run"),
            &result,
            &external,
            &source,
            text("--output-dir"),
            output_directory,
            text("--require-pass"),
        ]);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        verify_receipt(output_directory, "passed");
        let comparison = parse_external_comparison_ir_v1(
            &std::fs::read(output_directory.join("external-comparison-ir.json"))
                .expect("comparison bytes"),
        )
        .expect("strict comparison IR");
        assert_eq!(
            comparison.comparison().status,
            ExternalComparisonStatusV1::Passed
        );
        assert_eq!(
            comparison.comparison().source_result_hash,
            "sha256:c1b33678e4f3437c68cfc4cfee8d7a8678174bf84edb8c601f84c5290ca5157b"
        );
        assert_eq!(
            comparison.comparison().source.source_artifact_hash,
            "sha256:5872c8a89cf055096339a0e4a39b776ebf4af3060b3417ff4e9569d3de7916b5"
        );
    }
    for file in ["external-comparison-ir.json", "comparison-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(file)).expect("first artifact"),
            std::fs::read(second.join(file)).expect("second artifact"),
            "comparison artifact drift: {file}"
        );
    }
    for (file, length, hash) in [
        (
            "external-comparison-ir.json",
            2_608_usize,
            "sha256:600832e15cc055a418255a96948db8faef4a9db644318d951666b783dde6c545",
        ),
        (
            "comparison-receipt.json",
            968_usize,
            "sha256:d11919d16d28ce91541bd8c0abd0ccc03d1ecd847be7e926db86020c7b6b3727",
        ),
    ] {
        let bytes = std::fs::read(first.join(file)).expect("frozen comparison artifact");
        assert_eq!(bytes.len(), length, "comparison length drift: {file}");
        assert_eq!(
            sha256_identity(&bytes),
            hash,
            "comparison hash drift: {file}"
        );
    }
}

#[test]
fn model_linear_comparison_cli_binds_result_and_recovery() {
    let root = repository_root();
    let external =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json");
    let source = root.join(
        "native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt",
    );
    let temporary = TestDirectory::create();
    let (result, recovery) = build_model_linear_result(&temporary.0.join("linear-analysis"));
    let comparison = temporary.0.join("linear-comparison");
    let output = run_cli(&[
        text("comparison"),
        text("model-linear"),
        &result,
        &recovery,
        &external,
        &source,
        text("--output-dir"),
        &comparison,
        text("--require-pass"),
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&comparison, "passed");
    let comparison_ir = std::fs::read_to_string(comparison.join("external-comparison-ir.json"))
        .expect("model-linear comparison IR");
    assert!(comparison_ir.contains("structural-model-ir-linear-external-comparison-ir.v1"));
    assert!(comparison_ir.contains("\"source_recovery_hash\""));
}

#[test]
fn model_linear_require_pass_publishes_divergence_without_promoting_it() {
    let root = repository_root();
    let fixture =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json");
    let source = root.join(
        "native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt",
    );
    let temporary = TestDirectory::create();
    let (result, recovery) = build_model_linear_result(&temporary.0.join("linear-analysis"));
    let mut external: Value =
        serde_json::from_slice(&std::fs::read(fixture).expect("linear external fixture"))
            .expect("linear external JSON");
    external["observations"][0]["value"] = json!(0.125);
    let divergent = temporary.0.join("linear-divergent.json");
    std::fs::write(
        &divergent,
        serde_json::to_vec(&external).expect("divergent linear JSON"),
    )
    .expect("write divergent linear input");
    let output_directory = temporary.0.join("linear-diverged");
    let output = run_cli(&[
        text("comparison"),
        text("model-linear"),
        &result,
        &recovery,
        &divergent,
        &source,
        text("--output-dir"),
        &output_directory,
        text("--require-pass"),
    ]);
    assert_eq!(output.status.code(), Some(2));
    verify_receipt(&output_directory, "diverged");
    let comparison: Value = serde_json::from_slice(
        &std::fs::read(output_directory.join("external-comparison-ir.json"))
            .expect("diverged linear comparison"),
    )
    .expect("diverged linear comparison JSON");
    assert_eq!(comparison["status"], "diverged");
    assert_eq!(comparison["rows"][0]["within_tolerance"], false);
}

#[test]
fn model_linear_cross_bound_recovery_and_symlink_publish_nothing() {
    let root = repository_root();
    let external =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json");
    let source = root.join(
        "native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt",
    );
    let temporary = TestDirectory::create();
    let (result, recovery) = build_model_linear_result(&temporary.0.join("weak-analysis"));
    let axial_model =
        root.join("native/examples/frame3d-linear-cantilever/model-calculix-axial.json");
    let axial_request =
        root.join("native/examples/frame3d-linear-cantilever/analysis-request-axial.json");
    let (_, axial_recovery) = build_model_linear_result_from(
        &axial_model,
        &axial_request,
        &temporary.0.join("axial-analysis"),
    );
    let cross_bound_output = temporary.0.join("cross-bound-output");
    let output = run_cli(&[
        text("comparison"),
        text("model-linear"),
        &result,
        &axial_recovery,
        &external,
        &source,
        text("--output-dir"),
        &cross_bound_output,
    ]);
    assert_eq!(output.status.code(), Some(2));
    assert!(!cross_bound_output.exists());
    assert!(String::from_utf8_lossy(&output.stdout)
        .contains("model_ir_linear_recovery_result_binding_mismatch"));

    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;

        let linked_recovery = temporary.0.join("recovery-link.json");
        symlink(&recovery, &linked_recovery).expect("create recovery symlink");
        let linked_output = temporary.0.join("linked-linear-output");
        let output = run_cli(&[
            text("comparison"),
            text("model-linear"),
            &result,
            &linked_recovery,
            &external,
            &source,
            text("--output-dir"),
            &linked_output,
        ]);
        assert_eq!(output.status.code(), Some(1));
        assert!(!linked_output.exists());
        assert!(String::from_utf8_lossy(&output.stdout).contains("recovery_ir_read_error"));
        assert!(String::from_utf8_lossy(&output.stdout).contains("non-symlink"));
    }
}

#[test]
fn require_pass_surfaces_divergence_after_publishing_evidence() {
    let root = repository_root();
    let source = root
        .join("native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json");
    let temporary = TestDirectory::create();
    let result = build_result(&temporary.0.join("analysis"));
    let fixture =
        root.join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json");
    let mut external: Value =
        serde_json::from_slice(&std::fs::read(fixture).expect("external fixture"))
            .expect("external JSON");
    external["observations"][0]["value"] = json!(1.0);
    let divergent = temporary.0.join("divergent.json");
    std::fs::write(
        &divergent,
        serde_json::to_vec(&external).expect("divergent JSON"),
    )
    .expect("write divergent input");
    let output_directory = temporary.0.join("diverged");
    let output = run_cli(&[
        text("comparison"),
        text("run"),
        &result,
        &divergent,
        &source,
        text("--output-dir"),
        &output_directory,
        text("--require-pass"),
    ]);
    assert_eq!(output.status.code(), Some(2));
    verify_receipt(&output_directory, "diverged");
    let comparison = parse_external_comparison_ir_v1(
        &std::fs::read(output_directory.join("external-comparison-ir.json"))
            .expect("divergent comparison"),
    )
    .expect("valid divergent artifact");
    assert_eq!(
        comparison.comparison().status,
        ExternalComparisonStatusV1::Diverged
    );
}

#[test]
fn artifact_hash_mismatch_and_symlink_input_publish_nothing() {
    let root = repository_root();
    let external =
        root.join("native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json");
    let wrong_source = root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json");
    let temporary = TestDirectory::create();
    let result = build_result(&temporary.0.join("analysis"));
    let rejected = temporary.0.join("rejected");
    let output = run_cli(&[
        text("comparison"),
        text("run"),
        &result,
        &external,
        &wrong_source,
        text("--output-dir"),
        &rejected,
    ]);
    assert_eq!(output.status.code(), Some(2));
    assert!(!rejected.exists());
    assert!(
        String::from_utf8_lossy(&output.stdout).contains("external_source_artifact_hash_mismatch")
    );

    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;

        let source = root.join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        );
        let linked = temporary.0.join("source-link.json");
        symlink(source, &linked).expect("create input symlink");
        let linked_output = temporary.0.join("linked-output");
        let output = run_cli(&[
            text("comparison"),
            text("run"),
            &result,
            &external,
            &linked,
            text("--output-dir"),
            &linked_output,
        ]);
        assert_eq!(output.status.code(), Some(1));
        assert!(!linked_output.exists());
        assert!(String::from_utf8_lossy(&output.stdout).contains("non-symlink"));
    }
}
