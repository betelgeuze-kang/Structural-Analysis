use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_evidence::{
    build_evidence_bundle, canonical_receipt_json, check_evidence_sources,
    EvidenceBundleBuildRequest,
};

const SOURCE_PATHS: [&str; 5] = [
    "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
    "implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json",
    "implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json",
    "implementation/phase1/release_evidence/productization/evidence_console_scope_status.json",
    "implementation/phase1/real_project_corpus_measured_status.json",
];
const COMMIT_A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const COMMIT_B: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const GENERATED_AT: &str = "2026-08-13T00:00:00Z";
static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TestRoot(PathBuf);

impl TestRoot {
    fn create() -> Self {
        for _ in 0..1024 {
            let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "structural-evidence-test-{}-{sequence}",
                std::process::id()
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => panic!("create test root failed: {error}"),
            }
        }
        panic!("could not allocate evidence test root");
    }
}

impl Drop for TestRoot {
    fn drop(&mut self) {
        let _ignored = std::fs::remove_dir_all(&self.0);
    }
}

fn write_sources(root: &Path, commits: [&str; 5]) -> Vec<Vec<u8>> {
    SOURCE_PATHS
        .iter()
        .enumerate()
        .map(|(index, relative)| {
            let path = root.join(relative);
            std::fs::create_dir_all(path.parent().expect("source parent"))
                .expect("create source parent");
            let mut bytes = serde_json::to_vec_pretty(&json!({
                "schema_version": "fixture.v1",
                "source_commit_sha": commits[index],
                "status": "fixture",
                "sequence": index,
            }))
            .expect("encode fixture source");
            bytes.push(b'\n');
            std::fs::write(&path, &bytes).expect("write fixture source");
            bytes
        })
        .collect()
}

fn verify_receipt_hash(value: &Value) {
    let mut unsigned = value.clone();
    let expected = unsigned
        .as_object_mut()
        .expect("receipt object")
        .remove("receipt_hash")
        .and_then(|hash| hash.as_str().map(ToOwned::to_owned))
        .expect("receipt hash");
    let canonical = canonicalize_model_ir_v2(&unsigned).expect("canonical unsigned receipt");
    assert_eq!(expected, sha256_identity(canonical.as_bytes()));
}

fn run_binary(arguments: &[&OsStr]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_structural-evidence"))
        .args(arguments)
        .env_clear()
        .output()
        .expect("run structural-evidence")
}

#[test]
fn deterministic_build_copies_exact_bytes_and_never_replaces_output() {
    let test = TestRoot::create();
    let originals = write_sources(&test.0, [COMMIT_A; 5]);
    let first_output = test.0.join("bundle-a");
    let second_output = test.0.join("bundle-b");
    let first = build_evidence_bundle(&EvidenceBundleBuildRequest {
        source_root: &test.0,
        output: &first_output,
        generated_at: GENERATED_AT,
    })
    .expect("first deterministic evidence build");
    let second = build_evidence_bundle(&EvidenceBundleBuildRequest {
        source_root: &test.0,
        output: &second_output,
        generated_at: GENERATED_AT,
    })
    .expect("second deterministic evidence build");
    assert_eq!(first, second);
    assert_eq!(first.artifact_count, 5);
    assert_eq!(first.source_commit_sha, COMMIT_A);
    assert!(first.single_source_commit);
    assert!(first.sensitive_data_scan_passed);
    assert!(first.sources_unchanged);
    assert!(first.output_manifest_sha256.is_some());

    let bundle_paths = [
        "readiness/product-readiness.json",
        "readiness/benchmark-breadth.json",
        "readiness/fresh-validation.json",
        "readiness/evidence-console-scope.json",
        "readiness/real-project-corpus.json",
    ];
    for (index, relative) in bundle_paths.iter().enumerate() {
        let first_path = first_output.join(relative);
        assert_eq!(
            std::fs::read(&first_path).expect("read copied source"),
            originals[index]
        );
        assert_eq!(
            std::fs::read(&first_path).expect("first bundle file"),
            std::fs::read(second_output.join(relative)).expect("second bundle file")
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            assert_eq!(
                std::fs::metadata(&first_path)
                    .expect("copied source metadata")
                    .permissions()
                    .mode()
                    & 0o222,
                0,
                "published evidence source must be read-only"
            );
        }
    }
    assert_eq!(
        std::fs::read(first_output.join("manifest.json")).expect("first manifest"),
        std::fs::read(second_output.join("manifest.json")).expect("second manifest")
    );
    for (index, relative) in SOURCE_PATHS.iter().enumerate() {
        assert_eq!(
            std::fs::read(test.0.join(relative)).expect("re-read original source"),
            originals[index]
        );
    }
    let error = build_evidence_bundle(&EvidenceBundleBuildRequest {
        source_root: &test.0,
        output: &first_output,
        generated_at: GENERATED_AT,
    })
    .expect_err("existing output must not be replaced");
    assert_eq!(error.code, "evidence_output_exists");

    let invalid_timestamp_output = test.0.join("invalid-timestamp-bundle");
    let error = build_evidence_bundle(&EvidenceBundleBuildRequest {
        source_root: &test.0,
        output: &invalid_timestamp_output,
        generated_at: "not-a-timestamp",
    })
    .expect_err("invalid timestamp must fail before publication");
    assert_eq!(error.code, "evidence_generated_at_invalid");
    assert!(!invalid_timestamp_output.exists());

    let receipt_json = canonical_receipt_json(&first).expect("canonical build receipt");
    let receipt: Value = serde_json::from_str(&receipt_json).expect("decode build receipt");
    verify_receipt_hash(&receipt);
    assert_eq!(
        receipt["schema_version"],
        "structural-native-evidence-bundle-build-receipt.v1"
    );
}

