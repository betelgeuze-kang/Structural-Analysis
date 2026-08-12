#include "nonlinear_ndtha.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
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

[[nodiscard]] structural::solver_cpu::NonlinearNdthaConfig config() {
    return {
        2U,
        3U,
        0.01,
        0.25,
        0.5,
        1.0e-5,
        16U,
        0.82,
        0.6,
        120U,
        0.5,
        0.03125,
        0.2,
        1.0,
        10.0,
    };
}

struct InputStorage {
    std::array<double, 2> stiffness {1.0e8, 9.0e7};
    std::array<double, 2> height {3.0, 3.0};
    std::array<double, 2> axial {1.0e6, 8.0e5};
    std::array<double, 2> yield_drift {0.02, 0.02};
    std::array<double, 2> mass {10'000.0, 8'000.0};
    std::array<double, 2> damping {1'000.0, 900.0};
    std::array<double, 2> floor_load {10'000.0, 8'000.0};
    std::array<double, 3> acceleration {0.0, 0.01, -0.005};

    [[nodiscard]] structural::solver_cpu::NonlinearNdthaInputs views() const {
        return {
            stiffness,
            height,
            axial,
            yield_drift,
            mass,
            damping,
            floor_load,
            acceleration,
        };
    }
};

[[nodiscard]] bool frozen_legacy_case_matches_every_response_channel() {
    const InputStorage storage;
    const auto result = structural::solver_cpu::solve_nonlinear_ndtha(config(), storage.views());
    constexpr std::array expected_top {
        4.084273705964167e-7,
        2.008674095445957e-6,
        3.795754248884991e-6,
    };
    constexpr std::array expected_drift {
        1.1677310711126211e-5,
        5.301851826285648e-5,
        8.560401406754784e-5,
    };
    constexpr std::array expected_base_shear {
        0.035031932133378636,
        0.15905555478856942,
        0.2568120422026436,
    };
    constexpr std::array expected_residual {
        9.752318419486983e-8,
        2.736757522825428e-7,
        4.408786935528042e-8,
    };
    constexpr std::array expected_story_drift {
        8.560401406754784e-5,
        4.0921127561951836e-5,
    };

    CHECK(result.converged_all_steps);
    CHECK(!result.collapsed);
    CHECK(result.collapse_step == -1);
    CHECK(result.collapse_time_s == 0.0);
    CHECK(result.collapse_drift_ratio_pct == 0.0);
    CHECK(result.collapse_top_displacement_m == 0.0);
    CHECK(result.step_count_completed == 3U);
    CHECK(result.max_plastic_story_count == 0U);
    CHECK(near(result.max_drift_ratio_pct, 8.560401406754784e-5));
    CHECK(near(result.avg_step_iterations, 1.0));
    CHECK(near(result.residual_top_displacement_m, 3.795754248884991e-6));
    CHECK(near(result.residual_drift_ratio_pct, 8.560401406754784e-5));
    CHECK(result.total_line_search_backtracks == 0U);
    CHECK(result.response.top_displacement_m.size() == expected_top.size());
    for (std::size_t index = 0U; index < expected_top.size(); ++index) {
        CHECK(near(result.response.top_displacement_m[index], expected_top[index]));
        CHECK(near(result.response.drift_ratio_pct[index], expected_drift[index]));
        CHECK(near(result.response.base_shear_kn[index], expected_base_shear[index]));
        CHECK(near(result.response.core_drift_pct[index], expected_drift[index]));
        CHECK(near(result.response.core_shear_kn[index], expected_base_shear[index]));
        CHECK(result.response.step_converged[index] == 1U);
        CHECK(result.response.step_iterations[index] == 1U);
        CHECK(result.response.step_plastic_story_count[index] == 0U);
        CHECK(near(result.response.step_residual_inf[index], expected_residual[index]));
    }
    for (std::size_t index = 0U; index < expected_story_drift.size(); ++index) {
        CHECK(near(result.response.story_drift_envelope_pct[index], expected_story_drift[index]));
        CHECK(near(result.response.final_story_drift_pct[index], expected_story_drift[index]));
    }
    return true;
}

[[nodiscard]] bool numerical_nonconvergence_preserves_the_previous_state() {
    const InputStorage storage;
    auto bounded = config();
    bounded.max_step_iterations = 1U;
    bounded.newton_max_iter = 1U;
    bounded.tolerance = 1.0e-30;
    const auto result = structural::solver_cpu::solve_nonlinear_ndtha(bounded, storage.views());
    CHECK(!result.converged_all_steps);
    CHECK(!result.collapsed);
    CHECK(result.step_count_completed == 1U);
    CHECK(result.response.step_converged[0] == 0U);
    CHECK(result.residual_top_displacement_m == 0.0);
    CHECK(result.residual_drift_ratio_pct == 0.0);
    return true;
}

[[nodiscard]] bool collapse_is_a_deterministic_physical_termination() {
    const InputStorage storage;
    auto collapse = config();
    collapse.collapse_drift_threshold_pct = 1.0e-6;
    const auto result = structural::solver_cpu::solve_nonlinear_ndtha(collapse, storage.views());
    CHECK(!result.converged_all_steps);
    CHECK(result.collapsed);
    CHECK(result.collapse_step == 0);
    CHECK(result.step_count_completed == 1U);
    CHECK(near(result.collapse_drift_ratio_pct, 1.1677310711126211e-5));
    CHECK(near(result.collapse_top_displacement_m, 4.084273705964167e-7));
    return true;
}

} // namespace

int main() {
    const std::array tests {
        frozen_legacy_case_matches_every_response_channel,
        numerical_nonconvergence_preserves_the_previous_state,
        collapse_is_a_deterministic_physical_termination,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
