//! Strict bounded native-to-external linear `Frame3D` comparison contracts.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::result_ir::{validate_linear_frame3d_result_ir_v1, LinearFrame3dResultIrV1};
use crate::{
    FRAME3D_COMPARISON_IR_SCHEMA_V1, FRAME3D_EXTERNAL_REFERENCE_SCHEMA_V1,
    FRAME3D_RESULT_IR_SCHEMA_V1,
};

const REFERENCE_SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/external_linear_frame3d_reference_v1.schema.json"
));
const COMPARISON_SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/linear_frame3d_comparison_ir_v1.schema.json"
));
const HASH_PREFIX: &str = "sha256:";
const HASH_LENGTH: usize = 71;
const DISPLACEMENT_TOLERANCE: f64 = 0.005;
const REACTION_TOLERANCE: f64 = 0.005;
const MEMBER_FORCE_TOLERANCE: f64 = 0.01;
const DISPLACEMENT_FLOOR: f64 = 1.0e-12;
const FORCE_FLOOR: f64 = 1.0e-6;
const DISPLACEMENT_COMPONENTS: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];
const FORCE_COMPONENTS: [&str; 6] = ["FX", "FY", "FZ", "MX", "MY", "MZ"];

#[derive(Clone, Copy)]
struct RowPolicy {
    quantity: &'static str,
    tolerance: f64,
    absolute_floor: f64,
}

const DISPLACEMENT_POLICY: RowPolicy = RowPolicy {
    quantity: "displacement",
    tolerance: DISPLACEMENT_TOLERANCE,
    absolute_floor: DISPLACEMENT_FLOOR,
};
const REACTION_POLICY: RowPolicy = RowPolicy {
    quantity: "reaction",
    tolerance: REACTION_TOLERANCE,
    absolute_floor: FORCE_FLOOR,
};
const MEMBER_FORCE_POLICY: RowPolicy = RowPolicy {
    quantity: "member_end_force",
    tolerance: MEMBER_FORCE_TOLERANCE,
    absolute_floor: FORCE_FLOOR,
};

static REFERENCE_SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();
static COMPARISON_SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

/// Stable contract failure for reference decoding or comparison construction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Frame3dComparisonError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for Frame3dComparisonError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for Frame3dComparisonError {}

/// External tool identity and operator/synthetic origin declaration.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceSourceV1 {
    pub tool: String,
    pub version: String,
    pub origin: String,
    pub export_sha256: String,
}

/// Exact model/load identity declared by the reference producer.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceBindingsV1 {
    pub model_content_hash: String,
    pub load_pattern_id: Option<String>,
    pub load_combination_id: Option<String>,
}

/// Required coordinate, ordering and sign conventions.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceAxesV1 {
    pub node_displacement: String,
    pub node_reaction: String,
    pub member_end_force: String,
    pub sign_convention: String,
}

/// Supported external engineering units normalized to the native SI profile.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceUnitsV1 {
    pub translation: String,
    pub rotation: String,
    pub force: String,
    pub moment: String,
}

/// One external node row in the declared global component order.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceNodeV1 {
    pub node_id: String,
    pub displacement: [f64; 6],
    pub reaction: [f64; 6],
}

/// One external member row in declared member-local i-then-j order.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalFrame3dReferenceMemberV1 {
    pub member_id: String,
    pub end_i_force: [f64; 6],
    pub end_j_force: [f64; 6],
}

/// Strict external comparison input. It is a mapping assertion, not trusted validation evidence.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalLinearFrame3dReferenceV1 {
    pub schema_version: String,
    pub reference_id: String,
    pub source: ExternalFrame3dReferenceSourceV1,
    pub bindings: ExternalFrame3dReferenceBindingsV1,
    pub axes: ExternalFrame3dReferenceAxesV1,
    pub units: ExternalFrame3dReferenceUnitsV1,
    pub nodes: Vec<ExternalFrame3dReferenceNodeV1>,
    pub members: Vec<ExternalFrame3dReferenceMemberV1>,
    pub claim_boundary: String,
}

/// Parsed external reference plus the hash of its canonical strict JSON payload.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedExternalLinearFrame3dReferenceV1 {
    pub reference: ExternalLinearFrame3dReferenceV1,
    pub reference_hash: String,
}

/// Exact native source identity consumed by a comparison.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dComparisonSourceResultV1 {
    pub schema_version: String,
    pub result_id: String,
    pub result_hash: String,
    pub model_content_hash: String,
}

