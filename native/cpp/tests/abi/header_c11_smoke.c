#include "structural/abi_v1.h"

_Static_assert(sizeof(sa_header_v1) == 8U, "sa_header_v1 layout changed");
_Static_assert(sizeof(sa_buffer_view_v1) == 48U, "sa_buffer_view_v1 layout changed");
_Static_assert(offsetof(sa_buffer_view_v1, data) == 8U, "buffer data offset changed");
_Static_assert(offsetof(sa_buffer_view_v1, flags) == 44U, "buffer flags offset changed");
_Static_assert(sizeof(sa_error_buffer_v1) == 32U, "sa_error_buffer_v1 layout changed");
_Static_assert(sizeof(sa_api_request_v1) == 40U, "sa_api_request_v1 layout changed");
_Static_assert(sizeof(sa_api_v1) == 128U, "sa_api_v1 layout changed");
_Static_assert(SA_ERR_INTERNAL == 1900, "status taxonomy changed");

int main(void) {
    return SA_ABI_VERSION_MAJOR(SA_ABI_V1_0) == 1U ? 0 : 1;
}
