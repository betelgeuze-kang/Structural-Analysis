use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::native_job::{
    create_native_frame3d_job_event_v1, create_native_frame3d_job_event_v2,
    create_native_frame3d_job_request_v1, create_native_frame3d_job_view_v1,
    create_native_frame3d_job_view_v2, parse_native_frame3d_job_event_v2,
    parse_native_frame3d_job_request_v1, NativeFrame3dJobEventTypeV1, NativeFrame3dJobEventTypeV2,
};
use structural_runtime::{
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobStatusV1, NativeFrame3dJobStatusV2,
    NativeFrame3dJobStore, NativeFrame3dJobViewRecord,
};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TempStore(PathBuf);

impl TempStore {
    fn new() -> Self {
        let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        Self(std::env::temp_dir().join(format!(
            "structural-native-job-store-{}-{sequence}",
            std::process::id()
        )))
    }
}

impl Drop for TempStore {
    fn drop(&mut self) {
        let _removed = std::fs::remove_dir_all(&self.0);
    }
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn frame_alpha_bytes() -> Vec<u8> {
    let mut value: Value = serde_json::from_slice(
        &std::fs::read(
            repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("tracked fixture"),
    )
    .expect("fixture JSON");
    value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    serde_json::to_vec(&value).expect("Frame Alpha JSON")
}

fn simulate_worker_stopped_while_running(
    temporary: &TempStore,
    store: &NativeFrame3dJobStore,
    job_id: &str,
) {
    let job_dir = temporary.0.join(job_id);
    let request = parse_native_frame3d_job_request_v1(
        &std::fs::read(job_dir.join("request.json")).expect("request bytes"),
    )
    .expect("strict request");
    let submitted = parse_native_frame3d_job_event_v2(
        &std::fs::read(job_dir.join("events/00000000.json")).expect("submitted event bytes"),
    )
    .expect("strict submitted event");
    let queued = store.inspect(job_id).expect("strict queued view");
    let started = create_native_frame3d_job_event_v2(
        &request,
        1,
        queued.updated_unix_ms().saturating_add(1),
        NativeFrame3dJobEventTypeV2::Started,
        NativeFrame3dJobStatusV2::Running,
        Some(submitted.event_hash),
        None,
        None,
        None,
    )
    .expect("started event");
    let running = create_native_frame3d_job_view_v2(&request, &started, None, None, None)
        .expect("running view");
    std::fs::write(
        job_dir.join("events/00000001.json"),
        started.canonical_json().expect("started JSON"),
    )
    .expect("started event write");
    std::fs::write(
        job_dir.join("view.json"),
        running.canonical_json().expect("running JSON"),
    )
    .expect("running view write");
    std::fs::write(job_dir.join("run.lock"), request.request_hash).expect("run lock write");
    assert_eq!(
        store.inspect(job_id).expect("strict running view").status(),
        NativeFrame3dJobStatusV2::Running
    );
}

#[test]
fn submit_run_inspect_persists_a_hash_bound_success_chain() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_0123456789abcdef0123456789abcdef";
    let queued = store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.LC_AXIAL",
            "job.report.LC_AXIAL",
        )
        .expect("queued submission");
    assert_eq!(queued.status(), NativeFrame3dJobStatusV2::Queued);
    assert_eq!(queued.revision(), 0);

    let succeeded = store.run(job_id).expect("persisted execution");
    assert_eq!(succeeded.status(), NativeFrame3dJobStatusV2::Succeeded);
    assert_eq!(succeeded.revision(), 2);
    assert!(succeeded.bundle_manifest().is_some());
    assert!(temporary.0.join(job_id).join("run.lock").is_file());
    for path in [
        "events/00000000.json",
        "events/00000001.json",
        "events/00000002.json",
        "bundle/model-ir.json",
        "bundle/result-ir.json",
        "bundle/report-ir.json",
        "bundle/report.html",
        "bundle/manifest.json",
    ] {
        assert!(temporary.0.join(job_id).join(path).is_file(), "{path}");
    }
    assert_eq!(store.inspect(job_id).expect("strict inspect"), succeeded);
    assert_eq!(
        store
            .run(job_id)
            .expect_err("second execution forbidden")
            .code,
        "native_job_not_queued"
    );
}

