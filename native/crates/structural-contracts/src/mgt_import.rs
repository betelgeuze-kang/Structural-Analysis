//! Bounded, fail-closed MIDAS MGT import-health ownership.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2, ModelIrV2Document};

pub const MGT_IMPORT_HEALTH_V1: &str = "structural-native-mgt-import-health.v1";
pub const MGT_IMPORT_MAX_SOURCE_BYTES: usize = 64 * 1024 * 1024;

const NORMALIZER_ID: &str = "structural-native-mgt-import";
const NORMALIZER_VERSION: &str = "1";
const MAX_ENTITY_COUNT: usize = 1_000_000;
const DOFS: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];

/// Stable import outcome. A blocked parse still owns and inventories the original bytes.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MgtImportStatusV1 {
    Normalized,
    Blocked,
}

/// Loss disposition for one non-comment source row.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MgtRowDispositionKindV1 {
    Mapped,
    PreservedOnly,
    Dropped,
    Unsupported,
}

/// Exact source-byte identity owned by the Rust import boundary.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MgtSourceIdentityV1 {
    pub source_hash: String,
    pub byte_length: u64,
    pub encoding: String,
    pub line_count: u64,
}

/// One auditable source-row disposition without duplicating potentially sensitive source text.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MgtRowDispositionV1 {
    pub section: String,
    pub section_row_index: u64,
    pub source_line: u64,
    pub source_row_hash: String,
    pub disposition: MgtRowDispositionKindV1,
    pub reason_code: String,
    pub target_ids: Vec<String>,
}

/// Stable import diagnostic. Blockers prevent `ModelIR` publication.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MgtImportDiagnosticV1 {
    pub severity: String,
    pub code: String,
    pub path: String,
    pub source_line: Option<u64>,
    pub detail: String,
}

/// Three deterministic identities for a successfully normalized `ModelIR`.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MgtNormalizedModelIdentityV1 {
    pub model_id: String,
    pub content_hash: String,
    pub semantic_hash: String,
    pub provenance_hash: String,
}

/// Canonical import-health document emitted for both normalized and blocked inputs.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MgtImportHealthV1 {
    pub schema_version: String,
    pub status: MgtImportStatusV1,
    pub source: MgtSourceIdentityV1,
    pub model_id: String,
    pub section_counts: BTreeMap<String, u64>,
    pub dispositions: Vec<MgtRowDispositionV1>,
    pub diagnostics: Vec<MgtImportDiagnosticV1>,
    pub mapped_row_count: u64,
    pub preserved_only_row_count: u64,
    pub dropped_row_count: u64,
    pub unsupported_row_count: u64,
    pub blocker_count: u64,
    pub normalized_model: Option<MgtNormalizedModelIdentityV1>,
    pub claim_boundary: String,
    pub health_hash: String,
}

/// Immutable source, health report and optional strict `ModelIR` produced by one import.
#[derive(Clone, Debug)]
pub struct MgtImportDocumentV1 {
    source_bytes: Vec<u8>,
    health: MgtImportHealthV1,
    health_json: String,
    model: Option<ModelIrV2Document>,
}

impl MgtImportDocumentV1 {
    #[must_use]
    pub fn source_bytes(&self) -> &[u8] {
        &self.source_bytes
    }

    #[must_use]
    pub const fn health(&self) -> &MgtImportHealthV1 {
        &self.health
    }

    #[must_use]
    pub fn health_json(&self) -> &str {
        &self.health_json
    }

    #[must_use]
    pub fn model(&self) -> Option<&ModelIrV2Document> {
        self.model.as_ref()
    }

    #[must_use]
    pub const fn is_normalized(&self) -> bool {
        matches!(self.health.status, MgtImportStatusV1::Normalized)
    }
}

/// Stable contract failure for bounded import misuse or an internal normalization invariant.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MgtImportError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for MgtImportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for MgtImportError {}

#[derive(Clone, Debug)]
struct RawRow {
    section: String,
    section_row_index: usize,
    source_line: usize,
    source_text: String,
    text: String,
}

type CollectedRows = (
    Vec<RawRow>,
    BTreeMap<String, u64>,
    Vec<MgtImportDiagnosticV1>,
);

#[derive(Clone, Debug)]
struct UnitRow {
    force: String,
    length: String,
    force_to_n: f64,
    length_to_m: f64,
}

#[derive(Clone, Debug)]
struct NodeRow {
    id: u64,
    coordinates: [f64; 3],
    source_line: usize,
}

