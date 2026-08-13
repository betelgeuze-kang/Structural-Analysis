//! Strict, deterministic verification for the transitional legacy frontend contract.

#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::product_ir::sha256_identity;

const SOURCE_MAP_SCHEMA_V1: &str = "structural-legacy-frontend-build-contract.v1";
const RECEIPT_SCHEMA_V1: &str = "structural-native-frontend-contract-receipt.v1";
const MAX_SOURCE_MAP_BYTES: usize = 1024 * 1024;
const MAX_JSON_BYTES: u64 = 8 * 1024 * 1024;
const MAX_REQUIRED_FILES: usize = 256;
const MAX_PATH_BYTES: usize = 512;
const SOURCE_MAP_BYTES: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../decommission/legacy-frontend-build-contract-v1.json"
));

#[cfg(test)]
const TEST_SOURCE_MAP: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../decommission/legacy-frontend-build-contract-v1.json"
);

/// Stable frontend-contract failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrontendContractError {
    pub code: &'static str,
    pub detail: String,
}

impl FrontendContractError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for FrontendContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for FrontendContractError {}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct FrontendSourceMapV1 {
    schema_version: String,
    expected_package_name: String,
    expected_package_manager: String,
    minimum_lockfile_version: u64,
    forbidden_description_substrings: Vec<String>,
    required_files: Vec<String>,
    forbidden_paths: Vec<String>,
    expected_scripts: BTreeMap<String, String>,
    expected_dependencies: BTreeMap<String, String>,
    expected_dev_dependencies: BTreeMap<String, String>,
    claim_boundary: String,
}

#[derive(Debug)]
struct ValidatedPackage {
    name: String,
    version: String,
    manager: String,
    lockfile_version: u64,
}

/// Canonical, self-hashed result of one read-only contract check.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct FrontendContractReceiptV1 {
    pub schema_version: String,
    pub action: String,
    pub source_map_schema_version: String,
    pub source_map_sha256: String,
    pub package_name: String,
    pub package_version: String,
    pub package_manager: String,
    pub lockfile_version: u64,
    pub required_file_count: usize,
    pub required_file_inventory_sha256: String,
    pub package_json_sha256: String,
    pub package_lock_sha256: String,
    pub deterministic: bool,
    pub commands_executed: u64,
    pub network_access_count: u64,
    pub claim_boundary: String,
    pub receipt_hash: String,
}

/// Check the pinned legacy frontend package, lock metadata, and required source inventory.
///
/// # Errors
///
/// Rejects unsafe paths, symlinks, missing files, duplicate-key JSON, package or lock drift,
/// dependency drift, and malformed embedded contract metadata.
pub fn check_frontend_contract(
    root: &Path,
) -> Result<FrontendContractReceiptV1, FrontendContractError> {
    verify_real_directory(root, "frontend contract root")?;
    let source_map = parse_source_map()?;
    for path in &source_map.required_files {
        resolve_required_file(root, path)?;
    }
    for path in &source_map.forbidden_paths {
        if forbidden_path_present(root, path)? {
            return Err(FrontendContractError::new(
                "frontend_forbidden_path_present",
                format!("forbidden legacy frontend path is present: {path}"),
            ));
        }
    }

    let package_path = resolve_required_file(root, "package.json")?;
    let lock_path = resolve_required_file(root, "package-lock.json")?;
    let package_bytes = read_bounded_regular_file(&package_path, MAX_JSON_BYTES, "package.json")?;
    let lock_bytes = read_bounded_regular_file(&lock_path, MAX_JSON_BYTES, "package-lock.json")?;
    let package_object = decode_object(
        &package_bytes,
        "frontend_package_json_invalid",
        "package.json",
    )?;
    let lock_object = decode_object(
        &lock_bytes,
        "frontend_lock_json_invalid",
        "package-lock.json",
    )?;
    let validated = validate_package_and_lock(&package_object, &lock_object, &source_map)?;

    let inventory_json =
        canonical_struct(&source_map.required_files, "frontend_receipt_encode_failed")?;
    let mut receipt = FrontendContractReceiptV1 {
        schema_version: RECEIPT_SCHEMA_V1.to_owned(),
        action: "check".to_owned(),
        source_map_schema_version: source_map.schema_version,
        source_map_sha256: sha256_identity(SOURCE_MAP_BYTES),
        package_name: validated.name,
        package_version: validated.version,
        package_manager: validated.manager,
        lockfile_version: validated.lockfile_version,
        required_file_count: source_map.required_files.len(),
        required_file_inventory_sha256: sha256_identity(inventory_json.as_bytes()),
        package_json_sha256: sha256_identity(&package_bytes),
        package_lock_sha256: sha256_identity(&lock_bytes),
        deterministic: true,
        commands_executed: 0,
        network_access_count: 0,
        claim_boundary: source_map.claim_boundary,
        receipt_hash: String::new(),
    };
    receipt.receipt_hash = hash_without_receipt_hash(&receipt)?;
    Ok(receipt)
}

