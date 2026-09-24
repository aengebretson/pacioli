#include <luca/ledger.hpp>
#include <luca/lifecycle.hpp>
#include <luca/serialization/canonical.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  using namespace std::chrono_literals;

  const auto usd = luca::Currency::from_code("USD");
  if (!usd)
    return 1;
  const auto amount = luca::Money::parse("125.00", *usd);
  const auto provenance =
      luca::Provenance::create(std::vector{luca::SourceRecordId{"parent-ledger-consumer-source-1"}},
                               "parent-ledger-consumer", "1");
  if (!amount || !provenance)
    return 1;

  constexpr luca::Timestamp effective_at{1s};
  const auto header = luca::EventHeader::create(luca::EventId{"parent-ledger-deposit-1"},
                                                luca::AccountId{"parent-ledger-account-1"},
                                                effective_at, *provenance);
  if (!header)
    return 2;

  luca::Ledger ledger;
  const auto event = luca::CashMovement::create(*header, *amount);
  if (!ledger.append(event))
    return 3;
  if (ledger.entries().size() != 1)
    return 4;

  luca::LifecycleLedger lifecycle;
  if (!lifecycle.accept(luca::LifecycleRecordDraft::originate(
          luca::EconomicEventId{"parent-ledger-economic-deposit-1"}, effective_at, event)))
    return 5;
  if (luca::serialization::canonical_digest(lifecycle).size() != 64)
    return 6;

  std::cout << "ledger_entries=" << ledger.entries().size() << '\n';
  return 0;
}
