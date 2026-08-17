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
#define SA_ABI_VERSION_MINOR UINT32_C(0)

#define SA_CAPABILITY_CPU_REFERENCE (UINT64_C(1) << 0)
#define SA_CAPABILITY_HIP_BACKEND    (UINT64_C(1) << 1)
#define SA_CAPABILITY_CHECKPOINT     (UINT64_C(1) << 2)
#define SA_CAPABILITY_RESULT_IR      (UINT64_C(1) << 3)

typedef enum sa_status {
    SA_STATUS_OK = 0,
    SA_STATUS_INVALID_ARGUMENT = 1,
    SA_STATUS_ABI_MISMATCH = 2,
    SA_STATUS_UNSUPPORTED = 3,
    SA_STATUS_OUT_OF_MEMORY = 4,
    SA_STATUS_BUFFER_TOO_SMALL = 5,
    SA_STATUS_INTERNAL_ERROR = 6
} sa_status;

typedef enum sa_execution_mode {
    SA_EXECUTION_MODE_AUDITED = 0,
    SA_EXECUTION_MODE_PERFORMANCE = 1
} sa_execution_mode;

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

typedef struct sa_engine sa_engine;

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

#ifdef __cplusplus
}  // extern "C"
#endif

#undef SA_NOEXCEPT

#endif  // STRUCTURAL_ENGINE_C_API_H
