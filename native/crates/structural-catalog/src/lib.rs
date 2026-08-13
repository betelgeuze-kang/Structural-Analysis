//! Deterministic, fail-closed benchmark-catalog construction.

#![forbid(unsafe_code)]

use std::collections::BTreeSet;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const SOURCE_MAP_SCHEMA_V1: &str = "structural-benchmark-catalog-source-map.v1";
const CATALOG_SCHEMA_V2: &str = "benchmark-catalog.v2";
const RECEIPT_SCHEMA_V1: &str = "structural-native-benchmark-catalog-build-receipt.v1";
const GENERATED_BY: &str = "structural-catalog";
const MAX_SOURCE_MAP_BYTES: usize = 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_CATALOG_BYTES: u64 = 16 * 1024 * 1024;
const MAX_AGGREGATE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_SOURCE_FILES: usize = 512;
const MAX_CASES: usize = 512;
const CLAIM_BOUNDARY: &str = "builds_only_a_deterministic_candidate_catalog_from_bounded_strict_local_metadata_preserves_unverified_fields_and_never_fetches_sources_executes_commands_or_promotes_validation";
const DISCLAIMER: &str = "Shared language-neutral candidate benchmark catalog built from collected open-data metadata. Checksums and URLs are read from source metadata; licenses, most truth classes, reference results, and runners are UNVERIFIED. A run command is only offered for cases with a registered runnerId. geometry_only cases must not be used for numerical-accuracy averaging.";
const ACCURACY_EXCLUSION_RULE: &str = "geometry_only data is used only for import / topology / rendering / GUI performance / model health, never in numerical-accuracy averages.";
const LIFECYCLE_STATES: [&str; 6] = [
    "DISCOVERED",
    "ACQUIRED",
    "NORMALIZED",
    "REFERENCE_ATTACHED",
    "RUNNABLE",
    "VALIDATED",
];
const SOURCE_MAP_BYTES: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../catalog/benchmark-catalog-sources-v1.json"
));
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// Stable native catalog-builder failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CatalogBuildError {
    pub code: &'static str,
    pub detail: String,
}

impl CatalogBuildError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for CatalogBuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for CatalogBuildError {}

/// Explicit deterministic catalog build inputs.
#[derive(Clone, Copy, Debug)]
pub struct BenchmarkCatalogBuildRequest<'a> {
    pub source_root: &'a Path,
    pub output: &'a Path,
    pub generated_at: &'a str,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogSourceMapV1 {
    schema_version: String,
    report_directory: String,
    report_suffix: String,
    peer_specimen_directory: String,
    peer_specimen_suffix: String,
    first_validation_targets: Vec<FirstTargetRuleV1>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields, tag = "kind", rename_all = "snake_case")]
