//! Durable Rust-native Workbench state and product orchestration.

#![forbid(unsafe_code)]

use std::ffi::OsStr;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use structural_cli::{
    execute_external_comparison, execute_localized_pdf_report, execute_model_ir_linear_analysis,
    execute_model_ir_linear_external_comparison, execute_model_ir_native_analysis,
    execute_native_mgt_import, execute_pdf_report, execute_sparse_linear_localized_pdf_report,
    execute_sparse_linear_pdf_report, publish_external_comparison, publish_localized_pdf_report,
    publish_model_ir_linear_analysis, publish_model_ir_linear_external_comparison,
    publish_model_ir_native_analysis, publish_pdf_report, validate_model_bytes, PdfReportLocaleV2,
};
use structural_contracts::external_comparison::{parse_external_result_v1, ExternalSourceV1};
use structural_contracts::model_ir::{
    canonicalize_model_ir_v2, decode_json_strict, parse_model_ir_v2,
};
use structural_contracts::model_linear_comparison::parse_model_ir_linear_external_result_v1;
use structural_contracts::model_linear_product::parse_model_ir_linear_analysis_request_v1;
use structural_contracts::model_linear_reactions::{
    parse_model_ir_linear_reaction_result_ir_v1, verify_model_ir_linear_reaction_result_v1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
};
use structural_contracts::product_ir::{parse_model_ir_ndtha_analysis_request_v1, sha256_identity};
use structural_contracts::product_ir::{
    parse_nonlinear_ndtha_report_ir_v1, parse_nonlinear_ndtha_result_ir_v1,
};
use structural_contracts::sparse_product::{
    parse_sparse_linear_report_ir_v1, parse_sparse_linear_result_ir_v1,
};
use structural_report::build_sparse_linear_report_v1;

mod analysis_request;
mod catalog;
mod deformed_view;
mod evidence;
mod linear_combination;
mod model_edit;
mod model_view;
mod reaction_view;
mod report_view;
mod result_view;

pub use analysis_request::{
    create_model_linear_analysis_request, create_model_linear_combination_analysis_request,
    publish_model_linear_analysis_request, publish_model_linear_combination_analysis_request,
    ModelLinearAnalysisRequestCreateOutcomeV1,
};
pub use catalog::{
    browse_embedded_benchmark_catalog, show_embedded_benchmark_case, BenchmarkCatalogFilterV1,
    BenchmarkLifecycleV1, BenchmarkSizeClassV1, BenchmarkTruthClassV1,
};
pub use deformed_view::{
    WORKBENCH_DEFORMED_VIEW_DEFAULT_SCALE_V1, WORKBENCH_DEFORMED_VIEW_MAX_SCALE_V1,
};
pub use evidence::{browse_evidence_bundle, show_evidence_artifact};
pub use model_edit::{
    add_model_direct_linear_load_combination_term, add_model_fixed_constraint,
    add_model_fixed_constraint_dof, add_model_frame3d_member, add_model_frame_section,
    add_model_linear_load_combination, add_model_linear_load_pattern, add_model_linear_material,
    add_model_nested_linear_load_combination, add_model_nested_linear_load_combination_term,
    add_model_nodal_load, add_model_node, add_model_truss3d_member, add_model_truss_section,
    delete_model_direct_linear_load_combination_term, delete_model_fixed_constraint,
    delete_model_fixed_constraint_dof, delete_model_frame3d_leaf_member,
    delete_model_frame_section, delete_model_linear_load_combination,
    delete_model_linear_load_pattern, delete_model_linear_material,
    delete_model_nested_linear_load_combination_term, delete_model_nodal_load,
    delete_model_orphan_node, delete_model_truss3d_leaf_member, delete_model_truss_section,
    edit_model_constraint_target, edit_model_constraint_value,
    edit_model_direct_linear_load_combination_factor,
    edit_model_direct_linear_load_combination_reference, edit_model_element_connectivity,
    edit_model_element_identity, edit_model_element_identity_cascade,
    edit_model_fixed_constraint_identity, edit_model_fixed_constraint_identity_cascade,
    edit_model_frame_element_orientation, edit_model_frame_element_properties,
    edit_model_frame_section, edit_model_frame_section_identity,
    edit_model_frame_section_identity_cascade, edit_model_identity,
    edit_model_linear_load_combination_identity,
    edit_model_linear_load_combination_identity_cascade, edit_model_linear_load_pattern_identity,
    edit_model_linear_load_pattern_identity_cascade, edit_model_linear_material,
    edit_model_linear_material_identity, edit_model_linear_material_identity_cascade,
    edit_model_nested_linear_load_combination_factor,
    edit_model_nested_linear_load_combination_reference, edit_model_nodal_load_components,
    edit_model_nodal_load_identity, edit_model_nodal_load_target, edit_model_node_coordinates,
    edit_model_node_identity, edit_model_node_identity_cascade,
    edit_model_truss_element_properties, edit_model_truss_section,
    edit_model_truss_section_identity, edit_model_truss_section_identity_cascade,
    insert_model_direct_linear_load_combination_term,
    insert_model_nested_linear_load_combination_term, publish_model_constraint_target_edit,
    publish_model_constraint_value_edit, publish_model_direct_linear_load_combination_factor_edit,
    publish_model_direct_linear_load_combination_reference_edit,
    publish_model_direct_linear_load_combination_term_add,
    publish_model_direct_linear_load_combination_term_delete,
    publish_model_direct_linear_load_combination_term_insert,
    publish_model_direct_linear_load_combination_term_reorder,
    publish_model_element_connectivity_edit, publish_model_element_identity_cascade_edit,
    publish_model_element_identity_edit, publish_model_fixed_constraint_add,
    publish_model_fixed_constraint_delete, publish_model_fixed_constraint_dof_add,
    publish_model_fixed_constraint_dof_delete, publish_model_fixed_constraint_dof_reorder,
    publish_model_fixed_constraint_identity_cascade_edit,
    publish_model_fixed_constraint_identity_edit, publish_model_frame3d_leaf_member_delete,
    publish_model_frame3d_member_add, publish_model_frame_element_orientation_edit,
    publish_model_frame_element_properties_edit, publish_model_frame_section_add,
    publish_model_frame_section_delete, publish_model_frame_section_edit,
    publish_model_frame_section_identity_cascade_edit, publish_model_frame_section_identity_edit,
    publish_model_identity_edit, publish_model_linear_load_combination_add,
    publish_model_linear_load_combination_delete,
    publish_model_linear_load_combination_identity_cascade_edit,
    publish_model_linear_load_combination_identity_edit, publish_model_linear_load_pattern_add,
    publish_model_linear_load_pattern_delete,
    publish_model_linear_load_pattern_identity_cascade_edit,
    publish_model_linear_load_pattern_identity_edit, publish_model_linear_material_add,
    publish_model_linear_material_delete, publish_model_linear_material_edit,
    publish_model_linear_material_identity_cascade_edit,
    publish_model_linear_material_identity_edit, publish_model_nested_linear_load_combination_add,
    publish_model_nested_linear_load_combination_factor_edit,
    publish_model_nested_linear_load_combination_reference_edit,
    publish_model_nested_linear_load_combination_term_add,
    publish_model_nested_linear_load_combination_term_delete,
    publish_model_nested_linear_load_combination_term_insert,
    publish_model_nested_linear_load_combination_term_reorder, publish_model_nodal_load_add,
    publish_model_nodal_load_components_edit, publish_model_nodal_load_delete,
    publish_model_nodal_load_identity_edit, publish_model_nodal_load_target_edit,
    publish_model_node_add, publish_model_node_coordinate_edit,
    publish_model_node_identity_cascade_edit, publish_model_node_identity_edit,
    publish_model_orphan_node_delete, publish_model_truss3d_leaf_member_delete,
    publish_model_truss3d_member_add, publish_model_truss_element_properties_edit,
    publish_model_truss_section_add, publish_model_truss_section_delete,
    publish_model_truss_section_edit, publish_model_truss_section_identity_cascade_edit,
    publish_model_truss_section_identity_edit, reorder_model_direct_linear_load_combination_term,
    reorder_model_fixed_constraint_dof, reorder_model_nested_linear_load_combination_term,
    FrameSectionParametersV1, LinearElasticMaterialParametersV1,
    LinearLoadCombinationReferenceKindV1, LinearLoadCombinationTermV1,
    ModelConstraintTargetEditOutcomeV1, ModelConstraintValueEditOutcomeV1,
    ModelElementConnectivityEditOutcomeV1, ModelElementIdentityCascadeEditOutcomeV2,
    ModelElementIdentityEditOutcomeV1, ModelFixedConstraintAddOutcomeV1,
    ModelFixedConstraintDeleteOutcomeV1, ModelFixedConstraintDofAddOutcomeV1,
    ModelFixedConstraintDofDeleteOutcomeV1, ModelFixedConstraintDofReorderOutcomeV1,
    ModelFixedConstraintIdentityCascadeEditOutcomeV2, ModelFixedConstraintIdentityEditOutcomeV1,
    ModelFrame3dLeafMemberDeleteOutcomeV1, ModelFrame3dMemberAddOutcomeV1,
    ModelFrameElementOrientationEditOutcomeV1, ModelFrameElementPropertiesEditOutcomeV1,
    ModelFrameSectionAddOutcomeV1, ModelFrameSectionDeleteOutcomeV1,
    ModelFrameSectionEditOutcomeV1, ModelFrameSectionIdentityCascadeEditOutcomeV2,
    ModelFrameSectionIdentityEditOutcomeV1, ModelIdentityEditOutcomeV1,
    ModelLinearLoadCombinationAddOutcomeV1, ModelLinearLoadCombinationDeleteOutcomeV1,
    ModelLinearLoadCombinationFactorEditOutcomeV1,
    ModelLinearLoadCombinationIdentityCascadeEditOutcomeV2,
    ModelLinearLoadCombinationIdentityEditOutcomeV1,
    ModelLinearLoadCombinationReferenceEditOutcomeV1, ModelLinearLoadCombinationTermAddOutcomeV1,
    ModelLinearLoadCombinationTermDeleteOutcomeV1, ModelLinearLoadCombinationTermInsertOutcomeV1,
    ModelLinearLoadCombinationTermReorderOutcomeV1, ModelLinearLoadPatternAddOutcomeV1,
    ModelLinearLoadPatternDeleteOutcomeV1, ModelLinearLoadPatternIdentityCascadeEditOutcomeV2,
    ModelLinearLoadPatternIdentityEditOutcomeV1, ModelLinearMaterialAddOutcomeV1,
    ModelLinearMaterialDeleteOutcomeV1, ModelLinearMaterialEditOutcomeV1,
    ModelLinearMaterialIdentityCascadeEditOutcomeV2, ModelLinearMaterialIdentityEditOutcomeV1,
    ModelNestedLinearLoadCombinationTermAddOutcomeV1,
    ModelNestedLinearLoadCombinationTermDeleteOutcomeV1,
    ModelNestedLinearLoadCombinationTermInsertOutcomeV1,
    ModelNestedLinearLoadCombinationTermReorderOutcomeV1, ModelNodalLoadAddOutcomeV1,
    ModelNodalLoadDeleteOutcomeV1, ModelNodalLoadEditOutcomeV1,
    ModelNodalLoadIdentityEditOutcomeV1, ModelNodalLoadTargetEditOutcomeV1, ModelNodeAddOutcomeV1,
    ModelNodeEditOutcomeV1, ModelNodeIdentityCascadeEditOutcomeV2, ModelNodeIdentityEditOutcomeV1,
    ModelOrphanNodeDeleteOutcomeV1, ModelTruss3dLeafMemberDeleteOutcomeV1,
    ModelTruss3dMemberAddOutcomeV1, ModelTrussElementPropertiesEditOutcomeV1,
    ModelTrussSectionAddOutcomeV1, ModelTrussSectionDeleteOutcomeV1,
    ModelTrussSectionEditOutcomeV1, ModelTrussSectionIdentityCascadeEditOutcomeV2,
    ModelTrussSectionIdentityEditOutcomeV1, NestedLinearLoadCombinationTermV1,
    TrussSectionParametersV1, MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1,
    MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1,
};
pub use model_view::{
    render_model_topology_view, render_model_topology_view_file,
    render_model_topology_view_file_localized, render_model_topology_view_localized,
    ModelTopologyProjectionV1,
};
pub use reaction_view::{
    WORKBENCH_REACTION_VIEW_DEFAULT_COUNT_V1, WORKBENCH_REACTION_VIEW_MAX_COUNT_V1,
};
pub use report_view::WorkbenchReportLocaleV1;
pub use result_view::{
    WorkbenchResultChannelV1, WORKBENCH_RESULT_VIEW_DEFAULT_COUNT_V1,
    WORKBENCH_RESULT_VIEW_MAX_COUNT_V1,
};

const SESSION_SCHEMA_V1: &str = "structural-native-workbench-session.v1";
const IMPORT_RECEIPT_SCHEMA_V1: &str = "structural-native-workbench-import-receipt.v1";
const VALIDATION_RECEIPT_SCHEMA_V1: &str = "structural-native-workbench-validation-receipt.v1";
const CLAIM_BOUNDARY: &str = "bounded_terminal_rust_native_workbench_for_one_fixed_guided_model_ir_ndtha_profile_not_general_gui_live_external_solver_rocm_package_or_c6_decommission";
const MODEL_IR_LINEAR_CLAIM_BOUNDARY: &str = "bounded_terminal_rust_native_workbench_for_one_model_ir_linear_cpu_profile_with_recovered_global_dof_comparison_and_deterministic_pdf_not_general_gui_live_external_solver_rocm_package_or_c6_decommission";
const SESSION_FILE: &str = "workbench-session.json";
const IMPORT_DIRECTORY: &str = "01-import";
const VALIDATION_DIRECTORY: &str = "02-validate";
const RUN_DIRECTORY: &str = "03-run";
const RESUME_DIRECTORY: &str = "04-resume";
const COMPARISON_DIRECTORY: &str = "05-compare";
const REPORT_DIRECTORY: &str = "06-report";
const REVIEW_DIRECTORY: &str = "07-review";
const REVIEW_FILE: &str = "review.json";
const REVIEW_SCHEMA_V1: &str = "structural-native-workbench-review.v1";
const VIEW_SCHEMA_V1: &str = "structural-native-workbench-view.v1";
const EXPORT_SCHEMA_V1: &str = "structural-native-workbench-export.v1";
const REVIEW_CLAIM_BOUNDARY: &str = "explicit_human_review_bound_to_verified_native_result_comparison_and_pdf_not_an_automated_engineering_verdict_or_signature";
const MODEL_IR_LINEAR_REVIEW_CLAIM_BOUNDARY_LEGACY: &str = "explicit_human_review_bound_to_verified_model_ir_linear_result_recovery_comparison_report_ir_document_source_and_pdf_not_an_automated_engineering_verdict_or_signature";
const MODEL_IR_LINEAR_REACTION_REVIEW_CLAIM_BOUNDARY: &str = "explicit_human_review_bound_to_verified_model_ir_linear_result_recovery_constrained_reaction_result_comparison_report_ir_document_source_and_pdf_not_an_automated_engineering_verdict_or_signature";
const MAX_MODEL_BYTES: u64 = 64 * 1024 * 1024;
const MAX_REQUEST_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EXTERNAL_RESULT_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EXTERNAL_ARTIFACT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_PRODUCT_ARTIFACT_BYTES: u64 = 300 * 1024 * 1024;
static OUTPUT_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// A stable Workbench failure suitable for a CLI/API error envelope.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkbenchError {
    pub code: &'static str,
    pub detail: String,
}

impl WorkbenchError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for WorkbenchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for WorkbenchError {}

/// Ordered product stages exposed by the terminal-native Workbench.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkbenchStageV1 {
    Imported,
    Validated,
    Checkpointed,
    Terminal,
    Compared,
    Reported,
}

