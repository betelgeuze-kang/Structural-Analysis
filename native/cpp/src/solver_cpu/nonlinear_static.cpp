#include "nonlinear_static.hpp"
#include "story_frame.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace structural::solver_cpu {
namespace {

[[nodiscard]] bool spans_match(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs) {
    const auto expected = static_cast<std::size_t>(config.story_count);
    return expected > 0U && inputs.story_stiffness_n_per_m.size() == expected
        && inputs.story_height_m.size() == expected
        && inputs.story_axial_n.size() == expected
        && inputs.story_yield_drift_m.size() == expected
        && inputs.floor_load_n.size() == expected;
}

struct WorkBuffers {
    explicit WorkBuffers(const std::size_t count)
        : internal_force(count, 0.0),
          lower(count - 1U, 0.0),
          diagonal(count, 0.0),
          upper(count - 1U, 0.0),
          residual(count, 0.0),
          increment(count, 0.0),
          trial(count, 0.0) {}

    std::vector<double> internal_force;
    std::vector<double> lower;
    std::vector<double> diagonal;
    std::vector<double> upper;
    std::vector<double> residual;
    std::vector<double> increment;
    std::vector<double> trial;
};

[[nodiscard]] detail::StoryFrameConstitutiveConfig constitutive_config(
    const NonlinearStaticConfig& config) {
    return {config.hardening_ratio, config.pdelta_factor};
}

[[nodiscard]] detail::StoryFrameInputs story_inputs(const NonlinearStaticInputs& inputs) {
    return {
        inputs.story_stiffness_n_per_m,
        inputs.story_height_m,
        inputs.story_axial_n,
        inputs.story_yield_drift_m,
    };
}

void update_derived_state(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs,
    WorkBuffers& work,
    NonlinearStaticExecutionState& state) {
    const auto assembly = detail::assemble_story_frame(
        state.displacement_m,
        constitutive_config(config),
        story_inputs(inputs),
        work.internal_force,
        work.lower,
        work.diagonal,
        work.upper);
    for (std::size_t index = 0U; index < state.displacement_m.size(); ++index) {
        work.residual[index] = inputs.floor_load_n[index] - work.internal_force[index];
    }
    state.residual_inf = detail::norm_inf(work.residual);
    state.residual_l2 = detail::norm_l2(work.residual);
    state.max_abs_displacement_m = 0.0;
    for (const auto value : state.displacement_m) {
        state.max_abs_displacement_m =
            std::max(state.max_abs_displacement_m, std::abs(value));
    }
    state.top_displacement_m = state.displacement_m.back();
    state.base_shear_kn = assembly.base_shear_kn;
    state.plastic_story_count = assembly.plastic_story_count;
}

[[nodiscard]] bool same_bits(const double left, const double right) {
    return std::bit_cast<std::uint64_t>(left) == std::bit_cast<std::uint64_t>(right);
}

void validate_state(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs,
    const NonlinearStaticExecutionState& state) {
    const auto count = static_cast<std::size_t>(config.story_count);
    if (!spans_match(config, inputs) || state.displacement_m.size() != count
        || state.iterations > config.max_iter
        || !std::all_of(state.displacement_m.begin(), state.displacement_m.end(), [](const double value) {
               return std::isfinite(value);
           })) {
        throw std::invalid_argument("nonlinear static restart state shape is invalid");
    }
    WorkBuffers work(count);
    auto expected = state;
    update_derived_state(config, inputs, work, expected);
    const bool derived_valid = same_bits(state.residual_inf, expected.residual_inf)
        && same_bits(state.residual_l2, expected.residual_l2)
        && same_bits(state.max_abs_displacement_m, expected.max_abs_displacement_m)
        && same_bits(state.top_displacement_m, expected.top_displacement_m)
        && same_bits(state.base_shear_kn, expected.base_shear_kn)
        && state.plastic_story_count == expected.plastic_story_count;
    const bool finite = std::isfinite(state.residual_inf) && std::isfinite(state.residual_l2)
        && std::isfinite(state.max_abs_displacement_m)
        && std::isfinite(state.top_displacement_m) && std::isfinite(state.base_shear_kn);
    bool status_valid = false;
    switch (state.status) {
    case NonlinearStaticExecutionStatus::active:
        status_valid = state.iterations < config.max_iter;
        break;
    case NonlinearStaticExecutionStatus::converged:
        status_valid = state.iterations > 0U && state.iterations <= config.max_iter
            && state.residual_inf <= config.tolerance;
        break;
    case NonlinearStaticExecutionStatus::nonconverged:
        status_valid = state.iterations > 0U && state.iterations <= config.max_iter;
        break;
    }
    if (!derived_valid || !finite || !status_valid) {
        throw std::invalid_argument("nonlinear static restart state is inconsistent");
    }
}

} // namespace

