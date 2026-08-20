use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_contracts::spectral_product::{
    parse_dense_spectral_request_v1, DenseSpectralResultIrDocumentV1,
};
use structural_report::{build_dense_spectral_report_v1, DenseSpectralReportBundleV1};
use structural_runtime::{
    DenseSpectralCheckpointReceiptV1, DenseSpectralCheckpointV1, Runtime, RuntimeError,
};

use crate::product::{artifact_entry, canonicalize_value, publish_artifact_directory};

/// Stable product boundary for one dense modal/buckling command.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DenseSpectralProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl fmt::Display for DenseSpectralProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => {
                write!(formatter, "spectral product I/O error {code}: {message}")
            }
        }
    }
}

impl std::error::Error for DenseSpectralProductError {}

impl From<ProductIrContractError> for DenseSpectralProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for DenseSpectralProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<crate::product::NativeAnalysisProductError> for DenseSpectralProductError {
    fn from(error: crate::product::NativeAnalysisProductError) -> Self {
        match error {
            crate::product::NativeAnalysisProductError::Contract(error) => Self::Contract(error),
            crate::product::NativeAnalysisProductError::Runtime(error) => Self::Runtime(error),
            crate::product::NativeAnalysisProductError::Io { code, message } => {
                Self::Io { code, message }
            }
        }
    }
}

/// Complete deterministic product artifacts from one atomic dense eigensolve.
#[derive(Clone, Debug)]
pub struct DenseSpectralRunOutcomeV1 {
    checkpoint: DenseSpectralCheckpointV1,
    checkpoint_receipt: DenseSpectralCheckpointReceiptV1,
    result_ir: DenseSpectralResultIrDocumentV1,
    report: DenseSpectralReportBundleV1,
    run_receipt_json: String,
}

impl DenseSpectralRunOutcomeV1 {
    #[must_use]
    pub const fn checkpoint(&self) -> &DenseSpectralCheckpointV1 {
        &self.checkpoint
    }

    #[must_use]
    pub fn checkpoint_bytes(&self) -> &[u8] {
        self.checkpoint.as_bytes()
    }

    #[must_use]
    pub const fn checkpoint_receipt(&self) -> &DenseSpectralCheckpointReceiptV1 {
        &self.checkpoint_receipt
    }

    #[must_use]
    pub fn result_ir_json(&self) -> &str {
        self.result_ir.canonical_json()
    }

    #[must_use]
    pub fn report_ir_json(&self) -> &str {
        self.report.report_ir.canonical_json()
    }

    #[must_use]
    pub fn report_document(&self) -> &str {
        &self.report.document_source
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }
}

/// Execute or resume one strict bounded dense spectral request.
///
/// # Errors
///
/// Returns a stable contract/runtime error before publishing anything.
pub fn execute_dense_spectral_analysis(
    request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
) -> Result<DenseSpectralRunOutcomeV1, DenseSpectralProductError> {
    let request = parse_dense_spectral_request_v1(request_bytes)?;
    let runtime = Runtime::new()?;
    let product = runtime.execute_dense_spectral_product(&request, checkpoint_bytes)?;
    let checkpoint_receipt = product.checkpoint.receipt();
    let report = build_dense_spectral_report_v1(&product.result_ir)?;
    let run_receipt_json = build_run_receipt(
        request.request().case_id.as_str(),
        &request.request().analysis_kind.to_string(),
        request.request_hash(),
        &product.checkpoint,
        &checkpoint_receipt,
        product.result_ir.canonical_json(),
        report.report_ir.canonical_json(),
        &report.document_source,
    )?;
    Ok(DenseSpectralRunOutcomeV1 {
        checkpoint: product.checkpoint,
        checkpoint_receipt,
        result_ir: product.result_ir,
        report,
        run_receipt_json,
    })
}

/// Atomically publish a complete spectral result into a new directory.
///
/// # Errors
///
/// Returns an I/O error without overwriting an existing destination.
pub fn publish_dense_spectral_analysis(
    output_directory: &Path,
    outcome: &DenseSpectralRunOutcomeV1,
) -> Result<(), DenseSpectralProductError> {
    let artifacts = [
        ("checkpoint.eigcp", outcome.checkpoint_bytes()),
        ("result-ir.json", outcome.result_ir_json().as_bytes()),
        ("report-ir.json", outcome.report_ir_json().as_bytes()),
        ("report.md", outcome.report_document().as_bytes()),
        ("run-receipt.json", outcome.run_receipt_json().as_bytes()),
    ];
    publish_artifact_directory(output_directory, &artifacts).map_err(Into::into)
}

#[allow(clippy::too_many_arguments)]
fn build_run_receipt(
    case_id: &str,
    analysis_kind: &str,
    request_hash: &str,
    checkpoint: &DenseSpectralCheckpointV1,
    checkpoint_receipt: &DenseSpectralCheckpointReceiptV1,
    result_ir: &str,
    report_ir: &str,
    report_document: &str,
) -> Result<String, DenseSpectralProductError> {
    let artifacts = vec![
        artifact_entry(
            "checkpoint",
            "checkpoint.eigcp",
            "application/vnd.structural.dense-spectral-checkpoint",
            checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            result_ir.as_bytes(),
        )?,
        artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            report_ir.as_bytes(),
        )?,
        artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown",
            report_document.as_bytes(),
        )?,
    ];
    let mut receipt = json!({
        "schema_version": "structural-dense-spectral-run-receipt.v1",
        "case_id": case_id,
        "analysis_kind": analysis_kind,
        "status": "completed",
        "request_hash": request_hash,
        "checkpoint": checkpoint_receipt,
        "artifacts": artifacts,
        "claim_boundary": "bounded_dense_cpu_modal_or_buckling_product_flow_not_sparse_whole_model_hip_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            DenseSpectralProductError::Contract(ProductIrContractError {
                code: "spectral_run_receipt_invariant_failed".to_owned(),
                path: "/".to_owned(),
                detail: "spectral run receipt is not an object".to_owned(),
            })
        })?;
    let unsigned = canonicalize_value(&receipt, "spectral_run_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "spectral_run_receipt_canonicalization_failed").map_err(Into::into)
}
