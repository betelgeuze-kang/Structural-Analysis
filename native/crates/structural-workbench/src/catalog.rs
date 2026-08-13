//! Strict, read-only benchmark catalog browsing for the native Workbench.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

use crate::WorkbenchError;

const CATALOG_SCHEMA_V2: &str = "benchmark-catalog.v2";
const CATALOG_VIEW_SCHEMA_V1: &str = "structural-native-benchmark-catalog-view.v1";
const CASE_VIEW_SCHEMA_V1: &str = "structural-native-benchmark-case-view.v1";
const CATALOG_HASH_FIELD: &str = "catalog_view_hash";
const CASE_HASH_FIELD: &str = "case_view_hash";
const MAX_QUERY_CHARS: usize = 256;
const CLAIM_BOUNDARY: &str = "read_only_embedded_candidate_catalog_browsing_preserves_unverified_geometry_only_and_missing_runner_boundaries_and_never_executes_acquisition_or_solver_commands";
const EMBEDDED_CATALOG: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../catalog/benchmark-catalog-v2.json"
));
const EXPECTED_LIFECYCLE_STATES: [&str; 6] = [
    "DISCOVERED",
    "ACQUIRED",
    "NORMALIZED",
    "REFERENCE_ATTACHED",
    "RUNNABLE",
    "VALIDATED",
];

/// Truth class preserved from the language-neutral benchmark catalog.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BenchmarkTruthClassV1 {
    Analytic,
    IndependentSolver,
    CommercialReference,
    Experimental,
    GeometryOnly,
}

impl BenchmarkTruthClassV1 {
    /// Parse one exact CLI filter token.
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "analytic" => Some(Self::Analytic),
            "independent_solver" => Some(Self::IndependentSolver),
            "commercial_reference" => Some(Self::CommercialReference),
            "experimental" => Some(Self::Experimental),
            "geometry_only" => Some(Self::GeometryOnly),
            _ => None,
        }
    }

    const fn label(self) -> &'static str {
        match self {
            Self::Analytic => "analytic",
            Self::IndependentSolver => "independent_solver",
            Self::CommercialReference => "commercial_reference",
            Self::Experimental => "experimental",
            Self::GeometryOnly => "geometry_only",
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
enum LocalAvailabilityV1 {
    Available,
    External,
    Missing,
}

impl LocalAvailabilityV1 {
    const fn label(self) -> &'static str {
        match self {
            Self::Available => "available",
            Self::External => "external",
            Self::Missing => "missing",
        }
    }
}

/// File-size class used by the catalog browser filter.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum BenchmarkSizeClassV1 {
    Small,
    Medium,
    Large,
    Unknown,
}

impl BenchmarkSizeClassV1 {
    /// Parse one exact CLI filter token.
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "small" => Some(Self::Small),
            "medium" => Some(Self::Medium),
            "large" => Some(Self::Large),
            "unknown" => Some(Self::Unknown),
            _ => None,
        }
    }

    const fn label(self) -> &'static str {
        match self {
            Self::Small => "small",
            Self::Medium => "medium",
            Self::Large => "large",
            Self::Unknown => "unknown",
        }
    }
}

/// Lifecycle derived only from explicit catalog verification fields.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BenchmarkLifecycleV1 {
    Discovered,
    Acquired,
    Normalized,
    ReferenceAttached,
    Runnable,
    Validated,
}

impl BenchmarkLifecycleV1 {
    /// Parse one exact CLI filter token.
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "DISCOVERED" => Some(Self::Discovered),
            "ACQUIRED" => Some(Self::Acquired),
            "NORMALIZED" => Some(Self::Normalized),
            "REFERENCE_ATTACHED" => Some(Self::ReferenceAttached),
            "RUNNABLE" => Some(Self::Runnable),
            "VALIDATED" => Some(Self::Validated),
            _ => None,
        }
    }

    const fn label(self) -> &'static str {
        match self {
            Self::Discovered => "DISCOVERED",
            Self::Acquired => "ACQUIRED",
            Self::Normalized => "NORMALIZED",
            Self::ReferenceAttached => "REFERENCE_ATTACHED",
            Self::Runnable => "RUNNABLE",
            Self::Validated => "VALIDATED",
        }
    }
}

