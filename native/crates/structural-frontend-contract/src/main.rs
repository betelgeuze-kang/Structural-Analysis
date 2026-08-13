use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use structural_contracts::model_ir::canonicalize_model_ir_v2;
use structural_frontend_contract::{
    canonical_delivery_receipt_json, canonical_receipt_json, canonical_smoke_receipt_json,
    canonical_viewer_browser_smoke_receipt_json, canonical_viewer_manifest_receipt_json,
    canonical_viewer_performance_probe_receipt_json,
    canonical_viewer_report_pdf_smoke_receipt_json, canonical_viewer_sample_workflow_receipt_json,
    canonical_viewer_server_receipt_json, canonical_viewer_visual_regression_receipt_json,
    canonical_workbench_prototype_browser_smoke_receipt_json,
    canonical_workbench_prototype_receipt_json, canonical_workbench_v2_browser_smoke_receipt_json,
    check_frontend_contract, check_frontend_delivery, check_viewer_manifest,
    check_workbench_prototype, plan_viewer_server, run_frontend_smoke, run_viewer_browser_smoke,
    run_viewer_performance_probe, run_viewer_report_pdf_smoke, run_viewer_sample_workflow,
    run_viewer_visual_regression, run_workbench_prototype_browser_smoke,
    run_workbench_v2_browser_smoke, serve_viewer, FrontendContractError,
    ViewerPerformanceProbeOptions, ViewerReportPdfSmokeOptions, ViewerSampleWorkflowOptions,
    ViewerVisualRegressionOptions,
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
    if command == "browser-smoke" {
        let options = parse_browser_smoke_arguments(&arguments[1..])?;
        let receipt = run_viewer_browser_smoke(&options.root, &options.mode, options.dry_run)?;
        return canonical_viewer_browser_smoke_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "prototype-browser-smoke" {
        let (root, dry_run) = parse_smoke_arguments(&arguments[1..])?;
        let receipt = run_workbench_prototype_browser_smoke(&root, dry_run)?;
        return canonical_workbench_prototype_browser_smoke_receipt_json(&receipt)
            .map_err(Into::into);
    }
    if command == "workbench-v2-browser-smoke" {
        let (root, dry_run) = parse_smoke_arguments(&arguments[1..])?;
        let receipt = run_workbench_v2_browser_smoke(&root, dry_run)?;
        return canonical_workbench_v2_browser_smoke_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "viewer-performance-probe" {
        let options = parse_viewer_performance_probe_arguments(&arguments[1..])?;
        let receipt = run_viewer_performance_probe(&options)?;
        return canonical_viewer_performance_probe_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "viewer-report-pdf-smoke" {
        let options = parse_viewer_report_pdf_smoke_arguments(&arguments[1..])?;
        let receipt = run_viewer_report_pdf_smoke(&options)?;
        return canonical_viewer_report_pdf_smoke_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "viewer-sample-workflow" {
        let options = parse_viewer_sample_workflow_arguments(&arguments[1..])?;
        let receipt = run_viewer_sample_workflow(&options)?;
        return canonical_viewer_sample_workflow_receipt_json(&receipt).map_err(Into::into);
    }
    if command == "viewer-visual-regression" {
        let options = parse_viewer_visual_regression_arguments(&arguments[1..])?;
        let receipt = run_viewer_visual_regression(&options)?;
        return canonical_viewer_visual_regression_receipt_json(&receipt).map_err(Into::into);
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
            "command must be browser-smoke, check, delivery, prototype, prototype-browser-smoke, serve, smoke, viewer-manifest, viewer-performance-probe, viewer-report-pdf-smoke, viewer-sample-workflow, viewer-visual-regression, or workbench-v2-browser-smoke",
        )),
    }
}

fn parse_viewer_sample_workflow_arguments(
    arguments: &[OsString],
) -> Result<ViewerSampleWorkflowOptions, CliError> {
    let mut root = None;
    let mut max_minutes = None;
    let mut output = None;
    let mut dry_run = false;
    let mut keep_temporary_output = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("viewer-sample-workflow option names must be UTF-8"))?;
        if matches!(name, "--dry-run" | "--keep") {
            let flag = if name == "--dry-run" {
                &mut dry_run
            } else {
                &mut keep_temporary_output
            };
            if *flag {
                return Err(usage_error("duplicate options are not allowed"));
            }
            *flag = true;
            index += 1;
            continue;
        }
        let value = arguments
            .get(index + 1)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                usage_error("viewer-sample-workflow value options require one non-empty value")
            })?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--max-minutes" if max_minutes.is_none() => {
                max_minutes = Some(parse_positive_f64(value, "--max-minutes")?);
            }
            "--out" if output.is_none() => output = Some(PathBuf::from(value)),
            "--root" | "--max-minutes" | "--out" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => {
                return Err(usage_error(
                    "viewer-sample-workflow options are missing or unknown",
                ));
            }
        }
        index += 2;
    }
    let mut options = ViewerSampleWorkflowOptions::new(
        root.ok_or_else(|| usage_error("--root must be non-empty"))?,
    );
    options.max_sample_completion_minutes =
        max_minutes.unwrap_or(options.max_sample_completion_minutes);
    options.output = output;
    options.dry_run = dry_run;
    options.keep_temporary_output = keep_temporary_output;
    Ok(options)
}

