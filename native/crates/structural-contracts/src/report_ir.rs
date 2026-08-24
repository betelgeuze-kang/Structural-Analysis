//! Deterministic bounded native linear `Frame3D` `ReportIR` wire contract.

use std::collections::BTreeSet;
use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::result_ir::{
    validate_linear_frame3d_result_ir_v1, Frame3dResultGatesV1, LinearFrame3dResultIrV1,
};
use crate::{FRAME3D_REPORT_IR_SCHEMA_V1, FRAME3D_RESULT_IR_SCHEMA_V1};

const SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/linear_frame3d_report_ir_v1.schema.json"
));
const HASH_PREFIX: &str = "sha256:";
const HASH_LENGTH: usize = 71;
const LIMITATIONS: [&str; 10] = [
    "cpu_only_no_hip_parity",
    "load_scope_nodal_and_uniform_initial_local_force",
    "no_nonuniform_or_member_point_load",
    "release_scope_rotational_rx_ry_rz_only",
    "released_coordinate_must_remain_globally_stable",
    "offset_scope_finite_global_rigid_end_arms",
    "no_translational_release",
    "no_nonzero_prescribed_displacement",
    "no_workbench_e2e",
    "no_design_or_release_authority",
];

static SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

/// Stable `ReportIR` construction or decoding failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Frame3dReportIrError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for Frame3dReportIrError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for Frame3dReportIrError {}

/// Exact source `ResultIR` identity consumed by the report projection.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dReportSourceResultV1 {
    pub schema_version: String,
    pub result_id: String,
    pub result_hash: String,
}

/// Stable report header values copied from the bound result.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dReportSummaryV1 {
    pub model_id: String,
    pub load_pattern_id: String,
    pub formulation: String,
    pub backend: String,
    pub node_count: u32,
    pub member_count: u32,
}

/// Deterministically tie-broken signed extremum for one output quantity family.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dReportExtremumV1 {
    pub quantity: String,
    pub entity_id: String,
    pub component: String,
    pub signed_value: f64,
    pub absolute_value: f64,
    pub unit: String,
}

/// Explicitly non-promoting report authority axes.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dReportAuthorityV1 {
    pub source_result: String,
    pub presentation: String,
    pub comparison: String,
    pub engineering_design: String,
    pub release_readiness: String,
}

/// Versioned deterministic report source, independent of HTML/PDF rendering.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct LinearFrame3dReportIrV1 {
    pub schema_version: String,
    pub report_id: String,
    pub report_hash: String,
    pub report_kind: String,
    pub source_result: Frame3dReportSourceResultV1,
    pub summary: Frame3dReportSummaryV1,
    pub gates: Frame3dResultGatesV1,
    pub extrema: Vec<Frame3dReportExtremumV1>,
    pub limitations: Vec<String>,
    pub authority: Frame3dReportAuthorityV1,
    pub claim_boundary: String,
}

impl LinearFrame3dReportIrV1 {
    /// Render compact, sorted canonical JSON including the verified report hash.
    ///
    /// # Errors
    ///
    /// Returns a stable error if serialization or canonical number encoding fails.
    pub fn canonical_json(&self) -> Result<String, Frame3dReportIrError> {
        let value = serde_json::to_value(self).map_err(|_| serialization_error())?;
        canonicalize(&value)
    }
}

/// Checked projection values computed by `structural-report` from one exact source result.
pub struct LinearFrame3dReportIrInput {
    pub report_id: String,
    pub summary: Frame3dReportSummaryV1,
    pub extrema: Vec<Frame3dReportExtremumV1>,
}

