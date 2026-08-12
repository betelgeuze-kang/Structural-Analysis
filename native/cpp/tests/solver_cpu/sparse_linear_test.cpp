#include "sparse_linear.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace {

using structural::solver_cpu::CsrMatrixView;
using structural::solver_cpu::SolverStatus;
using structural::solver_cpu::SparseLinearConfig;
using structural::solver_cpu::SparseLinearExecutionState;
using structural::solver_cpu::SparseLinearExecutionStatus;

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::invalid_argument&) {
        return;
    }
    expect(false, message);
}

[[nodiscard]] bool nearly_equal(
    const double left,
    const double right,
    const double tolerance = 2.0e-12) {
    return std::abs(left - right) <= tolerance * std::max({1.0, std::abs(left), std::abs(right)});
}

struct OwnedCsr {
    std::size_t order;
    std::vector<std::uint64_t> rows;
    std::vector<std::uint32_t> columns;
    std::vector<double> values;

    [[nodiscard]] CsrMatrixView view() const {
        return {order, rows, columns, values};
    }
};

[[nodiscard]] OwnedCsr spd_five() {
    return {
        5U,
        {0U, 2U, 5U, 8U, 11U, 13U},
        {0U, 1U, 0U, 1U, 2U, 1U, 2U, 3U, 2U, 3U, 4U, 3U, 4U},
        {4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0,
         -1.0, 3.0, -1.0, -1.0, 2.0},
    };
}

[[nodiscard]] SparseLinearConfig config() {
    return {100U, 1.0e-13, 1.0e-13, 0.0};
}

[[nodiscard]] bool solves_spd_and_is_bitwise_deterministic() {
    const auto matrix = spd_five();
    const std::array<double, 5> expected {1.0, -2.0, 3.0, -4.0, 5.0};
    std::array<double, 5> right_hand_side {};
    structural::solver_cpu::csr_matvec(matrix.view(), expected, right_hand_side);
    const auto first = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config());
    const auto second = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config());
    expect(first.status == SolverStatus::converged, "SPD solve must converge");
    expect(first.iterations > 0U && first.iterations <= expected.size(), "bounded PCG iterations");
    expect(first.fallback_count == 0U, "CPU sparse solver fallback must be zero");
    expect(first.final_residual_inf <= 1.0e-11, "SPD final residual");
    for (std::size_t index = 0U; index < expected.size(); ++index) {
        expect(nearly_equal(first.solution[index], expected[index]), "SPD solution parity");
    }
    expect(first.solution == second.solution, "sparse solution must repeat bitwise");
    expect(first.iterations == second.iterations, "sparse iteration count must repeat");
    expect(first.final_residual_inf == second.final_residual_inf, "residual must repeat");
    return true;
}

[[nodiscard]] bool zero_rhs_and_exact_initial_guess_exit_without_iterations() {
    const auto matrix = spd_five();
    const std::array<double, 5> zero {};
    const auto zero_result = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), zero, {}, config());
    expect(zero_result.status == SolverStatus::converged, "zero RHS status");
    expect(zero_result.iterations == 0U, "zero RHS iteration count");
    expect(zero_result.solution == std::vector<double>(5U, 0.0), "zero RHS solution");

    const std::array<double, 5> exact {1.0, 2.0, 3.0, 4.0, 5.0};
    std::array<double, 5> right_hand_side {};
    structural::solver_cpu::csr_matvec(matrix.view(), exact, right_hand_side);
    const auto exact_result = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, exact, config());
    expect(exact_result.status == SolverStatus::converged, "exact initial status");
    expect(exact_result.iterations == 0U, "exact initial iteration count");
    expect(exact_result.solution == std::vector<double>(exact.begin(), exact.end()), "exact initial solution");
    return true;
}

[[nodiscard]] bool canonical_validation_fails_closed() {
    auto matrix = spd_five();
    auto duplicate = matrix;
    duplicate.columns[2] = 1U;
    expect_throws(
        [&duplicate] { structural::solver_cpu::validate_canonical_csr(duplicate.view()); },
        "duplicate/out-of-order CSR columns must fail");

    auto bad_offset = matrix;
    bad_offset.rows.back() += 1U;
    expect_throws(
        [&bad_offset] { structural::solver_cpu::validate_canonical_csr(bad_offset.view()); },
        "CSR terminal offset must fail");

    auto nonfinite = matrix;
    nonfinite.values[0] = std::numeric_limits<double>::quiet_NaN();
    expect_throws(
        [&nonfinite] { structural::solver_cpu::validate_canonical_csr(nonfinite.view()); },
        "non-finite CSR value must fail");

    auto asymmetric = matrix;
    asymmetric.values[2] = -2.0;
    const std::array<double, 5> rhs {1.0, 2.0, 3.0, 4.0, 5.0};
    expect_throws(
        [&asymmetric, &rhs] {
            static_cast<void>(structural::solver_cpu::solve_sparse_spd_pcg(
                asymmetric.view(), rhs, {}, config()));
        },
        "asymmetric PCG input must fail before execution");

    const OwnedCsr lower_only {
        2U,
        {0U, 1U, 3U},
        {0U, 0U, 1U},
        {2.0, -1.0, 2.0},
    };
    const std::array<double, 2> lower_rhs {1.0, 1.0};
    expect_throws(
        [&lower_only, &lower_rhs] {
            static_cast<void>(structural::solver_cpu::solve_sparse_spd_pcg(
                lower_only.view(), lower_rhs, {}, config()));
        },
        "one-sided lower CSR structure must fail symmetry validation");
    return true;
}

