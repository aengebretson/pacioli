#include <luca/portfolio.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  using namespace std::chrono_literals;

  const auto usd = luca::Currency::from_code("USD");
  if (!usd) return 1;
  const auto amount = luca::Money::parse("125.00", *usd);
  if (!amount) return 1;
  const auto provenance = luca::Provenance::create(
      std::vector{luca::SourceRecordId{"parent-consumer-source-1"}},
      "parent-consumer", "1");
  if (!provenance) return 1;
  constexpr luca::Timestamp effective_at{1s};
  const auto header = luca::EventHeader::create(
      luca::EventId{"parent-deposit-1"}, luca::AccountId{"parent-account-1"},
      effective_at, *provenance);
  if (!header) return 1;

  luca::Ledger ledger;
  const auto appended = ledger.append(
      luca::CashMovement::create(*header, *amount));
  if (!appended) return 2;

  const auto balances = luca::project_cash(
      ledger.entries(),
      luca::CashProjectionContext{
          effective_at, std::chrono::year{2026} / std::chrono::January / 1});
  if (!balances || balances->size() != 1) return 3;

  const auto& balance = balances->front();
  if (balance.amount().scaled_value() != 125'000'000 ||
      balance.amount().currency() != *usd) {
    return 4;
  }

  std::cout << "cash_scaled=" << balance.amount().scaled_value()
            << " currency=" << balance.amount().currency().code() << '\n';
  return 0;
}
