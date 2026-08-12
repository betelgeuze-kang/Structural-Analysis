use std::collections::BTreeSet;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufReader, BufWriter, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MANIFEST_NAME: &str = "structural-distribution.json";
const PAYLOAD_DIRECTORY: &str = "payload";
const RELEASES_DIRECTORY: &str = "releases";
const STATE_DIRECTORY: &str = "state";
const ACTIVATION_NAME: &str = "activation.json";
const TRANSACTION_NAME: &str = "transaction.json";
const LOCK_NAME: &str = ".structural-install.lock";
const SCHEMA_VERSION: &str = "structural-distribution.v1";
const ACTIVATION_SCHEMA_VERSION: &str = "structural-activation.v1";
const TRANSACTION_SCHEMA_VERSION: &str = "structural-install-transaction.v1";
const BUILD_SCHEMA_VERSION: &str = "structural-native-build.v1";
const ABI_VERSION: &str = "0x0001000c";
const MAX_MANIFEST_BYTES: u64 = 16 * 1024 * 1024;
const MAX_FILE_COUNT: usize = 16_384;
const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 8 * 1024 * 1024 * 1024;

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BackendProfileV1 {
    CpuOnly,
    Rocm,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LinkageV1 {
    Shared,
    Static,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DistributionFileV1 {
    pub path: String,
    pub size: u64,
    pub mode: u32,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct UnsignedDistributionManifestV1 {
    schema_version: String,
    release_id: String,
    package_version: String,
    backend_profile: BackendProfileV1,
    linkage: LinkageV1,
    abi_version: String,
    source_sha256: String,
    execution_authority: String,
    files: Vec<DistributionFileV1>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DistributionManifestV1 {
    pub schema_version: String,
    pub release_id: String,
    pub package_version: String,
    pub backend_profile: BackendProfileV1,
    pub linkage: LinkageV1,
    pub abi_version: String,
    pub source_sha256: String,
    pub execution_authority: String,
    pub files: Vec<DistributionFileV1>,
    pub manifest_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActivationStateV1 {
    pub schema_version: String,
    pub generation: u64,
    pub current_release: String,
    pub previous_release: Option<String>,
    pub current_manifest_hash: String,
}

#[derive(Clone, Debug)]
pub struct BundleCreateRequest<'a> {
    pub payload_root: &'a Path,
    pub output: &'a Path,
    pub release_id: &'a str,
    pub package_version: &'a str,
    pub backend_profile: BackendProfileV1,
    pub linkage: LinkageV1,
    pub source_sha256: &'a str,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DistributionError {
    pub code: &'static str,
    pub detail: String,
}

impl DistributionError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for DistributionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for DistributionError {}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NativeBuildManifestV1 {
    schema_version: String,
    package_version: String,
    abi_version: String,
    c_compiler: CompilerIdentityV1,
    cxx_compiler: CompilerIdentityV1,
    build_type: String,
    hip_enabled: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CompilerIdentityV1 {
    id: String,
    version: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum TransactionOperationV1 {
    Install,
    Rollback,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum TransactionPhaseV1 {
    Prepared,
    Materialized,
    Activated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct InstallTransactionV1 {
    schema_version: String,
    operation: TransactionOperationV1,
    phase: TransactionPhaseV1,
    release_id: String,
    manifest_hash: String,
    staging_name: Option<String>,
    desired_activation: ActivationStateV1,
}

struct InstallLock {
    file: File,
}

impl Drop for InstallLock {
    fn drop(&mut self) {
        let _ = FileExt::unlock(&self.file);
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum InstallInterruption {
    None,
    AfterPrepared,
    AfterMaterialized,
    AfterActivated,
}

/// Creates an immutable, deterministic directory bundle from a staged native payload.
///
/// # Errors
///
/// Returns an error when identities are invalid, the payload violates the product contract,
/// an unsafe filesystem entry is encountered, or durable publication fails.
pub fn create_bundle(
    request: &BundleCreateRequest<'_>,
) -> Result<DistributionManifestV1, DistributionError> {
    validate_release_id(request.release_id)?;
    validate_package_version(request.package_version)?;
    validate_sha256_identity(request.source_sha256, "source SHA-256")?;
    ensure_directory(request.payload_root, "payload root")?;
    if fs::symlink_metadata(request.output).is_ok() {
        return Err(DistributionError::new(
            "bundle_output_exists",
            "bundle output must not already exist",
        ));
    }
    let output_parent = request.output.parent().ok_or_else(|| {
        DistributionError::new(
            "bundle_output_invalid",
            "bundle output has no parent directory",
        )
    })?;
    ensure_directory(output_parent, "bundle output parent")?;
    let staging = unique_path(output_parent, ".structural-bundle-stage");
    fs::create_dir(&staging).map_err(|error| io_error("bundle_stage_create_failed", error))?;
    let outcome = create_bundle_in_staging(request, &staging);
    match outcome {
        Ok(manifest) => {
            sync_directory_tree(&staging)?;
            fs::rename(&staging, request.output)
                .map_err(|error| io_error("bundle_publish_failed", error))?;
            sync_directory(output_parent)?;
            Ok(manifest)
        }
        Err(error) => {
            let _ = fs::remove_dir_all(&staging);
            Err(error)
        }
    }
}

fn create_bundle_in_staging(
    request: &BundleCreateRequest<'_>,
    staging: &Path,
) -> Result<DistributionManifestV1, DistributionError> {
    let payload_destination = staging.join(PAYLOAD_DIRECTORY);
    fs::create_dir(&payload_destination)
        .map_err(|error| io_error("bundle_payload_create_failed", error))?;
    let source_root = request
        .payload_root
        .canonicalize()
        .map_err(|error| io_error("payload_root_resolve_failed", error))?;
    let mut sources = Vec::new();
    collect_payload_sources(&source_root, &source_root, &mut sources)?;
    if sources.is_empty() {
        return Err(DistributionError::new(
            "bundle_payload_empty",
            "payload root contains no files",
        ));
    }
    if sources.len() > MAX_FILE_COUNT {
        return Err(DistributionError::new(
            "bundle_file_count_exceeded",
            "payload file count exceeds the distribution limit",
        ));
    }
    let mut entries = Vec::with_capacity(sources.len());
    let mut total_size = 0_u64;
    for (relative, source) in sources {
        let relative_text = portable_relative_path(&relative)?;
        let destination = payload_destination.join(&relative);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| io_error("bundle_directory_create_failed", error))?;
        }
        let (size, mode, sha256) = copy_regular_file(&source, &destination)?;
        total_size = total_size.checked_add(size).ok_or_else(|| {
            DistributionError::new("bundle_size_overflow", "payload byte count overflowed")
        })?;
        if total_size > MAX_TOTAL_BYTES {
            return Err(DistributionError::new(
                "bundle_total_size_exceeded",
                "payload bytes exceed the distribution limit",
            ));
        }
        entries.push(DistributionFileV1 {
            path: relative_text,
            size,
            mode,
            sha256,
        });
    }
    entries.sort_by(|left, right| left.path.cmp(&right.path));
    validate_payload_contract(
        &payload_destination,
        request.package_version,
        request.backend_profile,
        request.linkage,
        &entries,
    )?;
    let unsigned = UnsignedDistributionManifestV1 {
        schema_version: SCHEMA_VERSION.to_owned(),
        release_id: request.release_id.to_owned(),
        package_version: request.package_version.to_owned(),
        backend_profile: request.backend_profile,
        linkage: request.linkage,
        abi_version: ABI_VERSION.to_owned(),
        source_sha256: request.source_sha256.to_owned(),
        execution_authority: match request.backend_profile {
            BackendProfileV1::CpuOnly => "cpu_build_candidate".to_owned(),
            BackendProfileV1::Rocm => "rocm_build_candidate".to_owned(),
        },
        files: entries,
    };
    let unsigned_bytes = canonical_json(&unsigned)?;
    let manifest = DistributionManifestV1 {
        schema_version: unsigned.schema_version,
        release_id: unsigned.release_id,
        package_version: unsigned.package_version,
        backend_profile: unsigned.backend_profile,
        linkage: unsigned.linkage,
        abi_version: unsigned.abi_version,
        source_sha256: unsigned.source_sha256,
        execution_authority: unsigned.execution_authority,
        files: unsigned.files,
        manifest_hash: sha256_identity(&unsigned_bytes),
    };
    let bytes = canonical_json(&manifest)?;
    write_new_file(&staging.join(MANIFEST_NAME), &bytes, 0o444)?;
    Ok(manifest)
}

/// Verifies the canonical manifest, complete file inventory, metadata, and payload hashes.
///
/// # Errors
///
/// Returns an error for any malformed, unsupported, missing, extra, unsafe, or modified entry.
pub fn verify_bundle(bundle: &Path) -> Result<DistributionManifestV1, DistributionError> {
    ensure_directory(bundle, "bundle")?;
    let manifest_path = bundle.join(MANIFEST_NAME);
    let bytes = read_bounded_regular_file(&manifest_path, MAX_MANIFEST_BYTES)?;
    let manifest: DistributionManifestV1 = serde_json::from_slice(&bytes).map_err(|error| {
        DistributionError::new(
            "bundle_manifest_invalid",
            format!("distribution manifest is invalid JSON: {error}"),
        )
    })?;
    if canonical_json(&manifest)? != bytes {
        return Err(DistributionError::new(
            "bundle_manifest_noncanonical",
            "distribution manifest must use exact canonical JSON bytes",
        ));
    }
    validate_manifest_fields(&manifest)?;
    let unsigned = UnsignedDistributionManifestV1 {
        schema_version: manifest.schema_version.clone(),
        release_id: manifest.release_id.clone(),
        package_version: manifest.package_version.clone(),
        backend_profile: manifest.backend_profile,
        linkage: manifest.linkage,
        abi_version: manifest.abi_version.clone(),
        source_sha256: manifest.source_sha256.clone(),
        execution_authority: manifest.execution_authority.clone(),
        files: manifest.files.clone(),
    };
    let expected_hash = sha256_identity(&canonical_json(&unsigned)?);
    if manifest.manifest_hash != expected_hash {
        return Err(DistributionError::new(
            "bundle_manifest_hash_mismatch",
            "distribution manifest self-hash does not match",
        ));
    }
    verify_payload_files(bundle, &manifest)?;
    validate_payload_contract(
        &bundle.join(PAYLOAD_DIRECTORY),
        &manifest.package_version,
        manifest.backend_profile,
        manifest.linkage,
        &manifest.files,
    )?;
    Ok(manifest)
}

/// Installs or updates to a verified release through an atomic, recoverable transaction.
///
/// # Errors
///
/// Returns an error when bundle verification, locking, staging, recovery, or activation fails.
pub fn install_bundle(
    bundle: &Path,
    install_root: &Path,
) -> Result<ActivationStateV1, DistributionError> {
    install_bundle_inner(bundle, install_root, InstallInterruption::None)
}

fn install_bundle_inner(
    bundle: &Path,
    install_root: &Path,
    interruption: InstallInterruption,
) -> Result<ActivationStateV1, DistributionError> {
    let manifest = verify_bundle(bundle)?;
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    let current = read_activation_optional(install_root)?;
    if current
        .as_ref()
        .is_some_and(|state| state.current_release == manifest.release_id)
    {
        let release = release_path(install_root, &manifest.release_id);
        let installed = verify_bundle(&release)?;
        if installed.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_id_immutable",
                "active release ID already names different package bytes",
            ));
        }
        return Ok(current.expect("checked active state"));
    }
    let releases = install_root.join(RELEASES_DIRECTORY);
    let staging_name = format!(".stage-{}", unique_token());
    let staging = releases.join(&staging_name);
    let target = release_path(install_root, &manifest.release_id);
    if path_entry_exists(&target)? {
        let installed = verify_bundle(&target)?;
        if installed.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_id_immutable",
                "release ID already names different package bytes",
            ));
        }
    } else {
        copy_verified_bundle(bundle, &staging, &manifest)?;
    }
    let desired = ActivationStateV1 {
        schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
        generation: next_generation(current.as_ref())?,
        current_release: manifest.release_id.clone(),
        previous_release: current.as_ref().map(|state| state.current_release.clone()),
        current_manifest_hash: manifest.manifest_hash.clone(),
    };
    let mut transaction = InstallTransactionV1 {
        schema_version: TRANSACTION_SCHEMA_VERSION.to_owned(),
        operation: TransactionOperationV1::Install,
        phase: TransactionPhaseV1::Prepared,
        release_id: manifest.release_id,
        manifest_hash: manifest.manifest_hash,
        staging_name: if path_entry_exists(&staging)? {
            Some(staging_name)
        } else {
            None
        },
        desired_activation: desired.clone(),
    };
    write_transaction(install_root, &transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterPrepared)?;
    materialize_transaction(install_root, &mut transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterMaterialized)?;
    activate_transaction(install_root, &mut transaction)?;
    maybe_interrupt(interruption, InstallInterruption::AfterActivated)?;
    finish_transaction(install_root)?;
    Ok(desired)
}

/// Completes an interrupted durable install transaction and returns the active release.
///
/// # Errors
///
/// Returns an error when state is corrupt, transaction bindings differ, or no release is active.
pub fn recover_install(install_root: &Path) -> Result<ActivationStateV1, DistributionError> {
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    read_activation_optional(install_root)?.ok_or_else(|| {
        DistributionError::new(
            "activation_missing",
            "installation has no active release after recovery",
        )
    })
}

/// Atomically swaps the current and previous immutable releases.
///
/// # Errors
///
/// Returns an error when no previous release exists or its bytes fail verification.
pub fn rollback_install(install_root: &Path) -> Result<ActivationStateV1, DistributionError> {
    let _lock = lock_install_root(install_root)?;
    recover_locked(install_root)?;
    let current = read_activation_optional(install_root)?.ok_or_else(|| {
        DistributionError::new("activation_missing", "installation has no active release")
    })?;
    let previous_release = current.previous_release.clone().ok_or_else(|| {
        DistributionError::new(
            "rollback_unavailable",
            "activation state has no previous release",
        )
    })?;
    let previous_manifest = verify_bundle(&release_path(install_root, &previous_release))?;
    let desired = ActivationStateV1 {
        schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
        generation: current.generation.checked_add(1).ok_or_else(|| {
            DistributionError::new(
                "activation_generation_overflow",
                "activation generation cannot be incremented",
            )
        })?,
        current_release: previous_release.clone(),
        previous_release: Some(current.current_release),
        current_manifest_hash: previous_manifest.manifest_hash.clone(),
    };
    let mut transaction = InstallTransactionV1 {
        schema_version: TRANSACTION_SCHEMA_VERSION.to_owned(),
        operation: TransactionOperationV1::Rollback,
        phase: TransactionPhaseV1::Materialized,
        release_id: previous_release,
        manifest_hash: previous_manifest.manifest_hash,
        staging_name: None,
        desired_activation: desired.clone(),
    };
    write_transaction(install_root, &transaction)?;
    activate_transaction(install_root, &mut transaction)?;
    finish_transaction(install_root)?;
    Ok(desired)
}

/// Returns a verified activation state without mutating or recovering the installation.
///
/// # Errors
///
/// Returns an error when recovery is pending or active state and release bytes do not agree.
pub fn installation_status(
    install_root: &Path,
) -> Result<Option<ActivationStateV1>, DistributionError> {
    ensure_directory(install_root, "install root")?;
    if path_entry_exists(&install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME))? {
        return Err(DistributionError::new(
            "recovery_required",
            "an interrupted install transaction must be recovered before status is authoritative",
        ));
    }
    let state = read_activation_optional(install_root)?;
    if let Some(active) = &state {
        let manifest = verify_bundle(&release_path(install_root, &active.current_release))?;
        if manifest.manifest_hash != active.current_manifest_hash {
            return Err(DistributionError::new(
                "activation_hash_mismatch",
                "active release does not match activation state",
            ));
        }
    }
    Ok(state)
}

/// Returns the verified active payload directory, if a release is active.
///
/// # Errors
///
/// Returns the same validation errors as [`installation_status`].
pub fn active_payload_path(install_root: &Path) -> Result<Option<PathBuf>, DistributionError> {
    installation_status(install_root).map(|state| {
        state.map(|active| {
            release_path(install_root, &active.current_release).join(PAYLOAD_DIRECTORY)
        })
    })
}

fn lock_install_root(install_root: &Path) -> Result<InstallLock, DistributionError> {
    match fs::symlink_metadata(install_root) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(DistributionError::new(
                "install_root_invalid",
                "install root must be a real directory",
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::create_dir(install_root)
                .map_err(|error| io_error("install_root_create_failed", error))?;
        }
        Err(error) => return Err(io_error("install_root_inspect_failed", error)),
    }
    create_real_subdirectory(install_root, RELEASES_DIRECTORY)?;
    create_real_subdirectory(install_root, STATE_DIRECTORY)?;
    let lock_path = install_root.join(LOCK_NAME);
    reject_symlink_if_present(&lock_path, "install lock")?;
    let file = open_install_lock(&lock_path)?;
    file.lock_exclusive()
        .map_err(|error| io_error("install_lock_failed", error))?;
    Ok(InstallLock { file })
}

fn recover_locked(install_root: &Path) -> Result<(), DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME);
    if !path_entry_exists(&path)? {
        return Ok(());
    }
    let mut transaction: InstallTransactionV1 = read_canonical_json(&path, MAX_MANIFEST_BYTES)?;
    validate_transaction(&transaction)?;
    if transaction.phase == TransactionPhaseV1::Prepared {
        materialize_transaction(install_root, &mut transaction)?;
    }
    if transaction.phase == TransactionPhaseV1::Materialized {
        activate_transaction(install_root, &mut transaction)?;
    }
    finish_transaction(install_root)
}

