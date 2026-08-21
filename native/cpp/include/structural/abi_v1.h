#ifndef STRUCTURAL_ABI_V1_H
#define STRUCTURAL_ABI_V1_H

#include <stddef.h>
#include <stdint.h>

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

typedef sa_status_code_v1 (*sa_validate_buffer_view_fn_v1)(
    const sa_buffer_view_v1* view,
    sa_error_buffer_v1* error);

typedef struct sa_api_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint64_t capabilities;
    sa_validate_buffer_view_fn_v1 validate_buffer_view;
    const void* reserved[13];
} sa_api_v1;

#define SA_API_REQUEST_V1_MIN_SIZE ((uint32_t)offsetof(sa_api_request_v1, reserved))
#define SA_API_V1_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, reserved))

SA_API_V1_EXPORT sa_status_code_v1 sa_get_api_v1(
    const sa_api_request_v1* request,
    sa_api_v1* out_api,
    sa_error_buffer_v1* error);

#ifdef __cplusplus
}
#endif

#endif
