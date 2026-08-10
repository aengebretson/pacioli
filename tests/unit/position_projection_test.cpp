#include "luca/portfolio.hpp"

#include <cassert>
#include <chrono>
#include <cstdint>
#include <limits>
#include <span>
#include <type_traits>

using namespace luca;
using namespace std::chrono_literals;

namespace {

Provenance provenance(const char* id) {
  auto result = Provenance::create({SourceRecordId{id}}, "position.fixture", "1");
  assert(result);
  return *result;
}

EventHeader make_header(const char* id, const char* account, Timestamp time) {
  auto result = EventHeader::create(EventId{id}, AccountId{account}, time, provenance(id));
  assert(result);
  return *result;
}

EconomicEvent trade(const char* id, const char* account, const char* instrument,
                    Quantity quantity, Timestamp time) {
  const auto usd = *Currency::from_code("USD");
  const auto settlement = *SettlementDate::create(
      std::chrono::year{2026} / std::chrono::January / std::chrono::day{8});
  auto result = EquityTrade::create(make_header(id, account, time),
                                    InstrumentId{instrument}, quantity,
                                    *Price::parse("1"), usd, settlement);
  assert(result);
  return *result;
}

EconomicEvent cash(const char* id, Timestamp time) {
  return CashMovement::create(make_header(id, "fund-a", time),
                              *Money::parse("100", *Currency::from_code("USD")));
}

Quantity quantity(const char* value) {
  auto result = Quantity::parse(value);
  assert(result);
  return *result;
}

const Position& only(const std::expected<std::vector<Position>, PositionProjectionError>& result) {
  assert(result && result->size() == 1);
  return result->front();
}

}  // namespace

int main() {
  static_assert(std::is_same_v<decltype(std::declval<const Position&>().quantity()), Quantity>);
  static_assert(std::is_same_v<decltype(std::declval<const Position&>().key()),
                               const PositionKey&>);
  constexpr Timestamp t1{std::chrono::nanoseconds{1'000'000'001}};
  constexpr Timestamp t2{std::chrono::nanoseconds{1'000'000'002}};
  constexpr Timestamp t3{std::chrono::nanoseconds{1'000'000'003}};

  Ledger empty;
  assert(project_positions(empty.entries(), t3)->empty());
  Ledger cash_only;
  assert(cash_only.append(cash("cash", t1)));
  assert(project_positions(cash_only.entries(), t3)->empty());

  Ledger buy;
  assert(buy.append(trade("buy", "fund-a", "AAPL", quantity("100"), t1)));
  assert(only(project_positions(buy.entries(), t3)).quantity() == quantity("100"));
  Ledger short_sale;
  assert(short_sale.append(trade("short", "fund-a", "AAPL", quantity("-40"), t1)));
  assert(only(project_positions(short_sale.entries(), t3)).quantity() == quantity("-40"));

  Ledger aggregate;
  assert(aggregate.append(trade("a1", "fund-b", "MSFT", quantity("20"), t2)));
  assert(aggregate.append(trade("a2", "fund-a", "AAPL", quantity("1000"), t1)));
  assert(aggregate.append(trade("a3", "fund-a", "AAPL", quantity("100"), t2)));
  assert(aggregate.append(trade("a4", "fund-a", "AAPL", quantity("-400"), t3)));
  assert(aggregate.append(trade("a5", "fund-a", "MSFT", quantity("5"), t1)));
  assert(aggregate.append(trade("a6", "fund-b", "AAPL", quantity("7"), t1)));
  const auto aggregated = project_positions(aggregate.entries(), t3);
  assert(aggregated && aggregated->size() == 4);
  const Position expected_aapl{PositionKey{AccountId{"fund-a"}, InstrumentId{"AAPL"}},
                               quantity("700")};
  assert((*aggregated)[0] == expected_aapl);
  const PositionKey fund_a_msft{AccountId{"fund-a"}, InstrumentId{"MSFT"}};
  const PositionKey fund_b_aapl{AccountId{"fund-b"}, InstrumentId{"AAPL"}};
  const PositionKey fund_b_msft{AccountId{"fund-b"}, InstrumentId{"MSFT"}};
  assert((*aggregated)[1].key() == fund_a_msft);
  assert((*aggregated)[2].key() == fund_b_aapl);
  assert((*aggregated)[3].key() == fund_b_msft);

  Ledger zero;
  assert(zero.append(trade("z1", "fund-a", "AAPL", quantity("100"), t1)));
  assert(zero.append(trade("z2", "fund-a", "AAPL", quantity("-100"), t2)));
  assert(project_positions(zero.entries(), t3)->empty());

  Ledger as_of;
  assert(as_of.append(trade("before", "fund-a", "AAPL", quantity("100"), t1)));
  assert(as_of.append(trade("exact", "fund-a", "AAPL", quantity("-25"), t2)));
  assert(as_of.append(trade("after", "fund-a", "AAPL", quantity("10"), t3)));
  assert(only(project_positions(as_of.entries(), t1)).quantity() == quantity("100"));
  assert(only(project_positions(as_of.entries(), t2)).quantity() == quantity("75"));
  assert(only(project_positions(as_of.entries(), t3)).quantity() == quantity("85"));

  // Sequence tie-breaking is observable here: max then +1 must overflow before
  // a later compensating -1 is processed. Acceptance order is the tie order.
  Ledger tied;
  assert(tied.append(trade("max", "fund-a", "AAPL",
                           Quantity::from_scaled(std::numeric_limits<std::int64_t>::max()), t2)));
  assert(tied.append(trade("overflow", "fund-a", "AAPL", Quantity::from_scaled(1), t2)));
  assert(tied.append(trade("compensate", "fund-a", "AAPL", Quantity::from_scaled(-1), t2)));
  const auto overflow = project_positions(tied.entries(), t3);
  assert(!overflow && overflow.error() == PositionProjectionError::quantity_overflow);

  // Out-of-order acceptance still uses economic replay; the early -1 prevents
  // overflow that acceptance-order replay would encounter.
  Ledger out_of_order;
  assert(out_of_order.append(trade("late-max", "fund-a", "AAPL",
                                   Quantity::from_scaled(std::numeric_limits<std::int64_t>::max()), t2)));
  assert(out_of_order.append(trade("early-minus", "fund-a", "AAPL", Quantity::from_scaled(-1), t1)));
  assert(out_of_order.append(trade("late-plus", "fund-a", "AAPL", Quantity::from_scaled(1), t2)));
  const auto reordered = project_positions(out_of_order.entries(), t3);
  assert(reordered && only(reordered).quantity() ==
                          Quantity::from_scaled(std::numeric_limits<std::int64_t>::max()));

  // Conformance semantics: deposits do not create positions; equity-buy and
  // lifecycle buys do so on trade date; sell history is reconstructed by events.
  Ledger sell_semantics;
  assert(sell_semantics.append(trade("opening-buy", "fund-a", "AAPL", quantity("1000"), t1)));
  assert(sell_semantics.append(trade("fixture-sell", "fund-a", "AAPL", quantity("-400"), t2)));
  assert(only(project_positions(sell_semantics.entries(), t2)).quantity() == quantity("600"));
  Ledger lifecycle;
  assert(lifecycle.append(trade("msft-buy", "fund-a", "MSFT", quantity("200"), t1)));
  assert(only(project_positions(lifecycle.entries(), t1)).quantity() == quantity("200"));
}
