#include "structural/abi_v1.h"

_Static_assert(sizeof(sa_header_v1) == 8U, "sa_header_v1 layout changed");
_Static_assert(sizeof(sa_buffer_view_v1) == 48U, "sa_buffer_view_v1 layout changed");
_Static_assert(sizeof(sa_mut_buffer_view_v1) == 48U, "sa_mut_buffer_view_v1 layout changed");
_Static_assert(offsetof(sa_buffer_view_v1, data) == 8U, "buffer data offset changed");
_Static_assert(offsetof(sa_buffer_view_v1, flags) == 44U, "buffer flags offset changed");
_Static_assert(sizeof(sa_error_buffer_v1) == 32U, "sa_error_buffer_v1 layout changed");
_Static_assert(sizeof(sa_api_request_v1) == 40U, "sa_api_request_v1 layout changed");
_Static_assert(
    SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT == UINT64_C(1000000),
    "ModelIR linear global-DOF bound changed");
_Static_assert(
    SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES == UINT64_C(100000000),
    "ModelIR linear structural-entry bound changed");
_Static_assert(
    SA_MODEL_IR_LINEAR_MAX_RECOVERY_RECORD_COUNT == UINT64_C(1000000),
    "ModelIR linear recovery-record bound changed");
_Static_assert(sizeof(sa_api_v1) == 200U, "sa_api_v1 layout changed");
_Static_assert(sizeof(sa_backend_request_v1) == 40U, "backend request layout changed");
_Static_assert(sizeof(sa_full_residual_operator_v1) == 544U, "full residual operator layout changed");
_Static_assert(sizeof(sa_full_residual_eval_config_v1) == 40U, "full residual config layout changed");
_Static_assert(sizeof(sa_full_residual_status_v1) == 216U, "full residual status layout changed");
_Static_assert(sizeof(sa_backend_api_v1) == 80U, "backend API layout changed");
_Static_assert(sizeof(sa_track_point_load_config_v1) == 112U, "track config layout changed");
_Static_assert(sizeof(sa_track_point_load_result_v1) == 64U, "track result layout changed");
_Static_assert(sizeof(sa_nonlinear_static_config_v1) == 80U, "nonlinear config layout changed");
_Static_assert(sizeof(sa_nonlinear_static_result_v1) == 88U, "nonlinear result layout changed");
_Static_assert(sizeof(sa_nonlinear_static_state_v1) == 152U, "nonlinear state layout changed");
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
    sizeof(sa_model_ir_linear_assembly_sizes_v1) == 88U,
    "ModelIR linear sizes layout changed");
_Static_assert(
    sizeof(sa_model_ir_linear_assembly_config_v1) == 144U,
    "ModelIR linear config layout changed");
_Static_assert(
    sizeof(sa_model_ir_linear_assembly_outputs_v1) == 792U,
    "ModelIR linear outputs layout changed");
_Static_assert(
    sizeof(sa_model_ir_linear_assembly_result_v1) == 88U,
    "ModelIR linear result layout changed");
_Static_assert(sizeof(sa_sparse_csr_matrix_v1) == 176U, "sparse CSR layout changed");
_Static_assert(sizeof(sa_sparse_linear_config_v1) == 56U, "sparse config layout changed");
_Static_assert(sizeof(sa_sparse_linear_result_v1) == 80U, "sparse result layout changed");
_Static_assert(sizeof(sa_dense_symmetric_matrix_v1) == 80U, "dense matrix layout changed");
_Static_assert(sizeof(sa_generalized_eigen_config_v1) == 96U, "eigen config layout changed");
_Static_assert(sizeof(sa_modal_outputs_v1) == 408U, "modal outputs layout changed");
_Static_assert(sizeof(sa_modal_result_v1) == 112U, "modal result layout changed");
_Static_assert(sizeof(sa_buckling_outputs_v1) == 264U, "buckling outputs layout changed");
_Static_assert(sizeof(sa_buckling_result_v1) == 120U, "buckling result layout changed");
_Static_assert(
    offsetof(sa_api_v1, nonlinear_ndtha_advance) == 96U,
    "NDTHA restart slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, model_ir_ndtha_adapt) == 104U,
    "ModelIR adapter slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, reference_element_evaluate) == 112U,
    "reference element slot offset changed");
_Static_assert(offsetof(sa_api_v1, sparse_linear_solve) == 120U, "sparse slot offset changed");
_Static_assert(offsetof(sa_api_v1, modal_solve) == 128U, "modal slot offset changed");
_Static_assert(offsetof(sa_api_v1, buckling_solve) == 136U, "buckling slot offset changed");
_Static_assert(offsetof(sa_api_v1, sparse_linear_begin) == 144U, "sparse begin slot offset changed");
_Static_assert(offsetof(sa_api_v1, sparse_linear_advance) == 152U, "sparse advance slot offset changed");
_Static_assert(offsetof(sa_api_v1, nonlinear_static_begin) == 160U, "static begin slot offset changed");
_Static_assert(offsetof(sa_api_v1, nonlinear_static_advance) == 168U, "static advance slot offset changed");
_Static_assert(offsetof(sa_api_v1, backend_get_api) == 176U, "backend selector slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, model_ir_linear_assembly_sizes) == 184U,
    "ModelIR linear sizes slot offset changed");
_Static_assert(
    offsetof(sa_api_v1, model_ir_linear_assemble) == 192U,
    "ModelIR linear execute slot offset changed");
_Static_assert(sizeof(sa_sparse_linear_state_v1) == 280U, "sparse restart state layout changed");
_Static_assert(sizeof(sa_string_view_v1) == 16U, "sa_string_view_v1 layout changed");
_Static_assert(sizeof(sa_model_ir_descriptor_v1) == 608U, "ModelIR descriptor layout changed");
_Static_assert(SA_ERR_INTERNAL == 1900, "status taxonomy changed");
_Static_assert(SA_ERR_SINGULARITY == 1601, "sparse status taxonomy changed");

int main(void) {
    return SA_ABI_VERSION_MAJOR(SA_ABI_V1_0) == 1U ? 0 : 1;
}
