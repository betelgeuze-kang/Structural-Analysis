#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* const data, const std::size_t size) {
    sa_api_request_v1 request {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_0;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK || api.validate_buffer_view == nullptr) {
        return 0;
    }

    sa_buffer_view_v1 view {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        size == 0U ? nullptr : data,
        0U,
        0U,
        SA_ELEMENT_TYPE_U8,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    const auto copied = size < sizeof(view) ? size : sizeof(view);
    if (copied > 0U) {
        std::memcpy(&view, data, copied);
    }
    if (size == 0U) {
        view.data = nullptr;
    } else if ((data[0] & 1U) != 0U) {
        view.data = data;
    }

    std::array<char, 64> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    static_cast<void>(api.validate_buffer_view(&view, &error));
    return 0;
}
