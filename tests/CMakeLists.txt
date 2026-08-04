add_executable(pacioli_core_tests version_test.cpp)
target_compile_features(pacioli_core_tests PRIVATE cxx_std_23)
target_link_libraries(pacioli_core_tests PRIVATE Pacioli::core)
add_test(NAME pacioli.core.version COMMAND pacioli_core_tests)