/// Optional filters matching the legacy benchmark browser semantics.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct BenchmarkCatalogFilterV1 {
    pub truth_class: Option<BenchmarkTruthClassV1>,
    pub size_class: Option<BenchmarkSizeClassV1>,
    pub lifecycle: Option<BenchmarkLifecycleV1>,
    pub first_targets_only: bool,
    pub query: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct BenchmarkVerificationV2 {
    license_id: Option<String>,
    license_url: Option<String>,
    license_verified: bool,
    truth_class_verified: bool,
    truth_evidence_path: Option<String>,
    reference_results_available: bool,
    reference_results_path: Option<String>,
    reference_solver: Option<String>,
    reference_solver_version: Option<String>,
    acquisition_command: Option<String>,
    runner_id: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
struct BenchmarkCaseV2 {
    id: String,
    title: String,
    source_url: String,
    source_version: String,
    license: String,
    truth_class: BenchmarkTruthClassV1,
    structure_family: String,
    analysis_types: Vec<String>,
    #[serde(default)]
    node_count: Option<u64>,
    #[serde(default)]
    element_count: Option<u64>,
    #[serde(default)]
    checksum: Option<String>,
    local_availability: LocalAvailabilityV1,
    source_format: Option<String>,
    file_bytes: Option<u64>,
    size_class: BenchmarkSizeClassV1,
    truth_class_basis: String,
    first_validation_target: bool,
    verification: BenchmarkVerificationV2,
    all_source_urls: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BenchmarkCatalogV2 {
    schema_version: String,
    catalog_kind: String,
    generated_at: Option<String>,
    generated_by: String,
    disclaimer: String,
    accuracy_exclusion_rule: String,
    lifecycle_states: Vec<String>,
    cases: Vec<BenchmarkCaseV2>,
}

/// Browse the catalog embedded in the Rust-native product binary.
///
/// # Errors
///
/// Rejects contract drift, invalid filters, duplicate case IDs, or canonicalization failure.
pub fn browse_embedded_benchmark_catalog(
    filter: &BenchmarkCatalogFilterV1,
) -> Result<String, WorkbenchError> {
    let parsed = parse_catalog(EMBEDDED_CATALOG)?;
    browse_catalog(&parsed, EMBEDDED_CATALOG, filter)
}

/// Return one exact case from the catalog embedded in the native binary.
///
/// # Errors
///
/// Rejects an invalid case ID, catalog contract drift, or a missing case.
pub fn show_embedded_benchmark_case(case_id: &str) -> Result<String, WorkbenchError> {
    if !valid_identifier(case_id) {
        return Err(WorkbenchError::new(
            "workbench_catalog_case_id_invalid",
            "catalog case ID must be a non-empty ASCII identifier",
        ));
    }
    let parsed = parse_catalog(EMBEDDED_CATALOG)?;
    let selected = parsed
        .catalog
        .cases
        .iter()
        .find(|case| case.id == case_id)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_catalog_case_not_found",
                format!("benchmark catalog has no case {case_id}"),
            )
        })?;
    let value = json!({
        "schema_version": CASE_VIEW_SCHEMA_V1,
        "source_schema_version": parsed.catalog.schema_version,
        "catalog_kind": parsed.catalog.catalog_kind,
        "source_content_hash": sha256_identity(EMBEDDED_CATALOG),
        "canonical_catalog_hash": parsed.canonical_hash,
        "case": project_case(selected)?,
        "claim_boundary": CLAIM_BOUNDARY,
    });
    canonical_hashed(value, CASE_HASH_FIELD)
}

