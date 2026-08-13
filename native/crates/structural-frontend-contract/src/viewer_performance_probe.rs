use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-performance-probe-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-performance-probe-receipt.v1";
const PROBE_SCHEMA_V1: &str = "structure-viewer-browser-performance-probe.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PROBE_MODE: &str = "local_browser_probe";
const EXPECTED_REASON_CODE: &str = "PASS";
const EXPECTED_CLAIM_BOUNDARY: &str =
    "Local browser performance smoke only; not a normalized customer hardware FPS claim.";
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_probe_loopback_and_browser_page_requests";
const EXPECTED_DEFAULT_QUERY: &str =
    "project=midas33_release&drawing=midas33_optimized&variant=optimized";
const EXPECTED_DEFAULT_SAMPLE_MS: u64 = 1_500;
const EXPECTED_DEFAULT_MAX_READY_MS: u64 = 60_000;
const EXPECTED_DEFAULT_MIN_FPS: f64 = 5.0;
const EXPECTED_DEFAULT_WIDTH: u32 = 1_440;
const EXPECTED_DEFAULT_HEIGHT: u32 = 1_000;
const MAX_TRACKED_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_PROBE_ARTIFACT_BYTES: u64 = 4 * 1024 * 1024;
const MAX_QUERY_BYTES: usize = 4_096;
const MAX_PATH_BYTES: usize = 4_096;
const MAX_SAMPLE_MS: u64 = 300_000;
const MAX_READY_MS: u64 = 600_000;
const MAX_VIEWPORT_DIMENSION: u32 = 16_384;
const MAX_MINIMUM_FPS: f64 = 1_000.0;
const EXPECTED_TRACKED_SOURCES: [(&str, &str); 4] = [
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
const EXPECTED_RESIDUAL_LIVE_WORK: [&str; 3] = [
    "Run the same probe across a defined browser/device/GPU matrix.",
    "Promote customer-hardware FPS and interaction latency budgets only after repeatable lab baselines exist.",
    "Attach screenshot visual regression baselines for the same query and view modes.",
];
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerPerformanceTrackedSourceV1 {
    label: String,
    path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerPerformanceProbeSourceV1 {
    schema_version: String,
    node_launcher: String,
    probe_path: String,
    output_schema_version: String,
    default_query: String,
    default_sample_ms: u64,
    default_max_ready_ms: u64,
    default_min_average_fps: f64,
    default_viewport_width: u32,
    default_viewport_height: u32,
    tracked_sources: Vec<ViewerPerformanceTrackedSourceV1>,
    expected_probe_mode: String,
    expected_probe_claim_boundary: String,
    residual_live_work: Vec<String>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Viewer browser performance probe plan or execution.
#[derive(Clone, Debug, PartialEq)]
pub struct ViewerPerformanceProbeOptions {
    pub root: PathBuf,
    pub query: String,
    pub sample_ms: u64,
    pub max_ready_ms: u64,
    pub minimum_average_fps: f64,
    pub viewport_width: u32,
    pub viewport_height: u32,
    pub output: Option<PathBuf>,
    pub dry_run: bool,
    pub keep_temporary_output: bool,
}

impl ViewerPerformanceProbeOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            query: EXPECTED_DEFAULT_QUERY.to_owned(),
            sample_ms: EXPECTED_DEFAULT_SAMPLE_MS,
            max_ready_ms: EXPECTED_DEFAULT_MAX_READY_MS,
            minimum_average_fps: EXPECTED_DEFAULT_MIN_FPS,
            viewport_width: EXPECTED_DEFAULT_WIDTH,
            viewport_height: EXPECTED_DEFAULT_HEIGHT,
            output: None,
            dry_run: false,
            keep_temporary_output: false,
        }
    }
}

struct TrackedInput {
    label: String,
    relative_path: String,
    absolute_path: PathBuf,
    bytes: Vec<u8>,
}

struct PreparedViewerPerformanceProbe {
    source: ViewerPerformanceProbeSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    tracked_inputs: Vec<TrackedInput>,
    query: String,
    sample_ms: u64,
    max_ready_ms: u64,
    minimum_average_fps: f64,
    viewport_width: u32,
    viewport_height: u32,
    requested_output: Option<String>,
    logical_command_template: Vec<String>,
}

struct ProbeOutput {
    artifact_path: PathBuf,
    published_output_path: Option<String>,
    output_disposition: &'static str,
    cleanup_explicit_output: bool,
    _workspace: TemporaryWorkspace,
}

impl Drop for ProbeOutput {
    fn drop(&mut self) {
        if self.cleanup_explicit_output {
            let _ignored = fs::remove_file(&self.artifact_path);
        }
    }
}

struct TemporaryWorkspace {
    path: PathBuf,
    retain: bool,
}

