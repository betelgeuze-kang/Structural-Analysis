//! Bounded single-host native linear `Frame3D` job wire contracts.
//!
//! These contracts deliberately do not reuse the nonlinear Python service contract. They describe
//! a filesystem append-only handoff with no process isolation, cancellation, resume, crash
//! recovery, multi-host execution, design authority or release authority.

use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict, parse_model_ir_v2};
use crate::{
    FRAME3D_JOB_EVENT_SCHEMA_V1, FRAME3D_JOB_REQUEST_SCHEMA_V1, FRAME3D_JOB_SUBMISSION_SCHEMA_V1,
    FRAME3D_JOB_VIEW_SCHEMA_V1,
};

const REQUEST_SCHEMA: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/native_linear_frame3d_job_request_v1.schema.json"
));
const EVENT_SCHEMA: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/native_linear_frame3d_job_event_v1.schema.json"
));
const VIEW_SCHEMA: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/native_linear_frame3d_job_view_v1.schema.json"
));
const SUBMISSION_SCHEMA: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/native_linear_frame3d_job_submission_v1.schema.json"
));
const ZERO_HASH: &str = "sha256:0000000000000000000000000000000000000000000000000000000000000000";

static REQUEST_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();
static EVENT_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();
static VIEW_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();
static SUBMISSION_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

/// Stable native job contract failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeFrame3dJobError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for NativeFrame3dJobError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for NativeFrame3dJobError {}

/// Exactly one supported load source selected by the immutable request.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum NativeFrame3dJobLoadSourceV1 {
    Pattern { id: String },
    Combination { id: String },
}

/// Browser submission envelope that preserves the exact nested `ModelIR` text.
///
/// Keeping `ModelIR` as a JSON string ensures its duplicate keys and byte-level syntax are still
/// checked by the authoritative strict `ModelIR` decoder instead of being normalized by the outer
/// HTTP envelope decoder.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobSubmissionV1 {
    pub schema_version: String,
    pub job_id: String,
    pub load_source: NativeFrame3dJobLoadSourceV1,
    pub result_id: String,
    pub report_id: String,
    pub model_ir_json: String,
    pub claim_boundary: String,
}

/// Strictly decode a loopback Workbench submission and independently validate embedded `ModelIR`.
///
/// # Errors
///
/// Rejects invalid UTF-8/JSON, duplicate keys, unknown fields, profile drift, invalid identifiers,
/// or any embedded `ModelIR` that fails the strict versioned wire contract.
pub fn parse_native_frame3d_job_submission_v1(
    bytes: &[u8],
) -> Result<NativeFrame3dJobSubmissionV1, NativeFrame3dJobError> {
    let value = decode(bytes, "native_job_submission_json_invalid")?;
    validate_schema(
        &value,
        &SUBMISSION_VALIDATOR,
        SUBMISSION_SCHEMA,
        "submission",
    )?;
    let submission: NativeFrame3dJobSubmissionV1 =
        decode_typed(value, "native_job_submission_decode_failed")?;
    if submission.schema_version != FRAME3D_JOB_SUBMISSION_SCHEMA_V1 {
        return Err(error(
            "native_job_submission_profile_invalid",
            "/schema_version",
            "Native job submission schema version is unsupported",
        ));
    }
    parse_model_ir_v2(submission.model_ir_json.as_bytes()).map_err(|source| {
        error(
            "native_job_submission_model_invalid",
            "/model_ir_json",
            &format!("Embedded ModelIR failed strict validation: {}", source.code),
        )
    })?;
    Ok(submission)
}

impl NativeFrame3dJobLoadSourceV1 {
    #[must_use]
    pub fn id(&self) -> &str {
        match self {
            Self::Pattern { id } | Self::Combination { id } => id,
        }
    }
}

/// Immutable, self-hashed request stored with canonical `ModelIR` bytes.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobRequestV1 {
    pub schema_version: String,
    pub request_hash: String,
    pub job_id: String,
    pub submitted_unix_ms: u64,
    pub model_content_hash: String,
    pub load_source: NativeFrame3dJobLoadSourceV1,
    pub result_id: String,
    pub report_id: String,
    pub output_profile: String,
    pub service_profile: String,
    pub claim_boundary: String,
}

