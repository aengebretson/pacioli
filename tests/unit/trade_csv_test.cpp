#ifdef NDEBUG
#undef NDEBUG
#endif
#include "luca/adapters/trade_csv.hpp"
#include "luca/reconciliation/trade_reconciliation.hpp"

#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

using namespace luca;
using namespace luca::adapters;
using namespace std::chrono;
namespace {
const Timestamp cutoff = sys_days{year{2026} / 9 / 30};
const auto context = *TradeComparisonContext::create(cutoff, cutoff,
    year{2026} / 9 / 28, year{2026} / 9 / 30, {AccountId{"a"}, AccountId{"b"}});
const TradeCsvSource source{SourceId{"synthetic"}, SourceRecordId{"statement-1"},
    *PayloadHash::create("synthetic", "payload-digest"), cutoff};
const std::string header = std::string(trade_csv_header) + "\n";
const std::string row = "ext-1,a,MSFT,100,50,USD,2026-09-28,2026-09-29";
std::string record(std::size_t column, std::string value) {
  std::array<std::string, 8> fields{"ext-1", "a", "MSFT", "100", "50", "USD", "2026-09-28", "2026-09-29"};
  fields[column - 1] = std::move(value);
  std::string result;
  for (const auto& field : fields) { if (!result.empty()) result += ','; result += field; }
  // Column 1 empty must still preserve its delimiter.
  if (fields[0].empty()) result.insert(result.begin(), ',');
  return result;
}
void reject(std::string text, TradeCsvErrorCode code, std::size_t physical_row = 2, std::size_t column = 0) {
  auto result = parse_trade_csv(text, source, context);
  assert(!result && result.error().code == code && result.error().row == physical_row);
  if (column) assert(result.error().column == column);
}
void exact_and_owned_evidence() {
  auto first = parse_trade_csv(header + row + "\n", source, context);
  auto second = parse_trade_csv(header + row + "\n", source, context);
  assert(first && first->size() == 1 && first == second);
  assert(first->front().terms().quantity() == *Quantity::parse("100"));
  const auto& evidence = first->front().source_record();
  assert(evidence.id().value() == "trade-csv-v1:9:synthetic:11:statement-1:2");
  assert(evidence.payload_hash() == source.payload_hash);
  assert(evidence.source_reference() == source.statement_id.value());
  assert(evidence.external_record_id() == "ext-1");
  assert(evidence.observed_at() == cutoff && !evidence.source_event_at());
  assert(first->front().provenance().source_records().front() == evidence.id());
  assert(parse_trade_csv(std::string(trade_csv_header), source, context)->empty());
  assert(parse_trade_csv(header, source, context)->empty());
  assert(parse_trade_csv(header + row, source, context) == first);  // No final newline required.
  auto crlf = parse_trade_csv(std::string(trade_csv_header) + "\r\n" + row + "\r\n", source, context);
  assert(crlf == first);  // Supplied digest, not calculated from this variant.
  auto quoted = parse_trade_csv(header + "\"ext,\"\"1\"\"\",a,\"Caf\xc3\xa9\",-0.00000001,0,EUR,2026-09-28,2026-09-29\n", source, context);
  assert(quoted && quoted->front().key().external_trade_id() == "ext,\"1\"");
  assert(quoted->front().terms().instrument().value() == "Caf\xc3\xa9");
  assert(quoted->front().terms().quantity().scaled_value() == -1);
  assert(quoted->front().terms().price().scaled_value() == 0);
  auto quoted_header = std::string(trade_csv_header);
  quoted_header.replace(0, 17, "\"external_trade_id\"");
  // Entire header uses the same CSV quoting grammar.
  assert(parse_trade_csv(quoted_header + "\n" + row, source, context));
  auto two = parse_trade_csv(header + row + "\n" + record(2, "b"), source, context);
  assert(two && two->size() == 2);  // Equal external ID across accounts is valid.
  assert(two->at(1).source_record().id().value().ends_with(":3"));
  auto new_source = source;
  new_source.statement_id = SourceRecordId{"statement-corrected"};
  auto corrected = parse_trade_csv(header + record(4, "80"), new_source, context);
  assert(corrected && corrected->front().source_record().id() != evidence.id());
  // Delimiter-looking source IDs cannot collide due to byte-length framing.
  auto framed_a = source;
  auto framed_b = source;
  framed_a.source = SourceId{"a:b"}; framed_a.statement_id = SourceRecordId{"c"};
  framed_b.source = SourceId{"a"}; framed_b.statement_id = SourceRecordId{"b:c"};
  assert(parse_trade_csv(header + row, framed_a, context)->front().source_record().id() !=
         parse_trade_csv(header + row, framed_b, context)->front().source_record().id());
}
void malformed_records() {
  using C = TradeCsvErrorCode;
  reject("", C::missing_header, 1);
  reject("account,instrument\n", C::wrong_column_count, 1);
  reject(header + row + ",extra", C::wrong_column_count);
  reject(header + "ext-1,a,MSFT,100,50,USD,2026-09-28", C::wrong_column_count);
  const std::string reordered = "account,external_trade_id,instrument,quantity,price,currency,trade_date,settlement_date\n";
  reject(reordered + row, C::invalid_header, 1);
  auto duplicate_header = header;
  duplicate_header.replace(0, 17, "account");
  reject(duplicate_header + row, C::invalid_header, 1);
  reject("\xef\xbb\xbf" + header + row, C::invalid_header, 1);
  reject(header + "\"ext-1,a,MSFT,100,50,USD,2026-09-28,2026-09-29", C::malformed_csv);
  reject(header + "\"ext-1\"x,a,MSFT,100,50,USD,2026-09-28,2026-09-29", C::malformed_csv);
  reject(header + record(1, "ext\"1"), C::malformed_csv);
  reject(header + record(1, "\"ext\n1\""), C::malformed_csv);
  reject(header + record(1, "ext\r1"), C::malformed_csv);
  reject(header + row + "\r", C::malformed_csv);
  reject(header + record(3, std::string("M\0S", 3)), C::malformed_csv);
  reject(header + "\n", C::wrong_column_count);
  reject(header + record(1, ""), C::invalid_identifier, 2, 1);
  reject(header + record(2, " a"), C::invalid_identifier, 2, 2);
  reject(header + record(3, "MSFT "), C::invalid_identifier, 2, 3);
  reject(header + record(2, "outside"), C::outside_coverage);
  reject(header + record(7, "2026-09-27"), C::outside_coverage);
  for (const std::string invalid : {"+1", "1e2", ".1", "1.", "1,000", " 1", "1.000000000", "-", "92233720368.54775808"}) {
    reject(header + record(4, '"' + invalid + '"'), C::invalid_decimal, 2, 4);
    reject(header + record(5, '"' + invalid + '"'), C::invalid_decimal, 2, 5);
  }
  reject(header + record(4, "0"), C::invalid_trade, 2, 4);
  reject(header + record(5, "-1"), C::invalid_trade, 2, 5);
  reject(header + record(6, "usd"), C::invalid_currency, 2, 6);
  for (const std::string invalid : {"2026-02-30", "2026-9-28", "0000-09-28", "2026-13-01"}) {
    reject(header + record(7, invalid), C::invalid_date, 2, 7);
    reject(header + record(8, invalid), C::invalid_date, 2, 8);
  }
  // One valid row followed by failure exposes no partial vector.
  reject(header + row + "\n" + row, C::duplicate_key, 3);
  reject(header + row + "\n" + record(4, "80"), C::duplicate_key, 3);
  reject(header + row + "\n" + record(5, "invalid"), C::invalid_decimal, 3, 5);
}
void utf8_and_bounds() {
  using C = TradeCsvErrorCode;
  for (const std::string& bytes : {std::string("\xc0\xaf"), std::string("\xed\xa0\x80"),
       std::string("\xf4\x90\x80\x80"), std::string("\xe2\x82"), std::string("\x80")})
    reject(header + record(3, bytes), C::invalid_utf8, 0);
  const auto text = header + row;
  auto limits = TradeCsvLimits{};
  limits.max_bytes = text.size();
  assert(parse_trade_csv(text, source, context, limits));
  --limits.max_bytes;
  assert(parse_trade_csv(text, source, context, limits).error().code == C::input_too_large);
  limits = {}; limits.max_rows = 1;
  assert(parse_trade_csv(text + "\n" + record(1, "second"), source, context, limits).error().code == C::too_many_rows);
  limits = {}; limits.max_field_bytes = 17;
  assert(parse_trade_csv(text, source, context, limits));
  assert(parse_trade_csv(header + record(1, std::string(18, 'x')), source, context, limits).error().code == C::field_too_large);
  limits = {}; limits.max_record_bytes = trade_csv_header.size();
  assert(parse_trade_csv(text, source, context, limits));
  assert(parse_trade_csv(header + record(1, std::string(100, 'x')), source, context, limits).error().code == C::record_too_large);
  limits = {}; limits.max_rows = 0;
  assert(parse_trade_csv(text, source, context, limits).error().code == C::invalid_limits);
  limits = {}; ++limits.max_bytes;
  assert(parse_trade_csv(text, source, context, limits).error().code == C::invalid_limits);
  auto bad_source = source; bad_source.statement_id = SourceRecordId{""};
  assert(parse_trade_csv(text, bad_source, context).error().code == C::invalid_source);
}

std::string fixture(const char* name) {
  std::ifstream stream(std::string(LUCA_TRADE_FIXTURE_DIR) + "/" + name, std::ios::binary);
  assert(stream);
  return {std::istreambuf_iterator<char>{stream}, std::istreambuf_iterator<char>{}};
}
void portable_csv_fixtures() {
  const auto scope = *TradeComparisonContext::create(cutoff, cutoff,
      year{2026} / 9 / 28, year{2026} / 9 / 30, {AccountId{"fund-a"}});
  const auto proof = [](const char* id) {
    return *Provenance::create({SourceRecordId{id}}, "fixture", "1");
  };
  const auto make_trade = [&](const char* id, const char* source_id, const char* quantity, const char* price) {
    return *EquityTrade::create(
        *EventHeader::create(EventId{id}, AccountId{"fund-a"}, sys_days{year{2026} / 9 / 28}, proof(source_id)),
        InstrumentId{"MSFT"}, *Quantity::parse(quantity), *Price::parse(price), *Currency::from_code("USD"),
        *SettlementDate::create(year{2026} / 9 / 29));
  };
  LifecycleLedger ledger;
  assert(ledger.accept(LifecycleRecordDraft::originate(EconomicEventId{"economic-1"},
      sys_days{year{2026} / 9 / 28}, make_trade("record-1", "execution-1", "100", "50"))));
  std::array maps{TradeIdentityMapping{EconomicEventId{"economic-1"}, EventId{"record-1"},
      *TradeKey::create(AccountId{"fund-a"}, "custodian-42"), year{2026} / 9 / 28, proof("mapping-1")}};
  const auto expected = project_trades(ledger, maps, scope);
  assert(expected);
  const TradeCsvSource original_source{SourceId{"synthetic-custodian"}, SourceRecordId{"statement-original"},
      *PayloadHash::create("synthetic", "original-statement"), cutoff};
  const auto original = parse_trade_csv(fixture("exact.csv"), original_source, scope);
  assert(original);
  assert(reconcile_trades(*expected, *original, scope)->entries.front().kind == TradeComparisonKind::exact_match);
  const auto different = parse_trade_csv(fixture("differing.csv"), source, scope);
  assert(different);
  assert((reconcile_trades(*expected, *different, scope)->entries.front().differing_fields ==
      std::vector{TradeField::instrument, TradeField::quantity, TradeField::price,
                  TradeField::currency, TradeField::trade_date, TradeField::settlement_date}));
  const auto missing = parse_trade_csv(fixture("missing.csv"), source, scope);
  assert(missing && missing->empty());
  assert(reconcile_trades(*expected, *missing, scope)->entries.front().kind == TradeComparisonKind::missing_observation);
  const auto extra = parse_trade_csv(fixture("unexpected.csv"), source, scope);
  assert(extra);
  const auto no_guess = reconcile_trades(*expected, *extra, scope);
  assert(no_guess->entries.size() == 2);
  assert(no_guess->entries[0].kind == TradeComparisonKind::missing_observation);
  assert(no_guess->entries[1].kind == TradeComparisonKind::unexpected_observation);
  for (const char* name : {"duplicate.csv", "ambiguous.csv", "malformed.csv"}) {
    auto result = parse_trade_csv(fixture(name), source, scope);
    assert(!result && result.error().row == 3);
    assert(result.error().code == (std::string_view(name) == "malformed.csv" ?
        TradeCsvErrorCode::invalid_decimal : TradeCsvErrorCode::duplicate_key));
  }
  assert(ledger.accept(LifecycleRecordDraft::correct(EconomicEventId{"economic-1"}, EventId{"record-1"},
      cutoff, make_trade("record-2", "execution-2", "80", "55"))));
  maps[0].active_record_id = EventId{"record-2"};
  maps[0].provenance = proof("mapping-2");
  const auto updated = project_trades(ledger, maps, scope);
  assert(updated && updated->front().lineage().size() == 2);
  assert((reconcile_trades(*updated, *original, scope)->entries.front().differing_fields ==
      std::vector{TradeField::quantity, TradeField::price}));
  const TradeCsvSource corrected_source{SourceId{"synthetic-custodian"}, SourceRecordId{"statement-corrected"},
      *PayloadHash::create("synthetic", "corrected-statement"), cutoff};
  const auto corrected = parse_trade_csv(fixture("corrected.csv"), corrected_source, scope);
  assert(corrected);
  assert(reconcile_trades(*updated, *corrected, scope)->entries.front().kind == TradeComparisonKind::exact_match);
  assert(original->front().source_record().id() != corrected->front().source_record().id());
}
}  // namespace
int main() { exact_and_owned_evidence(); malformed_records(); utf8_and_bounds(); portable_csv_fixtures(); }
