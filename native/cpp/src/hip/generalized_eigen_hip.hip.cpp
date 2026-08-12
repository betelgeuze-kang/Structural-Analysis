#include "generalized_eigen_hip.hpp"

#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#ifndef STRUCTURAL_GENERALIZED_EIGEN_HIP_SOURCE_SHA256
#define STRUCTURAL_GENERALIZED_EIGEN_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_GENERALIZED_EIGEN_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_GENERALIZED_EIGEN_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_GENERALIZED_EIGEN_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_GENERALIZED_EIGEN_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::size_t kMaximumOrder = 128U;
constexpr std::size_t kWorkspaceMatrixCount = 7U;
constexpr std::uint32_t kMaximumSweeps = 4'096U;
constexpr double kCanonicalBasisTolerance = 1.0e-12;
constexpr double kMinimumNormal = 2.225073858507201383090232717332404064219e-308;
constexpr double kPi = 3.141592653589793238462643383279502884;

constexpr std::uint32_t kModal = 0U;
constexpr std::uint32_t kBuckling = 1U;
constexpr std::uint32_t kConverged = 0U;
constexpr std::uint32_t kIndefiniteOperator = 3U;
constexpr std::uint32_t kNonconvergence = 4U;
constexpr std::uint32_t kResidualLimit = 6U;

constexpr std::uint32_t kContractNone = 0U;
constexpr std::uint32_t kContractModalMassPositiveDefinite = 1U;
constexpr std::uint32_t kContractModalStiffnessPositiveSemidefinite = 2U;
constexpr std::uint32_t kContractBucklingStiffnessPositiveDefinite = 3U;
constexpr std::uint32_t kContractBucklingGeometricPositiveSemidefinite = 4U;
constexpr std::uint32_t kContractScaledMetricPositiveDefinite = 5U;
constexpr std::uint32_t kContractModesUnavailable = 6U;
constexpr std::uint32_t kContractClusterCut = 7U;
constexpr std::uint32_t kContractScaledMatrixNonfinite = 8U;

struct DeviceConfig {
    std::uint32_t mode_count;
    double positive_semidefinite_relative_tolerance;
    double mode_relative_tolerance;
    double cluster_relative_tolerance;
    double residual_relative_tolerance;
    double orthogonality_tolerance;
    double eigensolver_relative_tolerance;
    std::uint32_t maximum_sweeps;
    double left_symmetry_error;
    double right_symmetry_error;
};

struct DevicePackedResult {
    std::uint32_t status;
    std::uint32_t contract_error;
    std::uint32_t mode_count;
    std::uint32_t auxiliary_count;
    std::uint32_t geometric_rank;
    std::uint32_t eigensolver_sweeps;
    double critical_load_factor;
    double metric_orthogonality_error;
    double operator_diagonalization_error;
    double left_symmetry_error;
    double right_symmetry_error;
    double left_minimum_eigenvalue;
    double right_minimum_eigenvalue;
    double values[kMaximumOrder];
    double scalar_a[kMaximumOrder];
    double scalar_b[kMaximumOrder];
    double residual_relative_inf[kMaximumOrder];
    double shapes[kMaximumOrder * kMaximumOrder];
    double max_component_shapes[kMaximumOrder * kMaximumOrder];
};

struct ProjectedInput {
    std::size_t order;
    std::vector<double> left;
    std::vector<double> right;
    std::vector<double> scale;
    double left_symmetry_error;
    double right_symmetry_error;
};

struct RawExecution {
    std::unique_ptr<DevicePackedResult> output;
    GeneralizedEigenExecutionReceipt receipt;
};

void check_hip(const hipError_t status, const char* const operation) {
    if (status != hipSuccess) {
        throw std::runtime_error(std::string(operation) + ":" + hipGetErrorString(status));
    }
}

class Stream final {
  public:
    Stream() {
        check_hip(hipStreamCreateWithFlags(&value_, hipStreamNonBlocking), "hipStreamCreate");
    }

    Stream(const Stream&) = delete;
    Stream& operator=(const Stream&) = delete;

    ~Stream() {
        if (value_ != nullptr) {
            static_cast<void>(hipStreamDestroy(value_));
        }
    }

    [[nodiscard]] hipStream_t get() const noexcept { return value_; }

  private:
    hipStream_t value_ {nullptr};
};

