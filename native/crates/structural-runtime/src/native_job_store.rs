//! Append-only single-host job storage for the bounded native `Frame3D` runtime.

use std::fmt;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use structural_contracts::model_ir::{decode_json_strict, parse_model_ir_v2};
use structural_contracts::native_job::{
    create_native_frame3d_job_event_v2, create_native_frame3d_job_request_v1,
    create_native_frame3d_job_view_v2, parse_native_frame3d_job_event_v1,
    parse_native_frame3d_job_event_v2, parse_native_frame3d_job_request_v1,
    parse_native_frame3d_job_view_v1, parse_native_frame3d_job_view_v2, NativeFrame3dJobArtifactV1,
    NativeFrame3dJobCancellationV2, NativeFrame3dJobEventTypeV2, NativeFrame3dJobFailureV1,
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobRequestV1, NativeFrame3dJobStatusV1,
    NativeFrame3dJobStatusV2, NativeFrame3dJobViewV1, NativeFrame3dJobViewV2,
};
use structural_contracts::report_ir::sha256_bytes_identity;
use structural_contracts::{FRAME3D_JOB_VIEW_SCHEMA_V1, FRAME3D_JOB_VIEW_SCHEMA_V2};
use structural_report::{build_linear_frame3d_report, publish_linear_frame3d_workbench_bundle};

use crate::{LinearFrame3dLoadSelection, Runtime};

const MAX_CONTRACT_BYTES: u64 = 2 * 1024 * 1024;

/// Stable filesystem job runner failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeFrame3dJobStoreError {
    pub code: String,
    pub detail: String,
}

impl fmt::Display for NativeFrame3dJobStoreError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for NativeFrame3dJobStoreError {}

/// Strictly replayed persisted view, preserving the immutable v1 wire contract alongside v2.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NativeFrame3dJobViewRecord {
    V1(NativeFrame3dJobViewV1),
    V2(NativeFrame3dJobViewV2),
}

impl NativeFrame3dJobViewRecord {
    #[must_use]
    pub fn status(&self) -> NativeFrame3dJobStatusV2 {
        match self {
            Self::V1(view) => match view.status {
                NativeFrame3dJobStatusV1::Queued => NativeFrame3dJobStatusV2::Queued,
                NativeFrame3dJobStatusV1::Running => NativeFrame3dJobStatusV2::Running,
                NativeFrame3dJobStatusV1::Succeeded => NativeFrame3dJobStatusV2::Succeeded,
                NativeFrame3dJobStatusV1::Failed => NativeFrame3dJobStatusV2::Failed,
            },
            Self::V2(view) => view.status,
        }
    }

    #[must_use]
    pub fn revision(&self) -> u32 {
        match self {
            Self::V1(view) => view.revision,
            Self::V2(view) => view.revision,
        }
    }

    #[must_use]
    pub fn updated_unix_ms(&self) -> u64 {
        match self {
            Self::V1(view) => view.updated_unix_ms,
            Self::V2(view) => view.updated_unix_ms,
        }
    }

    #[must_use]
    pub fn job_id(&self) -> &str {
        match self {
            Self::V1(view) => &view.job_id,
            Self::V2(view) => &view.job_id,
        }
    }

    #[must_use]
    pub fn bundle_manifest(&self) -> Option<&NativeFrame3dJobArtifactV1> {
        match self {
            Self::V1(view) => view.bundle_manifest.as_ref(),
            Self::V2(view) => view.bundle_manifest.as_ref(),
        }
    }

    #[must_use]
    pub fn error(&self) -> Option<&NativeFrame3dJobFailureV1> {
        match self {
            Self::V1(view) => view.error.as_ref(),
            Self::V2(view) => view.error.as_ref(),
        }
    }

    #[must_use]
    pub fn cancellation(&self) -> Option<&NativeFrame3dJobCancellationV2> {
        match self {
            Self::V1(_) => None,
            Self::V2(view) => view.cancellation.as_ref(),
        }
    }