/// Exact external reference identity consumed by a comparison.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dComparisonSourceReferenceV1 {
    pub schema_version: String,
    pub reference_id: String,
    pub reference_hash: String,
    pub tool: String,
    pub version: String,
    pub origin: String,
    pub export_sha256: String,
}

/// Fixed Frame Alpha cross-code tolerance and near-zero scaling policy.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dComparisonToleranceProfileV1 {
    pub profile: String,
    pub scaled_difference: String,
    pub displacement_relative: f64,
    pub reaction_relative: f64,
    pub member_end_force_relative: f64,
    pub translation_rotation_absolute_floor: f64,
    pub force_moment_absolute_floor: f64,
}

/// One auditable native/reference component comparison row.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dComparisonRowV1 {
    pub quantity: String,
    pub entity_id: String,
    pub component: String,
    pub unit: String,
    pub native_value: f64,
    pub reference_value: f64,
    pub absolute_difference: f64,
    pub scaled_difference: f64,
    pub tolerance: f64,
    pub passed: bool,
}

/// Deterministic aggregate for one result quantity family.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dComparisonFamilyV1 {
    pub quantity: String,
    pub row_count: u32,
    pub failing_row_count: u32,
    pub max_scaled_difference: f64,
    pub tolerance: f64,
    pub worst_entity_id: String,
    pub worst_component: String,
    pub passed: bool,
}

/// Overall comparison gate summary.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dComparisonSummaryV1 {
    pub row_count: u32,
    pub failing_row_count: u32,
    pub passed: bool,
    pub families: Vec<Frame3dComparisonFamilyV1>,
}

/// Explicitly non-promoting comparison authority axes.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dComparisonAuthorityV1 {
    pub source_result: String,
    pub reference_input: String,
    pub comparison: String,
    pub external_validation: String,
    pub engineering_design: String,
    pub release_readiness: String,
}

/// Versioned, hash-bound bounded native-to-external comparison artifact.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct LinearFrame3dComparisonIrV1 {
    pub schema_version: String,
    pub comparison_id: String,
    pub comparison_hash: String,
    pub comparison_kind: String,
    pub source_result: Frame3dComparisonSourceResultV1,
    pub source_reference: Frame3dComparisonSourceReferenceV1,
    pub tolerance_profile: Frame3dComparisonToleranceProfileV1,
    pub summary: Frame3dComparisonSummaryV1,
    pub rows: Vec<Frame3dComparisonRowV1>,
    pub authority: Frame3dComparisonAuthorityV1,
    pub claim_boundary: String,
}

impl LinearFrame3dComparisonIrV1 {
    /// Render sorted canonical JSON including the verified comparison hash.
    ///
    /// # Errors
    ///
    /// Returns a stable error when the typed artifact cannot be canonicalized.
    pub fn canonical_json(&self) -> Result<String, Frame3dComparisonError> {
        canonical_value(self)
    }
}

/// Strictly decode and validate one external reference input.
///
/// # Errors
///
/// Rejects malformed JSON, duplicate keys, schema/profile drift, invalid provenance, duplicate
/// entities, non-finite values and unstable identities.
pub fn parse_external_linear_frame3d_reference_v1(
    bytes: &[u8],
) -> Result<ParsedExternalLinearFrame3dReferenceV1, Frame3dComparisonError> {
    let value = decode_json_strict(bytes).map_err(|item| {
        error(
            "frame3d_external_reference_json_invalid",
            &item.path,
            &item.detail,
        )
    })?;
    validate_schema(
        &value,
        reference_schema_validator()?,
        "frame3d_external_reference_schema_invalid",
    )?;
    let reference: ExternalLinearFrame3dReferenceV1 = serde_json::from_value(value.clone())
        .map_err(|_| {
            error(
                "frame3d_external_reference_decode_failed",
                "/",
                "External reference JSON could not be decoded into the typed contract",
            )
        })?;
    validate_reference_content(&reference)?;
    let canonical = canonicalize_model_ir_v2(&value).map_err(|_| {
        error(
            "frame3d_external_reference_canonicalization_failed",
            "/",
            "External reference could not be represented as canonical JSON",
        )
    })?;
    Ok(ParsedExternalLinearFrame3dReferenceV1 {
        reference,
        reference_hash: sha256_identity(canonical.as_bytes()),
    })
}

