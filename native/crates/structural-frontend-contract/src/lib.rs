//! Strict, deterministic verification for the transitional legacy frontend contract.

#![forbid(unsafe_code)]

mod browser_smoke;
mod frontend_build;
mod frontend_dev;
mod frontend_preview;
mod playwright;
mod playwright_install;
mod prototype;
mod prototype_browser_smoke;
mod smoke;
mod verified_publication;
mod viewer_js_syntax;
mod viewer_manifest;
mod viewer_performance_probe;
mod viewer_readme_capture;
mod viewer_report_pdf_export;
mod viewer_report_pdf_smoke;
mod viewer_sample_workflow;
mod viewer_server;
mod viewer_visual_regression;
mod workbench_v2_browser_smoke;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

pub use browser_smoke::{
    canonical_viewer_browser_smoke_receipt_json, run_viewer_browser_smoke,
    ViewerBrowserSmokeReceiptV1,
};
use browser_smoke::{validate_viewer_browser_smoke_source, ViewerBrowserSmokeSourceV1};
pub use frontend_build::{
    canonical_frontend_build_receipt_json, run_frontend_build, FrontendBuildCliIdentityV1,
    FrontendBuildOptions, FrontendBuildReceiptV1, FrontendBuildRuntimeRequirementsV1,
    FrontendBuildSourceIdentityV1,
};
use frontend_build::{validate_frontend_build_source, FrontendBuildSourceV1};
pub use frontend_dev::{
    canonical_frontend_dev_receipt_json, run_frontend_dev, FrontendDevCliIdentityV1,
    FrontendDevOptions, FrontendDevReceiptV1, FrontendDevRuntimeRequirementsV1,
};
use frontend_dev::{validate_frontend_dev_source, FrontendDevSourceV1};
pub use frontend_preview::{
    canonical_frontend_preview_receipt_json, plan_frontend_preview, serve_frontend_preview,
    FrontendPreviewReceiptV1, FrontendPreviewRuntimeRequirementsV1,
};
use frontend_preview::{validate_frontend_preview_source, FrontendPreviewSourceV1};
pub use playwright_install::{
    canonical_playwright_install_receipt_json, run_playwright_install,
    PlaywrightInstallCliIdentityV1, PlaywrightInstallOptions, PlaywrightInstallReceiptV1,
    PlaywrightInstallRuntimeRequirementsV1,
};
use playwright_install::{validate_playwright_install_source, PlaywrightInstallSourceV1};
pub use prototype::{
    canonical_workbench_prototype_receipt_json, check_workbench_prototype,
    WorkbenchPrototypeReceiptV1,
};
use prototype::{validate_workbench_prototype_source, WorkbenchPrototypeSourceV1};
pub use prototype_browser_smoke::{
    canonical_workbench_prototype_browser_smoke_receipt_json,
    run_workbench_prototype_browser_smoke, WorkbenchPrototypeBrowserSmokeReceiptV1,
};
use prototype_browser_smoke::{
    validate_workbench_prototype_browser_smoke_source, WorkbenchPrototypeBrowserSmokeSourceV1,
};
pub use smoke::{canonical_smoke_receipt_json, run_frontend_smoke, FrontendSmokeReceiptV1};
use smoke::{validate_frontend_smoke_source, FrontendSmokeSourceV1};
pub use viewer_js_syntax::{
    canonical_viewer_js_syntax_receipt_json, run_viewer_js_syntax, ViewerJsSyntaxOptions,
    ViewerJsSyntaxReceiptV1, ViewerJsSyntaxSourceIdentityV1,
};
use viewer_js_syntax::{validate_viewer_js_syntax_source, ViewerJsSyntaxSourceV1};
pub use viewer_manifest::{
    canonical_viewer_manifest_receipt_json, check_viewer_manifest, ViewerArtifactCountCheckV1,
    ViewerManifestMinimumsV1, ViewerManifestReceiptV1, ViewerManifestSummaryV1,
};
use viewer_manifest::{validate_viewer_manifest_source, ViewerManifestSourceV1};
pub use viewer_performance_probe::{
    canonical_viewer_performance_probe_receipt_json, run_viewer_performance_probe,
    ViewerPerformanceProbeOptions, ViewerPerformanceProbeReceiptV1,
    ViewerPerformanceSourceIdentityV1,
};
use viewer_performance_probe::{
    validate_viewer_performance_probe_source, ViewerPerformanceProbeSourceV1,
};
pub use viewer_readme_capture::{
    canonical_viewer_readme_capture_receipt_json, run_viewer_readme_capture,
    ViewerReadmeCaptureOptions, ViewerReadmeCaptureReceiptV1, ViewerReadmeCaptureSourceIdentityV1,
};
use viewer_readme_capture::{validate_viewer_readme_capture_source, ViewerReadmeCaptureSourceV1};
pub use viewer_report_pdf_export::{
    canonical_viewer_report_pdf_export_receipt_json, run_viewer_report_pdf_export,
    ViewerReportPdfExportOptions, ViewerReportPdfExportReceiptV1,
};
pub use viewer_report_pdf_smoke::{
    canonical_viewer_report_pdf_smoke_receipt_json, run_viewer_report_pdf_smoke,
    ViewerReportPdfSmokeOptions, ViewerReportPdfSmokeReceiptV1,
};
use viewer_report_pdf_smoke::{
    validate_viewer_report_pdf_smoke_source, ViewerReportPdfSmokeSourceV1,
};
pub use viewer_sample_workflow::{
    canonical_viewer_sample_workflow_receipt_json, run_viewer_sample_workflow,
    ViewerSampleWorkflowOptions, ViewerSampleWorkflowReceiptV1,
    ViewerSampleWorkflowRuntimeRequirementsV1, ViewerSampleWorkflowSourceIdentityV1,
};
use viewer_sample_workflow::{
    validate_viewer_sample_workflow_source, ViewerSampleWorkflowSourceV1,
};
pub use viewer_server::{
    canonical_viewer_server_receipt_json, plan_viewer_server, serve_viewer, ViewerServerReceiptV1,
};
use viewer_server::{validate_viewer_server_source, ViewerServerSourceV1};
pub use viewer_visual_regression::{
    canonical_viewer_visual_regression_receipt_json, run_viewer_visual_regression,
    ViewerVisualRegressionOptions, ViewerVisualRegressionReceiptV1,
};
use viewer_visual_regression::{
    validate_viewer_visual_regression_source, ViewerVisualRegressionSourceV1,
};
pub use workbench_v2_browser_smoke::{
    canonical_workbench_v2_browser_smoke_receipt_json, run_workbench_v2_browser_smoke,
    WorkbenchV2BrowserSmokeReceiptV1, WorkbenchV2BrowserSmokeSpecificationV1,
};
use workbench_v2_browser_smoke::{
    validate_workbench_v2_browser_smoke_source, WorkbenchV2BrowserSmokeSourceV1,
};

