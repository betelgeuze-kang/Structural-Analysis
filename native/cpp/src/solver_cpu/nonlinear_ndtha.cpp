#include "nonlinear_ndtha.hpp"

#include "story_frame.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <utility>
#include <vector>

namespace structural::solver_cpu {
namespace {

struct StepResult {
    bool converged;
    std::uint32_t adaptive_iterations;
    std::uint32_t plastic_story_count;
    double base_shear_kn;
    double residual_inf;
    std::uint32_t line_search_backtracks;
};

[[nodiscard]] bool spans_match(
    const NonlinearNdthaConfig& config,
    const NonlinearNdthaInputs& inputs) noexcept {
    const auto stories = static_cast<std::size_t>(config.story_count);
    const auto steps = static_cast<std::size_t>(config.step_count);
    return stories > 0U && steps > 0U
        && inputs.story_stiffness_n_per_m.size() == stories
        && inputs.story_height_m.size() == stories
        && inputs.story_axial_n.size() == stories
        && inputs.story_yield_drift_m.size() == stories
        && inputs.story_mass_kg.size() == stories
        && inputs.story_damping_n_s_per_m.size() == stories
        && inputs.floor_load_base_n.size() == stories
        && inputs.acceleration_g.size() == steps;
}

[[nodiscard]] StepResult solve_step(
    const NonlinearNdthaConfig& config,
    const NonlinearNdthaInputs& inputs,
    const detail::StoryFrameConstitutiveConfig& constitutive,
    const detail::StoryFrameInputs& story_inputs,
    const std::vector<double>& external_force_n,
    const std::vector<double>& previous_displacement_m,
    const std::vector<double>& previous_velocity_m_per_s,
    const std::vector<double>& previous_acceleration_m_per_s2,
    std::vector<double>& next_displacement_m,
    std::vector<double>& next_velocity_m_per_s,
    std::vector<double>& next_acceleration_m_per_s2) {
    const auto count = inputs.story_stiffness_n_per_m.size();
    const double dt = std::max(config.dt_s, detail::kStoryFrameEpsilon);
    const double beta = std::max(config.newmark_beta, detail::kStoryFrameEpsilon);
    const double gamma = std::max(config.newmark_gamma, detail::kStoryFrameEpsilon);
    const double acceleration_coefficient = 1.0 / (beta * dt * dt);
    const double damping_coefficient = gamma / (beta * dt);

    std::vector<double> predicted_displacement(count, 0.0);
    std::vector<double> predicted_velocity(count, 0.0);
    std::vector<double> trial_displacement(count, 0.0);
    std::vector<double> candidate_displacement(count, 0.0);
    std::vector<double> trial_force(count, 0.0);
    std::vector<double> internal_force(count, 0.0);
    std::vector<double> lower(count - 1U, 0.0);
    std::vector<double> diagonal(count, 0.0);
    std::vector<double> upper(count - 1U, 0.0);
    std::vector<double> effective_diagonal(count, 0.0);
    std::vector<double> residual(count, 0.0);
    std::vector<double> increment(count, 0.0);

    for (std::size_t index = 0U; index < count; ++index) {
        predicted_displacement[index] = previous_displacement_m[index]
            + dt * previous_velocity_m_per_s[index]
            + dt * dt * (0.5 - beta) * previous_acceleration_m_per_s2[index];
        predicted_velocity[index] = previous_velocity_m_per_s[index]
            + dt * (1.0 - gamma) * previous_acceleration_m_per_s2[index];
        trial_displacement[index] = previous_displacement_m[index];
    }

    double load_scale = 1.0;
    std::uint32_t adaptive_iterations = 0U;
    double last_residual_inf = std::numeric_limits<double>::infinity();
    double last_base_shear_kn = 0.0;
    std::uint32_t last_plastic_story_count = 0U;
    std::uint32_t total_backtracks = 0U;

    for (std::uint32_t attempt = 1U; attempt <= config.max_step_iterations; ++attempt) {
        adaptive_iterations = attempt;
        for (std::size_t index = 0U; index < count; ++index) {
            trial_force[index] = external_force_n[index] * load_scale;
        }

        bool success = false;
        for (std::uint32_t iteration = 1U; iteration <= config.newton_max_iter; ++iteration) {
            static_cast<void>(iteration);
            const auto assembly = detail::assemble_story_frame(
                trial_displacement,
                constitutive,
                story_inputs,
                internal_force,
                lower,
                diagonal,
                upper);
            last_base_shear_kn = assembly.base_shear_kn;
            last_plastic_story_count = assembly.plastic_story_count;

            for (std::size_t index = 0U; index < count; ++index) {
                const double acceleration = acceleration_coefficient
                    * (trial_displacement[index] - predicted_displacement[index]);
                const double velocity = predicted_velocity[index] + gamma * dt * acceleration;
                residual[index] = trial_force[index] - internal_force[index]
                    - inputs.story_damping_n_s_per_m[index] * velocity
                    - inputs.story_mass_kg[index] * acceleration;
            }
            const double residual_inf = detail::norm_inf(residual);
            last_residual_inf = residual_inf;
            if (residual_inf <= config.tolerance) {
                for (std::size_t index = 0U; index < count; ++index) {
                    next_displacement_m[index] = trial_displacement[index];
                    next_acceleration_m_per_s2[index] = acceleration_coefficient
                        * (next_displacement_m[index] - predicted_displacement[index]);
                    next_velocity_m_per_s[index] = predicted_velocity[index]
                        + gamma * dt * next_acceleration_m_per_s2[index];
                }
                success = true;
                break;
            }

            for (std::size_t index = 0U; index < count; ++index) {
                effective_diagonal[index] = diagonal[index]
                    + inputs.story_mass_kg[index] * acceleration_coefficient
                    + inputs.story_damping_n_s_per_m[index] * damping_coefficient;
            }
            if (!detail::solve_tridiagonal(
                    lower, effective_diagonal, upper, residual, increment)) {
                break;
            }

            const double baseline =
                std::max(residual_inf, detail::kStoryFrameEpsilon);
            double scale = 1.0;
            bool accepted = false;
            while (scale >= config.line_search_min) {
                for (std::size_t index = 0U; index < count; ++index) {
                    candidate_displacement[index] =
                        trial_displacement[index] + scale * increment[index];
                }
                static_cast<void>(detail::assemble_story_frame(
                    candidate_displacement,
                    constitutive,
                    story_inputs,
                    internal_force,
                    lower,
                    diagonal,
                    upper));
                for (std::size_t index = 0U; index < count; ++index) {
                    const double acceleration = acceleration_coefficient
                        * (candidate_displacement[index] - predicted_displacement[index]);
                    const double velocity =
                        predicted_velocity[index] + gamma * dt * acceleration;
                    residual[index] = trial_force[index] - internal_force[index]
                        - inputs.story_damping_n_s_per_m[index] * velocity
                        - inputs.story_mass_kg[index] * acceleration;
                }
                const double candidate_norm = detail::norm_inf(residual);
                if (candidate_norm < baseline) {
                    trial_displacement = candidate_displacement;
                    accepted = true;
                    break;
                }
                scale *= config.line_search_decay;
                ++total_backtracks;
            }
            if (!accepted) {
                break;
            }
        }

        if (success) {
            return {
                true,
                adaptive_iterations,
                last_plastic_story_count,
                last_base_shear_kn,
                last_residual_inf,
                total_backtracks,
            };
        }
        load_scale *= config.adaptive_load_decay;
    }

    next_displacement_m = previous_displacement_m;
    next_velocity_m_per_s = previous_velocity_m_per_s;
    next_acceleration_m_per_s2 = previous_acceleration_m_per_s2;
    return {
        false,
        std::max(adaptive_iterations, 1U),
        last_plastic_story_count,
        last_base_shear_kn,
        last_residual_inf,
        total_backtracks,
    };
}

} // namespace

NonlinearNdthaResult solve_nonlinear_ndtha(
    const NonlinearNdthaConfig& config,
    const NonlinearNdthaInputs& inputs) {
    if (!spans_match(config, inputs)) {
        throw std::invalid_argument("nonlinear NDTHA input lengths do not match config counts");
    }

    const auto story_count = static_cast<std::size_t>(config.story_count);
    const auto step_count = static_cast<std::size_t>(config.step_count);
    const detail::StoryFrameConstitutiveConfig constitutive {
        config.hardening_ratio,
        config.pdelta_factor,
    };
    const detail::StoryFrameInputs story_inputs {
        inputs.story_stiffness_n_per_m,
        inputs.story_height_m,
        inputs.story_axial_n,
        inputs.story_yield_drift_m,
    };

    NonlinearNdthaResponse response {
        std::vector<double>(step_count, 0.0),
        std::vector<double>(step_count, 0.0),
        std::vector<double>(step_count, 0.0),
        std::vector<double>(step_count, 0.0),
        std::vector<double>(step_count, 0.0),
        std::vector<std::uint8_t>(step_count, 0U),
        std::vector<std::uint32_t>(step_count, 0U),
        std::vector<std::uint32_t>(step_count, 0U),
        std::vector<double>(step_count, 0.0),
        std::vector<double>(story_count, 0.0),
        std::vector<double>(story_count, 0.0),
    };

    std::vector<double> displacement(story_count, 0.0);
    std::vector<double> velocity(story_count, 0.0);
    std::vector<double> acceleration(story_count, 0.0);
    std::vector<double> next_displacement(story_count, 0.0);
    std::vector<double> next_velocity(story_count, 0.0);
    std::vector<double> next_acceleration(story_count, 0.0);
    std::vector<double> external_force(story_count, 0.0);
    std::vector<double> story_drift_pct(story_count, 0.0);
    std::vector<double> story_shear_kn(story_count, 0.0);
    std::vector<double> height_shape(story_count, 0.0);

    if (story_count == 1U) {
        height_shape[0] = 1.0;
    } else {
        for (std::size_t index = 0U; index < story_count; ++index) {
            const double phase = static_cast<double>(index) * 2.0 * std::numbers::pi
                / static_cast<double>(story_count);
            height_shape[index] = 0.85 + 0.30 * std::sin(phase);
        }
    }

    bool converged_all_steps = true;
    bool collapsed = false;
    std::int32_t collapse_step = -1;
    double collapse_time_s = 0.0;
    double collapse_drift_ratio_pct = 0.0;
    double collapse_top_displacement_m = 0.0;
    std::uint32_t max_plastic_story_count = 0U;
    double max_drift_ratio_pct = 0.0;
    std::uint64_t adaptive_iteration_sum = 0U;
    std::uint32_t step_count_completed = 0U;
    std::uint32_t total_line_search_backtracks = 0U;

    for (std::size_t step = 0U; step < step_count; ++step) {
        const double acceleration_g = inputs.acceleration_g[step];
        const double sign = std::abs(acceleration_g) > 1.0e-12
            ? (acceleration_g >= 0.0 ? 1.0 : -1.0)
            : 1.0;
        const auto denominator = std::max(step_count - 1U, std::size_t {1U});
        const double envelope = 1.0
            + 0.50 * (static_cast<double>(step) / static_cast<double>(denominator));
        for (std::size_t index = 0U; index < story_count; ++index) {
            const double static_force = inputs.floor_load_base_n[index]
                * height_shape[index] * envelope
                * (0.25 * acceleration_g + 0.02 * sign);
            const double inertial_force =
                -(inputs.story_mass_kg[index] * height_shape[index])
                * (acceleration_g * 9.80665 * 0.05);
            const double raw_force = static_force + inertial_force;
            double damping_force = inputs.story_damping_n_s_per_m[index] * velocity[index];
            const double damping_cap =
                std::max(std::abs(raw_force) * config.damping_force_cap_ratio, 1.0);
            damping_force = std::clamp(damping_force, -damping_cap, damping_cap);
            external_force[index] = raw_force - damping_force;
        }

        const auto step_result = solve_step(
            config,
            inputs,
            constitutive,
            story_inputs,
            external_force,
            displacement,
            velocity,
            acceleration,
            next_displacement,
            next_velocity,
            next_acceleration);
        response.step_converged[step] = step_result.converged ? 1U : 0U;
        response.step_iterations[step] = step_result.adaptive_iterations;
        response.step_plastic_story_count[step] = step_result.plastic_story_count;
        response.step_residual_inf[step] = step_result.residual_inf;
        adaptive_iteration_sum += step_result.adaptive_iterations;
        total_line_search_backtracks += step_result.line_search_backtracks;
        ++step_count_completed;

        if (!step_result.converged) {
            converged_all_steps = false;
            break;
        }

        displacement = next_displacement;
        velocity = next_velocity;
        acceleration = next_acceleration;
        detail::recover_story_response(
            displacement,
            inputs.story_height_m,
            inputs.story_stiffness_n_per_m,
            story_drift_pct,
            story_shear_kn);
        for (std::size_t index = 0U; index < story_count; ++index) {
            response.final_story_drift_pct[index] = story_drift_pct[index];
            response.story_drift_envelope_pct[index] = std::max(
                response.story_drift_envelope_pct[index], std::abs(story_drift_pct[index]));
        }
        const double drift_ratio_pct = detail::norm_inf(story_drift_pct);
        const double top_displacement_m = displacement[story_count - 1U];
        response.top_displacement_m[step] = top_displacement_m;
        response.drift_ratio_pct[step] = drift_ratio_pct;
        response.base_shear_kn[step] = step_result.base_shear_kn;
        response.core_drift_pct[step] = story_drift_pct[0];
        response.core_shear_kn[step] = story_shear_kn[0];
        max_plastic_story_count =
            std::max(max_plastic_story_count, step_result.plastic_story_count);
        max_drift_ratio_pct = std::max(max_drift_ratio_pct, drift_ratio_pct);

        if (drift_ratio_pct > config.collapse_drift_threshold_pct) {
            collapsed = true;
            converged_all_steps = false;
            collapse_step = static_cast<std::int32_t>(step);
            collapse_time_s = static_cast<double>(step) * config.dt_s;
            collapse_drift_ratio_pct = drift_ratio_pct;
            collapse_top_displacement_m = top_displacement_m;
            break;
        }
    }

    const double residual_top_displacement_m = displacement[story_count - 1U];
    const double residual_drift_ratio_pct = detail::norm_inf(response.final_story_drift_pct);
    const double avg_step_iterations = step_count_completed > 0U
        ? static_cast<double>(adaptive_iteration_sum)
            / static_cast<double>(step_count_completed)
        : 0.0;
    return {
        converged_all_steps && !collapsed,
        collapsed,
        collapse_step,
        collapse_time_s,
        collapse_drift_ratio_pct,
        collapse_top_displacement_m,
        step_count_completed,
        max_plastic_story_count,
        max_drift_ratio_pct,
        avg_step_iterations,
        residual_top_displacement_m,
        residual_drift_ratio_pct,
        total_line_search_backtracks,
        std::move(response),
    };
}

} // namespace structural::solver_cpu
