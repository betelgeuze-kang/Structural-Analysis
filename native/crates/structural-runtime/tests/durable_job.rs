use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Barrier};

use structural_contracts::product_ir::parse_native_analysis_request_v1;
use structural_report::build_nonlinear_ndtha_report_v1;
use structural_runtime::{
    DurableJobCompletionV1, DurableJobStatusV1, DurableJobStoreV1, NonlinearNdthaExecutionStatus,
    Runtime,
};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn request_bytes() -> Vec<u8> {
    std::fs::read(
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
    )
    .expect("tracked product request")
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create(label: &str) -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-runtime-job-{label}-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated job test directory");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).expect("remove isolated job test directory");
    }
}

struct TerminalArtifacts {
    checkpoint: Vec<u8>,
    result_ir: Vec<u8>,
    report_ir: Vec<u8>,
    report_document: Vec<u8>,
}

fn checkpoint_after(
    request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
    step_budget: u32,
) -> Vec<u8> {
    let request = parse_native_analysis_request_v1(request_bytes).expect("strict request");
    let runtime = Runtime::new().expect("native runtime");
    let value = request.request();
    let mut state = checkpoint_bytes.map_or_else(
        || {
            runtime
                .begin_nonlinear_ndtha(&value.config, &value.inputs)
                .expect("initial state")
        },
        |bytes| {
            runtime
                .restore_nonlinear_ndtha(&value.config, &value.inputs, bytes)
                .expect("restored state")
        },
    );
    runtime
        .advance_nonlinear_ndtha(&value.config, &value.inputs, step_budget, &mut state)
        .expect("bounded advancement");
    runtime
        .checkpoint_nonlinear_ndtha(&value.config, &value.inputs, &state)
        .expect("validated checkpoint")
        .as_bytes()
        .to_vec()
}

fn terminal_artifacts(request_bytes: &[u8], checkpoint_bytes: Option<&[u8]>) -> TerminalArtifacts {
    let request = parse_native_analysis_request_v1(request_bytes).expect("strict request");
    let runtime = Runtime::new().expect("native runtime");
    let value = request.request();
    let mut state = checkpoint_bytes.map_or_else(
        || {
            runtime
                .begin_nonlinear_ndtha(&value.config, &value.inputs)
                .expect("initial state")
        },
        |bytes| {
            runtime
                .restore_nonlinear_ndtha(&value.config, &value.inputs, bytes)
                .expect("restored state")
        },
    );
    runtime
        .advance_nonlinear_ndtha(&value.config, &value.inputs, u32::MAX, &mut state)
        .expect("terminal advancement");
    assert!(matches!(
        state.status,
        NonlinearNdthaExecutionStatus::Completed | NonlinearNdthaExecutionStatus::Collapsed
    ));
    let product = runtime
        .finish_nonlinear_ndtha_product(&request, &state)
        .expect("terminal product");
    let report = build_nonlinear_ndtha_report_v1(&product.result_ir).expect("deterministic report");
    TerminalArtifacts {
        checkpoint: product.checkpoint.as_bytes().to_vec(),
        result_ir: product.result_ir.canonical_bytes().to_vec(),
        report_ir: report.report_ir.canonical_bytes().to_vec(),
        report_document: report.document_source.into_bytes(),
    }
}

fn completion(artifacts: &TerminalArtifacts) -> DurableJobCompletionV1<'_> {
    DurableJobCompletionV1 {
        checkpoint_bytes: &artifacts.checkpoint,
        result_ir_bytes: &artifacts.result_ir,
        report_ir_bytes: &artifacts.report_ir,
        report_document_bytes: &artifacts.report_document,
    }
}

fn assert_terminal_artifacts_equal(left: &TerminalArtifacts, right: &TerminalArtifacts) {
    assert_eq!(left.checkpoint, right.checkpoint);
    assert_eq!(left.result_ir, right.result_ir);
    assert_eq!(left.report_ir, right.report_ir);
    assert_eq!(left.report_document, right.report_document);
}

