#include "track_point_load.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace structural::solver_cpu {
namespace {

constexpr double kEpsilon = 1.0e-12;

[[nodiscard]] double ghost_at(
    const std::vector<double>& values,
    const std::ptrdiff_t index,
    const TrackSupportType support_type) {
    const auto count = static_cast<std::ptrdiff_t>(values.size());
    if (index == -1) {
        return support_type == TrackSupportType::pinned ? -values[1] : values[1];
    }
    if (index == count) {
        const auto adjacent = values[values.size() - 2U];
        return support_type == TrackSupportType::pinned ? -adjacent : adjacent;
    }
    if (index < 0 || index >= count) {
        return 0.0;
    }
    return values[static_cast<std::size_t>(index)];
}

void apply_euler_operator(
    const std::vector<double>& values,
    std::vector<double>& output,
    const double dx,
    const double bending_stiffness_n_m2,
    const double winkler_k_n_per_m2,
    const double pasternak_g_n,
    const TrackSupportType support_type) {
    const auto count = values.size();
    const double inverse_dx2 = 1.0 / std::max(dx * dx, kEpsilon);
    const double inverse_dx4 = inverse_dx2 * inverse_dx2;

    for (std::size_t index = 1U; index < count - 1U; ++index) {
        const auto signed_index = static_cast<std::ptrdiff_t>(index);
        const double second_derivative =
            (ghost_at(values, signed_index + 1, support_type)
             - 2.0 * ghost_at(values, signed_index, support_type)
             + ghost_at(values, signed_index - 1, support_type))
            * inverse_dx2;
        const double fourth_derivative =
            (ghost_at(values, signed_index - 2, support_type)
             - 4.0 * ghost_at(values, signed_index - 1, support_type)
             + 6.0 * ghost_at(values, signed_index, support_type)
             - 4.0 * ghost_at(values, signed_index + 1, support_type)
             + ghost_at(values, signed_index + 2, support_type))
            * inverse_dx4;
        output[index] = bending_stiffness_n_m2 * fourth_derivative
            - pasternak_g_n * second_derivative
            + winkler_k_n_per_m2 * ghost_at(values, signed_index, support_type);
    }
    output[0] = values[0];
    output[count - 1U] = values[count - 1U];
}

[[nodiscard]] double dot(
    const std::vector<double>& left,
    const std::vector<double>& right) {
    double sum = 0.0;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        sum += left[index] * right[index];
    }
    return sum;
}

struct ConjugateGradientResult {
    bool converged;
    std::uint32_t iterations;
    double residual_inf;
};

[[nodiscard]] ConjugateGradientResult conjugate_gradient(
    const std::vector<double>& right_hand_side,
    std::vector<double>& solution,
    const TrackPointLoadConfig& config,
    const double dx) {
    const auto count = right_hand_side.size();
    std::vector<double> residual(count, 0.0);
    std::vector<double> direction(count, 0.0);
    std::vector<double> operator_direction(count, 0.0);
    std::vector<double> operator_solution(count, 0.0);

    apply_euler_operator(
        solution,
        operator_solution,
        dx,
        config.bending_stiffness_n_m2,
        config.winkler_k_n_per_m2,
        config.pasternak_g_n,
        config.support_type);
    for (std::size_t index = 0U; index < count; ++index) {
        residual[index] = right_hand_side[index] - operator_solution[index];
        direction[index] = residual[index];
    }

    const double tolerance_squared = config.tolerance * config.tolerance;
    double previous_norm_squared = dot(residual, residual);
    if (std::isfinite(previous_norm_squared) && previous_norm_squared <= tolerance_squared) {
        return {true, 0U, std::sqrt(previous_norm_squared)};
    }

    double norm_squared = previous_norm_squared;
    std::uint32_t iterations = 0U;
    for (std::uint32_t iteration = 1U; iteration <= config.cg_max_iter; ++iteration) {
        apply_euler_operator(
            direction,
            operator_direction,
            dx,
            config.bending_stiffness_n_m2,
            config.winkler_k_n_per_m2,
            config.pasternak_g_n,
            config.support_type);
        const double denominator = dot(direction, operator_direction);
        if (!std::isfinite(denominator) || std::abs(denominator) <= kEpsilon) {
            iterations = iteration;
            break;
        }
        const double alpha = previous_norm_squared / denominator;
        for (std::size_t index = 0U; index < count; ++index) {
            solution[index] += alpha * direction[index];
            residual[index] -= alpha * operator_direction[index];
        }
        norm_squared = dot(residual, residual);
        iterations = iteration;
        if (!std::isfinite(norm_squared)) {
            break;
        }
        if (norm_squared <= tolerance_squared) {
            return {true, iteration, std::sqrt(norm_squared)};
        }
        const double beta = norm_squared / previous_norm_squared;
        for (std::size_t index = 0U; index < count; ++index) {
            direction[index] = residual[index] + beta * direction[index];
        }
        previous_norm_squared = norm_squared;
    }
    return {false, iterations, std::sqrt(std::max(norm_squared, 0.0))};
}

