#ifndef STRUCTURAL_MODEL_IR_V1_H
#define STRUCTURAL_MODEL_IR_V1_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * ModelIR v2 typed descriptor surface introduced by ABI v1.1.
 *
 * Every pointer is borrowed only for the duration of sa_model_ir_create_v1.
 * A successful create deep-copies the complete descriptor and canonical
 * snapshot.  Counts and lengths are element counts, never byte counts.
 */

typedef struct sa_model_ir_handle_v1 sa_model_ir_handle_v1;

typedef struct sa_string_view_v1 {
    const char* data;
    uint64_t length;
} sa_string_view_v1;

typedef struct sa_optional_string_view_v1 {
    sa_string_view_v1 value;
    uint32_t is_present;
    uint32_t reserved;
} sa_optional_string_view_v1;

typedef uint32_t sa_model_ir_capability_profile_v1;
enum {
    SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D = 1,
    SA_MODEL_IR_PROFILE_GENERAL = SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D,
    SA_MODEL_IR_PROFILE_BOUNDED_PLANAR_FRAME_ALPHA = 2,
    SA_MODEL_IR_PROFILE_PLANAR_FRAME_VERIFIED_ALPHA_V1 = 3,
    SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL = 4
};

typedef uint32_t sa_source_format_v1;
enum {
    SA_SOURCE_FORMAT_NEUTRAL_JSON = 1,
    SA_SOURCE_FORMAT_MIDAS_MGT = 2,
    SA_SOURCE_FORMAT_IFC = 3,
    SA_SOURCE_FORMAT_OPENSEES = 4,
    SA_SOURCE_FORMAT_ETABS_E2K = 5,
    SA_SOURCE_FORMAT_DXF = 6,
    SA_SOURCE_FORMAT_GENERATED = 7
};

typedef uint32_t sa_length_unit_v1;
enum {
    SA_LENGTH_UNIT_M = 1,
    SA_LENGTH_UNIT_MM = 2,
    SA_LENGTH_UNIT_CM = 3,
    SA_LENGTH_UNIT_FT = 4,
    SA_LENGTH_UNIT_IN = 5
};

typedef uint32_t sa_force_unit_v1;
enum {
    SA_FORCE_UNIT_N = 1,
    SA_FORCE_UNIT_KN = 2,
    SA_FORCE_UNIT_MN = 3,
    SA_FORCE_UNIT_LBF = 4,
    SA_FORCE_UNIT_KIP = 5
};

typedef uint32_t sa_mass_unit_v1;
enum {
    SA_MASS_UNIT_KG = 1,
    SA_MASS_UNIT_TONNE = 2,
    SA_MASS_UNIT_SLUG = 3
};

typedef uint32_t sa_time_unit_v1;
enum { SA_TIME_UNIT_S = 1 };

typedef uint32_t sa_rotation_unit_v1;
enum {
    SA_ROTATION_UNIT_RAD = 1,
    SA_ROTATION_UNIT_DEG = 2
};

typedef uint32_t sa_dof_v1;
enum {
    SA_DOF_UX = 1,
    SA_DOF_UY = 2,
    SA_DOF_UZ = 3,
    SA_DOF_RX = 4,
    SA_DOF_RY = 5,
    SA_DOF_RZ = 6
};

typedef uint32_t sa_material_law_v1;
enum {
    SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC = 1,
    SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL = 2,
    SA_MATERIAL_ASYMMETRIC_CONCRETE_DAMAGE = 3
};

typedef uint32_t sa_material_state_epoch_v1;
enum {
    SA_MATERIAL_STATE_EPOCH_NONE = 1,
    SA_MATERIAL_STATE_EPOCH_ACCEPTED_STEP = 2
};

typedef uint32_t sa_section_family_v1;
enum {
    SA_SECTION_FRAME_3D = 1,
    SA_SECTION_TRUSS_3D = 2,
    SA_SECTION_RECTANGULAR_RC_FIBER_2D = 3
};

typedef uint32_t sa_element_type_v1;
enum {
    SA_ELEMENT_FRAME_3D = 1,
    SA_ELEMENT_TRUSS_3D = 2,
    SA_ELEMENT_FRAME_2D = 3
};

