#include "luca/ledger.hpp"

#include <cassert>
#include <chrono>
#include <cstdint>
#include <expected>
#include <limits>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

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

Currency currency(std::string_view code) {
  const auto result = Currency::from_code(code);
  assert(result);
  return *result;
}

JournalDate journal_date(std::chrono::year_month_day value) {
  const auto result = JournalDate::create(value);
  assert(result);
  return *result;
}

AccountingPolicyIdentity journal_policy(const char *id = "fixture.trade-date.v1",
                                        const char *version = "1") {
  auto result = AccountingPolicyIdentity::create(AccountingPolicyId{id}, version);
  assert(result);
  return *result;
}

JournalLineage journal_lineage(std::vector<EventId> records,
                               std::vector<EconomicEventId> economic_events,
                               std::vector<SourceRecordId> sources,
                               std::optional<EventId> reverses_record = std::nullopt) {
  auto result = JournalLineage::create(std::move(records), std::move(economic_events),
                                       std::move(sources), std::move(reverses_record));
  assert(result);
  return *result;
}

JournalLineage journal_lineage(const char *record = "trade-record-v1",
                               const char *economic_event = "trade-economic-1",
                               const char *source = "trade-source-original") {
  return journal_lineage({EventId{record}}, {EconomicEventId{economic_event}},
                         {SourceRecordId{source}});
}

JournalSettlementContext immediate_context() {
  auto result = JournalSettlementContext::create(std::nullopt, std::nullopt, "immediate");
  assert(result);
  return *result;
}

JournalSettlementContext
equity_context(JournalDate trade_date, JournalDate settlement_date,
               const char *recognition_rule = "trade_date_then_settlement") {
  auto result = JournalSettlementContext::create(trade_date, settlement_date, recognition_rule);
  assert(result);
  return *result;
}

JournalLine journal_line(const char *line_id, const char *entry_id, const char *account_id,
                         JournalSide side, std::int64_t scaled_amount,
                         const JournalLineage &lineage, std::string_view currency_code = "USD") {
  auto result = JournalLine::create(
      JournalLineId{line_id}, JournalEntryId{entry_id}, AccountId{account_id}, side,
      Money::from_scaled(scaled_amount, currency(currency_code)), lineage);
  assert(result);
  return *result;
}

std::vector<JournalLine> balanced_lines(const char *entry_id, const char *debit_line_id,
                                        const char *credit_line_id, const char *debit_account,
                                        const char *credit_account, std::int64_t scaled_amount,
                                        const JournalLineage &lineage) {
  return {journal_line(debit_line_id, entry_id, debit_account, JournalSide::debit, scaled_amount,
                       lineage),
          journal_line(credit_line_id, entry_id, credit_account, JournalSide::credit, scaled_amount,
                       lineage)};
}

std::expected<JournalEntry, JournalError>
create_journal_entry(JournalEntryId entry_id, JournalEventType event_type, EventId active_record_id,
                     JournalDate recognized_on, RecognitionPhase recognition_phase,
                     JournalSettlementContext settlement_context, JournalLineage lineage,
                     std::vector<JournalLine> lines, std::uint32_t phase_ordinal = 0) {
  return JournalEntry::create(std::move(entry_id), journal_policy(), event_type,
                              std::move(active_record_id), Timestamp{10h}, Timestamp{11h},
                              recognized_on, recognition_phase, phase_ordinal,
                              std::move(settlement_context), std::move(lineage), std::move(lines));
}

template <class Value>
void expect_journal_error(const std::expected<Value, JournalError> &result,
                          JournalDiagnosticCategory category) {
  assert(!result);
  assert(result.error().category() == category);
  assert(result.error().category_name() == luca::category_name(category));
  assert(!result.error().message().empty());
}

