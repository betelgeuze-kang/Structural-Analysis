use std::collections::BTreeSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use structural_contracts::model_buckling_job::{
    build_model_ir_linear_buckling_durable_job_request_v1,
    parse_model_ir_linear_buckling_durable_job_request_v1,
    ModelIrLinearBucklingDurableJobRequestDocumentV1,
    MODEL_IR_LINEAR_BUCKLING_MAXIMUM_JOB_REQUEST_BYTES,
};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::model_linear_job::{
    build_model_ir_linear_durable_job_request_v1, parse_model_ir_linear_durable_job_request_v1,
    ModelIrLinearDurableJobRequestDocumentV1, MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES,
};
use structural_contracts::model_linear_recovery::parse_model_ir_linear_result_recovery_ir_v1;
use structural_contracts::product_ir::{
    parse_native_analysis_request_v1, parse_nonlinear_ndtha_report_ir_v1,
    parse_nonlinear_ndtha_result_ir_v1, sha256_identity,
};
use structural_report::{
    build_dense_spectral_report_v1, build_nonlinear_ndtha_report_v1, build_sparse_linear_report_v1,
};

use crate::{
    ModelIrLinearBucklingCheckpointBindingsV1, ModelIrLinearBucklingCheckpointV1,
    ModelIrLinearCheckpointBindingsV1, ModelIrLinearCheckpointV1, NonlinearNdthaCheckpoint,
    NonlinearNdthaExecutionStatus, PreparedModelIrLinearBucklingReferenceV1,
    PreparedModelIrLinearBucklingSpectralV1, PreparedModelIrLinearProductV1, Runtime,
    SparseLinearExecutionStatus, SparseLinearSolverStatus,
};

const JOB_SCHEMA: &str = "structural-native-durable-job-event.v1";
const JOB_PROFILE: &str = "append_only_hash_chain_single_host.v1";
const CLAIM_BOUNDARY: &str = "single_host_local_job_orchestration_not_distributed_consensus_identity_authorization_or_release_authority";
const MAX_NDTHA_REQUEST_BYTES: usize = 16 * 1024 * 1024;
const MAX_REQUEST_BYTES: usize = MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES;
const MAX_BUCKLING_REQUEST_BYTES: usize = MODEL_IR_LINEAR_BUCKLING_MAXIMUM_JOB_REQUEST_BYTES;
const MAX_CHECKPOINT_BYTES: usize = 256 * 1024 * 1024;
const MAX_RESULT_BYTES: usize = 64 * 1024 * 1024;
const MAX_REPORT_BYTES: usize = 16 * 1024 * 1024;
const MAX_DOCUMENT_BYTES: usize = 16 * 1024 * 1024;
const MAX_RECOVERY_BYTES: usize = 64 * 1024 * 1024;
const MAX_REACTION_RESULT_BYTES: usize = 64 * 1024 * 1024;
const MAX_EVENT_BYTES: usize = 1024 * 1024;
const MIN_LEASE_MILLIS: u64 = 1_000;
const MAX_LEASE_MILLIS: u64 = 3_600_000;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

const BUCKLING_PRODUCT_ARTIFACTS: [(&str, &str); 18] = [
    ("buckling-assembly-receipt.json", "application/json"),
    (
        "checkpoint.eigcp",
        "application/vnd.structural.dense-spectral-checkpoint",
    ),
    (
        "checkpoint.mbcp",
        "application/vnd.structural.model-ir-linear-buckling-checkpoint",
    ),
    ("dense-run-receipt.json", "application/json"),
    ("generated-dense-request.json", "application/json"),
    ("generated-reference-request.json", "application/json"),
    ("model-buckling-request.json", "application/json"),
    ("model-ir.json", "application/json"),
    ("reference-assembly-receipt.json", "application/json"),
    (
        "reference-checkpoint.mlpcp",
        "application/vnd.structural.model-ir-linear-checkpoint",
    ),
    (
        "reference-checkpoint.pcgcp",
        "application/vnd.structural.sparse-linear-checkpoint",
    ),
    ("reference-reaction-ir.json", "application/json"),
    ("reference-recovery-ir.json", "application/json"),
    ("reference-result-ir.json", "application/json"),
    ("report-ir.json", "application/json"),
    ("report.md", "text/markdown"),
    ("result-ir.json", "application/json"),
    ("run-receipt.json", "application/json"),
];

const BUCKLING_RUN_RECEIPT_ARTIFACTS: [(&str, &str); 17] = [
    ("model-ir.json", "model_ir"),
    ("model-buckling-request.json", "model_buckling_request"),
    (
        "generated-reference-request.json",
        "generated_reference_request",
    ),
    (
        "reference-assembly-receipt.json",
        "reference_assembly_receipt",
    ),
    ("reference-checkpoint.pcgcp", "reference_sparse_checkpoint"),
    ("reference-checkpoint.mlpcp", "reference_model_checkpoint"),
    ("reference-result-ir.json", "reference_result_ir"),
    ("reference-recovery-ir.json", "reference_recovery_ir"),
    ("reference-reaction-ir.json", "reference_reaction_ir"),
    (
        "buckling-assembly-receipt.json",
        "buckling_assembly_receipt",
    ),
    ("generated-dense-request.json", "generated_dense_request"),
    ("checkpoint.eigcp", "dense_checkpoint"),
    ("checkpoint.mbcp", "model_ir_buckling_checkpoint"),
    ("result-ir.json", "result_ir"),
    ("report-ir.json", "report_ir"),
    ("report.md", "report_document_source"),
    ("dense-run-receipt.json", "dense_run_receipt"),
];

