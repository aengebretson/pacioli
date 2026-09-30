#include <luca/portfolio.hpp>
#include <luca/reconciliation.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  const auto fail = [](const char* step) {
    std::cerr << "LUCA walkthrough failed: " << step << '\n';
    return 1;
  };
  const luca::AccountId account{"fund-a"};
  const auto usd = luca::Currency::from_code("USD");
  const auto trade_day = std::chrono::year{2026} / std::chrono::June / 4;
  const auto settlement_day = std::chrono::year{2026} / std::chrono::June / 5;
  const luca::Timestamp deposit_at{std::chrono::sys_days{trade_day}};
  const luca::Timestamp trade_at{deposit_at + std::chrono::hours{1}};
  const luca::Timestamp as_of{std::chrono::sys_days{settlement_day}};
  const auto settlement = luca::SettlementDate::create(settlement_day);
  if (!usd || !settlement) return fail("currency/date");

  // Explicit decimal inputs: no binary floating-point amounts or live feeds.
  const auto deposit = luca::Money::parse("1000.00", *usd);
  const auto quantity = luca::Quantity::parse("10");
  const auto price = luca::Price::parse("20.00");
  const auto bank_amount = luca::Money::parse("790.00", *usd);
  if (!deposit || !quantity || !price || !bank_amount) return fail("exact values");

  const auto deposit_source = luca::Provenance::create(
      {luca::SourceRecordId{"source.deposit.1"}}, "package-walkthrough", "1");
  const auto trade_source = luca::Provenance::create(
      {luca::SourceRecordId{"source.trade.1"}}, "package-walkthrough", "1");
  const auto bank_source = luca::Provenance::create(
      {luca::SourceRecordId{"observation.bank.1"}}, "bank-observation", "1");
  if (!deposit_source || !trade_source || !bank_source) return fail("provenance");
  const auto deposit_header = luca::EventHeader::create(
      luca::EventId{"deposit-1"}, account, deposit_at, *deposit_source);
  const auto trade_header = luca::EventHeader::create(
      luca::EventId{"trade-1"}, account, trade_at, *trade_source);
  if (!deposit_header || !trade_header) return fail("event headers");
  const auto trade = luca::EquityTrade::create(
      *trade_header, luca::InstrumentId{"equity-a"}, *quantity, *price, *usd, *settlement);
  if (!trade) return fail("equity trade");

  luca::Ledger ledger;
  if (!ledger.append(luca::CashMovement::create(*deposit_header, *deposit)) ||
      !ledger.append(*trade)) return fail("append");

  // Same ordered event history, different explicit settlement contexts.
  const auto positions = luca::project_positions(ledger.entries(), as_of);
  const auto cash_before = luca::project_cash(ledger.entries(), {as_of, trade_day});
  const auto open_before =
      luca::project_settlement_obligations(ledger.entries(), {as_of, trade_day});
  const auto cash = luca::project_cash(ledger.entries(), {as_of, settlement_day});
  const auto open_after =
      luca::project_settlement_obligations(ledger.entries(), {as_of, settlement_day});
  if (!positions || !cash_before || !open_before || !cash || !open_after ||
      positions->size() != 1 || cash_before->size() != 1 || open_before->size() != 1 ||
      cash->size() != 1) return fail("projections");

  // External evidence remains separate; the discrepancy never changes the ledger.
  const auto observation = luca::CashObservation::create(
      account, *bank_amount, as_of, settlement_day, *bank_source);
  if (!observation) return fail("observation");
  const std::vector observations{*observation};
  const auto breaks = luca::reconcile_cash(*cash, observations, {as_of, settlement_day});
  if (!breaks || breaks->size() != 1 ||
      breaks->front().kind() != luca::CashBreakKind::amount_mismatch ||
      !breaks->front().difference() || !breaks->front().observation_provenance())
    return fail("reconciliation");

  std::cout << "position_scaled=" << positions->front().quantity().scaled_value()
            << " cash_before_scaled=" << cash_before->front().amount().scaled_value()
            << " payable_before_scaled=" << open_before->front().amount().scaled_value()
            << " cash_scaled=" << cash->front().amount().scaled_value()
            << " open_after=" << open_after->size() << '\n';
  std::cout << "cash_break=amount_mismatch difference_scaled="
            << breaks->front().difference()->scaled_value() << " currency=" << usd->code()
            << " observation_source="
            << breaks->front().observation_provenance()->source_records().front().value()
            << '\n';
  for (const auto& entry : ledger.entries()) {
    const auto& event_header = luca::header(entry.event());
    std::cout << "event=" << event_header.id().value() << " source="
              << event_header.provenance().source_records().front().value() << '\n';
  }
  return 0;
}
