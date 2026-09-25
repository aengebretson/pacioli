#include "luca/ledger.hpp"
#include "luca/portfolio/lifecycle_projection.hpp"

#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <expected>
#include <limits>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

using namespace luca;
using namespace std::chrono_literals;

namespace {
Provenance provenance(const char *source) {
  auto result = Provenance::create({SourceRecordId{source}}, "ledger.fixture", "1");
  assert(result);
  return *result;
}

EconomicEvent cash_event(const char *id, Timestamp time, const char *source,
                         const char *account = "account-a", const char *amount = "10",
                         const char *currency_code = "USD") {
  auto event_header =
      EventHeader::create(EventId{id}, AccountId{account}, time, provenance(source));
  const auto denomination = Currency::from_code(currency_code);
  assert(event_header && denomination);
  const auto money = Money::parse(amount, *denomination);
  assert(money);
  return CashMovement::create(*event_header, *money);
}

EconomicEvent trade_event(const char *id, Timestamp time, const char *source, const char *quantity,
                          const char *price, std::chrono::year_month_day settlement,
                          const char *account = "fund-a", const char *currency_code = "USD") {
  auto event_header =
      EventHeader::create(EventId{id}, AccountId{account}, time, provenance(source));
  const auto denomination = Currency::from_code(currency_code);
  const auto parsed_quantity = Quantity::parse(quantity);
  const auto parsed_price = Price::parse(price);
  const auto parsed_settlement = SettlementDate::create(settlement);
  assert(event_header && denomination && parsed_quantity && parsed_price && parsed_settlement);
  auto trade = EquityTrade::create(*event_header, InstrumentId{"MSFT"}, *parsed_quantity,
                                   *parsed_price, *denomination, *parsed_settlement);
  assert(trade);
  return *trade;
}

Timestamp timestamp(std::chrono::year_month_day date,
                    std::chrono::nanoseconds time_of_day = std::chrono::nanoseconds{0}) {
  return Timestamp{std::chrono::sys_days{date}.time_since_epoch() + time_of_day};
}

const EventHeader &entry_header(const LedgerEntry &entry) { return header(entry.event()); }

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

void accept(LifecycleLedger &ledger, LifecycleRecordDraft draft) {
  const auto result = ledger.accept(draft);
  assert(result);
}

std::int64_t journal_control(const TradeDateProjectionResult &result, std::string_view account,
                             JournalSide natural_side) {
  std::int64_t balance = 0;
  for (const auto &entry : result.entries()) {
    assert(entry.debit_total() == entry.credit_total());
    for (const auto &line : entry.lines()) {
      if (line.account_id().value() != account)
        continue;
      if (line.side() == natural_side)
        balance += line.amount().scaled_value();
      else
        balance -= line.amount().scaled_value();
    }
  }
  return balance;
}

void expect_portfolio_controls(const TradeDateProjectionResult &journals,
                               const LifecycleResolution &resolution, Timestamp economic_as_of,
                               std::chrono::year_month_day settlement_as_of,
                               std::int64_t expected_quantity, std::int64_t expected_cash,
                               std::int64_t expected_payable, std::int64_t expected_receivable) {
  const auto portfolio =
      project_lifecycle(resolution, LifecycleProjectionContext{economic_as_of, settlement_as_of});
  assert(portfolio.positions && portfolio.settled_cash && portfolio.open_settlement_obligations);
  if (expected_quantity == 0) {
    assert(portfolio.positions->empty());
  } else {
    assert(portfolio.positions->size() == 1);
    assert(portfolio.positions->front().quantity().scaled_value() == expected_quantity);
  }
  assert(portfolio.settled_cash->size() == 1);
  assert(portfolio.settled_cash->front().amount().scaled_value() == expected_cash);
  assert(journal_control(journals, "asset.cash", JournalSide::debit) == expected_cash);
  assert(journal_control(journals, "liability.trade-payable", JournalSide::credit) ==
         expected_payable);
  assert(journal_control(journals, "asset.trade-receivable", JournalSide::debit) ==
         expected_receivable);

  const auto expected_obligations =
      static_cast<std::size_t>((expected_payable != 0) + (expected_receivable != 0));
  assert(portfolio.open_settlement_obligations->size() == expected_obligations);
  if (expected_payable != 0) {
    assert(portfolio.open_settlement_obligations->front().key().direction() ==
           SettlementDirection::payable);
    assert(portfolio.open_settlement_obligations->front().amount().scaled_value() ==
           expected_payable);
  }
  if (expected_receivable != 0) {
    assert(portfolio.open_settlement_obligations->front().key().direction() ==
           SettlementDirection::receivable);
    assert(portfolio.open_settlement_obligations->front().amount().scaled_value() ==
           expected_receivable);
  }
}

void expect_projection_error(
    const std::expected<TradeDateProjectionResult, TradeDateProjectionError> &result,
    TradeDateProjectionDiagnosticCategory category, std::string_view record_id = {}) {
  assert(!result);
  assert(result.error().category() == category);
  assert(result.error().category_name() == luca::category_name(category));
  assert(!result.error().message().empty());
  if (!record_id.empty()) {
    assert(result.error().record_id());
    assert(result.error().record_id()->value() == record_id);
  }
}

void expect_projected_entry_identity(const JournalEntry &entry, std::string_view entry_id) {
  assert(entry.journal_entry_id().value() == entry_id);
  assert(entry.lines().size() == 2);
  assert(entry.lines()[0].journal_line_id().value() == std::string{entry_id} + ".debit");
  assert(entry.lines()[1].journal_line_id().value() == std::string{entry_id} + ".credit");
}

void test_trade_date_projection_walkthrough() {
  using namespace std::chrono;
  const auto may_29 = 2026y / May / 29d;
  const auto june_2 = 2026y / June / 2d;
  const auto june_3 = 2026y / June / 3d;
  const auto june_4 = 2026y / June / 4d;
  const auto june_5 = 2026y / June / 5d;
  const auto june_6 = 2026y / June / 6d;
  const auto june_7 = 2026y / June / 7d;
  const auto end_of_day = 23h + 59min + 59s;

  const auto opening_effective = timestamp(may_29, 9h);
  const auto opening_recorded = timestamp(may_29, 9h + 1min);
  const auto trade_effective = timestamp(june_2, 14h);
  const auto trade_recorded = timestamp(june_2, 14h + 1min);
  const auto correction_recorded = timestamp(june_3, 9h);
  const auto reversal_effective = timestamp(june_5, 10h);
  const auto reversal_recorded = timestamp(june_7, 9h);

  LifecycleLedger ledger;
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"opening-cash-economic"}, opening_recorded,
                                         cash_event("opening-cash-record", opening_effective,
                                                    "opening-cash-source", "fund-a", "100000")));
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"trade-economic-1"}, trade_recorded,
                     trade_event("trade-record-v1", trade_effective, "trade-source-original", "100",
                                 "50", june_4)));
  accept(ledger,
         LifecycleRecordDraft::correct(EconomicEventId{"trade-economic-1"},
                                       EventId{"trade-record-v1"}, correction_recorded,
                                       trade_event("trade-record-v2", trade_effective,
                                                   "trade-source-correction", "80", "55", june_4)));
  accept(ledger,
         LifecycleRecordDraft::reverse(EconomicEventId{"trade-reversal-economic-1"},
                                       EventId{"trade-record-v2"}, reversal_recorded,
                                       trade_event("reversal-record-v1", reversal_effective,
                                                   "trade-source-reversal", "-80", "55", june_6)));

  const auto original_economic = timestamp(june_2, end_of_day);
  const auto original = ledger.resolve(timestamp(june_2, end_of_day), original_economic);
  const auto original_journals = project_trade_date_journals(
      original, {timestamp(june_2, end_of_day), original_economic, june_2});
  assert(original_journals);
  assert(original_journals->engine_version() == "fixture-accounting-engine-1");
  assert(original_journals->projection_version() == "fixture-journal-projection-1");
  assert(original_journals->lifecycle_contract_version() == "luca.event-lifecycle.v1");
  assert(original_journals->policy().id() == AccountingPolicyId{"fixture.trade-date.v1"});
  assert(original_journals->policy().version() == "1");
  assert(original_journals->entries().size() == 2);
  expect_projected_entry_identity(original_journals->entries()[0], "td.opening-cash.immediate");
  expect_projected_entry_identity(original_journals->entries()[1], "td.trade-v1.trade");
  assert(original_journals->entries()[1].debit_total().scaled_value() == 5'000'000'000);
  assert(original_journals->active_record_ids().size() == 2);
  assert(original_journals->lifecycle_record_ids().size() == 2);
  assert(original_journals->economic_event_ids().size() == 2);
  assert(original_journals->source_record_ids().size() == 2);
  const auto original_repeat = project_trade_date_journals(
      original, {timestamp(june_2, end_of_day), original_economic, june_2});
  assert(original_repeat && *original_repeat == *original_journals);
  expect_portfolio_controls(*original_journals, original, original_economic, june_2,
                            100 * 100'000'000LL, 100'000'000'000LL, 5'000'000'000LL, 0);

  const auto corrected_economic = timestamp(june_2, end_of_day);
  const auto corrected = ledger.resolve(timestamp(june_3, end_of_day), corrected_economic);
  const auto corrected_journals = project_trade_date_journals(
      corrected, {timestamp(june_3, end_of_day), corrected_economic, june_2});
  assert(corrected_journals && corrected_journals->entries().size() == 2);
  const auto &corrected_trade = corrected_journals->entries()[1];
  expect_projected_entry_identity(corrected_trade, "td.trade-v2.trade");
  assert(corrected_trade.active_record_id() == EventId{"trade-record-v2"});
  assert(corrected_trade.debit_total().scaled_value() == 4'400'000'000LL);
  assert(corrected_trade.lineage().record_ids().size() == 2);
  assert(corrected_trade.lineage().record_ids()[0] == EventId{"trade-record-v1"});
  assert(corrected_trade.lineage().record_ids()[1] == EventId{"trade-record-v2"});
  assert(corrected_trade.lineage().source_record_ids().size() == 2);
  assert(corrected_journals->active_record_ids().size() == 2);
  assert(corrected_journals->lifecycle_record_ids().size() == 3);
  assert(corrected_journals->source_record_ids().size() == 3);
  expect_portfolio_controls(*corrected_journals, corrected, corrected_economic, june_2,
                            80 * 100'000'000LL, 100'000'000'000LL, 4'400'000'000LL, 0);

  const auto settled_economic = timestamp(june_4, end_of_day);
  const auto settled = ledger.resolve(timestamp(june_3, end_of_day), settled_economic);
  const auto settled_journals = project_trade_date_journals(
      settled, {timestamp(june_3, end_of_day), settled_economic, june_4});
  assert(settled_journals && settled_journals->entries().size() == 3);
  expect_projected_entry_identity(settled_journals->entries()[2], "td.trade-v2.settlement");
  assert(settled_journals->entries()[2].phase_ordinal() == 1);
  assert(settled_journals->entries()[2].lines()[0].account_id() ==
         AccountId{"liability.trade-payable"});
  assert(settled_journals->entries()[2].lines()[1].account_id() == AccountId{"asset.cash"});
  expect_portfolio_controls(*settled_journals, settled, settled_economic, june_4,
                            80 * 100'000'000LL, 95'600'000'000LL, 0, 0);

  const auto reversal_economic = timestamp(june_5, end_of_day);
  const auto reversed = ledger.resolve(timestamp(june_7, 12h), reversal_economic);
  const auto reversal_journals =
      project_trade_date_journals(reversed, {timestamp(june_7, 12h), reversal_economic, june_5});
  assert(reversal_journals && reversal_journals->entries().size() == 4);
  expect_projected_entry_identity(reversal_journals->entries()[3], "td.reversal.trade");
  assert(reversal_journals->entries()[3].lines()[0].account_id() ==
         AccountId{"asset.trade-receivable"});
  assert(reversal_journals->entries()[3].lines()[1].account_id() ==
         AccountId{"asset.equity-securities"});
  assert(reversal_journals->entries()[3].lineage().reverses_record_id() ==
         EventId{"trade-record-v2"});
  assert(reversal_journals->source_record_ids().size() == 4);
  expect_portfolio_controls(*reversal_journals, reversed, reversal_economic, june_5, 0,
                            95'600'000'000LL, 0, 4'400'000'000LL);

  const auto reversal_settled_economic = timestamp(june_6, end_of_day);
  const auto reversal_settled = ledger.resolve(timestamp(june_7, 12h), reversal_settled_economic);
  const auto reversal_settled_journals = project_trade_date_journals(
      reversal_settled, {timestamp(june_7, 12h), reversal_settled_economic, june_6});
  assert(reversal_settled_journals && reversal_settled_journals->entries().size() == 5);
  expect_projected_entry_identity(reversal_settled_journals->entries()[4],
                                  "td.reversal.settlement");
  assert(reversal_settled_journals->entries()[4].lines()[0].account_id() ==
         AccountId{"asset.cash"});
  assert(reversal_settled_journals->entries()[4].lines()[1].account_id() ==
         AccountId{"asset.trade-receivable"});
  expect_portfolio_controls(*reversal_settled_journals, reversal_settled, reversal_settled_economic,
                            june_6, 0, 100'000'000'000LL, 0, 0);

  expect_projection_error(
      project_trade_date_journals(corrected, {trade_recorded, corrected_economic, june_2}),
      TradeDateProjectionDiagnosticCategory::invalid_context, "trade-record-v2");
  expect_projection_error(
      project_trade_date_journals(
          original, {timestamp(june_2, end_of_day), original_economic, 2026y / February / 30d}),
      TradeDateProjectionDiagnosticCategory::invalid_context);
}

void test_trade_date_projection_rounding_and_rejections() {
  using namespace std::chrono;
  const auto trade_date = 2026y / June / 2d;
  const auto settlement_date = 2026y / June / 4d;
  const auto effective = timestamp(trade_date, 10h);
  const auto recorded = timestamp(trade_date, 11h);
  const auto cutoff = timestamp(trade_date, 23h);
  const auto context = TradeDateProjectionContext{cutoff, cutoff, trade_date};

  const auto project_one = [&](EconomicEvent event) {
    LifecycleLedger ledger;
    accept(ledger, LifecycleRecordDraft::originate(EconomicEventId{"economic"}, recorded,
                                                   std::move(event)));
    const auto resolution = ledger.resolve(cutoff, cutoff);
    return project_trade_date_journals(resolution, context);
  };

  const auto rounded = project_one(
      trade_event("rounded", effective, "rounded-source", "0.00000001", "150", settlement_date));
  assert(rounded && rounded->entries().size() == 1);
  assert(rounded->entries()[0].debit_total().scaled_value() == 2);
  const auto rounded_even = project_one(trade_event(
      "rounded-even", effective, "rounded-even-source", "0.00000001", "250", settlement_date));
  assert(rounded_even && rounded_even->entries()[0].debit_total().scaled_value() == 2);

  expect_projection_error(
      project_one(cash_event("withdrawal", effective, "withdrawal-source", "fund-a", "-1")),
      TradeDateProjectionDiagnosticCategory::unsupported_event, "withdrawal");
  expect_projection_error(
      project_one(trade_event("sell", effective, "sell-source", "-1", "50", settlement_date)),
      TradeDateProjectionDiagnosticCategory::unsupported_event, "sell");
  expect_projection_error(project_one(trade_event("zero-price", effective, "zero-price-source", "1",
                                                  "0", settlement_date)),
                          TradeDateProjectionDiagnosticCategory::unsupported_event, "zero-price");
  expect_projection_error(
      project_one(trade_event("settlement-before-trade", effective,
                              "settlement-before-trade-source", "1", "50", 2026y / June / 1d)),
      TradeDateProjectionDiagnosticCategory::invalid_context, "settlement-before-trade");
  expect_projection_error(
      project_one(cash_event("eur-cash", effective, "eur-source", "fund-a", "1", "EUR")),
      TradeDateProjectionDiagnosticCategory::unsupported_currency, "eur-cash");

  LifecycleLedger euro_ledger;
  accept(euro_ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"eur-economic"}, recorded,
                                         trade_event("eur-trade", effective, "eur-source", "1",
                                                     "50", settlement_date, "fund-a", "EUR")));
  const auto euro_resolution = euro_ledger.resolve(cutoff, cutoff);
  expect_projection_error(project_trade_date_journals(euro_resolution, context),
                          TradeDateProjectionDiagnosticCategory::unsupported_currency, "eur-trade");

  const auto maximum = std::numeric_limits<std::int64_t>::max();
  auto overflow_header = EventHeader::create(EventId{"overflow"}, AccountId{"fund-a"}, effective,
                                             provenance("overflow-source"));
  auto overflow_date = SettlementDate::create(settlement_date);
  assert(overflow_header && overflow_date);
  auto overflow_trade =
      EquityTrade::create(*overflow_header, InstrumentId{"MSFT"}, Quantity::from_scaled(maximum),
                          Price::from_scaled(maximum), currency("USD"), *overflow_date);
  assert(overflow_trade);
  expect_projection_error(project_one(*overflow_trade),
                          TradeDateProjectionDiagnosticCategory::arithmetic_overflow, "overflow");

  LifecycleLedger cash_reversal_ledger;
  accept(cash_reversal_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"cash-reversal-target-economic"}, recorded,
             cash_event("cash-reversal-target", effective, "cash-reversal-target-source")));
  accept(cash_reversal_ledger,
         LifecycleRecordDraft::reverse(EconomicEventId{"cash-reversal-economic"},
                                       EventId{"cash-reversal-target"}, recorded + 1s,
                                       cash_event("cash-reversal", effective + 1s,
                                                  "cash-reversal-source", "account-a", "-10")));
  const auto cash_reversal_resolution = cash_reversal_ledger.resolve(cutoff, cutoff);
  expect_projection_error(project_trade_date_journals(cash_reversal_resolution, context),
                          TradeDateProjectionDiagnosticCategory::invalid_reversal_treatment,
                          "cash-reversal");

  LifecycleLedger colliding_identity_ledger;
  accept(colliding_identity_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"opening-cash-record-economic"}, recorded,
             cash_event("opening-cash-record", effective, "opening-cash-record-source")));
  accept(colliding_identity_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"opening-cash-economic"}, recorded + 1s,
             cash_event("opening-cash", effective + 1s, "opening-cash-source")));
  const auto colliding_identity_resolution = colliding_identity_ledger.resolve(cutoff, cutoff);
  expect_projection_error(project_trade_date_journals(colliding_identity_resolution, context),
                          TradeDateProjectionDiagnosticCategory::journal_invariant, "opening-cash");

  LifecycleLedger partial_reversal_ledger;
  accept(partial_reversal_ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"partial-target-economic"}, recorded,
                                         trade_event("partial-target", effective,
                                                     "partial-target-source", "10", "50",
                                                     settlement_date)));
  const auto partial_reversal = partial_reversal_ledger.accept(LifecycleRecordDraft::reverse(
      EconomicEventId{"partial-reversal-economic"}, EventId{"partial-target"}, recorded + 1s,
      trade_event("partial-reversal", effective + 1s, "partial-reversal-source", "-9", "50",
                  settlement_date)));
  assert(!partial_reversal);
  assert(partial_reversal.error().category() ==
         LifecycleDiagnosticCategory::incompatible_event_relationship);
  assert(partial_reversal.error().category_name() == "incompatible_event_relationship");
}
} // namespace

