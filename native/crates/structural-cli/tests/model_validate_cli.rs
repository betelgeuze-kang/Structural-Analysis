use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(0);

struct TempModel(PathBuf);

impl TempModel {
    fn write(bytes: &[u8]) -> Self {
        let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-model-validate-{}-{sequence}.json",
            std::process::id()
        ));
        std::fs::write(&path, bytes).expect("temporary ModelIR");
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

fn fixture_value() -> Value {
    serde_json::from_slice(
        &std::fs::read(
            repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("fixture bytes"),
    )
    .expect("fixture JSON")
}

fn run(path: &Path, require_analysis_ready: bool) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
    command.args(["model", "validate"]).arg(path);
    if require_analysis_ready {
        command.arg("--require-analysis-ready");
    }
    command.output().expect("CLI runs")
}

fn report(output: &Output) -> Value {
    assert!(
        output.stderr.is_empty(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("one JSON report on stdout")
}

#[test]
fn tracked_model_is_ready_and_emits_the_cpp_versioned_report() {
    let path = repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let output = run(&path, true);
    assert_eq!(output.status.code(), Some(0));
    let report = report(&output);
    assert_eq!(
        report["schema_version"],
        "structural-model-ir-cpp-validation.v1"
    );
    assert_eq!(report["contract_valid"], true);
    assert_eq!(report["analysis_ready"], true);
    assert_eq!(
        report["claim_boundary"],
        "model_ir_contract_validation_not_solver_or_backend_readiness"
    );
}

#[test]
fn blocker_is_success_by_default_and_failure_only_under_explicit_readiness_policy() {
    let mut value = fixture_value();
    value["unsupported_features"] = json!([{
        "feature_id": "feature.blocked",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Blocked for CLI policy test.",
        "extensions": {}
    }]);
    let model = TempModel::write(&serde_json::to_vec(&value).expect("JSON"));

    let default = run(&model.0, false);
    assert_eq!(default.status.code(), Some(0));
    assert_eq!(report(&default)["analysis_ready"], false);

    let required = run(&model.0, true);
    assert_eq!(required.status.code(), Some(2));
    let required = report(&required);
    assert_eq!(required["contract_valid"], true);
    assert_eq!(required["analysis_ready"], false);
}

#[test]
fn semantic_and_wire_invalidity_fail_at_their_own_boundaries() {
    let mut value = fixture_value();
    value["provenance"]["unit_scales_to_si"]["length_to_m"] = json!(10.0);
    let semantic = TempModel::write(&serde_json::to_vec(&value).expect("JSON"));
    let output = run(&semantic.0, false);
    assert_eq!(output.status.code(), Some(2));
    let semantic_report = report(&output);
    assert_eq!(
        semantic_report["schema_version"],
        "structural-model-ir-cpp-validation.v1"
    );
    assert_eq!(semantic_report["schema_valid"], true);
    assert_eq!(semantic_report["contract_valid"], false);

    let duplicate = TempModel::write(br#"{"id":"first","id":"second"}"#);
    let output = run(&duplicate.0, false);
    assert_eq!(output.status.code(), Some(2));
    let wire_report = report(&output);
    assert_eq!(
        wire_report["schema_version"],
        "structural-model-ir-rust-validation.v1"
    );
    assert_eq!(wire_report["schema_valid"], false);
    assert_eq!(
        wire_report["issues"][0]["code"],
        "model_ir_duplicate_json_key"
    );
}
