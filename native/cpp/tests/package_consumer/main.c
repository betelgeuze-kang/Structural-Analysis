#include <structural/abi_v1.h>

#include <stddef.h>

int main(void) {
    const sa_api_request_v1 request = {
        SA_ABI_V1_2,
        (uint32_t)sizeof(sa_api_request_v1),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api = {0};
    api.abi_version = SA_ABI_V1_2;
    api.struct_size = (uint32_t)sizeof(sa_api_v1);
    if (sa_get_api_v1(&request, &api, NULL) != SA_OK
        || api.track_point_load_solve == NULL
        || (api.capabilities & SA_CAPABILITY_TRACK_POINT_LOAD_CPU) == 0U) {
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
    return result.converged == 1U && result.fallback_count == 0U
        && result.execution_backend == SA_EXECUTION_BACKEND_CPU
        ? 0
        : 1;
}
