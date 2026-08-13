use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};
use crate::verified_publication::{
    portable_publication_path, prepare_verified_publication_target, publish_verified_outputs,
    VerifiedOutput, VerifiedPublicationCodes, VerifiedPublicationTarget,
    VERIFIED_PUBLICATION_STRATEGY,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-readme-capture-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-readme-capture-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_CAPTURE_PATH: &str = "scripts/capture-readme-viewer-image.mjs";
const EXPECTED_DEFAULT_OUTPUT: &str = "docs/assets/commercialization-status-card.png";
const EXPECTED_VIEWER_PATH: &str = "/src/structure-viewer/index.html?preset=midas33_optimized";
const EXPECTED_VIEWPORT_WIDTH: u32 = 1600;
const EXPECTED_VIEWPORT_HEIGHT: u32 = 900;
const EXPECTED_VIEW_PRESET: &str = "review";
const EXPECTED_CAMERA_X: f64 = -0.55;
const EXPECTED_CAMERA_Y: f64 = 0.85;
const EXPECTED_CAMERA_Z: f64 = 0.35;
const EXPECTED_MINIMUM_PNG_BYTES: u64 = 10_000;
const EXPECTED_MAXIMUM_PNG_BYTES: u64 = 64 * 1024 * 1024;
const EXPECTED_COLOR_TYPES: [u8; 2] = [2, 6];
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_capture_loopback_and_browser_page_requests";
const MAX_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_PRESET_BYTES: usize = 128;
const MAX_PNG_CHUNKS: usize = 16_384;
const PNG_SIGNATURE: &[u8; 8] = b"\x89PNG\r\n\x1a\n";
const PUBLICATION_CODES: VerifiedPublicationCodes = VerifiedPublicationCodes {
    output_invalid: "viewer_readme_capture_output_invalid",
    output_changed: "viewer_readme_capture_output_changed",
    stage_failed: "viewer_readme_capture_stage_failed",
    publish_failed: "viewer_readme_capture_publish_failed",
    backup_cleanup_failed: "viewer_readme_capture_backup_cleanup_failed",
};
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerReadmeCaptureSourceV1 {
    schema_version: String,
    node_launcher: String,
    capture_path: String,
    default_output_path: String,
    viewer_path: String,
    viewport_width: u32,
    viewport_height: u32,
    default_view_preset: String,
    default_camera_x: f64,
    default_camera_y: f64,
    default_camera_z: f64,
    minimum_png_bytes: u64,
    maximum_png_bytes: u64,
    allowed_png_color_types: Vec<u8>,
    tracked_sources: Vec<ViewerReadmeCaptureTrackedSourceV1>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ViewerReadmeCaptureTrackedSourceV1 {
    label: String,
    path: String,
}

/// Inputs for one README Viewer image capture plan or publication.
#[derive(Clone, Debug, PartialEq)]
pub struct ViewerReadmeCaptureOptions {
    pub root: PathBuf,
    pub output: PathBuf,
    pub view_preset: String,
    pub camera_x: f64,
    pub camera_y: f64,
    pub camera_z: f64,
    pub dry_run: bool,
}

impl ViewerReadmeCaptureOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            output: PathBuf::from(EXPECTED_DEFAULT_OUTPUT),
            view_preset: EXPECTED_VIEW_PRESET.to_owned(),
            camera_x: EXPECTED_CAMERA_X,
            camera_y: EXPECTED_CAMERA_Y,
            camera_z: EXPECTED_CAMERA_Z,
            dry_run: false,
        }
    }
}

/// One frozen source identity used by the README capture command.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerReadmeCaptureSourceIdentityV1 {
    pub label: String,
    pub path: String,
    pub sha256: String,
}