/// Construct one complete component-wise comparison after strict mapping and SI normalization.
///
/// # Errors
///
/// Rejects invalid ResultIR/reference inputs, stale model/load bindings, partial entity coverage,
/// unsupported units, non-finite normalized values or hash/schema instability.
pub fn create_linear_frame3d_comparison_ir_v1(
    result: &LinearFrame3dResultIrV1,
    reference_bytes: &[u8],
    comparison_id: &str,
) -> Result<LinearFrame3dComparisonIrV1, Frame3dComparisonError> {
    validate_linear_frame3d_result_ir_v1(result).map_err(|item| {
        error(
            "frame3d_comparison_source_result_invalid",
            &item.path,
            &item.detail,
        )
    })?;
    require_stable_id(comparison_id, "/comparison_id")?;
    let parsed = parse_external_linear_frame3d_reference_v1(reference_bytes)?;
    validate_source_binding(result, &parsed.reference)?;
    let rows = comparison_rows(result, &parsed.reference)?;
    let summary = summarize_rows(&rows)?;
    let mut comparison = LinearFrame3dComparisonIrV1 {
        schema_version: FRAME3D_COMPARISON_IR_SCHEMA_V1.to_owned(),
        comparison_id: comparison_id.to_owned(),
        comparison_hash: format!("{HASH_PREFIX}{}", "0".repeat(64)),
        comparison_kind: "bounded_native_to_external_linear_frame3d".to_owned(),
        source_result: Frame3dComparisonSourceResultV1 {
            schema_version: FRAME3D_RESULT_IR_SCHEMA_V1.to_owned(),
            result_id: result.result_id.clone(),
            result_hash: result.result_hash.clone(),
            model_content_hash: result.bindings.model_content_hash.clone(),
        },
        source_reference: Frame3dComparisonSourceReferenceV1 {
            schema_version: FRAME3D_EXTERNAL_REFERENCE_SCHEMA_V1.to_owned(),
            reference_id: parsed.reference.reference_id.clone(),
            reference_hash: parsed.reference_hash,
            tool: parsed.reference.source.tool.clone(),
            version: parsed.reference.source.version.clone(),
            origin: parsed.reference.source.origin.clone(),
            export_sha256: parsed.reference.source.export_sha256.clone(),
        },
        tolerance_profile: tolerance_profile(),
        summary,
        rows,
        authority: comparison_authority(),
        claim_boundary: "strict_mapping_unit_normalization_and_tolerance_evaluation_not_external_validation_design_or_release_authority".to_owned(),
    };
    validate_comparison_content(&comparison)?;
    comparison.comparison_hash = comparison_hash(&comparison)?;
    validate_linear_frame3d_comparison_ir_v1(&comparison)?;
    Ok(comparison)
}

/// Strictly decode, schema-check and hash-check a bounded comparison artifact.
///
/// # Errors
///
/// Rejects malformed JSON, duplicate keys, schema/policy drift, inconsistent rows or summaries,
/// authority promotion and stale hashes.
pub fn parse_linear_frame3d_comparison_ir_v1(
    bytes: &[u8],
) -> Result<LinearFrame3dComparisonIrV1, Frame3dComparisonError> {
    let value = decode_json_strict(bytes).map_err(|item| {
        error(
            "frame3d_comparison_ir_json_invalid",
            &item.path,
            &item.detail,
        )
    })?;
    validate_schema(
        &value,
        comparison_schema_validator()?,
        "frame3d_comparison_ir_schema_invalid",
    )?;
    let comparison: LinearFrame3dComparisonIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "frame3d_comparison_ir_decode_failed",
            "/",
            "ComparisonIR JSON could not be decoded into the typed contract",
        )
    })?;
    validate_linear_frame3d_comparison_ir_v1(&comparison)?;
    Ok(comparison)
}

/// Validate fixed policy, internal row/summary consistency and comparison hash.
///
/// # Errors
///
/// Returns the first stable contract error for schema, identity, row, summary, authority or hash
/// drift.
pub fn validate_linear_frame3d_comparison_ir_v1(
    comparison: &LinearFrame3dComparisonIrV1,
) -> Result<(), Frame3dComparisonError> {
    let value = serde_json::to_value(comparison).map_err(|_| serialization_error())?;
    validate_schema(
        &value,
        comparison_schema_validator()?,
        "frame3d_comparison_ir_schema_invalid",
    )?;
    validate_comparison_content(comparison)?;
    if comparison.comparison_hash != comparison_hash(comparison)? {
        return Err(error(
            "frame3d_comparison_ir_hash_mismatch",
            "/comparison_hash",
            "ComparisonIR hash does not match its canonical payload",
        ));
    }
    Ok(())
}