#[test]
fn analysis_failure_is_a_terminal_persisted_view_without_bundle_authority() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_11111111111111111111111111111111";
    store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "UNKNOWN".to_owned(),
            },
            "job.result.UNKNOWN",
            "job.report.UNKNOWN",
        )
        .expect("queued submission");
    let failed = store.run(job_id).expect("failure persisted");
    assert_eq!(failed.status(), NativeFrame3dJobStatusV2::Failed);
    assert_eq!(failed.revision(), 2);
    assert!(failed.bundle_manifest().is_none());
    assert_eq!(
        failed.error().expect("terminal error").code,
        "native_analysis_failed"
    );
    assert!(!temporary
        .0
        .join(job_id)
        .join("bundle/manifest.json")
        .exists());
    assert_eq!(store.inspect(job_id).expect("strict inspect"), failed);
}

#[test]
fn isolated_worker_failure_is_append_only_terminalized_without_bundle_authority() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_33333333333333333333333333333333";
    store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.worker-crash",
            "job.report.worker-crash",
        )
        .expect("queued submission");
    simulate_worker_stopped_while_running(&temporary, &store, job_id);

    let failed = store
        .finalize_running_failure(
            job_id,
            "native_worker_process_exit",
            "Isolated worker exited before a terminal transition",
        )
        .expect("terminal failure finalization");
    assert_eq!(failed.status(), NativeFrame3dJobStatusV2::Failed);
    assert_eq!(failed.revision(), 2);
    assert!(failed.bundle_manifest().is_none());
    let error = failed.error().expect("terminal failure");
    assert_eq!(error.code, "native_worker_process_exit");
    assert_eq!(
        error.detail,
        "Isolated worker exited before a terminal transition"
    );
    assert!(temporary
        .0
        .join(job_id)
        .join("events/00000002.json")
        .is_file());
    assert_eq!(store.inspect(job_id).expect("strict failed replay"), failed);
    assert_eq!(
        store
            .finalize_running_failure(job_id, "second_failure", "must not overwrite")
            .expect_err("terminal overwrite forbidden")
            .code,
        "native_job_not_running"
    );
}

#[test]
fn failure_finalization_does_not_invent_a_started_transition_for_queued_jobs() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_44444444444444444444444444444444";
    let queued = store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.queued",
            "job.report.queued",
        )
        .expect("queued submission");
    assert_eq!(
        store
            .finalize_running_failure(job_id, "native_worker_timeout", "never started")
            .expect_err("queued finalization forbidden")
            .code,
        "native_job_not_running"
    );
    assert_eq!(
        store.inspect(job_id).expect("queued view unchanged"),
        queued
    );
    assert!(!temporary
        .0
        .join(job_id)
        .join("events/00000001.json")
        .exists());
}

#[test]
fn queued_cancellation_is_append_only_and_cannot_be_overwritten() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_55555555555555555555555555555555";
    store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.cancel-queued",
            "job.report.cancel-queued",
        )
        .expect("queued submission");

    let cancelled = store
        .finalize_cancellation(
            job_id,
            "native_worker_cancelled",
            "Worker was stopped and reaped before execution began",
        )
        .expect("queued cancellation");
    assert_eq!(cancelled.status(), NativeFrame3dJobStatusV2::Cancelled);
    assert_eq!(cancelled.revision(), 1);
    assert!(cancelled.bundle_manifest().is_none());
    assert!(cancelled.error().is_none());
    assert_eq!(
        cancelled
            .cancellation()
            .expect("cancellation evidence")
            .code,
        "native_worker_cancelled"
    );
    assert_eq!(store.inspect(job_id).expect("strict replay"), cancelled);
    assert_eq!(
        store
            .finalize_cancellation(job_id, "second_cancel", "must not overwrite")
            .expect_err("terminal overwrite forbidden")
            .code,
        "native_job_not_cancellable"
    );
    assert!(store.run(job_id).is_err());
}

