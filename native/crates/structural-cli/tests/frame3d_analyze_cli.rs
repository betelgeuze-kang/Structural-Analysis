use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);

struct TempModel(PathBuf);

impl TempModel {
    fn frame_alpha() -> Self {
        let mut value: Value = serde_json::from_slice(
            &std::fs::read(source_fixture()).expect("tracked ModelIR fixture"),
        )
        .expect("fixture JSON");
        value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-frame3d-{}-{sequence}.json",
            std::process::id()
        ));
        std::fs::write(&path, serde_json::to_vec(&value).expect("JSON"))
            .expect("temporary Frame Alpha ModelIR");
        Self(path)
    }
}

impl Drop for TempModel {
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

fn source_fixture() -> PathBuf {
    repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
}

fn run(output: &str, report_id: bool) -> Output {
    let model = TempModel::frame_alpha();
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
    command
        .args(["model", "analyze-frame3d"])
        .arg(&model.0)
        .args([
            "--load-pattern",
            "LC_AXIAL",
            "--result-id",
            "frame-alpha.LC_AXIAL",
            "--output",
            output,
        ]);
    if report_id {
        command.args(["--report-id", "frame-alpha.LC_AXIAL.report"]);
    }
    command.output().expect("CLI runs")
}

fn json_output(output: &Output) -> Value {
    assert!(
        output.stderr.is_empty(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("one JSON document on stdout")
}

#[test]
fn bounded_cli_emits_hash_bound_result_and_report_ir() {
    let result = run("result-ir", false);
    assert_eq!(result.status.code(), Some(0));
    let result = json_output(&result);
    assert_eq!(
        result["schema_version"],
        "structural-native-linear-frame3d-result-ir.v1"
    );
    assert_eq!(result["bindings"]["load_pattern_id"], "LC_AXIAL");
    assert_eq!(result["authority"]["reaction"], "bounded_candidate");
    assert_eq!(result["gates"]["independent_recovery_replay_passed"], true);
    assert_eq!(
        result["claim_boundary"]["independent_recovery_replay"],
        true
    );
    assert_eq!(result["claim_boundary"]["nodal_load_only"], false);
    assert_eq!(
        result["claim_boundary"]["uniform_member_load_initial_local"],
        true
    );
    assert!(
        result["gates"]["member_force_replay_scaled_linf"]
            .as_f64()
            .expect("finite recovery replay metric")
            <= 1.0e-9
    );
    assert_eq!(
        result["authority"]["release_readiness"],
        "not_authoritative"
    );

    let report = run("report-ir", true);
    assert_eq!(report.status.code(), Some(0));
    let report = json_output(&report);
    assert_eq!(
        report["schema_version"],
        "structural-native-linear-frame3d-report-ir.v1"
    );
    assert_eq!(
        report["source_result"]["result_hash"],
        result["result_hash"]
    );
    assert_eq!(report["authority"]["comparison"], "not_evaluated");
    assert_eq!(report["gates"]["independent_recovery_replay_passed"], true);
    let limitations = report["limitations"].as_array().expect("fixed limitations");
    assert!(limitations
        .iter()
        .any(|value| value == "load_scope_nodal_and_uniform_initial_local_force"));
    assert!(limitations
        .iter()
        .any(|value| value == "no_nonuniform_or_member_point_load"));
    assert!(!limitations
        .iter()
        .any(|value| value == "no_independent_recovery_replay"));
}

#[test]
fn bounded_cli_html_is_byte_deterministic_and_keeps_the_claim_boundary_visible() {
    let first = run("html", true);
    let second = run("html", true);
    assert_eq!(first.status.code(), Some(0));
    assert_eq!(second.status.code(), Some(0));
    assert!(first.stderr.is_empty());
    assert_eq!(first.stdout, second.stdout);
    let html = String::from_utf8(first.stdout).expect("UTF-8 HTML");
    assert!(html.starts_with("<!doctype html>\n"));
    assert!(html.contains("Authority boundary"));
    assert!(html.contains("no_design_or_release_authority"));
    assert!(html.contains("Independent member-force recovery replay"));
    assert!(html.contains("LC_AXIAL"));
}

#[test]
fn unknown_load_pattern_fails_without_result_authority() {
    let model = TempModel::frame_alpha();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["model", "analyze-frame3d"])
        .arg(&model.0)
        .args([
            "--load-pattern",
            "LC_UNKNOWN",
            "--result-id",
            "frame-alpha.unknown",
        ])
        .output()
        .expect("CLI runs");
    assert_eq!(output.status.code(), Some(1));
    let failure = json_output(&output);
    assert_eq!(failure["success"], false);
    assert_eq!(
        failure["claim_boundary"],
        "bounded_native_frame3d_analysis_failed_closed_without_result_authority"
    );
}
