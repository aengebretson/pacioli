#include <pacioli/ledger.hpp>

#include <type_traits>

static_assert(std::is_same_v<pacioli::Ledger, luca::Ledger>);

int main() {
  const pacioli::Ledger ledger;
  return ledger.entries().empty() ? 0 : 1;
}
