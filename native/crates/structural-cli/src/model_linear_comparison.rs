use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::external_comparison::ExternalComparisonStatusV1;
use structural_contracts::model_linear_comparison::{
    build_model_ir_linear_external_comparison_ir_v1, parse_model_ir_linear_external_result_v1,
};
use structural_contracts::model_linear_recovery::parse_model_ir_linear_result_recovery_ir_v1;
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_contracts::sparse_product::parse_sparse_linear_result_ir_v1;

use crate::product::{
    artifact_entry, canonicalize_value, publish_artifact_directory, NativeAnalysisProductError,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelIrLinearComparisonProductError {
    Contract(ProductIrContractError),
    Product(NativeAnalysisProductError),
}

impl ModelIrLinearComparisonProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for ModelIrLinearComparisonProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for ModelIrLinearComparisonProductError {}

impl From<ProductIrContractError> for ModelIrLinearComparisonProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<NativeAnalysisProductError> for ModelIrLinearComparisonProductError {
    fn from(error: NativeAnalysisProductError) -> Self {
        Self::Product(error)
    }
}

#[derive(Clone, Debug)]
pub struct ModelIrLinearExternalComparisonOutcomeV1 {
    status: ExternalComparisonStatusV1,
    comparison_ir_json: String,
    receipt_json: String,
}

impl ModelIrLinearExternalComparisonOutcomeV1 {
    #[must_use]
    pub const fn status(&self) -> ExternalComparisonStatusV1 {
        self.status
    }

    #[must_use]
    pub fn passed(&self) -> bool {
        self.status == ExternalComparisonStatusV1::Passed
    }

    #[must_use]
    pub fn comparison_ir_json(&self) -> &str {
        &self.comparison_ir_json
    }

    #[must_use]
    pub fn receipt_json(&self) -> &str {
        &self.receipt_json
    }
}

/// Build one self-hashed external comparison from exact sparse result and recovery bytes.
///
/// # Errors
///
/// Rejects all malformed contracts, identity/mapping/artifact mismatches, and receipt
/// canonicalization failures. Numerical divergence is a valid outcome.
pub fn execute_model_ir_linear_external_comparison(
    result_ir_bytes: &[u8],
    result_recovery_ir_bytes: &[u8],
    external_result_bytes: &[u8],
    source_artifact_bytes: &[u8],
    executable_artifact_bytes: Option<&[u8]>,
) -> Result<ModelIrLinearExternalComparisonOutcomeV1, ModelIrLinearComparisonProductError> {
    let result = parse_sparse_linear_result_ir_v1(result_ir_bytes)?;
    let recovery = parse_model_ir_linear_result_recovery_ir_v1(result_recovery_ir_bytes)?;
    let external = parse_model_ir_linear_external_result_v1(external_result_bytes)?;
    let comparison = build_model_ir_linear_external_comparison_ir_v1(
        &result,
        &recovery,
        &external,
        source_artifact_bytes,
        executable_artifact_bytes,
    )?;
    let comparison_ir_json = comparison.canonical_json().to_owned();
    let payload = comparison.comparison();
    let receipt_json = build_comparison_receipt(
        &comparison_ir_json,
        payload.status,
        &payload.comparison_id,
        &payload.source_result_hash,
        &payload.source_recovery_hash,
        &payload.external_result_hash,
        &payload.source.source_artifact_hash,
        payload.source.executable_hash.as_deref(),
        comparison.comparison_hash(),
    )?;
    Ok(ModelIrLinearExternalComparisonOutcomeV1 {
        status: payload.status,
        comparison_ir_json,
        receipt_json,
    })
}

/// Atomically publish a linear comparison artifact and its inventory receipt.
///
/// # Errors
///
/// Returns an I/O error if the destination exists or durable publication fails.
pub fn publish_model_ir_linear_external_comparison(
    output_directory: &Path,
    outcome: &ModelIrLinearExternalComparisonOutcomeV1,
) -> Result<(), ModelIrLinearComparisonProductError> {
    publish_artifact_directory(
        output_directory,
        &[
            (
                "external-comparison-ir.json",
                outcome.comparison_ir_json.as_bytes(),
            ),
            ("comparison-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn build_comparison_receipt(
    ir_json: &str,
    status: ExternalComparisonStatusV1,
    comparison_id: &str,
    source_result_hash: &str,
    source_recovery_hash: &str,
    external_result_hash: &str,
    source_artifact_hash: &str,
    executable_hash: Option<&str>,
    comparison_hash: &str,
) -> Result<String, ModelIrLinearComparisonProductError> {
    let status = match status {
        ExternalComparisonStatusV1::Passed => "passed",
        ExternalComparisonStatusV1::Diverged => "diverged",
    };
    let mut receipt = json!({
        "schema_version": "structural-native-model-ir-linear-comparison-receipt.v1",
        "comparison_id": comparison_id,
        "status": status,
        "source_result_hash": source_result_hash,
        "source_recovery_hash": source_recovery_hash,
        "external_result_hash": external_result_hash,
        "source_artifact_hash": source_artifact_hash,
        "executable_hash": executable_hash,
        "comparison_hash": comparison_hash,
        "artifacts": [artifact_entry(
            "external_comparison_ir",
            "external-comparison-ir.json",
            "application/json",
            ir_json.as_bytes(),
        )?],
        "claim_boundary": "inventory_for_one_bounded_model_ir_linear_global_dof_comparison_not_external_solver_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(receipt_error)?;
    let unsigned = canonicalize_value(
        &receipt,
        "model_ir_linear_comparison_receipt_canonicalization_failed",
    )?;
    receipt
        .as_object_mut()
        .expect("comparison receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(
        &receipt,
        "model_ir_linear_comparison_receipt_canonicalization_failed",
    )
    .map_err(Into::into)
}

fn receipt_error() -> ModelIrLinearComparisonProductError {
    ModelIrLinearComparisonProductError::Contract(ProductIrContractError {
        code: "model_ir_linear_comparison_receipt_invariant_failed".to_owned(),
        path: "/".to_owned(),
        detail: "comparison receipt is not an object".to_owned(),
    })
}
