#include <luca/reconciliation.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  using namespace std::chrono_literals;

  const auto quantity = luca::Quantity::parse("10");
  const auto provenance = luca::Provenance::create(
      std::vector{luca::SourceRecordId{"reconciliation-consumer-source-1"}},
      "reconciliation-consumer", "1");
  if (!quantity || !provenance)
    return 1;

  constexpr luca::Timestamp as_of{1s};
  const luca::AccountId account{"reconciliation-account-1"};
  const luca::InstrumentId instrument{"reconciliation-instrument-1"};
  const std::vector expected{luca::Position{luca::PositionKey{account, instrument}, *quantity}};
  const auto observation =
      luca::PositionObservation::create(account, instrument, *quantity, as_of, *provenance);
  if (!observation)
    return 2;

  const std::vector observed{*observation};
  const auto breaks =
      luca::reconcile_positions(expected, observed, luca::PositionReconciliationContext{as_of});
  if (!breaks || !breaks->empty())
    return 3;

  std::cout << "position_breaks=" << breaks->size() << '\n';
  return 0;
}
