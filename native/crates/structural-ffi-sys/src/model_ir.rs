//! Raw `ModelIR` v2 descriptors introduced by C ABI v1.1.

use core::ffi::c_char;

use crate::{SaErrorBufferV1, SaStatusCodeV1};

pub const SA_ABI_V1_1: u32 = 0x0001_0001;

pub const SA_CAPABILITY_MODEL_IR_V2_TYPED: u64 = 1 << 1;
pub const SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT: u64 = 1 << 2;

pub type SaModelIrCapabilityProfileV1 = u32;
pub const SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D: u32 = 1;
pub const SA_MODEL_IR_PROFILE_GENERAL: u32 = SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D;
pub const SA_MODEL_IR_PROFILE_BOUNDED_PLANAR_FRAME_ALPHA: u32 = 2;
pub const SA_MODEL_IR_PROFILE_PLANAR_FRAME_VERIFIED_ALPHA_V1: u32 = 3;
pub const SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL: u32 = 4;

pub type SaSourceFormatV1 = u32;
pub const SA_SOURCE_FORMAT_NEUTRAL_JSON: u32 = 1;
pub const SA_SOURCE_FORMAT_MIDAS_MGT: u32 = 2;
pub const SA_SOURCE_FORMAT_IFC: u32 = 3;
pub const SA_SOURCE_FORMAT_OPENSEES: u32 = 4;
pub const SA_SOURCE_FORMAT_ETABS_E2K: u32 = 5;
pub const SA_SOURCE_FORMAT_DXF: u32 = 6;
pub const SA_SOURCE_FORMAT_GENERATED: u32 = 7;

pub type SaLengthUnitV1 = u32;
pub const SA_LENGTH_UNIT_M: u32 = 1;
pub const SA_LENGTH_UNIT_MM: u32 = 2;
pub const SA_LENGTH_UNIT_CM: u32 = 3;
pub const SA_LENGTH_UNIT_FT: u32 = 4;
pub const SA_LENGTH_UNIT_IN: u32 = 5;

pub type SaForceUnitV1 = u32;
pub const SA_FORCE_UNIT_N: u32 = 1;
pub const SA_FORCE_UNIT_KN: u32 = 2;
pub const SA_FORCE_UNIT_MN: u32 = 3;
pub const SA_FORCE_UNIT_LBF: u32 = 4;
pub const SA_FORCE_UNIT_KIP: u32 = 5;

pub type SaMassUnitV1 = u32;
pub const SA_MASS_UNIT_KG: u32 = 1;
pub const SA_MASS_UNIT_TONNE: u32 = 2;
pub const SA_MASS_UNIT_SLUG: u32 = 3;

pub type SaTimeUnitV1 = u32;
pub const SA_TIME_UNIT_S: u32 = 1;

pub type SaRotationUnitV1 = u32;
pub const SA_ROTATION_UNIT_RAD: u32 = 1;
pub const SA_ROTATION_UNIT_DEG: u32 = 2;

pub type SaDofV1 = u32;
pub const SA_DOF_UX: u32 = 1;
pub const SA_DOF_UY: u32 = 2;
pub const SA_DOF_UZ: u32 = 3;
pub const SA_DOF_RX: u32 = 4;
pub const SA_DOF_RY: u32 = 5;
pub const SA_DOF_RZ: u32 = 6;

pub type SaMaterialLawV1 = u32;
pub const SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC: u32 = 1;
pub const SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL: u32 = 2;
pub const SA_MATERIAL_ASYMMETRIC_CONCRETE_DAMAGE: u32 = 3;

pub type SaMaterialStateEpochV1 = u32;
pub const SA_MATERIAL_STATE_EPOCH_NONE: u32 = 1;
pub const SA_MATERIAL_STATE_EPOCH_ACCEPTED_STEP: u32 = 2;

pub type SaSectionFamilyV1 = u32;
pub const SA_SECTION_FRAME_3D: u32 = 1;
pub const SA_SECTION_TRUSS_3D: u32 = 2;
pub const SA_SECTION_RECTANGULAR_RC_FIBER_2D: u32 = 3;

pub type SaElementTypeV1 = u32;
pub const SA_ELEMENT_FRAME_3D: u32 = 1;
pub const SA_ELEMENT_TRUSS_3D: u32 = 2;
pub const SA_ELEMENT_FRAME_2D: u32 = 3;