    /// Preserve the exact versioned wire representation.
    ///
    /// # Errors
    ///
    /// Returns a stable serialization error if the replayed view cannot be rendered.
    pub fn canonical_json(
        &self,
    ) -> Result<String, structural_contracts::native_job::NativeFrame3dJobError> {
        match self {
            Self::V1(view) => view.canonical_json(),
            Self::V2(view) => view.canonical_json(),
        }
    }
}

/// Explicit root for a no-overwrite, one-attempt-per-job single-host store.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeFrame3dJobStore {
    root: PathBuf,
}

impl NativeFrame3dJobStore {
    #[must_use]
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    #[must_use]
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Submit canonical `ModelIR` and an immutable request, publishing the queued view last.
    ///
    /// # Errors
    ///
    /// Rejects invalid model/request identities, an existing job, or any incomplete filesystem
    /// write. Partial directories remain fail-closed and are not recovered automatically.
    pub fn submit(
        &self,
        job_id: &str,
        model_bytes: &[u8],
        load_source: NativeFrame3dJobLoadSourceV1,
        result_id: &str,
        report_id: &str,
    ) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
        let model = parse_model_ir_v2(model_bytes).map_err(|_| {
            store_error(
                "native_job_model_invalid",
                "Submitted ModelIR failed strict wire validation",
            )
        })?;
        let submitted = unix_ms()?;
        let request = create_native_frame3d_job_request_v1(
            job_id,
            submitted,
            model.content_hash(),
            load_source,
            result_id,
            report_id,
        )
        .map_err(contract_error)?;
        let event = create_native_frame3d_job_event_v2(
            &request,
            0,
            submitted,
            NativeFrame3dJobEventTypeV2::Submitted,
            NativeFrame3dJobStatusV2::Queued,
            None,
            None,
            None,
            None,
        )
        .map_err(contract_error)?;
        let view = create_native_frame3d_job_view_v2(&request, &event, None, None, None)
            .map_err(contract_error)?;

