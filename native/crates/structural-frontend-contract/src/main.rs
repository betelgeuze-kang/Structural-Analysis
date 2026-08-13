use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_frontend_contract::{
    canonical_delivery_receipt_json, canonical_receipt_json, canonical_smoke_receipt_json,
    canonical_viewer_manifest_receipt_json, canonical_viewer_server_receipt_json,
    canonical_workbench_prototype_receipt_json, check_frontend_contract, check_frontend_delivery,
    check_viewer_manifest, check_workbench_prototype, plan_viewer_server, run_frontend_smoke,
    serve_viewer, FrontendContractError,
};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE: u8 = 2;

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    match run(&arguments) {
        Ok(output) => {
            println!("{output}");
            ExitCode::SUCCESS
        }
        Err(CliError::Usage(detail)) => {
            print_error("frontend_contract_usage_error", &detail);
            ExitCode::from(EXIT_USAGE)
        }
        Err(CliError::Contract(error)) => {
            print_error(error.code, &error.detail);
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

#[derive(Debug)]
enum CliError {
    Usage(String),
    Contract(FrontendContractError),
}

impl From<FrontendContractError> for CliError {
    fn from(value: FrontendContractError) -> Self {
        Self::Contract(value)
    }
}

fn run(arguments: &[OsString]) -> Result<String, CliError> {
    if arguments.len() == 1 && arguments[0] == "--version" {
        return canonicalize_model_ir_v2(&json!({
            "schema_version": "structural-frontend-contract-version.v1",
            "version": env!("CARGO_PKG_VERSION"),
        }))
        .map_err(|error| CliError::Usage(error.to_string()));
    }
    let command = arguments
        .first()
        .and_then(|value| value.to_str())
        .ok_or_else(|| usage_error("missing or non-UTF-8 command"))?;
    if command == "smoke" {
        let (root, dry_run) = parse_smoke_arguments(&arguments[1..])?;
        let receipt = run_frontend_smoke(&root, dry_run)?;
        return canonical_smoke_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "serve" {
        let options = parse_serve_arguments(&arguments[1..])?;
        if options.dry_run {
            let receipt = plan_viewer_server(&options.root, &options.host, options.port)?;
            return canonical_viewer_server_receipt_json(&receipt).map_err(Into::into);
        }
        return match serve_viewer(&options.root, &options.host, options.port) {
            Ok(never) => match never {},
            Err(error) => Err(error.into()),
        };
    }
    let options = parse_options(&arguments[1..])?;
    match command {
        "check" => {
            require_exact_options(&options, &["--root"])?;
            let receipt = check_frontend_contract(&required_path(&options, "--root")?)?;
            canonical_receipt_json(&receipt).map_err(Into::into)
        }
        "delivery" => {
            require_exact_options(&options, &["--root"])?;
            let receipt = check_frontend_delivery(&required_path(&options, "--root")?)?;
            canonical_delivery_receipt_json(&receipt).map_err(Into::into)
        }
        "viewer-manifest" => {
            require_exact_options(&options, &["--root"])?;
            let receipt = check_viewer_manifest(&required_path(&options, "--root")?)?;
            canonical_viewer_manifest_receipt_json(&receipt).map_err(Into::into)
        }
        "prototype" => {
            require_exact_options(&options, &["--root"])?;
            let receipt = check_workbench_prototype(&required_path(&options, "--root")?)?;
            canonical_workbench_prototype_receipt_json(&receipt).map_err(Into::into)
        }
        _ => Err(usage_error(
            "command must be check, delivery, prototype, serve, smoke, or viewer-manifest",
        )),
    }
}

#[derive(Debug, Eq, PartialEq)]
struct ServeOptions {
    root: PathBuf,
    host: String,
    port: u16,
    dry_run: bool,
}

fn parse_serve_arguments(arguments: &[OsString]) -> Result<ServeOptions, CliError> {
    let mut root = None;
    let mut host = None;
    let mut port = None;
    let mut dry_run = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("serve option names must be UTF-8"))?;
        if name == "--dry-run" {
            if dry_run {
                return Err(usage_error("duplicate options are not allowed"));
            }
            dry_run = true;
            index += 1;
            continue;
        }
        let value = arguments
            .get(index + 1)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| usage_error("serve value options require one non-empty value"))?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--host" if host.is_none() => {
                host = Some(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("--host must be UTF-8"))?
                        .to_owned(),
                );
            }
            "--port" if port.is_none() => {
                port = Some(parse_port(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("--port must be UTF-8"))?,
                )?);
            }
            "--root" | "--host" | "--port" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => return Err(usage_error("serve options are missing or unknown")),
        }
        index += 2;
    }
    let host = match host {
        Some(value) => value,
        None => optional_environment_utf8("STRUCTURE_VIEWER_HOST")?
            .unwrap_or_else(|| "127.0.0.1".to_owned()),
    };
    let port = match port {
        Some(value) => value,
        None => optional_environment_utf8("STRUCTURE_VIEWER_PORT")?
            .map(|value| parse_port(&value))
            .transpose()?
            .unwrap_or(8765),
    };
    Ok(ServeOptions {
        root: root.ok_or_else(|| usage_error("--root must be non-empty"))?,
        host,
        port,
        dry_run,
    })
}

