foreach(required_variable IN ITEMS
    LUCA_SOURCE_BINARY_DIR
    LUCA_CONSUMER_SOURCE_DIR
    LUCA_CONSUMER_BINARY_DIR
    LUCA_INSTALL_PREFIX
    LUCA_GENERATOR
    LUCA_CXX_COMPILER
    LUCA_CTEST_COMMAND)
  if(NOT DEFINED ${required_variable} OR "${${required_variable}}" STREQUAL "")
    message(FATAL_ERROR "${required_variable} is required")
  endif()
endforeach()

file(REMOVE_RECURSE "${LUCA_CONSUMER_BINARY_DIR}" "${LUCA_INSTALL_PREFIX}")

execute_process(
  COMMAND "${CMAKE_COMMAND}" --install "${LUCA_SOURCE_BINARY_DIR}"
    --prefix "${LUCA_INSTALL_PREFIX}" --config "${LUCA_BUILD_CONFIG}"
  RESULT_VARIABLE install_result
  OUTPUT_VARIABLE install_output
  ERROR_VARIABLE install_error)
if(NOT install_result EQUAL 0)
  message(FATAL_ERROR
    "LUCA install failed (${install_result})\n${install_output}\n${install_error}")
endif()

get_filename_component(
  luca_source_dir "${LUCA_CONSUMER_SOURCE_DIR}/../.." ABSOLUTE)
file(GLOB_RECURSE package_metadata
  LIST_DIRECTORIES FALSE
  "${LUCA_INSTALL_PREFIX}/*.cmake")
if(NOT package_metadata)
  message(FATAL_ERROR "LUCA install produced no CMake package metadata")
endif()
foreach(metadata_file IN LISTS package_metadata)
  file(READ "${metadata_file}" metadata_contents)
  foreach(forbidden_path IN ITEMS "${luca_source_dir}" "${LUCA_SOURCE_BINARY_DIR}")
    string(FIND "${metadata_contents}" "${forbidden_path}" path_position)
    if(NOT path_position EQUAL -1)
      message(FATAL_ERROR
        "Installed metadata ${metadata_file} contains checkout path "
        "${forbidden_path}")
    endif()
  endforeach()
endforeach()

set(configure_command
  "${CMAKE_COMMAND}"
  -S "${LUCA_CONSUMER_SOURCE_DIR}"
  -B "${LUCA_CONSUMER_BINARY_DIR}"
  -G "${LUCA_GENERATOR}"
  "-DCMAKE_PREFIX_PATH=${LUCA_INSTALL_PREFIX}"
  "-DLUCA_EXPECTED_INSTALL_PREFIX=${LUCA_INSTALL_PREFIX}"
  "-DCMAKE_CXX_COMPILER=${LUCA_CXX_COMPILER}")
if(DEFINED LUCA_GENERATOR_PLATFORM AND NOT "${LUCA_GENERATOR_PLATFORM}" STREQUAL "")
  list(APPEND configure_command -A "${LUCA_GENERATOR_PLATFORM}")
endif()
if(DEFINED LUCA_GENERATOR_TOOLSET AND NOT "${LUCA_GENERATOR_TOOLSET}" STREQUAL "")
  list(APPEND configure_command -T "${LUCA_GENERATOR_TOOLSET}")
endif()
if(DEFINED LUCA_BUILD_CONFIG AND NOT "${LUCA_BUILD_CONFIG}" STREQUAL "")
  list(APPEND configure_command "-DCMAKE_BUILD_TYPE=${LUCA_BUILD_CONFIG}")
endif()

execute_process(
  COMMAND ${configure_command}
  RESULT_VARIABLE configure_result
  OUTPUT_VARIABLE configure_output
  ERROR_VARIABLE configure_error)
if(NOT configure_result EQUAL 0)
  message(FATAL_ERROR
    "Consumer configure failed (${configure_result})\n${configure_output}\n${configure_error}")
endif()

execute_process(
  COMMAND "${CMAKE_COMMAND}" --build "${LUCA_CONSUMER_BINARY_DIR}"
    --config "${LUCA_BUILD_CONFIG}"
  RESULT_VARIABLE build_result
  OUTPUT_VARIABLE build_output
  ERROR_VARIABLE build_error)
if(NOT build_result EQUAL 0)
  message(FATAL_ERROR
    "Consumer build failed (${build_result})\n${build_output}\n${build_error}")
endif()

execute_process(
  COMMAND "${LUCA_CTEST_COMMAND}" --test-dir "${LUCA_CONSUMER_BINARY_DIR}"
    --build-config "${LUCA_BUILD_CONFIG}" --output-on-failure
  RESULT_VARIABLE test_result
  OUTPUT_VARIABLE test_output
  ERROR_VARIABLE test_error)
if(NOT test_result EQUAL 0)
  message(FATAL_ERROR
    "Consumer execution failed (${test_result})\n${test_output}\n${test_error}")
endif()

message(STATUS "Installed-package consumer passed\n${test_output}")