enum FirstTargetRuleV1 {
    ExactId { value: String },
    IdPrefix { value: String },
    SourceFormat { value: String },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum TruthClassV2 {
    IndependentSolver,
    CommercialReference,
    Experimental,
    GeometryOnly,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
enum LocalAvailabilityV2 {
    Available,
    External,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
enum SizeClassV2 {
    Small,
    Medium,
    Large,
    Unknown,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct VerificationV2 {
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

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct BenchmarkCaseV2 {
    id: String,
    title: String,
    source_url: String,
    source_version: String,
    license: String,
    truth_class: TruthClassV2,
    structure_family: String,
    analysis_types: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    checksum: Option<String>,
    local_availability: LocalAvailabilityV2,
    source_format: Option<String>,
    file_bytes: Option<u64>,
    size_class: SizeClassV2,
    truth_class_basis: String,
    all_source_urls: Vec<String>,
    first_validation_target: bool,
    verification: VerificationV2,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct BenchmarkCatalogV2 {
    schema_version: String,
    catalog_kind: String,
    generated_at: String,
    generated_by: String,
    disclaimer: String,
    accuracy_exclusion_rule: String,
    lifecycle_states: Vec<String>,
    cases: Vec<BenchmarkCaseV2>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct CatalogSourceReceiptV1 {
    pub kind: String,
    pub path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Self-hashed result of a catalog build or read-only drift check.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct BenchmarkCatalogBuildReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub source_map_schema_version: String,
    pub source_map_sha256: String,
    pub generated_at: String,
    pub generated_by: String,
    pub report_count: usize,
    pub peer_specimen_count: usize,
    pub case_count: usize,
    pub source_inventory_sha256: String,
    pub output_catalog_sha256: String,
    pub first_validation_targets: Vec<String>,
    pub sources: Vec<CatalogSourceReceiptV1>,
    pub deterministic: bool,
    pub sources_unchanged: bool,
    pub commands_executed: u64,
    pub network_access_count: u64,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Debug)]
struct GeneratedCatalogV2 {
    source_map_schema_version: String,
    generated_at: String,
    bytes: Vec<u8>,
    report_count: usize,
    peer_specimen_count: usize,
    first_validation_targets: Vec<String>,
    sources: Vec<CatalogSourceReceiptV1>,
}

/// Build and atomically replace one deterministic catalog file.
///
/// # Errors
///
/// Rejects malformed or unsafe inputs, invalid timestamps, output symlinks/directories, and
/// filesystem publication failures.
pub fn build_benchmark_catalog(
    request: &BenchmarkCatalogBuildRequest<'_>,
) -> Result<BenchmarkCatalogBuildReceiptV1, CatalogBuildError> {
    validate_generated_at(request.generated_at)?;
    let generated = generate_catalog(request.source_root, request.generated_at)?;
    atomic_replace_catalog(request.output, &generated.bytes)?;
    build_receipt(&generated, "build")
}

/// Rebuild a catalog in memory from its declared timestamp and require exact byte parity.
///
/// # Errors
///
/// Rejects every build-input error plus malformed, noncanonical, symlinked, or drifted catalogs.
pub fn check_benchmark_catalog(
    source_root: &Path,
    catalog_path: &Path,
) -> Result<BenchmarkCatalogBuildReceiptV1, CatalogBuildError> {
    let existing = read_bounded_regular_file(catalog_path, MAX_CATALOG_BYTES, "catalog")?;
    let value = decode_json_strict(&existing).map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_json_invalid",
            format!("catalog output is invalid strict JSON: {error}"),
        )
    })?;
    let generated_at = value
        .get("generated_at")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            CatalogBuildError::new(
                "catalog_generated_at_invalid",
                "catalog output has no generated_at timestamp",
            )
        })?;
    validate_generated_at(generated_at)?;
    let generated = generate_catalog(source_root, generated_at)?;
    if existing != generated.bytes {
        return Err(CatalogBuildError::new(
            "catalog_output_drift",
            "catalog bytes do not match the bounded native projection of current source metadata",
        ));
    }
    build_receipt(&generated, "check")
}

/// Encode a receipt as deterministic canonical JSON.
///
/// # Errors
///
/// Returns an error only if the receipt cannot satisfy canonical JSON rules.
pub fn canonical_receipt_json(
    receipt: &BenchmarkCatalogBuildReceiptV1,
) -> Result<String, CatalogBuildError> {
    canonical_struct(receipt, "catalog_receipt_encode_failed")
}

fn generate_catalog(
    root: &Path,
    generated_at: &str,
) -> Result<GeneratedCatalogV2, CatalogBuildError> {
    verify_real_directory(root, "catalog source root")?;
    let source_map = parse_source_map()?;
    let report_directory = resolve_directory(root, &source_map.report_directory)?;
    let peer_directory = resolve_optional_directory(root, &source_map.peer_specimen_directory)?;
    let mut aggregate_bytes = 0_u64;
    let mut sources = Vec::new();
    let mut cases = Vec::new();

    let report_files = selected_files(&report_directory, &source_map.report_suffix)?;
    if report_files.is_empty() {
        return Err(CatalogBuildError::new(
            "catalog_report_sources_missing",
            "catalog report directory contains no selected JSON sources",
        ));
    }
    for path in &report_files {
        let (bytes, receipt) = load_source(root, path, "report", &mut aggregate_bytes)?;
        let value = decode_source_json(path, &bytes)?;
        cases.push(case_from_report(&value, path)?);
        sources.push(receipt);
    }

    let peer_files = match peer_directory {
        Some(directory) => selected_files(&directory, &source_map.peer_specimen_suffix)?,
        None => Vec::new(),
    };
    for path in &peer_files {
        let (bytes, receipt) = load_source(root, path, "peer_specimen", &mut aggregate_bytes)?;
        let value = decode_source_json(path, &bytes)?;
        cases.push(case_from_peer_specimen(root, path, &value)?);
        sources.push(receipt);
    }

    if cases.is_empty() || cases.len() > MAX_CASES || sources.len() > MAX_SOURCE_FILES {
        return Err(CatalogBuildError::new(
            "catalog_case_count_invalid",
            "catalog case/source count is outside the bounded contract",
        ));
    }
    validate_unique_cases(&cases)?;
    mark_first_validation_targets(&mut cases, &source_map.first_validation_targets);
    let first_validation_targets = cases
        .iter()
        .filter(|case| case.first_validation_target)
        .map(|case| case.id.clone())
        .collect::<Vec<_>>();
    let catalog = BenchmarkCatalogV2 {
        schema_version: CATALOG_SCHEMA_V2.to_owned(),
        catalog_kind: "candidate".to_owned(),
        generated_at: generated_at.to_owned(),
        generated_by: GENERATED_BY.to_owned(),
        disclaimer: DISCLAIMER.to_owned(),
        accuracy_exclusion_rule: ACCURACY_EXCLUSION_RULE.to_owned(),
        lifecycle_states: LIFECYCLE_STATES.iter().map(ToString::to_string).collect(),
        cases,
    };
    let mut bytes = serde_json::to_vec_pretty(&catalog).map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_encode_failed",
            format!("encode benchmark catalog failed: {error}"),
        )
    })?;
    bytes.push(b'\n');
    Ok(GeneratedCatalogV2 {
        source_map_schema_version: source_map.schema_version,
        generated_at: generated_at.to_owned(),
        bytes,
        report_count: report_files.len(),
        peer_specimen_count: peer_files.len(),
        first_validation_targets,
        sources,
    })
}

