cmake_minimum_required(VERSION 3.24)
project(luca_package_consumer LANGUAGES CXX)

find_package(Luca 0.1 CONFIG REQUIRED)

set(LUCA_EXPECTED_INSTALL_PREFIX "" CACHE PATH
  "Expected isolated LUCA installation prefix")
if(NOT LUCA_EXPECTED_INSTALL_PREFIX)
  message(FATAL_ERROR "LUCA_EXPECTED_INSTALL_PREFIX is required")
endif()
get_filename_component(
  LUCA_EXPECTED_INSTALL_PREFIX "${LUCA_EXPECTED_INSTALL_PREFIX}" ABSOLUTE)
set(expected_include_dir "${LUCA_EXPECTED_INSTALL_PREFIX}/include")

foreach(luca_target IN ITEMS
    luca::ledger
    luca::portfolio
    luca::reconciliation
    luca::luca)
  if(NOT TARGET ${luca_target})
    message(FATAL_ERROR "Installed package did not expose ${luca_target}")
  endif()

  get_target_property(is_imported ${luca_target} IMPORTED)
  if(NOT is_imported)
    message(FATAL_ERROR "${luca_target} is not an installed imported target")
  endif()

  get_target_property(compile_features ${luca_target} INTERFACE_COMPILE_FEATURES)
  if(NOT "cxx_std_23" IN_LIST compile_features)
    message(FATAL_ERROR "${luca_target} does not require C++23")
  endif()

  get_target_property(include_dirs ${luca_target} INTERFACE_INCLUDE_DIRECTORIES)
  if(NOT include_dirs STREQUAL expected_include_dir)
    message(FATAL_ERROR
      "${luca_target} exposes unexpected installed include directories: "
      "${include_dirs}; expected ${expected_include_dir}")
  endif()
endforeach()

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

add_executable(luca_package_consumer main.cpp)
target_link_libraries(luca_package_consumer PRIVATE luca::luca)

add_executable(luca_package_ledger_consumer ledger.cpp)
target_link_libraries(luca_package_ledger_consumer PRIVATE luca::ledger)

add_executable(luca_package_portfolio_consumer main.cpp)
target_link_libraries(luca_package_portfolio_consumer PRIVATE luca::portfolio)

add_executable(luca_package_reconciliation_consumer reconciliation.cpp)
target_link_libraries(
  luca_package_reconciliation_consumer PRIVATE luca::reconciliation)

enable_testing()
add_test(NAME luca_package_consumer_run COMMAND luca_package_consumer)
set_tests_properties(luca_package_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
add_test(
  NAME luca_package_ledger_consumer_run
  COMMAND luca_package_ledger_consumer)
set_tests_properties(luca_package_ledger_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "ledger_entries=1")
add_test(
  NAME luca_package_portfolio_consumer_run
  COMMAND luca_package_portfolio_consumer)
set_tests_properties(luca_package_portfolio_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
add_test(
  NAME luca_package_reconciliation_consumer_run
  COMMAND luca_package_reconciliation_consumer)
set_tests_properties(luca_package_reconciliation_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "position_breaks=0")