#[allow(clippy::too_many_lines)] // Keeping the bounded option matrix in one duplicate-aware parser is clearer.
fn parse_viewer_visual_regression_arguments(
    arguments: &[OsString],
) -> Result<ViewerVisualRegressionOptions, CliError> {
    let mut root = None;
    let mut baseline = None;
    let mut case_ids = None;
    let mut timeout_ms = None;
    let mut max_mean_abs_diff = None;
    let mut max_max_abs_diff = None;
    let mut max_coverage_delta = None;
    let mut max_center_delta = None;
    let mut output = None;
    let mut dry_run = false;
    let mut keep_temporary_output = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("viewer-visual-regression option names must be UTF-8"))?;
        if matches!(name, "--dry-run" | "--keep") {
            let flag = if name == "--dry-run" {
                &mut dry_run
            } else {
                &mut keep_temporary_output
            };
            if *flag {
                return Err(usage_error("duplicate options are not allowed"));
            }
            *flag = true;
            index += 1;
            continue;
        }
        let value = arguments
            .get(index + 1)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                usage_error("viewer-visual-regression value options require one non-empty value")
            })?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--baseline" if baseline.is_none() => baseline = Some(PathBuf::from(value)),
            "--case-id" if case_ids.is_none() => {
                case_ids = Some(parse_utf8(value, "--case-id")?);
            }
            "--timeout-ms" if timeout_ms.is_none() => {
                timeout_ms = Some(parse_positive_u64(value, "--timeout-ms")?);
            }
            "--max-mean-abs-diff" if max_mean_abs_diff.is_none() => {
                max_mean_abs_diff = Some(parse_nonnegative_f64(value, "--max-mean-abs-diff")?);
            }
            "--max-max-abs-diff" if max_max_abs_diff.is_none() => {
                max_max_abs_diff = Some(parse_nonnegative_f64(value, "--max-max-abs-diff")?);
            }
            "--max-coverage-delta" if max_coverage_delta.is_none() => {
                max_coverage_delta = Some(parse_nonnegative_f64(value, "--max-coverage-delta")?);
            }
            "--max-center-delta" if max_center_delta.is_none() => {
                max_center_delta = Some(parse_nonnegative_f64(value, "--max-center-delta")?);
            }
            "--out" if output.is_none() => output = Some(PathBuf::from(value)),
            "--root"
            | "--baseline"
            | "--case-id"
            | "--timeout-ms"
            | "--max-mean-abs-diff"
            | "--max-max-abs-diff"
            | "--max-coverage-delta"
            | "--max-center-delta"
            | "--out" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => {
                return Err(usage_error(
                    "viewer-visual-regression options are missing or unknown",
                ));
            }
        }
        index += 2;
    }
    let mut options = ViewerVisualRegressionOptions::new(
        root.ok_or_else(|| usage_error("--root must be non-empty"))?,
    );
    if let Some(value) = baseline {
        options.baseline = value;
    }
    if let Some(value) = case_ids {
        let parsed = value
            .split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
            .collect::<Vec<_>>();
        if parsed.is_empty() {
            return Err(usage_error("--case-id must contain at least one case ID"));
        }
        options.case_ids = parsed;
    }
    options.timeout_ms = timeout_ms.unwrap_or(options.timeout_ms);
    options.max_mean_abs_diff = max_mean_abs_diff.unwrap_or(options.max_mean_abs_diff);
    options.max_max_abs_diff = max_max_abs_diff.unwrap_or(options.max_max_abs_diff);
    options.max_coverage_delta = max_coverage_delta.unwrap_or(options.max_coverage_delta);
    options.max_center_delta = max_center_delta.unwrap_or(options.max_center_delta);
    options.output = output;
    options.dry_run = dry_run;
    options.keep_temporary_output = keep_temporary_output;
    Ok(options)
}

