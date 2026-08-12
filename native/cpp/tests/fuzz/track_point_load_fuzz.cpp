#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* const data, const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_2;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.track_point_load_solve == nullptr) {
        return 0;
    }

    sa_track_point_load_config_v1 config {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_track_point_load_config_v1)),
        10.0,
        9U,
        SA_TRACK_SUPPORT_PINNED,
        SA_TRACK_THEORY_EULER,
        0U,
        1.0e8,
        1.0e9,
        1.0e5,
        1.0e4,
        1.0e-9,
        500U,
        0U,
        -10'000.0,
        5.0,
        {0U, 0U},
    };
    const auto copied = size < sizeof(config) ? size : sizeof(config);
    if (copied > 0U) {
        std::memcpy(&config, data, copied);
    }
    config.abi_version = SA_ABI_V1_2;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.node_count = 7U + config.node_count % 122U;
    config.cg_max_iter = 1U + config.cg_max_iter % 64U;
    config.support_type %= 2U;
    config.theory %= 2U;
    config.flags = 0U;
    config.reserved_u32 = 0U;
    config.reserved[0] = 0U;
    config.reserved[1] = 0U;

    std::array<double, 128> displacement {};
    std::array<double, 128> rotation {};
    sa_mut_buffer_view_v1 displacement_view {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        displacement.data(),
        config.node_count,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_mut_buffer_view_v1 rotation_view = displacement_view;
    rotation_view.data = rotation.data();
    if (size > 0U && (data[0] & 1U) != 0U) {
        displacement_view.length = static_cast<std::uint64_t>(config.node_count - 1U);
    }
    if (size > 1U && (data[1] & 1U) != 0U) {
        rotation_view.stride_bytes = sizeof(double) * 2U;
    }

    sa_track_point_load_result_v1 result {};
    result.abi_version = SA_ABI_V1_2;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    std::array<char, 128> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    static_cast<void>(api.track_point_load_solve(
        &config,
        &displacement_view,
        &rotation_view,
        &result,
        &error));
    return 0;
}
