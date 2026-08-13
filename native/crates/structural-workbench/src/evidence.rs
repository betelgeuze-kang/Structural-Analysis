//! Hash-bound, read-only evidence bundle browsing for the native Workbench.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Component, Path, PathBuf};

use serde::Deserialize;
use serde_json::{json, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

use crate::{read_bounded_regular_file, WorkbenchError};

const MANIFEST_FILE: &str = "manifest.json";
const MANIFEST_SCHEMA_V1: &str = "workbench-evidence-manifest.v1";
const BUNDLE_VIEW_SCHEMA_V1: &str = "structural-native-evidence-bundle-view.v1";
const ARTIFACT_VIEW_SCHEMA_V1: &str = "structural-native-evidence-artifact-view.v1";
const MAX_MANIFEST_BYTES: u64 = 1024 * 1024;
const MAX_ARTIFACT_BYTES: u64 = 16 * 1024 * 1024;
const MAX_AGGREGATE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_ARTIFACTS: usize = 128;
const MAX_AS_OF_UNIX_SECONDS: i64 = 253_402_300_799;
const MAX_EVIDENCE_AGE_SECONDS: i64 = 21 * 24 * 60 * 60;
const CLAIM_BOUNDARY: &str = "read_only_hash_bound_evidence_bundle_interpretation_never_promotes_missing_mismatched_blocked_or_signal_free_sources_and_does_not_generate_or_approve_evidence";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EvidenceManifestArtifactV1 {
    id: String,
    label: String,
    path: String,
    source_path: String,
    sha256: String,
    read_only: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EvidenceManifestV1 {
    schema_version: String,
    generated_at: String,
    source_commit_sha: String,
    artifacts: Vec<EvidenceManifestArtifactV1>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EvidenceGateV1 {
    Ready,
    Blocked,
    Unavailable,
}

impl EvidenceGateV1 {
    const fn label(self) -> &'static str {
        match self {
            Self::Ready => "ready",
            Self::Blocked => "blocked",
            Self::Unavailable => "unavailable",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EvidenceFreshnessV1 {
    Fresh,
    Stale,
    Unknown,
}

impl EvidenceFreshnessV1 {
    const fn label(self) -> &'static str {
        match self {
            Self::Fresh => "fresh",
            Self::Stale => "stale",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug)]
struct EvidenceFactsV1 {
    gate: EvidenceGateV1,
    freshness: EvidenceFreshnessV1,
    stale_reason: Option<String>,
    status: Option<String>,
    launch_ready: Option<bool>,
    release_ready: Option<bool>,
    contract_pass: Option<bool>,
    reason_code: Option<String>,
    evidence_fresh: Option<bool>,
    blockers: Vec<String>,
    generated_at: Option<String>,
    source_commit_sha: String,
    summary_line: Option<String>,
    claim_boundary: Option<String>,
}

#[derive(Debug)]
struct LoadedArtifactV1 {
    manifest: EvidenceManifestArtifactV1,
    byte_length: u64,
    facts: EvidenceFactsV1,
}

#[derive(Debug)]
struct LoadedBundleV1 {
    manifest: EvidenceManifestV1,
    manifest_content_hash: String,
    canonical_manifest_hash: String,
    artifacts: Vec<LoadedArtifactV1>,
    source_commits: Vec<String>,
    commit_mismatch: bool,
}

/// Verify and browse a copied Workbench evidence bundle without reading repository originals.
///
/// `as_of_unix_seconds` makes the 21-day freshness calculation deterministic. When omitted,
/// timestamp-only freshness is `unknown`; explicit stale signals remain stale.
///
/// # Errors
///
/// Rejects unsafe paths, symlinks, malformed manifests, duplicate IDs or paths, oversized input,
/// checksum drift, invalid JSON, and unsupported deterministic time bounds.
pub fn browse_evidence_bundle(
    bundle: &Path,
    as_of_unix_seconds: Option<i64>,
) -> Result<String, WorkbenchError> {
    let loaded = load_bundle(bundle, as_of_unix_seconds)?;
    let artifacts = loaded
        .artifacts
        .iter()
        .map(project_artifact)
        .collect::<Vec<_>>();
    let summary = summary(&loaded);
    let value = json!({
        "schema_version": BUNDLE_VIEW_SCHEMA_V1,
        "manifest_schema_version": loaded.manifest.schema_version,
        "manifest_generated_at": loaded.manifest.generated_at,
        "manifest_source_commit_sha": loaded.manifest.source_commit_sha,
        "manifest_content_hash": loaded.manifest_content_hash,
        "canonical_manifest_hash": loaded.canonical_manifest_hash,
        "as_of_unix_seconds": as_of_unix_seconds,
        "source_commits": loaded.source_commits,
        "commit_mismatch": loaded.commit_mismatch,
        "bundle_consistent": !loaded.commit_mismatch,
        "summary": summary,
        "artifacts": artifacts,
        "claim_boundary": CLAIM_BOUNDARY,
    });
    canonical_hashed(value, "evidence_view_hash")
}

/// Verify the complete bundle and return one exact evidence artifact projection.
///
/// # Errors
///
/// Returns the bundle errors from [`browse_evidence_bundle`] and rejects an invalid or unknown ID.
pub fn show_evidence_artifact(
    bundle: &Path,
    artifact_id: &str,
    as_of_unix_seconds: Option<i64>,
) -> Result<String, WorkbenchError> {
    if !valid_identifier(artifact_id) {
        return Err(WorkbenchError::new(
            "workbench_evidence_artifact_id_invalid",
            "evidence artifact ID must be a non-empty ASCII identifier",
        ));
    }
    let loaded = load_bundle(bundle, as_of_unix_seconds)?;
    let artifact = loaded
        .artifacts
        .iter()
        .find(|artifact| artifact.manifest.id == artifact_id)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_evidence_artifact_not_found",
                format!("evidence bundle has no artifact {artifact_id}"),
            )
        })?;
    let value = json!({
        "schema_version": ARTIFACT_VIEW_SCHEMA_V1,
        "manifest_schema_version": loaded.manifest.schema_version,
        "manifest_source_commit_sha": loaded.manifest.source_commit_sha,
        "manifest_content_hash": loaded.manifest_content_hash,
        "canonical_manifest_hash": loaded.canonical_manifest_hash,
        "as_of_unix_seconds": as_of_unix_seconds,
        "source_commits": loaded.source_commits,
        "commit_mismatch": loaded.commit_mismatch,
        "bundle_consistent": !loaded.commit_mismatch,
        "artifact": project_artifact(artifact),
        "claim_boundary": CLAIM_BOUNDARY,
    });
    canonical_hashed(value, "evidence_artifact_view_hash")
}

fn load_bundle(
    bundle: &Path,
    as_of_unix_seconds: Option<i64>,
) -> Result<LoadedBundleV1, WorkbenchError> {
    validate_as_of(as_of_unix_seconds)?;
    verify_real_directory(bundle, "evidence bundle root")?;
    let manifest_bytes = read_bounded_regular_file(&bundle.join(MANIFEST_FILE), MAX_MANIFEST_BYTES)
        .map_err(|error| evidence_io_error("manifest", &error))?;
    let manifest_value = decode_json_strict(&manifest_bytes).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_manifest_json_invalid",
            error.to_string(),
        )
    })?;
    let canonical_manifest = canonicalize_model_ir_v2(&manifest_value).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_manifest_canonicalization_failed",
            error.to_string(),
        )
    })?;
    let manifest: EvidenceManifestV1 = serde_json::from_value(manifest_value).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_manifest_contract_invalid",
            format!("manifest fields are missing, mistyped or unknown: {error}"),
        )
    })?;
    validate_manifest(&manifest)?;

    let mut aggregate = u64::try_from(manifest_bytes.len()).map_err(|_| {
        WorkbenchError::new(
            "workbench_evidence_length_invalid",
            "manifest length does not fit the evidence contract",
        )
    })?;
    let mut artifacts = Vec::with_capacity(manifest.artifacts.len());
    let mut commits = BTreeSet::from([manifest.source_commit_sha.clone()]);
    for entry in &manifest.artifacts {
        let path = resolve_artifact_path(bundle, &entry.path)?;
        let bytes = read_bounded_regular_file(&path, MAX_ARTIFACT_BYTES)
            .map_err(|error| evidence_io_error(&entry.id, &error))?;
        let byte_length = u64::try_from(bytes.len()).map_err(|_| {
            WorkbenchError::new(
                "workbench_evidence_length_invalid",
                format!(
                    "artifact {} length does not fit the evidence contract",
                    entry.id
                ),
            )
        })?;
        aggregate = aggregate.checked_add(byte_length).ok_or_else(|| {
            WorkbenchError::new(
                "workbench_evidence_length_invalid",
                "aggregate evidence length overflowed",
            )
        })?;
        if aggregate > MAX_AGGREGATE_BYTES {
            return Err(WorkbenchError::new(
                "workbench_evidence_bundle_too_large",
                "aggregate evidence bytes exceed the bounded contract",
            ));
        }
        if sha256_identity(&bytes) != entry.sha256 {
            return Err(WorkbenchError::new(
                "workbench_evidence_checksum_mismatch",
                format!("artifact {} does not match its manifest SHA-256", entry.id),
            ));
        }
        let value = decode_json_strict(&bytes).map_err(|error| {
            WorkbenchError::new(
                "workbench_evidence_artifact_json_invalid",
                format!("artifact {} is invalid: {error}", entry.id),
            )
        })?;
        if !value.is_object() {
            return Err(WorkbenchError::new(
                "workbench_evidence_artifact_contract_invalid",
                format!("artifact {} must contain a JSON object", entry.id),
            ));
        }
        let facts = interpret_facts(&value, as_of_unix_seconds)?;
        commits.insert(facts.source_commit_sha.clone());
        artifacts.push(LoadedArtifactV1 {
            manifest: entry.clone(),
            byte_length,
            facts,
        });
    }
    let source_commits = commits.into_iter().collect::<Vec<_>>();
    let commit_mismatch = source_commits.len() != 1;
    Ok(LoadedBundleV1 {
        manifest,
        manifest_content_hash: sha256_identity(&manifest_bytes),
        canonical_manifest_hash: sha256_identity(canonical_manifest.as_bytes()),
        artifacts,
        source_commits,
        commit_mismatch,
    })
}

