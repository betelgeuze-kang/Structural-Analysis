use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-visual-regression-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-visual-regression-receipt.v1";
const ARTIFACT_SCHEMA_V1: &str = "structure-viewer-visual-regression-baseline.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PROBE_PATH: &str = "scripts/measure-structure-viewer-visual-regression.mjs";
const EXPECTED_BASELINE_PATH: &str =
    "implementation/phase1/structure_viewer_visual_regression_baseline.json";
const EXPECTED_VERIFY_MODE: &str = "verify";
const EXPECTED_BASELINE_MODE: &str = "baseline_update";
const EXPECTED_VISUAL_MODE: &str = "local_canvas_signature_baseline";
const EXPECTED_REASON_CODE: &str = "PASS";
const EXPECTED_CLAIM_BOUNDARY: &str =
    "Local visual signature regression only; not a pixel-perfect customer-device rendering claim.";
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_probe_loopback_and_browser_page_requests";
const EXPECTED_DEFAULT_TIMEOUT_MS: u64 = 60_000;
const EXPECTED_MAX_MEAN_ABS_DIFF: f64 = 32.0;
const EXPECTED_MAX_MAX_ABS_DIFF: f64 = 150.0;
const EXPECTED_MAX_COVERAGE_DELTA: f64 = 0.16;
const EXPECTED_MAX_CENTER_DELTA: f64 = 0.12;
const MAX_TIMEOUT_MS: u64 = 600_000;
const MAX_PATH_BYTES: usize = 4_096;
const MAX_TRACKED_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_BASELINE_BYTES: u64 = 32 * 1024 * 1024;
const MAX_REPORT_BYTES: u64 = 32 * 1024 * 1024;
const SIGNATURE_WIDTH: u64 = 24;
const SIGNATURE_HEIGHT: u64 = 18;
const SIGNATURE_VALUE_COUNT: usize = 432;
const EXPECTED_TRACKED_SOURCES: [(&str, &str); 4] = [
    ("viewer_index", "src/structure-viewer/index.html"),
    ("visual_regression_probe", EXPECTED_PROBE_PATH),
    (
        "canvas_frame_probe",
        "scripts/structure-viewer-canvas-frame.mjs",
    ),
    (
        "frontend_smoke_spec",
        "tests/frontend/structure-viewer-smoke.spec.ts",
    ),
];
const EXPECTED_CASE_IDS: [&str; 11] = [
    "desktop_midas33_optimized",
    "mobile_midas33_optimized",
    "desktop_midas33_solid",
    "desktop_midas33_contour",
    "desktop_midas33_plan_wireframe",
    "desktop_midas33_review_member",
    "desktop_midas33_compare_risk_overlay",
    "desktop_midas33_evidence_ingest_csv",
    "desktop_midas33_renderable_json_ingest",
    "desktop_midas33_section_edit_apply",
    "desktop_midas33_loadcomb_draft",
];
const EXPECTED_RESIDUAL_LIVE_WORK: [&str; 3] = [
    "Add screenshot image artifacts only when storage and review policy are defined.",
    "Run the same visual baseline across the customer browser/device matrix.",
    "Expand visual baselines to customer browser/device matrix and low-memory profiles.",
];
const DEFAULT_QUERY: &str = "project=midas33_release&drawing=midas33_optimized&variant=optimized";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerVisualTrackedSourceV1 {
    label: String,
    path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerVisualRegressionSourceV1 {
    schema_version: String,
    node_launcher: String,
    probe_path: String,
    baseline_path: String,
    output_schema_version: String,
    default_timeout_ms: u64,
    default_max_mean_abs_diff: f64,
    default_max_max_abs_diff: f64,
    default_max_coverage_delta: f64,
    default_max_center_delta: f64,
    case_ids: Vec<String>,
    tracked_sources: Vec<ViewerVisualTrackedSourceV1>,
    expected_verify_mode: String,
    expected_visual_regression_mode: String,
    expected_probe_claim_boundary: String,
    residual_live_work: Vec<String>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Viewer visual-regression plan or execution.
#[derive(Clone, Debug, PartialEq)]
pub struct ViewerVisualRegressionOptions {
    pub root: PathBuf,
    pub baseline: PathBuf,
    pub case_ids: Vec<String>,
    pub timeout_ms: u64,
    pub max_mean_abs_diff: f64,
    pub max_max_abs_diff: f64,
    pub max_coverage_delta: f64,
    pub max_center_delta: f64,
    pub output: Option<PathBuf>,
    pub dry_run: bool,
    pub keep_temporary_output: bool,
}

impl ViewerVisualRegressionOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            baseline: PathBuf::from(EXPECTED_BASELINE_PATH),
            case_ids: Vec::new(),
            timeout_ms: EXPECTED_DEFAULT_TIMEOUT_MS,
            max_mean_abs_diff: EXPECTED_MAX_MEAN_ABS_DIFF,
            max_max_abs_diff: EXPECTED_MAX_MAX_ABS_DIFF,
            max_coverage_delta: EXPECTED_MAX_COVERAGE_DELTA,
            max_center_delta: EXPECTED_MAX_CENTER_DELTA,
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

struct PreparedVisualRegression {
    source: ViewerVisualRegressionSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    tracked_inputs: Vec<TrackedInput>,
    baseline_path: PathBuf,
    baseline_relative: String,
    baseline_bytes: Vec<u8>,
    baseline: VisualArtifactV1,
    selected_case_ids: Vec<String>,
    timeout_ms: u64,
    tolerances: ViewerVisualTolerancesV1,
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
        verify_real_directory(&parent, "Viewer visual-regression temporary parent")?;
        for _ in 0..1_024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-visual-regression-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path, retain }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_visual_regression_temp_create_failed",
                        format!(
                            "create Viewer visual-regression temporary directory failed: {error}"
                        ),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_visual_regression_temp_create_failed",
            "could not allocate a unique Viewer visual-regression temporary directory",
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

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerVisualSourceIdentityV1 {
    pub label: String,
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[allow(clippy::struct_field_names)]
pub struct ViewerVisualTolerancesV1 {
    pub max_mean_abs_diff: f64,
    pub max_max_abs_diff: f64,
    pub max_coverage_delta: f64,
    pub max_center_delta: f64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerVisualRuntimeRequirementsV1 {
    pub node_required: bool,
    pub browser_required: bool,
    pub retained_node_internal_listener: bool,
}

/// Canonical receipt for one planned or completed Viewer visual-regression verification.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ViewerVisualRegressionReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub baseline_path: String,
    pub baseline_bytes: u64,
    pub baseline_sha256: String,
    pub tracked_sources: Vec<ViewerVisualSourceIdentityV1>,
    pub selected_case_ids: Vec<String>,
    pub timeout_ms: u64,
    pub tolerances: ViewerVisualTolerancesV1,
    pub requested_output: Option<String>,
    pub published_output_path: Option<String>,
    pub output_disposition: String,
    pub logical_command_template: Vec<String>,
    pub report_schema_version: String,
    pub report_artifact_sha256: Option<String>,
    pub report_generated_at: Option<String>,
    pub verified_case_count: usize,
    pub verified_compare_count: usize,
    pub case_rows_sha256: Option<String>,
    pub compare_rows_sha256: Option<String>,
    pub blockers: Vec<String>,
    pub runtime_requirements: ViewerVisualRuntimeRequirementsV1,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
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

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VisualArtifactV1 {
    schema_version: String,
    generated_at: String,
    contract_pass: BooleanValue,
    reason_code: String,
    summary_line: String,
    mode: String,
    visual_regression_mode: String,
    live_visual_claim: BooleanValue,
    independent_product_claim: BooleanValue,
    claim_boundary: String,
    baseline_path: String,
    tolerances: ArtifactTolerances,
    case_rows: Vec<VisualCaseRow>,
    compare_rows: Vec<VisualCompareRow>,
    visual_case_scope: VisualCaseScope,
    source_rows: Vec<VisualSourceRow>,
    residual_live_work: Vec<String>,
    blockers: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
#[allow(clippy::struct_field_names)]
struct ArtifactTolerances {
    max_mean_abs_diff: f64,
    max_max_abs_diff: f64,
    max_coverage_delta: f64,
    max_center_delta: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct VisualCaseRow {
    id: String,
    query: String,
    viewport: VisualViewport,
    expected_render_mode: String,
    expected_view_preset: String,
    expected_workflow_state: String,
    expected_selected_member: String,
    expected_review_status: String,
    expected_comparison_filter: String,
    expected_evidence_ingest_kind: String,
    expected_renderable_payload_kind: String,
    expected_section_edit_target: String,
    expected_loadcomb_draft_target: String,
    url: String,
    canvas_metrics: CanvasMetrics,
    canvas_signature: CanvasSignature,
    viewport_screenshot_sha256: String,
    markers: VisualMarkers,
    browser_errors: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct VisualViewport {
    width: u32,
    height: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
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

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct CanvasBoundingBox {
    min_x: u64,
    min_y: u64,
    max_x: u64,
    max_y: u64,
    width: u64,
    height: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CanvasSignature {
    available: bool,
    width: u64,
    height: u64,
    values: Vec<u64>,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct VisualMarkers {
    title: String,
    stage_variant: String,
    workspace_status: String,
    render_mode: String,
    view_preset: String,
    legend_visible: bool,
    selected_text: String,
    comparison_filter: String,
    evidence_ingest_kind: String,
    evidence_ingest_drawing_count: u64,
    renderable_payload_kind: String,
    section_edit_status: String,
    section_edit_list: String,
    loadcomb_edit_status: String,
    loadcomb_edit_list: String,
    report_panel: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct VisualCompareRow {
    id: String,
    status: String,
    blockers: Vec<String>,
    signature_delta: SignatureDelta,
    coverage_width_delta: f64,
    coverage_height_delta: f64,
    center_x_delta: f64,
    center_y_delta: f64,
    expected_render_mode: String,
    actual_render_mode: String,
    expected_view_preset: String,
    actual_view_preset: String,
    expected_workflow_state: String,
    expected_selected_member: String,
    actual_selected_text: String,
    expected_comparison_filter: String,
    actual_comparison_filter: String,
    expected_evidence_ingest_kind: String,
    actual_evidence_ingest_kind: String,
    expected_renderable_payload_kind: String,
    actual_renderable_payload_kind: String,
    expected_section_edit_target: String,
    actual_section_edit_status: String,
    expected_loadcomb_draft_target: String,
    actual_loadcomb_edit_status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SignatureDelta {
    comparable: bool,
    mean_abs_diff: f64,
    max_abs_diff: f64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VisualCaseScope {
    cases: usize,
    render_modes: Vec<String>,
    view_presets: Vec<String>,
    workflow_states: Vec<String>,
    viewports: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VisualSourceRow {
    label: String,
    path: String,
    available: bool,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Copy)]
struct CaseExpectation {
    id: &'static str,
    query: &'static str,
    width: u32,
    height: u32,
    render_mode: &'static str,
    view_preset: &'static str,
    workflow_state: &'static str,
    selected_member: &'static str,
    review_status: &'static str,
    comparison_filter: &'static str,
    evidence_ingest_kind: &'static str,
    renderable_payload_kind: &'static str,
    section_edit_target: &'static str,
    loadcomb_draft_target: &'static str,
}

const CASE_EXPECTATIONS: [CaseExpectation; 11] = [
    case("desktop_midas33_optimized", DEFAULT_QUERY, 1_440, 1_000, "wireframe", "", "optimized_wireframe", "", "", "", "", "", "", ""),
    case("mobile_midas33_optimized", DEFAULT_QUERY, 390, 844, "wireframe", "", "optimized_mobile", "", "", "", "", "", "", ""),
    case("desktop_midas33_solid", DEFAULT_QUERY, 1_440, 1_000, "solid", "", "optimized_solid", "", "", "", "", "", "", ""),
    case("desktop_midas33_contour", DEFAULT_QUERY, 1_440, 1_000, "contour", "", "optimized_contour", "", "", "", "", "", "", ""),
    case("desktop_midas33_plan_wireframe", DEFAULT_QUERY, 1_440, 1_000, "wireframe", "plan", "plan_view", "", "", "", "", "", "", ""),
    case("desktop_midas33_review_member", DEFAULT_QUERY, 1_440, 1_000, "solid", "review", "review_member_selection", "911", "approved", "", "", "", "", ""),
    case("desktop_midas33_compare_risk_overlay", "project=midas33_release&drawing=midas33_optimized&variant=compare", 1_440, 1_000, "solid", "review", "compare_overlay", "", "", "risk_up", "", "", "", ""),
    case("desktop_midas33_evidence_ingest_csv", DEFAULT_QUERY, 1_440, 1_000, "solid", "review", "evidence_ingest_csv", "911", "", "", "csv", "", "", ""),
    case("desktop_midas33_renderable_json_ingest", DEFAULT_QUERY, 1_440, 1_000, "solid", "review", "renderable_json_ingest", "", "", "", "json", "direct_model", "", ""),
    case("desktop_midas33_section_edit_apply", "project=midas33_release&drawing=midas33_optimized&variant=optimized&member=2911&member_set=2911", 1_440, 1_000, "solid", "review", "section_edit_apply", "2911", "", "", "", "", "VISUAL-REGRESSION-H400", ""),
    case("desktop_midas33_loadcomb_draft", DEFAULT_QUERY, 1_440, 1_000, "solid", "review", "loadcomb_draft", "", "", "", "", "", "", "VISUAL_REGRESSION_LCB_085"),
];

#[allow(clippy::too_many_arguments)]
const fn case(
    id: &'static str,
    query: &'static str,
    width: u32,
    height: u32,
    render_mode: &'static str,
    view_preset: &'static str,
    workflow_state: &'static str,
    selected_member: &'static str,
    review_status: &'static str,
    comparison_filter: &'static str,
    evidence_ingest_kind: &'static str,
    renderable_payload_kind: &'static str,
    section_edit_target: &'static str,
    loadcomb_draft_target: &'static str,
) -> CaseExpectation {
    CaseExpectation {
        id,
        query,
        width,
        height,
        render_mode,
        view_preset,
        workflow_state,
        selected_member,
        review_status,
        comparison_filter,
        evidence_ingest_kind,
        renderable_payload_kind,
        section_edit_target,
        loadcomb_draft_target,
    }
}

struct VerifiedReport {
    bytes: Vec<u8>,
    generated_at: String,
    case_rows_sha256: String,
    compare_rows_sha256: String,
    case_count: usize,
    compare_count: usize,
    successful_exit_code: i32,
}

/// Plan or execute retained Viewer visual measurement under Rust verification authority.
///
/// Dry-run validates and hashes the baseline and every tracked source without spawning a process.
/// Live execution owns one direct Node child and the report lifetime, then strictly decodes and
/// independently rechecks all case metadata, canvas geometry/signatures, markers, source hashes,
/// baseline deltas, and comparison tolerances before emitting a canonical self-hashed receipt.
///
/// # Errors
///
/// Rejects unsafe inputs or outputs, invalid baseline/report JSON, source mutation, child failure,
/// browser errors, malformed canvas evidence, identity drift, or failed visual comparisons.
pub fn run_viewer_visual_regression(
    options: &ViewerVisualRegressionOptions,
) -> Result<ViewerVisualRegressionReceiptV1, FrontendContractError> {
    let prepared = prepare_visual_regression(options)?;
    if options.dry_run {
        return build_receipt(prepared, None, None);
    }
    let mut output = prepare_probe_output(options, &prepared.root)?;
    let exit_code = run_probe_child(&prepared, &output)?;
    let verified = verify_report(&prepared, &output, exit_code)?;
    verify_execution_inputs_unchanged(&prepared)?;
    let receipt = build_receipt(prepared, Some(&output), Some(&verified))?;
    output.cleanup_explicit_output = false;
    Ok(receipt)
}

fn prepare_visual_regression(
    options: &ViewerVisualRegressionOptions,
) -> Result<PreparedVisualRegression, FrontendContractError> {
    validate_options(options)?;
    verify_real_directory(&options.root, "Viewer visual-regression root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_visual_regression_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_root_invalid",
            format!("canonicalize Viewer visual-regression root failed: {error}"),
        )
    })?;
    let baseline_relative = portable_relative_path(&options.baseline, "visual baseline")?;
    let baseline_path = resolve_required_file(&root, &baseline_relative)?;
    let baseline_bytes = read_bounded_regular_file(
        &baseline_path,
        MAX_BASELINE_BYTES,
        "Viewer visual-regression baseline",
    )?;
    let baseline = decode_artifact(&baseline_bytes, "baseline")?;
    let tracked_inputs = load_tracked_inputs(&root, &source)?;
    validate_baseline(&baseline, &baseline_relative, &tracked_inputs)?;
    let selected_case_ids = select_case_ids(&options.case_ids)?;
    let requested_output = options
        .output
        .as_ref()
        .map(|path| portable_input_path(path, "Viewer visual-regression output"))
        .transpose()?;
    let tolerances = ViewerVisualTolerancesV1 {
        max_mean_abs_diff: options.max_mean_abs_diff,
        max_max_abs_diff: options.max_max_abs_diff,
        max_coverage_delta: options.max_coverage_delta,
        max_center_delta: options.max_center_delta,
    };
    let mut logical_command_template = vec![
        source.node_launcher.clone(),
        source.probe_path.clone(),
        "--verify".to_owned(),
        "--fail-blocked".to_owned(),
    ];
    if selected_case_ids.len() != EXPECTED_CASE_IDS.len() {
        logical_command_template.extend(["--case-id".to_owned(), selected_case_ids.join(",")]);
    }
    logical_command_template.extend([
        "--timeout-ms".to_owned(),
        options.timeout_ms.to_string(),
        "--baseline".to_owned(),
        baseline_relative.clone(),
        "--out".to_owned(),
        "{visual_report_output}".to_owned(),
        "--max-mean-abs-diff".to_owned(),
        options.max_mean_abs_diff.to_string(),
        "--max-max-abs-diff".to_owned(),
        options.max_max_abs_diff.to_string(),
        "--max-coverage-delta".to_owned(),
        options.max_coverage_delta.to_string(),
        "--max-center-delta".to_owned(),
        options.max_center_delta.to_string(),
    ]);
    Ok(PreparedVisualRegression {
        source,
        root,
        frontend_contract_receipt_hash,
        tracked_inputs,
        baseline_path,
        baseline_relative,
        baseline_bytes,
        baseline,
        selected_case_ids,
        timeout_ms: options.timeout_ms,
        tolerances,
        requested_output,
        logical_command_template,
    })
}

fn load_tracked_inputs(
    root: &Path,
    source: &ViewerVisualRegressionSourceV1,
) -> Result<Vec<TrackedInput>, FrontendContractError> {
    source
        .tracked_sources
        .iter()
        .map(|row| {
            let absolute_path = resolve_required_file(root, &row.path)?;
            let bytes = read_bounded_regular_file(
                &absolute_path,
                MAX_TRACKED_SOURCE_BYTES,
                &format!("Viewer visual-regression tracked source {}", row.label),
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

/// Encode a Viewer visual-regression receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_visual_regression_receipt_json(
    receipt: &ViewerVisualRegressionReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_visual_regression_receipt_encode_failed")
}

pub(crate) fn validate_viewer_visual_regression_source(
    source: &ViewerVisualRegressionSourceV1,
) -> Result<(), FrontendContractError> {
    let tracked_sources = source
        .tracked_sources
        .iter()
        .map(|row| (row.label.as_str(), row.path.as_str()))
        .collect::<Vec<_>>();
    let case_ids = source
        .case_ids
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let residual = source
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
        && source.probe_path == EXPECTED_PROBE_PATH
        && source.baseline_path == EXPECTED_BASELINE_PATH
        && source.output_schema_version == ARTIFACT_SCHEMA_V1
        && source.default_timeout_ms == EXPECTED_DEFAULT_TIMEOUT_MS
        && same_f64(source.default_max_mean_abs_diff, EXPECTED_MAX_MEAN_ABS_DIFF)
        && same_f64(source.default_max_max_abs_diff, EXPECTED_MAX_MAX_ABS_DIFF)
        && same_f64(
            source.default_max_coverage_delta,
            EXPECTED_MAX_COVERAGE_DELTA,
        )
        && same_f64(source.default_max_center_delta, EXPECTED_MAX_CENTER_DELTA)
        && case_ids == EXPECTED_CASE_IDS
        && tracked_sources == EXPECTED_TRACKED_SOURCES
        && source.expected_verify_mode == EXPECTED_VERIFY_MODE
        && source.expected_visual_regression_mode == EXPECTED_VISUAL_MODE
        && source.expected_probe_claim_boundary == EXPECTED_CLAIM_BOUNDARY
        && residual == EXPECTED_RESIDUAL_LIVE_WORK
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary)
        && unique_labels.len() == source.tracked_sources.len()
        && unique_paths.len() == source.tracked_sources.len();
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer visual-regression contract is invalid",
        ));
    }
    Ok(())
}

fn validate_options(options: &ViewerVisualRegressionOptions) -> Result<(), FrontendContractError> {
    let valid = options.timeout_ms > 0
        && options.timeout_ms <= MAX_TIMEOUT_MS
        && valid_tolerance(options.max_mean_abs_diff, 255.0)
        && valid_tolerance(options.max_max_abs_diff, 255.0)
        && valid_tolerance(options.max_coverage_delta, 1.0)
        && valid_tolerance(options.max_center_delta, 1.0);
    if !valid {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_options_invalid",
            "Viewer visual-regression timeout or tolerances are invalid",
        ));
    }
    portable_relative_path(&options.baseline, "visual baseline")?;
    if let Some(output) = &options.output {
        portable_input_path(output, "Viewer visual-regression output")?;
    }
    Ok(())
}

fn valid_tolerance(value: f64, maximum: f64) -> bool {
    value.is_finite() && value >= 0.0 && value <= maximum
}

fn select_case_ids(requested: &[String]) -> Result<Vec<String>, FrontendContractError> {
    if requested.is_empty() {
        return Ok(EXPECTED_CASE_IDS.iter().map(ToString::to_string).collect());
    }
    let requested_set = requested
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if requested_set.len() != requested.len()
        || requested_set
            .iter()
            .any(|id| !EXPECTED_CASE_IDS.contains(id))
    {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_options_invalid",
            "Viewer visual-regression case IDs must be unique known IDs",
        ));
    }
    Ok(EXPECTED_CASE_IDS
        .iter()
        .filter(|id| requested_set.contains(**id))
        .map(ToString::to_string)
        .collect())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn portable_relative_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = portable_input_path(path, label)?;
    if path.is_absolute() || value.contains('\\') {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_baseline_invalid",
            format!("Viewer {label} must be a portable repository-relative path"),
        ));
    }
    let mut count = 0_usize;
    for component in path.components() {
        if !matches!(component, Component::Normal(_)) {
            return Err(FrontendContractError::new(
                "viewer_visual_regression_baseline_invalid",
                format!("Viewer {label} must not escape the repository"),
            ));
        }
        count += 1;
    }
    if count == 0 {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_baseline_invalid",
            format!("Viewer {label} is empty"),
        ));
    }
    Ok(value)
}

fn portable_input_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_visual_regression_output_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_output_invalid",
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn prepare_probe_output(
    options: &ViewerVisualRegressionOptions,
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
                    "Viewer visual-regression output",
                )?),
                "operator_path_retained",
                true,
            )
        } else {
            let artifact = workspace.path.join("viewer_visual_regression_report.json");
            let published = if options.keep_temporary_output {
                Some(portable_input_path(
                    &artifact,
                    "Viewer visual-regression output",
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
            "viewer_visual_regression_output_invalid",
            "Viewer visual-regression output has no parent directory",
        )
    })?;
    verify_real_directory(parent, "Viewer visual-regression output parent")?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_output_invalid",
            format!("canonicalize Viewer visual-regression output parent failed: {error}"),
        )
    })?;
    let file_name = path.file_name().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_visual_regression_output_invalid",
            "Viewer visual-regression output has no file name",
        )
    })?;
    Ok(parent.join(file_name))
}

