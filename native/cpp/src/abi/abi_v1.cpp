#include "structural/abi_v1.h"

#include "../model_ir/model_ir.hpp"
#include "../solver_cpu/nonlinear_ndtha.hpp"
#include "../solver_cpu/nonlinear_static.hpp"
#include "../solver_cpu/track_point_load.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <unordered_map>

static_assert(sizeof(void*) == 8U);
static_assert(sizeof(double) == 8U);
static_assert(std::numeric_limits<double>::is_iec559);
static_assert(std::is_standard_layout_v<sa_header_v1>);
static_assert(sizeof(sa_header_v1) == 8U);
static_assert(sizeof(sa_buffer_view_v1) == 48U);
static_assert(offsetof(sa_buffer_view_v1, data) == 8U);
static_assert(offsetof(sa_buffer_view_v1, flags) == 44U);
static_assert(sizeof(sa_mut_buffer_view_v1) == 48U);
static_assert(offsetof(sa_mut_buffer_view_v1, data) == 8U);
static_assert(offsetof(sa_mut_buffer_view_v1, flags) == 44U);
static_assert(sizeof(sa_error_buffer_v1) == 32U);
static_assert(offsetof(sa_error_buffer_v1, required) == 24U);
static_assert(sizeof(sa_api_request_v1) == 40U);
static_assert(sizeof(sa_api_v1) == 128U);
static_assert(offsetof(sa_api_v1, validate_buffer_view) == 16U);
static_assert(offsetof(sa_api_v1, model_ir_create) == 24U);
static_assert(offsetof(sa_api_v1, model_ir_snapshot_write) == 64U);
static_assert(offsetof(sa_api_v1, track_point_load_solve) == 72U);
static_assert(offsetof(sa_api_v1, nonlinear_static_solve) == 80U);
static_assert(offsetof(sa_api_v1, nonlinear_ndtha_solve) == 88U);
static_assert(offsetof(sa_api_v1, reserved) == 96U);
static_assert(sizeof(sa_track_point_load_config_v1) == 112U);
static_assert(offsetof(sa_track_point_load_config_v1, length_m) == 8U);
static_assert(offsetof(sa_track_point_load_config_v1, bending_stiffness_n_m2) == 32U);
static_assert(offsetof(sa_track_point_load_config_v1, point_force_n) == 80U);
static_assert(offsetof(sa_track_point_load_config_v1, reserved) == 96U);
static_assert(sizeof(sa_track_point_load_result_v1) == 64U);
static_assert(offsetof(sa_track_point_load_result_v1, residual_inf) == 16U);
static_assert(offsetof(sa_track_point_load_result_v1, output_length) == 40U);
static_assert(offsetof(sa_track_point_load_result_v1, execution_backend) == 48U);
static_assert(sizeof(sa_nonlinear_static_config_v1) == 80U);
static_assert(offsetof(sa_nonlinear_static_config_v1, story_count) == 8U);
static_assert(offsetof(sa_nonlinear_static_config_v1, tolerance) == 16U);
static_assert(offsetof(sa_nonlinear_static_config_v1, pdelta_factor) == 48U);
static_assert(offsetof(sa_nonlinear_static_config_v1, reserved) == 64U);
static_assert(sizeof(sa_nonlinear_static_result_v1) == 88U);
static_assert(offsetof(sa_nonlinear_static_result_v1, residual_inf) == 16U);
static_assert(offsetof(sa_nonlinear_static_result_v1, base_shear_kn) == 48U);
static_assert(offsetof(sa_nonlinear_static_result_v1, output_length) == 64U);
static_assert(offsetof(sa_nonlinear_static_result_v1, execution_backend) == 72U);
static_assert(sizeof(sa_nonlinear_ndtha_config_v1) == 144U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, story_count) == 8U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, dt_s) == 16U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, max_step_iterations) == 48U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, adaptive_load_decay) == 56U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, newton_max_iter) == 72U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, line_search_decay) == 80U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, collapse_drift_threshold_pct) == 112U);
static_assert(offsetof(sa_nonlinear_ndtha_config_v1, reserved) == 128U);
static_assert(sizeof(sa_nonlinear_ndtha_inputs_v1) == 408U);
static_assert(offsetof(sa_nonlinear_ndtha_inputs_v1, story_stiffness_n_per_m) == 8U);
static_assert(offsetof(sa_nonlinear_ndtha_inputs_v1, acceleration_g) == 344U);
static_assert(offsetof(sa_nonlinear_ndtha_inputs_v1, reserved) == 392U);
static_assert(sizeof(sa_nonlinear_ndtha_outputs_v1) == 552U);
static_assert(offsetof(sa_nonlinear_ndtha_outputs_v1, top_displacement_m) == 8U);
static_assert(offsetof(sa_nonlinear_ndtha_outputs_v1, step_converged) == 248U);
static_assert(offsetof(sa_nonlinear_ndtha_outputs_v1, story_drift_envelope_pct) == 440U);
static_assert(offsetof(sa_nonlinear_ndtha_outputs_v1, reserved) == 536U);
static_assert(sizeof(sa_nonlinear_ndtha_result_v1) == 128U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, collapse_step) == 16U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, collapse_time_s) == 24U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, max_plastic_story_count) == 80U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, output_story_count) == 88U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, execution_backend) == 104U);
static_assert(offsetof(sa_nonlinear_ndtha_result_v1, reserved) == 112U);
static_assert(sizeof(sa_string_view_v1) == 16U);
static_assert(sizeof(sa_optional_string_view_v1) == 24U);

struct sa_model_ir_handle_v1 {
    std::uint64_t token;
};