/// Construct a deterministic `ReportIR` bound to one validated `ResultIR`.
///
/// # Errors
///
/// Rejects stale source results, invalid IDs, malformed extrema, non-finite values, limitation
/// drift, hash instability or any report authority promotion. Exact extrema-to-source binding is
/// revalidated by the deterministic `structural-report` projection owner.
pub fn create_linear_frame3d_report_ir_v1(
    source: &LinearFrame3dResultIrV1,
    input: LinearFrame3dReportIrInput,
) -> Result<LinearFrame3dReportIrV1, Frame3dReportIrError> {
    validate_linear_frame3d_result_ir_v1(source)
        .map_err(|item| error("frame3d_report_ir_source_invalid", &item.path, &item.detail))?;
    let node_count = u32::try_from(source.nodes.len()).map_err(|_| {
        error(
            "frame3d_report_ir_count_invalid",
            "/summary/node_count",
            "Source node count exceeds the report range",
        )
    })?;
    let member_count = u32::try_from(source.members.len()).map_err(|_| {
        error(
            "frame3d_report_ir_count_invalid",
            "/summary/member_count",
            "Source member count exceeds the report range",
        )
    })?;
    let expected_summary = Frame3dReportSummaryV1 {
        model_id: source.bindings.model_id.clone(),
        load_pattern_id: source.bindings.load_pattern_id.clone(),
        formulation: source.solver.formulation.clone(),
        backend: source.solver.backend.clone(),
        node_count,
        member_count,
    };
    if input.summary != expected_summary {
        return Err(error(
            "frame3d_report_ir_summary_binding_mismatch",
            "/summary",
            "Report summary does not match the exact source ResultIR",
        ));
    }
    let mut report = LinearFrame3dReportIrV1 {
        schema_version: FRAME3D_REPORT_IR_SCHEMA_V1.to_owned(),
        report_id: input.report_id,
        report_hash: format!("{HASH_PREFIX}{}", "0".repeat(64)),
        report_kind: "linear_frame3d_analysis_summary".to_owned(),
        source_result: Frame3dReportSourceResultV1 {
            schema_version: source.schema_version.clone(),
            result_id: source.result_id.clone(),
            result_hash: source.result_hash.clone(),
        },
        summary: input.summary,
        gates: source.gates.clone(),
        extrema: input.extrema,
        limitations: LIMITATIONS.iter().map(|value| (*value).to_owned()).collect(),
        authority: report_authority(),
        claim_boundary:
            "deterministic_presentation_of_bounded_candidate_result_not_comparison_design_or_release_authority"
                .to_owned(),
    };
    validate_content(&report)?;
    report.report_hash = report_hash(&report)?;
    validate_linear_frame3d_report_ir_v1(&report)?;
    Ok(report)
}

/// Strictly decode, schema-check and hash-check one bounded native `ReportIR`.
///
/// # Errors
///
/// Rejects invalid JSON, duplicate keys, schema violations, non-finite values and stale hashes.
pub fn parse_linear_frame3d_report_ir_v1(
    bytes: &[u8],
) -> Result<LinearFrame3dReportIrV1, Frame3dReportIrError> {
    let value = decode_json_strict(bytes)
        .map_err(|item| error("frame3d_report_ir_json_invalid", &item.path, &item.detail))?;
    validate_schema(&value)?;
    let report = serde_json::from_value(value).map_err(|_| {
        error(
            "frame3d_report_ir_decode_failed",
            "/",
            "ReportIR JSON could not be decoded into the typed contract",
        )
    })?;
    validate_linear_frame3d_report_ir_v1(&report)?;
    Ok(report)
}

/// Validate fixed profiles, bindings, extrema, limitations, authority and report hash.
///
/// # Errors
///
/// Returns a stable contract error for the first invalid boundary.
pub fn validate_linear_frame3d_report_ir_v1(
    report: &LinearFrame3dReportIrV1,
) -> Result<(), Frame3dReportIrError> {
    let value = serde_json::to_value(report).map_err(|_| serialization_error())?;
    validate_schema(&value)?;
    validate_content(report)?;
    if report.report_hash != report_hash(report)? {
        return Err(error(
            "frame3d_report_ir_hash_mismatch",
            "/report_hash",
            "ReportIR hash does not match its canonical payload",
        ));
    }
    Ok(())
}

/// Hash arbitrary deterministic rendered bytes using the shared lowercase identity format.
#[must_use]
pub fn sha256_bytes_identity(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("{HASH_PREFIX}{digest:x}")
}

fn validate_content(report: &LinearFrame3dReportIrV1) -> Result<(), Frame3dReportIrError> {
    require_stable_id(&report.report_id, "/report_id")?;
    require_stable_id(&report.source_result.result_id, "/source_result/result_id")?;
    require_stable_id(&report.summary.model_id, "/summary/model_id")?;
    require_stable_id(&report.summary.load_pattern_id, "/summary/load_pattern_id")?;
    require_hash(&report.report_hash, "/report_hash")?;
    require_hash(
        &report.source_result.result_hash,
        "/source_result/result_hash",
    )?;
    if report.source_result.schema_version != FRAME3D_RESULT_IR_SCHEMA_V1 {
        return Err(error(
            "frame3d_report_ir_source_schema_invalid",
            "/source_result/schema_version",
            "ReportIR requires the bounded native Frame3D ResultIR v1 source",
        ));
    }
    if !(2..=16).contains(&report.summary.node_count)
        || !(1..=32).contains(&report.summary.member_count)
    {
        return Err(error(
            "frame3d_report_ir_count_invalid",
            "/summary",
            "ReportIR summary exceeds the bounded Frame Alpha profile",
        ));
    }
    validate_extrema(&report.extrema)?;
    let expected_limitations = LIMITATIONS
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<Vec<_>>();
    if report.limitations != expected_limitations || report.authority != report_authority() {
        return Err(error(
            "frame3d_report_ir_authority_invalid",
            "/authority",
            "ReportIR limitations or authority were promoted outside the presentation boundary",
        ));
    }
    Ok(())
}

