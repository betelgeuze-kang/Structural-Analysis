if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "STRUCTURAL_BUILD_FUZZERS requires Clang libFuzzer")
endif()

add_executable(structural_abi_buffer_fuzz abi_buffer_fuzz.cpp)
target_link_libraries(structural_abi_buffer_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_abi_buffer_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_abi_buffer_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_abi_buffer_fuzz)

add_executable(structural_track_point_load_fuzz track_point_load_fuzz.cpp)
target_link_libraries(structural_track_point_load_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_track_point_load_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_track_point_load_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_track_point_load_fuzz)

add_executable(structural_nonlinear_static_fuzz nonlinear_static_fuzz.cpp)
target_link_libraries(structural_nonlinear_static_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_nonlinear_static_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_nonlinear_static_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_nonlinear_static_fuzz)

add_executable(structural_nonlinear_ndtha_fuzz nonlinear_ndtha_fuzz.cpp)
target_link_libraries(structural_nonlinear_ndtha_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_nonlinear_ndtha_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_nonlinear_ndtha_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_nonlinear_ndtha_fuzz)

add_executable(structural_nonlinear_ndtha_restart_fuzz nonlinear_ndtha_restart_fuzz.cpp)
target_link_libraries(structural_nonlinear_ndtha_restart_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_nonlinear_ndtha_restart_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_nonlinear_ndtha_restart_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_nonlinear_ndtha_restart_fuzz)

add_executable(structural_reference_elements_fuzz reference_elements_fuzz.cpp)
target_link_libraries(structural_reference_elements_fuzz PRIVATE structural_c_abi_v1)
target_compile_options(
  structural_reference_elements_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_reference_elements_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_reference_elements_fuzz)

add_executable(structural_sparse_linear_fuzz sparse_linear_fuzz.cpp)
target_include_directories(
  structural_sparse_linear_fuzz
  PRIVATE
    ${PROJECT_SOURCE_DIR}/src/solver_cpu
)
target_link_libraries(structural_sparse_linear_fuzz PRIVATE structural_solver_cpu)
target_compile_options(
  structural_sparse_linear_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(
  structural_sparse_linear_fuzz
  PRIVATE
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
structural_set_warnings(structural_sparse_linear_fuzz)

add_custom_target(
  structural_native_fuzzers
  DEPENDS
    structural_abi_buffer_fuzz
    structural_track_point_load_fuzz
    structural_nonlinear_static_fuzz
    structural_nonlinear_ndtha_fuzz
    structural_nonlinear_ndtha_restart_fuzz
    structural_reference_elements_fuzz
    structural_sparse_linear_fuzz
)
add_test(
  NAME structural_abi_buffer_fuzz_smoke
  COMMAND structural_abi_buffer_fuzz -runs=256
)
set_tests_properties(
  structural_abi_buffer_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_track_point_load_fuzz_smoke
  COMMAND structural_track_point_load_fuzz -runs=256
)
set_tests_properties(
  structural_track_point_load_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_nonlinear_static_fuzz_smoke
  COMMAND structural_nonlinear_static_fuzz -runs=256
)
set_tests_properties(
  structural_nonlinear_static_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_nonlinear_ndtha_fuzz_smoke
  COMMAND structural_nonlinear_ndtha_fuzz -runs=256
)
set_tests_properties(
  structural_nonlinear_ndtha_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_nonlinear_ndtha_restart_fuzz_smoke
  COMMAND structural_nonlinear_ndtha_restart_fuzz -runs=256
)
set_tests_properties(
  structural_nonlinear_ndtha_restart_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_reference_elements_fuzz_smoke
  COMMAND structural_reference_elements_fuzz -runs=256
)
set_tests_properties(
  structural_reference_elements_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke"
    TIMEOUT 30
)
add_test(
  NAME structural_sparse_linear_fuzz_smoke
  COMMAND structural_sparse_linear_fuzz -runs=256
)
set_tests_properties(
  structural_sparse_linear_fuzz_smoke
  PROPERTIES
    LABELS "fuzz-smoke;sparse_linear"
    TIMEOUT 30
)