impl NativeFrame3dJobRequestV1 {
    /// Render compact sorted canonical JSON including the verified request hash.
    ///
    /// # Errors
    ///
    /// Returns a stable serialization error if canonical JSON cannot be produced.
    pub fn canonical_json(&self) -> Result<String, NativeFrame3dJobError> {
        canonical(self, "native_job_request_serialization_failed")
    }
}

/// Create and self-validate one immutable native job request.
///
/// # Errors
///
/// Rejects invalid job, model, load, result or report identities.
pub fn create_native_frame3d_job_request_v1(
    job_id: &str,
    submitted_unix_ms: u64,
    model_content_hash: &str,
    load_source: NativeFrame3dJobLoadSourceV1,
    result_id: &str,
    report_id: &str,
) -> Result<NativeFrame3dJobRequestV1, NativeFrame3dJobError> {
    let mut request = NativeFrame3dJobRequestV1 {
        schema_version: FRAME3D_JOB_REQUEST_SCHEMA_V1.to_owned(),
        request_hash: ZERO_HASH.to_owned(),
        job_id: job_id.to_owned(),
        submitted_unix_ms,
        model_content_hash: model_content_hash.to_owned(),
        load_source,
        result_id: result_id.to_owned(),
        report_id: report_id.to_owned(),
        output_profile: "hash_bound_workbench_bundle.v1".to_owned(),
        service_profile: "filesystem_append_only_single_host.v1".to_owned(),
        claim_boundary: "submitted_native_frame3d_job_not_execution_or_result_authority".to_owned(),
    };
    validate_request_schema(&to_value(&request)?)?;
    request.request_hash = projection_hash(&request, "request_hash")?;
    validate_native_frame3d_job_request_v1(&request)?;
    Ok(request)
}

/// Strictly decode and verify a native job request.
///
/// # Errors
///
/// Rejects invalid JSON, schema drift, unknown fields and stale request hashes.
pub fn parse_native_frame3d_job_request_v1(
    bytes: &[u8],
) -> Result<NativeFrame3dJobRequestV1, NativeFrame3dJobError> {
    let value = decode(bytes, "native_job_request_json_invalid")?;
    validate_request_schema(&value)?;
    let request: NativeFrame3dJobRequestV1 =
        decode_typed(value, "native_job_request_decode_failed")?;
    validate_native_frame3d_job_request_v1(&request)?;
    Ok(request)
}

/// Verify the fixed request profile and self-hash.
///
/// # Errors
///
/// Rejects schema violations and a stale request hash.
pub fn validate_native_frame3d_job_request_v1(
    request: &NativeFrame3dJobRequestV1,
) -> Result<(), NativeFrame3dJobError> {
    validate_request_schema(&to_value(request)?)?;
    if request.request_hash != projection_hash(request, "request_hash")? {
        return Err(error(
            "native_job_request_hash_mismatch",
            "/request_hash",
            "Native job request hash does not match its canonical payload",
        ));
    }
    Ok(())
}

/// Materialized job status. Events remain the append-only lifecycle record.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum NativeFrame3dJobStatusV1 {
    Queued,
    Running,
    Succeeded,
    Failed,
}

/// One lifecycle transition in the append-only hash chain.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum NativeFrame3dJobEventTypeV1 {
    Submitted,
    Started,
    Completed,
    Failed,
}

/// Hash-chain event with bounded terminal evidence.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobEventV1 {
    pub schema_version: String,
    pub event_hash: String,
    pub previous_event_hash: Option<String>,
    pub request_hash: String,
    pub job_id: String,
    pub revision: u32,
    pub occurred_unix_ms: u64,
    pub event_type: NativeFrame3dJobEventTypeV1,
    pub status: NativeFrame3dJobStatusV1,
    pub bundle_manifest_hash: Option<String>,
    pub error_code: Option<String>,
    pub claim_boundary: String,
}

impl NativeFrame3dJobEventV1 {
    /// Render compact sorted canonical JSON including the verified event hash.
    ///
    /// # Errors
    ///
    /// Returns a stable serialization error if canonical JSON cannot be produced.
    pub fn canonical_json(&self) -> Result<String, NativeFrame3dJobError> {
        canonical(self, "native_job_event_serialization_failed")
    }
}