template <typename T>
class DeviceBuffer final {
  public:
    explicit DeviceBuffer(const std::size_t logical_count)
        : logical_count_(logical_count), allocated_count_(std::max<std::size_t>(1U, logical_count)) {
        if (allocated_count_ > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
            throw std::invalid_argument("HIP generalized-eigen allocation count is invalid");
        }
        check_hip(
            hipMalloc(reinterpret_cast<void**>(&value_), allocated_count_ * sizeof(T)),
            "hipMalloc");
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    ~DeviceBuffer() {
        if (value_ != nullptr) {
            static_cast<void>(hipFree(value_));
        }
    }

    [[nodiscard]] T* get() noexcept { return value_; }
    [[nodiscard]] const T* get() const noexcept { return value_; }
    [[nodiscard]] std::size_t logical_bytes() const noexcept {
        return logical_count_ * sizeof(T);
    }
    [[nodiscard]] std::size_t allocated_bytes() const noexcept {
        return allocated_count_ * sizeof(T);
    }

  private:
    T* value_ {nullptr};
    std::size_t logical_count_;
    std::size_t allocated_count_;
};

[[nodiscard]] bool finite(const double value) noexcept { return std::isfinite(value); }

void validate_config(
    const solver_cpu::GeneralizedEigenConfig& config,
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

[[nodiscard]] std::pair<std::vector<double>, double> validate_and_project(
    const solver_cpu::DenseSymmetricMatrixView input,
    const char* const name,
    const double tolerance) {
    if (input.order == 0U || input.order > kMaximumOrder
        || input.order > std::numeric_limits<std::size_t>::max() / input.order
        || input.values.size() != input.order * input.order) {
        throw std::invalid_argument(
            std::string(name) + " must be a bounded non-empty dense square matrix");
    }
    double maximum_value = 0.0;
    for (const double value : input.values) {
        if (!finite(value)) {
            throw std::invalid_argument(
                std::string(name) + " must contain only finite binary64 values");
        }
        maximum_value = std::max(maximum_value, std::abs(value));
    }
    std::vector<double> projected(input.values.size(), 0.0);
    double maximum_error = 0.0;
    for (std::size_t row = 0U; row < input.order; ++row) {
        for (std::size_t column = 0U; column < input.order; ++column) {
            const auto left = input.values[row * input.order + column];
            const auto right = input.values[column * input.order + row];
            maximum_error = std::max(maximum_error, std::abs(left - right));
            projected[row * input.order + column] = 0.5 * (left + right);
        }
    }
    const auto relative_error = maximum_error / std::max(maximum_value, kMinimumNormal);
    if (relative_error > tolerance) {
        throw std::invalid_argument(
            std::string(name) + " relative symmetry error exceeds the contract");
    }
    return {std::move(projected), relative_error};
}

[[nodiscard]] ProjectedInput validate_and_prepare(
    const solver_cpu::DenseSymmetricMatrixView left,
    const solver_cpu::DenseSymmetricMatrixView right,
    const std::span<const double> coordinate_recovery_scale,
    const solver_cpu::GeneralizedEigenConfig& config,
    const std::uint32_t problem_kind) {
    if (left.order != right.order) {
        throw std::invalid_argument(
            problem_kind == kModal
                ? "stiffness and mass matrix orders must match"
                : "stiffness and geometric stiffness matrix orders must match");
    }
    validate_config(config, left.order);
    auto left_projection = validate_and_project(
        left, "stiffness", config.symmetry_relative_tolerance);
    auto right_projection = validate_and_project(
        right,
        problem_kind == kModal ? "mass" : "geometric stiffness per unit load",
        config.symmetry_relative_tolerance);
    if (!coordinate_recovery_scale.empty()
        && coordinate_recovery_scale.size() != left.order) {
        throw std::invalid_argument(
            "coordinate recovery scale must be empty or match the matrix order");
    }
    std::vector<double> scale(left.order, 1.0);
    if (!coordinate_recovery_scale.empty()) {
        for (std::size_t index = 0U; index < left.order; ++index) {
            if (!finite(coordinate_recovery_scale[index])
                || coordinate_recovery_scale[index] <= 0.0) {
                throw std::invalid_argument(
                    "coordinate recovery scale must contain finite positive values");
            }
            scale[index] = coordinate_recovery_scale[index];
        }
    }
    return {
        left.order,
        std::move(left_projection.first),
        std::move(right_projection.first),
        std::move(scale),
        left_projection.second,
        right_projection.second,
    };
}

__device__ double device_max(const double left, const double right) {
    return left > right ? left : right;
}

__device__ std::uint32_t add_sweeps(
    const std::uint32_t left,
    const std::uint32_t right) {
    return left > 0xffffffffU - right ? 0xffffffffU : left + right;
}

__device__ bool symmetric_eigen_jacobi(
    double* const matrix,
    double* const vectors,
    double* const sorted_vector_scratch,
    double* const values,
    const std::size_t order,
    const double relative_tolerance,
    const std::uint32_t maximum_sweeps,
    std::uint32_t* const completed_sweeps) {
    if (vectors != nullptr) {
        for (std::size_t row = 0U; row < order; ++row) {
            for (std::size_t column = 0U; column < order; ++column) {
                vectors[row * order + column] = row == column ? 1.0 : 0.0;
            }
        }
    }
    *completed_sweeps = 0U;
    bool converged = order == 1U;
    for (std::uint32_t sweep = 0U; sweep < maximum_sweeps && !converged; ++sweep) {
        double off_diagonal = 0.0;
        double diagonal_scale = 0.0;
        for (std::size_t row = 0U; row < order; ++row) {
            diagonal_scale = device_max(diagonal_scale, fabs(matrix[row * order + row]));
            for (std::size_t column = row + 1U; column < order; ++column) {
                off_diagonal = device_max(
                    off_diagonal, fabs(matrix[row * order + column]));
            }
        }
        const double limit = relative_tolerance * device_max(diagonal_scale, kMinimumNormal);
        if (off_diagonal <= limit) {
            converged = true;
            break;
        }
        for (std::size_t left = 0U; left < order; ++left) {
            for (std::size_t right = left + 1U; right < order; ++right) {
                const auto cross = matrix[left * order + right];
                if (fabs(cross) <= limit) {
                    continue;
                }
                const auto diagonal_left = matrix[left * order + left];
                const auto diagonal_right = matrix[right * order + right];
                const auto tau = (diagonal_right - diagonal_left) / (2.0 * cross);
                const auto tangent = copysign(
                    1.0 / (fabs(tau) + hypot(1.0, tau)), tau);
                const auto cosine = 1.0 / sqrt(1.0 + tangent * tangent);
                const auto sine = tangent * cosine;
                matrix[left * order + left] = diagonal_left - tangent * cross;
                matrix[right * order + right] = diagonal_right + tangent * cross;
                matrix[left * order + right] = 0.0;
                matrix[right * order + left] = 0.0;
                for (std::size_t index = 0U; index < order; ++index) {
                    if (index == left || index == right) {
                        continue;
                    }
                    const auto value_left = matrix[index * order + left];
                    const auto value_right = matrix[index * order + right];
                    const auto rotated_left = cosine * value_left - sine * value_right;
                    const auto rotated_right = sine * value_left + cosine * value_right;
                    matrix[index * order + left] = rotated_left;
                    matrix[left * order + index] = rotated_left;
                    matrix[index * order + right] = rotated_right;
                    matrix[right * order + index] = rotated_right;
                }
                if (vectors != nullptr) {
                    for (std::size_t index = 0U; index < order; ++index) {
                        const auto value_left = vectors[index * order + left];
                        const auto value_right = vectors[index * order + right];
                        vectors[index * order + left] =
                            cosine * value_left - sine * value_right;
                        vectors[index * order + right] =
                            sine * value_left + cosine * value_right;
                    }
                }
            }
        }
        *completed_sweeps = sweep + 1U;
    }
    if (!converged) {
        double off_diagonal = 0.0;
        double diagonal_scale = 0.0;
        for (std::size_t row = 0U; row < order; ++row) {
            diagonal_scale = device_max(diagonal_scale, fabs(matrix[row * order + row]));
            for (std::size_t column = row + 1U; column < order; ++column) {
                off_diagonal = device_max(
                    off_diagonal, fabs(matrix[row * order + column]));
            }
        }
        converged = off_diagonal
            <= relative_tolerance * device_max(diagonal_scale, kMinimumNormal);
    }

    double diagonal[kMaximumOrder];
    std::uint32_t permutation[kMaximumOrder];
    bool used[kMaximumOrder];
    for (std::size_t index = 0U; index < order; ++index) {
        diagonal[index] = matrix[index * order + index];
        used[index] = false;
    }
    for (std::size_t destination = 0U; destination < order; ++destination) {
        std::size_t best = order;
        for (std::size_t candidate = 0U; candidate < order; ++candidate) {
            if (!used[candidate]
                && (best == order || diagonal[candidate] < diagonal[best])) {
                best = candidate;
            }
        }
        used[best] = true;
        permutation[destination] = static_cast<std::uint32_t>(best);
        values[destination] = diagonal[best];
    }
    if (vectors != nullptr) {
        for (std::size_t column = 0U; column < order; ++column) {
            const auto source = permutation[column];
            for (std::size_t row = 0U; row < order; ++row) {
                sorted_vector_scratch[row * order + column] =
                    vectors[row * order + source];
            }
        }
        for (std::size_t index = 0U; index < order * order; ++index) {
            vectors[index] = sorted_vector_scratch[index];
        }
    }
    return converged;
}

__device__ bool same_cluster(
    const double left,
    const double right,
    const double relative_tolerance) {
    const auto scale = device_max(device_max(fabs(left), fabs(right)), 1.0);
    return fabs(right - left) <= relative_tolerance * scale;
}

__device__ double metric_dot(
    const double* const left,
    const double* const metric,
    const double* const right,
    const std::size_t order) {
    double result = 0.0;
    for (std::size_t row = 0U; row < order; ++row) {
        double product = 0.0;
        for (std::size_t column = 0U; column < order; ++column) {
            product += metric[row * order + column] * right[column];
        }
        result += left[row] * product;
    }
    return result;
}

__device__ void canonicalize_sign(double* const vector, const std::size_t order) {
    std::size_t pivot = 0U;
    for (std::size_t index = 1U; index < order; ++index) {
        if (fabs(vector[index]) > fabs(vector[pivot])) {
            pivot = index;
        }
    }
    if (vector[pivot] < 0.0) {
        for (std::size_t index = 0U; index < order; ++index) {
            vector[index] = -vector[index];
        }
    }
}

__device__ bool canonicalize_cluster(
    double* const modes,
    double* const orthonormal,
    const double* const metric,
    double* const candidate,
    const std::size_t order,
    const std::size_t cluster_begin,
    const std::size_t cluster_end) {
    const auto required = cluster_end - cluster_begin;
    std::size_t accepted = 0U;
    for (std::size_t source = cluster_begin; source < cluster_end; ++source) {
        for (std::size_t row = 0U; row < order; ++row) {
            candidate[row] = modes[source * order + row];
        }
        for (int pass = 0; pass < 2; ++pass) {
            for (std::size_t prior = 0U; prior < accepted; ++prior) {
                const auto* const prior_vector =
                    orthonormal + (cluster_begin + prior) * order;
                const auto projection = metric_dot(
                    prior_vector, metric, candidate, order);
                for (std::size_t row = 0U; row < order; ++row) {
                    candidate[row] -= prior_vector[row] * projection;
                }
            }
        }
        const auto norm_squared = metric_dot(candidate, metric, candidate, order);
        if (!isfinite(norm_squared)
            || norm_squared <= kCanonicalBasisTolerance * kCanonicalBasisTolerance) {
            continue;
        }
        const auto inverse_norm = 1.0 / sqrt(norm_squared);
        for (std::size_t row = 0U; row < order; ++row) {
            candidate[row] *= inverse_norm;
        }
        canonicalize_sign(candidate, order);
        for (std::size_t row = 0U; row < order; ++row) {
            orthonormal[(cluster_begin + accepted) * order + row] = candidate[row];
        }
        ++accepted;
    }
    if (accepted != required) {
        return false;
    }

    accepted = 0U;
    for (std::size_t coordinate = 0U; coordinate < order && accepted < required;
         ++coordinate) {
        for (std::size_t row = 0U; row < order; ++row) {
            candidate[row] = 0.0;
        }
        for (std::size_t basis = 0U; basis < required; ++basis) {
            const auto* const vector =
                orthonormal + (cluster_begin + basis) * order;
            double coefficient = 0.0;
            for (std::size_t row = 0U; row < order; ++row) {
                coefficient += vector[row] * metric[row * order + coordinate];
            }
            for (std::size_t row = 0U; row < order; ++row) {
                candidate[row] += vector[row] * coefficient;
            }
        }
        for (int pass = 0; pass < 2; ++pass) {
            for (std::size_t prior = 0U; prior < accepted; ++prior) {
                const auto* const prior_vector = modes + (cluster_begin + prior) * order;
                const auto projection = metric_dot(
                    prior_vector, metric, candidate, order);
                for (std::size_t row = 0U; row < order; ++row) {
                    candidate[row] -= prior_vector[row] * projection;
                }
            }
        }
        const auto norm_squared = metric_dot(candidate, metric, candidate, order);
        if (!isfinite(norm_squared)
            || norm_squared <= kCanonicalBasisTolerance * kCanonicalBasisTolerance) {
            continue;
        }
        const auto inverse_norm = 1.0 / sqrt(norm_squared);
        for (std::size_t row = 0U; row < order; ++row) {
            candidate[row] *= inverse_norm;
        }
        canonicalize_sign(candidate, order);
        for (std::size_t row = 0U; row < order; ++row) {
            modes[(cluster_begin + accepted) * order + row] = candidate[row];
        }
        ++accepted;
    }
    return accepted == required;
}

__device__ double vector_inf(const double* const vector, const std::size_t order) {
    double result = 0.0;
    for (std::size_t index = 0U; index < order; ++index) {
        result = device_max(result, fabs(vector[index]));
    }
    return result;
}

__device__ void matrix_vector(
    const double* const matrix,
    const double* const vector,
    double* const output,
    const std::size_t order) {
    for (std::size_t row = 0U; row < order; ++row) {
        double value = 0.0;
        for (std::size_t column = 0U; column < order; ++column) {
            value += matrix[row * order + column] * vector[column];
        }
        output[row] = value;
    }
}

__device__ double vector_dot(
    const double* const left,
    const double* const right,
    const std::size_t order) {
    double result = 0.0;
    for (std::size_t index = 0U; index < order; ++index) {
        result += left[index] * right[index];
    }
    return result;
}

__device__ void initialize_output(
    DevicePackedResult* const output,
    const DeviceConfig config) {
    output->status = kNonconvergence;
    output->contract_error = kContractNone;
    output->mode_count = 0U;
    output->auxiliary_count = 0U;
    output->geometric_rank = 0U;
    output->eigensolver_sweeps = 0U;
    output->critical_load_factor = 0.0;
    output->metric_orthogonality_error = 0.0;
    output->operator_diagonalization_error = 0.0;
    output->left_symmetry_error = config.left_symmetry_error;
    output->right_symmetry_error = config.right_symmetry_error;
    output->left_minimum_eigenvalue = 0.0;
    output->right_minimum_eigenvalue = 0.0;
}

__device__ void set_contract_error(
    DevicePackedResult* const output,
    const std::uint32_t error) {
    output->contract_error = error;
    output->mode_count = 0U;
}

__device__ void set_numerical_failure(
    DevicePackedResult* const output,
    const std::uint32_t status) {
    output->status = status;
    output->mode_count = 0U;
    output->auxiliary_count = 0U;
}

__global__ void generalized_eigen_kernel(
    const std::uint32_t problem_kind,
    const std::size_t order,
    const double* const left,
    const double* const right,
    const double* const recovery_scale,
    const DeviceConfig config,
    double* const workspace,
    double* const eigenvalue_workspace,
    double* const vector_workspace,
    DevicePackedResult* const output) {
    if (blockIdx.x != 0U || threadIdx.x != 0U) {
        return;
    }
    initialize_output(output, config);
    const auto matrix_count = order * order;
    double* const matrix0 = workspace;
    double* const matrix1 = matrix0 + matrix_count;
    double* const matrix2 = matrix1 + matrix_count;
    double* const matrix3 = matrix2 + matrix_count;
    double* const matrix4 = matrix3 + matrix_count;
    double* const matrix5 = matrix4 + matrix_count;
    double* const matrix6 = matrix5 + matrix_count;
    double* const left_values = eigenvalue_workspace;
    double* const right_values = left_values + order;
    double* const solve_values = right_values + order;
    double* const candidate_values = solve_values + order;
    double* const candidate_vector = vector_workspace;
    double* const force_left = candidate_vector + order;
    double* const force_right = force_left + order;
    double* const residual = force_right + order;

    for (std::size_t index = 0U; index < matrix_count; ++index) {
        matrix0[index] = left[index];
        matrix1[index] = right[index];
    }
    std::uint32_t left_sweeps = 0U;
    std::uint32_t right_sweeps = 0U;
    const auto left_converged = symmetric_eigen_jacobi(
        matrix0, nullptr, nullptr, left_values, order,
        config.eigensolver_relative_tolerance, config.maximum_sweeps, &left_sweeps);
    const auto right_converged = symmetric_eigen_jacobi(
        matrix1, nullptr, nullptr, right_values, order,
        config.eigensolver_relative_tolerance, config.maximum_sweeps, &right_sweeps);
    output->eigensolver_sweeps = add_sweeps(left_sweeps, right_sweeps);
    output->left_minimum_eigenvalue = left_values[0];
    output->right_minimum_eigenvalue = right_values[0];

    double left_spectral_scale = 0.0;
    double right_spectral_scale = 0.0;
    for (std::size_t index = 0U; index < order; ++index) {
        left_spectral_scale = device_max(left_spectral_scale, fabs(left_values[index]));
        right_spectral_scale = device_max(right_spectral_scale, fabs(right_values[index]));
    }
    left_spectral_scale = device_max(left_spectral_scale, kMinimumNormal);
    right_spectral_scale = device_max(right_spectral_scale, kMinimumNormal);
    if (problem_kind == kBuckling) {
        for (std::size_t index = 0U; index < order; ++index) {
            if (right_values[index]
                > config.positive_semidefinite_relative_tolerance
                    * right_spectral_scale) {
                ++output->geometric_rank;
            }
        }
    }
    if (!left_converged || !right_converged) {
        output->status = kNonconvergence;
        return;
    }
    if (problem_kind == kModal) {
        if (right_values[0] <= 0.0) {
            set_contract_error(output, kContractModalMassPositiveDefinite);
            return;
        }
        if (left_values[0]
            < -config.positive_semidefinite_relative_tolerance * left_spectral_scale) {
            set_contract_error(output, kContractModalStiffnessPositiveSemidefinite);
            return;
        }
    } else {
        if (left_values[0] <= 0.0) {
            set_contract_error(output, kContractBucklingStiffnessPositiveDefinite);
            return;
        }
        if (right_values[0]
            < -config.positive_semidefinite_relative_tolerance * right_spectral_scale) {
            set_contract_error(output, kContractBucklingGeometricPositiveSemidefinite);
            return;
        }
    }

    const double* const physical_operator = problem_kind == kModal ? left : right;
    const double* const physical_metric = problem_kind == kModal ? right : left;
    for (std::size_t row = 0U; row < order; ++row) {
        for (std::size_t column = 0U; column < order; ++column) {
            const auto factor = recovery_scale[row] * recovery_scale[column];
            matrix0[row * order + column] = physical_operator[row * order + column] * factor;
            matrix1[row * order + column] = physical_metric[row * order + column] * factor;
            if (!isfinite(matrix0[row * order + column])
                || !isfinite(matrix1[row * order + column])) {
                set_contract_error(output, kContractScaledMatrixNonfinite);
                return;
            }
        }
    }

    for (std::size_t index = 0U; index < matrix_count; ++index) {
        matrix2[index] = 0.0;
    }
    for (std::size_t row = 0U; row < order; ++row) {
        for (std::size_t column = 0U; column <= row; ++column) {
            auto value = matrix1[row * order + column];
            for (std::size_t inner = 0U; inner < column; ++inner) {
                value -= matrix2[row * order + inner] * matrix2[column * order + inner];
            }
            if (row == column) {
                if (!isfinite(value) || value <= 0.0) {
                    set_contract_error(output, kContractScaledMetricPositiveDefinite);
                    return;
                }
                matrix2[row * order + column] = sqrt(value);
            } else {
                matrix2[row * order + column] = value / matrix2[column * order + column];
            }
        }
    }
    for (std::size_t index = 0U; index < matrix_count; ++index) {
        matrix3[index] = 0.0;
    }
    for (std::size_t column = 0U; column < order; ++column) {
        for (std::size_t row = 0U; row < order; ++row) {
            auto value = row == column ? 1.0 : 0.0;
            for (std::size_t inner = 0U; inner < row; ++inner) {
                value -= matrix2[row * order + inner] * matrix3[inner * order + column];
            }
            matrix3[row * order + column] = value / matrix2[row * order + row];
            if (!isfinite(matrix3[row * order + column])) {
                set_contract_error(output, kContractScaledMetricPositiveDefinite);
                return;
            }
        }
    }
    for (std::size_t row = 0U; row < order; ++row) {
        for (std::size_t column = 0U; column < order; ++column) {
            double value = 0.0;
            for (std::size_t inner = 0U; inner < order; ++inner) {
                value += matrix3[row * order + inner] * matrix0[inner * order + column];
            }
            matrix4[row * order + column] = value;
        }
    }
    for (std::size_t row = 0U; row < order; ++row) {
        for (std::size_t column = 0U; column < order; ++column) {
            double value = 0.0;
            for (std::size_t inner = 0U; inner < order; ++inner) {
                value += matrix4[row * order + inner] * matrix3[column * order + inner];
            }
            matrix5[row * order + column] = value;
        }
    }
    for (std::size_t row = 0U; row < order; ++row) {
        for (std::size_t column = row + 1U; column < order; ++column) {
            const auto projected = 0.5
                * (matrix5[row * order + column] + matrix5[column * order + row]);
            matrix5[row * order + column] = projected;
            matrix5[column * order + row] = projected;
        }
    }

    std::uint32_t solve_sweeps = 0U;
    const auto solve_converged = symmetric_eigen_jacobi(
        matrix5, matrix6, matrix4, solve_values, order,
        config.eigensolver_relative_tolerance, config.maximum_sweeps, &solve_sweeps);
    output->eigensolver_sweeps = add_sweeps(output->eigensolver_sweeps, solve_sweeps);
    if (!solve_converged) {
        output->status = kNonconvergence;
        return;
    }

    std::uint32_t source_indices[kMaximumOrder];
    std::size_t available = 0U;
    if (problem_kind == kModal) {
        double spectral_scale = 0.0;
        for (std::size_t index = 0U; index < order; ++index) {
            spectral_scale = device_max(spectral_scale, fabs(solve_values[index]));
        }
        spectral_scale = device_max(spectral_scale, 1.0);
        const auto rigid_limit = config.mode_relative_tolerance * spectral_scale;
        for (std::size_t index = 0U; index < order; ++index) {
            if (solve_values[index] <= rigid_limit) {
                ++output->auxiliary_count;
            } else {
                source_indices[available] = static_cast<std::uint32_t>(index);
                candidate_values[available] = solve_values[index];
                ++available;
            }
        }
    } else {
        double reciprocal_scale = 0.0;
        for (std::size_t index = 0U; index < order; ++index) {
            reciprocal_scale = device_max(reciprocal_scale, fabs(solve_values[index]));
        }
        reciprocal_scale = device_max(reciprocal_scale, kMinimumNormal);
        const auto positive_limit = config.mode_relative_tolerance * reciprocal_scale;
        for (std::size_t index = 0U; index < order; ++index) {
            if (isfinite(solve_values[index]) && solve_values[index] > positive_limit) {
                const auto load_factor = 1.0 / solve_values[index];
                std::size_t position = available;
                while (position > 0U && load_factor < candidate_values[position - 1U]) {
                    candidate_values[position] = candidate_values[position - 1U];
                    source_indices[position] = source_indices[position - 1U];
                    --position;
                }
                candidate_values[position] = load_factor;
                source_indices[position] = static_cast<std::uint32_t>(index);
                ++available;
            }
        }
        output->auxiliary_count = static_cast<std::uint32_t>(available);
    }
    if (available < config.mode_count) {
        set_contract_error(output, kContractModesUnavailable);
        return;
    }
    if (config.mode_count < available
        && same_cluster(
            candidate_values[config.mode_count - 1U],
            candidate_values[config.mode_count],
            config.cluster_relative_tolerance)) {
        set_contract_error(output, kContractClusterCut);
        return;
    }

    double* const solve_modes = matrix4;
    double* const canonical_scratch = matrix5;
    for (std::size_t selected = 0U; selected < config.mode_count; ++selected) {
        const auto source_column = source_indices[selected];
        for (std::size_t row = 0U; row < order; ++row) {
            double value = 0.0;
            for (std::size_t inner = 0U; inner < order; ++inner) {
                value += matrix3[inner * order + row]
                    * matrix6[inner * order + source_column];
            }
            solve_modes[selected * order + row] = value;
        }
    }
    std::size_t cluster_begin = 0U;
    while (cluster_begin < config.mode_count) {
        auto cluster_end = cluster_begin + 1U;
        while (cluster_end < config.mode_count
            && same_cluster(
                candidate_values[cluster_end - 1U],
                candidate_values[cluster_end],
                config.cluster_relative_tolerance)) {
            ++cluster_end;
        }
        if (!canonicalize_cluster(
                solve_modes,
                canonical_scratch,
                matrix1,
                candidate_vector,
                order,
                cluster_begin,
                cluster_end)) {
            set_numerical_failure(output, kNonconvergence);
            return;
        }
        cluster_begin = cluster_end;
    }

    for (std::size_t mode = 0U; mode < config.mode_count; ++mode) {
        for (std::size_t row = 0U; row < order; ++row) {
            output->shapes[mode * order + row] =
                recovery_scale[row] * solve_modes[mode * order + row];
        }
        const auto* const physical_mode = output->shapes + mode * order;
        matrix_vector(left, physical_mode, force_left, order);
        matrix_vector(right, physical_mode, force_right, order);
        const auto left_scalar = vector_dot(physical_mode, force_left, order);
        const auto right_scalar = vector_dot(physical_mode, force_right, order);
        double value = 0.0;
        if (problem_kind == kModal) {
            value = left_scalar;
            if (!isfinite(value) || value <= 0.0 || !isfinite(right_scalar)) {
                set_numerical_failure(output, kIndefiniteOperator);
                return;
            }
            for (std::size_t row = 0U; row < order; ++row) {
                residual[row] = force_left[row] - value * force_right[row];
            }
        } else {
            if (!isfinite(left_scalar) || !isfinite(right_scalar) || right_scalar <= 0.0) {
                set_numerical_failure(output, kIndefiniteOperator);
                return;
            }
            value = left_scalar / right_scalar;
            for (std::size_t row = 0U; row < order; ++row) {
                residual[row] = force_left[row] - value * force_right[row];
            }
        }
        const auto denominator = device_max(
            vector_inf(force_left, order) + fabs(value) * vector_inf(force_right, order),
            kMinimumNormal);
        const auto residual_relative = vector_inf(residual, order) / denominator;
        if (!isfinite(residual_relative)
            || residual_relative > config.residual_relative_tolerance) {
            set_numerical_failure(output, kResidualLimit);
            return;
        }
        output->values[mode] = value;
        output->scalar_a[mode] = left_scalar;
        output->scalar_b[mode] = right_scalar;
        output->residual_relative_inf[mode] = residual_relative;
        const auto maximum_component = vector_inf(physical_mode, order);
        if (!isfinite(maximum_component) || maximum_component <= 0.0) {
            set_numerical_failure(output, kNonconvergence);
            return;
        }
        for (std::size_t row = 0U; row < order; ++row) {
            output->max_component_shapes[mode * order + row] =
                physical_mode[row] / maximum_component;
        }
    }

    double metric_error = 0.0;
    double operator_error_absolute = 0.0;
    for (std::size_t row = 0U; row < config.mode_count; ++row) {
        for (std::size_t column = 0U; column < config.mode_count; ++column) {
            const auto* const left_mode = output->shapes + row * order;
            const auto* const right_mode = output->shapes + column * order;
            const auto metric_value = metric_dot(
                left_mode, physical_metric, right_mode, order);
            const auto operator_value = metric_dot(
                left_mode, physical_operator, right_mode, order);
            const auto expected_metric = row == column ? 1.0 : 0.0;
            double expected_operator = 0.0;
            if (row == column) {
                expected_operator = problem_kind == kModal
                    ? output->values[row]
                    : 1.0 / output->values[row];
            }
            metric_error = device_max(metric_error, fabs(metric_value - expected_metric));
            operator_error_absolute = device_max(
                operator_error_absolute, fabs(operator_value - expected_operator));
        }
    }
    double operator_scale = 1.0;
    for (std::size_t mode = 0U; mode < config.mode_count; ++mode) {
        const auto diagonal = problem_kind == kModal
            ? output->values[mode]
            : 1.0 / output->values[mode];
        operator_scale = device_max(operator_scale, fabs(diagonal));
    }
    const auto operator_error = operator_error_absolute / operator_scale;
    if (metric_error > config.orthogonality_tolerance
        || operator_error > config.orthogonality_tolerance) {
        set_numerical_failure(output, kResidualLimit);
        return;
    }
    output->metric_orthogonality_error = metric_error;
    output->operator_diagonalization_error = operator_error;
    output->mode_count = config.mode_count;
    output->critical_load_factor = problem_kind == kBuckling ? output->values[0] : 0.0;
    output->status = kConverged;
}

[[nodiscard]] solver_cpu::SolverStatus decode_status(const std::uint32_t raw) {
    if (raw != kConverged && raw != kIndefiniteOperator && raw != kNonconvergence
        && raw != kResidualLimit) {
        throw std::runtime_error(
            "HIP generalized-eigen kernel returned an invalid solver status");
    }
    return static_cast<solver_cpu::SolverStatus>(raw);
}

void throw_contract_error(const std::uint32_t error, const std::uint32_t problem_kind) {
    switch (error) {
    case kContractNone:
        return;
    case kContractModalMassPositiveDefinite:
        throw std::invalid_argument("mass must be positive definite");
    case kContractModalStiffnessPositiveSemidefinite:
        throw std::invalid_argument("stiffness violates the positive-semidefinite contract");
    case kContractBucklingStiffnessPositiveDefinite:
        throw std::invalid_argument("stiffness must be positive definite");
    case kContractBucklingGeometricPositiveSemidefinite:
        throw std::invalid_argument(
            "geometric stiffness violates the positive-semidefinite contract");
    case kContractScaledMetricPositiveDefinite:
        throw std::invalid_argument(
            problem_kind == kModal
                ? "mass must be positive definite"
                : "stiffness must be positive definite");
    case kContractModesUnavailable:
        throw std::invalid_argument(
            problem_kind == kModal
                ? "requested positive modal modes are not available"
                : "requested finite positive buckling modes are not available");
    case kContractClusterCut:
        throw std::invalid_argument(
            "requested mode_count cuts a repeated or clustered eigenvalue group");
    case kContractScaledMatrixNonfinite:
        throw std::invalid_argument(
            "coordinate-scaled generalized-eigen matrix is not finite");
    default:
        throw std::runtime_error(
            "HIP generalized-eigen kernel returned an invalid contract error");
    }
}

[[nodiscard]] RawExecution execute(
    const ProjectedInput& input,
    const solver_cpu::GeneralizedEigenConfig& config,
    const std::uint32_t problem_kind) {
    std::int32_t device_id = -1;
    check_hip(hipGetDevice(&device_id), "hipGetDevice");
    hipDeviceProp_t properties {};
    check_hip(hipGetDeviceProperties(&properties, device_id), "hipGetDeviceProperties");
    std::int32_t runtime_version = 0;
    std::int32_t driver_version = 0;
    check_hip(hipRuntimeGetVersion(&runtime_version), "hipRuntimeGetVersion");
    check_hip(hipDriverGetVersion(&driver_version), "hipDriverGetVersion");
    std::size_t free_before = 0U;
    std::size_t total_memory = 0U;
    check_hip(
        hipMemGetInfo(&free_before, &total_memory),
        "hipMemGetInfo before generalized-eigen allocation");

    const auto matrix_count = input.order * input.order;
    Stream stream;
    DeviceBuffer<double> device_left(matrix_count);
    DeviceBuffer<double> device_right(matrix_count);
    DeviceBuffer<double> device_scale(input.order);
    DeviceBuffer<double> device_workspace(kWorkspaceMatrixCount * matrix_count);
    DeviceBuffer<double> device_eigenvalues(4U * input.order);
    DeviceBuffer<double> device_vectors(4U * input.order);
    DeviceBuffer<DevicePackedResult> device_output(1U);
    const auto device_buffer_bytes = device_left.allocated_bytes()
        + device_right.allocated_bytes() + device_scale.allocated_bytes()
        + device_workspace.allocated_bytes() + device_eigenvalues.allocated_bytes()
        + device_vectors.allocated_bytes() + device_output.allocated_bytes();
    std::size_t free_after_alloc = 0U;
    std::size_t total_after_alloc = 0U;
    check_hip(
        hipMemGetInfo(&free_after_alloc, &total_after_alloc),
        "hipMemGetInfo after generalized-eigen allocation");
    if (total_after_alloc != total_memory) {
        throw std::runtime_error(
            "HIP visible VRAM changed during generalized-eigen allocation");
    }

    const auto copy_to_device = [&](void* const destination,
                                    const void* const source,
                                    const std::size_t bytes,
                                    const char* const operation) {
        check_hip(
            hipMemcpyAsync(
                destination, source, bytes, hipMemcpyHostToDevice, stream.get()),
            operation);
    };
    copy_to_device(
        device_left.get(), input.left.data(), device_left.logical_bytes(),
        "hipMemcpyAsync generalized-eigen left matrix");
    copy_to_device(
        device_right.get(), input.right.data(), device_right.logical_bytes(),
        "hipMemcpyAsync generalized-eigen right matrix");
    copy_to_device(
        device_scale.get(), input.scale.data(), device_scale.logical_bytes(),
        "hipMemcpyAsync generalized-eigen recovery scale");
    check_hip(
        hipMemsetAsync(
            device_output.get(), 0, device_output.logical_bytes(), stream.get()),
        "hipMemsetAsync generalized-eigen packed result");

    const DeviceConfig device_config {
        config.mode_count,
        config.positive_semidefinite_relative_tolerance,
        config.mode_relative_tolerance,
        config.cluster_relative_tolerance,
        config.residual_relative_tolerance,
        config.orthogonality_tolerance,
        config.eigensolver_relative_tolerance,
        config.maximum_sweeps,
        input.left_symmetry_error,
        input.right_symmetry_error,
    };
    hipLaunchKernelGGL(
        generalized_eigen_kernel,
        dim3(1U),
        dim3(1U),
        0U,
        stream.get(),
        problem_kind,
        input.order,
        device_left.get(),
        device_right.get(),
        device_scale.get(),
        device_config,
        device_workspace.get(),
        device_eigenvalues.get(),
        device_vectors.get(),
        device_output.get());
    check_hip(hipGetLastError(), "generalized_eigen_kernel launch");

    auto host_output = std::make_unique<DevicePackedResult>();
    check_hip(
        hipMemcpyAsync(
            host_output.get(),
            device_output.get(),
            sizeof(DevicePackedResult),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync generalized-eigen packed result");
    check_hip(
        hipStreamSynchronize(stream.get()),
        "hipStreamSynchronize generalized-eigen solve");
    throw_contract_error(host_output->contract_error, problem_kind);
    static_cast<void>(decode_status(host_output->status));
    if (host_output->mode_count > config.mode_count
        || host_output->mode_count > input.order) {
        throw std::runtime_error(
            "HIP generalized-eigen kernel returned an invalid mode count");
    }

    const auto h2d_bytes = device_left.logical_bytes() + device_right.logical_bytes()
        + device_scale.logical_bytes();
    const GeneralizedEigenExecutionReceipt receipt {
        device_id,
        properties.name,
        properties.gcnArchName,
        runtime_version,
        driver_version,
        __clang_version__,
        STRUCTURAL_GENERALIZED_EIGEN_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_GENERALIZED_EIGEN_HIP_SOURCE_SHA256,
        STRUCTURAL_GENERALIZED_EIGEN_HIP_DEVICE_LIB_SHA256,
        "single_thread_cyclic_jacobi_fp64.v1",
        h2d_bytes,
        sizeof(DevicePackedResult),
        3U,
        1U,
        1U,
        1U,
        device_buffer_bytes,
        total_memory,
        free_before,
        free_after_alloc,
        0U,
        true,
        true,
        true,
        true,
        0U,
        0U,
    };
    return {std::move(host_output), receipt};
}

[[nodiscard]] std::vector<double> copy_shape(
    const double* const values,
    const std::size_t order,
    const std::size_t mode) {
    return std::vector<double>(
        values + mode * order,
        values + (mode + 1U) * order);
}

}  // namespace

ModalEigenHipExecution solve_dense_modal_modes_hip(
    const solver_cpu::DenseSymmetricMatrixView stiffness,
    const solver_cpu::DenseSymmetricMatrixView mass,
    const std::span<const double> coordinate_recovery_scale,
    const solver_cpu::GeneralizedEigenConfig& config) {
    const auto input = validate_and_prepare(
        stiffness, mass, coordinate_recovery_scale, config, kModal);
    auto execution = execute(input, config, kModal);
    const auto& output = *execution.output;
    std::vector<solver_cpu::ModalEigenMode> modes;
    modes.reserve(output.mode_count);
    for (std::size_t mode = 0U; mode < output.mode_count; ++mode) {
        const auto eigenvalue = output.values[mode];
        const auto omega = std::sqrt(eigenvalue);
        modes.push_back({
            eigenvalue,
            omega,
            omega / (2.0 * kPi),
            (2.0 * kPi) / omega,
            copy_shape(output.shapes, input.order, mode),
            copy_shape(output.max_component_shapes, input.order, mode),
            output.scalar_b[mode],
            output.scalar_a[mode],
            output.residual_relative_inf[mode],
        });
    }
    solver_cpu::ModalEigenResult result {
        decode_status(output.status),
        std::move(modes),
        output.auxiliary_count,
        output.eigensolver_sweeps,
        output.metric_orthogonality_error,
        output.operator_diagonalization_error,
        output.left_symmetry_error,
        output.right_symmetry_error,
        output.left_minimum_eigenvalue,
        output.right_minimum_eigenvalue,
        0U,
    };
    return {std::move(result), std::move(execution.receipt)};
}

BucklingEigenHipExecution solve_dense_linear_buckling_hip(
    const solver_cpu::DenseSymmetricMatrixView stiffness,
    const solver_cpu::DenseSymmetricMatrixView geometric_stiffness_per_unit_load,
    const std::span<const double> coordinate_recovery_scale,
    const solver_cpu::GeneralizedEigenConfig& config) {
    const auto input = validate_and_prepare(
        stiffness,
        geometric_stiffness_per_unit_load,
        coordinate_recovery_scale,
        config,
        kBuckling);
    auto execution = execute(input, config, kBuckling);
    const auto& output = *execution.output;
    std::vector<solver_cpu::BucklingEigenMode> modes;
    modes.reserve(output.mode_count);
    for (std::size_t mode = 0U; mode < output.mode_count; ++mode) {
        modes.push_back({
            output.values[mode],
            copy_shape(output.shapes, input.order, mode),
            copy_shape(output.max_component_shapes, input.order, mode),
            output.scalar_a[mode],
            output.scalar_b[mode],
            output.residual_relative_inf[mode],
        });
    }
    solver_cpu::BucklingEigenResult result {
        decode_status(output.status),
        std::move(modes),
        output.auxiliary_count,
        output.geometric_rank,
        output.eigensolver_sweeps,
        output.critical_load_factor,
        output.metric_orthogonality_error,
        output.operator_diagonalization_error,
        output.left_symmetry_error,
        output.right_symmetry_error,
        output.left_minimum_eigenvalue,
        output.right_minimum_eigenvalue,
        0U,
    };
    return {std::move(result), std::move(execution.receipt)};
}

}  // namespace structural::hip
