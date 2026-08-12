#include "sparse_linear_hip.hpp"

#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#ifndef STRUCTURAL_SPARSE_HIP_SOURCE_SHA256
#define STRUCTURAL_SPARSE_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_SPARSE_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_SPARSE_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_SPARSE_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_SPARSE_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::size_t kMaximumOrder = 65'536U;
constexpr std::size_t kMaximumNonzeros = 4'000'000U;
constexpr std::uint32_t kMaximumIterations = 10'000U;
constexpr std::uint32_t kBlockSize = 256U;
constexpr double kMachineEpsilon = 2.2204460492503130808472633361816e-16;
constexpr double kBreakdownFactor = 64.0;
constexpr std::uint32_t kActive = std::numeric_limits<std::uint32_t>::max();
constexpr std::uint32_t kConverged = 0U;
constexpr std::uint32_t kSingularity = 2U;
constexpr std::uint32_t kIndefiniteOperator = 3U;
constexpr std::uint32_t kNonconvergence = 4U;
constexpr std::uint32_t kIncrementLimit = 5U;
constexpr std::uint32_t kResidualLimit = 6U;
constexpr std::uint32_t kBackendUnavailable = 9U;

struct DeviceConfig {
    std::uint32_t max_iterations;
    double absolute_residual_tolerance;
    double relative_residual_tolerance;
    double maximum_increment;
};

struct DeviceSolveResult {
    std::uint32_t status;
    std::uint32_t iterations;
    double initial_residual_inf;
    double final_residual_inf;
    double final_residual_l2;
    double last_increment_inf;
};

struct KernelState {
    std::uint32_t status;
    std::uint32_t iterations;
    double initial_residual_inf;
    double last_increment_inf;
    double convergence_limit;
    double rho;
    double alpha;
    double beta;
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

    [[nodiscard]] hipStream_t get() const noexcept {
        return value_;
    }

  private:
    hipStream_t value_ {nullptr};
};

