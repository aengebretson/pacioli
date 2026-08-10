cmake_minimum_required(VERSION 3.24)
project(pacioli VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(pacioli INTERFACE)
target_include_directories(pacioli INTERFACE
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/ledger/include
  ${CMAKE_CURRENT_SOURCE_DIR}/include)

option(PACIOLI_BUILD_TESTS "Build tests" ON)
if(PACIOLI_BUILD_TESTS)
  enable_testing()
  add_executable(pacioli_smoke_test tests/smoke.cpp)
  target_link_libraries(pacioli_smoke_test PRIVATE pacioli)
  add_test(NAME pacioli_smoke_test COMMAND pacioli_smoke_test)

  add_executable(pacioli_core_values_test tests/unit/core_values_test.cpp)
  target_link_libraries(pacioli_core_values_test PRIVATE pacioli)
  add_test(NAME pacioli_core_values_test COMMAND pacioli_core_values_test)
endif()
