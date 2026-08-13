use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};
use structural_catalog::{
    build_benchmark_catalog, canonical_receipt_json, check_benchmark_catalog,
    BenchmarkCatalogBuildRequest,
};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

const GENERATED_AT: &str = "2026-08-13T00:00:00Z";
const REPORT_DIRECTORY: &str = "implementation/phase1/open_data/irregular/collected/reports";
const PEER_DIRECTORY: &str = "implementation/phase1/open_data/pbd_hinge/peer_spd_specimens";
static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TestRoot(PathBuf);

impl TestRoot {
    fn create() -> Self {
        for _ in 0..1024 {
            let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "structural-catalog-test-{}-{sequence}",
                std::process::id()
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => panic!("create test root failed: {error}"),
            }
        }
        panic!("could not allocate catalog test root");
    }
}

impl Drop for TestRoot {
    fn drop(&mut self) {
        let _ignored = std::fs::remove_dir_all(&self.0);
    }
}

fn write_json(path: &Path, value: &Value) {
    std::fs::create_dir_all(path.parent().expect("fixture parent")).expect("create fixture parent");
    let mut bytes = serde_json::to_vec_pretty(value).expect("encode fixture JSON");
    bytes.push(b'\n');
    std::fs::write(path, bytes).expect("write fixture JSON");
}

fn report(id: &str, source_format: &str, index: u64) -> Value {
    json!({
        "source_id": id,
        "title": format!("Fixture {id}"),
        "source_urls": [format!("https://example.invalid/{id}")],
        "source_format": source_format,
        "family_id": "fixture_family",
        "sha256": format!("{index:064x}"),
        "source_exists": true,
        "bytes_copied": 1024 + index,
    })
}

fn write_valid_sources(root: &Path) {
    let report_root = root.join(REPORT_DIRECTORY);
    write_json(
        &report_root.join("01-lux.json"),
        &report("luxinzheng_megatall_tcl_model1_local", "tcl", 1),
    );
    write_json(
        &report_root.join("02-midas.json"),
        &report("midas_multifamily_building_meb_local", "meb", 2),
    );
    write_json(
        &report_root.join("03-ifc.json"),
        &report("fixture_ifc_case", "ifc", 3),
    );
    write_json(
        &root
            .join(PEER_DIRECTORY)
            .join("peer_spd_rc_column_rectangular_seed_01.specimen_page.json"),
        &json!({
            "seed_id": "peer_spd_rc_column_rectangular_seed_01",
            "page_title": "PEER fixture",
            "specimen_id": "121",
            "specimen_display_url": "https://example.invalid/peer/121",
            "hysteresis_link_candidates": [{"href": "https://example.invalid/data/121"}],
        }),
    );
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
    Command::new(env!("CARGO_BIN_EXE_structural-catalog"))
        .args(arguments)
        .env_clear()
        .output()
        .expect("run structural-catalog")
}

#[test]
fn deterministic_build_and_check_preserve_candidate_boundaries() {
    let test = TestRoot::create();
    write_valid_sources(&test.0);
    let first = test.0.join("catalog-a.json");
    let second = test.0.join("catalog-b.json");
    let first_receipt = build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
        source_root: &test.0,
        output: &first,
        generated_at: GENERATED_AT,
    })
    .expect("first deterministic catalog build");
    let second_receipt = build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
        source_root: &test.0,
        output: &second,
        generated_at: GENERATED_AT,
    })
    .expect("second deterministic catalog build");
    assert_eq!(
        std::fs::read(&first).unwrap(),
        std::fs::read(&second).unwrap()
    );
    assert_eq!(
        first_receipt.output_catalog_sha256,
        second_receipt.output_catalog_sha256
    );
    assert_eq!(first_receipt.report_count, 3);
    assert_eq!(first_receipt.peer_specimen_count, 1);
    assert_eq!(first_receipt.case_count, 4);
    assert_eq!(first_receipt.commands_executed, 0);
    assert_eq!(first_receipt.network_access_count, 0);
    assert_eq!(
        first_receipt.first_validation_targets,
        vec![
            "luxinzheng_megatall_tcl_model1_local",
            "midas_multifamily_building_meb_local",
            "fixture_ifc_case",
            "peer_spd_rc_column_rectangular_seed_01",
        ]
    );

    let catalog: Value = serde_json::from_slice(&std::fs::read(&first).unwrap()).unwrap();
    assert_eq!(catalog["schema_version"], "benchmark-catalog.v2");
    assert_eq!(catalog["catalog_kind"], "candidate");
    assert_eq!(catalog["generated_by"], "structural-catalog");
    assert!(catalog["cases"]
        .as_array()
        .unwrap()
        .iter()
        .all(|case| case["verification"]["runnerId"].is_null()));
    assert_eq!(
        catalog["cases"][2]["truthClass"], "geometry_only",
        "IFC remains geometry-only"
    );

    let check = check_benchmark_catalog(&test.0, &first).expect("exact catalog check");
    assert_eq!(check.action, "check");
    assert_eq!(
        check.output_catalog_sha256,
        first_receipt.output_catalog_sha256
    );
    let receipt_json = canonical_receipt_json(&check).expect("canonical check receipt");
    verify_receipt_hash(&serde_json::from_str(&receipt_json).unwrap());

    std::fs::write(
        &first,
        [std::fs::read(&first).unwrap(), b" \n".to_vec()].concat(),
    )
    .expect("append catalog drift");
    assert_eq!(
        check_benchmark_catalog(&test.0, &first)
            .expect_err("noncanonical output drift must fail")
            .code,
        "catalog_output_drift"
    );

    let invalid = test.0.join("invalid-timestamp.json");
    assert_eq!(
        build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
            source_root: &test.0,
            output: &invalid,
            generated_at: "not-a-timestamp",
        })
        .expect_err("invalid timestamp must fail")
        .code,
        "catalog_generated_at_invalid"
    );
    assert!(!invalid.exists());
}