pub type SaElementFormulationV1 = u32;
pub const SA_FORMULATION_EULER_BERNOULLI_3D: u32 = 1;
pub const SA_FORMULATION_LINEAR_TRUSS_3D: u32 = 2;
pub const SA_FORMULATION_STATEFUL_COROTATIONAL_TIMOSHENKO_FRAME3D: u32 = 3;
pub const SA_FORMULATION_STATEFUL_COROTATIONAL_RC_FIBER_FRAME2D: u32 = 4;

pub type SaAnalysisTypeV1 = u32;
pub const SA_ANALYSIS_LINEAR_STATIC: u32 = 1;
pub const SA_ANALYSIS_NONLINEAR_STATIC_LOAD_CONTROL: u32 = 2;
pub const SA_ANALYSIS_NONLINEAR_STATIC_DIRECT_DISPLACEMENT_CONTROL: u32 = 3;

pub type SaLoadRefKindV1 = u32;
pub const SA_LOAD_REF_PATTERN: u32 = 1;
pub const SA_LOAD_REF_COMBINATION: u32 = 2;

pub type SaMemberLoadBasisV1 = u32;
pub const SA_MEMBER_LOAD_INITIAL_MEMBER_LOCAL: u32 = 1;

pub type SaMemberLoadDistributionV1 = u32;
pub const SA_MEMBER_LOAD_UNIFORM_FULL_SPAN: u32 = 1;

pub type SaModelIrEntityKindV1 = u32;
pub const SA_MODEL_IR_ENTITY_NODE: u32 = 1;
pub const SA_MODEL_IR_ENTITY_MATERIAL: u32 = 2;
pub const SA_MODEL_IR_ENTITY_SECTION: u32 = 3;
pub const SA_MODEL_IR_ENTITY_ELEMENT: u32 = 4;
pub const SA_MODEL_IR_ENTITY_CONSTRAINT: u32 = 5;
pub const SA_MODEL_IR_ENTITY_LOAD_PATTERN: u32 = 6;
pub const SA_MODEL_IR_ENTITY_LOAD_COMBINATION: u32 = 7;
pub const SA_MODEL_IR_ENTITY_TIME_FUNCTION: u32 = 8;
pub const SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE: u32 = 9;

pub type SaRoundtripMappingStatusV1 = u32;
pub const SA_ROUNDTRIP_EXACT: u32 = 1;
pub const SA_ROUNDTRIP_CANONICALIZED: u32 = 2;
pub const SA_ROUNDTRIP_APPROXIMATED: u32 = 3;
pub const SA_ROUNDTRIP_UNSUPPORTED: u32 = 4;

pub type SaUnsupportedDispositionV1 = u32;
pub const SA_UNSUPPORTED_BLOCKED: u32 = 1;
pub const SA_UNSUPPORTED_PARTIAL_IMPORT: u32 = 2;
pub const SA_UNSUPPORTED_APPROXIMATED: u32 = 3;
pub const SA_UNSUPPORTED_PRESERVED_ONLY: u32 = 4;