fn materialize_transaction(
    install_root: &Path,
    transaction: &mut InstallTransactionV1,
) -> Result<(), DistributionError> {
    if transaction.operation == TransactionOperationV1::Install {
        let target = release_path(install_root, &transaction.release_id);
        if let Some(staging_name) = &transaction.staging_name {
            validate_staging_name(staging_name)?;
            let staging = install_root.join(RELEASES_DIRECTORY).join(staging_name);
            if path_entry_exists(&target)? {
                let existing = verify_bundle(&target)?;
                if existing.manifest_hash != transaction.manifest_hash {
                    return Err(DistributionError::new(
                        "release_id_immutable",
                        "materialized release differs from transaction manifest",
                    ));
                }
                if path_entry_exists(&staging)? {
                    fs::remove_dir_all(&staging)
                        .map_err(|error| io_error("staging_cleanup_failed", error))?;
                }
            } else {
                let staged = verify_bundle(&staging)?;
                if staged.manifest_hash != transaction.manifest_hash {
                    return Err(DistributionError::new(
                        "staging_hash_mismatch",
                        "staged release differs from transaction manifest",
                    ));
                }
                fs::rename(&staging, &target)
                    .map_err(|error| io_error("release_materialize_failed", error))?;
                sync_directory(&install_root.join(RELEASES_DIRECTORY))?;
            }
        } else {
            let existing = verify_bundle(&target)?;
            if existing.manifest_hash != transaction.manifest_hash {
                return Err(DistributionError::new(
                    "release_id_immutable",
                    "existing release differs from transaction manifest",
                ));
            }
        }
    }
    transaction.phase = TransactionPhaseV1::Materialized;
    write_transaction(install_root, transaction)
}

