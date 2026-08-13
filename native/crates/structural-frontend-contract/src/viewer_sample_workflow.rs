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

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-sample-workflow-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-sample-workflow-receipt.v1";
const ARTIFACT_SCHEMA_V1: &str = "structure-viewer-sample-workflow-smoke.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_REASON_CODE: &str = "PASS";
const EXPECTED_DEFAULT_MAX_MINUTES: f64 = 30.0;
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_probe_loopback_and_browser_page_requests";
const MAX_TRACKED_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_ARTIFACT_BYTES: u64 = 1024 * 1024;
const MAX_PATH_BYTES: usize = 4_096;
const MAX_TEXT_BYTES: usize = 16 * 1024;
const MAX_MINUTES: f64 = 24.0 * 60.0;
const EXPECTED_STEP_LABELS: [&str; 4] = [
    "midas33 optimized sample project",
    "midas33 search and selection input",
    "real drawing sample project",
    "real drawing search input",
];
const EXPECTED_MEASURED_QUERIES: [&str; 2] = [
    "project=midas33_release&drawing=midas33_optimized&variant=optimized",
    "preset=real_drawing_private_3d&member=RD-001&drawing_asset=RD-001",
];
const EXPECTED_TRACKED_SOURCES: [(&str, &str); 3] = [
    ("viewer_index", "src/structure-viewer/index.html"),
    (
        "sample_workflow_probe",
        "scripts/verify-structure-viewer-sample-workflow.mjs",
    ),
    (
        "canvas_frame_probe",
        "scripts/structure-viewer-canvas-frame.mjs",
    ),
];
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerSampleWorkflowTrackedSourceV1 {
    label: String,
    path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerSampleWorkflowSourceV1 {
    schema_version: String,
    node_launcher: String,
    probe_path: String,
    output_schema_version: String,
    default_max_sample_completion_minutes: f64,
    expected_reason_code: String,
    step_labels: Vec<String>,
    measured_queries: Vec<String>,
    tracked_sources: Vec<ViewerSampleWorkflowTrackedSourceV1>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Viewer sample-workflow plan or execution.
#[derive(Clone, Debug, PartialEq)]
pub struct ViewerSampleWorkflowOptions {
    pub root: PathBuf,
    pub max_sample_completion_minutes: f64,
    pub output: Option<PathBuf>,
    pub dry_run: bool,
    pub keep_temporary_output: bool,
}

impl ViewerSampleWorkflowOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            max_sample_completion_minutes: EXPECTED_DEFAULT_MAX_MINUTES,
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

struct PreparedViewerSampleWorkflow {
    source: ViewerSampleWorkflowSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    tracked_inputs: Vec<TrackedInput>,
    max_sample_completion_minutes: f64,
    requested_output: Option<String>,
    logical_command_template: Vec<String>,
}

struct WorkflowOutput {
    artifact_path: PathBuf,
    published_output_path: Option<String>,
    output_disposition: &'static str,
    cleanup_explicit_output: bool,
    _workspace: TemporaryWorkspace,
}

impl Drop for WorkflowOutput {
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
        verify_real_directory(&parent, "Viewer sample-workflow temporary parent")?;
        for _ in 0..1_024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-sample-workflow-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path, retain }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_sample_workflow_temp_create_failed",
                        format!(
                            "create Viewer sample-workflow temporary directory failed: {error}"
                        ),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_sample_workflow_temp_create_failed",
            "could not allocate a unique Viewer sample-workflow temporary directory",
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
pub struct ViewerSampleWorkflowSourceIdentityV1 {
    pub label: String,
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerSampleWorkflowRuntimeRequirementsV1 {
    pub node_required: bool,
    pub browser_required: bool,
    pub retained_node_internal_listener: bool,
}

/// Canonical receipt for one planned or completed Viewer sample-workflow smoke.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ViewerSampleWorkflowReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub tracked_sources: Vec<ViewerSampleWorkflowSourceIdentityV1>,
    pub max_sample_completion_minutes: f64,
    pub requested_output: Option<String>,
    pub published_output_path: Option<String>,
    pub output_disposition: String,
    pub logical_command_template: Vec<String>,
    pub artifact_schema_version: String,
    pub artifact_sha256: Option<String>,
    pub artifact_generated_at: Option<String>,
    pub sample_completion_minutes: Option<f64>,
    pub verified_step_count: u64,
    pub step_rows_sha256: Option<String>,
    pub significant_pixel_count: Option<u64>,
    pub browser_error_count: u64,
    pub browser_warning_count: u64,
    pub runtime_requirements: ViewerSampleWorkflowRuntimeRequirementsV1,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct WorkflowArtifactV1 {
    schema_version: String,
    generated_at: String,
    contract_pass: bool,
    reason_code: String,
    sample_completion_minutes: f64,
    max_sample_completion_minutes: f64,
    browser_error_count: u64,
    browser_warning_count: u64,
    steps: Vec<WorkflowStepV1>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct WorkflowStepV1 {
    label: String,
    query: Option<String>,
    elapsed_ms: u64,
    browser_error_count: u64,
    browser_errors: Option<Vec<String>>,
    browser_warning_count: Option<u64>,
    browser_warnings: Option<Vec<String>>,
    canvas_nonblank: bool,
    canvas_significant_pixel_count: Option<u64>,
}

struct VerifiedWorkflow {
    artifact_bytes: Vec<u8>,
    artifact: WorkflowArtifactV1,
    significant_pixel_count: u64,
    successful_exit_code: i32,
}

/// Plan or execute the retained Viewer sample workflow under Rust ownership.
///
/// Dry-run validates and hashes every tracked input without creating output, binding a listener,
/// or spawning a process. Live execution owns one direct Node child and the raw artifact lifetime,
/// then strictly decodes and independently rechecks the exact four-step browser rehearsal, time
/// budget, browser errors and warnings, and nonblank canvas evidence before emitting a canonical
/// self-hashed receipt. The retained Node probe continues to own its internal loopback server,
/// Playwright, Chromium, Viewer JavaScript behavior, navigation, input, and raw payload creation.
/// This automated rehearsal is not human new-user observation or release approval evidence.
///
/// # Errors
///
/// Rejects unsafe options or outputs, source drift, child-process failure, malformed or oversized
/// artifacts, step drift, forged aggregate values, browser errors, and failed workflow budgets.
pub fn run_viewer_sample_workflow(
    options: &ViewerSampleWorkflowOptions,
) -> Result<ViewerSampleWorkflowReceiptV1, FrontendContractError> {
    let prepared = prepare_viewer_sample_workflow(options)?;
    if options.dry_run {
        return build_receipt(prepared, None, None);
    }
    let mut output = prepare_workflow_output(options, &prepared.root)?;
    let exit_code = run_workflow_child(&prepared, &output)?;
    let verified = verify_workflow_artifact(&prepared, &output, exit_code)?;
    verify_execution_inputs_unchanged(&prepared)?;
    let receipt = build_receipt(prepared, Some(&output), Some(&verified))?;
    output.cleanup_explicit_output = false;
    Ok(receipt)
}

fn prepare_viewer_sample_workflow(
    options: &ViewerSampleWorkflowOptions,
) -> Result<PreparedViewerSampleWorkflow, FrontendContractError> {
    validate_options(options)?;
    verify_real_directory(&options.root, "Viewer sample-workflow root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_sample_workflow_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_root_invalid",
            format!("canonicalize Viewer sample-workflow root failed: {error}"),
        )
    })?;
    let tracked_inputs = load_tracked_inputs(&root, &source)?;
    let requested_output = options
        .output
        .as_ref()
        .map(|path| portable_input_path(path, "Viewer sample-workflow output"))
        .transpose()?;
    let logical_command_template = vec![
        source.node_launcher.clone(),
        source.probe_path.clone(),
        "--fail-blocked".to_owned(),
        "--out".to_owned(),
        "{workflow_output}".to_owned(),
        "--max-minutes".to_owned(),
        options.max_sample_completion_minutes.to_string(),
    ];
    Ok(PreparedViewerSampleWorkflow {
        source,
        root,
        frontend_contract_receipt_hash,
        tracked_inputs,
        max_sample_completion_minutes: options.max_sample_completion_minutes,
        requested_output,
        logical_command_template,
    })
}

fn load_tracked_inputs(
    root: &Path,
    source: &ViewerSampleWorkflowSourceV1,
) -> Result<Vec<TrackedInput>, FrontendContractError> {
    source
        .tracked_sources
        .iter()
        .map(|row| {
            let absolute_path = resolve_required_file(root, &row.path)?;
            let bytes = read_bounded_regular_file(
                &absolute_path,
                MAX_TRACKED_SOURCE_BYTES,
                &format!("Viewer sample-workflow tracked source {}", row.label),
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

/// Encode a Viewer sample-workflow receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_sample_workflow_receipt_json(
    receipt: &ViewerSampleWorkflowReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_sample_workflow_receipt_encode_failed")
}

pub(crate) fn validate_viewer_sample_workflow_source(
    source: &ViewerSampleWorkflowSourceV1,
) -> Result<(), FrontendContractError> {
    let tracked_sources = source
        .tracked_sources
        .iter()
        .map(|row| (row.label.as_str(), row.path.as_str()))
        .collect::<Vec<_>>();
    let step_labels = source
        .step_labels
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let measured_queries = source
        .measured_queries
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
        && source.output_schema_version == ARTIFACT_SCHEMA_V1
        && same_f64(
            source.default_max_sample_completion_minutes,
            EXPECTED_DEFAULT_MAX_MINUTES,
        )
        && source.expected_reason_code == EXPECTED_REASON_CODE
        && step_labels == EXPECTED_STEP_LABELS
        && measured_queries == EXPECTED_MEASURED_QUERIES
        && tracked_sources == EXPECTED_TRACKED_SOURCES
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary)
        && unique_labels.len() == source.tracked_sources.len()
        && unique_paths.len() == source.tracked_sources.len();
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer sample-workflow contract is invalid",
        ));
    }
    Ok(())
}

fn validate_options(options: &ViewerSampleWorkflowOptions) -> Result<(), FrontendContractError> {
    if !options.max_sample_completion_minutes.is_finite()
        || options.max_sample_completion_minutes <= 0.0
        || options.max_sample_completion_minutes > MAX_MINUTES
    {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_options_invalid",
            "Viewer sample-workflow maximum minutes must be finite and in (0, 1440]",
        ));
    }
    if let Some(output) = &options.output {
        portable_input_path(output, "Viewer sample-workflow output")?;
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty()
        && value.len() <= MAX_TEXT_BYTES
        && !value.chars().any(char::is_control)
}