void test_valid_journal_entries() {
  const auto may_29 = journal_date(2026y / std::chrono::May / 29d);
  const auto june_2 = journal_date(2026y / std::chrono::June / 2d);
  const auto june_4 = journal_date(2026y / std::chrono::June / 4d);
  const auto june_5 = journal_date(2026y / std::chrono::June / 5d);
  const auto june_6 = journal_date(2026y / std::chrono::June / 6d);

  const auto cash_lineage =
      journal_lineage("opening-cash-record", "opening-cash-economic", "opening-cash-source");
  const char *cash_id = "td.opening-cash.immediate";
  auto cash = create_journal_entry(
      JournalEntryId{cash_id}, JournalEventType::cash_movement, EventId{"opening-cash-record"},
      may_29, RecognitionPhase::immediate, immediate_context(), cash_lineage,
      balanced_lines(cash_id, "td.opening-cash.immediate.debit", "td.opening-cash.immediate.credit",
                     "asset.cash", "equity.contributed-capital", 100'000'000'000, cash_lineage));
  assert(cash);
  assert(cash->journal_entry_id() == JournalEntryId{cash_id});
  assert(cash->policy().id() == AccountingPolicyId{"fixture.trade-date.v1"});
  assert(cash->policy().version() == "1");
  assert(cash->event_type() == JournalEventType::cash_movement);
  assert(cash->active_record_id() == EventId{"opening-cash-record"});
  assert(cash->effective_at() == Timestamp{10h});
  assert(cash->recorded_at() == Timestamp{11h});
  assert(cash->recognized_on() == may_29);
  assert(cash->recognition_phase() == RecognitionPhase::immediate);
  assert(cash->phase_ordinal() == 0);
  assert(!cash->settlement_context().trade_date());
  assert(!cash->settlement_context().settlement_date());
  assert(cash->settlement_context().recognition_rule() == "immediate");
  assert(cash->currency() == currency("USD"));
  assert(cash->debit_total() == cash->credit_total());
  assert(cash->debit_total().scaled_value() == 100'000'000'000);
  assert(cash->lines().size() == 2);
  assert(cash->lines()[0].side() == JournalSide::debit);
  assert(cash->lines()[1].side() == JournalSide::credit);
  assert(cash->lines()[0].journal_entry_id() == cash->journal_entry_id());
  assert(cash->lines()[0].account_id() == AccountId{"asset.cash"});
  assert(cash->lines()[0].amount() == cash->debit_total());
  assert(cash->lines()[0].lineage() == cash->lineage());

  const auto purchase_lineage = journal_lineage();
  const auto purchase_context = equity_context(june_2, june_4);
  const char *purchase_id = "td.trade-v1.trade";
  auto purchase = create_journal_entry(
      JournalEntryId{purchase_id}, JournalEventType::equity_trade, EventId{"trade-record-v1"},
      june_2, RecognitionPhase::trade_date, purchase_context, purchase_lineage,
      balanced_lines(purchase_id, "td.trade-v1.trade.debit", "td.trade-v1.trade.credit",
                     "asset.equity-securities", "liability.trade-payable", 5'000'000'000,
                     purchase_lineage));
  assert(purchase);
  assert(purchase->settlement_context().trade_date() == june_2);
  assert(purchase->settlement_context().settlement_date() == june_4);

  const char *settlement_id = "td.trade-v1.settlement";
  auto settlement = create_journal_entry(
      JournalEntryId{settlement_id}, JournalEventType::equity_trade, EventId{"trade-record-v1"},
      june_4, RecognitionPhase::settlement_date, purchase_context, purchase_lineage,
      balanced_lines(settlement_id, "td.trade-v1.settlement.debit", "td.trade-v1.settlement.credit",
                     "liability.trade-payable", "asset.cash", 5'000'000'000, purchase_lineage),
      1);
  assert(settlement);
  assert(settlement->recognition_phase() == RecognitionPhase::settlement_date);
  assert(settlement->phase_ordinal() == 1);

  const auto correction_lineage = journal_lineage(
      {EventId{"trade-record-v1"}, EventId{"trade-record-v2"}},
      {EconomicEventId{"trade-economic-1"}},
      {SourceRecordId{"trade-source-original"}, SourceRecordId{"trade-source-correction"}});
  const char *correction_id = "td.trade-v2.trade";
  auto correction = create_journal_entry(
      JournalEntryId{correction_id}, JournalEventType::equity_trade, EventId{"trade-record-v2"},
      june_2, RecognitionPhase::trade_date, purchase_context, correction_lineage,
      balanced_lines(correction_id, "td.trade-v2.trade.debit", "td.trade-v2.trade.credit",
                     "asset.equity-securities", "liability.trade-payable", 4'400'000'000,
                     correction_lineage));
  assert(correction);
  assert(correction->lineage().record_ids().size() == 2);
  assert(correction->lineage().record_ids()[0] == EventId{"trade-record-v1"});
  assert(correction->lineage().record_ids()[1] == EventId{"trade-record-v2"});
  assert(correction->lineage().source_record_ids()[0] == SourceRecordId{"trade-source-original"});
  assert(correction->lineage().source_record_ids()[1] == SourceRecordId{"trade-source-correction"});
  assert(correction->lines()[0].journal_line_id() == JournalLineId{"td.trade-v2.trade.debit"});
  assert(correction->lines()[1].journal_line_id() == JournalLineId{"td.trade-v2.trade.credit"});

  const auto reversal_lineage = journal_lineage(
      {EventId{"reversal-record-v1"}}, {EconomicEventId{"trade-reversal-economic-1"}},
      {SourceRecordId{"trade-source-reversal"}}, EventId{"trade-record-v2"});
  const char *reversal_id = "td.reversal.trade";
  auto reversal = create_journal_entry(
      JournalEntryId{reversal_id}, JournalEventType::equity_trade, EventId{"reversal-record-v1"},
      june_5, RecognitionPhase::trade_date, equity_context(june_5, june_6), reversal_lineage,
      balanced_lines(reversal_id, "td.reversal.trade.debit", "td.reversal.trade.credit",
                     "asset.trade-receivable", "asset.equity-securities", 4'400'000'000,
                     reversal_lineage));
  assert(reversal);
  assert(reversal->lineage().reverses_record_id() == EventId{"trade-record-v2"});
  assert(reversal->lines()[0].lineage().reverses_record_id() == EventId{"trade-record-v2"});
}

void test_journal_factory_rejections_and_boundaries() {
  const auto june_2 = journal_date(2026y / std::chrono::June / 2d);
  const auto june_4 = journal_date(2026y / std::chrono::June / 4d);
  const auto lineage = journal_lineage();
  const auto context = equity_context(june_2, june_4);
  const char *entry_id = "entry";

  expect_journal_error(AccountingPolicyIdentity::create(AccountingPolicyId{""}, "1"),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(AccountingPolicyIdentity::create(AccountingPolicyId{"policy"}, ""),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalDate::create(2026y / std::chrono::February / 30d),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalSettlementContext::create(std::nullopt, std::nullopt, ""),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalSettlementContext::create(june_2, std::nullopt, "rule"),
                       JournalDiagnosticCategory::policy_context_mismatch);

  expect_journal_error(
      JournalLineage::create({}, {EconomicEventId{"economic"}}, {SourceRecordId{"source"}}),
      JournalDiagnosticCategory::lineage_missing);
  expect_journal_error(JournalLineage::create({EventId{"record"}}, {}, {SourceRecordId{"source"}}),
                       JournalDiagnosticCategory::lineage_missing);
  expect_journal_error(
      JournalLineage::create({EventId{"record"}}, {EconomicEventId{"economic"}}, {}),
      JournalDiagnosticCategory::lineage_missing);
  expect_journal_error(JournalLineage::create({EventId{""}}, {EconomicEventId{"economic"}},
                                              {SourceRecordId{"source"}}),
                       JournalDiagnosticCategory::schema_shape);

  const auto ten = Money::from_scaled(10, currency("USD"));
  expect_journal_error(JournalLine::create(JournalLineId{""}, JournalEntryId{entry_id},
                                           AccountId{"account"}, JournalSide::debit, ten, lineage),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalLine::create(JournalLineId{"line"}, JournalEntryId{""},
                                           AccountId{"account"}, JournalSide::debit, ten, lineage),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalLine::create(JournalLineId{"line"}, JournalEntryId{entry_id},
                                           AccountId{""}, JournalSide::debit, ten, lineage),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(JournalLine::create(JournalLineId{"line"}, JournalEntryId{entry_id},
                                           AccountId{"account"}, JournalSide::debit,
                                           Money::from_scaled(0, currency("USD")), lineage),
                       JournalDiagnosticCategory::invalid_line_amount);
  expect_journal_error(JournalLine::create(JournalLineId{"line"}, JournalEntryId{entry_id},
                                           AccountId{"account"}, JournalSide::credit,
                                           Money::from_scaled(-1, currency("USD")), lineage),
                       JournalDiagnosticCategory::invalid_line_amount);

  auto valid_lines =
      balanced_lines(entry_id, "debit", "credit", "asset.cash", "equity.capital", 10, lineage);
  expect_journal_error(create_journal_entry(JournalEntryId{""}, JournalEventType::equity_trade,
                                            EventId{"trade-record-v1"}, june_2,
                                            RecognitionPhase::trade_date, context, lineage,
                                            valid_lines),
                       JournalDiagnosticCategory::schema_shape);
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade, EventId{""},
                           june_2, RecognitionPhase::trade_date, context, lineage, valid_lines),
      JournalDiagnosticCategory::schema_shape);
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, {valid_lines.front()}),
      JournalDiagnosticCategory::schema_shape);

  auto duplicate_lines = std::vector<JournalLine>{
      journal_line("duplicate", entry_id, "asset.cash", JournalSide::debit, 10, lineage),
      journal_line("duplicate", entry_id, "equity.capital", JournalSide::credit, 10, lineage)};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, duplicate_lines),
      JournalDiagnosticCategory::duplicate_identity);

  auto wrong_parent = std::vector<JournalLine>{
      journal_line("debit", "different-entry", "asset.cash", JournalSide::debit, 10, lineage),
      journal_line("credit", entry_id, "equity.capital", JournalSide::credit, 10, lineage)};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, wrong_parent),
      JournalDiagnosticCategory::lineage_mismatch);

  const auto other_lineage =
      journal_lineage("trade-record-v1", "trade-economic-1", "different-source");
  auto wrong_lineage = std::vector<JournalLine>{
      journal_line("debit", entry_id, "asset.cash", JournalSide::debit, 10, other_lineage),
      journal_line("credit", entry_id, "equity.capital", JournalSide::credit, 10, lineage)};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, wrong_lineage),
      JournalDiagnosticCategory::lineage_mismatch);

  const auto unrelated_lineage = journal_lineage("other-record", "economic", "source");
  auto unrelated_lines = balanced_lines(entry_id, "debit", "credit", "asset.cash", "equity.capital",
                                        10, unrelated_lineage);
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, unrelated_lineage, unrelated_lines),
      JournalDiagnosticCategory::lineage_mismatch);

  auto mixed_currency = std::vector<JournalLine>{
      journal_line("debit", entry_id, "asset.cash", JournalSide::debit, 10, lineage, "USD"),
      journal_line("credit", entry_id, "equity.capital", JournalSide::credit, 10, lineage, "EUR")};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, mixed_currency),
      JournalDiagnosticCategory::mixed_currency_entry);

  auto unbalanced = std::vector<JournalLine>{
      journal_line("debit", entry_id, "asset.cash", JournalSide::debit, 10, lineage),
      journal_line("credit", entry_id, "equity.capital", JournalSide::credit, 9, lineage)};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, unbalanced),
      JournalDiagnosticCategory::unbalanced_entry);

  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           immediate_context(), lineage, valid_lines),
      JournalDiagnosticCategory::policy_context_mismatch);
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::cash_movement,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::immediate, context,
                           lineage, valid_lines),
      JournalDiagnosticCategory::policy_context_mismatch);
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_4, RecognitionPhase::trade_date,
                           context, lineage, valid_lines),
      JournalDiagnosticCategory::policy_context_mismatch);

  const auto maximum = std::numeric_limits<std::int64_t>::max();
  auto boundary_lines = std::vector<JournalLine>{
      journal_line("maximum-debit", entry_id, "asset.cash", JournalSide::debit, maximum, lineage),
      journal_line("almost-maximum-credit", entry_id, "equity.capital", JournalSide::credit,
                   maximum - 1, lineage),
      journal_line("one-credit", entry_id, "equity.capital", JournalSide::credit, 1, lineage)};
  auto boundary = create_journal_entry(
      JournalEntryId{entry_id}, JournalEventType::equity_trade, EventId{"trade-record-v1"}, june_2,
      RecognitionPhase::trade_date, context, lineage, boundary_lines);
  assert(boundary);
  assert(boundary->debit_total().scaled_value() == maximum);
  assert(boundary->credit_total().scaled_value() == maximum);

  auto overflowing_lines = std::vector<JournalLine>{
      journal_line("maximum-debit", entry_id, "asset.cash", JournalSide::debit, maximum, lineage),
      journal_line("one-debit", entry_id, "asset.cash", JournalSide::debit, 1, lineage),
      journal_line("maximum-credit", entry_id, "equity.capital", JournalSide::credit, maximum,
                   lineage),
      journal_line("one-credit", entry_id, "equity.capital", JournalSide::credit, 1, lineage)};
  expect_journal_error(
      create_journal_entry(JournalEntryId{entry_id}, JournalEventType::equity_trade,
                           EventId{"trade-record-v1"}, june_2, RecognitionPhase::trade_date,
                           context, lineage, overflowing_lines),
      JournalDiagnosticCategory::arithmetic_overflow);
}
}  // namespace

