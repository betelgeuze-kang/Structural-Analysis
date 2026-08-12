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

[[nodiscard]] sa_api_v1 load_track_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_2,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_2;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] sa_track_point_load_config_v1 config() {
    return {
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
}

[[nodiscard]] sa_mut_buffer_view_v1 output(double* const data, const std::uint64_t length) {
    return {
        SA_ABI_V1_2,
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

[[nodiscard]] sa_track_point_load_result_v1 result_descriptor() {
    sa_track_point_load_result_v1 result {};
    result.abi_version = SA_ABI_V1_2;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    result.reserved = UINT64_C(0xA5A5A5A5A5A5A5A5);
    return result;
}

[[nodiscard]] bool v1_2_table_preserves_older_prefixes_and_exposes_one_cpu_operation() {
    const auto api = load_track_api();
    CHECK(api.abi_version == SA_ABI_V1_2);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.capabilities
          == (SA_CAPABILITY_BUFFER_VALIDATION | SA_CAPABILITY_MODEL_IR_V2_TYPED
              | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT | SA_CAPABILITY_TRACK_POINT_LOAD_CPU));
    CHECK(api.validate_buffer_view != nullptr);
    CHECK(api.model_ir_create != nullptr);
    CHECK(api.track_point_load_solve != nullptr);
    CHECK(api.nonlinear_static_solve == nullptr);
    for (const auto* reserved : api.reserved) {
        CHECK(reserved == nullptr);
    }

    sa_api_request_v1 old_request {
        SA_ABI_V1_1,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 old_api {};
    old_api.abi_version = SA_ABI_V1_1;
    old_api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    CHECK(sa_get_api_v1(&old_request, &old_api, nullptr) == SA_OK);
    CHECK(old_api.track_point_load_solve == nullptr);
    CHECK(old_api.nonlinear_static_solve == nullptr);
    CHECK((old_api.capabilities & SA_CAPABILITY_TRACK_POINT_LOAD_CPU) == 0U);

    alignas(sa_api_v1) std::array<std::byte, 128> legacy_storage {};
    constexpr std::uint32_t legacy_version = SA_ABI_V1_1;
    constexpr std::uint32_t legacy_size = 128U;
    std::memcpy(legacy_storage.data(), &legacy_version, sizeof(legacy_version));
    std::memcpy(
        legacy_storage.data() + offsetof(sa_api_v1, struct_size),
        &legacy_size,
        sizeof(legacy_size));
    CHECK(sa_get_api_v1(
              &old_request,
              reinterpret_cast<sa_api_v1*>(legacy_storage.data()),
              nullptr)
          == SA_OK);
    std::array<const void*, 7> legacy_reserved {};
    std::memcpy(
        legacy_reserved.data(),
        legacy_storage.data() + 72U,
        sizeof(legacy_reserved));
    for (const auto* reserved : legacy_reserved) {
        CHECK(reserved == nullptr);
    }

    sa_api_request_v1 current_request {
        SA_ABI_V1_2,
        SA_API_REQUEST_V1_MIN_SIZE,
        0U,
        {0U, 0U, 0U},
    };
    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_2_MIN_SIZE> current_prefix {};
    auto* current_prefix_api = reinterpret_cast<sa_api_v1*>(current_prefix.data());
    current_prefix_api->abi_version = SA_ABI_V1_2;
    current_prefix_api->struct_size = SA_API_V1_2_MIN_SIZE;
    CHECK(sa_get_api_v1(&current_request, current_prefix_api, nullptr) == SA_OK);
    CHECK(current_prefix_api->track_point_load_solve != nullptr);

    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_1_MIN_SIZE> undersized {};
    auto* undersized_api = reinterpret_cast<sa_api_v1*>(undersized.data());
    undersized_api->abi_version = SA_ABI_V1_2;
    undersized_api->struct_size = SA_API_V1_1_MIN_SIZE;
    CHECK(sa_get_api_v1(&current_request, undersized_api, nullptr) == SA_ERR_STRUCT_SIZE);
    return true;
}

[[nodiscard]] bool caller_owned_outputs_match_the_python_c1_product_golden() {
    const auto api = load_track_api();
    auto input = config();
    std::array<double, 9> displacement {};
    std::array<double, 9> rotation {};
    const auto displacement_view = output(displacement.data(), displacement.size());
    const auto rotation_view = output(rotation.data(), rotation.size());
    auto result = result_descriptor();

    CHECK(api.track_point_load_solve(
              &input, &displacement_view, &rotation_view, &result, nullptr)
          == SA_OK);
    constexpr std::array expected_displacement {
        0.0,
        -0.0007037926926320691,
        -0.001321670876610801,
        -0.00176598837526238,
        -0.001945845157517316,
        -0.0017659883752623807,
        -0.0013216708766108014,
        -0.0007037926926320691,
        0.0,
    };
    constexpr std::array expected_rotation {
        -0.0005630341541056552,
        -0.0005286683506443204,
        -0.0004248782730521244,
        -0.00024966971236260597,
        -2.6020852139652105e-19,
        0.0002496697123626058,
        0.00042487827305212465,
        0.0005286683506443206,
        0.0005630341541056552,
    };
    CHECK(result.abi_version == SA_ABI_V1_2);
    CHECK(result.struct_size == sizeof(sa_track_point_load_result_v1));
    CHECK(result.converged == 1U);
    CHECK(result.iterations == 4U);
    CHECK(near(result.residual_inf, 7.657748132248844e-10));
    CHECK(near(result.max_abs_displacement_m, 0.001945845157517316));
    CHECK(near(result.mid_displacement_m, -0.001945845157517316));
    CHECK(result.output_length == displacement.size());
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(result.reserved == 0U);
    for (std::size_t index = 0U; index < displacement.size(); ++index) {
        CHECK(near(displacement[index], expected_displacement[index]));
        CHECK(near(rotation[index], expected_rotation[index]));
    }
    return true;
}

[[nodiscard]] bool invalid_and_nonconverged_calls_leave_all_outputs_unchanged() {
    const auto api = load_track_api();
    std::array<double, 9> displacement {};
    std::array<double, 9> rotation {};
    displacement.fill(41.0);
    rotation.fill(42.0);
    const auto displacement_view = output(displacement.data(), displacement.size());
    const auto rotation_view = output(rotation.data(), rotation.size());
    auto result = result_descriptor();
    const auto before_displacement = displacement;
    const auto before_rotation = rotation;
    const auto before_result = result;

    auto invalid = config();
    invalid.length_m = std::numeric_limits<double>::quiet_NaN();
    CHECK(api.track_point_load_solve(
              &invalid, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(displacement == before_displacement);
    CHECK(rotation == before_rotation);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    auto oversized = config();
    oversized.node_count = SA_TRACK_POINT_LOAD_MAX_NODE_COUNT + 1U;
    CHECK(api.track_point_load_solve(
              &oversized, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(displacement == before_displacement);
    CHECK(rotation == before_rotation);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    auto nonconverged = config();
    nonconverged.cg_max_iter = 1U;
    CHECK(api.track_point_load_solve(
              &nonconverged, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(displacement == before_displacement);
    CHECK(rotation == before_rotation);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);

    auto overflowed_norm = config();
    overflowed_norm.point_force_n = std::numeric_limits<double>::max();
    overflowed_norm.tolerance = std::numeric_limits<double>::max();
    CHECK(api.track_point_load_solve(
              &overflowed_norm, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(displacement == before_displacement);
    CHECK(rotation == before_rotation);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool output_metadata_and_aliasing_fail_closed() {
    const auto api = load_track_api();
    const auto input = config();
    std::array<double, 9> first {};
    std::array<double, 9> second {};
    auto displacement_view = output(first.data(), first.size());
    auto rotation_view = output(second.data(), second.size());
    auto result = result_descriptor();

    displacement_view.length = 8U;
    CHECK(api.track_point_load_solve(
              &input, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);

    displacement_view = output(first.data(), first.size());
    rotation_view = output(first.data(), first.size());
    CHECK(api.track_point_load_solve(
              &input, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    rotation_view = output(second.data(), second.size());
    displacement_view.stride_bytes = sizeof(double) * 2U;
    CHECK(api.track_point_load_solve(
              &input, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    const auto before_result = result;
    displacement_view = output(reinterpret_cast<double*>(&result), first.size());
    CHECK(api.track_point_load_solve(
              &input, &displacement_view, &rotation_view, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&result, &before_result, sizeof(result)) == 0);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        v1_2_table_preserves_older_prefixes_and_exposes_one_cpu_operation,
        caller_owned_outputs_match_the_python_c1_product_golden,
        invalid_and_nonconverged_calls_leave_all_outputs_unchanged,
        output_metadata_and_aliasing_fail_closed,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