/// Recompute the comparison from exact source bytes and reject transplantation or row drift.
///
/// # Errors
///
/// Rejects invalid sources or any comparison artifact that is not their deterministic evaluation.
pub fn validate_linear_frame3d_comparison_sources(
    comparison: &LinearFrame3dComparisonIrV1,
    result: &LinearFrame3dResultIrV1,
    reference_bytes: &[u8],
) -> Result<(), Frame3dComparisonError> {
    validate_linear_frame3d_comparison_ir_v1(comparison)?;
    let expected =
        create_linear_frame3d_comparison_ir_v1(result, reference_bytes, &comparison.comparison_id)?;
    if *comparison != expected {
        return Err(error(
            "frame3d_comparison_source_binding_mismatch",
            "/source_result",
            "ComparisonIR is not the deterministic evaluation of the supplied sources",
        ));
    }
    Ok(())
}

fn validate_reference_content(
    reference: &ExternalLinearFrame3dReferenceV1,
) -> Result<(), Frame3dComparisonError> {
    require_stable_id(&reference.reference_id, "/reference_id")?;
    require_hash(&reference.source.export_sha256, "/source/export_sha256")?;
    require_hash(
        &reference.bindings.model_content_hash,
        "/bindings/model_content_hash",
    )?;
    let source_pair_valid = matches!(
        (
            reference.source.tool.as_str(),
            reference.source.origin.as_str()
        ),
        ("synthetic_fixture", "synthetic_contract_fixture")
            | (
                "sap2000" | "midas_gen" | "opensees" | "calculix",
                "operator_attached_external"
            )
    );
    if !source_pair_valid {
        return Err(error(
            "frame3d_external_reference_origin_invalid",
            "/source",
            "Synthetic sources and operator-attached external tools must use matching origin labels",
        ));
    }
    if reference.source.version.trim().is_empty()
        || reference.source.version.chars().any(char::is_control)
    {
        return Err(error(
            "frame3d_external_reference_version_invalid",
            "/source/version",
            "External source version must be visible non-control text",
        ));
    }
    match (
        reference.bindings.load_pattern_id.as_deref(),
        reference.bindings.load_combination_id.as_deref(),
    ) {
        (Some(id), None) => require_stable_id(id, "/bindings/load_pattern_id")?,
        (None, Some(id)) => require_stable_id(id, "/bindings/load_combination_id")?,
        _ => {
            return Err(error(
                "frame3d_external_reference_load_binding_invalid",
                "/bindings",
                "Exactly one load pattern or load combination identity is required",
            ))
        }
    }
    let mut node_ids = BTreeSet::new();
    for (index, node) in reference.nodes.iter().enumerate() {
        require_stable_id(&node.node_id, &format!("/nodes/{index}/node_id"))?;
        if !node_ids.insert(&node.node_id) {
            return Err(error(
                "frame3d_external_reference_duplicate_node",
                &format!("/nodes/{index}/node_id"),
                "External reference node IDs must be unique",
            ));
        }
        require_finite(&node.displacement, &format!("/nodes/{index}/displacement"))?;
        require_finite(&node.reaction, &format!("/nodes/{index}/reaction"))?;
    }
    let mut member_ids = BTreeSet::new();
    for (index, member) in reference.members.iter().enumerate() {
        require_stable_id(&member.member_id, &format!("/members/{index}/member_id"))?;
        if !member_ids.insert(&member.member_id) {
            return Err(error(
                "frame3d_external_reference_duplicate_member",
                &format!("/members/{index}/member_id"),
                "External reference member IDs must be unique",
            ));
        }
        require_finite(
            &member.end_i_force,
            &format!("/members/{index}/end_i_force"),
        )?;
        require_finite(
            &member.end_j_force,
            &format!("/members/{index}/end_j_force"),
        )?;
    }
    Ok(())
}

fn validate_source_binding(
    result: &LinearFrame3dResultIrV1,
    reference: &ExternalLinearFrame3dReferenceV1,
) -> Result<(), Frame3dComparisonError> {
    if result.bindings.model_content_hash != reference.bindings.model_content_hash
        || result.bindings.load_pattern_id != reference.bindings.load_pattern_id
        || result.bindings.load_combination_id != reference.bindings.load_combination_id
    {
        return Err(error(
            "frame3d_external_reference_binding_mismatch",
            "/bindings",
            "External reference model/load binding does not match the exact native ResultIR",
        ));
    }
    if result.nodes.len() != reference.nodes.len()
        || result.members.len() != reference.members.len()
    {
        return Err(error(
            "frame3d_external_reference_coverage_mismatch",
            "/",
            "External reference must cover every native node and member exactly once",
        ));
    }
    Ok(())
}

