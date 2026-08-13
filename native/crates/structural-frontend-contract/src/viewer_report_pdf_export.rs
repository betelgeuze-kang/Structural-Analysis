use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::Serialize;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, read_bounded_regular_file, run_viewer_report_pdf_smoke,
    verify_real_directory, FrontendContractError, ViewerReportPdfSmokeOptions,
    ViewerReportPdfSmokeReceiptV1,
};

const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-report-pdf-export-receipt.v1";
const DEFAULT_PDF_OUTPUT: &str = "structure_viewer_report.pdf";
const MAX_PDF_BYTES: u64 = 128 * 1024 * 1024;
const MAX_HTML_BYTES: u64 = 32 * 1024 * 1024;
const MAX_PATH_BYTES: usize = 4096;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// Inputs for one safely published Viewer report PDF export.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ViewerReportPdfExportOptions {
    pub root: PathBuf,
    pub query: String,
    pub minimum_pdf_bytes: u64,
    pub output: PathBuf,
    pub html_output: Option<PathBuf>,
    pub dry_run: bool,
}

impl ViewerReportPdfExportOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        let smoke = ViewerReportPdfSmokeOptions::new(root.clone());
        Self {
            root,
            query: smoke.query,
            minimum_pdf_bytes: smoke.minimum_pdf_bytes,
            output: PathBuf::from(DEFAULT_PDF_OUTPUT),
            html_output: None,
            dry_run: false,
        }
    }
}

/// Canonical receipt for one planned or safely published Viewer report PDF export.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerReportPdfExportReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub verification_receipt_hash: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub exporter_sha256: String,
    pub query: String,
    pub minimum_pdf_bytes: u64,
    pub requested_pdf_output: String,
    pub requested_html_output: Option<String>,
    pub published_pdf_path: Option<String>,
    pub published_html_path: Option<String>,
    pub pdf_previous_state: String,
    pub pdf_previous_byte_length: Option<u64>,
    pub pdf_previous_sha256: Option<String>,
    pub html_previous_state: Option<String>,
    pub html_previous_byte_length: Option<u64>,
    pub html_previous_sha256: Option<String>,
    pub output_disposition: String,
    pub publication_strategy: String,
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

#[derive(Clone)]
struct OutputTarget {
    requested: String,
    path: PathBuf,
    maximum_previous_bytes: u64,
    snapshot: TargetSnapshot,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct TargetSnapshot {
    state: &'static str,
    byte_length: Option<u64>,
    sha256: Option<String>,
}

struct PreparedExport {
    pdf: OutputTarget,
    html: Option<OutputTarget>,
}

struct GeneratedWorkspace {
    path: PathBuf,
}

impl GeneratedWorkspace {
    fn create() -> Result<Self, FrontendContractError> {
        let parent = std::env::temp_dir();
        verify_real_directory(&parent, "Viewer report PDF export temporary parent")?;
        for _ in 0..1024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-report-pdf-export-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_report_pdf_export_temp_create_failed",
                        format!("create Viewer report PDF export workspace failed: {error}"),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_report_pdf_export_temp_create_failed",
            "could not allocate a unique Viewer report PDF export workspace",
        ))
    }

    fn pdf_path(&self) -> PathBuf {
        self.path.join(DEFAULT_PDF_OUTPUT)
    }

    fn html_path(&self) -> PathBuf {
        self.path.join(format!("{DEFAULT_PDF_OUTPUT}.html"))
    }
}

impl Drop for GeneratedWorkspace {
    fn drop(&mut self) {
        let _ignored = fs::remove_dir_all(&self.path);
    }
}

struct GeneratedArtifacts {
    pdf: Vec<u8>,
    html: Vec<u8>,
}

struct StagedTarget {
    target: OutputTarget,
    staged_path: PathBuf,
    backup_path: Option<PathBuf>,
    published: bool,
}

impl Drop for StagedTarget {
    fn drop(&mut self) {
        let _ignored = fs::remove_file(&self.staged_path);
    }
}

