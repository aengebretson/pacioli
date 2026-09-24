#include "luca/portfolio.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <expected>
#include <limits>
#include <string>
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
const SettlementDate settlement_as_of =
    *SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 5);

ExactCashEvaluationContext context(std::string id = "cash-context-1",
                                   std::string engine_version = "contract-fixture-1",
                                   Timestamp recorded = recorded_through,
                                   Timestamp economic = economic_as_of,
                                   SettlementDate settlement = settlement_as_of) {
  auto result = ExactCashEvaluationContext::create(std::move(id), std::move(engine_version),
                                                   recorded, economic, settlement);
  assert(result);
  return *result;
}

ExactCashReductionContract
contract(std::string account = "fund-a", Currency currency = usd,
         std::string operation_version = "1", std::string policy_id = "exact-cash-sum",
         std::string policy_version = "1",
         ExactCashEvaluationContext evaluation_context = context(),
         ExactCashReductionUnit unit = ExactCashReductionUnit::money,
         ExactCashPartitioning partitioning = ExactCashPartitioning::account_currency()) {
  auto policy = ExactCashReductionPolicy::create(std::move(policy_id), std::move(policy_version));
  assert(policy);
  auto result = ExactCashReductionContract::create(
      CashKey{AccountId{std::move(account)}, currency}, std::move(operation_version), *policy,
      std::move(evaluation_context), unit, std::move(partitioning));
  assert(result);
  return *result;
}

ExactCashPartial partial(const ExactCashReductionContract &reduction_contract, std::string amount,
                         std::string event_id, std::vector<SourceRecordId> source_records) {
  auto value = ExactCashPartial::create(reduction_contract,
                                        *Money::parse(amount, reduction_contract.key().currency()),
                                        {EventId{std::move(event_id)}}, std::move(source_records));
  assert(value);
  return *value;
}

ExactCashPartial partial(const ExactCashReductionContract &reduction_contract, std::string amount,
                         std::string event_id, std::string source_record_id) {
  return partial(reduction_contract, std::move(amount), std::move(event_id),
                 {SourceRecordId{std::move(source_record_id)}});
}

template <class T>
void expect_error(const std::expected<T, ExactCashReductionError> &result,
                  ExactCashReductionError error) {
  assert(!result);
  assert(result.error() == error);
  assert(!category_name(result.error()).empty());
}

template <class Partial>
std::expected<ExactCashReductionResult, ExactCashReductionError>
reduce_one(const ExactCashReductionContract &expected, const Partial &value) {
  const std::array values{value};
  return reduce_exact_cash(expected, values);
}

std::expected<ExactCashReductionResult, ExactCashReductionError>
merge_one(const ExactCashReductionContract &expected, const ExactCashReductionResult &value) {
  const std::array values{value};
  return merge_exact_cash(expected, values);
}

ExactCashReductionResult result(const ExactCashReductionContract &reduction_contract,
                                std::string event_id) {
  const auto value = partial(reduction_contract, "1", event_id, event_id + "-source");
  auto reduced = reduce_one(reduction_contract, value);
  assert(reduced);
  return *reduced;
}

} // namespace