fn valid_warning_text(value: &str) -> bool {
    valid_text(value) && value.starts_with("Failed to load resource")
}

fn portable_input_path(path: &Path, label: &str) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_sample_workflow_output_invalid",
            format!("{label} must be UTF-8"),
        )
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_output_invalid",
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

fn prepare_workflow_output(
    options: &ViewerSampleWorkflowOptions,
    root: &Path,
) -> Result<WorkflowOutput, FrontendContractError> {
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
                    "Viewer sample-workflow output",
                )?),
                "operator_path_retained",
                true,
            )
        } else {
            let artifact = workspace.path.join("viewer_sample_workflow.json");
            let published = if options.keep_temporary_output {
                Some(portable_input_path(
                    &artifact,
                    "Viewer sample-workflow output",
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
    Ok(WorkflowOutput {
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
            "viewer_sample_workflow_output_invalid",
            "Viewer sample-workflow output has no parent directory",
        )
    })?;
    verify_real_directory(parent, "Viewer sample-workflow output parent")?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_output_invalid",
            format!("canonicalize Viewer sample-workflow output parent failed: {error}"),
        )
    })?;
    let file_name = path.file_name().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_sample_workflow_output_invalid",
            "Viewer sample-workflow output has no file name",
        )
    })?;
    Ok(parent.join(file_name))
}

