cmake_minimum_required(VERSION 3.24)
project(luca_checkpoint_continuation LANGUAGES CXX)

# Deliberately independent of root targets/custom conformance generation.
get_filename_component(LUCA_SOURCE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
add_library(checkpoint_continuation_headers INTERFACE)
target_compile_features(checkpoint_continuation_headers INTERFACE cxx_std_23)
target_include_directories(checkpoint_continuation_headers INTERFACE
  "${LUCA_SOURCE_ROOT}/libs/ledger/include"
  "${LUCA_SOURCE_ROOT}/libs/portfolio/include")

add_executable(checkpoint_continuation main.cpp)
target_link_libraries(checkpoint_continuation PRIVATE checkpoint_continuation_headers)
set_target_properties(checkpoint_continuation PROPERTIES CXX_EXTENSIONS OFF)

# Compile and link the authored checks only when explicitly requested. No
# enable_testing(), add_test(), custom commands, or post-build execution.
add_executable(checkpoint_result_compile EXCLUDE_FROM_ALL
  "${LUCA_SOURCE_ROOT}/tests/unit/checkpoint_result_test.cpp")
target_link_libraries(checkpoint_result_compile PRIVATE checkpoint_continuation_headers)
set_target_properties(checkpoint_result_compile PROPERTIES CXX_EXTENSIONS OFF)
