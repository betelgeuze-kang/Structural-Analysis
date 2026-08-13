use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, check_frontend_delivery, parse_source_map,
    read_bounded_regular_file, resolve_required_directory, resolve_required_file,
    verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-build-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-build-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_TYPESCRIPT_CLI: &str = "node_modules/typescript/bin/tsc";
const EXPECTED_VITE_CLI: &str = "node_modules/vite/bin/vite.js";
const EXPECTED_MAXIMUM_SOURCE_FILES: u64 = 4_096;
const EXPECTED_MAXIMUM_SOURCE_BYTES: u64 = 32 * 1024 * 1024;
const EXPECTED_MAXIMUM_TOTAL_SOURCE_BYTES: u64 = 256 * 1024 * 1024;
const EXPECTED_MAXIMUM_CLI_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_vite_plugins_transitive_runtime_and_environment";
const MAX_DIRECTORY_DEPTH: usize = 32;
const MAX_ENVIRONMENT_BYTES: usize = 4_096;
const EXPECTED_SOURCE_FILES: [&str; 7] = [
    "index.html",
    "tsconfig.json",
    "vite.config.ts",
    "src/main.tsx",
    "src/App.tsx",
    "src/index.css",
    "src/vite-env.d.ts",
];
const EXPECTED_SOURCE_DIRECTORIES: [&str; 3] =
    ["src/workbench", "src/workbench-v2", "src/structure-viewer"];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendBuildSourceV1 {
    schema_version: String,
    node_launcher: String,
    typescript_cli_path: String,
    typescript_arguments: Vec<String>,
    vite_cli_path: String,
    vite_arguments: Vec<String>,
    source_files: Vec<String>,
    source_directories: Vec<String>,
    maximum_source_files: u64,
    maximum_source_bytes: u64,
    maximum_total_source_bytes: u64,
    maximum_cli_bytes: u64,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one frontend build plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendBuildOptions {
    pub root: PathBuf,
    pub dry_run: bool,
}

impl FrontendBuildOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
        }
    }
}

/// Frozen identity for one frontend build source.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendBuildSourceIdentityV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Installed CLI entrypoint identity used by one live frontend build.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendBuildCliIdentityV1 {
    pub label: String,
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Retained runtime boundary for one frontend build.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendBuildRuntimeRequirementsV1 {
    pub required: Vec<String>,
    pub browser_required: bool,
}

/// Canonical receipt for one planned or completed frontend build.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendBuildReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub source_identities: Vec<FrontendBuildSourceIdentityV1>,
    pub source_inventory_sha256: String,
    pub source_file_count: u64,
    pub source_total_bytes: u64,
    pub installed_cli_identities: Vec<FrontendBuildCliIdentityV1>,
    pub installed_cli_entrypoint_hashes_present: bool,
    pub logical_commands: Vec<Vec<String>>,
    pub node_launcher: String,
    pub node_options_disposition: String,
    pub vite_base_path: Option<String>,
    pub delivery_receipt_hash: Option<String>,
    pub runtime_requirements: FrontendBuildRuntimeRequirementsV1,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendBuild {
    source: FrontendBuildSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    source_inputs: Vec<FrozenInput>,
    vite_base_path: Option<String>,
}

#[derive(Clone)]
struct FrozenInput {
    relative_path: String,
    bytes: Vec<u8>,
}

struct RuntimeCli {
    label: &'static str,
    relative_path: String,
    bytes: Vec<u8>,
}

