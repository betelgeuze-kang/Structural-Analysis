use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{
    parse_sparse_linear_report_ir_v1, parse_sparse_linear_result_ir_v1,
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
        "structural-sparse-product-{name}-{}-{nanos}",
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

fn request(max_iterations: u32, right_hand_side: &[f64]) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema_version": "structural-sparse-linear-request.v1",
        "operation": "solve_sparse_spd_pcg",
        "case_id": "sparse-product-c5",
        "backend": "cpu",
        "order": 5,
        "row_offsets": [0, 2, 5, 8, 11, 13],
        "column_indices": [0, 1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4],
        "values": [4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 3.0, -1.0, -1.0, 2.0],
        "right_hand_side": right_hand_side,
        "initial_guess": [],
        "config": {
            "max_iterations": max_iterations,
            "absolute_residual_tolerance": 1e-13,
            "relative_residual_tolerance": 1e-13,
            "maximum_increment": 0.0
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
fn python_node_free_direct_and_real_iteration_resume_are_byte_identical() {
    let root = temporary_root("clean-env");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(
        &request_path,
        request(100, &[6.0, -12.0, 18.0, -20.0, 14.0]),
    )
    .expect("request");
    let direct = root.join("direct");
    let partial = root.join("partial");
    let resumed = root.join("resumed");

    let output = run(&[
        text("analysis"),
        text("linear-run"),
        &request_path,
        text("--output-dir"),
        &direct,
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    verify_receipt(&direct, "completed");

    let output = run(&[
        text("analysis"),
        text("linear-run"),
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
    assert!(partial.join("checkpoint.pcgcp").is_file());
    assert!(partial.join("checkpoint-receipt.json").is_file());
    assert!(!partial.join("result-ir.json").exists());
    assert!(!partial.join("report-ir.json").exists());

    let output = run(&[
        text("analysis"),
        text("linear-resume"),
        &request_path,
        &partial.join("checkpoint.pcgcp"),
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
        "checkpoint.pcgcp",
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
    for (actual, expected) in result
        .result()
        .solution
        .iter()
        .zip([1.0, -2.0, 3.0, -4.0, 5.0])
    {
        assert!((actual - expected).abs() <= 2.0e-12);
    }
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
    fs::write(&request_path, request(1, &[1.0; 5])).expect("request");
    let output_directory = root.join("failed");
    let output = run(&[
        text("analysis"),
        text("linear-run"),
        &request_path,
        text("--output-dir"),
        &output_directory,
    ]);
    assert!(!output.status.success());
    verify_receipt(&output_directory, "failed");
    assert!(output_directory.join("checkpoint.pcgcp").is_file());
    assert!(output_directory.join("checkpoint-receipt.json").is_file());
    assert!(!output_directory.join("result-ir.json").exists());
    let receipt: Value = serde_json::from_slice(
        &fs::read(output_directory.join("run-receipt.json")).expect("receipt"),
    )
    .expect("receipt JSON");
    assert_eq!(receipt["solver_status"], "nonconvergence");
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn tamper_symlink_and_existing_destination_fail_without_publication() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(
        &request_path,
        request(100, &[6.0, -12.0, 18.0, -20.0, 14.0]),
    )
    .expect("request");
    let partial = root.join("partial");
    assert!(run(&[
        text("analysis"),
        text("linear-run"),
        &request_path,
        text("--output-dir"),
        &partial,
        text("--iteration-budget"),
        text("1"),
    ])
    .status
    .success());
    let mut corrupt = fs::read(partial.join("checkpoint.pcgcp")).expect("checkpoint");
    let last = corrupt.len() - 1;
    corrupt[last] ^= 1;
    let corrupt_path = root.join("corrupt.pcgcp");
    fs::write(&corrupt_path, corrupt).expect("corrupt checkpoint");
    let rejected = root.join("rejected");
    assert!(!run(&[
        text("analysis"),
        text("linear-resume"),
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
            text("linear-run"),
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
        text("linear-run"),
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