/// Canonical receipt for one planned or published README Viewer capture.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ViewerReadmeCaptureReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub source_identities: Vec<ViewerReadmeCaptureSourceIdentityV1>,
    pub viewer_path: String,
    pub viewport_width: u32,
    pub viewport_height: u32,
    pub view_preset: String,
    pub camera_x: f64,
    pub camera_y: f64,
    pub camera_z: f64,
    pub requested_output: String,
    pub published_output_path: Option<String>,
    pub previous_output_state: String,
    pub previous_output_byte_length: Option<u64>,
    pub previous_output_sha256: Option<String>,
    pub output_disposition: String,
    pub publication_strategy: String,
    pub logical_command_template: Vec<String>,
    pub environment_overrides: Vec<String>,
    pub png_byte_length: Option<u64>,
    pub png_sha256: Option<String>,
    pub png_width: Option<u32>,
    pub png_height: Option<u32>,
    pub png_bit_depth: Option<u8>,
    pub png_color_type: Option<u8>,
    pub png_chunk_count: Option<u64>,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedCapture {
    source: ViewerReadmeCaptureSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    source_rows: Vec<LoadedSource>,
    output: VerifiedPublicationTarget,
    logical_command_template: Vec<String>,
    environment_overrides: Vec<String>,
}

struct LoadedSource {
    label: String,
    path: String,
    bytes: Vec<u8>,
}

struct TemporaryWorkspace {
    path: PathBuf,
}

impl TemporaryWorkspace {
    fn create() -> Result<Self, FrontendContractError> {
        let parent = std::env::temp_dir();
        verify_real_directory(&parent, "Viewer README capture temporary parent")?;
        for _ in 0..1024 {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                "structural-viewer-readme-capture-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(FrontendContractError::new(
                        "viewer_readme_capture_temp_create_failed",
                        format!("create Viewer README capture workspace failed: {error}"),
                    ));
                }
            }
        }
        Err(FrontendContractError::new(
            "viewer_readme_capture_temp_create_failed",
            "could not allocate a unique Viewer README capture workspace",
        ))
    }

    fn output(&self) -> PathBuf {
        self.path.join("readme-viewer-capture.png")
    }
}

impl Drop for TemporaryWorkspace {
    fn drop(&mut self) {
        let _ignored = fs::remove_dir_all(&self.path);
    }
}

struct VerifiedPng {
    bytes: Vec<u8>,
    width: u32,
    height: u32,
    bit_depth: u8,
    color_type: u8,
    chunk_count: u64,
}

/// Plan or execute the README Viewer screenshot under Rust publication ownership.
///
/// The retained script still owns its loopback server, Playwright, Chromium, Viewer JavaScript,
/// camera application, browser requests, and screenshot generation. Rust freezes its inputs and
/// environment, owns the direct child, verifies a bounded CRC-valid 1600x900 PNG, detects input or
/// destination mutation, and publishes only verified bytes through the shared rollback contract.
///
/// # Errors
///
/// Rejects source-map or frontend drift, unsafe outputs, invalid camera inputs, child failure,
/// malformed PNG output, mutation during capture, staging failure, or publication failure.
pub fn run_viewer_readme_capture(
    options: &ViewerReadmeCaptureOptions,
) -> Result<ViewerReadmeCaptureReceiptV1, FrontendContractError> {
    let prepared = prepare_capture(options)?;
    if options.dry_run {
        return build_receipt(options, prepared, None, None);
    }

    let workspace = TemporaryWorkspace::create()?;
    let exit_code = run_capture_child(options, &prepared, &workspace.output())?;
    let png = verify_png_output(&workspace.output(), &prepared.source)?;
    verify_execution_inputs_unchanged(&prepared)?;
    publish_verified_outputs(
        vec![VerifiedOutput {
            target: prepared.output.clone(),
            bytes: &png.bytes,
            suffix: "png",
        }],
        PUBLICATION_CODES,
    )?;
    build_receipt(options, prepared, Some(&png), Some(exit_code))
}

/// Encode a README Viewer capture receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_readme_capture_receipt_json(
    receipt: &ViewerReadmeCaptureReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_readme_capture_receipt_encode_failed")
}

