use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde_json::json;
use structural_cli::{execute_next_durable_job, export_durable_job, DurableJobCommandError};
use structural_runtime::{unix_time_millis, DurableJobStoreV1, DurableJobViewV1};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE_OR_INVALID: u8 = 2;

#[derive(Clone, Debug, Eq, PartialEq)]
enum JobCommand {
    Submit {
        request_path: PathBuf,
        store_directory: PathBuf,
        idempotency_key: String,
    },
    SubmitModelLinear {
        model_path: PathBuf,
        request_path: PathBuf,
        store_directory: PathBuf,
        idempotency_key: String,
    },
    SubmitModelBuckling {
        model_path: PathBuf,
        request_path: PathBuf,
        store_directory: PathBuf,
        idempotency_key: String,
    },
    Poll {
        job_id: String,
        store_directory: PathBuf,
    },
    Cancel {
        job_id: String,
        store_directory: PathBuf,
    },
    WorkOnce {
        store_directory: PathBuf,
        worker_id: String,
        lease_millis: u64,
        step_budget: u32,
    },
    Recover {
        store_directory: PathBuf,
    },
    Export {
        job_id: String,
        store_directory: PathBuf,
        output_directory: PathBuf,
    },
}

pub(crate) fn run_job(arguments: &[OsString]) -> Option<ExitCode> {
    let command = parse_job_arguments(arguments)?;
    Some(match execute_job_command(&command) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            print_command_error(&error);
            ExitCode::from(if error.is_contract_error() {
                EXIT_USAGE_OR_INVALID
            } else {
                EXIT_FAILURE
            })
        }
    })
}

fn execute_job_command(command: &JobCommand) -> Result<(), DurableJobCommandError> {
    match command {
        JobCommand::Submit {
            request_path,
            store_directory,
            idempotency_key,
        } => {
            let request = std::fs::read(request_path).map_err(|error| {
                io_command_error(
                    "durable_job_request_read_failed",
                    &format!("could not read durable job request: {error}"),
                )
            })?;
            let store = DurableJobStoreV1::open(store_directory)?;
            let view = store.submit(idempotency_key, &request, unix_time_millis()?)?;
            print_view(&view);
        }
        JobCommand::SubmitModelLinear {
            model_path,
            request_path,
            store_directory,
            idempotency_key,
        } => {
            execute_model_linear_submit(
                model_path,
                request_path,
                store_directory,
                idempotency_key,
            )?;
        }
        JobCommand::SubmitModelBuckling {
            model_path,
            request_path,
            store_directory,
            idempotency_key,
        } => execute_model_buckling_submit(
            model_path,
            request_path,
            store_directory,
            idempotency_key,
        )?,
        JobCommand::Poll {
            job_id,
            store_directory,
        } => {
            let store = DurableJobStoreV1::open(store_directory)?;
            print_view(&store.poll(job_id)?);
        }
        JobCommand::Cancel {
            job_id,
            store_directory,
        } => {
            let store = DurableJobStoreV1::open(store_directory)?;
            print_view(&store.request_cancel(job_id, unix_time_millis()?)?);
        }
        JobCommand::WorkOnce {
            store_directory,
            worker_id,
            lease_millis,
            step_budget,
        } => {
            let store = DurableJobStoreV1::open(store_directory)?;
            if let Some(view) =
                execute_next_durable_job(&store, worker_id, *lease_millis, *step_budget)?
            {
                print_view(&view);
            } else {
                println!(
                    "{}",
                    json!({
                        "schema_version": "structural-native-durable-job-command.v1",
                        "status": "idle",
                        "claim_boundary": "single_host_local_worker_queue_empty"
                    })
                );
            }
        }
        JobCommand::Recover { store_directory } => {
            let store = DurableJobStoreV1::open(store_directory)?;
            let recovered = store.recover_expired_leases(unix_time_millis()?)?;
            println!(
                "{}",
                json!({
                    "schema_version": "structural-native-durable-job-command.v1",
                    "status": "recovered",
                    "recovered_job_count": recovered,
                    "claim_boundary": "single_host_expired_lease_reconciliation"
                })
            );
        }
        JobCommand::Export {
            job_id,
            store_directory,
            output_directory,
        } => {
            let store = DurableJobStoreV1::open(store_directory)?;
            println!("{}", export_durable_job(&store, job_id, output_directory)?);
        }
    }
    Ok(())
}