fn activate_transaction(
    install_root: &Path,
    transaction: &mut InstallTransactionV1,
) -> Result<(), DistributionError> {
    let release = verify_bundle(&release_path(install_root, &transaction.release_id))?;
    if release.manifest_hash != transaction.manifest_hash
        || transaction.desired_activation.current_release != transaction.release_id
        || transaction.desired_activation.current_manifest_hash != transaction.manifest_hash
    {
        return Err(DistributionError::new(
            "transaction_binding_mismatch",
            "transaction, activation, and release identities differ",
        ));
    }
    let state_path = install_root.join(STATE_DIRECTORY).join(ACTIVATION_NAME);
    atomic_write_canonical(&state_path, &transaction.desired_activation)?;
    transaction.phase = TransactionPhaseV1::Activated;
    write_transaction(install_root, transaction)
}

fn finish_transaction(install_root: &Path) -> Result<(), DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME);
    match fs::remove_file(path) {
        Ok(()) => sync_directory(&install_root.join(STATE_DIRECTORY)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(io_error("transaction_finish_failed", error)),
    }
}

fn write_transaction(
    install_root: &Path,
    transaction: &InstallTransactionV1,
) -> Result<(), DistributionError> {
    validate_transaction(transaction)?;
    atomic_write_canonical(
        &install_root.join(STATE_DIRECTORY).join(TRANSACTION_NAME),
        transaction,
    )
}