template <typename T>
class DeviceBuffer final {
  public:
    explicit DeviceBuffer(const std::size_t logical_count)
        : logical_count_(logical_count), allocated_count_(std::max<std::size_t>(1U, logical_count)) {
        if (allocated_count_ > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
            throw std::invalid_argument("HIP sparse allocation count is invalid");
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

    [[nodiscard]] T* get() noexcept {
        return value_;
    }

    [[nodiscard]] const T* get() const noexcept {
        return value_;
    }

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

__device__ double block_sum(const double value, double* const scratch) {
    const auto lane = threadIdx.x;
    scratch[lane] = value;
    __syncthreads();
    for (std::uint32_t offset = kBlockSize / 2U; offset > 0U; offset /= 2U) {
        if (lane < offset) {
            scratch[lane] += scratch[lane + offset];
        }
        __syncthreads();
    }
    return scratch[0];
}

__device__ double block_max(const double value, double* const scratch) {
    const auto lane = threadIdx.x;
    scratch[lane] = value;
    __syncthreads();
    for (std::uint32_t offset = kBlockSize / 2U; offset > 0U; offset /= 2U) {
        if (lane < offset) {
            scratch[lane] = fmax(scratch[lane], scratch[lane + offset]);
        }
        __syncthreads();
    }
    return scratch[0];
}

__device__ double vector_dot(
    const double* const left,
    const double* const right,
    const std::size_t length,
    double* const scratch) {
    double partial = 0.0;
    for (std::size_t index = threadIdx.x; index < length; index += blockDim.x) {
        partial += left[index] * right[index];
    }
    return block_sum(partial, scratch);
}

__device__ double vector_norm_inf(
    const double* const values,
    const std::size_t length,
    double* const scratch) {
    double partial = 0.0;
    for (std::size_t index = threadIdx.x; index < length; index += blockDim.x) {
        partial = fmax(partial, fabs(values[index]));
    }
    return block_max(partial, scratch);
}

__device__ double vector_norm_l2(
    const double* const values,
    const std::size_t length,
    double* const scratch) {
    const auto squared = vector_dot(values, values, length, scratch);
    return sqrt(squared);
}

__device__ void sparse_matvec(
    const std::size_t order,
    const std::uint64_t* const row_offsets,
    const std::uint32_t* const column_indices,
    const double* const values,
    const double* const input,
    double* const output) {
    for (std::size_t row = threadIdx.x; row < order; row += blockDim.x) {
        double total = 0.0;
        for (auto offset = row_offsets[row]; offset < row_offsets[row + 1U]; ++offset) {
            total += values[offset] * input[column_indices[offset]];
        }
        output[row] = total;
    }
}

__global__ void sparse_pcg_kernel(
    const std::size_t order,
    const std::uint64_t* const row_offsets,
    const std::uint32_t* const column_indices,
    const double* const values,
    const double* const right_hand_side,
    const DeviceConfig config,
    double* const solution,
    double* const product,
    double* const residual,
    double* const diagonal_inverse,
    double* const preconditioned,
    double* const direction,
    double* const operator_direction,
    double* const candidate,
    DeviceSolveResult* const output) {
    __shared__ double scratch[kBlockSize];
    __shared__ KernelState state;

    if (threadIdx.x == 0U) {
        state.status = kActive;
        state.iterations = 0U;
        state.initial_residual_inf = 0.0;
        state.last_increment_inf = 0.0;
        state.convergence_limit = 0.0;
        state.rho = 0.0;
        state.alpha = 0.0;
        state.beta = 0.0;
    }
    __syncthreads();

    sparse_matvec(order, row_offsets, column_indices, values, solution, product);
    __syncthreads();
    for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
        residual[index] = right_hand_side[index] - product[index];
    }
    __syncthreads();
    const auto initial_residual_inf = vector_norm_inf(residual, order, scratch);
    const auto right_hand_side_inf = vector_norm_inf(right_hand_side, order, scratch);
    if (threadIdx.x == 0U) {
        state.initial_residual_inf = initial_residual_inf;
        state.convergence_limit = config.absolute_residual_tolerance
            + config.relative_residual_tolerance * right_hand_side_inf;
        for (std::size_t row = 0U; row < order; ++row) {
            bool found = false;
            double diagonal = 0.0;
            for (auto offset = row_offsets[row]; offset < row_offsets[row + 1U]; ++offset) {
                if (column_indices[offset] == row) {
                    diagonal = values[offset];
                    found = true;
                    break;
                }
            }
            if (!found || diagonal == 0.0) {
                state.status = kSingularity;
                break;
            }
            if (diagonal < 0.0) {
                state.status = kIndefiniteOperator;
                break;
            }
            diagonal_inverse[row] = 1.0 / diagonal;
            if (!isfinite(diagonal_inverse[row])) {
                state.status = kSingularity;
                break;
            }
        }
        if (state.status == kActive && initial_residual_inf <= state.convergence_limit) {
            state.status = kConverged;
        }
    }
    __syncthreads();

    if (state.status == kActive) {
        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            preconditioned[index] = diagonal_inverse[index] * residual[index];
            direction[index] = preconditioned[index];
        }
        __syncthreads();
        const auto rho = vector_dot(residual, preconditioned, order, scratch);
        if (threadIdx.x == 0U) {
            if (!isfinite(rho) || rho <= 0.0) {
                state.status = kIndefiniteOperator;
            } else {
                state.rho = rho;
            }
        }
        __syncthreads();
    }

    for (std::uint32_t iteration = 1U;
         iteration <= config.max_iterations && state.status == kActive;
         ++iteration) {
        sparse_matvec(
            order,
            row_offsets,
            column_indices,
            values,
            direction,
            operator_direction);
        __syncthreads();
        const auto denominator = vector_dot(direction, operator_direction, order, scratch);
        const auto direction_l2 = vector_norm_l2(direction, order, scratch);
        const auto operator_direction_l2 =
            vector_norm_l2(operator_direction, order, scratch);
        if (threadIdx.x == 0U) {
            const auto breakdown_scale = kBreakdownFactor * kMachineEpsilon
                * fmax(1.0, direction_l2 * operator_direction_l2);
            if (!isfinite(denominator) || denominator <= breakdown_scale) {
                state.status = denominator < -breakdown_scale
                    ? kIndefiniteOperator
                    : kSingularity;
                state.iterations = iteration - 1U;
            } else {
                state.alpha = state.rho / denominator;
                if (!isfinite(state.alpha)) {
                    state.status = kSingularity;
                    state.iterations = iteration - 1U;
                }
            }
        }
        __syncthreads();
        if (state.status != kActive) {
            break;
        }

        double local_increment_inf = 0.0;
        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            const auto increment = state.alpha * direction[index];
            local_increment_inf = fmax(local_increment_inf, fabs(increment));
            candidate[index] = solution[index] + increment;
        }
        const auto increment_inf = block_max(local_increment_inf, scratch);
        if (threadIdx.x == 0U) {
            state.last_increment_inf = increment_inf;
            if (config.maximum_increment > 0.0
                && increment_inf > config.maximum_increment) {
                state.status = kIncrementLimit;
                state.iterations = iteration - 1U;
            }
        }
        __syncthreads();
        if (state.status != kActive) {
            break;
        }

        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            solution[index] = candidate[index];
            residual[index] -= state.alpha * operator_direction[index];
        }
        __syncthreads();
        const auto recursive_residual_inf = vector_norm_inf(residual, order, scratch);
        if (recursive_residual_inf <= state.convergence_limit) {
            sparse_matvec(order, row_offsets, column_indices, values, solution, product);
            __syncthreads();
            for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
                residual[index] = right_hand_side[index] - product[index];
            }
            __syncthreads();
            const auto true_residual_inf = vector_norm_inf(residual, order, scratch);
            if (threadIdx.x == 0U) {
                state.status = true_residual_inf <= state.convergence_limit
                    ? kConverged
                    : kResidualLimit;
                state.iterations = iteration;
            }
            __syncthreads();
            break;
        }

        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            preconditioned[index] = diagonal_inverse[index] * residual[index];
        }
        __syncthreads();
        const auto next_rho = vector_dot(residual, preconditioned, order, scratch);
        if (threadIdx.x == 0U) {
            if (!isfinite(next_rho) || next_rho <= 0.0) {
                state.status = kIndefiniteOperator;
                state.iterations = iteration;
            } else {
                state.beta = next_rho / state.rho;
                if (!isfinite(state.beta)) {
                    state.status = kSingularity;
                    state.iterations = iteration;
                }
            }
        }
        __syncthreads();
        if (state.status != kActive) {
            break;
        }
        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            direction[index] = preconditioned[index] + state.beta * direction[index];
        }
        __syncthreads();
        if (threadIdx.x == 0U) {
            state.rho = next_rho;
        }
        __syncthreads();
    }

    if (state.status == kActive) {
        sparse_matvec(order, row_offsets, column_indices, values, solution, product);
        __syncthreads();
        for (std::size_t index = threadIdx.x; index < order; index += blockDim.x) {
            residual[index] = right_hand_side[index] - product[index];
        }
        __syncthreads();
        if (threadIdx.x == 0U) {
            state.status = kNonconvergence;
            state.iterations = config.max_iterations;
        }
        __syncthreads();
    }

    const auto final_residual_inf = vector_norm_inf(residual, order, scratch);
    const auto final_residual_l2 = vector_norm_l2(residual, order, scratch);
    if (threadIdx.x == 0U) {
        output->status = state.status;
        output->iterations = state.iterations;
        output->initial_residual_inf = state.initial_residual_inf;
        output->final_residual_inf = final_residual_inf;
        output->final_residual_l2 = final_residual_l2;
        output->last_increment_inf = state.last_increment_inf;
    }
}

