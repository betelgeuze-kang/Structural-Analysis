use std::ffi::OsString;
use std::path::PathBuf;
use std::process::Command;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, parse_source_map, read_bounded_regular_file,
    resolve_required_file, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-dev-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-dev-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_VITE_CLI: &str = "node_modules/vite/bin/vite.js";
const EXPECTED_DEFAULT_HOST: &str = "127.0.0.1";
const EXPECTED_DEFAULT_PORT: u16 = 5_173;
const EXPECTED_MAXIMUM_CLI_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_vite_plugins_environment_hmr_and_page_requests";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendDevSourceV1 {
    schema_version: String,
    node_launcher: String,
    vite_cli_path: String,
    default_host: String,
    default_port: u16,
    strict_port: bool,
    maximum_cli_bytes: u64,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one frontend development-server plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendDevOptions {
    pub root: PathBuf,
    pub host: String,
    pub port: u16,
    pub dry_run: bool,
}

impl FrontendDevOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            host: EXPECTED_DEFAULT_HOST.to_owned(),
            port: EXPECTED_DEFAULT_PORT,
            dry_run: false,
        }
    }
}

/// Installed Vite CLI entrypoint identity used by a live development-server child.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendDevCliIdentityV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Retained runtime boundary for one frontend development-server execution.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendDevRuntimeRequirementsV1 {
    pub required: Vec<String>,
    pub browser_required: bool,
}

/// Canonical receipt for one planned or completed frontend development-server child.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendDevReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub vite_cli_identity: Option<FrontendDevCliIdentityV1>,
    pub logical_command: Vec<String>,
    pub host: String,
    pub port: u16,
    pub dev_url: String,
    pub loopback_only: bool,
    pub node_options_disposition: String,
    pub rust_owned_listener_count: u64,
    pub retained_listener_ownership: String,
    pub direct_processes_spawned: u64,
    pub successful_exit_code: Option<i32>,
    pub runtime_requirements: FrontendDevRuntimeRequirementsV1,
    pub source_mutation_policy: String,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendDev {
    source: FrontendDevSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
}

struct RuntimeCli {
    bytes: Vec<u8>,
}

/// Plan or run the retained Vite development server under Rust process ownership.
///
/// Source mutation after launch is intentionally allowed because it is the input to Vite HMR.
/// The receipt therefore binds the launch-time frontend contract and installed Vite CLI only and
/// never claims that the child became ready or that rendered browser behavior passed.
///
/// # Errors
///
/// Rejects frontend contract drift, non-loopback hosts, port zero, unsafe or oversized installed
/// CLI input, child launch failure, nonzero child exit, or receipt serialization failure.
pub fn run_frontend_dev(
    options: &FrontendDevOptions,
) -> Result<FrontendDevReceiptV1, FrontendContractError> {
    let prepared = prepare_frontend_dev(options)?;
    if options.dry_run {
        return build_receipt(prepared, options, None, None);
    }
    let runtime = load_runtime_cli(&prepared)?;
    verify_launch_inputs_unchanged(&prepared, &runtime)?;
    let exit_code = run_dev_child(&prepared, options)?;
    build_receipt(prepared, options, Some(&runtime), Some(exit_code))
}

/// Encode a frontend-dev receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_dev_receipt_json(
    receipt: &FrontendDevReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_dev_receipt_encode_failed")
}

fn prepare_frontend_dev(
    options: &FrontendDevOptions,
) -> Result<PreparedFrontendDev, FrontendContractError> {
    let source = parse_source_map()?.frontend_dev_contract;
    validate_endpoint(&source, &options.host, options.port)?;
    verify_real_directory(&options.root, "frontend dev root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_dev_root_invalid",
            format!("canonicalize frontend dev root failed: {error}"),
        )
    })?;
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    Ok(PreparedFrontendDev {
        source,
        root,
        frontend_contract_receipt_hash,
    })
}

fn load_runtime_cli(prepared: &PreparedFrontendDev) -> Result<RuntimeCli, FrontendContractError> {
    let path =
        resolve_required_file(&prepared.root, &prepared.source.vite_cli_path).map_err(|error| {
            FrontendContractError::new(
                "frontend_dev_runtime_invalid",
                format!("resolve installed Vite CLI failed: {error}"),
            )
        })?;
    let bytes = read_bounded_regular_file(
        &path,
        prepared.source.maximum_cli_bytes,
        "installed frontend dev Vite CLI",
    )
    .map_err(|error| {
        FrontendContractError::new(
            "frontend_dev_runtime_invalid",
            format!("read installed Vite CLI failed: {error}"),
        )
    })?;
    Ok(RuntimeCli { bytes })
}

fn verify_launch_inputs_unchanged(
    prepared: &PreparedFrontendDev,
    runtime: &RuntimeCli,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(FrontendContractError::new(
            "frontend_dev_contract_changed",
            "frontend package, lock, source map, or required inventory changed before launch",
        ));
    }
    if load_runtime_cli(prepared)?.bytes != runtime.bytes {
        return Err(FrontendContractError::new(
            "frontend_dev_runtime_changed",
            "installed Vite CLI entrypoint changed before launch",
        ));
    }
    Ok(())
}

