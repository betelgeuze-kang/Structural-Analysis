//! CLI composition boundary shared by the binary and future API adapter.

#![forbid(unsafe_code)]

mod comparison;
mod job;
mod mgt_product;
mod model_linear_product;
mod model_product;
mod product;
mod report;
mod service;
mod sparse_product;
mod spectral_product;
mod static_product;

use std::fmt;

use serde_json::json;
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError};
use structural_runtime::{ModelIrValidation, Runtime, RuntimeError};

pub use comparison::{
    execute_external_comparison, publish_external_comparison, NativeComparisonProductError,
    NativeExternalComparisonOutcomeV1,
};
pub use job::{execute_next_durable_job, export_durable_job, DurableJobCommandError};
pub use mgt_product::{
    execute_native_mgt_import, publish_native_mgt_import, NativeMgtImportOutcomeV1,
    NativeMgtImportProductError,
};
pub use model_linear_product::{
    execute_model_ir_linear_analysis, publish_model_ir_linear_analysis,
    ModelIrLinearAnalysisOutcomeV1, ModelIrLinearProductError,
};
pub use model_product::{
    execute_model_ir_native_analysis, publish_model_ir_native_analysis,
    ModelIrNativeAnalysisOutcomeV1,
};
pub use product::{
    execute_native_analysis, publish_native_analysis, NativeAnalysisProductError,
    NativeAnalysisRunOutcomeV1,
};
pub use report::{
    execute_localized_pdf_report, execute_pdf_report, publish_localized_pdf_report,
    publish_pdf_report, NativeLocalizedPdfReportOutcomeV2, NativePdfReportError,
    NativePdfReportOutcomeV1,
};
pub use service::{
    load_native_job_api_credentials, NativeJobApiCredentialsV1, NativeJobApiError,
    NativeJobApiServeReceiptV1, NativeJobApiServerConfigV1, NativeJobApiServerV1,
    NATIVE_JOB_API_PROFILE_V1,
};
pub use sparse_product::{
    execute_sparse_linear_analysis, publish_sparse_linear_analysis, SparseLinearProductError,
    SparseLinearRunOutcomeV1,
};
pub use spectral_product::{
    execute_dense_spectral_analysis, publish_dense_spectral_analysis, DenseSpectralProductError,
    DenseSpectralRunOutcomeV1,
};
pub use static_product::{
    execute_nonlinear_static_analysis, publish_nonlinear_static_analysis,
    NonlinearStaticProductError, NonlinearStaticRunOutcomeV1,
};
pub use structural_report::PdfReportLocaleV2;

/// Failure boundary for a complete native `ModelIR` validation request.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelValidationError {
    Contract(ModelIrContractError),
    Runtime(RuntimeError),
}

impl fmt::Display for ModelValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for ModelValidationError {}

/// Load the current CPU-only native runtime and return its declared capabilities.
///
/// # Errors
///
/// Returns a runtime-layer error when the native ABI cannot be loaded.
pub fn probe_native_runtime() -> Result<u64, RuntimeError> {
    Runtime::new().map(|runtime| runtime.native_capabilities())
}

/// Strictly parse and fully round-trip one `ModelIR` v2 byte stream through C++.
///
/// # Errors
///
/// Returns a Rust contract error before FFI for invalid wire input, or a runtime error for
/// native ABI/report/snapshot failures. Semantic invalidity is a successful typed report.
pub fn validate_model_bytes(bytes: &[u8]) -> Result<ModelIrValidation, ModelValidationError> {
    let document = parse_model_ir_v2(bytes).map_err(ModelValidationError::Contract)?;
    Runtime::new()
        .map_err(ModelValidationError::Runtime)?
        .validate_model_ir(&document)
        .map_err(ModelValidationError::Runtime)
}

/// Render a deterministic, versioned pre-FFI failure report for invalid `ModelIR` wire input.
#[must_use]
pub fn contract_error_report(error: &ModelIrContractError) -> String {
    let issues = if error.issues.is_empty() {
        vec![json!({
            "code": error.code,
            "path": error.path,
            "detail": error.detail,
        })]
    } else {
        error
            .issues
            .iter()
            .map(|issue| {
                json!({
                    "code": issue.code,
                    "path": issue.path,
                    "detail": issue.detail,
                })
            })
            .collect()
    };
    json!({
        "schema_version": "structural-model-ir-rust-validation.v1",
        "model_ir_schema_version": "structural-analysis-model-ir.v2",
        "schema_valid": false,
        "semantics_valid": false,
        "contract_valid": false,
        "analysis_ready": false,
        "issues": issues,
        "blocking_feature_ids": [],
        "declared_blocking_feature_ids": [],
        "derived_blocking_feature_ids": [],
        "claim_boundary": "model_ir_wire_validation_before_native_semantics"
    })
    .to_string()
}

/// Decide the validation command outcome without conflating blockers with contract invalidity.
#[must_use]
pub const fn validation_succeeds(
    contract_valid: bool,
    analysis_ready: bool,
    require_analysis_ready: bool,
) -> bool {
    contract_valid && (!require_analysis_ready || analysis_ready)
}

#[cfg(test)]
mod tests {
    use super::{probe_native_runtime, validation_succeeds};

    #[test]
    fn cli_composition_reaches_the_current_native_api_table() {
        assert_eq!(probe_native_runtime(), Ok(255));
    }

    #[test]
    fn readiness_is_an_explicit_stricter_policy() {
        assert!(validation_succeeds(true, true, false));
        assert!(validation_succeeds(true, false, false));
        assert!(!validation_succeeds(true, false, true));
        assert!(!validation_succeeds(false, false, false));
    }
}
