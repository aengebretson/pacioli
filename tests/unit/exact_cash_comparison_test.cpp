#include "luca/event.hpp"
#include "luca/reconciliation.hpp"

#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <expected>
#include <limits>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

using namespace luca;

namespace {

const Currency usd = *Currency::from_code("USD");
const Currency eur = *Currency::from_code("EUR");
const Timestamp recorded_through{
    std::chrono::sys_days{std::chrono::year{2026} / std::chrono::June / 10}};
const Timestamp economic_as_of{
    std::chrono::sys_days{std::chrono::year{2026} / std::chrono::June / 5} +
    std::chrono::hours{23} + std::chrono::minutes{59} + std::chrono::seconds{59}};
constexpr auto settlement_date = std::chrono::year{2026} / std::chrono::June / 5;
const SettlementDate settlement_as_of = *SettlementDate::create(settlement_date);

ExactCashEvaluationContext context(std::string id = "cash-context-1",
                                   std::string engine_version = "contract-fixture-1",
                                   Timestamp recorded = recorded_through,
                                   Timestamp economic = economic_as_of,
                                   SettlementDate settlement = settlement_as_of) {
  const auto result = ExactCashEvaluationContext::create(std::move(id), std::move(engine_version),
                                                         recorded, economic, settlement);
  assert(result);
  return *result;
}

ExactCashReductionContract
reduction_contract(std::string account = "fund-a", Currency currency = usd,
                   ExactCashEvaluationContext evaluation_context = context()) {
  const auto policy = ExactCashReductionPolicy::create("exact-cash-sum", "1");
  assert(policy);
  const auto contract =
      ExactCashReductionContract::create(CashKey{AccountId{std::move(account)}, currency}, "1",
                                         *policy, std::move(evaluation_context));
  assert(contract);
  return *contract;
}

ExactCashReductionResult projection(std::string account, std::string amount, std::string event_id,
                                    std::string source_record_id, Currency currency = usd,
                                    ExactCashEvaluationContext evaluation_context = context()) {
  const auto contract =
      reduction_contract(std::move(account), currency, std::move(evaluation_context));
  const auto partial = ExactCashPartial::create(contract, *Money::parse(amount, currency),
                                                {EventId{std::move(event_id)}},
                                                {SourceRecordId{std::move(source_record_id)}});
  assert(partial);
  const std::array inputs{*partial};
  const auto result = reduce_exact_cash(contract, inputs);
  assert(result);
  return *result;
}

Provenance provenance(std::string source_record_id) {
  const auto result = Provenance::create({SourceRecordId{std::move(source_record_id)}},
                                         "bank-cash-observation", "1");
  assert(result);
  return *result;
}

CashObservation observation(std::string account, std::string amount, std::string source_record_id,
                            Currency currency = usd, Timestamp as_of = economic_as_of,
                            std::chrono::year_month_day settlement = settlement_date) {
  const auto result =
      CashObservation::create(AccountId{std::move(account)}, *Money::parse(amount, currency), as_of,
                              settlement, provenance(std::move(source_record_id)));
  assert(result);
  return *result;
}

ExactCashComparisonContract comparison_contract(
    std::string operation_version = "1", std::string policy_id = "exact-cash-comparison",
    std::string policy_version = "1", ExactCashEvaluationContext evaluation_context = context()) {
  const auto policy =
      ExactCashComparisonPolicy::create(std::move(policy_id), std::move(policy_version));
  assert(policy);
  const auto contract = ExactCashComparisonContract::create(std::move(operation_version), *policy,
                                                            std::move(evaluation_context));
  assert(contract);
  return *contract;
}

template <class T>
void expect_error(const std::expected<T, ExactCashComparisonError> &result,
                  ExactCashComparisonError error) {
  assert(!result);
  assert(result.error() == error);
  assert(!category_name(result.error()).empty());
}

} // namespace

