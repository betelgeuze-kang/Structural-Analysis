include_guard(GLOBAL)

include(CheckLanguage)
check_language(HIP)
if(NOT CMAKE_HIP_COMPILER)
  message(FATAL_ERROR "STRUCTURAL_ENABLE_HIP=ON requires a configured HIP compiler")
endif()
enable_language(HIP)

if(NOT CMAKE_HIP_ARCHITECTURES)
  message(FATAL_ERROR "HIP builds must declare CMAKE_HIP_ARCHITECTURES from the approved device lane")
endif()
