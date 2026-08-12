use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::{
    parse_native_analysis_request_v1, parse_nonlinear_ndtha_report_ir_v1,
    parse_nonlinear_ndtha_result_ir_v1, sha256_identity,
};
use structural_report::build_nonlinear_ndtha_report_v1;

use crate::{NonlinearNdthaCheckpoint, NonlinearNdthaExecutionStatus, Runtime};

const JOB_SCHEMA: &str = "structural-native-durable-job-event.v1";
const JOB_PROFILE: &str = "append_only_hash_chain_single_host.v1";
const CLAIM_BOUNDARY: &str = "single_host_local_job_orchestration_not_distributed_consensus_identity_authorization_or_release_authority";
const MAX_REQUEST_BYTES: usize = 16 * 1024 * 1024;
const MAX_CHECKPOINT_BYTES: usize = 256 * 1024 * 1024;
const MAX_RESULT_BYTES: usize = 64 * 1024 * 1024;
const MAX_REPORT_BYTES: usize = 16 * 1024 * 1024;
const MAX_DOCUMENT_BYTES: usize = 16 * 1024 * 1024;
const MAX_EVENT_BYTES: usize = 1024 * 1024;
const MIN_LEASE_MILLIS: u64 = 1_000;
const MAX_LEASE_MILLIS: u64 = 3_600_000;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

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
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum JobArtifactRoleV1 {
    Request,
    Checkpoint,
    ResultIr,
    ReportIr,
    ReportDocument,
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

struct CompletionReferencesV1 {
    checkpoint: JobArtifactReferenceV1,
    result_ir: JobArtifactReferenceV1,
    report_ir: JobArtifactReferenceV1,
    report_document: JobArtifactReferenceV1,
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
        require_size(request_bytes, MAX_REQUEST_BYTES, "/request")?;
        let request = parse_native_analysis_request_v1(request_bytes)
            .map_err(|error| contract_source_error("job_request_invalid", &error))?;
        let _lock = self.lock()?;
        let job_id = job_id(idempotency_key);
        let job_path = self.jobs_directory.join(&job_id);
        if job_path.exists() {
            let latest = self.load_latest_locked(&job_id)?;
            if latest.idempotency_key != idempotency_key
                || latest.request.content_hash != request.request_hash()
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
            MAX_REQUEST_BYTES,
        )?;
        let event = seal_event(JobEventV1 {
            schema_version: JOB_SCHEMA.to_owned(),
            service_profile: JOB_PROFILE.to_owned(),
            claim_boundary: CLAIM_BOUNDARY.to_owned(),
            job_id: job_id.clone(),
            idempotency_key: idempotency_key.to_owned(),
            request: request_reference,
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
            let request_bytes = self.read_blob_locked(&current.request, MAX_REQUEST_BYTES)?;
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
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        let request_bytes = self.read_blob_locked(&current.request, MAX_REQUEST_BYTES)?;
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
        require_lease(&current, worker_id, lease_token, now_unix_ms)?;
        if current.cancel_requested {
            return Err(job_error(
                "job_cancel_pending",
                "/status",
                "cancel-requested job cannot publish successful completion",
            ));
        }
        let request_bytes = self.read_blob_locked(&current.request, MAX_REQUEST_BYTES)?;
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
                || next.report_document != previous.report_document))
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
    validate_artifact_reference(&event.request, MAX_REQUEST_BYTES)?;
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
    let succeeded = event.status == DurableJobStatusV1::Succeeded;
    if succeeded
        != (event.result_ir.is_some()
            && event.report_ir.is_some()
            && event.report_document.is_some()
            && event.progress_completed == event.progress_total)
    {
        return Err(job_error(
            "job_event_terminal_artifacts_invalid",
            "/status",
            "only succeeded jobs may expose a complete terminal artifact set",
        ));
    }
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

fn view(event: &JobEventV1) -> DurableJobViewV1 {
    DurableJobViewV1 {
        job_id: event.job_id.clone(),
        request: event.request.clone(),
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
        error_code: event.error_code.clone(),
        created_unix_ms: event.created_unix_ms,
        updated_unix_ms: event.updated_unix_ms,
        can_resume: event.checkpoint.is_some() && event.status == DurableJobStatusV1::Checkpointed,
        terminal_event_hash: event.event_hash.clone(),
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
