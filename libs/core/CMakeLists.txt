add_library(pacioli_core)
add_library(Pacioli::core ALIAS pacioli_core)

target_sources(
  pacioli_core
  PRIVATE
    src/version.cpp
  PUBLIC
    FILE_SET HEADERS
    BASE_DIRS include
    FILES include/pacioli/version.hpp
)

target_compile_features(pacioli_core PUBLIC cxx_std_23)

target_include_directories(
  pacioli_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

set_target_properties(pacioli_core PROPERTIES OUTPUT_NAME pacioli_core)