#[derive(Debug, Eq, PartialEq)]
struct ServeOptions {
    root: PathBuf,
    host: String,
    port: u16,
    dry_run: bool,
}

#[derive(Debug, Eq, PartialEq)]
struct BrowserSmokeOptions {
    root: PathBuf,
    mode: String,
    dry_run: bool,
}

fn parse_viewer_performance_probe_arguments(
    arguments: &[OsString],
) -> Result<ViewerPerformanceProbeOptions, CliError> {
    let mut root = None;
    let mut query = None;
    let mut sample_ms = None;
    let mut max_ready_ms = None;
    let mut minimum_average_fps = None;
    let mut viewport_width = None;
    let mut viewport_height = None;
    let mut output = None;
    let mut dry_run = false;
    let mut keep_temporary_output = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("viewer-performance-probe option names must be UTF-8"))?;
        if matches!(name, "--dry-run" | "--keep") {
            let flag = if name == "--dry-run" {
                &mut dry_run
            } else {
                &mut keep_temporary_output
            };
            if *flag {
                return Err(usage_error("duplicate options are not allowed"));
            }
            *flag = true;
            index += 1;
            continue;
        }
        let value = arguments
            .get(index + 1)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                usage_error("viewer-performance-probe value options require one non-empty value")
            })?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--query" if query.is_none() => query = Some(parse_utf8(value, "--query")?),
            "--sample-ms" if sample_ms.is_none() => {
                sample_ms = Some(parse_positive_u64(value, "--sample-ms")?);
            }
            "--max-ready-ms" if max_ready_ms.is_none() => {
                max_ready_ms = Some(parse_positive_u64(value, "--max-ready-ms")?);
            }
            "--min-fps" if minimum_average_fps.is_none() => {
                minimum_average_fps = Some(parse_positive_f64(value, "--min-fps")?);
            }
            "--width" if viewport_width.is_none() => {
                viewport_width = Some(parse_positive_u32(value, "--width")?);
            }
            "--height" if viewport_height.is_none() => {
                viewport_height = Some(parse_positive_u32(value, "--height")?);
            }
            "--out" if output.is_none() => output = Some(PathBuf::from(value)),
            "--root" | "--query" | "--sample-ms" | "--max-ready-ms" | "--min-fps" | "--width"
            | "--height" | "--out" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => {
                return Err(usage_error(
                    "viewer-performance-probe options are missing or unknown",
                ));
            }
        }
        index += 2;
    }
    let mut options = ViewerPerformanceProbeOptions::new(
        root.ok_or_else(|| usage_error("--root must be non-empty"))?,
    );
    options.query = query.unwrap_or(options.query);
    options.sample_ms = sample_ms.unwrap_or(options.sample_ms);
    options.max_ready_ms = max_ready_ms.unwrap_or(options.max_ready_ms);
    options.minimum_average_fps = minimum_average_fps.unwrap_or(options.minimum_average_fps);
    options.viewport_width = viewport_width.unwrap_or(options.viewport_width);
    options.viewport_height = viewport_height.unwrap_or(options.viewport_height);
    options.output = output;
    options.dry_run = dry_run;
    options.keep_temporary_output = keep_temporary_output;
    Ok(options)
}

