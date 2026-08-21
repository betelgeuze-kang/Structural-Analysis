use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_runtime::{
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobStatusV1, NativeFrame3dJobStore,
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
    assert_eq!(queued.status, NativeFrame3dJobStatusV1::Queued);
    assert_eq!(queued.revision, 0);

    let succeeded = store.run(job_id).expect("persisted execution");
    assert_eq!(succeeded.status, NativeFrame3dJobStatusV1::Succeeded);
    assert_eq!(succeeded.revision, 2);
    assert!(succeeded.bundle_manifest.is_some());
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
    assert_eq!(failed.status, NativeFrame3dJobStatusV1::Failed);
    assert_eq!(failed.revision, 2);
    assert!(failed.bundle_manifest.is_none());
    assert_eq!(
        failed.error.as_ref().expect("terminal error").code,
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