        std::fs::create_dir_all(&self.root).map_err(|_| {
            store_error(
                "native_job_store_create_failed",
                "Native job store root could not be created",
            )
        })?;
        let job_dir = self.job_dir(job_id)?;
        std::fs::create_dir(&job_dir).map_err(|item| {
            if item.kind() == std::io::ErrorKind::AlreadyExists {
                store_error(
                    "native_job_already_exists",
                    "Native job identity already exists; overwrite is forbidden",
                )
            } else {
                store_error(
                    "native_job_create_failed",
                    "Native job directory could not be created",
                )
            }
        })?;
        std::fs::create_dir(job_dir.join("events")).map_err(|_| {
            store_error(
                "native_job_events_create_failed",
                "Native job event directory could not be created",
            )
        })?;
        write_new(&job_dir.join("model-ir.json"), model.canonical_bytes())?;
        write_new(
            &job_dir.join("request.json"),
            request.canonical_json().map_err(contract_error)?.as_bytes(),
        )?;
        write_new(
            &job_dir.join("events/00000000.json"),
            event.canonical_json().map_err(contract_error)?.as_bytes(),
        )?;
        write_new(
            &job_dir.join("view.json"),
            view.canonical_json().map_err(contract_error)?.as_bytes(),
        )?;
        Ok(NativeFrame3dJobViewRecord::V2(view))
    }

    /// Execute one queued job exactly once and persist either succeeded or failed terminal state.
    ///
    /// A returned failed view means execution failed as recorded; a returned error means the
    /// store itself could not establish or persist a trustworthy transition.
    ///
    /// # Errors
    ///
    /// Rejects corrupt lifecycle state, an already-started job, a stale model binding, or a
    /// filesystem transition failure. No stale-lock recovery is attempted.
    pub fn run(
        &self,
        job_id: &str,
    ) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        let queued = self.inspect(job_id)?;
        if queued.status() != NativeFrame3dJobStatusV2::Queued || queued.revision() != 0 {
            return Err(store_error(
                "native_job_not_queued",
                "Only a pristine queued native job can be run",
            ));
        }
        let model_bytes = read_bounded(&job_dir.join("model-ir.json"))?;
        let model = parse_model_ir_v2(&model_bytes).map_err(|_| {
            store_error(
                "native_job_model_corrupt",
                "Stored ModelIR failed strict wire validation",
            )
        })?;
        if model.content_hash() != request.model_content_hash {
            return Err(store_error(
                "native_job_model_binding_mismatch",
                "Stored ModelIR does not match the immutable request",
            ));
        }
        if !matches!(&queued, NativeFrame3dJobViewRecord::V2(_)) {
            return Err(store_error(
                "native_job_v1_execution_unsupported",
                "Legacy v1 jobs remain replayable but cannot be mutated by the v2 runtime",
            ));
        }
        write_new(&job_dir.join("run.lock"), request.request_hash.as_bytes()).map_err(|_| {
            store_error(
                "native_job_run_locked",
                "Native job has already been claimed or has a stale run lock; recovery is unsupported",
            )
        })?;

        let submitted = load_event_v2(&job_dir, 0)?;
        let started_time = unix_ms()?.max(request.submitted_unix_ms);
        let started = create_native_frame3d_job_event_v2(
            &request,
            1,
            started_time,
            NativeFrame3dJobEventTypeV2::Started,
            NativeFrame3dJobStatusV2::Running,
            Some(submitted.event_hash),
            None,
            None,
            None,
        )
        .map_err(contract_error)?;
        let running_view = create_native_frame3d_job_view_v2(&request, &started, None, None, None)
            .map_err(contract_error)?;
        append_event_v2(&job_dir, &started)?;
        replace_view_v2(&job_dir, &running_view)?;

        let outcome = execute(&job_dir, &request, &model_bytes);
        let terminal_time = unix_ms()?.max(started_time);
        persist_execution_outcome(&job_dir, &request, &started, outcome, terminal_time)
    }

    /// Append a terminal failed transition after an isolated worker stopped while running.
    ///
    /// This is failure finalization, not retry, resume, stale-lock recovery, or proof of why the
    /// worker stopped. A queued, terminal, corrupt, or partially persisted job remains untouched.
    ///
    /// # Errors
    ///
    /// Rejects any job that is not a strictly replayable revision-one running view, or any failure
    /// to append the terminal event and atomically replace the materialized view.
    pub fn finalize_running_failure(
        &self,
        job_id: &str,
        error_code: &str,
        detail: &str,
    ) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        let running = self.inspect(job_id)?;
        if running.status() != NativeFrame3dJobStatusV2::Running || running.revision() != 1 {
            return Err(store_error(
                "native_job_not_running",
                "Only a strictly replayable running native job can be finalized as failed",
            ));
        }
        if !matches!(&running, NativeFrame3dJobViewRecord::V2(_)) {
            return Err(store_error(
                "native_job_v1_failure_finalization_unsupported",
                "Legacy v1 jobs remain replayable but cannot be mutated by the v2 runtime",
            ));
        }
        let started = load_event_v2(&job_dir, 1)?;
        let failure = failure(error_code, detail);
        let terminal = create_native_frame3d_job_event_v2(
            &request,
            2,
            unix_ms()?.max(running.updated_unix_ms()),
            NativeFrame3dJobEventTypeV2::Failed,
            NativeFrame3dJobStatusV2::Failed,
            Some(started.event_hash),
            None,
            Some(failure.code.clone()),
            None,
        )
        .map_err(contract_error)?;
        let view =
            create_native_frame3d_job_view_v2(&request, &terminal, None, Some(failure), None)
                .map_err(contract_error)?;
        append_event_v2(&job_dir, &terminal)?;
        replace_view_v2(&job_dir, &view)?;
        Ok(NativeFrame3dJobViewRecord::V2(view))
    }

    /// Append a distinct cancelled transition after the host has stopped and reaped the worker.
    ///
    /// The store records cancellation evidence but does not own or prove process termination. Only
    /// a strictly replayable v2 queued or running job is accepted; v1 and terminal jobs are left
    /// untouched.
    ///
    /// # Errors
    ///
    /// Rejects legacy v1, terminal, corrupt or partial jobs and any failed append/view replacement.
    pub fn finalize_cancellation(
        &self,
        job_id: &str,
        cancellation_code: &str,
        detail: &str,
    ) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        let current = self.inspect(job_id)?;
        let current_revision = current.revision();
        if !matches!(&current, NativeFrame3dJobViewRecord::V2(_)) {
            return Err(store_error(
                "native_job_v1_cancellation_unsupported",
                "Legacy v1 jobs are replayable but do not support cancellation",
            ));
        }
        if !matches!(
            (current.status(), current_revision),
            (NativeFrame3dJobStatusV2::Queued, 0) | (NativeFrame3dJobStatusV2::Running, 1)
        ) {
            return Err(store_error(
                "native_job_not_cancellable",
                "Only a strictly replayable queued or running v2 job can be cancelled",
            ));
        }
        let previous = load_event_v2(&job_dir, current_revision)?;
        let cancellation = cancellation(cancellation_code, detail);
        let terminal = create_native_frame3d_job_event_v2(
            &request,
            current_revision + 1,
            unix_ms()?.max(current.updated_unix_ms()),
            NativeFrame3dJobEventTypeV2::Cancelled,
            NativeFrame3dJobStatusV2::Cancelled,
            Some(previous.event_hash),
            None,
            None,
            Some(cancellation.code.clone()),
        )
        .map_err(contract_error)?;
        let view =
            create_native_frame3d_job_view_v2(&request, &terminal, None, None, Some(cancellation))
                .map_err(contract_error)?;
        append_event_v2(&job_dir, &terminal)?;
        replace_view_v2(&job_dir, &view)?;
        Ok(NativeFrame3dJobViewRecord::V2(view))
    }

    /// Validate the immutable request, full event hash chain, materialized view and terminal
    /// manifest reference before returning a job view.
    ///
    /// # Errors
    ///
    /// Rejects missing, oversized, malformed, transplanted or stale lifecycle evidence.
    pub fn inspect(
        &self,
        job_id: &str,
    ) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        if request.job_id != job_id {
            return Err(store_error(
                "native_job_identity_mismatch",
                "Stored request job identity does not match the inspected directory",
            ));
        }
        let model =
            parse_model_ir_v2(&read_bounded(&job_dir.join("model-ir.json"))?).map_err(|_| {
                store_error(
                    "native_job_model_corrupt",
                    "Stored ModelIR failed strict wire validation",
                )
            })?;
        if model.content_hash() != request.model_content_hash {
            return Err(store_error(
                "native_job_model_binding_mismatch",
                "Stored ModelIR does not match the immutable request",
            ));
        }
        let view_bytes = read_bounded(&job_dir.join("view.json"))?;
        let decoded =
            decode_json_strict(&view_bytes).map_err(|source| NativeFrame3dJobStoreError {
                code: "native_job_view_json_invalid".to_owned(),
                detail: format!("Strict job view JSON is invalid at {}", source.path),
            })?;
        match decoded
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
        {
            Some(FRAME3D_JOB_VIEW_SCHEMA_V2) => {
                let view = parse_native_frame3d_job_view_v2(&view_bytes).map_err(contract_error)?;
                inspect_v2(&job_dir, &request, view)
            }
            Some(FRAME3D_JOB_VIEW_SCHEMA_V1) => {
                let view = parse_native_frame3d_job_view_v1(&view_bytes).map_err(contract_error)?;
                inspect_v1(&job_dir, &request, view)
            }
            _ => Err(store_error(
                "native_job_view_schema_unsupported",
                "Native job view schema version is missing or unsupported",
            )),
        }
    }

    fn job_dir(&self, job_id: &str) -> Result<PathBuf, NativeFrame3dJobStoreError> {
        if !valid_job_id(job_id) {
            return Err(store_error(
                "native_job_id_invalid",
                "Native job identity must match job_ followed by 32 lowercase hexadecimal digits",
            ));
        }
        Ok(self.root.join(job_id))
    }
}

