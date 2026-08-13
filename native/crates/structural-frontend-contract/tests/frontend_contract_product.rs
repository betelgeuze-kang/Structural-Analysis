use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;
use structural_frontend_contract::{
    canonical_delivery_receipt_json, canonical_receipt_json, canonical_smoke_receipt_json,
    canonical_viewer_browser_smoke_receipt_json, canonical_viewer_manifest_receipt_json,
    canonical_viewer_performance_probe_receipt_json,
    canonical_viewer_report_pdf_export_receipt_json,
    canonical_viewer_report_pdf_smoke_receipt_json, canonical_viewer_sample_workflow_receipt_json,
    canonical_viewer_server_receipt_json, canonical_viewer_visual_regression_receipt_json,
    canonical_workbench_prototype_browser_smoke_receipt_json,
    canonical_workbench_prototype_receipt_json, canonical_workbench_v2_browser_smoke_receipt_json,
    check_frontend_contract, check_frontend_delivery, check_viewer_manifest,
    check_workbench_prototype, plan_viewer_server, run_frontend_smoke, run_viewer_browser_smoke,
    run_viewer_performance_probe, run_viewer_report_pdf_export, run_viewer_report_pdf_smoke,
    run_viewer_sample_workflow, run_viewer_visual_regression,
    run_workbench_prototype_browser_smoke, run_workbench_v2_browser_smoke,
    ViewerPerformanceProbeOptions, ViewerReportPdfExportOptions, ViewerReportPdfSmokeOptions,
    ViewerSampleWorkflowOptions, ViewerVisualRegressionOptions,
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
    write_fake_executable(root, "npm", script)
}

#[cfg(unix)]
fn write_fake_executable(root: &Path, name: &str, script: &[u8]) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let bin = root.join("fake-bin");
    std::fs::create_dir_all(&bin).expect("create fake bin");
    let executable = bin.join(name);
    std::fs::write(&executable, script).expect("write fake executable");
    let mut permissions = std::fs::metadata(&executable)
        .expect("fake executable metadata")
        .permissions();
    permissions.set_mode(0o700);
    std::fs::set_permissions(&executable, permissions).expect("make fake executable runnable");
    bin
}

#[cfg(unix)]
fn performance_source_rows(root: &Path) -> Vec<Value> {
    let tracked = [
        ("viewer_index", "src/structure-viewer/index.html"),
        (
            "browser_performance_probe",
            "scripts/measure-structure-viewer-performance.mjs",
        ),
        (
            "canvas_frame_probe",
            "scripts/structure-viewer-canvas-frame.mjs",
        ),
        (
            "frontend_smoke_spec",
            "tests/frontend/structure-viewer-smoke.spec.ts",
        ),
    ];
    tracked
        .iter()
        .map(|(label, relative)| {
            let bytes = std::fs::read(root.join(relative)).expect("read performance source");
            let identity = sha256_identity(&bytes);
            serde_json::json!({
                "label": label,
                "path": relative,
                "available": true,
                "bytes": bytes.len(),
                "sha256": identity.strip_prefix("sha256:").expect("SHA prefix"),
            })
        })
        .collect()
}

#[cfg(unix)]
fn write_performance_probe_fixture(root: &Path, output: &Path) {
    let source_rows = performance_source_rows(root);
    let artifact = serde_json::json!({
        "schema_version": "structure-viewer-browser-performance-probe.v1",
        "generated_at": "2026-08-13T12:34:56.789Z",
        "contract_pass": true,
        "reason_code": "PASS",
        "summary_line": "Structure viewer browser performance probe: PASS | ready=125ms | fps=60.0 | mode=local_browser_probe",
        "probe_mode": "local_browser_probe",
        "measured_browser_probe": true,
        "live_performance_claim": false,
        "independent_product_claim": false,
        "claim_boundary": "Local browser performance smoke only; not a normalized customer hardware FPS claim.",
        "query": "project=midas33_release&drawing=midas33_optimized&variant=optimized",
        "output_path": output.to_str().expect("UTF-8 performance output"),
        "budgets": {
            "max_ready_ms": 60000,
            "min_average_fps": 5,
            "sample_ms": 1500,
        },
        "probe": {
            "url": "http://127.0.0.1:4173/src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized",
            "readyMs": 125,
            "viewport": {"width": 1440, "height": 1000},
            "canvasMetrics": {
                "nonBlank": true,
                "canvasWidth": 1440,
                "canvasHeight": 1000,
                "sampleWidth": 180,
                "sampleHeight": 120,
                "significantPixelCount": 2400,
                "significantPixelRatio": 0.111_111_111_111_111_1,
                "bbox": {"minX": 10, "minY": 12, "maxX": 169, "maxY": 107, "width": 160, "height": 96},
                "coverageWidth": 0.888_888_888_888_888_8,
                "coverageHeight": 0.8,
                "bboxAspectRatio": 1.666_666_666_666_666_7,
                "centerX": 0.5,
                "centerY": 0.5,
            },
            "rafSample": {
                "frameCount": 91,
                "elapsedMs": 1500,
                "averageFps": 60,
                "averageFrameMs": 16.666_666_666_666_668,
                "p95FrameMs": 17,
                "maxFrameMs": 19,
            },
            "navigationTiming": {
                "domContentLoadedMs": 50,
                "loadEventEndMs": 75,
                "responseEndMs": 20,
            },
            "viewerState": {
                "title": "Structural Insight",
                "stageVariant": "optimized",
                "projectStatus": "ready",
                "statsText": "Members 11,334",
            },
            "browserErrors": [],
        },
        "source_rows": source_rows,
        "residual_live_work": [
            "Run the same probe across a defined browser/device/GPU matrix.",
            "Promote customer-hardware FPS and interaction latency budgets only after repeatable lab baselines exist.",
            "Attach screenshot visual regression baselines for the same query and view modes."
        ],
        "blockers": [],
    });
    std::fs::write(
        root.join("performance-probe-fixture.json"),
        format!(
            "{}\n",
            serde_json::to_string_pretty(&artifact).expect("encode performance fixture")
        ),
    )
    .expect("write performance probe fixture");
}