/// Create one valid lifecycle event. Only submitted → started → terminal is represented in v1.
///
/// # Errors
///
/// Rejects any event outside the bounded submitted-started-terminal lifecycle.
#[allow(clippy::too_many_arguments)]
pub fn create_native_frame3d_job_event_v1(
    request: &NativeFrame3dJobRequestV1,
    revision: u32,
    occurred_unix_ms: u64,
    event_type: NativeFrame3dJobEventTypeV1,
    status: NativeFrame3dJobStatusV1,
    previous_event_hash: Option<String>,
    bundle_manifest_hash: Option<String>,
    error_code: Option<String>,
) -> Result<NativeFrame3dJobEventV1, NativeFrame3dJobError> {
    let mut event = NativeFrame3dJobEventV1 {
        schema_version: FRAME3D_JOB_EVENT_SCHEMA_V1.to_owned(),
        event_hash: ZERO_HASH.to_owned(),
        previous_event_hash,
        request_hash: request.request_hash.clone(),
        job_id: request.job_id.clone(),
        revision,
        occurred_unix_ms,
        event_type,
        status,
        bundle_manifest_hash,
        error_code,
        claim_boundary: "append_only_single_host_event_not_worker_isolation_or_recovery_authority"
            .to_owned(),
    };
    validate_event_content(&event)?;
    event.event_hash = projection_hash(&event, "event_hash")?;
    validate_native_frame3d_job_event_v1(&event)?;
    Ok(event)
}

/// Strictly decode, schema-check and self-hash-check one lifecycle event.
///
/// # Errors
///
/// Rejects invalid JSON, schema drift, invalid transitions and stale event hashes.
pub fn parse_native_frame3d_job_event_v1(
    bytes: &[u8],
) -> Result<NativeFrame3dJobEventV1, NativeFrame3dJobError> {
    let value = decode(bytes, "native_job_event_json_invalid")?;
    validate_event_schema(&value)?;
    let event: NativeFrame3dJobEventV1 = decode_typed(value, "native_job_event_decode_failed")?;
    validate_native_frame3d_job_event_v1(&event)?;
    Ok(event)
}

/// Verify one typed lifecycle event and its self-hash.
///
/// # Errors
///
/// Rejects schema violations, invalid transitions and stale event hashes.
pub fn validate_native_frame3d_job_event_v1(
    event: &NativeFrame3dJobEventV1,
) -> Result<(), NativeFrame3dJobError> {
    validate_event_schema(&to_value(event)?)?;
    validate_event_content(event)?;
    if event.event_hash != projection_hash(event, "event_hash")? {
        return Err(error(
            "native_job_event_hash_mismatch",
            "/event_hash",
            "Native job event hash does not match its canonical payload",
        ));
    }
    Ok(())
}

fn validate_event_content(event: &NativeFrame3dJobEventV1) -> Result<(), NativeFrame3dJobError> {
    let valid = match (event.event_type, event.status) {
        (NativeFrame3dJobEventTypeV1::Submitted, NativeFrame3dJobStatusV1::Queued) => {
            event.revision == 0
                && event.previous_event_hash.is_none()
                && event.bundle_manifest_hash.is_none()
                && event.error_code.is_none()
        }
        (NativeFrame3dJobEventTypeV1::Started, NativeFrame3dJobStatusV1::Running) => {
            event.revision == 1
                && event.previous_event_hash.is_some()
                && event.bundle_manifest_hash.is_none()
                && event.error_code.is_none()
        }
        (NativeFrame3dJobEventTypeV1::Completed, NativeFrame3dJobStatusV1::Succeeded) => {
            event.revision == 2
                && event.previous_event_hash.is_some()
                && event.bundle_manifest_hash.is_some()
                && event.error_code.is_none()
        }
        (NativeFrame3dJobEventTypeV1::Failed, NativeFrame3dJobStatusV1::Failed) => {
            event.revision == 2
                && event.previous_event_hash.is_some()
                && event.bundle_manifest_hash.is_none()
                && event.error_code.is_some()
        }
        _ => false,
    };
    if !valid {
        return Err(error(
            "native_job_event_transition_invalid",
            "/status",
            "Native job event does not satisfy the bounded submitted-started-terminal lifecycle",
        ));
    }
    Ok(())
}

/// Completed manifest reference exposed only by a succeeded view.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobArtifactV1 {
    pub path: String,
    pub content_hash: String,
    pub byte_length: u64,
}

/// Sanitized terminal failure persisted by the runner.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobFailureV1 {
    pub code: String,
    pub detail: String,
}

