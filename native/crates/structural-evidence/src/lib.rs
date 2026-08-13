//! Deterministic, fail-closed Workbench evidence-bundle construction.

#![forbid(unsafe_code)]

use std::collections::BTreeSet;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;

use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const SOURCE_MAP_SCHEMA_V1: &str = "structural-workbench-evidence-source-map.v1";
const MANIFEST_SCHEMA_V1: &str = "workbench-evidence-manifest.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-evidence-bundle-build-receipt.v1";
const MAX_SOURCE_MAP_BYTES: usize = 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_AGGREGATE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_ARTIFACTS: usize = 128;
const CLAIM_BOUNDARY: &str = "copies_only_the_fixed_language_neutral_source_map_after_strict_json_single_commit_sensitive_data_and_checksum_checks_and_never_modifies_sources_or_infers_readiness";
const SOURCE_MAP_BYTES: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../evidence/workbench-evidence-sources-v1.json"
));
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);
static EMAIL_PATTERN: OnceLock<Regex> = OnceLock::new();
static LONG_HEX_PATTERN: OnceLock<Regex> = OnceLock::new();

/// Stable native evidence-builder failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvidenceBuildError {
    pub code: &'static str,
    pub detail: String,
}

impl EvidenceBuildError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for EvidenceBuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for EvidenceBuildError {}