fn validate_new_output_target(path: &Path) -> Result<(), FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(FrontendContractError::new(
            "viewer_visual_regression_output_exists",
            format!(
                "Viewer visual-regression output already exists: {}",
                path.display()
            ),
        )),
        Err(error) => Err(FrontendContractError::new(
            "viewer_visual_regression_output_invalid",
            format!("inspect Viewer visual-regression output failed: {error}"),
        )),
    }
}

fn run_probe_child(
    prepared: &PreparedVisualRegression,
    output: &ProbeOutput,
) -> Result<i32, FrontendContractError> {
    let mut command = Command::new(node_launcher());
    command
        .arg(&prepared.source.probe_path)
        .args(["--verify", "--fail-blocked"]);
    if prepared.selected_case_ids.len() != EXPECTED_CASE_IDS.len() {
        command
            .arg("--case-id")
            .arg(prepared.selected_case_ids.join(","));
    }
    let status = command
        .arg("--timeout-ms")
        .arg(prepared.timeout_ms.to_string())
        .arg("--baseline")
        .arg(&prepared.baseline_relative)
        .arg("--out")
        .arg(&output.artifact_path)
        .arg("--max-mean-abs-diff")
        .arg(prepared.tolerances.max_mean_abs_diff.to_string())
        .arg("--max-max-abs-diff")
        .arg(prepared.tolerances.max_max_abs_diff.to_string())
        .arg("--max-coverage-delta")
        .arg(prepared.tolerances.max_coverage_delta.to_string())
        .arg("--max-center-delta")
        .arg(prepared.tolerances.max_center_delta.to_string())
        .current_dir(&prepared.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_visual_regression_launch_failed",
                format!("launch Viewer visual-regression probe failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_visual_regression_terminated",
            "Viewer visual-regression probe terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_failed",
            format!("Viewer visual-regression probe failed with exit code {exit_code}"),
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

fn verify_report(
    prepared: &PreparedVisualRegression,
    output: &ProbeOutput,
    successful_exit_code: i32,
) -> Result<VerifiedReport, FrontendContractError> {
    let bytes = read_bounded_regular_file(
        &output.artifact_path,
        MAX_REPORT_BYTES,
        "Viewer visual-regression report",
    )
    .map_err(|error| artifact_error("report failed bounded validation", &error))?;
    let artifact = decode_artifact(&bytes, "report")?;
    validate_report(prepared, &artifact)?;
    Ok(VerifiedReport {
        case_rows_sha256: hash_canonical(&artifact.case_rows)?,
        compare_rows_sha256: hash_canonical(&artifact.compare_rows)?,
        case_count: artifact.case_rows.len(),
        compare_count: artifact.compare_rows.len(),
        generated_at: artifact.generated_at,
        bytes,
        successful_exit_code,
    })
}

fn decode_artifact(bytes: &[u8], label: &str) -> Result<VisualArtifactV1, FrontendContractError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_artifact_invalid",
            format!("decode strict Viewer visual-regression {label} failed: {error}"),
        )
    })?;
    serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_artifact_invalid",
            format!("decode typed Viewer visual-regression {label} failed: {error}"),
        )
    })
}

