#pragma once

#include "luca/lifecycle.hpp"
#include "luca/reconciliation/trade_observation.hpp"

#include <map>
#include <optional>
#include <set>

namespace luca {

// Mapping is supplied evidence, never inferred from coincident economic terms.
// Binding to both identities forces a correction to receive an explicit mapping.
struct TradeIdentityMapping {
  EconomicEventId economic_event_id;
  EventId active_record_id;
  TradeKey key;
  std::chrono::year_month_day trade_date;
  Provenance provenance;
};

enum class TradeReconciliationErrorCode {
  context_mismatch, duplicate_projection_key, duplicate_observation_key,
  ambiguous_projection_identity, ambiguous_observation_identity,
  duplicate_mapping, missing_mapping, unused_mapping, mapping_identity_mismatch,
  invalid_trade,
};
enum class TradeInputSide { projection, observation, mapping };
struct TradeReconciliationError {
  TradeReconciliationErrorCode code;
  TradeInputSide side;
  std::optional<TradeKey> key;
  std::optional<EventId> record_id;
  std::optional<TradeValueError> value_error;
  bool operator==(const TradeReconciliationError&) const = default;
};

class TradeProjectionRow;
[[nodiscard]] inline std::expected<std::vector<TradeProjectionRow>, TradeReconciliationError>
project_trades(const LifecycleLedger&, std::span<const TradeIdentityMapping>,
               const TradeComparisonContext&);

// Immutable owned report input. Only lifecycle resolution plus an explicit
// mapping can construct it; observations cannot be promoted into this type.
class TradeProjectionRow {
 public:
  [[nodiscard]] const TradeKey& key() const noexcept { return key_; }
  [[nodiscard]] const TradeTerms& terms() const noexcept { return terms_; }
  [[nodiscard]] const TradeComparisonContext& context() const noexcept { return context_; }
  [[nodiscard]] const LifecycleRecord& active_record() const noexcept { return lineage_.back(); }
  [[nodiscard]] const EconomicEventId& economic_event_id() const noexcept {
    return active_record().economic_event_id();
  }
  [[nodiscard]] std::span<const LifecycleRecord> lineage() const noexcept { return lineage_; }
  [[nodiscard]] std::span<const LifecycleRecord> reversal_target_lineage() const noexcept {
    return reversal_target_lineage_;
  }
  [[nodiscard]] const Provenance& mapping_provenance() const noexcept { return mapping_provenance_; }
  bool operator==(const TradeProjectionRow&) const = default;
 private:
  friend std::expected<std::vector<TradeProjectionRow>, TradeReconciliationError>
  project_trades(const LifecycleLedger&, std::span<const TradeIdentityMapping>,
                 const TradeComparisonContext&);
  TradeProjectionRow(TradeKey key, TradeTerms terms, TradeComparisonContext context,
                     std::vector<LifecycleRecord> lineage,
                     std::vector<LifecycleRecord> reversal_target_lineage, Provenance mapping)
      : key_(std::move(key)), terms_(std::move(terms)), context_(std::move(context)),
        lineage_(std::move(lineage)), reversal_target_lineage_(std::move(reversal_target_lineage)),
        mapping_provenance_(std::move(mapping)) {}
  TradeKey key_;
  TradeTerms terms_;
  TradeComparisonContext context_;
  std::vector<LifecycleRecord> lineage_;
  std::vector<LifecycleRecord> reversal_target_lineage_;
  Provenance mapping_provenance_;
};

// Resolving here avoids falsely labeling a baseline LifecycleResolution with
// cutoffs it does not expose. The ledger is read-only and no new event is made.
// Map every active equity in covered accounts, including out-of-date-range
// trades: only the explicit mapping supplies the trade date used for selection.
[[nodiscard]] inline std::expected<std::vector<TradeProjectionRow>, TradeReconciliationError>
project_trades(const LifecycleLedger& ledger, std::span<const TradeIdentityMapping> mappings,
               const TradeComparisonContext& context) {
  using Code = TradeReconciliationErrorCode;
  std::map<EconomicEventId, const TradeIdentityMapping*> by_economic_id;
  std::set<TradeKey> keys;
  for (const auto& mapping : mappings) {
    if (!trade_detail::valid_identifier(mapping.economic_event_id.value()) ||
        !trade_detail::valid_identifier(mapping.active_record_id.value()) ||
        !context.covers(mapping.key.account()) || !mapping.trade_date.ok())
      return std::unexpected(TradeReconciliationError{
          Code::mapping_identity_mismatch, TradeInputSide::mapping, mapping.key,
          mapping.active_record_id, std::nullopt});
    if (!by_economic_id.emplace(mapping.economic_event_id, &mapping).second ||
        !keys.insert(mapping.key).second)
      return std::unexpected(TradeReconciliationError{
          Code::duplicate_mapping, TradeInputSide::mapping, mapping.key,
          mapping.active_record_id, std::nullopt});
  }
  const auto resolution = ledger.resolve(context.recorded_through(), context.economic_as_of());
  std::vector<TradeProjectionRow> rows;
  std::set<EconomicEventId> used;
  for (const auto& resolved : resolution.active_events()) {
    const auto* trade = std::get_if<EquityTrade>(&resolved.event());
    if (!trade || !context.covers(trade->header().account())) continue;
    const auto found = by_economic_id.find(resolved.record().economic_event_id());
    if (found == by_economic_id.end())
      return std::unexpected(TradeReconciliationError{
          Code::missing_mapping, TradeInputSide::mapping, std::nullopt,
          resolved.record().record_id(), std::nullopt});
    const auto& mapping = *found->second;
    if (mapping.active_record_id != resolved.record().record_id() ||
        mapping.key.account() != trade->header().account())
      return std::unexpected(TradeReconciliationError{
          Code::mapping_identity_mismatch, TradeInputSide::mapping, mapping.key,
          resolved.record().record_id(), std::nullopt});
    used.insert(mapping.economic_event_id);
    auto terms = TradeTerms::create(trade->instrument(), trade->quantity(), trade->price(),
                                    trade->quote_currency(), mapping.trade_date,
                                    trade->settlement_date());
    if (!terms)
      return std::unexpected(TradeReconciliationError{
          Code::invalid_trade, TradeInputSide::projection, mapping.key,
          resolved.record().record_id(), terms.error()});
    if (!context.covers(mapping.trade_date)) continue;
    std::vector<LifecycleRecord> lineage;
    for (const auto& record : resolved.lineage()) lineage.push_back(record.get());
    std::vector<LifecycleRecord> reversal_lineage;
    if (const auto* target = resolved.reversed_record()) {
      for (const auto& chain : resolution.chains()) {
        if (chain.economic_event_id() != target->economic_event_id()) continue;
        for (const auto& record : chain.lineage()) reversal_lineage.push_back(record.get());
        break;
      }
    }
    rows.push_back(TradeProjectionRow(mapping.key, std::move(*terms), context,
                                      std::move(lineage), std::move(reversal_lineage),
                                      mapping.provenance));
  }
  for (const auto& [id, mapping] : by_economic_id)
    if (!used.contains(id))
      return std::unexpected(TradeReconciliationError{
          Code::unused_mapping, TradeInputSide::mapping, mapping->key,
          mapping->active_record_id, std::nullopt});
  std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.key() < b.key(); });
  return rows;
}