impl TemporaryWorkspace {
    fn create(retain: bool) -> Result<Self, FrontendContractError> {
        let parent = std::env::temp_dir();
        verify_real_directory(&parent, "Viewer performance probe temporary parent")?;
        for _ in 0..1_024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-performance-probe-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path, retain }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_performance_probe_temp_create_failed",
                        format!("create Viewer performance temporary directory failed: {error}"),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_performance_probe_temp_create_failed",
            "could not allocate a unique Viewer performance temporary directory",
        ))
    }
}

impl Drop for TemporaryWorkspace {
    fn drop(&mut self) {
        if !self.retain {
            let _ignored = fs::remove_dir_all(&self.path);
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ViewerPerformanceSourceIdentityV1 {
    pub label: String,
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerPerformanceRuntimeRequirementsV1 {
    pub node_required: bool,
    pub browser_required: bool,
    pub retained_node_internal_listener: bool,
}

/// Canonical receipt for one planned or completed Viewer browser performance probe.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ViewerPerformanceProbeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub tracked_sources: Vec<ViewerPerformanceSourceIdentityV1>,
    pub query: String,
    pub sample_ms: u64,
    pub max_ready_ms: u64,
    pub minimum_average_fps: f64,
    pub viewport_width: u32,
    pub viewport_height: u32,
    pub requested_output: Option<String>,
    pub published_output_path: Option<String>,
    pub output_disposition: String,
    pub logical_command_template: Vec<String>,
    pub probe_schema_version: String,
    pub probe_artifact_sha256: Option<String>,
    pub probe_generated_at: Option<String>,
    pub viewer_ready_ms: Option<u64>,
    pub average_fps: Option<f64>,
    pub p95_frame_ms: Option<f64>,
    pub maximum_frame_ms: Option<f64>,
    pub significant_pixel_count: Option<u64>,
    pub browser_error_count: u64,
    pub blockers: Vec<String>,
    pub runtime_requirements: ViewerPerformanceRuntimeRequirementsV1,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeArtifactV1 {
    schema_version: String,
    generated_at: String,
    contract_pass: BooleanValue,
    reason_code: String,
    summary_line: String,
    probe_mode: String,
    measured_browser_probe: BooleanValue,
    live_performance_claim: BooleanValue,
    independent_product_claim: BooleanValue,
    claim_boundary: String,
    query: String,
    output_path: String,
    budgets: ProbeBudgets,
    probe: MeasuredProbe,
    source_rows: Vec<ProbeSourceRow>,
    residual_live_work: Vec<String>,
    blockers: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BooleanValue {
    False,
    True,
}

impl<'de> Deserialize<'de> for BooleanValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        bool::deserialize(deserializer).map(|value| if value { Self::True } else { Self::False })
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeBudgets {
    max_ready_ms: u64,
    min_average_fps: f64,
    sample_ms: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeSourceRow {
    label: String,
    path: String,
    available: bool,
    bytes: u64,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct MeasuredProbe {
    url: String,
    ready_ms: u64,
    viewport: ProbeViewport,
    canvas_metrics: CanvasMetrics,
    raf_sample: RafSample,
    navigation_timing: NavigationTiming,
    viewer_state: ViewerState,
    browser_errors: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeViewport {
    width: u32,
    height: u32,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct CanvasMetrics {
    non_blank: bool,
    canvas_width: u64,
    canvas_height: u64,
    sample_width: u64,
    sample_height: u64,
    significant_pixel_count: u64,
    significant_pixel_ratio: f64,
    bbox: CanvasBoundingBox,
    coverage_width: f64,
    coverage_height: f64,
    bbox_aspect_ratio: f64,
    center_x: f64,
    center_y: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct CanvasBoundingBox {
    min_x: u64,
    min_y: u64,
    max_x: u64,
    max_y: u64,
    width: u64,
    height: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct RafSample {
    frame_count: u64,
    elapsed_ms: f64,
    average_fps: f64,
    average_frame_ms: f64,
    p95_frame_ms: f64,
    max_frame_ms: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct NavigationTiming {
    #[serde(rename = "domContentLoadedMs")]
    dom_content_loaded: Option<f64>,
    #[serde(rename = "loadEventEndMs")]
    load_event_end: Option<f64>,
    #[serde(rename = "responseEndMs")]
    response_end: Option<f64>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct ViewerState {
    title: String,
    stage_variant: String,
    project_status: String,
    stats_text: String,
}

struct VerifiedProbe {
    artifact_bytes: Vec<u8>,
    generated_at: String,
    ready_ms: u64,
    average_fps: f64,
    p95_frame_ms: f64,
    maximum_frame_ms: f64,
    significant_pixel_count: u64,
    browser_error_count: u64,
    blockers: Vec<String>,
    successful_exit_code: i32,
}

/// Plan or execute the retained Viewer browser performance measurement under Rust ownership.
///
/// Dry-run validates and hashes every tracked input without spawning a process. Live execution
/// owns one direct Node child and the artifact lifetime, then strictly decodes and independently
/// rechecks the local-browser budget result before emitting a canonical self-hashed receipt. The
/// retained Node probe continues to own its internal loopback server, Playwright, Chromium, Viewer
/// JavaScript rendering, canvas inspection, and RAF sampling.
///
/// # Errors
///
/// Rejects unsafe options or outputs, source drift, child-process failure, malformed or oversized
/// artifacts, inconsistent source identities, browser errors, and failed performance budgets.
pub fn run_viewer_performance_probe(
    options: &ViewerPerformanceProbeOptions,
) -> Result<ViewerPerformanceProbeReceiptV1, FrontendContractError> {
    let prepared = prepare_viewer_performance_probe(options)?;
    if options.dry_run {
        return build_receipt(prepared, None, None);
    }
    let mut output = prepare_probe_output(options, &prepared.root)?;
    let exit_code = run_probe_child(&prepared, &output)?;
    let verified = verify_probe_artifact(&prepared, &output, exit_code)?;
    verify_execution_inputs_unchanged(&prepared)?;
    let receipt = build_receipt(prepared, Some(&output), Some(&verified))?;
    output.cleanup_explicit_output = false;
    Ok(receipt)
}

fn prepare_viewer_performance_probe(
    options: &ViewerPerformanceProbeOptions,
) -> Result<PreparedViewerPerformanceProbe, FrontendContractError> {
    validate_options(options)?;
    verify_real_directory(&options.root, "Viewer performance probe root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_performance_probe_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_root_invalid",
            format!("canonicalize Viewer performance probe root failed: {error}"),
        )
    })?;
    let tracked_inputs = load_tracked_inputs(&root, &source)?;
    let requested_output = options
        .output
        .as_ref()
        .map(|path| portable_input_path(path, "Viewer performance probe output"))
        .transpose()?;
    let logical_command_template = vec![
        source.node_launcher.clone(),
        source.probe_path.clone(),
        "--verify".to_owned(),
        "--fail-blocked".to_owned(),
        "--query".to_owned(),
        options.query.clone(),
        "--out".to_owned(),
        "{probe_output}".to_owned(),
        "--sample-ms".to_owned(),
        options.sample_ms.to_string(),
        "--max-ready-ms".to_owned(),
        options.max_ready_ms.to_string(),
        "--min-fps".to_owned(),
        options.minimum_average_fps.to_string(),
        "--width".to_owned(),
        options.viewport_width.to_string(),
        "--height".to_owned(),
        options.viewport_height.to_string(),
    ];
    Ok(PreparedViewerPerformanceProbe {
        source,
        root,
        frontend_contract_receipt_hash,
        tracked_inputs,
        query: options.query.clone(),
        sample_ms: options.sample_ms,
        max_ready_ms: options.max_ready_ms,
        minimum_average_fps: options.minimum_average_fps,
        viewport_width: options.viewport_width,
        viewport_height: options.viewport_height,
        requested_output,
        logical_command_template,
    })
}

fn load_tracked_inputs(
    root: &Path,
    source: &ViewerPerformanceProbeSourceV1,
) -> Result<Vec<TrackedInput>, FrontendContractError> {
    source
        .tracked_sources
        .iter()
        .map(|row| {
            let absolute_path = resolve_required_file(root, &row.path)?;
            let bytes = read_bounded_regular_file(
                &absolute_path,
                MAX_TRACKED_SOURCE_BYTES,
                &format!("Viewer performance tracked source {}", row.label),
            )?;
            Ok(TrackedInput {
                label: row.label.clone(),
                relative_path: row.path.clone(),
                absolute_path,
                bytes,
            })
        })
        .collect()
}

/// Encode a Viewer performance probe receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_performance_probe_receipt_json(
    receipt: &ViewerPerformanceProbeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_performance_probe_receipt_encode_failed")
}

pub(crate) fn validate_viewer_performance_probe_source(
    source: &ViewerPerformanceProbeSourceV1,
) -> Result<(), FrontendContractError> {
    let tracked_sources = source
        .tracked_sources
        .iter()
        .map(|row| (row.label.as_str(), row.path.as_str()))
        .collect::<Vec<_>>();
    let residual_live_work = source
        .residual_live_work
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let unique_labels = source
        .tracked_sources
        .iter()
        .map(|row| row.label.as_str())
        .collect::<BTreeSet<_>>();
    let unique_paths = source
        .tracked_sources
        .iter()
        .map(|row| row.path.as_str())
        .collect::<BTreeSet<_>>();
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.probe_path == EXPECTED_TRACKED_SOURCES[1].1
        && source.output_schema_version == PROBE_SCHEMA_V1
        && source.default_query == EXPECTED_DEFAULT_QUERY
        && source.default_sample_ms == EXPECTED_DEFAULT_SAMPLE_MS
        && source.default_max_ready_ms == EXPECTED_DEFAULT_MAX_READY_MS
        && same_f64(source.default_min_average_fps, EXPECTED_DEFAULT_MIN_FPS)
        && source.default_viewport_width == EXPECTED_DEFAULT_WIDTH
        && source.default_viewport_height == EXPECTED_DEFAULT_HEIGHT
        && tracked_sources == EXPECTED_TRACKED_SOURCES
        && source.expected_probe_mode == EXPECTED_PROBE_MODE
        && source.expected_probe_claim_boundary == EXPECTED_CLAIM_BOUNDARY
        && residual_live_work == EXPECTED_RESIDUAL_LIVE_WORK
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary)
        && unique_labels.len() == source.tracked_sources.len()
        && unique_paths.len() == source.tracked_sources.len();
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer performance probe contract is invalid",
        ));
    }
    Ok(())
}

fn validate_options(options: &ViewerPerformanceProbeOptions) -> Result<(), FrontendContractError> {
    let valid = !options.query.is_empty()
        && options.query.len() <= MAX_QUERY_BYTES
        && !options.query.chars().any(char::is_control)
        && options.sample_ms > 0
        && options.sample_ms <= MAX_SAMPLE_MS
        && options.max_ready_ms > 0
        && options.max_ready_ms <= MAX_READY_MS
        && options.minimum_average_fps.is_finite()
        && options.minimum_average_fps > 0.0
        && options.minimum_average_fps <= MAX_MINIMUM_FPS
        && options.viewport_width > 0
        && options.viewport_width <= MAX_VIEWPORT_DIMENSION
        && options.viewport_height > 0
        && options.viewport_height <= MAX_VIEWPORT_DIMENSION;
    if !valid {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_options_invalid",
            "Viewer performance query, budgets, or viewport are invalid",
        ));
    }
    if let Some(output) = &options.output {
        portable_input_path(output, "Viewer performance probe output")?;
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn portable_input_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn prepare_probe_output(
    options: &ViewerPerformanceProbeOptions,
    root: &Path,
) -> Result<ProbeOutput, FrontendContractError> {
    let retain_workspace = options.output.is_none() && options.keep_temporary_output;
    let workspace = TemporaryWorkspace::create(retain_workspace)?;
    let (artifact_path, published_output_path, output_disposition, cleanup_explicit_output) =
        if let Some(requested) = &options.output {
            let artifact = absolute_output_path(root, requested)?;
            validate_new_output_target(&artifact)?;
            (
                artifact.clone(),
                Some(portable_input_path(
                    &artifact,
                    "Viewer performance probe output",
                )?),
                "operator_path_retained",
                true,
            )
        } else {
            let artifact = workspace.path.join("viewer_performance_probe.json");
            let published = if options.keep_temporary_output {
                Some(portable_input_path(
                    &artifact,
                    "Viewer performance probe output",
                )?)
            } else {
                None
            };
            let disposition = if options.keep_temporary_output {
                "temporary_path_retained"
            } else {
                "temporary_removed_after_verification"
            };
            (artifact, published, disposition, false)
        };
    Ok(ProbeOutput {
        artifact_path,
        published_output_path,
        output_disposition,
        cleanup_explicit_output,
        _workspace: workspace,
    })
}

fn absolute_output_path(root: &Path, requested: &Path) -> Result<PathBuf, FrontendContractError> {
    let path = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    let parent = path.parent().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            "Viewer performance probe output has no parent directory",
        )
    })?;
    verify_real_directory(parent, "Viewer performance probe output parent")?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            format!("canonicalize Viewer performance output parent failed: {error}"),
        )
    })?;
    let file_name = path.file_name().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            "Viewer performance probe output has no file name",
        )
    })?;
    Ok(parent.join(file_name))
}

