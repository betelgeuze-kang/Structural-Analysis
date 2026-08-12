include_guard(GLOBAL)

if(STRUCTURAL_ROCM_ROOT)
  if(NOT IS_DIRECTORY "${STRUCTURAL_ROCM_ROOT}")
    message(FATAL_ERROR "STRUCTURAL_ROCM_ROOT is not a directory")
  endif()
  set(
    CMAKE_HIP_COMPILER_ROCM_ROOT
    "${STRUCTURAL_ROCM_ROOT}"
    CACHE PATH
    "ROCm root for CMake HIP compiler detection"
    FORCE
  )
endif()

if(NOT STRUCTURAL_HIP_DEVICE_LIB_PATH AND STRUCTURAL_ROCM_ROOT)
  foreach(
    candidate
    "${STRUCTURAL_ROCM_ROOT}/amdgcn/bitcode"
    "${STRUCTURAL_ROCM_ROOT}/lib/llvm/amdgcn/bitcode"
  )
    if(EXISTS "${candidate}/ocml.bc" AND EXISTS "${candidate}/ockl.bc")
      set(STRUCTURAL_HIP_DEVICE_LIB_PATH "${candidate}")
      break()
    endif()
  endforeach()
endif()
if(NOT STRUCTURAL_HIP_DEVICE_LIB_PATH
   OR NOT EXISTS "${STRUCTURAL_HIP_DEVICE_LIB_PATH}/ocml.bc"
   OR NOT EXISTS "${STRUCTURAL_HIP_DEVICE_LIB_PATH}/ockl.bc")
  message(
    FATAL_ERROR
    "STRUCTURAL_ENABLE_HIP=ON requires STRUCTURAL_HIP_DEVICE_LIB_PATH with ocml.bc and ockl.bc"
  )
endif()
string(
  FIND
  " ${CMAKE_HIP_FLAGS} "
  "--rocm-device-lib-path="
  STRUCTURAL_HIP_DEVICE_LIB_FLAG_INDEX
)
if(STRUCTURAL_HIP_DEVICE_LIB_FLAG_INDEX EQUAL -1)
  string(
    APPEND
    CMAKE_HIP_FLAGS
    " --rocm-device-lib-path=${STRUCTURAL_HIP_DEVICE_LIB_PATH}"
  )
  set(
    CMAKE_HIP_FLAGS
    "${CMAKE_HIP_FLAGS}"
    CACHE STRING
    "Flags used by the HIP compiler"
    FORCE
  )
endif()

include(CheckLanguage)
check_language(HIP)
if(NOT CMAKE_HIP_COMPILER)
  message(FATAL_ERROR "STRUCTURAL_ENABLE_HIP=ON requires a configured HIP compiler")
endif()
enable_language(HIP)

if(NOT CMAKE_HIP_COMPILER_ID STREQUAL "Clang")
  message(FATAL_ERROR "STRUCTURAL_ENABLE_HIP=ON requires the ROCm Clang HIP compiler")
endif()

if(NOT CMAKE_HIP_ARCHITECTURES)
  message(FATAL_ERROR "HIP builds must declare CMAKE_HIP_ARCHITECTURES from the approved device lane")
endif()
