use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::path::Path;

use serde_json::Value;
use structural_cli::validate_model_bytes;
use structural_contracts::product_ir::sha256_identity;

use super::{
    input_error, read_bounded_regular_file, WorkbenchError, WorkbenchReportLocaleV1,
    MAX_MODEL_BYTES,
};

const VIEW_SCHEMA_V1: &str = "structural-native-model-topology-view.v1";
const VIEW_WIDTH: usize = 73;
const VIEW_HEIGHT: usize = 25;
const VIEW_MAX_COLUMN_F64: f64 = 72.0;
const VIEW_MAX_ROW_F64: f64 = 24.0;
const MAX_VIEW_NODES: usize = 512;
const MAX_VIEW_ELEMENTS: usize = 1_024;
const CLAIM_BOUNDARY: &str = "bounded_general_modelir_semantic_snapshot_terminal_topology_projection_not_model_editing_deformed_result_exploration_accessibility_or_engineering_acceptance";

/// Fixed native terminal projections for the bounded general `ModelIR` topology view.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ModelTopologyProjectionV1 {
    Isometric,
    Xy,
    Xz,
    Yz,
}

impl ModelTopologyProjectionV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Isometric => "isometric",
            Self::Xy => "xy",
            Self::Xz => "xz",
            Self::Yz => "yz",
        }
    }

    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "isometric" => Some(Self::Isometric),
            "xy" => Some(Self::Xy),
            "xz" => Some(Self::Xz),
            "yz" => Some(Self::Yz),
            _ => None,
        }
    }

    pub(crate) fn project(self, coordinates: [f64; 3]) -> (f64, f64) {
        let [x, y, z] = coordinates;
        match self {
            // A rational oblique projection avoids trigonometric/library drift while preserving
            // all three axes in one deterministic terminal view.
            Self::Isometric => (x - y, z + (x + y) * 0.5),
            Self::Xy => (x, y),
            Self::Xz => (x, z),
            Self::Yz => (y, z),
        }
    }
}

#[derive(Clone, Debug)]
struct ViewNode {
    id: String,
    index: u64,
    coordinates: [f64; 3],
    supported: bool,
    loaded: bool,
    column: usize,
    row: usize,
}

#[derive(Clone, Debug)]
struct ViewElement {
    id: String,
    index: u64,
    kind: String,
    first_node_id: String,
    second_node_id: String,
}

#[derive(Clone, Debug)]
struct ViewMetadata {
    model_id: String,
    capability_profile: String,
    content_hash: String,
    semantic_hash: String,
    provenance_hash: String,
    analysis_ready: bool,
    blocking_features: Vec<String>,
    constraint_count: u64,
    load_pattern_count: u64,
}

struct ModelViewLabels {
    title: &'static str,
    locale: Option<&'static str>,
    schema: &'static str,
    model: &'static str,
    capability_profile: &'static str,
    projection: &'static str,
    viewport: &'static str,
    content_hash: &'static str,
    semantic_hash: &'static str,
    provenance_hash: &'static str,
    semantic_snapshot: &'static str,
    analysis_ready: &'static str,
    blocking_features: &'static str,
    analysis_types: &'static str,
    inventory: &'static str,
    legend: &'static str,
    nodes: &'static str,
    elements: &'static str,
    claim_boundary: &'static str,
    view_hash: &'static str,
}

/// Read one bounded regular `ModelIR` file and render its verified C++ semantic snapshot.
///
/// # Errors
///
/// Rejects unsafe input files, invalid `ModelIR`, C++ semantic rejection, unsupported projection
/// inventory sizes, or malformed snapshot fields.
pub fn render_model_topology_view_file(
    path: &Path,
    projection: ModelTopologyProjectionV1,
) -> Result<String, WorkbenchError> {
    render_model_topology_view_file_localized(path, WorkbenchReportLocaleV1::EnUs, projection)
}

/// Read one bounded regular `ModelIR` file and render a localized verified C++ snapshot.
///
/// # Errors
///
/// Rejects unsafe input files, invalid `ModelIR`, C++ semantic rejection, unsupported projection
/// inventory sizes, or malformed snapshot fields.
pub fn render_model_topology_view_file_localized(
    path: &Path,
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
) -> Result<String, WorkbenchError> {
    let bytes = read_bounded_regular_file(path, MAX_MODEL_BYTES)?;
    render_model_topology_view_localized(&bytes, locale, projection)
}

