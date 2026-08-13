use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_frontend_contract::{
    canonical_delivery_receipt_json, canonical_receipt_json, canonical_smoke_receipt_json,
    canonical_viewer_browser_smoke_receipt_json, canonical_viewer_manifest_receipt_json,
    canonical_viewer_server_receipt_json, canonical_workbench_prototype_receipt_json,
    check_frontend_contract, check_frontend_delivery, check_viewer_manifest,
    check_workbench_prototype, plan_viewer_server, run_frontend_smoke, run_viewer_browser_smoke,
};

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

fn write_delivery_fixture(root: &Path) {
    let assets = root.join("dist/assets");
    std::fs::create_dir_all(&assets).expect("create delivery assets");
    std::fs::create_dir_all(root.join("dist/src/structure-viewer"))
        .expect("create viewer entry parent");
    std::fs::write(
        root.join("dist/index.html"),
        b"<html><head><link href=\"/assets/workbench.css?v=1\"></head><body><div id=\"root\"></div><script src=\"/assets/workbench-a1.js\"></script></body></html>\n",
    )
    .expect("write workbench entry");
    std::fs::write(
        root.join("dist/src/structure-viewer/index.html"),
        b"<html><body data-si-shell=\"product\" data-viewer-workflow=\"model\"><script src=\"../../../assets/viewer-b2.js#entry\"></script></body></html>\n",
    )
    .expect("write viewer entry");
    std::fs::write(assets.join("workbench.css"), b"body{}\n").expect("write stylesheet");
    std::fs::write(
        assets.join("workbench-a1.js"),
        b"const viewer='src/structure-viewer/index.html';const legacy=()=>import('./App-c3.js');\n",
    )
    .expect("write workbench asset");
    std::fs::write(assets.join("viewer-b2.js"), b"const viewer=true;\n")
        .expect("write viewer asset");
    std::fs::write(
        assets.join("App-c3.js"),
        b"const markers=['Structural Signal Desk','native-authoring-controls','release-gap-review-state'];\n",
    )
    .expect("write legacy chunk");
}

fn write_viewer_manifest_and_projection(root: &Path, manifest: &str) {
    let body = manifest.strip_suffix('\n').expect("manifest trailing LF");
    assert!(!body.ends_with('\n'));
    let manifest_path = root.join("src/structure-viewer/viewer-project-manifest.v1.json");
    let projection_path = root.join("src/structure-viewer/viewer-project-manifest-data.js");
    std::fs::write(&manifest_path, manifest).expect("write Viewer manifest");
    let projection = format!(
        "/* Generated from viewer-project-manifest.v1.json; checked by structural-frontend-contract. */\nexport const DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST = {body};\n"
    );
    std::fs::write(&projection_path, projection).expect("write Viewer manifest projection");
}

