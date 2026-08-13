use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::product_ir::{
    parse_nonlinear_ndtha_report_ir_v1, parse_nonlinear_ndtha_result_ir_v1, sha256_identity,
    ProductIrContractError,
};
use structural_contracts::sparse_product::{
    parse_sparse_linear_report_ir_v1, parse_sparse_linear_result_ir_v1,
};
use structural_report::{
    render_nonlinear_ndtha_localized_pdf_v2, render_nonlinear_ndtha_pdf_v1,
    render_sparse_linear_localized_pdf_v2, render_sparse_linear_pdf_v1, PdfRenderError,
    PdfReportLocaleV2,
};

use crate::product::{
    artifact_entry, canonicalize_value, publish_artifact_directory, NativeAnalysisProductError,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NativePdfReportError {
    Contract(ProductIrContractError),
    Render(PdfRenderError),
    Product(NativeAnalysisProductError),
}

impl NativePdfReportError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        match self {
            Self::Contract(_) => true,
            Self::Render(error) => error.is_input_error(),
            Self::Product(_) => false,
        }
    }
}

impl fmt::Display for NativePdfReportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Render(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for NativePdfReportError {}

impl From<ProductIrContractError> for NativePdfReportError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<PdfRenderError> for NativePdfReportError {
    fn from(error: PdfRenderError) -> Self {
        Self::Render(error)
    }
}

impl From<NativeAnalysisProductError> for NativePdfReportError {
    fn from(error: NativeAnalysisProductError) -> Self {
        Self::Product(error)
    }
}

#[derive(Clone, Debug)]
pub struct NativePdfReportOutcomeV1 {
    pdf_bytes: Vec<u8>,
    receipt_json: String,
}

#[derive(Clone, Debug)]
pub struct NativeLocalizedPdfReportOutcomeV2 {
    pdf_bytes: Vec<u8>,
    receipt_json: String,
}

impl NativeLocalizedPdfReportOutcomeV2 {
    #[must_use]
    pub fn pdf_bytes(&self) -> &[u8] {
        &self.pdf_bytes
    }

    #[must_use]
    pub fn receipt_json(&self) -> &str {
        &self.receipt_json
    }
}

impl NativePdfReportOutcomeV1 {
    #[must_use]
    pub fn pdf_bytes(&self) -> &[u8] {
        &self.pdf_bytes
    }

    #[must_use]
    pub fn receipt_json(&self) -> &str {
        &self.receipt_json
    }
}

/// Verify exact ResultIR/ReportIR/Markdown bindings and render one deterministic native PDF.
///
/// # Errors
///
/// Rejects malformed or forged inputs, projection mismatch, PDF structure failure and receipt
/// canonicalization errors.
pub fn execute_pdf_report(
    result_ir_bytes: &[u8],
    report_ir_bytes: &[u8],
    document_source_bytes: &[u8],
) -> Result<NativePdfReportOutcomeV1, NativePdfReportError> {
    let result = parse_nonlinear_ndtha_result_ir_v1(result_ir_bytes)?;
    let report = parse_nonlinear_ndtha_report_ir_v1(report_ir_bytes)?;
    let pdf = render_nonlinear_ndtha_pdf_v1(&result, &report, document_source_bytes)?;
    let receipt_json = build_pdf_receipt(
        result.result().case_id.as_str(),
        pdf.source_result_hash(),
        pdf.source_report_hash(),
        pdf.document_source_hash(),
        pdf.pdf_hash(),
        pdf.claim_boundary(),
        pdf.as_bytes(),
    )?;
    Ok(NativePdfReportOutcomeV1 {
        pdf_bytes: pdf.as_bytes().to_vec(),
        receipt_json,
    })
}

/// Verify exact sparse ResultIR/ReportIR/Markdown bindings and render a deterministic native PDF.
///
/// # Errors
///
/// Rejects malformed or forged sparse inputs, projection mismatch, PDF structure failure, and
/// receipt canonicalization errors.
pub fn execute_sparse_linear_pdf_report(
    result_ir_bytes: &[u8],
    report_ir_bytes: &[u8],
    document_source_bytes: &[u8],
) -> Result<NativePdfReportOutcomeV1, NativePdfReportError> {
    let result = parse_sparse_linear_result_ir_v1(result_ir_bytes)?;
    let report = parse_sparse_linear_report_ir_v1(report_ir_bytes)?;
    let pdf = render_sparse_linear_pdf_v1(&result, &report, document_source_bytes)?;
    let receipt_json = build_sparse_pdf_receipt(
        result.result().case_id.as_str(),
        pdf.source_result_hash(),
        pdf.source_report_hash(),
        pdf.document_source_hash(),
        pdf.pdf_hash(),
        pdf.claim_boundary(),
        pdf.as_bytes(),
    )?;
    Ok(NativePdfReportOutcomeV1 {
        pdf_bytes: pdf.as_bytes().to_vec(),
        receipt_json,
    })
}

/// Verify exact sparse source bindings and render one deterministic embedded-font localized PDF.
///
/// # Errors
///
/// Rejects malformed or forged sparse inputs, fixed-locale/glyph violations, embedded-font
/// identity drift, PDF structure failure, and receipt canonicalization errors.
pub fn execute_sparse_linear_localized_pdf_report(
    result_ir_bytes: &[u8],
    report_ir_bytes: &[u8],
    document_source_bytes: &[u8],
    locale: PdfReportLocaleV2,
) -> Result<NativeLocalizedPdfReportOutcomeV2, NativePdfReportError> {
    let result = parse_sparse_linear_result_ir_v1(result_ir_bytes)?;
    let report = parse_sparse_linear_report_ir_v1(report_ir_bytes)?;
    let pdf =
        render_sparse_linear_localized_pdf_v2(&result, &report, document_source_bytes, locale)?;
    let receipt_json = build_sparse_localized_pdf_receipt(
        result.result().case_id.as_str(),
        locale,
        pdf.source_result_hash(),
        pdf.source_report_hash(),
        pdf.document_source_hash(),
        pdf.pdf_hash(),
        pdf.embedded_font_hash(),
        pdf.embedded_font_byte_length(),
        pdf.embedded_font_postscript_name(),
        pdf.embedded_font_license_notice_hash(),
        pdf.embedded_font_license_notice_byte_length(),
        pdf.embedded_font_provenance_hash(),
        pdf.embedded_font_provenance_byte_length(),
        pdf.claim_boundary(),
        pdf.as_bytes(),
    )?;
    Ok(NativeLocalizedPdfReportOutcomeV2 {
        pdf_bytes: pdf.as_bytes().to_vec(),
        receipt_json,
    })
}

/// Verify exact source bindings and render one deterministic embedded-font localized PDF.
///
/// # Errors
///
/// Rejects malformed or forged inputs, fixed-locale/glyph violations, embedded-font identity
/// drift, PDF structure failure, and receipt canonicalization errors.
pub fn execute_localized_pdf_report(
    result_ir_bytes: &[u8],
    report_ir_bytes: &[u8],
    document_source_bytes: &[u8],
    locale: PdfReportLocaleV2,
) -> Result<NativeLocalizedPdfReportOutcomeV2, NativePdfReportError> {
    let result = parse_nonlinear_ndtha_result_ir_v1(result_ir_bytes)?;
    let report = parse_nonlinear_ndtha_report_ir_v1(report_ir_bytes)?;
    let pdf =
        render_nonlinear_ndtha_localized_pdf_v2(&result, &report, document_source_bytes, locale)?;
    let receipt_json = build_localized_pdf_receipt(
        result.result().case_id.as_str(),
        locale,
        pdf.source_result_hash(),
        pdf.source_report_hash(),
        pdf.document_source_hash(),
        pdf.pdf_hash(),
        pdf.embedded_font_hash(),
        pdf.embedded_font_byte_length(),
        pdf.embedded_font_postscript_name(),
        pdf.embedded_font_license_notice_hash(),
        pdf.embedded_font_license_notice_byte_length(),
        pdf.embedded_font_provenance_hash(),
        pdf.embedded_font_provenance_byte_length(),
        pdf.claim_boundary(),
        pdf.as_bytes(),
    )?;
    Ok(NativeLocalizedPdfReportOutcomeV2 {
        pdf_bytes: pdf.as_bytes().to_vec(),
        receipt_json,
    })
}

/// Atomically publish `report.pdf` and its self-hashed receipt into one new directory.
///
/// # Errors
///
/// Returns an I/O error if the destination exists or durable directory publication fails.
pub fn publish_pdf_report(
    output_directory: &Path,
    outcome: &NativePdfReportOutcomeV1,
) -> Result<(), NativePdfReportError> {
    publish_artifact_directory(
        output_directory,
        &[
            ("report.pdf", outcome.pdf_bytes()),
            ("pdf-receipt.json", outcome.receipt_json().as_bytes()),
        ],
    )?;
    Ok(())
}

/// Atomically publish one localized `report.pdf` and self-hashed v2 receipt into a new directory.
///
/// # Errors
///
/// Returns an I/O error if the destination exists or durable directory publication fails.
pub fn publish_localized_pdf_report(
    output_directory: &Path,
    outcome: &NativeLocalizedPdfReportOutcomeV2,
) -> Result<(), NativePdfReportError> {
    publish_artifact_directory(
        output_directory,
        &[
            ("report.pdf", outcome.pdf_bytes()),
            ("pdf-receipt.json", outcome.receipt_json().as_bytes()),
        ],
    )?;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn build_pdf_receipt(
    case_id: &str,
    source_result_hash: &str,
    source_report_hash: &str,
    document_source_hash: &str,
    pdf_hash: &str,
    pdf_claim_boundary: &str,
    pdf_bytes: &[u8],
) -> Result<String, NativePdfReportError> {
    let mut receipt = json!({
        "schema_version": "structural-native-pdf-report-receipt.v1",
        "case_id": case_id,
        "source_result_hash": source_result_hash,
        "source_report_hash": source_report_hash,
        "document_source_hash": document_source_hash,
        "pdf_hash": pdf_hash,
        "pdf_claim_boundary": pdf_claim_boundary,
        "artifacts": [artifact_entry(
            "pdf_report",
            "report.pdf",
            "application/pdf",
            pdf_bytes,
        )?],
        "claim_boundary": "inventory_for_one_deterministic_bounded_candidate_pdf_not_pdf_a_accessibility_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| receipt_error("PDF receipt is not an object"))?;
    let unsigned = canonicalize_value(&receipt, "pdf_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("PDF receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "pdf_receipt_canonicalization_failed").map_err(Into::into)
}

#[allow(clippy::too_many_arguments)]
fn build_sparse_pdf_receipt(
    case_id: &str,
    source_result_hash: &str,
    source_report_hash: &str,
    document_source_hash: &str,
    pdf_hash: &str,
    pdf_claim_boundary: &str,
    pdf_bytes: &[u8],
) -> Result<String, NativePdfReportError> {
    let mut receipt = json!({
        "schema_version": "structural-native-sparse-linear-pdf-report-receipt.v1",
        "case_id": case_id,
        "source_result_hash": source_result_hash,
        "source_report_hash": source_report_hash,
        "document_source_hash": document_source_hash,
        "pdf_hash": pdf_hash,
        "pdf_claim_boundary": pdf_claim_boundary,
        "artifacts": [artifact_entry(
            "sparse_linear_pdf_report",
            "report.pdf",
            "application/pdf",
            pdf_bytes,
        )?],
        "claim_boundary": "inventory_for_one_deterministic_bounded_sparse_linear_candidate_pdf_not_pdf_a_accessibility_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| receipt_error("sparse PDF receipt is not an object"))?;
    let unsigned = canonicalize_value(&receipt, "sparse_pdf_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("sparse PDF receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "sparse_pdf_receipt_canonicalization_failed").map_err(Into::into)
}

#[allow(clippy::too_many_arguments)]
fn build_localized_pdf_receipt(
    case_id: &str,
    locale: PdfReportLocaleV2,
    source_result_hash: &str,
    source_report_hash: &str,
    document_source_hash: &str,
    pdf_hash: &str,
    embedded_font_hash: &str,
    embedded_font_byte_length: usize,
    embedded_font_postscript_name: &str,
    license_notice_hash: &str,
    license_notice_byte_length: usize,
    provenance_hash: &str,
    provenance_byte_length: usize,
    pdf_claim_boundary: &str,
    pdf_bytes: &[u8],
) -> Result<String, NativePdfReportError> {
    let mut receipt = json!({
        "schema_version": "structural-native-localized-pdf-report-receipt.v2",
        "case_id": case_id,
        "locale": locale.language_tag(),
        "source_result_hash": source_result_hash,
        "source_report_hash": source_report_hash,
        "document_source_hash": document_source_hash,
        "pdf_hash": pdf_hash,
        "pdf_claim_boundary": pdf_claim_boundary,
        "embedded_font": {
            "postscript_name": embedded_font_postscript_name,
            "content_hash": embedded_font_hash,
            "byte_length": u64::try_from(embedded_font_byte_length).map_err(|_| {
                receipt_error("embedded font byte length exceeds the receipt integer boundary")
            })?,
            "license": {
                "id": "OFL-1.1",
                "distribution_path": "share/structural-report/OFL-1.1.txt",
                "content_hash": license_notice_hash,
                "byte_length": u64::try_from(license_notice_byte_length).map_err(|_| {
                    receipt_error("font license notice byte length exceeds the receipt integer boundary")
                })?
            },
            "provenance": {
                "distribution_path": "share/structural-report/StructuralReportKoreanSubset.provenance.json",
                "content_hash": provenance_hash,
                "byte_length": u64::try_from(provenance_byte_length).map_err(|_| {
                    receipt_error("font provenance byte length exceeds the receipt integer boundary")
                })?
            }
        },
        "artifacts": [artifact_entry(
            "localized_pdf_report",
            "report.pdf",
            "application/pdf",
            pdf_bytes,
        )?],
        "claim_boundary": "inventory_for_one_deterministic_bounded_fixed_en_us_or_ko_kr_embedded_font_candidate_pdf_not_arbitrary_unicode_pdf_ua_accessibility_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| receipt_error("localized PDF receipt is not an object"))?;
    let unsigned = canonicalize_value(&receipt, "localized_pdf_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("localized PDF receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "localized_pdf_receipt_canonicalization_failed")
        .map_err(Into::into)
}

#[allow(clippy::too_many_arguments)]
fn build_sparse_localized_pdf_receipt(
    case_id: &str,
    locale: PdfReportLocaleV2,
    source_result_hash: &str,
    source_report_hash: &str,
    document_source_hash: &str,
    pdf_hash: &str,
    embedded_font_hash: &str,
    embedded_font_byte_length: usize,
    embedded_font_postscript_name: &str,
    license_notice_hash: &str,
    license_notice_byte_length: usize,
    provenance_hash: &str,
    provenance_byte_length: usize,
    pdf_claim_boundary: &str,
    pdf_bytes: &[u8],
) -> Result<String, NativePdfReportError> {
    let mut receipt = json!({
        "schema_version": "structural-native-sparse-linear-localized-pdf-report-receipt.v2",
        "profile": "sparse_linear_cpu_v1",
        "case_id": case_id,
        "locale": locale.language_tag(),
        "source_result_hash": source_result_hash,
        "source_report_hash": source_report_hash,
        "document_source_hash": document_source_hash,
        "pdf_hash": pdf_hash,
        "pdf_claim_boundary": pdf_claim_boundary,
        "embedded_font": {
            "postscript_name": embedded_font_postscript_name,
            "content_hash": embedded_font_hash,
            "byte_length": u64::try_from(embedded_font_byte_length).map_err(|_| {
                receipt_error("embedded font byte length exceeds the receipt integer boundary")
            })?,
            "license": {
                "id": "OFL-1.1",
                "distribution_path": "share/structural-report/OFL-1.1.txt",
                "content_hash": license_notice_hash,
                "byte_length": u64::try_from(license_notice_byte_length).map_err(|_| {
                    receipt_error("font license notice byte length exceeds the receipt integer boundary")
                })?
            },
            "provenance": {
                "distribution_path": "share/structural-report/StructuralReportKoreanSubset.provenance.json",
                "content_hash": provenance_hash,
                "byte_length": u64::try_from(provenance_byte_length).map_err(|_| {
                    receipt_error("font provenance byte length exceeds the receipt integer boundary")
                })?
            }
        },
        "artifacts": [artifact_entry(
            "sparse_linear_localized_pdf_report",
            "report.pdf",
            "application/pdf",
            pdf_bytes,
        )?],
        "claim_boundary": "inventory_for_one_deterministic_bounded_sparse_linear_fixed_en_us_or_ko_kr_embedded_font_candidate_pdf_not_arbitrary_unicode_pdf_ua_accessibility_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| receipt_error("sparse localized PDF receipt is not an object"))?;
    let unsigned = canonicalize_value(
        &receipt,
        "sparse_localized_pdf_receipt_canonicalization_failed",
    )?;
    receipt
        .as_object_mut()
        .expect("sparse localized PDF receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(
        &receipt,
        "sparse_localized_pdf_receipt_canonicalization_failed",
    )
    .map_err(Into::into)
}

fn receipt_error(detail: &str) -> NativePdfReportError {
    NativePdfReportError::Contract(ProductIrContractError {
        code: "pdf_receipt_invariant_failed".to_owned(),
        path: "/".to_owned(),
        detail: detail.to_owned(),
    })
}
