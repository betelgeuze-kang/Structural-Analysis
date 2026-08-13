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

const CONTRACT_SCHEMA_V1: &str = "structural-native-frontend-audit-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-audit-receipt.v1";
const EXPECTED_NPM_LAUNCHER: &str = "npm";
const EXPECTED_ARGUMENTS: [&str; 3] = ["audit", "--audit-level", "high"];
const EXPECTED_WORKFLOW_FAILURE_POLICY: &str = "record_numeric_nonzero_without_failing_workflow";
const EXPECTED_FINDINGS_INTERPRETATION: &str =
    "nonzero_not_classified_as_vulnerability_network_or_tool_failure";
const EXPECTED_NETWORK_ACCOUNTING: &str =
    "not_instrumented_npm_registry_advisory_service_and_cache_access";
const EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING: &str =
    "repository_contract_must_remain_unchanged_external_cache_mutation_not_instrumented";
const EXPECTED_ENVIRONMENT_ACCOUNTING: &str =
    "npm_executable_configuration_registry_response_and_transitive_process_identity_not_instrumented";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FrontendAuditSourceV1 {
    schema_version: String,
    npm_launcher: String,
    arguments: Vec<String>,
    workflow_failure_policy: String,
    findings_interpretation: String,
    network_access_accounting: String,
    filesystem_mutation_accounting: String,
    environment_accounting: String,
    claim_boundary: String,
}

/// Inputs for one frontend dependency-audit plan or execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendAuditOptions {
    pub root: PathBuf,
    pub dry_run: bool,
}

impl FrontendAuditOptions {
    #[must_use]
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            dry_run: false,
        }
    }
}

/// Retained runtime boundary for one frontend dependency audit.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditRuntimeRequirementsV1 {
    pub required: Vec<String>,
    pub browser_required: bool,
    pub repository_contract_mutation_allowed: bool,
}

/// Canonical receipt for one planned or completed frontend dependency audit.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendAuditReceiptV1 {
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
    pub observed_exit_code: Option<i32>,
    pub workflow_failure_policy: String,
    pub findings_interpretation: String,
    pub runtime_requirements: FrontendAuditRuntimeRequirementsV1,
    pub network_access_accounting: String,
    pub filesystem_mutation_accounting: String,
    pub environment_accounting: String,
    pub deterministic_receipt: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

struct PreparedFrontendAudit {
    source: FrontendAuditSourceV1,
    root: PathBuf,
    frontend_contract_receipt_hash: String,
}

/// Plan or directly run the fixed non-blocking `npm audit --audit-level high` child.
///
/// A numeric nonzero child exit is recorded in the receipt and deliberately does not make this
/// function fail. The contract cannot distinguish an advisory from registry, network, or npm
/// failure without taking ownership of npm's output schema.
///
/// # Errors
///
/// Rejects frontend contract drift, child launch or signal termination, package/lock/source-map
/// mutation, or receipt serialization failure.
pub fn run_frontend_audit(
    options: &FrontendAuditOptions,
) -> Result<FrontendAuditReceiptV1, FrontendContractError> {
    let prepared = prepare_frontend_audit(options)?;
    if options.dry_run {
        return build_receipt(prepared, None);
    }
    verify_inputs_unchanged(&prepared)?;
    let exit_code = run_audit_child(&prepared)?;
    verify_inputs_unchanged(&prepared)?;
    build_receipt(prepared, Some(exit_code))
}

/// Encode a frontend-audit receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_frontend_audit_receipt_json(
    receipt: &FrontendAuditReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_audit_receipt_encode_failed")
}

fn prepare_frontend_audit(
    options: &FrontendAuditOptions,
) -> Result<PreparedFrontendAudit, FrontendContractError> {
    verify_real_directory(&options.root, "frontend audit root")?;
    let root = options.root.canonicalize().map_err(|error| {
        FrontendContractError::new(
            "frontend_audit_root_invalid",
            format!("canonicalize frontend audit root failed: {error}"),
        )
    })?;
    let source = parse_source_map()?.frontend_audit_contract;
    let frontend_contract_receipt_hash = check_frontend_contract(&root)?.receipt_hash;
    Ok(PreparedFrontendAudit {
        source,
        root,
        frontend_contract_receipt_hash,
    })
}

fn verify_inputs_unchanged(prepared: &PreparedFrontendAudit) -> Result<(), FrontendContractError> {
    if check_frontend_contract(&prepared.root)?.receipt_hash
        != prepared.frontend_contract_receipt_hash
    {
        return Err(FrontendContractError::new(
            "frontend_audit_contract_changed",
            "frontend package, lock, source map, or required inventory changed during audit",
        ));
    }
    Ok(())
}