#[cfg(unix)]
fn write_fake_npm(root: &Path, script: &[u8]) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let bin = root.join("fake-bin");
    std::fs::create_dir(&bin).expect("create fake bin");
    let npm = bin.join("npm");
    std::fs::write(&npm, script).expect("write fake npm");
    let mut permissions = std::fs::metadata(&npm)
        .expect("fake npm metadata")
        .permissions();
    permissions.set_mode(0o700);
    std::fs::set_permissions(&npm, permissions).expect("make fake npm executable");
    bin
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
    assert!(first.source_map_sha256.starts_with("sha256:"));
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
fn frontend_smoke_dry_run_is_deterministic_native_and_process_free() {
    let root = repository_root();
    let first = run_frontend_smoke(&root, true).expect("frontend smoke dry-run");
    let second = run_frontend_smoke(&root, true).expect("repeat frontend smoke dry-run");
    assert_eq!(first, second);
    assert_eq!(first.mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert_eq!(
        first.logical_commands,
        vec![
            vec!["npm".to_owned(), "ci".to_owned()],
            vec!["npm".to_owned(), "run".to_owned(), "build".to_owned()],
        ]
    );
    assert_eq!(first.direct_processes_spawned, 0);
    assert!(first.successful_exit_codes.is_empty());
    assert!(first.delivery_receipt_hash.is_none());
    assert_eq!(
        first.network_access_accounting,
        "not_instrumented_npm_ci_may_access_registry"
    );
    let encoded = canonical_smoke_receipt_json(&first).expect("canonical smoke receipt");
    let value: Value = serde_json::from_str(&encoded).expect("smoke receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn tracked_workbench_prototype_contract_is_conservative_and_self_hashed() {
    let root = repository_root();
    let first = check_workbench_prototype(&root).expect("tracked Workbench prototype contract");
    let second = check_workbench_prototype(&root).expect("repeat Workbench prototype contract");
    assert_eq!(first, second);
    assert_eq!(first.data_mode, "demo");
    assert_eq!(first.canonical_state_count, 6);
    assert_eq!(first.status_states["solver_connected"], "BLOCKED");
    assert_eq!(first.status_states["p0"], "UNAVAILABLE");
    assert_eq!(first.status_states["p1"], "UNAVAILABLE");
    assert_eq!(first.status_states["gpu"], "MISSING");
    assert!(!first.status_states.values().any(|state| state == "LIVE"));
    assert_eq!(first.commands_executed, 0);
    assert_eq!(first.network_access_count, 0);
    assert!(!first.browser_executed);
    let encoded = canonical_workbench_prototype_receipt_json(&first)
        .expect("canonical Workbench prototype receipt");
    let value: Value = serde_json::from_str(&encoded).expect("prototype receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn tracked_viewer_server_plan_is_loopback_bounded_and_self_hashed() {
    let root = repository_root();
    let first = plan_viewer_server(&root, "127.0.0.1", 8765).expect("Viewer server plan");
    let second = plan_viewer_server(&root, "127.0.0.1", 8765).expect("repeat server plan");
    assert_eq!(first, second);
    assert_eq!(first.mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert!(first.loopback_only);
    assert_eq!(first.listener_count, 0);
    assert_eq!(first.external_network_access_count, 0);
    assert_eq!(first.commands_executed, 0);
    assert_eq!(
        first.viewer_url,
        "http://127.0.0.1:8765/src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized"
    );
    assert!(first
        .allowed_path_prefixes
        .iter()
        .any(|prefix| prefix == "src/structure-viewer/"));
    assert!(!first
        .allowed_path_prefixes
        .iter()
        .any(|prefix| prefix.starts_with('.') || prefix == "/"));
    let encoded = canonical_viewer_server_receipt_json(&first).expect("canonical server receipt");
    let value: Value = serde_json::from_str(&encoded).expect("server receipt JSON");
    verify_receipt_hash(&value);

    let error = plan_viewer_server(&root, "0.0.0.0", 8765)
        .expect_err("non-loopback Viewer server must fail");
    assert_eq!(error.code, "viewer_server_host_forbidden");
}

#[test]
fn viewer_browser_smoke_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let first =
        run_viewer_browser_smoke(&root, "minimal", true).expect("Viewer browser smoke dry-run");
    let second = run_viewer_browser_smoke(&root, "minimal", true)
        .expect("repeat Viewer browser smoke dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.browser_smoke_mode, "minimal");
    assert_eq!(first.status, "planned");
    assert!(first.frontend_contract_receipt_hash.starts_with("sha256:"));
    assert_eq!(first.playwright_cli_sha256, None);
    assert_eq!(
        first.logical_command,
        vec![
            "node".to_owned(),
            "node_modules/@playwright/test/cli.js".to_owned(),
            "test".to_owned(),
            "tests/frontend/structure-viewer-smoke.spec.ts".to_owned(),
            "--reporter=line".to_owned(),
        ]
    );
    assert!(first.node_runtime_required);
    assert!(first.browser_runtime_required);
    assert_eq!(first.loopback_listener_count, 0);
    assert_eq!(first.direct_processes_spawned, 0);
    assert_eq!(first.successful_exit_code, None);
    assert_eq!(first.request_error_count, 0);
    assert_eq!(
        first.external_network_access_accounting,
        "not_instrumented_browser_page_requests"
    );
    assert!(first.deterministic_receipt);
    let encoded = canonical_viewer_browser_smoke_receipt_json(&first)
        .expect("canonical Viewer browser smoke receipt");
    let value: Value = serde_json::from_str(&encoded).expect("browser smoke receipt JSON");
    verify_receipt_hash(&value);

    let error = run_viewer_browser_smoke(&root, "widened", true)
        .expect_err("unknown Viewer browser smoke mode must fail");
    assert_eq!(error.code, "viewer_browser_smoke_mode_invalid");
}

#[test]
fn clean_environment_viewer_browser_smoke_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["browser-smoke", "--root"])
        .arg(&root)
        .args(["--mode", "full", "--dry-run"])
        .env_clear()
        .output()
        .expect("run Viewer browser smoke dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("browser smoke receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "viewer_browser_smoke");
    assert_eq!(value["browser_smoke_mode"], "full");
    assert_eq!(value["loopback_listener_count"], 0);
    assert_eq!(value["direct_processes_spawned"], 0);
    assert!(value["frontend_contract_receipt_hash"]
        .as_str()
        .is_some_and(|hash| hash.starts_with("sha256:")));
    assert!(value["playwright_cli_sha256"].is_null());
    verify_receipt_hash(&value);
}

#[test]
fn viewer_browser_smoke_requires_the_pinned_runtime_before_live_side_effects() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let error = run_viewer_browser_smoke(&test.0, "minimal", false)
        .expect_err("missing pinned Playwright CLI must fail");
    assert_eq!(error.code, "frontend_required_file_missing");
    assert!(error
        .detail
        .contains("node_modules/@playwright/test/cli.js"));
}

#[test]
fn clean_environment_viewer_server_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args([
            "serve",
            "--root",
            root.to_str().expect("UTF-8 repo root"),
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--dry-run",
        ])
        .env_clear()
        .output()
        .expect("run Viewer server dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("server receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "viewer_server");
    assert_eq!(value["listener_count"], 0);
    verify_receipt_hash(&value);
}

