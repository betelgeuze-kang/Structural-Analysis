use std::ffi::OsString;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-playwright-install-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-playwright-install-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_PLAYWRIGHT_CLI: &str = "node_modules/@playwright/test/cli.js";
const EXPECTED_ARGUMENTS: [&str; 3] = ["install", "--with-deps", "chromium"];
const EXPECTED_MAXIMUM_CLI_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_playwright_browser_and_os_dependency_downloads";
const EXPECTED_SYSTEM_MUTATION_ACCOUNTING: &str =
    "retained_playwright_with_deps_may_mutate_host_packages_and_browser_cache";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PlaywrightInstallSourceV1 {
    schema_version: String,
    node_launcher: String,
    playwright_cli_path: String,
    arguments: Vec<String>,
    maximum_cli_bytes: u64,
    external_network_access_accounting: String,
    system_mutation_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Playwright Chromium installation plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlaywrightInstallOptions {
    pub root: PathBuf,
    pub dry_run: bool,
}

impl PlaywrightInstallOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
        }
    }
}

/// Installed Playwright CLI identity used by a live installation child.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PlaywrightInstallCliIdentityV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Retained runtime boundary for one Playwright installation execution.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PlaywrightInstallRuntimeRequirementsV1 {
    pub required: Vec<String>,
    pub browser_process_required: bool,
    pub elevated_host_package_mutation_may_be_required: bool,
}

/// Canonical receipt for one planned or completed Playwright Chromium installation.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PlaywrightInstallReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub playwright_cli_identity: Option<PlaywrightInstallCliIdentityV1>,
    pub logical_command: Vec<String>,
    pub node_options_disposition: String,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub runtime_requirements: PlaywrightInstallRuntimeRequirementsV1,
    pub external_network_access_accounting: String,
    pub system_mutation_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedPlaywrightInstall {
    source: PlaywrightInstallSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
}

struct RuntimeCli {
    bytes: Vec<u8>,
}

/// Plan or directly run the pinned Playwright Chromium installation under Rust ownership.
///
/// # Errors
///
/// Rejects frontend contract drift, unsafe or oversized installed CLI input, child launch or exit
/// failure, mutation of the package/source-map/CLI contract, or receipt serialization failure.
pub fn run_playwright_install(
    options: &PlaywrightInstallOptions,
) -> Result<PlaywrightInstallReceiptV1, FrontendContractError> {
    let prepared = prepare_playwright_install(options)?;
    if options.dry_run {
        return build_receipt(prepared, None, None);
    }
    let runtime = load_runtime_cli(&prepared)?;
    verify_inputs_unchanged(&prepared, &runtime)?;
    let exit_code = run_install_child(&prepared)?;
    verify_inputs_unchanged(&prepared, &runtime)?;
    build_receipt(prepared, Some(&runtime), Some(exit_code))
}

/// Encode a Playwright-install receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_playwright_install_receipt_json(
    receipt: &PlaywrightInstallReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "playwright_install_receipt_encode_failed")
}

fn prepare_playwright_install(
    options: &PlaywrightInstallOptions,
) -> Result<PreparedPlaywrightInstall, FrontendContractError> {
    verify_real_directory(&options.root, "Playwright install root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "playwright_install_root_invalid",
            format!("canonicalize Playwright install root failed: {error}"),
        )
    })?;
    let source = parse_source_map()?.playwright_install_contract;
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    Ok(PreparedPlaywrightInstall {
        source,
        root,
        frontend_contract_receipt_hash,
    })
}

fn load_runtime_cli(
    prepared: &PreparedPlaywrightInstall,
) -> Result<RuntimeCli, FrontendContractError> {
    let path = resolve_required_file(&prepared.root, &prepared.source.playwright_cli_path)
        .map_err(|error| {
            FrontendContractError::new(
                "playwright_install_runtime_invalid",
                format!("resolve installed Playwright CLI failed: {error}"),
            )
        })?;
    let bytes = read_bounded_regular_file(
        &path,
        prepared.source.maximum_cli_bytes,
        "installed Playwright install CLI",
    )
    .map_err(|error| {
        FrontendContractError::new(
            "playwright_install_runtime_invalid",
            format!("read installed Playwright CLI failed: {error}"),
        )
    })?;
    Ok(RuntimeCli { bytes })
}