fn validate_transaction(transaction: &InstallTransactionV1) -> Result<(), DistributionError> {
    if transaction.schema_version != TRANSACTION_SCHEMA_VERSION {
        return Err(DistributionError::new(
            "transaction_schema_unsupported",
            "install transaction schema is unsupported",
        ));
    }
    validate_release_id(&transaction.release_id)?;
    validate_sha256_identity(&transaction.manifest_hash, "transaction manifest hash")?;
    validate_activation(&transaction.desired_activation)?;
    if let Some(staging) = &transaction.staging_name {
        validate_staging_name(staging)?;
    }
    Ok(())
}

fn validate_activation(activation: &ActivationStateV1) -> Result<(), DistributionError> {
    if activation.schema_version != ACTIVATION_SCHEMA_VERSION || activation.generation == 0 {
        return Err(DistributionError::new(
            "activation_invalid",
            "activation schema or generation is invalid",
        ));
    }
    validate_release_id(&activation.current_release)?;
    if let Some(previous) = &activation.previous_release {
        validate_release_id(previous)?;
    }
    validate_sha256_identity(
        &activation.current_manifest_hash,
        "activation manifest hash",
    )
}

fn read_activation_optional(
    install_root: &Path,
) -> Result<Option<ActivationStateV1>, DistributionError> {
    let path = install_root.join(STATE_DIRECTORY).join(ACTIVATION_NAME);
    if !path_entry_exists(&path)? {
        return Ok(None);
    }
    let activation: ActivationStateV1 = read_canonical_json(&path, MAX_MANIFEST_BYTES)?;
    validate_activation(&activation)?;
    Ok(Some(activation))
}

fn copy_verified_bundle(
    source: &Path,
    destination: &Path,
    manifest: &DistributionManifestV1,
) -> Result<(), DistributionError> {
    fs::create_dir(destination).map_err(|error| io_error("release_stage_create_failed", error))?;
    let payload_destination = destination.join(PAYLOAD_DIRECTORY);
    fs::create_dir(&payload_destination)
        .map_err(|error| io_error("release_payload_create_failed", error))?;
    let outcome = (|| {
        for entry in &manifest.files {
            let relative = validated_relative_path(&entry.path)?;
            let source_file = source.join(PAYLOAD_DIRECTORY).join(&relative);
            let destination_file = payload_destination.join(relative);
            if let Some(parent) = destination_file.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| io_error("release_directory_create_failed", error))?;
            }
            let (size, mode, hash) = copy_regular_file(&source_file, &destination_file)?;
            if size != entry.size || mode != entry.mode || hash != entry.sha256 {
                return Err(DistributionError::new(
                    "release_copy_mismatch",
                    format!("copied payload changed for {}", entry.path),
                ));
            }
        }
        let manifest_bytes = canonical_json(manifest)?;
        write_new_file(&destination.join(MANIFEST_NAME), &manifest_bytes, 0o444)?;
        sync_directory_tree(destination)?;
        let copied = verify_bundle(destination)?;
        if copied.manifest_hash != manifest.manifest_hash {
            return Err(DistributionError::new(
                "release_copy_mismatch",
                "copied release manifest changed",
            ));
        }
        Ok(())
    })();
    if outcome.is_err() {
        let _ = fs::remove_dir_all(destination);
    }
    outcome
}

fn collect_payload_sources(
    root: &Path,
    directory: &Path,
    output: &mut Vec<(PathBuf, PathBuf)>,
) -> Result<(), DistributionError> {
    let mut entries = fs::read_dir(directory)
        .map_err(|error| io_error("payload_directory_read_failed", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("payload_entry_read_failed", error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let relative = path.strip_prefix(root).map_err(|_| {
            DistributionError::new("payload_path_invalid", "payload path escaped its root")
        })?;
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("payload_metadata_failed", error))?;
        if metadata.is_dir() {
            collect_payload_sources(root, &path, output)?;
        } else if metadata.is_file() {
            output.push((relative.to_path_buf(), path));
        } else if metadata.file_type().is_symlink() {
            let resolved = path
                .canonicalize()
                .map_err(|error| io_error("payload_symlink_resolve_failed", error))?;
            if !resolved.starts_with(root) {
                return Err(DistributionError::new(
                    "payload_symlink_escape",
                    "payload symlink resolves outside the payload root",
                ));
            }
            let target = fs::metadata(&resolved)
                .map_err(|error| io_error("payload_symlink_target_failed", error))?;
            if !target.is_file() {
                return Err(DistributionError::new(
                    "payload_entry_unsupported",
                    "only regular-file symlinks may be normalized into a bundle",
                ));
            }
            output.push((relative.to_path_buf(), resolved));
        } else {
            return Err(DistributionError::new(
                "payload_entry_unsupported",
                "payload contains a socket, device, FIFO, or other unsupported entry",
            ));
        }
    }
    Ok(())
}

fn verify_payload_files(
    bundle: &Path,
    manifest: &DistributionManifestV1,
) -> Result<(), DistributionError> {
    let payload = bundle.join(PAYLOAD_DIRECTORY);
    ensure_directory(&payload, "bundle payload")?;
    let mut actual = Vec::new();
    collect_strict_regular_files(&payload, &payload, &mut actual)?;
    let expected = manifest
        .files
        .iter()
        .map(|entry| entry.path.clone())
        .collect::<Vec<_>>();
    let actual = actual
        .iter()
        .map(|path| portable_relative_path(path))
        .collect::<Result<Vec<_>, _>>()?;
    if actual != expected {
        return Err(DistributionError::new(
            "bundle_inventory_mismatch",
            "payload file inventory differs from the manifest",
        ));
    }
    let mut total_size = 0_u64;
    for entry in &manifest.files {
        let relative = validated_relative_path(&entry.path)?;
        let path = payload.join(relative);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("bundle_payload_metadata_failed", error))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(DistributionError::new(
                "bundle_payload_not_regular",
                format!("payload entry is not a regular file: {}", entry.path),
            ));
        }
        let mode = portable_mode(&metadata);
        let size = metadata.len();
        if size != entry.size || mode != entry.mode || sha256_file(&path)? != entry.sha256 {
            return Err(DistributionError::new(
                "bundle_payload_hash_mismatch",
                format!("payload bytes or metadata changed: {}", entry.path),
            ));
        }
        total_size = total_size.checked_add(size).ok_or_else(|| {
            DistributionError::new("bundle_size_overflow", "payload byte count overflowed")
        })?;
        if total_size > MAX_TOTAL_BYTES {
            return Err(DistributionError::new(
                "bundle_total_size_exceeded",
                "payload bytes exceed the distribution limit",
            ));
        }
    }
    Ok(())
}