#[repr(C)]
pub struct SaModelIrHandleV1 {
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaStringViewV1 {
    pub data: *const c_char,
    pub length: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaOptionalStringViewV1 {
    pub value: SaStringViewV1,
    pub is_present: u32,
    pub reserved: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaSourceUnitsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub length: SaLengthUnitV1,
    pub force: SaForceUnitV1,
    pub mass: SaMassUnitV1,
    pub time: SaTimeUnitV1,
    pub rotation: SaRotationUnitV1,
    pub reserved: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaUnitScalesV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub length_to_m: f64,
    pub force_to_n: f64,
    pub mass_to_kg: f64,
    pub time_to_s: f64,
    pub rotation_to_rad: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaProvenanceDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub source_format: SaSourceFormatV1,
    pub reserved: u32,
    pub source_ref: SaStringViewV1,
    pub source_sha256: SaStringViewV1,
    pub normalizer_id: SaStringViewV1,
    pub normalizer_version: SaStringViewV1,
    pub source_units: SaSourceUnitsV1,
    pub unit_scales_to_si: SaUnitScalesV1,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaCoordinateSystemDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub is_global: u32,
    pub axis_order_xyz: u32,
    pub up_axis_z: u32,
    pub right_handed: u32,
    pub origin_m: [f64; 3],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaEntityIdentityV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub id: SaStringViewV1,
    pub index: u64,
    pub source_id: SaOptionalStringViewV1,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNodeDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub coordinates_m: [f64; 3],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaLinearMaterialParametersV1 {
    pub elastic_modulus_pa: f64,
    pub poisson_ratio: f64,
    pub density_kg_m3: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaSteelMaterialParametersV1 {
    pub elastic_modulus_pa: f64,
    pub shear_modulus_pa: f64,
    pub yield_stress_pa: f64,
    pub isotropic_hardening_modulus_pa: f64,
    pub kinematic_hardening_modulus_pa: f64,
    pub yield_tolerance_pa: f64,
    pub has_shear_modulus: u32,
    pub reserved: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaConcreteMaterialParametersV1 {
    pub elastic_modulus_pa: f64,
    pub tensile_strength_pa: f64,
    pub compressive_strength_pa: f64,
    pub tensile_softening_rate: f64,
    pub compressive_softening_rate: f64,
    pub history_tolerance: f64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub union SaMaterialParametersV1 {
    pub linear: SaLinearMaterialParametersV1,
    pub steel: SaSteelMaterialParametersV1,
    pub concrete: SaConcreteMaterialParametersV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaMaterialAdmissibilityV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub is_present: u32,
    pub reserved: u32,
    pub loading_domain: SaStringViewV1,
    pub supports_unloading: u32,
    pub supports_reversal: u32,
    pub supports_cyclic: u32,
    pub supports_tension: u32,
    pub supports_compression: u32,
    pub supports_multiaxial: u32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SaMaterialDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub law_id: SaMaterialLawV1,
    pub parameter_set_version: u32,
    pub parameters: SaMaterialParametersV1,
    pub stateful: u32,
    pub state_update_epoch: SaMaterialStateEpochV1,
    pub supports_trial_commit_rollback: u32,
    pub reserved: u32,
    pub admissibility: SaMaterialAdmissibilityV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaFrameSectionParametersV1 {
    pub area_m2: f64,
    pub iy_m4: f64,
    pub iz_m4: f64,
    pub torsional_constant_m4: f64,
    pub shear_area_y_m2: f64,
    pub shear_area_z_m2: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaTrussSectionParametersV1 {
    pub area_m2: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaRcFiberSectionParametersV1 {
    pub width_m: f64,
    pub depth_m: f64,
    pub cover_m: f64,
    pub concrete_layer_count: u64,
    pub top_bar_count: u64,
    pub bottom_bar_count: u64,
    pub bar_area_m2: f64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub union SaSectionParametersV1 {
    pub frame: SaFrameSectionParametersV1,
    pub truss: SaTrussSectionParametersV1,
    pub rc_fiber: SaRcFiberSectionParametersV1,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SaSectionDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub family_id: SaSectionFamilyV1,
    pub parameter_set_version: u32,
    pub parameters: SaSectionParametersV1,
    pub steel_material_id: SaOptionalStringViewV1,
    pub concrete_material_id: SaOptionalStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaElementDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub element_type: SaElementTypeV1,
    pub formulation: SaElementFormulationV1,
    pub node_ids: [SaStringViewV1; 2],
    pub material_id: SaOptionalStringViewV1,
    pub section_id: SaStringViewV1,
    pub local_axis_rotation_rad: f64,
    pub has_local_axis_rotation: u32,
    pub reserved0: u32,
    pub offset_i_global_m: [f64; 3],
    pub offset_j_global_m: [f64; 3],
    pub releases_i: *const SaDofV1,
    pub releases_i_count: u64,
    pub releases_j: *const SaDofV1,
    pub releases_j_count: u64,
    pub integration_order: u64,
    pub has_integration_order: u32,
    pub has_uniform_distributed_load_local: u32,
    pub uniform_qx_n_per_m: f64,
    pub uniform_qy_n_per_m: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaPrescribedValueV1 {
    pub dof: SaDofV1,
    pub reserved: u32,
    pub value_si: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaConstraintDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub node_id: SaStringViewV1,
    pub dofs: *const SaDofV1,
    pub dof_count: u64,
    pub prescribed_values: *const SaPrescribedValueV1,
    pub prescribed_value_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNodalLoadDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub node_id: SaStringViewV1,
    pub components_si: [f64; 6],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaMemberDistributedLoadDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub load_pattern_id: SaStringViewV1,
    pub element_id: SaStringViewV1,
    pub basis: SaMemberLoadBasisV1,
    pub distribution: SaMemberLoadDistributionV1,
    pub components_si: [f64; 3],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaLoadPatternDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub analysis_type: SaAnalysisTypeV1,
    pub reserved: u32,
    pub self_weight: [f64; 3],
    pub nodal_loads: *const SaNodalLoadDescriptorV1,
    pub nodal_load_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaLoadCombinationTermV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub ref_id: SaStringViewV1,
    pub ref_kind: SaLoadRefKindV1,
    pub reserved: u32,
    pub factor: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaLoadCombinationDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub identity: SaEntityIdentityV1,
    pub terms: *const SaLoadCombinationTermV1,
    pub term_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaTimePointV1 {
    pub time: f64,
    pub value: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaTimeFunctionDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub id: SaStringViewV1,
    pub index: u64,
    pub points: *const SaTimePointV1,
    pub point_count: u64,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaConstructionStageDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub id: SaStringViewV1,
    pub index: u64,
    pub active_element_ids: *const SaStringViewV1,
    pub active_element_id_count: u64,
    pub active_constraint_ids: *const SaStringViewV1,
    pub active_constraint_id_count: u64,
    pub load_pattern_ids: *const SaStringViewV1,
    pub load_pattern_id_count: u64,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaRoundtripRowDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub source_entity_id: SaStringViewV1,
    pub entity_kind: SaModelIrEntityKindV1,
    pub reserved: u32,
    pub model_ir_entity_id: SaStringViewV1,
    pub mapping_status: SaRoundtripMappingStatusV1,
    pub reserved1: u32,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaUnsupportedFeatureDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub feature_id: SaStringViewV1,
    pub kind: SaStringViewV1,
    pub source_entity_id: SaOptionalStringViewV1,
    pub disposition: SaUnsupportedDispositionV1,
    pub blocking: u32,
    pub detail: SaStringViewV1,
    pub extensions_json: SaStringViewV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrDescriptorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub schema_version: SaStringViewV1,
    pub model_id: SaStringViewV1,
    pub capability_profile: SaModelIrCapabilityProfileV1,
    pub reserved0: u32,
    pub canonical_units: SaSourceUnitsV1,
    pub coordinate_system: SaCoordinateSystemDescriptorV1,
    pub dof_components: *const SaDofV1,
    pub dof_component_count: u64,
    pub provenance: SaProvenanceDescriptorV1,
    pub nodes: *const SaNodeDescriptorV1,
    pub node_count: u64,
    pub materials: *const SaMaterialDescriptorV1,
    pub material_count: u64,
    pub sections: *const SaSectionDescriptorV1,
    pub section_count: u64,
    pub elements: *const SaElementDescriptorV1,
    pub element_count: u64,
    pub constraints: *const SaConstraintDescriptorV1,
    pub constraint_count: u64,
    pub load_patterns: *const SaLoadPatternDescriptorV1,
    pub load_pattern_count: u64,
    pub load_combinations: *const SaLoadCombinationDescriptorV1,
    pub load_combination_count: u64,
    pub time_functions: *const SaTimeFunctionDescriptorV1,
    pub time_function_count: u64,
    pub construction_stages: *const SaConstructionStageDescriptorV1,
    pub construction_stage_count: u64,
    pub roundtrip_rows: *const SaRoundtripRowDescriptorV1,
    pub roundtrip_row_count: u64,
    pub unsupported_features: *const SaUnsupportedFeatureDescriptorV1,
    pub unsupported_feature_count: u64,
    pub extensions_json: SaStringViewV1,
    pub canonical_json: SaStringViewV1,
    pub content_hash: SaStringViewV1,
    pub semantic_hash: SaStringViewV1,
    pub provenance_hash: SaStringViewV1,
    pub flags: u64,
    pub reserved: [u64; 3],
    pub member_distributed_loads: *const SaMemberDistributedLoadDescriptorV1,
    pub member_distributed_load_count: u64,
}

pub type SaModelIrCreateFnV1 = unsafe extern "C" fn(
    descriptor: *const SaModelIrDescriptorV1,
    out_handle: *mut *mut SaModelIrHandleV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrDestroyFnV1 = unsafe extern "C" fn(
    handle: *mut SaModelIrHandleV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrValidationReportSizeFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    out_size: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrValidationReportWriteFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    output: *mut u8,
    capacity: u64,
    out_written: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrSnapshotSizeFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    out_size: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrSnapshotWriteFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    output: *mut u8,
    capacity: u64,
    out_written: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaConcreteMaterialParametersV1, SaConstraintDescriptorV1, SaConstructionStageDescriptorV1,
        SaCoordinateSystemDescriptorV1, SaElementDescriptorV1, SaEntityIdentityV1,
        SaFrameSectionParametersV1, SaLinearMaterialParametersV1, SaLoadCombinationDescriptorV1,
        SaLoadCombinationTermV1, SaLoadPatternDescriptorV1, SaMaterialAdmissibilityV1,
        SaMaterialDescriptorV1, SaMaterialParametersV1, SaMemberDistributedLoadDescriptorV1,
        SaModelIrDescriptorV1, SaNodalLoadDescriptorV1, SaNodeDescriptorV1, SaOptionalStringViewV1,
        SaPrescribedValueV1, SaProvenanceDescriptorV1, SaRcFiberSectionParametersV1,
        SaRoundtripRowDescriptorV1, SaSectionDescriptorV1, SaSectionParametersV1, SaSourceUnitsV1,
        SaSteelMaterialParametersV1, SaStringViewV1, SaTimeFunctionDescriptorV1, SaTimePointV1,
        SaTrussSectionParametersV1, SaUnitScalesV1, SaUnsupportedFeatureDescriptorV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_model_ir_layout_matches_the_public_c_header_contract() {
        macro_rules! assert_layout {
            ($type:ty, $size:literal, $alignment:literal) => {
                assert_eq!(size_of::<$type>(), $size);
                assert_eq!(align_of::<$type>(), $alignment);
            };
        }
        assert_layout!(SaStringViewV1, 16, 8);
        assert_layout!(SaOptionalStringViewV1, 24, 8);
        assert_layout!(SaSourceUnitsV1, 32, 4);
        assert_layout!(SaUnitScalesV1, 48, 8);
        assert_layout!(SaProvenanceDescriptorV1, 176, 8);
        assert_layout!(SaCoordinateSystemDescriptorV1, 48, 8);
        assert_layout!(SaEntityIdentityV1, 72, 8);
        assert_layout!(SaNodeDescriptorV1, 104, 8);
        assert_layout!(SaLinearMaterialParametersV1, 24, 8);
        assert_layout!(SaSteelMaterialParametersV1, 56, 8);
        assert_layout!(SaConcreteMaterialParametersV1, 48, 8);
        assert_layout!(SaMaterialParametersV1, 56, 8);
        assert_layout!(SaMaterialAdmissibilityV1, 56, 8);
        assert_layout!(SaMaterialDescriptorV1, 216, 8);
        assert_layout!(SaFrameSectionParametersV1, 48, 8);
        assert_layout!(SaTrussSectionParametersV1, 8, 8);
        assert_layout!(SaRcFiberSectionParametersV1, 56, 8);
        assert_layout!(SaSectionParametersV1, 56, 8);
        assert_layout!(SaSectionDescriptorV1, 192, 8);
        assert_layout!(SaElementDescriptorV1, 288, 8);
        assert_layout!(SaPrescribedValueV1, 16, 8);
        assert_layout!(SaConstraintDescriptorV1, 128, 8);
        assert_layout!(SaNodalLoadDescriptorV1, 144, 8);
        assert_layout!(SaMemberDistributedLoadDescriptorV1, 144, 8);
        assert_layout!(SaLoadPatternDescriptorV1, 128, 8);
        assert_layout!(SaLoadCombinationTermV1, 40, 8);
        assert_layout!(SaLoadCombinationDescriptorV1, 96, 8);
        assert_layout!(SaTimePointV1, 16, 8);
        assert_layout!(SaTimeFunctionDescriptorV1, 64, 8);
        assert_layout!(SaConstructionStageDescriptorV1, 96, 8);
        assert_layout!(SaRoundtripRowDescriptorV1, 72, 8);
        assert_layout!(SaUnsupportedFeatureDescriptorV1, 104, 8);
        assert_layout!(SaModelIrDescriptorV1, 624, 8);
        assert_eq!(offset_of!(SaModelIrDescriptorV1, provenance), 144);
        assert_eq!(offset_of!(SaModelIrDescriptorV1, nodes), 320);
        assert_eq!(offset_of!(SaModelIrDescriptorV1, canonical_json), 512);
        assert_eq!(offset_of!(SaModelIrDescriptorV1, reserved), 584);
        assert_eq!(
            offset_of!(SaModelIrDescriptorV1, member_distributed_loads),
            608
        );
        assert_eq!(
            offset_of!(SaModelIrDescriptorV1, member_distributed_load_count),
            616
        );
    }
}