#[test]
fn workbench_prototype_duplicate_fixture_and_inner_html_fail_closed() {
    let duplicate = TestRoot::create();
    copy_contract_inventory(&duplicate.0);
    let demo_path = duplicate
        .0
        .join("prototype/structural-workbench/demo-case.json");
    let bytes = std::fs::read(&demo_path).expect("read demo fixture");
    let mut drift = b"{\"schema_version\":\"duplicate\",".to_vec();
    drift.extend_from_slice(bytes.strip_prefix(b"{").expect("fixture object"));
    std::fs::write(&demo_path, drift).expect("write duplicate demo fixture");
    let error = check_workbench_prototype(&duplicate.0).expect_err("duplicate key must fail");
    assert_eq!(error.code, "workbench_prototype_demo_json_invalid");

    let unsafe_source = TestRoot::create();
    copy_contract_inventory(&unsafe_source.0);
    let app_path = unsafe_source
        .0
        .join("prototype/structural-workbench/app.js");
    let mut app = std::fs::read(&app_path).expect("read prototype app");
    app.extend_from_slice(b"\ndocument.body.innerHTML = 'unsafe';\n");
    std::fs::write(&app_path, app).expect("write unsafe prototype app");
    let error = check_workbench_prototype(&unsafe_source.0).expect_err("innerHTML must fail");
    assert_eq!(error.code, "workbench_prototype_source_drift");
}

#[test]
fn clean_environment_prototype_cli_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["prototype", "--root"])
        .arg(&root)
        .env_clear()
        .output()
        .expect("run native Workbench prototype contract");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("prototype receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "workbench_prototype_check");
    verify_receipt_hash(&value);
}

#[cfg(unix)]
#[test]
fn clean_environment_smoke_cli_owns_exact_process_order_and_delivery_postcheck() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_delivery_fixture(&test.0);
    let bin = write_fake_npm(
        &test.0,
        b"#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$PWD/npm-invocations.log\"\nexit 0\n",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["smoke", "--root"])
        .arg(&test.0)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("run native frontend smoke");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    assert_eq!(
        std::fs::read_to_string(test.0.join("npm-invocations.log"))
            .expect("read npm invocation log"),
        "ci\nrun build\n"
    );
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("smoke receipt JSON");
    assert_eq!(value["mode"], "execute");
    assert_eq!(value["status"], "ready");
    assert_eq!(value["direct_processes_spawned"], 2);
    assert_eq!(value["successful_exit_codes"], serde_json::json!([0, 0]));
    assert!(value["delivery_receipt_hash"]
        .as_str()
        .is_some_and(|hash| hash.starts_with("sha256:")));
    verify_receipt_hash(&value);
}

#[cfg(unix)]
#[test]
fn frontend_smoke_stops_after_the_first_nonzero_child_exit() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_npm(
        &test.0,
        b"#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$PWD/npm-invocations.log\"\nexit 17\n",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["smoke", "--root"])
        .arg(&test.0)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("run failing native frontend smoke");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    assert_eq!(
        std::fs::read_to_string(test.0.join("npm-invocations.log"))
            .expect("read npm invocation log"),
        "ci\n"
    );
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("error JSON");
    assert_eq!(
        value["schema_version"],
        "structural-frontend-contract-error.v1"
    );
    assert_eq!(value["code"], "frontend_smoke_command_failed");
    assert!(value["detail"]
        .as_str()
        .is_some_and(|detail| detail.contains("command 1 failed with exit code 17")));
}

