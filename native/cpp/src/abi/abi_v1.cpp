#include "structural/abi_v1.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <new>
#include <string_view>
#include <type_traits>

static_assert(sizeof(void*) == 8U);
static_assert(sizeof(double) == 8U);
static_assert(std::numeric_limits<double>::is_iec559);
static_assert(std::is_standard_layout_v<sa_header_v1>);
static_assert(sizeof(sa_header_v1) == 8U);
static_assert(sizeof(sa_buffer_view_v1) == 48U);
static_assert(offsetof(sa_buffer_view_v1, data) == 8U);
static_assert(offsetof(sa_buffer_view_v1, flags) == 44U);
static_assert(sizeof(sa_error_buffer_v1) == 32U);
static_assert(offsetof(sa_error_buffer_v1, required) == 24U);
static_assert(sizeof(sa_api_request_v1) == 40U);
static_assert(sizeof(sa_api_v1) == 128U);
static_assert(offsetof(sa_api_v1, validate_buffer_view) == 16U);
static_assert(offsetof(sa_api_v1, reserved) == 24U);

namespace {

constexpr std::uint32_t kCurrentAbi = SA_ABI_V1_0;

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

[[nodiscard]] sa_status_code_v1 get_api_impl(
    const sa_api_request_v1* const request,
    sa_api_v1* const out_api,
    sa_error_buffer_v1* const error) {
    if (request == nullptr || out_api == nullptr) {
        return report_error(error, SA_ERR_INVALID_ARGUMENT, "API request or output is null");
    }
    if (!supported_version(request->abi_version) || !supported_version(out_api->abi_version)) {
        return report_error(error, SA_ERR_ABI_VERSION_MISMATCH, "requested API version is unsupported");
    }
    if (request->struct_size < SA_API_REQUEST_V1_MIN_SIZE
        || out_api->struct_size < SA_API_V1_MIN_SIZE) {
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

    const sa_api_v1 table {
        kCurrentAbi,
        static_cast<std::uint32_t>(sizeof(sa_api_v1)),
        SA_CAPABILITY_BUFFER_VALIDATION,
        &validate_buffer_view_boundary,
        {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
         nullptr, nullptr, nullptr},
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
