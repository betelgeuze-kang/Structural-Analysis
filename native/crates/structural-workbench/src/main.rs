use std::ffi::{OsStr, OsString};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde_json::json;
use structural_workbench::{
    browse_embedded_benchmark_catalog, browse_evidence_bundle, show_embedded_benchmark_case,
    show_evidence_artifact, BenchmarkCatalogFilterV1, BenchmarkLifecycleV1, BenchmarkSizeClassV1,
    BenchmarkTruthClassV1, ModelTopologyProjectionV1, NativeWorkbench, WorkbenchError,
    WorkbenchReportLocaleV1, WorkbenchReviewDecisionV1, WorkbenchStageV1,
};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE_OR_POLICY: u8 = 2;

#[derive(Clone, Debug, Eq, PartialEq)]
struct ImportCommand {
    model: PathBuf,
    mgt_model_id: Option<String>,
    request: PathBuf,
    external_result: PathBuf,
    source_artifact: PathBuf,
    executable_artifact: Option<PathBuf>,
    workspace: PathBuf,
    step_budget: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ReviewCommand {
    workspace: PathBuf,
    decision: WorkbenchReviewDecisionV1,
    reviewer: String,
    comment: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EvidenceCommand {
    bundle: PathBuf,
    artifact_id: Option<String>,
    as_of_unix_seconds: Option<i64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelViewCommand {
    model: PathBuf,
    projection: ModelTopologyProjectionV1,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditNodeCommand {
    model: PathBuf,
    node_id: String,
    coordinates_m: [f64; 3],
    output_directory: PathBuf,
}

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    run(&arguments)
}

fn run(arguments: &[OsString]) -> ExitCode {
    if arguments.len() == 1 && arguments[0] == "--version" {
        println!("structural-workbench {}", env!("CARGO_PKG_VERSION"));
        return ExitCode::SUCCESS;
    }
    let result = match arguments.first().and_then(|argument| argument.to_str()) {
        Some("import") => {
            parse_import(arguments, false, false).and_then(|command| run_import(&command))
        }
        Some("import-mgt") => {
            parse_import(arguments, false, true).and_then(|command| run_import(&command))
        }
        Some("workflow") => {
            parse_import(arguments, true, false).and_then(|command| run_workflow(&command))
        }
        Some("workflow-mgt") => {
            parse_import(arguments, true, true).and_then(|command| run_workflow(&command))
        }
        Some("model-view") => {
            parse_model_view(arguments).and_then(|command| run_model_view(&command))
        }
        Some("model-edit-node") => {
            parse_model_edit_node(arguments).and_then(|command| run_model_edit_node(&command))
        }
        Some("status") => {
            parse_workspace_only(arguments).and_then(|workspace| run_status(&workspace))
        }
        Some("inspect") => {
            parse_workspace_only(arguments).and_then(|workspace| run_inspect(&workspace))
        }
        Some("validate") => parse_workspace_only(arguments).and_then(|workspace| {
            let mut workbench = NativeWorkbench::open(&workspace)?;
            workbench.validate()?;
            print_session(&workbench)
        }),
        Some("run") => {
            parse_stage_command(arguments, "--step-budget", 1).and_then(|(workspace, budget, _)| {
                let mut workbench = NativeWorkbench::open(&workspace)?;
                workbench.run(budget)?;
                print_session(&workbench)
            })
        }
        Some("resume") => {
            parse_stage_command(arguments, "--step-budget", 0).and_then(|(workspace, budget, _)| {
                let mut workbench = NativeWorkbench::open(&workspace)?;
                workbench.resume(budget)?;
                print_session(&workbench)
            })
        }
        Some("compare") => parse_stage_command(arguments, "--unused", 0).and_then(
            |(workspace, _, require_pass)| {
                let mut workbench = NativeWorkbench::open(&workspace)?;
                workbench.compare(require_pass)?;
                print_session(&workbench)
            },
        ),
        Some("report") => parse_workspace_only(arguments).and_then(|workspace| {
            let mut workbench = NativeWorkbench::open(&workspace)?;
            workbench.report()?;
            print_session(&workbench)
        }),
        Some("report-view") => parse_report_view(arguments).and_then(|(workspace, locale)| {
            let workbench = NativeWorkbench::open(&workspace)?;
            print!("{}", workbench.linear_report_text(locale)?);
            Ok(())
        }),
        Some("report-export-pdf") => {
            parse_report_pdf_export(arguments).and_then(|(workspace, output_directory, locale)| {
                let workbench = NativeWorkbench::open(&workspace)?;
                println!(
                    "{}",
                    workbench.export_localized_pdf(locale, &output_directory)?
                );
                Ok(())
            })
        }
        Some("review") => parse_review(arguments).and_then(|command| run_review(&command)),
        Some("review-show") => {
            parse_workspace_only(arguments).and_then(|workspace| run_review_show(&workspace))
        }
        Some("export") => {
            parse_workspace_only(arguments).and_then(|workspace| run_export(&workspace))
        }
        Some("catalog") => parse_catalog(arguments).and_then(|filter| run_catalog(&filter)),
        Some("catalog-show") => {
            parse_catalog_show(arguments).and_then(|case_id| run_catalog_show(&case_id))
        }
        Some("evidence") => {
            parse_evidence(arguments, false).and_then(|command| run_evidence(&command))
        }
        Some("evidence-show") => {
            parse_evidence(arguments, true).and_then(|command| run_evidence_show(&command))
        }
        Some("interactive") => {
            parse_workspace_only(arguments).and_then(|workspace| run_interactive(&workspace))
        }
        _ => Err(usage_error("unknown or incomplete Workbench command")),
    };
    finish(result)
}

fn finish(result: Result<(), WorkbenchError>) -> ExitCode {
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            println!(
                "{}",
                json!({
                    "schema_version": "structural-native-workbench-failure.v1",
                    "code": error.code,
                    "detail": error.detail,
                })
            );
            let exit = if matches!(
                error.code,
                "workbench_usage_error"
                    | "workbench_transition_invalid"
                    | "workbench_comparison_diverged"
                    | "workbench_catalog_case_id_invalid"
                    | "workbench_catalog_case_not_found"
                    | "workbench_catalog_filter_invalid"
                    | "workbench_evidence_artifact_id_invalid"
                    | "workbench_evidence_artifact_not_found"
                    | "workbench_evidence_as_of_invalid"
            ) {
                EXIT_USAGE_OR_POLICY
            } else {
                EXIT_FAILURE
            };
            if error.code == "workbench_usage_error" {
                eprintln!("{}", usage());
            }
            ExitCode::from(exit)
        }
    }
}

fn run_import(command: &ImportCommand) -> Result<(), WorkbenchError> {
    let workbench = initialize(command)?;
    print_session(&workbench)
}

fn run_workflow(command: &ImportCommand) -> Result<(), WorkbenchError> {
    let mut workbench = initialize(command)?;
    workbench.validate()?;
    workbench.run(command.step_budget)?;
    workbench.resume(0)?;
    workbench.compare(true)?;
    workbench.report()?;
    print_session(&workbench)
}

fn initialize(command: &ImportCommand) -> Result<NativeWorkbench, WorkbenchError> {
    if let Some(model_id) = command.mgt_model_id.as_deref() {
        NativeWorkbench::initialize_from_mgt_paths(
            &command.workspace,
            &command.model,
            model_id,
            &command.request,
            &command.external_result,
            &command.source_artifact,
            command.executable_artifact.as_deref(),
        )
    } else {
        NativeWorkbench::initialize_from_paths(
            &command.workspace,
            &command.model,
            &command.request,
            &command.external_result,
            &command.source_artifact,
            command.executable_artifact.as_deref(),
        )
    }
}

fn run_status(workspace: &Path) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(workspace)?;
    print_session(&workbench)
}

