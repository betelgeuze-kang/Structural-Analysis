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
