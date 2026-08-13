use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::model_linear_job::{
    build_model_ir_linear_durable_job_request_v1, parse_model_ir_linear_durable_job_request_v1,
};
use structural_report::build_sparse_linear_report_v1;
use structural_runtime::{
    DurableJobAnalysisProfileV1, DurableJobStatusV1, DurableJobStoreV1,
    ModelIrLinearCheckpointBindingsV1, ModelIrLinearCheckpointV1,
    ModelIrLinearDurableJobCompletionV1, Runtime,
};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn model_bytes() -> Vec<u8> {
    std::fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("ModelIR fixture")
}

fn request_bytes(max_iterations: u32) -> Vec<u8> {
    let bytes = std::fs::read(
        repository_root()
            .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"),
    )
    .expect("analysis request fixture");
    let mut value: Value = serde_json::from_slice(&bytes).expect("request JSON");
    value["config"]["max_iterations"] = json!(max_iterations);
    serde_json::to_vec(&value).expect("modified request")
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create(label: &str) -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-model-linear-job-{label}-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("isolated test directory");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).expect("remove isolated test directory");
    }
}

struct Boundary {
    checkpoint: ModelIrLinearCheckpointV1,
    result_ir: Option<Vec<u8>>,
    recovery_ir: Option<Vec<u8>>,
    report_ir: Option<Vec<u8>>,
    report_document: Option<Vec<u8>>,
}

fn advance(envelope: &[u8], checkpoint: Option<&[u8]>, budget: u32) -> Boundary {
    let request = parse_model_ir_linear_durable_job_request_v1(envelope).expect("durable request");
    let runtime = Runtime::new().expect("runtime");
    let prepared = runtime
        .prepare_model_ir_linear_product(request.model_ir(), request.analysis_request())
        .expect("prepared product");
    let restored = checkpoint
        .map(ModelIrLinearCheckpointV1::from_bytes)
        .transpose()
        .expect("outer checkpoint");
    let progress = runtime
        .advance_sparse_linear_product(
            &prepared.generated_request,
            restored.as_ref().map(|value| value.inner().as_bytes()),
            budget,
        )
        .expect("PCG advancement");
    let bindings = ModelIrLinearCheckpointBindingsV1 {
        model_content_hash: request.model_ir().content_hash().to_owned(),
        model_semantic_hash: request.model_ir().semantic_hash().to_owned(),
        model_provenance_hash: request.model_ir().provenance_hash().to_owned(),
        analysis_request_hash: request.analysis_request().request_hash().to_owned(),
        assembly_hash: prepared.assembly_hash.clone(),
        generated_request_hash: prepared.generated_request.request_hash().to_owned(),
    };
    let checkpoint =
        ModelIrLinearCheckpointV1::create(progress.checkpoint, &bindings).expect("outer boundary");
    let (result_ir, recovery_ir, report_ir, report_document) =
        progress
            .result_ir
            .map_or((None, None, None, None), |result| {
                let recovery = runtime
                    .recover_model_ir_linear_product(
                        request.model_ir(),
                        request.analysis_request(),
                        &prepared,
                        &result,
                    )
                    .expect("terminal recovery");
                let report = build_sparse_linear_report_v1(&result).expect("terminal report");
                (
                    Some(result.canonical_bytes().to_vec()),
                    Some(recovery.into_bytes()),
                    Some(report.report_ir.canonical_json().as_bytes().to_vec()),
                    Some(report.document_source.into_bytes()),
                )
            });
    Boundary {
        checkpoint,
        result_ir,
        recovery_ir,
        report_ir,
        report_document,
    }
}

fn completion(boundary: &Boundary) -> ModelIrLinearDurableJobCompletionV1<'_> {
    ModelIrLinearDurableJobCompletionV1 {
        checkpoint_bytes: boundary.checkpoint.as_bytes(),
        result_ir_bytes: boundary.result_ir.as_deref().expect("ResultIR"),
        result_recovery_ir_bytes: boundary.recovery_ir.as_deref().expect("recovery IR"),
        report_ir_bytes: boundary.report_ir.as_deref().expect("ReportIR"),
        report_document_bytes: boundary
            .report_document
            .as_deref()
            .expect("report document"),
    }
}

