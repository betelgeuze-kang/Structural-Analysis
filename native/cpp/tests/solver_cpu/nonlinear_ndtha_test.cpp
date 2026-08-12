#include "nonlinear_ndtha.hpp"

#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <vector>

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

[[nodiscard]] bool exact_double(const double left, const double right) {
    return std::bit_cast<std::uint64_t>(left) == std::bit_cast<std::uint64_t>(right);
}

[[nodiscard]] bool exact_doubles(
    const std::vector<double>& left,
    const std::vector<double>& right) {
    if (left.size() != right.size()) {
        return false;
    }
    for (std::size_t index = 0U; index < left.size(); ++index) {
        if (!exact_double(left[index], right[index])) {
            return false;
        }
    }
    return true;
}

[[nodiscard]] bool exact_response(
    const structural::solver_cpu::NonlinearNdthaResponse& left,
    const structural::solver_cpu::NonlinearNdthaResponse& right) {
    return exact_doubles(left.top_displacement_m, right.top_displacement_m)
        && exact_doubles(left.drift_ratio_pct, right.drift_ratio_pct)
        && exact_doubles(left.base_shear_kn, right.base_shear_kn)
        && exact_doubles(left.core_drift_pct, right.core_drift_pct)
        && exact_doubles(left.core_shear_kn, right.core_shear_kn)
        && left.step_converged == right.step_converged
        && left.step_iterations == right.step_iterations
        && left.step_plastic_story_count == right.step_plastic_story_count
        && exact_doubles(left.step_residual_inf, right.step_residual_inf)
        && exact_doubles(left.story_drift_envelope_pct, right.story_drift_envelope_pct)
        && exact_doubles(left.final_story_drift_pct, right.final_story_drift_pct);
}

[[nodiscard]] bool exact_result(
    const structural::solver_cpu::NonlinearNdthaResult& left,
    const structural::solver_cpu::NonlinearNdthaResult& right) {
    return left.converged_all_steps == right.converged_all_steps
        && left.collapsed == right.collapsed && left.collapse_step == right.collapse_step
        && exact_double(left.collapse_time_s, right.collapse_time_s)
        && exact_double(left.collapse_drift_ratio_pct, right.collapse_drift_ratio_pct)
        && exact_double(left.collapse_top_displacement_m, right.collapse_top_displacement_m)
        && left.step_count_completed == right.step_count_completed
        && left.max_plastic_story_count == right.max_plastic_story_count
        && exact_double(left.max_drift_ratio_pct, right.max_drift_ratio_pct)
        && exact_double(left.avg_step_iterations, right.avg_step_iterations)
        && exact_double(
            left.residual_top_displacement_m, right.residual_top_displacement_m)
        && exact_double(left.residual_drift_ratio_pct, right.residual_drift_ratio_pct)
        && left.total_line_search_backtracks == right.total_line_search_backtracks
        && exact_response(left.response, right.response);
}