fn collect_strict_regular_files(
    root: &Path,
    directory: &Path,
    output: &mut Vec<PathBuf>,
) -> Result<(), DistributionError> {
    let metadata = fs::symlink_metadata(directory)
        .map_err(|error| io_error("bundle_directory_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(DistributionError::new(
            "bundle_directory_invalid",
            "bundle directory tree contains a symlink or non-directory",
        ));
    }
    let mut entries = fs::read_dir(directory)
        .map_err(|error| io_error("bundle_directory_read_failed", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("bundle_entry_read_failed", error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| io_error("bundle_entry_metadata_failed", error))?;
        if metadata.file_type().is_symlink() {
            return Err(DistributionError::new(
                "bundle_symlink_rejected",
                "verified bundles must not contain symlinks",
            ));
        }
        if metadata.is_dir() {
            collect_strict_regular_files(root, &path, output)?;
        } else if metadata.is_file() {
            output.push(
                path.strip_prefix(root)
                    .map_err(|_| {
                        DistributionError::new(
                            "bundle_path_invalid",
                            "bundle entry escaped the payload root",
                        )
                    })?
                    .to_path_buf(),
            );
        } else {
            return Err(DistributionError::new(
                "bundle_entry_unsupported",
                "bundle contains a socket, device, FIFO, or other unsupported entry",
            ));
        }
    }
    Ok(())
}

fn validate_manifest_fields(manifest: &DistributionManifestV1) -> Result<(), DistributionError> {
    if manifest.schema_version != SCHEMA_VERSION || manifest.abi_version != ABI_VERSION {
        return Err(DistributionError::new(
            "bundle_contract_unsupported",
            "distribution schema or ABI version is unsupported",
        ));
    }
    validate_release_id(&manifest.release_id)?;
    validate_package_version(&manifest.package_version)?;
    validate_sha256_identity(&manifest.source_sha256, "source SHA-256")?;
    validate_sha256_identity(&manifest.manifest_hash, "manifest hash")?;
    let expected_authority = match manifest.backend_profile {
        BackendProfileV1::CpuOnly => "cpu_build_candidate",
        BackendProfileV1::Rocm => "rocm_build_candidate",
    };
    if manifest.execution_authority != expected_authority {
        return Err(DistributionError::new(
            "bundle_authority_invalid",
            "execution authority is incompatible with the backend profile",
        ));
    }
    if manifest.files.is_empty() || manifest.files.len() > MAX_FILE_COUNT {
        return Err(DistributionError::new(
            "bundle_file_count_invalid",
            "distribution file count is empty or exceeds the limit",
        ));
    }
    let mut previous = None;
    let mut unique = BTreeSet::new();
    for entry in &manifest.files {
        validated_relative_path(&entry.path)?;
        validate_sha256_identity(&entry.sha256, "payload SHA-256")?;
        if entry.size > MAX_FILE_BYTES || !matches!(entry.mode, 0o444 | 0o555) {
            return Err(DistributionError::new(
                "bundle_file_metadata_invalid",
                format!("invalid size or mode for {}", entry.path),
            ));
        }
        if previous.is_some_and(|path: &String| path >= &entry.path)
            || !unique.insert(entry.path.clone())
        {
            return Err(DistributionError::new(
                "bundle_inventory_noncanonical",
                "payload inventory must be unique and bytewise sorted",
            ));
        }
        previous = Some(&entry.path);
    }
    Ok(())
}

fn validate_payload_contract(
    payload: &Path,
    package_version: &str,
    backend: BackendProfileV1,
    linkage: LinkageV1,
    entries: &[DistributionFileV1],
) -> Result<(), DistributionError> {
    let inventory = entries
        .iter()
        .map(|entry| entry.path.as_str())
        .collect::<BTreeSet<_>>();
    for required in [
        "bin/structural-cli",
        "bin/structural-installer",
        "bin/structural-workbench",
        "include/structural/abi_v1.h",
        "share/structural-native/structural-native-build.json",
    ] {
        if !inventory.contains(required) {
            return Err(DistributionError::new(
                "bundle_required_file_missing",
                format!("required product file is missing: {required}"),
            ));
        }
    }
    let required_library = match linkage {
        LinkageV1::Shared => "lib/libstructural_c_abi_v1.so",
        LinkageV1::Static => "lib/libstructural_c_abi_v1.a",
    };
    if !inventory.contains(required_library) {
        return Err(DistributionError::new(
            "bundle_required_file_missing",
            format!("required product library is missing: {required_library}"),
        ));
    }
    for binary in [
        "bin/structural-cli",
        "bin/structural-installer",
        "bin/structural-workbench",
    ] {
        let entry = entries
            .iter()
            .find(|entry| entry.path == binary)
            .expect("required entry checked");
        if entry.mode != 0o555 {
            return Err(DistributionError::new(
                "bundle_binary_not_executable",
                format!("product binary is not executable: {binary}"),
            ));
        }
    }
    let build_path = payload.join("share/structural-native/structural-native-build.json");
    let build_bytes = read_bounded_regular_file(&build_path, MAX_MANIFEST_BYTES)?;
    let build: NativeBuildManifestV1 = serde_json::from_slice(&build_bytes).map_err(|error| {
        DistributionError::new(
            "native_build_manifest_invalid",
            format!("native build manifest is invalid: {error}"),
        )
    })?;
    let expected_hip = backend == BackendProfileV1::Rocm;
    if build.schema_version != BUILD_SCHEMA_VERSION
        || build.package_version != package_version
        || build.abi_version != ABI_VERSION
        || build.hip_enabled != expected_hip
        || build.c_compiler.id.is_empty()
        || build.c_compiler.version.is_empty()
        || build.cxx_compiler.id.is_empty()
        || build.cxx_compiler.version.is_empty()
        || build.build_type != "Release"
    {
        return Err(DistributionError::new(
            "native_build_manifest_mismatch",
            "native build identity does not match the distribution profile",
        ));
    }
    Ok(())
}

fn validate_release_id(value: &str) -> Result<(), DistributionError> {
    if value.is_empty()
        || value.len() > 128
        || value == "."
        || value == ".."
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
    {
        return Err(DistributionError::new(
            "release_id_invalid",
            "release ID must use 1-128 ASCII alphanumeric, dot, underscore, or hyphen bytes",
        ));
    }
    Ok(())
}

fn validate_staging_name(value: &str) -> Result<(), DistributionError> {
    if !value.starts_with(".stage-") {
        return Err(DistributionError::new(
            "transaction_staging_invalid",
            "transaction staging name is invalid",
        ));
    }
    validate_release_id(value)
}