namespace {

constexpr std::uint32_t kCurrentAbi = SA_ABI_V1_CURRENT;

using ModelRegistry = std::unordered_map<
    const sa_model_ir_handle_v1*,
    std::shared_ptr<const structural::model_ir::Model>>;

[[nodiscard]] ModelRegistry& model_registry() {
    static ModelRegistry registry;
    return registry;
}

[[nodiscard]] std::mutex& model_registry_mutex() {
    static std::mutex mutex;
    return mutex;
}

[[nodiscard]] std::shared_ptr<const structural::model_ir::Model> acquire_model(
    const sa_model_ir_handle_v1* const handle) {
    if (handle == nullptr) {
        throw structural::model_ir::Error(SA_ERR_INVALID_ARGUMENT, "ModelIR handle is null");
    }
    const std::lock_guard lock {model_registry_mutex()};
    const auto found = model_registry().find(handle);
    if (found == model_registry().end()) {
        throw structural::model_ir::Error(SA_ERR_INVALID_ARGUMENT, "ModelIR handle is not live");
    }
    return found->second;
}

[[nodiscard]] bool supported_version(const std::uint32_t version) noexcept {
    return SA_ABI_VERSION_MAJOR(version) == SA_ABI_VERSION_MAJOR(kCurrentAbi)
        && SA_ABI_VERSION_MINOR(version) <= SA_ABI_VERSION_MINOR(kCurrentAbi);
}

[[nodiscard]] sa_status_code_v1 prepare_error(sa_error_buffer_v1* const error) noexcept {
    if (error == nullptr) {
        return SA_OK;
    }
    if (!supported_version(error->abi_version)) {
        return SA_ERR_ABI_VERSION_MISMATCH;
    }
    if (error->struct_size < sizeof(sa_error_buffer_v1)) {
        return SA_ERR_STRUCT_SIZE;
    }
    if ((error->capacity == 0U && error->data != nullptr)
        || (error->capacity > 0U && error->data == nullptr)
        || error->capacity > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        return SA_ERR_INVALID_ARGUMENT;
    }
    error->required = 0U;
    if (error->capacity > 0U) {
        error->data[0] = '\0';
    }
    return SA_OK;
}

[[nodiscard]] sa_status_code_v1 report_error(
    sa_error_buffer_v1* const error,
    const sa_status_code_v1 status,
    const std::string_view message) noexcept {
    if (error == nullptr || error->struct_size < sizeof(sa_error_buffer_v1)
        || !supported_version(error->abi_version)) {
        return status;
    }
    const auto required = message.size() + 1U;
    error->required = static_cast<std::uint64_t>(required);
    if (error->data == nullptr || error->capacity == 0U) {
        return status;
    }
    const auto capacity = static_cast<std::size_t>(error->capacity);
    const auto copied = std::min(message.size(), capacity - 1U);
    std::memcpy(error->data, message.data(), copied);
    error->data[copied] = '\0';
    return status;
}

[[nodiscard]] std::uint64_t element_size(const std::uint32_t element_type) noexcept {
    switch (element_type) {
    case SA_ELEMENT_TYPE_F64:
    case SA_ELEMENT_TYPE_U64:
        return 8U;
    case SA_ELEMENT_TYPE_I32:
    case SA_ELEMENT_TYPE_U32:
        return 4U;
    case SA_ELEMENT_TYPE_U8:
        return 1U;
    default:
        return 0U;
    }
}

[[nodiscard]] sa_status_code_v1 validate_buffer_view_impl(
    const sa_buffer_view_v1* const view,
    sa_error_buffer_v1* const error) {
    if (view == nullptr) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer view is null");
    }
    if (!supported_version(view->abi_version)) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "buffer view ABI is unsupported");
    }
    if (view->struct_size < sizeof(sa_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "buffer view struct_size is too small");
    }
    if (view->flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer view flags are not zero");
    }
    const auto width = element_size(view->element_type);
    if (width == 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer element_type is unknown");
    }
    if (view->memory_space == SA_MEMORY_SPACE_DEVICE) {
        if (view->device_id < 0) {
            return report_error(error, SA_ERR_DEVICE_MISMATCH, "device buffer has no device id");
        }
        return report_error(error, SA_ERR_BACKEND_UNAVAILABLE, "device buffer requires HIP context");
    }
    if (view->memory_space != SA_MEMORY_SPACE_HOST || view->device_id != -1) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "host buffer memory metadata is invalid");
    }
    if (view->length == 0U) {
        if (view->data != nullptr) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "empty buffer data must be null");
        }
        return SA_OK;
    }
    if (view->data == nullptr) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "non-empty buffer data is null");
    }
    if (view->stride_bytes < width) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer stride is smaller than element size");
    }
    if (view->length > std::numeric_limits<std::uint64_t>::max() / view->stride_bytes) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer length and stride overflow");
    }
    const auto extent = view->length * view->stride_bytes;
    if (extent > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer extent exceeds host address space");
    }
    const auto address = reinterpret_cast<std::uintptr_t>(view->data);
    if (extent > 0U && address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "buffer pointer extent overflows");
    }
    return SA_OK;
}

[[nodiscard]] sa_status_code_v1 validate_buffer_view_boundary(
    const sa_buffer_view_v1* const view,
    sa_error_buffer_v1* const error) noexcept {
    const auto error_status = prepare_error(error);
    if (error_status != SA_OK) {
        return error_status;
    }
    try {
        return validate_buffer_view_impl(view, error);
    } catch (const std::bad_alloc&) {
        return report_error(error, SA_ERR_INTERNAL, "native allocation failed");
    } catch (const std::exception&) {
        return report_error(error, SA_ERR_INTERNAL, "native exception was contained");
    } catch (...) {
        return report_error(error, SA_ERR_INTERNAL, "unknown native exception was contained");
    }
}

template <typename Operation>
[[nodiscard]] sa_status_code_v1 contain_boundary(
    sa_error_buffer_v1* const error,
    Operation operation) noexcept {
    const auto error_status = prepare_error(error);
    if (error_status != SA_OK) {
        return error_status;
    }
    try {
        return operation();
    } catch (const structural::model_ir::Error& exception) {
        return report_error(error, exception.status(), exception.what());
    } catch (const std::bad_alloc&) {
        return report_error(error, SA_ERR_INTERNAL, "native allocation failed");
    } catch (const std::exception&) {
        return report_error(error, SA_ERR_INTERNAL, "native exception was contained");
    } catch (...) {
        return report_error(error, SA_ERR_INTERNAL, "unknown native exception was contained");
    }
}

[[nodiscard]] sa_status_code_v1 model_ir_create_boundary(
    const sa_model_ir_descriptor_v1* const descriptor,
    sa_model_ir_handle_v1** const out_handle,
    sa_error_buffer_v1* const error) noexcept {
    return contain_boundary(error, [descriptor, out_handle, error]() -> sa_status_code_v1 {
        if (descriptor == nullptr || out_handle == nullptr) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR descriptor or output is null");
        }
        auto model = std::make_shared<structural::model_ir::Model>(*descriptor);
        auto handle = std::make_unique<sa_model_ir_handle_v1>();
        handle->token = reinterpret_cast<std::uintptr_t>(handle.get());
        {
            const std::lock_guard lock {model_registry_mutex()};
            model_registry().emplace(handle.get(), std::move(model));
        }
        *out_handle = handle.release();
        return SA_OK;
    });
}

[[nodiscard]] sa_status_code_v1 model_ir_destroy_boundary(
    sa_model_ir_handle_v1* const handle,
    sa_error_buffer_v1* const error) noexcept {
    return contain_boundary(error, [handle, error]() -> sa_status_code_v1 {
        if (handle == nullptr) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR handle is null");
        }
        {
            const std::lock_guard lock {model_registry_mutex()};
            const auto found = model_registry().find(handle);
            if (found == model_registry().end()) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR handle is not live");
            }
            if (found->second.use_count() != 1L) {
                return report_error(
                    error, SA_ERR_STATE_CONFLICT, "ModelIR handle has an in-flight immutable call");
            }
            model_registry().erase(found);
        }
        delete handle;
        return SA_OK;
    });
}

[[nodiscard]] sa_status_code_v1 immutable_size_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint64_t* const out_size,
    sa_error_buffer_v1* const error,
    const bool report) noexcept {
    return contain_boundary(error, [handle, out_size, error, report]() -> sa_status_code_v1 {
        if (out_size == nullptr) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR handle or size output is null");
        }
        const auto model = acquire_model(handle);
        const auto value = report ? model->validation_report() : model->snapshot();
        *out_size = static_cast<std::uint64_t>(value.size());
        return SA_OK;
    });
}