#[derive(Clone, Debug)]
struct MaterialRow {
    id: u64,
    elastic_modulus: f64,
    poisson_ratio: f64,
    density: f64,
    source_line: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SectionFamily {
    Frame,
    Truss,
}

#[derive(Clone, Debug)]
struct SectionRow {
    id: u64,
    family: SectionFamily,
    values: Vec<f64>,
    source_line: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ElementFamily {
    Frame,
    Truss,
}

#[derive(Clone, Debug)]
struct ElementRow {
    id: u64,
    family: ElementFamily,
    material_id: u64,
    section_id: u64,
    node_i: u64,
    node_j: u64,
    angle_deg: f64,
    source_line: usize,
}

#[derive(Clone, Debug)]
struct ConstraintRow {
    node_id: u64,
    fixed: [bool; 6],
    source_line: usize,
}

#[derive(Clone, Debug)]
struct LoadCaseRow {
    name: String,
    source_line: usize,
}

#[derive(Clone, Debug)]
struct NodalLoadRow {
    node_id: u64,
    components: [f64; 6],
    source_line: usize,
}

#[derive(Default)]
struct ParsedMgt {
    unit: Option<UnitRow>,
    nodes: BTreeMap<u64, NodeRow>,
    materials: BTreeMap<u64, MaterialRow>,
    sections: BTreeMap<u64, SectionRow>,
    elements: BTreeMap<u64, ElementRow>,
    constraints: BTreeMap<u64, ConstraintRow>,
    load_cases: Vec<LoadCaseRow>,
    nodal_loads: Vec<NodalLoadRow>,
}

/// Parse MGT bytes, preserve every data-row disposition and emit `ModelIR` only for the exact
/// numeric frame/truss subset. Invalid encoding and unsupported source constructs are data-level
/// blockers rather than lossy decode success.
///
/// # Errors
///
/// Returns an error for an invalid requested model ID, source larger than the public bound,
/// allocation failure, or an internal ModelIR/canonicalization invariant.
#[allow(clippy::too_many_lines)]
pub fn import_mgt_v1(
    source_bytes: &[u8],
    model_id: &str,
) -> Result<MgtImportDocumentV1, MgtImportError> {
    validate_stable_id(model_id, "/model_id")?;
    if source_bytes.len() > MGT_IMPORT_MAX_SOURCE_BYTES {
        return Err(import_error(
            "mgt_source_too_large",
            "/source",
            "MGT source exceeds the 64 MiB import bound",
        ));
    }
    let mut owned_source = Vec::new();
    owned_source
        .try_reserve_exact(source_bytes.len())
        .map_err(|_| {
            import_error(
                "mgt_source_allocation_failed",
                "/source",
                "MGT source allocation failed",
            )
        })?;
    owned_source.extend_from_slice(source_bytes);

    let source_hash = sha256_identity(source_bytes);
    let (encoding, text) = match decode_source(source_bytes) {
        Ok(decoded) => decoded,
        Err(valid_up_to) => {
            let diagnostic = MgtImportDiagnosticV1 {
                severity: "blocker".to_owned(),
                code: "mgt_encoding_unsupported".to_owned(),
                path: "/source/encoding".to_owned(),
                source_line: None,
                detail: format!(
                    "source is not strict UTF-8; first invalid byte offset is {valid_up_to}"
                ),
            };
            return finish_document(
                owned_source,
                source_identity(source_bytes, &source_hash, "unsupported", 0)?,
                model_id,
                BTreeMap::new(),
                Vec::new(),
                vec![diagnostic],
                None,
            );
        }
    };
    let line_count = text.lines().count();
    let (rows, section_counts, mut diagnostics) = collect_rows(text)?;
    let mut dispositions = Vec::with_capacity(rows.len());
    let mut parsed = ParsedMgt::default();
    for row in &rows {
        process_row(row, &mut parsed, &mut dispositions, &mut diagnostics)?;
    }
    validate_normalization_graph(&parsed, &mut dispositions, &mut diagnostics)?;
    sort_evidence(&mut dispositions, &mut diagnostics);
    let has_blocker = diagnostics
        .iter()
        .any(|diagnostic| diagnostic.severity == "blocker");
    let source = source_identity(source_bytes, &source_hash, encoding, line_count)?;
    if has_blocker {
        return finish_document(
            owned_source,
            source,
            model_id,
            section_counts,
            dispositions,
            diagnostics,
            None,
        );
    }
    let model = build_model_ir(model_id, &source_hash, encoding, &parsed)?;
    finish_document(
        owned_source,
        source,
        model_id,
        section_counts,
        dispositions,
        diagnostics,
        Some(model),
    )
}

fn decode_source(source: &[u8]) -> Result<(&'static str, &str), usize> {
    if let Some(without_bom) = source.strip_prefix(&[0xef, 0xbb, 0xbf]) {
        std::str::from_utf8(without_bom)
            .map(|text| ("utf-8-bom", text))
            .map_err(|error| error.valid_up_to() + 3)
    } else {
        std::str::from_utf8(source)
            .map(|text| ("utf-8", text))
            .map_err(|error| error.valid_up_to())
    }
}

fn collect_rows(text: &str) -> Result<CollectedRows, MgtImportError> {
    let mut rows = Vec::new();
    let mut counts = BTreeMap::<String, u64>::new();
    let mut diagnostics = Vec::new();
    let mut current = "ROOT".to_owned();
    counts.insert(current.clone(), 0);
    for (zero_line, raw) in text.lines().enumerate() {
        let source_line = zero_line + 1;
        let Some(line) = clean_line(raw) else {
            continue;
        };
        if let Some(header) = line.strip_prefix('*') {
            let section = header
                .split(',')
                .next()
                .map(str::trim)
                .unwrap_or_default()
                .to_ascii_uppercase();
            if section.is_empty()
                || !section
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
            {
                diagnostics.push(blocker(
                    "mgt_section_header_invalid",
                    "/sections",
                    Some(source_line),
                    "section header is empty or outside the bounded ASCII grammar",
                ));
                "INVALID".clone_into(&mut current);
            } else {
                current = section;
            }
            counts.entry(current.clone()).or_insert(0);
            continue;
        }
        if rows.len() >= MAX_ENTITY_COUNT {
            return Err(import_error(
                "mgt_row_count_exceeded",
                "/source",
                "MGT source exceeds the bounded non-comment row count",
            ));
        }
        let count = counts.entry(current.clone()).or_insert(0);
        let section_row_index = usize::try_from(*count).map_err(|_| {
            import_error(
                "mgt_row_index_overflow",
                "/source",
                "MGT section row index exceeds the platform range",
            )
        })?;
        *count = count.checked_add(1).ok_or_else(|| {
            import_error(
                "mgt_row_count_overflow",
                "/source",
                "MGT section row count overflowed",
            )
        })?;
        rows.push(RawRow {
            section: current.clone(),
            section_row_index,
            source_line,
            source_text: raw.to_owned(),
            text: line,
        });
    }
    if counts.get("ROOT") == Some(&0) {
        counts.remove("ROOT");
    }
    Ok((rows, counts, diagnostics))
}

fn clean_line(raw: &str) -> Option<String> {
    let stripped = raw.trim_start();
    if stripped.is_empty() || stripped.starts_with('#') || stripped.starts_with('$') {
        return None;
    }
    let without_comment = raw.split(';').next().unwrap_or_default().trim();
    (!without_comment.is_empty()).then(|| without_comment.to_owned())
}

fn tokens(row: &RawRow) -> Vec<&str> {
    let mut values = row.text.split(',').map(str::trim).collect::<Vec<_>>();
    while values.last().is_some_and(|value| value.is_empty()) {
        values.pop();
    }
    values
}

#[allow(clippy::too_many_lines)]
fn process_row(
    row: &RawRow,
    parsed: &mut ParsedMgt,
    dispositions: &mut Vec<MgtRowDispositionV1>,
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
) -> Result<(), MgtImportError> {
    let values = tokens(row);
    match row.section.as_str() {
        "VERSION" | "GROUP" => push_disposition(
            dispositions,
            row,
            MgtRowDispositionKindV1::PreservedOnly,
            "mgt_metadata_preserved",
            Vec::new(),
        )?,
        "UNIT" => match parse_unit(&values) {
            Some(unit) if parsed.unit.is_none() => {
                parsed.unit = Some(unit);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_unit_mapped",
                    Vec::new(),
                )?;
            }
            Some(_) => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_unit_duplicate",
                "multiple unit rows are ambiguous",
            )?,
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_unit_unsupported",
                "unit row is outside the supported force/length grammar",
            )?,
        },
        "NODE" => match parse_node(&values, row.source_line) {
            Some(node) if !parsed.nodes.contains_key(&node.id) => {
                let target = entity_id("N", node.id);
                parsed.nodes.insert(node.id, node);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_node_mapped",
                    vec![target],
                )?;
            }
            Some(node) => duplicate_entity(dispositions, diagnostics, row, "node", node.id)?,
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_node_row_invalid",
                "node row requires one positive integer ID and three finite coordinates",
            )?,
        },
        "MATERIAL" => match parse_material(&values, row.source_line) {
            Some(material) if !parsed.materials.contains_key(&material.id) => {
                let target = entity_id("M", material.id);
                parsed.materials.insert(material.id, material);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_linear_material_mapped",
                    vec![target],
                )?;
            }
            Some(material) => {
                duplicate_entity(dispositions, diagnostics, row, "material", material.id)?;
            }
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_material_properties_unsupported",
                "material row lacks the exact linear E, Poisson ratio and density fields",
            )?,
        },
        "SECTION" => match parse_section(&values, row.source_line) {
            Some(section) if !parsed.sections.contains_key(&section.id) => {
                let target = entity_id("S", section.id);
                parsed.sections.insert(section.id, section);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_section_mapped",
                    vec![target],
                )?;
            }
            Some(section) => {
                duplicate_entity(dispositions, diagnostics, row, "section", section.id)?;
            }
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_section_properties_unsupported",
                "section row lacks the exact FRAME or TRUSS numeric property fields",
            )?,
        },
        "ELEMENT" => {
            if values.get(1).is_some_and(|value| {
                let upper = value.to_ascii_uppercase();
                upper.contains("PLATE")
                    || upper.contains("SHELL")
                    || upper.contains("WALL")
                    || upper.contains("SOLID")
            }) {
                dropped(
                    dispositions,
                    diagnostics,
                    row,
                    "mgt_element_family_dropped",
                    "shell, wall and solid elements are outside this frame/truss import slice",
                )?;
            } else {
                match parse_element(&values, row.source_line) {
                    Some(element) if !parsed.elements.contains_key(&element.id) => {
                        let target = entity_id("E", element.id);
                        parsed.elements.insert(element.id, element);
                        push_disposition(
                            dispositions,
                            row,
                            MgtRowDispositionKindV1::Mapped,
                            "mgt_element_mapped",
                            vec![target],
                        )?;
                    }
                    Some(element) => {
                        duplicate_entity(dispositions, diagnostics, row, "element", element.id)?;
                    }
                    None => unsupported(
                        dispositions,
                        diagnostics,
                        row,
                        "mgt_element_row_unsupported",
                        "element row is outside the exact BEAM/FRAME/TRUSS grammar",
                    )?,
                }
            }
        }
        "CONSTRAINT" | "SUPPORT" => match parse_constraint(&values, row.source_line) {
            Some(constraint) if !parsed.constraints.contains_key(&constraint.node_id) => {
                let target = entity_id("C", constraint.node_id);
                parsed.constraints.insert(constraint.node_id, constraint);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_constraint_mapped",
                    vec![target],
                )?;
            }
            Some(constraint) => duplicate_entity(
                dispositions,
                diagnostics,
                row,
                "constraint_node",
                constraint.node_id,
            )?,
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_constraint_row_unsupported",
                "constraint row requires one node and a six-character binary DOF mask",
            )?,
        },
        "STLDCASE" | "LOADCASE" => match parse_load_case(&values, row.source_line) {
            Some(load_case)
                if !parsed
                    .load_cases
                    .iter()
                    .any(|existing| existing.name == load_case.name) =>
            {
                let target = format!("LP_{}", load_case.name);
                parsed.load_cases.push(load_case);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_load_case_mapped",
                    vec![target],
                )?;
            }
            Some(_) => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_load_case_duplicate",
                "load-case name is duplicated",
            )?,
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_load_case_row_unsupported",
                "load-case row requires an ASCII stable ID",
            )?,
        },
        "CONLOAD" => match parse_nodal_load(&values, row.source_line) {
            Some(load) => {
                let target = format!("L_{}_{}", load.node_id, parsed.nodal_loads.len());
                parsed.nodal_loads.push(load);
                push_disposition(
                    dispositions,
                    row,
                    MgtRowDispositionKindV1::Mapped,
                    "mgt_nodal_load_mapped",
                    vec![target],
                )?;
            }
            None => unsupported(
                dispositions,
                diagnostics,
                row,
                "mgt_nodal_load_row_unsupported",
                "nodal load requires one node ID and six finite components",
            )?,
        },
        "ROOT" | "INVALID" => unsupported(
            dispositions,
            diagnostics,
            row,
            "mgt_unsectioned_row_unsupported",
            "data row appears outside a valid section",
        )?,
        _ => unsupported(
            dispositions,
            diagnostics,
            row,
            "mgt_section_unsupported",
            "section is preserved in the source artifact but has no native mapping",
        )?,
    }
    Ok(())
}