fn execute_model_buckling_submit(
    model_path: &Path,
    request_path: &Path,
    store_directory: &Path,
    idempotency_key: &str,
) -> Result<(), DurableJobCommandError> {
    let model = read_bounded_regular_file(model_path, 64 * 1024 * 1024, "model")?;
    let request = read_bounded_regular_file(request_path, 4 * 1024 * 1024, "analysis request")?;
    let store = DurableJobStoreV1::open(store_directory)?;
    let view = store.submit_model_ir_linear_buckling(
        idempotency_key,
        &model,
        &request,
        unix_time_millis()?,
    )?;
    print_view(&view);
    Ok(())
}

fn execute_model_linear_submit(
    model_path: &Path,
    request_path: &Path,
    store_directory: &Path,
    idempotency_key: &str,
) -> Result<(), DurableJobCommandError> {
    let model = read_bounded_regular_file(model_path, 64 * 1024 * 1024, "model")?;
    let request = read_bounded_regular_file(request_path, 4 * 1024 * 1024, "analysis request")?;
    let store = DurableJobStoreV1::open(store_directory)?;
    let view =
        store.submit_model_ir_linear(idempotency_key, &model, &request, unix_time_millis()?)?;
    print_view(&view);
    Ok(())
}

fn print_view(view: &DurableJobViewV1) {
    println!(
        "{}",
        json!({
            "schema_version": "structural-native-durable-job-command.v1",
            "job": view,
            "claim_boundary": "single_host_local_durable_job_not_distributed_consensus_identity_authorization_or_release_authority"
        })
    );
}

fn print_command_error(error: &DurableJobCommandError) {
    let (code, path, detail) = match error {
        DurableJobCommandError::Store(error) => {
            (error.code.clone(), error.path.clone(), error.detail.clone())
        }
        DurableJobCommandError::Product(error) => (
            "durable_job_native_product_failed".to_owned(),
            "/worker".to_owned(),
            error.to_string(),
        ),
        DurableJobCommandError::ModelLinearProduct(error) => (
            "durable_job_model_ir_linear_product_failed".to_owned(),
            "/worker".to_owned(),
            error.to_string(),
        ),
        DurableJobCommandError::ModelBucklingProduct(error) => (
            "durable_job_model_ir_buckling_product_failed".to_owned(),
            "/worker".to_owned(),
            error.to_string(),
        ),
        DurableJobCommandError::Invariant { code, detail } => {
            (code.clone(), "/job".to_owned(), detail.clone())
        }
    };
    println!(
        "{}",
        json!({
            "schema_version": "structural-native-durable-job-failure.v1",
            "code": code,
            "path": path,
            "detail": detail
        })
    );
}