fn persist_execution_outcome(
    job_dir: &Path,
    request: &NativeFrame3dJobRequestV1,
    started: &structural_contracts::native_job::NativeFrame3dJobEventV2,
    outcome: Result<NativeFrame3dJobArtifactV1, NativeFrame3dJobFailureV1>,
    terminal_time: u64,
) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
    let (terminal, artifact, failure) = match outcome {
        Ok(artifact) => (
            create_native_frame3d_job_event_v2(
                request,
                2,
                terminal_time,
                NativeFrame3dJobEventTypeV2::Completed,
                NativeFrame3dJobStatusV2::Succeeded,
                Some(started.event_hash.clone()),
                Some(artifact.content_hash.clone()),
                None,
                None,
            )
            .map_err(contract_error)?,
            Some(artifact),
            None,
        ),
        Err(failure) => (
            create_native_frame3d_job_event_v2(
                request,
                2,
                terminal_time,
                NativeFrame3dJobEventTypeV2::Failed,
                NativeFrame3dJobStatusV2::Failed,
                Some(started.event_hash.clone()),
                None,
                Some(failure.code.clone()),
                None,
            )
            .map_err(contract_error)?,
            None,
            Some(failure),
        ),
    };
    let view = create_native_frame3d_job_view_v2(request, &terminal, artifact, failure, None)
        .map_err(contract_error)?;
    append_event_v2(job_dir, &terminal)?;
    replace_view_v2(job_dir, &view)?;
    Ok(NativeFrame3dJobViewRecord::V2(view))
}

