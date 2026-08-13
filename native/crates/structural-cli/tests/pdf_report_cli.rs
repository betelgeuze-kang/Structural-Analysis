use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_report::{validate_deterministic_localized_pdf_v2, validate_deterministic_pdf_v1};

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

fn build_model_linear_analysis(directory: &Path) {
    let root = repository_root();
    let model = root.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let request =
        root.join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json");
    let output = run_cli(&[
        text("analysis"),
        text("model-linear-run"),
        &model,
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

fn render_sparse_pdf(analysis: &Path, output_directory: &Path) -> Output {
    run_cli(&[
        text("report"),
        text("render-sparse-pdf"),
        &analysis.join("result-ir.json"),
        &analysis.join("report-ir.json"),
        &analysis.join("report.md"),
        text("--output-dir"),
        output_directory,
    ])
}

fn render_localized_pdf(analysis: &Path, output_directory: &Path, locale: &str) -> Output {
    run_cli(&[
        text("report"),
        text("render-pdf"),
        &analysis.join("result-ir.json"),
        &analysis.join("report-ir.json"),
        &analysis.join("report.md"),
        text("--output-dir"),
        output_directory,
        text("--locale"),
        text(locale),
    ])
}

fn render_sparse_localized_pdf(analysis: &Path, output_directory: &Path, locale: &str) -> Output {
    run_cli(&[
        text("report"),
        text("render-sparse-pdf"),
        &analysis.join("result-ir.json"),
        &analysis.join("report-ir.json"),
        &analysis.join("report.md"),
        text("--output-dir"),
        output_directory,
        text("--locale"),
        text(locale),
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
fn sparse_linear_pdf_cli_is_clean_environment_deterministic_and_profile_typed() {
    let temporary = TestDirectory::create();
    let analysis = temporary.0.join("model-linear-analysis");
    build_model_linear_analysis(&analysis);
    let first = temporary.0.join("sparse-pdf-first");
    let second = temporary.0.join("sparse-pdf-second");
    for output_directory in [&first, &second] {
        let output = render_sparse_pdf(&analysis, output_directory);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        let receipt: Value =
            serde_json::from_slice(&output.stdout).expect("sparse PDF receipt stdout");
        assert_eq!(
            receipt["schema_version"],
            "structural-native-sparse-linear-pdf-report-receipt.v1"
        );
        verify_receipt(output_directory);
    }
    for file in ["report.pdf", "pdf-receipt.json"] {
        assert_eq!(
            std::fs::read(first.join(file)).expect("first sparse PDF artifact"),
            std::fs::read(second.join(file)).expect("second sparse PDF artifact"),
            "sparse PDF artifact drift: {file}"
        );
    }

    let wrong_profile = render_pdf(&analysis, &temporary.0.join("wrong-profile"));
    assert_eq!(wrong_profile.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&wrong_profile.stdout).contains("result_ir"));
}

#[test]
fn localized_sparse_linear_pdf_cli_is_deterministic_and_profile_typed() {
    let temporary = TestDirectory::create();
    let analysis = temporary.0.join("model-linear-analysis");
    build_model_linear_analysis(&analysis);
    let mut locale_hashes = Vec::new();
    for locale in ["en-US", "ko-KR"] {
        let first = temporary.0.join(format!("sparse-localized-{locale}-first"));
        let second = temporary
            .0
            .join(format!("sparse-localized-{locale}-second"));
        for output_directory in [&first, &second] {
            let output = render_sparse_localized_pdf(&analysis, output_directory, locale);
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stdout)
            );
            let receipt: Value =
                serde_json::from_slice(&output.stdout).expect("sparse localized receipt stdout");
            assert_eq!(
                receipt["schema_version"],
                "structural-native-sparse-linear-localized-pdf-report-receipt.v2"
            );
            assert_eq!(receipt["profile"], "sparse_linear_cpu_v1");
            assert_eq!(receipt["locale"], locale);
            assert_eq!(
                receipt["artifacts"][0]["role"],
                "sparse_linear_localized_pdf_report"
            );
            let pdf = std::fs::read(output_directory.join("report.pdf"))
                .expect("localized sparse PDF artifact");
            validate_deterministic_localized_pdf_v2(&pdf)
                .expect("localized sparse PDF and embedded font structure");
        }
        for file in ["report.pdf", "pdf-receipt.json"] {
            assert_eq!(
                std::fs::read(first.join(file)).expect("first localized sparse artifact"),
                std::fs::read(second.join(file)).expect("second localized sparse artifact"),
                "localized sparse artifact drift: {locale}/{file}"
            );
        }
        locale_hashes.push(sha256_identity(
            &std::fs::read(first.join("report.pdf")).expect("localized sparse PDF"),
        ));
    }
    assert_ne!(locale_hashes[0], locale_hashes[1]);
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
    assert!(String::from_utf8_lossy(&output.stdout).contains("pdf_report_publish_failed"));
    assert_eq!(
        std::fs::read(existing.join("sentinel")).expect("preserved sentinel"),
        b"preserve"
    );
    assert!(!existing.join("report.pdf").exists());
}

#[test]
fn localized_embedded_font_pdf_is_clean_environment_deterministic_and_closed() {
    let temporary = TestDirectory::create();
    let analysis = temporary.0.join("analysis");
    build_analysis(&analysis);
    let mut locale_hashes = Vec::new();
    for locale in ["en-US", "ko-KR"] {
        let first = temporary.0.join(format!("pdf-{locale}-first"));
        let second = temporary.0.join(format!("pdf-{locale}-second"));
        for output_directory in [&first, &second] {
            let output = render_localized_pdf(&analysis, output_directory, locale);
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stdout)
            );
            let stdout: Value =
                serde_json::from_slice(&output.stdout).expect("localized receipt stdout");
            assert_eq!(
                stdout["schema_version"],
                "structural-native-localized-pdf-report-receipt.v2"
            );
            assert_eq!(stdout["locale"], locale);
            assert_eq!(stdout["embedded_font"]["license"]["id"], "OFL-1.1");
            assert_eq!(
                stdout["embedded_font"]["license"]["distribution_path"],
                "share/structural-report/OFL-1.1.txt"
            );
            assert_eq!(
                stdout["embedded_font"]["provenance"]["distribution_path"],
                "share/structural-report/StructuralReportKoreanSubset.provenance.json"
            );
            assert_eq!(
                stdout["embedded_font"]["content_hash"],
                "sha256:bdcc6ac7747f102ba1dc64a0d034d9695bab41b1f82b098ffb836334c9329a68"
            );
            let pdf =
                std::fs::read(output_directory.join("report.pdf")).expect("localized PDF artifact");
            validate_deterministic_localized_pdf_v2(&pdf)
                .expect("localized PDF and embedded font structure");
        }
        for file in ["report.pdf", "pdf-receipt.json"] {
            assert_eq!(
                std::fs::read(first.join(file)).expect("first localized artifact"),
                std::fs::read(second.join(file)).expect("second localized artifact"),
                "localized artifact drift: {locale}/{file}"
            );
        }
        let pdf = std::fs::read(first.join("report.pdf")).expect("localized PDF");
        locale_hashes.push(sha256_identity(&pdf));
    }
    assert_ne!(locale_hashes[0], locale_hashes[1]);

    let invalid_destination = temporary.0.join("invalid-locale");
    let invalid = render_localized_pdf(&analysis, &invalid_destination, "ko-kr");
    assert_eq!(invalid.status.code(), Some(2));
    assert!(!invalid_destination.exists());
}