[[nodiscard]] sa_status_code_v1 immutable_write_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint8_t* const output,
    const std::uint64_t capacity,
    std::uint64_t* const out_written,
    sa_error_buffer_v1* const error,
    const bool report) noexcept {
    return contain_boundary(
        error,
        [handle, output, capacity, out_written, error, report]() -> sa_status_code_v1 {
        if (out_written == nullptr) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR handle or write output is null");
        }
        if ((capacity == 0U && output != nullptr) || (capacity > 0U && output == nullptr)
            || capacity > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR output pointer or capacity is invalid");
        }
        const auto model = acquire_model(handle);
        const auto value = report ? model->validation_report() : model->snapshot();
        if (capacity < static_cast<std::uint64_t>(value.size())) {
            return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "ModelIR output buffer is too small");
        }
        if (!value.empty()) {
            const auto address = reinterpret_cast<std::uintptr_t>(output);
            if (address > std::numeric_limits<std::uintptr_t>::max() - (value.size() - 1U)) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "ModelIR output pointer extent overflows");
            }
            std::memcpy(output, value.data(), value.size());
        }
        *out_written = static_cast<std::uint64_t>(value.size());
        return SA_OK;
        });
}

[[nodiscard]] sa_status_code_v1 model_ir_validation_report_size_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint64_t* const out_size,
    sa_error_buffer_v1* const error) noexcept {
    return immutable_size_boundary(handle, out_size, error, true);
}

[[nodiscard]] sa_status_code_v1 model_ir_validation_report_write_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint8_t* const output,
    const std::uint64_t capacity,
    std::uint64_t* const out_written,
    sa_error_buffer_v1* const error) noexcept {
    return immutable_write_boundary(handle, output, capacity, out_written, error, true);
}

[[nodiscard]] sa_status_code_v1 model_ir_snapshot_size_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint64_t* const out_size,
    sa_error_buffer_v1* const error) noexcept {
    return immutable_size_boundary(handle, out_size, error, false);
}

[[nodiscard]] sa_status_code_v1 model_ir_snapshot_write_boundary(
    const sa_model_ir_handle_v1* const handle,
    std::uint8_t* const output,
    const std::uint64_t capacity,
    std::uint64_t* const out_written,
    sa_error_buffer_v1* const error) noexcept {
    return immutable_write_boundary(handle, output, capacity, out_written, error, false);
}

template <typename Value>
[[nodiscard]] bool pointer_is_aligned(const Value* const value) noexcept {
    return value != nullptr
        && reinterpret_cast<std::uintptr_t>(value) % alignof(Value) == 0U;
}

[[nodiscard]] sa_status_code_v1 validate_track_output(
    const sa_mut_buffer_view_v1* const view,
    const std::uint64_t expected_length,
    const std::string_view label,
    sa_error_buffer_v1* const error) {
    if (!pointer_is_aligned(view)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "track output descriptor is null or misaligned");
    }
    if (view->abi_version != SA_ABI_V1_2) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "track output ABI is not v1.2");
    }
    if (view->struct_size < sizeof(sa_mut_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "track output struct_size is too small");
    }
    if (view->data == nullptr || view->stride_bytes != sizeof(double)
        || view->element_type != SA_ELEMENT_TYPE_F64
        || view->memory_space != SA_MEMORY_SPACE_HOST || view->device_id != -1
        || view->flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, label);
    }
    if (view->length < expected_length) {
        return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "track output buffer is too small");
    }
    const auto extent = expected_length * sizeof(double);
    const auto address = reinterpret_cast<std::uintptr_t>(view->data);
    if (address % alignof(double) != 0U
        || (extent > 0U && address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U))) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "track output pointer extent is invalid");
    }
    return SA_OK;
}

[[nodiscard]] bool ranges_overlap(
    const void* const left,
    const std::uint64_t left_extent,
    const void* const right,
    const std::uint64_t right_extent) noexcept {
    const auto left_start = reinterpret_cast<std::uintptr_t>(left);
    const auto right_start = reinterpret_cast<std::uintptr_t>(right);
    return left_start <= right_start
        ? right_start - left_start < static_cast<std::uintptr_t>(left_extent)
        : left_start - right_start < static_cast<std::uintptr_t>(right_extent);
}

[[nodiscard]] sa_status_code_v1 validate_nonlinear_input(
    const sa_buffer_view_v1* const view,
    const std::uint64_t expected_length,
    const std::string_view label,
    sa_error_buffer_v1* const error) {
    if (!pointer_is_aligned(view)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static input descriptor is null or misaligned");
    }
    if (view->abi_version != SA_ABI_V1_3) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear static input ABI is not v1.3");
    }
    if (view->struct_size < sizeof(sa_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear static input struct_size is too small");
    }
    if (view->data == nullptr || view->stride_bytes != sizeof(double)
        || view->element_type != SA_ELEMENT_TYPE_F64
        || view->memory_space != SA_MEMORY_SPACE_HOST || view->device_id != -1
        || view->flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, label);
    }
    if (view->length < expected_length) {
        return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "nonlinear static input buffer is too small");
    }
    const auto extent = expected_length * sizeof(double);
    const auto address = reinterpret_cast<std::uintptr_t>(view->data);
    if (address % alignof(double) != 0U
        || address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static input pointer extent is invalid");
    }
    return SA_OK;
}

[[nodiscard]] sa_status_code_v1 validate_nonlinear_output(
    const sa_mut_buffer_view_v1* const view,
    const std::uint64_t expected_length,
    sa_error_buffer_v1* const error) {
    if (!pointer_is_aligned(view)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output descriptor is null or misaligned");
    }
    if (view->abi_version != SA_ABI_V1_3) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear static output ABI is not v1.3");
    }
    if (view->struct_size < sizeof(sa_mut_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear static output struct_size is too small");
    }
    if (view->data == nullptr || view->stride_bytes != sizeof(double)
        || view->element_type != SA_ELEMENT_TYPE_F64
        || view->memory_space != SA_MEMORY_SPACE_HOST || view->device_id != -1
        || view->flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output metadata is invalid");
    }
    if (view->length < expected_length) {
        return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "nonlinear static output buffer is too small");
    }
    const auto extent = expected_length * sizeof(double);
    const auto address = reinterpret_cast<std::uintptr_t>(view->data);
    if (address % alignof(double) != 0U
        || address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output pointer extent is invalid");
    }
    return SA_OK;
}

