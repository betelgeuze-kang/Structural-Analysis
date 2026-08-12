#include "nonlinear_static_hip.hpp"

#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <cfloat>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#ifndef STRUCTURAL_NONLINEAR_STATIC_HIP_SOURCE_SHA256
#define STRUCTURAL_NONLINEAR_STATIC_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_NONLINEAR_STATIC_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_NONLINEAR_STATIC_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_NONLINEAR_STATIC_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_NONLINEAR_STATIC_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::size_t kMaximumStoryCount = 256U;
constexpr std::uint32_t kMaximumIterations = 10'000U;
constexpr double kStoryFrameEpsilon = 1.0e-12;
constexpr std::uint32_t kActive = 0U;
constexpr std::uint32_t kConverged = 1U;
constexpr std::uint32_t kNonconverged = 2U;

struct DeviceConfig {
    std::uint32_t story_count;
    double tolerance;
    std::uint32_t max_iter;
    double hardening_ratio;
    double line_search_decay;
    double line_search_min;
    double pdelta_factor;
};

struct DeviceResult {
    std::uint32_t status;
    std::uint32_t iterations;
    std::uint32_t line_search_backtracks;
    std::uint32_t plastic_story_count;
    double residual_inf;
    double residual_l2;
    double max_abs_displacement_m;
    double top_displacement_m;
    double base_shear_kn;
};

