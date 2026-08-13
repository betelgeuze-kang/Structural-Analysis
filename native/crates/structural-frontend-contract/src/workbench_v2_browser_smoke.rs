use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::Path;
use std::process::Command;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::playwright::{
    execute_playwright, map_playwright_error, validate_playwright_plan, PlaywrightErrorDomain,
    PlaywrightExecution, PlaywrightPlan, PlaywrightServerRoute,
};
use super::{
    canonical_struct, check_frontend_contract, check_frontend_delivery, parse_source_map,
    read_bounded_regular_file, resolve_required_directory, resolve_required_file,
    validate_relative_path, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-workbench-v2-browser-smoke-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-workbench-v2-browser-smoke-receipt.v1";
const MAX_LOADER_BYTES: u64 = 1024 * 1024;
const MAX_SPEC_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_LOADER_PATH: &str = "scripts/json-module-loader.mjs";
const EXPECTED_LOADER_ARGUMENT: &str = "--loader=./scripts/json-module-loader.mjs";
const EXPECTED_PLAYWRIGHT_CLI: &str = "node_modules/@playwright/test/cli.js";
const EXPECTED_DIST_DIRECTORY: &str = "dist";
const EXPECTED_FALLBACK_ENTRY: &str = "index.html";
const EXPECTED_BASE_URL_ENVIRONMENT: &str = "WORKBENCH_V2_BASE_URL";
const EXPECTED_EXTERNAL_NETWORK_ACCOUNTING: &str =
    "not_instrumented_npm_build_and_browser_page_requests";
const EXPECTED_SPECS: [&str; 6] = [
    "tests/frontend/workbench-v2-e2e.spec.ts",
    "tests/frontend/workbench-v2-unit-coordinate-guard.spec.ts",
    "tests/frontend/workbench-v2-live-provider-guard.spec.ts",
    "tests/frontend/workbench-v2-job-contract.spec.ts",
    "tests/frontend/workbench-v2-engineering-value-state.spec.ts",
    "tests/frontend/workbench-v2-status-taxonomy.spec.ts",
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkbenchV2BrowserSmokeSourceV1 {
    schema_version: String,
    build_command: Vec<String>,
    build_environment: BTreeMap<String, String>,
    node_launcher: String,
    node_environment: BTreeMap<String, String>,
    json_module_loader_path: String,
    playwright_cli_path: String,
    spec_paths: Vec<String>,
    dist_directory: String,
    spa_fallback_entry: String,
    base_url_environment: String,
    external_network_access_accounting: String,
    claim_boundary: String,
}

struct PreparedWorkbenchV2BrowserSmoke {
    source: WorkbenchV2BrowserSmokeSourceV1,
    frontend_contract_receipt_hash: String,
    loader_bytes: Vec<u8>,
    specifications: Vec<WorkbenchV2BrowserSmokeSpecificationV1>,
    playwright_plan: PlaywrightPlan,
}

/// One source specification bound into the Workbench v2 browser-smoke receipt.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkbenchV2BrowserSmokeSpecificationV1 {
    pub path: String,
    pub sha256: String,
}

/// Canonical receipt for one planned or completed Workbench v2 browser smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkbenchV2BrowserSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub delivery_receipt_hash: Option<String>,
    pub build_command: Vec<String>,
    pub build_environment: BTreeMap<String, String>,
    pub json_module_loader_sha256: String,
    pub specifications: Vec<WorkbenchV2BrowserSmokeSpecificationV1>,
    pub playwright_cli_sha256: Option<String>,
    pub playwright_command: Vec<String>,
    pub dist_directory: String,
    pub spa_fallback_entry: String,
    pub base_url_environment: String,
    pub node_environment: BTreeMap<String, String>,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub loopback_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub request_error_count: u64,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Plan or execute the retained Workbench v2 build and Playwright suite under Rust ownership.
///
/// Dry-run validates and hashes the tracked build, loader, specification, command, environment,
/// and SPA-server plan without spawning a process or binding a listener. Live execution directly
/// owns one npm build child, verifies the unchanged contract and emitted delivery, then owns one
/// ephemeral IPv4 loopback listener and one Node child running the pinned Playwright CLI.
///
/// # Errors
///
/// Rejects contract drift, unsafe or missing files, build failure, an invalid emitted delivery,
/// missing runtime files, socket or browser-process failure, and any nonzero child exit.
pub fn run_workbench_v2_browser_smoke(
    root: &Path,
    dry_run: bool,
) -> Result<WorkbenchV2BrowserSmokeReceiptV1, FrontendContractError> {
    let mut prepared = prepare_workbench_v2_browser_smoke(root)
        .map_err(|error| map_playwright_error(PlaywrightErrorDomain::WorkbenchV2, error))?;
    if dry_run {
        return build_receipt(prepared, None, None, None);
    }

    let build_exit_code = run_build_command(
        &prepared.playwright_plan.root,
        &prepared.source.build_command,
        &prepared.source.build_environment,
    )?;
    let post_contract = check_frontend_contract(&prepared.playwright_plan.root)?;
    if post_contract.receipt_hash != prepared.frontend_contract_receipt_hash {
        return Err(FrontendContractError::new(
            "workbench_v2_browser_smoke_contract_changed",
            "frontend package or lock contract changed while the Workbench v2 build executed",
        ));
    }
    let delivery_receipt_hash =
        check_frontend_delivery(&prepared.playwright_plan.root)?.receipt_hash;
    prepared.playwright_plan.server_root = resolve_required_directory(
        &prepared.playwright_plan.root,
        &prepared.source.dist_directory,
    )?;
    let execution = execute_playwright(&prepared.playwright_plan)
        .map_err(|error| map_playwright_error(PlaywrightErrorDomain::WorkbenchV2, error))?;
    build_receipt(
        prepared,
        Some(delivery_receipt_hash),
        Some(build_exit_code),
        Some(&execution),
    )
}

fn prepare_workbench_v2_browser_smoke(
    root: &Path,
) -> Result<PreparedWorkbenchV2BrowserSmoke, FrontendContractError> {
    verify_real_directory(root, "Workbench v2 browser smoke root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(root)?.receipt_hash;
    let source = parse_source_map()?.workbench_v2_browser_smoke_contract;
    let working_root = root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "workbench_v2_browser_smoke_root_invalid",
            format!("canonicalize Workbench v2 browser smoke root failed: {error}"),
        )
    })?;
    let loader_path = resolve_required_file(&working_root, &source.json_module_loader_path)?;
    let loader_bytes = read_bounded_regular_file(
        &loader_path,
        MAX_LOADER_BYTES,
        "Workbench v2 JSON module loader",
    )?;
    let specifications = source
        .spec_paths
        .iter()
        .map(|relative| {
            let path = resolve_required_file(&working_root, relative)?;
            let bytes = read_bounded_regular_file(
                &path,
                MAX_SPEC_BYTES,
                "Workbench v2 browser smoke specification",
            )?;
            Ok(WorkbenchV2BrowserSmokeSpecificationV1 {
                path: relative.clone(),
                sha256: sha256_identity(&bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;

    let mut playwright_command = vec![
        source.node_launcher.clone(),
        source.playwright_cli_path.clone(),
        "test".to_owned(),
    ];
    playwright_command.extend(source.spec_paths.iter().cloned());
    playwright_command.push("--reporter=line".to_owned());
    let playwright_plan = PlaywrightPlan {
        root: working_root.clone(),
        server_root: working_root.join(&source.dist_directory),
        node_launcher: source.node_launcher.clone(),
        playwright_cli_path: source.playwright_cli_path.clone(),
        playwright_cli_command_index: 1,
        logical_command: playwright_command,
        base_url_environment: source.base_url_environment.clone(),
        base_url_path: String::new(),
        extra_environment: source
            .node_environment
            .iter()
            .map(|(name, value)| (name.clone(), value.clone()))
            .collect(),
        server_route: PlaywrightServerRoute::Spa {
            fallback_entry: source.spa_fallback_entry.clone(),
        },
    };
    validate_playwright_plan(&playwright_plan)?;
    Ok(PreparedWorkbenchV2BrowserSmoke {
        source,
        frontend_contract_receipt_hash,
        loader_bytes,
        specifications,
        playwright_plan,
    })
}

/// Encode a Workbench v2 browser-smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_workbench_v2_browser_smoke_receipt_json(
    receipt: &WorkbenchV2BrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "workbench_v2_browser_smoke_receipt_encode_failed")
}

pub(crate) fn validate_workbench_v2_browser_smoke_source(
    source: &WorkbenchV2BrowserSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    let expected_build = ["npm", "run", "build"];
    let expected_build_environment =
        BTreeMap::from([("VITE_BASE_PATH".to_owned(), "/".to_owned())]);
    let expected_node_environment = BTreeMap::from([(
        "NODE_OPTIONS".to_owned(),
        EXPECTED_LOADER_ARGUMENT.to_owned(),
    )]);
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source
            .build_command
            .iter()
            .map(String::as_str)
            .eq(expected_build)
        && source.build_environment == expected_build_environment
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.node_environment == expected_node_environment
        && source.json_module_loader_path == EXPECTED_LOADER_PATH
        && source.playwright_cli_path == EXPECTED_PLAYWRIGHT_CLI
        && source
            .spec_paths
            .iter()
            .map(String::as_str)
            .eq(EXPECTED_SPECS)
        && source.dist_directory == EXPECTED_DIST_DIRECTORY
        && source.spa_fallback_entry == EXPECTED_FALLBACK_ENTRY
        && source.base_url_environment == EXPECTED_BASE_URL_ENVIRONMENT
        && source.external_network_access_accounting == EXPECTED_EXTERNAL_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Workbench v2 browser smoke contract is invalid",
        ));
    }
    for relative in source.spec_paths.iter().chain([
        &source.json_module_loader_path,
        &source.playwright_cli_path,
        &source.dist_directory,
        &source.spa_fallback_entry,
    ]) {
        validate_relative_path(relative)?;
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn npm_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("npm.cmd")
    } else {
        OsString::from("npm")
    }
}

