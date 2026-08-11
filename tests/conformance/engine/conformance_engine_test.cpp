#include "luca/ledger.hpp"
#include "luca/portfolio.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

using namespace luca;

namespace {

struct PositionValue {
  std::string account, instrument, quantity;
  auto operator<=>(const PositionValue &) const = default;
};
struct CashValue {
  std::string account, currency, amount;
  auto operator<=>(const CashValue &) const = default;
};
struct SettlementValue {
  std::string account, currency, amount, direction, date;
  auto operator<=>(const SettlementValue &) const = default;
};
struct Input {
  std::vector<std::string> fields;
};
struct Phase {
  std::string name;
  std::int64_t as_of;
  int year, month, day;
  std::vector<PositionValue> positions;
  std::vector<CashValue> cash;
  std::vector<SettlementValue> settlements;
};
struct Scenario {
  std::string name;
  std::vector<PositionValue> initial_positions;
  std::vector<CashValue> initial_cash;
  std::vector<Input> inputs;
  std::vector<Phase> phases;
};
struct State {
  std::vector<PositionValue> positions;
  std::vector<CashValue> cash;
  std::vector<SettlementValue> settlements;
  auto operator<=>(const State &) const = default;
};

[[noreturn]] void fail(const std::string &message) {
  std::cerr << message << '\n';
  std::exit(1);
}
template <class T> T number(std::string_view value) {
  T result{};
  auto [end, error] =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (error != std::errc{} || end != value.data() + value.size())
    fail("invalid generated number: " + std::string(value));
  return result;
}
std::vector<std::string> split(const std::string &line) {
  std::vector<std::string> result;
  std::size_t start = 0;
  while (true) {
    const auto end = line.find('\t', start);
    result.push_back(line.substr(start, end - start));
    if (end == std::string::npos)
      return result;
    start = end + 1;
  }
}

std::vector<Scenario> load(const char *path) {
  std::ifstream stream(path);
  if (!stream)
    fail(std::string("cannot open generated fixture artifact: ") + path);
  std::string line;
  std::getline(stream, line);
  if (line != "LUCA_CONFORMANCE_V1")
    fail("invalid generated fixture artifact");
  std::vector<Scenario> scenarios;
  Scenario *scenario = nullptr;
  Phase *phase = nullptr;
  while (std::getline(stream, line)) {
    const auto f = split(line);
    const auto &tag = f[0];
    if (tag == "SCENARIO") {
      scenarios.push_back({.name = f[1]});
      scenario = &scenarios.back();
    } else if (tag == "INITIAL_POSITION")
      scenario->initial_positions.push_back({f[1], f[2], f[3]});
    else if (tag == "INITIAL_CASH")
      scenario->initial_cash.push_back({f[1], f[2], f[3]});
    else if (tag == "CASH" || tag == "TRADE")
      scenario->inputs.push_back({f});
    else if (tag == "PHASE") {
      scenario->phases.push_back({f[1], number<std::int64_t>(f[2]),
                                  number<int>(f[3]), number<int>(f[4]),
                                  number<int>(f[5])});
      phase = &scenario->phases.back();
    } else if (tag == "POSITION")
      phase->positions.push_back({f[1], f[2], f[3]});
    else if (tag == "BALANCE")
      phase->cash.push_back({f[1], f[2], f[3]});
    else if (tag == "SETTLEMENT")
      phase->settlements.push_back(
          {f[1], f[2], f[3], f[4], f[5] + "-" + f[6] + "-" + f[7]});
    else if (tag == "END_PHASE")
      phase = nullptr;
    else if (tag == "END_SCENARIO")
      scenario = nullptr;
    else
      fail("unknown generated fixture record: " + tag);
  }
  return scenarios;
}

template <class T>
T require(std::expected<T, ValueError> value, std::string_view context) {
  if (!value)
    fail("fixture translation failed: " + std::string(context));
  return *std::move(value);
}
Timestamp timestamp(std::string_view value) {
  return Timestamp{std::chrono::nanoseconds{number<std::int64_t>(value)}};
}
std::chrono::year_month_day date(int y, int m, int d) {
  return std::chrono::year{y} / std::chrono::month{static_cast<unsigned>(m)} /
         std::chrono::day{static_cast<unsigned>(d)};
}
std::string decimal(std::int64_t value, unsigned scale) {
  const bool negative = value < 0;
  std::uint64_t magnitude = negative
                                ? static_cast<std::uint64_t>(-(value + 1)) + 1
                                : static_cast<std::uint64_t>(value);
  std::uint64_t factor = 1;
  for (unsigned i = 0; i < scale; ++i)
    factor *= 10;
  std::ostringstream out;
  if (negative)
    out << '-';
  out << (magnitude / factor) << '.';
  out.width(scale);
  out.fill('0');
  out << (magnitude % factor);
  return out.str();
}

Provenance provenance(const std::string &source) {
  return require(
      Provenance::create({SourceRecordId{source}}, "conformance.fixture", "1"),
      "provenance");
}
EventHeader header(const Scenario &scenario, std::string id,
                   const std::string &account, Timestamp at) {
  return require(EventHeader::create(EventId{scenario.name + ":" + id},
                                     AccountId{account}, at,
                                     provenance(scenario.name + ":" + id)),
                 "event header");
}

Ledger translate(const Scenario &scenario) {
  Ledger ledger;
  const auto opening_at = timestamp(
      scenario.inputs.front()
          .fields[scenario.inputs.front().fields[0] == "CASH" ? 5 : 8]);
  for (std::size_t i = 0; i < scenario.initial_cash.size(); ++i) {
    const auto &v = scenario.initial_cash[i];
    auto currency =
        require(Currency::from_code(v.currency), "opening currency");
    EconomicEvent event = CashMovement::create(
        header(scenario, "opening-cash-" + std::to_string(i), v.account,
               opening_at),
        require(Money::parse(v.amount, currency), "opening cash"));
    if (!ledger.append(event))
      fail("ledger rejected opening event");
  }
  for (const auto &input : scenario.inputs) {
    const auto &f = input.fields;
    EconomicEvent event = [&]() -> EconomicEvent {
      if (f[0] == "CASH") {
        auto currency = require(Currency::from_code(f[3]), "cash currency");
        return CashMovement::create(
            header(scenario, "event-" + f[1], f[2], timestamp(f[5])),
            require(Money::parse(f[4], currency), "cash amount"));
      }
      auto quantity =
          require(Quantity::parse((f[3] == "sell" ? "-" : "") + f[5]),
                  "trade quantity");
      auto currency = require(Currency::from_code(f[6]), "trade currency");
      auto settlement = require(
          SettlementDate::create(
              date(number<int>(f[9]), number<int>(f[10]), number<int>(f[11]))),
          "settlement date");
      return require(EquityTrade::create(header(scenario, "event-" + f[1], f[2],
                                                timestamp(f[8])),
                                         InstrumentId{f[4]}, quantity,
                                         require(Price::parse(f[7]), "price"),
                                         currency, settlement),
                     "equity trade");
    }();
    if (!ledger.append(event))
      fail("ledger rejected fixture event");
  }
  return ledger;
}

State execute(const Scenario &scenario, const Phase &phase) {
  const auto ledger = translate(scenario);
  State state;
  const auto as_of = Timestamp{std::chrono::nanoseconds{phase.as_of}};
  const auto settlement_date = date(phase.year, phase.month, phase.day);
  auto positions = project_positions(ledger.entries(), as_of);
  if (!positions)
    fail("position projection failed");
  std::map<std::pair<std::string, std::string>, Quantity> position_totals;
  for (const auto &p : scenario.initial_positions)
    position_totals.emplace(
        std::pair{p.account, p.instrument},
        require(Quantity::parse(p.quantity), "initial position"));
  for (const auto &p : *positions) {
    const auto key =
        std::pair{p.key().account().value(), p.key().instrument().value()};
    const auto found = position_totals.find(key);
    if (found == position_totals.end())
      position_totals.emplace(key, p.quantity());
    else
      found->second = require(found->second.add(p.quantity()),
                              "position opening-state merge");
  }
  for (const auto &[key, quantity] : position_totals)
    if (quantity.scaled_value() != 0)
      state.positions.push_back(
          {key.first, key.second,
           decimal(quantity.scaled_value(), Quantity::scale)});
  auto cash = project_cash(ledger.entries(), {as_of, settlement_date});
  if (!cash)
    fail("cash projection failed");
  for (const auto &c : *cash)
    state.cash.push_back({c.key().account().value(),
                          std::string(c.key().currency().code()),
                          decimal(c.amount().scaled_value(), Money::scale)});
  auto settlements = project_settlement_obligations(ledger.entries(),
                                                    {as_of, settlement_date});
  if (!settlements)
    fail("settlement projection failed");
  for (const auto &s : *settlements) {
    const auto d = s.key().settlement_date().value();
    std::ostringstream ds;
    ds << int(d.year()) << '-';
    ds.width(2);
    ds.fill('0');
    ds << unsigned(d.month()) << '-';
    ds.width(2);
    ds << unsigned(d.day());
    state.settlements.push_back(
        {s.key().account().value(), std::string(s.key().currency().code()),
         decimal(s.amount().scaled_value(), Money::scale),
         s.key().direction() == SettlementDirection::payable ? "payable"
                                                             : "receivable",
         ds.str()});
  }
  return state;
}

template <class T> std::string show(const std::vector<T> &values) {
  std::ostringstream out;
  out << '[';
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i)
      out << ", ";
    if constexpr (std::is_same_v<T, PositionValue>)
      out << "{" << values[i].account << ',' << values[i].instrument << ','
          << values[i].quantity << '}';
    else if constexpr (std::is_same_v<T, CashValue>)
      out << "{" << values[i].account << ',' << values[i].currency << ','
          << values[i].amount << '}';
    else
      out << "{" << values[i].account << ',' << values[i].currency << ','
          << values[i].amount << ',' << values[i].direction << ','
          << values[i].date << '}';
  }
  return out.str() + ']';
}
template <class T>
void compare(const Scenario &s, const Phase &p, std::string_view projection,
             const std::vector<T> &expected, const std::vector<T> &actual) {
  if (expected != actual)
    fail("conformance failure\nscenario: " + s.name + "\nphase: " + p.name +
         "\nprojection: " + std::string(projection) +
         "\nexpected: " + show(expected) + "\nactual: " + show(actual));
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2)
    fail("usage: conformance_engine_test ARTIFACT");
  for (const auto &scenario : load(argv[1]))
    for (const auto &phase : scenario.phases) {
      const auto actual = execute(scenario, phase);
      const auto repeated = execute(scenario, phase);
      if (actual != repeated)
        fail("nondeterministic conformance execution: " + scenario.name + "/" +
             phase.name);
      compare(scenario, phase, "positions", phase.positions, actual.positions);
      compare(scenario, phase, "cash", phase.cash, actual.cash);
      compare(scenario, phase, "settlements", phase.settlements,
              actual.settlements);
    }
}