/// Explicit opt-in analysis profile. Absence in a v1 session means the byte-stable legacy NDTHA
/// profile so existing durable sessions keep their exact canonical representation.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkbenchAnalysisProfileV1 {
    ModelIrLinearCpuV1,
}

impl WorkbenchAnalysisProfileV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::ModelIrLinearCpuV1 => "model_ir_linear_cpu_v1",
        }
    }
}

impl WorkbenchStageV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Imported => "imported",
            Self::Validated => "validated",
            Self::Checkpointed => "checkpointed",
            Self::Terminal => "terminal",
            Self::Compared => "compared",
            Self::Reported => "reported",
        }
    }
}

/// Explicit human disposition. It is never derived from solver or comparison status.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkbenchReviewDecisionV1 {
    Pass,
    Review,
    Fail,
}

impl WorkbenchReviewDecisionV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Pass => "pass",
            Self::Review => "review",
            Self::Fail => "fail",
        }
    }

    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "pass" => Some(Self::Pass),
            "review" => Some(Self::Review),
            "fail" => Some(Self::Fail),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct WorkbenchReviewV1 {
    schema_version: String,
    session_id: String,
    source_session_hash: String,
    decision: WorkbenchReviewDecisionV1,
    reviewer: String,
    comment: String,
    result_artifact_hash: String,
    comparison_artifact_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pdf_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    result_recovery_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    reaction_result_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    report_document_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    analysis_profile: Option<WorkbenchAnalysisProfileV1>,
    claim_boundary: String,
    review_hash: String,
}

/// Self-hashed durable Workbench state. Paths are intentionally excluded.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkbenchSessionV1 {
    schema_version: String,
    session_id: String,
    stage: WorkbenchStageV1,
    source_model_ir_hash: String,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    external_result_hash: String,
    source_artifact_hash: String,
    executable_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    analysis_profile: Option<WorkbenchAnalysisProfileV1>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_source_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_import_health_artifact_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    mgt_import_receipt_artifact_hash: Option<String>,
    terminal_status: Option<String>,
    comparison_passed: Option<bool>,
    claim_boundary: String,
    session_hash: String,
}

impl WorkbenchSessionV1 {
    #[must_use]
    pub const fn stage(&self) -> WorkbenchStageV1 {
        self.stage
    }

    #[must_use]
    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    #[must_use]
    pub fn terminal_status(&self) -> Option<&str> {
        self.terminal_status.as_deref()
    }

    #[must_use]
    pub const fn comparison_passed(&self) -> Option<bool> {
        self.comparison_passed
    }

    #[must_use]
    pub const fn analysis_profile(&self) -> Option<WorkbenchAnalysisProfileV1> {
        self.analysis_profile
    }

    #[must_use]
    pub const fn analysis_profile_label(&self) -> &'static str {
        match self.analysis_profile {
            Some(profile) => profile.label(),
            None => "fixed_guided_model_ir_ndtha_v1",
        }
    }
}

/// A durable controller that invokes product libraries directly, never subprocess adapters.
#[derive(Debug)]
pub struct NativeWorkbench {
    root: PathBuf,
    session: WorkbenchSessionV1,
}

#[derive(Clone, Copy, Debug)]
struct MgtImportEvidence<'a> {
    source: &'a [u8],
    health: &'a str,
    validation: &'a str,
    snapshot: &'a str,
    receipt: &'a str,
}

