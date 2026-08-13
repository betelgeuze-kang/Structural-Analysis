use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-report-pdf-smoke-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-report-pdf-smoke-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_EXPORTER_PATH: &str = "scripts/export-structure-viewer-report-pdf.mjs";
const EXPECTED_DEFAULT_QUERY: &str =
    "project=midas33_release&drawing=midas33_optimized&variant=optimized";
const EXPECTED_DEFAULT_MINIMUM_BYTES: u64 = 12_000;
const EXPECTED_PDFTOTEXT_LAUNCHER: &str = "pdftotext";
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_exporter_loopback_and_browser_page_requests";
const MAX_EXPORTER_BYTES: u64 = 2 * 1024 * 1024;
const MAX_PDF_BYTES: u64 = 128 * 1024 * 1024;
const MAX_HTML_BYTES: u64 = 32 * 1024 * 1024;
const MAX_PDF_TEXT_BYTES: u64 = 16 * 1024 * 1024;
const MAX_QUERY_BYTES: usize = 4096;
const MAX_PATH_BYTES: usize = 4096;
const HTML_SNIPPETS: [&str; 5] = [
    "Drawing Review",
    "Before / After Member Comparison",
    "viewer screenshot marker",
    "Engineer-in-loop Checklist",
    "상용 검토 가능",
];
const PDF_TEXT_SNIPPETS: [&str; 3] = [
    "Drawing Review",
    "Before / After Member Comparison",
    "Engineer-in-loop Checklist",
];
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerReportPdfSmokeSourceV1 {
    schema_version: String,
    node_launcher: String,
    exporter_path: String,
    default_query: String,
    default_minimum_bytes: u64,
    required_html_snippets: Vec<String>,
    optional_pdf_text_launcher: String,
    required_pdf_text_snippets: Vec<String>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Viewer report PDF smoke plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ViewerReportPdfSmokeOptions {
    pub root: PathBuf,
    pub query: String,
    pub minimum_pdf_bytes: u64,
    pub output: Option<PathBuf>,
    pub dry_run: bool,
    pub keep_temporary_output: bool,
}

impl ViewerReportPdfSmokeOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            query: EXPECTED_DEFAULT_QUERY.to_owned(),
            minimum_pdf_bytes: EXPECTED_DEFAULT_MINIMUM_BYTES,
            output: None,
            dry_run: false,
            keep_temporary_output: false,
        }
    }
}

struct PreparedViewerReportPdfSmoke {
    source: ViewerReportPdfSmokeSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    exporter_bytes: Vec<u8>,
    query: String,
    minimum_pdf_bytes: u64,
    requested_output: Option<String>,
    logical_command_template: Vec<String>,
}

struct LiveOutput {
    pdf_path: PathBuf,
    html_path: PathBuf,
    published_output_path: Option<String>,
    output_disposition: &'static str,
    cleanup_explicit_outputs: bool,
    workspace: TemporaryWorkspace,
}

impl Drop for LiveOutput {
    fn drop(&mut self) {
        if self.cleanup_explicit_outputs {
            let _ignored = fs::remove_file(&self.pdf_path);
            let _ignored = fs::remove_file(&self.html_path);
        }
    }
}

struct VerifiedArtifacts {
    pdf_bytes: Vec<u8>,
    html_bytes: Vec<u8>,
    pdf_text_bytes: Option<Vec<u8>>,
    pdf_text_status: &'static str,
    successful_exit_codes: Vec<i32>,
}

struct OptionalPdfText {
    bytes: Option<Vec<u8>>,
    status: &'static str,
    exit_code: Option<i32>,
}

struct TemporaryWorkspace {
    path: PathBuf,
    retain: bool,
}

impl TemporaryWorkspace {
    fn create(retain: bool) -> Result<Self, FrontendContractError> {
        let parent = std::env::temp_dir();
        verify_real_directory(&parent, "Viewer report PDF temporary parent")?;
        for _ in 0..1024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-report-pdf-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path, retain }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_report_pdf_smoke_temp_create_failed",
                        format!("create Viewer report PDF temporary directory failed: {error}"),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_temp_create_failed",
            "could not allocate a unique Viewer report PDF temporary directory",
        ))
    }
}

