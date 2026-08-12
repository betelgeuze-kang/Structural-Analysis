#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace {

template <typename Value, std::size_t Length>
[[nodiscard]] sa_buffer_view_v1 input(
    const std::array<Value, Length>& values,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* const data,
    const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_8;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.sparse_linear_solve == nullptr) {
        return 0;
    }

    std::array<std::uint64_t, 5> rows {0U, 1U, 2U, 3U, 4U};
    std::array<std::uint32_t, 4> columns {0U, 1U, 2U, 3U};
    std::array<double, 4> values {1.0, 2.0, 3.0, 4.0};
    std::array<double, 4> rhs {1.0, 2.0, 3.0, 4.0};
    std::array<double, 4> output_values {};
    sa_sparse_linear_config_v1 config {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_sparse_linear_config_v1)),
        1U + static_cast<std::uint32_t>(size == 0U ? 0U : data[0] % 32U),
        0U,
        1.0e-10,
        1.0e-10,
        0.0,
        {0U, 0U},
    };
    sa_sparse_csr_matrix_v1 matrix {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_sparse_csr_matrix_v1)),
        4U,
        input(rows, SA_ELEMENT_TYPE_U64),
        input(columns, SA_ELEMENT_TYPE_U32),
        input(values, SA_ELEMENT_TYPE_F64),
        {0U, 0U},
    };
    auto rhs_view = input(rhs, SA_ELEMENT_TYPE_F64);
    sa_buffer_view_v1 initial_view {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        nullptr,
        0U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_mut_buffer_view_v1 output_view {
        SA_ABI_V1_8,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        output_values.data(),
        output_values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_sparse_linear_result_v1 result {};
    result.abi_version = SA_ABI_V1_8;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));

    if (size > 1U) {
        switch (data[1] % 8U) {
        case 1U:
            rows.back() = std::numeric_limits<std::uint64_t>::max();
            break;
        case 2U:
            columns[1] = 0U;
            break;
        case 3U:
            values[0] = std::numeric_limits<double>::quiet_NaN();
            break;
        case 4U:
            matrix.row_offsets.stride_bytes = sizeof(std::uint64_t) * 2U;
            break;
        case 5U:
            rhs_view.length = std::numeric_limits<std::uint64_t>::max();
            break;
        case 6U:
            output_view.data = rhs.data();
            break;
        case 7U:
            config.flags = 1U;
            break;
        default:
            break;
        }
    }
    if (size > 2U && (data[2] & 1U) != 0U) {
        const auto copied = std::min(size - 3U, sizeof(config.maximum_increment));
        if (copied > 0U) {
            std::memcpy(&config.maximum_increment, data + 3U, copied);
        }
    }
    static_cast<void>(api.sparse_linear_solve(
        &config,
        &matrix,
        &rhs_view,
        &initial_view,
        &output_view,
        &result,
        nullptr));
    return 0;
}