#[cfg(unix)]
fn write_visual_regression_fixture(root: &Path) {
    let baseline_path =
        root.join("implementation/phase1/structure_viewer_visual_regression_baseline.json");
    let mut artifact: Value = serde_json::from_slice(
        &std::fs::read(&baseline_path).expect("read visual-regression baseline"),
    )
    .expect("visual-regression baseline JSON");
    let rows = artifact["case_rows"]
        .as_array()
        .expect("visual-regression case rows")
        .clone();
    let compare_rows = rows
        .iter()
        .map(|row| {
            let markers = &row["markers"];
            serde_json::json!({
                "id": row["id"],
                "status": "pass",
                "blockers": [],
                "signature_delta": {
                    "comparable": true,
                    "mean_abs_diff": 0,
                    "max_abs_diff": 0,
                },
                "coverage_width_delta": 0,
                "coverage_height_delta": 0,
                "center_x_delta": 0,
                "center_y_delta": 0,
                "expected_render_mode": row["expected_render_mode"],
                "actual_render_mode": markers["renderMode"],
                "expected_view_preset": row["expected_view_preset"],
                "actual_view_preset": markers["viewPreset"],
                "expected_workflow_state": row["expected_workflow_state"],
                "expected_selected_member": row["expected_selected_member"],
                "actual_selected_text": markers["selectedText"],
                "expected_comparison_filter": row["expected_comparison_filter"],
                "actual_comparison_filter": markers["comparisonFilter"],
                "expected_evidence_ingest_kind": row["expected_evidence_ingest_kind"],
                "actual_evidence_ingest_kind": markers["evidenceIngestKind"],
                "expected_renderable_payload_kind": row["expected_renderable_payload_kind"],
                "actual_renderable_payload_kind": markers["renderablePayloadKind"],
                "expected_section_edit_target": row["expected_section_edit_target"],
                "actual_section_edit_status": markers["sectionEditStatus"],
                "expected_loadcomb_draft_target": row["expected_loadcomb_draft_target"],
                "actual_loadcomb_edit_status": markers["loadcombEditStatus"],
            })
        })
        .collect::<Vec<_>>();
    artifact["generated_at"] = Value::String("2026-08-13T12:34:56.789Z".to_owned());
    artifact["mode"] = Value::String("verify".to_owned());
    artifact["summary_line"] = Value::String(
        "Structure viewer visual regression: PASS | cases=11/11 | mode=verify".to_owned(),
    );
    artifact["compare_rows"] = Value::Array(compare_rows);
    std::fs::write(
        root.join("visual-regression-fixture.json"),
        format!(
            "{}\n",
            serde_json::to_string(&artifact).expect("encode visual-regression fixture")
        ),
    )
    .expect("write visual-regression fixture");
}

#[cfg(unix)]
fn write_sample_workflow_fixture(root: &Path) {
    std::fs::copy(
        repository_root().join("implementation/phase1/structure_viewer_sample_workflow_smoke.json"),
        root.join("sample-workflow-fixture.json"),
    )
    .expect("copy tracked sample-workflow fixture");
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
fn prototype_browser_smoke_dry_run_is_scoped_process_free_and_self_hashed() {
    let root = repository_root();
    let first = run_workbench_prototype_browser_smoke(&root, true)
        .expect("Workbench prototype browser smoke dry-run");
    let second = run_workbench_prototype_browser_smoke(&root, true)
        .expect("repeat Workbench prototype browser smoke dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert!(first.frontend_contract_receipt_hash.starts_with("sha256:"));
    assert!(first.prototype_contract_receipt_hash.starts_with("sha256:"));
    assert!(first.spec_sha256.starts_with("sha256:"));
    assert_eq!(first.playwright_cli_sha256, None);
    assert_eq!(
        first.logical_command,
        vec![
            "node".to_owned(),
            "node_modules/@playwright/test/cli.js".to_owned(),
            "test".to_owned(),
            "tests/frontend/workbench-prototype-smoke.spec.ts".to_owned(),
            "--reporter=line".to_owned(),
        ]
    );
    assert_eq!(first.server_path_prefix, "prototype/structural-workbench/");
    assert_eq!(first.base_url_environment, "WORKBENCH_PROTOTYPE_BASE_URL");
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
    let encoded = canonical_workbench_prototype_browser_smoke_receipt_json(&first)
        .expect("canonical Workbench prototype browser smoke receipt");
    let value: Value = serde_json::from_str(&encoded).expect("prototype browser receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_prototype_browser_smoke_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["prototype-browser-smoke", "--root"])
        .arg(&root)
        .arg("--dry-run")
        .env_clear()
        .output()
        .expect("run Workbench prototype browser smoke dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("prototype browser receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "workbench_prototype_browser_smoke");
    assert_eq!(value["execution_mode"], "dry_run");
    assert_eq!(value["loopback_listener_count"], 0);
    assert_eq!(value["direct_processes_spawned"], 0);
    assert!(value["playwright_cli_sha256"].is_null());
    verify_receipt_hash(&value);
}

#[test]
fn prototype_browser_smoke_requires_pinned_runtime_before_live_side_effects() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let error = run_workbench_prototype_browser_smoke(&test.0, false)
        .expect_err("missing pinned Playwright CLI must fail");
    assert_eq!(error.code, "frontend_required_file_missing");
    assert!(error
        .detail
        .contains("node_modules/@playwright/test/cli.js"));
}

#[test]
fn workbench_v2_browser_smoke_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let first =
        run_workbench_v2_browser_smoke(&root, true).expect("Workbench v2 browser smoke dry-run");
    let second = run_workbench_v2_browser_smoke(&root, true)
        .expect("repeat Workbench v2 browser smoke dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert!(first.frontend_contract_receipt_hash.starts_with("sha256:"));
    assert_eq!(first.delivery_receipt_hash, None);
    assert_eq!(
        first.build_command,
        vec!["npm".to_owned(), "run".to_owned(), "build".to_owned()]
    );
    assert_eq!(first.build_environment["VITE_BASE_PATH"], "/");
    assert_eq!(first.specifications.len(), 6);
    assert!(first
        .specifications
        .iter()
        .all(|specification| specification.sha256.starts_with("sha256:")));
    assert!(first.json_module_loader_sha256.starts_with("sha256:"));
    assert_eq!(first.playwright_cli_sha256, None);
    assert_eq!(
        first.playwright_command,
        vec![
            "node".to_owned(),
            "node_modules/@playwright/test/cli.js".to_owned(),
            "test".to_owned(),
            "tests/frontend/workbench-v2-e2e.spec.ts".to_owned(),
            "tests/frontend/workbench-v2-unit-coordinate-guard.spec.ts".to_owned(),
            "tests/frontend/workbench-v2-live-provider-guard.spec.ts".to_owned(),
            "tests/frontend/workbench-v2-job-contract.spec.ts".to_owned(),
            "tests/frontend/workbench-v2-engineering-value-state.spec.ts".to_owned(),
            "tests/frontend/workbench-v2-status-taxonomy.spec.ts".to_owned(),
            "--reporter=line".to_owned(),
        ]
    );
    assert_eq!(first.dist_directory, "dist");
    assert_eq!(first.spa_fallback_entry, "index.html");
    assert_eq!(first.base_url_environment, "WORKBENCH_V2_BASE_URL");
    assert_eq!(
        first.node_environment["NODE_OPTIONS"],
        "--loader=./scripts/json-module-loader.mjs"
    );
    assert!(first.node_runtime_required);
    assert!(first.browser_runtime_required);
    assert_eq!(first.loopback_listener_count, 0);
    assert_eq!(first.direct_processes_spawned, 0);
    assert!(first.successful_exit_codes.is_empty());
    assert_eq!(first.request_error_count, 0);
    assert!(first.deterministic_receipt);
    let encoded = canonical_workbench_v2_browser_smoke_receipt_json(&first)
        .expect("canonical Workbench v2 browser receipt");
    let value: Value = serde_json::from_str(&encoded).expect("Workbench v2 browser receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_workbench_v2_browser_smoke_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["workbench-v2-browser-smoke", "--root"])
        .arg(&root)
        .arg("--dry-run")
        .env_clear()
        .output()
        .expect("run Workbench v2 browser smoke dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("Workbench v2 browser receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "workbench_v2_browser_smoke");
    assert_eq!(value["execution_mode"], "dry_run");
    assert_eq!(value["loopback_listener_count"], 0);
    assert_eq!(value["direct_processes_spawned"], 0);
    assert!(value["delivery_receipt_hash"].is_null());
    assert!(value["playwright_cli_sha256"].is_null());
    verify_receipt_hash(&value);
}

#[cfg(unix)]
#[test]
fn workbench_v2_browser_smoke_stops_on_build_failure_before_runtime_or_socket() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_npm(
        &test.0,
        b"#!/bin/sh\nprintf '%s|%s\\n' \"$VITE_BASE_PATH\" \"$*\" >> \"$PWD/npm-invocations.log\"\nexit 19\n",
    );
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["workbench-v2-browser-smoke", "--root"])
        .arg(&test.0)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("run failing Workbench v2 browser smoke");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    assert_eq!(
        std::fs::read_to_string(test.0.join("npm-invocations.log"))
            .expect("read npm invocation log"),
        "/|run build\n"
    );
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("error JSON");
    assert_eq!(value["code"], "workbench_v2_browser_smoke_build_failed");
    assert!(value["detail"]
        .as_str()
        .is_some_and(|detail| detail.contains("exit code 19")));
}

#[cfg(unix)]
#[test]
fn workbench_v2_browser_smoke_checks_delivery_then_requires_pinned_runtime() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_delivery_fixture(&test.0);
    let bin = write_fake_npm(
        &test.0,
        b"#!/bin/sh\nprintf '%s|%s\\n' \"$VITE_BASE_PATH\" \"$*\" >> \"$PWD/npm-invocations.log\"\nexit 0\n",
    );
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["workbench-v2-browser-smoke", "--root"])
        .arg(&test.0)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("run Workbench v2 browser smoke without installed Playwright");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    assert_eq!(
        std::fs::read_to_string(test.0.join("npm-invocations.log"))
            .expect("read npm invocation log"),
        "/|run build\n"
    );
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("error JSON");
    assert_eq!(value["code"], "frontend_required_file_missing");
    assert!(value["detail"]
        .as_str()
        .is_some_and(|detail| detail.contains("node_modules/@playwright/test/cli.js")));
}

