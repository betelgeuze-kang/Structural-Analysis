cmake_minimum_required(VERSION 3.22)

project(StructuralNative VERSION 0.1.0 LANGUAGES C CXX)

include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)
include(TestBigEndian)
include(${CMAKE_CURRENT_LIST_DIR}/../cmake/StructuralOptions.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../cmake/StructuralWarnings.cmake)

find_package(Threads REQUIRED)

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

add_library(
  structural_c_abi_v1
  src/abi/abi_v1.cpp
  src/frame3d/linear_frame3d.cpp
)
add_library(Structural::c_abi_v1 ALIAS structural_c_abi_v1)
target_link_libraries(structural_c_abi_v1 PUBLIC structural_model_ir Threads::Threads)
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

install(
  TARGETS structural_model_ir structural_c_abi_v1
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
