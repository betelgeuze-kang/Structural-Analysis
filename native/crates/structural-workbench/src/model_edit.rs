use std::path::Path;

use serde_json::{json, Value};
use structural_cli::validate_model_bytes;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::sha256_identity;

use super::{
    artifact_entry, canonical_self_hashed, input_error, publish_new_directory,
    read_bounded_regular_file, WorkbenchError, MAX_MODEL_BYTES,
};

use super::linear_combination::{
    require_bounded_linear_load_combination, ExpandedLinearLoadCombinationV1,
    MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
    MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
};
pub use super::linear_combination::{
    MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1,
    MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1,
};

const EDIT_SCHEMA_V1: &str = "structural-native-model-edit-receipt.v1";
const NODE_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-node.v1";
const NODE_ADD_EXTENSION_KEY: &str = "structural-native:model-add-node.v1";
const ORPHAN_NODE_DELETE_EXTENSION_KEY: &str = "structural-native:model-delete-orphan-node.v1";
const NODAL_LOAD_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-nodal-load.v1";
const CONSTRAINT_VALUE_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-constraint-value.v1";
const LINEAR_MATERIAL_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-linear-material.v1";
const FRAME_SECTION_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-frame-section.v1";
const TRUSS_SECTION_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-truss-section.v1";
const FRAME_ELEMENT_ORIENTATION_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-frame-element-orientation.v1";
const FRAME_ELEMENT_PROPERTIES_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-frame-element-properties.v1";
const TRUSS_ELEMENT_PROPERTIES_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-truss-element-properties.v1";
const ELEMENT_CONNECTIVITY_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-element-connectivity.v1";
const FRAME3D_MEMBER_ADD_EXTENSION_KEY: &str = "structural-native:model-add-frame3d-member.v1";
const TRUSS3D_MEMBER_ADD_EXTENSION_KEY: &str = "structural-native:model-add-truss3d-member.v1";
const FRAME3D_LEAF_MEMBER_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-frame3d-leaf-member.v1";
const TRUSS3D_LEAF_MEMBER_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-truss3d-leaf-member.v1";
const NODAL_LOAD_ADD_EXTENSION_KEY: &str = "structural-native:model-add-nodal-load.v1";
const NODAL_LOAD_DELETE_EXTENSION_KEY: &str = "structural-native:model-delete-nodal-load.v1";
const FIXED_CONSTRAINT_ADD_EXTENSION_KEY: &str = "structural-native:model-add-fixed-constraint.v1";
const FIXED_CONSTRAINT_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-fixed-constraint.v1";
const LINEAR_LOAD_PATTERN_ADD_EXTENSION_KEY: &str =
    "structural-native:model-add-linear-load-pattern.v1";
const LINEAR_LOAD_PATTERN_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-linear-load-pattern.v1";
const LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY: &str =
    "structural-native:model-add-linear-load-combination.v1";
const DIRECT_LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY: &str =
    "structural-native:model-add-direct-linear-load-combination.v2";
const NESTED_LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY: &str =
    "structural-native:model-add-nested-linear-load-combination.v3";
const DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-direct-linear-load-combination-factor.v1";
const DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-direct-linear-load-combination-reference.v1";
const NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-nested-linear-load-combination-factor.v1";
const NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-nested-linear-load-combination-reference.v1";
const LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-linear-load-combination.v1";
const DIRECT_LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-direct-linear-load-combination.v2";
const NESTED_LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-nested-linear-load-combination.v3";
const LINEAR_MATERIAL_ADD_EXTENSION_KEY: &str = "structural-native:model-add-linear-material.v1";
const LINEAR_MATERIAL_DELETE_EXTENSION_KEY: &str =
    "structural-native:model-delete-linear-material.v1";
const FRAME_SECTION_ADD_EXTENSION_KEY: &str = "structural-native:model-add-frame-section.v1";
const FRAME_SECTION_DELETE_EXTENSION_KEY: &str = "structural-native:model-delete-frame-section.v1";
const TRUSS_SECTION_ADD_EXTENSION_KEY: &str = "structural-native:model-add-truss-section.v1";
const TRUSS_SECTION_DELETE_EXTENSION_KEY: &str = "structural-native:model-delete-truss-section.v1";
const UPSTREAM_PROVENANCE_KEY: &str = "structural-native:upstream-provenance";
const NODE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_node_coordinate_edit_not_visual_dragging_property_constraint_load_or_solver_editing_engineering_acceptance_or_c6";
const NODE_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_contiguous_neutral_node_addition_not_member_load_constraint_property_solver_visual_editing_engineering_acceptance_or_c6";
const ORPHAN_NODE_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_orphan_node_deletion_with_two_nodes_retained_not_source_owned_extended_element_constraint_load_mapped_unsupported_feature_owned_cascade_reindexing_general_topology_solver_visual_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_nodal_load_component_edit_not_load_creation_deletion_combination_property_constraint_solver_editing_engineering_acceptance_or_c6";
const CONSTRAINT_VALUE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_restrained_dof_prescribed_value_edit_not_restraint_node_or_topology_creation_deletion_solver_editing_engineering_acceptance_or_c6";
const LINEAR_MATERIAL_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_linear_elastic_isotropic_material_parameter_edit_not_material_creation_deletion_law_version_state_or_solver_editing_engineering_acceptance_or_c6";
const FRAME_SECTION_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_frame3d_section_parameter_edit_not_section_creation_deletion_family_version_topology_or_solver_editing_engineering_acceptance_or_c6";
const TRUSS_SECTION_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_truss3d_section_area_edit_not_section_creation_deletion_family_version_topology_or_solver_editing_engineering_acceptance_or_c6";
const FRAME_ELEMENT_ORIENTATION_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_frame3d_element_local_axis_rotation_edit_not_element_creation_deletion_connectivity_formulation_offset_release_topology_or_solver_editing_engineering_acceptance_or_c6";
const FRAME_ELEMENT_PROPERTIES_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_frame3d_element_material_and_section_reference_edit_not_identity_type_formulation_connectivity_orientation_offset_release_property_creation_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const TRUSS_ELEMENT_PROPERTIES_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_truss3d_element_material_and_section_reference_edit_not_identity_type_formulation_connectivity_offset_property_creation_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const ELEMENT_CONNECTIVITY_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_two_node_element_connectivity_edit_not_element_or_node_creation_deletion_identity_type_formulation_property_offset_release_or_solver_editing_engineering_acceptance_or_c6";
const FRAME3D_MEMBER_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_frame3d_node_and_member_addition_with_existing_material_section_not_general_topology_property_load_constraint_solver_visual_editing_engineering_acceptance_or_c6";
const TRUSS3D_MEMBER_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_truss3d_node_and_member_addition_with_existing_material_and_truss_section_not_general_topology_property_load_constraint_solver_visual_editing_engineering_acceptance_or_c6";
const FRAME3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_euler_bernoulli_frame3d_leaf_member_and_orphan_node_deletion_not_cascade_general_entity_or_property_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const TRUSS3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_linear_truss3d_leaf_member_and_orphan_node_deletion_not_cascade_general_entity_or_property_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_static_nodal_load_addition_to_existing_pattern_and_node_not_pattern_node_combination_member_property_constraint_solver_visual_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_nonzero_six_component_nodal_load_deletion_from_existing_linear_static_pattern_with_another_nonzero_load_retained_not_source_owned_pattern_combination_stage_node_or_general_load_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const FIXED_CONSTRAINT_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_homogeneous_six_dof_fixed_constraint_addition_to_existing_unconstrained_node_not_partial_nonzero_mpc_contact_support_set_solver_visual_editing_engineering_acceptance_or_c6";
const FIXED_CONSTRAINT_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_homogeneous_six_dof_fixed_constraint_deletion_not_source_owned_partial_nonzero_staged_mapped_general_constraint_or_topology_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const LINEAR_LOAD_PATTERN_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_static_pattern_with_first_nonzero_nodal_load_addition_to_existing_node_not_self_weight_combination_time_function_pattern_edit_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const LINEAR_LOAD_PATTERN_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_zero_self_weight_linear_static_pattern_with_single_neutral_nonzero_six_component_nodal_load_deletion_not_source_owned_combined_staged_mapped_general_pattern_load_node_or_topology_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_two_distinct_existing_linear_static_load_pattern_term_linear_combination_addition_not_nested_combination_term_edit_deletion_solver_execution_or_selection_visual_editing_engineering_acceptance_or_c6";
const DIRECT_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_two_to_64_unique_direct_existing_linear_static_load_pattern_term_linear_combination_addition_not_nested_combination_term_edit_deletion_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const NESTED_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_acyclic_nested_linear_static_load_combination_addition_depth_eight_expanded_64_terms_not_term_edit_nested_deletion_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_neutral_unreferenced_extension_free_two_to_64_unique_direct_linear_static_load_pattern_combination_single_existing_term_factor_edit_not_reference_identity_order_count_nested_combination_source_owned_roundtrip_unsupported_feature_cascade_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_neutral_unreferenced_extension_free_two_to_64_unique_direct_linear_static_load_pattern_combination_single_existing_term_reference_edit_with_factor_order_count_preserved_not_factor_identity_order_count_nested_combination_source_owned_roundtrip_unsupported_feature_cascade_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_neutral_unreferenced_extension_free_acyclic_nested_linear_static_root_single_existing_typed_term_factor_edit_depth_eight_expanded_64_terms_not_reference_identity_order_count_descendant_edit_source_owned_roundtrip_unsupported_feature_cascade_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_neutral_unreferenced_extension_free_acyclic_nested_linear_static_root_single_existing_typed_term_reference_edit_with_factor_order_count_preserved_depth_eight_expanded_64_terms_not_factor_order_count_descendant_edit_direct_degradation_source_owned_roundtrip_unsupported_feature_cascade_general_solver_selection_visual_editing_engineering_acceptance_or_c6";
const LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_two_distinct_linear_static_load_pattern_term_linear_combination_deletion_not_source_owned_nested_combination_roundtrip_unsupported_feature_term_edit_reindexing_general_deletion_solver_selection_visual_editing_engineering_acceptance_or_c6";
const DIRECT_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_two_to_64_unique_direct_linear_static_load_pattern_term_linear_combination_deletion_not_source_owned_nested_combination_roundtrip_unsupported_feature_term_edit_reindexing_general_deletion_solver_selection_visual_editing_engineering_acceptance_or_c6";
const NESTED_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_acyclic_nested_linear_static_load_combination_deletion_depth_eight_expanded_64_terms_not_source_owned_direct_combination_roundtrip_unsupported_feature_term_edit_reindexing_general_deletion_solver_selection_visual_editing_engineering_acceptance_or_c6";
const LINEAR_MATERIAL_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_elastic_isotropic_material_addition_not_nonlinear_material_section_member_assignment_property_reference_edit_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const LINEAR_MATERIAL_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_v1_linear_elastic_isotropic_material_deletion_with_one_material_retained_not_source_owned_element_or_section_retargeting_cascade_general_property_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const FRAME_SECTION_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_frame3d_section_addition_not_other_section_family_member_assignment_property_reference_edit_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const FRAME_SECTION_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_v1_frame3d_section_deletion_with_one_section_retained_not_source_owned_element_retargeting_cascade_general_property_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const TRUSS_SECTION_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_truss3d_section_addition_not_other_section_family_member_assignment_property_reference_edit_deletion_solver_visual_editing_engineering_acceptance_or_c6";
const TRUSS_SECTION_DELETE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_v1_truss3d_section_deletion_with_one_truss_section_retained_not_source_owned_element_retargeting_cascade_general_property_deletion_reindexing_solver_visual_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_COMPONENT_KEYS: [&str; 6] = ["FX", "FY", "FZ", "MX", "MY", "MZ"];
const DOF_KEYS: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];

/// Complete deterministic artifact pair produced by one bounded node-coordinate edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodeEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded node addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodeAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded orphan-node deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelOrphanNodeDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded nodal-load edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodalLoadEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded constraint-value edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelConstraintValueEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Closed SI parameter set accepted by the linear-elastic material editor.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LinearElasticMaterialParametersV1 {
    pub elastic_modulus_pa: f64,
    pub poisson_ratio: f64,
    pub density_kg_m3: f64,
}

/// Complete deterministic artifact pair produced by one bounded material edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearMaterialEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Closed SI parameter set accepted by the frame-3D section editor.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FrameSectionParametersV1 {
    pub area_m2: f64,
    pub iy_m4: f64,
    pub iz_m4: f64,
    pub torsional_constant_m4: f64,
    pub shear_area_y_m2: f64,
    pub shear_area_z_m2: f64,
}

/// Closed SI parameter set accepted by the truss-3D section author and editor.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TrussSectionParametersV1 {
    pub area_m2: f64,
}

/// Complete deterministic artifact pair produced by one bounded frame-section edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameSectionEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss-section edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTrussSectionEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-element orientation edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameElementOrientationEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-element property edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameElementPropertiesEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss-element property edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTrussElementPropertiesEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded element-connectivity edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelElementConnectivityEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-3D member addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrame3dMemberAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss-3D member addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTruss3dMemberAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame leaf deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrame3dLeafMemberDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss leaf deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTruss3dLeafMemberDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded nodal-load addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodalLoadAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded nodal-load deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodalLoadDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded fixed-constraint addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFixedConstraintAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded fixed-constraint deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFixedConstraintDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded linear-load-pattern addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadPatternAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded linear-load-pattern deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadPatternDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// One load-pattern term accepted by the bounded linear-combination author.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearLoadCombinationTermV1 {
    pub load_pattern_id: String,
    pub factor: f64,
}

/// Explicit reference family accepted by the bounded nested linear-combination author.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LinearLoadCombinationReferenceKindV1 {
    LoadPattern,
    LoadCombination,
}

impl LinearLoadCombinationReferenceKindV1 {
    fn as_str(self) -> &'static str {
        match self {
            Self::LoadPattern => "load_pattern",
            Self::LoadCombination => "load_combination",
        }
    }
}

/// One explicitly typed term accepted by the bounded nested linear-combination author.
#[derive(Clone, Debug, PartialEq)]
pub struct NestedLinearLoadCombinationTermV1 {
    pub reference_id: String,
    pub reference_kind: LinearLoadCombinationReferenceKindV1,
    pub factor: f64,
}

#[derive(Clone, Copy)]
struct SourceModelHashesV1<'a> {
    content: &'a str,
    semantic: &'a str,
    provenance: &'a str,
}

/// Complete deterministic artifact pair produced by one bounded linear-combination addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadCombinationAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded direct-combination factor edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadCombinationFactorEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded direct-combination reference edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadCombinationReferenceEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded linear-combination deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearLoadCombinationDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded linear-material addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearMaterialAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded linear-material deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelLinearMaterialDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-section addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameSectionAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-section deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameSectionDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss-section addition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTrussSectionAddOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded truss-section deletion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelTrussSectionDeleteOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Edit one node in a bounded regular `ModelIR` file and atomically publish a new artifact set.
///
/// # Errors
///
/// Rejects unsafe input/output paths, non-finite coordinates, invalid source or edited semantics,
/// missing node identities, no-op edits, or any create-new publication failure.
pub fn publish_model_node_coordinate_edit(
    source_path: &Path,
    node_id: &str,
    coordinates_m: [f64; 3],
    output_directory: &Path,
) -> Result<ModelNodeEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_node_coordinates(&source, node_id, coordinates_m)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one neutral contiguous node to a bounded regular `ModelIR` file and publish it.
///
/// # Errors
///
/// Rejects unsafe input/output paths, invalid identities or coordinates, invalid source or edited
/// semantics, duplicate identities or coordinates, index drift, or create-new publication failure.
pub fn publish_model_node_add(
    source_path: &Path,
    node_id: &str,
    coordinates_m: [f64; 3],
    output_directory: &Path,
) -> Result<ModelNodeAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_node(&source, node_id, coordinates_m)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one terminal neutral unreferenced orphan node and publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing, non-terminal, source-owned,
/// extended or referenced nodes, minimum topology, index drift, or create-new publication failure.
pub fn publish_model_orphan_node_delete(
    source_path: &Path,
    node_id: &str,
    output_directory: &Path,
) -> Result<ModelOrphanNodeDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_orphan_node(&source, node_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit one existing nodal load in a bounded regular `ModelIR` file and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe input/output paths, non-finite components, invalid source or edited semantics,
/// missing load identities, no-op edits, or any create-new publication failure.
pub fn publish_model_nodal_load_components_edit(
    source_path: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    components_si: [f64; 6],
    output_directory: &Path,
) -> Result<ModelNodalLoadEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome =
        edit_model_nodal_load_components(&source, load_pattern_id, nodal_load_id, components_si)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one nodal load to an existing linear-static pattern and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or components, invalid source or edited semantics,
/// missing or unsupported references, duplicate load identities, or publication failure.
pub fn publish_model_nodal_load_add(
    source_path: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
    output_directory: &Path,
) -> Result<ModelNodalLoadAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_nodal_load(
        &source,
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral nodal load from an existing linear-static pattern.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal loads,
/// source ownership, invalid components, unsupported-feature or round-trip ownership, a pattern
/// that would retain no load, and publication failures.
pub fn publish_model_nodal_load_delete(
    source_path: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    output_directory: &Path,
) -> Result<ModelNodalLoadDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_nodal_load(&source, load_pattern_id, nodal_load_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one homogeneous six-DOF fixed constraint to an existing unconstrained node.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities, invalid source or edited semantics, missing nodes,
/// duplicate constraint identities, overlapping node constraints, or publication failure.
pub fn publish_model_fixed_constraint_add(
    source_path: &Path,
    constraint_id: &str,
    node_id: &str,
    output_directory: &Path,
) -> Result<ModelFixedConstraintAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_fixed_constraint(&source, constraint_id, node_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral homogeneous fixed constraint and publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, non-terminal, source-owned,
/// non-homogeneous, staged, unsupported-feature-owned, or round-trip-mapped constraints, and
/// publication failures.
pub fn publish_model_fixed_constraint_delete(
    source_path: &Path,
    constraint_id: &str,
    output_directory: &Path,
) -> Result<ModelFixedConstraintDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_fixed_constraint(&source, constraint_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one linear-static pattern and its first nonzero nodal load atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or components, invalid source or edited semantics,
/// missing nodes, duplicate pattern/load identities, or publication failure.
pub fn publish_model_linear_load_pattern_add(
    source_path: &Path,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
    output_directory: &Path,
) -> Result<ModelLinearLoadPatternAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_linear_load_pattern(
        &source,
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one bounded direct-pattern linear load combination and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or factors, invalid source or edited semantics,
/// duplicate or missing load patterns, duplicate combination identities, or publication failure.
pub fn publish_model_linear_load_combination_add(
    source_path: &Path,
    load_combination_id: &str,
    terms: &[LinearLoadCombinationTermV1],
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_linear_load_combination(&source, load_combination_id, terms)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit one factor in a bounded direct-pattern linear load combination and publish it atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or factors, invalid source or edited semantics,
/// source-owned, extended, referenced, nested, unsupported-feature-owned or round-trip-owned
/// combinations, missing pattern terms, no-op edits, and publication failures.
pub fn publish_model_direct_linear_load_combination_factor_edit(
    source_path: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: f64,
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationFactorEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_direct_linear_load_combination_factor(
        &source,
        load_combination_id,
        load_pattern_id,
        factor,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Replace one pattern reference in a bounded direct linear load combination and publish it
/// atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities, invalid source or edited semantics, source-owned,
/// extended, referenced, nested, unsupported-feature-owned or round-trip-owned combinations,
/// missing source or replacement patterns, duplicate replacements, no-op edits, and publication
/// failures.
pub fn publish_model_direct_linear_load_combination_reference_edit(
    source_path: &Path,
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationReferenceEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_direct_linear_load_combination_reference(
        &source,
        load_combination_id,
        load_pattern_id,
        replacement_load_pattern_id,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit one typed root factor in a bounded nested linear load combination and publish it
/// atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or factors, invalid source or edited semantics,
/// source-owned, extended, referenced, direct, unsupported-feature-owned or round-trip-owned
/// combinations, missing typed root terms, no-op edits, out-of-profile expansion, and
/// publication failures.
pub fn publish_model_nested_linear_load_combination_factor_edit(
    source_path: &Path,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    factor: f64,
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationFactorEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_nested_linear_load_combination_factor(
        &source,
        load_combination_id,
        reference_kind,
        reference_id,
        factor,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Replace one typed root reference in a bounded nested linear load combination and publish it
/// atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or reference kinds, invalid source or edited
/// semantics, source-owned, extended, referenced, direct, unsupported-feature-owned or
/// round-trip-owned combinations, missing or duplicate typed references, no-op edits, cycles,
/// direct degradation, out-of-profile expansion, and publication failures.
#[allow(clippy::too_many_arguments)]
pub fn publish_model_nested_linear_load_combination_reference_edit(
    source_path: &Path,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    replacement_reference_kind: LinearLoadCombinationReferenceKindV1,
    replacement_reference_id: &str,
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationReferenceEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_nested_linear_load_combination_reference(
        &source,
        load_combination_id,
        reference_kind,
        reference_id,
        replacement_reference_kind,
        replacement_reference_id,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one bounded acyclic nested linear load combination and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or factors, missing or incompatible typed
/// references, cycles, depth/expansion overflow, invalid source or edited semantics, and
/// publication failures.
pub fn publish_model_nested_linear_load_combination_add(
    source_path: &Path,
    load_combination_id: &str,
    terms: &[NestedLinearLoadCombinationTermV1],
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_nested_linear_load_combination(&source, load_combination_id, terms)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral unreferenced bounded direct or nested linear combination
/// atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal
/// combinations, source-owned or malformed rows, out-of-profile nested graphs,
/// unsupported-feature or round-trip ownership, and publication failures.
pub fn publish_model_linear_load_combination_delete(
    source_path: &Path,
    load_combination_id: &str,
    output_directory: &Path,
) -> Result<ModelLinearLoadCombinationDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_linear_load_combination(&source, load_combination_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral linear-static pattern and its sole nodal load atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal patterns,
/// source-owned or malformed rows, load-combination/construction-stage references,
/// unsupported-feature or round-trip ownership, and publication failures.
pub fn publish_model_linear_load_pattern_delete(
    source_path: &Path,
    load_pattern_id: &str,
    output_directory: &Path,
) -> Result<ModelLinearLoadPatternDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_linear_load_pattern(&source, load_pattern_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one v1 linear-elastic isotropic material atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or parameters, invalid source or edited semantics,
/// duplicate material identities, or publication failure.
pub fn publish_model_linear_material_add(
    source_path: &Path,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
    output_directory: &Path,
) -> Result<ModelLinearMaterialAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_linear_material(&source, material_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral unreferenced v1 linear material atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal materials,
/// source-owned or malformed rows, element/section references, unsupported-feature or round-trip
/// ownership, and publication failures.
pub fn publish_model_linear_material_delete(
    source_path: &Path,
    material_id: &str,
    output_directory: &Path,
) -> Result<ModelLinearMaterialDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_linear_material(&source, material_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one v1 `frame_3d` section atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities or parameters, invalid source or edited semantics,
/// duplicate section identities, or publication failure.
pub fn publish_model_frame_section_add(
    source_path: &Path,
    section_id: &str,
    parameters: FrameSectionParametersV1,
    output_directory: &Path,
) -> Result<ModelFrameSectionAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_frame_section(&source, section_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral unreferenced v1 frame section atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal sections,
/// source-owned or malformed rows, element references, unsupported-feature or round-trip
/// ownership, and publication failures.
pub fn publish_model_frame_section_delete(
    source_path: &Path,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelFrameSectionDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_frame_section(&source, section_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one v1 `truss_3d` section atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identity or area, invalid source or edited semantics, duplicate
/// section identities, or publication failure.
pub fn publish_model_truss_section_add(
    source_path: &Path,
    section_id: &str,
    parameters: TrussSectionParametersV1,
    output_directory: &Path,
) -> Result<ModelTrussSectionAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_truss_section(&source, section_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral unreferenced v1 truss section atomically.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing or non-terminal sections,
/// source-owned or malformed rows, element references, unsupported-feature or round-trip
/// ownership, removal of the last truss section, and publication failures.
pub fn publish_model_truss_section_delete(
    source_path: &Path,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelTrussSectionDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_truss_section(&source, section_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit one prescribed value for an existing restrained DOF and atomically publish the result.
///
/// # Errors
///
/// Rejects unsafe input/output paths, unknown DOFs, non-finite values, invalid source or edited
/// semantics, missing constraint identities, unrestrained DOFs, no-op edits, or publication failure.
pub fn publish_model_constraint_value_edit(
    source_path: &Path,
    constraint_id: &str,
    dof: &str,
    value_si: f64,
    output_directory: &Path,
) -> Result<ModelConstraintValueEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_constraint_value(&source, constraint_id, dof, value_si)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit the parameters of one existing v1 linear-elastic material and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid SI parameters, invalid source or edited semantics, missing or
/// unsupported material identities, no-op edits, or create-new publication failures.
pub fn publish_model_linear_material_edit(
    source_path: &Path,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
    output_directory: &Path,
) -> Result<ModelLinearMaterialEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_linear_material(&source, material_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit the parameters of one existing v1 `frame_3d` section and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid SI parameters, invalid source or edited semantics, missing or
/// unsupported section identities, no-op edits, or create-new publication failures.
pub fn publish_model_frame_section_edit(
    source_path: &Path,
    section_id: &str,
    parameters: FrameSectionParametersV1,
    output_directory: &Path,
) -> Result<ModelFrameSectionEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_frame_section(&source, section_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit the area of one existing v1 `truss_3d` section and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, invalid SI area, invalid source or edited semantics, missing or
/// unsupported section identities, no-op edits, or create-new publication failures.
pub fn publish_model_truss_section_edit(
    source_path: &Path,
    section_id: &str,
    parameters: TrussSectionParametersV1,
    output_directory: &Path,
) -> Result<ModelTrussSectionEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_truss_section(&source, section_id, parameters)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Edit the local-axis rotation of one existing `frame_3d` element and atomically publish it.
///
/// # Errors
///
/// Rejects unsafe paths, non-finite radians, invalid source or edited semantics, missing or
/// unsupported element identities, no-op edits, or create-new publication failures.
pub fn publish_model_frame_element_orientation_edit(
    source_path: &Path,
    element_id: &str,
    local_axis_rotation_rad: f64,
    output_directory: &Path,
) -> Result<ModelFrameElementOrientationEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome =
        edit_model_frame_element_orientation(&source, element_id, local_axis_rotation_rad)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Assign compatible material and section references to one existing `frame_3d` element.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities, invalid source or edited semantics, missing or
/// incompatible element/property identities, complete no-op edits, or publication failures.
pub fn publish_model_frame_element_properties_edit(
    source_path: &Path,
    element_id: &str,
    material_id: &str,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelFrameElementPropertiesEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome =
        edit_model_frame_element_properties(&source, element_id, material_id, section_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Assign compatible material and section references to one existing `truss_3d` element.
///
/// # Errors
///
/// Rejects unsafe paths, invalid identities, invalid source or edited semantics, missing or
/// incompatible element/property identities, complete no-op edits, or publication failures.
pub fn publish_model_truss_element_properties_edit(
    source_path: &Path,
    element_id: &str,
    material_id: &str,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelTrussElementPropertiesEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome =
        edit_model_truss_element_properties(&source, element_id, material_id, section_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Retarget the two endpoints of one existing element and atomically publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, missing element or node identities,
/// identical endpoints, no-op edits, or create-new publication failures.
pub fn publish_model_element_connectivity_edit(
    source_path: &Path,
    element_id: &str,
    node_ids: [&str; 2],
    output_directory: &Path,
) -> Result<ModelElementConnectivityEditOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = edit_model_element_connectivity(&source, element_id, node_ids)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one node and one connected linear `frame_3d` member and atomically publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, duplicate identities or coordinates,
/// missing/unsupported existing node, material, or section references, and publication failures.
#[allow(clippy::too_many_arguments)]
pub fn publish_model_frame3d_member_add(
    source_path: &Path,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelFrame3dMemberAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_frame3d_member(
        &source,
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Add one node and one connected linear `truss_3d` member and atomically publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, duplicate identities or coordinates,
/// missing/unsupported existing node, material, or truss-section references, and publication
/// failures.
#[allow(clippy::too_many_arguments)]
pub fn publish_model_truss3d_member_add(
    source_path: &Path,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
    output_directory: &Path,
) -> Result<ModelTruss3dMemberAddOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = add_model_truss3d_member(
        &source,
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral frame leaf and its orphan node, then publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, non-terminal or source-owned rows,
/// any other element/load/constraint/stage/round-trip reference, and publication failures.
pub fn publish_model_frame3d_leaf_member_delete(
    source_path: &Path,
    element_id: &str,
    node_id: &str,
    output_directory: &Path,
) -> Result<ModelFrame3dLeafMemberDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_frame3d_leaf_member(&source, element_id, node_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Delete one last contiguous neutral truss leaf and its orphan node, then publish the result.
///
/// # Errors
///
/// Rejects unsafe paths, invalid source or edited semantics, non-terminal or source-owned rows,
/// any other element/load/constraint/stage/round-trip reference, and publication failures.
pub fn publish_model_truss3d_leaf_member_delete(
    source_path: &Path,
    element_id: &str,
    node_id: &str,
    output_directory: &Path,
) -> Result<ModelTruss3dLeafMemberDeleteOutcomeV1, WorkbenchError> {
    let source = read_bounded_regular_file(source_path, MAX_MODEL_BYTES)?;
    let outcome = delete_model_truss3d_leaf_member(&source, element_id, node_id)?;
    publish_new_directory(
        output_directory,
        &[
            ("model-ir.json", outcome.model_ir_json.as_bytes()),
            ("edit-receipt.json", outcome.receipt_json.as_bytes()),
        ],
    )?;
    Ok(outcome)
}

/// Produce one provenance-bound, C++-revalidated node-coordinate edit in memory.
///
/// # Errors
///
/// Rejects non-finite coordinates, an invalid source model, a missing node, a no-op edit, schema
/// drift introduced by provenance projection, or edited geometry rejected by C++ semantics.
pub fn edit_model_node_coordinates(
    source_bytes: &[u8],
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<ModelNodeEditOutcomeV1, WorkbenchError> {
    validate_edit_request(source_bytes.len(), node_id, coordinates_m)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_coordinates_m = replace_node_coordinates(&mut edited, node_id, coordinates_m)?;
    if previous_coordinates_m
        .iter()
        .zip(coordinates_m)
        .all(|(previous, edited)| {
            normalized_number_bits(*previous) == normalized_number_bits(edited)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited coordinates are canonically identical to the source node",
        ));
    }
    bind_edit_provenance(
        &mut edited,
        node_id,
        previous_coordinates_m,
        coordinates_m,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_node_approximated(&mut edited, node_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "node_coordinates",
        "model_id": edited_validation.report.model_id,
        "node_id": node_id,
        "previous_coordinates_m": previous_coordinates_m,
        "edited_coordinates_m": coordinates_m,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NODE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodeEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated neutral node addition in memory.
///
/// # Errors
///
/// Rejects non-finite coordinates, an invalid source model, duplicate node identity or exact
/// coordinates, non-contiguous source indices, schema drift, or edited semantics rejected by C++.
pub fn add_model_node(
    source_bytes: &[u8],
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<ModelNodeAddOutcomeV1, WorkbenchError> {
    validate_node_add_request(source_bytes.len(), node_id, coordinates_m)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let node_index = append_node(&mut edited, node_id, coordinates_m)?;
    bind_node_add_provenance(
        &mut edited,
        node_id,
        node_index,
        coordinates_m,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "node_add",
        "model_id": edited_validation.report.model_id,
        "node_id": node_id,
        "node_index": node_index,
        "coordinates_m": coordinates_m,
        "source_id": null,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NODE_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodeAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedOrphanNodeV1 {
    node_index: usize,
    coordinates_m: [f64; 3],
    extensions: Value,
}

/// Delete one provenance-bound terminal neutral unreferenced orphan node in memory.
///
/// # Errors
///
/// Rejects an invalid source model, missing or non-terminal nodes, source ownership, entity
/// extensions, any element/constraint/load/unsupported-feature/round-trip reference, minimum
/// topology, index drift, schema drift, or edited semantics rejected by C++.
pub fn delete_model_orphan_node(
    source_bytes: &[u8],
    node_id: &str,
) -> Result<ModelOrphanNodeDeleteOutcomeV1, WorkbenchError> {
    validate_orphan_node_delete_request(source_bytes.len(), node_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_orphan_node(&mut edited, node_id)?;
    bind_orphan_node_delete_provenance(
        &mut edited,
        node_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "orphan_node_delete",
        "model_id": edited_validation.report.model_id,
        "removed_node_id": node_id,
        "removed_node_index": removed.node_index,
        "removed_coordinates_m": removed.coordinates_m,
        "removed_source_id": null,
        "removed_extensions": removed.extensions,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": ORPHAN_NODE_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelOrphanNodeDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated nodal-load component edit in memory.
///
/// # Errors
///
/// Rejects non-finite components, an invalid source model, missing load identities, a no-op edit,
/// schema drift introduced by provenance projection, or edited semantics rejected by C++.
pub fn edit_model_nodal_load_components(
    source_bytes: &[u8],
    load_pattern_id: &str,
    nodal_load_id: &str,
    components_si: [f64; 6],
) -> Result<ModelNodalLoadEditOutcomeV1, WorkbenchError> {
    validate_nodal_load_edit_request(
        source_bytes.len(),
        load_pattern_id,
        nodal_load_id,
        components_si,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_components_si =
        replace_nodal_load_components(&mut edited, load_pattern_id, nodal_load_id, components_si)?;
    if previous_components_si
        .iter()
        .zip(components_si)
        .all(|(previous, edited)| {
            normalized_number_bits(*previous) == normalized_number_bits(edited)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited nodal-load components are canonically identical to the source load",
        ));
    }
    bind_nodal_load_edit_provenance(
        &mut edited,
        load_pattern_id,
        nodal_load_id,
        previous_components_si,
        components_si,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "load_pattern", load_pattern_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nodal_load_components",
        "model_id": edited_validation.report.model_id,
        "load_pattern_id": load_pattern_id,
        "nodal_load_id": nodal_load_id,
        "previous_components_si": components_object(previous_components_si),
        "edited_components_si": components_object(components_si),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NODAL_LOAD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodalLoadEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound nodal load to an existing linear-static pattern in memory.
///
/// # Errors
///
/// Rejects invalid identities or components, invalid source semantics, missing patterns or nodes,
/// duplicate load identities, non-linear-static patterns, schema drift, or edited semantics
/// rejected by C++.
pub fn add_model_nodal_load(
    source_bytes: &[u8],
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<ModelNodalLoadAddOutcomeV1, WorkbenchError> {
    validate_nodal_load_add_request(
        source_bytes.len(),
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (load_pattern_index, nodal_load_index) = append_nodal_load(
        &mut edited,
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;
    bind_nodal_load_add_provenance(
        &mut edited,
        load_pattern_id,
        load_pattern_index,
        nodal_load_id,
        nodal_load_index,
        node_id,
        components_si,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "load_pattern", load_pattern_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nodal_load_add",
        "model_id": edited_validation.report.model_id,
        "load_pattern_id": load_pattern_id,
        "load_pattern_index": load_pattern_index,
        "analysis_type": "linear_static",
        "nodal_load_id": nodal_load_id,
        "nodal_load_index": nodal_load_index,
        "node_id": node_id,
        "components_si": components_object(components_si),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NODAL_LOAD_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodalLoadAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedNodalLoadV1 {
    load_pattern_index: usize,
    nodal_load_index: usize,
    node_id: String,
    components_si: Value,
}

/// Delete one last contiguous neutral nonzero nodal load in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal rows, unsupported pattern types,
/// source-owned or malformed loads, unsupported-feature/round-trip ownership, empty retained
/// patterns, schema drift, or edited semantics rejected by the C++ validator.
pub fn delete_model_nodal_load(
    source_bytes: &[u8],
    load_pattern_id: &str,
    nodal_load_id: &str,
) -> Result<ModelNodalLoadDeleteOutcomeV1, WorkbenchError> {
    validate_nodal_load_delete_request(source_bytes.len(), load_pattern_id, nodal_load_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_nodal_load(&mut edited, load_pattern_id, nodal_load_id)?;
    bind_nodal_load_delete_provenance(
        &mut edited,
        load_pattern_id,
        nodal_load_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "load_pattern", load_pattern_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nodal_load_delete",
        "model_id": edited_validation.report.model_id,
        "load_pattern_id": load_pattern_id,
        "load_pattern_index": removed.load_pattern_index,
        "analysis_type": "linear_static",
        "removed_nodal_load_id": nodal_load_id,
        "removed_nodal_load_index": removed.nodal_load_index,
        "removed_node_id": removed.node_id,
        "removed_components_si": removed.components_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NODAL_LOAD_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelNodalLoadDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound homogeneous six-DOF fixed constraint in memory.
///
/// # Errors
///
/// Rejects invalid identities, invalid source semantics, missing or already constrained nodes,
/// duplicate constraint identities, schema drift, or edited semantics rejected by C++.
pub fn add_model_fixed_constraint(
    source_bytes: &[u8],
    constraint_id: &str,
    node_id: &str,
) -> Result<ModelFixedConstraintAddOutcomeV1, WorkbenchError> {
    validate_fixed_constraint_add_request(source_bytes.len(), constraint_id, node_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let constraint_index = append_fixed_constraint(&mut edited, constraint_id, node_id)?;
    bind_fixed_constraint_add_provenance(
        &mut edited,
        constraint_id,
        constraint_index,
        node_id,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "fixed_constraint_add",
        "model_id": edited_validation.report.model_id,
        "constraint_id": constraint_id,
        "constraint_index": constraint_index,
        "constraint_type": "fixed_dofs",
        "node_id": node_id,
        "dofs": DOF_KEYS,
        "prescribed_values_si": fixed_constraint_values_object(),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FIXED_CONSTRAINT_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFixedConstraintAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedFixedConstraintV1 {
    constraint_index: usize,
    node_id: String,
    dofs: Value,
    prescribed_values_si: Value,
}

/// Delete one last contiguous neutral homogeneous six-DOF fixed constraint in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal rows, source-owned, partial or
/// nonzero constraints, construction-stage/unsupported-feature/round-trip references, schema
/// drift, or edited semantics rejected by the C++ validator.
pub fn delete_model_fixed_constraint(
    source_bytes: &[u8],
    constraint_id: &str,
) -> Result<ModelFixedConstraintDeleteOutcomeV1, WorkbenchError> {
    validate_fixed_constraint_delete_request(source_bytes.len(), constraint_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_fixed_constraint(&mut edited, constraint_id)?;
    bind_fixed_constraint_delete_provenance(
        &mut edited,
        constraint_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "fixed_constraint_delete",
        "model_id": edited_validation.report.model_id,
        "removed_constraint_id": constraint_id,
        "removed_constraint_index": removed.constraint_index,
        "removed_constraint_type": "fixed_dofs",
        "removed_node_id": removed.node_id,
        "removed_dofs": removed.dofs,
        "removed_prescribed_values_si": removed.prescribed_values_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FIXED_CONSTRAINT_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFixedConstraintDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound linear-static load pattern and first nodal load in memory.
///
/// # Errors
///
/// Rejects invalid identities/components, invalid source semantics, missing nodes, duplicate
/// pattern or nested-load identities, schema drift, or edited semantics rejected by C++.
pub fn add_model_linear_load_pattern(
    source_bytes: &[u8],
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<ModelLinearLoadPatternAddOutcomeV1, WorkbenchError> {
    validate_linear_load_pattern_add_request(
        source_bytes.len(),
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let load_pattern_index = append_linear_load_pattern(
        &mut edited,
        load_pattern_id,
        nodal_load_id,
        node_id,
        components_si,
    )?;
    bind_linear_load_pattern_add_provenance(
        &mut edited,
        load_pattern_id,
        load_pattern_index,
        nodal_load_id,
        node_id,
        components_si,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_load_pattern_add",
        "model_id": edited_validation.report.model_id,
        "load_pattern_id": load_pattern_id,
        "load_pattern_index": load_pattern_index,
        "analysis_type": "linear_static",
        "self_weight": [0, 0, 0],
        "nodal_load_id": nodal_load_id,
        "nodal_load_index": 0,
        "node_id": node_id,
        "components_si": components_object(components_si),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_LOAD_PATTERN_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadPatternAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound two-to-64-pattern direct linear load combination in memory.
///
/// # Errors
///
/// Rejects invalid identities or factors, invalid source semantics, duplicate or missing pattern
/// references, duplicate combination identities, schema drift, or edited semantics rejected by
/// C++.
pub fn add_model_linear_load_combination(
    source_bytes: &[u8],
    load_combination_id: &str,
    terms: &[LinearLoadCombinationTermV1],
) -> Result<ModelLinearLoadCombinationAddOutcomeV1, WorkbenchError> {
    validate_linear_load_combination_add_request(source_bytes.len(), load_combination_id, terms)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let load_combination_index =
        append_linear_load_combination(&mut edited, load_combination_id, terms)?;
    bind_linear_load_combination_add_provenance(
        &mut edited,
        load_combination_id,
        load_combination_index,
        terms,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = if terms.len() == 2 {
        canonical_self_hashed(json!({
            "schema_version": EDIT_SCHEMA_V1,
            "operation": "linear_load_combination_add",
            "model_id": edited_validation.report.model_id,
            "load_combination_id": load_combination_id,
            "load_combination_index": load_combination_index,
            "combination_type": "linear",
            "terms": linear_load_combination_terms_value(terms),
            "source_input_sha256": source_input_sha256,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "edited_content_hash": edited_validation.report.content_hash,
            "edited_semantic_hash": edited_validation.report.semantic_hash,
            "edited_provenance_hash": edited_validation.report.provenance_hash,
            "cpp_semantic_snapshot_verified": true,
            "analysis_ready": edited_validation.report.analysis_ready,
            "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
            "artifacts": [model_artifact],
            "claim_boundary": LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY,
        }))?
    } else {
        canonical_self_hashed(json!({
            "schema_version": EDIT_SCHEMA_V1,
            "operation": "direct_linear_load_combination_add",
            "authoring_profile": "unique_direct_linear_static_patterns_2_to_64",
            "model_id": edited_validation.report.model_id,
            "load_combination_id": load_combination_id,
            "load_combination_index": load_combination_index,
            "combination_type": "linear",
            "term_count": terms.len(),
            "terms": linear_load_combination_terms_value(terms),
            "source_input_sha256": source_input_sha256,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "edited_content_hash": edited_validation.report.content_hash,
            "edited_semantic_hash": edited_validation.report.semantic_hash,
            "edited_provenance_hash": edited_validation.report.provenance_hash,
            "cpp_semantic_snapshot_verified": true,
            "analysis_ready": edited_validation.report.analysis_ready,
            "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
            "artifacts": [model_artifact],
            "claim_boundary": DIRECT_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY,
        }))?
    };
    Ok(ModelLinearLoadCombinationAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Edit one existing factor in a provenance-bound direct linear load combination in memory.
///
/// # Errors
///
/// Rejects invalid identities or factors, invalid source semantics, source-owned, extended,
/// referenced, nested, unsupported-feature-owned or round-trip-owned combinations, malformed or
/// missing direct pattern terms, no-op edits, schema drift, or edited semantics rejected by C++.
pub fn edit_model_direct_linear_load_combination_factor(
    source_bytes: &[u8],
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: f64,
) -> Result<ModelLinearLoadCombinationFactorEditOutcomeV1, WorkbenchError> {
    validate_direct_linear_load_combination_factor_edit_request(
        source_bytes.len(),
        load_combination_id,
        load_pattern_id,
        factor,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let factor_edit = replace_direct_linear_load_combination_factor(
        &mut edited,
        load_combination_id,
        load_pattern_id,
        factor,
    )?;
    if normalized_number_bits(factor_edit.previous_factor) == normalized_number_bits(factor) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited load-combination factor is canonically identical to the source term",
        ));
    }
    bind_direct_linear_load_combination_factor_edit_provenance(
        &mut edited,
        load_combination_id,
        load_pattern_id,
        &factor_edit,
        factor,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "direct_linear_load_combination_factor_edit",
        "editing_profile": "unique_direct_linear_static_patterns_2_to_64",
        "model_id": edited_validation.report.model_id,
        "load_combination_id": load_combination_id,
        "load_combination_index": factor_edit.load_combination_index,
        "combination_type": "linear",
        "load_pattern_id": load_pattern_id,
        "term_index": factor_edit.term_index,
        "term_count": factor_edit.edited_terms.as_array().map_or(0, Vec::len),
        "previous_factor": factor_edit.previous_factor,
        "edited_factor": factor,
        "edited_terms": factor_edit.edited_terms,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadCombinationFactorEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Replace one existing pattern reference in a provenance-bound direct linear load combination.
///
/// # Errors
///
/// Rejects invalid identities, invalid source semantics, source-owned, extended, referenced,
/// nested, unsupported-feature-owned or round-trip-owned combinations, malformed or missing
/// direct pattern terms, missing/nonlinear/duplicate replacement patterns, no-op edits, schema
/// drift, or edited semantics rejected by C++.
pub fn edit_model_direct_linear_load_combination_reference(
    source_bytes: &[u8],
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
) -> Result<ModelLinearLoadCombinationReferenceEditOutcomeV1, WorkbenchError> {
    validate_direct_linear_load_combination_reference_edit_request(
        source_bytes.len(),
        load_combination_id,
        load_pattern_id,
        replacement_load_pattern_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let reference_edit = replace_direct_linear_load_combination_reference(
        &mut edited,
        load_combination_id,
        load_pattern_id,
        replacement_load_pattern_id,
    )?;
    bind_direct_linear_load_combination_reference_edit_provenance(
        &mut edited,
        load_combination_id,
        load_pattern_id,
        replacement_load_pattern_id,
        &reference_edit,
        SourceModelHashesV1 {
            content: &source_content_hash,
            semantic: &source_semantic_hash,
            provenance: &source_provenance_hash,
        },
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the reference-edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "direct_linear_load_combination_reference_edit",
        "editing_profile": "unique_direct_linear_static_patterns_2_to_64",
        "model_id": edited_validation.report.model_id,
        "load_combination_id": load_combination_id,
        "load_combination_index": reference_edit.load_combination_index,
        "combination_type": "linear",
        "load_pattern_id": load_pattern_id,
        "replacement_load_pattern_id": replacement_load_pattern_id,
        "term_index": reference_edit.term_index,
        "term_count": reference_edit.edited_terms.as_array().map_or(0, Vec::len),
        "preserved_factor": reference_edit.preserved_factor,
        "source_terms": reference_edit.source_terms,
        "edited_terms": reference_edit.edited_terms,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadCombinationReferenceEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Edit one existing typed root factor in a provenance-bound nested linear load combination.
///
/// # Errors
///
/// Rejects invalid identities or factors, invalid source semantics, source-owned, extended,
/// referenced, direct, unsupported-feature-owned or round-trip-owned combinations, malformed or
/// missing typed root terms, no-op edits, depth/expansion overflow, schema drift, or edited
/// semantics rejected by C++.
#[allow(clippy::too_many_lines)]
pub fn edit_model_nested_linear_load_combination_factor(
    source_bytes: &[u8],
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    factor: f64,
) -> Result<ModelLinearLoadCombinationFactorEditOutcomeV1, WorkbenchError> {
    validate_nested_linear_load_combination_factor_edit_request(
        source_bytes.len(),
        load_combination_id,
        reference_id,
        factor,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let factor_edit = replace_nested_linear_load_combination_factor(
        &mut edited,
        load_combination_id,
        reference_kind,
        reference_id,
        factor,
    )?;
    if normalized_number_bits(factor_edit.previous_factor) == normalized_number_bits(factor) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited nested load-combination factor is canonically identical to the source term",
        ));
    }
    bind_nested_linear_load_combination_factor_edit_provenance(
        &mut edited,
        load_combination_id,
        reference_kind,
        reference_id,
        &factor_edit,
        factor,
        SourceModelHashesV1 {
            content: &source_content_hash,
            semantic: &source_semantic_hash,
            provenance: &source_provenance_hash,
        },
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited nested-combination ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let source_expanded_pattern_count = factor_edit
        .source_expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len);
    let edited_expanded_pattern_count = factor_edit
        .edited_expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len);
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nested_linear_load_combination_factor_edit",
        "editing_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
        "model_id": edited_validation.report.model_id,
        "load_combination_id": load_combination_id,
        "load_combination_index": factor_edit.load_combination_index,
        "combination_type": "linear",
        "reference_kind": reference_kind.as_str(),
        "reference_id": reference_id,
        "term_index": factor_edit.term_index,
        "term_count": factor_edit.edited_expansion.root_terms.as_array().map_or(0, Vec::len),
        "previous_factor": factor_edit.previous_factor,
        "edited_factor": factor,
        "source_terms": factor_edit.source_expansion.root_terms,
        "edited_terms": factor_edit.edited_expansion.root_terms,
        "source_combination_depth": factor_edit.source_expansion.max_depth,
        "source_expanded_term_count": factor_edit.source_expansion.expanded_term_count,
        "source_expanded_pattern_count": source_expanded_pattern_count,
        "source_expanded_pattern_terms": factor_edit.source_expansion.expanded_pattern_terms,
        "edited_combination_depth": factor_edit.edited_expansion.max_depth,
        "edited_expanded_term_count": factor_edit.edited_expansion.expanded_term_count,
        "edited_expanded_pattern_count": edited_expanded_pattern_count,
        "edited_expanded_pattern_terms": factor_edit.edited_expansion.expanded_pattern_terms,
        "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
        "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadCombinationFactorEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Replace one existing typed root reference in a provenance-bound nested linear load
/// combination.
///
/// # Errors
///
/// Rejects invalid identities, invalid source semantics, source-owned, extended, referenced,
/// direct, unsupported-feature-owned or round-trip-owned roots, malformed, missing or duplicate
/// typed references, no-op edits, cycles, direct degradation, depth/expansion overflow, schema
/// drift, or edited semantics rejected by C++.
#[allow(clippy::too_many_lines)]
pub fn edit_model_nested_linear_load_combination_reference(
    source_bytes: &[u8],
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    replacement_reference_kind: LinearLoadCombinationReferenceKindV1,
    replacement_reference_id: &str,
) -> Result<ModelLinearLoadCombinationReferenceEditOutcomeV1, WorkbenchError> {
    validate_nested_linear_load_combination_reference_edit_request(
        source_bytes.len(),
        load_combination_id,
        reference_id,
        replacement_reference_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let reference_edit = replace_nested_linear_load_combination_reference(
        &mut edited,
        load_combination_id,
        reference_kind,
        reference_id,
        replacement_reference_kind,
        replacement_reference_id,
    )?;
    bind_nested_linear_load_combination_reference_edit_provenance(
        &mut edited,
        load_combination_id,
        reference_kind,
        reference_id,
        replacement_reference_kind,
        replacement_reference_id,
        &reference_edit,
        SourceModelHashesV1 {
            content: &source_content_hash,
            semantic: &source_semantic_hash,
            provenance: &source_provenance_hash,
        },
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the reference-edited nested-combination ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let source_expanded_pattern_count = reference_edit
        .source_expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len);
    let edited_expanded_pattern_count = reference_edit
        .edited_expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len);
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nested_linear_load_combination_reference_edit",
        "editing_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
        "model_id": edited_validation.report.model_id,
        "load_combination_id": load_combination_id,
        "load_combination_index": reference_edit.load_combination_index,
        "combination_type": "linear",
        "reference_kind": reference_kind.as_str(),
        "reference_id": reference_id,
        "replacement_reference_kind": replacement_reference_kind.as_str(),
        "replacement_reference_id": replacement_reference_id,
        "term_index": reference_edit.term_index,
        "term_count": reference_edit.edited_expansion.root_terms.as_array().map_or(0, Vec::len),
        "preserved_factor": reference_edit.preserved_factor,
        "source_terms": reference_edit.source_expansion.root_terms,
        "edited_terms": reference_edit.edited_expansion.root_terms,
        "source_combination_depth": reference_edit.source_expansion.max_depth,
        "source_expanded_term_count": reference_edit.source_expansion.expanded_term_count,
        "source_expanded_pattern_count": source_expanded_pattern_count,
        "source_expanded_pattern_terms": reference_edit.source_expansion.expanded_pattern_terms,
        "edited_combination_depth": reference_edit.edited_expansion.max_depth,
        "edited_expanded_term_count": reference_edit.edited_expansion.expanded_term_count,
        "edited_expanded_pattern_count": edited_expanded_pattern_count,
        "edited_expanded_pattern_terms": reference_edit.edited_expansion.expanded_pattern_terms,
        "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
        "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadCombinationReferenceEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound bounded acyclic nested linear load combination in memory.
///
/// # Errors
///
/// Rejects invalid identities or factors, invalid source semantics, duplicate or missing typed
/// references, cycles, depth/expansion overflow, schema drift, or edited semantics rejected by
/// C++.
pub fn add_model_nested_linear_load_combination(
    source_bytes: &[u8],
    load_combination_id: &str,
    terms: &[NestedLinearLoadCombinationTermV1],
) -> Result<ModelLinearLoadCombinationAddOutcomeV1, WorkbenchError> {
    validate_nested_linear_load_combination_add_request(
        source_bytes.len(),
        load_combination_id,
        terms,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let load_combination_index =
        append_nested_linear_load_combination(&mut edited, load_combination_id, terms)?;
    let expansion = require_bounded_linear_load_combination(&edited, load_combination_id)?;
    bind_nested_linear_load_combination_add_provenance(
        &mut edited,
        load_combination_id,
        load_combination_index,
        terms,
        &expansion,
        SourceModelHashesV1 {
            content: &source_content_hash,
            semantic: &source_semantic_hash,
            provenance: &source_provenance_hash,
        },
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited nested-combination ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let expanded_pattern_count = expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len);
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "nested_linear_load_combination_add",
        "authoring_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
        "model_id": edited_validation.report.model_id,
        "load_combination_id": load_combination_id,
        "load_combination_index": load_combination_index,
        "combination_type": "linear",
        "term_count": terms.len(),
        "terms": nested_linear_load_combination_terms_value(terms),
        "combination_depth": expansion.max_depth,
        "expanded_term_count": expansion.expanded_term_count,
        "expanded_pattern_count": expanded_pattern_count,
        "expanded_pattern_terms": expansion.expanded_pattern_terms,
        "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
        "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadCombinationAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LinearLoadCombinationDeletionProfileV1 {
    ExactTwoV1,
    DirectV2,
    NestedV3,
}

#[derive(Clone, Debug, PartialEq)]
struct DirectLinearLoadCombinationFactorEditV1 {
    load_combination_index: usize,
    term_index: usize,
    previous_factor: f64,
    edited_terms: Value,
}

#[derive(Clone, Debug, PartialEq)]
struct DirectLinearLoadCombinationReferenceEditV1 {
    load_combination_index: usize,
    term_index: usize,
    preserved_factor: f64,
    source_terms: Value,
    edited_terms: Value,
}

#[derive(Clone, Debug, PartialEq)]
struct NestedLinearLoadCombinationFactorEditV1 {
    load_combination_index: usize,
    term_index: usize,
    previous_factor: f64,
    source_expansion: ExpandedLinearLoadCombinationV1,
    edited_expansion: ExpandedLinearLoadCombinationV1,
}

#[derive(Clone, Debug, PartialEq)]
struct NestedLinearLoadCombinationReferenceEditV1 {
    load_combination_index: usize,
    term_index: usize,
    preserved_factor: f64,
    source_expansion: ExpandedLinearLoadCombinationV1,
    edited_expansion: ExpandedLinearLoadCombinationV1,
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedLinearLoadCombinationV1 {
    load_combination_index: usize,
    terms: Value,
    profile: LinearLoadCombinationDeletionProfileV1,
    expansion: Option<ExpandedLinearLoadCombinationV1>,
}

/// Delete one provenance-bound terminal neutral bounded direct or nested linear combination in
/// memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal combinations, source-owned or
/// malformed rows, out-of-profile nested graphs, unsupported-feature or round-trip ownership,
/// schema drift, or edited semantics rejected by the C++ validator.
pub fn delete_model_linear_load_combination(
    source_bytes: &[u8],
    load_combination_id: &str,
) -> Result<ModelLinearLoadCombinationDeleteOutcomeV1, WorkbenchError> {
    validate_linear_load_combination_delete_request(source_bytes.len(), load_combination_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_linear_load_combination(&mut edited, load_combination_id)?;
    bind_linear_load_combination_delete_provenance(
        &mut edited,
        load_combination_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let mut receipt = json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_load_combination_delete",
        "model_id": edited_validation.report.model_id,
        "removed_load_combination_id": load_combination_id,
        "removed_load_combination_index": removed.load_combination_index,
        "removed_combination_type": "linear",
        "removed_terms": removed.terms,
        "removed_source_id": null,
        "removed_extensions": {},
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY,
    });
    if removed.profile == LinearLoadCombinationDeletionProfileV1::DirectV2 {
        receipt["operation"] = json!("direct_linear_load_combination_delete");
        receipt["deletion_profile"] = json!("unique_direct_linear_static_patterns_2_to_64");
        receipt["term_count"] = json!(removed.terms.as_array().map_or(0, Vec::len));
        receipt["claim_boundary"] = json!(DIRECT_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY);
    } else if removed.profile == LinearLoadCombinationDeletionProfileV1::NestedV3 {
        receipt["operation"] = json!("nested_linear_load_combination_delete");
        bind_nested_linear_load_combination_delete_fields(&mut receipt, &removed)?;
        receipt["claim_boundary"] = json!(NESTED_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY);
    }
    let receipt_json = canonical_self_hashed(receipt)?;
    Ok(ModelLinearLoadCombinationDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedLinearLoadPatternV1 {
    load_pattern_index: usize,
    nodal_load_id: String,
    node_id: String,
    components_si: Value,
}

/// Delete one provenance-bound terminal neutral linear-static pattern in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal patterns, source-owned or malformed
/// pattern/load rows, nonzero self weight, combination or stage references, unsupported-feature
/// or round-trip ownership, schema drift, or edited semantics rejected by the C++ validator.
pub fn delete_model_linear_load_pattern(
    source_bytes: &[u8],
    load_pattern_id: &str,
) -> Result<ModelLinearLoadPatternDeleteOutcomeV1, WorkbenchError> {
    validate_linear_load_pattern_delete_request(source_bytes.len(), load_pattern_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_linear_load_pattern(&mut edited, load_pattern_id)?;
    bind_linear_load_pattern_delete_provenance(
        &mut edited,
        load_pattern_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_load_pattern_delete",
        "model_id": edited_validation.report.model_id,
        "removed_load_pattern_id": load_pattern_id,
        "removed_load_pattern_index": removed.load_pattern_index,
        "removed_analysis_type": "linear_static",
        "removed_self_weight": [0, 0, 0],
        "removed_nodal_load_id": removed.nodal_load_id,
        "removed_nodal_load_index": 0,
        "removed_node_id": removed.node_id,
        "removed_components_si": removed.components_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_LOAD_PATTERN_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearLoadPatternDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound v1 linear-elastic isotropic material in memory.
///
/// # Errors
///
/// Rejects invalid identity/parameters, invalid source semantics, duplicate material identity,
/// schema drift, or edited semantics rejected by C++.
pub fn add_model_linear_material(
    source_bytes: &[u8],
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<ModelLinearMaterialAddOutcomeV1, WorkbenchError> {
    validate_linear_material_add_request(source_bytes.len(), material_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let material_index = append_linear_material(&mut edited, material_id, parameters)?;
    bind_linear_material_add_provenance(
        &mut edited,
        material_id,
        material_index,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_material_add",
        "model_id": edited_validation.report.model_id,
        "material_id": material_id,
        "material_index": material_index,
        "law_id": "linear_elastic_isotropic",
        "parameter_set_version": "1",
        "parameters_si": linear_material_parameters_object(parameters),
        "state_schema": linear_material_state_schema_object(),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_MATERIAL_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearMaterialAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedLinearMaterialV1 {
    material_index: usize,
    parameters_si: Value,
    state_schema: Value,
}

/// Delete one provenance-bound terminal neutral v1 linear material in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal materials, source-owned or malformed
/// rows, element or section references, unsupported-feature or round-trip ownership, schema drift,
/// or edited semantics rejected by the C++ validator.
pub fn delete_model_linear_material(
    source_bytes: &[u8],
    material_id: &str,
) -> Result<ModelLinearMaterialDeleteOutcomeV1, WorkbenchError> {
    validate_linear_material_delete_request(source_bytes.len(), material_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_linear_material(&mut edited, material_id)?;
    bind_linear_material_delete_provenance(
        &mut edited,
        material_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_material_delete",
        "model_id": edited_validation.report.model_id,
        "removed_material_id": material_id,
        "removed_material_index": removed.material_index,
        "removed_law_id": "linear_elastic_isotropic",
        "removed_parameter_set_version": "1",
        "removed_parameters_si": removed.parameters_si,
        "removed_state_schema": removed.state_schema,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_MATERIAL_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearMaterialDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound v1 `frame_3d` section in memory.
///
/// # Errors
///
/// Rejects invalid identity/parameters, invalid source semantics, duplicate section identity,
/// schema drift, or edited semantics rejected by C++.
pub fn add_model_frame_section(
    source_bytes: &[u8],
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<ModelFrameSectionAddOutcomeV1, WorkbenchError> {
    validate_frame_section_add_request(source_bytes.len(), section_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let section_index = append_frame_section(&mut edited, section_id, parameters)?;
    bind_frame_section_add_provenance(
        &mut edited,
        section_id,
        section_index,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame_section_add",
        "model_id": edited_validation.report.model_id,
        "section_id": section_id,
        "section_index": section_index,
        "family_id": "frame_3d",
        "parameter_set_version": "1",
        "parameters_si": frame_section_parameters_object(parameters),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME_SECTION_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrameSectionAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedFrameSectionV1 {
    section_index: usize,
    parameters_si: Value,
}

/// Delete one provenance-bound terminal neutral v1 frame section in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal sections, source-owned or malformed
/// rows, element references, unsupported-feature or round-trip ownership, schema drift, or edited
/// semantics rejected by the C++ validator.
pub fn delete_model_frame_section(
    source_bytes: &[u8],
    section_id: &str,
) -> Result<ModelFrameSectionDeleteOutcomeV1, WorkbenchError> {
    validate_frame_section_delete_request(source_bytes.len(), section_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_frame_section(&mut edited, section_id)?;
    bind_frame_section_delete_provenance(
        &mut edited,
        section_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame_section_delete",
        "model_id": edited_validation.report.model_id,
        "removed_section_id": section_id,
        "removed_section_index": removed.section_index,
        "removed_family_id": "frame_3d",
        "removed_parameter_set_version": "1",
        "removed_parameters_si": removed.parameters_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME_SECTION_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrameSectionDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound v1 `truss_3d` section in memory.
///
/// # Errors
///
/// Rejects invalid identity/area, invalid source semantics, duplicate section identity, schema
/// drift, or edited semantics rejected by C++.
pub fn add_model_truss_section(
    source_bytes: &[u8],
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<ModelTrussSectionAddOutcomeV1, WorkbenchError> {
    validate_truss_section_add_request(source_bytes.len(), section_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let section_index = append_truss_section(&mut edited, section_id, parameters)?;
    bind_truss_section_add_provenance(
        &mut edited,
        section_id,
        section_index,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss_section_add",
        "model_id": edited_validation.report.model_id,
        "section_id": section_id,
        "section_index": section_index,
        "family_id": "truss_3d",
        "parameter_set_version": "1",
        "parameters_si": truss_section_parameters_object(parameters),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS_SECTION_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTrussSectionAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedTrussSectionV1 {
    section_index: usize,
    parameters_si: Value,
}

/// Delete one provenance-bound terminal neutral v1 truss section in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal sections, source-owned or malformed
/// rows, element references, unsupported-feature or round-trip ownership, removal of the last
/// truss section, schema drift, or edited semantics rejected by the C++ validator.
pub fn delete_model_truss_section(
    source_bytes: &[u8],
    section_id: &str,
) -> Result<ModelTrussSectionDeleteOutcomeV1, WorkbenchError> {
    validate_truss_section_delete_request(source_bytes.len(), section_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_truss_section(&mut edited, section_id)?;
    bind_truss_section_delete_provenance(
        &mut edited,
        section_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss_section_delete",
        "model_id": edited_validation.report.model_id,
        "removed_section_id": section_id,
        "removed_section_index": removed.section_index,
        "removed_family_id": "truss_3d",
        "removed_parameter_set_version": "1",
        "removed_parameters_si": removed.parameters_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS_SECTION_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTrussSectionDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated prescribed-constraint-value edit in memory.
///
/// # Errors
///
/// Rejects an unknown DOF, non-finite value, invalid source model, missing constraint, unrestrained
/// DOF, no-op edit, schema drift, or edited semantics rejected by C++.
pub fn edit_model_constraint_value(
    source_bytes: &[u8],
    constraint_id: &str,
    dof: &str,
    value_si: f64,
) -> Result<ModelConstraintValueEditOutcomeV1, WorkbenchError> {
    validate_constraint_value_edit_request(source_bytes.len(), constraint_id, dof, value_si)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_value_si = replace_constraint_value(&mut edited, constraint_id, dof, value_si)?;
    if normalized_number_bits(previous_value_si) == normalized_number_bits(value_si) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited prescribed value is canonically identical to the source constraint",
        ));
    }
    bind_constraint_value_edit_provenance(
        &mut edited,
        constraint_id,
        dof,
        previous_value_si,
        value_si,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "constraint", constraint_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "constraint_prescribed_value",
        "model_id": edited_validation.report.model_id,
        "constraint_id": constraint_id,
        "dof": dof,
        "unit": constraint_value_unit(dof),
        "previous_value_si": previous_value_si,
        "edited_value_si": value_si,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": CONSTRAINT_VALUE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelConstraintValueEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated linear-elastic material edit in memory.
///
/// # Errors
///
/// Rejects invalid parameters, an invalid source model, missing material identity, any law or
/// parameter-set version outside the closed v1 surface, a no-op edit, schema drift, or edited
/// semantics rejected by C++.
pub fn edit_model_linear_material(
    source_bytes: &[u8],
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<ModelLinearMaterialEditOutcomeV1, WorkbenchError> {
    validate_linear_material_edit_request(source_bytes.len(), material_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_parameters =
        replace_linear_material_parameters(&mut edited, material_id, parameters)?;
    if linear_material_parameters_equal(previous_parameters, parameters) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited material parameters are canonically identical to the source material",
        ));
    }
    bind_linear_material_edit_provenance(
        &mut edited,
        material_id,
        previous_parameters,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "material", material_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "linear_elastic_material_parameters",
        "model_id": edited_validation.report.model_id,
        "material_id": material_id,
        "law_id": "linear_elastic_isotropic",
        "parameter_set_version": "1",
        "previous_parameters_si": linear_material_parameters_object(previous_parameters),
        "edited_parameters_si": linear_material_parameters_object(parameters),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": LINEAR_MATERIAL_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelLinearMaterialEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated `frame_3d` section edit in memory.
///
/// # Errors
///
/// Rejects invalid parameters, an invalid source model, missing section identity, any family or
/// parameter-set version outside the closed v1 surface, a no-op edit, schema drift, or edited
/// semantics rejected by C++.
pub fn edit_model_frame_section(
    source_bytes: &[u8],
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<ModelFrameSectionEditOutcomeV1, WorkbenchError> {
    validate_frame_section_edit_request(source_bytes.len(), section_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_parameters =
        replace_frame_section_parameters(&mut edited, section_id, parameters)?;
    if frame_section_parameters_equal(previous_parameters, parameters) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited section parameters are canonically identical to the source section",
        ));
    }
    bind_frame_section_edit_provenance(
        &mut edited,
        section_id,
        previous_parameters,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "section", section_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame_section_parameters",
        "model_id": edited_validation.report.model_id,
        "section_id": section_id,
        "family_id": "frame_3d",
        "parameter_set_version": "1",
        "previous_parameters_si": frame_section_parameters_object(previous_parameters),
        "edited_parameters_si": frame_section_parameters_object(parameters),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME_SECTION_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrameSectionEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated `truss_3d` section edit in memory.
///
/// # Errors
///
/// Rejects invalid area, an invalid source model, missing section identity, any family or
/// parameter-set version outside the closed v1 surface, a no-op edit, schema drift, or edited
/// semantics rejected by C++.
pub fn edit_model_truss_section(
    source_bytes: &[u8],
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<ModelTrussSectionEditOutcomeV1, WorkbenchError> {
    validate_truss_section_edit_request(source_bytes.len(), section_id, parameters)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let previous_parameters =
        replace_truss_section_parameters(&mut edited, section_id, parameters)?;
    if normalized_number_bits(previous_parameters.area_m2)
        == normalized_number_bits(parameters.area_m2)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited truss-section area is canonically identical to the source section",
        ));
    }
    bind_truss_section_edit_provenance(
        &mut edited,
        section_id,
        previous_parameters,
        parameters,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "section", section_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss_section_parameters",
        "model_id": edited_validation.report.model_id,
        "section_id": section_id,
        "family_id": "truss_3d",
        "parameter_set_version": "1",
        "previous_parameters_si": truss_section_parameters_object(previous_parameters),
        "edited_parameters_si": truss_section_parameters_object(parameters),
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS_SECTION_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTrussSectionEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated frame-element local-axis rotation edit.
///
/// # Errors
///
/// Rejects non-finite radians, an invalid source model, a missing element, a non-`frame_3d`
/// element, a no-op edit, schema drift, or edited semantics rejected by C++.
pub fn edit_model_frame_element_orientation(
    source_bytes: &[u8],
    element_id: &str,
    local_axis_rotation_rad: f64,
) -> Result<ModelFrameElementOrientationEditOutcomeV1, WorkbenchError> {
    validate_frame_element_orientation_edit_request(
        source_bytes.len(),
        element_id,
        local_axis_rotation_rad,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (previous_local_axis_rotation_rad, formulation) =
        replace_frame_element_orientation(&mut edited, element_id, local_axis_rotation_rad)?;
    if normalized_number_bits(previous_local_axis_rotation_rad)
        == normalized_number_bits(local_axis_rotation_rad)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited local-axis rotation is canonically identical to the source element",
        ));
    }
    bind_frame_element_orientation_edit_provenance(
        &mut edited,
        element_id,
        &formulation,
        previous_local_axis_rotation_rad,
        local_axis_rotation_rad,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "element", element_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame_element_local_axis_rotation",
        "model_id": edited_validation.report.model_id,
        "element_id": element_id,
        "element_type": "frame_3d",
        "formulation": formulation,
        "previous_local_axis_rotation_rad": previous_local_axis_rotation_rad,
        "edited_local_axis_rotation_rad": local_axis_rotation_rad,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME_ELEMENT_ORIENTATION_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrameElementOrientationEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated frame-element property-reference edit.
///
/// # Errors
///
/// Rejects invalid identities, an invalid source model, a missing or non-`frame_3d` element,
/// missing or incompatible v1 property references, a complete no-op, schema drift, or edited
/// semantics rejected by C++.
pub fn edit_model_frame_element_properties(
    source_bytes: &[u8],
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<ModelFrameElementPropertiesEditOutcomeV1, WorkbenchError> {
    validate_frame_element_properties_edit_request(
        source_bytes.len(),
        element_id,
        material_id,
        section_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (previous_material_id, previous_section_id, formulation) =
        replace_frame_element_properties(&mut edited, element_id, material_id, section_id)?;
    if previous_material_id == material_id && previous_section_id == section_id {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited material and section references are identical to the source element",
        ));
    }
    bind_frame_element_properties_edit_provenance(
        &mut edited,
        element_id,
        &formulation,
        &previous_material_id,
        material_id,
        &previous_section_id,
        section_id,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "element", element_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame_element_properties",
        "model_id": edited_validation.report.model_id,
        "element_id": element_id,
        "element_type": "frame_3d",
        "formulation": formulation,
        "previous_material_id": previous_material_id,
        "edited_material_id": material_id,
        "previous_section_id": previous_section_id,
        "edited_section_id": section_id,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME_ELEMENT_PROPERTIES_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrameElementPropertiesEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated truss-element property-reference edit.
///
/// # Errors
///
/// Rejects invalid identities, an invalid source model, a missing or non-`truss_3d` element,
/// missing or incompatible v1 property references, a complete no-op, schema drift, or edited
/// semantics rejected by C++.
pub fn edit_model_truss_element_properties(
    source_bytes: &[u8],
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<ModelTrussElementPropertiesEditOutcomeV1, WorkbenchError> {
    validate_truss_element_properties_edit_request(
        source_bytes.len(),
        element_id,
        material_id,
        section_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (previous_material_id, previous_section_id, formulation) =
        replace_truss_element_properties(&mut edited, element_id, material_id, section_id)?;
    if previous_material_id == material_id && previous_section_id == section_id {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited material and section references are identical to the source truss element",
        ));
    }
    bind_truss_element_properties_edit_provenance(
        &mut edited,
        element_id,
        &formulation,
        &previous_material_id,
        material_id,
        &previous_section_id,
        section_id,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "element", element_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss_element_properties",
        "model_id": edited_validation.report.model_id,
        "element_id": element_id,
        "element_type": "truss_3d",
        "formulation": formulation,
        "previous_material_id": previous_material_id,
        "edited_material_id": material_id,
        "previous_section_id": previous_section_id,
        "edited_section_id": section_id,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS_ELEMENT_PROPERTIES_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTrussElementPropertiesEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Produce one provenance-bound, C++-revalidated two-node element connectivity edit.
///
/// # Errors
///
/// Rejects invalid identities, identical endpoints, an invalid source model, a missing element or
/// endpoint node, a no-op edit, schema drift, or edited semantics rejected by C++.
pub fn edit_model_element_connectivity(
    source_bytes: &[u8],
    element_id: &str,
    node_ids: [&str; 2],
) -> Result<ModelElementConnectivityEditOutcomeV1, WorkbenchError> {
    validate_element_connectivity_edit_request(source_bytes.len(), element_id, node_ids)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (previous_node_ids, element_type, formulation) =
        replace_element_connectivity(&mut edited, element_id, node_ids)?;
    let edited_node_ids = [node_ids[0].to_owned(), node_ids[1].to_owned()];
    if previous_node_ids == edited_node_ids {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "edited connectivity is canonically identical to the source element",
        ));
    }
    bind_element_connectivity_edit_provenance(
        &mut edited,
        element_id,
        &element_type,
        &formulation,
        &previous_node_ids,
        &edited_node_ids,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;
    mark_roundtrip_entity_approximated(&mut edited, "element", element_id)?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "element_connectivity",
        "model_id": edited_validation.report.model_id,
        "element_id": element_id,
        "element_type": element_type,
        "formulation": formulation,
        "previous_node_ids": previous_node_ids,
        "edited_node_ids": edited_node_ids,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": ELEMENT_CONNECTIVITY_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelElementConnectivityEditOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound node and connected linear `frame_3d` member in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, duplicate identities or coordinates, missing or unsupported
/// references, schema drift, or edited topology rejected by the C++ semantic validator.
#[allow(clippy::too_many_arguments)]
pub fn add_model_frame3d_member(
    source_bytes: &[u8],
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<ModelFrame3dMemberAddOutcomeV1, WorkbenchError> {
    validate_frame3d_member_add_request(
        source_bytes.len(),
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (node_index, element_index) = append_frame3d_member(
        &mut edited,
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;
    bind_frame3d_member_add_provenance(
        &mut edited,
        node_id,
        node_index,
        coordinates_m,
        element_id,
        element_index,
        from_node_id,
        material_id,
        section_id,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame3d_member_add",
        "model_id": edited_validation.report.model_id,
        "node_id": node_id,
        "node_index": node_index,
        "coordinates_m": coordinates_m,
        "element_id": element_id,
        "element_index": element_index,
        "element_type": "frame_3d",
        "formulation": "euler_bernoulli_3d",
        "node_ids": [from_node_id, node_id],
        "material_id": material_id,
        "section_id": section_id,
        "local_axis_rotation_rad": 0.0,
        "offsets_m": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
        "releases": {"i": [], "j": []},
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME3D_MEMBER_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrame3dMemberAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Add one provenance-bound node and connected linear `truss_3d` member in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, duplicate identities or coordinates, missing or unsupported
/// references, schema drift, or edited topology rejected by the C++ semantic validator.
#[allow(clippy::too_many_arguments)]
pub fn add_model_truss3d_member(
    source_bytes: &[u8],
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<ModelTruss3dMemberAddOutcomeV1, WorkbenchError> {
    validate_truss3d_member_add_request(
        source_bytes.len(),
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let (node_index, element_index) = append_truss3d_member(
        &mut edited,
        node_id,
        coordinates_m,
        element_id,
        from_node_id,
        material_id,
        section_id,
    )?;
    bind_truss3d_member_add_provenance(
        &mut edited,
        node_id,
        node_index,
        coordinates_m,
        element_id,
        element_index,
        from_node_id,
        material_id,
        section_id,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss3d_member_add",
        "model_id": edited_validation.report.model_id,
        "node_id": node_id,
        "node_index": node_index,
        "coordinates_m": coordinates_m,
        "element_id": element_id,
        "element_index": element_index,
        "element_type": "truss_3d",
        "formulation": "linear_truss_3d",
        "node_ids": [from_node_id, node_id],
        "material_id": material_id,
        "section_id": section_id,
        "offsets_m": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS3D_MEMBER_ADD_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTruss3dMemberAddOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedFrame3dLeafV1 {
    node_index: usize,
    coordinates_m: [f64; 3],
    element_index: usize,
    node_ids: [String; 2],
    material_id: String,
    section_id: String,
    local_axis_rotation_rad: f64,
    offsets_global_m: [[f64; 3]; 2],
    releases: Value,
}

#[derive(Clone, Debug, PartialEq)]
struct RemovedTruss3dLeafV1 {
    node_index: usize,
    coordinates_m: [f64; 3],
    element_index: usize,
    node_ids: [String; 2],
    material_id: String,
    section_id: String,
    offsets_global_m: [[f64; 3]; 2],
}

/// Delete one last contiguous neutral Euler-Bernoulli frame leaf and its orphan node in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal rows, source-owned entities, a node
/// referenced by any other element/load/constraint, a staged element, round-trip mappings, schema
/// drift, or edited topology rejected by the C++ semantic validator.
pub fn delete_model_frame3d_leaf_member(
    source_bytes: &[u8],
    element_id: &str,
    node_id: &str,
) -> Result<ModelFrame3dLeafMemberDeleteOutcomeV1, WorkbenchError> {
    validate_frame3d_leaf_member_delete_request(source_bytes.len(), element_id, node_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_frame3d_leaf_member(&mut edited, element_id, node_id)?;
    bind_frame3d_leaf_member_delete_provenance(
        &mut edited,
        element_id,
        node_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "frame3d_leaf_member_delete",
        "model_id": edited_validation.report.model_id,
        "removed_node_id": node_id,
        "removed_node_index": removed.node_index,
        "removed_coordinates_m": removed.coordinates_m,
        "removed_element_id": element_id,
        "removed_element_index": removed.element_index,
        "removed_element_type": "frame_3d",
        "removed_formulation": "euler_bernoulli_3d",
        "removed_node_ids": removed.node_ids,
        "removed_material_id": removed.material_id,
        "removed_section_id": removed.section_id,
        "removed_local_axis_rotation_rad": removed.local_axis_rotation_rad,
        "removed_offsets_m": {
            "i_global_m": removed.offsets_global_m[0],
            "j_global_m": removed.offsets_global_m[1]
        },
        "removed_releases": removed.releases,
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": FRAME3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelFrame3dLeafMemberDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

/// Delete one last contiguous neutral linear-truss leaf and its orphan node in memory.
///
/// # Errors
///
/// Rejects invalid source semantics, missing or non-terminal rows, source-owned entities, a node
/// referenced by any other element/load/constraint, a staged element, round-trip mappings, schema
/// drift, or edited topology rejected by the C++ semantic validator.
pub fn delete_model_truss3d_leaf_member(
    source_bytes: &[u8],
    element_id: &str,
    node_id: &str,
) -> Result<ModelTruss3dLeafMemberDeleteOutcomeV1, WorkbenchError> {
    validate_truss3d_leaf_member_delete_request(source_bytes.len(), element_id, node_id)?;

    let source_validation = validate_model_bytes(source_bytes)
        .map_err(|error| input_error("workbench_model_edit_source_validation_failed", &error))?;
    if !source_validation.report.contract_valid || !source_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_source_semantics_invalid",
            "native C++ validation rejected the source ModelIR semantics",
        ));
    }
    let source_document = &source_validation.snapshot;
    let source_content_hash = source_document.content_hash().to_owned();
    let source_semantic_hash = source_document.semantic_hash().to_owned();
    let source_provenance_hash = source_document.provenance_hash().to_owned();
    let source_input_sha256 = sha256_identity(source_bytes);
    let mut edited = source_document.value().clone();
    let removed = remove_truss3d_leaf_member(&mut edited, element_id, node_id)?;
    bind_truss3d_leaf_member_delete_provenance(
        &mut edited,
        element_id,
        node_id,
        &removed,
        &source_content_hash,
        &source_semantic_hash,
        &source_provenance_hash,
    )?;

    let edited_wire = canonicalize_model_ir_v2(&edited)
        .map_err(|error| input_error("workbench_model_edit_serialization_failed", &error))?;
    parse_model_ir_v2(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_contract_invalid", &error))?;
    let edited_validation = validate_model_bytes(edited_wire.as_bytes())
        .map_err(|error| input_error("workbench_model_edit_validation_failed", &error))?;
    if !edited_validation.report.contract_valid || !edited_validation.report.semantics_valid {
        return Err(WorkbenchError::new(
            "workbench_model_edit_semantics_invalid",
            "native C++ validation rejected the edited ModelIR semantics",
        ));
    }
    let model_ir_json = edited_validation.snapshot.canonical_json().to_owned();
    let model_artifact = artifact_entry(
        "edited_model_ir",
        "model-ir.json",
        "application/json",
        model_ir_json.as_bytes(),
    )?;
    let receipt_json = canonical_self_hashed(json!({
        "schema_version": EDIT_SCHEMA_V1,
        "operation": "truss3d_leaf_member_delete",
        "model_id": edited_validation.report.model_id,
        "removed_node_id": node_id,
        "removed_node_index": removed.node_index,
        "removed_coordinates_m": removed.coordinates_m,
        "removed_element_id": element_id,
        "removed_element_index": removed.element_index,
        "removed_element_type": "truss_3d",
        "removed_formulation": "linear_truss_3d",
        "removed_node_ids": removed.node_ids,
        "removed_material_id": removed.material_id,
        "removed_section_id": removed.section_id,
        "removed_offsets_m": {
            "i_global_m": removed.offsets_global_m[0],
            "j_global_m": removed.offsets_global_m[1]
        },
        "source_input_sha256": source_input_sha256,
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "edited_content_hash": edited_validation.report.content_hash,
        "edited_semantic_hash": edited_validation.report.semantic_hash,
        "edited_provenance_hash": edited_validation.report.provenance_hash,
        "cpp_semantic_snapshot_verified": true,
        "analysis_ready": edited_validation.report.analysis_ready,
        "blocking_feature_ids": edited_validation.report.blocking_feature_ids,
        "artifacts": [model_artifact],
        "claim_boundary": TRUSS3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY,
    }))?;
    Ok(ModelTruss3dLeafMemberDeleteOutcomeV1 {
        model_ir_json,
        receipt_json,
    })
}

fn validate_edit_request(
    source_length: usize,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<(), WorkbenchError> {
    if source_length > usize::try_from(MAX_MODEL_BYTES).unwrap_or(usize::MAX) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_input_too_large",
            "ModelIR exceeds the bounded editor input limit",
        ));
    }
    if coordinates_m
        .iter()
        .any(|coordinate| !coordinate.is_finite())
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_coordinate_invalid",
            "edited node coordinates must be finite SI values",
        ));
    }
    if node_id.is_empty() || node_id.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_node_id_invalid",
            "edited node identity must contain 1 through 128 bytes",
        ));
    }
    Ok(())
}

fn validate_node_add_request(
    source_length: usize,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, node_id, "new node")?;
    if coordinates_m
        .iter()
        .any(|coordinate| !coordinate.is_finite())
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_node_coordinate_invalid",
            "new node coordinates must be finite SI values",
        ));
    }
    Ok(())
}

fn validate_orphan_node_delete_request(
    source_length: usize,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, node_id, "orphan node")
}

fn validate_nodal_load_edit_request(
    source_length: usize,
    load_pattern_id: &str,
    nodal_load_id: &str,
    components_si: [f64; 6],
) -> Result<(), WorkbenchError> {
    if source_length > usize::try_from(MAX_MODEL_BYTES).unwrap_or(usize::MAX) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_input_too_large",
            "ModelIR exceeds the bounded editor input limit",
        ));
    }
    if load_pattern_id.is_empty() || load_pattern_id.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_load_pattern_id_invalid",
            "edited load-pattern identity must contain 1 through 128 bytes",
        ));
    }
    if nodal_load_id.is_empty() || nodal_load_id.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nodal_load_id_invalid",
            "edited nodal-load identity must contain 1 through 128 bytes",
        ));
    }
    if components_si.iter().any(|component| !component.is_finite()) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_load_component_invalid",
            "edited nodal-load components must be finite SI values",
        ));
    }
    Ok(())
}

fn validate_constraint_value_edit_request(
    source_length: usize,
    constraint_id: &str,
    dof: &str,
    value_si: f64,
) -> Result<(), WorkbenchError> {
    if source_length > usize::try_from(MAX_MODEL_BYTES).unwrap_or(usize::MAX) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_input_too_large",
            "ModelIR exceeds the bounded editor input limit",
        ));
    }
    if constraint_id.is_empty() || constraint_id.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_constraint_id_invalid",
            "edited constraint identity must contain 1 through 128 bytes",
        ));
    }
    if !DOF_KEYS.contains(&dof) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_constraint_dof_invalid",
            "edited constraint DOF must be UX, UY, UZ, RX, RY, or RZ",
        ));
    }
    if !value_si.is_finite() {
        return Err(WorkbenchError::new(
            "workbench_model_edit_constraint_value_invalid",
            "edited prescribed value must be a finite SI value",
        ));
    }
    Ok(())
}

fn validate_linear_material_edit_request(
    source_length: usize,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, material_id, "material")?;
    if !parameters.elastic_modulus_pa.is_finite() || parameters.elastic_modulus_pa <= 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_material_elastic_modulus_invalid",
            "edited elastic modulus must be a finite SI value greater than zero",
        ));
    }
    if !parameters.poisson_ratio.is_finite()
        || parameters.poisson_ratio <= -1.0
        || parameters.poisson_ratio >= 0.5
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_material_poisson_ratio_invalid",
            "edited Poisson ratio must be finite and strictly between -1 and 0.5",
        ));
    }
    if !parameters.density_kg_m3.is_finite() || parameters.density_kg_m3 < 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_material_density_invalid",
            "edited density must be a finite SI value greater than or equal to zero",
        ));
    }
    Ok(())
}

fn validate_frame_section_edit_request(
    source_length: usize,
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "section")?;
    if frame_section_parameter_values(parameters)
        .iter()
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_frame_section_parameter_invalid",
            "edited frame-section SI parameters must be finite and greater than zero",
        ));
    }
    Ok(())
}

fn validate_truss_section_edit_request(
    source_length: usize,
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "section")?;
    if !parameters.area_m2.is_finite() || parameters.area_m2 <= 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_section_area_invalid",
            "edited truss-section area must be a finite SI value greater than zero",
        ));
    }
    Ok(())
}

fn validate_frame_element_orientation_edit_request(
    source_length: usize,
    element_id: &str,
    local_axis_rotation_rad: f64,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "element")?;
    if !local_axis_rotation_rad.is_finite() {
        return Err(WorkbenchError::new(
            "workbench_model_edit_element_orientation_invalid",
            "edited frame-element local-axis rotation must be a finite radian value",
        ));
    }
    Ok(())
}

fn validate_frame_element_properties_edit_request(
    source_length: usize,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "element")?;
    validate_bounded_edit_identity(0, material_id, "material")?;
    validate_bounded_edit_identity(0, section_id, "section")?;
    Ok(())
}

fn validate_truss_element_properties_edit_request(
    source_length: usize,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "element")?;
    validate_bounded_edit_identity(0, material_id, "material")?;
    validate_bounded_edit_identity(0, section_id, "section")?;
    Ok(())
}

fn validate_element_connectivity_edit_request(
    source_length: usize,
    element_id: &str,
    node_ids: [&str; 2],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "element")?;
    validate_bounded_edit_identity(0, node_ids[0], "i-node")?;
    validate_bounded_edit_identity(0, node_ids[1], "j-node")?;
    if node_ids[0] == node_ids[1] {
        return Err(WorkbenchError::new(
            "workbench_model_edit_element_connectivity_invalid",
            "edited element endpoints must reference two distinct node identities",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn validate_frame3d_member_add_request(
    source_length: usize,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, node_id, "new node")?;
    validate_bounded_edit_identity(0, element_id, "new element")?;
    validate_bounded_edit_identity(0, from_node_id, "existing node")?;
    validate_bounded_edit_identity(0, material_id, "material")?;
    validate_bounded_edit_identity(0, section_id, "section")?;
    if node_id == from_node_id {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_node_identity_invalid",
            "new and existing endpoint node identities must differ",
        ));
    }
    if coordinates_m.iter().any(|value| !value.is_finite()) {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_coordinate_invalid",
            "new frame-member node coordinates must be finite SI values",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn validate_truss3d_member_add_request(
    source_length: usize,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, node_id, "new node")?;
    validate_bounded_edit_identity(0, element_id, "new element")?;
    validate_bounded_edit_identity(0, from_node_id, "existing node")?;
    validate_bounded_edit_identity(0, material_id, "material")?;
    validate_bounded_edit_identity(0, section_id, "section")?;
    if node_id == from_node_id {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_node_identity_invalid",
            "new and existing endpoint node identities must differ",
        ));
    }
    if coordinates_m.iter().any(|value| !value.is_finite()) {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_coordinate_invalid",
            "new truss-member node coordinates must be finite SI values",
        ));
    }
    Ok(())
}

fn validate_frame3d_leaf_member_delete_request(
    source_length: usize,
    element_id: &str,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "frame element")?;
    validate_bounded_edit_identity(0, node_id, "orphan node")?;
    if element_id == node_id {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame3d_leaf_identity_collision",
            "deleted element and node identities must differ",
        ));
    }
    Ok(())
}

fn validate_truss3d_leaf_member_delete_request(
    source_length: usize,
    element_id: &str,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, element_id, "truss element")?;
    validate_bounded_edit_identity(0, node_id, "orphan node")?;
    if element_id == node_id {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss3d_leaf_identity_collision",
            "deleted element and node identities must differ",
        ));
    }
    Ok(())
}

fn validate_nodal_load_add_request(
    source_length: usize,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_pattern_id, "load pattern")?;
    validate_bounded_edit_identity(0, nodal_load_id, "new nodal load")?;
    validate_bounded_edit_identity(0, node_id, "load target node")?;
    if components_si.iter().any(|value| !value.is_finite()) {
        return Err(WorkbenchError::new(
            "workbench_model_add_nodal_load_component_invalid",
            "new nodal-load components must be finite SI values",
        ));
    }
    if components_si.iter().all(|value| *value == 0.0) {
        return Err(WorkbenchError::new(
            "workbench_model_add_nodal_load_zero_components",
            "new nodal load must contain at least one non-zero SI component",
        ));
    }
    Ok(())
}

fn validate_nodal_load_delete_request(
    source_length: usize,
    load_pattern_id: &str,
    nodal_load_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_pattern_id, "load pattern")?;
    validate_bounded_edit_identity(0, nodal_load_id, "nodal load")
}

fn validate_fixed_constraint_add_request(
    source_length: usize,
    constraint_id: &str,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, constraint_id, "new fixed constraint")?;
    validate_bounded_edit_identity(0, node_id, "fixed-constraint target node")?;
    Ok(())
}

fn validate_fixed_constraint_delete_request(
    source_length: usize,
    constraint_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, constraint_id, "fixed constraint")
}

fn validate_linear_load_pattern_add_request(
    source_length: usize,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_pattern_id, "new load pattern")?;
    validate_bounded_edit_identity(0, nodal_load_id, "new nodal load")?;
    validate_bounded_edit_identity(0, node_id, "load target node")?;
    if components_si.iter().any(|value| !value.is_finite()) {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_pattern_component_invalid",
            "new load-pattern nodal-load components must be finite SI values",
        ));
    }
    if components_si.iter().all(|value| *value == 0.0) {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_pattern_zero_components",
            "new linear-static load pattern must contain a non-zero first nodal load",
        ));
    }
    Ok(())
}

fn validate_linear_load_combination_add_request(
    source_length: usize,
    load_combination_id: &str,
    terms: &[LinearLoadCombinationTermV1],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "new load combination")?;
    if !(MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
        ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
        .contains(&terms.len())
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_combination_term_count_invalid",
            "direct load combinations require between two and 64 terms",
        ));
    }
    for term in terms {
        validate_bounded_edit_identity(0, &term.load_pattern_id, "load-combination term pattern")?;
        if !term.factor.is_finite() || term.factor == 0.0 {
            return Err(WorkbenchError::new(
                "workbench_model_add_linear_load_combination_factor_invalid",
                "load-combination factors must be finite and non-zero",
            ));
        }
    }
    if terms.iter().enumerate().any(|(index, term)| {
        terms[..index]
            .iter()
            .any(|prior| prior.load_pattern_id == term.load_pattern_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_combination_pattern_duplicate",
            "direct load-combination terms must reference unique load patterns",
        ));
    }
    Ok(())
}

fn validate_direct_linear_load_combination_factor_edit_request(
    source_length: usize,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: f64,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "load combination")?;
    validate_bounded_edit_identity(0, load_pattern_id, "load-combination term pattern")?;
    if !factor.is_finite() || factor == 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_factor_invalid",
            "edited load-combination factor must be finite and non-zero",
        ));
    }
    Ok(())
}

fn validate_direct_linear_load_combination_reference_edit_request(
    source_length: usize,
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "load combination")?;
    validate_bounded_edit_identity(0, load_pattern_id, "source load-combination pattern")?;
    validate_bounded_edit_identity(
        0,
        replacement_load_pattern_id,
        "replacement load-combination pattern",
    )?;
    Ok(())
}

fn validate_nested_linear_load_combination_factor_edit_request(
    source_length: usize,
    load_combination_id: &str,
    reference_id: &str,
    factor: f64,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "load combination")?;
    validate_bounded_edit_identity(0, reference_id, "nested load-combination typed term")?;
    if !factor.is_finite() || factor == 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_factor_invalid",
            "edited nested load-combination factor must be finite and non-zero",
        ));
    }
    Ok(())
}

fn validate_nested_linear_load_combination_reference_edit_request(
    source_length: usize,
    load_combination_id: &str,
    reference_id: &str,
    replacement_reference_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "load combination")?;
    validate_bounded_edit_identity(0, reference_id, "source nested typed reference")?;
    validate_bounded_edit_identity(
        0,
        replacement_reference_id,
        "replacement nested typed reference",
    )?;
    Ok(())
}

fn validate_nested_linear_load_combination_add_request(
    source_length: usize,
    load_combination_id: &str,
    terms: &[NestedLinearLoadCombinationTermV1],
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_combination_id, "new load combination")?;
    if !(MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
        ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
        .contains(&terms.len())
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_nested_linear_load_combination_term_count_invalid",
            "nested load combinations require between two and 64 root terms",
        ));
    }
    if !terms
        .iter()
        .any(|term| term.reference_kind == LinearLoadCombinationReferenceKindV1::LoadCombination)
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_nested_linear_load_combination_reference_required",
            "nested load-combination authoring requires at least one load-combination term",
        ));
    }
    for term in terms {
        validate_bounded_edit_identity(
            0,
            &term.reference_id,
            "nested load-combination term reference",
        )?;
        if term.reference_id == load_combination_id {
            return Err(WorkbenchError::new(
                "workbench_model_add_nested_linear_load_combination_self_reference",
                "a new nested load combination cannot reference itself",
            ));
        }
        if !term.factor.is_finite() || term.factor == 0.0 {
            return Err(WorkbenchError::new(
                "workbench_model_add_nested_linear_load_combination_factor_invalid",
                "nested load-combination factors must be finite and non-zero",
            ));
        }
    }
    if terms.iter().enumerate().any(|(index, term)| {
        terms[..index].iter().any(|prior| {
            prior.reference_kind == term.reference_kind && prior.reference_id == term.reference_id
        })
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_nested_linear_load_combination_reference_duplicate",
            "nested load-combination root terms must use unique typed references",
        ));
    }
    Ok(())
}

fn validate_linear_load_combination_delete_request(
    source_length: usize,
    load_combination_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(
        source_length,
        load_combination_id,
        "deleted load combination",
    )
}

fn validate_linear_load_pattern_delete_request(
    source_length: usize,
    load_pattern_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, load_pattern_id, "load pattern")
}

fn validate_linear_material_add_request(
    source_length: usize,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, material_id, "new material")?;
    if !parameters.elastic_modulus_pa.is_finite() || parameters.elastic_modulus_pa <= 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_material_elastic_modulus_invalid",
            "new material elastic modulus must be a finite SI value greater than zero",
        ));
    }
    if !parameters.poisson_ratio.is_finite()
        || parameters.poisson_ratio <= -1.0
        || parameters.poisson_ratio >= 0.5
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_material_poisson_ratio_invalid",
            "new material Poisson ratio must be finite and strictly between -1 and 0.5",
        ));
    }
    if !parameters.density_kg_m3.is_finite() || parameters.density_kg_m3 < 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_material_density_invalid",
            "new material density must be a finite SI value greater than or equal to zero",
        ));
    }
    Ok(())
}

fn validate_linear_material_delete_request(
    source_length: usize,
    material_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, material_id, "material")
}

fn validate_frame_section_add_request(
    source_length: usize,
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "new section")?;
    if frame_section_parameter_values(parameters)
        .iter()
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame_section_parameter_invalid",
            "new frame-section SI parameters must be finite and greater than zero",
        ));
    }
    Ok(())
}

fn validate_frame_section_delete_request(
    source_length: usize,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "section")
}

fn validate_truss_section_add_request(
    source_length: usize,
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "new section")?;
    if !parameters.area_m2.is_finite() || parameters.area_m2 <= 0.0 {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss_section_area_invalid",
            "new truss-section area must be a finite SI value greater than zero",
        ));
    }
    Ok(())
}

fn validate_truss_section_delete_request(
    source_length: usize,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    validate_bounded_edit_identity(source_length, section_id, "section")
}

fn validate_bounded_edit_identity(
    source_length: usize,
    identity: &str,
    entity_kind: &str,
) -> Result<(), WorkbenchError> {
    if source_length > usize::try_from(MAX_MODEL_BYTES).unwrap_or(usize::MAX) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_input_too_large",
            "ModelIR exceeds the bounded editor input limit",
        ));
    }
    if identity.is_empty() || identity.len() > 128 {
        return Err(WorkbenchError::new(
            "workbench_model_edit_entity_id_invalid",
            format!("edited {entity_kind} identity must contain 1 through 128 bytes"),
        ));
    }
    Ok(())
}

fn replace_node_coordinates(
    model: &mut Value,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<[f64; 3], WorkbenchError> {
    let nodes = model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?;
    let node = nodes
        .iter_mut()
        .find(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_node_missing",
                format!("ModelIR has no node with identity {node_id}"),
            )
        })?;
    let previous = node
        .get("coordinates_m")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| snapshot_error("node coordinates_m"))?;
    let previous_coordinates_m = [
        finite_number(&previous[0], "finite coordinate")?,
        finite_number(&previous[1], "finite coordinate")?,
        finite_number(&previous[2], "finite coordinate")?,
    ];
    node.as_object_mut()
        .ok_or_else(|| snapshot_error("node"))?
        .insert("coordinates_m".to_owned(), json!(coordinates_m));
    Ok(previous_coordinates_m)
}

fn replace_nodal_load_components(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
    components_si: [f64; 6],
) -> Result<[f64; 6], WorkbenchError> {
    let load_patterns = model
        .get_mut("load_patterns")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    let load_pattern = load_patterns
        .iter_mut()
        .find(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_pattern_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_load_pattern_missing",
                format!("ModelIR has no load pattern with identity {load_pattern_id}"),
            )
        })?;
    let nodal_loads = load_pattern
        .get_mut("nodal_loads")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load pattern nodal_loads"))?;
    let nodal_load = nodal_loads
        .iter_mut()
        .find(|load| load.get("id").and_then(Value::as_str) == Some(nodal_load_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_nodal_load_missing",
                format!(
                    "load pattern {load_pattern_id} has no nodal load with identity {nodal_load_id}"
                ),
            )
        })?;
    let previous = nodal_load
        .get("components_si")
        .and_then(Value::as_object)
        .ok_or_else(|| snapshot_error("nodal load components_si"))?;
    let mut previous_components_si = [0.0; 6];
    for (index, key) in NODAL_LOAD_COMPONENT_KEYS.iter().enumerate() {
        previous_components_si[index] = previous
            .get(*key)
            .ok_or_else(|| snapshot_error("nodal load component"))
            .and_then(|value| finite_number(value, "nodal load component"))?;
    }
    nodal_load
        .as_object_mut()
        .ok_or_else(|| snapshot_error("nodal load"))?
        .insert("components_si".to_owned(), components_object(components_si));
    Ok(previous_components_si)
}

fn append_nodal_load(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<(usize, usize), WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if !nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_nodal_load_node_missing",
            format!("ModelIR has no load target node with identity {node_id}"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns.iter().any(|pattern| {
        pattern
            .get("nodal_loads")
            .and_then(Value::as_array)
            .is_some_and(|loads| {
                loads
                    .iter()
                    .any(|load| load.get("id").and_then(Value::as_str) == Some(nodal_load_id))
            })
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_nodal_load_identity_exists",
            format!("ModelIR already has a nodal load with identity {nodal_load_id}"),
        ));
    }
    let load_pattern_index = load_patterns
        .iter()
        .position(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_pattern_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_add_nodal_load_pattern_missing",
                format!("ModelIR has no load pattern with identity {load_pattern_id}"),
            )
        })?;
    let pattern = &load_patterns[load_pattern_index];
    if pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
        return Err(WorkbenchError::new(
            "workbench_model_add_nodal_load_pattern_unsupported",
            "new nodal load requires an existing linear_static load pattern",
        ));
    }
    let nodal_load_index = pattern
        .get("nodal_loads")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load pattern nodal_loads"))?
        .len();
    model
        .get_mut("load_patterns")
        .and_then(Value::as_array_mut)
        .and_then(|patterns| patterns.get_mut(load_pattern_index))
        .and_then(|pattern| pattern.get_mut("nodal_loads"))
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load pattern nodal_loads"))?
        .push(json!({
            "id": nodal_load_id,
            "index": nodal_load_index,
            "node_id": node_id,
            "components_si": components_object(components_si),
            "source_id": null,
            "extensions": {}
        }));
    Ok((load_pattern_index, nodal_load_index))
}

#[allow(clippy::too_many_lines)]
fn remove_nodal_load(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
) -> Result<RemovedNodalLoadV1, WorkbenchError> {
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    let load_pattern_index = load_patterns
        .iter()
        .position(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_pattern_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_nodal_load_pattern_missing",
                format!("ModelIR has no load pattern with identity {load_pattern_id}"),
            )
        })?;
    let load_pattern = &load_patterns[load_pattern_index];
    if load_pattern.get("index").and_then(Value::as_u64) != u64::try_from(load_pattern_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_pattern_index_mismatch",
            "target load-pattern index must match its contiguous position",
        ));
    }
    if load_pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_pattern_unsupported",
            "nodal-load deletion accepts only an existing linear_static pattern",
        ));
    }
    let nodal_loads = load_pattern
        .get("nodal_loads")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load pattern nodal_loads"))?;
    let nodal_load_index = nodal_loads
        .iter()
        .position(|load| load.get("id").and_then(Value::as_str) == Some(nodal_load_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_nodal_load_missing",
                format!(
                    "load pattern {load_pattern_id} has no nodal load with identity {nodal_load_id}"
                ),
            )
        })?;
    if nodal_load_index + 1 != nodal_loads.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_not_terminal",
            "deleted nodal load must be the last contiguous row in its pattern",
        ));
    }
    if nodal_loads.len() <= 1 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_minimum_pattern",
            "nodal-load deletion must retain at least one nonzero nodal load in the pattern",
        ));
    }
    let nodal_load = &nodal_loads[nodal_load_index];
    if nodal_load.get("index").and_then(Value::as_u64) != u64::try_from(nodal_load_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_index_mismatch",
            "deleted nodal-load index must match its last contiguous position",
        ));
    }
    if !nodal_load.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_source_owned",
            "nodal-load deletion accepts only a neutral row with null source_id",
        ));
    }
    let node_id = nodal_load
        .get("node_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("nodal load node_id"))?
        .to_owned();
    let components = nodal_load
        .get("components_si")
        .and_then(Value::as_object)
        .filter(|values| values.len() == NODAL_LOAD_COMPONENT_KEYS.len())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_nodal_load_components_invalid",
                "deleted nodal load must contain exactly six SI components",
            )
        })?;
    let mut removed_is_nonzero = false;
    for component in NODAL_LOAD_COMPONENT_KEYS {
        let value = components
            .get(component)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_delete_nodal_load_components_invalid",
                    format!("deleted nodal load has no {component} component"),
                )
            })?
            .as_f64()
            .filter(|value| value.is_finite())
            .ok_or_else(|| snapshot_error("nodal load component"))?;
        removed_is_nonzero = removed_is_nonzero || value != 0.0;
    }
    if !removed_is_nonzero {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_zero_components",
            "deleted nodal load must contain at least one nonzero SI component",
        ));
    }
    let mut retained_nonzero = false;
    for retained in &nodal_loads[..nodal_load_index] {
        let retained_components = retained
            .get("components_si")
            .and_then(Value::as_object)
            .filter(|values| values.len() == NODAL_LOAD_COMPONENT_KEYS.len())
            .ok_or_else(|| snapshot_error("retained nodal load components_si"))?;
        for component in NODAL_LOAD_COMPONENT_KEYS {
            let value = retained_components
                .get(component)
                .and_then(Value::as_f64)
                .filter(|value| value.is_finite())
                .ok_or_else(|| snapshot_error("retained nodal load component"))?;
            retained_nonzero = retained_nonzero || value != 0.0;
        }
    }
    if !retained_nonzero {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_retained_pattern_zero",
            "nodal-load deletion must retain another nonzero nodal load in the pattern",
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features.iter().any(|feature| {
        feature.get("source_entity_id").and_then(Value::as_str) == Some(nodal_load_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_unsupported_feature_owned",
            "nodal-load deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(nodal_load_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_nodal_load_roundtrip_owned",
            "nodal-load deletion refuses a row with a direct round-trip mapping",
        ));
    }

    let components_si = nodal_load["components_si"].clone();
    model
        .get_mut("load_patterns")
        .and_then(Value::as_array_mut)
        .and_then(|patterns| patterns.get_mut(load_pattern_index))
        .and_then(|pattern| pattern.get_mut("nodal_loads"))
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load pattern nodal_loads"))?
        .pop()
        .ok_or_else(|| snapshot_error("last nodal load"))?;
    Ok(RemovedNodalLoadV1 {
        load_pattern_index,
        nodal_load_index,
        node_id,
        components_si,
    })
}

fn append_fixed_constraint(
    model: &mut Value,
    constraint_id: &str,
    node_id: &str,
) -> Result<usize, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if !nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_fixed_constraint_node_missing",
            format!("ModelIR has no fixed-constraint target node with identity {node_id}"),
        ));
    }
    let constraints = model
        .get("constraints")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("constraints"))?;
    if constraints
        .iter()
        .any(|constraint| constraint.get("id").and_then(Value::as_str) == Some(constraint_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_fixed_constraint_identity_exists",
            format!("ModelIR already has a constraint with identity {constraint_id}"),
        ));
    }
    if constraints
        .iter()
        .any(|constraint| constraint.get("node_id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_fixed_constraint_node_already_constrained",
            format!("ModelIR node {node_id} already has a constraint"),
        ));
    }
    let constraint_index = constraints.len();
    model
        .get_mut("constraints")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("constraints"))?
        .push(json!({
            "id": constraint_id,
            "index": constraint_index,
            "type": "fixed_dofs",
            "node_id": node_id,
            "dofs": DOF_KEYS,
            "prescribed_values_si": fixed_constraint_values_object(),
            "source_id": null,
            "extensions": {}
        }));
    Ok(constraint_index)
}

#[allow(clippy::too_many_lines)]
fn remove_fixed_constraint(
    model: &mut Value,
    constraint_id: &str,
) -> Result<RemovedFixedConstraintV1, WorkbenchError> {
    let constraints = model
        .get("constraints")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("constraints"))?;
    if constraints.len() <= 1 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_minimum_topology",
            "fixed-constraint deletion must retain at least one constraint",
        ));
    }
    let constraint_index = constraints
        .iter()
        .position(|constraint| constraint.get("id").and_then(Value::as_str) == Some(constraint_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_fixed_constraint_missing",
                format!("ModelIR has no constraint with identity {constraint_id}"),
            )
        })?;
    if constraint_index + 1 != constraints.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_not_terminal",
            "deleted constraint must be the last contiguous constraint row",
        ));
    }
    let constraint = &constraints[constraint_index];
    if constraint.get("index").and_then(Value::as_u64) != u64::try_from(constraint_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_index_mismatch",
            "deleted constraint index must match its last contiguous position",
        ));
    }
    if constraint.get("type").and_then(Value::as_str) != Some("fixed_dofs") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_type_unsupported",
            "fixed-constraint deletion accepts only a fixed_dofs constraint",
        ));
    }
    if !constraint.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_source_owned",
            "fixed-constraint deletion accepts only a neutral row with null source_id",
        ));
    }
    let node_id = constraint
        .get("node_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("fixed constraint node_id"))?
        .to_owned();
    let dofs = constraint
        .get("dofs")
        .and_then(Value::as_array)
        .filter(|values| values.len() == DOF_KEYS.len())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_fixed_constraint_not_homogeneous",
                "deleted constraint must contain the closed six-DOF mask",
            )
        })?;
    if dofs
        .iter()
        .zip(DOF_KEYS)
        .any(|(value, expected)| value.as_str() != Some(expected))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_not_homogeneous",
            "deleted constraint must use the ordered UX/UY/UZ/RX/RY/RZ mask",
        ));
    }
    let prescribed_values = constraint
        .get("prescribed_values_si")
        .and_then(Value::as_object)
        .filter(|values| values.len() == DOF_KEYS.len())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_fixed_constraint_not_homogeneous",
                "deleted constraint must contain exactly six prescribed values",
            )
        })?;
    for dof in DOF_KEYS {
        let value = prescribed_values
            .get(dof)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_delete_fixed_constraint_not_homogeneous",
                    format!("deleted constraint has no prescribed value for {dof}"),
                )
            })?
            .as_f64()
            .filter(|value| value.is_finite())
            .ok_or_else(|| snapshot_error("fixed constraint prescribed value"))?;
        if normalized_number_bits(value) != normalized_number_bits(0.0) {
            return Err(WorkbenchError::new(
                "workbench_model_delete_fixed_constraint_not_homogeneous",
                "deleted constraint must prescribe zero for every restrained DOF",
            ));
        }
    }
    let construction_stages = model
        .get("construction_stages")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("construction_stages"))?;
    if construction_stages.iter().any(|stage| {
        stage
            .get("active_constraint_ids")
            .and_then(Value::as_array)
            .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(constraint_id)))
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_referenced_by_stage",
            format!("constraint {constraint_id} is referenced by a construction stage"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features.iter().any(|feature| {
        feature.get("source_entity_id").and_then(Value::as_str) == Some(constraint_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_unsupported_feature_owned",
            "fixed-constraint deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(constraint_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_fixed_constraint_roundtrip_owned",
            "fixed-constraint deletion refuses a row with a round-trip mapping",
        ));
    }

    let dofs = constraint["dofs"].clone();
    let prescribed_values_si = constraint["prescribed_values_si"].clone();
    model
        .get_mut("constraints")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("constraints"))?
        .pop()
        .ok_or_else(|| snapshot_error("last constraint"))?;
    Ok(RemovedFixedConstraintV1 {
        constraint_index,
        node_id,
        dofs,
        prescribed_values_si,
    })
}

fn append_linear_load_pattern(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
) -> Result<usize, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if !nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_pattern_node_missing",
            format!("ModelIR has no load target node with identity {node_id}"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns
        .iter()
        .any(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_pattern_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_pattern_identity_exists",
            format!("ModelIR already has a load pattern with identity {load_pattern_id}"),
        ));
    }
    if load_patterns.iter().any(|pattern| {
        pattern
            .get("nodal_loads")
            .and_then(Value::as_array)
            .is_some_and(|loads| {
                loads
                    .iter()
                    .any(|load| load.get("id").and_then(Value::as_str) == Some(nodal_load_id))
            })
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_pattern_load_identity_exists",
            format!("ModelIR already has a nodal load with identity {nodal_load_id}"),
        ));
    }
    let load_pattern_index = load_patterns.len();
    model
        .get_mut("load_patterns")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_patterns"))?
        .push(json!({
            "id": load_pattern_id,
            "index": load_pattern_index,
            "analysis_type": "linear_static",
            "self_weight": [0, 0, 0],
            "nodal_loads": [{
                "id": nodal_load_id,
                "index": 0,
                "node_id": node_id,
                "components_si": components_object(components_si),
                "source_id": null,
                "extensions": {}
            }],
            "source_id": null,
            "extensions": {}
        }));
    Ok(load_pattern_index)
}

fn append_linear_load_combination(
    model: &mut Value,
    load_combination_id: &str,
    terms: &[LinearLoadCombinationTermV1],
) -> Result<usize, WorkbenchError> {
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    if load_combinations.iter().any(|combination| {
        combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_load_combination_identity_exists",
            format!("ModelIR already has a load combination with identity {load_combination_id}"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    for term in terms {
        let pattern = load_patterns
            .iter()
            .find(|pattern| {
                pattern.get("id").and_then(Value::as_str) == Some(term.load_pattern_id.as_str())
            })
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_add_linear_load_combination_pattern_missing",
                    format!(
                        "ModelIR has no load pattern with identity {}",
                        term.load_pattern_id
                    ),
                )
            })?;
        if pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
            return Err(WorkbenchError::new(
                "workbench_model_add_linear_load_combination_pattern_unsupported",
                format!("load pattern {} is not linear_static", term.load_pattern_id),
            ));
        }
    }
    let load_combination_index = load_combinations.len();
    model
        .get_mut("load_combinations")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_combinations"))?
        .push(json!({
            "id": load_combination_id,
            "index": load_combination_index,
            "combination_type": "linear",
            "terms": linear_load_combination_terms_value(terms),
            "source_id": null,
            "extensions": {}
        }));
    Ok(load_combination_index)
}

fn linear_load_combination_terms_value(terms: &[LinearLoadCombinationTermV1]) -> Value {
    Value::Array(
        terms
            .iter()
            .map(|term| {
                json!({
                    "ref_id": term.load_pattern_id,
                    "ref_kind": "load_pattern",
                    "factor": term.factor
                })
            })
            .collect(),
    )
}

#[allow(clippy::too_many_lines)]
fn replace_direct_linear_load_combination_factor(
    model: &mut Value,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor: f64,
) -> Result<DirectLinearLoadCombinationFactorEditV1, WorkbenchError> {
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    let load_combination_index = load_combinations
        .iter()
        .position(|combination| {
            combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    let combination = &load_combinations[load_combination_index];
    if combination.get("index").and_then(Value::as_u64)
        != u64::try_from(load_combination_index).ok()
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_index_mismatch",
            "edited load-combination index must match its contiguous position",
        ));
    }
    if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_type_unsupported",
            "factor editing accepts only a linear load combination",
        ));
    }
    if !combination.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_source_owned",
            "factor editing accepts only a neutral combination with null source_id",
        ));
    }
    if !combination
        .get("extensions")
        .and_then(Value::as_object)
        .is_some_and(serde_json::Map::is_empty)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_extensions_unsupported",
            "factor editing accepts only a combination with empty extensions",
        ));
    }
    let terms = combination
        .get("terms")
        .and_then(Value::as_array)
        .filter(|terms| {
            (MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
                ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
                .contains(&terms.len())
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_terms_unsupported",
                "edited direct load combination must contain between two and 64 terms",
            )
        })?;
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    let mut direct_pattern_ids = Vec::with_capacity(terms.len());
    let mut term_index = None;
    let mut previous_factor = None;
    for (index, term) in terms.iter().enumerate() {
        if term.get("ref_kind").and_then(Value::as_str) != Some("load_pattern") {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_nested_unsupported",
                "direct factor editing accepts load-pattern terms only",
            ));
        }
        let reference_id = term
            .get("ref_id")
            .and_then(Value::as_str)
            .ok_or_else(|| snapshot_error("load-combination term ref_id"))?;
        let source_factor = term
            .get("factor")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite() && *value != 0.0)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_edit_linear_load_combination_source_factor_unsupported",
                    "source load-combination factors must be finite and non-zero",
                )
            })?;
        if direct_pattern_ids.contains(&reference_id) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_pattern_duplicate",
                "edited direct load combination must reference unique load patterns",
            ));
        }
        if !load_patterns.iter().any(|pattern| {
            pattern.get("id").and_then(Value::as_str) == Some(reference_id)
                && pattern.get("analysis_type").and_then(Value::as_str) == Some("linear_static")
        }) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_pattern_unsupported",
                format!("combination term {reference_id} is not an existing linear_static pattern"),
            ));
        }
        direct_pattern_ids.push(reference_id);
        if reference_id == load_pattern_id {
            term_index = Some(index);
            previous_factor = Some(source_factor);
        }
    }
    let term_index = term_index.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_term_missing",
            format!(
                "load combination {load_combination_id} has no load-pattern term {load_pattern_id}"
            ),
        )
    })?;
    let previous_factor = previous_factor.ok_or_else(|| snapshot_error("source term factor"))?;
    if load_combinations
        .iter()
        .enumerate()
        .any(|(index, candidate)| {
            index != load_combination_index
                && candidate
                    .get("terms")
                    .and_then(Value::as_array)
                    .is_some_and(|candidate_terms| {
                        candidate_terms.iter().any(|term| {
                            term.get("ref_kind").and_then(Value::as_str) == Some("load_combination")
                                && term.get("ref_id").and_then(Value::as_str)
                                    == Some(load_combination_id)
                        })
                    })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_referenced_by_combination",
            format!("load combination {load_combination_id} is referenced by another combination"),
        ));
    }
    if model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?
        .iter()
        .any(|feature| {
            feature.get("source_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_unsupported_feature_owned",
            "factor editing refuses a combination referenced by an unsupported feature",
        ));
    }
    if model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?
        .iter()
        .any(|row| {
            row.get("model_ir_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_roundtrip_owned",
            "factor editing refuses a combination with a direct round-trip mapping",
        ));
    }

    let edited_terms = {
        let combination = model
            .get_mut("load_combinations")
            .and_then(Value::as_array_mut)
            .and_then(|combinations| combinations.get_mut(load_combination_index))
            .ok_or_else(|| snapshot_error("edited load combination"))?;
        let terms = combination
            .get_mut("terms")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| snapshot_error("edited load-combination terms"))?;
        terms[term_index]["factor"] = json!(factor);
        Value::Array(terms.clone())
    };
    Ok(DirectLinearLoadCombinationFactorEditV1 {
        load_combination_index,
        term_index,
        previous_factor,
        edited_terms,
    })
}

#[allow(clippy::too_many_lines)]
fn replace_direct_linear_load_combination_reference(
    model: &mut Value,
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
) -> Result<DirectLinearLoadCombinationReferenceEditV1, WorkbenchError> {
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    let load_combination_index = load_combinations
        .iter()
        .position(|combination| {
            combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    let combination = &load_combinations[load_combination_index];
    if combination.get("index").and_then(Value::as_u64)
        != u64::try_from(load_combination_index).ok()
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_index_mismatch",
            "edited load-combination index must match its contiguous position",
        ));
    }
    if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_type_unsupported",
            "reference editing accepts only a linear load combination",
        ));
    }
    if !combination.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_source_owned",
            "reference editing accepts only a neutral combination with null source_id",
        ));
    }
    if !combination
        .get("extensions")
        .and_then(Value::as_object)
        .is_some_and(serde_json::Map::is_empty)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_extensions_unsupported",
            "reference editing accepts only a combination with empty extensions",
        ));
    }
    let terms = combination
        .get("terms")
        .and_then(Value::as_array)
        .filter(|terms| {
            (MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
                ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
                .contains(&terms.len())
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_terms_unsupported",
                "edited direct load combination must contain between two and 64 terms",
            )
        })?;
    let source_terms = Value::Array(terms.clone());
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    let replacement_pattern = load_patterns
        .iter()
        .find(|pattern| {
            pattern.get("id").and_then(Value::as_str) == Some(replacement_load_pattern_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_replacement_pattern_missing",
                format!(
                    "ModelIR has no replacement load pattern with identity {replacement_load_pattern_id}"
                ),
            )
        })?;
    if replacement_pattern
        .get("analysis_type")
        .and_then(Value::as_str)
        != Some("linear_static")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_replacement_pattern_unsupported",
            format!("replacement load pattern {replacement_load_pattern_id} is not linear_static"),
        ));
    }
    let mut direct_pattern_ids = Vec::with_capacity(terms.len());
    let mut term_index = None;
    let mut preserved_factor = None;
    for (index, term) in terms.iter().enumerate() {
        if term.get("ref_kind").and_then(Value::as_str) != Some("load_pattern") {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_nested_unsupported",
                "direct reference editing accepts load-pattern terms only",
            ));
        }
        let reference_id = term
            .get("ref_id")
            .and_then(Value::as_str)
            .ok_or_else(|| snapshot_error("load-combination term ref_id"))?;
        let source_factor = term
            .get("factor")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite() && *value != 0.0)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_edit_linear_load_combination_source_factor_unsupported",
                    "source load-combination factors must be finite and non-zero",
                )
            })?;
        if direct_pattern_ids.contains(&reference_id) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_pattern_duplicate",
                "edited direct load combination must reference unique load patterns",
            ));
        }
        if !load_patterns.iter().any(|pattern| {
            pattern.get("id").and_then(Value::as_str) == Some(reference_id)
                && pattern.get("analysis_type").and_then(Value::as_str) == Some("linear_static")
        }) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_linear_load_combination_pattern_unsupported",
                format!("combination term {reference_id} is not an existing linear_static pattern"),
            ));
        }
        direct_pattern_ids.push(reference_id);
        if reference_id == load_pattern_id {
            term_index = Some(index);
            preserved_factor = Some(source_factor);
        }
    }
    let term_index = term_index.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_term_missing",
            format!(
                "load combination {load_combination_id} has no load-pattern term {load_pattern_id}"
            ),
        )
    })?;
    let preserved_factor =
        preserved_factor.ok_or_else(|| snapshot_error("source term preserved factor"))?;
    if replacement_load_pattern_id == load_pattern_id {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "replacement load-pattern reference is identical to the source term",
        ));
    }
    if direct_pattern_ids.contains(&replacement_load_pattern_id) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_replacement_pattern_duplicate",
            format!(
                "replacement load pattern {replacement_load_pattern_id} already occurs in the combination"
            ),
        ));
    }
    if load_combinations
        .iter()
        .enumerate()
        .any(|(index, candidate)| {
            index != load_combination_index
                && candidate
                    .get("terms")
                    .and_then(Value::as_array)
                    .is_some_and(|candidate_terms| {
                        candidate_terms.iter().any(|term| {
                            term.get("ref_kind").and_then(Value::as_str) == Some("load_combination")
                                && term.get("ref_id").and_then(Value::as_str)
                                    == Some(load_combination_id)
                        })
                    })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_referenced_by_combination",
            format!("load combination {load_combination_id} is referenced by another combination"),
        ));
    }
    if model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?
        .iter()
        .any(|feature| {
            feature.get("source_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_unsupported_feature_owned",
            "reference editing refuses a combination referenced by an unsupported feature",
        ));
    }
    if model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?
        .iter()
        .any(|row| {
            row.get("model_ir_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_linear_load_combination_roundtrip_owned",
            "reference editing refuses a combination with a direct round-trip mapping",
        ));
    }

    let edited_terms = {
        let combination = model
            .get_mut("load_combinations")
            .and_then(Value::as_array_mut)
            .and_then(|combinations| combinations.get_mut(load_combination_index))
            .ok_or_else(|| snapshot_error("reference-edited load combination"))?;
        let terms = combination
            .get_mut("terms")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| snapshot_error("reference-edited load-combination terms"))?;
        terms[term_index]["ref_id"] = json!(replacement_load_pattern_id);
        Value::Array(terms.clone())
    };
    Ok(DirectLinearLoadCombinationReferenceEditV1 {
        load_combination_index,
        term_index,
        preserved_factor,
        source_terms,
        edited_terms,
    })
}

#[allow(clippy::too_many_lines)]
fn replace_nested_linear_load_combination_factor(
    model: &mut Value,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    factor: f64,
) -> Result<NestedLinearLoadCombinationFactorEditV1, WorkbenchError> {
    let source_expansion = require_bounded_linear_load_combination(model, load_combination_id)?;
    if !source_expansion.nested {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported",
            "nested factor editing requires a root with at least one load-combination term",
        ));
    }
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    let load_combination_index = load_combinations
        .iter()
        .position(|combination| {
            combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    let combination = &load_combinations[load_combination_index];
    if combination.get("index").and_then(Value::as_u64)
        != u64::try_from(load_combination_index).ok()
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_index_mismatch",
            "edited nested load-combination index must match its contiguous position",
        ));
    }
    if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_type_unsupported",
            "nested factor editing accepts only a linear load combination",
        ));
    }
    if !combination.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_source_owned",
            "nested factor editing accepts only a neutral root combination with null source_id",
        ));
    }
    if !combination
        .get("extensions")
        .and_then(Value::as_object)
        .is_some_and(serde_json::Map::is_empty)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_extensions_unsupported",
            "nested factor editing accepts only a root combination with empty extensions",
        ));
    }
    let terms = combination
        .get("terms")
        .and_then(Value::as_array)
        .filter(|terms| {
            (MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
                ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
                .contains(&terms.len())
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_terms_unsupported",
                "edited nested load-combination root must contain between two and 64 terms",
            )
        })?;
    let mut typed_references = Vec::with_capacity(terms.len());
    let mut term_index = None;
    let mut previous_factor = None;
    for (index, term) in terms.iter().enumerate() {
        let source_reference_kind = match term.get("ref_kind").and_then(Value::as_str) {
            Some("load_pattern") => LinearLoadCombinationReferenceKindV1::LoadPattern,
            Some("load_combination") => LinearLoadCombinationReferenceKindV1::LoadCombination,
            _ => {
                return Err(WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_reference_kind_unsupported",
                    "nested factor editing accepts load_pattern or load_combination root terms only",
                ));
            }
        };
        let source_reference_id = term
            .get("ref_id")
            .and_then(Value::as_str)
            .ok_or_else(|| snapshot_error("nested load-combination term ref_id"))?;
        let source_factor = term
            .get("factor")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite() && *value != 0.0)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_source_factor_unsupported",
                    "source nested load-combination factors must be finite and non-zero",
                )
            })?;
        let typed_reference = format!(
            "{}\u{0}{source_reference_id}",
            source_reference_kind.as_str()
        );
        if typed_references.contains(&typed_reference) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_reference_duplicate",
                "edited nested load-combination root must contain unique typed references",
            ));
        }
        typed_references.push(typed_reference);
        if source_reference_kind == reference_kind && source_reference_id == reference_id {
            term_index = Some(index);
            previous_factor = Some(source_factor);
        }
    }
    let term_index = term_index.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_term_missing",
            format!(
                "load combination {load_combination_id} has no {} term {reference_id}",
                reference_kind.as_str()
            ),
        )
    })?;
    let previous_factor =
        previous_factor.ok_or_else(|| snapshot_error("source nested term factor"))?;
    if load_combinations
        .iter()
        .enumerate()
        .any(|(index, candidate)| {
            index != load_combination_index
                && candidate
                    .get("terms")
                    .and_then(Value::as_array)
                    .is_some_and(|candidate_terms| {
                        candidate_terms.iter().any(|term| {
                            term.get("ref_kind").and_then(Value::as_str) == Some("load_combination")
                                && term.get("ref_id").and_then(Value::as_str)
                                    == Some(load_combination_id)
                        })
                    })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_referenced_by_combination",
            format!("load combination {load_combination_id} is referenced by another combination"),
        ));
    }
    if model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?
        .iter()
        .any(|feature| {
            feature.get("source_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_unsupported_feature_owned",
            "nested factor editing refuses a root referenced by an unsupported feature",
        ));
    }
    if model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?
        .iter()
        .any(|row| {
            row.get("model_ir_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_roundtrip_owned",
            "nested factor editing refuses a root with a direct round-trip mapping",
        ));
    }

    {
        let combination = model
            .get_mut("load_combinations")
            .and_then(Value::as_array_mut)
            .and_then(|combinations| combinations.get_mut(load_combination_index))
            .ok_or_else(|| snapshot_error("edited nested load combination"))?;
        let terms = combination
            .get_mut("terms")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| snapshot_error("edited nested load-combination terms"))?;
        terms[term_index]["factor"] = json!(factor);
    }
    let edited_expansion = require_bounded_linear_load_combination(model, load_combination_id)?;
    if !edited_expansion.nested {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported",
            "edited load-combination root must remain nested",
        ));
    }
    Ok(NestedLinearLoadCombinationFactorEditV1 {
        load_combination_index,
        term_index,
        previous_factor,
        source_expansion,
        edited_expansion,
    })
}

#[allow(clippy::too_many_lines)]
fn replace_nested_linear_load_combination_reference(
    model: &mut Value,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    replacement_reference_kind: LinearLoadCombinationReferenceKindV1,
    replacement_reference_id: &str,
) -> Result<NestedLinearLoadCombinationReferenceEditV1, WorkbenchError> {
    let source_expansion = require_bounded_linear_load_combination(model, load_combination_id)?;
    if !source_expansion.nested {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported",
            "nested reference editing requires a root with at least one load-combination term",
        ));
    }
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    let load_combination_index = load_combinations
        .iter()
        .position(|combination| {
            combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    let combination = &load_combinations[load_combination_index];
    if combination.get("index").and_then(Value::as_u64)
        != u64::try_from(load_combination_index).ok()
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_index_mismatch",
            "edited nested load-combination index must match its contiguous position",
        ));
    }
    if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_type_unsupported",
            "nested reference editing accepts only a linear load combination",
        ));
    }
    if !combination.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_source_owned",
            "nested reference editing accepts only a neutral root combination with null source_id",
        ));
    }
    if !combination
        .get("extensions")
        .and_then(Value::as_object)
        .is_some_and(serde_json::Map::is_empty)
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_extensions_unsupported",
            "nested reference editing accepts only a root combination with empty extensions",
        ));
    }
    let terms = combination
        .get("terms")
        .and_then(Value::as_array)
        .filter(|terms| {
            (MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
                ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
                .contains(&terms.len())
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_terms_unsupported",
                "edited nested load-combination root must contain between two and 64 terms",
            )
        })?;
    let mut typed_references = Vec::with_capacity(terms.len());
    let mut term_index = None;
    let mut preserved_factor = None;
    for (index, term) in terms.iter().enumerate() {
        let source_reference_kind = match term.get("ref_kind").and_then(Value::as_str) {
            Some("load_pattern") => LinearLoadCombinationReferenceKindV1::LoadPattern,
            Some("load_combination") => LinearLoadCombinationReferenceKindV1::LoadCombination,
            _ => {
                return Err(WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_reference_kind_unsupported",
                    "nested reference editing accepts load_pattern or load_combination root terms only",
                ));
            }
        };
        let source_reference_id = term
            .get("ref_id")
            .and_then(Value::as_str)
            .ok_or_else(|| snapshot_error("nested load-combination term ref_id"))?;
        let source_factor = term
            .get("factor")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite() && *value != 0.0)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_source_factor_unsupported",
                    "source nested load-combination factors must be finite and non-zero",
                )
            })?;
        let typed_reference = format!(
            "{}\u{0}{source_reference_id}",
            source_reference_kind.as_str()
        );
        if typed_references.contains(&typed_reference) {
            return Err(WorkbenchError::new(
                "workbench_model_edit_nested_linear_load_combination_reference_duplicate",
                "edited nested load-combination root must contain unique typed references",
            ));
        }
        typed_references.push(typed_reference);
        if source_reference_kind == reference_kind && source_reference_id == reference_id {
            term_index = Some(index);
            preserved_factor = Some(source_factor);
        }
    }
    let term_index = term_index.ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_term_missing",
            format!(
                "load combination {load_combination_id} has no {} term {reference_id}",
                reference_kind.as_str()
            ),
        )
    })?;
    let preserved_factor =
        preserved_factor.ok_or_else(|| snapshot_error("source nested term preserved factor"))?;
    if reference_kind == replacement_reference_kind && reference_id == replacement_reference_id {
        return Err(WorkbenchError::new(
            "workbench_model_edit_no_change",
            "replacement nested typed reference is identical to the source term",
        ));
    }
    let replacement_typed_reference = format!(
        "{}\u{0}{replacement_reference_id}",
        replacement_reference_kind.as_str()
    );
    if typed_references.contains(&replacement_typed_reference) {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_replacement_reference_duplicate",
            format!(
                "replacement {} {replacement_reference_id} already occurs in the root terms",
                replacement_reference_kind.as_str()
            ),
        ));
    }
    match replacement_reference_kind {
        LinearLoadCombinationReferenceKindV1::LoadPattern => {
            let load_patterns = model
                .get("load_patterns")
                .and_then(Value::as_array)
                .ok_or_else(|| snapshot_error("load_patterns"))?;
            let replacement = load_patterns
                .iter()
                .find(|pattern| {
                    pattern.get("id").and_then(Value::as_str)
                        == Some(replacement_reference_id)
                })
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_model_edit_nested_linear_load_combination_replacement_pattern_missing",
                        format!(
                            "ModelIR has no replacement load pattern with identity {replacement_reference_id}"
                        ),
                    )
                })?;
            if replacement.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
                return Err(WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_replacement_pattern_unsupported",
                    format!(
                        "replacement load pattern {replacement_reference_id} is not linear_static"
                    ),
                ));
            }
        }
        LinearLoadCombinationReferenceKindV1::LoadCombination => {
            let replacement = load_combinations
                .iter()
                .find(|candidate| {
                    candidate.get("id").and_then(Value::as_str)
                        == Some(replacement_reference_id)
                })
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_model_edit_nested_linear_load_combination_replacement_combination_missing",
                        format!(
                            "ModelIR has no replacement load combination with identity {replacement_reference_id}"
                        ),
                    )
                })?;
            if replacement.get("combination_type").and_then(Value::as_str) != Some("linear") {
                return Err(WorkbenchError::new(
                    "workbench_model_edit_nested_linear_load_combination_replacement_combination_unsupported",
                    format!(
                        "replacement load combination {replacement_reference_id} is not linear"
                    ),
                ));
            }
        }
    }
    if load_combinations
        .iter()
        .enumerate()
        .any(|(index, candidate)| {
            index != load_combination_index
                && candidate
                    .get("terms")
                    .and_then(Value::as_array)
                    .is_some_and(|candidate_terms| {
                        candidate_terms.iter().any(|term| {
                            term.get("ref_kind").and_then(Value::as_str) == Some("load_combination")
                                && term.get("ref_id").and_then(Value::as_str)
                                    == Some(load_combination_id)
                        })
                    })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_referenced_by_combination",
            format!("load combination {load_combination_id} is referenced by another combination"),
        ));
    }
    if model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?
        .iter()
        .any(|feature| {
            feature.get("source_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_unsupported_feature_owned",
            "nested reference editing refuses a root referenced by an unsupported feature",
        ));
    }
    if model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?
        .iter()
        .any(|row| {
            row.get("model_ir_entity_id").and_then(Value::as_str) == Some(load_combination_id)
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_roundtrip_owned",
            "nested reference editing refuses a root with a direct round-trip mapping",
        ));
    }

    {
        let combination = model
            .get_mut("load_combinations")
            .and_then(Value::as_array_mut)
            .and_then(|combinations| combinations.get_mut(load_combination_index))
            .ok_or_else(|| snapshot_error("reference-edited nested load combination"))?;
        let terms = combination
            .get_mut("terms")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| snapshot_error("reference-edited nested load-combination terms"))?;
        terms[term_index]["ref_kind"] = json!(replacement_reference_kind.as_str());
        terms[term_index]["ref_id"] = json!(replacement_reference_id);
    }
    let edited_expansion = require_bounded_linear_load_combination(model, load_combination_id)?;
    if !edited_expansion.nested {
        return Err(WorkbenchError::new(
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported",
            "reference-edited load-combination root must remain nested",
        ));
    }
    Ok(NestedLinearLoadCombinationReferenceEditV1 {
        load_combination_index,
        term_index,
        preserved_factor,
        source_expansion,
        edited_expansion,
    })
}

fn append_nested_linear_load_combination(
    model: &mut Value,
    load_combination_id: &str,
    terms: &[NestedLinearLoadCombinationTermV1],
) -> Result<usize, WorkbenchError> {
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    if load_combinations.iter().any(|combination| {
        combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_add_nested_linear_load_combination_identity_exists",
            format!("ModelIR already has a load combination with identity {load_combination_id}"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns
        .iter()
        .any(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_combination_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_nested_linear_load_combination_identity_ambiguous",
            format!("identity {load_combination_id} already names a load pattern"),
        ));
    }
    for term in terms {
        match term.reference_kind {
            LinearLoadCombinationReferenceKindV1::LoadPattern => {
                let pattern = load_patterns
                    .iter()
                    .find(|pattern| {
                        pattern.get("id").and_then(Value::as_str)
                            == Some(term.reference_id.as_str())
                    })
                    .ok_or_else(|| {
                        WorkbenchError::new(
                            "workbench_model_add_nested_linear_load_combination_pattern_missing",
                            format!(
                                "ModelIR has no load pattern with identity {}",
                                term.reference_id
                            ),
                        )
                    })?;
                if pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
                    return Err(WorkbenchError::new(
                        "workbench_model_add_nested_linear_load_combination_pattern_unsupported",
                        format!("load pattern {} is not linear_static", term.reference_id),
                    ));
                }
            }
            LinearLoadCombinationReferenceKindV1::LoadCombination => {
                let combination = load_combinations
                    .iter()
                    .find(|combination| {
                        combination.get("id").and_then(Value::as_str)
                            == Some(term.reference_id.as_str())
                    })
                    .ok_or_else(|| {
                        WorkbenchError::new(
                            "workbench_model_add_nested_linear_load_combination_combination_missing",
                            format!(
                                "ModelIR has no load combination with identity {}",
                                term.reference_id
                            ),
                        )
                    })?;
                if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
                    return Err(WorkbenchError::new(
                        "workbench_model_add_nested_linear_load_combination_combination_unsupported",
                        format!("load combination {} is not linear", term.reference_id),
                    ));
                }
            }
        }
    }
    let load_combination_index = load_combinations.len();
    model
        .get_mut("load_combinations")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_combinations"))?
        .push(json!({
            "id": load_combination_id,
            "index": load_combination_index,
            "combination_type": "linear",
            "terms": nested_linear_load_combination_terms_value(terms),
            "source_id": null,
            "extensions": {}
        }));
    Ok(load_combination_index)
}

fn nested_linear_load_combination_terms_value(
    terms: &[NestedLinearLoadCombinationTermV1],
) -> Value {
    Value::Array(
        terms
            .iter()
            .map(|term| {
                json!({
                    "ref_id": term.reference_id,
                    "ref_kind": term.reference_kind.as_str(),
                    "factor": term.factor
                })
            })
            .collect(),
    )
}

#[allow(clippy::too_many_lines)]
fn remove_linear_load_combination(
    model: &mut Value,
    load_combination_id: &str,
) -> Result<RemovedLinearLoadCombinationV1, WorkbenchError> {
    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    let load_combination_index = load_combinations
        .iter()
        .position(|combination| {
            combination.get("id").and_then(Value::as_str) == Some(load_combination_id)
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_combination_missing",
                format!("ModelIR has no load combination with identity {load_combination_id}"),
            )
        })?;
    if load_combination_index + 1 != load_combinations.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_not_terminal",
            "deleted load combination must be the last contiguous load-combination row",
        ));
    }
    let load_combination = &load_combinations[load_combination_index];
    if load_combination.get("index").and_then(Value::as_u64)
        != u64::try_from(load_combination_index).ok()
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_index_mismatch",
            "deleted load-combination index must match its last contiguous position",
        ));
    }
    if load_combination
        .get("combination_type")
        .and_then(Value::as_str)
        != Some("linear")
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_type_unsupported",
            "linear-load-combination deletion accepts only a linear combination",
        ));
    }
    if !load_combination
        .get("source_id")
        .is_some_and(Value::is_null)
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_source_owned",
            "linear-load-combination deletion accepts only a neutral row with null source_id",
        ));
    }
    if !load_combination
        .get("extensions")
        .and_then(Value::as_object)
        .is_some_and(serde_json::Map::is_empty)
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_extensions_unsupported",
            "linear-load-combination deletion accepts only a row with empty extensions",
        ));
    }
    let terms = load_combination
        .get("terms")
        .and_then(Value::as_array)
        .filter(|terms| {
            (MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
                ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
                .contains(&terms.len())
        })
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_combination_terms_unsupported",
                "deleted direct linear load combination must contain between two and 64 terms",
            )
        })?;
    let nested = terms
        .iter()
        .any(|term| term.get("ref_kind").and_then(Value::as_str) == Some("load_combination"));
    let expansion = if nested {
        let mut typed_references = Vec::with_capacity(terms.len());
        for term in terms {
            let reference_kind = term
                .get("ref_kind")
                .and_then(Value::as_str)
                .filter(|kind| matches!(*kind, "load_pattern" | "load_combination"))
                .ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_model_delete_nested_linear_load_combination_reference_kind_unsupported",
                        "deleted nested load-combination terms must use explicit load_pattern or load_combination references",
                    )
                })?;
            let reference_id = term
                .get("ref_id")
                .and_then(Value::as_str)
                .ok_or_else(|| snapshot_error("nested load-combination term ref_id"))?;
            if !term
                .get("factor")
                .and_then(Value::as_f64)
                .is_some_and(|factor| factor.is_finite() && factor != 0.0)
            {
                return Err(WorkbenchError::new(
                    "workbench_model_delete_nested_linear_load_combination_factor_unsupported",
                    "deleted nested load-combination terms must have finite nonzero factors",
                ));
            }
            if typed_references.contains(&(reference_kind, reference_id)) {
                return Err(WorkbenchError::new(
                    "workbench_model_delete_nested_linear_load_combination_reference_duplicate",
                    "deleted nested load-combination root terms must use unique typed references",
                ));
            }
            typed_references.push((reference_kind, reference_id));
        }
        let bounded = require_bounded_linear_load_combination(model, load_combination_id).map_err(
            |error| {
                WorkbenchError::new(
                    "workbench_model_delete_nested_linear_load_combination_profile_unsupported",
                    error.to_string(),
                )
            },
        )?;
        if !bounded.nested {
            return Err(snapshot_error("nested load-combination deletion profile"));
        }
        Some(bounded)
    } else {
        let load_patterns = model
            .get("load_patterns")
            .and_then(Value::as_array)
            .ok_or_else(|| snapshot_error("load_patterns"))?;
        let mut term_ids = Vec::with_capacity(terms.len());
        for term in terms {
            if term.get("ref_kind").and_then(Value::as_str) != Some("load_pattern") {
                return Err(WorkbenchError::new(
                    "workbench_model_delete_linear_load_combination_nested_unsupported",
                    "deleted direct linear load combination must reference load patterns only",
                ));
            }
            let ref_id = term
                .get("ref_id")
                .and_then(Value::as_str)
                .ok_or_else(|| snapshot_error("load-combination term ref_id"))?;
            if !term
                .get("factor")
                .and_then(Value::as_f64)
                .is_some_and(|factor| factor.is_finite() && factor != 0.0)
            {
                return Err(WorkbenchError::new(
                    "workbench_model_delete_linear_load_combination_factor_unsupported",
                    "deleted linear load-combination terms must have finite nonzero factors",
                ));
            }
            if !load_patterns.iter().any(|pattern| {
                pattern.get("id").and_then(Value::as_str) == Some(ref_id)
                    && pattern.get("analysis_type").and_then(Value::as_str) == Some("linear_static")
            }) {
                return Err(WorkbenchError::new(
                    "workbench_model_delete_linear_load_combination_pattern_unsupported",
                    format!(
                        "deleted combination term {ref_id} is not an existing linear_static pattern"
                    ),
                ));
            }
            term_ids.push(ref_id);
        }
        if term_ids
            .iter()
            .enumerate()
            .any(|(index, id)| term_ids[..index].iter().any(|prior| prior == id))
        {
            return Err(WorkbenchError::new(
                "workbench_model_delete_linear_load_combination_pattern_duplicate",
                "deleted direct linear load combination must reference unique patterns",
            ));
        }
        None
    };
    if load_combinations
        .iter()
        .enumerate()
        .filter(|(index, _)| *index != load_combination_index)
        .any(|(_, combination)| {
            combination
                .get("terms")
                .and_then(Value::as_array)
                .is_some_and(|candidate_terms| {
                    candidate_terms.iter().any(|term| {
                        term.get("ref_kind").and_then(Value::as_str) == Some("load_combination")
                            && term.get("ref_id").and_then(Value::as_str)
                                == Some(load_combination_id)
                    })
                })
        })
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_referenced_by_combination",
            format!("load combination {load_combination_id} is referenced by another combination"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features.iter().any(|feature| {
        feature.get("source_entity_id").and_then(Value::as_str) == Some(load_combination_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_unsupported_feature_owned",
            "linear-load-combination deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows.iter().any(|row| {
        row.get("model_ir_entity_id").and_then(Value::as_str) == Some(load_combination_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_combination_roundtrip_owned",
            "linear-load-combination deletion refuses a row with a direct round-trip mapping",
        ));
    }

    let removed_terms = Value::Array(terms.clone());
    let profile = if nested {
        LinearLoadCombinationDeletionProfileV1::NestedV3
    } else if terms.len() == 2 {
        LinearLoadCombinationDeletionProfileV1::ExactTwoV1
    } else {
        LinearLoadCombinationDeletionProfileV1::DirectV2
    };
    model
        .get_mut("load_combinations")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_combinations"))?
        .pop()
        .ok_or_else(|| snapshot_error("last load combination"))?;
    Ok(RemovedLinearLoadCombinationV1 {
        load_combination_index,
        terms: removed_terms,
        profile,
        expansion,
    })
}

#[allow(clippy::too_many_lines)]
fn remove_linear_load_pattern(
    model: &mut Value,
    load_pattern_id: &str,
) -> Result<RemovedLinearLoadPatternV1, WorkbenchError> {
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns.len() <= 1 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_minimum_model",
            "linear-load-pattern deletion must retain at least one load pattern",
        ));
    }
    let load_pattern_index = load_patterns
        .iter()
        .position(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_pattern_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_pattern_missing",
                format!("ModelIR has no load pattern with identity {load_pattern_id}"),
            )
        })?;
    if load_pattern_index + 1 != load_patterns.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_not_terminal",
            "deleted load pattern must be the last contiguous load-pattern row",
        ));
    }
    let load_pattern = &load_patterns[load_pattern_index];
    if load_pattern.get("index").and_then(Value::as_u64) != u64::try_from(load_pattern_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_index_mismatch",
            "deleted load-pattern index must match its last contiguous position",
        ));
    }
    if load_pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_type_unsupported",
            "linear-load-pattern deletion accepts only a linear_static pattern",
        ));
    }
    if !load_pattern.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_source_owned",
            "linear-load-pattern deletion accepts only a neutral pattern with null source_id",
        ));
    }
    let self_weight = load_pattern
        .get("self_weight")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_pattern_self_weight_unsupported",
                "deleted load pattern must contain exactly three self-weight components",
            )
        })?;
    for value in self_weight {
        let value = value
            .as_f64()
            .filter(|value| value.is_finite())
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_delete_linear_load_pattern_self_weight_unsupported",
                    "deleted load-pattern self weight must contain finite SI values",
                )
            })?;
        if value != 0.0 {
            return Err(WorkbenchError::new(
                "workbench_model_delete_linear_load_pattern_self_weight_unsupported",
                "deleted load pattern must have zero self weight",
            ));
        }
    }
    let nodal_loads = load_pattern
        .get("nodal_loads")
        .and_then(Value::as_array)
        .filter(|loads| loads.len() == 1)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_pattern_single_load_required",
                "deleted load pattern must contain exactly one nodal load",
            )
        })?;
    let nodal_load = &nodal_loads[0];
    let nodal_load_id = nodal_load
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("nodal load id"))?
        .to_owned();
    if nodal_load.get("index").and_then(Value::as_u64) != Some(0) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_load_index_mismatch",
            "deleted pattern's sole nodal-load index must be zero",
        ));
    }
    if !nodal_load.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_load_source_owned",
            "linear-load-pattern deletion accepts only a neutral nested load with null source_id",
        ));
    }
    let node_id = nodal_load
        .get("node_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("nodal load node_id"))?
        .to_owned();
    let components = nodal_load
        .get("components_si")
        .and_then(Value::as_object)
        .filter(|values| values.len() == NODAL_LOAD_COMPONENT_KEYS.len())
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_load_pattern_components_invalid",
                "deleted pattern's nodal load must contain exactly six SI components",
            )
        })?;
    let mut nonzero = false;
    for component in NODAL_LOAD_COMPONENT_KEYS {
        let value = components
            .get(component)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_delete_linear_load_pattern_components_invalid",
                    format!("deleted pattern's nodal load has no {component} component"),
                )
            })?
            .as_f64()
            .filter(|value| value.is_finite())
            .ok_or_else(|| snapshot_error("nodal load component"))?;
        nonzero = nonzero || value != 0.0;
    }
    if !nonzero {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_zero_components",
            "deleted pattern's nodal load must contain at least one nonzero SI component",
        ));
    }

    let load_combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_combinations"))?;
    if load_combinations.iter().any(|combination| {
        combination
            .get("terms")
            .and_then(Value::as_array)
            .is_some_and(|terms| {
                terms.iter().any(|term| {
                    term.get("ref_kind").and_then(Value::as_str) == Some("load_pattern")
                        && term.get("ref_id").and_then(Value::as_str) == Some(load_pattern_id)
                })
            })
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_referenced_by_combination",
            format!("load pattern {load_pattern_id} is referenced by a load combination"),
        ));
    }
    let construction_stages = model
        .get("construction_stages")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("construction_stages"))?;
    if construction_stages.iter().any(|stage| {
        stage
            .get("load_pattern_ids")
            .and_then(Value::as_array)
            .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(load_pattern_id)))
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_referenced_by_stage",
            format!("load pattern {load_pattern_id} is referenced by a construction stage"),
        ));
    }
    let removed_ids = [load_pattern_id, nodal_load_id.as_str()];
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features.iter().any(|feature| {
        feature
            .get("source_entity_id")
            .and_then(Value::as_str)
            .is_some_and(|id| removed_ids.contains(&id))
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_unsupported_feature_owned",
            "linear-load-pattern deletion refuses a pattern or nested load owned by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows.iter().any(|row| {
        row.get("model_ir_entity_id")
            .and_then(Value::as_str)
            .is_some_and(|id| removed_ids.contains(&id))
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_load_pattern_roundtrip_owned",
            "linear-load-pattern deletion refuses a pattern or nested load with a direct round-trip mapping",
        ));
    }

    let components_si = nodal_load["components_si"].clone();
    model
        .get_mut("load_patterns")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("load_patterns"))?
        .pop()
        .ok_or_else(|| snapshot_error("last load pattern"))?;
    Ok(RemovedLinearLoadPatternV1 {
        load_pattern_index,
        nodal_load_id,
        node_id,
        components_si,
    })
}

fn append_linear_material(
    model: &mut Value,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<usize, WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    if materials
        .iter()
        .any(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_linear_material_identity_exists",
            format!("ModelIR already has a material with identity {material_id}"),
        ));
    }
    let material_index = materials.len();
    model
        .get_mut("materials")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("materials"))?
        .push(json!({
            "id": material_id,
            "index": material_index,
            "law_id": "linear_elastic_isotropic",
            "parameter_set_version": "1",
            "parameters": linear_material_parameters_object(parameters),
            "state_schema": linear_material_state_schema_object(),
            "source_id": null,
            "extensions": {}
        }));
    Ok(material_index)
}

#[allow(clippy::too_many_lines)]
fn remove_linear_material(
    model: &mut Value,
    material_id: &str,
) -> Result<RemovedLinearMaterialV1, WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    if materials.len() <= 1 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_minimum_model",
            "linear-material deletion must retain at least one material",
        ));
    }
    let material_index = materials
        .iter()
        .position(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material_index + 1 != materials.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_not_terminal",
            "deleted material must be the last contiguous material row",
        ));
    }
    let material = &materials[material_index];
    if material.get("index").and_then(Value::as_u64) != u64::try_from(material_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_index_mismatch",
            "deleted material index must match its last contiguous position",
        ));
    }
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_law_unsupported",
            "linear-material deletion accepts only a linear_elastic_isotropic material",
        ));
    }
    if material
        .get("parameter_set_version")
        .and_then(Value::as_str)
        != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_version_unsupported",
            "linear-material deletion accepts only parameter_set_version 1",
        ));
    }
    if !material.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_source_owned",
            "linear-material deletion accepts only a neutral row with null source_id",
        ));
    }
    let parameters = material
        .get("parameters")
        .and_then(Value::as_object)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_material_parameters_invalid",
                "deleted linear material must contain exactly three SI parameters",
            )
        })?;
    let read_parameter = |key: &'static str| {
        parameters
            .get(key)
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite())
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_model_delete_linear_material_parameters_invalid",
                    format!("deleted linear material has no finite {key}"),
                )
            })
    };
    let elastic_modulus_pa = read_parameter("elastic_modulus_pa")?;
    let poisson_ratio = read_parameter("poisson_ratio")?;
    let density_kg_m3 = read_parameter("density_kg_m3")?;
    if elastic_modulus_pa <= 0.0
        || poisson_ratio <= -1.0
        || poisson_ratio >= 0.5
        || density_kg_m3 < 0.0
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_parameters_invalid",
            "deleted linear material parameters are outside the closed v1 physical ranges",
        ));
    }
    let state_schema = material
        .get("state_schema")
        .and_then(Value::as_object)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_linear_material_state_schema_unsupported",
                "deleted linear material must contain the exact stateless v1 state schema",
            )
        })?;
    if state_schema.get("stateful").and_then(Value::as_bool) != Some(false)
        || state_schema
            .get("state_update_epoch")
            .and_then(Value::as_str)
            != Some("none")
        || state_schema
            .get("supports_trial_commit_rollback")
            .and_then(Value::as_bool)
            != Some(true)
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_state_schema_unsupported",
            "deleted linear material must use the exact stateless v1 state schema",
        ));
    }

    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements
        .iter()
        .any(|element| element.get("material_id").and_then(Value::as_str) == Some(material_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_referenced_by_element",
            format!("material {material_id} is referenced by an element"),
        ));
    }
    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    if sections.iter().any(|section| {
        section.get("steel_material_id").and_then(Value::as_str) == Some(material_id)
            || section.get("concrete_material_id").and_then(Value::as_str) == Some(material_id)
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_referenced_by_section",
            format!("material {material_id} is referenced by a section"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features
        .iter()
        .any(|feature| feature.get("source_entity_id").and_then(Value::as_str) == Some(material_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_unsupported_feature_owned",
            "linear-material deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(material_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_linear_material_roundtrip_owned",
            "linear-material deletion refuses a row with a direct round-trip mapping",
        ));
    }

    let parameters_si = material["parameters"].clone();
    let state_schema = material["state_schema"].clone();
    model
        .get_mut("materials")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("materials"))?
        .pop()
        .ok_or_else(|| snapshot_error("last material"))?;
    Ok(RemovedLinearMaterialV1 {
        material_index,
        parameters_si,
        state_schema,
    })
}

fn append_frame_section(
    model: &mut Value,
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<usize, WorkbenchError> {
    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    if sections
        .iter()
        .any(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame_section_identity_exists",
            format!("ModelIR already has a section with identity {section_id}"),
        ));
    }
    let section_index = sections.len();
    model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?
        .push(json!({
            "id": section_id,
            "index": section_index,
            "family_id": "frame_3d",
            "parameter_set_version": "1",
            "parameters": frame_section_parameters_object(parameters),
            "source_id": null,
            "extensions": {}
        }));
    Ok(section_index)
}

#[allow(clippy::too_many_lines)]
fn remove_frame_section(
    model: &mut Value,
    section_id: &str,
) -> Result<RemovedFrameSectionV1, WorkbenchError> {
    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    if sections.len() <= 1 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_minimum_model",
            "frame-section deletion must retain at least one section",
        ));
    }
    let section_index = sections
        .iter()
        .position(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_frame_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section_index + 1 != sections.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_not_terminal",
            "deleted frame section must be the last contiguous section row",
        ));
    }
    let section = &sections[section_index];
    if section.get("index").and_then(Value::as_u64) != u64::try_from(section_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_index_mismatch",
            "deleted frame-section index must match its last contiguous position",
        ));
    }
    if section.get("family_id").and_then(Value::as_str) != Some("frame_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_family_unsupported",
            "frame-section deletion accepts only a frame_3d section",
        ));
    }
    if section.get("parameter_set_version").and_then(Value::as_str) != Some("1") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_version_unsupported",
            "frame-section deletion accepts only parameter_set_version 1",
        ));
    }
    if !section.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_source_owned",
            "frame-section deletion accepts only a neutral row with null source_id",
        ));
    }
    let parameters = section
        .get("parameters")
        .and_then(Value::as_object)
        .filter(|values| values.len() == 6)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_frame_section_parameters_invalid",
                "deleted frame section must contain exactly six SI parameters",
            )
        })?;
    for key in [
        "area_m2",
        "iy_m4",
        "iz_m4",
        "torsional_constant_m4",
        "shear_area_y_m2",
        "shear_area_z_m2",
    ] {
        if !parameters
            .get(key)
            .and_then(Value::as_f64)
            .is_some_and(|value| value.is_finite() && value > 0.0)
        {
            return Err(WorkbenchError::new(
                "workbench_model_delete_frame_section_parameters_invalid",
                format!("deleted frame section has no finite positive {key}"),
            ));
        }
    }

    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements
        .iter()
        .any(|element| element.get("section_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_referenced_by_element",
            format!("section {section_id} is referenced by an element"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features
        .iter()
        .any(|feature| feature.get("source_entity_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_unsupported_feature_owned",
            "frame-section deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_frame_section_roundtrip_owned",
            "frame-section deletion refuses a row with a direct round-trip mapping",
        ));
    }

    let parameters_si = section["parameters"].clone();
    model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?
        .pop()
        .ok_or_else(|| snapshot_error("last section"))?;
    Ok(RemovedFrameSectionV1 {
        section_index,
        parameters_si,
    })
}

fn append_truss_section(
    model: &mut Value,
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<usize, WorkbenchError> {
    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    if sections
        .iter()
        .any(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss_section_identity_exists",
            format!("ModelIR already has a section with identity {section_id}"),
        ));
    }
    let section_index = sections.len();
    model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?
        .push(json!({
            "id": section_id,
            "index": section_index,
            "family_id": "truss_3d",
            "parameter_set_version": "1",
            "parameters": truss_section_parameters_object(parameters),
            "source_id": null,
            "extensions": {}
        }));
    Ok(section_index)
}

#[allow(clippy::too_many_lines)]
fn remove_truss_section(
    model: &mut Value,
    section_id: &str,
) -> Result<RemovedTrussSectionV1, WorkbenchError> {
    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section_index = sections
        .iter()
        .position(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_truss_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section_index + 1 != sections.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_not_terminal",
            "deleted truss section must be the last contiguous section row",
        ));
    }
    let section = &sections[section_index];
    if section.get("index").and_then(Value::as_u64) != u64::try_from(section_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_index_mismatch",
            "deleted truss-section index must match its last contiguous position",
        ));
    }
    if section.get("family_id").and_then(Value::as_str) != Some("truss_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_family_unsupported",
            "truss-section deletion accepts only a truss_3d section",
        ));
    }
    if section.get("parameter_set_version").and_then(Value::as_str) != Some("1") {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_version_unsupported",
            "truss-section deletion accepts only parameter_set_version 1",
        ));
    }
    if !section.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_source_owned",
            "truss-section deletion accepts only a neutral row with null source_id",
        ));
    }
    let parameters = section
        .get("parameters")
        .and_then(Value::as_object)
        .filter(|values| values.len() == 1)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_truss_section_parameters_invalid",
                "deleted truss section must contain exactly one SI parameter",
            )
        })?;
    if !parameters
        .get("area_m2")
        .and_then(Value::as_f64)
        .is_some_and(|value| value.is_finite() && value > 0.0)
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_parameters_invalid",
            "deleted truss section must have a finite positive area_m2",
        ));
    }
    if sections
        .iter()
        .filter(|row| row.get("family_id").and_then(Value::as_str) == Some("truss_3d"))
        .count()
        <= 1
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_minimum_family",
            "truss-section deletion must retain at least one truss_3d section",
        ));
    }

    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements
        .iter()
        .any(|element| element.get("section_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_referenced_by_element",
            format!("section {section_id} is referenced by an element"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features
        .iter()
        .any(|feature| feature.get("source_entity_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_unsupported_feature_owned",
            "truss-section deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(section_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_truss_section_roundtrip_owned",
            "truss-section deletion refuses a row with a direct round-trip mapping",
        ));
    }

    let parameters_si = section["parameters"].clone();
    model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?
        .pop()
        .ok_or_else(|| snapshot_error("last section"))?;
    Ok(RemovedTrussSectionV1 {
        section_index,
        parameters_si,
    })
}

fn replace_constraint_value(
    model: &mut Value,
    constraint_id: &str,
    dof: &str,
    value_si: f64,
) -> Result<f64, WorkbenchError> {
    let constraints = model
        .get_mut("constraints")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("constraints"))?;
    let constraint = constraints
        .iter_mut()
        .find(|constraint| constraint.get("id").and_then(Value::as_str) == Some(constraint_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_constraint_missing",
                format!("ModelIR has no constraint with identity {constraint_id}"),
            )
        })?;
    let restrained = constraint
        .get("dofs")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("constraint dofs"))?
        .iter()
        .any(|candidate| candidate.as_str() == Some(dof));
    if !restrained {
        return Err(WorkbenchError::new(
            "workbench_model_edit_constraint_dof_not_restrained",
            format!("constraint {constraint_id} does not restrain DOF {dof}"),
        ));
    }
    let prescribed = constraint
        .get_mut("prescribed_values_si")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("constraint prescribed_values_si"))?;
    let previous_value_si = prescribed
        .get(dof)
        .map(|value| finite_number(value, "constraint prescribed value"))
        .transpose()?
        .unwrap_or(0.0);
    prescribed.insert(dof.to_owned(), json!(value_si));
    Ok(previous_value_si)
}

fn replace_linear_material_parameters(
    model: &mut Value,
    material_id: &str,
    parameters: LinearElasticMaterialParametersV1,
) -> Result<LinearElasticMaterialParametersV1, WorkbenchError> {
    let materials = model
        .get_mut("materials")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("materials"))?;
    let material = materials
        .iter_mut()
        .find(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_material_law_unsupported",
            format!("material {material_id} is not a linear_elastic_isotropic material"),
        ));
    }
    if material
        .get("parameter_set_version")
        .and_then(Value::as_str)
        != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_material_version_unsupported",
            format!("material {material_id} does not use parameter_set_version 1"),
        ));
    }
    let previous = material
        .get("parameters")
        .and_then(Value::as_object)
        .ok_or_else(|| snapshot_error("material parameters"))?;
    let previous_parameters = LinearElasticMaterialParametersV1 {
        elastic_modulus_pa: previous
            .get("elastic_modulus_pa")
            .ok_or_else(|| snapshot_error("material elastic_modulus_pa"))
            .and_then(|value| finite_number(value, "material elastic_modulus_pa"))?,
        poisson_ratio: previous
            .get("poisson_ratio")
            .ok_or_else(|| snapshot_error("material poisson_ratio"))
            .and_then(|value| finite_number(value, "material poisson_ratio"))?,
        density_kg_m3: previous
            .get("density_kg_m3")
            .ok_or_else(|| snapshot_error("material density_kg_m3"))
            .and_then(|value| finite_number(value, "material density_kg_m3"))?,
    };
    material
        .as_object_mut()
        .ok_or_else(|| snapshot_error("material"))?
        .insert(
            "parameters".to_owned(),
            linear_material_parameters_object(parameters),
        );
    Ok(previous_parameters)
}

fn replace_frame_section_parameters(
    model: &mut Value,
    section_id: &str,
    parameters: FrameSectionParametersV1,
) -> Result<FrameSectionParametersV1, WorkbenchError> {
    let sections = model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter_mut()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("frame_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_section_family_unsupported",
            format!("section {section_id} is not a frame_3d section"),
        ));
    }
    if section.get("parameter_set_version").and_then(Value::as_str) != Some("1") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_section_version_unsupported",
            format!("section {section_id} does not use parameter_set_version 1"),
        ));
    }
    let previous = section
        .get("parameters")
        .and_then(Value::as_object)
        .ok_or_else(|| snapshot_error("section parameters"))?;
    let read = |key, field| {
        previous
            .get(key)
            .ok_or_else(|| snapshot_error(field))
            .and_then(|value| finite_number(value, field))
    };
    let previous_parameters = FrameSectionParametersV1 {
        area_m2: read("area_m2", "section area_m2")?,
        iy_m4: read("iy_m4", "section iy_m4")?,
        iz_m4: read("iz_m4", "section iz_m4")?,
        torsional_constant_m4: read("torsional_constant_m4", "section torsional_constant_m4")?,
        shear_area_y_m2: read("shear_area_y_m2", "section shear_area_y_m2")?,
        shear_area_z_m2: read("shear_area_z_m2", "section shear_area_z_m2")?,
    };
    section
        .as_object_mut()
        .ok_or_else(|| snapshot_error("section"))?
        .insert(
            "parameters".to_owned(),
            frame_section_parameters_object(parameters),
        );
    Ok(previous_parameters)
}

fn replace_truss_section_parameters(
    model: &mut Value,
    section_id: &str,
    parameters: TrussSectionParametersV1,
) -> Result<TrussSectionParametersV1, WorkbenchError> {
    let sections = model
        .get_mut("sections")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter_mut()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_truss_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("truss_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_section_family_unsupported",
            format!("section {section_id} is not a truss_3d section"),
        ));
    }
    if section.get("parameter_set_version").and_then(Value::as_str) != Some("1") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_section_version_unsupported",
            format!("section {section_id} does not use parameter_set_version 1"),
        ));
    }
    let previous_area_m2 = section
        .get("parameters")
        .and_then(Value::as_object)
        .and_then(|parameters| parameters.get("area_m2"))
        .ok_or_else(|| snapshot_error("truss section area_m2"))
        .and_then(|value| finite_number(value, "truss section area_m2"))?;
    section
        .as_object_mut()
        .ok_or_else(|| snapshot_error("section"))?
        .insert(
            "parameters".to_owned(),
            truss_section_parameters_object(parameters),
        );
    Ok(TrussSectionParametersV1 {
        area_m2: previous_area_m2,
    })
}

fn replace_frame_element_orientation(
    model: &mut Value,
    element_id: &str,
    local_axis_rotation_rad: f64,
) -> Result<(f64, String), WorkbenchError> {
    let elements = model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?;
    let element = elements
        .iter_mut()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_element_missing",
                format!("ModelIR has no element with identity {element_id}"),
            )
        })?;
    if element.get("type").and_then(Value::as_str) != Some("frame_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_element_type_unsupported",
            format!("element {element_id} is not a frame_3d element"),
        ));
    }
    let formulation = element
        .get("formulation")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element formulation"))?
        .to_owned();
    let previous_local_axis_rotation_rad = element
        .get("local_axis_rotation_rad")
        .ok_or_else(|| snapshot_error("element local_axis_rotation_rad"))
        .and_then(|value| finite_number(value, "element local_axis_rotation_rad"))?;
    element
        .as_object_mut()
        .ok_or_else(|| snapshot_error("element"))?
        .insert(
            "local_axis_rotation_rad".to_owned(),
            json!(local_axis_rotation_rad),
        );
    Ok((previous_local_axis_rotation_rad, formulation))
}

fn replace_frame_element_properties(
    model: &mut Value,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(String, String, String), WorkbenchError> {
    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    let element = elements
        .iter()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_element_missing",
                format!("ModelIR has no element with identity {element_id}"),
            )
        })?;
    if element.get("type").and_then(Value::as_str) != Some("frame_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_element_type_unsupported",
            format!("element {element_id} is not a frame_3d element"),
        ));
    }
    let formulation = element
        .get("formulation")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element formulation"))?
        .to_owned();
    let previous_material_id = element
        .get("material_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element material_id"))?
        .to_owned();
    let previous_section_id = element
        .get("section_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element section_id"))?
        .to_owned();
    validate_frame_element_property_references(model, material_id, section_id)?;
    let element = model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?
        .iter_mut()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| snapshot_error("element"))?;
    let object = element
        .as_object_mut()
        .ok_or_else(|| snapshot_error("element"))?;
    object.insert("material_id".to_owned(), json!(material_id));
    object.insert("section_id".to_owned(), json!(section_id));
    Ok((previous_material_id, previous_section_id, formulation))
}

fn validate_frame_element_property_references(
    model: &Value,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    let material = materials
        .iter()
        .find(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_frame_element_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic")
        || material
            .get("parameter_set_version")
            .and_then(Value::as_str)
            != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_frame_element_material_unsupported",
            "frame_3d element assignment requires a v1 linear_elastic_isotropic material",
        ));
    }

    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_frame_element_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("frame_3d")
        || section.get("parameter_set_version").and_then(Value::as_str) != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_frame_element_section_unsupported",
            "frame_3d element assignment requires a v1 frame_3d section",
        ));
    }
    Ok(())
}

fn replace_truss_element_properties(
    model: &mut Value,
    element_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(String, String, String), WorkbenchError> {
    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    let element = elements
        .iter()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_truss_element_missing",
                format!("ModelIR has no element with identity {element_id}"),
            )
        })?;
    if element.get("type").and_then(Value::as_str) != Some("truss_3d") {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_element_type_unsupported",
            format!("element {element_id} is not a truss_3d element"),
        ));
    }
    let formulation = element
        .get("formulation")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element formulation"))?
        .to_owned();
    let previous_material_id = element
        .get("material_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element material_id"))?
        .to_owned();
    let previous_section_id = element
        .get("section_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element section_id"))?
        .to_owned();
    validate_truss_element_property_references(model, material_id, section_id)?;
    let element = model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?
        .iter_mut()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| snapshot_error("element"))?;
    let object = element
        .as_object_mut()
        .ok_or_else(|| snapshot_error("element"))?;
    object.insert("material_id".to_owned(), json!(material_id));
    object.insert("section_id".to_owned(), json!(section_id));
    Ok((previous_material_id, previous_section_id, formulation))
}

fn validate_truss_element_property_references(
    model: &Value,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    let material = materials
        .iter()
        .find(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_truss_element_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic")
        || material
            .get("parameter_set_version")
            .and_then(Value::as_str)
            != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_element_material_unsupported",
            "truss_3d element assignment requires a v1 linear_elastic_isotropic material",
        ));
    }

    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_truss_element_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("truss_3d")
        || section.get("parameter_set_version").and_then(Value::as_str) != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_edit_truss_element_section_unsupported",
            "truss_3d element assignment requires a v1 truss_3d section",
        ));
    }
    Ok(())
}

fn replace_element_connectivity(
    model: &mut Value,
    element_id: &str,
    node_ids: [&str; 2],
) -> Result<([String; 2], String, String), WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    for node_id in node_ids {
        if !nodes
            .iter()
            .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
        {
            return Err(WorkbenchError::new(
                "workbench_model_edit_connectivity_node_missing",
                format!("ModelIR has no endpoint node with identity {node_id}"),
            ));
        }
    }

    let elements = model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?;
    let element = elements
        .iter_mut()
        .find(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_edit_element_missing",
                format!("ModelIR has no element with identity {element_id}"),
            )
        })?;
    let element_type = element
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element type"))?
        .to_owned();
    let formulation = element
        .get("formulation")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("element formulation"))?
        .to_owned();
    let previous = element
        .get("node_ids")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 2)
        .ok_or_else(|| snapshot_error("element node_ids"))?;
    let previous_node_ids = [
        previous[0]
            .as_str()
            .ok_or_else(|| snapshot_error("element i-node identity"))?
            .to_owned(),
        previous[1]
            .as_str()
            .ok_or_else(|| snapshot_error("element j-node identity"))?
            .to_owned(),
    ];
    element
        .as_object_mut()
        .ok_or_else(|| snapshot_error("element"))?
        .insert("node_ids".to_owned(), json!([node_ids[0], node_ids[1]]));
    Ok((previous_node_ids, element_type, formulation))
}

fn append_node(
    model: &mut Value,
    node_id: &str,
    coordinates_m: [f64; 3],
) -> Result<usize, WorkbenchError> {
    let nodes = model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_node_exists",
            format!("ModelIR already has a node with identity {node_id}"),
        ));
    }
    for node in nodes.iter() {
        let existing = node
            .get("coordinates_m")
            .and_then(Value::as_array)
            .filter(|values| values.len() == 3)
            .ok_or_else(|| snapshot_error("node coordinates_m"))?;
        let duplicates = existing.iter().zip(coordinates_m).all(|(left, right)| {
            finite_number(left, "node coordinate")
                .is_ok_and(|left| normalized_number_bits(left) == normalized_number_bits(right))
        });
        if duplicates {
            return Err(WorkbenchError::new(
                "workbench_model_add_node_coordinate_exists",
                "new node coordinates duplicate an existing node",
            ));
        }
    }
    let node_index = nodes.len();
    nodes.push(json!({
        "id": node_id,
        "index": node_index,
        "coordinates_m": coordinates_m,
        "source_id": null,
        "extensions": {}
    }));
    Ok(node_index)
}

#[allow(clippy::too_many_lines)]
fn remove_orphan_node(
    model: &mut Value,
    node_id: &str,
) -> Result<RemovedOrphanNodeV1, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if nodes.len() <= 2 {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_minimum_topology",
            "orphan-node deletion must retain at least two nodes",
        ));
    }
    let node_index = nodes
        .iter()
        .position(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_delete_orphan_node_missing",
                format!("ModelIR has no node with identity {node_id}"),
            )
        })?;
    if node_index + 1 != nodes.len() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_not_terminal",
            "deleted orphan node must be the last contiguous node row",
        ));
    }
    let node = &nodes[node_index];
    if node.get("index").and_then(Value::as_u64) != u64::try_from(node_index).ok() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_index_mismatch",
            "deleted orphan-node index must match its last contiguous position",
        ));
    }
    if !node.get("source_id").is_some_and(Value::is_null) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_source_owned",
            "orphan-node deletion accepts only a neutral row with null source_id",
        ));
    }
    let extensions = node
        .get("extensions")
        .and_then(Value::as_object)
        .ok_or_else(|| snapshot_error("orphan node extensions"))?;
    if !extensions.is_empty() {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_extensions_unsupported",
            "orphan-node deletion accepts only a row with empty entity extensions",
        ));
    }
    let removed_extensions = Value::Object(extensions.clone());
    let coordinates = node
        .get("coordinates_m")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 3)
        .ok_or_else(|| snapshot_error("orphan node coordinates_m"))?;
    let coordinates_m = [
        finite_number(&coordinates[0], "orphan node coordinate")?,
        finite_number(&coordinates[1], "orphan node coordinate")?,
        finite_number(&coordinates[2], "orphan node coordinate")?,
    ];

    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements.iter().any(|element| {
        element
            .get("node_ids")
            .and_then(Value::as_array)
            .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(node_id)))
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_referenced_by_element",
            format!("node {node_id} is referenced by an element"),
        ));
    }
    let constraints = model
        .get("constraints")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("constraints"))?;
    if constraints
        .iter()
        .any(|constraint| constraint.get("node_id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_referenced_by_constraint",
            format!("node {node_id} is referenced by a constraint"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns.iter().any(|pattern| {
        pattern
            .get("nodal_loads")
            .and_then(Value::as_array)
            .is_some_and(|loads| {
                loads
                    .iter()
                    .any(|load| load.get("node_id").and_then(Value::as_str) == Some(node_id))
            })
    }) {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_referenced_by_load",
            format!("node {node_id} is referenced by a nodal load"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features
        .iter()
        .any(|feature| feature.get("source_entity_id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_unsupported_feature_owned",
            "orphan-node deletion refuses a row referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows
        .iter()
        .any(|row| row.get("model_ir_entity_id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_delete_orphan_node_roundtrip_owned",
            "orphan-node deletion refuses a row with a direct round-trip mapping",
        ));
    }

    model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?
        .pop()
        .ok_or_else(|| snapshot_error("last node"))?;
    Ok(RemovedOrphanNodeV1 {
        node_index,
        coordinates_m,
        extensions: removed_extensions,
    })
}

#[allow(clippy::too_many_arguments)]
fn append_frame3d_member(
    model: &mut Value,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(usize, usize), WorkbenchError> {
    let node_index = validate_frame3d_node_add(model, node_id, coordinates_m, from_node_id)?;
    validate_frame3d_member_properties(model, material_id, section_id)?;
    let element_index = validate_frame3d_element_add(model, element_id)?;
    model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?
        .push(json!({
            "id": node_id,
            "index": node_index,
            "coordinates_m": coordinates_m,
            "source_id": null,
            "extensions": {}
        }));
    model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?
        .push(json!({
            "id": element_id,
            "index": element_index,
            "type": "frame_3d",
            "formulation": "euler_bernoulli_3d",
            "node_ids": [from_node_id, node_id],
            "material_id": material_id,
            "section_id": section_id,
            "local_axis_rotation_rad": 0.0,
            "offsets": {
                "i_global_m": [0.0, 0.0, 0.0],
                "j_global_m": [0.0, 0.0, 0.0]
            },
            "releases": {"i": [], "j": []},
            "source_id": null,
            "extensions": {}
        }));
    Ok((node_index, element_index))
}

#[allow(clippy::too_many_arguments)]
fn append_truss3d_member(
    model: &mut Value,
    node_id: &str,
    coordinates_m: [f64; 3],
    element_id: &str,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
) -> Result<(usize, usize), WorkbenchError> {
    let node_index = validate_truss3d_node_add(model, node_id, coordinates_m, from_node_id)?;
    validate_truss3d_member_properties(model, material_id, section_id)?;
    let element_index = validate_truss3d_element_add(model, element_id)?;
    model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?
        .push(json!({
            "id": node_id,
            "index": node_index,
            "coordinates_m": coordinates_m,
            "source_id": null,
            "extensions": {}
        }));
    model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?
        .push(json!({
            "id": element_id,
            "index": element_index,
            "type": "truss_3d",
            "formulation": "linear_truss_3d",
            "node_ids": [from_node_id, node_id],
            "material_id": material_id,
            "section_id": section_id,
            "offsets": {
                "i_global_m": [0.0, 0.0, 0.0],
                "j_global_m": [0.0, 0.0, 0.0]
            },
            "source_id": null,
            "extensions": {}
        }));
    Ok((node_index, element_index))
}

#[derive(Clone, Copy)]
struct LeafMemberDeleteErrorCodes {
    minimum_topology: &'static str,
    node_missing: &'static str,
    element_missing: &'static str,
    not_terminal: &'static str,
    index_mismatch: &'static str,
    type_unsupported: &'static str,
    source_owned: &'static str,
    endpoint_mismatch: &'static str,
    node_referenced_by_element: &'static str,
    node_referenced_by_constraint: &'static str,
    node_referenced_by_load: &'static str,
    element_referenced_by_stage: &'static str,
    unsupported_feature_owned: &'static str,
    roundtrip_owned: &'static str,
}

const FRAME3D_LEAF_DELETE_ERRORS: LeafMemberDeleteErrorCodes = LeafMemberDeleteErrorCodes {
    minimum_topology: "workbench_model_delete_frame3d_leaf_minimum_topology",
    node_missing: "workbench_model_delete_frame3d_leaf_node_missing",
    element_missing: "workbench_model_delete_frame3d_leaf_element_missing",
    not_terminal: "workbench_model_delete_frame3d_leaf_not_terminal",
    index_mismatch: "workbench_model_delete_frame3d_leaf_index_mismatch",
    type_unsupported: "workbench_model_delete_frame3d_leaf_type_unsupported",
    source_owned: "workbench_model_delete_frame3d_leaf_source_owned",
    endpoint_mismatch: "workbench_model_delete_frame3d_leaf_endpoint_mismatch",
    node_referenced_by_element: "workbench_model_delete_frame3d_leaf_node_referenced_by_element",
    node_referenced_by_constraint:
        "workbench_model_delete_frame3d_leaf_node_referenced_by_constraint",
    node_referenced_by_load: "workbench_model_delete_frame3d_leaf_node_referenced_by_load",
    element_referenced_by_stage: "workbench_model_delete_frame3d_leaf_element_referenced_by_stage",
    unsupported_feature_owned: "workbench_model_delete_frame3d_leaf_unsupported_feature_owned",
    roundtrip_owned: "workbench_model_delete_frame3d_leaf_roundtrip_owned",
};

const TRUSS3D_LEAF_DELETE_ERRORS: LeafMemberDeleteErrorCodes = LeafMemberDeleteErrorCodes {
    minimum_topology: "workbench_model_delete_truss3d_leaf_minimum_topology",
    node_missing: "workbench_model_delete_truss3d_leaf_node_missing",
    element_missing: "workbench_model_delete_truss3d_leaf_element_missing",
    not_terminal: "workbench_model_delete_truss3d_leaf_not_terminal",
    index_mismatch: "workbench_model_delete_truss3d_leaf_index_mismatch",
    type_unsupported: "workbench_model_delete_truss3d_leaf_type_unsupported",
    source_owned: "workbench_model_delete_truss3d_leaf_source_owned",
    endpoint_mismatch: "workbench_model_delete_truss3d_leaf_endpoint_mismatch",
    node_referenced_by_element: "workbench_model_delete_truss3d_leaf_node_referenced_by_element",
    node_referenced_by_constraint:
        "workbench_model_delete_truss3d_leaf_node_referenced_by_constraint",
    node_referenced_by_load: "workbench_model_delete_truss3d_leaf_node_referenced_by_load",
    element_referenced_by_stage: "workbench_model_delete_truss3d_leaf_element_referenced_by_stage",
    unsupported_feature_owned: "workbench_model_delete_truss3d_leaf_unsupported_feature_owned",
    roundtrip_owned: "workbench_model_delete_truss3d_leaf_roundtrip_owned",
};

#[derive(Clone, Debug, PartialEq)]
struct RemovedLeafMemberCoreV1 {
    node_index: usize,
    coordinates_m: [f64; 3],
    element_index: usize,
    node_ids: [String; 2],
    material_id: String,
    section_id: String,
    offsets_global_m: [[f64; 3]; 2],
    element_snapshot: Value,
}

#[allow(clippy::too_many_lines)]
fn remove_leaf_member_core(
    model: &mut Value,
    element_id: &str,
    node_id: &str,
    expected_type: &'static str,
    expected_formulation: &'static str,
    errors: LeafMemberDeleteErrorCodes,
) -> Result<RemovedLeafMemberCoreV1, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if nodes.len() <= 2 || elements.len() <= 1 {
        return Err(WorkbenchError::new(
            errors.minimum_topology,
            "leaf deletion must retain at least two nodes and one element",
        ));
    }
    let node_position = nodes
        .iter()
        .position(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                errors.node_missing,
                format!("ModelIR has no node with identity {node_id}"),
            )
        })?;
    let element_position = elements
        .iter()
        .position(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                errors.element_missing,
                format!("ModelIR has no element with identity {element_id}"),
            )
        })?;
    if node_position + 1 != nodes.len() || element_position + 1 != elements.len() {
        return Err(WorkbenchError::new(
            errors.not_terminal,
            "deleted node and element must be the last contiguous rows in their families",
        ));
    }
    let node = &nodes[node_position];
    let element = &elements[element_position];
    if node.get("index").and_then(Value::as_u64) != u64::try_from(node_position).ok()
        || element.get("index").and_then(Value::as_u64) != u64::try_from(element_position).ok()
    {
        return Err(WorkbenchError::new(
            errors.index_mismatch,
            "deleted node and element indices must match their last contiguous positions",
        ));
    }
    if element.get("type").and_then(Value::as_str) != Some(expected_type)
        || element.get("formulation").and_then(Value::as_str) != Some(expected_formulation)
    {
        return Err(WorkbenchError::new(
            errors.type_unsupported,
            format!("leaf deletion accepts only a {expected_type}/{expected_formulation} element"),
        ));
    }
    if !node.get("source_id").is_some_and(Value::is_null)
        || !element.get("source_id").is_some_and(Value::is_null)
    {
        return Err(WorkbenchError::new(
            errors.source_owned,
            "leaf deletion accepts only neutral node and element rows with null source_id",
        ));
    }
    let element_node_values = element
        .get("node_ids")
        .and_then(Value::as_array)
        .filter(|values| values.len() == 2)
        .ok_or_else(|| snapshot_error("leaf element node_ids"))?;
    let node_ids = [
        element_node_values[0]
            .as_str()
            .ok_or_else(|| snapshot_error("leaf element i-node identity"))?
            .to_owned(),
        element_node_values[1]
            .as_str()
            .ok_or_else(|| snapshot_error("leaf element j-node identity"))?
            .to_owned(),
    ];
    if node_ids.iter().all(|candidate| candidate != node_id) {
        return Err(WorkbenchError::new(
            errors.endpoint_mismatch,
            format!("element {element_id} does not reference deleted node {node_id}"),
        ));
    }
    if elements[..element_position].iter().any(|candidate| {
        candidate
            .get("node_ids")
            .and_then(Value::as_array)
            .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(node_id)))
    }) {
        return Err(WorkbenchError::new(
            errors.node_referenced_by_element,
            format!("node {node_id} is referenced by another element"),
        ));
    }
    let constraints = model
        .get("constraints")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("constraints"))?;
    if constraints
        .iter()
        .any(|constraint| constraint.get("node_id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            errors.node_referenced_by_constraint,
            format!("node {node_id} is referenced by a constraint"),
        ));
    }
    let load_patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("load_patterns"))?;
    if load_patterns.iter().any(|pattern| {
        pattern
            .get("nodal_loads")
            .and_then(Value::as_array)
            .is_some_and(|loads| {
                loads
                    .iter()
                    .any(|load| load.get("node_id").and_then(Value::as_str) == Some(node_id))
            })
    }) {
        return Err(WorkbenchError::new(
            errors.node_referenced_by_load,
            format!("node {node_id} is referenced by a nodal load"),
        ));
    }
    let construction_stages = model
        .get("construction_stages")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("construction_stages"))?;
    if construction_stages.iter().any(|stage| {
        stage
            .get("active_element_ids")
            .and_then(Value::as_array)
            .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(element_id)))
    }) {
        return Err(WorkbenchError::new(
            errors.element_referenced_by_stage,
            format!("element {element_id} is referenced by a construction stage"),
        ));
    }
    let unsupported_features = model
        .get("unsupported_features")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("unsupported_features"))?;
    if unsupported_features.iter().any(|feature| {
        matches!(
            feature.get("source_entity_id").and_then(Value::as_str),
            Some(identity) if identity == element_id || identity == node_id
        )
    }) {
        return Err(WorkbenchError::new(
            errors.unsupported_feature_owned,
            "leaf deletion refuses node or element rows referenced by an unsupported feature",
        ));
    }
    let roundtrip_rows = model
        .get("roundtrip_map")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    if roundtrip_rows.iter().any(|row| {
        matches!(
            row.get("model_ir_entity_id").and_then(Value::as_str),
            Some(identity) if identity == element_id || identity == node_id
        )
    }) {
        return Err(WorkbenchError::new(
            errors.roundtrip_owned,
            "leaf deletion refuses node or element rows with a round-trip mapping",
        ));
    }

    let read_triplet = |value: &Value, field: &'static str| {
        let values = value
            .as_array()
            .filter(|values| values.len() == 3)
            .ok_or_else(|| snapshot_error(field))?;
        Ok::<[f64; 3], WorkbenchError>([
            finite_number(&values[0], field)?,
            finite_number(&values[1], field)?,
            finite_number(&values[2], field)?,
        ])
    };
    let coordinates_m = node
        .get("coordinates_m")
        .ok_or_else(|| snapshot_error("node coordinates_m"))
        .and_then(|value| read_triplet(value, "node coordinates_m"))?;
    let offsets = element
        .get("offsets")
        .and_then(Value::as_object)
        .ok_or_else(|| snapshot_error("leaf element offsets"))?;
    let offsets_global_m = [
        offsets
            .get("i_global_m")
            .ok_or_else(|| snapshot_error("leaf element i offset"))
            .and_then(|value| read_triplet(value, "leaf element i offset"))?,
        offsets
            .get("j_global_m")
            .ok_or_else(|| snapshot_error("leaf element j offset"))
            .and_then(|value| read_triplet(value, "leaf element j offset"))?,
    ];
    let material_id = element
        .get("material_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("leaf element material_id"))?
        .to_owned();
    let section_id = element
        .get("section_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("leaf element section_id"))?
        .to_owned();
    if expected_type == "frame_3d" {
        element
            .get("local_axis_rotation_rad")
            .ok_or_else(|| snapshot_error("frame leaf local_axis_rotation_rad"))
            .and_then(|value| finite_number(value, "frame leaf local_axis_rotation_rad"))?;
        let releases = element
            .get("releases")
            .and_then(Value::as_object)
            .ok_or_else(|| snapshot_error("frame leaf releases"))?;
        if !releases.get("i").is_some_and(Value::is_array)
            || !releases.get("j").is_some_and(Value::is_array)
        {
            return Err(snapshot_error("frame leaf releases"));
        }
    }
    let element_snapshot = element.clone();

    model
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("elements"))?
        .pop()
        .ok_or_else(|| snapshot_error("last element"))?;
    model
        .get_mut("nodes")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("nodes"))?
        .pop()
        .ok_or_else(|| snapshot_error("last node"))?;
    Ok(RemovedLeafMemberCoreV1 {
        node_index: node_position,
        coordinates_m,
        element_index: element_position,
        node_ids,
        material_id,
        section_id,
        offsets_global_m,
        element_snapshot,
    })
}

fn remove_frame3d_leaf_member(
    model: &mut Value,
    element_id: &str,
    node_id: &str,
) -> Result<RemovedFrame3dLeafV1, WorkbenchError> {
    let removed = remove_leaf_member_core(
        model,
        element_id,
        node_id,
        "frame_3d",
        "euler_bernoulli_3d",
        FRAME3D_LEAF_DELETE_ERRORS,
    )?;
    let local_axis_rotation_rad = removed
        .element_snapshot
        .get("local_axis_rotation_rad")
        .ok_or_else(|| snapshot_error("frame leaf local_axis_rotation_rad"))
        .and_then(|value| finite_number(value, "frame leaf local_axis_rotation_rad"))?;
    let releases = removed
        .element_snapshot
        .get("releases")
        .and_then(Value::as_object)
        .filter(|values| {
            values.get("i").is_some_and(Value::is_array)
                && values.get("j").is_some_and(Value::is_array)
        })
        .map(|_| removed.element_snapshot["releases"].clone())
        .ok_or_else(|| snapshot_error("frame leaf releases"))?;
    Ok(RemovedFrame3dLeafV1 {
        node_index: removed.node_index,
        coordinates_m: removed.coordinates_m,
        element_index: removed.element_index,
        node_ids: removed.node_ids,
        material_id: removed.material_id,
        section_id: removed.section_id,
        local_axis_rotation_rad,
        offsets_global_m: removed.offsets_global_m,
        releases,
    })
}

fn remove_truss3d_leaf_member(
    model: &mut Value,
    element_id: &str,
    node_id: &str,
) -> Result<RemovedTruss3dLeafV1, WorkbenchError> {
    let removed = remove_leaf_member_core(
        model,
        element_id,
        node_id,
        "truss_3d",
        "linear_truss_3d",
        TRUSS3D_LEAF_DELETE_ERRORS,
    )?;
    Ok(RemovedTruss3dLeafV1 {
        node_index: removed.node_index,
        coordinates_m: removed.coordinates_m,
        element_index: removed.element_index,
        node_ids: removed.node_ids,
        material_id: removed.material_id,
        section_id: removed.section_id,
        offsets_global_m: removed.offsets_global_m,
    })
}

fn validate_truss3d_node_add(
    model: &Value,
    node_id: &str,
    coordinates_m: [f64; 3],
    from_node_id: &str,
) -> Result<usize, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_node_exists",
            format!("ModelIR already has a node with identity {node_id}"),
        ));
    }
    if !nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(from_node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_from_node_missing",
            format!("ModelIR has no existing endpoint node with identity {from_node_id}"),
        ));
    }
    for node in nodes {
        let existing = node
            .get("coordinates_m")
            .and_then(Value::as_array)
            .filter(|values| values.len() == 3)
            .ok_or_else(|| snapshot_error("node coordinates_m"))?;
        let duplicates = existing.iter().zip(coordinates_m).all(|(left, right)| {
            finite_number(left, "node coordinate")
                .is_ok_and(|left| normalized_number_bits(left) == normalized_number_bits(right))
        });
        if duplicates {
            return Err(WorkbenchError::new(
                "workbench_model_add_truss3d_member_coordinate_exists",
                "new truss-member node coordinates duplicate an existing node",
            ));
        }
    }
    Ok(nodes.len())
}

fn validate_truss3d_member_properties(
    model: &Value,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    let material = materials
        .iter()
        .find(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_add_truss3d_member_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic")
        || material
            .get("parameter_set_version")
            .and_then(Value::as_str)
            != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_material_unsupported",
            "new linear truss member requires an existing v1 linear_elastic_isotropic material",
        ));
    }

    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_add_truss3d_member_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("truss_3d")
        || section.get("parameter_set_version").and_then(Value::as_str) != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_section_unsupported",
            "new linear truss member requires an existing v1 truss_3d section",
        ));
    }
    Ok(())
}

fn validate_truss3d_element_add(model: &Value, element_id: &str) -> Result<usize, WorkbenchError> {
    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements
        .iter()
        .any(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_truss3d_member_element_exists",
            format!("ModelIR already has an element with identity {element_id}"),
        ));
    }
    Ok(elements.len())
}

fn validate_frame3d_node_add(
    model: &Value,
    node_id: &str,
    coordinates_m: [f64; 3],
    from_node_id: &str,
) -> Result<usize, WorkbenchError> {
    let nodes = model
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("nodes"))?;
    if nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_node_exists",
            format!("ModelIR already has a node with identity {node_id}"),
        ));
    }
    if !nodes
        .iter()
        .any(|node| node.get("id").and_then(Value::as_str) == Some(from_node_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_from_node_missing",
            format!("ModelIR has no existing endpoint node with identity {from_node_id}"),
        ));
    }
    for node in nodes {
        let existing = node
            .get("coordinates_m")
            .and_then(Value::as_array)
            .filter(|values| values.len() == 3)
            .ok_or_else(|| snapshot_error("node coordinates_m"))?;
        let duplicates = existing.iter().zip(coordinates_m).all(|(left, right)| {
            finite_number(left, "node coordinate")
                .is_ok_and(|left| normalized_number_bits(left) == normalized_number_bits(right))
        });
        if duplicates {
            return Err(WorkbenchError::new(
                "workbench_model_add_frame3d_member_coordinate_exists",
                "new frame-member node coordinates duplicate an existing node",
            ));
        }
    }
    Ok(nodes.len())
}

fn validate_frame3d_member_properties(
    model: &Value,
    material_id: &str,
    section_id: &str,
) -> Result<(), WorkbenchError> {
    let materials = model
        .get("materials")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("materials"))?;
    let material = materials
        .iter()
        .find(|material| material.get("id").and_then(Value::as_str) == Some(material_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_add_frame3d_member_material_missing",
                format!("ModelIR has no material with identity {material_id}"),
            )
        })?;
    if material.get("law_id").and_then(Value::as_str) != Some("linear_elastic_isotropic")
        || material
            .get("parameter_set_version")
            .and_then(Value::as_str)
            != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_material_unsupported",
            "new linear frame member requires an existing v1 linear_elastic_isotropic material",
        ));
    }

    let sections = model
        .get("sections")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("sections"))?;
    let section = sections
        .iter()
        .find(|section| section.get("id").and_then(Value::as_str) == Some(section_id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_add_frame3d_member_section_missing",
                format!("ModelIR has no section with identity {section_id}"),
            )
        })?;
    if section.get("family_id").and_then(Value::as_str) != Some("frame_3d")
        || section.get("parameter_set_version").and_then(Value::as_str) != Some("1")
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_section_unsupported",
            "new linear frame member requires an existing v1 frame_3d section",
        ));
    }
    Ok(())
}

fn validate_frame3d_element_add(model: &Value, element_id: &str) -> Result<usize, WorkbenchError> {
    let elements = model
        .get("elements")
        .and_then(Value::as_array)
        .ok_or_else(|| snapshot_error("elements"))?;
    if elements
        .iter()
        .any(|element| element.get("id").and_then(Value::as_str) == Some(element_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_add_frame3d_member_element_exists",
            format!("ModelIR already has an element with identity {element_id}"),
        ));
    }
    Ok(elements.len())
}

#[allow(clippy::too_many_arguments)]
fn bind_edit_provenance(
    model: &mut Value,
    node_id: &str,
    previous_coordinates_m: [f64; 3],
    edited_coordinates_m: [f64; 3],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let model_id = model
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("model_id"))?
        .to_owned();
    let object = model
        .as_object_mut()
        .ok_or_else(|| snapshot_error("root object"))?;
    let upstream_provenance = object
        .get("provenance")
        .cloned()
        .ok_or_else(|| snapshot_error("provenance"))?;
    object.insert(
        "provenance".to_owned(),
        json!({
            "source_format": "neutral_json",
            "source_ref": format!("modelir-edit:{model_id}"),
            "source_sha256": source_content_hash,
            "normalizer_id": "structural-native-model-editor",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad"
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0
            },
            "extensions": {
                UPSTREAM_PROVENANCE_KEY: upstream_provenance
            }
        }),
    );
    let extensions = object
        .get_mut("extensions")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("root extensions"))?;
    extensions.insert(
        NODE_EDIT_EXTENSION_KEY.to_owned(),
        json!({
            "operation": "node_coordinates",
            "node_id": node_id,
            "previous_coordinates_m": previous_coordinates_m,
            "edited_coordinates_m": edited_coordinates_m,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": NODE_CLAIM_BOUNDARY
        }),
    );
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn bind_nodal_load_edit_provenance(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
    previous_components_si: [f64; 6],
    edited_components_si: [f64; 6],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let model_id = model
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("model_id"))?
        .to_owned();
    let object = model
        .as_object_mut()
        .ok_or_else(|| snapshot_error("root object"))?;
    let upstream_provenance = object
        .get("provenance")
        .cloned()
        .ok_or_else(|| snapshot_error("provenance"))?;
    object.insert(
        "provenance".to_owned(),
        json!({
            "source_format": "neutral_json",
            "source_ref": format!("modelir-edit:{model_id}"),
            "source_sha256": source_content_hash,
            "normalizer_id": "structural-native-model-editor",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad"
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0
            },
            "extensions": {
                UPSTREAM_PROVENANCE_KEY: upstream_provenance
            }
        }),
    );
    let extensions = object
        .get_mut("extensions")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("root extensions"))?;
    extensions.insert(
        NODAL_LOAD_EDIT_EXTENSION_KEY.to_owned(),
        json!({
            "operation": "nodal_load_components",
            "load_pattern_id": load_pattern_id,
            "nodal_load_id": nodal_load_id,
            "previous_components_si": components_object(previous_components_si),
            "edited_components_si": components_object(edited_components_si),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": NODAL_LOAD_CLAIM_BOUNDARY
        }),
    );
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn bind_nodal_load_add_provenance(
    model: &mut Value,
    load_pattern_id: &str,
    load_pattern_index: usize,
    nodal_load_id: &str,
    nodal_load_index: usize,
    node_id: &str,
    components_si: [f64; 6],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NODAL_LOAD_ADD_EXTENSION_KEY,
        json!({
            "operation": "nodal_load_add",
            "load_pattern_id": load_pattern_id,
            "load_pattern_index": load_pattern_index,
            "analysis_type": "linear_static",
            "nodal_load_id": nodal_load_id,
            "nodal_load_index": nodal_load_index,
            "node_id": node_id,
            "components_si": components_object(components_si),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": NODAL_LOAD_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_nodal_load_delete_provenance(
    model: &mut Value,
    load_pattern_id: &str,
    nodal_load_id: &str,
    removed: &RemovedNodalLoadV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NODAL_LOAD_DELETE_EXTENSION_KEY,
        json!({
            "operation": "nodal_load_delete",
            "load_pattern_id": load_pattern_id,
            "load_pattern_index": removed.load_pattern_index,
            "analysis_type": "linear_static",
            "removed_nodal_load_id": nodal_load_id,
            "removed_nodal_load_index": removed.nodal_load_index,
            "removed_node_id": removed.node_id,
            "removed_components_si": removed.components_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": NODAL_LOAD_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_fixed_constraint_add_provenance(
    model: &mut Value,
    constraint_id: &str,
    constraint_index: usize,
    node_id: &str,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FIXED_CONSTRAINT_ADD_EXTENSION_KEY,
        json!({
            "operation": "fixed_constraint_add",
            "constraint_id": constraint_id,
            "constraint_index": constraint_index,
            "constraint_type": "fixed_dofs",
            "node_id": node_id,
            "dofs": DOF_KEYS,
            "prescribed_values_si": fixed_constraint_values_object(),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FIXED_CONSTRAINT_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_fixed_constraint_delete_provenance(
    model: &mut Value,
    constraint_id: &str,
    removed: &RemovedFixedConstraintV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FIXED_CONSTRAINT_DELETE_EXTENSION_KEY,
        json!({
            "operation": "fixed_constraint_delete",
            "removed_constraint_id": constraint_id,
            "removed_constraint_index": removed.constraint_index,
            "removed_constraint_type": "fixed_dofs",
            "removed_node_id": removed.node_id,
            "removed_dofs": removed.dofs,
            "removed_prescribed_values_si": removed.prescribed_values_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FIXED_CONSTRAINT_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_linear_load_pattern_add_provenance(
    model: &mut Value,
    load_pattern_id: &str,
    load_pattern_index: usize,
    nodal_load_id: &str,
    node_id: &str,
    components_si: [f64; 6],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        LINEAR_LOAD_PATTERN_ADD_EXTENSION_KEY,
        json!({
            "operation": "linear_load_pattern_add",
            "load_pattern_id": load_pattern_id,
            "load_pattern_index": load_pattern_index,
            "analysis_type": "linear_static",
            "self_weight": [0, 0, 0],
            "nodal_load_id": nodal_load_id,
            "nodal_load_index": 0,
            "node_id": node_id,
            "components_si": components_object(components_si),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": LINEAR_LOAD_PATTERN_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_linear_load_combination_add_provenance(
    model: &mut Value,
    load_combination_id: &str,
    load_combination_index: usize,
    terms: &[LinearLoadCombinationTermV1],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let (extension_key, operation, claim_boundary) = if terms.len() == 2 {
        (
            LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY,
            "linear_load_combination_add",
            LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY,
        )
    } else {
        (
            DIRECT_LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY,
            "direct_linear_load_combination_add",
            DIRECT_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY,
        )
    };
    let mut provenance = json!({
        "operation": operation,
        "load_combination_id": load_combination_id,
        "load_combination_index": load_combination_index,
        "combination_type": "linear",
        "terms": linear_load_combination_terms_value(terms),
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "claim_boundary": claim_boundary
    });
    if terms.len() != 2 {
        provenance["authoring_profile"] = json!("unique_direct_linear_static_patterns_2_to_64");
        provenance["term_count"] = json!(terms.len());
    }
    bind_parameter_edit_provenance(model, extension_key, provenance, source_content_hash)
}

#[allow(clippy::too_many_arguments)]
fn bind_direct_linear_load_combination_factor_edit_provenance(
    model: &mut Value,
    load_combination_id: &str,
    load_pattern_id: &str,
    factor_edit: &DirectLinearLoadCombinationFactorEditV1,
    edited_factor: f64,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_EXTENSION_KEY,
        json!({
            "operation": "direct_linear_load_combination_factor_edit",
            "editing_profile": "unique_direct_linear_static_patterns_2_to_64",
            "load_combination_id": load_combination_id,
            "load_combination_index": factor_edit.load_combination_index,
            "combination_type": "linear",
            "load_pattern_id": load_pattern_id,
            "term_index": factor_edit.term_index,
            "term_count": factor_edit.edited_terms.as_array().map_or(0, Vec::len),
            "previous_factor": factor_edit.previous_factor,
            "edited_factor": edited_factor,
            "edited_terms": factor_edit.edited_terms,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_direct_linear_load_combination_reference_edit_provenance(
    model: &mut Value,
    load_combination_id: &str,
    load_pattern_id: &str,
    replacement_load_pattern_id: &str,
    reference_edit: &DirectLinearLoadCombinationReferenceEditV1,
    source_hashes: SourceModelHashesV1<'_>,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_EXTENSION_KEY,
        json!({
            "operation": "direct_linear_load_combination_reference_edit",
            "editing_profile": "unique_direct_linear_static_patterns_2_to_64",
            "load_combination_id": load_combination_id,
            "load_combination_index": reference_edit.load_combination_index,
            "combination_type": "linear",
            "load_pattern_id": load_pattern_id,
            "replacement_load_pattern_id": replacement_load_pattern_id,
            "term_index": reference_edit.term_index,
            "term_count": reference_edit.edited_terms.as_array().map_or(0, Vec::len),
            "preserved_factor": reference_edit.preserved_factor,
            "source_terms": reference_edit.source_terms.clone(),
            "edited_terms": reference_edit.edited_terms.clone(),
            "source_content_hash": source_hashes.content,
            "source_semantic_hash": source_hashes.semantic,
            "source_provenance_hash": source_hashes.provenance,
            "claim_boundary": DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY
        }),
        source_hashes.content,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_nested_linear_load_combination_factor_edit_provenance(
    model: &mut Value,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    factor_edit: &NestedLinearLoadCombinationFactorEditV1,
    edited_factor: f64,
    source_hashes: SourceModelHashesV1<'_>,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_EXTENSION_KEY,
        json!({
            "operation": "nested_linear_load_combination_factor_edit",
            "editing_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
            "load_combination_id": load_combination_id,
            "load_combination_index": factor_edit.load_combination_index,
            "combination_type": "linear",
            "reference_kind": reference_kind.as_str(),
            "reference_id": reference_id,
            "term_index": factor_edit.term_index,
            "term_count": factor_edit.edited_expansion.root_terms.as_array().map_or(0, Vec::len),
            "previous_factor": factor_edit.previous_factor,
            "edited_factor": edited_factor,
            "source_terms": factor_edit.source_expansion.root_terms.clone(),
            "edited_terms": factor_edit.edited_expansion.root_terms.clone(),
            "source_combination_depth": factor_edit.source_expansion.max_depth,
            "source_expanded_term_count": factor_edit.source_expansion.expanded_term_count,
            "source_expanded_pattern_count": factor_edit
                .source_expansion
                .expanded_pattern_terms
                .as_array()
                .map_or(0, Vec::len),
            "source_expanded_pattern_terms": factor_edit
                .source_expansion
                .expanded_pattern_terms
                .clone(),
            "edited_combination_depth": factor_edit.edited_expansion.max_depth,
            "edited_expanded_term_count": factor_edit.edited_expansion.expanded_term_count,
            "edited_expanded_pattern_count": factor_edit
                .edited_expansion
                .expanded_pattern_terms
                .as_array()
                .map_or(0, Vec::len),
            "edited_expanded_pattern_terms": factor_edit
                .edited_expansion
                .expanded_pattern_terms
                .clone(),
            "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
            "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
            "source_content_hash": source_hashes.content,
            "source_semantic_hash": source_hashes.semantic,
            "source_provenance_hash": source_hashes.provenance,
            "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_CLAIM_BOUNDARY
        }),
        source_hashes.content,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_nested_linear_load_combination_reference_edit_provenance(
    model: &mut Value,
    load_combination_id: &str,
    reference_kind: LinearLoadCombinationReferenceKindV1,
    reference_id: &str,
    replacement_reference_kind: LinearLoadCombinationReferenceKindV1,
    replacement_reference_id: &str,
    reference_edit: &NestedLinearLoadCombinationReferenceEditV1,
    source_hashes: SourceModelHashesV1<'_>,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_EXTENSION_KEY,
        json!({
            "operation": "nested_linear_load_combination_reference_edit",
            "editing_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
            "load_combination_id": load_combination_id,
            "load_combination_index": reference_edit.load_combination_index,
            "combination_type": "linear",
            "reference_kind": reference_kind.as_str(),
            "reference_id": reference_id,
            "replacement_reference_kind": replacement_reference_kind.as_str(),
            "replacement_reference_id": replacement_reference_id,
            "term_index": reference_edit.term_index,
            "term_count": reference_edit.edited_expansion.root_terms.as_array().map_or(0, Vec::len),
            "preserved_factor": reference_edit.preserved_factor,
            "source_terms": reference_edit.source_expansion.root_terms.clone(),
            "edited_terms": reference_edit.edited_expansion.root_terms.clone(),
            "source_combination_depth": reference_edit.source_expansion.max_depth,
            "source_expanded_term_count": reference_edit.source_expansion.expanded_term_count,
            "source_expanded_pattern_count": reference_edit
                .source_expansion
                .expanded_pattern_terms
                .as_array()
                .map_or(0, Vec::len),
            "source_expanded_pattern_terms": reference_edit
                .source_expansion
                .expanded_pattern_terms
                .clone(),
            "edited_combination_depth": reference_edit.edited_expansion.max_depth,
            "edited_expanded_term_count": reference_edit.edited_expansion.expanded_term_count,
            "edited_expanded_pattern_count": reference_edit
                .edited_expansion
                .expanded_pattern_terms
                .as_array()
                .map_or(0, Vec::len),
            "edited_expanded_pattern_terms": reference_edit
                .edited_expansion
                .expanded_pattern_terms
                .clone(),
            "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
            "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
            "source_content_hash": source_hashes.content,
            "source_semantic_hash": source_hashes.semantic,
            "source_provenance_hash": source_hashes.provenance,
            "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_CLAIM_BOUNDARY
        }),
        source_hashes.content,
    )
}

fn bind_nested_linear_load_combination_add_provenance(
    model: &mut Value,
    load_combination_id: &str,
    load_combination_index: usize,
    terms: &[NestedLinearLoadCombinationTermV1],
    expansion: &ExpandedLinearLoadCombinationV1,
    source_hashes: SourceModelHashesV1<'_>,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NESTED_LINEAR_LOAD_COMBINATION_ADD_EXTENSION_KEY,
        json!({
            "operation": "nested_linear_load_combination_add",
            "authoring_profile": "acyclic_nested_linear_static_depth_8_expanded_terms_64",
            "load_combination_id": load_combination_id,
            "load_combination_index": load_combination_index,
            "combination_type": "linear",
            "term_count": terms.len(),
            "terms": nested_linear_load_combination_terms_value(terms),
            "combination_depth": expansion.max_depth,
            "expanded_term_count": expansion.expanded_term_count,
            "expanded_pattern_count": expansion
                .expanded_pattern_terms
                .as_array()
                .map_or(0, Vec::len),
            "expanded_pattern_terms": expansion.expanded_pattern_terms.clone(),
            "maximum_combination_depth": MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1,
            "maximum_expanded_terms": MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1,
            "source_content_hash": source_hashes.content,
            "source_semantic_hash": source_hashes.semantic,
            "source_provenance_hash": source_hashes.provenance,
            "claim_boundary": NESTED_LINEAR_LOAD_COMBINATION_ADD_CLAIM_BOUNDARY
        }),
        source_hashes.content,
    )
}

fn bind_linear_load_combination_delete_provenance(
    model: &mut Value,
    load_combination_id: &str,
    removed: &RemovedLinearLoadCombinationV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let (extension_key, operation, claim_boundary) = match removed.profile {
        LinearLoadCombinationDeletionProfileV1::ExactTwoV1 => (
            LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY,
            "linear_load_combination_delete",
            LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY,
        ),
        LinearLoadCombinationDeletionProfileV1::DirectV2 => (
            DIRECT_LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY,
            "direct_linear_load_combination_delete",
            DIRECT_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY,
        ),
        LinearLoadCombinationDeletionProfileV1::NestedV3 => (
            NESTED_LINEAR_LOAD_COMBINATION_DELETE_EXTENSION_KEY,
            "nested_linear_load_combination_delete",
            NESTED_LINEAR_LOAD_COMBINATION_DELETE_CLAIM_BOUNDARY,
        ),
    };
    let mut provenance = json!({
        "operation": operation,
        "removed_load_combination_id": load_combination_id,
        "removed_load_combination_index": removed.load_combination_index,
        "removed_combination_type": "linear",
        "removed_terms": removed.terms,
        "removed_source_id": null,
        "removed_extensions": {},
        "source_content_hash": source_content_hash,
        "source_semantic_hash": source_semantic_hash,
        "source_provenance_hash": source_provenance_hash,
        "claim_boundary": claim_boundary
    });
    if removed.profile == LinearLoadCombinationDeletionProfileV1::DirectV2 {
        provenance["deletion_profile"] = json!("unique_direct_linear_static_patterns_2_to_64");
        provenance["term_count"] = json!(removed.terms.as_array().map_or(0, Vec::len));
    } else if removed.profile == LinearLoadCombinationDeletionProfileV1::NestedV3 {
        bind_nested_linear_load_combination_delete_fields(&mut provenance, removed)?;
    }
    bind_parameter_edit_provenance(model, extension_key, provenance, source_content_hash)
}

fn bind_nested_linear_load_combination_delete_fields(
    document: &mut Value,
    removed: &RemovedLinearLoadCombinationV1,
) -> Result<(), WorkbenchError> {
    let expansion = removed
        .expansion
        .as_ref()
        .ok_or_else(|| snapshot_error("nested load-combination deletion expansion"))?;
    document["deletion_profile"] = json!("acyclic_nested_linear_static_depth_8_expanded_terms_64");
    document["term_count"] = json!(removed.terms.as_array().map_or(0, Vec::len));
    document["combination_depth"] = json!(expansion.max_depth);
    document["expanded_term_count"] = json!(expansion.expanded_term_count);
    document["expanded_pattern_count"] = json!(expansion
        .expanded_pattern_terms
        .as_array()
        .map_or(0, Vec::len));
    document["expanded_pattern_terms"] = expansion.expanded_pattern_terms.clone();
    document["maximum_combination_depth"] =
        json!(MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1);
    document["maximum_expanded_terms"] = json!(MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1);
    Ok(())
}

fn bind_linear_load_pattern_delete_provenance(
    model: &mut Value,
    load_pattern_id: &str,
    removed: &RemovedLinearLoadPatternV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        LINEAR_LOAD_PATTERN_DELETE_EXTENSION_KEY,
        json!({
            "operation": "linear_load_pattern_delete",
            "removed_load_pattern_id": load_pattern_id,
            "removed_load_pattern_index": removed.load_pattern_index,
            "removed_analysis_type": "linear_static",
            "removed_self_weight": [0, 0, 0],
            "removed_nodal_load_id": removed.nodal_load_id,
            "removed_nodal_load_index": 0,
            "removed_node_id": removed.node_id,
            "removed_components_si": removed.components_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": LINEAR_LOAD_PATTERN_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_linear_material_add_provenance(
    model: &mut Value,
    material_id: &str,
    material_index: usize,
    parameters: LinearElasticMaterialParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        LINEAR_MATERIAL_ADD_EXTENSION_KEY,
        json!({
            "operation": "linear_material_add",
            "material_id": material_id,
            "material_index": material_index,
            "law_id": "linear_elastic_isotropic",
            "parameter_set_version": "1",
            "parameters_si": linear_material_parameters_object(parameters),
            "state_schema": linear_material_state_schema_object(),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": LINEAR_MATERIAL_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_linear_material_delete_provenance(
    model: &mut Value,
    material_id: &str,
    removed: &RemovedLinearMaterialV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        LINEAR_MATERIAL_DELETE_EXTENSION_KEY,
        json!({
            "operation": "linear_material_delete",
            "removed_material_id": material_id,
            "removed_material_index": removed.material_index,
            "removed_law_id": "linear_elastic_isotropic",
            "removed_parameter_set_version": "1",
            "removed_parameters_si": removed.parameters_si,
            "removed_state_schema": removed.state_schema,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": LINEAR_MATERIAL_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame_section_add_provenance(
    model: &mut Value,
    section_id: &str,
    section_index: usize,
    parameters: FrameSectionParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME_SECTION_ADD_EXTENSION_KEY,
        json!({
            "operation": "frame_section_add",
            "section_id": section_id,
            "section_index": section_index,
            "family_id": "frame_3d",
            "parameter_set_version": "1",
            "parameters_si": frame_section_parameters_object(parameters),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME_SECTION_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_frame_section_delete_provenance(
    model: &mut Value,
    section_id: &str,
    removed: &RemovedFrameSectionV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME_SECTION_DELETE_EXTENSION_KEY,
        json!({
            "operation": "frame_section_delete",
            "removed_section_id": section_id,
            "removed_section_index": removed.section_index,
            "removed_family_id": "frame_3d",
            "removed_parameter_set_version": "1",
            "removed_parameters_si": removed.parameters_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME_SECTION_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_truss_section_add_provenance(
    model: &mut Value,
    section_id: &str,
    section_index: usize,
    parameters: TrussSectionParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS_SECTION_ADD_EXTENSION_KEY,
        json!({
            "operation": "truss_section_add",
            "section_id": section_id,
            "section_index": section_index,
            "family_id": "truss_3d",
            "parameter_set_version": "1",
            "parameters_si": truss_section_parameters_object(parameters),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS_SECTION_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_truss_section_delete_provenance(
    model: &mut Value,
    section_id: &str,
    removed: &RemovedTrussSectionV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS_SECTION_DELETE_EXTENSION_KEY,
        json!({
            "operation": "truss_section_delete",
            "removed_section_id": section_id,
            "removed_section_index": removed.section_index,
            "removed_family_id": "truss_3d",
            "removed_parameter_set_version": "1",
            "removed_parameters_si": removed.parameters_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS_SECTION_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_constraint_value_edit_provenance(
    model: &mut Value,
    constraint_id: &str,
    dof: &str,
    previous_value_si: f64,
    edited_value_si: f64,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    let model_id = model
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("model_id"))?
        .to_owned();
    let object = model
        .as_object_mut()
        .ok_or_else(|| snapshot_error("root object"))?;
    let upstream_provenance = object
        .get("provenance")
        .cloned()
        .ok_or_else(|| snapshot_error("provenance"))?;
    object.insert(
        "provenance".to_owned(),
        json!({
            "source_format": "neutral_json",
            "source_ref": format!("modelir-edit:{model_id}"),
            "source_sha256": source_content_hash,
            "normalizer_id": "structural-native-model-editor",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad"
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0
            },
            "extensions": {
                UPSTREAM_PROVENANCE_KEY: upstream_provenance
            }
        }),
    );
    let extensions = object
        .get_mut("extensions")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("root extensions"))?;
    extensions.insert(
        CONSTRAINT_VALUE_EDIT_EXTENSION_KEY.to_owned(),
        json!({
            "operation": "constraint_prescribed_value",
            "constraint_id": constraint_id,
            "dof": dof,
            "unit": constraint_value_unit(dof),
            "previous_value_si": previous_value_si,
            "edited_value_si": edited_value_si,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": CONSTRAINT_VALUE_CLAIM_BOUNDARY
        }),
    );
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn bind_linear_material_edit_provenance(
    model: &mut Value,
    material_id: &str,
    previous_parameters: LinearElasticMaterialParametersV1,
    edited_parameters: LinearElasticMaterialParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        LINEAR_MATERIAL_EDIT_EXTENSION_KEY,
        json!({
            "operation": "linear_elastic_material_parameters",
            "material_id": material_id,
            "law_id": "linear_elastic_isotropic",
            "parameter_set_version": "1",
            "previous_parameters_si": linear_material_parameters_object(previous_parameters),
            "edited_parameters_si": linear_material_parameters_object(edited_parameters),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": LINEAR_MATERIAL_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame_section_edit_provenance(
    model: &mut Value,
    section_id: &str,
    previous_parameters: FrameSectionParametersV1,
    edited_parameters: FrameSectionParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME_SECTION_EDIT_EXTENSION_KEY,
        json!({
            "operation": "frame_section_parameters",
            "section_id": section_id,
            "family_id": "frame_3d",
            "parameter_set_version": "1",
            "previous_parameters_si": frame_section_parameters_object(previous_parameters),
            "edited_parameters_si": frame_section_parameters_object(edited_parameters),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME_SECTION_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_truss_section_edit_provenance(
    model: &mut Value,
    section_id: &str,
    previous_parameters: TrussSectionParametersV1,
    edited_parameters: TrussSectionParametersV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS_SECTION_EDIT_EXTENSION_KEY,
        json!({
            "operation": "truss_section_parameters",
            "section_id": section_id,
            "family_id": "truss_3d",
            "parameter_set_version": "1",
            "previous_parameters_si": truss_section_parameters_object(previous_parameters),
            "edited_parameters_si": truss_section_parameters_object(edited_parameters),
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS_SECTION_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame_element_orientation_edit_provenance(
    model: &mut Value,
    element_id: &str,
    formulation: &str,
    previous_local_axis_rotation_rad: f64,
    edited_local_axis_rotation_rad: f64,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME_ELEMENT_ORIENTATION_EDIT_EXTENSION_KEY,
        json!({
            "operation": "frame_element_local_axis_rotation",
            "element_id": element_id,
            "element_type": "frame_3d",
            "formulation": formulation,
            "previous_local_axis_rotation_rad": previous_local_axis_rotation_rad,
            "edited_local_axis_rotation_rad": edited_local_axis_rotation_rad,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME_ELEMENT_ORIENTATION_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame_element_properties_edit_provenance(
    model: &mut Value,
    element_id: &str,
    formulation: &str,
    previous_material_id: &str,
    edited_material_id: &str,
    previous_section_id: &str,
    edited_section_id: &str,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME_ELEMENT_PROPERTIES_EDIT_EXTENSION_KEY,
        json!({
            "operation": "frame_element_properties",
            "element_id": element_id,
            "element_type": "frame_3d",
            "formulation": formulation,
            "previous_material_id": previous_material_id,
            "edited_material_id": edited_material_id,
            "previous_section_id": previous_section_id,
            "edited_section_id": edited_section_id,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME_ELEMENT_PROPERTIES_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_truss_element_properties_edit_provenance(
    model: &mut Value,
    element_id: &str,
    formulation: &str,
    previous_material_id: &str,
    edited_material_id: &str,
    previous_section_id: &str,
    edited_section_id: &str,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS_ELEMENT_PROPERTIES_EDIT_EXTENSION_KEY,
        json!({
            "operation": "truss_element_properties",
            "element_id": element_id,
            "element_type": "truss_3d",
            "formulation": formulation,
            "previous_material_id": previous_material_id,
            "edited_material_id": edited_material_id,
            "previous_section_id": previous_section_id,
            "edited_section_id": edited_section_id,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS_ELEMENT_PROPERTIES_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_element_connectivity_edit_provenance(
    model: &mut Value,
    element_id: &str,
    element_type: &str,
    formulation: &str,
    previous_node_ids: &[String; 2],
    edited_node_ids: &[String; 2],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        ELEMENT_CONNECTIVITY_EDIT_EXTENSION_KEY,
        json!({
            "operation": "element_connectivity",
            "element_id": element_id,
            "element_type": element_type,
            "formulation": formulation,
            "previous_node_ids": previous_node_ids,
            "edited_node_ids": edited_node_ids,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": ELEMENT_CONNECTIVITY_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_node_add_provenance(
    model: &mut Value,
    node_id: &str,
    node_index: usize,
    coordinates_m: [f64; 3],
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        NODE_ADD_EXTENSION_KEY,
        json!({
            "operation": "node_add",
            "node_id": node_id,
            "node_index": node_index,
            "coordinates_m": coordinates_m,
            "source_id": null,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": NODE_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_orphan_node_delete_provenance(
    model: &mut Value,
    node_id: &str,
    removed: &RemovedOrphanNodeV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        ORPHAN_NODE_DELETE_EXTENSION_KEY,
        json!({
            "operation": "orphan_node_delete",
            "removed_node_id": node_id,
            "removed_node_index": removed.node_index,
            "removed_coordinates_m": removed.coordinates_m,
            "removed_source_id": null,
            "removed_extensions": removed.extensions,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": ORPHAN_NODE_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame3d_member_add_provenance(
    model: &mut Value,
    node_id: &str,
    node_index: usize,
    coordinates_m: [f64; 3],
    element_id: &str,
    element_index: usize,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME3D_MEMBER_ADD_EXTENSION_KEY,
        json!({
            "operation": "frame3d_member_add",
            "node_id": node_id,
            "node_index": node_index,
            "coordinates_m": coordinates_m,
            "element_id": element_id,
            "element_index": element_index,
            "element_type": "frame_3d",
            "formulation": "euler_bernoulli_3d",
            "node_ids": [from_node_id, node_id],
            "material_id": material_id,
            "section_id": section_id,
            "local_axis_rotation_rad": 0.0,
            "offsets_m": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
            "releases": {"i": [], "j": []},
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME3D_MEMBER_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_truss3d_member_add_provenance(
    model: &mut Value,
    node_id: &str,
    node_index: usize,
    coordinates_m: [f64; 3],
    element_id: &str,
    element_index: usize,
    from_node_id: &str,
    material_id: &str,
    section_id: &str,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS3D_MEMBER_ADD_EXTENSION_KEY,
        json!({
            "operation": "truss3d_member_add",
            "node_id": node_id,
            "node_index": node_index,
            "coordinates_m": coordinates_m,
            "element_id": element_id,
            "element_index": element_index,
            "element_type": "truss_3d",
            "formulation": "linear_truss_3d",
            "node_ids": [from_node_id, node_id],
            "material_id": material_id,
            "section_id": section_id,
            "offsets_m": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS3D_MEMBER_ADD_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_frame3d_leaf_member_delete_provenance(
    model: &mut Value,
    element_id: &str,
    node_id: &str,
    removed: &RemovedFrame3dLeafV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        FRAME3D_LEAF_MEMBER_DELETE_EXTENSION_KEY,
        json!({
            "operation": "frame3d_leaf_member_delete",
            "removed_node_id": node_id,
            "removed_node_index": removed.node_index,
            "removed_coordinates_m": removed.coordinates_m,
            "removed_element_id": element_id,
            "removed_element_index": removed.element_index,
            "removed_element_type": "frame_3d",
            "removed_formulation": "euler_bernoulli_3d",
            "removed_node_ids": removed.node_ids,
            "removed_material_id": removed.material_id,
            "removed_section_id": removed.section_id,
            "removed_local_axis_rotation_rad": removed.local_axis_rotation_rad,
            "removed_offsets_m": {
                "i_global_m": removed.offsets_global_m[0],
                "j_global_m": removed.offsets_global_m[1]
            },
            "removed_releases": removed.releases,
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": FRAME3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

#[allow(clippy::too_many_arguments)]
fn bind_truss3d_leaf_member_delete_provenance(
    model: &mut Value,
    element_id: &str,
    node_id: &str,
    removed: &RemovedTruss3dLeafV1,
    source_content_hash: &str,
    source_semantic_hash: &str,
    source_provenance_hash: &str,
) -> Result<(), WorkbenchError> {
    bind_parameter_edit_provenance(
        model,
        TRUSS3D_LEAF_MEMBER_DELETE_EXTENSION_KEY,
        json!({
            "operation": "truss3d_leaf_member_delete",
            "removed_node_id": node_id,
            "removed_node_index": removed.node_index,
            "removed_coordinates_m": removed.coordinates_m,
            "removed_element_id": element_id,
            "removed_element_index": removed.element_index,
            "removed_element_type": "truss_3d",
            "removed_formulation": "linear_truss_3d",
            "removed_node_ids": removed.node_ids,
            "removed_material_id": removed.material_id,
            "removed_section_id": removed.section_id,
            "removed_offsets_m": {
                "i_global_m": removed.offsets_global_m[0],
                "j_global_m": removed.offsets_global_m[1]
            },
            "source_content_hash": source_content_hash,
            "source_semantic_hash": source_semantic_hash,
            "source_provenance_hash": source_provenance_hash,
            "claim_boundary": TRUSS3D_LEAF_MEMBER_DELETE_CLAIM_BOUNDARY
        }),
        source_content_hash,
    )
}

fn bind_parameter_edit_provenance(
    model: &mut Value,
    extension_key: &str,
    extension_value: Value,
    source_content_hash: &str,
) -> Result<(), WorkbenchError> {
    let model_id = model
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("model_id"))?
        .to_owned();
    let object = model
        .as_object_mut()
        .ok_or_else(|| snapshot_error("root object"))?;
    let upstream_provenance = object
        .get("provenance")
        .cloned()
        .ok_or_else(|| snapshot_error("provenance"))?;
    object.insert(
        "provenance".to_owned(),
        json!({
            "source_format": "neutral_json",
            "source_ref": format!("modelir-edit:{model_id}"),
            "source_sha256": source_content_hash,
            "normalizer_id": "structural-native-model-editor",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad"
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0
            },
            "extensions": {
                UPSTREAM_PROVENANCE_KEY: upstream_provenance
            }
        }),
    );
    object
        .get_mut("extensions")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| snapshot_error("root extensions"))?
        .insert(extension_key.to_owned(), extension_value);
    Ok(())
}

fn mark_roundtrip_node_approximated(
    model: &mut Value,
    node_id: &str,
) -> Result<(), WorkbenchError> {
    mark_roundtrip_entity_approximated(model, "node", node_id)
}

fn mark_roundtrip_entity_approximated(
    model: &mut Value,
    entity_kind: &str,
    entity_id: &str,
) -> Result<(), WorkbenchError> {
    let rows = model
        .get_mut("roundtrip_map")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| snapshot_error("roundtrip_map"))?;
    for row in rows {
        if row.get("entity_kind").and_then(Value::as_str) == Some(entity_kind)
            && row.get("model_ir_entity_id").and_then(Value::as_str) == Some(entity_id)
            && matches!(
                row.get("mapping_status").and_then(Value::as_str),
                Some("exact" | "canonicalized")
            )
        {
            row.as_object_mut()
                .ok_or_else(|| snapshot_error("roundtrip_map entity row"))?
                .insert(
                    "mapping_status".to_owned(),
                    Value::String("approximated".to_owned()),
                );
        }
    }
    Ok(())
}

fn components_object(components_si: [f64; 6]) -> Value {
    json!({
        "FX": components_si[0],
        "FY": components_si[1],
        "FZ": components_si[2],
        "MX": components_si[3],
        "MY": components_si[4],
        "MZ": components_si[5]
    })
}

fn linear_material_parameters_object(parameters: LinearElasticMaterialParametersV1) -> Value {
    json!({
        "elastic_modulus_pa": parameters.elastic_modulus_pa,
        "poisson_ratio": parameters.poisson_ratio,
        "density_kg_m3": parameters.density_kg_m3
    })
}

fn linear_material_state_schema_object() -> Value {
    json!({
        "stateful": false,
        "state_update_epoch": "none",
        "supports_trial_commit_rollback": true
    })
}

fn linear_material_parameters_equal(
    left: LinearElasticMaterialParametersV1,
    right: LinearElasticMaterialParametersV1,
) -> bool {
    [
        left.elastic_modulus_pa,
        left.poisson_ratio,
        left.density_kg_m3,
    ]
    .iter()
    .zip([
        right.elastic_modulus_pa,
        right.poisson_ratio,
        right.density_kg_m3,
    ])
    .all(|(left, right)| normalized_number_bits(*left) == normalized_number_bits(right))
}

fn frame_section_parameter_values(parameters: FrameSectionParametersV1) -> [f64; 6] {
    [
        parameters.area_m2,
        parameters.iy_m4,
        parameters.iz_m4,
        parameters.torsional_constant_m4,
        parameters.shear_area_y_m2,
        parameters.shear_area_z_m2,
    ]
}

fn frame_section_parameters_object(parameters: FrameSectionParametersV1) -> Value {
    json!({
        "area_m2": parameters.area_m2,
        "iy_m4": parameters.iy_m4,
        "iz_m4": parameters.iz_m4,
        "torsional_constant_m4": parameters.torsional_constant_m4,
        "shear_area_y_m2": parameters.shear_area_y_m2,
        "shear_area_z_m2": parameters.shear_area_z_m2
    })
}

fn truss_section_parameters_object(parameters: TrussSectionParametersV1) -> Value {
    json!({"area_m2": parameters.area_m2})
}

fn frame_section_parameters_equal(
    left: FrameSectionParametersV1,
    right: FrameSectionParametersV1,
) -> bool {
    frame_section_parameter_values(left)
        .iter()
        .zip(frame_section_parameter_values(right))
        .all(|(left, right)| normalized_number_bits(*left) == normalized_number_bits(right))
}

fn constraint_value_unit(dof: &str) -> &'static str {
    if matches!(dof, "UX" | "UY" | "UZ") {
        "m"
    } else {
        "rad"
    }
}

fn fixed_constraint_values_object() -> Value {
    json!({"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0})
}

fn normalized_number_bits(value: f64) -> u64 {
    let bits = value.to_bits();
    if bits.trailing_zeros() >= 63 {
        0
    } else {
        bits
    }
}

fn finite_number(value: &Value, field: &str) -> Result<f64, WorkbenchError> {
    value
        .as_f64()
        .filter(|number| number.is_finite())
        .ok_or_else(|| snapshot_error(field))
}

fn snapshot_error(field: &str) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_model_edit_snapshot_invalid",
        format!("verified ModelIR snapshot has an invalid {field} field"),
    )
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Value};

    use super::{
        append_linear_load_combination, append_nested_linear_load_combination, append_node,
        constraint_value_unit, linear_load_combination_terms_value,
        mark_roundtrip_entity_approximated, mark_roundtrip_node_approximated,
        nested_linear_load_combination_terms_value, normalized_number_bits,
        remove_fixed_constraint, remove_frame3d_leaf_member, remove_frame_section,
        remove_linear_load_combination, remove_linear_load_pattern, remove_linear_material,
        remove_nodal_load, remove_orphan_node, remove_truss3d_leaf_member, remove_truss_section,
        replace_direct_linear_load_combination_factor,
        replace_direct_linear_load_combination_reference,
        replace_nested_linear_load_combination_factor,
        replace_nested_linear_load_combination_reference, validate_constraint_value_edit_request,
        validate_direct_linear_load_combination_factor_edit_request,
        validate_direct_linear_load_combination_reference_edit_request, validate_edit_request,
        validate_element_connectivity_edit_request, validate_fixed_constraint_add_request,
        validate_fixed_constraint_delete_request, validate_frame3d_leaf_member_delete_request,
        validate_frame3d_member_add_request, validate_frame_element_orientation_edit_request,
        validate_frame_element_properties_edit_request, validate_frame_element_property_references,
        validate_frame_section_add_request, validate_frame_section_delete_request,
        validate_frame_section_edit_request, validate_linear_load_combination_add_request,
        validate_linear_load_combination_delete_request, validate_linear_load_pattern_add_request,
        validate_linear_load_pattern_delete_request, validate_linear_material_add_request,
        validate_linear_material_delete_request, validate_linear_material_edit_request,
        validate_nested_linear_load_combination_add_request,
        validate_nested_linear_load_combination_factor_edit_request,
        validate_nested_linear_load_combination_reference_edit_request,
        validate_nodal_load_add_request, validate_nodal_load_delete_request,
        validate_nodal_load_edit_request, validate_node_add_request,
        validate_orphan_node_delete_request, validate_truss3d_leaf_member_delete_request,
        validate_truss3d_member_add_request, validate_truss3d_member_properties,
        validate_truss_element_properties_edit_request, validate_truss_element_property_references,
        validate_truss_section_add_request, validate_truss_section_delete_request,
        validate_truss_section_edit_request, FrameSectionParametersV1,
        LinearElasticMaterialParametersV1, LinearLoadCombinationDeletionProfileV1,
        LinearLoadCombinationReferenceKindV1, LinearLoadCombinationTermV1,
        NestedLinearLoadCombinationTermV1, TrussSectionParametersV1, MAX_MODEL_BYTES,
        MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1,
    };

    #[test]
    fn signed_zero_is_the_same_canonical_coordinate() {
        assert_eq!(normalized_number_bits(0.0), normalized_number_bits(-0.0));
        assert_ne!(normalized_number_bits(1.0), normalized_number_bits(-1.0));
    }

    #[test]
    fn node_add_requires_bounded_identity_finite_unique_coordinates_and_contiguous_index() {
        validate_node_add_request(0, "N3", [2.0, 0.0, 0.0]).expect("valid node-add request");
        assert_eq!(
            validate_node_add_request(0, "N3", [f64::NAN, 0.0, 0.0])
                .expect_err("non-finite coordinate")
                .code,
            "workbench_model_add_node_coordinate_invalid"
        );
        assert!(validate_node_add_request(0, "", [2.0, 0.0, 0.0]).is_err());

        let mut model = json!({
            "nodes": [
                {"id": "N1", "index": 0, "coordinates_m": [0.0, 0.0, 0.0]},
                {"id": "N2", "index": 1, "coordinates_m": [1.0, 0.0, 0.0]}
            ]
        });
        assert_eq!(
            append_node(&mut model, "N3", [2.0, 0.0, 0.0]).expect("append node"),
            2
        );
        assert_eq!(model["nodes"][2]["index"], json!(2));
        assert_eq!(model["nodes"][2]["source_id"], Value::Null);
        assert_eq!(model["nodes"][2]["extensions"], json!({}));
        assert_eq!(
            append_node(&mut model, "N3", [3.0, 0.0, 0.0])
                .expect_err("duplicate identity")
                .code,
            "workbench_model_add_node_exists"
        );
        assert_eq!(
            append_node(&mut model, "N4", [2.0, -0.0, 0.0])
                .expect_err("duplicate canonical coordinates")
                .code,
            "workbench_model_add_node_coordinate_exists"
        );
    }

    #[test]
    fn orphan_node_delete_requires_terminal_neutral_unreferenced_empty_row() {
        validate_orphan_node_delete_request(0, "N3").expect("valid orphan-node deletion");
        assert!(validate_orphan_node_delete_request(0, "").is_err());

        let model = json!({
            "nodes": [
                {"id": "N1", "index": 0, "coordinates_m": [0, 0, 0], "source_id": "source:N1", "extensions": {}},
                {"id": "N2", "index": 1, "coordinates_m": [1, 0, 0], "source_id": "source:N2", "extensions": {}},
                {"id": "N3", "index": 2, "coordinates_m": [2, 0, 0], "source_id": null, "extensions": {}}
            ],
            "elements": [],
            "constraints": [],
            "load_patterns": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_orphan_node(&mut deleted, "N3").expect("delete orphan node");
        assert_eq!(removed.node_index, 2);
        assert_eq!(
            removed.coordinates_m.map(f64::to_bits),
            [2.0_f64, 0.0, 0.0].map(f64::to_bits)
        );
        assert_eq!(removed.extensions, json!({}));
        assert_eq!(
            deleted["nodes"].as_array().expect("retained nodes").len(),
            2
        );

        let mut nonterminal = model.clone();
        assert_eq!(
            remove_orphan_node(&mut nonterminal, "N2")
                .expect_err("nonterminal node")
                .code,
            "workbench_model_delete_orphan_node_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["nodes"][2]["source_id"] = json!("source:N3");
        assert_eq!(
            remove_orphan_node(&mut source_owned, "N3")
                .expect_err("source-owned node")
                .code,
            "workbench_model_delete_orphan_node_source_owned"
        );
        let mut extended = model.clone();
        extended["nodes"][2]["extensions"] = json!({"external:owner": "external"});
        assert_eq!(
            remove_orphan_node(&mut extended, "N3")
                .expect_err("extended node")
                .code,
            "workbench_model_delete_orphan_node_extensions_unsupported"
        );
        let mut element = model.clone();
        element["elements"] = json!([{"node_ids": ["N1", "N3"]}]);
        assert_eq!(
            remove_orphan_node(&mut element, "N3")
                .expect_err("element reference")
                .code,
            "workbench_model_delete_orphan_node_referenced_by_element"
        );
        let mut constraint = model.clone();
        constraint["constraints"] = json!([{"node_id": "N3"}]);
        assert_eq!(
            remove_orphan_node(&mut constraint, "N3")
                .expect_err("constraint reference")
                .code,
            "workbench_model_delete_orphan_node_referenced_by_constraint"
        );
        let mut load = model.clone();
        load["load_patterns"] = json!([{"nodal_loads": [{"node_id": "N3"}]}]);
        assert_eq!(
            remove_orphan_node(&mut load, "N3")
                .expect_err("load reference")
                .code,
            "workbench_model_delete_orphan_node_referenced_by_load"
        );
        let mut unsupported = model.clone();
        unsupported["unsupported_features"] = json!([{"source_entity_id": "N3"}]);
        assert_eq!(
            remove_orphan_node(&mut unsupported, "N3")
                .expect_err("unsupported-feature reference")
                .code,
            "workbench_model_delete_orphan_node_unsupported_feature_owned"
        );
        let mut mapped = model.clone();
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "N3"}]);
        assert_eq!(
            remove_orphan_node(&mut mapped, "N3")
                .expect_err("round-trip reference")
                .code,
            "workbench_model_delete_orphan_node_roundtrip_owned"
        );
        let mut minimum = model;
        minimum["nodes"].as_array_mut().expect("nodes").pop();
        assert_eq!(
            remove_orphan_node(&mut minimum, "N2")
                .expect_err("minimum topology")
                .code,
            "workbench_model_delete_orphan_node_minimum_topology"
        );
    }

    #[test]
    fn edit_request_bounds_have_stable_error_taxonomy() {
        let too_large = usize::try_from(MAX_MODEL_BYTES).expect("model size fits usize") + 1;
        assert_eq!(
            validate_edit_request(too_large, "N1", [0.0; 3])
                .expect_err("oversized edit request")
                .code,
            "workbench_model_edit_input_too_large"
        );
        assert_eq!(
            validate_edit_request(0, "", [0.0; 3])
                .expect_err("empty edit node identity")
                .code,
            "workbench_model_edit_node_id_invalid"
        );
        assert_eq!(
            validate_edit_request(0, "N1", [f64::NAN, 0.0, 0.0])
                .expect_err("non-finite edit coordinate")
                .code,
            "workbench_model_edit_coordinate_invalid"
        );
    }

    #[test]
    fn roundtrip_mapping_only_degrades_direct_source_claims() {
        let mut model = json!({
            "roundtrip_map": [
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "exact"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "canonicalized"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "approximated"},
                {"entity_kind": "node", "model_ir_entity_id": "N2", "mapping_status": "unsupported"},
                {"entity_kind": "node", "model_ir_entity_id": "N1", "mapping_status": "exact"}
            ]
        });
        mark_roundtrip_node_approximated(&mut model, "N2").expect("mapping update");
        let statuses = model["roundtrip_map"]
            .as_array()
            .expect("mapping rows")
            .iter()
            .map(|row| row["mapping_status"].as_str().expect("mapping status"))
            .collect::<Vec<_>>();
        assert_eq!(
            statuses,
            [
                "approximated",
                "approximated",
                "approximated",
                "unsupported",
                "exact"
            ]
        );
    }

    #[test]
    fn nodal_load_edit_request_bounds_have_stable_error_taxonomy() {
        assert_eq!(
            validate_nodal_load_edit_request(0, "", "L1", [0.0; 6])
                .expect_err("empty pattern identity")
                .code,
            "workbench_model_edit_load_pattern_id_invalid"
        );
        assert_eq!(
            validate_nodal_load_edit_request(0, "LC1", "", [0.0; 6])
                .expect_err("empty load identity")
                .code,
            "workbench_model_edit_nodal_load_id_invalid"
        );
        assert_eq!(
            validate_nodal_load_edit_request(
                0,
                "LC1",
                "L1",
                [0.0, f64::INFINITY, 0.0, 0.0, 0.0, 0.0],
            )
            .expect_err("non-finite load component")
            .code,
            "workbench_model_edit_load_component_invalid"
        );
    }

    #[test]
    fn load_pattern_roundtrip_mapping_degrades_without_touching_other_entities() {
        let mut model = json!({
            "roundtrip_map": [
                {"entity_kind": "load_pattern", "model_ir_entity_id": "LC1", "mapping_status": "exact"},
                {"entity_kind": "load_pattern", "model_ir_entity_id": "LC2", "mapping_status": "canonicalized"},
                {"entity_kind": "node", "model_ir_entity_id": "LC1", "mapping_status": "exact"}
            ]
        });
        mark_roundtrip_entity_approximated(&mut model, "load_pattern", "LC1")
            .expect("load-pattern mapping update");
        assert_eq!(model["roundtrip_map"][0]["mapping_status"], "approximated");
        assert_eq!(model["roundtrip_map"][1]["mapping_status"], "canonicalized");
        assert_eq!(model["roundtrip_map"][2]["mapping_status"], "exact");
    }

    #[test]
    fn constraint_value_request_has_closed_dofs_units_and_error_taxonomy() {
        assert_eq!(constraint_value_unit("UX"), "m");
        assert_eq!(constraint_value_unit("RZ"), "rad");
        assert_eq!(
            validate_constraint_value_edit_request(0, "", "UX", 0.0)
                .expect_err("empty constraint identity")
                .code,
            "workbench_model_edit_constraint_id_invalid"
        );
        assert_eq!(
            validate_constraint_value_edit_request(0, "BC1", "QX", 0.0)
                .expect_err("unknown constraint DOF")
                .code,
            "workbench_model_edit_constraint_dof_invalid"
        );
        assert_eq!(
            validate_constraint_value_edit_request(0, "BC1", "UX", f64::NAN)
                .expect_err("non-finite constraint value")
                .code,
            "workbench_model_edit_constraint_value_invalid"
        );
    }

    #[test]
    fn material_and_section_parameter_requests_have_closed_physical_ranges() {
        let material = LinearElasticMaterialParametersV1 {
            elastic_modulus_pa: 200_000_000_000.0,
            poisson_ratio: 0.3,
            density_kg_m3: 7850.0,
        };
        validate_linear_material_edit_request(0, "M1", material).expect("valid material request");
        for (parameters, expected_code) in [
            (
                LinearElasticMaterialParametersV1 {
                    elastic_modulus_pa: 0.0,
                    ..material
                },
                "workbench_model_edit_material_elastic_modulus_invalid",
            ),
            (
                LinearElasticMaterialParametersV1 {
                    poisson_ratio: 0.5,
                    ..material
                },
                "workbench_model_edit_material_poisson_ratio_invalid",
            ),
            (
                LinearElasticMaterialParametersV1 {
                    density_kg_m3: -0.01,
                    ..material
                },
                "workbench_model_edit_material_density_invalid",
            ),
        ] {
            assert_eq!(
                validate_linear_material_edit_request(0, "M1", parameters)
                    .expect_err("invalid material parameters")
                    .code,
                expected_code
            );
        }

        let section = FrameSectionParametersV1 {
            area_m2: 0.02,
            iy_m4: 0.000_08,
            iz_m4: 0.000_05,
            torsional_constant_m4: 0.000_01,
            shear_area_y_m2: 0.016,
            shear_area_z_m2: 0.016,
        };
        validate_frame_section_edit_request(0, "S1", section).expect("valid section request");
        for invalid_value in [0.0, -1.0, f64::INFINITY] {
            assert_eq!(
                validate_frame_section_edit_request(
                    0,
                    "S1",
                    FrameSectionParametersV1 {
                        torsional_constant_m4: invalid_value,
                        ..section
                    },
                )
                .expect_err("invalid frame-section parameter")
                .code,
                "workbench_model_edit_frame_section_parameter_invalid"
            );
        }
    }

    #[test]
    fn frame_element_orientation_request_requires_bounded_identity_and_finite_radians() {
        validate_frame_element_orientation_edit_request(0, "E1", 0.25)
            .expect("valid frame-element orientation request");
        assert_eq!(
            validate_frame_element_orientation_edit_request(0, "", 0.25)
                .expect_err("empty element identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_frame_element_orientation_edit_request(0, "E1", f64::NAN)
                .expect_err("non-finite element orientation")
                .code,
            "workbench_model_edit_element_orientation_invalid"
        );
    }

    #[test]
    fn frame_element_properties_request_requires_all_bounded_identities() {
        validate_frame_element_properties_edit_request(0, "E1", "M2", "S2")
            .expect("valid frame-element property request");
        for (element, material, section) in [("", "M2", "S2"), ("E1", "", "S2"), ("E1", "M2", "")] {
            assert_eq!(
                validate_frame_element_properties_edit_request(0, element, material, section)
                    .expect_err("empty property-edit identity")
                    .code,
                "workbench_model_edit_entity_id_invalid"
            );
        }
    }

    #[test]
    fn frame_element_property_references_require_compatible_v1_families() {
        let model = json!({
            "materials": [
                {"id": "M1", "law_id": "linear_elastic_isotropic", "parameter_set_version": "1"},
                {"id": "M_NONLINEAR", "law_id": "bilinear_combined_hardening_steel", "parameter_set_version": "1"}
            ],
            "sections": [
                {"id": "S1", "family_id": "frame_3d", "parameter_set_version": "1"},
                {"id": "S_PLANAR", "family_id": "rectangular_rc_fiber_2d", "parameter_set_version": "1"}
            ]
        });
        validate_frame_element_property_references(&model, "M1", "S1")
            .expect("compatible frame-element properties");
        assert_eq!(
            validate_frame_element_property_references(&model, "M_NONLINEAR", "S1")
                .expect_err("nonlinear material is outside assignment slice")
                .code,
            "workbench_model_edit_frame_element_material_unsupported"
        );
        assert_eq!(
            validate_frame_element_property_references(&model, "M1", "S_PLANAR")
                .expect_err("planar section is outside assignment slice")
                .code,
            "workbench_model_edit_frame_element_section_unsupported"
        );
    }

    #[test]
    fn element_connectivity_request_requires_bounded_distinct_identities() {
        validate_element_connectivity_edit_request(0, "E1", ["N1", "N2"])
            .expect("valid element connectivity request");
        assert_eq!(
            validate_element_connectivity_edit_request(0, "", ["N1", "N2"])
                .expect_err("empty element identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_element_connectivity_edit_request(0, "E1", ["N1", ""])
                .expect_err("empty endpoint identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_element_connectivity_edit_request(0, "E1", ["N1", "N1"])
                .expect_err("identical endpoints")
                .code,
            "workbench_model_edit_element_connectivity_invalid"
        );
    }

    #[test]
    fn frame3d_member_add_requires_bounded_distinct_identities_and_finite_coordinates() {
        validate_frame3d_member_add_request(0, "N3", [4.0, 0.0, 0.0], "E2", "N2", "M1", "S1")
            .expect("valid frame3d member addition request");
        assert_eq!(
            validate_frame3d_member_add_request(0, "N2", [4.0, 0.0, 0.0], "E2", "N2", "M1", "S1",)
                .expect_err("new and existing node identities must differ")
                .code,
            "workbench_model_add_frame3d_member_node_identity_invalid"
        );
        assert_eq!(
            validate_frame3d_member_add_request(
                0,
                "N3",
                [f64::NAN, 0.0, 0.0],
                "E2",
                "N2",
                "M1",
                "S1",
            )
            .expect_err("new node coordinates must be finite")
            .code,
            "workbench_model_add_frame3d_member_coordinate_invalid"
        );
        assert_eq!(
            validate_frame3d_member_add_request(0, "N3", [4.0, 0.0, 0.0], "", "N2", "M1", "S1",)
                .expect_err("new element identity must be bounded")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
    }

    #[test]
    fn nodal_load_add_requires_bounded_identities_finite_and_nonzero_components() {
        validate_nodal_load_add_request(
            0,
            "LC_WEAK",
            "L_WEAK_N3",
            "N3",
            [0.0, -1_000.0, 0.0, 0.0, 0.0, 0.0],
        )
        .expect("valid nodal-load addition request");
        assert_eq!(
            validate_nodal_load_add_request(0, "LC_WEAK", "", "N3", [1.0; 6])
                .expect_err("new load identity must be bounded")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_nodal_load_add_request(
                0,
                "LC_WEAK",
                "L_WEAK_N3",
                "N3",
                [0.0, f64::NAN, 0.0, 0.0, 0.0, 0.0],
            )
            .expect_err("new load components must be finite")
            .code,
            "workbench_model_add_nodal_load_component_invalid"
        );
        assert_eq!(
            validate_nodal_load_add_request(0, "LC_WEAK", "L_WEAK_N3", "N3", [-0.0; 6])
                .expect_err("new load must not be all zero")
                .code,
            "workbench_model_add_nodal_load_zero_components"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn nodal_load_delete_requires_terminal_neutral_nonzero_row_and_nonzero_retained_load() {
        validate_nodal_load_delete_request(0, "LC_WEAK", "L_WEAK_N3")
            .expect("valid nodal-load deletion request");
        assert_eq!(
            validate_nodal_load_delete_request(0, "LC_WEAK", "")
                .expect_err("empty nodal-load identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let model = json!({
            "load_patterns": [{
                "id": "LC_WEAK",
                "index": 0,
                "analysis_type": "linear_static",
                "nodal_loads": [
                    {
                        "id": "L_WEAK_N2",
                        "index": 0,
                        "node_id": "N2",
                        "components_si": {"FX": 0, "FY": -10000, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0},
                        "source_id": "source:L_WEAK_N2"
                    },
                    {
                        "id": "L_WEAK_N3",
                        "index": 1,
                        "node_id": "N3",
                        "components_si": {"FX": 0, "FY": -1000, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0},
                        "source_id": null
                    }
                ]
            }],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_nodal_load(&mut deleted, "LC_WEAK", "L_WEAK_N3")
            .expect("delete terminal neutral nodal load");
        assert_eq!(removed.load_pattern_index, 0);
        assert_eq!(removed.nodal_load_index, 1);
        assert_eq!(removed.node_id, "N3");
        assert_eq!(
            deleted["load_patterns"][0]["nodal_loads"]
                .as_array()
                .expect("nodal loads")
                .len(),
            1
        );

        let mut nonterminal = model.clone();
        assert_eq!(
            remove_nodal_load(&mut nonterminal, "LC_WEAK", "L_WEAK_N2")
                .expect_err("nonterminal nodal load")
                .code,
            "workbench_model_delete_nodal_load_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["load_patterns"][0]["nodal_loads"][1]["source_id"] = json!("source:L_WEAK_N3");
        assert_eq!(
            remove_nodal_load(&mut source_owned, "LC_WEAK", "L_WEAK_N3")
                .expect_err("source-owned nodal load")
                .code,
            "workbench_model_delete_nodal_load_source_owned"
        );
        let mut zero = model.clone();
        zero["load_patterns"][0]["nodal_loads"][1]["components_si"] =
            json!({"FX": 0, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0});
        assert_eq!(
            remove_nodal_load(&mut zero, "LC_WEAK", "L_WEAK_N3")
                .expect_err("zero nodal load")
                .code,
            "workbench_model_delete_nodal_load_zero_components"
        );
        let mut retained_zero = model.clone();
        retained_zero["load_patterns"][0]["nodal_loads"][0]["components_si"] =
            json!({"FX": 0, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0});
        assert_eq!(
            remove_nodal_load(&mut retained_zero, "LC_WEAK", "L_WEAK_N3")
                .expect_err("zero retained nodal load")
                .code,
            "workbench_model_delete_nodal_load_retained_pattern_zero"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "L_WEAK_N3"}]);
        assert_eq!(
            remove_nodal_load(&mut feature_owned, "LC_WEAK", "L_WEAK_N3")
                .expect_err("unsupported-feature-owned nodal load")
                .code,
            "workbench_model_delete_nodal_load_unsupported_feature_owned"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "L_WEAK_N3"}]);
        assert_eq!(
            remove_nodal_load(&mut mapped, "LC_WEAK", "L_WEAK_N3")
                .expect_err("round-trip-owned nodal load")
                .code,
            "workbench_model_delete_nodal_load_roundtrip_owned"
        );
        let mut minimum = deleted;
        assert_eq!(
            remove_nodal_load(&mut minimum, "LC_WEAK", "L_WEAK_N2")
                .expect_err("minimum retained pattern")
                .code,
            "workbench_model_delete_nodal_load_minimum_pattern"
        );
    }

    #[test]
    fn fixed_constraint_add_requires_bounded_identities() {
        validate_fixed_constraint_add_request(0, "BC_N3", "N3")
            .expect("valid fixed-constraint addition request");
        assert_eq!(
            validate_fixed_constraint_add_request(0, "", "N3")
                .expect_err("empty constraint identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_fixed_constraint_add_request(0, "BC_N3", "")
                .expect_err("empty node identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
    }

    #[test]
    fn fixed_constraint_delete_requires_terminal_neutral_unreferenced_homogeneous_row() {
        validate_fixed_constraint_delete_request(0, "BC_N3")
            .expect("valid fixed-constraint deletion request");
        assert_eq!(
            validate_fixed_constraint_delete_request(0, "")
                .expect_err("empty constraint identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let model = json!({
            "constraints": [
                {
                    "id": "BC1",
                    "index": 0,
                    "type": "fixed_dofs",
                    "node_id": "N1",
                    "dofs": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
                    "prescribed_values_si": {"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0},
                    "source_id": "source:BC1"
                },
                {
                    "id": "BC_N3",
                    "index": 1,
                    "type": "fixed_dofs",
                    "node_id": "N3",
                    "dofs": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
                    "prescribed_values_si": {"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0},
                    "source_id": null
                }
            ],
            "construction_stages": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_fixed_constraint(&mut deleted, "BC_N3")
            .expect("delete terminal neutral fixed constraint");
        assert_eq!(removed.constraint_index, 1);
        assert_eq!(removed.node_id, "N3");
        assert_eq!(
            deleted["constraints"]
                .as_array()
                .expect("constraints")
                .len(),
            1
        );

        let mut staged = model.clone();
        staged["construction_stages"] = json!([{
            "active_constraint_ids": ["BC_N3"]
        }]);
        assert_eq!(
            remove_fixed_constraint(&mut staged, "BC_N3")
                .expect_err("staged constraint")
                .code,
            "workbench_model_delete_fixed_constraint_referenced_by_stage"
        );
        let mut nonzero = model.clone();
        nonzero["constraints"][1]["prescribed_values_si"]["UY"] = json!(0.001);
        assert_eq!(
            remove_fixed_constraint(&mut nonzero, "BC_N3")
                .expect_err("nonzero fixed constraint")
                .code,
            "workbench_model_delete_fixed_constraint_not_homogeneous"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "BC_N3"}]);
        assert_eq!(
            remove_fixed_constraint(&mut mapped, "BC_N3")
                .expect_err("mapped constraint")
                .code,
            "workbench_model_delete_fixed_constraint_roundtrip_owned"
        );
        let mut feature_owned = deleted.clone();
        feature_owned["constraints"]
            .as_array_mut()
            .expect("constraints")
            .push(json!({
                "id": "BC_N3",
                "index": 1,
                "type": "fixed_dofs",
                "node_id": "N3",
                "dofs": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
                "prescribed_values_si": {"UX": 0, "UY": 0, "UZ": 0, "RX": 0, "RY": 0, "RZ": 0},
                "source_id": null
            }));
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "BC_N3"}]);
        assert_eq!(
            remove_fixed_constraint(&mut feature_owned, "BC_N3")
                .expect_err("unsupported-feature-owned constraint")
                .code,
            "workbench_model_delete_fixed_constraint_unsupported_feature_owned"
        );
        let mut minimum = deleted;
        assert_eq!(
            remove_fixed_constraint(&mut minimum, "BC1")
                .expect_err("minimum retained topology")
                .code,
            "workbench_model_delete_fixed_constraint_minimum_topology"
        );
    }

    #[test]
    fn linear_load_pattern_add_requires_bounded_identities_finite_and_nonzero_components() {
        validate_linear_load_pattern_add_request(
            0,
            "LC_CUSTOM",
            "L_CUSTOM_N2",
            "N2",
            [2_500.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        .expect("valid linear-load-pattern addition request");
        assert_eq!(
            validate_linear_load_pattern_add_request(0, "", "L_CUSTOM_N2", "N2", [1.0; 6])
                .expect_err("empty pattern identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        assert_eq!(
            validate_linear_load_pattern_add_request(
                0,
                "LC_CUSTOM",
                "L_CUSTOM_N2",
                "N2",
                [0.0, f64::NAN, 0.0, 0.0, 0.0, 0.0],
            )
            .expect_err("new load components must be finite")
            .code,
            "workbench_model_add_linear_load_pattern_component_invalid"
        );
        assert_eq!(
            validate_linear_load_pattern_add_request(
                0,
                "LC_CUSTOM",
                "L_CUSTOM_N2",
                "N2",
                [-0.0; 6],
            )
            .expect_err("new pattern must not contain an all-zero first load")
            .code,
            "workbench_model_add_linear_load_pattern_zero_components"
        );
    }

    #[test]
    fn linear_load_combination_add_requires_two_distinct_existing_linear_patterns() {
        let terms = [
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_WEAK".to_owned(),
                factor: 1.2,
            },
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_STRONG".to_owned(),
                factor: -0.5,
            },
        ];
        validate_linear_load_combination_add_request(0, "COMBO_SERVICE", &terms)
            .expect("valid linear-load-combination addition request");

        let mut invalid_factor = terms.clone();
        invalid_factor[0].factor = f64::NAN;
        assert_eq!(
            validate_linear_load_combination_add_request(0, "COMBO_SERVICE", &invalid_factor)
                .expect_err("non-finite factor")
                .code,
            "workbench_model_add_linear_load_combination_factor_invalid"
        );
        let mut zero_factor = terms.clone();
        zero_factor[0].factor = -0.0;
        assert_eq!(
            validate_linear_load_combination_add_request(0, "COMBO_SERVICE", &zero_factor)
                .expect_err("zero factor")
                .code,
            "workbench_model_add_linear_load_combination_factor_invalid"
        );
        let duplicate_terms = [terms[0].clone(), terms[0].clone()];
        assert_eq!(
            validate_linear_load_combination_add_request(0, "COMBO_SERVICE", &duplicate_terms,)
                .expect_err("duplicate pattern terms")
                .code,
            "workbench_model_add_linear_load_combination_pattern_duplicate"
        );

        let model = json!({
            "load_patterns": [
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": []
        });
        let mut added = model.clone();
        assert_eq!(
            append_linear_load_combination(&mut added, "COMBO_SERVICE", &terms)
                .expect("append linear load combination"),
            0
        );
        assert_eq!(
            added["load_combinations"][0],
            json!({
                "id": "COMBO_SERVICE",
                "index": 0,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            })
        );
        assert_eq!(
            append_linear_load_combination(&mut added, "COMBO_SERVICE", &terms)
                .expect_err("duplicate combination identity")
                .code,
            "workbench_model_add_linear_load_combination_identity_exists"
        );

        let mut missing = model.clone();
        let missing_terms = [
            terms[0].clone(),
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_MISSING".to_owned(),
                factor: 0.5,
            },
        ];
        assert_eq!(
            append_linear_load_combination(&mut missing, "COMBO_SERVICE", &missing_terms)
                .expect_err("missing load pattern")
                .code,
            "workbench_model_add_linear_load_combination_pattern_missing"
        );
        let mut unsupported = model;
        unsupported["load_patterns"][1]["analysis_type"] = json!("nonlinear_static");
        assert_eq!(
            append_linear_load_combination(&mut unsupported, "COMBO_SERVICE", &terms)
                .expect_err("unsupported load pattern")
                .code,
            "workbench_model_add_linear_load_combination_pattern_unsupported"
        );
    }

    #[test]
    fn direct_linear_load_combination_add_accepts_three_to_64_unique_patterns() {
        let direct_terms = vec![
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_AXIAL".to_owned(),
                factor: 0.25,
            },
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_WEAK".to_owned(),
                factor: 1.2,
            },
            LinearLoadCombinationTermV1 {
                load_pattern_id: "LC_STRONG".to_owned(),
                factor: -0.5,
            },
        ];
        validate_linear_load_combination_add_request(0, "COMBO_DIRECT", &direct_terms)
            .expect("valid three-pattern direct combination");
        assert_eq!(
            validate_linear_load_combination_add_request(0, "COMBO_ONE", &direct_terms[..1])
                .expect_err("one direct term is unsupported")
                .code,
            "workbench_model_add_linear_load_combination_term_count_invalid"
        );

        let maximum_terms = (0..MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
            .map(|index| LinearLoadCombinationTermV1 {
                load_pattern_id: format!("LC_{index:02}"),
                factor: 1.0,
            })
            .collect::<Vec<_>>();
        validate_linear_load_combination_add_request(0, "COMBO_MAX", &maximum_terms)
            .expect("64 direct terms remain bounded");
        let mut excessive_terms = maximum_terms;
        excessive_terms.push(LinearLoadCombinationTermV1 {
            load_pattern_id: "LC_64".to_owned(),
            factor: 1.0,
        });
        assert_eq!(
            validate_linear_load_combination_add_request(0, "COMBO_TOO_LARGE", &excessive_terms)
                .expect_err("65 direct terms are unsupported")
                .code,
            "workbench_model_add_linear_load_combination_term_count_invalid"
        );

        let mut model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": []
        });
        assert_eq!(
            append_linear_load_combination(&mut model, "COMBO_DIRECT", &direct_terms)
                .expect("append three-pattern direct combination"),
            0
        );
        assert_eq!(
            model["load_combinations"][0]["terms"],
            linear_load_combination_terms_value(&direct_terms)
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn direct_linear_load_combination_factor_edit_is_bounded_and_preserves_term_identity() {
        validate_direct_linear_load_combination_factor_edit_request(
            0,
            "COMBO_DIRECT",
            "LC_WEAK",
            1.35,
        )
        .expect("valid direct factor edit request");
        assert_eq!(
            validate_direct_linear_load_combination_factor_edit_request(
                0,
                "COMBO_DIRECT",
                "LC_WEAK",
                -0.0,
            )
            .expect_err("zero factor")
            .code,
            "workbench_model_edit_linear_load_combination_factor_invalid"
        );

        let model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [{
                "id": "COMBO_DIRECT",
                "index": 0,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            }],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut edited = model.clone();
        let result = replace_direct_linear_load_combination_factor(
            &mut edited,
            "COMBO_DIRECT",
            "LC_WEAK",
            1.35,
        )
        .expect("edit existing direct term factor");
        assert_eq!(result.load_combination_index, 0);
        assert_eq!(result.term_index, 1);
        assert_eq!(result.previous_factor.to_bits(), 1.2_f64.to_bits());
        assert_eq!(edited["load_combinations"][0]["terms"][1]["factor"], 1.35);
        assert_eq!(
            edited["load_combinations"][0]["terms"][1]["ref_id"],
            model["load_combinations"][0]["terms"][1]["ref_id"]
        );
        assert_eq!(
            edited["load_combinations"][0]["terms"]
                .as_array()
                .map(Vec::len),
            Some(3)
        );

        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_MISSING",
                1.0,
            )
            .expect_err("missing target term")
            .code,
            "workbench_model_edit_linear_load_combination_term_missing"
        );
        let mut source_owned = model.clone();
        source_owned["load_combinations"][0]["source_id"] = json!("mgt:COMBO_DIRECT");
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut source_owned,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("source-owned combination")
            .code,
            "workbench_model_edit_linear_load_combination_source_owned"
        );
        let mut extended = model.clone();
        extended["load_combinations"][0]["extensions"] = json!({"owner": "external"});
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut extended,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("extended combination")
            .code,
            "workbench_model_edit_linear_load_combination_extensions_unsupported"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "COMBO_DIRECT"}]);
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut feature_owned,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("unsupported-feature-owned combination")
            .code,
            "workbench_model_edit_linear_load_combination_unsupported_feature_owned"
        );
        let mut roundtrip_owned = model.clone();
        roundtrip_owned["roundtrip_map"] = json!([{"model_ir_entity_id": "COMBO_DIRECT"}]);
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut roundtrip_owned,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("round-trip-owned combination")
            .code,
            "workbench_model_edit_linear_load_combination_roundtrip_owned"
        );
        let mut nested = model.clone();
        nested["load_combinations"][0]["terms"][0]["ref_kind"] = json!("load_combination");
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut nested,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("nested combination")
            .code,
            "workbench_model_edit_linear_load_combination_nested_unsupported"
        );
        let mut referenced = model;
        referenced["load_combinations"]
            .as_array_mut()
            .expect("load combinations")
            .push(json!({
                "id": "COMBO_NESTED",
                "index": 1,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_DIRECT", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                ],
                "source_id": null,
                "extensions": {}
            }));
        assert_eq!(
            replace_direct_linear_load_combination_factor(
                &mut referenced,
                "COMBO_DIRECT",
                "LC_WEAK",
                1.35,
            )
            .expect_err("referenced direct combination")
            .code,
            "workbench_model_edit_linear_load_combination_referenced_by_combination"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn direct_linear_load_combination_reference_edit_is_bounded_and_preserves_factor() {
        validate_direct_linear_load_combination_reference_edit_request(
            0,
            "COMBO_DIRECT",
            "LC_WEAK",
            "LC_AXIAL",
        )
        .expect("valid direct reference edit request");
        assert!(
            validate_direct_linear_load_combination_reference_edit_request(
                0,
                "COMBO_DIRECT",
                "LC_WEAK",
                "",
            )
            .is_err()
        );

        let model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"},
                {"id": "LC_MODAL", "analysis_type": "modal"}
            ],
            "load_combinations": [{
                "id": "COMBO_DIRECT",
                "index": 0,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            }],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut edited = model.clone();
        let result = replace_direct_linear_load_combination_reference(
            &mut edited,
            "COMBO_DIRECT",
            "LC_WEAK",
            "LC_AXIAL",
        )
        .expect("replace one existing direct pattern reference");
        assert_eq!(result.load_combination_index, 0);
        assert_eq!(result.term_index, 0);
        assert_eq!(result.preserved_factor.to_bits(), 1.2_f64.to_bits());
        assert_eq!(result.source_terms, model["load_combinations"][0]["terms"]);
        assert_eq!(result.edited_terms, edited["load_combinations"][0]["terms"]);
        assert_eq!(
            edited["load_combinations"][0]["terms"],
            json!([
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.2},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
            ])
        );
        assert_eq!(
            edited["load_combinations"][0]["terms"][0]["factor"],
            model["load_combinations"][0]["terms"][0]["factor"]
        );
        assert_eq!(
            edited["load_combinations"][0]["terms"][1],
            model["load_combinations"][0]["terms"][1]
        );

        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_MISSING",
                "LC_AXIAL",
            )
            .expect_err("missing source term")
            .code,
            "workbench_model_edit_linear_load_combination_term_missing"
        );
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_MISSING",
            )
            .expect_err("missing replacement pattern")
            .code,
            "workbench_model_edit_linear_load_combination_replacement_pattern_missing"
        );
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_MODAL",
            )
            .expect_err("nonlinear replacement pattern")
            .code,
            "workbench_model_edit_linear_load_combination_replacement_pattern_unsupported"
        );
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_STRONG",
            )
            .expect_err("duplicate replacement pattern")
            .code,
            "workbench_model_edit_linear_load_combination_replacement_pattern_duplicate"
        );
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_WEAK",
            )
            .expect_err("identical replacement pattern")
            .code,
            "workbench_model_edit_no_change"
        );
        let mut source_owned = model.clone();
        source_owned["load_combinations"][0]["source_id"] = json!("mgt:COMBO_DIRECT");
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut source_owned,
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_AXIAL",
            )
            .expect_err("source-owned combination")
            .code,
            "workbench_model_edit_linear_load_combination_source_owned"
        );
        let mut nested = model.clone();
        nested["load_combinations"][0]["terms"][0]["ref_kind"] = json!("load_combination");
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut nested,
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_AXIAL",
            )
            .expect_err("nested combination")
            .code,
            "workbench_model_edit_linear_load_combination_nested_unsupported"
        );
        let mut referenced = model;
        referenced["load_combinations"]
            .as_array_mut()
            .expect("load combinations")
            .push(json!({
                "id": "COMBO_PARENT",
                "index": 1,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_DIRECT", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                ],
                "source_id": null,
                "extensions": {}
            }));
        assert_eq!(
            replace_direct_linear_load_combination_reference(
                &mut referenced,
                "COMBO_DIRECT",
                "LC_WEAK",
                "LC_AXIAL",
            )
            .expect_err("referenced direct combination")
            .code,
            "workbench_model_edit_linear_load_combination_referenced_by_combination"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn nested_linear_load_combination_factor_edit_is_typed_bounded_and_non_cascading() {
        validate_nested_linear_load_combination_factor_edit_request(
            0,
            "COMBO_NESTED",
            "COMBO_BASE",
            0.75,
        )
        .expect("valid nested factor edit request");
        assert_eq!(
            validate_nested_linear_load_combination_factor_edit_request(
                0,
                "COMBO_NESTED",
                "COMBO_BASE",
                -0.0,
            )
            .expect_err("zero nested factor")
            .code,
            "workbench_model_edit_nested_linear_load_combination_factor_invalid"
        );

        let model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [
                {
                    "id": "COMBO_BASE",
                    "index": 0,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                        {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                    ],
                    "source_id": null,
                    "extensions": {}
                },
                {
                    "id": "COMBO_NESTED",
                    "index": 1,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                        {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                    ],
                    "source_id": null,
                    "extensions": {}
                }
            ],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut edited = model.clone();
        let result = replace_nested_linear_load_combination_factor(
            &mut edited,
            "COMBO_NESTED",
            LinearLoadCombinationReferenceKindV1::LoadCombination,
            "COMBO_BASE",
            0.75,
        )
        .expect("edit existing nested typed term factor");
        assert_eq!(result.load_combination_index, 1);
        assert_eq!(result.term_index, 0);
        assert_eq!(result.previous_factor.to_bits(), 0.5_f64.to_bits());
        assert_eq!(edited["load_combinations"][1]["terms"][0]["factor"], 0.75);
        assert_eq!(
            edited["load_combinations"][1]["terms"][0]["ref_id"],
            model["load_combinations"][1]["terms"][0]["ref_id"]
        );
        assert_eq!(
            edited["load_combinations"][0], model["load_combinations"][0],
            "descendant combination must remain byte-equivalent in the JSON value"
        );
        assert_eq!(
            result.source_expansion.expanded_pattern_terms,
            json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.6},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.25},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
            ])
        );
        assert_eq!(
            result.edited_expansion.expanded_pattern_terms,
            json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.899_999_999_999_999_9},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.375},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
            ])
        );

        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("typed mismatch")
            .code,
            "workbench_model_edit_nested_linear_load_combination_term_missing"
        );
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut model.clone(),
                "COMBO_BASE",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_WEAK",
                1.35,
            )
            .expect_err("direct root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported"
        );
        let mut source_owned = model.clone();
        source_owned["load_combinations"][1]["source_id"] = json!("mgt:COMBO_NESTED");
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut source_owned,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("source-owned nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_source_owned"
        );
        let mut extended = model.clone();
        extended["load_combinations"][1]["extensions"] = json!({"owner": "external"});
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut extended,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("extended nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_extensions_unsupported"
        );
        let mut duplicate = model.clone();
        duplicate["load_combinations"][1]["terms"][1] = json!({
            "ref_id": "COMBO_BASE",
            "ref_kind": "load_combination",
            "factor": 0.25
        });
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut duplicate,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("duplicate typed reference")
            .code,
            "workbench_model_edit_nested_linear_load_combination_reference_duplicate"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "COMBO_NESTED"}]);
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut feature_owned,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("unsupported-feature-owned nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_unsupported_feature_owned"
        );
        let mut roundtrip_owned = model.clone();
        roundtrip_owned["roundtrip_map"] = json!([{"model_ir_entity_id": "COMBO_NESTED"}]);
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut roundtrip_owned,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("round-trip-owned nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_roundtrip_owned"
        );
        let mut referenced = model;
        referenced["load_combinations"]
            .as_array_mut()
            .expect("load combinations")
            .push(json!({
                "id": "COMBO_PARENT",
                "index": 2,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_NESTED", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 0.25}
                ],
                "source_id": null,
                "extensions": {}
            }));
        assert_eq!(
            replace_nested_linear_load_combination_factor(
                &mut referenced,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                0.75,
            )
            .expect_err("referenced nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_referenced_by_combination"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn nested_linear_load_combination_reference_edit_is_typed_bounded_and_non_cascading() {
        validate_nested_linear_load_combination_reference_edit_request(
            0,
            "COMBO_NESTED",
            "LC_AXIAL",
            "COMBO_ALTERNATE",
        )
        .expect("valid nested reference edit request");
        assert!(
            validate_nested_linear_load_combination_reference_edit_request(
                0,
                "COMBO_NESTED",
                "LC_AXIAL",
                "",
            )
            .is_err()
        );

        let model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [
                {
                    "id": "COMBO_BASE",
                    "index": 0,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                        {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                    ],
                    "source_id": null,
                    "extensions": {}
                },
                {
                    "id": "COMBO_ALTERNATE",
                    "index": 1,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.8},
                        {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 0.2}
                    ],
                    "source_id": null,
                    "extensions": {}
                },
                {
                    "id": "COMBO_NESTED",
                    "index": 2,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                        {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                    ],
                    "source_id": null,
                    "extensions": {}
                }
            ],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut edited = model.clone();
        let result = replace_nested_linear_load_combination_reference(
            &mut edited,
            "COMBO_NESTED",
            LinearLoadCombinationReferenceKindV1::LoadPattern,
            "LC_AXIAL",
            LinearLoadCombinationReferenceKindV1::LoadCombination,
            "COMBO_ALTERNATE",
        )
        .expect("replace a pattern root term with a combination term");
        assert_eq!(result.load_combination_index, 2);
        assert_eq!(result.term_index, 1);
        assert_eq!(result.preserved_factor.to_bits(), 0.25_f64.to_bits());
        assert_eq!(
            edited["load_combinations"][0],
            model["load_combinations"][0]
        );
        assert_eq!(
            edited["load_combinations"][1],
            model["load_combinations"][1]
        );
        assert_eq!(
            edited["load_combinations"][2]["terms"],
            json!([
                {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                {"ref_id": "COMBO_ALTERNATE", "ref_kind": "load_combination", "factor": 0.25}
            ])
        );
        assert_eq!(
            result.source_expansion.expanded_pattern_terms,
            json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.6},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.25},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
            ])
        );
        assert_eq!(
            result.edited_expansion.expanded_pattern_terms,
            json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.8},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.2}
            ])
        );
        assert_eq!(result.source_expansion.expanded_term_count, 3);
        assert_eq!(result.edited_expansion.expanded_term_count, 4);

        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
            )
            .expect_err("no-op nested reference edit")
            .code,
            "workbench_model_edit_no_change"
        );
        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
            )
            .expect_err("duplicate replacement typed reference")
            .code,
            "workbench_model_edit_nested_linear_load_combination_replacement_reference_duplicate"
        );
        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_MISSING",
            )
            .expect_err("missing replacement combination")
            .code,
            "workbench_model_edit_nested_linear_load_combination_replacement_combination_missing"
        );
        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_BASE",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_WEAK",
            )
            .expect_err("reference edit cannot degrade the nested root to direct")
            .code,
            "workbench_model_edit_nested_linear_load_combination_direct_unsupported"
        );
        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut model.clone(),
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_NESTED",
            )
            .expect_err("self-cycle replacement")
            .code,
            "workbench_model_linear_nested_combination_cycle"
        );

        let mut referenced = model;
        referenced["load_combinations"]
            .as_array_mut()
            .expect("load combinations")
            .push(json!({
                "id": "COMBO_PARENT",
                "index": 3,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_NESTED", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 0.25}
                ],
                "source_id": null,
                "extensions": {}
            }));
        assert_eq!(
            replace_nested_linear_load_combination_reference(
                &mut referenced,
                "COMBO_NESTED",
                LinearLoadCombinationReferenceKindV1::LoadPattern,
                "LC_AXIAL",
                LinearLoadCombinationReferenceKindV1::LoadCombination,
                "COMBO_ALTERNATE",
            )
            .expect_err("referenced nested root")
            .code,
            "workbench_model_edit_nested_linear_load_combination_referenced_by_combination"
        );
    }

    #[test]
    fn nested_linear_load_combination_add_requires_typed_existing_references() {
        let terms = [
            NestedLinearLoadCombinationTermV1 {
                reference_id: "COMBO_BASE".to_owned(),
                reference_kind: LinearLoadCombinationReferenceKindV1::LoadCombination,
                factor: 0.5,
            },
            NestedLinearLoadCombinationTermV1 {
                reference_id: "LC_AXIAL".to_owned(),
                reference_kind: LinearLoadCombinationReferenceKindV1::LoadPattern,
                factor: 0.25,
            },
        ];
        validate_nested_linear_load_combination_add_request(0, "COMBO_NESTED", &terms)
            .expect("valid nested combination request");

        let model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [{
                "id": "COMBO_BASE",
                "index": 0,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            }]
        });
        let mut added = model.clone();
        assert_eq!(
            append_nested_linear_load_combination(&mut added, "COMBO_NESTED", &terms)
                .expect("append nested load combination"),
            1
        );
        assert_eq!(
            added["load_combinations"][1],
            json!({
                "id": "COMBO_NESTED",
                "index": 1,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                ],
                "source_id": null,
                "extensions": {}
            })
        );
        assert_eq!(
            added["load_combinations"][1]["terms"],
            nested_linear_load_combination_terms_value(&terms)
        );

        let direct_only = [
            NestedLinearLoadCombinationTermV1 {
                reference_id: "LC_WEAK".to_owned(),
                reference_kind: LinearLoadCombinationReferenceKindV1::LoadPattern,
                factor: 1.0,
            },
            NestedLinearLoadCombinationTermV1 {
                reference_id: "LC_STRONG".to_owned(),
                reference_kind: LinearLoadCombinationReferenceKindV1::LoadPattern,
                factor: 1.0,
            },
        ];
        assert_eq!(
            validate_nested_linear_load_combination_add_request(
                0,
                "COMBO_DIRECT_ONLY",
                &direct_only,
            )
            .expect_err("nested author requires a combination reference")
            .code,
            "workbench_model_add_nested_linear_load_combination_reference_required"
        );
        let mut missing = model;
        let mut missing_terms = terms;
        missing_terms[0].reference_id = "COMBO_MISSING".to_owned();
        assert_eq!(
            append_nested_linear_load_combination(&mut missing, "COMBO_NESTED", &missing_terms,)
                .expect_err("missing nested combination")
                .code,
            "workbench_model_add_nested_linear_load_combination_combination_missing"
        );
    }

    #[test]
    fn linear_load_combination_delete_requires_terminal_neutral_unreferenced_direct_row() {
        validate_linear_load_combination_delete_request(0, "COMBO_B")
            .expect("valid linear-load-combination deletion request");
        assert!(validate_linear_load_combination_delete_request(0, "").is_err());

        let combination = |id: &str, index: usize| {
            json!({
                "id": id,
                "index": index,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            })
        };
        let model = json!({
            "load_patterns": [
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [combination("COMBO_A", 0), combination("COMBO_B", 1)],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_linear_load_combination(&mut deleted, "COMBO_B")
            .expect("delete terminal neutral linear combination");
        assert_eq!(removed.load_combination_index, 1);
        assert_eq!(removed.terms, model["load_combinations"][1]["terms"]);
        assert_eq!(
            removed.profile,
            LinearLoadCombinationDeletionProfileV1::ExactTwoV1
        );
        assert_eq!(
            deleted["load_combinations"],
            json!([combination("COMBO_A", 0)])
        );

        assert_eq!(
            remove_linear_load_combination(&mut model.clone(), "COMBO_A")
                .expect_err("nonterminal combination")
                .code,
            "workbench_model_delete_linear_load_combination_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["load_combinations"][1]["source_id"] = json!("mgt:COMBO_B");
        assert_eq!(
            remove_linear_load_combination(&mut source_owned, "COMBO_B")
                .expect_err("source-owned combination")
                .code,
            "workbench_model_delete_linear_load_combination_source_owned"
        );
        let mut extended = model.clone();
        extended["load_combinations"][1]["extensions"] = json!({"owner": "external"});
        assert_eq!(
            remove_linear_load_combination(&mut extended, "COMBO_B")
                .expect_err("extended combination")
                .code,
            "workbench_model_delete_linear_load_combination_extensions_unsupported"
        );
        let mut unsupported_reference = model.clone();
        unsupported_reference["load_combinations"][1]["terms"][1]["ref_kind"] = json!("load_case");
        assert_eq!(
            remove_linear_load_combination(&mut unsupported_reference, "COMBO_B")
                .expect_err("unsupported direct reference kind")
                .code,
            "workbench_model_delete_linear_load_combination_nested_unsupported"
        );
        let mut referenced = model.clone();
        referenced["load_combinations"][0]["terms"][0]["ref_kind"] = json!("load_combination");
        referenced["load_combinations"][0]["terms"][0]["ref_id"] = json!("COMBO_B");
        assert_eq!(
            remove_linear_load_combination(&mut referenced, "COMBO_B")
                .expect_err("combination reference")
                .code,
            "workbench_model_delete_linear_load_combination_referenced_by_combination"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "COMBO_B"}]);
        assert_eq!(
            remove_linear_load_combination(&mut feature_owned, "COMBO_B")
                .expect_err("unsupported-feature ownership")
                .code,
            "workbench_model_delete_linear_load_combination_unsupported_feature_owned"
        );
        let mut roundtrip_owned = model;
        roundtrip_owned["roundtrip_map"] = json!([{"model_ir_entity_id": "COMBO_B"}]);
        assert_eq!(
            remove_linear_load_combination(&mut roundtrip_owned, "COMBO_B")
                .expect_err("round-trip ownership")
                .code,
            "workbench_model_delete_linear_load_combination_roundtrip_owned"
        );
    }

    #[test]
    fn linear_load_combination_delete_accepts_three_pattern_direct_row() {
        let mut model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [{
                "id": "COMBO_DIRECT",
                "index": 0,
                "combination_type": "linear",
                "terms": [
                    {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25},
                    {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                ],
                "source_id": null,
                "extensions": {}
            }],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let removed = remove_linear_load_combination(&mut model, "COMBO_DIRECT")
            .expect("delete terminal three-pattern direct combination");
        assert_eq!(
            removed.profile,
            LinearLoadCombinationDeletionProfileV1::DirectV2
        );
        assert_eq!(removed.terms.as_array().map(Vec::len), Some(3));
        assert_eq!(model["load_combinations"], json!([]));
    }

    #[test]
    fn linear_load_combination_delete_accepts_bounded_nested_root() {
        let mut model = json!({
            "load_patterns": [
                {"id": "LC_AXIAL", "analysis_type": "linear_static"},
                {"id": "LC_WEAK", "analysis_type": "linear_static"},
                {"id": "LC_STRONG", "analysis_type": "linear_static"}
            ],
            "load_combinations": [
                {
                    "id": "COMBO_BASE",
                    "index": 0,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 1.2},
                        {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.5}
                    ],
                    "source_id": null,
                    "extensions": {}
                },
                {
                    "id": "COMBO_NESTED",
                    "index": 1,
                    "combination_type": "linear",
                    "terms": [
                        {"ref_id": "COMBO_BASE", "ref_kind": "load_combination", "factor": 0.5},
                        {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
                    ],
                    "source_id": null,
                    "extensions": {}
                }
            ],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let removed = remove_linear_load_combination(&mut model, "COMBO_NESTED")
            .expect("delete terminal bounded nested combination");
        assert_eq!(
            removed.profile,
            LinearLoadCombinationDeletionProfileV1::NestedV3
        );
        let expansion = removed.expansion.expect("nested deletion expansion");
        assert_eq!(expansion.max_depth, 2);
        assert_eq!(expansion.expanded_term_count, 3);
        assert_eq!(
            expansion.expanded_pattern_terms,
            json!([
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": 0.6},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": -0.25},
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 0.25}
            ])
        );
        assert_eq!(model["load_combinations"].as_array().map(Vec::len), Some(1));
        assert_eq!(model["load_combinations"][0]["id"], "COMBO_BASE");
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn linear_load_pattern_delete_requires_terminal_neutral_unreferenced_single_load_pattern() {
        validate_linear_load_pattern_delete_request(0, "LC_CUSTOM")
            .expect("valid linear-load-pattern deletion request");
        assert_eq!(
            validate_linear_load_pattern_delete_request(0, "")
                .expect_err("empty pattern identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let model = json!({
            "load_patterns": [
                {
                    "id": "LC_WEAK",
                    "index": 0,
                    "analysis_type": "linear_static",
                    "self_weight": [0, 0, 0],
                    "nodal_loads": [{
                        "id": "L_WEAK_N2",
                        "index": 0,
                        "node_id": "N2",
                        "components_si": {"FX": 0, "FY": -10000, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0},
                        "source_id": "source:L_WEAK_N2"
                    }],
                    "source_id": "source:LC_WEAK"
                },
                {
                    "id": "LC_CUSTOM",
                    "index": 1,
                    "analysis_type": "linear_static",
                    "self_weight": [0, 0, 0],
                    "nodal_loads": [{
                        "id": "L_CUSTOM_N2",
                        "index": 0,
                        "node_id": "N2",
                        "components_si": {"FX": 2500, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0},
                        "source_id": null
                    }],
                    "source_id": null
                }
            ],
            "load_combinations": [],
            "construction_stages": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_linear_load_pattern(&mut deleted, "LC_CUSTOM")
            .expect("delete terminal neutral load pattern");
        assert_eq!(removed.load_pattern_index, 1);
        assert_eq!(removed.nodal_load_id, "L_CUSTOM_N2");
        assert_eq!(removed.node_id, "N2");
        assert_eq!(
            deleted["load_patterns"]
                .as_array()
                .expect("load patterns")
                .len(),
            1
        );

        let mut nonterminal = model.clone();
        assert_eq!(
            remove_linear_load_pattern(&mut nonterminal, "LC_WEAK")
                .expect_err("nonterminal pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["load_patterns"][1]["source_id"] = json!("source:LC_CUSTOM");
        assert_eq!(
            remove_linear_load_pattern(&mut source_owned, "LC_CUSTOM")
                .expect_err("source-owned pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_source_owned"
        );
        let mut self_weight = model.clone();
        self_weight["load_patterns"][1]["self_weight"] = json!([0, -9.81, 0]);
        assert_eq!(
            remove_linear_load_pattern(&mut self_weight, "LC_CUSTOM")
                .expect_err("self-weight pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_self_weight_unsupported"
        );
        let mut multiple = model.clone();
        multiple["load_patterns"][1]["nodal_loads"]
            .as_array_mut()
            .expect("nodal loads")
            .push(json!({
                "id": "L_CUSTOM_N3",
                "index": 1,
                "node_id": "N3",
                "components_si": {"FX": 1, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0},
                "source_id": null
            }));
        assert_eq!(
            remove_linear_load_pattern(&mut multiple, "LC_CUSTOM")
                .expect_err("multiple nested loads")
                .code,
            "workbench_model_delete_linear_load_pattern_single_load_required"
        );
        let mut load_source_owned = model.clone();
        load_source_owned["load_patterns"][1]["nodal_loads"][0]["source_id"] =
            json!("source:L_CUSTOM_N2");
        assert_eq!(
            remove_linear_load_pattern(&mut load_source_owned, "LC_CUSTOM")
                .expect_err("source-owned nested load")
                .code,
            "workbench_model_delete_linear_load_pattern_load_source_owned"
        );
        let mut zero = model.clone();
        zero["load_patterns"][1]["nodal_loads"][0]["components_si"] =
            json!({"FX": 0, "FY": 0, "FZ": 0, "MX": 0, "MY": 0, "MZ": 0});
        assert_eq!(
            remove_linear_load_pattern(&mut zero, "LC_CUSTOM")
                .expect_err("zero nested load")
                .code,
            "workbench_model_delete_linear_load_pattern_zero_components"
        );
        let mut combined = model.clone();
        combined["load_combinations"] = json!([{
            "terms": [{"ref_id": "LC_CUSTOM", "ref_kind": "load_pattern", "factor": 1}]
        }]);
        assert_eq!(
            remove_linear_load_pattern(&mut combined, "LC_CUSTOM")
                .expect_err("combined pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_referenced_by_combination"
        );
        let mut staged = model.clone();
        staged["construction_stages"] = json!([{"load_pattern_ids": ["LC_CUSTOM"]}]);
        assert_eq!(
            remove_linear_load_pattern(&mut staged, "LC_CUSTOM")
                .expect_err("staged pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_referenced_by_stage"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "L_CUSTOM_N2"}]);
        assert_eq!(
            remove_linear_load_pattern(&mut feature_owned, "LC_CUSTOM")
                .expect_err("unsupported-feature-owned nested load")
                .code,
            "workbench_model_delete_linear_load_pattern_unsupported_feature_owned"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "LC_CUSTOM"}]);
        assert_eq!(
            remove_linear_load_pattern(&mut mapped, "LC_CUSTOM")
                .expect_err("round-trip-owned pattern")
                .code,
            "workbench_model_delete_linear_load_pattern_roundtrip_owned"
        );
        let mut minimum = deleted;
        assert_eq!(
            remove_linear_load_pattern(&mut minimum, "LC_WEAK")
                .expect_err("minimum retained model")
                .code,
            "workbench_model_delete_linear_load_pattern_minimum_model"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn linear_material_delete_requires_terminal_neutral_unreferenced_v1_material() {
        validate_linear_material_delete_request(0, "M2")
            .expect("valid linear-material deletion request");
        assert_eq!(
            validate_linear_material_delete_request(0, "")
                .expect_err("empty material identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let model = json!({
            "materials": [
                {
                    "id": "M1",
                    "index": 0,
                    "law_id": "linear_elastic_isotropic",
                    "parameter_set_version": "1",
                    "parameters": {
                        "elastic_modulus_pa": 200_000_000_000.0,
                        "poisson_ratio": 0.3,
                        "density_kg_m3": 7850.0
                    },
                    "state_schema": {
                        "stateful": false,
                        "state_update_epoch": "none",
                        "supports_trial_commit_rollback": true
                    },
                    "source_id": "source:M1"
                },
                {
                    "id": "M2",
                    "index": 1,
                    "law_id": "linear_elastic_isotropic",
                    "parameter_set_version": "1",
                    "parameters": {
                        "elastic_modulus_pa": 70_000_000_000.0,
                        "poisson_ratio": 0.33,
                        "density_kg_m3": 2700.0
                    },
                    "state_schema": {
                        "stateful": false,
                        "state_update_epoch": "none",
                        "supports_trial_commit_rollback": true
                    },
                    "source_id": null
                }
            ],
            "sections": [],
            "elements": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed = remove_linear_material(&mut deleted, "M2")
            .expect("delete terminal neutral linear material");
        assert_eq!(removed.material_index, 1);
        assert_eq!(
            removed.parameters_si["elastic_modulus_pa"],
            70_000_000_000.0
        );
        assert_eq!(removed.state_schema["state_update_epoch"], "none");
        assert_eq!(deleted["materials"].as_array().expect("materials").len(), 1);

        let mut missing = model.clone();
        assert_eq!(
            remove_linear_material(&mut missing, "M404")
                .expect_err("missing material")
                .code,
            "workbench_model_delete_linear_material_missing"
        );
        let mut nonterminal = model.clone();
        nonterminal["materials"]
            .as_array_mut()
            .expect("materials")
            .push(json!({
                "id": "M3",
                "index": 2,
                "law_id": "linear_elastic_isotropic",
                "parameter_set_version": "1",
                "parameters": {"elastic_modulus_pa": 1, "poisson_ratio": 0, "density_kg_m3": 0},
                "state_schema": {"stateful": false, "state_update_epoch": "none", "supports_trial_commit_rollback": true},
                "source_id": null
            }));
        assert_eq!(
            remove_linear_material(&mut nonterminal, "M2")
                .expect_err("nonterminal material")
                .code,
            "workbench_model_delete_linear_material_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["materials"][1]["source_id"] = json!("source:M2");
        assert_eq!(
            remove_linear_material(&mut source_owned, "M2")
                .expect_err("source-owned material")
                .code,
            "workbench_model_delete_linear_material_source_owned"
        );
        let mut index_drift = model.clone();
        index_drift["materials"][1]["index"] = json!(0);
        assert_eq!(
            remove_linear_material(&mut index_drift, "M2")
                .expect_err("material index drift")
                .code,
            "workbench_model_delete_linear_material_index_mismatch"
        );
        let mut law_drift = model.clone();
        law_drift["materials"][1]["law_id"] = json!("bilinear_uniaxial");
        assert_eq!(
            remove_linear_material(&mut law_drift, "M2")
                .expect_err("material law drift")
                .code,
            "workbench_model_delete_linear_material_law_unsupported"
        );
        let mut version_drift = model.clone();
        version_drift["materials"][1]["parameter_set_version"] = json!("2");
        assert_eq!(
            remove_linear_material(&mut version_drift, "M2")
                .expect_err("material parameter-set drift")
                .code,
            "workbench_model_delete_linear_material_version_unsupported"
        );
        let mut parameter_drift = model.clone();
        parameter_drift["materials"][1]["parameters"]["poisson_ratio"] = json!(0.5);
        assert_eq!(
            remove_linear_material(&mut parameter_drift, "M2")
                .expect_err("material physical-parameter drift")
                .code,
            "workbench_model_delete_linear_material_parameters_invalid"
        );
        let mut malformed_state = model.clone();
        malformed_state["materials"][1]["state_schema"]["stateful"] = json!(true);
        assert_eq!(
            remove_linear_material(&mut malformed_state, "M2")
                .expect_err("stateful material")
                .code,
            "workbench_model_delete_linear_material_state_schema_unsupported"
        );
        let mut element_referenced = model.clone();
        element_referenced["elements"] = json!([{"material_id": "M2"}]);
        assert_eq!(
            remove_linear_material(&mut element_referenced, "M2")
                .expect_err("element-referenced material")
                .code,
            "workbench_model_delete_linear_material_referenced_by_element"
        );
        let mut section_referenced = model.clone();
        section_referenced["sections"] = json!([{"steel_material_id": "M2"}]);
        assert_eq!(
            remove_linear_material(&mut section_referenced, "M2")
                .expect_err("section-referenced material")
                .code,
            "workbench_model_delete_linear_material_referenced_by_section"
        );
        let mut concrete_section_referenced = model.clone();
        concrete_section_referenced["sections"] = json!([{"concrete_material_id": "M2"}]);
        assert_eq!(
            remove_linear_material(&mut concrete_section_referenced, "M2")
                .expect_err("concrete-section-referenced material")
                .code,
            "workbench_model_delete_linear_material_referenced_by_section"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "M2"}]);
        assert_eq!(
            remove_linear_material(&mut feature_owned, "M2")
                .expect_err("unsupported-feature-owned material")
                .code,
            "workbench_model_delete_linear_material_unsupported_feature_owned"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "M2"}]);
        assert_eq!(
            remove_linear_material(&mut mapped, "M2")
                .expect_err("round-trip-owned material")
                .code,
            "workbench_model_delete_linear_material_roundtrip_owned"
        );
        assert_eq!(
            remove_linear_material(&mut deleted, "M1")
                .expect_err("minimum retained model")
                .code,
            "workbench_model_delete_linear_material_minimum_model"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn frame_section_delete_requires_terminal_neutral_unreferenced_v1_section() {
        validate_frame_section_delete_request(0, "S2")
            .expect("valid frame-section deletion request");
        assert_eq!(
            validate_frame_section_delete_request(0, "")
                .expect_err("empty section identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let frame_parameters = json!({
            "area_m2": 0.01,
            "iy_m4": 0.00004,
            "iz_m4": 0.000_025,
            "torsional_constant_m4": 0.000_005,
            "shear_area_y_m2": 0.008,
            "shear_area_z_m2": 0.008
        });
        let model = json!({
            "sections": [
                {
                    "id": "S1",
                    "index": 0,
                    "family_id": "frame_3d",
                    "parameter_set_version": "1",
                    "parameters": frame_parameters,
                    "source_id": "source:S1"
                },
                {
                    "id": "S2",
                    "index": 1,
                    "family_id": "frame_3d",
                    "parameter_set_version": "1",
                    "parameters": frame_parameters,
                    "source_id": null
                }
            ],
            "elements": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed =
            remove_frame_section(&mut deleted, "S2").expect("delete terminal frame section");
        assert_eq!(removed.section_index, 1);
        assert_eq!(removed.parameters_si["area_m2"], 0.01);
        assert_eq!(deleted["sections"].as_array().expect("sections").len(), 1);

        let mut missing = model.clone();
        assert_eq!(
            remove_frame_section(&mut missing, "S404")
                .expect_err("missing frame section")
                .code,
            "workbench_model_delete_frame_section_missing"
        );
        let mut nonterminal = model.clone();
        nonterminal["sections"]
            .as_array_mut()
            .expect("sections")
            .push(json!({
                "id": "S3",
                "index": 2,
                "family_id": "frame_3d",
                "parameter_set_version": "1",
                "parameters": frame_parameters,
                "source_id": null
            }));
        assert_eq!(
            remove_frame_section(&mut nonterminal, "S2")
                .expect_err("nonterminal frame section")
                .code,
            "workbench_model_delete_frame_section_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["sections"][1]["source_id"] = json!("source:S2");
        assert_eq!(
            remove_frame_section(&mut source_owned, "S2")
                .expect_err("source-owned frame section")
                .code,
            "workbench_model_delete_frame_section_source_owned"
        );
        let mut index_drift = model.clone();
        index_drift["sections"][1]["index"] = json!(0);
        assert_eq!(
            remove_frame_section(&mut index_drift, "S2")
                .expect_err("frame-section index drift")
                .code,
            "workbench_model_delete_frame_section_index_mismatch"
        );
        let mut family_drift = model.clone();
        family_drift["sections"][1]["family_id"] = json!("truss_3d");
        assert_eq!(
            remove_frame_section(&mut family_drift, "S2")
                .expect_err("frame-section family drift")
                .code,
            "workbench_model_delete_frame_section_family_unsupported"
        );
        let mut version_drift = model.clone();
        version_drift["sections"][1]["parameter_set_version"] = json!("2");
        assert_eq!(
            remove_frame_section(&mut version_drift, "S2")
                .expect_err("frame-section parameter-set drift")
                .code,
            "workbench_model_delete_frame_section_version_unsupported"
        );
        let mut parameter_drift = model.clone();
        parameter_drift["sections"][1]["parameters"]["area_m2"] = json!(0);
        assert_eq!(
            remove_frame_section(&mut parameter_drift, "S2")
                .expect_err("frame-section parameter drift")
                .code,
            "workbench_model_delete_frame_section_parameters_invalid"
        );
        let mut element_referenced = model.clone();
        element_referenced["elements"] = json!([{"section_id": "S2"}]);
        assert_eq!(
            remove_frame_section(&mut element_referenced, "S2")
                .expect_err("element-referenced frame section")
                .code,
            "workbench_model_delete_frame_section_referenced_by_element"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "S2"}]);
        assert_eq!(
            remove_frame_section(&mut feature_owned, "S2")
                .expect_err("unsupported-feature-owned frame section")
                .code,
            "workbench_model_delete_frame_section_unsupported_feature_owned"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "S2"}]);
        assert_eq!(
            remove_frame_section(&mut mapped, "S2")
                .expect_err("round-trip-owned frame section")
                .code,
            "workbench_model_delete_frame_section_roundtrip_owned"
        );
        assert_eq!(
            remove_frame_section(&mut deleted, "S1")
                .expect_err("minimum retained model")
                .code,
            "workbench_model_delete_frame_section_minimum_model"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn truss_section_delete_requires_terminal_neutral_unreferenced_v1_section() {
        validate_truss_section_delete_request(0, "T2")
            .expect("valid truss-section deletion request");
        assert_eq!(
            validate_truss_section_delete_request(0, "")
                .expect_err("empty section identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        let model = json!({
            "sections": [
                {
                    "id": "S1",
                    "index": 0,
                    "family_id": "frame_3d",
                    "parameter_set_version": "1",
                    "parameters": {
                        "area_m2": 0.01,
                        "iy_m4": 0.000_04,
                        "iz_m4": 0.000_025,
                        "torsional_constant_m4": 0.000_005,
                        "shear_area_y_m2": 0.008,
                        "shear_area_z_m2": 0.008
                    },
                    "source_id": "source:S1"
                },
                {
                    "id": "T1",
                    "index": 1,
                    "family_id": "truss_3d",
                    "parameter_set_version": "1",
                    "parameters": {"area_m2": 0.005},
                    "source_id": null
                },
                {
                    "id": "T2",
                    "index": 2,
                    "family_id": "truss_3d",
                    "parameter_set_version": "1",
                    "parameters": {"area_m2": 0.0025},
                    "source_id": null
                }
            ],
            "elements": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed =
            remove_truss_section(&mut deleted, "T2").expect("delete terminal truss section");
        assert_eq!(removed.section_index, 2);
        assert_eq!(removed.parameters_si["area_m2"], 0.0025);
        assert_eq!(deleted["sections"].as_array().expect("sections").len(), 2);

        let mut missing = model.clone();
        assert_eq!(
            remove_truss_section(&mut missing, "T404")
                .expect_err("missing truss section")
                .code,
            "workbench_model_delete_truss_section_missing"
        );
        let mut nonterminal = model.clone();
        nonterminal["sections"]
            .as_array_mut()
            .expect("sections")
            .push(json!({
                "id": "T3",
                "index": 3,
                "family_id": "truss_3d",
                "parameter_set_version": "1",
                "parameters": {"area_m2": 0.001},
                "source_id": null
            }));
        assert_eq!(
            remove_truss_section(&mut nonterminal, "T2")
                .expect_err("nonterminal truss section")
                .code,
            "workbench_model_delete_truss_section_not_terminal"
        );
        let mut source_owned = model.clone();
        source_owned["sections"][2]["source_id"] = json!("source:T2");
        assert_eq!(
            remove_truss_section(&mut source_owned, "T2")
                .expect_err("source-owned truss section")
                .code,
            "workbench_model_delete_truss_section_source_owned"
        );
        let mut index_drift = model.clone();
        index_drift["sections"][2]["index"] = json!(1);
        assert_eq!(
            remove_truss_section(&mut index_drift, "T2")
                .expect_err("truss-section index drift")
                .code,
            "workbench_model_delete_truss_section_index_mismatch"
        );
        let mut family_drift = model.clone();
        family_drift["sections"][2]["family_id"] = json!("frame_3d");
        assert_eq!(
            remove_truss_section(&mut family_drift, "T2")
                .expect_err("truss-section family drift")
                .code,
            "workbench_model_delete_truss_section_family_unsupported"
        );
        let mut version_drift = model.clone();
        version_drift["sections"][2]["parameter_set_version"] = json!("2");
        assert_eq!(
            remove_truss_section(&mut version_drift, "T2")
                .expect_err("truss-section parameter-set drift")
                .code,
            "workbench_model_delete_truss_section_version_unsupported"
        );
        let mut parameter_drift = model.clone();
        parameter_drift["sections"][2]["parameters"]["area_m2"] = json!(0);
        assert_eq!(
            remove_truss_section(&mut parameter_drift, "T2")
                .expect_err("truss-section parameter drift")
                .code,
            "workbench_model_delete_truss_section_parameters_invalid"
        );
        let mut element_referenced = model.clone();
        element_referenced["elements"] = json!([{"section_id": "T2"}]);
        assert_eq!(
            remove_truss_section(&mut element_referenced, "T2")
                .expect_err("element-referenced truss section")
                .code,
            "workbench_model_delete_truss_section_referenced_by_element"
        );
        let mut feature_owned = model.clone();
        feature_owned["unsupported_features"] = json!([{"source_entity_id": "T2"}]);
        assert_eq!(
            remove_truss_section(&mut feature_owned, "T2")
                .expect_err("unsupported-feature-owned truss section")
                .code,
            "workbench_model_delete_truss_section_unsupported_feature_owned"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{"model_ir_entity_id": "T2"}]);
        assert_eq!(
            remove_truss_section(&mut mapped, "T2")
                .expect_err("round-trip-owned truss section")
                .code,
            "workbench_model_delete_truss_section_roundtrip_owned"
        );
        assert_eq!(
            remove_truss_section(&mut deleted, "T1")
                .expect_err("minimum retained truss family")
                .code,
            "workbench_model_delete_truss_section_minimum_family"
        );
    }

    #[test]
    fn linear_material_add_requires_bounded_identity_and_closed_physical_ranges() {
        let material = LinearElasticMaterialParametersV1 {
            elastic_modulus_pa: 70_000_000_000.0,
            poisson_ratio: 0.33,
            density_kg_m3: 2_700.0,
        };
        validate_linear_material_add_request(0, "M2", material)
            .expect("valid linear-material addition request");
        assert_eq!(
            validate_linear_material_add_request(0, "", material)
                .expect_err("empty material identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        for (parameters, expected_code) in [
            (
                LinearElasticMaterialParametersV1 {
                    elastic_modulus_pa: 0.0,
                    ..material
                },
                "workbench_model_add_linear_material_elastic_modulus_invalid",
            ),
            (
                LinearElasticMaterialParametersV1 {
                    poisson_ratio: 0.5,
                    ..material
                },
                "workbench_model_add_linear_material_poisson_ratio_invalid",
            ),
            (
                LinearElasticMaterialParametersV1 {
                    density_kg_m3: -0.01,
                    ..material
                },
                "workbench_model_add_linear_material_density_invalid",
            ),
            (
                LinearElasticMaterialParametersV1 {
                    elastic_modulus_pa: f64::NAN,
                    ..material
                },
                "workbench_model_add_linear_material_elastic_modulus_invalid",
            ),
        ] {
            assert_eq!(
                validate_linear_material_add_request(0, "M2", parameters)
                    .expect_err("invalid material parameters")
                    .code,
                expected_code
            );
        }
    }

    #[test]
    fn frame_section_add_requires_bounded_identity_and_positive_finite_parameters() {
        let section = FrameSectionParametersV1 {
            area_m2: 0.01,
            iy_m4: 0.000_04,
            iz_m4: 0.000_025,
            torsional_constant_m4: 0.000_005,
            shear_area_y_m2: 0.008,
            shear_area_z_m2: 0.008,
        };
        validate_frame_section_add_request(0, "S2", section)
            .expect("valid frame-section addition request");
        assert_eq!(
            validate_frame_section_add_request(0, "", section)
                .expect_err("empty section identity")
                .code,
            "workbench_model_edit_entity_id_invalid"
        );
        for invalid_value in [0.0, -1.0, f64::INFINITY, f64::NAN] {
            assert_eq!(
                validate_frame_section_add_request(
                    0,
                    "S2",
                    FrameSectionParametersV1 {
                        shear_area_z_m2: invalid_value,
                        ..section
                    },
                )
                .expect_err("invalid frame-section parameter")
                .code,
                "workbench_model_add_frame_section_parameter_invalid"
            );
        }
    }

    #[test]
    fn truss_authoring_requests_require_bounded_identities_and_positive_finite_area() {
        validate_truss_section_add_request(0, "T1", TrussSectionParametersV1 { area_m2: 0.005 })
            .expect("valid truss-section addition request");
        for area_m2 in [0.0, -1.0, f64::INFINITY, f64::NAN] {
            assert_eq!(
                validate_truss_section_add_request(0, "T1", TrussSectionParametersV1 { area_m2 },)
                    .expect_err("invalid truss-section area")
                    .code,
                "workbench_model_add_truss_section_area_invalid"
            );
        }
        validate_truss3d_member_add_request(0, "N3", [2.0, 1.0, 0.0], "E2", "N2", "M1", "T1")
            .expect("valid truss-member addition request");
        assert_eq!(
            validate_truss3d_member_add_request(0, "N2", [2.0, 1.0, 0.0], "E2", "N2", "M1", "T1",)
                .expect_err("identical endpoint identities")
                .code,
            "workbench_model_add_truss3d_member_node_identity_invalid"
        );
        assert_eq!(
            validate_truss3d_member_add_request(
                0,
                "N3",
                [f64::NAN, 1.0, 0.0],
                "E2",
                "N2",
                "M1",
                "T1",
            )
            .expect_err("non-finite coordinate")
            .code,
            "workbench_model_add_truss3d_member_coordinate_invalid"
        );
    }

    #[test]
    fn truss_member_properties_require_linear_material_and_v1_truss_section() {
        let valid = json!({
            "materials": [{
                "id": "M1",
                "law_id": "linear_elastic_isotropic",
                "parameter_set_version": "1"
            }],
            "sections": [{
                "id": "T1",
                "family_id": "truss_3d",
                "parameter_set_version": "1"
            }]
        });
        validate_truss3d_member_properties(&valid, "M1", "T1")
            .expect("compatible truss properties");
        let mut nonlinear = valid.clone();
        nonlinear["materials"][0]["law_id"] = json!("bilinear_combined_hardening_steel");
        assert_eq!(
            validate_truss3d_member_properties(&nonlinear, "M1", "T1")
                .expect_err("nonlinear material")
                .code,
            "workbench_model_add_truss3d_member_material_unsupported"
        );
        let mut frame = valid.clone();
        frame["sections"][0]["family_id"] = json!("frame_3d");
        assert_eq!(
            validate_truss3d_member_properties(&frame, "M1", "T1")
                .expect_err("frame section")
                .code,
            "workbench_model_add_truss3d_member_section_unsupported"
        );
        let mut wrong_version = valid;
        wrong_version["sections"][0]["parameter_set_version"] = json!("2");
        assert_eq!(
            validate_truss3d_member_properties(&wrong_version, "M1", "T1")
                .expect_err("unsupported truss-section version")
                .code,
            "workbench_model_add_truss3d_member_section_unsupported"
        );
    }

    #[test]
    fn frame_leaf_delete_reuses_terminal_neutral_reference_guards() {
        validate_frame3d_leaf_member_delete_request(0, "E2", "N3")
            .expect("valid bounded frame delete request");
        assert_eq!(
            validate_frame3d_leaf_member_delete_request(0, "E2", "E2")
                .expect_err("identity collision")
                .code,
            "workbench_model_delete_frame3d_leaf_identity_collision"
        );
        let model = json!({
            "nodes": [
                {"id": "N1", "index": 0, "coordinates_m": [0, 0, 0], "source_id": "s:N1"},
                {"id": "N2", "index": 1, "coordinates_m": [2, 0, 0], "source_id": "s:N2"},
                {"id": "N3", "index": 2, "coordinates_m": [2, 1, 0], "source_id": null}
            ],
            "elements": [
                {"id": "E1", "index": 0, "node_ids": ["N1", "N2"], "source_id": "s:E1"},
                {
                    "id": "E2",
                    "index": 1,
                    "type": "frame_3d",
                    "formulation": "euler_bernoulli_3d",
                    "node_ids": ["N2", "N3"],
                    "material_id": "M1",
                    "section_id": "S1",
                    "local_axis_rotation_rad": 0.25,
                    "offsets": {
                        "i_global_m": [0, 0, 0],
                        "j_global_m": [0, 0, 0]
                    },
                    "releases": {"i": [], "j": ["RZ"]},
                    "source_id": null
                }
            ],
            "constraints": [],
            "load_patterns": [],
            "construction_stages": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed =
            remove_frame3d_leaf_member(&mut deleted, "E2", "N3").expect("delete neutral leaf");
        assert_eq!(removed.node_index, 2);
        assert_eq!(removed.element_index, 1);
        assert_eq!(
            removed.local_axis_rotation_rad.to_bits(),
            0.25_f64.to_bits()
        );
        assert_eq!(removed.releases, json!({"i": [], "j": ["RZ"]}));
        assert_eq!(deleted["nodes"].as_array().expect("nodes").len(), 2);
        assert_eq!(deleted["elements"].as_array().expect("elements").len(), 1);

        let mut constrained = model.clone();
        constrained["constraints"] = json!([{"id": "BC3", "node_id": "N3"}]);
        assert_eq!(
            remove_frame3d_leaf_member(&mut constrained, "E2", "N3")
                .expect_err("constraint reference")
                .code,
            "workbench_model_delete_frame3d_leaf_node_referenced_by_constraint"
        );
        let mut wrong_family = model;
        wrong_family["elements"][1]["type"] = json!("truss_3d");
        assert_eq!(
            remove_frame3d_leaf_member(&mut wrong_family, "E2", "N3")
                .expect_err("wrong element family")
                .code,
            "workbench_model_delete_frame3d_leaf_type_unsupported"
        );
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn truss_leaf_delete_requires_terminal_neutral_unreferenced_rows() {
        validate_truss3d_leaf_member_delete_request(0, "E2", "N3")
            .expect("valid bounded delete request");
        assert_eq!(
            validate_truss3d_leaf_member_delete_request(0, "E2", "E2")
                .expect_err("identity collision")
                .code,
            "workbench_model_delete_truss3d_leaf_identity_collision"
        );
        let model = json!({
            "nodes": [
                {"id": "N1", "index": 0, "coordinates_m": [0, 0, 0], "source_id": "s:N1"},
                {"id": "N2", "index": 1, "coordinates_m": [2, 0, 0], "source_id": "s:N2"},
                {"id": "N3", "index": 2, "coordinates_m": [2, 1, 0], "source_id": null}
            ],
            "elements": [
                {"id": "E1", "index": 0, "node_ids": ["N1", "N2"], "source_id": "s:E1"},
                {
                    "id": "E2",
                    "index": 1,
                    "type": "truss_3d",
                    "formulation": "linear_truss_3d",
                    "node_ids": ["N2", "N3"],
                    "material_id": "M1",
                    "section_id": "T1",
                    "offsets": {
                        "i_global_m": [0, 0, 0],
                        "j_global_m": [0, 0, 0]
                    },
                    "source_id": null
                }
            ],
            "constraints": [],
            "load_patterns": [],
            "construction_stages": [],
            "unsupported_features": [],
            "roundtrip_map": []
        });
        let mut deleted = model.clone();
        let removed =
            remove_truss3d_leaf_member(&mut deleted, "E2", "N3").expect("delete neutral leaf");
        assert_eq!(removed.node_index, 2);
        assert_eq!(removed.element_index, 1);
        assert_eq!(deleted["nodes"].as_array().expect("nodes").len(), 2);
        assert_eq!(deleted["elements"].as_array().expect("elements").len(), 1);

        let mut constrained = model.clone();
        constrained["constraints"] = json!([{"id": "BC3", "node_id": "N3"}]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut constrained, "E2", "N3")
                .expect_err("constraint reference")
                .code,
            "workbench_model_delete_truss3d_leaf_node_referenced_by_constraint"
        );
        let mut element_referenced = model.clone();
        element_referenced["elements"][0]["node_ids"] = json!(["N1", "N3"]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut element_referenced, "E2", "N3")
                .expect_err("other element reference")
                .code,
            "workbench_model_delete_truss3d_leaf_node_referenced_by_element"
        );
        let mut loaded = model.clone();
        loaded["load_patterns"] = json!([{
            "id": "LC1",
            "nodal_loads": [{"id": "L3", "node_id": "N3"}]
        }]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut loaded, "E2", "N3")
                .expect_err("nodal load reference")
                .code,
            "workbench_model_delete_truss3d_leaf_node_referenced_by_load"
        );
        let mut staged = model.clone();
        staged["construction_stages"] = json!([{
            "id": "STAGE1",
            "active_element_ids": ["E2"]
        }]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut staged, "E2", "N3")
                .expect_err("construction-stage reference")
                .code,
            "workbench_model_delete_truss3d_leaf_element_referenced_by_stage"
        );
        let mut unsupported = model.clone();
        unsupported["unsupported_features"] = json!([{
            "feature_id": "feature:E2",
            "source_entity_id": "E2"
        }]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut unsupported, "E2", "N3")
                .expect_err("unsupported-feature reference")
                .code,
            "workbench_model_delete_truss3d_leaf_unsupported_feature_owned"
        );
        let mut source_owned = model.clone();
        source_owned["nodes"][2]["source_id"] = json!("source:N3");
        assert_eq!(
            remove_truss3d_leaf_member(&mut source_owned, "E2", "N3")
                .expect_err("source-owned node")
                .code,
            "workbench_model_delete_truss3d_leaf_source_owned"
        );
        let mut wrong_family = model.clone();
        wrong_family["elements"][1]["type"] = json!("frame_3d");
        assert_eq!(
            remove_truss3d_leaf_member(&mut wrong_family, "E2", "N3")
                .expect_err("wrong element family")
                .code,
            "workbench_model_delete_truss3d_leaf_type_unsupported"
        );
        let mut mapped = model;
        mapped["roundtrip_map"] = json!([{
            "entity_kind": "element",
            "model_ir_entity_id": "E2"
        }]);
        assert_eq!(
            remove_truss3d_leaf_member(&mut mapped, "E2", "N3")
                .expect_err("round-trip ownership")
                .code,
            "workbench_model_delete_truss3d_leaf_roundtrip_owned"
        );
    }

    #[test]
    fn truss_edit_requests_require_bounded_ids_and_positive_finite_area() {
        validate_truss_section_edit_request(0, "T1", TrussSectionParametersV1 { area_m2: 0.0075 })
            .expect("valid truss-section edit request");
        for area_m2 in [0.0, -1.0, f64::INFINITY, f64::NAN] {
            assert_eq!(
                validate_truss_section_edit_request(0, "T1", TrussSectionParametersV1 { area_m2 },)
                    .expect_err("invalid truss-section edit area")
                    .code,
                "workbench_model_edit_truss_section_area_invalid"
            );
        }
        validate_truss_element_properties_edit_request(0, "E2", "M2", "T2")
            .expect("valid truss property edit request");
        assert!(validate_truss_element_properties_edit_request(0, "", "M2", "T2").is_err());
    }

    #[test]
    fn truss_property_edit_references_require_linear_material_and_v1_truss_section() {
        let valid = json!({
            "materials": [{
                "id": "M2",
                "law_id": "linear_elastic_isotropic",
                "parameter_set_version": "1"
            }],
            "sections": [{
                "id": "T2",
                "family_id": "truss_3d",
                "parameter_set_version": "1"
            }]
        });
        validate_truss_element_property_references(&valid, "M2", "T2")
            .expect("compatible truss edit properties");
        let mut nonlinear = valid.clone();
        nonlinear["materials"][0]["law_id"] = json!("bilinear_combined_hardening_steel");
        assert_eq!(
            validate_truss_element_property_references(&nonlinear, "M2", "T2")
                .expect_err("nonlinear material")
                .code,
            "workbench_model_edit_truss_element_material_unsupported"
        );
        let mut frame = valid.clone();
        frame["sections"][0]["family_id"] = json!("frame_3d");
        assert_eq!(
            validate_truss_element_property_references(&frame, "M2", "T2")
                .expect_err("frame section")
                .code,
            "workbench_model_edit_truss_element_section_unsupported"
        );
        let mut wrong_version = valid;
        wrong_version["sections"][0]["parameter_set_version"] = json!("2");
        assert_eq!(
            validate_truss_element_property_references(&wrong_version, "M2", "T2")
                .expect_err("unsupported truss-section version")
                .code,
            "workbench_model_edit_truss_element_section_unsupported"
        );
    }
}
