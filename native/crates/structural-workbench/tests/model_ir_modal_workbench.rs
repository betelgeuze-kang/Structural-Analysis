use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::model_modal_product::{
    build_model_ir_modal_analysis_request_v1, ModelIrModalAnalysisRequestV1, ModelIrModalBackendV1,
    MODEL_IR_MODAL_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::spectral_product::SpectralGeneralizedEigenConfigV1;
use structural_workbench::{ModelIrModalWorkbench, ModelIrModalWorkbenchStageV1};

const PRODUCT_FILES: [&str; 11] = [
    "assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mmcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "model-ir.json",
    "model-modal-request.json",
    "report-ir.json",
    "report.md",
    "result-ir.json",
    "run-receipt.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-modal-workbench-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn model_bytes() -> Vec<u8> {
    fs::read(repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"))
        .expect("model fixture")
}

fn request_bytes(model_bytes: &[u8], load_pattern: &str) -> Vec<u8> {
    request_bytes_with_content_hash(model_bytes, load_pattern, None)
}

fn request_bytes_with_content_hash(
    model_bytes: &[u8],
    load_pattern: &str,
    content_hash: Option<&str>,
) -> Vec<u8> {
    let model = parse_model_ir_v2(model_bytes).expect("strict ModelIR");
    build_model_ir_modal_analysis_request_v1(ModelIrModalAnalysisRequestV1 {
        schema_version: MODEL_IR_MODAL_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_modal".to_owned(),
        case_id: "frame-cantilever-modal-workbench".to_owned(),
        backend: ModelIrModalBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: content_hash.unwrap_or(model.content_hash()).to_owned(),
            semantic_hash: model.semantic_hash().to_owned(),
            provenance_hash: model.provenance_hash().to_owned(),
        },
        assembly_load_pattern_id: load_pattern.to_owned(),
        config: SpectralGeneralizedEigenConfigV1 {
            mode_count: 3,
            maximum_sweeps: 4_096,
            symmetry_relative_tolerance: 1e-12,
            positive_semidefinite_relative_tolerance: 1e-12,
            mode_relative_tolerance: 1e-10,
            cluster_relative_tolerance: 1e-9,
            residual_relative_tolerance: 1e-9,
            orthogonality_tolerance: 1e-9,
            eigensolver_relative_tolerance: 1e-12,
        },
    })
    .expect("modal request")
    .canonical_bytes()
    .to_vec()
}

fn rewrite_self_hash(path: &Path, field: &str, mutate: impl FnOnce(&mut Value)) {
    let mut value: Value =
        serde_json::from_slice(&fs::read(path).expect("self-hashed JSON")).expect("strict JSON");
    value.as_object_mut().expect("JSON object").remove(field);
    mutate(&mut value);
    let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned JSON");
    value.as_object_mut().expect("JSON object").insert(
        field.to_owned(),
        Value::String(sha256_identity(unsigned.as_bytes())),
    );
    fs::write(
        path,
        canonicalize_model_ir_v2(&value).expect("canonical signed JSON"),
    )
    .expect("rewrite self-hashed JSON");
}

#[test]
fn durable_modal_workbench_reopens_every_stage_and_reports_exact_restart() {
    let parent = temporary_root("stages");
    fs::create_dir_all(&parent).expect("temporary parent");
    let workspace = parent.join("workspace");
    let model = model_bytes();
    let request = request_bytes(&model, "LC_WEAK");

    let workbench =
        ModelIrModalWorkbench::initialize(&workspace, &model, &request).expect("modal import");
    assert_eq!(workbench.stage(), ModelIrModalWorkbenchStageV1::Imported);
    assert_eq!(
        ModelIrModalWorkbench::open(&workspace)
            .expect("reopen import")
            .stage(),
        ModelIrModalWorkbenchStageV1::Imported
    );

    let mut workbench = ModelIrModalWorkbench::open(&workspace).expect("open import");
    workbench.validate().expect("modal validation");
    assert_eq!(
        ModelIrModalWorkbench::open(&workspace)
            .expect("reopen validation")
            .stage(),
        ModelIrModalWorkbenchStageV1::Validated
    );
    let mut workbench = ModelIrModalWorkbench::open(&workspace).expect("open validation");
    workbench.run().expect("direct modal run");
    assert_eq!(
        ModelIrModalWorkbench::open(&workspace)
            .expect("reopen direct")
            .stage(),
        ModelIrModalWorkbenchStageV1::Direct
    );
    let mut workbench = ModelIrModalWorkbench::open(&workspace).expect("open direct");
    workbench.resume().expect("modal checkpoint resume");
    assert_eq!(
        ModelIrModalWorkbench::open(&workspace)
            .expect("reopen resume")
            .stage(),
        ModelIrModalWorkbenchStageV1::Resumed
    );
    for file in PRODUCT_FILES {
        assert_eq!(
            fs::read(workspace.join("03-run").join(file)).expect("direct artifact"),
            fs::read(workspace.join("04-resume").join(file)).expect("resumed artifact"),
            "restart drifted: {file}"
        );
    }

    let mut workbench = ModelIrModalWorkbench::open(&workspace).expect("open resume");
    workbench.report().expect("localized modal report");
    let reopened = ModelIrModalWorkbench::open(&workspace).expect("reopen report");
    assert_eq!(reopened.stage(), ModelIrModalWorkbenchStageV1::Reported);
    let inspect: Value = serde_json::from_str(&reopened.inspect_json().expect("inspect JSON"))
        .expect("decode inspect JSON");
    assert_eq!(inspect["next_action"], "complete");
    assert!(inspect["external_comparison"].is_null());
    assert!(inspect["engineering_verdict"].is_null());
    assert_eq!(inspect["workflow"].as_array().expect("workflow").len(), 5);
    let english = fs::read_to_string(
        workspace
            .join("06-report")
            .join("modal-result-view.en-US.txt"),
    )
    .expect("English report");
    let korean = fs::read_to_string(
        workspace
            .join("06-report")
            .join("modal-result-view.ko-KR.txt"),
    )
    .expect("Korean report");
    assert!(english.contains("Displayed modes: 1-3 / 3"));
    assert!(korean.contains("표시 모드: 1-3 / 3"));
    let _ = fs::remove_dir_all(parent);
}

#[test]
fn modal_workbench_reconciles_atomic_stage_and_rejects_checkpoint_tamper() {
    let parent = temporary_root("reconcile-tamper");
    fs::create_dir_all(&parent).expect("temporary parent");
    let model = model_bytes();
    let request = request_bytes(&model, "LC_WEAK");

    let reconcile = parent.join("reconcile");
    let mut workbench =
        ModelIrModalWorkbench::initialize(&reconcile, &model, &request).expect("modal import");
    workbench.validate().expect("modal validation");
    let lagging_session = fs::read(reconcile.join("workbench-session.json")).expect("session");
    workbench.run().expect("direct run");
    fs::write(reconcile.join("workbench-session.json"), lagging_session).expect("simulate crash");
    assert_eq!(
        ModelIrModalWorkbench::open(&reconcile)
            .expect("reconcile atomic stage")
            .stage(),
        ModelIrModalWorkbenchStageV1::Direct
    );

    let tampered = parent.join("tampered");
    let mut workbench =
        ModelIrModalWorkbench::initialize(&tampered, &model, &request).expect("modal import");
    workbench.validate().expect("modal validation");
    workbench.run().expect("direct run");
    let checkpoint = tampered.join("03-run").join("checkpoint.mmcp");
    let mut bytes = fs::read(&checkpoint).expect("checkpoint");
    let index = bytes.len() / 2;
    bytes[index] ^= 1;
    fs::write(&checkpoint, bytes).expect("tamper checkpoint");
    assert!(ModelIrModalWorkbench::open(&tampered).is_err());
    assert!(!tampered.join("04-resume").exists());

    let semantic = parent.join("semantic-tamper");
    let mut workbench =
        ModelIrModalWorkbench::initialize(&semantic, &model, &request).expect("modal import");
    workbench.validate().expect("modal validation");
    rewrite_self_hash(
        &semantic.join("02-validate").join("validation-receipt.json"),
        "receipt_hash",
        |value| value["active_dof_count"] = Value::from(1_u64),
    );
    assert!(ModelIrModalWorkbench::open(&semantic).is_err());
    assert!(!semantic.join("03-run").exists());

    let mismatched = parent.join("mismatched");
    let other_request = request_bytes_with_content_hash(
        &model,
        "LC_WEAK",
        Some("sha256:0000000000000000000000000000000000000000000000000000000000000000"),
    );
    assert!(ModelIrModalWorkbench::initialize(&mismatched, &model, &other_request).is_err());
    assert!(!mismatched.exists());
    let _ = fs::remove_dir_all(parent);
}

#[test]
fn clean_environment_cli_workflow_is_durable_and_source_read_only() {
    let parent = temporary_root("cli");
    fs::create_dir_all(&parent).expect("temporary parent");
    let model_path = parent.join("model.json");
    let request_path = parent.join("request.json");
    let workspace = parent.join("workspace");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model input");
    fs::write(&request_path, request_bytes(&model, "LC_WEAK")).expect("request input");
    let before_model = fs::read(&model_path).expect("model before");
    let before_request = fs::read(&request_path).expect("request before");

    let output = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            OsString::from("workflow-model-modal"),
            model_path.as_os_str().to_owned(),
            request_path.as_os_str().to_owned(),
            OsString::from("--workspace"),
            workspace.as_os_str().to_owned(),
        ])
        .output()
        .expect("modal Workbench CLI");
    assert!(
        output.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let session: Value = serde_json::from_slice(&output.stdout).expect("session JSON");
    assert_eq!(session["stage"], "reported");
    assert_eq!(session["analysis_profile"], "model_ir_modal_cpu_v1");
    assert_eq!(fs::read(&model_path).expect("model after"), before_model);
    assert_eq!(
        fs::read(&request_path).expect("request after"),
        before_request
    );
    let reopened = ModelIrModalWorkbench::open(&workspace).expect("open CLI workspace");
    assert_eq!(reopened.stage(), ModelIrModalWorkbenchStageV1::Reported);
    let _ = fs::remove_dir_all(parent);
}
