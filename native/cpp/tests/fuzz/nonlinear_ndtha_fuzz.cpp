#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace {

[[nodiscard]] sa_buffer_view_v1 input(const double* const values, const std::uint64_t length) {
    return {
        SA_ABI_V1_4,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values,
        length,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

template <typename Value, std::size_t Length>
[[nodiscard]] sa_mut_buffer_view_v1 output(
    std::array<Value, Length>& values,
    const std::uint64_t length,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_4,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.data(),
        length,
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

} // namespace

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* const data, const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_4,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_4;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.nonlinear_ndtha_solve == nullptr) {
        return 0;
    }

    sa_nonlinear_ndtha_config_v1 config {};
    config.abi_version = SA_ABI_V1_4;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.story_count = 2U;
    config.step_count = 3U;
    config.dt_s = 0.01;
    config.newmark_beta = 0.25;
    config.newmark_gamma = 0.5;
    config.tolerance = 1.0e-5;
    config.max_step_iterations = 4U;
    config.adaptive_load_decay = 0.82;
    config.damping_force_cap_ratio = 0.6;
    config.newton_max_iter = 8U;
    config.line_search_decay = 0.5;
    config.line_search_min = 0.03125;
    config.hardening_ratio = 0.2;
    config.pdelta_factor = 1.0;
    config.collapse_drift_threshold_pct = 10.0;
    const auto copied = size < sizeof(config) ? size : sizeof(config);
    if (copied > 0U) {
        std::memcpy(&config, data, copied);
    }
    config.abi_version = SA_ABI_V1_4;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.story_count = 1U + config.story_count % 8U;
    config.step_count = 1U + config.step_count % 8U;
    config.max_step_iterations = 1U + config.max_step_iterations % 4U;
    config.newton_max_iter = 1U + config.newton_max_iter % 8U;
    config.reserved_iteration_u32 = 0U;
    config.reserved_newton_u32 = 0U;
    config.flags = 0U;
    config.reserved_u32 = 0U;
    config.reserved[0] = 0U;
    config.reserved[1] = 0U;

    std::array<double, 8> stiffness {};
    std::array<double, 8> height {};
    std::array<double, 8> axial {};
    std::array<double, 8> yield_drift {};
    std::array<double, 8> mass {};
    std::array<double, 8> damping {};
    std::array<double, 8> floor_load {};
    std::array<double, 8> acceleration {};
    for (std::size_t index = 0U; index < stiffness.size(); ++index) {
        stiffness[index] = 1.0e8 - static_cast<double>(index) * 1.0e6;
        height[index] = 3.0;
        axial[index] = 1.0e6;
        yield_drift[index] = 0.02;
        mass[index] = 10'000.0;
        damping[index] = 1'000.0;
        floor_load[index] = 10'000.0;
        acceleration[index] = index % 2U == 0U ? 0.01 : -0.005;
    }
    sa_nonlinear_ndtha_inputs_v1 inputs {};
    inputs.abi_version = SA_ABI_V1_4;
    inputs.struct_size = static_cast<std::uint32_t>(sizeof(inputs));
    inputs.story_stiffness_n_per_m = input(stiffness.data(), config.story_count);
    inputs.story_height_m = input(height.data(), config.story_count);
    inputs.story_axial_n = input(axial.data(), config.story_count);
    inputs.story_yield_drift_m = input(yield_drift.data(), config.story_count);
    inputs.story_mass_kg = input(mass.data(), config.story_count);
    inputs.story_damping_n_s_per_m = input(damping.data(), config.story_count);
    inputs.floor_load_base_n = input(floor_load.data(), config.story_count);
    inputs.acceleration_g = input(acceleration.data(), config.step_count);

    std::array<double, 8> top {};
    std::array<double, 8> drift {};
    std::array<double, 8> base_shear {};
    std::array<double, 8> core_drift {};
    std::array<double, 8> core_shear {};
    std::array<std::uint8_t, 8> step_converged {};
    std::array<std::uint32_t, 8> step_iterations {};
    std::array<std::uint32_t, 8> step_plastic {};
    std::array<double, 8> step_residual {};
    std::array<double, 8> drift_envelope {};
    std::array<double, 8> final_drift {};
    sa_nonlinear_ndtha_outputs_v1 outputs {};
    outputs.abi_version = SA_ABI_V1_4;
    outputs.struct_size = static_cast<std::uint32_t>(sizeof(outputs));
    outputs.top_displacement_m = output(top, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.drift_ratio_pct = output(drift, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.base_shear_kn = output(base_shear, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.core_drift_pct = output(core_drift, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.core_shear_kn = output(core_shear, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.step_converged = output(step_converged, config.step_count, SA_ELEMENT_TYPE_U8);
    outputs.step_iterations = output(step_iterations, config.step_count, SA_ELEMENT_TYPE_U32);
    outputs.step_plastic_story_count =
        output(step_plastic, config.step_count, SA_ELEMENT_TYPE_U32);
    outputs.step_residual_inf = output(step_residual, config.step_count, SA_ELEMENT_TYPE_F64);
    outputs.story_drift_envelope_pct =
        output(drift_envelope, config.story_count, SA_ELEMENT_TYPE_F64);
    outputs.final_story_drift_pct =
        output(final_drift, config.story_count, SA_ELEMENT_TYPE_F64);

    if (size > 0U && (data[0] & 1U) != 0U) {
        inputs.acceleration_g.length = config.step_count - 1U;
    }
    if (size > 1U && (data[1] & 1U) != 0U) {
        outputs.step_iterations.element_type = SA_ELEMENT_TYPE_F64;
    }
    if (size > 2U && (data[2] & 1U) != 0U) {
        outputs.drift_ratio_pct.data = outputs.top_displacement_m.data;
    }
    if (size > 3U && (data[3] & 1U) != 0U) {
        outputs.top_displacement_m.data = stiffness.data();
    }

    sa_nonlinear_ndtha_result_v1 result {};
    result.abi_version = SA_ABI_V1_4;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    std::array<char, 128> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_4,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    static_cast<void>(api.nonlinear_ndtha_solve(
        &config, &inputs, &outputs, &result, &error));
    return 0;
}
