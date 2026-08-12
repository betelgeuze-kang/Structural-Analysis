#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace {

[[nodiscard]] sa_buffer_view_v1 input(
    const double* const values,
    const std::uint64_t length) {
    return {
        SA_ABI_V1_5,
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
[[nodiscard]] sa_mut_buffer_view_v1 state_view(
    std::array<Value, Length>& values,
    const std::uint64_t length,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_5,
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

extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* const data,
    const std::size_t size) {
    const sa_api_request_v1 request {
        SA_ABI_V1_5,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_5;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.nonlinear_ndtha_advance == nullptr) {
        return 0;
    }

    sa_nonlinear_ndtha_config_v1 config {};
    config.abi_version = SA_ABI_V1_5;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.story_count = 2U;
    config.step_count = 3U;
    config.dt_s = 0.01;
    config.newmark_beta = 0.25;
    config.newmark_gamma = 0.5;
    config.tolerance = 1.0e-5;
    config.max_step_iterations = 16U;
    config.adaptive_load_decay = 0.82;
    config.damping_force_cap_ratio = 0.6;
    config.newton_max_iter = 120U;
    config.line_search_decay = 0.5;
    config.line_search_min = 0.03125;
    config.hardening_ratio = 0.2;
    config.pdelta_factor = 1.0;
    config.collapse_drift_threshold_pct = 10.0;

    std::array<double, 2> stiffness {1.0e8, 9.0e7};
    std::array<double, 2> height {3.0, 3.0};
    std::array<double, 2> axial {1.0e6, 8.0e5};
    std::array<double, 2> yield_drift {0.02, 0.02};
    std::array<double, 2> mass {10'000.0, 8'000.0};
    std::array<double, 2> damping {1'000.0, 900.0};
    std::array<double, 2> floor_load {10'000.0, 8'000.0};
    std::array<double, 3> acceleration {0.0, 0.01, -0.005};
    sa_nonlinear_ndtha_inputs_v1 inputs {};
    inputs.abi_version = SA_ABI_V1_5;
    inputs.struct_size = static_cast<std::uint32_t>(sizeof(inputs));
    inputs.story_stiffness_n_per_m = input(stiffness.data(), stiffness.size());
    inputs.story_height_m = input(height.data(), height.size());
    inputs.story_axial_n = input(axial.data(), axial.size());
    inputs.story_yield_drift_m = input(yield_drift.data(), yield_drift.size());
    inputs.story_mass_kg = input(mass.data(), mass.size());
    inputs.story_damping_n_s_per_m = input(damping.data(), damping.size());
    inputs.floor_load_base_n = input(floor_load.data(), floor_load.size());
    inputs.acceleration_g = input(acceleration.data(), acceleration.size());

    std::array<double, 2> displacement {};
    std::array<double, 2> velocity {};
    std::array<double, 2> state_acceleration {};
    std::array<double, 3> top {};
    std::array<double, 3> drift {};
    std::array<double, 3> base_shear {};
    std::array<double, 3> core_drift {};
    std::array<double, 3> core_shear {};
    std::array<std::uint8_t, 3> step_converged {};
    std::array<std::uint32_t, 3> step_iterations {};
    std::array<std::uint32_t, 3> step_plastic {};
    std::array<double, 3> step_residual {};
    std::array<double, 2> drift_envelope {};
    std::array<double, 2> final_drift {};

    sa_nonlinear_ndtha_state_v1 state {};
    const auto scalar_bytes = offsetof(sa_nonlinear_ndtha_state_v1, displacement_m);
    const auto copied = size < scalar_bytes ? size : scalar_bytes;
    if (copied > 0U) {
        std::memcpy(&state, data, copied);
    }
    state.abi_version = SA_ABI_V1_5;
    state.struct_size = static_cast<std::uint32_t>(sizeof(state));
    state.displacement_m = state_view(displacement, displacement.size(), SA_ELEMENT_TYPE_F64);
    state.velocity_m_per_s = state_view(velocity, velocity.size(), SA_ELEMENT_TYPE_F64);
    state.acceleration_m_per_s2 =
        state_view(state_acceleration, state_acceleration.size(), SA_ELEMENT_TYPE_F64);
    state.response.abi_version = SA_ABI_V1_5;
    state.response.struct_size = static_cast<std::uint32_t>(sizeof(state.response));
    state.response.top_displacement_m = state_view(top, top.size(), SA_ELEMENT_TYPE_F64);
    state.response.drift_ratio_pct = state_view(drift, drift.size(), SA_ELEMENT_TYPE_F64);
    state.response.base_shear_kn =
        state_view(base_shear, base_shear.size(), SA_ELEMENT_TYPE_F64);
    state.response.core_drift_pct =
        state_view(core_drift, core_drift.size(), SA_ELEMENT_TYPE_F64);
    state.response.core_shear_kn =
        state_view(core_shear, core_shear.size(), SA_ELEMENT_TYPE_F64);
    state.response.step_converged =
        state_view(step_converged, step_converged.size(), SA_ELEMENT_TYPE_U8);
    state.response.step_iterations =
        state_view(step_iterations, step_iterations.size(), SA_ELEMENT_TYPE_U32);
    state.response.step_plastic_story_count =
        state_view(step_plastic, step_plastic.size(), SA_ELEMENT_TYPE_U32);
    state.response.step_residual_inf =
        state_view(step_residual, step_residual.size(), SA_ELEMENT_TYPE_F64);
    state.response.story_drift_envelope_pct =
        state_view(drift_envelope, drift_envelope.size(), SA_ELEMENT_TYPE_F64);
    state.response.final_story_drift_pct =
        state_view(final_drift, final_drift.size(), SA_ELEMENT_TYPE_F64);

    if (size > 0U && (data[0] & 1U) != 0U) {
        state.displacement_m.length = 1U;
    }
    if (size > 1U && (data[1] & 1U) != 0U) {
        state.velocity_m_per_s.data = state.displacement_m.data;
    }
    if (size > 2U && (data[2] & 1U) != 0U) {
        state.response.step_iterations.element_type = SA_ELEMENT_TYPE_F64;
    }
    if (size > 3U && (data[3] & 1U) != 0U) {
        state.response.top_displacement_m.data = stiffness.data();
    }

    std::array<char, 128> error_text {};
    sa_error_buffer_v1 error {
        SA_ABI_V1_5,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        error_text.data(),
        error_text.size(),
        0U,
    };
    const auto step_budget = size == 0U ? 0U : static_cast<std::uint32_t>(data[size - 1U] % 9U);
    static_cast<void>(api.nonlinear_ndtha_advance(
        &config, &inputs, step_budget, &state, &error));
    return 0;
}