#[test]
fn running_cancellation_is_a_distinct_revision_two_terminal_transition() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_66666666666666666666666666666666";
    store
        .submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.cancel-running",
            "job.report.cancel-running",
        )
        .expect("queued submission");
    simulate_worker_stopped_while_running(&temporary, &store, job_id);

    let cancelled = store
        .finalize_cancellation(
            job_id,
            "native_worker_cancelled",
            "Worker was stopped and reaped while running",
        )
        .expect("running cancellation");
    assert_eq!(cancelled.status(), NativeFrame3dJobStatusV2::Cancelled);
    assert_eq!(cancelled.revision(), 2);
    assert!(cancelled.error().is_none());
    assert!(cancelled.cancellation().is_some());
    assert!(temporary
        .0
        .join(job_id)
        .join("events/00000002.json")
        .is_file());

    let view_path = temporary.0.join(job_id).join("view.json");
    let tampered = std::fs::read_to_string(&view_path)
        .expect("view JSON")
        .replace("native_worker_cancelled", "native_worker_interrupted");
    std::fs::write(view_path, tampered).expect("test-only tamper");
    assert_eq!(
        store
            .inspect(job_id)
            .expect_err("cancellation binding tamper rejected")
            .code,
        "native_job_cancellation_binding_mismatch"
    );
}

#[test]
fn legacy_v1_job_remains_strictly_replayable_without_v2_mutation() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_77777777777777777777777777777777";
    let model_bytes = frame_alpha_bytes();
    let model = parse_model_ir_v2(&model_bytes).expect("strict model");
    let request = create_native_frame3d_job_request_v1(
        job_id,
        1_700_000_000_000,
        model.content_hash(),
        NativeFrame3dJobLoadSourceV1::Pattern {
            id: "LC_AXIAL".to_owned(),
        },
        "job.result.legacy-v1",
        "job.report.legacy-v1",
    )
    .expect("v1 request");
    let submitted = create_native_frame3d_job_event_v1(
        &request,
        0,
        request.submitted_unix_ms,
        NativeFrame3dJobEventTypeV1::Submitted,
        NativeFrame3dJobStatusV1::Queued,
        None,
        None,
        None,
    )
    .expect("v1 submitted event");
    let view = create_native_frame3d_job_view_v1(&request, &submitted, None, None)
        .expect("v1 queued view");
    let job_dir = temporary.0.join(job_id);
    std::fs::create_dir_all(job_dir.join("events")).expect("legacy job directory");
    std::fs::write(job_dir.join("model-ir.json"), &model_bytes).expect("model write");
    std::fs::write(
        job_dir.join("request.json"),
        request.canonical_json().expect("request JSON"),
    )
    .expect("request write");
    std::fs::write(
        job_dir.join("events/00000000.json"),
        submitted.canonical_json().expect("event JSON"),
    )
    .expect("event write");
    std::fs::write(
        job_dir.join("view.json"),
        view.canonical_json().expect("view JSON"),
    )
    .expect("view write");

    let replay = store.inspect(job_id).expect("legacy replay");
    assert!(matches!(replay, NativeFrame3dJobViewRecord::V1(_)));
    assert_eq!(replay.status(), NativeFrame3dJobStatusV2::Queued);
    assert_eq!(
        store
            .finalize_cancellation(job_id, "legacy_cancel", "unsupported")
            .expect_err("v1 cancellation rejected")
            .code,
        "native_job_v1_cancellation_unsupported"
    );
}

#[test]
fn duplicate_submission_and_event_tampering_fail_closed() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    let job_id = "job_22222222222222222222222222222222";
    let submit = || {
        store.submit(
            job_id,
            &frame_alpha_bytes(),
            NativeFrame3dJobLoadSourceV1::Pattern {
                id: "LC_AXIAL".to_owned(),
            },
            "job.result.LC_AXIAL",
            "job.report.LC_AXIAL",
        )
    };
    submit().expect("initial submission");
    assert_eq!(
        submit().expect_err("no overwrite").code,
        "native_job_already_exists"
    );

    let event_path = temporary.0.join(job_id).join("events/00000000.json");
    let bytes = std::fs::read(&event_path).expect("event bytes");
    let tampered = String::from_utf8(bytes)
        .expect("UTF-8 event")
        .replace("\"revision\":0", "\"revision\":1");
    std::fs::write(event_path, tampered).expect("test-only tamper");
    assert!(store.inspect(job_id).is_err());
}

#[test]
fn traversal_shaped_job_identity_never_reaches_the_filesystem() {
    let temporary = TempStore::new();
    let store = NativeFrame3dJobStore::new(&temporary.0);
    assert_eq!(
        store
            .inspect("../job_0123456789abcdef0123456789abcdef")
            .expect_err("traversal rejected")
            .code,
        "native_job_id_invalid"
    );
    assert!(!temporary.0.exists());
}
