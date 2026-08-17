#include "structural_engine_c_api.h"
#include "structural_engine_internal.hpp"

#include <cstring>
#include <new>

namespace structural_engine_internal {

namespace {
constexpr size_t kErrorCapacity = 4096;
thread_local char g_last_error[kErrorCapacity] = {};
}  // namespace

void set_thread_error(const char *message) noexcept {
    const char *source = message == nullptr ? "" : message;
    size_t index = 0;
    while (source[index] != '\0' && index + 1 < kErrorCapacity) {
        g_last_error[index] = source[index];
        ++index;
    }
    g_last_error[index] = '\0';
}

const char *thread_error() noexcept {
    return g_last_error;
}

}  // namespace structural_engine_internal

namespace {

constexpr uint64_t kReferenceCapabilities =
    SA_CAPABILITY_CPU_REFERENCE | SA_CAPABILITY_LINEAR_FRAME3D;
constexpr const char *kImplementationName = "structural-engine-cpu-reference-abi";

sa_status validate_config(const sa_engine_config *config) {
    using structural_engine_internal::set_thread_error;
    if (config == nullptr) {
        set_thread_error("engine config is null");
        return SA_STATUS_INVALID_ARGUMENT;
    }
    if (config->struct_size < sizeof(sa_engine_config)) {
        set_thread_error("engine config struct_size is too small");
        return SA_STATUS_INVALID_ARGUMENT;
    }
    if (config->abi_version_major != SA_ABI_VERSION_MAJOR ||
        config->abi_version_minor > SA_ABI_VERSION_MINOR) {
        set_thread_error("requested ABI version is not supported");
        return SA_STATUS_ABI_MISMATCH;
    }
    if (config->execution_mode != SA_EXECUTION_MODE_AUDITED &&
        config->execution_mode != SA_EXECUTION_MODE_PERFORMANCE) {
        set_thread_error("execution mode is invalid");
        return SA_STATUS_INVALID_ARGUMENT;
    }
    if (config->requested_device_index != -1) {
        set_thread_error("the reference lifecycle implementation has no device backend");
        return SA_STATUS_UNSUPPORTED;
    }
    for (const uint32_t value : config->reserved_u32) {
        if (value != 0) {
            set_thread_error("engine config reserved fields must be zero");
            return SA_STATUS_INVALID_ARGUMENT;
        }
    }
    return SA_STATUS_OK;
}

}  // namespace

struct sa_engine {
    uint32_t execution_mode;
    uint64_t capability_bits;
};

extern "C" sa_status sa_get_api_info(sa_api_info *out_info) noexcept {
    using structural_engine_internal::set_thread_error;
    try {
        if (out_info == nullptr) {
            set_thread_error("API info output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        if (out_info->struct_size < sizeof(sa_api_info)) {
            set_thread_error("API info struct_size is too small");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        out_info->abi_version_major = SA_ABI_VERSION_MAJOR;
        out_info->abi_version_minor = SA_ABI_VERSION_MINOR;
        out_info->reserved_u32 = 0;
        out_info->capability_bits = kReferenceCapabilities;
        out_info->implementation_name = kImplementationName;
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (...) {
        set_thread_error("unexpected exception while querying API information");
        return SA_STATUS_INTERNAL_ERROR;
    }
}

extern "C" sa_status sa_engine_create(
    const sa_engine_config *config,
    sa_engine **out_engine
) noexcept {
    using structural_engine_internal::set_thread_error;
    try {
        if (out_engine == nullptr) {
            set_thread_error("engine output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        *out_engine = nullptr;
        const sa_status status = validate_config(config);
        if (status != SA_STATUS_OK) {
            return status;
        }

        sa_engine *engine = new (std::nothrow) sa_engine{
            config->execution_mode,
            kReferenceCapabilities,
        };
        if (engine == nullptr) {
            set_thread_error("engine allocation failed");
            return SA_STATUS_OUT_OF_MEMORY;
        }
        *out_engine = engine;
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (...) {
        set_thread_error("unexpected exception while creating engine");
        return SA_STATUS_INTERNAL_ERROR;
    }
}

extern "C" void sa_engine_destroy(sa_engine *engine) noexcept {
    using structural_engine_internal::set_thread_error;
    try {
        delete engine;
    } catch (...) {
        set_thread_error("unexpected exception while destroying engine");
    }
}

extern "C" sa_status sa_engine_capabilities(
    const sa_engine *engine,
    uint64_t *out_capability_bits
) noexcept {
    using structural_engine_internal::set_thread_error;
    try {
        if (out_capability_bits == nullptr) {
            set_thread_error("capability output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        *out_capability_bits = 0;
        if (engine == nullptr) {
            set_thread_error("engine is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        *out_capability_bits = engine->capability_bits;
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (...) {
        if (out_capability_bits != nullptr) {
            *out_capability_bits = 0;
        }
        set_thread_error("unexpected exception while querying capabilities");
        return SA_STATUS_INTERNAL_ERROR;
    }
}

extern "C" sa_status sa_engine_last_error(
    const sa_engine *engine,
    char *buffer,
    size_t buffer_capacity,
    size_t *out_required_size
) noexcept {
    using structural_engine_internal::set_thread_error;
    try {
        (void)engine;
        if (out_required_size == nullptr) {
            set_thread_error("required-size output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        const char *message = structural_engine_internal::thread_error();
        const size_t message_size = std::strlen(message);
        const size_t required = message_size + 1;
        *out_required_size = required;
        if (buffer == nullptr || buffer_capacity < required) {
            return SA_STATUS_BUFFER_TOO_SMALL;
        }
        if (message_size > 0) {
            std::memcpy(buffer, message, message_size);
        }
        buffer[message_size] = '\0';
        return SA_STATUS_OK;
    } catch (...) {
        set_thread_error("unexpected exception while reading last error");
        return SA_STATUS_INTERNAL_ERROR;
    }
}
