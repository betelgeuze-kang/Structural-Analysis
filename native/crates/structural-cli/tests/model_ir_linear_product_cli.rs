use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_cli::{
    execute_model_ir_linear_analysis, validate_model_ir_linear_analysis_compatibility,
};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::model_linear_reactions::{
    parse_model_ir_linear_reaction_result_ir_v1, verify_model_ir_linear_reaction_result_v1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
};
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{
    parse_sparse_linear_report_ir_v1, parse_sparse_linear_result_ir_v1,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-model-linear-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn run(arguments: &[&Path]) -> Output {
    let mut command = Command::new(binary());
    command.env_clear();
    command.env("PATH", "/nonexistent");
    for argument in arguments {
        command.arg(argument);
    }
    command.output().expect("run CLI")
}

fn text(value: &str) -> &Path {
    Path::new(value)
}

fn model_bytes() -> Vec<u8> {
    fs::read(repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"))
        .expect("ModelIR fixture")
}

fn request_bytes(max_iterations: u32) -> Vec<u8> {
    let bytes = fs::read(
        repository_root()
            .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"),
    )
    .expect("language-neutral request fixture");
    let mut value: Value = serde_json::from_slice(&bytes).expect("request fixture JSON");
    value["config"]["max_iterations"] = json!(max_iterations);
    serde_json::to_vec(&value).expect("request JSON")
}

fn combination_model_bytes() -> Vec<u8> {
    let mut value: Value = serde_json::from_slice(&model_bytes()).expect("ModelIR fixture JSON");
    value["load_combinations"] = json!([{
        "id": "COMBO_SERVICE",
        "index": 0,
        "combination_type": "linear",
        "terms": [
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ],
        "source_id": null,
        "extensions": {}
    }]);
    canonicalize_model_ir_v2(&value)
        .expect("canonical combination ModelIR")
        .into_bytes()
}

fn direct_combination_model_bytes() -> Vec<u8> {
    let mut value: Value = serde_json::from_slice(&model_bytes()).expect("ModelIR fixture JSON");
    value["load_combinations"] = json!([{
        "id": "COMBO_DIRECT",
        "index": 0,
        "combination_type": "linear",
        "terms": [
            {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
            {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
            {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
        ],
        "source_id": null,
        "extensions": {}
    }]);
    canonicalize_model_ir_v2(&value)
        .expect("canonical direct-combination ModelIR")
        .into_bytes()
}

fn nested_combination_model_bytes() -> Vec<u8> {
    let mut value: Value = serde_json::from_slice(&model_bytes()).expect("ModelIR fixture JSON");
    value["load_combinations"] = json!([
        {
            "id": "COMBO_BASE",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
            ],
            "source_id": null,
            "extensions": {}
        },
        {
            "id": "COMBO_NESTED",
            "index": 1,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
            ],
            "source_id": null,
            "extensions": {}
        }
    ]);
    canonicalize_model_ir_v2(&value)
        .expect("canonical nested-combination ModelIR")
        .into_bytes()
}

fn rebound_request_bytes(model: &[u8], selector_id: &str, max_iterations: u32) -> Vec<u8> {
    let document = parse_model_ir_v2(model).expect("strict rebound ModelIR");
    let mut value: Value =
        serde_json::from_slice(&request_bytes(max_iterations)).expect("request fixture JSON");
    value["model_identity"] = json!({
        "content_hash": document.content_hash(),
        "semantic_hash": document.semantic_hash(),
        "provenance_hash": document.provenance_hash(),
    });
    value["load_pattern_id"] = json!(selector_id);
    canonicalize_model_ir_v2(&value)
        .expect("canonical rebound request")
        .into_bytes()
}

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let hash = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned
        .as_object_mut()
        .expect("self-hashed object")
        .remove(field);
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical self-hash payload");
    assert_eq!(hash, sha256_identity(canonical.as_bytes()));
}

fn verify_receipt(directory: &Path, expected_status: &str) -> Value {
    let bytes = fs::read(directory.join("run-receipt.json")).expect("run receipt");
    let value: Value = serde_json::from_slice(&bytes).expect("run receipt JSON");
    assert_eq!(value["status"], expected_status);
    verify_self_hash(&value, "receipt_hash");
    for artifact in value["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let artifact_bytes = fs::read(directory.join(file)).expect("artifact bytes");
        assert_eq!(
            artifact["byte_length"].as_u64().expect("artifact length"),
            u64::try_from(artifact_bytes.len()).expect("bounded length")
        );
        assert_eq!(
            artifact["content_hash"].as_str().expect("artifact hash"),
            sha256_identity(&artifact_bytes)
        );
    }
    value
}

#[test]
fn compatibility_preflight_is_deterministic_and_uses_cpp_assembly() {
    let model = model_bytes();
    let request = request_bytes(100);
    let first = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("compatible typed ModelIR linear request");
    let second = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("deterministic compatibility preflight");
    assert_eq!(first, second);
    assert!(first.assembly_hash.starts_with("sha256:"));
    assert!(first.generated_request_hash.starts_with("sha256:"));

    let planar =
        fs::read(repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json"))
            .expect("unsupported planar ModelIR");
    let mut rebound: Value = serde_json::from_slice(&request).expect("request JSON");
    let planar_document =
        structural_contracts::model_ir::parse_model_ir_v2(&planar).expect("strict planar ModelIR");
    rebound["model_identity"] = json!({
        "content_hash": planar_document.content_hash(),
        "semantic_hash": planar_document.semantic_hash(),
        "provenance_hash": planar_document.provenance_hash(),
    });
    rebound["load_pattern_id"] = json!("LP1");
    let unsupported = serde_json::to_vec(&rebound).expect("rebound request");
    assert!(validate_model_ir_linear_analysis_compatibility(&planar, &unsupported).is_err());
}

#[test]
fn bounded_two_pattern_combination_executes_and_restarts_exactly() {
    let model = combination_model_bytes();
    let request = rebound_request_bytes(&model, "COMBO_SERVICE", 100);
    let first = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("bounded combination compatibility");
    let repeated = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("deterministic bounded combination compatibility");
    assert_eq!(first, repeated);

    let direct = execute_model_ir_linear_analysis(&model, &request, None, u32::MAX)
        .expect("bounded combination execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("combination recovery IR"),
    )
    .expect("combination recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_SERVICE");
    assert_eq!(recovery["load_pattern_index"], 0);
    assert_eq!(
        recovery["active_external_load"]
            .as_array()
            .expect("combination external load")
            .iter()
            .map(|value| value.as_f64().expect("finite external load"))
            .collect::<Vec<_>>(),
        vec![0.0, -12000.0, 5000.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(recovery["fallback_count"], 0);
    assert!(
        recovery["summary"]["active_residual_inf"]
            .as_f64()
            .expect("combination residual")
            <= 1.0e-8
    );

    let partial = execute_model_ir_linear_analysis(&model, &request, None, 0)
        .expect("initial combination checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &model,
        &request,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("resumed combination execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );
    assert_eq!(
        resumed.reaction_result_ir_json(),
        direct.reaction_result_ir_json()
    );
    assert_eq!(resumed.report_ir_json(), direct.report_ir_json());

    let direct_pattern_request = rebound_request_bytes(&model, "LC_WEAK", 100);
    let direct_pattern =
        execute_model_ir_linear_analysis(&model, &direct_pattern_request, None, u32::MAX)
            .expect("direct pattern remains executable beside a combination");
    let original =
        execute_model_ir_linear_analysis(&model_bytes(), &request_bytes(100), None, u32::MAX)
            .expect("original direct pattern execution");
    let direct_pattern_result = parse_sparse_linear_result_ir_v1(
        direct_pattern
            .result_ir_json()
            .expect("direct pattern ResultIR")
            .as_bytes(),
    )
    .expect("strict direct-pattern ResultIR");
    let original_result = parse_sparse_linear_result_ir_v1(
        original
            .result_ir_json()
            .expect("original ResultIR")
            .as_bytes(),
    )
    .expect("strict original ResultIR");
    assert_eq!(
        direct_pattern_result.result().solution,
        original_result.result().solution
    );
}

#[test]
fn bounded_three_pattern_direct_combination_executes_and_restarts_exactly() {
    let model = direct_combination_model_bytes();
    let request = rebound_request_bytes(&model, "COMBO_DIRECT", 100);
    let first = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("bounded direct-combination compatibility");
    let repeated = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("deterministic direct-combination compatibility");
    assert_eq!(first, repeated);

    let direct = execute_model_ir_linear_analysis(&model, &request, None, u32::MAX)
        .expect("bounded direct-combination execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("direct-combination recovery IR"),
    )
    .expect("direct-combination recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_DIRECT");
    assert_eq!(
        recovery["active_external_load"],
        json!([25000, -12000, 5000, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&model, &request, None, 0)
        .expect("initial direct-combination checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &model,
        &request,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("resumed direct-combination execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );
    assert_eq!(
        resumed.reaction_result_ir_json(),
        direct.reaction_result_ir_json()
    );
    assert_eq!(resumed.report_ir_json(), direct.report_ir_json());
}

#[test]
fn bounded_nested_combination_executes_and_restarts_exactly() {
    let model = nested_combination_model_bytes();
    let request = rebound_request_bytes(&model, "COMBO_NESTED", 100);
    let first = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("bounded nested-combination compatibility");
    let repeated = validate_model_ir_linear_analysis_compatibility(&model, &request)
        .expect("deterministic nested-combination compatibility");
    assert_eq!(first, repeated);

    let direct = execute_model_ir_linear_analysis(&model, &request, None, u32::MAX)
        .expect("bounded nested-combination execution");
    assert!(direct.is_complete());
    let recovery: Value = serde_json::from_str(
        direct
            .result_recovery_ir_json()
            .expect("nested-combination recovery IR"),
    )
    .expect("nested-combination recovery JSON");
    assert_eq!(recovery["load_pattern_id"], "COMBO_NESTED");
    assert_eq!(recovery["load_pattern_index"], 1);
    assert_eq!(
        recovery["active_external_load"],
        json!([25000, -6000, 2500, 0, 0, 0])
    );
    assert_eq!(recovery["fallback_count"], 0);

    let partial = execute_model_ir_linear_analysis(&model, &request, None, 0)
        .expect("initial nested-combination checkpoint");
    assert!(!partial.is_complete());
    let resumed = execute_model_ir_linear_analysis(
        &model,
        &request,
        Some(partial.checkpoint_bytes()),
        u32::MAX,
    )
    .expect("resumed nested-combination execution");
    assert!(resumed.is_complete());
    assert_eq!(resumed.result_ir_json(), direct.result_ir_json());
    assert_eq!(
        resumed.result_recovery_ir_json(),
        direct.result_recovery_ir_json()
    );
    assert_eq!(
        resumed.reaction_result_ir_json(),
        direct.reaction_result_ir_json()
    );
    assert_eq!(resumed.report_ir_json(), direct.report_ir_json());
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_environment_direct_and_real_iteration_resume_are_byte_identical() {
    let root = temporary_root("clean-env");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(100)).expect("request");
    let direct = root.join("direct");
    let partial = root.join("partial");
    let resumed = root.join("resumed");

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let direct_receipt = verify_receipt(&direct, "completed");
    assert!(direct_receipt["checkpoint"]["artifact_bytes"]
        .as_u64()
        .is_some());

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &partial,
        text("--iteration-budget"),
        text("1"),
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&partial, "active");
    assert!(partial.join("checkpoint.mlpcp").is_file());
    assert!(partial.join("checkpoint.pcgcp").is_file());
    assert!(!partial.join("result-ir.json").exists());
    assert!(!partial.join("result-recovery-ir.json").exists());
    assert!(!partial.join("reaction-result-ir.json").exists());

    let output = run(&[
        text("analysis"),
        text("model-linear-resume"),
        &model_path,
        &request_path,
        &partial.join("checkpoint.mlpcp"),
        text("--output-dir"),
        &resumed,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&resumed, "completed");

    for name in [
        "model-ir.json",
        "model-analysis-request.json",
        "assembly-receipt.json",
        "generated-sparse-request.json",
        "checkpoint.mlpcp",
        "model-checkpoint-receipt.json",
        "checkpoint.pcgcp",
        "checkpoint-receipt.json",
        "sparse-run-receipt.json",
        "result-ir.json",
        "result-recovery-ir.json",
        "reaction-result-ir.json",
        "report-ir.json",
        "report.md",
        "run-receipt.json",
    ] {
        assert_eq!(
            fs::read(direct.join(name)).expect("direct artifact"),
            fs::read(resumed.join(name)).expect("resumed artifact"),
            "artifact drift: {name}"
        );
    }

    let result = parse_sparse_linear_result_ir_v1(
        &fs::read(direct.join("result-ir.json")).expect("ResultIR"),
    )
    .expect("strict ResultIR");
    let report = parse_sparse_linear_report_ir_v1(
        &fs::read(direct.join("report-ir.json")).expect("ReportIR"),
    )
    .expect("strict ReportIR");
    assert_eq!(report.report().source_result_hash, result.result_hash());
    assert_eq!(result.result().backend_receipt.fallback_count, 0);
    assert_eq!(
        direct_receipt["artifacts"]
            .as_array()
            .expect("artifact inventory")
            .len(),
        14
    );

    let assembly: Value = serde_json::from_slice(
        &fs::read(direct.join("assembly-receipt.json")).expect("assembly receipt"),
    )
    .expect("assembly receipt JSON");
    verify_self_hash(&assembly, "assembly_hash");
    assert_eq!(direct_receipt["assembly_hash"], assembly["assembly_hash"]);

    let recovery: Value = serde_json::from_slice(
        &fs::read(direct.join("result-recovery-ir.json")).expect("recovery"),
    )
    .expect("recovery JSON");
    verify_self_hash(&recovery, "recovery_hash");
    assert_eq!(recovery["source_result_hash"], result.result_hash());
    assert_eq!(recovery["active_dof_indices"], json!([6, 7, 8, 9, 10, 11]));
    assert_eq!(
        recovery["active_internal_force"],
        recovery["same_state_jvp"]
    );
    assert_eq!(recovery["fallback_count"], 0);
    assert_eq!(
        recovery["units"]["global_displacement"],
        "translations_m_rotations_rad"
    );
    assert_eq!(
        recovery["coordinate_frame"]["frame3d_recovery"],
        "element_local"
    );
    assert!(
        recovery["summary"]["active_residual_inf"]
            .as_f64()
            .expect("residual")
            <= 1.0e-8
    );
    let recovery_document = parse_model_ir_linear_result_recovery_ir_v1(
        &fs::read(direct.join("result-recovery-ir.json")).expect("recovery bytes"),
    )
    .expect("strict recovery IR");
    verify_model_ir_linear_result_recovery_v1(&result, &recovery_document)
        .expect("recovery binds exact sparse result");
    let reaction_bytes =
        fs::read(direct.join("reaction-result-ir.json")).expect("reaction ResultIR");
    let reaction = parse_model_ir_linear_reaction_result_ir_v1(&reaction_bytes)
        .expect("strict reaction ResultIR");
    verify_model_ir_linear_reaction_result_v1(&result, &recovery_document, &reaction)
        .expect("reaction binds exact sparse result and recovery");
    assert_eq!(
        reaction.result().constrained_dof_indices,
        [0, 1, 2, 3, 4, 5]
    );
    assert_eq!(
        reaction.result().reactions,
        [0.0, 10_000.0, 0.0, 0.0, 0.0, 20_000.0]
    );
    assert_eq!(reaction.result().identity, result.result().identity);
    assert_eq!(
        reaction.result().source_recovery_hash,
        recovery_document.recovery_hash()
    );
    assert_eq!(reaction.result().backend_receipt.fallback_count, 0);
    assert_eq!(reaction.result().backend_receipt.abi_version, "0x0001000e");
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn every_checkpoint_byte_and_request_drift_fail_before_resume() {
    let model = model_bytes();
    let request = request_bytes(100);
    let partial = execute_model_ir_linear_analysis(&model, &request, None, 1)
        .expect("one real PCG iteration");
    assert!(!partial.is_complete());
    assert_eq!(
        partial.checkpoint_receipt().schema_version,
        "structural-model-ir-linear-checkpoint-receipt.v1"
    );
    let checkpoint = partial.checkpoint_bytes();
    for index in 0..checkpoint.len() {
        let mut corrupt = checkpoint.to_vec();
        corrupt[index] ^= 1;
        let error = execute_model_ir_linear_analysis(&model, &request, Some(&corrupt), u32::MAX)
            .expect_err("every single-byte mutation fails");
        assert!(
            matches!(
                error,
                structural_cli::ModelIrLinearProductError::Runtime(ref value)
                    if value.code == 1301
            ),
            "mutation {index} returned {error}"
        );
    }

    let drifted = request_bytes(101);
    let error = execute_model_ir_linear_analysis(&model, &drifted, Some(checkpoint), u32::MAX)
        .expect_err("configuration drift fails");
    assert!(matches!(
        error,
        structural_cli::ModelIrLinearProductError::Runtime(ref value) if value.code == 1301
    ));
}

#[test]
fn numerical_failure_publishes_both_terminal_checkpoints_without_result_files() {
    let root = temporary_root("numerical-failure");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(1)).expect("request");
    let failed = root.join("failed");

    let output = run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &failed,
    ]);
    assert!(!output.status.success());
    let receipt = verify_receipt(&failed, "failed");
    assert_eq!(receipt["solver_status"], "nonconvergence");
    assert!(failed.join("checkpoint.mlpcp").is_file());
    assert!(failed.join("checkpoint.pcgcp").is_file());
    assert!(!failed.join("result-ir.json").exists());
    assert!(!failed.join("result-recovery-ir.json").exists());
    assert!(!failed.join("reaction-result-ir.json").exists());
    assert!(!failed.join("report-ir.json").exists());
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn symlink_and_existing_destination_fail_without_partial_publication() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("root");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    let model = model_bytes();
    fs::write(&model_path, &model).expect("model");
    fs::write(&request_path, request_bytes(100)).expect("request");
    let rejected = root.join("rejected");

    #[cfg(unix)]
    {
        let model_link = root.join("model-link.json");
        std::os::unix::fs::symlink(&model_path, &model_link).expect("model symlink");
        assert!(!run(&[
            text("analysis"),
            text("model-linear-run"),
            &model_link,
            &request_path,
            text("--output-dir"),
            &rejected,
        ])
        .status
        .success());
        assert!(!rejected.exists());
    }

    fs::create_dir(&rejected).expect("existing destination");
    fs::write(rejected.join("sentinel"), b"owned").expect("sentinel");
    assert!(!run(&[
        text("analysis"),
        text("model-linear-run"),
        &model_path,
        &request_path,
        text("--output-dir"),
        &rejected,
    ])
    .status
    .success());
    assert_eq!(
        fs::read(rejected.join("sentinel")).expect("sentinel"),
        b"owned"
    );
    fs::remove_dir_all(root).expect("cleanup");
}