fn parse_unit(values: &[&str]) -> Option<UnitRow> {
    if !(2..=3).contains(&values.len())
        || values
            .get(2)
            .is_some_and(|temperature| !temperature.eq_ignore_ascii_case("C"))
    {
        return None;
    }
    let force = values[0].to_ascii_uppercase();
    let length = values[1].to_ascii_uppercase();
    let (force_name, force_to_n) = match force.as_str() {
        "N" => ("N", 1.0),
        "KN" => ("kN", 1_000.0),
        "MN" => ("MN", 1_000_000.0),
        "LBF" => ("lbf", 4.448_221_615_260_5),
        "KIP" => ("kip", 4_448.221_615_260_5),
        _ => return None,
    };
    let (length_name, length_to_m) = match length.as_str() {
        "M" => ("m", 1.0),
        "MM" => ("mm", 0.001),
        "CM" => ("cm", 0.01),
        "FT" => ("ft", 0.3048),
        "IN" => ("in", 0.0254),
        _ => return None,
    };
    Some(UnitRow {
        force: force_name.to_owned(),
        length: length_name.to_owned(),
        force_to_n,
        length_to_m,
    })
}

fn parse_node(values: &[&str], source_line: usize) -> Option<NodeRow> {
    if values.len() != 4 {
        return None;
    }
    let id = positive_id(values.first()?)?;
    let coordinates = [
        finite_f64(values.get(1)?)?,
        finite_f64(values.get(2)?)?,
        finite_f64(values.get(3)?)?,
    ];
    Some(NodeRow {
        id,
        coordinates,
        source_line,
    })
}

