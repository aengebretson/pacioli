#include <luca/accounting/settlement_date_projection.hpp>
#include <luca/accounting/trade_date_projection.hpp>
#include <luca/portfolio/lifecycle_projection.hpp>
#include "fixture.hpp"

#include <iostream>
#include <string>

namespace {
// Display exact scaled integers without a binary floating-point conversion.
template <class Value> std::string decimal(Value value) {
  auto text = std::to_string(value.scaled_value());
  const std::size_t sign = text.front() == '-' ? 1 : 0;
  if (text.size() - sign <= Value::scale)
    text.insert(sign, Value::scale + 1 - (text.size() - sign), '0');
  text.insert(text.size() - Value::scale, 1, '.');
  return text;
}

template <class Result> void print(const Result &result) {
  std::cout << "  " << result.policy().id().value() << " version " << result.policy().version() << '\n';
  for (const auto &entry : result.entries()) {
    const auto date = entry.recognized_on().value();
    std::cout << "    " << entry.journal_entry_id().value() << " recognized "
              << static_cast<int>(date.year()) << '-' << static_cast<unsigned>(date.month())
              << '-' << static_cast<unsigned>(date.day()) << '\n';
    for (const auto &line : entry.lines())
      std::cout << "      " << (line.side() == luca::JournalSide::debit ? "debit " : "credit ")
                << line.account_id().value() << ' ' << decimal(line.amount()) << ' '
                << line.amount().currency().code() << '\n';
    std::cout << "      evidence:";
    for (const auto &source : entry.lineage().source_record_ids())
      std::cout << ' ' << source.value();
    if (entry.lineage().reverses_record_id())
      std::cout << "; reverses " << entry.lineage().reverses_record_id()->value();
    std::cout << '\n';
  }
}
} // namespace

int main() {
  using namespace luca;
  using namespace settlement_date_example;
  const auto ledger = history();
  for (const auto &e : evaluations()) {
    const auto resolved = ledger.resolve(e.recorded_through, e.economic_as_of);
    const auto td = project_trade_date_journals(
        resolved, {e.recorded_through, e.economic_as_of, e.settlement_as_of_date});
    const auto sd = project_settlement_date_journals(
        resolved, {e.recorded_through, e.economic_as_of, e.settlement_as_of_date});
    if (!td || !sd) {
      std::cerr << (td ? sd.error().message() : td.error().message()) << '\n';
      return 1;
    }
    std::cout << e.name << '\n';
    print(*td);
    print(*sd);
    const auto portfolio = project_lifecycle(resolved, {e.economic_as_of, e.settlement_as_of_date});
    if (!portfolio.positions || !portfolio.settled_cash || !portfolio.open_settlement_obligations)
      return 1;
    for (const auto &position : *portfolio.positions)
      std::cout << "  Portfolio quantity: " << decimal(position.quantity()) << '\n';
    for (const auto &cash : *portfolio.settled_cash)
      std::cout << "  Portfolio settled cash: " << decimal(cash.amount()) << " USD\n";
    for (const auto &obligation : *portfolio.open_settlement_obligations)
      std::cout << "  Open portfolio "
                << (obligation.key().direction() == SettlementDirection::payable ? "payable: " : "receivable: ")
                << decimal(obligation.amount()) << " USD\n";
    std::cout << "  Settlement-date policy defers equity recognition until the supplied settlement date; "
                 "it carries no unsettled journal control.\n\n";
  }
}