fn assert_legacy_submission_event_shape(root: &Path, job_id: &str) {
    let submitted_event = std::fs::read_to_string(
        root.join("jobs")
            .join(job_id)
            .join("events/00000000000000000000.json"),
    )
    .expect("legacy submission event");
    assert!(!submitted_event.contains("analysis_profile"));
    assert!(!submitted_event.contains("result_recovery_ir"));
}

#[test]
fn checkpointed_job_reopens_resumes_and_publishes_exact_terminal_artifacts() {
    let directory = TestDirectory::create("resume");
    let request = request_bytes();
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let submitted = store
        .submit("resume-e2e", &request, 1_000)
        .expect("submitted job");
    assert_eq!(submitted.status, DurableJobStatusV1::Queued);
    assert_legacy_submission_event_shape(&directory.0, &submitted.job_id);
    assert_eq!(
        store
            .submit("resume-e2e", &request, 1_001)
            .expect("idempotent submission"),
        submitted
    );

    let conflicting = String::from_utf8(request.clone())
        .expect("UTF-8 fixture")
        .replace("ndtha-one-story-elastic", "ndtha-one-story-conflict");
    let error = store
        .submit("resume-e2e", conflicting.as_bytes(), 1_002)
        .expect_err("idempotency conflict");
    assert_eq!(error.code, "job_idempotency_conflict");

    let first = store
        .claim_next("worker-first", 10_000, 1_100)
        .expect("first claim")
        .expect("queued job");
    assert_eq!(first.job.attempt, 1);
    let partial = checkpoint_after(&first.request_bytes, None, 2);
    let checkpointed = store
        .publish_checkpoint(
            &first.job.job_id,
            "worker-first",
            &first.lease_token,
            &partial,
            1_200,
        )
        .expect("durable partial checkpoint");
    assert_eq!(checkpointed.status, DurableJobStatusV1::Checkpointed);
    assert_eq!(checkpointed.progress_completed, 2);
    assert!(checkpointed.can_resume);
    drop(store);

    let reopened = DurableJobStoreV1::open(&directory.0).expect("reopened job store");
    assert_eq!(
        reopened
            .poll(&submitted.job_id)
            .expect("verified reopened chain"),
        checkpointed
    );
    let resumed = reopened
        .claim_next("worker-resume", 10_000, 1_300)
        .expect("resume claim")
        .expect("checkpointed job");
    assert_eq!(resumed.job.attempt, 2);
    assert_eq!(
        resumed.checkpoint_bytes.as_deref(),
        Some(partial.as_slice())
    );
    let resumed_artifacts =
        terminal_artifacts(&resumed.request_bytes, resumed.checkpoint_bytes.as_deref());
    let direct_artifacts = terminal_artifacts(&resumed.request_bytes, None);
    assert_terminal_artifacts_equal(&resumed_artifacts, &direct_artifacts);

    let succeeded = reopened
        .complete_job(
            &resumed.job.job_id,
            "worker-resume",
            &resumed.lease_token,
            completion(&resumed_artifacts),
            1_400,
        )
        .expect("complete durable job");
    assert_eq!(succeeded.status, DurableJobStatusV1::Succeeded);
    assert_eq!(succeeded.revision, 4);
    assert_eq!(succeeded.attempt, 2);
    assert_eq!(succeeded.progress_completed, succeeded.progress_total);
    assert!(!succeeded.can_resume);
    assert_eq!(
        reopened
            .read_result_ir(&succeeded.job_id)
            .expect("ResultIR"),
        direct_artifacts.result_ir
    );
    assert_eq!(
        reopened
            .read_report_ir(&succeeded.job_id)
            .expect("ReportIR"),
        direct_artifacts.report_ir
    );
    assert_eq!(
        reopened
            .read_report_document(&succeeded.job_id)
            .expect("report document"),
        direct_artifacts.report_document
    );
    assert!(reopened
        .claim_next("worker-idle", 1_000, 1_500)
        .expect("idle claim")
        .is_none());
}

