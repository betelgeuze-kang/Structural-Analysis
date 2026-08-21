use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::{json, Value};
use structural_cli::{
    analyze_frame3d_bytes, analyze_frame3d_combination_bytes, contract_error_report,
    validate_model_bytes, validation_succeeds, Frame3dAnalysisError,
};
use structural_contracts::comparison_ir::create_linear_frame3d_comparison_ir_v1;
use structural_contracts::result_ir::parse_linear_frame3d_result_ir_v1;
use structural_report::{
    build_linear_frame3d_report, publish_linear_frame3d_workbench_bundle,
    render_linear_frame3d_comparison_html,
};
use structural_runtime::{
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobStatusV1, NativeFrame3dJobStore,
    NativeFrame3dJobViewV1,
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
    match parse_command(arguments) {
        Some(Command::Validate {
            path,
            require_analysis_ready,
        }) => run_validate(&path, require_analysis_ready),
        Some(Command::Analyze(options)) => run_analyze(&options),
        Some(Command::Compare(options)) => run_compare(&options),
        Some(Command::Job(command)) => run_job(&command),
        None => {
            eprintln!(
                "usage:\n  structural-cli model validate <MODEL.json> [--require-analysis-ready]\n  structural-cli model analyze-frame3d <MODEL.json> (--load-pattern <ID> | --load-combination <ID>) --result-id <ID> [--output result-ir|report-ir|html|workbench-bundle --report-id <ID> --output-dir <DIR>]\n  structural-cli result compare-frame3d <RESULT.json> <REFERENCE.json> --comparison-id <ID> [--output comparison-ir|html]\n  structural-cli job submit-frame3d <MODEL.json> --store <DIR> --job-id <ID> (--load-pattern <ID> | --load-combination <ID>) --result-id <ID> --report-id <ID>\n  structural-cli job run <JOB_ID> --store <DIR>\n  structural-cli job inspect <JOB_ID> --store <DIR>"
            );
            ExitCode::from(EXIT_USAGE_OR_INVALID)
        }
    }
}

fn run_compare(options: &CompareOptions) -> ExitCode {
    let Ok(result_bytes) = std::fs::read(&options.result_path) else {
        println!(
            "{}",
            comparison_failure(
                "comparison_result_read_failed",
                "/result",
                "ResultIR input could not be read"
            )
        );
        return ExitCode::from(EXIT_FAILURE);
    };
    let Ok(reference_bytes) = std::fs::read(&options.reference_path) else {
        println!(
            "{}",
            comparison_failure(
                "comparison_reference_read_failed",
                "/reference",
                "External reference input could not be read"
            )
        );
        return ExitCode::from(EXIT_FAILURE);
    };
    let result = match parse_linear_frame3d_result_ir_v1(&result_bytes) {
        Ok(result) => result,
        Err(error) => {
            println!(
                "{}",
                comparison_failure(&error.code, &error.path, &error.detail)
            );
            return ExitCode::from(EXIT_USAGE_OR_INVALID);
        }
    };
    let comparison = match create_linear_frame3d_comparison_ir_v1(
        &result,
        &reference_bytes,
        &options.comparison_id,
    ) {
        Ok(comparison) => comparison,
        Err(error) => {
            println!(
                "{}",
                comparison_failure(&error.code, &error.path, &error.detail)
            );
            return ExitCode::from(EXIT_USAGE_OR_INVALID);
        }
    };
    match options.output {
        ComparisonOutput::ComparisonIr => match comparison.canonical_json() {
            Ok(json) => println!("{json}"),
            Err(error) => {
                println!(
                    "{}",
                    comparison_failure(&error.code, &error.path, &error.detail)
                );
                return ExitCode::from(EXIT_FAILURE);
            }
        },
        ComparisonOutput::Html => {
            let report =
                match render_linear_frame3d_comparison_html(&comparison, &result, &reference_bytes)
                {
                    Ok(report) => report,
                    Err(error) => {
                        println!(
                            "{}",
                            comparison_failure(&error.code, &error.path, &error.detail)
                        );
                        return ExitCode::from(EXIT_FAILURE);
                    }
                };
            print!("{}", report.html);
        }
    }
    if comparison.summary.passed {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(EXIT_USAGE_OR_INVALID)
    }
}

fn comparison_failure(code: &str, path: &str, detail: &str) -> Value {
    json!({
        "schema_version": "structural-native-linear-frame3d-comparison-failure.v1",
        "success": false,
        "issues": [{"code": code, "path": path, "detail": detail}],
        "claim_boundary": "external_comparison_failed_closed_without_validation_design_or_release_authority"
    })
}

