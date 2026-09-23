#include <luca/portfolio.hpp>

#include <chrono>

int main() {
  const luca::Ledger ledger;
  const auto positions = luca::project_positions(
      ledger.entries(), luca::Timestamp{std::chrono::nanoseconds{0}});
  return positions && positions->empty() ? 0 : 1;
}