fn validate_package_version(value: &str) -> Result<(), DistributionError> {
    if value.is_empty()
        || value.len() > 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'+' | b'-'))
    {
        return Err(DistributionError::new(
            "package_version_invalid",
            "package version must be a bounded portable version token",
        ));
    }
    Ok(())
}

fn validate_sha256_identity(value: &str, label: &str) -> Result<(), DistributionError> {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return Err(DistributionError::new(
            "sha256_identity_invalid",
            format!("{label} must start with sha256:"),
        ));
    };
    if hex.len() != 64
        || !hex
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(DistributionError::new(
            "sha256_identity_invalid",
            format!("{label} must contain exactly 64 lowercase hexadecimal digits"),
        ));
    }
    Ok(())
}

fn validated_relative_path(value: &str) -> Result<PathBuf, DistributionError> {
    if value.is_empty() || value.contains('\\') {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "bundle paths must be non-empty portable relative paths",
        ));
    }
    let path = Path::new(value);
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "bundle path contains root, parent, current, or prefix components",
        ));
    }
    Ok(path.to_path_buf())
}

fn portable_relative_path(path: &Path) -> Result<String, DistributionError> {
    let mut components = Vec::new();
    for component in path.components() {
        let Component::Normal(value) = component else {
            return Err(DistributionError::new(
                "bundle_path_invalid",
                "payload path is not a portable relative path",
            ));
        };
        let text = value.to_str().ok_or_else(|| {
            DistributionError::new("bundle_path_utf8_required", "payload paths must be UTF-8")
        })?;
        if text.is_empty() || text.contains(['/', '\\']) {
            return Err(DistributionError::new(
                "bundle_path_invalid",
                "payload path component is invalid",
            ));
        }
        components.push(text);
    }
    if components.is_empty() {
        return Err(DistributionError::new(
            "bundle_path_invalid",
            "payload path is empty",
        ));
    }
    Ok(components.join("/"))
}

fn copy_regular_file(
    source: &Path,
    destination: &Path,
) -> Result<(u64, u32, String), DistributionError> {
    let metadata =
        fs::metadata(source).map_err(|error| io_error("payload_file_metadata_failed", error))?;
    if !metadata.is_file() || metadata.len() > MAX_FILE_BYTES {
        return Err(DistributionError::new(
            "payload_file_invalid",
            "payload source must be a bounded regular file",
        ));
    }
    let mode = if portable_mode(&metadata) & 0o111 != 0 {
        0o555
    } else {
        0o444
    };
    let source_file = open_regular_no_follow(source, "payload_file_open_failed")?;
    let source_metadata = source_file
        .metadata()
        .map_err(|error| io_error("payload_file_metadata_failed", error))?;
    if !source_metadata.is_file() || source_metadata.len() != metadata.len() {
        return Err(DistributionError::new(
            "payload_file_changed",
            "payload file changed while opening it",
        ));
    }
    let destination_file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(destination)
        .map_err(|error| io_error("payload_copy_open_failed", error))?;
    let mut reader = BufReader::new(source_file);
    let mut writer = BufWriter::new(destination_file);
    let mut digest = Sha256::new();
    let mut size = 0_u64;
    let mut buffer = vec![0_u8; 64 * 1024].into_boxed_slice();
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| io_error("payload_copy_read_failed", error))?;
        if count == 0 {
            break;
        }
        size = size.checked_add(count as u64).ok_or_else(|| {
            DistributionError::new("payload_size_overflow", "payload file size overflowed")
        })?;
        if size > MAX_FILE_BYTES {
            return Err(DistributionError::new(
                "payload_file_size_exceeded",
                "payload file grew beyond the distribution limit",
            ));
        }
        digest.update(&buffer[..count]);
        writer
            .write_all(&buffer[..count])
            .map_err(|error| io_error("payload_copy_write_failed", error))?;
    }
    writer
        .flush()
        .map_err(|error| io_error("payload_copy_flush_failed", error))?;
    writer
        .get_ref()
        .sync_all()
        .map_err(|error| io_error("payload_copy_sync_failed", error))?;
    set_mode(destination, mode)?;
    writer
        .get_ref()
        .sync_all()
        .map_err(|error| io_error("payload_mode_sync_failed", error))?;
    Ok((size, mode, digest_identity(digest)))
}

fn sha256_file(path: &Path) -> Result<String, DistributionError> {
    let file = open_regular_no_follow(path, "payload_hash_open_failed")?;
    let mut reader = BufReader::new(file);
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 64 * 1024].into_boxed_slice();
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| io_error("payload_hash_read_failed", error))?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(digest_identity(digest))
}

fn sha256_identity(bytes: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(bytes);
    digest_identity(digest)
}

fn digest_identity(digest: Sha256) -> String {
    let bytes = digest.finalize();
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in bytes {
        use fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, DistributionError> {
    let mut bytes = serde_json::to_vec(value).map_err(|error| {
        DistributionError::new(
            "distribution_json_encode_failed",
            format!("could not encode deterministic JSON: {error}"),
        )
    })?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn atomic_write_canonical<T: Serialize>(path: &Path, value: &T) -> Result<(), DistributionError> {
    let bytes = canonical_json(value)?;
    let parent = path.parent().ok_or_else(|| {
        DistributionError::new(
            "atomic_write_invalid",
            "atomic output has no parent directory",
        )
    })?;
    reject_symlink_if_present(path, "atomic output")?;
    let temporary = unique_path(parent, ".structural-state-tmp");
    write_new_file(&temporary, &bytes, 0o600)?;
    fs::rename(&temporary, path).map_err(|error| io_error("atomic_write_rename_failed", error))?;
    sync_directory(parent)
}

fn write_new_file(path: &Path, bytes: &[u8], mode: u32) -> Result<(), DistributionError> {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("file_create_failed", error))?;
    file.write_all(bytes)
        .map_err(|error| io_error("file_write_failed", error))?;
    set_mode(path, mode)?;
    file.sync_all()
        .map_err(|error| io_error("file_sync_failed", error))
}

fn read_canonical_json<T: for<'de> Deserialize<'de> + Serialize>(
    path: &Path,
    limit: u64,
) -> Result<T, DistributionError> {
    let bytes = read_bounded_regular_file(path, limit)?;
    let value: T = serde_json::from_slice(&bytes).map_err(|error| {
        DistributionError::new(
            "state_json_invalid",
            format!("installation state JSON is invalid: {error}"),
        )
    })?;
    if canonical_json(&value)? != bytes {
        return Err(DistributionError::new(
            "state_json_noncanonical",
            "installation state must use exact canonical JSON bytes",
        ));
    }
    Ok(value)
}

fn read_bounded_regular_file(path: &Path, limit: u64) -> Result<Vec<u8>, DistributionError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| io_error("bounded_file_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(DistributionError::new(
            "bounded_regular_file_required",
            "input must be a bounded regular non-symlink file",
        ));
    }
    let file = open_regular_no_follow(path, "bounded_file_open_failed")?;
    let opened_metadata = file
        .metadata()
        .map_err(|error| io_error("bounded_file_metadata_failed", error))?;
    if !opened_metadata.is_file() || opened_metadata.len() != metadata.len() {
        return Err(DistributionError::new(
            "bounded_file_changed",
            "bounded input changed while opening it",
        ));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(0));
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| io_error("bounded_file_read_failed", error))?;
    if bytes.len() as u64 > limit {
        return Err(DistributionError::new(
            "bounded_file_size_exceeded",
            "input grew beyond the byte limit while reading",
        ));
    }
    Ok(bytes)
}