typedef uint32_t sa_element_formulation_v1;
enum {
    SA_FORMULATION_EULER_BERNOULLI_3D = 1,
    SA_FORMULATION_LINEAR_TRUSS_3D = 2,
    SA_FORMULATION_STATEFUL_COROTATIONAL_TIMOSHENKO_FRAME3D = 3,
    SA_FORMULATION_STATEFUL_COROTATIONAL_RC_FIBER_FRAME2D = 4,
    SA_FORMULATION_LINEAR_TIMOSHENKO_FRAME3D = 5
};

typedef uint32_t sa_analysis_type_v1;
enum {
    SA_ANALYSIS_LINEAR_STATIC = 1,
    SA_ANALYSIS_NONLINEAR_STATIC_LOAD_CONTROL = 2,
    SA_ANALYSIS_NONLINEAR_STATIC_DIRECT_DISPLACEMENT_CONTROL = 3
};

typedef uint32_t sa_load_ref_kind_v1;
enum {
    SA_LOAD_REF_PATTERN = 1,
    SA_LOAD_REF_COMBINATION = 2
};

typedef uint32_t sa_model_ir_entity_kind_v1;
enum {
    SA_MODEL_IR_ENTITY_NODE = 1,
    SA_MODEL_IR_ENTITY_MATERIAL = 2,
    SA_MODEL_IR_ENTITY_SECTION = 3,
    SA_MODEL_IR_ENTITY_ELEMENT = 4,
    SA_MODEL_IR_ENTITY_CONSTRAINT = 5,
    SA_MODEL_IR_ENTITY_LOAD_PATTERN = 6,
    SA_MODEL_IR_ENTITY_LOAD_COMBINATION = 7,
    SA_MODEL_IR_ENTITY_TIME_FUNCTION = 8,
    SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE = 9
};

typedef uint32_t sa_roundtrip_mapping_status_v1;
enum {
    SA_ROUNDTRIP_EXACT = 1,
    SA_ROUNDTRIP_CANONICALIZED = 2,
    SA_ROUNDTRIP_APPROXIMATED = 3,
    SA_ROUNDTRIP_UNSUPPORTED = 4
};

typedef uint32_t sa_unsupported_disposition_v1;
enum {
    SA_UNSUPPORTED_BLOCKED = 1,
    SA_UNSUPPORTED_PARTIAL_IMPORT = 2,
    SA_UNSUPPORTED_APPROXIMATED = 3,
    SA_UNSUPPORTED_PRESERVED_ONLY = 4
};

typedef struct sa_source_units_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_length_unit_v1 length;
    sa_force_unit_v1 force;
    sa_mass_unit_v1 mass;
    sa_time_unit_v1 time;
    sa_rotation_unit_v1 rotation;
    uint32_t reserved;
} sa_source_units_v1;

typedef struct sa_unit_scales_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    double length_to_m;
    double force_to_n;
    double mass_to_kg;
    double time_to_s;
    double rotation_to_rad;
} sa_unit_scales_v1;

typedef struct sa_provenance_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_source_format_v1 source_format;
    uint32_t reserved;
    sa_string_view_v1 source_ref;
    sa_string_view_v1 source_sha256;
    sa_string_view_v1 normalizer_id;
    sa_string_view_v1 normalizer_version;
    sa_source_units_v1 source_units;
    sa_unit_scales_v1 unit_scales_to_si;
    sa_string_view_v1 extensions_json;
} sa_provenance_descriptor_v1;

typedef struct sa_coordinate_system_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    /* Schema constants: global, X/Y/Z, Z-up and right-handed. */
    uint32_t is_global;
    uint32_t axis_order_xyz;
    uint32_t up_axis_z;
    uint32_t right_handed;
    double origin_m[3];
} sa_coordinate_system_descriptor_v1;

typedef struct sa_entity_identity_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 id;
    uint64_t index;
    sa_optional_string_view_v1 source_id;
    sa_string_view_v1 extensions_json;
} sa_entity_identity_v1;

typedef struct sa_node_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    double coordinates_m[3];
} sa_node_descriptor_v1;

typedef struct sa_linear_material_parameters_v1 {
    double elastic_modulus_pa;
    double poisson_ratio;
    double density_kg_m3;
} sa_linear_material_parameters_v1;

typedef struct sa_steel_material_parameters_v1 {
    double elastic_modulus_pa;
    double shear_modulus_pa;
    double yield_stress_pa;
    double isotropic_hardening_modulus_pa;
    double kinematic_hardening_modulus_pa;
    double yield_tolerance_pa;
    uint32_t has_shear_modulus;
    uint32_t reserved;
} sa_steel_material_parameters_v1;