fn inspect_v1(
    job_dir: &Path,
    request: &NativeFrame3dJobRequestV1,
    view: NativeFrame3dJobViewV1,
) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
    validate_view_binding(
        request,
        &view.job_id,
        &view.request_hash,
        &view.model_content_hash,
    )?;
    validate_event_file_set(job_dir, view.revision)?;
    let mut previous = None;
    let mut latest = None;
    for revision in 0..=view.revision {
        let event = load_event_v1(job_dir, revision)?;
        validate_event_binding(
            request,
            &event.job_id,
            &event.request_hash,
            event.previous_event_hash.as_ref(),
            previous.as_ref(),
        )?;
        previous = Some(event.event_hash.clone());
        latest = Some(event);
    }
    let latest = latest.ok_or_else(missing_event)?;
    if latest.revision != view.revision || latest.status != view.status {
        return Err(stale_view());
    }
    if latest.error_code.as_deref() != view.error.as_ref().map(|failure| failure.code.as_str()) {
        return Err(store_error(
            "native_job_failure_binding_mismatch",
            "Materialized job failure does not match the terminal lifecycle event",
        ));
    }
    validate_bundle_manifest(
        job_dir,
        view.bundle_manifest.as_ref(),
        latest.bundle_manifest_hash.as_ref(),
    )?;
    Ok(NativeFrame3dJobViewRecord::V1(view))
}

