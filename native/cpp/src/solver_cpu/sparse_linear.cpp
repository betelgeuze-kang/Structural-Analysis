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

void make_terminal(
    SparseLinearExecutionState& state,
    const SolverStatus status) noexcept {
    state.execution_status = SparseLinearExecutionStatus::terminal;
    state.solver_status = status;
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

void validate_sparse_spd_problem(
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
}

SparseLinearExecutionState begin_sparse_spd_pcg(
    const CsrMatrixView matrix,
    const std::span<const double> right_hand_side,
    const std::span<const double> initial_guess,
    const SparseLinearConfig& config) {
    validate_sparse_spd_problem(matrix, right_hand_side, initial_guess, config);

    SparseLinearExecutionState state {
        SparseLinearExecutionStatus::active,
        SolverStatus::nonconvergence,
        0U,
        0.0,
        config.absolute_residual_tolerance
            + config.relative_residual_tolerance * norm_inf(right_hand_side),
        0.0,
        0.0,
        std::vector<double>(matrix.order, 0.0),
        std::vector<double>(matrix.order, 0.0),
        std::vector<double>(matrix.order, 0.0),
        std::vector<double>(matrix.order, 0.0),
    };
    if (!initial_guess.empty()) {
        std::copy(initial_guess.begin(), initial_guess.end(), state.solution.begin());
    }
    std::vector<double> product(matrix.order, 0.0);
    matvec_unchecked(matrix, state.solution, product);
    for (std::size_t index = 0U; index < matrix.order; ++index) {
        state.residual[index] = right_hand_side[index] - product[index];
    }
    state.initial_residual_inf = norm_inf(state.residual);

    for (std::size_t row = 0U; row < matrix.order; ++row) {
        const auto diagonal_offset =
            find_column(matrix, row, static_cast<std::uint32_t>(row));
        if (diagonal_offset == matrix.values.size()
            || matrix.values[diagonal_offset] == 0.0) {
            make_terminal(state, SolverStatus::singularity);
            return state;
        }
        if (matrix.values[diagonal_offset] < 0.0) {
            make_terminal(state, SolverStatus::indefinite_operator);
            return state;
        }
        state.diagonal_inverse[row] = 1.0 / matrix.values[diagonal_offset];
        if (!std::isfinite(state.diagonal_inverse[row])) {
            make_terminal(state, SolverStatus::singularity);
            return state;
        }
    }
    if (state.initial_residual_inf <= state.convergence_limit) {
        make_terminal(state, SolverStatus::converged);
        return state;
    }

    std::vector<double> preconditioned(matrix.order, 0.0);
    for (std::size_t index = 0U; index < matrix.order; ++index) {
        preconditioned[index] = state.diagonal_inverse[index] * state.residual[index];
        state.direction[index] = preconditioned[index];
    }
    state.rho = dot(state.residual, preconditioned);
    if (!std::isfinite(state.rho) || state.rho <= 0.0) {
        make_terminal(state, SolverStatus::indefinite_operator);
    }
    return state;
}

void advance_sparse_spd_pcg(
    const CsrMatrixView matrix,
    const std::span<const double> right_hand_side,
    const SparseLinearConfig& config,
    const std::uint32_t iteration_budget,
    SparseLinearExecutionState& state) {
    validate_sparse_spd_problem(matrix, right_hand_side, {}, config);
    const bool lengths_valid = state.solution.size() == matrix.order
        && state.residual.size() == matrix.order
        && state.direction.size() == matrix.order
        && state.diagonal_inverse.size() == matrix.order;
    const bool scalars_valid = std::isfinite(state.initial_residual_inf)
        && std::isfinite(state.convergence_limit) && std::isfinite(state.rho)
        && std::isfinite(state.last_increment_inf)
        && state.initial_residual_inf >= 0.0 && state.convergence_limit >= 0.0
        && state.last_increment_inf >= 0.0;
    const bool vectors_valid = all_finite(state.solution) && all_finite(state.residual)
        && all_finite(state.direction) && all_finite(state.diagonal_inverse);
    const double expected_limit = config.absolute_residual_tolerance
        + config.relative_residual_tolerance * norm_inf(right_hand_side);
    const bool metadata_valid = state.execution_status == SparseLinearExecutionStatus::active
        || state.execution_status == SparseLinearExecutionStatus::terminal;
    if (!lengths_valid || !scalars_valid || !vectors_valid || !metadata_valid
        || state.iterations > config.max_iterations
        || state.convergence_limit != expected_limit) {
        throw std::invalid_argument("sparse PCG restart state is invalid");
    }
    if (state.execution_status == SparseLinearExecutionStatus::terminal) {
        return;
    }
    if (state.rho <= 0.0 || state.iterations >= config.max_iterations
        || norm_inf(state.residual) <= state.convergence_limit
        || std::any_of(
            state.diagonal_inverse.begin(), state.diagonal_inverse.end(),
            [](const double value) { return value <= 0.0; })) {
        throw std::invalid_argument("active sparse PCG restart state is inconsistent");
    }

    std::vector<double> operator_direction(matrix.order, 0.0);
    std::vector<double> candidate(matrix.order, 0.0);
    std::vector<double> preconditioned(matrix.order, 0.0);
    std::vector<double> product(matrix.order, 0.0);
    const auto remaining = config.max_iterations - state.iterations;
    const auto to_run = std::min(iteration_budget, remaining);
    for (std::uint32_t offset = 0U; offset < to_run; ++offset) {
        const auto iteration = state.iterations + 1U;
        matvec_unchecked(matrix, state.direction, operator_direction);
        const double denominator = dot(state.direction, operator_direction);
        const double breakdown_scale =
            kBreakdownFactor * std::numeric_limits<double>::epsilon()
            * std::max(1.0, norm_l2(state.direction) * norm_l2(operator_direction));
        if (!std::isfinite(denominator) || denominator <= breakdown_scale) {
            const auto status = denominator < -breakdown_scale
                ? SolverStatus::indefinite_operator
                : SolverStatus::singularity;
            make_terminal(state, status);
            return;
        }
        const double alpha = state.rho / denominator;
        if (!std::isfinite(alpha)) {
            make_terminal(state, SolverStatus::singularity);
            return;
        }
        state.last_increment_inf = 0.0;
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            const double increment = alpha * state.direction[index];
            state.last_increment_inf = std::max(state.last_increment_inf, std::abs(increment));
            candidate[index] = state.solution[index] + increment;
        }
        if (config.maximum_increment > 0.0
            && state.last_increment_inf > config.maximum_increment) {
            make_terminal(state, SolverStatus::increment_limit);
            return;
        }
        state.solution.swap(candidate);
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            state.residual[index] -= alpha * operator_direction[index];
        }
        state.iterations = iteration;
        if (norm_inf(state.residual) <= state.convergence_limit) {
            matvec_unchecked(matrix, state.solution, product);
            for (std::size_t index = 0U; index < matrix.order; ++index) {
                state.residual[index] = right_hand_side[index] - product[index];
            }
            const auto status = norm_inf(state.residual) <= state.convergence_limit
                ? SolverStatus::converged
                : SolverStatus::residual_limit;
            make_terminal(state, status);
            return;
        }
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            preconditioned[index] = state.diagonal_inverse[index] * state.residual[index];
        }
        const double next_rho = dot(state.residual, preconditioned);
        if (!std::isfinite(next_rho) || next_rho <= 0.0) {
            make_terminal(state, SolverStatus::indefinite_operator);
            return;
        }
        const double beta = next_rho / state.rho;
        if (!std::isfinite(beta)) {
            make_terminal(state, SolverStatus::singularity);
            return;
        }
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            state.direction[index] = preconditioned[index] + beta * state.direction[index];
        }
        state.rho = next_rho;
    }
    if (state.iterations == config.max_iterations) {
        matvec_unchecked(matrix, state.solution, product);
        for (std::size_t index = 0U; index < matrix.order; ++index) {
            state.residual[index] = right_hand_side[index] - product[index];
        }
        make_terminal(state, SolverStatus::nonconvergence);
    }
}

SparseLinearResult sparse_linear_result(const SparseLinearExecutionState& state) {
    if (state.execution_status != SparseLinearExecutionStatus::terminal) {
        throw std::invalid_argument("sparse PCG result requires a terminal state");
    }
    return make_result(
        state.solver_status, state.solution, state.iterations,
        state.initial_residual_inf, state.residual, state.last_increment_inf);
}

SparseLinearResult solve_sparse_spd_pcg(
    const CsrMatrixView matrix,
    const std::span<const double> right_hand_side,
    const std::span<const double> initial_guess,
    const SparseLinearConfig& config) {
    auto state = begin_sparse_spd_pcg(matrix, right_hand_side, initial_guess, config);
    advance_sparse_spd_pcg(matrix, right_hand_side, config, config.max_iterations, state);
    return sparse_linear_result(state);
}

}  // namespace structural::solver_cpu
