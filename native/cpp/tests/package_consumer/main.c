#include <structural/abi_v1.h>

#include <stddef.h>

int main(void) {
    const sa_api_request_v1 request = {
        SA_ABI_V1_3,
        (uint32_t)sizeof(sa_api_request_v1),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api = {0};
    api.abi_version = SA_ABI_V1_3;
    api.struct_size = (uint32_t)sizeof(sa_api_v1);
    if (sa_get_api_v1(&request, &api, NULL) != SA_OK
        || api.track_point_load_solve == NULL
        || api.nonlinear_static_solve == NULL
        || (api.capabilities & SA_CAPABILITY_TRACK_POINT_LOAD_CPU) == 0U
        || (api.capabilities & SA_CAPABILITY_NONLINEAR_STATIC_CPU) == 0U) {
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
    return nonlinear_result.converged == 1U
            && nonlinear_result.fallback_count == 0U
            && nonlinear_result.execution_backend == SA_EXECUTION_BACKEND_CPU
        ? 0
        : 1;
}
