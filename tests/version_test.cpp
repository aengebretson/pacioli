#include <pacioli/version.hpp>

#include <cstdlib>

int main() {
  return pacioli::name() == "Pacioli" && pacioli::version() == "0.1.0"
             ? EXIT_SUCCESS
             : EXIT_FAILURE;
}