fn comparison_rows(
    result: &LinearFrame3dResultIrV1,
    reference: &ExternalLinearFrame3dReferenceV1,
) -> Result<Vec<Frame3dComparisonRowV1>, Frame3dComparisonError> {
    let node_map = reference
        .nodes
        .iter()
        .map(|row| (row.node_id.as_str(), row))
        .collect::<BTreeMap<_, _>>();
    let member_map = reference
        .members
        .iter()
        .map(|row| (row.member_id.as_str(), row))
        .collect::<BTreeMap<_, _>>();
    let mut rows = Vec::with_capacity(result.nodes.len() * 12 + result.members.len() * 12);
    append_node_rows(&mut rows, result, reference, &node_map)?;
    if node_map
        .keys()
        .any(|id| !result.nodes.iter().any(|row| row.node_id == *id))
    {
        return Err(error(
            "frame3d_external_reference_node_extra",
            "/nodes",
            "External reference contains a node absent from the native result",
        ));
    }
    append_member_rows(&mut rows, result, reference, &member_map)?;
    if member_map
        .keys()
        .any(|id| !result.members.iter().any(|row| row.member_id == *id))
    {
        return Err(error(
            "frame3d_external_reference_member_extra",
            "/members",
            "External reference contains a member absent from the native result",
        ));
    }
    Ok(rows)
}

fn append_node_rows(
    rows: &mut Vec<Frame3dComparisonRowV1>,
    result: &LinearFrame3dResultIrV1,
    reference: &ExternalLinearFrame3dReferenceV1,
    node_map: &BTreeMap<&str, &ExternalFrame3dReferenceNodeV1>,
) -> Result<(), Frame3dComparisonError> {
    for node in &result.nodes {
        let Some(reference_node) = node_map.get(node.node_id.as_str()) else {
            return Err(error(
                "frame3d_external_reference_node_missing",
                "/nodes",
                "External reference node IDs must exactly match the native result",
            ));
        };
        for (index, component) in DISPLACEMENT_COMPONENTS.iter().enumerate() {
            let scale = if index < 3 {
                translation_scale(&reference.units.translation)?
            } else {
                1.0
            };
            rows.push(comparison_row(
                DISPLACEMENT_POLICY,
                &node.node_id,
                component,
                if index < 3 { "m" } else { "rad" },
                node.displacement_m_rad[index],
                reference_node.displacement[index] * scale,
            ));
        }
        for (index, component) in FORCE_COMPONENTS.iter().enumerate() {
            let scale = if index < 3 {
                force_scale(&reference.units.force)?
            } else {
                moment_scale(&reference.units.moment)?
            };
            rows.push(comparison_row(
                REACTION_POLICY,
                &node.node_id,
                component,
                if index < 3 { "N" } else { "N*m" },
                node.reaction_n_nm[index],
                reference_node.reaction[index] * scale,
            ));
        }
    }
    Ok(())
}

fn append_member_rows(
    rows: &mut Vec<Frame3dComparisonRowV1>,
    result: &LinearFrame3dResultIrV1,
    reference: &ExternalLinearFrame3dReferenceV1,
    member_map: &BTreeMap<&str, &ExternalFrame3dReferenceMemberV1>,
) -> Result<(), Frame3dComparisonError> {
    for member in &result.members {
        let Some(reference_member) = member_map.get(member.member_id.as_str()) else {
            return Err(error(
                "frame3d_external_reference_member_missing",
                "/members",
                "External reference member IDs must exactly match the native result",
            ));
        };
        for (end, native_values, reference_values) in [
            ("I", &member.end_i_force_n_nm, &reference_member.end_i_force),
            ("J", &member.end_j_force_n_nm, &reference_member.end_j_force),
        ] {
            for (index, component) in FORCE_COMPONENTS.iter().enumerate() {
                let scale = if index < 3 {
                    force_scale(&reference.units.force)?
                } else {
                    moment_scale(&reference.units.moment)?
                };
                rows.push(comparison_row(
                    MEMBER_FORCE_POLICY,
                    &member.member_id,
                    &format!("{component}_{end}"),
                    if index < 3 { "N" } else { "N*m" },
                    native_values[index],
                    reference_values[index] * scale,
                ));
            }
        }
    }
    Ok(())
}

fn comparison_row(
    policy: RowPolicy,
    entity_id: &str,
    component: &str,
    unit: &str,
    native_value: f64,
    reference_value: f64,
) -> Frame3dComparisonRowV1 {
    let absolute_difference = (native_value - reference_value).abs();
    let denominator = native_value
        .abs()
        .max(reference_value.abs())
        .max(policy.absolute_floor);
    let scaled_difference = absolute_difference / denominator;
    Frame3dComparisonRowV1 {
        quantity: policy.quantity.to_owned(),
        entity_id: entity_id.to_owned(),
        component: component.to_owned(),
        unit: unit.to_owned(),
        native_value,
        reference_value,
        absolute_difference,
        scaled_difference,
        tolerance: policy.tolerance,
        passed: scaled_difference <= policy.tolerance,
    }
}

