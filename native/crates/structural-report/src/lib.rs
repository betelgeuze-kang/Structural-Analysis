//! Deterministic presentation projection for bounded native linear `Frame3D` results.

#![forbid(unsafe_code)]

use std::fmt::{self, Write as FmtWrite};
use std::io::Write as IoWrite;
use std::path::Path;

use serde_json::json;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::report_ir::{
    create_linear_frame3d_report_ir_v1, sha256_bytes_identity,
    validate_linear_frame3d_report_ir_v1, Frame3dReportExtremumV1, Frame3dReportSummaryV1,
    LinearFrame3dReportIrInput, LinearFrame3dReportIrV1,
};
use structural_contracts::result_ir::{
    validate_linear_frame3d_result_ir_v1, LinearFrame3dResultIrV1,
};

const DISPLACEMENT_COMPONENTS: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];
const FORCE_COMPONENTS: [&str; 6] = ["FX", "FY", "FZ", "MX", "MY", "MZ"];

/// Stable report projection failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Frame3dReportError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for Frame3dReportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for Frame3dReportError {}

/// Hash-bound `ReportIR` plus its deterministic standalone HTML projection.
#[derive(Clone, Debug, PartialEq)]
pub struct Frame3dReportBundle {
    pub report_ir: LinearFrame3dReportIrV1,
    pub html: String,
    pub html_hash: String,
}

/// Build a deterministic report from one already validated bounded native result.
///
/// The projection does not infer convergence, comparison, design or release authority.
/// Ties are resolved by source entity order and then canonical component order.
///
/// # Errors
///
/// Rejects an invalid/stale source result, invalid report identity, projection contract drift or
/// an in-memory formatting failure.
pub fn build_linear_frame3d_report(
    source: &LinearFrame3dResultIrV1,
    report_id: &str,
) -> Result<Frame3dReportBundle, Frame3dReportError> {
    let projected = project_report_ir(source, report_id)?;
    let html = render_html(source, &projected)?;
    let html_hash = sha256_bytes_identity(html.as_bytes());
    Ok(Frame3dReportBundle {
        report_ir: projected,
        html,
        html_hash,
    })
}

/// Publish one complete no-overwrite ModelIR/ResultIR/ReportIR/HTML Workbench directory.
///
/// `manifest.json` is synchronized last. Its absence therefore remains the fail-closed marker for
/// a partial publication. This is an artifact handoff, not a durable analysis-job claim.
///
/// # Errors
///
/// Rejects stale model/result bindings, existing output directories, serialization failures and
/// incomplete filesystem writes.
pub fn publish_linear_frame3d_workbench_bundle(
    output_dir: &Path,
    model_bytes: &[u8],
    result: &LinearFrame3dResultIrV1,
    report: &Frame3dReportBundle,
) -> Result<String, Frame3dReportError> {
    let model = parse_model_ir_v2(model_bytes).map_err(|_| {
        error(
            "bundle_model_serialization_failed",
            "/model",
            "Canonical ModelIR could not be reconstructed for Workbench publication",
        )
    })?;
    let model_json = model.canonical_bytes();
    if model.content_hash() != result.bindings.model_content_hash {
        return Err(error(
            "bundle_model_binding_mismatch",
            "/model",
            "Canonical ModelIR identity does not match the ResultIR model binding",
        ));
    }
    let result_json = result.canonical_json().map_err(|item| {
        error(
            "bundle_result_serialization_failed",
            &item.path,
            &item.detail,
        )
    })?;
    let report_json = report.report_ir.canonical_json().map_err(contract_error)?;
    std::fs::create_dir(output_dir).map_err(|item| {
        if item.kind() == std::io::ErrorKind::AlreadyExists {
            error(
                "bundle_output_exists",
                "/output_dir",
                "Workbench bundle output directory already exists; overwrite is forbidden",
            )
        } else {
            error(
                "bundle_output_create_failed",
                "/output_dir",
                "Workbench bundle output directory could not be created",
            )
        }
    })?;

    write_new_file(&output_dir.join("model-ir.json"), model_json)?;
    write_new_file(&output_dir.join("result-ir.json"), result_json.as_bytes())?;
    write_new_file(&output_dir.join("report-ir.json"), report_json.as_bytes())?;
    write_new_file(&output_dir.join("report.html"), report.html.as_bytes())?;

    let manifest_value = json!({
        "schema_version": "structural-native-linear-frame3d-workbench-bundle.v1",
        "status": "complete",
        "artifacts": {
            "model_ir": artifact("model-ir.json", "application/json", model_json),
            "result_ir": artifact("result-ir.json", "application/json", result_json.as_bytes()),
            "report_ir": artifact("report-ir.json", "application/json", report_json.as_bytes()),
            "html": artifact("report.html", "text/html", report.html.as_bytes()),
        },
        "bindings": {
            "model_content_hash": result.bindings.model_content_hash,
            "result_id": result.result_id,
            "result_hash": result.result_hash,
            "report_id": report.report_ir.report_id,
            "report_hash": report.report_ir.report_hash,
        },
        "claim_boundary": "completed_no_overwrite_cli_artifact_bundle_not_job_or_workbench_execution_authority",
    });
    let manifest = canonicalize_model_ir_v2(&manifest_value).map_err(|_| {
        error(
            "bundle_manifest_serialization_failed",
            "/manifest",
            "Workbench bundle manifest could not be serialized",
        )
    })?;
    write_new_file(&output_dir.join("manifest.json"), manifest.as_bytes())?;
    Ok(manifest)
}