fn run_model_view(command: &ModelViewCommand) -> Result<(), WorkbenchError> {
    print!(
        "{}",
        structural_workbench::render_model_topology_view_file(&command.model, command.projection)?
    );
    Ok(())
}

fn run_model_edit_node(command: &ModelEditNodeCommand) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_node_coordinate_edit(
        &command.model,
        &command.node_id,
        command.coordinates_m,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_inspect(workspace: &Path) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(workspace)?;
    println!("{}", workbench.inspect_json()?);
    Ok(())
}

fn run_review(command: &ReviewCommand) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(&command.workspace)?;
    println!(
        "{}",
        workbench.publish_review(command.decision, &command.reviewer, &command.comment,)?
    );
    Ok(())
}

fn run_review_show(workspace: &Path) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(workspace)?;
    println!("{}", workbench.review_json()?);
    Ok(())
}

fn run_export(workspace: &Path) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(workspace)?;
    println!("{}", workbench.export_json()?);
    Ok(())
}

fn run_catalog(filter: &BenchmarkCatalogFilterV1) -> Result<(), WorkbenchError> {
    println!("{}", browse_embedded_benchmark_catalog(filter)?);
    Ok(())
}

fn run_catalog_show(case_id: &str) -> Result<(), WorkbenchError> {
    println!("{}", show_embedded_benchmark_case(case_id)?);
    Ok(())
}

