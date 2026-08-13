use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

use super::{
    canonical_struct, parse_source_map, read_bounded_regular_file, resolve_required_file,
    validate_relative_path, verify_real_directory, FrontendContractError, SOURCE_MAP_BYTES,
};

const PROTOTYPE_CONTRACT_V1: &str = "structural-workbench-prototype-static-contract.v1";
const PROTOTYPE_RECEIPT_V1: &str = "structural-native-workbench-prototype-receipt.v1";
const DEMO_SCHEMA_V1: &str = "workbench-demo.v1";
const MAX_PROTOTYPE_FILE_BYTES: u64 = 1024 * 1024;
const MAX_MARKERS: usize = 64;
const MAX_MARKER_BYTES: usize = 16 * 1024;
const CANONICAL_STATES: [&str; 6] = ["DEMO", "LIVE", "STALE", "BLOCKED", "MISSING", "UNAVAILABLE"];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkbenchPrototypeSourceV1 {
    contract: String,
    app_path: String,
    demo_case_path: String,
    html_path: String,
    expected_demo_schema_version: String,
    expected_data_mode: String,
    canonical_states: Vec<String>,
    expected_status_states: BTreeMap<String, String>,
    app_required_markers: Vec<String>,
    app_forbidden_markers: Vec<String>,
    html_required_markers: Vec<String>,
    claim_boundary: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DemoCaseV1 {
    schema_version: String,
    data_mode: String,
    claim_boundary: String,
    project: DemoProjectV1,
    status: DemoStatusV1,
    case: DemoAnalysisCaseV1,
    residual_history: Vec<Value>,
    reference_comparison: Vec<Value>,
    members: Vec<Value>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DemoProjectV1 {
    id: String,
    name: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DemoAnalysisCaseV1 {
    id: String,
    label: String,
    structure_family: String,
    load_combination: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DemoStatusV1 {
    solver_connected: CheckValueV1,
    p0: CheckValueV1,
    p1: CheckValueV1,
    gpu: CheckValueV1,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize)]
#[serde(untagged)]
enum CheckValueV1 {
    Boolean(bool),
    Text(String),
}

/// Canonical, self-hashed result of the offline Workbench prototype static contract.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkbenchPrototypeReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub contract: String,
    pub status: String,
    pub source_map_sha256: String,
    pub demo_schema_version: String,
    pub data_mode: String,
    pub status_states: BTreeMap<String, String>,
    pub canonical_state_count: usize,
    pub app_required_marker_count: usize,
    pub app_forbidden_marker_count: usize,
    pub html_required_marker_count: usize,
    pub app_byte_length: u64,
    pub demo_case_byte_length: u64,
    pub html_byte_length: u64,
    pub app_sha256: String,
    pub demo_case_sha256: String,
    pub html_sha256: String,
    pub deterministic: bool,
    pub commands_executed: u64,
    pub network_access_count: u64,
    pub browser_executed: bool,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Check the bounded static and language-neutral Workbench prototype contract.
///
/// This deliberately does not execute JavaScript or replace the retained Playwright browser smoke.
/// It strictly decodes the demo fixture, applies the frozen conservative status taxonomy, and
/// checks source/HTML safety and ownership markers without a DOM shim.
///
/// # Errors
///
/// Rejects unsafe or oversized inputs, duplicate/unknown JSON fields, fixture drift, missing or
/// forbidden source markers, and malformed embedded contract metadata.
pub fn check_workbench_prototype(
    root: &Path,
) -> Result<WorkbenchPrototypeReceiptV1, FrontendContractError> {
    verify_real_directory(root, "Workbench prototype contract root")?;
    let source_map = parse_source_map()?;
    let contract = &source_map.workbench_prototype_contract;
    let app_path = resolve_required_file(root, &contract.app_path)?;
    let demo_path = resolve_required_file(root, &contract.demo_case_path)?;
    let html_path = resolve_required_file(root, &contract.html_path)?;
    let app_bytes = read_bounded_regular_file(
        &app_path,
        MAX_PROTOTYPE_FILE_BYTES,
        "Workbench prototype app",
    )?;
    let demo_bytes = read_bounded_regular_file(
        &demo_path,
        MAX_PROTOTYPE_FILE_BYTES,
        "Workbench prototype demo case",
    )?;
    let html_bytes = read_bounded_regular_file(
        &html_path,
        MAX_PROTOTYPE_FILE_BYTES,
        "Workbench prototype HTML",
    )?;
    let app = decode_text(&app_bytes, "app.js")?;
    let html = decode_text(&html_bytes, "index.html")?;
    validate_source_markers(&app, &html, contract)?;
    let demo = decode_demo_case(&demo_bytes)?;
    let status_states = validate_demo_case(&demo, contract)?;

    let mut receipt = WorkbenchPrototypeReceiptV1 {
        schema_version: PROTOTYPE_RECEIPT_V1.to_owned(),
        action: "workbench_prototype_check".to_owned(),
        contract: contract.contract.clone(),
        status: "ready".to_owned(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        demo_schema_version: demo.schema_version,
        data_mode: demo.data_mode,
        status_states,
        canonical_state_count: contract.canonical_states.len(),
        app_required_marker_count: contract.app_required_markers.len(),
        app_forbidden_marker_count: contract.app_forbidden_markers.len(),
        html_required_marker_count: contract.html_required_markers.len(),
        app_byte_length: byte_length(&app_bytes, "app.js")?,
        demo_case_byte_length: byte_length(&demo_bytes, "demo-case.json")?,
        html_byte_length: byte_length(&html_bytes, "index.html")?,
        app_sha256: sha256_identity(&app_bytes),
        demo_case_sha256: sha256_identity(&demo_bytes),
        html_sha256: sha256_identity(&html_bytes),
        deterministic: true,
        commands_executed: 0,
        network_access_count: 0,
        browser_executed: false,
        claim_boundary: contract.claim_boundary.clone(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a Workbench prototype receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_workbench_prototype_receipt_json(
    receipt: &WorkbenchPrototypeReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "workbench_prototype_receipt_encode_failed")
}

pub(crate) fn validate_workbench_prototype_source(
    source: &WorkbenchPrototypeSourceV1,
) -> Result<(), FrontendContractError> {
    if source.contract != PROTOTYPE_CONTRACT_V1
        || source.expected_demo_schema_version != DEMO_SCHEMA_V1
        || source.expected_data_mode != "demo"
        || source
            .canonical_states
            .iter()
            .map(String::as_str)
            .ne(CANONICAL_STATES)
        || source.app_required_markers.is_empty()
        || source.app_required_markers.len() > MAX_MARKERS
        || source.app_forbidden_markers.is_empty()
        || source.app_forbidden_markers.len() > MAX_MARKERS
        || source.html_required_markers.is_empty()
        || source.html_required_markers.len() > MAX_MARKERS
        || !valid_marker_set(&source.app_required_markers)
        || !valid_marker_set(&source.app_forbidden_markers)
        || !valid_marker_set(&source.html_required_markers)
        || !valid_text(&source.claim_boundary)
    {
        return Err(source_error(
            "Workbench prototype contract metadata is invalid",
        ));
    }
    for path in [&source.app_path, &source.demo_case_path, &source.html_path] {
        validate_relative_path(path)?;
    }
    let expected_status_states = BTreeMap::from([
        ("gpu".to_owned(), "MISSING".to_owned()),
        ("p0".to_owned(), "UNAVAILABLE".to_owned()),
        ("p1".to_owned(), "UNAVAILABLE".to_owned()),
        ("solver_connected".to_owned(), "BLOCKED".to_owned()),
    ]);
    if source.expected_status_states != expected_status_states {
        return Err(source_error(
            "Workbench prototype expected status states are not the frozen demo projection",
        ));
    }
    Ok(())
}

fn decode_text(bytes: &[u8], label: &str) -> Result<String, FrontendContractError> {
    std::str::from_utf8(bytes)
        .map(str::to_owned)
        .map_err(|error| {
            FrontendContractError::new(
                "workbench_prototype_text_invalid",
                format!("Workbench prototype {label} is not UTF-8: {error}"),
            )
        })
}

fn decode_demo_case(bytes: &[u8]) -> Result<DemoCaseV1, FrontendContractError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_demo_json_invalid",
            format!("Workbench prototype demo case is invalid strict JSON: {error}"),
        )
    })?;
    serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_demo_contract_invalid",
            format!("Workbench prototype demo fields are invalid: {error}"),
        )
    })
}