fn parse_source_map() -> Result<CatalogSourceMapV1, CatalogBuildError> {
    if SOURCE_MAP_BYTES.len() > MAX_SOURCE_MAP_BYTES {
        return Err(CatalogBuildError::new(
            "catalog_source_map_too_large",
            "embedded catalog source map exceeds its bound",
        ));
    }
    let value = decode_json_strict(SOURCE_MAP_BYTES).map_err(|error| {
        CatalogBuildError::new(
            "catalog_source_map_json_invalid",
            format!("embedded catalog source map is invalid: {error}"),
        )
    })?;
    let source_map: CatalogSourceMapV1 = serde_json::from_value(value).map_err(|error| {
        CatalogBuildError::new(
            "catalog_source_map_contract_invalid",
            format!("embedded catalog source map fields are invalid: {error}"),
        )
    })?;
    if source_map.schema_version != SOURCE_MAP_SCHEMA_V1
        || source_map.first_validation_targets.is_empty()
        || source_map.first_validation_targets.len() > 32
    {
        return Err(CatalogBuildError::new(
            "catalog_source_map_contract_invalid",
            "embedded catalog source map schema or target count is invalid",
        ));
    }
    for directory in [
        &source_map.report_directory,
        &source_map.peer_specimen_directory,
    ] {
        validate_relative_path(directory)?;
    }
    for suffix in [&source_map.report_suffix, &source_map.peer_specimen_suffix] {
        if suffix.is_empty()
            || suffix.len() > 64
            || !suffix.starts_with('.')
            || suffix.contains('/')
            || suffix.contains('\\')
            || suffix.chars().any(char::is_control)
        {
            return Err(CatalogBuildError::new(
                "catalog_source_map_contract_invalid",
                "catalog source suffix is invalid",
            ));
        }
    }
    for rule in &source_map.first_validation_targets {
        let value = match rule {
            FirstTargetRuleV1::ExactId { value }
            | FirstTargetRuleV1::IdPrefix { value }
            | FirstTargetRuleV1::SourceFormat { value } => value,
        };
        if !valid_token(value) {
            return Err(CatalogBuildError::new(
                "catalog_source_map_contract_invalid",
                "catalog first-target selector is invalid",
            ));
        }
    }
    Ok(source_map)
}

fn selected_files(directory: &Path, suffix: &str) -> Result<Vec<PathBuf>, CatalogBuildError> {
    let entries = fs::read_dir(directory).map_err(|error| {
        CatalogBuildError::new(
            "catalog_io_error",
            format!("read catalog source directory failed: {error}"),
        )
    })?;
    let mut selected = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|error| {
            CatalogBuildError::new(
                "catalog_io_error",
                format!("read catalog source entry failed: {error}"),
            )
        })?;
        let name = entry.file_name().into_string().map_err(|_| {
            CatalogBuildError::new(
                "catalog_source_name_invalid",
                "catalog source file names must be UTF-8",
            )
        })?;
        if name.ends_with(suffix) {
            selected.push((name, entry.path()));
        }
    }
    selected.sort_by(|left, right| left.0.cmp(&right.0));
    if selected.len() > MAX_SOURCE_FILES {
        return Err(CatalogBuildError::new(
            "catalog_source_count_invalid",
            "catalog source directory exceeds the file-count bound",
        ));
    }
    Ok(selected.into_iter().map(|(_, path)| path).collect())
}