/// Explicit deterministic build inputs.
#[derive(Clone, Copy, Debug)]
pub struct EvidenceBundleBuildRequest<'a> {
    pub source_root: &'a Path,
    pub output: &'a Path,
    pub generated_at: &'a str,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EvidenceSourceDefinitionV1 {
    id: String,
    label: String,
    source_path: String,
    bundle_path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EvidenceSourceMapV1 {
    schema_version: String,
    artifacts: Vec<EvidenceSourceDefinitionV1>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct EvidenceBuildArtifactReceiptV1 {
    pub id: String,
    pub source_path: String,
    pub bundle_path: String,
    pub byte_length: u64,
    pub sha256: String,
}

/// Self-hashed result of a read-only check or an atomically published build.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct EvidenceBundleBuildReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub source_map_schema_version: String,
    pub source_map_sha256: String,
    pub source_commit_sha: String,
    pub artifact_count: usize,
    pub aggregate_source_bytes: u64,
    pub single_source_commit: bool,
    pub sensitive_data_scan_passed: bool,
    pub sources_unchanged: bool,
    pub output_manifest_sha256: Option<String>,
    pub artifacts: Vec<EvidenceBuildArtifactReceiptV1>,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

#[derive(Clone, Debug, Serialize)]
struct EvidenceManifestArtifactV1 {
    id: String,
    label: String,
    path: String,
    source_path: String,
    sha256: String,
    read_only: bool,
}

#[derive(Clone, Debug, Serialize)]
struct EvidenceManifestV1 {
    schema_version: String,
    generated_at: String,
    source_commit_sha: String,
    artifacts: Vec<EvidenceManifestArtifactV1>,
}

#[derive(Debug)]
struct LoadedSourceV1 {
    definition: EvidenceSourceDefinitionV1,
    bytes: Vec<u8>,
    byte_length: u64,
    sha256: String,
    source_commit_sha: String,
}

#[derive(Debug)]
struct LoadedSourcesV1 {
    source_map_schema_version: String,
    source_commit_sha: String,
    aggregate_source_bytes: u64,
    sources: Vec<LoadedSourceV1>,
}

/// Check every mapped source without writing output.
///
/// # Errors
///
/// Rejects source-map drift, unsafe paths, symlinks, oversized or malformed JSON, mixed commits,
/// sensitive-data signals, and any missing source.
pub fn check_evidence_sources(
    source_root: &Path,
) -> Result<EvidenceBundleBuildReceiptV1, EvidenceBuildError> {
    let loaded = load_sources(source_root)?;
    build_receipt(&loaded, "check", None)
}

/// Copy verified source bytes and atomically publish one immutable evidence bundle.
///
/// Existing output is never deleted or replaced. `generated_at` is explicit so identical inputs
/// produce identical output bytes.
///
/// # Errors
///
/// Returns the source-check errors from [`check_evidence_sources`] and rejects invalid timestamps,
/// unsafe/existing output, partial publication, or filesystem durability failures.
pub fn build_evidence_bundle(
    request: &EvidenceBundleBuildRequest<'_>,
) -> Result<EvidenceBundleBuildReceiptV1, EvidenceBuildError> {
    validate_generated_at(request.generated_at)?;
    let loaded = load_sources(request.source_root)?;
    let output_parent = request.output.parent().ok_or_else(|| {
        EvidenceBuildError::new(
            "evidence_output_path_invalid",
            "evidence bundle output must have a parent directory",
        )
    })?;
    verify_real_directory(output_parent, "evidence output parent")?;
    if path_entry_exists(request.output)? {
        return Err(EvidenceBuildError::new(
            "evidence_output_exists",
            "evidence bundle output already exists and will not be replaced",
        ));
    }

    let stage = create_stage_directory(output_parent)?;
    let mut guard = OutputStageGuard::new(stage.clone());
    let manifest = EvidenceManifestV1 {
        schema_version: MANIFEST_SCHEMA_V1.to_owned(),
        generated_at: request.generated_at.to_owned(),
        source_commit_sha: loaded.source_commit_sha.clone(),
        artifacts: loaded
            .sources
            .iter()
            .map(|source| EvidenceManifestArtifactV1 {
                id: source.definition.id.clone(),
                label: source.definition.label.clone(),
                path: source.definition.bundle_path.clone(),
                source_path: source.definition.source_path.clone(),
                sha256: source.sha256.clone(),
                read_only: true,
            })
            .collect(),
    };
    for source in &loaded.sources {
        let destination = create_destination_path(&stage, &source.definition.bundle_path)?;
        write_read_only_file(&destination, &source.bytes)?;
    }
    let mut manifest_bytes = serde_json::to_vec_pretty(&manifest).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_manifest_encode_failed",
            format!("encode evidence manifest failed: {error}"),
        )
    })?;
    manifest_bytes.push(b'\n');
    write_read_only_file(&stage.join("manifest.json"), &manifest_bytes)?;
    sync_directory(&stage)?;
    fs::rename(&stage, request.output).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_output_publish_failed",
            format!("atomically publish evidence bundle failed: {error}"),
        )
    })?;
    guard.disarm();
    sync_directory(output_parent)?;
    build_receipt(&loaded, "build", Some(sha256_identity(&manifest_bytes)))
}

/// Encode a receipt as deterministic canonical JSON.
///
/// # Errors
///
/// Returns an error only if the receipt cannot satisfy canonical JSON rules.
pub fn canonical_receipt_json(
    receipt: &EvidenceBundleBuildReceiptV1,
) -> Result<String, EvidenceBuildError> {
    canonical_struct(receipt, "evidence_receipt_encode_failed")
}

