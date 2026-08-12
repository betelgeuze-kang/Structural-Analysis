#include "sparse_linear.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace structural::solver_cpu {
namespace {

constexpr std::size_t kMaximumOrder = 1'000'000U;
constexpr std::uint64_t kMaximumNonzeros = 100'000'000U;
constexpr double kBreakdownFactor = 64.0;

[[nodiscard]] bool all_finite(const std::span<const double> values) noexcept {
    return std::all_of(values.begin(), values.end(), [](const double value) {
        return std::isfinite(value);
    });
}

[[nodiscard]] double norm_inf(const std::span<const double> values) noexcept {
    double maximum = 0.0;
    for (const double value : values) {
        maximum = std::max(maximum, std::abs(value));
    }
    return maximum;
}

[[nodiscard]] double norm_l2(const std::span<const double> values) noexcept {
    double scale = 0.0;
    double sum_squares = 1.0;
    for (const double value : values) {
        const double magnitude = std::abs(value);
        if (magnitude == 0.0) {
            continue;
        }
        if (scale < magnitude) {
            const double ratio = scale / magnitude;
            sum_squares = 1.0 + sum_squares * ratio * ratio;
            scale = magnitude;
        } else {
            const double ratio = magnitude / scale;
            sum_squares += ratio * ratio;
        }
    }
    return scale == 0.0 ? 0.0 : scale * std::sqrt(sum_squares);
}

[[nodiscard]] double dot(
    const std::span<const double> left,
    const std::span<const double> right) noexcept {
    double sum = 0.0;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        sum += left[index] * right[index];
    }
    return sum;
}

[[nodiscard]] std::size_t find_column(
    const CsrMatrixView matrix,
    const std::size_t row,
    const std::uint32_t column) noexcept {
    const auto begin = static_cast<std::size_t>(matrix.row_offsets[row]);
    const auto end = static_cast<std::size_t>(matrix.row_offsets[row + 1U]);
    const auto first = matrix.column_indices.begin() + static_cast<std::ptrdiff_t>(begin);
    const auto last = matrix.column_indices.begin() + static_cast<std::ptrdiff_t>(end);
    const auto found = std::lower_bound(first, last, column);
    if (found == last || *found != column) {
        return matrix.values.size();
    }
    return static_cast<std::size_t>(found - matrix.column_indices.begin());
}

void matvec_unchecked(
    const CsrMatrixView matrix,
    const std::span<const double> input,
    const std::span<double> output) noexcept {
    for (std::size_t row = 0U; row < matrix.order; ++row) {
        double value = 0.0;
        const auto begin = matrix.row_offsets[row];
        const auto end = matrix.row_offsets[row + 1U];
        for (std::uint64_t offset = begin; offset < end; ++offset) {
            const auto index = static_cast<std::size_t>(offset);
            value += matrix.values[index] * input[matrix.column_indices[index]];
        }
        output[row] = value;
    }
}

void validate_symmetric_structure_and_values(const CsrMatrixView matrix) {
    constexpr double tolerance_factor = 32.0;
    const double epsilon = std::numeric_limits<double>::epsilon();
    for (std::size_t row = 0U; row < matrix.order; ++row) {
        const auto begin = static_cast<std::size_t>(matrix.row_offsets[row]);
        const auto end = static_cast<std::size_t>(matrix.row_offsets[row + 1U]);
        for (std::size_t offset = begin; offset < end; ++offset) {
            const auto column = matrix.column_indices[offset];
            const auto transpose = find_column(
                matrix, static_cast<std::size_t>(column), static_cast<std::uint32_t>(row));
            if (transpose == matrix.values.size()) {
                throw std::invalid_argument("sparse SPD matrix structure is not symmetric");
            }
            const double left = matrix.values[offset];
            const double right = matrix.values[transpose];
            const double scale = std::max({1.0, std::abs(left), std::abs(right)});
            if (std::abs(left - right) > tolerance_factor * epsilon * scale) {
                throw std::invalid_argument("sparse SPD matrix values are not symmetric");
            }
        }
    }
}

[[nodiscard]] SparseLinearResult make_result(
    const SolverStatus status,
    std::vector<double> solution,
    const std::uint32_t iterations,
    const double initial_residual_inf,
    const std::span<const double> residual,
    const double last_increment_inf) {
    return {
        status,
        std::move(solution),
        iterations,
        initial_residual_inf,
        norm_inf(residual),
        norm_l2(residual),
        last_increment_inf,
        0U,
    };
}