fn load_source(
    root: &Path,
    path: &Path,
    kind: &str,
    aggregate_bytes: &mut u64,
) -> Result<(Vec<u8>, CatalogSourceReceiptV1), CatalogBuildError> {
    let bytes = read_bounded_regular_file(path, MAX_SOURCE_BYTES, "catalog source")?;
    let byte_length = u64::try_from(bytes.len()).map_err(|_| {
        CatalogBuildError::new(
            "catalog_source_length_invalid",
            "catalog source length is not addressable",
        )
    })?;
    *aggregate_bytes = aggregate_bytes.checked_add(byte_length).ok_or_else(|| {
        CatalogBuildError::new(
            "catalog_aggregate_length_invalid",
            "aggregate catalog source length overflowed",
        )
    })?;
    if *aggregate_bytes > MAX_AGGREGATE_BYTES {
        return Err(CatalogBuildError::new(
            "catalog_sources_too_large",
            "aggregate catalog source bytes exceed the bounded contract",
        ));
    }
    let relative = relative_portable_path(root, path)?;
    let receipt = CatalogSourceReceiptV1 {
        kind: kind.to_owned(),
        path: relative,
        byte_length,
        sha256: sha256_identity(&bytes),
    };
    Ok((bytes, receipt))
}

fn decode_source_json(path: &Path, bytes: &[u8]) -> Result<Value, CatalogBuildError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        CatalogBuildError::new(
            "catalog_source_json_invalid",
            format!(
                "catalog source {} is invalid strict JSON: {error}",
                path.display()
            ),
        )
    })?;
    if !value.is_object() {
        return Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!("catalog source {} must be a JSON object", path.display()),
        ));
    }
    Ok(value)
}

fn case_from_report(value: &Value, path: &Path) -> Result<BenchmarkCaseV2, CatalogBuildError> {
    let object = value.as_object().expect("source object checked above");
    let id = required_string(object.get("source_id"), "source_id", path)?;
    validate_identifier(&id, "report source ID")?;
    let title = optional_string(object.get("title"), "title", path)?.unwrap_or_else(|| id.clone());
    let source_urls = string_array(object.get("source_urls"), "source_urls", path)?;
    let source_format = optional_string(object.get("source_format"), "source_format", path)?;
    let structure_family = optional_string(object.get("family_id"), "family_id", path)?
        .unwrap_or_else(|| "unspecified".to_owned());
    let checksum = optional_string(object.get("sha256"), "sha256", path)?
        .map(|value| validate_source_sha256(&value, path))
        .transpose()?
        .map(|value| format!("sha256:{value}"));
    let source_exists =
        optional_bool(object.get("source_exists"), "source_exists", path)?.unwrap_or(false);
    let file_bytes = optional_u64(object.get("bytes_copied"), "bytes_copied", path)?;
    let truth_class = truth_class_for_format(source_format.as_deref());
    let truth_class_basis = source_format.as_ref().map_or_else(
        || "unknown format".to_owned(),
        |format| format!("inferred from source format: {format}"),
    );
    let source_url = source_urls.first().cloned().unwrap_or_default();
    let acquisition_command = source_urls
        .first()
        .map(|url| format!("# obtain manually from {url}"));
    validate_text_fields(&id, &title, &source_url, &structure_family, &source_urls)?;
    Ok(BenchmarkCaseV2 {
        id,
        title,
        source_url,
        source_version: "unspecified".to_owned(),
        license: "unknown".to_owned(),
        truth_class,
        structure_family,
        analysis_types: Vec::new(),
        checksum,
        local_availability: if source_exists {
            LocalAvailabilityV2::Available
        } else {
            LocalAvailabilityV2::External
        },
        source_format,
        file_bytes,
        size_class: size_class_from_bytes(file_bytes),
        truth_class_basis,
        all_source_urls: source_urls,
        first_validation_target: false,
        verification: base_verification(acquisition_command),
    })
}

