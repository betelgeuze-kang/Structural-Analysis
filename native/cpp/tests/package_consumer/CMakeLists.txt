cmake_minimum_required(VERSION 3.22)

project(StructuralNativePackageConsumer LANGUAGES C)

find_package(StructuralNative CONFIG REQUIRED)

add_executable(structural_native_package_consumer main.c)
target_link_libraries(structural_native_package_consumer PRIVATE Structural::c_abi_v1)
