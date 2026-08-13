use std::ffi::OsString;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, verify_real_directory,
    FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-install-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-install-receipt.v1";
const EXPECTED_NPM_LAUNCHER: &str = "npm";
const EXPECTED_ARGUMENTS: [&str; 1] = ["ci"];
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_npm_registry_cache_and_dependency_lifecycle_access";
const EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING: &str =
    "node_modules_replaced_by_npm_ci_package_and_lock_must_remain_unchanged";
const EXPECTED_ENVIRONMENT_ACCOUNTING: &str =
    "npm_executable_transitive_package_and_npm_configuration_identity_not_instrumented";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendInstallSourceV1 {
    schema_version: String,
    npm_launcher: String,
    arguments: Vec<String>,
    network_access_accounting: String,
    filesystem_mutation_accounting: String,
    environment_accounting: String,
    claim_boundary: String,
}

/// Inputs for one frontend dependency installation plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendInstallOptions {
    pub root: PathBuf,
    pub dry_run: bool,
}

impl FrontendInstallOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
        }
    }
}

/// Retained runtime boundary for one frontend dependency installation.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendInstallRuntimeRequirementsV1 {
    pub required: Vec<String>,
    pub node_modules_mutation_expected: bool,
}

/// Canonical receipt for one planned or completed frontend dependency installation.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendInstallReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub logical_command: Vec<String>,
    pub process_launcher: String,
    pub node_options_disposition: String,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub runtime_requirements: FrontendInstallRuntimeRequirementsV1,
    pub network_access_accounting: String,
    pub filesystem_mutation_accounting: String,
    pub environment_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendInstall {
    source: FrontendInstallSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
}

/// Plan or directly run the pinned `npm ci` dependency installation under Rust ownership.
///
/// # Errors
///
/// Rejects frontend contract drift, child launch or exit failure, package/lock/source-map mutation,
/// or receipt serialization failure.
pub fn run_frontend_install(
    options: &FrontendInstallOptions,
) -> Result<FrontendInstallReceiptV1, FrontendContractError> {
    let prepared = prepare_frontend_install(options)?;
    if options.dry_run {
        return build_receipt(prepared, None);
    }
    verify_inputs_unchanged(&prepared)?;
    let exit_code = run_install_child(&prepared)?;
    verify_inputs_unchanged(&prepared)?;
    build_receipt(prepared, Some(exit_code))
}

/// Encode a frontend-install receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_install_receipt_json(
    receipt: &FrontendInstallReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_install_receipt_encode_failed")
}

fn prepare_frontend_install(
    options: &FrontendInstallOptions,
) -> Result<PreparedFrontendInstall, FrontendContractError> {
    verify_real_directory(&options.root, "frontend install root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_install_root_invalid",
            format!("canonicalize frontend install root failed: {error}"),
        )
    })?;
    let source = parse_source_map()?.frontend_install_contract;
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    Ok(PreparedFrontendInstall {
        source,
        root,
        frontend_contract_receipt_hash,
    })
}

fn verify_inputs_unchanged(
    prepared: &PreparedFrontendInstall,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(FrontendContractError::new(
            "frontend_install_contract_changed",
            "frontend package, lock, source map, or required inventory changed during installation",
        ));
    }
    Ok(())
}

fn run_install_child(prepared: &PreparedFrontendInstall) -> Result<i32, FrontendContractError> {
    let status = Command::new(npm_launcher())
        .args(&prepared.source.arguments)
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .stdin(Stdio::null())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_install_launch_failed",
                format!("launch frontend dependency installation failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_install_terminated",
            "frontend dependency installation terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "frontend_install_command_failed",
            format!("frontend dependency installation failed with exit code {exit_code}"),
        ));
    }
    Ok(exit_code)
}

fn npm_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("npm.cmd")
    } else {
        OsString::from("npm")
    }
}

pub(crate) fn validate_frontend_install_source(
    source: &FrontendInstallSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.npm_launcher == EXPECTED_NPM_LAUNCHER
        && source.arguments == EXPECTED_ARGUMENTS
        && source.network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && source.filesystem_mutation_accounting == EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING
        && source.environment_accounting == EXPECTED_ENVIRONMENT_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend dependency installation contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedFrontendInstall,
    exit_code: Option<i32>,
) -> Result<FrontendInstallReceiptV1, FrontendContractError> {
    let executed = exit_code.is_some();
    let logical_command = std::iter::once("npm".to_owned())
        .chain(prepared.source.arguments.iter().cloned())
        .collect();
    let mut receipt = FrontendInstallReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_install".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "installed" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        logical_command,
        process_launcher: EXPECTED_NPM_LAUNCHER.to_owned(),
        node_options_disposition: "removed_for_direct_child".to_owned(),
        direct_processes_spawned: u64::from(executed),
        successful_exit_code: exit_code,
        runtime_requirements: FrontendInstallRuntimeRequirementsV1 {
            required: vec!["node".to_owned(), "npm".to_owned()],
            node_modules_mutation_expected: executed,
        },
        network_access_accounting: prepared.source.network_access_accounting,
        filesystem_mutation_accounting: prepared.source.filesystem_mutation_accounting,
        environment_accounting: prepared.source.environment_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_install_receipt_encode_failed", detail)
}

fn hash_without_receipt_hash(
    receipt: &FrontendInstallReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!("project frontend install receipt failed: {error}"))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("frontend install receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize frontend install receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_install_source, FrontendInstallSourceV1};

    fn source() -> FrontendInstallSourceV1 {
        FrontendInstallSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            npm_launcher: super::EXPECTED_NPM_LAUNCHER.to_owned(),
            arguments: super::EXPECTED_ARGUMENTS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            filesystem_mutation_accounting: super::EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING
                .to_owned(),
            environment_accounting: super::EXPECTED_ENVIRONMENT_ACCOUNTING.to_owned(),
            claim_boundary: "bounded frontend dependency install".to_owned(),
        }
    }

    #[test]
    fn install_contract_rejects_argument_and_launcher_widening() {
        assert!(validate_frontend_install_source(&source()).is_ok());

        let mut arguments = source();
        arguments.arguments.push("--force".to_owned());
        assert!(validate_frontend_install_source(&arguments).is_err());

        let mut launcher = source();
        launcher.npm_launcher = "npx".to_owned();
        assert!(validate_frontend_install_source(&launcher).is_err());
    }
}