#[cfg(unix)]
#[test]
fn frontend_smoke_rejects_contract_mutation_before_delivery_publication() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_delivery_fixture(&test.0);
    let bin = write_fake_npm(
        &test.0,
        b"#!/bin/sh\nprintf ' ' >> \"$PWD/package.json\"\nexit 0\n",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["smoke", "--root"])
        .arg(&test.0)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("run mutating native frontend smoke");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("error JSON");
    assert_eq!(value["code"], "frontend_smoke_contract_changed");
    assert!(value["detail"]
        .as_str()
        .is_some_and(|detail| detail.contains("changed while the smoke sequence executed")));
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
fn delivery_check_is_deterministic_hash_bound_and_preserves_the_v1_contract() {
    let test = TestRoot::create();
    write_delivery_fixture(&test.0);
    let first = check_frontend_delivery(&test.0).expect("delivery check");
    let second = check_frontend_delivery(&test.0).expect("repeated delivery check");
    assert_eq!(first, second);
    assert_eq!(first.contract, "workbench_viewer_production_delivery_v1");
    assert_eq!(first.status, "ready");
    assert_eq!(first.workbench_entry, "dist/index.html");
    assert_eq!(first.viewer_entry, "dist/src/structure-viewer/index.html");
    assert_eq!(first.legacy_chunk, "dist/assets/App-c3.js");
    assert_eq!(first.workbench_asset_count, 2);
    assert_eq!(first.viewer_asset_count, 1);
    assert_eq!(first.legacy_marker_count, 3);
    assert_eq!(first.commands_executed, 0);
    assert_eq!(first.network_access_count, 0);
    let encoded = canonical_delivery_receipt_json(&first).expect("canonical delivery receipt");
    let value: Value = serde_json::from_str(&encoded).expect("delivery receipt JSON");
    verify_receipt_hash(&value);

    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["delivery", "--root", "."])
        .current_dir(&test.0)
        .env_clear()
        .output()
        .expect("run delivery CLI");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let cli_value: Value = serde_json::from_slice(bytes).expect("CLI delivery receipt");
    assert_eq!(
        canonicalize_model_ir_v2(&cli_value)
            .expect("canonical CLI delivery receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(cli_value, value);
}

#[test]
fn tracked_viewer_manifest_is_neutral_deterministic_and_self_hashed() {
    let root = repository_root();
    let first = check_viewer_manifest(&root).expect("tracked Viewer manifest");
    let second = check_viewer_manifest(&root).expect("repeated Viewer manifest");
    assert_eq!(first, second);
    assert!(first.contract_pass);
    assert_eq!(first.reason_code, "PASS");
    assert_eq!(first.summary.project_count, 3);
    assert_eq!(first.summary.drawing_count, 11);
    assert_eq!(first.summary.variant_count, 32);
    assert_eq!(first.release_triple_count, 8);
    assert_eq!(first.path_check_count, 65);
    assert_eq!(first.artifact_count_check_count, 9);
    assert!(first.missing_path_count > 0);
    assert_eq!(first.commands_executed, 0);
    assert_eq!(first.network_access_count, 0);
    assert!(first.errors.is_empty());
    assert!(first
        .warnings
        .iter()
        .any(|warning| warning.contains("generated release artifact")));
    let encoded = canonical_viewer_manifest_receipt_json(&first).expect("canonical Viewer receipt");
    let value: Value = serde_json::from_str(&encoded).expect("Viewer receipt JSON");
    verify_receipt_hash(&value);

    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-manifest", "--root", "."])
        .current_dir(&root)
        .env_clear()
        .output()
        .expect("run Viewer manifest CLI");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let cli_value: Value = serde_json::from_slice(bytes).expect("CLI Viewer receipt");
    assert_eq!(
        canonicalize_model_ir_v2(&cli_value)
            .expect("canonical CLI Viewer receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(cli_value, value);
}

#[test]
fn viewer_manifest_duplicate_projection_and_repo_escape_fail_closed() {
    let duplicate = TestRoot::create();
    copy_contract_inventory(&duplicate.0);
    write_viewer_manifest_and_projection(
        &duplicate.0,
        "{\"schema_version\":\"structure-viewer-project-manifest.v1\",\"schema_version\":\"forged\"}\n",
    );
    assert_eq!(
        check_viewer_manifest(&duplicate.0)
            .expect_err("duplicate manifest key must fail")
            .code,
        "viewer_manifest_json_invalid"
    );

    let projection = TestRoot::create();
    copy_contract_inventory(&projection.0);
    std::fs::write(
        projection
            .0
            .join("src/structure-viewer/viewer-project-manifest-data.js"),
        b"export const DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST = {};\n",
    )
    .expect("write forged projection");
    assert_eq!(
        check_viewer_manifest(&projection.0)
            .expect_err("projection drift must fail")
            .code,
        "viewer_manifest_javascript_projection_drift"
    );

    let escaped = TestRoot::create();
    copy_contract_inventory(&escaped.0);
    let path = escaped
        .0
        .join("src/structure-viewer/viewer-project-manifest.v1.json");
    let mut manifest: Value =
        serde_json::from_slice(&std::fs::read(&path).expect("read Viewer manifest"))
            .expect("Viewer manifest JSON");
    manifest["projects"][2]["drawings"][0]["artifact_path"] =
        Value::String("../../../outside.json".to_owned());
    let text = format!(
        "{}\n",
        serde_json::to_string_pretty(&manifest).expect("encode escaped manifest")
    );
    write_viewer_manifest_and_projection(&escaped.0, &text);
    let error = check_viewer_manifest(&escaped.0).expect_err("repo escape must fail");
    assert_eq!(error.code, "viewer_manifest_contract_drift");
    assert!(error
        .detail
        .contains("escapes or violates the repo boundary"));
}

#[test]
fn delivery_check_rejects_marker_asset_and_chunk_drift() {
    let eager = TestRoot::create();
    write_delivery_fixture(&eager.0);
    std::fs::write(
        eager.0.join("dist/assets/workbench-a1.js"),
        b"const viewer='src/structure-viewer/index.html';const marker='Structural Signal Desk';const legacy=()=>import('./App-c3.js');\n",
    )
    .expect("write eager marker drift");
    assert_eq!(
        check_frontend_delivery(&eager.0)
            .expect_err("eager legacy marker must fail")
            .code,
        "frontend_delivery_contract_drift"
    );

    let missing = TestRoot::create();
    write_delivery_fixture(&missing.0);
    std::fs::remove_file(missing.0.join("dist/assets/viewer-b2.js"))
        .expect("remove referenced asset");
    assert_eq!(
        check_frontend_delivery(&missing.0)
            .expect_err("missing emitted asset must fail")
            .code,
        "frontend_delivery_contract_drift"
    );

    let multiple = TestRoot::create();
    write_delivery_fixture(&multiple.0);
    std::fs::write(
        multiple.0.join("dist/assets/workbench-a1.js"),
        b"const viewer='src/structure-viewer/index.html';import('./App-c3.js');import('assets/App-d4.js');\n",
    )
    .expect("write multiple legacy chunks");
    assert_eq!(
        check_frontend_delivery(&multiple.0)
            .expect_err("multiple lazy legacy chunks must fail")
            .code,
        "frontend_delivery_contract_drift"
    );

    let fallback = TestRoot::create();
    write_delivery_fixture(&fallback.0);
    std::fs::write(
        fallback.0.join("dist/src/structure-viewer/index.html"),
        b"<html><body data-si-shell=\"product\" data-viewer-workflow=\"model\" data-wb2-root><script src=\"/assets/viewer-b2.js\"></script></body></html>\n",
    )
    .expect("write fallback marker drift");
    assert_eq!(
        check_frontend_delivery(&fallback.0)
            .expect_err("Workbench fallback must fail")
            .code,
        "frontend_delivery_contract_drift"
    );
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
fn symlinked_root_and_delivery_asset_are_rejected() {
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

    let delivery = TestRoot::create();
    write_delivery_fixture(&delivery.0);
    let asset = delivery.0.join("dist/assets/viewer-b2.js");
    std::fs::remove_file(&asset).expect("remove viewer asset before symlink");
    symlink("App-c3.js", &asset).expect("create emitted-asset symlink");
    assert_eq!(
        check_frontend_delivery(&delivery.0)
            .expect_err("symlinked emitted asset must fail")
            .code,
        "frontend_delivery_contract_drift"
    );
}