const SOURCE_MAP_SCHEMA_V1: &str = "structural-legacy-frontend-build-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-contract-receipt.v1";
const DELIVERY_RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-delivery-receipt.v1";
const MAX_SOURCE_MAP_BYTES: usize = 1024 * 1024;
const MAX_JSON_BYTES: u64 = 8 * 1024 * 1024;
const MAX_DELIVERY_TEXT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_DELIVERY_TOTAL_ASSET_BYTES: u64 = 256 * 1024 * 1024;
const MAX_DELIVERY_ASSETS: usize = 512;
const MAX_REQUIRED_FILES: usize = 256;
const MAX_PATH_BYTES: usize = 512;
const SOURCE_MAP_BYTES: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../decommission/legacy-frontend-build-contract-v1.json"
));

#[cfg(test)]
const TEST_SOURCE_MAP: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../decommission/legacy-frontend-build-contract-v1.json"
);

/// Stable frontend-contract failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendContractError {
    pub code: &'static str,
    pub detail: String,
}

impl FrontendContractError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for FrontendContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for FrontendContractError {}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct FrontendSourceMapV1 {
    schema_version: String,
    expected_package_name: String,
    expected_package_manager: String,
    minimum_lockfile_version: u64,
    forbidden_description_substrings: Vec<String>,
    required_files: Vec<String>,
    forbidden_paths: Vec<String>,
    expected_scripts: BTreeMap<String, String>,
    expected_dependencies: BTreeMap<String, String>,
    expected_dev_dependencies: BTreeMap<String, String>,
    frontend_build_contract: FrontendBuildSourceV1,
    frontend_dev_contract: FrontendDevSourceV1,
    frontend_preview_contract: FrontendPreviewSourceV1,
    playwright_install_contract: PlaywrightInstallSourceV1,
    delivery_contract: FrontendDeliverySourceV1,
    smoke_contract: FrontendSmokeSourceV1,
    viewer_manifest_contract: ViewerManifestSourceV1,
    viewer_browser_smoke_contract: ViewerBrowserSmokeSourceV1,
    viewer_js_syntax_contract: ViewerJsSyntaxSourceV1,
    viewer_performance_probe_contract: ViewerPerformanceProbeSourceV1,
    viewer_readme_capture_contract: ViewerReadmeCaptureSourceV1,
    viewer_report_pdf_smoke_contract: ViewerReportPdfSmokeSourceV1,
    viewer_sample_workflow_contract: ViewerSampleWorkflowSourceV1,
    viewer_server_contract: ViewerServerSourceV1,
    viewer_visual_regression_contract: ViewerVisualRegressionSourceV1,
    workbench_prototype_contract: WorkbenchPrototypeSourceV1,
    workbench_prototype_browser_smoke_contract: WorkbenchPrototypeBrowserSmokeSourceV1,
    workbench_v2_browser_smoke_contract: WorkbenchV2BrowserSmokeSourceV1,
    claim_boundary: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct FrontendDeliverySourceV1 {
    contract: String,
    dist_directory: String,
    workbench_entry: String,
    viewer_entry: String,
    workbench_required_marker: String,
    workbench_forbidden_marker: String,
    viewer_required_markers: Vec<String>,
    viewer_forbidden_marker: String,
    workbench_viewer_target: String,
    legacy_sentinels: Vec<String>,
    claim_boundary: String,
}

#[derive(Debug)]
struct ValidatedPackage {
    name: String,
    version: String,
    manager: String,
    lockfile_version: u64,
}

#[derive(Debug)]
struct DeliveryText {
    path: String,
    bytes: Vec<u8>,
    text: String,
}

#[derive(Debug)]
struct LoadedDeliveryAsset {
    receipt: DeliveryAssetReceiptV1,
    bytes: Vec<u8>,
}

/// Canonical, self-hashed result of one read-only contract check.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendContractReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub source_map_schema_version: String,
    pub source_map_sha256: String,
    pub package_name: String,
    pub package_version: String,
    pub package_manager: String,
    pub lockfile_version: u64,
    pub required_file_count: usize,
    pub required_file_inventory_sha256: String,
    pub package_json_sha256: String,
    pub package_lock_sha256: String,
    pub deterministic: bool,
    pub commands_executed: u64,
    pub network_access_count: u64,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct DeliveryAssetReceiptV1 {
    entry: String,
    reference: String,
    path: String,
    byte_length: u64,
    sha256: String,
}

/// Canonical, self-hashed verification of one completed Vite delivery tree.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendDeliveryReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub contract: String,
    pub status: String,
    pub source_map_sha256: String,
    pub workbench_entry: String,
    pub viewer_entry: String,
    pub legacy_chunk: String,
    pub workbench_asset_count: usize,
    pub viewer_asset_count: usize,
    pub legacy_marker_count: usize,
    pub workbench_entry_sha256: String,
    pub viewer_entry_sha256: String,
    pub legacy_chunk_sha256: String,
    pub asset_inventory_sha256: String,
    pub deterministic: bool,
    pub commands_executed: u64,
    pub network_access_count: u64,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Check the pinned legacy frontend package, lock metadata, and required source inventory.
///
/// # Errors
///
/// Rejects unsafe paths, symlinks, missing files, duplicate-key JSON, package or lock drift,
/// dependency drift, and malformed embedded contract metadata.
pub fn check_frontend_contract(
    root: &Path,
) -> Result<FrontendContractReceiptV1, FrontendContractError> {
    verify_real_directory(root, "frontend contract root")?;
    let source_map = parse_source_map()?;
    for path in &source_map.required_files {
        resolve_required_file(root, path)?;
    }
    for path in &source_map.forbidden_paths {
        if forbidden_path_present(root, path)? {
            return Err(FrontendContractError::new(
                "frontend_forbidden_path_present",
                format!("forbidden legacy frontend path is present: {path}"),
            ));
        }
    }

    let package_path = resolve_required_file(root, "package.json")?;
    let lock_path = resolve_required_file(root, "package-lock.json")?;
    let package_bytes = read_bounded_regular_file(&package_path, MAX_JSON_BYTES, "package.json")?;
    let lock_bytes = read_bounded_regular_file(&lock_path, MAX_JSON_BYTES, "package-lock.json")?;
    let package_object = decode_object(
        &package_bytes,
        "frontend_package_json_invalid",
        "package.json",
    )?;
    let lock_object = decode_object(
        &lock_bytes,
        "frontend_lock_json_invalid",
        "package-lock.json",
    )?;
    let validated = validate_package_and_lock(&package_object, &lock_object, &source_map)?;

    let inventory_json =
        canonical_struct(&source_map.required_files, "frontend_receipt_encode_failed")?;
    let mut receipt = FrontendContractReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "check".to_owned(),
        source_map_schema_version: source_map.schema_version,
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        package_name: validated.name,
        package_version: validated.version,
        package_manager: validated.manager,
        lockfile_version: validated.lockfile_version,
        required_file_count: source_map.required_files.len(),
        required_file_inventory_sha256: sha256_identity(inventory_json.as_bytes()),
        package_json_sha256: sha256_identity(&package_bytes),
        package_lock_sha256: sha256_identity(&lock_bytes),
        deterministic: true,
        commands_executed: 0,
        network_access_count: 0,
        claim_boundary: source_map.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a frontend-contract receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_receipt_json(
    receipt: &FrontendContractReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_receipt_encode_failed")
}

/// Verify the already-built Workbench/Viewer delivery tree without executing it.
///
/// # Errors
///
/// Rejects missing, empty, oversized, non-UTF-8, or symlinked entries; unsafe or missing emitted
/// assets; entry-marker drift; eager legacy markers; and zero or multiple lazy legacy chunks.
pub fn check_frontend_delivery(
    root: &Path,
) -> Result<FrontendDeliveryReceiptV1, FrontendContractError> {
    verify_real_directory(root, "frontend delivery root")?;
    let source_map = parse_source_map()?;
    let contract = &source_map.delivery_contract;
    let dist = resolve_required_directory(root, &contract.dist_directory)?;
    let workbench = read_delivery_text(root, &dist, &contract.workbench_entry, "Workbench entry")?;
    let viewer = read_delivery_text(root, &dist, &contract.viewer_entry, "Viewer entry")?;
    validate_delivery_entry_markers(&workbench.text, &viewer.text, contract)?;

    let workbench_assets = load_delivery_assets(root, &dist, &workbench.text, "workbench")?;
    let viewer_assets = load_delivery_assets(root, &dist, &viewer.text, "viewer")?;
    let workbench_scripts = workbench_assets
        .iter()
        .filter(|asset| has_js_extension(clean_reference(&asset.receipt.reference)))
        .map(|asset| delivery_asset_text(asset, "Workbench JavaScript asset"))
        .collect::<Result<Vec<_>, _>>()?;
    if !workbench_scripts
        .iter()
        .any(|source| source.contains(&contract.workbench_viewer_target))
    {
        return Err(delivery_drift(
            "Workbench JavaScript does not target the emitted Viewer entry",
        ));
    }
    for sentinel in &contract.legacy_sentinels {
        if workbench_scripts
            .iter()
            .any(|source| source.contains(sentinel))
        {
            return Err(delivery_drift(&format!(
                "legacy App code leaked into the eager Workbench graph: {sentinel}"
            )));
        }
    }

    let legacy_chunks = find_legacy_chunk_names(&workbench_scripts)?;
    if legacy_chunks.len() != 1 {
        return Err(delivery_drift(&format!(
            "Workbench must reference exactly one lazy legacy App chunk; found {}",
            legacy_chunks.len()
        )));
    }
    let legacy_name = legacy_chunks
        .iter()
        .next()
        .ok_or_else(|| delivery_drift("legacy chunk selection failed"))?;
    let legacy_relative = format!("assets/{legacy_name}");
    let legacy = read_delivery_text(root, &dist, &legacy_relative, "Legacy App JavaScript asset")?;
    for sentinel in &contract.legacy_sentinels {
        if !legacy.text.contains(sentinel) {
            return Err(delivery_drift(&format!(
                "lazy legacy App chunk is missing its ownership marker: {sentinel}"
            )));
        }
    }

    let asset_inventory = workbench_assets
        .iter()
        .chain(&viewer_assets)
        .map(|asset| asset.receipt.clone())
        .collect::<Vec<_>>();
    let inventory_json =
        canonical_struct(&asset_inventory, "frontend_delivery_receipt_encode_failed")?;
    let mut receipt = FrontendDeliveryReceiptV1 {
        schema_version: DELIVERY_RECEIPT_SCHEMA_V1.to_owned(),
        action: "delivery_check".to_owned(),
        contract: contract.contract.clone(),
        status: "ready".to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        workbench_entry: workbench.path,
        viewer_entry: viewer.path,
        legacy_chunk: legacy.path,
        workbench_asset_count: workbench_assets.len(),
        viewer_asset_count: viewer_assets.len(),
        legacy_marker_count: contract.legacy_sentinels.len(),
        workbench_entry_sha256: sha256_identity(&workbench.bytes),
        viewer_entry_sha256: sha256_identity(&viewer.bytes),
        legacy_chunk_sha256: sha256_identity(&legacy.bytes),
        asset_inventory_sha256: sha256_identity(inventory_json.as_bytes()),
        deterministic: true,
        commands_executed: 0,
        network_access_count: 0,
        claim_boundary: contract.claim_boundary.clone(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_delivery_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a frontend-delivery receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_delivery_receipt_json(
    receipt: &FrontendDeliveryReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_delivery_receipt_encode_failed")
}

fn parse_source_map() -> Result<FrontendSourceMapV1, FrontendContractError> {
    if SOURCE_MAP_BYTES.len() > MAX_SOURCE_MAP_BYTES {
        return Err(FrontendContractError::new(
            "frontend_source_map_too_large",
            "embedded frontend source map exceeds its size bound",
        ));
    }
    let value = decode_json_strict(SOURCE_MAP_BYTES).map_err(|error| {
        FrontendContractError::new(
            "frontend_source_map_json_invalid",
            format!("embedded frontend source map is invalid: {error}"),
        )
    })?;
    let source_map: FrontendSourceMapV1 = serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            format!("embedded frontend source map fields are invalid: {error}"),
        )
    })?;
    validate_source_map(&source_map)?;
    Ok(source_map)
}

fn validate_source_map(source_map: &FrontendSourceMapV1) -> Result<(), FrontendContractError> {
    if source_map.schema_version != SOURCE_MAP_SCHEMA_V1
        || source_map.expected_package_name.is_empty()
        || source_map.expected_package_manager.is_empty()
        || source_map.minimum_lockfile_version == 0
        || source_map.required_files.is_empty()
        || source_map.required_files.len() > MAX_REQUIRED_FILES
        || source_map.expected_scripts.is_empty()
        || source_map.expected_dependencies.is_empty()
        || source_map.expected_dev_dependencies.is_empty()
        || source_map.claim_boundary.trim().is_empty()
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "embedded frontend source map has an invalid schema or empty required field",
        ));
    }
    let mut paths = BTreeSet::new();
    for path in source_map
        .required_files
        .iter()
        .chain(source_map.forbidden_paths.iter())
    {
        validate_relative_path(path)?;
        if !paths.insert(path.as_str()) {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                format!("frontend source-map path is duplicated: {path}"),
            ));
        }
    }
    if !source_map
        .required_files
        .iter()
        .any(|path| path == "package.json")
        || !source_map
            .required_files
            .iter()
            .any(|path| path == "package-lock.json")
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend source map must require package.json and package-lock.json",
        ));
    }
    for substring in &source_map.forbidden_description_substrings {
        if substring.is_empty()
            || substring != &substring.to_lowercase()
            || substring.chars().any(char::is_control)
        {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                "forbidden description substrings must be lowercase bounded text",
            ));
        }
    }
    for (name, value) in source_map
        .expected_scripts
        .iter()
        .chain(source_map.expected_dependencies.iter())
        .chain(source_map.expected_dev_dependencies.iter())
    {
        if name.is_empty()
            || value.is_empty()
            || name.len() > 256
            || value.len() > 16 * 1024
            || name.chars().any(char::is_control)
            || value.chars().any(char::is_control)
        {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                "frontend source-map key/value is invalid",
            ));
        }
    }
    validate_frontend_build_source(&source_map.frontend_build_contract)?;
    validate_frontend_dev_source(&source_map.frontend_dev_contract)?;
    validate_frontend_preview_source(&source_map.frontend_preview_contract)?;
    validate_playwright_install_source(&source_map.playwright_install_contract)?;
    validate_delivery_source(&source_map.delivery_contract)?;
    validate_frontend_smoke_source(&source_map.smoke_contract)?;
    validate_viewer_manifest_source(&source_map.viewer_manifest_contract)?;
    validate_viewer_browser_smoke_source(&source_map.viewer_browser_smoke_contract)?;
    validate_viewer_js_syntax_source(&source_map.viewer_js_syntax_contract)?;
    validate_viewer_performance_probe_source(&source_map.viewer_performance_probe_contract)?;
    validate_viewer_readme_capture_source(&source_map.viewer_readme_capture_contract)?;
    validate_viewer_report_pdf_smoke_source(&source_map.viewer_report_pdf_smoke_contract)?;
    validate_viewer_sample_workflow_source(&source_map.viewer_sample_workflow_contract)?;
    validate_viewer_server_source(&source_map.viewer_server_contract)?;
    validate_viewer_visual_regression_source(&source_map.viewer_visual_regression_contract)?;
    validate_workbench_prototype_source(&source_map.workbench_prototype_contract)?;
    validate_workbench_prototype_browser_smoke_source(
        &source_map.workbench_prototype_browser_smoke_contract,
    )?;
    validate_workbench_v2_browser_smoke_source(&source_map.workbench_v2_browser_smoke_contract)?;
    Ok(())
}