fn artifact(path: &str, media_type: &str, bytes: &[u8]) -> serde_json::Value {
    json!({
        "path": path,
        "media_type": media_type,
        "content_hash": sha256_bytes_identity(bytes),
        "byte_length": bytes.len(),
    })
}

fn write_new_file(path: &Path, bytes: &[u8]) -> Result<(), Frame3dReportError> {
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| {
            error(
                "bundle_artifact_create_failed",
                "/output_dir",
                "Workbench bundle artifact could not be created without overwrite",
            )
        })?;
    file.write_all(bytes).map_err(|_| {
        error(
            "bundle_artifact_write_failed",
            "/output_dir",
            "Workbench bundle artifact could not be written completely",
        )
    })?;
    file.sync_all().map_err(|_| {
        error(
            "bundle_artifact_sync_failed",
            "/output_dir",
            "Workbench bundle artifact could not be synchronized",
        )
    })
}

/// Verify that a parsed `ReportIR` is the exact deterministic projection of a source `ResultIR`.
///
/// # Errors
///
/// Rejects invalid contracts, source identity transplantation or any summary/extremum drift.
pub fn validate_linear_frame3d_report_source(
    report: &LinearFrame3dReportIrV1,
    source: &LinearFrame3dResultIrV1,
) -> Result<(), Frame3dReportError> {
    validate_linear_frame3d_report_ir_v1(report).map_err(contract_error)?;
    let expected = project_report_ir(source, &report.report_id)?;
    if *report != expected {
        return Err(error(
            "frame3d_report_source_binding_mismatch",
            "/source_result",
            "ReportIR is not the exact deterministic projection of the supplied ResultIR",
        ));
    }
    Ok(())
}

fn project_report_ir(
    source: &LinearFrame3dResultIrV1,
    report_id: &str,
) -> Result<LinearFrame3dReportIrV1, Frame3dReportError> {
    validate_linear_frame3d_result_ir_v1(source)
        .map_err(|item| error("frame3d_report_source_invalid", &item.path, &item.detail))?;
    let node_count = u32::try_from(source.nodes.len()).map_err(|_| {
        error(
            "frame3d_report_count_invalid",
            "/summary/node_count",
            "Source node count exceeds the bounded report range",
        )
    })?;
    let member_count = u32::try_from(source.members.len()).map_err(|_| {
        error(
            "frame3d_report_count_invalid",
            "/summary/member_count",
            "Source member count exceeds the bounded report range",
        )
    })?;
    create_linear_frame3d_report_ir_v1(
        source,
        LinearFrame3dReportIrInput {
            report_id: report_id.to_owned(),
            summary: Frame3dReportSummaryV1 {
                model_id: source.bindings.model_id.clone(),
                load_pattern_id: source.bindings.load_pattern_id.clone(),
                load_combination_id: source.bindings.load_combination_id.clone(),
                formulation: source.solver.formulation.clone(),
                backend: source.solver.backend.clone(),
                node_count,
                member_count,
            },
            extrema: vec![
                displacement_extremum(source),
                reaction_extremum(source),
                member_force_extremum(source),
            ],
        },
    )
    .map_err(contract_error)
}

fn displacement_extremum(source: &LinearFrame3dResultIrV1) -> Frame3dReportExtremumV1 {
    let mut selected = (
        &source.nodes[0].node_id,
        0_usize,
        source.nodes[0].displacement_m_rad[0],
    );
    for node in &source.nodes {
        for (index, value) in node.displacement_m_rad.iter().copied().enumerate() {
            if value.abs() > selected.2.abs() {
                selected = (&node.node_id, index, value);
            }
        }
    }
    Frame3dReportExtremumV1 {
        quantity: "displacement".to_owned(),
        entity_id: selected.0.clone(),
        component: DISPLACEMENT_COMPONENTS[selected.1].to_owned(),
        signed_value: selected.2,
        absolute_value: selected.2.abs(),
        unit: displacement_unit(selected.1).to_owned(),
    }
}

