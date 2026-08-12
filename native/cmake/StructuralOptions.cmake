include_guard(GLOBAL)

option(STRUCTURAL_BUILD_TESTS "Build native C/C++ contract tests" ON)
option(STRUCTURAL_BUILD_FUZZERS "Build bounded libFuzzer harnesses" OFF)
option(STRUCTURAL_ENABLE_HIP "Enable the ROCm/HIP backend" OFF)
set(
  STRUCTURAL_ROCM_ROOT
  ""
  CACHE PATH
  "ROCm root used by the dedicated HIP build (for example /opt/rocm)"
)
set(
  STRUCTURAL_HIP_DEVICE_LIB_PATH
  ""
  CACHE PATH
  "Directory containing ocml.bc, ockl.bc and architecture bitcode"
)
option(STRUCTURAL_ENABLE_SANITIZERS "Enable ASan and UBSan on hosted CPU targets" OFF)
option(STRUCTURAL_WARNINGS_AS_ERRORS "Treat native compiler warnings as errors" OFF)
