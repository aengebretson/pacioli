cmake_minimum_required(VERSION 3.24)

if(NOT DEFINED luca_source_dir)
  message(FATAL_ERROR "luca_source_dir must be set")
endif()
if(NOT DEFINED consumer_binary_dir)
  message(FATAL_ERROR "consumer_binary_dir must be set")
endif()

set(consumer_fixture_dir "${CMAKE_CURRENT_LIST_DIR}")
set(configure_command
  "${CMAKE_COMMAND}"
  "-S" "${consumer_fixture_dir}"
  "-B" "${consumer_binary_dir}"
  "-DLUCA_SOURCE_DIR=${luca_source_dir}"
  "-DCMAKE_DISABLE_FIND_PACKAGE_Python3=TRUE"
)
if(DEFINED consumer_generator AND NOT consumer_generator STREQUAL "")
  list(APPEND configure_command "-G" "${consumer_generator}")
endif()
if(DEFINED consumer_make_program AND NOT consumer_make_program STREQUAL "")
  list(APPEND configure_command "-DCMAKE_MAKE_PROGRAM=${consumer_make_program}")
endif()
if(DEFINED consumer_build_type AND NOT consumer_build_type STREQUAL "")
  list(APPEND configure_command "-DCMAKE_BUILD_TYPE=${consumer_build_type}")
endif()

execute_process(
  COMMAND ${configure_command}
  RESULT_VARIABLE configure_result
  OUTPUT_VARIABLE configure_stdout
  ERROR_VARIABLE configure_stderr
)
if(NOT configure_result EQUAL 0)
  message(FATAL_ERROR
    "add_subdirectory consumer configure failed\nstdout:\n${configure_stdout}\nstderr:\n${configure_stderr}")
endif()

set(build_command "${CMAKE_COMMAND}" "--build" "${consumer_binary_dir}")
if(DEFINED consumer_config AND NOT consumer_config STREQUAL "")
  list(APPEND build_command "--config" "${consumer_config}")
endif()

execute_process(
  COMMAND ${build_command}
  RESULT_VARIABLE build_result
  OUTPUT_VARIABLE build_stdout
  ERROR_VARIABLE build_stderr
)
if(NOT build_result EQUAL 0)
  message(FATAL_ERROR
    "add_subdirectory consumer build failed\nstdout:\n${build_stdout}\nstderr:\n${build_stderr}")
endif()

set(executable_name "add_subdirectory_consumer")
if(CMAKE_HOST_WIN32)
  set(executable_name "${executable_name}.exe")
endif()

set(candidate_paths)
if(DEFINED consumer_config AND NOT consumer_config STREQUAL "")
  list(APPEND candidate_paths "${consumer_binary_dir}/${consumer_config}/${executable_name}")
endif()
list(APPEND candidate_paths "${consumer_binary_dir}/${executable_name}")

set(consumer_executable "")
foreach(candidate_path IN LISTS candidate_paths)
  if(EXISTS "${candidate_path}")
    set(consumer_executable "${candidate_path}")
    break()
  endif()
endforeach()

if(consumer_executable STREQUAL "")
  message(FATAL_ERROR "could not locate add_subdirectory consumer executable in ${consumer_binary_dir}")
endif()

execute_process(
  COMMAND "${consumer_executable}"
  WORKING_DIRECTORY "${consumer_binary_dir}"
  RESULT_VARIABLE run_result
  OUTPUT_VARIABLE run_stdout
  ERROR_VARIABLE run_stderr
)
if(NOT run_result EQUAL 0)
  message(FATAL_ERROR
    "add_subdirectory consumer execution failed\nstdout:\n${run_stdout}\nstderr:\n${run_stderr}")
endif()