/// Encode a frontend-contract receipt as canonical JSON.
///
/// # Errors
///
/// Returns an error if the receipt cannot be projected into canonical JSON.
pub fn canonical_receipt_json(
    receipt: &FrontendContractReceiptV1,
) -> Result<String, FrontendContractError> {
    canonical_struct(receipt, "frontend_receipt_encode_failed")
}

fn parse_source_map() -> Result<FrontendSourceMapV1, FrontendContractError> {
    if SOURCE_MAP_BYTES.len() > MAX_SOURCE_MAP_BYTES {
        return Err(FrontendContractError::new(
            "frontend_source_map_too_large",
            "embedded frontend source map exceeds its size bound",
        ));
    }
    let value = decode_json_strict(SOURCE_MAP_BYTES).map_err(|error| {
        FrontendContractError::new(
            "frontend_source_map_json_invalid",
            format!("embedded frontend source map is invalid: {error}"),
        )
    })?;
    let source_map: FrontendSourceMapV1 = serde_json::from_value(value).map_err(|error| {
        FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            format!("embedded frontend source map fields are invalid: {error}"),
        )
    })?;
    validate_source_map(&source_map)?;
    Ok(source_map)
}

fn validate_source_map(source_map: &FrontendSourceMapV1) -> Result<(), FrontendContractError> {
    if source_map.schema_version != SOURCE_MAP_SCHEMA_V1
        || source_map.expected_package_name.is_empty()
        || source_map.expected_package_manager.is_empty()
        || source_map.minimum_lockfile_version == 0
        || source_map.required_files.is_empty()
        || source_map.required_files.len() > MAX_REQUIRED_FILES
        || source_map.expected_scripts.is_empty()
        || source_map.expected_dependencies.is_empty()
        || source_map.expected_dev_dependencies.is_empty()
        || source_map.claim_boundary.trim().is_empty()
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "embedded frontend source map has an invalid schema or empty required field",
        ));
    }
    let mut paths = BTreeSet::new();
    for path in source_map
        .required_files
        .iter()
        .chain(source_map.forbidden_paths.iter())
    {
        validate_relative_path(path)?;
        if !paths.insert(path.as_str()) {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                format!("frontend source-map path is duplicated: {path}"),
            ));
        }
    }
    if !source_map
        .required_files
        .iter()
        .any(|path| path == "package.json")
        || !source_map
            .required_files
            .iter()
            .any(|path| path == "package-lock.json")
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_contract_invalid",
            "frontend source map must require package.json and package-lock.json",
        ));
    }
    for substring in &source_map.forbidden_description_substrings {
        if substring.is_empty()
            || substring != &substring.to_lowercase()
            || substring.chars().any(char::is_control)
        {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                "forbidden description substrings must be lowercase bounded text",
            ));
        }
    }
    for (name, value) in source_map
        .expected_scripts
        .iter()
        .chain(source_map.expected_dependencies.iter())
        .chain(source_map.expected_dev_dependencies.iter())
    {
        if name.is_empty()
            || value.is_empty()
            || name.len() > 256
            || value.len() > 16 * 1024
            || name.chars().any(char::is_control)
            || value.chars().any(char::is_control)
        {
            return Err(FrontendContractError::new(
                "frontend_source_map_contract_invalid",
                "frontend source-map key/value is invalid",
            ));
        }
    }
    Ok(())
}