[[nodiscard]] sa_status_code_v1 track_point_load_boundary(
    const sa_track_point_load_config_v1* const config,
    const sa_mut_buffer_view_v1* const displacement_m,
    const sa_mut_buffer_view_v1* const rotation_rad,
    sa_track_point_load_result_v1* const result,
    sa_error_buffer_v1* const error) noexcept {
    return contain_boundary(
        error,
        [config, displacement_m, rotation_rad, result, error]() -> sa_status_code_v1 {
        if (!pointer_is_aligned(config) || !pointer_is_aligned(result)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track config or result is null or misaligned");
        }
        if (config->abi_version != SA_ABI_V1_2 || result->abi_version != SA_ABI_V1_2) {
            return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "track descriptors require ABI v1.2");
        }
        if (config->struct_size < sizeof(sa_track_point_load_config_v1)
            || result->struct_size < sizeof(sa_track_point_load_result_v1)) {
            return report_error(error, SA_ERR_STRUCT_SIZE, "track descriptor struct_size is too small");
        }
        if (config->flags != 0U || config->reserved_u32 != 0U
            || std::any_of(std::begin(config->reserved), std::end(config->reserved), [](const auto value) {
                   return value != 0U;
               })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track config reserved fields are not zero");
        }
        const std::array scalar_values {
            config->length_m,
            config->bending_stiffness_n_m2,
            config->shear_stiffness_n,
            config->winkler_k_n_per_m2,
            config->pasternak_g_n,
            config->tolerance,
            config->point_force_n,
            config->point_position_m,
        };
        if (std::any_of(scalar_values.begin(), scalar_values.end(), [](const auto value) {
                return !std::isfinite(value);
            })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track config contains a non-finite scalar");
        }
        if (config->length_m <= 0.0 || config->node_count < 7U
            || config->node_count > SA_TRACK_POINT_LOAD_MAX_NODE_COUNT
            || config->bending_stiffness_n_m2 <= 0.0 || config->shear_stiffness_n <= 0.0
            || config->winkler_k_n_per_m2 < 0.0 || config->pasternak_g_n < 0.0
            || config->tolerance <= 0.0 || config->cg_max_iter == 0U
            || config->support_type > SA_TRACK_SUPPORT_FIXED
            || config->theory > SA_TRACK_THEORY_TIMOSHENKO_REDUCED) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track config value is outside the v1.2 domain");
        }

        const auto expected_length = static_cast<std::uint64_t>(config->node_count);
        auto status = validate_track_output(
            displacement_m,
            expected_length,
            "track displacement output metadata is invalid",
            error);
        if (status != SA_OK) {
            return status;
        }
        status = validate_track_output(
            rotation_rad,
            expected_length,
            "track rotation output metadata is invalid",
            error);
        if (status != SA_OK) {
            return status;
        }
        const auto extent = expected_length * sizeof(double);
        if (ranges_overlap(displacement_m->data, extent, rotation_rad->data, extent)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track output buffers overlap");
        }
        if (ranges_overlap(displacement_m->data, extent, result, sizeof(*result))
            || ranges_overlap(rotation_rad->data, extent, result, sizeof(*result))) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track output overlaps result descriptor");
        }
        const bool overlaps_input_descriptor =
            ranges_overlap(displacement_m->data, extent, config, sizeof(*config))
            || ranges_overlap(rotation_rad->data, extent, config, sizeof(*config))
            || ranges_overlap(displacement_m->data, extent, displacement_m, sizeof(*displacement_m))
            || ranges_overlap(rotation_rad->data, extent, displacement_m, sizeof(*displacement_m))
            || ranges_overlap(displacement_m->data, extent, rotation_rad, sizeof(*rotation_rad))
            || ranges_overlap(rotation_rad->data, extent, rotation_rad, sizeof(*rotation_rad));
        if (overlaps_input_descriptor) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "track output overlaps an input descriptor");
        }

        const structural::solver_cpu::TrackPointLoadConfig native_config {
            config->length_m,
            config->node_count,
            config->support_type == SA_TRACK_SUPPORT_PINNED
                ? structural::solver_cpu::TrackSupportType::pinned
                : structural::solver_cpu::TrackSupportType::fixed,
            config->theory == SA_TRACK_THEORY_EULER
                ? structural::solver_cpu::TrackTheory::euler
                : structural::solver_cpu::TrackTheory::timoshenko_reduced,
            config->bending_stiffness_n_m2,
            config->shear_stiffness_n,
            config->winkler_k_n_per_m2,
            config->pasternak_g_n,
            config->tolerance,
            config->cg_max_iter,
            config->point_force_n,
            config->point_position_m,
        };
        const auto native_result = structural::solver_cpu::solve_track_point_load(native_config);
        if (!native_result.converged) {
            return report_error(error, SA_ERR_NONCONVERGENCE, "track CPU conjugate gradient did not converge");
        }
        if (native_result.displacement_m.size() != expected_length
            || native_result.rotation_rad.size() != expected_length) {
            return report_error(error, SA_ERR_INTERNAL, "track CPU result length invariant failed");
        }

        std::memcpy(displacement_m->data, native_result.displacement_m.data(), extent);
        std::memcpy(rotation_rad->data, native_result.rotation_rad.data(), extent);
        *result = {
            SA_ABI_V1_2,
            static_cast<std::uint32_t>(sizeof(sa_track_point_load_result_v1)),
            1U,
            native_result.iterations,
            native_result.residual_inf,
            native_result.max_abs_displacement_m,
            native_result.mid_displacement_m,
            expected_length,
            SA_EXECUTION_BACKEND_CPU,
            0U,
            0U,
        };
        return SA_OK;
        });
}