fn validate_extrema(extrema: &[Frame3dReportExtremumV1]) -> Result<(), Frame3dReportIrError> {
    let expected = ["displacement", "reaction", "member_end_force"];
    if extrema.len() != expected.len()
        || extrema
            .iter()
            .zip(expected)
            .any(|(row, quantity)| row.quantity != quantity)
    {
        return Err(error(
            "frame3d_report_ir_extrema_invalid",
            "/extrema",
            "ReportIR requires displacement, reaction and member-end-force extrema in order",
        ));
    }
    let mut identities = BTreeSet::new();
    for (index, row) in extrema.iter().enumerate() {
        require_stable_id(&row.entity_id, &format!("/extrema/{index}/entity_id"))?;
        if !row.signed_value.is_finite()
            || !row.absolute_value.is_finite()
            || row.absolute_value.to_bits() != row.signed_value.abs().to_bits()
            || row.component.is_empty()
            || row.unit.is_empty()
        {
            return Err(error(
                "frame3d_report_ir_extremum_domain_invalid",
                &format!("/extrema/{index}"),
                "Report extrema require finite signed/absolute pairs, component and unit",
            ));
        }
        if !identities.insert((&row.quantity, &row.entity_id, &row.component)) {
            return Err(error(
                "frame3d_report_ir_extremum_duplicate",
                &format!("/extrema/{index}"),
                "Report extrema identities must be unique",
            ));
        }
    }
    Ok(())
}

fn validate_schema(value: &Value) -> Result<(), Frame3dReportIrError> {
    let validator = schema_validator()?;
    if let Err(errors) = validator.validate(value) {
        let mut paths = errors
            .map(|item| {
                let path = item.instance_path.to_string();
                if path.is_empty() {
                    "/".to_owned()
                } else {
                    path
                }
            })
            .collect::<Vec<_>>();
        paths.sort();
        return Err(error(
            "frame3d_report_ir_schema_invalid",
            paths.first().map_or("/", String::as_str),
            "ReportIR does not satisfy the bounded native v1 schema",
        ));
    }
    Ok(())
}

fn schema_validator() -> Result<&'static JSONSchema, Frame3dReportIrError> {
    let compiled = SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(SCHEMA_TEXT).map_err(|item| item.to_string())?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|item| item.to_string())
    });
    compiled.as_ref().map_err(|_| {
        error(
            "frame3d_report_ir_schema_contract_invalid",
            "/",
            "Embedded bounded native ReportIR schema could not be compiled",
        )
    })
}

fn report_hash(report: &LinearFrame3dReportIrV1) -> Result<String, Frame3dReportIrError> {
    let mut value = serde_json::to_value(report).map_err(|_| serialization_error())?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            error(
                "frame3d_report_ir_invariant",
                "/",
                "ReportIR root is not an object",
            )
        })?
        .remove("report_hash");
    Ok(sha256_bytes_identity(canonicalize(&value)?.as_bytes()))
}

fn canonicalize(value: &Value) -> Result<String, Frame3dReportIrError> {
    canonicalize_model_ir_v2(value).map_err(|item| {
        error(
            "frame3d_report_ir_canonicalization_failed",
            &item.path,
            &item.detail,
        )
    })
}

fn require_hash(value: &str, path: &str) -> Result<(), Frame3dReportIrError> {
    if value.len() != HASH_LENGTH
        || !value.starts_with(HASH_PREFIX)
        || !value[HASH_PREFIX.len()..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(error(
            "frame3d_report_ir_hash_invalid",
            path,
            "Expected a lowercase sha256 identity",
        ));
    }
    Ok(())
}

fn require_stable_id(value: &str, path: &str) -> Result<(), Frame3dReportIrError> {
    let mut bytes = value.bytes();
    let valid = value.len() <= 128
        && bytes.next().is_some_and(|byte| byte.is_ascii_alphabetic())
        && bytes
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b':' | b'-'));
    if valid {
        Ok(())
    } else {
        Err(error(
            "frame3d_report_ir_id_invalid",
            path,
            "Expected a stable ASCII identifier",
        ))
    }
}

fn report_authority() -> Frame3dReportAuthorityV1 {
    Frame3dReportAuthorityV1 {
        source_result: "bounded_candidate".to_owned(),
        presentation: "deterministic_projection".to_owned(),
        comparison: "not_evaluated".to_owned(),
        engineering_design: "not_authoritative".to_owned(),
        release_readiness: "not_authoritative".to_owned(),
    }
}

fn serialization_error() -> Frame3dReportIrError {
    error(
        "frame3d_report_ir_serialization_failed",
        "/",
        "ReportIR could not be represented as JSON",
    )
}

fn error(code: &str, path: &str, detail: &str) -> Frame3dReportIrError {
    Frame3dReportIrError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
