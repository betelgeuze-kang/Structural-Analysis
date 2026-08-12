find_package(Threads REQUIRED)

add_executable(structural_abi_header_c11_smoke abi/header_c11_smoke.c)
target_link_libraries(structural_abi_header_c11_smoke PRIVATE structural_model_ir)
structural_set_warnings(structural_abi_header_c11_smoke)
structural_enable_sanitizers(structural_abi_header_c11_smoke)
add_test(NAME structural_abi_header_c11_smoke COMMAND structural_abi_header_c11_smoke)
set_tests_properties(structural_abi_header_c11_smoke PROPERTIES LABELS "abi")

add_executable(structural_abi_header_cpp20_smoke abi/header_cpp20_smoke.cpp)
target_link_libraries(structural_abi_header_cpp20_smoke PRIVATE structural_model_ir)
structural_set_warnings(structural_abi_header_cpp20_smoke)
structural_enable_sanitizers(structural_abi_header_cpp20_smoke)
add_test(NAME structural_abi_header_cpp20_smoke COMMAND structural_abi_header_cpp20_smoke)
set_tests_properties(structural_abi_header_cpp20_smoke PROPERTIES LABELS "abi")

add_executable(structural_abi_contract_tests abi/abi_contract_test.cpp)
target_link_libraries(
  structural_abi_contract_tests
  PRIVATE
    structural_c_abi_v1
    Threads::Threads
)
structural_set_warnings(structural_abi_contract_tests)
structural_enable_sanitizers(structural_abi_contract_tests)
add_test(NAME structural_abi_contract_tests COMMAND structural_abi_contract_tests)
set_tests_properties(structural_abi_contract_tests PROPERTIES LABELS "abi")

add_executable(
  structural_track_point_load_abi_tests
  abi/track_point_load_contract_test.cpp
)
target_link_libraries(structural_track_point_load_abi_tests PRIVATE structural_c_abi_v1)
structural_set_warnings(structural_track_point_load_abi_tests)
structural_enable_sanitizers(structural_track_point_load_abi_tests)
add_test(NAME structural_track_point_load_abi_tests COMMAND structural_track_point_load_abi_tests)
set_tests_properties(structural_track_point_load_abi_tests PROPERTIES LABELS "abi;solver_cpu;track")

add_executable(
  structural_nonlinear_static_abi_tests
  abi/nonlinear_static_contract_test.cpp
)
target_link_libraries(structural_nonlinear_static_abi_tests PRIVATE structural_c_abi_v1)
structural_set_warnings(structural_nonlinear_static_abi_tests)
structural_enable_sanitizers(structural_nonlinear_static_abi_tests)
add_test(NAME structural_nonlinear_static_abi_tests COMMAND structural_nonlinear_static_abi_tests)
set_tests_properties(
  structural_nonlinear_static_abi_tests
  PROPERTIES LABELS "abi;solver_cpu;nonlinear_static"
)

add_executable(
  structural_nonlinear_ndtha_abi_tests
  abi/nonlinear_ndtha_contract_test.cpp
)
target_link_libraries(structural_nonlinear_ndtha_abi_tests PRIVATE structural_c_abi_v1)
structural_set_warnings(structural_nonlinear_ndtha_abi_tests)
structural_enable_sanitizers(structural_nonlinear_ndtha_abi_tests)
add_test(NAME structural_nonlinear_ndtha_abi_tests COMMAND structural_nonlinear_ndtha_abi_tests)
set_tests_properties(
  structural_nonlinear_ndtha_abi_tests
  PROPERTIES LABELS "abi;solver_cpu;nonlinear_ndtha"
)

add_executable(
  structural_reference_elements_abi_tests
  abi/reference_elements_contract_test.cpp
)
target_link_libraries(structural_reference_elements_abi_tests PRIVATE structural_c_abi_v1)
structural_set_warnings(structural_reference_elements_abi_tests)
structural_enable_sanitizers(structural_reference_elements_abi_tests)
add_test(NAME structural_reference_elements_abi_tests COMMAND structural_reference_elements_abi_tests)
set_tests_properties(
  structural_reference_elements_abi_tests
  PROPERTIES LABELS "abi;elements;materials;solver_cpu"
)

add_executable(
  structural_sparse_linear_abi_tests
  abi/sparse_linear_contract_test.cpp
)
target_link_libraries(
  structural_sparse_linear_abi_tests
  PRIVATE
    structural_c_abi_v1
    Threads::Threads
)
structural_set_warnings(structural_sparse_linear_abi_tests)
structural_enable_sanitizers(structural_sparse_linear_abi_tests)
add_test(NAME structural_sparse_linear_abi_tests COMMAND structural_sparse_linear_abi_tests)
set_tests_properties(
  structural_sparse_linear_abi_tests
  PROPERTIES LABELS "abi;solver_cpu;sparse_linear"
)