fn summarize_rows(
    rows: &[Frame3dComparisonRowV1],
) -> Result<Frame3dComparisonSummaryV1, Frame3dComparisonError> {
    let families = [
        ("displacement", DISPLACEMENT_TOLERANCE),
        ("reaction", REACTION_TOLERANCE),
        ("member_end_force", MEMBER_FORCE_TOLERANCE),
    ]
    .into_iter()
    .map(|(quantity, tolerance)| summarize_family(rows, quantity, tolerance))
    .collect::<Result<Vec<_>, _>>()?;
    let row_count = u32::try_from(rows.len()).map_err(|_| count_error())?;
    let failing = rows.iter().filter(|row| !row.passed).count();
    let failing_row_count = u32::try_from(failing).map_err(|_| count_error())?;
    Ok(Frame3dComparisonSummaryV1 {
        row_count,
        failing_row_count,
        passed: failing == 0,
        families,
    })
}

fn summarize_family(
    rows: &[Frame3dComparisonRowV1],
    quantity: &str,
    tolerance: f64,
) -> Result<Frame3dComparisonFamilyV1, Frame3dComparisonError> {
    let family = rows
        .iter()
        .filter(|row| row.quantity == quantity)
        .collect::<Vec<_>>();
    let Some(mut worst) = family.first().copied() else {
        return Err(error(
            "frame3d_comparison_family_missing",
            "/rows",
            "Every comparison quantity family requires at least one row",
        ));
    };
    for row in &family[1..] {
        if row.scaled_difference > worst.scaled_difference {
            worst = row;
        }
    }
    let failing = family.iter().filter(|row| !row.passed).count();
    Ok(Frame3dComparisonFamilyV1 {
        quantity: quantity.to_owned(),
        row_count: u32::try_from(family.len()).map_err(|_| count_error())?,
        failing_row_count: u32::try_from(failing).map_err(|_| count_error())?,
        max_scaled_difference: worst.scaled_difference,
        tolerance,
        worst_entity_id: worst.entity_id.clone(),
        worst_component: worst.component.clone(),
        passed: failing == 0,
    })
}

fn validate_comparison_content(
    comparison: &LinearFrame3dComparisonIrV1,
) -> Result<(), Frame3dComparisonError> {
    validate_comparison_identity_policy(comparison)?;
    validate_comparison_rows(&comparison.rows)?;
    let expected_summary = summarize_rows(&comparison.rows)?;
    if comparison.summary != expected_summary {
        return Err(error(
            "frame3d_comparison_summary_inconsistent",
            "/summary",
            "Comparison summary is not the deterministic aggregate of its rows",
        ));
    }
    Ok(())
}

fn validate_comparison_identity_policy(
    comparison: &LinearFrame3dComparisonIrV1,
) -> Result<(), Frame3dComparisonError> {
    require_stable_id(&comparison.comparison_id, "/comparison_id")?;
    require_hash(&comparison.comparison_hash, "/comparison_hash")?;
    require_hash(
        &comparison.source_result.result_hash,
        "/source_result/result_hash",
    )?;
    require_hash(
        &comparison.source_result.model_content_hash,
        "/source_result/model_content_hash",
    )?;
    require_hash(
        &comparison.source_reference.reference_hash,
        "/source_reference/reference_hash",
    )?;
    require_hash(
        &comparison.source_reference.export_sha256,
        "/source_reference/export_sha256",
    )?;
    let source_pair_valid = matches!(
        (
            comparison.source_reference.tool.as_str(),
            comparison.source_reference.origin.as_str()
        ),
        ("synthetic_fixture", "synthetic_contract_fixture")
            | (
                "sap2000" | "midas_gen" | "opensees" | "calculix",
                "operator_attached_external"
            )
    );
    if !source_pair_valid {
        return Err(error(
            "frame3d_comparison_reference_origin_invalid",
            "/source_reference",
            "Comparison reference tool and origin labels must remain consistent",
        ));
    }
    if comparison.tolerance_profile != tolerance_profile()
        || comparison.authority != comparison_authority()
    {
        return Err(error(
            "frame3d_comparison_policy_promotion_forbidden",
            "/",
            "Comparison tolerance or authority policy drift is forbidden",
        ));
    }
    Ok(())
}