const DENSE_RUN_RECEIPT_ARTIFACTS: [(&str, &str); 4] = [
    ("checkpoint.eigcp", "checkpoint"),
    ("result-ir.json", "result_ir"),
    ("report-ir.json", "report_ir"),
    ("report.md", "report_document_source"),
];

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct DurableJobError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl std::fmt::Display for DurableJobError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for DurableJobError {}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DurableJobStatusV1 {
    Queued,
    Running,
    Checkpointed,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DurableJobAnalysisProfileV1 {
    NonlinearNdthaCpuV1,
    ModelIrLinearCpuV1,
    ModelIrLinearBucklingCpuV1,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum JobEventTypeV1 {
    Submitted,
    Claimed,
    CheckpointPublished,
    Completed,
    Failed,
    RetryQueued,
    CancelRequested,
    Cancelled,
    LeaseExpiredRequeued,
    LeaseExpiredCancelled,
    NumericalFailurePublished,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum JobArtifactRoleV1 {
    Request,
    Checkpoint,
    ResultIr,
    ReportIr,
    ReportDocument,
    ResultRecoveryIr,
    ReactionResultIr,
    ProductArtifact,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct JobArtifactReferenceV1 {
    pub role: String,
    pub content_hash: String,
    pub byte_length: u64,
    pub media_type: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct JobNamedArtifactReferenceV1 {
    pub name: String,
    pub artifact: JobArtifactReferenceV1,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct LeaseRecordV1 {
    worker_id: String,
    token_hash: String,
    expires_unix_ms: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct JobEventV1 {
    schema_version: String,
    service_profile: String,
    claim_boundary: String,
    job_id: String,
    idempotency_key: String,
    request: JobArtifactReferenceV1,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    analysis_profile: Option<DurableJobAnalysisProfileV1>,
    status: DurableJobStatusV1,
    event_type: JobEventTypeV1,
    revision: u64,
    attempt: u32,
    progress_completed: u32,
    progress_total: u32,
    cancel_requested: bool,
    lease: Option<LeaseRecordV1>,
    checkpoint: Option<JobArtifactReferenceV1>,
    resume_contract_hash: Option<String>,
    result_ir: Option<JobArtifactReferenceV1>,
    report_ir: Option<JobArtifactReferenceV1>,
    report_document: Option<JobArtifactReferenceV1>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    result_recovery_ir: Option<JobArtifactReferenceV1>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    reaction_result_ir: Option<JobArtifactReferenceV1>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    product_artifacts: Vec<JobNamedArtifactReferenceV1>,
    error_code: Option<String>,
    created_unix_ms: u64,
    updated_unix_ms: u64,
    previous_event_hash: Option<String>,
    event_hash: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct DurableJobViewV1 {
    pub job_id: String,
    pub request: JobArtifactReferenceV1,
    #[serde(skip_serializing_if = "is_legacy_analysis_profile")]
    pub analysis_profile: DurableJobAnalysisProfileV1,
    pub status: DurableJobStatusV1,
    pub revision: u64,
    pub attempt: u32,
    pub progress_completed: u32,
    pub progress_total: u32,
    pub cancel_requested: bool,
    pub lease_worker_id: Option<String>,
    pub lease_expires_unix_ms: Option<u64>,
    pub checkpoint: Option<JobArtifactReferenceV1>,
    pub resume_contract_hash: Option<String>,
    pub result_ir: Option<JobArtifactReferenceV1>,
    pub report_ir: Option<JobArtifactReferenceV1>,
    pub report_document: Option<JobArtifactReferenceV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result_recovery_ir: Option<JobArtifactReferenceV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reaction_result_ir: Option<JobArtifactReferenceV1>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub product_artifacts: Vec<JobNamedArtifactReferenceV1>,
    pub error_code: Option<String>,
    pub created_unix_ms: u64,
    pub updated_unix_ms: u64,
    pub can_resume: bool,
    pub terminal_event_hash: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DurableJobClaimV1 {
    pub job: DurableJobViewV1,
    pub lease_token: String,
    pub request_bytes: Vec<u8>,
    pub checkpoint_bytes: Option<Vec<u8>>,
}

#[derive(Clone, Copy, Debug)]
pub struct DurableJobCompletionV1<'a> {
    pub checkpoint_bytes: &'a [u8],
    pub result_ir_bytes: &'a [u8],
    pub report_ir_bytes: &'a [u8],
    pub report_document_bytes: &'a [u8],
}

#[derive(Clone, Copy, Debug)]
pub struct ModelIrLinearDurableJobCompletionV1<'a> {
    pub checkpoint_bytes: &'a [u8],
    pub result_ir_bytes: &'a [u8],
    pub result_recovery_ir_bytes: &'a [u8],
    pub reaction_result_ir_bytes: &'a [u8],
    pub report_ir_bytes: &'a [u8],
    pub report_document_bytes: &'a [u8],
}

#[derive(Clone, Copy, Debug)]
pub struct DurableJobNamedArtifactV1<'a> {
    pub name: &'a str,
    pub media_type: &'a str,
    pub bytes: &'a [u8],
}

#[derive(Clone, Copy, Debug)]
pub struct ModelIrLinearBucklingDurableJobCompletionV1<'a> {
    pub artifacts: &'a [DurableJobNamedArtifactV1<'a>],
}

struct CompletionReferencesV1 {
    checkpoint: JobArtifactReferenceV1,
    result_ir: JobArtifactReferenceV1,
    report_ir: JobArtifactReferenceV1,
    report_document: JobArtifactReferenceV1,
}

struct ModelIrLinearCompletionReferencesV1 {
    checkpoint: JobArtifactReferenceV1,
    result_ir: JobArtifactReferenceV1,
    result_recovery_ir: JobArtifactReferenceV1,
    reaction_result_ir: JobArtifactReferenceV1,
    report_ir: JobArtifactReferenceV1,
    report_document: JobArtifactReferenceV1,
}

struct RestoredModelIrLinearJobV1 {
    request: ModelIrLinearDurableJobRequestDocumentV1,
    prepared: PreparedModelIrLinearProductV1,
    checkpoint: ModelIrLinearCheckpointV1,
}

#[derive(Debug)]
pub struct DurableJobStoreV1 {
    lock_file: PathBuf,
    jobs_directory: PathBuf,
    blobs_directory: PathBuf,
}

struct StoreLock(File);

impl Drop for StoreLock {
    fn drop(&mut self) {
        let _ignored = FileExt::unlock(&self.0);
    }
}

impl DurableJobStoreV1 {
    /// Open or initialize one local single-host append-only job store.
    ///
    /// # Errors
    ///
    /// Returns a stable error for a symlink root or filesystem initialization failure.
    pub fn open(root: &Path) -> Result<Self, DurableJobError> {
        if root.exists() && root.is_symlink() {
            return Err(job_error(
                "job_store_root_symlink_rejected",
                "/root",
                "durable job store root may not be a symbolic link",
            ));
        }
        fs::create_dir_all(root)
            .map_err(|error| io_error("job_store_initialize_failed", "/root", &error))?;
        let root = root
            .canonicalize()
            .map_err(|error| io_error("job_store_root_invalid", "/root", &error))?;
        let jobs_path = root.join("jobs");
        let blobs_root = root.join("blobs");
        let blobs_path = blobs_root.join("sha256");
        ensure_real_directory(&jobs_path, "/jobs")?;
        ensure_real_directory(&blobs_root, "/blobs")?;
        ensure_real_directory(&blobs_path, "/blobs/sha256")?;
        let lock_path = root.join("store.lock");
        reject_symlink_if_present(&lock_path, "/lock")?;
        OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(&lock_path)
            .map_err(|error| io_error("job_store_lock_open_failed", "/lock", &error))?;
        Ok(Self {
            lock_file: lock_path,
            jobs_directory: jobs_path,
            blobs_directory: blobs_path,
        })
    }

    /// Submit an idempotency-key-bound strict native request.
    ///
    /// # Errors
    ///
    /// Returns a stable error for invalid input, conflicting idempotency or durable write failure.
    pub fn submit(
        &self,
        idempotency_key: &str,
        request_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_stable_id(idempotency_key, "/idempotency_key")?;
        require_size(request_bytes, MAX_NDTHA_REQUEST_BYTES, "/request")?;
        let request = parse_native_analysis_request_v1(request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let _lock = self.lock()?;
        let job_id = job_id(idempotency_key);
        let job_path = self.jobs_directory.join(&job_id);
        if job_path.exists() {
            let latest = self.load_latest_locked(&job_id)?;
            if latest.idempotency_key != idempotency_key
                || latest.request.content_hash != request.request_hash()
                || analysis_profile(&latest) != DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1
            {
                return Err(job_error(
                    "job_idempotency_conflict",
                    "/idempotency_key",
                    "idempotency key is already bound to a different request",
                ));
            }
            return Ok(view(&latest));
        }
        let request_reference = self.store_blob_locked(
            JobArtifactRoleV1::Request,
            request.canonical_bytes(),
            "application/json",
            MAX_NDTHA_REQUEST_BYTES,
        )?;
        let event = seal_event(JobEventV1 {
            schema_version: JOB_SCHEMA.to_owned(),
            service_profile: JOB_PROFILE.to_owned(),
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            job_id: job_id.clone(),
            idempotency_key: idempotency_key.to_owned(),
            request: request_reference,
            analysis_profile: None,
            status: DurableJobStatusV1::Queued,
            event_type: JobEventTypeV1::Submitted,
            revision: 0,
            attempt: 0,
            progress_completed: 0,
            progress_total: request.request().config.step_count,
            cancel_requested: false,
            lease: None,
            checkpoint: None,
            resume_contract_hash: None,
            result_ir: None,
            report_ir: None,
            report_document: None,
            result_recovery_ir: None,
            reaction_result_ir: None,
            product_artifacts: Vec::new(),
            error_code: None,
            created_unix_ms: now_unix_ms,
            updated_unix_ms: now_unix_ms,
            previous_event_hash: None,
            event_hash: String::new(),
        })?;
        self.create_job_locked(&event)?;
        Ok(view(&event))
    }

    /// Submit one self-contained typed-`ModelIR` linear CPU job from separate source documents.
    ///
    /// # Errors
    ///
    /// Returns a stable error for strict model/request validation, identity drift, conflicting
    /// idempotency, or durable write failure.
    pub fn submit_model_ir_linear(
        &self,
        idempotency_key: &str,
        model_ir_bytes: &[u8],
        analysis_request_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        let request =
            build_model_ir_linear_durable_job_request_v1(model_ir_bytes, analysis_request_bytes)
                .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        self.submit_model_ir_linear_document(idempotency_key, &request, now_unix_ms)
    }

    /// Submit a previously packaged language-neutral typed-`ModelIR` linear job envelope.
    ///
    /// # Errors
    ///
    /// Returns the same stable boundary as [`Self::submit_model_ir_linear`].
    pub fn submit_model_ir_linear_envelope(
        &self,
        idempotency_key: &str,
        request_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        let request = parse_model_ir_linear_durable_job_request_v1(request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        self.submit_model_ir_linear_document(idempotency_key, &request, now_unix_ms)
    }

    fn submit_model_ir_linear_document(
        &self,
        idempotency_key: &str,
        request: &ModelIrLinearDurableJobRequestDocumentV1,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_stable_id(idempotency_key, "/idempotency_key")?;
        require_size(request.canonical_bytes(), MAX_REQUEST_BYTES, "/request")?;
        let _lock = self.lock()?;
        let job_id = job_id(idempotency_key);
        let job_path = self.jobs_directory.join(&job_id);
        if job_path.exists() {
            let latest = self.load_latest_locked(&job_id)?;
            if latest.idempotency_key != idempotency_key
                || latest.request.content_hash != request.request_hash()
                || analysis_profile(&latest) != DurableJobAnalysisProfileV1::ModelIrLinearCpuV1
            {
                return Err(job_error(
                    "job_idempotency_conflict",
                    "/idempotency_key",
                    "idempotency key is already bound to a different request or profile",
                ));
            }
            return Ok(view(&latest));
        }
        let request_reference = self.store_blob_locked(
            JobArtifactRoleV1::Request,
            request.canonical_bytes(),
            "application/json",
            MAX_REQUEST_BYTES,
        )?;
        let event = seal_event(JobEventV1 {
            schema_version: JOB_SCHEMA.to_owned(),
            service_profile: JOB_PROFILE.to_owned(),
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            job_id: job_id.clone(),
            idempotency_key: idempotency_key.to_owned(),
            request: request_reference,
            analysis_profile: Some(DurableJobAnalysisProfileV1::ModelIrLinearCpuV1),
            status: DurableJobStatusV1::Queued,
            event_type: JobEventTypeV1::Submitted,
            revision: 0,
            attempt: 0,
            progress_completed: 0,
            progress_total: request.analysis_request().request().config.max_iterations,
            cancel_requested: false,
            lease: None,
            checkpoint: None,
            resume_contract_hash: None,
            result_ir: None,
            report_ir: None,
            report_document: None,
            result_recovery_ir: None,
            reaction_result_ir: None,
            product_artifacts: Vec::new(),
            error_code: None,
            created_unix_ms: now_unix_ms,
            updated_unix_ms: now_unix_ms,
            previous_event_hash: None,
            event_hash: String::new(),
        })?;
        self.create_job_locked(&event)?;
        Ok(view(&event))
    }

    /// Submit one self-contained typed-`ModelIR` reference-static plus linear-buckling CPU job.
    ///
    /// # Errors
    ///
    /// Returns a stable error for strict model/request validation, identity drift, conflicting
    /// idempotency, or durable write failure.
    pub fn submit_model_ir_linear_buckling(
        &self,
        idempotency_key: &str,
        model_ir_bytes: &[u8],
        analysis_request_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        let request = build_model_ir_linear_buckling_durable_job_request_v1(
            model_ir_bytes,
            analysis_request_bytes,
        )
        .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        self.submit_model_ir_linear_buckling_document(idempotency_key, &request, now_unix_ms)
    }

    /// Submit a previously packaged language-neutral buckling job envelope.
    ///
    /// # Errors
    ///
    /// Returns the same stable boundary as [`Self::submit_model_ir_linear_buckling`].
    pub fn submit_model_ir_linear_buckling_envelope(
        &self,
        idempotency_key: &str,
        request_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        let request = parse_model_ir_linear_buckling_durable_job_request_v1(request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        self.submit_model_ir_linear_buckling_document(idempotency_key, &request, now_unix_ms)
    }

    fn submit_model_ir_linear_buckling_document(
        &self,
        idempotency_key: &str,
        request: &ModelIrLinearBucklingDurableJobRequestDocumentV1,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_stable_id(idempotency_key, "/idempotency_key")?;
        require_size(
            request.canonical_bytes(),
            MAX_BUCKLING_REQUEST_BYTES,
            "/request",
        )?;
        let _lock = self.lock()?;
        let job_id = job_id(idempotency_key);
        let job_path = self.jobs_directory.join(&job_id);
        if job_path.exists() {
            let latest = self.load_latest_locked(&job_id)?;
            if latest.idempotency_key != idempotency_key
                || latest.request.content_hash != request.request_hash()
                || analysis_profile(&latest)
                    != DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1
            {
                return Err(job_error(
                    "job_idempotency_conflict",
                    "/idempotency_key",
                    "idempotency key is already bound to a different request or profile",
                ));
            }
            return Ok(view(&latest));
        }
        let request_reference = self.store_blob_locked(
            JobArtifactRoleV1::Request,
            request.canonical_bytes(),
            "application/json",
            MAX_BUCKLING_REQUEST_BYTES,
        )?;
        let event = seal_event(JobEventV1 {
            schema_version: JOB_SCHEMA.to_owned(),
            service_profile: JOB_PROFILE.to_owned(),
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            job_id: job_id.clone(),
            idempotency_key: idempotency_key.to_owned(),
            request: request_reference,
            analysis_profile: Some(DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1),
            status: DurableJobStatusV1::Queued,
            event_type: JobEventTypeV1::Submitted,
            revision: 0,
            attempt: 0,
            progress_completed: 0,
            progress_total: 2,
            cancel_requested: false,
            lease: None,
            checkpoint: None,
            resume_contract_hash: None,
            result_ir: None,
            report_ir: None,
            report_document: None,
            result_recovery_ir: None,
            reaction_result_ir: None,
            product_artifacts: Vec::new(),
            error_code: None,
            created_unix_ms: now_unix_ms,
            updated_unix_ms: now_unix_ms,
            previous_event_hash: None,
            event_hash: String::new(),
        })?;
        self.create_job_locked(&event)?;
        Ok(view(&event))
    }

    /// Read and fully verify the append-only event chain for one job.
    ///
    /// # Errors
    ///
    /// Returns a stable error for a missing job or any chain/integrity violation.
    pub fn poll(&self, job_id: &str) -> Result<DurableJobViewV1, DurableJobError> {
        validate_job_id(job_id)?;
        let _lock = self.lock()?;
        self.load_latest_locked(job_id).map(|event| view(&event))
    }

    /// Claim the first checkpointed, then queued job under a bounded worker lease.
    ///
    /// Expired running leases are reconciled before selection.
    ///
    /// # Errors
    ///
    /// Returns a stable error for invalid worker/lease input or store corruption.
    pub fn claim_next(
        &self,
        worker_id: &str,
        lease_millis: u64,
        now_unix_ms: u64,
    ) -> Result<Option<DurableJobClaimV1>, DurableJobError> {
        validate_stable_id(worker_id, "/worker_id")?;
        if !(MIN_LEASE_MILLIS..=MAX_LEASE_MILLIS).contains(&lease_millis) {
            return Err(job_error(
                "job_lease_duration_invalid",
                "/lease_millis",
                "worker lease must be between 1000 and 3600000 milliseconds",
            ));
        }
        let _lock = self.lock()?;
        self.recover_expired_locked(now_unix_ms)?;
        let mut candidates = self.list_job_ids_locked()?;
        candidates.sort_by_key(|job_id| {
            self.load_latest_locked(job_id)
                .map_or((2_u8, job_id.clone()), |event| {
                    let priority = match event.status {
                        DurableJobStatusV1::Checkpointed => 0,
                        DurableJobStatusV1::Queued => 1,
                        _ => 2,
                    };
                    (priority, job_id.clone())
                })
        });
        for job_id in candidates {
            let current = self.load_latest_locked(&job_id)?;
            if !matches!(
                current.status,
                DurableJobStatusV1::Queued | DurableJobStatusV1::Checkpointed
            ) {
                continue;
            }
            let request_bytes = self.read_blob_locked(
                &current.request,
                maximum_request_bytes(analysis_profile(&current)),
            )?;
            let checkpoint_bytes = current
                .checkpoint
                .as_ref()
                .map(|reference| self.read_blob_locked(reference, MAX_CHECKPOINT_BYTES))
                .transpose()?;
            let token = random_token()?;
            let mut next = next_event(&current, JobEventTypeV1::Claimed, now_unix_ms)?;
            next.status = DurableJobStatusV1::Running;
            next.attempt = next.attempt.checked_add(1).ok_or_else(|| {
                job_error(
                    "job_attempt_overflow",
                    "/attempt",
                    "job attempt counter overflowed",
                )
            })?;
            next.lease = Some(LeaseRecordV1 {
                worker_id: worker_id.to_owned(),
                token_hash: lease_token_hash(&job_id, &token),
                expires_unix_ms: next.updated_unix_ms.checked_add(lease_millis).ok_or_else(
                    || {
                        job_error(
                            "job_lease_expiry_overflow",
                            "/lease_millis",
                            "worker lease expiry overflowed",
                        )
                    },
                )?,
            });
            next.error_code = None;
            let next = seal_event(next)?;
            self.append_event_locked(&current, &next)?;
            return Ok(Some(DurableJobClaimV1 {
                job: view(&next),
                lease_token: token,
                request_bytes,
                checkpoint_bytes,
            }));
        }
        Ok(None)
    }

    /// Publish a worker checkpoint and return the job to resumable state.
    ///
    /// If cancellation was requested while the lease was active, the same validated checkpoint
    /// is retained but the transition becomes terminal `cancelled`.
    ///
    /// # Errors
    ///
    /// Returns a stable error for stale lease, checkpoint mismatch, progress drift or I/O failure.
    pub fn publish_checkpoint(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        checkpoint_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        require_size(checkpoint_bytes, MAX_CHECKPOINT_BYTES, "/checkpoint")?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(&current, DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        let request_bytes = self.read_blob_locked(&current.request, MAX_NDTHA_REQUEST_BYTES)?;
        let request = parse_native_analysis_request_v1(&request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let runtime = Runtime::new().map_err(|error| runtime_source_error(&error))?;
        let state = runtime
            .restore_nonlinear_ndtha(
                &request.request().config,
                &request.request().inputs,
                checkpoint_bytes,
            )
            .map_err(|error| runtime_source_error(&error))?;
        if state.next_step < current.progress_completed
            || state.next_step > current.progress_total
            || state.status == NonlinearNdthaExecutionStatus::Nonconverged
            || (!current.cancel_requested && state.status != NonlinearNdthaExecutionStatus::Active)
        {
            return Err(job_error(
                "job_checkpoint_progress_invalid",
                "/checkpoint",
                "checkpoint progress/status is incompatible with the durable job",
            ));
        }
        let checkpoint = NonlinearNdthaCheckpoint::from_bytes(checkpoint_bytes)
            .map_err(|error| runtime_source_error(&error))?;
        let receipt = checkpoint.receipt();
        let reference = self.store_blob_locked(
            JobArtifactRoleV1::Checkpoint,
            checkpoint_bytes,
            "application/vnd.structural.ndtha-checkpoint",
            MAX_CHECKPOINT_BYTES,
        )?;
        let event_type = if current.cancel_requested {
            JobEventTypeV1::Cancelled
        } else {
            JobEventTypeV1::CheckpointPublished
        };
        let mut next = next_event(&current, event_type, now_unix_ms)?;
        next.status = if current.cancel_requested {
            DurableJobStatusV1::Cancelled
        } else {
            DurableJobStatusV1::Checkpointed
        };
        next.progress_completed = state.next_step;
        next.lease = None;
        next.checkpoint = Some(reference);
        next.resume_contract_hash = Some(receipt.checkpoint_hash);
        next.error_code = if current.cancel_requested {
            Some("cancelled_by_user".to_owned())
        } else {
            None
        };
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Publish one verified active typed-`ModelIR` linear checkpoint and release the lease.
    ///
    /// Cancellation retains the same exact checkpoint but commits a terminal cancelled event.
    ///
    /// # Errors
    ///
    /// Returns a stable error for profile mismatch, stale lease, model/request/assembly binding
    /// drift, a non-active checkpoint, or durable storage failure.
    pub fn publish_model_ir_linear_checkpoint(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        checkpoint_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        require_size(checkpoint_bytes, MAX_CHECKPOINT_BYTES, "/checkpoint")?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(&current, DurableJobAnalysisProfileV1::ModelIrLinearCpuV1)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        let restored =
            self.restore_model_ir_linear_checkpoint_locked(&current, checkpoint_bytes)?;
        let checkpoint = &restored.checkpoint;
        let state = checkpoint.inner().state();
        if !current.cancel_requested
            && state.execution_status != SparseLinearExecutionStatus::Active
        {
            return Err(job_error(
                "job_checkpoint_progress_invalid",
                "/checkpoint",
                "ModelIR linear checkpoint is not an active PCG boundary",
            ));
        }
        let reference = self.store_blob_locked(
            JobArtifactRoleV1::Checkpoint,
            checkpoint_bytes,
            "application/vnd.structural.model-ir-linear-checkpoint",
            MAX_CHECKPOINT_BYTES,
        )?;
        let event_type = if current.cancel_requested {
            JobEventTypeV1::Cancelled
        } else {
            JobEventTypeV1::CheckpointPublished
        };
        let mut next = next_event(&current, event_type, now_unix_ms)?;
        next.status = if current.cancel_requested {
            DurableJobStatusV1::Cancelled
        } else {
            DurableJobStatusV1::Checkpointed
        };
        next.progress_completed = state.iterations;
        next.lease = None;
        next.checkpoint = Some(reference);
        next.resume_contract_hash = Some(checkpoint.receipt().checkpoint_hash);
        next.error_code = current
            .cancel_requested
            .then(|| "cancelled_by_user".to_owned());
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Publish one verified terminal numerical failure with its last exact PCG boundary.
    ///
    /// # Errors
    ///
    /// Returns a stable error unless this is a leased ModelIR-linear job with a non-converged
    /// terminal checkpoint bound to its exact durable request.
    pub fn fail_model_ir_linear_job(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        checkpoint_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        require_size(checkpoint_bytes, MAX_CHECKPOINT_BYTES, "/checkpoint")?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(&current, DurableJobAnalysisProfileV1::ModelIrLinearCpuV1)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        let restored =
            self.restore_model_ir_linear_checkpoint_locked(&current, checkpoint_bytes)?;
        let checkpoint = &restored.checkpoint;
        let state = checkpoint.inner().state();
        if state.execution_status != SparseLinearExecutionStatus::Terminal
            || state.solver_status == SparseLinearSolverStatus::Converged
        {
            return Err(job_error(
                "job_checkpoint_progress_invalid",
                "/checkpoint",
                "ModelIR linear failure requires a non-converged terminal PCG boundary",
            ));
        }
        let reference = self.store_blob_locked(
            JobArtifactRoleV1::Checkpoint,
            checkpoint_bytes,
            "application/vnd.structural.model-ir-linear-checkpoint",
            MAX_CHECKPOINT_BYTES,
        )?;
        let mut next = next_event(
            &current,
            if current.cancel_requested {
                JobEventTypeV1::Cancelled
            } else {
                JobEventTypeV1::NumericalFailurePublished
            },
            now_unix_ms,
        )?;
        next.status = if current.cancel_requested {
            DurableJobStatusV1::Cancelled
        } else {
            DurableJobStatusV1::Failed
        };
        next.progress_completed = state.iterations;
        next.lease = None;
        next.checkpoint = Some(reference);
        next.resume_contract_hash = Some(checkpoint.receipt().checkpoint_hash);
        next.error_code = Some(if current.cancel_requested {
            "cancelled_by_user".to_owned()
        } else {
            sparse_failure_code(state.solver_status).to_owned()
        });
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Publish the exact terminal checkpoint, `ResultIR`, `ReportIR` and document source.
    ///
    /// # Errors
    ///
    /// Returns a stable error for stale lease, cross-artifact identity mismatch, non-terminal
    /// native state, invalid self-hash or durable storage failure.
    pub fn complete_job(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        completion: DurableJobCompletionV1<'_>,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_completion_sizes(completion)?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(&current, DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        if current.cancel_requested {
            return Err(job_error(
                "job_cancel_pending",
                "/status",
                "cancel-requested job cannot publish successful completion",
            ));
        }
        let request_bytes = self.read_blob_locked(&current.request, MAX_NDTHA_REQUEST_BYTES)?;
        let request = parse_native_analysis_request_v1(&request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let result = parse_nonlinear_ndtha_result_ir_v1(completion.result_ir_bytes)
            .map_err(|error| contract_source_error("job_result_ir_invalid", &error))?;
        let report = parse_nonlinear_ndtha_report_ir_v1(completion.report_ir_bytes)
            .map_err(|error| contract_source_error("job_report_ir_invalid", &error))?;
        if result.result().identity.request_hash != current.request.content_hash
            || result.result().case_id != request.request().case_id
            || report.report().source_result_hash != result.result_hash()
            || report.report().case_id != result.result().case_id
            || report.report().identity != result.result().identity
            || report.report().document_source_hash
                != sha256_identity(completion.report_document_bytes)
        {
            return Err(job_error(
                "job_completion_identity_mismatch",
                "/completion",
                "completion artifacts are not bound to this exact job/result/document",
            ));
        }
        let runtime = Runtime::new().map_err(|error| runtime_source_error(&error))?;
        let state = runtime
            .restore_nonlinear_ndtha(
                &request.request().config,
                &request.request().inputs,
                completion.checkpoint_bytes,
            )
            .map_err(|error| runtime_source_error(&error))?;
        if !matches!(
            state.status,
            NonlinearNdthaExecutionStatus::Completed | NonlinearNdthaExecutionStatus::Collapsed
        ) || state.next_step != result.result().summary.step_count_completed
        {
            return Err(job_error(
                "job_completion_state_invalid",
                "/checkpoint",
                "completion checkpoint is not the terminal ResultIR state",
            ));
        }
        let expected_product = runtime
            .finish_nonlinear_ndtha_product(&request, &state)
            .map_err(|error| runtime_source_error(&error))?;
        let expected_report = build_nonlinear_ndtha_report_v1(&expected_product.result_ir)
            .map_err(|error| contract_source_error("job_report_projection_failed", &error))?;
        if expected_product.checkpoint.as_bytes() != completion.checkpoint_bytes
            || expected_product.result_ir.canonical_bytes() != completion.result_ir_bytes
            || expected_report.report_ir.canonical_bytes() != completion.report_ir_bytes
            || expected_report.document_source.as_bytes() != completion.report_document_bytes
        {
            return Err(job_error(
                "job_completion_projection_mismatch",
                "/completion",
                "completion artifacts differ from the deterministic native state projection",
            ));
        }
        let checkpoint = expected_product.checkpoint;
        let references = self.store_completion_blobs_locked(completion)?;
        let mut next = next_event(&current, JobEventTypeV1::Completed, now_unix_ms)?;
        next.status = DurableJobStatusV1::Succeeded;
        next.progress_completed = state.next_step;
        next.lease = None;
        next.checkpoint = Some(references.checkpoint);
        next.resume_contract_hash = Some(checkpoint.receipt().checkpoint_hash);
        next.result_ir = Some(references.result_ir);
        next.report_ir = Some(references.report_ir);
        next.report_document = Some(references.report_document);
        next.error_code = None;
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Publish a converged typed-`ModelIR` linear checkpoint and every deterministic terminal IR.
    ///
    /// The store reconstructs the model assembly, sparse request, result, active recovery,
    /// constrained reactions, report IR and document source before committing any reference.
    ///
    /// # Errors
    ///
    /// Returns a stable error for stale lease, cancellation, profile or identity drift, a
    /// non-converged checkpoint, noncanonical output, projection mismatch, or durable I/O failure.
    pub fn complete_model_ir_linear_job(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        completion: ModelIrLinearDurableJobCompletionV1<'_>,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_model_ir_linear_completion_sizes(completion)?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(&current, DurableJobAnalysisProfileV1::ModelIrLinearCpuV1)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        if current.cancel_requested {
            return Err(job_error(
                "job_cancel_pending",
                "/status",
                "cancel-requested job cannot publish successful completion",
            ));
        }
        let restored =
            self.restore_model_ir_linear_checkpoint_locked(&current, completion.checkpoint_bytes)?;
        let state = restored.checkpoint.inner().state();
        if state.execution_status != SparseLinearExecutionStatus::Terminal
            || state.solver_status != SparseLinearSolverStatus::Converged
        {
            return Err(job_error(
                "job_completion_state_invalid",
                "/checkpoint",
                "ModelIR linear completion checkpoint is not converged and terminal",
            ));
        }
        let expected_result = Runtime::finish_sparse_linear_product(
            &restored.prepared.generated_request,
            restored.checkpoint.inner(),
        )
        .map_err(|error| runtime_source_error(&error))?;
        let expected_report = build_sparse_linear_report_v1(&expected_result)
            .map_err(|error| contract_source_error("job_report_projection_failed", &error))?;
        let runtime = Runtime::new().map_err(|error| runtime_source_error(&error))?;
        let expected_recovered = runtime
            .recover_model_ir_linear_product_artifacts(
                restored.request.model_ir(),
                restored.request.analysis_request(),
                &restored.prepared,
                &expected_result,
            )
            .map_err(|error| runtime_source_error(&error))?;
        if restored.checkpoint.as_bytes() != completion.checkpoint_bytes
            || expected_result.canonical_bytes() != completion.result_ir_bytes
            || expected_recovered.result_recovery_json.as_bytes()
                != completion.result_recovery_ir_bytes
            || expected_recovered.reaction_result_json.as_bytes()
                != completion.reaction_result_ir_bytes
            || expected_report.report_ir.canonical_json().as_bytes() != completion.report_ir_bytes
            || expected_report.document_source.as_bytes() != completion.report_document_bytes
        {
            return Err(job_error(
                "job_completion_projection_mismatch",
                "/completion",
                "ModelIR linear completion differs from deterministic native projection",
            ));
        }
        let references = self.store_model_ir_linear_completion_blobs_locked(completion)?;
        let mut next = next_event(&current, JobEventTypeV1::Completed, now_unix_ms)?;
        next.status = DurableJobStatusV1::Succeeded;
        next.progress_completed = state.iterations;
        next.lease = None;
        next.checkpoint = Some(references.checkpoint);
        next.resume_contract_hash = Some(restored.checkpoint.receipt().checkpoint_hash);
        next.result_ir = Some(references.result_ir);
        next.result_recovery_ir = Some(references.result_recovery_ir);
        next.reaction_result_ir = Some(references.reaction_result_ir);
        next.report_ir = Some(references.report_ir);
        next.report_document = Some(references.report_document);
        next.error_code = None;
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Retain one verified terminal buckling checkpoint as a cancellation/restart boundary.
    ///
    /// # Errors
    ///
    /// Returns a stable error for profile, lease, envelope, checkpoint binding, or storage drift.
    pub fn publish_model_ir_linear_buckling_checkpoint(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        checkpoint_bytes: &[u8],
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        require_size(checkpoint_bytes, MAX_CHECKPOINT_BYTES, "/checkpoint")?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(
            &current,
            DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1,
        )?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        let request_bytes = self.read_blob_locked(&current.request, MAX_BUCKLING_REQUEST_BYTES)?;
        let request = parse_model_ir_linear_buckling_durable_job_request_v1(&request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let checkpoint = ModelIrLinearBucklingCheckpointV1::from_bytes(checkpoint_bytes)
            .map_err(|error| runtime_source_error(&error))?;
        verify_buckling_checkpoint_outer_bindings(&request, &checkpoint)?;
        let reference = self.store_blob_locked(
            JobArtifactRoleV1::Checkpoint,
            checkpoint_bytes,
            "application/vnd.structural.model-ir-linear-buckling-checkpoint",
            MAX_CHECKPOINT_BYTES,
        )?;
        let mut next = next_event(
            &current,
            if current.cancel_requested {
                JobEventTypeV1::Cancelled
            } else {
                JobEventTypeV1::CheckpointPublished
            },
            now_unix_ms,
        )?;
        next.status = if current.cancel_requested {
            DurableJobStatusV1::Cancelled
        } else {
            DurableJobStatusV1::Checkpointed
        };
        next.progress_completed = current.progress_total;
        next.lease = None;
        next.checkpoint = Some(reference);
        next.resume_contract_hash = Some(checkpoint.receipt().checkpoint_hash);
        next.error_code = current
            .cancel_requested
            .then(|| "cancelled_by_user".to_owned());
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Publish the exact deterministic eighteen-artifact buckling product as one terminal event.
    ///
    /// # Errors
    ///
    /// Returns a stable error for cancellation, inventory/media drift, noncanonical JSON,
    /// checkpoint/envelope mismatch, spectral projection mismatch, or durable storage failure.
    pub fn complete_model_ir_linear_buckling_job(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_buckling_completion_inventory(completion)?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_analysis_profile(
            &current,
            DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1,
        )?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        if current.cancel_requested {
            return Err(job_error(
                "job_cancel_pending",
                "/status",
                "cancel-requested job cannot publish successful completion",
            ));
        }
        let request_bytes = self.read_blob_locked(&current.request, MAX_BUCKLING_REQUEST_BYTES)?;
        let request = parse_model_ir_linear_buckling_durable_job_request_v1(&request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let checkpoint = verify_buckling_completion(&request, completion)?;
        let product_artifacts = self.store_buckling_completion_blobs_locked(completion)?;
        let mut checkpoint_reference =
            named_artifact_reference(&product_artifacts, "checkpoint.mbcp")?;
        "checkpoint".clone_into(&mut checkpoint_reference.role);
        let mut result_reference = named_artifact_reference(&product_artifacts, "result-ir.json")?;
        "result_ir".clone_into(&mut result_reference.role);
        let mut report_reference = named_artifact_reference(&product_artifacts, "report-ir.json")?;
        "report_ir".clone_into(&mut report_reference.role);
        let mut document_reference = named_artifact_reference(&product_artifacts, "report.md")?;
        "report_document".clone_into(&mut document_reference.role);
        let mut next = next_event(&current, JobEventTypeV1::Completed, now_unix_ms)?;
        next.status = DurableJobStatusV1::Succeeded;
        next.progress_completed = current.progress_total;
        next.lease = None;
        next.checkpoint = Some(checkpoint_reference);
        next.resume_contract_hash = Some(checkpoint.receipt().checkpoint_hash);
        next.result_ir = Some(result_reference);
        next.report_ir = Some(report_reference);
        next.report_document = Some(document_reference);
        next.product_artifacts = product_artifacts;
        next.error_code = None;
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Request cooperative cancellation or immediately cancel an unleased job.
    ///
    /// # Errors
    ///
    /// Returns a stable error for a terminal job, invalid identifier or event write failure.
    pub fn request_cancel(
        &self,
        job_id: &str,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        if current.cancel_requested {
            return Ok(view(&current));
        }
        if matches!(
            current.status,
            DurableJobStatusV1::Succeeded
                | DurableJobStatusV1::Failed
                | DurableJobStatusV1::Cancelled
        ) {
            return Err(job_error(
                "job_terminal_state_conflict",
                "/status",
                "terminal job cannot accept cancellation",
            ));
        }
        let running = current.status == DurableJobStatusV1::Running;
        let event_type = if running {
            JobEventTypeV1::CancelRequested
        } else {
            JobEventTypeV1::Cancelled
        };
        let mut next = next_event(&current, event_type, now_unix_ms)?;
        next.cancel_requested = true;
        if !running {
            next.status = DurableJobStatusV1::Cancelled;
            next.error_code = Some("cancelled_by_user".to_owned());
        }
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Fail a leased attempt, optionally returning it to queued/checkpointed state.
    ///
    /// # Errors
    ///
    /// Returns a stable error for invalid error code, stale lease or event write failure.
    pub fn fail_job(
        &self,
        job_id: &str,
        worker_id: &str,
        lease_token: &str,
        error_code: &str,
        retriable: bool,
        now_unix_ms: u64,
    ) -> Result<DurableJobViewV1, DurableJobError> {
        validate_error_code(error_code)?;
        let _lock = self.lock()?;
        let current = self.load_latest_locked(job_id)?;
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        if current.cancel_requested {
            let mut next = next_event(&current, JobEventTypeV1::Cancelled, now_unix_ms)?;
            next.status = DurableJobStatusV1::Cancelled;
            next.lease = None;
            next.error_code = Some("cancelled_by_user".to_owned());
            let next = seal_event(next)?;
            self.append_event_locked(&current, &next)?;
            return Ok(view(&next));
        }
        let mut next = next_event(
            &current,
            if retriable {
                JobEventTypeV1::RetryQueued
            } else {
                JobEventTypeV1::Failed
            },
            now_unix_ms,
        )?;
        next.status = if retriable && next.checkpoint.is_some() {
            DurableJobStatusV1::Checkpointed
        } else if retriable {
            DurableJobStatusV1::Queued
        } else {
            DurableJobStatusV1::Failed
        };
        next.lease = None;
        next.error_code = Some(error_code.to_owned());
        let next = seal_event(next)?;
        self.append_event_locked(&current, &next)?;
        Ok(view(&next))
    }

    /// Reconcile every expired running lease and return the number of recovered jobs.
    ///
    /// # Errors
    ///
    /// Returns a stable error for corrupt chains or durable event write failure.
    pub fn recover_expired_leases(&self, now_unix_ms: u64) -> Result<usize, DurableJobError> {
        let _lock = self.lock()?;
        self.recover_expired_locked(now_unix_ms)
    }

    /// Read the latest validated checkpoint bytes retained by a job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the job or artifact is missing, corrupt, or too large.
    pub fn read_checkpoint(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(
            job_id,
            |event| event.checkpoint.as_ref(),
            MAX_CHECKPOINT_BYTES,
        )
    }

    /// Read the published `ResultIR` bytes for a succeeded job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the job or artifact is missing, corrupt, or too large.
    pub fn read_result_ir(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(job_id, |event| event.result_ir.as_ref(), MAX_RESULT_BYTES)
    }

    /// Read the published `ReportIR` bytes for a succeeded job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the job or artifact is missing, corrupt, or too large.
    pub fn read_report_ir(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(job_id, |event| event.report_ir.as_ref(), MAX_REPORT_BYTES)
    }

    /// Read the published deterministic report document source for a succeeded job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the job or artifact is missing, corrupt, or too large.
    pub fn read_report_document(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(
            job_id,
            |event| event.report_document.as_ref(),
            MAX_DOCUMENT_BYTES,
        )
    }

    /// Read the published typed-`ModelIR` linear recovery IR for a succeeded job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the artifact is absent, corrupt, symlinked, or oversized.
    pub fn read_result_recovery_ir(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(
            job_id,
            |event| event.result_recovery_ir.as_ref(),
            MAX_RECOVERY_BYTES,
        )
    }

    /// Read the published typed-`ModelIR` constrained-reaction `ResultIR` for a succeeded job.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the artifact is absent, corrupt, symlinked, or oversized.
    pub fn read_reaction_result_ir(&self, job_id: &str) -> Result<Vec<u8>, DurableJobError> {
        self.read_published(
            job_id,
            |event| event.reaction_result_ir.as_ref(),
            MAX_REACTION_RESULT_BYTES,
        )
    }

    /// Read one exact named artifact from a succeeded profile-specific product.
    ///
    /// # Errors
    ///
    /// Returns a stable error for an invalid name, absent artifact, corrupt chain/blob, or size.
    pub fn read_product_artifact(
        &self,
        job_id: &str,
        name: &str,
    ) -> Result<Vec<u8>, DurableJobError> {
        validate_product_artifact_name(name)?;
        let _lock = self.lock()?;
        let event = self.load_latest_locked(job_id)?;
        let reference = event
            .product_artifacts
            .iter()
            .find(|candidate| candidate.name == name)
            .map(|candidate| &candidate.artifact)
            .ok_or_else(|| {
                job_error(
                    "job_artifact_not_published",
                    "/artifact",
                    "requested named product artifact has not been published",
                )
            })?;
        self.read_blob_locked(reference, MAX_CHECKPOINT_BYTES)
    }

    fn restore_model_ir_linear_checkpoint_locked(
        &self,
        current: &JobEventV1,
        checkpoint_bytes: &[u8],
    ) -> Result<RestoredModelIrLinearJobV1, DurableJobError> {
        let request_bytes = self.read_blob_locked(&current.request, MAX_REQUEST_BYTES)?;
        let request = parse_model_ir_linear_durable_job_request_v1(&request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let runtime = Runtime::new().map_err(|error| runtime_source_error(&error))?;
        let prepared = runtime
            .prepare_model_ir_linear_product(request.model_ir(), request.analysis_request())
            .map_err(|error| runtime_source_error(&error))?;
        let bindings = ModelIrLinearCheckpointBindingsV1 {
            model_content_hash: request.model_ir().content_hash().to_owned(),
            model_semantic_hash: request.model_ir().semantic_hash().to_owned(),
            model_provenance_hash: request.model_ir().provenance_hash().to_owned(),
            analysis_request_hash: request.analysis_request().request_hash().to_owned(),
            assembly_hash: prepared.assembly_hash.clone(),
            generated_request_hash: prepared.generated_request.request_hash().to_owned(),
        };
        let checkpoint = ModelIrLinearCheckpointV1::from_bytes(checkpoint_bytes)
            .map_err(|error| runtime_source_error(&error))?;
        checkpoint
            .verify_bindings(&bindings)
            .map_err(|error| runtime_source_error(&error))?;
        Runtime::restore_sparse_linear(&prepared.generated_request, checkpoint.inner().as_bytes())
            .map_err(|error| runtime_source_error(&error))?;
        Ok(RestoredModelIrLinearJobV1 {
            request,
            prepared,
            checkpoint,
        })
    }

    fn read_published<F>(
        &self,
        job_id: &str,
        select: F,
        maximum: usize,
    ) -> Result<Vec<u8>, DurableJobError>
    where
        F: FnOnce(&JobEventV1) -> Option<&JobArtifactReferenceV1>,
    {
        let _lock = self.lock()?;
        let event = self.load_latest_locked(job_id)?;
        let reference = select(&event).ok_or_else(|| {
            job_error(
                "job_artifact_not_published",
                "/artifact",
                "requested job artifact has not been published",
            )
        })?;
        self.read_blob_locked(reference, maximum)
    }

    fn lock(&self) -> Result<StoreLock, DurableJobError> {
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&self.lock_file)
            .map_err(|error| io_error("job_store_lock_open_failed", "/lock", &error))?;
        file.lock_exclusive()
            .map_err(|error| io_error("job_store_lock_failed", "/lock", &error))?;
        Ok(StoreLock(file))
    }

    fn create_job_locked(&self, event: &JobEventV1) -> Result<(), DurableJobError> {
        let destination = self.jobs_directory.join(&event.job_id);
        let temporary = self.jobs_directory.join(format!(
            ".{}.tmp.{}.{}",
            event.job_id,
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&temporary)
            .map_err(|error| io_error("job_directory_create_failed", "/job", &error))?;
        let result = (|| -> Result<(), DurableJobError> {
            let events = temporary.join("events");
            fs::create_dir(&events).map_err(|error| {
                io_error("job_event_directory_create_failed", "/events", &error)
            })?;
            write_atomic_new(
                &events.join(event_file_name(0)),
                event_bytes(event)?.as_bytes(),
            )?;
            sync_directory(&events, "/events")?;
            sync_directory(&temporary, "/job")?;
            if destination.exists() {
                return Err(job_error(
                    "job_idempotency_race",
                    "/job_id",
                    "job destination appeared during atomic submission",
                ));
            }
            fs::rename(&temporary, &destination)
                .map_err(|error| io_error("job_publish_failed", "/job", &error))?;
            sync_directory(&self.jobs_directory, "/jobs")
        })();
        if result.is_err() {
            let _ignored = fs::remove_dir_all(&temporary);
        }
        result
    }

    fn append_event_locked(
        &self,
        previous: &JobEventV1,
        event: &JobEventV1,
    ) -> Result<(), DurableJobError> {
        validate_transition(previous, event)?;
        let events = self.jobs_directory.join(&event.job_id).join("events");
        let destination = events.join(event_file_name(event.revision));
        if destination.exists() {
            return Err(job_error(
                "job_event_revision_conflict",
                "/revision",
                "next durable job event already exists",
            ));
        }
        write_atomic_new(&destination, event_bytes(event)?.as_bytes())?;
        sync_directory(&events, "/events")
    }

    fn load_latest_locked(&self, job_id: &str) -> Result<JobEventV1, DurableJobError> {
        validate_job_id(job_id)?;
        let job_path = self.jobs_directory.join(job_id);
        let events_path = job_path.join("events");
        if !is_real_directory(&job_path)? || !is_real_directory(&events_path)? {
            return Err(job_error(
                "job_not_found",
                "/job_id",
                "durable job does not exist",
            ));
        }
        let mut paths = fs::read_dir(&events_path)
            .map_err(|error| io_error("job_event_read_failed", "/events", &error))?
            .filter_map(|entry| match entry {
                Ok(entry) if is_atomic_temporary_name(&entry.file_name()) => None,
                Ok(entry) => Some(
                    entry
                        .file_type()
                        .map_err(|error| io_error("job_event_read_failed", "/events", &error))
                        .and_then(|file_type| {
                            if file_type.is_file() {
                                Ok(entry.path())
                            } else {
                                Err(job_error(
                                    "job_event_entry_invalid",
                                    "/events",
                                    "committed event entry is not a regular file",
                                ))
                            }
                        }),
                ),
                Err(error) => Some(Err(io_error("job_event_read_failed", "/events", &error))),
            })
            .collect::<Result<Vec<_>, _>>()?;
        paths.sort();
        if paths.is_empty() {
            return Err(job_error(
                "job_event_chain_empty",
                "/events",
                "durable job has no committed event",
            ));
        }
        let mut previous: Option<JobEventV1> = None;
        for (index, path) in paths.iter().enumerate() {
            let revision = u64::try_from(index).map_err(|_| {
                job_error(
                    "job_event_revision_overflow",
                    "/events",
                    "job event count exceeds u64",
                )
            })?;
            if path.file_name().and_then(|name| name.to_str())
                != Some(event_file_name(revision).as_str())
            {
                return Err(job_error(
                    "job_event_sequence_invalid",
                    "/events",
                    "job event filenames are not one contiguous revision sequence",
                ));
            }
            let bytes = read_bounded_file(path, MAX_EVENT_BYTES, "/events")?;
            let event = parse_event(&bytes)?;
            if event.revision != revision || event.job_id != job_id {
                return Err(job_error(
                    "job_event_identity_invalid",
                    "/events",
                    "job event revision or job id differs from its durable path",
                ));
            }
            if let Some(prior) = previous.as_ref() {
                validate_transition(prior, &event)?;
            } else if !valid_genesis(&event) {
                return Err(job_error(
                    "job_event_genesis_invalid",
                    "/events/0",
                    "first durable job event is not a valid submission",
                ));
            }
            previous = Some(event);
        }
        previous.ok_or_else(|| {
            job_error(
                "job_event_chain_empty",
                "/events",
                "durable job has no committed event",
            )
        })
    }

    fn list_job_ids_locked(&self) -> Result<Vec<String>, DurableJobError> {
        fs::read_dir(&self.jobs_directory)
            .map_err(|error| io_error("job_list_failed", "/jobs", &error))?
            .filter_map(|entry| match entry {
                Ok(entry) if is_atomic_temporary_name(&entry.file_name()) => None,
                Ok(entry) => Some(
                    entry
                        .file_type()
                        .map_err(|error| io_error("job_list_failed", "/jobs", &error))
                        .and_then(|file_type| {
                            if !file_type.is_dir() {
                                return Err(job_error(
                                    "job_directory_entry_invalid",
                                    "/jobs",
                                    "committed job entry is not a real directory",
                                ));
                            }
                            entry.file_name().into_string().map_err(|_| {
                                job_error(
                                    "job_directory_name_invalid",
                                    "/jobs",
                                    "job directory name is not UTF-8",
                                )
                            })
                        }),
                ),
                Err(error) => Some(Err(io_error("job_list_failed", "/jobs", &error))),
            })
            .collect()
    }

    fn recover_expired_locked(&self, now_unix_ms: u64) -> Result<usize, DurableJobError> {
        let mut recovered = 0_usize;
        for job_id in self.list_job_ids_locked()? {
            let current = self.load_latest_locked(&job_id)?;
            let expired = current.status == DurableJobStatusV1::Running
                && current
                    .lease
                    .as_ref()
                    .is_some_and(|lease| lease.expires_unix_ms <= now_unix_ms);
            if !expired {
                continue;
            }
            let event_type = if current.cancel_requested {
                JobEventTypeV1::LeaseExpiredCancelled
            } else {
                JobEventTypeV1::LeaseExpiredRequeued
            };
            let mut next = next_event(&current, event_type, now_unix_ms)?;
            next.status = if current.cancel_requested {
                DurableJobStatusV1::Cancelled
            } else if current.checkpoint.is_some() {
                DurableJobStatusV1::Checkpointed
            } else {
                DurableJobStatusV1::Queued
            };
            next.lease = None;
            next.error_code = Some(if current.cancel_requested {
                "cancelled_after_worker_exit".to_owned()
            } else {
                "worker_lease_expired".to_owned()
            });
            let next = seal_event(next)?;
            self.append_event_locked(&current, &next)?;
            recovered += 1;
        }
        Ok(recovered)
    }

    fn store_blob_locked(
        &self,
        role: JobArtifactRoleV1,
        bytes: &[u8],
        media_type: &str,
        maximum: usize,
    ) -> Result<JobArtifactReferenceV1, DurableJobError> {
        require_size(bytes, maximum, "/artifact")?;
        let content_hash = sha256_identity(bytes);
        let path = self.blob_path(&content_hash)?;
        if path.exists() {
            let existing = read_bounded_file(&path, maximum, "/artifact")?;
            if existing != bytes {
                return Err(job_error(
                    "job_blob_hash_collision",
                    "/artifact",
                    "existing content-addressed artifact bytes differ",
                ));
            }
        } else {
            write_atomic_new(&path, bytes)?;
            sync_directory(&self.blobs_directory, "/blobs")?;
        }
        Ok(JobArtifactReferenceV1 {
            role: artifact_role(role).to_owned(),
            content_hash,
            byte_length: u64::try_from(bytes.len()).map_err(|_| {
                job_error(
                    "job_artifact_size_invalid",
                    "/artifact",
                    "artifact length exceeds u64",
                )
            })?,
            media_type: media_type.to_owned(),
        })
    }

    fn store_completion_blobs_locked(
        &self,
        completion: DurableJobCompletionV1<'_>,
    ) -> Result<CompletionReferencesV1, DurableJobError> {
        Ok(CompletionReferencesV1 {
            checkpoint: self.store_blob_locked(
                JobArtifactRoleV1::Checkpoint,
                completion.checkpoint_bytes,
                "application/vnd.structural.ndtha-checkpoint",
                MAX_CHECKPOINT_BYTES,
            )?,
            result_ir: self.store_blob_locked(
                JobArtifactRoleV1::ResultIr,
                completion.result_ir_bytes,
                "application/json",
                MAX_RESULT_BYTES,
            )?,
            report_ir: self.store_blob_locked(
                JobArtifactRoleV1::ReportIr,
                completion.report_ir_bytes,
                "application/json",
                MAX_REPORT_BYTES,
            )?,
            report_document: self.store_blob_locked(
                JobArtifactRoleV1::ReportDocument,
                completion.report_document_bytes,
                "text/markdown",
                MAX_DOCUMENT_BYTES,
            )?,
        })
    }

    fn store_model_ir_linear_completion_blobs_locked(
        &self,
        completion: ModelIrLinearDurableJobCompletionV1<'_>,
    ) -> Result<ModelIrLinearCompletionReferencesV1, DurableJobError> {
        Ok(ModelIrLinearCompletionReferencesV1 {
            checkpoint: self.store_blob_locked(
                JobArtifactRoleV1::Checkpoint,
                completion.checkpoint_bytes,
                "application/vnd.structural.model-ir-linear-checkpoint",
                MAX_CHECKPOINT_BYTES,
            )?,
            result_ir: self.store_blob_locked(
                JobArtifactRoleV1::ResultIr,
                completion.result_ir_bytes,
                "application/json",
                MAX_RESULT_BYTES,
            )?,
            result_recovery_ir: self.store_blob_locked(
                JobArtifactRoleV1::ResultRecoveryIr,
                completion.result_recovery_ir_bytes,
                "application/json",
                MAX_RECOVERY_BYTES,
            )?,
            reaction_result_ir: self.store_blob_locked(
                JobArtifactRoleV1::ReactionResultIr,
                completion.reaction_result_ir_bytes,
                "application/json",
                MAX_REACTION_RESULT_BYTES,
            )?,
            report_ir: self.store_blob_locked(
                JobArtifactRoleV1::ReportIr,
                completion.report_ir_bytes,
                "application/json",
                MAX_REPORT_BYTES,
            )?,
            report_document: self.store_blob_locked(
                JobArtifactRoleV1::ReportDocument,
                completion.report_document_bytes,
                "text/markdown",
                MAX_DOCUMENT_BYTES,
            )?,
        })
    }

    fn store_buckling_completion_blobs_locked(
        &self,
        completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
    ) -> Result<Vec<JobNamedArtifactReferenceV1>, DurableJobError> {
        completion
            .artifacts
            .iter()
            .map(|artifact| {
                Ok(JobNamedArtifactReferenceV1 {
                    name: artifact.name.to_owned(),
                    artifact: self.store_blob_locked(
                        JobArtifactRoleV1::ProductArtifact,
                        artifact.bytes,
                        artifact.media_type,
                        MAX_CHECKPOINT_BYTES,
                    )?,
                })
            })
            .collect()
    }

    fn read_blob_locked(
        &self,
        reference: &JobArtifactReferenceV1,
        maximum: usize,
    ) -> Result<Vec<u8>, DurableJobError> {
        validate_artifact_reference(reference, maximum)?;
        let bytes = read_bounded_file(
            &self.blob_path(&reference.content_hash)?,
            maximum,
            "/artifact",
        )?;
        if u64::try_from(bytes.len()).ok() != Some(reference.byte_length)
            || sha256_identity(&bytes) != reference.content_hash
        {
            return Err(job_error(
                "job_artifact_integrity_failed",
                "/artifact",
                "content-addressed artifact length or hash does not match",
            ));
        }
        Ok(bytes)
    }

    fn blob_path(&self, content_hash: &str) -> Result<PathBuf, DurableJobError> {
        validate_hash(content_hash, "/artifact/content_hash")?;
        Ok(self.blobs_directory.join(&content_hash[7..]))
    }
}

fn seal_event(mut event: JobEventV1) -> Result<JobEventV1, DurableJobError> {
    event.event_hash.clear();
    validate_event_invariants(&event)?;
    event.event_hash = hash_without_field(&event, "event_hash")?;
    Ok(event)
}

fn parse_event(bytes: &[u8]) -> Result<JobEventV1, DurableJobError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        job_error(
            "job_event_json_invalid",
            &error.path,
            "durable job event JSON is malformed or contains duplicate keys",
        )
    })?;
    let event: JobEventV1 = serde_json::from_value(value).map_err(|_| {
        job_error(
            "job_event_decode_failed",
            "/events",
            "durable job event does not satisfy the typed contract",
        )
    })?;
    validate_event_invariants(&event)?;
    let expected = hash_without_field(&event, "event_hash")?;
    if event.event_hash != expected {
        return Err(job_error(
            "job_event_hash_mismatch",
            "/event_hash",
            "durable job event self-hash does not match",
        ));
    }
    if event_bytes(&event)?.as_bytes() != bytes {
        return Err(job_error(
            "job_event_not_canonical",
            "/events",
            "durable job event bytes are not canonical",
        ));
    }
    Ok(event)
}

fn event_bytes(event: &JobEventV1) -> Result<String, DurableJobError> {
    let value = serde_json::to_value(event).map_err(|_| {
        job_error(
            "job_event_encode_failed",
            "/events",
            "durable job event could not be represented as JSON",
        )
    })?;
    canonicalize_model_ir_v2(&value).map_err(|_| {
        job_error(
            "job_event_encode_failed",
            "/events",
            "durable job event could not be canonicalized",
        )
    })
}

fn hash_without_field(event: &JobEventV1, field: &str) -> Result<String, DurableJobError> {
    let mut value = serde_json::to_value(event).map_err(|_| {
        job_error(
            "job_event_encode_failed",
            "/events",
            "durable job event could not be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| {
            job_error(
                "job_event_encode_failed",
                "/events",
                "durable job event self-hash field is missing",
            )
        })?;
    let canonical = canonicalize_model_ir_v2(&value).map_err(|_| {
        job_error(
            "job_event_encode_failed",
            "/events",
            "durable job event could not be canonicalized",
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn next_event(
    current: &JobEventV1,
    event_type: JobEventTypeV1,
    now_unix_ms: u64,
) -> Result<JobEventV1, DurableJobError> {
    let mut next = current.clone();
    next.event_type = event_type;
    next.revision = next.revision.checked_add(1).ok_or_else(|| {
        job_error(
            "job_revision_overflow",
            "/revision",
            "job revision counter overflowed",
        )
    })?;
    next.updated_unix_ms = now_unix_ms.max(current.updated_unix_ms);
    next.previous_event_hash = Some(current.event_hash.clone());
    next.event_hash.clear();
    Ok(next)
}

fn validate_transition(previous: &JobEventV1, next: &JobEventV1) -> Result<(), DurableJobError> {
    if previous.revision.checked_add(1) != Some(next.revision)
        || next.previous_event_hash.as_deref() != Some(previous.event_hash.as_str())
        || next.job_id != previous.job_id
        || next.idempotency_key != previous.idempotency_key
        || next.request != previous.request
        || next.analysis_profile != previous.analysis_profile
        || next.progress_total != previous.progress_total
        || next.created_unix_ms != previous.created_unix_ms
        || next.updated_unix_ms < previous.updated_unix_ms
        || next.progress_completed < previous.progress_completed
        || !valid_transition_shape(previous, next)
    {
        return Err(job_error(
            "job_event_transition_invalid",
            "/events",
            "durable job event breaks immutable identity, hash chain or monotonic progress",
        ));
    }
    validate_event_invariants(next)
}

fn valid_genesis(event: &JobEventV1) -> bool {
    event.event_type == JobEventTypeV1::Submitted
        && event.status == DurableJobStatusV1::Queued
        && event.revision == 0
        && event.attempt == 0
        && event.progress_completed == 0
        && !event.cancel_requested
        && event.lease.is_none()
        && event.checkpoint.is_none()
        && event.resume_contract_hash.is_none()
        && event.result_ir.is_none()
        && event.report_ir.is_none()
        && event.report_document.is_none()
        && event.result_recovery_ir.is_none()
        && event.reaction_result_ir.is_none()
        && event.product_artifacts.is_empty()
        && event.error_code.is_none()
        && event.created_unix_ms == event.updated_unix_ms
        && event.previous_event_hash.is_none()
}

fn valid_transition_shape(previous: &JobEventV1, next: &JobEventV1) -> bool {
    let expected_attempt = if next.event_type == JobEventTypeV1::Claimed {
        previous.attempt.checked_add(1)
    } else {
        Some(previous.attempt)
    };
    if expected_attempt != Some(next.attempt)
        || (next.event_type != JobEventTypeV1::Completed
            && (next.result_ir != previous.result_ir
                || next.report_ir != previous.report_ir
                || next.report_document != previous.report_document
                || next.result_recovery_ir != previous.result_recovery_ir
                || next.reaction_result_ir != previous.reaction_result_ir
                || next.product_artifacts != previous.product_artifacts))
    {
        return false;
    }
    match next.event_type {
        JobEventTypeV1::Submitted => false,
        JobEventTypeV1::Claimed => {
            matches!(
                previous.status,
                DurableJobStatusV1::Queued | DurableJobStatusV1::Checkpointed
            ) && next.status == DurableJobStatusV1::Running
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.progress_completed == previous.progress_completed
                && next.checkpoint == previous.checkpoint
                && next.resume_contract_hash == previous.resume_contract_hash
                && next.error_code.is_none()
        }
        JobEventTypeV1::CheckpointPublished => {
            previous.status == DurableJobStatusV1::Running
                && next.status == DurableJobStatusV1::Checkpointed
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.lease.is_none()
                && next.checkpoint.is_some()
                && next.error_code.is_none()
        }
        JobEventTypeV1::Completed => {
            previous.status == DurableJobStatusV1::Running
                && next.status == DurableJobStatusV1::Succeeded
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.lease.is_none()
                && next.checkpoint.is_some()
                && next.result_ir.is_some()
                && next.report_ir.is_some()
                && next.report_document.is_some()
                && next.error_code.is_none()
        }
        JobEventTypeV1::Failed => {
            previous.status == DurableJobStatusV1::Running
                && next.status == DurableJobStatusV1::Failed
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.lease.is_none()
                && next.checkpoint == previous.checkpoint
                && next.error_code.is_some()
        }
        JobEventTypeV1::NumericalFailurePublished => {
            previous.status == DurableJobStatusV1::Running
                && analysis_profile(previous) == DurableJobAnalysisProfileV1::ModelIrLinearCpuV1
                && next.status == DurableJobStatusV1::Failed
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.lease.is_none()
                && next.checkpoint.is_some()
                && next.resume_contract_hash.is_some()
                && next.error_code.is_some()
        }
        JobEventTypeV1::RetryQueued => {
            previous.status == DurableJobStatusV1::Running
                && next.status
                    == if previous.checkpoint.is_some() {
                        DurableJobStatusV1::Checkpointed
                    } else {
                        DurableJobStatusV1::Queued
                    }
                && !previous.cancel_requested
                && !next.cancel_requested
                && next.lease.is_none()
                && next.checkpoint == previous.checkpoint
                && next.error_code.is_some()
        }
        JobEventTypeV1::CancelRequested => valid_cancellation_transition(previous, next, false),
        JobEventTypeV1::Cancelled => valid_cancellation_transition(previous, next, true),
        JobEventTypeV1::LeaseExpiredRequeued => {
            valid_lease_expiry_transition(previous, next, false)
        }
        JobEventTypeV1::LeaseExpiredCancelled => {
            valid_lease_expiry_transition(previous, next, true)
        }
    }
}

fn valid_cancellation_transition(previous: &JobEventV1, next: &JobEventV1, terminal: bool) -> bool {
    if terminal {
        let cancellable = matches!(
            previous.status,
            DurableJobStatusV1::Queued | DurableJobStatusV1::Checkpointed
        ) && !previous.cancel_requested
            || previous.status == DurableJobStatusV1::Running && previous.cancel_requested;
        cancellable
            && next.status == DurableJobStatusV1::Cancelled
            && next.cancel_requested
            && next.lease.is_none()
            && next.error_code.is_some()
    } else {
        previous.status == DurableJobStatusV1::Running
            && next.status == DurableJobStatusV1::Running
            && !previous.cancel_requested
            && next.cancel_requested
            && next.lease == previous.lease
            && next.progress_completed == previous.progress_completed
            && next.checkpoint == previous.checkpoint
            && next.error_code == previous.error_code
    }
}

fn valid_lease_expiry_transition(
    previous: &JobEventV1,
    next: &JobEventV1,
    cancelled: bool,
) -> bool {
    let expected_status = if cancelled {
        DurableJobStatusV1::Cancelled
    } else if previous.checkpoint.is_some() {
        DurableJobStatusV1::Checkpointed
    } else {
        DurableJobStatusV1::Queued
    };
    let expected_error = if cancelled {
        "cancelled_after_worker_exit"
    } else {
        "worker_lease_expired"
    };
    previous.status == DurableJobStatusV1::Running
        && previous.cancel_requested == cancelled
        && next.status == expected_status
        && next.cancel_requested == cancelled
        && next.lease.is_none()
        && next.checkpoint == previous.checkpoint
        && next.progress_completed == previous.progress_completed
        && next.error_code.as_deref() == Some(expected_error)
}

fn validate_event_invariants(event: &JobEventV1) -> Result<(), DurableJobError> {
    if event.schema_version != JOB_SCHEMA
        || event.service_profile != JOB_PROFILE
        || event.claim_boundary != CLAIM_BOUNDARY
    {
        return Err(job_error(
            "job_event_contract_identity_invalid",
            "/events",
            "durable job event contract identity is invalid",
        ));
    }
    validate_job_id(&event.job_id)?;
    validate_stable_id(&event.idempotency_key, "/idempotency_key")?;
    validate_artifact_reference(
        &event.request,
        maximum_request_bytes(analysis_profile(event)),
    )?;
    if event.request.role != "request"
        || event.progress_total == 0
        || event.progress_completed > event.progress_total
        || event.updated_unix_ms < event.created_unix_ms
    {
        return Err(job_error(
            "job_event_state_invalid",
            "/events",
            "durable job event progress or request state is invalid",
        ));
    }
    if (event.status == DurableJobStatusV1::Running) != event.lease.is_some() {
        return Err(job_error(
            "job_event_lease_state_invalid",
            "/lease",
            "only a running job may retain a worker lease",
        ));
    }
    if let Some(lease) = event.lease.as_ref() {
        validate_stable_id(&lease.worker_id, "/lease/worker_id")?;
        validate_hash(&lease.token_hash, "/lease/token_hash")?;
        if lease.expires_unix_ms <= event.updated_unix_ms {
            return Err(job_error(
                "job_event_lease_expiry_invalid",
                "/lease/expires_unix_ms",
                "committed worker lease is already expired",
            ));
        }
    }
    validate_optional_artifact(
        event.checkpoint.as_ref(),
        "checkpoint",
        MAX_CHECKPOINT_BYTES,
    )?;
    validate_optional_artifact(event.result_ir.as_ref(), "result_ir", MAX_RESULT_BYTES)?;
    validate_optional_artifact(event.report_ir.as_ref(), "report_ir", MAX_REPORT_BYTES)?;
    validate_optional_artifact(
        event.report_document.as_ref(),
        "report_document",
        MAX_DOCUMENT_BYTES,
    )?;
    validate_optional_artifact(
        event.result_recovery_ir.as_ref(),
        "result_recovery_ir",
        MAX_RECOVERY_BYTES,
    )?;
    validate_optional_artifact(
        event.reaction_result_ir.as_ref(),
        "reaction_result_ir",
        MAX_REACTION_RESULT_BYTES,
    )?;
    validate_named_product_artifact_references(&event.product_artifacts)?;
    if event.checkpoint.is_some() != event.resume_contract_hash.is_some() {
        return Err(job_error(
            "job_event_checkpoint_identity_invalid",
            "/resume_contract_hash",
            "checkpoint reference and resume contract hash must appear together",
        ));
    }
    if let Some(hash) = event.resume_contract_hash.as_ref() {
        validate_hash(hash, "/resume_contract_hash")?;
    }
    validate_terminal_artifacts(event)?;
    if let Some(code) = event.error_code.as_ref() {
        validate_error_code(code)?;
    }
    if !event.event_hash.is_empty() {
        validate_hash(&event.event_hash, "/event_hash")?;
    }
    if let Some(hash) = event.previous_event_hash.as_ref() {
        validate_hash(hash, "/previous_event_hash")?;
    }
    Ok(())
}

fn validate_terminal_artifacts(event: &JobEventV1) -> Result<(), DurableJobError> {
    let succeeded = event.status == DurableJobStatusV1::Succeeded;
    let terminal_artifacts_complete =
        event.result_ir.is_some() && event.report_ir.is_some() && event.report_document.is_some();
    let any_terminal_artifact = event.result_ir.is_some()
        || event.report_ir.is_some()
        || event.report_document.is_some()
        || event.result_recovery_ir.is_some()
        || event.reaction_result_ir.is_some()
        || !event.product_artifacts.is_empty();
    let profile_terminal_valid = match analysis_profile(event) {
        DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1 => {
            event.result_recovery_ir.is_none()
                && event.reaction_result_ir.is_none()
                && event.product_artifacts.is_empty()
                && event.progress_completed == event.progress_total
        }
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 => {
            event.result_recovery_ir.is_some()
                && event.product_artifacts.is_empty()
                && event.progress_completed <= event.progress_total
        }
        DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1 => {
            event.result_recovery_ir.is_none()
                && event.reaction_result_ir.is_none()
                && valid_buckling_product_references(event)
                && event.progress_completed == event.progress_total
        }
    };
    if (succeeded && !(terminal_artifacts_complete && profile_terminal_valid))
        || (!succeeded && any_terminal_artifact)
    {
        Err(job_error(
            "job_event_terminal_artifacts_invalid",
            "/status",
            "only succeeded jobs may expose a complete terminal artifact set",
        ))
    } else {
        Ok(())
    }
}

fn view(event: &JobEventV1) -> DurableJobViewV1 {
    DurableJobViewV1 {
        job_id: event.job_id.clone(),
        request: event.request.clone(),
        analysis_profile: analysis_profile(event),
        status: event.status,
        revision: event.revision,
        attempt: event.attempt,
        progress_completed: event.progress_completed,
        progress_total: event.progress_total,
        cancel_requested: event.cancel_requested,
        lease_worker_id: event.lease.as_ref().map(|lease| lease.worker_id.clone()),
        lease_expires_unix_ms: event.lease.as_ref().map(|lease| lease.expires_unix_ms),
        checkpoint: event.checkpoint.clone(),
        resume_contract_hash: event.resume_contract_hash.clone(),
        result_ir: event.result_ir.clone(),
        report_ir: event.report_ir.clone(),
        report_document: event.report_document.clone(),
        result_recovery_ir: event.result_recovery_ir.clone(),
        reaction_result_ir: event.reaction_result_ir.clone(),
        product_artifacts: event.product_artifacts.clone(),
        error_code: event.error_code.clone(),
        created_unix_ms: event.created_unix_ms,
        updated_unix_ms: event.updated_unix_ms,
        can_resume: event.checkpoint.is_some() && event.status == DurableJobStatusV1::Checkpointed,
        terminal_event_hash: event.event_hash.clone(),
    }
}

fn analysis_profile(event: &JobEventV1) -> DurableJobAnalysisProfileV1 {
    event
        .analysis_profile
        .unwrap_or(DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1)
}

#[allow(clippy::trivially_copy_pass_by_ref)] // serde skip predicate requires `&T`.
const fn is_legacy_analysis_profile(profile: &DurableJobAnalysisProfileV1) -> bool {
    matches!(profile, DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1)
}

const fn maximum_request_bytes(profile: DurableJobAnalysisProfileV1) -> usize {
    match profile {
        DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1 => MAX_NDTHA_REQUEST_BYTES,
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 => MAX_REQUEST_BYTES,
        DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1 => MAX_BUCKLING_REQUEST_BYTES,
    }
}

fn require_analysis_profile(
    event: &JobEventV1,
    expected: DurableJobAnalysisProfileV1,
) -> Result<(), DurableJobError> {
    if analysis_profile(event) == expected {
        Ok(())
    } else {
        Err(job_error(
            "job_analysis_profile_mismatch",
            "/analysis_profile",
            "durable job operation does not match the submitted analysis profile",
        ))
    }
}

const fn sparse_failure_code(status: SparseLinearSolverStatus) -> &'static str {
    match status {
        SparseLinearSolverStatus::Converged => "model_ir_linear_unexpected_convergence",
        SparseLinearSolverStatus::Singularity => "model_ir_linear_singularity",
        SparseLinearSolverStatus::IndefiniteOperator => "model_ir_linear_indefinite_operator",
        SparseLinearSolverStatus::Nonconvergence => "model_ir_linear_nonconvergence",
        SparseLinearSolverStatus::IncrementLimit => "model_ir_linear_increment_limit",
        SparseLinearSolverStatus::ResidualLimit => "model_ir_linear_residual_limit",
    }
}

fn require_lease(
    event: &JobEventV1,
    worker_id: &str,
    token: &str,
    now_unix_ms: u64,
) -> Result<(), DurableJobError> {
    validate_stable_id(worker_id, "/worker_id")?;
    let lease = event.lease.as_ref().ok_or_else(|| {
        job_error(
            "job_lease_state_invalid",
            "/lease",
            "job does not have an active worker lease",
        )
    })?;
    let supplied = lease_token_hash(&event.job_id, token);
    if event.status != DurableJobStatusV1::Running
        || lease.worker_id != worker_id
        || !constant_time_equal(lease.token_hash.as_bytes(), supplied.as_bytes())
    {
        return Err(job_error(
            "job_lease_unauthorized",
            "/lease_token",
            "worker does not own this exact job lease",
        ));
    }
    if lease.expires_unix_ms <= now_unix_ms {
        return Err(job_error(
            "job_lease_expired",
            "/lease_token",
            "worker lease has expired",
        ));
    }
    Ok(())
}

fn random_token() -> Result<String, DurableJobError> {
    let mut bytes = [0_u8; 32];
    getrandom::getrandom(&mut bytes).map_err(|_| {
        job_error(
            "job_lease_token_generation_failed",
            "/lease_token",
            "operating system randomness is unavailable",
        )
    })?;
    Ok(hex(&bytes))
}

fn lease_token_hash(job_id: &str, token: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(b"structural-native-job-lease.v1\0");
    digest.update(job_id.as_bytes());
    digest.update([0]);
    digest.update(token.as_bytes());
    format!("sha256:{:x}", digest.finalize())
}

fn job_id(idempotency_key: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(b"structural-native-job-id.v1\0");
    digest.update(idempotency_key.as_bytes());
    format!("job-{:x}", digest.finalize())
}

fn artifact_role(role: JobArtifactRoleV1) -> &'static str {
    match role {
        JobArtifactRoleV1::Request => "request",
        JobArtifactRoleV1::Checkpoint => "checkpoint",
        JobArtifactRoleV1::ResultIr => "result_ir",
        JobArtifactRoleV1::ReportIr => "report_ir",
        JobArtifactRoleV1::ReportDocument => "report_document",
        JobArtifactRoleV1::ResultRecoveryIr => "result_recovery_ir",
        JobArtifactRoleV1::ReactionResultIr => "reaction_result_ir",
        JobArtifactRoleV1::ProductArtifact => "product_artifact",
    }
}

fn event_file_name(revision: u64) -> String {
    format!("{revision:020}.json")
}

fn validate_optional_artifact(
    reference: Option<&JobArtifactReferenceV1>,
    role: &str,
    maximum: usize,
) -> Result<(), DurableJobError> {
    if let Some(reference) = reference {
        validate_artifact_reference(reference, maximum)?;
        if reference.role != role {
            return Err(job_error(
                "job_artifact_role_invalid",
                "/artifact/role",
                "job artifact role does not match its state slot",
            ));
        }
    }
    Ok(())
}

fn validate_product_artifact_name(name: &str) -> Result<(), DurableJobError> {
    if BUCKLING_PRODUCT_ARTIFACTS
        .iter()
        .any(|(expected, _)| *expected == name)
    {
        Ok(())
    } else {
        Err(job_error(
            "job_product_artifact_name_invalid",
            "/artifact/name",
            "named product artifact is outside the fixed buckling inventory",
        ))
    }
}

fn validate_named_product_artifact_references(
    references: &[JobNamedArtifactReferenceV1],
) -> Result<(), DurableJobError> {
    if references.is_empty() {
        return Ok(());
    }
    if references.len() != BUCKLING_PRODUCT_ARTIFACTS.len() {
        return Err(job_error(
            "job_product_artifact_inventory_invalid",
            "/product_artifacts",
            "named product artifact inventory is incomplete",
        ));
    }
    for (reference, (expected_name, expected_media_type)) in
        references.iter().zip(BUCKLING_PRODUCT_ARTIFACTS)
    {
        if reference.name != expected_name
            || reference.artifact.role != "product_artifact"
            || reference.artifact.media_type != expected_media_type
        {
            return Err(job_error(
                "job_product_artifact_inventory_invalid",
                "/product_artifacts",
                "named product artifact order, role, or media type drifted",
            ));
        }
        validate_artifact_reference(&reference.artifact, MAX_CHECKPOINT_BYTES)?;
    }
    Ok(())
}

fn valid_buckling_product_references(event: &JobEventV1) -> bool {
    if validate_named_product_artifact_references(&event.product_artifacts).is_err() {
        return false;
    }
    [
        ("checkpoint.mbcp", event.checkpoint.as_ref()),
        ("result-ir.json", event.result_ir.as_ref()),
        ("report-ir.json", event.report_ir.as_ref()),
        ("report.md", event.report_document.as_ref()),
    ]
    .into_iter()
    .all(|(name, common)| {
        common.is_some_and(|common| {
            event.product_artifacts.iter().any(|named| {
                named.name == name
                    && named.artifact.content_hash == common.content_hash
                    && named.artifact.byte_length == common.byte_length
                    && named.artifact.media_type == common.media_type
            })
        })
    })
}

fn validate_buckling_completion_inventory(
    completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
) -> Result<(), DurableJobError> {
    if completion.artifacts.len() != BUCKLING_PRODUCT_ARTIFACTS.len() {
        return Err(job_error(
            "job_completion_inventory_invalid",
            "/completion/artifacts",
            "buckling completion must contain exactly eighteen artifacts",
        ));
    }
    for (artifact, (expected_name, expected_media_type)) in
        completion.artifacts.iter().zip(BUCKLING_PRODUCT_ARTIFACTS)
    {
        if artifact.name != expected_name || artifact.media_type != expected_media_type {
            return Err(job_error(
                "job_completion_inventory_invalid",
                "/completion/artifacts",
                "buckling completion artifact order, name, or media type drifted",
            ));
        }
        require_size(
            artifact.bytes,
            MAX_CHECKPOINT_BYTES,
            "/completion/artifacts",
        )?;
        if artifact.media_type == "application/json" {
            let value = decode_json_strict(artifact.bytes).map_err(|error| {
                job_error(
                    "job_completion_json_invalid",
                    &error.path,
                    "buckling completion JSON is malformed or contains duplicate keys",
                )
            })?;
            let canonical = canonicalize_model_ir_v2(&value).map_err(|_| {
                job_error(
                    "job_completion_json_invalid",
                    "/completion/artifacts",
                    "buckling completion JSON cannot be canonicalized",
                )
            })?;
            if canonical.as_bytes() != artifact.bytes {
                return Err(job_error(
                    "job_completion_json_not_canonical",
                    "/completion/artifacts",
                    "buckling completion JSON is not canonical",
                ));
            }
        }
    }
    Ok(())
}

#[allow(clippy::too_many_lines)] // Explicitly verifies every independently published product phase.
fn verify_buckling_completion(
    request: &ModelIrLinearBucklingDurableJobRequestDocumentV1,
    completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
) -> Result<ModelIrLinearBucklingCheckpointV1, DurableJobError> {
    if buckling_completion_artifact(completion, "model-ir.json")?.bytes
        != request.model_ir().canonical_bytes()
        || buckling_completion_artifact(completion, "model-buckling-request.json")?.bytes
            != request.analysis_request().canonical_bytes()
    {
        return Err(job_error(
            "job_completion_identity_mismatch",
            "/completion",
            "buckling product model/request differs from the durable envelope",
        ));
    }
    let checkpoint = ModelIrLinearBucklingCheckpointV1::from_bytes(
        buckling_completion_artifact(completion, "checkpoint.mbcp")?.bytes,
    )
    .map_err(|error| runtime_source_error(&error))?;
    verify_buckling_checkpoint_outer_bindings(request, &checkpoint)?;
    if checkpoint.reference().as_bytes()
        != buckling_completion_artifact(completion, "reference-checkpoint.mlpcp")?.bytes
        || checkpoint.reference().inner().as_bytes()
            != buckling_completion_artifact(completion, "reference-checkpoint.pcgcp")?.bytes
        || checkpoint.spectral().as_bytes()
            != buckling_completion_artifact(completion, "checkpoint.eigcp")?.bytes
    {
        return Err(job_error(
            "job_completion_projection_mismatch",
            "/completion",
            "buckling aggregate checkpoint differs from published phase checkpoints",
        ));
    }
    let runtime = Runtime::new().map_err(|error| runtime_source_error(&error))?;
    let reference = runtime
        .prepare_model_ir_linear_buckling_reference(request.model_ir(), request.analysis_request())
        .map_err(|error| runtime_source_error(&error))?;
    let reference_result = Runtime::finish_sparse_linear_product(
        &reference.product.generated_request,
        checkpoint.reference().inner(),
    )
    .map_err(|error| runtime_source_error(&error))?;
    let recovered = runtime
        .recover_model_ir_linear_product_artifacts(
            request.model_ir(),
            &reference.request,
            &reference.product,
            &reference_result,
        )
        .map_err(|error| runtime_source_error(&error))?;
    let recovered_document =
        parse_model_ir_linear_result_recovery_ir_v1(recovered.result_recovery_json.as_bytes())
            .map_err(|error| contract_source_error("job_result_recovery_ir_invalid", &error))?;
    if reference.request.canonical_bytes()
        != buckling_completion_artifact(completion, "generated-reference-request.json")?.bytes
        || reference.product.assembly_receipt_json.as_bytes()
            != buckling_completion_artifact(completion, "reference-assembly-receipt.json")?.bytes
        || reference_result.canonical_bytes()
            != buckling_completion_artifact(completion, "reference-result-ir.json")?.bytes
        || recovered.result_recovery_json.as_bytes()
            != buckling_completion_artifact(completion, "reference-recovery-ir.json")?.bytes
        || recovered.reaction_result_json.as_bytes()
            != buckling_completion_artifact(completion, "reference-reaction-ir.json")?.bytes
    {
        return Err(job_error(
            "job_completion_projection_mismatch",
            "/completion",
            "buckling reference-static product differs from deterministic native projection",
        ));
    }
    let spectral = runtime
        .prepare_model_ir_linear_buckling_spectral(
            request.model_ir(),
            request.analysis_request(),
            &reference,
            &recovered_document.recovery().global_displacement,
            reference_result.result_hash(),
            recovered_document.recovery_hash(),
        )
        .map_err(|error| runtime_source_error(&error))?;
    checkpoint
        .verify_bindings(&ModelIrLinearBucklingCheckpointBindingsV1 {
            model_content_hash: request.model_ir().content_hash().to_owned(),
            model_semantic_hash: request.model_ir().semantic_hash().to_owned(),
            model_provenance_hash: request.model_ir().provenance_hash().to_owned(),
            analysis_request_hash: request.analysis_request().request_hash().to_owned(),
            generated_reference_request_hash: reference.request.request_hash().to_owned(),
            reference_assembly_hash: reference.product.assembly_hash.clone(),
            buckling_assembly_hash: spectral.assembly_hash.clone(),
            generated_spectral_request_hash: spectral.generated_request.request_hash().to_owned(),
            reference_result_hash: reference_result.result_hash().to_owned(),
            reference_recovery_hash: recovered_document.recovery_hash().to_owned(),
        })
        .map_err(|error| runtime_source_error(&error))?;
    if spectral.assembly_receipt_json.as_bytes()
        != buckling_completion_artifact(completion, "buckling-assembly-receipt.json")?.bytes
        || spectral.generated_request.canonical_bytes()
            != buckling_completion_artifact(completion, "generated-dense-request.json")?.bytes
    {
        return Err(job_error(
            "job_completion_projection_mismatch",
            "/completion",
            "buckling K/Kg assembly differs from deterministic native projection",
        ));
    }
    let expected = runtime
        .execute_dense_spectral_product(
            &spectral.generated_request,
            Some(checkpoint.spectral().as_bytes()),
        )
        .map_err(|error| runtime_source_error(&error))?;
    let expected_report = build_dense_spectral_report_v1(&expected.result_ir)
        .map_err(|error| contract_source_error("job_report_projection_failed", &error))?;
    if expected.result_ir.canonical_bytes()
        != buckling_completion_artifact(completion, "result-ir.json")?.bytes
        || expected_report.report_ir.canonical_json().as_bytes()
            != buckling_completion_artifact(completion, "report-ir.json")?.bytes
        || expected_report.document_source.as_bytes()
            != buckling_completion_artifact(completion, "report.md")?.bytes
    {
        return Err(job_error(
            "job_completion_projection_mismatch",
            "/completion",
            "buckling result/report differs from deterministic spectral projection",
        ));
    }
    verify_buckling_completion_receipts(completion, request, &checkpoint, &reference, &spectral)?;
    Ok(checkpoint)
}

fn verify_buckling_completion_receipts(
    completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
    request: &ModelIrLinearBucklingDurableJobRequestDocumentV1,
    checkpoint: &ModelIrLinearBucklingCheckpointV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    spectral: &PreparedModelIrLinearBucklingSpectralV1,
) -> Result<(), DurableJobError> {
    let dense = parse_and_verify_completion_receipt(
        completion,
        "dense-run-receipt.json",
        "structural-dense-spectral-run-receipt.v1",
        &DENSE_RUN_RECEIPT_ARTIFACTS,
    )?;
    let dense_checkpoint = serde_json::to_value(checkpoint.spectral().receipt()).map_err(|_| {
        job_error(
            "job_completion_receipt_invalid",
            "/completion/dense-run-receipt.json",
            "dense checkpoint receipt cannot be represented as JSON",
        )
    })?;
    if dense["status"] != "completed"
        || dense["case_id"] != request.analysis_request().request().case_id
        || dense["analysis_kind"] != "linear_buckling"
        || dense["request_hash"] != spectral.generated_request.request_hash()
        || dense["checkpoint"] != dense_checkpoint
    {
        return Err(job_error(
            "job_completion_receipt_identity_mismatch",
            "/completion/dense-run-receipt.json",
            "dense run receipt is not bound to the regenerated spectral product",
        ));
    }

    let outer = parse_and_verify_completion_receipt(
        completion,
        "run-receipt.json",
        "structural-model-ir-linear-buckling-run-receipt.v1",
        &BUCKLING_RUN_RECEIPT_ARTIFACTS,
    )?;
    let outer_checkpoint = serde_json::to_value(checkpoint.receipt()).map_err(|_| {
        job_error(
            "job_completion_receipt_invalid",
            "/completion/run-receipt.json",
            "buckling checkpoint receipt cannot be represented as JSON",
        )
    })?;
    let reference_checkpoint =
        serde_json::to_value(checkpoint.reference().receipt()).map_err(|_| {
            job_error(
                "job_completion_receipt_invalid",
                "/completion/run-receipt.json",
                "reference checkpoint receipt cannot be represented as JSON",
            )
        })?;
    let model_identity = serde_json::to_value(&request.analysis_request().request().model_identity)
        .map_err(|_| {
            job_error(
                "job_completion_receipt_invalid",
                "/completion/run-receipt.json",
                "model identity cannot be represented as JSON",
            )
        })?;
    let checkpoint_receipt = checkpoint.receipt();
    if outer["status"] != "completed"
        || outer["fallback_count"] != 0
        || outer["case_id"] != request.analysis_request().request().case_id
        || outer["model_id"] != request.model_ir().model_id()
        || outer["model_identity"] != model_identity
        || outer["analysis_request_hash"] != request.analysis_request().request_hash()
        || outer["generated_reference_request_hash"] != reference.request.request_hash()
        || outer["reference_linear_assembly_hash"] != reference.product.assembly_hash
        || outer["reference_result_hash"] != checkpoint_receipt.reference_result_hash
        || outer["reference_recovery_hash"] != checkpoint_receipt.reference_recovery_hash
        || outer["buckling_assembly_hash"] != spectral.assembly_hash
        || outer["generated_dense_request_hash"] != spectral.generated_request.request_hash()
        || outer["model_ir_linear_buckling_checkpoint"] != outer_checkpoint
        || outer["reference_checkpoint"] != reference_checkpoint
        || outer["dense_checkpoint"] != dense_checkpoint
    {
        return Err(job_error(
            "job_completion_receipt_identity_mismatch",
            "/completion/run-receipt.json",
            "buckling run receipt is not bound to the regenerated product",
        ));
    }
    Ok(())
}

fn parse_and_verify_completion_receipt(
    completion: ModelIrLinearBucklingDurableJobCompletionV1<'_>,
    receipt_name: &str,
    schema_version: &str,
    expected_artifacts: &[(&str, &str)],
) -> Result<serde_json::Value, DurableJobError> {
    let bytes = buckling_completion_artifact(completion, receipt_name)?.bytes;
    let mut value = decode_json_strict(bytes).map_err(|error| {
        job_error(
            "job_completion_receipt_invalid",
            &error.path,
            "completion receipt JSON is malformed or contains duplicate keys",
        )
    })?;
    if value["schema_version"] != schema_version {
        return Err(job_error(
            "job_completion_receipt_invalid",
            "/completion/receipt/schema_version",
            "completion receipt schema is unsupported",
        ));
    }
    let receipt_hash = value["receipt_hash"]
        .as_str()
        .ok_or_else(|| {
            job_error(
                "job_completion_receipt_invalid",
                "/completion/receipt/receipt_hash",
                "completion receipt self-hash is missing",
            )
        })?
        .to_owned();
    value
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            job_error(
                "job_completion_receipt_invalid",
                "/completion/receipt",
                "completion receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_model_ir_v2(&value).map_err(|_| {
        job_error(
            "job_completion_receipt_invalid",
            "/completion/receipt",
            "completion receipt cannot be canonicalized",
        )
    })?;
    if receipt_hash != sha256_identity(unsigned.as_bytes()) {
        return Err(job_error(
            "job_completion_receipt_hash_mismatch",
            "/completion/receipt/receipt_hash",
            "completion receipt self-hash does not match",
        ));
    }
    value
        .as_object_mut()
        .expect("receipt object checked above")
        .insert(
            "receipt_hash".to_owned(),
            serde_json::Value::String(receipt_hash),
        );
    let rows = value["artifacts"].as_array().ok_or_else(|| {
        job_error(
            "job_completion_receipt_invalid",
            "/completion/receipt/artifacts",
            "completion receipt artifact inventory is missing",
        )
    })?;
    if rows.len() != expected_artifacts.len() {
        return Err(job_error(
            "job_completion_receipt_invalid",
            "/completion/receipt/artifacts",
            "completion receipt artifact inventory length drifted",
        ));
    }
    let mut seen = BTreeSet::new();
    for (row, (expected_file, expected_role)) in rows.iter().zip(expected_artifacts) {
        let file = row["file"].as_str().unwrap_or_default();
        let artifact = buckling_completion_artifact(completion, file)?;
        if file != *expected_file
            || row["role"] != *expected_role
            || row["media_type"] != artifact.media_type
            || row["byte_length"].as_u64() != u64::try_from(artifact.bytes.len()).ok()
            || row["content_hash"] != sha256_identity(artifact.bytes)
            || !seen.insert(file)
        {
            return Err(job_error(
                "job_completion_receipt_artifact_mismatch",
                "/completion/receipt/artifacts",
                "completion receipt artifact row differs from exact supplied bytes",
            ));
        }
    }
    Ok(value)
}

fn buckling_completion_artifact<'a>(
    completion: ModelIrLinearBucklingDurableJobCompletionV1<'a>,
    name: &str,
) -> Result<&'a DurableJobNamedArtifactV1<'a>, DurableJobError> {
    completion
        .artifacts
        .iter()
        .find(|artifact| artifact.name == name)
        .ok_or_else(|| {
            job_error(
                "job_completion_inventory_invalid",
                "/completion/artifacts",
                "required buckling completion artifact is missing",
            )
        })
}

fn named_artifact_reference(
    references: &[JobNamedArtifactReferenceV1],
    name: &str,
) -> Result<JobArtifactReferenceV1, DurableJobError> {
    references
        .iter()
        .find(|reference| reference.name == name)
        .map(|reference| reference.artifact.clone())
        .ok_or_else(|| {
            job_error(
                "job_completion_inventory_invalid",
                "/completion/artifacts",
                "required stored buckling artifact is missing",
            )
        })
}

fn verify_buckling_checkpoint_outer_bindings(
    request: &ModelIrLinearBucklingDurableJobRequestDocumentV1,
    checkpoint: &ModelIrLinearBucklingCheckpointV1,
) -> Result<(), DurableJobError> {
    let receipt = checkpoint.receipt();
    if receipt.model_content_hash != request.model_ir().content_hash()
        || receipt.model_semantic_hash != request.model_ir().semantic_hash()
        || receipt.model_provenance_hash != request.model_ir().provenance_hash()
        || receipt.analysis_request_hash != request.analysis_request().request_hash()
    {
        Err(job_error(
            "job_completion_identity_mismatch",
            "/checkpoint",
            "buckling checkpoint is not bound to the durable model/request",
        ))
    } else {
        Ok(())
    }
}

fn validate_artifact_reference(
    reference: &JobArtifactReferenceV1,
    maximum: usize,
) -> Result<(), DurableJobError> {
    validate_hash(&reference.content_hash, "/artifact/content_hash")?;
    if reference.byte_length == 0
        || usize::try_from(reference.byte_length).map_or(true, |size| size > maximum)
        || reference.media_type.is_empty()
        || reference.media_type.len() > 128
    {
        return Err(job_error(
            "job_artifact_reference_invalid",
            "/artifact",
            "job artifact size or media type is outside the bounded contract",
        ));
    }
    Ok(())
}

fn validate_hash(value: &str, path: &str) -> Result<(), DurableJobError> {
    if value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(job_error(
            "job_hash_invalid",
            path,
            "job identity must be lowercase sha256:<64 hex>",
        ))
    }
}

fn validate_job_id(value: &str) -> Result<(), DurableJobError> {
    if value.len() == 68
        && value.starts_with("job-")
        && value[4..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(job_error(
            "job_id_invalid",
            "/job_id",
            "job id does not satisfy the deterministic v1 format",
        ))
    }
}

fn validate_stable_id(value: &str, path: &str) -> Result<(), DurableJobError> {
    let valid = !value.is_empty()
        && value.len() <= 128
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':'));
    if valid {
        Ok(())
    } else {
        Err(job_error(
            "job_stable_id_invalid",
            path,
            "identifier must satisfy the bounded ASCII stable-id contract",
        ))
    }
}

fn validate_error_code(value: &str) -> Result<(), DurableJobError> {
    let valid = !value.is_empty()
        && value.len() <= 96
        && value.as_bytes()[0].is_ascii_lowercase()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_');
    if valid {
        Ok(())
    } else {
        Err(job_error(
            "job_error_code_invalid",
            "/error_code",
            "job error code must be lowercase snake_case",
        ))
    }
}

fn validate_completion_sizes(
    completion: DurableJobCompletionV1<'_>,
) -> Result<(), DurableJobError> {
    require_size(
        completion.checkpoint_bytes,
        MAX_CHECKPOINT_BYTES,
        "/checkpoint",
    )?;
    require_size(completion.result_ir_bytes, MAX_RESULT_BYTES, "/result_ir")?;
    require_size(completion.report_ir_bytes, MAX_REPORT_BYTES, "/report_ir")?;
    require_size(
        completion.report_document_bytes,
        MAX_DOCUMENT_BYTES,
        "/report_document",
    )
}

fn validate_model_ir_linear_completion_sizes(
    completion: ModelIrLinearDurableJobCompletionV1<'_>,
) -> Result<(), DurableJobError> {
    require_size(
        completion.checkpoint_bytes,
        MAX_CHECKPOINT_BYTES,
        "/checkpoint",
    )?;
    require_size(completion.result_ir_bytes, MAX_RESULT_BYTES, "/result_ir")?;
    require_size(
        completion.result_recovery_ir_bytes,
        MAX_RECOVERY_BYTES,
        "/result_recovery_ir",
    )?;
    require_size(
        completion.reaction_result_ir_bytes,
        MAX_REACTION_RESULT_BYTES,
        "/reaction_result_ir",
    )?;
    require_size(completion.report_ir_bytes, MAX_REPORT_BYTES, "/report_ir")?;
    require_size(
        completion.report_document_bytes,
        MAX_DOCUMENT_BYTES,
        "/report_document",
    )
}

fn is_atomic_temporary_name(name: &std::ffi::OsStr) -> bool {
    name.to_str()
        .is_some_and(|name| name.starts_with('.') && name.contains(".tmp."))
}

fn require_size(bytes: &[u8], maximum: usize, path: &str) -> Result<(), DurableJobError> {
    if bytes.is_empty() || bytes.len() > maximum {
        Err(job_error(
            "job_artifact_size_invalid",
            path,
            "job artifact is empty or exceeds its bounded size",
        ))
    } else {
        Ok(())
    }
}

fn write_atomic_new(path: &Path, bytes: &[u8]) -> Result<(), DurableJobError> {
    let parent = path.parent().ok_or_else(|| {
        job_error(
            "job_artifact_path_invalid",
            "/artifact",
            "job artifact path has no parent",
        )
    })?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| {
            job_error(
                "job_artifact_path_invalid",
                "/artifact",
                "job artifact path has no UTF-8 file name",
            )
        })?;
    let temporary = parent.join(format!(
        ".{name}.tmp.{}.{}",
        std::process::id(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    let result = (|| -> Result<(), DurableJobError> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .map_err(|error| io_error("job_artifact_create_failed", "/artifact", &error))?;
        file.write_all(bytes)
            .map_err(|error| io_error("job_artifact_write_failed", "/artifact", &error))?;
        file.sync_all()
            .map_err(|error| io_error("job_artifact_sync_failed", "/artifact", &error))?;
        drop(file);
        if path.exists() {
            return Err(job_error(
                "job_artifact_already_exists",
                "/artifact",
                "create-new durable artifact destination already exists",
            ));
        }
        fs::rename(&temporary, path)
            .map_err(|error| io_error("job_artifact_publish_failed", "/artifact", &error))?;
        sync_directory(parent, "/artifact")
    })();
    if result.is_err() {
        let _ignored = fs::remove_file(&temporary);
    }
    result
}

fn read_bounded_file(path: &Path, maximum: usize, field: &str) -> Result<Vec<u8>, DurableJobError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| io_error("job_artifact_metadata_failed", field, &error))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(job_error(
            "job_artifact_file_type_invalid",
            field,
            "durable artifact is not a regular non-symlink file",
        ));
    }
    let mut file =
        File::open(path).map_err(|error| io_error("job_artifact_open_failed", field, &error))?;
    let length = usize::try_from(
        file.metadata()
            .map_err(|error| io_error("job_artifact_metadata_failed", field, &error))?
            .len(),
    )
    .map_err(|_| {
        job_error(
            "job_artifact_size_invalid",
            field,
            "job artifact length exceeds address space",
        )
    })?;
    require_size_from_length(length, maximum, field)?;
    let mut bytes = Vec::new();
    bytes.try_reserve_exact(length).map_err(|_| {
        job_error(
            "job_artifact_allocation_failed",
            field,
            "job artifact allocation failed",
        )
    })?;
    file.read_to_end(&mut bytes)
        .map_err(|error| io_error("job_artifact_read_failed", field, &error))?;
    if bytes.len() != length {
        return Err(job_error(
            "job_artifact_size_changed",
            field,
            "job artifact size changed while reading",
        ));
    }
    Ok(bytes)
}

fn require_size_from_length(
    length: usize,
    maximum: usize,
    path: &str,
) -> Result<(), DurableJobError> {
    if length == 0 || length > maximum {
        Err(job_error(
            "job_artifact_size_invalid",
            path,
            "job artifact is empty or exceeds its bounded size",
        ))
    } else {
        Ok(())
    }
}

fn sync_directory(path: &Path, field: &str) -> Result<(), DurableJobError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| io_error("job_directory_sync_failed", field, &error))
}

fn ensure_real_directory(path: &Path, field: &str) -> Result<(), DurableJobError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => Ok(()),
        Ok(_) => Err(job_error(
            "job_store_path_type_invalid",
            field,
            "durable job store path is not a real directory",
        )),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => fs::create_dir(path)
            .map_err(|error| io_error("job_store_initialize_failed", field, &error)),
        Err(error) => Err(io_error("job_store_initialize_failed", field, &error)),
    }
}

fn reject_symlink_if_present(path: &Path, field: &str) -> Result<(), DurableJobError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => Err(job_error(
            "job_store_path_type_invalid",
            field,
            "durable job store file may not be a symbolic link",
        )),
        Ok(metadata) if !metadata.is_file() => Err(job_error(
            "job_store_path_type_invalid",
            field,
            "durable job store lock is not a regular file",
        )),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(io_error("job_store_initialize_failed", field, &error)),
    }
}

fn is_real_directory(path: &Path) -> Result<bool, DurableJobError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => Ok(metadata.is_dir() && !metadata.file_type().is_symlink()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(io_error("job_store_path_metadata_failed", "/jobs", &error)),
    }
}

fn constant_time_equal(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0_u8, |difference, (left, right)| {
            difference | (left ^ right)
        })
        == 0
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(char::from(DIGITS[usize::from(byte >> 4)]));
        output.push(char::from(DIGITS[usize::from(byte & 0x0f)]));
    }
    output
}

fn contract_source_error(
    code: &str,
    error: &structural_contracts::product_ir::ProductIrContractError,
) -> DurableJobError {
    job_error(code, &error.path, &error.to_string())
}

fn runtime_source_error(error: &crate::RuntimeError) -> DurableJobError {
    job_error(
        "job_native_runtime_failed",
        "/runtime",
        &format!("native runtime error {}: {}", error.code, error.message),
    )
}

fn job_error(code: &str, path: &str, detail: &str) -> DurableJobError {
    DurableJobError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}

fn io_error(code: &str, path: &str, error: &std::io::Error) -> DurableJobError {
    job_error(
        code,
        path,
        &format!("durable job filesystem operation failed: {error}"),
    )
}

/// Current Unix time in milliseconds for durable job transition callers.
///
/// # Errors
///
/// Returns a stable error if the system clock precedes the Unix epoch or exceeds `u64`.
pub fn unix_time_millis() -> Result<u64, DurableJobError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| {
        job_error(
            "job_system_clock_invalid",
            "/now_unix_ms",
            "system clock precedes the Unix epoch",
        )
    })?;
    u64::try_from(elapsed.as_millis()).map_err(|_| {
        job_error(
            "job_system_clock_invalid",
            "/now_unix_ms",
            "system clock milliseconds exceed u64",
        )
    })
}
