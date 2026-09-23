cmake_minimum_required(VERSION 3.24)
project(luca_parent_consumer LANGUAGES CXX)

set(LUCA_SOURCE_DIR "" CACHE PATH "Path to the LUCA source tree")
if(NOT LUCA_SOURCE_DIR)
  message(FATAL_ERROR "LUCA_SOURCE_DIR is required")
endif()

option(LUCA_PARENT_CONSUMER_ALLOW_PYTHON
  "Allow the nested LUCA project to discover Python" OFF)
if(NOT LUCA_PARENT_CONSUMER_ALLOW_PYTHON)
  set(CMAKE_DISABLE_FIND_PACKAGE_Python3 TRUE)
endif()

include(CTest)
add_subdirectory("${LUCA_SOURCE_DIR}" luca)

if(NOT TARGET luca::luca)
  message(FATAL_ERROR "The nested LUCA project did not expose luca::luca")
endif()

add_executable(luca_parent_consumer main.cpp)
target_link_libraries(luca_parent_consumer PRIVATE luca::luca)

add_test(NAME luca_parent_consumer_run COMMAND luca_parent_consumer)
set_tests_properties(luca_parent_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
