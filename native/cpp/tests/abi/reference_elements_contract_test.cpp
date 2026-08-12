#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string_view>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

[[nodiscard]] sa_api_v1 load_api(const std::uint32_t version) {
    const sa_api_request_v1 request {
        version,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

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

struct TrussCall {
    std::array<double, 6> coordinates {0.0, 0.0, 0.0, 2.0, 0.0, 0.0};
    std::array<double, 6> displacement {0.0, 0.0, 0.0, 0.002, 0.0, 0.0};
    std::array<double, 6> direction {0.0, 0.0, 0.0, 1.0, 0.0, 0.0};
    std::array<double, 36> tangent {};
    std::array<double, 36> mass {};
    std::array<double, 6> residual {};
    std::array<double, 6> jvp {};
    std::array<double, 3> recovery {};
    sa_reference_element_config_v1 config {};
    sa_reference_element_outputs_v1 outputs {};
    sa_reference_element_result_v1 result {};

    TrussCall() {
        config = {
            SA_ABI_V1_7,
            static_cast<std::uint32_t>(sizeof(config)),
            SA_REFERENCE_ELEMENT_TRUSS3D,
            0U,
            200.0,
            0.25,
            1000.0,
            0.01,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            input(coordinates.data(), coordinates.size()),
            input(displacement.data(), displacement.size()),
            input(direction.data(), direction.size()),
            {0U, 0U},
        };
        outputs = {
            SA_ABI_V1_7,
            static_cast<std::uint32_t>(sizeof(outputs)),
            output(tangent.data(), tangent.size()),
            output(mass.data(), mass.size()),
            output(residual.data(), residual.size()),
            output(jvp.data(), jvp.size()),
            output(recovery.data(), recovery.size()),
            {0U, 0U},
        };
        result.abi_version = SA_ABI_V1_7;
        result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    }
};

[[nodiscard]] bool table_is_append_only() {
    const auto api = load_api(SA_ABI_V1_7);
    CHECK(api.abi_version == SA_ABI_V1_7);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.reference_element_evaluate != nullptr);
    CHECK((api.capabilities & SA_CAPABILITY_REFERENCE_ELEMENTS_CPU) != 0U);
    const auto old = load_api(SA_ABI_V1_6);
    CHECK(old.model_ir_ndtha_adapt != nullptr);
    CHECK(old.reference_element_evaluate == nullptr);
    CHECK((old.capabilities & SA_CAPABILITY_REFERENCE_ELEMENTS_CPU) == 0U);
    return true;
}

[[nodiscard]] bool truss_success_is_complete_and_cpu_only() {
    const auto api = load_api(SA_ABI_V1_7);
    TrussCall call;
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_OK);
    CHECK(call.result.abi_version == SA_ABI_V1_7);
    CHECK(call.result.struct_size == sizeof(call.result));
    CHECK(call.result.kind == SA_REFERENCE_ELEMENT_TRUSS3D);
    CHECK(call.result.dof_count == 6U);
    CHECK(call.result.recovery_count == 3U);
    CHECK(call.result.output_matrix_length == 36U);
    CHECK(call.result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(call.result.fallback_count == 0U);
    CHECK(call.result.reserved_u32 == 0U);
    CHECK(call.result.reserved[0] == 0U && call.result.reserved[1] == 0U);
    CHECK(std::abs(call.tangent[0] - 1.0) <= 1.0E-15);
    CHECK(std::abs(call.tangent[3] + 1.0) <= 1.0E-15);
    CHECK(std::abs(call.residual[0] + 0.002) <= 1.0E-15);
    CHECK(std::abs(call.residual[3] - 0.002) <= 1.0E-15);
    CHECK(std::abs(call.recovery[0] - 0.001) <= 1.0E-15);
    CHECK(std::abs(call.recovery[1] - 0.2) <= 1.0E-15);
    CHECK(std::abs(call.recovery[2] - 0.002) <= 1.0E-15);
    return true;
}

[[nodiscard]] bool failures_do_not_publish_partial_outputs() {
    const auto api = load_api(SA_ABI_V1_7);
    TrussCall call;
    std::fill(call.tangent.begin(), call.tangent.end(), -7.0);
    std::fill(call.mass.begin(), call.mass.end(), -7.0);
    std::fill(call.residual.begin(), call.residual.end(), -7.0);
    std::fill(call.jvp.begin(), call.jvp.end(), -7.0);
    std::fill(call.recovery.begin(), call.recovery.end(), -7.0);
    call.result.kind = UINT32_C(0xA5A5A5A5);
    call.coordinates[3] = 0.0;
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::all_of(call.tangent.begin(), call.tangent.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(std::all_of(call.mass.begin(), call.mass.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(std::all_of(call.residual.begin(), call.residual.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(std::all_of(call.jvp.begin(), call.jvp.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(std::all_of(call.recovery.begin(), call.recovery.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(call.result.kind == UINT32_C(0xA5A5A5A5));

    call.coordinates[3] = 2.0;
    call.outputs.tangent.length = 35U;
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    call.outputs.tangent = output(call.tangent.data(), call.tangent.size());
    call.outputs.consistent_mass = output(call.tangent.data(), call.tangent.size());
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    call.outputs.consistent_mass = output(call.mass.data(), call.mass.size());
    call.displacement[0] = std::numeric_limits<double>::quiet_NaN();
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    call.displacement[0] = 0.0;
    call.config.youngs_modulus_pa = std::numeric_limits<double>::max();
    call.config.area_m2 = std::numeric_limits<double>::max();
    CHECK(api.reference_element_evaluate(
              &call.config, &call.outputs, &call.result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::all_of(call.tangent.begin(), call.tangent.end(), [](const auto value) {
        return value == -7.0;
    }));
    CHECK(call.result.kind == UINT32_C(0xA5A5A5A5));
    return true;
}

}  // namespace

int main() {
    if (!table_is_append_only() || !truss_success_is_complete_and_cpu_only()
        || !failures_do_not_publish_partial_outputs()) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