int main() {
  const auto reduction_contract = contract();
  const auto first = partial(reduction_contract, "1000.000000", "cash-event-1", "source.cash.1");
  const auto second = partial(reduction_contract, "-250.000000", "cash-event-2", "source.cash.2");
  const auto third = partial(reduction_contract, "50.000000", "cash-event-3", "source.cash.3");
  const std::vector inputs{first, second, third};

  const auto full = reduce_exact_cash(reduction_contract, inputs);
  assert(full);
  assert(full->amount() == *Money::parse("800.000000", usd));
  assert((full->key() == CashKey{AccountId{"fund-a"}, usd}));
  assert(full->operation_id() == "reduce.cash.exact");
  assert(full->operation_version() == "1");
  assert(full->policy().id() == "exact-cash-sum");
  assert(full->policy().version() == "1");
  assert(full->evaluation_context().id() == "cash-context-1");
  assert(full->evaluation_context().engine_version() == "contract-fixture-1");
  assert(full->evaluation_context().recorded_through() == recorded_through);
  assert(full->evaluation_context().economic_as_of() == economic_as_of);
  assert(full->evaluation_context().settlement_as_of_date() == settlement_as_of);
  assert(full->unit() == ExactCashReductionUnit::money);
  assert(full->partitioning() == ExactCashPartitioning::account_currency());
  assert(std::ranges::equal(
      full->source_event_ids(),
      std::array{EventId{"cash-event-1"}, EventId{"cash-event-2"}, EventId{"cash-event-3"}}));
  assert(
      std::ranges::equal(full->source_record_ids(), std::array{SourceRecordId{"source.cash.1"},
                                                               SourceRecordId{"source.cash.2"},
                                                               SourceRecordId{"source.cash.3"}}));

  // Full, incremental, partitioned, and differently ordered evaluation are equal.
  const std::vector prefix_inputs{first, second};
  const std::vector suffix_inputs{third};
  const auto prefix = reduce_exact_cash(reduction_contract, prefix_inputs);
  const auto suffix = reduce_exact_cash(reduction_contract, suffix_inputs);
  assert(prefix && prefix->amount() == *Money::parse("750.000000", usd));
  assert(suffix && suffix->amount() == *Money::parse("50.000000", usd));
  const std::vector incremental_partials{*prefix, *suffix};
  const auto incremental = merge_exact_cash(reduction_contract, incremental_partials);
  assert(incremental == full);

  const std::vector reversed_partitions{*suffix, *prefix};
  const auto partitioned = merge_exact_cash(reduction_contract, reversed_partitions);
  assert(partitioned == full);
  auto reversed_inputs = inputs;
  std::ranges::reverse(reversed_inputs);
  assert(reduce_exact_cash(reduction_contract, reversed_inputs) == full);

  const auto one = reduce_one(reduction_contract, first);
  const auto two = reduce_one(reduction_contract, second);
  const auto three = reduce_one(reduction_contract, third);
  assert(one && two && three);
  const std::vector first_pair{*one, *two};
  const auto left_prefix = merge_exact_cash(reduction_contract, first_pair);
  const std::vector left_grouping{*left_prefix, *three};
  const std::vector second_pair{*two, *three};
  const auto right_suffix = merge_exact_cash(reduction_contract, second_pair);
  const std::vector right_grouping{*one, *right_suffix};
  assert(merge_exact_cash(reduction_contract, left_grouping) == full);
  assert(merge_exact_cash(reduction_contract, right_grouping) == full);

  // The identity is created only from an explicit compatible contract.
  const auto zero = exact_cash_zero(reduction_contract);
  assert(zero);
  assert(zero->amount() == Money::from_scaled(0, usd));
  assert(zero->source_event_ids().empty() && zero->source_record_ids().empty());
  assert(reduce_exact_cash(reduction_contract, std::span<const ExactCashPartial>{}) == zero);
  const std::vector with_identity{*zero, *full};
  assert(merge_exact_cash(reduction_contract, with_identity) == full);

  const auto account_only = *ExactCashPartitioning::create({ExactCashPartitionKey::account});
  expect_error(exact_cash_zero(contract("fund-a", usd, "1", "exact-cash-sum", "1", context(),
                                        ExactCashReductionUnit::quantity)),
               ExactCashReductionError::unit_mismatch);
  expect_error(exact_cash_zero(contract("fund-a", usd, "1", "exact-cash-sum", "1", context(),
                                        ExactCashReductionUnit::money, account_only)),
               ExactCashReductionError::partition_key_mismatch);

  // Lineage is canonical. Duplicate events are rejected before arithmetic;
  // repeated source evidence is retained once.
  const auto shared_source_first =
      partial(reduction_contract, "1", "event-b",
              {SourceRecordId{"shared-source"}, SourceRecordId{"shared-source"}});
  const auto shared_source_second = partial(reduction_contract, "2", "event-a", "shared-source");
  const std::vector shared_source_inputs{shared_source_first, shared_source_second};
  const auto shared_source = reduce_exact_cash(reduction_contract, shared_source_inputs);
  assert(shared_source);
  assert(std::ranges::equal(shared_source->source_event_ids(),
                            std::array{EventId{"event-a"}, EventId{"event-b"}}));
  assert(std::ranges::equal(shared_source->source_record_ids(),
                            std::array{SourceRecordId{"shared-source"}}));

  const auto repeated_event = partial(reduction_contract, "2", "cash-event-1", "other-source");
  const std::vector duplicate_event_inputs{first, repeated_event};
  expect_error(reduce_exact_cash(reduction_contract, duplicate_event_inputs),
               ExactCashReductionError::duplicate_event_lineage);
  const auto repeated_event_result = reduce_one(reduction_contract, repeated_event);
  assert(repeated_event_result);
  const std::vector duplicate_event_results{*one, *repeated_event_result};
  expect_error(merge_exact_cash(reduction_contract, duplicate_event_results),
               ExactCashReductionError::duplicate_event_lineage);
  expect_error(ExactCashPartial::create(reduction_contract, *Money::parse("1", usd),
                                        {EventId{"same"}, EventId{"same"}},
                                        {SourceRecordId{"source"}}),
               ExactCashReductionError::duplicate_event_lineage);

  // Every compatibility dimension has a stable, distinct diagnostic.
  expect_error(reduce_one(reduction_contract,
                          partial(contract("fund-b"), "1", "other-event", "other-source")),
               ExactCashReductionError::account_mismatch);
  expect_error(reduce_one(reduction_contract,
                          partial(contract("fund-a", eur), "1", "other-event", "other-source")),
               ExactCashReductionError::currency_mismatch);
  expect_error(reduce_one(reduction_contract, partial(contract("fund-a", usd, "2"), "1",
                                                      "other-event", "other-source")),
               ExactCashReductionError::operation_version_mismatch);
  expect_error(
      reduce_one(reduction_contract, partial(contract("fund-a", usd, "1", "another-policy"), "1",
                                             "other-event", "other-source")),
      ExactCashReductionError::policy_id_mismatch);
  expect_error(
      reduce_one(reduction_contract, partial(contract("fund-a", usd, "1", "exact-cash-sum", "2"),
                                             "1", "other-event", "other-source")),
      ExactCashReductionError::policy_version_mismatch);

  const std::array mismatched_contexts{
      context("another-context"),
      context("cash-context-1", "another-engine"),
      context("cash-context-1", "contract-fixture-1",
              recorded_through + std::chrono::nanoseconds{1}),
      context("cash-context-1", "contract-fixture-1", recorded_through,
              economic_as_of + std::chrono::nanoseconds{1}),
      context("cash-context-1", "contract-fixture-1", recorded_through, economic_as_of,
              *SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 6)),
  };
  for (const auto &mismatched_context : mismatched_contexts) {
    expect_error(
        reduce_one(reduction_contract,
                   partial(contract("fund-a", usd, "1", "exact-cash-sum", "1", mismatched_context),
                           "1", "other-event", "other-source")),
        ExactCashReductionError::context_mismatch);
  }
  expect_error(
      reduce_one(reduction_contract, partial(contract("fund-a", usd, "1", "exact-cash-sum", "1",
                                                      context(), ExactCashReductionUnit::quantity),
                                             "1", "other-event", "other-source")),
      ExactCashReductionError::unit_mismatch);
  expect_error(reduce_one(reduction_contract,
                          partial(contract("fund-a", usd, "1", "exact-cash-sum", "1", context(),
                                           ExactCashReductionUnit::money, account_only),
                                  "1", "other-event", "other-source")),
               ExactCashReductionError::partition_key_mismatch);

  // Compatible-result merging performs the same complete checks.
  expect_error(merge_one(reduction_contract, result(contract("fund-b"), "merge-account-event")),
               ExactCashReductionError::account_mismatch);
  expect_error(
      merge_one(reduction_contract, result(contract("fund-a", eur), "merge-currency-event")),
      ExactCashReductionError::currency_mismatch);
  expect_error(
      merge_one(reduction_contract, result(contract("fund-a", usd, "2"), "merge-operation-event")),
      ExactCashReductionError::operation_version_mismatch);
  expect_error(merge_one(reduction_contract, result(contract("fund-a", usd, "1", "another-policy"),
                                                    "merge-policy-event")),
               ExactCashReductionError::policy_id_mismatch);
  expect_error(
      merge_one(reduction_contract, result(contract("fund-a", usd, "1", "exact-cash-sum", "2"),
                                           "merge-policy-version-event")),
      ExactCashReductionError::policy_version_mismatch);
  expect_error(merge_one(reduction_contract, result(contract("fund-a", usd, "1", "exact-cash-sum",
                                                             "1", context("merge-context")),
                                                    "merge-context-event")),
               ExactCashReductionError::context_mismatch);
  const std::array full_result{*full};
  expect_error(merge_exact_cash(contract("fund-a", usd, "1", "exact-cash-sum", "1", context(),
                                         ExactCashReductionUnit::quantity),
                                full_result),
               ExactCashReductionError::unit_mismatch);
  expect_error(merge_exact_cash(contract("fund-a", usd, "1", "exact-cash-sum", "1", context(),
                                         ExactCashReductionUnit::money, account_only),
                                full_result),
               ExactCashReductionError::partition_key_mismatch);

  // Construction rejects malformed identities and incomplete context/lineage.
  expect_error(ExactCashReductionPolicy::create("", "1"),
               ExactCashReductionError::invalid_identifier);
  expect_error(ExactCashReductionPolicy::create("policy", "bad version"),
               ExactCashReductionError::invalid_identifier);
  expect_error(ExactCashEvaluationContext::create("", "engine", recorded_through, economic_as_of,
                                                  settlement_as_of),
               ExactCashReductionError::incomplete_context);
  expect_error(ExactCashEvaluationContext::create("context", "", recorded_through, economic_as_of,
                                                  settlement_as_of),
               ExactCashReductionError::incomplete_context);
  expect_error(ExactCashEvaluationContext::create("bad context", "engine", recorded_through,
                                                  economic_as_of, settlement_as_of),
               ExactCashReductionError::invalid_identifier);
  const auto policy = *ExactCashReductionPolicy::create("policy", "1");
  expect_error(
      ExactCashReductionContract::create(CashKey{AccountId{""}, usd}, "1", policy, context()),
      ExactCashReductionError::invalid_identifier);
  expect_error(
      ExactCashReductionContract::create(CashKey{AccountId{"account"}, usd}, "", policy, context()),
      ExactCashReductionError::invalid_identifier);
  expect_error(ExactCashPartial::create(reduction_contract, *Money::parse("1", usd), {},
                                        {SourceRecordId{"source"}}),
               ExactCashReductionError::incomplete_lineage);
  expect_error(
      ExactCashPartial::create(reduction_contract, *Money::parse("1", usd), {EventId{"event"}}, {}),
      ExactCashReductionError::incomplete_lineage);
  expect_error(ExactCashPartial::create(reduction_contract, *Money::parse("1", usd),
                                        {EventId{"bad event"}}, {SourceRecordId{"source"}}),
               ExactCashReductionError::invalid_identifier);
  expect_error(ExactCashPartial::create(reduction_contract, *Money::parse("1", eur),
                                        {EventId{"event"}}, {SourceRecordId{"source"}}),
               ExactCashReductionError::currency_mismatch);
  expect_error(ExactCashPartitioning::create({}), ExactCashReductionError::partition_key_mismatch);
  expect_error(ExactCashPartitioning::create(
                   {ExactCashPartitionKey::account, ExactCashPartitionKey::account}),
               ExactCashReductionError::partition_key_mismatch);
  assert(*ExactCashPartitioning::create(
             {ExactCashPartitionKey::currency, ExactCashPartitionKey::account}) ==
         ExactCashPartitioning::account_currency());

  // Money::add remains authoritative and overflow yields no result.
  const auto maximum = ExactCashPartial::create(
      reduction_contract, Money::from_scaled(std::numeric_limits<std::int64_t>::max(), usd),
      {EventId{"maximum-event"}}, {SourceRecordId{"maximum-source"}});
  const auto plus_one =
      ExactCashPartial::create(reduction_contract, Money::from_scaled(1, usd),
                               {EventId{"plus-one-event"}}, {SourceRecordId{"plus-one-source"}});
  assert(maximum && plus_one);
  const std::vector overflowing_inputs{*maximum, *plus_one};
  expect_error(reduce_exact_cash(reduction_contract, overflowing_inputs),
               ExactCashReductionError::amount_overflow);
  const auto maximum_result = reduce_one(reduction_contract, *maximum);
  const auto plus_one_result = reduce_one(reduction_contract, *plus_one);
  assert(maximum_result && plus_one_result);
  const std::vector overflowing_results{*maximum_result, *plus_one_result};
  expect_error(merge_exact_cash(reduction_contract, overflowing_results),
               ExactCashReductionError::amount_overflow);
}