[[nodiscard]] solver_cpu::SolverStatus decode_status(const std::uint32_t raw) {
    if (raw > kBackendUnavailable || raw == 1U) {
        throw std::runtime_error("HIP sparse kernel returned an invalid solver status");
    }
    return static_cast<solver_cpu::SolverStatus>(raw);
}

}  // namespace

SparseLinearHipExecution solve_sparse_spd_pcg_hip(
    const solver_cpu::CsrMatrixView matrix,
    const std::span<const double> right_hand_side,
    const std::span<const double> initial_guess,
    const solver_cpu::SparseLinearConfig& config) {
    solver_cpu::validate_sparse_spd_problem(
        matrix, right_hand_side, initial_guess, config);
    if (matrix.order > kMaximumOrder || matrix.values.size() > kMaximumNonzeros
        || config.max_iterations > kMaximumIterations) {
        throw std::invalid_argument("HIP sparse PCG problem exceeds the bounded device domain");
    }

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
    check_hip(hipMemGetInfo(&free_before, &total_memory), "hipMemGetInfo before allocation");

    Stream stream;
    DeviceBuffer<std::uint64_t> device_rows(matrix.row_offsets.size());
    DeviceBuffer<std::uint32_t> device_columns(matrix.column_indices.size());
    DeviceBuffer<double> device_values(matrix.values.size());
    DeviceBuffer<double> device_rhs(right_hand_side.size());
    DeviceBuffer<double> device_solution(matrix.order);
    DeviceBuffer<double> device_product(matrix.order);
    DeviceBuffer<double> device_residual(matrix.order);
    DeviceBuffer<double> device_diagonal_inverse(matrix.order);
    DeviceBuffer<double> device_preconditioned(matrix.order);
    DeviceBuffer<double> device_direction(matrix.order);
    DeviceBuffer<double> device_operator_direction(matrix.order);
    DeviceBuffer<double> device_candidate(matrix.order);
    DeviceBuffer<DeviceSolveResult> device_result(1U);

    const auto device_buffer_bytes = device_rows.allocated_bytes()
        + device_columns.allocated_bytes() + device_values.allocated_bytes()
        + device_rhs.allocated_bytes() + device_solution.allocated_bytes()
        + device_product.allocated_bytes() + device_residual.allocated_bytes()
        + device_diagonal_inverse.allocated_bytes() + device_preconditioned.allocated_bytes()
        + device_direction.allocated_bytes() + device_operator_direction.allocated_bytes()
        + device_candidate.allocated_bytes() + device_result.allocated_bytes();
    std::size_t free_after_alloc = 0U;
    std::size_t total_after_alloc = 0U;
    check_hip(
        hipMemGetInfo(&free_after_alloc, &total_after_alloc),
        "hipMemGetInfo after allocation");
    if (total_after_alloc != total_memory) {
        throw std::runtime_error("HIP visible VRAM changed during sparse allocation");
    }

    std::uint64_t h2d_bytes = 0U;
    std::uint64_t h2d_transfer_count = 0U;
    const auto copy_to_device = [&](void* const destination,
                                    const void* const source,
                                    const std::size_t bytes,
                                    const char* const operation) {
        if (bytes == 0U) {
            return;
        }
        check_hip(
            hipMemcpyAsync(
                destination, source, bytes, hipMemcpyHostToDevice, stream.get()),
            operation);
        h2d_bytes += bytes;
        ++h2d_transfer_count;
    };
    copy_to_device(
        device_rows.get(),
        matrix.row_offsets.data(),
        device_rows.logical_bytes(),
        "hipMemcpyAsync sparse row offsets");
    copy_to_device(
        device_columns.get(),
        matrix.column_indices.data(),
        device_columns.logical_bytes(),
        "hipMemcpyAsync sparse column indices");
    copy_to_device(
        device_values.get(),
        matrix.values.data(),
        device_values.logical_bytes(),
        "hipMemcpyAsync sparse values");
    copy_to_device(
        device_rhs.get(),
        right_hand_side.data(),
        device_rhs.logical_bytes(),
        "hipMemcpyAsync sparse right-hand side");
    if (initial_guess.empty()) {
        check_hip(
            hipMemsetAsync(
                device_solution.get(), 0, device_solution.logical_bytes(), stream.get()),
            "hipMemsetAsync sparse initial solution");
    } else {
        copy_to_device(
            device_solution.get(),
            initial_guess.data(),
            device_solution.logical_bytes(),
            "hipMemcpyAsync sparse initial solution");
    }

    const DeviceConfig device_config {
        config.max_iterations,
        config.absolute_residual_tolerance,
        config.relative_residual_tolerance,
        config.maximum_increment,
    };
    hipLaunchKernelGGL(
        sparse_pcg_kernel,
        dim3(1U),
        dim3(kBlockSize),
        0U,
        stream.get(),
        matrix.order,
        device_rows.get(),
        device_columns.get(),
        device_values.get(),
        device_rhs.get(),
        device_config,
        device_solution.get(),
        device_product.get(),
        device_residual.get(),
        device_diagonal_inverse.get(),
        device_preconditioned.get(),
        device_direction.get(),
        device_operator_direction.get(),
        device_candidate.get(),
        device_result.get());
    check_hip(hipGetLastError(), "sparse_pcg_kernel launch");

    DeviceSolveResult host_result {};
    std::vector<double> host_solution(matrix.order, 0.0);
    check_hip(
        hipMemcpyAsync(
            &host_result,
            device_result.get(),
            sizeof(host_result),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync sparse result");
    check_hip(
        hipMemcpyAsync(
            host_solution.data(),
            device_solution.get(),
            device_solution.logical_bytes(),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync sparse solution");
    check_hip(hipStreamSynchronize(stream.get()), "hipStreamSynchronize sparse solve");

    const auto metrics_finite = std::isfinite(host_result.initial_residual_inf)
        && std::isfinite(host_result.final_residual_inf)
        && std::isfinite(host_result.final_residual_l2)
        && std::isfinite(host_result.last_increment_inf)
        && std::all_of(host_solution.begin(), host_solution.end(), [](const double value) {
               return std::isfinite(value);
           });
    if (!metrics_finite) {
        throw std::runtime_error("HIP sparse kernel returned a non-finite result");
    }

    const solver_cpu::SparseLinearResult result {
        decode_status(host_result.status),
        std::move(host_solution),
        host_result.iterations,
        host_result.initial_residual_inf,
        host_result.final_residual_inf,
        host_result.final_residual_l2,
        host_result.last_increment_inf,
        0U,
    };
    const SparseLinearExecutionReceipt receipt {
        device_id,
        properties.name,
        properties.gcnArchName,
        runtime_version,
        driver_version,
        __clang_version__,
        STRUCTURAL_SPARSE_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_SPARSE_HIP_SOURCE_SHA256,
        STRUCTURAL_SPARSE_HIP_DEVICE_LIB_SHA256,
        "single_block_fixed_tree_fp64.v1",
        h2d_bytes,
        static_cast<std::uint64_t>(sizeof(host_result) + device_solution.logical_bytes()),
        h2d_transfer_count,
        2U,
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
        0U,
        0U,
    };
    return {result, receipt};
}

}  // namespace structural::hip