fn run_dev_child(
    prepared: &PreparedFrontendDev,
    options: &FrontendDevOptions,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .args(logical_arguments(prepared, options))
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_dev_launch_failed",
                format!("launch frontend development server failed: {error}"),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_dev_terminated",
            "frontend development server terminated without an exit code",
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "frontend_dev_command_failed",
            format!("frontend development server failed with exit code {exit_code}"),
        ));
    }
    Ok(exit_code)
}

fn logical_arguments(prepared: &PreparedFrontendDev, options: &FrontendDevOptions) -> Vec<String> {
    vec![
        prepared.source.vite_cli_path.clone(),
        "--host".to_owned(),
        options.host.clone(),
        "--port".to_owned(),
        options.port.to_string(),
        "--strictPort".to_owned(),
    ]
}

fn node_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("node.exe")
    } else {
        OsString::from("node")
    }
}

fn validate_endpoint(
    source: &FrontendDevSourceV1,
    host: &str,
    port: u16,
) -> Result<(), FrontendContractError> {
    if host != source.default_host || host != EXPECTED_DEFAULT_HOST {
        return Err(FrontendContractError::new(
            "frontend_dev_host_forbidden",
            "frontend development host must be the frozen IPv4 loopback address 127.0.0.1",
        ));
    }
    if port == 0 {
        return Err(FrontendContractError::new(
            "frontend_dev_port_invalid",
            "frontend development port must be in 1..=65535",
        ));
    }
    Ok(())
}

pub(crate) fn validate_frontend_dev_source(
    source: &FrontendDevSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.vite_cli_path == EXPECTED_VITE_CLI
        && source.default_host == EXPECTED_DEFAULT_HOST
        && source.default_port == EXPECTED_DEFAULT_PORT
        && source.strict_port
        && source.maximum_cli_bytes == EXPECTED_MAXIMUM_CLI_BYTES
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend development-server contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedFrontendDev,
    options: &FrontendDevOptions,
    runtime: Option<&RuntimeCli>,
    exit_code: Option<i32>,
) -> Result<FrontendDevReceiptV1, FrontendContractError> {
    let executed = exit_code.is_some();
    let vite_cli_identity = runtime
        .map(|runtime| {
            Ok(FrontendDevCliIdentityV1 {
                path: prepared.source.vite_cli_path.clone(),
                byte_length: u64::try_from(runtime.bytes.len()).map_err(|_| {
                    receipt_error("frontend development CLI length is not addressable")
                })?,
                sha256: sha256_identity(&runtime.bytes),
            })
        })
        .transpose()?;
    let logical_command = std::iter::once("node".to_owned())
        .chain(logical_arguments(&prepared, options))
        .collect();
    let mut receipt = FrontendDevReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_dev".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "stopped" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        vite_cli_identity,
        logical_command,
        host: options.host.clone(),
        port: options.port,
        dev_url: format!("http://{}:{}/", options.host, options.port),
        loopback_only: true,
        node_options_disposition: "removed_for_direct_child".to_owned(),
        rust_owned_listener_count: 0,
        retained_listener_ownership: "vite_child_uninstrumented".to_owned(),
        direct_processes_spawned: u64::from(executed),
        successful_exit_code: exit_code,
        runtime_requirements: FrontendDevRuntimeRequirementsV1 {
            required: vec!["node".to_owned(), "vite".to_owned()],
            browser_required: false,
        },
        source_mutation_policy: "allowed_after_launch_for_hmr_not_revalidated".to_owned(),
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_dev_receipt_encode_failed", detail)
}

fn hash_without_receipt_hash(
    receipt: &FrontendDevReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!(
            "project frontend development receipt failed: {error}"
        ))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("frontend development receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize frontend development receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_dev_source, FrontendDevSourceV1};

    fn source() -> FrontendDevSourceV1 {
        FrontendDevSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            node_launcher: super::EXPECTED_NODE_LAUNCHER.to_owned(),
            vite_cli_path: super::EXPECTED_VITE_CLI.to_owned(),
            default_host: super::EXPECTED_DEFAULT_HOST.to_owned(),
            default_port: super::EXPECTED_DEFAULT_PORT,
            strict_port: true,
            maximum_cli_bytes: super::EXPECTED_MAXIMUM_CLI_BYTES,
            external_network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            claim_boundary: "bounded development child".to_owned(),
        }
    }

    #[test]
    fn dev_contract_rejects_remote_host_and_non_strict_port() {
        assert!(validate_frontend_dev_source(&source()).is_ok());

        let mut host = source();
        host.default_host = "0.0.0.0".to_owned();
        assert!(validate_frontend_dev_source(&host).is_err());

        let mut port = source();
        port.strict_port = false;
        assert!(validate_frontend_dev_source(&port).is_err());
    }
}
