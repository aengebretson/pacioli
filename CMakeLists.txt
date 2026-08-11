cmake_minimum_required(VERSION 3.24)
project(pacioli VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(pacioli INTERFACE)
target_include_directories(pacioli INTERFACE
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/ledger/include
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/portfolio/include
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/reconciliation/include
  ${CMAKE_CURRENT_SOURCE_DIR}/include)

option(PACIOLI_BUILD_TESTS "Build tests" ON)
option(PACIOLI_BUILD_BENCHMARKS "Build reproducible performance benchmarks" OFF)
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

  add_executable(pacioli_position_projection_test tests/unit/position_projection_test.cpp)
  target_link_libraries(pacioli_position_projection_test PRIVATE pacioli)
  add_test(NAME pacioli_position_projection_test COMMAND pacioli_position_projection_test)

  add_executable(pacioli_position_reconciliation_test tests/unit/position_reconciliation_test.cpp)
  target_link_libraries(pacioli_position_reconciliation_test PRIVATE pacioli)
  add_test(NAME pacioli_position_reconciliation_test COMMAND pacioli_position_reconciliation_test)

  add_executable(pacioli_cash_reconciliation_test tests/unit/cash_reconciliation_test.cpp)
  target_link_libraries(pacioli_cash_reconciliation_test PRIVATE pacioli)
  add_test(NAME pacioli_cash_reconciliation_test COMMAND pacioli_cash_reconciliation_test)

  add_executable(pacioli_cash_projection_test tests/unit/cash_projection_test.cpp)
  target_link_libraries(pacioli_cash_projection_test PRIVATE pacioli)
  add_test(NAME pacioli_cash_projection_test COMMAND pacioli_cash_projection_test)

  add_executable(pacioli_settlement_projection_test tests/unit/settlement_projection_test.cpp)
  target_link_libraries(pacioli_settlement_projection_test PRIVATE pacioli)
  add_test(NAME pacioli_settlement_projection_test COMMAND pacioli_settlement_projection_test)

  add_test(
    NAME pacioli_conformance_test
    COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests/conformance -p "test_*.py"
  )
  set_tests_properties(pacioli_conformance_test PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

  set(CONFORMANCE_ARTIFACT ${CMAKE_CURRENT_BINARY_DIR}/conformance/fixtures.tsv)
  file(GLOB_RECURSE CONFORMANCE_FIXTURES CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/*.json)
  add_custom_command(
    OUTPUT ${CONFORMANCE_ARTIFACT}
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/generate_engine_fixture.py
      --root ${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance
      --output ${CONFORMANCE_ARTIFACT}
    DEPENDS ${CONFORMANCE_FIXTURES}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/harness.py
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/generate_engine_fixture.py
    VERBATIM)
  add_executable(pacioli_conformance_engine_test
    tests/conformance/engine/conformance_engine_test.cpp
    ${CONFORMANCE_ARTIFACT})
  target_link_libraries(pacioli_conformance_engine_test PRIVATE pacioli)
  add_test(NAME pacioli_conformance_engine_test
    COMMAND pacioli_conformance_engine_test ${CONFORMANCE_ARTIFACT})
endif()

if(PACIOLI_BUILD_BENCHMARKS)
  add_executable(pacioli_benchmarks
    tests/benchmarks/benchmark_main.cpp
    tests/benchmarks/ledger_benchmark.cpp
    tests/benchmarks/projection_benchmark.cpp
    tests/benchmarks/reconciliation_benchmark.cpp)
  target_link_libraries(pacioli_benchmarks PRIVATE pacioli)
  target_compile_definitions(pacioli_benchmarks PRIVATE
    LUCA_BENCHMARK_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    LUCA_BENCHMARK_COMPILER="${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
endif()
