cmake_minimum_required(VERSION 3.24)
project(pacioli VERSION 0.1.0 LANGUAGES CXX)

include(CMakePackageConfigHelpers)
include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(luca_ledger INTERFACE)
add_library(luca::ledger ALIAS luca_ledger)
set_target_properties(luca_ledger PROPERTIES EXPORT_NAME ledger)
target_compile_features(luca_ledger INTERFACE cxx_std_23)
target_include_directories(luca_ledger INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/ledger/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)

add_library(luca_portfolio INTERFACE)
add_library(luca::portfolio ALIAS luca_portfolio)
set_target_properties(luca_portfolio PROPERTIES EXPORT_NAME portfolio)
target_compile_features(luca_portfolio INTERFACE cxx_std_23)
target_include_directories(luca_portfolio INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/portfolio/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_link_libraries(luca_portfolio INTERFACE luca::ledger)

add_library(luca_reconciliation INTERFACE)
add_library(luca::reconciliation ALIAS luca_reconciliation)
set_target_properties(luca_reconciliation PROPERTIES EXPORT_NAME reconciliation)
target_compile_features(luca_reconciliation INTERFACE cxx_std_23)
target_include_directories(luca_reconciliation INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/reconciliation/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_link_libraries(luca_reconciliation INTERFACE
  luca::portfolio
  luca::ledger)

add_library(pacioli INTERFACE)
add_library(luca::luca ALIAS pacioli)
set_target_properties(pacioli PROPERTIES EXPORT_NAME luca)
target_compile_features(pacioli INTERFACE cxx_std_23)
target_include_directories(pacioli INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_link_libraries(pacioli INTERFACE
  luca::ledger
  luca::portfolio
  luca::reconciliation)

install(
  TARGETS
    luca_ledger
    luca_portfolio
    luca_reconciliation
    pacioli
  EXPORT LucaTargets)
install(
  DIRECTORY
    libs/ledger/include/
    libs/portfolio/include/
    libs/reconciliation/include/
    include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
  FILES_MATCHING PATTERN "*.hpp")
install(
  EXPORT LucaTargets
  FILE LucaTargets.cmake
  NAMESPACE luca::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Luca)

configure_package_config_file(
  cmake/LucaConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/LucaConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Luca)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/LucaConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion)
install(
  FILES
    ${CMAKE_CURRENT_BINARY_DIR}/LucaConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/LucaConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Luca)

option(PACIOLI_BUILD_TESTS "Build tests" ${PROJECT_IS_TOP_LEVEL})
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

  add_executable(pacioli_canonical_serialization_test
    tests/unit/canonical_serialization_test.cpp)
  target_link_libraries(pacioli_canonical_serialization_test PRIVATE luca::luca)
  add_test(NAME pacioli_canonical_serialization_test
    COMMAND pacioli_canonical_serialization_test)

  add_executable(pacioli_lifecycle_serialization_test
    tests/unit/lifecycle_serialization_test.cpp)
  target_link_libraries(pacioli_lifecycle_serialization_test PRIVATE luca::luca)
  add_test(NAME pacioli_lifecycle_serialization_test
    COMMAND pacioli_lifecycle_serialization_test)

  add_executable(pacioli_portfolio_serialization_test
    tests/unit/portfolio_serialization_test.cpp)
  target_link_libraries(pacioli_portfolio_serialization_test PRIVATE luca::portfolio)
  add_test(NAME pacioli_portfolio_serialization_test
    COMMAND pacioli_portfolio_serialization_test)

  add_executable(pacioli_checkpoint_manifest_serialization_test
    tests/unit/checkpoint_manifest_serialization_test.cpp)
  target_compile_definitions(pacioli_checkpoint_manifest_serialization_test PRIVATE
    "LUCA_CHECKPOINT_MANIFEST_FIXTURE_PATH=\"${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/serialization-checkpoints/valid-append.json\"")
  target_link_libraries(pacioli_checkpoint_manifest_serialization_test
    PRIVATE luca::portfolio)
  add_test(NAME pacioli_checkpoint_manifest_serialization_test
    COMMAND pacioli_checkpoint_manifest_serialization_test)

  add_executable(pacioli_checkpoint_decode_test
    tests/unit/checkpoint_decode_test.cpp)
  target_compile_definitions(pacioli_checkpoint_decode_test PRIVATE
    "LUCA_CHECKPOINT_DECODE_FIXTURE_PATH=\"${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/serialization-checkpoints/valid-append.json\""
    "LUCA_CHECKPOINT_DECODE_LATE_FIXTURE_PATH=\"${CMAKE_CURRENT_SOURCE_DIR}/tests/conformance/serialization-checkpoints/late-correction.json\"")
  target_link_libraries(pacioli_checkpoint_decode_test PRIVATE luca::portfolio)
  add_test(NAME pacioli_checkpoint_decode_test
    COMMAND pacioli_checkpoint_decode_test)

  add_executable(pacioli_checkpoint_resume_test
    tests/unit/checkpoint_resume_test.cpp)
  target_link_libraries(pacioli_checkpoint_resume_test PRIVATE luca::portfolio)
  add_test(NAME pacioli_checkpoint_resume_test
    COMMAND pacioli_checkpoint_resume_test)

  add_executable(pacioli_checkpoint_apply_test
    tests/unit/checkpoint_apply_test.cpp)
  target_link_libraries(pacioli_checkpoint_apply_test PRIVATE luca::portfolio)
  add_test(NAME pacioli_checkpoint_apply_test
    COMMAND pacioli_checkpoint_apply_test)

  add_executable(pacioli_provenance_test tests/unit/provenance_test.cpp)
  target_link_libraries(pacioli_provenance_test PRIVATE pacioli)
  add_test(NAME pacioli_provenance_test COMMAND pacioli_provenance_test)

  add_executable(pacioli_economic_event_test tests/unit/economic_event_test.cpp)
  target_link_libraries(pacioli_economic_event_test PRIVATE pacioli)
  add_test(NAME pacioli_economic_event_test COMMAND pacioli_economic_event_test)

  add_executable(pacioli_ledger_test tests/unit/ledger_test.cpp)
  target_link_libraries(pacioli_ledger_test PRIVATE pacioli)
  add_test(NAME pacioli_ledger_test COMMAND pacioli_ledger_test)

  add_executable(pacioli_event_lifecycle_test tests/unit/event_lifecycle_test.cpp)
  target_link_libraries(pacioli_event_lifecycle_test PRIVATE pacioli)
  add_test(NAME pacioli_event_lifecycle_test COMMAND pacioli_event_lifecycle_test)

  add_executable(pacioli_lifecycle_projection_test tests/unit/lifecycle_projection_test.cpp)
  target_link_libraries(pacioli_lifecycle_projection_test PRIVATE pacioli)
  add_test(NAME pacioli_lifecycle_projection_test COMMAND pacioli_lifecycle_projection_test)

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

  add_test(
    NAME luca_package_consumer_test
    COMMAND ${CMAKE_COMMAND}
      -DLUCA_SOURCE_BINARY_DIR=${CMAKE_CURRENT_BINARY_DIR}
      -DLUCA_CONSUMER_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/package_consumer
      -DLUCA_CONSUMER_BINARY_DIR=${CMAKE_CURRENT_BINARY_DIR}/package_consumer
      -DLUCA_INSTALL_PREFIX=${CMAKE_CURRENT_BINARY_DIR}/package_consumer_prefix
      -DLUCA_GENERATOR=${CMAKE_GENERATOR}
      -DLUCA_GENERATOR_PLATFORM=${CMAKE_GENERATOR_PLATFORM}
      -DLUCA_GENERATOR_TOOLSET=${CMAKE_GENERATOR_TOOLSET}
      -DLUCA_CXX_COMPILER=${CMAKE_CXX_COMPILER}
      -DLUCA_BUILD_CONFIG=$<CONFIG>
      -DLUCA_CTEST_COMMAND=${CMAKE_CTEST_COMMAND}
      -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/package_consumer/run_test.cmake)

  add_test(
    NAME luca_parent_consumer_test
    COMMAND ${CMAKE_COMMAND}
      -DLUCA_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}
      -DLUCA_PARENT_CONSUMER_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/parent_consumer
      -DLUCA_PARENT_CONSUMER_BINARY_DIR=${CMAKE_CURRENT_BINARY_DIR}/parent_consumer
      -DLUCA_GENERATOR=${CMAKE_GENERATOR}
      -DLUCA_GENERATOR_PLATFORM=${CMAKE_GENERATOR_PLATFORM}
      -DLUCA_GENERATOR_TOOLSET=${CMAKE_GENERATOR_TOOLSET}
      -DLUCA_CXX_COMPILER=${CMAKE_CXX_COMPILER}
      -DLUCA_BUILD_CONFIG=$<CONFIG>
      -DLUCA_CTEST_COMMAND=${CMAKE_CTEST_COMMAND}
      -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/parent_consumer/run_test.cmake)
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
