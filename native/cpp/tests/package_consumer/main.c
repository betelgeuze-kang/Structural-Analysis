#include <structural/abi_v1.h>

#include <stddef.h>

int main(void) {
    const sa_api_request_v1 request = {
        SA_ABI_V1_0,
        (uint32_t)sizeof(sa_api_request_v1),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api = {0};
    api.abi_version = SA_ABI_V1_0;
    api.struct_size = (uint32_t)sizeof(sa_api_v1);
    return sa_get_api_v1(&request, &api, NULL) == SA_OK ? 0 : 1;
}