/// Render a deterministic ANSI-free terminal topology view from one `ModelIR` byte stream.
///
/// # Errors
///
/// Rejects invalid `ModelIR`, a C++ semantically invalid snapshot, oversized topology inventory, or
/// missing/mistyped snapshot fields.
pub fn render_model_topology_view(
    model_ir_bytes: &[u8],
    projection: ModelTopologyProjectionV1,
) -> Result<String, WorkbenchError> {
    render_model_topology_view_localized(model_ir_bytes, WorkbenchReportLocaleV1::EnUs, projection)
}

/// Render a localized deterministic ANSI-free topology view from one `ModelIR` byte stream.
///
/// # Errors
///
/// Rejects invalid `ModelIR`, a C++ semantically invalid snapshot, oversized topology inventory, or
/// missing/mistyped snapshot fields.
pub fn render_model_topology_view_localized(
    model_ir_bytes: &[u8],
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
) -> Result<String, WorkbenchError> {
    let length = u64::try_from(model_ir_bytes.len()).map_err(|_| {
        WorkbenchError::new(
            "workbench_model_view_input_too_large",
            "ModelIR byte length exceeds the viewer representation",
        )
    })?;
    if length > MAX_MODEL_BYTES {
        return Err(WorkbenchError::new(
            "workbench_model_view_input_too_large",
            "ModelIR exceeds the bounded viewer input limit",
        ));
    }
    let validation = validate_model_bytes(model_ir_bytes)
        .map_err(|error| input_error("workbench_model_view_validation_failed", &error))?;
    if !validation.report.contract_valid || !validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_view_semantics_invalid",
            "native C++ validation rejected the ModelIR semantic topology",
        ));
    }
    let snapshot = validation.snapshot.value();
    let nodes_value = array_field(snapshot, "nodes")?;
    let elements_value = array_field(snapshot, "elements")?;
    if nodes_value.len() > MAX_VIEW_NODES || elements_value.len() > MAX_VIEW_ELEMENTS {
        return Err(WorkbenchError::new(
            "workbench_model_view_inventory_too_large",
            format!(
                "viewer supports at most {MAX_VIEW_NODES} nodes and {MAX_VIEW_ELEMENTS} elements"
            ),
        ));
    }

    let supported_nodes = reference_ids(array_field(snapshot, "constraints")?, "node_id")?;
    let loaded_nodes = loaded_node_ids(array_field(snapshot, "load_patterns")?)?;
    let mut nodes = parse_nodes(nodes_value, &supported_nodes, &loaded_nodes)?;
    let elements = parse_elements(elements_value)?;
    let analysis_types = analysis_types(array_field(snapshot, "load_patterns")?)?;
    project_nodes(&mut nodes, projection);
    let (canvas, projected_collision_count) = render_canvas(&nodes, &elements)?;

    let metadata = ViewMetadata {
        model_id: validation.report.model_id,
        capability_profile: validation.snapshot.capability_profile().to_owned(),
        content_hash: validation.report.content_hash,
        semantic_hash: validation.report.semantic_hash,
        provenance_hash: validation.report.provenance_hash,
        analysis_ready: validation.report.analysis_ready,
        blocking_features: validation.report.blocking_feature_ids,
        constraint_count: validation.report.entity_counts.constraints,
        load_pattern_count: validation.report.entity_counts.load_patterns,
    };
    Ok(format_topology_view(
        &metadata,
        locale,
        projection,
        &nodes,
        &elements,
        &analysis_types,
        &canvas,
        projected_collision_count,
    ))
}