fn validate_comparison_rows(rows: &[Frame3dComparisonRowV1]) -> Result<(), Frame3dComparisonError> {
    let mut identities = BTreeSet::new();
    for (index, row) in rows.iter().enumerate() {
        require_stable_id(&row.entity_id, &format!("/rows/{index}/entity_id"))?;
        for value in [
            row.native_value,
            row.reference_value,
            row.absolute_difference,
            row.scaled_difference,
            row.tolerance,
        ] {
            if !value.is_finite() {
                return Err(error(
                    "frame3d_comparison_non_finite",
                    &format!("/rows/{index}"),
                    "Comparison rows require finite values",
                ));
            }
        }
        let policy = match row.quantity.as_str() {
            "displacement" => DISPLACEMENT_POLICY,
            "reaction" => REACTION_POLICY,
            "member_end_force" => MEMBER_FORCE_POLICY,
            _ => {
                return Err(error(
                    "frame3d_comparison_quantity_invalid",
                    &format!("/rows/{index}/quantity"),
                    "Comparison quantity is unsupported",
                ))
            }
        };
        if !row_identity_is_valid(row) {
            return Err(error(
                "frame3d_comparison_row_identity_invalid",
                &format!("/rows/{index}"),
                "Quantity, component and normalized unit do not form a supported comparison row",
            ));
        }
        let expected = comparison_row(
            policy,
            &row.entity_id,
            &row.component,
            &row.unit,
            row.native_value,
            row.reference_value,
        );
        if *row != expected {
            return Err(error(
                "frame3d_comparison_row_inconsistent",
                &format!("/rows/{index}"),
                "Comparison row metrics or pass verdict do not match its values",
            ));
        }
        if !identities.insert((&row.quantity, &row.entity_id, &row.component)) {
            return Err(error(
                "frame3d_comparison_row_duplicate",
                &format!("/rows/{index}"),
                "Comparison row identities must be unique",
            ));
        }
    }
    Ok(())
}

fn row_identity_is_valid(row: &Frame3dComparisonRowV1) -> bool {
    match row.quantity.as_str() {
        "displacement" => DISPLACEMENT_COMPONENTS
            .iter()
            .position(|component| *component == row.component)
            .is_some_and(|index| row.unit == if index < 3 { "m" } else { "rad" }),
        "reaction" => FORCE_COMPONENTS
            .iter()
            .position(|component| *component == row.component)
            .is_some_and(|index| row.unit == if index < 3 { "N" } else { "N*m" }),
        "member_end_force" => ["I", "J"].iter().any(|end| {
            FORCE_COMPONENTS
                .iter()
                .position(|component| format!("{component}_{end}") == row.component)
                .is_some_and(|index| row.unit == if index < 3 { "N" } else { "N*m" })
        }),
        _ => false,
    }
}

fn translation_scale(unit: &str) -> Result<f64, Frame3dComparisonError> {
    match unit {
        "m" => Ok(1.0),
        "mm" => Ok(1.0e-3),
        _ => Err(error(
            "frame3d_external_reference_unit_invalid",
            "/units/translation",
            "Unsupported translation unit",
        )),
    }
}

fn force_scale(unit: &str) -> Result<f64, Frame3dComparisonError> {
    match unit {
        "N" => Ok(1.0),
        "kN" => Ok(1.0e3),
        _ => Err(error(
            "frame3d_external_reference_unit_invalid",
            "/units/force",
            "Unsupported force unit",
        )),
    }
}

fn moment_scale(unit: &str) -> Result<f64, Frame3dComparisonError> {
    match unit {
        "N*m" => Ok(1.0),
        "kN*m" => Ok(1.0e3),
        _ => Err(error(
            "frame3d_external_reference_unit_invalid",
            "/units/moment",
            "Unsupported moment unit",
        )),
    }
}

fn tolerance_profile() -> Frame3dComparisonToleranceProfileV1 {
    Frame3dComparisonToleranceProfileV1 {
        profile: "frame_alpha_cross_code.v1".to_owned(),
        scaled_difference: "abs(native-reference)/max(abs(native),abs(reference),absolute_floor)"
            .to_owned(),
        displacement_relative: DISPLACEMENT_TOLERANCE,
        reaction_relative: REACTION_TOLERANCE,
        member_end_force_relative: MEMBER_FORCE_TOLERANCE,
        translation_rotation_absolute_floor: DISPLACEMENT_FLOOR,
        force_moment_absolute_floor: FORCE_FLOOR,
    }
}

