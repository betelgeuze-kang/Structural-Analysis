#ifndef STRUCTURAL_ENGINE_C_API_H
#define STRUCTURAL_ENGINE_C_API_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  if defined(STRUCTURAL_ENGINE_BUILD_SHARED)
#    define SA_API __declspec(dllexport)
#  elif defined(STRUCTURAL_ENGINE_USE_SHARED)
#    define SA_API __declspec(dllimport)
#  else
#    define SA_API
#  endif
#else
#  define SA_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
#  define SA_NOEXCEPT noexcept
extern "C" {
#else
#  define SA_NOEXCEPT
#endif

#define SA_ABI_VERSION_MAJOR UINT32_C(1)
#define SA_ABI_VERSION_MINOR UINT32_C(1)

#define SA_CAPABILITY_CPU_REFERENCE  (UINT64_C(1) << 0)
#define SA_CAPABILITY_HIP_BACKEND     (UINT64_C(1) << 1)
#define SA_CAPABILITY_CHECKPOINT      (UINT64_C(1) << 2)
#define SA_CAPABILITY_RESULT_IR       (UINT64_C(1) << 3)
#define SA_CAPABILITY_LINEAR_FRAME3D  (UINT64_C(1) << 4)

/*
 * ABI-facing scalar types use fixed-width integers. C enum underlying types are
 * implementation-defined and therefore are not used as function return types or
 * public structure fields across the C/Rust boundary.
 */
typedef int32_t sa_status;
enum {
    SA_STATUS_OK = 0,
    SA_STATUS_INVALID_ARGUMENT = 1,
    SA_STATUS_ABI_MISMATCH = 2,
    SA_STATUS_UNSUPPORTED = 3,
    SA_STATUS_OUT_OF_MEMORY = 4,
    SA_STATUS_BUFFER_TOO_SMALL = 5,
    SA_STATUS_INTERNAL_ERROR = 6,
    SA_STATUS_SINGULAR_SYSTEM = 7
};

typedef uint32_t sa_execution_mode;
enum {
    SA_EXECUTION_MODE_AUDITED = 0,
    SA_EXECUTION_MODE_PERFORMANCE = 1
};

typedef struct sa_api_info {
    uint32_t struct_size;
    uint32_t abi_version_major;
    uint32_t abi_version_minor;
    uint32_t reserved_u32;
    uint64_t capability_bits;
    const char *implementation_name;
} sa_api_info;

typedef struct sa_engine_config {
    uint32_t struct_size;
    uint32_t abi_version_major;
    uint32_t abi_version_minor;
    uint32_t execution_mode;
    int32_t requested_device_index;
    uint32_t reserved_u32[3];
} sa_engine_config;

typedef struct sa_linear_frame3d_node {
    uint32_t struct_size;
    uint32_t reserved_u32;
    double x_m;
    double y_m;
    double z_m;
} sa_linear_frame3d_node;

typedef struct sa_linear_frame3d_section {
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
} sa_linear_frame3d_section;

typedef struct sa_linear_frame3d_member {
    uint32_t struct_size;
    uint32_t node_i;
    uint32_t node_j;
    uint32_t section_index;
    uint32_t reserved_u32[2];
    double local_axis_roll_deg;
} sa_linear_frame3d_member;

typedef struct sa_linear_frame3d_model_input {
    uint32_t struct_size;
    uint32_t abi_version_major;
    uint32_t abi_version_minor;
    uint32_t reserved_u32;
    const sa_linear_frame3d_node *nodes;
    size_t node_count;
    const sa_linear_frame3d_section *sections;
    size_t section_count;
    const sa_linear_frame3d_member *members;
    size_t member_count;
    const uint32_t *restrained_dofs;
    size_t restrained_dof_count;
} sa_linear_frame3d_model_input;

typedef struct sa_linear_frame3d_result_buffers {
    uint32_t struct_size;
    uint32_t reserved_u32;
    double *displacements;
    size_t displacement_count;
    double *reactions;
    size_t reaction_count;
    double *member_end_forces;
    size_t member_end_force_count;
} sa_linear_frame3d_result_buffers;

typedef struct sa_engine sa_engine;
typedef struct sa_linear_frame3d_model sa_linear_frame3d_model;

SA_API sa_status sa_get_api_info(sa_api_info *out_info) SA_NOEXCEPT;

SA_API sa_status sa_engine_create(
    const sa_engine_config *config,
    sa_engine **out_engine
) SA_NOEXCEPT;

SA_API void sa_engine_destroy(sa_engine *engine) SA_NOEXCEPT;

SA_API sa_status sa_engine_capabilities(
    const sa_engine *engine,
    uint64_t *out_capability_bits
) SA_NOEXCEPT;

SA_API sa_status sa_engine_last_error(
    const sa_engine *engine,
    char *buffer,
    size_t buffer_capacity,
    size_t *out_required_size
) SA_NOEXCEPT;

SA_API sa_status sa_linear_frame3d_model_compile(
    const sa_engine *engine,
    const sa_linear_frame3d_model_input *input,
    sa_linear_frame3d_model **out_model
) SA_NOEXCEPT;

SA_API void sa_linear_frame3d_model_destroy(
    sa_linear_frame3d_model *model
) SA_NOEXCEPT;

SA_API sa_status sa_linear_frame3d_model_sizes(
    const sa_linear_frame3d_model *model,
    size_t *out_dof_count,
    size_t *out_member_end_force_count
) SA_NOEXCEPT;

SA_API sa_status sa_linear_frame3d_solve(
    const sa_linear_frame3d_model *model,
    const double *load_vector_kn,
    size_t load_count,
    sa_linear_frame3d_result_buffers *out_result
) SA_NOEXCEPT;

#ifdef __cplusplus
}  // extern "C"
#endif

#undef SA_NOEXCEPT

#endif  // STRUCTURAL_ENGINE_C_API_H