fn load_sources(source_root: &Path) -> Result<LoadedSourcesV1, EvidenceBuildError> {
    verify_real_directory(source_root, "evidence source root")?;
    let source_map = parse_source_map()?;
    let mut aggregate = 0_u64;
    let mut commits = BTreeSet::new();
    let mut sources = Vec::with_capacity(source_map.artifacts.len());
    for definition in source_map.artifacts {
        let path = resolve_source_path(source_root, &definition.source_path)?;
        let bytes = read_bounded_regular_file(&path, MAX_SOURCE_BYTES)?;
        let byte_length = u64::try_from(bytes.len()).map_err(|_| {
            EvidenceBuildError::new(
                "evidence_source_length_invalid",
                format!("source {} length is not addressable", definition.id),
            )
        })?;
        aggregate = aggregate.checked_add(byte_length).ok_or_else(|| {
            EvidenceBuildError::new(
                "evidence_aggregate_length_invalid",
                "aggregate evidence source length overflowed",
            )
        })?;
        if aggregate > MAX_AGGREGATE_BYTES {
            return Err(EvidenceBuildError::new(
                "evidence_sources_too_large",
                "aggregate evidence source bytes exceed the bounded contract",
            ));
        }
        let value = decode_json_strict(&bytes).map_err(|error| {
            EvidenceBuildError::new(
                "evidence_source_json_invalid",
                format!("source {} is invalid strict JSON: {error}", definition.id),
            )
        })?;
        if !value.is_object() {
            return Err(EvidenceBuildError::new(
                "evidence_source_contract_invalid",
                format!("source {} must contain a JSON object", definition.id),
            ));
        }
        let source_commit_sha = value
            .get("source_commit_sha")
            .and_then(Value::as_str)
            .filter(|value| valid_commit(value))
            .ok_or_else(|| {
                EvidenceBuildError::new(
                    "evidence_source_commit_invalid",
                    format!(
                        "source {} has no exact lowercase source_commit_sha",
                        definition.id
                    ),
                )
            })?
            .to_owned();
        scan_sensitive(&definition.id, &bytes, &value)?;
        commits.insert(source_commit_sha.clone());
        sources.push(LoadedSourceV1 {
            definition,
            sha256: sha256_identity(&bytes),
            bytes,
            byte_length,
            source_commit_sha,
        });
    }
    if commits.len() != 1 {
        let short = commits
            .iter()
            .map(|commit| commit.chars().take(8).collect::<String>())
            .collect::<Vec<_>>()
            .join(", ");
        return Err(EvidenceBuildError::new(
            "evidence_source_commit_mismatch",
            format!(
                "evidence sources must share one commit; found {} ({short})",
                commits.len()
            ),
        ));
    }
    let source_commit_sha = commits.into_iter().next().ok_or_else(|| {
        EvidenceBuildError::new(
            "evidence_source_commit_invalid",
            "evidence source map produced no commit",
        )
    })?;
    if sources
        .iter()
        .any(|source| source.source_commit_sha != source_commit_sha)
    {
        return Err(EvidenceBuildError::new(
            "evidence_source_commit_mismatch",
            "evidence source commit projection is inconsistent",
        ));
    }
    Ok(LoadedSourcesV1 {
        source_map_schema_version: source_map.schema_version,
        source_commit_sha,
        aggregate_source_bytes: aggregate,
        sources,
    })
}

fn parse_source_map() -> Result<EvidenceSourceMapV1, EvidenceBuildError> {
    if SOURCE_MAP_BYTES.len() > MAX_SOURCE_MAP_BYTES {
        return Err(EvidenceBuildError::new(
            "evidence_source_map_too_large",
            "embedded evidence source map exceeds its bound",
        ));
    }
    let value = decode_json_strict(SOURCE_MAP_BYTES).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_source_map_json_invalid",
            format!("embedded evidence source map is invalid: {error}"),
        )
    })?;
    let source_map: EvidenceSourceMapV1 = serde_json::from_value(value).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_source_map_contract_invalid",
            format!("embedded evidence source map fields are invalid: {error}"),
        )
    })?;
    if source_map.schema_version != SOURCE_MAP_SCHEMA_V1
        || source_map.artifacts.is_empty()
        || source_map.artifacts.len() > MAX_ARTIFACTS
    {
        return Err(EvidenceBuildError::new(
            "evidence_source_map_contract_invalid",
            "embedded evidence source map schema or artifact count is invalid",
        ));
    }
    let mut identifiers = BTreeSet::new();
    let mut source_paths = BTreeSet::new();
    let mut bundle_paths = BTreeSet::new();
    for definition in &source_map.artifacts {
        if !valid_identifier(&definition.id)
            || definition.label.trim().is_empty()
            || definition.label.chars().any(char::is_control)
        {
            return Err(EvidenceBuildError::new(
                "evidence_source_map_contract_invalid",
                format!(
                    "source-map artifact {} has an invalid ID or label",
                    definition.id
                ),
            ));
        }
        validate_relative_path(&definition.source_path, "source")?;
        validate_relative_path(&definition.bundle_path, "bundle")?;
        if definition.bundle_path == "manifest.json"
            || !identifiers.insert(definition.id.as_str())
            || !source_paths.insert(definition.source_path.as_str())
            || !bundle_paths.insert(definition.bundle_path.as_str())
        {
            return Err(EvidenceBuildError::new(
                "evidence_source_map_contract_invalid",
                format!(
                    "source-map artifact {} collides with another entry",
                    definition.id
                ),
            ));
        }
    }
    Ok(source_map)
}