fn artifact_error(context: &str, error: &FrontendContractError) -> FrontendContractError {
    FrontendContractError::new(
        "viewer_visual_regression_artifact_invalid",
        format!("Viewer visual-regression {context}: {error}"),
    )
}

#[allow(clippy::too_many_lines)]
fn validate_baseline(
    baseline: &VisualArtifactV1,
    baseline_relative: &str,
    tracked_inputs: &[TrackedInput],
) -> Result<(), FrontendContractError> {
    validate_common_artifact(baseline, EXPECTED_BASELINE_MODE, baseline_relative)?;
    if !same_tolerances(
        &baseline.tolerances,
        &ViewerVisualTolerancesV1 {
            max_mean_abs_diff: EXPECTED_MAX_MEAN_ABS_DIFF,
            max_max_abs_diff: EXPECTED_MAX_MAX_ABS_DIFF,
            max_coverage_delta: EXPECTED_MAX_COVERAGE_DELTA,
            max_center_delta: EXPECTED_MAX_CENTER_DELTA,
        },
    ) || !baseline.compare_rows.is_empty()
        || !baseline.blockers.is_empty()
        || baseline.case_rows.len() != EXPECTED_CASE_IDS.len()
    {
        return Err(baseline_invalid(
            "baseline tolerances, comparison rows, blockers, or case count are invalid",
        ));
    }
    for (row, expectation) in baseline.case_rows.iter().zip(CASE_EXPECTATIONS) {
        validate_case(row, expectation).map_err(|error| {
            baseline_invalid(&format!("baseline case {} is invalid: {error}", row.id))
        })?;
    }
    validate_scope(&baseline.visual_case_scope, &baseline.case_rows)
        .map_err(|error| baseline_invalid(&format!("baseline scope is invalid: {error}")))?;
    validate_source_rows(&baseline.source_rows, tracked_inputs)
        .map_err(|error| baseline_invalid(&format!("baseline sources are invalid: {error}")))?;
    Ok(())
}

