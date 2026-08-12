#ifndef STRUCTURAL_HIP_STORY_FRAME_HIP_DEVICE_HPP
#define STRUCTURAL_HIP_STORY_FRAME_HIP_DEVICE_HPP

#include <hip/hip_runtime.h>

#include <cfloat>
#include <cstddef>
#include <cstdint>

namespace structural::hip::device_detail {

inline constexpr double kStoryFrameEpsilon = 1.0e-12;

struct StoryFrameAssemblyResult {
    double base_shear_kn;
    std::uint32_t plastic_story_count;
};

__device__ inline double vector_norm_inf(const double* const values, const std::size_t count) {
    double maximum = 0.0;
    for (std::size_t index = 0U; index < count; ++index) {
        maximum = fmax(maximum, fabs(values[index]));
    }
    return maximum;
}

__device__ inline double vector_norm_l2(const double* const values, const std::size_t count) {
    double squared = 0.0;
    for (std::size_t index = 0U; index < count; ++index) {
        squared += values[index] * values[index];
    }
    return sqrt(squared);
}

__device__ inline StoryFrameAssemblyResult assemble_story_frame(
    const std::size_t story_count, const double hardening_ratio, const double pdelta_factor,
    const double* const stiffness, const double* const height, const double* const axial,
    const double* const yield_drift, const double* const displacement, double* const spring_force,
    double* const spring_tangent, double* const internal_force, double* const lower,
    double* const diagonal, double* const upper) {
    std::uint32_t plastic_story_count = 0U;
    for (std::size_t index = 0U; index < story_count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement[index - 1U];
        const double drift = displacement[index] - previous;
        const double initial_stiffness = fmax(stiffness[index], kStoryFrameEpsilon);
        const double bounded_yield_drift = fmax(fabs(yield_drift[index]), 1.0e-9);
        const double hardened_stiffness = hardening_ratio * initial_stiffness;
        if (fabs(drift) <= bounded_yield_drift) {
            spring_force[index] = initial_stiffness * drift;
            spring_tangent[index] = initial_stiffness;
        } else {
            const double sign = drift >= 0.0 ? 1.0 : -1.0;
            spring_force[index] = sign * (initial_stiffness * bounded_yield_drift +
                                          hardened_stiffness * (fabs(drift) - bounded_yield_drift));
            spring_tangent[index] = hardened_stiffness;
            ++plastic_story_count;
        }
        const double bounded_height = fmax(height[index], kStoryFrameEpsilon);
        const double geometric_stiffness = pdelta_factor * fabs(axial[index]) / bounded_height;
        spring_tangent[index] -= geometric_stiffness;
    }

    for (std::size_t index = 0U; index < story_count; ++index) {
        internal_force[index] = index + 1U < story_count
                                    ? spring_force[index] - spring_force[index + 1U]
                                    : spring_force[index];
        lower[index] = 0.0;
        diagonal[index] = 0.0;
        upper[index] = 0.0;
    }
    for (std::size_t index = 0U; index < story_count; ++index) {
        const double current = spring_tangent[index];
        const double next = index + 1U < story_count ? spring_tangent[index + 1U] : 0.0;
        diagonal[index] = current + next;
        if (index > 0U) {
            lower[index - 1U] = -current;
        }
        if (index + 1U < story_count) {
            upper[index] = -next;
        }
    }

    double minimum_diagonal = DBL_MAX;
    for (std::size_t index = 0U; index < story_count; ++index) {
        minimum_diagonal = fmin(minimum_diagonal, fabs(diagonal[index]));
    }
    if (!isfinite(minimum_diagonal) || minimum_diagonal <= 1.0e-9) {
        for (std::size_t index = 0U; index < story_count; ++index) {
            diagonal[index] += 1.0e-6 * fmax(stiffness[index], 1.0);
        }
    }
    return {fabs(spring_force[0]) / 1000.0, plastic_story_count};
}

__device__ inline bool solve_tridiagonal(const std::size_t count, const double* const lower,
                                         const double* const diagonal, const double* const upper,
                                         const double* const right_hand_side,
                                         double* const upper_prime, double* const right_prime,
                                         double* const output) {
    const double first_diagonal = diagonal[0];
    if (!isfinite(first_diagonal) || fabs(first_diagonal) <= kStoryFrameEpsilon) {
        return false;
    }
    upper_prime[0] = count > 1U ? upper[0] / first_diagonal : 0.0;
    right_prime[0] = right_hand_side[0] / first_diagonal;
    for (std::size_t index = 1U; index < count; ++index) {
        const double denominator = diagonal[index] - lower[index - 1U] * upper_prime[index - 1U];
        if (!isfinite(denominator) || fabs(denominator) <= kStoryFrameEpsilon) {
            return false;
        }
        upper_prime[index] = index + 1U < count ? upper[index] / denominator : 0.0;
        right_prime[index] =
            (right_hand_side[index] - lower[index - 1U] * right_prime[index - 1U]) / denominator;
    }
    output[count - 1U] = right_prime[count - 1U];
    for (std::size_t index = count - 1U; index-- > 0U;) {
        output[index] = right_prime[index] - upper_prime[index] * output[index + 1U];
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!isfinite(output[index])) {
            return false;
        }
    }
    return true;
}

__device__ inline void
recover_story_response(const std::size_t count, const double* const displacement,
                       const double* const height, const double* const stiffness,
                       double* const drift_ratio_pct, double* const shear_kn) {
    for (std::size_t index = 0U; index < count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement[index - 1U];
        const double drift = displacement[index] - previous;
        drift_ratio_pct[index] = 100.0 * drift / fmax(height[index], kStoryFrameEpsilon);
        shear_kn[index] = stiffness[index] * drift / 1000.0;
    }
}

} // namespace structural::hip::device_detail

#endif
