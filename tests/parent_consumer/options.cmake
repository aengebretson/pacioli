# Authored acceptance matrix. This script configures projects; it is registered
# with CTest but must not be invoked while automated testing is paused.
foreach(required IN ITEMS LUCA_SOURCE_DIR LUCA_OPTIONS_BINARY_DIR LUCA_GENERATOR
    LUCA_CXX_COMPILER)
  if(NOT DEFINED ${required} OR "${${required}}" STREQUAL "")
    message(FATAL_ERROR "${required} is required")
  endif()
endforeach()
set(generator_args -G "${LUCA_GENERATOR}" "-DCMAKE_CXX_COMPILER=${LUCA_CXX_COMPILER}")
if(LUCA_GENERATOR_PLATFORM)
  list(APPEND generator_args -A "${LUCA_GENERATOR_PLATFORM}")
endif()
if(LUCA_GENERATOR_TOOLSET)
  list(APPEND generator_args -T "${LUCA_GENERATOR_TOOLSET}")
endif()
file(REMOVE_RECURSE "${LUCA_OPTIONS_BINARY_DIR}")

function(configure_case name expected_conflict)
  execute_process(COMMAND "${CMAKE_COMMAND}"
    -S "${LUCA_SOURCE_DIR}/tests/parent_consumer"
    -B "${LUCA_OPTIONS_BINARY_DIR}/${name}" ${generator_args}
    "-DLUCA_SOURCE_DIR=${LUCA_SOURCE_DIR}" ${ARGN}
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
  if(expected_conflict)
    if(result EQUAL 0 OR NOT "${output}\n${error}" MATCHES "Conflicting LUCA options")
      message(FATAL_ERROR "${name}: expected actionable option conflict\n${output}\n${error}")
    endif()
  elseif(NOT result EQUAL 0)
    message(FATAL_ERROR "${name}: configure failed\n${output}\n${error}")
  endif()
endfunction()

configure_case(default OFF)
foreach(prefix IN ITEMS LUCA PACIOLI)
  foreach(suffix IN ITEMS TESTS TOOLS BENCHMARKS)
    configure_case(${prefix}_${suffix}_off OFF -D${prefix}_BUILD_${suffix}=OFF)
    configure_case(${prefix}_${suffix}_on OFF -D${prefix}_BUILD_${suffix}=ON
      -DLUCA_PARENT_EXPECT_${suffix}=ON -DLUCA_PARENT_CONSUMER_ALLOW_PYTHON=ON)
  endforeach()
  configure_case(normal_${prefix} OFF -DLUCA_PARENT_NORMAL_PREFIX=${prefix}
    -DLUCA_PARENT_NORMAL_VALUE=ON -DLUCA_PARENT_EXPECT_TESTS=ON
    -DLUCA_PARENT_EXPECT_TOOLS=ON -DLUCA_PARENT_EXPECT_BENCHMARKS=ON
    -DLUCA_PARENT_CONSUMER_ALLOW_PYTHON=ON)
endforeach()
foreach(suffix IN ITEMS TESTS TOOLS BENCHMARKS)
  configure_case(agree_${suffix} OFF -DLUCA_BUILD_${suffix}=TRUE
    -DPACIOLI_BUILD_${suffix}=ON -DLUCA_PARENT_EXPECT_${suffix}=ON
    -DLUCA_PARENT_CONSUMER_ALLOW_PYTHON=ON)
  configure_case(agree_off_${suffix} OFF -DLUCA_BUILD_${suffix}=FALSE
    -DPACIOLI_BUILD_${suffix}=OFF)
  configure_case(conflict_${suffix} ON -DLUCA_BUILD_${suffix}=ON
    -DPACIOLI_BUILD_${suffix}=OFF)
  configure_case(reverse_conflict_${suffix} ON -DLUCA_BUILD_${suffix}=OFF
    -DPACIOLI_BUILD_${suffix}=ON)
  # Reuse the legacy-only cache: no generated canonical cache entry may freeze it.
  configure_case(PACIOLI_${suffix}_off OFF -DPACIOLI_BUILD_${suffix}=ON
    -DLUCA_PARENT_EXPECT_${suffix}=ON -DLUCA_PARENT_CONSUMER_ALLOW_PYTHON=ON)
  configure_case(PACIOLI_${suffix}_off OFF -DPACIOLI_BUILD_${suffix}=OFF
    -DLUCA_PARENT_EXPECT_${suffix}=OFF)
endforeach()
configure_case(normal_conflict ON -DLUCA_PARENT_NORMAL_PREFIX=PACIOLI
  -DLUCA_PARENT_NORMAL_VALUE=ON -DLUCA_BUILD_TESTS=OFF)

# Top-level defaults remain tests/tools ON, benchmarks OFF.
execute_process(COMMAND "${CMAKE_COMMAND}" -S "${LUCA_SOURCE_DIR}"
  -B "${LUCA_OPTIONS_BINARY_DIR}/standalone" ${generator_args}
  RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
if(NOT result EQUAL 0)
  message(FATAL_ERROR "Standalone configure failed\n${output}\n${error}")
endif()
file(READ "${LUCA_OPTIONS_BINARY_DIR}/standalone/CMakeCache.txt" cache)
foreach(entry IN ITEMS LUCA_BUILD_TESTS:BOOL=ON LUCA_BUILD_TOOLS:BOOL=ON
    LUCA_BUILD_BENCHMARKS:BOOL=OFF CMAKE_PROJECT_NAME:STATIC=luca)
  string(FIND "${cache}" "${entry}" found)
  if(found EQUAL -1)
    message(FATAL_ERROR "Standalone defaults missing ${entry}")
  endif()
endforeach()