fn validate_delivery_source(
    delivery: &FrontendDeliverySourceV1,
) -> Result<(), FrontendContractError> {
    if delivery.contract != "workbench_viewer_production_delivery_v1"
        || delivery.viewer_required_markers.is_empty()
        || delivery.viewer_required_markers.len() > 16
        || delivery.legacy_sentinels.is_empty()
        || delivery.legacy_sentinels.len() > 16
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend delivery contract identity or marker count is invalid",
        ));
    }
    for path in [
        &delivery.dist_directory,
        &delivery.workbench_entry,
        &delivery.viewer_entry,
    ] {
        validate_relative_path(path)?;
    }
    let strings = [
        delivery.contract.as_str(),
        delivery.workbench_required_marker.as_str(),
        delivery.workbench_forbidden_marker.as_str(),
        delivery.viewer_forbidden_marker.as_str(),
        delivery.workbench_viewer_target.as_str(),
        delivery.claim_boundary.as_str(),
    ];
    if strings
        .into_iter()
        .chain(
            delivery
                .viewer_required_markers
                .iter()
                .chain(&delivery.legacy_sentinels)
                .map(String::as_str),
        )
        .any(|value| {
            value.is_empty() || value.len() > 16 * 1024 || value.chars().any(char::is_control)
        })
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend delivery marker text is invalid",
        ));
    }
    let unique_sentinels = delivery.legacy_sentinels.iter().collect::<BTreeSet<_>>();
    if unique_sentinels.len() != delivery.legacy_sentinels.len() {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend delivery legacy sentinels must be unique",
        ));
    }
    Ok(())
}