impl Drop for TemporaryWorkspace {
    fn drop(&mut self) {
        if !self.retain {
            let _ignored = fs::remove_dir_all(&self.path);
        }
    }
}

/// Canonical receipt for one planned or completed Viewer report PDF smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerReportPdfSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub exporter_sha256: String,
    pub query: String,
    pub minimum_pdf_bytes: u64,
    pub requested_output: Option<String>,
    pub published_output_path: Option<String>,
    pub output_disposition: String,
    pub logical_command_template: Vec<String>,
    pub pdf_byte_length: Option<u64>,
    pub pdf_sha256: Option<String>,
    pub html_byte_length: Option<u64>,
    pub html_sha256: Option<String>,
    pub pdf_text_status: String,
    pub pdf_text_sha256: Option<String>,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Plan or execute the retained Viewer report PDF export verification under Rust ownership.
///
/// Dry-run validates and hashes the tracked frontend and exporter and emits a process-free plan.
/// Live execution directly owns one Node exporter child, validates bounded non-symlink PDF and HTML
/// outputs, and uses `pdftotext` only when that optional executable is installed. The retained
/// exporter continues to own its loopback server, Playwright, Chromium, and browser behavior.
///
/// # Errors
///
/// Rejects contract drift, unsafe inputs or outputs, exporter failure, missing or malformed PDF or
/// HTML output, optional PDF text conversion failure, and required report-text drift.
pub fn run_viewer_report_pdf_smoke(
    options: &ViewerReportPdfSmokeOptions,
) -> Result<ViewerReportPdfSmokeReceiptV1, FrontendContractError> {
    let prepared = prepare_viewer_report_pdf_smoke(options)?;
    if options.dry_run {
        return build_receipt(prepared, None, None);
    }

    let mut output = prepare_live_output(options, &prepared.root)?;
    let exporter_exit = run_exporter(&prepared, &output)?;
    let verified = verify_live_artifacts(
        &prepared.source,
        prepared.minimum_pdf_bytes,
        &output,
        exporter_exit,
    )?;
    verify_execution_inputs_unchanged(&prepared)?;
    let receipt = build_receipt(prepared, Some(&output), Some(&verified))?;
    output.cleanup_explicit_outputs = false;
    Ok(receipt)
}

fn verify_execution_inputs_unchanged(
    prepared: &PreparedViewerReportPdfSmoke,
) -> Result<(), FrontendContractError> {
    let post_contract = check_frontend_contract(&prepared.root)?;
    let exporter = resolve_required_file(&prepared.root, &prepared.source.exporter_path)?;
    let exporter_bytes =
        read_bounded_regular_file(&exporter, MAX_EXPORTER_BYTES, "Viewer report PDF exporter")?;
    if post_contract.receipt_hash != prepared.frontend_contract_receipt_hash
        || exporter_bytes != prepared.exporter_bytes
    {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_contract_changed",
            "frontend package, lock, or exporter changed while Viewer PDF verification executed",
        ));
    }
    Ok(())
}

fn prepare_viewer_report_pdf_smoke(
    options: &ViewerReportPdfSmokeOptions,
) -> Result<PreparedViewerReportPdfSmoke, FrontendContractError> {
    validate_options(options)?;
    verify_real_directory(&options.root, "Viewer report PDF smoke root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_report_pdf_smoke_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_root_invalid",
            format!("canonicalize Viewer report PDF smoke root failed: {error}"),
        )
    })?;
    let exporter = resolve_required_file(&root, &source.exporter_path)?;
    let exporter_bytes =
        read_bounded_regular_file(&exporter, MAX_EXPORTER_BYTES, "Viewer report PDF exporter")?;
    let requested_output = options
        .output
        .as_ref()
        .map(|path| portable_input_path(path, "Viewer report PDF output"))
        .transpose()?;
    let logical_command_template = vec![
        source.node_launcher.clone(),
        source.exporter_path.clone(),
        "--query".to_owned(),
        options.query.clone(),
        "--out".to_owned(),
        "{pdf_output}".to_owned(),
        "--html-out".to_owned(),
        "{html_output}".to_owned(),
    ];
    Ok(PreparedViewerReportPdfSmoke {
        source,
        root,
        frontend_contract_receipt_hash,
        exporter_bytes,
        query: options.query.clone(),
        minimum_pdf_bytes: options.minimum_pdf_bytes,
        requested_output,
        logical_command_template,
    })
}

