cmake_minimum_required(VERSION 3.24)
project(LucaFinancialAlgebraReport LANGUAGES CXX)

# Standalone only: no parent build, custom commands, test registration or execution.
set(LUCA_SOURCE_DIR "" CACHE PATH "Optional LUCA checkout; otherwise use installed Luca")
if(LUCA_SOURCE_DIR)
  add_library(financial_algebra_report_headers INTERFACE)
  target_include_directories(financial_algebra_report_headers INTERFACE
    "${LUCA_SOURCE_DIR}/libs/ledger/include"
    "${LUCA_SOURCE_DIR}/libs/portfolio/include"
    "${LUCA_SOURCE_DIR}/libs/reconciliation/include")
  set(report_library financial_algebra_report_headers)
else()
  find_package(Luca CONFIG REQUIRED)
  set(report_library luca::reconciliation)
endif()

add_executable(luca-financial-algebra-report main.cpp)
target_compile_features(luca-financial-algebra-report PRIVATE cxx_std_23)
set_target_properties(luca-financial-algebra-report PROPERTIES CXX_EXTENSIONS OFF)
target_link_libraries(luca-financial-algebra-report PRIVATE ${report_library})