fn optional_environment_utf8(name: &str) -> Result<Option<String>, CliError> {
    std::env::var_os(name)
        .map(|value| {
            value
                .into_string()
                .map_err(|_| usage_error(&format!("{name} must be UTF-8")))
        })
        .transpose()
}

fn parse_port(value: &str) -> Result<u16, CliError> {
    value
        .parse::<u16>()
        .ok()
        .filter(|port| *port > 0)
        .ok_or_else(|| usage_error("Viewer server port must be in 1..=65535"))
}

fn parse_smoke_arguments(arguments: &[OsString]) -> Result<(PathBuf, bool), CliError> {
    let mut root = None;
    let mut dry_run = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("smoke option names must be UTF-8"))?;
        match name {
            "--dry-run" => {
                if dry_run {
                    return Err(usage_error("duplicate options are not allowed"));
                }
                dry_run = true;
                index += 1;
            }
            "--root" => {
                if root.is_some() {
                    return Err(usage_error("duplicate options are not allowed"));
                }
                let value = arguments
                    .get(index + 1)
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| usage_error("--root must have one non-empty value"))?;
                root = Some(PathBuf::from(value));
                index += 2;
            }
            _ => return Err(usage_error("smoke options are missing or unknown")),
        }
    }
    Ok((
        root.ok_or_else(|| usage_error("--root must be non-empty"))?,
        dry_run,
    ))
}

fn parse_options(arguments: &[OsString]) -> Result<BTreeMap<String, OsString>, CliError> {
    if arguments.len() % 2 != 0 {
        return Err(usage_error("every option must have one value"));
    }
    let mut options = BTreeMap::new();
    for pair in arguments.chunks_exact(2) {
        let name = pair[0]
            .to_str()
            .filter(|value| value.starts_with("--"))
            .ok_or_else(|| usage_error("option names must be UTF-8 --tokens"))?;
        if options.insert(name.to_owned(), pair[1].clone()).is_some() {
            return Err(usage_error("duplicate options are not allowed"));
        }
    }
    Ok(options)
}

fn require_exact_options(
    options: &BTreeMap<String, OsString>,
    expected: &[&str],
) -> Result<(), CliError> {
    let actual = options.keys().map(String::as_str).collect::<Vec<_>>();
    let mut expected = expected.to_vec();
    expected.sort_unstable();
    if actual != expected {
        return Err(usage_error("command options are missing or unknown"));
    }
    Ok(())
}

fn required_path(options: &BTreeMap<String, OsString>, name: &str) -> Result<PathBuf, CliError> {
    options
        .get(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or_else(|| usage_error(&format!("{name} must be non-empty")))
}

fn print_error(code: &str, detail: &str) {
    let value = json!({
        "schema_version": "structural-frontend-contract-error.v1",
        "code": code,
        "detail": detail,
    });
    match canonicalize_model_ir_v2(&value) {
        Ok(output) => println!("{output}"),
        Err(_) => println!(
            "{{\"code\":\"frontend_contract_error_encode_failed\",\"detail\":\"failed to encode frontend contract error\",\"schema_version\":\"structural-frontend-contract-error.v1\"}}"
        ),
    }
}

fn usage_error(detail: &str) -> CliError {
    CliError::Usage(format!("{detail}; {}", usage()))
}

fn usage() -> &'static str {
    "usage: structural-frontend-contract check|delivery|prototype|viewer-manifest --root DIR; structural-frontend-contract smoke --root DIR [--dry-run]; structural-frontend-contract serve --root DIR [--host 127.0.0.1] [--port PORT] [--dry-run]"
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::path::PathBuf;

    use super::{parse_serve_arguments, parse_smoke_arguments, run, ServeOptions};

    #[test]
    fn parser_rejects_unknown_duplicate_and_incomplete_options() {
        assert!(run(&[]).is_err());
        assert!(run(&[OsString::from("check"), OsString::from("--root"),]).is_err());
        assert!(run(&[
            OsString::from("check"),
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--root"),
            OsString::from("b"),
        ])
        .is_err());
        assert!(run(&[
            OsString::from("check"),
            OsString::from("--unknown"),
            OsString::from("a"),
        ])
        .is_err());
        assert!(parse_smoke_arguments(&[]).is_err());
        assert!(parse_smoke_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--dry-run"),
            OsString::from("--dry-run"),
        ])
        .is_err());
        assert_eq!(
            parse_smoke_arguments(&[
                OsString::from("--dry-run"),
                OsString::from("--root"),
                OsString::from("a"),
            ])
            .expect("valid smoke arguments"),
            (PathBuf::from("a"), true)
        );
        assert_eq!(
            parse_serve_arguments(&[
                OsString::from("--root"),
                OsString::from("a"),
                OsString::from("--host"),
                OsString::from("127.0.0.1"),
                OsString::from("--port"),
                OsString::from("8765"),
                OsString::from("--dry-run"),
            ])
            .expect("valid serve arguments"),
            ServeOptions {
                root: PathBuf::from("a"),
                host: "127.0.0.1".to_owned(),
                port: 8765,
                dry_run: true,
            }
        );
        assert!(parse_serve_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--port"),
            OsString::from("0"),
        ])
        .is_err());
    }
}