fn run_evidence(command: &EvidenceCommand) -> Result<(), WorkbenchError> {
    println!(
        "{}",
        browse_evidence_bundle(&command.bundle, command.as_of_unix_seconds)?
    );
    Ok(())
}

fn run_evidence_show(command: &EvidenceCommand) -> Result<(), WorkbenchError> {
    println!(
        "{}",
        show_evidence_artifact(
            &command.bundle,
            command
                .artifact_id
                .as_deref()
                .expect("show parser requires an artifact ID"),
            command.as_of_unix_seconds,
        )?
    );
    Ok(())
}

fn run_interactive(workspace: &Path) -> Result<(), WorkbenchError> {
    let mut workbench = NativeWorkbench::open(workspace)?;
    loop {
        println!(
            "Structural Native Workbench — durable stage: {}",
            workbench.session().stage().label()
        );
        let action = match workbench.session().stage() {
            WorkbenchStageV1::Imported => "Validate",
            WorkbenchStageV1::Validated => "Run to checkpoint",
            WorkbenchStageV1::Checkpointed => "Resume to terminal result",
            WorkbenchStageV1::Terminal => "Compare external result",
            WorkbenchStageV1::Compared => "Render native PDF report",
            WorkbenchStageV1::Reported => {
                print_session(&workbench)?;
                return Ok(());
            }
        };
        print!("Press Enter to {action}, or q to quit: ");
        io::stdout().flush().map_err(|error| WorkbenchError {
            code: "workbench_terminal_io_error",
            detail: error.to_string(),
        })?;
        let mut input = String::new();
        io::stdin()
            .read_line(&mut input)
            .map_err(|error| WorkbenchError {
                code: "workbench_terminal_io_error",
                detail: error.to_string(),
            })?;
        if input.trim().eq_ignore_ascii_case("q") {
            return print_session(&workbench);
        }
        match workbench.session().stage() {
            WorkbenchStageV1::Imported => workbench.validate()?,
            WorkbenchStageV1::Validated => workbench.run(1)?,
            WorkbenchStageV1::Checkpointed => workbench.resume(0)?,
            WorkbenchStageV1::Terminal => workbench.compare(true)?,
            WorkbenchStageV1::Compared => workbench.report()?,
            WorkbenchStageV1::Reported => unreachable!("reported returns above"),
        }
    }
}

fn print_session(workbench: &NativeWorkbench) -> Result<(), WorkbenchError> {
    println!("{}", workbench.session_json()?);
    Ok(())
}

fn parse_import(
    arguments: &[OsString],
    workflow: bool,
    mgt: bool,
) -> Result<ImportCommand, WorkbenchError> {
    if arguments.len() < 3 {
        return Err(usage_error(
            "import/workflow requires MODEL and MODEL-REQUEST",
        ));
    }
    let model = PathBuf::from(&arguments[1]);
    let request = PathBuf::from(&arguments[2]);
    let mut external_result = None;
    let mut source_artifact = None;
    let mut executable_artifact = None;
    let mut workspace = None;
    let mut mgt_model_id = None;
    let mut step_budget = 1_u32;
    let mut step_budget_seen = false;
    let mut index = 3;
    while index < arguments.len() {
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("Workbench option names must be valid UTF-8"))?;
        if index + 1 >= arguments.len() {
            return Err(usage_error("Workbench option has no value"));
        }
        let value = &arguments[index + 1];
        match flag {
            "--external-result" if external_result.is_none() => {
                external_result = Some(PathBuf::from(value));
            }
            "--source-artifact" if source_artifact.is_none() => {
                source_artifact = Some(PathBuf::from(value));
            }
            "--executable-artifact" if executable_artifact.is_none() => {
                executable_artifact = Some(PathBuf::from(value));
            }
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--model-id" if mgt && mgt_model_id.is_none() => {
                let value = value
                    .to_str()
                    .filter(|text| !text.is_empty())
                    .ok_or_else(|| usage_error("MGT model ID must be non-empty UTF-8"))?;
                mgt_model_id = Some(value.to_owned());
            }
            "--step-budget" if workflow && !step_budget_seen => {
                step_budget = parse_u32(value, "step budget")?;
                step_budget_seen = true;
            }
            _ => return Err(usage_error("duplicate or unknown import/workflow option")),
        }
        index += 2;
    }
    Ok(ImportCommand {
        model,
        mgt_model_id: if mgt {
            Some(mgt_model_id.ok_or_else(|| usage_error("--model-id is required for MGT"))?)
        } else {
            None
        },
        request,
        external_result: external_result
            .ok_or_else(|| usage_error("--external-result is required"))?,
        source_artifact: source_artifact
            .ok_or_else(|| usage_error("--source-artifact is required"))?,
        executable_artifact,
        workspace: workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        step_budget,
    })
}