fn validate_new_output_target(path: &Path) -> Result<(), FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(FrontendContractError::new(
            "viewer_performance_probe_output_exists",
            format!(
                "Viewer performance probe output already exists: {}",
                path.display()
            ),
        )),
        Err(error) => Err(FrontendContractError::new(
            "viewer_performance_probe_output_invalid",
            format!("inspect Viewer performance probe output failed: {error}"),
        )),
    }
}

fn run_probe_child(
    prepared: &PreparedViewerPerformanceProbe,
    output: &ProbeOutput,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg(&prepared.source.probe_path)
        .args(["--verify", "--fail-blocked", "--query"])
        .arg(&prepared.query)
        .arg("--out")
        .arg(&output.artifact_path)
        .arg("--sample-ms")
        .arg(prepared.sample_ms.to_string())
        .arg("--max-ready-ms")
        .arg(prepared.max_ready_ms.to_string())
        .arg("--min-fps")
        .arg(prepared.minimum_average_fps.to_string())
        .arg("--width")
        .arg(prepared.viewport_width.to_string())
        .arg("--height")
        .arg(prepared.viewport_height.to_string())
        .current_dir(&prepared.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_performance_probe_launch_failed",
                format!("launch Viewer performance probe failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_performance_probe_terminated",
            "Viewer performance probe terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_failed",
            format!("Viewer performance probe failed with exit code {exit_code}"),
        ));
    }
    Ok(exit_code)
}