fn validate_manifest(manifest: &EvidenceManifestV1) -> Result<(), WorkbenchError> {
    if manifest.schema_version != MANIFEST_SCHEMA_V1
        || manifest.generated_at.trim().is_empty()
        || !valid_commit(&manifest.source_commit_sha)
        || manifest.artifacts.is_empty()
        || manifest.artifacts.len() > MAX_ARTIFACTS
    {
        return Err(manifest_error(
            "manifest header, source commit or artifact count is invalid",
        ));
    }
    let mut identifiers = BTreeSet::new();
    let mut paths = BTreeSet::new();
    for artifact in &manifest.artifacts {
        if !valid_identifier(&artifact.id)
            || artifact.label.trim().is_empty()
            || artifact.label.chars().any(char::is_control)
            || artifact.source_path.trim().is_empty()
            || artifact.source_path.chars().any(char::is_control)
            || !valid_sha256(&artifact.sha256)
            || !artifact.read_only
        {
            return Err(manifest_error(&format!(
                "manifest artifact {} has an invalid field",
                artifact.id
            )));
        }
        if !identifiers.insert(artifact.id.as_str()) {
            return Err(WorkbenchError::new(
                "workbench_evidence_duplicate_artifact_id",
                format!("manifest artifact ID is duplicated: {}", artifact.id),
            ));
        }
        if !paths.insert(artifact.path.as_str()) {
            return Err(WorkbenchError::new(
                "workbench_evidence_duplicate_artifact_path",
                format!("manifest artifact path is duplicated: {}", artifact.path),
            ));
        }
        validate_relative_path(&artifact.path)?;
    }
    Ok(())
}