fn inspect_v2(
    job_dir: &Path,
    request: &NativeFrame3dJobRequestV1,
    view: NativeFrame3dJobViewV2,
) -> Result<NativeFrame3dJobViewRecord, NativeFrame3dJobStoreError> {
    validate_view_binding(
        request,
        &view.job_id,
        &view.request_hash,
        &view.model_content_hash,
    )?;
    validate_event_file_set(job_dir, view.revision)?;
    let mut previous = None;
    let mut latest = None;
    let mut revision_one_started = false;
    for revision in 0..=view.revision {
        let event = load_event_v2(job_dir, revision)?;
        validate_event_binding(
            request,
            &event.job_id,
            &event.request_hash,
            event.previous_event_hash.as_ref(),
            previous.as_ref(),
        )?;
        let expected_type = match revision {
            0 => event.event_type == NativeFrame3dJobEventTypeV2::Submitted,
            1 => matches!(
                event.event_type,
                NativeFrame3dJobEventTypeV2::Started | NativeFrame3dJobEventTypeV2::Cancelled
            ),
            2 => {
                revision_one_started
                    && matches!(
                        event.event_type,
                        NativeFrame3dJobEventTypeV2::Completed
                            | NativeFrame3dJobEventTypeV2::Failed
                            | NativeFrame3dJobEventTypeV2::Cancelled
                    )
            }
            _ => false,
        };
        if !expected_type {
            return Err(store_error(
                "native_job_event_sequence_invalid",
                "Native job v2 event sequence is not submitted, optional started, then terminal",
            ));
        }
        revision_one_started =
            revision == 1 && event.event_type == NativeFrame3dJobEventTypeV2::Started;
        previous = Some(event.event_hash.clone());
        latest = Some(event);
    }
    let latest = latest.ok_or_else(missing_event)?;
    if latest.revision != view.revision || latest.status != view.status {
        return Err(stale_view());
    }
    if latest.error_code.as_deref() != view.error.as_ref().map(|failure| failure.code.as_str()) {
        return Err(store_error(
            "native_job_failure_binding_mismatch",
            "Materialized job failure does not match the terminal lifecycle event",
        ));
    }
    if latest.cancellation_code.as_deref()
        != view
            .cancellation
            .as_ref()
            .map(|cancellation| cancellation.code.as_str())
    {
        return Err(store_error(
            "native_job_cancellation_binding_mismatch",
            "Materialized job cancellation does not match the terminal lifecycle event",
        ));
    }
    validate_bundle_manifest(
        job_dir,
        view.bundle_manifest.as_ref(),
        latest.bundle_manifest_hash.as_ref(),
    )?;
    Ok(NativeFrame3dJobViewRecord::V2(view))
}

fn validate_view_binding(
    request: &NativeFrame3dJobRequestV1,
    job_id: &str,
    request_hash: &str,
    model_content_hash: &str,
) -> Result<(), NativeFrame3dJobStoreError> {
    if job_id != request.job_id
        || request_hash != request.request_hash
        || model_content_hash != request.model_content_hash
    {
        return Err(store_error(
            "native_job_view_binding_mismatch",
            "Materialized job view does not match the immutable request",
        ));
    }
    Ok(())
}

fn validate_event_binding(
    request: &NativeFrame3dJobRequestV1,
    job_id: &str,
    request_hash: &str,
    previous_event_hash: Option<&String>,
    expected_previous: Option<&String>,
) -> Result<(), NativeFrame3dJobStoreError> {
    if job_id != request.job_id
        || request_hash != request.request_hash
        || previous_event_hash != expected_previous
    {
        return Err(store_error(
            "native_job_event_chain_invalid",
            "Native job event hash chain or request binding is invalid",
        ));
    }
    Ok(())
}

fn validate_bundle_manifest(
    job_dir: &Path,
    artifact: Option<&NativeFrame3dJobArtifactV1>,
    event_hash: Option<&String>,
) -> Result<(), NativeFrame3dJobStoreError> {
    if let Some(artifact) = artifact {
        let bytes = read_bounded(&job_dir.join(&artifact.path))?;
        if bytes.len() as u64 != artifact.byte_length
            || sha256_bytes_identity(&bytes) != artifact.content_hash
            || event_hash != Some(&artifact.content_hash)
        {
            return Err(store_error(
                "native_job_bundle_manifest_invalid",
                "Succeeded job manifest reference is missing, stale or hash-mismatched",
            ));
        }
    }
    Ok(())
}

fn missing_event() -> NativeFrame3dJobStoreError {
    store_error(
        "native_job_event_missing",
        "Native job has no submitted lifecycle event",
    )
}

