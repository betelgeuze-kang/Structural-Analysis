#ifndef STRUCTURAL_SOLVER_CPU_SPARSE_LINEAR_HPP
#define STRUCTURAL_SOLVER_CPU_SPARSE_LINEAR_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace structural::solver_cpu {

/// Stable numerical outcome taxonomy shared by the bounded sparse solver families.
enum class SolverStatus : std::uint32_t {
    converged = 0U,
    invalid_input = 1U,
    singularity = 2U,
    indefinite_operator = 3U,
    nonconvergence = 4U,
    increment_limit = 5U,
    residual_limit = 6U,
    cancelled = 7U,
    checkpoint_mismatch = 8U,
    backend_unavailable = 9U,
};

/// Caller-owned canonical CSR view. Rows must contain strictly increasing column indices.
struct CsrMatrixView {
    std::size_t order;
    std::span<const std::uint64_t> row_offsets;
    std::span<const std::uint32_t> column_indices;
    std::span<const double> values;
};

struct SparseLinearConfig {
    std::uint32_t max_iterations;
    double absolute_residual_tolerance;
    double relative_residual_tolerance;
    /// Zero disables the guard. A positive value rejects an iteration before it is published.
    double maximum_increment;
};

struct SparseLinearResult {
    SolverStatus status;
    std::vector<double> solution;
    std::uint32_t iterations;
    double initial_residual_inf;
    double final_residual_inf;
    double final_residual_l2;
    double last_increment_inf;
    std::uint32_t fallback_count;
};

enum class SparseLinearExecutionStatus : std::uint32_t {
    active = 0U,
    terminal = 1U,
};

/// Complete caller-serializable PCG state at an iteration boundary.
///
/// Scratch vectors used inside one iteration are deliberately excluded: an advance either stops
/// before publishing an iteration or publishes every value below for the next boundary.
struct SparseLinearExecutionState {
    SparseLinearExecutionStatus execution_status;
    SolverStatus solver_status;
    std::uint32_t iterations;
    double initial_residual_inf;
    double convergence_limit;
    double rho;
    double last_increment_inf;
    std::vector<double> solution;
    std::vector<double> residual;
    std::vector<double> direction;
    std::vector<double> diagonal_inverse;
};

/// Validate dimensions, bounds, finite values and canonical per-row ordering.
///
/// Structural input failures throw `std::invalid_argument`; numerical solver outcomes are returned
/// through `SolverStatus` so later ABI layers can map them without parsing exception text.
void validate_canonical_csr(CsrMatrixView matrix);

/// Deterministic serial FP64 CSR matrix-vector product.
void csr_matvec(
    CsrMatrixView matrix,
    std::span<const double> input,
    std::span<double> output);

/// Validate the complete SPD/PCG problem without performing a numerical solve.
///
/// CPU and accelerator backends call this shared source so canonical CSR, symmetry, finite
/// values, vector lengths and convergence configuration cannot drift between implementations.
void validate_sparse_spd_problem(
    CsrMatrixView matrix,
    std::span<const double> right_hand_side,
    std::span<const double> initial_guess,
    const SparseLinearConfig& config);

/// Construct the deterministic iteration-zero PCG boundary.
///
/// Singular, indefinite and already-converged problems are represented as terminal states rather
/// than exceptions. Structural input failures throw `std::invalid_argument`.
[[nodiscard]] SparseLinearExecutionState begin_sparse_spd_pcg(
    CsrMatrixView matrix,
    std::span<const double> right_hand_side,
    std::span<const double> initial_guess,
    const SparseLinearConfig& config);

/// Validate and advance an existing PCG state by at most `iteration_budget` boundaries.
///
/// A zero budget performs deterministic validation only. Terminal states are idempotent. State is
/// updated only at a complete iteration boundary, making every returned active state restartable.
void advance_sparse_spd_pcg(
    CsrMatrixView matrix,
    std::span<const double> right_hand_side,
    const SparseLinearConfig& config,
    std::uint32_t iteration_budget,
    SparseLinearExecutionState& state);

/// Project a terminal execution state into the stable one-shot result contract.
[[nodiscard]] SparseLinearResult sparse_linear_result(
    const SparseLinearExecutionState& state);

/// Solve a symmetric positive-definite canonical CSR system using Jacobi-preconditioned CG.
///
/// The operation has no fallback path. `initial_guess` may be empty (all-zero) or exactly `order`
/// values. Invalid input throws before a result is returned; numerical failure returns the last
/// fully published iterate with a stable status.
[[nodiscard]] SparseLinearResult solve_sparse_spd_pcg(
    CsrMatrixView matrix,
    std::span<const double> right_hand_side,
    std::span<const double> initial_guess,
    const SparseLinearConfig& config);

}  // namespace structural::solver_cpu

#endif