/// Plan or execute a Viewer report PDF export with verified-before-publish semantics.
///
/// The retained exporter still owns Playwright, Chromium, its loopback server, Viewer JavaScript
/// rendering, and the raw PDF generation. Rust owns the direct exporter child through the smoke
/// verifier, validates both generated artifacts, rejects output symlinks and non-files, detects
/// output mutation during generation, and publishes only the verified bytes. Existing regular
/// output files are replaced only after successful verification and are restored if publication
/// fails.
///
/// # Errors
///
/// Rejects invalid or aliased destinations, frontend/exporter drift, exporter or artifact failure,
/// output mutation during generation, staging failure, publication failure, or rollback failure.
pub fn run_viewer_report_pdf_export(
    options: &ViewerReportPdfExportOptions,
) -> Result<ViewerReportPdfExportReceiptV1, FrontendContractError> {
    let prepared = prepare_export(options)?;
    if options.dry_run {
        let verification = run_verification(options, None, true)?;
        return build_receipt(options, &prepared, &verification, None);
    }

    let workspace = GeneratedWorkspace::create()?;
    let verification = run_verification(options, Some(workspace.pdf_path()), false)?;
    let artifacts = read_verified_artifacts(&workspace, &verification)?;
    publish_verified_artifacts(&prepared, &artifacts)?;
    build_receipt(options, &prepared, &verification, Some(&artifacts))
}

/// Encode a Viewer report PDF export receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_report_pdf_export_receipt_json(
    receipt: &ViewerReportPdfExportReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_report_pdf_export_receipt_encode_failed")
}

fn prepare_export(
    options: &ViewerReportPdfExportOptions,
) -> Result<PreparedExport, FrontendContractError> {
    verify_real_directory(&options.root, "Viewer report PDF export root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_export_root_invalid",
            format!("canonicalize Viewer report PDF export root failed: {error}"),
        )
    })?;
    let pdf = prepare_target(
        &root,
        &options.output,
        MAX_PDF_BYTES,
        "Viewer report PDF output",
    )?;
    let html = options
        .html_output
        .as_ref()
        .map(|path| prepare_target(&root, path, MAX_HTML_BYTES, "Viewer report HTML output"))
        .transpose()?;
    if html.as_ref().is_some_and(|value| value.path == pdf.path) {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_export_output_alias",
            "Viewer report PDF and HTML outputs must be different files",
        ));
    }
    Ok(PreparedExport { pdf, html })
}

fn prepare_target(
    root: &Path,
    requested: &Path,
    maximum_previous_bytes: u64,
    label: &str,
) -> Result<OutputTarget, FrontendContractError> {
    let requested_string = portable_path(requested, label)?;
    let unresolved = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    let parent = unresolved.parent().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("{label} has no parent directory"),
        )
    })?;
    verify_real_directory(parent, &format!("{label} parent"))?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("canonicalize {label} parent failed: {error}"),
        )
    })?;
    let file_name = unresolved.file_name().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("{label} has no file name"),
        )
    })?;
    let path = parent.join(file_name);
    let snapshot = inspect_target(&path, maximum_previous_bytes, label)?;
    Ok(OutputTarget {
        requested: requested_string,
        path,
        maximum_previous_bytes,
        snapshot,
    })
}

fn portable_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn inspect_target(
    path: &Path,
    maximum_bytes: u64,
    label: &str,
) -> Result<TargetSnapshot, FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(TargetSnapshot {
            state: "absent",
            byte_length: None,
            sha256: None,
        }),
        Err(error) => Err(FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("inspect {label} failed: {error}"),
        )),
        Ok(metadata) if metadata.file_type().is_file() => {
            let bytes = read_bounded_regular_file(path, maximum_bytes, label).map_err(|error| {
                FrontendContractError::new(
                    "viewer_report_pdf_export_output_invalid",
                    format!("read existing {label} failed bounded validation: {error}"),
                )
            })?;
            let byte_length = u64::try_from(bytes.len()).map_err(|_| {
                FrontendContractError::new(
                    "viewer_report_pdf_export_output_invalid",
                    format!("existing {label} length is not addressable"),
                )
            })?;
            Ok(TargetSnapshot {
                state: "regular_file",
                byte_length: Some(byte_length),
                sha256: Some(sha256_identity(&bytes)),
            })
        }
        Ok(_) => Err(FrontendContractError::new(
            "viewer_report_pdf_export_output_invalid",
            format!("{label} must be absent or an existing non-symlink regular file"),
        )),
    }
}

