#include "structural/abi_v1.h"

#include <stddef.h>

int main(void) {
    sa_api_request_v1 request = {SA_ABI_V1_0, (uint32_t)sizeof(sa_api_request_v1), 0U, {0U}};
    sa_api_v1 api = {0};
    api.abi_version = SA_ABI_V1_0;
    api.struct_size = (uint32_t)sizeof(sa_api_v1);
    if (sa_get_api_v1(&request, &api, NULL) != SA_OK) {
        return 1;
    }
    if (api.validate_buffer_view == NULL) {
        return 2;
    }
    const double values[2] = {1.0, 2.0};
    const sa_buffer_view_v1 view = {
        SA_ABI_V1_0,
        (uint32_t)sizeof(sa_buffer_view_v1),
        values,
        2U,
        (uint64_t)sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
    return api.validate_buffer_view(&view, NULL) == SA_OK ? 0 : 3;
}
