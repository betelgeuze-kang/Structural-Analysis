#include "full_residual_hip.hpp"

#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

#ifndef STRUCTURAL_FULL_RESIDUAL_HIP_SOURCE_SHA256
#define STRUCTURAL_FULL_RESIDUAL_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_FULL_RESIDUAL_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_FULL_RESIDUAL_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_FULL_RESIDUAL_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_FULL_RESIDUAL_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::uint32_t kHipBackend = 2U;
constexpr std::uint32_t kBlockSize = 256U;
constexpr std::uint32_t kMaximumBlockCount = 4096U;

void check_hip(const hipError_t status, const char* const operation) {
    if (status != hipSuccess) {
        throw std::runtime_error(std::string(operation) + ": " + hipGetErrorString(status));
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

class Event final {
  public:
    Event() { check_hip(hipEventCreate(&value_), "hipEventCreate"); }

    Event(const Event&) = delete;
    Event& operator=(const Event&) = delete;

    ~Event() {
        if (value_ != nullptr) {
            static_cast<void>(hipEventDestroy(value_));
        }
    }

    [[nodiscard]] hipEvent_t get() const noexcept { return value_; }

  private:
    hipEvent_t value_ {nullptr};
};

template <typename Value>
class DeviceArray final {
  public:
    DeviceArray() = default;

    explicit DeviceArray(const std::size_t count) : count_(count) {
        if (count_ == 0U) {
            return;
        }
        if (count_ > std::numeric_limits<std::size_t>::max() / sizeof(Value)) {
            throw std::invalid_argument("HIP full-residual allocation count overflows");
        }
        check_hip(
            hipMalloc(reinterpret_cast<void**>(&value_), count_ * sizeof(Value)),
            "hipMalloc full residual");
    }

    DeviceArray(const DeviceArray&) = delete;
    DeviceArray& operator=(const DeviceArray&) = delete;

    DeviceArray(DeviceArray&& other) noexcept
        : value_(std::exchange(other.value_, nullptr)), count_(std::exchange(other.count_, 0U)) {}

    DeviceArray& operator=(DeviceArray&& other) noexcept {
        if (this != &other) {
            if (value_ != nullptr) {
                static_cast<void>(hipFree(value_));
            }
            value_ = std::exchange(other.value_, nullptr);
            count_ = std::exchange(other.count_, 0U);
        }
        return *this;
    }

    ~DeviceArray() {
        if (value_ != nullptr) {
            static_cast<void>(hipFree(value_));
        }
    }

    void copy_from(const std::span<const Value> source, const hipStream_t stream) {
        if (source.size() != count_) {
            throw std::invalid_argument("HIP full-residual copy length mismatch");
        }
        if (source.empty()) {
            return;
        }
        check_hip(
            hipMemcpyAsync(
                value_,
                source.data(),
                source.size_bytes(),
                hipMemcpyHostToDevice,
                stream),
            "hipMemcpyAsync full-residual operator");
    }

    [[nodiscard]] Value* get() noexcept { return value_; }
    [[nodiscard]] const Value* get() const noexcept { return value_; }
    [[nodiscard]] std::size_t bytes() const noexcept { return count_ * sizeof(Value); }

  private:
    Value* value_ {nullptr};
    std::size_t count_ {0U};
};

__global__ void deterministic_full_residual_kernel(
    const std::uint64_t* const frame_dofs,
    const double* const frame_stiffness,
    const std::uint64_t* const shell_row_offsets,
    const std::uint64_t* const shell_column_indices,
    const double* const shell_values,
    const std::uint64_t* const spring_row_offsets,
    const std::uint64_t* const spring_column_indices,
    const double* const spring_values,
    const double* const external_force,
    const std::uint64_t* const free_dofs,
    const double* const states,
    double* const residual,
    const std::uint64_t frame_element_count,
    const std::uint64_t order,
    const std::uint64_t free_dof_count,
    const std::uint64_t batch_size) {
    const auto first = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const auto stride = static_cast<std::uint64_t>(blockDim.x) * gridDim.x;
    const auto total = batch_size * free_dof_count;
    for (auto index = first; index < total; index += stride) {
        const auto batch = index / free_dof_count;
        const auto free_index = index % free_dof_count;
        const auto row = free_dofs[free_index];
        const auto* const state = states + batch * order;
        double value = 0.0;
        for (std::uint64_t element = 0U; element < frame_element_count; ++element) {
            const auto dof_base = element * solver_cpu::kFullResidualFrameDofCount;
            const auto matrix_base = element * solver_cpu::kFullResidualFrameMatrixCount;
            for (std::uint64_t local_row = 0U;
                 local_row < solver_cpu::kFullResidualFrameDofCount;
                 ++local_row) {
                if (frame_dofs[dof_base + local_row] != row) {
                    continue;
                }
                double local_value = 0.0;
                const auto stiffness_row =
                    matrix_base + local_row * solver_cpu::kFullResidualFrameDofCount;
                for (std::uint64_t local_column = 0U;
                     local_column < solver_cpu::kFullResidualFrameDofCount;
                     ++local_column) {
                    local_value += frame_stiffness[stiffness_row + local_column]
                        * state[frame_dofs[dof_base + local_column]];
                }
                value += local_value;
            }
        }
        for (auto offset = shell_row_offsets[row]; offset < shell_row_offsets[row + 1U];
             ++offset) {
            value += shell_values[offset] * state[shell_column_indices[offset]];
        }
        for (auto offset = spring_row_offsets[row]; offset < spring_row_offsets[row + 1U];
             ++offset) {
            value += spring_values[offset] * state[spring_column_indices[offset]];
        }
        residual[index] = value - external_force[row];
    }
}

[[nodiscard]] std::uint64_t transfer_count(
    const std::initializer_list<std::size_t> sizes) noexcept {
    return static_cast<std::uint64_t>(
        std::count_if(sizes.begin(), sizes.end(), [](const auto size) { return size != 0U; }));
}

class HipFullResidualContext final : public solver_cpu::FullResidualContext {
  public:
    HipFullResidualContext(
        solver_cpu::FullResidualOperator operator_data,
        const std::int32_t device_id,
        std::string device_name,
        const std::uint64_t vram_total_bytes,
        const std::uint64_t vram_free_before_bytes)
        : stream_(),
          operator_(std::move(operator_data)),
          device_id_(device_id),
          device_name_(std::move(device_name)),
          d_frame_dofs_(operator_.frame_dofs.size()),
          d_frame_stiffness_(operator_.frame_stiffness.size()),
          d_shell_row_offsets_(operator_.shell_row_offsets.size()),
          d_shell_column_indices_(operator_.shell_column_indices.size()),
          d_shell_values_(operator_.shell_values.size()),
          d_spring_row_offsets_(operator_.spring_row_offsets.size()),
          d_spring_column_indices_(operator_.spring_column_indices.size()),
          d_spring_values_(operator_.spring_values.size()),
          d_external_force_(operator_.external_force.size()),
          d_free_dofs_(operator_.free_dofs.size()),
          vram_total_bytes_(vram_total_bytes),
          vram_free_before_bytes_(vram_free_before_bytes) {
        d_frame_dofs_.copy_from(operator_.frame_dofs, stream_.get());
        d_frame_stiffness_.copy_from(operator_.frame_stiffness, stream_.get());
        d_shell_row_offsets_.copy_from(operator_.shell_row_offsets, stream_.get());
        d_shell_column_indices_.copy_from(operator_.shell_column_indices, stream_.get());
        d_shell_values_.copy_from(operator_.shell_values, stream_.get());
        d_spring_row_offsets_.copy_from(operator_.spring_row_offsets, stream_.get());
        d_spring_column_indices_.copy_from(operator_.spring_column_indices, stream_.get());
        d_spring_values_.copy_from(operator_.spring_values, stream_.get());
        d_external_force_.copy_from(operator_.external_force, stream_.get());
        d_free_dofs_.copy_from(operator_.free_dofs, stream_.get());
        check_hip(hipStreamSynchronize(stream_.get()), "hipStreamSynchronize operator upload");
        std::size_t free_after = 0U;
        std::size_t total_after = 0U;
        check_hip(hipMemGetInfo(&free_after, &total_after), "hipMemGetInfo after operator upload");
        vram_free_after_creation_bytes_ = free_after;
    }

    ~HipFullResidualContext() override {
        static_cast<void>(hipSetDevice(device_id_));
    }

    [[nodiscard]] std::uint32_t execution_backend() const noexcept override {
        return kHipBackend;
    }

    [[nodiscard]] std::int32_t device_id() const noexcept override { return device_id_; }

    [[nodiscard]] std::string_view device_name() const noexcept override { return device_name_; }

    [[nodiscard]] const solver_cpu::FullResidualOperator& operator_data() const noexcept override {
        return operator_;
    }

    [[nodiscard]] solver_cpu::FullResidualMetrics creation_metrics() const noexcept override {
        return {
            false,
            true,
            operator_bytes(),
            0U,
            operator_transfer_count(),
            0U,
            1U,
            0U,
            device_buffer_bytes(),
            vram_total_bytes_,
            vram_free_before_bytes_,
            vram_free_after_creation_bytes_,
            0.0,
            0.0,
            0.0,
            0.0,
        };
    }

    [[nodiscard]] solver_cpu::FullResidualMetrics evaluate(
        const std::span<const double> states,
        const std::size_t batch_size,
        const std::uint32_t repetitions,
        const std::span<double> residual) override {
        solver_cpu::validate_full_residual_evaluation(
            operator_, states, batch_size, repetitions, residual.size());
        check_hip(hipSetDevice(device_id_), "hipSetDevice full residual evaluate");
        const auto state_count = batch_size * operator_.order;
        const auto output_count = batch_size * operator_.free_dof_count;
        const bool reused = state_count <= state_capacity_ && output_count <= output_capacity_;
        if (!reused) {
            DeviceArray<double> staged_states(state_count);
            DeviceArray<double> staged_residual(output_count);
            d_states_ = std::move(staged_states);
            d_residual_ = std::move(staged_residual);
            state_capacity_ = state_count;
            output_capacity_ = output_count;
        }
        check_hip(
            hipMemcpyAsync(
                d_states_.get(),
                states.data(),
                states.size_bytes(),
                hipMemcpyHostToDevice,
                stream_.get()),
            "hipMemcpyAsync full-residual states");
        Event start;
        Event stop;
        check_hip(hipEventRecord(start.get(), stream_.get()), "hipEventRecord start");
        const auto total = static_cast<std::uint64_t>(output_count);
        const auto required_blocks = (total + kBlockSize - 1U) / kBlockSize;
        const auto block_count = static_cast<std::uint32_t>(
            std::min<std::uint64_t>(required_blocks, kMaximumBlockCount));
        for (std::uint32_t repetition = 0U; repetition < repetitions; ++repetition) {
            hipLaunchKernelGGL(
                deterministic_full_residual_kernel,
                dim3(block_count),
                dim3(kBlockSize),
                0U,
                stream_.get(),
                d_frame_dofs_.get(),
                d_frame_stiffness_.get(),
                d_shell_row_offsets_.get(),
                d_shell_column_indices_.get(),
                d_shell_values_.get(),
                d_spring_row_offsets_.get(),
                d_spring_column_indices_.get(),
                d_spring_values_.get(),
                d_external_force_.get(),
                d_free_dofs_.get(),
                d_states_.get(),
                d_residual_.get(),
                operator_.frame_element_count,
                operator_.order,
                operator_.free_dof_count,
                batch_size);
            check_hip(hipGetLastError(), "deterministic_full_residual_kernel launch");
        }
        check_hip(hipEventRecord(stop.get(), stream_.get()), "hipEventRecord stop");
        check_hip(
            hipMemcpyAsync(
                residual.data(),
                d_residual_.get(),
                residual.size_bytes(),
                hipMemcpyDeviceToHost,
                stream_.get()),
            "hipMemcpyAsync full-residual output");
        check_hip(hipStreamSynchronize(stream_.get()), "hipStreamSynchronize full residual");
        float elapsed_ms = 0.0F;
        check_hip(
            hipEventElapsedTime(&elapsed_ms, start.get(), stop.get()),
            "hipEventElapsedTime full residual");
        double output_abs_sum = 0.0;
        double output_max_abs = 0.0;
        for (const double value : residual) {
            if (!std::isfinite(value)) {
                throw std::runtime_error("HIP full-residual output is non-finite");
            }
            output_abs_sum += std::abs(value);
            output_max_abs = std::max(output_max_abs, std::abs(value));
        }
        std::size_t free_after = 0U;
        std::size_t total_after = 0U;
        check_hip(hipMemGetInfo(&free_after, &total_after), "hipMemGetInfo after evaluation");
        const auto elapsed = static_cast<double>(elapsed_ms);
        return {
            reused,
            true,
            states.size_bytes(),
            residual.size_bytes(),
            1U,
            1U,
            1U,
            repetitions,
            device_buffer_bytes(),
            total_after,
            vram_free_after_creation_bytes_,
            free_after,
            elapsed,
            elapsed / static_cast<double>(repetitions),
            output_abs_sum,
            output_max_abs,
        };
    }

  private:
    [[nodiscard]] std::uint64_t operator_bytes() const noexcept {
        return d_frame_dofs_.bytes() + d_frame_stiffness_.bytes()
            + d_shell_row_offsets_.bytes() + d_shell_column_indices_.bytes()
            + d_shell_values_.bytes() + d_spring_row_offsets_.bytes()
            + d_spring_column_indices_.bytes() + d_spring_values_.bytes()
            + d_external_force_.bytes() + d_free_dofs_.bytes();
    }

    [[nodiscard]] std::uint64_t operator_transfer_count() const noexcept {
        return transfer_count({
            d_frame_dofs_.bytes(),
            d_frame_stiffness_.bytes(),
            d_shell_row_offsets_.bytes(),
            d_shell_column_indices_.bytes(),
            d_shell_values_.bytes(),
            d_spring_row_offsets_.bytes(),
            d_spring_column_indices_.bytes(),
            d_spring_values_.bytes(),
            d_external_force_.bytes(),
            d_free_dofs_.bytes(),
        });
    }

    [[nodiscard]] std::uint64_t device_buffer_bytes() const noexcept {
        return operator_bytes() + d_states_.bytes() + d_residual_.bytes();
    }

    Stream stream_;
    solver_cpu::FullResidualOperator operator_;
    std::int32_t device_id_;
    std::string device_name_;
    DeviceArray<std::uint64_t> d_frame_dofs_;
    DeviceArray<double> d_frame_stiffness_;
    DeviceArray<std::uint64_t> d_shell_row_offsets_;
    DeviceArray<std::uint64_t> d_shell_column_indices_;
    DeviceArray<double> d_shell_values_;
    DeviceArray<std::uint64_t> d_spring_row_offsets_;
    DeviceArray<std::uint64_t> d_spring_column_indices_;
    DeviceArray<double> d_spring_values_;
    DeviceArray<double> d_external_force_;
    DeviceArray<std::uint64_t> d_free_dofs_;
    DeviceArray<double> d_states_;
    DeviceArray<double> d_residual_;
    std::size_t state_capacity_ {0U};
    std::size_t output_capacity_ {0U};
    std::uint64_t vram_total_bytes_;
    std::uint64_t vram_free_before_bytes_;
    std::uint64_t vram_free_after_creation_bytes_ {0U};
};

}  // namespace

FullResidualHipDeviceStatus full_residual_hip_device_status(
    const std::int32_t device_id) noexcept {
    if (device_id < 0) {
        return FullResidualHipDeviceStatus::device_mismatch;
    }
    int device_count = 0;
    const auto status = hipGetDeviceCount(&device_count);
    if (status != hipSuccess || device_count <= 0) {
        return FullResidualHipDeviceStatus::backend_unavailable;
    }
    if (device_id >= device_count) {
        return FullResidualHipDeviceStatus::device_mismatch;
    }
    return FullResidualHipDeviceStatus::available;
}

FullResidualHipBuildIdentity full_residual_hip_build_identity(
    const std::int32_t device_id) {
    const auto device_status = full_residual_hip_device_status(device_id);
    if (device_status == FullResidualHipDeviceStatus::device_mismatch) {
        throw std::invalid_argument("requested HIP full-residual device does not exist");
    }
    if (device_status != FullResidualHipDeviceStatus::available) {
        throw std::runtime_error("HIP full-residual backend is unavailable");
    }
    check_hip(hipSetDevice(device_id), "hipSetDevice full residual identity");
    hipDeviceProp_t properties {};
    check_hip(
        hipGetDeviceProperties(&properties, device_id),
        "hipGetDeviceProperties full residual identity");
    int runtime_version = 0;
    int driver_version = 0;
    check_hip(hipRuntimeGetVersion(&runtime_version), "hipRuntimeGetVersion full residual");
    check_hip(hipDriverGetVersion(&driver_version), "hipDriverGetVersion full residual");
    return {
        device_id,
        std::string(properties.name),
        std::string(properties.gcnArchName),
        runtime_version,
        driver_version,
        std::string(__clang_version__),
        STRUCTURAL_FULL_RESIDUAL_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_FULL_RESIDUAL_HIP_SOURCE_SHA256,
        STRUCTURAL_FULL_RESIDUAL_HIP_DEVICE_LIB_SHA256,
    };
}

std::unique_ptr<solver_cpu::FullResidualContext> make_hip_full_residual_context(
    solver_cpu::FullResidualOperator operator_data,
    const std::int32_t device_id) {
    const auto identity = full_residual_hip_build_identity(device_id);
    std::size_t free_before = 0U;
    std::size_t total_before = 0U;
    check_hip(hipMemGetInfo(&free_before, &total_before), "hipMemGetInfo before allocation");
    return std::make_unique<HipFullResidualContext>(
        std::move(operator_data),
        device_id,
        identity.device_name,
        total_before,
        free_before);
}

}  // namespace structural::hip