fn parse_job_arguments(arguments: &[OsString]) -> Option<JobCommand> {
    if arguments.len() < 2 || arguments[0] != "job" {
        return None;
    }
    match arguments[1].to_str()? {
        "submit" if arguments.len() >= 7 => {
            let flags = parse_flags(arguments, 3)?;
            Some(JobCommand::Submit {
                request_path: positional(arguments, 2)?,
                store_directory: path_flag(&flags, "--store")?,
                idempotency_key: string_flag(&flags, "--idempotency-key")?,
            })
            .filter(|_| flags.len() == 2)
        }
        "submit-model-linear" if arguments.len() >= 8 => {
            let flags = parse_flags(arguments, 4)?;
            Some(JobCommand::SubmitModelLinear {
                model_path: positional(arguments, 2)?,
                request_path: positional(arguments, 3)?,
                store_directory: path_flag(&flags, "--store")?,
                idempotency_key: string_flag(&flags, "--idempotency-key")?,
            })
            .filter(|_| flags.len() == 2)
        }
        "submit-model-buckling" if arguments.len() >= 8 => {
            let flags = parse_flags(arguments, 4)?;
            Some(JobCommand::SubmitModelBuckling {
                model_path: positional(arguments, 2)?,
                request_path: positional(arguments, 3)?,
                store_directory: path_flag(&flags, "--store")?,
                idempotency_key: string_flag(&flags, "--idempotency-key")?,
            })
            .filter(|_| flags.len() == 2)
        }
        "poll" if arguments.len() >= 5 => {
            parse_job_id_store(arguments, |job_id, store_directory| JobCommand::Poll {
                job_id,
                store_directory,
            })
        }
        "cancel" if arguments.len() >= 5 => {
            parse_job_id_store(arguments, |job_id, store_directory| JobCommand::Cancel {
                job_id,
                store_directory,
            })
        }
        "work-once" if arguments.len() >= 6 => {
            let flags = parse_flags(arguments, 2)?;
            let lease_millis = optional_integer_flag(&flags, "--lease-ms")
                .ok()?
                .unwrap_or(3_600_000);
            let step_budget = optional_integer_flag(&flags, "--step-budget")
                .ok()?
                .unwrap_or(u32::MAX);
            Some(JobCommand::WorkOnce {
                store_directory: path_flag(&flags, "--store")?,
                worker_id: string_flag(&flags, "--worker-id")?,
                lease_millis,
                step_budget,
            })
            .filter(|_| {
                (2..=4).contains(&flags.len())
                    && flags.keys().all(|key| {
                        matches!(
                            key.as_str(),
                            "--store" | "--worker-id" | "--lease-ms" | "--step-budget"
                        )
                    })
                    && step_budget > 0
            })
        }
        "recover" if arguments.len() == 4 => {
            let flags = parse_flags(arguments, 2)?;
            Some(JobCommand::Recover {
                store_directory: path_flag(&flags, "--store")?,
            })
            .filter(|_| flags.len() == 1)
        }
        "export" if arguments.len() >= 7 => {
            let flags = parse_flags(arguments, 3)?;
            Some(JobCommand::Export {
                job_id: string_positional(arguments, 2)?,
                store_directory: path_flag(&flags, "--store")?,
                output_directory: path_flag(&flags, "--output-dir")?,
            })
            .filter(|_| flags.len() == 2)
        }
        _ => None,
    }
}

fn parse_job_id_store(
    arguments: &[OsString],
    build: fn(String, PathBuf) -> JobCommand,
) -> Option<JobCommand> {
    let flags = parse_flags(arguments, 3)?;
    (flags.len() == 1).then(|| {
        Some(build(
            string_positional(arguments, 2)?,
            path_flag(&flags, "--store")?,
        ))
    })?
}

fn parse_flags(arguments: &[OsString], start: usize) -> Option<BTreeMap<String, OsString>> {
    let tail = arguments.get(start..)?;
    if tail.len() % 2 != 0 {
        return None;
    }
    let mut flags = BTreeMap::new();
    for pair in tail.chunks_exact(2) {
        let key = pair[0].to_str()?;
        if !key.starts_with("--")
            || pair[1].to_string_lossy().starts_with('-')
            || flags.insert(key.to_owned(), pair[1].clone()).is_some()
        {
            return None;
        }
    }
    Some(flags)
}

fn positional(arguments: &[OsString], index: usize) -> Option<PathBuf> {
    let value = arguments.get(index)?;
    (!value.to_string_lossy().starts_with('-')).then(|| PathBuf::from(value))
}

fn string_positional(arguments: &[OsString], index: usize) -> Option<String> {
    let value = arguments.get(index)?.to_str()?;
    (!value.starts_with('-')).then(|| value.to_owned())
}

fn path_flag(flags: &BTreeMap<String, OsString>, name: &str) -> Option<PathBuf> {
    flags.get(name).map(PathBuf::from)
}

fn string_flag(flags: &BTreeMap<String, OsString>, name: &str) -> Option<String> {
    flags.get(name)?.to_str().map(str::to_owned)
}

fn optional_integer_flag<T>(flags: &BTreeMap<String, OsString>, name: &str) -> Result<Option<T>, ()>
where
    T: std::str::FromStr,
{
    flags.get(name).map_or(Ok(None), |value| {
        value
            .to_str()
            .and_then(|value| value.parse().ok())
            .map(Some)
            .ok_or(())
    })
}