impl NativeWorkbench {
    /// Read bounded non-symlink input files and initialize a new Workbench.
    ///
    /// # Errors
    ///
    /// Returns the same strict input and publication errors as [`Self::initialize`].
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_paths(
        root: &Path,
        source_model_ir_path: &Path,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_model_ir = read_bounded_regular_file(source_model_ir_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize(
            root,
            &source_model_ir,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Read bounded, non-symlinked inputs and initialize the opt-in `ModelIR` linear CPU profile.
    ///
    /// # Errors
    ///
    /// Rejects unsafe paths, malformed or identity-mismatched inputs, and existing destinations.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_model_ir_linear_from_paths(
        root: &Path,
        source_model_ir_path: &Path,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_model_ir = read_bounded_regular_file(source_model_ir_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize_model_ir_linear(
            root,
            &source_model_ir,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Read an original MGT source, retain its import-health evidence, and initialize a new
    /// Workbench from the exact normalized `ModelIR`.
    ///
    /// # Errors
    ///
    /// Rejects a blocked/unsupported MGT import, an identity-mismatched analysis request, unsafe
    /// input paths, or any durable publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_mgt_paths(
        root: &Path,
        source_mgt_path: &Path,
        model_id: &str,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_mgt = read_bounded_regular_file(source_mgt_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize_from_mgt(
            root,
            &source_mgt,
            model_id,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Read an original MGT source, retain its import-health evidence, and initialize the opt-in
    /// `ModelIR` linear CPU profile from the exact normalized model.
    ///
    /// # Errors
    ///
    /// Rejects a blocked/unsupported MGT import, an identity-mismatched linear request, unsafe
    /// input paths, or any durable publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_model_ir_linear_from_mgt_paths(
        root: &Path,
        source_mgt_path: &Path,
        model_id: &str,
        analysis_request_path: &Path,
        external_result_path: &Path,
        source_artifact_path: &Path,
        executable_artifact_path: Option<&Path>,
    ) -> Result<Self, WorkbenchError> {
        let source_mgt = read_bounded_regular_file(source_mgt_path, MAX_MODEL_BYTES)?;
        let analysis_request = read_bounded_regular_file(analysis_request_path, MAX_REQUEST_BYTES)?;
        let external_result =
            read_bounded_regular_file(external_result_path, MAX_EXTERNAL_RESULT_BYTES)?;
        let source_artifact =
            read_bounded_regular_file(source_artifact_path, MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_artifact = executable_artifact_path
            .map(|path| read_bounded_regular_file(path, MAX_EXTERNAL_ARTIFACT_BYTES))
            .transpose()?;
        Self::initialize_model_ir_linear_from_mgt(
            root,
            &source_mgt,
            model_id,
            &analysis_request,
            &external_result,
            &source_artifact,
            executable_artifact.as_deref(),
        )
    }

    /// Normalize one bounded MGT source through Rust/C++ product owners and create a durable
    /// Workbench import stage containing the original bytes and complete import evidence.
    ///
    /// # Errors
    ///
    /// Returns a stable Workbench error for blocked import health, missing normalized artifacts,
    /// identity mismatch, or publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_from_mgt(
        root: &Path,
        source_mgt: &[u8],
        model_id: &str,
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        Self::initialize_from_mgt_with_profile(
            root,
            source_mgt,
            model_id,
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            None,
        )
    }

    /// Normalize one bounded MGT source and create a durable `ModelIR` linear CPU Workbench.
    ///
    /// # Errors
    ///
    /// Returns a stable Workbench error for blocked import health, missing normalized artifacts,
    /// linear identity mismatch, or publication failure.
    #[allow(clippy::too_many_arguments)]
    pub fn initialize_model_ir_linear_from_mgt(
        root: &Path,
        source_mgt: &[u8],
        model_id: &str,
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        Self::initialize_from_mgt_with_profile(
            root,
            source_mgt,
            model_id,
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1),
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn initialize_from_mgt_with_profile(
        root: &Path,
        source_mgt: &[u8],
        model_id: &str,
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
        analysis_profile: Option<WorkbenchAnalysisProfileV1>,
    ) -> Result<Self, WorkbenchError> {
        verify_slice_bound(source_mgt, MAX_MODEL_BYTES, "MGT source")?;
        let imported = execute_native_mgt_import(source_mgt, model_id)
            .map_err(|error| input_error("workbench_mgt_import_failed", &error))?;
        if !imported.is_normalized() {
            return Err(WorkbenchError::new(
                "workbench_mgt_import_blocked",
                "MGT import health is blocked and cannot start an analysis Workbench",
            ));
        }
        let (Some(model), Some(validation), Some(snapshot)) = (
            imported.model_ir_json(),
            imported.validation_json(),
            imported.snapshot_json(),
        ) else {
            return Err(WorkbenchError::new(
                "workbench_mgt_import_incomplete",
                "normalized MGT import did not publish ModelIR and C++ validation artifacts",
            ));
        };
        Self::initialize_with_mgt_evidence(
            root,
            model.as_bytes(),
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            analysis_profile,
            Some(MgtImportEvidence {
                source: imported.source_bytes(),
                health: imported.health_json(),
                validation,
                snapshot,
                receipt: imported.receipt_json(),
            }),
        )
    }

    /// Create a new immutable input set and publish its first durable session atomically.
    ///
    /// # Errors
    ///
    /// Rejects malformed or identity-mismatched inputs, symlinked/existing destinations and
    /// publication failures.
    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    pub fn initialize(
        root: &Path,
        source_model_ir: &[u8],
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        Self::initialize_with_mgt_evidence(
            root,
            source_model_ir,
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            None,
            None,
        )
    }

    /// Create a new immutable `ModelIR` linear CPU Workbench input set.
    ///
    /// # Errors
    ///
    /// Rejects malformed or identity-mismatched inputs, symlinked/existing destinations, and
    /// provenance/publication failures.
    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    pub fn initialize_model_ir_linear(
        root: &Path,
        source_model_ir: &[u8],
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
    ) -> Result<Self, WorkbenchError> {
        Self::initialize_with_mgt_evidence(
            root,
            source_model_ir,
            analysis_request,
            external_result,
            source_artifact,
            executable_artifact,
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1),
            None,
        )
    }

    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    fn initialize_with_mgt_evidence(
        root: &Path,
        source_model_ir: &[u8],
        analysis_request: &[u8],
        external_result: &[u8],
        source_artifact: &[u8],
        executable_artifact: Option<&[u8]>,
        analysis_profile: Option<WorkbenchAnalysisProfileV1>,
        mgt: Option<MgtImportEvidence<'_>>,
    ) -> Result<Self, WorkbenchError> {
        if root.exists() {
            return Err(WorkbenchError::new(
                "workbench_destination_exists",
                "the Workbench directory must not already exist",
            ));
        }
        verify_slice_bound(source_model_ir, MAX_MODEL_BYTES, "ModelIR")?;
        verify_slice_bound(
            analysis_request,
            MAX_REQUEST_BYTES,
            "model analysis request",
        )?;
        verify_slice_bound(
            external_result,
            MAX_EXTERNAL_RESULT_BYTES,
            "external result",
        )?;
        verify_slice_bound(
            source_artifact,
            MAX_EXTERNAL_ARTIFACT_BYTES,
            "external source artifact",
        )?;
        if let Some(bytes) = executable_artifact {
            verify_slice_bound(
                bytes,
                MAX_EXTERNAL_ARTIFACT_BYTES,
                "external executable artifact",
            )?;
        }
        if let Some(evidence) = mgt {
            verify_slice_bound(evidence.source, MAX_MODEL_BYTES, "MGT source")?;
            verify_slice_bound(
                evidence.health.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT import health",
            )?;
            verify_slice_bound(
                evidence.validation.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT native validation",
            )?;
            verify_slice_bound(
                evidence.snapshot.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT native snapshot",
            )?;
            verify_slice_bound(
                evidence.receipt.as_bytes(),
                MAX_MODEL_BYTES,
                "MGT import receipt",
            )?;
        }
        let parent = output_parent(root);
        verify_directory(parent, "workbench_output_parent_invalid")?;

        let model = parse_model_ir_v2(source_model_ir)
            .map_err(|error| input_error("workbench_model_ir_invalid", &error))?;
        let (analysis_request_hash, canonical_analysis_request) = match analysis_profile {
            None => {
                let request = parse_model_ir_ndtha_analysis_request_v1(analysis_request)
                    .map_err(|error| input_error("workbench_analysis_request_invalid", &error))?;
                verify_requested_model_identity(&request.request().model_identity, &model)?;
                (
                    request.request_hash().to_owned(),
                    request.canonical_json().to_owned(),
                )
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let request = parse_model_ir_linear_analysis_request_v1(analysis_request)
                    .map_err(|error| input_error("workbench_analysis_request_invalid", &error))?;
                verify_requested_model_identity(&request.request().model_identity, &model)?;
                (
                    request.request_hash().to_owned(),
                    request.canonical_json().to_owned(),
                )
            }
        };
        let (external_result_hash, canonical_external_result) = match analysis_profile {
            None => {
                let external = parse_external_result_v1(external_result)
                    .map_err(|error| input_error("workbench_external_result_invalid", &error))?;
                verify_external_source_artifact_bindings(
                    &external.external_result().source,
                    source_artifact,
                    executable_artifact,
                )?;
                (
                    external.external_result_hash().to_owned(),
                    external.canonical_json().to_owned(),
                )
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let external = parse_model_ir_linear_external_result_v1(external_result)
                    .map_err(|error| input_error("workbench_external_result_invalid", &error))?;
                verify_external_source_artifact_bindings(
                    &external.external_result().source,
                    source_artifact,
                    executable_artifact,
                )?;
                (
                    external.external_result_hash().to_owned(),
                    external.canonical_json().to_owned(),
                )
            }
        };

        let source_model_ir_hash = sha256_identity(source_model_ir);
        let source_artifact_hash = sha256_identity(source_artifact);
        let executable_artifact_hash = executable_artifact.map(sha256_identity);
        let mgt_source_hash = mgt.map(|evidence| sha256_identity(evidence.source));
        let mgt_import_health_artifact_hash =
            mgt.map(|evidence| sha256_identity(evidence.health.as_bytes()));
        let mgt_import_receipt_artifact_hash =
            mgt.map(|evidence| sha256_identity(evidence.receipt.as_bytes()));
        let mut binding = json!({
            "source_model_ir_hash": source_model_ir_hash,
            "model_content_hash": model.content_hash(),
            "model_semantic_hash": model.semantic_hash(),
            "model_provenance_hash": model.provenance_hash(),
            "analysis_request_hash": analysis_request_hash,
            "external_result_hash": external_result_hash,
            "source_artifact_hash": source_artifact_hash,
            "executable_artifact_hash": executable_artifact_hash,
        });
        if let Some(profile) = analysis_profile {
            binding
                .as_object_mut()
                .expect("Workbench binding is an object")
                .insert("analysis_profile".to_owned(), json!(profile));
        }
        if let (Some(source_hash), Some(health_hash), Some(receipt_hash)) = (
            mgt_source_hash.as_deref(),
            mgt_import_health_artifact_hash.as_deref(),
            mgt_import_receipt_artifact_hash.as_deref(),
        ) {
            binding
                .as_object_mut()
                .expect("Workbench binding is an object")
                .insert(
                    "mgt_import".to_owned(),
                    json!({
                        "source_hash": source_hash,
                        "health_artifact_hash": health_hash,
                        "receipt_artifact_hash": receipt_hash,
                    }),
                );
        }
        let binding_json = canonical_json(&binding, "workbench_session_identity_failed")?;
        let session_id = sha256_identity(binding_json.as_bytes());
        let session = WorkbenchSessionV1 {
            schema_version: SESSION_SCHEMA_V1.to_owned(),
            session_id: session_id.clone(),
            stage: WorkbenchStageV1::Imported,
            source_model_ir_hash,
            model_content_hash: model.content_hash().to_owned(),
            model_semantic_hash: model.semantic_hash().to_owned(),
            model_provenance_hash: model.provenance_hash().to_owned(),
            analysis_request_hash,
            external_result_hash,
            source_artifact_hash,
            executable_artifact_hash,
            analysis_profile,
            mgt_source_hash,
            mgt_import_health_artifact_hash,
            mgt_import_receipt_artifact_hash,
            terminal_status: None,
            comparison_passed: None,
            claim_boundary: session_claim_boundary(analysis_profile).to_owned(),
            session_hash: String::new(),
        };
        let session_json = canonical_session(&session)?;
        let mut inventory = vec![
            artifact_entry(
                if mgt.is_some() {
                    "normalized_source_model_ir"
                } else {
                    "original_model_ir"
                },
                "source-model-ir.json",
                "application/json",
                source_model_ir,
            )?,
            artifact_entry(
                "canonical_model_ir",
                "model-ir.json",
                "application/json",
                model.canonical_bytes(),
            )?,
            artifact_entry(
                "model_analysis_request",
                "model-analysis-request.json",
                "application/json",
                canonical_analysis_request.as_bytes(),
            )?,
            artifact_entry(
                "external_result",
                "external-result.json",
                "application/json",
                canonical_external_result.as_bytes(),
            )?,
            artifact_entry(
                "external_source_artifact",
                "external-source.artifact",
                "application/octet-stream",
                source_artifact,
            )?,
        ];
        if let Some(bytes) = executable_artifact {
            inventory.push(artifact_entry(
                "external_executable_artifact",
                "external-executable.artifact",
                "application/octet-stream",
                bytes,
            )?);
        }
        if let Some(evidence) = mgt {
            inventory.extend([
                artifact_entry(
                    "original_mgt_source",
                    "source.mgt",
                    "application/octet-stream",
                    evidence.source,
                )?,
                artifact_entry(
                    "mgt_import_health",
                    "import-health.json",
                    "application/json",
                    evidence.health.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_cpp_validation_report",
                    "mgt-native-validation.json",
                    "application/json",
                    evidence.validation.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_cpp_canonical_snapshot",
                    "mgt-native-snapshot.json",
                    "application/json",
                    evidence.snapshot.as_bytes(),
                )?,
                artifact_entry(
                    "mgt_import_receipt",
                    "mgt-import-receipt.json",
                    "application/json",
                    evidence.receipt.as_bytes(),
                )?,
            ]);
        }
        let mut import_receipt_value = json!({
            "schema_version": IMPORT_RECEIPT_SCHEMA_V1,
            "session_id": session_id,
            "status": "imported",
            "artifacts": inventory,
            "claim_boundary": if analysis_profile.is_some() && mgt.is_some() {
                "bounded_original_mgt_import_health_normalized_modelir_cpp_snapshot_and_linear_input_ingestion_only_not_solver_execution_or_external_acceptance"
            } else if analysis_profile.is_some() {
                "strict_language_neutral_model_ir_linear_input_ingestion_only_not_cpp_validation_solver_execution_or_external_acceptance"
            } else if mgt.is_some() {
                "bounded_original_mgt_import_health_normalized_modelir_and_cpp_snapshot_bound_to_one_native_workbench_profile"
            } else {
                "strict_language_neutral_input_ingestion_only_not_cpp_validation_or_solver_execution"
            },
        });
        if let Some(profile) = analysis_profile {
            import_receipt_value
                .as_object_mut()
                .expect("Workbench import receipt is an object")
                .insert("analysis_profile".to_owned(), json!(profile));
        }
        let import_receipt = canonical_self_hashed(import_receipt_value)?;
        let mut artifacts = vec![
            ("source-model-ir.json", source_model_ir),
            ("model-ir.json", model.canonical_bytes()),
            (
                "model-analysis-request.json",
                canonical_analysis_request.as_bytes(),
            ),
            ("external-result.json", canonical_external_result.as_bytes()),
            ("external-source.artifact", source_artifact),
        ];
        if let Some(evidence) = mgt {
            artifacts.extend([
                ("source.mgt", evidence.source),
                ("import-health.json", evidence.health.as_bytes()),
                ("mgt-native-validation.json", evidence.validation.as_bytes()),
                ("mgt-native-snapshot.json", evidence.snapshot.as_bytes()),
                ("mgt-import-receipt.json", evidence.receipt.as_bytes()),
            ]);
        }
        publish_initial_workspace(
            root,
            &artifacts,
            executable_artifact,
            import_receipt.as_bytes(),
            session_json.as_bytes(),
        )?;
        Ok(Self {
            root: root.to_path_buf(),
            session: parse_session(session_json.as_bytes())?,
        })
    }

    /// Open and verify a durable session, reconciling an atomic stage publication after a crash.
    ///
    /// # Errors
    ///
    /// Rejects a symlinked root, a tampered session/input/receipt, a stage gap or missing artifacts.
    pub fn open(root: &Path) -> Result<Self, WorkbenchError> {
        verify_directory(root, "workbench_directory_invalid")?;
        let session_bytes =
            read_bounded_regular_file(&root.join(SESSION_FILE), MAX_EXTERNAL_RESULT_BYTES)?;
        let mut session = parse_session(&session_bytes)?;
        verify_import_bindings(root, &session)?;
        let discovered = verify_stage_chain(root, &session)?;
        if session.stage > discovered.stage {
            return Err(WorkbenchError::new(
                "workbench_session_ahead_of_artifacts",
                "the durable session claims a stage whose atomic artifacts are absent",
            ));
        }
        session.stage = discovered.stage;
        session.terminal_status = discovered.terminal_status;
        session.comparison_passed = discovered.comparison_passed;
        verify_optional_review(root, &session)?;
        Ok(Self {
            root: root.to_path_buf(),
            session,
        })
    }

    #[must_use]
    pub const fn session(&self) -> &WorkbenchSessionV1 {
        &self.session
    }

    /// Return the reconciled, self-hashed canonical session bytes.
    ///
    /// # Errors
    ///
    /// Returns an invariant failure if the state cannot be canonically serialized.
    pub fn session_json(&self) -> Result<String, WorkbenchError> {
        canonical_session(&self.session)
    }

    /// Return a deterministic operator view over the verified durable stage chain.
    ///
    /// The view contains only product-owned identities, status, summaries and relative artifact
    /// references. It never infers an engineering verdict from solver or comparison success.
    ///
    /// # Errors
    ///
    /// Returns an invariant error if a verified product artifact cannot be decoded or projected.
    #[allow(clippy::too_many_lines)]
    pub fn inspect_json(&self) -> Result<String, WorkbenchError> {
        let stages = [
            (WorkbenchStageV1::Imported, "import"),
            (WorkbenchStageV1::Validated, "validate"),
            (WorkbenchStageV1::Checkpointed, "run"),
            (WorkbenchStageV1::Terminal, "resume"),
            (WorkbenchStageV1::Compared, "compare"),
            (WorkbenchStageV1::Reported, "report"),
        ];
        let workflow = stages
            .iter()
            .map(|(required, label)| {
                json!({
                    "stage": label,
                    "state": if self.session.stage >= *required { "complete" } else { "pending" },
                })
            })
            .collect::<Vec<_>>();

        let (result_summary, backend_receipt) = if self.session.stage >= WorkbenchStageV1::Terminal
        {
            let value = strict_artifact_json(
                &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
                "workbench_result_view_invalid",
            )?;
            (
                value.get("summary").cloned().unwrap_or(Value::Null),
                value.get("backend_receipt").cloned().unwrap_or(Value::Null),
            )
        } else {
            (Value::Null, Value::Null)
        };
        let constrained_reactions = if self.session.stage >= WorkbenchStageV1::Terminal
            && self.session.analysis_profile.is_some()
        {
            read_optional_bounded_regular_file(
                &self
                    .root
                    .join(RESUME_DIRECTORY)
                    .join("reaction-result-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?
            .map_or(Ok(Value::Null), |bytes| {
                let reaction = parse_model_ir_linear_reaction_result_ir_v1(&bytes)
                    .map_err(|error| input_error("workbench_reaction_view_invalid", &error))?;
                Ok(json!({
                    "result_hash": reaction.result_hash(),
                    "summary": reaction.result().summary,
                    "units": reaction.result().units,
                    "backend_receipt": reaction.result().backend_receipt,
                }))
            })?
        } else {
            Value::Null
        };
        let comparison = if self.session.stage >= WorkbenchStageV1::Compared {
            let receipt = verified_receipt_json(
                &self
                    .root
                    .join(COMPARISON_DIRECTORY)
                    .join("comparison-receipt.json"),
            )?;
            json!({
                "status": receipt.get("status").cloned().unwrap_or(Value::Null),
                "comparison_hash": receipt.get("comparison_hash").cloned().unwrap_or(Value::Null),
            })
        } else {
            Value::Null
        };
        let report = if self.session.stage >= WorkbenchStageV1::Reported {
            match self.session.analysis_profile {
                None => {
                    let receipt = verified_receipt_json(
                        &self.root.join(REPORT_DIRECTORY).join("pdf-receipt.json"),
                    )?;
                    json!({
                        "pdf_hash": receipt.get("pdf_hash").cloned().unwrap_or(Value::Null),
                        "source_result_hash": receipt.get("source_result_hash").cloned().unwrap_or(Value::Null),
                        "source_report_hash": receipt.get("source_report_hash").cloned().unwrap_or(Value::Null),
                    })
                }
                Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                    let receipt = verified_receipt_json(
                        &self.root.join(REPORT_DIRECTORY).join("report-receipt.json"),
                    )?;
                    json!({
                        "pdf_hash": receipt.get("pdf_hash").cloned().unwrap_or(Value::Null),
                        "document_source_hash": receipt.get("document_source_hash").cloned().unwrap_or(Value::Null),
                        "source_result_hash": receipt.get("source_result_hash").cloned().unwrap_or(Value::Null),
                        "source_recovery_hash": receipt.get("source_recovery_hash").cloned().unwrap_or(Value::Null),
                        "source_reaction_hash": receipt.get("source_reaction_hash").cloned().unwrap_or(Value::Null),
                        "source_report_hash": receipt.get("source_report_hash").cloned().unwrap_or(Value::Null),
                    })
                }
            }
        } else {
            Value::Null
        };
        let review = read_optional_review(&self.root, &self.session)?;
        let review_view = review.as_ref().map_or(Value::Null, |review| {
            json!({
                "decision": review.decision,
                "reviewer": review.reviewer,
                "comment": review.comment,
                "review_hash": review.review_hash,
                "automatically_inferred": false,
            })
        });
        let next_action = if review.is_some() {
            "export"
        } else {
            match self.session.stage {
                WorkbenchStageV1::Imported => "validate",
                WorkbenchStageV1::Validated => "run",
                WorkbenchStageV1::Checkpointed => "resume",
                WorkbenchStageV1::Terminal => "compare",
                WorkbenchStageV1::Compared => "report",
                WorkbenchStageV1::Reported => "review",
            }
        };
        let mut view = json!({
            "schema_version": VIEW_SCHEMA_V1,
            "session_id": self.session.session_id,
            "durable_stage": self.session.stage,
            "import_kind": if self.session.mgt_source_hash.is_some() { "mgt" } else { "model_ir" },
            "model_identity": {
                "content_hash": self.session.model_content_hash,
                "semantic_hash": self.session.model_semantic_hash,
                "provenance_hash": self.session.model_provenance_hash,
            },
            "workflow": workflow,
            "terminal_status": self.session.terminal_status,
            "result_summary": result_summary,
            "backend_receipt": backend_receipt,
            "constrained_reactions": constrained_reactions,
            "comparison": comparison,
            "report": report,
            "human_review": review_view,
            "next_action": next_action,
            "claim_boundary": "deterministic_verified_native_operator_view_not_visual_model_editing_or_an_engineering_verdict",
        });
        if let Some(profile) = self.session.analysis_profile {
            view.as_object_mut()
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_view_serialization_failed",
                        "Workbench view projection is not an object",
                    )
                })?
                .insert("analysis_profile".to_owned(), json!(profile));
        }
        canonical_hashed_json(view, "view_hash", "workbench_view_serialization_failed")
    }

    /// Publish one immutable explicit human review bound to the reported native artifacts.
    ///
    /// # Errors
    ///
    /// Requires a reported session, a non-empty bounded reviewer, safe bounded comment text and no
    /// pre-existing review. Review publication is atomic and cannot overwrite prior disposition.
    pub fn publish_review(
        &self,
        decision: WorkbenchReviewDecisionV1,
        reviewer: &str,
        comment: &str,
    ) -> Result<String, WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Reported)?;
        validate_review_text(reviewer, comment)?;
        if self.root.join(REVIEW_DIRECTORY).exists() {
            return Err(WorkbenchError::new(
                "workbench_review_exists",
                "the immutable review already exists; create a new Workbench session to revise it",
            ));
        }
        let session_json = canonical_session(&self.session)?;
        let session_value = decode_json_strict(session_json.as_bytes())
            .map_err(|error| input_error("workbench_review_session_invalid", &error))?;
        let source_session_hash = session_value
            .get("session_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_review_session_invalid",
                    "the canonical Workbench session has no session hash",
                )
            })?;
        let result = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let comparison = read_bounded_regular_file(
            &self
                .root
                .join(COMPARISON_DIRECTORY)
                .join("external-comparison-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let pdf_artifact_hash = Some(sha256_identity(&read_bounded_regular_file(
            &self.root.join(REPORT_DIRECTORY).join("report.pdf"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?));
        let (
            result_recovery_artifact_hash,
            reaction_result_artifact_hash,
            report_document_artifact_hash,
        ) = match self.session.analysis_profile {
            None => (None, None, None),
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => (
                Some(sha256_identity(&read_bounded_regular_file(
                    &self
                        .root
                        .join(RESUME_DIRECTORY)
                        .join("result-recovery-ir.json"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
                read_optional_bounded_regular_file(
                    &self
                        .root
                        .join(RESUME_DIRECTORY)
                        .join("reaction-result-ir.json"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?
                .map(|bytes| sha256_identity(&bytes)),
                Some(sha256_identity(&read_bounded_regular_file(
                    &self.root.join(REPORT_DIRECTORY).join("report.md"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
            ),
        };
        let reaction_bound = reaction_result_artifact_hash.is_some();
        let review = WorkbenchReviewV1 {
            schema_version: REVIEW_SCHEMA_V1.to_owned(),
            session_id: self.session.session_id.clone(),
            source_session_hash: source_session_hash.to_owned(),
            decision,
            reviewer: reviewer.to_owned(),
            comment: comment.to_owned(),
            result_artifact_hash: sha256_identity(&result),
            comparison_artifact_hash: sha256_identity(&comparison),
            pdf_artifact_hash,
            result_recovery_artifact_hash,
            reaction_result_artifact_hash,
            report_document_artifact_hash,
            analysis_profile: self.session.analysis_profile,
            claim_boundary: review_claim_boundary(self.session.analysis_profile, reaction_bound)
                .to_owned(),
            review_hash: String::new(),
        };
        let canonical = canonical_review(&review)?;
        publish_new_directory(
            &self.root.join(REVIEW_DIRECTORY),
            &[(REVIEW_FILE, canonical.as_bytes())],
        )?;
        let verified = read_review(&self.root, &self.session)?;
        canonical_review(&verified)
    }

    /// Return the verified immutable human review.
    ///
    /// # Errors
    ///
    /// Returns `workbench_review_missing` when no review was published and fails closed on drift.
    pub fn review_json(&self) -> Result<String, WorkbenchError> {
        canonical_review(&read_review(&self.root, &self.session)?)
    }

    /// Return a deterministic native handoff manifest for the reported and reviewed session.
    ///
    /// The PDF and JSON artifacts remain separate files; this manifest binds their exact relative
    /// names, lengths and hashes without a browser or archive utility.
    ///
    /// # Errors
    ///
    /// Requires a reported session and a verified explicit human review.
    #[allow(clippy::too_many_lines)]
    pub fn export_json(&self) -> Result<String, WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Reported)?;
        let review = read_review(&self.root, &self.session)?;
        let session = canonical_session(&self.session)?;
        let result = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let comparison = read_bounded_regular_file(
            &self
                .root
                .join(COMPARISON_DIRECTORY)
                .join("external-comparison-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let review_json = canonical_review(&review)?;
        let mut artifacts = vec![
            artifact_entry(
                "workbench_session",
                SESSION_FILE,
                "application/json",
                session.as_bytes(),
            )?,
            artifact_entry(
                "result_ir",
                "04-resume/result-ir.json",
                "application/json",
                &result,
            )?,
        ];
        let mut reaction_included = false;
        if self.session.analysis_profile.is_some() {
            let recovery = read_bounded_regular_file(
                &self
                    .root
                    .join(RESUME_DIRECTORY)
                    .join("result-recovery-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )?;
            artifacts.push(artifact_entry(
                "result_recovery_ir",
                "04-resume/result-recovery-ir.json",
                "application/json",
                &recovery,
            )?);
            if let Some(reaction) = read_optional_bounded_regular_file(
                &self
                    .root
                    .join(RESUME_DIRECTORY)
                    .join("reaction-result-ir.json"),
                MAX_PRODUCT_ARTIFACT_BYTES,
            )? {
                reaction_included = true;
                artifacts.push(artifact_entry(
                    "reaction_result_ir",
                    "04-resume/reaction-result-ir.json",
                    "application/json",
                    &reaction,
                )?);
            }
        }
        artifacts.extend([
            artifact_entry(
                "report_ir",
                "04-resume/report-ir.json",
                "application/json",
                &report,
            )?,
            artifact_entry(
                "external_comparison_ir",
                "05-compare/external-comparison-ir.json",
                "application/json",
                &comparison,
            )?,
        ]);
        match self.session.analysis_profile {
            None => {
                let pdf = read_bounded_regular_file(
                    &self.root.join(REPORT_DIRECTORY).join("report.pdf"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                artifacts.push(artifact_entry(
                    "pdf_report",
                    "06-report/report.pdf",
                    "application/pdf",
                    &pdf,
                )?);
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let pdf = read_bounded_regular_file(
                    &self.root.join(REPORT_DIRECTORY).join("report.pdf"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                let document = read_bounded_regular_file(
                    &self.root.join(REPORT_DIRECTORY).join("report.md"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                artifacts.push(artifact_entry(
                    "sparse_linear_pdf_report",
                    "06-report/report.pdf",
                    "application/pdf",
                    &pdf,
                )?);
                artifacts.push(artifact_entry(
                    "pdf_ready_document_source",
                    "06-report/report.md",
                    "text/markdown; charset=utf-8",
                    &document,
                )?);
            }
        }
        artifacts.push(artifact_entry(
            "human_review",
            "07-review/review.json",
            "application/json",
            review_json.as_bytes(),
        )?);
        let mut export = json!({
            "schema_version": EXPORT_SCHEMA_V1,
            "session_id": self.session.session_id,
            "decision": review.decision,
            "review_hash": review.review_hash,
            "artifacts": artifacts,
            "claim_boundary": if reaction_included {
                "deterministic_model_ir_linear_native_handoff_manifest_with_constrained_reactions_pdf_and_document_source_not_an_archive_signature_or_engineering_acceptance"
            } else if self.session.analysis_profile.is_some() {
                "deterministic_model_ir_linear_legacy_native_handoff_manifest_without_constrained_reactions_with_pdf_and_document_source_not_an_archive_signature_or_engineering_acceptance"
            } else {
                "deterministic_native_handoff_manifest_not_an_archive_signature_or_engineering_acceptance"
            },
        });
        if let Some(profile) = self.session.analysis_profile {
            export
                .as_object_mut()
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_export_serialization_failed",
                        "Workbench export projection is not an object",
                    )
                })?
                .insert("analysis_profile".to_owned(), json!(profile));
        }
        canonical_hashed_json(
            export,
            "export_hash",
            "workbench_export_serialization_failed",
        )
    }

    /// Return a deterministic UTF-8 linear alternative to the verified bounded report.
    ///
    /// English and Korean labels carry the same values and identities. The projection uses no
    /// ANSI styling, color, cursor positioning, graphics, browser, or external renderer. This is
    /// a bounded terminal accessibility aid, not WCAG or PDF/UA conformance.
    ///
    /// # Errors
    ///
    /// Requires a reported session and rejects any `ResultIR`, `ReportIR`, Markdown, PDF, receipt,
    /// or optional review drift before rendering text.
    pub fn linear_report_text(
        &self,
        locale: WorkbenchReportLocaleV1,
    ) -> Result<String, WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Reported)?;
        if self.session.analysis_profile.is_some() {
            return self.model_ir_linear_report_text(locale);
        }
        let terminal = self.root.join(RESUME_DIRECTORY);
        let result_bytes = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report_bytes = read_bounded_regular_file(
            &terminal.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document_bytes =
            read_bounded_regular_file(&terminal.join("report.md"), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let report_directory = self.root.join(REPORT_DIRECTORY);
        let pdf_bytes = read_bounded_regular_file(
            &report_directory.join("report.pdf"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let pdf_receipt_bytes = read_bounded_regular_file(
            &report_directory.join("pdf-receipt.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reproduced = execute_pdf_report(&result_bytes, &report_bytes, &document_bytes)
            .map_err(|error| input_error("workbench_linear_report_binding_invalid", &error))?;
        if reproduced.pdf_bytes() != pdf_bytes
            || reproduced.receipt_json().as_bytes() != pdf_receipt_bytes
        {
            return Err(WorkbenchError::new(
                "workbench_linear_report_binding_mismatch",
                "stored PDF or receipt differs from the exact ResultIR/ReportIR/Markdown projection",
            ));
        }
        let result = parse_nonlinear_ndtha_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_linear_report_result_invalid", &error))?;
        let report = parse_nonlinear_ndtha_report_ir_v1(&report_bytes)
            .map_err(|error| input_error("workbench_linear_report_report_invalid", &error))?;
        let comparison_passed = self.session.comparison_passed.ok_or_else(|| {
            WorkbenchError::new(
                "workbench_linear_report_comparison_missing",
                "reported session has no verified external-comparison disposition",
            )
        })?;
        let comparison_receipt = verified_receipt_json(
            &self
                .root
                .join(COMPARISON_DIRECTORY)
                .join("comparison-receipt.json"),
        )?;
        let comparison_hash = comparison_receipt
            .get("comparison_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_linear_report_comparison_invalid",
                    "verified external-comparison receipt has no comparison hash",
                )
            })?;
        let review = read_optional_review(&self.root, &self.session)?;
        let pdf_hash = sha256_identity(&pdf_bytes);
        report_view::render_linear_report(
            locale,
            &report_view::LinearReportInput {
                result: result.result(),
                report_hash: report.report_hash(),
                document_hash: &report.report().document_source_hash,
                comparison_passed,
                comparison_hash,
                pdf_hash: &pdf_hash,
                review: review
                    .as_ref()
                    .map(|review| report_view::LinearReportReview {
                        decision: review.decision,
                        reviewer: &review.reviewer,
                        comment: &review.comment,
                        review_hash: &review.review_hash,
                    }),
            },
        )
    }

    #[allow(clippy::too_many_lines)]
    fn model_ir_linear_report_text(
        &self,
        locale: WorkbenchReportLocaleV1,
    ) -> Result<String, WorkbenchError> {
        let report_directory = self.root.join(REPORT_DIRECTORY);
        verify_receipt_directory(&report_directory, "report-receipt.json")?;
        let result_bytes = read_bounded_regular_file(
            &report_directory.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let recovery_bytes = read_bounded_regular_file(
            &report_directory.join("result-recovery-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reaction_bytes = read_optional_bounded_regular_file(
            &report_directory.join("reaction-result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report_bytes = read_bounded_regular_file(
            &report_directory.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document_bytes = read_bounded_regular_file(
            &report_directory.join("report.md"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let pdf_bytes = read_bounded_regular_file(
            &report_directory.join("report.pdf"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let pdf_receipt_bytes = read_bounded_regular_file(
            &report_directory.join("pdf-receipt.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reproduced =
            execute_sparse_linear_pdf_report(&result_bytes, &report_bytes, &document_bytes)
                .map_err(|error| input_error("workbench_linear_report_pdf_invalid", &error))?;
        if reproduced.pdf_bytes() != pdf_bytes
            || reproduced.receipt_json().as_bytes() != pdf_receipt_bytes
        {
            return Err(WorkbenchError::new(
                "workbench_linear_report_pdf_mismatch",
                "stored sparse PDF or receipt differs from the exact ResultIR/ReportIR/Markdown projection",
            ));
        }
        let result = parse_sparse_linear_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_linear_report_result_invalid", &error))?;
        let recovery = parse_model_ir_linear_result_recovery_ir_v1(&recovery_bytes)
            .map_err(|error| input_error("workbench_linear_report_recovery_invalid", &error))?;
        verify_model_ir_linear_result_recovery_v1(&result, &recovery)
            .map_err(|error| input_error("workbench_linear_report_recovery_invalid", &error))?;
        let reaction = reaction_bytes
            .as_deref()
            .map(parse_model_ir_linear_reaction_result_ir_v1)
            .transpose()
            .map_err(|error| input_error("workbench_linear_report_reaction_invalid", &error))?;
        if let Some(reaction) = reaction.as_ref() {
            verify_model_ir_linear_reaction_result_v1(&result, &recovery, reaction)
                .map_err(|error| input_error("workbench_linear_report_reaction_invalid", &error))?;
        }
        let report = parse_sparse_linear_report_ir_v1(&report_bytes)
            .map_err(|error| input_error("workbench_linear_report_report_invalid", &error))?;
        let expected = build_sparse_linear_report_v1(&result)
            .map_err(|error| input_error("workbench_linear_report_projection_failed", &error))?;
        if report.canonical_json() != expected.report_ir.canonical_json()
            || document_bytes != expected.document_source.as_bytes()
        {
            return Err(WorkbenchError::new(
                "workbench_linear_report_binding_mismatch",
                "stored linear recovery, reactions, ReportIR, or document differs from the exact ResultIR projection",
            ));
        }
        let comparison = verified_receipt_json(
            &self
                .root
                .join(COMPARISON_DIRECTORY)
                .join("comparison-receipt.json"),
        )?;
        let comparison_status = comparison
            .get("status")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_linear_report_comparison_invalid",
                    "verified comparison receipt has no status",
                )
            })?;
        let comparison_hash = comparison
            .get("comparison_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_linear_report_comparison_invalid",
                    "verified comparison receipt has no comparison hash",
                )
            })?;
        let (title, case_label, status_label, comparison_label, source_label, boundary) =
            match locale {
                WorkbenchReportLocaleV1::EnUs => (
                    "Structural ModelIR Linear Workbench Report",
                    "Case",
                    "Terminal status",
                    "External comparison",
                    "Verified PDF document source",
                    "This is a bounded CPU candidate view, not engineering acceptance, PDF/A, accessibility conformance, or design-code compliance.",
                ),
                WorkbenchReportLocaleV1::KoKr => (
                    "구조 ModelIR 선형 Workbench 보고서",
                    "케이스",
                    "종료 상태",
                    "외부 비교",
                    "검증된 PDF 문서 원본",
                    "이 결과는 제한된 CPU 후보 뷰이며, 공학적 승인·PDF/A·접근성 적합성·설계기준 적합성을 의미하지 않습니다.",
                ),
            };
        let source = std::str::from_utf8(&document_bytes).map_err(|_| {
            WorkbenchError::new(
                "workbench_linear_report_document_invalid",
                "verified report document source is not UTF-8",
            )
        })?;
        let reaction_lines = reaction.as_ref().map_or_else(
            || match locale {
                WorkbenchReportLocaleV1::EnUs => {
                    "Constrained reactions: unavailable in legacy artifact set\n".to_owned()
                }
                WorkbenchReportLocaleV1::KoKr => "구속 반력: 기존 산출물 세트에 없음\n".to_owned(),
            },
            |reaction| {
                let label = match locale {
                    WorkbenchReportLocaleV1::EnUs => "Maximum absolute constrained reaction",
                    WorkbenchReportLocaleV1::KoKr => "최대 절대 구속 반력",
                };
                format!(
                    "{label}: {:.17e}\nReaction hash: {}\n",
                    reaction
                        .result()
                        .summary
                        .maximum_absolute_reaction_component,
                    reaction.result_hash(),
                )
            },
        );
        let mut output = format!(
            "{title}\nSchema: structural-native-workbench-model-ir-linear-report-view.v1\nLocale: {}\n{case_label}: {}\n{status_label}: completed\n{comparison_label}: {comparison_status}\nMatrix order: {}\nPCG iterations: {}\nMaximum absolute global displacement: {:.17e}\nActive residual infinity norm: {:.17e}\nResult hash: {}\nRecovery hash: {}\n{reaction_lines}Report hash: {}\nPDF hash: {}\nComparison hash: {comparison_hash}\nBoundary: {boundary}\n\n{source_label}\n\n",
            locale.label(),
            result.result().case_id,
            result.result().summary.order,
            result.result().summary.iterations,
            recovery.recovery().summary.maximum_absolute_displacement,
            recovery.recovery().summary.active_residual_inf,
            result.result_hash(),
            recovery.recovery_hash(),
            report.report_hash(),
            sha256_identity(&pdf_bytes),
        );
        output.push_str(source);
        Ok(output)
    }

    /// Return a deterministic bounded window over verified `ModelIR` linear constrained reactions.
    ///
    /// The view maps each global constrained DOF back to the immutable `ModelIR` node identifier,
    /// preserves the internal-force, external-load, and reaction values, and exposes all source
    /// identities without mutating or re-executing the analysis.
    ///
    /// # Errors
    ///
    /// Requires a `ModelIR` linear session at terminal or later and rejects missing legacy reaction
    /// evidence, receipt drift, source-binding drift, invalid node mapping, or an unsafe window.
    pub fn model_ir_linear_reaction_view_text(
        &self,
        start_row: u32,
        count: u32,
    ) -> Result<String, WorkbenchError> {
        self.model_ir_linear_reaction_view_text_localized(
            WorkbenchReportLocaleV1::EnUs,
            start_row,
            count,
        )
    }

    /// Return a localized deterministic bounded window over constrained reactions.
    ///
    /// Locale changes labels only. Exact FP64 values, node/DOF mappings, units, execution receipt,
    /// and provenance identities remain visible in both supported languages.
    ///
    /// # Errors
    ///
    /// Requires a `ModelIR` linear session at terminal or later and rejects missing legacy reaction
    /// evidence, receipt drift, source-binding drift, invalid node mapping, or an unsafe window.
    pub fn model_ir_linear_reaction_view_text_localized(
        &self,
        locale: WorkbenchReportLocaleV1,
        start_row: u32,
        count: u32,
    ) -> Result<String, WorkbenchError> {
        if self.session.analysis_profile != Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) {
            return Err(WorkbenchError::new(
                "workbench_profile_unsupported",
                "constrained reaction view is available only for the ModelIR linear CPU profile",
            ));
        }
        if self.session.stage < WorkbenchStageV1::Terminal {
            return Err(WorkbenchError::new(
                "workbench_transition_invalid",
                format!(
                    "terminal or later is required but the durable stage is {}",
                    self.session.stage.label()
                ),
            ));
        }
        let terminal = self.root.join(RESUME_DIRECTORY);
        verify_receipt_directory(&terminal, "run-receipt.json")?;
        let result_bytes = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let recovery_bytes = read_bounded_regular_file(
            &terminal.join("result-recovery-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reaction_bytes = read_optional_bounded_regular_file(
            &terminal.join("reaction-result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_reaction_view_missing",
                "frozen pre-reaction ModelIR linear workspace has no constrained reaction ResultIR",
            )
        })?;
        let result = parse_sparse_linear_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_reaction_view_result_invalid", &error))?;
        let recovery = parse_model_ir_linear_result_recovery_ir_v1(&recovery_bytes)
            .map_err(|error| input_error("workbench_reaction_view_recovery_invalid", &error))?;
        verify_model_ir_linear_result_recovery_v1(&result, &recovery)
            .map_err(|error| input_error("workbench_reaction_view_recovery_invalid", &error))?;
        let reaction = parse_model_ir_linear_reaction_result_ir_v1(&reaction_bytes)
            .map_err(|error| input_error("workbench_reaction_view_reaction_invalid", &error))?;
        verify_model_ir_linear_reaction_result_v1(&result, &recovery, &reaction)
            .map_err(|error| input_error("workbench_reaction_view_reaction_invalid", &error))?;
        let model_bytes = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let model = parse_model_ir_v2(&model_bytes)
            .map_err(|error| input_error("workbench_reaction_view_model_invalid", &error))?;
        reaction_view::render_model_ir_linear_reaction_view(
            &model,
            reaction.result(),
            locale,
            start_row,
            count,
        )
    }

    /// Return a deterministic bounded window over one verified terminal NDTHA response channel.
    ///
    /// The view uses only the completed `ResultIR` prefix, preserves exact numeric values in a
    /// table, and uses a fixed-width ASCII plot whose extent is stable across windows. It does not
    /// infer timestamps because `ResultIR` v1 does not carry the analysis time increment.
    ///
    /// # Errors
    ///
    /// Requires at least the terminal stage and rejects receipt drift, invalid `ResultIR`, an
    /// unsupported channel window, or an unsafe terminal projection.
    pub fn ndtha_response_view_text(
        &self,
        channel: WorkbenchResultChannelV1,
        start_step: u32,
        count: u32,
    ) -> Result<String, WorkbenchError> {
        self.ndtha_response_view_text_localized(
            WorkbenchReportLocaleV1::EnUs,
            channel,
            start_step,
            count,
        )
    }

    /// Return a localized deterministic bounded window over one verified terminal response.
    ///
    /// The locale changes presentation only; the same verified `ResultIR` values and identities
    /// remain visible in both supported languages.
    ///
    /// # Errors
    ///
    /// Requires at least the terminal stage and rejects receipt drift, invalid `ResultIR`, an
    /// unsupported channel window, or an unsafe terminal projection.
    pub fn ndtha_response_view_text_localized(
        &self,
        locale: WorkbenchReportLocaleV1,
        channel: WorkbenchResultChannelV1,
        start_step: u32,
        count: u32,
    ) -> Result<String, WorkbenchError> {
        self.require_ndtha_profile("NDTHA response view")?;
        if self.session.stage < WorkbenchStageV1::Terminal {
            return Err(WorkbenchError::new(
                "workbench_transition_invalid",
                format!(
                    "terminal or later is required but the durable stage is {}",
                    self.session.stage.label()
                ),
            ));
        }
        let result_bytes = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let result = parse_nonlinear_ndtha_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_result_view_result_invalid", &error))?;
        result_view::render_ndtha_response_view(result.result(), locale, channel, start_step, count)
    }

    /// Return a deterministic original/deformed overlay for the executed fixed-guided profile.
    ///
    /// The view revalidates the immutable `ModelIR` through C++, consumes the adapter selectors
    /// from the immutable request, and applies only one selected `ResultIR` top displacement in
    /// global X.
    /// The scale changes presentation only and never mutates or re-executes the analysis.
    ///
    /// # Errors
    ///
    /// Requires at least the terminal stage and rejects receipt drift, profile/identity mismatch,
    /// an incomplete result prefix, an out-of-range step, or an unsafe visual magnification.
    pub fn fixed_guided_deformed_shape_view_text(
        &self,
        projection: ModelTopologyProjectionV1,
        step: Option<u32>,
        scale: f64,
    ) -> Result<String, WorkbenchError> {
        self.fixed_guided_deformed_shape_view_text_localized(
            WorkbenchReportLocaleV1::EnUs,
            projection,
            step,
            scale,
        )
    }

    /// Return a localized original/deformed overlay for the executed fixed-guided profile.
    ///
    /// The locale changes only labels and operator guidance; coordinates, selectors, exact
    /// provenance identities, and the selected displacement remain unchanged.
    ///
    /// # Errors
    ///
    /// Requires at least the terminal stage and rejects receipt drift, profile/identity mismatch,
    /// an incomplete result prefix, an out-of-range step, or an unsafe visual magnification.
    pub fn fixed_guided_deformed_shape_view_text_localized(
        &self,
        locale: WorkbenchReportLocaleV1,
        projection: ModelTopologyProjectionV1,
        step: Option<u32>,
        scale: f64,
    ) -> Result<String, WorkbenchError> {
        self.require_ndtha_profile("fixed-guided deformed view")?;
        if self.session.stage < WorkbenchStageV1::Terminal {
            return Err(WorkbenchError::new(
                "workbench_transition_invalid",
                format!(
                    "terminal or later is required but the durable stage is {}",
                    self.session.stage.label()
                ),
            ));
        }
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let request_bytes =
            self.read_import_artifact("model-analysis-request.json", MAX_REQUEST_BYTES)?;
        let request = parse_model_ir_ndtha_analysis_request_v1(&request_bytes)
            .map_err(|error| input_error("workbench_deformed_view_request_invalid", &error))?;
        let result_bytes = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let result = parse_nonlinear_ndtha_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_deformed_view_result_invalid", &error))?;
        deformed_view::render_fixed_guided_deformed_view(
            &model,
            &request,
            result.result(),
            locale,
            projection,
            step,
            scale,
        )
    }

    /// Publish a deterministic embedded-font English or Korean PDF from a verified report session.
    ///
    /// The durable profile-specific v1 PDF remains byte-identical and authoritative inside the
    /// workspace. This method first reproduces that stored PDF and receipt from the exact report
    /// artifacts, then publishes a separate create-new localized output directory. It uses no host
    /// font, Python, Node, browser, subprocess, or external renderer.
    ///
    /// # Errors
    ///
    /// Requires a reported session and rejects stored report drift, unsupported text, embedded
    /// font identity drift, or destination publication failure.
    pub fn export_localized_pdf(
        &self,
        locale: WorkbenchReportLocaleV1,
        output_directory: &Path,
    ) -> Result<String, WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Reported)?;
        if self.session.analysis_profile.is_some() {
            return self.export_model_ir_linear_localized_pdf(locale, output_directory);
        }
        let terminal = self.root.join(RESUME_DIRECTORY);
        let result = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report = read_bounded_regular_file(
            &terminal.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document =
            read_bounded_regular_file(&terminal.join("report.md"), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let stored_report = self.root.join(REPORT_DIRECTORY);
        let stored_pdf = read_bounded_regular_file(
            &stored_report.join("report.pdf"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let stored_receipt = read_bounded_regular_file(
            &stored_report.join("pdf-receipt.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reproduced = execute_pdf_report(&result, &report, &document)
            .map_err(|error| input_error("workbench_localized_pdf_binding_invalid", &error))?;
        if reproduced.pdf_bytes() != stored_pdf
            || reproduced.receipt_json().as_bytes() != stored_receipt
        {
            return Err(WorkbenchError::new(
                "workbench_localized_pdf_binding_mismatch",
                "stored PDF or receipt differs from the exact ResultIR/ReportIR/Markdown projection",
            ));
        }
        let locale = match locale {
            WorkbenchReportLocaleV1::EnUs => PdfReportLocaleV2::EnUs,
            WorkbenchReportLocaleV1::KoKr => PdfReportLocaleV2::KoKr,
        };
        let outcome = execute_localized_pdf_report(&result, &report, &document, locale)
            .map_err(|error| input_error("workbench_localized_pdf_render_failed", &error))?;
        publish_localized_pdf_report(output_directory, &outcome)
            .map_err(|error| input_error("workbench_localized_pdf_publish_failed", &error))?;
        Ok(outcome.receipt_json().to_owned())
    }

    fn export_model_ir_linear_localized_pdf(
        &self,
        locale: WorkbenchReportLocaleV1,
        output_directory: &Path,
    ) -> Result<String, WorkbenchError> {
        let report_directory = self.root.join(REPORT_DIRECTORY);
        verify_receipt_directory(&report_directory, "report-receipt.json")?;
        let result = read_bounded_regular_file(
            &report_directory.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report = read_bounded_regular_file(
            &report_directory.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document = read_bounded_regular_file(
            &report_directory.join("report.md"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let stored_pdf = read_bounded_regular_file(
            &report_directory.join("report.pdf"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let stored_receipt = read_bounded_regular_file(
            &report_directory.join("pdf-receipt.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reproduced = execute_sparse_linear_pdf_report(&result, &report, &document)
            .map_err(|error| input_error("workbench_localized_pdf_binding_invalid", &error))?;
        if reproduced.pdf_bytes() != stored_pdf
            || reproduced.receipt_json().as_bytes() != stored_receipt
        {
            return Err(WorkbenchError::new(
                "workbench_localized_pdf_binding_mismatch",
                "stored sparse PDF or receipt differs from the exact ResultIR/ReportIR/Markdown projection",
            ));
        }
        let locale = match locale {
            WorkbenchReportLocaleV1::EnUs => PdfReportLocaleV2::EnUs,
            WorkbenchReportLocaleV1::KoKr => PdfReportLocaleV2::KoKr,
        };
        let outcome =
            execute_sparse_linear_localized_pdf_report(&result, &report, &document, locale)
                .map_err(|error| input_error("workbench_localized_pdf_render_failed", &error))?;
        publish_localized_pdf_report(output_directory, &outcome)
            .map_err(|error| input_error("workbench_localized_pdf_publish_failed", &error))?;
        Ok(outcome.receipt_json().to_owned())
    }

    /// Cross the C ABI into C++ semantic validation and publish the exact snapshot/report.
    ///
    /// # Errors
    ///
    /// Fails closed unless the current stage is `imported` and the model is analysis-ready.
    pub fn validate(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Imported)?;
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let validation = validate_model_bytes(&model)
            .map_err(|error| input_error("workbench_native_validation_failed", &error))?;
        if !validation.report.contract_valid || !validation.report.analysis_ready {
            return Err(WorkbenchError::new(
                "workbench_model_not_analysis_ready",
                "native C++ validation did not accept the imported model as analysis-ready",
            ));
        }
        let snapshot = validation.snapshot.canonical_bytes();
        let receipt = canonical_self_hashed(json!({
            "schema_version": VALIDATION_RECEIPT_SCHEMA_V1,
            "session_id": self.session.session_id,
            "status": "validated",
            "model_identity": {
                "content_hash": validation.report.content_hash,
                "semantic_hash": validation.report.semantic_hash,
                "provenance_hash": validation.report.provenance_hash,
            },
            "artifacts": [
                artifact_entry("cpp_validation_report", "native-validation.json", "application/json", validation.report_json.as_bytes())?,
                artifact_entry("cpp_canonical_snapshot", "native-snapshot.json", "application/json", snapshot)?,
            ],
            "claim_boundary": "one_strict_model_ir_rust_to_c_abi_to_cpp_snapshot_validation",
        }))?;
        publish_new_directory(
            &self.root.join(VALIDATION_DIRECTORY),
            &[
                ("native-validation.json", validation.report_json.as_bytes()),
                ("native-snapshot.json", snapshot),
                ("validation-receipt.json", receipt.as_bytes()),
            ],
        )?;
        self.session.stage = WorkbenchStageV1::Validated;
        self.persist()
    }

    /// Advance a fresh native analysis to a real nonterminal checkpoint.
    ///
    /// # Errors
    ///
    /// Rejects zero budget, invalid order, terminal-at-first-advance and product/runtime failures.
    pub fn run(&mut self, step_budget: u32) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Validated)?;
        if step_budget == 0 {
            return Err(WorkbenchError::new(
                "workbench_run_budget_invalid",
                "Run requires a positive bounded step budget so Resume remains a real transition",
            ));
        }
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let request =
            self.read_import_artifact("model-analysis-request.json", MAX_REQUEST_BYTES)?;
        match self.session.analysis_profile {
            None => {
                let outcome = execute_model_ir_native_analysis(&model, &request, None, step_budget)
                    .map_err(|error| input_error("workbench_run_failed", &error))?;
                if outcome.is_terminal() {
                    return Err(WorkbenchError::new(
                        "workbench_run_did_not_checkpoint",
                        "the bounded Run budget reached a terminal state; choose a smaller budget",
                    ));
                }
                publish_model_ir_native_analysis(&self.root.join(RUN_DIRECTORY), &outcome)
                    .map_err(|error| input_error("workbench_run_publish_failed", &error))?;
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let outcome = execute_model_ir_linear_analysis(&model, &request, None, step_budget)
                    .map_err(|error| input_error("workbench_run_failed", &error))?;
                if outcome.is_complete() || outcome.is_terminal_failure() {
                    return Err(WorkbenchError::new(
                        "workbench_run_did_not_checkpoint",
                        "the bounded Run iteration budget reached a terminal state; choose a smaller budget",
                    ));
                }
                publish_model_ir_linear_analysis(&self.root.join(RUN_DIRECTORY), &outcome)
                    .map_err(|error| input_error("workbench_run_publish_failed", &error))?;
            }
        }
        self.session.stage = WorkbenchStageV1::Checkpointed;
        self.persist()
    }

    /// Resume the exact Workbench checkpoint to a terminal product result.
    ///
    /// A zero budget means the existing native unbounded-to-terminal policy.
    ///
    /// # Errors
    ///
    /// Rejects invalid order, corrupt/binding-mismatched checkpoints and nonterminal outcomes.
    pub fn resume(&mut self, step_budget: u32) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Checkpointed)?;
        let model = self.read_import_artifact("model-ir.json", MAX_MODEL_BYTES)?;
        let request =
            self.read_import_artifact("model-analysis-request.json", MAX_REQUEST_BYTES)?;
        let effective_budget = if step_budget == 0 {
            u32::MAX
        } else {
            step_budget
        };
        let terminal_status = match self.session.analysis_profile {
            None => {
                let checkpoint = read_bounded_regular_file(
                    &self.root.join(RUN_DIRECTORY).join("checkpoint.ndcp"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                let outcome = execute_model_ir_native_analysis(
                    &model,
                    &request,
                    Some(&checkpoint),
                    effective_budget,
                )
                .map_err(|error| input_error("workbench_resume_failed", &error))?;
                if !outcome.is_terminal() {
                    return Err(WorkbenchError::new(
                        "workbench_resume_not_terminal",
                        "Resume exhausted its budget before reaching a terminal state",
                    ));
                }
                let status = receipt_status(outcome.run_receipt_json(), None)?;
                publish_model_ir_native_analysis(&self.root.join(RESUME_DIRECTORY), &outcome)
                    .map_err(|error| input_error("workbench_resume_publish_failed", &error))?;
                status
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let checkpoint = read_bounded_regular_file(
                    &self.root.join(RUN_DIRECTORY).join("checkpoint.mlpcp"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                let outcome = execute_model_ir_linear_analysis(
                    &model,
                    &request,
                    Some(&checkpoint),
                    effective_budget,
                )
                .map_err(|error| input_error("workbench_resume_failed", &error))?;
                if !outcome.is_complete() {
                    return Err(WorkbenchError::new(
                        "workbench_resume_not_terminal",
                        "Resume did not produce a converged ModelIR linear result",
                    ));
                }
                let status = receipt_status(
                    outcome.run_receipt_json(),
                    Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1),
                )?;
                publish_model_ir_linear_analysis(&self.root.join(RESUME_DIRECTORY), &outcome)
                    .map_err(|error| input_error("workbench_resume_publish_failed", &error))?;
                status
            }
        };
        self.session.stage = WorkbenchStageV1::Terminal;
        self.session.terminal_status = Some(terminal_status);
        self.persist()
    }

    /// Compare terminal `ResultIR` against a hash-bound external result and source artifact.
    ///
    /// # Errors
    ///
    /// Rejects invalid order/contracts. With `require_pass`, divergence remains published and
    /// durable but is returned as a policy failure.
    pub fn compare(&mut self, require_pass: bool) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Terminal)?;
        let result = read_bounded_regular_file(
            &self.root.join(RESUME_DIRECTORY).join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let external =
            self.read_import_artifact("external-result.json", MAX_EXTERNAL_RESULT_BYTES)?;
        let source =
            self.read_import_artifact("external-source.artifact", MAX_EXTERNAL_ARTIFACT_BYTES)?;
        let executable_path = self
            .root
            .join(IMPORT_DIRECTORY)
            .join("external-executable.artifact");
        let executable = if self.session.executable_artifact_hash.is_some() {
            Some(read_bounded_regular_file(
                &executable_path,
                MAX_EXTERNAL_ARTIFACT_BYTES,
            )?)
        } else {
            None
        };
        let passed = match self.session.analysis_profile {
            None => {
                let outcome =
                    execute_external_comparison(&result, &external, &source, executable.as_deref())
                        .map_err(|error| input_error("workbench_comparison_failed", &error))?;
                let passed = outcome.passed();
                publish_external_comparison(&self.root.join(COMPARISON_DIRECTORY), &outcome)
                    .map_err(|error| input_error("workbench_comparison_publish_failed", &error))?;
                passed
            }
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                let recovery = read_bounded_regular_file(
                    &self
                        .root
                        .join(RESUME_DIRECTORY)
                        .join("result-recovery-ir.json"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?;
                let outcome = execute_model_ir_linear_external_comparison(
                    &result,
                    &recovery,
                    &external,
                    &source,
                    executable.as_deref(),
                )
                .map_err(|error| input_error("workbench_comparison_failed", &error))?;
                let passed = outcome.passed();
                publish_model_ir_linear_external_comparison(
                    &self.root.join(COMPARISON_DIRECTORY),
                    &outcome,
                )
                .map_err(|error| input_error("workbench_comparison_publish_failed", &error))?;
                passed
            }
        };
        self.session.stage = WorkbenchStageV1::Compared;
        self.session.comparison_passed = Some(passed);
        self.persist()?;
        if require_pass && !passed {
            return Err(WorkbenchError::new(
                "workbench_comparison_diverged",
                "external comparison evidence was published but exceeded tolerance",
            ));
        }
        Ok(())
    }

    /// Render and publish a deterministic native PDF from the exact terminal artifacts.
    ///
    /// # Errors
    ///
    /// Rejects invalid order, forged projections and native PDF publication failure.
    pub fn report(&mut self) -> Result<(), WorkbenchError> {
        self.require_stage(WorkbenchStageV1::Compared)?;
        if self.session.analysis_profile.is_some() {
            return self.publish_model_ir_linear_pdf_report();
        }
        let terminal = self.root.join(RESUME_DIRECTORY);
        let result = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report = read_bounded_regular_file(
            &terminal.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document =
            read_bounded_regular_file(&terminal.join("report.md"), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let outcome = execute_pdf_report(&result, &report, &document)
            .map_err(|error| input_error("workbench_report_failed", &error))?;
        publish_pdf_report(&self.root.join(REPORT_DIRECTORY), &outcome)
            .map_err(|error| input_error("workbench_report_publish_failed", &error))?;
        self.session.stage = WorkbenchStageV1::Reported;
        self.persist()
    }

    #[allow(clippy::too_many_lines)]
    fn publish_model_ir_linear_pdf_report(&mut self) -> Result<(), WorkbenchError> {
        let terminal = self.root.join(RESUME_DIRECTORY);
        let result_bytes = read_bounded_regular_file(
            &terminal.join("result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let recovery_bytes = read_bounded_regular_file(
            &terminal.join("result-recovery-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let reaction_bytes = read_optional_bounded_regular_file(
            &terminal.join("reaction-result-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let report_bytes = read_bounded_regular_file(
            &terminal.join("report-ir.json"),
            MAX_PRODUCT_ARTIFACT_BYTES,
        )?;
        let document_bytes =
            read_bounded_regular_file(&terminal.join("report.md"), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let result = parse_sparse_linear_result_ir_v1(&result_bytes)
            .map_err(|error| input_error("workbench_report_result_invalid", &error))?;
        let recovery = parse_model_ir_linear_result_recovery_ir_v1(&recovery_bytes)
            .map_err(|error| input_error("workbench_report_recovery_invalid", &error))?;
        verify_model_ir_linear_result_recovery_v1(&result, &recovery)
            .map_err(|error| input_error("workbench_report_recovery_invalid", &error))?;
        let reaction = reaction_bytes
            .as_deref()
            .map(parse_model_ir_linear_reaction_result_ir_v1)
            .transpose()
            .map_err(|error| input_error("workbench_report_reaction_invalid", &error))?;
        if let Some(reaction) = reaction.as_ref() {
            verify_model_ir_linear_reaction_result_v1(&result, &recovery, reaction)
                .map_err(|error| input_error("workbench_report_reaction_invalid", &error))?;
        }
        let report = parse_sparse_linear_report_ir_v1(&report_bytes)
            .map_err(|error| input_error("workbench_report_ir_invalid", &error))?;
        let expected = build_sparse_linear_report_v1(&result)
            .map_err(|error| input_error("workbench_report_projection_failed", &error))?;
        if report.report().source_result_hash != result.result_hash()
            || report.canonical_json() != expected.report_ir.canonical_json()
            || document_bytes != expected.document_source.as_bytes()
        {
            return Err(WorkbenchError::new(
                "workbench_report_projection_mismatch",
                "terminal recovery, reactions, ReportIR, or document source is not the exact sparse ResultIR projection",
            ));
        }
        let pdf = execute_sparse_linear_pdf_report(&result_bytes, &report_bytes, &document_bytes)
            .map_err(|error| input_error("workbench_report_pdf_failed", &error))?;
        let mut artifacts = vec![
            artifact_entry(
                "result_ir",
                "result-ir.json",
                "application/json",
                &result_bytes,
            )?,
            artifact_entry(
                "result_recovery_ir",
                "result-recovery-ir.json",
                "application/json",
                &recovery_bytes,
            )?,
            artifact_entry(
                "report_ir",
                "report-ir.json",
                "application/json",
                &report_bytes,
            )?,
            artifact_entry(
                "pdf_ready_document_source",
                "report.md",
                "text/markdown; charset=utf-8",
                &document_bytes,
            )?,
            artifact_entry(
                "sparse_linear_pdf_report",
                "report.pdf",
                "application/pdf",
                pdf.pdf_bytes(),
            )?,
            artifact_entry(
                "sparse_linear_pdf_receipt",
                "pdf-receipt.json",
                "application/json",
                pdf.receipt_json().as_bytes(),
            )?,
        ];
        if let Some(bytes) = reaction_bytes.as_deref() {
            artifacts.insert(
                2,
                artifact_entry(
                    "reaction_result_ir",
                    "reaction-result-ir.json",
                    "application/json",
                    bytes,
                )?,
            );
        }
        let mut receipt_value = json!({
            "schema_version": "structural-native-model-ir-linear-pdf-report-receipt.v1",
            "session_id": self.session.session_id,
            "status": "reported",
            "source_result_hash": result.result_hash(),
            "source_recovery_hash": recovery.recovery_hash(),
            "source_report_hash": report.report_hash(),
            "document_source_hash": sha256_identity(&document_bytes),
            "pdf_hash": sha256_identity(pdf.pdf_bytes()),
            "pdf_receipt_hash": sha256_identity(pdf.receipt_json().as_bytes()),
            "artifacts": artifacts,
            "claim_boundary": if reaction.is_some() {
                "verified_deterministic_sparse_report_ir_constrained_reactions_markdown_and_single_page_pdf_not_pdf_a_accessibility_engineering_acceptance_or_design_code_compliance"
            } else {
                "legacy_verified_deterministic_sparse_report_ir_without_constrained_reactions_markdown_and_single_page_pdf_not_pdf_a_accessibility_engineering_acceptance_or_design_code_compliance"
            },
        });
        if let Some(reaction) = reaction.as_ref() {
            receipt_value
                .as_object_mut()
                .expect("report receipt is an object")
                .insert(
                    "source_reaction_hash".to_owned(),
                    json!(reaction.result_hash()),
                );
        }
        let receipt = canonical_self_hashed(receipt_value)?;
        let mut published_artifacts = vec![
            ("result-ir.json", result_bytes.as_slice()),
            ("result-recovery-ir.json", recovery_bytes.as_slice()),
            ("report-ir.json", report_bytes.as_slice()),
            ("report.md", document_bytes.as_slice()),
            ("report.pdf", pdf.pdf_bytes()),
            ("pdf-receipt.json", pdf.receipt_json().as_bytes()),
            ("report-receipt.json", receipt.as_bytes()),
        ];
        if let Some(bytes) = reaction_bytes.as_deref() {
            published_artifacts.insert(2, ("reaction-result-ir.json", bytes));
        }
        publish_new_directory(&self.root.join(REPORT_DIRECTORY), &published_artifacts)?;
        self.session.stage = WorkbenchStageV1::Reported;
        self.persist()
    }

    fn require_stage(&self, expected: WorkbenchStageV1) -> Result<(), WorkbenchError> {
        if self.session.stage == expected {
            Ok(())
        } else {
            Err(WorkbenchError::new(
                "workbench_transition_invalid",
                format!(
                    "{} is required but the durable stage is {}",
                    expected.label(),
                    self.session.stage.label()
                ),
            ))
        }
    }

    fn require_ndtha_profile(&self, operation: &str) -> Result<(), WorkbenchError> {
        if self.session.analysis_profile.is_none() {
            Ok(())
        } else {
            Err(WorkbenchError::new(
                "workbench_profile_unsupported",
                format!("{operation} is available only for the fixed-guided NDTHA profile"),
            ))
        }
    }

    fn read_import_artifact(
        &self,
        file: &str,
        maximum_bytes: u64,
    ) -> Result<Vec<u8>, WorkbenchError> {
        read_bounded_regular_file(&self.root.join(IMPORT_DIRECTORY).join(file), maximum_bytes)
    }

    fn persist(&mut self) -> Result<(), WorkbenchError> {
        let canonical = canonical_session(&self.session)?;
        self.session = parse_session(canonical.as_bytes())?;
        write_atomic_file(&self.root.join(SESSION_FILE), canonical.as_bytes())
    }
}

#[derive(Debug)]
struct DiscoveredState {
    stage: WorkbenchStageV1,
    terminal_status: Option<String>,
    comparison_passed: Option<bool>,
}

fn validate_review_text(reviewer: &str, comment: &str) -> Result<(), WorkbenchError> {
    if reviewer.is_empty()
        || reviewer.trim() != reviewer
        || reviewer.chars().count() > 256
        || reviewer.chars().any(char::is_control)
    {
        return Err(WorkbenchError::new(
            "workbench_reviewer_invalid",
            "reviewer must be 1..256 trimmed non-control Unicode characters",
        ));
    }
    if comment.chars().count() > 20_000
        || comment
            .chars()
            .any(|character| character.is_control() && character != '\n' && character != '\t')
    {
        return Err(WorkbenchError::new(
            "workbench_review_comment_invalid",
            "review comment exceeds 20000 characters or contains unsupported controls",
        ));
    }
    Ok(())
}

fn canonical_review(review: &WorkbenchReviewV1) -> Result<String, WorkbenchError> {
    let value = serde_json::to_value(review).map_err(|_| {
        WorkbenchError::new(
            "workbench_review_serialization_failed",
            "review could not be projected to JSON",
        )
    })?;
    canonical_hashed_json(
        value,
        "review_hash",
        "workbench_review_serialization_failed",
    )
}

fn read_optional_review(
    root: &Path,
    session: &WorkbenchSessionV1,
) -> Result<Option<WorkbenchReviewV1>, WorkbenchError> {
    let directory = root.join(REVIEW_DIRECTORY);
    match fs::symlink_metadata(&directory) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(io_error("read Workbench review metadata", &error)),
    }
    verify_directory(&directory, "workbench_review_directory_invalid")?;
    let mut entries = fs::read_dir(&directory)
        .map_err(|error| io_error("read Workbench review directory", &error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| io_error("read Workbench review entry", &error))?;
    entries.sort_by_key(fs::DirEntry::file_name);
    if entries.len() != 1 || entries[0].file_name() != OsStr::new(REVIEW_FILE) {
        return Err(WorkbenchError::new(
            "workbench_review_inventory_invalid",
            "review directory must contain exactly review.json",
        ));
    }
    let bytes = read_bounded_regular_file(&directory.join(REVIEW_FILE), MAX_REQUEST_BYTES)?;
    let value = verify_self_hashed_json(&bytes, "review_hash")?;
    let review: WorkbenchReviewV1 = serde_json::from_value(value).map_err(|_| {
        WorkbenchError::new(
            "workbench_review_decode_failed",
            "review fields are missing, mistyped or unknown",
        )
    })?;
    verify_review_binding(root, session, &review)?;
    Ok(Some(review))
}

fn read_review(
    root: &Path,
    session: &WorkbenchSessionV1,
) -> Result<WorkbenchReviewV1, WorkbenchError> {
    read_optional_review(root, session)?.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_review_missing",
            "an explicit human review has not been published",
        )
    })
}

fn verify_optional_review(root: &Path, session: &WorkbenchSessionV1) -> Result<(), WorkbenchError> {
    read_optional_review(root, session).map(|_| ())
}

fn verify_review_binding(
    root: &Path,
    session: &WorkbenchSessionV1,
    review: &WorkbenchReviewV1,
) -> Result<(), WorkbenchError> {
    if session.stage != WorkbenchStageV1::Reported
        || review.schema_version != REVIEW_SCHEMA_V1
        || review.session_id != session.session_id
        || review.analysis_profile != session.analysis_profile
    {
        return Err(WorkbenchError::new(
            "workbench_review_contract_invalid",
            "review schema, session, stage or claim boundary does not match",
        ));
    }
    validate_review_text(&review.reviewer, &review.comment)?;
    let session_json = canonical_session(session)?;
    let session_value = decode_json_strict(session_json.as_bytes())
        .map_err(|error| input_error("workbench_review_session_invalid", &error))?;
    let expected_session_hash = session_value
        .get("session_hash")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_review_session_invalid",
                "canonical Workbench session has no session hash",
            )
        })?;
    let result = read_bounded_regular_file(
        &root.join(RESUME_DIRECTORY).join("result-ir.json"),
        MAX_PRODUCT_ARTIFACT_BYTES,
    )?;
    let comparison = read_bounded_regular_file(
        &root
            .join(COMPARISON_DIRECTORY)
            .join("external-comparison-ir.json"),
        MAX_PRODUCT_ARTIFACT_BYTES,
    )?;
    let (expected_pdf, expected_recovery, expected_reaction, expected_document) =
        match session.analysis_profile {
            None => (
                Some(sha256_identity(&read_bounded_regular_file(
                    &root.join(REPORT_DIRECTORY).join("report.pdf"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
                None,
                None,
                None,
            ),
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => (
                Some(sha256_identity(&read_bounded_regular_file(
                    &root.join(REPORT_DIRECTORY).join("report.pdf"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
                Some(sha256_identity(&read_bounded_regular_file(
                    &root.join(RESUME_DIRECTORY).join("result-recovery-ir.json"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
                read_optional_bounded_regular_file(
                    &root.join(RESUME_DIRECTORY).join("reaction-result-ir.json"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?
                .map(|bytes| sha256_identity(&bytes)),
                Some(sha256_identity(&read_bounded_regular_file(
                    &root.join(REPORT_DIRECTORY).join("report.md"),
                    MAX_PRODUCT_ARTIFACT_BYTES,
                )?)),
            ),
        };
    if review.claim_boundary
        != review_claim_boundary(session.analysis_profile, expected_reaction.is_some())
    {
        return Err(WorkbenchError::new(
            "workbench_review_contract_invalid",
            "review claim boundary does not match the verified reaction binding",
        ));
    }
    if review.source_session_hash != expected_session_hash
        || review.result_artifact_hash != sha256_identity(&result)
        || review.comparison_artifact_hash != sha256_identity(&comparison)
        || review.pdf_artifact_hash != expected_pdf
        || review.result_recovery_artifact_hash != expected_recovery
        || review.reaction_result_artifact_hash != expected_reaction
        || review.report_document_artifact_hash != expected_document
    {
        return Err(WorkbenchError::new(
            "workbench_review_binding_mismatch",
            "human review is not bound to the verified session, result, reactions, comparison and PDF",
        ));
    }
    Ok(())
}

const fn review_claim_boundary(
    profile: Option<WorkbenchAnalysisProfileV1>,
    reaction_bound: bool,
) -> &'static str {
    match (profile, reaction_bound) {
        (Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1), true) => {
            MODEL_IR_LINEAR_REACTION_REVIEW_CLAIM_BOUNDARY
        }
        (Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1), false) => {
            MODEL_IR_LINEAR_REVIEW_CLAIM_BOUNDARY_LEGACY
        }
        (None, _) => REVIEW_CLAIM_BOUNDARY,
    }
}

fn strict_artifact_json(
    path: &Path,
    maximum_bytes: u64,
    code: &'static str,
) -> Result<Value, WorkbenchError> {
    let bytes = read_bounded_regular_file(path, maximum_bytes)?;
    let value = decode_json_strict(&bytes).map_err(|error| input_error(code, &error))?;
    let canonical = canonical_json(&value, code)?;
    if canonical.as_bytes() != bytes {
        return Err(WorkbenchError::new(
            code,
            "verified product JSON is not canonical",
        ));
    }
    Ok(value)
}

fn verified_receipt_json(path: &Path) -> Result<Value, WorkbenchError> {
    let bytes = read_bounded_regular_file(path, MAX_PRODUCT_ARTIFACT_BYTES)?;
    verify_self_hashed_json(&bytes, "receipt_hash")
}

fn verify_external_source_artifact_bindings(
    source: &ExternalSourceV1,
    source_artifact: &[u8],
    executable_artifact: Option<&[u8]>,
) -> Result<(), WorkbenchError> {
    if sha256_identity(source_artifact) != source.source_artifact_hash {
        return Err(WorkbenchError::new(
            "workbench_external_source_hash_mismatch",
            "the imported external source bytes do not match the external-result binding",
        ));
    }
    match (&source.executable_hash, executable_artifact) {
        (Some(expected), Some(bytes)) if *expected == sha256_identity(bytes) => Ok(()),
        (None, None) => Ok(()),
        (Some(_), Some(_)) => Err(WorkbenchError::new(
            "workbench_external_executable_hash_mismatch",
            "the imported executable bytes do not match the external-result binding",
        )),
        (Some(_), None) => Err(WorkbenchError::new(
            "workbench_external_executable_missing",
            "the external-result binding requires executable bytes",
        )),
        (None, Some(_)) => Err(WorkbenchError::new(
            "workbench_external_executable_unbound",
            "executable bytes were supplied without an external-result hash binding",
        )),
    }
}

fn verify_requested_model_identity(
    requested: &structural_contracts::product_ir::ModelIrIdentityV1,
    model: &structural_contracts::model_ir::ModelIrV2Document,
) -> Result<(), WorkbenchError> {
    if requested.content_hash == model.content_hash()
        && requested.semantic_hash == model.semantic_hash()
        && requested.provenance_hash == model.provenance_hash()
    {
        Ok(())
    } else {
        Err(WorkbenchError::new(
            "workbench_model_request_identity_mismatch",
            "the analysis request is not bound to the imported ModelIR identities",
        ))
    }
}

#[allow(clippy::too_many_lines)]
fn verify_import_bindings(root: &Path, session: &WorkbenchSessionV1) -> Result<(), WorkbenchError> {
    let imported = root.join(IMPORT_DIRECTORY);
    let source_model =
        read_bounded_regular_file(&imported.join("source-model-ir.json"), MAX_MODEL_BYTES)?;
    let model = read_bounded_regular_file(&imported.join("model-ir.json"), MAX_MODEL_BYTES)?;
    let request = read_bounded_regular_file(
        &imported.join("model-analysis-request.json"),
        MAX_REQUEST_BYTES,
    )?;
    let external = read_bounded_regular_file(
        &imported.join("external-result.json"),
        MAX_EXTERNAL_RESULT_BYTES,
    )?;
    let source = read_bounded_regular_file(
        &imported.join("external-source.artifact"),
        MAX_EXTERNAL_ARTIFACT_BYTES,
    )?;
    let parsed_model = parse_model_ir_v2(&model)
        .map_err(|error| input_error("workbench_imported_model_invalid", &error))?;
    let request_hash = match session.analysis_profile {
        None => {
            let parsed = parse_model_ir_ndtha_analysis_request_v1(&request)
                .map_err(|error| input_error("workbench_imported_request_invalid", &error))?;
            verify_requested_model_identity(&parsed.request().model_identity, &parsed_model)?;
            parsed.request_hash().to_owned()
        }
        Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
            let parsed = parse_model_ir_linear_analysis_request_v1(&request)
                .map_err(|error| input_error("workbench_imported_request_invalid", &error))?;
            verify_requested_model_identity(&parsed.request().model_identity, &parsed_model)?;
            parsed.request_hash().to_owned()
        }
    };
    let executable = if session.executable_artifact_hash.is_some() {
        Some(read_bounded_regular_file(
            &imported.join("external-executable.artifact"),
            MAX_EXTERNAL_ARTIFACT_BYTES,
        )?)
    } else {
        if imported.join("external-executable.artifact").exists() {
            return Err(WorkbenchError::new(
                "workbench_import_binding_mismatch",
                "an unbound executable artifact appeared in the immutable import set",
            ));
        }
        None
    };
    let external_result_hash = match session.analysis_profile {
        None => {
            let parsed = parse_external_result_v1(&external).map_err(|error| {
                input_error("workbench_imported_external_result_invalid", &error)
            })?;
            verify_external_source_artifact_bindings(
                &parsed.external_result().source,
                &source,
                executable.as_deref(),
            )?;
            parsed.external_result_hash().to_owned()
        }
        Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
            let parsed = parse_model_ir_linear_external_result_v1(&external).map_err(|error| {
                input_error("workbench_imported_external_result_invalid", &error)
            })?;
            verify_external_source_artifact_bindings(
                &parsed.external_result().source,
                &source,
                executable.as_deref(),
            )?;
            parsed.external_result_hash().to_owned()
        }
    };
    let mgt_binding = verify_mgt_import_bindings(&imported, session, &parsed_model, &model)?;
    let valid = session.source_model_ir_hash == sha256_identity(&source_model)
        && session.model_content_hash == parsed_model.content_hash()
        && session.model_semantic_hash == parsed_model.semantic_hash()
        && session.model_provenance_hash == parsed_model.provenance_hash()
        && session.analysis_request_hash == request_hash
        && session.external_result_hash == external_result_hash
        && session.source_artifact_hash == sha256_identity(&source)
        && session.executable_artifact_hash == executable.as_deref().map(sha256_identity);
    if !valid {
        return Err(WorkbenchError::new(
            "workbench_import_binding_mismatch",
            "one or more immutable imported artifacts differ from the durable session",
        ));
    }
    let mut binding = json!({
        "source_model_ir_hash": session.source_model_ir_hash,
        "model_content_hash": session.model_content_hash,
        "model_semantic_hash": session.model_semantic_hash,
        "model_provenance_hash": session.model_provenance_hash,
        "analysis_request_hash": session.analysis_request_hash,
        "external_result_hash": session.external_result_hash,
        "source_artifact_hash": session.source_artifact_hash,
        "executable_artifact_hash": session.executable_artifact_hash,
    });
    if let Some(profile) = session.analysis_profile {
        binding
            .as_object_mut()
            .expect("Workbench binding is an object")
            .insert("analysis_profile".to_owned(), json!(profile));
    }
    if let Some(mgt_import) = mgt_binding {
        binding
            .as_object_mut()
            .expect("Workbench binding is an object")
            .insert("mgt_import".to_owned(), mgt_import);
    }
    let binding_json = canonical_json(&binding, "workbench_session_identity_failed")?;
    if session.session_id != sha256_identity(binding_json.as_bytes()) {
        return Err(WorkbenchError::new(
            "workbench_session_identity_mismatch",
            "the session ID is not derived from the immutable imported artifact identities",
        ));
    }
    verify_receipt_directory(&imported, "import-receipt.json")?;
    Ok(())
}

fn verify_mgt_import_bindings(
    imported: &Path,
    session: &WorkbenchSessionV1,
    parsed_model: &structural_contracts::model_ir::ModelIrV2Document,
    model: &[u8],
) -> Result<Option<Value>, WorkbenchError> {
    let field_count = [
        session.mgt_source_hash.as_ref(),
        session.mgt_import_health_artifact_hash.as_ref(),
        session.mgt_import_receipt_artifact_hash.as_ref(),
    ]
    .into_iter()
    .flatten()
    .count();
    let names = [
        "source.mgt",
        "import-health.json",
        "mgt-native-validation.json",
        "mgt-native-snapshot.json",
        "mgt-import-receipt.json",
    ];
    if field_count == 0 {
        if names.iter().any(|name| imported.join(name).exists()) {
            return Err(WorkbenchError::new(
                "workbench_import_binding_mismatch",
                "unbound MGT evidence appeared in a ModelIR-only import set",
            ));
        }
        return Ok(None);
    }
    if field_count != 3 {
        return Err(WorkbenchError::new(
            "workbench_mgt_import_binding_incomplete",
            "MGT import session identities must be absent or complete",
        ));
    }

    let mgt_source = read_bounded_regular_file(&imported.join("source.mgt"), MAX_MODEL_BYTES)?;
    let mgt_health =
        read_bounded_regular_file(&imported.join("import-health.json"), MAX_MODEL_BYTES)?;
    let mgt_validation = read_bounded_regular_file(
        &imported.join("mgt-native-validation.json"),
        MAX_MODEL_BYTES,
    )?;
    let mgt_snapshot =
        read_bounded_regular_file(&imported.join("mgt-native-snapshot.json"), MAX_MODEL_BYTES)?;
    let mgt_receipt =
        read_bounded_regular_file(&imported.join("mgt-import-receipt.json"), MAX_MODEL_BYTES)?;
    let reproduced = execute_native_mgt_import(&mgt_source, parsed_model.model_id())
        .map_err(|error| input_error("workbench_mgt_revalidation_failed", &error))?;
    let reproduced_exact = reproduced.is_normalized()
        && reproduced.source_bytes() == mgt_source
        && reproduced
            .model_ir_json()
            .is_some_and(|value| value.as_bytes() == model)
        && reproduced.health_json().as_bytes() == mgt_health
        && reproduced
            .validation_json()
            .is_some_and(|value| value.as_bytes() == mgt_validation)
        && reproduced
            .snapshot_json()
            .is_some_and(|value| value.as_bytes() == mgt_snapshot)
        && reproduced.receipt_json().as_bytes() == mgt_receipt;
    let source_hash = sha256_identity(&mgt_source);
    let health_hash = sha256_identity(&mgt_health);
    let receipt_hash = sha256_identity(&mgt_receipt);
    if !reproduced_exact
        || session.mgt_source_hash.as_deref() != Some(source_hash.as_str())
        || session.mgt_import_health_artifact_hash.as_deref() != Some(health_hash.as_str())
        || session.mgt_import_receipt_artifact_hash.as_deref() != Some(receipt_hash.as_str())
    {
        return Err(WorkbenchError::new(
            "workbench_mgt_import_binding_mismatch",
            "original MGT bytes or deterministic import/C++ validation evidence changed",
        ));
    }
    Ok(Some(json!({
        "source_hash": source_hash,
        "health_artifact_hash": health_hash,
        "receipt_artifact_hash": receipt_hash,
    })))
}

fn verify_stage_chain(
    root: &Path,
    session: &WorkbenchSessionV1,
) -> Result<DiscoveredState, WorkbenchError> {
    let report_receipt = match session.analysis_profile {
        Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => "report-receipt.json",
        None => "pdf-receipt.json",
    };
    let stages = [
        (
            WorkbenchStageV1::Imported,
            IMPORT_DIRECTORY,
            "import-receipt.json",
        ),
        (
            WorkbenchStageV1::Validated,
            VALIDATION_DIRECTORY,
            "validation-receipt.json",
        ),
        (
            WorkbenchStageV1::Checkpointed,
            RUN_DIRECTORY,
            "run-receipt.json",
        ),
        (
            WorkbenchStageV1::Terminal,
            RESUME_DIRECTORY,
            "run-receipt.json",
        ),
        (
            WorkbenchStageV1::Compared,
            COMPARISON_DIRECTORY,
            "comparison-receipt.json",
        ),
        (WorkbenchStageV1::Reported, REPORT_DIRECTORY, report_receipt),
    ];
    let mut discovered = WorkbenchStageV1::Imported;
    let mut gap = false;
    let mut terminal_status = None;
    let mut comparison_passed = None;
    for (stage, directory, receipt) in stages {
        let path = root.join(directory);
        if !path.exists() {
            gap = true;
            continue;
        }
        if gap {
            return Err(WorkbenchError::new(
                "workbench_stage_gap",
                format!("atomic stage directory {directory} exists after a missing predecessor"),
            ));
        }
        verify_directory(&path, "workbench_stage_directory_invalid")?;
        let receipt_value = verify_receipt_directory(&path, receipt)?;
        let (terminal, comparison) = verify_stage_receipt(
            stage,
            directory,
            &receipt_value,
            session.session_id(),
            session.analysis_profile,
        )?;
        if terminal.is_some() {
            terminal_status = terminal;
        }
        if comparison.is_some() {
            comparison_passed = comparison;
        }
        discovered = stage;
    }
    Ok(DiscoveredState {
        stage: discovered,
        terminal_status,
        comparison_passed,
    })
}

fn verify_stage_receipt(
    stage: WorkbenchStageV1,
    directory: &str,
    receipt: &Value,
    expected_session_id: &str,
    analysis_profile: Option<WorkbenchAnalysisProfileV1>,
) -> Result<(Option<String>, Option<bool>), WorkbenchError> {
    if receipt
        .get("session_id")
        .and_then(Value::as_str)
        .is_some_and(|session_id| session_id != expected_session_id)
    {
        return Err(WorkbenchError::new(
            "workbench_stage_session_mismatch",
            format!("stage {directory} belongs to a different Workbench session"),
        ));
    }
    let status = receipt.get("status").and_then(Value::as_str);
    let expected = match stage {
        WorkbenchStageV1::Imported => Some("imported"),
        WorkbenchStageV1::Validated => Some("validated"),
        WorkbenchStageV1::Checkpointed if analysis_profile.is_some() => Some("active"),
        WorkbenchStageV1::Checkpointed => Some("checkpointed"),
        WorkbenchStageV1::Reported if analysis_profile.is_some() => Some("reported"),
        WorkbenchStageV1::Terminal | WorkbenchStageV1::Compared | WorkbenchStageV1::Reported => {
            None
        }
    };
    if expected.is_some() && status != expected {
        return Err(WorkbenchError::new(
            "workbench_stage_receipt_invalid",
            format!("stage {directory} receipt has an invalid status"),
        ));
    }
    let terminal = if stage == WorkbenchStageV1::Terminal {
        let accepted = match analysis_profile {
            Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => {
                status.filter(|value| *value == "completed")
            }
            None => status.filter(|value| matches!(*value, "completed" | "collapsed")),
        };
        Some(
            accepted
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_terminal_receipt_invalid",
                        "terminal run receipt has no status supported by the Workbench profile",
                    )
                })?
                .to_owned(),
        )
    } else {
        None
    };
    let comparison = if stage == WorkbenchStageV1::Compared {
        Some(
            status
                .filter(|value| matches!(*value, "passed" | "diverged"))
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_comparison_receipt_invalid",
                        "comparison receipt must say passed or diverged",
                    )
                })?
                == "passed",
        )
    } else {
        None
    };
    Ok((terminal, comparison))
}

fn verify_receipt_directory(directory: &Path, receipt_name: &str) -> Result<Value, WorkbenchError> {
    let receipt_bytes =
        read_bounded_regular_file(&directory.join(receipt_name), MAX_PRODUCT_ARTIFACT_BYTES)?;
    let receipt = verify_self_hashed_json(&receipt_bytes, "receipt_hash")?;
    let artifacts = receipt
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_receipt_inventory_invalid",
                "stage receipt has no artifact inventory",
            )
        })?;
    for artifact in artifacts {
        let file = artifact
            .get("file")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no file",
                )
            })?;
        if !valid_flat_file_name(file) {
            return Err(WorkbenchError::new(
                "workbench_receipt_inventory_invalid",
                "artifact inventory contains a non-flat file name",
            ));
        }
        let expected_hash = artifact
            .get("content_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no content hash",
                )
            })?;
        let expected_length = artifact
            .get("byte_length")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_receipt_inventory_invalid",
                    "artifact inventory entry has no byte length",
                )
            })?;
        let bytes = read_bounded_regular_file(&directory.join(file), MAX_PRODUCT_ARTIFACT_BYTES)?;
        let actual_length = u64::try_from(bytes.len()).map_err(|_| {
            WorkbenchError::new(
                "workbench_artifact_length_invalid",
                "artifact length does not fit the receipt contract",
            )
        })?;
        if expected_length != actual_length || expected_hash != sha256_identity(&bytes) {
            return Err(WorkbenchError::new(
                "workbench_artifact_inventory_mismatch",
                format!("artifact {file} differs from its stage receipt"),
            ));
        }
    }
    Ok(receipt)
}

fn parse_session(bytes: &[u8]) -> Result<WorkbenchSessionV1, WorkbenchError> {
    let value = verify_self_hashed_json(bytes, "session_hash")?;
    let session: WorkbenchSessionV1 = serde_json::from_value(value).map_err(|_| {
        WorkbenchError::new(
            "workbench_session_decode_failed",
            "session fields are missing, mistyped or unknown",
        )
    })?;
    if session.schema_version != SESSION_SCHEMA_V1
        || session.claim_boundary != session_claim_boundary(session.analysis_profile)
    {
        return Err(WorkbenchError::new(
            "workbench_session_contract_invalid",
            "session schema or claim boundary is unsupported",
        ));
    }
    Ok(session)
}

const fn session_claim_boundary(profile: Option<WorkbenchAnalysisProfileV1>) -> &'static str {
    match profile {
        Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => MODEL_IR_LINEAR_CLAIM_BOUNDARY,
        None => CLAIM_BOUNDARY,
    }
}

fn canonical_session(session: &WorkbenchSessionV1) -> Result<String, WorkbenchError> {
    let mut value = serde_json::to_value(session).map_err(|_| {
        WorkbenchError::new(
            "workbench_session_serialization_failed",
            "session could not be projected to JSON",
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_session_serialization_failed",
                "session projection is not an object",
            )
        })?
        .remove("session_hash");
    let unsigned = canonical_json(&value, "workbench_session_canonicalization_failed")?;
    value
        .as_object_mut()
        .expect("checked session object")
        .insert(
            "session_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonical_json(&value, "workbench_session_canonicalization_failed")
}

fn canonical_self_hashed(value: Value) -> Result<String, WorkbenchError> {
    canonical_hashed_json(
        value,
        "receipt_hash",
        "workbench_receipt_serialization_failed",
    )
}

fn canonical_hashed_json(
    mut value: Value,
    hash_field: &'static str,
    code: &'static str,
) -> Result<String, WorkbenchError> {
    let object = value
        .as_object_mut()
        .ok_or_else(|| WorkbenchError::new(code, "hashed JSON projection is not an object"))?;
    object.remove(hash_field);
    let unsigned = canonical_json(&value, code)?;
    value
        .as_object_mut()
        .expect("checked receipt object")
        .insert(
            hash_field.to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonical_json(&value, code)
}

fn verify_self_hashed_json(bytes: &[u8], hash_field: &str) -> Result<Value, WorkbenchError> {
    let mut value = decode_json_strict(bytes)
        .map_err(|error| input_error("workbench_hashed_json_invalid", &error))?;
    let canonical = canonical_json(&value, "workbench_hashed_json_canonicalization_failed")?;
    if canonical.as_bytes() != bytes {
        return Err(WorkbenchError::new(
            "workbench_hashed_json_noncanonical",
            "durable JSON bytes are not the exact canonical representation",
        ));
    }
    let expected = value
        .as_object_mut()
        .and_then(|object| object.remove(hash_field))
        .and_then(|item| item.as_str().map(ToOwned::to_owned))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_hashed_json_missing_hash",
                format!("durable JSON has no {hash_field}"),
            )
        })?;
    let unsigned = canonical_json(&value, "workbench_hashed_json_canonicalization_failed")?;
    if expected != sha256_identity(unsigned.as_bytes()) {
        return Err(WorkbenchError::new(
            "workbench_hashed_json_hash_mismatch",
            format!("durable JSON {hash_field} does not verify"),
        ));
    }
    value
        .as_object_mut()
        .expect("verified JSON object")
        .insert(hash_field.to_owned(), Value::String(expected));
    Ok(value)
}

fn receipt_status(
    receipt_json: &str,
    analysis_profile: Option<WorkbenchAnalysisProfileV1>,
) -> Result<String, WorkbenchError> {
    let value = verify_self_hashed_json(receipt_json.as_bytes(), "receipt_hash")?;
    let accepted = |status: &&str| match analysis_profile {
        Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1) => *status == "completed",
        None => matches!(*status, "completed" | "collapsed"),
    };
    value
        .get("status")
        .and_then(Value::as_str)
        .filter(accepted)
        .map(ToOwned::to_owned)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_terminal_receipt_invalid",
                "terminal outcome has no supported status",
            )
        })
}

fn artifact_entry(
    role: &str,
    file: &str,
    media_type: &str,
    bytes: &[u8],
) -> Result<Value, WorkbenchError> {
    Ok(json!({
        "role": role,
        "file": file,
        "media_type": media_type,
        "byte_length": u64::try_from(bytes.len()).map_err(|_| WorkbenchError::new(
            "workbench_artifact_length_invalid",
            "artifact length exceeds the receipt representation",
        ))?,
        "content_hash": sha256_identity(bytes),
    }))
}

fn canonical_json(value: &Value, code: &'static str) -> Result<String, WorkbenchError> {
    canonicalize_model_ir_v2(value).map_err(|error| WorkbenchError::new(code, error.to_string()))
}

fn input_error(code: &'static str, error: &impl fmt::Display) -> WorkbenchError {
    WorkbenchError::new(code, error.to_string())
}

fn publish_initial_workspace(
    root: &Path,
    artifacts: &[(&str, &[u8])],
    executable_artifact: Option<&[u8]>,
    import_receipt: &[u8],
    session_json: &[u8],
) -> Result<(), WorkbenchError> {
    let parent = output_parent(root);
    let output_name = output_name(root)?;
    let temporary = temporary_path(parent, output_name);
    fs::create_dir(&temporary)
        .map_err(|error| io_error("create Workbench temporary root", &error))?;
    let result = (|| {
        let import = temporary.join(IMPORT_DIRECTORY);
        fs::create_dir(&import)
            .map_err(|error| io_error("create Workbench import directory", &error))?;
        for (name, bytes) in artifacts {
            write_synced_new_file(&import.join(name), bytes)?;
        }
        if let Some(bytes) = executable_artifact {
            write_synced_new_file(&import.join("external-executable.artifact"), bytes)?;
        }
        write_synced_new_file(&import.join("import-receipt.json"), import_receipt)?;
        sync_directory(&import, "sync Workbench import directory")?;
        write_synced_new_file(&temporary.join(SESSION_FILE), session_json)?;
        sync_directory(&temporary, "sync Workbench temporary root")?;
        fs::rename(&temporary, root).map_err(|error| io_error("publish Workbench root", &error))?;
        sync_directory(parent, "sync Workbench output parent")
    })();
    if result.is_err() {
        let _ignored = fs::remove_dir_all(&temporary);
    }
    result
}

fn publish_new_directory(output: &Path, artifacts: &[(&str, &[u8])]) -> Result<(), WorkbenchError> {
    if output.exists() {
        return Err(WorkbenchError::new(
            "workbench_stage_destination_exists",
            "stage output directory already exists",
        ));
    }
    let parent = output_parent(output);
    verify_directory(parent, "workbench_stage_parent_invalid")?;
    let output_name = output_name(output)?;
    let temporary = temporary_path(parent, output_name);
    fs::create_dir(&temporary)
        .map_err(|error| io_error("create Workbench stage temporary directory", &error))?;
    let result = (|| {
        for (name, bytes) in artifacts {
            if !valid_flat_file_name(name) {
                return Err(WorkbenchError::new(
                    "workbench_artifact_name_invalid",
                    "stage artifact must use a flat fixed file name",
                ));
            }
            write_synced_new_file(&temporary.join(name), bytes)?;
        }
        sync_directory(&temporary, "sync Workbench stage temporary directory")?;
        fs::rename(&temporary, output)
            .map_err(|error| io_error("publish Workbench stage directory", &error))?;
        sync_directory(parent, "sync Workbench stage parent")
    })();
    if result.is_err() {
        let _ignored = fs::remove_dir_all(&temporary);
    }
    result
}

fn write_atomic_file(path: &Path, bytes: &[u8]) -> Result<(), WorkbenchError> {
    let parent = output_parent(path);
    verify_directory(parent, "workbench_session_parent_invalid")?;
    let name = output_name(path)?;
    let temporary = temporary_path(parent, name);
    write_synced_new_file(&temporary, bytes)?;
    let result = fs::rename(&temporary, path)
        .map_err(|error| io_error("atomically replace Workbench session", &error));
    if result.is_err() {
        let _ignored = fs::remove_file(&temporary);
        return result;
    }
    sync_directory(parent, "sync Workbench session parent")
}

fn write_synced_new_file(path: &Path, bytes: &[u8]) -> Result<(), WorkbenchError> {
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| io_error("create Workbench artifact", &error))?;
    file.write_all(bytes)
        .map_err(|error| io_error("write Workbench artifact", &error))?;
    file.sync_all()
        .map_err(|error| io_error("sync Workbench artifact", &error))
}

fn read_bounded_regular_file(path: &Path, maximum_bytes: u64) -> Result<Vec<u8>, WorkbenchError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| io_error("read Workbench artifact metadata", &error))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err(WorkbenchError::new(
            "workbench_artifact_not_regular",
            "artifact must be a regular non-symlink file",
        ));
    }
    if metadata.len() > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_too_large",
            "artifact exceeds its bounded byte limit",
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options
        .open(path)
        .map_err(|error| io_error("open Workbench artifact without symlink traversal", &error))?;
    let opened = file
        .metadata()
        .map_err(|error| io_error("read opened Workbench artifact metadata", &error))?;
    if !opened.is_file() || opened.len() > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_changed",
            "opened artifact is not the same bounded regular file class",
        ));
    }
    let capacity = usize::try_from(opened.len().min(maximum_bytes)).map_err(|_| {
        WorkbenchError::new(
            "workbench_artifact_length_invalid",
            "artifact length does not fit addressable memory",
        )
    })?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(maximum_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| io_error("read Workbench artifact", &error))?;
    if u64::try_from(bytes.len()).map_or(true, |length| length > maximum_bytes) {
        return Err(WorkbenchError::new(
            "workbench_artifact_changed",
            "artifact changed beyond its bounded byte limit while reading",
        ));
    }
    Ok(bytes)
}

fn read_optional_bounded_regular_file(
    path: &Path,
    maximum_bytes: u64,
) -> Result<Option<Vec<u8>>, WorkbenchError> {
    match fs::symlink_metadata(path) {
        Ok(_) => read_bounded_regular_file(path, maximum_bytes).map(Some),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(io_error(
            "read optional Workbench artifact metadata",
            &error,
        )),
    }
}

fn verify_slice_bound(bytes: &[u8], maximum_bytes: u64, label: &str) -> Result<(), WorkbenchError> {
    let length = u64::try_from(bytes.len()).map_err(|_| {
        WorkbenchError::new(
            "workbench_artifact_length_invalid",
            format!("{label} length does not fit the bounded contract"),
        )
    })?;
    if length > maximum_bytes {
        return Err(WorkbenchError::new(
            "workbench_artifact_too_large",
            format!("{label} exceeds its bounded byte limit"),
        ));
    }
    Ok(())
}

fn verify_directory(path: &Path, code: &'static str) -> Result<(), WorkbenchError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| io_error("read directory metadata", &error))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(WorkbenchError::new(
            code,
            "path must be a real non-symlink directory",
        ));
    }
    Ok(())
}

fn sync_directory(path: &Path, action: &'static str) -> Result<(), WorkbenchError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| io_error(action, &error))
}

fn output_parent(path: &Path) -> &Path {
    path.parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
}

fn output_name(path: &Path) -> Result<&str, WorkbenchError> {
    path.file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_output_name_invalid",
                "output path has no valid UTF-8 file name",
            )
        })
}

fn temporary_path(parent: &Path, name: &str) -> PathBuf {
    let sequence = OUTPUT_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    parent.join(format!(".{name}.tmp.{}.{}", std::process::id(), sequence))
}

fn valid_flat_file_name(name: &str) -> bool {
    !name.is_empty() && name != "." && name != ".." && !name.contains('/') && !name.contains('\\')
}

fn io_error(action: &str, error: &std::io::Error) -> WorkbenchError {
    WorkbenchError::new("workbench_io_error", format!("{action} failed: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{
        canonical_session, parse_session, review_claim_boundary, WorkbenchAnalysisProfileV1,
        WorkbenchSessionV1, WorkbenchStageV1,
    };

    #[test]
    fn review_claim_boundaries_preserve_legacy_and_bind_reactions() {
        assert_eq!(
            review_claim_boundary(None, false),
            super::REVIEW_CLAIM_BOUNDARY
        );
        assert_eq!(
            review_claim_boundary(None, true),
            super::REVIEW_CLAIM_BOUNDARY
        );
        assert_eq!(
            review_claim_boundary(Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1), false),
            super::MODEL_IR_LINEAR_REVIEW_CLAIM_BOUNDARY_LEGACY
        );
        assert_eq!(
            review_claim_boundary(Some(WorkbenchAnalysisProfileV1::ModelIrLinearCpuV1), true),
            super::MODEL_IR_LINEAR_REACTION_REVIEW_CLAIM_BOUNDARY
        );
    }

    #[test]
    fn session_hash_round_trip_is_strict_and_deterministic() {
        let session = WorkbenchSessionV1 {
            schema_version: super::SESSION_SCHEMA_V1.to_owned(),
            session_id: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .to_owned(),
            stage: WorkbenchStageV1::Imported,
            source_model_ir_hash:
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
            model_content_hash:
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".to_owned(),
            model_semantic_hash:
                "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd".to_owned(),
            model_provenance_hash:
                "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee".to_owned(),
            analysis_request_hash:
                "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff".to_owned(),
            external_result_hash:
                "sha256:1111111111111111111111111111111111111111111111111111111111111111".to_owned(),
            source_artifact_hash:
                "sha256:2222222222222222222222222222222222222222222222222222222222222222".to_owned(),
            executable_artifact_hash: None,
            analysis_profile: None,
            mgt_source_hash: None,
            mgt_import_health_artifact_hash: None,
            mgt_import_receipt_artifact_hash: None,
            terminal_status: None,
            comparison_passed: None,
            claim_boundary: super::CLAIM_BOUNDARY.to_owned(),
            session_hash: String::new(),
        };
        let first = canonical_session(&session).expect("canonical session");
        let restored = parse_session(first.as_bytes()).expect("verified session");
        let second = canonical_session(&restored).expect("re-canonical session");
        assert_eq!(first, second);

        let mut tampered = first.into_bytes();
        let offset = tampered
            .windows("imported".len())
            .position(|window| window == b"imported")
            .expect("stage token");
        tampered[offset] = b'I';
        assert!(parse_session(&tampered).is_err());
    }
}