#[test]
fn viewer_performance_probe_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let mut options = ViewerPerformanceProbeOptions::new(root);
    options.dry_run = true;
    options.output = Some(PathBuf::from("planned-performance.json"));
    let first = run_viewer_performance_probe(&options).expect("Viewer performance dry-run");
    let second = run_viewer_performance_probe(&options).expect("repeat Viewer performance dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert_eq!(first.tracked_sources.len(), 4);
    assert!(first
        .tracked_sources
        .iter()
        .all(|source| source.sha256.starts_with("sha256:") && source.bytes > 0));
    assert_eq!(first.sample_ms, 1_500);
    assert_eq!(first.max_ready_ms, 60_000);
    assert_eq!(first.minimum_average_fps.to_bits(), 5.0_f64.to_bits());
    assert_eq!(first.viewport_width, 1_440);
    assert_eq!(first.viewport_height, 1_000);
    assert_eq!(
        first.requested_output.as_deref(),
        Some("planned-performance.json")
    );
    assert_eq!(first.output_disposition, "not_created");
    assert_eq!(first.probe_artifact_sha256, None);
    assert_eq!(first.viewer_ready_ms, None);
    assert_eq!(first.direct_processes_spawned, 0);
    assert_eq!(first.successful_exit_code, None);
    assert!(first.runtime_requirements.node_required);
    assert!(first.runtime_requirements.browser_required);
    assert!(first.runtime_requirements.retained_node_internal_listener);
    assert!(first.deterministic_receipt);
    let encoded = canonical_viewer_performance_probe_receipt_json(&first)
        .expect("canonical Viewer performance receipt");
    let value: Value = serde_json::from_str(&encoded).expect("Viewer performance receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_viewer_performance_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-performance-probe", "--root"])
        .arg(&root)
        .args([
            "--query",
            "project=p&drawing=d",
            "--sample-ms",
            "250",
            "--max-ready-ms",
            "5000",
            "--min-fps",
            "7.5",
            "--width",
            "800",
            "--height",
            "600",
            "--out",
            "planned.json",
            "--dry-run",
        ])
        .env_clear()
        .output()
        .expect("run Viewer performance dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer performance CLI receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer performance receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["action"], "viewer_performance_probe");
    assert_eq!(receipt["query"], "project=p&drawing=d");
    assert_eq!(receipt["sample_ms"], 250);
    assert_eq!(receipt["max_ready_ms"], 5_000);
    assert_eq!(receipt["minimum_average_fps"], 7.5);
    assert_eq!(receipt["viewport_width"], 800);
    assert_eq!(receipt["viewport_height"], 600);
    assert_eq!(receipt["direct_processes_spawned"], 0);
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_performance_probe_owns_child_and_strict_retained_artifact() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let output_path = test.0.join("verified-performance.json");
    write_performance_probe_fixture(&test.0, &output_path);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf '%s\n' \"$*\" >> \"$PWD/node-invocations.log\"\nprintf 'probe chatter\n'\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/performance-probe-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-performance-probe", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute Viewer performance probe");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer performance live receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer performance receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["execution_mode"], "execute");
    assert_eq!(receipt["status"], "passed");
    assert_eq!(receipt["output_disposition"], "operator_path_retained");
    assert_eq!(
        receipt["published_output_path"].as_str(),
        output_path.to_str()
    );
    assert_eq!(receipt["viewer_ready_ms"], 125);
    assert_eq!(receipt["average_fps"], 60);
    assert_eq!(receipt["significant_pixel_count"], 2_400);
    assert_eq!(receipt["browser_error_count"], 0);
    assert_eq!(receipt["direct_processes_spawned"], 1);
    assert_eq!(receipt["successful_exit_code"], 0);
    assert!(receipt["probe_artifact_sha256"].is_string());
    assert!(output_path.is_file());
    assert!(std::fs::read_to_string(test.0.join("node-invocations.log"))
        .expect("read Viewer performance invocation")
        .contains("scripts/measure-structure-viewer-performance.mjs --verify --fail-blocked"));
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_performance_probe_removes_partial_explicit_output_on_failure() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf 'partial' > \"$out\"\nexit 29\n",
    );
    let output_path = test.0.join("failed-performance.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-performance-probe", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute failing Viewer performance probe");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer performance error JSON");
    assert_eq!(error["code"], "viewer_performance_probe_failed");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_performance_probe_rejects_duplicate_json_and_removes_output() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf '%s\n' '{\"schema_version\":\"first\",\"schema_version\":\"forged\"}' > \"$out\"\nexit 0\n",
    );
    let output_path = test.0.join("duplicate-performance.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-performance-probe", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute duplicate-key Viewer performance probe");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer performance duplicate-key error JSON");
    assert_eq!(error["code"], "viewer_performance_probe_artifact_invalid");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_performance_probe_rejects_source_mutation_and_removes_output() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let output_path = test.0.join("mutated-performance.json");
    write_performance_probe_fixture(&test.0, &output_path);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf ' ' >> scripts/structure-viewer-canvas-frame.mjs\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/performance-probe-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-performance-probe", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute mutating Viewer performance probe");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer performance mutation error JSON");
    assert_eq!(error["code"], "viewer_performance_probe_contract_changed");
    assert!(!output_path.exists());
}

