use std::ffi::{OsStr, OsString};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde_json::json;
use structural_workbench::{
    NativeWorkbench, WorkbenchError, WorkbenchReviewDecisionV1, WorkbenchStageV1,
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
        Some("review") => parse_review(arguments).and_then(|command| run_review(&command)),
        Some("review-show") => {
            parse_workspace_only(arguments).and_then(|workspace| run_review_show(&workspace))
        }
        Some("export") => {
            parse_workspace_only(arguments).and_then(|workspace| run_export(&workspace))
        }
        Some("interactive") => {
            parse_workspace_only(arguments).and_then(|workspace| run_interactive(&workspace))
        }
        _ => Err(usage_error("unknown or incomplete Workbench command")),
    };
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

fn usage_error(detail: &str) -> WorkbenchError {
    WorkbenchError {
        code: "workbench_usage_error",
        detail: detail.to_owned(),
    }
}

fn usage() -> &'static str {
    "usage:\n  structural-workbench import <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench import-mgt <SOURCE.mgt> <MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench validate --workspace <DIR>\n  structural-workbench run --workspace <DIR> [--step-budget <N>]\n  structural-workbench resume --workspace <DIR> [--step-budget <N>]\n  structural-workbench compare --workspace <DIR> [--require-pass]\n  structural-workbench report --workspace <DIR>\n  structural-workbench status --workspace <DIR>\n  structural-workbench inspect --workspace <DIR>\n  structural-workbench review --workspace <DIR> --decision <pass|review|fail> --reviewer <NAME> [--comment <TEXT>]\n  structural-workbench review-show --workspace <DIR>\n  structural-workbench export --workspace <DIR>\n  structural-workbench interactive --workspace <DIR>\n  structural-workbench workflow <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]\n  structural-workbench workflow-mgt <SOURCE.mgt> <MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]"
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::path::PathBuf;

    use super::{parse_import, parse_review, parse_stage_command};

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
}
