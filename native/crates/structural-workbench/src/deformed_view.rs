use std::collections::BTreeMap;
use std::fmt::Write as _;

use serde_json::Value;
use structural_cli::validate_model_bytes;
use structural_contracts::product_ir::{
    sha256_identity, ModelIrNdthaAdapterProfileV1, ModelIrNdthaAnalysisRequestDocumentV1,
    NonlinearNdthaResultIrV1, NonlinearNdthaTerminalStatusV1,
};

use crate::{input_error, ModelTopologyProjectionV1, WorkbenchError};

pub(crate) const DEFORMED_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-fixed-guided-deformed-view.v1";
pub const WORKBENCH_DEFORMED_VIEW_DEFAULT_SCALE_V1: f64 = 1_000.0;
pub const WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1: f64 = 1_000_000.0;
const VIEW_WIDTH: usize = 73;
const VIEW_HEIGHT: usize = 25;
const VIEW_MAX_COLUMN_F64: f64 = 72.0;
const VIEW_MAX_ROW_F64: f64 = 24.0;
const CLAIM_BOUNDARY: &str = "exact_executed_fixed_guided_frame3d_x_profile_selected_step_global_x_top_displacement_overlay_not_general_nodal_displacement_3d_modal_contour_engineering_acceptance_or_design_code_compliance";