int main() {
  static_assert(!std::is_convertible_v<CashObservation, EconomicEvent>);

  const auto comparison = comparison_contract();
  const std::vector projected{
      projection("fund-a", "1000.000000", "cash-event-1", "source.cash.1"),
  };
  const auto second = projection("fund-a", "-250.000000", "cash-event-2", "source.cash.2");
  const auto third = projection("fund-a", "50.000000", "cash-event-3", "source.cash.3");
  const std::vector fixture_partitions{projected.front(), second, third};
  const auto fixture_projection = merge_exact_cash(reduction_contract(), fixture_partitions);
  assert(fixture_projection);
  assert(fixture_projection->amount() == *Money::parse("800.000000", usd));

  const std::vector fixture_projected{*fixture_projection};
  const std::vector fixture_observed{observation("fund-a", "790.000000", "observation.bank.1")};
  const auto fixture = compare_exact_cash(comparison, fixture_projected, fixture_observed);
  assert(fixture);
  assert(fixture->operation_id() == "compare.cash.exact");
  assert(fixture->operation_version() == "1");
  assert(fixture->policy().id() == "exact-cash-comparison");
  assert(fixture->policy().version() == "1");
  assert(fixture->evaluation_context().id() == "cash-context-1");
  assert(fixture->evaluation_context().engine_version() == "contract-fixture-1");
  assert(fixture->evaluation_context().recorded_through() == recorded_through);
  assert(fixture->evaluation_context().economic_as_of() == economic_as_of);
  assert(fixture->evaluation_context().settlement_as_of_date() == settlement_as_of);
  assert(fixture->breaks().size() == 1);

  const auto &mismatch = fixture->breaks().front();
  assert((mismatch.key() == CashKey{AccountId{"fund-a"}, usd}));
  assert(mismatch.kind() == ExactCashBreakKind::amount_mismatch);
  assert(category_name(mismatch.kind()) == "amount_mismatch");
  assert(mismatch.expected() == std::optional{*Money::parse("800.000000", usd)});
  assert(mismatch.observed() == std::optional{*Money::parse("790.000000", usd)});
  assert(mismatch.difference() == std::optional{*Money::parse("-10.000000", usd)});
  assert(mismatch.projection() == std::optional{*fixture_projection});
  assert(mismatch.observation() == std::optional{fixture_observed.front()});
  assert(std::ranges::equal(
      mismatch.projection_source_event_ids(),
      std::array{EventId{"cash-event-1"}, EventId{"cash-event-2"}, EventId{"cash-event-3"}}));
  assert(std::ranges::equal(mismatch.projection_source_record_ids(),
                            std::array{SourceRecordId{"source.cash.1"},
                                       SourceRecordId{"source.cash.2"},
                                       SourceRecordId{"source.cash.3"}}));
  assert(mismatch.observation_provenance() == std::optional{fixture_observed.front().provenance()});
  assert(std::ranges::equal(mismatch.observation_provenance()->source_records(),
                            std::array{SourceRecordId{"observation.bank.1"}}));

  // Exact matches carry the same trace and produce no break.
  const std::vector exact_observed{observation("fund-a", "800.000000", "observation.bank.exact")};
  const auto exact = compare_exact_cash(comparison, fixture_projected, exact_observed);
  assert(exact && exact->breaks().empty());
  assert(exact->contract() == comparison);

  // Missing and unexpected evidence preserve only their appropriate lineage role.
  const std::vector<CashObservation> no_observations;
  const auto missing = compare_exact_cash(comparison, fixture_projected, no_observations);
  assert(missing && missing->breaks().size() == 1);
  assert(missing->breaks().front().kind() == ExactCashBreakKind::missing_observation);
  assert(missing->breaks().front().projection() == std::optional{*fixture_projection});
  assert(!missing->breaks().front().observation());
  assert(!missing->breaks().front().observation_provenance());

  const std::vector<ExactCashReductionResult> no_projections;
  const auto unexpected = compare_exact_cash(comparison, no_projections, fixture_observed);
  assert(unexpected && unexpected->breaks().size() == 1);
  assert(unexpected->breaks().front().kind() == ExactCashBreakKind::unexpected_observation);
  assert(!unexpected->breaks().front().projection());
  assert(unexpected->breaks().front().projection_source_event_ids().empty());
  assert(unexpected->breaks().front().projection_source_record_ids().empty());
  assert(unexpected->breaks().front().observation() == std::optional{fixture_observed.front()});

  // Input order cannot affect complete-key and break-kind output ordering.
  const std::vector unordered_projected{
      projection("z-account", "7", "event-z", "source-z"),
      projection("m-account", "5", "event-m", "source-m"),
  };
  const std::vector unordered_observed{
      observation("m-account", "4", "observation-m"),
      observation("a-account", "9", "observation-a"),
  };
  const auto ordered = compare_exact_cash(comparison, unordered_projected, unordered_observed);
  assert(ordered && ordered->breaks().size() == 3);
  assert(ordered->breaks()[0].key().account() == AccountId{"a-account"});
  assert(ordered->breaks()[0].kind() == ExactCashBreakKind::unexpected_observation);
  assert(ordered->breaks()[1].key().account() == AccountId{"m-account"});
  assert(ordered->breaks()[1].kind() == ExactCashBreakKind::amount_mismatch);
  assert(ordered->breaks()[2].key().account() == AccountId{"z-account"});
  assert(ordered->breaks()[2].kind() == ExactCashBreakKind::missing_observation);
  auto reversed_projected = unordered_projected;
  auto reversed_observed = unordered_observed;
  std::ranges::reverse(reversed_projected);
  std::ranges::reverse(reversed_observed);
  assert(compare_exact_cash(comparison, reversed_projected, reversed_observed) == ordered);

  // Duplicate keys fail before producing any successful result.
  const std::vector duplicate_projected{
      projection("duplicate", "1", "duplicate-event-1", "duplicate-source-1"),
      projection("duplicate", "2", "duplicate-event-2", "duplicate-source-2"),
  };
  expect_error(compare_exact_cash(comparison, duplicate_projected, no_observations),
               ExactCashComparisonError::duplicate_projected_key);
  const std::vector duplicate_observed{
      observation("duplicate", "1", "duplicate-observation-1"),
      observation("duplicate", "2", "duplicate-observation-2"),
  };
  expect_error(compare_exact_cash(comparison, no_projections, duplicate_observed),
               ExactCashComparisonError::duplicate_observation);

  // Every projection context component is part of compatibility.
  const std::array incompatible_contexts{
      context("another-context"),
      context("cash-context-1", "another-engine"),
      context("cash-context-1", "contract-fixture-1",
              recorded_through + std::chrono::nanoseconds{1}),
      context("cash-context-1", "contract-fixture-1", recorded_through,
              economic_as_of + std::chrono::nanoseconds{1}),
      context("cash-context-1", "contract-fixture-1", recorded_through, economic_as_of,
              *SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 6)),
  };
  for (std::size_t index = 0; index < incompatible_contexts.size(); ++index) {
    const std::vector incompatible{
        projection("context-account", "1", "context-event-" + std::to_string(index),
                   "context-source-" + std::to_string(index), usd, incompatible_contexts[index]),
    };
    expect_error(compare_exact_cash(comparison, incompatible, no_observations),
                 ExactCashComparisonError::context_mismatch);
  }

  const std::vector wrong_time{observation("fund-a", "790", "wrong-time", usd,
                                           economic_as_of + std::chrono::nanoseconds{1})};
  expect_error(compare_exact_cash(comparison, fixture_projected, wrong_time),
               ExactCashComparisonError::observation_time_mismatch);
  const std::vector wrong_settlement{observation("fund-a", "790", "wrong-settlement", usd,
                                                 economic_as_of,
                                                 std::chrono::year{2026} / std::chrono::June / 6)};
  expect_error(compare_exact_cash(comparison, fixture_projected, wrong_settlement),
               ExactCashComparisonError::observation_settlement_date_mismatch);

  // Account identifiers are checked at the comparison boundary. Currency/key
  // incompatibility is unrepresentable because both public input types derive
  // their CashKey currency from their Money value.
  const std::vector invalid_account{observation("bad account", "1", "invalid-account-source")};
  expect_error(compare_exact_cash(comparison, no_projections, invalid_account),
               ExactCashComparisonError::account_mismatch);
  const auto euro_observation = observation("fund-a", "1", "euro-source", eur);
  assert(euro_observation.key().currency() == euro_observation.amount().currency());
  const auto mismatched_partial =
      ExactCashPartial::create(reduction_contract(), *Money::parse("1", eur),
                               {EventId{"currency-event"}}, {SourceRecordId{"currency-source"}});
  assert(!mismatched_partial);
  assert(mismatched_partial.error() == ExactCashReductionError::currency_mismatch);

  expect_error(ExactCashComparisonPolicy::create("", "1"),
               ExactCashComparisonError::incomplete_policy_identity);
  expect_error(ExactCashComparisonPolicy::create("policy", ""),
               ExactCashComparisonError::incomplete_policy_identity);
  expect_error(ExactCashComparisonPolicy::create("bad policy", "1"),
               ExactCashComparisonError::invalid_identifier);
  const auto valid_policy = *ExactCashComparisonPolicy::create("policy", "1");
  expect_error(ExactCashComparisonContract::create("", valid_policy, context()),
               ExactCashComparisonError::incomplete_operation_identity);
  expect_error(ExactCashComparisonContract::create("bad version", valid_policy, context()),
               ExactCashComparisonError::invalid_identifier);

  const std::vector minimum_projected{
      projection("overflow", "-9223372036854.775808", "minimum-event", "minimum-source")};
  const std::vector maximum_observed{
      observation("overflow", "9223372036854.775807", "maximum-source")};
  expect_error(compare_exact_cash(comparison, minimum_projected, maximum_observed),
               ExactCashComparisonError::amount_overflow);

  // Comparison owns copies in its output and never changes either input port.
  const auto projected_before = unordered_projected;
  const auto observed_before = unordered_observed;
  const auto immutable_result =
      compare_exact_cash(comparison, unordered_projected, unordered_observed);
  assert(immutable_result);
  assert(unordered_projected == projected_before);
  assert(unordered_observed == observed_before);
}
