cmake_minimum_required(VERSION 3.24)
project(luca VERSION 0.1.0 LANGUAGES CXX)

set(LUCA_STANDALONE ${PROJECT_IS_TOP_LEVEL})

add_library(luca_ledger INTERFACE)
add_library(luca::ledger ALIAS luca_ledger)
set_target_properties(luca_ledger PROPERTIES EXPORT_NAME ledger)
target_compile_features(luca_ledger INTERFACE cxx_std_23)
target_include_directories(luca_ledger INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/ledger/include>)

add_library(luca_portfolio INTERFACE)
add_library(luca::portfolio ALIAS luca_portfolio)
set_target_properties(luca_portfolio PROPERTIES EXPORT_NAME portfolio)
target_compile_features(luca_portfolio INTERFACE cxx_std_23)
target_include_directories(luca_portfolio INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/portfolio/include>)
target_link_libraries(luca_portfolio INTERFACE luca::ledger)

add_library(luca_reconciliation INTERFACE)
add_library(luca::reconciliation ALIAS luca_reconciliation)
set_target_properties(luca_reconciliation PROPERTIES EXPORT_NAME reconciliation)
target_compile_features(luca_reconciliation INTERFACE cxx_std_23)
target_include_directories(luca_reconciliation INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/reconciliation/include>)
target_link_libraries(luca_reconciliation INTERFACE luca::portfolio)

add_library(luca INTERFACE)
add_library(luca::luca ALIAS luca)
set_target_properties(luca PROPERTIES EXPORT_NAME luca)
target_link_libraries(luca INTERFACE
  luca::ledger
  luca::portfolio
  luca::reconciliation)

option(LUCA_BUILD_TESTS "Build LUCA tests" ${LUCA_STANDALONE})
option(LUCA_BUILD_EXAMPLES "Build LUCA examples" ${LUCA_STANDALONE})
option(LUCA_BUILD_BENCHMARKS "Build LUCA benchmarks" OFF)
if(LUCA_BUILD_TESTS)
  enable_testing()
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_executable(luca_smoke_test tests/smoke.cpp)
  target_link_libraries(luca_smoke_test PRIVATE luca::ledger)
  add_test(NAME luca_smoke_test COMMAND luca_smoke_test)

  add_executable(luca_core_values_test tests/unit/core_values_test.cpp)
  target_link_libraries(luca_core_values_test PRIVATE luca::ledger)
  add_test(NAME luca_core_values_test COMMAND luca_core_values_test)

  add_executable(luca_provenance_test tests/unit/provenance_test.cpp)
  target_link_libraries(luca_provenance_test PRIVATE luca::ledger)
  add_test(NAME luca_provenance_test COMMAND luca_provenance_test)

  add_executable(luca_economic_event_test tests/unit/economic_event_test.cpp)
  target_link_libraries(luca_economic_event_test PRIVATE luca::ledger)
  add_test(NAME luca_economic_event_test COMMAND luca_economic_event_test)

  add_executable(luca_ledger_test tests/unit/ledger_test.cpp)
  target_link_libraries(luca_ledger_test PRIVATE luca::ledger)
  add_test(NAME luca_ledger_test COMMAND luca_ledger_test)

  add_executable(luca_position_projection_test tests/unit/position_projection_test.cpp)
  target_link_libraries(luca_position_projection_test PRIVATE luca::portfolio)
  add_test(NAME luca_position_projection_test COMMAND luca_position_projection_test)

  add_executable(luca_position_reconciliation_test tests/unit/position_reconciliation_test.cpp)
  target_link_libraries(luca_position_reconciliation_test PRIVATE luca::reconciliation)
  add_test(NAME luca_position_reconciliation_test COMMAND luca_position_reconciliation_test)

  add_executable(luca_cash_reconciliation_test tests/unit/cash_reconciliation_test.cpp)
  target_link_libraries(luca_cash_reconciliation_test PRIVATE luca::reconciliation)
  add_test(NAME luca_cash_reconciliation_test COMMAND luca_cash_reconciliation_test)

  add_executable(luca_cash_projection_test tests/unit/cash_projection_test.cpp)
  target_link_libraries(luca_cash_projection_test PRIVATE luca::portfolio)
  add_test(NAME luca_cash_projection_test COMMAND luca_cash_projection_test)

  add_executable(luca_settlement_projection_test tests/unit/settlement_projection_test.cpp)
  target_link_libraries(luca_settlement_projection_test PRIVATE luca::portfolio)
  add_test(NAME luca_settlement_projection_test COMMAND luca_settlement_projection_test)

  add_test(
    NAME luca_conformance_test
    COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests/conformance -p "test_*.py"
  )
  set_tests_properties(luca_conformance_test PROPERTIES
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
  add_executable(luca_conformance_engine_test
    tests/conformance/engine/conformance_engine_test.cpp
    ${CONFORMANCE_ARTIFACT})
  target_link_libraries(luca_conformance_engine_test PRIVATE luca::portfolio)
  add_test(NAME luca_conformance_engine_test
    COMMAND luca_conformance_engine_test ${CONFORMANCE_ARTIFACT})
endif()

if(LUCA_BUILD_BENCHMARKS)
  add_executable(luca_benchmarks
    tests/benchmarks/benchmark_main.cpp
    tests/benchmarks/ledger_benchmark.cpp
    tests/benchmarks/projection_benchmark.cpp
    tests/benchmarks/reconciliation_benchmark.cpp)
  target_link_libraries(luca_benchmarks PRIVATE luca::reconciliation)
  target_compile_definitions(luca_benchmarks PRIVATE
    LUCA_BENCHMARK_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    LUCA_BENCHMARK_COMPILER="${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
endif()