fn validate_source_markers(
    app: &str,
    html: &str,
    contract: &WorkbenchPrototypeSourceV1,
) -> Result<(), FrontendContractError> {
    for marker in &contract.app_required_markers {
        if !app.contains(marker) {
            return Err(source_drift(&format!(
                "app.js required marker is missing: {marker}"
            )));
        }
    }
    for marker in &contract.app_forbidden_markers {
        if app.contains(marker) {
            return Err(source_drift(&format!(
                "app.js forbidden marker is present: {marker}"
            )));
        }
    }
    for marker in &contract.html_required_markers {
        if !html.contains(marker) {
            return Err(source_drift(&format!(
                "index.html required marker is missing: {marker}"
            )));
        }
    }
    Ok(())
}

fn validate_demo_case(
    demo: &DemoCaseV1,
    contract: &WorkbenchPrototypeSourceV1,
) -> Result<BTreeMap<String, String>, FrontendContractError> {
    if demo.schema_version != contract.expected_demo_schema_version
        || demo.data_mode != contract.expected_data_mode
        || map_data_mode(&demo.data_mode) != "DEMO"
        || !valid_text(&demo.claim_boundary)
        || contains_word_pass(&demo.claim_boundary)
        || !valid_identifier(&demo.project.id)
        || !valid_text(&demo.project.name)
        || !valid_identifier(&demo.case.id)
        || !valid_text(&demo.case.label)
        || !valid_identifier(&demo.case.structure_family)
        || !valid_text(&demo.case.load_combination)
        || !demo.residual_history.is_empty()
        || !demo.reference_comparison.is_empty()
        || !demo.members.is_empty()
    {
        return Err(demo_drift(
            "demo identity, claim boundary, metadata, or empty evidence collections drifted",
        ));
    }
    if demo.status.solver_connected != CheckValueV1::Boolean(false)
        || demo.status.p0 != CheckValueV1::Text("NOT_EVALUATED".to_owned())
        || demo.status.p1 != CheckValueV1::Text("NOT_EVALUATED".to_owned())
        || demo.status.gpu != CheckValueV1::Text("NOT_CONNECTED".to_owned())
    {
        return Err(demo_drift("demo raw status values drifted"));
    }
    let status_states = BTreeMap::from([
        (
            "gpu".to_owned(),
            map_check_state(&demo.status.gpu).to_owned(),
        ),
        ("p0".to_owned(), map_check_state(&demo.status.p0).to_owned()),
        ("p1".to_owned(), map_check_state(&demo.status.p1).to_owned()),
        (
            "solver_connected".to_owned(),
            map_check_state(&demo.status.solver_connected).to_owned(),
        ),
    ]);
    if status_states != contract.expected_status_states
        || status_states.values().any(|state| state == "LIVE")
    {
        return Err(demo_drift(
            "demo status projection became positive or drifted from the frozen taxonomy",
        ));
    }
    Ok(status_states)
}