#[derive(Debug)]
struct ParsedCatalog {
    catalog: BenchmarkCatalogV2,
    canonical_hash: String,
}

fn parse_catalog(bytes: &[u8]) -> Result<ParsedCatalog, WorkbenchError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        WorkbenchError::new("workbench_catalog_json_invalid", error.to_string())
    })?;
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        WorkbenchError::new(
            "workbench_catalog_canonicalization_failed",
            error.to_string(),
        )
    })?;
    let catalog: BenchmarkCatalogV2 = serde_json::from_value(value).map_err(|error| {
        WorkbenchError::new(
            "workbench_catalog_contract_invalid",
            format!("catalog fields are missing, mistyped or unknown: {error}"),
        )
    })?;
    validate_catalog(&catalog)?;
    Ok(ParsedCatalog {
        catalog,
        canonical_hash: sha256_identity(canonical.as_bytes()),
    })
}

fn validate_catalog(catalog: &BenchmarkCatalogV2) -> Result<(), WorkbenchError> {
    if catalog.schema_version != CATALOG_SCHEMA_V2
        || catalog.catalog_kind.trim().is_empty()
        || catalog.generated_by.trim().is_empty()
        || catalog.disclaimer.trim().is_empty()
        || catalog.accuracy_exclusion_rule.trim().is_empty()
        || catalog.lifecycle_states
            != EXPECTED_LIFECYCLE_STATES
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
    {
        return Err(contract_error(
            "catalog header is unsupported or incomplete",
        ));
    }
    if catalog
        .generated_at
        .as_deref()
        .is_some_and(|value| value.trim().is_empty())
    {
        return Err(contract_error(
            "catalog generated_at must be null or non-empty",
        ));
    }
    let mut identifiers = BTreeSet::new();
    for case in &catalog.cases {
        if !identifiers.insert(case.id.as_str()) {
            return Err(WorkbenchError::new(
                "workbench_catalog_duplicate_case_id",
                format!("catalog case ID is duplicated: {}", case.id),
            ));
        }
        validate_case(case)?;
    }
    Ok(())
}

fn validate_case(case: &BenchmarkCaseV2) -> Result<(), WorkbenchError> {
    if !valid_identifier(&case.id)
        || [
            case.title.as_str(),
            case.source_url.as_str(),
            case.source_version.as_str(),
            case.license.as_str(),
            case.structure_family.as_str(),
            case.truth_class_basis.as_str(),
        ]
        .iter()
        .any(|value| value.trim().is_empty() || value.chars().any(char::is_control))
        || case
            .analysis_types
            .iter()
            .chain(case.all_source_urls.iter())
            .any(|value| value.trim().is_empty() || value.chars().any(char::is_control))
        || case.file_bytes == Some(0)
    {
        return Err(contract_error(&format!(
            "catalog case {} has an invalid required field",
            case.id
        )));
    }
    if let Some(checksum) = case.checksum.as_deref() {
        if !valid_sha256(checksum) {
            return Err(contract_error(&format!(
                "catalog case {} has an invalid checksum",
                case.id
            )));
        }
    }
    for optional in [
        case.source_format.as_deref(),
        case.verification.license_id.as_deref(),
        case.verification.license_url.as_deref(),
        case.verification.truth_evidence_path.as_deref(),
        case.verification.reference_results_path.as_deref(),
        case.verification.reference_solver.as_deref(),
        case.verification.reference_solver_version.as_deref(),
        case.verification.acquisition_command.as_deref(),
        case.verification.runner_id.as_deref(),
    ] {
        if optional
            .is_some_and(|value| value.trim().is_empty() || value.chars().any(char::is_control))
        {
            return Err(contract_error(&format!(
                "catalog case {} has an invalid optional field",
                case.id
            )));
        }
    }
    if case
        .verification
        .runner_id
        .as_deref()
        .is_some_and(|runner| {
            !valid_command_token(runner)
                || !valid_command_token(&case.id)
                || case
                    .source_format
                    .as_deref()
                    .is_some_and(|format| !valid_command_token(format))
        })
    {
        return Err(contract_error(&format!(
            "catalog case {} has an unsafe runner token",
            case.id
        )));
    }
    Ok(())
}