fn reaction_extremum(source: &LinearFrame3dResultIrV1) -> Frame3dReportExtremumV1 {
    let mut selected = (
        &source.nodes[0].node_id,
        0_usize,
        source.nodes[0].reaction_n_nm[0],
    );
    for node in &source.nodes {
        for (index, value) in node.reaction_n_nm.iter().copied().enumerate() {
            if value.abs() > selected.2.abs() {
                selected = (&node.node_id, index, value);
            }
        }
    }
    Frame3dReportExtremumV1 {
        quantity: "reaction".to_owned(),
        entity_id: selected.0.clone(),
        component: FORCE_COMPONENTS[selected.1].to_owned(),
        signed_value: selected.2,
        absolute_value: selected.2.abs(),
        unit: force_unit(selected.1).to_owned(),
    }
}

fn member_force_extremum(source: &LinearFrame3dResultIrV1) -> Frame3dReportExtremumV1 {
    let first = &source.members[0];
    let mut selected = (&first.member_id, 0_usize, false, first.end_i_force_n_nm[0]);
    for member in &source.members {
        for (end_j, values) in [false, true]
            .into_iter()
            .zip([&member.end_i_force_n_nm, &member.end_j_force_n_nm])
        {
            for (index, value) in values.iter().copied().enumerate() {
                if value.abs() > selected.3.abs() {
                    selected = (&member.member_id, index, end_j, value);
                }
            }
        }
    }
    let end = if selected.2 { 'J' } else { 'I' };
    Frame3dReportExtremumV1 {
        quantity: "member_end_force".to_owned(),
        entity_id: selected.0.clone(),
        component: format!("{}_{}", FORCE_COMPONENTS[selected.1], end),
        signed_value: selected.3,
        absolute_value: selected.3.abs(),
        unit: force_unit(selected.1).to_owned(),
    }
}