fn io_command_error(code: &str, detail: &str) -> DurableJobCommandError {
    DurableJobCommandError::Invariant {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}

fn read_bounded_regular_file(
    path: &std::path::Path,
    maximum: u64,
    label: &str,
) -> Result<Vec<u8>, DurableJobCommandError> {
    let path_metadata = std::fs::symlink_metadata(path).map_err(|error| {
        io_command_error(
            "durable_job_input_metadata_failed",
            &format!("could not inspect {label}: {error}"),
        )
    })?;
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || path_metadata.len() == 0
        || path_metadata.len() > maximum
    {
        return Err(io_command_error(
            "durable_job_input_type_or_size_invalid",
            &format!("{label} must be one bounded regular non-symlink file"),
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file: File = options.open(path).map_err(|error| {
        io_command_error(
            "durable_job_input_read_failed",
            &format!("could not open {label} without following symlinks: {error}"),
        )
    })?;
    let opened_metadata = file.metadata().map_err(|error| {
        io_command_error(
            "durable_job_input_metadata_failed",
            &format!("could not inspect opened {label}: {error}"),
        )
    })?;
    if !opened_metadata.is_file() || opened_metadata.len() == 0 || opened_metadata.len() > maximum {
        return Err(io_command_error(
            "durable_job_input_type_or_size_invalid",
            &format!("opened {label} is not one bounded regular file"),
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if path_metadata.dev() != opened_metadata.dev()
            || path_metadata.ino() != opened_metadata.ino()
        {
            return Err(io_command_error(
                "durable_job_input_changed",
                &format!("{label} changed while being opened"),
            ));
        }
    }
    let mut bytes = Vec::with_capacity(
        usize::try_from(opened_metadata.len().min(maximum)).map_err(|_| {
            io_command_error(
                "durable_job_input_size_invalid",
                &format!("{label} length does not fit the memory bound"),
            )
        })?,
    );
    let mut bounded = file.take(maximum.saturating_add(1));
    bounded.read_to_end(&mut bytes).map_err(|error| {
        io_command_error(
            "durable_job_input_read_failed",
            &format!("could not read {label}: {error}"),
        )
    })?;
    if bytes.is_empty()
        || u64::try_from(bytes.len()).ok() != Some(opened_metadata.len())
        || bytes.len() > usize::try_from(maximum).unwrap_or(usize::MAX)
    {
        return Err(io_command_error(
            "durable_job_input_changed",
            &format!("{label} changed while being read"),
        ));
    }
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::{parse_job_arguments, JobCommand};
    use std::ffi::OsString;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn durable_job_arguments_are_explicit_and_bounded() {
        assert_eq!(
            parse_job_arguments(&args(&[
                "job",
                "submit",
                "request.json",
                "--store",
                "jobs",
                "--idempotency-key",
                "case-1"
            ])),
            Some(JobCommand::Submit {
                request_path: "request.json".into(),
                store_directory: "jobs".into(),
                idempotency_key: "case-1".to_owned(),
            })
        );
        assert_eq!(
            parse_job_arguments(&args(&[
                "job",
                "submit-model-buckling",
                "model.json",
                "buckling.json",
                "--store",
                "jobs",
                "--idempotency-key",
                "buckling-case-1"
            ])),
            Some(JobCommand::SubmitModelBuckling {
                model_path: "model.json".into(),
                request_path: "buckling.json".into(),
                store_directory: "jobs".into(),
                idempotency_key: "buckling-case-1".to_owned(),
            })
        );
        assert_eq!(
            parse_job_arguments(&args(&[
                "job",
                "submit-model-linear",
                "model.json",
                "analysis.json",
                "--store",
                "jobs",
                "--idempotency-key",
                "model-case-1"
            ])),
            Some(JobCommand::SubmitModelLinear {
                model_path: "model.json".into(),
                request_path: "analysis.json".into(),
                store_directory: "jobs".into(),
                idempotency_key: "model-case-1".to_owned(),
            })
        );
        assert_eq!(
            parse_job_arguments(&args(&[
                "job",
                "work-once",
                "--store",
                "jobs",
                "--worker-id",
                "worker-1",
                "--step-budget",
                "2",
                "--lease-ms",
                "1000"
            ])),
            Some(JobCommand::WorkOnce {
                store_directory: "jobs".into(),
                worker_id: "worker-1".to_owned(),
                lease_millis: 1_000,
                step_budget: 2,
            })
        );
        assert!(parse_job_arguments(&args(&[
            "job",
            "work-once",
            "--store",
            "jobs",
            "--worker-id",
            "worker-1",
            "--step-budget",
            "0"
        ]))
        .is_none());
        assert!(parse_job_arguments(&args(&[
            "job", "poll", "job-id", "--store", "jobs", "--store", "other"
        ]))
        .is_none());
    }
}