fn case_from_peer_specimen(
    root: &Path,
    path: &Path,
    value: &Value,
) -> Result<BenchmarkCaseV2, CatalogBuildError> {
    let object = value.as_object().expect("source object checked above");
    let fallback_id = path
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| name.strip_suffix(".specimen_page.json"))
        .ok_or_else(|| {
            CatalogBuildError::new(
                "catalog_source_name_invalid",
                "peer specimen source name does not match its suffix",
            )
        })?
        .to_owned();
    let id = optional_string(object.get("seed_id"), "seed_id", path)?.unwrap_or(fallback_id);
    validate_identifier(&id, "peer specimen ID")?;
    let specimen_id = optional_string(object.get("specimen_id"), "specimen_id", path)?;
    let title =
        optional_string(object.get("page_title"), "page_title", path)?.unwrap_or_else(|| {
            specimen_id.as_ref().map_or_else(
                || "PEER SPD specimen".to_owned(),
                |value| format!("PEER SPD specimen {value}"),
            )
        });
    let source_url = optional_string(
        object.get("specimen_display_url"),
        "specimen_display_url",
        path,
    )?
    .unwrap_or_default();
    let has_reference = object
        .get("hysteresis_link_candidates")
        .and_then(Value::as_array)
        .is_some_and(|items| !items.is_empty());
    let source_relative = relative_portable_path(root, path)?;
    let all_source_urls = if source_url.is_empty() {
        Vec::new()
    } else {
        vec![source_url.clone()]
    };
    validate_text_fields(&id, &title, &source_url, "rc_column", &all_source_urls)?;
    let acquisition_command = if source_url.is_empty() {
        None
    } else {
        Some(format!(
            "# PEER SPD specimen {} from {source_url}",
            specimen_id.as_deref().unwrap_or("")
        ))
    };
    let mut verification = base_verification(acquisition_command);
    verification.truth_class_verified = true;
    verification.truth_evidence_path = Some(source_relative);
    verification.reference_results_available = has_reference;
    Ok(BenchmarkCaseV2 {
        id,
        title,
        source_url,
        source_version: specimen_id.map_or_else(
            || "unspecified".to_owned(),
            |value| format!("specimen {value}"),
        ),
        license: "unknown".to_owned(),
        truth_class: TruthClassV2::Experimental,
        structure_family: "rc_column".to_owned(),
        analysis_types: vec!["cyclic_quasi_static".to_owned()],
        checksum: None,
        local_availability: LocalAvailabilityV2::Available,
        source_format: Some("peer_spd_specimen_page".to_owned()),
        file_bytes: None,
        size_class: SizeClassV2::Small,
        truth_class_basis: "PEER Structural Performance Database (experimental specimens)"
            .to_owned(),
        all_source_urls,
        first_validation_target: false,
        verification,
    })
}

fn base_verification(acquisition_command: Option<String>) -> VerificationV2 {
    VerificationV2 {
        license_id: None,
        license_url: None,
        license_verified: false,
        truth_class_verified: false,
        truth_evidence_path: None,
        reference_results_available: false,
        reference_results_path: None,
        reference_solver: None,
        reference_solver_version: None,
        acquisition_command,
        runner_id: None,
    }
}

fn mark_first_validation_targets(cases: &mut [BenchmarkCaseV2], rules: &[FirstTargetRuleV1]) {
    for rule in rules {
        if let Some(case) = cases.iter_mut().find(|case| {
            !case.first_validation_target
                && match rule {
                    FirstTargetRuleV1::ExactId { value } => case.id == *value,
                    FirstTargetRuleV1::IdPrefix { value } => case.id.starts_with(value),
                    FirstTargetRuleV1::SourceFormat { value } => {
                        case.source_format.as_deref() == Some(value)
                    }
                }
        }) {
            case.first_validation_target = true;
        }
    }
}

fn validate_unique_cases(cases: &[BenchmarkCaseV2]) -> Result<(), CatalogBuildError> {
    let mut identifiers = BTreeSet::new();
    for case in cases {
        if !identifiers.insert(case.id.as_str()) {
            return Err(CatalogBuildError::new(
                "catalog_duplicate_case_id",
                format!("catalog case ID is duplicated: {}", case.id),
            ));
        }
    }
    Ok(())
}

fn truth_class_for_format(format: Option<&str>) -> TruthClassV2 {
    match format {
        Some("tcl" | "json_graph") => TruthClassV2::IndependentSolver,
        Some("mgt" | "mcb" | "meb") => TruthClassV2::CommercialReference,
        _ => TruthClassV2::GeometryOnly,
    }
}

fn size_class_from_bytes(bytes: Option<u64>) -> SizeClassV2 {
    match bytes {
        None | Some(0) => SizeClassV2::Unknown,
        Some(value) if value < 100 * 1024 => SizeClassV2::Small,
        Some(value) if value < 2 * 1024 * 1024 => SizeClassV2::Medium,
        Some(_) => SizeClassV2::Large,
    }
}

