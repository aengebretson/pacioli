#include "luca/event.hpp"

#include <cassert>
#include <chrono>
#include <type_traits>
#include <variant>

using namespace luca;
using namespace std::chrono;
using namespace std::chrono_literals;

namespace {

Provenance provenance(SourceRecordId source = SourceRecordId{"source-1"}) {
  auto value = Provenance::create({std::move(source)}, "fixture.normalization", "1");
  assert(value);
  return *value;
}

EventHeader event_header(const char* id, Timestamp effective_at) {
  auto value = EventHeader::create(EventId{id}, AccountId{"fund-a"}, effective_at,
                                   provenance());
  assert(value);
  return *value;
}

template <class T> T parsed(const char* text) {
  auto value = T::parse(text);
  assert(value);
  return *value;
}

}  // namespace

int main() {
  static_assert(std::is_same_v<Timestamp, sys_time<nanoseconds>>);
  static_assert(!std::is_constructible_v<EventHeader, EventId, AccountId, Timestamp,
                                         Provenance>);
  static_assert(!std::is_convertible_v<SourceRecordId, EventId>);
  static_assert(!std::is_convertible_v<InstrumentId, AccountId>);
  static_assert(std::variant_size_v<EconomicEvent> == 2);
  static_assert(std::is_same_v<decltype(std::declval<const EventHeader&>().id()),
                               const EventId&>);

  constexpr Timestamp effective_at{nanoseconds{1'767'600'000'123'456'789LL}};
  const auto common = event_header("event-1", effective_at);
  assert(common.id() == EventId{"event-1"});
  assert(common.account() == AccountId{"fund-a"});
  assert(common.effective_at() == effective_at);
  assert(common.provenance().source_records()[0] == SourceRecordId{"source-1"});
  const auto common_copy = common;
  assert(common_copy == common);
  assert(!EventHeader::create(EventId{""}, AccountId{"fund-a"}, effective_at,
                              provenance()));
  assert(!EventHeader::create(EventId{"event"}, AccountId{""}, effective_at,
                              provenance()));

  const auto usd = *Currency::from_code("USD");
  const auto deposit = CashMovement::create(
      event_header("deposit", effective_at), *Money::parse("1000000", usd));
  const auto withdrawal = CashMovement::create(
      event_header("withdrawal", effective_at), *Money::parse("-50000", usd));
  assert(deposit && withdrawal);
  assert(deposit->amount().scaled_value() == 1'000'000'000'000LL);
  assert(withdrawal->amount().scaled_value() == -50'000'000'000LL);
  assert(deposit->amount().currency() == usd);
  assert(deposit->header().provenance().source_records()[0] ==
         SourceRecordId{"source-1"});

  const auto settlement = SettlementDate::create(2026y / January / 8d);
  assert(settlement);
  assert(!SettlementDate::create(2026y / February / 30d));
  const auto buy = EquityTrade::create(
      event_header("buy", effective_at), InstrumentId{"AAPL"}, parsed<Quantity>("1000"),
      parsed<Price>("200.000000"), usd, *settlement);
  const auto sell = EquityTrade::create(
      event_header("sell", effective_at), InstrumentId{"AAPL"}, parsed<Quantity>("-400"),
      parsed<Price>("250.000000"), usd, *settlement);
  assert(buy && sell);
  assert(buy->quantity().scaled_value() == 100'000'000'000LL);
  assert(sell->quantity().scaled_value() == -40'000'000'000LL);
  assert(buy->instrument() == InstrumentId{"AAPL"});
  assert(buy->price() == parsed<Price>("200.000000"));
  assert(buy->quote_currency() == usd);
  assert(buy->settlement_date().value() == 2026y / January / 8d);
  assert(buy->header().effective_at() == effective_at);
  assert(!EquityTrade::create(event_header("zero", effective_at), InstrumentId{"AAPL"},
                              Quantity::from_scaled(0), parsed<Price>("200"), usd,
                              *settlement));
  assert(!EquityTrade::create(event_header("bad-instrument", effective_at),
                              InstrumentId{""}, parsed<Quantity>("1"),
                              parsed<Price>("0"), usd, *settlement));

  // Equal economic times are valid and deliberately do not imply replay order.
  const EconomicEvent first = *deposit;
  const EconomicEvent second = *buy;
  assert(header(first).effective_at() == header(second).effective_at());
  assert(header(first).id() != header(second).id());
  assert(std::holds_alternative<CashMovement>(first));
  assert(std::holds_alternative<EquityTrade>(second));
}