fn validate_package_and_lock(
    package: &Map<String, Value>,
    lock: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<ValidatedPackage, FrontendContractError> {
    let name = required_string(package, "name", "package.json")?;
    let version = required_string(package, "version", "package.json")?;
    let manager = required_string(package, "packageManager", "package.json")?;
    if name != source_map.expected_package_name {
        return Err(contract_drift("package name"));
    }
    if manager != source_map.expected_package_manager {
        return Err(contract_drift("package manager"));
    }
    if version.len() > 128 {
        return Err(contract_drift("package version"));
    }
    validate_package_description(package, source_map)?;
    validate_package_maps(package, source_map)?;

    let lock_name = required_string(lock, "name", "package-lock.json")?;
    let lock_version = required_string(lock, "version", "package-lock.json")?;
    let lockfile_version = required_u64(lock, "lockfileVersion", "package-lock.json")?;
    if lock_name != name
        || lock_version != version
        || lockfile_version < source_map.minimum_lockfile_version
    {
        return Err(contract_drift("lockfile root identity"));
    }
    let packages = required_object(lock, "packages", "package-lock.json")?;
    let root_package = packages
        .get("")
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift("lockfile packages[''] object"))?;
    if required_string(root_package, "name", "lockfile root package")? != name
        || required_string(root_package, "version", "lockfile root package")? != version
    {
        return Err(contract_drift("lockfile root package metadata"));
    }
    require_exact_map(
        root_package.get("dependencies"),
        &source_map.expected_dependencies,
        "lockfile root dependencies",
    )?;
    require_exact_map(
        root_package.get("devDependencies"),
        &source_map.expected_dev_dependencies,
        "lockfile root devDependencies",
    )?;
    Ok(ValidatedPackage {
        name,
        version,
        manager,
        lockfile_version,
    })
}

