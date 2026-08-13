use std::path::{Path, PathBuf};

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
    run_frontend_build, validate_relative_path, verify_real_directory, FrontendBuildOptions,
    FrontendBuildReceiptV1, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-phase5-task-browser-smoke-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-phase5-task-browser-smoke-receipt.v1";
const MAX_SPEC_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PLAYWRIGHT_CLI: &str = "node_modules/@playwright/test/cli.js";
const EXPECTED_SPEC: &str = "tests/frontend/developer-preview-workflow.spec.ts";
const EXPECTED_DIST_DIRECTORY: &str = "dist";
const EXPECTED_FALLBACK_ENTRY: &str = "index.html";
const EXPECTED_BASE_URL_ENVIRONMENT: &str = "DEVELOPER_PREVIEW_BASE_URL";
const EXPECTED_LOOPBACK_PORT: u16 = 4_173;
const EXPECTED_EXTERNAL_NETWORK_ACCOUNTING: &str =
    "not_instrumented_frontend_build_and_browser_page_requests";
const EXPECTED_WORKFLOW_STEPS: [&str; 5] = [
    "import",
    "model_health",
    "analysis_setup",
    "run_monitor",
    "compare_report",
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Phase5TaskBrowserSmokeSourceV1 {
    schema_version: String,
    node_launcher: String,
    playwright_cli_path: String,
    spec_path: String,
    dist_directory: String,
    spa_fallback_entry: String,
    base_url_environment: String,
    loopback_port: u16,
    required_workflow_steps: Vec<String>,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Options for the bounded Phase 5 task-based browser smoke.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Phase5TaskBrowserSmokeOptions {
    pub root: PathBuf,
    pub dry_run: bool,
    pub skip_build: bool,
}

impl Phase5TaskBrowserSmokeOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
            skip_build: false,
        }
    }
}

/// Frozen identity of the one Phase 5 Playwright specification.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Phase5TaskBrowserSmokeSpecificationV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Retained runtime boundary for the Phase 5 task-based browser smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Phase5TaskBrowserSmokeRuntimeRequirementsV1 {
    pub node_required: bool,
    pub browser_required: bool,
}

/// Canonical plan or success receipt for the Phase 5 task-based browser smoke.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Phase5TaskBrowserSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub build_skipped: bool,
    pub build_disposition: String,
    pub frontend_build_receipt_hash: Option<String>,
    pub delivery_receipt_hash: Option<String>,
    pub specification: Phase5TaskBrowserSmokeSpecificationV1,
    pub playwright_cli_sha256: Option<String>,
    pub playwright_command: Vec<String>,
    pub dist_directory: String,
    pub spa_fallback_entry: String,
    pub base_url_environment: String,
    pub required_workflow_steps: Vec<String>,
    pub runtime_requirements: Phase5TaskBrowserSmokeRuntimeRequirementsV1,
    pub loopback_listener_count: u64,
    pub loopback_port: u16,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub request_error_count: u64,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedPhase5TaskBrowserSmoke {
    source: Phase5TaskBrowserSmokeSourceV1,
    frontend_contract_receipt_hash: String,
    spec_bytes: Vec<u8>,
    playwright_plan: PlaywrightPlan,
}

/// Plan or execute the Phase 5 build, fixed-loopback server, and Playwright task smoke.
///
/// Dry-run validates and hashes the frontend build plan, source contract, exact specification,
/// command, workflow vocabulary, and SPA route without spawning a process or binding a listener.
/// Live execution uses the Rust-owned frontend build unless `skip_build` is requested, validates
/// the delivery, then owns one fixed IPv4 loopback listener and the exact Playwright Node child.
///
/// # Errors
///
/// Rejects contract or source drift, unsafe or missing delivery/runtime files, build failure,
/// socket failure, browser-process failure, request errors, and nonzero child exits.
pub fn run_phase5_task_browser_smoke(
    options: &Phase5TaskBrowserSmokeOptions,
) -> Result<Phase5TaskBrowserSmokeReceiptV1, FrontendContractError> {
    let mut prepared = prepare_phase5_task_browser_smoke(&options.root)
        .map_err(|error| map_playwright_error(PlaywrightErrorDomain::Phase5Task, error))?;

    let frontend_build = if options.skip_build {
        None
    } else {
        let mut build_options = FrontendBuildOptions::new(prepared.playwright_plan.root.clone());
        build_options.dry_run = options.dry_run;
        Some(run_frontend_build(&build_options)?)
    };
    if options.dry_run {
        return build_receipt(prepared, options, frontend_build.as_ref(), None, None);
    }

    verify_inputs_unchanged(&prepared)?;
    let delivery_receipt_hash = match frontend_build.as_ref() {
        Some(build) => build.delivery_receipt_hash.clone().ok_or_else(|| {
            FrontendContractError::new(
                "phase5_task_browser_smoke_build_receipt_invalid",
                "executed frontend build did not publish a delivery receipt hash",
            )
        })?,
        None => check_frontend_delivery(&prepared.playwright_plan.root)?.receipt_hash,
    };
    prepared.playwright_plan.server_root = resolve_required_directory(
        &prepared.playwright_plan.root,
        &prepared.source.dist_directory,
    )?;
    let execution = execute_playwright(&prepared.playwright_plan)
        .map_err(|error| map_playwright_error(PlaywrightErrorDomain::Phase5Task, error))?;
    verify_inputs_unchanged(&prepared)?;
    if check_frontend_delivery(&prepared.playwright_plan.root)?.receipt_hash
        != delivery_receipt_hash
    {
        return Err(FrontendContractError::new(
            "phase5_task_browser_smoke_delivery_changed",
            "frontend delivery changed during Phase 5 browser execution",
        ));
    }
    build_receipt(
        prepared,
        options,
        frontend_build.as_ref(),
        Some(delivery_receipt_hash),
        Some(&execution),
    )
}

