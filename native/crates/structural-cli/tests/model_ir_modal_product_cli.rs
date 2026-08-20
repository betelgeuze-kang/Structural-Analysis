use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_modal_product::{
    build_model_ir_modal_analysis_request_v1, ModelIrModalAnalysisRequestV1, ModelIrModalBackendV1,
    MODEL_IR_MODAL_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::spectral_product::{
    parse_dense_spectral_result_ir_v1, SpectralGeneralizedEigenConfigV1,
};

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
        "structural-model-modal-{name}-{}-{nanos}",
        std::process::id()
    ))
}

fn request(model_bytes: &[u8], load_pattern: &str) -> Vec<u8> {
    let model = parse_model_ir_v2(model_bytes).expect("strict ModelIR");
    build_model_ir_modal_analysis_request_v1(ModelIrModalAnalysisRequestV1 {
        schema_version: MODEL_IR_MODAL_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_modal".to_owned(),
        case_id: "frame-cantilever-modal".to_owned(),
        backend: ModelIrModalBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: model.content_hash().to_owned(),
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

fn verify_self_hash(value: &Value, field: &str) {
    let mut unsigned = value.clone();
    let expected = unsigned[field].as_str().expect("self hash").to_owned();
    unsigned
        .as_object_mut()
        .expect("self-hashed object")
        .remove(field);
    let canonical = structural_contracts::model_ir::canonicalize_model_ir_v2(&unsigned)
        .expect("canonical unsigned value");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

#[test]
fn python_node_free_modelir_modal_direct_resume_are_byte_identical_and_bound() {
    let root = temporary_root("e2e");
    fs::create_dir_all(&root).expect("temporary root");
    let model_path =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let model_bytes = fs::read(&model_path).expect("ModelIR fixture");
    let request_path = root.join("request.json");
    fs::write(&request_path, request(&model_bytes, "LC_WEAK")).expect("request fixture");
    let first = root.join("first");
    let second = root.join("second");
    let resumed = root.join("resumed");

    for output in [&first, &second] {
        let execution = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
            .env_clear()
            .env("PATH", "/nonexistent")
            .args([
                "analysis",
                "model-modal-run",
                model_path.to_str().expect("model path"),
                request_path.to_str().expect("request path"),
                "--output-dir",
                output.to_str().expect("output path"),
            ])
            .output()
            .expect("execute structural-cli");
        assert!(
            execution.status.success(),
            "stdout={} stderr={}",
            String::from_utf8_lossy(&execution.stdout),
            String::from_utf8_lossy(&execution.stderr)
        );
    }
    let resume = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "analysis",
            "model-modal-resume",
            model_path.to_str().expect("model path"),
            request_path.to_str().expect("request path"),
            first
                .join("checkpoint.mmcp")
                .to_str()
                .expect("checkpoint path"),
            "--output-dir",
            resumed.to_str().expect("output path"),
        ])
        .output()
        .expect("resume structural-cli");
    assert!(
        resume.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&resume.stdout),
        String::from_utf8_lossy(&resume.stderr)
    );

    let expected_files = [
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
    for file in expected_files {
        assert_eq!(
            fs::read(first.join(file)).expect("first artifact"),
            fs::read(second.join(file)).expect("second artifact"),
            "artifact drifted: {file}"
        );
        assert_eq!(
            fs::read(first.join(file)).expect("direct artifact"),
            fs::read(resumed.join(file)).expect("resumed artifact"),
            "resume artifact drifted: {file}"
        );
    }

    let result =
        parse_dense_spectral_result_ir_v1(&fs::read(first.join("result-ir.json")).expect("result"))
            .expect("verified ResultIR");
    assert_eq!(result.result().summary.mode_count, 3);
    assert_eq!(result.result().backend_receipt.fallback_count, 0);

    let receipt: Value =
        serde_json::from_slice(&fs::read(first.join("run-receipt.json")).expect("run receipt"))
            .expect("run receipt JSON");
    assert_eq!(receipt["status"], "completed");
    assert_eq!(receipt["fallback_count"], 0);
    verify_self_hash(&receipt, "receipt_hash");
    for artifact in receipt["artifacts"].as_array().expect("artifact rows") {
        let file = artifact["file"].as_str().expect("artifact file");
        let bytes = fs::read(first.join(file)).expect("bound artifact");
        assert_eq!(artifact["content_hash"], sha256_identity(&bytes));
        assert_eq!(
            artifact["byte_length"],
            u64::try_from(bytes.len()).expect("bounded artifact length")
        );
    }

    let _ = fs::remove_dir_all(root);
}

#[test]
fn modelir_modal_resume_rejects_tamper_and_outer_binding_drift_without_publication() {
    let root = temporary_root("restart-rejection");
    fs::create_dir_all(&root).expect("temporary root");
    let model_path =
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");
    let model_bytes = fs::read(&model_path).expect("ModelIR fixture");
    let first_request = root.join("first-request.json");
    fs::write(&first_request, request(&model_bytes, "LC_WEAK")).expect("first request");
    let direct = root.join("direct");
    let execution = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "analysis",
            "model-modal-run",
            model_path.to_str().expect("model path"),
            first_request.to_str().expect("request path"),
            "--output-dir",
            direct.to_str().expect("output path"),
        ])
        .output()
        .expect("direct structural-cli");
    assert!(execution.status.success());

    let checkpoint = fs::read(direct.join("checkpoint.mmcp")).expect("model checkpoint");
    let mut tampered = checkpoint.clone();
    let last = tampered.last_mut().expect("nonempty checkpoint");
    *last ^= 1;
    let tampered_path = root.join("tampered.mmcp");
    fs::write(&tampered_path, tampered).expect("tampered checkpoint");
    let alternate_request = root.join("alternate-request.json");
    fs::write(&alternate_request, request(&model_bytes, "LC_STRONG")).expect("alternate request");

    for (name, request_path, checkpoint_path) in [
        ("tampered-output", &first_request, &tampered_path),
        (
            "binding-drift-output",
            &alternate_request,
            &direct.join("checkpoint.mmcp"),
        ),
    ] {
        let output = root.join(name);
        let rejected = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
            .env_clear()
            .env("PATH", "/nonexistent")
            .args([
                "analysis",
                "model-modal-resume",
                model_path.to_str().expect("model path"),
                request_path.to_str().expect("request path"),
                checkpoint_path.to_str().expect("checkpoint path"),
                "--output-dir",
                output.to_str().expect("output path"),
            ])
            .output()
            .expect("reject structural-cli resume");
        assert!(!rejected.status.success(), "{name} unexpectedly succeeded");
        assert!(!output.exists(), "{name} published a partial directory");
    }

    let _ = fs::remove_dir_all(root);
}
