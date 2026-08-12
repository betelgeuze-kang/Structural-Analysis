#include "structural/abi_v1.h"

_Static_assert(sizeof(sa_header_v1) == 8U, "sa_header_v1 layout changed");
_Static_assert(sizeof(sa_buffer_view_v1) == 48U, "sa_buffer_view_v1 layout changed");
_Static_assert(sizeof(sa_mut_buffer_view_v1) == 48U, "sa_mut_buffer_view_v1 layout changed");
_Static_assert(offsetof(sa_buffer_view_v1, data) == 8U, "buffer data offset changed");
_Static_assert(offsetof(sa_buffer_view_v1, flags) == 44U, "buffer flags offset changed");
_Static_assert(sizeof(sa_error_buffer_v1) == 32U, "sa_error_buffer_v1 layout changed");
_Static_assert(sizeof(sa_api_request_v1) == 40U, "sa_api_request_v1 layout changed");
_Static_assert(sizeof(sa_api_v1) == 136U, "sa_api_v1 layout changed");
_Static_assert(sizeof(sa_track_point_load_config_v1) == 112U, "track config layout changed");
_Static_assert(sizeof(sa_track_point_load_result_v1) == 64U, "track result layout changed");
_Static_assert(sizeof(sa_nonlinear_static_config_v1) == 80U, "nonlinear config layout changed");
_Static_assert(sizeof(sa_nonlinear_static_result_v1) == 88U, "nonlinear result layout changed");
_Static_assert(sizeof(sa_nonlinear_ndtha_config_v1) == 144U, "NDTHA config layout changed");
_Static_assert(sizeof(sa_nonlinear_ndtha_inputs_v1) == 408U, "NDTHA inputs layout changed");
_Static_assert(sizeof(sa_nonlinear_ndtha_outputs_v1) == 552U, "NDTHA outputs layout changed");
_Static_assert(sizeof(sa_nonlinear_ndtha_result_v1) == 128U, "NDTHA result layout changed");
_Static_assert(sizeof(sa_nonlinear_ndtha_state_v1) == 792U, "NDTHA state layout changed");
_Static_assert(
    sizeof(sa_model_ir_ndtha_adapter_request_v1) == 304U,
    "ModelIR adapter request layout changed");
_Static_assert(
    sizeof(sa_model_ir_ndtha_adapter_outputs_v1) == 360U,
    "ModelIR adapter outputs layout changed");
_Static_assert(
    sizeof(sa_model_ir_ndtha_adapter_result_v1) == 136U,
    "ModelIR adapter result layout changed");
_Static_assert(sizeof(sa_reference_element_config_v1) == 248U, "reference config layout changed");
_Static_assert(sizeof(sa_reference_element_outputs_v1) == 264U, "reference outputs layout changed");
_Static_assert(sizeof(sa_reference_element_result_v1) == 56U, "reference result layout changed");
_Static_assert(
    offsetof(sa_api_v1, nonlinear_ndtha_advance) == 96U,
    "NDTHA restart slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, model_ir_ndtha_adapt) == 104U,
    "ModelIR adapter slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, reference_element_evaluate) == 112U,
    "reference element slot offset changed");
_Static_assert(offsetof(sa_api_v1, reserved) == 120U, "API reserved tail offset changed");
_Static_assert(sizeof(sa_string_view_v1) == 16U, "sa_string_view_v1 layout changed");
_Static_assert(sizeof(sa_model_ir_descriptor_v1) == 608U, "ModelIR descriptor layout changed");
_Static_assert(SA_ERR_INTERNAL == 1900, "status taxonomy changed");

int main(void) {
    return SA_ABI_VERSION_MAJOR(SA_ABI_V1_0) == 1U ? 0 : 1;
}