#[allow(clippy::too_many_arguments, clippy::too_many_lines)]
fn format_topology_view(
    metadata: &ViewMetadata,
    locale: WorkbenchReportLocaleV1,
    projection: ModelTopologyProjectionV1,
    nodes: &[ViewNode],
    elements: &[ViewElement],
    analysis_types: &BTreeSet<String>,
    canvas: &[Vec<char>],
    projected_collision_count: usize,
) -> String {
    let labels = model_view_labels(locale);
    let mut output = String::new();
    writeln!(output, "{}", labels.title).expect("String writes cannot fail");
    writeln!(output, "{}: {VIEW_SCHEMA_V1}", labels.schema).expect("String writes cannot fail");
    if let Some(locale_label) = labels.locale {
        writeln!(output, "{locale_label}: {}", locale.label()).expect("String writes cannot fail");
    }
    writeln!(output, "{}: {}", labels.model, metadata.model_id).expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.capability_profile, metadata.capability_profile
    )
    .expect("String writes cannot fail");
    writeln!(output, "{}: {}", labels.projection, projection.label())
        .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {VIEW_WIDTH}x{VIEW_HEIGHT} cells",
        labels.viewport
    )
    .expect("String writes cannot fail");
    writeln!(output, "{}: {}", labels.content_hash, metadata.content_hash)
        .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.semantic_hash, metadata.semantic_hash
    )
    .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.provenance_hash, metadata.provenance_hash
    )
    .expect("String writes cannot fail");
    writeln!(output, "{}: verified", labels.semantic_snapshot).expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.analysis_ready, metadata.analysis_ready
    )
    .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.blocking_features,
        if metadata.blocking_features.is_empty() {
            "none".to_owned()
        } else {
            metadata.blocking_features.join(",")
        }
    )
    .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: {}",
        labels.analysis_types,
        if analysis_types.is_empty() {
            "none".to_owned()
        } else {
            analysis_types.iter().cloned().collect::<Vec<_>>().join(",")
        }
    )
    .expect("String writes cannot fail");
    writeln!(
        output,
        "{}: nodes={} elements={} constraints={} load_patterns={} projected_collisions={projected_collision_count}",
        labels.inventory,
        nodes.len(),
        elements.len(),
        metadata.constraint_count,
        metadata.load_pattern_count,
    )
    .expect("String writes cannot fail");
    writeln!(output, "{}", labels.legend).expect("String writes cannot fail");
    let border = format!("+{}+", "-".repeat(VIEW_WIDTH));
    writeln!(output, "{border}").expect("String writes cannot fail");
    for row in canvas {
        writeln!(output, "|{}|", row.iter().collect::<String>())
            .expect("String writes cannot fail");
    }
    writeln!(output, "{border}").expect("String writes cannot fail");
    writeln!(output, "{}", labels.nodes).expect("String writes cannot fail");
    for node in nodes {
        writeln!(
            output,
            "  {} [{},{}] xyz_m=[{},{},{}] flags={}",
            node.id,
            node.column,
            node.row,
            format_number(node.coordinates[0]),
            format_number(node.coordinates[1]),
            format_number(node.coordinates[2]),
            node_flags(node),
        )
        .expect("String writes cannot fail");
    }
    writeln!(output, "{}", labels.elements).expect("String writes cannot fail");
    for element in elements {
        writeln!(
            output,
            "  {} {} {} -> {}",
            element.id, element.kind, element.first_node_id, element.second_node_id
        )
        .expect("String writes cannot fail");
    }
    writeln!(output, "{}: {CLAIM_BOUNDARY}", labels.claim_boundary)
        .expect("String writes cannot fail");
    let view_hash = sha256_identity(output.as_bytes());
    writeln!(output, "{}: {view_hash}", labels.view_hash).expect("String writes cannot fail");
    output
}

