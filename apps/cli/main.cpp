#include <pacioli/version.hpp>

#include <iostream>
#include <string_view>

int main(int argc, char** argv) {
  if (argc == 2 && std::string_view{argv[1]} == "version") {
    std::cout << pacioli::name() << ' ' << pacioli::version() << '\n';
    return 0;
  }

  std::cout << "Pacioli — open-source financial data and accounting engine\n"
               "Usage: pacioli version\n";
  return 0;
}
