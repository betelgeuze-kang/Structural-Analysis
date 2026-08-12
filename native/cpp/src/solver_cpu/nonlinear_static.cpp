#include "nonlinear_static.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace structural::solver_cpu {
namespace {

constexpr double kEpsilon = 1.0e-12;

[[nodiscard]] double norm_inf(const std::vector<double>& values) {
    double maximum = 0.0;
    for (const auto value : values) {
        maximum = std::max(maximum, std::abs(value));
    }
    return maximum;
}

[[nodiscard]] double norm_l2(const std::vector<double>& values) {
    double sum = 0.0;
    for (const auto value : values) {
        sum += value * value;
    }
    return std::sqrt(sum);
}

[[nodiscard]] bool solve_tridiagonal(
    const std::vector<double>& lower,
    const std::vector<double>& diagonal,
    const std::vector<double>& upper,
    const std::vector<double>& right_hand_side,
    std::vector<double>& output) {
    const auto count = diagonal.size();
    if (count == 0U || lower.size() + 1U != count || upper.size() + 1U != count
        || right_hand_side.size() != count || output.size() != count) {
        return false;
    }

    std::vector<double> upper_prime(count, 0.0);
    std::vector<double> right_prime(count, 0.0);
    const double first_diagonal = diagonal[0];
    if (!std::isfinite(first_diagonal) || std::abs(first_diagonal) <= kEpsilon) {
        return false;
    }
    upper_prime[0] = count > 1U ? upper[0] / first_diagonal : 0.0;
    right_prime[0] = right_hand_side[0] / first_diagonal;

    for (std::size_t index = 1U; index < count; ++index) {
        const double denominator =
            diagonal[index] - lower[index - 1U] * upper_prime[index - 1U];
        if (!std::isfinite(denominator) || std::abs(denominator) <= kEpsilon) {
            return false;
        }
        upper_prime[index] = index < count - 1U ? upper[index] / denominator : 0.0;
        right_prime[index] =
            (right_hand_side[index] - lower[index - 1U] * right_prime[index - 1U])
            / denominator;
    }

    output[count - 1U] = right_prime[count - 1U];
    for (std::size_t index = count - 1U; index-- > 0U;) {
        output[index] = right_prime[index] - upper_prime[index] * output[index + 1U];
    }
    return std::all_of(output.begin(), output.end(), [](const auto value) {
        return std::isfinite(value);
    });
}

struct AssemblyResult {
    double base_shear_kn;
    std::uint32_t plastic_story_count;
};

[[nodiscard]] AssemblyResult assemble_internal_and_tangent(
    const std::vector<double>& displacement,
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs,
    std::vector<double>& internal_force,
    std::vector<double>& lower,
    std::vector<double>& diagonal,
    std::vector<double>& upper) {
    const auto count = displacement.size();
    std::vector<double> spring_force(count, 0.0);
    std::vector<double> spring_tangent(count, 0.0);
    std::uint32_t plastic_story_count = 0U;

    for (std::size_t index = 0U; index < count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement[index - 1U];
        const double drift = displacement[index] - previous;
        const double initial_stiffness =
            std::max(inputs.story_stiffness_n_per_m[index], kEpsilon);
        const double yield_drift =
            std::max(std::abs(inputs.story_yield_drift_m[index]), 1.0e-9);
        const double hardened_stiffness = config.hardening_ratio * initial_stiffness;
        double force = 0.0;
        double tangent = 0.0;
        if (std::abs(drift) <= yield_drift) {
            force = initial_stiffness * drift;
            tangent = initial_stiffness;
        } else {
            const double sign = drift >= 0.0 ? 1.0 : -1.0;
            force = sign
                * (initial_stiffness * yield_drift
                   + hardened_stiffness * (std::abs(drift) - yield_drift));
            tangent = hardened_stiffness;
            ++plastic_story_count;
        }

        const double height = std::max(inputs.story_height_m[index], kEpsilon);
        const double geometric_stiffness =
            config.pdelta_factor * std::abs(inputs.story_axial_n[index]) / height;
        spring_force[index] = force;
        spring_tangent[index] = tangent - geometric_stiffness;
    }

    for (std::size_t index = 0U; index < count; ++index) {
        internal_force[index] = index < count - 1U
            ? spring_force[index] - spring_force[index + 1U]
            : spring_force[index];
    }
    std::fill(lower.begin(), lower.end(), 0.0);
    std::fill(diagonal.begin(), diagonal.end(), 0.0);
    std::fill(upper.begin(), upper.end(), 0.0);
    for (std::size_t index = 0U; index < count; ++index) {
        const double current = spring_tangent[index];
        const double next = index < count - 1U ? spring_tangent[index + 1U] : 0.0;
        diagonal[index] = current + next;
        if (index > 0U) {
            lower[index - 1U] = -current;
        }
        if (index < count - 1U) {
            upper[index] = -next;
        }
    }

    double minimum_diagonal = std::numeric_limits<double>::infinity();
    for (const auto value : diagonal) {
        minimum_diagonal = std::min(minimum_diagonal, std::abs(value));
    }
    if (!std::isfinite(minimum_diagonal) || minimum_diagonal <= 1.0e-9) {
        for (std::size_t index = 0U; index < count; ++index) {
            diagonal[index] +=
                1.0e-6 * std::max(inputs.story_stiffness_n_per_m[index], 1.0);
        }
    }

    return {std::abs(spring_force[0]) / 1000.0, plastic_story_count};
}

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
        static_cast<void>(assemble_internal_and_tangent(
            displacement,
            config,
            inputs,
            internal_force,
            lower,
            diagonal,
            upper));
        for (std::size_t index = 0U; index < count; ++index) {
            residual[index] = inputs.floor_load_n[index] - internal_force[index];
        }
        const double residual_inf = norm_inf(residual);
        if (std::isfinite(residual_inf) && residual_inf <= config.tolerance) {
            converged = true;
            iterations = iteration;
            break;
        }
        if (!solve_tridiagonal(lower, diagonal, upper, residual, increment)) {
            iterations = iteration;
            break;
        }

        const double baseline = std::max(residual_inf, kEpsilon);
        double scale = 1.0;
        bool accepted = false;
        std::uint32_t local_backtracks = 0U;
        while (scale >= config.line_search_min) {
            for (std::size_t index = 0U; index < count; ++index) {
                trial[index] = displacement[index] + scale * increment[index];
            }
            static_cast<void>(assemble_internal_and_tangent(
                trial,
                config,
                inputs,
                internal_force,
                lower,
                diagonal,
                upper));
            for (std::size_t index = 0U; index < count; ++index) {
                residual[index] = inputs.floor_load_n[index] - internal_force[index];
            }
            const double trial_norm = norm_inf(residual);
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

    const auto assembly = assemble_internal_and_tangent(
        displacement,
        config,
        inputs,
        internal_force,
        lower,
        diagonal,
        upper);
    for (std::size_t index = 0U; index < count; ++index) {
        residual[index] = inputs.floor_load_n[index] - internal_force[index];
    }
    const double residual_inf = norm_inf(residual);
    const double residual_l2 = norm_l2(residual);
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
