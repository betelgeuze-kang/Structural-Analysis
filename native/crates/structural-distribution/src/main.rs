use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde::Serialize;
use structural_distribution::{
    active_payload_path, create_bundle, create_rootfs_isolation_receipt, install_bundle,
    installation_status, recover_install, rollback_install, verify_bundle,
    verify_rootfs_isolation_receipt, BackendProfileV1, BundleCreateRequest, DistributionError,
    LinkageV1, RootfsIsolationProbeRequest,
};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE: u8 = 2;

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    match run(&arguments) {
        Ok(value) => match serde_json::to_string(&value) {
            Ok(json) => {
                println!("{json}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("distribution_json_encode_failed: {error}");
                ExitCode::from(EXIT_FAILURE)
            }
        },
        Err(CliError::Usage(detail)) => {
            eprintln!("{detail}\n{}", usage());
            ExitCode::from(EXIT_USAGE)
        }
        Err(CliError::Distribution(error)) => {
            eprintln!("{}: {}", error.code, error.detail);
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

#[derive(Debug)]
enum CliError {
    Usage(String),
    Distribution(DistributionError),
}

impl From<DistributionError> for CliError {
    fn from(value: DistributionError) -> Self {
        Self::Distribution(value)
    }
}

#[derive(Serialize)]
struct CommandResult<T: Serialize> {
    schema_version: &'static str,
    action: &'static str,
    result: T,
}

fn run(arguments: &[OsString]) -> Result<serde_json::Value, CliError> {
    if arguments.len() == 1 && arguments[0] == "--version" {
        return Ok(serde_json::json!({
            "schema_version": "structural-installer-version.v1",
            "version": env!("CARGO_PKG_VERSION")
        }));
    }
    let command = arguments
        .first()
        .and_then(|value| value.to_str())
        .ok_or_else(|| usage_error("missing or non-UTF-8 command"))?;
    let options = parse_options(&arguments[1..])?;
    let value = match command {
        "bundle-create" => {
            require_exact_options(
                &options,
                &[
                    "--payload",
                    "--output",
                    "--release-id",
                    "--package-version",
                    "--backend",
                    "--linkage",
                    "--source-sha256",
                ],
            )?;
            let payload = required_path(&options, "--payload")?;
            let output = required_path(&options, "--output")?;
            let release_id = required(&options, "--release-id")?;
            let package_version = required(&options, "--package-version")?;
            let backend = parse_backend(required(&options, "--backend")?)?;
            let linkage = parse_linkage(required(&options, "--linkage")?)?;
            let source_sha256 = required(&options, "--source-sha256")?;
            let manifest = create_bundle(&BundleCreateRequest {
                payload_root: &payload,
                output: &output,
                release_id,
                package_version,
                backend_profile: backend,
                linkage,
                source_sha256,
            })?;
            json_result("bundle_create", manifest)?
        }
        "bundle-verify" => {
            require_exact_options(&options, &["--bundle"])?;
            let manifest = verify_bundle(&required_path(&options, "--bundle")?)?;
            json_result("bundle_verify", manifest)?
        }
        "runtime-probe" => run_runtime_probe(&options)?,
        "runtime-receipt-verify" => run_runtime_receipt_verify(&options)?,
        "install" | "update" => {
            require_exact_options(&options, &["--bundle", "--root"])?;
            let state = install_bundle(
                &required_path(&options, "--bundle")?,
                &required_path(&options, "--root")?,
            )?;
            json_result(
                if command == "install" {
                    "install"
                } else {
                    "update"
                },
                state,
            )?
        }
        "rollback" => {
            require_exact_options(&options, &["--root"])?;
            let state = rollback_install(&required_path(&options, "--root")?)?;
            json_result("rollback", state)?
        }
        "recover" => {
            require_exact_options(&options, &["--root"])?;
            let state = recover_install(&required_path(&options, "--root")?)?;
            json_result("recover", state)?
        }
        "status" => {
            require_exact_options(&options, &["--root"])?;
            let root = required_path(&options, "--root")?;
            let state = installation_status(&root)?;
            let payload = active_payload_path(&root)?;
            json_result(
                "status",
                serde_json::json!({"activation": state, "payload": payload}),
            )?
        }
        _ => return Err(usage_error("unknown command")),
    };
    Ok(value)
}

fn run_runtime_probe(options: &BTreeMap<String, String>) -> Result<serde_json::Value, CliError> {
    require_exact_options(
        options,
        &[
            "--bundle",
            "--payload-root",
            "--workspace",
            "--workbench-root",
            "--mgt-workbench-root",
            "--workbench-inspect-before-review",
            "--workbench-review-show",
            "--workbench-inspect-after-review",
            "--workbench-export",
            "--mgt-workbench-inspect-before-review",
            "--mgt-workbench-review-show",
            "--mgt-workbench-inspect-after-review",
            "--mgt-workbench-export",
            "--receipt",
        ],
    )?;
    let bundle = required_path(options, "--bundle")?;
    let payload_root = required_path(options, "--payload-root")?;
    let workspace = required_path(options, "--workspace")?;
    let workbench_root = required_path(options, "--workbench-root")?;
    let mgt_workbench_root = required_path(options, "--mgt-workbench-root")?;
    let workbench_inspect_before_review =
        required_path(options, "--workbench-inspect-before-review")?;
    let workbench_review_show = required_path(options, "--workbench-review-show")?;
    let workbench_inspect_after_review =
        required_path(options, "--workbench-inspect-after-review")?;
    let workbench_export = required_path(options, "--workbench-export")?;
    let mgt_workbench_inspect_before_review =
        required_path(options, "--mgt-workbench-inspect-before-review")?;
    let mgt_workbench_review_show = required_path(options, "--mgt-workbench-review-show")?;
    let mgt_workbench_inspect_after_review =
        required_path(options, "--mgt-workbench-inspect-after-review")?;
    let mgt_workbench_export = required_path(options, "--mgt-workbench-export")?;
    let receipt = required_path(options, "--receipt")?;
    let result = create_rootfs_isolation_receipt(&RootfsIsolationProbeRequest {
        bundle: &bundle,
        payload_root: &payload_root,
        workspace: &workspace,
        workbench_root: &workbench_root,
        mgt_workbench_root: &mgt_workbench_root,
        workbench_inspect_before_review: &workbench_inspect_before_review,
        workbench_review_show: &workbench_review_show,
        workbench_inspect_after_review: &workbench_inspect_after_review,
        workbench_export: &workbench_export,
        mgt_workbench_inspect_before_review: &mgt_workbench_inspect_before_review,
        mgt_workbench_review_show: &mgt_workbench_review_show,
        mgt_workbench_inspect_after_review: &mgt_workbench_inspect_after_review,
        mgt_workbench_export: &mgt_workbench_export,
        receipt: &receipt,
    })?;
    json_result("runtime_probe", result)
}

fn run_runtime_receipt_verify(
    options: &BTreeMap<String, String>,
) -> Result<serde_json::Value, CliError> {
    require_exact_options(options, &["--receipt", "--bundle"])?;
    let receipt = verify_rootfs_isolation_receipt(
        &required_path(options, "--receipt")?,
        &required_path(options, "--bundle")?,
    )?;
    json_result("runtime_receipt_verify", receipt)
}

fn json_result<T: Serialize>(
    action: &'static str,
    result: T,
) -> Result<serde_json::Value, CliError> {
    serde_json::to_value(CommandResult {
        schema_version: "structural-installer-result.v1",
        action,
        result,
    })
    .map_err(|error| usage_error(&format!("could not encode command result: {error}")))
}

fn parse_options(arguments: &[OsString]) -> Result<BTreeMap<String, String>, CliError> {
    if arguments.len() % 2 != 0 {
        return Err(usage_error("options must be --name VALUE pairs"));
    }
    let mut options = BTreeMap::new();
    for pair in arguments.chunks_exact(2) {
        let name = pair[0]
            .to_str()
            .ok_or_else(|| usage_error("option names must be UTF-8"))?;
        let value = pair[1]
            .to_str()
            .ok_or_else(|| usage_error("option values must be UTF-8"))?;
        if !name.starts_with("--") || options.insert(name.to_owned(), value.to_owned()).is_some() {
            return Err(usage_error("option names must be unique --name tokens"));
        }
    }
    Ok(options)
}

fn required<'a>(options: &'a BTreeMap<String, String>, name: &str) -> Result<&'a str, CliError> {
    options
        .get(name)
        .map(String::as_str)
        .ok_or_else(|| usage_error(&format!("missing required option {name}")))
}

fn required_path(options: &BTreeMap<String, String>, name: &str) -> Result<PathBuf, CliError> {
    required(options, name).map(PathBuf::from)
}

fn require_exact_options(
    options: &BTreeMap<String, String>,
    expected: &[&str],
) -> Result<(), CliError> {
    if options.len() != expected.len() || expected.iter().any(|name| !options.contains_key(*name)) {
        return Err(usage_error(
            "command options differ from the exact contract",
        ));
    }
    Ok(())
}

fn parse_backend(value: &str) -> Result<BackendProfileV1, CliError> {
    match value {
        "cpu-only" => Ok(BackendProfileV1::CpuOnly),
        "rocm" => Ok(BackendProfileV1::Rocm),
        _ => Err(usage_error("--backend must be cpu-only or rocm")),
    }
}

fn parse_linkage(value: &str) -> Result<LinkageV1, CliError> {
    match value {
        "shared" => Ok(LinkageV1::Shared),
        "static" => Ok(LinkageV1::Static),
        _ => Err(usage_error("--linkage must be shared or static")),
    }
}

fn usage_error(detail: &str) -> CliError {
    CliError::Usage(detail.to_owned())
}

fn usage() -> &'static str {
    "usage:\n  structural-distribution bundle-create --payload DIR --output DIR --release-id ID --package-version VERSION --backend cpu-only|rocm --linkage shared|static --source-sha256 sha256:HEX\n  structural-distribution bundle-verify --bundle DIR\n  structural-distribution runtime-probe --bundle DIR --payload-root DIR --workspace DIR --workbench-root DIR --mgt-workbench-root DIR --workbench-inspect-before-review FILE --workbench-review-show FILE --workbench-inspect-after-review FILE --workbench-export FILE --mgt-workbench-inspect-before-review FILE --mgt-workbench-review-show FILE --mgt-workbench-inspect-after-review FILE --mgt-workbench-export FILE --receipt FILE\n  structural-distribution runtime-receipt-verify --receipt FILE --bundle DIR\n  structural-distribution install --bundle DIR --root DIR\n  structural-distribution update --bundle DIR --root DIR\n  structural-distribution rollback --root DIR\n  structural-distribution recover --root DIR\n  structural-distribution status --root DIR"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_rejects_duplicate_options() {
        let arguments = [
            OsString::from("status"),
            OsString::from("--root"),
            OsString::from("one"),
            OsString::from("--root"),
            OsString::from("two"),
        ];
        assert!(matches!(run(&arguments), Err(CliError::Usage(_))));
    }

    #[test]
    fn parser_rejects_unknown_options() {
        let arguments = [
            OsString::from("status"),
            OsString::from("--root"),
            OsString::from("one"),
            OsString::from("--typo"),
            OsString::from("ignored"),
        ];
        assert!(matches!(run(&arguments), Err(CliError::Usage(_))));
    }

    #[test]
    fn version_is_machine_readable() {
        let value = run(&[OsString::from("--version")]).expect("version result");
        assert_eq!(value["schema_version"], "structural-installer-version.v1");
    }
}