/// Plan or execute the pinned TypeScript/Vite build under Rust orchestration.
///
/// Rust owns the bounded source and installed CLI-entrypoint identities, removes inherited
/// `NODE_OPTIONS`, owns the two direct Node children, rejects input mutation, and verifies the
/// resulting delivery tree. Node, transitive npm packages, TypeScript and Vite execution remain
/// retained transitional dependencies.
///
/// # Errors
///
/// Rejects frontend contract drift, unsafe or oversized sources, unsafe installed CLI paths,
/// invalid environment input, child launch or build failure, input mutation, delivery-contract
/// failure, or receipt serialization failure.
pub fn run_frontend_build(
    options: &FrontendBuildOptions,
) -> Result<FrontendBuildReceiptV1, FrontendContractError> {
    let prepared = prepare_frontend_build(options)?;
    if options.dry_run {
        return build_receipt(prepared, &[], Vec::new(), None);
    }

    let runtime = load_runtime_cli(&prepared)?;
    let mut exit_codes = Vec::with_capacity(runtime.len());
    for (index, cli) in runtime.iter().enumerate() {
        verify_execution_inputs_unchanged(&prepared, &runtime)?;
        exit_codes.push(run_build_child(&prepared, cli, index)?);
    }
    verify_execution_inputs_unchanged(&prepared, &runtime)?;
    let delivery_receipt_hash = check_frontend_delivery(&prepared.root)?.receipt_hash;
    verify_execution_inputs_unchanged(&prepared, &runtime)?;
    build_receipt(prepared, &runtime, exit_codes, Some(delivery_receipt_hash))
}

/// Encode a frontend-build receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_build_receipt_json(
    receipt: &FrontendBuildReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_build_receipt_encode_failed")
}

fn prepare_frontend_build(
    options: &FrontendBuildOptions,
) -> Result<PreparedFrontendBuild, FrontendContractError> {
    verify_real_directory(&options.root, "frontend build root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.frontend_build_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_build_root_invalid",
            format!("canonicalize frontend build root failed: {error}"),
        )
    })?;
    let source_inputs = load_source_inventory(&root, &source)?;
    let vite_base_path = optional_environment_utf8("VITE_BASE_PATH")?;
    if vite_base_path.as_ref().is_some_and(|value| {
        value.is_empty()
            || value.len() > MAX_ENVIRONMENT_BYTES
            || value.chars().any(char::is_control)
    }) {
        return Err(FrontendContractError::new(
            "frontend_build_environment_invalid",
            "VITE_BASE_PATH must be bounded printable UTF-8 when present",
        ));
    }
    Ok(PreparedFrontendBuild {
        source,
        root,
        frontend_contract_receipt_hash,
        source_inputs,
        vite_base_path,
    })
}

fn load_source_inventory(
    root: &Path,
    source: &FrontendBuildSourceV1,
) -> Result<Vec<FrozenInput>, FrontendContractError> {
    let mut inputs = Vec::new();
    let mut total_bytes = 0_u64;
    for relative in &source.source_files {
        let path = resolve_required_file(root, relative)?;
        push_source(root, &path, source, &mut inputs, &mut total_bytes)?;
    }
    for relative in &source.source_directories {
        let path = resolve_required_directory(root, relative)?;
        collect_source_directory(root, &path, source, 0, &mut inputs, &mut total_bytes)?;
    }
    inputs.sort_by(|left, right| left.relative_path.cmp(&right.relative_path));
    if inputs.is_empty()
        || u64::try_from(inputs.len()).unwrap_or(u64::MAX) > source.maximum_source_files
        || inputs
            .windows(2)
            .any(|rows| rows[0].relative_path == rows[1].relative_path)
    {
        return Err(FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source inventory is empty, duplicate, or excessive",
        ));
    }
    Ok(inputs)
}

