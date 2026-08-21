cmake_minimum_required(VERSION 3.22)

# The public source remains C11. CXX is enabled so CMake can honor the
# imported static archive's CXX link language and add its runtime libraries.
project(StructuralNativePackageConsumer LANGUAGES C CXX)

find_package(StructuralNative CONFIG REQUIRED)

add_executable(structural_native_package_consumer main.c)
target_link_libraries(structural_native_package_consumer PRIVATE Structural::c_abi_v1)
