cmake_minimum_required(VERSION 3.20)
project(structural_engine_native LANGUAGES CXX)

add_library(structural_engine_c_api STATIC
    cpp/structural_engine_c_api.cpp
    cpp/linear_frame3d_c_api.cpp
)

set_target_properties(structural_engine_c_api PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

target_include_directories(structural_engine_c_api
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/cpp
)

target_compile_features(structural_engine_c_api PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(structural_engine_c_api PRIVATE /W4 /WX)
else()
    target_compile_options(structural_engine_c_api PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Werror
    )
endif()