fn parse_utf8(value: &OsString, name: &str) -> Result<String, CliError> {
    value
        .to_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| usage_error(&format!("{name} must be UTF-8")))
}

fn parse_positive_u64(value: &OsString, name: &str) -> Result<u64, CliError> {
    parse_utf8(value, name)?
        .parse::<u64>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| usage_error(&format!("{name} must be a positive integer")))
}

fn parse_positive_u32(value: &OsString, name: &str) -> Result<u32, CliError> {
    parse_utf8(value, name)?
        .parse::<u32>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| usage_error(&format!("{name} must be a positive integer")))
}

fn parse_positive_f64(value: &OsString, name: &str) -> Result<f64, CliError> {
    parse_utf8(value, name)?
        .parse::<f64>()
        .ok()
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or_else(|| usage_error(&format!("{name} must be a positive finite number")))
}

fn parse_nonnegative_f64(value: &OsString, name: &str) -> Result<f64, CliError> {
    parse_utf8(value, name)?
        .parse::<f64>()
        .ok()
        .filter(|value| value.is_finite() && *value >= 0.0)
        .ok_or_else(|| usage_error(&format!("{name} must be a finite nonnegative number")))
}

fn parse_viewer_report_pdf_smoke_arguments(
    arguments: &[OsString],
) -> Result<ViewerReportPdfSmokeOptions, CliError> {
    let mut root = None;
    let mut query = None;
    let mut minimum_pdf_bytes = None;
    let mut output = None;
    let mut dry_run = false;
    let mut keep_temporary_output = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("viewer-report-pdf-smoke option names must be UTF-8"))?;
        if matches!(name, "--dry-run" | "--keep") {
            let flag = if name == "--dry-run" {
                &mut dry_run
            } else {
                &mut keep_temporary_output
            };
            if *flag {
                return Err(usage_error("duplicate options are not allowed"));
            }
            *flag = true;
            index += 1;
            continue;
        }
        let value = arguments
            .get(index + 1)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                usage_error("viewer-report-pdf-smoke value options require one non-empty value")
            })?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--query" if query.is_none() => {
                query = Some(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("--query must be UTF-8"))?
                        .to_owned(),
                );
            }
            "--min-bytes" if minimum_pdf_bytes.is_none() => {
                minimum_pdf_bytes = Some(
                    value
                        .to_str()
                        .and_then(|value| value.parse::<u64>().ok())
                        .filter(|value| *value > 0)
                        .ok_or_else(|| usage_error("--min-bytes must be a positive integer"))?,
                );
            }
            "--out" if output.is_none() => output = Some(PathBuf::from(value)),
            "--root" | "--query" | "--min-bytes" | "--out" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => {
                return Err(usage_error(
                    "viewer-report-pdf-smoke options are missing or unknown",
                ));
            }
        }
        index += 2;
    }
    let mut options = ViewerReportPdfSmokeOptions::new(
        root.ok_or_else(|| usage_error("--root must be non-empty"))?,
    );
    if let Some(query) = query {
        options.query = query;
    }
    if let Some(minimum_pdf_bytes) = minimum_pdf_bytes {
        options.minimum_pdf_bytes = minimum_pdf_bytes;
    }
    options.output = output;
    options.dry_run = dry_run;
    options.keep_temporary_output = keep_temporary_output;
    Ok(options)
}