fn prepare_capture(
    options: &ViewerReadmeCaptureOptions,
) -> Result<PreparedCapture, FrontendContractError> {
    validate_options(options)?;
    verify_real_directory(&options.root, "Viewer README capture root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_readme_capture_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_readme_capture_root_invalid",
            format!("canonicalize Viewer README capture root failed: {error}"),
        )
    })?;
    let mut source_rows = Vec::with_capacity(source.tracked_sources.len());
    for row in &source.tracked_sources {
        let path = resolve_required_file(&root, &row.path)?;
        let bytes = read_bounded_regular_file(
            &path,
            MAX_SOURCE_BYTES,
            "Viewer README capture tracked source",
        )?;
        source_rows.push(LoadedSource {
            label: row.label.clone(),
            path: row.path.clone(),
            bytes,
        });
    }
    let output = prepare_verified_publication_target(
        &root,
        &options.output,
        source.maximum_png_bytes,
        "Viewer README capture output",
        PUBLICATION_CODES,
    )?;
    let logical_command_template = vec![
        source.node_launcher.clone(),
        source.capture_path.clone(),
        "--out".to_owned(),
        "{temporary_png_output}".to_owned(),
    ];
    let environment_overrides = vec![
        format!("README_CAPTURE_VIEW_PRESET={}", options.view_preset),
        format!("README_CAPTURE_CAMERA_X={}", options.camera_x),
        format!("README_CAPTURE_CAMERA_Y={}", options.camera_y),
        format!("README_CAPTURE_CAMERA_Z={}", options.camera_z),
    ];
    Ok(PreparedCapture {
        source,
        root,
        frontend_contract_receipt_hash,
        source_rows,
        output,
        logical_command_template,
        environment_overrides,
    })
}

fn validate_options(options: &ViewerReadmeCaptureOptions) -> Result<(), FrontendContractError> {
    if options.view_preset.is_empty()
        || options.view_preset.len() > MAX_PRESET_BYTES
        || !options
            .view_preset
            .bytes()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, b'_' | b'-'))
        || ![options.camera_x, options.camera_y, options.camera_z]
            .iter()
            .all(|value| value.is_finite() && (-10.0..=10.0).contains(value))
    {
        return Err(FrontendContractError::new(
            "viewer_readme_capture_options_invalid",
            "Viewer README preset or camera factors are invalid",
        ));
    }
    Ok(())
}