fn parse_material(values: &[&str], source_line: usize) -> Option<MaterialRow> {
    if values.len() != 5 {
        return None;
    }
    let id = positive_id(values.first()?)?;
    let law = values.get(1)?.to_ascii_uppercase();
    if !matches!(law.as_str(), "STEEL" | "CONC" | "LINEAR" | "ELASTIC") {
        return None;
    }
    let elastic_modulus = finite_f64(values.get(2)?)?;
    let poisson_ratio = finite_f64(values.get(3)?)?;
    let density = finite_f64(values.get(4)?)?;
    if elastic_modulus <= 0.0 || !(-1.0..0.5).contains(&poisson_ratio) || density < 0.0 {
        return None;
    }
    Some(MaterialRow {
        id,
        elastic_modulus,
        poisson_ratio,
        density,
        source_line,
    })
}

fn parse_section(values: &[&str], source_line: usize) -> Option<SectionRow> {
    let id = positive_id(values.first()?)?;
    let family = match values.get(1)?.to_ascii_uppercase().as_str() {
        "FRAME" => SectionFamily::Frame,
        "TRUSS" => SectionFamily::Truss,
        _ => return None,
    };
    let expected = if family == SectionFamily::Frame { 8 } else { 3 };
    if values.len() != expected {
        return None;
    }
    let numeric = values[2..expected]
        .iter()
        .map(|value| finite_f64(value))
        .collect::<Option<Vec<_>>>()?;
    if numeric.iter().any(|value| *value <= 0.0) {
        return None;
    }
    Some(SectionRow {
        id,
        family,
        values: numeric,
        source_line,
    })
}

fn parse_element(values: &[&str], source_line: usize) -> Option<ElementRow> {
    if !(6..=8).contains(&values.len())
        || values
            .get(7)
            .is_some_and(|flag| finite_f64(flag) != Some(0.0))
    {
        return None;
    }
    let id = positive_id(values.first()?)?;
    let family = match values.get(1)?.to_ascii_uppercase().as_str() {
        "BEAM" | "FRAME" | "COLUMN" => ElementFamily::Frame,
        "TRUSS" => ElementFamily::Truss,
        _ => return None,
    };
    let material_id = positive_id(values.get(2)?)?;
    let section_id = positive_id(values.get(3)?)?;
    let node_i = positive_id(values.get(4)?)?;
    let node_j = positive_id(values.get(5)?)?;
    let angle_deg = values.get(6).map_or(Some(0.0), |value| finite_f64(value))?;
    (node_i != node_j).then_some(ElementRow {
        id,
        family,
        material_id,
        section_id,
        node_i,
        node_j,
        angle_deg,
        source_line,
    })
}

fn parse_constraint(values: &[&str], source_line: usize) -> Option<ConstraintRow> {
    if values.len() != 2 {
        return None;
    }
    let node_id = positive_id(values.first()?)?;
    let mask = values.get(1)?.as_bytes();
    if mask.len() != 6 || mask.iter().any(|value| !matches!(value, b'0' | b'1')) {
        return None;
    }
    let mut fixed = [false; 6];
    for (target, source) in fixed.iter_mut().zip(mask) {
        *target = *source == b'1';
    }
    fixed.iter().any(|value| *value).then_some(ConstraintRow {
        node_id,
        fixed,
        source_line,
    })
}

fn parse_load_case(values: &[&str], source_line: usize) -> Option<LoadCaseRow> {
    if values.is_empty()
        || values.len() > 2
        || values.get(1).is_some_and(|kind| {
            !matches!(
                kind.to_ascii_uppercase().as_str(),
                "D" | "DEAD" | "L" | "LIVE" | "W" | "WIND" | "USER"
            )
        })
    {
        return None;
    }
    let name = values.first()?.trim().to_ascii_uppercase();
    validate_stable_id(&name, "/load_case").ok()?;
    Some(LoadCaseRow { name, source_line })
}

fn parse_nodal_load(values: &[&str], source_line: usize) -> Option<NodalLoadRow> {
    if values.len() != 7 {
        return None;
    }
    let node_id = positive_id(values.first()?)?;
    let mut components = [0.0; 6];
    for (index, target) in components.iter_mut().enumerate() {
        *target = finite_f64(values.get(index + 1)?)?;
    }
    Some(NodalLoadRow {
        node_id,
        components,
        source_line,
    })
}

fn positive_id(value: &str) -> Option<u64> {
    value.parse::<u64>().ok().filter(|id| *id > 0)
}

