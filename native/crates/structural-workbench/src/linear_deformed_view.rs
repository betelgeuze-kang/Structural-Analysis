use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;

use serde_json::Value;
use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_recovery::ModelIrLinearResultRecoveryIrV1;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{SparseLinearBackendV1, SparseLinearResultIrV1};

use crate::deformed_view::{draw_segment, project_points, validate_scale, VIEW_HEIGHT, VIEW_WIDTH};
use crate::{ModelTopologyProjectionV1, WorkbenchError, WorkbenchReportLocaleV1};

pub(crate) const MODEL_IR_LINEAR_DEFORMED_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-deformed-view.v1";

const MAX_VIEW_NODES: usize = 512;
const MAX_VIEW_ELEMENTS: usize = 1_024;
const CLAIM_BOUNDARY: &str = "bounded_read_only_modelir_linear_two_node_centerline_original_and_magnified_translational_displacement_projection_not_member_curvature_rigid_offset_rotation_stress_contour_modal_serviceability_support_design_engineering_acceptance_or_design_code_compliance";

#[derive(Clone, Debug)]
struct LinearViewNode {
    id: String,
    index: usize,
    original: [f64; 3],
    displacement: [f64; 6],
    deformed: [f64; 3],
    original_cell: (usize, usize),
    deformed_cell: (usize, usize),
}

