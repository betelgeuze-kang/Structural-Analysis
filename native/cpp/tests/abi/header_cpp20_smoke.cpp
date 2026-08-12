#include "structural/abi_v1.h"

#include <cstddef>
#include <type_traits>

static_assert(std::is_standard_layout_v<sa_header_v1>);
static_assert(std::is_standard_layout_v<sa_buffer_view_v1>);
static_assert(std::is_standard_layout_v<sa_mut_buffer_view_v1>);
static_assert(std::is_standard_layout_v<sa_error_buffer_v1>);
static_assert(std::is_standard_layout_v<sa_api_request_v1>);
static_assert(std::is_standard_layout_v<sa_api_v1>);
static_assert(std::is_standard_layout_v<sa_track_point_load_config_v1>);
static_assert(std::is_standard_layout_v<sa_track_point_load_result_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_static_config_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_static_result_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_config_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_inputs_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_result_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_descriptor_v1>);
static_assert(sizeof(sa_api_v1) == 128U);
static_assert(sizeof(sa_string_view_v1) == 16U);
static_assert(sizeof(sa_optional_string_view_v1) == 24U);
static_assert(sizeof(sa_entity_identity_v1) == 72U);
static_assert(sizeof(sa_node_descriptor_v1) == 104U);
static_assert(sizeof(sa_model_ir_descriptor_v1) == 608U);
static_assert(offsetof(sa_api_v1, validate_buffer_view) == 16U);
static_assert(offsetof(sa_api_v1, model_ir_create) == 24U);
static_assert(offsetof(sa_api_v1, track_point_load_solve) == 72U);
static_assert(offsetof(sa_api_v1, nonlinear_static_solve) == 80U);
static_assert(offsetof(sa_api_v1, nonlinear_ndtha_solve) == 88U);
static_assert(offsetof(sa_api_v1, reserved) == 96U);
static_assert(sizeof(sa_nonlinear_ndtha_config_v1) == 144U);
static_assert(sizeof(sa_nonlinear_ndtha_inputs_v1) == 408U);
static_assert(sizeof(sa_nonlinear_ndtha_outputs_v1) == 552U);
static_assert(sizeof(sa_nonlinear_ndtha_result_v1) == 128U);

int main() {
    return SA_ABI_VERSION_MINOR(SA_ABI_V1_0) == 0U ? 0 : 1;
}
