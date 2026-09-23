cmake_minimum_required(VERSION 3.24)
project(luca_package_consumer LANGUAGES CXX)

find_package(Luca 0.1 CONFIG REQUIRED)

add_executable(luca_package_consumer main.cpp)
target_link_libraries(luca_package_consumer PRIVATE luca::luca)

enable_testing()
add_test(NAME luca_package_consumer_run COMMAND luca_package_consumer)
set_tests_properties(luca_package_consumer_run PROPERTIES
  PASS_REGULAR_EXPRESSION "cash_scaled=125000000 currency=USD")
