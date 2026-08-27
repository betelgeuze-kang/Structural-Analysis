use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);

struct TempFile(PathBuf);

impl TempFile {
    fn write(label: &str, bytes: &[u8]) -> Self {
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-report-replay-{label}-{}-{sequence}.json",
            std::process::id()
        ));
        std::fs::write(&path, bytes).expect("temporary report replay file");
        Self(path)
    }
}

impl Drop for TempFile {
    fn drop(&mut self) {
        let _removed = std::fs::remove_file(&self.0);
    }
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn native_result() -> (TempFile, Value) {
    let fixture =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let mut model: Value =
        serde_json::from_slice(&std::fs::read(fixture).expect("ModelIR fixture"))
            .expect("ModelIR JSON");
    model["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    let model_file = TempFile::write("model", &serde_json::to_vec(&model).expect("model bytes"));
    let output = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["model", "analyze-frame3d"])
        .arg(&model_file.0)
        .args([
            "--load-pattern",
            "LC_AXIAL",
            "--result-id",
            "frame-alpha.LC_AXIAL",
        ])
        .output()
        .expect("native analysis runs");
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let value: Value = serde_json::from_slice(&output.stdout).expect("ResultIR JSON");
    (TempFile::write("result", &output.stdout), value)
}

fn replay(result: &TempFile, output: &str) -> Output {
    Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["result", "report-frame3d"])
        .arg(&result.0)
        .args(["--report-id", "report.LC_AXIAL", "--output", output])
        .output()
        .expect("report replay CLI runs")
}

#[test]
fn persisted_result_replays_to_a_source_bound_report_ir() {
    let (result_file, result) = native_result();
    let first = replay(&result_file, "report-ir");
    let second = replay(&result_file, "report-ir");

    assert_eq!(first.status.code(), Some(0));
    assert_eq!(first.stdout, second.stdout);
    assert!(first.stderr.is_empty());
    let report: Value = serde_json::from_slice(&first.stdout).expect("ReportIR JSON");
    assert_eq!(
        report["schema_version"],
        "structural-native-linear-frame3d-report-ir.v1"
    );
    assert_eq!(report["source_result"]["result_id"], result["result_id"]);
    assert_eq!(
        report["source_result"]["result_hash"],
        result["result_hash"]
    );
    assert_eq!(
        report["authority"]["presentation"],
        "deterministic_projection"
    );
    assert_eq!(
        report["authority"]["release_readiness"],
        "not_authoritative"
    );
}

#[test]
fn persisted_result_replays_to_deterministic_html() {
    let (result_file, _) = native_result();
    let first = replay(&result_file, "html");
    let second = replay(&result_file, "html");

    assert_eq!(first.status.code(), Some(0));
    assert_eq!(first.stdout, second.stdout);
    let html = String::from_utf8(first.stdout).expect("UTF-8 report HTML");
    assert!(html.starts_with("<!doctype html>\n"));
    assert!(html.contains("deterministic_presentation_of_bounded_candidate_result"));
    assert!(html.contains("no_design_or_release_authority"));
}

#[test]
fn tampered_persisted_result_fails_closed_without_report_output() {
    let (_, mut result) = native_result();
    result["nodes"][1]["displacement_m_rad"][0] = json!(1.0);
    let result_file = TempFile::write(
        "tampered-result",
        &serde_json::to_vec(&result).expect("tampered ResultIR bytes"),
    );
    let output = replay(&result_file, "report-ir");

    assert_eq!(output.status.code(), Some(2));
    let failure: Value = serde_json::from_slice(&output.stdout).expect("failure JSON");
    assert_eq!(
        failure["schema_version"],
        "structural-native-linear-frame3d-report-failure.v1"
    );
    assert_ne!(
        failure["schema_version"],
        "structural-native-linear-frame3d-report-ir.v1"
    );
    assert_eq!(
        failure["claim_boundary"],
        "persisted_result_report_replay_failed_closed_without_presentation_design_or_release_authority"
    );
}