int main() {
  static_assert(LedgerSequence::first_value == 1);
  static_assert(
      std::is_same_v<decltype(std::declval<const LedgerEntry &>().event()), const EconomicEvent &>);
  static_assert(std::is_same_v<decltype(std::declval<const Ledger &>().entries()),
                               std::span<const LedgerEntry>>);
  static_assert(std::is_same_v<decltype(std::declval<const JournalEntry &>().lines()),
                               std::span<const JournalLine>>);
  static_assert(std::is_same_v<decltype(std::declval<const JournalEntry &>().policy()),
                               const AccountingPolicyIdentity &>);

  test_valid_journal_entries();
  test_journal_factory_rejections_and_boundaries();
  test_trade_date_projection_walkthrough();
  test_trade_date_projection_rounding_and_rejections();

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

  const auto duplicate =
      ledger.append(cash_event("a", earlier, "different-source", "different-account", "999"));
  assert(!duplicate && duplicate.error() == LedgerError::duplicate_event);
  assert(ledger.size() == 2);
  const auto *original = ledger.find(EventId{"a"});
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
  for (const auto &entry : ledger.entries())
    assert(same_history.append(entry.event()));
  for (std::size_t index = 0; index < ledger.size(); ++index)
    assert(same_history.entries()[index] == ledger.entries()[index]);
  const auto same_replay = same_history.economic_order();
  for (std::size_t index = 0; index < replay.size(); ++index)
    assert(same_replay[index].get() == replay[index].get());
}
