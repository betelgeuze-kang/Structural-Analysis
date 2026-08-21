#ifndef STRUCTURAL_ABI_V1_H
#define STRUCTURAL_ABI_V1_H

#include <stddef.h>
#include <stdint.h>

#include "structural/model_ir_v1.h"

#if defined(_WIN32)
#  if defined(STRUCTURAL_C_ABI_V1_BUILD)
#    define SA_API_V1_EXPORT __declspec(dllexport)
#  else
#    define SA_API_V1_EXPORT __declspec(dllimport)
#  endif
#elif defined(__GNUC__) || defined(__clang__)
#  define SA_API_V1_EXPORT __attribute__((visibility("default")))
#else
#  define SA_API_V1_EXPORT
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define SA_ABI_V1_0 UINT32_C(0x00010000)
#define SA_ABI_V1_1 UINT32_C(0x00010001)
#define SA_ABI_V1_2 UINT32_C(0x00010002)
#define SA_ABI_V1_CURRENT SA_ABI_V1_2
#define SA_ABI_VERSION_MAJOR(value) ((uint16_t)(((uint32_t)(value)) >> 16U))
#define SA_ABI_VERSION_MINOR(value) ((uint16_t)(((uint32_t)(value)) & UINT32_C(0xffff)))

typedef uint32_t sa_status_code_v1;

enum {
    SA_OK = 0,
    SA_ERR_INVALID_ARGUMENT = 1000,
    SA_ERR_ABI_VERSION_MISMATCH = 1001,
    SA_ERR_STRUCT_SIZE = 1002,
    SA_ERR_BUFFER_TOO_SMALL = 1003,
    SA_ERR_SCHEMA_INVALID = 1100,
    SA_ERR_SEMANTIC_INVALID = 1101,
    SA_ERR_ANALYSIS_NOT_READY = 1102,
    SA_ERR_UNSUPPORTED = 1200,
    SA_ERR_STATE_CONFLICT = 1300,
    SA_ERR_CHECKPOINT_MISMATCH = 1301,
    SA_ERR_BACKEND_UNAVAILABLE = 1400,
    SA_ERR_DEVICE_MISMATCH = 1401,
    SA_ERR_FALLBACK_FORBIDDEN = 1402,
    SA_ERR_CANCELLED = 1500,
    SA_ERR_INTERNAL = 1900
};

enum {
    SA_ELEMENT_TYPE_F64 = 1,
    SA_ELEMENT_TYPE_U64 = 2,
    SA_ELEMENT_TYPE_I32 = 3,
    SA_ELEMENT_TYPE_U8 = 4
};

enum {
    SA_MEMORY_SPACE_HOST = 0,
    SA_MEMORY_SPACE_DEVICE = 1
};

#define SA_CAPABILITY_BUFFER_VALIDATION UINT64_C(1)
#define SA_CAPABILITY_MODEL_IR_V2_TYPED UINT64_C(2)
#define SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT UINT64_C(4)
#define SA_CAPABILITY_LINEAR_FRAME3D_CPU UINT64_C(8)

typedef struct sa_header_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
} sa_header_v1;

typedef struct sa_buffer_view_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    const void* data;
    uint64_t length;
    uint64_t stride_bytes;
    uint32_t element_type;
    uint32_t memory_space;
    int32_t device_id;
    uint32_t flags;
} sa_buffer_view_v1;

typedef struct sa_error_buffer_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    char* data;
    uint64_t capacity;
    uint64_t required;
} sa_error_buffer_v1;

typedef struct sa_api_request_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint64_t flags;
    uint64_t reserved[3];
} sa_api_request_v1;

typedef struct sa_linear_frame3d_node_v1 {
    uint32_t struct_size;
    uint32_t reserved_u32;
    double x_m;
    double y_m;
    double z_m;
} sa_linear_frame3d_node_v1;

typedef struct sa_linear_frame3d_section_v1 {
    uint32_t struct_size;
    uint32_t reserved_u32;
    double area_m2;
    double elastic_modulus_kn_per_m2;
    double shear_modulus_kn_per_m2;
    double iy_m4;
    double iz_m4;
    double j_m4;
    double effective_shear_area_y_m2;
    double effective_shear_area_z_m2;
} sa_linear_frame3d_section_v1;

typedef struct sa_linear_frame3d_member_v1 {
    uint32_t struct_size;
    uint32_t node_i;
    uint32_t node_j;
    uint32_t section_index;
    uint32_t reserved_u32[2];
    double local_axis_roll_deg;
} sa_linear_frame3d_member_v1;

