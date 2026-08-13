use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use structural_contracts::product_ir::sha256_identity;

use super::{read_bounded_regular_file, verify_real_directory, FrontendContractError};

pub(crate) const VERIFIED_PUBLICATION_STRATEGY: &str =
    "bounded_staging_then_backup_rename_with_rollback";
const MAX_PATH_BYTES: usize = 4096;
static PUBLICATION_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy)]
pub(crate) struct VerifiedPublicationCodes {
    pub output_invalid: &'static str,
    pub output_changed: &'static str,
    pub stage_failed: &'static str,
    pub publish_failed: &'static str,
    pub backup_cleanup_failed: &'static str,
}

#[derive(Clone)]
pub(crate) struct VerifiedPublicationTarget {
    pub requested: String,
    pub path: PathBuf,
    pub maximum_previous_bytes: u64,
    pub snapshot: VerifiedPublicationSnapshot,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct VerifiedPublicationSnapshot {
    pub state: &'static str,
    pub byte_length: Option<u64>,
    pub sha256: Option<String>,
}

pub(crate) struct VerifiedOutput<'a> {
    pub target: VerifiedPublicationTarget,
    pub bytes: &'a [u8],
    pub suffix: &'static str,
}

struct StagedTarget {
    target: VerifiedPublicationTarget,
    staged_path: PathBuf,
    backup_path: Option<PathBuf>,
    published: bool,
}

impl Drop for StagedTarget {
    fn drop(&mut self) {
        let _ignored = fs::remove_file(&self.staged_path);
    }
}

pub(crate) fn prepare_verified_publication_target(
    root: &Path,
    requested: &Path,
    maximum_previous_bytes: u64,
    label: &str,
    codes: VerifiedPublicationCodes,
) -> Result<VerifiedPublicationTarget, FrontendContractError> {
    let requested_string = portable_publication_path(requested, label, codes)?;
    let unresolved = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    let parent = unresolved.parent().ok_or_else(|| {
        FrontendContractError::new(
            codes.output_invalid,
            format!("{label} has no parent directory"),
        )
    })?;
    verify_real_directory(parent, &format!("{label} parent"))?;
    let parent = parent.canonicalize().map_err(|error| {
        FrontendContractError::new(
            codes.output_invalid,
            format!("canonicalize {label} parent failed: {error}"),
        )
    })?;
    let file_name = unresolved.file_name().ok_or_else(|| {
        FrontendContractError::new(codes.output_invalid, format!("{label} has no file name"))
    })?;
    let path = parent.join(file_name);
    let snapshot = inspect_target(&path, maximum_previous_bytes, label, codes)?;
    Ok(VerifiedPublicationTarget {
        requested: requested_string,
        path,
        maximum_previous_bytes,
        snapshot,
    })
}

pub(crate) fn portable_publication_path(
    path: &Path,
    label: &str,
    codes: VerifiedPublicationCodes,
) -> Result<String, FrontendContractError> {
    let value = path.to_str().ok_or_else(|| {
        FrontendContractError::new(codes.output_invalid, format!("{label} must be UTF-8"))
    })?;
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.chars().any(char::is_control) {
        return Err(FrontendContractError::new(
            codes.output_invalid,
            format!("{label} is empty, too long, or contains control characters"),
        ));
    }
    Ok(value.to_owned())
}

pub(crate) fn publish_verified_outputs(
    outputs: Vec<VerifiedOutput<'_>>,
    codes: VerifiedPublicationCodes,
) -> Result<(), FrontendContractError> {
    if outputs.is_empty() {
        return Err(FrontendContractError::new(
            codes.stage_failed,
            "verified publication requires at least one output",
        ));
    }
    let mut staged = Vec::with_capacity(outputs.len());
    for output in outputs {
        staged.push(stage_target(
            output.target,
            output.bytes,
            output.suffix,
            codes,
        )?);
    }

    for target in &staged {
        require_unchanged(target, "during generation", codes)?;
    }

    for index in 0..staged.len() {
        let unchanged = require_unchanged(&staged[index], "immediately before publication", codes);
        let publish = unchanged.and_then(|()| {
            publish_one(&mut staged[index]).map_err(|error| {
                FrontendContractError::new(
                    codes.publish_failed,
                    format!("publish verified output failed: {error}"),
                )
            })
        });
        if let Err(error) = publish {
            let rollback = rollback_publication(&mut staged);
            let detail = match rollback {
                Ok(()) => error.to_string(),
                Err(rollback_error) => {
                    format!("{error}; publication rollback also failed: {rollback_error}")
                }
            };
            return Err(FrontendContractError::new(codes.publish_failed, detail));
        }
    }

    for target in &mut staged {
        if let Some(backup) = target.backup_path.take() {
            fs::remove_file(&backup).map_err(|error| {
                FrontendContractError::new(
                    codes.backup_cleanup_failed,
                    format!(
                        "verified output was published but old output backup cleanup failed: {error}"
                    ),
                )
            })?;
        }
    }
    Ok(())
}

