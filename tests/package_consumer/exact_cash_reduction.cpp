#include <luca/portfolio.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  const auto usd = luca::Currency::from_code("USD");
  const auto settlement_date =
      luca::SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 5);
  const auto policy = luca::ExactCashReductionPolicy::create("package-consumer.cash-policy", "1");
  const auto context = luca::ExactCashEvaluationContext::create(
      "package-consumer-context", "package-consumer-engine-1",
      luca::Timestamp{std::chrono::seconds{3}}, luca::Timestamp{std::chrono::seconds{2}},
      *settlement_date);
  if (!usd || !settlement_date || !policy || !context)
    return 1;

  const auto contract = luca::ExactCashReductionContract::create(
      luca::CashKey{luca::AccountId{"package-account"}, *usd}, "1", *policy, *context);
  if (!contract)
    return 2;

  const auto deposit = luca::ExactCashPartial::create(
      *contract, *luca::Money::parse("1000.000000", *usd), {luca::EventId{"package-deposit"}},
      {luca::SourceRecordId{"package-source-1"}});
  const auto withdrawal = luca::ExactCashPartial::create(
      *contract, *luca::Money::parse("-200.000000", *usd), {luca::EventId{"package-withdrawal"}},
      {luca::SourceRecordId{"package-source-2"}});
  if (!deposit || !withdrawal)
    return 3;

  const std::vector partials{*withdrawal, *deposit};
  const auto result = luca::reduce_exact_cash(*contract, partials);
  if (!result || result->amount() != *luca::Money::parse("800.000000", *usd) ||
      result->source_event_ids().size() != 2 || result->source_record_ids().size() != 2) {
    return 4;
  }

  std::cout << "exact_cash_scaled=" << result->amount().scaled_value()
            << " currency=" << result->amount().currency().code()
            << " policy=" << result->policy().id() << '\n';
  return 0;
}
