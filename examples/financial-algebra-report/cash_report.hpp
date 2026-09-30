#pragma once

#include <luca/financial_algebra.hpp>
#include <luca/reconciliation/exact_cash_comparison.hpp>

#include <map>
#include <set>
#include <variant>

namespace custom_report {

using Error = std::variant<luca::FinancialAlgebraDeclarationError,
                           luca::ExactCashReductionError, luca::ExactCashComparisonError>;

inline auto cash_algebra() {
  using namespace luca;
  const std::string domain =
      "Equal account/currency, money unit, operation/policy versions and complete context; "
      "disjoint event lineage; all intermediate scaled int64 sums representable in EVERY "
      "evaluated ordering/grouping. Zero has empty lineage. No rounding, FX or lifecycle inverse.";
  return FinancialAlgebraDescriptor::create({
      .kind = FinancialOperationKind::reduction,
      .operation_id = std::string{ExactCashReductionContract::operation_id},
      .operation_version = "1",
      .policy_id = "exact-cash-sum",
      .policy_version = "1",
      .inputs = {{"contributions", "ExactCashPartial"}},
      .output = {"total", "ExactCashReductionResult"},
      .ordering = FinancialOrdering::unordered,
      .ordering_keys = {},
      .partitioned = true,
      .partition_keys = {"account", "currency"},
      .laws = {{AlgebraLaw::identity, AlgebraLawStatus::claimed, domain},
               {AlgebraLaw::associativity, AlgebraLawStatus::claimed, domain},
               {AlgebraLaw::commutativity, AlgebraLawStatus::claimed, domain}}});
}

// Independent application-owned reporting projection. Its arithmetic is entirely
// in LUCA. Keeping both input authority roles also retains evidence for matches,
// for which compare_exact_cash intentionally emits no break.
struct CashReport {
  luca::FinancialAlgebraDescriptor projection;
  luca::FinancialAlgebraDescriptor reduction;
  std::vector<luca::ExactCashReductionResult> totals;
  std::vector<luca::CashObservation> observations;
  luca::ExactCashComparisonResult comparison;
};

inline std::expected<CashReport, Error>
project_cash_report(const luca::ExactCashComparisonContract &comparison,
                    std::span<const luca::ExactCashPartial> contributions,
                    std::span<const luca::CashObservation> observations) {
  using namespace luca;
  auto projection = FinancialAlgebraDescriptor::create({
      .kind = FinancialOperationKind::map,
      .operation_id = "example.cash-report",
      .operation_version = "1",
      .policy_id = "example.cash-report.presentation",
      .policy_version = "1",
      .inputs = {{"contributions", "ExactCashPartial"}, {"observed", "CashObservation"}},
      .output = {"report", "CashReport"},
      .ordering = FinancialOrdering::ordered,
      .ordering_keys = {"input_index"},
      .partitioned = false,
      .partition_keys = {},
      .laws = {}});
  auto reduction = cash_algebra();
  if (!projection) return std::unexpected(Error{projection.error()});
  if (!reduction) return std::unexpected(Error{reduction.error()});

  std::map<CashKey, std::vector<ExactCashPartial>> groups;
  std::set<std::string> events;
  for (const auto &partial : contributions) {
    // Prevent duplicate economic contributions even across different report keys.
    for (const auto &event : partial.source_event_ids()) {
      if (!events.insert(event.value()).second)
        return std::unexpected(Error{ExactCashReductionError::duplicate_event_lineage});
    }
    groups[partial.contract().key()].push_back(partial);
  }
  std::vector<ExactCashReductionResult> totals;
  for (const auto &[key, partials] : groups) {
    // Fixed supported operation/policy identity; all compatibility validation is
    // delegated to the existing reducer rather than trusting descriptor strings.
    auto policy = ExactCashReductionPolicy::create("exact-cash-sum", "1");
    if (!policy) return std::unexpected(Error{policy.error()});
    auto contract = ExactCashReductionContract::create(
        key, "1", *policy, comparison.evaluation_context());
    if (!contract) return std::unexpected(Error{contract.error()});
    auto total = reduce_exact_cash(*contract, partials);
    if (!total) return std::unexpected(Error{total.error()});
    totals.push_back(std::move(*total));
  }
  auto compared = compare_exact_cash(comparison, totals, observations);
  if (!compared) return std::unexpected(Error{compared.error()});
  std::vector<CashObservation> evidence{observations.begin(), observations.end()};
  std::ranges::sort(evidence, {}, &CashObservation::key);
  return CashReport{std::move(*projection), std::move(*reduction), std::move(totals),
                    std::move(evidence), std::move(*compared)};
}

} // namespace custom_report
