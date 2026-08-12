use std::ffi::OsString;
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_cli::{
    contract_error_report, execute_external_comparison, execute_model_ir_native_analysis,
    execute_native_analysis, execute_pdf_report, publish_external_comparison,
    publish_model_ir_native_analysis, publish_native_analysis, publish_pdf_report,
    validate_model_bytes, validation_succeeds,
};

mod job_cli;
mod service_cli;

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE_OR_INVALID: u8 = 2;
const MAX_RESULT_IR_BYTES: u64 = 16 * 1024 * 1024;
const MAX_MODEL_IR_BYTES: u64 = 64 * 1024 * 1024;
const MAX_MODEL_ANALYSIS_REQUEST_BYTES: u64 = 4 * 1024 * 1024;
const MAX_CHECKPOINT_BYTES: u64 = 256 * 1024 * 1024;
const MAX_EXTERNAL_RESULT_BYTES: u64 = 1024 * 1024;
const MAX_EXTERNAL_ARTIFACT_BYTES: u64 = 64 * 1024 * 1024;

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
    if let Some(command) = parse_model_analysis_arguments(arguments) {
        return run_model_native_analysis(&command);
    }
    if let Some(command) = parse_analysis_arguments(arguments) {
        return run_native_analysis(&command);
    }
    if let Some(command) = parse_pdf_report_arguments(arguments) {
        return run_pdf_report(&command);
    }
    if let Some(command) = parse_comparison_arguments(arguments) {
        return run_external_comparison(&command);
    }
    if arguments.first().is_some_and(|argument| argument == "job") {
        if let Some(exit) = job_cli::run_job(arguments) {
            return exit;
        }
    }
    if arguments
        .first()
        .is_some_and(|argument| argument == "service")
    {
        if let Some(exit) = service_cli::run_service(arguments) {
            return exit;
        }
    }
    eprintln!(
        "usage:\n  structural-cli model validate <MODEL.json> [--require-analysis-ready]\n  structural-cli analysis model-run <MODEL.json> <MODEL-REQUEST.json> --output-dir <DIR> [--step-budget <N>]\n  structural-cli analysis model-resume <MODEL.json> <MODEL-REQUEST.json> <CHECKPOINT.ndcp> --output-dir <DIR> [--step-budget <N>]\n  structural-cli analysis run <REQUEST.json> --output-dir <DIR> [--step-budget <N>]\n  structural-cli analysis resume <REQUEST.json> <CHECKPOINT.ndcp> --output-dir <DIR> [--step-budget <N>]\n  structural-cli report render-pdf <RESULT-IR.json> <REPORT-IR.json> <REPORT.md> --output-dir <DIR>\n  structural-cli comparison run <RESULT-IR.json> <EXTERNAL-RESULT.json> <SOURCE-ARTIFACT> --output-dir <DIR> [--executable-artifact <FILE>] [--require-pass]\n  structural-cli job submit <REQUEST.json> --store <DIR> --idempotency-key <KEY>\n  structural-cli job poll <JOB_ID> --store <DIR>\n  structural-cli job cancel <JOB_ID> --store <DIR>\n  structural-cli job work-once --store <DIR> --worker-id <ID> [--lease-ms <N>] [--step-budget <N>]\n  structural-cli job recover --store <DIR>\n  structural-cli job export <JOB_ID> --store <DIR> --output-dir <DIR>\n  structural-cli service serve --listen <LOOPBACK:PORT> --store <DIR> --client-token-file <FILE> --worker-token-file <FILE> [--ready-file <FILE>] [--max-requests <N>]"
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelAnalysisCommand {
    model_path: PathBuf,
    request_path: PathBuf,
    checkpoint_path: Option<PathBuf>,
    output_directory: PathBuf,
    step_budget: u32,
}

fn run_model_native_analysis(command: &ModelAnalysisCommand) -> ExitCode {
    let Ok(model_bytes) = read_bounded_regular_file(&command.model_path, MAX_MODEL_IR_BYTES) else {
        return model_analysis_input_failure("model_read_error", "/model");
    };
    let Ok(request_bytes) =
        read_bounded_regular_file(&command.request_path, MAX_MODEL_ANALYSIS_REQUEST_BYTES)
    else {
        return model_analysis_input_failure("request_read_error", "/request");
    };
    let checkpoint_bytes = if let Some(path) = command.checkpoint_path.as_ref() {
        let Ok(bytes) = read_bounded_regular_file(path, MAX_CHECKPOINT_BYTES) else {
            return model_analysis_input_failure("checkpoint_read_error", "/checkpoint");
        };
        Some(bytes)
    } else {
        None
    };
    let outcome = match execute_model_ir_native_analysis(
        &model_bytes,
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
                    "schema_version": "structural-model-ir-ndtha-analysis-failure.v1",
                    "code": "model_ir_ndtha_analysis_failed",
                    "detail": error.to_string()
                })
            );
            return ExitCode::from(exit);
        }
    };
    if let Err(error) = publish_model_ir_native_analysis(&command.output_directory, &outcome) {
        println!(
            "{}",
            json!({
                "schema_version": "structural-model-ir-ndtha-analysis-failure.v1",
                "code": "model_ir_ndtha_publish_failed",
                "detail": error.to_string()
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    }
    println!("{}", outcome.run_receipt_json());
    ExitCode::SUCCESS
}

fn model_analysis_input_failure(code: &str, path: &str) -> ExitCode {
    println!(
        "{}",
        json!({
            "schema_version": "structural-model-ir-ndtha-analysis-failure.v1",
            "code": code,
            "path": path,
            "detail": "ModelIR analysis input could not be read"
        })
    );
    ExitCode::from(EXIT_FAILURE)
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct PdfReportCommand {
    result_ir_path: PathBuf,
    report_ir_path: PathBuf,
    document_source_path: PathBuf,
    output_directory: PathBuf,
}

fn run_pdf_report(command: &PdfReportCommand) -> ExitCode {
    let result_ir = match read_bounded_regular_file(&command.result_ir_path, MAX_RESULT_IR_BYTES) {
        Ok(bytes) => bytes,
        Err(detail) => return pdf_input_failure("result_ir_read_error", "/result_ir", &detail),
    };
    let report_ir = match read_bounded_regular_file(&command.report_ir_path, MAX_RESULT_IR_BYTES) {
        Ok(bytes) => bytes,
        Err(detail) => return pdf_input_failure("report_ir_read_error", "/report_ir", &detail),
    };
    let document_source =
        match read_bounded_regular_file(&command.document_source_path, MAX_RESULT_IR_BYTES) {
            Ok(bytes) => bytes,
            Err(detail) => {
                return pdf_input_failure(
                    "document_source_read_error",
                    "/document_source",
                    &detail,
                );
            }
        };
    let outcome = match execute_pdf_report(&result_ir, &report_ir, &document_source) {
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
                    "schema_version": "structural-native-pdf-report-failure.v1",
                    "code": "pdf_report_failed",
                    "detail": error.to_string()
                })
            );
            return ExitCode::from(exit);
        }
    };
    if let Err(error) = publish_pdf_report(&command.output_directory, &outcome) {
        println!(
            "{}",
            json!({
                "schema_version": "structural-native-pdf-report-failure.v1",
                "code": "pdf_report_publish_failed",
                "detail": error.to_string()
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    }
    println!("{}", outcome.receipt_json());
    ExitCode::SUCCESS
}

fn pdf_input_failure(code: &str, path: &str, detail: &str) -> ExitCode {
    println!(
        "{}",
        json!({
            "schema_version": "structural-native-pdf-report-failure.v1",
            "code": code,
            "path": path,
            "detail": detail
        })
    );
    ExitCode::from(EXIT_FAILURE)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ComparisonCommand {
    result_ir_path: PathBuf,
    external_result_path: PathBuf,
    source_artifact_path: PathBuf,
    executable_artifact_path: Option<PathBuf>,
    output_directory: PathBuf,
    require_pass: bool,
}

fn run_external_comparison(command: &ComparisonCommand) -> ExitCode {
    let result_ir = match read_bounded_regular_file(&command.result_ir_path, MAX_RESULT_IR_BYTES) {
        Ok(bytes) => bytes,
        Err(detail) => {
            return comparison_input_failure("result_ir_read_error", "/result_ir", &detail)
        }
    };
    let external_result =
        match read_bounded_regular_file(&command.external_result_path, MAX_EXTERNAL_RESULT_BYTES) {
            Ok(bytes) => bytes,
            Err(detail) => {
                return comparison_input_failure(
                    "external_result_read_error",
                    "/external_result",
                    &detail,
                );
            }
        };
    let source_artifact =
        match read_bounded_regular_file(&command.source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)
        {
            Ok(bytes) => bytes,
            Err(detail) => {
                return comparison_input_failure(
                    "source_artifact_read_error",
                    "/source_artifact",
                    &detail,
                );
            }
        };
    let executable_artifact = if let Some(path) = command.executable_artifact_path.as_ref() {
        match read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES) {
            Ok(bytes) => Some(bytes),
            Err(detail) => {
                return comparison_input_failure(
                    "executable_artifact_read_error",
                    "/executable_artifact",
                    &detail,
                );
            }
        }
    } else {
        None
    };
    let outcome = match execute_external_comparison(
        &result_ir,
        &external_result,
        &source_artifact,
        executable_artifact.as_deref(),
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
                    "schema_version": "structural-native-external-comparison-failure.v1",
                    "code": "external_comparison_failed",
                    "detail": error.to_string()
                })
            );
            return ExitCode::from(exit);
        }
    };
    if let Err(error) = publish_external_comparison(&command.output_directory, &outcome) {
        println!(
            "{}",
            json!({
                "schema_version": "structural-native-external-comparison-failure.v1",
                "code": "external_comparison_publish_failed",
                "detail": error.to_string()
            })
        );
        return ExitCode::from(EXIT_FAILURE);
    }
    println!("{}", outcome.receipt_json());
    if command.require_pass && !outcome.passed() {
        ExitCode::from(EXIT_USAGE_OR_INVALID)
    } else {
        ExitCode::SUCCESS
    }
}

