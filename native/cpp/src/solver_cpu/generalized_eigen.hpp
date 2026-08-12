#ifndef STRUCTURAL_SOLVER_CPU_GENERALIZED_EIGEN_HPP
#define STRUCTURAL_SOLVER_CPU_GENERALIZED_EIGEN_HPP

#include "sparse_linear.hpp"

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace structural::solver_cpu {

/// Caller-owned row-major dense square matrix view.
struct DenseSymmetricMatrixView {
    std::size_t order;
    std::span<const double> values;
};

/// Shared strict contract for the bounded modal and linear-buckling reference kernels.
struct GeneralizedEigenConfig {
    std::uint32_t mode_count;
    double symmetry_relative_tolerance;
    double positive_semidefinite_relative_tolerance;
    /// Modal: rigid-mode threshold. Buckling: finite reciprocal-mode threshold.
    double mode_relative_tolerance;
    double cluster_relative_tolerance;
    double residual_relative_tolerance;
    double orthogonality_tolerance;
    double eigensolver_relative_tolerance;
    std::uint32_t maximum_sweeps;
};

struct ModalEigenMode {
    double eigenvalue_rad2_per_s2;
    double omega_rad_per_s;
    double frequency_hz;
    double period_s;
    std::vector<double> mass_normalized_shape;
    std::vector<double> max_component_normalized_shape;
    double generalized_mass;
    double generalized_stiffness;
    double residual_relative_inf;
};

struct ModalEigenResult {
    SolverStatus status;
    std::vector<ModalEigenMode> modes;
    std::uint32_t rigid_mode_count;
    std::uint32_t eigensolver_sweeps;
    double mass_orthogonality_error_inf;
    double stiffness_diagonalization_error_inf;
    double stiffness_relative_symmetry_error;
    double mass_relative_symmetry_error;
    double stiffness_minimum_eigenvalue;
    double mass_minimum_eigenvalue;
    std::uint32_t fallback_count;
};

struct BucklingEigenMode {
    double load_factor;
    std::vector<double> stiffness_normalized_shape;
    std::vector<double> max_component_normalized_shape;
    double generalized_elastic_stiffness;
    double generalized_geometric_stiffness;
    double residual_relative_inf;
};

struct BucklingEigenResult {
    SolverStatus status;
    std::vector<BucklingEigenMode> modes;
    std::uint32_t finite_positive_eigenvalue_count;
    std::uint32_t geometric_stiffness_positive_rank;
    std::uint32_t eigensolver_sweeps;
    double critical_load_factor;
    double stiffness_orthogonality_error_inf;
    double geometric_diagonalization_error_inf;
    double stiffness_relative_symmetry_error;
    double geometric_stiffness_relative_symmetry_error;
    double stiffness_minimum_eigenvalue;
    double geometric_stiffness_minimum_eigenvalue;
    std::uint32_t fallback_count;
};

/// Defaults aligned with the strict Python dense generalized-eigen oracle profiles.
[[nodiscard]] GeneralizedEigenConfig default_modal_eigen_config(
    std::uint32_t mode_count) noexcept;

[[nodiscard]] GeneralizedEigenConfig default_buckling_eigen_config(
    std::uint32_t mode_count) noexcept;

/// Solve K phi = omega^2 M phi using a deterministic serial FP64 Jacobi reference path.
///
/// `coordinate_recovery_scale` is empty (identity) or exactly `order` finite positive values.
/// Invalid input and matrix-contract failures throw `std::invalid_argument`. Eigensolver and
/// result-gate failures are returned through `SolverStatus`; no regularization or fallback exists.
[[nodiscard]] ModalEigenResult solve_dense_modal_modes(
    DenseSymmetricMatrixView stiffness,
    DenseSymmetricMatrixView mass,
    std::span<const double> coordinate_recovery_scale,
    const GeneralizedEigenConfig& config);

/// Solve K phi = lambda Kg phi by extracting positive reciprocal modes of Kg phi = mu K phi.
///
/// This bounded reference contract accepts positive-definite K and positive-semidefinite Kg,
/// including rank-deficient Kg. Infinite modes are filtered without regularization or fallback.
[[nodiscard]] BucklingEigenResult solve_dense_linear_buckling(
    DenseSymmetricMatrixView stiffness,
    DenseSymmetricMatrixView geometric_stiffness_per_unit_load,
    std::span<const double> coordinate_recovery_scale,
    const GeneralizedEigenConfig& config);

}  // namespace structural::solver_cpu

#endif
