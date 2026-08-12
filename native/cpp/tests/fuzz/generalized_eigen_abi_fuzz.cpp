#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <span>

namespace {

template <std::size_t Length>
[[nodiscard]] sa_buffer_view_v1 input(const std::array<double, Length>& values) {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

template <std::size_t Length>
[[nodiscard]] sa_mut_buffer_view_v1 output(std::array<double, Length>& values) {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_generalized_eigen_config_v1 config() {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_generalized_eigen_config_v1)),
        2U,
        128U,
        0U,
        0U,
        1.0e-12,
        1.0e-12,
        1.0e-12,
        1.0e-10,
        1.0e-9,
        1.0e-8,
        1.0e-14,
        {0U, 0U},
    };
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* const data,
    const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_9;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK || api.modal_solve == nullptr
        || api.buckling_solve == nullptr) {
        return 0;
    }

    std::array<double, 16> stiffness {
        6.0, -0.2, 0.0, 0.0,
        -0.2, 8.0, -0.3, 0.0,
        0.0, -0.3, 10.0, -0.4,
        0.0, 0.0, -0.4, 12.0,
    };
    std::array<double, 16> mass {
        2.0, 0.0, 0.0, 0.0,
        0.0, 3.0, 0.0, 0.0,
        0.0, 0.0, 4.0, 0.0,
        0.0, 0.0, 0.0, 5.0,
    };
    std::array<double, 16> geometric {
        3.0, 0.0, 0.0, 0.0,
        0.0, 2.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 0.0,
    };
    std::array<double, 4> recovery_scale {1.0, 1.0, 1.0, 1.0};
    auto eigen_config = config();
    sa_dense_symmetric_matrix_v1 stiffness_matrix {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_dense_symmetric_matrix_v1)),
        4U,
        input(stiffness),
        {0U, 0U},
    };
    sa_dense_symmetric_matrix_v1 mass_matrix {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_dense_symmetric_matrix_v1)),
        4U,
        input(mass),
        {0U, 0U},
    };
    sa_dense_symmetric_matrix_v1 geometric_matrix {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_dense_symmetric_matrix_v1)),
        4U,
        input(geometric),
        {0U, 0U},
    };
    auto scale = input(recovery_scale);

    std::array<double, 2> modal_eigenvalue {};
    std::array<double, 2> modal_omega {};
    std::array<double, 2> modal_frequency {};
    std::array<double, 2> modal_period {};
    std::array<double, 8> modal_shapes {};
    std::array<double, 2> modal_mass {};
    std::array<double, 2> modal_stiffness {};
    std::array<double, 2> modal_residual {};
    sa_modal_outputs_v1 modal_outputs {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_modal_outputs_v1)),
        output(modal_eigenvalue),
        output(modal_omega),
        output(modal_frequency),
        output(modal_period),
        output(modal_shapes),
        output(modal_mass),
        output(modal_stiffness),
        output(modal_residual),
        {0U, 0U},
    };
    sa_modal_result_v1 modal_result {};
    modal_result.abi_version = SA_ABI_V1_9;
    modal_result.struct_size = static_cast<std::uint32_t>(sizeof(modal_result));

    std::array<double, 2> load_factor {};
    std::array<double, 8> buckling_shapes {};
    std::array<double, 2> elastic {};
    std::array<double, 2> geometric_energy {};
    std::array<double, 2> buckling_residual {};
    sa_buckling_outputs_v1 buckling_outputs {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_buckling_outputs_v1)),
        output(load_factor),
        output(buckling_shapes),
        output(elastic),
        output(geometric_energy),
        output(buckling_residual),
        {0U, 0U},
    };
    sa_buckling_result_v1 buckling_result {};
    buckling_result.abi_version = SA_ABI_V1_9;
    buckling_result.struct_size = static_cast<std::uint32_t>(sizeof(buckling_result));

    if (size > 0U) {
        switch (data[0] % 12U) {
        case 1U:
            stiffness[1] += 1.0;
            break;
        case 2U:
            mass[0] = -1.0;
            break;
        case 3U:
            geometric[0] = std::numeric_limits<double>::quiet_NaN();
            break;
        case 4U:
            eigen_config.maximum_sweeps = 1U;
            break;
        case 5U:
            eigen_config.flags = 1U;
            break;
        case 6U:
            stiffness_matrix.values.length = std::numeric_limits<std::uint64_t>::max();
            break;
        case 7U:
            mass_matrix.values.stride_bytes = 16U;
            break;
        case 8U:
            modal_outputs.omega_rad_per_s.data = modal_outputs.eigenvalue_rad2_per_s2.data;
            break;
        case 9U:
            buckling_outputs.load_factor.data = const_cast<void*>(stiffness_matrix.values.data);
            break;
        case 10U:
            scale.length = 3U;
            break;
        case 11U:
            modal_result.abi_version = SA_ABI_V1_8;
            break;
        default:
            break;
        }
    }
    if (size > 1U && (data[1] & 1U) != 0U) {
        const auto copied = std::min(size - 2U, sizeof(eigen_config.residual_relative_tolerance));
        if (copied > 0U) {
            std::memcpy(&eigen_config.residual_relative_tolerance, data + 2U, copied);
        }
    }
    static_cast<void>(api.modal_solve(
        &eigen_config,
        &stiffness_matrix,
        &mass_matrix,
        &scale,
        &modal_outputs,
        &modal_result,
        nullptr));
    static_cast<void>(api.buckling_solve(
        &eigen_config,
        &stiffness_matrix,
        &geometric_matrix,
        &scale,
        &buckling_outputs,
        &buckling_result,
        nullptr));
    return 0;
}
