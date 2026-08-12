use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::static_product::{
    parse_nonlinear_static_report_ir_v1, parse_nonlinear_static_result_ir_v1,
};

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-static-product-{name}-{}-{nanos}",
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

fn request(max_iter: u32) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema_version": "structural-nonlinear-static-request.v1",
        "operation": "solve_nonlinear_static_newton",
        "case_id": "static-product-c5",
        "backend": "cpu",
        "config": {
            "story_count": 3,
            "tolerance": 1e-7,
            "max_iter": max_iter,
            "hardening_ratio": 0.04,
            "line_search_decay": 0.5,
            "line_search_min": 0.03125,
            "pdelta_factor": 1.0
        },
        "inputs": {
            "story_k_n_per_m": [100_000_000.0, 90_000_000.0, 80_000_000.0],
            "story_h_m": [3.0, 3.0, 3.0],
            "story_axial_n": [1_000_000.0, 800_000.0, 600_000.0],
            "story_yield_drift_m": [0.02, 0.02, 0.02],
            "floor_load_n": [10000.0, 8000.0, 6000.0]
        }
    }))
    .expect("request JSON")
}

fn verify_receipt(directory: &Path, expected_status: &str) {
    let bytes = fs::read(directory.join("run-receipt.json")).expect("run receipt");
    let mut value: Value = serde_json::from_slice(&bytes).expect("run receipt JSON");
    assert_eq!(value["status"], expected_status);
    let hash = value["receipt_hash"]
        .as_str()
        .expect("receipt hash")
        .to_owned();
    value
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).expect("canonical receipt");
    assert_eq!(hash, sha256_identity(canonical.as_bytes()));
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
}

#[test]
fn python_node_free_direct_and_real_newton_resume_are_byte_identical() {
    let root = temporary_root("clean-env");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(&request_path, request(60)).expect("request");
    let direct = root.join("direct");
    let partial = root.join("partial");
    let resumed = root.join("resumed");

    let output = run(&[
        text("analysis"),
        text("static-run"),
        &request_path,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{} {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    verify_receipt(&direct, "completed");

    let output = run(&[
        text("analysis"),
        text("static-run"),
        &request_path,
        text("--output-dir"),
        &partial,
        text("--iteration-budget"),
        text("1"),
    ]);
    assert!(
        output.status.success(),
        "{} {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    verify_receipt(&partial, "active");
    assert!(partial.join("checkpoint.stacp").is_file());
    assert!(partial.join("checkpoint-receipt.json").is_file());
    assert!(!partial.join("result-ir.json").exists());
    assert!(!partial.join("report-ir.json").exists());

    let output = run(&[
        text("analysis"),
        text("static-resume"),
        &request_path,
        &partial.join("checkpoint.stacp"),
        text("--output-dir"),
        &resumed,
    ]);
    assert!(
        output.status.success(),
        "{} {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    verify_receipt(&resumed, "completed");
    for name in [
        "checkpoint.stacp",
        "checkpoint-receipt.json",
        "result-ir.json",
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
    let result = parse_nonlinear_static_result_ir_v1(
        &fs::read(direct.join("result-ir.json")).expect("ResultIR"),
    )
    .expect("strict ResultIR");
    let report = parse_nonlinear_static_report_ir_v1(
        &fs::read(direct.join("report-ir.json")).expect("ReportIR"),
    )
    .expect("strict ReportIR");
    assert_eq!(report.report().source_result_hash, result.result_hash());
    assert_eq!(result.result().backend_receipt.fallback_count, 0);
    assert_eq!(result.result().summary.iterations, 6);
    assert_eq!(result.result().displacement_m.len(), 3);
    assert_eq!(
        report.report().document_source_hash,
        sha256_identity(&fs::read(direct.join("report.md")).expect("report source"))
    );
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn numerical_failure_publishes_terminal_checkpoint_and_returns_failure() {
    let root = temporary_root("numerical-failure");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(&request_path, request(1)).expect("request");
    let output_directory = root.join("failed");
    let output = run(&[
        text("analysis"),
        text("static-run"),
        &request_path,
        text("--output-dir"),
        &output_directory,
    ]);
    assert!(!output.status.success());
    verify_receipt(&output_directory, "failed");
    assert!(output_directory.join("checkpoint.stacp").is_file());
    assert!(!output_directory.join("result-ir.json").exists());
    let receipt: Value = serde_json::from_slice(
        &fs::read(output_directory.join("run-receipt.json")).expect("receipt"),
    )
    .expect("receipt JSON");
    assert_eq!(receipt["execution_status"], "nonconverged");
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn tamper_symlink_and_existing_destination_fail_without_publication() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(&request_path, request(60)).expect("request");
    let partial = root.join("partial");
    assert!(run(&[
        text("analysis"),
        text("static-run"),
        &request_path,
        text("--output-dir"),
        &partial,
        text("--iteration-budget"),
        text("1"),
    ])
    .status
    .success());
    let mut corrupt = fs::read(partial.join("checkpoint.stacp")).expect("checkpoint");
    let last = corrupt.len() - 1;
    corrupt[last] ^= 1;
    let corrupt_path = root.join("corrupt.stacp");
    fs::write(&corrupt_path, corrupt).expect("corrupt checkpoint");
    let rejected = root.join("rejected");
    assert!(!run(&[
        text("analysis"),
        text("static-resume"),
        &request_path,
        &corrupt_path,
        text("--output-dir"),
        &rejected,
    ])
    .status
    .success());
    assert!(!rejected.exists());

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(&request_path, root.join("request-link.json"))
            .expect("request symlink");
        assert!(!run(&[
            text("analysis"),
            text("static-run"),
            &root.join("request-link.json"),
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
        text("static-run"),
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