fn required_string(
    value: Option<&Value>,
    field: &str,
    path: &Path,
) -> Result<String, CatalogBuildError> {
    optional_string(value, field, path)?.ok_or_else(|| {
        CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!("catalog source {} requires string {field}", path.display()),
        )
    })
}

fn optional_string(
    value: Option<&Value>,
    field: &str,
    path: &Path,
) -> Result<Option<String>, CatalogBuildError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value.clone())),
        Some(_) => Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!(
                "catalog source {} field {field} must be a string",
                path.display()
            ),
        )),
    }
}

fn optional_bool(
    value: Option<&Value>,
    field: &str,
    path: &Path,
) -> Result<Option<bool>, CatalogBuildError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Bool(value)) => Ok(Some(*value)),
        Some(_) => Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!(
                "catalog source {} field {field} must be boolean",
                path.display()
            ),
        )),
    }
}

fn optional_u64(
    value: Option<&Value>,
    field: &str,
    path: &Path,
) -> Result<Option<u64>, CatalogBuildError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Number(value)) => value
            .as_u64()
            .filter(|number| *number > 0)
            .map(Some)
            .ok_or_else(|| {
                CatalogBuildError::new(
                    "catalog_source_contract_invalid",
                    format!(
                        "catalog source {} field {field} must be a positive integer",
                        path.display()
                    ),
                )
            }),
        Some(_) => Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!(
                "catalog source {} field {field} must be a positive integer",
                path.display()
            ),
        )),
    }
}

fn string_array(
    value: Option<&Value>,
    field: &str,
    path: &Path,
) -> Result<Vec<String>, CatalogBuildError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let array = value.as_array().ok_or_else(|| {
        CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!(
                "catalog source {} field {field} must be an array",
                path.display()
            ),
        )
    })?;
    let mut output = Vec::new();
    for item in array {
        if let Some(item) = item.as_str() {
            output.push(item.to_owned());
        }
    }
    Ok(output)
}

fn validate_source_sha256(value: &str, path: &Path) -> Result<String, CatalogBuildError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(CatalogBuildError::new(
            "catalog_source_checksum_invalid",
            format!("catalog source {} has an invalid SHA-256", path.display()),
        ));
    }
    Ok(value.to_owned())
}

fn validate_text_fields(
    id: &str,
    title: &str,
    source_url: &str,
    structure_family: &str,
    source_urls: &[String],
) -> Result<(), CatalogBuildError> {
    if title.trim().is_empty()
        || structure_family.trim().is_empty()
        || [title, source_url, structure_family]
            .into_iter()
            .chain(source_urls.iter().map(String::as_str))
            .any(|value| value.len() > 16 * 1024 || value.chars().any(char::is_control))
    {
        return Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!("catalog case {id} has an invalid text field"),
        ));
    }
    Ok(())
}