fn run_job(command: &JobCommand) -> ExitCode {
    match command {
        JobCommand::Submit(options) => {
            let Ok(model_bytes) = std::fs::read(&options.path) else {
                println!(
                    "{}",
                    job_failure(
                        "submit",
                        "native_job_input_read_failed",
                        "Submitted ModelIR could not be read",
                    )
                );
                return ExitCode::from(EXIT_FAILURE);
            };
            let store = NativeFrame3dJobStore::new(&options.store);
            match store.submit(
                &options.job_id,
                &model_bytes,
                options.load_source.clone(),
                &options.result_id,
                &options.report_id,
            ) {
                Ok(view) => emit_job_view(&view, false),
                Err(error) => {
                    println!("{}", job_failure("submit", &error.code, &error.detail));
                    ExitCode::from(EXIT_FAILURE)
                }
            }
        }
        JobCommand::Run { store, job_id } => match NativeFrame3dJobStore::new(store).run(job_id) {
            Ok(view) => emit_job_view(&view, true),
            Err(error) => {
                println!("{}", job_failure("run", &error.code, &error.detail));
                ExitCode::from(EXIT_FAILURE)
            }
        },
        JobCommand::Inspect { store, job_id } => {
            match NativeFrame3dJobStore::new(store).inspect(job_id) {
                Ok(view) => emit_job_view(&view, false),
                Err(error) => {
                    println!("{}", job_failure("inspect", &error.code, &error.detail));
                    ExitCode::from(EXIT_FAILURE)
                }
            }
        }
    }
}

