#include "luca/ledger.hpp"

#include <cassert>
#include <chrono>
#include <type_traits>

using namespace luca;
using namespace std::chrono_literals;

namespace {
Provenance provenance(const char* source) {
  auto result = Provenance::create({SourceRecordId{source}}, "ledger.fixture", "1");
  assert(result);
  return *result;
}

EconomicEvent cash_event(const char* id, Timestamp time, const char* source,
                         const char* account = "account-a", const char* amount = "10") {
  auto event_header = EventHeader::create(EventId{id}, AccountId{account}, time,
                                          provenance(source));
  const auto currency = Currency::from_code("USD");
  assert(event_header && currency);
  const auto money = Money::parse(amount, *currency);
  assert(money);
  return CashMovement::create(*event_header, *money);
}

const EventHeader& entry_header(const LedgerEntry& entry) {
  return header(entry.event());
}
}  // namespace

int main() {
  static_assert(LedgerSequence::first_value == 1);
  static_assert(std::is_same_v<decltype(std::declval<const LedgerEntry&>().event()),
                               const EconomicEvent&>);
  static_assert(std::is_same_v<decltype(std::declval<const Ledger&>().entries()),
                               std::span<const LedgerEntry>>);

  constexpr Timestamp later{10h + 5s};
  constexpr Timestamp earlier{9h + 59min + 58s};
  Ledger ledger;
  assert(ledger.empty() && ledger.size() == 0);

  const auto event_a = cash_event("a", later, "source-a", "account-a", "25.125");
  const auto first = ledger.append(event_a);
  assert(first && first->get().sequence().value() == 1);
  const auto event_b = cash_event("b", earlier, "source-b");
  const auto second = ledger.append(event_b);
  assert(second && second->get().sequence().value() == 2);
  assert(ledger.size() == 2 && !ledger.empty());
  assert(entry_header(ledger.entries()[0]).id() == EventId{"a"});
  assert(entry_header(ledger.entries()[1]).id() == EventId{"b"});

  const auto duplicate = ledger.append(
      cash_event("a", earlier, "different-source", "different-account", "999"));
  assert(!duplicate && duplicate.error() == LedgerError::duplicate_event);
  assert(ledger.size() == 2);
  const auto* original = ledger.find(EventId{"a"});
  assert(original && original->event() == event_a);
  assert(entry_header(*original).account() == AccountId{"account-a"});
  assert(entry_header(*original).effective_at() == later);
  assert(entry_header(*original).provenance() == provenance("source-a"));
  assert(std::get<CashMovement>(original->event()).amount() ==
         *Money::parse("25.125", *Currency::from_code("USD")));
  assert(ledger.find(EventId{"missing"}) == nullptr);

  constexpr Timestamp tied{11h};
  assert(ledger.append(cash_event("c", tied, "source-c")));
  assert(ledger.append(cash_event("d", tied, "source-d")));
  assert(ledger.entries()[2].sequence().value() == 3);
  assert(ledger.entries()[3].sequence().value() == 4);

  const auto replay = ledger.economic_order();
  assert(entry_header(replay[0]).id() == EventId{"b"});
  assert(entry_header(replay[1]).id() == EventId{"a"});
  assert(entry_header(replay[2]).id() == EventId{"c"});
  assert(entry_header(replay[3]).id() == EventId{"d"});

  Ledger ranges;
  assert(ranges.append(cash_event("before", Timestamp{9s}, "s1")));
  assert(ranges.append(cash_event("from", Timestamp{10s}, "s2")));
  assert(ranges.append(cash_event("inside", Timestamp{19s}, "s3")));
  assert(ranges.append(cash_event("to", Timestamp{20s}, "s4")));
  const auto between = ranges.entries_between(Timestamp{10s}, Timestamp{20s});
  assert(between.size() == 2);
  assert(entry_header(between[0]).id() == EventId{"from"});
  assert(entry_header(between[1]).id() == EventId{"inside"});
  assert(ranges.entries_between(Timestamp{20s}, Timestamp{10s}).empty());

  Ledger same_history;
  for (const auto& entry : ledger.entries()) assert(same_history.append(entry.event()));
  for (std::size_t index = 0; index < ledger.size(); ++index)
    assert(same_history.entries()[index] == ledger.entries()[index]);
  const auto same_replay = same_history.economic_order();
  for (std::size_t index = 0; index < replay.size(); ++index)
    assert(same_replay[index].get() == replay[index].get());
}
