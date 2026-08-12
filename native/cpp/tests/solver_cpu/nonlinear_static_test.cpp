#include "nonlinear_static.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

[[nodiscard]] bool near(const double actual, const double expected) {
    return std::abs(actual - expected) <= 1.0e-15;
}

[[nodiscard]] structural::solver_cpu::NonlinearStaticConfig config() {
    return {3U, 1.0e-7, 60U, 0.04, 0.5, 0.03125, 1.0};
}

[[nodiscard]] bool three_story_case_matches_the_frozen_legacy_result() {
    constexpr std::array stiffness {1.0e8, 9.0e7, 8.0e7};
    constexpr std::array height {3.0, 3.0, 3.0};
    constexpr std::array axial {1.0e6, 8.0e5, 6.0e5};
    constexpr std::array yield_drift {0.02, 0.02, 0.02};
    constexpr std::array load {10'000.0, 8'000.0, 6'000.0};
    const structural::solver_cpu::NonlinearStaticInputs inputs {
        stiffness,
        height,
        axial,
        yield_drift,
        load,
    };
    const auto result = structural::solver_cpu::solve_nonlinear_static(config(), inputs);
    constexpr std::array expected_displacement {
        0.0002400000000001004,
        0.000395555555555692,
        0.0004705555555556994,
    };

    CHECK(result.converged);
    CHECK(result.iterations == 6U);
    CHECK(near(result.residual_inf, 6.79574441164732e-9));
    CHECK(near(result.residual_l2, 7.31922742469327e-9));
    CHECK(near(result.max_abs_displacement_m, 0.0004705555555556994));
    CHECK(near(result.top_displacement_m, 0.0004705555555556994));
    CHECK(near(result.base_shear_kn, 24.00000000001004));
    CHECK(result.plastic_story_count == 0U);
    CHECK(result.line_search_backtracks == 0U);
    CHECK(result.displacement_m.size() == expected_displacement.size());
    for (std::size_t index = 0U; index < expected_displacement.size(); ++index) {
        CHECK(near(result.displacement_m[index], expected_displacement[index]));
    }
    return true;
}

[[nodiscard]] bool one_story_case_is_supported_and_deterministic() {
    constexpr std::array stiffness {1.0e7};
    constexpr std::array height {3.0};
    constexpr std::array axial {0.0};
    constexpr std::array yield_drift {0.01};
    constexpr std::array load {1'000.0};
    const structural::solver_cpu::NonlinearStaticInputs inputs {
        stiffness,
        height,
        axial,
        yield_drift,
        load,
    };
    auto one_story = config();
    one_story.story_count = 1U;
    const auto first = structural::solver_cpu::solve_nonlinear_static(one_story, inputs);
    const auto second = structural::solver_cpu::solve_nonlinear_static(one_story, inputs);
    CHECK(first.converged);
    CHECK(first.iterations == 2U);
    CHECK(first.displacement_m == second.displacement_m);
    CHECK(near(first.top_displacement_m, 0.0001));
    return true;
}

[[nodiscard]] bool same_state(
    const structural::solver_cpu::NonlinearStaticExecutionState& left,
    const structural::solver_cpu::NonlinearStaticExecutionState& right) {
    return left.status == right.status && left.iterations == right.iterations
        && left.line_search_backtracks == right.line_search_backtracks
        && left.residual_inf == right.residual_inf && left.residual_l2 == right.residual_l2
        && left.max_abs_displacement_m == right.max_abs_displacement_m
        && left.top_displacement_m == right.top_displacement_m
        && left.base_shear_kn == right.base_shear_kn
        && left.plastic_story_count == right.plastic_story_count
        && left.displacement_m == right.displacement_m;
}

[[nodiscard]] bool restart_boundaries_are_complete_and_bitwise_stable() {
    using structural::solver_cpu::NonlinearStaticExecutionStatus;
    constexpr std::array stiffness {1.0e8, 9.0e7, 8.0e7};
    constexpr std::array height {3.0, 3.0, 3.0};
    constexpr std::array axial {1.0e6, 8.0e5, 6.0e5};
    constexpr std::array yield_drift {0.02, 0.02, 0.02};
    constexpr std::array load {10'000.0, 8'000.0, 6'000.0};
    const structural::solver_cpu::NonlinearStaticInputs inputs {
        stiffness,
        height,
        axial,
        yield_drift,
        load,
    };
    auto direct = structural::solver_cpu::begin_nonlinear_static(config(), inputs);
    auto segmented = direct;
    const auto initial = segmented;
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, 0U, segmented);
    CHECK(same_state(segmented, initial));
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, 1U, segmented);
    CHECK(segmented.status == NonlinearStaticExecutionStatus::active);
    CHECK(segmented.iterations == 1U);
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, 2U, segmented);
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, UINT32_MAX, segmented);
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, UINT32_MAX, direct);
    CHECK(same_state(segmented, direct));
    CHECK(direct.status == NonlinearStaticExecutionStatus::converged);
    const auto terminal = direct;
    structural::solver_cpu::advance_nonlinear_static(config(), inputs, 1U, direct);
    CHECK(same_state(direct, terminal));
    const auto projected = structural::solver_cpu::nonlinear_static_result(direct);
    const auto one_shot = structural::solver_cpu::solve_nonlinear_static(config(), inputs);
    CHECK(projected.displacement_m == one_shot.displacement_m);
    CHECK(projected.iterations == one_shot.iterations);
    CHECK(projected.residual_inf == one_shot.residual_inf);

    auto corrupt = structural::solver_cpu::begin_nonlinear_static(config(), inputs);
    corrupt.residual_inf = std::numeric_limits<double>::quiet_NaN();
    bool rejected = false;
    try {
        structural::solver_cpu::advance_nonlinear_static(config(), inputs, 0U, corrupt);
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    CHECK(rejected);

    auto exhausted_config = config();
    exhausted_config.max_iter = 1U;
    auto exhausted =
        structural::solver_cpu::begin_nonlinear_static(exhausted_config, inputs);
    structural::solver_cpu::advance_nonlinear_static(
        exhausted_config, inputs, UINT32_MAX, exhausted);
    CHECK(exhausted.status == NonlinearStaticExecutionStatus::nonconverged);
    CHECK(exhausted.iterations == 1U);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        three_story_case_matches_the_frozen_legacy_result,
        one_story_case_is_supported_and_deterministic,
        restart_boundaries_are_complete_and_bitwise_stable,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
