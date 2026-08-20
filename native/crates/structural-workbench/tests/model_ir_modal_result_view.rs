use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use structural_cli::{execute_model_ir_modal_analysis, publish_model_ir_modal_analysis};
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_modal_product::{
    build_model_ir_modal_analysis_request_v1, ModelIrModalAnalysisRequestV1, ModelIrModalBackendV1,
    MODEL_IR_MODAL_ANALYSIS_REQUEST_V1,
};
use structural_contracts::product_ir::{sha256_identity, ModelIrIdentityV1};
use structural_contracts::spectral_product::SpectralGeneralizedEigenConfigV1;
use structural_workbench::{render_model_ir_modal_result_view_directory, WorkbenchReportLocaleV1};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn temporary_root() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-modal-result-view-{}-{nanos}",
        std::process::id()
    ))
}

fn create_result(directory: &Path) {
    let model_bytes = fs::read(
        repository_root().join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    )
    .expect("model fixture");
    let model = parse_model_ir_v2(&model_bytes).expect("strict ModelIR");
    let request = build_model_ir_modal_analysis_request_v1(ModelIrModalAnalysisRequestV1 {
        schema_version: MODEL_IR_MODAL_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "solve_model_ir_modal".to_owned(),
        case_id: "frame-cantilever-modal-view".to_owned(),
        backend: ModelIrModalBackendV1::Cpu,
        model_identity: ModelIrIdentityV1 {
            content_hash: model.content_hash().to_owned(),
            semantic_hash: model.semantic_hash().to_owned(),
            provenance_hash: model.provenance_hash().to_owned(),
        },
        assembly_load_pattern_id: "LC_WEAK".to_owned(),
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
    .expect("modal request");
    let outcome = execute_model_ir_modal_analysis(&model_bytes, request.canonical_bytes())
        .expect("modal execution");
    publish_model_ir_modal_analysis(directory, &outcome).expect("modal publication");
}

fn verify_view_hash(text: &str, label: &str) {
    let marker = format!("{label}: ");
    let start = text.rfind(&marker).expect("view hash field");
    let expected = text[start + marker.len()..].trim_end();
    assert_eq!(expected, sha256_identity(&text.as_bytes()[..start]));
}

#[test]
fn clean_environment_modal_result_view_is_localized_deterministic_and_read_only() {
    let root = temporary_root();
    fs::create_dir_all(&root).expect("temporary root");
    let result = root.join("result");
    create_result(&result);
    let before = fs::read_dir(&result)
        .expect("result inventory")
        .map(|entry| {
            let entry = entry.expect("artifact entry");
            (
                entry.file_name(),
                fs::read(entry.path()).expect("artifact bytes"),
            )
        })
        .collect::<Vec<_>>();

    let english =
        render_model_ir_modal_result_view_directory(&result, WorkbenchReportLocaleV1::EnUs, 1, 16)
            .expect("English view");
    let repeated =
        render_model_ir_modal_result_view_directory(&result, WorkbenchReportLocaleV1::EnUs, 1, 16)
            .expect("repeated English view");
    let korean =
        render_model_ir_modal_result_view_directory(&result, WorkbenchReportLocaleV1::KoKr, 2, 2)
            .expect("Korean view");
    assert_eq!(english, repeated);
    assert!(english.contains("structural-native-workbench-model-ir-modal-result-view.v1"));
    assert!(english.contains("Displayed modes: 1-3 / 3"));
    assert!(english.contains("cpu / fp64 / fallback 0"));
    assert!(english.contains("0001"));
    assert!(english.contains("0003"));
    assert!(korean.contains("표시 모드: 2-3 / 3"));
    assert!(korean.contains("보기 해시"));
    verify_view_hash(&english, "View hash");
    verify_view_hash(&korean, "보기 해시");

    let cli = Command::new(env!("CARGO_BIN_EXE_structural-workbench"))
        .env_clear()
        .env("PATH", "/nonexistent")
        .args([
            "modal-result-view",
            result.to_str().expect("result path"),
            "--count",
            "16",
        ])
        .output()
        .expect("Workbench CLI");
    assert!(
        cli.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&cli.stdout),
        String::from_utf8_lossy(&cli.stderr)
    );
    assert_eq!(cli.stdout, english.as_bytes());
    let after = fs::read_dir(&result)
        .expect("result inventory")
        .map(|entry| {
            let entry = entry.expect("artifact entry");
            (
                entry.file_name(),
                fs::read(entry.path()).expect("artifact bytes"),
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(before, after);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn modal_result_view_rejects_inventory_hash_and_window_drift() {
    let root = temporary_root();
    fs::create_dir_all(&root).expect("temporary root");

    let extra = root.join("extra");
    create_result(&extra);
    fs::write(extra.join("operator-note.txt"), b"unbound").expect("extra artifact");
    assert!(render_model_ir_modal_result_view_directory(
        &extra,
        WorkbenchReportLocaleV1::EnUs,
        1,
        1,
    )
    .is_err());

    let tampered = root.join("tampered");
    create_result(&tampered);
    let path = tampered.join("result-ir.json");
    let mut bytes = fs::read(&path).expect("result bytes");
    let position = bytes
        .iter()
        .position(|byte| *byte == b'3')
        .expect("mutable result byte");
    bytes[position] = b'4';
    fs::write(path, bytes).expect("tampered result");
    assert!(render_model_ir_modal_result_view_directory(
        &tampered,
        WorkbenchReportLocaleV1::EnUs,
        1,
        1,
    )
    .is_err());

    let valid = root.join("valid");
    create_result(&valid);
    for (start, count) in [(0, 1), (4, 1), (1, 0), (1, 129)] {
        assert!(render_model_ir_modal_result_view_directory(
            &valid,
            WorkbenchReportLocaleV1::EnUs,
            start,
            count,
        )
        .is_err());
    }
    let _ = fs::remove_dir_all(root);
}
