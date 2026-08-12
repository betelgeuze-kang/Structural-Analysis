#include "structural/abi_v1.h"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

[[nodiscard]] bool near(const double actual, const double expected) {
    return std::abs(actual - expected) <= 1.0e-15;
}

[[nodiscard]] sa_api_v1 load_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_3;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] sa_nonlinear_static_config_v1 config() {
    return {
        SA_ABI_V1_3,
        static_cast<std::uint32_t>(sizeof(sa_nonlinear_static_config_v1)),
        3U,
        60U,
        1.0e-7,
        0.04,
        0.5,
        0.03125,
        1.0,
        0U,
        0U,
        {0U, 0U},
    };
}

[[nodiscard]] sa_buffer_view_v1 input(const double* const data, const std::uint64_t length = 3U) {
    return {
        SA_ABI_V1_3,
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

[[nodiscard]] sa_mut_buffer_view_v1 output(double* const data, const std::uint64_t length = 3U) {
    return {
        SA_ABI_V1_3,
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

[[nodiscard]] sa_nonlinear_static_result_v1 result_descriptor() {
    sa_nonlinear_static_result_v1 result {};
    result.abi_version = SA_ABI_V1_3;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    result.reserved = UINT64_C(0xA5A5A5A5A5A5A5A5);
    return result;
}

struct Inputs {
    std::array<double, 3> stiffness {1.0e8, 9.0e7, 8.0e7};
    std::array<double, 3> height {3.0, 3.0, 3.0};
    std::array<double, 3> axial {1.0e6, 8.0e5, 6.0e5};
    std::array<double, 3> yield_drift {0.02, 0.02, 0.02};
    std::array<double, 3> load {10'000.0, 8'000.0, 6'000.0};
};

[[nodiscard]] bool v1_3_table_preserves_v1_2_and_exposes_one_new_operation() {
    const auto api = load_api();
    CHECK(api.abi_version == SA_ABI_V1_3);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.capabilities
          == (SA_CAPABILITY_BUFFER_VALIDATION | SA_CAPABILITY_MODEL_IR_V2_TYPED
              | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
              | SA_CAPABILITY_NONLINEAR_STATIC_CPU));
    CHECK(api.track_point_load_solve != nullptr);
    CHECK(api.nonlinear_static_solve != nullptr);
    for (const auto* reserved : api.reserved) {
        CHECK(reserved == nullptr);
    }

    sa_api_request_v1 old_request {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 old_api {};
    old_api.abi_version = SA_ABI_V1_2;
    old_api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    CHECK(sa_get_api_v1(&old_request, &old_api, nullptr) == SA_OK);
    CHECK(old_api.track_point_load_solve != nullptr);
    CHECK(old_api.nonlinear_static_solve == nullptr);
    CHECK((old_api.capabilities & SA_CAPABILITY_NONLINEAR_STATIC_CPU) == 0U);

    sa_api_request_v1 current_request {
        SA_ABI_V1_3,
        SA_API_REQUEST_V1_MIN_SIZE,
        0U,
        {0U, 0U, 0U},
    };
    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_3_MIN_SIZE> current_prefix {};
    auto* prefix_api = reinterpret_cast<sa_api_v1*>(current_prefix.data());
    prefix_api->abi_version = SA_ABI_V1_3;
    prefix_api->struct_size = SA_API_V1_3_MIN_SIZE;
    CHECK(sa_get_api_v1(&current_request, prefix_api, nullptr) == SA_OK);
    CHECK(prefix_api->nonlinear_static_solve != nullptr);

    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_2_MIN_SIZE> undersized {};
    auto* undersized_api = reinterpret_cast<sa_api_v1*>(undersized.data());
    undersized_api->abi_version = SA_ABI_V1_3;
    undersized_api->struct_size = SA_API_V1_2_MIN_SIZE;
    CHECK(sa_get_api_v1(&current_request, undersized_api, nullptr) == SA_ERR_STRUCT_SIZE);
    return true;
}

[[nodiscard]] bool caller_owned_output_matches_the_frozen_legacy_result() {
    const auto api = load_api();
    const auto cfg = config();
    Inputs values;
    const auto stiffness = input(values.stiffness.data());
    const auto height = input(values.height.data());
    const auto axial = input(values.axial.data());
    const auto yield_drift = input(values.yield_drift.data());
    const auto load = input(values.load.data());
    std::array<double, 3> displacement {};
    const auto displacement_view = output(displacement.data());
    auto result = result_descriptor();

    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_OK);
    constexpr std::array expected {
        0.0002400000000001004,
        0.000395555555555692,
        0.0004705555555556994,
    };
    CHECK(result.abi_version == SA_ABI_V1_3);
    CHECK(result.struct_size == sizeof(sa_nonlinear_static_result_v1));
    CHECK(result.converged == 1U);
    CHECK(result.iterations == 6U);
    CHECK(near(result.residual_inf, 6.79574441164732e-9));
    CHECK(near(result.residual_l2, 7.31922742469327e-9));
    CHECK(near(result.max_abs_displacement_m, 0.0004705555555556994));
    CHECK(near(result.top_displacement_m, 0.0004705555555556994));
    CHECK(near(result.base_shear_kn, 24.00000000001004));
    CHECK(result.plastic_story_count == 0U);
    CHECK(result.line_search_backtracks == 0U);
    CHECK(result.output_length == displacement.size());
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(result.reserved == 0U);
    for (std::size_t index = 0U; index < displacement.size(); ++index) {
        CHECK(near(displacement[index], expected[index]));
    }
    return true;
}

[[nodiscard]] bool invalid_and_nonconverged_calls_are_atomic() {
    const auto api = load_api();
    const auto valid_config = config();
    Inputs values;
    auto stiffness = input(values.stiffness.data());
    const auto height = input(values.height.data());
    const auto axial = input(values.axial.data());
    const auto yield_drift = input(values.yield_drift.data());
    const auto load = input(values.load.data());
    std::array<double, 3> displacement {41.0, 41.0, 41.0};
    auto displacement_view = output(displacement.data());
    auto result = result_descriptor();
    const auto before_displacement = displacement;
    const auto before_result = result;

    values.stiffness[1] = std::numeric_limits<double>::quiet_NaN();
    CHECK(api.nonlinear_static_solve(
              &valid_config,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(displacement == before_displacement);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);
    values.stiffness[1] = 9.0e7;

    auto nonconverged = config();
    nonconverged.max_iter = 1U;
    CHECK(api.nonlinear_static_solve(
              &nonconverged,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(displacement == before_displacement);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    stiffness.length = 2U;
    CHECK(api.nonlinear_static_solve(
              &valid_config,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(displacement == before_displacement);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool output_metadata_and_aliasing_fail_closed() {
    const auto api = load_api();
    const auto cfg = config();
    Inputs values;
    const auto stiffness = input(values.stiffness.data());
    const auto height = input(values.height.data());
    const auto axial = input(values.axial.data());
    const auto yield_drift = input(values.yield_drift.data());
    const auto load = input(values.load.data());
    std::array<double, 3> displacement {41.0, 41.0, 41.0};
    auto displacement_view = output(displacement.data());
    auto result = result_descriptor();
    const auto before_displacement = displacement;
    const auto before_result = result;

    displacement_view.length = 2U;
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(displacement == before_displacement);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    displacement_view = output(displacement.data());
    displacement_view.stride_bytes = sizeof(double) * 2U;
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    auto invalid_stiffness = stiffness;
    invalid_stiffness.stride_bytes = sizeof(double) * 2U;
    displacement_view = output(displacement.data());
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &invalid_stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    invalid_stiffness = stiffness;
    invalid_stiffness.data = reinterpret_cast<const void*>(
        std::numeric_limits<std::uintptr_t>::max() - 7U);
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &invalid_stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    displacement_view.data = reinterpret_cast<void*>(
        std::numeric_limits<std::uintptr_t>::max() - 7U);
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    displacement_view = output(values.stiffness.data());
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    displacement_view = output(reinterpret_cast<double*>(&result));
    CHECK(api.nonlinear_static_solve(
              &cfg,
              &stiffness,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    CHECK(api.nonlinear_static_solve(
              &cfg,
              nullptr,
              &height,
              &axial,
              &yield_drift,
              &load,
              &displacement_view,
              &result,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(displacement == before_displacement);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        v1_3_table_preserves_v1_2_and_exposes_one_new_operation,
        caller_owned_output_matches_the_frozen_legacy_result,
        invalid_and_nonconverged_calls_are_atomic,
        output_metadata_and_aliasing_fail_closed,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
