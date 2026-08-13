use std::path::Path;

use serde_json::{json, Value};
use structural_cli::validate_model_bytes;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, parse_model_ir_v2};
use structural_contracts::product_ir::sha256_identity;

use super::{
    artifact_entry, canonical_self_hashed, input_error, publish_new_directory,
    read_bounded_regular_file, WorkbenchError, MAX_MODEL_BYTES,
};

const EDIT_SCHEMA_V1: &str = "structural-native-model-edit-receipt.v1";
const NODE_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-node.v1";
const NODAL_LOAD_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-nodal-load.v1";
const CONSTRAINT_VALUE_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-constraint-value.v1";
const LINEAR_MATERIAL_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-linear-material.v1";
const FRAME_SECTION_EDIT_EXTENSION_KEY: &str = "structural-native:model-edit-frame-section.v1";
const FRAME_ELEMENT_ORIENTATION_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-frame-element-orientation.v1";
const ELEMENT_CONNECTIVITY_EDIT_EXTENSION_KEY: &str =
    "structural-native:model-edit-element-connectivity.v1";
const FRAME3D_MEMBER_ADD_EXTENSION_KEY: &str = "structural-native:model-add-frame3d-member.v1";
const UPSTREAM_PROVENANCE_KEY: &str = "structural-native:upstream-provenance";
const NODE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_node_coordinate_edit_not_visual_dragging_property_constraint_load_or_solver_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_nodal_load_component_edit_not_load_creation_deletion_combination_property_constraint_solver_editing_engineering_acceptance_or_c6";
const CONSTRAINT_VALUE_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_restrained_dof_prescribed_value_edit_not_restraint_node_or_topology_creation_deletion_solver_editing_engineering_acceptance_or_c6";
const LINEAR_MATERIAL_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_linear_elastic_isotropic_material_parameter_edit_not_material_creation_deletion_law_version_state_or_solver_editing_engineering_acceptance_or_c6";
const FRAME_SECTION_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_frame3d_section_parameter_edit_not_section_creation_deletion_family_version_topology_or_solver_editing_engineering_acceptance_or_c6";
const FRAME_ELEMENT_ORIENTATION_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_frame3d_element_local_axis_rotation_edit_not_element_creation_deletion_connectivity_formulation_offset_release_topology_or_solver_editing_engineering_acceptance_or_c6";
const ELEMENT_CONNECTIVITY_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_existing_modelir_two_node_element_connectivity_edit_not_element_or_node_creation_deletion_identity_type_formulation_property_offset_release_or_solver_editing_engineering_acceptance_or_c6";
const FRAME3D_MEMBER_ADD_CLAIM_BOUNDARY: &str = "bounded_cpp_revalidated_modelir_linear_frame3d_node_and_member_addition_with_existing_material_section_not_general_topology_property_load_constraint_solver_visual_editing_engineering_acceptance_or_c6";
const NODAL_LOAD_COMPONENT_KEYS: [&str; 6] = ["FX", "FY", "FZ", "MX", "MY", "MZ"];
const DOF_KEYS: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];

/// Complete deterministic artifact pair produced by one bounded node-coordinate edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelNodeEditOutcomeV1 {
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

/// Complete deterministic artifact pair produced by one bounded frame-section edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameSectionEditOutcomeV1 {
    pub model_ir_json: String,
    pub receipt_json: String,
}

/// Complete deterministic artifact pair produced by one bounded frame-element orientation edit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelFrameElementOrientationEditOutcomeV1 {
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
    use serde_json::json;

    use super::{
        constraint_value_unit, mark_roundtrip_entity_approximated,
        mark_roundtrip_node_approximated, normalized_number_bits,
        validate_constraint_value_edit_request, validate_edit_request,
        validate_element_connectivity_edit_request, validate_frame3d_member_add_request,
        validate_frame_element_orientation_edit_request, validate_frame_section_edit_request,
        validate_linear_material_edit_request, validate_nodal_load_edit_request,
        FrameSectionParametersV1, LinearElasticMaterialParametersV1, MAX_MODEL_BYTES,
    };

    #[test]
    fn signed_zero_is_the_same_canonical_coordinate() {
        assert_eq!(normalized_number_bits(0.0), normalized_number_bits(-0.0));
        assert_ne!(normalized_number_bits(1.0), normalized_number_bits(-1.0));
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
}