fn validate_new_output_target(path: &Path) -> Result<(), FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(FrontendContractError::new(
            "viewer_sample_workflow_output_exists",
            format!(
                "Viewer sample-workflow output already exists: {}",
                path.display()
            ),
        )),
        Err(error) => Err(FrontendContractError::new(
            "viewer_sample_workflow_output_invalid",
            format!("inspect Viewer sample-workflow output failed: {error}"),
        )),
    }
}

fn run_workflow_child(
    prepared: &PreparedViewerSampleWorkflow,
    output: &WorkflowOutput,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg(&prepared.source.probe_path)
        .arg("--fail-blocked")
        .arg("--out")
        .arg(&output.artifact_path)
        .arg("--max-minutes")
        .arg(prepared.max_sample_completion_minutes.to_string())
        .current_dir(&prepared.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_sample_workflow_launch_failed",
                format!("launch Viewer sample-workflow probe failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_sample_workflow_terminated",
            "Viewer sample-workflow probe terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_failed",
            format!("Viewer sample-workflow probe failed with exit code {exit_code}"),
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

fn verify_workflow_artifact(
    prepared: &PreparedViewerSampleWorkflow,
    output: &WorkflowOutput,
    successful_exit_code: i32,
) -> Result<VerifiedWorkflow, FrontendContractError> {
    let bytes = read_bounded_regular_file(
        &output.artifact_path,
        MAX_ARTIFACT_BYTES,
        "Viewer sample-workflow artifact",
    )
    .map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_artifact_invalid",
            format!("Viewer sample-workflow artifact failed bounded validation: {error}"),
        )
    })?;
    let value = decode_json_strict(&bytes).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_artifact_invalid",
            format!("decode strict Viewer sample-workflow artifact failed: {error}"),
        )
    })?;
    let artifact: WorkflowArtifactV1 = serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_artifact_invalid",
            format!("decode typed Viewer sample-workflow artifact failed: {error}"),
        )
    })?;
    let significant_pixel_count = validate_workflow_artifact(prepared, &artifact)?;
    Ok(VerifiedWorkflow {
        artifact_bytes: bytes,
        artifact,
        significant_pixel_count,
        successful_exit_code,
    })
}

