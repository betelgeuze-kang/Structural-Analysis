use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_contracts::sparse_product::{
    parse_sparse_linear_request_v1, SparseLinearResultIrDocumentV1,
};
use structural_report::{build_sparse_linear_report_v1, SparseLinearReportBundleV1};
use structural_runtime::{
    Runtime, RuntimeError, SparseLinearCheckpointReceiptV1, SparseLinearCheckpointV1,
    SparseLinearExecutionStatus, SparseLinearSolverStatus,
};

use crate::product::{artifact_entry, canonicalize_value, publish_artifact_directory};

/// Stable product boundary for one sparse PCG run or resume command.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SparseLinearProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl fmt::Display for SparseLinearProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => {
                write!(
                    formatter,
                    "sparse linear product I/O error {code}: {message}"
                )
            }
        }
    }
}

impl std::error::Error for SparseLinearProductError {}

impl From<ProductIrContractError> for SparseLinearProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for SparseLinearProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<crate::product::NativeAnalysisProductError> for SparseLinearProductError {
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

/// Deterministic artifacts for an active, completed, or numerically failed PCG boundary.
#[derive(Clone, Debug)]
pub struct SparseLinearRunOutcomeV1 {
    checkpoint: SparseLinearCheckpointV1,
    checkpoint_receipt: SparseLinearCheckpointReceiptV1,
    checkpoint_receipt_json: String,
    result_ir: Option<SparseLinearResultIrDocumentV1>,
    report: Option<SparseLinearReportBundleV1>,
    run_receipt_json: String,
}

impl SparseLinearRunOutcomeV1 {
    #[must_use]
    pub const fn checkpoint(&self) -> &SparseLinearCheckpointV1 {
        &self.checkpoint
    }

    #[must_use]
    pub fn checkpoint_bytes(&self) -> &[u8] {
        self.checkpoint.as_bytes()
    }

    #[must_use]
    pub const fn checkpoint_receipt(&self) -> &SparseLinearCheckpointReceiptV1 {
        &self.checkpoint_receipt
    }

    #[must_use]
    pub fn checkpoint_receipt_json(&self) -> &str {
        &self.checkpoint_receipt_json
    }

    #[must_use]
    pub fn result_ir_json(&self) -> Option<&str> {
        self.result_ir
            .as_ref()
            .map(SparseLinearResultIrDocumentV1::canonical_json)
    }

    #[must_use]
    pub const fn result_ir(&self) -> Option<&SparseLinearResultIrDocumentV1> {
        self.result_ir.as_ref()
    }

    #[must_use]
    pub fn report_ir_json(&self) -> Option<&str> {
        self.report
            .as_ref()
            .map(|value| value.report_ir.canonical_json())
    }

    #[must_use]
    pub fn report_document(&self) -> Option<&str> {
        self.report
            .as_ref()
            .map(|value| value.document_source.as_str())
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }

    #[must_use]
    pub fn is_complete(&self) -> bool {
        self.result_ir.is_some()
    }