int main() {
  static_assert(LedgerSequence::first_value == 1);
  static_assert(std::is_same_v<decltype(std::declval<const LedgerEntry&>().event()),
                               const EconomicEvent&>);
  static_assert(std::is_same_v<decltype(std::declval<const Ledger&>().entries()),
                               std::span<const LedgerEntry>>);
  static_assert(std::is_same_v<decltype(std::declval<const JournalEntry &>().lines()),
                               std::span<const JournalLine>>);
  static_assert(std::is_same_v<decltype(std::declval<const JournalEntry &>().policy()),
                               const AccountingPolicyIdentity &>);

  test_valid_journal_entries();
  test_journal_factory_rejections_and_boundaries();

  constexpr Timestamp later{10h + 5s};
  constexpr Timestamp earlier{9h + 59min + 58s};
  Ledger ledger;
  assert(ledger.empty() && ledger.size() == 0);
  assert(economic_entries(ledger.entries()).empty());
  assert(economic_entries_through(ledger.entries(), Timestamp{10s}).empty());
  assert(economic_entries_between(ledger.entries(), Timestamp{0s}, Timestamp{10s}).empty());

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

  // The reusable span helper has identical deterministic ordering and inclusive
  // as-of semantics: earlier and exact events are selected, later events are not.
  const auto through_later = economic_entries_through(ledger.entries(), later);
  assert(through_later.size() == 2);
  assert(entry_header(through_later[0]).id() == EventId{"b"});
  assert(entry_header(through_later[1]).id() == EventId{"a"});
  const auto before_later = economic_entries_through(ledger.entries(), earlier);
  assert(before_later.size() == 1);
  assert(entry_header(before_later[0]).id() == EventId{"b"});

  const auto reusable_replay = economic_entries(ledger.entries());
  assert(reusable_replay.size() == replay.size());
  for (std::size_t index = 0; index < replay.size(); ++index)
    assert(reusable_replay[index].get() == replay[index].get());

  Ledger ranges;
  assert(ranges.append(cash_event("after", Timestamp{21s}, "s1")));
  assert(ranges.append(cash_event("tied-first", Timestamp{15s}, "s2")));
  assert(ranges.append(cash_event("before", Timestamp{9s}, "s3")));
  assert(ranges.append(cash_event("inside-late", Timestamp{19s}, "s4")));
  assert(ranges.append(cash_event("from", Timestamp{10s}, "s5")));
  assert(ranges.append(cash_event("tied-second", Timestamp{15s}, "s6")));
  assert(ranges.append(cash_event("to", Timestamp{20s}, "s7")));

  // A narrow range filters the acceptance-order ledger before sorting only its
  // matching subset. The subset still uses economic time, then sequence.
  const auto between = ranges.entries_between(Timestamp{10s}, Timestamp{20s});
  assert(between.size() == 4);
  assert(entry_header(between[0]).id() == EventId{"from"});
  assert(entry_header(between[1]).id() == EventId{"tied-first"});
  assert(entry_header(between[2]).id() == EventId{"tied-second"});
  assert(entry_header(between[3]).id() == EventId{"inside-late"});
  assert(ranges.entries_between(Timestamp{10s}, Timestamp{10s}).empty());
  assert(ranges.entries_between(Timestamp{20s}, Timestamp{10s}).empty());

  const auto range_replay = ranges.economic_order();
  assert(entry_header(range_replay[0]).id() == EventId{"before"});
  assert(entry_header(range_replay[1]).id() == EventId{"from"});
  assert(entry_header(range_replay[2]).id() == EventId{"tied-first"});
  assert(entry_header(range_replay[3]).id() == EventId{"tied-second"});
  assert(entry_header(range_replay[4]).id() == EventId{"inside-late"});
  assert(entry_header(range_replay[5]).id() == EventId{"to"});
  assert(entry_header(range_replay[6]).id() == EventId{"after"});

  Ledger same_history;
  for (const auto& entry : ledger.entries()) assert(same_history.append(entry.event()));
  for (std::size_t index = 0; index < ledger.size(); ++index)
    assert(same_history.entries()[index] == ledger.entries()[index]);
  const auto same_replay = same_history.economic_order();
  for (std::size_t index = 0; index < replay.size(); ++index)
    assert(same_replay[index].get() == replay[index].get());
}