fn collect_source_directory(
    root: &Path,
    directory: &Path,
    source: &FrontendBuildSourceV1,
    depth: usize,
    inputs: &mut Vec<FrozenInput>,
    total_bytes: &mut u64,
) -> Result<(), FrontendContractError> {
    if depth > MAX_DIRECTORY_DEPTH {
        return Err(FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source directory depth exceeds its bound",
        ));
    }
    verify_real_directory(directory, "frontend build source directory")?;
    let mut entries = fs::read_dir(directory)
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                format!("read frontend build source directory failed: {error}"),
            )
        })?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                format!("enumerate frontend build source directory failed: {error}"),
            )
        })?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                format!("inspect frontend build source entry failed: {error}"),
            )
        })?;
        if metadata.file_type().is_symlink() {
            return Err(FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                "frontend build source inventory may not traverse symlinks",
            ));
        }
        if metadata.is_dir() {
            collect_source_directory(root, &path, source, depth + 1, inputs, total_bytes)?;
        } else if metadata.is_file() {
            push_source(root, &path, source, inputs, total_bytes)?;
        } else {
            return Err(FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                "frontend build source inventory contains a special file",
            ));
        }
    }
    Ok(())
}

fn push_source(
    root: &Path,
    path: &Path,
    source: &FrontendBuildSourceV1,
    inputs: &mut Vec<FrozenInput>,
    total_bytes: &mut u64,
) -> Result<(), FrontendContractError> {
    if u64::try_from(inputs.len()).unwrap_or(u64::MAX) >= source.maximum_source_files {
        return Err(FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source file count exceeds its bound",
        ));
    }
    let relative_path = portable_relative_path(root, path)?;
    let bytes =
        read_bounded_regular_file(path, source.maximum_source_bytes, "frontend build source")?;
    let byte_length = u64::try_from(bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source length is not addressable",
        )
    })?;
    *total_bytes = total_bytes.checked_add(byte_length).ok_or_else(|| {
        FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source byte total overflowed",
        )
    })?;
    if *total_bytes > source.maximum_total_source_bytes {
        return Err(FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source byte total exceeds its bound",
        ));
    }
    inputs.push(FrozenInput {
        relative_path,
        bytes,
    });
    Ok(())
}

fn portable_relative_path(root: &Path, path: &Path) -> Result<String, FrontendContractError> {
    let relative = path.strip_prefix(root).map_err(|_| {
        FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source escaped its root",
        )
    })?;
    let mut segments = Vec::new();
    for component in relative.components() {
        let Component::Normal(segment) = component else {
            return Err(FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                "frontend build source path is not portable",
            ));
        };
        segments.push(segment.to_str().ok_or_else(|| {
            FrontendContractError::new(
                "frontend_build_source_inventory_invalid",
                "frontend build source path must be UTF-8",
            )
        })?);
    }
    if segments.is_empty() {
        return Err(FrontendContractError::new(
            "frontend_build_source_inventory_invalid",
            "frontend build source path is empty",
        ));
    }
    Ok(segments.join("/"))
}

fn load_runtime_cli(
    prepared: &PreparedFrontendBuild,
) -> Result<Vec<RuntimeCli>, FrontendContractError> {
    [
        ("typescript", prepared.source.typescript_cli_path.as_str()),
        ("vite", prepared.source.vite_cli_path.as_str()),
    ]
    .into_iter()
    .map(|(label, relative_path)| {
        let path = resolve_required_file(&prepared.root, relative_path).map_err(|error| {
            FrontendContractError::new(
                "frontend_build_runtime_invalid",
                format!("resolve installed {label} CLI failed: {error}"),
            )
        })?;
        let bytes = read_bounded_regular_file(
            &path,
            prepared.source.maximum_cli_bytes,
            "installed frontend build CLI",
        )
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_build_runtime_invalid",
                format!("read installed {label} CLI failed: {error}"),
            )
        })?;
        Ok(RuntimeCli {
            label,
            relative_path: relative_path.to_owned(),
            bytes,
        })
    })
    .collect()
}

