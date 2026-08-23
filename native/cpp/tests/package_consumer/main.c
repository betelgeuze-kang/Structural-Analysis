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
    if (sa_get_api_v1(&request, &api, NULL) != SA_OK) {
        return 1;
    }
    if ((api.capabilities & SA_CAPABILITY_LINEAR_FRAME3D_CPU) == 0U) {
        return 2;
    }
    return api.linear_frame3d_model_compile != NULL && api.linear_frame3d_model_destroy != NULL
               && api.linear_frame3d_model_sizes != NULL && api.linear_frame3d_solve != NULL
        ? 0
        : 3;
}