fn parse_workspace_only(arguments: &[OsString]) -> Result<PathBuf, WorkbenchError> {
    if arguments.len() == 3 && arguments[1] == "--workspace" {
        Ok(PathBuf::from(&arguments[2]))
    } else {
        Err(usage_error("command requires exactly --workspace DIR"))
    }
}

fn parse_model_view(arguments: &[OsString]) -> Result<ModelViewCommand, WorkbenchError> {
    if arguments.len() != 2 && arguments.len() != 4 {
        return Err(usage_error(
            "model-view requires MODEL.json and optional --projection isometric|xy|xz|yz",
        ));
    }
    let mut projection = ModelTopologyProjectionV1::Isometric;
    if arguments.len() == 4 {
        if arguments[2] != "--projection" {
            return Err(usage_error("model-view accepts only --projection"));
        }
        projection = arguments[3]
            .to_str()
            .and_then(ModelTopologyProjectionV1::parse)
            .ok_or_else(|| usage_error("model-view projection must be isometric, xy, xz or yz"))?;
    }
    Ok(ModelViewCommand {
        model: PathBuf::from(&arguments[1]),
        projection,
    })
}

fn parse_model_edit_node(arguments: &[OsString]) -> Result<ModelEditNodeCommand, WorkbenchError> {
    if arguments.len() != 10
        || arguments[2] != "--node"
        || arguments[4] != "--coordinates"
        || arguments[8] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-node requires MODEL.json --node ID --coordinates X Y Z --output-dir DIR",
        ));
    }
    let node_id = arguments[3]
        .to_str()
        .filter(|value| !value.is_empty() && value.len() <= 128)
        .ok_or_else(|| usage_error("model-edit-node ID must be valid UTF-8 with 1-128 bytes"))?
        .to_owned();
    let mut coordinates_m = [0.0; 3];
    for (target, source) in coordinates_m.iter_mut().zip(&arguments[5..8]) {
        *target = source
            .to_str()
            .and_then(|value| value.parse::<f64>().ok())
            .filter(|value| value.is_finite())
            .ok_or_else(|| usage_error("model-edit-node coordinates must be finite SI numbers"))?;
    }
    Ok(ModelEditNodeCommand {
        model: PathBuf::from(&arguments[1]),
        node_id,
        coordinates_m,
        output_directory: PathBuf::from(&arguments[9]),
    })
}

fn parse_report_view(
    arguments: &[OsString],
) -> Result<(PathBuf, WorkbenchReportLocaleV1), WorkbenchError> {
    let mut workspace = None;
    let mut locale = WorkbenchReportLocaleV1::EnUs;
    let mut locale_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("report-view option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("report-view option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--locale" if !locale_seen => {
                locale_seen = true;
                locale = value
                    .to_str()
                    .and_then(WorkbenchReportLocaleV1::parse)
                    .ok_or_else(|| usage_error("report-view locale must be en-US or ko-KR"))?;
            }
            _ => return Err(usage_error("duplicate or unknown report-view option")),
        }
        index += 2;
    }
    Ok((
        workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        locale,
    ))
}