void require_finite_vector(
    const std::span<const double> values,
    const std::string_view label) {
    if (!all_finite(values)) {
        throw std::invalid_argument(std::string(label) + " contains a non-finite value");
    }
}

}  // namespace

void validate_canonical_csr(const CsrMatrixView matrix) {
    if (matrix.order == 0U || matrix.order > kMaximumOrder
        || matrix.order == std::numeric_limits<std::size_t>::max()
        || matrix.row_offsets.size() != matrix.order + 1U
        || matrix.column_indices.size() != matrix.values.size()
        || matrix.values.size() > kMaximumNonzeros) {
        throw std::invalid_argument("canonical CSR dimensions are outside the bounded domain");
    }
    if (matrix.row_offsets.front() != 0U
        || matrix.row_offsets.back() != matrix.values.size()) {
        throw std::invalid_argument("canonical CSR row offsets do not span the value arrays");
    }
    require_finite_vector(matrix.values, "canonical CSR values");
    for (std::size_t row = 0U; row < matrix.order; ++row) {
        const auto begin = matrix.row_offsets[row];
        const auto end = matrix.row_offsets[row + 1U];
        if (begin > end || end > matrix.values.size()) {
            throw std::invalid_argument("canonical CSR row offsets are not monotonic");
        }
        bool has_previous = false;
        std::uint32_t previous = 0U;
        for (std::uint64_t offset = begin; offset < end; ++offset) {
            const auto column = matrix.column_indices[static_cast<std::size_t>(offset)];
            if (column >= matrix.order) {
                throw std::invalid_argument("canonical CSR column is out of range");
            }
            if (has_previous && column <= previous) {
                throw std::invalid_argument(
                    "canonical CSR columns must be strictly increasing per row");
            }
            previous = column;
            has_previous = true;
        }
    }
}

void csr_matvec(
    const CsrMatrixView matrix,
    const std::span<const double> input,
    const std::span<double> output) {
    validate_canonical_csr(matrix);
    if (input.size() != matrix.order || output.size() != matrix.order) {
        throw std::invalid_argument("CSR matrix-vector dimensions do not match");
    }
    require_finite_vector(input, "CSR input");
    matvec_unchecked(matrix, input, output);
}