fn run_audit_child(prepared: &PreparedFrontendAudit) -> Result<i32, FrontendContractError> {
    let status = Command::new(npm_launcher())
        .args(&prepared.source.arguments)
        .current_dir(&prepared.root)
        .env_remove("NODE_OPTIONS")
        .stdin(Stdio::null())
        .status()
        .map_err(|error| {
            FrontendContractError::new(
                "frontend_audit_launch_failed",
                format!("launch frontend dependency audit failed: {error}"),
            )
        })?;
    status.code().ok_or_else(|| {
        FrontendContractError::new(
            "frontend_audit_terminated",
            "frontend dependency audit terminated without an exit code",
        )
    })
}

fn npm_launcher() -> OsString {
    if cfg!(windows) {
        OsString::from("npm.cmd")
    } else {
        OsString::from("npm")
    }
}

pub(crate) fn validate_frontend_audit_source(
    source: &FrontendAuditSourceV1,
) -> Result<(), FrontendContractError> {
    let valid = source.schema_version == CONTRACT_SCHEMA_V1
        && source.npm_launcher == EXPECTED_NPM_LAUNCHER
        && source.arguments == EXPECTED_ARGUMENTS
        && source.workflow_failure_policy == EXPECTED_WORKFLOW_FAILURE_POLICY
        && source.findings_interpretation == EXPECTED_FINDINGS_INTERPRETATION
        && source.network_access_accounting == EXPECTED_NETWORK_ACCOUNTING
        && source.filesystem_mutation_accounting == EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING
        && source.environment_accounting == EXPECTED_ENVIRONMENT_ACCOUNTING
        && valid_text(&source.claim_boundary);
    if !valid {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend dependency-audit contract is invalid",
        ));
    }
    Ok(())
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 16 * 1024 && !value.chars().any(char::is_control)
}

fn build_receipt(
    prepared: PreparedFrontendAudit,
    exit_code: Option<i32>,
) -> Result<FrontendAuditReceiptV1, FrontendContractError> {
    let executed = exit_code.is_some();
    let status = match exit_code {
        None => "planned",
        Some(0) => "audit_clean_exit",
        Some(_) => "advisory_or_tool_failure",
    };
    let logical_command = std::iter::once("npm".to_owned())
        .chain(prepared.source.arguments.iter().cloned())
        .collect();
    let mut receipt = FrontendAuditReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "frontend_audit".to_owned(),
        execution_mode: if executed { "execute" } else { "dry_run" }.to_owned(),
        status: status.to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        frontend_contract_receipt_hash: prepared.frontend_contract_receipt_hash,
        logical_command,
        process_launcher: EXPECTED_NPM_LAUNCHER.to_owned(),
        node_options_disposition: "removed_for_direct_child".to_owned(),
        direct_processes_spawned: u64::from(executed),
        observed_exit_code: exit_code,
        workflow_failure_policy: prepared.source.workflow_failure_policy,
        findings_interpretation: prepared.source.findings_interpretation,
        runtime_requirements: FrontendAuditRuntimeRequirementsV1 {
            required: vec!["node".to_owned(), "npm".to_owned()],
            browser_required: false,
            repository_contract_mutation_allowed: false,
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
    FrontendContractError::new("frontend_audit_receipt_encode_failed", detail)
}

fn hash_without_receipt_hash(
    receipt: &FrontendAuditReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        receipt_error(&format!("project frontend audit receipt failed: {error}"))
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| receipt_error("frontend audit receipt is not an object"))?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        receipt_error(&format!(
            "canonicalize frontend audit receipt failed: {error}"
        ))
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{validate_frontend_audit_source, FrontendAuditSourceV1};

    fn source() -> FrontendAuditSourceV1 {
        FrontendAuditSourceV1 {
            schema_version: super::CONTRACT_SCHEMA_V1.to_owned(),
            npm_launcher: super::EXPECTED_NPM_LAUNCHER.to_owned(),
            arguments: super::EXPECTED_ARGUMENTS
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
            workflow_failure_policy: super::EXPECTED_WORKFLOW_FAILURE_POLICY.to_owned(),
            findings_interpretation: super::EXPECTED_FINDINGS_INTERPRETATION.to_owned(),
            network_access_accounting: super::EXPECTED_NETWORK_ACCOUNTING.to_owned(),
            filesystem_mutation_accounting: super::EXPECTED_FILESYSTEM_MUTATION_ACCOUNTING
                .to_owned(),
            environment_accounting: super::EXPECTED_ENVIRONMENT_ACCOUNTING.to_owned(),
            claim_boundary: "bounded non-blocking frontend dependency audit".to_owned(),
        }
    }

    #[test]
    fn audit_contract_rejects_command_and_failure_policy_widening() {
        assert!(validate_frontend_audit_source(&source()).is_ok());

        let mut arguments = source();
        arguments.arguments.push("--omit=dev".to_owned());
        assert!(validate_frontend_audit_source(&arguments).is_err());

        let mut launcher = source();
        launcher.npm_launcher = "npx".to_owned();
        assert!(validate_frontend_audit_source(&launcher).is_err());

        let mut policy = source();
        policy.workflow_failure_policy = "always_pass_without_receipt".to_owned();
        assert!(validate_frontend_audit_source(&policy).is_err());
    }
}