fn parse_report_pdf_export(
    arguments: &[OsString],
) -> Result<(PathBuf, PathBuf, WorkbenchReportLocaleV1), WorkbenchError> {
    let mut workspace = None;
    let mut output_directory = None;
    let mut locale = WorkbenchReportLocaleV1::EnUs;
    let mut locale_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("report-export-pdf option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("report-export-pdf option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--output-dir" if output_directory.is_none() => {
                output_directory = Some(PathBuf::from(value));
            }
            "--locale" if !locale_seen => {
                locale_seen = true;
                locale = value
                    .to_str()
                    .and_then(WorkbenchReportLocaleV1::parse)
                    .ok_or_else(|| {
                        usage_error("report-export-pdf locale must be en-US or ko-KR")
                    })?;
            }
            _ => return Err(usage_error("duplicate or unknown report-export-pdf option")),
        }
        index += 2;
    }
    Ok((
        workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        output_directory.ok_or_else(|| usage_error("--output-dir is required"))?,
        locale,
    ))
}

fn parse_stage_command(
    arguments: &[OsString],
    budget_flag: &str,
    default_budget: u32,
) -> Result<(PathBuf, u32, bool), WorkbenchError> {
    let mut workspace = None;
    let mut budget = default_budget;
    let mut budget_seen = false;
    let mut require_pass = false;
    let mut index = 1;
    while index < arguments.len() {
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("Workbench option names must be valid UTF-8"))?;
        if flag == "--require-pass" && budget_flag == "--unused" && !require_pass {
            require_pass = true;
            index += 1;
            continue;
        }
        if index + 1 >= arguments.len() {
            return Err(usage_error("Workbench option has no value"));
        }
        let value = &arguments[index + 1];
        if flag == "--workspace" && workspace.is_none() {
            workspace = Some(PathBuf::from(value));
        } else if flag == budget_flag && budget_flag != "--unused" && !budget_seen {
            budget = parse_u32(value, "step budget")?;
            budget_seen = true;
        } else {
            return Err(usage_error("duplicate or unknown stage option"));
        }
        index += 2;
    }
    Ok((
        workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        budget,
        require_pass,
    ))
}

fn parse_u32(value: &OsStr, label: &str) -> Result<u32, WorkbenchError> {
    value
        .to_str()
        .and_then(|text| text.parse::<u32>().ok())
        .ok_or_else(|| usage_error(&format!("{label} must be an unsigned 32-bit integer")))
}

fn parse_review(arguments: &[OsString]) -> Result<ReviewCommand, WorkbenchError> {
    let mut workspace = None;
    let mut decision = None;
    let mut reviewer = None;
    let mut comment = None;
    let mut index = 1;
    while index < arguments.len() {
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("review option names must be valid UTF-8"))?;
        if index + 1 >= arguments.len() {
            return Err(usage_error("review option has no value"));
        }
        let value = &arguments[index + 1];
        match flag {
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--decision" if decision.is_none() => {
                let parsed = value
                    .to_str()
                    .and_then(WorkbenchReviewDecisionV1::parse)
                    .ok_or_else(|| usage_error("review decision must be pass, review or fail"))?;
                decision = Some(parsed);
            }
            "--reviewer" if reviewer.is_none() => {
                reviewer = Some(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("reviewer must be valid UTF-8"))?
                        .to_owned(),
                );
            }
            "--comment" if comment.is_none() => {
                comment = Some(
                    value
                        .to_str()
                        .ok_or_else(|| usage_error("review comment must be valid UTF-8"))?
                        .to_owned(),
                );
            }
            _ => return Err(usage_error("duplicate or unknown review option")),
        }
        index += 2;
    }
    Ok(ReviewCommand {
        workspace: workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        decision: decision.ok_or_else(|| usage_error("--decision is required"))?,
        reviewer: reviewer.ok_or_else(|| usage_error("--reviewer is required"))?,
        comment: comment.unwrap_or_default(),
    })
}

