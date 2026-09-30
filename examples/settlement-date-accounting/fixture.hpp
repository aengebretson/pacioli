#pragma once

#include <luca/lifecycle.hpp>

#include <array>
#include <chrono>
#include <cstdlib>
#include <utility>

// Synthetic inputs from accounting-foundations/valid-cash-equity-lifecycle.json.
// This file is example/test setup, not financial-domain implementation.
namespace settlement_date_example {
using namespace luca;
using namespace std::chrono;
using namespace std::chrono_literals;

inline Timestamp at(year_month_day date, nanoseconds time = 0ns) {
  return Timestamp{sys_days{date}.time_since_epoch() + time};
}

template <class T, class E> T require(std::expected<T, E> result) {
  if (!result)
    std::abort();
  return std::move(*result);
}

inline EconomicEvent cash(const char *id, Timestamp effective, const char *source,
                          const char *amount = "100000", const char *currency = "USD") {
  auto provenance = require(Provenance::create({SourceRecordId{source}},
                                               "fixture.cash-normalization", "1"));
  auto header = require(EventHeader::create(EventId{id}, AccountId{"fund-a"}, effective,
                                            std::move(provenance)));
  return CashMovement::create(std::move(header),
      require(Money::parse(amount, require(Currency::from_code(currency)))));
}

inline EconomicEvent trade(const char *id, Timestamp effective, const char *source,
                           const char *quantity, const char *price, year_month_day settlement,
                           const char *currency = "USD") {
  auto provenance = require(Provenance::create({SourceRecordId{source}},
                                               "fixture.trade-normalization", "1"));
  auto header = require(EventHeader::create(EventId{id}, AccountId{"fund-a"}, effective,
                                            std::move(provenance)));
  return require(EquityTrade::create(std::move(header), InstrumentId{"MSFT"},
      require(Quantity::parse(quantity)), require(Price::parse(price)),
      require(Currency::from_code(currency)), require(SettlementDate::create(settlement))));
}

inline auto drafts() {
  return std::array{
      LifecycleRecordDraft::originate(EconomicEventId{"opening-cash-economic"},
          at(2026y / May / 29d, 9h + 1min),
          cash("opening-cash-record", at(2026y / May / 29d), "opening-cash-source")),
      LifecycleRecordDraft::originate(EconomicEventId{"trade-economic-1"},
          at(2026y / June / 2d, 14h + 2min),
          trade("trade-record-v1", at(2026y / June / 2d, 14h), "trade-source-original",
                "100", "50", 2026y / June / 4d)),
      LifecycleRecordDraft::correct(EconomicEventId{"trade-economic-1"}, EventId{"trade-record-v1"},
          at(2026y / June / 3d, 9h + 1min),
          trade("trade-record-v2", at(2026y / June / 2d, 14h), "trade-source-correction",
                "80", "55", 2026y / June / 4d)),
      LifecycleRecordDraft::reverse(EconomicEventId{"trade-reversal-economic-1"},
          EventId{"trade-record-v2"}, at(2026y / June / 7d, 9h + 1min),
          trade("reversal-record-v1", at(2026y / June / 5d, 10h), "trade-source-reversal",
                "-80", "55", 2026y / June / 6d))};
}

inline LifecycleLedger history() {
  LifecycleLedger ledger;
  require(ledger.accept_batch(drafts()));
  return ledger;
}

struct Evaluation {
  const char *name;
  Timestamp recorded_through;
  Timestamp economic_as_of;
  year_month_day settlement_as_of_date;
};

inline auto evaluations() {
  constexpr auto end = 23h + 59min + 59s;
  return std::array{
      Evaluation{"original-trade-before-correction", at(2026y / June / 2d, end),
                 at(2026y / June / 2d, end), 2026y / June / 2d},
      Evaluation{"corrected-trade-before-settlement", at(2026y / June / 3d, end),
                 at(2026y / June / 2d, end), 2026y / June / 2d},
      Evaluation{"corrected-trade-after-settlement", at(2026y / June / 6d, end),
                 at(2026y / June / 4d, end), 2026y / June / 4d},
      Evaluation{"reversal-known-before-reversal-settlement", at(2026y / June / 7d, 12h),
                 at(2026y / June / 5d, end), 2026y / June / 5d},
      Evaluation{"reversal-after-settlement", at(2026y / June / 7d, 12h),
                 at(2026y / June / 6d, end), 2026y / June / 6d}};
}
} // namespace settlement_date_example
