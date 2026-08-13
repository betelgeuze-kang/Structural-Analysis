use std::ffi::OsString;
use std::path::Path;
use std::process::Command;

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, check_frontend_contract, check_frontend_delivery, parse_source_map,
    FrontendContractError, SOURCE_MAP_BYTES,
};

const SMOKE_CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-smoke-contract.v1";
const SMOKE_RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-smoke-receipt.v1";
const NETWORK_ACCOUNTING_BOUNDARY: &str = "not_instrumented_npm_ci_may_access_registry";
const MAX_COMMAND_PARTS: usize = 8;
const MAX_COMMAND_PART_BYTES: usize = 256;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendSmokeSourceV1 {
    schema_version: String,
    install_command: Vec<String>,
    build_command: Vec<String>,
    network_access_accounting: String,
    claim_boundary: String,
}

/// One canonical result from the native frontend build-smoke orchestrator.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendSmokeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub contract_receipt_hash: String,
    pub delivery_receipt_hash: Option<String>,
    pub logical_commands: Vec<Vec<String>>,
    pub process_launcher: String,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Validate the pinned frontend contract and optionally execute its clean build smoke.
///
/// In dry-run mode this executes no child process and does not require a built delivery tree. In
/// execution mode Rust directly owns the two child-process boundaries, stops on the first failure,
/// and verifies the completed delivery tree before publishing a receipt.
///
/// # Errors
///
/// Rejects frontend contract drift, malformed embedded smoke metadata, a child-process launch or
/// nonzero exit, and any post-build delivery-contract failure.
pub fn run_frontend_smoke(
    root: &Path,
    dry_run: bool,
) -> Result<FrontendSmokeReceiptV1, FrontendContractError> {
    let contract_receipt = check_frontend_contract(root)?;
    let source_map = parse_source_map()?;
    let smoke = &source_map.smoke_contract;
    let logical_commands = vec![smoke.install_command.clone(), smoke.build_command.clone()];
    let launcher = npm_launcher();

    let mut successful_exit_codes = Vec::new();
    let delivery_receipt_hash = if dry_run {
        None
    } else {
        let working_root = root.canonicalize().map_err(|error| {
            FrontendContractError::new(
                "frontend_smoke_root_invalid",
                format!("canonicalize frontend smoke root failed: {error}"),
            )
        })?;
        for (index, logical_command) in logical_commands.iter().enumerate() {
            successful_exit_codes.push(run_command(
                &working_root,
                &launcher,
                logical_command,
                index,
            )?);
        }
        let post_contract = check_frontend_contract(&working_root)?;
        if post_contract.receipt_hash != contract_receipt.receipt_hash {
            return Err(FrontendContractError::new(
                "frontend_smoke_contract_changed",
                "frontend package or lock contract changed while the smoke sequence executed",
            ));
        }
        Some(check_frontend_delivery(&working_root)?.receipt_hash)
    };

    let mut receipt = FrontendSmokeReceiptV1 {
        schema_version: SMOKE_RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_smoke".to_owned(),
        mode: if dry_run { "dry_run" } else { "execute" }.to_owned(),
        status: if dry_run { "planned" } else { "ready" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        contract_receipt_hash: contract_receipt.receipt_hash,
        delivery_receipt_hash,
        logical_commands,
        process_launcher: launcher.to_string_lossy().into_owned(),
        direct_processes_spawned: u64::try_from(successful_exit_codes.len()).map_err(|_| {
            FrontendContractError::new(
                "frontend_smoke_receipt_encode_failed",
                "frontend smoke process count is not addressable",
            )
        })?,
        successful_exit_codes,
        network_access_accounting: smoke.network_access_accounting.clone(),
        deterministic_receipt: true,
        claim_boundary: smoke.claim_boundary.clone(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a frontend-smoke receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_smoke_receipt_json(
    receipt: &FrontendSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_smoke_receipt_encode_failed")
}

pub(crate) fn validate_frontend_smoke_source(
    source: &FrontendSmokeSourceV1,
) -> Result<(), FrontendContractError> {
    let expected_install = ["npm", "ci"];
    let expected_build = ["npm", "run", "build"];
    if source.schema_version != SMOKE_CONTRACT_SCHEMA_V1
        || source.network_access_accounting != NETWORK_ACCOUNTING_BOUNDARY
        || !valid_command(&source.install_command, &expected_install)
        || !valid_command(&source.build_command, &expected_build)
        || source.claim_boundary.trim().is_empty()
        || source.claim_boundary.len() > 16 * 1024
        || source.claim_boundary.chars().any(char::is_control)
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend smoke contract is invalid",
        ));
    }
    Ok(())
}

fn valid_command(command: &[String], expected: &[&str]) -> bool {
    command.len() <= MAX_COMMAND_PARTS
        && command
            .iter()
            .map(String::as_str)
            .eq(expected.iter().copied())
        && command.iter().all(|part| {
            !part.is_empty()
                && part.len() <= MAX_COMMAND_PART_BYTES
                && !part.chars().any(char::is_control)
        })
}

fn npm_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("npm.cmd")
    } else {
        OsString::from("npm")
    }
}

fn run_command(
    root: &Path,
    launcher: &OsString,
    logical_command: &[String],
    index: usize,
) -> Result<i32, FrontendContractError> {
    let arguments = logical_command.get(1..).ok_or_else(|| {
        FrontendContractError::new(
            "frontend_smoke_command_invalid",
            "frontend smoke command has no argument boundary",
        )
    })?;
    let status = Command::new(launcher)
        .args(arguments)
        .current_dir(root)
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_smoke_command_launch_failed",
                format!(
                    "launch frontend smoke command {} failed: {error}",
                    index + 1
                ),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_smoke_command_terminated",
            format!(
                "frontend smoke command {} terminated without an exit code",
                index + 1
            ),
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "frontend_smoke_command_failed",
            format!(
                "frontend smoke command {} failed with exit code {exit_code}",
                index + 1
            ),
        ));
    }
    Ok(exit_code)
}

fn hash_without_receipt_hash(
    receipt: &FrontendSmokeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_smoke_receipt_encode_failed",
            format!("project frontend smoke receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_smoke_receipt_encode_failed",
                "frontend smoke receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_smoke_receipt_encode_failed",
            format!("canonicalize frontend smoke receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_smoke_source, FrontendSmokeSourceV1};

    #[test]
    fn smoke_source_accepts_only_the_frozen_process_sequence() {
        let source = FrontendSmokeSourceV1 {
            schema_version: "structural-native-frontend-smoke-contract.v1".to_owned(),
            install_command: vec!["npm".to_owned(), "ci".to_owned()],
            build_command: vec!["npm".to_owned(), "run".to_owned(), "build".to_owned()],
            network_access_accounting: "not_instrumented_npm_ci_may_access_registry".to_owned(),
            claim_boundary: "bounded".to_owned(),
        };
        assert!(validate_frontend_smoke_source(&source).is_ok());

        let mut drift = source;
        drift.build_command = vec!["sh".to_owned(), "-c".to_owned(), "build".to_owned()];
        assert!(validate_frontend_smoke_source(&drift).is_err());
    }
}