fn build_receipt(
    loaded: &LoadedSourcesV1,
    action: &str,
    output_manifest_sha256: Option<String>,
) -> Result<EvidenceBundleBuildReceiptV1, EvidenceBuildError> {
    let mut receipt = EvidenceBundleBuildReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: action.to_owned(),
        source_map_schema_version: loaded.source_map_schema_version.clone(),
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        source_commit_sha: loaded.source_commit_sha.clone(),
        artifact_count: loaded.sources.len(),
        aggregate_source_bytes: loaded.aggregate_source_bytes,
        single_source_commit: true,
        sensitive_data_scan_passed: true,
        sources_unchanged: true,
        output_manifest_sha256,
        artifacts: loaded
            .sources
            .iter()
            .map(|source| EvidenceBuildArtifactReceiptV1 {
                id: source.definition.id.clone(),
                source_path: source.definition.source_path.clone(),
                bundle_path: source.definition.bundle_path.clone(),
                byte_length: source.byte_length,
                sha256: source.sha256.clone(),
            })
            .collect(),
        claim_boundary: CLAIM_BOUNDARY.to_owned(),
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

fn hash_without_receipt_hash(
    receipt: &EvidenceBundleBuildReceiptV1,
) -> Result<String, EvidenceBuildError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_receipt_encode_failed",
            format!("project evidence receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .expect("serialized evidence receipt is an object")
        .remove("receipt_hash");
    Ok(sha256_identity(
        canonicalize_model_ir_v2(&value)
            .map_err(|error| {
                EvidenceBuildError::new(
                    "evidence_receipt_encode_failed",
                    format!("canonicalize evidence receipt failed: {error}"),
                )
            })?
            .as_bytes(),
    ))
}

fn canonical_struct<T: Serialize>(
    value: &T,
    code: &'static str,
) -> Result<String, EvidenceBuildError> {
    let value = serde_json::to_value(value).map_err(|error| {
        EvidenceBuildError::new(code, format!("project canonical JSON failed: {error}"))
    })?;
    canonicalize_model_ir_v2(&value)
        .map_err(|error| EvidenceBuildError::new(code, format!("canonical JSON failed: {error}")))
}

fn scan_sensitive(id: &str, bytes: &[u8], value: &Value) -> Result<(), EvidenceBuildError> {
    let text = std::str::from_utf8(bytes).map_err(|_| {
        EvidenceBuildError::new(
            "evidence_source_json_invalid",
            format!("source {id} is not UTF-8"),
        )
    })?;
    let email = EMAIL_PATTERN.get_or_init(|| {
        Regex::new(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
            .expect("fixed email regex")
    });
    if email.is_match(text) {
        return Err(sensitive_error(id, "contains an email-like value"));
    }
    let long_hex = LONG_HEX_PATTERN
        .get_or_init(|| Regex::new(r"(?i)[0-9a-f]{32,}").expect("fixed long-hex regex"));
    let without_hashes = long_hex.replace_all(text, "");
    if contains_credit_card_like_digits(&without_hashes) {
        return Err(sensitive_error(
            id,
            "contains a credit-card-like digit sequence",
        ));
    }
    if let Some(key) = first_sensitive_key(value) {
        return Err(sensitive_error(
            id,
            &format!("contains sensitive key {key}"),
        ));
    }
    Ok(())
}

fn first_sensitive_key(value: &Value) -> Option<String> {
    match value {
        Value::Array(items) => items.iter().find_map(first_sensitive_key),
        Value::Object(object) => {
            for (key, item) in object {
                let normalized = key.to_ascii_lowercase().replace('-', "_");
                if normalized.contains("password")
                    || normalized.contains("passwd")
                    || normalized.contains("secret")
                    || normalized.contains("api_key")
                    || normalized.contains("apikey")
                    || normalized.contains("access_token")
                    || normalized.contains("private_key")
                    || normalized.contains("client_secret")
                    || normalized == "ssn"
                    || normalized.contains("social_security")
                {
                    return Some(key.clone());
                }
                if let Some(found) = first_sensitive_key(item) {
                    return Some(found);
                }
            }
            None
        }
        _ => None,
    }
}

fn contains_credit_card_like_digits(text: &str) -> bool {
    let bytes = text.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        if !bytes[index].is_ascii_digit() {
            index += 1;
            continue;
        }
        let mut cursor = index;
        let mut digits = 0_usize;
        while cursor < bytes.len()
            && (bytes[cursor].is_ascii_digit() || matches!(bytes[cursor], b' ' | b'-'))
        {
            if bytes[cursor].is_ascii_digit() {
                digits += 1;
            }
            cursor += 1;
        }
        if (13..=16).contains(&digits) {
            return true;
        }
        index = cursor.max(index + 1);
    }
    false
}

fn sensitive_error(id: &str, detail: &str) -> EvidenceBuildError {
    EvidenceBuildError::new(
        "evidence_sensitive_data_detected",
        format!("sensitive-data gate rejected {id}: {detail}"),
    )
}

fn resolve_source_path(root: &Path, relative: &str) -> Result<PathBuf, EvidenceBuildError> {
    validate_relative_path(relative, "source")?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut resolved = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(unsafe_path_error(relative));
        };
        resolved.push(name);
        if index + 1 < components.len() {
            verify_real_directory(&resolved, "evidence source parent")?;
        }
    }
    Ok(resolved)
}

