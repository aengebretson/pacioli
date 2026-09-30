cmake_minimum_required(VERSION 3.24)
project(luca_trade_reconciliation_example LANGUAGES CXX)

# Intentionally independent of the repository root and its custom conformance
# generation. There are no test registrations or commands that run executables.
get_filename_component(LUCA_SOURCE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
add_library(trade_example_headers INTERFACE)
target_compile_features(trade_example_headers INTERFACE cxx_std_23)
target_include_directories(trade_example_headers INTERFACE
  "${LUCA_SOURCE_ROOT}/libs/ledger/include"
  "${LUCA_SOURCE_ROOT}/libs/reconciliation/include"
  "${LUCA_SOURCE_ROOT}/libs/adapters/include")

add_executable(trade_reconciliation_example main.cpp)
target_link_libraries(trade_reconciliation_example PRIVATE trade_example_headers)

# These targets compile authored checks only. Building never executes them.
add_executable(trade_reconciliation_test EXCLUDE_FROM_ALL
  "${LUCA_SOURCE_ROOT}/tests/unit/trade_reconciliation_test.cpp")
target_link_libraries(trade_reconciliation_test PRIVATE trade_example_headers)
add_executable(trade_csv_test EXCLUDE_FROM_ALL
  "${LUCA_SOURCE_ROOT}/tests/unit/trade_csv_test.cpp")
target_link_libraries(trade_csv_test PRIVATE trade_example_headers)
target_compile_definitions(trade_csv_test PRIVATE
  LUCA_TRADE_FIXTURE_DIR="${LUCA_SOURCE_ROOT}/tests/conformance/trade-reconciliation")