fn map_data_mode(mode: &str) -> &'static str {
    match mode.trim().to_ascii_lowercase().as_str() {
        "demo" => "DEMO",
        "live" => "LIVE",
        "stale" => "STALE",
        _ => "UNAVAILABLE",
    }
}

fn map_check_state(value: &CheckValueV1) -> &'static str {
    match value {
        CheckValueV1::Boolean(true) => "LIVE",
        CheckValueV1::Boolean(false) => "BLOCKED",
        CheckValueV1::Text(text) => match text.trim().to_ascii_uppercase().as_str() {
            "NOT_CONNECTED" | "DISCONNECTED" => "MISSING",
            "BLOCKED" => "BLOCKED",
            "STALE" => "STALE",
            "CONNECTED" | "READY" | "CONVERGED" => "LIVE",
            _ => "UNAVAILABLE",
        },
    }
}

fn valid_marker_set(markers: &[String]) -> bool {
    let unique = markers.iter().collect::<BTreeSet<_>>();
    unique.len() == markers.len()
        && markers.iter().all(|marker| {
            !marker.is_empty()
                && marker.len() <= MAX_MARKER_BYTES
                && !marker.chars().any(char::is_control)
        })
}

fn valid_text(value: &str) -> bool {
    !value.trim().is_empty()
        && value.len() <= MAX_MARKER_BYTES
        && !value.chars().any(char::is_control)
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn contains_word_pass(value: &str) -> bool {
    value
        .split(|character: char| !character.is_ascii_alphanumeric() && character != '_')
        .any(|word| word.eq_ignore_ascii_case("pass"))
}

fn byte_length(bytes: &[u8], label: &str) -> Result<u64, FrontendContractError> {
    u64::try_from(bytes.len()).map_err(|_| {
        FrontendContractError::new(
            "workbench_prototype_length_invalid",
            format!("Workbench prototype {label} length is not addressable"),
        )
    })
}

fn source_error(detail: &str) -> FrontendContractError {
    FrontendContractError::new("frontend_source_map_contract_invalid", detail)
}

fn source_drift(detail: &str) -> FrontendContractError {
    FrontendContractError::new("workbench_prototype_source_drift", detail)
}

fn demo_drift(detail: &str) -> FrontendContractError {
    FrontendContractError::new("workbench_prototype_demo_drift", detail)
}

fn hash_without_receipt_hash(
    receipt: &WorkbenchPrototypeReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_receipt_encode_failed",
            format!("project Workbench prototype receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "workbench_prototype_receipt_encode_failed",
                "Workbench prototype receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "workbench_prototype_receipt_encode_failed",
            format!("canonicalize Workbench prototype receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::{map_check_state, map_data_mode, CheckValueV1};

    #[test]
    fn native_taxonomy_matches_the_conservative_prototype_mapping() {
        assert_eq!(map_data_mode("demo"), "DEMO");
        assert_eq!(map_data_mode("LIVE"), "LIVE");
        assert_eq!(map_data_mode("stale"), "STALE");
        assert_eq!(map_data_mode("unknown"), "UNAVAILABLE");
        assert_eq!(map_check_state(&CheckValueV1::Boolean(true)), "LIVE");
        assert_eq!(map_check_state(&CheckValueV1::Boolean(false)), "BLOCKED");
        for token in ["NOT_CONNECTED", "DISCONNECTED"] {
            assert_eq!(
                map_check_state(&CheckValueV1::Text(token.to_owned())),
                "MISSING"
            );
        }
        for token in ["NOT_EVALUATED", "PENDING", "", "unknown"] {
            assert_eq!(
                map_check_state(&CheckValueV1::Text(token.to_owned())),
                "UNAVAILABLE"
            );
        }
        for token in ["CONNECTED", "READY", "CONVERGED"] {
            assert_eq!(
                map_check_state(&CheckValueV1::Text(token.to_owned())),
                "LIVE"
            );
        }
    }
}