/// Encode a Viewer report PDF smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_report_pdf_smoke_receipt_json(
    receipt: &ViewerReportPdfSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_report_pdf_smoke_receipt_encode_failed")
}

pub(crate) fn validate_viewer_report_pdf_smoke_source(
    source: &ViewerReportPdfSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    let html_snippets = source
        .required_html_snippets
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let pdf_text_snippets = source
        .required_pdf_text_snippets
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.exporter_path == EXPECTED_EXPORTER_PATH
        && source.default_query == EXPECTED_DEFAULT_QUERY
        && source.default_minimum_bytes == EXPECTED_DEFAULT_MINIMUM_BYTES
        && html_snippets == HTML_SNIPPETS
        && source.optional_pdf_text_launcher == EXPECTED_PDFTOTEXT_LAUNCHER
        && pdf_text_snippets == PDF_TEXT_SNIPPETS
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    let unique_html = source
        .required_html_snippets
        .iter()
        .collect::<BTreeSet<_>>();
    let unique_pdf_text = source
        .required_pdf_text_snippets
        .iter()
        .collect::<BTreeSet<_>>();
    if !valid
        || unique_html.len() != source.required_html_snippets.len()
        || unique_pdf_text.len() != source.required_pdf_text_snippets.len()
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer report PDF smoke contract is invalid",
        ));
    }
    Ok(())
}

fn validate_options(options: &ViewerReportPdfSmokeOptions) -> Result<(), FrontendContractError> {
    if options.query.is_empty()
        || options.query.len() > MAX_QUERY_BYTES
        || options.query.chars().any(char::is_control)
        || options.minimum_pdf_bytes == 0
        || options.minimum_pdf_bytes > MAX_PDF_BYTES
    {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_options_invalid",
            "Viewer report PDF query or minimum byte count is invalid",
        ));
    }
    if let Some(output) = &options.output {
        portable_input_path(output, "Viewer report PDF output")?;
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn portable_input_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn prepare_live_output(
    options: &ViewerReportPdfSmokeOptions,
    root: &Path,
) -> Result<LiveOutput, FrontendContractError> {
    let retain_workspace = options.output.is_none() && options.keep_temporary_output;
    let workspace = TemporaryWorkspace::create(retain_workspace)?;
    let (pdf_path, html_path, published_output_path, output_disposition, cleanup_explicit_outputs) =
        if let Some(requested) = &options.output {
            let pdf = absolute_output_path(root, requested)?;
            let html = path_with_suffix(&pdf, ".html")?;
            validate_new_output_target(&pdf, "Viewer report PDF output")?;
            validate_new_output_target(&html, "Viewer report HTML output")?;
            (
                pdf.clone(),
                html,
                Some(portable_input_path(&pdf, "Viewer report PDF output")?),
                "operator_path_retained",
                true,
            )
        } else {
            let pdf = workspace.path.join("structure_viewer_report.pdf");
            let html = workspace.path.join("structure_viewer_report.html");
            let published = if options.keep_temporary_output {
                Some(portable_input_path(&pdf, "Viewer report PDF output")?)
            } else {
                None
            };
            let disposition = if options.keep_temporary_output {
                "temporary_path_retained"
            } else {
                "temporary_removed_after_verification"
            };
            (pdf, html, published, disposition, false)
        };
    Ok(LiveOutput {
        pdf_path,
        html_path,
        published_output_path,
        output_disposition,
        cleanup_explicit_outputs,
        workspace,
    })
}

fn absolute_output_path(root: &Path, requested: &Path) -> Result<PathBuf, FrontendContractError> {
    let path = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    let parent = path.parent().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            "Viewer report PDF output has no parent directory",
        )
    })?;
    verify_real_directory(parent, "Viewer report PDF output parent")?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("canonicalize Viewer report PDF output parent failed: {error}"),
        )
    })?;
    let file_name = path.file_name().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            "Viewer report PDF output has no file name",
        )
    })?;
    Ok(parent.join(file_name))
}