fn validate_report(
    prepared: &PreparedVisualRegression,
    report: &VisualArtifactV1,
) -> Result<(), FrontendContractError> {
    validate_common_artifact(report, EXPECTED_VERIFY_MODE, &prepared.baseline_relative)?;
    if !same_tolerances(&report.tolerances, &prepared.tolerances)
        || !report.blockers.is_empty()
        || report.case_rows.len() != prepared.selected_case_ids.len()
        || report.compare_rows.len() != prepared.selected_case_ids.len()
    {
        return Err(report_invalid(
            "report tolerances, blockers, or case/comparison counts are invalid",
        ));
    }
    for ((row, compare), id) in report
        .case_rows
        .iter()
        .zip(&report.compare_rows)
        .zip(&prepared.selected_case_ids)
    {
        let expectation = expectation(id).ok_or_else(|| report_invalid("unknown selected case"))?;
        validate_case(row, expectation)
            .map_err(|error| report_invalid(&format!("case {id} is invalid: {error}")))?;
        let baseline = prepared
            .baseline
            .case_rows
            .iter()
            .find(|candidate| candidate.id == *id)
            .ok_or_else(|| report_invalid(&format!("baseline case is missing: {id}")))?;
        validate_compare(compare, row, baseline, &prepared.tolerances)
            .map_err(|error| report_invalid(&format!("comparison {id} is invalid: {error}")))?;
    }
    validate_scope(&report.visual_case_scope, &report.case_rows)
        .map_err(|error| report_invalid(&format!("report scope is invalid: {error}")))?;
    validate_source_rows(&report.source_rows, &prepared.tracked_inputs)
        .map_err(|error| report_invalid(&format!("report sources are invalid: {error}")))?;
    Ok(())
}

