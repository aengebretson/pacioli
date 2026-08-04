add_executable(pacioli_cli main.cpp)
set_target_properties(pacioli_cli PROPERTIES OUTPUT_NAME pacioli)
target_compile_features(pacioli_cli PRIVATE cxx_std_23)
target_link_libraries(pacioli_cli PRIVATE Pacioli::core)