#[test]
#[allow(clippy::too_many_lines)]
fn model_linear_job_reopens_resumes_and_revalidates_every_terminal_projection() {
    let directory = TestDirectory::create("resume");
    let model = model_bytes();
    let analysis_request = request_bytes(100);
    let envelope = build_model_ir_linear_durable_job_request_v1(&model, &analysis_request)
        .expect("durable envelope");
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let submitted = store
        .submit_model_ir_linear("model-linear-resume", &model, &analysis_request, 1_000)
        .expect("submitted job");
    assert_eq!(
        submitted.analysis_profile,
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1
    );
    assert_eq!(submitted.progress_total, 100);
    assert_eq!(
        store
            .submit_model_ir_linear_envelope(
                "model-linear-resume",
                envelope.canonical_bytes(),
                1_001,
            )
            .expect("idempotent envelope submission"),
        submitted
    );

    let first = store
        .claim_next("worker-first", 10_000, 1_100)
        .expect("claim")
        .expect("queued job");
    assert_eq!(first.request_bytes, envelope.canonical_bytes());
    let partial = advance(&first.request_bytes, None, 1);
    assert!(partial.result_ir.is_none());
    let checkpointed = store
        .publish_model_ir_linear_checkpoint(
            &first.job.job_id,
            "worker-first",
            &first.lease_token,
            partial.checkpoint.as_bytes(),
            1_200,
        )
        .expect("published partial boundary");
    assert_eq!(checkpointed.status, DurableJobStatusV1::Checkpointed);
    assert_eq!(checkpointed.progress_completed, 1);
    drop(store);

    let reopened = DurableJobStoreV1::open(&directory.0).expect("reopened store");
    assert_eq!(
        reopened.poll(&submitted.job_id).expect("poll"),
        checkpointed
    );
    let resumed = reopened
        .claim_next("worker-resume", 10_000, 1_300)
        .expect("resume claim")
        .expect("checkpointed job");
    let resumed_boundary = advance(
        &resumed.request_bytes,
        resumed.checkpoint_bytes.as_deref(),
        u32::MAX,
    );
    let direct_boundary = advance(&resumed.request_bytes, None, u32::MAX);
    assert_eq!(
        resumed_boundary.checkpoint.as_bytes(),
        direct_boundary.checkpoint.as_bytes()
    );
    assert_eq!(resumed_boundary.result_ir, direct_boundary.result_ir);
    assert_eq!(resumed_boundary.recovery_ir, direct_boundary.recovery_ir);
    assert_eq!(resumed_boundary.report_ir, direct_boundary.report_ir);
    assert_eq!(
        resumed_boundary.report_document,
        direct_boundary.report_document
    );

    let mut forged_recovery = resumed_boundary
        .recovery_ir
        .as_ref()
        .expect("recovery")
        .clone();
    forged_recovery[0] ^= 1;
    let mut forged = completion(&resumed_boundary);
    forged.result_recovery_ir_bytes = &forged_recovery;
    let error = reopened
        .complete_model_ir_linear_job(
            &resumed.job.job_id,
            "worker-resume",
            &resumed.lease_token,
            forged,
            1_400,
        )
        .expect_err("forged recovery rejected");
    assert_eq!(error.code, "job_completion_projection_mismatch");
    assert_eq!(
        reopened
            .poll(&resumed.job.job_id)
            .expect("unchanged job")
            .status,
        DurableJobStatusV1::Running
    );

    let succeeded = reopened
        .complete_model_ir_linear_job(
            &resumed.job.job_id,
            "worker-resume",
            &resumed.lease_token,
            completion(&resumed_boundary),
            1_401,
        )
        .expect("completed durable job");
    assert_eq!(succeeded.status, DurableJobStatusV1::Succeeded);
    assert!(succeeded.progress_completed < succeeded.progress_total);
    assert_eq!(
        reopened
            .read_result_recovery_ir(&succeeded.job_id)
            .expect("published recovery"),
        direct_boundary.recovery_ir.expect("direct recovery")
    );
}