[[nodiscard]] bool exact_state(
    const structural::solver_cpu::NonlinearNdthaExecutionState& left,
    const structural::solver_cpu::NonlinearNdthaExecutionState& right) {
    return left.next_step == right.next_step && left.status == right.status
        && left.collapse_step == right.collapse_step
        && exact_double(left.collapse_time_s, right.collapse_time_s)
        && exact_double(left.collapse_drift_ratio_pct, right.collapse_drift_ratio_pct)
        && exact_double(left.collapse_top_displacement_m, right.collapse_top_displacement_m)
        && left.max_plastic_story_count == right.max_plastic_story_count
        && exact_double(left.max_drift_ratio_pct, right.max_drift_ratio_pct)
        && left.adaptive_iteration_sum == right.adaptive_iteration_sum
        && left.total_line_search_backtracks == right.total_line_search_backtracks
        && exact_doubles(left.displacement_m, right.displacement_m)
        && exact_doubles(left.velocity_m_per_s, right.velocity_m_per_s)
        && exact_doubles(left.acceleration_m_per_s2, right.acceleration_m_per_s2)
        && exact_response(left.response, right.response);
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

[[nodiscard]] bool segmented_resume_is_bitwise_identical_to_one_shot() {
    const InputStorage storage;
    const auto expected = structural::solver_cpu::solve_nonlinear_ndtha(
        config(), storage.views());

    auto state = structural::solver_cpu::make_nonlinear_ndtha_initial_state(config());
    structural::solver_cpu::advance_nonlinear_ndtha(config(), storage.views(), 0U, state);
    CHECK(state.next_step == 0U);
    CHECK(state.status == structural::solver_cpu::NonlinearNdthaExecutionStatus::active);
    structural::solver_cpu::advance_nonlinear_ndtha(config(), storage.views(), 1U, state);
    CHECK(state.next_step == 1U);
    CHECK(state.status == structural::solver_cpu::NonlinearNdthaExecutionStatus::active);

    auto bulk_resume = state;
    structural::solver_cpu::advance_nonlinear_ndtha(
        config(), storage.views(), 100U, bulk_resume);
    CHECK(bulk_resume.status
        == structural::solver_cpu::NonlinearNdthaExecutionStatus::completed);
    const auto bulk_result = structural::solver_cpu::finalize_nonlinear_ndtha(
        config(), bulk_resume);
    CHECK(exact_result(bulk_result, expected));

    auto single_step_resume = state;
    structural::solver_cpu::advance_nonlinear_ndtha(
        config(), storage.views(), 1U, single_step_resume);
    structural::solver_cpu::advance_nonlinear_ndtha(
        config(), storage.views(), 1U, single_step_resume);
    const auto single_step_result = structural::solver_cpu::finalize_nonlinear_ndtha(
        config(), single_step_resume);
    CHECK(exact_result(single_step_result, expected));
    CHECK(exact_state(bulk_resume, single_step_resume));
    return true;
}

[[nodiscard]] bool terminal_resume_is_idempotent_and_bitwise_identical() {
    const InputStorage storage;
    auto collapse = config();
    collapse.collapse_drift_threshold_pct = 1.0e-6;
    const auto expected_collapse = structural::solver_cpu::solve_nonlinear_ndtha(
        collapse, storage.views());
    auto collapsed_state = structural::solver_cpu::make_nonlinear_ndtha_initial_state(collapse);
    structural::solver_cpu::advance_nonlinear_ndtha(
        collapse, storage.views(), 1U, collapsed_state);
    CHECK(collapsed_state.status
        == structural::solver_cpu::NonlinearNdthaExecutionStatus::collapsed);
    const auto collapsed_snapshot = collapsed_state;
    structural::solver_cpu::advance_nonlinear_ndtha(
        collapse, storage.views(), 100U, collapsed_state);
    CHECK(exact_state(collapsed_state, collapsed_snapshot));
    const auto resumed_collapse = structural::solver_cpu::finalize_nonlinear_ndtha(
        collapse, collapsed_state);
    CHECK(exact_result(resumed_collapse, expected_collapse));

    auto bounded = config();
    bounded.max_step_iterations = 1U;
    bounded.newton_max_iter = 1U;
    bounded.tolerance = 1.0e-30;
    const auto expected_failure = structural::solver_cpu::solve_nonlinear_ndtha(
        bounded, storage.views());
    auto failed_state = structural::solver_cpu::make_nonlinear_ndtha_initial_state(bounded);
    structural::solver_cpu::advance_nonlinear_ndtha(
        bounded, storage.views(), 1U, failed_state);
    CHECK(failed_state.status
        == structural::solver_cpu::NonlinearNdthaExecutionStatus::nonconverged);
    const auto failed_snapshot = failed_state;
    structural::solver_cpu::advance_nonlinear_ndtha(
        bounded, storage.views(), 100U, failed_state);
    CHECK(exact_state(failed_state, failed_snapshot));
    const auto resumed_failure = structural::solver_cpu::finalize_nonlinear_ndtha(
        bounded, failed_state);
    CHECK(exact_result(resumed_failure, expected_failure));
    return true;
}

[[nodiscard]] bool invalid_resume_state_is_rejected_without_mutation() {
    const InputStorage storage;
    auto state = structural::solver_cpu::make_nonlinear_ndtha_initial_state(config());
    structural::solver_cpu::advance_nonlinear_ndtha(config(), storage.views(), 1U, state);
    const auto snapshot = state;

    auto short_inputs = storage.views();
    short_inputs.acceleration_g = std::span<const double>(storage.acceleration.data(), 2U);
    bool input_rejected = false;
    try {
        structural::solver_cpu::advance_nonlinear_ndtha(
            config(), short_inputs, 1U, state);
    } catch (const std::invalid_argument&) {
        input_rejected = true;
    }
    CHECK(input_rejected);
    CHECK(exact_state(state, snapshot));

    auto corrupt = state;
    corrupt.response.step_iterations[2] = 1U;
    bool tail_rejected = false;
    try {
        structural::solver_cpu::advance_nonlinear_ndtha(
            config(), storage.views(), 1U, corrupt);
    } catch (const std::invalid_argument&) {
        tail_rejected = true;
    }
    CHECK(tail_rejected);

    corrupt = state;
    corrupt.status = static_cast<structural::solver_cpu::NonlinearNdthaExecutionStatus>(99U);
    bool status_rejected = false;
    try {
        static_cast<void>(structural::solver_cpu::finalize_nonlinear_ndtha(config(), corrupt));
    } catch (const std::invalid_argument&) {
        status_rejected = true;
    }
    CHECK(status_rejected);
    return true;
}

[[nodiscard]] bool shared_problem_validation_rejects_invalid_domains() {
    InputStorage nonfinite_storage;
    nonfinite_storage.stiffness[0] = std::numeric_limits<double>::quiet_NaN();
    bool nonfinite_rejected = false;
    try {
        structural::solver_cpu::validate_nonlinear_ndtha_problem(
            config(), nonfinite_storage.views());
    } catch (const std::invalid_argument&) {
        nonfinite_rejected = true;
    }
    CHECK(nonfinite_rejected);

    InputStorage negative_damping_storage;
    negative_damping_storage.damping[1] = -1.0;
    bool physical_domain_rejected = false;
    try {
        structural::solver_cpu::validate_nonlinear_ndtha_problem(
            config(), negative_damping_storage.views());
    } catch (const std::invalid_argument&) {
        physical_domain_rejected = true;
    }
    CHECK(physical_domain_rejected);

    const InputStorage storage;
    auto invalid_config = config();
    invalid_config.line_search_decay = 1.0;
    bool config_rejected = false;
    try {
        structural::solver_cpu::validate_nonlinear_ndtha_problem(
            invalid_config, storage.views());
    } catch (const std::invalid_argument&) {
        config_rejected = true;
    }
    CHECK(config_rejected);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        frozen_legacy_case_matches_every_response_channel,
        numerical_nonconvergence_preserves_the_previous_state,
        collapse_is_a_deterministic_physical_termination,
        segmented_resume_is_bitwise_identical_to_one_shot,
        terminal_resume_is_idempotent_and_bitwise_identical,
        invalid_resume_state_is_rejected_without_mutation,
        shared_problem_validation_rejects_invalid_domains,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
