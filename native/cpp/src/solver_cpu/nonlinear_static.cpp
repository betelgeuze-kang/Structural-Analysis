#include "nonlinear_static.hpp"
#include "story_frame.hpp"

#include <algorithm>
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

} // namespace

NonlinearStaticResult solve_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs) {
    if (!spans_match(config, inputs)) {
        throw std::invalid_argument("nonlinear static input lengths do not match story_count");
    }

    const auto count = static_cast<std::size_t>(config.story_count);
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
    std::vector<double> displacement(count, 0.0);
    std::vector<double> internal_force(count, 0.0);
    std::vector<double> lower(count - 1U, 0.0);
    std::vector<double> diagonal(count, 0.0);
    std::vector<double> upper(count - 1U, 0.0);
    std::vector<double> residual(count, 0.0);
    std::vector<double> increment(count, 0.0);
    std::vector<double> trial(count, 0.0);

    bool converged = false;
    std::uint32_t iterations = 0U;
    std::uint32_t backtracks = 0U;
    for (std::uint32_t iteration = 1U; iteration <= config.max_iter; ++iteration) {
        static_cast<void>(detail::assemble_story_frame(
            displacement,
            constitutive,
            story_inputs,
            internal_force,
            lower,
            diagonal,
            upper));
        for (std::size_t index = 0U; index < count; ++index) {
            residual[index] = inputs.floor_load_n[index] - internal_force[index];
        }
        const double residual_inf = detail::norm_inf(residual);
        if (std::isfinite(residual_inf) && residual_inf <= config.tolerance) {
            converged = true;
            iterations = iteration;
            break;
        }
        if (!detail::solve_tridiagonal(lower, diagonal, upper, residual, increment)) {
            iterations = iteration;
            break;
        }

        const double baseline = std::max(residual_inf, detail::kStoryFrameEpsilon);
        double scale = 1.0;
        bool accepted = false;
        std::uint32_t local_backtracks = 0U;
        while (scale >= config.line_search_min) {
            for (std::size_t index = 0U; index < count; ++index) {
                trial[index] = displacement[index] + scale * increment[index];
            }
            static_cast<void>(detail::assemble_story_frame(
                trial,
                constitutive,
                story_inputs,
                internal_force,
                lower,
                diagonal,
                upper));
            for (std::size_t index = 0U; index < count; ++index) {
                residual[index] = inputs.floor_load_n[index] - internal_force[index];
            }
            const double trial_norm = detail::norm_inf(residual);
            if (std::isfinite(trial_norm) && trial_norm < baseline) {
                displacement = trial;
                accepted = true;
                break;
            }
            scale *= config.line_search_decay;
            ++local_backtracks;
        }
        backtracks += local_backtracks;
        iterations = iteration;
        if (!accepted) {
            break;
        }
    }

    const auto assembly = detail::assemble_story_frame(
        displacement,
        constitutive,
        story_inputs,
        internal_force,
        lower,
        diagonal,
        upper);
    for (std::size_t index = 0U; index < count; ++index) {
        residual[index] = inputs.floor_load_n[index] - internal_force[index];
    }
    const double residual_inf = detail::norm_inf(residual);
    const double residual_l2 = detail::norm_l2(residual);
    double maximum_displacement = 0.0;
    for (const auto value : displacement) {
        maximum_displacement = std::max(maximum_displacement, std::abs(value));
    }
    const double top_displacement = displacement[count - 1U];
    const bool finite_result = std::isfinite(residual_inf) && std::isfinite(residual_l2)
        && std::isfinite(maximum_displacement) && std::isfinite(top_displacement)
        && std::isfinite(assembly.base_shear_kn)
        && std::all_of(displacement.begin(), displacement.end(), [](const auto value) {
               return std::isfinite(value);
           });
    if (finite_result && residual_inf <= config.tolerance) {
        converged = true;
    }
    return {
        converged && finite_result,
        iterations,
        residual_inf,
        residual_l2,
        maximum_displacement,
        top_displacement,
        assembly.base_shear_kn,
        assembly.plastic_story_count,
        backtracks,
        std::move(displacement),
    };
}

} // namespace structural::solver_cpu