fn parse_catalog(arguments: &[OsString]) -> Result<BenchmarkCatalogFilterV1, WorkbenchError> {
    let mut filter = BenchmarkCatalogFilterV1::default();
    let mut truth_seen = false;
    let mut size_seen = false;
    let mut lifecycle_seen = false;
    let mut query_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("catalog option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("catalog option names must be valid UTF-8"))?;
        let value = arguments[index + 1]
            .to_str()
            .ok_or_else(|| usage_error("catalog option values must be valid UTF-8"))?;
        match flag {
            "--truth" if !truth_seen => {
                truth_seen = true;
                filter.truth_class = if value == "all" {
                    None
                } else {
                    Some(BenchmarkTruthClassV1::parse(value).ok_or_else(|| {
                        usage_error("catalog truth must be all or a supported truth class")
                    })?)
                };
            }
            "--size" if !size_seen => {
                size_seen = true;
                filter.size_class = if value == "all" {
                    None
                } else {
                    Some(BenchmarkSizeClassV1::parse(value).ok_or_else(|| {
                        usage_error("catalog size must be all, small, medium, large or unknown")
                    })?)
                };
            }
            "--lifecycle" if !lifecycle_seen => {
                lifecycle_seen = true;
                if value == "all" {
                    filter.lifecycle = None;
                } else if value == "first-targets" {
                    filter.first_targets_only = true;
                } else {
                    filter.lifecycle = Some(BenchmarkLifecycleV1::parse(value).ok_or_else(|| {
                        usage_error("catalog lifecycle must be all, first-targets or a supported lifecycle")
                    })?);
                }
            }
            "--query" if !query_seen => {
                query_seen = true;
                filter.query = Some(value.to_owned());
            }
            _ => return Err(usage_error("duplicate or unknown catalog option")),
        }
        index += 2;
    }
    Ok(filter)
}

fn parse_catalog_show(arguments: &[OsString]) -> Result<String, WorkbenchError> {
    if arguments.len() == 3 && arguments[1] == "--case" {
        arguments[2]
            .to_str()
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
            .ok_or_else(|| usage_error("catalog case ID must be non-empty UTF-8"))
    } else {
        Err(usage_error("catalog-show requires exactly --case ID"))
    }
}

fn parse_evidence(arguments: &[OsString], show: bool) -> Result<EvidenceCommand, WorkbenchError> {
    let mut bundle = None;
    let mut artifact_id = None;
    let mut as_of_unix_seconds = None;
    let mut as_of_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("evidence option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("evidence option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--bundle" if bundle.is_none() => bundle = Some(PathBuf::from(value)),
            "--artifact" if show && artifact_id.is_none() => {
                artifact_id = Some(
                    value
                        .to_str()
                        .filter(|text| !text.is_empty())
                        .ok_or_else(|| usage_error("evidence artifact ID must be non-empty UTF-8"))?
                        .to_owned(),
                );
            }
            "--as-of-unix" if !as_of_seen => {
                as_of_seen = true;
                as_of_unix_seconds = Some(
                    value
                        .to_str()
                        .and_then(|text| text.parse::<i64>().ok())
                        .ok_or_else(|| usage_error("evidence as-of must be signed Unix seconds"))?,
                );
            }
            _ => return Err(usage_error("duplicate or unknown evidence option")),
        }
        index += 2;
    }
    if !show && artifact_id.is_some() {
        return Err(usage_error("evidence browse does not accept --artifact"));
    }
    Ok(EvidenceCommand {
        bundle: bundle.ok_or_else(|| usage_error("--bundle is required"))?,
        artifact_id: if show {
            Some(artifact_id.ok_or_else(|| usage_error("--artifact is required"))?)
        } else {
            None
        },
        as_of_unix_seconds,
    })
}

fn usage_error(detail: &str) -> WorkbenchError {
    WorkbenchError {
        code: "workbench_usage_error",
        detail: detail.to_owned(),
    }
}

