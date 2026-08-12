use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_cli::{
    contract_error_report, execute_native_analysis, publish_native_analysis, validate_model_bytes,
    validation_succeeds,
};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE_OR_INVALID: u8 = 2;

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    run(&arguments)
}

fn run(arguments: &[OsString]) -> ExitCode {
    if arguments.len() == 1 && arguments[0] == "--version" {
        println!("structural-cli {}", env!("CARGO_PKG_VERSION"));
        return ExitCode::SUCCESS;
    }
    if let Some((path, require_analysis_ready)) = parse_validate_arguments(arguments) {
        return run_model_validation(&path, require_analysis_ready);
    }
    if let Some(command) = parse_analysis_arguments(arguments) {
        return run_native_analysis(&command);
    }
    eprintln!(
        "usage:\n  structural-cli model validate <MODEL.json> [--require-analysis-ready]\n  structural-cli analysis run <REQUEST.json> --output-dir <DIR> [--step-budget <N>]\n  structural-cli analysis resume <REQUEST.json> <CHECKPOINT.ndcp> --output-dir <DIR> [--step-budget <N>]"
    );
    ExitCode::from(EXIT_USAGE_OR_INVALID)
}

fn run_model_validation(path: &PathBuf, require_analysis_ready: bool) -> ExitCode {
    let Ok(bytes) = std::fs::read(path) else {
        println!(
            "{}",
            json!({
                "schema_version": "structural-model-ir-rust-validation.v1",
                "schema_valid": false,
                "semantics_valid": false,
                "contract_valid": false,
                "analysis_ready": false,
                "issues": [{
                    "code": "input_read_error",
                    "path": "/",
                    "detail": "ModelIR input could not be read"
                }],
                "claim_boundary": "model_ir_input_read_before_wire_validation"
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    };
    match validate_model_bytes(&bytes) {
        Ok(validation) => {
            println!("{}", validation.report_json);
            if validation_succeeds(
                validation.report.contract_valid,
                validation.report.analysis_ready,
                require_analysis_ready,
            ) {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(EXIT_USAGE_OR_INVALID)
            }
        }
        Err(structural_cli::ModelValidationError::Contract(error)) => {
            println!("{}", contract_error_report(&error));
            ExitCode::from(EXIT_USAGE_OR_INVALID)
        }
        Err(structural_cli::ModelValidationError::Runtime(error)) => {
            println!(
                "{}",
                json!({
                    "schema_version": "structural-model-ir-native-failure.v1",
                    "schema_valid": true,
                    "semantics_valid": false,
                    "contract_valid": false,
                    "analysis_ready": false,
                    "issues": [{
                        "code": "native_runtime_error",
                        "path": "/",
                        "detail": error.message,
                        "status_code": error.code
                    }],
                    "claim_boundary": "native_model_ir_validation_failed_closed"
                })
            );
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct AnalysisCommand {
    request_path: PathBuf,
    checkpoint_path: Option<PathBuf>,
    output_directory: PathBuf,
    step_budget: u32,
}

fn run_native_analysis(command: &AnalysisCommand) -> ExitCode {
    let Ok(request_bytes) = std::fs::read(&command.request_path) else {
        println!(
            "{}",
            json!({
                "schema_version": "structural-native-analysis-failure.v1",
                "code": "request_read_error",
                "path": "/request",
                "detail": "native analysis request could not be read"
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    };
    let checkpoint_bytes = if let Some(path) = command.checkpoint_path.as_ref() {
        let Ok(bytes) = std::fs::read(path) else {
            println!(
                "{}",
                json!({
                    "schema_version": "structural-native-analysis-failure.v1",
                    "code": "checkpoint_read_error",
                    "path": "/checkpoint",
                    "detail": "native analysis checkpoint could not be read"
                })
            );
            return ExitCode::from(EXIT_FAILURE);
        };
        Some(bytes)
    } else {
        None
    };
    let outcome = match execute_native_analysis(
        &request_bytes,
        checkpoint_bytes.as_deref(),
        command.step_budget,
    ) {
        Ok(outcome) => outcome,
        Err(error) => {
            let exit = if error.is_contract_error() {
                EXIT_USAGE_OR_INVALID
            } else {
                EXIT_FAILURE
            };
            println!(
                "{}",
                json!({
                    "schema_version": "structural-native-analysis-failure.v1",
                    "code": "native_analysis_failed",
                    "detail": error.to_string()
                })
            );
            return ExitCode::from(exit);
        }
    };
    if let Err(error) = publish_native_analysis(&command.output_directory, &outcome) {
        println!(
            "{}",
            json!({
                "schema_version": "structural-native-analysis-failure.v1",
                "code": "native_analysis_publish_failed",
                "detail": error.to_string()
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    }
    println!("{}", outcome.run_receipt_json());
    ExitCode::SUCCESS
}

fn parse_validate_arguments(arguments: &[OsString]) -> Option<(PathBuf, bool)> {
    if arguments.len() < 3 || arguments[0] != "model" || arguments[1] != "validate" {
        return None;
    }
    let mut path = None;
    let mut require_analysis_ready = false;
    for argument in &arguments[2..] {
        if argument == "--require-analysis-ready" {
            if require_analysis_ready {
                return None;
            }
            require_analysis_ready = true;
        } else if argument.to_string_lossy().starts_with('-') || path.is_some() {
            return None;
        } else {
            path = Some(PathBuf::from(argument));
        }
    }
    path.map(|path| (path, require_analysis_ready))
}

fn parse_analysis_arguments(arguments: &[OsString]) -> Option<AnalysisCommand> {
    if arguments.len() < 5 || arguments[0] != "analysis" {
        return None;
    }
    let (positional_count, checkpoint_index) = if arguments[1] == "run" {
        (1_usize, None)
    } else if arguments[1] == "resume" {
        (2_usize, Some(3_usize))
    } else {
        return None;
    };
    let flag_start = 2 + positional_count;
    if arguments.len() < flag_start + 2 {
        return None;
    }
    let request_path = PathBuf::from(&arguments[2]);
    if arguments[2].to_string_lossy().starts_with('-') {
        return None;
    }
    let checkpoint_path = checkpoint_index.map(|index| PathBuf::from(&arguments[index]));
    if checkpoint_path
        .as_ref()
        .is_some_and(|path| path.as_os_str().to_string_lossy().starts_with('-'))
    {
        return None;
    }
    let mut output_directory = None;
    let mut step_budget = u32::MAX;
    let mut step_budget_seen = false;
    let mut index = flag_start;
    while index < arguments.len() {
        if arguments[index] == "--output-dir" && output_directory.is_none() {
            index += 1;
            if index >= arguments.len() || arguments[index].to_string_lossy().starts_with('-') {
                return None;
            }
            output_directory = Some(PathBuf::from(&arguments[index]));
        } else if arguments[index] == "--step-budget" && !step_budget_seen {
            index += 1;
            if index >= arguments.len() {
                return None;
            }
            step_budget = arguments[index].to_str()?.parse::<u32>().ok()?;
            if step_budget == 0 {
                return None;
            }
            step_budget_seen = true;
        } else {
            return None;
        }
        index += 1;
    }
    Some(AnalysisCommand {
        request_path,
        checkpoint_path,
        output_directory: output_directory?,
        step_budget,
    })
}

#[cfg(test)]
mod tests {
    use super::{parse_analysis_arguments, parse_validate_arguments, AnalysisCommand};
    use std::ffi::OsString;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn validation_arguments_accept_one_path_and_one_optional_policy() {
        assert_eq!(
            parse_validate_arguments(&args(&["model", "validate", "model.json"])),
            Some(("model.json".into(), false))
        );
        assert_eq!(
            parse_validate_arguments(&args(&[
                "model",
                "validate",
                "--require-analysis-ready",
                "model.json"
            ])),
            Some(("model.json".into(), true))
        );
        assert!(parse_validate_arguments(&args(&["model", "validate"])).is_none());
        assert!(
            parse_validate_arguments(&args(&["model", "validate", "a.json", "b.json"])).is_none()
        );
    }

    #[test]
    fn analysis_arguments_separate_run_and_resume_without_implicit_paths() {
        assert_eq!(
            parse_analysis_arguments(&args(&[
                "analysis",
                "run",
                "request.json",
                "--output-dir",
                "out",
                "--step-budget",
                "2"
            ])),
            Some(AnalysisCommand {
                request_path: "request.json".into(),
                checkpoint_path: None,
                output_directory: "out".into(),
                step_budget: 2,
            })
        );
        assert_eq!(
            parse_analysis_arguments(&args(&[
                "analysis",
                "resume",
                "request.json",
                "checkpoint.ndcp",
                "--output-dir",
                "out"
            ])),
            Some(AnalysisCommand {
                request_path: "request.json".into(),
                checkpoint_path: Some("checkpoint.ndcp".into()),
                output_directory: "out".into(),
                step_budget: u32::MAX,
            })
        );
        assert!(parse_analysis_arguments(&args(&[
            "analysis",
            "run",
            "request.json",
            "--step-budget",
            "0",
            "--output-dir",
            "out"
        ]))
        .is_none());
    }
}