fn path_with_suffix(path: &Path, suffix: &str) -> Result<PathBuf, FrontendContractError> {
    let mut value = path.as_os_str().to_os_string();
    value.push(suffix);
    let output = PathBuf::from(value);
    portable_input_path(&output, "Viewer report HTML output")?;
    Ok(output)
}

fn validate_new_output_target(path: &Path, label: &str) -> Result<(), FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_output_exists",
            format!("{label} already exists: {}", path.display()),
        )),
        Err(error) => Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("inspect {label} failed: {error}"),
        )),
    }
}

fn run_exporter(
    prepared: &PreparedViewerReportPdfSmoke,
    output: &LiveOutput,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg(&prepared.source.exporter_path)
        .arg("--query")
        .arg(&prepared.query)
        .arg("--out")
        .arg(&output.pdf_path)
        .arg("--html-out")
        .arg(&output.html_path)
        .current_dir(&prepared.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_report_pdf_smoke_export_launch_failed",
                format!("launch Viewer report PDF exporter failed: {error}"),
            )
        })?;
    successful_exit_code(
        status,
        "viewer_report_pdf_smoke_export_terminated",
        "viewer_report_pdf_smoke_export_failed",
        "Viewer report PDF exporter",
    )
}

fn node_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("node.exe")
    } else {
        OsString::from("node")
    }
}

fn successful_exit_code(
    status: std::process::ExitStatus,
    terminated_code: &'static str,
    failed_code: &'static str,
    label: &str,
) -> Result<i32, FrontendContractError> {
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            terminated_code,
            format!("{label} terminated without an exit code"),
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            failed_code,
            format!("{label} failed with exit code {exit_code}"),
        ));
    }
    Ok(exit_code)
}

fn verify_live_artifacts(
    source: &ViewerReportPdfSmokeSourceV1,
    minimum_pdf_bytes: u64,
    output: &LiveOutput,
    exporter_exit: i32,
) -> Result<VerifiedArtifacts, FrontendContractError> {
    let (pdf_bytes, html_bytes) = verify_report_files(source, minimum_pdf_bytes, output)?;
    let pdf_text = verify_optional_pdf_text(source, output)?;
    let mut successful_exit_codes = vec![exporter_exit];
    if let Some(exit_code) = pdf_text.exit_code {
        successful_exit_codes.push(exit_code);
    }
    Ok(VerifiedArtifacts {
        pdf_bytes,
        html_bytes,
        pdf_text_bytes: pdf_text.bytes,
        pdf_text_status: pdf_text.status,
        successful_exit_codes,
    })
}

fn verify_report_files(
    source: &ViewerReportPdfSmokeSourceV1,
    minimum_pdf_bytes: u64,
    output: &LiveOutput,
) -> Result<(Vec<u8>, Vec<u8>), FrontendContractError> {
    let pdf_bytes =
        read_generated_file(&output.pdf_path, MAX_PDF_BYTES, "Viewer report PDF output")?;
    let pdf_length = u64::try_from(pdf_bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_invalid",
            "Viewer report PDF length is not addressable",
        )
    })?;
    if pdf_length < minimum_pdf_bytes || !pdf_bytes.starts_with(b"%PDF-") {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_invalid",
            format!(
                "Viewer report PDF is smaller than {minimum_pdf_bytes} bytes or has no PDF header"
            ),
        ));
    }
    let html_bytes = read_generated_file(
        &output.html_path,
        MAX_HTML_BYTES,
        "Viewer report HTML output",
    )?;
    let html = std::str::from_utf8(&html_bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_html_invalid",
            format!("Viewer report HTML output is not UTF-8: {error}"),
        )
    })?;
    for snippet in &source.required_html_snippets {
        if !html.contains(snippet) {
            return Err(FrontendContractError::new(
                "viewer_report_pdf_smoke_html_invalid",
                format!("Viewer report HTML output is missing required snippet: {snippet}"),
            ));
        }
    }
    Ok((pdf_bytes, html_bytes))
}