fn node_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("node.exe")
    } else {
        OsString::from("node")
    }
}

fn verify_probe_artifact(
    prepared: &PreparedViewerPerformanceProbe,
    output: &ProbeOutput,
    successful_exit_code: i32,
) -> Result<VerifiedProbe, FrontendContractError> {
    let bytes = read_bounded_regular_file(
        &output.artifact_path,
        MAX_PROBE_ARTIFACT_BYTES,
        "Viewer performance probe artifact",
    )
    .map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_artifact_invalid",
            format!("Viewer performance artifact failed bounded validation: {error}"),
        )
    })?;
    let value = decode_json_strict(&bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_artifact_invalid",
            format!("decode strict Viewer performance artifact failed: {error}"),
        )
    })?;
    let artifact: ProbeArtifactV1 = serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_artifact_invalid",
            format!("decode typed Viewer performance artifact failed: {error}"),
        )
    })?;
    validate_probe_artifact(prepared, output, &artifact)?;
    Ok(VerifiedProbe {
        artifact_bytes: bytes,
        generated_at: artifact.generated_at,
        ready_ms: artifact.probe.ready_ms,
        average_fps: artifact.probe.raf_sample.average_fps,
        p95_frame_ms: artifact.probe.raf_sample.p95_frame_ms,
        maximum_frame_ms: artifact.probe.raf_sample.max_frame_ms,
        significant_pixel_count: artifact.probe.canvas_metrics.significant_pixel_count,
        browser_error_count: u64::try_from(artifact.probe.browser_errors.len()).map_err(|_| {
            FrontendContractError::new(
                "viewer_performance_probe_artifact_invalid",
                "Viewer performance browser error count is not addressable",
            )
        })?,
        blockers: artifact.blockers,
        successful_exit_code,
    })
}

