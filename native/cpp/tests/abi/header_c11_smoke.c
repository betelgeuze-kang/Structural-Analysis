#include "structural/abi_v1.h"

_Static_assert(sizeof(sa_header_v1) == 8U, "sa_header_v1 layout changed");
_Static_assert(sizeof(sa_buffer_view_v1) == 48U, "sa_buffer_view_v1 layout changed");
_Static_assert(offsetof(sa_buffer_view_v1, data) == 8U, "buffer data offset changed");
_Static_assert(offsetof(sa_buffer_view_v1, flags) == 44U, "buffer flags offset changed");
_Static_assert(sizeof(sa_error_buffer_v1) == 32U, "sa_error_buffer_v1 layout changed");
_Static_assert(sizeof(sa_api_request_v1) == 40U, "sa_api_request_v1 layout changed");
_Static_assert(sizeof(sa_api_v1) == 128U, "sa_api_v1 layout changed");
_Static_assert(sizeof(sa_linear_frame3d_node_v1) == 32U, "Frame3D node layout changed");
_Static_assert(sizeof(sa_linear_frame3d_section_v1) == 72U, "Frame3D section layout changed");
_Static_assert(sizeof(sa_linear_frame3d_member_v1) == 32U, "Frame3D member layout changed");
_Static_assert(sizeof(sa_linear_frame3d_model_input_v1) == 80U, "Frame3D input layout changed");
_Static_assert(
    sizeof(sa_linear_frame3d_result_buffers_v1) == 56U,
    "Frame3D result layout changed");
_Static_assert(
    offsetof(sa_api_v1, linear_frame3d_model_compile) == 72U,
    "Frame3D compile slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, linear_frame3d_solve) == 96U,
    "Frame3D solve slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, linear_frame3d_solve_load_case) == 104U,
    "Frame3D load-case solve slot offset changed");
_Static_assert(
    sizeof(sa_linear_frame3d_uniform_member_load_v1) == 40U,
    "Frame3D member-load layout changed");
_Static_assert(
    sizeof(sa_linear_frame3d_load_case_v1) == 40U,
    "Frame3D load-case layout changed");
_Static_assert(sizeof(sa_string_view_v1) == 16U, "sa_string_view_v1 layout changed");
_Static_assert(sizeof(sa_model_ir_descriptor_v1) == 608U, "ModelIR descriptor layout changed");
_Static_assert(SA_ERR_INTERNAL == 1900, "status taxonomy changed");

int main(void) {
    return SA_ABI_VERSION_MINOR(SA_ABI_V1_CURRENT) == 3U ? 0 : 1;
}