fn interpret_facts(
    value: &Value,
    as_of_unix_seconds: Option<i64>,
) -> Result<EvidenceFactsV1, WorkbenchError> {
    let status = optional_string(value, "status");
    let launch_ready = optional_bool(value, "launch_ready");
    let release_ready = optional_bool(value, "release_ready");
    let contract_pass = optional_bool(value, "contract_pass");
    let reason_code = optional_string(value, "reason_code");
    let evidence_fresh = optional_bool(value, "evidence_fresh");
    let blockers = extract_blockers(value)?;
    let generated_at = optional_string(value, "generated_at");
    let source_commit_sha = optional_string(value, "source_commit_sha")
        .filter(|commit| valid_commit(commit))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_evidence_source_commit_missing",
                "evidence artifact has no valid source_commit_sha",
            )
        })?;
    let summary_line = optional_string(value, "summary_line");
    let claim_boundary = optional_string(value, "claim_boundary");
    let gate = if status.as_deref() == Some("blocked")
        || launch_ready == Some(false)
        || release_ready == Some(false)
        || !blockers.is_empty()
    {
        EvidenceGateV1::Blocked
    } else if blockers.is_empty()
        && (reason_code.as_deref() == Some("PASS") || contract_pass == Some(true))
        && status.as_deref() != Some("blocked")
    {
        EvidenceGateV1::Ready
    } else {
        EvidenceGateV1::Unavailable
    };
    let (freshness, stale_reason) = freshness(
        generated_at.as_deref(),
        status.as_deref(),
        reason_code.as_deref(),
        evidence_fresh,
        as_of_unix_seconds,
    );
    Ok(EvidenceFactsV1 {
        gate,
        freshness,
        stale_reason,
        status,
        launch_ready,
        release_ready,
        contract_pass,
        reason_code,
        evidence_fresh,
        blockers,
        generated_at,
        source_commit_sha,
        summary_line,
        claim_boundary,
    })
}

