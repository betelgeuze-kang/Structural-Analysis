use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_catalog::{
    build_benchmark_catalog, canonical_receipt_json, check_benchmark_catalog,
    BenchmarkCatalogBuildRequest, CatalogBuildError,
};
use structural_contracts::model_ir::canonicalize_model_ir_v2;

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
            print_error("catalog_usage_error", &detail);
            ExitCode::from(EXIT_USAGE)
        }
        Err(CliError::Catalog(error)) => {
            print_error(error.code, &error.detail);
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

#[derive(Debug)]
enum CliError {
    Usage(String),
    Catalog(CatalogBuildError),
}

impl From<CatalogBuildError> for CliError {
    fn from(value: CatalogBuildError) -> Self {
        Self::Catalog(value)
    }
}

fn run(arguments: &[OsString]) -> Result<String, CliError> {
    if arguments.len() == 1 && arguments[0] == "--version" {
        return canonicalize_model_ir_v2(&json!({
            "schema_version": "structural-catalog-version.v1",
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
            require_exact_options(&options, &["--root", "--catalog"])?;
            let receipt = check_benchmark_catalog(
                &required_path(&options, "--root")?,
                &required_path(&options, "--catalog")?,
            )?;
            canonical_receipt_json(&receipt).map_err(Into::into)
        }
        "build" => {
            require_exact_options(&options, &["--root", "--out", "--generated-at"])?;
            let root = required_path(&options, "--root")?;
            let output = required_path(&options, "--out")?;
            let generated_at = required_utf8(&options, "--generated-at")?;
            let receipt = build_benchmark_catalog(&BenchmarkCatalogBuildRequest {
                source_root: &root,
                output: &output,
                generated_at,
            })?;
            canonical_receipt_json(&receipt).map_err(Into::into)
        }
        _ => Err(usage_error("command must be check or build")),
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

fn required_utf8<'a>(
    options: &'a BTreeMap<String, OsString>,
    name: &str,
) -> Result<&'a str, CliError> {
    options
        .get(name)
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| usage_error(&format!("{name} must be non-empty UTF-8")))
}

fn print_error(code: &str, detail: &str) {
    let value = json!({
        "schema_version": "structural-catalog-error.v1",
        "code": code,
        "detail": detail,
    });
    match canonicalize_model_ir_v2(&value) {
        Ok(output) => println!("{output}"),
        Err(_) => println!(
            "{{\"code\":\"catalog_error_encode_failed\",\"detail\":\"failed to encode catalog error\",\"schema_version\":\"structural-catalog-error.v1\"}}"
        ),
    }
}

fn usage_error(detail: &str) -> CliError {
    CliError::Usage(format!("{detail}; {}", usage()))
}

fn usage() -> &'static str {
    "usage: structural-catalog check --root DIR --catalog FILE | structural-catalog build --root DIR --out FILE --generated-at RFC3339"
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;

    use super::run;

    #[test]
    fn parser_rejects_unknown_duplicate_and_incomplete_options() {
        assert!(run(&[
            OsString::from("check"),
            OsString::from("--root"),
            OsString::from("fixture"),
            OsString::from("--root"),
            OsString::from("again"),
        ])
        .is_err());
        assert!(run(&[
            OsString::from("build"),
            OsString::from("--root"),
            OsString::from("fixture"),
        ])
        .is_err());
        assert!(run(&[
            OsString::from("check"),
            OsString::from("--unknown"),
            OsString::from("fixture"),
        ])
        .is_err());
    }
}