#[test]
fn viewer_sample_workflow_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let mut options = ViewerSampleWorkflowOptions::new(root);
    options.dry_run = true;
    options.output = Some(PathBuf::from("planned-sample-workflow.json"));
    let first = run_viewer_sample_workflow(&options).expect("Viewer sample-workflow dry-run");
    let second =
        run_viewer_sample_workflow(&options).expect("repeat Viewer sample-workflow dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert_eq!(first.tracked_sources.len(), 3);
    assert!(first
        .tracked_sources
        .iter()
        .all(|source| source.sha256.starts_with("sha256:") && source.bytes > 0));
    assert_eq!(
        first.max_sample_completion_minutes.to_bits(),
        30.0_f64.to_bits()
    );
    assert_eq!(
        first.requested_output.as_deref(),
        Some("planned-sample-workflow.json")
    );
    assert_eq!(first.output_disposition, "not_created");
    assert_eq!(first.artifact_sha256, None);
    assert_eq!(first.verified_step_count, 0);
    assert_eq!(first.direct_processes_spawned, 0);
    assert_eq!(first.successful_exit_code, None);
    assert!(first.runtime_requirements.node_required);
    assert!(first.runtime_requirements.browser_required);
    assert!(first.runtime_requirements.retained_node_internal_listener);
    assert!(first.deterministic_receipt);
    let encoded = canonical_viewer_sample_workflow_receipt_json(&first)
        .expect("canonical Viewer sample-workflow receipt");
    let value: Value = serde_json::from_str(&encoded).expect("Viewer sample-workflow receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_viewer_sample_workflow_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&root)
        .args([
            "--max-minutes",
            "12.5",
            "--out",
            "planned-workflow.json",
            "--dry-run",
        ])
        .env_clear()
        .output()
        .expect("run Viewer sample-workflow dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer sample-workflow CLI receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer sample-workflow receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["action"], "viewer_sample_workflow");
    assert_eq!(receipt["max_sample_completion_minutes"], 12.5);
    assert_eq!(receipt["requested_output"], "planned-workflow.json");
    assert_eq!(receipt["direct_processes_spawned"], 0);
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_sample_workflow_owns_child_and_strict_retained_artifact() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_sample_workflow_fixture(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf '%s\n' \"$*\" >> \"$PWD/node-invocations.log\"\nprintf 'probe chatter\n'\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/sample-workflow-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = test.0.join("verified-sample-workflow.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute Viewer sample workflow");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer sample-workflow live receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer sample-workflow receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["execution_mode"], "execute");
    assert_eq!(receipt["status"], "passed");
    assert_eq!(receipt["output_disposition"], "operator_path_retained");
    assert_eq!(receipt["verified_step_count"], 4);
    assert_eq!(receipt["significant_pixel_count"], 7134);
    assert_eq!(receipt["browser_error_count"], 0);
    assert_eq!(receipt["browser_warning_count"], 3);
    assert_eq!(receipt["direct_processes_spawned"], 1);
    assert_eq!(receipt["successful_exit_code"], 0);
    assert!(receipt["artifact_sha256"].is_string());
    assert!(receipt["step_rows_sha256"].is_string());
    assert!(output_path.is_file());
    assert!(std::fs::read_to_string(test.0.join("node-invocations.log"))
        .expect("read Viewer sample-workflow invocation")
        .contains("scripts/verify-structure-viewer-sample-workflow.mjs --fail-blocked --out"));
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_sample_workflow_removes_partial_explicit_output_on_failure() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf 'partial' > \"$out\"\nexit 37\n",
    );
    let output_path = test.0.join("failed-sample-workflow.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute failing Viewer sample workflow");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer sample-workflow error JSON");
    assert_eq!(error["code"], "viewer_sample_workflow_failed");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_sample_workflow_rejects_forged_aggregate_and_duplicate_json() {
    let forged = TestRoot::create();
    copy_contract_inventory(&forged.0);
    write_sample_workflow_fixture(&forged.0);
    let fixture_path = forged.0.join("sample-workflow-fixture.json");
    let mut fixture: Value = serde_json::from_slice(
        &std::fs::read(&fixture_path).expect("read sample-workflow fixture"),
    )
    .expect("sample-workflow fixture JSON");
    fixture["browser_warning_count"] = serde_json::json!(99);
    std::fs::write(
        &fixture_path,
        format!(
            "{}\n",
            serde_json::to_string(&fixture).expect("encode forged workflow fixture")
        ),
    )
    .expect("write forged workflow fixture");
    let bin = write_fake_executable(
        &forged.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/sample-workflow-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = forged.0.join("forged-sample-workflow.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&forged.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute forged Viewer sample workflow");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer sample-workflow aggregate error JSON");
    assert_eq!(error["code"], "viewer_sample_workflow_aggregate_mismatch");
    assert!(!output_path.exists());

    let duplicate = TestRoot::create();
    copy_contract_inventory(&duplicate.0);
    let bin = write_fake_executable(
        &duplicate.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf '%s\n' '{\"schema_version\":\"first\",\"schema_version\":\"forged\"}' > \"$out\"\nexit 0\n",
    );
    let output_path = duplicate.0.join("duplicate-sample-workflow.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&duplicate.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute duplicate-key Viewer sample workflow");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer sample-workflow duplicate-key error JSON");
    assert_eq!(error["code"], "viewer_sample_workflow_artifact_invalid");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_sample_workflow_rejects_source_mutation_and_removes_output() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_sample_workflow_fixture(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf ' ' >> scripts/structure-viewer-canvas-frame.mjs\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/sample-workflow-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = test.0.join("mutated-sample-workflow.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-sample-workflow", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute mutating Viewer sample workflow");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer sample-workflow mutation error JSON");
    assert_eq!(error["code"], "viewer_sample_workflow_contract_changed");
    assert!(!output_path.exists());
}

#[test]
fn viewer_visual_regression_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let mut options = ViewerVisualRegressionOptions::new(root);
    options.dry_run = true;
    options.output = Some(PathBuf::from("planned-visual-regression.json"));
    options.case_ids = vec![
        "desktop_midas33_loadcomb_draft".to_owned(),
        "desktop_midas33_optimized".to_owned(),
    ];
    let first = run_viewer_visual_regression(&options).expect("Viewer visual-regression dry-run");
    let second =
        run_viewer_visual_regression(&options).expect("repeat Viewer visual-regression dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert_eq!(first.baseline_bytes, 105_131);
    assert_eq!(
        first.baseline_sha256,
        "sha256:85d5150e46dc859042a824e9b98948a0e3476a781a3315b4903e8d9df7dd75be"
    );
    assert_eq!(first.tracked_sources.len(), 4);
    assert_eq!(
        first.selected_case_ids,
        vec![
            "desktop_midas33_optimized",
            "desktop_midas33_loadcomb_draft"
        ]
    );
    assert_eq!(first.output_disposition, "not_created");
    assert_eq!(first.report_artifact_sha256, None);
    assert_eq!(first.verified_case_count, 0);
    assert_eq!(first.direct_processes_spawned, 0);
    assert_eq!(first.successful_exit_code, None);
    assert!(first.runtime_requirements.node_required);
    assert!(first.runtime_requirements.browser_required);
    assert!(first.runtime_requirements.retained_node_internal_listener);
    assert!(first.deterministic_receipt);
    let encoded = canonical_viewer_visual_regression_receipt_json(&first)
        .expect("canonical Viewer visual-regression receipt");
    let value: Value =
        serde_json::from_str(&encoded).expect("Viewer visual-regression receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn viewer_visual_regression_baseline_is_strict_tamper_evident_and_repo_confined() {
    let tampered = TestRoot::create();
    copy_contract_inventory(&tampered.0);
    let baseline_path = tampered
        .0
        .join("implementation/phase1/structure_viewer_visual_regression_baseline.json");
    let mut baseline: Value = serde_json::from_slice(
        &std::fs::read(&baseline_path).expect("read visual-regression baseline"),
    )
    .expect("visual-regression baseline JSON");
    baseline["case_rows"][0]["canvas_signature"]["sha256"] = Value::String("0".repeat(64));
    std::fs::write(
        &baseline_path,
        serde_json::to_vec(&baseline).expect("encode tampered visual baseline"),
    )
    .expect("write tampered visual baseline");
    let mut options = ViewerVisualRegressionOptions::new(tampered.0.clone());
    options.dry_run = true;
    let error = run_viewer_visual_regression(&options).expect_err("tampered baseline must fail");
    assert_eq!(error.code, "viewer_visual_regression_baseline_invalid");

    let duplicate = TestRoot::create();
    copy_contract_inventory(&duplicate.0);
    let baseline_path = duplicate
        .0
        .join("implementation/phase1/structure_viewer_visual_regression_baseline.json");
    let bytes = std::fs::read(&baseline_path).expect("read visual baseline for duplicate key");
    let mut forged = b"{\"schema_version\":\"duplicate\",".to_vec();
    forged.extend_from_slice(bytes.strip_prefix(b"{").expect("visual baseline object"));
    std::fs::write(&baseline_path, forged).expect("write duplicate-key visual baseline");
    let mut options = ViewerVisualRegressionOptions::new(duplicate.0.clone());
    options.dry_run = true;
    let error = run_viewer_visual_regression(&options).expect_err("duplicate key must fail");
    assert_eq!(error.code, "viewer_visual_regression_artifact_invalid");

    let mut unsafe_path = ViewerVisualRegressionOptions::new(repository_root());
    unsafe_path.dry_run = true;
    unsafe_path.baseline = PathBuf::from("../visual-baseline.json");
    let error = run_viewer_visual_regression(&unsafe_path).expect_err("path escape must fail");
    assert_eq!(error.code, "viewer_visual_regression_baseline_invalid");
}

#[test]
fn clean_environment_viewer_visual_regression_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&root)
        .args([
            "--case-id",
            "desktop_midas33_contour,desktop_midas33_optimized",
            "--timeout-ms",
            "45000",
            "--max-mean-abs-diff",
            "24",
            "--max-max-abs-diff",
            "120",
            "--max-coverage-delta",
            "0.1",
            "--max-center-delta",
            "0.08",
            "--dry-run",
        ])
        .env_clear()
        .output()
        .expect("run Viewer visual-regression dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer visual-regression CLI receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer visual-regression receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["action"], "viewer_visual_regression");
    assert_eq!(
        receipt["selected_case_ids"],
        serde_json::json!(["desktop_midas33_optimized", "desktop_midas33_contour"])
    );
    assert_eq!(receipt["timeout_ms"], 45_000);
    assert_eq!(receipt["tolerances"]["max_mean_abs_diff"], 24);
    assert_eq!(receipt["direct_processes_spawned"], 0);
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_visual_regression_owns_child_and_strict_retained_report() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_visual_regression_fixture(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf '%s\n' \"$*\" >> \"$PWD/node-invocations.log\"\nprintf 'probe chatter\n'\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/visual-regression-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = test.0.join("verified-visual-regression.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute Viewer visual regression");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value =
        serde_json::from_slice(bytes).expect("Viewer visual-regression live receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&receipt)
            .expect("canonical Viewer visual-regression receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(receipt["execution_mode"], "execute");
    assert_eq!(receipt["status"], "passed");
    assert_eq!(receipt["output_disposition"], "operator_path_retained");
    assert_eq!(receipt["verified_case_count"], 11);
    assert_eq!(receipt["verified_compare_count"], 11);
    assert_eq!(receipt["direct_processes_spawned"], 1);
    assert_eq!(receipt["successful_exit_code"], 0);
    assert!(receipt["report_artifact_sha256"].is_string());
    assert!(receipt["case_rows_sha256"].is_string());
    assert!(receipt["compare_rows_sha256"].is_string());
    assert!(output_path.is_file());
    assert!(std::fs::read_to_string(test.0.join("node-invocations.log"))
        .expect("read Viewer visual-regression invocation")
        .contains(
            "scripts/measure-structure-viewer-visual-regression.mjs --verify --fail-blocked"
        ));
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_visual_regression_removes_partial_explicit_output_on_failure() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf 'partial' > \"$out\"\nexit 31\n",
    );
    let output_path = test.0.join("failed-visual-regression.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute failing Viewer visual regression");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer visual-regression error JSON");
    assert_eq!(error["code"], "viewer_visual_regression_failed");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_visual_regression_rejects_forged_delta_and_duplicate_json() {
    let forged = TestRoot::create();
    copy_contract_inventory(&forged.0);
    write_visual_regression_fixture(&forged.0);
    let fixture_path = forged.0.join("visual-regression-fixture.json");
    let mut fixture: Value = serde_json::from_slice(
        &std::fs::read(&fixture_path).expect("read visual-regression fixture"),
    )
    .expect("visual-regression fixture JSON");
    fixture["compare_rows"][0]["signature_delta"]["mean_abs_diff"] = serde_json::json!(1);
    std::fs::write(
        &fixture_path,
        format!(
            "{}\n",
            serde_json::to_string(&fixture).expect("encode forged fixture")
        ),
    )
    .expect("write forged fixture");
    let bin = write_fake_executable(
        &forged.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/visual-regression-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = forged.0.join("forged-visual-regression.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&forged.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute forged Viewer visual regression");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer visual-regression forged error JSON");
    assert_eq!(error["code"], "viewer_visual_regression_artifact_invalid");
    assert!(!output_path.exists());

    let duplicate = TestRoot::create();
    copy_contract_inventory(&duplicate.0);
    let bin = write_fake_executable(
        &duplicate.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf '%s\n' '{\"schema_version\":\"first\",\"schema_version\":\"forged\"}' > \"$out\"\nexit 0\n",
    );
    let output_path = duplicate.0.join("duplicate-visual-regression.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&duplicate.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute duplicate-key Viewer visual regression");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer visual-regression duplicate-key error JSON");
    assert_eq!(error["code"], "viewer_visual_regression_artifact_invalid");
    assert!(!output_path.exists());
}

#[cfg(unix)]
#[test]
fn viewer_visual_regression_rejects_source_mutation_and_removes_output() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    write_visual_regression_fixture(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nprintf ' ' >> scripts/structure-viewer-canvas-frame.mjs\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nwhile IFS= read -r line; do printf '%s\n' \"$line\"; done < \"$PWD/visual-regression-fixture.json\" > \"$out\"\nexit 0\n",
    );
    let output_path = test.0.join("mutated-visual-regression.json");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-visual-regression", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute mutating Viewer visual regression");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer visual-regression mutation error JSON");
    assert_eq!(error["code"], "viewer_visual_regression_contract_changed");
    assert!(!output_path.exists());
}

#[test]
fn viewer_report_pdf_export_dry_run_is_process_free_canonical_and_self_hashed() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let mut options = ViewerReportPdfExportOptions::new(test.0.clone());
    options.output = PathBuf::from("planned.pdf");
    options.html_output = Some(PathBuf::from("planned.html"));
    options.dry_run = true;
    let first = run_viewer_report_pdf_export(&options).expect("Viewer report PDF export dry-run");
    let second =
        run_viewer_report_pdf_export(&options).expect("repeat Viewer report PDF export dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert_eq!(first.requested_pdf_output, "planned.pdf");
    assert_eq!(first.requested_html_output.as_deref(), Some("planned.html"));
    assert_eq!(first.published_pdf_path, None);
    assert_eq!(first.published_html_path, None);
    assert_eq!(first.pdf_previous_state, "absent");
    assert_eq!(first.html_previous_state.as_deref(), Some("absent"));
    assert_eq!(first.output_disposition, "not_created");
    assert_eq!(first.direct_processes_spawned, 0);
    assert!(first.successful_exit_codes.is_empty());
    assert!(first.deterministic_receipt);
    assert!(!test.0.join("planned.pdf").exists());
    assert!(!test.0.join("planned.html").exists());
    let encoded = canonical_viewer_report_pdf_export_receipt_json(&first)
        .expect("canonical Viewer report PDF export receipt");
    let value: Value = serde_json::from_str(&encoded).expect("Viewer report PDF export JSON");
    verify_receipt_hash(&value);
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_export_replaces_existing_files_only_after_verification() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        "#!/bin/sh\nout=''\nhtml=''\nwhile [ \"$#\" -gt 0 ]; do\n  case \"$1\" in\n    --out) shift; out=$1 ;;\n    --html-out) shift; html=$1 ;;\n  esac\n  shift\ndone\nprintf '%%PDF-fake-published-report\\n' > \"$out\"\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'viewer screenshot marker' 'Engineer-in-loop Checklist' '상용 검토 가능' > \"$html\"\nexit 0\n".as_bytes(),
    );
    let pdf = test.0.join("published.pdf");
    let html = test.0.join("published.html");
    std::fs::write(&pdf, b"old-pdf").expect("write old PDF");
    std::fs::write(&html, b"old-html").expect("write old HTML");
    let old_pdf_sha = sha256_identity(b"old-pdf");
    let old_html_sha = sha256_identity(b"old-html");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-export", "--root"])
        .arg(&test.0)
        .args(["--min-bytes", "5", "--out"])
        .arg(&pdf)
        .arg("--html-out")
        .arg(&html)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute Viewer report PDF export");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let receipt: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF export receipt");
    assert_eq!(
        receipt["schema_version"],
        "structural-native-viewer-report-pdf-export-receipt.v1"
    );
    assert_eq!(receipt["status"], "published");
    assert_eq!(receipt["pdf_previous_state"], "regular_file");
    assert_eq!(receipt["pdf_previous_sha256"], old_pdf_sha);
    assert_eq!(receipt["html_previous_state"], "regular_file");
    assert_eq!(receipt["html_previous_sha256"], old_html_sha);
    assert_eq!(
        receipt["output_disposition"],
        "verified_pdf_and_html_published"
    );
    assert_eq!(receipt["direct_processes_spawned"], 1);
    assert_eq!(receipt["successful_exit_codes"], serde_json::json!([0]));
    assert!(std::fs::read(&pdf)
        .expect("read published PDF")
        .starts_with(b"%PDF-"));
    assert!(std::fs::read_to_string(&html)
        .expect("read published HTML")
        .contains("Engineer-in-loop Checklist"));
    assert!(std::fs::read_dir(&test.0)
        .expect("read test root")
        .all(|entry| !entry
            .expect("directory entry")
            .file_name()
            .to_string_lossy()
            .starts_with(".structural-viewer-report-pdf-")));
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_export_preserves_existing_outputs_when_verification_fails() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        "#!/bin/sh\nout=''\nhtml=''\nwhile [ \"$#\" -gt 0 ]; do\n  case \"$1\" in\n    --out) shift; out=$1 ;;\n    --html-out) shift; html=$1 ;;\n  esac\n  shift\ndone\nprintf 'not-a-pdf' > \"$out\"\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'viewer screenshot marker' 'Engineer-in-loop Checklist' '상용 검토 가능' > \"$html\"\nexit 0\n".as_bytes(),
    );
    let pdf = test.0.join("preserved.pdf");
    let html = test.0.join("preserved.html");
    std::fs::write(&pdf, b"old-pdf").expect("write old PDF");
    std::fs::write(&html, b"old-html").expect("write old HTML");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-export", "--root"])
        .arg(&test.0)
        .args(["--min-bytes", "5", "--out"])
        .arg(&pdf)
        .arg("--html-out")
        .arg(&html)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute invalid Viewer report PDF export");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF export error");
    assert_eq!(error["code"], "viewer_report_pdf_smoke_pdf_invalid");
    assert_eq!(std::fs::read(&pdf).expect("read preserved PDF"), b"old-pdf");
    assert_eq!(
        std::fs::read(&html).expect("read preserved HTML"),
        b"old-html"
    );
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_export_rejects_destination_mutation_during_generation() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        "#!/bin/sh\nout=''\nhtml=''\nwhile [ \"$#\" -gt 0 ]; do\n  case \"$1\" in\n    --out) shift; out=$1 ;;\n    --html-out) shift; html=$1 ;;\n  esac\n  shift\ndone\nprintf '%%PDF-fake-raced-report\\n' > \"$out\"\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'viewer screenshot marker' 'Engineer-in-loop Checklist' '상용 검토 가능' > \"$html\"\nprintf 'concurrent-writer' > \"$PWD/raced.pdf\"\nexit 0\n".as_bytes(),
    );
    let pdf = test.0.join("raced.pdf");
    std::fs::write(&pdf, b"old-pdf").expect("write old PDF");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-export", "--root"])
        .arg(&test.0)
        .args(["--min-bytes", "5", "--out"])
        .arg(&pdf)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute raced Viewer report PDF export");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF race error");
    assert_eq!(error["code"], "viewer_report_pdf_export_output_changed");
    assert_eq!(
        std::fs::read(&pdf).expect("read concurrently changed output"),
        b"concurrent-writer"
    );
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_export_rejects_symlink_destination_before_process_launch() {
    use std::os::unix::fs::symlink;

    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let target = test.0.join("real.pdf");
    let link = test.0.join("linked.pdf");
    std::fs::write(&target, b"preserve").expect("write symlink target");
    symlink(&target, &link).expect("create output symlink");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-export", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&link)
        .env_clear()
        .output()
        .expect("reject Viewer report PDF output symlink");
    assert_eq!(output.status.code(), Some(1));
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF symlink error");
    assert_eq!(error["code"], "viewer_report_pdf_export_output_invalid");
    assert_eq!(std::fs::read(&target).expect("read target"), b"preserve");
}

#[test]
fn viewer_report_pdf_smoke_dry_run_is_deterministic_process_free_and_self_hashed() {
    let root = repository_root();
    let mut options = ViewerReportPdfSmokeOptions::new(root);
    options.dry_run = true;
    options.output = Some(PathBuf::from("report.pdf"));
    let first = run_viewer_report_pdf_smoke(&options).expect("Viewer report PDF smoke dry-run");
    let second =
        run_viewer_report_pdf_smoke(&options).expect("repeat Viewer report PDF smoke dry-run");
    assert_eq!(first, second);
    assert_eq!(first.execution_mode, "dry_run");
    assert_eq!(first.status, "planned");
    assert!(first.frontend_contract_receipt_hash.starts_with("sha256:"));
    assert!(first.exporter_sha256.starts_with("sha256:"));
    assert_eq!(
        first.query,
        "project=midas33_release&drawing=midas33_optimized&variant=optimized"
    );
    assert_eq!(first.minimum_pdf_bytes, 12_000);
    assert_eq!(first.requested_output.as_deref(), Some("report.pdf"));
    assert_eq!(first.published_output_path, None);
    assert_eq!(first.output_disposition, "not_created");
    assert_eq!(
        first.logical_command_template,
        vec![
            "node".to_owned(),
            "scripts/export-structure-viewer-report-pdf.mjs".to_owned(),
            "--query".to_owned(),
            "project=midas33_release&drawing=midas33_optimized&variant=optimized".to_owned(),
            "--out".to_owned(),
            "{pdf_output}".to_owned(),
            "--html-out".to_owned(),
            "{html_output}".to_owned(),
        ]
    );
    assert_eq!(first.pdf_byte_length, None);
    assert_eq!(first.pdf_sha256, None);
    assert_eq!(first.html_byte_length, None);
    assert_eq!(first.html_sha256, None);
    assert_eq!(first.pdf_text_status, "not_executed");
    assert_eq!(first.pdf_text_sha256, None);
    assert!(first.node_runtime_required);
    assert!(first.browser_runtime_required);
    assert_eq!(first.rust_owned_listener_count, 0);
    assert_eq!(first.direct_processes_spawned, 0);
    assert!(first.successful_exit_codes.is_empty());
    assert!(first.deterministic_receipt);
    let encoded = canonical_viewer_report_pdf_smoke_receipt_json(&first)
        .expect("canonical Viewer report PDF smoke receipt");
    let value: Value =
        serde_json::from_str(&encoded).expect("Viewer report PDF smoke receipt JSON");
    verify_receipt_hash(&value);
}

#[test]
fn clean_environment_viewer_report_pdf_smoke_dry_run_emits_one_canonical_receipt() {
    let root = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-smoke", "--root"])
        .arg(&root)
        .args([
            "--query",
            "project=p&drawing=d&variant=v",
            "--min-bytes",
            "17",
            "--out",
            "planned.pdf",
            "--dry-run",
        ])
        .env_clear()
        .output()
        .expect("run Viewer report PDF smoke dry-run");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let value: Value = serde_json::from_slice(bytes).expect("Viewer report PDF smoke receipt JSON");
    assert_eq!(
        canonicalize_model_ir_v2(&value)
            .expect("canonical receipt")
            .as_bytes(),
        bytes
    );
    assert_eq!(value["action"], "viewer_report_pdf_smoke");
    assert_eq!(value["execution_mode"], "dry_run");
    assert_eq!(value["query"], "project=p&drawing=d&variant=v");
    assert_eq!(value["minimum_pdf_bytes"], 17);
    assert_eq!(value["requested_output"], "planned.pdf");
    assert_eq!(value["direct_processes_spawned"], 0);
    verify_receipt_hash(&value);
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_smoke_owns_processes_and_verifies_retained_artifacts() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$PWD/node-invocations.log\"\nprintf 'exporter chatter\\n'\nout=''\nhtml=''\nwhile [ \"$#\" -gt 0 ]; do\n  case \"$1\" in\n    --out) shift; out=$1 ;;\n    --html-out) shift; html=$1 ;;\n  esac\n  shift\ndone\nprintf '%%PDF-fake-report\\n' > \"$out\"\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'viewer screenshot marker' 'Engineer-in-loop Checklist' '상용 검토 가능' > \"$html\"\nexit 0\n".as_bytes(),
    );
    write_fake_executable(
        &test.0,
        "pdftotext",
        b"#!/bin/sh\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'Engineer-in-loop Checklist'\nexit 0\n",
    );
    let output_path = test.0.join("verified-report.pdf");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-smoke", "--root"])
        .arg(&test.0)
        .args(["--min-bytes", "5", "--out"])
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute Viewer report PDF smoke");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let bytes = output.stdout.strip_suffix(b"\n").expect("one JSON line");
    let receipt: Value = serde_json::from_slice(bytes).expect("Viewer report PDF receipt JSON");
    assert_eq!(receipt["execution_mode"], "execute");
    assert_eq!(receipt["status"], "passed");
    assert_eq!(receipt["output_disposition"], "operator_path_retained");
    assert_eq!(
        receipt["published_output_path"].as_str(),
        output_path.to_str(),
    );
    assert!(receipt["pdf_byte_length"]
        .as_u64()
        .is_some_and(|length| length >= 5));
    assert!(receipt["pdf_sha256"].is_string());
    assert!(receipt["html_sha256"].is_string());
    assert_eq!(receipt["pdf_text_status"], "verified");
    assert!(receipt["pdf_text_sha256"].is_string());
    assert_eq!(receipt["direct_processes_spawned"], 2);
    assert_eq!(receipt["successful_exit_codes"], serde_json::json!([0, 0]));
    assert!(output_path.is_file());
    assert!(PathBuf::from(format!("{}.html", output_path.display())).is_file());
    assert!(std::fs::read_to_string(test.0.join("node-invocations.log"))
        .expect("read Node invocation")
        .contains("scripts/export-structure-viewer-report-pdf.mjs"));
    verify_receipt_hash(&receipt);
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_smoke_removes_partial_explicit_outputs_on_failure() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        b"#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n  if [ \"$1\" = '--out' ]; then shift; out=$1; fi\n  shift\ndone\nprintf 'partial' > \"$out\"\nexit 23\n",
    );
    let output_path = test.0.join("failed-report.pdf");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-smoke", "--root"])
        .arg(&test.0)
        .arg("--out")
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute failing Viewer report PDF smoke");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF error JSON");
    assert_eq!(error["code"], "viewer_report_pdf_smoke_export_failed");
    assert!(!output_path.exists());
    assert!(!PathBuf::from(format!("{}.html", output_path.display())).exists());
}