fn validate_probe_artifact(
    prepared: &PreparedViewerPerformanceProbe,
    output: &ProbeOutput,
    artifact: &ProbeArtifactV1,
) -> Result<(), FrontendContractError> {
    let output_path = portable_input_path(
        &output.artifact_path,
        "Viewer performance probe artifact path",
    )?;
    let expected_residual = prepared
        .source
        .residual_live_work
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let actual_residual = artifact
        .residual_live_work
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let top_level_valid = artifact.schema_version == prepared.source.output_schema_version
        && valid_generated_at(&artifact.generated_at)
        && artifact.contract_pass == BooleanValue::True
        && artifact.reason_code == EXPECTED_REASON_CODE
        && artifact
            .summary_line
            .starts_with("Structure viewer browser performance probe: PASS |")
        && artifact
            .summary_line
            .ends_with("| mode=local_browser_probe")
        && artifact.probe_mode == prepared.source.expected_probe_mode
        && artifact.measured_browser_probe == BooleanValue::True
        && artifact.live_performance_claim == BooleanValue::False
        && artifact.independent_product_claim == BooleanValue::False
        && artifact.claim_boundary == prepared.source.expected_probe_claim_boundary
        && artifact.query == prepared.query
        && artifact.output_path == output_path
        && artifact.blockers.is_empty()
        && actual_residual == expected_residual;
    if !top_level_valid {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_contract_failed",
            "Viewer performance artifact top-level contract or claim boundary failed",
        ));
    }
    validate_probe_budgets(prepared, &artifact.budgets)?;
    validate_source_rows(&prepared.tracked_inputs, &artifact.source_rows)?;
    validate_measured_probe(prepared, &artifact.probe)
}

fn validate_probe_budgets(
    prepared: &PreparedViewerPerformanceProbe,
    budgets: &ProbeBudgets,
) -> Result<(), FrontendContractError> {
    let valid = budgets.max_ready_ms == prepared.max_ready_ms
        && finite_nonnegative(budgets.min_average_fps)
        && same_f64(budgets.min_average_fps, prepared.minimum_average_fps)
        && budgets.sample_ms == prepared.sample_ms;
    if !valid {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_budget_mismatch",
            "Viewer performance artifact budgets do not match the Rust-owned request",
        ));
    }
    Ok(())
}