fn comparison_authority() -> Frame3dComparisonAuthorityV1 {
    Frame3dComparisonAuthorityV1 {
        source_result: "bounded_candidate".to_owned(),
        reference_input: "operator_declared_or_synthetic_fixture".to_owned(),
        comparison: "bounded_cross_code_evaluation".to_owned(),
        external_validation: "not_established".to_owned(),
        engineering_design: "not_authoritative".to_owned(),
        release_readiness: "not_authoritative".to_owned(),
    }
}

fn reference_schema_validator() -> Result<&'static JSONSchema, Frame3dComparisonError> {
    schema_validator(
        &REFERENCE_SCHEMA_VALIDATOR,
        REFERENCE_SCHEMA_TEXT,
        "frame3d_external_reference_schema_compile_failed",
    )
}

fn comparison_schema_validator() -> Result<&'static JSONSchema, Frame3dComparisonError> {
    schema_validator(
        &COMPARISON_SCHEMA_VALIDATOR,
        COMPARISON_SCHEMA_TEXT,
        "frame3d_comparison_ir_schema_compile_failed",
    )
}

fn schema_validator(
    lock: &'static OnceLock<Result<JSONSchema, String>>,
    text: &'static str,
    code: &str,
) -> Result<&'static JSONSchema, Frame3dComparisonError> {
    let compiled = lock.get_or_init(|| {
        let schema: Value = serde_json::from_str(text).map_err(|item| item.to_string())?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|item| item.to_string())
    });
    compiled.as_ref().map_err(|detail| error(code, "/", detail))
}

fn validate_schema(
    value: &Value,
    schema: &JSONSchema,
    code: &str,
) -> Result<(), Frame3dComparisonError> {
    if let Err(mut errors) = schema.validate(value) {
        if let Some(item) = errors.next() {
            return Err(error(
                code,
                &item.instance_path.to_string(),
                &item.to_string(),
            ));
        }
    }
    Ok(())
}

fn comparison_hash(
    comparison: &LinearFrame3dComparisonIrV1,
) -> Result<String, Frame3dComparisonError> {
    let mut value = serde_json::to_value(comparison).map_err(|_| serialization_error())?;
    let Some(root) = value.as_object_mut() else {
        return Err(serialization_error());
    };
    root.insert(
        "comparison_hash".to_owned(),
        Value::String(format!("{HASH_PREFIX}{}", "0".repeat(64))),
    );
    Ok(sha256_identity(
        canonicalize_model_ir_v2(&value)
            .map_err(|_| serialization_error())?
            .as_bytes(),
    ))
}

fn canonical_value<T: Serialize>(value: &T) -> Result<String, Frame3dComparisonError> {
    let value = serde_json::to_value(value).map_err(|_| serialization_error())?;
    canonicalize_model_ir_v2(&value).map_err(|_| serialization_error())
}

fn sha256_identity(bytes: &[u8]) -> String {
    format!("{HASH_PREFIX}{:x}", Sha256::digest(bytes))
}

fn require_hash(value: &str, path: &str) -> Result<(), Frame3dComparisonError> {
    if value.len() != HASH_LENGTH
        || !value.starts_with(HASH_PREFIX)
        || !value[HASH_PREFIX.len()..]
            .bytes()
            .all(|item| item.is_ascii_digit() || (b'a'..=b'f').contains(&item))
    {
        return Err(error(
            "frame3d_comparison_hash_invalid",
            path,
            "Expected a lowercase sha256 identity",
        ));
    }
    Ok(())
}

fn require_stable_id(value: &str, path: &str) -> Result<(), Frame3dComparisonError> {
    let mut bytes = value.bytes();
    let valid = value.len() <= 128
        && matches!(bytes.next(), Some(first) if first.is_ascii_alphabetic())
        && bytes.all(|item| item.is_ascii_alphanumeric() || b"_.:-".contains(&item));
    if !valid {
        return Err(error(
            "frame3d_comparison_id_invalid",
            path,
            "Expected a stable bounded identifier",
        ));
    }
    Ok(())
}

fn require_finite(values: &[f64; 6], path: &str) -> Result<(), Frame3dComparisonError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(error(
            "frame3d_external_reference_non_finite",
            path,
            "External reference values must be finite",
        ));
    }
    Ok(())
}

fn count_error() -> Frame3dComparisonError {
    error(
        "frame3d_comparison_count_invalid",
        "/rows",
        "Comparison row count exceeds the bounded profile",
    )
}

fn serialization_error() -> Frame3dComparisonError {
    error(
        "frame3d_comparison_ir_serialization_failed",
        "/",
        "ComparisonIR could not be represented as canonical JSON",
    )
}

fn error(code: &str, path: &str, detail: &str) -> Frame3dComparisonError {
    Frame3dComparisonError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