fn verify_optional_pdf_text(
    source: &ViewerReportPdfSmokeSourceV1,
    output: &LiveOutput,
) -> Result<OptionalPdfText, FrontendContractError> {
    let child = Command::new(&source.optional_pdf_text_launcher)
        .arg(&output.pdf_path)
        .arg("-")
        .current_dir(&output.workspace.path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn();
    match child {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(OptionalPdfText {
            bytes: None,
            status: "unavailable",
            exit_code: None,
        }),
        Err(error) => Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_text_launch_failed",
            format!("launch optional pdftotext verification failed: {error}"),
        )),
        Ok(mut child) => {
            let bytes = read_bounded_pdf_text_stdout(&mut child, MAX_PDF_TEXT_BYTES)?;
            let status = child.wait().map_err(|error| {
                FrontendContractError::new(
                    "viewer_report_pdf_smoke_pdf_text_wait_failed",
                    format!("wait for optional pdftotext verification failed: {error}"),
                )
            })?;
            let exit_code = successful_exit_code(
                status,
                "viewer_report_pdf_smoke_pdf_text_terminated",
                "viewer_report_pdf_smoke_pdf_text_failed",
                "optional pdftotext verification",
            )?;
            let text = std::str::from_utf8(&bytes).map_err(|error| {
                FrontendContractError::new(
                    "viewer_report_pdf_smoke_pdf_text_invalid",
                    format!("Viewer report PDF text output is not UTF-8: {error}"),
                )
            })?;
            for snippet in &source.required_pdf_text_snippets {
                if !text.contains(snippet) {
                    return Err(FrontendContractError::new(
                        "viewer_report_pdf_smoke_pdf_text_invalid",
                        format!("Viewer report PDF text is missing required snippet: {snippet}"),
                    ));
                }
            }
            Ok(OptionalPdfText {
                bytes: Some(bytes),
                status: "verified",
                exit_code: Some(exit_code),
            })
        }
    }
}

fn read_bounded_pdf_text_stdout(
    child: &mut Child,
    maximum_bytes: u64,
) -> Result<Vec<u8>, FrontendContractError> {
    let Some(read_limit) = maximum_bytes.checked_add(1) else {
        let _ignored = child.kill();
        let _ignored = child.wait();
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_text_output_failed",
            "Viewer report PDF text byte limit overflowed",
        ));
    };
    let Some(stdout) = child.stdout.take() else {
        let _ignored = child.kill();
        let _ignored = child.wait();
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_text_launch_failed",
            "optional pdftotext stdout pipe is unavailable",
        ));
    };
    let mut bytes = Vec::new();
    if let Err(error) = stdout.take(read_limit).read_to_end(&mut bytes) {
        let _ignored = child.kill();
        let _ignored = child.wait();
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_text_output_failed",
            format!("read bounded PDF text output failed: {error}"),
        ));
    }
    if u64::try_from(bytes.len()).unwrap_or(u64::MAX) > maximum_bytes {
        let _ignored = child.kill();
        let _ignored = child.wait();
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_pdf_text_output_failed",
            "Viewer report PDF text output exceeds the bounded byte limit",
        ));
    }
    Ok(bytes)
}

fn read_generated_file(
    path: &Path,
    maximum_bytes: u64,
    label: &str,
) -> Result<Vec<u8>, FrontendContractError> {
    let bytes = read_bounded_regular_file(path, maximum_bytes, label).map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("{label} failed bounded file validation: {error}"),
        )
    })?;
    if bytes.is_empty() {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_output_invalid",
            format!("{label} is empty"),
        ));
    }
    Ok(bytes)
}