fn freshness(
    generated_at: Option<&str>,
    status: Option<&str>,
    reason_code: Option<&str>,
    evidence_fresh: Option<bool>,
    as_of_unix_seconds: Option<i64>,
) -> (EvidenceFreshnessV1, Option<String>) {
    if status == Some("stale_or_inconsistent")
        || reason_code.is_some_and(|reason| reason.to_ascii_uppercase().contains("STALE"))
    {
        return (
            EvidenceFreshnessV1::Stale,
            Some("Source reports a stale / inconsistent status.".to_owned()),
        );
    }
    if evidence_fresh == Some(false) {
        return (
            EvidenceFreshnessV1::Stale,
            Some("Source reports evidence_fresh = false.".to_owned()),
        );
    }
    let Some(generated_at) = generated_at else {
        return (
            EvidenceFreshnessV1::Unknown,
            Some("No generated_at timestamp.".to_owned()),
        );
    };
    let Ok(generated) = OffsetDateTime::parse(generated_at, &Rfc3339) else {
        return (
            EvidenceFreshnessV1::Unknown,
            Some("Unparseable generated_at.".to_owned()),
        );
    };
    let Some(as_of) = as_of_unix_seconds else {
        return (
            EvidenceFreshnessV1::Unknown,
            Some("No deterministic as_of_unix_seconds was supplied.".to_owned()),
        );
    };
    let age = as_of.saturating_sub(generated.unix_timestamp());
    if age > MAX_EVIDENCE_AGE_SECONDS {
        return (
            EvidenceFreshnessV1::Stale,
            Some(format!(
                "Generated {} day(s) before the supplied as-of time.",
                age / (24 * 60 * 60)
            )),
        );
    }
    (EvidenceFreshnessV1::Fresh, None)
}

fn extract_blockers(value: &Value) -> Result<Vec<String>, WorkbenchError> {
    let Some(items) = value.get("blockers").and_then(Value::as_array) else {
        return Ok(Vec::new());
    };
    items
        .iter()
        .filter_map(|item| {
            if let Some(text) = item.as_str().map(str::trim).filter(|text| !text.is_empty()) {
                return Some(Ok(text.to_owned()));
            }
            let object = item.as_object()?;
            for key in ["id", "code", "message", "reason"] {
                if let Some(text) = object
                    .get(key)
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|text| !text.is_empty())
                {
                    return Some(Ok(text.to_owned()));
                }
            }
            Some(canonicalize_model_ir_v2(item).map_err(|error| {
                WorkbenchError::new(
                    "workbench_evidence_artifact_canonicalization_failed",
                    error.to_string(),
                )
            }))
        })
        .collect()
}

