#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* const data, const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_3;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.nonlinear_static_solve == nullptr) {
        return 0;
    }

    sa_nonlinear_static_config_v1 config {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_nonlinear_static_config_v1)),
        3U,
        16U,
        1.0e-7,
        0.04,
        0.5,
        0.03125,
        1.0,
        0U,
        0U,
        {0U, 0U},
    };
    const auto copied = size < sizeof(config) ? size : sizeof(config);
    if (copied > 0U) {
        std::memcpy(&config, data, copied);
    }
    config.abi_version = SA_ABI_V1_3;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.story_count = 1U + config.story_count % 16U;
    config.max_iter = 1U + config.max_iter % 16U;
    config.flags = 0U;
    config.reserved_u32 = 0U;
    config.reserved[0] = 0U;
    config.reserved[1] = 0U;

    std::array<double, 16> stiffness {};
    std::array<double, 16> height {};
    std::array<double, 16> axial {};
    std::array<double, 16> yield_drift {};
    std::array<double, 16> load {};
    std::array<double, 16> displacement {};
    for (std::size_t index = 0U; index < stiffness.size(); ++index) {
        stiffness[index] = 1.0e8 - static_cast<double>(index) * 1.0e6;
        height[index] = 3.0;
        axial[index] = 1.0e6;
        yield_drift[index] = 0.02;
        load[index] = 10'000.0;
    }
    const auto input = [&config](const double* const values) {
        return sa_buffer_view_v1 {
            SA_ABI_V1_3,
            static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
            values,
            config.story_count,
            sizeof(double),
            SA_ELEMENT_TYPE_F64,
            SA_MEMORY_SPACE_HOST,
            -1,
            0U,
        };
    };
    auto stiffness_view = input(stiffness.data());
    const auto height_view = input(height.data());
    const auto axial_view = input(axial.data());
    const auto yield_view = input(yield_drift.data());
    const auto load_view = input(load.data());
    sa_mut_buffer_view_v1 displacement_view {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        displacement.data(),
        config.story_count,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    if (size > 0U && (data[0] & 1U) != 0U) {
        stiffness_view.length = static_cast<std::uint64_t>(config.story_count - 1U);
    }
    if (size > 1U && (data[1] & 1U) != 0U) {
        displacement_view.stride_bytes = sizeof(double) * 2U;
    }
    if (size > 2U && (data[2] & 1U) != 0U) {
        displacement_view.data = stiffness.data();
    }

    sa_nonlinear_static_result_v1 result {};
    result.abi_version = SA_ABI_V1_3;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    std::array<char, 128> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    static_cast<void>(api.nonlinear_static_solve(
        &config,
        &stiffness_view,
        &height_view,
        &axial_view,
        &yield_view,
        &load_view,
        &displacement_view,
        &result,
        &error));
    return 0;
}