fn browse_catalog(
    parsed: &ParsedCatalog,
    source_bytes: &[u8],
    filter: &BenchmarkCatalogFilterV1,
) -> Result<String, WorkbenchError> {
    let normalized_query = normalize_query(filter.query.as_deref())?;
    if filter.first_targets_only && filter.lifecycle.is_some() {
        return Err(WorkbenchError::new(
            "workbench_catalog_filter_invalid",
            "first-targets and an exact lifecycle filter are mutually exclusive",
        ));
    }
    let matched = parsed
        .catalog
        .cases
        .iter()
        .filter(|case| matches_filter(case, filter, normalized_query.as_deref()))
        .map(project_case)
        .collect::<Result<Vec<_>, _>>()?;
    let cases = &parsed.catalog.cases;
    let value = json!({
        "schema_version": CATALOG_VIEW_SCHEMA_V1,
        "source_schema_version": parsed.catalog.schema_version,
        "catalog_kind": parsed.catalog.catalog_kind,
        "generated_at": parsed.catalog.generated_at,
        "generated_by": parsed.catalog.generated_by,
        "disclaimer": parsed.catalog.disclaimer,
        "accuracy_exclusion_rule": parsed.catalog.accuracy_exclusion_rule,
        "source_content_hash": sha256_identity(source_bytes),
        "canonical_catalog_hash": parsed.canonical_hash,
        "filters": {
            "truth_class": filter.truth_class.map(BenchmarkTruthClassV1::label),
            "size_class": filter.size_class.map(BenchmarkSizeClassV1::label),
            "lifecycle": filter.lifecycle.map(BenchmarkLifecycleV1::label),
            "first_targets_only": filter.first_targets_only,
            "query": normalized_query,
        },
        "summary": {
            "total_case_count": cases.len(),
            "matched_case_count": matched.len(),
            "accuracy_comparable_count": cases.iter().filter(|case| accuracy_comparable(case)).count(),
            "validated_count": cases.iter().filter(|case| lifecycle(case) == BenchmarkLifecycleV1::Validated).count(),
            "runnable_count": cases.iter().filter(|case| case.verification.runner_id.is_some()).count(),
            "geometry_only_count": cases.iter().filter(|case| case.truth_class == BenchmarkTruthClassV1::GeometryOnly).count(),
            "first_validation_target_count": cases.iter().filter(|case| case.first_validation_target).count(),
        },
        "cases": matched,
        "claim_boundary": CLAIM_BOUNDARY,
    });
    canonical_hashed(value, CATALOG_HASH_FIELD)
}

fn matches_filter(
    case: &BenchmarkCaseV2,
    filter: &BenchmarkCatalogFilterV1,
    normalized_query: Option<&str>,
) -> bool {
    if filter
        .truth_class
        .is_some_and(|truth| truth != case.truth_class)
        || filter
            .size_class
            .is_some_and(|size| size != case.size_class)
        || filter
            .lifecycle
            .is_some_and(|expected| expected != lifecycle(case))
        || (filter.first_targets_only && !case.first_validation_target)
    {
        return false;
    }
    normalized_query.map_or(true, |query| {
        format!(
            "{} {} {} {}",
            case.title, case.structure_family, case.source_url, case.license
        )
        .to_lowercase()
        .contains(query)
    })
}

fn normalize_query(query: Option<&str>) -> Result<Option<String>, WorkbenchError> {
    let Some(query) = query.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(None);
    };
    if query.chars().count() > MAX_QUERY_CHARS || query.chars().any(char::is_control) {
        return Err(WorkbenchError::new(
            "workbench_catalog_filter_invalid",
            "catalog query must be at most 256 non-control characters",
        ));
    }
    Ok(Some(query.to_lowercase()))
}

