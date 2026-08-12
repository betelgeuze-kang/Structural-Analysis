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
static_assert(std::is_standard_layout_v<sa_nonlinear_static_state_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_config_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_inputs_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_result_v1>);
static_assert(std::is_standard_layout_v<sa_nonlinear_ndtha_state_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_ndtha_adapter_request_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_ndtha_adapter_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_ndtha_adapter_result_v1>);
static_assert(std::is_standard_layout_v<sa_reference_element_config_v1>);
static_assert(std::is_standard_layout_v<sa_reference_element_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_reference_element_result_v1>);
static_assert(std::is_standard_layout_v<sa_sparse_csr_matrix_v1>);
static_assert(std::is_standard_layout_v<sa_sparse_linear_config_v1>);
static_assert(std::is_standard_layout_v<sa_sparse_linear_result_v1>);
static_assert(std::is_standard_layout_v<sa_dense_symmetric_matrix_v1>);
static_assert(std::is_standard_layout_v<sa_generalized_eigen_config_v1>);
static_assert(std::is_standard_layout_v<sa_modal_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_modal_result_v1>);
static_assert(std::is_standard_layout_v<sa_buckling_outputs_v1>);
static_assert(std::is_standard_layout_v<sa_buckling_result_v1>);
static_assert(std::is_standard_layout_v<sa_model_ir_descriptor_v1>);
static_assert(sizeof(sa_api_v1) == 176U);
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
static_assert(offsetof(sa_api_v1, nonlinear_ndtha_advance) == 96U);
static_assert(offsetof(sa_api_v1, model_ir_ndtha_adapt) == 104U);
static_assert(offsetof(sa_api_v1, reference_element_evaluate) == 112U);
static_assert(offsetof(sa_api_v1, sparse_linear_solve) == 120U);
static_assert(offsetof(sa_api_v1, modal_solve) == 128U);
static_assert(offsetof(sa_api_v1, buckling_solve) == 136U);
static_assert(offsetof(sa_api_v1, sparse_linear_begin) == 144U);
static_assert(offsetof(sa_api_v1, sparse_linear_advance) == 152U);
static_assert(offsetof(sa_api_v1, nonlinear_static_begin) == 160U);
static_assert(offsetof(sa_api_v1, nonlinear_static_advance) == 168U);
static_assert(sizeof(sa_sparse_linear_state_v1) == 280U);
static_assert(sizeof(sa_nonlinear_static_state_v1) == 152U);
static_assert(sizeof(sa_nonlinear_ndtha_config_v1) == 144U);
static_assert(sizeof(sa_nonlinear_ndtha_inputs_v1) == 408U);
static_assert(sizeof(sa_nonlinear_ndtha_outputs_v1) == 552U);
static_assert(sizeof(sa_nonlinear_ndtha_result_v1) == 128U);
static_assert(sizeof(sa_nonlinear_ndtha_state_v1) == 792U);
static_assert(sizeof(sa_model_ir_ndtha_adapter_request_v1) == 304U);
static_assert(sizeof(sa_model_ir_ndtha_adapter_outputs_v1) == 360U);
static_assert(sizeof(sa_model_ir_ndtha_adapter_result_v1) == 136U);
static_assert(sizeof(sa_reference_element_config_v1) == 248U);
static_assert(sizeof(sa_reference_element_outputs_v1) == 264U);
static_assert(sizeof(sa_reference_element_result_v1) == 56U);
static_assert(sizeof(sa_sparse_csr_matrix_v1) == 176U);
static_assert(sizeof(sa_sparse_linear_config_v1) == 56U);
static_assert(sizeof(sa_sparse_linear_result_v1) == 80U);
static_assert(sizeof(sa_dense_symmetric_matrix_v1) == 80U);
static_assert(sizeof(sa_generalized_eigen_config_v1) == 96U);
static_assert(sizeof(sa_modal_outputs_v1) == 408U);
static_assert(sizeof(sa_modal_result_v1) == 112U);
static_assert(sizeof(sa_buckling_outputs_v1) == 264U);
static_assert(sizeof(sa_buckling_result_v1) == 120U);
static_assert(offsetof(sa_nonlinear_ndtha_state_v1, adaptive_iteration_sum) == 40U);
static_assert(offsetof(sa_nonlinear_ndtha_state_v1, displacement_m) == 80U);
static_assert(offsetof(sa_nonlinear_ndtha_state_v1, response) == 224U);

int main() {
    return SA_ABI_VERSION_MINOR(SA_ABI_V1_0) == 0U ? 0 : 1;
}