#[test]
fn expired_lease_recovers_after_reopen_and_stale_worker_is_rejected() {
    let directory = TestDirectory::create("lease-recovery");
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let submitted = store
        .submit("lease-recovery", &request_bytes(), 10_000)
        .expect("submitted job");
    let crashed = store
        .claim_next("worker-crashed", 1_000, 9_000)
        .expect("first claim")
        .expect("queued job");
    assert_eq!(crashed.job.updated_unix_ms, 10_000);
    assert_eq!(crashed.job.lease_expires_unix_ms, Some(11_000));
    drop(store);

    let event_temporary = directory
        .0
        .join("jobs")
        .join(&submitted.job_id)
        .join("events")
        .join(".00000000000000000002.json.tmp.crashed.0");
    std::fs::write(event_temporary, b"incomplete").expect("simulated interrupted event write");
    let job_temporary = directory
        .0
        .join("jobs")
        .join(format!(".{}.tmp.crashed.0", submitted.job_id));
    std::fs::create_dir(job_temporary).expect("simulated interrupted job creation");

    let reopened = DurableJobStoreV1::open(&directory.0).expect("reopened job store");
    let recovered = reopened
        .claim_next("worker-recovery", 1_000, 11_100)
        .expect("expired lease recovery")
        .expect("requeued job");
    assert_eq!(recovered.job.attempt, 2);
    assert_eq!(recovered.job.revision, 3);
    assert_eq!(recovered.job.error_code, None);

    let error = reopened
        .fail_job(
            &submitted.job_id,
            "worker-crashed",
            &crashed.lease_token,
            "stale_worker",
            true,
            11_200,
        )
        .expect_err("stale lease rejected");
    assert_eq!(error.code, "job_lease_unauthorized");
    let requeued = reopened
        .fail_job(
            &submitted.job_id,
            "worker-recovery",
            &recovered.lease_token,
            "transient_worker_failure",
            true,
            11_300,
        )
        .expect("owned retriable failure");
    assert_eq!(requeued.status, DurableJobStatusV1::Queued);
    assert_eq!(
        requeued.error_code.as_deref(),
        Some("transient_worker_failure")
    );
}

#[test]
fn queued_and_running_cancellation_are_durable_and_idempotent() {
    let directory = TestDirectory::create("cancel");
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let queued = store
        .submit("cancel-queued", &request_bytes(), 20_000)
        .expect("queued job");
    let cancelled = store
        .request_cancel(&queued.job_id, 20_100)
        .expect("queued cancellation");
    assert_eq!(cancelled.status, DurableJobStatusV1::Cancelled);
    assert_eq!(
        store
            .request_cancel(&queued.job_id, 20_200)
            .expect("idempotent cancellation"),
        cancelled
    );

    let running = store
        .submit("cancel-running", &request_bytes(), 20_300)
        .expect("second job");
    let claim = store
        .claim_next("worker-cancel", 10_000, 20_400)
        .expect("claim")
        .expect("running job");
    assert_eq!(claim.job.job_id, running.job_id);
    let pending = store
        .request_cancel(&running.job_id, 20_500)
        .expect("cooperative cancellation request");
    assert_eq!(pending.status, DurableJobStatusV1::Running);
    assert!(pending.cancel_requested);
    let revision = pending.revision;
    assert_eq!(
        store
            .request_cancel(&running.job_id, 20_600)
            .expect("idempotent running cancellation")
            .revision,
        revision
    );
    let checkpoint = checkpoint_after(&claim.request_bytes, None, 1);
    let cancelled = store
        .publish_checkpoint(
            &running.job_id,
            "worker-cancel",
            &claim.lease_token,
            &checkpoint,
            20_700,
        )
        .expect("cancel acknowledgement checkpoint");
    assert_eq!(cancelled.status, DurableJobStatusV1::Cancelled);
    assert!(cancelled.checkpoint.is_some());
    assert!(!cancelled.can_resume);
    assert_eq!(cancelled.error_code.as_deref(), Some("cancelled_by_user"));
    assert!(store
        .claim_next("worker-idle", 1_000, 20_800)
        .expect("no cancelled claim")
        .is_none());
}

