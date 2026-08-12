cmake_minimum_required(VERSION 3.22)

project(StructuralNative VERSION 0.1.0 LANGUAGES C CXX)

include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)
include(TestBigEndian)
include(${CMAKE_CURRENT_LIST_DIR}/../cmake/StructuralOptions.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../cmake/StructuralWarnings.cmake)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "C ABI v1 requires a 64-bit process data model")
endif()
test_big_endian(STRUCTURAL_HOST_IS_BIG_ENDIAN)
if(STRUCTURAL_HOST_IS_BIG_ENDIAN)
  message(FATAL_ERROR "C ABI v1 requires a little-endian host")
endif()

if(STRUCTURAL_ENABLE_HIP)
  include(${CMAKE_CURRENT_LIST_DIR}/../cmake/StructuralHip.cmake)
endif()

add_library(
  structural_model_ir STATIC
  src/model_ir/model_ir.cpp
  src/model_ir/sha256.cpp
)
add_library(Structural::model_ir ALIAS structural_model_ir)
set_target_properties(
  structural_model_ir
  PROPERTIES
    EXPORT_NAME model_ir
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
target_include_directories(
  structural_model_ir
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/model_ir
)
structural_set_warnings(structural_model_ir)
structural_enable_sanitizers(structural_model_ir)

add_library(structural_materials STATIC src/materials/materials.cpp)
add_library(Structural::materials ALIAS structural_materials)
set_target_properties(
  structural_materials
  PROPERTIES
    EXPORT_NAME materials
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
target_include_directories(
  structural_materials
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/materials
)
structural_set_warnings(structural_materials)
structural_enable_sanitizers(structural_materials)

add_library(structural_elements STATIC src/elements/reference_elements.cpp)
add_library(Structural::elements ALIAS structural_elements)
set_target_properties(
  structural_elements
  PROPERTIES
    EXPORT_NAME elements
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
target_include_directories(
  structural_elements
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/elements
    ${CMAKE_CURRENT_SOURCE_DIR}/src/materials
)
target_link_libraries(structural_elements PUBLIC structural_materials)
structural_set_warnings(structural_elements)
structural_enable_sanitizers(structural_elements)

add_library(structural_assembly STATIC src/assembly/dense_assembly.cpp)
add_library(Structural::assembly ALIAS structural_assembly)
set_target_properties(
  structural_assembly
  PROPERTIES
    EXPORT_NAME assembly
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
target_include_directories(
  structural_assembly
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/assembly
)
structural_set_warnings(structural_assembly)
structural_enable_sanitizers(structural_assembly)

if(STRUCTURAL_ENABLE_HIP)
  set(STRUCTURAL_REFERENCE_HIP_SOURCE src/hip/reference_elements_hip.hip.cpp)
  set(STRUCTURAL_SPARSE_HIP_SOURCE src/hip/sparse_linear_hip.hip.cpp)
  set_source_files_properties(${STRUCTURAL_REFERENCE_HIP_SOURCE} PROPERTIES LANGUAGE HIP)
  set_source_files_properties(${STRUCTURAL_SPARSE_HIP_SOURCE} PROPERTIES LANGUAGE HIP)
  set_property(
    DIRECTORY
    APPEND
    PROPERTY CMAKE_CONFIGURE_DEPENDS
      ${STRUCTURAL_REFERENCE_HIP_SOURCE}
      src/hip/reference_elements_hip.hpp
      ${STRUCTURAL_SPARSE_HIP_SOURCE}
      src/hip/sparse_linear_hip.hpp
  )
  file(READ ${STRUCTURAL_REFERENCE_HIP_SOURCE} STRUCTURAL_REFERENCE_HIP_SOURCE_TEXT)
  file(READ src/hip/reference_elements_hip.hpp STRUCTURAL_REFERENCE_HIP_HEADER_TEXT)
  string(
    SHA256
    STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256
    "${STRUCTURAL_REFERENCE_HIP_HEADER_TEXT}${STRUCTURAL_REFERENCE_HIP_SOURCE_TEXT}"
  )
  file(READ ${STRUCTURAL_SPARSE_HIP_SOURCE} STRUCTURAL_SPARSE_HIP_SOURCE_TEXT)
  file(READ src/hip/sparse_linear_hip.hpp STRUCTURAL_SPARSE_HIP_HEADER_TEXT)
  string(
    SHA256
    STRUCTURAL_SPARSE_HIP_SOURCE_SHA256
    "${STRUCTURAL_SPARSE_HIP_HEADER_TEXT}${STRUCTURAL_SPARSE_HIP_SOURCE_TEXT}"
  )
  list(GET CMAKE_HIP_ARCHITECTURES 0 STRUCTURAL_REFERENCE_HIP_PRIMARY_ARCH)
  string(REGEX REPLACE "^gfx" "" STRUCTURAL_REFERENCE_HIP_ISA_SUFFIX "${STRUCTURAL_REFERENCE_HIP_PRIMARY_ARCH}")
  set(
    STRUCTURAL_REFERENCE_HIP_ISA_FILE
    "${STRUCTURAL_HIP_DEVICE_LIB_PATH}/oclc_isa_version_${STRUCTURAL_REFERENCE_HIP_ISA_SUFFIX}.bc"
  )
  if(NOT EXISTS "${STRUCTURAL_REFERENCE_HIP_ISA_FILE}")
    message(FATAL_ERROR "HIP device libraries do not support ${STRUCTURAL_REFERENCE_HIP_PRIMARY_ARCH}")
  endif()
  file(SHA256 "${STRUCTURAL_HIP_DEVICE_LIB_PATH}/ocml.bc" STRUCTURAL_REFERENCE_HIP_OCML_SHA256)
  file(SHA256 "${STRUCTURAL_HIP_DEVICE_LIB_PATH}/ockl.bc" STRUCTURAL_REFERENCE_HIP_OCKL_SHA256)
  file(SHA256 "${STRUCTURAL_REFERENCE_HIP_ISA_FILE}" STRUCTURAL_REFERENCE_HIP_ISA_SHA256)
  string(
    SHA256
    STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256
    "${STRUCTURAL_REFERENCE_HIP_OCML_SHA256}${STRUCTURAL_REFERENCE_HIP_OCKL_SHA256}${STRUCTURAL_REFERENCE_HIP_ISA_SHA256}"
  )
  add_library(structural_elements_hip STATIC ${STRUCTURAL_REFERENCE_HIP_SOURCE})
  add_library(Structural::elements_hip ALIAS structural_elements_hip)
  set_target_properties(
    structural_elements_hip
    PROPERTIES
      EXPORT_NAME elements_hip
      HIP_STANDARD 20
      HIP_STANDARD_REQUIRED ON
      HIP_EXTENSIONS OFF
      CXX_VISIBILITY_PRESET hidden
      VISIBILITY_INLINES_HIDDEN YES
  )
  target_include_directories(
    structural_elements_hip
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/hip
      ${CMAKE_CURRENT_SOURCE_DIR}/src/assembly
      ${CMAKE_CURRENT_SOURCE_DIR}/src/elements
      ${CMAKE_CURRENT_SOURCE_DIR}/src/materials
  )
  target_link_libraries(
    structural_elements_hip
    PUBLIC
      structural_elements
      structural_assembly
  )
  target_compile_definitions(
    structural_elements_hip
    PRIVATE
      STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256="${STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256}"
      STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256="${STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256}"
      STRUCTURAL_REFERENCE_HIP_COMPILED_ARCHITECTURES="${CMAKE_HIP_ARCHITECTURES}"
  )
  target_compile_options(
    structural_elements_hip
    PRIVATE
      $<$<COMPILE_LANGUAGE:HIP>:-ffp-contract=off>
  )
  structural_set_warnings(structural_elements_hip)
endif()

add_library(
  structural_solver_cpu STATIC
  src/solver_cpu/generalized_eigen.cpp
  src/solver_cpu/story_frame.cpp
  src/solver_cpu/nonlinear_ndtha.cpp
  src/solver_cpu/nonlinear_static.cpp
  src/solver_cpu/sparse_linear.cpp
  src/solver_cpu/track_point_load.cpp
)
add_library(Structural::solver_cpu ALIAS structural_solver_cpu)
set_target_properties(
  structural_solver_cpu
  PROPERTIES
    EXPORT_NAME solver_cpu
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
target_include_directories(
  structural_solver_cpu
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/solver_cpu
)
structural_set_warnings(structural_solver_cpu)
structural_enable_sanitizers(structural_solver_cpu)

if(STRUCTURAL_ENABLE_HIP)
  add_library(structural_solver_hip STATIC ${STRUCTURAL_SPARSE_HIP_SOURCE})
  add_library(Structural::solver_hip ALIAS structural_solver_hip)
  set_target_properties(
    structural_solver_hip
    PROPERTIES
      EXPORT_NAME solver_hip
      HIP_STANDARD 20
      HIP_STANDARD_REQUIRED ON
      HIP_EXTENSIONS OFF
      CXX_VISIBILITY_PRESET hidden
      VISIBILITY_INLINES_HIDDEN YES
  )
  target_include_directories(
    structural_solver_hip
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/hip
      ${CMAKE_CURRENT_SOURCE_DIR}/src/solver_cpu
  )
  target_link_libraries(structural_solver_hip PUBLIC structural_solver_cpu)
  target_compile_definitions(
    structural_solver_hip
    PRIVATE
      STRUCTURAL_SPARSE_HIP_SOURCE_SHA256="${STRUCTURAL_SPARSE_HIP_SOURCE_SHA256}"
      STRUCTURAL_SPARSE_HIP_DEVICE_LIB_SHA256="${STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256}"
      STRUCTURAL_SPARSE_HIP_COMPILED_ARCHITECTURES="${CMAKE_HIP_ARCHITECTURES}"
  )
  target_compile_options(
    structural_solver_hip
    PRIVATE
      $<$<COMPILE_LANGUAGE:HIP>:-ffp-contract=off>
  )
  structural_set_warnings(structural_solver_hip)
endif()

add_library(structural_c_abi_v1 src/abi/abi_v1.cpp)
add_library(Structural::c_abi_v1 ALIAS structural_c_abi_v1)
target_link_libraries(
  structural_c_abi_v1
  PUBLIC
    structural_model_ir
    structural_elements
    structural_solver_cpu
)
target_compile_definitions(structural_c_abi_v1 PRIVATE STRUCTURAL_C_ABI_V1_BUILD=1)
set_target_properties(
  structural_c_abi_v1
  PROPERTIES
    EXPORT_NAME c_abi_v1
    OUTPUT_NAME structural_c_abi_v1
    VERSION ${PROJECT_VERSION}
    SOVERSION 1
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
structural_set_warnings(structural_c_abi_v1)
structural_enable_sanitizers(structural_c_abi_v1)
if(BUILD_SHARED_LIBS)
  if(APPLE)
    target_link_options(
      structural_c_abi_v1
      PRIVATE
        "LINKER:-exported_symbols_list,${CMAKE_CURRENT_SOURCE_DIR}/src/abi/structural_c_abi_v1.exports"
    )
  elseif(UNIX)
    target_link_options(
      structural_c_abi_v1
      PRIVATE
        "LINKER:--version-script=${CMAKE_CURRENT_SOURCE_DIR}/src/abi/structural_c_abi_v1.map"
    )
  endif()
endif()

if(STRUCTURAL_BUILD_TESTS)
  add_subdirectory(tests)
endif()

if(STRUCTURAL_BUILD_FUZZERS)
  add_subdirectory(tests/fuzz)
endif()

set(
  STRUCTURAL_INSTALL_TARGETS
  structural_model_ir
  structural_materials
  structural_elements
  structural_assembly
  structural_solver_cpu
  structural_c_abi_v1
)
install(
  TARGETS ${STRUCTURAL_INSTALL_TARGETS}
  EXPORT StructuralNativeTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
  INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
configure_package_config_file(
  cmake/StructuralNativeConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/StructuralNativeConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/StructuralNative
)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/StructuralNativeConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion
)
if(STRUCTURAL_ENABLE_HIP)
  set(STRUCTURAL_ENABLE_HIP_JSON true)
else()
  set(STRUCTURAL_ENABLE_HIP_JSON false)
endif()
configure_file(
  cmake/structural-native-build.json.in
  ${CMAKE_CURRENT_BINARY_DIR}/structural-native-build.json
  @ONLY
)
install(
  FILES
    ${CMAKE_CURRENT_BINARY_DIR}/StructuralNativeConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/StructuralNativeConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/StructuralNative
)
install(
  FILES ${CMAKE_CURRENT_BINARY_DIR}/structural-native-build.json
  DESTINATION ${CMAKE_INSTALL_DATADIR}/structural-native
)
install(
  FILES
    include/structural/abi_v1.h
    include/structural/model_ir_v1.h
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/structural
)
install(
  EXPORT StructuralNativeTargets
  FILE StructuralNativeTargets.cmake
  NAMESPACE Structural::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/StructuralNative
)