add_executable(structural_abi_link_smoke_c abi/link_smoke.c)
target_link_libraries(structural_abi_link_smoke_c PRIVATE structural_c_abi_v1)
structural_set_warnings(structural_abi_link_smoke_c)
structural_enable_sanitizers(structural_abi_link_smoke_c)
add_test(NAME structural_abi_link_smoke_c COMMAND structural_abi_link_smoke_c)
set_tests_properties(structural_abi_link_smoke_c PROPERTIES LABELS "abi;link")

add_executable(structural_model_ir_contract_tests model_ir/model_ir_contract_test.cpp)
target_link_libraries(
  structural_model_ir_contract_tests
  PRIVATE
    structural_c_abi_v1
    Threads::Threads
)
structural_set_warnings(structural_model_ir_contract_tests)
structural_enable_sanitizers(structural_model_ir_contract_tests)
add_test(NAME structural_model_ir_contract_tests COMMAND structural_model_ir_contract_tests)
set_tests_properties(structural_model_ir_contract_tests PROPERTIES LABELS "abi;modelir")

add_executable(structural_track_point_load_cpu_tests solver_cpu/track_point_load_test.cpp)
target_include_directories(
  structural_track_point_load_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_track_point_load_cpu_tests PRIVATE structural_solver_cpu)
structural_set_warnings(structural_track_point_load_cpu_tests)
structural_enable_sanitizers(structural_track_point_load_cpu_tests)
add_test(NAME structural_track_point_load_cpu_tests COMMAND structural_track_point_load_cpu_tests)
set_tests_properties(structural_track_point_load_cpu_tests PROPERTIES LABELS "solver_cpu;track")

add_executable(structural_nonlinear_static_cpu_tests solver_cpu/nonlinear_static_test.cpp)
target_include_directories(
  structural_nonlinear_static_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_nonlinear_static_cpu_tests PRIVATE structural_solver_cpu)
structural_set_warnings(structural_nonlinear_static_cpu_tests)
structural_enable_sanitizers(structural_nonlinear_static_cpu_tests)
add_test(NAME structural_nonlinear_static_cpu_tests COMMAND structural_nonlinear_static_cpu_tests)
set_tests_properties(
  structural_nonlinear_static_cpu_tests
  PROPERTIES LABELS "solver_cpu;nonlinear_static"
)

add_executable(structural_nonlinear_ndtha_cpu_tests solver_cpu/nonlinear_ndtha_test.cpp)
target_include_directories(
  structural_nonlinear_ndtha_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_nonlinear_ndtha_cpu_tests PRIVATE structural_solver_cpu)
structural_set_warnings(structural_nonlinear_ndtha_cpu_tests)
structural_enable_sanitizers(structural_nonlinear_ndtha_cpu_tests)
add_test(NAME structural_nonlinear_ndtha_cpu_tests COMMAND structural_nonlinear_ndtha_cpu_tests)
set_tests_properties(
  structural_nonlinear_ndtha_cpu_tests
  PROPERTIES LABELS "solver_cpu;nonlinear_ndtha"
)

add_executable(structural_sparse_linear_cpu_tests solver_cpu/sparse_linear_test.cpp)
target_include_directories(
  structural_sparse_linear_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_sparse_linear_cpu_tests PRIVATE structural_solver_cpu)
structural_set_warnings(structural_sparse_linear_cpu_tests)
structural_enable_sanitizers(structural_sparse_linear_cpu_tests)
add_test(NAME structural_sparse_linear_cpu_tests COMMAND structural_sparse_linear_cpu_tests)
set_tests_properties(
  structural_sparse_linear_cpu_tests
  PROPERTIES LABELS "solver_cpu;sparse_linear"
)

add_executable(
  structural_generalized_eigen_cpu_tests
  solver_cpu/generalized_eigen_test.cpp
)
target_include_directories(
  structural_generalized_eigen_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_generalized_eigen_cpu_tests PRIVATE structural_solver_cpu)
structural_set_warnings(structural_generalized_eigen_cpu_tests)
structural_enable_sanitizers(structural_generalized_eigen_cpu_tests)
add_test(
  NAME structural_generalized_eigen_cpu_tests
  COMMAND structural_generalized_eigen_cpu_tests
)
set_tests_properties(
  structural_generalized_eigen_cpu_tests
  PROPERTIES LABELS "solver_cpu;generalized_eigen;modal;buckling"
)

add_executable(structural_materials_cpu_tests materials/materials_test.cpp)
target_include_directories(
  structural_materials_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/materials
)
target_link_libraries(structural_materials_cpu_tests PRIVATE structural_materials)
structural_set_warnings(structural_materials_cpu_tests)
structural_enable_sanitizers(structural_materials_cpu_tests)
add_test(NAME structural_materials_cpu_tests COMMAND structural_materials_cpu_tests)
set_tests_properties(
  structural_materials_cpu_tests
  PROPERTIES LABELS "materials;solver_cpu"
)

