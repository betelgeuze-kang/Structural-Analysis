#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace {

[[nodiscard]] sa_buffer_view_v1 input(const double* const data, const std::uint64_t length) {
    return {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        data,
        length,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_mut_buffer_view_v1 output(double* const data, const std::uint64_t length) {
    return {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        data,
        length,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* const data, const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_7;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.reference_element_evaluate == nullptr) {
        return 0;
    }
    const auto kind = size == 0U ? SA_REFERENCE_ELEMENT_TRUSS3D
                                 : 1U + static_cast<std::uint32_t>(data[0] % 3U);
    const auto coordinate_count = kind == SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE ? 9U : 6U;
    const auto dof_count = kind == SA_REFERENCE_ELEMENT_TRUSS3D
        ? 6U
        : (kind == SA_REFERENCE_ELEMENT_FRAME3D ? 12U : 9U);
    const auto recovery_count = kind == SA_REFERENCE_ELEMENT_TRUSS3D
        ? 3U
        : (kind == SA_REFERENCE_ELEMENT_FRAME3D ? 12U : 6U);
    std::array<double, 9> coordinates {0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0, 0.0};
    std::array<double, 12> displacement {};
    std::array<double, 12> direction {};
    const auto copied = size > 1U
        ? ((size - 1U) < sizeof(coordinates) ? size - 1U : sizeof(coordinates))
        : 0U;
    if (copied > 0U) {
        std::memcpy(coordinates.data(), data + 1U, copied);
    }
    for (std::size_t index = 0U; index < direction.size(); ++index) {
        direction[index] = static_cast<double>(index + 1U);
    }
    std::array<double, 144> tangent {};
    std::array<double, 144> mass {};
    std::array<double, 12> residual {};
    std::array<double, 12> jvp {};
    std::array<double, 12> recovery {};
    sa_reference_element_config_v1 config {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(sa_reference_element_config_v1)),
        kind,
        0U,
        200.0,
        0.25,
        1000.0,
        kind == SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE ? 0.0 : 0.01,
        kind == SA_REFERENCE_ELEMENT_FRAME3D ? 2.0E-5 : 0.0,
        kind == SA_REFERENCE_ELEMENT_FRAME3D ? 3.0E-5 : 0.0,
        kind == SA_REFERENCE_ELEMENT_FRAME3D ? 4.0E-5 : 0.0,
        kind == SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE ? 0.1 : 0.0,
        0.0,
        input(coordinates.data(), coordinate_count),
        input(displacement.data(), dof_count),
        input(direction.data(), dof_count),
        {0U, 0U},
    };
    sa_reference_element_outputs_v1 outputs {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(sa_reference_element_outputs_v1)),
        output(tangent.data(), dof_count * dof_count),
        output(mass.data(), dof_count * dof_count),
        output(residual.data(), dof_count),
        output(jvp.data(), dof_count),
        output(recovery.data(), recovery_count),
        {0U, 0U},
    };
    if (size > 2U && (data[1] & 1U) != 0U) {
        config.displacement.length = dof_count - 1U;
    }
    if (size > 3U && (data[2] & 1U) != 0U) {
        outputs.consistent_mass.data = outputs.tangent.data;
    }
    if (size > 4U && (data[3] & 1U) != 0U) {
        config.flags = 1U;
    }
    sa_reference_element_result_v1 result {};
    result.abi_version = SA_ABI_V1_7;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    std::array<char, 128> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_7,
        static_cast<std::uint32_t>(sizeof(error)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    static_cast<void>(api.reference_element_evaluate(&config, &outputs, &result, &error));
    return 0;
}
