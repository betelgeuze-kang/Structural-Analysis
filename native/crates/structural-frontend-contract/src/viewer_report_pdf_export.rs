use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

use serde::Serialize;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, read_bounded_regular_file, run_viewer_report_pdf_smoke,
    verify_real_directory, FrontendContractError, ViewerReportPdfSmokeOptions,
    ViewerReportPdfSmokeReceiptV1,
};
use crate::verified_publication::{
    portable_publication_path, prepare_verified_publication_target, publish_verified_outputs,
    VerifiedOutput, VerifiedPublicationCodes, VerifiedPublicationTarget,
    VERIFIED_PUBLICATION_STRATEGY,
};

const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-report-pdf-export-receipt.v1";
const DEFAULT_PDF_OUTPUT: &str = "structure_viewer_report.pdf";
const MAX_PDF_BYTES: u64 = 128 * 1024 * 1024;
const MAX_HTML_BYTES: u64 = 32 * 1024 * 1024;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const PUBLICATION_CODES: VerifiedPublicationCodes = VerifiedPublicationCodes {
    output_invalid: "viewer_report_pdf_export_output_invalid",
    output_changed: "viewer_report_pdf_export_output_changed",
    stage_failed: "viewer_report_pdf_export_stage_failed",
    publish_failed: "viewer_report_pdf_export_publish_failed",
    backup_cleanup_failed: "viewer_report_pdf_export_backup_cleanup_failed",
};

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

struct PreparedExport {
    pdf: VerifiedPublicationTarget,
    html: Option<VerifiedPublicationTarget>,
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
    let pdf = prepare_verified_publication_target(
        &root,
        &options.output,
        MAX_PDF_BYTES,
        "Viewer report PDF output",
        PUBLICATION_CODES,
    )?;
    let html = options
        .html_output
        .as_ref()
        .map(|path| {
            prepare_verified_publication_target(
                &root,
                path,
                MAX_HTML_BYTES,
                "Viewer report HTML output",
                PUBLICATION_CODES,
            )
        })
        .transpose()?;
    if html.as_ref().is_some_and(|value| value.path == pdf.path) {
        return Err(FrontendContractError::new(
            "viewer_report_pdf_export_output_alias",
            "Viewer report PDF and HTML outputs must be different files",
        ));
    }
    Ok(PreparedExport { pdf, html })
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
    let mut outputs = Vec::with_capacity(if prepared.html.is_some() { 2 } else { 1 });
    if let Some(html) = &prepared.html {
        outputs.push(VerifiedOutput {
            target: html.clone(),
            bytes: &artifacts.html,
            suffix: "html",
        });
    }
    outputs.push(VerifiedOutput {
        target: prepared.pdf.clone(),
        bytes: &artifacts.pdf,
        suffix: "pdf",
    });
    publish_verified_outputs(outputs, PUBLICATION_CODES)
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
            .then(|| {
                portable_publication_path(
                    &prepared.pdf.path,
                    "published Viewer report PDF",
                    PUBLICATION_CODES,
                )
            })
            .transpose()?,
        published_html_path: if executed {
            prepared
                .html
                .as_ref()
                .map(|value| {
                    portable_publication_path(
                        &value.path,
                        "published Viewer report HTML",
                        PUBLICATION_CODES,
                    )
                })
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
        publication_strategy: VERIFIED_PUBLICATION_STRATEGY.to_owned(),
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