fn validate_package_description(
    package: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<(), FrontendContractError> {
    let description = optional_string(package, "description", "package.json")?.unwrap_or_default();
    let description_lower = description.to_lowercase();
    if source_map
        .forbidden_description_substrings
        .iter()
        .any(|substring| description_lower.contains(substring))
    {
        return Err(contract_drift("package description"));
    }
    Ok(())
}

fn validate_package_maps(
    package: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<(), FrontendContractError> {
    let scripts = object_of_strings(package.get("scripts"), "package.json scripts")?;
    for (name, expected) in &source_map.expected_scripts {
        if scripts.get(name) != Some(expected) {
            return Err(FrontendContractError::new(
                "frontend_script_drift",
                format!("package script differs from the pinned contract: {name}"),
            ));
        }
    }
    require_exact_map(
        package.get("dependencies"),
        &source_map.expected_dependencies,
        "package dependencies",
    )?;
    require_exact_map(
        package.get("devDependencies"),
        &source_map.expected_dev_dependencies,
        "package devDependencies",
    )
}

fn validate_delivery_entry_markers(
    workbench: &str,
    viewer: &str,
    contract: &FrontendDeliverySourceV1,
) -> Result<(), FrontendContractError> {
    if !workbench.contains(&contract.workbench_required_marker) {
        return Err(delivery_drift(
            "Workbench entry does not contain the React product-shell root",
        ));
    }
    if workbench.contains(&contract.workbench_forbidden_marker) {
        return Err(delivery_drift(
            "Workbench entry was replaced by the Viewer entry",
        ));
    }
    for marker in &contract.viewer_required_markers {
        if !viewer.contains(marker) {
            return Err(delivery_drift(&format!(
                "Viewer entry is missing required marker: {marker}"
            )));
        }
    }
    if viewer.contains(&contract.viewer_forbidden_marker) {
        return Err(delivery_drift(
            "Viewer entry resolved to the Workbench SPA fallback",
        ));
    }
    Ok(())
}

fn read_delivery_text(
    root: &Path,
    dist: &Path,
    relative: &str,
    label: &str,
) -> Result<DeliveryText, FrontendContractError> {
    let path = resolve_required_file(dist, relative)?;
    let bytes = read_bounded_regular_file(&path, MAX_DELIVERY_TEXT_BYTES, label)?;
    if bytes.is_empty() {
        return Err(delivery_drift(&format!("{label} is empty")));
    }
    let text = String::from_utf8(bytes.clone())
        .map_err(|_| delivery_drift(&format!("{label} must be valid UTF-8 text")))?;
    if text.trim().is_empty() {
        return Err(delivery_drift(&format!("{label} is empty")));
    }
    Ok(DeliveryText {
        path: relative_portable_path(root, &path)?,
        bytes,
        text,
    })
}

fn load_delivery_assets(
    root: &Path,
    dist: &Path,
    html: &str,
    entry: &str,
) -> Result<Vec<LoadedDeliveryAsset>, FrontendContractError> {
    let references = emitted_asset_references(html)?;
    if references.is_empty() {
        return Err(delivery_drift(&format!(
            "{entry} entry has no emitted asset references"
        )));
    }
    if references.len() > MAX_DELIVERY_ASSETS {
        return Err(delivery_drift(&format!(
            "{entry} entry exceeds the emitted asset-count bound"
        )));
    }
    let mut loaded = Vec::with_capacity(references.len());
    let mut total_bytes = 0_u64;
    for (reference, relative) in references {
        let path = resolve_required_file(dist, &relative).map_err(|error| {
            delivery_drift(&format!(
                "{entry} entry references a missing or unsafe emitted asset {reference}: {error}"
            ))
        })?;
        let remaining = MAX_DELIVERY_TOTAL_ASSET_BYTES.saturating_sub(total_bytes);
        if remaining == 0 {
            return Err(delivery_drift(&format!(
                "{entry} entry exceeds the emitted asset-byte bound"
            )));
        }
        let bytes = read_bounded_regular_file(
            &path,
            MAX_DELIVERY_TEXT_BYTES.min(remaining),
            "frontend emitted asset",
        )
        .map_err(|error| {
            delivery_drift(&format!(
                "{entry} entry references an invalid emitted asset {reference}: {error}"
            ))
        })?;
        let byte_length = u64::try_from(bytes.len())
            .map_err(|_| delivery_drift("frontend emitted asset length is not addressable"))?;
        total_bytes = total_bytes
            .checked_add(byte_length)
            .ok_or_else(|| delivery_drift("frontend emitted asset-byte count overflowed"))?;
        loaded.push(LoadedDeliveryAsset {
            receipt: DeliveryAssetReceiptV1 {
                entry: entry.to_owned(),
                reference,
                path: relative_portable_path(root, &path)?,
                byte_length,
                sha256: sha256_identity(&bytes),
            },
            bytes,
        });
    }
    Ok(loaded)
}

fn emitted_asset_references(html: &str) -> Result<Vec<(String, String)>, FrontendContractError> {
    let mut references = Vec::new();
    let mut cursor = 0_usize;
    while cursor < html.len() {
        let src = html[cursor..].find("src=\"").map(|index| index + cursor);
        let href = html[cursor..].find("href=\"").map(|index| index + cursor);
        let Some(start) = (match (src, href) {
            (Some(left), Some(right)) => Some(left.min(right)),
            (Some(value), None) | (None, Some(value)) => Some(value),
            (None, None) => None,
        }) else {
            break;
        };
        let value_start = start
            + if html[start..].starts_with("src=\"") {
                "src=\"".len()
            } else {
                "href=\"".len()
            };
        let Some(end_offset) = html[value_start..].find('"') else {
            break;
        };
        let end = value_start + end_offset;
        let reference = &html[value_start..end];
        if let Some(relative) = emitted_asset_relative(reference)? {
            references.push((reference.to_owned(), relative));
        }
        cursor = end.saturating_add(1);
    }
    Ok(references)
}

fn emitted_asset_relative(reference: &str) -> Result<Option<String>, FrontendContractError> {
    if reference.len() > MAX_PATH_BYTES || reference.chars().any(char::is_control) {
        return Err(delivery_drift("frontend asset reference is invalid"));
    }
    let clean = clean_reference(reference);
    let candidate = if clean.starts_with("assets/") {
        Some(clean)
    } else {
        clean.find("/assets/").map(|index| &clean[index + 1..])
    };
    let Some(candidate) = candidate else {
        return Ok(None);
    };
    if candidate.contains('\'') {
        return Ok(None);
    }
    validate_relative_path(candidate).map_err(|_| {
        delivery_drift(&format!(
            "frontend emitted asset path is unsafe: {reference}"
        ))
    })?;
    if !candidate.starts_with("assets/") {
        return Ok(None);
    }
    Ok(Some(candidate.to_owned()))
}

fn clean_reference(reference: &str) -> &str {
    let query = reference.find('?');
    let fragment = reference.find('#');
    match (query, fragment) {
        (Some(left), Some(right)) => &reference[..left.min(right)],
        (Some(index), None) | (None, Some(index)) => &reference[..index],
        (None, None) => reference,
    }
}

fn delivery_asset_text(
    asset: &LoadedDeliveryAsset,
    label: &str,
) -> Result<String, FrontendContractError> {
    if asset.bytes.is_empty() {
        return Err(delivery_drift(&format!("{label} is empty")));
    }
    let text = String::from_utf8(asset.bytes.clone())
        .map_err(|_| delivery_drift(&format!("{label} must be valid UTF-8 text")))?;
    if text.trim().is_empty() {
        return Err(delivery_drift(&format!("{label} is empty")));
    }
    Ok(text)
}

fn find_legacy_chunk_names(scripts: &[String]) -> Result<BTreeSet<String>, FrontendContractError> {
    let mut names = BTreeSet::new();
    for source in scripts {
        for prefix in ["assets/App-", "./App-"] {
            let mut cursor = 0_usize;
            while let Some(offset) = source[cursor..].find(prefix) {
                let marker_start = cursor + offset;
                let name_start = marker_start + prefix.len() - "App-".len();
                let Some(suffix) = source[name_start..].find(".js") else {
                    break;
                };
                let name_end = name_start + suffix + ".js".len();
                let name = &source[name_start..name_end];
                if valid_legacy_chunk_name(name) {
                    names.insert(name.to_owned());
                }
                cursor = name_end;
            }
        }
    }
    if names.len() > 32 {
        return Err(delivery_drift(
            "frontend lazy legacy chunk inventory exceeds its bound",
        ));
    }
    Ok(names)
}

fn valid_legacy_chunk_name(value: &str) -> bool {
    value.starts_with("App-")
        && has_js_extension(value)
        && value.len() <= MAX_PATH_BYTES
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

fn has_js_extension(value: &str) -> bool {
    Path::new(value)
        .extension()
        .is_some_and(|extension| extension == "js")
}

fn delivery_drift(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_delivery_contract_drift", detail)
}

fn decode_object(
    bytes: &[u8],
    code: &'static str,
    label: &str,
) -> Result<Map<String, Value>, FrontendContractError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        FrontendContractError::new(code, format!("{label} is invalid strict JSON: {error}"))
    })?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| FrontendContractError::new(code, format!("{label} must be a JSON object")))
}