fn run_verification(
    options: &ViewerReportPdfExportOptions,
    output: Option<PathBuf>,
    dry_run: bool,
) -> Result<ViewerReportPdfSmokeReceiptV1, FrontendContractError> {
    let mut smoke = ViewerReportPdfSmokeOptions::new(options.root.clone());
    smoke.query.clone_from(&options.query);
    smoke.minimum_pdf_bytes = options.minimum_pdf_bytes;
    smoke.output = output;
    smoke.dry_run = dry_run;
    run_viewer_report_pdf_smoke(&smoke)
}

fn read_verified_artifacts(
    workspace: &GeneratedWorkspace,
    verification: &ViewerReportPdfSmokeReceiptV1,
) -> Result<GeneratedArtifacts, FrontendContractError> {
    let pdf = read_bounded_regular_file(
        &workspace.pdf_path(),
        MAX_PDF_BYTES,
        "verified Viewer report PDF",
    )?;
    let html = read_bounded_regular_file(
        &workspace.html_path(),
        MAX_HTML_BYTES,
        "verified Viewer report HTML",
    )?;
    require_verified_identity(
        &pdf,
        verification.pdf_byte_length,
        verification.pdf_sha256.as_deref(),
        "PDF",
    )?;
    require_verified_identity(
        &html,
        verification.html_byte_length,
        verification.html_sha256.as_deref(),
        "HTML",
    )?;
    Ok(GeneratedArtifacts { pdf, html })
}

fn require_verified_identity(
    bytes: &[u8],
    expected_length: Option<u64>,
    expected_sha256: Option<&str>,
    label: &str,
) -> Result<(), FrontendContractError> {
    let length = u64::try_from(bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "viewer_report_pdf_export_verified_artifact_changed",
            format!("verified Viewer report {label} length is not addressable"),
        )
    })?;
    if expected_length != Some(length) || expected_sha256 != Some(sha256_identity(bytes).as_str()) {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_export_verified_artifact_changed",
            format!("Viewer report {label} changed after verification and before publication"),
        ));
    }
    Ok(())
}

fn publish_verified_artifacts(
    prepared: &PreparedExport,
    artifacts: &GeneratedArtifacts,
) -> Result<(), FrontendContractError> {
    let mut staged = Vec::with_capacity(if prepared.html.is_some() { 2 } else { 1 });
    if let Some(html) = &prepared.html {
        staged.push(stage_target(html.clone(), &artifacts.html, "html")?);
    }
    staged.push(stage_target(prepared.pdf.clone(), &artifacts.pdf, "pdf")?);

    for target in &staged {
        let current = inspect_target(
            &target.target.path,
            target.target.maximum_previous_bytes,
            "Viewer report publication output",
        )?;
        if current != target.target.snapshot {
            return Err(FrontendContractError::new(
                "viewer_report_pdf_export_output_changed",
                format!(
                    "Viewer report output changed during generation: {}",
                    target.target.path.display()
                ),
            ));
        }
    }

    for index in 0..staged.len() {
        let current = inspect_target(
            &staged[index].target.path,
            staged[index].target.maximum_previous_bytes,
            "Viewer report publication output",
        );
        let publish = match current {
            Ok(snapshot) if snapshot == staged[index].target.snapshot => {
                publish_one(&mut staged[index]).map_err(|error| error.to_string())
            }
            Ok(_) => Err(format!(
                "Viewer report output changed immediately before publication: {}",
                staged[index].target.path.display()
            )),
            Err(error) => Err(error.to_string()),
        };
        if let Err(error) = publish {
            let rollback = rollback_publication(&mut staged);
            let detail = match rollback {
                Ok(()) => format!("publish verified Viewer report output failed: {error}"),
                Err(rollback_error) => format!(
                    "publish verified Viewer report output failed: {error}; rollback also failed: {rollback_error}"
                ),
            };
            return Err(FrontendContractError::new(
                "viewer_report_pdf_export_publish_failed",
                detail,
            ));
        }
    }
    for target in &mut staged {
        if let Some(backup) = target.backup_path.take() {
            fs::remove_file(&backup).map_err(|error| {
                FrontendContractError::new(
                    "viewer_report_pdf_export_backup_cleanup_failed",
                    format!(
                        "verified output was published but old output backup cleanup failed: {error}"
                    ),
                )
            })?;
        }
    }
    Ok(())
}

