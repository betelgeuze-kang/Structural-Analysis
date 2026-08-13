use std::path::Path;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::playwright::{
    execute_playwright, map_playwright_error, validate_playwright_plan, PlaywrightErrorDomain,
    PlaywrightExecution, PlaywrightPlan, PlaywrightServerRoute,
};
use super::{
    canonical_struct, check_frontend_contract, check_workbench_prototype, parse_source_map,
    read_bounded_regular_file, resolve_required_file, verify_real_directory, FrontendContractError,
    SOURCE_MAP_BYTES,
};

const PROTOTYPE_BROWSER_SMOKE_CONTRACT_V1: &str =
    "structural-native-workbench-prototype-browser-smoke-contract.v1";
const PROTOTYPE_BROWSER_SMOKE_RECEIPT_V1: &str =
    "structural-native-workbench-prototype-browser-smoke-receipt.v1";
const MAX_SPEC_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PLAYWRIGHT_CLI: &str = "node_modules/@playwright/test/cli.js";
const EXPECTED_SPEC: &str = "tests/frontend/workbench-prototype-smoke.spec.ts";
const EXPECTED_SERVER_PREFIX: &str = "prototype/structural-workbench/";
const EXPECTED_SERVER_ENTRY: &str = "prototype/structural-workbench/index.html";
const EXPECTED_BASE_URL_ENVIRONMENT: &str = "WORKBENCH_PROTOTYPE_BASE_URL";
const EXTERNAL_NETWORK_ACCOUNTING: &str = "not_instrumented_browser_page_requests";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkbenchPrototypeBrowserSmokeSourceV1 {
    schema_version: String,
    node_launcher: String,
    playwright_cli_path: String,
    spec_path: String,
    server_path_prefix: String,
    server_entry_path: String,
    base_url_environment: String,
    external_network_access_accounting: String,
    claim_boundary: String,
}

struct PreparedPrototypeBrowserSmoke {
    source: WorkbenchPrototypeBrowserSmokeSourceV1,
    frontend_contract_receipt_hash: String,
    prototype_contract_receipt_hash: String,
    spec_bytes: Vec<u8>,
    playwright_plan: PlaywrightPlan,
}

/// Canonical receipt for one planned or completed Workbench prototype browser smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkbenchPrototypeBrowserSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub prototype_contract_receipt_hash: String,
    pub spec_sha256: String,
    pub playwright_cli_sha256: Option<String>,
    pub logical_command: Vec<String>,
    pub server_path_prefix: String,
    pub base_url_environment: String,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub loopback_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub request_error_count: u64,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Plan or execute the retained Workbench prototype Playwright smoke under Rust ownership.
///
/// Dry-run validates the tracked frontend, static prototype, specification, command, environment,
/// and scoped server policy without binding a listener or spawning a process. Live execution owns
/// one ephemeral IPv4 loopback listener and one direct Node child running the pinned Playwright
/// CLI, then publishes a receipt only after an exit code of zero.
///
/// # Errors
///
/// Rejects contract drift, unsafe or missing files, invalid execution plans, missing runtime
/// files, socket or process failures, nonzero browser exit, and server-thread failure.
pub fn run_workbench_prototype_browser_smoke(
    root: &Path,
    dry_run: bool,
) -> Result<WorkbenchPrototypeBrowserSmokeReceiptV1, FrontendContractError> {
    let prepared = prepare_prototype_browser_smoke(root)
        .map_err(|error| map_playwright_error(PlaywrightErrorDomain::WorkbenchPrototype, error))?;
    let execution = if dry_run {
        None
    } else {
        Some(
            execute_playwright(&prepared.playwright_plan).map_err(|error| {
                map_playwright_error(PlaywrightErrorDomain::WorkbenchPrototype, error)
            })?,
        )
    };
    build_receipt(prepared, execution.as_ref())
}

fn prepare_prototype_browser_smoke(
    root: &Path,
) -> Result<PreparedPrototypeBrowserSmoke, FrontendContractError> {
    verify_real_directory(root, "Workbench prototype browser smoke root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(root)?.receipt_hash;
    let prototype_contract_receipt_hash = check_workbench_prototype(root)?.receipt_hash;
    let source = parse_source_map()?.workbench_prototype_browser_smoke_contract;
    let working_root = root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_browser_smoke_root_invalid",
            format!("canonicalize Workbench prototype browser smoke root failed: {error}"),
        )
    })?;
    resolve_required_file(&working_root, &source.server_entry_path)?;
    let spec_path = resolve_required_file(&working_root, &source.spec_path)?;
    let spec_bytes = read_bounded_regular_file(
        &spec_path,
        MAX_SPEC_BYTES,
        "Workbench prototype browser smoke specification",
    )?;
    let logical_command = vec![
        source.node_launcher.clone(),
        source.playwright_cli_path.clone(),
        "test".to_owned(),
        source.spec_path.clone(),
        "--reporter=line".to_owned(),
    ];
    let playwright_plan = PlaywrightPlan {
        root: working_root.clone(),
        server_root: working_root,
        node_launcher: source.node_launcher.clone(),
        playwright_cli_path: source.playwright_cli_path.clone(),
        playwright_cli_command_index: 1,
        logical_command,
        base_url_environment: source.base_url_environment.clone(),
        base_url_path: format!("/{}", source.server_path_prefix.trim_end_matches('/')),
        listener_port: 0,
        extra_environment: Vec::new(),
        server_route: PlaywrightServerRoute::Scoped {
            allowed_path_prefix: source.server_path_prefix.clone(),
            root_redirect: format!("/{}", source.server_entry_path),
        },
    };
    validate_playwright_plan(&playwright_plan)?;
    Ok(PreparedPrototypeBrowserSmoke {
        source,
        frontend_contract_receipt_hash,
        prototype_contract_receipt_hash,
        spec_bytes,
        playwright_plan,
    })
}

