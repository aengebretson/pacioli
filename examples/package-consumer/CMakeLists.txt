cmake_minimum_required(VERSION 3.24)
project(luca_package_walkthrough LANGUAGES CXX)

# An external project: no source-tree includes or financial implementation here.
find_package(Luca 0.1 CONFIG REQUIRED)
add_executable(luca_package_walkthrough main.cpp)
target_link_libraries(luca_package_walkthrough PRIVATE luca::reconciliation)
set_target_properties(luca_package_walkthrough PROPERTIES CXX_EXTENSIONS OFF)
