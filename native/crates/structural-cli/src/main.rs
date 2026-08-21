use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::{json, Value};
use structural_cli::{
    analyze_frame3d_bytes, analyze_frame3d_combination_bytes, contract_error_report,
    validate_model_bytes, validation_succeeds, Frame3dAnalysisError,
};
use structural_report::build_linear_frame3d_report;

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
    match parse_command(arguments) {
        Some(Command::Validate {
            path,
            require_analysis_ready,
        }) => run_validate(&path, require_analysis_ready),
        Some(Command::Analyze(options)) => run_analyze(&options),
        None => {
            eprintln!(
                "usage:\n  structural-cli model validate <MODEL.json> [--require-analysis-ready]\n  structural-cli model analyze-frame3d <MODEL.json> (--load-pattern <ID> | --load-combination <ID>) --result-id <ID> [--output result-ir|report-ir|html --report-id <ID>]"
            );
            ExitCode::from(EXIT_USAGE_OR_INVALID)
        }
    }
}

fn run_validate(path: &PathBuf, require_analysis_ready: bool) -> ExitCode {
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

fn run_analyze(options: &AnalyzeOptions) -> ExitCode {
    let Ok(bytes) = std::fs::read(&options.path) else {
        println!(
            "{}",
            analysis_failure(
                "input_read_error",
                "/model",
                "ModelIR input could not be read",
                None,
            )
        );
        return ExitCode::from(EXIT_FAILURE);
    };
    let analysis = match &options.load_source {
        AnalysisLoadSource::Pattern(id) => analyze_frame3d_bytes(&bytes, id, &options.result_id),
        AnalysisLoadSource::Combination(id) => {
            analyze_frame3d_combination_bytes(&bytes, id, &options.result_id)
        }
    };
    let result = match analysis {
        Ok(result) => result,
        Err(Frame3dAnalysisError::Contract(error)) => {
            println!(
                "{}",
                analysis_failure(&error.code, &error.path, &error.detail, None)
            );
            return ExitCode::from(EXIT_USAGE_OR_INVALID);
        }
        Err(Frame3dAnalysisError::Runtime(error)) => {
            println!(
                "{}",
                analysis_failure(
                    "native_runtime_error",
                    "/analysis",
                    &error.message,
                    Some(error.code),
                )
            );
            return ExitCode::from(EXIT_FAILURE);
        }
    };
    match options.output {
        AnalysisOutput::ResultIr => match result.canonical_json() {
            Ok(json) => {
                println!("{json}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                println!(
                    "{}",
                    analysis_failure(&error.code, &error.path, &error.detail, None)
                );
                ExitCode::from(EXIT_FAILURE)
            }
        },
        AnalysisOutput::ReportIr | AnalysisOutput::Html => {
            let Some(report_id) = options.report_id.as_deref() else {
                println!(
                    "{}",
                    analysis_failure(
                        "report_identity_missing",
                        "/report_id",
                        "Report output requires an explicit report identity",
                        None,
                    )
                );
                return ExitCode::from(EXIT_USAGE_OR_INVALID);
            };
            let bundle = match build_linear_frame3d_report(&result, report_id) {
                Ok(bundle) => bundle,
                Err(error) => {
                    println!(
                        "{}",
                        analysis_failure(&error.code, &error.path, &error.detail, None)
                    );
                    return ExitCode::from(EXIT_USAGE_OR_INVALID);
                }
            };
            if options.output == AnalysisOutput::Html {
                print!("{}", bundle.html);
                ExitCode::SUCCESS
            } else {
                match bundle.report_ir.canonical_json() {
                    Ok(json) => {
                        println!("{json}");
                        ExitCode::SUCCESS
                    }
                    Err(error) => {
                        println!(
                            "{}",
                            analysis_failure(&error.code, &error.path, &error.detail, None)
                        );
                        ExitCode::from(EXIT_FAILURE)
                    }
                }
            }
        }
    }
}

fn analysis_failure(code: &str, path: &str, detail: &str, status_code: Option<u32>) -> Value {
    json!({
        "schema_version": "structural-native-linear-frame3d-analysis-failure.v1",
        "success": false,
        "issues": [{
            "code": code,
            "path": path,
            "detail": detail,
            "status_code": status_code,
        }],
        "claim_boundary": "bounded_native_frame3d_analysis_failed_closed_without_result_authority"
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum Command {
    Validate {
        path: PathBuf,
        require_analysis_ready: bool,
    },
    Analyze(AnalyzeOptions),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AnalysisOutput {
    ResultIr,
    ReportIr,
    Html,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct AnalyzeOptions {
    path: PathBuf,
    load_source: AnalysisLoadSource,
    result_id: String,
    report_id: Option<String>,
    output: AnalysisOutput,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum AnalysisLoadSource {
    Pattern(String),
    Combination(String),
}

fn parse_command(arguments: &[OsString]) -> Option<Command> {
    if let Some((path, require_analysis_ready)) = parse_validate_arguments(arguments) {
        return Some(Command::Validate {
            path,
            require_analysis_ready,
        });
    }
    parse_analyze_arguments(arguments).map(Command::Analyze)
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

fn parse_analyze_arguments(arguments: &[OsString]) -> Option<AnalyzeOptions> {
    if arguments.len() < 7 || arguments[0] != "model" || arguments[1] != "analyze-frame3d" {
        return None;
    }
    let mut path = None;
    let mut load_pattern_id = None;
    let mut load_combination_id = None;
    let mut result_id = None;
    let mut report_id = None;
    let mut output = None;
    let mut index = 2;
    while index < arguments.len() {
        let argument = &arguments[index];
        if matches!(
            argument.to_str(),
            Some(
                "--load-pattern"
                    | "--load-combination"
                    | "--result-id"
                    | "--report-id"
                    | "--output"
            )
        ) {
            let flag = argument.to_str()?;
            let value = arguments.get(index + 1)?.to_str()?;
            if value.starts_with('-') {
                return None;
            }
            match flag {
                "--load-pattern" if load_pattern_id.is_none() => {
                    load_pattern_id = Some(value.to_owned());
                }
                "--load-combination" if load_combination_id.is_none() => {
                    load_combination_id = Some(value.to_owned());
                }
                "--result-id" if result_id.is_none() => result_id = Some(value.to_owned()),
                "--report-id" if report_id.is_none() => report_id = Some(value.to_owned()),
                "--output" if output.is_none() => {
                    output = Some(match value {
                        "result-ir" => AnalysisOutput::ResultIr,
                        "report-ir" => AnalysisOutput::ReportIr,
                        "html" => AnalysisOutput::Html,
                        _ => return None,
                    });
                }
                _ => return None,
            }
            index += 2;
        } else if argument.to_string_lossy().starts_with('-') || path.is_some() {
            return None;
        } else {
            path = Some(PathBuf::from(argument));
            index += 1;
        }
    }
    let output = output.unwrap_or(AnalysisOutput::ResultIr);
    if (output == AnalysisOutput::ResultIr) == report_id.is_some() {
        return None;
    }
    let load_source = match (load_pattern_id, load_combination_id) {
        (Some(id), None) => AnalysisLoadSource::Pattern(id),
        (None, Some(id)) => AnalysisLoadSource::Combination(id),
        _ => return None,
    };
    Some(AnalyzeOptions {
        path: path?,
        load_source,
        result_id: result_id?,
        report_id,
        output,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        parse_analyze_arguments, parse_validate_arguments, AnalysisLoadSource, AnalysisOutput,
        AnalyzeOptions,
    };
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
    fn analysis_arguments_make_report_identity_and_output_explicit() {
        assert_eq!(
            parse_analyze_arguments(&args(&[
                "model",
                "analyze-frame3d",
                "model.json",
                "--load-pattern",
                "LC1",
                "--result-id",
                "result.LC1"
            ])),
            Some(AnalyzeOptions {
                path: "model.json".into(),
                load_source: AnalysisLoadSource::Pattern("LC1".to_owned()),
                result_id: "result.LC1".to_owned(),
                report_id: None,
                output: AnalysisOutput::ResultIr,
            })
        );
        assert_eq!(
            parse_analyze_arguments(&args(&[
                "model",
                "analyze-frame3d",
                "model.json",
                "--load-pattern",
                "LC1",
                "--result-id",
                "result.LC1",
                "--output",
                "html",
                "--report-id",
                "report.LC1"
            ]))
            .expect("report arguments")
            .output,
            AnalysisOutput::Html
        );
        assert!(parse_analyze_arguments(&args(&[
            "model",
            "analyze-frame3d",
            "model.json",
            "--load-pattern",
            "LC1",
            "--result-id",
            "result.LC1",
            "--output",
            "report-ir"
        ]))
        .is_none());
        assert_eq!(
            parse_analyze_arguments(&args(&[
                "model",
                "analyze-frame3d",
                "model.json",
                "--load-combination",
                "COMB1",
                "--result-id",
                "result.COMB1"
            ]))
            .expect("load combination arguments")
            .load_source,
            AnalysisLoadSource::Combination("COMB1".to_owned())
        );
        assert!(parse_analyze_arguments(&args(&[
            "model",
            "analyze-frame3d",
            "model.json",
            "--load-pattern",
            "LC1",
            "--load-combination",
            "COMB1",
            "--result-id",
            "result.invalid"
        ]))
        .is_none());
    }
}
