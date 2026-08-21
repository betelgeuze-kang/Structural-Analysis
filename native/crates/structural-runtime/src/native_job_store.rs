//! Append-only single-host job storage for the bounded native `Frame3D` runtime.

use std::fmt;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::native_job::{
    create_native_frame3d_job_event_v1, create_native_frame3d_job_request_v1,
    create_native_frame3d_job_view_v1, parse_native_frame3d_job_event_v1,
    parse_native_frame3d_job_request_v1, parse_native_frame3d_job_view_v1,
    NativeFrame3dJobArtifactV1, NativeFrame3dJobEventTypeV1, NativeFrame3dJobFailureV1,
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobRequestV1, NativeFrame3dJobStatusV1,
    NativeFrame3dJobViewV1,
};
use structural_contracts::report_ir::sha256_bytes_identity;
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
    ) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobStoreError> {
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
        let event = create_native_frame3d_job_event_v1(
            &request,
            0,
            submitted,
            NativeFrame3dJobEventTypeV1::Submitted,
            NativeFrame3dJobStatusV1::Queued,
            None,
            None,
            None,
        )
        .map_err(contract_error)?;
        let view = create_native_frame3d_job_view_v1(&request, &event, None, None)
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
        Ok(view)
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
    pub fn run(&self, job_id: &str) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        let queued = self.inspect(job_id)?;
        if queued.status != NativeFrame3dJobStatusV1::Queued || queued.revision != 0 {
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
        write_new(&job_dir.join("run.lock"), request.request_hash.as_bytes()).map_err(|_| {
            store_error(
                "native_job_run_locked",
                "Native job has already been claimed or has a stale run lock; recovery is unsupported",
            )
        })?;

        let submitted = load_event(&job_dir, 0)?;
        let started_time = unix_ms()?.max(request.submitted_unix_ms);
        let started = create_native_frame3d_job_event_v1(
            &request,
            1,
            started_time,
            NativeFrame3dJobEventTypeV1::Started,
            NativeFrame3dJobStatusV1::Running,
            Some(submitted.event_hash),
            None,
            None,
        )
        .map_err(contract_error)?;
        append_event(&job_dir, &started)?;
        replace_view(
            &job_dir,
            &create_native_frame3d_job_view_v1(&request, &started, None, None)
                .map_err(contract_error)?,
        )?;

        let outcome = execute(&job_dir, &request, &model_bytes);
        let terminal_time = unix_ms()?.max(started_time);
        match outcome {
            Ok(artifact) => {
                let terminal = create_native_frame3d_job_event_v1(
                    &request,
                    2,
                    terminal_time,
                    NativeFrame3dJobEventTypeV1::Completed,
                    NativeFrame3dJobStatusV1::Succeeded,
                    Some(started.event_hash),
                    Some(artifact.content_hash.clone()),
                    None,
                )
                .map_err(contract_error)?;
                append_event(&job_dir, &terminal)?;
                let view =
                    create_native_frame3d_job_view_v1(&request, &terminal, Some(artifact), None)
                        .map_err(contract_error)?;
                replace_view(&job_dir, &view)?;
                Ok(view)
            }
            Err(failure) => {
                let terminal = create_native_frame3d_job_event_v1(
                    &request,
                    2,
                    terminal_time,
                    NativeFrame3dJobEventTypeV1::Failed,
                    NativeFrame3dJobStatusV1::Failed,
                    Some(started.event_hash),
                    None,
                    Some(failure.code.clone()),
                )
                .map_err(contract_error)?;
                append_event(&job_dir, &terminal)?;
                let view =
                    create_native_frame3d_job_view_v1(&request, &terminal, None, Some(failure))
                        .map_err(contract_error)?;
                replace_view(&job_dir, &view)?;
                Ok(view)
            }
        }
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
    ) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        let running = self.inspect(job_id)?;
        if running.status != NativeFrame3dJobStatusV1::Running || running.revision != 1 {
            return Err(store_error(
                "native_job_not_running",
                "Only a strictly replayable running native job can be finalized as failed",
            ));
        }
        let started = load_event(&job_dir, 1)?;
        let failure = failure(error_code, detail);
        let terminal = create_native_frame3d_job_event_v1(
            &request,
            2,
            unix_ms()?.max(running.updated_unix_ms),
            NativeFrame3dJobEventTypeV1::Failed,
            NativeFrame3dJobStatusV1::Failed,
            Some(started.event_hash),
            None,
            Some(failure.code.clone()),
        )
        .map_err(contract_error)?;
        append_event(&job_dir, &terminal)?;
        let view = create_native_frame3d_job_view_v1(&request, &terminal, None, Some(failure))
            .map_err(contract_error)?;
        replace_view(&job_dir, &view)?;
        Ok(view)
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
    ) -> Result<NativeFrame3dJobViewV1, NativeFrame3dJobStoreError> {
        let job_dir = self.job_dir(job_id)?;
        let request = load_request(&job_dir)?;
        if request.job_id != job_id {
            return Err(store_error(
                "native_job_identity_mismatch",
                "Stored request job identity does not match the inspected directory",
            ));
        }
        let view = parse_native_frame3d_job_view_v1(&read_bounded(&job_dir.join("view.json"))?)
            .map_err(contract_error)?;
        if view.job_id != request.job_id
            || view.request_hash != request.request_hash
            || view.model_content_hash != request.model_content_hash
        {
            return Err(store_error(
                "native_job_view_binding_mismatch",
                "Materialized job view does not match the immutable request",
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
        validate_event_file_set(&job_dir, view.revision)?;
        let mut previous = None;
        let mut latest = None;
        for revision in 0..=view.revision {
            let event = load_event(&job_dir, revision)?;
            if event.job_id != request.job_id
                || event.request_hash != request.request_hash
                || event.previous_event_hash != previous
            {
                return Err(store_error(
                    "native_job_event_chain_invalid",
                    "Native job event hash chain or request binding is invalid",
                ));
            }
            previous = Some(event.event_hash.clone());
            latest = Some(event);
        }
        let latest = latest.ok_or_else(|| {
            store_error(
                "native_job_event_missing",
                "Native job has no submitted lifecycle event",
            )
        })?;
        if latest.revision != view.revision || latest.status != view.status {
            return Err(store_error(
                "native_job_view_stale",
                "Materialized job view does not match the latest lifecycle event",
            ));
        }
        if latest.error_code.as_deref() != view.error.as_ref().map(|failure| failure.code.as_str())
        {
            return Err(store_error(
                "native_job_failure_binding_mismatch",
                "Materialized job failure does not match the terminal lifecycle event",
            ));
        }
        if let Some(artifact) = &view.bundle_manifest {
            let bytes = read_bounded(&job_dir.join(&artifact.path))?;
            if bytes.len() as u64 != artifact.byte_length
                || sha256_bytes_identity(&bytes) != artifact.content_hash
                || latest.bundle_manifest_hash.as_ref() != Some(&artifact.content_hash)
            {
                return Err(store_error(
                    "native_job_bundle_manifest_invalid",
                    "Succeeded job manifest reference is missing, stale or hash-mismatched",
                ));
            }
        }
        Ok(view)
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

fn load_event(
    job_dir: &Path,
    revision: u32,
) -> Result<structural_contracts::native_job::NativeFrame3dJobEventV1, NativeFrame3dJobStoreError> {
    parse_native_frame3d_job_event_v1(&read_bounded(
        &job_dir.join(format!("events/{revision:08}.json")),
    )?)
    .map_err(contract_error)
}

fn append_event(
    job_dir: &Path,
    event: &structural_contracts::native_job::NativeFrame3dJobEventV1,
) -> Result<(), NativeFrame3dJobStoreError> {
    write_new(
        &job_dir.join(format!("events/{:08}.json", event.revision)),
        event.canonical_json().map_err(contract_error)?.as_bytes(),
    )
}

fn replace_view(
    job_dir: &Path,
    view: &NativeFrame3dJobViewV1,
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