fn validate_workflow_artifact(
    prepared: &PreparedViewerSampleWorkflow,
    artifact: &WorkflowArtifactV1,
) -> Result<u64, FrontendContractError> {
    let top_level_valid = artifact.schema_version == prepared.source.output_schema_version
        && valid_generated_at(&artifact.generated_at)
        && artifact.contract_pass
        && artifact.reason_code == prepared.source.expected_reason_code
        && finite_nonnegative(artifact.sample_completion_minutes)
        && artifact.sample_completion_minutes <= prepared.max_sample_completion_minutes
        && same_f64(
            artifact.max_sample_completion_minutes,
            prepared.max_sample_completion_minutes,
        )
        && artifact.browser_error_count == 0
        && artifact.steps.len() == EXPECTED_STEP_LABELS.len();
    if !top_level_valid {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_contract_failed",
            "Viewer sample-workflow artifact top-level contract or budget failed",
        ));
    }

    let mut total_elapsed_ms = 0_u64;
    let mut total_errors = 0_u64;
    let mut total_warnings = 0_u64;
    let mut significant_pixels = 0_u64;
    for (index, step) in artifact.steps.iter().enumerate() {
        if step.label != EXPECTED_STEP_LABELS[index] || !step.canvas_nonblank {
            return Err(step_failure("step label or canvas state drifted"));
        }
        total_elapsed_ms = total_elapsed_ms
            .checked_add(step.elapsed_ms)
            .ok_or_else(|| step_failure("step elapsed-time aggregation overflowed"))?;
        total_errors = total_errors
            .checked_add(step.browser_error_count)
            .ok_or_else(|| step_failure("step browser-error aggregation overflowed"))?;
        if index == 0 || index == 2 {
            let query_index = index / 2;
            if step.query.as_deref() != Some(EXPECTED_MEASURED_QUERIES[query_index])
                || step.elapsed_ms == 0
                || step.browser_error_count != 0
                || step.browser_errors.as_deref() != Some(&[])
                || step.canvas_significant_pixel_count.unwrap_or(0) == 0
            {
                return Err(step_failure("measured Viewer step evidence drifted"));
            }
            let warnings = step
                .browser_warnings
                .as_deref()
                .ok_or_else(|| step_failure("measured Viewer step warning rows are missing"))?;
            let warning_count = step
                .browser_warning_count
                .ok_or_else(|| step_failure("measured Viewer step warning count is missing"))?;
            if usize::try_from(warning_count).ok() != Some(warnings.len())
                || warnings.iter().any(|warning| !valid_warning_text(warning))
            {
                return Err(step_failure("measured Viewer warning evidence drifted"));
            }
            total_warnings = total_warnings
                .checked_add(warning_count)
                .ok_or_else(|| step_failure("step browser-warning aggregation overflowed"))?;
            significant_pixels = significant_pixels
                .checked_add(step.canvas_significant_pixel_count.unwrap_or(0))
                .ok_or_else(|| step_failure("significant-pixel aggregation overflowed"))?;
        } else if step.query.is_some()
            || step.elapsed_ms != 0
            || step.browser_error_count != 0
            || step.browser_errors.is_some()
            || step.browser_warning_count.is_some()
            || step.browser_warnings.is_some()
            || step.canvas_significant_pixel_count.is_some()
        {
            return Err(step_failure(
                "synthetic input-confirmation step shape drifted",
            ));
        }
    }

    let exact_elapsed_ms = u32::try_from(total_elapsed_ms).map_err(|_| {
        FrontendContractError::new(
            "viewer_sample_workflow_aggregate_mismatch",
            "Viewer sample-workflow elapsed time exceeds the exact numeric range",
        )
    })?;
    let expected_minutes = f64::from(exact_elapsed_ms) / 60_000.0;
    if total_errors != artifact.browser_error_count
        || total_warnings != artifact.browser_warning_count
        || !approximately_equal(artifact.sample_completion_minutes, expected_minutes)
    {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_aggregate_mismatch",
            "Viewer sample-workflow aggregate values do not match the exact step rows",
        ));
    }
    Ok(significant_pixels)
}