fn project_case(case: &BenchmarkCaseV2) -> Result<Value, WorkbenchError> {
    let mut value = serde_json::to_value(case).map_err(|error| {
        WorkbenchError::new("workbench_catalog_serialization_failed", error.to_string())
    })?;
    let object = value.as_object_mut().ok_or_else(|| {
        WorkbenchError::new(
            "workbench_catalog_serialization_failed",
            "catalog case projection is not an object",
        )
    })?;
    object.insert(
        "lifecycle".to_owned(),
        Value::String(lifecycle(case).label().to_owned()),
    );
    object.insert(
        "accuracyComparable".to_owned(),
        Value::Bool(accuracy_comparable(case)),
    );
    object.insert(
        "comparabilityReason".to_owned(),
        Value::String(comparability_reason(case)),
    );
    let (run_command, blocked_reason) = run_surface(case);
    object.insert(
        "runCommand".to_owned(),
        run_command.map_or(Value::Null, Value::String),
    );
    object.insert(
        "runBlockedReason".to_owned(),
        blocked_reason.map_or(Value::Null, Value::String),
    );
    Ok(value)
}

fn lifecycle(case: &BenchmarkCaseV2) -> BenchmarkLifecycleV1 {
    let verification = &case.verification;
    if verification.license_verified
        && verification.truth_class_verified
        && verification.reference_results_available
        && verification.runner_id.is_some()
    {
        BenchmarkLifecycleV1::Validated
    } else if verification.runner_id.is_some() {
        BenchmarkLifecycleV1::Runnable
    } else if verification.reference_results_available {
        BenchmarkLifecycleV1::ReferenceAttached
    } else if case.local_availability == LocalAvailabilityV1::Available {
        if case.source_format.is_some() {
            BenchmarkLifecycleV1::Normalized
        } else {
            BenchmarkLifecycleV1::Acquired
        }
    } else {
        BenchmarkLifecycleV1::Discovered
    }
}

fn accuracy_comparable(case: &BenchmarkCaseV2) -> bool {
    case.truth_class != BenchmarkTruthClassV1::GeometryOnly
        && case.verification.reference_results_available
        && case.local_availability == LocalAvailabilityV1::Available
}

fn comparability_reason(case: &BenchmarkCaseV2) -> String {
    if case.truth_class == BenchmarkTruthClassV1::GeometryOnly {
        "geometry_only — import/topology/rendering only; excluded from accuracy averaging"
            .to_owned()
    } else if case.local_availability != LocalAvailabilityV1::Available {
        format!(
            "not locally available ({})",
            case.local_availability.label()
        )
    } else if !case.verification.reference_results_available {
        "no reference results attached yet".to_owned()
    } else if !case.verification.truth_class_verified {
        "comparable, but truth class is unverified".to_owned()
    } else {
        "accuracy-comparable".to_owned()
    }
}

fn run_surface(case: &BenchmarkCaseV2) -> (Option<String>, Option<String>) {
    let Some(runner) = case.verification.runner_id.as_deref() else {
        return (None, Some("No benchmark runner registered".to_owned()));
    };
    let format = case
        .source_format
        .as_deref()
        .map_or_else(String::new, |value| format!(" --source-format {value}"));
    (
        Some(format!(
            "run-benchmark --runner {runner} --case {}{format}",
            case.id
        )),
        None,
    )
}