add_executable(structural_reference_elements_cpu_tests elements/reference_elements_test.cpp)
target_include_directories(
  structural_reference_elements_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/elements
    ${PROJECT_SOURCE_DIR}/src/materials
)
target_link_libraries(
  structural_reference_elements_cpu_tests
  PRIVATE
    structural_elements
    structural_materials
)
structural_set_warnings(structural_reference_elements_cpu_tests)
structural_enable_sanitizers(structural_reference_elements_cpu_tests)
add_test(NAME structural_reference_elements_cpu_tests COMMAND structural_reference_elements_cpu_tests)
set_tests_properties(
  structural_reference_elements_cpu_tests
  PROPERTIES LABELS "elements;materials;solver_cpu"
)

add_executable(structural_dense_assembly_cpu_tests assembly/dense_assembly_test.cpp)
target_include_directories(
  structural_dense_assembly_cpu_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/assembly
)
target_link_libraries(structural_dense_assembly_cpu_tests PRIVATE structural_assembly)
structural_set_warnings(structural_dense_assembly_cpu_tests)
structural_enable_sanitizers(structural_dense_assembly_cpu_tests)
add_test(NAME structural_dense_assembly_cpu_tests COMMAND structural_dense_assembly_cpu_tests)
set_tests_properties(
  structural_dense_assembly_cpu_tests
  PROPERTIES LABELS "assembly;solver_cpu"
)

if(STRUCTURAL_ENABLE_HIP)
  set(STRUCTURAL_REFERENCE_HIP_TEST_SOURCE hip/reference_elements_hip_parity_test.hip.cpp)
  set(STRUCTURAL_SPARSE_HIP_TEST_SOURCE hip/sparse_linear_hip_parity_test.hip.cpp)
  set_source_files_properties(${STRUCTURAL_REFERENCE_HIP_TEST_SOURCE} PROPERTIES LANGUAGE HIP)
  set_source_files_properties(${STRUCTURAL_SPARSE_HIP_TEST_SOURCE} PROPERTIES LANGUAGE HIP)
  add_executable(
    structural_reference_elements_hip_parity_tests
    ${STRUCTURAL_REFERENCE_HIP_TEST_SOURCE}
  )
  set_target_properties(
    structural_reference_elements_hip_parity_tests
    PROPERTIES
      HIP_STANDARD 20
      HIP_STANDARD_REQUIRED ON
      HIP_EXTENSIONS OFF
  )
  target_include_directories(
    structural_reference_elements_hip_parity_tests
    PRIVATE
      ${PROJECT_SOURCE_DIR}/src/hip
      ${PROJECT_SOURCE_DIR}/src/assembly
      ${PROJECT_SOURCE_DIR}/src/elements
      ${PROJECT_SOURCE_DIR}/src/materials
  )
  target_link_libraries(
    structural_reference_elements_hip_parity_tests
    PRIVATE
      structural_elements_hip
      structural_elements
      structural_assembly
  )
  target_compile_options(
    structural_reference_elements_hip_parity_tests
    PRIVATE
      $<$<COMPILE_LANGUAGE:HIP>:-ffp-contract=off>
  )
  structural_set_warnings(structural_reference_elements_hip_parity_tests)
  add_test(
    NAME structural_reference_elements_hip_parity_tests
    COMMAND structural_reference_elements_hip_parity_tests
  )
  set_tests_properties(
    structural_reference_elements_hip_parity_tests
    PROPERTIES
      LABELS "hip;hip-dedicated;elements;assembly"
      RESOURCE_LOCK "structural_rocm_device_0"
      TIMEOUT 120
  )

  add_executable(
    structural_sparse_linear_hip_parity_tests
    ${STRUCTURAL_SPARSE_HIP_TEST_SOURCE}
  )
  set_target_properties(
    structural_sparse_linear_hip_parity_tests
    PROPERTIES
      HIP_STANDARD 20
      HIP_STANDARD_REQUIRED ON
      HIP_EXTENSIONS OFF
  )
  target_include_directories(
    structural_sparse_linear_hip_parity_tests
    PRIVATE
      ${PROJECT_SOURCE_DIR}/src/hip
      ${PROJECT_SOURCE_DIR}/src/solver_cpu
  )
  target_link_libraries(
    structural_sparse_linear_hip_parity_tests
    PRIVATE
      structural_solver_hip
      structural_solver_cpu
  )
  target_compile_options(
    structural_sparse_linear_hip_parity_tests
    PRIVATE
      $<$<COMPILE_LANGUAGE:HIP>:-ffp-contract=off>
  )
  structural_set_warnings(structural_sparse_linear_hip_parity_tests)
  add_test(
    NAME structural_sparse_linear_hip_parity_tests
    COMMAND structural_sparse_linear_hip_parity_tests
  )
  set_tests_properties(
    structural_sparse_linear_hip_parity_tests
    PROPERTIES
      LABELS "hip;hip-dedicated;solver_hip;sparse_linear"
      RESOURCE_LOCK "structural_rocm_device_0"
      TIMEOUT 120
  )
endif()