fn comparison_input_failure(code: &str, path: &str, detail: &str) -> ExitCode {
    println!(
        "{}",
        json!({
            "schema_version": "structural-native-external-comparison-failure.v1",
            "code": code,
            "path": path,
            "detail": detail
        })
    );
    ExitCode::from(EXIT_FAILURE)
}

fn read_bounded_regular_file(path: &PathBuf, maximum_bytes: u64) -> Result<Vec<u8>, String> {
    let path_metadata = std::fs::symlink_metadata(path)
        .map_err(|_| "input artifact metadata could not be read".to_owned())?;
    if path_metadata.file_type().is_symlink() || !path_metadata.file_type().is_file() {
        return Err("input artifact must be a regular non-symlink file".to_owned());
    }
    if path_metadata.len() > maximum_bytes {
        return Err("input artifact exceeds its bounded byte limit".to_owned());
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file: File = options
        .open(path)
        .map_err(|_| "input artifact could not be opened without following symlinks".to_owned())?;
    let opened_metadata = file
        .metadata()
        .map_err(|_| "opened input artifact metadata could not be read".to_owned())?;
    if !opened_metadata.is_file() || opened_metadata.len() > maximum_bytes {
        return Err("opened input artifact is not a bounded regular file".to_owned());
    }
    let mut bytes = Vec::with_capacity(
        usize::try_from(opened_metadata.len().min(maximum_bytes))
            .map_err(|_| "input artifact length does not fit memory bounds".to_owned())?,
    );
    file.take(maximum_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|_| "input artifact could not be read".to_owned())?;
    if u64::try_from(bytes.len()).map_or(true, |length| length > maximum_bytes) {
        return Err("input artifact changed beyond its bounded byte limit".to_owned());
    }
    Ok(bytes)
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

fn parse_pdf_report_arguments(arguments: &[OsString]) -> Option<PdfReportCommand> {
    if arguments.len() != 7 || arguments[0] != "report" || arguments[1] != "render-pdf" {
        return None;
    }
    if [&arguments[2], &arguments[3], &arguments[4], &arguments[6]]
        .iter()
        .any(|value| value.to_string_lossy().starts_with('-'))
        || arguments[5] != "--output-dir"
    {
        return None;
    }
    Some(PdfReportCommand {
        result_ir_path: PathBuf::from(&arguments[2]),
        report_ir_path: PathBuf::from(&arguments[3]),
        document_source_path: PathBuf::from(&arguments[4]),
        output_directory: PathBuf::from(&arguments[6]),
    })
}

fn parse_comparison_arguments(arguments: &[OsString]) -> Option<ComparisonCommand> {
    if arguments.len() < 7 || arguments[0] != "comparison" || arguments[1] != "run" {
        return None;
    }
    let positional = [&arguments[2], &arguments[3], &arguments[4]];
    if positional
        .iter()
        .any(|value| value.to_string_lossy().starts_with('-'))
    {
        return None;
    }
    let mut output_directory = None;
    let mut executable_artifact_path = None;
    let mut require_pass = false;
    let mut index = 5;
    while index < arguments.len() {
        if arguments[index] == "--output-dir" && output_directory.is_none() {
            index += 1;
            if index >= arguments.len() || arguments[index].to_string_lossy().starts_with('-') {
                return None;
            }
            output_directory = Some(PathBuf::from(&arguments[index]));
        } else if arguments[index] == "--executable-artifact" && executable_artifact_path.is_none()
        {
            index += 1;
            if index >= arguments.len() || arguments[index].to_string_lossy().starts_with('-') {
                return None;
            }
            executable_artifact_path = Some(PathBuf::from(&arguments[index]));
        } else if arguments[index] == "--require-pass" && !require_pass {
            require_pass = true;
        } else {
            return None;
        }
        index += 1;
    }
    Some(ComparisonCommand {
        result_ir_path: PathBuf::from(&arguments[2]),
        external_result_path: PathBuf::from(&arguments[3]),
        source_artifact_path: PathBuf::from(&arguments[4]),
        executable_artifact_path,
        output_directory: output_directory?,
        require_pass,
    })
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

fn parse_model_analysis_arguments(arguments: &[OsString]) -> Option<ModelAnalysisCommand> {
    if arguments.len() < 6 || arguments[0] != "analysis" {
        return None;
    }
    let (positional_count, checkpoint_index) = if arguments[1] == "model-run" {
        (2_usize, None)
    } else if arguments[1] == "model-resume" {
        (3_usize, Some(4_usize))
    } else {
        return None;
    };
    let flag_start = 2 + positional_count;
    if arguments.len() < flag_start + 2
        || arguments[2..flag_start]
            .iter()
            .any(|value| value.to_string_lossy().starts_with('-'))
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
    Some(ModelAnalysisCommand {
        model_path: PathBuf::from(&arguments[2]),
        request_path: PathBuf::from(&arguments[3]),
        checkpoint_path: checkpoint_index.map(|position| PathBuf::from(&arguments[position])),
        output_directory: output_directory?,
        step_budget,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        parse_analysis_arguments, parse_comparison_arguments, parse_model_analysis_arguments,
        parse_pdf_report_arguments, parse_validate_arguments, AnalysisCommand, ComparisonCommand,
        ModelAnalysisCommand, PdfReportCommand,
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

    #[test]
    fn model_analysis_arguments_require_model_request_and_bound_checkpoint() {
        assert_eq!(
            parse_model_analysis_arguments(&args(&[
                "analysis",
                "model-run",
                "model.json",
                "adapter.json",
                "--output-dir",
                "out",
                "--step-budget",
                "2"
            ])),
            Some(ModelAnalysisCommand {
                model_path: "model.json".into(),
                request_path: "adapter.json".into(),
                checkpoint_path: None,
                output_directory: "out".into(),
                step_budget: 2,
            })
        );
        assert_eq!(
            parse_model_analysis_arguments(&args(&[
                "analysis",
                "model-resume",
                "model.json",
                "adapter.json",
                "checkpoint.ndcp",
                "--output-dir",
                "out"
            ])),
            Some(ModelAnalysisCommand {
                model_path: "model.json".into(),
                request_path: "adapter.json".into(),
                checkpoint_path: Some("checkpoint.ndcp".into()),
                output_directory: "out".into(),
                step_budget: u32::MAX,
            })
        );
        assert!(parse_model_analysis_arguments(&args(&[
            "analysis",
            "model-run",
            "model.json",
            "adapter.json",
            "--output-dir",
            "out",
            "--step-budget",
            "0"
        ]))
        .is_none());
    }

    #[test]
    fn comparison_arguments_require_all_explicit_artifact_paths() {
        assert_eq!(
            parse_comparison_arguments(&args(&[
                "comparison",
                "run",
                "result.json",
                "external.json",
                "source.out",
                "--output-dir",
                "comparison",
                "--require-pass",
                "--executable-artifact",
                "solver.bin"
            ])),
            Some(ComparisonCommand {
                result_ir_path: "result.json".into(),
                external_result_path: "external.json".into(),
                source_artifact_path: "source.out".into(),
                executable_artifact_path: Some("solver.bin".into()),
                output_directory: "comparison".into(),
                require_pass: true,
            })
        );
        assert!(parse_comparison_arguments(&args(&[
            "comparison",
            "run",
            "result.json",
            "external.json",
            "source.out",
            "--require-pass"
        ]))
        .is_none());
        assert!(parse_comparison_arguments(&args(&[
            "comparison",
            "run",
            "result.json",
            "external.json",
            "source.out",
            "--output-dir",
            "a",
            "--output-dir",
            "b"
        ]))
        .is_none());
    }

    #[test]
    fn pdf_report_arguments_have_no_implicit_input_or_output() {
        assert_eq!(
            parse_pdf_report_arguments(&args(&[
                "report",
                "render-pdf",
                "result.json",
                "report.json",
                "report.md",
                "--output-dir",
                "pdf"
            ])),
            Some(PdfReportCommand {
                result_ir_path: "result.json".into(),
                report_ir_path: "report.json".into(),
                document_source_path: "report.md".into(),
                output_directory: "pdf".into(),
            })
        );
        assert!(parse_pdf_report_arguments(&args(&[
            "report",
            "render-pdf",
            "result.json",
            "report.json",
            "report.md",
            "pdf"
        ]))
        .is_none());
    }
}
