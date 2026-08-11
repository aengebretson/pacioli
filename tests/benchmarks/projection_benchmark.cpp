#include "benchmark.hpp"
#include "synthetic_data.hpp"

#include <memory>

namespace luca::bench {

void add_projection_benchmarks(std::vector<Benchmark>& benchmarks,
                               const Configuration& configuration) {
  auto mixed = std::make_shared<Ledger>(make_ledger(make_events(configuration.events, true, 50)));
  const auto as_of = end_time(configuration.events);
  benchmarks.push_back({"project_positions", configuration.events, "events",
    [mixed, as_of] { auto result = project_positions(mixed->entries(), as_of); if (!result || result->empty()) throw std::runtime_error("position projection failed"); return result->size(); },
    [mixed, as_of] { auto result = project_positions(mixed->entries(), as_of); return result ? result->size() : 0; }});

  const auto add_cash = [&](std::string name, std::size_t settled_percent) {
    auto ledger = std::make_shared<Ledger>(make_ledger(make_events(configuration.events, true, settled_percent)));
    const CashProjectionContext context{as_of, base_date};
    benchmarks.push_back({std::move(name), configuration.events, "events",
      [ledger, context] { auto result = project_cash(ledger->entries(), context); if (!result || result->empty()) throw std::runtime_error("cash projection failed"); return result->size(); },
      [ledger, context] { auto result = project_cash(ledger->entries(), context); return result ? result->size() : 0; }});
  };
  add_cash("project_cash_mostly_unsettled", 10);
  add_cash("project_cash_mostly_settled", 90);
  add_cash("project_cash_mixed", 50);

  const auto add_settlement = [&](std::string name, std::size_t settled_percent) {
    auto ledger = std::make_shared<Ledger>(make_ledger(make_events(configuration.events, true, settled_percent)));
    const SettlementProjectionContext context{as_of, base_date};
    benchmarks.push_back({std::move(name), configuration.events, "events",
      [ledger, context] { auto result = project_settlement_obligations(ledger->entries(), context); if (!result || result->empty()) throw std::runtime_error("settlement projection failed"); return result->size(); },
      [ledger, context] { auto result = project_settlement_obligations(ledger->entries(), context); return result ? result->size() : 0; }});
  };
  add_settlement("project_settlements_many_open", 10);
  add_settlement("project_settlements_mostly_settled", 90);
}

}  // namespace luca::bench