fn validate_identifier(value: &str, label: &str) -> Result<(), CatalogBuildError> {
    if !valid_token(value) {
        return Err(CatalogBuildError::new(
            "catalog_source_contract_invalid",
            format!("{label} is not a bounded portable token"),
        ));
    }
    Ok(())
}

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 160
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn build_receipt(
    generated: &GeneratedCatalogV2,
    action: &str,
) -> Result<BenchmarkCatalogBuildReceiptV1, CatalogBuildError> {
    let source_inventory_sha256 = {
        let canonical = canonical_struct(&generated.sources, "catalog_receipt_encode_failed")?;
        sha256_identity(canonical.as_bytes())
    };
    let mut receipt = BenchmarkCatalogBuildReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: action.to_owned(),
        source_map_schema_version: generated.source_map_schema_version.clone(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        generated_at: generated.generated_at.clone(),
        generated_by: GENERATED_BY.to_owned(),
        report_count: generated.report_count,
        peer_specimen_count: generated.peer_specimen_count,
        case_count: generated.report_count + generated.peer_specimen_count,
        source_inventory_sha256,
        output_catalog_sha256: sha256_identity(&generated.bytes),
        first_validation_targets: generated.first_validation_targets.clone(),
        sources: generated.sources.clone(),
        deterministic: true,
        sources_unchanged: true,
        commands_executed: 0,
        network_access_count: 0,
        claim_boundary: CLAIM_BOUNDARY.to_owned(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &BenchmarkCatalogBuildReceiptV1,
) -> Result<String, CatalogBuildError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        CatalogBuildError::new(
            "catalog_receipt_encode_failed",
            format!("project catalog receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .expect("serialized catalog receipt is an object")
        .remove("receipt_hash");
    Ok(sha256_identity(
        canonicalize_model_ir_v2(&value)
            .map_err(|error| {
                CatalogBuildError::new(
                    "catalog_receipt_encode_failed",
                    format!("canonicalize catalog receipt failed: {error}"),
                )
            })?
            .as_bytes(),
    ))
}

fn canonical_struct<T: Serialize>(
    value: &T,
    code: &'static str,
) -> Result<String, CatalogBuildError> {
    let value = serde_json::to_value(value).map_err(|error| {
        CatalogBuildError::new(code, format!("project canonical JSON failed: {error}"))
    })?;
    canonicalize_model_ir_v2(&value)
        .map_err(|error| CatalogBuildError::new(code, format!("canonical JSON failed: {error}")))
}

fn resolve_directory(root: &Path, relative: &str) -> Result<PathBuf, CatalogBuildError> {
    validate_relative_path(relative)?;
    let mut resolved = root.to_path_buf();
    for component in Path::new(relative).components() {
        let Component::Normal(name) = component else {
            return Err(unsafe_path_error(relative));
        };
        resolved.push(name);
        verify_real_directory(&resolved, "catalog source directory")?;
    }
    Ok(resolved)
}

fn resolve_optional_directory(
    root: &Path,
    relative: &str,
) -> Result<Option<PathBuf>, CatalogBuildError> {
    validate_relative_path(relative)?;
    let mut resolved = root.to_path_buf();
    let components = Path::new(relative).components().collect::<Vec<_>>();
    for component in &components {
        let Component::Normal(name) = component else {
            return Err(unsafe_path_error(relative));
        };
        resolved.push(name);
        match fs::symlink_metadata(&resolved) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() || !metadata.is_dir() {
                    return Err(CatalogBuildError::new(
                        "catalog_unsafe_path",
                        "catalog source directory must be a real non-symlink directory",
                    ));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(None);
            }
            Err(error) => {
                return Err(CatalogBuildError::new(
                    "catalog_io_error",
                    format!("inspect optional catalog directory failed: {error}"),
                ));
            }
        }
    }
    Ok(Some(resolved))
}

fn validate_relative_path(relative: &str) -> Result<(), CatalogBuildError> {
    if relative.is_empty()
        || relative.contains('\\')
        || relative.chars().any(char::is_control)
        || Path::new(relative).is_absolute()
        || !Path::new(relative)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return Err(unsafe_path_error(relative));
    }
    Ok(())
}

fn relative_portable_path(root: &Path, path: &Path) -> Result<String, CatalogBuildError> {
    let relative = path.strip_prefix(root).map_err(|_| {
        CatalogBuildError::new(
            "catalog_unsafe_path",
            "catalog source escaped the declared source root",
        )
    })?;
    let mut segments = Vec::new();
    for component in relative.components() {
        let Component::Normal(segment) = component else {
            return Err(CatalogBuildError::new(
                "catalog_unsafe_path",
                "catalog source path is not portable",
            ));
        };
        segments.push(segment.to_str().ok_or_else(|| {
            CatalogBuildError::new(
                "catalog_source_name_invalid",
                "catalog source path must be UTF-8",
            )
        })?);
    }
    Ok(segments.join("/"))
}

fn validate_generated_at(value: &str) -> Result<(), CatalogBuildError> {
    if value.trim() != value
        || value.chars().any(char::is_control)
        || OffsetDateTime::parse(value, &Rfc3339).is_err()
    {
        return Err(CatalogBuildError::new(
            "catalog_generated_at_invalid",
            "generated-at must be an exact RFC 3339 timestamp",
        ));
    }
    Ok(())
}

fn verify_real_directory(path: &Path, label: &str) -> Result<(), CatalogBuildError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        CatalogBuildError::new(
            "catalog_io_error",
            format!("read {label} metadata failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(CatalogBuildError::new(
            "catalog_unsafe_path",
            format!("{label} must be a real non-symlink directory"),
        ));
    }
    Ok(())
}

