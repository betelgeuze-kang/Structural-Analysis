#include <structural/abi_v1.h>

#include <stddef.h>

int main(void) {
    const sa_api_request_v1 request = {
        SA_ABI_V1_4,
        (uint32_t)sizeof(sa_api_request_v1),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api = {0};
    api.abi_version = SA_ABI_V1_4;
    api.struct_size = (uint32_t)sizeof(sa_api_v1);
    if (sa_get_api_v1(&request, &api, NULL) != SA_OK
        || api.track_point_load_solve == NULL
        || api.nonlinear_static_solve == NULL
        || api.nonlinear_ndtha_solve == NULL
        || (api.capabilities & SA_CAPABILITY_TRACK_POINT_LOAD_CPU) == 0U
        || (api.capabilities & SA_CAPABILITY_NONLINEAR_STATIC_CPU) == 0U
        || (api.capabilities & SA_CAPABILITY_NONLINEAR_NDTHA_CPU) == 0U) {
        return 1;
    }

    const sa_track_point_load_config_v1 config = {
        SA_ABI_V1_2,
        (uint32_t)sizeof(sa_track_point_load_config_v1),
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
        -10000.0,
        5.0,
        {0U, 0U},
    };
    double displacement[9] = {0.0};
    double rotation[9] = {0.0};
    const sa_mut_buffer_view_v1 displacement_view = {
        SA_ABI_V1_2,
        (uint32_t)sizeof(sa_mut_buffer_view_v1),
        displacement,
        9U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    const sa_mut_buffer_view_v1 rotation_view = {
        SA_ABI_V1_2,
        (uint32_t)sizeof(sa_mut_buffer_view_v1),
        rotation,
        9U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_track_point_load_result_v1 result = {0};
    result.abi_version = SA_ABI_V1_2;
    result.struct_size = (uint32_t)sizeof(result);
    if (api.track_point_load_solve(
            &config,
            &displacement_view,
            &rotation_view,
            &result,
            NULL)
        != SA_OK) {
        return 1;
    }
    if (result.converged != 1U || result.fallback_count != 0U
        || result.execution_backend != SA_EXECUTION_BACKEND_CPU) {
        return 1;
    }

    const sa_nonlinear_static_config_v1 nonlinear_config = {
        SA_ABI_V1_3,
        (uint32_t)sizeof(sa_nonlinear_static_config_v1),
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
    const double stiffness[3] = {1.0e8, 9.0e7, 8.0e7};
    const double height[3] = {3.0, 3.0, 3.0};
    const double axial[3] = {1.0e6, 8.0e5, 6.0e5};
    const double yield_drift[3] = {0.02, 0.02, 0.02};
    const double load[3] = {10000.0, 8000.0, 6000.0};
    const sa_buffer_view_v1 stiffness_view = {
        SA_ABI_V1_3,
        (uint32_t)sizeof(sa_buffer_view_v1),
        stiffness,
        3U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_buffer_view_v1 height_view = stiffness_view;
    sa_buffer_view_v1 axial_view = stiffness_view;
    sa_buffer_view_v1 yield_view = stiffness_view;
    sa_buffer_view_v1 load_view = stiffness_view;
    height_view.data = height;
    axial_view.data = axial;
    yield_view.data = yield_drift;
    load_view.data = load;
    double story_displacement[3] = {0.0};
    const sa_mut_buffer_view_v1 story_displacement_view = {
        SA_ABI_V1_3,
        (uint32_t)sizeof(sa_mut_buffer_view_v1),
        story_displacement,
        3U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_nonlinear_static_result_v1 nonlinear_result = {0};
    nonlinear_result.abi_version = SA_ABI_V1_3;
    nonlinear_result.struct_size = (uint32_t)sizeof(nonlinear_result);
    if (api.nonlinear_static_solve(
            &nonlinear_config,
            &stiffness_view,
            &height_view,
            &axial_view,
            &yield_view,
            &load_view,
            &story_displacement_view,
            &nonlinear_result,
            NULL)
        != SA_OK) {
        return 1;
    }
    if (nonlinear_result.converged != 1U || nonlinear_result.fallback_count != 0U
        || nonlinear_result.execution_backend != SA_EXECUTION_BACKEND_CPU) {
        return 1;
    }

    sa_nonlinear_ndtha_config_v1 ndtha_config = {0};
    ndtha_config.abi_version = SA_ABI_V1_4;
    ndtha_config.struct_size = (uint32_t)sizeof(ndtha_config);
    ndtha_config.story_count = 2U;
    ndtha_config.step_count = 3U;
    ndtha_config.dt_s = 0.01;
    ndtha_config.newmark_beta = 0.25;
    ndtha_config.newmark_gamma = 0.5;
    ndtha_config.tolerance = 1.0e-5;
    ndtha_config.max_step_iterations = 16U;
    ndtha_config.adaptive_load_decay = 0.82;
    ndtha_config.damping_force_cap_ratio = 0.6;
    ndtha_config.newton_max_iter = 120U;
    ndtha_config.line_search_decay = 0.5;
    ndtha_config.line_search_min = 0.03125;
    ndtha_config.hardening_ratio = 0.2;
    ndtha_config.pdelta_factor = 1.0;
    ndtha_config.collapse_drift_threshold_pct = 10.0;

    const double ndtha_stiffness[2] = {1.0e8, 9.0e7};
    const double ndtha_height[2] = {3.0, 3.0};
    const double ndtha_axial[2] = {1.0e6, 8.0e5};
    const double ndtha_yield[2] = {0.02, 0.02};
    const double ndtha_mass[2] = {10000.0, 8000.0};
    const double ndtha_damping[2] = {1000.0, 900.0};
    const double ndtha_load[2] = {10000.0, 8000.0};
    const double ndtha_acceleration[3] = {0.0, 0.01, -0.005};
    const sa_buffer_view_v1 ndtha_story_input = {
        SA_ABI_V1_4,
        (uint32_t)sizeof(sa_buffer_view_v1),
        ndtha_stiffness,
        2U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_nonlinear_ndtha_inputs_v1 ndtha_inputs = {0};
    ndtha_inputs.abi_version = SA_ABI_V1_4;
    ndtha_inputs.struct_size = (uint32_t)sizeof(ndtha_inputs);
    ndtha_inputs.story_stiffness_n_per_m = ndtha_story_input;
    ndtha_inputs.story_height_m = ndtha_story_input;
    ndtha_inputs.story_height_m.data = ndtha_height;
    ndtha_inputs.story_axial_n = ndtha_story_input;
    ndtha_inputs.story_axial_n.data = ndtha_axial;
    ndtha_inputs.story_yield_drift_m = ndtha_story_input;
    ndtha_inputs.story_yield_drift_m.data = ndtha_yield;
    ndtha_inputs.story_mass_kg = ndtha_story_input;
    ndtha_inputs.story_mass_kg.data = ndtha_mass;
    ndtha_inputs.story_damping_n_s_per_m = ndtha_story_input;
    ndtha_inputs.story_damping_n_s_per_m.data = ndtha_damping;
    ndtha_inputs.floor_load_base_n = ndtha_story_input;
    ndtha_inputs.floor_load_base_n.data = ndtha_load;
    ndtha_inputs.acceleration_g = ndtha_story_input;
    ndtha_inputs.acceleration_g.data = ndtha_acceleration;
    ndtha_inputs.acceleration_g.length = 3U;

    double ndtha_top[3] = {0.0};
    double ndtha_drift[3] = {0.0};
    double ndtha_base_shear[3] = {0.0};
    double ndtha_core_drift[3] = {0.0};
    double ndtha_core_shear[3] = {0.0};
    uint8_t ndtha_step_converged[3] = {0U};
    uint32_t ndtha_step_iterations[3] = {0U};
    uint32_t ndtha_step_plastic[3] = {0U};
    double ndtha_step_residual[3] = {0.0};
    double ndtha_drift_envelope[2] = {0.0};
    double ndtha_final_drift[2] = {0.0};
    const sa_mut_buffer_view_v1 ndtha_step_output = {
        SA_ABI_V1_4,
        (uint32_t)sizeof(sa_mut_buffer_view_v1),
        ndtha_top,
        3U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    sa_nonlinear_ndtha_outputs_v1 ndtha_outputs = {0};
    ndtha_outputs.abi_version = SA_ABI_V1_4;
    ndtha_outputs.struct_size = (uint32_t)sizeof(ndtha_outputs);
    ndtha_outputs.top_displacement_m = ndtha_step_output;
    ndtha_outputs.drift_ratio_pct = ndtha_step_output;
    ndtha_outputs.drift_ratio_pct.data = ndtha_drift;
    ndtha_outputs.base_shear_kn = ndtha_step_output;
    ndtha_outputs.base_shear_kn.data = ndtha_base_shear;
    ndtha_outputs.core_drift_pct = ndtha_step_output;
    ndtha_outputs.core_drift_pct.data = ndtha_core_drift;
    ndtha_outputs.core_shear_kn = ndtha_step_output;
    ndtha_outputs.core_shear_kn.data = ndtha_core_shear;
    ndtha_outputs.step_converged = ndtha_step_output;
    ndtha_outputs.step_converged.data = ndtha_step_converged;
    ndtha_outputs.step_converged.stride_bytes = sizeof(uint8_t);
    ndtha_outputs.step_converged.element_type = SA_ELEMENT_TYPE_U8;
    ndtha_outputs.step_iterations = ndtha_step_output;
    ndtha_outputs.step_iterations.data = ndtha_step_iterations;
    ndtha_outputs.step_iterations.stride_bytes = sizeof(uint32_t);
    ndtha_outputs.step_iterations.element_type = SA_ELEMENT_TYPE_U32;
    ndtha_outputs.step_plastic_story_count = ndtha_outputs.step_iterations;
    ndtha_outputs.step_plastic_story_count.data = ndtha_step_plastic;
    ndtha_outputs.step_residual_inf = ndtha_step_output;
    ndtha_outputs.step_residual_inf.data = ndtha_step_residual;
    ndtha_outputs.story_drift_envelope_pct = ndtha_step_output;
    ndtha_outputs.story_drift_envelope_pct.data = ndtha_drift_envelope;
    ndtha_outputs.story_drift_envelope_pct.length = 2U;
    ndtha_outputs.final_story_drift_pct = ndtha_outputs.story_drift_envelope_pct;
    ndtha_outputs.final_story_drift_pct.data = ndtha_final_drift;

    sa_nonlinear_ndtha_result_v1 ndtha_result = {0};
    ndtha_result.abi_version = SA_ABI_V1_4;
    ndtha_result.struct_size = (uint32_t)sizeof(ndtha_result);
    if (api.nonlinear_ndtha_solve(
            &ndtha_config, &ndtha_inputs, &ndtha_outputs, &ndtha_result, NULL)
        != SA_OK) {
        return 1;
    }
    return ndtha_result.converged_all_steps == 1U
            && ndtha_result.collapsed == 0U
            && ndtha_result.fallback_count == 0U
            && ndtha_result.execution_backend == SA_EXECUTION_BACKEND_CPU
        ? 0
        : 1;
}