SparseLinearResult solve_sparse_spd_pcg(
    const CsrMatrixView matrix,
    const std::span<const double> right_hand_side,
    const std::span<const double> initial_guess,
    const SparseLinearConfig& config) {
    validate_canonical_csr(matrix);
    validate_symmetric_structure_and_values(matrix);
    if (right_hand_side.size() != matrix.order
        || (!initial_guess.empty() && initial_guess.size() != matrix.order)
        || config.max_iterations == 0U
        || !std::isfinite(config.absolute_residual_tolerance)
        || !std::isfinite(config.relative_residual_tolerance)
        || !std::isfinite(config.maximum_increment)
        || config.absolute_residual_tolerance < 0.0
        || config.relative_residual_tolerance < 0.0
        || (config.absolute_residual_tolerance == 0.0
            && config.relative_residual_tolerance == 0.0)
        || config.maximum_increment < 0.0) {
        throw std::invalid_argument("sparse PCG configuration or vector dimensions are invalid");
    }
    require_finite_vector(right_hand_side, "sparse PCG right-hand side");
    require_finite_vector(initial_guess, "sparse PCG initial guess");

    std::vector<double> solution(matrix.order, 0.0);
    if (!initial_guess.empty()) {
        std::copy(initial_guess.begin(), initial_guess.end(), solution.begin());
    }
    std::vector<double> product(matrix.order, 0.0);
    matvec_unchecked(matrix, solution, product);
    std::vector<double> residual(matrix.order, 0.0);
    for (std::size_t index = 0U; index < matrix.order; ++index) {
        residual[index] = right_hand_side[index] - product[index];
    }
    const double initial_residual_inf = norm_inf(residual);

    std::vector<double> diagonal_inverse(matrix.order, 0.0);
    for (std::size_t row = 0U; row < matrix.order; ++row) {
        const auto diagonal_offset =
            find_column(matrix, row, static_cast<std::uint32_t>(row));
        if (diagonal_offset == matrix.values.size()
            || matrix.values[diagonal_offset] == 0.0) {
            return make_result(
                SolverStatus::singularity, std::move(solution), 0U,
                initial_residual_inf, residual, 0.0);
        }
        if (matrix.values[diagonal_offset] < 0.0) {
            return make_result(
                SolverStatus::indefinite_operator, std::move(solution), 0U,
                initial_residual_inf, residual, 0.0);
        }
        diagonal_inverse[row] = 1.0 / matrix.values[diagonal_offset];
        if (!std::isfinite(diagonal_inverse[row])) {
            return make_result(
                SolverStatus::singularity, std::move(solution), 0U,
                initial_residual_inf, residual, 0.0);
        }
    }
    const double convergence_limit = config.absolute_residual_tolerance
        + config.relative_residual_tolerance * norm_inf(right_hand_side);
    if (initial_residual_inf <= convergence_limit) {
        return make_result(
            SolverStatus::converged, std::move(solution), 0U,
            initial_residual_inf, residual, 0.0);
    }

    std::vector<double> preconditioned(matrix.order, 0.0);
    std::vector<double> direction(matrix.order, 0.0);
    for (std::size_t index = 0U; index < matrix.order; ++index) {
        preconditioned[index] = diagonal_inverse[index] * residual[index];
        direction[index] = preconditioned[index];
    }
    double rho = dot(residual, preconditioned);
    if (!std::isfinite(rho) || rho <= 0.0) {
        return make_result(
            SolverStatus::indefinite_operator, std::move(solution), 0U,
            initial_residual_inf, residual, 0.0);
    }

    std::vector<double> operator_direction(matrix.order, 0.0);
    std::vector<double> candidate(matrix.order, 0.0);
    double last_increment_inf = 0.0;
    for (std::uint32_t iteration = 1U; iteration <= config.max_iterations; ++iteration) {
        matvec_unchecked(matrix, direction, operator_direction);
        const double denominator = dot(direction, operator_direction);
        const double breakdown_scale =
            kBreakdownFactor * std::numeric_limits<double>::epsilon()
            * std::max(1.0, norm_l2(direction) * norm_l2(operator_direction));
        if (!std::isfinite(denominator) || denominator <= breakdown_scale) {
            const auto status = denominator < -breakdown_scale
                ? SolverStatus::indefinite_operator
                : SolverStatus::singularity;
            return make_result(
                status, std::move(solution), iteration - 1U,
                initial_residual_inf, residual, last_increment_inf);
        }
        const double alpha = rho / denominator;
        if (!std::isfinite(alpha)) {
            return make_result(
                SolverStatus::singularity, std::move(solution), iteration - 1U,
                initial_residual_inf, residual, last_increment_inf);
        }
        last_increment_inf = 0.0;
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            const double increment = alpha * direction[index];
            last_increment_inf = std::max(last_increment_inf, std::abs(increment));
            candidate[index] = solution[index] + increment;
        }
        if (config.maximum_increment > 0.0
            && last_increment_inf > config.maximum_increment) {
            return make_result(
                SolverStatus::increment_limit, std::move(solution), iteration - 1U,
                initial_residual_inf, residual, last_increment_inf);
        }
        solution.swap(candidate);
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            residual[index] -= alpha * operator_direction[index];
        }
        if (norm_inf(residual) <= convergence_limit) {
            matvec_unchecked(matrix, solution, product);
            for (std::size_t index = 0U; index < matrix.order; ++index) {
                residual[index] = right_hand_side[index] - product[index];
            }
            const auto status = norm_inf(residual) <= convergence_limit
                ? SolverStatus::converged
                : SolverStatus::residual_limit;
            return make_result(
                status, std::move(solution), iteration,
                initial_residual_inf, residual, last_increment_inf);
        }
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            preconditioned[index] = diagonal_inverse[index] * residual[index];
        }
        const double next_rho = dot(residual, preconditioned);
        if (!std::isfinite(next_rho) || next_rho <= 0.0) {
            return make_result(
                SolverStatus::indefinite_operator, std::move(solution), iteration,
                initial_residual_inf, residual, last_increment_inf);
        }
        const double beta = next_rho / rho;
        if (!std::isfinite(beta)) {
            return make_result(
                SolverStatus::singularity, std::move(solution), iteration,
                initial_residual_inf, residual, last_increment_inf);
        }
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            direction[index] = preconditioned[index] + beta * direction[index];
        }
        rho = next_rho;
    }
    matvec_unchecked(matrix, solution, product);
    for (std::size_t index = 0U; index < matrix.order; ++index) {
        residual[index] = right_hand_side[index] - product[index];
    }
    return make_result(
        SolverStatus::nonconvergence, std::move(solution), config.max_iterations,
        initial_residual_inf, residual, last_increment_inf);
}

}  // namespace structural::solver_cpu