fn usage() -> &'static str {
    concat!(
        "usage:\n  structural-workbench model-view <MODEL.json> [--projection <isometric|xy|xz|yz>]\n  structural-workbench model-edit-node <MODEL.json> --node <ID> --coordinates <X> <Y> <Z> --output-dir <DIR>\n  structural-workbench import <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench import-mgt <SOURCE.mgt> <MGT-MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench validate --workspace <DIR>\n  structural-workbench run --workspace <DIR> [--step-budget <N>]\n  structural-workbench resume --workspace <DIR> [--step-budget <N>]\n  structural-workbench compare --workspace <DIR> [--require-pass]\n  structural-workbench report --workspace <DIR>\n  structural-workbench report-view --workspace <DIR> [--locale <en-US|ko-KR>]\n  structural-workbench status --workspace <DIR>\n  structural-workbench inspect --workspace <DIR>\n  structural-workbench review --workspace <DIR> --decision <pass|review|fail> --reviewer <NAME> [--comment <TEXT>]\n  structural-workbench review-show --workspace <DIR>\n  structural-workbench export --workspace <DIR>\n  structural-workbench catalog [--truth <CLASS|all>] [--size <CLASS|all>] [--lifecycle <STATE|first-targets|all>] [--query <TEXT>]\n  structural-workbench catalog-show --case <ID>\n  structural-workbench evidence --bundle <DIR> [--as-of-unix <SECONDS>]\n  structural-workbench evidence-show --bundle <DIR> --artifact <ID> [--as-of-unix <SECONDS>]\n  structural-workbench interactive --workspace <DIR>\n  structural-workbench workflow <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]\n  structural-workbench workflow-mgt <SOURCE.mgt> <MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]",
        "\n  structural-workbench report-export-pdf --workspace <DIR> --output-dir <DIR> [--locale <en-US|ko-KR>]"
    )
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::path::PathBuf;

    use super::{
        parse_catalog, parse_catalog_show, parse_evidence, parse_import, parse_model_edit_node,
        parse_model_view, parse_report_pdf_export, parse_report_view, parse_review,
        parse_stage_command,
    };

    #[test]
    fn parser_requires_explicit_provenance_inputs() {
        let arguments = [
            OsString::from("import"),
            OsString::from("model.json"),
            OsString::from("request.json"),
            OsString::from("--external-result"),
            OsString::from("external.json"),
            OsString::from("--source-artifact"),
            OsString::from("source.json"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_import(&arguments, false, false).expect("valid import command");
        assert_eq!(parsed.workspace, PathBuf::from("session"));
        assert_eq!(parsed.step_budget, 1);
        assert_eq!(parsed.mgt_model_id, None);
    }

    #[test]
    fn model_view_parser_defaults_to_isometric_and_rejects_unknown_projection() {
        let default = [OsString::from("model-view"), OsString::from("model.json")];
        let parsed = parse_model_view(&default).expect("default model view");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.projection.label(), "isometric");

        let xz = [
            OsString::from("model-view"),
            OsString::from("model.json"),
            OsString::from("--projection"),
            OsString::from("xz"),
        ];
        assert_eq!(
            parse_model_view(&xz)
                .expect("explicit XZ projection")
                .projection
                .label(),
            "xz"
        );
        let mut invalid = xz;
        invalid[3] = OsString::from("perspective");
        assert!(parse_model_view(&invalid).is_err());
    }

    #[test]
    fn model_edit_node_parser_requires_fixed_finite_si_coordinates() {
        let arguments = [
            OsString::from("model-edit-node"),
            OsString::from("model.json"),
            OsString::from("--node"),
            OsString::from("N2"),
            OsString::from("--coordinates"),
            OsString::from("2"),
            OsString::from("1.5"),
            OsString::from("-0.25"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_node(&arguments).expect("valid node edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.node_id, "N2");
        assert_eq!(
            parsed.coordinates_m.map(f64::to_bits),
            [2.0_f64, 1.5_f64, -0.25_f64].map(f64::to_bits)
        );
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        let mut invalid = arguments;
        invalid[6] = OsString::from("NaN");
        assert!(parse_model_edit_node(&invalid).is_err());
    }

    #[test]
    fn mgt_parser_requires_an_explicit_model_identity() {
        let arguments = [
            OsString::from("import-mgt"),
            OsString::from("source.mgt"),
            OsString::from("request.json"),
            OsString::from("--model-id"),
            OsString::from("bounded-mgt-model-v1"),
            OsString::from("--external-result"),
            OsString::from("external.json"),
            OsString::from("--source-artifact"),
            OsString::from("source.json"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_import(&arguments, false, true).expect("valid MGT import command");
        assert_eq!(parsed.mgt_model_id.as_deref(), Some("bounded-mgt-model-v1"));
        let missing = &arguments[2..];
        assert!(parse_import(missing, false, true).is_err());
    }

    #[test]
    fn compare_policy_flag_is_not_a_value_option() {
        let arguments = [
            OsString::from("compare"),
            OsString::from("--workspace"),
            OsString::from("session"),
            OsString::from("--require-pass"),
        ];
        let (_, _, require_pass) =
            parse_stage_command(&arguments, "--unused", 0).expect("comparison command");
        assert!(require_pass);

        let invalid_run = [
            OsString::from("run"),
            OsString::from("--workspace"),
            OsString::from("session"),
            OsString::from("--require-pass"),
        ];
        assert!(parse_stage_command(&invalid_run, "--step-budget", 1).is_err());
    }

    #[test]
    fn review_parser_requires_an_explicit_human_disposition() {
        let arguments = [
            OsString::from("review"),
            OsString::from("--workspace"),
            OsString::from("session"),
            OsString::from("--decision"),
            OsString::from("review"),
            OsString::from("--reviewer"),
            OsString::from("Engineer A"),
            OsString::from("--comment"),
            OsString::from("Check connection assumptions."),
        ];
        let parsed = parse_review(&arguments).expect("valid explicit review");
        assert_eq!(parsed.workspace, PathBuf::from("session"));
        assert_eq!(parsed.decision.label(), "review");
        assert_eq!(parsed.reviewer, "Engineer A");

        let mut invalid = arguments;
        invalid[4] = OsString::from("inferred-pass");
        assert!(parse_review(&invalid).is_err());
    }

    #[test]
    fn report_view_parser_defaults_to_english_and_accepts_korean() {
        let default = [
            OsString::from("report-view"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let (workspace, locale) = parse_report_view(&default).expect("default report view");
        assert_eq!(workspace, PathBuf::from("session"));
        assert_eq!(locale.label(), "en-US");

        let korean = [
            OsString::from("report-view"),
            OsString::from("--locale"),
            OsString::from("ko-KR"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        assert_eq!(
            parse_report_view(&korean)
                .expect("Korean report view")
                .1
                .label(),
            "ko-KR"
        );
        let mut invalid = korean;
        invalid[2] = OsString::from("ko-kr");
        assert!(parse_report_view(&invalid).is_err());
    }

    #[test]
    fn localized_pdf_export_parser_requires_new_destination_and_closed_locale() {
        let arguments = [
            OsString::from("report-export-pdf"),
            OsString::from("--workspace"),
            OsString::from("session"),
            OsString::from("--locale"),
            OsString::from("ko-KR"),
            OsString::from("--output-dir"),
            OsString::from("localized"),
        ];
        let (workspace, output, locale) =
            parse_report_pdf_export(&arguments).expect("localized PDF export");
        assert_eq!(workspace, PathBuf::from("session"));
        assert_eq!(output, PathBuf::from("localized"));
        assert_eq!(locale.label(), "ko-KR");

        let mut invalid = arguments;
        invalid[4] = OsString::from("ko-kr");
        assert!(parse_report_pdf_export(&invalid).is_err());
        assert!(parse_report_pdf_export(&[
            OsString::from("report-export-pdf"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ])
        .is_err());
    }

    #[test]
    fn catalog_parser_preserves_explicit_filters() {
        let arguments = [
            OsString::from("catalog"),
            OsString::from("--truth"),
            OsString::from("geometry_only"),
            OsString::from("--size"),
            OsString::from("large"),
            OsString::from("--lifecycle"),
            OsString::from("first-targets"),
            OsString::from("--query"),
            OsString::from("PEER"),
        ];
        let parsed = parse_catalog(&arguments).expect("catalog filters");
        assert!(parsed.truth_class.is_some());
        assert!(parsed.size_class.is_some());
        assert!(parsed.first_targets_only);
        assert_eq!(parsed.query.as_deref(), Some("PEER"));
        assert!(parse_catalog(&[arguments[0].clone(), arguments[1].clone()]).is_err());

        let show = [
            OsString::from("catalog-show"),
            OsString::from("--case"),
            OsString::from("case-a"),
        ];
        assert_eq!(parse_catalog_show(&show).expect("show case"), "case-a");
    }

    #[test]
    fn evidence_parser_requires_an_explicit_bundle_and_show_id() {
        let browse = [
            OsString::from("evidence"),
            OsString::from("--bundle"),
            OsString::from("bundle"),
            OsString::from("--as-of-unix"),
            OsString::from("1786579200"),
        ];
        let parsed = parse_evidence(&browse, false).expect("evidence browse");
        assert_eq!(parsed.bundle, PathBuf::from("bundle"));
        assert_eq!(parsed.as_of_unix_seconds, Some(1_786_579_200));
        assert_eq!(parsed.artifact_id, None);

        let show = [
            OsString::from("evidence-show"),
            OsString::from("--bundle"),
            OsString::from("bundle"),
            OsString::from("--artifact"),
            OsString::from("product_readiness"),
        ];
        assert_eq!(
            parse_evidence(&show, true)
                .expect("evidence show")
                .artifact_id
                .as_deref(),
            Some("product_readiness")
        );
        assert!(parse_evidence(&show[..3], true).is_err());
    }
}
