#ifndef STRUCTURAL_TESTS_MODEL_IR_ASSEMBLY_FIXTURE_HPP
#define STRUCTURAL_TESTS_MODEL_IR_ASSEMBLY_FIXTURE_HPP

#include "structural/abi_v1.h"

#include <array>
#include <cstdint>
#include <cstring>

namespace structural::tests {

[[nodiscard]] inline sa_string_view_v1 text(const char* const value) {
    return {value, static_cast<std::uint64_t>(std::strlen(value))};
}

[[nodiscard]] inline sa_optional_string_view_v1 absent_text() {
    return {{nullptr, 0U}, 0U, 0U};
}

[[nodiscard]] inline sa_optional_string_view_v1 present_text(const char* const value) {
    return {text(value), 1U, 0U};
}

[[nodiscard]] inline sa_entity_identity_v1 entity(
    const char* const id,
    const std::uint64_t index) {
    return {
        SA_ABI_V1_1,
        static_cast<std::uint32_t>(sizeof(sa_entity_identity_v1)),
        text(id),
        index,
        absent_text(),
        text("{}"),
    };
}

struct ModelIrAssemblyFixture final {
    ModelIrAssemblyFixture(const ModelIrAssemblyFixture&) = delete;
    ModelIrAssemblyFixture& operator=(const ModelIrAssemblyFixture&) = delete;
    ModelIrAssemblyFixture(ModelIrAssemblyFixture&&) = delete;
    ModelIrAssemblyFixture& operator=(ModelIrAssemblyFixture&&) = delete;

    std::array<char, 2> canonical {'{', '}'};
    std::array<sa_dof_v1, 6> canonical_dofs {
        SA_DOF_UX,
        SA_DOF_UY,
        SA_DOF_UZ,
        SA_DOF_RX,
        SA_DOF_RY,
        SA_DOF_RZ,
    };
    std::array<sa_dof_v1, 6> fixed_dofs = canonical_dofs;
    std::array<sa_dof_v1, 5> n2_guided_dofs {
        SA_DOF_UX,
        SA_DOF_UZ,
        SA_DOF_RX,
        SA_DOF_RY,
        SA_DOF_RZ,
    };
    std::array<sa_node_descriptor_v1, 3> nodes {};
    std::array<sa_material_descriptor_v1, 1> materials {};
    std::array<sa_section_descriptor_v1, 2> sections {};
    std::array<sa_element_descriptor_v1, 2> elements {};
    std::array<sa_constraint_descriptor_v1, 2> constraints {};
    std::array<sa_nodal_load_descriptor_v1, 2> nodal_loads {};
    std::array<sa_nodal_load_descriptor_v1, 1> secondary_nodal_loads {};
    std::array<sa_nodal_load_descriptor_v1, 1> tertiary_nodal_loads {};
    std::array<sa_load_pattern_descriptor_v1, 3> load_patterns {};
    std::array<sa_load_combination_term_v1, 3> load_combination_terms {};
    std::array<sa_load_combination_descriptor_v1, 1> load_combinations {};
    sa_model_ir_descriptor_v1 descriptor {};

