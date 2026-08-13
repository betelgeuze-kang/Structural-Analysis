use std::convert::Infallible;
use std::io::Write;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_contracts::product_ir::sha256_identity;

use super::viewer_server::{handle_spa_stream, validate_spa_policy};
use super::{
    canonical_struct, check_frontend_contract, check_frontend_delivery, parse_source_map,
    resolve_required_directory, validate_relative_path, verify_real_directory,
    FrontendContractError, SOURCE_MAP_BYTES,
};

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-preview-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-preview-receipt.v1";
const EXPECTED_DEFAULT_HOST: &str = "127.0.0.1";
const EXPECTED_DEFAULT_PORT: u16 = 4_173;
const EXPECTED_DIST_DIRECTORY: &str = "dist";
const EXPECTED_FALLBACK_ENTRY: &str = "index.html";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendPreviewSourceV1 {
    schema_version: String,
    default_host: String,
    default_port: u16,
    dist_directory: String,
    spa_fallback_entry: String,
    claim_boundary: String,
}

/// Runtime dependencies for the frontend-preview execution mode.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendPreviewRuntimeRequirementsV1 {
    pub node_required: bool,
    pub browser_required: bool,
    pub loopback_listener_required: bool,
}

/// Canonical startup receipt for the Rust-owned production-delivery preview server.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendPreviewReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub delivery_receipt_hash: String,
    pub dist_directory: String,
    pub spa_fallback_entry: String,
    pub host: String,
    pub port: u16,
    pub preview_url: String,
    pub loopback_only: bool,
    pub listener_count: u64,
    pub direct_processes_spawned: u64,
    pub external_network_access_count: u64,
    pub runtime_requirements: FrontendPreviewRuntimeRequirementsV1,
    pub delivery_validated: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendPreview {
    source: FrontendPreviewSourceV1,
    dist: PathBuf,
    frontend_contract_receipt_hash: String,
    delivery_receipt_hash: String,
}

/// Build a deterministic, listener-free plan for the production-delivery preview server.
///
/// # Errors
///
/// Rejects frontend-contract or delivery drift, an unsafe delivery root, a non-loopback host,
/// port zero, or a malformed embedded preview contract.
pub fn plan_frontend_preview(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<FrontendPreviewReceiptV1, FrontendContractError> {
    let prepared = prepare_frontend_preview(root, host, port)?;
    build_receipt(prepared, host, port, true)
}

/// Bind one IPv4 loopback listener and serve the verified production delivery with SPA fallback.
///
/// A canonical startup receipt is written only after the listener is bound and the frontend
/// contract plus delivery hashes are rechecked. The normal lifetime ends through process
/// termination; listener, request, and response errors fail closed.
///
/// # Errors
///
/// Rejects invalid or changed inputs and returns stable I/O errors for bind, accept, read, or
/// write failures.
pub fn serve_frontend_preview(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<Infallible, FrontendContractError> {
    let prepared = prepare_frontend_preview(root, host, port)?;
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let listener = TcpListener::bind(address).map_err(|error| {
        FrontendContractError::new(
            "frontend_preview_bind_failed",
            format!("bind frontend preview loopback server failed: {error}"),
        )
    })?;
    verify_preview_inputs_unchanged(root, &prepared)?;
    let dist = prepared.dist.clone();
    let fallback_entry = prepared.source.spa_fallback_entry.clone();
    let receipt = build_receipt(prepared, host, port, false)?;
    let encoded = canonical_frontend_preview_receipt_json(&receipt)?;
    println!("{encoded}");
    std::io::stdout().flush().map_err(|error| {
        FrontendContractError::new(
            "frontend_preview_output_failed",
            format!("flush frontend preview startup receipt failed: {error}"),
        )
    })?;

    loop {
        let (stream, _) = listener.accept().map_err(|error| {
            FrontendContractError::new(
                "frontend_preview_accept_failed",
                format!("accept frontend preview loopback connection failed: {error}"),
            )
        })?;
        handle_spa_stream(&dist, &fallback_entry, stream)?;
    }
}

/// Encode a frontend-preview receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_preview_receipt_json(
    receipt: &FrontendPreviewReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_preview_receipt_encode_failed")
}

fn prepare_frontend_preview(
    root: &Path,
    host: &str,
    port: u16,
) -> Result<PreparedFrontendPreview, FrontendContractError> {
    verify_real_directory(root, "frontend preview root")?;
    let source = parse_source_map()?.frontend_preview_contract;
    validate_endpoint(&source, host, port)?;
    let root = root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_preview_root_invalid",
            format!("canonicalize frontend preview root failed: {error}"),
        )
    })?;
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    let delivery_receipt_hash = check_frontend_delivery(&root)?.receipt_hash;
    let dist = resolve_required_directory(&root, &source.dist_directory)?;
    Ok(PreparedFrontendPreview {
        source,
        dist,
        frontend_contract_receipt_hash,
        delivery_receipt_hash,
    })
}