#[test]
fn source_checks_fail_closed_on_mixed_commit_sensitive_data_and_duplicate_keys() {
    let mixed = TestRoot::create();
    write_sources(&mixed.0, [COMMIT_B, COMMIT_A, COMMIT_A, COMMIT_A, COMMIT_A]);
    assert_eq!(
        check_evidence_sources(&mixed.0)
            .expect_err("mixed commit must fail")
            .code,
        "evidence_source_commit_mismatch"
    );

    let sensitive = TestRoot::create();
    write_sources(&sensitive.0, [COMMIT_A; 5]);
    std::fs::write(
        sensitive.0.join(SOURCE_PATHS[0]),
        format!(
            "{{\"contact_email\":\"operator@example.com\",\"source_commit_sha\":\"{COMMIT_A}\"}}\n"
        ),
    )
    .expect("write sensitive fixture");
    assert_eq!(
        check_evidence_sources(&sensitive.0)
            .expect_err("sensitive value must fail")
            .code,
        "evidence_sensitive_data_detected"
    );

    let duplicate = TestRoot::create();
    write_sources(&duplicate.0, [COMMIT_A; 5]);
    std::fs::write(
        duplicate.0.join(SOURCE_PATHS[0]),
        format!("{{\"source_commit_sha\":\"{COMMIT_A}\",\"source_commit_sha\":\"{COMMIT_A}\"}}\n"),
    )
    .expect("write duplicate-key fixture");
    assert_eq!(
        check_evidence_sources(&duplicate.0)
            .expect_err("duplicate JSON key must fail")
            .code,
        "evidence_source_json_invalid"
    );

    let missing_commit = TestRoot::create();
    write_sources(&missing_commit.0, [COMMIT_A; 5]);
    std::fs::write(
        missing_commit.0.join(SOURCE_PATHS[0]),
        b"{\"schema_version\":\"fixture.v1\",\"status\":\"fixture\"}\n",
    )
    .expect("write missing-commit fixture");
    assert_eq!(
        check_evidence_sources(&missing_commit.0)
            .expect_err("missing source commit must fail")
            .code,
        "evidence_source_commit_invalid"
    );
}

#[cfg(unix)]
#[test]
fn source_checks_reject_symlinked_evidence() {
    use std::os::unix::fs::symlink;

    let test = TestRoot::create();
    write_sources(&test.0, [COMMIT_A; 5]);
    let target = test.0.join(SOURCE_PATHS[1]);
    let link = test.0.join(SOURCE_PATHS[0]);
    std::fs::remove_file(&link).expect("remove source before symlink");
    symlink(target, link).expect("create evidence source symlink");
    assert_eq!(
        check_evidence_sources(&test.0)
            .expect_err("source symlink must fail")
            .code,
        "evidence_source_not_bounded_regular_file"
    );
}

#[test]
fn clean_environment_cli_emits_canonical_self_hashed_check_receipt() {
    let test = TestRoot::create();
    write_sources(&test.0, [COMMIT_A; 5]);
    let output = run_binary(&[
        OsStr::new("check"),
        OsStr::new("--root"),
        test.0.as_os_str(),
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("CLI receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical CLI receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "check");
    assert!(value["output_manifest_sha256"].is_null());
    verify_receipt_hash(&value);
}
