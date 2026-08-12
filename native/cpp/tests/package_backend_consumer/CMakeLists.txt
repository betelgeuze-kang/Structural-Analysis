cmake_minimum_required(VERSION 3.22)

project(StructuralNativeBackendPackageConsumer LANGUAGES CXX)

find_package(StructuralNative CONFIG REQUIRED)

add_executable(structural_native_backend_package_consumer main.cpp)
target_compile_features(structural_native_backend_package_consumer PRIVATE cxx_std_20)
target_link_libraries(
  structural_native_backend_package_consumer
  PRIVATE Structural::c_abi_v1
)