fn emit_job_view(view: &NativeFrame3dJobViewV1, terminal_failure_is_error: bool) -> ExitCode {
    match view.canonical_json() {
        Ok(json) => {
            println!("{json}");
            if terminal_failure_is_error && view.status == NativeFrame3dJobStatusV1::Failed {
                ExitCode::from(EXIT_FAILURE)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(error) => {
            println!("{}", job_failure("serialize", &error.code, &error.detail));
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

fn job_failure(operation: &str, code: &str, detail: &str) -> Value {
    json!({
        "schema_version": "structural-native-linear-frame3d-job-operation-failure.v1",
        "success": false,
        "operation": operation,
        "issues": [{"code": code, "detail": detail}],
        "claim_boundary": "native_job_operation_failed_closed_without_result_or_release_authority"
    })
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
    emit_analysis_output(options, &result, &bytes)
}

fn emit_analysis_output(
    options: &AnalyzeOptions,
    result: &structural_runtime::LinearFrame3dResultIrV1,
    model_bytes: &[u8],
) -> ExitCode {
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
        AnalysisOutput::ReportIr | AnalysisOutput::Html | AnalysisOutput::WorkbenchBundle => {
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
            let bundle = match build_linear_frame3d_report(result, report_id) {
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
            } else if options.output == AnalysisOutput::WorkbenchBundle {
                let Some(output_dir) = options.output_dir.as_ref() else {
                    println!(
                        "{}",
                        analysis_failure(
                            "bundle_output_directory_missing",
                            "/output_dir",
                            "Workbench bundle output requires an explicit output directory",
                            None,
                        )
                    );
                    return ExitCode::from(EXIT_USAGE_OR_INVALID);
                };
                match publish_linear_frame3d_workbench_bundle(
                    output_dir,
                    model_bytes,
                    result,
                    &bundle,
                ) {
                    Ok(manifest) => {
                        println!("{manifest}");
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
    Compare(CompareOptions),
    Job(JobCommand),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ComparisonOutput {
    ComparisonIr,
    Html,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct CompareOptions {
    result_path: PathBuf,
    reference_path: PathBuf,
    comparison_id: String,
    output: ComparisonOutput,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum JobCommand {
    Submit(JobSubmitOptions),
    Run { store: PathBuf, job_id: String },
    Inspect { store: PathBuf, job_id: String },
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct JobSubmitOptions {
    path: PathBuf,
    store: PathBuf,
    job_id: String,
    load_source: NativeFrame3dJobLoadSourceV1,
    result_id: String,
    report_id: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AnalysisOutput {
    ResultIr,
    ReportIr,
    Html,
    WorkbenchBundle,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct AnalyzeOptions {
    path: PathBuf,
    load_source: AnalysisLoadSource,
    result_id: String,
    report_id: Option<String>,
    output: AnalysisOutput,
    output_dir: Option<PathBuf>,
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
    if let Some(options) = parse_analyze_arguments(arguments) {
        return Some(Command::Analyze(options));
    }
    if let Some(options) = parse_compare_arguments(arguments) {
        return Some(Command::Compare(options));
    }
    parse_job_arguments(arguments).map(Command::Job)
}

fn parse_compare_arguments(arguments: &[OsString]) -> Option<CompareOptions> {
    if arguments.len() < 6
        || arguments[0] != "result"
        || arguments[1] != "compare-frame3d"
        || arguments[2].to_string_lossy().starts_with('-')
        || arguments[3].to_string_lossy().starts_with('-')
    {
        return None;
    }
    let result_path = PathBuf::from(&arguments[2]);
    let reference_path = PathBuf::from(&arguments[3]);
    let mut comparison_id = None;
    let mut output = None;
    let mut index = 4;
    while index < arguments.len() {
        let flag = arguments.get(index)?.to_str()?;
        let value = arguments.get(index + 1)?.to_str()?;
        if value.starts_with('-') {
            return None;
        }
        match flag {
            "--comparison-id" if comparison_id.is_none() => {
                comparison_id = Some(value.to_owned());
            }
            "--output" if output.is_none() => {
                output = Some(match value {
                    "comparison-ir" => ComparisonOutput::ComparisonIr,
                    "html" => ComparisonOutput::Html,
                    _ => return None,
                });
            }
            _ => return None,
        }
        index += 2;
    }
    Some(CompareOptions {
        result_path,
        reference_path,
        comparison_id: comparison_id?,
        output: output.unwrap_or(ComparisonOutput::ComparisonIr),
    })
}

fn parse_job_arguments(arguments: &[OsString]) -> Option<JobCommand> {
    if arguments.len() < 2 || arguments[0] != "job" {
        return None;
    }
    if arguments[1] == "submit-frame3d" {
        return parse_job_submit_arguments(arguments).map(JobCommand::Submit);
    }
    if arguments.len() == 5
        && matches!(arguments[1].to_str(), Some("run" | "inspect"))
        && arguments[3] == "--store"
    {
        let job_id = arguments[2].to_str()?.to_owned();
        let store = PathBuf::from(&arguments[4]);
        return if arguments[1] == "run" {
            Some(JobCommand::Run { store, job_id })
        } else {
            Some(JobCommand::Inspect { store, job_id })
        };
    }
    None
}

fn parse_job_submit_arguments(arguments: &[OsString]) -> Option<JobSubmitOptions> {
    if arguments.len() < 13 || arguments[0] != "job" || arguments[1] != "submit-frame3d" {
        return None;
    }
    let mut path = None;
    let mut store = None;
    let mut job_id = None;
    let mut load_pattern = None;
    let mut load_combination = None;
    let mut result_id = None;
    let mut report_id = None;
    let mut index = 2;
    while index < arguments.len() {
        let argument = &arguments[index];
        if matches!(
            argument.to_str(),
            Some(
                "--store"
                    | "--job-id"
                    | "--load-pattern"
                    | "--load-combination"
                    | "--result-id"
                    | "--report-id"
            )
        ) {
            let flag = argument.to_str()?;
            let value = arguments.get(index + 1)?.to_str()?;
            if value.starts_with('-') {
                return None;
            }
            match flag {
                "--store" if store.is_none() => store = Some(PathBuf::from(value)),
                "--job-id" if job_id.is_none() => job_id = Some(value.to_owned()),
                "--load-pattern" if load_pattern.is_none() => {
                    load_pattern = Some(value.to_owned());
                }
                "--load-combination" if load_combination.is_none() => {
                    load_combination = Some(value.to_owned());
                }
                "--result-id" if result_id.is_none() => result_id = Some(value.to_owned()),
                "--report-id" if report_id.is_none() => report_id = Some(value.to_owned()),
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
    let load_source = match (load_pattern, load_combination) {
        (Some(id), None) => NativeFrame3dJobLoadSourceV1::Pattern { id },
        (None, Some(id)) => NativeFrame3dJobLoadSourceV1::Combination { id },
        _ => return None,
    };
    Some(JobSubmitOptions {
        path: path?,
        store: store?,
        job_id: job_id?,
        load_source,
        result_id: result_id?,
        report_id: report_id?,
    })
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
    let mut output_dir = None;
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
                    | "--output-dir"
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
                "--output-dir" if output_dir.is_none() => {
                    output_dir = Some(PathBuf::from(value));
                }
                "--output" if output.is_none() => {
                    output = Some(match value {
                        "result-ir" => AnalysisOutput::ResultIr,
                        "report-ir" => AnalysisOutput::ReportIr,
                        "html" => AnalysisOutput::Html,
                        "workbench-bundle" => AnalysisOutput::WorkbenchBundle,
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
    if (output == AnalysisOutput::ResultIr) == report_id.is_some()
        || (output == AnalysisOutput::WorkbenchBundle) != output_dir.is_some()
    {
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
        output_dir,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        parse_analyze_arguments, parse_compare_arguments, parse_validate_arguments,
        AnalysisLoadSource, AnalysisOutput, AnalyzeOptions, ComparisonOutput,
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
                output_dir: None,
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

    #[test]
    fn comparison_arguments_require_two_sources_and_an_explicit_identity() {
        let parsed = parse_compare_arguments(&args(&[
            "result",
            "compare-frame3d",
            "result.json",
            "reference.json",
            "--comparison-id",
            "comparison.LC1",
            "--output",
            "html",
        ]))
        .expect("comparison arguments");
        assert_eq!(parsed.result_path, std::path::PathBuf::from("result.json"));
        assert_eq!(
            parsed.reference_path,
            std::path::PathBuf::from("reference.json")
        );
        assert_eq!(parsed.comparison_id, "comparison.LC1");
        assert_eq!(parsed.output, ComparisonOutput::Html);
        assert!(parse_compare_arguments(&args(&[
            "result",
            "compare-frame3d",
            "result.json",
            "reference.json",
        ]))
        .is_none());
    }
}
