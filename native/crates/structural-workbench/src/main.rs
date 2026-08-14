use std::ffi::{OsStr, OsString};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde_json::json;
use structural_contracts::sparse_product::SparseLinearConfigV1;
use structural_workbench::{
    browse_embedded_benchmark_catalog, browse_evidence_bundle, show_embedded_benchmark_case,
    show_evidence_artifact, BenchmarkCatalogFilterV1, BenchmarkLifecycleV1, BenchmarkSizeClassV1,
    BenchmarkTruthClassV1, FrameSectionParametersV1, LinearElasticMaterialParametersV1,
    ModelTopologyProjectionV1, NativeWorkbench, TrussSectionParametersV1, WorkbenchError,
    WorkbenchReportLocaleV1, WorkbenchResultChannelV1, WorkbenchReviewDecisionV1, WorkbenchStageV1,
    WORKBENCH_DEFORMED_VIEW_DEFAULT_SCALE_V1, WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1,
    WORKBENCH_RESULT_VIEW_DEFAULT_COUNT_V1, WORKBENCH_RESULT_VIEW_MAX_COUNT_V1,
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
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditNodeCommand {
    model: PathBuf,
    node_id: String,
    coordinates_m: [f64; 3],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddNodeCommand {
    model: PathBuf,
    node_id: String,
    coordinates_m: [f64; 3],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteOrphanNodeCommand {
    model: PathBuf,
    node_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditNodalLoadCommand {
    model: PathBuf,
    load_pattern_id: String,
    nodal_load_id: String,
    components_si: [f64; 6],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddNodalLoadCommand {
    model: PathBuf,
    load_pattern_id: String,
    nodal_load_id: String,
    node_id: String,
    components_si: [f64; 6],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteNodalLoadCommand {
    model: PathBuf,
    load_pattern_id: String,
    nodal_load_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelAddFixedConstraintCommand {
    model: PathBuf,
    constraint_id: String,
    node_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteFixedConstraintCommand {
    model: PathBuf,
    constraint_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddLinearLoadPatternCommand {
    model: PathBuf,
    load_pattern_id: String,
    nodal_load_id: String,
    node_id: String,
    components_si: [f64; 6],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteLinearLoadPatternCommand {
    model: PathBuf,
    load_pattern_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddLinearMaterialCommand {
    model: PathBuf,
    material_id: String,
    parameters: LinearElasticMaterialParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteLinearMaterialCommand {
    model: PathBuf,
    material_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddFrameSectionCommand {
    model: PathBuf,
    section_id: String,
    parameters: FrameSectionParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteFrameSectionCommand {
    model: PathBuf,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddTrussSectionCommand {
    model: PathBuf,
    section_id: String,
    parameters: TrussSectionParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteTrussSectionCommand {
    model: PathBuf,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditConstraintValueCommand {
    model: PathBuf,
    constraint_id: String,
    dof: String,
    value_si: f64,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditLinearMaterialCommand {
    model: PathBuf,
    material_id: String,
    parameters: LinearElasticMaterialParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditFrameSectionCommand {
    model: PathBuf,
    section_id: String,
    parameters: FrameSectionParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditTrussSectionCommand {
    model: PathBuf,
    section_id: String,
    parameters: TrussSectionParametersV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelEditFrameElementOrientationCommand {
    model: PathBuf,
    element_id: String,
    local_axis_rotation_rad: f64,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelEditFrameElementPropertiesCommand {
    model: PathBuf,
    element_id: String,
    material_id: String,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelEditTrussElementPropertiesCommand {
    model: PathBuf,
    element_id: String,
    material_id: String,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelEditElementConnectivityCommand {
    model: PathBuf,
    element_id: String,
    node_ids: [String; 2],
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddFrame3dMemberCommand {
    model: PathBuf,
    node_id: String,
    coordinates_m: [f64; 3],
    element_id: String,
    from_node_id: String,
    material_id: String,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelAddTruss3dMemberCommand {
    model: PathBuf,
    node_id: String,
    coordinates_m: [f64; 3],
    element_id: String,
    from_node_id: String,
    material_id: String,
    section_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteFrame3dLeafMemberCommand {
    model: PathBuf,
    element_id: String,
    node_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ModelDeleteTruss3dLeafMemberCommand {
    model: PathBuf,
    element_id: String,
    node_id: String,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
struct ModelCreateLinearAnalysisRequestCommand {
    model: PathBuf,
    case_id: String,
    load_pattern_id: String,
    config: SparseLinearConfigV1,
    output_directory: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ResultViewCommand {
    workspace: PathBuf,
    locale: WorkbenchReportLocaleV1,
    channel: WorkbenchResultChannelV1,
    start_step: u32,
    count: u32,
}

#[derive(Clone, Debug, PartialEq)]
struct DeformedViewCommand {
    workspace: PathBuf,
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
    step: Option<u32>,
    scale: f64,
}

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    run(&arguments)
}

#[allow(clippy::too_many_lines)] // Closed command dispatch stays visible in one auditable match.
fn run(arguments: &[OsString]) -> ExitCode {
    if arguments.len() == 1 && arguments[0] == "--version" {
        return print_version();
    }
    let result = match arguments.first().and_then(|argument| argument.to_str()) {
        Some("import") => {
            parse_import(arguments, false, false).and_then(|command| run_import(&command))
        }
        Some("import-mgt") => {
            parse_import(arguments, false, true).and_then(|command| run_import(&command))
        }
        Some("import-model-linear") => parse_import(arguments, false, false)
            .and_then(|command| run_model_ir_linear_import(&command)),
        Some("import-mgt-model-linear") => parse_import(arguments, false, true)
            .and_then(|command| run_model_ir_linear_import(&command)),
        Some("workflow") => {
            parse_import(arguments, true, false).and_then(|command| run_workflow(&command))
        }
        Some("workflow-mgt") => {
            parse_import(arguments, true, true).and_then(|command| run_workflow(&command))
        }
        Some("workflow-model-linear") => parse_import(arguments, true, false)
            .and_then(|command| run_model_ir_linear_workflow(&command)),
        Some("workflow-mgt-model-linear") => parse_import(arguments, true, true)
            .and_then(|command| run_model_ir_linear_workflow(&command)),
        Some("model-view") => {
            parse_model_view(arguments).and_then(|command| run_model_view(&command))
        }
        Some("model-edit-node") => {
            parse_model_edit_node(arguments).and_then(|command| run_model_edit_node(&command))
        }
        Some("model-edit-nodal-load") => parse_model_edit_nodal_load(arguments)
            .and_then(|command| run_model_edit_nodal_load(&command)),
        Some("model-add-node") => {
            parse_model_add_node(arguments).and_then(|command| run_model_add_node(&command))
        }
        Some("model-delete-orphan-node") => parse_model_delete_orphan_node(arguments)
            .and_then(|command| run_model_delete_orphan_node(&command)),
        Some("model-add-nodal-load") => parse_model_add_nodal_load(arguments)
            .and_then(|command| run_model_add_nodal_load(&command)),
        Some("model-delete-nodal-load") => parse_model_delete_nodal_load(arguments)
            .and_then(|command| run_model_delete_nodal_load(&command)),
        Some("model-add-fixed-constraint") => parse_model_add_fixed_constraint(arguments)
            .and_then(|command| run_model_add_fixed_constraint(&command)),
        Some("model-delete-fixed-constraint") => parse_model_delete_fixed_constraint(arguments)
            .and_then(|command| run_model_delete_fixed_constraint(&command)),
        Some("model-add-linear-load-pattern") => parse_model_add_linear_load_pattern(arguments)
            .and_then(|command| run_model_add_linear_load_pattern(&command)),
        Some("model-delete-linear-load-pattern") => {
            parse_model_delete_linear_load_pattern(arguments)
                .and_then(|command| run_model_delete_linear_load_pattern(&command))
        }
        Some("model-add-linear-material") => parse_model_add_linear_material(arguments)
            .and_then(|command| run_model_add_linear_material(&command)),
        Some("model-delete-linear-material") => parse_model_delete_linear_material(arguments)
            .and_then(|command| run_model_delete_linear_material(&command)),
        Some("model-add-frame-section") => parse_model_add_frame_section(arguments)
            .and_then(|command| run_model_add_frame_section(&command)),
        Some("model-delete-frame-section") => parse_model_delete_frame_section(arguments)
            .and_then(|command| run_model_delete_frame_section(&command)),
        Some("model-add-truss-section") => parse_model_add_truss_section(arguments)
            .and_then(|command| run_model_add_truss_section(&command)),
        Some("model-delete-truss-section") => parse_model_delete_truss_section(arguments)
            .and_then(|command| run_model_delete_truss_section(&command)),
        Some("model-edit-constraint-value") => parse_model_edit_constraint_value(arguments)
            .and_then(|command| run_model_edit_constraint_value(&command)),
        Some("model-edit-linear-material") => parse_model_edit_linear_material(arguments)
            .and_then(|command| run_model_edit_linear_material(&command)),
        Some("model-edit-frame-section") => parse_model_edit_frame_section(arguments)
            .and_then(|command| run_model_edit_frame_section(&command)),
        Some("model-edit-truss-section") => parse_model_edit_truss_section(arguments)
            .and_then(|command| run_model_edit_truss_section(&command)),
        Some("model-edit-frame-element-orientation") => {
            parse_model_edit_frame_element_orientation(arguments)
                .and_then(|command| run_model_edit_frame_element_orientation(&command))
        }
        Some("model-edit-frame-element-properties") => {
            parse_model_edit_frame_element_properties(arguments)
                .and_then(|command| run_model_edit_frame_element_properties(&command))
        }
        Some("model-edit-truss-element-properties") => {
            parse_model_edit_truss_element_properties(arguments)
                .and_then(|command| run_model_edit_truss_element_properties(&command))
        }
        Some("model-edit-element-connectivity") => parse_model_edit_element_connectivity(arguments)
            .and_then(|command| run_model_edit_element_connectivity(&command)),
        Some("model-add-frame3d-member") => parse_model_add_frame3d_member(arguments)
            .and_then(|command| run_model_add_frame3d_member(&command)),
        Some("model-add-truss3d-member") => parse_model_add_truss3d_member(arguments)
            .and_then(|command| run_model_add_truss3d_member(&command)),
        Some("model-delete-frame3d-leaf-member") => {
            parse_model_delete_frame3d_leaf_member(arguments)
                .and_then(|command| run_model_delete_frame3d_leaf_member(&command))
        }
        Some("model-delete-truss3d-leaf-member") => {
            parse_model_delete_truss3d_leaf_member(arguments)
                .and_then(|command| run_model_delete_truss3d_leaf_member(&command))
        }
        Some("model-create-linear-analysis-request") => {
            parse_model_create_linear_analysis_request(arguments)
                .and_then(|command| run_model_create_linear_analysis_request(&command))
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
        Some("result-view") => {
            parse_result_view(arguments).and_then(|command| run_result_view(&command))
        }
        Some("result-deformed-view") => {
            parse_deformed_view(arguments).and_then(|command| run_deformed_view(&command))
        }
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

fn print_version() -> ExitCode {
    println!("structural-workbench {}", env!("CARGO_PKG_VERSION"));
    ExitCode::SUCCESS
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
                    | "workbench_result_view_window_invalid"
                    | "workbench_deformed_view_step_invalid"
                    | "workbench_deformed_view_scale_invalid"
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

fn run_model_ir_linear_import(command: &ImportCommand) -> Result<(), WorkbenchError> {
    let workbench = initialize_model_ir_linear(command)?;
    print_session(&workbench)
}

fn run_model_ir_linear_workflow(command: &ImportCommand) -> Result<(), WorkbenchError> {
    let mut workbench = initialize_model_ir_linear(command)?;
    workbench.validate()?;
    workbench.run(command.step_budget)?;
    workbench.resume(0)?;
    workbench.compare(true)?;
    workbench.report()?;
    print_session(&workbench)
}

fn run_result_view(command: &ResultViewCommand) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(&command.workspace)?;
    print!(
        "{}",
        workbench.ndtha_response_view_text_localized(
            command.locale,
            command.channel,
            command.start_step,
            command.count,
        )?
    );
    Ok(())
}

fn run_deformed_view(command: &DeformedViewCommand) -> Result<(), WorkbenchError> {
    let workbench = NativeWorkbench::open(&command.workspace)?;
    print!(
        "{}",
        workbench.fixed_guided_deformed_shape_view_text_localized(
            command.locale,
            command.projection,
            command.step,
            command.scale,
        )?
    );
    Ok(())
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

fn initialize_model_ir_linear(command: &ImportCommand) -> Result<NativeWorkbench, WorkbenchError> {
    if let Some(model_id) = command.mgt_model_id.as_deref() {
        NativeWorkbench::initialize_model_ir_linear_from_mgt_paths(
            &command.workspace,
            &command.model,
            model_id,
            &command.request,
            &command.external_result,
            &command.source_artifact,
            command.executable_artifact.as_deref(),
        )
    } else {
        NativeWorkbench::initialize_model_ir_linear_from_paths(
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
        structural_workbench::render_model_topology_view_file_localized(
            &command.model,
            command.locale,
            command.projection,
        )?
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

fn run_model_add_node(command: &ModelAddNodeCommand) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_node_add(
        &command.model,
        &command.node_id,
        command.coordinates_m,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_orphan_node(
    command: &ModelDeleteOrphanNodeCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_orphan_node_delete(
        &command.model,
        &command.node_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_nodal_load(command: &ModelEditNodalLoadCommand) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_nodal_load_components_edit(
        &command.model,
        &command.load_pattern_id,
        &command.nodal_load_id,
        command.components_si,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_nodal_load(command: &ModelAddNodalLoadCommand) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_nodal_load_add(
        &command.model,
        &command.load_pattern_id,
        &command.nodal_load_id,
        &command.node_id,
        command.components_si,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_nodal_load(
    command: &ModelDeleteNodalLoadCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_nodal_load_delete(
        &command.model,
        &command.load_pattern_id,
        &command.nodal_load_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_fixed_constraint(
    command: &ModelAddFixedConstraintCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_fixed_constraint_add(
        &command.model,
        &command.constraint_id,
        &command.node_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_fixed_constraint(
    command: &ModelDeleteFixedConstraintCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_fixed_constraint_delete(
        &command.model,
        &command.constraint_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_linear_load_pattern(
    command: &ModelAddLinearLoadPatternCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_load_pattern_add(
        &command.model,
        &command.load_pattern_id,
        &command.nodal_load_id,
        &command.node_id,
        command.components_si,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_linear_load_pattern(
    command: &ModelDeleteLinearLoadPatternCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_load_pattern_delete(
        &command.model,
        &command.load_pattern_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_linear_material(
    command: &ModelAddLinearMaterialCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_material_add(
        &command.model,
        &command.material_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_linear_material(
    command: &ModelDeleteLinearMaterialCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_material_delete(
        &command.model,
        &command.material_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_frame_section(
    command: &ModelAddFrameSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame_section_add(
        &command.model,
        &command.section_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_frame_section(
    command: &ModelDeleteFrameSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame_section_delete(
        &command.model,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_truss_section(
    command: &ModelAddTrussSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss_section_add(
        &command.model,
        &command.section_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_truss_section(
    command: &ModelDeleteTrussSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss_section_delete(
        &command.model,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_constraint_value(
    command: &ModelEditConstraintValueCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_constraint_value_edit(
        &command.model,
        &command.constraint_id,
        &command.dof,
        command.value_si,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_linear_material(
    command: &ModelEditLinearMaterialCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_material_edit(
        &command.model,
        &command.material_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_frame_section(
    command: &ModelEditFrameSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame_section_edit(
        &command.model,
        &command.section_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_truss_section(
    command: &ModelEditTrussSectionCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss_section_edit(
        &command.model,
        &command.section_id,
        command.parameters,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_frame_element_orientation(
    command: &ModelEditFrameElementOrientationCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame_element_orientation_edit(
        &command.model,
        &command.element_id,
        command.local_axis_rotation_rad,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_frame_element_properties(
    command: &ModelEditFrameElementPropertiesCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame_element_properties_edit(
        &command.model,
        &command.element_id,
        &command.material_id,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_truss_element_properties(
    command: &ModelEditTrussElementPropertiesCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss_element_properties_edit(
        &command.model,
        &command.element_id,
        &command.material_id,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_edit_element_connectivity(
    command: &ModelEditElementConnectivityCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_element_connectivity_edit(
        &command.model,
        &command.element_id,
        [&command.node_ids[0], &command.node_ids[1]],
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_frame3d_member(
    command: &ModelAddFrame3dMemberCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame3d_member_add(
        &command.model,
        &command.node_id,
        command.coordinates_m,
        &command.element_id,
        &command.from_node_id,
        &command.material_id,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_add_truss3d_member(
    command: &ModelAddTruss3dMemberCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss3d_member_add(
        &command.model,
        &command.node_id,
        command.coordinates_m,
        &command.element_id,
        &command.from_node_id,
        &command.material_id,
        &command.section_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_frame3d_leaf_member(
    command: &ModelDeleteFrame3dLeafMemberCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_frame3d_leaf_member_delete(
        &command.model,
        &command.element_id,
        &command.node_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_delete_truss3d_leaf_member(
    command: &ModelDeleteTruss3dLeafMemberCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_truss3d_leaf_member_delete(
        &command.model,
        &command.element_id,
        &command.node_id,
        &command.output_directory,
    )?;
    println!("{}", outcome.receipt_json);
    Ok(())
}

fn run_model_create_linear_analysis_request(
    command: &ModelCreateLinearAnalysisRequestCommand,
) -> Result<(), WorkbenchError> {
    let outcome = structural_workbench::publish_model_linear_analysis_request(
        &command.model,
        &command.case_id,
        &command.load_pattern_id,
        command.config,
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
            WorkbenchStageV1::Compared => {
                if workbench.session().analysis_profile().is_some() {
                    "Publish verified ReportIR and PDF-ready document source"
                } else {
                    "Render native PDF report"
                }
            }
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
    if arguments.len() < 2 || arguments.len() > 6 || arguments.len() % 2 != 0 {
        return Err(usage_error(
            "model-view requires MODEL.json with optional --locale and --projection values",
        ));
    }
    let mut locale = WorkbenchReportLocaleV1::EnUs;
    let mut locale_seen = false;
    let mut projection = ModelTopologyProjectionV1::Isometric;
    let mut projection_seen = false;
    let mut index = 2;
    while index < arguments.len() {
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("model-view option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--locale" if !locale_seen => {
                locale_seen = true;
                locale = value
                    .to_str()
                    .and_then(WorkbenchReportLocaleV1::parse)
                    .ok_or_else(|| usage_error("model-view locale must be en-US or ko-KR"))?;
            }
            "--projection" if !projection_seen => {
                projection_seen = true;
                projection = value
                    .to_str()
                    .and_then(ModelTopologyProjectionV1::parse)
                    .ok_or_else(|| {
                        usage_error("model-view projection must be isometric, xy, xz or yz")
                    })?;
            }
            _ => return Err(usage_error("duplicate or unknown model-view option")),
        }
        index += 2;
    }
    Ok(ModelViewCommand {
        model: PathBuf::from(&arguments[1]),
        locale,
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

fn parse_model_add_node(arguments: &[OsString]) -> Result<ModelAddNodeCommand, WorkbenchError> {
    if arguments.len() != 10
        || arguments[2] != "--node"
        || arguments[4] != "--coordinates"
        || arguments[8] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-node requires MODEL.json --node NEW-ID --coordinates X Y Z --output-dir DIR",
        ));
    }
    let mut coordinates_m = [0.0; 3];
    for (target, source) in coordinates_m.iter_mut().zip(&arguments[5..8]) {
        *target = parse_finite_edit_number(source, "model-add-node coordinate")?;
    }
    Ok(ModelAddNodeCommand {
        model: PathBuf::from(&arguments[1]),
        node_id: parse_bounded_edit_id(&arguments[3], "model-add-node new node ID")?,
        coordinates_m,
        output_directory: PathBuf::from(&arguments[9]),
    })
}

fn parse_model_delete_orphan_node(
    arguments: &[OsString],
) -> Result<ModelDeleteOrphanNodeCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--node" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-orphan-node requires MODEL.json --node ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteOrphanNodeCommand {
        model: PathBuf::from(&arguments[1]),
        node_id: parse_bounded_edit_id(&arguments[3], "model-delete-orphan-node node ID")?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_edit_nodal_load(
    arguments: &[OsString],
) -> Result<ModelEditNodalLoadCommand, WorkbenchError> {
    if arguments.len() != 15
        || arguments[2] != "--load-pattern"
        || arguments[4] != "--load"
        || arguments[6] != "--components"
        || arguments[13] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-nodal-load requires MODEL.json --load-pattern PATTERN-ID --load LOAD-ID --components FX FY FZ MX MY MZ --output-dir DIR",
        ));
    }
    let bounded_id = |argument: &OsString, name: &str| {
        argument
            .to_str()
            .filter(|value| !value.is_empty() && value.len() <= 128)
            .map(ToOwned::to_owned)
            .ok_or_else(|| {
                usage_error(&format!(
                    "model-edit-nodal-load {name} must be valid UTF-8 with 1-128 bytes"
                ))
            })
    };
    let mut components_si = [0.0; 6];
    for (target, source) in components_si.iter_mut().zip(&arguments[7..13]) {
        *target = source
            .to_str()
            .and_then(|value| value.parse::<f64>().ok())
            .filter(|value| value.is_finite())
            .ok_or_else(|| {
                usage_error("model-edit-nodal-load components must be finite SI numbers")
            })?;
    }
    Ok(ModelEditNodalLoadCommand {
        model: PathBuf::from(&arguments[1]),
        load_pattern_id: bounded_id(&arguments[3], "load-pattern ID")?,
        nodal_load_id: bounded_id(&arguments[5], "load ID")?,
        components_si,
        output_directory: PathBuf::from(&arguments[14]),
    })
}

fn parse_model_add_nodal_load(
    arguments: &[OsString],
) -> Result<ModelAddNodalLoadCommand, WorkbenchError> {
    if arguments.len() != 17
        || arguments[2] != "--load-pattern"
        || arguments[4] != "--load"
        || arguments[6] != "--node"
        || arguments[8] != "--components"
        || arguments[15] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-nodal-load requires MODEL.json --load-pattern PATTERN-ID --load NEW-LOAD-ID --node EXISTING-NODE-ID --components FX FY FZ MX MY MZ --output-dir DIR",
        ));
    }
    let mut components_si = [0.0; 6];
    for (target, source) in components_si.iter_mut().zip(&arguments[9..15]) {
        *target = parse_finite_edit_number(source, "model-add-nodal-load component")?;
    }
    if components_si.iter().all(|value| *value == 0.0) {
        return Err(usage_error(
            "model-add-nodal-load requires at least one non-zero component",
        ));
    }
    Ok(ModelAddNodalLoadCommand {
        model: PathBuf::from(&arguments[1]),
        load_pattern_id: parse_bounded_edit_id(
            &arguments[3],
            "model-add-nodal-load load-pattern ID",
        )?,
        nodal_load_id: parse_bounded_edit_id(&arguments[5], "model-add-nodal-load new load ID")?,
        node_id: parse_bounded_edit_id(&arguments[7], "model-add-nodal-load target node ID")?,
        components_si,
        output_directory: PathBuf::from(&arguments[16]),
    })
}

fn parse_model_delete_nodal_load(
    arguments: &[OsString],
) -> Result<ModelDeleteNodalLoadCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--load-pattern"
        || arguments[4] != "--load"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-delete-nodal-load requires MODEL.json --load-pattern PATTERN-ID --load LOAD-ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteNodalLoadCommand {
        model: PathBuf::from(&arguments[1]),
        load_pattern_id: parse_bounded_edit_id(
            &arguments[3],
            "model-delete-nodal-load load-pattern ID",
        )?,
        nodal_load_id: parse_bounded_edit_id(&arguments[5], "model-delete-nodal-load load ID")?,
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_add_fixed_constraint(
    arguments: &[OsString],
) -> Result<ModelAddFixedConstraintCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--constraint"
        || arguments[4] != "--node"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-fixed-constraint requires MODEL.json --constraint NEW-ID --node EXISTING-NODE-ID --output-dir DIR",
        ));
    }
    Ok(ModelAddFixedConstraintCommand {
        model: PathBuf::from(&arguments[1]),
        constraint_id: parse_bounded_edit_id(
            &arguments[3],
            "model-add-fixed-constraint new constraint ID",
        )?,
        node_id: parse_bounded_edit_id(&arguments[5], "model-add-fixed-constraint target node ID")?,
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_delete_fixed_constraint(
    arguments: &[OsString],
) -> Result<ModelDeleteFixedConstraintCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--constraint" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-fixed-constraint requires MODEL.json --constraint ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteFixedConstraintCommand {
        model: PathBuf::from(&arguments[1]),
        constraint_id: parse_bounded_edit_id(
            &arguments[3],
            "model-delete-fixed-constraint constraint ID",
        )?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_add_linear_load_pattern(
    arguments: &[OsString],
) -> Result<ModelAddLinearLoadPatternCommand, WorkbenchError> {
    if arguments.len() != 17
        || arguments[2] != "--load-pattern"
        || arguments[4] != "--load"
        || arguments[6] != "--node"
        || arguments[8] != "--components"
        || arguments[15] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-linear-load-pattern requires MODEL.json --load-pattern NEW-PATTERN-ID --load NEW-LOAD-ID --node EXISTING-NODE-ID --components FX FY FZ MX MY MZ --output-dir DIR",
        ));
    }
    let mut components_si = [0.0; 6];
    for (target, source) in components_si.iter_mut().zip(&arguments[9..15]) {
        *target = parse_finite_edit_number(source, "model-add-linear-load-pattern component")?;
    }
    if components_si.iter().all(|value| *value == 0.0) {
        return Err(usage_error(
            "model-add-linear-load-pattern requires at least one non-zero component",
        ));
    }
    Ok(ModelAddLinearLoadPatternCommand {
        model: PathBuf::from(&arguments[1]),
        load_pattern_id: parse_bounded_edit_id(
            &arguments[3],
            "model-add-linear-load-pattern new load-pattern ID",
        )?,
        nodal_load_id: parse_bounded_edit_id(
            &arguments[5],
            "model-add-linear-load-pattern new load ID",
        )?,
        node_id: parse_bounded_edit_id(
            &arguments[7],
            "model-add-linear-load-pattern target node ID",
        )?,
        components_si,
        output_directory: PathBuf::from(&arguments[16]),
    })
}

fn parse_model_delete_linear_load_pattern(
    arguments: &[OsString],
) -> Result<ModelDeleteLinearLoadPatternCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--load-pattern" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-linear-load-pattern requires MODEL.json --load-pattern ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteLinearLoadPatternCommand {
        model: PathBuf::from(&arguments[1]),
        load_pattern_id: parse_bounded_edit_id(
            &arguments[3],
            "model-delete-linear-load-pattern load-pattern ID",
        )?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_add_linear_material(
    arguments: &[OsString],
) -> Result<ModelAddLinearMaterialCommand, WorkbenchError> {
    if arguments.len() != 12
        || arguments[2] != "--material"
        || arguments[4] != "--elastic-modulus-pa"
        || arguments[6] != "--poisson-ratio"
        || arguments[8] != "--density-kg-m3"
        || arguments[10] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-linear-material requires MODEL.json --material NEW-ID --elastic-modulus-pa E --poisson-ratio NU --density-kg-m3 RHO --output-dir DIR",
        ));
    }
    let parameters = LinearElasticMaterialParametersV1 {
        elastic_modulus_pa: parse_finite_edit_number(
            &arguments[5],
            "model-add-linear-material elastic modulus",
        )?,
        poisson_ratio: parse_finite_edit_number(
            &arguments[7],
            "model-add-linear-material Poisson ratio",
        )?,
        density_kg_m3: parse_finite_edit_number(
            &arguments[9],
            "model-add-linear-material density",
        )?,
    };
    if parameters.elastic_modulus_pa <= 0.0
        || parameters.poisson_ratio <= -1.0
        || parameters.poisson_ratio >= 0.5
        || parameters.density_kg_m3 < 0.0
    {
        return Err(usage_error(
            "model-add-linear-material requires E > 0, -1 < NU < 0.5, and RHO >= 0",
        ));
    }
    Ok(ModelAddLinearMaterialCommand {
        model: PathBuf::from(&arguments[1]),
        material_id: parse_bounded_edit_id(
            &arguments[3],
            "model-add-linear-material new material ID",
        )?,
        parameters,
        output_directory: PathBuf::from(&arguments[11]),
    })
}

fn parse_model_delete_linear_material(
    arguments: &[OsString],
) -> Result<ModelDeleteLinearMaterialCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--material" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-linear-material requires MODEL.json --material ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteLinearMaterialCommand {
        model: PathBuf::from(&arguments[1]),
        material_id: parse_bounded_edit_id(
            &arguments[3],
            "model-delete-linear-material material ID",
        )?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_add_frame_section(
    arguments: &[OsString],
) -> Result<ModelAddFrameSectionCommand, WorkbenchError> {
    if arguments.len() != 18
        || arguments[2] != "--section"
        || arguments[4] != "--area-m2"
        || arguments[6] != "--iy-m4"
        || arguments[8] != "--iz-m4"
        || arguments[10] != "--torsional-constant-m4"
        || arguments[12] != "--shear-area-y-m2"
        || arguments[14] != "--shear-area-z-m2"
        || arguments[16] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-frame-section requires MODEL.json --section NEW-ID --area-m2 A --iy-m4 IY --iz-m4 IZ --torsional-constant-m4 J --shear-area-y-m2 AY --shear-area-z-m2 AZ --output-dir DIR",
        ));
    }
    let values = arguments[5..16]
        .iter()
        .step_by(2)
        .map(|value| parse_finite_edit_number(value, "model-add-frame-section parameter"))
        .collect::<Result<Vec<_>, _>>()?;
    if values.iter().any(|value| *value <= 0.0) {
        return Err(usage_error(
            "model-add-frame-section parameters must be finite SI numbers greater than zero",
        ));
    }
    Ok(ModelAddFrameSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-add-frame-section new section ID")?,
        parameters: FrameSectionParametersV1 {
            area_m2: values[0],
            iy_m4: values[1],
            iz_m4: values[2],
            torsional_constant_m4: values[3],
            shear_area_y_m2: values[4],
            shear_area_z_m2: values[5],
        },
        output_directory: PathBuf::from(&arguments[17]),
    })
}

fn parse_model_delete_frame_section(
    arguments: &[OsString],
) -> Result<ModelDeleteFrameSectionCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--section" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-frame-section requires MODEL.json --section ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteFrameSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-delete-frame-section section ID")?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_add_truss_section(
    arguments: &[OsString],
) -> Result<ModelAddTrussSectionCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--section"
        || arguments[4] != "--area-m2"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-truss-section requires MODEL.json --section NEW-ID --area-m2 A --output-dir DIR",
        ));
    }
    let area_m2 = parse_finite_edit_number(
        &arguments[5],
        "model-add-truss-section cross-sectional area",
    )?;
    if area_m2 <= 0.0 {
        return Err(usage_error(
            "model-add-truss-section area must be a finite SI number greater than zero",
        ));
    }
    Ok(ModelAddTrussSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-add-truss-section new section ID")?,
        parameters: TrussSectionParametersV1 { area_m2 },
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_delete_truss_section(
    arguments: &[OsString],
) -> Result<ModelDeleteTrussSectionCommand, WorkbenchError> {
    if arguments.len() != 6 || arguments[2] != "--section" || arguments[4] != "--output-dir" {
        return Err(usage_error(
            "model-delete-truss-section requires MODEL.json --section ID --output-dir DIR",
        ));
    }
    Ok(ModelDeleteTrussSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-delete-truss-section section ID")?,
        output_directory: PathBuf::from(&arguments[5]),
    })
}

fn parse_model_edit_constraint_value(
    arguments: &[OsString],
) -> Result<ModelEditConstraintValueCommand, WorkbenchError> {
    if arguments.len() != 10
        || arguments[2] != "--constraint"
        || arguments[4] != "--dof"
        || arguments[6] != "--value"
        || arguments[8] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-constraint-value requires MODEL.json --constraint ID --dof UX|UY|UZ|RX|RY|RZ --value SI-VALUE --output-dir DIR",
        ));
    }
    let constraint_id = arguments[3]
        .to_str()
        .filter(|value| !value.is_empty() && value.len() <= 128)
        .ok_or_else(|| {
            usage_error(
                "model-edit-constraint-value constraint ID must be valid UTF-8 with 1-128 bytes",
            )
        })?
        .to_owned();
    let dof = arguments[5]
        .to_str()
        .filter(|value| matches!(*value, "UX" | "UY" | "UZ" | "RX" | "RY" | "RZ"))
        .ok_or_else(|| {
            usage_error("model-edit-constraint-value DOF must be UX, UY, UZ, RX, RY, or RZ")
        })?
        .to_owned();
    let value_si = arguments[7]
        .to_str()
        .and_then(|value| value.parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            usage_error("model-edit-constraint-value prescribed value must be a finite SI number")
        })?;
    Ok(ModelEditConstraintValueCommand {
        model: PathBuf::from(&arguments[1]),
        constraint_id,
        dof,
        value_si,
        output_directory: PathBuf::from(&arguments[9]),
    })
}

fn parse_model_edit_linear_material(
    arguments: &[OsString],
) -> Result<ModelEditLinearMaterialCommand, WorkbenchError> {
    if arguments.len() != 12
        || arguments[2] != "--material"
        || arguments[4] != "--elastic-modulus-pa"
        || arguments[6] != "--poisson-ratio"
        || arguments[8] != "--density-kg-m3"
        || arguments[10] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-linear-material requires MODEL.json --material ID --elastic-modulus-pa E --poisson-ratio NU --density-kg-m3 RHO --output-dir DIR",
        ));
    }
    let material_id =
        parse_bounded_edit_id(&arguments[3], "model-edit-linear-material material ID")?;
    let parameters = LinearElasticMaterialParametersV1 {
        elastic_modulus_pa: parse_finite_edit_number(
            &arguments[5],
            "model-edit-linear-material elastic modulus",
        )?,
        poisson_ratio: parse_finite_edit_number(
            &arguments[7],
            "model-edit-linear-material Poisson ratio",
        )?,
        density_kg_m3: parse_finite_edit_number(
            &arguments[9],
            "model-edit-linear-material density",
        )?,
    };
    if parameters.elastic_modulus_pa <= 0.0
        || parameters.poisson_ratio <= -1.0
        || parameters.poisson_ratio >= 0.5
        || parameters.density_kg_m3 < 0.0
    {
        return Err(usage_error(
            "model-edit-linear-material requires E > 0, -1 < NU < 0.5, and RHO >= 0",
        ));
    }
    Ok(ModelEditLinearMaterialCommand {
        model: PathBuf::from(&arguments[1]),
        material_id,
        parameters,
        output_directory: PathBuf::from(&arguments[11]),
    })
}

fn parse_model_edit_frame_section(
    arguments: &[OsString],
) -> Result<ModelEditFrameSectionCommand, WorkbenchError> {
    if arguments.len() != 18
        || arguments[2] != "--section"
        || arguments[4] != "--area-m2"
        || arguments[6] != "--iy-m4"
        || arguments[8] != "--iz-m4"
        || arguments[10] != "--torsional-constant-m4"
        || arguments[12] != "--shear-area-y-m2"
        || arguments[14] != "--shear-area-z-m2"
        || arguments[16] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-frame-section requires MODEL.json --section ID --area-m2 A --iy-m4 IY --iz-m4 IZ --torsional-constant-m4 J --shear-area-y-m2 AY --shear-area-z-m2 AZ --output-dir DIR",
        ));
    }
    let values = arguments[5..16]
        .iter()
        .step_by(2)
        .map(|value| parse_finite_edit_number(value, "model-edit-frame-section parameter"))
        .collect::<Result<Vec<_>, _>>()?;
    if values.iter().any(|value| *value <= 0.0) {
        return Err(usage_error(
            "model-edit-frame-section parameters must be finite SI numbers greater than zero",
        ));
    }
    Ok(ModelEditFrameSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-edit-frame-section section ID")?,
        parameters: FrameSectionParametersV1 {
            area_m2: values[0],
            iy_m4: values[1],
            iz_m4: values[2],
            torsional_constant_m4: values[3],
            shear_area_y_m2: values[4],
            shear_area_z_m2: values[5],
        },
        output_directory: PathBuf::from(&arguments[17]),
    })
}

fn parse_model_edit_truss_section(
    arguments: &[OsString],
) -> Result<ModelEditTrussSectionCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--section"
        || arguments[4] != "--area-m2"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-truss-section requires MODEL.json --section ID --area-m2 A --output-dir DIR",
        ));
    }
    let area_m2 = parse_finite_edit_number(
        &arguments[5],
        "model-edit-truss-section cross-sectional area",
    )?;
    if area_m2 <= 0.0 {
        return Err(usage_error(
            "model-edit-truss-section area must be a finite SI number greater than zero",
        ));
    }
    Ok(ModelEditTrussSectionCommand {
        model: PathBuf::from(&arguments[1]),
        section_id: parse_bounded_edit_id(&arguments[3], "model-edit-truss-section section ID")?,
        parameters: TrussSectionParametersV1 { area_m2 },
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_edit_frame_element_orientation(
    arguments: &[OsString],
) -> Result<ModelEditFrameElementOrientationCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--element"
        || arguments[4] != "--rotation-rad"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-frame-element-orientation requires MODEL.json --element ID --rotation-rad VALUE --output-dir DIR",
        ));
    }
    Ok(ModelEditFrameElementOrientationCommand {
        model: PathBuf::from(&arguments[1]),
        element_id: parse_bounded_edit_id(
            &arguments[3],
            "model-edit-frame-element-orientation element ID",
        )?,
        local_axis_rotation_rad: parse_finite_edit_number(
            &arguments[5],
            "model-edit-frame-element-orientation rotation",
        )?,
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_edit_frame_element_properties(
    arguments: &[OsString],
) -> Result<ModelEditFrameElementPropertiesCommand, WorkbenchError> {
    if arguments.len() != 10
        || arguments[2] != "--element"
        || arguments[4] != "--material"
        || arguments[6] != "--section"
        || arguments[8] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-frame-element-properties requires MODEL.json --element ID --material ID --section ID --output-dir DIR",
        ));
    }
    Ok(ModelEditFrameElementPropertiesCommand {
        model: PathBuf::from(&arguments[1]),
        element_id: parse_bounded_edit_id(
            &arguments[3],
            "model-edit-frame-element-properties element ID",
        )?,
        material_id: parse_bounded_edit_id(
            &arguments[5],
            "model-edit-frame-element-properties material ID",
        )?,
        section_id: parse_bounded_edit_id(
            &arguments[7],
            "model-edit-frame-element-properties section ID",
        )?,
        output_directory: PathBuf::from(&arguments[9]),
    })
}

fn parse_model_edit_truss_element_properties(
    arguments: &[OsString],
) -> Result<ModelEditTrussElementPropertiesCommand, WorkbenchError> {
    if arguments.len() != 10
        || arguments[2] != "--element"
        || arguments[4] != "--material"
        || arguments[6] != "--section"
        || arguments[8] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-truss-element-properties requires MODEL.json --element ID --material ID --section ID --output-dir DIR",
        ));
    }
    Ok(ModelEditTrussElementPropertiesCommand {
        model: PathBuf::from(&arguments[1]),
        element_id: parse_bounded_edit_id(
            &arguments[3],
            "model-edit-truss-element-properties element ID",
        )?,
        material_id: parse_bounded_edit_id(
            &arguments[5],
            "model-edit-truss-element-properties material ID",
        )?,
        section_id: parse_bounded_edit_id(
            &arguments[7],
            "model-edit-truss-element-properties section ID",
        )?,
        output_directory: PathBuf::from(&arguments[9]),
    })
}

fn parse_model_edit_element_connectivity(
    arguments: &[OsString],
) -> Result<ModelEditElementConnectivityCommand, WorkbenchError> {
    if arguments.len() != 9
        || arguments[2] != "--element"
        || arguments[4] != "--nodes"
        || arguments[7] != "--output-dir"
    {
        return Err(usage_error(
            "model-edit-element-connectivity requires MODEL.json --element ID --nodes I J --output-dir DIR",
        ));
    }
    let node_ids = [
        parse_bounded_edit_id(&arguments[5], "model-edit-element-connectivity i-node ID")?,
        parse_bounded_edit_id(&arguments[6], "model-edit-element-connectivity j-node ID")?,
    ];
    if node_ids[0] == node_ids[1] {
        return Err(usage_error(
            "model-edit-element-connectivity requires two distinct endpoint node IDs",
        ));
    }
    Ok(ModelEditElementConnectivityCommand {
        model: PathBuf::from(&arguments[1]),
        element_id: parse_bounded_edit_id(
            &arguments[3],
            "model-edit-element-connectivity element ID",
        )?,
        node_ids,
        output_directory: PathBuf::from(&arguments[8]),
    })
}

fn parse_model_add_frame3d_member(
    arguments: &[OsString],
) -> Result<ModelAddFrame3dMemberCommand, WorkbenchError> {
    if arguments.len() != 18
        || arguments[2] != "--node"
        || arguments[4] != "--coordinates"
        || arguments[8] != "--element"
        || arguments[10] != "--from-node"
        || arguments[12] != "--material"
        || arguments[14] != "--section"
        || arguments[16] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-frame3d-member requires MODEL.json --node NEW-ID --coordinates X Y Z --element NEW-ID --from-node EXISTING-ID --material ID --section ID --output-dir DIR",
        ));
    }
    let mut coordinates_m = [0.0; 3];
    for (target, source) in coordinates_m.iter_mut().zip(&arguments[5..8]) {
        *target = parse_finite_edit_number(source, "model-add-frame3d-member coordinate")?;
    }
    let node_id = parse_bounded_edit_id(&arguments[3], "model-add-frame3d-member node ID")?;
    let from_node_id =
        parse_bounded_edit_id(&arguments[11], "model-add-frame3d-member existing node ID")?;
    if node_id == from_node_id {
        return Err(usage_error(
            "model-add-frame3d-member new and existing node IDs must differ",
        ));
    }
    Ok(ModelAddFrame3dMemberCommand {
        model: PathBuf::from(&arguments[1]),
        node_id,
        coordinates_m,
        element_id: parse_bounded_edit_id(&arguments[9], "model-add-frame3d-member element ID")?,
        from_node_id,
        material_id: parse_bounded_edit_id(&arguments[13], "model-add-frame3d-member material ID")?,
        section_id: parse_bounded_edit_id(&arguments[15], "model-add-frame3d-member section ID")?,
        output_directory: PathBuf::from(&arguments[17]),
    })
}

fn parse_model_add_truss3d_member(
    arguments: &[OsString],
) -> Result<ModelAddTruss3dMemberCommand, WorkbenchError> {
    if arguments.len() != 18
        || arguments[2] != "--node"
        || arguments[4] != "--coordinates"
        || arguments[8] != "--element"
        || arguments[10] != "--from-node"
        || arguments[12] != "--material"
        || arguments[14] != "--section"
        || arguments[16] != "--output-dir"
    {
        return Err(usage_error(
            "model-add-truss3d-member requires MODEL.json --node NEW-ID --coordinates X Y Z --element NEW-ID --from-node EXISTING-ID --material ID --section ID --output-dir DIR",
        ));
    }
    let mut coordinates_m = [0.0; 3];
    for (target, source) in coordinates_m.iter_mut().zip(&arguments[5..8]) {
        *target = parse_finite_edit_number(source, "model-add-truss3d-member coordinate")?;
    }
    let node_id = parse_bounded_edit_id(&arguments[3], "model-add-truss3d-member node ID")?;
    let from_node_id =
        parse_bounded_edit_id(&arguments[11], "model-add-truss3d-member existing node ID")?;
    if node_id == from_node_id {
        return Err(usage_error(
            "model-add-truss3d-member new and existing node IDs must differ",
        ));
    }
    Ok(ModelAddTruss3dMemberCommand {
        model: PathBuf::from(&arguments[1]),
        node_id,
        coordinates_m,
        element_id: parse_bounded_edit_id(&arguments[9], "model-add-truss3d-member element ID")?,
        from_node_id,
        material_id: parse_bounded_edit_id(&arguments[13], "model-add-truss3d-member material ID")?,
        section_id: parse_bounded_edit_id(&arguments[15], "model-add-truss3d-member section ID")?,
        output_directory: PathBuf::from(&arguments[17]),
    })
}

fn parse_model_delete_frame3d_leaf_member(
    arguments: &[OsString],
) -> Result<ModelDeleteFrame3dLeafMemberCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--element"
        || arguments[4] != "--node"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-delete-frame3d-leaf-member requires MODEL.json --element ID --node ID --output-dir DIR",
        ));
    }
    let element_id =
        parse_bounded_edit_id(&arguments[3], "model-delete-frame3d-leaf-member element ID")?;
    let node_id = parse_bounded_edit_id(&arguments[5], "model-delete-frame3d-leaf-member node ID")?;
    if element_id == node_id {
        return Err(usage_error(
            "model-delete-frame3d-leaf-member element and node IDs must differ",
        ));
    }
    Ok(ModelDeleteFrame3dLeafMemberCommand {
        model: PathBuf::from(&arguments[1]),
        element_id,
        node_id,
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_delete_truss3d_leaf_member(
    arguments: &[OsString],
) -> Result<ModelDeleteTruss3dLeafMemberCommand, WorkbenchError> {
    if arguments.len() != 8
        || arguments[2] != "--element"
        || arguments[4] != "--node"
        || arguments[6] != "--output-dir"
    {
        return Err(usage_error(
            "model-delete-truss3d-leaf-member requires MODEL.json --element ID --node ID --output-dir DIR",
        ));
    }
    let element_id =
        parse_bounded_edit_id(&arguments[3], "model-delete-truss3d-leaf-member element ID")?;
    let node_id = parse_bounded_edit_id(&arguments[5], "model-delete-truss3d-leaf-member node ID")?;
    if element_id == node_id {
        return Err(usage_error(
            "model-delete-truss3d-leaf-member element and node IDs must differ",
        ));
    }
    Ok(ModelDeleteTruss3dLeafMemberCommand {
        model: PathBuf::from(&arguments[1]),
        element_id,
        node_id,
        output_directory: PathBuf::from(&arguments[7]),
    })
}

fn parse_model_create_linear_analysis_request(
    arguments: &[OsString],
) -> Result<ModelCreateLinearAnalysisRequestCommand, WorkbenchError> {
    if arguments.len() != 16
        || arguments[2] != "--case"
        || arguments[4] != "--load-pattern"
        || arguments[6] != "--max-iterations"
        || arguments[8] != "--absolute-residual-tolerance"
        || arguments[10] != "--relative-residual-tolerance"
        || arguments[12] != "--maximum-increment"
        || arguments[14] != "--output-dir"
    {
        return Err(usage_error(
            "model-create-linear-analysis-request requires MODEL.json --case ID --load-pattern ID --max-iterations N --absolute-residual-tolerance VALUE --relative-residual-tolerance VALUE --maximum-increment VALUE --output-dir DIR",
        ));
    }
    let max_iterations = arguments[7]
        .to_str()
        .and_then(|value| value.parse::<u32>().ok())
        .filter(|value| (1..=1_000_000).contains(value))
        .ok_or_else(|| usage_error("max iterations must be an integer from 1 through 1000000"))?;
    let absolute_residual_tolerance = parse_finite_edit_number(
        &arguments[9],
        "model-create-linear-analysis-request absolute residual tolerance",
    )?;
    let relative_residual_tolerance = parse_finite_edit_number(
        &arguments[11],
        "model-create-linear-analysis-request relative residual tolerance",
    )?;
    let maximum_increment = parse_finite_edit_number(
        &arguments[13],
        "model-create-linear-analysis-request maximum increment",
    )?;
    if absolute_residual_tolerance < 0.0
        || relative_residual_tolerance < 0.0
        || (absolute_residual_tolerance == 0.0 && relative_residual_tolerance == 0.0)
        || maximum_increment < 0.0
    {
        return Err(usage_error(
            "linear request tolerances must be nonnegative with at least one positive, and maximum increment must be nonnegative",
        ));
    }
    Ok(ModelCreateLinearAnalysisRequestCommand {
        model: PathBuf::from(&arguments[1]),
        case_id: parse_bounded_edit_id(
            &arguments[3],
            "model-create-linear-analysis-request case ID",
        )?,
        load_pattern_id: parse_bounded_edit_id(
            &arguments[5],
            "model-create-linear-analysis-request load-pattern ID",
        )?,
        config: SparseLinearConfigV1 {
            max_iterations,
            absolute_residual_tolerance,
            relative_residual_tolerance,
            maximum_increment,
        },
        output_directory: PathBuf::from(&arguments[15]),
    })
}

fn parse_bounded_edit_id(argument: &OsString, name: &str) -> Result<String, WorkbenchError> {
    argument
        .to_str()
        .filter(|value| !value.is_empty() && value.len() <= 128)
        .map(ToOwned::to_owned)
        .ok_or_else(|| usage_error(&format!("{name} must be valid UTF-8 with 1-128 bytes")))
}

fn parse_finite_edit_number(argument: &OsString, name: &str) -> Result<f64, WorkbenchError> {
    argument
        .to_str()
        .and_then(|value| value.parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .ok_or_else(|| usage_error(&format!("{name} must be a finite SI number")))
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

fn parse_result_view(arguments: &[OsString]) -> Result<ResultViewCommand, WorkbenchError> {
    let mut workspace = None;
    let mut locale = WorkbenchReportLocaleV1::EnUs;
    let mut locale_seen = false;
    let mut channel = WorkbenchResultChannelV1::TopDisplacement;
    let mut channel_seen = false;
    let mut start_step = 1;
    let mut start_seen = false;
    let mut count = WORKBENCH_RESULT_VIEW_DEFAULT_COUNT_V1;
    let mut count_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("result-view option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("result-view option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--locale" if !locale_seen => {
                locale_seen = true;
                locale = value
                    .to_str()
                    .and_then(WorkbenchReportLocaleV1::parse)
                    .ok_or_else(|| usage_error("result-view locale must be en-US or ko-KR"))?;
            }
            "--channel" if !channel_seen => {
                channel_seen = true;
                channel = value
                    .to_str()
                    .and_then(WorkbenchResultChannelV1::parse)
                    .ok_or_else(|| {
                        usage_error(
                            "result-view channel must be top-displacement, drift-ratio, base-shear or residual-inf",
                        )
                    })?;
            }
            "--start-step" if !start_seen => {
                start_seen = true;
                start_step = parse_u32(value, "result-view start step")?;
                if start_step == 0 {
                    return Err(usage_error("result-view start step must be at least 1"));
                }
            }
            "--count" if !count_seen => {
                count_seen = true;
                count = parse_u32(value, "result-view count")?;
                if count == 0 || count > WORKBENCH_RESULT_VIEW_MAX_COUNT_V1 {
                    return Err(usage_error("result-view count must be in 1..=256"));
                }
            }
            _ => return Err(usage_error("duplicate or unknown result-view option")),
        }
        index += 2;
    }
    Ok(ResultViewCommand {
        workspace: workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        locale,
        channel,
        start_step,
        count,
    })
}

fn parse_deformed_view(arguments: &[OsString]) -> Result<DeformedViewCommand, WorkbenchError> {
    let mut workspace = None;
    let mut locale = WorkbenchReportLocaleV1::EnUs;
    let mut locale_seen = false;
    let mut projection = ModelTopologyProjectionV1::Isometric;
    let mut projection_seen = false;
    let mut step = None;
    let mut scale = WORKBENCH_DEFORMED_VIEW_DEFAULT_SCALE_V1;
    let mut scale_seen = false;
    let mut index = 1;
    while index < arguments.len() {
        if index + 1 >= arguments.len() {
            return Err(usage_error("result-deformed-view option has no value"));
        }
        let flag = arguments[index]
            .to_str()
            .ok_or_else(|| usage_error("result-deformed-view option names must be valid UTF-8"))?;
        let value = &arguments[index + 1];
        match flag {
            "--workspace" if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            "--locale" if !locale_seen => {
                locale_seen = true;
                locale = value
                    .to_str()
                    .and_then(WorkbenchReportLocaleV1::parse)
                    .ok_or_else(|| {
                        usage_error("result-deformed-view locale must be en-US or ko-KR")
                    })?;
            }
            "--projection" if !projection_seen => {
                projection_seen = true;
                projection = value
                    .to_str()
                    .and_then(ModelTopologyProjectionV1::parse)
                    .ok_or_else(|| {
                        usage_error(
                            "result-deformed-view projection must be isometric, xy, xz or yz",
                        )
                    })?;
            }
            "--step" if step.is_none() => {
                let parsed = parse_u32(value, "result-deformed-view step")?;
                if parsed == 0 {
                    return Err(usage_error("result-deformed-view step must be at least 1"));
                }
                step = Some(parsed);
            }
            "--scale" if !scale_seen => {
                scale_seen = true;
                scale = value
                    .to_str()
                    .and_then(|text| text.parse::<f64>().ok())
                    .filter(|value| {
                        value.is_finite()
                            && *value > 0.0
                            && *value <= WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1
                    })
                    .ok_or_else(|| {
                        usage_error("result-deformed-view scale must be finite and in (0, 1000000]")
                    })?;
            }
            _ => {
                return Err(usage_error(
                    "duplicate or unknown result-deformed-view option",
                ))
            }
        }
        index += 2;
    }
    Ok(DeformedViewCommand {
        workspace: workspace.ok_or_else(|| usage_error("--workspace is required"))?,
        locale,
        projection,
        step,
        scale,
    })
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
        "usage:\n  structural-workbench model-view <MODEL.json> [--locale <en-US|ko-KR>] [--projection <isometric|xy|xz|yz>]\n  structural-workbench model-edit-node <MODEL.json> --node <ID> --coordinates <X> <Y> <Z> --output-dir <DIR>\n  structural-workbench model-add-node <MODEL.json> --node <NEW-ID> --coordinates <X> <Y> <Z> --output-dir <DIR>\n  structural-workbench model-delete-orphan-node <MODEL.json> --node <ID> --output-dir <DIR>\n  structural-workbench model-edit-nodal-load <MODEL.json> --load-pattern <PATTERN-ID> --load <LOAD-ID> --components <FX> <FY> <FZ> <MX> <MY> <MZ> --output-dir <DIR>\n  structural-workbench model-add-nodal-load <MODEL.json> --load-pattern <PATTERN-ID> --load <NEW-LOAD-ID> --node <EXISTING-NODE-ID> --components <FX> <FY> <FZ> <MX> <MY> <MZ> --output-dir <DIR>\n  structural-workbench model-delete-nodal-load <MODEL.json> --load-pattern <PATTERN-ID> --load <LOAD-ID> --output-dir <DIR>\n  structural-workbench import <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench import-mgt <SOURCE.mgt> <MGT-MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench validate --workspace <DIR>\n  structural-workbench run --workspace <DIR> [--step-budget <N>]\n  structural-workbench resume --workspace <DIR> [--step-budget <N>]\n  structural-workbench compare --workspace <DIR> [--require-pass]\n  structural-workbench report --workspace <DIR>\n  structural-workbench report-view --workspace <DIR> [--locale <en-US|ko-KR>]\n  structural-workbench result-view --workspace <DIR> [--locale <en-US|ko-KR>] [--channel <top-displacement|drift-ratio|base-shear|residual-inf>] [--start-step <N>] [--count <1..256>]\n  structural-workbench result-deformed-view --workspace <DIR> [--locale <en-US|ko-KR>] [--projection <isometric|xy|xz|yz>] [--step <N>] [--scale <F64>]\n  structural-workbench status --workspace <DIR>\n  structural-workbench inspect --workspace <DIR>\n  structural-workbench review --workspace <DIR> --decision <pass|review|fail> --reviewer <NAME> [--comment <TEXT>]\n  structural-workbench review-show --workspace <DIR>\n  structural-workbench export --workspace <DIR>\n  structural-workbench catalog [--truth <CLASS|all>] [--size <CLASS|all>] [--lifecycle <STATE|first-targets|all>] [--query <TEXT>]\n  structural-workbench catalog-show --case <ID>\n  structural-workbench evidence --bundle <DIR> [--as-of-unix <SECONDS>]\n  structural-workbench evidence-show --bundle <DIR> --artifact <ID> [--as-of-unix <SECONDS>]\n  structural-workbench interactive --workspace <DIR>\n  structural-workbench workflow <MODEL.json> <MODEL-REQUEST.json> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]\n  structural-workbench workflow-mgt <SOURCE.mgt> <MGT-MODEL-REQUEST.json> --model-id <ID> --external-result <EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]",
        "\n  structural-workbench model-add-fixed-constraint <MODEL.json> --constraint <NEW-ID> --node <EXISTING-NODE-ID> --output-dir <DIR>\n  structural-workbench model-add-linear-load-pattern <MODEL.json> --load-pattern <NEW-PATTERN-ID> --load <NEW-LOAD-ID> --node <EXISTING-NODE-ID> --components <FX> <FY> <FZ> <MX> <MY> <MZ> --output-dir <DIR>\n  structural-workbench model-add-linear-material <MODEL.json> --material <NEW-ID> --elastic-modulus-pa <E> --poisson-ratio <NU> --density-kg-m3 <RHO> --output-dir <DIR>\n  structural-workbench model-add-frame-section <MODEL.json> --section <NEW-ID> --area-m2 <A> --iy-m4 <IY> --iz-m4 <IZ> --torsional-constant-m4 <J> --shear-area-y-m2 <AY> --shear-area-z-m2 <AZ> --output-dir <DIR>\n  structural-workbench model-add-truss-section <MODEL.json> --section <NEW-ID> --area-m2 <A> --output-dir <DIR>\n  structural-workbench model-edit-constraint-value <MODEL.json> --constraint <ID> --dof <UX|UY|UZ|RX|RY|RZ> --value <SI-VALUE> --output-dir <DIR>\n  structural-workbench model-edit-linear-material <MODEL.json> --material <ID> --elastic-modulus-pa <E> --poisson-ratio <NU> --density-kg-m3 <RHO> --output-dir <DIR>\n  structural-workbench model-edit-frame-section <MODEL.json> --section <ID> --area-m2 <A> --iy-m4 <IY> --iz-m4 <IZ> --torsional-constant-m4 <J> --shear-area-y-m2 <AY> --shear-area-z-m2 <AZ> --output-dir <DIR>\n  structural-workbench model-edit-frame-element-orientation <MODEL.json> --element <ID> --rotation-rad <VALUE> --output-dir <DIR>\n  structural-workbench model-edit-frame-element-properties <MODEL.json> --element <ID> --material <ID> --section <ID> --output-dir <DIR>\n  structural-workbench model-edit-element-connectivity <MODEL.json> --element <ID> --nodes <I> <J> --output-dir <DIR>\n  structural-workbench model-add-frame3d-member <MODEL.json> --node <NEW-ID> --coordinates <X> <Y> <Z> --element <NEW-ID> --from-node <EXISTING-ID> --material <ID> --section <ID> --output-dir <DIR>\n  structural-workbench model-add-truss3d-member <MODEL.json> --node <NEW-ID> --coordinates <X> <Y> <Z> --element <NEW-ID> --from-node <EXISTING-ID> --material <ID> --section <ID> --output-dir <DIR>\n  structural-workbench model-create-linear-analysis-request <MODEL.json> --case <ID> --load-pattern <ID> --max-iterations <N> --absolute-residual-tolerance <VALUE> --relative-residual-tolerance <VALUE> --maximum-increment <VALUE> --output-dir <DIR>\n  structural-workbench import-model-linear <MODEL.json> <MODEL-LINEAR-REQUEST.json> --external-result <LINEAR-EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench import-mgt-model-linear <SOURCE.mgt> <MODEL-LINEAR-REQUEST.json> --model-id <ID> --external-result <LINEAR-EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR>\n  structural-workbench workflow-model-linear <MODEL.json> <MODEL-LINEAR-REQUEST.json> --external-result <LINEAR-EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]\n  structural-workbench workflow-mgt-model-linear <SOURCE.mgt> <MODEL-LINEAR-REQUEST.json> --model-id <ID> --external-result <LINEAR-EXTERNAL.json> --source-artifact <FILE> [--executable-artifact <FILE>] --workspace <DIR> [--step-budget <N>]\n  structural-workbench report-export-pdf --workspace <DIR> --output-dir <DIR> [--locale <en-US|ko-KR>]"
        ,
        "\n  structural-workbench model-delete-fixed-constraint <MODEL.json> --constraint <ID> --output-dir <DIR>\n  structural-workbench model-edit-truss-section <MODEL.json> --section <ID> --area-m2 <A> --output-dir <DIR>\n  structural-workbench model-edit-truss-element-properties <MODEL.json> --element <ID> --material <ID> --section <ID> --output-dir <DIR>\n  structural-workbench model-delete-frame3d-leaf-member <MODEL.json> --element <ID> --node <ID> --output-dir <DIR>\n  structural-workbench model-delete-truss3d-leaf-member <MODEL.json> --element <ID> --node <ID> --output-dir <DIR>\n  structural-workbench model-delete-linear-load-pattern <MODEL.json> --load-pattern <ID> --output-dir <DIR>\n  structural-workbench model-delete-linear-material <MODEL.json> --material <ID> --output-dir <DIR>\n  structural-workbench model-delete-frame-section <MODEL.json> --section <ID> --output-dir <DIR>\n  structural-workbench model-delete-truss-section <MODEL.json> --section <ID> --output-dir <DIR>"
    )
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::path::PathBuf;

    use super::{
        parse_catalog, parse_catalog_show, parse_deformed_view, parse_evidence, parse_import,
        parse_model_add_fixed_constraint, parse_model_add_frame3d_member,
        parse_model_add_frame_section, parse_model_add_linear_load_pattern,
        parse_model_add_linear_material, parse_model_add_nodal_load, parse_model_add_node,
        parse_model_add_truss3d_member, parse_model_add_truss_section,
        parse_model_create_linear_analysis_request, parse_model_delete_fixed_constraint,
        parse_model_delete_frame3d_leaf_member, parse_model_delete_frame_section,
        parse_model_delete_linear_load_pattern, parse_model_delete_linear_material,
        parse_model_delete_nodal_load, parse_model_delete_orphan_node,
        parse_model_delete_truss3d_leaf_member, parse_model_delete_truss_section,
        parse_model_edit_constraint_value, parse_model_edit_element_connectivity,
        parse_model_edit_frame_element_orientation, parse_model_edit_frame_element_properties,
        parse_model_edit_frame_section, parse_model_edit_linear_material,
        parse_model_edit_nodal_load, parse_model_edit_node,
        parse_model_edit_truss_element_properties, parse_model_edit_truss_section,
        parse_model_view, parse_report_pdf_export, parse_report_view, parse_result_view,
        parse_review, parse_stage_command,
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
    fn model_view_parser_has_closed_locale_and_projection_options() {
        let default = [OsString::from("model-view"), OsString::from("model.json")];
        let parsed = parse_model_view(&default).expect("default model view");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.locale.label(), "en-US");
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

        let korean = [
            OsString::from("model-view"),
            OsString::from("model.json"),
            OsString::from("--projection"),
            OsString::from("yz"),
            OsString::from("--locale"),
            OsString::from("ko-KR"),
        ];
        let parsed = parse_model_view(&korean).expect("Korean YZ model view");
        assert_eq!(parsed.locale.label(), "ko-KR");
        assert_eq!(parsed.projection.label(), "yz");
        let mut invalid_locale = korean;
        invalid_locale[5] = OsString::from("ko-kr");
        assert!(parse_model_view(&invalid_locale).is_err());

        for invalid in [
            [
                OsString::from("model-view"),
                OsString::from("model.json"),
                OsString::from("--locale"),
                OsString::from("en-US"),
                OsString::from("--locale"),
                OsString::from("ko-KR"),
            ],
            [
                OsString::from("model-view"),
                OsString::from("model.json"),
                OsString::from("--format"),
                OsString::from("json"),
                OsString::from("--projection"),
                OsString::from("xy"),
            ],
        ] {
            assert!(parse_model_view(&invalid).is_err());
        }
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
    fn model_add_node_parser_requires_fixed_bounded_and_finite_inputs() {
        let arguments = [
            OsString::from("model-add-node"),
            OsString::from("model.json"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--coordinates"),
            OsString::from("2"),
            OsString::from("1.5"),
            OsString::from("-0.25"),
            OsString::from("--output-dir"),
            OsString::from("authored"),
        ];
        let parsed = parse_model_add_node(&arguments).expect("valid node-add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(
            parsed.coordinates_m.map(f64::to_bits),
            [2.0_f64, 1.5_f64, -0.25_f64].map(f64::to_bits)
        );
        assert_eq!(parsed.output_directory, PathBuf::from("authored"));

        let mut nonfinite = arguments.clone();
        nonfinite[6] = OsString::from("NaN");
        assert!(parse_model_add_node(&nonfinite).is_err());
        let mut empty_id = arguments;
        empty_id[3] = OsString::from("");
        assert!(parse_model_add_node(&empty_id).is_err());
    }

    #[test]
    fn model_delete_orphan_node_parser_requires_bounded_identity() {
        let arguments = [
            OsString::from("model-delete-orphan-node"),
            OsString::from("model.json"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_orphan_node(&arguments).expect("valid node-delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_id = arguments.clone();
        empty_id[3] = OsString::from("");
        assert!(parse_model_delete_orphan_node(&empty_id).is_err());
        let mut wrong_option = arguments;
        wrong_option[2] = OsString::from("--element");
        assert!(parse_model_delete_orphan_node(&wrong_option).is_err());
    }

    #[test]
    fn model_edit_nodal_load_parser_requires_fixed_finite_si_components() {
        let arguments = [
            OsString::from("model-edit-nodal-load"),
            OsString::from("model.json"),
            OsString::from("--load-pattern"),
            OsString::from("LC_WEAK"),
            OsString::from("--load"),
            OsString::from("L_WEAK_N2"),
            OsString::from("--components"),
            OsString::from("0"),
            OsString::from("-20000"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed =
            parse_model_edit_nodal_load(&arguments).expect("valid nodal-load edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.load_pattern_id, "LC_WEAK");
        assert_eq!(parsed.nodal_load_id, "L_WEAK_N2");
        assert_eq!(
            parsed.components_si.map(f64::to_bits),
            [0.0_f64, -20_000.0, 0.0, 0.0, 0.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        let mut invalid = arguments;
        invalid[8] = OsString::from("NaN");
        assert!(parse_model_edit_nodal_load(&invalid).is_err());
    }

    #[test]
    fn model_add_nodal_load_parser_requires_target_and_nonzero_finite_components() {
        let arguments = [
            OsString::from("model-add-nodal-load"),
            OsString::from("model.json"),
            OsString::from("--load-pattern"),
            OsString::from("LC_WEAK"),
            OsString::from("--load"),
            OsString::from("L_WEAK_N3"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--components"),
            OsString::from("0"),
            OsString::from("-1000"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_nodal_load(&arguments).expect("valid nodal-load add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.load_pattern_id, "LC_WEAK");
        assert_eq!(parsed.nodal_load_id, "L_WEAK_N3");
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(
            parsed.components_si.map(f64::to_bits),
            [0.0_f64, -1_000.0, 0.0, 0.0, 0.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut nonfinite = arguments.clone();
        nonfinite[10] = OsString::from("NaN");
        assert!(parse_model_add_nodal_load(&nonfinite).is_err());
        let mut all_zero = arguments;
        all_zero[10] = OsString::from("0");
        assert!(parse_model_add_nodal_load(&all_zero).is_err());
    }

    #[test]
    fn model_delete_nodal_load_parser_requires_bounded_pattern_and_load_ids() {
        let arguments = [
            OsString::from("model-delete-nodal-load"),
            OsString::from("model.json"),
            OsString::from("--load-pattern"),
            OsString::from("LC_WEAK"),
            OsString::from("--load"),
            OsString::from("L_WEAK_N3"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed =
            parse_model_delete_nodal_load(&arguments).expect("valid nodal-load delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.load_pattern_id, "LC_WEAK");
        assert_eq!(parsed.nodal_load_id, "L_WEAK_N3");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_pattern = arguments.clone();
        empty_pattern[3] = OsString::new();
        assert!(parse_model_delete_nodal_load(&empty_pattern).is_err());
        let mut empty_load = arguments;
        empty_load[5] = OsString::new();
        assert!(parse_model_delete_nodal_load(&empty_load).is_err());
    }

    #[test]
    fn model_add_fixed_constraint_parser_requires_bounded_constraint_and_node_ids() {
        let arguments = [
            OsString::from("model-add-fixed-constraint"),
            OsString::from("model.json"),
            OsString::from("--constraint"),
            OsString::from("BC_N3"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_fixed_constraint(&arguments)
            .expect("valid fixed-constraint add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.constraint_id, "BC_N3");
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut empty_constraint = arguments.clone();
        empty_constraint[3] = OsString::new();
        assert!(parse_model_add_fixed_constraint(&empty_constraint).is_err());
        let mut empty_node = arguments;
        empty_node[5] = OsString::new();
        assert!(parse_model_add_fixed_constraint(&empty_node).is_err());
    }

    #[test]
    fn model_delete_fixed_constraint_parser_requires_bounded_constraint_id() {
        let arguments = [
            OsString::from("model-delete-fixed-constraint"),
            OsString::from("model.json"),
            OsString::from("--constraint"),
            OsString::from("BC_N3"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_fixed_constraint(&arguments)
            .expect("valid fixed-constraint delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.constraint_id, "BC_N3");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_constraint = arguments;
        empty_constraint[3] = OsString::new();
        assert!(parse_model_delete_fixed_constraint(&empty_constraint).is_err());
    }

    #[test]
    fn model_add_linear_load_pattern_parser_requires_new_ids_target_and_nonzero_components() {
        let arguments = [
            OsString::from("model-add-linear-load-pattern"),
            OsString::from("model.json"),
            OsString::from("--load-pattern"),
            OsString::from("LC_CUSTOM"),
            OsString::from("--load"),
            OsString::from("L_CUSTOM_N2"),
            OsString::from("--node"),
            OsString::from("N2"),
            OsString::from("--components"),
            OsString::from("2500"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_linear_load_pattern(&arguments)
            .expect("valid linear-load-pattern add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.load_pattern_id, "LC_CUSTOM");
        assert_eq!(parsed.nodal_load_id, "L_CUSTOM_N2");
        assert_eq!(parsed.node_id, "N2");
        assert_eq!(
            parsed.components_si.map(f64::to_bits),
            [2_500.0_f64, 0.0, 0.0, 0.0, 0.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut nonfinite = arguments.clone();
        nonfinite[9] = OsString::from("NaN");
        assert!(parse_model_add_linear_load_pattern(&nonfinite).is_err());
        let mut all_zero = arguments;
        all_zero[9] = OsString::from("0");
        assert!(parse_model_add_linear_load_pattern(&all_zero).is_err());
    }

    #[test]
    fn model_delete_linear_load_pattern_parser_requires_bounded_pattern_id() {
        let arguments = [
            OsString::from("model-delete-linear-load-pattern"),
            OsString::from("model.json"),
            OsString::from("--load-pattern"),
            OsString::from("LC_CUSTOM"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_linear_load_pattern(&arguments)
            .expect("valid linear-load-pattern delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.load_pattern_id, "LC_CUSTOM");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_pattern = arguments;
        empty_pattern[3] = OsString::new();
        assert!(parse_model_delete_linear_load_pattern(&empty_pattern).is_err());
    }

    #[test]
    fn model_delete_linear_material_parser_requires_bounded_material_id() {
        let arguments = [
            OsString::from("model-delete-linear-material"),
            OsString::from("model.json"),
            OsString::from("--material"),
            OsString::from("M2"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_linear_material(&arguments)
            .expect("valid linear-material delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.material_id, "M2");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_material = arguments;
        empty_material[3] = OsString::new();
        assert!(parse_model_delete_linear_material(&empty_material).is_err());
    }

    #[test]
    fn model_delete_frame_section_parser_requires_bounded_section_id() {
        let arguments = [
            OsString::from("model-delete-frame-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("S2"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_frame_section(&arguments)
            .expect("valid frame-section delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "S2");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_section = arguments;
        empty_section[3] = OsString::new();
        assert!(parse_model_delete_frame_section(&empty_section).is_err());
    }

    #[test]
    fn model_add_linear_material_parser_requires_new_id_and_physical_parameters() {
        let arguments = [
            OsString::from("model-add-linear-material"),
            OsString::from("model.json"),
            OsString::from("--material"),
            OsString::from("M2"),
            OsString::from("--elastic-modulus-pa"),
            OsString::from("70000000000"),
            OsString::from("--poisson-ratio"),
            OsString::from("0.33"),
            OsString::from("--density-kg-m3"),
            OsString::from("2700"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed =
            parse_model_add_linear_material(&arguments).expect("valid linear-material add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.material_id, "M2");
        assert_eq!(
            parsed.parameters.elastic_modulus_pa.to_bits(),
            70_000_000_000.0_f64.to_bits()
        );
        assert_eq!(
            parsed.parameters.poisson_ratio.to_bits(),
            0.33_f64.to_bits()
        );
        assert_eq!(
            parsed.parameters.density_kg_m3.to_bits(),
            2_700.0_f64.to_bits()
        );
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut invalid_modulus = arguments.clone();
        invalid_modulus[5] = OsString::from("0");
        assert!(parse_model_add_linear_material(&invalid_modulus).is_err());
        let mut invalid_ratio = arguments.clone();
        invalid_ratio[7] = OsString::from("0.5");
        assert!(parse_model_add_linear_material(&invalid_ratio).is_err());
        let mut invalid_density = arguments;
        invalid_density[9] = OsString::from("-1");
        assert!(parse_model_add_linear_material(&invalid_density).is_err());
        let mut nonfinite = invalid_density;
        nonfinite[5] = OsString::from("NaN");
        nonfinite[9] = OsString::from("2700");
        assert!(parse_model_add_linear_material(&nonfinite).is_err());
    }

    #[test]
    fn model_add_frame_section_parser_requires_new_id_and_positive_finite_si_values() {
        let arguments = [
            OsString::from("model-add-frame-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("S2"),
            OsString::from("--area-m2"),
            OsString::from("0.01"),
            OsString::from("--iy-m4"),
            OsString::from("0.00004"),
            OsString::from("--iz-m4"),
            OsString::from("0.000025"),
            OsString::from("--torsional-constant-m4"),
            OsString::from("0.000005"),
            OsString::from("--shear-area-y-m2"),
            OsString::from("0.008"),
            OsString::from("--shear-area-z-m2"),
            OsString::from("0.008"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed =
            parse_model_add_frame_section(&arguments).expect("valid frame-section add command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "S2");
        assert_eq!(parsed.parameters.area_m2.to_bits(), 0.01_f64.to_bits());
        assert_eq!(
            parsed.parameters.torsional_constant_m4.to_bits(),
            0.000_005_f64.to_bits()
        );
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        for (index, value) in [(5, "0"), (7, "-1"), (15, "inf")] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::from(value);
            assert!(parse_model_add_frame_section(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_constraint_value_parser_has_closed_dof_and_finite_value() {
        let arguments = [
            OsString::from("model-edit-constraint-value"),
            OsString::from("model.json"),
            OsString::from("--constraint"),
            OsString::from("BC2"),
            OsString::from("--dof"),
            OsString::from("UY"),
            OsString::from("--value"),
            OsString::from("-0.0002"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_constraint_value(&arguments)
            .expect("valid constraint-value edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.constraint_id, "BC2");
        assert_eq!(parsed.dof, "UY");
        assert_eq!(parsed.value_si.to_bits(), (-0.0002_f64).to_bits());
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        let mut invalid_dof = arguments.clone();
        invalid_dof[5] = OsString::from("QX");
        assert!(parse_model_edit_constraint_value(&invalid_dof).is_err());
        let mut invalid_value = arguments;
        invalid_value[7] = OsString::from("inf");
        assert!(parse_model_edit_constraint_value(&invalid_value).is_err());
    }

    #[test]
    fn model_edit_linear_material_parser_has_closed_physical_ranges() {
        let arguments = [
            OsString::from("model-edit-linear-material"),
            OsString::from("model.json"),
            OsString::from("--material"),
            OsString::from("M1"),
            OsString::from("--elastic-modulus-pa"),
            OsString::from("210000000000"),
            OsString::from("--poisson-ratio"),
            OsString::from("0.29"),
            OsString::from("--density-kg-m3"),
            OsString::from("7850"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_linear_material(&arguments)
            .expect("valid linear-material edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.material_id, "M1");
        assert_eq!(
            parsed.parameters.elastic_modulus_pa.to_bits(),
            210_000_000_000.0_f64.to_bits()
        );
        assert_eq!(
            parsed.parameters.poisson_ratio.to_bits(),
            0.29_f64.to_bits()
        );
        assert_eq!(
            parsed.parameters.density_kg_m3.to_bits(),
            7850.0_f64.to_bits()
        );
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        for (index, value) in [(5, "0"), (7, "0.5"), (7, "-1"), (9, "-1"), (9, "NaN")] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::from(value);
            assert!(parse_model_edit_linear_material(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_frame_section_parser_requires_positive_finite_si_values() {
        let arguments = [
            OsString::from("model-edit-frame-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("S1"),
            OsString::from("--area-m2"),
            OsString::from("0.025"),
            OsString::from("--iy-m4"),
            OsString::from("0.00009"),
            OsString::from("--iz-m4"),
            OsString::from("0.00006"),
            OsString::from("--torsional-constant-m4"),
            OsString::from("0.000012"),
            OsString::from("--shear-area-y-m2"),
            OsString::from("0.02"),
            OsString::from("--shear-area-z-m2"),
            OsString::from("0.02"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed =
            parse_model_edit_frame_section(&arguments).expect("valid frame-section edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "S1");
        assert_eq!(parsed.parameters.area_m2.to_bits(), 0.025_f64.to_bits());
        assert_eq!(
            parsed.parameters.torsional_constant_m4.to_bits(),
            0.000_012_f64.to_bits()
        );
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        for (index, value) in [(5, "0"), (7, "-1"), (15, "inf")] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::from(value);
            assert!(parse_model_edit_frame_section(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_truss_section_parser_requires_positive_finite_area() {
        let arguments = [
            OsString::from("model-edit-truss-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("T1"),
            OsString::from("--area-m2"),
            OsString::from("0.0075"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_truss_section(&arguments)
            .expect("valid bounded truss-section edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "T1");
        assert_eq!(parsed.parameters.area_m2.to_bits(), 0.0075_f64.to_bits());
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        for value in ["0", "-1", "NaN"] {
            let mut invalid = arguments.clone();
            invalid[5] = OsString::from(value);
            assert!(parse_model_edit_truss_section(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_frame_element_orientation_parser_requires_finite_radians() {
        let arguments = [
            OsString::from("model-edit-frame-element-orientation"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E1"),
            OsString::from("--rotation-rad"),
            OsString::from("0.25"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_frame_element_orientation(&arguments)
            .expect("valid frame-element orientation edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E1");
        assert_eq!(parsed.local_axis_rotation_rad.to_bits(), 0.25_f64.to_bits());
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        let mut invalid = arguments;
        invalid[5] = OsString::from("NaN");
        assert!(parse_model_edit_frame_element_orientation(&invalid).is_err());
    }

    #[test]
    fn model_edit_frame_element_properties_parser_requires_all_bounded_ids() {
        let arguments = [
            OsString::from("model-edit-frame-element-properties"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E1"),
            OsString::from("--material"),
            OsString::from("M2"),
            OsString::from("--section"),
            OsString::from("S2"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_frame_element_properties(&arguments)
            .expect("valid frame-element property edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E1");
        assert_eq!(parsed.material_id, "M2");
        assert_eq!(parsed.section_id, "S2");
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        for index in [3, 5, 7] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::new();
            assert!(parse_model_edit_frame_element_properties(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_truss_element_properties_parser_requires_all_bounded_ids() {
        let arguments = [
            OsString::from("model-edit-truss-element-properties"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E2"),
            OsString::from("--material"),
            OsString::from("M2"),
            OsString::from("--section"),
            OsString::from("T2"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_truss_element_properties(&arguments)
            .expect("valid truss-element property edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E2");
        assert_eq!(parsed.material_id, "M2");
        assert_eq!(parsed.section_id, "T2");
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        for index in [3, 5, 7] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::new();
            assert!(parse_model_edit_truss_element_properties(&invalid).is_err());
        }
    }

    #[test]
    fn model_edit_element_connectivity_parser_requires_distinct_bounded_ids() {
        let arguments = [
            OsString::from("model-edit-element-connectivity"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E1"),
            OsString::from("--nodes"),
            OsString::from("N1"),
            OsString::from("N3"),
            OsString::from("--output-dir"),
            OsString::from("edited"),
        ];
        let parsed = parse_model_edit_element_connectivity(&arguments)
            .expect("valid element-connectivity edit command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E1");
        assert_eq!(parsed.node_ids, ["N1", "N3"]);
        assert_eq!(parsed.output_directory, PathBuf::from("edited"));

        let mut identical = arguments.clone();
        identical[6] = OsString::from("N1");
        assert!(parse_model_edit_element_connectivity(&identical).is_err());

        let mut empty = arguments;
        empty[5] = OsString::new();
        assert!(parse_model_edit_element_connectivity(&empty).is_err());
    }

    #[test]
    fn model_add_frame3d_member_parser_is_fixed_bounded_and_finite() {
        let arguments = [
            OsString::from("model-add-frame3d-member"),
            OsString::from("model.json"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--coordinates"),
            OsString::from("4"),
            OsString::from("0"),
            OsString::from("0"),
            OsString::from("--element"),
            OsString::from("E2"),
            OsString::from("--from-node"),
            OsString::from("N2"),
            OsString::from("--material"),
            OsString::from("M1"),
            OsString::from("--section"),
            OsString::from("S1"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_frame3d_member(&arguments)
            .expect("valid bounded frame3d member addition command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(
            parsed.coordinates_m.map(f64::to_bits),
            [4.0, 0.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(parsed.element_id, "E2");
        assert_eq!(parsed.from_node_id, "N2");
        assert_eq!(parsed.material_id, "M1");
        assert_eq!(parsed.section_id, "S1");
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut nonfinite = arguments.clone();
        nonfinite[5] = OsString::from("NaN");
        assert!(parse_model_add_frame3d_member(&nonfinite).is_err());
        let mut identical_nodes = arguments.clone();
        identical_nodes[11] = OsString::from("N3");
        assert!(parse_model_add_frame3d_member(&identical_nodes).is_err());
        let mut empty_material = arguments;
        empty_material[13] = OsString::new();
        assert!(parse_model_add_frame3d_member(&empty_material).is_err());
    }

    #[test]
    fn model_add_truss_section_parser_requires_positive_finite_area() {
        let arguments = [
            OsString::from("model-add-truss-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("T1"),
            OsString::from("--area-m2"),
            OsString::from("0.005"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_truss_section(&arguments)
            .expect("valid bounded truss-section addition command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "T1");
        assert_eq!(parsed.parameters.area_m2.to_bits(), 0.005_f64.to_bits());
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        for value in ["0", "-1", "NaN"] {
            let mut invalid = arguments.clone();
            invalid[5] = OsString::from(value);
            assert!(parse_model_add_truss_section(&invalid).is_err());
        }
    }

    #[test]
    fn model_delete_truss_section_parser_requires_bounded_section_id() {
        let arguments = [
            OsString::from("model-delete-truss-section"),
            OsString::from("model.json"),
            OsString::from("--section"),
            OsString::from("T2"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_truss_section(&arguments)
            .expect("valid truss-section delete command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.section_id, "T2");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut empty_section = arguments;
        empty_section[3] = OsString::new();
        assert!(parse_model_delete_truss_section(&empty_section).is_err());
    }

    #[test]
    fn model_add_truss3d_member_parser_is_fixed_bounded_and_finite() {
        let arguments = [
            OsString::from("model-add-truss3d-member"),
            OsString::from("model.json"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--coordinates"),
            OsString::from("2"),
            OsString::from("1"),
            OsString::from("0"),
            OsString::from("--element"),
            OsString::from("E2"),
            OsString::from("--from-node"),
            OsString::from("N2"),
            OsString::from("--material"),
            OsString::from("M1"),
            OsString::from("--section"),
            OsString::from("T1"),
            OsString::from("--output-dir"),
            OsString::from("added"),
        ];
        let parsed = parse_model_add_truss3d_member(&arguments)
            .expect("valid bounded truss3d member addition command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(
            parsed.coordinates_m.map(f64::to_bits),
            [2.0, 1.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(parsed.element_id, "E2");
        assert_eq!(parsed.from_node_id, "N2");
        assert_eq!(parsed.material_id, "M1");
        assert_eq!(parsed.section_id, "T1");
        assert_eq!(parsed.output_directory, PathBuf::from("added"));

        let mut nonfinite = arguments.clone();
        nonfinite[6] = OsString::from("inf");
        assert!(parse_model_add_truss3d_member(&nonfinite).is_err());
        let mut identical_nodes = arguments.clone();
        identical_nodes[11] = OsString::from("N3");
        assert!(parse_model_add_truss3d_member(&identical_nodes).is_err());
        let mut empty_section = arguments;
        empty_section[15] = OsString::new();
        assert!(parse_model_add_truss3d_member(&empty_section).is_err());
    }

    #[test]
    fn model_delete_frame3d_leaf_member_parser_requires_distinct_bounded_ids() {
        let arguments = [
            OsString::from("model-delete-frame3d-leaf-member"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E2"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_frame3d_leaf_member(&arguments)
            .expect("valid bounded frame leaf deletion command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E2");
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut identical = arguments.clone();
        identical[5] = OsString::from("E2");
        assert!(parse_model_delete_frame3d_leaf_member(&identical).is_err());
        let mut empty = arguments;
        empty[3] = OsString::new();
        assert!(parse_model_delete_frame3d_leaf_member(&empty).is_err());
    }

    #[test]
    fn model_delete_truss3d_leaf_member_parser_requires_distinct_bounded_ids() {
        let arguments = [
            OsString::from("model-delete-truss3d-leaf-member"),
            OsString::from("model.json"),
            OsString::from("--element"),
            OsString::from("E2"),
            OsString::from("--node"),
            OsString::from("N3"),
            OsString::from("--output-dir"),
            OsString::from("deleted"),
        ];
        let parsed = parse_model_delete_truss3d_leaf_member(&arguments)
            .expect("valid bounded truss leaf deletion command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.element_id, "E2");
        assert_eq!(parsed.node_id, "N3");
        assert_eq!(parsed.output_directory, PathBuf::from("deleted"));

        let mut identical = arguments.clone();
        identical[5] = OsString::from("E2");
        assert!(parse_model_delete_truss3d_leaf_member(&identical).is_err());
        let mut empty = arguments;
        empty[3] = OsString::new();
        assert!(parse_model_delete_truss3d_leaf_member(&empty).is_err());
    }

    #[test]
    fn model_create_linear_request_parser_enforces_bounded_pcg_controls() {
        let arguments = [
            OsString::from("model-create-linear-analysis-request"),
            OsString::from("model.json"),
            OsString::from("--case"),
            OsString::from("case-1"),
            OsString::from("--load-pattern"),
            OsString::from("LC1"),
            OsString::from("--max-iterations"),
            OsString::from("100"),
            OsString::from("--absolute-residual-tolerance"),
            OsString::from("1e-11"),
            OsString::from("--relative-residual-tolerance"),
            OsString::from("1e-13"),
            OsString::from("--maximum-increment"),
            OsString::from("0"),
            OsString::from("--output-dir"),
            OsString::from("request"),
        ];
        let parsed = parse_model_create_linear_analysis_request(&arguments)
            .expect("valid ModelIR linear request creation command");
        assert_eq!(parsed.model, PathBuf::from("model.json"));
        assert_eq!(parsed.case_id, "case-1");
        assert_eq!(parsed.load_pattern_id, "LC1");
        assert_eq!(parsed.config.max_iterations, 100);
        assert_eq!(
            parsed.config.absolute_residual_tolerance.to_bits(),
            1.0e-11_f64.to_bits()
        );
        assert_eq!(parsed.output_directory, PathBuf::from("request"));

        for (index, value) in [(7, "0"), (9, "-1"), (11, "NaN"), (13, "-1")] {
            let mut invalid = arguments.clone();
            invalid[index] = OsString::from(value);
            assert!(parse_model_create_linear_analysis_request(&invalid).is_err());
        }
        let mut zero_tolerances = arguments;
        zero_tolerances[9] = OsString::from("0");
        zero_tolerances[11] = OsString::from("0");
        assert!(parse_model_create_linear_analysis_request(&zero_tolerances).is_err());
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
    fn result_view_parser_has_bounded_closed_channel_and_window_options() {
        let default = [
            OsString::from("result-view"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_result_view(&default).expect("default result view");
        assert_eq!(parsed.workspace, PathBuf::from("session"));
        assert_eq!(parsed.locale.label(), "en-US");
        assert_eq!(parsed.channel.label(), "top-displacement");
        assert_eq!(parsed.start_step, 1);
        assert_eq!(parsed.count, 64);

        let window = [
            OsString::from("result-view"),
            OsString::from("--count"),
            OsString::from("2"),
            OsString::from("--channel"),
            OsString::from("base-shear"),
            OsString::from("--start-step"),
            OsString::from("3"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_result_view(&window).expect("explicit result window");
        assert_eq!(parsed.channel.label(), "base-shear");
        assert_eq!(parsed.start_step, 3);
        assert_eq!(parsed.count, 2);

        let korean = [
            OsString::from("result-view"),
            OsString::from("--workspace"),
            OsString::from("session"),
            OsString::from("--locale"),
            OsString::from("ko-KR"),
        ];
        assert_eq!(
            parse_result_view(&korean)
                .expect("Korean result view")
                .locale
                .label(),
            "ko-KR"
        );
        let mut invalid_locale = korean;
        invalid_locale[4] = OsString::from("ko-kr");
        assert!(parse_result_view(&invalid_locale).is_err());

        for (index, invalid_value) in [(2, "257"), (4, "energy"), (6, "0")] {
            let mut invalid = window.clone();
            invalid[index] = OsString::from(invalid_value);
            assert!(parse_result_view(&invalid).is_err());
        }
    }

    #[test]
    fn deformed_view_parser_has_closed_projection_step_and_scale_options() {
        let default = [
            OsString::from("result-deformed-view"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_deformed_view(&default).expect("default deformed view");
        assert_eq!(parsed.workspace, PathBuf::from("session"));
        assert_eq!(parsed.locale.label(), "en-US");
        assert_eq!(parsed.projection.label(), "isometric");
        assert_eq!(parsed.step, None);
        assert_eq!(parsed.scale.to_bits(), 1_000.0_f64.to_bits());

        let explicit = [
            OsString::from("result-deformed-view"),
            OsString::from("--scale"),
            OsString::from("25.5"),
            OsString::from("--step"),
            OsString::from("3"),
            OsString::from("--projection"),
            OsString::from("xz"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        let parsed = parse_deformed_view(&explicit).expect("explicit deformed view");
        assert_eq!(parsed.projection.label(), "xz");
        assert_eq!(parsed.step, Some(3));
        assert_eq!(parsed.scale.to_bits(), 25.5_f64.to_bits());

        let korean = [
            OsString::from("result-deformed-view"),
            OsString::from("--locale"),
            OsString::from("ko-KR"),
            OsString::from("--workspace"),
            OsString::from("session"),
        ];
        assert_eq!(
            parse_deformed_view(&korean)
                .expect("Korean deformed view")
                .locale
                .label(),
            "ko-KR"
        );
        let mut invalid_locale = korean;
        invalid_locale[2] = OsString::from("ko-kr");
        assert!(parse_deformed_view(&invalid_locale).is_err());

        for (index, invalid_value) in [(2, "NaN"), (4, "0"), (6, "perspective")] {
            let mut invalid = explicit.clone();
            invalid[index] = OsString::from(invalid_value);
            assert!(parse_deformed_view(&invalid).is_err());
        }
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