fn run_capture_child(
    options: &ViewerReadmeCaptureOptions,
    prepared: &PreparedCapture,
    output: &Path,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg(&prepared.source.capture_path)
        .arg("--out")
        .arg(output)
        .current_dir(&prepared.root)
        .env_remove("README_CAPTURE_VIEW_PRESET")
        .env_remove("README_CAPTURE_CAMERA_X")
        .env_remove("README_CAPTURE_CAMERA_Y")
        .env_remove("README_CAPTURE_CAMERA_Z")
        .env("README_CAPTURE_VIEW_PRESET", &options.view_preset)
        .env("README_CAPTURE_CAMERA_X", options.camera_x.to_string())
        .env("README_CAPTURE_CAMERA_Y", options.camera_y.to_string())
        .env("README_CAPTURE_CAMERA_Z", options.camera_z.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_readme_capture_launch_failed",
                format!("launch Viewer README capture failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_readme_capture_terminated",
            "Viewer README capture terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_readme_capture_failed",
            format!("Viewer README capture failed with exit code {exit_code}"),
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

fn verify_execution_inputs_unchanged(
    prepared: &PreparedCapture,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(capture_contract_changed());
    }
    for source in &prepared.source_rows {
        let path = resolve_required_file(&prepared.root, &source.path)?;
        let bytes = read_bounded_regular_file(
            &path,
            MAX_SOURCE_BYTES,
            "Viewer README capture tracked source",
        )?;
        if bytes != source.bytes {
            return Err(capture_contract_changed());
        }
    }
    Ok(())
}

fn capture_contract_changed() -> FrontendContractError {
    FrontendContractError::new(
        "viewer_readme_capture_contract_changed",
        "frontend package, lock, or README capture source changed while capture executed",
    )
}

fn verify_png_output(
    path: &Path,
    source: &ViewerReadmeCaptureSourceV1,
) -> Result<VerifiedPng, FrontendContractError> {
    let bytes = read_bounded_regular_file(path, source.maximum_png_bytes, "Viewer README PNG")
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_readme_capture_png_invalid",
                format!("read Viewer README PNG failed bounded validation: {error}"),
            )
        })?;
    let length = u64::try_from(bytes.len()).unwrap_or(u64::MAX);
    if length < source.minimum_png_bytes || !bytes.starts_with(PNG_SIGNATURE) {
        return Err(png_invalid("PNG is too small or has an invalid signature"));
    }

    let mut offset = PNG_SIGNATURE.len();
    let mut chunk_count = 0_usize;
    let mut ihdr = None;
    let mut idat_count = 0_usize;
    let mut saw_iend = false;
    while offset < bytes.len() {
        chunk_count = chunk_count
            .checked_add(1)
            .ok_or_else(|| png_invalid("PNG chunk count overflowed"))?;
        if chunk_count > MAX_PNG_CHUNKS || bytes.len().saturating_sub(offset) < 12 {
            return Err(png_invalid("PNG chunk inventory is truncated or excessive"));
        }
        let data_length = usize::try_from(read_u32_be(&bytes[offset..offset + 4]))
            .map_err(|_| png_invalid("PNG chunk length is not addressable"))?;
        let chunk_end = offset
            .checked_add(12)
            .and_then(|value| value.checked_add(data_length))
            .ok_or_else(|| png_invalid("PNG chunk length overflowed"))?;
        if chunk_end > bytes.len() {
            return Err(png_invalid("PNG chunk exceeds the bounded file"));
        }
        let chunk_type = &bytes[offset + 4..offset + 8];
        if !chunk_type.iter().all(u8::is_ascii_alphabetic) {
            return Err(png_invalid("PNG chunk type is invalid"));
        }
        let data_start = offset + 8;
        let data_end = data_start + data_length;
        let expected_crc = read_u32_be(&bytes[data_end..data_end + 4]);
        if png_crc32(&bytes[offset + 4..data_end]) != expected_crc {
            return Err(png_invalid("PNG chunk CRC is invalid"));
        }
        match chunk_type {
            b"IHDR" => {
                if chunk_count != 1 || data_length != 13 || ihdr.is_some() {
                    return Err(png_invalid("PNG IHDR position or length is invalid"));
                }
                let data = &bytes[data_start..data_end];
                let width = read_u32_be(&data[0..4]);
                let height = read_u32_be(&data[4..8]);
                let bit_depth = data[8];
                let color_type = data[9];
                if width != source.viewport_width
                    || height != source.viewport_height
                    || bit_depth != 8
                    || !source.allowed_png_color_types.contains(&color_type)
                    || data[10..13] != [0, 0, 0]
                {
                    return Err(png_invalid("PNG IHDR does not match the frozen capture"));
                }
                ihdr = Some((width, height, bit_depth, color_type));
            }
            b"IDAT" => {
                if ihdr.is_none() || saw_iend {
                    return Err(png_invalid("PNG IDAT ordering is invalid"));
                }
                idat_count += 1;
            }
            b"IEND" => {
                if data_length != 0 || saw_iend || chunk_end != bytes.len() {
                    return Err(png_invalid("PNG IEND is invalid or not final"));
                }
                saw_iend = true;
            }
            _ => {
                if saw_iend {
                    return Err(png_invalid("PNG contains a chunk after IEND"));
                }
            }
        }
        offset = chunk_end;
    }
    let (width, height, bit_depth, color_type) = ihdr
        .filter(|_| idat_count > 0 && saw_iend)
        .ok_or_else(|| png_invalid("PNG is missing IHDR, IDAT, or IEND"))?;
    Ok(VerifiedPng {
        bytes,
        width,
        height,
        bit_depth,
        color_type,
        chunk_count: u64::try_from(chunk_count)
            .map_err(|_| png_invalid("PNG chunk count is not addressable"))?,
    })
}

