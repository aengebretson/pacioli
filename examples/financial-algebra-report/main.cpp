#include "cash_report.hpp"

#include <chrono>
#include <iostream>

namespace {
void print_date(std::chrono::year_month_day date) {
  std::cout << int(date.year()) << '-' << unsigned(date.month()) << '-' << unsigned(date.day());
}

void print_context(const luca::ExactCashEvaluationContext &context) {
  std::cout << " context=" << context.id() << " engine=" << context.engine_version()
            << " recorded_through_epoch_ns=" << context.recorded_through().time_since_epoch().count()
            << " economic_as_of_epoch_ns=" << context.economic_as_of().time_since_epoch().count()
            << " settlement_as_of=";
  print_date(context.settlement_as_of_date().value());
  std::cout << '\n';
}

void print_report(const custom_report::CashReport &report) {
  const auto &projection = report.projection.definition();
  std::cout << "projection=" << projection.operation_id << '@' << projection.operation_version
            << " policy=" << projection.policy_id << '@' << projection.policy_version << '\n';
  for (const auto &law : report.reduction.definition().laws)
    std::cout << "declared_law=" << static_cast<int>(law.law) << " domain=" << law.domain << '\n';
  for (const auto &total : report.totals) {
    std::cout << "projected account=" << total.key().account().value()
              << " currency=" << total.key().currency().code()
              << " amount_scaled_1e6=" << total.amount().scaled_value()
              << " operation=" << total.operation_id() << '@' << total.operation_version()
              << " policy=" << total.policy().id() << '@' << total.policy().version()
              << " unit=money partition_keys=account,currency";
    print_context(total.evaluation_context());
    for (const auto &event : total.source_event_ids())
      std::cout << "  projected_event=" << event.value() << '\n';
    for (const auto &source : total.source_record_ids())
      std::cout << "  projected_source=" << source.value() << '\n';
  }
  for (const auto &observation : report.observations) {
    const auto &provenance = observation.provenance();
    std::cout << "observed account=" << observation.account().value()
              << " currency=" << observation.currency().code()
              << " amount_scaled_1e6=" << observation.amount().scaled_value()
              << " as_of_epoch_ns=" << observation.as_of().time_since_epoch().count()
              << " settlement_as_of=";
    print_date(observation.settlement_as_of_date());
    std::cout << " transformation=" << provenance.transformation_name() << '@'
              << provenance.transformation_version() << '\n';
    for (const auto &source : provenance.source_records())
      std::cout << "  observed_source=" << source.value() << '\n';
    if (provenance.transformation_metadata())
      std::cout << "  observed_metadata=" << *provenance.transformation_metadata() << '\n';
  }
  const auto &comparison = report.comparison;
  std::cout << "comparison=" << comparison.operation_id() << '@' << comparison.operation_version()
            << " policy=" << comparison.policy().id() << '@' << comparison.policy().version();
  print_context(comparison.evaluation_context());
  for (const auto &value : comparison.breaks()) {
    std::cout << "break=" << luca::category_name(value.kind())
              << " account=" << value.key().account().value()
              << " currency=" << value.key().currency().code();
    if (value.difference())
      std::cout << " observed_minus_expected_scaled_1e6=" << value.difference()->scaled_value();
    std::cout << '\n';
  }
}
} // namespace

int main() {
  using namespace luca;
  const auto usd = Currency::from_code("USD");
  const auto date = SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 5);
  const auto reduction_policy = ExactCashReductionPolicy::create("exact-cash-sum", "1");
  const auto comparison_policy = ExactCashComparisonPolicy::create("exact-cash-comparison", "1");
  if (!usd || !date || !reduction_policy || !comparison_policy) return 1;
  const Timestamp cutoff{std::chrono::sys_days{date->value()}};
  const auto context = ExactCashEvaluationContext::create(
      "synthetic-report-context", "synthetic-engine-1", cutoff, cutoff, *date);
  if (!context) return 1;
  const auto reduction = ExactCashReductionContract::create(
      CashKey{AccountId{"fund-a"}, *usd}, "1", *reduction_policy, *context);
  const auto comparison = ExactCashComparisonContract::create("1", *comparison_policy, *context);
  if (!reduction || !comparison) return 1;

  std::vector<ExactCashPartial> partials;
  // Already-valued synthetic contributions: no price, FX or lifecycle source is inferred.
  const std::vector<std::string> amounts{"1000.000000", "-250.000000", "50.000000"};
  for (std::size_t index = 0; index < amounts.size(); ++index) {
    auto amount = Money::parse(amounts[index], *usd);
    if (!amount) return 1;
    const auto suffix = std::to_string(index + 1);
    auto partial = ExactCashPartial::create(*reduction, *amount,
        {EventId{"event-" + suffix}}, {SourceRecordId{"source-" + suffix}});
    if (!partial) return 1;
    partials.push_back(std::move(*partial));
  }
  const auto amount = Money::parse("790.000000", *usd);
  const auto provenance = Provenance::create({SourceRecordId{"bank-observation-1"}},
      "synthetic-bank-observation", "1", "synthetic evidence only");
  if (!amount || !provenance) return 1;
  const auto observation = CashObservation::create(AccountId{"fund-a"}, *amount,
      cutoff, date->value(), *provenance);
  if (!observation) return 1;
  const std::vector observations{*observation};
  auto report = custom_report::project_cash_report(*comparison, partials, observations);
  if (!report) {
    std::visit([](auto error) { std::cerr << category_name(error) << '\n'; }, report.error());
    return 1;
  }
  print_report(*report);
}