typedef struct sa_concrete_material_parameters_v1 {
    double elastic_modulus_pa;
    double tensile_strength_pa;
    double compressive_strength_pa;
    double tensile_softening_rate;
    double compressive_softening_rate;
    double history_tolerance;
} sa_concrete_material_parameters_v1;

typedef union sa_material_parameters_v1 {
    sa_linear_material_parameters_v1 linear;
    sa_steel_material_parameters_v1 steel;
    sa_concrete_material_parameters_v1 concrete;
} sa_material_parameters_v1;

typedef struct sa_material_admissibility_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t is_present;
    uint32_t reserved;
    sa_string_view_v1 loading_domain;
    uint32_t supports_unloading;
    uint32_t supports_reversal;
    uint32_t supports_cyclic;
    uint32_t supports_tension;
    uint32_t supports_compression;
    uint32_t supports_multiaxial;
} sa_material_admissibility_v1;

typedef struct sa_material_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_material_law_v1 law_id;
    uint32_t parameter_set_version;
    sa_material_parameters_v1 parameters;
    uint32_t stateful;
    sa_material_state_epoch_v1 state_update_epoch;
    uint32_t supports_trial_commit_rollback;
    uint32_t reserved;
    sa_material_admissibility_v1 admissibility;
} sa_material_descriptor_v1;

typedef struct sa_frame_section_parameters_v1 {
    double area_m2;
    double iy_m4;
    double iz_m4;
    double torsional_constant_m4;
    double shear_area_y_m2;
    double shear_area_z_m2;
} sa_frame_section_parameters_v1;

typedef struct sa_truss_section_parameters_v1 {
    double area_m2;
} sa_truss_section_parameters_v1;

typedef struct sa_rc_fiber_section_parameters_v1 {
    double width_m;
    double depth_m;
    double cover_m;
    uint64_t concrete_layer_count;
    uint64_t top_bar_count;
    uint64_t bottom_bar_count;
    double bar_area_m2;
} sa_rc_fiber_section_parameters_v1;

typedef union sa_section_parameters_v1 {
    sa_frame_section_parameters_v1 frame;
    sa_truss_section_parameters_v1 truss;
    sa_rc_fiber_section_parameters_v1 rc_fiber;
} sa_section_parameters_v1;

typedef struct sa_section_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_section_family_v1 family_id;
    uint32_t parameter_set_version;
    sa_section_parameters_v1 parameters;
    sa_optional_string_view_v1 steel_material_id;
    sa_optional_string_view_v1 concrete_material_id;
} sa_section_descriptor_v1;

typedef struct sa_element_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_element_type_v1 type;
    sa_element_formulation_v1 formulation;
    sa_string_view_v1 node_ids[2];
    sa_optional_string_view_v1 material_id;
    sa_string_view_v1 section_id;
    double local_axis_rotation_rad;
    uint32_t has_local_axis_rotation;
    uint32_t reserved0;
    double offset_i_global_m[3];
    double offset_j_global_m[3];
    const sa_dof_v1* releases_i;
    uint64_t releases_i_count;
    const sa_dof_v1* releases_j;
    uint64_t releases_j_count;
    uint64_t integration_order;
    uint32_t has_integration_order;
    uint32_t has_uniform_distributed_load_local;
    double uniform_qx_n_per_m;
    double uniform_qy_n_per_m;
} sa_element_descriptor_v1;

typedef struct sa_prescribed_value_v1 {
    sa_dof_v1 dof;
    uint32_t reserved;
    double value_si;
} sa_prescribed_value_v1;

typedef struct sa_constraint_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_string_view_v1 node_id;
    const sa_dof_v1* dofs;
    uint64_t dof_count;
    const sa_prescribed_value_v1* prescribed_values;
    uint64_t prescribed_value_count;
} sa_constraint_descriptor_v1;

typedef struct sa_nodal_load_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_string_view_v1 node_id;
    /* FX, FY, FZ, MX, MY, MZ in that order. */
    double components_si[6];
} sa_nodal_load_descriptor_v1;

typedef struct sa_uniform_member_load_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_string_view_v1 member_id;
    /* QX, QY, QZ in N/m in the initial member-local basis. */
    double components_si[3];
} sa_uniform_member_load_descriptor_v1;

