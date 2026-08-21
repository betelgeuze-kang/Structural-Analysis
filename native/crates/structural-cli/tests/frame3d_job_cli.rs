use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TempJob(PathBuf);

impl TempJob {
    fn new() -> Self {
        let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-native-job-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("temporary job root");
        let mut model: Value = serde_json::from_slice(
            &std::fs::read(source_fixture()).expect("tracked ModelIR fixture"),
        )
        .expect("fixture JSON");
        model["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
        std::fs::write(
            path.join("model.json"),
            serde_json::to_vec(&model).expect("model JSON"),
        )
        .expect("temporary model");
        Self(path)
    }

    fn model(&self) -> PathBuf {
        self.0.join("model.json")
    }

    fn store(&self) -> PathBuf {
        self.0.join("store")
    }
}

impl Drop for TempJob {
    fn drop(&mut self) {
        let _removed = std::fs::remove_dir_all(&self.0);
    }
}

fn source_fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
}

fn cli(arguments: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(arguments)
        .output()
        .expect("run structural-cli")
}

fn payload(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).expect("CLI JSON output")
}

#[test]
fn cli_submit_run_and_inspect_expose_only_strict_native_job_views() {
    let temporary = TempJob::new();
    let model = temporary.model().to_string_lossy().into_owned();
    let store = temporary.store().to_string_lossy().into_owned();
    let job_id = "job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let submitted = cli(&[
        "job",
        "submit-frame3d",
        &model,
        "--store",
        &store,
        "--job-id",
        job_id,
        "--load-pattern",
        "LC_AXIAL",
        "--result-id",
        "cli.job.result",
        "--report-id",
        "cli.job.report",
    ]);
    assert!(submitted.status.success(), "{:?}", submitted.stderr);
    let submitted_json = payload(&submitted);
    assert_eq!(submitted_json["status"], "queued");
    assert_eq!(
        submitted_json["service_profile"],
        "filesystem_append_only_single_host.v2"
    );
    assert_eq!(submitted_json["capabilities"]["cancellation"], true);
    assert_eq!(submitted_json["capabilities"]["crash_recovery"], false);

    let run = cli(&["job", "run", job_id, "--store", &store]);
    assert!(run.status.success(), "{:?}", run.stderr);
    let run_json = payload(&run);
    assert_eq!(run_json["status"], "succeeded");
    assert_eq!(run_json["bundle_manifest"]["path"], "bundle/manifest.json");
    assert_eq!(run_json["error"], Value::Null);
    assert_eq!(run_json["cancellation"], Value::Null);

    let inspect = cli(&["job", "inspect", job_id, "--store", &store]);
    assert!(inspect.status.success());
    assert_eq!(payload(&inspect), run_json);
}

#[test]
fn cli_returns_failure_for_a_persisted_terminal_analysis_error() {
    let temporary = TempJob::new();
    let model = temporary.model().to_string_lossy().into_owned();
    let store = temporary.store().to_string_lossy().into_owned();
    let job_id = "job_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    assert!(cli(&[
        "job",
        "submit-frame3d",
        &model,
        "--store",
        &store,
        "--job-id",
        job_id,
        "--load-pattern",
        "UNKNOWN",
        "--result-id",
        "cli.job.failed.result",
        "--report-id",
        "cli.job.failed.report",
    ])
    .status
    .success());

    let run = cli(&["job", "run", job_id, "--store", &store]);
    assert!(!run.status.success());
    let failed = payload(&run);
    assert_eq!(failed["status"], "failed");
    assert_eq!(failed["bundle_manifest"], Value::Null);
    assert_eq!(failed["error"]["code"], "native_analysis_failed");

    let inspect = cli(&["job", "inspect", job_id, "--store", &store]);
    assert!(inspect.status.success());
    assert_eq!(payload(&inspect), failed);
}

#[test]
fn cli_rejects_invalid_job_identity_without_creating_a_store() {
    let temporary = TempJob::new();
    let model = temporary.model().to_string_lossy().into_owned();
    let store = temporary.store().to_string_lossy().into_owned();
    let output = cli(&[
        "job",
        "submit-frame3d",
        &model,
        "--store",
        &store,
        "--job-id",
        "../escape",
        "--load-pattern",
        "LC_AXIAL",
        "--result-id",
        "cli.job.result",
        "--report-id",
        "cli.job.report",
    ]);
    assert!(!output.status.success());
    assert_eq!(
        payload(&output)["issues"][0]["code"],
        "native_job_request_schema_invalid"
    );
    assert!(!temporary.store().exists());
}
