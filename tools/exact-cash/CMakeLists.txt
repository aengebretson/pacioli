add_executable(luca-exact-cash main.cpp)
target_link_libraries(luca-exact-cash PRIVATE luca::reconciliation)

install(TARGETS luca-exact-cash RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