/// Explicit unsupported service capabilities.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(clippy::struct_excessive_bools)]
pub struct NativeFrame3dJobCapabilitiesV1 {
    pub process_isolation: bool,
    pub cancellation: bool,
    pub resume: bool,
    pub crash_recovery: bool,
    pub multi_host: bool,
}

/// Strict materialized view reconstructed at every accepted transition.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct NativeFrame3dJobViewV1 {
    pub schema_version: String,
    pub job_id: String,
    pub request_hash: String,
    pub model_content_hash: String,
    pub revision: u32,
    pub status: NativeFrame3dJobStatusV1,
    pub created_unix_ms: u64,
    pub updated_unix_ms: u64,
    pub bundle_manifest: Option<NativeFrame3dJobArtifactV1>,
    pub error: Option<NativeFrame3dJobFailureV1>,
    pub service_profile: String,
    pub capabilities: NativeFrame3dJobCapabilitiesV1,
    pub solver_truth_owner: String,
    pub result_authority: String,
    pub claim_boundary: String,
}

impl NativeFrame3dJobViewV1 {
    /// Render compact sorted canonical JSON for the materialized view.
    ///
    /// # Errors
    ///
    /// Returns a stable serialization error if canonical JSON cannot be produced.
    pub fn canonical_json(&self) -> Result<String, NativeFrame3dJobError> {
        canonical(self, "native_job_view_serialization_failed")
    }
}

/// Build a materialized view from one request and its latest event.
///
/// # Errors
///
/// Rejects request/event binding mismatches and invalid status/evidence shapes.
pub fn create_native_frame3d_job_view_v1(
    request: &NativeFrame3dJobRequestV1,
    event: &NativeFrame3dJobEventV1,
    bundle_manifest: Option<NativeFrame3dJobArtifactV1>,
    failure: Option<NativeFrame3dJobFailureV1>,
) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobError> {
    if request.job_id != event.job_id || request.request_hash != event.request_hash {
        return Err(error(
            "native_job_view_binding_mismatch",
            "/request_hash",
            "Native job view request and event identities do not match",
        ));
    }
    let view = NativeFrame3dJobViewV1 {
        schema_version: FRAME3D_JOB_VIEW_SCHEMA_V1.to_owned(),
        job_id: request.job_id.clone(),
        request_hash: request.request_hash.clone(),
        model_content_hash: request.model_content_hash.clone(),
        revision: event.revision,
        status: event.status,
        created_unix_ms: request.submitted_unix_ms,
        updated_unix_ms: event.occurred_unix_ms,
        bundle_manifest,
        error: failure,
        service_profile: "filesystem_append_only_single_host.v1".to_owned(),
        capabilities: NativeFrame3dJobCapabilitiesV1 {
            process_isolation: false,
            cancellation: false,
            resume: false,
            crash_recovery: false,
            multi_host: false,
        },
        solver_truth_owner: "structural_native_runtime".to_owned(),
        result_authority: "referenced_hash_bound_bundle_contract_only".to_owned(),
        claim_boundary: "single_host_materialized_view_not_release_or_durable_worker_authority"
            .to_owned(),
    };
    validate_native_frame3d_job_view_v1(&view)?;
    Ok(view)
}

/// Strictly decode and validate one materialized view.
///
/// # Errors
///
/// Rejects invalid JSON, schema drift, invalid timestamps and status/evidence mismatches.
pub fn parse_native_frame3d_job_view_v1(
    bytes: &[u8],
) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobError> {
    let value = decode(bytes, "native_job_view_json_invalid")?;
    validate_view_schema(&value)?;
    let view: NativeFrame3dJobViewV1 = decode_typed(value, "native_job_view_decode_failed")?;
    validate_native_frame3d_job_view_v1(&view)?;
    Ok(view)
}

