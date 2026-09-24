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

get_filename_component(LUCA_SOURCE_DIR "${LUCA_SOURCE_DIR}" ABSOLUTE)

function(assert_luca_source_target target_name aliased_target build_include_dir)
  if(NOT TARGET ${target_name})
    message(FATAL_ERROR "The nested LUCA project did not expose ${target_name}")
  endif()

  get_target_property(is_imported ${target_name} IMPORTED)
  if(is_imported)
    message(FATAL_ERROR "${target_name} unexpectedly resolves to an imported target")
  endif()
  get_target_property(actual_alias ${target_name} ALIASED_TARGET)
  if(NOT actual_alias STREQUAL aliased_target)
    message(FATAL_ERROR
      "${target_name} aliases ${actual_alias}; expected ${aliased_target}")
  endif()

  get_target_property(compile_features ${target_name} INTERFACE_COMPILE_FEATURES)
  if(NOT "cxx_std_23" IN_LIST compile_features)
    message(FATAL_ERROR "${target_name} does not require C++23")
  endif()

  get_target_property(include_dirs ${target_name} INTERFACE_INCLUDE_DIRECTORIES)
  set(expected_build_include "$<BUILD_INTERFACE:${build_include_dir}>")
  if(NOT expected_build_include IN_LIST include_dirs OR
      NOT "$<INSTALL_INTERFACE:include>" IN_LIST include_dirs)
    message(FATAL_ERROR
      "${target_name} exposes unexpected include directories: ${include_dirs}")
  endif()
  list(LENGTH include_dirs include_dir_count)
  if(NOT include_dir_count EQUAL 2)
    message(FATAL_ERROR
      "${target_name} exposes extra include directories: ${include_dirs}")
  endif()
endfunction()

assert_luca_source_target(
  luca::ledger luca_ledger "${LUCA_SOURCE_DIR}/libs/ledger/include")
assert_luca_source_target(
  luca::portfolio luca_portfolio "${LUCA_SOURCE_DIR}/libs/portfolio/include")
assert_luca_source_target(
  luca::reconciliation luca_reconciliation
  "${LUCA_SOURCE_DIR}/libs/reconciliation/include")
assert_luca_source_target(luca::luca pacioli "${LUCA_SOURCE_DIR}/include")

get_target_property(portfolio_links luca::portfolio INTERFACE_LINK_LIBRARIES)
if(NOT portfolio_links STREQUAL "luca::ledger")
  message(FATAL_ERROR
    "luca::portfolio has unexpected dependencies: ${portfolio_links}")
endif()
get_target_property(
  reconciliation_links luca::reconciliation INTERFACE_LINK_LIBRARIES)
if(NOT reconciliation_links STREQUAL "luca::portfolio;luca::ledger")
  message(FATAL_ERROR
    "luca::reconciliation has unexpected dependencies: ${reconciliation_links}")
endif()
get_target_property(umbrella_links luca::luca INTERFACE_LINK_LIBRARIES)
if(NOT umbrella_links STREQUAL
    "luca::ledger;luca::portfolio;luca::reconciliation")
  message(FATAL_ERROR "luca::luca has unexpected dependencies: ${umbrella_links}")
endif()

add_executable(luca_parent_consumer main.cpp)
target_link_libraries(luca_parent_consumer PRIVATE luca::luca)

add_executable(luca_parent_ledger_consumer ledger.cpp)
target_link_libraries(luca_parent_ledger_consumer PRIVATE luca::ledger)

add_executable(luca_parent_portfolio_consumer main.cpp)
target_link_libraries(luca_parent_portfolio_consumer PRIVATE luca::portfolio)

add_executable(luca_parent_reconciliation_consumer reconciliation.cpp)
target_link_libraries(
  luca_parent_reconciliation_consumer PRIVATE luca::reconciliation)

add_executable(luca_parent_exact_cash_consumer exact_cash_reduction.cpp)
target_link_libraries(luca_parent_exact_cash_consumer PRIVATE luca::portfolio)

add_executable(luca_parent_exact_cash_comparison_consumer
  exact_cash_comparison.cpp)
target_link_libraries(luca_parent_exact_cash_comparison_consumer
  PRIVATE luca::reconciliation)

add_test(NAME luca_parent_consumer_run COMMAND luca_parent_consumer)
set_tests_properties(luca_parent_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
add_test(
  NAME luca_parent_ledger_consumer_run
  COMMAND luca_parent_ledger_consumer)
set_tests_properties(luca_parent_ledger_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "ledger_entries=1")
add_test(
  NAME luca_parent_portfolio_consumer_run
  COMMAND luca_parent_portfolio_consumer)
set_tests_properties(luca_parent_portfolio_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
add_test(
  NAME luca_parent_reconciliation_consumer_run
  COMMAND luca_parent_reconciliation_consumer)
set_tests_properties(luca_parent_reconciliation_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "position_breaks=0")
add_test(
  NAME luca_parent_exact_cash_consumer_run
  COMMAND luca_parent_exact_cash_consumer)
set_tests_properties(luca_parent_exact_cash_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION
    "exact_cash_scaled=800000000 currency=USD policy=parent-consumer.cash-policy")
add_test(
  NAME luca_parent_exact_cash_comparison_consumer_run
  COMMAND luca_parent_exact_cash_comparison_consumer)
set_tests_properties(luca_parent_exact_cash_comparison_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION
    "exact_cash_break=amount_mismatch difference_scaled=-10000000 currency=USD operation=compare.cash.exact")