fn finite_f64(value: &str) -> Option<f64> {
    value
        .parse::<f64>()
        .ok()
        .filter(|number| number.is_finite())
}

#[allow(clippy::too_many_lines)]
fn validate_normalization_graph(
    parsed: &ParsedMgt,
    dispositions: &mut [MgtRowDispositionV1],
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
) -> Result<(), MgtImportError> {
    for (family, empty) in [
        ("unit", parsed.unit.is_none()),
        ("nodes", parsed.nodes.is_empty()),
        ("materials", parsed.materials.is_empty()),
        ("sections", parsed.sections.is_empty()),
        ("elements", parsed.elements.is_empty()),
        ("constraints", parsed.constraints.is_empty()),
        ("load_cases", parsed.load_cases.is_empty()),
        ("nodal_loads", parsed.nodal_loads.is_empty()),
    ] {
        if empty {
            diagnostics.push(blocker(
                &format!("mgt_{family}_missing"),
                &format!("/{family}"),
                None,
                "required exact-profile family has no mapped rows",
            ));
        }
    }
    if parsed.load_cases.len() > 1 {
        diagnostics.push(blocker(
            "mgt_load_case_association_unsupported",
            "/load_cases",
            None,
            "multiple load cases require explicit USE-STLD association, which is outside v1",
        ));
    }
    if let Some(unit) = parsed.unit.as_ref() {
        let length2 = unit.length_to_m * unit.length_to_m;
        let length3 = length2 * unit.length_to_m;
        let length4 = length2 * length2;
        for node in parsed.nodes.values() {
            if node
                .coordinates
                .iter()
                .any(|value| !(value * unit.length_to_m).is_finite())
            {
                numeric_overflow(dispositions, diagnostics, node.source_line, "nodes")?;
            }
        }
        for material in parsed.materials.values() {
            let values = [
                material.elastic_modulus * unit.force_to_n / length2,
                material.density / length3,
            ];
            if values.iter().any(|value| !value.is_finite()) {
                numeric_overflow(dispositions, diagnostics, material.source_line, "materials")?;
            }
        }
        for section in parsed.sections.values() {
            let finite = match section.family {
                SectionFamily::Frame => section.values.iter().enumerate().all(|(index, value)| {
                    let scale = if matches!(index, 0 | 4 | 5) {
                        length2
                    } else {
                        length4
                    };
                    (value * scale).is_finite()
                }),
                SectionFamily::Truss => (section.values[0] * length2).is_finite(),
            };
            if !finite {
                numeric_overflow(dispositions, diagnostics, section.source_line, "sections")?;
            }
        }
        for element in parsed.elements.values() {
            if !(element.angle_deg * std::f64::consts::PI / 180.0).is_finite() {
                numeric_overflow(dispositions, diagnostics, element.source_line, "elements")?;
            }
        }
        for load in &parsed.nodal_loads {
            let finite = load.components.iter().enumerate().all(|(index, value)| {
                let scale = if index < 3 {
                    unit.force_to_n
                } else {
                    unit.force_to_n * unit.length_to_m
                };
                (value * scale).is_finite()
            });
            if !finite {
                numeric_overflow(dispositions, diagnostics, load.source_line, "nodal_loads")?;
            }
        }
    }
    let node_ids = parsed.nodes.keys().copied().collect::<BTreeSet<_>>();
    for element in parsed.elements.values() {
        let mut reason = None;
        if !node_ids.contains(&element.node_i) || !node_ids.contains(&element.node_j) {
            reason = Some((
                "mgt_element_dangling_node",
                "element references an unmapped node",
            ));
        } else if !parsed.materials.contains_key(&element.material_id) {
            reason = Some((
                "mgt_element_dangling_material",
                "element references an unmapped material",
            ));
        } else if let Some(section) = parsed.sections.get(&element.section_id) {
            let family_matches = matches!(
                (element.family, section.family),
                (ElementFamily::Frame, SectionFamily::Frame)
                    | (ElementFamily::Truss, SectionFamily::Truss)
            );
            if !family_matches {
                reason = Some((
                    "mgt_element_section_family_mismatch",
                    "element and section families do not match",
                ));
            }
        } else {
            reason = Some((
                "mgt_element_dangling_section",
                "element references an unmapped section",
            ));
        }
        if let Some((code, detail)) = reason {
            mark_row_unsupported(dispositions, element.source_line, code)?;
            diagnostics.push(blocker(
                code,
                "/elements",
                Some(element.source_line),
                detail,
            ));
        }
    }
    for constraint in parsed.constraints.values() {
        if !node_ids.contains(&constraint.node_id) {
            mark_row_unsupported(
                dispositions,
                constraint.source_line,
                "mgt_constraint_dangling_node",
            )?;
            diagnostics.push(blocker(
                "mgt_constraint_dangling_node",
                "/constraints",
                Some(constraint.source_line),
                "constraint references an unmapped node",
            ));
        }
    }
    for load in &parsed.nodal_loads {
        if !node_ids.contains(&load.node_id) {
            mark_row_unsupported(
                dispositions,
                load.source_line,
                "mgt_nodal_load_dangling_node",
            )?;
            diagnostics.push(blocker(
                "mgt_nodal_load_dangling_node",
                "/nodal_loads",
                Some(load.source_line),
                "nodal load references an unmapped node",
            ));
        }
    }
    Ok(())
}

fn numeric_overflow(
    dispositions: &mut [MgtRowDispositionV1],
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
    source_line: usize,
    family: &str,
) -> Result<(), MgtImportError> {
    mark_row_unsupported(dispositions, source_line, "mgt_si_conversion_overflow")?;
    diagnostics.push(blocker(
        "mgt_si_conversion_overflow",
        &format!("/{family}"),
        Some(source_line),
        "finite source value overflows during explicit SI conversion",
    ));
    Ok(())
}