fn validate_common_artifact(
    artifact: &VisualArtifactV1,
    expected_mode: &str,
    baseline_relative: &str,
) -> Result<(), FrontendContractError> {
    let expected_summary = format!(
        "Structure viewer visual regression: PASS | cases={0}/{0} | mode={expected_mode}",
        artifact.case_rows.len()
    );
    let residual = artifact
        .residual_live_work
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    if artifact.schema_version != ARTIFACT_SCHEMA_V1
        || !valid_generated_at(&artifact.generated_at)
        || artifact.contract_pass != BooleanValue::True
        || artifact.reason_code != EXPECTED_REASON_CODE
        || artifact.summary_line != expected_summary
        || artifact.mode != expected_mode
        || artifact.visual_regression_mode != EXPECTED_VISUAL_MODE
        || artifact.live_visual_claim != BooleanValue::False
        || artifact.independent_product_claim != BooleanValue::False
        || artifact.claim_boundary != EXPECTED_CLAIM_BOUNDARY
        || artifact.baseline_path != baseline_relative
        || residual != EXPECTED_RESIDUAL_LIVE_WORK
    {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_contract_failed",
            "Viewer visual-regression identity, claims, summary, or residual work are invalid",
        ));
    }
    Ok(())
}

fn validate_case(
    row: &VisualCaseRow,
    expected: CaseExpectation,
) -> Result<(), FrontendContractError> {
    if row.id != expected.id
        || row.query != expected.query
        || row.viewport.width != expected.width
        || row.viewport.height != expected.height
        || row.expected_render_mode != expected.render_mode
        || row.expected_view_preset != expected.view_preset
        || row.expected_workflow_state != expected.workflow_state
        || row.expected_selected_member != expected.selected_member
        || row.expected_review_status != expected.review_status
        || row.expected_comparison_filter != expected.comparison_filter
        || row.expected_evidence_ingest_kind != expected.evidence_ingest_kind
        || row.expected_renderable_payload_kind != expected.renderable_payload_kind
        || row.expected_section_edit_target != expected.section_edit_target
        || row.expected_loadcomb_draft_target != expected.loadcomb_draft_target
        || !valid_loopback_case_url(&row.url, expected.query)
        || !row.browser_errors.is_empty()
    {
        return Err(artifact_contract_error(
            "case identity, expected state, URL, or browser errors are invalid",
        ));
    }
    validate_canvas_metrics(&row.canvas_metrics, expected.id)?;
    validate_signature(&row.canvas_signature)?;
    if !valid_raw_sha256(&row.viewport_screenshot_sha256) {
        return Err(artifact_contract_error(
            "viewport screenshot identity is invalid",
        ));
    }
    validate_markers(&row.markers, expected)
}