enum class TradeField { instrument, quantity, price, currency, trade_date, settlement_date };
enum class TradeComparisonKind { exact_match, missing_observation, unexpected_observation, field_mismatch };

struct TradeComparisonEntry {
  TradeKey key;
  TradeComparisonKind kind;
  std::optional<TradeProjectionRow> expected;
  std::optional<TradeObservation> observed;
  std::vector<TradeField> differing_fields;
  bool operator==(const TradeComparisonEntry&) const = default;
};
struct TradeReconciliationReport {
  TradeComparisonContext context;
  std::vector<TradeComparisonEntry> entries;
  bool operator==(const TradeReconciliationReport&) const = default;
};

// This comparison projection performs no arithmetic, rounding, FX, netting or
// inference. Exact matches retain both evidence branches. Validation finishes
// before any output is returned, including duplicate keys with equal payloads.
[[nodiscard]] inline std::expected<TradeReconciliationReport, TradeReconciliationError>
reconcile_trades(std::span<const TradeProjectionRow> expected,
                 std::span<const TradeObservation> observed,
                 const TradeComparisonContext& context) {
  using Code = TradeReconciliationErrorCode;
  std::vector<const TradeProjectionRow*> projected;
  std::vector<const TradeObservation*> observations;
  for (const auto& row : expected) projected.push_back(&row);
  for (const auto& row : observed) observations.push_back(&row);
  const auto key_less = [](const auto* a, const auto* b) { return a->key() < b->key(); };
  std::sort(projected.begin(), projected.end(), key_less);
  std::sort(observations.begin(), observations.end(), key_less);
  // Fixed validation precedence: projection, then observation; sorted keys.
  std::set<EventId> records;
  std::set<EconomicEventId> economic_ids;
  for (std::size_t i = 0; i < projected.size(); ++i) {
    const auto& row = *projected[i];
    std::optional<Code> code;
    if (row.context() != context) code = Code::context_mismatch;
    else if (i && projected[i - 1]->key() == row.key()) code = Code::duplicate_projection_key;
    else if (!records.insert(row.active_record().record_id()).second ||
             !economic_ids.insert(row.economic_event_id()).second)
      code = Code::ambiguous_projection_identity;
    if (code) return std::unexpected(TradeReconciliationError{
        *code, TradeInputSide::projection, row.key(), std::nullopt, std::nullopt});
  }
  std::set<SourceRecordId> sources;
  for (std::size_t i = 0; i < observations.size(); ++i) {
    const auto& row = *observations[i];
    std::optional<Code> code;
    if (row.context() != context) code = Code::context_mismatch;
    else if (i && observations[i - 1]->key() == row.key()) code = Code::duplicate_observation_key;
    else if (!sources.insert(row.source_record().id()).second)
      code = Code::ambiguous_observation_identity;
    if (code) return std::unexpected(TradeReconciliationError{
        *code, TradeInputSide::observation, row.key(), std::nullopt, std::nullopt});
  }
  TradeReconciliationReport report{context, {}};
  std::size_t p = 0, o = 0;
  while (p < projected.size() || o < observations.size()) {
    if (o == observations.size() ||
        (p < projected.size() && projected[p]->key() < observations[o]->key())) {
      const auto& row = *projected[p++];
      report.entries.push_back({row.key(), TradeComparisonKind::missing_observation,
                                row, std::nullopt, {}});
    } else if (p == projected.size() || observations[o]->key() < projected[p]->key()) {
      const auto& row = *observations[o++];
      report.entries.push_back({row.key(), TradeComparisonKind::unexpected_observation,
                                std::nullopt, row, {}});
    } else {
      const auto& left = *projected[p++];
      const auto& right = *observations[o++];
      const auto& a = left.terms();
      const auto& b = right.terms();
      std::vector<TradeField> fields;
      if (a.instrument() != b.instrument()) fields.push_back(TradeField::instrument);
      if (a.quantity() != b.quantity()) fields.push_back(TradeField::quantity);
      if (a.price() != b.price()) fields.push_back(TradeField::price);
      if (a.currency() != b.currency()) fields.push_back(TradeField::currency);
      if (a.trade_date() != b.trade_date()) fields.push_back(TradeField::trade_date);
      if (a.settlement_date() != b.settlement_date()) fields.push_back(TradeField::settlement_date);
      const auto kind = fields.empty() ? TradeComparisonKind::exact_match : TradeComparisonKind::field_mismatch;
      report.entries.push_back({left.key(), kind, left, right, std::move(fields)});
    }
  }
  return report;
}

}  // namespace luca
