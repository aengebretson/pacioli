#include <luca/reconciliation.hpp>

#include <chrono>
#include <iostream>
#include <optional>
#include <vector>

int main() {
  const auto usd = luca::Currency::from_code("USD");
  const auto settlement =
      luca::SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 5);
  const auto reduction_policy = luca::ExactCashReductionPolicy::create("exact-cash-sum", "1");
  const auto comparison_policy =
      luca::ExactCashComparisonPolicy::create("exact-cash-comparison", "1");
  if (!usd || !settlement || !reduction_policy || !comparison_policy)
    return 1;

  const auto economic_as_of =
      luca::Timestamp{std::chrono::sys_days{std::chrono::year{2026} / std::chrono::June / 5} +
                      std::chrono::hours{23} + std::chrono::minutes{59} + std::chrono::seconds{59}};
  const auto context = luca::ExactCashEvaluationContext::create(
      "cash-context-1", "contract-fixture-1",
      luca::Timestamp{std::chrono::sys_days{std::chrono::year{2026} / std::chrono::June / 10}},
      economic_as_of, *settlement);
  if (!context)
    return 2;
  const auto reduction = luca::ExactCashReductionContract::create(
      luca::CashKey{luca::AccountId{"fund-a"}, *usd}, "1", *reduction_policy, *context);
  const auto comparison =
      luca::ExactCashComparisonContract::create("1", *comparison_policy, *context);
  if (!reduction || !comparison)
    return 3;

  const auto deposit = luca::ExactCashPartial::create(
      *reduction, *luca::Money::parse("1000.000000", *usd), {luca::EventId{"cash-event-1"}},
      {luca::SourceRecordId{"source.cash.1"}});
  const auto withdrawal = luca::ExactCashPartial::create(
      *reduction, *luca::Money::parse("-250.000000", *usd), {luca::EventId{"cash-event-2"}},
      {luca::SourceRecordId{"source.cash.2"}});
  const auto adjustment = luca::ExactCashPartial::create(
      *reduction, *luca::Money::parse("50.000000", *usd), {luca::EventId{"cash-event-3"}},
      {luca::SourceRecordId{"source.cash.3"}});
  if (!deposit || !withdrawal || !adjustment)
    return 4;
  const std::vector partials{*withdrawal, *adjustment, *deposit};
  const auto projected = luca::reduce_exact_cash(*reduction, partials);

  const auto provenance = luca::Provenance::create({luca::SourceRecordId{"observation.bank.1"}},
                                                   "bank-cash-observation", "1");
  if (!projected || !provenance)
    return 5;
  const auto observation = luca::CashObservation::create(
      luca::AccountId{"fund-a"}, *luca::Money::parse("790.000000", *usd), economic_as_of,
      settlement->value(), *provenance);
  if (!observation)
    return 6;

  const std::vector projections{*projected};
  const std::vector observations{*observation};
  const auto result = luca::compare_exact_cash(*comparison, projections, observations);
  if (!result || result->operation_id() != "compare.cash.exact" || result->breaks().size() != 1)
    return 7;
  const auto &cash_break = result->breaks().front();
  if (cash_break.kind() != luca::ExactCashBreakKind::amount_mismatch ||
      cash_break.difference() != std::optional{*luca::Money::parse("-10.000000", *usd)} ||
      cash_break.projection_source_event_ids().size() != 3 ||
      !cash_break.observation_provenance() ||
      cash_break.observation_provenance()->source_records().size() != 1) {
    return 8;
  }

  std::cout << "exact_cash_break=" << luca::category_name(cash_break.kind())
            << " difference_scaled=" << cash_break.difference()->scaled_value()
            << " currency=" << cash_break.difference()->currency().code()
            << " operation=" << result->operation_id() << '\n';
  return 0;
}