#[derive(Clone, Debug)]
struct LinearViewElement {
    id: String,
    index: u64,
    kind: String,
    first_node: usize,
    second_node: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PointLayer {
    Original,
    Deformed,
}

struct LinearDeformedViewLabels {
    title: &'static str,
    schema: &'static str,
    locale: &'static str,
    authority: &'static str,
    profile: &'static str,
    projection: &'static str,
    viewport: &'static str,
    state: &'static str,
    visual_magnification: &'static str,
    applied_components: &'static str,
    omitted_components: &'static str,
    case: &'static str,
    model: &'static str,
    load_pattern: &'static str,
    inventory: &'static str,
    coincident_nodes: &'static str,
    projected_collisions: &'static str,
    backend: &'static str,
    transfer_sync: &'static str,
    maximum_displacement: &'static str,
    content_hash: &'static str,
    semantic_hash: &'static str,
    provenance_hash: &'static str,
    result_hash: &'static str,
    recovery_hash: &'static str,
    analysis_request_hash: &'static str,
    assembly_hash: &'static str,
    sparse_request_hash: &'static str,
    sparse_model_hash: &'static str,
    state_hash: &'static str,
    execution_hash: &'static str,
    checkpoint_hash: &'static str,
    legend: &'static str,
    coordinates: &'static str,
    elements: &'static str,
    claim_boundary: &'static str,
    view_hash: &'static str,
}

/// Render one deterministic original/deformed centerline overlay for a verified linear result.
#[allow(clippy::too_many_lines)] // Keep the self-hashed presentation order explicit and auditable.
pub(crate) fn render_model_ir_linear_deformed_view(
    model: &ModelIrV2Document,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
    scale: f64,
) -> Result<String, WorkbenchError> {
    validate_scale(scale)?;
    verify_model_identity(model, result, recovery)?;
    let mut nodes = indexed_nodes(model, recovery, scale)?;
    let elements = indexed_elements(model, &nodes)?;

    let mut points = nodes.iter().map(|node| node.original).collect::<Vec<_>>();
    points.extend(nodes.iter().map(|node| node.deformed));
    verify_projection_domain(&points, projection)?;
    let cells = project_points(&points, projection);
    let node_count = nodes.len();
    for (index, node) in nodes.iter_mut().enumerate() {
        node.original_cell = cells[index];
        node.deformed_cell = cells[index + node_count];
    }

    let mut canvas = vec![vec![' '; VIEW_WIDTH]; VIEW_HEIGHT];
    for element in &elements {
        draw_segment(
            &mut canvas,
            nodes[element.first_node].original_cell,
            nodes[element.second_node].original_cell,
            '.',
        );
    }
    for element in &elements {
        draw_segment(
            &mut canvas,
            nodes[element.first_node].deformed_cell,
            nodes[element.second_node].deformed_cell,
            '*',
        );
    }
    let projected_collision_count = draw_node_points(&mut canvas, &nodes);
    let coincident_node_count = nodes
        .iter()
        .filter(|node| node.original_cell == node.deformed_cell)
        .count();

    let labels = linear_deformed_view_labels(locale);
    let mut output = String::new();
    push_line(&mut output, labels.title);
    push_field(
        &mut output,
        labels.schema,
        MODEL_IR_LINEAR_DEFORMED_VIEW_SCHEMA_V1,
    );
    push_field(&mut output, labels.locale, locale.label());
    push_field(&mut output, labels.authority, "bounded candidate");
    push_field(&mut output, labels.profile, "model_ir_linear_cpu_v1");
    push_field(&mut output, labels.projection, projection.label());
    push_field(
        &mut output,
        labels.viewport,
        &format!("{VIEW_WIDTH}x{VIEW_HEIGHT} cells"),
    );
    push_field(&mut output, labels.state, "1 of 1 (terminal linear static)");
    push_field(
        &mut output,
        labels.visual_magnification,
        &format!("{scale:.17e}"),
    );
    push_field(
        &mut output,
        labels.applied_components,
        "UX/UY/UZ translational displacement in m",
    );
    push_field(
        &mut output,
        labels.omitted_components,
        "RX/RY/RZ are reported in rad but are not applied to centerline coordinates",
    );
    push_field(&mut output, labels.case, &recovery.case_id);
    push_field(&mut output, labels.model, &recovery.model_id);
    push_field(&mut output, labels.load_pattern, &recovery.load_pattern_id);
    push_field(
        &mut output,
        labels.inventory,
        &format!("nodes={} elements={}", nodes.len(), elements.len()),
    );
    push_field(
        &mut output,
        labels.coincident_nodes,
        &coincident_node_count.to_string(),
    );
    push_field(
        &mut output,
        labels.projected_collisions,
        &projected_collision_count.to_string(),
    );
    push_field(
        &mut output,
        labels.backend,
        &format!(
            "{} / {} / ABI {} / fallback {}",
            sparse_backend_label(result.backend_receipt.backend),
            result.backend_receipt.precision,
            result.backend_receipt.abi_version,
            result.backend_receipt.fallback_count,
        ),
    );
    push_field(
        &mut output,
        labels.transfer_sync,
        &format!(
            "H2D {} / D2H {} / sync {}",
            result.backend_receipt.h2d_bytes,
            result.backend_receipt.d2h_bytes,
            result.backend_receipt.sync_count,
        ),
    );
    push_field(
        &mut output,
        labels.maximum_displacement,
        &format!("{:+.17e}", recovery.summary.maximum_absolute_displacement),
    );
    push_field(
        &mut output,
        labels.content_hash,
        &recovery.model_identity.content_hash,
    );
    push_field(
        &mut output,
        labels.semantic_hash,
        &recovery.model_identity.semantic_hash,
    );
    push_field(
        &mut output,
        labels.provenance_hash,
        &recovery.model_identity.provenance_hash,
    );
    push_field(
        &mut output,
        labels.result_hash,
        &recovery.source_result_hash,
    );
    push_field(&mut output, labels.recovery_hash, &recovery.recovery_hash);
    push_field(
        &mut output,
        labels.analysis_request_hash,
        &recovery.analysis_request_hash,
    );
    push_field(&mut output, labels.assembly_hash, &recovery.assembly_hash);
    push_field(
        &mut output,
        labels.sparse_request_hash,
        &result.identity.request_hash,
    );
    push_field(
        &mut output,
        labels.sparse_model_hash,
        &result.identity.model_hash,
    );
    push_field(&mut output, labels.state_hash, &result.identity.state_hash);
    push_field(
        &mut output,
        labels.execution_hash,
        &result.identity.execution_hash,
    );
    push_field(
        &mut output,
        labels.checkpoint_hash,
        &result.identity.checkpoint_hash,
    );
    push_line(&mut output, labels.legend);
    let border = format!("+{}+", "-".repeat(VIEW_WIDTH));
    push_line(&mut output, &border);
    for row in &canvas {
        writeln!(output, "|{}|", row.iter().collect::<String>())
            .expect("writing to a String cannot fail");
    }
    push_line(&mut output, &border);
    push_line(&mut output, labels.coordinates);
    for node in &nodes {
        writeln!(
            output,
            "  {:06} {} original_xyz_m=[{:+.17e},{:+.17e},{:+.17e}] translation_m=[{:+.17e},{:+.17e},{:+.17e}] rotation_rad=[{:+.17e},{:+.17e},{:+.17e}] magnified_xyz_m=[{:+.17e},{:+.17e},{:+.17e}] original_cell=[{},{}] deformed_cell=[{},{}]",
            node.index + 1,
            node.id,
            node.original[0],
            node.original[1],
            node.original[2],
            node.displacement[0],
            node.displacement[1],
            node.displacement[2],
            node.displacement[3],
            node.displacement[4],
            node.displacement[5],
            node.deformed[0],
            node.deformed[1],
            node.deformed[2],
            node.original_cell.0,
            node.original_cell.1,
            node.deformed_cell.0,
            node.deformed_cell.1,
        )
        .expect("writing to a String cannot fail");
    }
    push_line(&mut output, labels.elements);
    for (row_index, element) in elements.iter().enumerate() {
        writeln!(
            output,
            "  {:06} {} element_index={:010} {} {} -> {}",
            row_index + 1,
            element.id,
            element.index,
            element.kind,
            nodes[element.first_node].id,
            nodes[element.second_node].id,
        )
        .expect("writing to a String cannot fail");
    }
    push_field(&mut output, labels.claim_boundary, CLAIM_BOUNDARY);
    let view_hash = sha256_identity(output.as_bytes());
    push_field(&mut output, labels.view_hash, &view_hash);
    if output.as_bytes().contains(&0x1b) {
        return Err(view_error(
            "workbench_linear_deformed_view_unsafe",
            "ModelIR linear deformed view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn verify_model_identity(
    model: &ModelIrV2Document,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), WorkbenchError> {
    if model.model_id() != recovery.model_id
        || model.content_hash() != recovery.model_identity.content_hash
        || model.semantic_hash() != recovery.model_identity.semantic_hash
        || model.provenance_hash() != recovery.model_identity.provenance_hash
        || result.case_id != recovery.case_id
        || result.result_hash != recovery.source_result_hash
    {
        return Err(view_error(
            "workbench_linear_deformed_view_model_mismatch",
            "verified recovery identities do not match the immutable ModelIR and sparse result",
        ));
    }
    Ok(())
}

fn indexed_nodes(
    model: &ModelIrV2Document,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    scale: f64,
) -> Result<Vec<LinearViewNode>, WorkbenchError> {
    let global_dof_count = usize::try_from(recovery.global_dof_count)
        .map_err(|_| model_error("global DOF count does not fit the native node address space"))?;
    if global_dof_count == 0 || global_dof_count % 6 != 0 {
        return Err(model_error(
            "global DOF count is not a nonzero six-component node mapping",
        ));
    }
    let node_count = global_dof_count / 6;
    let values = array_field(model.value(), "nodes")?;
    if node_count > MAX_VIEW_NODES {
        return Err(view_error(
            "workbench_linear_deformed_view_inventory_too_large",
            format!("deformed view supports at most {MAX_VIEW_NODES} nodes"),
        ));
    }
    if values.len() != node_count || recovery.global_displacement.len() != global_dof_count {
        return Err(view_error(
            "workbench_linear_deformed_view_model_mismatch",
            "ModelIR nodes and recovered global displacement dimensions differ",
        ));
    }
    let mut nodes = vec![None; node_count];
    let mut ids = BTreeSet::new();
    for value in values {
        let index = value
            .get("index")
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|&value| value < node_count)
            .ok_or_else(|| model_error("ModelIR node index is missing or outside the DOF map"))?;
        let id = safe_string_field(value, "id")?.to_owned();
        if !ids.insert(id.clone()) {
            return Err(model_error("ModelIR node identifiers are not unique"));
        }
        let source = array_field(value, "coordinates_m")?;
        if source.len() != 3 {
            return Err(model_error(
                "ModelIR node coordinates are not three-dimensional",
            ));
        }
        let mut original = [0.0; 3];
        for (target, source) in original.iter_mut().zip(source) {
            *target = source
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| model_error("ModelIR node coordinate is not finite"))?;
        }
        let mut displacement = [0.0; 6];
        let offset = index * 6;
        for (target, source) in displacement
            .iter_mut()
            .zip(&recovery.global_displacement[offset..offset + 6])
        {
            if !source.is_finite() {
                return Err(result_error("recovered nodal displacement is not finite"));
            }
            *target = *source;
        }
        let mut deformed = original;
        for axis in 0..3 {
            deformed[axis] += displacement[axis] * scale;
            if !deformed[axis].is_finite() {
                return Err(view_error(
                    "workbench_deformed_view_scale_invalid",
                    "magnified ModelIR linear coordinate is outside the finite viewer domain",
                ));
            }
        }
        let node = LinearViewNode {
            id,
            index,
            original,
            displacement,
            deformed,
            original_cell: (0, 0),
            deformed_cell: (0, 0),
        };
        if nodes[index].replace(node).is_some() {
            return Err(model_error("ModelIR node indices are not unique"));
        }
    }
    nodes
        .into_iter()
        .map(|node| {
            node.ok_or_else(|| {
                model_error("ModelIR node indices do not form a complete contiguous mapping")
            })
        })
        .collect()
}

fn indexed_elements(
    model: &ModelIrV2Document,
    nodes: &[LinearViewNode],
) -> Result<Vec<LinearViewElement>, WorkbenchError> {
    let values = array_field(model.value(), "elements")?;
    if values.len() > MAX_VIEW_ELEMENTS {
        return Err(view_error(
            "workbench_linear_deformed_view_inventory_too_large",
            format!("deformed view supports at most {MAX_VIEW_ELEMENTS} elements"),
        ));
    }
    let node_indices = nodes
        .iter()
        .map(|node| (node.id.as_str(), node.index))
        .collect::<BTreeMap<_, _>>();
    let mut indices = BTreeSet::new();
    let mut ids = BTreeSet::new();
    let mut elements = Vec::with_capacity(values.len());
    for value in values {
        let id = safe_string_field(value, "id")?.to_owned();
        let kind = safe_string_field(value, "type")?.to_owned();
        let index = value
            .get("index")
            .and_then(Value::as_u64)
            .ok_or_else(|| model_error("ModelIR element index is missing"))?;
        if !indices.insert(index) || !ids.insert(id.clone()) {
            return Err(model_error(
                "ModelIR element indices and identifiers must be unique",
            ));
        }
        let node_ids = array_field(value, "node_ids")?;
        if node_ids.len() != 2 {
            return Err(model_error(
                "bounded linear deformed view supports only two-node elements",
            ));
        }
        let first_id = safe_value_string(&node_ids[0], "element first node")?;
        let second_id = safe_value_string(&node_ids[1], "element second node")?;
        let first_node = node_indices
            .get(first_id)
            .copied()
            .ok_or_else(|| model_error("element first node is absent from the node map"))?;
        let second_node = node_indices
            .get(second_id)
            .copied()
            .ok_or_else(|| model_error("element second node is absent from the node map"))?;
        elements.push(LinearViewElement {
            id,
            index,
            kind,
            first_node,
            second_node,
        });
    }
    elements.sort_by(|left, right| (left.index, &left.id).cmp(&(right.index, &right.id)));
    Ok(elements)
}

fn draw_node_points(canvas: &mut [Vec<char>], nodes: &[LinearViewNode]) -> usize {
    let mut groups = BTreeMap::<(usize, usize), Vec<(usize, PointLayer)>>::new();
    for node in nodes {
        groups
            .entry(node.original_cell)
            .or_default()
            .push((node.index, PointLayer::Original));
        groups
            .entry(node.deformed_cell)
            .or_default()
            .push((node.index, PointLayer::Deformed));
    }
    let mut collisions = 0;
    for ((column, row), points) in groups {
        let glyph = point_glyph(&points);
        if glyph == '@' {
            collisions += 1;
        }
        canvas[row][column] = glyph;
    }
    collisions
}

fn verify_projection_domain(
    points: &[[f64; 3]],
    projection: ModelTopologyProjectionV1,
) -> Result<(), WorkbenchError> {
    let projected = points
        .iter()
        .map(|&point| projection.project(point))
        .collect::<Vec<_>>();
    if projected
        .iter()
        .any(|(u, v)| !u.is_finite() || !v.is_finite())
    {
        return Err(view_error(
            "workbench_linear_deformed_view_projection_invalid",
            "projected ModelIR linear coordinates are outside the finite viewer domain",
        ));
    }
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
    if !(max_u - min_u).is_finite() || !(max_v - min_v).is_finite() {
        return Err(view_error(
            "workbench_linear_deformed_view_projection_invalid",
            "projected ModelIR linear extent is outside the finite viewer domain",
        ));
    }
    Ok(())
}

fn point_glyph(points: &[(usize, PointLayer)]) -> char {
    if points.len() == 1 {
        return match points[0].1 {
            PointLayer::Original => 'o',
            PointLayer::Deformed => 'd',
        };
    }
    if points.len() == 2
        && points[0].0 == points[1].0
        && points.iter().any(|point| point.1 == PointLayer::Original)
        && points.iter().any(|point| point.1 == PointLayer::Deformed)
    {
        'X'
    } else {
        '@'
    }
}

const fn sparse_backend_label(backend: SparseLinearBackendV1) -> &'static str {
    match backend {
        SparseLinearBackendV1::Cpu => "cpu",
    }
}

fn linear_deformed_view_labels(locale: WorkbenchReportLocaleV1) -> LinearDeformedViewLabels {
    match locale {
        WorkbenchReportLocaleV1::EnUs => LinearDeformedViewLabels {
            title: "Structural ModelIR Linear Workbench - Deformed Shape",
            schema: "Schema",
            locale: "Locale",
            authority: "Authority",
            profile: "Profile",
            projection: "Projection",
            viewport: "Viewport",
            state: "Selected state",
            visual_magnification: "Visual magnification",
            applied_components: "Applied components",
            omitted_components: "Rotation treatment",
            case: "Case",
            model: "Model",
            load_pattern: "Load pattern",
            inventory: "Inventory",
            coincident_nodes: "Original/deformed coincident nodes",
            projected_collisions: "Other projected node collisions",
            backend: "Backend",
            transfer_sync: "Transfer/sync counts",
            maximum_displacement: "Maximum absolute recovered component (mixed m/rad)",
            content_hash: "Model content hash",
            semantic_hash: "Model semantic hash",
            provenance_hash: "Model provenance hash",
            result_hash: "Source result hash",
            recovery_hash: "Recovery hash",
            analysis_request_hash: "Analysis request hash",
            assembly_hash: "Assembly hash",
            sparse_request_hash: "Sparse request hash",
            sparse_model_hash: "Sparse model hash",
            state_hash: "State hash",
            execution_hash: "Execution hash",
            checkpoint_hash: "Checkpoint hash",
            legend: "Legend: .=original centerline *=magnified deformed centerline ==coincident centerlines o=original node d=deformed node X=coincident original/deformed node @=other projected collision",
            coordinates: "Nodes (global SI coordinates and exact recovered components):",
            elements: "Elements (two-node centerlines):",
            claim_boundary: "Claim boundary",
            view_hash: "View hash",
        },
        WorkbenchReportLocaleV1::KoKr => LinearDeformedViewLabels {
            title: "Structural ModelIR 선형 Workbench - 변형 형상",
            schema: "스키마",
            locale: "로케일",
            authority: "권한",
            profile: "프로파일",
            projection: "투영",
            viewport: "뷰포트",
            state: "선택 상태",
            visual_magnification: "시각 확대 배율",
            applied_components: "적용 성분",
            omitted_components: "회전 처리",
            case: "해석 사례",
            model: "모델",
            load_pattern: "하중 패턴",
            inventory: "재고",
            coincident_nodes: "원형/변형 일치 노드",
            projected_collisions: "기타 투영 노드 중첩",
            backend: "백엔드",
            transfer_sync: "전송/동기 계수",
            maximum_displacement: "최대 절대 복원 성분(혼합 m/rad)",
            content_hash: "모델 콘텐츠 해시",
            semantic_hash: "모델 의미 해시",
            provenance_hash: "모델 출처 해시",
            result_hash: "소스 결과 해시",
            recovery_hash: "복원 해시",
            analysis_request_hash: "분석 요청 해시",
            assembly_hash: "조립 해시",
            sparse_request_hash: "희소 요청 해시",
            sparse_model_hash: "희소 모델 해시",
            state_hash: "상태 해시",
            execution_hash: "실행 해시",
            checkpoint_hash: "체크포인트 해시",
            legend: "범례: .=원래 중심선 *=확대 변형 중심선 ==일치 중심선 o=원래 노드 d=변형 노드 X=원형/변형 일치 노드 @=기타 투영 중첩",
            coordinates: "노드 (전역 SI 좌표와 정확한 복원 성분):",
            elements: "요소 (2절점 중심선):",
            claim_boundary: "주장 경계",
            view_hash: "보기 해시",
        },
    }
}

fn array_field<'a>(value: &'a Value, field: &str) -> Result<&'a [Value], WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| model_error(format!("ModelIR field {field} is not an array")))
}