#[derive(Clone, Debug)]
struct ProfileGeometry {
    model_id: String,
    capability_profile: String,
    content_hash: String,
    semantic_hash: String,
    provenance_hash: String,
    snapshot_hash: String,
    element_id: String,
    base_node_id: String,
    floor_node_id: String,
    base: [f64; 3],
    floor: [f64; 3],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PointKind {
    OriginalBase,
    DeformedBase,
    OriginalFloor,
    DeformedFloor,
}

/// Render an original/deformed overlay for the one executed C++ adapter profile.
#[allow(clippy::too_many_lines)]
pub(crate) fn render_fixed_guided_deformed_view(
    model_ir_bytes: &[u8],
    request: &ModelIrNdthaAnalysisRequestDocumentV1,
    result: &NonlinearNdthaResultIrV1,
    projection: ModelTopologyProjectionV1,
    step: Option<u32>,
    scale: f64,
) -> Result<String, WorkbenchError> {
    validate_scale(scale)?;
    let geometry = verified_profile_geometry(model_ir_bytes, request)?;
    let completed = usize::try_from(result.summary.step_count_completed).map_err(|_| {
        view_error(
            "workbench_deformed_view_result_invalid",
            "completed step count does not fit the native address space",
        )
    })?;
    if completed == 0 || result.response.top_displacement_m.len() < completed {
        return Err(view_error(
            "workbench_deformed_view_result_invalid",
            "verified ResultIR does not contain a completed top-displacement prefix",
        ));
    }
    if result.case_id != request.request().case_id {
        return Err(view_error(
            "workbench_deformed_view_binding_mismatch",
            "terminal ResultIR case does not match the immutable adapter request",
        ));
    }
    let selected_step = step.unwrap_or(result.summary.step_count_completed);
    if selected_step == 0
        || usize::try_from(selected_step)
            .ok()
            .map_or(true, |value| value > completed)
    {
        return Err(view_error(
            "workbench_deformed_view_step_invalid",
            format!("selected step must be in 1..={completed} for the completed response prefix"),
        ));
    }
    let selected_index = usize::try_from(selected_step - 1).map_err(|_| {
        view_error(
            "workbench_deformed_view_step_invalid",
            "selected step does not fit the native address space",
        )
    })?;
    let displacement = result.response.top_displacement_m[selected_index];
    let magnified_displacement = displacement * scale;
    if !displacement.is_finite() || !magnified_displacement.is_finite() {
        return Err(view_error(
            "workbench_deformed_view_result_invalid",
            "selected top displacement or its magnified projection is non-finite",
        ));
    }
    let deformed_base = geometry.base;
    let mut deformed_floor = geometry.floor;
    deformed_floor[0] += magnified_displacement;
    if !deformed_floor[0].is_finite() {
        return Err(view_error(
            "workbench_deformed_view_scale_invalid",
            "magnified deformed coordinate is outside the finite viewer domain",
        ));
    }

    let points = [geometry.base, geometry.floor, deformed_base, deformed_floor];
    let cells = project_points(&points, projection);
    let mut canvas = vec![vec![' '; VIEW_WIDTH]; VIEW_HEIGHT];
    draw_segment(&mut canvas, cells[0], cells[1], '.');
    draw_segment(&mut canvas, cells[2], cells[3], '*');
    draw_points(
        &mut canvas,
        &[
            (cells[0], PointKind::OriginalBase),
            (cells[2], PointKind::DeformedBase),
            (cells[1], PointKind::OriginalFloor),
            (cells[3], PointKind::DeformedFloor),
        ],
    );
    let terminal_status = match result.summary.terminal_status {
        NonlinearNdthaTerminalStatusV1::Completed => "completed",
        NonlinearNdthaTerminalStatusV1::Collapsed => "collapsed",
    };
    let mut output = String::new();
    writeln!(
        output,
        "Structural Native Workbench - fixed-guided NDTHA deformed shape"
    )
    .expect("String writes cannot fail");
    push_field(&mut output, "Schema", DEFORMED_VIEW_SCHEMA_V1);
    push_field(&mut output, "Authority", "bounded candidate");
    push_field(&mut output, "Profile", "fixed_guided_frame3d_x");
    push_field(&mut output, "Projection", projection.label());
    push_field(&mut output, "Viewport", "73x25 cells");
    push_field(&mut output, "Case", &result.case_id);
    push_field(&mut output, "Terminal status", terminal_status);
    push_field(&mut output, "Completed steps", &completed.to_string());
    push_field(&mut output, "Selected step", &selected_step.to_string());
    push_field(
        &mut output,
        "Top displacement global X (m)",
        &format!("{displacement:+.17e}"),
    );
    push_field(
        &mut output,
        "Visual magnification",
        &format!("{scale:.17e}"),
    );
    push_field(
        &mut output,
        "Magnified global X offset (m)",
        &format!("{magnified_displacement:+.17e}"),
    );
    push_field(
        &mut output,
        "Projected motion visible",
        if cells[1] == cells[3] {
            "false"
        } else {
            "true"
        },
    );
    push_field(&mut output, "Model", &geometry.model_id);
    push_field(
        &mut output,
        "Capability profile",
        &geometry.capability_profile,
    );
    push_field(&mut output, "C++ semantic snapshot", "verified");
    push_field(
        &mut output,
        "C++ fixed-guided adapter execution",
        "verified by durable terminal receipt",
    );
    push_field(&mut output, "Content hash", &geometry.content_hash);
    push_field(&mut output, "Semantic hash", &geometry.semantic_hash);
    push_field(&mut output, "Provenance hash", &geometry.provenance_hash);
    push_field(&mut output, "Snapshot hash", &geometry.snapshot_hash);
    push_field(&mut output, "Adapter request hash", request.request_hash());
    push_field(&mut output, "Result hash", &result.result_hash);
    push_field(
        &mut output,
        "Result request hash",
        &result.identity.request_hash,
    );
    push_field(
        &mut output,
        "Result model hash",
        &result.identity.model_hash,
    );
    push_field(&mut output, "State hash", &result.identity.state_hash);
    push_field(
        &mut output,
        "Execution hash",
        &result.identity.execution_hash,
    );
    push_field(
        &mut output,
        "Checkpoint hash",
        &result.identity.checkpoint_hash,
    );
    writeln!(
        output,
        "Legend: .=original element *=magnified deformed element ==coincident elements o=original floor d=deformed floor X=coincident floor B=fixed base @=other collision"
    )
    .expect("String writes cannot fail");
    let border = format!("+{}+", "-".repeat(VIEW_WIDTH));
    writeln!(output, "{border}").expect("String writes cannot fail");
    for row in &canvas {
        writeln!(output, "|{}|", row.iter().collect::<String>())
            .expect("String writes cannot fail");
    }
    writeln!(output, "{border}").expect("String writes cannot fail");
    writeln!(output, "Selected profile coordinates (global SI):")
        .expect("String writes cannot fail");
    push_coordinate(
        &mut output,
        "base original/deformed",
        &geometry.base_node_id,
        geometry.base,
        cells[0],
    );
    push_coordinate(
        &mut output,
        "floor original",
        &geometry.floor_node_id,
        geometry.floor,
        cells[1],
    );
    push_coordinate(
        &mut output,
        "floor magnified deformed",
        &geometry.floor_node_id,
        deformed_floor,
        cells[3],
    );
    writeln!(
        output,
        "Element: {} {} -> {}",
        geometry.element_id, geometry.base_node_id, geometry.floor_node_id
    )
    .expect("String writes cannot fail");
    writeln!(output, "Claim boundary: {CLAIM_BOUNDARY}").expect("String writes cannot fail");
    let view_hash = sha256_identity(output.as_bytes());
    push_field(&mut output, "View hash", &view_hash);
    if output.as_bytes().contains(&0x1b) {
        return Err(view_error(
            "workbench_deformed_view_unsafe",
            "deformed-shape view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn validate_scale(scale: f64) -> Result<(), WorkbenchError> {
    if !scale.is_finite() || scale <= 0.0 || scale > WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1 {
        return Err(view_error(
            "workbench_deformed_view_scale_invalid",
            format!(
                "visual magnification must be finite and in (0, {WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1}]"
            ),
        ));
    }
    Ok(())
}

#[allow(clippy::float_cmp)] // The C++ adapter contract requires exact vertical-axis coordinates.
fn verified_profile_geometry(
    model_ir_bytes: &[u8],
    request: &ModelIrNdthaAnalysisRequestDocumentV1,
) -> Result<ProfileGeometry, WorkbenchError> {
    let validation = validate_model_bytes(model_ir_bytes)
        .map_err(|error| input_error("workbench_deformed_view_validation_failed", &error))?;
    if !validation.report.contract_valid || !validation.report.semantics_valid {
        return Err(view_error(
            "workbench_deformed_view_semantics_invalid",
            "native C++ validation rejected the immutable ModelIR",
        ));
    }
    let selected = request.request();
    if selected.profile != ModelIrNdthaAdapterProfileV1::FixedGuidedFrame3dX
        || selected.model_identity.content_hash != validation.report.content_hash
        || selected.model_identity.semantic_hash != validation.report.semantic_hash
        || selected.model_identity.provenance_hash != validation.report.provenance_hash
    {
        return Err(view_error(
            "workbench_deformed_view_binding_mismatch",
            "adapter profile or ModelIR identities do not match the C++ semantic snapshot",
        ));
    }
    let snapshot = validation.snapshot.value();
    if validation.snapshot.capability_profile() != "engine_v2_phase0_linear_3d"
        || array_field(snapshot, "nodes")?.len() != 2
        || array_field(snapshot, "elements")?.len() != 1
        || array_field(snapshot, "materials")?.len() != 1
        || array_field(snapshot, "sections")?.len() != 1
        || array_field(snapshot, "constraints")?.len() != 2
        || array_field(snapshot, "load_patterns")?.len() != 1
    {
        return Err(profile_error(
            "C++ snapshot inventory is outside the exact fixed-guided adapter profile",
        ));
    }
    let base = find_node(snapshot, &selected.base_node_id)?;
    let floor = find_node(snapshot, &selected.floor_node_id)?;
    if base[0] != floor[0] || base[1] != floor[1] || floor[2] <= base[2] {
        return Err(profile_error(
            "adapter nodes are not a vertical positive-global-Z member",
        ));
    }
    let element = array_field(snapshot, "elements")?
        .first()
        .expect("exact inventory checked");
    let node_ids = array_field(element, "node_ids")?;
    if string_field(element, "id")? != selected.element_id
        || string_field(element, "type")? != "frame_3d"
        || node_ids.len() != 2
        || node_ids[0].as_str() != Some(selected.base_node_id.as_str())
        || node_ids[1].as_str() != Some(selected.floor_node_id.as_str())
    {
        return Err(profile_error(
            "adapter element selector or connectivity is outside the exact profile",
        ));
    }
    Ok(ProfileGeometry {
        model_id: validation.report.model_id,
        capability_profile: validation.snapshot.capability_profile().to_owned(),
        content_hash: validation.report.content_hash,
        semantic_hash: validation.report.semantic_hash,
        provenance_hash: validation.report.provenance_hash,
        snapshot_hash: sha256_identity(validation.snapshot.canonical_json().as_bytes()),
        element_id: selected.element_id.clone(),
        base_node_id: selected.base_node_id.clone(),
        floor_node_id: selected.floor_node_id.clone(),
        base,
        floor,
    })
}

fn find_node(snapshot: &Value, id: &str) -> Result<[f64; 3], WorkbenchError> {
    let node = array_field(snapshot, "nodes")?
        .iter()
        .find(|node| node.get("id").and_then(Value::as_str) == Some(id))
        .ok_or_else(|| profile_error("adapter node selector is absent from the C++ snapshot"))?;
    let source = array_field(node, "coordinates_m")?;
    if source.len() != 3 {
        return Err(profile_error(
            "adapter node coordinates are not three-dimensional",
        ));
    }
    let mut coordinates = [0.0; 3];
    for (target, value) in coordinates.iter_mut().zip(source) {
        *target = value
            .as_f64()
            .filter(|value| value.is_finite())
            .ok_or_else(|| profile_error("adapter node coordinate is not finite"))?;
    }
    Ok(coordinates)
}

fn project_points(
    points: &[[f64; 3]],
    projection: ModelTopologyProjectionV1,
) -> Vec<(usize, usize)> {
    let projected = points
        .iter()
        .map(|&point| projection.project(point))
        .collect::<Vec<_>>();
    let min_u = projected
        .iter()
        .map(|point| point.0)
        .fold(f64::INFINITY, f64::min);
    let max_u = projected
        .iter()
        .map(|point| point.0)
        .fold(f64::NEG_INFINITY, f64::max);
    let min_v = projected
        .iter()
        .map(|point| point.1)
        .fold(f64::INFINITY, f64::min);
    let max_v = projected
        .iter()
        .map(|point| point.1)
        .fold(f64::NEG_INFINITY, f64::max);
    let width = VIEW_MAX_COLUMN_F64;
    let height = VIEW_MAX_ROW_F64;
    let span_u = max_u - min_u;
    let span_v = max_v - min_v;
    let scale_u = if span_u > 0.0 {
        width / span_u
    } else {
        f64::INFINITY
    };
    let scale_v = if span_v > 0.0 {
        height / span_v
    } else {
        f64::INFINITY
    };
    let scale = scale_u.min(scale_v);
    let finite_scale = if scale.is_finite() { scale } else { 0.0 };
    let offset_u = (width - span_u * finite_scale) * 0.5;
    let offset_v = (height - span_v * finite_scale) * 0.5;
    projected
        .into_iter()
        .map(|point| {
            let column = bounded_cell((point.0 - min_u) * finite_scale + offset_u, width);
            let from_bottom = bounded_cell((point.1 - min_v) * finite_scale + offset_v, height);
            (column, VIEW_HEIGHT - 1 - from_bottom)
        })
        .collect()
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn bounded_cell(value: f64, maximum: f64) -> usize {
    value.round().clamp(0.0, maximum) as usize
}

fn draw_segment(
    canvas: &mut [Vec<char>],
    first: (usize, usize),
    second: (usize, usize),
    glyph: char,
) {
    let (mut column, mut row) = (
        isize::try_from(first.0).expect("fixed view column fits isize"),
        isize::try_from(first.1).expect("fixed view row fits isize"),
    );
    let (target_column, target_row) = (
        isize::try_from(second.0).expect("fixed view column fits isize"),
        isize::try_from(second.1).expect("fixed view row fits isize"),
    );
    let delta_column = (target_column - column).abs();
    let step_column = if column < target_column { 1 } else { -1 };
    let delta_row = -(target_row - row).abs();
    let step_row = if row < target_row { 1 } else { -1 };
    let mut error = delta_column + delta_row;
    loop {
        let cell = &mut canvas[usize::try_from(row).expect("view row stays nonnegative")]
            [usize::try_from(column).expect("view column stays nonnegative")];
        *cell = match (*cell, glyph) {
            (' ', value) => value,
            (existing, incoming) if existing == incoming => existing,
            ('.', '*') | ('*', '.') | ('=', _) => '=',
            _ => '@',
        };
        if column == target_column && row == target_row {
            break;
        }
        let doubled = error * 2;
        if doubled >= delta_row {
            error += delta_row;
            column += step_column;
        }
        if doubled <= delta_column {
            error += delta_column;
            row += step_row;
        }
    }
}

fn draw_points(canvas: &mut [Vec<char>], points: &[((usize, usize), PointKind)]) {
    let mut grouped = BTreeMap::<(usize, usize), Vec<PointKind>>::new();
    for &(cell, kind) in points {
        grouped.entry(cell).or_default().push(kind);
    }
    for ((column, row), kinds) in grouped {
        canvas[row][column] = point_glyph(&kinds);
    }
}

fn point_glyph(kinds: &[PointKind]) -> char {
    let has = |kind| kinds.contains(&kind);
    if kinds.len() == 2 && has(PointKind::OriginalBase) && has(PointKind::DeformedBase) {
        'B'
    } else if kinds.len() == 2 && has(PointKind::OriginalFloor) && has(PointKind::DeformedFloor) {
        'X'
    } else if kinds.len() != 1 {
        '@'
    } else {
        match kinds[0] {
            PointKind::OriginalBase | PointKind::DeformedBase => 'B',
            PointKind::OriginalFloor => 'o',
            PointKind::DeformedFloor => 'd',
        }
    }
}

fn push_coordinate(
    output: &mut String,
    label: &str,
    id: &str,
    xyz: [f64; 3],
    cell: (usize, usize),
) {
    writeln!(
        output,
        "  {label}: {id} xyz_m=[{:+.17e},{:+.17e},{:+.17e}] projected_cell=[{},{}]",
        xyz[0], xyz[1], xyz[2], cell.0, cell.1,
    )
    .expect("String writes cannot fail");
}

fn push_field(output: &mut String, label: &str, value: &str) {
    writeln!(output, "{label}: {value}").expect("String writes cannot fail");
}

fn array_field<'a>(value: &'a Value, field: &str) -> Result<&'a [Value], WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| profile_error(format!("C++ snapshot field {field} is not an array")))
}

fn string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| profile_error(format!("C++ snapshot field {field} is not a string")))
}

fn profile_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_deformed_view_profile_invalid", detail)
}

fn view_error(code: &'static str, detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}

#[cfg(test)]
mod tests {
    use super::{point_glyph, PointKind};

    #[test]
    fn collision_glyphs_preserve_fixed_and_floor_meaning() {
        assert_eq!(
            point_glyph(&[PointKind::OriginalBase, PointKind::DeformedBase]),
            'B'
        );
        assert_eq!(
            point_glyph(&[PointKind::OriginalFloor, PointKind::DeformedFloor]),
            'X'
        );
        assert_eq!(point_glyph(&[PointKind::OriginalFloor]), 'o');
        assert_eq!(
            point_glyph(&[PointKind::OriginalBase, PointKind::OriginalFloor]),
            '@'
        );
    }
}