fn required_object<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<&'a Map<String, Value>, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn required_string(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<String, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty() && value.len() <= 16 * 1024)
        .map(ToOwned::to_owned)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn optional_string(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<Option<String>, FrontendContractError> {
    match object.get(field) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) if value.len() <= 16 * 1024 => Ok(Some(value.clone())),
        Some(_) => Err(contract_drift(&format!("{label} field {field}"))),
    }
}

fn required_u64(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<u64, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn object_of_strings(
    value: Option<&Value>,
    label: &str,
) -> Result<BTreeMap<String, String>, FrontendContractError> {
    let object = value
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift(label))?;
    object
        .iter()
        .map(|(name, value)| {
            value
                .as_str()
                .map(|value| (name.clone(), value.to_owned()))
                .ok_or_else(|| contract_drift(label))
        })
        .collect()
}

fn require_exact_map(
    value: Option<&Value>,
    expected: &BTreeMap<String, String>,
    label: &str,
) -> Result<(), FrontendContractError> {
    let actual = object_of_strings(value, label)?;
    if &actual != expected
        || actual
            .values()
            .any(|version| version.starts_with('^') || version.starts_with('~'))
    {
        return Err(contract_drift(label));
    }
    Ok(())
}

fn contract_drift(label: &str) -> FrontendContractError {
    FrontendContractError::new(
        "frontend_contract_drift",
        format!("legacy frontend contract drifted at {label}"),
    )
}