fn stage_target(
    target: OutputTarget,
    bytes: &[u8],
    suffix: &str,
) -> Result<StagedTarget, FrontendContractError> {
    let parent = target.path.parent().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_report_pdf_export_stage_failed",
            "Viewer report publication target has no parent",
        )
    })?;
    for _ in 0..1024 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            ".structural-viewer-report-pdf-{}-{sequence}.{suffix}.part",
            std::process::id()
        ));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                if let Err(error) = file.write_all(bytes).and_then(|()| file.sync_all()) {
                    let _ignored = fs::remove_file(&path);
                    return Err(FrontendContractError::new(
                        "viewer_report_pdf_export_stage_failed",
                        format!("stage verified Viewer report output failed: {error}"),
                    ));
                }
                return Ok(StagedTarget {
                    target,
                    staged_path: path,
                    backup_path: None,
                    published: false,
                });
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(FrontendContractError::new(
                    "viewer_report_pdf_export_stage_failed",
                    format!("create Viewer report staging file failed: {error}"),
                ));
            }
        }
    }
    Err(FrontendContractError::new(
        "viewer_report_pdf_export_stage_failed",
        "could not allocate a unique Viewer report staging file",
    ))
}

fn publish_one(target: &mut StagedTarget) -> Result<(), std::io::Error> {
    if target.target.snapshot.state == "regular_file" {
        let backup = unique_unused_sibling(&target.target.path, "backup")?;
        fs::rename(&target.target.path, &backup)?;
        target.backup_path = Some(backup);
    }
    fs::rename(&target.staged_path, &target.target.path)?;
    target.published = true;
    Ok(())
}

fn unique_unused_sibling(path: &Path, suffix: &str) -> Result<PathBuf, std::io::Error> {
    let parent = path.parent().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::InvalidInput, "output has no parent")
    })?;
    for _ in 0..1024 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let candidate = parent.join(format!(
            ".structural-viewer-report-pdf-{}-{sequence}.{suffix}",
            std::process::id()
        ));
        match fs::symlink_metadata(&candidate) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(candidate),
            Ok(_) => {}
            Err(error) => return Err(error),
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "could not allocate a unique Viewer report backup path",
    ))
}