fn ensure_directory(path: &Path, label: &str) -> Result<(), DistributionError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| io_error("directory_metadata_failed", error))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(DistributionError::new(
            "directory_required",
            format!("{label} must be a real directory"),
        ));
    }
    Ok(())
}

fn create_real_subdirectory(parent: &Path, name: &str) -> Result<(), DistributionError> {
    let path = parent.join(name);
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(DistributionError::new(
                "install_subdirectory_invalid",
                format!("install {name} path must be a real directory"),
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::create_dir(&path)
                .map_err(|error| io_error("install_subdirectory_create_failed", error))?;
        }
        Err(error) => return Err(io_error("install_subdirectory_inspect_failed", error)),
    }
    ensure_directory(&path, name)
}

fn path_entry_exists(path: &Path) -> Result<bool, DistributionError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(io_error("path_metadata_failed", error)),
    }
}

fn reject_symlink_if_present(path: &Path, label: &str) -> Result<(), DistributionError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => Err(DistributionError::new(
            "symlink_rejected",
            format!("{label} must not be a symlink"),
        )),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(io_error("path_metadata_failed", error)),
    }
}

fn sync_directory(path: &Path) -> Result<(), DistributionError> {
    File::open(path)
        .and_then(|file| file.sync_all())
        .map_err(|error| io_error("directory_sync_failed", error))
}

fn sync_directory_tree(root: &Path) -> Result<(), DistributionError> {
    fn visit(path: &Path, output: &mut Vec<PathBuf>) -> io::Result<()> {
        output.push(path.to_path_buf());
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                visit(&entry.path(), output)?;
            }
        }
        Ok(())
    }
    let mut directories = Vec::new();
    visit(root, &mut directories).map_err(|error| io_error("directory_walk_failed", error))?;
    directories.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
    for directory in directories {
        sync_directory(&directory)?;
    }
    Ok(())
}

fn release_path(install_root: &Path, release_id: &str) -> PathBuf {
    install_root.join(RELEASES_DIRECTORY).join(release_id)
}

fn unique_token() -> String {
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("{}-{sequence}", std::process::id())
}

fn unique_path(parent: &Path, prefix: &str) -> PathBuf {
    parent.join(format!("{prefix}-{}", unique_token()))
}

fn next_generation(current: Option<&ActivationStateV1>) -> Result<u64, DistributionError> {
    current.map_or(Ok(1), |state| {
        state.generation.checked_add(1).ok_or_else(|| {
            DistributionError::new(
                "activation_generation_overflow",
                "activation generation cannot be incremented",
            )
        })
    })
}

fn maybe_interrupt(
    actual: InstallInterruption,
    boundary: InstallInterruption,
) -> Result<(), DistributionError> {
    if actual == boundary {
        Err(DistributionError::new(
            "simulated_interruption",
            "test-only interruption at a durable transaction boundary",
        ))
    } else {
        Ok(())
    }
}

#[allow(clippy::needless_pass_by_value)]
fn io_error(code: &'static str, error: io::Error) -> DistributionError {
    DistributionError::new(code, error.to_string())
}

#[cfg(unix)]
fn open_regular_no_follow(path: &Path, code: &'static str) -> Result<File, DistributionError> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| io_error(code, error))
}

#[cfg(unix)]
fn open_install_lock(path: &Path) -> Result<File, DistributionError> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| io_error("install_lock_open_failed", error))
}

#[cfg(not(unix))]
fn open_install_lock(path: &Path) -> Result<File, DistributionError> {
    OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("install_lock_open_failed", error))
}

#[cfg(not(unix))]
fn open_regular_no_follow(path: &Path, code: &'static str) -> Result<File, DistributionError> {
    File::open(path).map_err(|error| io_error(code, error))
}

#[cfg(unix)]
fn portable_mode(metadata: &fs::Metadata) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    metadata.permissions().mode() & 0o777
}