fn validate_relative_path(relative: &str) -> Result<(), FrontendContractError> {
    if relative.is_empty()
        || relative.len() > MAX_PATH_BYTES
        || relative.contains('\\')
        || relative.chars().any(char::is_control)
        || Path::new(relative).is_absolute()
        || !Path::new(relative)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_path_invalid",
            format!("frontend contract path is unsafe: {relative}"),
        ));
    }
    Ok(())
}

pub(crate) fn resolve_required_directory(
    root: &Path,
    relative: &str,
) -> Result<PathBuf, FrontendContractError> {
    validate_relative_path(relative)?;
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        let Component::Normal(name) = component else {
            return Err(FrontendContractError::new(
                "frontend_source_map_path_invalid",
                format!("frontend contract path is unsafe: {relative}"),
            ));
        };
        path.push(name);
        verify_real_directory(&path, "frontend delivery directory")?;
    }
    Ok(path)
}

fn relative_portable_path(root: &Path, path: &Path) -> Result<String, FrontendContractError> {
    let relative = path.strip_prefix(root).map_err(|_| {
        FrontendContractError::new(
            "frontend_unsafe_path",
            "frontend delivery path escaped the declared root",
        )
    })?;
    let mut segments = Vec::new();
    for component in relative.components() {
        let Component::Normal(segment) = component else {
            return Err(FrontendContractError::new(
                "frontend_unsafe_path",
                "frontend delivery path is not portable",
            ));
        };
        segments.push(segment.to_str().ok_or_else(|| {
            FrontendContractError::new(
                "frontend_unsafe_path",
                "frontend delivery path must be UTF-8",
            )
        })?);
    }
    Ok(segments.join("/"))
}