fn run_build_command(
    root: &Path,
    logical_command: &[String],
    environment: &BTreeMap<String, String>,
) -> Result<i32, FrontendContractError> {
    let arguments = logical_command.get(1..).ok_or_else(|| {
        FrontendContractError::new(
            "workbench_v2_browser_smoke_build_command_invalid",
            "Workbench v2 build command has no argument boundary",
        )
    })?;
    let status = Command::new(npm_launcher())
        .args(arguments)
        .current_dir(root)
        .envs(environment)
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "workbench_v2_browser_smoke_build_launch_failed",
                format!("launch Workbench v2 build failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "workbench_v2_browser_smoke_build_terminated",
            "Workbench v2 build terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "workbench_v2_browser_smoke_build_failed",
            format!("Workbench v2 build failed with exit code {exit_code}"),
        ));
    }
    Ok(exit_code)
}

fn build_receipt(
    prepared: PreparedWorkbenchV2BrowserSmoke,
    delivery_receipt_hash: Option<String>,
    build_exit_code: Option<i32>,
    execution: Option<&PlaywrightExecution>,
) -> Result<WorkbenchV2BrowserSmokeReceiptV1, FrontendContractError> {
    let dry_run = execution.is_none();
    let successful_exit_codes = match (build_exit_code, execution) {
        (None, None) => Vec::new(),
        (Some(build), Some(browser)) => vec![build, browser.successful_exit_code],
        _ => {
            return Err(FrontendContractError::new(
                "workbench_v2_browser_smoke_receipt_encode_failed",
                "Workbench v2 browser smoke execution receipt is incomplete",
            ));
        }
    };
    let mut receipt = WorkbenchV2BrowserSmokeReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "workbench_v2_browser_smoke".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        delivery_receipt_hash,
        build_command: prepared.source.build_command,
        build_environment: prepared.source.build_environment,
        json_module_loader_sha256: sha256_identity(&prepared.loader_bytes),
        specifications: prepared.specifications,
        playwright_cli_sha256: execution.map(|value| value.playwright_cli_sha256.clone()),
        playwright_command: prepared.playwright_plan.logical_command,
        dist_directory: prepared.source.dist_directory,
        spa_fallback_entry: prepared.source.spa_fallback_entry,
        base_url_environment: prepared.source.base_url_environment,
        node_environment: prepared.source.node_environment,
        node_runtime_required: true,
        browser_runtime_required: true,
        loopback_listener_count: u64::from(!dry_run),
        direct_processes_spawned: if dry_run { 0 } else { 2 },
        successful_exit_codes,
        request_error_count: execution.map_or(0, |value| value.request_error_count),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: dry_run,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &WorkbenchV2BrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "workbench_v2_browser_smoke_receipt_encode_failed",
            format!("project Workbench v2 browser smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "workbench_v2_browser_smoke_receipt_encode_failed",
                "Workbench v2 browser smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "workbench_v2_browser_smoke_receipt_encode_failed",
            format!("canonicalize Workbench v2 browser smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::{
        validate_workbench_v2_browser_smoke_source, WorkbenchV2BrowserSmokeSourceV1, EXPECTED_SPECS,
    };

    #[test]
    fn source_contract_rejects_command_spec_and_environment_widening() {
        let source = WorkbenchV2BrowserSmokeSourceV1 {
            schema_version: "structural-native-workbench-v2-browser-smoke-contract.v1".to_owned(),
            build_command: vec!["npm".to_owned(), "run".to_owned(), "build".to_owned()],
            build_environment: BTreeMap::from([("VITE_BASE_PATH".to_owned(), "/".to_owned())]),
            node_launcher: "node".to_owned(),
            node_environment: BTreeMap::from([(
                "NODE_OPTIONS".to_owned(),
                "--loader=./scripts/json-module-loader.mjs".to_owned(),
            )]),
            json_module_loader_path: "scripts/json-module-loader.mjs".to_owned(),
            playwright_cli_path: "node_modules/@playwright/test/cli.js".to_owned(),
            spec_paths: EXPECTED_SPECS.iter().map(ToString::to_string).collect(),
            dist_directory: "dist".to_owned(),
            spa_fallback_entry: "index.html".to_owned(),
            base_url_environment: "WORKBENCH_V2_BASE_URL".to_owned(),
            external_network_access_accounting:
                "not_instrumented_npm_build_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        };
        assert!(validate_workbench_v2_browser_smoke_source(&source).is_ok());
        let mut drift = source;
        drift.node_environment.clear();
        assert!(validate_workbench_v2_browser_smoke_source(&drift).is_err());
    }
}