#[cfg(unix)]
#[test]
fn viewer_report_pdf_smoke_rejects_exporter_mutation_and_removes_outputs() {
    let test = TestRoot::create();
    copy_contract_inventory(&test.0);
    let bin = write_fake_executable(
        &test.0,
        "node",
        "#!/bin/sh\nprintf ' ' >> scripts/export-structure-viewer-report-pdf.mjs\nout=''\nhtml=''\nwhile [ \"$#\" -gt 0 ]; do\n  case \"$1\" in\n    --out) shift; out=$1 ;;\n    --html-out) shift; html=$1 ;;\n  esac\n  shift\ndone\nprintf '%%PDF-fake-report\\n' > \"$out\"\nprintf '%s\\n' 'Drawing Review' 'Before / After Member Comparison' 'viewer screenshot marker' 'Engineer-in-loop Checklist' '상용 검토 가능' > \"$html\"\nexit 0\n".as_bytes(),
    );
    let output_path = test.0.join("mutated-report.pdf");
    let output = Command::new(env!("CARGO_BIN_EXE_structural-frontend-contract"))
        .args(["viewer-report-pdf-smoke", "--root"])
        .arg(&test.0)
        .args(["--min-bytes", "5", "--out"])
        .arg(&output_path)
        .env_clear()
        .env("PATH", &bin)
        .output()
        .expect("execute mutating Viewer report PDF smoke");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stderr.is_empty());
    let error: Value =
        serde_json::from_slice(output.stdout.strip_suffix(b"\n").expect("one JSON line"))
            .expect("Viewer report PDF mutation error JSON");
    assert_eq!(error["code"], "viewer_report_pdf_smoke_contract_changed");
    assert!(!output_path.exists());
    assert!(!PathBuf::from(format!("{}.html", output_path.display())).exists());
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
