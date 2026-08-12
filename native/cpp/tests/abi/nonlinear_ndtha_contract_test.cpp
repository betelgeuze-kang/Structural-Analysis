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

[[nodiscard]] sa_api_v1 load_api(const std::uint32_t version = SA_ABI_V1_4) {
    const sa_api_request_v1 request {
        version,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] sa_nonlinear_ndtha_config_v1 config() {
    sa_nonlinear_ndtha_config_v1 value {};
    value.abi_version = SA_ABI_V1_4;
    value.struct_size = static_cast<std::uint32_t>(sizeof(value));
    value.story_count = 2U;
    value.step_count = 3U;
    value.dt_s = 0.01;
    value.newmark_beta = 0.25;
    value.newmark_gamma = 0.5;
    value.tolerance = 1.0e-5;
    value.max_step_iterations = 16U;
    value.adaptive_load_decay = 0.82;
    value.damping_force_cap_ratio = 0.6;
    value.newton_max_iter = 120U;
    value.line_search_decay = 0.5;
    value.line_search_min = 0.03125;
    value.hardening_ratio = 0.2;
    value.pdelta_factor = 1.0;
    value.collapse_drift_threshold_pct = 10.0;
    return value;
}

[[nodiscard]] sa_buffer_view_v1 input_view(
    const double* const data,
    const std::uint64_t length) {
    return {
        SA_ABI_V1_4,
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

template <typename Value, std::size_t Length>
[[nodiscard]] sa_mut_buffer_view_v1 output_view(
    std::array<Value, Length>& values,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_4,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

struct InputStorage {
    std::array<double, 2> stiffness {1.0e8, 9.0e7};
    std::array<double, 2> height {3.0, 3.0};
    std::array<double, 2> axial {1.0e6, 8.0e5};
    std::array<double, 2> yield_drift {0.02, 0.02};
    std::array<double, 2> mass {10'000.0, 8'000.0};
    std::array<double, 2> damping {1'000.0, 900.0};
    std::array<double, 2> floor_load {10'000.0, 8'000.0};
    std::array<double, 3> acceleration {0.0, 0.01, -0.005};
};

[[nodiscard]] sa_nonlinear_ndtha_inputs_v1 inputs(InputStorage& storage) {
    sa_nonlinear_ndtha_inputs_v1 value {};
    value.abi_version = SA_ABI_V1_4;
    value.struct_size = static_cast<std::uint32_t>(sizeof(value));
    value.story_stiffness_n_per_m = input_view(storage.stiffness.data(), 2U);
    value.story_height_m = input_view(storage.height.data(), 2U);
    value.story_axial_n = input_view(storage.axial.data(), 2U);
    value.story_yield_drift_m = input_view(storage.yield_drift.data(), 2U);
    value.story_mass_kg = input_view(storage.mass.data(), 2U);
    value.story_damping_n_s_per_m = input_view(storage.damping.data(), 2U);
    value.floor_load_base_n = input_view(storage.floor_load.data(), 2U);
    value.acceleration_g = input_view(storage.acceleration.data(), 3U);
    return value;
}

struct OutputStorage {
    std::array<double, 3> top_displacement_m {41.0, 41.0, 41.0};
    std::array<double, 3> drift_ratio_pct {42.0, 42.0, 42.0};
    std::array<double, 3> base_shear_kn {43.0, 43.0, 43.0};
    std::array<double, 3> core_drift_pct {44.0, 44.0, 44.0};
    std::array<double, 3> core_shear_kn {45.0, 45.0, 45.0};
    std::array<std::uint8_t, 3> step_converged {46U, 46U, 46U};
    std::array<std::uint32_t, 3> step_iterations {47U, 47U, 47U};
    std::array<std::uint32_t, 3> step_plastic_story_count {48U, 48U, 48U};
    std::array<double, 3> step_residual_inf {49.0, 49.0, 49.0};
    std::array<double, 2> story_drift_envelope_pct {50.0, 50.0};
    std::array<double, 2> final_story_drift_pct {51.0, 51.0};

    [[nodiscard]] bool operator==(const OutputStorage&) const = default;
};

[[nodiscard]] sa_nonlinear_ndtha_outputs_v1 outputs(OutputStorage& storage) {
    sa_nonlinear_ndtha_outputs_v1 value {};
    value.abi_version = SA_ABI_V1_4;
    value.struct_size = static_cast<std::uint32_t>(sizeof(value));
    value.top_displacement_m = output_view(storage.top_displacement_m, SA_ELEMENT_TYPE_F64);
    value.drift_ratio_pct = output_view(storage.drift_ratio_pct, SA_ELEMENT_TYPE_F64);
    value.base_shear_kn = output_view(storage.base_shear_kn, SA_ELEMENT_TYPE_F64);
    value.core_drift_pct = output_view(storage.core_drift_pct, SA_ELEMENT_TYPE_F64);
    value.core_shear_kn = output_view(storage.core_shear_kn, SA_ELEMENT_TYPE_F64);
    value.step_converged = output_view(storage.step_converged, SA_ELEMENT_TYPE_U8);
    value.step_iterations = output_view(storage.step_iterations, SA_ELEMENT_TYPE_U32);
    value.step_plastic_story_count =
        output_view(storage.step_plastic_story_count, SA_ELEMENT_TYPE_U32);
    value.step_residual_inf = output_view(storage.step_residual_inf, SA_ELEMENT_TYPE_F64);
    value.story_drift_envelope_pct =
        output_view(storage.story_drift_envelope_pct, SA_ELEMENT_TYPE_F64);
    value.final_story_drift_pct =
        output_view(storage.final_story_drift_pct, SA_ELEMENT_TYPE_F64);
    return value;
}

[[nodiscard]] sa_nonlinear_ndtha_result_v1 result_descriptor() {
    sa_nonlinear_ndtha_result_v1 value {};
    value.abi_version = SA_ABI_V1_4;
    value.struct_size = static_cast<std::uint32_t>(sizeof(value));
    value.collapse_step = std::numeric_limits<std::int32_t>::min();
    value.fallback_count = std::numeric_limits<std::uint32_t>::max();
    value.reserved[0] = UINT64_C(0xA5A5A5A5A5A5A5A5);
    value.reserved[1] = UINT64_C(0x5A5A5A5A5A5A5A5A);
    return value;
}

[[nodiscard]] bool v1_4_table_preserves_every_older_prefix() {
    const auto api = load_api();
    CHECK(api.abi_version == SA_ABI_V1_4);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.capabilities
          == (SA_CAPABILITY_BUFFER_VALIDATION | SA_CAPABILITY_MODEL_IR_V2_TYPED
              | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT | SA_CAPABILITY_TRACK_POINT_LOAD_CPU
              | SA_CAPABILITY_NONLINEAR_STATIC_CPU | SA_CAPABILITY_NONLINEAR_NDTHA_CPU));
    CHECK(api.track_point_load_solve != nullptr);
    CHECK(api.nonlinear_static_solve != nullptr);
    CHECK(api.nonlinear_ndtha_solve != nullptr);
    for (const auto* reserved : api.reserved) {
        CHECK(reserved == nullptr);
    }

    const auto old = load_api(SA_ABI_V1_3);
    CHECK(old.abi_version == SA_ABI_V1_3);
    CHECK(old.nonlinear_static_solve != nullptr);
    CHECK(old.nonlinear_ndtha_solve == nullptr);
    CHECK((old.capabilities & SA_CAPABILITY_NONLINEAR_NDTHA_CPU) == 0U);

    const sa_api_request_v1 request {
        SA_ABI_V1_4,
        SA_API_REQUEST_V1_MIN_SIZE,
        0U,
        {0U, 0U, 0U},
    };
    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_4_MIN_SIZE> prefix {};
    auto* prefix_api = reinterpret_cast<sa_api_v1*>(prefix.data());
    prefix_api->abi_version = SA_ABI_V1_4;
    prefix_api->struct_size = SA_API_V1_4_MIN_SIZE;
    CHECK(sa_get_api_v1(&request, prefix_api, nullptr) == SA_OK);
    CHECK(prefix_api->nonlinear_ndtha_solve != nullptr);

    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_3_MIN_SIZE> undersized {};
    auto* undersized_api = reinterpret_cast<sa_api_v1*>(undersized.data());
    undersized_api->abi_version = SA_ABI_V1_4;
    undersized_api->struct_size = SA_API_V1_3_MIN_SIZE;
    CHECK(sa_get_api_v1(&request, undersized_api, nullptr) == SA_ERR_STRUCT_SIZE);
    return true;
}

[[nodiscard]] bool caller_owned_outputs_match_the_frozen_legacy_case() {
    const auto api = load_api();
    const auto cfg = config();
    InputStorage input_storage;
    const auto input_descriptors = inputs(input_storage);
    OutputStorage output_storage;
    const auto output_descriptors = outputs(output_storage);
    auto result = result_descriptor();
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_OK);

    constexpr std::array expected_top {
        4.084273705964167e-7,
        2.008674095445957e-6,
        3.795754248884991e-6,
    };
    constexpr std::array expected_drift {
        1.1677310711126211e-5,
        5.301851826285648e-5,
        8.560401406754784e-5,
    };
    constexpr std::array expected_base_shear {
        0.035031932133378636,
        0.15905555478856942,
        0.2568120422026436,
    };
    constexpr std::array expected_residual {
        9.752318419486983e-8,
        2.736757522825428e-7,
        4.408786935528042e-8,
    };
    constexpr std::array expected_story_drift {
        8.560401406754784e-5,
        4.0921127561951836e-5,
    };
    CHECK(result.abi_version == SA_ABI_V1_4);
    CHECK(result.struct_size == sizeof(sa_nonlinear_ndtha_result_v1));
    CHECK(result.converged_all_steps == 1U);
    CHECK(result.collapsed == 0U);
    CHECK(result.collapse_step == -1);
    CHECK(result.step_count_completed == 3U);
    CHECK(result.max_plastic_story_count == 0U);
    CHECK(result.total_line_search_backtracks == 0U);
    CHECK(result.output_story_count == 2U);
    CHECK(result.output_step_count == 3U);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(result.reserved[0] == 0U && result.reserved[1] == 0U);
    CHECK(near(result.max_drift_ratio_pct, 8.560401406754784e-5));
    CHECK(near(result.avg_step_iterations, 1.0));
    CHECK(near(result.residual_top_displacement_m, 3.795754248884991e-6));
    CHECK(near(result.residual_drift_ratio_pct, 8.560401406754784e-5));
    for (std::size_t index = 0U; index < expected_top.size(); ++index) {
        CHECK(near(output_storage.top_displacement_m[index], expected_top[index]));
        CHECK(near(output_storage.drift_ratio_pct[index], expected_drift[index]));
        CHECK(near(output_storage.base_shear_kn[index], expected_base_shear[index]));
        CHECK(near(output_storage.core_drift_pct[index], expected_drift[index]));
        CHECK(near(output_storage.core_shear_kn[index], expected_base_shear[index]));
        CHECK(output_storage.step_converged[index] == 1U);
        CHECK(output_storage.step_iterations[index] == 1U);
        CHECK(output_storage.step_plastic_story_count[index] == 0U);
        CHECK(near(output_storage.step_residual_inf[index], expected_residual[index]));
    }
    for (std::size_t index = 0U; index < expected_story_drift.size(); ++index) {
        CHECK(near(
            output_storage.story_drift_envelope_pct[index], expected_story_drift[index]));
        CHECK(near(output_storage.final_story_drift_pct[index], expected_story_drift[index]));
    }
    return true;
}

[[nodiscard]] bool invalid_and_nonconverged_calls_are_failure_atomic() {
    const auto api = load_api();
    const auto valid_config = config();
    InputStorage input_storage;
    auto input_descriptors = inputs(input_storage);
    OutputStorage output_storage;
    auto output_descriptors = outputs(output_storage);
    auto result = result_descriptor();
    const auto original_outputs = output_storage;
    const auto original_result = result;

    input_storage.stiffness[1] = std::numeric_limits<double>::quiet_NaN();
    CHECK(api.nonlinear_ndtha_solve(
              &valid_config, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(output_storage == original_outputs);
    CHECK(std::memcmp(&result, &original_result, sizeof(result)) == 0);
    input_storage.stiffness[1] = 9.0e7;

    auto nonconverged = valid_config;
    nonconverged.max_step_iterations = 1U;
    nonconverged.newton_max_iter = 1U;
    nonconverged.tolerance = 1.0e-30;
    CHECK(api.nonlinear_ndtha_solve(
              &nonconverged, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(output_storage == original_outputs);
    CHECK(std::memcmp(&result, &original_result, sizeof(result)) == 0);

    input_descriptors.acceleration_g.length = 2U;
    CHECK(api.nonlinear_ndtha_solve(
              &valid_config, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(output_storage == original_outputs);
    CHECK(std::memcmp(&result, &original_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool output_metadata_and_aliasing_fail_closed() {
    const auto api = load_api();
    const auto cfg = config();
    InputStorage input_storage;
    const auto input_descriptors = inputs(input_storage);
    OutputStorage output_storage;
    auto output_descriptors = outputs(output_storage);
    auto result = result_descriptor();
    const auto original_outputs = output_storage;
    const auto original_result = result;

    output_descriptors.top_displacement_m.length = 2U;
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(output_storage == original_outputs);

    output_descriptors = outputs(output_storage);
    output_descriptors.step_iterations.element_type = SA_ELEMENT_TYPE_F64;
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    output_descriptors = outputs(output_storage);
    output_descriptors.drift_ratio_pct.data = output_descriptors.top_displacement_m.data;
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    output_descriptors = outputs(output_storage);
    output_descriptors.top_displacement_m.data = input_storage.stiffness.data();
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(output_storage == original_outputs);
    CHECK(std::memcmp(&result, &original_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool physical_collapse_returns_a_complete_terminal_result() {
    const auto api = load_api();
    auto cfg = config();
    cfg.collapse_drift_threshold_pct = 1.0e-6;
    InputStorage input_storage;
    const auto input_descriptors = inputs(input_storage);
    OutputStorage output_storage;
    const auto output_descriptors = outputs(output_storage);
    auto result = result_descriptor();
    CHECK(api.nonlinear_ndtha_solve(
              &cfg, &input_descriptors, &output_descriptors, &result, nullptr)
          == SA_OK);
    CHECK(result.converged_all_steps == 0U);
    CHECK(result.collapsed == 1U);
    CHECK(result.collapse_step == 0);
    CHECK(result.step_count_completed == 1U);
    CHECK(near(result.collapse_drift_ratio_pct, 1.1677310711126211e-5));
    CHECK(near(result.collapse_top_displacement_m, 4.084273705964167e-7));
    CHECK(output_storage.step_converged[0] == 1U);
    CHECK(output_storage.step_converged[1] == 0U);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        v1_4_table_preserves_every_older_prefix,
        caller_owned_outputs_match_the_frozen_legacy_case,
        invalid_and_nonconverged_calls_are_failure_atomic,
        output_metadata_and_aliasing_fail_closed,
        physical_collapse_returns_a_complete_terminal_result,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