#[test]
fn source_validation_rejects_duplicate_keys_bad_checksums_and_duplicate_ids() {
    let duplicate_key = TestRoot::create();
    write_valid_sources(&duplicate_key.0);
    std::fs::write(
        duplicate_key.0.join(REPORT_DIRECTORY).join("01-lux.json"),
        b"{\"source_id\":\"a\",\"source_id\":\"b\"}\n",
    )
    .expect("write duplicate-key report");
    assert_eq!(
        build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
            source_root: &duplicate_key.0,
            output: &duplicate_key.0.join("catalog.json"),
            generated_at: GENERATED_AT,
        })
        .expect_err("duplicate JSON key must fail")
        .code,
        "catalog_source_json_invalid"
    );

    let bad_checksum = TestRoot::create();
    write_valid_sources(&bad_checksum.0);
    let mut bad = report("luxinzheng_megatall_tcl_model1_local", "tcl", 1);
    bad["sha256"] = json!("not-a-sha256");
    write_json(
        &bad_checksum.0.join(REPORT_DIRECTORY).join("01-lux.json"),
        &bad,
    );
    assert_eq!(
        build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
            source_root: &bad_checksum.0,
            output: &bad_checksum.0.join("catalog.json"),
            generated_at: GENERATED_AT,
        })
        .expect_err("invalid source checksum must fail")
        .code,
        "catalog_source_checksum_invalid"
    );

    let duplicate_id = TestRoot::create();
    write_valid_sources(&duplicate_id.0);
    write_json(
        &duplicate_id
            .0
            .join(REPORT_DIRECTORY)
            .join("04-duplicate.json"),
        &report("fixture_ifc_case", "ifc", 4),
    );
    assert_eq!(
        build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
            source_root: &duplicate_id.0,
            output: &duplicate_id.0.join("catalog.json"),
            generated_at: GENERATED_AT,
        })
        .expect_err("duplicate case ID must fail")
        .code,
        "catalog_duplicate_case_id"
    );
}

#[cfg(unix)]
#[test]
fn source_validation_rejects_symlinked_metadata() {
    use std::os::unix::fs::symlink;

    let test = TestRoot::create();
    write_valid_sources(&test.0);
    let source = test.0.join(REPORT_DIRECTORY).join("01-lux.json");
    let target = test.0.join(REPORT_DIRECTORY).join("02-midas.json");
    std::fs::remove_file(&source).expect("remove report before symlink");
    symlink(target, source).expect("create report symlink");
    assert_eq!(
        build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
            source_root: &test.0,
            output: &test.0.join("catalog.json"),
            generated_at: GENERATED_AT,
        })
        .expect_err("source symlink must fail")
        .code,
        "catalog_source_not_bounded_regular_file"
    );
}

#[test]
fn tracked_26_case_catalog_is_an_exact_native_projection() {
    let repository_root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root");
    let catalog = repository_root.join("native/catalog/benchmark-catalog-v2.json");
    let receipt = check_benchmark_catalog(&repository_root, &catalog)
        .expect("tracked catalog must exactly match native source projection");
    assert_eq!(receipt.report_count, 21);
    assert_eq!(receipt.peer_specimen_count, 5);
    assert_eq!(receipt.case_count, 26);
    assert_eq!(receipt.first_validation_targets.len(), 4);
}

#[test]
fn clean_environment_cli_emits_canonical_self_hashed_receipt() {
    let test = TestRoot::create();
    write_valid_sources(&test.0);
    let catalog = test.0.join("catalog.json");
    build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
        source_root: &test.0,
        output: &catalog,
        generated_at: GENERATED_AT,
    })
    .expect("catalog fixture build");
    let output = run_binary(&[
        OsStr::new("check"),
        OsStr::new("--root"),
        test.0.as_os_str(),
        OsStr::new("--catalog"),
        catalog.as_os_str(),
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
    verify_receipt_hash(&value);
}
