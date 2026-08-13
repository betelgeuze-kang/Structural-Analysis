use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_frontend_contract::{canonical_receipt_json, check_frontend_contract};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TestRoot(PathBuf);

impl TestRoot {
    fn create() -> Self {
        for _ in 0..1024 {
            let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "structural-frontend-contract-test-{}-{sequence}",
                std::process::id()
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => panic!("create test root failed: {error}"),
            }
        }
        panic!("could not allocate frontend-contract test root");
    }
}

impl Drop for TestRoot {
    fn drop(&mut self) {
        let _ignored = std::fs::remove_dir_all(&self.0);
    }
}

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn copy_contract_inventory(destination: &Path) {
    let root = repository_root();
    let source_map: Value = serde_json::from_slice(
        &std::fs::read(root.join("native/decommission/legacy-frontend-build-contract-v1.json"))
            .expect("read source map"),
    )
    .expect("source-map JSON");
    for relative in source_map["required_files"]
        .as_array()
        .expect("required files")
        .iter()
        .map(|value| value.as_str().expect("required path"))
    {
        let target = destination.join(relative);
        std::fs::create_dir_all(target.parent().expect("target parent"))
            .expect("create target parent");
        std::fs::copy(root.join(relative), target).expect("copy required file");
    }
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

#[test]
fn tracked_frontend_contract_is_canonical_self_hashed_and_read_only() {
    let root = repository_root();
    let before = std::fs::read(root.join("package.json")).expect("package before check");
    let first = check_frontend_contract(&root).expect("tracked frontend contract");
    let second = check_frontend_contract(&root).expect("repeat frontend contract");
    assert_eq!(first, second);
    assert_eq!(first.package_name, "structural-analysis");
    assert_eq!(first.package_manager, "npm@10.8.2");
    assert_eq!(first.lockfile_version, 3);
    assert_eq!(first.commands_executed, 0);
    assert_eq!(first.network_access_count, 0);
    assert!(first.required_file_count >= 40);
    assert_eq!(
        before,
        std::fs::read(root.join("package.json")).expect("package after check")
    );
    let receipt = canonical_receipt_json(&first).expect("canonical receipt");
    let value: Value = serde_json::from_str(&receipt).expect("receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_cli_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["check", "--root"])
        .arg(&root)
        .env_clear()
        .output()
        .expect("run structural-frontend-contract");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "check");
    verify_receipt_hash(&value);
}

#[test]
fn duplicate_package_key_is_rejected_before_contract_interpretation() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    std::fs::write(
        test.0.join("package.json"),
        b"{\"name\":\"structural-analysis\",\"name\":\"forged\"}\n",
    )
    .expect("write duplicate package");
    let error = check_frontend_contract(&test.0).expect_err("duplicate key must fail closed");
    assert_eq!(error.code, "frontend_package_json_invalid");
}

#[test]
fn dependency_and_forbidden_path_drift_fail_closed() {
    let dependency_drift = TestRoot::create();
    copy_contract_inventory(&dependency_drift.0);
    let package_path = dependency_drift.0.join("package.json");
    let mut package: Value =
        serde_json::from_slice(&std::fs::read(&package_path).expect("read package"))
            .expect("package JSON");
    package["dependencies"]["react"] = Value::String("18.3.0".to_owned());
    std::fs::write(
        &package_path,
        serde_json::to_vec_pretty(&package).expect("encode drifted package"),
    )
    .expect("write drifted package");
    assert_eq!(
        check_frontend_contract(&dependency_drift.0)
            .expect_err("dependency drift must fail")
            .code,
        "frontend_contract_drift"
    );

    let forbidden = TestRoot::create();
    copy_contract_inventory(&forbidden.0);
    std::fs::write(forbidden.0.join("pakage.json"), b"{}\n")
        .expect("write forbidden typo manifest");
    assert_eq!(
        check_frontend_contract(&forbidden.0)
            .expect_err("forbidden typo manifest must fail")
            .code,
        "frontend_forbidden_path_present"
    );
}

#[cfg(unix)]
#[test]
fn symlinked_root_is_rejected() {
    use std::os::unix::fs::symlink;

    let test = TestRoot::create();
    let link = test.0.join("root-link");
    symlink(repository_root(), &link).expect("create root symlink");
    assert_eq!(
        check_frontend_contract(&link)
            .expect_err("symlinked root must fail")
            .code,
        "frontend_unsafe_path"
    );
}