struct AssemblyResult {
    double base_shear_kn;
    std::uint32_t plastic_story_count;
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
            throw std::invalid_argument("HIP nonlinear-static allocation count is invalid");
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

__device__ double vector_norm_inf(const double* const values, const std::size_t count) {
    double maximum = 0.0;
    for (std::size_t index = 0U; index < count; ++index) {
        maximum = fmax(maximum, fabs(values[index]));
    }
    return maximum;
}

__device__ double vector_norm_l2(const double* const values, const std::size_t count) {
    double squared = 0.0;
    for (std::size_t index = 0U; index < count; ++index) {
        squared += values[index] * values[index];
    }
    return sqrt(squared);
}

__device__ AssemblyResult assemble_story_frame(
    const DeviceConfig config,
    const double* const stiffness,
    const double* const height,
    const double* const axial,
    const double* const yield_drift,
    const double* const displacement,
    double* const spring_force,
    double* const spring_tangent,
    double* const internal_force,
    double* const lower,
    double* const diagonal,
    double* const upper) {
    std::uint32_t plastic_story_count = 0U;
    for (std::size_t index = 0U; index < config.story_count; ++index) {
        const double previous = index == 0U ? 0.0 : displacement[index - 1U];
        const double drift = displacement[index] - previous;
        const double initial_stiffness = fmax(stiffness[index], kStoryFrameEpsilon);
        const double bounded_yield_drift = fmax(fabs(yield_drift[index]), 1.0e-9);
        const double hardened_stiffness = config.hardening_ratio * initial_stiffness;
        if (fabs(drift) <= bounded_yield_drift) {
            spring_force[index] = initial_stiffness * drift;
            spring_tangent[index] = initial_stiffness;
        } else {
            const double sign = drift >= 0.0 ? 1.0 : -1.0;
            spring_force[index] = sign
                * (initial_stiffness * bounded_yield_drift
                   + hardened_stiffness * (fabs(drift) - bounded_yield_drift));
            spring_tangent[index] = hardened_stiffness;
            ++plastic_story_count;
        }
        const double bounded_height = fmax(height[index], kStoryFrameEpsilon);
        const double geometric_stiffness =
            config.pdelta_factor * fabs(axial[index]) / bounded_height;
        spring_tangent[index] -= geometric_stiffness;
    }

    for (std::size_t index = 0U; index < config.story_count; ++index) {
        internal_force[index] = index + 1U < config.story_count
            ? spring_force[index] - spring_force[index + 1U]
            : spring_force[index];
        lower[index] = 0.0;
        diagonal[index] = 0.0;
        upper[index] = 0.0;
    }
    for (std::size_t index = 0U; index < config.story_count; ++index) {
        const double current = spring_tangent[index];
        const double next = index + 1U < config.story_count
            ? spring_tangent[index + 1U]
            : 0.0;
        diagonal[index] = current + next;
        if (index > 0U) {
            lower[index - 1U] = -current;
        }
        if (index + 1U < config.story_count) {
            upper[index] = -next;
        }
    }

    double minimum_diagonal = DBL_MAX;
    for (std::size_t index = 0U; index < config.story_count; ++index) {
        minimum_diagonal = fmin(minimum_diagonal, fabs(diagonal[index]));
    }
    if (!isfinite(minimum_diagonal) || minimum_diagonal <= 1.0e-9) {
        for (std::size_t index = 0U; index < config.story_count; ++index) {
            diagonal[index] += 1.0e-6 * fmax(stiffness[index], 1.0);
        }
    }
    return {fabs(spring_force[0]) / 1000.0, plastic_story_count};
}

__device__ bool solve_tridiagonal(
    const std::size_t count,
    const double* const lower,
    const double* const diagonal,
    const double* const upper,
    const double* const right_hand_side,
    double* const upper_prime,
    double* const right_prime,
    double* const output) {
    const double first_diagonal = diagonal[0];
    if (!isfinite(first_diagonal) || fabs(first_diagonal) <= kStoryFrameEpsilon) {
        return false;
    }
    upper_prime[0] = count > 1U ? upper[0] / first_diagonal : 0.0;
    right_prime[0] = right_hand_side[0] / first_diagonal;
    for (std::size_t index = 1U; index < count; ++index) {
        const double denominator =
            diagonal[index] - lower[index - 1U] * upper_prime[index - 1U];
        if (!isfinite(denominator) || fabs(denominator) <= kStoryFrameEpsilon) {
            return false;
        }
        upper_prime[index] = index + 1U < count ? upper[index] / denominator : 0.0;
        right_prime[index] =
            (right_hand_side[index] - lower[index - 1U] * right_prime[index - 1U])
            / denominator;
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

__device__ void update_derived_state(
    const DeviceConfig config,
    const double* const stiffness,
    const double* const height,
    const double* const axial,
    const double* const yield_drift,
    const double* const floor_load,
    const double* const displacement,
    double* const spring_force,
    double* const spring_tangent,
    double* const internal_force,
    double* const lower,
    double* const diagonal,
    double* const upper,
    double* const residual,
    DeviceResult* const output) {
    const auto assembly = assemble_story_frame(
        config,
        stiffness,
        height,
        axial,
        yield_drift,
        displacement,
        spring_force,
        spring_tangent,
        internal_force,
        lower,
        diagonal,
        upper);
    double maximum_displacement = 0.0;
    for (std::size_t index = 0U; index < config.story_count; ++index) {
        residual[index] = floor_load[index] - internal_force[index];
        maximum_displacement = fmax(maximum_displacement, fabs(displacement[index]));
    }
    output->residual_inf = vector_norm_inf(residual, config.story_count);
    output->residual_l2 = vector_norm_l2(residual, config.story_count);
    output->max_abs_displacement_m = maximum_displacement;
    output->top_displacement_m = displacement[config.story_count - 1U];
    output->base_shear_kn = assembly.base_shear_kn;
    output->plastic_story_count = assembly.plastic_story_count;
}

__global__ void nonlinear_static_newton_kernel(
    const DeviceConfig config,
    const double* const stiffness,
    const double* const height,
    const double* const axial,
    const double* const yield_drift,
    const double* const floor_load,
    double* const displacement,
    double* const spring_force,
    double* const spring_tangent,
    double* const internal_force,
    double* const lower,
    double* const diagonal,
    double* const upper,
    double* const residual,
    double* const increment,
    double* const trial,
    double* const upper_prime,
    double* const right_prime,
    DeviceResult* const output) {
    if (blockIdx.x != 0U || threadIdx.x != 0U) {
        return;
    }
    output->status = kActive;
    output->iterations = 0U;
    output->line_search_backtracks = 0U;
    for (std::size_t index = 0U; index < config.story_count; ++index) {
        displacement[index] = 0.0;
    }
    update_derived_state(
        config,
        stiffness,
        height,
        axial,
        yield_drift,
        floor_load,
        displacement,
        spring_force,
        spring_tangent,
        internal_force,
        lower,
        diagonal,
        upper,
        residual,
        output);

    for (std::uint32_t iteration = 1U; iteration <= config.max_iter; ++iteration) {
        static_cast<void>(assemble_story_frame(
            config,
            stiffness,
            height,
            axial,
            yield_drift,
            displacement,
            spring_force,
            spring_tangent,
            internal_force,
            lower,
            diagonal,
            upper));
        for (std::size_t index = 0U; index < config.story_count; ++index) {
            residual[index] = floor_load[index] - internal_force[index];
        }
        const double residual_inf = vector_norm_inf(residual, config.story_count);
        if (isfinite(residual_inf) && residual_inf <= config.tolerance) {
            output->iterations = iteration;
            output->status = kConverged;
            update_derived_state(
                config,
                stiffness,
                height,
                axial,
                yield_drift,
                floor_load,
                displacement,
                spring_force,
                spring_tangent,
                internal_force,
                lower,
                diagonal,
                upper,
                residual,
                output);
            return;
        }
        if (!solve_tridiagonal(
                config.story_count,
                lower,
                diagonal,
                upper,
                residual,
                upper_prime,
                right_prime,
                increment)) {
            output->iterations = iteration;
            output->status = kNonconverged;
            update_derived_state(
                config,
                stiffness,
                height,
                axial,
                yield_drift,
                floor_load,
                displacement,
                spring_force,
                spring_tangent,
                internal_force,
                lower,
                diagonal,
                upper,
                residual,
                output);
            return;
        }

        const double baseline = fmax(residual_inf, kStoryFrameEpsilon);
        double scale = 1.0;
        bool accepted = false;
        std::uint32_t local_backtracks = 0U;
        while (scale >= config.line_search_min) {
            for (std::size_t index = 0U; index < config.story_count; ++index) {
                trial[index] = displacement[index] + scale * increment[index];
            }
            static_cast<void>(assemble_story_frame(
                config,
                stiffness,
                height,
                axial,
                yield_drift,
                trial,
                spring_force,
                spring_tangent,
                internal_force,
                lower,
                diagonal,
                upper));
            for (std::size_t index = 0U; index < config.story_count; ++index) {
                residual[index] = floor_load[index] - internal_force[index];
            }
            const double trial_norm = vector_norm_inf(residual, config.story_count);
            if (isfinite(trial_norm) && trial_norm < baseline) {
                for (std::size_t index = 0U; index < config.story_count; ++index) {
                    displacement[index] = trial[index];
                }
                accepted = true;
                break;
            }
            scale *= config.line_search_decay;
            ++local_backtracks;
        }
        output->line_search_backtracks += local_backtracks;
        output->iterations = iteration;
        update_derived_state(
            config,
            stiffness,
            height,
            axial,
            yield_drift,
            floor_load,
            displacement,
            spring_force,
            spring_tangent,
            internal_force,
            lower,
            diagonal,
            upper,
            residual,
            output);
        if (!accepted) {
            output->status = kNonconverged;
            return;
        }
        if (iteration == config.max_iter) {
            output->status = output->residual_inf <= config.tolerance
                ? kConverged
                : kNonconverged;
            return;
        }
    }
    output->status = kNonconverged;
}

}  // namespace

NonlinearStaticHipExecution solve_nonlinear_static_hip(
    const solver_cpu::NonlinearStaticConfig& config,
    const solver_cpu::NonlinearStaticInputs& inputs) {
    solver_cpu::validate_nonlinear_static_problem(config, inputs);
    if (config.story_count > kMaximumStoryCount || config.max_iter > kMaximumIterations) {
        throw std::invalid_argument(
            "HIP nonlinear-static problem exceeds the bounded device domain");
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
    check_hip(
        hipMemGetInfo(&free_before, &total_memory),
        "hipMemGetInfo before nonlinear-static allocation");

    const auto count = static_cast<std::size_t>(config.story_count);
    Stream stream;
    DeviceBuffer<double> device_stiffness(count);
    DeviceBuffer<double> device_height(count);
    DeviceBuffer<double> device_axial(count);
    DeviceBuffer<double> device_yield_drift(count);
    DeviceBuffer<double> device_floor_load(count);
    DeviceBuffer<double> device_displacement(count);
    DeviceBuffer<double> device_spring_force(count);
    DeviceBuffer<double> device_spring_tangent(count);
    DeviceBuffer<double> device_internal_force(count);
    DeviceBuffer<double> device_lower(count);
    DeviceBuffer<double> device_diagonal(count);
    DeviceBuffer<double> device_upper(count);
    DeviceBuffer<double> device_residual(count);
    DeviceBuffer<double> device_increment(count);
    DeviceBuffer<double> device_trial(count);
    DeviceBuffer<double> device_upper_prime(count);
    DeviceBuffer<double> device_right_prime(count);
    DeviceBuffer<DeviceResult> device_result(1U);

    const auto device_buffer_bytes = device_stiffness.allocated_bytes()
        + device_height.allocated_bytes() + device_axial.allocated_bytes()
        + device_yield_drift.allocated_bytes() + device_floor_load.allocated_bytes()
        + device_displacement.allocated_bytes() + device_spring_force.allocated_bytes()
        + device_spring_tangent.allocated_bytes() + device_internal_force.allocated_bytes()
        + device_lower.allocated_bytes() + device_diagonal.allocated_bytes()
        + device_upper.allocated_bytes() + device_residual.allocated_bytes()
        + device_increment.allocated_bytes() + device_trial.allocated_bytes()
        + device_upper_prime.allocated_bytes() + device_right_prime.allocated_bytes()
        + device_result.allocated_bytes();
    std::size_t free_after_alloc = 0U;
    std::size_t total_after_alloc = 0U;
    check_hip(
        hipMemGetInfo(&free_after_alloc, &total_after_alloc),
        "hipMemGetInfo after nonlinear-static allocation");
    if (total_after_alloc != total_memory) {
        throw std::runtime_error(
            "HIP visible VRAM changed during nonlinear-static allocation");
    }

    std::uint64_t h2d_bytes = 0U;
    std::uint64_t h2d_transfer_count = 0U;
    const auto copy_to_device = [&](void* const destination,
                                    const void* const source,
                                    const std::size_t bytes,
                                    const char* const operation) {
        check_hip(
            hipMemcpyAsync(
                destination, source, bytes, hipMemcpyHostToDevice, stream.get()),
            operation);
        h2d_bytes += bytes;
        ++h2d_transfer_count;
    };
    copy_to_device(
        device_stiffness.get(),
        inputs.story_stiffness_n_per_m.data(),
        device_stiffness.logical_bytes(),
        "hipMemcpyAsync nonlinear-static stiffness");
    copy_to_device(
        device_height.get(),
        inputs.story_height_m.data(),
        device_height.logical_bytes(),
        "hipMemcpyAsync nonlinear-static height");
    copy_to_device(
        device_axial.get(),
        inputs.story_axial_n.data(),
        device_axial.logical_bytes(),
        "hipMemcpyAsync nonlinear-static axial load");
    copy_to_device(
        device_yield_drift.get(),
        inputs.story_yield_drift_m.data(),
        device_yield_drift.logical_bytes(),
        "hipMemcpyAsync nonlinear-static yield drift");
    copy_to_device(
        device_floor_load.get(),
        inputs.floor_load_n.data(),
        device_floor_load.logical_bytes(),
        "hipMemcpyAsync nonlinear-static floor load");
    check_hip(
        hipMemsetAsync(
            device_displacement.get(), 0, device_displacement.logical_bytes(), stream.get()),
        "hipMemsetAsync nonlinear-static displacement");
    check_hip(
        hipMemsetAsync(device_result.get(), 0, device_result.logical_bytes(), stream.get()),
        "hipMemsetAsync nonlinear-static result");

    const DeviceConfig device_config {
        config.story_count,
        config.tolerance,
        config.max_iter,
        config.hardening_ratio,
        config.line_search_decay,
        config.line_search_min,
        config.pdelta_factor,
    };
    hipLaunchKernelGGL(
        nonlinear_static_newton_kernel,
        dim3(1U),
        dim3(1U),
        0U,
        stream.get(),
        device_config,
        device_stiffness.get(),
        device_height.get(),
        device_axial.get(),
        device_yield_drift.get(),
        device_floor_load.get(),
        device_displacement.get(),
        device_spring_force.get(),
        device_spring_tangent.get(),
        device_internal_force.get(),
        device_lower.get(),
        device_diagonal.get(),
        device_upper.get(),
        device_residual.get(),
        device_increment.get(),
        device_trial.get(),
        device_upper_prime.get(),
        device_right_prime.get(),
        device_result.get());
    check_hip(hipGetLastError(), "nonlinear_static_newton_kernel launch");

    DeviceResult host_result {};
    std::vector<double> host_displacement(count, 0.0);
    check_hip(
        hipMemcpyAsync(
            &host_result,
            device_result.get(),
            sizeof(host_result),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync nonlinear-static result");
    check_hip(
        hipMemcpyAsync(
            host_displacement.data(),
            device_displacement.get(),
            device_displacement.logical_bytes(),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync nonlinear-static displacement");
    check_hip(
        hipStreamSynchronize(stream.get()),
        "hipStreamSynchronize nonlinear-static solve");

    const std::array metrics {
        host_result.residual_inf,
        host_result.residual_l2,
        host_result.max_abs_displacement_m,
        host_result.top_displacement_m,
        host_result.base_shear_kn,
    };
    if ((host_result.status != kConverged && host_result.status != kNonconverged)
        || host_result.iterations == 0U || host_result.iterations > config.max_iter
        || host_result.plastic_story_count > config.story_count
        || !std::all_of(metrics.begin(), metrics.end(), [](const double value) {
               return std::isfinite(value);
           })
        || !std::all_of(
            host_displacement.begin(), host_displacement.end(), [](const double value) {
                return std::isfinite(value);
            })) {
        throw std::runtime_error("HIP nonlinear-static kernel returned an invalid result");
    }

    const solver_cpu::NonlinearStaticResult result {
        host_result.status == kConverged,
        host_result.iterations,
        host_result.residual_inf,
        host_result.residual_l2,
        host_result.max_abs_displacement_m,
        host_result.top_displacement_m,
        host_result.base_shear_kn,
        host_result.plastic_story_count,
        host_result.line_search_backtracks,
        std::move(host_displacement),
    };
    const NonlinearStaticExecutionReceipt receipt {
        device_id,
        properties.name,
        properties.gcnArchName,
        runtime_version,
        driver_version,
        __clang_version__,
        STRUCTURAL_NONLINEAR_STATIC_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_NONLINEAR_STATIC_HIP_SOURCE_SHA256,
        STRUCTURAL_NONLINEAR_STATIC_HIP_DEVICE_LIB_SHA256,
        "single_thread_resident_newton_fp64.v1",
        h2d_bytes,
        static_cast<std::uint64_t>(sizeof(host_result) + device_displacement.logical_bytes()),
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
        true,
        true,
        true,
        0U,
        0U,
    };
    return {result, receipt};
}

}  // namespace structural::hip