fn create_destination_path(root: &Path, relative: &str) -> Result<PathBuf, EvidenceBuildError> {
    validate_relative_path(relative, "bundle")?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut resolved = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(unsafe_path_error(relative));
        };
        resolved.push(name);
        if index + 1 < components.len() && !path_entry_exists(&resolved)? {
            fs::create_dir(&resolved).map_err(|error| {
                EvidenceBuildError::new(
                    "evidence_output_create_failed",
                    format!("create evidence bundle directory failed: {error}"),
                )
            })?;
        }
        if index + 1 < components.len() {
            verify_real_directory(&resolved, "evidence bundle parent")?;
        }
    }
    Ok(resolved)
}

fn validate_relative_path(relative: &str, kind: &str) -> Result<(), EvidenceBuildError> {
    if relative.is_empty()
        || relative.contains('\\')
        || relative.chars().any(char::is_control)
        || Path::new(relative).is_absolute()
        || !Path::new(relative)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return Err(EvidenceBuildError::new(
            "evidence_source_map_path_invalid",
            format!("evidence {kind} path is unsafe: {relative}"),
        ));
    }
    Ok(())
}

fn validate_generated_at(value: &str) -> Result<(), EvidenceBuildError> {
    if value.trim() != value
        || value.chars().any(char::is_control)
        || OffsetDateTime::parse(value, &Rfc3339).is_err()
    {
        return Err(EvidenceBuildError::new(
            "evidence_generated_at_invalid",
            "generated-at must be an exact RFC 3339 timestamp",
        ));
    }
    Ok(())
}