fn read_u32_be(bytes: &[u8]) -> u32 {
    u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]])
}

fn png_crc32(bytes: &[u8]) -> u32 {
    let mut crc = u32::MAX;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0_u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

fn png_invalid(detail: &str) -> FrontendContractError {
    FrontendContractError::new("viewer_readme_capture_png_invalid", detail.to_owned())
}

pub(crate) fn validate_viewer_readme_capture_source(
    source: &ViewerReadmeCaptureSourceV1,
) -> Result<(), FrontendContractError> {
    let expected_sources = [
        ("viewer_index", "src/structure-viewer/index.html"),
        ("readme_capture", EXPECTED_CAPTURE_PATH),
        (
            "canvas_frame_probe",
            "scripts/structure-viewer-canvas-frame.mjs",
        ),
    ];
    let actual_sources = source
        .tracked_sources
        .iter()
        .map(|row| (row.label.as_str(), row.path.as_str()))
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
        && source.capture_path == EXPECTED_CAPTURE_PATH
        && source.default_output_path == EXPECTED_DEFAULT_OUTPUT
        && source.viewer_path == EXPECTED_VIEWER_PATH
        && source.viewport_width == EXPECTED_VIEWPORT_WIDTH
        && source.viewport_height == EXPECTED_VIEWPORT_HEIGHT
        && source.default_view_preset == EXPECTED_VIEW_PRESET
        && source.default_camera_x.to_bits() == EXPECTED_CAMERA_X.to_bits()
        && source.default_camera_y.to_bits() == EXPECTED_CAMERA_Y.to_bits()
        && source.default_camera_z.to_bits() == EXPECTED_CAMERA_Z.to_bits()
        && source.minimum_png_bytes == EXPECTED_MINIMUM_PNG_BYTES
        && source.maximum_png_bytes == EXPECTED_MAXIMUM_PNG_BYTES
        && source.allowed_png_color_types == EXPECTED_COLOR_TYPES
        && actual_sources == expected_sources
        && unique_labels.len() == expected_sources.len()
        && unique_paths.len() == expected_sources.len()
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer README capture contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    options: &ViewerReadmeCaptureOptions,
    prepared: PreparedCapture,
    png: Option<&VerifiedPng>,
    exit_code: Option<i32>,
) -> Result<ViewerReadmeCaptureReceiptV1, FrontendContractError> {
    let executed = png.is_some();
    let source_identities = prepared
        .source_rows
        .iter()
        .map(|row| ViewerReadmeCaptureSourceIdentityV1 {
            label: row.label.clone(),
            path: row.path.clone(),
            sha256: sha256_identity(&row.bytes),
        })
        .collect();
    let mut receipt = ViewerReadmeCaptureReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_readme_capture".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "published" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        source_identities,
        viewer_path: prepared.source.viewer_path,
        viewport_width: prepared.source.viewport_width,
        viewport_height: prepared.source.viewport_height,
        view_preset: options.view_preset.clone(),
        camera_x: options.camera_x,
        camera_y: options.camera_y,
        camera_z: options.camera_z,
        requested_output: prepared.output.requested.clone(),
        published_output_path: if executed {
            Some(portable_publication_path(
                &prepared.output.path,
                "published Viewer README PNG",
                PUBLICATION_CODES,
            )?)
        } else {
            None
        },
        previous_output_state: prepared.output.snapshot.state.to_owned(),
        previous_output_byte_length: prepared.output.snapshot.byte_length,
        previous_output_sha256: prepared.output.snapshot.sha256,
        output_disposition: if executed {
            "verified_png_published"
        } else {
            "not_created"
        }
        .to_owned(),
        publication_strategy: VERIFIED_PUBLICATION_STRATEGY.to_owned(),
        logical_command_template: prepared.logical_command_template,
        environment_overrides: prepared.environment_overrides,
        png_byte_length: png
            .map(|value| u64::try_from(value.bytes.len()))
            .transpose()
            .map_err(|_| receipt_error("PNG byte length is not addressable"))?,
        png_sha256: png.map(|value| sha256_identity(&value.bytes)),
        png_width: png.map(|value| value.width),
        png_height: png.map(|value| value.height),
        png_bit_depth: png.map(|value| value.bit_depth),
        png_color_type: png.map(|value| value.color_type),
        png_chunk_count: png.map(|value| value.chunk_count),
        node_runtime_required: true,
        browser_runtime_required: true,
        rust_owned_listener_count: 0,
        direct_processes_spawned: u64::from(executed),
        successful_exit_codes: exit_code.into_iter().collect(),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new(
        "viewer_readme_capture_receipt_encode_failed",
        detail.to_owned(),
    )
}

fn hash_without_receipt_hash(
    receipt: &ViewerReadmeCaptureReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!(
            "project Viewer README capture receipt failed: {error}"
        ))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("Viewer README capture receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize Viewer README capture receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{png_crc32, verify_png_output, ViewerReadmeCaptureSourceV1};
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn chunk(kind: [u8; 4], data: &[u8]) -> Vec<u8> {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(&(u32::try_from(data.len()).expect("chunk length")).to_be_bytes());
        bytes.extend_from_slice(&kind);
        bytes.extend_from_slice(data);
        bytes.extend_from_slice(&png_crc32(&bytes[4..]).to_be_bytes());
        bytes
    }

    fn minimal_png() -> Vec<u8> {
        let mut bytes = super::PNG_SIGNATURE.to_vec();
        let mut ihdr = Vec::new();
        ihdr.extend_from_slice(&1600_u32.to_be_bytes());
        ihdr.extend_from_slice(&900_u32.to_be_bytes());
        ihdr.extend_from_slice(&[8, 2, 0, 0, 0]);
        bytes.extend_from_slice(&chunk(*b"IHDR", &ihdr));
        bytes.extend_from_slice(&chunk(*b"IDAT", b"bounded-test-data"));
        bytes.extend_from_slice(&chunk(*b"IEND", b""));
        bytes
    }

    fn source() -> ViewerReadmeCaptureSourceV1 {
        ViewerReadmeCaptureSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            node_launcher: "node".to_owned(),
            capture_path: super::EXPECTED_CAPTURE_PATH.to_owned(),
            default_output_path: super::EXPECTED_DEFAULT_OUTPUT.to_owned(),
            viewer_path: super::EXPECTED_VIEWER_PATH.to_owned(),
            viewport_width: 1600,
            viewport_height: 900,
            default_view_preset: "review".to_owned(),
            default_camera_x: -0.55,
            default_camera_y: 0.85,
            default_camera_z: 0.35,
            minimum_png_bytes: 1,
            maximum_png_bytes: 1024,
            allowed_png_color_types: vec![2, 6],
            tracked_sources: Vec::new(),
            external_network_access_accounting: "bounded".to_owned(),
            claim_boundary: "bounded".to_owned(),
        }
    }

    #[test]
    fn png_parser_checks_crc_dimensions_and_terminal_chunk() {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-viewer-readme-png-test-{}-{sequence}.png",
            std::process::id()
        ));
        let bytes = minimal_png();
        fs::write(&path, &bytes).expect("write PNG");
        let verified = verify_png_output(&path, &source()).expect("valid bounded PNG");
        assert_eq!((verified.width, verified.height), (1600, 900));
        let mut corrupted = bytes;
        let corrupt_index = corrupted.len() - 5;
        corrupted[corrupt_index] ^= 1;
        fs::write(&path, corrupted).expect("write corrupt PNG");
        assert!(verify_png_output(&path, &source()).is_err());
        fs::remove_file(path).expect("remove PNG");
    }
}