/// Encode a Workbench prototype browser-smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_workbench_prototype_browser_smoke_receipt_json(
    receipt: &WorkbenchPrototypeBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(
        receipt,
        "workbench_prototype_browser_smoke_receipt_encode_failed",
    )
}

pub(crate) fn validate_workbench_prototype_browser_smoke_source(
    source: &WorkbenchPrototypeBrowserSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    if source.schema_version != PROTOTYPE_BROWSER_SMOKE_CONTRACT_V1
        || source.node_launcher != EXPECTED_NODE_LAUNCHER
        || source.playwright_cli_path != EXPECTED_PLAYWRIGHT_CLI
        || source.spec_path != EXPECTED_SPEC
        || source.server_path_prefix != EXPECTED_SERVER_PREFIX
        || source.server_entry_path != EXPECTED_SERVER_ENTRY
        || source.base_url_environment != EXPECTED_BASE_URL_ENVIRONMENT
        || source.external_network_access_accounting != EXTERNAL_NETWORK_ACCOUNTING
        || !valid_text(&source.claim_boundary)
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Workbench prototype browser smoke contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedPrototypeBrowserSmoke,
    execution: Option<&PlaywrightExecution>,
) -> Result<WorkbenchPrototypeBrowserSmokeReceiptV1, FrontendContractError> {
    let dry_run = execution.is_none();
    let mut receipt = WorkbenchPrototypeBrowserSmokeReceiptV1 {
        schema_version: PROTOTYPE_BROWSER_SMOKE_RECEIPT_V1.to_owned(),
        action: "workbench_prototype_browser_smoke".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "passed" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        prototype_contract_receipt_hash: prepared.prototype_contract_receipt_hash,
        spec_sha256: sha256_identity(&prepared.spec_bytes),
        playwright_cli_sha256: execution.map(|value| value.playwright_cli_sha256.clone()),
        logical_command: prepared.playwright_plan.logical_command,
        server_path_prefix: prepared.source.server_path_prefix,
        base_url_environment: prepared.source.base_url_environment,
        node_runtime_required: true,
        browser_runtime_required: true,
        loopback_listener_count: u64::from(!dry_run),
        direct_processes_spawned: execution.map_or(0, |value| value.direct_processes_spawned),
        successful_exit_code: execution.map(|value| value.successful_exit_code),
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
    receipt: &WorkbenchPrototypeBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_browser_smoke_receipt_encode_failed",
            format!("project Workbench prototype browser smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "workbench_prototype_browser_smoke_receipt_encode_failed",
                "Workbench prototype browser smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_browser_smoke_receipt_encode_failed",
            format!("canonicalize Workbench prototype browser smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{
        validate_workbench_prototype_browser_smoke_source, WorkbenchPrototypeBrowserSmokeSourceV1,
    };

    #[test]
    fn prototype_browser_source_contract_cannot_widen_server_or_command() {
        let source = WorkbenchPrototypeBrowserSmokeSourceV1 {
            schema_version: "structural-native-workbench-prototype-browser-smoke-contract.v1"
                .to_owned(),
            node_launcher: "node".to_owned(),
            playwright_cli_path: "node_modules/@playwright/test/cli.js".to_owned(),
            spec_path: "tests/frontend/workbench-prototype-smoke.spec.ts".to_owned(),
            server_path_prefix: "prototype/structural-workbench/".to_owned(),
            server_entry_path: "prototype/structural-workbench/index.html".to_owned(),
            base_url_environment: "WORKBENCH_PROTOTYPE_BASE_URL".to_owned(),
            external_network_access_accounting: "not_instrumented_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        };
        assert!(validate_workbench_prototype_browser_smoke_source(&source).is_ok());
        let mut drift = source;
        drift.server_path_prefix = "prototype/".to_owned();
        assert!(validate_workbench_prototype_browser_smoke_source(&drift).is_err());
    }
}