fn parse_browser_smoke_arguments(arguments: &[OsString]) -> Result<BrowserSmokeOptions, CliError> {
    let mut root = None;
    let mut mode = None;
    let mut dry_run = false;
    let mut index = 0;
    while index < arguments.len() {
        let name = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("browser-smoke option names must be UTF-8"))?;
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
            .ok_or_else(|| {
                usage_error("browser-smoke value options require one non-empty value")
            })?;
        match name {
            "--root" if root.is_none() => root = Some(PathBuf::from(value)),
            "--mode" if mode.is_none() => {
                mode = Some(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("--mode must be UTF-8"))?
                        .to_owned(),
                );
            }
            "--root" | "--mode" => {
                return Err(usage_error("duplicate options are not allowed"));
            }
            _ => return Err(usage_error("browser-smoke options are missing or unknown")),
        }
        index += 2;
    }
    Ok(BrowserSmokeOptions {
        root: root.ok_or_else(|| usage_error("--root must be non-empty"))?,
        mode: mode.unwrap_or_else(|| "full".to_owned()),
        dry_run,
    })
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
    "usage: structural-frontend-contract check|delivery|prototype|viewer-manifest --root DIR; structural-frontend-contract smoke|prototype-browser-smoke|workbench-v2-browser-smoke --root DIR [--dry-run]; structural-frontend-contract viewer-performance-probe --root DIR [--query QUERY] [--sample-ms N] [--max-ready-ms N] [--min-fps N] [--width N] [--height N] [--out FILE] [--dry-run] [--keep]; structural-frontend-contract viewer-report-pdf-smoke --root DIR [--query QUERY] [--min-bytes N] [--out FILE] [--dry-run] [--keep]; structural-frontend-contract viewer-sample-workflow --root DIR [--max-minutes N] [--out FILE] [--dry-run] [--keep]; structural-frontend-contract viewer-visual-regression --root DIR [--baseline FILE] [--case-id IDS] [--timeout-ms N] [--max-mean-abs-diff N] [--max-max-abs-diff N] [--max-coverage-delta N] [--max-center-delta N] [--out FILE] [--dry-run] [--keep]; structural-frontend-contract browser-smoke --root DIR [--mode minimal|full] [--dry-run]; structural-frontend-contract serve --root DIR [--host 127.0.0.1] [--port PORT] [--dry-run]"
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::path::PathBuf;

    use super::{
        parse_browser_smoke_arguments, parse_serve_arguments, parse_smoke_arguments,
        parse_viewer_performance_probe_arguments, parse_viewer_report_pdf_smoke_arguments,
        parse_viewer_sample_workflow_arguments, parse_viewer_visual_regression_arguments, run,
        BrowserSmokeOptions, ServeOptions,
    };

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
        assert!(parse_browser_smoke_arguments(&[]).is_err());
        assert_eq!(
            parse_browser_smoke_arguments(&[
                OsString::from("--dry-run"),
                OsString::from("--mode"),
                OsString::from("minimal"),
                OsString::from("--root"),
                OsString::from("a"),
            ])
            .expect("valid browser smoke arguments"),
            BrowserSmokeOptions {
                root: PathBuf::from("a"),
                mode: "minimal".to_owned(),
                dry_run: true,
            }
        );
        assert!(parse_browser_smoke_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--mode"),
            OsString::from("full"),
            OsString::from("--mode"),
            OsString::from("minimal"),
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

    #[test]
    fn viewer_report_pdf_parser_accepts_complete_and_rejects_invalid_options() {
        let pdf = parse_viewer_report_pdf_smoke_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--query"),
            OsString::from("project=p&drawing=d&variant=v"),
            OsString::from("--min-bytes"),
            OsString::from("42"),
            OsString::from("--out"),
            OsString::from("report.pdf"),
            OsString::from("--dry-run"),
            OsString::from("--keep"),
        ])
        .expect("valid Viewer report PDF smoke arguments");
        assert_eq!(pdf.root, PathBuf::from("a"));
        assert_eq!(pdf.query, "project=p&drawing=d&variant=v");
        assert_eq!(pdf.minimum_pdf_bytes, 42);
        assert_eq!(pdf.output, Some(PathBuf::from("report.pdf")));
        assert!(pdf.dry_run);
        assert!(pdf.keep_temporary_output);
        assert!(parse_viewer_report_pdf_smoke_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--min-bytes"),
            OsString::from("0"),
        ])
        .is_err());
    }

    #[test]
    fn viewer_performance_parser_accepts_complete_and_rejects_invalid_options() {
        let probe = parse_viewer_performance_probe_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--query"),
            OsString::from("project=p&drawing=d"),
            OsString::from("--sample-ms"),
            OsString::from("250"),
            OsString::from("--max-ready-ms"),
            OsString::from("5000"),
            OsString::from("--min-fps"),
            OsString::from("7.5"),
            OsString::from("--width"),
            OsString::from("800"),
            OsString::from("--height"),
            OsString::from("600"),
            OsString::from("--out"),
            OsString::from("probe.json"),
            OsString::from("--dry-run"),
            OsString::from("--keep"),
        ])
        .expect("valid Viewer performance arguments");
        assert_eq!(probe.root, PathBuf::from("a"));
        assert_eq!(probe.query, "project=p&drawing=d");
        assert_eq!(probe.sample_ms, 250);
        assert_eq!(probe.max_ready_ms, 5_000);
        assert_eq!(probe.minimum_average_fps.to_bits(), 7.5_f64.to_bits());
        assert_eq!(probe.viewport_width, 800);
        assert_eq!(probe.viewport_height, 600);
        assert_eq!(probe.output, Some(PathBuf::from("probe.json")));
        assert!(probe.dry_run);
        assert!(probe.keep_temporary_output);
        assert!(parse_viewer_performance_probe_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--min-fps"),
            OsString::from("NaN"),
        ])
        .is_err());
    }

    #[test]
    fn viewer_sample_workflow_parser_accepts_complete_and_rejects_invalid_options() {
        let workflow = parse_viewer_sample_workflow_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--max-minutes"),
            OsString::from("12.5"),
            OsString::from("--out"),
            OsString::from("workflow.json"),
            OsString::from("--dry-run"),
            OsString::from("--keep"),
        ])
        .expect("valid Viewer sample-workflow arguments");
        assert_eq!(workflow.root, PathBuf::from("a"));
        assert_eq!(
            workflow.max_sample_completion_minutes.to_bits(),
            12.5_f64.to_bits()
        );
        assert_eq!(workflow.output, Some(PathBuf::from("workflow.json")));
        assert!(workflow.dry_run);
        assert!(workflow.keep_temporary_output);
        assert!(parse_viewer_sample_workflow_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--max-minutes"),
            OsString::from("NaN"),
        ])
        .is_err());
        assert!(parse_viewer_sample_workflow_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--root"),
            OsString::from("b"),
        ])
        .is_err());
    }

    #[test]
    fn viewer_visual_regression_parser_accepts_complete_and_rejects_invalid_options() {
        let visual = parse_viewer_visual_regression_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--baseline"),
            OsString::from("baseline.json"),
            OsString::from("--case-id"),
            OsString::from("first, second"),
            OsString::from("--timeout-ms"),
            OsString::from("45000"),
            OsString::from("--max-mean-abs-diff"),
            OsString::from("24"),
            OsString::from("--max-max-abs-diff"),
            OsString::from("120"),
            OsString::from("--max-coverage-delta"),
            OsString::from("0.1"),
            OsString::from("--max-center-delta"),
            OsString::from("0.08"),
            OsString::from("--out"),
            OsString::from("report.json"),
            OsString::from("--dry-run"),
            OsString::from("--keep"),
        ])
        .expect("valid Viewer visual-regression arguments");
        assert_eq!(visual.root, PathBuf::from("a"));
        assert_eq!(visual.baseline, PathBuf::from("baseline.json"));
        assert_eq!(visual.case_ids, vec!["first", "second"]);
        assert_eq!(visual.timeout_ms, 45_000);
        assert_eq!(visual.max_mean_abs_diff.to_bits(), 24.0_f64.to_bits());
        assert_eq!(visual.max_max_abs_diff.to_bits(), 120.0_f64.to_bits());
        assert_eq!(visual.max_coverage_delta.to_bits(), 0.1_f64.to_bits());
        assert_eq!(visual.max_center_delta.to_bits(), 0.08_f64.to_bits());
        assert_eq!(visual.output, Some(PathBuf::from("report.json")));
        assert!(visual.dry_run);
        assert!(visual.keep_temporary_output);
        assert!(parse_viewer_visual_regression_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--case-id"),
            OsString::from(","),
        ])
        .is_err());
        assert!(parse_viewer_visual_regression_arguments(&[
            OsString::from("--root"),
            OsString::from("a"),
            OsString::from("--max-center-delta"),
            OsString::from("NaN"),
        ])
        .is_err());
    }
}