fn rollback_publication(targets: &mut [StagedTarget]) -> Result<(), String> {
    let mut failures = Vec::new();
    for target in targets.iter_mut().rev() {
        if target.published {
            if let Err(error) = fs::remove_file(&target.target.path) {
                failures.push(format!(
                    "remove new {} failed: {error}",
                    target.target.path.display()
                ));
                continue;
            }
            target.published = false;
        }
        if let Some(backup) = target.backup_path.take() {
            if let Err(error) = fs::rename(&backup, &target.target.path) {
                failures.push(format!(
                    "restore {} failed: {error}; backup retained at {}",
                    target.target.path.display(),
                    backup.display()
                ));
                target.backup_path = Some(backup);
            }
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(failures.join("; "))
    }
}

fn build_receipt(
    options: &ViewerReportPdfExportOptions,
    prepared: &PreparedExport,
    verification: &ViewerReportPdfSmokeReceiptV1,
    artifacts: Option<&GeneratedArtifacts>,
) -> Result<ViewerReportPdfExportReceiptV1, FrontendContractError> {
    let executed = artifacts.is_some();
    let mut receipt = ViewerReportPdfExportReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_report_pdf_export".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "published" } else { "planned" }.to_owned(),
        verification_receipt_hash: verification.receipt_hash.clone(),
        source_map_sha256: verification.source_map_sha256.clone(),
        frontend_contract_receipt_hash: verification.frontend_contract_receipt_hash.clone(),
        exporter_sha256: verification.exporter_sha256.clone(),
        query: options.query.clone(),
        minimum_pdf_bytes: options.minimum_pdf_bytes,
        requested_pdf_output: prepared.pdf.requested.clone(),
        requested_html_output: prepared.html.as_ref().map(|value| value.requested.clone()),
        published_pdf_path: executed
            .then(|| portable_path(&prepared.pdf.path, "published Viewer report PDF"))
            .transpose()?,
        published_html_path: if executed {
            prepared
                .html
                .as_ref()
                .map(|value| portable_path(&value.path, "published Viewer report HTML"))
                .transpose()?
        } else {
            None
        },
        pdf_previous_state: prepared.pdf.snapshot.state.to_owned(),
        pdf_previous_byte_length: prepared.pdf.snapshot.byte_length,
        pdf_previous_sha256: prepared.pdf.snapshot.sha256.clone(),
        html_previous_state: prepared
            .html
            .as_ref()
            .map(|value| value.snapshot.state.to_owned()),
        html_previous_byte_length: prepared
            .html
            .as_ref()
            .and_then(|value| value.snapshot.byte_length),
        html_previous_sha256: prepared
            .html
            .as_ref()
            .and_then(|value| value.snapshot.sha256.clone()),
        output_disposition: if executed {
            if prepared.html.is_some() {
                "verified_pdf_and_html_published"
            } else {
                "verified_pdf_published_html_removed"
            }
        } else {
            "not_created"
        }
        .to_owned(),
        publication_strategy: "bounded_staging_then_backup_rename_with_rollback".to_owned(),
        logical_command_template: verification.logical_command_template.clone(),
        pdf_byte_length: artifacts
            .map(|value| u64::try_from(value.pdf.len()))
            .transpose()
            .map_err(|_| receipt_error("Viewer report PDF length is not addressable"))?,
        pdf_sha256: artifacts.map(|value| sha256_identity(&value.pdf)),
        html_byte_length: artifacts
            .map(|value| u64::try_from(value.html.len()))
            .transpose()
            .map_err(|_| receipt_error("Viewer report HTML length is not addressable"))?,
        html_sha256: artifacts.map(|value| sha256_identity(&value.html)),
        pdf_text_status: verification.pdf_text_status.clone(),
        pdf_text_sha256: verification.pdf_text_sha256.clone(),
        node_runtime_required: verification.node_runtime_required,
        browser_runtime_required: verification.browser_runtime_required,
        rust_owned_listener_count: verification.rust_owned_listener_count,
        direct_processes_spawned: verification.direct_processes_spawned,
        successful_exit_codes: verification.successful_exit_codes.clone(),
        external_network_access_accounting: verification
            .external_network_access_accounting
            .clone(),
        deterministic_receipt: !executed,
        claim_boundary: "bounded transitional publication authority only; the retained Node exporter, Playwright, Chromium, internal loopback server, Viewer JavaScript rendering, and browser page requests remain outside Rust ownership; no native UI/PDF-generation parity, engineering approval, C5, or C6 is inferred"
            .to_owned(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new(
        "viewer_report_pdf_export_receipt_encode_failed",
        detail.to_owned(),
    )
}

fn hash_without_receipt_hash(
    receipt: &ViewerReportPdfExportReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!(
            "project Viewer report PDF export receipt failed: {error}"
        ))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("Viewer report PDF export receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize Viewer report PDF export receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}