fn validate_canvas_metrics(
    metrics: &CanvasMetrics,
    case_id: &str,
) -> Result<(), FrontendContractError> {
    let bbox = &metrics.bbox;
    let expected_sample_width = metrics.canvas_width.clamp(1, 180);
    let expected_sample_height = metrics.canvas_height.clamp(1, 120);
    let sample_area = metrics
        .sample_width
        .checked_mul(metrics.sample_height)
        .ok_or_else(|| artifact_contract_error("canvas sample area overflowed"))?;
    let expected_bbox_width = bbox
        .max_x
        .checked_sub(bbox.min_x)
        .and_then(|value| value.checked_add(1));
    let expected_bbox_height = bbox
        .max_y
        .checked_sub(bbox.min_y)
        .and_then(|value| value.checked_add(1));
    let min_coverage_height = if case_id == "desktop_midas33_plan_wireframe" {
        0.08
    } else {
        0.1
    };
    let max_aspect = if case_id == "desktop_midas33_plan_wireframe" {
        12.0
    } else {
        6.5
    };
    let valid = metrics.non_blank
        && metrics.canvas_width >= 10
        && metrics.canvas_height >= 10
        && metrics.sample_width == expected_sample_width
        && metrics.sample_height == expected_sample_height
        && sample_area > 0
        && metrics.significant_pixel_count > 32
        && metrics.significant_pixel_count <= sample_area
        && expected_bbox_width == Some(bbox.width)
        && expected_bbox_height == Some(bbox.height)
        && bbox.max_x < metrics.sample_width
        && bbox.max_y < metrics.sample_height
        && same_f64(
            metrics.significant_pixel_ratio,
            ratio(metrics.significant_pixel_count, sample_area),
        )
        && same_f64(
            metrics.coverage_width,
            ratio(bbox.width, metrics.sample_width),
        )
        && same_f64(
            metrics.coverage_height,
            ratio(bbox.height, metrics.sample_height),
        )
        && same_f64(
            metrics.bbox_aspect_ratio,
            ratio(bbox.width, bbox.height.max(1)),
        )
        && same_f64(
            metrics.center_x,
            ratio(bbox.min_x + bbox.max_x + 1, 2 * metrics.sample_width),
        )
        && same_f64(
            metrics.center_y,
            ratio(bbox.min_y + bbox.max_y + 1, 2 * metrics.sample_height),
        )
        && metrics.significant_pixel_ratio >= 0.001
        && (0.08..=1.0).contains(&metrics.coverage_width)
        && (min_coverage_height..=1.0).contains(&metrics.coverage_height)
        && (0.08..=max_aspect).contains(&metrics.bbox_aspect_ratio)
        && (0.08..=0.92).contains(&metrics.center_x)
        && (0.08..=0.92).contains(&metrics.center_y);
    if !valid {
        return Err(artifact_contract_error(
            "canvas geometry or framing derivation is invalid",
        ));
    }
    Ok(())
}

fn ratio(numerator: u64, denominator: u64) -> f64 {
    #[allow(clippy::cast_precision_loss)]
    let value = numerator as f64 / denominator as f64;
    value
}

fn validate_signature(signature: &CanvasSignature) -> Result<(), FrontendContractError> {
    let encoded = serde_json::to_vec(&signature.values).map_err(|error| {
        artifact_contract_error(&format!("encode canvas signature values failed: {error}"))
    })?;
    let actual_hash = sha256_identity(&encoded);
    let valid = signature.available
        && signature.width == SIGNATURE_WIDTH
        && signature.height == SIGNATURE_HEIGHT
        && signature.values.len() == SIGNATURE_VALUE_COUNT
        && signature.values.iter().all(|value| *value <= 255)
        && valid_raw_sha256(&signature.sha256)
        && actual_hash.strip_prefix("sha256:") == Some(signature.sha256.as_str());
    if !valid {
        return Err(artifact_contract_error(
            "canvas signature dimensions, values, or hash are invalid",
        ));
    }
    Ok(())
}

fn validate_markers(
    markers: &VisualMarkers,
    expected: CaseExpectation,
) -> Result<(), FrontendContractError> {
    let expected_variant = if expected.query.contains("variant=compare") {
        "Variant compare"
    } else {
        "Variant optimized"
    };
    let required_text_valid = [
        markers.title.as_str(),
        markers.stage_variant.as_str(),
        markers.workspace_status.as_str(),
        markers.render_mode.as_str(),
        markers.view_preset.as_str(),
        markers.selected_text.as_str(),
        markers.section_edit_status.as_str(),
        markers.section_edit_list.as_str(),
        markers.loadcomb_edit_status.as_str(),
        markers.loadcomb_edit_list.as_str(),
        markers.report_panel.as_str(),
    ]
    .iter()
    .all(|value| valid_marker_text(value));
    let valid = required_text_valid
        && markers.title == "Structural Insight Viewer"
        && markers.stage_variant == expected_variant
        && !markers.workspace_status.is_empty()
        && markers.render_mode == expected.render_mode
        && (expected.view_preset.is_empty() || markers.view_preset == expected.view_preset)
        && markers.legend_visible == (expected.render_mode == "contour")
        && (expected.selected_member.is_empty()
            || markers.selected_text.contains(expected.selected_member))
        && (expected.review_status.is_empty()
            || (expected.review_status == "approved"
                && markers.report_panel.contains("Review Task승인")
                && markers
                    .report_panel
                    .contains("Solver Receiptsolver receipt verified")))
        && (expected.comparison_filter.is_empty()
            || markers.comparison_filter == expected.comparison_filter)
        && (expected.evidence_ingest_kind.is_empty()
            || (markers.evidence_ingest_kind == expected.evidence_ingest_kind
                && markers.evidence_ingest_drawing_count >= 1))
        && (expected.renderable_payload_kind.is_empty()
            || markers.renderable_payload_kind == expected.renderable_payload_kind)
        && (expected.section_edit_target.is_empty()
            || (markers.section_edit_status.contains("Applied staged draft")
                && markers
                    .section_edit_list
                    .contains(expected.section_edit_target)))
        && (expected.loadcomb_draft_target.is_empty()
            || (markers
                .loadcomb_edit_status
                .contains(expected.loadcomb_draft_target)
                && markers
                    .loadcomb_edit_list
                    .contains(expected.loadcomb_draft_target)))
        && !markers.report_panel.is_empty();
    if !valid {
        return Err(artifact_contract_error(
            "Viewer state markers do not prove the expected workflow state",
        ));
    }
    Ok(())
}

#[allow(clippy::similar_names)]
fn validate_compare(
    compare: &VisualCompareRow,
    current: &VisualCaseRow,
    baseline: &VisualCaseRow,
    tolerances: &ViewerVisualTolerancesV1,
) -> Result<(), FrontendContractError> {
    let (mean_abs_diff, max_abs_diff) = signature_delta(
        &current.canvas_signature.values,
        &baseline.canvas_signature.values,
    )?;
    let coverage_width_delta =
        (current.canvas_metrics.coverage_width - baseline.canvas_metrics.coverage_width).abs();
    let coverage_height_delta =
        (current.canvas_metrics.coverage_height - baseline.canvas_metrics.coverage_height).abs();
    let center_x_delta = (current.canvas_metrics.center_x - baseline.canvas_metrics.center_x).abs();
    let center_y_delta = (current.canvas_metrics.center_y - baseline.canvas_metrics.center_y).abs();
    let fields_match = compare.id == current.id
        && compare.status == "pass"
        && compare.blockers.is_empty()
        && compare.signature_delta.comparable
        && same_f64(compare.signature_delta.mean_abs_diff, mean_abs_diff)
        && same_f64(compare.signature_delta.max_abs_diff, max_abs_diff)
        && same_f64(compare.coverage_width_delta, coverage_width_delta)
        && same_f64(compare.coverage_height_delta, coverage_height_delta)
        && same_f64(compare.center_x_delta, center_x_delta)
        && same_f64(compare.center_y_delta, center_y_delta)
        && compare.expected_render_mode == current.expected_render_mode
        && compare.actual_render_mode == current.markers.render_mode
        && compare.expected_view_preset == current.expected_view_preset
        && compare.actual_view_preset == current.markers.view_preset
        && compare.expected_workflow_state == current.expected_workflow_state
        && compare.expected_selected_member == current.expected_selected_member
        && compare.actual_selected_text == current.markers.selected_text
        && compare.expected_comparison_filter == current.expected_comparison_filter
        && compare.actual_comparison_filter == current.markers.comparison_filter
        && compare.expected_evidence_ingest_kind == current.expected_evidence_ingest_kind
        && compare.actual_evidence_ingest_kind == current.markers.evidence_ingest_kind
        && compare.expected_renderable_payload_kind == current.expected_renderable_payload_kind
        && compare.actual_renderable_payload_kind == current.markers.renderable_payload_kind
        && compare.expected_section_edit_target == current.expected_section_edit_target
        && compare.actual_section_edit_status == current.markers.section_edit_status
        && compare.expected_loadcomb_draft_target == current.expected_loadcomb_draft_target
        && compare.actual_loadcomb_edit_status == current.markers.loadcomb_edit_status
        && current.markers == baseline.markers
        && mean_abs_diff <= tolerances.max_mean_abs_diff
        && max_abs_diff <= tolerances.max_max_abs_diff
        && coverage_width_delta <= tolerances.max_coverage_delta
        && coverage_height_delta <= tolerances.max_coverage_delta
        && center_x_delta <= tolerances.max_center_delta
        && center_y_delta <= tolerances.max_center_delta;
    if !fields_match {
        return Err(artifact_contract_error(
            "comparison fields or independently recomputed deltas are invalid",
        ));
    }
    Ok(())
}

