//! Strict external-result ingestion and bounded `ResultIR` comparison contracts.

use std::collections::BTreeSet;
use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{sha256_identity, NonlinearNdthaResultIrDocumentV1};

pub const EXTERNAL_RESULT_V1: &str = "structural-native-external-result.v1";
pub const EXTERNAL_COMPARISON_IR_V1: &str = "structural-native-external-comparison-ir.v1";

const EXTERNAL_RESULT_SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/external_result_v1.schema.json"
));
const COMPARISON_CLAIM_BOUNDARY: &str = "bounded_numeric_comparison_of_explicit_global_ndtha_quantities_not_same_mesh_proof_engineering_acceptance_or_solver_certification";
const MAX_ARTIFACT_BYTES: usize = 64 * 1024 * 1024;
static EXTERNAL_RESULT_SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ExternalComparisonContractError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for ExternalComparisonContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for ExternalComparisonContractError {}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalSolverFamilyV1 {
    MidasGen,
    #[serde(rename = "opensees")]
    OpenSees,
    Calculix,
    ReferenceOracle,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalEvidenceKindV1 {
    LiveExternalExecution,
    LanguageNeutralGolden,
    Proxy,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalSourceV1 {
    pub solver_family: ExternalSolverFamilyV1,
    pub solver_version: String,
    pub run_id: String,
    pub evidence_kind: ExternalEvidenceKindV1,
    pub source_artifact_hash: String,
    pub executable_hash: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalResultBindingV1 {
    pub analysis_kind: String,
    pub case_id: String,
    pub model_hash: String,
    pub coordinate_frame: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalQuantityV1 {
    MaxDriftRatioPct,
    ResidualDriftRatioPct,
    ResidualTopDisplacementM,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ComparisonToleranceV1 {
    pub absolute: f64,
    pub relative: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalObservationV1 {
    pub observation_id: String,
    pub quantity: ExternalQuantityV1,
    pub external_location_id: String,
    pub native_location_id: String,
    pub native_result_path: String,
    pub unit: String,
    pub value: f64,
    pub tolerance: ComparisonToleranceV1,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalResultV1 {
    pub schema_version: String,
    pub comparison_id: String,
    pub source: ExternalSourceV1,
    pub binding: ExternalResultBindingV1,
    pub observations: Vec<ExternalObservationV1>,
}

#[derive(Clone, Debug)]
pub struct ExternalResultDocumentV1 {
    external_result: ExternalResultV1,
    canonical_json: String,
    external_result_hash: String,
}

impl ExternalResultDocumentV1 {
    #[must_use]
    pub const fn external_result(&self) -> &ExternalResultV1 {
        &self.external_result
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn canonical_bytes(&self) -> &[u8] {
        self.canonical_json.as_bytes()
    }

    #[must_use]
    pub fn external_result_hash(&self) -> &str {
        &self.external_result_hash
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalComparisonAuthorityV1 {
    BoundedCandidate,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalComparisonStatusV1 {
    Passed,
    Diverged,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalComparisonRowV1 {
    pub observation_id: String,
    pub quantity: ExternalQuantityV1,
    pub external_location_id: String,
    pub native_location_id: String,
    pub native_result_path: String,
    pub unit: String,
    pub native_value: f64,
    pub external_value: f64,
    pub absolute_error: f64,
    pub relative_error: Option<f64>,
    pub tolerance: ComparisonToleranceV1,
    pub within_tolerance: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExternalComparisonIrV1 {
    pub schema_version: String,
    pub comparison_id: String,
    pub authority: ExternalComparisonAuthorityV1,
    pub status: ExternalComparisonStatusV1,
    pub source: ExternalSourceV1,
    pub binding: ExternalResultBindingV1,
    pub source_result_hash: String,
    pub external_result_hash: String,
    pub rows: Vec<ExternalComparisonRowV1>,
    pub claim_boundary: String,
    pub comparison_hash: String,
}

#[derive(Clone, Debug)]
pub struct ExternalComparisonIrDocumentV1 {
    comparison: ExternalComparisonIrV1,
    canonical_json: String,
}

impl ExternalComparisonIrDocumentV1 {
    #[must_use]
    pub const fn comparison(&self) -> &ExternalComparisonIrV1 {
        &self.comparison
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn canonical_bytes(&self) -> &[u8] {
        self.canonical_json.as_bytes()
    }

    #[must_use]
    pub fn comparison_hash(&self) -> &str {
        &self.comparison.comparison_hash
    }
}

/// Strictly decode and canonicalize one external-result input.
///
/// # Errors
///
/// Rejects invalid UTF-8/JSON, duplicate or unknown fields, unsupported mappings, inconsistent
/// evidence authority, malformed hashes and ambiguous duplicate quantities.
pub fn parse_external_result_v1(
    bytes: &[u8],
) -> Result<ExternalResultDocumentV1, ExternalComparisonContractError> {
    let value = strict_value(bytes, "external_result")?;
    validate_external_result_schema(&value)?;
    let external_result: ExternalResultV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            contract_error(
                "external_result_decode_failed",
                "/",
                "external result fields do not satisfy the typed v1 contract",
            )
        })?;
    validate_external_result(&external_result)?;
    let canonical_json = canonicalize(&value, "external_result_canonicalization_failed")?;
    let external_result_hash = sha256_identity(canonical_json.as_bytes());
    Ok(ExternalResultDocumentV1 {
        external_result,
        canonical_json,
        external_result_hash,
    })
}

/// Compare one strict external result against one exact bounded `ResultIR`.
///
/// `source_artifact` is always verified. A declared executable hash is also verified against
/// `executable_artifact`; live evidence cannot be built without those executable bytes.
///
/// # Errors
///
/// Rejects artifact/hash mismatch, model/case/frame mismatch, missing executable evidence or
/// non-finite comparison arithmetic.
pub fn build_external_comparison_ir_v1(
    result: &NonlinearNdthaResultIrDocumentV1,
    external: &ExternalResultDocumentV1,
    source_artifact: &[u8],
    executable_artifact: Option<&[u8]>,
) -> Result<ExternalComparisonIrDocumentV1, ExternalComparisonContractError> {
    validate_artifact_size(source_artifact, "/source/source_artifact_hash")?;
    let input = external.external_result();
    if sha256_identity(source_artifact) != input.source.source_artifact_hash {
        return Err(contract_error(
            "external_source_artifact_hash_mismatch",
            "/source/source_artifact_hash",
            "external source artifact bytes do not match the declared SHA-256",
        ));
    }
    verify_executable_artifact(&input.source, executable_artifact)?;

    let native = result.result();
    if input.binding.analysis_kind != native.analysis_kind {
        return Err(binding_error(
            "external_analysis_kind_mismatch",
            "/binding/analysis_kind",
        ));
    }
    if input.binding.case_id != native.case_id {
        return Err(binding_error(
            "external_case_id_mismatch",
            "/binding/case_id",
        ));
    }
    if input.binding.model_hash != native.identity.model_hash {
        return Err(binding_error(
            "external_model_hash_mismatch",
            "/binding/model_hash",
        ));
    }
    if input.binding.coordinate_frame != native.units.coordinate_frame {
        return Err(binding_error(
            "external_coordinate_frame_mismatch",
            "/binding/coordinate_frame",
        ));
    }

    let mut rows = Vec::with_capacity(input.observations.len());
    for observation in &input.observations {
        let native_value = native_value(result, observation.quantity);
        let absolute_error = (native_value - observation.value).abs();
        if !absolute_error.is_finite() {
            return Err(contract_error(
                "external_comparison_numeric_overflow",
                "/observations",
                "comparison arithmetic exceeded finite FP64 range",
            ));
        }
        let relative_error = relative_error(absolute_error, observation.value);
        let within_tolerance =
            passes_tolerance(absolute_error, relative_error, &observation.tolerance);
        rows.push(ExternalComparisonRowV1 {
            observation_id: observation.observation_id.clone(),
            quantity: observation.quantity,
            external_location_id: observation.external_location_id.clone(),
            native_location_id: observation.native_location_id.clone(),
            native_result_path: observation.native_result_path.clone(),
            unit: observation.unit.clone(),
            native_value,
            external_value: observation.value,
            absolute_error,
            relative_error,
            tolerance: observation.tolerance.clone(),
            within_tolerance,
        });
    }
    let status = if rows.iter().all(|row| row.within_tolerance) {
        ExternalComparisonStatusV1::Passed
    } else {
        ExternalComparisonStatusV1::Diverged
    };
    let mut comparison = ExternalComparisonIrV1 {
        schema_version: EXTERNAL_COMPARISON_IR_V1.to_owned(),
        comparison_id: input.comparison_id.clone(),
        authority: ExternalComparisonAuthorityV1::BoundedCandidate,
        status,
        source: input.source.clone(),
        binding: input.binding.clone(),
        source_result_hash: native.result_hash.clone(),
        external_result_hash: external.external_result_hash.clone(),
        rows,
        claim_boundary: COMPARISON_CLAIM_BOUNDARY.to_owned(),
        comparison_hash: String::new(),
    };
    validate_comparison(&comparison)?;
    comparison.comparison_hash = hash_without_field(
        &comparison,
        "comparison_hash",
        "external_comparison_hash_failed",
    )?;
    let canonical_json =
        canonical_struct(&comparison, "external_comparison_canonicalization_failed")?;
    Ok(ExternalComparisonIrDocumentV1 {
        comparison,
        canonical_json,
    })
}

/// Strictly decode a comparison artifact and verify all derived rows and its self-hash.
///
/// # Errors
///
/// Rejects malformed wire data, invalid derived arithmetic/status or a self-hash mismatch.
pub fn parse_external_comparison_ir_v1(
    bytes: &[u8],
) -> Result<ExternalComparisonIrDocumentV1, ExternalComparisonContractError> {
    let value = strict_value(bytes, "external_comparison")?;
    let comparison: ExternalComparisonIrV1 = serde_json::from_value(value).map_err(|_| {
        contract_error(
            "external_comparison_decode_failed",
            "/",
            "external comparison fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_comparison(&comparison)?;
    let expected = hash_without_field(
        &comparison,
        "comparison_hash",
        "external_comparison_hash_failed",
    )?;
    if comparison.comparison_hash != expected {
        return Err(contract_error(
            "external_comparison_hash_mismatch",
            "/comparison_hash",
            "external comparison self-hash does not match its canonical payload",
        ));
    }
    let canonical_json =
        canonical_struct(&comparison, "external_comparison_canonicalization_failed")?;
    Ok(ExternalComparisonIrDocumentV1 {
        comparison,
        canonical_json,
    })
}

fn validate_external_result_schema(value: &Value) -> Result<(), ExternalComparisonContractError> {
    let compiled = EXTERNAL_RESULT_SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(EXTERNAL_RESULT_SCHEMA_TEXT)
            .map_err(|error| format!("schema JSON invalid: {error}"))?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|error| format!("schema compile failed: {error}"))
    });
    let validator = compiled.as_ref().map_err(|_| {
        contract_error(
            "external_result_schema_contract_invalid",
            "/",
            "embedded external result schema could not be compiled",
        )
    })?;
    let mut paths = validator
        .validate(value)
        .err()
        .into_iter()
        .flatten()
        .map(|error| {
            let path = error.instance_path.to_string();
            if path.is_empty() {
                "/".to_owned()
            } else {
                path
            }
        })
        .collect::<Vec<_>>();
    paths.sort();
    if let Some(path) = paths.first() {
        return Err(contract_error(
            "external_result_schema_invalid",
            path,
            "external result does not satisfy the v1 schema",
        ));
    }
    Ok(())
}

fn validate_external_result(
    external: &ExternalResultV1,
) -> Result<(), ExternalComparisonContractError> {
    if external.schema_version != EXTERNAL_RESULT_V1 {
        return Err(contract_error(
            "external_result_contract_identity_invalid",
            "/schema_version",
            "external result schema identity is invalid",
        ));
    }
    validate_source(&external.source)?;
    validate_hash(&external.binding.model_hash, "/binding/model_hash")?;
    let mut observation_ids = BTreeSet::new();
    let mut quantities = BTreeSet::new();
    for (index, observation) in external.observations.iter().enumerate() {
        if !observation_ids.insert(&observation.observation_id) {
            return Err(contract_error(
                "external_observation_id_duplicate",
                &format!("/observations/{index}/observation_id"),
                "external observation ids must be unique",
            ));
        }
        if !quantities.insert(observation.quantity) {
            return Err(contract_error(
                "external_quantity_duplicate",
                &format!("/observations/{index}/quantity"),
                "the bounded global profile accepts one observation per quantity",
            ));
        }
        validate_observation(observation, index)?;
    }
    Ok(())
}

fn validate_source(source: &ExternalSourceV1) -> Result<(), ExternalComparisonContractError> {
    validate_hash(&source.source_artifact_hash, "/source/source_artifact_hash")?;
    if let Some(hash) = source.executable_hash.as_deref() {
        validate_hash(hash, "/source/executable_hash")?;
    }
    if source.solver_version.chars().any(char::is_control) {
        return Err(contract_error(
            "external_solver_version_invalid",
            "/source/solver_version",
            "solver version cannot contain control characters",
        ));
    }
    let source_valid = match source.evidence_kind {
        ExternalEvidenceKindV1::LiveExternalExecution => {
            source.solver_family != ExternalSolverFamilyV1::ReferenceOracle
                && source.executable_hash.is_some()
        }
        ExternalEvidenceKindV1::LanguageNeutralGolden => {
            source.solver_family == ExternalSolverFamilyV1::ReferenceOracle
                && source.executable_hash.is_none()
        }
        ExternalEvidenceKindV1::Proxy => {
            source.solver_family != ExternalSolverFamilyV1::ReferenceOracle
        }
    };
    if !source_valid {
        return Err(contract_error(
            "external_evidence_authority_invalid",
            "/source/evidence_kind",
            "solver family, evidence kind and executable hash are inconsistent",
        ));
    }
    Ok(())
}

fn validate_observation(
    observation: &ExternalObservationV1,
    index: usize,
) -> Result<(), ExternalComparisonContractError> {
    let (location, path, unit) = quantity_contract(observation.quantity);
    let base = format!("/observations/{index}");
    if observation.native_location_id != location {
        return Err(contract_error(
            "external_native_location_mismatch",
            &format!("{base}/native_location_id"),
            "native location does not match the selected bounded quantity",
        ));
    }
    if observation.native_result_path != path {
        return Err(contract_error(
            "external_native_result_path_mismatch",
            &format!("{base}/native_result_path"),
            "native ResultIR path does not match the selected bounded quantity",
        ));
    }
    if observation.unit != unit {
        return Err(contract_error(
            "external_quantity_unit_mismatch",
            &format!("{base}/unit"),
            "external unit does not match the selected bounded quantity",
        ));
    }
    for (name, value) in [
        ("value", observation.value),
        ("tolerance/absolute", observation.tolerance.absolute),
        ("tolerance/relative", observation.tolerance.relative),
    ] {
        if !value.is_finite() {
            return Err(contract_error(
                "external_observation_non_finite",
                &format!("{base}/{name}"),
                "external observation values and tolerances must be finite",
            ));
        }
    }
    if observation.tolerance.absolute < 0.0 || observation.tolerance.relative < 0.0 {
        return Err(contract_error(
            "external_tolerance_negative",
            &format!("{base}/tolerance"),
            "external comparison tolerances cannot be negative",
        ));
    }
    Ok(())
}

fn validate_comparison(
    comparison: &ExternalComparisonIrV1,
) -> Result<(), ExternalComparisonContractError> {
    if comparison.schema_version != EXTERNAL_COMPARISON_IR_V1
        || comparison.authority != ExternalComparisonAuthorityV1::BoundedCandidate
        || comparison.claim_boundary != COMPARISON_CLAIM_BOUNDARY
    {
        return Err(contract_error(
            "external_comparison_contract_identity_invalid",
            "/",
            "external comparison identity or authority boundary is invalid",
        ));
    }
    validate_source(&comparison.source)?;
    validate_hash(&comparison.binding.model_hash, "/binding/model_hash")?;
    validate_hash(&comparison.source_result_hash, "/source_result_hash")?;
    validate_hash(&comparison.external_result_hash, "/external_result_hash")?;
    if !comparison.comparison_hash.is_empty() {
        validate_hash(&comparison.comparison_hash, "/comparison_hash")?;
    }
    if comparison.rows.is_empty() || comparison.rows.len() > 64 {
        return Err(contract_error(
            "external_comparison_row_count_invalid",
            "/rows",
            "external comparison must contain between one and 64 rows",
        ));
    }
    let mut ids = BTreeSet::new();
    let mut quantities = BTreeSet::new();
    for (index, row) in comparison.rows.iter().enumerate() {
        if !ids.insert(&row.observation_id) || !quantities.insert(row.quantity) {
            return Err(contract_error(
                "external_comparison_row_duplicate",
                &format!("/rows/{index}"),
                "comparison row ids and bounded quantities must be unique",
            ));
        }
        let observation = ExternalObservationV1 {
            observation_id: row.observation_id.clone(),
            quantity: row.quantity,
            external_location_id: row.external_location_id.clone(),
            native_location_id: row.native_location_id.clone(),
            native_result_path: row.native_result_path.clone(),
            unit: row.unit.clone(),
            value: row.external_value,
            tolerance: row.tolerance.clone(),
        };
        validate_observation(&observation, index)?;
        if !row.native_value.is_finite()
            || !row.absolute_error.is_finite()
            || row.relative_error.is_some_and(|value| !value.is_finite())
        {
            return Err(contract_error(
                "external_comparison_row_non_finite",
                &format!("/rows/{index}"),
                "comparison row contains a non-finite derived value",
            ));
        }
        let expected_absolute = (row.native_value - row.external_value).abs();
        let expected_relative = relative_error(expected_absolute, row.external_value);
        let expected_pass = passes_tolerance(expected_absolute, expected_relative, &row.tolerance);
        if row.absolute_error.to_bits() != expected_absolute.to_bits()
            || !optional_bits_equal(row.relative_error, expected_relative)
            || row.within_tolerance != expected_pass
        {
            return Err(contract_error(
                "external_comparison_row_derivation_invalid",
                &format!("/rows/{index}"),
                "comparison row arithmetic does not match its source values and tolerances",
            ));
        }
    }
    let expected_status = if comparison.rows.iter().all(|row| row.within_tolerance) {
        ExternalComparisonStatusV1::Passed
    } else {
        ExternalComparisonStatusV1::Diverged
    };
    if comparison.status != expected_status {
        return Err(contract_error(
            "external_comparison_status_invalid",
            "/status",
            "comparison status does not match the aggregate row status",
        ));
    }
    Ok(())
}

fn quantity_contract(quantity: ExternalQuantityV1) -> (&'static str, &'static str, &'static str) {
    match quantity {
        ExternalQuantityV1::MaxDriftRatioPct => (
            "global_response_envelope",
            "/summary/max_drift_ratio_pct",
            "percent",
        ),
        ExternalQuantityV1::ResidualDriftRatioPct => (
            "terminal_global_response",
            "/summary/residual_drift_ratio_pct",
            "percent",
        ),
        ExternalQuantityV1::ResidualTopDisplacementM => (
            "terminal_global_response",
            "/summary/residual_top_displacement_m",
            "m",
        ),
    }
}

fn native_value(result: &NonlinearNdthaResultIrDocumentV1, quantity: ExternalQuantityV1) -> f64 {
    let summary = &result.result().summary;
    match quantity {
        ExternalQuantityV1::MaxDriftRatioPct => summary.max_drift_ratio_pct,
        ExternalQuantityV1::ResidualDriftRatioPct => summary.residual_drift_ratio_pct,
        ExternalQuantityV1::ResidualTopDisplacementM => summary.residual_top_displacement_m,
    }
}

fn relative_error(absolute_error: f64, external_value: f64) -> Option<f64> {
    if external_value.to_bits() == 0.0_f64.to_bits()
        || external_value.to_bits() == (-0.0_f64).to_bits()
    {
        if absolute_error.to_bits() == 0.0_f64.to_bits() {
            Some(0.0)
        } else {
            None
        }
    } else {
        Some(absolute_error / external_value.abs())
    }
}

fn passes_tolerance(
    absolute_error: f64,
    relative_error: Option<f64>,
    tolerance: &ComparisonToleranceV1,
) -> bool {
    absolute_error <= tolerance.absolute
        || relative_error.is_some_and(|error| error <= tolerance.relative)
}

fn optional_bits_equal(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => left.to_bits() == right.to_bits(),
        (None, None) => true,
        (Some(_), None) | (None, Some(_)) => false,
    }
}

fn verify_executable_artifact(
    source: &ExternalSourceV1,
    executable_artifact: Option<&[u8]>,
) -> Result<(), ExternalComparisonContractError> {
    match (source.executable_hash.as_deref(), executable_artifact) {
        (Some(expected), Some(bytes)) => {
            validate_artifact_size(bytes, "/source/executable_hash")?;
            if sha256_identity(bytes) != expected {
                return Err(contract_error(
                    "external_executable_hash_mismatch",
                    "/source/executable_hash",
                    "external executable bytes do not match the declared SHA-256",
                ));
            }
        }
        (Some(_), None) => {
            return Err(contract_error(
                "external_executable_artifact_missing",
                "/source/executable_hash",
                "declared external executable hash requires exact executable artifact bytes",
            ));
        }
        (None, Some(_)) => {
            return Err(contract_error(
                "external_executable_hash_missing",
                "/source/executable_hash",
                "external executable bytes were supplied without a declared hash",
            ));
        }
        (None, None) => {}
    }
    Ok(())
}

fn validate_artifact_size(bytes: &[u8], path: &str) -> Result<(), ExternalComparisonContractError> {
    if bytes.is_empty() || bytes.len() > MAX_ARTIFACT_BYTES {
        return Err(contract_error(
            "external_artifact_size_invalid",
            path,
            "external artifacts must contain between one byte and 64 MiB",
        ));
    }
    Ok(())
}

fn validate_hash(value: &str, path: &str) -> Result<(), ExternalComparisonContractError> {
    if value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(contract_error(
            "external_hash_invalid",
            path,
            "identity must be lowercase sha256:<64 hex>",
        ))
    }
}

fn strict_value(bytes: &[u8], family: &str) -> Result<Value, ExternalComparisonContractError> {
    decode_json_strict(bytes).map_err(|error| ExternalComparisonContractError {
        code: error.code.replacen("model_ir", family, 1),
        path: error.path,
        detail: error.detail.replace("ModelIR", family),
    })
}

fn canonicalize(value: &Value, code: &str) -> Result<String, ExternalComparisonContractError> {
    canonicalize_model_ir_v2(value).map_err(|_| {
        contract_error(
            code,
            "/",
            "value could not be represented by the canonical JSON contract",
        )
    })
}

fn canonical_struct<T: Serialize>(
    value: &T,
    code: &str,
) -> Result<String, ExternalComparisonContractError> {
    let value = serde_json::to_value(value)
        .map_err(|_| contract_error(code, "/", "typed value could not be represented as JSON"))?;
    canonicalize(&value, code)
}

fn hash_without_field<T: Serialize>(
    value: &T,
    field: &str,
    code: &str,
) -> Result<String, ExternalComparisonContractError> {
    let mut value = serde_json::to_value(value)
        .map_err(|_| contract_error(code, "/", "typed value could not be represented as JSON"))?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| contract_error(code, "/", "self-hash field is missing"))?;
    let canonical = canonicalize(&value, code)?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn binding_error(code: &str, path: &str) -> ExternalComparisonContractError {
    contract_error(
        code,
        path,
        "external result binding does not match the supplied native ResultIR",
    )
}

fn contract_error(code: &str, path: &str, detail: &str) -> ExternalComparisonContractError {
    ExternalComparisonContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::{relative_error, ComparisonToleranceV1};

    #[test]
    fn zero_reference_relative_error_has_no_infinite_wire_value() {
        assert_eq!(relative_error(0.0, 0.0), Some(0.0));
        assert_eq!(relative_error(1.0, 0.0), None);
    }

    #[test]
    fn tolerance_is_absolute_or_relative() {
        let tolerance = ComparisonToleranceV1 {
            absolute: 0.1,
            relative: 0.01,
        };
        assert!(super::passes_tolerance(0.05, Some(0.5), &tolerance));
        assert!(super::passes_tolerance(0.5, Some(0.005), &tolerance));
        assert!(!super::passes_tolerance(0.5, None, &tolerance));
    }
}
