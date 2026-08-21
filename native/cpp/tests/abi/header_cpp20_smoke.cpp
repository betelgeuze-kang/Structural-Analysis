#include "structural/abi_v1.h"

#include <cstddef>
#include <type_traits>

static_assert(std::is_standard_layout_v<sa_header_v1>);
static_assert(std::is_standard_layout_v<sa_buffer_view_v1>);
static_assert(std::is_standard_layout_v<sa_error_buffer_v1>);
static_assert(std::is_standard_layout_v<sa_api_request_v1>);
static_assert(std::is_standard_layout_v<sa_api_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_descriptor_v1>);
static_assert(std::is_standard_layout_v<sa_linear_frame3d_model_input_v1>);
static_assert(std::is_standard_layout_v<sa_linear_frame3d_result_buffers_v1>);
static_assert(sizeof(sa_api_v1) == 128U);
static_assert(sizeof(sa_string_view_v1) == 16U);
static_assert(sizeof(sa_optional_string_view_v1) == 24U);
static_assert(sizeof(sa_entity_identity_v1) == 72U);
static_assert(sizeof(sa_node_descriptor_v1) == 104U);
static_assert(sizeof(sa_model_ir_descriptor_v1) == 608U);
static_assert(offsetof(sa_api_v1, validate_buffer_view) == 16U);
static_assert(offsetof(sa_api_v1, model_ir_create) == 24U);
static_assert(offsetof(sa_api_v1, linear_frame3d_model_compile) == 72U);
static_assert(offsetof(sa_api_v1, linear_frame3d_solve) == 96U);
static_assert(offsetof(sa_api_v1, linear_frame3d_solve_load_case) == 104U);
static_assert(offsetof(sa_api_v1, reserved) == 112U);
static_assert(sizeof(sa_linear_frame3d_node_v1) == 32U);
static_assert(sizeof(sa_linear_frame3d_section_v1) == 72U);
static_assert(sizeof(sa_linear_frame3d_member_v1) == 32U);
static_assert(sizeof(sa_linear_frame3d_model_input_v1) == 80U);
static_assert(sizeof(sa_linear_frame3d_result_buffers_v1) == 56U);
static_assert(sizeof(sa_linear_frame3d_uniform_member_load_v1) == 40U);
static_assert(sizeof(sa_linear_frame3d_load_case_v1) == 40U);

int main() {
    return SA_ABI_VERSION_MINOR(SA_ABI_V1_CURRENT) == 4U ? 0 : 1;
}