fn build_receipt(
    prepared: PreparedViewerReportPdfSmoke,
    output: Option<&LiveOutput>,
    verified: Option<&VerifiedArtifacts>,
) -> Result<ViewerReportPdfSmokeReceiptV1, FrontendContractError> {
    let dry_run = verified.is_none();
    let (pdf_byte_length, pdf_sha256, html_byte_length, html_sha256) = match verified {
        None => (None, None, None, None),
        Some(artifacts) => (
            Some(u64::try_from(artifacts.pdf_bytes.len()).map_err(|_| {
                FrontendContractError::new(
                    "viewer_report_pdf_smoke_receipt_encode_failed",
                    "Viewer report PDF length is not addressable",
                )
            })?),
            Some(sha256_identity(&artifacts.pdf_bytes)),
            Some(u64::try_from(artifacts.html_bytes.len()).map_err(|_| {
                FrontendContractError::new(
                    "viewer_report_pdf_smoke_receipt_encode_failed",
                    "Viewer report HTML length is not addressable",
                )
            })?),
            Some(sha256_identity(&artifacts.html_bytes)),
        ),
    };
    let mut receipt = ViewerReportPdfSmokeReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_report_pdf_smoke".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        exporter_sha256: sha256_identity(&prepared.exporter_bytes),
        query: prepared.query,
        minimum_pdf_bytes: prepared.minimum_pdf_bytes,
        requested_output: prepared.requested_output,
        published_output_path: output.and_then(|value| value.published_output_path.clone()),
        output_disposition: output
            .map_or("not_created", |value| value.output_disposition)
            .to_owned(),
        logical_command_template: prepared.logical_command_template,
        pdf_byte_length,
        pdf_sha256,
        html_byte_length,
        html_sha256,
        pdf_text_status: verified
            .map_or("not_executed", |value| value.pdf_text_status)
            .to_owned(),
        pdf_text_sha256: verified
            .and_then(|value| value.pdf_text_bytes.as_ref())
            .map(|bytes| sha256_identity(bytes)),
        node_runtime_required: true,
        browser_runtime_required: true,
        rust_owned_listener_count: 0,
        direct_processes_spawned: verified.map_or(0, |value| {
            u64::try_from(value.successful_exit_codes.len()).unwrap_or(u64::MAX)
        }),
        successful_exit_codes: verified
            .map_or_else(Vec::new, |value| value.successful_exit_codes.clone()),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: dry_run,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    if receipt.direct_processes_spawned == u64::MAX {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_smoke_receipt_encode_failed",
            "Viewer report PDF process count is not addressable",
        ));
    }
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &ViewerReportPdfSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_receipt_encode_failed",
            format!("project Viewer report PDF smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_report_pdf_smoke_receipt_encode_failed",
                "Viewer report PDF smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_smoke_receipt_encode_failed",
            format!("canonicalize Viewer report PDF smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    #[cfg(unix)]
    use std::process::{Command, Stdio};

    #[cfg(unix)]
    use super::read_bounded_pdf_text_stdout;
    use super::{
        validate_viewer_report_pdf_smoke_source, ViewerReportPdfSmokeSourceV1, HTML_SNIPPETS,
        PDF_TEXT_SNIPPETS,
    };

    #[test]
    fn source_contract_rejects_report_marker_or_runtime_widening() {
        let source = ViewerReportPdfSmokeSourceV1 {
            schema_version: "structural-native-viewer-report-pdf-smoke-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            exporter_path: "scripts/export-structure-viewer-report-pdf.mjs".to_owned(),
            default_query: "project=midas33_release&drawing=midas33_optimized&variant=optimized"
                .to_owned(),
            default_minimum_bytes: 12_000,
            required_html_snippets: HTML_SNIPPETS.iter().map(ToString::to_string).collect(),
            optional_pdf_text_launcher: "pdftotext".to_owned(),
            required_pdf_text_snippets: PDF_TEXT_SNIPPETS.iter().map(ToString::to_string).collect(),
            external_network_access_accounting:
                "not_instrumented_exporter_loopback_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        };
        assert!(validate_viewer_report_pdf_smoke_source(&source).is_ok());
        let mut drift = source;
        drift.required_html_snippets.pop();
        assert!(validate_viewer_report_pdf_smoke_source(&drift).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn oversized_pdf_text_output_is_bounded_and_child_is_reaped() {
        let mut child = Command::new("sh")
            .args(["-c", "while :; do printf '0123456789abcdef'; done"])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn noisy PDF text converter");
        let error = read_bounded_pdf_text_stdout(&mut child, 1024)
            .expect_err("oversized PDF text must fail closed");
        assert_eq!(error.code, "viewer_report_pdf_smoke_pdf_text_output_failed");
        assert!(error.detail.contains("exceeds the bounded byte limit"));
        assert!(child.try_wait().expect("inspect reaped child").is_some());
    }
}
