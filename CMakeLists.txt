cmake_minimum_required(VERSION 3.28)

project(Pacioli VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

add_subdirectory(libs/core)
add_subdirectory(apps/cli)

if(BUILD_TESTING)
  add_subdirectory(tests)
endif()
