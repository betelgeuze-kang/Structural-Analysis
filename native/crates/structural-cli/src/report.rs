use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::product_ir::{
    parse_nonlinear_ndtha_report_ir_v1, parse_nonlinear_ndtha_result_ir_v1, sha256_identity,
    ProductIrContractError,
};
use structural_report::{render_nonlinear_ndtha_pdf_v1, PdfRenderError};

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

fn receipt_error(detail: &str) -> NativePdfReportError {
    NativePdfReportError::Contract(ProductIrContractError {
        code: "pdf_receipt_invariant_failed".to_owned(),
        path: "/".to_owned(),
        detail: detail.to_owned(),
    })
}