fn summary(bundle: &LoadedBundleV1) -> Value {
    let ready = bundle
        .artifacts
        .iter()
        .filter(|artifact| artifact.facts.gate == EvidenceGateV1::Ready)
        .count();
    let blocked = bundle
        .artifacts
        .iter()
        .filter(|artifact| artifact.facts.gate == EvidenceGateV1::Blocked)
        .count();
    let unavailable = bundle.artifacts.len() - ready - blocked;
    let stale = bundle
        .artifacts
        .iter()
        .filter(|artifact| artifact.facts.freshness == EvidenceFreshnessV1::Stale)
        .count();
    let product_release_ready = if bundle.commit_mismatch {
        None
    } else {
        bundle
            .artifacts
            .iter()
            .find(|artifact| artifact.manifest.id == "product_readiness")
            .and_then(|artifact| artifact.facts.release_ready)
    };
    json!({
        "artifact_count": bundle.artifacts.len(),
        "ready_count": ready,
        "blocked_count": blocked,
        "unavailable_count": unavailable,
        "stale_count": stale,
        "product_release_ready": product_release_ready,
    })
}

fn project_artifact(artifact: &LoadedArtifactV1) -> Value {
    let facts = &artifact.facts;
    json!({
        "id": artifact.manifest.id,
        "label": artifact.manifest.label,
        "bundle_path": artifact.manifest.path,
        "source_path": artifact.manifest.source_path,
        "sha256": artifact.manifest.sha256,
        "read_only": artifact.manifest.read_only,
        "byte_length": artifact.byte_length,
        "facts": {
            "gate_state": facts.gate.label(),
            "freshness": facts.freshness.label(),
            "stale_reason": facts.stale_reason,
            "status": facts.status,
            "launch_ready": facts.launch_ready,
            "release_ready": facts.release_ready,
            "contract_pass": facts.contract_pass,
            "reason_code": facts.reason_code,
            "evidence_fresh": facts.evidence_fresh,
            "blockers": facts.blockers,
            "blocker_count": facts.blockers.len(),
            "generated_at": facts.generated_at,
            "source_commit_sha": facts.source_commit_sha,
            "source_commit_short": facts.source_commit_sha.chars().take(8).collect::<String>(),
            "summary_line": facts.summary_line,
            "claim_boundary": facts.claim_boundary,
        },
    })
}

fn optional_string(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(ToOwned::to_owned)
}

fn optional_bool(value: &Value, key: &str) -> Option<bool> {
    value.get(key).and_then(Value::as_bool)
}

fn resolve_artifact_path(bundle: &Path, relative: &str) -> Result<PathBuf, WorkbenchError> {
    validate_relative_path(relative)?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut resolved = bundle.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(unsafe_path_error(relative));
        };
        resolved.push(name);
        if index + 1 < components.len() {
            verify_real_directory(&resolved, "evidence artifact parent")?;
        }
    }
    Ok(resolved)
}

fn validate_relative_path(relative: &str) -> Result<(), WorkbenchError> {
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

fn verify_real_directory(path: &Path, label: &str) -> Result<(), WorkbenchError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_io_error",
            format!("read {label} metadata failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(WorkbenchError::new(
            "workbench_evidence_unsafe_path",
            format!("{label} must be a real non-symlink directory"),
        ));
    }
    Ok(())
}

fn validate_as_of(as_of: Option<i64>) -> Result<(), WorkbenchError> {
    if as_of.is_some_and(|value| !(0..=MAX_AS_OF_UNIX_SECONDS).contains(&value)) {
        return Err(WorkbenchError::new(
            "workbench_evidence_as_of_invalid",
            "as-of Unix seconds are outside the supported UTC range",
        ));
    }
    Ok(())
}

fn canonical_hashed(mut value: Value, hash_field: &str) -> Result<String, WorkbenchError> {
    value
        .as_object_mut()
        .expect("evidence view is constructed as an object")
        .remove(hash_field);
    let unsigned = canonicalize_model_ir_v2(&value).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_view_canonicalization_failed",
            error.to_string(),
        )
    })?;
    value
        .as_object_mut()
        .expect("evidence view is constructed as an object")
        .insert(
            hash_field.to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_model_ir_v2(&value).map_err(|error| {
        WorkbenchError::new(
            "workbench_evidence_view_canonicalization_failed",
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

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_commit(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn unsafe_path_error(relative: &str) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_evidence_unsafe_path",
        format!("evidence artifact path is unsafe: {relative}"),
    )
}

fn manifest_error(detail: &str) -> WorkbenchError {
    WorkbenchError::new("workbench_evidence_manifest_contract_invalid", detail)
}

fn evidence_io_error(label: &str, error: &WorkbenchError) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_evidence_io_error",
        format!("read evidence {label} failed: {error}"),
    )
}
