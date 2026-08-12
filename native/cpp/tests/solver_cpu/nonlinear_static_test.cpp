#include "nonlinear_static.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <iostream>

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

} // namespace

int main() {
    const std::array tests {
        three_story_case_matches_the_frozen_legacy_result,
        one_story_case_is_supported_and_deterministic,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
