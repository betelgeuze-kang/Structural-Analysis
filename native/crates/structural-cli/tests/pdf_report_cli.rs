use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_report::validate_deterministic_pdf_v1;

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
            "structural-native-pdf-cli-test-{}-{sequence}",
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

fn build_analysis(directory: &Path) {
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
}

fn render_pdf(analysis: &Path, output_directory: &Path) -> Output {
    run_cli(&[
        text("report"),
        text("render-pdf"),
        &analysis.join("result-ir.json"),
        &analysis.join("report-ir.json"),
        &analysis.join("report.md"),
        text("--output-dir"),
        output_directory,
    ])
}

fn verify_receipt(directory: &Path) {
    let receipt_bytes =
        std::fs::read(directory.join("pdf-receipt.json")).expect("PDF receipt bytes");
    let mut receipt: Value = serde_json::from_slice(&receipt_bytes).expect("PDF receipt JSON");
    let receipt_hash = receipt["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    receipt
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("canonical unsigned receipt");
    assert_eq!(receipt_hash, sha256_identity(unsigned.as_bytes()));
    let pdf = std::fs::read(directory.join("report.pdf")).expect("PDF artifact");
    validate_deterministic_pdf_v1(&pdf).expect("native PDF structure");
    assert_eq!(receipt["pdf_hash"], sha256_identity(&pdf));
    assert_eq!(
        receipt["artifacts"][0]["content_hash"],
        sha256_identity(&pdf)
    );
    assert_eq!(
        receipt["artifacts"][0]["byte_length"],
        u64::try_from(pdf.len()).expect("bounded PDF length")
    );
}

#[test]
fn python_node_and_external_renderer_free_pdf_is_bitwise_deterministic() {
    let temporary = TestDirectory::create();
    let analysis = temporary.0.join("analysis");
    build_analysis(&analysis);
    let first = temporary.0.join("pdf-first");
    let second = temporary.0.join("pdf-second");
    for output_directory in [&first, &second] {
        let output = render_pdf(&analysis, output_directory);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        verify_receipt(output_directory);
    }
    for file in ["report.pdf", "pdf-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(file)).expect("first PDF artifact"),
            std::fs::read(second.join(file)).expect("second PDF artifact"),
            "PDF artifact drift: {file}"
        );
    }
    for (file, length, hash) in [
        (
            "report.pdf",
            5_638_usize,
            "sha256:35f2bebb41411b31cba9e0c395ba74f914097498e8da63e4b14d72704f06c197",
        ),
        (
            "pdf-receipt.json",
            1_040_usize,
            "sha256:b807334630bb3c98398efcec4451e44ba23e3e538a1938b1c284bc781a677877",
        ),
    ] {
        let bytes = std::fs::read(first.join(file)).expect("frozen PDF artifact");
        assert_eq!(bytes.len(), length, "PDF length drift: {file}");
        assert_eq!(sha256_identity(&bytes), hash, "PDF hash drift: {file}");
    }
}

#[test]
fn forged_markdown_and_existing_destination_fail_without_overwrite() {
    let temporary = TestDirectory::create();
    let analysis = temporary.0.join("analysis");
    build_analysis(&analysis);
    let mut forged = std::fs::read(analysis.join("report.md")).expect("report source");
    forged.extend_from_slice(b"\nforged\n");
    let forged_path = temporary.0.join("forged.md");
    std::fs::write(&forged_path, forged).expect("write forged source");
    let rejected = temporary.0.join("rejected");
    let output = run_cli(&[
        text("report"),
        text("render-pdf"),
        &analysis.join("result-ir.json"),
        &analysis.join("report-ir.json"),
        &forged_path,
        text("--output-dir"),
        &rejected,
    ]);
    assert_eq!(output.status.code(), Some(2));
    assert!(!rejected.exists());
    assert!(
        String::from_utf8_lossy(&output.stdout).contains("pdf_document_source_projection_mismatch")
    );

    let existing = temporary.0.join("existing");
    std::fs::create_dir(&existing).expect("existing output directory");
    std::fs::write(existing.join("sentinel"), b"preserve").expect("sentinel");
    let output = render_pdf(&analysis, &existing);
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(
        std::fs::read(existing.join("sentinel")).expect("preserved sentinel"),
        b"preserve"
    );
    assert!(!existing.join("report.pdf").exists());
}
