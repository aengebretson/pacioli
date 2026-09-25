#include <luca/accounting/journal.hpp>
#include <luca/ledger.hpp>
#include <luca/lifecycle.hpp>
#include <luca/serialization/canonical.hpp>
#include <luca/serialization/canonical_decode.hpp>

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  using namespace std::chrono_literals;

  const auto usd = luca::Currency::from_code("USD");
  if (!usd)
    return 1;
  const auto amount = luca::Money::parse("125.00", *usd);
  const auto provenance = luca::Provenance::create(
      std::vector{luca::SourceRecordId{"ledger-consumer-source-1"}}, "ledger-consumer", "1");
  if (!amount || !provenance)
    return 1;

  constexpr luca::Timestamp effective_at{1s};
  const auto header =
      luca::EventHeader::create(luca::EventId{"ledger-deposit-1"},
                                luca::AccountId{"ledger-account-1"}, effective_at, *provenance);
  if (!header)
    return 2;

  luca::Ledger ledger;
  const auto event = luca::CashMovement::create(*header, *amount);
  if (!ledger.append(event))
    return 3;
  if (ledger.entries().size() != 1)
    return 4;

  luca::LifecycleLedger lifecycle;
  if (!lifecycle.accept(luca::LifecycleRecordDraft::originate(
          luca::EconomicEventId{"ledger-economic-deposit-1"}, effective_at, event)))
    return 5;
  const auto lifecycle_resolution = lifecycle.resolve(effective_at, effective_at);
  const auto projected_journal = luca::project_trade_date_journals(
      lifecycle_resolution,
      luca::TradeDateProjectionContext{effective_at, effective_at,
                                       std::chrono::year{2026} / std::chrono::January /
                                           std::chrono::day{1}});
  if (!projected_journal || projected_journal->entries().size() != 1 ||
      projected_journal->entries().front().debit_total() != *amount ||
      projected_journal->entries().front().journal_entry_id() !=
          luca::JournalEntryId{"td.ledger-deposit-1.immediate"} ||
      projected_journal->policy().id() != luca::AccountingPolicyId{"fixture.trade-date.v1"} ||
      projected_journal->active_record_ids().size() != 1 ||
      projected_journal->source_record_ids().size() != 1)
    return 6;
  if (luca::serialization::canonical_digest(lifecycle).size() != 64)
    return 7;
  const auto lifecycle_bytes = luca::serialization::canonical_bytes(lifecycle);
  const auto decoded = luca::serialization::decode_lifecycle_ledger(lifecycle_bytes);
  if (!decoded || decoded->size() != 1 ||
      luca::serialization::canonical_bytes(*decoded) != lifecycle_bytes)
    return 8;

  const auto journal_lineage =
      luca::JournalLineage::create(std::vector{luca::EventId{"ledger-deposit-1"}},
                                   std::vector{luca::EconomicEventId{"ledger-economic-deposit-1"}},
                                   std::vector{luca::SourceRecordId{"ledger-consumer-source-1"}});
  const auto policy = luca::AccountingPolicyIdentity::create(
      luca::AccountingPolicyId{"package-consumer.cash-contribution"}, "1");
  const auto recognized_on = luca::JournalDate::create(
      std::chrono::year{2026} / std::chrono::September / std::chrono::day{24});
  const auto settlement_context =
      luca::JournalSettlementContext::create(std::nullopt, std::nullopt, "immediate");
  if (!journal_lineage || !policy || !recognized_on || !settlement_context)
    return 8;

  const luca::JournalEntryId journal_entry_id{"ledger-journal-entry-1"};
  const auto debit = luca::JournalLine::create(luca::JournalLineId{"ledger-journal-line-debit-1"},
                                               journal_entry_id, luca::AccountId{"asset.cash"},
                                               luca::JournalSide::debit, *amount, *journal_lineage);
  const auto credit =
      luca::JournalLine::create(luca::JournalLineId{"ledger-journal-line-credit-1"},
                                journal_entry_id, luca::AccountId{"equity.contributed-capital"},
                                luca::JournalSide::credit, *amount, *journal_lineage);
  if (!debit || !credit)
    return 9;

  const auto journal_entry = luca::JournalEntry::create(
      journal_entry_id, *policy, luca::JournalEventType::cash_movement,
      luca::EventId{"ledger-deposit-1"}, effective_at, luca::Timestamp{2s}, *recognized_on,
      luca::RecognitionPhase::immediate, 0, *settlement_context, *journal_lineage,
      std::vector{*debit, *credit});
  if (!journal_entry)
    return 10;
  if (journal_entry->debit_total() != *amount || journal_entry->credit_total() != *amount)
    return 11;
  if (journal_entry->policy().id() !=
          luca::AccountingPolicyId{"package-consumer.cash-contribution"} ||
      journal_entry->policy().version() != "1")
    return 12;
  const auto source_lineage = journal_entry->lineage().source_record_ids();
  if (source_lineage.size() != 1 ||
      source_lineage.front() != luca::SourceRecordId{"ledger-consumer-source-1"})
    return 13;
  for (const auto &line : journal_entry->lines())
    if (line.lineage().source_record_ids().size() != 1 ||
        line.lineage().source_record_ids().front() != source_lineage.front())
      return 14;

  std::cout << "ledger_entries=" << ledger.entries().size()
            << " journal_debit_scaled=" << journal_entry->debit_total().scaled_value()
            << " projected_entries=" << projected_journal->entries().size()
            << " policy=" << journal_entry->policy().id().value()
            << " source=" << source_lineage.front().value() << '\n';
  return 0;
}
