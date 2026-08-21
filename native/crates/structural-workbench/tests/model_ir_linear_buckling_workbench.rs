use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::{
    execute_model_ir_linear_buckling_analysis, publish_model_ir_linear_buckling_analysis,
};
use structural_contracts::model_buckling_product::{
    build_model_ir_linear_buckling_analysis_request_v1,
    parse_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
    ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::sparse_product::SparseLinearConfigV1;
use structural_contracts::spectral_product::{
    parse_dense_spectral_result_ir_v1, SpectralGeneralizedEigenConfigV1,
};
use structural_workbench::{
    create_model_buckling_analysis_request, render_model_ir_linear_buckling_result_view_directory,
    ModelIrLinearBucklingWorkbench, ModelIrLinearBucklingWorkbenchStageV1, WorkbenchReportLocaleV1,
};

const PRODUCT_FILES: [&str; 18] = [
    "buckling-assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mbcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "generated-reference-request.json",
    "model-buckling-request.json",
    "model-ir.json",
    "reference-assembly-receipt.json",
    "reference-checkpoint.mlpcp",
    "reference-checkpoint.pcgcp",
    "reference-reaction-ir.json",
    "reference-recovery-ir.json",
    "reference-result-ir.json",
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
        "structural-buckling-workbench-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn compression_model() -> structural_contracts::model_ir::ModelIrV2Document {
    let source = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("fixture");
    let source = parse_model_ir_v2(&source).expect("strict source");
    let mut value = source.value().clone();
    value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(-100_000.0);
    parse_model_ir_v2(&serde_json::to_vec(&value).expect("compression JSON"))
        .expect("strict compression model")
}

fn linear_config() -> SparseLinearConfigV1 {
    SparseLinearConfigV1 {
        max_iterations: 64,
        absolute_residual_tolerance: 1e-12,
        relative_residual_tolerance: 1e-12,
        maximum_increment: 0.0,
    }
}

fn buckling_config() -> SpectralGeneralizedEigenConfigV1 {
    SpectralGeneralizedEigenConfigV1 {
        mode_count: 2,
        maximum_sweeps: 4_096,
        symmetry_relative_tolerance: 1e-12,
        positive_semidefinite_relative_tolerance: 1e-12,
        mode_relative_tolerance: 1e-10,
        cluster_relative_tolerance: 1e-9,
        residual_relative_tolerance: 1e-9,
        orthogonality_tolerance: 1e-9,
        eigensolver_relative_tolerance: 1e-12,
    }
}

fn request_bytes(model: &structural_contracts::model_ir::ModelIrV2Document) -> Vec<u8> {
    build_model_ir_linear_buckling_analysis_request_v1(ModelIrLinearBucklingAnalysisRequestV1 {
        schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_linear_buckling".to_owned(),
        case_id: "frame-cantilever-buckling-workbench".to_owned(),
        backend: ModelIrLinearBucklingBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: model.content_hash().to_owned(),
            semantic_hash: model.semantic_hash().to_owned(),
            provenance_hash: model.provenance_hash().to_owned(),
        },
        reference_load_pattern_id: "LC_AXIAL".to_owned(),
        reference_linear_config: linear_config(),
        buckling_config: buckling_config(),
    })
    .expect("buckling request")
    .canonical_bytes()
    .to_vec()
}

fn publish_result(directory: &Path) {
    let model = compression_model();
    let request = request_bytes(&model);
    let outcome = execute_model_ir_linear_buckling_analysis(model.canonical_bytes(), &request)
        .expect("buckling product");
    publish_model_ir_linear_buckling_analysis(directory, &outcome).expect("publish product");
}

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let expected = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned.as_object_mut().expect("object").remove(field);
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical unsigned value");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

fn verify_view_hash(text: &str, label: &str) {
    let marker = format!("{label}: ");
    let start = text.rfind(&marker).expect("view hash field");
    let expected = text[start + marker.len()..].trim_end();
    assert_eq!(expected, sha256_identity(&text.as_bytes()[..start]));
}