fn verify_preview_inputs_unchanged(
    root: &Path,
    prepared: &PreparedFrontendPreview,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(root)?.receipt_hash != prepared.frontend_contract_receipt_hash
        || check_frontend_delivery(root)?.receipt_hash != prepared.delivery_receipt_hash
    {
        return Err(FrontendContractError::new(
            "frontend_preview_input_changed",
            "frontend package, source map, or delivery changed before preview publication",
        ));
    }
    Ok(())
}

fn validate_endpoint(
    source: &FrontendPreviewSourceV1,
    host: &str,
    port: u16,
) -> Result<(), FrontendContractError> {
    if host != source.default_host || host != EXPECTED_DEFAULT_HOST {
        return Err(FrontendContractError::new(
            "frontend_preview_host_forbidden",
            "frontend preview host must be the frozen IPv4 loopback address 127.0.0.1",
        ));
    }
    if port == 0 {
        return Err(FrontendContractError::new(
            "frontend_preview_port_invalid",
            "frontend preview port must be in 1..=65535",
        ));
    }
    Ok(())
}

pub(crate) fn validate_frontend_preview_source(
    source: &FrontendPreviewSourceV1,
) -> Result<(), FrontendContractError> {
    if source.schema_version != CONTRACT_SCHEMA_V1
        || source.default_host != EXPECTED_DEFAULT_HOST
        || source.default_port != EXPECTED_DEFAULT_PORT
        || source.dist_directory != EXPECTED_DIST_DIRECTORY
        || source.spa_fallback_entry != EXPECTED_FALLBACK_ENTRY
        || !valid_text(&source.claim_boundary)
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend preview contract is invalid",
        ));
    }
    validate_relative_path(&source.dist_directory)?;
    validate_spa_policy(&source.spa_fallback_entry)
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedFrontendPreview,
    host: &str,
    port: u16,
    dry_run: bool,
) -> Result<FrontendPreviewReceiptV1, FrontendContractError> {
    let mut receipt = FrontendPreviewReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_preview".to_owned(),
        execution_mode: if dry_run { "dry_run" } else { "serve" }.to_owned(),
        status: if dry_run { "planned" } else { "listening" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        delivery_receipt_hash: prepared.delivery_receipt_hash,
        dist_directory: prepared.source.dist_directory,
        spa_fallback_entry: prepared.source.spa_fallback_entry,
        host: host.to_owned(),
        port,
        preview_url: format!("http://{host}:{port}/"),
        loopback_only: true,
        listener_count: u64::from(!dry_run),
        direct_processes_spawned: 0,
        external_network_access_count: 0,
        runtime_requirements: FrontendPreviewRuntimeRequirementsV1 {
            node_required: false,
            browser_required: false,
            loopback_listener_required: !dry_run,
        },
        delivery_validated: true,
        claim_boundary: prepared.source.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &FrontendPreviewReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_preview_receipt_encode_failed",
            format!("project frontend preview receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_preview_receipt_encode_failed",
                "frontend preview receipt is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_preview_receipt_encode_failed",
            format!("canonicalize frontend preview receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_preview_source, FrontendPreviewSourceV1};

    fn source() -> FrontendPreviewSourceV1 {
        FrontendPreviewSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            default_host: super::EXPECTED_DEFAULT_HOST.to_owned(),
            default_port: super::EXPECTED_DEFAULT_PORT,
            dist_directory: super::EXPECTED_DIST_DIRECTORY.to_owned(),
            spa_fallback_entry: super::EXPECTED_FALLBACK_ENTRY.to_owned(),
            claim_boundary: "bounded preview server".to_owned(),
        }
    }

    #[test]
    fn preview_contract_rejects_widened_host_and_unsafe_fallback() {
        assert!(validate_frontend_preview_source(&source()).is_ok());

        let mut host = source();
        host.default_host = "0.0.0.0".to_owned();
        assert!(validate_frontend_preview_source(&host).is_err());

        let mut fallback = source();
        fallback.spa_fallback_entry = "../index.html".to_owned();
        assert!(validate_frontend_preview_source(&fallback).is_err());
    }
}