typedef struct sa_linear_frame3d_model_input_v1 {
    uint32_t struct_size;
    uint32_t abi_version_major;
    uint32_t abi_version_minor;
    uint32_t reserved_u32;
    const sa_linear_frame3d_node_v1* nodes;
    uint64_t node_count;
    const sa_linear_frame3d_section_v1* sections;
    uint64_t section_count;
    const sa_linear_frame3d_member_v1* members;
    uint64_t member_count;
    const uint32_t* restrained_dofs;
    uint64_t restrained_dof_count;
} sa_linear_frame3d_model_input_v1;

typedef struct sa_linear_frame3d_result_buffers_v1 {
    uint32_t struct_size;
    uint32_t reserved_u32;
    double* displacements;
    uint64_t displacement_count;
    double* reactions;
    uint64_t reaction_count;
    double* member_end_forces;
    uint64_t member_end_force_count;
} sa_linear_frame3d_result_buffers_v1;

typedef struct sa_linear_frame3d_model_v1 sa_linear_frame3d_model_v1;

typedef sa_status_code_v1 (*sa_validate_buffer_view_fn_v1)(
    const sa_buffer_view_v1* view,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_create_fn_v1)(
    const sa_model_ir_descriptor_v1* descriptor,
    sa_model_ir_handle_v1** out_handle,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_destroy_fn_v1)(
    sa_model_ir_handle_v1* handle,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_validation_report_size_fn_v1)(
    const sa_model_ir_handle_v1* handle,
    uint64_t* out_size,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_validation_report_write_fn_v1)(
    const sa_model_ir_handle_v1* handle,
    uint8_t* output,
    uint64_t capacity,
    uint64_t* out_written,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_snapshot_size_fn_v1)(
    const sa_model_ir_handle_v1* handle,
    uint64_t* out_size,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_model_ir_snapshot_write_fn_v1)(
    const sa_model_ir_handle_v1* handle,
    uint8_t* output,
    uint64_t capacity,
    uint64_t* out_written,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_linear_frame3d_model_compile_fn_v1)(
    const sa_linear_frame3d_model_input_v1* input,
    sa_linear_frame3d_model_v1** out_model,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_linear_frame3d_model_destroy_fn_v1)(
    sa_linear_frame3d_model_v1* model,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_linear_frame3d_model_sizes_fn_v1)(
    const sa_linear_frame3d_model_v1* model,
    uint64_t* out_dof_count,
    uint64_t* out_member_end_force_count,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_linear_frame3d_solve_fn_v1)(
    const sa_linear_frame3d_model_v1* model,
    const double* load_vector_kn,
    uint64_t load_count,
    sa_linear_frame3d_result_buffers_v1* out_result,
    sa_error_buffer_v1* error);

typedef struct sa_api_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint64_t capabilities;
    sa_validate_buffer_view_fn_v1 validate_buffer_view;
    sa_model_ir_create_fn_v1 model_ir_create;
    sa_model_ir_destroy_fn_v1 model_ir_destroy;
    sa_model_ir_validation_report_size_fn_v1 model_ir_validation_report_size;
    sa_model_ir_validation_report_write_fn_v1 model_ir_validation_report_write;
    sa_model_ir_snapshot_size_fn_v1 model_ir_snapshot_size;
    sa_model_ir_snapshot_write_fn_v1 model_ir_snapshot_write;
    sa_linear_frame3d_model_compile_fn_v1 linear_frame3d_model_compile;
    sa_linear_frame3d_model_destroy_fn_v1 linear_frame3d_model_destroy;
    sa_linear_frame3d_model_sizes_fn_v1 linear_frame3d_model_sizes;
    sa_linear_frame3d_solve_fn_v1 linear_frame3d_solve;
    const void* reserved[3];
} sa_api_v1;

#define SA_API_REQUEST_V1_MIN_SIZE ((uint32_t)offsetof(sa_api_request_v1, reserved))
#define SA_API_V1_0_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, model_ir_create))
#define SA_API_V1_1_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, linear_frame3d_model_compile))
#define SA_API_V1_2_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, reserved))
#define SA_API_V1_MIN_SIZE SA_API_V1_0_MIN_SIZE

SA_API_V1_EXPORT sa_status_code_v1 sa_get_api_v1(
    const sa_api_request_v1* request,
    sa_api_v1* out_api,
    sa_error_buffer_v1* error);

#ifdef __cplusplus
}
#endif

#endif