fn validate_package_and_lock(
    package: &Map<String, Value>,
    lock: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<ValidatedPackage, FrontendContractError> {
    let name = required_string(package, "name", "package.json")?;
    let version = required_string(package, "version", "package.json")?;
    let manager = required_string(package, "packageManager", "package.json")?;
    if name != source_map.expected_package_name {
        return Err(contract_drift("package name"));
    }
    if manager != source_map.expected_package_manager {
        return Err(contract_drift("package manager"));
    }
    if version.len() > 128 {
        return Err(contract_drift("package version"));
    }
    validate_package_description(package, source_map)?;
    validate_package_maps(package, source_map)?;

    let lock_name = required_string(lock, "name", "package-lock.json")?;
    let lock_version = required_string(lock, "version", "package-lock.json")?;
    let lockfile_version = required_u64(lock, "lockfileVersion", "package-lock.json")?;
    if lock_name != name
        || lock_version != version
        || lockfile_version < source_map.minimum_lockfile_version
    {
        return Err(contract_drift("lockfile root identity"));
    }
    let packages = required_object(lock, "packages", "package-lock.json")?;
    let root_package = packages
        .get("")
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift("lockfile packages[''] object"))?;
    if required_string(root_package, "name", "lockfile root package")? != name
        || required_string(root_package, "version", "lockfile root package")? != version
    {
        return Err(contract_drift("lockfile root package metadata"));
    }
    require_exact_map(
        root_package.get("dependencies"),
        &source_map.expected_dependencies,
        "lockfile root dependencies",
    )?;
    require_exact_map(
        root_package.get("devDependencies"),
        &source_map.expected_dev_dependencies,
        "lockfile root devDependencies",
    )?;
    Ok(ValidatedPackage {
        name,
        version,
        manager,
        lockfile_version,
    })
}

fn validate_package_description(
    package: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<(), FrontendContractError> {
    let description = optional_string(package, "description", "package.json")?.unwrap_or_default();
    let description_lower = description.to_lowercase();
    if source_map
        .forbidden_description_substrings
        .iter()
        .any(|substring| description_lower.contains(substring))
    {
        return Err(contract_drift("package description"));
    }
    Ok(())
}

fn validate_package_maps(
    package: &Map<String, Value>,
    source_map: &FrontendSourceMapV1,
) -> Result<(), FrontendContractError> {
    let scripts = object_of_strings(package.get("scripts"), "package.json scripts")?;
    for (name, expected) in &source_map.expected_scripts {
        if scripts.get(name) != Some(expected) {
            return Err(FrontendContractError::new(
                "frontend_script_drift",
                format!("package script differs from the pinned contract: {name}"),
            ));
        }
    }
    require_exact_map(
        package.get("dependencies"),
        &source_map.expected_dependencies,
        "package dependencies",
    )?;
    require_exact_map(
        package.get("devDependencies"),
        &source_map.expected_dev_dependencies,
        "package devDependencies",
    )
}

fn decode_object(
    bytes: &[u8],
    code: &'static str,
    label: &str,
) -> Result<Map<String, Value>, FrontendContractError> {
    let value = decode_json_strict(bytes).map_err(|error| {
        FrontendContractError::new(code, format!("{label} is invalid strict JSON: {error}"))
    })?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| FrontendContractError::new(code, format!("{label} must be a JSON object")))
}

fn required_object<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<&'a Map<String, Value>, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn required_string(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<String, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty() && value.len() <= 16 * 1024)
        .map(ToOwned::to_owned)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn optional_string(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<Option<String>, FrontendContractError> {
    match object.get(field) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) if value.len() <= 16 * 1024 => Ok(Some(value.clone())),
        Some(_) => Err(contract_drift(&format!("{label} field {field}"))),
    }
}

