#include "generalized_eigen.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numbers>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace structural::solver_cpu {
namespace {

constexpr std::size_t kMaximumOrder = 128U;
constexpr std::uint32_t kMaximumSweeps = 4'096U;
constexpr double kCanonicalBasisTolerance = 1.0e-12;

class Matrix {
public:
    explicit Matrix(const std::size_t order, const double initial = 0.0)
        : order_(order), values_(order * order, initial) {}

    [[nodiscard]] std::size_t order() const noexcept { return order_; }
    [[nodiscard]] const std::vector<double>& values() const noexcept { return values_; }

    [[nodiscard]] double& operator()(const std::size_t row, const std::size_t column) noexcept {
        return values_[row * order_ + column];
    }

    [[nodiscard]] double operator()(
        const std::size_t row,
        const std::size_t column) const noexcept {
        return values_[row * order_ + column];
    }

    [[nodiscard]] static Matrix identity(const std::size_t order) {
        Matrix result(order);
        for (std::size_t index = 0U; index < order; ++index) {
            result(index, index) = 1.0;
        }
        return result;
    }

private:
    std::size_t order_;
    std::vector<double> values_;
};

struct SymmetricProjection {
    Matrix matrix;
    double relative_error;
};

struct SymmetricEigenResult {
    bool converged;
    std::vector<double> values;
    Matrix vectors;
    std::uint32_t sweeps;
};

[[nodiscard]] bool finite(const double value) noexcept {
    return std::isfinite(value);
}

[[nodiscard]] double max_abs(const std::span<const double> values) noexcept {
    double result = 0.0;
    for (const double value : values) {
        result = std::max(result, std::abs(value));
    }
    return result;
}

void validate_config(
    const GeneralizedEigenConfig& config,
    const std::size_t order) {
    if (config.mode_count == 0U || config.mode_count > order
        || config.maximum_sweeps == 0U || config.maximum_sweeps > kMaximumSweeps
        || !finite(config.symmetry_relative_tolerance)
        || !finite(config.positive_semidefinite_relative_tolerance)
        || !finite(config.mode_relative_tolerance)
        || !finite(config.cluster_relative_tolerance)
        || !finite(config.residual_relative_tolerance)
        || !finite(config.orthogonality_tolerance)
        || !finite(config.eigensolver_relative_tolerance)
        || config.symmetry_relative_tolerance < 0.0
        || config.positive_semidefinite_relative_tolerance < 0.0
        || config.mode_relative_tolerance < 0.0
        || config.cluster_relative_tolerance < 0.0
        || config.residual_relative_tolerance < 0.0
        || config.orthogonality_tolerance < 0.0
        || config.eigensolver_relative_tolerance <= 0.0) {
        throw std::invalid_argument("generalized-eigen configuration is invalid");
    }
}

[[nodiscard]] SymmetricProjection validate_and_project_symmetric(
    const DenseSymmetricMatrixView input,
    const std::string_view name,
    const double tolerance) {
    if (input.order == 0U || input.order > kMaximumOrder
        || input.order > std::numeric_limits<std::size_t>::max() / input.order
        || input.values.size() != input.order * input.order) {
        throw std::invalid_argument(
            std::string(name) + " must be a bounded non-empty dense square matrix");
    }
    for (const double value : input.values) {
        if (!finite(value)) {
            throw std::invalid_argument(
                std::string(name) + " must contain only finite binary64 values");
        }
    }
    Matrix projected(input.order);
    double maximum_error = 0.0;
    for (std::size_t row = 0U; row < input.order; ++row) {
        for (std::size_t column = 0U; column < input.order; ++column) {
            const double left = input.values[row * input.order + column];
            const double right = input.values[column * input.order + row];
            maximum_error = std::max(maximum_error, std::abs(left - right));
            projected(row, column) = 0.5 * (left + right);
        }
    }
    const double scale = std::max(
        max_abs(input.values), std::numeric_limits<double>::min());
    const double relative_error = maximum_error / scale;
    if (relative_error > tolerance) {
        throw std::invalid_argument(
            std::string(name) + " relative symmetry error exceeds the contract");
    }
    return {std::move(projected), relative_error};
}

[[nodiscard]] std::vector<double> validate_recovery_scale(
    const std::span<const double> input,
    const std::size_t order) {
    if (!input.empty() && input.size() != order) {
        throw std::invalid_argument(
            "coordinate recovery scale must be empty or match the matrix order");
    }
    std::vector<double> result(order, 1.0);
    if (!input.empty()) {
        for (std::size_t index = 0U; index < order; ++index) {
            if (!finite(input[index]) || input[index] <= 0.0) {
                throw std::invalid_argument(
                    "coordinate recovery scale must contain finite positive values");
            }
            result[index] = input[index];
        }
    }
    return result;
}

[[nodiscard]] Matrix congruence_scale(
    const Matrix& matrix,
    const std::span<const double> scale) {
    Matrix result(matrix.order());
    for (std::size_t row = 0U; row < matrix.order(); ++row) {
        for (std::size_t column = 0U; column < matrix.order(); ++column) {
            result(row, column) = scale[row] * matrix(row, column) * scale[column];
            if (!finite(result(row, column))) {
                throw std::invalid_argument(
                    "coordinate-scaled generalized-eigen matrix is not finite");
            }
        }
    }
    return result;
}

[[nodiscard]] SymmetricEigenResult symmetric_eigen_jacobi(
    Matrix matrix,
    const double relative_tolerance,
    const std::uint32_t maximum_sweeps) {
    const std::size_t order = matrix.order();
    Matrix vectors = Matrix::identity(order);
    std::uint32_t completed_sweeps = 0U;
    bool converged = order == 1U;
    for (std::uint32_t sweep = 0U; sweep < maximum_sweeps && !converged; ++sweep) {
        double off_diagonal = 0.0;
        double diagonal_scale = 0.0;
        for (std::size_t row = 0U; row < order; ++row) {
            diagonal_scale = std::max(diagonal_scale, std::abs(matrix(row, row)));
            for (std::size_t column = row + 1U; column < order; ++column) {
                off_diagonal = std::max(off_diagonal, std::abs(matrix(row, column)));
            }
        }
        const double limit = relative_tolerance
            * std::max(diagonal_scale, std::numeric_limits<double>::min());
        if (off_diagonal <= limit) {
            converged = true;
            break;
        }
        for (std::size_t left = 0U; left < order; ++left) {
            for (std::size_t right = left + 1U; right < order; ++right) {
                const double cross = matrix(left, right);
                if (std::abs(cross) <= limit) {
                    continue;
                }
                const double diagonal_left = matrix(left, left);
                const double diagonal_right = matrix(right, right);
                const double tau = (diagonal_right - diagonal_left) / (2.0 * cross);
                const double tangent = std::copysign(
                    1.0 / (std::abs(tau) + std::hypot(1.0, tau)), tau);
                const double cosine = 1.0 / std::sqrt(1.0 + tangent * tangent);
                const double sine = tangent * cosine;
                matrix(left, left) = diagonal_left - tangent * cross;
                matrix(right, right) = diagonal_right + tangent * cross;
                matrix(left, right) = 0.0;
                matrix(right, left) = 0.0;
                for (std::size_t index = 0U; index < order; ++index) {
                    if (index == left || index == right) {
                        continue;
                    }
                    const double value_left = matrix(index, left);
                    const double value_right = matrix(index, right);
                    const double rotated_left = cosine * value_left - sine * value_right;
                    const double rotated_right = sine * value_left + cosine * value_right;
                    matrix(index, left) = rotated_left;
                    matrix(left, index) = rotated_left;
                    matrix(index, right) = rotated_right;
                    matrix(right, index) = rotated_right;
                }
                for (std::size_t index = 0U; index < order; ++index) {
                    const double value_left = vectors(index, left);
                    const double value_right = vectors(index, right);
                    vectors(index, left) = cosine * value_left - sine * value_right;
                    vectors(index, right) = sine * value_left + cosine * value_right;
                }
            }
        }
        completed_sweeps = sweep + 1U;
    }
    if (!converged) {
        double off_diagonal = 0.0;
        double diagonal_scale = 0.0;
        for (std::size_t row = 0U; row < order; ++row) {
            diagonal_scale = std::max(diagonal_scale, std::abs(matrix(row, row)));
            for (std::size_t column = row + 1U; column < order; ++column) {
                off_diagonal = std::max(off_diagonal, std::abs(matrix(row, column)));
            }
        }
        converged = off_diagonal
            <= relative_tolerance
                * std::max(diagonal_scale, std::numeric_limits<double>::min());
    }

    std::vector<double> diagonal(order, 0.0);
    for (std::size_t index = 0U; index < order; ++index) {
        diagonal[index] = matrix(index, index);
    }
    std::vector<std::size_t> permutation(order, 0U);
    std::iota(permutation.begin(), permutation.end(), 0U);
    std::stable_sort(
        permutation.begin(), permutation.end(),
        [&diagonal](const std::size_t left, const std::size_t right) {
            return diagonal[left] < diagonal[right];
        });
    std::vector<double> sorted_values(order, 0.0);
    Matrix sorted_vectors(order);
    for (std::size_t column = 0U; column < order; ++column) {
        sorted_values[column] = diagonal[permutation[column]];
        for (std::size_t row = 0U; row < order; ++row) {
            sorted_vectors(row, column) = vectors(row, permutation[column]);
        }
    }
    return {
        converged,
        std::move(sorted_values),
        std::move(sorted_vectors),
        completed_sweeps,
    };
}

[[nodiscard]] Matrix cholesky_lower(const Matrix& matrix, const std::string_view name) {
    Matrix lower(matrix.order());
    for (std::size_t row = 0U; row < matrix.order(); ++row) {
        for (std::size_t column = 0U; column <= row; ++column) {
            double value = matrix(row, column);
            for (std::size_t inner = 0U; inner < column; ++inner) {
                value -= lower(row, inner) * lower(column, inner);
            }
            if (row == column) {
                if (!finite(value) || value <= 0.0) {
                    throw std::invalid_argument(
                        std::string(name) + " must be positive definite");
                }
                lower(row, column) = std::sqrt(value);
            } else {
                lower(row, column) = value / lower(column, column);
            }
        }
    }
    return lower;
}

[[nodiscard]] Matrix inverse_lower(const Matrix& lower) {
    Matrix inverse(lower.order());
    for (std::size_t column = 0U; column < lower.order(); ++column) {
        for (std::size_t row = 0U; row < lower.order(); ++row) {
            double value = row == column ? 1.0 : 0.0;
            for (std::size_t inner = 0U; inner < row; ++inner) {
                value -= lower(row, inner) * inverse(inner, column);
            }
            inverse(row, column) = value / lower(row, row);
            if (!finite(inverse(row, column))) {
                throw std::invalid_argument(
                    "positive-definite generalized-eigen metric is numerically singular");
            }
        }
    }
    return inverse;
}

[[nodiscard]] Matrix multiply(const Matrix& left, const Matrix& right) {
    Matrix result(left.order());
    for (std::size_t row = 0U; row < left.order(); ++row) {
        for (std::size_t column = 0U; column < left.order(); ++column) {
            double value = 0.0;
            for (std::size_t inner = 0U; inner < left.order(); ++inner) {
                value += left(row, inner) * right(inner, column);
            }
            result(row, column) = value;
        }
    }
    return result;
}

[[nodiscard]] Matrix multiply_right_transpose(
    const Matrix& left,
    const Matrix& right) {
    Matrix result(left.order());
    for (std::size_t row = 0U; row < left.order(); ++row) {
        for (std::size_t column = 0U; column < left.order(); ++column) {
            double value = 0.0;
            for (std::size_t inner = 0U; inner < left.order(); ++inner) {
                value += left(row, inner) * right(column, inner);
            }
            result(row, column) = value;
        }
    }
    for (std::size_t row = 0U; row < result.order(); ++row) {
        for (std::size_t column = row + 1U; column < result.order(); ++column) {
            const double projected = 0.5 * (result(row, column) + result(column, row));
            result(row, column) = projected;
            result(column, row) = projected;
        }
    }
    return result;
}

[[nodiscard]] Matrix transform_generalized_operator(
    const Matrix& operator_matrix,
    const Matrix& metric_lower_inverse) {
    return multiply_right_transpose(
        multiply(metric_lower_inverse, operator_matrix), metric_lower_inverse);
}

[[nodiscard]] std::vector<double> recover_generalized_vector(
    const Matrix& lower_inverse,
    const std::span<const double> transformed_vector) {
    std::vector<double> result(lower_inverse.order(), 0.0);
    for (std::size_t row = 0U; row < lower_inverse.order(); ++row) {
        for (std::size_t inner = 0U; inner < lower_inverse.order(); ++inner) {
            result[row] += lower_inverse(inner, row) * transformed_vector[inner];
        }
    }
    return result;
}

[[nodiscard]] std::vector<double> matrix_vector(
    const Matrix& matrix,
    const std::span<const double> vector) {
    std::vector<double> result(matrix.order(), 0.0);
    for (std::size_t row = 0U; row < matrix.order(); ++row) {
        for (std::size_t column = 0U; column < matrix.order(); ++column) {
            result[row] += matrix(row, column) * vector[column];
        }
    }
    return result;
}

[[nodiscard]] double dot(
    const std::span<const double> left,
    const std::span<const double> right) noexcept {
    double result = 0.0;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        result += left[index] * right[index];
    }
    return result;
}

