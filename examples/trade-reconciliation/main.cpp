#include "luca/adapters/trade_csv.hpp"
#include "luca/reconciliation/trade_reconciliation.hpp"

#include <array>
#include <iostream>

int main() {
  using namespace luca;
  using namespace std::chrono;
  const auto trade_date = year{2026} / 9 / 28;
  const auto settlement_date = *SettlementDate::create(year{2026} / 9 / 29);
  const Timestamp economic = sys_days{year{2026} / 9 / 30};
  const Timestamp knowledge = economic;
  const auto context = *TradeComparisonContext::create(
      economic, knowledge, trade_date, year{2026} / 9 / 30, {AccountId{"fund-a"}});
  const auto original_source = *Provenance::create({SourceRecordId{"execution-1"}}, "fixture", "1");
  const auto correction_source = *Provenance::create({SourceRecordId{"execution-2"}}, "fixture", "1");
  const auto original = *EquityTrade::create(
      *EventHeader::create(EventId{"record-1"}, AccountId{"fund-a"}, sys_days{trade_date}, original_source),
      InstrumentId{"MSFT"}, *Quantity::parse("100"), *Price::parse("50"),
      *Currency::from_code("USD"), settlement_date);
  const auto correction = *EquityTrade::create(
      *EventHeader::create(EventId{"record-2"}, AccountId{"fund-a"}, sys_days{trade_date}, correction_source),
      InstrumentId{"MSFT"}, *Quantity::parse("80"), *Price::parse("55"),
      *Currency::from_code("USD"), settlement_date);
  LifecycleLedger ledger;
  if (!ledger.accept(LifecycleRecordDraft::originate(EconomicEventId{"economic-1"}, sys_days{trade_date}, original))) return 1;
  if (!ledger.accept(LifecycleRecordDraft::correct(EconomicEventId{"economic-1"}, EventId{"record-1"}, economic, correction))) return 2;
  // Supplied matching ID deliberately differs from both ledger identities.
  const std::array mappings{TradeIdentityMapping{
      EconomicEventId{"economic-1"}, EventId{"record-2"},
      *TradeKey::create(AccountId{"fund-a"}, "custodian-42"), trade_date,
      *Provenance::create({SourceRecordId{"mapping-1"}}, "fixture.trade-map", "1")}};
  const auto expected = project_trades(ledger, mappings, context);
  if (!expected) return 3;
  const std::string original_csv = std::string(adapters::trade_csv_header) +
      "\ncustodian-42,fund-a,MSFT,100,50,USD,2026-09-28,2026-09-29\n";
  const std::string corrected_csv = std::string(adapters::trade_csv_header) +
      "\ncustodian-42,fund-a,MSFT,80,55,USD,2026-09-28,2026-09-29\n";
  // Explicit synthetic digests; parsing preserves them and does not verify them.
  const auto observed = adapters::parse_trade_csv(original_csv,
      {SourceId{"synthetic-custodian"}, SourceRecordId{"statement-original"},
       *PayloadHash::create("synthetic", "original-payload"), knowledge}, context);
  const auto corrected = adapters::parse_trade_csv(corrected_csv,
      {SourceId{"synthetic-custodian"}, SourceRecordId{"statement-corrected"},
       *PayloadHash::create("synthetic", "corrected-payload"), knowledge}, context);
  if (!observed || !corrected) return 4;
  const auto first = reconcile_trades(*expected, *observed, context);
  const auto second = reconcile_trades(*expected, *corrected, context);
  if (!first || !second) return 5;
  std::cout << "Original statement: " << first->entries.front().differing_fields.size()
            << " differing fields\nCorrected statement: "
            << second->entries.front().differing_fields.size() << " differing fields\n";
}
