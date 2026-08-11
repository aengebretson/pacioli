#include "benchmark.hpp"
#include "synthetic_data.hpp"

#include <memory>

namespace luca::bench {
namespace {

struct PositionScenario {
  std::vector<Position> expected;
  std::vector<PositionObservation> observed;
  std::size_t breaks{};
};

PositionScenario positions(std::size_t rows, std::size_t break_percent) {
  PositionScenario scenario;
  scenario.expected.reserve(rows);
  scenario.observed.reserve(rows + rows / 10);
  const auto as_of = end_time(rows);
  const auto source = provenance();
  const auto break_rows = rows * break_percent / 100;
  for (std::size_t i = 0; i < rows; ++i) {
    const AccountId account{"account-" + std::to_string(i % account_count)};
    const InstrumentId instrument{"instrument-" + std::to_string(i / account_count)};
    const auto quantity = Quantity::from_scaled(static_cast<std::int64_t>(100'000'000 + i));
    scenario.expected.emplace_back(PositionKey{account, instrument}, quantity);
    if (i < break_rows && i % 3 == 0) { ++scenario.breaks; continue; }
    const auto observed_quantity = i < break_rows && i % 3 == 1
        ? Quantity::from_scaled(quantity.scaled_value() + 1) : quantity;
    auto observation = PositionObservation::create(account, instrument, observed_quantity, as_of, source);
    scenario.observed.push_back(std::move(*observation));
    if (i < break_rows && i % 3 == 1) ++scenario.breaks;
  }
  for (std::size_t i = 2; i < break_rows; i += 3) {
    auto observation = PositionObservation::create(
        AccountId{"unexpected-account"}, InstrumentId{"unexpected-" + std::to_string(i)},
        Quantity::from_scaled(1), as_of, source);
    scenario.observed.push_back(std::move(*observation));
    ++scenario.breaks;
  }
  return scenario;
}

struct CashScenario {
  std::vector<CashBalance> expected;
  std::vector<CashObservation> observed;
  std::size_t breaks{};
};

CashScenario cash(std::size_t rows, std::size_t break_percent) {
  CashScenario scenario;
  scenario.expected.reserve(rows);
  scenario.observed.reserve(rows + rows / 10);
  const auto as_of = end_time(rows);
  const auto source = provenance();
  const auto break_rows = rows * break_percent / 100;
  for (std::size_t i = 0; i < rows; ++i) {
    const AccountId account{"cash-account-" + std::to_string(i)};
    const auto amount = Money::from_scaled(static_cast<std::int64_t>(1'000'000 + i), currency(i));
    scenario.expected.emplace_back(account, amount);
    if (i < break_rows && i % 3 == 0) { ++scenario.breaks; continue; }
    const auto observed_amount = i < break_rows && i % 3 == 1
        ? Money::from_scaled(amount.scaled_value() + 1, amount.currency()) : amount;
    auto observation = CashObservation::create(account, observed_amount, as_of, base_date, source);
    scenario.observed.push_back(std::move(*observation));
    if (i < break_rows && i % 3 == 1) ++scenario.breaks;
  }
  for (std::size_t i = 2; i < break_rows; i += 3) {
    auto observation = CashObservation::create(
        AccountId{"unexpected-cash-" + std::to_string(i)},
        Money::from_scaled(1, currency(i)), as_of, base_date, source);
    scenario.observed.push_back(std::move(*observation));
    ++scenario.breaks;
  }
  return scenario;
}

}  // namespace

void add_reconciliation_benchmarks(std::vector<Benchmark>& benchmarks,
                                   const Configuration& configuration) {
  const auto rows = std::min<std::size_t>(configuration.events, 100'000);
  for (const auto rate : {std::size_t{0}, std::size_t{1}, std::size_t{10}}) {
    auto scenario = std::make_shared<PositionScenario>(positions(rows, rate));
    const PositionReconciliationContext context{end_time(rows)};
    benchmarks.push_back({"reconcile_positions_" + std::to_string(rate) + "pct_breaks", rows, "rows",
      [scenario, context] { auto result = reconcile_positions(scenario->expected, scenario->observed, context); if (!result || result->size() != scenario->breaks) throw std::runtime_error("position reconciliation mismatch"); return result->size(); },
      [scenario, context] { auto result = reconcile_positions(scenario->expected, scenario->observed, context); return result ? result->size() : 0; }});
  }
  const auto cash_rows = std::min<std::size_t>(configuration.events, 10'000);
  for (const auto rate : {std::size_t{0}, std::size_t{1}, std::size_t{10}}) {
    auto scenario = std::make_shared<CashScenario>(cash(cash_rows, rate));
    const CashReconciliationContext context{end_time(cash_rows), base_date};
    benchmarks.push_back({"reconcile_cash_" + std::to_string(rate) + "pct_breaks", cash_rows, "rows",
      [scenario, context] { auto result = reconcile_cash(scenario->expected, scenario->observed, context); if (!result || result->size() != scenario->breaks) throw std::runtime_error("cash reconciliation mismatch"); return result->size(); },
      [scenario, context] { auto result = reconcile_cash(scenario->expected, scenario->observed, context); return result ? result->size() : 0; }});
  }
}

}  // namespace luca::bench