fn mark_row_unsupported(
    dispositions: &mut [MgtRowDispositionV1],
    source_line: usize,
    reason: &str,
) -> Result<(), MgtImportError> {
    let source_line = u64::try_from(source_line).map_err(|_| {
        import_error(
            "mgt_source_line_overflow",
            "/source",
            "source line exceeds u64",
        )
    })?;
    let row = dispositions
        .iter_mut()
        .find(|row| row.source_line == source_line)
        .ok_or_else(|| {
            import_error(
                "mgt_disposition_invariant_failed",
                "/dispositions",
                "mapped source row is missing from disposition inventory",
            )
        })?;
    row.disposition = MgtRowDispositionKindV1::Unsupported;
    reason.clone_into(&mut row.reason_code);
    row.target_ids.clear();
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn build_model_ir(
    model_id: &str,
    source_hash: &str,
    encoding: &str,
    parsed: &ParsedMgt,
) -> Result<ModelIrV2Document, MgtImportError> {
    let unit = parsed.unit.as_ref().ok_or_else(|| {
        import_error(
            "mgt_normalization_invariant_failed",
            "/unit",
            "normalized import has no unit row",
        )
    })?;
    let length2 = unit.length_to_m * unit.length_to_m;
    let length3 = length2 * unit.length_to_m;
    let length4 = length2 * length2;

    let nodes = parsed
        .nodes
        .values()
        .enumerate()
        .map(|(index, row)| {
            json!({
                "id": entity_id("N", row.id),
                "index": index,
                "coordinates_m": row.coordinates.map(|value| value * unit.length_to_m),
                "source_id": format!("midas_mgt:NODE:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            })
        })
        .collect::<Vec<_>>();
    let materials = parsed
        .materials
        .values()
        .enumerate()
        .map(|(index, row)| {
            json!({
                "id": entity_id("M", row.id),
                "index": index,
                "law_id": "linear_elastic_isotropic",
                "parameter_set_version": "1",
                "parameters": {
                    "elastic_modulus_pa": row.elastic_modulus * unit.force_to_n / length2,
                    "poisson_ratio": row.poisson_ratio,
                    "density_kg_m3": row.density / length3
                },
                "state_schema": {
                    "stateful": false,
                    "state_update_epoch": "none",
                    "supports_trial_commit_rollback": true
                },
                "source_id": format!("midas_mgt:MATERIAL:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            })
        })
        .collect::<Vec<_>>();
    let sections = parsed
        .sections
        .values()
        .enumerate()
        .map(|(index, row)| match row.family {
            SectionFamily::Frame => json!({
                "id": entity_id("S", row.id),
                "index": index,
                "family_id": "frame_3d",
                "parameter_set_version": "1",
                "parameters": {
                    "area_m2": row.values[0] * length2,
                    "iy_m4": row.values[1] * length4,
                    "iz_m4": row.values[2] * length4,
                    "torsional_constant_m4": row.values[3] * length4,
                    "shear_area_y_m2": row.values[4] * length2,
                    "shear_area_z_m2": row.values[5] * length2
                },
                "source_id": format!("midas_mgt:SECTION:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            }),
            SectionFamily::Truss => json!({
                "id": entity_id("S", row.id),
                "index": index,
                "family_id": "truss_3d",
                "parameter_set_version": "1",
                "parameters": {"area_m2": row.values[0] * length2},
                "source_id": format!("midas_mgt:SECTION:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            }),
        })
        .collect::<Vec<_>>();
    let elements = parsed
        .elements
        .values()
        .enumerate()
        .map(|(index, row)| match row.family {
            ElementFamily::Frame => json!({
                "id": entity_id("E", row.id),
                "index": index,
                "type": "frame_3d",
                "formulation": "euler_bernoulli_3d",
                "node_ids": [entity_id("N", row.node_i), entity_id("N", row.node_j)],
                "material_id": entity_id("M", row.material_id),
                "section_id": entity_id("S", row.section_id),
                "local_axis_rotation_rad": row.angle_deg * std::f64::consts::PI / 180.0,
                "offsets": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
                "releases": {"i": [], "j": []},
                "source_id": format!("midas_mgt:ELEMENT:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            }),
            ElementFamily::Truss => json!({
                "id": entity_id("E", row.id),
                "index": index,
                "type": "truss_3d",
                "formulation": "linear_truss_3d",
                "node_ids": [entity_id("N", row.node_i), entity_id("N", row.node_j)],
                "material_id": entity_id("M", row.material_id),
                "section_id": entity_id("S", row.section_id),
                "offsets": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
                "source_id": format!("midas_mgt:ELEMENT:{}", row.id),
                "extensions": {"native_mgt:source_line": row.source_line}
            }),
        })
        .collect::<Vec<_>>();
    let constraints = parsed
        .constraints
        .values()
        .enumerate()
        .map(|(index, row)| {
            let dofs = DOFS
                .iter()
                .zip(row.fixed)
                .filter_map(|(dof, fixed)| fixed.then_some(*dof))
                .collect::<Vec<_>>();
            let prescribed = dofs
                .iter()
                .map(|dof| ((*dof).to_owned(), Value::from(0.0)))
                .collect::<serde_json::Map<_, _>>();
            json!({
                "id": entity_id("C", row.node_id),
                "index": index,
                "type": "fixed_dofs",
                "node_id": entity_id("N", row.node_id),
                "dofs": dofs,
                "prescribed_values_si": prescribed,
                "source_id": format!("midas_mgt:CONSTRAINT:{}", row.node_id),
                "extensions": {"native_mgt:source_line": row.source_line}
            })
        })
        .collect::<Vec<_>>();
    let load_case = parsed.load_cases.first().ok_or_else(|| {
        import_error(
            "mgt_normalization_invariant_failed",
            "/load_cases",
            "normalized import has no load case",
        )
    })?;
    let nodal_loads = parsed
        .nodal_loads
        .iter()
        .enumerate()
        .map(|(index, row)| {
            let force = unit.force_to_n;
            let moment = unit.force_to_n * unit.length_to_m;
            json!({
                "id": format!("L_{}_{}", row.node_id, index),
                "index": index,
                "node_id": entity_id("N", row.node_id),
                "components_si": {
                    "FX": row.components[0] * force,
                    "FY": row.components[1] * force,
                    "FZ": row.components[2] * force,
                    "MX": row.components[3] * moment,
                    "MY": row.components[4] * moment,
                    "MZ": row.components[5] * moment
                },
                "source_id": format!("midas_mgt:CONLOAD:{}:{}", row.node_id, index),
                "extensions": {"native_mgt:source_line": row.source_line}
            })
        })
        .collect::<Vec<_>>();
    let load_patterns = vec![json!({
        "id": format!("LP_{}", load_case.name),
        "index": 0,
        "analysis_type": "linear_static",
        "self_weight": [0.0, 0.0, 0.0],
        "nodal_loads": nodal_loads,
        "source_id": format!("midas_mgt:STLDCASE:{}", load_case.name),
        "extensions": {"native_mgt:source_line": load_case.source_line}
    })];
    let roundtrip_map = roundtrip_rows(parsed);
    let value = json!({
        "schema_version": "structural-analysis-model-ir.v2",
        "model_id": model_id,
        "capability_profile": "engine_v2_phase0_linear_3d",
        "provenance": {
            "source_format": "midas_mgt",
            "source_ref": format!("mgt:{}", source_hash.trim_start_matches("sha256:")),
            "source_sha256": source_hash,
            "normalizer_id": NORMALIZER_ID,
            "normalizer_version": NORMALIZER_VERSION,
            "source_units": {
                "length": unit.length,
                "force": unit.force,
                "mass": "kg",
                "time": "s",
                "rotation": "deg"
            },
            "unit_scales_to_si": {
                "length_to_m": unit.length_to_m,
                "force_to_n": unit.force_to_n,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": std::f64::consts::PI / 180.0
            },
            "extensions": {"native_mgt:encoding": encoding}
        },
        "units": {"length": "m", "force": "N", "mass": "kg", "time": "s", "rotation": "rad"},
        "coordinate_system": {
            "frame_id": "global",
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
            "handedness": "right",
            "origin_m": [0.0, 0.0, 0.0]
        },
        "dof_components": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "nodes": nodes,
        "materials": materials,
        "sections": sections,
        "elements": elements,
        "constraints": constraints,
        "load_patterns": load_patterns,
        "load_combinations": [],
        "time_functions": [],
        "construction_stages": [],
        "roundtrip_map": roundtrip_map,
        "unsupported_features": [],
        "extensions": {"native_mgt:import_profile": "exact_numeric_frame_truss_v1"}
    });
    let canonical = canonicalize_model_ir_v2(&value).map_err(|error| {
        import_error(
            "mgt_model_ir_canonicalization_failed",
            "/model_ir",
            &error.to_string(),
        )
    })?;
    parse_model_ir_v2(canonical.as_bytes())
        .map_err(|error| import_error("mgt_model_ir_contract_failed", &error.path, &error.detail))
}

fn roundtrip_rows(parsed: &ParsedMgt) -> Vec<Value> {
    let mut rows = Vec::new();
    for row in parsed.nodes.values() {
        rows.push(roundtrip_row(
            "NODE",
            row.id,
            "node",
            &entity_id("N", row.id),
        ));
    }
    for row in parsed.materials.values() {
        rows.push(roundtrip_row(
            "MATERIAL",
            row.id,
            "material",
            &entity_id("M", row.id),
        ));
    }
    for row in parsed.sections.values() {
        rows.push(roundtrip_row(
            "SECTION",
            row.id,
            "section",
            &entity_id("S", row.id),
        ));
    }
    for row in parsed.elements.values() {
        rows.push(roundtrip_row(
            "ELEMENT",
            row.id,
            "element",
            &entity_id("E", row.id),
        ));
    }
    for row in parsed.constraints.values() {
        rows.push(roundtrip_row(
            "CONSTRAINT",
            row.node_id,
            "constraint",
            &entity_id("C", row.node_id),
        ));
    }
    for row in &parsed.load_cases {
        rows.push(json!({
            "source_entity_id": format!("STLDCASE:{}", row.name),
            "entity_kind": "load_pattern",
            "model_ir_entity_id": format!("LP_{}", row.name),
            "mapping_status": "canonicalized",
            "extensions": {}
        }));
    }
    rows
}

fn roundtrip_row(section: &str, source_id: u64, kind: &str, target_id: &str) -> Value {
    json!({
        "source_entity_id": format!("{section}:{source_id}"),
        "entity_kind": kind,
        "model_ir_entity_id": target_id,
        "mapping_status": "canonicalized",
        "extensions": {}
    })
}

#[allow(clippy::too_many_arguments)]
fn finish_document(
    source_bytes: Vec<u8>,
    source: MgtSourceIdentityV1,
    model_id: &str,
    section_counts: BTreeMap<String, u64>,
    dispositions: Vec<MgtRowDispositionV1>,
    diagnostics: Vec<MgtImportDiagnosticV1>,
    model: Option<ModelIrV2Document>,
) -> Result<MgtImportDocumentV1, MgtImportError> {
    let count = |kind| {
        dispositions
            .iter()
            .filter(|row| row.disposition == kind)
            .count()
    };
    let mapped_row_count = count_to_u64(count(MgtRowDispositionKindV1::Mapped))?;
    let preserved_only_row_count = count_to_u64(count(MgtRowDispositionKindV1::PreservedOnly))?;
    let dropped_row_count = count_to_u64(count(MgtRowDispositionKindV1::Dropped))?;
    let unsupported_row_count = count_to_u64(count(MgtRowDispositionKindV1::Unsupported))?;
    let normalized_model = model.as_ref().map(|document| MgtNormalizedModelIdentityV1 {
        model_id: document.model_id().to_owned(),
        content_hash: document.content_hash().to_owned(),
        semantic_hash: document.semantic_hash().to_owned(),
        provenance_hash: document.provenance_hash().to_owned(),
    });
    let blocker_count = diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.severity == "blocker")
        .count();
    let mut health = MgtImportHealthV1 {
        schema_version: MGT_IMPORT_HEALTH_V1.to_owned(),
        status: if model.is_some() {
            MgtImportStatusV1::Normalized
        } else {
            MgtImportStatusV1::Blocked
        },
        source,
        model_id: model_id.to_owned(),
        section_counts,
        dispositions,
        diagnostics,
        mapped_row_count,
        preserved_only_row_count,
        dropped_row_count,
        unsupported_row_count,
        blocker_count: count_to_u64(blocker_count)?,
        normalized_model,
        claim_boundary: "bounded_mgt_import_health_and_exact_numeric_frame_truss_modelir_validation_not_general_mgt_solver_authority".to_owned(),
        health_hash: String::new(),
    };
    let mut unsigned = serde_json::to_value(&health).map_err(|_| {
        import_error(
            "mgt_health_encode_failed",
            "/health",
            "import health could not be represented as JSON",
        )
    })?;
    unsigned
        .as_object_mut()
        .and_then(|object| object.remove("health_hash"))
        .ok_or_else(|| {
            import_error(
                "mgt_health_invariant_failed",
                "/health",
                "import health is not an object",
            )
        })?;
    let canonical_unsigned = canonicalize_model_ir_v2(&unsigned).map_err(|_| {
        import_error(
            "mgt_health_canonicalization_failed",
            "/health",
            "import health could not be canonicalized",
        )
    })?;
    health.health_hash = sha256_identity(canonical_unsigned.as_bytes());
    let health_value = serde_json::to_value(&health).map_err(|_| {
        import_error(
            "mgt_health_encode_failed",
            "/health",
            "import health could not be represented as JSON",
        )
    })?;
    let health_json = canonicalize_model_ir_v2(&health_value).map_err(|_| {
        import_error(
            "mgt_health_canonicalization_failed",
            "/health",
            "import health could not be canonicalized",
        )
    })?;
    Ok(MgtImportDocumentV1 {
        source_bytes,
        health,
        health_json,
        model,
    })
}

fn source_identity(
    bytes: &[u8],
    source_hash: &str,
    encoding: &str,
    line_count: usize,
) -> Result<MgtSourceIdentityV1, MgtImportError> {
    Ok(MgtSourceIdentityV1 {
        source_hash: source_hash.to_owned(),
        byte_length: count_to_u64(bytes.len())?,
        encoding: encoding.to_owned(),
        line_count: count_to_u64(line_count)?,
    })
}

fn push_disposition(
    output: &mut Vec<MgtRowDispositionV1>,
    row: &RawRow,
    disposition: MgtRowDispositionKindV1,
    reason_code: &str,
    target_ids: Vec<String>,
) -> Result<(), MgtImportError> {
    output.push(MgtRowDispositionV1 {
        section: row.section.clone(),
        section_row_index: count_to_u64(row.section_row_index)?,
        source_line: count_to_u64(row.source_line)?,
        source_row_hash: sha256_identity(row.source_text.as_bytes()),
        disposition,
        reason_code: reason_code.to_owned(),
        target_ids,
    });
    Ok(())
}

fn unsupported(
    dispositions: &mut Vec<MgtRowDispositionV1>,
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
    row: &RawRow,
    code: &str,
    detail: &str,
) -> Result<(), MgtImportError> {
    push_disposition(
        dispositions,
        row,
        MgtRowDispositionKindV1::Unsupported,
        code,
        Vec::new(),
    )?;
    diagnostics.push(blocker(
        code,
        &format!("/{}/{}", row.section, row.section_row_index),
        Some(row.source_line),
        detail,
    ));
    Ok(())
}

fn dropped(
    dispositions: &mut Vec<MgtRowDispositionV1>,
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
    row: &RawRow,
    code: &str,
    detail: &str,
) -> Result<(), MgtImportError> {
    push_disposition(
        dispositions,
        row,
        MgtRowDispositionKindV1::Dropped,
        code,
        Vec::new(),
    )?;
    diagnostics.push(blocker(
        code,
        &format!("/{}/{}", row.section, row.section_row_index),
        Some(row.source_line),
        detail,
    ));
    Ok(())
}

fn duplicate_entity(
    dispositions: &mut Vec<MgtRowDispositionV1>,
    diagnostics: &mut Vec<MgtImportDiagnosticV1>,
    row: &RawRow,
    family: &str,
    id: u64,
) -> Result<(), MgtImportError> {
    unsupported(
        dispositions,
        diagnostics,
        row,
        &format!("mgt_duplicate_{family}_id"),
        &format!("duplicate {family} ID {id}"),
    )
}

fn blocker(
    code: &str,
    path: &str,
    source_line: Option<usize>,
    detail: &str,
) -> MgtImportDiagnosticV1 {
    MgtImportDiagnosticV1 {
        severity: "blocker".to_owned(),
        code: code.to_owned(),
        path: path.to_owned(),
        source_line: source_line.and_then(|line| u64::try_from(line).ok()),
        detail: detail.to_owned(),
    }
}

fn sort_evidence(
    dispositions: &mut [MgtRowDispositionV1],
    diagnostics: &mut [MgtImportDiagnosticV1],
) {
    dispositions.sort_by_key(|row| (row.source_line, row.section_row_index));
    diagnostics.sort_by(|left, right| {
        (left.source_line.unwrap_or(u64::MAX), &left.path, &left.code).cmp(&(
            right.source_line.unwrap_or(u64::MAX),
            &right.path,
            &right.code,
        ))
    });
}

fn validate_stable_id(value: &str, path: &str) -> Result<(), MgtImportError> {
    let bytes = value.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphabetic()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':'));
    if valid {
        Ok(())
    } else {
        Err(import_error(
            "mgt_model_id_invalid",
            path,
            "model ID must satisfy the ModelIR stable-ID contract",
        ))
    }
}

fn count_to_u64(value: usize) -> Result<u64, MgtImportError> {
    u64::try_from(value)
        .map_err(|_| import_error("mgt_count_overflow", "/", "MGT import count exceeds u64"))
}

fn entity_id(prefix: &str, id: u64) -> String {
    format!("{prefix}_{id}")
}

fn sha256_identity(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

fn import_error(code: &str, path: &str, detail: &str) -> MgtImportError {
    MgtImportError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