fn resolve_required_file(root: &Path, relative: &str) -> Result<PathBuf, FrontendContractError> {
    validate_relative_path(relative)?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut path = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(FrontendContractError::new(
                "frontend_source_map_path_invalid",
                format!("frontend contract path is unsafe: {relative}"),
            ));
        };
        path.push(name);
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            let code = if error.kind() == std::io::ErrorKind::NotFound {
                "frontend_required_file_missing"
            } else {
                "frontend_io_error"
            };
            FrontendContractError::new(
                code,
                format!("inspect required frontend path {relative} failed: {error}"),
            )
        })?;
        if metadata.file_type().is_symlink() {
            return Err(FrontendContractError::new(
                "frontend_unsafe_path",
                format!("required frontend path traverses a symlink: {relative}"),
            ));
        }
        let final_component = index + 1 == components.len();
        if (final_component && !metadata.is_file()) || (!final_component && !metadata.is_dir()) {
            return Err(FrontendContractError::new(
                "frontend_required_file_invalid",
                format!("required frontend path has the wrong file type: {relative}"),
            ));
        }
    }
    Ok(path)
}

fn forbidden_path_present(root: &Path, relative: &str) -> Result<bool, FrontendContractError> {
    validate_relative_path(relative)?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut path = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(FrontendContractError::new(
                "frontend_source_map_path_invalid",
                format!("frontend contract path is unsafe: {relative}"),
            ));
        };
        path.push(name);
        match fs::symlink_metadata(&path) {
            Ok(metadata) => {
                if index + 1 == components.len() {
                    return Ok(true);
                }
                if metadata.file_type().is_symlink() || !metadata.is_dir() {
                    return Err(FrontendContractError::new(
                        "frontend_unsafe_path",
                        format!("forbidden frontend path has an unsafe parent: {relative}"),
                    ));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => {
                return Err(FrontendContractError::new(
                    "frontend_io_error",
                    format!("inspect forbidden frontend path failed: {error}"),
                ));
            }
        }
    }
    Ok(false)
}

fn verify_real_directory(path: &Path, label: &str) -> Result<(), FrontendContractError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect {label} failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(FrontendContractError::new(
            "frontend_unsafe_path",
            format!("{label} must be a real non-symlink directory"),
        ));
    }
    Ok(())
}

fn read_bounded_regular_file(
    path: &Path,
    limit: u64,
    label: &str,
) -> Result<Vec<u8>, FrontendContractError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect {label} failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(FrontendContractError::new(
            "frontend_input_not_bounded_regular_file",
            format!("{label} must be a bounded regular non-symlink file"),
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(path).map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("open {label} without symlink traversal failed: {error}"),
        )
    })?;
    let opened = file.metadata().map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect opened {label} failed: {error}"),
        )
    })?;
    if !opened.is_file() || opened.len() != metadata.len() || opened.len() > limit {
        return Err(FrontendContractError::new(
            "frontend_input_changed",
            format!("{label} changed while being opened"),
        ));
    }
    let capacity = usize::try_from(opened.len()).map_err(|_| {
        FrontendContractError::new(
            "frontend_input_length_invalid",
            format!("{label} length is not addressable"),
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| {
            FrontendContractError::new("frontend_io_error", format!("read {label} failed: {error}"))
        })?;
    if u64::try_from(bytes.len()).ok() != Some(opened.len()) {
        return Err(FrontendContractError::new(
            "frontend_input_changed",
            format!("{label} changed while being read"),
        ));
    }
    Ok(bytes)
}

fn hash_without_receipt_hash(
    receipt: &FrontendContractReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_receipt_encode_failed",
            format!("project frontend receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_receipt_encode_failed",
                "frontend receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_receipt_encode_failed",
            format!("canonicalize frontend receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn hash_without_delivery_receipt_hash(
    receipt: &FrontendDeliveryReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_delivery_receipt_encode_failed",
            format!("project frontend delivery receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_delivery_receipt_encode_failed",
                "frontend delivery receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_delivery_receipt_encode_failed",
            format!("canonicalize frontend delivery receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn canonical_struct<T: Serialize>(
    value: &T,
    code: &'static str,
) -> Result<String, FrontendContractError> {
    let value = serde_json::to_value(value).map_err(|error| {
        FrontendContractError::new(code, format!("project canonical JSON failed: {error}"))
    })?;
    canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(code, format!("canonical JSON failed: {error}"))
    })
}

#[cfg(test)]
mod tests {
    use super::{decode_object, validate_relative_path, TEST_SOURCE_MAP};

    #[test]
    fn embedded_source_map_is_strict_json() {
        let bytes = std::fs::read(TEST_SOURCE_MAP).expect("read embedded source map");
        let object = decode_object(&bytes, "test_json_invalid", "source map")
            .expect("strict source-map JSON");
        assert_eq!(
            object
                .get("schema_version")
                .and_then(serde_json::Value::as_str),
            Some("structural-legacy-frontend-build-contract.v1")
        );
    }

    #[test]
    fn relative_paths_reject_escape_absolute_and_backslash() {
        for invalid in ["", "../package.json", "/package.json", "src\\main.tsx"] {
            assert!(validate_relative_path(invalid).is_err(), "{invalid}");
        }
        assert!(validate_relative_path("src/main.tsx").is_ok());
    }

    #[test]
    fn strict_decoder_rejects_duplicate_keys_and_non_objects() {
        assert!(decode_object(
            b"{\"name\":\"a\",\"name\":\"b\"}",
            "test_json_invalid",
            "fixture"
        )
        .is_err());
        assert!(decode_object(b"[]", "test_json_invalid", "fixture").is_err());
    }
}
