cmake_minimum_required(VERSION 3.24)
project(luca_settlement_date_accounting_example LANGUAGES CXX)

# Isolated compilation: no parent build, custom commands, tests, or downloads.
get_filename_component(LUCA_SOURCE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
add_executable(luca_settlement_date_accounting main.cpp)
target_compile_features(luca_settlement_date_accounting PRIVATE cxx_std_23)
set_target_properties(luca_settlement_date_accounting PROPERTIES CXX_EXTENSIONS OFF)
target_include_directories(luca_settlement_date_accounting PRIVATE
  "${LUCA_SOURCE_ROOT}/libs/ledger/include"
  "${LUCA_SOURCE_ROOT}/libs/portfolio/include")