#[test]
fn model_linear_numerical_failure_and_cooperative_cancel_retain_exact_checkpoints() {
    let directory = TestDirectory::create("terminal-transitions");
    let model = model_bytes();
    let failing_request = request_bytes(1);
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let failed_job = store
        .submit_model_ir_linear("model-linear-failure", &model, &failing_request, 2_000)
        .expect("submitted failure job");
    let failure_claim = store
        .claim_next("worker-failure", 10_000, 2_100)
        .expect("failure claim")
        .expect("queued failure job");
    let failure = advance(&failure_claim.request_bytes, None, u32::MAX);
    assert!(failure.result_ir.is_none());
    let failed = store
        .fail_model_ir_linear_job(
            &failed_job.job_id,
            "worker-failure",
            &failure_claim.lease_token,
            failure.checkpoint.as_bytes(),
            2_200,
        )
        .expect("terminal numerical failure");
    assert_eq!(failed.status, DurableJobStatusV1::Failed);
    assert_eq!(
        failed.error_code.as_deref(),
        Some("model_ir_linear_nonconvergence")
    );
    assert_eq!(
        store
            .read_checkpoint(&failed.job_id)
            .expect("failure checkpoint"),
        failure.checkpoint.as_bytes()
    );

    let normal_request = request_bytes(100);
    let cancel_job = store
        .submit_model_ir_linear("model-linear-cancel", &model, &normal_request, 2_300)
        .expect("submitted cancel job");
    let cancel_claim = store
        .claim_next("worker-cancel", 10_000, 2_400)
        .expect("cancel claim")
        .expect("queued cancel job");
    let partial = advance(&cancel_claim.request_bytes, None, 1);
    let pending = store
        .request_cancel(&cancel_job.job_id, 2_500)
        .expect("cancel requested");
    assert!(pending.cancel_requested);
    let cancelled = store
        .publish_model_ir_linear_checkpoint(
            &cancel_job.job_id,
            "worker-cancel",
            &cancel_claim.lease_token,
            partial.checkpoint.as_bytes(),
            2_600,
        )
        .expect("cancel acknowledgement");
    assert_eq!(cancelled.status, DurableJobStatusV1::Cancelled);
    assert!(cancelled.checkpoint.is_some());
    assert!(!cancelled.can_resume);
}

#[test]
fn model_linear_expired_lease_requeues_after_reopen_and_rejects_stale_worker() {
    let directory = TestDirectory::create("lease-recovery");
    let model = model_bytes();
    let request = request_bytes(100);
    let store = DurableJobStoreV1::open(&directory.0).expect("job store");
    let submitted = store
        .submit_model_ir_linear("model-linear-lease", &model, &request, 3_000)
        .expect("submitted job");
    let crashed = store
        .claim_next("worker-crashed", 1_000, 3_100)
        .expect("first claim")
        .expect("queued job");
    drop(store);

    let reopened = DurableJobStoreV1::open(&directory.0).expect("reopened store");
    let recovered = reopened
        .claim_next("worker-recovered", 1_000, 4_101)
        .expect("recovered claim")
        .expect("requeued job");
    assert_eq!(recovered.job.job_id, submitted.job_id);
    assert_eq!(recovered.job.attempt, 2);
    assert_eq!(recovered.job.revision, 3);
    assert_eq!(recovered.request_bytes, crashed.request_bytes);
    assert_eq!(
        recovered.job.analysis_profile,
        DurableJobAnalysisProfileV1::ModelIrLinearCpuV1
    );

    let error = reopened
        .fail_job(
            &submitted.job_id,
            "worker-crashed",
            &crashed.lease_token,
            "stale_model_worker",
            false,
            4_200,
        )
        .expect_err("stale lease rejected");
    assert_eq!(error.code, "job_lease_unauthorized");
}