fn step_failure(detail: &str) -> FrontendContractError {
    FrontendContractError::new("viewer_sample_workflow_step_failed", detail)
}

fn finite_nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn same_f64(left: f64, right: f64) -> bool {
    left.to_bits() == right.to_bits()
}

fn approximately_equal(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= 1.0e-12
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
    prepared: &PreparedViewerSampleWorkflow,
) -> Result<(), FrontendContractError> {
    let post_contract = check_frontend_contract(&prepared.root)?;
    if post_contract.receipt_hash != prepared.frontend_contract_receipt_hash {
        return Err(FrontendContractError::new(
            "viewer_sample_workflow_contract_changed",
            "frontend package or lock changed while Viewer sample-workflow verification executed",
        ));
    }
    for input in &prepared.tracked_inputs {
        let bytes = read_bounded_regular_file(
            &input.absolute_path,
            MAX_TRACKED_SOURCE_BYTES,
            &format!("Viewer sample-workflow tracked source {}", input.label),
        )?;
        if bytes != input.bytes {
            return Err(FrontendContractError::new(
                "viewer_sample_workflow_contract_changed",
                format!(
                    "Viewer sample-workflow source changed during execution: {}",
                    input.label
                ),
            ));
        }
    }
    Ok(())
}

fn build_receipt(
    prepared: PreparedViewerSampleWorkflow,
    output: Option<&WorkflowOutput>,
    verified: Option<&VerifiedWorkflow>,
) -> Result<ViewerSampleWorkflowReceiptV1, FrontendContractError> {
    let dry_run = verified.is_none();
    let tracked_sources = prepared
        .tracked_inputs
        .iter()
        .map(|input| {
            Ok(ViewerSampleWorkflowSourceIdentityV1 {
                label: input.label.clone(),
                path: input.relative_path.clone(),
                bytes: u64::try_from(input.bytes.len()).map_err(|_| {
                    FrontendContractError::new(
                        "viewer_sample_workflow_receipt_encode_failed",
                        "Viewer sample-workflow source length is not addressable",
                    )
                })?,
                sha256: sha256_identity(&input.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let step_rows_sha256 = verified
        .map(|value| hash_steps(&value.artifact.steps))
        .transpose()?;
    let verified_step_count = verified
        .map(|value| u64::try_from(value.artifact.steps.len()))
        .transpose()
        .map_err(|_| {
            FrontendContractError::new(
                "viewer_sample_workflow_receipt_encode_failed",
                "Viewer sample-workflow step count is not addressable",
            )
        })?
        .unwrap_or(0);
    let mut receipt = ViewerSampleWorkflowReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_sample_workflow".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        tracked_sources,
        max_sample_completion_minutes: prepared.max_sample_completion_minutes,
        requested_output: prepared.requested_output,
        published_output_path: output.and_then(|value| value.published_output_path.clone()),
        output_disposition: output
            .map_or("not_created", |value| value.output_disposition)
            .to_owned(),
        logical_command_template: prepared.logical_command_template,
        artifact_schema_version: prepared.source.output_schema_version,
        artifact_sha256: verified.map(|value| sha256_identity(&value.artifact_bytes)),
        artifact_generated_at: verified.map(|value| value.artifact.generated_at.clone()),
        sample_completion_minutes: verified.map(|value| value.artifact.sample_completion_minutes),
        verified_step_count,
        step_rows_sha256,
        significant_pixel_count: verified.map(|value| value.significant_pixel_count),
        browser_error_count: verified.map_or(0, |value| value.artifact.browser_error_count),
        browser_warning_count: verified.map_or(0, |value| value.artifact.browser_warning_count),
        runtime_requirements: ViewerSampleWorkflowRuntimeRequirementsV1 {
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

fn hash_steps(steps: &[WorkflowStepV1]) -> Result<String, FrontendContractError> {
    let value = serde_json::to_value(steps).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_receipt_encode_failed",
            format!("project Viewer sample-workflow step rows failed: {error}"),
        )
    })?;
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_receipt_encode_failed",
            format!("canonicalize Viewer sample-workflow step rows failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn hash_without_receipt_hash(
    receipt: &ViewerSampleWorkflowReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_receipt_encode_failed",
            format!("project Viewer sample-workflow receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "viewer_sample_workflow_receipt_encode_failed",
                "Viewer sample-workflow receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "viewer_sample_workflow_receipt_encode_failed",
            format!("canonicalize Viewer sample-workflow receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{
        validate_viewer_sample_workflow_source, ViewerSampleWorkflowSourceV1,
        ViewerSampleWorkflowTrackedSourceV1, EXPECTED_MEASURED_QUERIES, EXPECTED_STEP_LABELS,
        EXPECTED_TRACKED_SOURCES,
    };

    fn source() -> ViewerSampleWorkflowSourceV1 {
        ViewerSampleWorkflowSourceV1 {
            schema_version: "structural-native-viewer-sample-workflow-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            probe_path: "scripts/verify-structure-viewer-sample-workflow.mjs".to_owned(),
            output_schema_version: "structure-viewer-sample-workflow-smoke.v1".to_owned(),
            default_max_sample_completion_minutes: 30.0,
            expected_reason_code: "PASS".to_owned(),
            step_labels: EXPECTED_STEP_LABELS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            measured_queries: EXPECTED_MEASURED_QUERIES
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            tracked_sources: EXPECTED_TRACKED_SOURCES
                .iter()
                .map(|(label, path)| ViewerSampleWorkflowTrackedSourceV1 {
                    label: (*label).to_owned(),
                    path: (*path).to_owned(),
                })
                .collect(),
            external_network_access_accounting:
                "not_instrumented_probe_loopback_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded automated rehearsal; not human observation".to_owned(),
        }
    }

    #[test]
    fn source_contract_rejects_step_query_and_runtime_widening() {
        let mut value = source();
        validate_viewer_sample_workflow_source(&value).expect("valid source contract");
        value.step_labels.swap(0, 1);
        assert!(validate_viewer_sample_workflow_source(&value).is_err());

        let mut value = source();
        value.measured_queries[0].push_str("&forged=1");
        assert!(validate_viewer_sample_workflow_source(&value).is_err());

        let mut value = source();
        value.node_launcher = "sh".to_owned();
        assert!(validate_viewer_sample_workflow_source(&value).is_err());
    }

    #[test]
    fn generated_timestamp_validation_is_calendar_aware() {
        assert!(super::valid_generated_at("2026-08-13T12:34:56.789Z"));
        assert!(super::valid_generated_at("2024-02-29T23:59:59.000Z"));
        assert!(!super::valid_generated_at("2025-02-29T23:59:59.000Z"));
        assert!(!super::valid_generated_at("2026-08-13T12:34:56Z"));
    }
}
