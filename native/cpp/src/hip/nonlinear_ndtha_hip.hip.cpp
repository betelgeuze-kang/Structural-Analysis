#include "nonlinear_ndtha_hip.hpp"
#include "story_frame_hip_device.hpp"

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

#ifndef STRUCTURAL_NONLINEAR_NDTHA_HIP_SOURCE_SHA256
#define STRUCTURAL_NONLINEAR_NDTHA_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_NONLINEAR_NDTHA_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_NONLINEAR_NDTHA_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_NONLINEAR_NDTHA_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_NONLINEAR_NDTHA_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::size_t kMaximumStoryCount = 128U;
constexpr std::size_t kMaximumStepCount = 4'096U;
constexpr std::uint32_t kMaximumAdaptiveIterations = 64U;
constexpr std::uint32_t kMaximumNewtonIterations = 1'000U;
constexpr std::uint32_t kActive = 0U;
constexpr std::uint32_t kCompleted = 1U;
constexpr std::uint32_t kCollapsed = 2U;
constexpr std::uint32_t kNonconverged = 3U;

struct DeviceConfig {
    std::uint32_t story_count;
    std::uint32_t step_count;
    double dt_s;
    double newmark_beta;
    double newmark_gamma;
    double tolerance;
    std::uint32_t max_step_iterations;
    double adaptive_load_decay;
    double damping_force_cap_ratio;
    std::uint32_t newton_max_iter;
    double line_search_decay;
    double line_search_min;
    double hardening_ratio;
    double pdelta_factor;
    double collapse_drift_threshold_pct;
};

struct DeviceStepResult {
    bool converged;
    std::uint32_t adaptive_iterations;
    std::uint32_t plastic_story_count;
    double base_shear_kn;
    double residual_inf;
    std::uint32_t line_search_backtracks;
};