fn canonical_hashed(mut value: Value, hash_field: &str) -> Result<String, WorkbenchError> {
    let object = value.as_object_mut().ok_or_else(|| {
        WorkbenchError::new(
            "workbench_catalog_serialization_failed",
            "catalog view is not an object",
        )
    })?;
    object.remove(hash_field);
    let unsigned = canonicalize_model_ir_v2(&value).map_err(|error| {
        WorkbenchError::new(
            "workbench_catalog_canonicalization_failed",
            error.to_string(),
        )
    })?;
    value
        .as_object_mut()
        .expect("catalog view object checked above")
        .insert(
            hash_field.to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_model_ir_v2(&value).map_err(|error| {
        WorkbenchError::new(
            "workbench_catalog_canonicalization_failed",
            error.to_string(),
        )
    })
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 160
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn valid_command_token(value: &str) -> bool {
    valid_identifier(value)
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn contract_error(detail: &str) -> WorkbenchError {
    WorkbenchError::new("workbench_catalog_contract_invalid", detail)
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Value};
    use structural_contracts::model_ir::canonicalize_model_ir_v2;
    use structural_contracts::product_ir::sha256_identity;

    use super::{
        browse_catalog, parse_catalog, BenchmarkCatalogFilterV1, BenchmarkSizeClassV1,
        BenchmarkTruthClassV1, EMBEDDED_CATALOG,
    };

    #[test]
    fn embedded_catalog_is_strict_and_frozen() {
        let parsed = parse_catalog(EMBEDDED_CATALOG).expect("embedded catalog contract");
        assert_eq!(parsed.catalog.cases.len(), 26);
        assert_eq!(
            sha256_identity(EMBEDDED_CATALOG),
            "sha256:235a463ccd9508440b8cba9e7e793396b8635b0a761cfdb645e120a756d60736"
        );
    }

    #[test]
    fn filters_match_the_legacy_browser_without_promoting_geometry() {
        let parsed = parse_catalog(EMBEDDED_CATALOG).expect("embedded catalog contract");
        let filtered = browse_catalog(
            &parsed,
            EMBEDDED_CATALOG,
            &BenchmarkCatalogFilterV1 {
                truth_class: Some(BenchmarkTruthClassV1::GeometryOnly),
                size_class: Some(BenchmarkSizeClassV1::Large),
                ..BenchmarkCatalogFilterV1::default()
            },
        )
        .expect("filtered catalog");
        let mut value: Value = serde_json::from_str(&filtered).expect("catalog JSON");
        assert_eq!(value["summary"]["total_case_count"], 26);
        assert_eq!(value["summary"]["matched_case_count"], 4);
        assert_eq!(value["summary"]["accuracy_comparable_count"], 5);
        assert!(value["cases"]
            .as_array()
            .expect("cases")
            .iter()
            .all(|case| case["accuracyComparable"] == false && case["runCommand"].is_null()));
        let expected_hash = value["catalog_view_hash"]
            .as_str()
            .expect("view hash")
            .to_owned();
        value
            .as_object_mut()
            .expect("view object")
            .remove("catalog_view_hash");
        let unsigned = canonicalize_model_ir_v2(&value).expect("canonical unsigned view");
        assert_eq!(expected_hash, sha256_identity(unsigned.as_bytes()));
    }

    #[test]
    fn unknown_fields_and_duplicate_identifiers_fail_closed() {
        let value: Value = serde_json::from_slice(EMBEDDED_CATALOG).expect("fixture JSON");
        let mut unknown = value.clone();
        unknown
            .as_object_mut()
            .expect("catalog object")
            .insert("future_claim".to_owned(), json!(true));
        assert!(parse_catalog(
            serde_json::to_string(&unknown)
                .expect("unknown JSON")
                .as_bytes()
        )
        .is_err());

        let mut duplicate = value;
        let first = duplicate["cases"][0].clone();
        duplicate["cases"]
            .as_array_mut()
            .expect("catalog cases")
            .push(first);
        let error = parse_catalog(
            serde_json::to_string(&duplicate)
                .expect("duplicate JSON")
                .as_bytes(),
        )
        .expect_err("duplicate ID must fail");
        assert_eq!(error.code, "workbench_catalog_duplicate_case_id");
    }
}