typedef struct sa_load_pattern_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    sa_analysis_type_v1 analysis_type;
    uint32_t reserved;
    double self_weight[3];
    const sa_nodal_load_descriptor_v1* nodal_loads;
    uint64_t nodal_load_count;
    /* Optional append-only v1 tail; absent when struct_size stops before this field. */
    const sa_uniform_member_load_descriptor_v1* uniform_member_loads;
    uint64_t uniform_member_load_count;
} sa_load_pattern_descriptor_v1;

typedef struct sa_load_combination_term_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 ref_id;
    sa_load_ref_kind_v1 ref_kind;
    uint32_t reserved;
    double factor;
} sa_load_combination_term_v1;

typedef struct sa_load_combination_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_entity_identity_v1 identity;
    const sa_load_combination_term_v1* terms;
    uint64_t term_count;
} sa_load_combination_descriptor_v1;

typedef struct sa_time_point_v1 {
    double time;
    double value;
} sa_time_point_v1;

typedef struct sa_time_function_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 id;
    uint64_t index;
    const sa_time_point_v1* points;
    uint64_t point_count;
    sa_string_view_v1 extensions_json;
} sa_time_function_descriptor_v1;

typedef struct sa_construction_stage_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 id;
    uint64_t index;
    const sa_string_view_v1* active_element_ids;
    uint64_t active_element_id_count;
    const sa_string_view_v1* active_constraint_ids;
    uint64_t active_constraint_id_count;
    const sa_string_view_v1* load_pattern_ids;
    uint64_t load_pattern_id_count;
    sa_string_view_v1 extensions_json;
} sa_construction_stage_descriptor_v1;

typedef struct sa_roundtrip_row_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 source_entity_id;
    sa_model_ir_entity_kind_v1 entity_kind;
    uint32_t reserved;
    sa_string_view_v1 model_ir_entity_id;
    sa_roundtrip_mapping_status_v1 mapping_status;
    uint32_t reserved1;
    sa_string_view_v1 extensions_json;
} sa_roundtrip_row_descriptor_v1;

typedef struct sa_unsupported_feature_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 feature_id;
    sa_string_view_v1 kind;
    sa_optional_string_view_v1 source_entity_id;
    sa_unsupported_disposition_v1 disposition;
    uint32_t blocking;
    sa_string_view_v1 detail;
    sa_string_view_v1 extensions_json;
} sa_unsupported_feature_descriptor_v1;

typedef struct sa_model_ir_descriptor_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    sa_string_view_v1 schema_version;
    sa_string_view_v1 model_id;
    sa_model_ir_capability_profile_v1 capability_profile;
    uint32_t reserved0;

    sa_source_units_v1 canonical_units;
    sa_coordinate_system_descriptor_v1 coordinate_system;
    const sa_dof_v1* dof_components;
    uint64_t dof_component_count;
    sa_provenance_descriptor_v1 provenance;

    const sa_node_descriptor_v1* nodes;
    uint64_t node_count;
    const sa_material_descriptor_v1* materials;
    uint64_t material_count;
    const sa_section_descriptor_v1* sections;
    uint64_t section_count;
    const sa_element_descriptor_v1* elements;
    uint64_t element_count;
    const sa_constraint_descriptor_v1* constraints;
    uint64_t constraint_count;
    const sa_load_pattern_descriptor_v1* load_patterns;
    uint64_t load_pattern_count;
    const sa_load_combination_descriptor_v1* load_combinations;
    uint64_t load_combination_count;
    const sa_time_function_descriptor_v1* time_functions;
    uint64_t time_function_count;
    const sa_construction_stage_descriptor_v1* construction_stages;
    uint64_t construction_stage_count;
    const sa_roundtrip_row_descriptor_v1* roundtrip_rows;
    uint64_t roundtrip_row_count;
    const sa_unsupported_feature_descriptor_v1* unsupported_features;
    uint64_t unsupported_feature_count;

    sa_string_view_v1 extensions_json;
    sa_string_view_v1 canonical_json;
    sa_string_view_v1 content_hash;
    sa_string_view_v1 semantic_hash;
    sa_string_view_v1 provenance_hash;
    uint64_t flags;
    uint64_t reserved[3];
} sa_model_ir_descriptor_v1;

#ifdef __cplusplus
}
#endif

#endif