[[nodiscard]] double metric_dot(
    const std::span<const double> left,
    const Matrix& metric,
    const std::span<const double> right) {
    return dot(left, matrix_vector(metric, right));
}

[[nodiscard]] double vector_inf(const std::span<const double> vector) noexcept {
    return max_abs(vector);
}

void canonicalize_sign(std::vector<double>& vector) noexcept {
    std::size_t pivot = 0U;
    for (std::size_t index = 1U; index < vector.size(); ++index) {
        if (std::abs(vector[index]) > std::abs(vector[pivot])) {
            pivot = index;
        }
    }
    if (vector[pivot] < 0.0) {
        for (double& value : vector) {
            value = -value;
        }
    }
}

[[nodiscard]] std::vector<std::vector<double>> metric_orthonormalize(
    const std::vector<std::vector<double>>& candidates,
    const Matrix& metric,
    const std::size_t required_count) {
    std::vector<std::vector<double>> accepted;
    accepted.reserve(required_count);
    for (const auto& candidate : candidates) {
        if (candidate.size() != metric.order()) {
            continue;
        }
        std::vector<double> vector = candidate;
        for (int pass = 0; pass < 2; ++pass) {
            for (const auto& prior : accepted) {
                const double projection = metric_dot(prior, metric, vector);
                for (std::size_t index = 0U; index < vector.size(); ++index) {
                    vector[index] -= prior[index] * projection;
                }
            }
        }
        const double norm_squared = metric_dot(vector, metric, vector);
        if (!finite(norm_squared)
            || norm_squared <= kCanonicalBasisTolerance * kCanonicalBasisTolerance) {
            continue;
        }
        const double inverse_norm = 1.0 / std::sqrt(norm_squared);
        for (double& value : vector) {
            value *= inverse_norm;
        }
        canonicalize_sign(vector);
        accepted.push_back(std::move(vector));
        if (accepted.size() == required_count) {
            break;
        }
    }
    if (accepted.size() != required_count) {
        throw std::runtime_error(
            "coordinate-axis eigenspace canonicalization lost rank");
    }
    return accepted;
}