[[nodiscard]] bool numerical_status_taxonomy_is_stable() {
    const std::array<std::uint64_t, 3> rows {0U, 1U, 2U};
    const std::array<std::uint32_t, 2> columns {0U, 1U};
    const std::array<double, 2> singular_values {0.0, 1.0};
    const std::array<double, 2> indefinite_values {-1.0, 2.0};
    const std::array<double, 2> rhs {1.0, 1.0};
    const CsrMatrixView singular {2U, rows, columns, singular_values};
    const CsrMatrixView indefinite {2U, rows, columns, indefinite_values};
    expect(
        structural::solver_cpu::solve_sparse_spd_pcg(singular, rhs, {}, config()).status
            == SolverStatus::singularity,
        "zero diagonal must be singularity");
    expect(
        structural::solver_cpu::solve_sparse_spd_pcg(indefinite, rhs, {}, config()).status
            == SolverStatus::indefinite_operator,
        "negative diagonal must be indefinite operator");

    const auto matrix = spd_five();
    const std::array<double, 5> full_rhs {1.0, 2.0, 3.0, 4.0, 5.0};
    auto limited_iterations = config();
    limited_iterations.max_iterations = 1U;
    expect(
        structural::solver_cpu::solve_sparse_spd_pcg(
            matrix.view(), full_rhs, {}, limited_iterations).status
            == SolverStatus::nonconvergence,
        "iteration exhaustion must be nonconvergence");
    auto limited_increment = config();
    limited_increment.maximum_increment = 1.0e-20;
    const auto increment = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), full_rhs, {}, limited_increment);
    expect(increment.status == SolverStatus::increment_limit, "increment guard taxonomy");
    expect(increment.iterations == 0U, "rejected increment is not published");
    expect(increment.solution == std::vector<double>(5U, 0.0), "increment failure atomicity");
    return true;
}

void expect_same_state(
    const SparseLinearExecutionState& left,
    const SparseLinearExecutionState& right,
    const std::string_view message) {
    expect(left.execution_status == right.execution_status, message);
    expect(left.solver_status == right.solver_status, message);
    expect(left.iterations == right.iterations, message);
    expect(left.initial_residual_inf == right.initial_residual_inf, message);
    expect(left.convergence_limit == right.convergence_limit, message);
    expect(left.rho == right.rho, message);
    expect(left.last_increment_inf == right.last_increment_inf, message);
    expect(left.solution == right.solution, message);
    expect(left.residual == right.residual, message);
    expect(left.direction == right.direction, message);
    expect(left.diagonal_inverse == right.diagonal_inverse, message);
}

[[nodiscard]] bool restart_boundaries_are_complete_and_bitwise_stable() {
    const auto matrix = spd_five();
    const std::array<double, 5> expected {1.0, -2.0, 3.0, -4.0, 5.0};
    std::array<double, 5> right_hand_side {};
    structural::solver_cpu::csr_matvec(matrix.view(), expected, right_hand_side);

    auto direct = structural::solver_cpu::begin_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config());
    auto segmented = direct;
    const auto unchanged = segmented;
    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 0U, segmented);
    expect_same_state(segmented, unchanged, "zero-budget PCG advance must be a no-op");
    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 1U, segmented);
    expect(
        segmented.execution_status == SparseLinearExecutionStatus::active,
        "one PCG iteration must expose an active restart boundary");
    expect(segmented.iterations == 1U, "one PCG iteration must be published");
    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 1U, segmented);
    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 100U, segmented);

    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 100U, direct);
    expect_same_state(segmented, direct, "segmented PCG restart must match direct execution");
    expect(
        direct.execution_status == SparseLinearExecutionStatus::terminal
            && direct.solver_status == SolverStatus::converged,
        "direct PCG restart execution must converge");
    const auto terminal = direct;
    structural::solver_cpu::advance_sparse_spd_pcg(
        matrix.view(), right_hand_side, config(), 1U, direct);
    expect_same_state(direct, terminal, "terminal PCG advance must be idempotent");

    const auto projected = structural::solver_cpu::sparse_linear_result(direct);
    const auto one_shot = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config());
    expect(projected.solution == one_shot.solution, "restart projection solution parity");
    expect(projected.iterations == one_shot.iterations, "restart projection iteration parity");
    expect(
        projected.final_residual_inf == one_shot.final_residual_inf,
        "restart projection residual parity");

    auto corrupt = structural::solver_cpu::begin_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config());
    corrupt.rho = std::numeric_limits<double>::quiet_NaN();
    expect_throws(
        [&matrix, &right_hand_side, &corrupt] {
            structural::solver_cpu::advance_sparse_spd_pcg(
                matrix.view(), right_hand_side, config(), 0U, corrupt);
        },
        "non-finite PCG restart scalar must fail closed");
    return true;
}

}  // namespace

int main() {
    const std::array tests {
        solves_spd_and_is_bitwise_deterministic,
        zero_rhs_and_exact_initial_guess_exit_without_iterations,
        canonical_validation_fails_closed,
        numerical_status_taxonomy_is_stable,
        restart_boundaries_are_complete_and_bitwise_stable,
    };
    for (const auto test : tests) {
        if (!test()) {
            return EXIT_FAILURE;
        }
    }
    return EXIT_SUCCESS;
}