fn model_view_labels(locale: WorkbenchReportLocaleV1) -> ModelViewLabels {
    match locale {
        WorkbenchReportLocaleV1::EnUs => ModelViewLabels {
            title: "Structural Native Workbench - Model topology view",
            locale: None,
            schema: "Schema",
            model: "Model",
            capability_profile: "Capability profile",
            projection: "Projection",
            viewport: "Viewport",
            content_hash: "Content hash",
            semantic_hash: "Semantic hash",
            provenance_hash: "Provenance hash",
            semantic_snapshot: "C++ semantic snapshot",
            analysis_ready: "Analysis ready",
            blocking_features: "Blocking features",
            analysis_types: "Analysis types",
            inventory: "Inventory",
            legend: "Legend: o=node #=support ^=load *=support+load @=projected collision",
            nodes: "Nodes (projected column,row; SI coordinates):",
            elements: "Elements:",
            claim_boundary: "Claim boundary",
            view_hash: "View hash",
        },
        WorkbenchReportLocaleV1::KoKr => ModelViewLabels {
            title: "Structural Native Workbench - 모델 위상 뷰",
            locale: Some("로케일"),
            schema: "스키마",
            model: "모델",
            capability_profile: "기능 프로파일",
            projection: "투영",
            viewport: "뷰포트",
            content_hash: "콘텐츠 해시",
            semantic_hash: "의미 해시",
            provenance_hash: "출처 해시",
            semantic_snapshot: "C++ 의미 스냅샷",
            analysis_ready: "해석 준비",
            blocking_features: "차단 기능",
            analysis_types: "해석 유형",
            inventory: "재고",
            legend: "범례: o=절점 #=지지 ^=하중 *=지지+하중 @=투영 중첩",
            nodes: "절점 (투영 column,row; SI 좌표):",
            elements: "요소:",
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
        .ok_or_else(|| snapshot_error(field))
}

fn reference_ids(values: &[Value], field: &str) -> Result<BTreeSet<String>, WorkbenchError> {
    values
        .iter()
        .map(|value| string_field(value, field).map(ToOwned::to_owned))
        .collect()
}

fn loaded_node_ids(load_patterns: &[Value]) -> Result<BTreeSet<String>, WorkbenchError> {
    let mut nodes = BTreeSet::new();
    for pattern in load_patterns {
        for load in array_field(pattern, "nodal_loads")? {
            nodes.insert(string_field(load, "node_id")?.to_owned());
        }
    }
    Ok(nodes)
}

fn analysis_types(load_patterns: &[Value]) -> Result<BTreeSet<String>, WorkbenchError> {
    load_patterns
        .iter()
        .map(|pattern| string_field(pattern, "analysis_type").map(ToOwned::to_owned))
        .collect()
}

fn parse_nodes(
    values: &[Value],
    supported_nodes: &BTreeSet<String>,
    loaded_nodes: &BTreeSet<String>,
) -> Result<Vec<ViewNode>, WorkbenchError> {
    let mut nodes = values
        .iter()
        .map(|value| {
            let id = string_field(value, "id")?.to_owned();
            let coordinates = array_field(value, "coordinates_m")?;
            if coordinates.len() != 3 {
                return Err(snapshot_error("coordinates_m"));
            }
            let mut typed = [0.0; 3];
            for (target, source) in typed.iter_mut().zip(coordinates) {
                *target = source
                    .as_f64()
                    .filter(|coordinate| coordinate.is_finite())
                    .ok_or_else(|| snapshot_error("coordinates_m"))?;
            }
            Ok(ViewNode {
                supported: supported_nodes.contains(&id),
                loaded: loaded_nodes.contains(&id),
                id,
                index: integer_field(value, "index")?,
                coordinates: typed,
                column: 0,
                row: 0,
            })
        })
        .collect::<Result<Vec<_>, WorkbenchError>>()?;
    nodes.sort_by(|left, right| (left.index, &left.id).cmp(&(right.index, &right.id)));
    Ok(nodes)
}

fn parse_elements(values: &[Value]) -> Result<Vec<ViewElement>, WorkbenchError> {
    let mut elements = values
        .iter()
        .map(|value| {
            let node_ids = array_field(value, "node_ids")?;
            if node_ids.len() != 2 {
                return Err(snapshot_error("node_ids"));
            }
            Ok(ViewElement {
                id: string_field(value, "id")?.to_owned(),
                index: integer_field(value, "index")?,
                kind: string_field(value, "type")?.to_owned(),
                first_node_id: node_ids[0]
                    .as_str()
                    .ok_or_else(|| snapshot_error("node_ids"))?
                    .to_owned(),
                second_node_id: node_ids[1]
                    .as_str()
                    .ok_or_else(|| snapshot_error("node_ids"))?
                    .to_owned(),
            })
        })
        .collect::<Result<Vec<_>, WorkbenchError>>()?;
    elements.sort_by(|left, right| (left.index, &left.id).cmp(&(right.index, &right.id)));
    Ok(elements)
}

fn project_nodes(nodes: &mut [ViewNode], projection: ModelTopologyProjectionV1) {
    let projected = nodes
        .iter()
        .map(|node| projection.project(node.coordinates))
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
    let span_u = max_u - min_u;
    let span_v = max_v - min_v;
    let width = VIEW_MAX_COLUMN_F64;
    let height = VIEW_MAX_ROW_F64;
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
    let used_width = span_u * finite_scale;
    let used_height = span_v * finite_scale;
    let offset_u = (width - used_width) * 0.5;
    let offset_v = (height - used_height) * 0.5;
    for (node, point) in nodes.iter_mut().zip(projected) {
        node.column = bounded_cell((point.0 - min_u) * finite_scale + offset_u, width);
        let from_bottom = bounded_cell((point.1 - min_v) * finite_scale + offset_v, height);
        node.row = VIEW_HEIGHT - 1 - from_bottom;
    }
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn bounded_cell(value: f64, maximum: f64) -> usize {
    // The finite value is clamped to the fixed 0..=72/24 terminal-grid bounds.
    value.round().clamp(0.0, maximum) as usize
}

fn render_canvas(
    nodes: &[ViewNode],
    elements: &[ViewElement],
) -> Result<(Vec<Vec<char>>, usize), WorkbenchError> {
    let positions = nodes
        .iter()
        .map(|node| (node.id.as_str(), (node.column, node.row)))
        .collect::<BTreeMap<_, _>>();
    let mut canvas = vec![vec![' '; VIEW_WIDTH]; VIEW_HEIGHT];
    for element in elements {
        let first = positions
            .get(element.first_node_id.as_str())
            .copied()
            .ok_or_else(|| snapshot_error("element first node"))?;
        let second = positions
            .get(element.second_node_id.as_str())
            .copied()
            .ok_or_else(|| snapshot_error("element second node"))?;
        draw_line(&mut canvas, first, second);
    }
    let mut collisions = BTreeMap::<(usize, usize), Vec<&ViewNode>>::new();
    for node in nodes {
        collisions
            .entry((node.column, node.row))
            .or_default()
            .push(node);
    }
    let projected_collision_count = collisions.values().filter(|group| group.len() > 1).count();
    for ((column, row), group) in collisions {
        canvas[row][column] = if group.len() > 1 {
            '@'
        } else {
            node_glyph(group[0])
        };
    }
    Ok((canvas, projected_collision_count))
}

fn draw_line(canvas: &mut [Vec<char>], first: (usize, usize), second: (usize, usize)) {
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
    let glyph = line_glyph(first, second);
    loop {
        let cell = &mut canvas[usize::try_from(row).expect("view row stays nonnegative")]
            [usize::try_from(column).expect("view column stays nonnegative")];
        *cell = merge_line_glyph(*cell, glyph);
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

fn line_glyph(first: (usize, usize), second: (usize, usize)) -> char {
    if first.0 == second.0 {
        '|'
    } else if first.1 == second.1 {
        '-'
    } else if (first.0 < second.0) == (first.1 < second.1) {
        '\\'
    } else {
        '/'
    }
}

fn merge_line_glyph(existing: char, incoming: char) -> char {
    match existing {
        ' ' => incoming,
        value if value == incoming => value,
        _ => '+',
    }
}

fn node_glyph(node: &ViewNode) -> char {
    match (node.supported, node.loaded) {
        (false, false) => 'o',
        (true, false) => '#',
        (false, true) => '^',
        (true, true) => '*',
    }
}

fn node_flags(node: &ViewNode) -> &'static str {
    match (node.supported, node.loaded) {
        (false, false) => "none",
        (true, false) => "support",
        (false, true) => "load",
        (true, true) => "support,load",
    }
}

fn string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error(field))
}

fn integer_field(value: &Value, field: &str) -> Result<u64, WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| snapshot_error(field))
}

fn snapshot_error(field: &str) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_model_view_snapshot_invalid",
        format!("verified ModelIR snapshot has an invalid {field} field"),
    )
}

fn format_number(value: f64) -> String {
    if value == 0.0 {
        "0".to_owned()
    } else {
        value.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::ModelTopologyProjectionV1;

    #[test]
    fn projection_contract_is_exact_and_case_sensitive() {
        for (label, projection) in [
            ("isometric", ModelTopologyProjectionV1::Isometric),
            ("xy", ModelTopologyProjectionV1::Xy),
            ("xz", ModelTopologyProjectionV1::Xz),
            ("yz", ModelTopologyProjectionV1::Yz),
        ] {
            assert_eq!(ModelTopologyProjectionV1::parse(label), Some(projection));
            assert_eq!(projection.label(), label);
        }
        assert_eq!(ModelTopologyProjectionV1::parse("XY"), None);
        assert_eq!(ModelTopologyProjectionV1::parse("perspective"), None);
    }
}
