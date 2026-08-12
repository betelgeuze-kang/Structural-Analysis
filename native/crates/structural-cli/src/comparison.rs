use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::external_comparison::{
    build_external_comparison_ir_v1, parse_external_result_v1, ExternalComparisonContractError,
    ExternalComparisonStatusV1,
};
use structural_contracts::product_ir::{
    parse_nonlinear_ndtha_result_ir_v1, sha256_identity, ProductIrContractError,
};

use crate::product::{
    artifact_entry, canonicalize_value, publish_artifact_directory, NativeAnalysisProductError,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NativeComparisonProductError {
    ExternalContract(ExternalComparisonContractError),
    ResultContract(ProductIrContractError),
    Product(NativeAnalysisProductError),
}

impl NativeComparisonProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::ExternalContract(_) | Self::ResultContract(_))
    }
}

impl fmt::Display for NativeComparisonProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ExternalContract(error) => write!(formatter, "{error}"),
            Self::ResultContract(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for NativeComparisonProductError {}

impl From<ExternalComparisonContractError> for NativeComparisonProductError {
    fn from(error: ExternalComparisonContractError) -> Self {
        Self::ExternalContract(error)
    }
}

impl From<ProductIrContractError> for NativeComparisonProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::ResultContract(error)
    }
}

impl From<NativeAnalysisProductError> for NativeComparisonProductError {
    fn from(error: NativeAnalysisProductError) -> Self {
        Self::Product(error)
    }
}

#[derive(Clone, Debug)]
pub struct NativeExternalComparisonOutcomeV1 {
    status: ExternalComparisonStatusV1,
    comparison_ir_json: String,
    receipt_json: String,
}

impl NativeExternalComparisonOutcomeV1 {
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

/// Build one strict, self-hashed comparison artifact from exact input bytes.
///
/// # Errors
///
/// Rejects either wire contract, all provenance/model/mapping mismatches, and receipt
/// canonicalization failures. Numerical divergence is a valid `diverged` outcome, not an error.
pub fn execute_external_comparison(
    result_ir_bytes: &[u8],
    external_result_bytes: &[u8],
    source_artifact_bytes: &[u8],
    executable_artifact_bytes: Option<&[u8]>,
) -> Result<NativeExternalComparisonOutcomeV1, NativeComparisonProductError> {
    let result = parse_nonlinear_ndtha_result_ir_v1(result_ir_bytes)?;
    let external = parse_external_result_v1(external_result_bytes)?;
    let comparison = build_external_comparison_ir_v1(
        &result,
        &external,
        source_artifact_bytes,
        executable_artifact_bytes,
    )?;
    let comparison_ir_json = comparison.canonical_json().to_owned();
    let receipt_json = build_comparison_receipt(
        &comparison_ir_json,
        comparison.comparison().status,
        comparison.comparison().comparison_id.as_str(),
        comparison.comparison().source_result_hash.as_str(),
        comparison.comparison().external_result_hash.as_str(),
        comparison.comparison().source.source_artifact_hash.as_str(),
        comparison.comparison().source.executable_hash.as_deref(),
        comparison.comparison_hash(),
    )?;
    Ok(NativeExternalComparisonOutcomeV1 {
        status: comparison.comparison().status,
        comparison_ir_json,
        receipt_json,
    })
}

/// Atomically publish a comparison artifact and its inventory into a new directory.
///
/// # Errors
///
/// Returns an I/O error if the destination exists or durable directory publication fails.
pub fn publish_external_comparison(
    output_directory: &Path,
    outcome: &NativeExternalComparisonOutcomeV1,
) -> Result<(), NativeComparisonProductError> {
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
    external_result_hash: &str,
    source_artifact_hash: &str,
    executable_hash: Option<&str>,
    comparison_hash: &str,
) -> Result<String, NativeComparisonProductError> {
    let status = match status {
        ExternalComparisonStatusV1::Passed => "passed",
        ExternalComparisonStatusV1::Diverged => "diverged",
    };
    let mut receipt = json!({
        "schema_version": "structural-native-external-comparison-receipt.v1",
        "comparison_id": comparison_id,
        "status": status,
        "source_result_hash": source_result_hash,
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
        "claim_boundary": "inventory_for_one_bounded_external_comparison_not_external_solver_or_engineering_acceptance",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| receipt_error("comparison receipt is not an object"))?;
    let unsigned = canonicalize_value(&receipt, "comparison_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("comparison receipt object was checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "comparison_receipt_canonicalization_failed").map_err(Into::into)
}

fn receipt_error(detail: &str) -> NativeComparisonProductError {
    NativeComparisonProductError::ResultContract(ProductIrContractError {
        code: "comparison_receipt_invariant_failed".to_owned(),
        path: "/".to_owned(),
        detail: detail.to_owned(),
    })
}
