use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::mgt_import::{import_mgt_v1, MgtImportDocumentV1, MgtImportError};
use structural_contracts::product_ir::sha256_identity;
use structural_runtime::{Runtime, RuntimeError};

use crate::product::{
    artifact_entry, canonicalize_value, publish_artifact_directory, NativeAnalysisProductError,
};

/// Product-layer failure for bounded native MGT import health.
#[derive(Debug)]
pub enum NativeMgtImportProductError {
    Contract(MgtImportError),
    Runtime(RuntimeError),
    Product(NativeAnalysisProductError),
    Invariant { code: &'static str, detail: String },
}

impl NativeMgtImportProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for NativeMgtImportProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Product(error) => write!(formatter, "{error}"),
            Self::Invariant { code, detail } => write!(formatter, "{code}: {detail}"),
        }
    }
}

impl std::error::Error for NativeMgtImportProductError {}

impl From<MgtImportError> for NativeMgtImportProductError {
    fn from(error: MgtImportError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for NativeMgtImportProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<NativeAnalysisProductError> for NativeMgtImportProductError {
    fn from(error: NativeAnalysisProductError) -> Self {
        Self::Product(error)
    }
}

/// Complete bounded MGT import-health artifact set.
#[derive(Clone, Debug)]
pub struct NativeMgtImportOutcomeV1 {
    source_bytes: Vec<u8>,
    health_json: String,
    model_ir_json: Option<String>,
    validation_json: Option<String>,
    snapshot_json: Option<String>,
    receipt_json: String,
    normalized: bool,
}

struct ValidatedModelArtifacts {
    model_ir: Option<String>,
    validation: Option<String>,
    snapshot: Option<String>,
}

impl NativeMgtImportOutcomeV1 {
    #[must_use]
    pub const fn is_normalized(&self) -> bool {
        self.normalized
    }

    #[must_use]
    pub fn receipt_json(&self) -> &str {
        &self.receipt_json
    }

    #[must_use]
    pub fn source_bytes(&self) -> &[u8] {
        &self.source_bytes
    }

    #[must_use]
    pub fn health_json(&self) -> &str {
        &self.health_json
    }

    #[must_use]
    pub fn model_ir_json(&self) -> Option<&str> {
        self.model_ir_json.as_deref()
    }

    #[must_use]
    pub fn validation_json(&self) -> Option<&str> {
        self.validation_json.as_deref()
    }

    #[must_use]
    pub fn snapshot_json(&self) -> Option<&str> {
        self.snapshot_json.as_deref()
    }
}

/// Import MGT bytes and validate any complete exact-profile `ModelIR` through the C++ owner.
///
/// A blocked import is a successful health outcome and retains the original source bytes. Only a
/// complete numeric frame/truss subset reaches the C ABI and C++ semantic validator.
///
/// # Errors
///
/// Returns a contract error for invalid caller parameters, a runtime error for native validation,
/// or an invariant error if the Rust and C++ identities diverge.
pub fn execute_native_mgt_import(
    source_bytes: &[u8],
    model_id: &str,
) -> Result<NativeMgtImportOutcomeV1, NativeMgtImportProductError> {
    let document = import_mgt_v1(source_bytes, model_id)?;
    let validated = validate_normalized_model(&document)?;
    let receipt_json = build_import_receipt(
        &document,
        validated.model_ir.as_deref(),
        validated.validation.as_deref(),
        validated.snapshot.as_deref(),
    )?;
    Ok(NativeMgtImportOutcomeV1 {
        source_bytes: document.source_bytes().to_vec(),
        health_json: document.health_json().to_owned(),
        model_ir_json: validated.model_ir,
        validation_json: validated.validation,
        snapshot_json: validated.snapshot,
        receipt_json,
        normalized: document.is_normalized(),
    })
}

/// Atomically publish a complete MGT import-health result into a new directory.
///
/// # Errors
///
/// Returns a stable product I/O error without overwriting an existing destination.
pub fn publish_native_mgt_import(
    output_directory: &Path,
    outcome: &NativeMgtImportOutcomeV1,
) -> Result<(), NativeMgtImportProductError> {
    let mut artifacts = vec![
        ("source.mgt", outcome.source_bytes.as_slice()),
        ("import-health.json", outcome.health_json.as_bytes()),
    ];
    if let (Some(model), Some(validation), Some(snapshot)) = (
        outcome.model_ir_json.as_ref(),
        outcome.validation_json.as_ref(),
        outcome.snapshot_json.as_ref(),
    ) {
        artifacts.push(("model-ir.json", model.as_bytes()));
        artifacts.push(("native-validation.json", validation.as_bytes()));
        artifacts.push(("native-snapshot.json", snapshot.as_bytes()));
    }
    artifacts.push(("import-receipt.json", outcome.receipt_json.as_bytes()));
    publish_artifact_directory(output_directory, &artifacts)?;
    Ok(())
}

fn validate_normalized_model(
    document: &MgtImportDocumentV1,
) -> Result<ValidatedModelArtifacts, NativeMgtImportProductError> {
    let Some(model) = document.model() else {
        return Ok(ValidatedModelArtifacts {
            model_ir: None,
            validation: None,
            snapshot: None,
        });
    };
    let validation = Runtime::new()?.validate_model_ir(model)?;
    if !validation.report.contract_valid || !validation.report.analysis_ready {
        return Err(NativeMgtImportProductError::Invariant {
            code: "mgt_cpp_normalized_model_rejected",
            detail: "exact-profile ModelIR was not contract-valid and analysis-ready in C++"
                .to_owned(),
        });
    }
    let identities_match = validation.snapshot.content_hash() == model.content_hash()
        && validation.snapshot.semantic_hash() == model.semantic_hash()
        && validation.snapshot.provenance_hash() == model.provenance_hash();
    if !identities_match {
        return Err(NativeMgtImportProductError::Invariant {
            code: "mgt_cpp_snapshot_identity_mismatch",
            detail: "C++ snapshot identities differ from the Rust-normalized ModelIR".to_owned(),
        });
    }
    Ok(ValidatedModelArtifacts {
        model_ir: Some(model.canonical_json().to_owned()),
        validation: Some(validation.report_json),
        snapshot: Some(validation.snapshot.canonical_json().to_owned()),
    })
}

fn build_import_receipt(
    document: &MgtImportDocumentV1,
    model_ir_json: Option<&str>,
    validation_json: Option<&str>,
    snapshot_json: Option<&str>,
) -> Result<String, NativeMgtImportProductError> {
    let source_media_type = if document.health().source.encoding.starts_with("utf-8") {
        "text/plain; charset=utf-8"
    } else {
        "application/octet-stream"
    };
    let mut artifacts = vec![
        artifact_entry(
            "original_mgt_source",
            "source.mgt",
            source_media_type,
            document.source_bytes(),
        )?,
        artifact_entry(
            "import_health",
            "import-health.json",
            "application/json",
            document.health_json().as_bytes(),
        )?,
    ];
    if let (Some(model), Some(validation), Some(snapshot)) =
        (model_ir_json, validation_json, snapshot_json)
    {
        artifacts.push(artifact_entry(
            "normalized_model_ir",
            "model-ir.json",
            "application/json",
            model.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "cpp_validation_report",
            "native-validation.json",
            "application/json",
            validation.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "cpp_canonical_snapshot",
            "native-snapshot.json",
            "application/json",
            snapshot.as_bytes(),
        )?);
    }
    let mut receipt = json!({
        "schema_version": "structural-native-mgt-import-receipt.v1",
        "status": if document.is_normalized() { "normalized" } else { "blocked" },
        "model_id": document.health().model_id,
        "source_hash": document.health().source.source_hash,
        "health_hash": document.health().health_hash,
        "normalized_model": document.health().normalized_model,
        "artifacts": artifacts,
        "claim_boundary": "bounded_mgt_import_health_and_cpp_modelir_validation_not_general_mgt_analysis_or_roundtrip_writeback",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| NativeMgtImportProductError::Invariant {
            code: "mgt_import_receipt_invariant_failed",
            detail: "MGT import receipt is not an object".to_owned(),
        })?;
    let unsigned = canonicalize_value(&receipt, "mgt_import_receipt_canonicalization_failed")?;
    receipt
        .as_object_mut()
        .expect("receipt object checked above")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&receipt, "mgt_import_receipt_canonicalization_failed").map_err(Into::into)
}