[[nodiscard]] std::vector<std::vector<double>> canonicalize_eigenspace(
    const std::vector<std::vector<double>>& basis,
    const Matrix& metric) {
    const auto orthonormal = metric_orthonormalize(basis, metric, basis.size());
    std::vector<std::vector<double>> axis_projections;
    axis_projections.reserve(metric.order());
    for (std::size_t coordinate = 0U; coordinate < metric.order(); ++coordinate) {
        std::vector<double> candidate(metric.order(), 0.0);
        for (const auto& vector : orthonormal) {
            double coefficient = 0.0;
            for (std::size_t row = 0U; row < metric.order(); ++row) {
                coefficient += vector[row] * metric(row, coordinate);
            }
            for (std::size_t row = 0U; row < metric.order(); ++row) {
                candidate[row] += vector[row] * coefficient;
            }
        }
        axis_projections.push_back(std::move(candidate));
    }
    return metric_orthonormalize(axis_projections, metric, basis.size());
}

[[nodiscard]] bool same_cluster(
    const double left,
    const double right,
    const double relative_tolerance) noexcept {
    const double scale = std::max({std::abs(left), std::abs(right), 1.0});
    return std::abs(right - left) <= relative_tolerance * scale;
}

void require_complete_cluster_selection(
    const std::span<const double> sorted_values,
    const std::size_t selected_count,
    const double tolerance) {
    if (selected_count < sorted_values.size()
        && same_cluster(
            sorted_values[selected_count - 1U], sorted_values[selected_count], tolerance)) {
        throw std::invalid_argument(
            "requested mode_count cuts a repeated or clustered eigenvalue group");
    }
}