[[nodiscard]] std::vector<double> point_load(const TrackPointLoadConfig& config) {
    const auto count = static_cast<std::size_t>(config.node_count);
    std::vector<double> right_hand_side(count, 0.0);
    const double dx = config.length_m / std::max(static_cast<double>(count - 1U), 1.0);
    const double position = std::clamp(config.point_position_m, 0.0, config.length_m);
    const double coordinate = position / std::max(dx, kEpsilon);
    const auto lower = static_cast<std::size_t>(std::floor(coordinate));
    const auto upper = std::min(lower + 1U, count - 1U);
    const double upper_weight = coordinate - static_cast<double>(lower);
    const double lower_weight = 1.0 - upper_weight;
    right_hand_side[lower] += config.point_force_n * lower_weight / std::max(dx, kEpsilon);
    right_hand_side[upper] += config.point_force_n * upper_weight / std::max(dx, kEpsilon);
    right_hand_side[0] = 0.0;
    right_hand_side[count - 1U] = 0.0;
    return right_hand_side;
}

[[nodiscard]] std::vector<double> displacement_gradient(
    const std::vector<double>& displacement,
    const double dx,
    const TrackTheory theory) {
    const auto count = displacement.size();
    std::vector<double> rotation(count, 0.0);
    for (std::size_t index = 1U; index < count - 1U; ++index) {
        rotation[index] =
            (displacement[index + 1U] - displacement[index - 1U])
            / (2.0 * std::max(dx, kEpsilon));
    }
    if (theory == TrackTheory::euler) {
        // Python's C1 Euler oracle uses numpy.gradient's default one-sided endpoints.
        rotation[0] = (displacement[1] - displacement[0]) / std::max(dx, kEpsilon);
        rotation[count - 1U] =
            (displacement[count - 1U] - displacement[count - 2U])
            / std::max(dx, kEpsilon);
    } else {
        // The reduced Timoshenko oracle explicitly replaces both one-sided endpoints.
        rotation[0] = rotation[1];
        rotation[count - 1U] = rotation[count - 2U];
    }
    return rotation;
}

} // namespace

TrackPointLoadResult solve_track_point_load(const TrackPointLoadConfig& config) {
    const auto count = static_cast<std::size_t>(config.node_count);
    const double dx = config.length_m / std::max(static_cast<double>(count - 1U), 1.0);
    const auto right_hand_side = point_load(config);
    std::vector<double> displacement(count, 0.0);
    const auto solve = conjugate_gradient(right_hand_side, displacement, config, dx);

    if (config.theory == TrackTheory::timoshenko_reduced) {
        const double denominator = std::max(
            config.shear_stiffness_n * config.length_m * config.length_m,
            kEpsilon);
        const double raw_correction = 12.0 * config.bending_stiffness_n_m2 / denominator;
        const double scale = 1.0 + std::clamp(raw_correction, 0.0, 0.75);
        for (auto& value : displacement) {
            value *= scale;
        }
    }

    auto rotation = displacement_gradient(displacement, dx, config.theory);
    double maximum = 0.0;
    for (const auto value : displacement) {
        maximum = std::max(maximum, std::abs(value));
    }
    const double midpoint = displacement[count / 2U];
    const bool finite_result = std::isfinite(solve.residual_inf)
        && std::isfinite(maximum)
        && std::isfinite(midpoint)
        && std::all_of(displacement.begin(), displacement.end(), [](const auto value) {
               return std::isfinite(value);
           })
        && std::all_of(rotation.begin(), rotation.end(), [](const auto value) {
               return std::isfinite(value);
           });
    return {
        solve.converged && finite_result,
        solve.iterations,
        solve.residual_inf,
        maximum,
        midpoint,
        std::move(displacement),
        std::move(rotation),
    };
}

} // namespace structural::solver_cpu