fn validate_source_rows(
    inputs: &[TrackedInput],
    rows: &[ProbeSourceRow],
) -> Result<(), FrontendContractError> {
    if rows.len() != inputs.len() {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_source_identity_mismatch",
            "Viewer performance artifact source row count drifted",
        ));
    }
    for (input, row) in inputs.iter().zip(rows) {
        let byte_length = u64::try_from(input.bytes.len()).map_err(|_| {
            FrontendContractError::new(
                "viewer_performance_probe_source_identity_mismatch",
                "Viewer performance source byte length is not addressable",
            )
        })?;
        let sha256 = sha256_identity(&input.bytes);
        let expected_sha256 = sha256.strip_prefix("sha256:").unwrap_or(&sha256);
        if row.label != input.label
            || row.path != input.relative_path
            || !row.available
            || row.bytes != byte_length
            || row.sha256 != expected_sha256
        {
            return Err(FrontendContractError::new(
                "viewer_performance_probe_source_identity_mismatch",
                format!(
                    "Viewer performance source identity drifted: {}",
                    input.label
                ),
            ));
        }
    }
    Ok(())
}

fn validate_measured_probe(
    prepared: &PreparedViewerPerformanceProbe,
    probe: &MeasuredProbe,
) -> Result<(), FrontendContractError> {
    let metrics = &probe.canvas_metrics;
    let raf = &probe.raf_sample;
    let expected_url_suffix = format!("/src/structure-viewer/index.html?{}", prepared.query);
    let valid = valid_loopback_probe_url(&probe.url, &expected_url_suffix)
        && probe.viewport.width == prepared.viewport_width
        && probe.viewport.height == prepared.viewport_height
        && probe.ready_ms <= prepared.max_ready_ms
        && valid_canvas_metrics(metrics)
        && raf.frame_count >= 2
        && finite_positive(raf.elapsed_ms)
        && finite_positive(raf.average_fps)
        && raf.average_fps >= prepared.minimum_average_fps
        && finite_nonnegative(raf.average_frame_ms)
        && finite_nonnegative(raf.p95_frame_ms)
        && finite_nonnegative(raf.max_frame_ms)
        && raf.max_frame_ms >= raf.p95_frame_ms
        && probe.browser_errors.is_empty()
        && valid_navigation_timing(&probe.navigation_timing)
        && valid_viewer_state(&probe.viewer_state);
    if !valid {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_measurement_failed",
            "Viewer performance measurement or Rust-owned budget validation failed",
        ));
    }
    Ok(())
}

fn valid_canvas_metrics(metrics: &CanvasMetrics) -> bool {
    if !metrics.non_blank
        || metrics.canvas_width == 0
        || metrics.canvas_height == 0
        || metrics.sample_width != metrics.canvas_width.min(180)
        || metrics.sample_height != metrics.canvas_height.min(120)
        || !valid_bbox(&metrics.bbox, metrics.sample_width, metrics.sample_height)
    {
        return false;
    }
    let Some(sample_pixels) = metrics.sample_width.checked_mul(metrics.sample_height) else {
        return false;
    };
    if metrics.significant_pixel_count <= 32
        || metrics.significant_pixel_count > sample_pixels
        || metrics.significant_pixel_ratio < 0.001
        || metrics.coverage_width < 0.08
        || metrics.coverage_height < 0.1
        || !(0.08..=6.5).contains(&metrics.bbox_aspect_ratio)
        || !(0.08..=0.92).contains(&metrics.center_x)
        || !(0.08..=0.92).contains(&metrics.center_y)
    {
        return false;
    }
    let Some(sample_width) = exact_metric_f64(metrics.sample_width) else {
        return false;
    };
    let Some(sample_height) = exact_metric_f64(metrics.sample_height) else {
        return false;
    };
    let Some(sample_pixels) = exact_metric_f64(sample_pixels) else {
        return false;
    };
    let Some(significant_pixels) = exact_metric_f64(metrics.significant_pixel_count) else {
        return false;
    };
    let Some(bbox_width) = exact_metric_f64(metrics.bbox.width) else {
        return false;
    };
    let Some(bbox_height) = exact_metric_f64(metrics.bbox.height) else {
        return false;
    };
    let Some(horizontal_center_numerator) = metrics
        .bbox
        .min_x
        .checked_add(metrics.bbox.max_x)
        .and_then(|value| value.checked_add(1))
        .and_then(exact_metric_f64)
    else {
        return false;
    };
    let Some(vertical_center_numerator) = metrics
        .bbox
        .min_y
        .checked_add(metrics.bbox.max_y)
        .and_then(|value| value.checked_add(1))
        .and_then(exact_metric_f64)
    else {
        return false;
    };
    approximately_equal(
        metrics.significant_pixel_ratio,
        significant_pixels / sample_pixels,
    ) && approximately_equal(metrics.coverage_width, bbox_width / sample_width)
        && approximately_equal(metrics.coverage_height, bbox_height / sample_height)
        && approximately_equal(metrics.bbox_aspect_ratio, bbox_width / bbox_height.max(1.0))
        && approximately_equal(
            metrics.center_x,
            horizontal_center_numerator / 2.0 / sample_width,
        )
        && approximately_equal(
            metrics.center_y,
            vertical_center_numerator / 2.0 / sample_height,
        )
}

fn exact_metric_f64(value: u64) -> Option<f64> {
    u32::try_from(value).ok().map(f64::from)
}

