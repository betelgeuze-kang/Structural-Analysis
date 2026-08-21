use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_contracts::model_buckling_product::{
    build_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
    ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::sparse_product::SparseLinearConfigV1;
use structural_contracts::spectral_product::SpectralGeneralizedEigenConfigV1;
use structural_runtime::{
    DurableJobNamedArtifactV1, DurableJobStatusV1, DurableJobStoreV1,
    ModelIrLinearBucklingDurableJobCompletionV1,
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

fn temporary_root(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-model-buckling-job-{label}-{}-{nanos}",
        std::process::id()
    ))
}

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
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

fn output_json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "CLI output is not JSON: {error}: {}",
            String::from_utf8_lossy(&output.stdout)
        )
    })
}

fn write_inputs(root: &Path) -> (PathBuf, PathBuf) {
    let source = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("model fixture");
    let source = parse_model_ir_v2(&source).expect("strict source");
    let mut value = source.value().clone();
    value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(-100_000.0);
    let model = parse_model_ir_v2(&serde_json::to_vec(&value).expect("compression JSON"))
        .expect("compression model");
    let request = build_model_ir_linear_buckling_analysis_request_v1(
        ModelIrLinearBucklingAnalysisRequestV1 {
            schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
            operation: "solve_model_ir_linear_buckling".to_owned(),
            case_id: "frame-cantilever-buckling-job".to_owned(),
            backend: ModelIrLinearBucklingBackendV1::Cpu,
            model_identity: ModelIrIdentityV1 {
                content_hash: model.content_hash().to_owned(),
                semantic_hash: model.semantic_hash().to_owned(),
                provenance_hash: model.provenance_hash().to_owned(),
            },
            reference_load_pattern_id: "LC_AXIAL".to_owned(),
            reference_linear_config: SparseLinearConfigV1 {
                max_iterations: 64,
                absolute_residual_tolerance: 1e-12,
                relative_residual_tolerance: 1e-12,
                maximum_increment: 0.0,
            },
            buckling_config: SpectralGeneralizedEigenConfigV1 {
                mode_count: 2,
                maximum_sweeps: 4_096,
                symmetry_relative_tolerance: 1e-12,
                positive_semidefinite_relative_tolerance: 1e-12,
                mode_relative_tolerance: 1e-10,
                cluster_relative_tolerance: 1e-9,
                residual_relative_tolerance: 1e-9,
                orthogonality_tolerance: 1e-9,
                eigensolver_relative_tolerance: 1e-12,
            },
        },
    )
    .expect("buckling request");
    let model_path = root.join("model.json");
    let request_path = root.join("request.json");
    fs::write(&model_path, model.canonical_bytes()).expect("model input");
    fs::write(&request_path, request.canonical_bytes()).expect("request input");
    (model_path, request_path)
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_process_buckling_job_is_idempotent_restartable_exportable_and_tamper_evident() {
    let root = temporary_root("lifecycle");
    fs::create_dir(&root).expect("root");
    let (model, request) = write_inputs(&root);
    let store = root.join("store");
    let direct = root.join("direct");
    let exported = root.join("exported");
    let submit_arguments = [
        text("job"),
        text("submit-model-buckling"),
        &model,
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("buckling-clean-process"),
    ];
    let submitted = run(&submit_arguments);
    assert!(
        submitted.status.success(),
        "{}",
        String::from_utf8_lossy(&submitted.stdout)
    );
    let submitted_json = output_json(&submitted);
    assert_eq!(
        submitted_json["job"]["analysis_profile"],
        "model_ir_linear_buckling_cpu_v1"
    );
    let job_id = submitted_json["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();
    let repeated = run(&submit_arguments);
    assert!(repeated.status.success());
    assert_eq!(output_json(&repeated)["job"]["job_id"], job_id);

    let advanced = run(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("buckling-worker-after-process-restart"),
    ]);
    assert!(
        advanced.status.success(),
        "{}",
        String::from_utf8_lossy(&advanced.stdout)
    );
    let advanced_json = output_json(&advanced);
    assert_eq!(advanced_json["job"]["status"], "succeeded");
    assert_eq!(
        advanced_json["job"]["product_artifacts"]
            .as_array()
            .expect("inventory")
            .len(),
        18
    );

    let export = run(&[
        text("job"),
        text("export"),
        Path::new(&job_id),
        text("--store"),
        &store,
        text("--output-dir"),
        &exported,
    ]);
    assert!(
        export.status.success(),
        "{}",
        String::from_utf8_lossy(&export.stdout)
    );
    let mut receipt = output_json(&export);
    assert_eq!(
        receipt["analysis_profile"],
        "model_ir_linear_buckling_cpu_v1"
    );
    assert_eq!(
        receipt["artifacts"].as_array().expect("artifacts").len(),
        18
    );
    let receipt_hash = receipt["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    receipt
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let unsigned = canonicalize_model_ir_v2(&receipt).expect("canonical receipt");
    assert_eq!(receipt_hash, sha256_identity(unsigned.as_bytes()));

    let direct_run = run(&[
        text("analysis"),
        text("model-buckling-run"),
        &model,
        &request,
        text("--output-dir"),
        &direct,
    ]);
    assert!(direct_run.status.success());
    for file in PRODUCT_FILES {
        assert_eq!(
            fs::read(exported.join(file)).expect("exported artifact"),
            fs::read(direct.join(file)).expect("direct artifact"),
            "artifact drift: {file}"
        );
    }
    assert!(exported.join("job-receipt.json").is_file());

    let product = advanced_json["job"]["product_artifacts"]
        .as_array()
        .expect("inventory");
    let result = product
        .iter()
        .find(|row| row["name"] == "result-ir.json")
        .expect("result reference");
    let hash = result["artifact"]["content_hash"].as_str().expect("hash");
    let blob = store.join("blobs/sha256").join(&hash[7..]);
    let mut bytes = fs::read(&blob).expect("result blob");
    bytes[0] ^= 1;
    fs::write(&blob, bytes).expect("tamper result blob");
    let rejected = run(&[
        text("job"),
        text("export"),
        Path::new(&job_id),
        text("--store"),
        &store,
        text("--output-dir"),
        &root.join("tampered-export"),
    ]);
    assert!(!rejected.status.success());
    assert_eq!(
        output_json(&rejected)["code"],
        "job_artifact_integrity_failed"
    );
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn queued_buckling_job_cancels_without_execution_or_export() {
    let root = temporary_root("cancel");
    fs::create_dir(&root).expect("root");
    let (model, request) = write_inputs(&root);
    let store = root.join("store");
    let submitted = run(&[
        text("job"),
        text("submit-model-buckling"),
        &model,
        &request,
        text("--store"),
        &store,
        text("--idempotency-key"),
        text("buckling-cancel"),
    ]);
    assert!(submitted.status.success());
    let job_id = output_json(&submitted)["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();
    let cancelled = run(&[
        text("job"),
        text("cancel"),
        Path::new(&job_id),
        text("--store"),
        &store,
    ]);
    assert!(cancelled.status.success());
    assert_eq!(output_json(&cancelled)["job"]["status"], "cancelled");
    let worker = run(&[
        text("job"),
        text("work-once"),
        text("--store"),
        &store,
        text("--worker-id"),
        text("idle-after-cancel"),
    ]);
    assert!(worker.status.success());
    assert_eq!(output_json(&worker)["status"], "idle");
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn expired_buckling_worker_lease_requeues_and_completes_on_a_new_attempt() {
    let root = temporary_root("lease-recovery");
    fs::create_dir(&root).expect("root");
    let (model_path, request_path) = write_inputs(&root);
    let store_path = root.join("store");
    let store = DurableJobStoreV1::open(&store_path).expect("store");
    let model = fs::read(model_path).expect("model");
    let request = fs::read(request_path).expect("request");
    let submitted = store
        .submit_model_ir_linear_buckling("buckling-expired-lease", &model, &request, 1_000)
        .expect("submit");
    let claim = store
        .claim_next("worker-that-exits", 1_000, 1_001)
        .expect("claim")
        .expect("claimed job");
    assert_eq!(claim.job.status, DurableJobStatusV1::Running);
    assert_eq!(store.recover_expired_leases(2_001).expect("recover"), 1);
    let recovered = store.poll(&submitted.job_id).expect("poll recovered");
    assert_eq!(recovered.status, DurableJobStatusV1::Queued);
    assert_eq!(
        recovered.error_code.as_deref(),
        Some("worker_lease_expired")
    );
    let completed =
        structural_cli::execute_next_durable_job(&store, "replacement-worker", 10_000, 1)
            .expect("replacement execution")
            .expect("advanced job");
    assert_eq!(completed.status, DurableJobStatusV1::Succeeded);
    assert_eq!(completed.attempt, 2);
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
#[allow(clippy::too_many_lines)]
fn forged_buckling_completion_is_rejected_without_a_terminal_event() {
    let root = temporary_root("forged-completion");
    fs::create_dir(&root).expect("root");
    let (model_path, request_path) = write_inputs(&root);
    let model = fs::read(model_path).expect("model");
    let request = fs::read(request_path).expect("request");
    let store = DurableJobStoreV1::open(&root.join("store")).expect("store");
    let submitted = store
        .submit_model_ir_linear_buckling("forged-completion", &model, &request, 1_000)
        .expect("submit");
    let claim = store
        .claim_next("forged-worker", 10_000, 1_001)
        .expect("claim")
        .expect("claimed job");
    let outcome = structural_cli::execute_model_ir_linear_buckling_analysis(&model, &request)
        .expect("product");
    let owned = outcome
        .artifacts()
        .iter()
        .map(|artifact| (artifact.name, artifact.media_type, artifact.bytes.to_vec()))
        .collect::<Vec<_>>();
    let mut owned = owned;
    owned
        .iter_mut()
        .find(|(name, _, _)| *name == "report.md")
        .expect("report artifact")
        .2
        .extend_from_slice(b"forged");
    let artifacts = owned
        .iter()
        .map(|(name, media_type, bytes)| DurableJobNamedArtifactV1 {
            name,
            media_type,
            bytes,
        })
        .collect::<Vec<_>>();
    let error = store
        .complete_model_ir_linear_buckling_job(
            &submitted.job_id,
            "forged-worker",
            &claim.lease_token,
            ModelIrLinearBucklingDurableJobCompletionV1 {
                artifacts: &artifacts,
            },
            1_002,
        )
        .expect_err("forged completion");
    assert_eq!(error.code, "job_completion_projection_mismatch");
    let retained = store
        .poll(&submitted.job_id)
        .expect("retained running event");
    assert_eq!(retained.status, DurableJobStatusV1::Running);
    assert!(retained.product_artifacts.is_empty());

    let mut receipt_owned = outcome
        .artifacts()
        .iter()
        .map(|artifact| (artifact.name, artifact.media_type, artifact.bytes.to_vec()))
        .collect::<Vec<_>>();
    let receipt_bytes = &mut receipt_owned
        .iter_mut()
        .find(|(name, _, _)| *name == "run-receipt.json")
        .expect("run receipt")
        .2;
    let mut receipt_value: Value = serde_json::from_slice(receipt_bytes).expect("receipt JSON");
    receipt_value["case_id"] = json!("forged-case");
    receipt_value
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let unsigned = canonicalize_model_ir_v2(&receipt_value).expect("unsigned receipt");
    receipt_value
        .as_object_mut()
        .expect("receipt object")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    *receipt_bytes = canonicalize_model_ir_v2(&receipt_value)
        .expect("forged canonical receipt")
        .into_bytes();
    let receipt_artifacts = receipt_owned
        .iter()
        .map(|(name, media_type, bytes)| DurableJobNamedArtifactV1 {
            name,
            media_type,
            bytes,
        })
        .collect::<Vec<_>>();
    let receipt_error = store
        .complete_model_ir_linear_buckling_job(
            &submitted.job_id,
            "forged-worker",
            &claim.lease_token,
            ModelIrLinearBucklingDurableJobCompletionV1 {
                artifacts: &receipt_artifacts,
            },
            1_003,
        )
        .expect_err("self-hashed forged receipt");
    assert_eq!(
        receipt_error.code,
        "job_completion_receipt_identity_mismatch"
    );
    fs::remove_dir_all(root).expect("cleanup");
}
