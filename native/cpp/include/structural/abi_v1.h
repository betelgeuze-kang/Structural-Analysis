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
#define SA_ABI_V1_3 UINT32_C(0x00010003)
#define SA_ABI_V1_CURRENT SA_ABI_V1_3
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
    SA_ERR_NONCONVERGENCE = 1600,
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
#define SA_CAPABILITY_TRACK_POINT_LOAD_CPU UINT64_C(8)
#define SA_CAPABILITY_NONLINEAR_STATIC_CPU UINT64_C(16)
#define SA_TRACK_POINT_LOAD_MAX_NODE_COUNT UINT32_C(1000000)
#define SA_NONLINEAR_STATIC_MAX_STORY_COUNT UINT32_C(1000000)

enum {
    SA_TRACK_SUPPORT_PINNED = 0,
    SA_TRACK_SUPPORT_FIXED = 1
};

enum {
    SA_TRACK_THEORY_EULER = 0,
    SA_TRACK_THEORY_TIMOSHENKO_REDUCED = 1
};

/*
 * v1.2 rotation recovery uses centered differences at interior nodes. Euler uses
 * first-order one-sided endpoint differences; reduced Timoshenko copies the adjacent
 * centered value to each endpoint. This theory-specific convention is ABI semantics.
 */

enum {
    SA_EXECUTION_BACKEND_CPU = 1,
    SA_EXECUTION_BACKEND_HIP = 2
};

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

typedef struct sa_mut_buffer_view_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    void* data;
    uint64_t length;
    uint64_t stride_bytes;
    uint32_t element_type;
    uint32_t memory_space;
    int32_t device_id;
    uint32_t flags;
} sa_mut_buffer_view_v1;

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

typedef struct sa_track_point_load_config_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    double length_m;
    uint32_t node_count;
    uint32_t support_type;
    uint32_t theory;
    uint32_t flags;
    double bending_stiffness_n_m2;
    double shear_stiffness_n;
    double winkler_k_n_per_m2;
    double pasternak_g_n;
    double tolerance;
    uint32_t cg_max_iter;
    uint32_t reserved_u32;
    double point_force_n;
    double point_position_m;
    uint64_t reserved[2];
} sa_track_point_load_config_v1;

typedef struct sa_track_point_load_result_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t converged;
    uint32_t iterations;
    double residual_inf;
    double max_abs_displacement_m;
    double mid_displacement_m;
    uint64_t output_length;
    uint32_t execution_backend;
    uint32_t fallback_count;
    uint64_t reserved;
} sa_track_point_load_result_v1;

typedef struct sa_nonlinear_static_config_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t story_count;
    uint32_t max_iter;
    double tolerance;
    double hardening_ratio;
    double line_search_decay;
    double line_search_min;
    double pdelta_factor;
    uint32_t flags;
    uint32_t reserved_u32;
    uint64_t reserved[2];
} sa_nonlinear_static_config_v1;

typedef struct sa_nonlinear_static_result_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t converged;
    uint32_t iterations;
    double residual_inf;
    double residual_l2;
    double max_abs_displacement_m;
    double top_displacement_m;
    double base_shear_kn;
    uint32_t plastic_story_count;
    uint32_t line_search_backtracks;
    uint64_t output_length;
    uint32_t execution_backend;
    uint32_t fallback_count;
    uint64_t reserved;
} sa_nonlinear_static_result_v1;

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

typedef sa_status_code_v1 (*sa_track_point_load_solve_fn_v1)(
    const sa_track_point_load_config_v1* config,
    const sa_mut_buffer_view_v1* displacement_m,
    const sa_mut_buffer_view_v1* rotation_rad,
    sa_track_point_load_result_v1* result,
    sa_error_buffer_v1* error);

typedef sa_status_code_v1 (*sa_nonlinear_static_solve_fn_v1)(
    const sa_nonlinear_static_config_v1* config,
    const sa_buffer_view_v1* story_stiffness_n_per_m,
    const sa_buffer_view_v1* story_height_m,
    const sa_buffer_view_v1* story_axial_n,
    const sa_buffer_view_v1* story_yield_drift_m,
    const sa_buffer_view_v1* floor_load_n,
    const sa_mut_buffer_view_v1* displacement_m,
    sa_nonlinear_static_result_v1* result,
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
    sa_track_point_load_solve_fn_v1 track_point_load_solve;
    sa_nonlinear_static_solve_fn_v1 nonlinear_static_solve;
    const void* reserved[5];
} sa_api_v1;

#define SA_API_REQUEST_V1_MIN_SIZE ((uint32_t)offsetof(sa_api_request_v1, reserved))
#define SA_API_V1_0_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, model_ir_create))
#define SA_API_V1_1_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, track_point_load_solve))
#define SA_API_V1_2_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, nonlinear_static_solve))
#define SA_API_V1_3_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, reserved))
#define SA_API_V1_MIN_SIZE SA_API_V1_0_MIN_SIZE

SA_API_V1_EXPORT sa_status_code_v1 sa_get_api_v1(
    const sa_api_request_v1* request,
    sa_api_v1* out_api,
    sa_error_buffer_v1* error);

#ifdef __cplusplus
}
#endif

#endif