fn approximately_equal(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= 1.0e-12
}

fn valid_loopback_probe_url(url: &str, suffix: &str) -> bool {
    let Some(value) = url.strip_prefix("http://127.0.0.1:") else {
        return false;
    };
    let Some((port, path)) = value.split_once('/') else {
        return false;
    };
    port.parse::<u16>().is_ok_and(|port| port > 0) && format!("/{path}") == suffix
}

fn valid_bbox(bbox: &CanvasBoundingBox, sample_width: u64, sample_height: u64) -> bool {
    bbox.min_x <= bbox.max_x
        && bbox.min_y <= bbox.max_y
        && bbox.max_x < sample_width
        && bbox.max_y < sample_height
        && bbox.width == bbox.max_x - bbox.min_x + 1
        && bbox.height == bbox.max_y - bbox.min_y + 1
}

fn valid_navigation_timing(timing: &NavigationTiming) -> bool {
    [
        timing.dom_content_loaded,
        timing.load_event_end,
        timing.response_end,
    ]
    .into_iter()
    .flatten()
    .all(finite_nonnegative)
}

fn valid_viewer_state(state: &ViewerState) -> bool {
    valid_text(&state.title)
        && state.stage_variant.len() <= 4_096
        && state.project_status.len() <= 4_096
        && state.stats_text.len() <= 400
        && !state.stage_variant.chars().any(char::is_control)
        && !state.project_status.chars().any(char::is_control)
        && !state.stats_text.chars().any(char::is_control)
}

fn finite_nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn same_f64(left: f64, right: f64) -> bool {
    left.to_bits() == right.to_bits()
}

fn finite_positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn valid_generated_at(value: &str) -> bool {
    let bytes = value.as_bytes();
    let layout_valid = bytes.len() == 24
        && bytes[4] == b'-'
        && bytes[7] == b'-'
        && bytes[10] == b'T'
        && bytes[13] == b':'
        && bytes[16] == b':'
        && bytes[19] == b'.'
        && bytes[23] == b'Z'
        && bytes.iter().enumerate().all(|(index, byte)| {
            matches!(index, 4 | 7 | 10 | 13 | 16 | 19 | 23) || byte.is_ascii_digit()
        });
    if !layout_valid {
        return false;
    }
    let year = decimal_digits(&bytes[0..4]);
    let month = decimal_digits(&bytes[5..7]);
    let day = decimal_digits(&bytes[8..10]);
    let hour = decimal_digits(&bytes[11..13]);
    let minute = decimal_digits(&bytes[14..16]);
    let second = decimal_digits(&bytes[17..19]);
    let days_in_month = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        2 => 28,
        _ => return false,
    };
    year > 0 && (1..=days_in_month).contains(&day) && hour <= 23 && minute <= 59 && second <= 59
}

fn decimal_digits(bytes: &[u8]) -> u32 {
    bytes
        .iter()
        .fold(0, |value, byte| value * 10 + u32::from(byte - b'0'))
}