[[nodiscard]] sa_status_code_v1 nonlinear_static_boundary(
    const sa_nonlinear_static_config_v1* const config,
    const sa_buffer_view_v1* const story_stiffness_n_per_m,
    const sa_buffer_view_v1* const story_height_m,
    const sa_buffer_view_v1* const story_axial_n,
    const sa_buffer_view_v1* const story_yield_drift_m,
    const sa_buffer_view_v1* const floor_load_n,
    const sa_mut_buffer_view_v1* const displacement_m,
    sa_nonlinear_static_result_v1* const result,
    sa_error_buffer_v1* const error) noexcept {
    return contain_boundary(
        error,
        [config,
         story_stiffness_n_per_m,
         story_height_m,
         story_axial_n,
         story_yield_drift_m,
         floor_load_n,
         displacement_m,
         result,
         error]() -> sa_status_code_v1 {
        if (!pointer_is_aligned(config) || !pointer_is_aligned(result)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static config or result is null or misaligned");
        }
        if (config->abi_version != SA_ABI_V1_3 || result->abi_version != SA_ABI_V1_3) {
            return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear static descriptors require ABI v1.3");
        }
        if (config->struct_size < sizeof(sa_nonlinear_static_config_v1)
            || result->struct_size < sizeof(sa_nonlinear_static_result_v1)) {
            return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear static descriptor struct_size is too small");
        }
        if (config->flags != 0U || config->reserved_u32 != 0U
            || std::any_of(std::begin(config->reserved), std::end(config->reserved), [](const auto value) {
                   return value != 0U;
               })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static config reserved fields are not zero");
        }
        const std::array scalar_values {
            config->tolerance,
            config->hardening_ratio,
            config->line_search_decay,
            config->line_search_min,
            config->pdelta_factor,
        };
        if (std::any_of(scalar_values.begin(), scalar_values.end(), [](const auto value) {
                return !std::isfinite(value);
            })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static config contains a non-finite scalar");
        }
        if (config->story_count == 0U
            || config->story_count > SA_NONLINEAR_STATIC_MAX_STORY_COUNT
            || config->max_iter == 0U || config->tolerance <= 0.0
            || config->hardening_ratio < 0.0 || config->hardening_ratio > 1.0
            || config->line_search_decay <= 0.0 || config->line_search_decay >= 1.0
            || config->line_search_min <= 0.0 || config->line_search_min > 1.0
            || config->pdelta_factor < 0.0) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static config value is outside the v1.3 domain");
        }

        const auto expected_length = static_cast<std::uint64_t>(config->story_count);
        const std::array input_views {
            story_stiffness_n_per_m,
            story_height_m,
            story_axial_n,
            story_yield_drift_m,
            floor_load_n,
        };
        const std::array input_labels {
            std::string_view {"nonlinear static stiffness input metadata is invalid"},
            std::string_view {"nonlinear static height input metadata is invalid"},
            std::string_view {"nonlinear static axial input metadata is invalid"},
            std::string_view {"nonlinear static yield-drift input metadata is invalid"},
            std::string_view {"nonlinear static floor-load input metadata is invalid"},
        };
        for (std::size_t index = 0U; index < input_views.size(); ++index) {
            const auto status = validate_nonlinear_input(
                input_views[index], expected_length, input_labels[index], error);
            if (status != SA_OK) {
                return status;
            }
        }
        const auto output_status =
            validate_nonlinear_output(displacement_m, expected_length, error);
        if (output_status != SA_OK) {
            return output_status;
        }

        const auto extent = expected_length * sizeof(double);
        for (const auto* const input_view : input_views) {
            if (ranges_overlap(displacement_m->data, extent, input_view->data, extent)) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output overlaps input data");
            }
            if (ranges_overlap(displacement_m->data, extent, input_view, sizeof(*input_view))) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output overlaps an input descriptor");
            }
            if (ranges_overlap(result, sizeof(*result), input_view->data, extent)
                || ranges_overlap(result, sizeof(*result), input_view, sizeof(*input_view))) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static result overlaps input storage");
            }
        }
        if (ranges_overlap(displacement_m->data, extent, config, sizeof(*config))
            || ranges_overlap(displacement_m->data, extent, displacement_m, sizeof(*displacement_m))
            || ranges_overlap(displacement_m->data, extent, result, sizeof(*result))
            || ranges_overlap(result, sizeof(*result), config, sizeof(*config))
            || ranges_overlap(result, sizeof(*result), displacement_m, sizeof(*displacement_m))) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static output descriptors overlap");
        }

        const auto count = static_cast<std::size_t>(expected_length);
        const auto values = [count](const sa_buffer_view_v1* const view) {
            return std::span<const double> {
                static_cast<const double*>(view->data),
                count,
            };
        };
        const auto stiffness = values(story_stiffness_n_per_m);
        const auto height = values(story_height_m);
        const auto axial = values(story_axial_n);
        const auto yield_drift = values(story_yield_drift_m);
        const auto load = values(floor_load_n);
        const auto all_finite = [](const std::span<const double> input) {
            return std::all_of(input.begin(), input.end(), [](const auto value) {
                return std::isfinite(value);
            });
        };
        if (!all_finite(stiffness) || !all_finite(height) || !all_finite(axial)
            || !all_finite(yield_drift) || !all_finite(load)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static inputs contain a non-finite value");
        }
        if (std::any_of(stiffness.begin(), stiffness.end(), [](const auto value) {
                return value <= 0.0;
            })
            || std::any_of(height.begin(), height.end(), [](const auto value) {
                   return value <= 0.0;
               })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear static stiffness and height must be positive");
        }

        const structural::solver_cpu::NonlinearStaticConfig native_config {
            config->story_count,
            config->tolerance,
            config->max_iter,
            config->hardening_ratio,
            config->line_search_decay,
            config->line_search_min,
            config->pdelta_factor,
        };
        const structural::solver_cpu::NonlinearStaticInputs native_inputs {
            stiffness,
            height,
            axial,
            yield_drift,
            load,
        };
        const auto native_result =
            structural::solver_cpu::solve_nonlinear_static(native_config, native_inputs);
        if (!native_result.converged) {
            return report_error(error, SA_ERR_NONCONVERGENCE, "nonlinear static CPU Newton solve did not converge");
        }
        if (native_result.displacement_m.size() != expected_length) {
            return report_error(error, SA_ERR_INTERNAL, "nonlinear static CPU result length invariant failed");
        }

        std::memcpy(displacement_m->data, native_result.displacement_m.data(), extent);
        *result = {
            SA_ABI_V1_3,
            static_cast<std::uint32_t>(sizeof(sa_nonlinear_static_result_v1)),
            1U,
            native_result.iterations,
            native_result.residual_inf,
            native_result.residual_l2,
            native_result.max_abs_displacement_m,
            native_result.top_displacement_m,
            native_result.base_shear_kn,
            native_result.plastic_story_count,
            native_result.line_search_backtracks,
            expected_length,
            SA_EXECUTION_BACKEND_CPU,
            0U,
            0U,
        };
        return SA_OK;
        });
}

[[nodiscard]] sa_status_code_v1 validate_ndtha_input_view(
    const sa_buffer_view_v1& view,
    const std::uint64_t expected_length,
    const std::string_view label,
    sa_error_buffer_v1* const error) {
    if (view.abi_version != SA_ABI_V1_4) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear NDTHA input ABI is not v1.4");
    }
    if (view.struct_size < sizeof(sa_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear NDTHA input struct_size is too small");
    }
    if (view.data == nullptr || view.stride_bytes != sizeof(double)
        || view.element_type != SA_ELEMENT_TYPE_F64
        || view.memory_space != SA_MEMORY_SPACE_HOST || view.device_id != -1
        || view.flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, label);
    }
    if (view.length < expected_length) {
        return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "nonlinear NDTHA input buffer is too small");
    }
    const auto extent = expected_length * sizeof(double);
    const auto address = reinterpret_cast<std::uintptr_t>(view.data);
    if (address % alignof(double) != 0U
        || address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA input pointer extent is invalid");
    }
    return SA_OK;
}

[[nodiscard]] sa_status_code_v1 validate_ndtha_output_view(
    const sa_mut_buffer_view_v1& view,
    const std::uint64_t expected_length,
    const std::uint32_t expected_type,
    const std::uint64_t expected_width,
    const std::string_view label,
    sa_error_buffer_v1* const error) {
    if (view.abi_version != SA_ABI_V1_4) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear NDTHA output ABI is not v1.4");
    }
    if (view.struct_size < sizeof(sa_mut_buffer_view_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear NDTHA output struct_size is too small");
    }
    if (view.data == nullptr || view.stride_bytes != expected_width
        || view.element_type != expected_type
        || view.memory_space != SA_MEMORY_SPACE_HOST || view.device_id != -1
        || view.flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, label);
    }
    if (view.length < expected_length) {
        return report_error(error, SA_ERR_BUFFER_TOO_SMALL, "nonlinear NDTHA output buffer is too small");
    }
    const auto extent = expected_length * expected_width;
    const auto address = reinterpret_cast<std::uintptr_t>(view.data);
    if (address % expected_width != 0U
        || address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA output pointer extent is invalid");
    }
    return SA_OK;
}

