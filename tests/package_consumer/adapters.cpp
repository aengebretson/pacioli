#include <luca/adapters/trade_csv.hpp>
#include <luca/reconciliation/trade_reconciliation.hpp>

#include <chrono>
#include <iostream>
#include <string>

int main() {
  using namespace luca;
  const auto day = std::chrono::year{2026} / std::chrono::September / 28;
  const Timestamp cutoff{std::chrono::sys_days{day}};
  const auto context = TradeComparisonContext::create(
      cutoff, cutoff, day, day, {AccountId{"consumer-fund"}});
  const auto digest = PayloadHash::create("synthetic", "consumer-statement");
  if (!context || !digest) return 1;
  const adapters::TradeCsvSource source{
      SourceId{"consumer-custodian"}, SourceRecordId{"statement-1"}, *digest, cutoff};
  const std::string csv = std::string{adapters::trade_csv_header} +
      "\nexternal-1,consumer-fund,equity-a,10,20,USD,2026-09-28,2026-09-29\n";
  const auto observed = adapters::parse_trade_csv(csv, source, *context);
  if (!observed || observed->size() != 1) return 2;

  // External evidence cannot create a projected trade in an empty ledger.
  const LifecycleLedger ledger;
  const auto projected = project_trades(ledger, {}, *context);
  if (!projected || !projected->empty()) return 3;
  const auto report = reconcile_trades(*projected, *observed, *context);
  if (!report || report->entries.size() != 1 ||
      report->entries.front().kind != TradeComparisonKind::unexpected_observation ||
      report->entries.front().expected ||
      report->entries.front().observed != observed->front()) return 4;
  std::cout << "trade_observations=1 unexpected_observations=1\n";
}
