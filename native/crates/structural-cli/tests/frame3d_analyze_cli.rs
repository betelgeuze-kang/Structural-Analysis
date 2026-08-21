use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use jsonschema::{Draft, JSONSchema};
use serde_json::{json, Value};
use structural_contracts::report_ir::sha256_bytes_identity;

static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);

struct TempModel(PathBuf);

struct TempBundle(PathBuf);

impl TempBundle {
    fn new() -> Self {
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        Self(std::env::temp_dir().join(format!(
            "structural-cli-workbench-bundle-{}-{sequence}",
            std::process::id()
        )))
    }
}

impl Drop for TempBundle {
    fn drop(&mut self) {
        let _removed = std::fs::remove_dir_all(&self.0);
    }
}

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

    fn load_combination() -> Self {
        let mut value: Value = serde_json::from_slice(
            &std::fs::read(source_fixture()).expect("tracked ModelIR fixture"),
        )
        .expect("fixture JSON");
        value["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
        value["load_combinations"] = json!([{
            "id": "COMB_CLI",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.2},
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": -0.4}
            ],
            "source_id": null,
            "extensions": {}
        }]);
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-frame3d-combination-{}-{sequence}.json",
            std::process::id()
        ));
        std::fs::write(&path, serde_json::to_vec(&value).expect("JSON"))
            .expect("temporary combination ModelIR");
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
    assert_eq!(
        result.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&result.stdout)
    );
    let result = json_output(&result);
    assert_eq!(
        result["schema_version"],
        "structural-native-linear-frame3d-result-ir.v1"
    );
    assert_eq!(result["bindings"]["load_pattern_id"], "LC_AXIAL");
    assert_eq!(result["bindings"]["load_combination_id"], Value::Null);
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
    assert_eq!(
        result["claim_boundary"]["self_weight_standard_gravity"],
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
    assert_eq!(report["summary"]["load_pattern_id"], "LC_AXIAL");
    assert_eq!(report["summary"]["load_combination_id"], Value::Null);
    let limitations = report["limitations"].as_array().expect("fixed limitations");
    assert!(limitations.iter().any(
        |value| value == "load_scope_nodal_uniform_self_weight_and_nested_linear_combinations"
    ));
    assert!(limitations
        .iter()
        .any(|value| value == "no_nonuniform_or_member_point_load"));
    assert!(!limitations
        .iter()
        .any(|value| value == "no_independent_recovery_replay"));
}

#[test]
fn bounded_cli_selects_and_binds_one_linear_load_combination() {
    let model = TempModel::load_combination();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args(["model", "analyze-frame3d"])
        .arg(&model.0)
        .args([
            "--load-combination",
            "COMB_CLI",
            "--result-id",
            "frame-alpha.COMB_CLI",
        ])
        .output()
        .expect("CLI runs");
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let result = json_output(&output);
    assert_eq!(result["bindings"]["load_pattern_id"], Value::Null);
    assert_eq!(result["bindings"]["load_combination_id"], "COMB_CLI");
    assert_eq!(
        result["claim_boundary"]["linear_load_combination_superposition"],
        true
    );
    assert_eq!(result["gates"]["global_resultant_gate_passed"], true);
    assert_eq!(result["gates"]["independent_recovery_replay_passed"], true);
}

#[test]
fn bounded_cli_html_is_byte_deterministic_and_keeps_the_claim_boundary_visible() {
    let first = run("html", true);
    let second = run("html", true);
    assert_eq!(
        first.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&first.stdout)
    );
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
fn workbench_bundle_publishes_complete_hash_bound_artifacts_without_overwrite() {
    let model = TempModel::frame_alpha();
    let bundle = TempBundle::new();
    let run_bundle = || {
        Command::new(env!("CARGO_BIN_EXE_structural-cli"))
            .args(["model", "analyze-frame3d"])
            .arg(&model.0)
            .args([
                "--load-pattern",
                "LC_AXIAL",
                "--result-id",
                "frame-alpha.LC_AXIAL",
                "--output",
                "workbench-bundle",
                "--report-id",
                "frame-alpha.LC_AXIAL.report",
                "--output-dir",
            ])
            .arg(&bundle.0)
            .output()
            .expect("CLI bundle runs")
    };

    let first = run_bundle();
    assert_eq!(
        first.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&first.stdout)
    );
    let manifest_bytes =
        std::fs::read(bundle.0.join("manifest.json")).expect("completion manifest");
    assert_eq!(first.stdout, [manifest_bytes.as_slice(), b"\n"].concat());
    let manifest: Value = serde_json::from_slice(&manifest_bytes).expect("manifest JSON");
    let schema: Value = serde_json::from_slice(
        &std::fs::read(repository_root().join(
            "native/crates/structural-contracts/schemas/linear_frame3d_workbench_bundle_v1.schema.json",
        ))
        .expect("tracked Workbench bundle schema"),
    )
    .expect("Workbench bundle schema JSON");
    let validator = JSONSchema::options()
        .with_draft(Draft::Draft202012)
        .compile(&schema)
        .expect("Workbench bundle schema compiles");
    assert!(validator.is_valid(&manifest));
    assert_eq!(
        manifest["schema_version"],
        "structural-native-linear-frame3d-workbench-bundle.v1"
    );
    assert_eq!(manifest["status"], "complete");
    assert_eq!(
        manifest["claim_boundary"],
        "completed_no_overwrite_cli_artifact_bundle_not_job_or_workbench_execution_authority"
    );

    for (key, filename) in [
        ("model_ir", "model-ir.json"),
        ("result_ir", "result-ir.json"),
        ("report_ir", "report-ir.json"),
        ("html", "report.html"),
    ] {
        let bytes = std::fs::read(bundle.0.join(filename)).expect("published artifact");
        assert_eq!(manifest["artifacts"][key]["path"], filename);
        assert_eq!(
            manifest["artifacts"][key]["byte_length"],
            u64::try_from(bytes.len()).expect("bounded byte length")
        );
        assert_eq!(
            manifest["artifacts"][key]["content_hash"],
            sha256_bytes_identity(&bytes)
        );
    }
    let result: Value =
        serde_json::from_slice(&std::fs::read(bundle.0.join("result-ir.json")).expect("ResultIR"))
            .expect("ResultIR JSON");
    let report: Value =
        serde_json::from_slice(&std::fs::read(bundle.0.join("report-ir.json")).expect("ReportIR"))
            .expect("ReportIR JSON");
    assert_eq!(
        manifest["artifacts"]["model_ir"]["content_hash"],
        manifest["bindings"]["model_content_hash"]
    );
    assert_eq!(manifest["bindings"]["result_hash"], result["result_hash"]);
    assert_eq!(manifest["bindings"]["report_hash"], report["report_hash"]);

    let second = run_bundle();
    assert_eq!(second.status.code(), Some(1));
    assert_eq!(
        json_output(&second)["issues"][0]["code"],
        "bundle_output_exists"
    );
    assert_eq!(
        std::fs::read(bundle.0.join("manifest.json")).expect("unchanged manifest"),
        manifest_bytes
    );
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