void validate_nonlinear_static_problem(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs) {
    constexpr std::uint32_t maximum_story_count = 1'000'000U;
    const std::array scalar_values {
        config.tolerance,
        config.hardening_ratio,
        config.line_search_decay,
        config.line_search_min,
        config.pdelta_factor,
    };
    if (!spans_match(config, inputs) || config.story_count > maximum_story_count
        || config.max_iter == 0U
        || std::any_of(scalar_values.begin(), scalar_values.end(), [](const double value) {
               return !std::isfinite(value);
           })
        || config.tolerance <= 0.0 || config.hardening_ratio < 0.0
        || config.hardening_ratio > 1.0 || config.line_search_decay <= 0.0
        || config.line_search_decay >= 1.0 || config.line_search_min <= 0.0
        || config.line_search_min > 1.0 || config.pdelta_factor < 0.0) {
        throw std::invalid_argument("nonlinear static problem is outside the bounded domain");
    }
    const std::array values {
        inputs.story_stiffness_n_per_m,
        inputs.story_height_m,
        inputs.story_axial_n,
        inputs.story_yield_drift_m,
        inputs.floor_load_n,
    };
    for (const auto input : values) {
        if (!std::all_of(input.begin(), input.end(), [](const double value) {
                return std::isfinite(value);
            })) {
            throw std::invalid_argument("nonlinear static input contains a non-finite value");
        }
    }
    if (std::any_of(
            inputs.story_stiffness_n_per_m.begin(),
            inputs.story_stiffness_n_per_m.end(),
            [](const double value) { return value <= 0.0; })
        || std::any_of(
            inputs.story_height_m.begin(),
            inputs.story_height_m.end(),
            [](const double value) { return value <= 0.0; })) {
        throw std::invalid_argument("nonlinear static stiffness and height must be positive");
    }
}

NonlinearStaticExecutionState begin_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs) {
    validate_nonlinear_static_problem(config, inputs);
    const auto count = static_cast<std::size_t>(config.story_count);
    WorkBuffers work(count);
    NonlinearStaticExecutionState state;
    state.displacement_m.assign(count, 0.0);
    update_derived_state(config, inputs, work, state);
    return state;
}

void advance_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs,
    std::uint32_t iteration_budget,
    NonlinearStaticExecutionState& state) {
    validate_state(config, inputs, state);
    if (state.status != NonlinearStaticExecutionStatus::active || iteration_budget == 0U) {
        return;
    }

    const auto count = static_cast<std::size_t>(config.story_count);
    const auto constitutive = constitutive_config(config);
    const auto frame_inputs = story_inputs(inputs);
    WorkBuffers work(count);
    while (iteration_budget > 0U && state.status == NonlinearStaticExecutionStatus::active) {
        const auto iteration = state.iterations + 1U;
        static_cast<void>(detail::assemble_story_frame(
            state.displacement_m,
            constitutive,
            frame_inputs,
            work.internal_force,
            work.lower,
            work.diagonal,
            work.upper));
        for (std::size_t index = 0U; index < count; ++index) {
            work.residual[index] = inputs.floor_load_n[index] - work.internal_force[index];
        }
        const double residual_inf = detail::norm_inf(work.residual);
        if (std::isfinite(residual_inf) && residual_inf <= config.tolerance) {
            state.iterations = iteration;
            state.status = NonlinearStaticExecutionStatus::converged;
            update_derived_state(config, inputs, work, state);
            break;
        }
        if (!detail::solve_tridiagonal(
                work.lower, work.diagonal, work.upper, work.residual, work.increment)) {
            state.iterations = iteration;
            state.status = NonlinearStaticExecutionStatus::nonconverged;
            update_derived_state(config, inputs, work, state);
            break;
        }

        const double baseline = std::max(residual_inf, detail::kStoryFrameEpsilon);
        double scale = 1.0;
        bool accepted = false;
        std::uint32_t local_backtracks = 0U;
        while (scale >= config.line_search_min) {
            for (std::size_t index = 0U; index < count; ++index) {
                work.trial[index] = state.displacement_m[index] + scale * work.increment[index];
            }
            static_cast<void>(detail::assemble_story_frame(
                work.trial,
                constitutive,
                frame_inputs,
                work.internal_force,
                work.lower,
                work.diagonal,
                work.upper));
            for (std::size_t index = 0U; index < count; ++index) {
                work.residual[index] = inputs.floor_load_n[index] - work.internal_force[index];
            }
            const double trial_norm = detail::norm_inf(work.residual);
            if (std::isfinite(trial_norm) && trial_norm < baseline) {
                state.displacement_m = work.trial;
                accepted = true;
                break;
            }
            scale *= config.line_search_decay;
            ++local_backtracks;
        }
        state.line_search_backtracks += local_backtracks;
        state.iterations = iteration;
        update_derived_state(config, inputs, work, state);
        if (!accepted) {
            state.status = NonlinearStaticExecutionStatus::nonconverged;
            break;
        }
        if (state.iterations == config.max_iter) {
            state.status = state.residual_inf <= config.tolerance
                ? NonlinearStaticExecutionStatus::converged
                : NonlinearStaticExecutionStatus::nonconverged;
            break;
        }
        --iteration_budget;
    }
}

NonlinearStaticResult nonlinear_static_result(const NonlinearStaticExecutionState& state) {
    return {
        state.status == NonlinearStaticExecutionStatus::converged,
        state.iterations,
        state.residual_inf,
        state.residual_l2,
        state.max_abs_displacement_m,
        state.top_displacement_m,
        state.base_shear_kn,
        state.plastic_story_count,
        state.line_search_backtracks,
        state.displacement_m,
    };
}

NonlinearStaticResult solve_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs) {
    auto state = begin_nonlinear_static(config, inputs);
    advance_nonlinear_static(config, inputs, UINT32_MAX, state);
    return nonlinear_static_result(state);
}

} // namespace structural::solver_cpu