fn prepare_phase5_task_browser_smoke(
    root: &Path,
) -> Result<PreparedPhase5TaskBrowserSmoke, FrontendContractError> {
    verify_real_directory(root, "Phase 5 task browser smoke root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(root)?.receipt_hash;
    let source = parse_source_map()?.phase5_task_browser_smoke_contract;
    let working_root = root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "phase5_task_browser_smoke_root_invalid",
            format!("canonicalize Phase 5 browser-smoke root failed: {error}"),
        )
    })?;
    let spec_path = resolve_required_file(&working_root, &source.spec_path)?;
    let spec_bytes = read_bounded_regular_file(
        &spec_path,
        MAX_SPEC_BYTES,
        "Phase 5 task browser smoke specification",
    )?;
    let playwright_plan = PlaywrightPlan {
        root: working_root.clone(),
        server_root: working_root.join(&source.dist_directory),
        node_launcher: source.node_launcher.clone(),
        playwright_cli_path: source.playwright_cli_path.clone(),
        playwright_cli_command_index: 1,
        logical_command: vec![
            source.node_launcher.clone(),
            source.playwright_cli_path.clone(),
            "test".to_owned(),
            source.spec_path.clone(),
            "--reporter=line".to_owned(),
        ],
        base_url_environment: source.base_url_environment.clone(),
        base_url_path: String::new(),
        listener_port: source.loopback_port,
        extra_environment: Vec::new(),
        server_route: PlaywrightServerRoute::Spa {
            fallback_entry: source.spa_fallback_entry.clone(),
        },
    };
    validate_playwright_plan(&playwright_plan)?;
    Ok(PreparedPhase5TaskBrowserSmoke {
        source,
        frontend_contract_receipt_hash,
        spec_bytes,
        playwright_plan,
    })
}

fn verify_inputs_unchanged(
    prepared: &PreparedPhase5TaskBrowserSmoke,
) -> Result<(), FrontendContractError> {
    let current_contract = check_frontend_contract(&prepared.playwright_plan.root)?;
    let current_spec = read_bounded_regular_file(
        &resolve_required_file(&prepared.playwright_plan.root, &prepared.source.spec_path)?,
        MAX_SPEC_BYTES,
        "Phase 5 task browser smoke specification",
    )?;
    if current_contract.receipt_hash != prepared.frontend_contract_receipt_hash
        || current_spec != prepared.spec_bytes
    {
        return Err(FrontendContractError::new(
            "phase5_task_browser_smoke_contract_changed",
            "frontend contract or Phase 5 specification changed during execution",
        ));
    }
    Ok(())
}

/// Encode a Phase 5 task browser-smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_phase5_task_browser_smoke_receipt_json(
    receipt: &Phase5TaskBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "phase5_task_browser_smoke_receipt_encode_failed")
}

pub(crate) fn validate_phase5_task_browser_smoke_source(
    source: &Phase5TaskBrowserSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.playwright_cli_path == EXPECTED_PLAYWRIGHT_CLI
        && source.spec_path == EXPECTED_SPEC
        && source.dist_directory == EXPECTED_DIST_DIRECTORY
        && source.spa_fallback_entry == EXPECTED_FALLBACK_ENTRY
        && source.base_url_environment == EXPECTED_BASE_URL_ENVIRONMENT
        && source.loopback_port == EXPECTED_LOOPBACK_PORT
        && source
            .required_workflow_steps
            .iter()
            .map(String::as_str)
            .eq(EXPECTED_WORKFLOW_STEPS)
        && source.external_network_access_accounting == EXPECTED_EXTERNAL_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Phase 5 task browser smoke contract is invalid",
        ));
    }
    for relative in [
        &source.playwright_cli_path,
        &source.spec_path,
        &source.dist_directory,
        &source.spa_fallback_entry,
    ] {
        validate_relative_path(relative)?;
    }
    Ok(())
}

