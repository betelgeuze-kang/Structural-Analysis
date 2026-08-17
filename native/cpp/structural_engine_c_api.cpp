#include "structural_engine_c_api.h"

#include <algorithm>
#include <cstring>
#include <new>
#include <string>

namespace {

constexpr uint64_t kReferenceCapabilities = SA_CAPABILITY_CPU_REFERENCE;
constexpr const char *kImplementationName = "structural-engine-cpu-reference-abi";
thread_local std::string g_last_error;

void set_thread_error(const char *message) {
    g_last_error = message == nullptr ? "" : message;
}

sa_status validate_config(const sa_engine_config *config) {
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
    return SA_STATUS_OK;
}

const std::string &error_for(const sa_engine *engine);

}  // namespace

struct sa_engine {
    uint32_t execution_mode;
    uint64_t capability_bits;
    std::string last_error;
};

namespace {

const std::string &error_for(const sa_engine *engine) {
    if (engine != nullptr && !engine->last_error.empty()) {
        return engine->last_error;
    }
    return g_last_error;
}

}  // namespace

extern "C" sa_status sa_get_api_info(sa_api_info *out_info) noexcept {
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
            std::string{},
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
    try {
        if (engine == nullptr || out_capability_bits == nullptr) {
            set_thread_error("engine or capability output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        *out_capability_bits = engine->capability_bits;
        return SA_STATUS_OK;
    } catch (...) {
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
    try {
        if (out_required_size == nullptr) {
            set_thread_error("required-size output is null");
            return SA_STATUS_INVALID_ARGUMENT;
        }
        const std::string &message = error_for(engine);
        const size_t required = message.size() + 1;
        *out_required_size = required;
        if (buffer == nullptr || buffer_capacity < required) {
            return SA_STATUS_BUFFER_TOO_SMALL;
        }
        const size_t bytes = std::min(message.size(), buffer_capacity - 1);
        if (bytes > 0) {
            std::memcpy(buffer, message.data(), bytes);
        }
        buffer[bytes] = '\0';
        return SA_STATUS_OK;
    } catch (...) {
        set_thread_error("unexpected exception while reading last error");
        return SA_STATUS_INTERNAL_ERROR;
    }
}
