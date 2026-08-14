#include "model_ir_assembly.hpp"

#include "model_ir_assembly_fixture.hpp"

#include <array>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <string_view>
#include <vector>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_status(
    const std::function<void()>& operation,
    const sa_status_code_v1 expected,
    const std::string_view message) {
    try {
        operation();
    } catch (const structural::model_ir::Error& error) {
        expect(error.status() == expected, message);
        return;
    }
    expect(false, message);
}

}  // namespace

int main() {
    structural::tests::ModelIrAssemblyFixture fixture;
    const structural::model_ir::Model model(fixture.descriptor);
    expect(
        model.validation_report().find("\"analysis_ready\":true") != std::string_view::npos,
        "fixture must pass typed ModelIR semantics");
    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    const auto result = structural::assembly::assemble_model_ir_linear_reference(
        model, "lp", displacement, direction);

    expect(
        result.model_content_hash
            == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "assembly retains exact ModelIR content identity");
    expect(
        result.model_semantic_hash
            == "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        "assembly retains exact ModelIR semantic identity");
    expect(
        result.model_provenance_hash
            == "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        "assembly retains exact ModelIR provenance identity");
    expect(result.load_pattern_id == "lp", "selected load-pattern identity");
    expect(result.load_pattern_index == 0U, "selected load-pattern stable index");
    expect(result.operator_result.global_dof_count == 18U, "six canonical DOFs per node");
    expect(
        result.operator_result.active_dof_indices
            == std::vector<std::uint32_t>({6U, 7U, 8U, 9U, 10U, 11U, 13U}),
        "canonical active node/DOF mapping");
    expect(
        result.operator_result.row_offsets
            == std::vector<std::uint64_t>({0U, 7U, 14U, 21U, 27U, 33U, 39U, 43U}),
        "mixed frame/truss canonical CSR rows");
    expect(
        result.operator_result.column_indices
            == std::vector<std::uint32_t>({
                0U, 1U, 2U, 3U, 4U, 5U, 6U,
                0U, 1U, 2U, 3U, 4U, 5U, 6U,
                0U, 1U, 2U, 3U, 4U, 5U, 6U,
                0U, 1U, 2U, 3U, 4U, 5U,
                0U, 1U, 2U, 3U, 4U, 5U,
                0U, 1U, 2U, 3U, 4U, 5U,
                0U, 1U, 2U, 6U,
            }),
        "mixed frame/truss canonical CSR columns");
    expect(
        result.external_load == std::vector<double>({10.0, -20.0, 0.0, 0.0, 0.0, 0.0, 30.0}),
        "selected nodal-load projection");
    expect(result.equilibrium_residual.size() == result.external_load.size(), "residual size");
    for (std::size_t index = 0U; index < result.external_load.size(); ++index) {
        expect(
            result.equilibrium_residual[index]
                == result.operator_result.residual[index] - result.external_load[index],
            "equilibrium residual uses internal minus external convention");
    }
    expect(result.element_recovery.size() == 2U, "one recovery row per element");
    expect(
        result.element_recovery[0].stable_index == 0U
            && result.element_recovery[0].element_type == SA_ELEMENT_FRAME_3D
            && result.element_recovery[0].values.size() == 12U,
        "frame recovery identity and shape");
    expect(
        result.element_recovery[1].stable_index == 1U
            && result.element_recovery[1].element_type == SA_ELEMENT_TRUSS_3D
            && result.element_recovery[1].values.size() == 3U,
        "truss recovery identity and shape");

    const auto repeated = structural::assembly::assemble_model_ir_linear_reference(
        model, "lp", displacement, direction);
    expect(repeated.operator_result.tangent == result.operator_result.tangent, "repeat tangent");
    expect(
        repeated.operator_result.consistent_mass == result.operator_result.consistent_mass,
        "repeat mass");
    expect(repeated.operator_result.residual == result.operator_result.residual, "repeat internal");
    expect(repeated.operator_result.jvp == result.operator_result.jvp, "repeat JVP");
    expect(repeated.external_load == result.external_load, "repeat external load");
    expect(repeated.equilibrium_residual == result.equilibrium_residual, "repeat equilibrium");

    structural::tests::ModelIrAssemblyFixture combination_fixture;
    combination_fixture.enable_linear_combination();
    const structural::model_ir::Model combination_model(combination_fixture.descriptor);
    const auto combination = structural::assembly::assemble_model_ir_linear_reference(
        combination_model, "combo", displacement, direction);
    expect(combination.load_pattern_id == "combo", "selected combination identity");
    expect(combination.load_pattern_index == 0U, "selected combination stable index");
    expect(
        combination.external_load
            == std::vector<double>({12.0, -24.0, -4.0, 0.0, 0.0, 0.0, 36.0}),
        "two-pattern combination uses deterministic signed factors");
    const auto direct_with_combination = structural::assembly::assemble_model_ir_linear_reference(
        combination_model, "lp", displacement, direction);
    expect(
        direct_with_combination.external_load == result.external_load,
        "combination presence preserves direct-pattern loads");
    expect(
        direct_with_combination.operator_result.tangent == result.operator_result.tangent,
        "combination presence preserves direct-pattern operator");

    structural::tests::ModelIrAssemblyFixture direct_terms_fixture;
    direct_terms_fixture.enable_three_pattern_linear_combination();
    const structural::model_ir::Model direct_terms_model(direct_terms_fixture.descriptor);
    const auto direct_terms = structural::assembly::assemble_model_ir_linear_reference(
        direct_terms_model, "combo", displacement, direction);
    expect(
        direct_terms.external_load
            == std::vector<double>({12.0, -24.0, -4.0, 0.0, 0.0, 0.0, 40.0}),
        "three-pattern combination preserves declared signed-factor order");

    structural::tests::ModelIrAssemblyFixture nested_fixture;
    nested_fixture.enable_nested_linear_combination();
    const structural::model_ir::Model nested_model(nested_fixture.descriptor);
    const auto nested = structural::assembly::assemble_model_ir_linear_reference(
        nested_model, "combo_nested", displacement, direction);
    expect(nested.load_pattern_id == "combo_nested", "selected nested combination identity");
    expect(nested.load_pattern_index == 1U, "selected nested combination stable index");
    expect(
        nested.external_load
            == std::vector<double>({10.0, -20.0, -2.0, 0.0, 0.0, 0.0, 34.0}),
        "nested combination flattens in declaration order and consolidates repeated patterns");
    const auto nested_repeated = structural::assembly::assemble_model_ir_linear_reference(
        nested_model, "combo_nested", displacement, direction);
    expect(
        nested_repeated.external_load == nested.external_load,
        "nested combination flattening is deterministic");

    structural::tests::ModelIrAssemblyFixture deep_nested_fixture;
    constexpr std::array<const char*, 9> deep_ids {
        "deep0", "deep1", "deep2", "deep3", "deep4",
        "deep5", "deep6", "deep7", "deep8",
    };
    std::array<std::array<sa_load_combination_term_v1, 2>, deep_ids.size()> deep_terms {};
    std::array<sa_load_combination_descriptor_v1, deep_ids.size()> deep_combinations {};
    for (std::size_t index = 0U; index < deep_ids.size(); ++index) {
        deep_terms[index][0] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            structural::tests::text(index + 1U == deep_ids.size() ? "lp" : deep_ids[index + 1U]),
            index + 1U == deep_ids.size() ? SA_LOAD_REF_PATTERN : SA_LOAD_REF_COMBINATION,
            0U,
            1.0,
        };
        deep_terms[index][1] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            structural::tests::text("lp2"),
            SA_LOAD_REF_PATTERN,
            0U,
            1.0,
        };
        deep_combinations[index] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_descriptor_v1)),
            structural::tests::entity(deep_ids[index], index),
            deep_terms[index].data(),
            deep_terms[index].size(),
        };
    }
    deep_nested_fixture.descriptor.load_pattern_count = 2U;
    deep_nested_fixture.descriptor.load_combinations = deep_combinations.data();
    deep_nested_fixture.descriptor.load_combination_count = deep_combinations.size();
    const structural::model_ir::Model deep_nested_model(deep_nested_fixture.descriptor);
    expect_status(
        [&deep_nested_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                deep_nested_model, "deep0", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "nested combination deeper than eight must fail closed");

    structural::tests::ModelIrAssemblyFixture expanded_nested_fixture;
    std::array<sa_load_combination_term_v1, 64> expanded_leaf_terms {};
    expanded_leaf_terms.fill({
        SA_ABI_V1_1,
        static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
        structural::tests::text("lp"),
        SA_LOAD_REF_PATTERN,
        0U,
        1.0,
    });
    const std::array<sa_load_combination_term_v1, 2> expanded_root_terms {{
        {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            structural::tests::text("expanded_leaf"),
            SA_LOAD_REF_COMBINATION,
            0U,
            1.0,
        },
        {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_term_v1)),
            structural::tests::text("lp2"),
            SA_LOAD_REF_PATTERN,
            0U,
            1.0,
        },
    }};
    const std::array<sa_load_combination_descriptor_v1, 2> expanded_combinations {{
        {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_descriptor_v1)),
            structural::tests::entity("expanded_leaf", 0U),
            expanded_leaf_terms.data(),
            expanded_leaf_terms.size(),
        },
        {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_load_combination_descriptor_v1)),
            structural::tests::entity("expanded_root", 1U),
            expanded_root_terms.data(),
            expanded_root_terms.size(),
        },
    }};
    expanded_nested_fixture.descriptor.load_pattern_count = 2U;
    expanded_nested_fixture.descriptor.load_combinations = expanded_combinations.data();
    expanded_nested_fixture.descriptor.load_combination_count = expanded_combinations.size();
    const structural::model_ir::Model expanded_nested_model(expanded_nested_fixture.descriptor);
    expect_status(
        [&expanded_nested_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                expanded_nested_model, "expanded_root", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "nested combination with more than 64 expanded pattern terms must fail closed");

    structural::tests::ModelIrAssemblyFixture short_combination_fixture;
    short_combination_fixture.enable_linear_combination();
    short_combination_fixture.load_combinations[0].term_count = 1U;
    const structural::model_ir::Model short_combination_model(
        short_combination_fixture.descriptor);
    expect_status(
        [&short_combination_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                short_combination_model, "combo", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "combination with fewer than two terms must fail closed");

    structural::tests::ModelIrAssemblyFixture oversized_combination_fixture;
    oversized_combination_fixture.enable_linear_combination();
    std::array<sa_load_combination_term_v1, 65> oversized_terms {};
    oversized_terms.fill(oversized_combination_fixture.load_combination_terms[0]);
    oversized_combination_fixture.load_combinations[0].terms = oversized_terms.data();
    oversized_combination_fixture.load_combinations[0].term_count = oversized_terms.size();
    const structural::model_ir::Model oversized_combination_model(
        oversized_combination_fixture.descriptor);
    expect_status(
        [&oversized_combination_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                oversized_combination_model, "combo", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "combination with more than 64 direct terms must fail closed");

    structural::tests::ModelIrAssemblyFixture duplicate_term_fixture;
    duplicate_term_fixture.enable_linear_combination();
    duplicate_term_fixture.load_combination_terms[1].ref_id = structural::tests::text("lp");
    const structural::model_ir::Model duplicate_term_model(duplicate_term_fixture.descriptor);
    expect_status(
        [&duplicate_term_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                duplicate_term_model, "combo", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "combination with duplicate patterns must fail closed");

    structural::tests::ModelIrAssemblyFixture zero_factor_fixture;
    zero_factor_fixture.enable_linear_combination();
    zero_factor_fixture.load_combination_terms[1].factor = 0.0;
    const structural::model_ir::Model zero_factor_model(zero_factor_fixture.descriptor);
    expect_status(
        [&zero_factor_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                zero_factor_model, "combo", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "combination with a zero factor must fail closed");

    structural::tests::ModelIrAssemblyFixture ambiguous_fixture;
    ambiguous_fixture.enable_linear_combination();
    ambiguous_fixture.load_combinations[0].identity.id = structural::tests::text("lp");
    const structural::model_ir::Model ambiguous_model(ambiguous_fixture.descriptor);
    expect_status(
        [&ambiguous_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                ambiguous_model, "lp", displacement, direction));
        },
        SA_ERR_INVALID_ARGUMENT,
        "cross-family selector ambiguity must fail closed");

    structural::tests::ModelIrAssemblyFixture scaled_overflow_fixture;
    scaled_overflow_fixture.enable_linear_combination();
    scaled_overflow_fixture.load_combination_terms[0].factor =
        std::numeric_limits<double>::max();
    const structural::model_ir::Model scaled_overflow_model(
        scaled_overflow_fixture.descriptor);
    expect_status(
        [&scaled_overflow_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                scaled_overflow_model, "combo", displacement, direction));
        },
        SA_ERR_RESIDUAL_LIMIT,
        "combination scaling overflow must use residual-limit taxonomy");

    expect_status(
        [&model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                model, "missing", displacement, direction));
        },
        SA_ERR_INVALID_ARGUMENT,
        "unknown load pattern must fail");
    auto invalid_state = displacement;
    invalid_state[0] = 1.0;
    expect_status(
        [&model, &invalid_state, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                model, "lp", invalid_state, direction));
        },
        SA_ERR_INVALID_ARGUMENT,
        "nonzero homogeneous constrained state must fail");
    expect_status(
        [&model, &direction] {
            const std::array<double, 17> short_state {};
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                model, "lp", short_state, direction));
        },
        SA_ERR_INVALID_ARGUMENT,
        "state vector length mismatch must fail");
    auto non_finite_state = displacement;
    non_finite_state[6] = std::numeric_limits<double>::quiet_NaN();
    expect_status(
        [&model, &non_finite_state, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                model, "lp", non_finite_state, direction));
        },
        SA_ERR_INVALID_ARGUMENT,
        "non-finite state must fail");
    auto overflowing_state = displacement;
    overflowing_state[7] = std::numeric_limits<double>::max();
    expect_status(
        [&model, &overflowing_state, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                model, "lp", overflowing_state, direction));
        },
        SA_ERR_RESIDUAL_LIMIT,
        "non-finite element response must use residual-limit taxonomy");

    structural::tests::ModelIrAssemblyFixture offset_fixture;
    offset_fixture.elements[0].offset_i_global_m[0] = 0.1;
    const structural::model_ir::Model offset_model(offset_fixture.descriptor);
    expect_status(
        [&offset_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                offset_model, "lp", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "unsupported rigid offset must fail closed");

    structural::tests::ModelIrAssemblyFixture constraint_fixture;
    const std::array<sa_prescribed_value_v1, 1> prescribed {{
        {SA_DOF_UX, 0U, 0.001},
    }};
    constraint_fixture.constraints[0].prescribed_values = prescribed.data();
    constraint_fixture.constraints[0].prescribed_value_count = prescribed.size();
    const structural::model_ir::Model constraint_model(constraint_fixture.descriptor);
    expect_status(
        [&constraint_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                constraint_model, "lp", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "nonzero prescribed constraint must fail closed");

    structural::tests::ModelIrAssemblyFixture self_weight_fixture;
    self_weight_fixture.load_patterns[0].self_weight[2] = -9.81;
    const structural::model_ir::Model self_weight_model(self_weight_fixture.descriptor);
    expect_status(
        [&self_weight_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                self_weight_model, "lp", displacement, direction));
        },
        SA_ERR_ANALYSIS_NOT_READY,
        "unimplemented self weight must fail closed");

    structural::tests::ModelIrAssemblyFixture load_overflow_fixture;
    load_overflow_fixture.nodal_loads[0].components_si[0] =
        std::numeric_limits<double>::max();
    load_overflow_fixture.nodal_loads[1].node_id = structural::tests::text("n1");
    load_overflow_fixture.nodal_loads[1].components_si[0] =
        std::numeric_limits<double>::max();
    const structural::model_ir::Model load_overflow_model(load_overflow_fixture.descriptor);
    expect_status(
        [&load_overflow_model, &displacement, &direction] {
            static_cast<void>(structural::assembly::assemble_model_ir_linear_reference(
                load_overflow_model, "lp", displacement, direction));
        },
        SA_ERR_RESIDUAL_LIMIT,
        "non-finite nodal-load accumulation must use residual-limit taxonomy");
    return EXIT_SUCCESS;
}
