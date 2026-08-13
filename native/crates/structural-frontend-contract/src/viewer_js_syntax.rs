use std::collections::BTreeSet;
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

const CONTRACT_SCHEMA_V1: &str = "structural-native-viewer-js-syntax-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-viewer-js-syntax-receipt.v1";
const EXPECTED_NODE_LAUNCHER: &str = "node";
const EXPECTED_MAXIMUM_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const EXPECTED_NETWORK_ACCOUNTING: &str = "none_syntax_check_only";
const EXPECTED_SYNTAX_PATHS: [&str; 10] = [
    "src/structure-viewer/viewer-force-diagram-overlay.js",
    "src/structure-viewer/viewer-contracts.js",
    "src/structure-viewer/viewer-ingest.js",
    "src/structure-viewer/viewer-renderer.js",
    "src/structure-viewer/viewer-report.js",
    "src/structure-viewer/viewer-shell.js",
    "src/structure-viewer/viewer-state.js",
    "src/structure-viewer/viewer-storage.js",
    "src/structure-viewer/viewer-runtime-ingest-payload-storage.js",
    "src/structure-viewer/viewer-story-analysis-panel.js",
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ViewerJsSyntaxSourceV1 {
    schema_version: String,
    node_launcher: String,
    syntax_paths: Vec<String>,
    maximum_source_bytes: u64,
    external_network_access_accounting: String,
    claim_boundary: String,
}

/// Inputs for one Viewer JavaScript syntax plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ViewerJsSyntaxOptions {
    pub root: PathBuf,
    pub dry_run: bool,
}

impl ViewerJsSyntaxOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
        }
    }
}

/// Frozen identity of one syntax-checked Viewer JavaScript source.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerJsSyntaxSourceIdentityV1 {
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Canonical receipt for one Viewer JavaScript syntax plan or execution.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ViewerJsSyntaxReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub execution_mode: String,
    pub status: String,
    pub source_map_sha256: String,
    pub frontend_contract_receipt_hash: String,
    pub source_identities: Vec<ViewerJsSyntaxSourceIdentityV1>,
    pub syntax_source_count: u64,
    pub node_launcher: String,
    pub logical_command_template: Vec<String>,
    pub node_runtime_required: bool,
    pub browser_runtime_required: bool,
    pub rust_owned_listener_count: u64,
    pub direct_processes_spawned: u64,
    pub successful_exit_codes: Vec<i32>,
    pub external_network_access_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedSyntaxCheck {
    source: ViewerJsSyntaxSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
    inputs: Vec<FrozenSyntaxInput>,
}

struct FrozenSyntaxInput {
    relative_path: String,
    bytes: Vec<u8>,
}

/// Plan or execute the frozen Viewer JavaScript syntax gate under Rust orchestration.
///
/// Rust owns input validation, source identities, direct child lifetimes, mutation checks, and the
/// canonical receipt. The retained Node `--check` parser and executable identity remain outside
/// Rust authority.
///
/// # Errors
///
/// Rejects source-map or frontend drift, missing or unsafe sources, a child launch or syntax
/// failure, source mutation during execution, or receipt serialization failure.
pub fn run_viewer_js_syntax(
    options: &ViewerJsSyntaxOptions,
) -> Result<ViewerJsSyntaxReceiptV1, FrontendContractError> {
    let prepared = prepare_syntax_check(options)?;
    if options.dry_run {
        return build_receipt(prepared, false, Vec::new());
    }

    let mut exit_codes = Vec::with_capacity(prepared.inputs.len());
    for input in &prepared.inputs {
        verify_execution_inputs_unchanged(&prepared)?;
        exit_codes.push(run_syntax_child(&prepared, input)?);
    }
    verify_execution_inputs_unchanged(&prepared)?;
    build_receipt(prepared, true, exit_codes)
}

/// Encode a Viewer JavaScript syntax receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_viewer_js_syntax_receipt_json(
    receipt: &ViewerJsSyntaxReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "viewer_js_syntax_receipt_encode_failed")
}

fn prepare_syntax_check(
    options: &ViewerJsSyntaxOptions,
) -> Result<PreparedSyntaxCheck, FrontendContractError> {
    verify_real_directory(&options.root, "Viewer JavaScript syntax root")?;
    let frontend_contract_receipt_hash = check_frontend_contract(&options.root)?.receipt_hash;
    let source = parse_source_map()?.viewer_js_syntax_contract;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "viewer_js_syntax_root_invalid",
            format!("canonicalize Viewer JavaScript syntax root failed: {error}"),
        )
    })?;
    let mut inputs = Vec::with_capacity(source.syntax_paths.len());
    for relative_path in &source.syntax_paths {
        let path = resolve_required_file(&root, relative_path)?;
        let bytes = read_bounded_regular_file(
            &path,
            source.maximum_source_bytes,
            "Viewer JavaScript syntax source",
        )?;
        inputs.push(FrozenSyntaxInput {
            relative_path: relative_path.clone(),
            bytes,
        });
    }
    Ok(PreparedSyntaxCheck {
        source,
        root,
        frontend_contract_receipt_hash,
        inputs,
    })
}

