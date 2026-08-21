#include "structural/abi_v1.h"

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <thread>
#include <vector>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

struct ErrorStorage {
    std::array<char, 128> bytes {};
    sa_error_buffer_v1 descriptor {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        bytes.data(),
        bytes.size(),
        0U,
    };
};

[[nodiscard]] sa_api_request_v1 request() {
    return {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
}

[[nodiscard]] sa_api_v1 output_table() {
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_0;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    return api;
}

[[nodiscard]] bool status_taxonomy_is_stable() {
    CHECK(SA_OK == 0);
    CHECK(SA_ERR_INVALID_ARGUMENT == 1000);
    CHECK(SA_ERR_ABI_VERSION_MISMATCH == 1001);
    CHECK(SA_ERR_STRUCT_SIZE == 1002);
    CHECK(SA_ERR_BUFFER_TOO_SMALL == 1003);
    CHECK(SA_ERR_SCHEMA_INVALID == 1100);
    CHECK(SA_ERR_SEMANTIC_INVALID == 1101);
    CHECK(SA_ERR_ANALYSIS_NOT_READY == 1102);
    CHECK(SA_ERR_UNSUPPORTED == 1200);
    CHECK(SA_ERR_STATE_CONFLICT == 1300);
    CHECK(SA_ERR_CHECKPOINT_MISMATCH == 1301);
    CHECK(SA_ERR_BACKEND_UNAVAILABLE == 1400);
    CHECK(SA_ERR_DEVICE_MISMATCH == 1401);
    CHECK(SA_ERR_FALLBACK_FORBIDDEN == 1402);
    CHECK(SA_ERR_CANCELLED == 1500);
    CHECK(SA_ERR_INTERNAL == 1900);
    return true;
}

[[nodiscard]] bool entry_table_supports_prefix_and_current_sizes() {
    auto current_request = request();
    auto api = output_table();
    ErrorStorage error;
    CHECK(sa_get_api_v1(&current_request, &api, &error.descriptor) == SA_OK);
    CHECK(api.abi_version == SA_ABI_V1_0);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.capabilities == SA_CAPABILITY_BUFFER_VALIDATION);
    CHECK(api.validate_buffer_view != nullptr);
    for (const auto* reserved : api.reserved) {
        CHECK(reserved == nullptr);
    }

    auto prefix_request = request();
    prefix_request.struct_size = SA_API_REQUEST_V1_MIN_SIZE;
    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_MIN_SIZE> prefix_storage {};
    auto* prefix_api = reinterpret_cast<sa_api_v1*>(prefix_storage.data());
    prefix_api->abi_version = SA_ABI_V1_0;
    prefix_api->struct_size = SA_API_V1_MIN_SIZE;
    CHECK(sa_get_api_v1(&prefix_request, prefix_api, nullptr) == SA_OK);
    CHECK(prefix_api->abi_version == SA_ABI_V1_0);
    CHECK(prefix_api->capabilities == SA_CAPABILITY_BUFFER_VALIDATION);
    CHECK(prefix_api->validate_buffer_view != nullptr);
    return true;
}

[[nodiscard]] bool entry_failures_are_atomic() {
    auto invalid_request = request();
    invalid_request.abi_version = 0x0002'0000U;
    auto api = output_table();
    std::memset(api.reserved, 0xA5, sizeof(api.reserved));
    std::array<std::byte, sizeof(sa_api_v1)> before {};
    std::memcpy(before.data(), &api, before.size());
    ErrorStorage error;
    CHECK(sa_get_api_v1(&invalid_request, &api, &error.descriptor)
          == SA_ERR_ABI_VERSION_MISMATCH);
    CHECK(std::memcmp(before.data(), &api, before.size()) == 0);
    CHECK(error.descriptor.required > 1U);

    invalid_request = request();
    invalid_request.reserved[1] = 1U;
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_INVALID_ARGUMENT);

    invalid_request = request();
    invalid_request.struct_size = sizeof(sa_header_v1);
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_STRUCT_SIZE);

    invalid_request = request();
    invalid_request.struct_size = SA_API_REQUEST_V1_MIN_SIZE + 1U;
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_STRUCT_SIZE);
    return true;
}

[[nodiscard]] bool caller_owned_error_buffers_are_bounded() {
    sa_error_buffer_v1 query {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        nullptr,
        0U,
        0U,
    };
    auto api = output_table();
    CHECK(sa_get_api_v1(nullptr, &api, &query) == SA_ERR_INVALID_ARGUMENT);
    CHECK(query.required > 1U);

    std::array<char, 4> tiny {'x', 'x', 'x', 'x'};
    sa_error_buffer_v1 truncated {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        tiny.data(),
        tiny.size(),
        0U,
    };
    CHECK(sa_get_api_v1(nullptr, &api, &truncated) == SA_ERR_INVALID_ARGUMENT);
    CHECK(truncated.required > tiny.size());
    CHECK(tiny.back() == '\0');

    sa_error_buffer_v1 malformed {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        tiny.data(),
        0U,
        77U,
    };
    CHECK(sa_get_api_v1(nullptr, &api, &malformed) == SA_ERR_INVALID_ARGUMENT);
    CHECK(malformed.required == 77U);
    return true;
}

[[nodiscard]] sa_buffer_view_v1 valid_view(const double* const values) {
    return {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values,
        2U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] bool buffer_validation_is_fail_closed() {
    auto api = output_table();
    auto current_request = request();
    CHECK(sa_get_api_v1(&current_request, &api, nullptr) == SA_OK);
    const std::array<double, 2> values {1.0, 2.0};
    auto view = valid_view(values.data());
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_OK);

    view.data = nullptr;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.stride_bytes = sizeof(double) - 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.length = std::numeric_limits<std::uint64_t>::max();
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(reinterpret_cast<const double*>(
        std::numeric_limits<std::uintptr_t>::max() - 3U));
    view.length = 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.element_type = 999U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.flags = 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.memory_space = SA_MEMORY_SPACE_DEVICE;
    view.device_id = -1;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_DEVICE_MISMATCH);
    view.device_id = 0;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_BACKEND_UNAVAILABLE);

    view = valid_view(values.data());
    view.data = nullptr;
    view.length = 0U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool immutable_calls_are_concurrent() {
    auto api = output_table();
    auto current_request = request();
    CHECK(sa_get_api_v1(&current_request, &api, nullptr) == SA_OK);
    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    workers.reserve(8U);
    for (std::size_t worker = 0U; worker < 8U; ++worker) {
        workers.emplace_back([api, worker, &passed] {
            const std::array<double, 2> values {
                static_cast<double>(worker),
                static_cast<double>(worker + 1U),
            };
            const auto view = valid_view(values.data());
            for (std::size_t iteration = 0U; iteration < 512U; ++iteration) {
                ErrorStorage error;
                if (api.validate_buffer_view(&view, &error.descriptor) != SA_OK) {
                    passed.store(false, std::memory_order_relaxed);
                }
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    CHECK(passed.load(std::memory_order_relaxed));
    return true;
}

} // namespace

int main() {
    const std::array tests {
        status_taxonomy_is_stable,
        entry_table_supports_prefix_and_current_sizes,
        entry_failures_are_atomic,
        caller_owned_error_buffers_are_bounded,
        buffer_validation_is_fail_closed,
        immutable_calls_are_concurrent,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
