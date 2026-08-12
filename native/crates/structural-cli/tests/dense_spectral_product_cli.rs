use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_structural-cli"))
}

fn temporary_root(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "structural-spectral-{name}-{}-{nanos}",
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

fn request(kind: &str) -> Vec<u8> {
    let (case_id, stiffness, secondary, mode_count) = if kind == "modal" {
        (
            "modal-rigid-product",
            vec![0.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 9.0],
            vec![1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            2,
        )
    } else {
        (
            "buckling-singular-product",
            vec![6.0, 0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 10.0],
            vec![3.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0],
            2,
        )
    };
    serde_json::to_vec(&json!({
        "schema_version": "structural-dense-spectral-request.v1",
        "operation": "solve_dense_generalized_eigen",
        "case_id": case_id,
        "analysis_kind": if kind == "modal" { "modal" } else { "linear_buckling" },
        "backend": "cpu",
        "order": 3,
        "stiffness": stiffness,
        "secondary_matrix": secondary,
        "coordinate_recovery_scale": [],
        "config": {
            "mode_count": mode_count,
            "maximum_sweeps": 128,
            "symmetry_relative_tolerance": 1e-12,
            "positive_semidefinite_relative_tolerance": 1e-12,
            "mode_relative_tolerance": 1e-12,
            "cluster_relative_tolerance": 1e-10,
            "residual_relative_tolerance": if kind == "modal" { 1e-10 } else { 1e-9 },
            "orthogonality_tolerance": if kind == "modal" { 1e-10 } else { 1e-8 },
            "eigensolver_relative_tolerance": 1e-14
        }
    }))
    .expect("request JSON")
}

fn assert_same_artifacts(left: &Path, right: &Path) {
    for name in [
        "checkpoint.eigcp",
        "result-ir.json",
        "report-ir.json",
        "report.md",
        "run-receipt.json",
    ] {
        assert_eq!(
            fs::read(left.join(name)).expect("left artifact"),
            fs::read(right.join(name)).expect("right artifact"),
            "artifact drift: {name}"
        );
    }
}

#[test]
fn python_node_free_modal_and_buckling_direct_resume_are_byte_identical() {
    for kind in ["modal", "buckling"] {
        let root = temporary_root(kind);
        fs::create_dir(&root).expect("root");
        let request_path = root.join("request.json");
        fs::write(&request_path, request(kind)).expect("request");
        let direct = root.join("direct");
        let resumed = root.join("resumed");
        let output = run(&[
            text("analysis"),
            text("eigen-run"),
            &request_path,
            text("--output-dir"),
            &direct,
        ]);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        let output = run(&[
            text("analysis"),
            text("eigen-resume"),
            &request_path,
            &direct.join("checkpoint.eigcp"),
            text("--output-dir"),
            &resumed,
        ]);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        assert_same_artifacts(&direct, &resumed);
        let result: Value =
            serde_json::from_slice(&fs::read(direct.join("result-ir.json")).expect("result"))
                .expect("result JSON");
        assert_eq!(
            result["analysis_kind"],
            if kind == "modal" {
                "modal"
            } else {
                "linear_buckling"
            }
        );
        assert_eq!(result["backend_receipt"]["fallback_count"], 0);
        assert_eq!(result["modes"].as_array().expect("modes").len(), 2);
        fs::remove_dir_all(root).expect("cleanup");
    }
}

#[test]
fn tamper_request_drift_and_existing_destination_publish_nothing() {
    let root = temporary_root("negative");
    fs::create_dir(&root).expect("root");
    let request_path = root.join("request.json");
    fs::write(&request_path, request("modal")).expect("request");
    let first = root.join("first");
    assert!(run(&[
        text("analysis"),
        text("eigen-run"),
        &request_path,
        text("--output-dir"),
        &first,
    ])
    .status
    .success());
    let checkpoint = first.join("checkpoint.eigcp");
    let mut corrupt = fs::read(&checkpoint).expect("checkpoint");
    let last = corrupt.len() - 1;
    corrupt[last] ^= 1;
    let corrupt_path = root.join("corrupt.eigcp");
    fs::write(&corrupt_path, corrupt).expect("corrupt");
    let rejected = root.join("rejected");
    assert!(!run(&[
        text("analysis"),
        text("eigen-resume"),
        &request_path,
        &corrupt_path,
        text("--output-dir"),
        &rejected,
    ])
    .status
    .success());
    assert!(!rejected.exists());

    let mut drift: Value = serde_json::from_slice(&request("modal")).expect("request JSON");
    drift["stiffness"][4] = json!(5.0);
    let drift_path = root.join("drift.json");
    fs::write(&drift_path, serde_json::to_vec(&drift).expect("drift")).expect("drift file");
    assert!(!run(&[
        text("analysis"),
        text("eigen-resume"),
        &drift_path,
        &checkpoint,
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
            text("eigen-run"),
            &root.join("request-link.json"),
            text("--output-dir"),
            &rejected,
        ])
        .status
        .success());
        assert!(!rejected.exists());
    }

    fs::create_dir(&rejected).expect("existing output");
    fs::write(rejected.join("sentinel"), b"owned").expect("sentinel");
    assert!(!run(&[
        text("analysis"),
        text("eigen-run"),
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
