use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_frontend_contract::{
    canonical_delivery_receipt_json, canonical_receipt_json, check_frontend_contract,
    check_frontend_delivery, FrontendContractError,
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
        _ => Err(usage_error("command must be check or delivery")),
    }
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
    "usage: structural-frontend-contract check|delivery --root DIR"
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;

    use super::run;

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
    }
}