fn verify_inputs_unchanged(
    prepared: &PreparedPlaywrightInstall,
    runtime: &RuntimeCli,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(FrontendContractError::new(
            "playwright_install_contract_changed",
            "frontend package, lock, source map, or required inventory changed during installation",
        ));
    }
    if load_runtime_cli(prepared)?.bytes != runtime.bytes {
        return Err(FrontendContractError::new(
            "playwright_install_runtime_changed",
            "installed Playwright CLI entrypoint changed during installation",
        ));
    }
    Ok(())
}

fn run_install_child(prepared: &PreparedPlaywrightInstall) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg(&prepared.source.playwright_cli_path)
        .args(&prepared.source.arguments)
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .stdin(Stdio::null())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "playwright_install_launch_failed",
                format!("launch Playwright Chromium installation failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "playwright_install_terminated",
            "Playwright Chromium installation terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "playwright_install_command_failed",
            format!("Playwright Chromium installation failed with exit code {exit_code}"),
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

pub(crate) fn validate_playwright_install_source(
    source: &PlaywrightInstallSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.playwright_cli_path == EXPECTED_PLAYWRIGHT_CLI
        && source.arguments == EXPECTED_ARGUMENTS
        && source.maximum_cli_bytes == EXPECTED_MAXIMUM_CLI_BYTES
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && source.system_mutation_accounting == EXPECTED_SYSTEM_MUTATION_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Playwright installation contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedPlaywrightInstall,
    runtime: Option<&RuntimeCli>,
    exit_code: Option<i32>,
) -> Result<PlaywrightInstallReceiptV1, FrontendContractError> {
    let executed = exit_code.is_some();
    let playwright_cli_identity = runtime
        .map(|runtime| {
            Ok(PlaywrightInstallCliIdentityV1 {
                path: prepared.source.playwright_cli_path.clone(),
                byte_length: u64::try_from(runtime.bytes.len())
                    .map_err(|_| receipt_error("Playwright CLI length is not addressable"))?,
                sha256: sha256_identity(&runtime.bytes),
            })
        })
        .transpose()?;
    let logical_command = std::iter::once("node".to_owned())
        .chain(std::iter::once(prepared.source.playwright_cli_path.clone()))
        .chain(prepared.source.arguments.iter().cloned())
        .collect();
    let mut receipt = PlaywrightInstallReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "playwright_install".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "installed" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        playwright_cli_identity,
        logical_command,
        node_options_disposition: "removed_for_direct_child".to_owned(),
        direct_processes_spawned: u64::from(executed),
        successful_exit_code: exit_code,
        runtime_requirements: PlaywrightInstallRuntimeRequirementsV1 {
            required: vec!["node".to_owned(), "playwright".to_owned()],
            browser_process_required: false,
            elevated_host_package_mutation_may_be_required: true,
        },
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        system_mutation_accounting: prepared.source.system_mutation_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("playwright_install_receipt_encode_failed", detail)
}

fn hash_without_receipt_hash(
    receipt: &PlaywrightInstallReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!(
            "project Playwright install receipt failed: {error}"
        ))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("Playwright install receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize Playwright install receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_playwright_install_source, PlaywrightInstallSourceV1};

    fn source() -> PlaywrightInstallSourceV1 {
        PlaywrightInstallSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            node_launcher: super::EXPECTED_NODE_LAUNCHER.to_owned(),
            playwright_cli_path: super::EXPECTED_PLAYWRIGHT_CLI.to_owned(),
            arguments: super::EXPECTED_ARGUMENTS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            maximum_cli_bytes: super::EXPECTED_MAXIMUM_CLI_BYTES,
            external_network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            system_mutation_accounting: super::EXPECTED_SYSTEM_MUTATION_ACCOUNTING.to_owned(),
            claim_boundary: "bounded Playwright install".to_owned(),
        }
    }

    #[test]
    fn install_contract_rejects_browser_and_argument_widening() {
        assert!(validate_playwright_install_source(&source()).is_ok());

        let mut browser = source();
        browser.arguments[2] = "firefox".to_owned();
        assert!(validate_playwright_install_source(&browser).is_err());

        let mut arguments = source();
        arguments.arguments.push("--force".to_owned());
        assert!(validate_playwright_install_source(&arguments).is_err());
    }
}
