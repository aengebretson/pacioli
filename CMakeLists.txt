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
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_executable(pacioli_smoke_test tests/smoke.cpp)
  target_link_libraries(pacioli_smoke_test PRIVATE pacioli)
  add_test(NAME pacioli_smoke_test COMMAND pacioli_smoke_test)

  add_executable(pacioli_core_values_test tests/unit/core_values_test.cpp)
  target_link_libraries(pacioli_core_values_test PRIVATE pacioli)
  add_test(NAME pacioli_core_values_test COMMAND pacioli_core_values_test)

  add_executable(pacioli_provenance_test tests/unit/provenance_test.cpp)
  target_link_libraries(pacioli_provenance_test PRIVATE pacioli)
  add_test(NAME pacioli_provenance_test COMMAND pacioli_provenance_test)

  add_executable(pacioli_economic_event_test tests/unit/economic_event_test.cpp)
  target_link_libraries(pacioli_economic_event_test PRIVATE pacioli)
  add_test(NAME pacioli_economic_event_test COMMAND pacioli_economic_event_test)

  add_executable(pacioli_ledger_test tests/unit/ledger_test.cpp)
  target_link_libraries(pacioli_ledger_test PRIVATE pacioli)
  add_test(NAME pacioli_ledger_test COMMAND pacioli_ledger_test)

  add_test(
    NAME pacioli_conformance_test
    COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests/conformance -p "test_*.py"
  )
  set_tests_properties(pacioli_conformance_test PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
endif()