fn run_build_child(
    prepared: &PreparedFrontendBuild,
    cli: &RuntimeCli,
    index: usize,
) -> Result<i32, FrontendContractError> {
    let arguments = if cli.label == "typescript" {
        &prepared.source.typescript_arguments
    } else {
        &prepared.source.vite_arguments
    };
    let status = Command::new(node_launcher())
        .arg(&cli.relative_path)
        .args(arguments)
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_build_launch_failed",
                format!(
                    "launch frontend build command {} failed: {error}",
                    index + 1
                ),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_build_terminated",
            format!(
                "frontend build command {} terminated without an exit code",
                index + 1
            ),
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "frontend_build_command_failed",
            format!(
                "frontend build command {} failed with exit code {exit_code}",
                index + 1
            ),
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
    prepared: &PreparedFrontendBuild,
    runtime: &[RuntimeCli],
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
        || load_source_inventory(&prepared.root, &prepared.source)?
            .iter()
            .map(|input| (&input.relative_path, &input.bytes))
            .ne(prepared
                .source_inputs
                .iter()
                .map(|input| (&input.relative_path, &input.bytes)))
    {
        return Err(FrontendContractError::new(
            "frontend_build_source_changed",
            "frontend package, lock, source map, or build source changed during execution",
        ));
    }
    let current_runtime = load_runtime_cli(prepared)?;
    if current_runtime
        .iter()
        .map(|cli| (&cli.label, &cli.relative_path, &cli.bytes))
        .ne(runtime
            .iter()
            .map(|cli| (&cli.label, &cli.relative_path, &cli.bytes)))
    {
        return Err(FrontendContractError::new(
            "frontend_build_runtime_changed",
            "installed TypeScript or Vite CLI entrypoint changed during build",
        ));
    }
    Ok(())
}

fn optional_environment_utf8(name: &str) -> Result<Option<String>, FrontendContractError> {
    std::env::var_os(name)
        .map(|value| {
            value.into_string().map_err(|_| {
                FrontendContractError::new(
                    "frontend_build_environment_invalid",
                    format!("{name} must be UTF-8"),
                )
            })
        })
        .transpose()
}