fn build_receipt(
    prepared: PreparedPhase5TaskBrowserSmoke,
    options: &Phase5TaskBrowserSmokeOptions,
    frontend_build: Option<&FrontendBuildReceiptV1>,
    delivery_receipt_hash: Option<String>,
    execution: Option<&PlaywrightExecution>,
) -> Result<Phase5TaskBrowserSmokeReceiptV1, FrontendContractError> {
    let executed = execution.is_some();
    let mut exit_codes =
        frontend_build.map_or_else(Vec::new, |build| build.successful_exit_codes.clone());
    if let Some(browser) = execution {
        exit_codes.push(browser.successful_exit_code);
    }
    let build_process_count = frontend_build.map_or(0, |build| build.direct_processes_spawned);
    let browser_process_count = execution.map_or(0, |browser| browser.direct_processes_spawned);
    let direct_processes_spawned = build_process_count
        .checked_add(browser_process_count)
        .ok_or_else(|| {
            FrontendContractError::new(
                "phase5_task_browser_smoke_receipt_encode_failed",
                "Phase 5 direct-process count overflowed",
            )
        })?;
    let byte_length = u64::try_from(prepared.spec_bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "phase5_task_browser_smoke_receipt_encode_failed",
            "Phase 5 specification length is not addressable",
        )
    })?;
    let build_disposition = if options.skip_build {
        "skipped_existing_delivery"
    } else if options.dry_run {
        "planned"
    } else {
        "executed"
    };
    let mut receipt = Phase5TaskBrowserSmokeReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "phase5_task_browser_smoke".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "passed" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        build_skipped: options.skip_build,
        build_disposition: build_disposition.to_owned(),
        frontend_build_receipt_hash: frontend_build.map(|build| build.receipt_hash.clone()),
        delivery_receipt_hash,
        specification: Phase5TaskBrowserSmokeSpecificationV1 {
            path: prepared.source.spec_path,
            byte_length,
            sha256: sha256_identity(&prepared.spec_bytes),
        },
        playwright_cli_sha256: execution.map(|browser| browser.playwright_cli_sha256.clone()),
        playwright_command: prepared.playwright_plan.logical_command,
        dist_directory: prepared.source.dist_directory,
        spa_fallback_entry: prepared.source.spa_fallback_entry,
        base_url_environment: prepared.source.base_url_environment,
        required_workflow_steps: prepared.source.required_workflow_steps,
        runtime_requirements: Phase5TaskBrowserSmokeRuntimeRequirementsV1 {
            node_required: true,
            browser_required: true,
        },
        loopback_listener_count: u64::from(executed),
        loopback_port: prepared.source.loopback_port,
        direct_processes_spawned,
        successful_exit_codes: exit_codes,
        request_error_count: execution.map_or(0, |browser| browser.request_error_count),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &Phase5TaskBrowserSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "phase5_task_browser_smoke_receipt_encode_failed",
            format!("project Phase 5 browser-smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "phase5_task_browser_smoke_receipt_encode_failed",
                "Phase 5 browser-smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "phase5_task_browser_smoke_receipt_encode_failed",
            format!("canonicalize Phase 5 browser-smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

#[cfg(test)]
mod tests {
    use super::{
        validate_phase5_task_browser_smoke_source, Phase5TaskBrowserSmokeSourceV1,
        EXPECTED_WORKFLOW_STEPS,
    };

    fn source() -> Phase5TaskBrowserSmokeSourceV1 {
        Phase5TaskBrowserSmokeSourceV1 {
            schema_version: "structural-native-phase5-task-browser-smoke-contract.v1".to_owned(),
            node_launcher: "node".to_owned(),
            playwright_cli_path: "node_modules/@playwright/test/cli.js".to_owned(),
            spec_path: "tests/frontend/developer-preview-workflow.spec.ts".to_owned(),
            dist_directory: "dist".to_owned(),
            spa_fallback_entry: "index.html".to_owned(),
            base_url_environment: "DEVELOPER_PREVIEW_BASE_URL".to_owned(),
            loopback_port: 4_173,
            required_workflow_steps: EXPECTED_WORKFLOW_STEPS
                .iter()
                .map(ToString::to_string)
                .collect(),
            external_network_access_accounting:
                "not_instrumented_frontend_build_and_browser_page_requests".to_owned(),
            claim_boundary: "bounded".to_owned(),
        }
    }

    #[test]
    fn source_contract_rejects_spec_port_and_workflow_widening() {
        assert!(validate_phase5_task_browser_smoke_source(&source()).is_ok());
        let mut drift = source();
        drift.loopback_port = 4_174;
        assert!(validate_phase5_task_browser_smoke_source(&drift).is_err());
        let mut drift = source();
        drift.required_workflow_steps.push("approve".to_owned());
        assert!(validate_phase5_task_browser_smoke_source(&drift).is_err());
    }
}