fn render_html(
    source: &LinearFrame3dResultIrV1,
    report: &LinearFrame3dReportIrV1,
) -> Result<String, Frame3dReportError> {
    let mut html = String::with_capacity(12_000);
    let (load_source_kind, load_source_id) = match (
        report.summary.load_pattern_id.as_deref(),
        report.summary.load_combination_id.as_deref(),
    ) {
        (Some(id), None) => ("Load pattern", id),
        (None, Some(id)) => ("Load combination", id),
        _ => {
            return Err(error(
                "frame3d_report_load_binding_invalid",
                "/summary",
                "Exactly one load source identity is required",
            ));
        }
    };
    writeln!(
        html,
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n\
         <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n\
         <title>Frame3D bounded analysis report</title>\n\
         <style>body{{font:14px/1.45 system-ui,sans-serif;margin:2rem;color:#17202a}}\
         h1,h2{{color:#102a43}}table{{border-collapse:collapse;width:100%;margin:.75rem 0 1.5rem}}\
         th,td{{border:1px solid #bcccdc;padding:.35rem .5rem;text-align:right}}\
         th:first-child,td:first-child{{text-align:left}}code{{overflow-wrap:anywhere}}\
         .boundary{{border-left:4px solid #d64545;background:#fff5f5;padding:.75rem}}\
         .pass{{color:#087f5b;font-weight:700}}</style></head><body>\n\
         <h1>Bounded native linear Frame3D report</h1>\n\
         <p class=\"boundary\"><strong>Authority boundary:</strong> {}.</p>\n\
         <h2>Identity</h2><table><tbody>\
         <tr><th>Report</th><td>{}</td></tr><tr><th>Report hash</th><td><code>{}</code></td></tr>\
         <tr><th>Result</th><td>{}</td></tr><tr><th>Result hash</th><td><code>{}</code></td></tr>\
         <tr><th>Model</th><td>{}</td></tr><tr><th>{}</th><td>{}</td></tr>\
         <tr><th>Formulation</th><td>{}</td></tr><tr><th>Backend</th><td>{}</td></tr>\
         </tbody></table>",
        escape_html(&report.claim_boundary),
        escape_html(&report.report_id),
        report.report_hash,
        escape_html(&report.source_result.result_id),
        report.source_result.result_hash,
        escape_html(&report.summary.model_id),
        load_source_kind,
        escape_html(load_source_id),
        escape_html(&report.summary.formulation),
        escape_html(&report.summary.backend),
    )
    .map_err(format_error)?;

    writeln!(
        html,
        "<h2>Promotion gates</h2><table><thead><tr><th>Gate</th><th>Metric</th><th>Tolerance</th><th>Status</th></tr></thead><tbody>\
         <tr><td>Free residual scaled L∞</td><td>{:.17e}</td><td>{:.17e}</td><td class=\"pass\">PASS</td></tr>\
         <tr><td>Global force balance scaled L∞</td><td>{:.17e}</td><td>{:.17e}</td><td class=\"pass\">PASS</td></tr>\
         <tr><td>Global moment balance scaled L∞</td><td>{:.17e}</td><td>{:.17e}</td><td class=\"pass\">PASS</td></tr>\
         <tr><td>Independent member-force recovery replay scaled L∞</td><td>{:.17e}</td><td>{:.17e}</td><td class=\"pass\">PASS</td></tr>\
         </tbody></table>",
        report.gates.free_residual_scaled_linf,
        report.gates.free_residual_scaled_linf_tolerance,
        report.gates.global_force_balance_scaled_linf,
        report.gates.global_force_balance_scaled_linf_tolerance,
        report.gates.global_moment_balance_scaled_linf,
        report.gates.global_moment_balance_scaled_linf_tolerance,
        report.gates.member_force_replay_scaled_linf,
        report.gates.member_force_replay_scaled_linf_tolerance,
    )
    .map_err(format_error)?;

    html.push_str("<h2>Absolute extrema (signed value retained)</h2><table><thead><tr><th>Quantity</th><th>Entity</th><th>Component</th><th>Signed value</th><th>Absolute value</th><th>Unit</th></tr></thead><tbody>\n");
    for row in &report.extrema {
        writeln!(
            html,
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{:.17e}</td><td>{:.17e}</td><td>{}</td></tr>",
            escape_html(&row.quantity),
            escape_html(&row.entity_id),
            escape_html(&row.component),
            row.signed_value,
            row.absolute_value,
            escape_html(&row.unit),
        )
        .map_err(format_error)?;
    }
    html.push_str("</tbody></table>\n<h2>Node results</h2><table><thead><tr><th>Node</th><th>UX (m)</th><th>UY (m)</th><th>UZ (m)</th><th>RX (rad)</th><th>RY (rad)</th><th>RZ (rad)</th><th>FX (N)</th><th>FY (N)</th><th>FZ (N)</th><th>MX (N*m)</th><th>MY (N*m)</th><th>MZ (N*m)</th></tr></thead><tbody>\n");
    for node in &source.nodes {
        write!(html, "<tr><td>{}</td>", escape_html(&node.node_id)).map_err(format_error)?;
        write_values(&mut html, &node.displacement_m_rad)?;
        write_values(&mut html, &node.reaction_n_nm)?;
        html.push_str("</tr>\n");
    }
    html.push_str("</tbody></table>\n<h2>Member local end forces</h2><table><thead><tr><th>Member</th><th>FX I</th><th>FY I</th><th>FZ I</th><th>MX I</th><th>MY I</th><th>MZ I</th><th>FX J</th><th>FY J</th><th>FZ J</th><th>MX J</th><th>MY J</th><th>MZ J</th></tr></thead><tbody>\n");
    for member in &source.members {
        write!(html, "<tr><td>{}</td>", escape_html(&member.member_id)).map_err(format_error)?;
        write_values(&mut html, &member.end_i_force_n_nm)?;
        write_values(&mut html, &member.end_j_force_n_nm)?;
        html.push_str("</tr>\n");
    }
    html.push_str("</tbody></table>\n<h2>Explicit limitations</h2><ul>\n");
    for limitation in &report.limitations {
        writeln!(html, "<li>{}</li>", escape_html(limitation)).map_err(format_error)?;
    }
    html.push_str("</ul>\n</body></html>\n");
    Ok(html)
}

fn write_values(output: &mut String, values: &[f64; 6]) -> Result<(), Frame3dReportError> {
    for value in values {
        write!(output, "<td>{value:.17e}</td>").map_err(format_error)?;
    }
    Ok(())
}

const fn displacement_unit(index: usize) -> &'static str {
    if index < 3 {
        "m"
    } else {
        "rad"
    }
}

const fn force_unit(index: usize) -> &'static str {
    if index < 3 {
        "N"
    } else {
        "N*m"
    }
}

fn escape_html(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&#39;"),
            _ => escaped.push(character),
        }
    }
    escaped
}

fn contract_error(
    item: structural_contracts::report_ir::Frame3dReportIrError,
) -> Frame3dReportError {
    Frame3dReportError {
        code: item.code,
        path: item.path,
        detail: item.detail,
    }
}

fn format_error(_: fmt::Error) -> Frame3dReportError {
    error(
        "frame3d_report_format_failed",
        "/html",
        "Deterministic HTML projection could not be formatted",
    )
}

fn error(code: &str, path: &str, detail: &str) -> Frame3dReportError {
    Frame3dReportError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