struct MemoryRegion {
    const void* data;
    std::uint64_t extent;
};

[[nodiscard]] sa_status_code_v1 nonlinear_ndtha_boundary(
    const sa_nonlinear_ndtha_config_v1* const config,
    const sa_nonlinear_ndtha_inputs_v1* const inputs,
    const sa_nonlinear_ndtha_outputs_v1* const outputs,
    sa_nonlinear_ndtha_result_v1* const result,
    sa_error_buffer_v1* const error) noexcept {
    return contain_boundary(error, [config, inputs, outputs, result, error]() -> sa_status_code_v1 {
        if (!pointer_is_aligned(config) || !pointer_is_aligned(inputs)
            || !pointer_is_aligned(outputs) || !pointer_is_aligned(result)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA descriptor is null or misaligned");
        }
        if (config->abi_version != SA_ABI_V1_4 || inputs->abi_version != SA_ABI_V1_4
            || outputs->abi_version != SA_ABI_V1_4 || result->abi_version != SA_ABI_V1_4) {
            return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "nonlinear NDTHA descriptors require ABI v1.4");
        }
        if (config->struct_size < sizeof(sa_nonlinear_ndtha_config_v1)
            || inputs->struct_size < sizeof(sa_nonlinear_ndtha_inputs_v1)
            || outputs->struct_size < sizeof(sa_nonlinear_ndtha_outputs_v1)
            || result->struct_size < sizeof(sa_nonlinear_ndtha_result_v1)) {
            return report_error(error, SA_ERR_STRUCT_SIZE, "nonlinear NDTHA descriptor struct_size is too small");
        }
        const bool reserved_nonzero = config->reserved_iteration_u32 != 0U
            || config->reserved_newton_u32 != 0U || config->flags != 0U
            || config->reserved_u32 != 0U
            || std::any_of(std::begin(config->reserved), std::end(config->reserved), [](const auto value) {
                   return value != 0U;
               })
            || std::any_of(std::begin(inputs->reserved), std::end(inputs->reserved), [](const auto value) {
                   return value != 0U;
               })
            || std::any_of(std::begin(outputs->reserved), std::end(outputs->reserved), [](const auto value) {
                   return value != 0U;
               });
        if (reserved_nonzero) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA reserved fields are not zero");
        }

        const std::array scalar_values {
            config->dt_s,
            config->newmark_beta,
            config->newmark_gamma,
            config->tolerance,
            config->adaptive_load_decay,
            config->damping_force_cap_ratio,
            config->line_search_decay,
            config->line_search_min,
            config->hardening_ratio,
            config->pdelta_factor,
            config->collapse_drift_threshold_pct,
        };
        if (std::any_of(scalar_values.begin(), scalar_values.end(), [](const auto value) {
                return !std::isfinite(value);
            })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA config contains a non-finite scalar");
        }
        if (config->story_count == 0U
            || config->story_count > SA_NONLINEAR_NDTHA_MAX_STORY_COUNT
            || config->step_count == 0U
            || config->step_count > SA_NONLINEAR_NDTHA_MAX_STEP_COUNT
            || config->dt_s <= 0.0 || config->newmark_beta <= 0.0
            || config->newmark_gamma <= 0.0 || config->tolerance <= 0.0
            || config->max_step_iterations == 0U || config->newton_max_iter == 0U
            || config->adaptive_load_decay <= 0.0 || config->adaptive_load_decay > 1.0
            || config->damping_force_cap_ratio <= 0.0
            || config->line_search_decay <= 0.0 || config->line_search_decay >= 1.0
            || config->line_search_min <= 0.0 || config->line_search_min > 1.0
            || config->hardening_ratio < 0.0 || config->hardening_ratio > 1.0
            || config->pdelta_factor < 0.0 || config->collapse_drift_threshold_pct <= 0.0) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA config value is outside the v1.4 domain");
        }

        const auto story_count = static_cast<std::uint64_t>(config->story_count);
        const auto step_count = static_cast<std::uint64_t>(config->step_count);
        const std::array input_views {
            &inputs->story_stiffness_n_per_m,
            &inputs->story_height_m,
            &inputs->story_axial_n,
            &inputs->story_yield_drift_m,
            &inputs->story_mass_kg,
            &inputs->story_damping_n_s_per_m,
            &inputs->floor_load_base_n,
            &inputs->acceleration_g,
        };
        const std::array input_lengths {
            story_count,
            story_count,
            story_count,
            story_count,
            story_count,
            story_count,
            story_count,
            step_count,
        };
        const std::array input_labels {
            std::string_view {"nonlinear NDTHA stiffness input metadata is invalid"},
            std::string_view {"nonlinear NDTHA height input metadata is invalid"},
            std::string_view {"nonlinear NDTHA axial input metadata is invalid"},
            std::string_view {"nonlinear NDTHA yield-drift input metadata is invalid"},
            std::string_view {"nonlinear NDTHA mass input metadata is invalid"},
            std::string_view {"nonlinear NDTHA damping input metadata is invalid"},
            std::string_view {"nonlinear NDTHA base-load input metadata is invalid"},
            std::string_view {"nonlinear NDTHA acceleration input metadata is invalid"},
        };
        for (std::size_t index = 0U; index < input_views.size(); ++index) {
            const auto status = validate_ndtha_input_view(
                *input_views[index], input_lengths[index], input_labels[index], error);
            if (status != SA_OK) {
                return status;
            }
        }

        const std::array output_views {
            &outputs->top_displacement_m,
            &outputs->drift_ratio_pct,
            &outputs->base_shear_kn,
            &outputs->core_drift_pct,
            &outputs->core_shear_kn,
            &outputs->step_converged,
            &outputs->step_iterations,
            &outputs->step_plastic_story_count,
            &outputs->step_residual_inf,
            &outputs->story_drift_envelope_pct,
            &outputs->final_story_drift_pct,
        };
        const std::array output_lengths {
            step_count,
            step_count,
            step_count,
            step_count,
            step_count,
            step_count,
            step_count,
            step_count,
            step_count,
            story_count,
            story_count,
        };
        const std::array output_types {
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_U8},
            std::uint32_t {SA_ELEMENT_TYPE_U32},
            std::uint32_t {SA_ELEMENT_TYPE_U32},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
            std::uint32_t {SA_ELEMENT_TYPE_F64},
        };
        const std::array output_widths {
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(std::uint8_t)},
            std::uint64_t {sizeof(std::uint32_t)},
            std::uint64_t {sizeof(std::uint32_t)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
            std::uint64_t {sizeof(double)},
        };
        for (std::size_t index = 0U; index < output_views.size(); ++index) {
            const auto status = validate_ndtha_output_view(
                *output_views[index],
                output_lengths[index],
                output_types[index],
                output_widths[index],
                "nonlinear NDTHA output metadata is invalid",
                error);
            if (status != SA_OK) {
                return status;
            }
        }

        const std::array descriptor_regions {
            MemoryRegion {config, sizeof(*config)},
            MemoryRegion {inputs, sizeof(*inputs)},
            MemoryRegion {outputs, sizeof(*outputs)},
            MemoryRegion {result, sizeof(*result)},
        };
        for (std::size_t left = 0U; left < descriptor_regions.size(); ++left) {
            for (std::size_t right = left + 1U; right < descriptor_regions.size(); ++right) {
                if (ranges_overlap(
                        descriptor_regions[left].data,
                        descriptor_regions[left].extent,
                        descriptor_regions[right].data,
                        descriptor_regions[right].extent)) {
                    return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA top-level descriptors overlap");
                }
            }
        }

        std::array<MemoryRegion, 8> input_regions {};
        for (std::size_t index = 0U; index < input_views.size(); ++index) {
            input_regions[index] = {
                input_views[index]->data,
                input_lengths[index] * sizeof(double),
            };
            if (ranges_overlap(result, sizeof(*result), input_regions[index].data, input_regions[index].extent)) {
                return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA result overlaps input data");
            }
        }
        std::array<MemoryRegion, 11> output_regions {};
        for (std::size_t index = 0U; index < output_views.size(); ++index) {
            output_regions[index] = {
                output_views[index]->data,
                output_lengths[index] * output_widths[index],
            };
            for (const auto& descriptor : descriptor_regions) {
                if (ranges_overlap(
                        output_regions[index].data,
                        output_regions[index].extent,
                        descriptor.data,
                        descriptor.extent)) {
                    return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA output overlaps descriptor storage");
                }
            }
            for (const auto& input_region : input_regions) {
                if (ranges_overlap(
                        output_regions[index].data,
                        output_regions[index].extent,
                        input_region.data,
                        input_region.extent)) {
                    return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA output overlaps input data");
                }
            }
        }
        for (std::size_t left = 0U; left < output_regions.size(); ++left) {
            for (std::size_t right = left + 1U; right < output_regions.size(); ++right) {
                if (ranges_overlap(
                        output_regions[left].data,
                        output_regions[left].extent,
                        output_regions[right].data,
                        output_regions[right].extent)) {
                    return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA output buffers overlap");
                }
            }
        }

        const auto story_size = static_cast<std::size_t>(story_count);
        const auto step_size = static_cast<std::size_t>(step_count);
        const auto story_values = [story_size](const sa_buffer_view_v1& view) {
            return std::span<const double> {static_cast<const double*>(view.data), story_size};
        };
        const auto step_values = [step_size](const sa_buffer_view_v1& view) {
            return std::span<const double> {static_cast<const double*>(view.data), step_size};
        };
        const auto stiffness = story_values(inputs->story_stiffness_n_per_m);
        const auto height = story_values(inputs->story_height_m);
        const auto axial = story_values(inputs->story_axial_n);
        const auto yield_drift = story_values(inputs->story_yield_drift_m);
        const auto mass = story_values(inputs->story_mass_kg);
        const auto damping = story_values(inputs->story_damping_n_s_per_m);
        const auto floor_load = story_values(inputs->floor_load_base_n);
        const auto acceleration = step_values(inputs->acceleration_g);
        const auto all_finite = [](const std::span<const double> values) {
            return std::all_of(values.begin(), values.end(), [](const auto value) {
                return std::isfinite(value);
            });
        };
        if (!all_finite(stiffness) || !all_finite(height) || !all_finite(axial)
            || !all_finite(yield_drift) || !all_finite(mass) || !all_finite(damping)
            || !all_finite(floor_load) || !all_finite(acceleration)) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA inputs contain a non-finite value");
        }
        if (std::any_of(stiffness.begin(), stiffness.end(), [](const auto value) {
                return value <= 0.0;
            })
            || std::any_of(height.begin(), height.end(), [](const auto value) {
                   return value <= 0.0;
               })
            || std::any_of(mass.begin(), mass.end(), [](const auto value) {
                   return value <= 0.0;
               })
            || std::any_of(damping.begin(), damping.end(), [](const auto value) {
                   return value < 0.0;
               })) {
            return report_error(error, SA_ERR_INVALID_ARGUMENT, "nonlinear NDTHA stiffness, height, mass or damping is outside the physical domain");
        }

        const structural::solver_cpu::NonlinearNdthaConfig native_config {
            config->story_count,
            config->step_count,
            config->dt_s,
            config->newmark_beta,
            config->newmark_gamma,
            config->tolerance,
            config->max_step_iterations,
            config->adaptive_load_decay,
            config->damping_force_cap_ratio,
            config->newton_max_iter,
            config->line_search_decay,
            config->line_search_min,
            config->hardening_ratio,
            config->pdelta_factor,
            config->collapse_drift_threshold_pct,
        };
        const structural::solver_cpu::NonlinearNdthaInputs native_inputs {
            stiffness,
            height,
            axial,
            yield_drift,
            mass,
            damping,
            floor_load,
            acceleration,
        };
        const auto native_result =
            structural::solver_cpu::solve_nonlinear_ndtha(native_config, native_inputs);
        if (!native_result.converged_all_steps && !native_result.collapsed) {
            return report_error(error, SA_ERR_NONCONVERGENCE, "nonlinear NDTHA CPU Newmark/Newton solve did not converge");
        }

        const auto& response = native_result.response;
        const bool response_sizes_valid = response.top_displacement_m.size() == step_size
            && response.drift_ratio_pct.size() == step_size
            && response.base_shear_kn.size() == step_size
            && response.core_drift_pct.size() == step_size
            && response.core_shear_kn.size() == step_size
            && response.step_converged.size() == step_size
            && response.step_iterations.size() == step_size
            && response.step_plastic_story_count.size() == step_size
            && response.step_residual_inf.size() == step_size
            && response.story_drift_envelope_pct.size() == story_size
            && response.final_story_drift_pct.size() == story_size;
        const auto finite_vector = [](const std::vector<double>& values) {
            return std::all_of(values.begin(), values.end(), [](const auto value) {
                return std::isfinite(value);
            });
        };
        const bool result_finite = std::isfinite(native_result.collapse_time_s)
            && std::isfinite(native_result.collapse_drift_ratio_pct)
            && std::isfinite(native_result.collapse_top_displacement_m)
            && std::isfinite(native_result.max_drift_ratio_pct)
            && std::isfinite(native_result.avg_step_iterations)
            && std::isfinite(native_result.residual_top_displacement_m)
            && std::isfinite(native_result.residual_drift_ratio_pct)
            && finite_vector(response.top_displacement_m)
            && finite_vector(response.drift_ratio_pct)
            && finite_vector(response.base_shear_kn)
            && finite_vector(response.core_drift_pct)
            && finite_vector(response.core_shear_kn)
            && finite_vector(response.step_residual_inf)
            && finite_vector(response.story_drift_envelope_pct)
            && finite_vector(response.final_story_drift_pct);
        if (!response_sizes_valid || !result_finite) {
            return report_error(error, SA_ERR_INTERNAL, "nonlinear NDTHA CPU result invariant failed");
        }

        std::memcpy(outputs->top_displacement_m.data, response.top_displacement_m.data(), step_count * sizeof(double));
        std::memcpy(outputs->drift_ratio_pct.data, response.drift_ratio_pct.data(), step_count * sizeof(double));
        std::memcpy(outputs->base_shear_kn.data, response.base_shear_kn.data(), step_count * sizeof(double));
        std::memcpy(outputs->core_drift_pct.data, response.core_drift_pct.data(), step_count * sizeof(double));
        std::memcpy(outputs->core_shear_kn.data, response.core_shear_kn.data(), step_count * sizeof(double));
        std::memcpy(outputs->step_converged.data, response.step_converged.data(), step_count * sizeof(std::uint8_t));
        std::memcpy(outputs->step_iterations.data, response.step_iterations.data(), step_count * sizeof(std::uint32_t));
        std::memcpy(outputs->step_plastic_story_count.data, response.step_plastic_story_count.data(), step_count * sizeof(std::uint32_t));
        std::memcpy(outputs->step_residual_inf.data, response.step_residual_inf.data(), step_count * sizeof(double));
        std::memcpy(outputs->story_drift_envelope_pct.data, response.story_drift_envelope_pct.data(), story_count * sizeof(double));
        std::memcpy(outputs->final_story_drift_pct.data, response.final_story_drift_pct.data(), story_count * sizeof(double));
        *result = {
            SA_ABI_V1_4,
            static_cast<std::uint32_t>(sizeof(sa_nonlinear_ndtha_result_v1)),
            native_result.converged_all_steps ? 1U : 0U,
            native_result.collapsed ? 1U : 0U,
            native_result.collapse_step,
            native_result.step_count_completed,
            native_result.collapse_time_s,
            native_result.collapse_drift_ratio_pct,
            native_result.collapse_top_displacement_m,
            native_result.max_drift_ratio_pct,
            native_result.avg_step_iterations,
            native_result.residual_top_displacement_m,
            native_result.residual_drift_ratio_pct,
            native_result.max_plastic_story_count,
            native_result.total_line_search_backtracks,
            story_count,
            step_count,
            SA_EXECUTION_BACKEND_CPU,
            0U,
            {0U, 0U},
        };
        return SA_OK;
    });
}

