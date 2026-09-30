#include "luca/financial_algebra.hpp"
#include "../../examples/financial-algebra-report/cash_report.hpp"

#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <limits>
#include <string>

using namespace luca;

namespace {
using DeclarationError = FinancialAlgebraDeclarationError;

void expect_declaration_error(FinancialAlgebraDescriptor::Definition definition,
                              DeclarationError expected) {
  const auto result = FinancialAlgebraDescriptor::create(std::move(definition));
  assert(!result && result.error() == expected);
  assert(!category_name(result.error()).empty());
}

void declarations() {
  auto valid = custom_report::cash_algebra();
  assert(valid);
  auto definition = valid->definition();
  auto owned = FinancialAlgebraDescriptor::create(definition);
  assert(owned);
  definition.operation_id = "changed";
  definition.inputs.front().role = "changed";
  definition.partition_keys.clear();
  definition.laws.front().domain.clear();
  assert(*owned == *valid); // All strings, ports, keys and domains are owned.
  assert(owned->law_status(AlgebraLaw::associativity) == AlgebraLawStatus::claimed);
  assert(owned->law_status(AlgebraLaw::invertibility) == AlgebraLawStatus::unknown);

  for (const std::string &invalid : {std::string{}, std::string{"bad id"},
                                   std::string{"bad\n"}, std::string{"bad\0id", 6}}) {
    definition = valid->definition();
    definition.operation_id = invalid;
    expect_declaration_error(definition, DeclarationError::invalid_identifier);
    definition = valid->definition();
    definition.policy_version = invalid;
    expect_declaration_error(definition, DeclarationError::invalid_identifier);
  }
  definition = valid->definition();
  definition.kind = static_cast<FinancialOperationKind>(99);
  expect_declaration_error(definition, DeclarationError::invalid_enum);
  definition = valid->definition();
  definition.inputs.clear();
  expect_declaration_error(definition, DeclarationError::invalid_ports);
  definition = valid->definition();
  definition.inputs.push_back(definition.inputs.front());
  expect_declaration_error(definition, DeclarationError::invalid_ports);
  definition = valid->definition();
  definition.output.type_name.clear();
  expect_declaration_error(definition, DeclarationError::invalid_ports);
  definition = valid->definition();
  definition.partition_keys.clear();
  expect_declaration_error(definition, DeclarationError::invalid_partition_keys);
  definition = valid->definition();
  definition.partition_keys.push_back("account");
  expect_declaration_error(definition, DeclarationError::invalid_partition_keys);
  definition = valid->definition();
  definition.partitioned = false;
  expect_declaration_error(definition, DeclarationError::invalid_partition_keys);
  definition = valid->definition();
  definition.laws.front().domain = " \n\t";
  expect_declaration_error(definition, DeclarationError::missing_law_domain);
  definition = valid->definition();
  definition.laws.push_back(definition.laws.front());
  expect_declaration_error(definition, DeclarationError::duplicate_law);
  for (auto law : {AlgebraLaw::invertibility, AlgebraLaw::distributivity}) {
    definition = valid->definition();
    definition.laws = {{law, AlgebraLawStatus::claimed, "unsupported composition"}};
    expect_declaration_error(definition, DeclarationError::unsupported_law_claim);
  }
  definition = valid->definition();
  definition.laws = {{AlgebraLaw::associativity, AlgebraLawStatus::unknown, {}}};
  auto unknown = FinancialAlgebraDescriptor::create(definition);
  assert(unknown && unknown->law_status(AlgebraLaw::associativity) == AlgebraLawStatus::unknown);
  definition.laws.front().status = static_cast<AlgebraLawStatus>(99);
  expect_declaration_error(definition, DeclarationError::invalid_enum);
  definition.laws = {{static_cast<AlgebraLaw>(99), AlgebraLawStatus::unknown, {}}};
  expect_declaration_error(definition, DeclarationError::invalid_enum);

  definition = valid->definition();
  definition.kind = FinancialOperationKind::ordered_fold;
  definition.laws.clear();
  expect_declaration_error(definition, DeclarationError::invalid_ordering);
  definition.ordering = FinancialOrdering::ordered;
  expect_declaration_error(definition, DeclarationError::invalid_ordering);
  definition.ordering_keys = {"effective_at", "sequence"};
  assert(FinancialAlgebraDescriptor::create(definition));
  definition.laws = {{AlgebraLaw::commutativity, AlgebraLawStatus::claimed, "all records"}};
  expect_declaration_error(definition, DeclarationError::unsupported_law_claim);
  definition.laws.clear();
  definition.ordering_keys.push_back("sequence");
  expect_declaration_error(definition, DeclarationError::invalid_ordering);

  definition = valid->definition();
  definition.kind = FinancialOperationKind::comparison;
  definition.laws.clear();
  expect_declaration_error(definition, DeclarationError::invalid_ports);
  definition.inputs = {{"projected", "ExactCashReductionResult"}, {"observed", "CashObservation"}};
  assert(FinancialAlgebraDescriptor::create(definition));
  definition.laws = {{AlgebraLaw::commutativity, AlgebraLawStatus::claimed, "swapped ports"}};
  expect_declaration_error(definition, DeclarationError::unsupported_law_claim);
  definition.laws.clear();
  definition.inputs[1].role = "input";
  expect_declaration_error(definition, DeclarationError::invalid_ports);
}

void report_semantics() {
  const auto usd = *Currency::from_code("USD");
  const auto eur = *Currency::from_code("EUR");
  const auto date = *SettlementDate::create(std::chrono::year{2026} / std::chrono::June / 5);
  const Timestamp cutoff{std::chrono::sys_days{date.value()}};
  const auto context = *ExactCashEvaluationContext::create("context", "engine-1", cutoff, cutoff, date);
  const auto policy = *ExactCashReductionPolicy::create("exact-cash-sum", "1");
  const auto contract = *ExactCashReductionContract::create(
      CashKey{AccountId{"fund-a"}, usd}, "1", policy, context);
  const auto comparison = *ExactCashComparisonContract::create("1",
      *ExactCashComparisonPolicy::create("exact-cash-comparison", "1"), context);
  auto partial = [](const ExactCashReductionContract &rule, std::int64_t amount,
                    const std::string &id) {
    return *ExactCashPartial::create(rule, Money::from_scaled(amount, rule.key().currency()),
        {EventId{id}}, {SourceRecordId{"source-" + id}});
  };
  auto observe = [&](Currency currency, std::int64_t amount, std::string account = "fund-a") {
    return *CashObservation::create(AccountId{std::move(account)}, Money::from_scaled(amount, currency),
        cutoff, date.value(), *Provenance::create({SourceRecordId{"external-bank"}},
            "synthetic-bank", "1", "available metadata"));
  };
  const std::vector partials{partial(contract, 1000000000, "e1"),
                           partial(contract, -250000000, "e2"),
                           partial(contract, 50000000, "e3")};
  const std::array observations{observe(usd, 790000000)};
  const auto report = custom_report::project_cash_report(comparison, partials, observations);
  assert(report && report->totals.size() == 1 && report->comparison.breaks().size() == 1);
  assert(report->totals.front().amount().scaled_value() == 800000000);
  assert(report->totals.front().source_event_ids().size() == 3);
  assert(report->totals.front().source_record_ids().size() == 3);
  assert(report->totals.front().evaluation_context() == context);
  assert(report->observations.front().provenance() == observations.front().provenance());
  const auto &mismatch = report->comparison.breaks().front();
  assert(mismatch.kind() == ExactCashBreakKind::amount_mismatch);
  assert(mismatch.difference()->scaled_value() == -10000000);
  assert(mismatch.projection() == report->totals.front());
  assert(mismatch.observation() == observations.front());
  const auto repeated = custom_report::project_cash_report(comparison, partials, observations);
  assert(repeated && repeated->totals == report->totals &&
         repeated->observations == report->observations && repeated->comparison == report->comparison);

  const std::array matches{observe(usd, 800000000)};
  auto matched = custom_report::project_cash_report(comparison, partials, matches);
  assert(matched && matched->comparison.breaks().empty());
  assert(matched->totals.front().source_event_ids().size() == 3);
  assert(matched->observations.front() == matches.front()); // Match evidence is not discarded.
  auto missing = custom_report::project_cash_report(comparison, partials, {});
  assert(missing && missing->comparison.breaks().front().kind() == ExactCashBreakKind::missing_observation);
  auto unexpected = custom_report::project_cash_report(comparison, {}, observations);
  assert(unexpected && unexpected->comparison.breaks().front().kind() == ExactCashBreakKind::unexpected_observation);
  const std::array other_currency{observe(eur, 800000000)};
  auto separate = custom_report::project_cash_report(comparison, partials, other_currency);
  assert(separate && separate->comparison.breaks().size() == 2); // No implicit FX.

  const auto changed_context = *ExactCashEvaluationContext::create(
      "context", "engine-1", cutoff + std::chrono::seconds{1}, cutoff, date);
  const auto incompatible = *ExactCashReductionContract::create(contract.key(), "1", policy, changed_context);
  const std::array changed{partial(incompatible, 1, "e4")};
  auto failed = custom_report::project_cash_report(comparison, changed, {});
  assert(!failed && std::get<ExactCashReductionError>(failed.error()) == ExactCashReductionError::context_mismatch);
  const auto bad_partition = *ExactCashReductionContract::create(contract.key(), "1", policy,
      context, ExactCashReductionUnit::money, *ExactCashPartitioning::create({ExactCashPartitionKey::account}));
  const std::array incomplete{partial(bad_partition, 1, "e4")};
  failed = custom_report::project_cash_report(comparison, incomplete, {});
  assert(!failed && std::get<ExactCashReductionError>(failed.error()) == ExactCashReductionError::partition_key_mismatch);
  auto bad_currency = ExactCashPartial::create(contract, Money::from_scaled(1, eur),
      {EventId{"e4"}}, {SourceRecordId{"s4"}});
  assert(!bad_currency && bad_currency.error() == ExactCashReductionError::currency_mismatch);

  const auto eur_contract = *ExactCashReductionContract::create(
      CashKey{AccountId{"fund-a"}, eur}, "1", policy, context);
  const std::array mixed{partials.front(), partial(eur_contract, 42, "e4")};
  auto multiple = custom_report::project_cash_report(comparison, mixed, {});
  assert(multiple && multiple->totals.size() == 2);
  assert(multiple->totals[0].key().currency() == eur && multiple->totals[1].key().currency() == usd);
  const std::array duplicates{partials.front(), partial(eur_contract, 42, "e1")};
  failed = custom_report::project_cash_report(comparison, duplicates, {});
  assert(!failed && std::get<ExactCashReductionError>(failed.error()) == ExactCashReductionError::duplicate_event_lineage);

  // A representable final sum is insufficient to permit arbitrary reordering.
  constexpr auto maximum = std::numeric_limits<std::int64_t>::max();
  const std::array overflowing{partial(contract, maximum, "max"),
                             partial(contract, 1, "plus"), partial(contract, -1, "minus")};
  failed = custom_report::project_cash_report(comparison, overflowing, {});
  assert(!failed && std::get<ExactCashReductionError>(failed.error()) == ExactCashReductionError::amount_overflow);
  const std::array representable{overflowing[0], overflowing[2], overflowing[1]};
  auto reordered = custom_report::project_cash_report(comparison, representable, {});
  assert(reordered && reordered->totals.front().amount().scaled_value() == maximum);

  // On this bounded domain, identity and supported partition merge preserve lineage.
  const auto prefix = reduce_exact_cash(contract, std::span{partials}.first(2));
  const auto suffix = reduce_exact_cash(contract, std::span{partials}.last(1));
  const auto zero = exact_cash_zero(contract);
  assert(prefix && suffix && zero);
  const std::array partitions{*suffix, *zero, *prefix};
  const auto merged = merge_exact_cash(contract, partitions);
  assert(merged && *merged == report->totals.front());
}
} // namespace

int main() {
  declarations();
  report_semantics();
}