    ModelIrAssemblyFixture() {
        nodes[0] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_node_descriptor_v1)),
            entity("n0", 0U),
            {0.0, 0.0, 0.0},
        };
        nodes[1] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_node_descriptor_v1)),
            entity("n1", 1U),
            {2.0, 0.0, 0.0},
        };
        nodes[2] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_node_descriptor_v1)),
            entity("n2", 2U),
            {2.0, 1.0, 0.0},
        };

        materials[0].abi_version = SA_ABI_V1_1;
        materials[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_material_descriptor_v1));
        materials[0].identity = entity("mat", 0U);
        materials[0].law_id = SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC;
        materials[0].parameter_set_version = 1U;
        materials[0].parameters.linear = {200.0, 0.25, 1000.0};
        materials[0].stateful = 0U;
        materials[0].state_update_epoch = SA_MATERIAL_STATE_EPOCH_NONE;
        materials[0].supports_trial_commit_rollback = 1U;
        materials[0].admissibility.abi_version = SA_ABI_V1_1;
        materials[0].admissibility.struct_size =
            static_cast<std::uint32_t>(sizeof(sa_material_admissibility_v1));

        sections[0].abi_version = SA_ABI_V1_1;
        sections[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_section_descriptor_v1));
        sections[0].identity = entity("frame", 0U);
        sections[0].family_id = SA_SECTION_FRAME_3D;
        sections[0].parameter_set_version = 1U;
        sections[0].parameters.frame = {0.01, 2.0e-5, 3.0e-5, 4.0e-5, 0.01, 0.01};
        sections[0].steel_material_id = absent_text();
        sections[0].concrete_material_id = absent_text();
        sections[1].abi_version = SA_ABI_V1_1;
        sections[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_section_descriptor_v1));
        sections[1].identity = entity("truss", 1U);
        sections[1].family_id = SA_SECTION_TRUSS_3D;
        sections[1].parameter_set_version = 1U;
        sections[1].parameters.truss = {0.02};
        sections[1].steel_material_id = absent_text();
        sections[1].concrete_material_id = absent_text();

        elements[0].abi_version = SA_ABI_V1_1;
        elements[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_element_descriptor_v1));
        elements[0].identity = entity("e0", 0U);
        elements[0].type = SA_ELEMENT_FRAME_3D;
        elements[0].formulation = SA_FORMULATION_EULER_BERNOULLI_3D;
        elements[0].node_ids[0] = text("n0");
        elements[0].node_ids[1] = text("n1");
        elements[0].material_id = present_text("mat");
        elements[0].section_id = text("frame");
        elements[0].local_axis_rotation_rad = 0.2;
        elements[0].has_local_axis_rotation = 1U;
        elements[1].abi_version = SA_ABI_V1_1;
        elements[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_element_descriptor_v1));
        elements[1].identity = entity("e1", 1U);
        elements[1].type = SA_ELEMENT_TRUSS_3D;
        elements[1].formulation = SA_FORMULATION_LINEAR_TRUSS_3D;
        elements[1].node_ids[0] = text("n1");
        elements[1].node_ids[1] = text("n2");
        elements[1].material_id = present_text("mat");
        elements[1].section_id = text("truss");

        constraints[0].abi_version = SA_ABI_V1_1;
        constraints[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_constraint_descriptor_v1));
        constraints[0].identity = entity("c0", 0U);
        constraints[0].node_id = text("n0");
        constraints[0].dofs = fixed_dofs.data();
        constraints[0].dof_count = fixed_dofs.size();
        constraints[1].abi_version = SA_ABI_V1_1;
        constraints[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_constraint_descriptor_v1));
        constraints[1].identity = entity("c1", 1U);
        constraints[1].node_id = text("n2");
        constraints[1].dofs = n2_guided_dofs.data();
        constraints[1].dof_count = n2_guided_dofs.size();

        nodal_loads[0].abi_version = SA_ABI_V1_1;
        nodal_loads[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_nodal_load_descriptor_v1));
        nodal_loads[0].identity = entity("l0", 0U);
        nodal_loads[0].node_id = text("n1");
        nodal_loads[0].components_si[0] = 10.0;
        nodal_loads[0].components_si[1] = -20.0;
        nodal_loads[1].abi_version = SA_ABI_V1_1;
        nodal_loads[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_nodal_load_descriptor_v1));
        nodal_loads[1].identity = entity("l1", 1U);
        nodal_loads[1].node_id = text("n2");
        nodal_loads[1].components_si[1] = 30.0;

        load_patterns[0].abi_version = SA_ABI_V1_1;
        load_patterns[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_load_pattern_descriptor_v1));
        load_patterns[0].identity = entity("lp", 0U);
        load_patterns[0].analysis_type = SA_ANALYSIS_LINEAR_STATIC;
        load_patterns[0].nodal_loads = nodal_loads.data();
        load_patterns[0].nodal_load_count = nodal_loads.size();

        secondary_nodal_loads[0].abi_version = SA_ABI_V1_1;
        secondary_nodal_loads[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_nodal_load_descriptor_v1));
        secondary_nodal_loads[0].identity = entity("l2", 0U);
        secondary_nodal_loads[0].node_id = text("n1");
        secondary_nodal_loads[0].components_si[2] = 8.0;
        load_patterns[1].abi_version = SA_ABI_V1_1;
        load_patterns[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_load_pattern_descriptor_v1));
        load_patterns[1].identity = entity("lp2", 1U);
        load_patterns[1].analysis_type = SA_ANALYSIS_LINEAR_STATIC;
        load_patterns[1].nodal_loads = secondary_nodal_loads.data();
        load_patterns[1].nodal_load_count = secondary_nodal_loads.size();

        tertiary_nodal_loads[0].abi_version = SA_ABI_V1_1;
        tertiary_nodal_loads[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_nodal_load_descriptor_v1));
        tertiary_nodal_loads[0].identity = entity("l3", 0U);
        tertiary_nodal_loads[0].node_id = text("n2");
        tertiary_nodal_loads[0].components_si[1] = 16.0;
        load_patterns[2].abi_version = SA_ABI_V1_1;
        load_patterns[2].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_load_pattern_descriptor_v1));
        load_patterns[2].identity = entity("lp3", 2U);
        load_patterns[2].analysis_type = SA_ANALYSIS_LINEAR_STATIC;
        load_patterns[2].nodal_loads = tertiary_nodal_loads.data();
        load_patterns[2].nodal_load_count = tertiary_nodal_loads.size();

        load_combination_terms[0] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            text("lp"),
            SA_LOAD_REF_PATTERN,
            0U,
            1.2,
        };
        load_combination_terms[1] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            text("lp2"),
            SA_LOAD_REF_PATTERN,
            0U,
            -0.5,
        };
        load_combination_terms[2] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            text("lp3"),
            SA_LOAD_REF_PATTERN,
            0U,
            0.25,
        };
        load_combinations[0] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_descriptor_v1)),
            entity("combo", 0U),
            load_combination_terms.data(),
            2U,
        };

        descriptor.abi_version = SA_ABI_V1_1;
        descriptor.struct_size =
            static_cast<std::uint32_t>(sizeof(sa_model_ir_descriptor_v1));
        descriptor.schema_version = text("structural-analysis-model-ir.v2");
        descriptor.model_id = text("model-assembly");
        descriptor.capability_profile = SA_MODEL_IR_PROFILE_GENERAL;
        descriptor.canonical_units = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_source_units_v1)),
            SA_LENGTH_UNIT_M,
            SA_FORCE_UNIT_N,
            SA_MASS_UNIT_KG,
            SA_TIME_UNIT_S,
            SA_ROTATION_UNIT_RAD,
            0U,
        };
        descriptor.coordinate_system = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_coordinate_system_descriptor_v1)),
            1U,
            1U,
            1U,
            1U,
            {0.0, 0.0, 0.0},
        };
        descriptor.dof_components = canonical_dofs.data();
        descriptor.dof_component_count = canonical_dofs.size();
        descriptor.provenance.abi_version = SA_ABI_V1_1;
        descriptor.provenance.struct_size =
            static_cast<std::uint32_t>(sizeof(sa_provenance_descriptor_v1));
        descriptor.provenance.source_format = SA_SOURCE_FORMAT_GENERATED;
        descriptor.provenance.source_ref = text("unit-test");
        descriptor.provenance.source_sha256 = text(
            "sha256:0000000000000000000000000000000000000000000000000000000000000000");
        descriptor.provenance.normalizer_id = text("native-test");
        descriptor.provenance.normalizer_version = text("1");
        descriptor.provenance.source_units = descriptor.canonical_units;
        descriptor.provenance.unit_scales_to_si = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_unit_scales_v1)),
            1.0,
            1.0,
            1.0,
            1.0,
            1.0,
        };
        descriptor.provenance.extensions_json = text("{}");
        descriptor.nodes = nodes.data();
        descriptor.node_count = nodes.size();
        descriptor.materials = materials.data();
        descriptor.material_count = materials.size();
        descriptor.sections = sections.data();
        descriptor.section_count = sections.size();
        descriptor.elements = elements.data();
        descriptor.element_count = elements.size();
        descriptor.constraints = constraints.data();
        descriptor.constraint_count = constraints.size();
        descriptor.load_patterns = load_patterns.data();
        descriptor.load_pattern_count = 1U;
        descriptor.extensions_json = text("{}");
        descriptor.canonical_json = {canonical.data(), canonical.size()};
        descriptor.content_hash = text(
            "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
        descriptor.semantic_hash = text(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111");
        descriptor.provenance_hash = text(
            "sha256:2222222222222222222222222222222222222222222222222222222222222222");
    }

    void enable_linear_combination() {
        descriptor.load_pattern_count = 2U;
        descriptor.load_combinations = load_combinations.data();
        descriptor.load_combination_count = load_combinations.size();
    }

    void enable_three_pattern_linear_combination() {
        descriptor.load_pattern_count = load_patterns.size();
        load_combinations[0].term_count = load_combination_terms.size();
        descriptor.load_combinations = load_combinations.data();
        descriptor.load_combination_count = load_combinations.size();
    }
};

[[nodiscard]] inline std::array<double, 18> assembly_displacement() {
    std::array<double, 18> output {};
    output[6] = 0.001;
    output[7] = -0.002;
    output[8] = 0.003;
    output[9] = 0.0004;
    output[10] = -0.0005;
    output[11] = 0.0006;
    output[13] = 0.004;
    return output;
}

[[nodiscard]] inline std::array<double, 18> assembly_direction() {
    std::array<double, 18> output {};
    output[6] = -0.003;
    output[7] = 0.002;
    output[8] = 0.001;
    output[9] = -0.0002;
    output[10] = 0.0007;
    output[11] = -0.0004;
    output[13] = -0.005;
    return output;
}

}  // namespace structural::tests

#endif