[[nodiscard]] sa_status_code_v1 get_api_impl(
    const sa_api_request_v1* const request,
    sa_api_v1* const out_api,
    sa_error_buffer_v1* const error) {
    if (request == nullptr || out_api == nullptr) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "API request or output is null");
    }
    if (!supported_version(request->abi_version) || !supported_version(out_api->abi_version)
        || request->abi_version != out_api->abi_version) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "requested API version is unsupported");
    }
    const auto api_min_size = request->abi_version == SA_ABI_V1_0
        ? SA_API_V1_0_MIN_SIZE
        : (request->abi_version == SA_ABI_V1_1
                ? SA_API_V1_1_MIN_SIZE
                : (request->abi_version == SA_ABI_V1_2
                        ? SA_API_V1_2_MIN_SIZE
                        : (request->abi_version == SA_ABI_V1_3
                                ? SA_API_V1_3_MIN_SIZE
                                : SA_API_V1_4_MIN_SIZE)));
    if (request->struct_size < SA_API_REQUEST_V1_MIN_SIZE || out_api->struct_size < api_min_size) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "API descriptor struct_size is too small");
    }
    if (request->flags != 0U) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "API request flags are not zero");
    }
    if (request->struct_size > SA_API_REQUEST_V1_MIN_SIZE
        && request->struct_size < sizeof(sa_api_request_v1)) {
        return report_error(error, SA_ERR_STRUCT_SIZE, "API request has a partial reserved tail");
    }
    if (request->struct_size >= sizeof(sa_api_request_v1)
        && std::any_of(std::begin(request->reserved), std::end(request->reserved), [](const auto value) {
               return value != 0U;
           })) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "API request reserved fields are not zero");
    }

    const bool model_ir_enabled = request->abi_version >= SA_ABI_V1_1;
    const bool track_enabled = request->abi_version >= SA_ABI_V1_2;
    const bool nonlinear_static_enabled = request->abi_version >= SA_ABI_V1_3;
    const bool nonlinear_ndtha_enabled = request->abi_version >= SA_ABI_V1_4;
    const sa_api_v1 table {
        request->abi_version,
        static_cast<std::uint32_t>(sizeof(sa_api_v1)),
        SA_CAPABILITY_BUFFER_VALIDATION
            | (model_ir_enabled
                    ? SA_CAPABILITY_MODEL_IR_V2_TYPED | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT
                    : UINT64_C(0))
            | (track_enabled ? SA_CAPABILITY_TRACK_POINT_LOAD_CPU : UINT64_C(0))
            | (nonlinear_static_enabled ? SA_CAPABILITY_NONLINEAR_STATIC_CPU : UINT64_C(0))
            | (nonlinear_ndtha_enabled ? SA_CAPABILITY_NONLINEAR_NDTHA_CPU : UINT64_C(0)),
        &validate_buffer_view_boundary,
        model_ir_enabled ? &model_ir_create_boundary : nullptr,
        model_ir_enabled ? &model_ir_destroy_boundary : nullptr,
        model_ir_enabled ? &model_ir_validation_report_size_boundary : nullptr,
        model_ir_enabled ? &model_ir_validation_report_write_boundary : nullptr,
        model_ir_enabled ? &model_ir_snapshot_size_boundary : nullptr,
        model_ir_enabled ? &model_ir_snapshot_write_boundary : nullptr,
        track_enabled ? &track_point_load_boundary : nullptr,
        nonlinear_static_enabled ? &nonlinear_static_boundary : nullptr,
        nonlinear_ndtha_enabled ? &nonlinear_ndtha_boundary : nullptr,
        {nullptr, nullptr, nullptr, nullptr},
    };
    const auto copied = std::min<std::size_t>(out_api->struct_size, sizeof(table));
    std::memcpy(out_api, &table, copied);
    return SA_OK;
}

} // namespace

extern "C" SA_API_V1_EXPORT sa_status_code_v1 sa_get_api_v1(
    const sa_api_request_v1* const request,
    sa_api_v1* const out_api,
    sa_error_buffer_v1* const error) {
    const auto error_status = prepare_error(error);
    if (error_status != SA_OK) {
        return error_status;
    }
    try {
        return get_api_impl(request, out_api, error);
    } catch (const std::bad_alloc&) {
        return report_error(error, SA_ERR_INTERNAL, "native allocation failed");
    } catch (const std::exception&) {
        return report_error(error, SA_ERR_INTERNAL, "native exception was contained");
    } catch (...) {
        return report_error(error, SA_ERR_INTERNAL, "unknown native exception was contained");
    }
}