#[test]
fn concurrent_claim_has_one_winner_and_corrupt_blob_does_not_advance_state() {
    let directory = TestDirectory::create("concurrency");
    let store = Arc::new(DurableJobStoreV1::open(&directory.0).expect("job store"));
    let submitted = store
        .submit("concurrent-claim", &request_bytes(), 30_000)
        .expect("submitted job");
    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();
    for worker_id in ["worker-a", "worker-b"] {
        let store = Arc::clone(&store);
        let barrier = Arc::clone(&barrier);
        workers.push(std::thread::spawn(move || {
            barrier.wait();
            store
                .claim_next(worker_id, 10_000, 30_100)
                .expect("concurrent claim")
        }));
    }
    barrier.wait();
    let claimed = workers
        .into_iter()
        .filter_map(|worker| worker.join().expect("worker thread"))
        .count();
    assert_eq!(claimed, 1);
    let running = store.poll(&submitted.job_id).expect("running job");
    assert_eq!(running.status, DurableJobStatusV1::Running);
    assert_eq!(running.attempt, 1);

    let second_directory = TestDirectory::create("corrupt-blob");
    let second_store = DurableJobStoreV1::open(&second_directory.0).expect("second store");
    let second = second_store
        .submit("corrupt-request", &request_bytes(), 31_000)
        .expect("second job");
    let request_blob = second_directory
        .0
        .join("blobs/sha256")
        .join(&second.request.content_hash[7..]);
    let mut bytes = std::fs::read(&request_blob).expect("request blob");
    bytes[0] ^= 1;
    std::fs::write(request_blob, bytes).expect("tamper isolated blob");
    let error = second_store
        .claim_next("worker-integrity", 1_000, 31_100)
        .expect_err("corrupt content-addressed request rejected");
    assert_eq!(error.code, "job_artifact_integrity_failed");
    let unchanged = second_store
        .poll(&second.job_id)
        .expect("unchanged event chain");
    assert_eq!(unchanged.status, DurableJobStatusV1::Queued);
    assert_eq!(unchanged.revision, 0);
}

#[test]
fn completion_rejects_non_deterministic_report_source_without_publishing() {
    let directory = TestDirectory::create("completion-integrity");
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let submitted = store
        .submit("completion-integrity", &request_bytes(), 40_000)
        .expect("submitted job");
    let claim = store
        .claim_next("worker-complete", 10_000, 40_100)
        .expect("claim")
        .expect("queued job");
    let mut artifacts = terminal_artifacts(&claim.request_bytes, None);
    artifacts.report_document.extend_from_slice(b"\nforged\n");
    let error = store
        .complete_job(
            &submitted.job_id,
            "worker-complete",
            &claim.lease_token,
            completion(&artifacts),
            40_200,
        )
        .expect_err("document drift rejected");
    assert_eq!(error.code, "job_completion_identity_mismatch");
    let running = store
        .poll(&submitted.job_id)
        .expect("unchanged running job");
    assert_eq!(running.status, DurableJobStatusV1::Running);
    assert!(running.result_ir.is_none());
}

#[cfg(unix)]
#[test]
fn symlinked_store_directories_and_artifacts_are_rejected() {
    use std::os::unix::fs::symlink;

    let directory = TestDirectory::create("symlink-directory");
    let redirected = directory.0.join("redirected-jobs");
    std::fs::create_dir(&redirected).expect("redirect target");
    symlink(&redirected, directory.0.join("jobs")).expect("jobs symlink");
    let error = DurableJobStoreV1::open(&directory.0).expect_err("symlinked jobs directory");
    assert_eq!(error.code, "job_store_path_type_invalid");

    let artifact_directory = TestDirectory::create("symlink-artifact");
    let store = DurableJobStoreV1::open(&artifact_directory.0).expect("artifact store");
    let submitted = store
        .submit("symlink-artifact", &request_bytes(), 50_000)
        .expect("submitted job");
    let blob = artifact_directory
        .0
        .join("blobs/sha256")
        .join(&submitted.request.content_hash[7..]);
    let redirected_blob = artifact_directory.0.join("redirected-request.json");
    std::fs::rename(&blob, &redirected_blob).expect("move request blob inside test root");
    symlink(&redirected_blob, &blob).expect("request blob symlink");
    let error = store
        .claim_next("worker-symlink", 1_000, 50_100)
        .expect_err("symlinked request blob rejected");
    assert_eq!(error.code, "job_artifact_file_type_invalid");
    assert_eq!(
        store.poll(&submitted.job_id).expect("unchanged job").status,
        DurableJobStatusV1::Queued
    );
}
