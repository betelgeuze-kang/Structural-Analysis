//! Strict external-result comparison for recovered `ModelIR` linear-static global DOFs.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::external_comparison::{
    ComparisonToleranceV1, ExternalComparisonAuthorityV1, ExternalComparisonStatusV1,
    ExternalEvidenceKindV1, ExternalSolverFamilyV1, ExternalSourceV1,
};
use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::model_linear_recovery::{
    verify_model_ir_linear_result_recovery_v1, ModelIrLinearResultRecoveryDocumentV1,
};
use crate::product_ir::{sha256_identity, ModelIrIdentityV1, ProductIrContractError};
use crate::sparse_product::SparseLinearResultIrDocumentV1;

pub const MODEL_IR_LINEAR_EXTERNAL_RESULT_V1: &str =
    "structural-model-ir-linear-external-result.v1";
pub const MODEL_IR_LINEAR_EXTERNAL_COMPARISON_IR_V1: &str =
    "structural-model-ir-linear-external-comparison-ir.v1";
pub const MODEL_IR_LINEAR_MAXIMUM_EXTERNAL_RESULT_BYTES: usize = 4 * 1024 * 1024;

const ANALYSIS_KIND: &str = "model_ir_linear_static";
const COORDINATE_FRAME: &str = "model_global";
const MAXIMUM_OBSERVATIONS: usize = 256;
const MAXIMUM_ARTIFACT_BYTES: usize = 64 * 1024 * 1024;
const COMPARISON_CLAIM_BOUNDARY: &str = "bounded_numeric_comparison_of_explicit_recovered_model_ir_global_dofs_not_same_mesh_proof_engineering_acceptance_or_solver_certification";

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub enum ModelIrLinearDofV1 {
    #[serde(rename = "UX")]
    Ux,
    #[serde(rename = "UY")]
    Uy,
    #[serde(rename = "UZ")]
    Uz,
    #[serde(rename = "RX")]
    Rx,
    #[serde(rename = "RY")]
    Ry,
    #[serde(rename = "RZ")]
    Rz,
}

impl ModelIrLinearDofV1 {
    const fn ordinal(self) -> u32 {
        match self {
            Self::Ux => 0,
            Self::Uy => 1,
            Self::Uz => 2,
            Self::Rx => 3,
            Self::Ry => 4,
            Self::Rz => 5,
        }
    }