/// Verify the fixed single-host profile and status/evidence shape.
///
/// # Errors
///
/// Rejects schema drift, invalid timestamps and status/evidence mismatches.
pub fn validate_native_frame3d_job_view_v1(
    view: &NativeFrame3dJobViewV1,
) -> Result<(), NativeFrame3dJobError> {
    validate_view_schema(&to_value(view)?)?;
    if view.updated_unix_ms < view.created_unix_ms {
        return Err(error(
            "native_job_view_time_invalid",
            "/updated_unix_ms",
            "Native job view update time precedes submission time",
        ));
    }
    let shape_valid = match view.status {
        NativeFrame3dJobStatusV1::Queued => {
            view.revision == 0 && view.bundle_manifest.is_none() && view.error.is_none()
        }
        NativeFrame3dJobStatusV1::Running => {
            view.revision == 1 && view.bundle_manifest.is_none() && view.error.is_none()
        }
        NativeFrame3dJobStatusV1::Succeeded => {
            view.revision == 2 && view.bundle_manifest.is_some() && view.error.is_none()
        }
        NativeFrame3dJobStatusV1::Failed => {
            view.revision == 2 && view.bundle_manifest.is_none() && view.error.is_some()
        }
    };
    if !shape_valid {
        return Err(error(
            "native_job_view_status_invalid",
            "/status",
            "Native job view status does not match its bounded evidence shape",
        ));
    }
    Ok(())
}

fn decode(bytes: &[u8], code: &str) -> Result<Value, NativeFrame3dJobError> {
    decode_json_strict(bytes).map_err(|source| error(code, &source.path, &source.detail))
}

fn decode_typed<T>(value: Value, code: &str) -> Result<T, NativeFrame3dJobError>
where
    T: for<'de> Deserialize<'de>,
{
    serde_json::from_value(value).map_err(|_| {
        error(
            code,
            "/",
            "Native job JSON could not be decoded into its typed contract",
        )
    })
}

fn canonical<T: Serialize>(value: &T, code: &str) -> Result<String, NativeFrame3dJobError> {
    canonicalize_model_ir_v2(&to_value(value)?).map_err(|_| {
        error(
            code,
            "/",
            "Native job contract could not be serialized as canonical JSON",
        )
    })
}

fn to_value<T: Serialize>(value: &T) -> Result<Value, NativeFrame3dJobError> {
    serde_json::to_value(value).map_err(|_| {
        error(
            "native_job_serialization_failed",
            "/",
            "Native job contract could not be represented as JSON",
        )
    })
}

fn projection_hash<T: Serialize>(
    value: &T,
    hash_field: &str,
) -> Result<String, NativeFrame3dJobError> {
    let mut projection = to_value(value)?;
    projection
        .as_object_mut()
        .ok_or_else(|| {
            error(
                "native_job_invariant",
                "/",
                "Native job contract root is not an object",
            )
        })?
        .remove(hash_field);
    let canonical = canonicalize_model_ir_v2(&projection).map_err(|_| {
        error(
            "native_job_hash_failed",
            "/",
            "Native job hash projection could not be canonicalized",
        )
    })?;
    Ok(format!("sha256:{:x}", Sha256::digest(canonical.as_bytes())))
}

fn validate_request_schema(value: &Value) -> Result<(), NativeFrame3dJobError> {
    validate_schema(value, &REQUEST_VALIDATOR, REQUEST_SCHEMA, "request")
}

fn validate_event_schema(value: &Value) -> Result<(), NativeFrame3dJobError> {
    validate_schema(value, &EVENT_VALIDATOR, EVENT_SCHEMA, "event")
}

fn validate_view_schema(value: &Value) -> Result<(), NativeFrame3dJobError> {
    validate_schema(value, &VIEW_VALIDATOR, VIEW_SCHEMA, "view")
}

fn validate_schema(
    value: &Value,
    cache: &'static OnceLock<Result<JSONSchema, String>>,
    schema_text: &str,
    kind: &str,
) -> Result<(), NativeFrame3dJobError> {
    let compiled = cache.get_or_init(|| {
        let schema: Value = serde_json::from_str(schema_text).map_err(|item| item.to_string())?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|item| item.to_string())
    });
    let validator = compiled.as_ref().map_err(|_| {
        error(
            "native_job_schema_contract_invalid",
            "/",
            "Embedded native job schema could not be compiled",
        )
    })?;
    if let Err(errors) = validator.validate(value) {
        let mut paths = errors
            .map(|item| {
                let path = item.instance_path.to_string();
                if path.is_empty() {
                    "/".to_owned()
                } else {
                    path
                }
            })
            .collect::<Vec<_>>();
        paths.sort();
        return Err(error(
            &format!("native_job_{kind}_schema_invalid"),
            paths.first().map_or("/", String::as_str),
            "Native job document does not satisfy its bounded v1 schema",
        ));
    }
    Ok(())
}

fn error(code: &str, path: &str, detail: &str) -> NativeFrame3dJobError {
    NativeFrame3dJobError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