fn is_leap_year(year: u32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn verify_execution_inputs_unchanged(
    prepared: &PreparedViewerPerformanceProbe,
) -> Result<(), FrontendContractError> {
    let post_contract = check_frontend_contract(&prepared.root)?;
    if post_contract.receipt_hash != prepared.frontend_contract_receipt_hash {
        return Err(FrontendContractError::new(
            "viewer_performance_probe_contract_changed",
            "frontend package or lock changed while Viewer performance verification executed",
        ));
    }
    for input in &prepared.tracked_inputs {
        let bytes = read_bounded_regular_file(
            &input.absolute_path,
            MAX_TRACKED_SOURCE_BYTES,
            &format!("Viewer performance tracked source {}", input.label),
        )?;
        if bytes != input.bytes {
            return Err(FrontendContractError::new(
                "viewer_performance_probe_contract_changed",
                format!(
                    "Viewer performance source changed during execution: {}",
                    input.label
                ),
            ));
        }
    }
    Ok(())
}

fn build_receipt(
    prepared: PreparedViewerPerformanceProbe,
    output: Option<&ProbeOutput>,
    verified: Option<&VerifiedProbe>,
) -> Result<ViewerPerformanceProbeReceiptV1, FrontendContractError> {
    let dry_run = verified.is_none();
    let tracked_sources = prepared
        .tracked_inputs
        .iter()
        .map(|input| {
            Ok(ViewerPerformanceSourceIdentityV1 {
                label: input.label.clone(),
                path: input.relative_path.clone(),
                bytes: u64::try_from(input.bytes.len()).map_err(|_| {
                    FrontendContractError::new(
                        "viewer_performance_probe_receipt_encode_failed",
                        "Viewer performance source length is not addressable",
                    )
                })?,
                sha256: sha256_identity(&input.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let mut receipt = ViewerPerformanceProbeReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_performance_probe".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        tracked_sources,
        query: prepared.query,
        sample_ms: prepared.sample_ms,
        max_ready_ms: prepared.max_ready_ms,
        minimum_average_fps: prepared.minimum_average_fps,
        viewport_width: prepared.viewport_width,
        viewport_height: prepared.viewport_height,
        requested_output: prepared.requested_output,
        published_output_path: output.and_then(|value| value.published_output_path.clone()),
        output_disposition: output
            .map_or("not_created", |value| value.output_disposition)
            .to_owned(),
        logical_command_template: prepared.logical_command_template,
        probe_schema_version: prepared.source.output_schema_version,
        probe_artifact_sha256: verified.map(|value| sha256_identity(&value.artifact_bytes)),
        probe_generated_at: verified.map(|value| value.generated_at.clone()),
        viewer_ready_ms: verified.map(|value| value.ready_ms),
        average_fps: verified.map(|value| value.average_fps),
        p95_frame_ms: verified.map(|value| value.p95_frame_ms),
        maximum_frame_ms: verified.map(|value| value.maximum_frame_ms),
        significant_pixel_count: verified.map(|value| value.significant_pixel_count),
        browser_error_count: verified.map_or(0, |value| value.browser_error_count),
        blockers: verified.map_or_else(Vec::new, |value| value.blockers.clone()),
        runtime_requirements: ViewerPerformanceRuntimeRequirementsV1 {
            node_required: true,
            browser_required: true,
            retained_node_internal_listener: true,
        },
        rust_owned_listener_count: 0,
        direct_processes_spawned: u64::from(!dry_run),
        successful_exit_code: verified.map(|value| value.successful_exit_code),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: dry_run,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &ViewerPerformanceProbeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_receipt_encode_failed",
            format!("project Viewer performance receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_performance_probe_receipt_encode_failed",
                "Viewer performance receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_performance_probe_receipt_encode_failed",
            format!("canonicalize Viewer performance receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{
        valid_generated_at, valid_loopback_probe_url, validate_viewer_performance_probe_source,
        ViewerPerformanceProbeSourceV1, ViewerPerformanceTrackedSourceV1,
        EXPECTED_RESIDUAL_LIVE_WORK, EXPECTED_TRACKED_SOURCES,
    };

    fn source() -> ViewerPerformanceProbeSourceV1 {
        ViewerPerformanceProbeSourceV1 {
            schema_version: "structural-native-viewer-performance-probe-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            probe_path: "scripts/measure-structure-viewer-performance.mjs".to_owned(),
            output_schema_version: "structure-viewer-browser-performance-probe.v1".to_owned(),
            default_query:
                "project=midas33_release&drawing=midas33_optimized&variant=optimized".to_owned(),
            default_sample_ms: 1_500,
            default_max_ready_ms: 60_000,
            default_min_average_fps: 5.0,
            default_viewport_width: 1_440,
            default_viewport_height: 1_000,
            tracked_sources: EXPECTED_TRACKED_SOURCES
                .iter()
                .map(|(label, path)| ViewerPerformanceTrackedSourceV1 {
                    label: (*label).to_owned(),
                    path: (*path).to_owned(),
                })
                .collect(),
            expected_probe_mode: "local_browser_probe".to_owned(),
            expected_probe_claim_boundary: "Local browser performance smoke only; not a normalized customer hardware FPS claim.".to_owned(),
            residual_live_work: EXPECTED_RESIDUAL_LIVE_WORK
                .iter()
                .map(ToString::to_string)
                .collect(),
            external_network_access_accounting:
                "not_instrumented_probe_loopback_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        }
    }

    #[test]
    fn source_contract_and_timestamp_are_strict() {
        let source = source();
        assert!(validate_viewer_performance_probe_source(&source).is_ok());
        let mut drift = source;
        drift.tracked_sources.swap(0, 1);
        assert!(validate_viewer_performance_probe_source(&drift).is_err());
        assert!(valid_generated_at("2026-08-13T12:34:56.789Z"));
        assert!(!valid_generated_at("2026-08-13T12:34:56Z"));
        assert!(!valid_generated_at("2026-02-30T12:34:56.789Z"));
        assert!(valid_generated_at("2024-02-29T23:59:59.999Z"));
    }

    #[test]
    fn probe_url_is_fixed_to_ipv4_loopback_and_exact_query() {
        let suffix = "/src/structure-viewer/index.html?project=p&drawing=d";
        assert!(valid_loopback_probe_url(
            "http://127.0.0.1:4173/src/structure-viewer/index.html?project=p&drawing=d",
            suffix,
        ));
        assert!(!valid_loopback_probe_url(
            "http://localhost:4173/src/structure-viewer/index.html?project=p&drawing=d",
            suffix,
        ));
        assert!(!valid_loopback_probe_url(
            "http://127.0.0.1:0/src/structure-viewer/index.html?project=p&drawing=d",
            suffix,
        ));
    }
}