    const fn unit(self) -> &'static str {
        match self {
            Self::Ux | Self::Uy | Self::Uz => "m",
            Self::Rx | Self::Ry | Self::Rz => "rad",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearExternalBindingV1 {
    pub analysis_kind: String,
    pub case_id: String,
    pub model_identity: ModelIrIdentityV1,
    pub analysis_request_hash: String,
    pub load_pattern_id: String,
    pub coordinate_frame: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearExternalObservationV1 {
    pub observation_id: String,
    pub external_location_id: String,
    pub global_dof_index: u32,
    pub dof: ModelIrLinearDofV1,
    pub native_result_path: String,
    pub unit: String,
    pub value: f64,
    pub tolerance: ComparisonToleranceV1,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearExternalResultV1 {
    pub schema_version: String,
    pub comparison_id: String,
    pub source: ExternalSourceV1,
    pub binding: ModelIrLinearExternalBindingV1,
    pub observations: Vec<ModelIrLinearExternalObservationV1>,
}

#[derive(Clone, Debug)]
pub struct ModelIrLinearExternalResultDocumentV1 {
    external_result: ModelIrLinearExternalResultV1,
    canonical_json: String,
    external_result_hash: String,
}

impl ModelIrLinearExternalResultDocumentV1 {
    #[must_use]
    pub const fn external_result(&self) -> &ModelIrLinearExternalResultV1 {
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

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearExternalComparisonRowV1 {
    pub observation_id: String,
    pub external_location_id: String,
    pub global_dof_index: u32,
    pub dof: ModelIrLinearDofV1,
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
pub struct ModelIrLinearExternalComparisonIrV1 {
    pub schema_version: String,
    pub comparison_id: String,
    pub authority: ExternalComparisonAuthorityV1,
    pub status: ExternalComparisonStatusV1,
    pub source: ExternalSourceV1,
    pub binding: ModelIrLinearExternalBindingV1,
    pub source_result_hash: String,
    pub source_recovery_hash: String,
    pub external_result_hash: String,
    pub rows: Vec<ModelIrLinearExternalComparisonRowV1>,
    pub claim_boundary: String,
    pub comparison_hash: String,
}

#[derive(Clone, Debug)]
pub struct ModelIrLinearExternalComparisonDocumentV1 {
    comparison: ModelIrLinearExternalComparisonIrV1,
    canonical_json: String,
}

impl ModelIrLinearExternalComparisonDocumentV1 {
    #[must_use]
    pub const fn comparison(&self) -> &ModelIrLinearExternalComparisonIrV1 {
        &self.comparison
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn comparison_hash(&self) -> &str {
        &self.comparison.comparison_hash
    }
}

/// Parse and canonicalize one bounded external linear-static result.
///
/// # Errors
///
/// Rejects invalid UTF-8/JSON, duplicate or unknown fields, invalid provenance, malformed
/// bindings, ambiguous DOF observations, or non-finite numeric data.
pub fn parse_model_ir_linear_external_result_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearExternalResultDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_MAXIMUM_EXTERNAL_RESULT_BYTES {
        return Err(error(
            "model_ir_linear_external_result_size_invalid",
            "/",
            "external result bytes are outside the bounded comparison domain",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_external_result_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let external_result: ModelIrLinearExternalResultV1 = serde_json::from_value(value.clone())
        .map_err(|_| {
            error(
                "model_ir_linear_external_result_decode_failed",
                "/",
                "external result has unknown, missing, or mistyped fields",
            )
        })?;
    validate_external_result(&external_result)?;
    let canonical_json = canonicalize(&value, "external result")?;
    let external_result_hash = sha256_identity(canonical_json.as_bytes());
    Ok(ModelIrLinearExternalResultDocumentV1 {
        external_result,
        canonical_json,
        external_result_hash,
    })
}

/// Compare explicit external global-DOF observations against one exact recovered result.
///
/// # Errors
///
/// Rejects artifact/hash, result/recovery, model/request/case/load-pattern, mapping, and finite
/// arithmetic mismatches. Numerical divergence is represented by a valid `diverged` artifact.
pub fn build_model_ir_linear_external_comparison_ir_v1(
    result: &SparseLinearResultIrDocumentV1,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
    external: &ModelIrLinearExternalResultDocumentV1,
    source_artifact: &[u8],
    executable_artifact: Option<&[u8]>,
) -> Result<ModelIrLinearExternalComparisonDocumentV1, ProductIrContractError> {
    verify_artifacts(
        &external.external_result.source,
        source_artifact,
        executable_artifact,
    )?;
    verify_bindings(result, recovery, external)?;

    let input = &external.external_result;
    let recovered = recovery.recovery();
    let mut rows = Vec::with_capacity(input.observations.len());
    for observation in &input.observations {
        let index = usize::try_from(observation.global_dof_index).map_err(|_| {
            error(
                "model_ir_linear_external_dof_index_invalid",
                "/observations/global_dof_index",
                "global DOF index does not fit the bounded host representation",
            )
        })?;
        let native_value = recovered
            .global_displacement
            .get(index)
            .copied()
            .ok_or_else(|| {
                error(
                    "model_ir_linear_external_dof_index_invalid",
                    "/observations/global_dof_index",
                    "global DOF observation is outside the recovered displacement vector",
                )
            })?;
        let absolute_error = (native_value - observation.value).abs();
        if !absolute_error.is_finite() {
            return Err(error(
                "model_ir_linear_external_comparison_numeric_overflow",
                "/observations",
                "comparison arithmetic exceeded finite FP64 range",
            ));
        }
        let relative_error = relative_error(absolute_error, observation.value);
        let within_tolerance =
            passes_tolerance(absolute_error, relative_error, &observation.tolerance);
        rows.push(ModelIrLinearExternalComparisonRowV1 {
            observation_id: observation.observation_id.clone(),
            external_location_id: observation.external_location_id.clone(),
            global_dof_index: observation.global_dof_index,
            dof: observation.dof,
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
    let mut comparison = ModelIrLinearExternalComparisonIrV1 {
        schema_version: MODEL_IR_LINEAR_EXTERNAL_COMPARISON_IR_V1.to_owned(),
        comparison_id: input.comparison_id.clone(),
        authority: ExternalComparisonAuthorityV1::BoundedCandidate,
        status,
        source: input.source.clone(),
        binding: input.binding.clone(),
        source_result_hash: result.result_hash().to_owned(),
        source_recovery_hash: recovery.recovery_hash().to_owned(),
        external_result_hash: external.external_result_hash.clone(),
        rows,
        claim_boundary: COMPARISON_CLAIM_BOUNDARY.to_owned(),
        comparison_hash: String::new(),
    };
    validate_comparison(&comparison)?;
    comparison.comparison_hash = hash_struct_without_field(&comparison, "comparison_hash")?;
    let canonical_json = canonical_struct(&comparison, "comparison")?;
    Ok(ModelIrLinearExternalComparisonDocumentV1 {
        comparison,
        canonical_json,
    })
}

/// Parse, validate, and self-hash-check one linear external comparison artifact.
///
/// # Errors
///
/// Rejects malformed fields, invalid mappings/arithmetic/status, or a self-hash mismatch.
pub fn parse_model_ir_linear_external_comparison_ir_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearExternalComparisonDocumentV1, ProductIrContractError> {
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_external_comparison_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let comparison: ModelIrLinearExternalComparisonIrV1 =
        serde_json::from_value(value).map_err(|_| {
            error(
                "model_ir_linear_external_comparison_decode_failed",
                "/",
                "comparison has unknown, missing, or mistyped fields",
            )
        })?;
    validate_comparison(&comparison)?;
    let expected = hash_struct_without_field(&comparison, "comparison_hash")?;
    if comparison.comparison_hash != expected {
        return Err(error(
            "model_ir_linear_external_comparison_hash_mismatch",
            "/comparison_hash",
            "comparison self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&comparison, "comparison")?;
    Ok(ModelIrLinearExternalComparisonDocumentV1 {
        comparison,
        canonical_json,
    })
}

fn verify_bindings(
    result: &SparseLinearResultIrDocumentV1,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
    external: &ModelIrLinearExternalResultDocumentV1,
) -> Result<(), ProductIrContractError> {
    verify_model_ir_linear_result_recovery_v1(result, recovery)?;
    let native = recovery.recovery();
    let binding = &external.external_result.binding;
    if native.source_result_hash != result.result_hash() {
        return Err(binding_error(
            "model_ir_linear_recovery_result_hash_mismatch",
            "/source_result_hash",
        ));
    }
    if binding.case_id != result.result().case_id || binding.case_id != native.case_id {
        return Err(binding_error(
            "model_ir_linear_external_case_id_mismatch",
            "/binding/case_id",
        ));
    }
    if binding.model_identity != native.model_identity {
        return Err(binding_error(
            "model_ir_linear_external_model_identity_mismatch",
            "/binding/model_identity",
        ));
    }
    if binding.analysis_request_hash != native.analysis_request_hash {
        return Err(binding_error(
            "model_ir_linear_external_request_hash_mismatch",
            "/binding/analysis_request_hash",
        ));
    }
    if binding.load_pattern_id != native.load_pattern_id {
        return Err(binding_error(
            "model_ir_linear_external_load_pattern_mismatch",
            "/binding/load_pattern_id",
        ));
    }
    Ok(())
}

fn validate_external_result(
    external: &ModelIrLinearExternalResultV1,
) -> Result<(), ProductIrContractError> {
    if external.schema_version != MODEL_IR_LINEAR_EXTERNAL_RESULT_V1 {
        return Err(error(
            "model_ir_linear_external_result_identity_invalid",
            "/schema_version",
            "external result schema identity is unsupported",
        ));
    }
    validate_id(&external.comparison_id, "/comparison_id")?;
    validate_source(&external.source)?;
    validate_binding(&external.binding)?;
    if external.observations.is_empty() || external.observations.len() > MAXIMUM_OBSERVATIONS {
        return Err(error(
            "model_ir_linear_external_observation_count_invalid",
            "/observations",
            "external comparison requires between one and 256 observations",
        ));
    }
    let mut ids = BTreeSet::new();
    let mut dofs = BTreeSet::new();
    for (index, observation) in external.observations.iter().enumerate() {
        if !ids.insert(&observation.observation_id) {
            return Err(error(
                "model_ir_linear_external_observation_id_duplicate",
                &format!("/observations/{index}/observation_id"),
                "external observation IDs must be unique",
            ));
        }
        if !dofs.insert(observation.global_dof_index) {
            return Err(error(
                "model_ir_linear_external_dof_duplicate",
                &format!("/observations/{index}/global_dof_index"),
                "the bounded profile accepts one observation per global DOF",
            ));
        }
        validate_observation(observation, index)?;
    }
    Ok(())
}

fn validate_binding(
    binding: &ModelIrLinearExternalBindingV1,
) -> Result<(), ProductIrContractError> {
    if binding.analysis_kind != ANALYSIS_KIND || binding.coordinate_frame != COORDINATE_FRAME {
        return Err(error(
            "model_ir_linear_external_binding_identity_invalid",
            "/binding",
            "analysis kind or coordinate frame is unsupported",
        ));
    }
    validate_id(&binding.case_id, "/binding/case_id")?;
    validate_id(&binding.load_pattern_id, "/binding/load_pattern_id")?;
    for (path, hash) in [
        (
            "/binding/model_identity/content_hash",
            binding.model_identity.content_hash.as_str(),
        ),
        (
            "/binding/model_identity/semantic_hash",
            binding.model_identity.semantic_hash.as_str(),
        ),
        (
            "/binding/model_identity/provenance_hash",
            binding.model_identity.provenance_hash.as_str(),
        ),
        (
            "/binding/analysis_request_hash",
            binding.analysis_request_hash.as_str(),
        ),
    ] {
        validate_hash(hash, path)?;
    }
    Ok(())
}

fn validate_observation(
    observation: &ModelIrLinearExternalObservationV1,
    index: usize,
) -> Result<(), ProductIrContractError> {
    let base = format!("/observations/{index}");
    validate_id(
        &observation.observation_id,
        &format!("{base}/observation_id"),
    )?;
    if observation.global_dof_index >= 1_000_000 {
        return Err(error(
            "model_ir_linear_external_dof_index_invalid",
            &format!("{base}/global_dof_index"),
            "global DOF observation exceeds the bounded ModelIR assembly domain",
        ));
    }
    validate_id(
        &observation.external_location_id,
        &format!("{base}/external_location_id"),
    )?;
    if observation.global_dof_index % 6 != observation.dof.ordinal() {
        return Err(error(
            "model_ir_linear_external_dof_mapping_invalid",
            &format!("{base}/dof"),
            "DOF label does not match global_dof_index modulo the fixed six-DOF order",
        ));
    }
    let expected_path = format!("/global_displacement/{}", observation.global_dof_index);
    if observation.native_result_path != expected_path {
        return Err(error(
            "model_ir_linear_external_result_path_invalid",
            &format!("{base}/native_result_path"),
            "native result path does not match the selected global DOF",
        ));
    }
    if observation.unit != observation.dof.unit() {
        return Err(error(
            "model_ir_linear_external_unit_invalid",
            &format!("{base}/unit"),
            "observation unit does not match the selected translational or rotational DOF",
        ));
    }
    validate_numeric(
        observation.value,
        &format!("{base}/value"),
        "external observation value must be finite",
    )?;
    validate_tolerance(&observation.tolerance, &format!("{base}/tolerance"))
}

fn validate_comparison(
    comparison: &ModelIrLinearExternalComparisonIrV1,
) -> Result<(), ProductIrContractError> {
    if comparison.schema_version != MODEL_IR_LINEAR_EXTERNAL_COMPARISON_IR_V1
        || comparison.authority != ExternalComparisonAuthorityV1::BoundedCandidate
        || comparison.claim_boundary != COMPARISON_CLAIM_BOUNDARY
    {
        return Err(error(
            "model_ir_linear_external_comparison_identity_invalid",
            "/",
            "comparison schema, authority, or claim boundary is unsupported",
        ));
    }
    validate_id(&comparison.comparison_id, "/comparison_id")?;
    validate_source(&comparison.source)?;
    validate_binding(&comparison.binding)?;
    for (path, hash) in [
        (
            "/source_result_hash",
            comparison.source_result_hash.as_str(),
        ),
        (
            "/source_recovery_hash",
            comparison.source_recovery_hash.as_str(),
        ),
        (
            "/external_result_hash",
            comparison.external_result_hash.as_str(),
        ),
    ] {
        validate_hash(hash, path)?;
    }
    if !comparison.comparison_hash.is_empty() {
        validate_hash(&comparison.comparison_hash, "/comparison_hash")?;
    }
    if comparison.rows.is_empty() || comparison.rows.len() > MAXIMUM_OBSERVATIONS {
        return Err(error(
            "model_ir_linear_external_comparison_row_count_invalid",
            "/rows",
            "comparison requires between one and 256 rows",
        ));
    }
    validate_comparison_rows(&comparison.rows)?;
    let expected_status = if comparison.rows.iter().all(|row| row.within_tolerance) {
        ExternalComparisonStatusV1::Passed
    } else {
        ExternalComparisonStatusV1::Diverged
    };
    if comparison.status != expected_status {
        return Err(error(
            "model_ir_linear_external_comparison_status_invalid",
            "/status",
            "comparison status differs from the aggregate row result",
        ));
    }
    Ok(())
}

fn validate_comparison_rows(
    rows: &[ModelIrLinearExternalComparisonRowV1],
) -> Result<(), ProductIrContractError> {
    let mut ids = BTreeSet::new();
    let mut dofs = BTreeSet::new();
    for (index, row) in rows.iter().enumerate() {
        if !ids.insert(&row.observation_id) || !dofs.insert(row.global_dof_index) {
            return Err(error(
                "model_ir_linear_external_comparison_row_duplicate",
                &format!("/rows/{index}"),
                "comparison row IDs and global DOF indices must be unique",
            ));
        }
        validate_observation(
            &ModelIrLinearExternalObservationV1 {
                observation_id: row.observation_id.clone(),
                external_location_id: row.external_location_id.clone(),
                global_dof_index: row.global_dof_index,
                dof: row.dof,
                native_result_path: row.native_result_path.clone(),
                unit: row.unit.clone(),
                value: row.external_value,
                tolerance: row.tolerance.clone(),
            },
            index,
        )?;
        for (path, value) in [
            ("native_value", row.native_value),
            ("absolute_error", row.absolute_error),
        ] {
            validate_numeric(
                value,
                &format!("/rows/{index}/{path}"),
                "comparison arithmetic must be finite",
            )?;
        }
        if row.relative_error.is_some_and(|value| !value.is_finite()) {
            return Err(error(
                "model_ir_linear_external_comparison_row_non_finite",
                &format!("/rows/{index}/relative_error"),
                "relative error must be null or finite",
            ));
        }
        let absolute = (row.native_value - row.external_value).abs();
        let relative = relative_error(absolute, row.external_value);
        let within = passes_tolerance(absolute, relative, &row.tolerance);
        if row.absolute_error.to_bits() != absolute.to_bits()
            || !optional_bits_equal(row.relative_error, relative)
            || row.within_tolerance != within
        {
            return Err(error(
                "model_ir_linear_external_comparison_row_derivation_invalid",
                &format!("/rows/{index}"),
                "comparison row differs from its exact FP64 derivation",
            ));
        }
    }
    Ok(())
}

fn validate_source(source: &ExternalSourceV1) -> Result<(), ProductIrContractError> {
    validate_hash(&source.source_artifact_hash, "/source/source_artifact_hash")?;
    if let Some(hash) = source.executable_hash.as_deref() {
        validate_hash(hash, "/source/executable_hash")?;
    }
    if source.solver_version.is_empty()
        || source.solver_version.len() > 128
        || source.solver_version.chars().any(char::is_control)
    {
        return Err(error(
            "model_ir_linear_external_solver_version_invalid",
            "/source/solver_version",
            "solver version must be 1..128 non-control characters",
        ));
    }
    validate_id(&source.run_id, "/source/run_id")?;
    let valid = match source.evidence_kind {
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
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_external_evidence_authority_invalid",
            "/source/evidence_kind",
            "solver family, evidence kind, and executable binding are inconsistent",
        ))
    }
}

fn verify_artifacts(
    source: &ExternalSourceV1,
    source_artifact: &[u8],
    executable_artifact: Option<&[u8]>,
) -> Result<(), ProductIrContractError> {
    if source_artifact.len() > MAXIMUM_ARTIFACT_BYTES
        || sha256_identity(source_artifact) != source.source_artifact_hash
    {
        return Err(error(
            "model_ir_linear_external_source_artifact_mismatch",
            "/source/source_artifact_hash",
            "external source artifact is oversized or differs from its declared SHA-256",
        ));
    }
    match (source.executable_hash.as_deref(), executable_artifact) {
        (Some(expected), Some(bytes))
            if bytes.len() <= MAXIMUM_ARTIFACT_BYTES && sha256_identity(bytes) == expected =>
        {
            Ok(())
        }
        (None, None) => Ok(()),
        (Some(_), Some(_)) => Err(error(
            "model_ir_linear_external_executable_mismatch",
            "/source/executable_hash",
            "external executable is oversized or differs from its declared SHA-256",
        )),
        (Some(_), None) => Err(error(
            "model_ir_linear_external_executable_missing",
            "/source/executable_hash",
            "external executable bytes are required by the provenance binding",
        )),
        (None, Some(_)) => Err(error(
            "model_ir_linear_external_executable_unbound",
            "/source/executable_hash",
            "external executable bytes were supplied without a hash binding",
        )),
    }
}

fn validate_tolerance(
    tolerance: &ComparisonToleranceV1,
    path: &str,
) -> Result<(), ProductIrContractError> {
    if tolerance.absolute.is_finite()
        && tolerance.relative.is_finite()
        && tolerance.absolute >= 0.0
        && tolerance.relative >= 0.0
        && tolerance.absolute <= 1.0e100
        && tolerance.relative <= 1.0e6
    {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_external_tolerance_invalid",
            path,
            "comparison tolerances must be finite, nonnegative, and bounded",
        ))
    }
}

fn validate_numeric(value: f64, path: &str, detail: &str) -> Result<(), ProductIrContractError> {
    if value.is_finite() && value.abs() <= 1.0e100 {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_external_numeric_invalid",
            path,
            detail,
        ))
    }
}

fn relative_error(absolute_error: f64, external_value: f64) -> Option<f64> {
    if external_value == 0.0 {
        if absolute_error == 0.0 {
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
        || relative_error.is_some_and(|value| value <= tolerance.relative)
}

fn optional_bits_equal(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => left.to_bits() == right.to_bits(),
        (None, None) => true,
        (Some(_), None) | (None, Some(_)) => false,
    }
}

fn hash_struct_without_field<T: Serialize>(
    value: &T,
    field: &str,
) -> Result<String, ProductIrContractError> {
    let mut value = serde_json::to_value(value).map_err(|_| {
        error(
            "model_ir_linear_external_comparison_encode_failed",
            "/",
            "comparison could not be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| {
            error(
                "model_ir_linear_external_comparison_hash_missing",
                &format!("/{field}"),
                "comparison has no self-hash field",
            )
        })?;
    Ok(sha256_identity(
        canonicalize(&value, "comparison self-hash")?.as_bytes(),
    ))
}

fn canonical_struct<T: Serialize>(
    value: &T,
    label: &str,
) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            "model_ir_linear_external_comparison_encode_failed",
            "/",
            &format!("{label} could not be represented as JSON"),
        )
    })?;
    canonicalize(&value, label)
}

fn canonicalize(value: &Value, label: &str) -> Result<String, ProductIrContractError> {
    canonicalize_model_ir_v2(value).map_err(|source| {
        error(
            "model_ir_linear_external_canonicalization_failed",
            &source.path,
            &format!("{label}: {}", source.detail),
        )
    })
}

fn validate_id(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    let bytes = value.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphanumeric()
        && bytes.iter().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(*byte, b'_' | b'-' | b'.' | b':' | b'/')
        });
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_external_identifier_invalid",
            path,
            "identifier must be 1..128 portable bytes and begin with an alphanumeric byte",
        ))
    }
}

fn validate_hash(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    let digest = value.strip_prefix("sha256:").unwrap_or_default();
    if digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_external_hash_invalid",
            path,
            "identity must be lowercase sha256:<64 hex>",
        ))
    }
}

fn binding_error(code: &str, path: &str) -> ProductIrContractError {
    error(
        code,
        path,
        "external comparison binding differs from the exact native result or recovery",
    )
}

fn error(code: &str, path: &str, detail: &str) -> ProductIrContractError {
    ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