fn signature_delta(left: &[u64], right: &[u64]) -> Result<(f64, f64), FrontendContractError> {
    if left.len() != SIGNATURE_VALUE_COUNT || right.len() != SIGNATURE_VALUE_COUNT {
        return Err(artifact_contract_error(
            "signature delta inputs are not comparable",
        ));
    }
    let mut total = 0_u64;
    let mut maximum = 0_u64;
    for (left, right) in left.iter().zip(right) {
        let difference = left.abs_diff(*right);
        total = total
            .checked_add(difference)
            .ok_or_else(|| artifact_contract_error("signature delta overflowed"))?;
        maximum = maximum.max(difference);
    }
    Ok((ratio(total, 432), ratio(maximum, 1)))
}

fn validate_scope(
    scope: &VisualCaseScope,
    rows: &[VisualCaseRow],
) -> Result<(), FrontendContractError> {
    let render_modes = unique_order(rows.iter().map(|row| row.expected_render_mode.as_str()));
    let view_presets = unique_order(
        rows.iter()
            .map(|row| row.expected_view_preset.as_str())
            .filter(|value| !value.is_empty()),
    );
    let workflow_states = unique_order(rows.iter().map(|row| row.expected_workflow_state.as_str()));
    let mut viewports = Vec::new();
    for row in rows {
        let viewport = format!("{}x{}", row.viewport.width, row.viewport.height);
        if !viewports.contains(&viewport) {
            viewports.push(viewport);
        }
    }
    if scope.cases != rows.len()
        || scope.render_modes != render_modes
        || scope.view_presets != view_presets
        || scope.workflow_states != workflow_states
        || scope.viewports != viewports
    {
        return Err(artifact_contract_error(
            "visual case scope is not derived from the ordered case rows",
        ));
    }
    Ok(())
}

fn unique_order<'a>(values: impl Iterator<Item = &'a str>) -> Vec<String> {
    let mut seen = BTreeSet::new();
    let mut ordered = Vec::new();
    for value in values {
        if seen.insert(value) {
            ordered.push(value.to_owned());
        }
    }
    ordered
}

fn validate_source_rows(
    rows: &[VisualSourceRow],
    tracked_inputs: &[TrackedInput],
) -> Result<(), FrontendContractError> {
    if rows.len() != tracked_inputs.len() {
        return Err(artifact_contract_error("source-row count is invalid"));
    }
    for (row, input) in rows.iter().zip(tracked_inputs) {
        let expected_bytes = u64::try_from(input.bytes.len())
            .map_err(|_| artifact_contract_error("tracked source length is not addressable"))?;
        let expected_sha = sha256_identity(&input.bytes);
        if row.label != input.label
            || row.path != input.relative_path
            || !row.available
            || row.bytes != expected_bytes
            || !valid_raw_sha256(&row.sha256)
            || expected_sha.strip_prefix("sha256:") != Some(row.sha256.as_str())
        {
            return Err(FrontendContractError::new(
                "viewer_visual_regression_source_identity_mismatch",
                format!(
                    "Viewer visual-regression source identity differs: {}",
                    input.label
                ),
            ));
        }
    }
    Ok(())
}

fn expectation(id: &str) -> Option<CaseExpectation> {
    CASE_EXPECTATIONS
        .iter()
        .copied()
        .find(|candidate| candidate.id == id)
}

fn same_tolerances(left: &ArtifactTolerances, right: &ViewerVisualTolerancesV1) -> bool {
    same_f64(left.max_mean_abs_diff, right.max_mean_abs_diff)
        && same_f64(left.max_max_abs_diff, right.max_max_abs_diff)
        && same_f64(left.max_coverage_delta, right.max_coverage_delta)
        && same_f64(left.max_center_delta, right.max_center_delta)
}

fn same_f64(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= 1.0e-12
}

fn valid_raw_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_marker_text(value: &str) -> bool {
    value.len() <= 16 * 1024
        && !value
            .chars()
            .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
}

fn valid_loopback_case_url(value: &str, query: &str) -> bool {
    let Some(rest) = value.strip_prefix("http://127.0.0.1:") else {
        return false;
    };
    let Some((port, path)) = rest.split_once('/') else {
        return false;
    };
    let valid_port = !port.is_empty()
        && port.bytes().all(|byte| byte.is_ascii_digit())
        && port.parse::<u16>().is_ok_and(|value| value > 0);
    valid_port && path == format!("src/structure-viewer/index.html?{query}")
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

fn baseline_invalid(detail: &str) -> FrontendContractError {
    FrontendContractError::new("viewer_visual_regression_baseline_invalid", detail)
}

fn report_invalid(detail: &str) -> FrontendContractError {
    FrontendContractError::new("viewer_visual_regression_artifact_invalid", detail)
}

fn artifact_contract_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("viewer_visual_regression_measurement_failed", detail)
}

