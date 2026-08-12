use std::collections::BTreeMap;
use std::ffi::OsString;
use std::io::Write as _;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_cli::{
    load_native_job_api_credentials, NativeJobApiError, NativeJobApiServerConfigV1,
    NativeJobApiServerV1,
};

const EXIT_FAILURE: u8 = 1;

#[derive(Clone, Debug, Eq, PartialEq)]
struct ServiceCommand {
    listen_address: SocketAddr,
    store_directory: PathBuf,
    client_token_file: PathBuf,
    worker_token_file: PathBuf,
    ready_file: Option<PathBuf>,
    maximum_requests: Option<u64>,
}

pub(crate) fn run_service(arguments: &[OsString]) -> Option<ExitCode> {
    let command = parse_service_arguments(arguments)?;
    Some(match execute_service_command(&command) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            println!(
                "{}",
                json!({
                    "schema_version": "structural-native-job-http-api-startup-error.v1",
                    "error": {
                        "code": error.code,
                        "detail": error.detail,
                    },
                    "claim_boundary": "startup_failure_without_credential_or_filesystem_disclosure",
                })
            );
            ExitCode::from(EXIT_FAILURE)
        }
    })
}

fn execute_service_command(command: &ServiceCommand) -> Result<(), NativeJobApiError> {
    let credentials =
        load_native_job_api_credentials(&command.client_token_file, &command.worker_token_file)?;
    let config = NativeJobApiServerConfigV1 {
        listen_address: command.listen_address,
        store_directory: command.store_directory.clone(),
        maximum_requests: command.maximum_requests,
    };
    let server = NativeJobApiServerV1::bind(&config, credentials)?;
    if let Some(path) = command.ready_file.as_ref() {
        server.publish_ready_file(path)?;
    }
    println!("{}", server.ready_json()?);
    std::io::stdout().flush().map_err(|_| NativeJobApiError {
        code: "job_api_ready_output_failed".to_owned(),
        detail: "startup metadata could not be flushed".to_owned(),
    })?;
    println!("{}", server.serve()?.canonical_json());
    Ok(())
}

fn parse_service_arguments(arguments: &[OsString]) -> Option<ServiceCommand> {
    if arguments.len() < 10 || arguments[0] != "service" || arguments[1] != "serve" {
        return None;
    }
    let flags = parse_flags(arguments, 2)?;
    if !(4..=6).contains(&flags.len())
        || !flags.keys().all(|key| {
            matches!(
                key.as_str(),
                "--listen"
                    | "--store"
                    | "--client-token-file"
                    | "--worker-token-file"
                    | "--ready-file"
                    | "--max-requests"
            )
        })
    {
        return None;
    }
    let maximum_requests = optional_integer_flag(&flags, "--max-requests").ok()?;
    if maximum_requests == Some(0) {
        return None;
    }
    Some(ServiceCommand {
        listen_address: string_flag(&flags, "--listen")?.parse().ok()?,
        store_directory: path_flag(&flags, "--store")?,
        client_token_file: path_flag(&flags, "--client-token-file")?,
        worker_token_file: path_flag(&flags, "--worker-token-file")?,
        ready_file: flags.get("--ready-file").map(PathBuf::from),
        maximum_requests,
    })
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

fn path_flag(flags: &BTreeMap<String, OsString>, name: &str) -> Option<PathBuf> {
    flags.get(name).map(PathBuf::from)
}

fn string_flag<'a>(flags: &'a BTreeMap<String, OsString>, name: &str) -> Option<&'a str> {
    flags.get(name)?.to_str()
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

#[cfg(test)]
mod tests {
    use super::{parse_service_arguments, ServiceCommand};
    use std::ffi::OsString;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn service_arguments_require_explicit_loopback_and_role_token_files() {
        assert_eq!(
            parse_service_arguments(&args(&[
                "service",
                "serve",
                "--listen",
                "127.0.0.1:0",
                "--store",
                "jobs",
                "--client-token-file",
                "client.token",
                "--worker-token-file",
                "worker.token",
                "--ready-file",
                "ready.json",
                "--max-requests",
                "5",
            ])),
            Some(ServiceCommand {
                listen_address: "127.0.0.1:0".parse().expect("socket address"),
                store_directory: "jobs".into(),
                client_token_file: "client.token".into(),
                worker_token_file: "worker.token".into(),
                ready_file: Some("ready.json".into()),
                maximum_requests: Some(5),
            })
        );
        assert!(parse_service_arguments(&args(&[
            "service",
            "serve",
            "--listen",
            "0.0.0.0:8080",
            "--store",
            "jobs",
            "--client-token-file",
            "client.token",
            "--worker-token-file",
            "worker.token",
            "--max-requests",
            "0",
        ]))
        .is_none());
    }
}