fn required_u64(
    object: &Map<String, Value>,
    field: &str,
    label: &str,
) -> Result<u64, FrontendContractError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| contract_drift(&format!("{label} field {field}")))
}

fn object_of_strings(
    value: Option<&Value>,
    label: &str,
) -> Result<BTreeMap<String, String>, FrontendContractError> {
    let object = value
        .and_then(Value::as_object)
        .ok_or_else(|| contract_drift(label))?;
    object
        .iter()
        .map(|(name, value)| {
            value
                .as_str()
                .map(|value| (name.clone(), value.to_owned()))
                .ok_or_else(|| contract_drift(label))
        })
        .collect()
}

fn require_exact_map(
    value: Option<&Value>,
    expected: &BTreeMap<String, String>,
    label: &str,
) -> Result<(), FrontendContractError> {
    let actual = object_of_strings(value, label)?;
    if &actual != expected
        || actual
            .values()
            .any(|version| version.starts_with('^') || version.starts_with('~'))
    {
        return Err(contract_drift(label));
    }
    Ok(())
}

fn contract_drift(label: &str) -> FrontendContractError {
    FrontendContractError::new(
        "frontend_contract_drift",
        format!("legacy frontend contract drifted at {label}"),
    )
}

fn validate_relative_path(relative: &str) -> Result<(), FrontendContractError> {
    if relative.is_empty()
        || relative.len() > MAX_PATH_BYTES
        || relative.contains('\\')
        || relative.chars().any(char::is_control)
        || Path::new(relative).is_absolute()
        || !Path::new(relative)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return Err(FrontendContractError::new(
            "frontend_source_map_path_invalid",
            format!("frontend contract path is unsafe: {relative}"),
        ));
    }
    Ok(())
}

fn resolve_required_file(root: &Path, relative: &str) -> Result<PathBuf, FrontendContractError> {
    validate_relative_path(relative)?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut path = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(FrontendContractError::new(
                "frontend_source_map_path_invalid",
                format!("frontend contract path is unsafe: {relative}"),
            ));
        };
        path.push(name);
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            let code = if error.kind() == std::io::ErrorKind::NotFound {
                "frontend_required_file_missing"
            } else {
                "frontend_io_error"
            };
            FrontendContractError::new(
                code,
                format!("inspect required frontend path {relative} failed: {error}"),
            )
        })?;
        if metadata.file_type().is_symlink() {
            return Err(FrontendContractError::new(
                "frontend_unsafe_path",
                format!("required frontend path traverses a symlink: {relative}"),
            ));
        }
        let final_component = index + 1 == components.len();
        if (final_component && !metadata.is_file()) || (!final_component && !metadata.is_dir()) {
            return Err(FrontendContractError::new(
                "frontend_required_file_invalid",
                format!("required frontend path has the wrong file type: {relative}"),
            ));
        }
    }
    Ok(path)
}

fn forbidden_path_present(root: &Path, relative: &str) -> Result<bool, FrontendContractError> {
    validate_relative_path(relative)?;
    let components = Path::new(relative).components().collect::<Vec<_>>();
    let mut path = root.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else {
            return Err(FrontendContractError::new(
                "frontend_source_map_path_invalid",
                format!("frontend contract path is unsafe: {relative}"),
            ));
        };
        path.push(name);
        match fs::symlink_metadata(&path) {
            Ok(metadata) => {
                if index + 1 == components.len() {
                    return Ok(true);
                }
                if metadata.file_type().is_symlink() || !metadata.is_dir() {
                    return Err(FrontendContractError::new(
                        "frontend_unsafe_path",
                        format!("forbidden frontend path has an unsafe parent: {relative}"),
                    ));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => {
                return Err(FrontendContractError::new(
                    "frontend_io_error",
                    format!("inspect forbidden frontend path failed: {error}"),
                ));
            }
        }
    }
    Ok(false)
}

fn verify_real_directory(path: &Path, label: &str) -> Result<(), FrontendContractError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect {label} failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(FrontendContractError::new(
            "frontend_unsafe_path",
            format!("{label} must be a real non-symlink directory"),
        ));
    }
    Ok(())
}

