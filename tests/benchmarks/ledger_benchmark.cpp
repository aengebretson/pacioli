#include "benchmark.hpp"
#include "synthetic_data.hpp"

#include <memory>

namespace luca::bench {
namespace {

Benchmark view_benchmark(std::string name, std::shared_ptr<Ledger> ledger,
                         std::function<LedgerEntryView()> operation) {
  const auto count = operation().size();
  return {std::move(name), ledger->size(), "events", [count] { return count; },
          [operation = std::move(operation)] {
            const auto result = operation();
            return static_cast<std::uint64_t>(result.size());
          }};
}

}  // namespace

void add_ledger_benchmarks(std::vector<Benchmark>& benchmarks,
                           const Configuration& configuration) {
  auto ordered_events = std::make_shared<std::vector<EconomicEvent>>(
      make_events(configuration.events, false));
  auto unordered_events = std::make_shared<std::vector<EconomicEvent>>(
      make_events(configuration.events, true));

  benchmarks.push_back({
      "ledger_append", configuration.events, "events",
      [ordered_events] {
        const auto ledger = make_ledger(*ordered_events);
        if (ledger.size() != ordered_events->size()) throw std::runtime_error("append size mismatch");
        return ledger.size();
      },
      [ordered_events] {
        Ledger ledger;
        for (const auto& event : *ordered_events) (void)ledger.append(event);
        return static_cast<std::uint64_t>(ledger.size());
      }});

  auto ledger = std::make_shared<Ledger>(make_ledger(*unordered_events));
  auto existing_ids = std::make_shared<std::vector<EventId>>();
  auto missing_ids = std::make_shared<std::vector<EventId>>();
  const auto lookup_count = std::min<std::size_t>(configuration.events, 10'000);
  existing_ids->reserve(lookup_count);
  missing_ids->reserve(lookup_count);
  for (std::size_t i = 0; i < lookup_count; ++i) {
    existing_ids->emplace_back("event-" + std::to_string((i * 97) % configuration.events));
    missing_ids->emplace_back("missing-" + std::to_string(i));
  }
  benchmarks.push_back({
      "ledger_find_existing", lookup_count, "lookups", [ledger, existing_ids] {
        std::size_t found = 0;
        for (const auto& id : *existing_ids) found += ledger->find(id) != nullptr;
        if (found != existing_ids->size()) throw std::runtime_error("existing lookup mismatch");
        return found;
      }, [ledger, existing_ids] {
        std::uint64_t found = 0;
        for (const auto& id : *existing_ids) found += ledger->find(id) != nullptr;
        return found;
      }});
  benchmarks.push_back({
      "ledger_find_missing", lookup_count, "lookups", [ledger, missing_ids] {
        std::size_t found = 0;
        for (const auto& id : *missing_ids) found += ledger->find(id) != nullptr;
        if (found != 0) throw std::runtime_error("missing lookup mismatch");
        return found;
      }, [ledger, missing_ids] {
        std::uint64_t found = 0;
        for (const auto& id : *missing_ids) found += ledger->find(id) != nullptr;
        return found;
      }});

  auto mostly_ordered = std::make_shared<Ledger>(make_ledger(*ordered_events));
  benchmarks.push_back(view_benchmark("economic_order_mostly_ordered", mostly_ordered,
                                      [mostly_ordered] { return economic_entries(mostly_ordered->entries()); }));
  benchmarks.push_back(view_benchmark("economic_order_out_of_order", ledger,
                                      [ledger] { return economic_entries(ledger->entries()); }));
  const auto broad_from = base_time + std::chrono::seconds{static_cast<std::int64_t>(configuration.events / 10)};
  const auto broad_to = base_time + std::chrono::seconds{static_cast<std::int64_t>(configuration.events * 9 / 10)};
  const auto narrow_from = base_time + std::chrono::seconds{static_cast<std::int64_t>(configuration.events / 2)};
  const auto narrow_to = narrow_from + std::chrono::seconds{100};
  const auto narrow_as_of = base_time + std::chrono::seconds{100};
  benchmarks.push_back(view_benchmark("economic_through_broad", ledger,
      [ledger, broad_to] { return economic_entries_through(ledger->entries(), broad_to); }));
  benchmarks.push_back(view_benchmark("economic_through_narrow", ledger,
      [ledger, narrow_as_of] { return economic_entries_through(ledger->entries(), narrow_as_of); }));
  benchmarks.push_back(view_benchmark("economic_between_broad", ledger,
      [ledger, broad_from, broad_to] { return economic_entries_between(ledger->entries(), broad_from, broad_to); }));
  benchmarks.push_back(view_benchmark("economic_between_narrow", ledger,
      [ledger, narrow_from, narrow_to] { return economic_entries_between(ledger->entries(), narrow_from, narrow_to); }));
}

}  // namespace luca::bench