pub(crate) fn validate_frontend_build_source(
    source: &FrontendBuildSourceV1,
) -> Result<(), FrontendContractError> {
    let source_files = source
        .source_files
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let source_directories = source
        .source_directories
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && source.typescript_cli_path == EXPECTED_TYPESCRIPT_CLI
        && source.typescript_arguments == ["--noEmit"]
        && source.vite_cli_path == EXPECTED_VITE_CLI
        && source.vite_arguments == ["build"]
        && source_files == EXPECTED_SOURCE_FILES
        && source_directories == EXPECTED_SOURCE_DIRECTORIES
        && source_files.iter().copied().collect::<BTreeSet<_>>().len()
            == EXPECTED_SOURCE_FILES.len()
        && source_directories
            .iter()
            .copied()
            .collect::<BTreeSet<_>>()
            .len()
            == EXPECTED_SOURCE_DIRECTORIES.len()
        && source.maximum_source_files == EXPECTED_MAXIMUM_SOURCE_FILES
        && source.maximum_source_bytes == EXPECTED_MAXIMUM_SOURCE_BYTES
        && source.maximum_total_source_bytes == EXPECTED_MAXIMUM_TOTAL_SOURCE_BYTES
        && source.maximum_cli_bytes == EXPECTED_MAXIMUM_CLI_BYTES
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend build contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedFrontendBuild,
    runtime: &[RuntimeCli],
    exit_codes: Vec<i32>,
    delivery_receipt_hash: Option<String>,
) -> Result<FrontendBuildReceiptV1, FrontendContractError> {
    let executed = delivery_receipt_hash.is_some();
    let source_identities = prepared
        .source_inputs
        .iter()
        .map(|input| {
            Ok(FrontendBuildSourceIdentityV1 {
                path: input.relative_path.clone(),
                byte_length: u64::try_from(input.bytes.len())
                    .map_err(|_| receipt_error("frontend source length is not addressable"))?,
                sha256: sha256_identity(&input.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let source_inventory_json =
        canonical_struct(&source_identities, "frontend_build_receipt_encode_failed")?;
    let source_file_count = u64::try_from(source_identities.len())
        .map_err(|_| receipt_error("frontend source count is not addressable"))?;
    let source_total_bytes = source_identities.iter().try_fold(0_u64, |total, input| {
        total
            .checked_add(input.byte_length)
            .ok_or_else(|| receipt_error("frontend source byte total overflowed"))
    })?;
    let installed_cli_identities = runtime
        .iter()
        .map(|cli| {
            Ok(FrontendBuildCliIdentityV1 {
                label: cli.label.to_owned(),
                path: cli.relative_path.clone(),
                byte_length: u64::try_from(cli.bytes.len())
                    .map_err(|_| receipt_error("frontend CLI length is not addressable"))?,
                sha256: sha256_identity(&cli.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let mut receipt = FrontendBuildReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_build".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "ready" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        source_identities,
        source_inventory_sha256: sha256_identity(source_inventory_json.as_bytes()),
        source_file_count,
        source_total_bytes,
        installed_cli_entrypoint_hashes_present: executed && installed_cli_identities.len() == 2,
        installed_cli_identities,
        logical_commands: vec![
            std::iter::once("node".to_owned())
                .chain(std::iter::once(prepared.source.typescript_cli_path))
                .chain(prepared.source.typescript_arguments)
                .collect(),
            std::iter::once("node".to_owned())
                .chain(std::iter::once(prepared.source.vite_cli_path))
                .chain(prepared.source.vite_arguments)
                .collect(),
        ],
        node_launcher: node_launcher().to_string_lossy().into_owned(),
        node_options_disposition: "removed_for_direct_children".to_owned(),
        vite_base_path: prepared.vite_base_path,
        delivery_receipt_hash,
        runtime_requirements: FrontendBuildRuntimeRequirementsV1 {
            required: vec![
                "node".to_owned(),
                "typescript".to_owned(),
                "vite".to_owned(),
            ],
            browser_required: false,
        },
        rust_owned_listener_count: 0,
        direct_processes_spawned: u64::try_from(exit_codes.len())
            .map_err(|_| receipt_error("frontend build process count is not addressable"))?,
        successful_exit_codes: exit_codes,
        external_network_access_accounting: prepared.source.external_network_access_accounting,
        deterministic_receipt: !executed,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn receipt_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_build_receipt_encode_failed", detail.to_owned())
}

fn hash_without_receipt_hash(
    receipt: &FrontendBuildReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!("project frontend build receipt failed: {error}"))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("frontend build receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize frontend build receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_build_source, FrontendBuildSourceV1};

    fn source() -> FrontendBuildSourceV1 {
        FrontendBuildSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            node_launcher: "node".to_owned(),
            typescript_cli_path: super::EXPECTED_TYPESCRIPT_CLI.to_owned(),
            typescript_arguments: vec!["--noEmit".to_owned()],
            vite_cli_path: super::EXPECTED_VITE_CLI.to_owned(),
            vite_arguments: vec!["build".to_owned()],
            source_files: super::EXPECTED_SOURCE_FILES
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            source_directories: super::EXPECTED_SOURCE_DIRECTORIES
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            maximum_source_files: super::EXPECTED_MAXIMUM_SOURCE_FILES,
            maximum_source_bytes: super::EXPECTED_MAXIMUM_SOURCE_BYTES,
            maximum_total_source_bytes: super::EXPECTED_MAXIMUM_TOTAL_SOURCE_BYTES,
            maximum_cli_bytes: super::EXPECTED_MAXIMUM_CLI_BYTES,
            external_network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            claim_boundary: "bounded build orchestration".to_owned(),
        }
    }

    #[test]
    fn build_source_contract_rejects_command_and_inventory_widening() {
        assert!(validate_frontend_build_source(&source()).is_ok());

        let mut command = source();
        command.vite_arguments.push("--host".to_owned());
        assert!(validate_frontend_build_source(&command).is_err());

        let mut inventory = source();
        inventory.source_directories.push(".".to_owned());
        assert!(validate_frontend_build_source(&inventory).is_err());
    }
}