#[cfg(not(unix))]
fn portable_mode(_metadata: &fs::Metadata) -> u32 {
    0o444
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> Result<(), DistributionError> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
        .map_err(|error| io_error("file_mode_set_failed", error))
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> Result<(), DistributionError> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn create(label: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "structural-distribution-{label}-{}",
                unique_token()
            ));
            fs::create_dir(&path).expect("create isolated distribution test directory");
            Self(path)
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).expect("remove isolated distribution test directory");
        }
    }

    fn create_payload(root: &Path, hip_enabled: bool, linkage: LinkageV1, marker: &str) {
        for directory in [
            "bin",
            "include/structural",
            "lib",
            "share/structural-native",
        ] {
            fs::create_dir_all(root.join(directory)).expect("create payload directory");
        }
        for binary in [
            "bin/structural-cli",
            "bin/structural-installer",
            "bin/structural-workbench",
        ] {
            fs::write(root.join(binary), format!("#!/bin/sh\necho {marker}\n"))
                .expect("write product binary fixture");
            set_mode(&root.join(binary), 0o755).expect("mark fixture executable");
        }
        fs::write(
            root.join("include/structural/abi_v1.h"),
            "/* ABI v1.12 */\n",
        )
        .expect("write ABI header fixture");
        let library = match linkage {
            LinkageV1::Shared => "lib/libstructural_c_abi_v1.so",
            LinkageV1::Static => "lib/libstructural_c_abi_v1.a",
        };
        fs::write(root.join(library), marker).expect("write library fixture");
        let build = serde_json::json!({
            "schema_version": BUILD_SCHEMA_VERSION,
            "package_version": "0.1.0",
            "abi_version": ABI_VERSION,
            "c_compiler": {"id": "GNU", "version": "14.2"},
            "cxx_compiler": {"id": "GNU", "version": "14.2"},
            "build_type": "Release",
            "hip_enabled": hip_enabled,
        });
        fs::write(
            root.join("share/structural-native/structural-native-build.json"),
            serde_json::to_vec_pretty(&build).expect("build manifest JSON"),
        )
        .expect("write build manifest fixture");
    }

    fn make_bundle(directory: &TestDirectory, release: &str, marker: &str) -> PathBuf {
        let payload = directory.0.join(format!("payload-{release}"));
        fs::create_dir(&payload).expect("create payload root");
        create_payload(&payload, false, LinkageV1::Shared, marker);
        let bundle = directory.0.join(format!("bundle-{release}"));
        create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &bundle,
            release_id: release,
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", marker.len()),
        })
        .expect("create bundle fixture");
        bundle
    }

    #[test]
    fn bundle_is_deterministic_and_tamper_evident() {
        let temporary = TestDirectory::create("bundle");
        let first = make_bundle(&temporary, "release-1", "one");
        let payload = temporary.0.join("payload-copy");
        fs::create_dir(&payload).expect("create second payload");
        create_payload(&payload, false, LinkageV1::Shared, "one");
        let second = temporary.0.join("bundle-copy");
        let second_manifest = create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &second,
            release_id: "release-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 3),
        })
        .expect("create deterministic copy");
        let first_manifest = verify_bundle(&first).expect("verify first bundle");
        assert_eq!(first_manifest, second_manifest);
        assert_eq!(
            fs::read(first.join(MANIFEST_NAME)).expect("first manifest"),
            fs::read(second.join(MANIFEST_NAME)).expect("second manifest")
        );
        let library = first
            .join(PAYLOAD_DIRECTORY)
            .join("lib/libstructural_c_abi_v1.so");
        set_mode(&library, 0o644).expect("make fixture writable for tamper");
        fs::write(&library, "tampered").expect("tamper payload");
        assert_eq!(
            verify_bundle(&first)
                .expect_err("tampered bundle must fail")
                .code,
            "bundle_payload_hash_mismatch"
        );
    }

    #[test]
    fn backend_build_identity_must_match() {
        let temporary = TestDirectory::create("backend");
        let payload = temporary.0.join("payload");
        fs::create_dir(&payload).expect("create payload");
        create_payload(&payload, false, LinkageV1::Shared, "cpu");
        let error = create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &temporary.0.join("bundle"),
            release_id: "rocm-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::Rocm,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 1),
        })
        .expect_err("CPU build must not become ROCm package");
        assert_eq!(error.code, "native_build_manifest_mismatch");
    }

    #[test]
    fn install_update_and_rollback_are_hash_bound() {
        let temporary = TestDirectory::create("lifecycle");
        let first = make_bundle(&temporary, "release-1", "one");
        let second = make_bundle(&temporary, "release-2", "two");
        let install = temporary.0.join("install");
        let state1 = install_bundle(&first, &install).expect("install first release");
        assert_eq!(state1.current_release, "release-1");
        assert_eq!(state1.previous_release, None);
        let state2 = install_bundle(&second, &install).expect("update second release");
        assert_eq!(state2.current_release, "release-2");
        assert_eq!(state2.previous_release.as_deref(), Some("release-1"));
        let rolled_back = rollback_install(&install).expect("rollback release");
        assert_eq!(rolled_back.current_release, "release-1");
        assert_eq!(rolled_back.previous_release.as_deref(), Some("release-2"));
        assert_eq!(
            installation_status(&install).expect("status"),
            Some(rolled_back)
        );
    }

    #[test]
    fn every_durable_install_boundary_recovers() {
        for interruption in [
            InstallInterruption::AfterPrepared,
            InstallInterruption::AfterMaterialized,
            InstallInterruption::AfterActivated,
        ] {
            let temporary = TestDirectory::create("recovery");
            let bundle = make_bundle(&temporary, "release-1", "one");
            let install = temporary.0.join("install");
            let error = install_bundle_inner(&bundle, &install, interruption)
                .expect_err("injected interruption must stop install");
            assert_eq!(error.code, "simulated_interruption");
            assert_eq!(
                installation_status(&install)
                    .expect_err("pending transaction makes status non-authoritative")
                    .code,
                "recovery_required"
            );
            let recovered = recover_install(&install).expect("recover interrupted install");
            assert_eq!(recovered.current_release, "release-1");
            assert_eq!(
                installation_status(&install).expect("status"),
                Some(recovered)
            );
        }
    }

    #[test]
    fn release_ids_are_immutable() {
        let temporary = TestDirectory::create("immutable");
        let first = make_bundle(&temporary, "release-1", "one");
        let install = temporary.0.join("install");
        install_bundle(&first, &install).expect("install release");
        let payload = temporary.0.join("replacement-payload");
        fs::create_dir(&payload).expect("replacement payload");
        create_payload(&payload, false, LinkageV1::Shared, "different");
        let replacement = temporary.0.join("replacement-bundle");
        create_bundle(&BundleCreateRequest {
            payload_root: &payload,
            output: &replacement,
            release_id: "release-1",
            package_version: "0.1.0",
            backend_profile: BackendProfileV1::CpuOnly,
            linkage: LinkageV1::Shared,
            source_sha256: &format!("sha256:{:064x}", 99),
        })
        .expect("create replacement");
        assert_eq!(
            install_bundle(&replacement, &install)
                .expect_err("release identity reuse must fail")
                .code,
            "release_id_immutable"
        );
    }

    #[test]
    fn activation_generation_overflow_fails_closed() {
        let state = ActivationStateV1 {
            schema_version: ACTIVATION_SCHEMA_VERSION.to_owned(),
            generation: u64::MAX,
            current_release: "release-1".to_owned(),
            previous_release: None,
            current_manifest_hash: format!("sha256:{:064x}", 1),
        };
        assert_eq!(
            next_generation(Some(&state))
                .expect_err("generation overflow must fail")
                .code,
            "activation_generation_overflow"
        );
    }

    #[cfg(unix)]
    #[test]
    fn install_rejects_symlinked_internal_directories() {
        use std::os::unix::fs::symlink;

        for name in [RELEASES_DIRECTORY, STATE_DIRECTORY] {
            let temporary = TestDirectory::create("install-symlink");
            let bundle = make_bundle(&temporary, "release-1", "one");
            let install = temporary.0.join("install");
            let redirected = temporary.0.join("redirected");
            fs::create_dir(&install).expect("create install root");
            fs::create_dir(&redirected).expect("create redirect target");
            symlink(&redirected, install.join(name)).expect("create internal directory symlink");
            assert_eq!(
                install_bundle(&bundle, &install)
                    .expect_err("internal directory symlink must fail")
                    .code,
                "install_subdirectory_invalid"
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn bundle_creation_rejects_external_symlink() {
        use std::os::unix::fs::symlink;

        let temporary = TestDirectory::create("symlink");
        let payload = temporary.0.join("payload");
        fs::create_dir(&payload).expect("create payload");
        create_payload(&payload, false, LinkageV1::Shared, "one");
        symlink("/etc/passwd", payload.join("escaped")).expect("create external symlink fixture");
        assert_eq!(
            create_bundle(&BundleCreateRequest {
                payload_root: &payload,
                output: &temporary.0.join("bundle"),
                release_id: "release-1",
                package_version: "0.1.0",
                backend_profile: BackendProfileV1::CpuOnly,
                linkage: LinkageV1::Shared,
                source_sha256: &format!("sha256:{:064x}", 1),
            })
            .expect_err("external symlink must fail")
            .code,
            "payload_symlink_escape"
        );
    }
}