fn stale_view() -> NativeFrame3dJobStoreError {
    store_error(
        "native_job_view_stale",
        "Materialized job view does not match the latest lifecycle event",
    )
}

fn validate_event_file_set(
    job_dir: &Path,
    latest_revision: u32,
) -> Result<(), NativeFrame3dJobStoreError> {
    let mut names = std::fs::read_dir(job_dir.join("events"))
        .map_err(|_| {
            store_error(
                "native_job_events_read_failed",
                "Native job event directory could not be read",
            )
        })?
        .map(|entry| {
            entry
                .map_err(|_| {
                    store_error(
                        "native_job_events_read_failed",
                        "Native job event directory could not be read completely",
                    )
                })?
                .file_name()
                .into_string()
                .map_err(|_| {
                    store_error(
                        "native_job_event_file_set_invalid",
                        "Native job event filename is not valid UTF-8",
                    )
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    names.sort();
    let expected = (0..=latest_revision)
        .map(|revision| format!("{revision:08}.json"))
        .collect::<Vec<_>>();
    if names != expected {
        return Err(store_error(
            "native_job_event_file_set_invalid",
            "Native job event files do not exactly match the materialized revision",
        ));
    }
    Ok(())
}

fn execute(
    job_dir: &Path,
    request: &NativeFrame3dJobRequestV1,
    model_bytes: &[u8],
) -> Result<NativeFrame3dJobArtifactV1, NativeFrame3dJobFailureV1> {
    let model = parse_model_ir_v2(model_bytes).map_err(|_| {
        failure(
            "native_job_model_invalid",
            "Stored ModelIR failed strict validation before execution",
        )
    })?;
    let runtime = Runtime::new().map_err(|_| {
        failure(
            "native_runtime_unavailable",
            "Native runtime could not be initialized",
        )
    })?;
    let selection = match &request.load_source {
        NativeFrame3dJobLoadSourceV1::Pattern { id } => LinearFrame3dLoadSelection::Pattern(id),
        NativeFrame3dJobLoadSourceV1::Combination { id } => {
            LinearFrame3dLoadSelection::Combination(id)
        }
    };
    let result = runtime
        .analyze_linear_frame3d_load_case_result_ir(&model, selection, &request.result_id)
        .map_err(|item| failure("native_analysis_failed", &item.message))?;
    let report = build_linear_frame3d_report(&result, &request.report_id)
        .map_err(|item| failure(&sanitize_code(&item.code), &item.detail))?;
    let manifest = publish_linear_frame3d_workbench_bundle(
        &job_dir.join("bundle"),
        model_bytes,
        &result,
        &report,
    )
    .map_err(|item| failure(&sanitize_code(&item.code), &item.detail))?;
    Ok(NativeFrame3dJobArtifactV1 {
        path: "bundle/manifest.json".to_owned(),
        content_hash: sha256_bytes_identity(manifest.as_bytes()),
        byte_length: manifest.len() as u64,
    })
}

fn load_request(job_dir: &Path) -> Result<NativeFrame3dJobRequestV1, NativeFrame3dJobStoreError> {
    parse_native_frame3d_job_request_v1(&read_bounded(&job_dir.join("request.json"))?)
        .map_err(contract_error)
}

fn load_event_v1(
    job_dir: &Path,
    revision: u32,
) -> Result<structural_contracts::native_job::NativeFrame3dJobEventV1, NativeFrame3dJobStoreError> {
    parse_native_frame3d_job_event_v1(&read_bounded(
        &job_dir.join(format!("events/{revision:08}.json")),
    )?)
    .map_err(contract_error)
}

fn load_event_v2(
    job_dir: &Path,
    revision: u32,
) -> Result<structural_contracts::native_job::NativeFrame3dJobEventV2, NativeFrame3dJobStoreError> {
    parse_native_frame3d_job_event_v2(&read_bounded(
        &job_dir.join(format!("events/{revision:08}.json")),
    )?)
    .map_err(contract_error)
}

fn append_event_v2(
    job_dir: &Path,
    event: &structural_contracts::native_job::NativeFrame3dJobEventV2,
) -> Result<(), NativeFrame3dJobStoreError> {
    write_new(
        &job_dir.join(format!("events/{:08}.json", event.revision)),
        event.canonical_json().map_err(contract_error)?.as_bytes(),
    )
}

fn replace_view_v2(
    job_dir: &Path,
    view: &NativeFrame3dJobViewV2,
) -> Result<(), NativeFrame3dJobStoreError> {
    let temporary = job_dir.join(format!(".view-{:08}.json", view.revision));
    write_new(
        &temporary,
        view.canonical_json().map_err(contract_error)?.as_bytes(),
    )?;
    std::fs::rename(&temporary, job_dir.join("view.json")).map_err(|_| {
        store_error(
            "native_job_view_replace_failed",
            "Materialized native job view could not be atomically replaced",
        )
    })
}

fn read_bounded(path: &Path) -> Result<Vec<u8>, NativeFrame3dJobStoreError> {
    let metadata = std::fs::metadata(path).map_err(|_| {
        store_error(
            "native_job_artifact_missing",
            "Required native job artifact is missing",
        )
    })?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_CONTRACT_BYTES {
        return Err(store_error(
            "native_job_artifact_size_invalid",
            "Native job artifact is empty, oversized, or not a regular file",
        ));
    }
    std::fs::read(path).map_err(|_| {
        store_error(
            "native_job_artifact_read_failed",
            "Native job artifact could not be read completely",
        )
    })
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), NativeFrame3dJobStoreError> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| {
            store_error(
                "native_job_artifact_create_failed",
                "Native job artifact could not be created without overwrite",
            )
        })?;
    file.write_all(bytes).map_err(|_| {
        store_error(
            "native_job_artifact_write_failed",
            "Native job artifact could not be written completely",
        )
    })?;
    file.sync_all().map_err(|_| {
        store_error(
            "native_job_artifact_sync_failed",
            "Native job artifact could not be synchronized",
        )
    })
}

fn unix_ms() -> Result<u64, NativeFrame3dJobStoreError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| {
        store_error(
            "native_job_clock_invalid",
            "System clock precedes the Unix epoch",
        )
    })?;
    u64::try_from(elapsed.as_millis()).map_err(|_| {
        store_error(
            "native_job_clock_invalid",
            "System clock exceeds the native job timestamp domain",
        )
    })
}