    #[must_use]
    pub fn is_terminal_failure(&self) -> bool {
        self.checkpoint.state().execution_status == SparseLinearExecutionStatus::Terminal
            && self.checkpoint.state().solver_status != SparseLinearSolverStatus::Converged
    }
}

/// Execute or resume one strict bounded sparse request by a real iteration budget.
///
/// # Errors
///
/// Returns a typed product error for an invalid request/checkpoint, native execution failure, or
/// deterministic checkpoint, result, report, or receipt projection failure.
pub fn execute_sparse_linear_analysis(
    request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
    iteration_budget: u32,
) -> Result<SparseLinearRunOutcomeV1, SparseLinearProductError> {
    let request = parse_sparse_linear_request_v1(request_bytes)?;
    let runtime = Runtime::new()?;
    let progress =
        runtime.advance_sparse_linear_product(&request, checkpoint_bytes, iteration_budget)?;
    let checkpoint_receipt = progress.checkpoint.receipt();
    let checkpoint_receipt_json = canonicalize_value(
        &serde_json::to_value(&checkpoint_receipt).map_err(|_| ProductIrContractError {
            code: "sparse_checkpoint_receipt_encode_failed".to_owned(),
            path: "/checkpoint".to_owned(),
            detail: "sparse checkpoint receipt could not be represented as JSON".to_owned(),
        })?,
        "sparse_checkpoint_receipt_canonicalization_failed",
    )?;
    let report = progress
        .result_ir
        .as_ref()
        .map(build_sparse_linear_report_v1)
        .transpose()?;
    let status = if progress.result_ir.is_some() {
        "completed"
    } else if progress.checkpoint.state().execution_status == SparseLinearExecutionStatus::Terminal
    {
        "failed"
    } else {
        "active"
    };
    let run_receipt_json = build_run_receipt(
        request.request().case_id.as_str(),
        request.request_hash(),
        status,
        &progress.checkpoint,
        &checkpoint_receipt,
        &checkpoint_receipt_json,
        progress
            .result_ir
            .as_ref()
            .map(SparseLinearResultIrDocumentV1::canonical_json),
        report
            .as_ref()
            .map(|value| value.report_ir.canonical_json()),
        report.as_ref().map(|value| value.document_source.as_str()),
    )?;
    Ok(SparseLinearRunOutcomeV1 {
        checkpoint: progress.checkpoint,
        checkpoint_receipt,
        checkpoint_receipt_json,
        result_ir: progress.result_ir,
        report,
        run_receipt_json,
    })
}

/// Atomically publish the complete artifact set for the current PCG boundary.
///
/// # Errors
///
/// Returns a typed product error when create-new atomic publication, persistence, or artifact
/// path validation fails. No completed destination is published on failure.
pub fn publish_sparse_linear_analysis(
    output_directory: &Path,
    outcome: &SparseLinearRunOutcomeV1,
) -> Result<(), SparseLinearProductError> {
    let mut artifacts = vec![
        ("checkpoint.pcgcp", outcome.checkpoint_bytes()),
        (
            "checkpoint-receipt.json",
            outcome.checkpoint_receipt_json().as_bytes(),
        ),
        ("run-receipt.json", outcome.run_receipt_json().as_bytes()),
    ];
    if let (Some(result), Some(report), Some(document)) = (
        outcome.result_ir_json(),
        outcome.report_ir_json(),
        outcome.report_document(),
    ) {
        artifacts.push(("result-ir.json", result.as_bytes()));
        artifacts.push(("report-ir.json", report.as_bytes()));
        artifacts.push(("report.md", document.as_bytes()));
    }
    publish_artifact_directory(output_directory, &artifacts).map_err(Into::into)
}

#[allow(clippy::too_many_arguments)]
fn build_run_receipt(
    case_id: &str,
    request_hash: &str,
    status: &str,
    checkpoint: &SparseLinearCheckpointV1,
    checkpoint_receipt: &SparseLinearCheckpointReceiptV1,
    checkpoint_receipt_json: &str,
    result_ir: Option<&str>,
    report_ir: Option<&str>,
    report_document: Option<&str>,
) -> Result<String, SparseLinearProductError> {
    let mut artifacts = vec![
        artifact_entry(
            "checkpoint",
            "checkpoint.pcgcp",
            "application/vnd.structural.sparse-linear-checkpoint",
            checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "checkpoint_receipt",
            "checkpoint-receipt.json",
            "application/json",
            checkpoint_receipt_json.as_bytes(),
        )?,
    ];
    if let (Some(result), Some(report), Some(document)) = (result_ir, report_ir, report_document) {
        artifacts.push(artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            result.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            report.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown",
            document.as_bytes(),
        )?);
    }
    let mut receipt = json!({
        "schema_version": "structural-sparse-linear-run-receipt.v1",
        "case_id": case_id,
        "status": status,
        "solver_status": checkpoint_receipt.solver_status,
        "request_hash": request_hash,
        "checkpoint": checkpoint_receipt,
        "artifacts": artifacts,
        "claim_boundary": "bounded_canonical_csr_cpu_pcg_product_flow_not_whole_model_assembly_hip_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            SparseLinearProductError::Contract(ProductIrContractError {
                code: "sparse_run_receipt_invariant_failed".to_owned(),
                path: "/".to_owned(),
                detail: "sparse run receipt is not an object".to_owned(),
            })
        })?;
    let unsigned = canonicalize_value(&receipt, "sparse_run_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "sparse_run_receipt_canonicalization_failed").map_err(Into::into)
}