fn run_syntax_child(
    prepared: &PreparedSyntaxCheck,
    input: &FrozenSyntaxInput,
) -> Result<i32, FrontendContractError> {
    let status = Command::new(node_launcher())
        .arg("--check")
        .arg(&input.relative_path)
        .current_dir(&prepared.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "viewer_js_syntax_launch_failed",
                format!(
                    "launch Viewer JavaScript syntax check for {} failed: {error}",
                    input.relative_path
                ),
            )
        })?;
    let exit_code = status.code().ok_or_else(|| {
        FrontendContractError::new(
            "viewer_js_syntax_terminated",
            format!(
                "Viewer JavaScript syntax check for {} terminated without an exit code",
                input.relative_path
            ),
        )
    })?;
    if !status.success() {
        return Err(FrontendContractError::new(
            "viewer_js_syntax_failed",
            format!(
                "Viewer JavaScript syntax check for {} failed with exit code {exit_code}",
                input.relative_path
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
    prepared: &PreparedSyntaxCheck,
) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(syntax_contract_changed());
    }
    for input in &prepared.inputs {
        let path = resolve_required_file(&prepared.root, &input.relative_path)?;
        let bytes = read_bounded_regular_file(
            &path,
            prepared.source.maximum_source_bytes,
            "Viewer JavaScript syntax source",
        )?;
        if bytes != input.bytes {
            return Err(syntax_contract_changed());
        }
    }
    Ok(())
}

fn syntax_contract_changed() -> FrontendContractError {
    FrontendContractError::new(
        "viewer_js_syntax_contract_changed",
        "frontend package, lock, source map, or Viewer JavaScript changed during syntax execution",
    )
}

pub(crate) fn validate_viewer_js_syntax_source(
    source: &ViewerJsSyntaxSourceV1,
) -> Result<(), FrontendContractError> {
    let expected = EXPECTED_SYNTAX_PATHS.to_vec();
    let actual = source
        .syntax_paths
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let unique = actual.iter().copied().collect::<BTreeSet<_>>();
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.node_launcher == EXPECTED_NODE_LAUNCHER
        && actual == expected
        && unique.len() == expected.len()
        && source.maximum_source_bytes == EXPECTED_MAXIMUM_SOURCE_BYTES
        && source.external_network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "Viewer JavaScript syntax contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedSyntaxCheck,
    executed: bool,
    exit_codes: Vec<i32>,
) -> Result<ViewerJsSyntaxReceiptV1, FrontendContractError> {
    let source_identities = prepared
        .inputs
        .iter()
        .map(|input| {
            Ok(ViewerJsSyntaxSourceIdentityV1 {
                path: input.relative_path.clone(),
                byte_length: u64::try_from(input.bytes.len()).map_err(|_| {
                    receipt_error("Viewer JavaScript source length is not addressable")
                })?,
                sha256: sha256_identity(&input.bytes),
            })
        })
        .collect::<Result<Vec<_>, FrontendContractError>>()?;
    let syntax_source_count = u64::try_from(source_identities.len())
        .map_err(|_| receipt_error("Viewer JavaScript source count is not addressable"))?;
    let mut receipt = ViewerJsSyntaxReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "viewer_js_syntax".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: if executed { "verified" } else { "planned" }.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        source_identities,
        syntax_source_count,
        node_launcher: prepared.source.node_launcher,
        logical_command_template: vec![
            "node".to_owned(),
            "--check".to_owned(),
            "{syntax_source}".to_owned(),
        ],
        node_runtime_required: true,
        browser_runtime_required: false,
        rust_owned_listener_count: 0,
        direct_processes_spawned: if executed { syntax_source_count } else { 0 },
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
    FrontendContractError::new("viewer_js_syntax_receipt_encode_failed", detail.to_owned())
}

fn hash_without_receipt_hash(
    receipt: &ViewerJsSyntaxReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!(
            "project Viewer JavaScript syntax receipt failed: {error}"
        ))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("Viewer JavaScript syntax receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize Viewer JavaScript syntax receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_viewer_js_syntax_source, ViewerJsSyntaxSourceV1};

    fn source() -> ViewerJsSyntaxSourceV1 {
        ViewerJsSyntaxSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            node_launcher: "node".to_owned(),
            syntax_paths: super::EXPECTED_SYNTAX_PATHS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            maximum_source_bytes: super::EXPECTED_MAXIMUM_SOURCE_BYTES,
            external_network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            claim_boundary: "bounded Node syntax parser authority".to_owned(),
        }
    }

    #[test]
    fn source_contract_rejects_reordered_or_duplicate_paths() {
        let mut reordered = source();
        reordered.syntax_paths.swap(0, 1);
        assert!(validate_viewer_js_syntax_source(&reordered).is_err());

        let mut duplicate = source();
        duplicate.syntax_paths[1] = duplicate.syntax_paths[0].clone();
        assert!(validate_viewer_js_syntax_source(&duplicate).is_err());
        assert!(validate_viewer_js_syntax_source(&source()).is_ok());
    }
}