fn verify_execution_inputs_unchanged(
    prepared: &PreparedVisualRegression,
) -> Result<(), FrontendContractError> {
    let post_contract = check_frontend_contract(&prepared.root)?;
    if post_contract.receipt_hash != prepared.frontend_contract_receipt_hash {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_contract_changed",
            "frontend package or lock changed while Viewer visual regression executed",
        ));
    }
    let baseline_bytes = read_bounded_regular_file(
        &prepared.baseline_path,
        MAX_BASELINE_BYTES,
        "Viewer visual-regression baseline",
    )?;
    if baseline_bytes != prepared.baseline_bytes {
        return Err(FrontendContractError::new(
            "viewer_visual_regression_contract_changed",
            "Viewer visual-regression baseline changed during execution",
        ));
    }
    for input in &prepared.tracked_inputs {
        let bytes = read_bounded_regular_file(
            &input.absolute_path,
            MAX_TRACKED_SOURCE_BYTES,
            &format!("Viewer visual-regression tracked source {}", input.label),
        )?;
        if bytes != input.bytes {
            return Err(FrontendContractError::new(
                "viewer_visual_regression_contract_changed",
                format!(
                    "Viewer visual-regression source changed during execution: {}",
                    input.label
                ),
            ));
        }
    }
    Ok(())
}

fn build_receipt(
    prepared: PreparedVisualRegression,
    output: Option<&ProbeOutput>,
    verified: Option<&VerifiedReport>,
) -> Result<ViewerVisualRegressionReceiptV1, FrontendContractError> {
    let dry_run = verified.is_none();
    let tracked_sources = prepared
        .tracked_inputs
        .iter()
        .map(|input| {
            Ok(ViewerVisualSourceIdentityV1 {
                label: input.label.clone(),
                path: input.relative_path.clone(),
                bytes: u64::try_from(input.bytes.len()).map_err(|_| {
                    FrontendContractError::new(
                        "viewer_visual_regression_receipt_encode_failed",
                        "Viewer visual-regression source length is not addressable",
                    )
                })?,
                sha256: sha256_identity(&input.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let baseline_bytes = u64::try_from(prepared.baseline_bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "viewer_visual_regression_receipt_encode_failed",
            "Viewer visual-regression baseline length is not addressable",
        )
    })?;
    let mut receipt = ViewerVisualRegressionReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_visual_regression".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        baseline_path: prepared.baseline_relative,
        baseline_bytes,
        baseline_sha256: sha256_identity(&prepared.baseline_bytes),
        tracked_sources,
        selected_case_ids: prepared.selected_case_ids,
        timeout_ms: prepared.timeout_ms,
        tolerances: ViewerVisualTolerancesV1 {
            max_mean_abs_diff: prepared.tolerances.max_mean_abs_diff,
            max_max_abs_diff: prepared.tolerances.max_max_abs_diff,
            max_coverage_delta: prepared.tolerances.max_coverage_delta,
            max_center_delta: prepared.tolerances.max_center_delta,
        },
        requested_output: prepared.requested_output,
        published_output_path: output.and_then(|value| value.published_output_path.clone()),
        output_disposition: output
            .map_or("not_created", |value| value.output_disposition)
            .to_owned(),
        logical_command_template: prepared.logical_command_template,
        report_schema_version: prepared.source.output_schema_version,
        report_artifact_sha256: verified.map(|value| sha256_identity(&value.bytes)),
        report_generated_at: verified.map(|value| value.generated_at.clone()),
        verified_case_count: verified.map_or(0, |value| value.case_count),
        verified_compare_count: verified.map_or(0, |value| value.compare_count),
        case_rows_sha256: verified.map(|value| value.case_rows_sha256.clone()),
        compare_rows_sha256: verified.map(|value| value.compare_rows_sha256.clone()),
        blockers: Vec::new(),
        runtime_requirements: ViewerVisualRuntimeRequirementsV1 {
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

fn hash_canonical<T: Serialize>(value: &T) -> Result<String, FrontendContractError> {
    let value = serde_json::to_value(value).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_receipt_encode_failed",
            format!("project Viewer visual-regression rows failed: {error}"),
        )
    })?;
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_receipt_encode_failed",
            format!("canonicalize Viewer visual-regression rows failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn hash_without_receipt_hash(
    receipt: &ViewerVisualRegressionReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_receipt_encode_failed",
            format!("project Viewer visual-regression receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_visual_regression_receipt_encode_failed",
                "Viewer visual-regression receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_visual_regression_receipt_encode_failed",
            format!("canonicalize Viewer visual-regression receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{
        valid_generated_at, valid_loopback_case_url, validate_viewer_visual_regression_source,
        ViewerVisualRegressionSourceV1, ViewerVisualTrackedSourceV1, EXPECTED_CASE_IDS,
        EXPECTED_RESIDUAL_LIVE_WORK, EXPECTED_TRACKED_SOURCES,
    };

    fn valid_source() -> ViewerVisualRegressionSourceV1 {
        ViewerVisualRegressionSourceV1 {
            schema_version: "structural-native-viewer-visual-regression-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            probe_path: "scripts/measure-structure-viewer-visual-regression.mjs".to_owned(),
            baseline_path:
                "implementation/phase1/structure_viewer_visual_regression_baseline.json".to_owned(),
            output_schema_version: "structure-viewer-visual-regression-baseline.v1".to_owned(),
            default_timeout_ms: 60_000,
            default_max_mean_abs_diff: 32.0,
            default_max_max_abs_diff: 150.0,
            default_max_coverage_delta: 0.16,
            default_max_center_delta: 0.12,
            case_ids: EXPECTED_CASE_IDS.iter().map(ToString::to_string).collect(),
            tracked_sources: EXPECTED_TRACKED_SOURCES
                .iter()
                .map(|(label, path)| ViewerVisualTrackedSourceV1 {
                    label: (*label).to_owned(),
                    path: (*path).to_owned(),
                })
                .collect(),
            expected_verify_mode: "verify".to_owned(),
            expected_visual_regression_mode: "local_canvas_signature_baseline".to_owned(),
            expected_probe_claim_boundary: "Local visual signature regression only; not a pixel-perfect customer-device rendering claim.".to_owned(),
            residual_live_work: EXPECTED_RESIDUAL_LIVE_WORK
                .iter()
                .map(ToString::to_string)
                .collect(),
            external_network_access_accounting:
                "not_instrumented_probe_loopback_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded transitional authority".to_owned(),
        }
    }

    #[test]
    fn source_contract_and_timestamp_are_strict() {
        let source = valid_source();
        assert!(validate_viewer_visual_regression_source(&source).is_ok());
        let mut drift = source;
        drift.case_ids.swap(0, 1);
        assert!(validate_viewer_visual_regression_source(&drift).is_err());
        assert!(valid_generated_at("2024-02-29T23:59:59.999Z"));
        assert!(!valid_generated_at("2023-02-29T23:59:59.999Z"));
        assert!(!valid_generated_at("2024-02-29T24:00:00.000Z"));
    }

    #[test]
    fn loopback_case_url_is_ipv4_and_query_exact() {
        let query = "project=p&drawing=d";
        assert!(valid_loopback_case_url(
            "http://127.0.0.1:49152/src/structure-viewer/index.html?project=p&drawing=d",
            query,
        ));
        assert!(!valid_loopback_case_url(
            "http://localhost:49152/src/structure-viewer/index.html?project=p&drawing=d",
            query,
        ));
        assert!(!valid_loopback_case_url(
            "http://127.0.0.1:0/src/structure-viewer/index.html?project=p&drawing=d",
            query,
        ));
    }
}
