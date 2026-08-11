#pragma once

#include "luca/ledger.hpp"
#include "luca/portfolio.hpp"
#include "luca/reconciliation.hpp"

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace luca::bench {

inline constexpr std::size_t account_count = 100;
inline constexpr std::size_t instrument_count = 1'000;
inline constexpr std::size_t currency_count = 3;
inline constexpr std::uint64_t synthetic_seed = 0x4c554341ULL;
inline constexpr Timestamp base_time = Timestamp{std::chrono::seconds{1'767'225'600}};
inline constexpr auto base_date = std::chrono::year{2026}/std::chrono::January/1;

inline Provenance provenance(std::size_t index = 0) {
  auto value = Provenance::create({SourceRecordId{"synthetic-" + std::to_string(index)}},
                                  "benchmark-generator", "1");
  if (!value) throw std::runtime_error("could not create benchmark provenance");
  return std::move(*value);
}

inline Currency currency(std::size_t index) {
  constexpr const char* codes[] = {"USD", "EUR", "GBP"};
  return *Currency::from_code(codes[index % currency_count]);
}

// A fixed pattern (seed is metadata for future-compatible generators): 10% cash,
// 90% trades, alternating trade signs, repeated keys, and seven settlement dates.
inline std::vector<EconomicEvent> make_events(std::size_t count,
                                               bool out_of_order = false,
                                               std::size_t settled_percent = 50) {
  std::vector<EconomicEvent> events;
  events.reserve(count);
  const auto common_provenance = provenance();
  for (std::size_t i = 0; i < count; ++i) {
    std::size_t time_slot = i;
    if (out_of_order && i % 16 < 8) time_slot = i + 7 - 2 * (i % 8);
    auto header_value = EventHeader::create(
        EventId{"event-" + std::to_string(i)},
        AccountId{"account-" + std::to_string(i % account_count)},
        base_time + std::chrono::seconds{static_cast<std::int64_t>(time_slot)},
        common_provenance);
    if (!header_value) throw std::runtime_error("could not create event header");
    if (i % 10 == 0) {
      const auto sign = (i / 10) % 2 == 0 ? 1 : -1;
      events.emplace_back(CashMovement::create(
          std::move(*header_value), Money::from_scaled(sign * (1'000'000 + i), currency(i))));
    } else {
      const auto sign = i % 2 == 0 ? std::int64_t{1} : std::int64_t{-1};
      const bool settled = (i % 100) < settled_percent;
      const auto date = std::chrono::year_month_day{
          std::chrono::sys_days{base_date} +
          std::chrono::days{settled ? -static_cast<int>(i % 3)
                                    : 1 + static_cast<int>(i % 7)}};
      auto trade = EquityTrade::create(
          std::move(*header_value),
          InstrumentId{"instrument-" + std::to_string(i % instrument_count)},
          Quantity::from_scaled(sign * static_cast<std::int64_t>(100'000'000 + i % 17)),
          Price::from_scaled(static_cast<std::int64_t>(10'000'000'000 + i % 101)),
          currency(i), SettlementDate::create(date).value());
      if (!trade) throw std::runtime_error("could not create equity trade");
      events.emplace_back(std::move(*trade));
    }
  }
  return events;
}

inline Ledger make_ledger(const std::vector<EconomicEvent>& events) {
  Ledger ledger;
  for (const auto& event : events)
    if (!ledger.append(event)) throw std::runtime_error("benchmark ledger append failed");
  return ledger;
}

inline Timestamp end_time(std::size_t count) {
  return base_time + std::chrono::seconds{static_cast<std::int64_t>(count + 32)};
}

}  // namespace luca::bench