[[nodiscard]] std::vector<double> max_component_normalized(
    const std::span<const double> vector) {
    const double scale = vector_inf(vector);
    if (!finite(scale) || scale <= 0.0) {
        throw std::runtime_error("mode vector cannot be normalized");
    }
    std::vector<double> result(vector.begin(), vector.end());
    for (double& value : result) {
        value /= scale;
    }
    return result;
}

[[nodiscard]] double gram_error_identity(
    const std::vector<std::vector<double>>& columns,
    const Matrix& metric) {
    double error = 0.0;
    for (std::size_t row = 0U; row < columns.size(); ++row) {
        for (std::size_t column = 0U; column < columns.size(); ++column) {
            const double expected = row == column ? 1.0 : 0.0;
            error = std::max(
                error,
                std::abs(metric_dot(columns[row], metric, columns[column]) - expected));
        }
    }
    return error;
}

[[nodiscard]] double gram_error_diagonal(
    const std::vector<std::vector<double>>& columns,
    const Matrix& operator_matrix,
    const std::span<const double> expected_diagonal) {
    double error = 0.0;
    for (std::size_t row = 0U; row < columns.size(); ++row) {
        for (std::size_t column = 0U; column < columns.size(); ++column) {
            const double expected = row == column ? expected_diagonal[row] : 0.0;
            error = std::max(
                error,
                std::abs(metric_dot(
                    columns[row], operator_matrix, columns[column]) - expected));
        }
    }
    return error;
}

[[nodiscard]] std::uint32_t add_sweeps(
    const std::uint32_t left,
    const std::uint32_t right) noexcept {
    return left > std::numeric_limits<std::uint32_t>::max() - right
        ? std::numeric_limits<std::uint32_t>::max()
        : left + right;
}

[[nodiscard]] ModalEigenResult modal_failure(
    const SolverStatus status,
    const double stiffness_symmetry,
    const double mass_symmetry,
    const double stiffness_minimum,
    const double mass_minimum,
    const std::uint32_t sweeps) {
    return {
        status,
        {},
        0U,
        sweeps,
        0.0,
        0.0,
        stiffness_symmetry,
        mass_symmetry,
        stiffness_minimum,
        mass_minimum,
        0U,
    };
}