fn read_bounded_regular_file(
    path: &Path,
    limit: u64,
    label: &str,
) -> Result<Vec<u8>, FrontendContractError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect {label} failed: {error}"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > limit {
        return Err(FrontendContractError::new(
            "frontend_input_not_bounded_regular_file",
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
        FrontendContractError::new(
            "frontend_io_error",
            format!("open {label} without symlink traversal failed: {error}"),
        )
    })?;
    let opened = file.metadata().map_err(|error| {
        FrontendContractError::new(
            "frontend_io_error",
            format!("inspect opened {label} failed: {error}"),
        )
    })?;
    if !opened.is_file() || opened.len() != metadata.len() || opened.len() > limit {
        return Err(FrontendContractError::new(
            "frontend_input_changed",
            format!("{label} changed while being opened"),
        ));
    }
    let capacity = usize::try_from(opened.len()).map_err(|_| {
        FrontendContractError::new(
            "frontend_input_length_invalid",
            format!("{label} length is not addressable"),
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(limit.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| {
            FrontendContractError::new("frontend_io_error", format!("read {label} failed: {error}"))
        })?;
    if u64::try_from(bytes.len()).ok() != Some(opened.len()) {
        return Err(FrontendContractError::new(
            "frontend_input_changed",
            format!("{label} changed while being read"),
        ));
    }
    Ok(bytes)
}

fn hash_without_receipt_hash(
    receipt: &FrontendContractReceiptV1,
) -> Result<String, FrontendContractError> {
    let mut value = serde_json::to_value(receipt).map_err(|error| {
        FrontendContractError::new(
            "frontend_receipt_encode_failed",
            format!("project frontend receipt failed: {error}"),
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            FrontendContractError::new(
                "frontend_receipt_encode_failed",
                "frontend receipt projection is not an object",
            )
        })?
        .remove("receipt_hash");
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(
            "frontend_receipt_encode_failed",
            format!("canonicalize frontend receipt failed: {error}"),
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn canonical_struct<T: Serialize>(
    value: &T,
    code: &'static str,
) -> Result<String, FrontendContractError> {
    let value = serde_json::to_value(value).map_err(|error| {
        FrontendContractError::new(code, format!("project canonical JSON failed: {error}"))
    })?;
    canonicalize_model_ir_v2(&value).map_err(|error| {
        FrontendContractError::new(code, format!("canonical JSON failed: {error}"))
    })
}

#[cfg(test)]
mod tests {
    use super::{decode_object, validate_relative_path, TEST_SOURCE_MAP};

    #[test]
    fn embedded_source_map_is_strict_json() {
        let bytes = std::fs::read(TEST_SOURCE_MAP).expect("read embedded source map");
        let object = decode_object(&bytes, "test_json_invalid", "source map")
            .expect("strict source-map JSON");
        assert_eq!(
            object
                .get("schema_version")
                .and_then(serde_json::Value::as_str),
            Some("structural-legacy-frontend-build-contract.v1")
        );
    }

    #[test]
    fn relative_paths_reject_escape_absolute_and_backslash() {
        for invalid in ["", "../package.json", "/package.json", "src\\main.tsx"] {
            assert!(validate_relative_path(invalid).is_err(), "{invalid}");
        }
        assert!(validate_relative_path("src/main.tsx").is_ok());
    }

    #[test]
    fn strict_decoder_rejects_duplicate_keys_and_non_objects() {
        assert!(decode_object(
            b"{\"name\":\"a\",\"name\":\"b\"}",
            "test_json_invalid",
            "fixture"
        )
        .is_err());
        assert!(decode_object(b"[]", "test_json_invalid", "fixture").is_err());
    }
}
