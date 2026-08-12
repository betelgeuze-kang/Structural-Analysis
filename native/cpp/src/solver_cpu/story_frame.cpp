#include "story_frame.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <vector>

namespace structural::solver_cpu::detail {

double norm_inf(const std::span<const double> values) noexcept {
    double maximum = 0.0;
    for (const auto value : values) {
        maximum = std::max(maximum, std::abs(value));
    }
    return maximum;
}

double norm_l2(const std::span<const double> values) noexcept {
    double sum = 0.0;
    for (const auto value : values) {
        sum += value * value;
    }
    return std::sqrt(sum);
}

bool solve_tridiagonal(
    const std::span<const double> lower,
    const std::span<const double> diagonal,
    const std::span<const double> upper,
    const std::span<const double> right_hand_side,
    const std::span<double> output) {
    const auto count = diagonal.size();
    if (count == 0U || lower.size() + 1U != count || upper.size() + 1U != count
        || right_hand_side.size() != count || output.size() != count) {
        return false;
    }

    std::vector<double> upper_prime(count, 0.0);
    std::vector<double> right_prime(count, 0.0);
    const double first_diagonal = diagonal[0];
    if (!std::isfinite(first_diagonal) || std::abs(first_diagonal) <= kStoryFrameEpsilon) {
        return false;
    }
    upper_prime[0] = count > 1U ? upper[0] / first_diagonal : 0.0;
    right_prime[0] = right_hand_side[0] / first_diagonal;

    for (std::size_t index = 1U; index < count; ++index) {
        const double denominator =
            diagonal[index] - lower[index - 1U] * upper_prime[index - 1U];
        if (!std::isfinite(denominator) || std::abs(denominator) <= kStoryFrameEpsilon) {
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

StoryFrameAssemblyResult assemble_story_frame(
    const std::span<const double> displacement_m,
    const StoryFrameConstitutiveConfig& config,
    const StoryFrameInputs& inputs,
    const std::span<double> internal_force_n,
    const std::span<double> lower_n_per_m,
    const std::span<double> diagonal_n_per_m,
    const std::span<double> upper_n_per_m) {
    const auto count = displacement_m.size();
    if (count == 0U || inputs.story_stiffness_n_per_m.size() != count
        || inputs.story_height_m.size() != count || inputs.story_axial_n.size() != count
        || inputs.story_yield_drift_m.size() != count || internal_force_n.size() != count
        || lower_n_per_m.size() + 1U != count || diagonal_n_per_m.size() != count
        || upper_n_per_m.size() + 1U != count) {
        throw std::invalid_argument("story-frame assembly lengths do not match");
    }

    std::vector<double> spring_force(count, 0.0);
    std::vector<double> spring_tangent(count, 0.0);
    std::uint32_t plastic_story_count = 0U;

    for (std::size_t index = 0U; index < count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement_m[index - 1U];
        const double drift = displacement_m[index] - previous;
        const double initial_stiffness =
            std::max(inputs.story_stiffness_n_per_m[index], kStoryFrameEpsilon);
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

        const double height =
            std::max(inputs.story_height_m[index], kStoryFrameEpsilon);
        const double geometric_stiffness =
            config.pdelta_factor * std::abs(inputs.story_axial_n[index]) / height;
        spring_force[index] = force;
        spring_tangent[index] = tangent - geometric_stiffness;
    }

    for (std::size_t index = 0U; index < count; ++index) {
        internal_force_n[index] = index < count - 1U
            ? spring_force[index] - spring_force[index + 1U]
            : spring_force[index];
    }
    std::fill(lower_n_per_m.begin(), lower_n_per_m.end(), 0.0);
    std::fill(diagonal_n_per_m.begin(), diagonal_n_per_m.end(), 0.0);
    std::fill(upper_n_per_m.begin(), upper_n_per_m.end(), 0.0);
    for (std::size_t index = 0U; index < count; ++index) {
        const double current = spring_tangent[index];
        const double next = index < count - 1U ? spring_tangent[index + 1U] : 0.0;
        diagonal_n_per_m[index] = current + next;
        if (index > 0U) {
            lower_n_per_m[index - 1U] = -current;
        }
        if (index < count - 1U) {
            upper_n_per_m[index] = -next;
        }
    }

    double minimum_diagonal = std::numeric_limits<double>::infinity();
    for (const auto value : diagonal_n_per_m) {
        minimum_diagonal = std::min(minimum_diagonal, std::abs(value));
    }
    if (!std::isfinite(minimum_diagonal) || minimum_diagonal <= 1.0e-9) {
        for (std::size_t index = 0U; index < count; ++index) {
            diagonal_n_per_m[index] +=
                1.0e-6 * std::max(inputs.story_stiffness_n_per_m[index], 1.0);
        }
    }

    return {std::abs(spring_force[0]) / 1000.0, plastic_story_count};
}

void recover_story_response(
    const std::span<const double> displacement_m,
    const std::span<const double> story_height_m,
    const std::span<const double> story_stiffness_n_per_m,
    const std::span<double> drift_ratio_pct,
    const std::span<double> shear_kn) {
    const auto count = displacement_m.size();
    if (story_height_m.size() != count || story_stiffness_n_per_m.size() != count
        || drift_ratio_pct.size() != count || shear_kn.size() != count) {
        throw std::invalid_argument("story-frame recovery lengths do not match");
    }
    for (std::size_t index = 0U; index < count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement_m[index - 1U];
        const double drift = displacement_m[index] - previous;
        drift_ratio_pct[index] =
            100.0 * drift / std::max(story_height_m[index], kStoryFrameEpsilon);
        shear_kn[index] = story_stiffness_n_per_m[index] * drift / 1000.0;
    }
}

} // namespace structural::solver_cpu::detail