[[nodiscard]] BucklingEigenResult buckling_failure(
    const SolverStatus status,
    const double stiffness_symmetry,
    const double geometric_symmetry,
    const double stiffness_minimum,
    const double geometric_minimum,
    const std::uint32_t geometric_rank,
    const std::uint32_t sweeps) {
    return {
        status,
        {},
        0U,
        geometric_rank,
        sweeps,
        0.0,
        0.0,
        0.0,
        stiffness_symmetry,
        geometric_symmetry,
        stiffness_minimum,
        geometric_minimum,
        0U,
    };
}

}  // namespace

GeneralizedEigenConfig default_modal_eigen_config(
    const std::uint32_t mode_count) noexcept {
    return {
        mode_count,
        1.0e-12,
        1.0e-12,
        1.0e-12,
        1.0e-10,
        1.0e-10,
        1.0e-10,
        1.0e-14,
        128U,
    };
}

GeneralizedEigenConfig default_buckling_eigen_config(
    const std::uint32_t mode_count) noexcept {
    auto config = default_modal_eigen_config(mode_count);
    config.residual_relative_tolerance = 1.0e-9;
    config.orthogonality_tolerance = 1.0e-8;
    return config;
}

ModalEigenResult solve_dense_modal_modes(
    const DenseSymmetricMatrixView stiffness,
    const DenseSymmetricMatrixView mass,
    const std::span<const double> coordinate_recovery_scale,
    const GeneralizedEigenConfig& config) {
    if (stiffness.order != mass.order) {
        throw std::invalid_argument("stiffness and mass matrix orders must match");
    }
    validate_config(config, stiffness.order);
    auto stiffness_projection = validate_and_project_symmetric(
        stiffness, "stiffness", config.symmetry_relative_tolerance);
    auto mass_projection = validate_and_project_symmetric(
        mass, "mass", config.symmetry_relative_tolerance);
    const auto scale = validate_recovery_scale(coordinate_recovery_scale, stiffness.order);

    std::uint32_t sweeps = 0U;
    const auto stiffness_spectrum = symmetric_eigen_jacobi(
        stiffness_projection.matrix,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, stiffness_spectrum.sweeps);
    const auto mass_spectrum = symmetric_eigen_jacobi(
        mass_projection.matrix,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, mass_spectrum.sweeps);
    const double stiffness_minimum = stiffness_spectrum.values.front();
    const double mass_minimum = mass_spectrum.values.front();
    if (!stiffness_spectrum.converged || !mass_spectrum.converged) {
        return modal_failure(
            SolverStatus::nonconvergence,
            stiffness_projection.relative_error,
            mass_projection.relative_error,
            stiffness_minimum,
            mass_minimum,
            sweeps);
    }
    if (mass_minimum <= 0.0) {
        throw std::invalid_argument("mass must be positive definite");
    }
    const double stiffness_scale = std::max(
        max_abs(stiffness_spectrum.values), std::numeric_limits<double>::min());
    if (stiffness_minimum
        < -config.positive_semidefinite_relative_tolerance * stiffness_scale) {
        throw std::invalid_argument("stiffness violates the positive-semidefinite contract");
    }

    const Matrix solve_stiffness = congruence_scale(stiffness_projection.matrix, scale);
    const Matrix solve_mass = congruence_scale(mass_projection.matrix, scale);
    const Matrix mass_lower = cholesky_lower(solve_mass, "mass");
    const Matrix mass_lower_inverse = inverse_lower(mass_lower);
    const Matrix transformed = transform_generalized_operator(
        solve_stiffness, mass_lower_inverse);
    const auto solve_spectrum = symmetric_eigen_jacobi(
        transformed,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, solve_spectrum.sweeps);
    if (!solve_spectrum.converged) {
        return modal_failure(
            SolverStatus::nonconvergence,
            stiffness_projection.relative_error,
            mass_projection.relative_error,
            stiffness_minimum,
            mass_minimum,
            sweeps);
    }

    const double spectral_scale = std::max(max_abs(solve_spectrum.values), 1.0);
    const double rigid_limit = config.mode_relative_tolerance * spectral_scale;
    std::uint32_t rigid_count = 0U;
    std::vector<std::size_t> positive_indices;
    for (std::size_t index = 0U; index < solve_spectrum.values.size(); ++index) {
        if (solve_spectrum.values[index] <= rigid_limit) {
            ++rigid_count;
        } else {
            positive_indices.push_back(index);
        }
    }
    if (positive_indices.size() < config.mode_count) {
        throw std::invalid_argument("requested positive modal modes are not available");
    }
    std::vector<double> positive_values;
    positive_values.reserve(positive_indices.size());
    for (const auto index : positive_indices) {
        positive_values.push_back(solve_spectrum.values[index]);
    }
    require_complete_cluster_selection(
        positive_values, config.mode_count, config.cluster_relative_tolerance);

    std::vector<std::vector<double>> solve_modes(config.mode_count);
    std::size_t cluster_begin = 0U;
    while (cluster_begin < config.mode_count) {
        std::size_t cluster_end = cluster_begin + 1U;
        while (cluster_end < config.mode_count
            && same_cluster(
                positive_values[cluster_end - 1U],
                positive_values[cluster_end],
                config.cluster_relative_tolerance)) {
            ++cluster_end;
        }
        std::vector<std::vector<double>> basis;
        basis.reserve(cluster_end - cluster_begin);
        for (std::size_t selected = cluster_begin; selected < cluster_end; ++selected) {
            const std::size_t source_column = positive_indices[selected];
            std::vector<double> transformed_vector(stiffness.order, 0.0);
            for (std::size_t row = 0U; row < stiffness.order; ++row) {
                transformed_vector[row] = solve_spectrum.vectors(row, source_column);
            }
            basis.push_back(recover_generalized_vector(
                mass_lower_inverse, transformed_vector));
        }
        std::vector<std::vector<double>> canonical;
        try {
            canonical = canonicalize_eigenspace(basis, solve_mass);
        } catch (const std::runtime_error&) {
            return modal_failure(
                SolverStatus::nonconvergence,
                stiffness_projection.relative_error,
                mass_projection.relative_error,
                stiffness_minimum,
                mass_minimum,
                sweeps);
        }
        for (std::size_t offset = 0U; offset < canonical.size(); ++offset) {
            solve_modes[cluster_begin + offset] = std::move(canonical[offset]);
        }
        cluster_begin = cluster_end;
    }

    std::vector<std::vector<double>> physical_modes = solve_modes;
    for (auto& vector : physical_modes) {
        for (std::size_t index = 0U; index < vector.size(); ++index) {
            vector[index] *= scale[index];
        }
    }
    std::vector<double> eigenvalues(config.mode_count, 0.0);
    std::vector<ModalEigenMode> modes;
    modes.reserve(config.mode_count);
    for (std::size_t index = 0U; index < physical_modes.size(); ++index) {
        const auto stiffness_force = matrix_vector(
            stiffness_projection.matrix, physical_modes[index]);
        const auto mass_force = matrix_vector(
            mass_projection.matrix, physical_modes[index]);
        const double generalized_mass = dot(physical_modes[index], mass_force);
        const double generalized_stiffness = dot(physical_modes[index], stiffness_force);
        const double eigenvalue = generalized_stiffness;
        if (!finite(eigenvalue) || eigenvalue <= 0.0 || !finite(generalized_mass)) {
            return modal_failure(
                SolverStatus::indefinite_operator,
                stiffness_projection.relative_error,
                mass_projection.relative_error,
                stiffness_minimum,
                mass_minimum,
                sweeps);
        }
        std::vector<double> residual(stiffness.order, 0.0);
        for (std::size_t row = 0U; row < stiffness.order; ++row) {
            residual[row] = stiffness_force[row] - eigenvalue * mass_force[row];
        }
        const double denominator = std::max(
            vector_inf(stiffness_force) + std::abs(eigenvalue) * vector_inf(mass_force),
            std::numeric_limits<double>::min());
        const double residual_relative = vector_inf(residual) / denominator;
        if (!finite(residual_relative)
            || residual_relative > config.residual_relative_tolerance) {
            return modal_failure(
                SolverStatus::residual_limit,
                stiffness_projection.relative_error,
                mass_projection.relative_error,
                stiffness_minimum,
                mass_minimum,
                sweeps);
        }
        const double omega = std::sqrt(eigenvalue);
        eigenvalues[index] = eigenvalue;
        modes.push_back({
            eigenvalue,
            omega,
            omega / (2.0 * std::numbers::pi_v<double>),
            (2.0 * std::numbers::pi_v<double>) / omega,
            physical_modes[index],
            max_component_normalized(physical_modes[index]),
            generalized_mass,
            generalized_stiffness,
            residual_relative,
        });
    }
    const double mass_error = gram_error_identity(physical_modes, mass_projection.matrix);
    const double diagonal_error_absolute = gram_error_diagonal(
        physical_modes, stiffness_projection.matrix, eigenvalues);
    const double diagonal_error = diagonal_error_absolute
        / std::max(max_abs(eigenvalues), 1.0);
    if (mass_error > config.orthogonality_tolerance
        || diagonal_error > config.orthogonality_tolerance) {
        return modal_failure(
            SolverStatus::residual_limit,
            stiffness_projection.relative_error,
            mass_projection.relative_error,
            stiffness_minimum,
            mass_minimum,
            sweeps);
    }
    return {
        SolverStatus::converged,
        std::move(modes),
        rigid_count,
        sweeps,
        mass_error,
        diagonal_error,
        stiffness_projection.relative_error,
        mass_projection.relative_error,
        stiffness_minimum,
        mass_minimum,
        0U,
    };
}