fn valid_job_id(value: &str) -> bool {
    value.len() == 36
        && value.starts_with("job_")
        && value[4..]
            .bytes()
            .all(|item| item.is_ascii_digit() || (b'a'..=b'f').contains(&item))
}

fn sanitize_code(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|item| {
            if item.is_ascii_lowercase() || item.is_ascii_digit() || item == '_' {
                item
            } else {
                '_'
            }
        })
        .take(96)
        .collect::<String>();
    if sanitized.starts_with(|item: char| item.is_ascii_lowercase()) {
        sanitized
    } else {
        "native_job_execution_failed".to_owned()
    }
}

fn failure(code: &str, detail: &str) -> NativeFrame3dJobFailureV1 {
    NativeFrame3dJobFailureV1 {
        code: sanitize_code(code),
        detail: detail.chars().take(512).collect(),
    }
}

fn cancellation(code: &str, detail: &str) -> NativeFrame3dJobCancellationV2 {
    NativeFrame3dJobCancellationV2 {
        code: sanitize_code(code),
        detail: detail.chars().take(512).collect(),
    }
}

fn contract_error(
    source: structural_contracts::native_job::NativeFrame3dJobError,
) -> NativeFrame3dJobStoreError {
    NativeFrame3dJobStoreError {
        code: source.code,
        detail: source.detail,
    }
}

fn store_error(code: &str, detail: &str) -> NativeFrame3dJobStoreError {
    NativeFrame3dJobStoreError {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}