fn verify_real_directory(path: &Path, label: &str) -> Result<(), EvidenceBuildError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_io_error",
            format!("read {label} metadata failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(EvidenceBuildError::new(
            "evidence_unsafe_path",
            format!("{label} must be a real non-symlink directory"),
        ));
    }
    Ok(())
}

fn read_bounded_regular_file(path: &Path, limit: u64) -> Result<Vec<u8>, EvidenceBuildError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_io_error",
            format!("read evidence source metadata failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(EvidenceBuildError::new(
            "evidence_source_not_bounded_regular_file",
            "evidence source must be a bounded regular non-symlink file",
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
        EvidenceBuildError::new(
            "evidence_io_error",
            format!("open evidence source without symlink traversal failed: {error}"),
        )
    })?;
    let opened = file.metadata().map_err(|error| {
        EvidenceBuildError::new(
            "evidence_io_error",
            format!("read opened evidence source metadata failed: {error}"),
        )
    })?;
    if !opened.is_file() || opened.len() != metadata.len() || opened.len() > limit {
        return Err(EvidenceBuildError::new(
            "evidence_source_changed",
            "evidence source changed while it was being opened",
        ));
    }
    let capacity = usize::try_from(opened.len()).map_err(|_| {
        EvidenceBuildError::new(
            "evidence_source_length_invalid",
            "evidence source length is not addressable",
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| {
            EvidenceBuildError::new(
                "evidence_io_error",
                format!("read evidence source failed: {error}"),
            )
        })?;
    if u64::try_from(bytes.len()).map_or(true, |length| length > limit) {
        return Err(EvidenceBuildError::new(
            "evidence_source_changed",
            "evidence source grew beyond its bound while reading",
        ));
    }
    Ok(bytes)
}

fn create_stage_directory(parent: &Path) -> Result<PathBuf, EvidenceBuildError> {
    for _ in 0..1024 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            ".structural-evidence-stage.{}.{}",
            std::process::id(),
            sequence
        ));
        match fs::create_dir(&path) {
            Ok(()) => return Ok(path),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(EvidenceBuildError::new(
                    "evidence_output_create_failed",
                    format!("create evidence bundle stage failed: {error}"),
                ));
            }
        }
    }
    Err(EvidenceBuildError::new(
        "evidence_output_create_failed",
        "could not allocate a unique evidence bundle stage",
    ))
}

fn write_read_only_file(path: &Path, bytes: &[u8]) -> Result<(), EvidenceBuildError> {
    let mut options = OpenOptions::new();
    options.create_new(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_output_create_failed",
            format!("create evidence bundle file failed: {error}"),
        )
    })?;
    file.write_all(bytes).map_err(|error| {
        EvidenceBuildError::new(
            "evidence_output_write_failed",
            format!("write evidence bundle file failed: {error}"),
        )
    })?;
    file.sync_all().map_err(|error| {
        EvidenceBuildError::new(
            "evidence_output_sync_failed",
            format!("sync evidence bundle file failed: {error}"),
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o444)).map_err(|error| {
            EvidenceBuildError::new(
                "evidence_output_permission_failed",
                format!("set evidence bundle file read-only failed: {error}"),
            )
        })?;
    }
    Ok(())
}

fn sync_directory(path: &Path) -> Result<(), EvidenceBuildError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| {
            EvidenceBuildError::new(
                "evidence_output_sync_failed",
                format!("sync evidence bundle directory failed: {error}"),
            )
        })
}

fn path_entry_exists(path: &Path) -> Result<bool, EvidenceBuildError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(EvidenceBuildError::new(
            "evidence_io_error",
            format!("inspect evidence path failed: {error}"),
        )),
    }
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 160
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn valid_commit(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn unsafe_path_error(relative: &str) -> EvidenceBuildError {
    EvidenceBuildError::new(
        "evidence_source_map_path_invalid",
        format!("evidence path is unsafe: {relative}"),
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
            let _ignored = fs::remove_dir_all(&self.path);
        }
    }
}