fn inspect_target(
    path: &Path,
    maximum_bytes: u64,
    label: &str,
    codes: VerifiedPublicationCodes,
) -> Result<VerifiedPublicationSnapshot, FrontendContractError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            Ok(VerifiedPublicationSnapshot {
                state: "absent",
                byte_length: None,
                sha256: None,
            })
        }
        Err(error) => Err(FrontendContractError::new(
            codes.output_invalid,
            format!("inspect {label} failed: {error}"),
        )),
        Ok(metadata) if metadata.file_type().is_file() => {
            let bytes = read_bounded_regular_file(path, maximum_bytes, label).map_err(|error| {
                FrontendContractError::new(
                    codes.output_invalid,
                    format!("read existing {label} failed bounded validation: {error}"),
                )
            })?;
            let byte_length = u64::try_from(bytes.len()).map_err(|_| {
                FrontendContractError::new(
                    codes.output_invalid,
                    format!("existing {label} length is not addressable"),
                )
            })?;
            Ok(VerifiedPublicationSnapshot {
                state: "regular_file",
                byte_length: Some(byte_length),
                sha256: Some(sha256_identity(&bytes)),
            })
        }
        Ok(_) => Err(FrontendContractError::new(
            codes.output_invalid,
            format!("{label} must be absent or an existing non-symlink regular file"),
        )),
    }
}

fn require_unchanged(
    target: &StagedTarget,
    phase: &str,
    codes: VerifiedPublicationCodes,
) -> Result<(), FrontendContractError> {
    let current = inspect_target(
        &target.target.path,
        target.target.maximum_previous_bytes,
        "publication output",
        codes,
    )?;
    if current != target.target.snapshot {
        return Err(FrontendContractError::new(
            codes.output_changed,
            format!("output changed {phase}: {}", target.target.path.display()),
        ));
    }
    Ok(())
}

fn stage_target(
    target: VerifiedPublicationTarget,
    bytes: &[u8],
    suffix: &str,
    codes: VerifiedPublicationCodes,
) -> Result<StagedTarget, FrontendContractError> {
    let parent = target.path.parent().ok_or_else(|| {
        FrontendContractError::new(codes.stage_failed, "publication target has no parent")
    })?;
    for _ in 0..1024 {
        let sequence = PUBLICATION_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            ".structural-verified-publication-{}-{sequence}.{suffix}.part",
            std::process::id()
        ));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                if let Err(error) = file.write_all(bytes).and_then(|()| file.sync_all()) {
                    let _ignored = fs::remove_file(&path);
                    return Err(FrontendContractError::new(
                        codes.stage_failed,
                        format!("stage verified output failed: {error}"),
                    ));
                }
                return Ok(StagedTarget {
                    target,
                    staged_path: path,
                    backup_path: None,
                    published: false,
                });
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(FrontendContractError::new(
                    codes.stage_failed,
                    format!("create verified output staging file failed: {error}"),
                ));
            }
        }
    }
    Err(FrontendContractError::new(
        codes.stage_failed,
        "could not allocate a unique verified output staging file",
    ))
}

fn publish_one(target: &mut StagedTarget) -> Result<(), std::io::Error> {
    if target.target.snapshot.state == "regular_file" {
        let backup = unique_unused_sibling(&target.target.path, "backup")?;
        fs::rename(&target.target.path, &backup)?;
        target.backup_path = Some(backup);
    }
    fs::rename(&target.staged_path, &target.target.path)?;
    target.published = true;
    Ok(())
}

fn unique_unused_sibling(path: &Path, suffix: &str) -> Result<PathBuf, std::io::Error> {
    let parent = path.parent().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::InvalidInput, "output has no parent")
    })?;
    for _ in 0..1024 {
        let sequence = PUBLICATION_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let candidate = parent.join(format!(
            ".structural-verified-publication-{}-{sequence}.{suffix}",
            std::process::id()
        ));
        match fs::symlink_metadata(&candidate) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(candidate),
            Ok(_) => {}
            Err(error) => return Err(error),
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "could not allocate a unique verified output backup path",
    ))
}

fn rollback_publication(targets: &mut [StagedTarget]) -> Result<(), String> {
    let mut failures = Vec::new();
    for target in targets.iter_mut().rev() {
        if target.published {
            if let Err(error) = fs::remove_file(&target.target.path) {
                failures.push(format!(
                    "remove new {} failed: {error}",
                    target.target.path.display()
                ));
                continue;
            }
            target.published = false;
        }
        if let Some(backup) = target.backup_path.take() {
            if let Err(error) = fs::rename(&backup, &target.target.path) {
                failures.push(format!(
                    "restore {} failed: {error}; backup retained at {}",
                    target.target.path.display(),
                    backup.display()
                ));
                target.backup_path = Some(backup);
            }
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(failures.join("; "))
    }
}