#[test]
#[allow(clippy::too_many_lines)] // One test binds library authoring, receipt fields and clean CLI replay.
fn request_authoring_runs_full_preflight_and_cli_is_deterministic() {
    let model = compression_model();
    let first = create_model_buckling_analysis_request(
        model.canonical_bytes(),
        "frame-workbench-buckling",
        "LC_AXIAL",
        linear_config(),
        buckling_config(),
    )
    .expect("preflighted request");
    let second = create_model_buckling_analysis_request(
        model.canonical_bytes(),
        "frame-workbench-buckling",
        "LC_AXIAL",
        linear_config(),
        buckling_config(),
    )
    .expect("repeat request");
    assert_eq!(first, second);
    let request =
        parse_model_ir_linear_buckling_analysis_request_v1(first.analysis_request_json.as_bytes())
            .expect("strict request");
    let result = execute_model_ir_linear_buckling_analysis(
        model.canonical_bytes(),
        request.canonical_bytes(),
    )
    .expect("authored request execution");
    assert_eq!(
        parse_dense_spectral_result_ir_v1(result.result_ir_json().as_bytes())
            .expect("buckling ResultIR")
            .result()
            .summary
            .mode_count,
        2
    );
    let receipt: Value = serde_json::from_str(&first.receipt_json).expect("receipt JSON");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-model-linear-buckling-request-create-receipt.v1"
    );
    assert_eq!(
        receipt["native_reference_pcg_recovery_reaction_preflight_executed"],
        true
    );
    assert_eq!(receipt["native_v1_15_k_kg_preflight_executed"], true);
    assert_eq!(receipt["dense_buckling_preflight_executed"], true);
    assert_eq!(receipt["product_publication_started"], false);
    assert_eq!(receipt["active_dof_count"], 6);
    assert!(receipt["critical_load_factor"].as_f64().expect("factor") > 0.0);
    verify_self_hash(&receipt, "receipt_hash");

    let root = temporary_root("request-cli");
    fs::create_dir_all(&root).expect("temporary root");
    let model_path = root.join("model.json");
    fs::write(&model_path, model.canonical_bytes()).expect("model input");
    for output in [root.join("first"), root.join("second")] {
        let execution = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
            .env_clear()
            .env("PATH", "/nonexistent")
            .args([
                "model-create-buckling-analysis-request",
                model_path.to_str().expect("model path"),
                "--case",
                "frame-workbench-buckling",
                "--reference-load-pattern",
                "LC_AXIAL",
                "--max-iterations",
                "64",
                "--absolute-residual-tolerance",
                "1e-12",
                "--relative-residual-tolerance",
                "1e-12",
                "--maximum-increment",
                "0",
                "--mode-count",
                "2",
                "--maximum-sweeps",
                "4096",
                "--symmetry-relative-tolerance",
                "1e-12",
                "--positive-semidefinite-relative-tolerance",
                "1e-12",
                "--mode-relative-tolerance",
                "1e-10",
                "--cluster-relative-tolerance",
                "1e-9",
                "--residual-relative-tolerance",
                "1e-9",
                "--orthogonality-tolerance",
                "1e-9",
                "--eigensolver-relative-tolerance",
                "1e-12",
                "--output-dir",
                output.to_str().expect("output path"),
            ])
            .output()
            .expect("Workbench request CLI");
        assert!(
            execution.status.success(),
            "stderr={}",
            String::from_utf8_lossy(&execution.stderr)
        );
    }
    for file in ["analysis-request.json", "request-receipt.json"] {
        assert_eq!(
            fs::read(root.join("first").join(file)).expect("first artifact"),
            fs::read(root.join("second").join(file)).expect("second artifact")
        );
    }

    let mut tension = model.value().clone();
    tension["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(100_000.0);
    let tension = parse_model_ir_v2(&serde_json::to_vec(&tension).expect("tension JSON"))
        .expect("strict tension model");
    assert!(create_model_buckling_analysis_request(
        tension.canonical_bytes(),
        "tension",
        "LC_AXIAL",
        linear_config(),
        buckling_config(),
    )
    .is_err());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn result_view_is_verified_localized_read_only_and_fail_closed() {
    let root = temporary_root("view");
    fs::create_dir_all(&root).expect("temporary root");
    let result = root.join("result");
    publish_result(&result);
    let before = PRODUCT_FILES
        .iter()
        .map(|file| fs::read(result.join(file)).expect("artifact"))
        .collect::<Vec<_>>();
    let english = render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::EnUs,
        1,
        16,
    )
    .expect("English view");
    assert_eq!(
        english,
        render_model_ir_linear_buckling_result_view_directory(
            &result,
            WorkbenchReportLocaleV1::EnUs,
            1,
            16,
        )
        .expect("repeat view")
    );
    let korean = render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::KoKr,
        2,
        1,
    )
    .expect("Korean view");
    assert!(english.contains("0001"));
    assert!(english.contains("0002"));
    assert!(english.contains("Critical load factor"));
    assert!(english.contains("cpu / fp64 / fallback 0"));
    assert!(korean.contains("0002"));
    verify_view_hash(&english, "View hash");
    verify_view_hash(&korean, "보기 해시");
    let cli = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "buckling-result-view",
            result.to_str().expect("result path"),
        ])
        .output()
        .expect("view CLI");
    assert!(
        cli.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&cli.stderr)
    );
    assert_eq!(cli.stdout, english.as_bytes());
    let after = PRODUCT_FILES
        .iter()
        .map(|file| fs::read(result.join(file)).expect("artifact"))
        .collect::<Vec<_>>();
    assert_eq!(before, after);

    fs::write(result.join("extra.txt"), b"unbound").expect("extra file");
    assert!(render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::EnUs,
        1,
        1,
    )
    .is_err());
    fs::remove_file(result.join("extra.txt")).expect("remove extra");
    let checkpoint = result.join("checkpoint.mbcp");
    let mut bytes = fs::read(&checkpoint).expect("checkpoint");
    let midpoint = bytes.len() / 2;
    bytes[midpoint] ^= 1;
    fs::write(checkpoint, bytes).expect("tamper checkpoint");
    assert!(render_model_ir_linear_buckling_result_view_directory(
        &result,
        WorkbenchReportLocaleV1::EnUs,
        1,
        1,
    )
    .is_err());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn durable_workbench_reopens_every_stage_and_exactly_resumes() {
    let root = temporary_root("durable");
    fs::create_dir_all(&root).expect("temporary root");
    let workspace = root.join("workspace");
    let model = compression_model();
    let request = request_bytes(&model);
    let workbench =
        ModelIrLinearBucklingWorkbench::initialize(&workspace, model.canonical_bytes(), &request)
            .expect("buckling import");
    assert_eq!(
        workbench.stage(),
        ModelIrLinearBucklingWorkbenchStageV1::Imported
    );
    let mut workbench = ModelIrLinearBucklingWorkbench::open(&workspace).expect("open import");
    workbench.validate().expect("validate");
    assert_eq!(
        ModelIrLinearBucklingWorkbench::open(&workspace)
            .expect("reopen validate")
            .stage(),
        ModelIrLinearBucklingWorkbenchStageV1::Validated
    );
    let mut workbench = ModelIrLinearBucklingWorkbench::open(&workspace).expect("open validate");
    workbench.run().expect("direct run");
    let mut workbench = ModelIrLinearBucklingWorkbench::open(&workspace).expect("open direct");
    workbench.resume().expect("resume");
    for file in PRODUCT_FILES {
        assert_eq!(
            fs::read(workspace.join("03-run").join(file)).expect("direct artifact"),
            fs::read(workspace.join("04-resume").join(file)).expect("resumed artifact"),
            "restart drifted: {file}"
        );
    }
    let mut workbench = ModelIrLinearBucklingWorkbench::open(&workspace).expect("open resume");
    workbench.report().expect("report");
    let reopened = ModelIrLinearBucklingWorkbench::open(&workspace).expect("open report");
    assert_eq!(
        reopened.stage(),
        ModelIrLinearBucklingWorkbenchStageV1::Reported
    );
    let inspect: Value =
        serde_json::from_str(&reopened.inspect_json().expect("inspect")).expect("inspect JSON");
    assert_eq!(inspect["next_action"], "complete");
    assert!(inspect["external_comparison"].is_null());
    assert!(inspect["engineering_verdict"].is_null());
    assert!(
        fs::read_to_string(workspace.join("06-report/buckling-result-view.en-US.txt"))
            .expect("English report")
            .contains("Critical load factor")
    );

    let tampered = root.join("tampered");
    let mut workbench =
        ModelIrLinearBucklingWorkbench::initialize(&tampered, model.canonical_bytes(), &request)
            .expect("tampered import");
    workbench.validate().expect("tampered validate");
    workbench.run().expect("tampered direct");
    let path = tampered.join("03-run/checkpoint.mbcp");
    let mut bytes = fs::read(&path).expect("checkpoint");
    let midpoint = bytes.len() / 2;
    bytes[midpoint] ^= 1;
    fs::write(path, bytes).expect("tamper checkpoint");
    assert!(ModelIrLinearBucklingWorkbench::open(&tampered).is_err());
    assert!(!tampered.join("04-resume").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn clean_environment_cli_workflow_is_durable_and_source_read_only() {
    let root = temporary_root("workflow-cli");
    fs::create_dir_all(&root).expect("temporary root");
    let model = compression_model();
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let workspace = root.join("workspace");
    fs::write(&model_path, model.canonical_bytes()).expect("model input");
    fs::write(&request_path, request_bytes(&model)).expect("request input");
    let before_model = fs::read(&model_path).expect("model before");
    let before_request = fs::read(&request_path).expect("request before");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            OsString::from("workflow-model-buckling"),
            model_path.as_os_str().to_owned(),
            request_path.as_os_str().to_owned(),
            OsString::from("--workspace"),
            workspace.as_os_str().to_owned(),
        ])
        .output()
        .expect("buckling workflow CLI");
    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let session: Value = serde_json::from_slice(&output.stdout).expect("session JSON");
    assert_eq!(session["stage"], "reported");
    assert_eq!(
        session["analysis_profile"],
        "model_ir_linear_buckling_cpu_v1"
    );
    assert_eq!(fs::read(&model_path).expect("model after"), before_model);
    assert_eq!(
        fs::read(&request_path).expect("request after"),
        before_request
    );
    assert_eq!(
        ModelIrLinearBucklingWorkbench::open(&workspace)
            .expect("open workspace")
            .stage(),
        ModelIrLinearBucklingWorkbenchStageV1::Reported
    );
    let status = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "buckling-status",
            "--workspace",
            workspace.to_str().expect("workspace"),
        ])
        .output()
        .expect("status CLI");
    assert!(status.status.success());
    assert_eq!(status.stdout, output.stdout);
    let _ = fs::remove_dir_all(root);
}