fn read_bounded_regular_file(
    path: &Path,
    limit: u64,
    label: &str,
) -> Result<Vec<u8>, CatalogBuildError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        CatalogBuildError::new(
            "catalog_io_error",
            format!("read {label} metadata failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(CatalogBuildError::new(
            "catalog_source_not_bounded_regular_file",
            format!("{label} must be a bounded regular non-symlink file"),
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(path).map_err(|error| {
        CatalogBuildError::new(
            "catalog_io_error",
            format!("open {label} without symlink traversal failed: {error}"),
        )
    })?;
    let opened = file.metadata().map_err(|error| {
        CatalogBuildError::new(
            "catalog_io_error",
            format!("read opened {label} metadata failed: {error}"),
        )
    })?;
    if !opened.is_file() || opened.len() != metadata.len() || opened.len() > limit {
        return Err(CatalogBuildError::new(
            "catalog_source_changed",
            format!("{label} changed while it was being opened"),
        ));
    }
    let capacity = usize::try_from(opened.len()).map_err(|_| {
        CatalogBuildError::new(
            "catalog_source_length_invalid",
            format!("{label} length is not addressable"),
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| {
            CatalogBuildError::new("catalog_io_error", format!("read {label} failed: {error}"))
        })?;
    if u64::try_from(bytes.len()).map_or(true, |length| length > limit) {
        return Err(CatalogBuildError::new(
            "catalog_source_changed",
            format!("{label} grew beyond its bound while reading"),
        ));
    }
    Ok(bytes)
}

fn atomic_replace_catalog(path: &Path, bytes: &[u8]) -> Result<(), CatalogBuildError> {
    let parent = path.parent().ok_or_else(|| {
        CatalogBuildError::new(
            "catalog_output_path_invalid",
            "catalog output must have a parent directory",
        )
    })?;
    verify_real_directory(parent, "catalog output parent")?;
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
            return Err(CatalogBuildError::new(
                "catalog_output_path_invalid",
                "catalog output may be absent or a regular non-symlink file only",
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            return Err(CatalogBuildError::new(
                "catalog_io_error",
                format!("inspect catalog output failed: {error}"),
            ));
        }
    }
    let stage = create_stage_file(parent)?;
    let mut guard = OutputStageGuard::new(stage.clone());
    let mut options = OpenOptions::new();
    options.write(true);
    let mut file = options.open(&stage).map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_create_failed",
            format!("open catalog output stage failed: {error}"),
        )
    })?;
    file.write_all(bytes).map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_write_failed",
            format!("write catalog output failed: {error}"),
        )
    })?;
    file.sync_all().map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_sync_failed",
            format!("sync catalog output failed: {error}"),
        )
    })?;
    drop(file);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&stage, fs::Permissions::from_mode(0o644)).map_err(|error| {
            CatalogBuildError::new(
                "catalog_output_permission_failed",
                format!("normalize catalog output permissions failed: {error}"),
            )
        })?;
    }
    File::open(&stage)
        .and_then(|output| output.sync_all())
        .map_err(|error| {
            CatalogBuildError::new(
                "catalog_output_sync_failed",
                format!("sync normalized catalog output metadata failed: {error}"),
            )
        })?;
    fs::rename(&stage, path).map_err(|error| {
        CatalogBuildError::new(
            "catalog_output_publish_failed",
            format!("atomically publish benchmark catalog failed: {error}"),
        )
    })?;
    guard.disarm();
    sync_directory(parent)
}

fn create_stage_file(parent: &Path) -> Result<PathBuf, CatalogBuildError> {
    for _ in 0..1024 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            ".structural-catalog-stage.{}.{}",
            std::process::id(),
            sequence
        ));
        let mut options = OpenOptions::new();
        options.create_new(true).write(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&path) {
            Ok(file) => {
                drop(file);
                return Ok(path);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(CatalogBuildError::new(
                    "catalog_output_create_failed",
                    format!("create catalog output stage failed: {error}"),
                ));
            }
        }
    }
    Err(CatalogBuildError::new(
        "catalog_output_create_failed",
        "could not allocate a unique catalog output stage",
    ))
}

fn sync_directory(path: &Path) -> Result<(), CatalogBuildError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| {
            CatalogBuildError::new(
                "catalog_output_sync_failed",
                format!("sync catalog output directory failed: {error}"),
            )
        })
}

fn unsafe_path_error(relative: &str) -> CatalogBuildError {
    CatalogBuildError::new(
        "catalog_source_map_path_invalid",
        format!("catalog source path is unsafe: {relative}"),
    )
}

struct OutputStageGuard {
    path: PathBuf,
    active: bool,
}

impl OutputStageGuard {
    fn new(path: PathBuf) -> Self {
        Self { path, active: true }
    }

    fn disarm(&mut self) {
        self.active = false;
    }
}

impl Drop for OutputStageGuard {
    fn drop(&mut self) {
        if self.active {
            let _ignored = fs::remove_file(&self.path);
        }
    }
}