struct DeviceSummary {
    std::uint32_t status;
    std::uint32_t step_count_completed;
    std::int32_t collapse_step;
    std::uint32_t max_plastic_story_count;
    std::uint64_t adaptive_iteration_sum;
    std::uint32_t total_line_search_backtracks;
    std::uint32_t reserved;
    double collapse_time_s;
    double collapse_drift_ratio_pct;
    double collapse_top_displacement_m;
    double max_drift_ratio_pct;
    double avg_step_iterations;
    double residual_top_displacement_m;
    double residual_drift_ratio_pct;
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

template <typename T> class DeviceBuffer final {
  public:
    explicit DeviceBuffer(const std::size_t logical_count)
        : logical_count_(logical_count),
          allocated_count_(std::max<std::size_t>(1U, logical_count)) {
        if (allocated_count_ > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
            throw std::invalid_argument("HIP nonlinear-NDTHA allocation count is invalid");
        }
        check_hip(hipMalloc(reinterpret_cast<void**>(&value_), allocated_count_ * sizeof(T)),
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
    [[nodiscard]] std::size_t logical_bytes() const noexcept { return logical_count_ * sizeof(T); }
    [[nodiscard]] std::size_t allocated_bytes() const noexcept {
        return allocated_count_ * sizeof(T);
    }

  private:
    T* value_ {nullptr};
    std::size_t logical_count_;
    std::size_t allocated_count_;
};

__device__ DeviceStepResult
solve_step(const DeviceConfig config, const double* const stiffness, const double* const height,
           const double* const axial, const double* const yield_drift, const double* const mass,
           const double* const damping, const double* const external_force,
           const double* const previous_displacement, const double* const previous_velocity,
           const double* const previous_acceleration, double* const next_displacement,
           double* const next_velocity, double* const next_acceleration,
           double* const predicted_displacement, double* const predicted_velocity,
           double* const trial_displacement, double* const candidate_displacement,
           double* const trial_force, double* const spring_force, double* const spring_tangent,
           double* const internal_force, double* const lower, double* const diagonal,
           double* const upper, double* const effective_diagonal, double* const residual,
           double* const increment, double* const upper_prime, double* const right_prime) {
    const auto count = static_cast<std::size_t>(config.story_count);
    const double dt = fmax(config.dt_s, device_detail::kStoryFrameEpsilon);
    const double beta = fmax(config.newmark_beta, device_detail::kStoryFrameEpsilon);
    const double gamma = fmax(config.newmark_gamma, device_detail::kStoryFrameEpsilon);
    const double acceleration_coefficient = 1.0 / (beta * dt * dt);
    const double damping_coefficient = gamma / (beta * dt);

    for (std::size_t index = 0U; index < count; ++index) {
        predicted_displacement[index] = previous_displacement[index] +
                                        dt * previous_velocity[index] +
                                        dt * dt * (0.5 - beta) * previous_acceleration[index];
        predicted_velocity[index] =
            previous_velocity[index] + dt * (1.0 - gamma) * previous_acceleration[index];
        trial_displacement[index] = previous_displacement[index];
    }

    double load_scale = 1.0;
    std::uint32_t adaptive_iterations = 0U;
    double last_residual_inf = DBL_MAX;
    double last_base_shear_kn = 0.0;
    std::uint32_t last_plastic_story_count = 0U;
    std::uint32_t total_backtracks = 0U;

    for (std::uint32_t attempt = 1U; attempt <= config.max_step_iterations; ++attempt) {
        adaptive_iterations = attempt;
        for (std::size_t index = 0U; index < count; ++index) {
            trial_force[index] = external_force[index] * load_scale;
        }

        bool success = false;
        for (std::uint32_t iteration = 1U; iteration <= config.newton_max_iter; ++iteration) {
            static_cast<void>(iteration);
            const auto assembly = device_detail::assemble_story_frame(
                count, config.hardening_ratio, config.pdelta_factor, stiffness, height, axial,
                yield_drift, trial_displacement, spring_force, spring_tangent, internal_force,
                lower, diagonal, upper);
            last_base_shear_kn = assembly.base_shear_kn;
            last_plastic_story_count = assembly.plastic_story_count;

            for (std::size_t index = 0U; index < count; ++index) {
                const double acceleration =
                    acceleration_coefficient *
                    (trial_displacement[index] - predicted_displacement[index]);
                const double velocity = predicted_velocity[index] + gamma * dt * acceleration;
                residual[index] = trial_force[index] - internal_force[index] -
                                  damping[index] * velocity - mass[index] * acceleration;
            }
            const double residual_inf = device_detail::vector_norm_inf(residual, count);
            last_residual_inf = residual_inf;
            if (residual_inf <= config.tolerance) {
                for (std::size_t index = 0U; index < count; ++index) {
                    next_displacement[index] = trial_displacement[index];
                    next_acceleration[index] =
                        acceleration_coefficient *
                        (next_displacement[index] - predicted_displacement[index]);
                    next_velocity[index] =
                        predicted_velocity[index] + gamma * dt * next_acceleration[index];
                }
                success = true;
                break;
            }

            for (std::size_t index = 0U; index < count; ++index) {
                effective_diagonal[index] = diagonal[index] +
                                            mass[index] * acceleration_coefficient +
                                            damping[index] * damping_coefficient;
            }
            if (!device_detail::solve_tridiagonal(count, lower, effective_diagonal, upper, residual,
                                                  upper_prime, right_prime, increment)) {
                break;
            }

            const double baseline = fmax(residual_inf, device_detail::kStoryFrameEpsilon);
            double scale = 1.0;
            bool accepted = false;
            while (scale >= config.line_search_min) {
                for (std::size_t index = 0U; index < count; ++index) {
                    candidate_displacement[index] =
                        trial_displacement[index] + scale * increment[index];
                }
                static_cast<void>(device_detail::assemble_story_frame(
                    count, config.hardening_ratio, config.pdelta_factor, stiffness, height, axial,
                    yield_drift, candidate_displacement, spring_force, spring_tangent,
                    internal_force, lower, diagonal, upper));
                for (std::size_t index = 0U; index < count; ++index) {
                    const double acceleration =
                        acceleration_coefficient *
                        (candidate_displacement[index] - predicted_displacement[index]);
                    const double velocity = predicted_velocity[index] + gamma * dt * acceleration;
                    residual[index] = trial_force[index] - internal_force[index] -
                                      damping[index] * velocity - mass[index] * acceleration;
                }
                const double candidate_norm = device_detail::vector_norm_inf(residual, count);
                if (candidate_norm < baseline) {
                    for (std::size_t index = 0U; index < count; ++index) {
                        trial_displacement[index] = candidate_displacement[index];
                    }
                    accepted = true;
                    break;
                }
                scale *= config.line_search_decay;
                ++total_backtracks;
            }
            if (!accepted) {
                break;
            }
        }

        if (success) {
            return {
                true,
                adaptive_iterations,
                last_plastic_story_count,
                last_base_shear_kn,
                last_residual_inf,
                total_backtracks,
            };
        }
        load_scale *= config.adaptive_load_decay;
    }

    for (std::size_t index = 0U; index < count; ++index) {
        next_displacement[index] = previous_displacement[index];
        next_velocity[index] = previous_velocity[index];
        next_acceleration[index] = previous_acceleration[index];
    }
    return {
        false,
        adaptive_iterations > 0U ? adaptive_iterations : 1U,
        last_plastic_story_count,
        last_base_shear_kn,
        last_residual_inf,
        total_backtracks,
    };
}

__global__ void nonlinear_ndtha_kernel(
    const DeviceConfig config, const double* const stiffness, const double* const height,
    const double* const axial, const double* const yield_drift, const double* const mass,
    const double* const damping, const double* const floor_load, const double* const acceleration_g,
    const double* const height_shape, double* const displacement, double* const velocity,
    double* const acceleration, double* const next_displacement, double* const next_velocity,
    double* const next_acceleration, double* const external_force,
    double* const predicted_displacement, double* const predicted_velocity,
    double* const trial_displacement, double* const candidate_displacement,
    double* const trial_force, double* const spring_force, double* const spring_tangent,
    double* const internal_force, double* const lower, double* const diagonal, double* const upper,
    double* const effective_diagonal, double* const residual, double* const increment,
    double* const upper_prime, double* const right_prime, double* const story_drift_pct,
    double* const story_shear_kn, double* const response_top_displacement,
    double* const response_drift_ratio, double* const response_base_shear,
    double* const response_core_drift, double* const response_core_shear,
    std::uint8_t* const response_step_converged, std::uint32_t* const response_step_iterations,
    std::uint32_t* const response_step_plastic_count, double* const response_step_residual,
    double* const story_drift_envelope, double* const final_story_drift,
    DeviceSummary* const output) {
    if (blockIdx.x != 0U || threadIdx.x != 0U) {
        return;
    }
    output->status = kActive;
    output->step_count_completed = 0U;
    output->collapse_step = -1;
    output->max_plastic_story_count = 0U;
    output->adaptive_iteration_sum = 0U;
    output->total_line_search_backtracks = 0U;
    output->reserved = 0U;
    output->collapse_time_s = 0.0;
    output->collapse_drift_ratio_pct = 0.0;
    output->collapse_top_displacement_m = 0.0;
    output->max_drift_ratio_pct = 0.0;
    output->avg_step_iterations = 0.0;
    output->residual_top_displacement_m = 0.0;
    output->residual_drift_ratio_pct = 0.0;

    for (std::size_t index = 0U; index < config.story_count; ++index) {
        displacement[index] = 0.0;
        velocity[index] = 0.0;
        acceleration[index] = 0.0;
        story_drift_envelope[index] = 0.0;
        final_story_drift[index] = 0.0;
    }
    for (std::size_t step = 0U; step < config.step_count; ++step) {
        response_top_displacement[step] = 0.0;
        response_drift_ratio[step] = 0.0;
        response_base_shear[step] = 0.0;
        response_core_drift[step] = 0.0;
        response_core_shear[step] = 0.0;
        response_step_converged[step] = 0U;
        response_step_iterations[step] = 0U;
        response_step_plastic_count[step] = 0U;
        response_step_residual[step] = 0.0;
    }

    const auto story_count = static_cast<std::size_t>(config.story_count);
    const auto step_count = static_cast<std::size_t>(config.step_count);
    for (std::size_t step = 0U; step < step_count; ++step) {
        const double ground_acceleration = acceleration_g[step];
        const double sign =
            fabs(ground_acceleration) > 1.0e-12 ? (ground_acceleration >= 0.0 ? 1.0 : -1.0) : 1.0;
        const auto denominator = step_count > 1U ? step_count - 1U : 1U;
        const double envelope =
            1.0 + 0.50 * (static_cast<double>(step) / static_cast<double>(denominator));
        for (std::size_t index = 0U; index < story_count; ++index) {
            const double static_force = floor_load[index] * height_shape[index] * envelope *
                                        (0.25 * ground_acceleration + 0.02 * sign);
            const double inertial_force =
                -(mass[index] * height_shape[index]) * (ground_acceleration * 9.80665 * 0.05);
            const double raw_force = static_force + inertial_force;
            double damping_force = damping[index] * velocity[index];
            const double damping_cap = fmax(fabs(raw_force) * config.damping_force_cap_ratio, 1.0);
            damping_force = fmin(fmax(damping_force, -damping_cap), damping_cap);
            external_force[index] = raw_force - damping_force;
        }

        const auto step_result =
            solve_step(config, stiffness, height, axial, yield_drift, mass, damping, external_force,
                       displacement, velocity, acceleration, next_displacement, next_velocity,
                       next_acceleration, predicted_displacement, predicted_velocity,
                       trial_displacement, candidate_displacement, trial_force, spring_force,
                       spring_tangent, internal_force, lower, diagonal, upper, effective_diagonal,
                       residual, increment, upper_prime, right_prime);
        response_step_converged[step] = step_result.converged ? 1U : 0U;
        response_step_iterations[step] = step_result.adaptive_iterations;
        response_step_plastic_count[step] = step_result.plastic_story_count;
        response_step_residual[step] = step_result.residual_inf;
        output->adaptive_iteration_sum += step_result.adaptive_iterations;
        output->total_line_search_backtracks += step_result.line_search_backtracks;
        output->step_count_completed = static_cast<std::uint32_t>(step + 1U);

        if (!step_result.converged) {
            output->status = kNonconverged;
            break;
        }

        for (std::size_t index = 0U; index < story_count; ++index) {
            displacement[index] = next_displacement[index];
            velocity[index] = next_velocity[index];
            acceleration[index] = next_acceleration[index];
        }
        device_detail::recover_story_response(story_count, displacement, height, stiffness,
                                              story_drift_pct, story_shear_kn);
        for (std::size_t index = 0U; index < story_count; ++index) {
            final_story_drift[index] = story_drift_pct[index];
            story_drift_envelope[index] =
                fmax(story_drift_envelope[index], fabs(story_drift_pct[index]));
        }
        const double drift_ratio_pct = device_detail::vector_norm_inf(story_drift_pct, story_count);
        const double top_displacement = displacement[story_count - 1U];
        response_top_displacement[step] = top_displacement;
        response_drift_ratio[step] = drift_ratio_pct;
        response_base_shear[step] = step_result.base_shear_kn;
        response_core_drift[step] = story_drift_pct[0];
        response_core_shear[step] = story_shear_kn[0];
        output->max_plastic_story_count =
            output->max_plastic_story_count > step_result.plastic_story_count
                ? output->max_plastic_story_count
                : step_result.plastic_story_count;
        output->max_drift_ratio_pct = fmax(output->max_drift_ratio_pct, drift_ratio_pct);

        if (drift_ratio_pct > config.collapse_drift_threshold_pct) {
            output->status = kCollapsed;
            output->collapse_step = static_cast<std::int32_t>(step);
            output->collapse_time_s = static_cast<double>(step) * config.dt_s;
            output->collapse_drift_ratio_pct = drift_ratio_pct;
            output->collapse_top_displacement_m = top_displacement;
            break;
        }
    }

    if (output->status == kActive && output->step_count_completed == config.step_count) {
        output->status = kCompleted;
    }
    output->avg_step_iterations = output->step_count_completed > 0U
                                      ? static_cast<double>(output->adaptive_iteration_sum) /
                                            static_cast<double>(output->step_count_completed)
                                      : 0.0;
    output->residual_top_displacement_m = displacement[story_count - 1U];
    output->residual_drift_ratio_pct =
        device_detail::vector_norm_inf(final_story_drift, story_count);
}

template <typename T>
void copy_from_device(std::vector<T>& destination, const DeviceBuffer<T>& source,
                      hipStream_t stream, const char* const operation) {
    check_hip(hipMemcpyAsync(destination.data(), source.get(), source.logical_bytes(),
                             hipMemcpyDeviceToHost, stream),
              operation);
}

[[nodiscard]] bool finite_vector(const std::vector<double>& values) {
    return std::all_of(values.begin(), values.end(),
                       [](const double value) { return std::isfinite(value); });
}

} // namespace

NonlinearNdthaHipExecution
solve_nonlinear_ndtha_hip(const solver_cpu::NonlinearNdthaConfig& config,
                          const solver_cpu::NonlinearNdthaInputs& inputs) {
    solver_cpu::validate_nonlinear_ndtha_problem(config, inputs);
    if (config.story_count > kMaximumStoryCount || config.step_count > kMaximumStepCount ||
        config.max_step_iterations > kMaximumAdaptiveIterations ||
        config.newton_max_iter > kMaximumNewtonIterations) {
        throw std::invalid_argument(
            "HIP nonlinear-NDTHA problem exceeds the bounded device domain");
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
    check_hip(hipMemGetInfo(&free_before, &total_memory),
              "hipMemGetInfo before nonlinear-NDTHA allocation");

    const auto stories = static_cast<std::size_t>(config.story_count);
    const auto steps = static_cast<std::size_t>(config.step_count);
    const auto height_shape = solver_cpu::nonlinear_ndtha_height_shape(stories);
    Stream stream;
    DeviceBuffer<double> device_stiffness(stories);
    DeviceBuffer<double> device_height(stories);
    DeviceBuffer<double> device_axial(stories);
    DeviceBuffer<double> device_yield_drift(stories);
    DeviceBuffer<double> device_mass(stories);
    DeviceBuffer<double> device_damping(stories);
    DeviceBuffer<double> device_floor_load(stories);
    DeviceBuffer<double> device_acceleration_g(steps);
    DeviceBuffer<double> device_height_shape(stories);
    DeviceBuffer<double> device_displacement(stories);
    DeviceBuffer<double> device_velocity(stories);
    DeviceBuffer<double> device_acceleration(stories);
    DeviceBuffer<double> device_next_displacement(stories);
    DeviceBuffer<double> device_next_velocity(stories);
    DeviceBuffer<double> device_next_acceleration(stories);
    DeviceBuffer<double> device_external_force(stories);
    DeviceBuffer<double> device_predicted_displacement(stories);
    DeviceBuffer<double> device_predicted_velocity(stories);
    DeviceBuffer<double> device_trial_displacement(stories);
    DeviceBuffer<double> device_candidate_displacement(stories);
    DeviceBuffer<double> device_trial_force(stories);
    DeviceBuffer<double> device_spring_force(stories);
    DeviceBuffer<double> device_spring_tangent(stories);
    DeviceBuffer<double> device_internal_force(stories);
    DeviceBuffer<double> device_lower(stories);
    DeviceBuffer<double> device_diagonal(stories);
    DeviceBuffer<double> device_upper(stories);
    DeviceBuffer<double> device_effective_diagonal(stories);
    DeviceBuffer<double> device_residual(stories);
    DeviceBuffer<double> device_increment(stories);
    DeviceBuffer<double> device_upper_prime(stories);
    DeviceBuffer<double> device_right_prime(stories);
    DeviceBuffer<double> device_story_drift(stories);
    DeviceBuffer<double> device_story_shear(stories);
    DeviceBuffer<double> device_response_top(steps);
    DeviceBuffer<double> device_response_drift(steps);
    DeviceBuffer<double> device_response_base_shear(steps);
    DeviceBuffer<double> device_response_core_drift(steps);
    DeviceBuffer<double> device_response_core_shear(steps);
    DeviceBuffer<std::uint8_t> device_response_converged(steps);
    DeviceBuffer<std::uint32_t> device_response_iterations(steps);
    DeviceBuffer<std::uint32_t> device_response_plastic_count(steps);
    DeviceBuffer<double> device_response_residual(steps);
    DeviceBuffer<double> device_story_envelope(stories);
    DeviceBuffer<double> device_final_story_drift(stories);
    DeviceBuffer<DeviceSummary> device_summary(1U);

    const std::array story_double_buffers {
        &device_stiffness,
        &device_height,
        &device_axial,
        &device_yield_drift,
        &device_mass,
        &device_damping,
        &device_floor_load,
        &device_height_shape,
        &device_displacement,
        &device_velocity,
        &device_acceleration,
        &device_next_displacement,
        &device_next_velocity,
        &device_next_acceleration,
        &device_external_force,
        &device_predicted_displacement,
        &device_predicted_velocity,
        &device_trial_displacement,
        &device_candidate_displacement,
        &device_trial_force,
        &device_spring_force,
        &device_spring_tangent,
        &device_internal_force,
        &device_lower,
        &device_diagonal,
        &device_upper,
        &device_effective_diagonal,
        &device_residual,
        &device_increment,
        &device_upper_prime,
        &device_right_prime,
        &device_story_drift,
        &device_story_shear,
        &device_story_envelope,
        &device_final_story_drift,
    };
    const std::array step_double_buffers {
        &device_acceleration_g,      &device_response_top,        &device_response_drift,
        &device_response_base_shear, &device_response_core_drift, &device_response_core_shear,
        &device_response_residual,
    };
    std::uint64_t device_buffer_bytes = device_summary.allocated_bytes() +
                                        device_response_converged.allocated_bytes() +
                                        device_response_iterations.allocated_bytes() +
                                        device_response_plastic_count.allocated_bytes();
    for (const auto* const buffer : story_double_buffers) {
        device_buffer_bytes += buffer->allocated_bytes();
    }
    for (const auto* const buffer : step_double_buffers) {
        device_buffer_bytes += buffer->allocated_bytes();
    }

    std::size_t free_after_alloc = 0U;
    std::size_t total_after_alloc = 0U;
    check_hip(hipMemGetInfo(&free_after_alloc, &total_after_alloc),
              "hipMemGetInfo after nonlinear-NDTHA allocation");
    if (total_after_alloc != total_memory) {
        throw std::runtime_error("HIP visible VRAM changed during nonlinear-NDTHA allocation");
    }

    std::uint64_t h2d_bytes = 0U;
    std::uint64_t h2d_transfer_count = 0U;
    const auto copy_to_device = [&](void* const destination, const void* const source,
                                    const std::size_t bytes, const char* const operation) {
        check_hip(hipMemcpyAsync(destination, source, bytes, hipMemcpyHostToDevice, stream.get()),
                  operation);
        h2d_bytes += bytes;
        ++h2d_transfer_count;
    };
    copy_to_device(device_stiffness.get(), inputs.story_stiffness_n_per_m.data(),
                   device_stiffness.logical_bytes(), "hipMemcpyAsync NDTHA stiffness");
    copy_to_device(device_height.get(), inputs.story_height_m.data(), device_height.logical_bytes(),
                   "hipMemcpyAsync NDTHA height");
    copy_to_device(device_axial.get(), inputs.story_axial_n.data(), device_axial.logical_bytes(),
                   "hipMemcpyAsync NDTHA axial");
    copy_to_device(device_yield_drift.get(), inputs.story_yield_drift_m.data(),
                   device_yield_drift.logical_bytes(), "hipMemcpyAsync NDTHA yield drift");
    copy_to_device(device_mass.get(), inputs.story_mass_kg.data(), device_mass.logical_bytes(),
                   "hipMemcpyAsync NDTHA mass");
    copy_to_device(device_damping.get(), inputs.story_damping_n_s_per_m.data(),
                   device_damping.logical_bytes(), "hipMemcpyAsync NDTHA damping");
    copy_to_device(device_floor_load.get(), inputs.floor_load_base_n.data(),
                   device_floor_load.logical_bytes(), "hipMemcpyAsync NDTHA floor load");
    copy_to_device(device_acceleration_g.get(), inputs.acceleration_g.data(),
                   device_acceleration_g.logical_bytes(),
                   "hipMemcpyAsync NDTHA acceleration record");
    copy_to_device(device_height_shape.get(), height_shape.data(),
                   device_height_shape.logical_bytes(), "hipMemcpyAsync NDTHA height shape");

    const DeviceConfig device_config {
        config.story_count,         config.step_count,          config.dt_s,
        config.newmark_beta,        config.newmark_gamma,       config.tolerance,
        config.max_step_iterations, config.adaptive_load_decay, config.damping_force_cap_ratio,
        config.newton_max_iter,     config.line_search_decay,   config.line_search_min,
        config.hardening_ratio,     config.pdelta_factor,       config.collapse_drift_threshold_pct,
    };
    hipLaunchKernelGGL(
        nonlinear_ndtha_kernel, dim3(1U), dim3(1U), 0U, stream.get(), device_config,
        device_stiffness.get(), device_height.get(), device_axial.get(), device_yield_drift.get(),
        device_mass.get(), device_damping.get(), device_floor_load.get(),
        device_acceleration_g.get(), device_height_shape.get(), device_displacement.get(),
        device_velocity.get(), device_acceleration.get(), device_next_displacement.get(),
        device_next_velocity.get(), device_next_acceleration.get(), device_external_force.get(),
        device_predicted_displacement.get(), device_predicted_velocity.get(),
        device_trial_displacement.get(), device_candidate_displacement.get(),
        device_trial_force.get(), device_spring_force.get(), device_spring_tangent.get(),
        device_internal_force.get(), device_lower.get(), device_diagonal.get(), device_upper.get(),
        device_effective_diagonal.get(), device_residual.get(), device_increment.get(),
        device_upper_prime.get(), device_right_prime.get(), device_story_drift.get(),
        device_story_shear.get(), device_response_top.get(), device_response_drift.get(),
        device_response_base_shear.get(), device_response_core_drift.get(),
        device_response_core_shear.get(), device_response_converged.get(),
        device_response_iterations.get(), device_response_plastic_count.get(),
        device_response_residual.get(), device_story_envelope.get(), device_final_story_drift.get(),
        device_summary.get());
    check_hip(hipGetLastError(), "nonlinear_ndtha_kernel launch");

    DeviceSummary summary {};
    solver_cpu::NonlinearNdthaResponse response {
        std::vector<double>(steps, 0.0),       std::vector<double>(steps, 0.0),
        std::vector<double>(steps, 0.0),       std::vector<double>(steps, 0.0),
        std::vector<double>(steps, 0.0),       std::vector<std::uint8_t>(steps, 0U),
        std::vector<std::uint32_t>(steps, 0U), std::vector<std::uint32_t>(steps, 0U),
        std::vector<double>(steps, 0.0),       std::vector<double>(stories, 0.0),
        std::vector<double>(stories, 0.0),
    };
    check_hip(hipMemcpyAsync(&summary, device_summary.get(), sizeof(summary), hipMemcpyDeviceToHost,
                             stream.get()),
              "hipMemcpyAsync NDTHA summary");
    copy_from_device(response.top_displacement_m, device_response_top, stream.get(),
                     "hipMemcpyAsync NDTHA top displacement");
    copy_from_device(response.drift_ratio_pct, device_response_drift, stream.get(),
                     "hipMemcpyAsync NDTHA drift ratio");
    copy_from_device(response.base_shear_kn, device_response_base_shear, stream.get(),
                     "hipMemcpyAsync NDTHA base shear");
    copy_from_device(response.core_drift_pct, device_response_core_drift, stream.get(),
                     "hipMemcpyAsync NDTHA core drift");
    copy_from_device(response.core_shear_kn, device_response_core_shear, stream.get(),
                     "hipMemcpyAsync NDTHA core shear");
    copy_from_device(response.step_converged, device_response_converged, stream.get(),
                     "hipMemcpyAsync NDTHA convergence flags");
    copy_from_device(response.step_iterations, device_response_iterations, stream.get(),
                     "hipMemcpyAsync NDTHA step iterations");
    copy_from_device(response.step_plastic_story_count, device_response_plastic_count, stream.get(),
                     "hipMemcpyAsync NDTHA plastic counts");
    copy_from_device(response.step_residual_inf, device_response_residual, stream.get(),
                     "hipMemcpyAsync NDTHA step residuals");
    copy_from_device(response.story_drift_envelope_pct, device_story_envelope, stream.get(),
                     "hipMemcpyAsync NDTHA drift envelope");
    copy_from_device(response.final_story_drift_pct, device_final_story_drift, stream.get(),
                     "hipMemcpyAsync NDTHA final story drift");
    check_hip(hipStreamSynchronize(stream.get()), "hipStreamSynchronize nonlinear-NDTHA solve");

    const std::array summary_values {
        summary.collapse_time_s,
        summary.collapse_drift_ratio_pct,
        summary.collapse_top_displacement_m,
        summary.max_drift_ratio_pct,
        summary.avg_step_iterations,
        summary.residual_top_displacement_m,
        summary.residual_drift_ratio_pct,
    };
    const bool response_finite =
        finite_vector(response.top_displacement_m) && finite_vector(response.drift_ratio_pct) &&
        finite_vector(response.base_shear_kn) && finite_vector(response.core_drift_pct) &&
        finite_vector(response.core_shear_kn) && finite_vector(response.step_residual_inf) &&
        finite_vector(response.story_drift_envelope_pct) &&
        finite_vector(response.final_story_drift_pct);
    const bool response_metadata_valid =
        std::all_of(response.step_converged.begin(), response.step_converged.end(),
                    [](const std::uint8_t value) { return value <= 1U; }) &&
        std::all_of(
            response.step_iterations.begin(), response.step_iterations.end(),
            [&](const std::uint32_t value) { return value <= config.max_step_iterations; }) &&
        std::all_of(response.step_plastic_story_count.begin(),
                    response.step_plastic_story_count.end(),
                    [&](const std::uint32_t value) { return value <= config.story_count; });
    if ((summary.status != kCompleted && summary.status != kCollapsed &&
         summary.status != kNonconverged) ||
        summary.step_count_completed == 0U || summary.step_count_completed > config.step_count ||
        summary.max_plastic_story_count > config.story_count ||
        !std::all_of(summary_values.begin(), summary_values.end(),
                     [](const double value) { return std::isfinite(value); }) ||
        !response_finite || !response_metadata_valid) {
        throw std::runtime_error("HIP nonlinear-NDTHA kernel returned an invalid result");
    }

    const solver_cpu::NonlinearNdthaResult result {
        summary.status == kCompleted,
        summary.status == kCollapsed,
        summary.collapse_step,
        summary.collapse_time_s,
        summary.collapse_drift_ratio_pct,
        summary.collapse_top_displacement_m,
        summary.step_count_completed,
        summary.max_plastic_story_count,
        summary.max_drift_ratio_pct,
        summary.avg_step_iterations,
        summary.residual_top_displacement_m,
        summary.residual_drift_ratio_pct,
        summary.total_line_search_backtracks,
        std::move(response),
    };
    const auto d2h_bytes = static_cast<std::uint64_t>(
        sizeof(summary) + 6U * steps * sizeof(double) + steps * sizeof(std::uint8_t) +
        2U * steps * sizeof(std::uint32_t) + 2U * stories * sizeof(double));
    const NonlinearNdthaExecutionReceipt receipt {
        device_id,
        properties.name,
        properties.gcnArchName,
        runtime_version,
        driver_version,
        __clang_version__,
        STRUCTURAL_NONLINEAR_NDTHA_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_NONLINEAR_NDTHA_HIP_SOURCE_SHA256,
        STRUCTURAL_NONLINEAR_NDTHA_HIP_DEVICE_LIB_SHA256,
        "single_thread_resident_newmark_newton_fp64.v1",
        h2d_bytes,
        d2h_bytes,
        h2d_transfer_count,
        12U,
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
        true,
        0U,
        0U,
        0U,
    };
    return {result, receipt};
}

} // namespace structural::hip