fn safe_string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .get(field)
        .ok_or_else(|| model_error(format!("ModelIR field {field} is missing")))
        .and_then(|value| safe_value_string(value, field))
}

fn safe_value_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .as_str()
        .filter(|text| !text.is_empty() && !text.chars().any(char::is_control))
        .ok_or_else(|| {
            model_error(format!(
                "ModelIR field {field} is not a safe terminal string"
            ))
        })
}

fn model_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_linear_deformed_view_model_invalid", detail)
}

fn result_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_linear_deformed_view_result_invalid", detail)
}

fn view_error(code: &'static str, detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}

fn push_line(output: &mut String, value: &str) {
    output.push_str(value);
    output.push('\n');
}

fn push_field(output: &mut String, label: &str, value: &str) {
    output.push_str(label);
    output.push_str(": ");
    push_line(output, value);
}

#[cfg(test)]
mod tests {
    use super::{point_glyph, verify_projection_domain, PointLayer};
    use crate::ModelTopologyProjectionV1;

    #[test]
    fn point_glyph_distinguishes_same_node_coincidence_from_projection_collision() {
        assert_eq!(point_glyph(&[(0, PointLayer::Original)]), 'o');
        assert_eq!(point_glyph(&[(0, PointLayer::Deformed)]), 'd');
        assert_eq!(
            point_glyph(&[(0, PointLayer::Original), (0, PointLayer::Deformed)]),
            'X'
        );
        assert_eq!(
            point_glyph(&[(0, PointLayer::Original), (1, PointLayer::Deformed)]),
            '@'
        );
    }

    #[test]
    fn projection_domain_rejects_finite_coordinates_with_infinite_extent() {
        let error = verify_projection_domain(
            &[[f64::MAX, 0.0, 0.0], [-f64::MAX, 0.0, 0.0]],
            ModelTopologyProjectionV1::Xy,
        )
        .expect_err("overflowing projected extent must fail closed");
        assert_eq!(
            error.code,
            "workbench_linear_deformed_view_projection_invalid"
        );
    }
}
