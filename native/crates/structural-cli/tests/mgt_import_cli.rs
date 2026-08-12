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
            "structural-mgt-import-cli-test-{}-{sequence}",
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

fn verify_receipt(directory: &Path, expected_status: &str) {
    let bytes = std::fs::read(directory.join("import-receipt.json")).expect("receipt bytes");
    let mut value: serde_json::Value = serde_json::from_slice(&bytes).expect("receipt JSON");
    assert_eq!(value["status"], expected_status);
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

fn verify_frozen_exact(directory: &Path) {
    for (file, length, hash) in [
        (
            "source.mgt",
            336,
            "sha256:8316dbf1f9563a3239b303456970b827f5fc834a1d3d4aab84d7486e9a80d9f5",
        ),
        (
            "import-health.json",
            3_648,
            "sha256:2b9cfc5fd295e73e9339699251260d453b5bc912283429ab6a0be1f767550240",
        ),
        (
            "model-ir.json",
            4_343,
            "sha256:37740f33001eeae02a616a4f7c368ea2f6796d3db1e8a637bdd9c164430d2851",
        ),
        (
            "native-validation.json",
            983,
            "sha256:92902b0e3bd69aa4bfb44af4134ec7d3d65438d3605cc4a68fc8b7b9f0c29840",
        ),
        (
            "native-snapshot.json",
            4_343,
            "sha256:37740f33001eeae02a616a4f7c368ea2f6796d3db1e8a637bdd9c164430d2851",
        ),
        (
            "import-receipt.json",
            1_833,
            "sha256:2ff7dd4c8ef618d7e46c9284daee4ffaad68149cd03bf2cf308d614e3c542c9d",
        ),
    ] {
        let bytes = std::fs::read(directory.join(file)).expect("frozen exact artifact");
        assert_eq!(bytes.len(), length, "artifact length drift: {file}");
        assert_eq!(sha256_identity(&bytes), hash, "artifact hash drift: {file}");
    }
}

#[test]
fn clean_environment_exact_import_is_cpp_validated_and_deterministic() {
    let root = repository_root();
    let source = root.join("native/tests/fixtures/mgt_import/fixed_guided_frame3d_x.mgt");
    let directory = TestDirectory::create();
    let first = directory.0.join("first");
    let second = directory.0.join("second");
    for output_directory in [&first, &second] {
        let output = run_cli(&[
            text("import"),
            text("mgt"),
            &source,
            text("--model-id"),
            text("mgt-fixed-guided-v1"),
            text("--output-dir"),
            output_directory,
            text("--require-normalized"),
        ]);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        verify_receipt(output_directory, "normalized");
    }
    verify_frozen_exact(&first);
    for file in [
        "source.mgt",
        "import-health.json",
        "model-ir.json",
        "native-validation.json",
        "native-snapshot.json",
        "import-receipt.json",
    ] {
        assert_eq!(
            std::fs::read(first.join(file)).expect("first artifact"),
            std::fs::read(second.join(file)).expect("second artifact"),
            "artifact drift: {file}"
        );
    }
    let report: serde_json::Value = serde_json::from_slice(
        &std::fs::read(first.join("native-validation.json")).expect("native report"),
    )
    .expect("native report JSON");
    assert_eq!(report["contract_valid"], true);
    assert_eq!(report["analysis_ready"], true);
    assert_eq!(
        std::fs::read(first.join("model-ir.json")).expect("ModelIR"),
        std::fs::read(first.join("native-snapshot.json")).expect("C++ snapshot")
    );
}

#[test]
fn existing_fixture_blockers_policy_symlink_and_existing_output_fail_closed() {
    let root = repository_root();
    let source = root.join("tests/fixtures/foundation_realish/foundation_small.mgt");
    let directory = TestDirectory::create();
    let health = directory.0.join("health");
    let output = run_cli(&[
        text("import"),
        text("mgt"),
        &source,
        text("--model-id"),
        text("foundation-small-health-v1"),
        text("--output-dir"),
        &health,
    ]);
    assert!(output.status.success());
    verify_receipt(&health, "blocked");
    assert!(health.join("source.mgt").exists());
    assert!(health.join("import-health.json").exists());
    assert!(!health.join("model-ir.json").exists());
    assert_eq!(
        std::fs::read(&source).expect("source"),
        std::fs::read(health.join("source.mgt")).expect("owned source")
    );
    for (file, length, hash) in [
        (
            "source.mgt",
            454,
            "sha256:b5bbe7b31a74ee098e4c3b5ea4a62b59ec5a14e8754ba441c538bf1cc451c813",
        ),
        (
            "import-health.json",
            7_634,
            "sha256:187f75f1389bc56f7d48f36c455e6730f88acc6f7cce77213d4d67fae890b94d",
        ),
        (
            "import-receipt.json",
            934,
            "sha256:a4d295f07f4ba7357d9ee8f2be7baefb1eb6d7b917c6ae13dad51214aa88300e",
        ),
    ] {
        let bytes = std::fs::read(health.join(file)).expect("frozen blocked artifact");
        assert_eq!(bytes.len(), length, "blocked artifact length drift: {file}");
        assert_eq!(
            sha256_identity(&bytes),
            hash,
            "blocked artifact hash drift: {file}"
        );
    }

    let required = directory.0.join("required");
    let output = run_cli(&[
        text("import"),
        text("mgt"),
        &source,
        text("--model-id"),
        text("foundation-small-health-v1"),
        text("--output-dir"),
        &required,
        text("--require-normalized"),
    ]);
    assert_eq!(output.status.code(), Some(2));
    verify_receipt(&required, "blocked");
    for file in ["source.mgt", "import-health.json", "import-receipt.json"] {
        assert_eq!(
            std::fs::read(health.join(file)).expect("default health artifact"),
            std::fs::read(required.join(file)).expect("required health artifact")
        );
    }

    let output = run_cli(&[
        text("import"),
        text("mgt"),
        &source,
        text("--model-id"),
        text("foundation-small-health-v1"),
        text("--output-dir"),
        &health,
    ]);
    assert!(!output.status.success());
    verify_receipt(&health, "blocked");

    #[cfg(unix)]
    {
        let link = directory.0.join("source-link.mgt");
        std::os::unix::fs::symlink(&source, &link).expect("source symlink");
        let symlink_output = directory.0.join("symlink-output");
        let output = run_cli(&[
            text("import"),
            text("mgt"),
            &link,
            text("--model-id"),
            text("foundation-small-health-v1"),
            text("--output-dir"),
            &symlink_output,
        ]);
        assert!(!output.status.success());
        assert!(!symlink_output.exists());
    }
}
