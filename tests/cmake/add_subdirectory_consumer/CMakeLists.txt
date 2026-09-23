cmake_minimum_required(VERSION 3.24)
project(luca_add_subdirectory_consumer LANGUAGES CXX)

if(NOT DEFINED LUCA_SOURCE_DIR)
  message(FATAL_ERROR "LUCA_SOURCE_DIR must be set for the add_subdirectory consumer fixture")
endif()

add_subdirectory("${LUCA_SOURCE_DIR}" luca)

foreach(option_name IN ITEMS LUCA_BUILD_TESTS LUCA_BUILD_EXAMPLES LUCA_BUILD_BENCHMARKS)
  if(${option_name})
    message(FATAL_ERROR "${option_name} must default OFF for add_subdirectory consumers")
  endif()
endforeach()

foreach(target_name IN ITEMS
  luca_smoke_test
  luca_core_values_test
  luca_provenance_test
  luca_economic_event_test
  luca_ledger_test
  luca_position_projection_test
  luca_position_reconciliation_test
  luca_cash_reconciliation_test
  luca_cash_projection_test
  luca_settlement_projection_test
  luca_conformance_engine_test
  luca_benchmarks
)
  if(TARGET ${target_name})
    message(FATAL_ERROR "${target_name} must not be created by default for add_subdirectory consumers")
  endif()
endforeach()

add_executable(add_subdirectory_consumer main.cpp)
set_target_properties(add_subdirectory_consumer PROPERTIES CXX_EXTENSIONS OFF)
target_link_libraries(add_subdirectory_consumer PRIVATE luca::portfolio)