BucklingEigenResult solve_dense_linear_buckling(
    const DenseSymmetricMatrixView stiffness,
    const DenseSymmetricMatrixView geometric_stiffness_per_unit_load,
    const std::span<const double> coordinate_recovery_scale,
    const GeneralizedEigenConfig& config) {
    if (stiffness.order != geometric_stiffness_per_unit_load.order) {
        throw std::invalid_argument(
            "stiffness and geometric stiffness matrix orders must match");
    }
    validate_config(config, stiffness.order);
    auto stiffness_projection = validate_and_project_symmetric(
        stiffness, "stiffness", config.symmetry_relative_tolerance);
    auto geometric_projection = validate_and_project_symmetric(
        geometric_stiffness_per_unit_load,
        "geometric stiffness per unit load",
        config.symmetry_relative_tolerance);
    const auto scale = validate_recovery_scale(coordinate_recovery_scale, stiffness.order);

    std::uint32_t sweeps = 0U;
    const auto stiffness_spectrum = symmetric_eigen_jacobi(
        stiffness_projection.matrix,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, stiffness_spectrum.sweeps);
    const auto geometric_spectrum = symmetric_eigen_jacobi(
        geometric_projection.matrix,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, geometric_spectrum.sweeps);
    const double stiffness_minimum = stiffness_spectrum.values.front();
    const double geometric_minimum = geometric_spectrum.values.front();
    const double geometric_scale = std::max(
        max_abs(geometric_spectrum.values), std::numeric_limits<double>::min());
    std::uint32_t geometric_rank = 0U;
    for (const double value : geometric_spectrum.values) {
        if (value > config.positive_semidefinite_relative_tolerance * geometric_scale) {
            ++geometric_rank;
        }
    }
    if (!stiffness_spectrum.converged || !geometric_spectrum.converged) {
        return buckling_failure(
            SolverStatus::nonconvergence,
            stiffness_projection.relative_error,
            geometric_projection.relative_error,
            stiffness_minimum,
            geometric_minimum,
            geometric_rank,
            sweeps);
    }
    if (stiffness_minimum <= 0.0) {
        throw std::invalid_argument("stiffness must be positive definite");
    }
    if (geometric_minimum
        < -config.positive_semidefinite_relative_tolerance * geometric_scale) {
        throw std::invalid_argument(
            "geometric stiffness violates the positive-semidefinite contract");
    }

    const Matrix solve_stiffness = congruence_scale(stiffness_projection.matrix, scale);
    const Matrix solve_geometric = congruence_scale(geometric_projection.matrix, scale);
    const Matrix stiffness_lower = cholesky_lower(solve_stiffness, "stiffness");
    const Matrix stiffness_lower_inverse = inverse_lower(stiffness_lower);
    const Matrix transformed = transform_generalized_operator(
        solve_geometric, stiffness_lower_inverse);
    const auto reciprocal_spectrum = symmetric_eigen_jacobi(
        transformed,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps);
    sweeps = add_sweeps(sweeps, reciprocal_spectrum.sweeps);
    if (!reciprocal_spectrum.converged) {
        return buckling_failure(
            SolverStatus::nonconvergence,
            stiffness_projection.relative_error,
            geometric_projection.relative_error,
            stiffness_minimum,
            geometric_minimum,
            geometric_rank,
            sweeps);
    }

    const double reciprocal_scale = std::max(
        max_abs(reciprocal_spectrum.values), std::numeric_limits<double>::min());
    const double positive_limit = config.mode_relative_tolerance * reciprocal_scale;
    struct Candidate {
        double load_factor;
        std::size_t source_column;
    };
    std::vector<Candidate> candidates;
    for (std::size_t index = 0U; index < reciprocal_spectrum.values.size(); ++index) {
        const double reciprocal = reciprocal_spectrum.values[index];
        if (finite(reciprocal) && reciprocal > positive_limit) {
            candidates.push_back({1.0 / reciprocal, index});
        }
    }
    std::stable_sort(
        candidates.begin(), candidates.end(),
        [](const Candidate& left, const Candidate& right) {
            return left.load_factor < right.load_factor;
        });
    if (candidates.size() < config.mode_count) {
        throw std::invalid_argument(
            "requested finite positive buckling modes are not available");
    }
    std::vector<double> candidate_values;
    candidate_values.reserve(candidates.size());
    for (const auto& candidate : candidates) {
        candidate_values.push_back(candidate.load_factor);
    }
    require_complete_cluster_selection(
        candidate_values, config.mode_count, config.cluster_relative_tolerance);

    std::vector<std::vector<double>> solve_modes(config.mode_count);
    std::size_t cluster_begin = 0U;
    while (cluster_begin < config.mode_count) {
        std::size_t cluster_end = cluster_begin + 1U;
        while (cluster_end < config.mode_count
            && same_cluster(
                candidate_values[cluster_end - 1U],
                candidate_values[cluster_end],
                config.cluster_relative_tolerance)) {
            ++cluster_end;
        }
        std::vector<std::vector<double>> basis;
        basis.reserve(cluster_end - cluster_begin);
        for (std::size_t selected = cluster_begin; selected < cluster_end; ++selected) {
            std::vector<double> transformed_vector(stiffness.order, 0.0);
            for (std::size_t row = 0U; row < stiffness.order; ++row) {
                transformed_vector[row] = reciprocal_spectrum.vectors(
                    row, candidates[selected].source_column);
            }
            basis.push_back(recover_generalized_vector(
                stiffness_lower_inverse, transformed_vector));
        }
        std::vector<std::vector<double>> canonical;
        try {
            canonical = canonicalize_eigenspace(basis, solve_stiffness);
        } catch (const std::runtime_error&) {
            return buckling_failure(
                SolverStatus::nonconvergence,
                stiffness_projection.relative_error,
                geometric_projection.relative_error,
                stiffness_minimum,
                geometric_minimum,
                geometric_rank,
                sweeps);
        }
        for (std::size_t offset = 0U; offset < canonical.size(); ++offset) {
            solve_modes[cluster_begin + offset] = std::move(canonical[offset]);
        }
        cluster_begin = cluster_end;
    }

    std::vector<std::vector<double>> physical_modes = solve_modes;
    for (auto& vector : physical_modes) {
        for (std::size_t index = 0U; index < vector.size(); ++index) {
            vector[index] *= scale[index];
        }
    }
    std::vector<double> load_factors(config.mode_count, 0.0);
    std::vector<double> reciprocal_factors(config.mode_count, 0.0);
    std::vector<BucklingEigenMode> modes;
    modes.reserve(config.mode_count);
    for (std::size_t index = 0U; index < physical_modes.size(); ++index) {
        const auto elastic_force = matrix_vector(
            stiffness_projection.matrix, physical_modes[index]);
        const auto geometric_force = matrix_vector(
            geometric_projection.matrix, physical_modes[index]);
        const double elastic = dot(physical_modes[index], elastic_force);
        const double geometric = dot(physical_modes[index], geometric_force);
        if (!finite(elastic) || !finite(geometric) || geometric <= 0.0) {
            return buckling_failure(
                SolverStatus::indefinite_operator,
                stiffness_projection.relative_error,
                geometric_projection.relative_error,
                stiffness_minimum,
                geometric_minimum,
                geometric_rank,
                sweeps);
        }
        const double load_factor = elastic / geometric;
        std::vector<double> residual(stiffness.order, 0.0);
        for (std::size_t row = 0U; row < stiffness.order; ++row) {
            residual[row] = elastic_force[row] - load_factor * geometric_force[row];
        }
        const double denominator = std::max(
            vector_inf(elastic_force)
                + std::abs(load_factor) * vector_inf(geometric_force),
            std::numeric_limits<double>::min());
        const double residual_relative = vector_inf(residual) / denominator;
        if (!finite(residual_relative)
            || residual_relative > config.residual_relative_tolerance) {
            return buckling_failure(
                SolverStatus::residual_limit,
                stiffness_projection.relative_error,
                geometric_projection.relative_error,
                stiffness_minimum,
                geometric_minimum,
                geometric_rank,
                sweeps);
        }
        load_factors[index] = load_factor;
        reciprocal_factors[index] = 1.0 / load_factor;
        modes.push_back({
            load_factor,
            physical_modes[index],
            max_component_normalized(physical_modes[index]),
            elastic,
            geometric,
            residual_relative,
        });
    }
    const double stiffness_error = gram_error_identity(
        physical_modes, stiffness_projection.matrix);
    const double geometric_error_absolute = gram_error_diagonal(
        physical_modes, geometric_projection.matrix, reciprocal_factors);
    const double geometric_error = geometric_error_absolute
        / std::max(max_abs(reciprocal_factors), 1.0);
    if (stiffness_error > config.orthogonality_tolerance
        || geometric_error > config.orthogonality_tolerance) {
        return buckling_failure(
            SolverStatus::residual_limit,
            stiffness_projection.relative_error,
            geometric_projection.relative_error,
            stiffness_minimum,
            geometric_minimum,
            geometric_rank,
            sweeps);
    }
    return {
        SolverStatus::converged,
        std::move(modes),
        static_cast<std::uint32_t>(candidates.size()),
        geometric_rank,
        sweeps,
        load_factors.front(),
        stiffness_error,
        geometric_error,
        stiffness_projection.relative_error,
        geometric_projection.relative_error,
        stiffness_minimum,
        geometric_minimum,
        0U,
    };
}

}  // namespace structural::solver_cpu
