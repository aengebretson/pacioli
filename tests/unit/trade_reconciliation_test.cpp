#ifdef NDEBUG
#undef NDEBUG
#endif
#include "luca/reconciliation/trade_reconciliation.hpp"

#include <array>
#include <cassert>
#include <limits>
#include <type_traits>

using namespace luca;
using namespace std::chrono;
namespace {
const auto day1 = year{2026} / 9 / 28;
const auto day2 = year{2026} / 9 / 29;
const auto day3 = year{2026} / 9 / 30;
const Timestamp cutoff = sys_days{day3};
const auto usd = *Currency::from_code("USD");
const auto eur = *Currency::from_code("EUR");
const auto context = *TradeComparisonContext::create(cutoff, cutoff, day1, day3,
                                                     {AccountId{"a"}, AccountId{"b"}});
Provenance provenance(std::string id) {
  return *Provenance::create({SourceRecordId{std::move(id)}}, "synthetic", "1");
}
TradeKey key(std::string id = "external-1", std::string account = "a") {
  return *TradeKey::create(AccountId{std::move(account)}, std::move(id));
}
TradeTerms terms(std::string instrument = "MSFT", std::string quantity = "100",
                 std::string price = "50", Currency currency = usd,
                 year_month_day trade_date = day1, year_month_day settlement = day2) {
  return *TradeTerms::create(InstrumentId{std::move(instrument)}, *Quantity::parse(quantity),
                             *Price::parse(price), currency, trade_date, *SettlementDate::create(settlement));
}
EquityTrade event(std::string record = "record-1", std::string source = "source-original",
                  TradeTerms value = terms(), std::string account = "a") {
  return *EquityTrade::create(
      *EventHeader::create(EventId{std::move(record)}, AccountId{std::move(account)},
                           sys_days{value.trade_date()}, provenance(std::move(source))),
      value.instrument(), value.quantity(), value.price(), value.currency(), value.settlement_date());
}
TradeIdentityMapping mapping(std::string record = "record-1", TradeKey match = key(),
                             std::string economic = "economic-1") {
  return {EconomicEventId{std::move(economic)}, EventId{std::move(record)}, std::move(match),
          day1, provenance("explicit-mapping")};
}
std::vector<TradeProjectionRow> projected(TradeTerms value = terms(), TradeKey match = key()) {
  LifecycleLedger ledger;
  assert(ledger.accept(LifecycleRecordDraft::originate(
      EconomicEventId{"economic-1"}, sys_days{day1}, event("record-1", "source-original", value, match.account().value()))));
  std::array maps{mapping("record-1", match)};
  maps.front().trade_date = value.trade_date();
  auto rows = project_trades(ledger, maps, context);
  assert(rows);
  return *rows;  // Ledger destroyed; lineage must be owned.
}
TradeObservation observation(TradeTerms value = terms(), TradeKey match = key(),
                             std::string id = "observed-1",
                             TradeComparisonContext scope = context) {
  auto source = *SourceRecord::create(SourceId{"custodian"}, SourceRecordId{id}, match.external_trade_id(),
      cutoff, std::nullopt, *PayloadHash::create("synthetic", "hash-" + id), "trade.fixture");
  return *TradeObservation::create(std::move(match), std::move(value), std::move(scope),
                                   std::move(source), provenance(id));
}
void exact_and_each_field() {
  const auto expected = projected();
  const std::array observed{observation()};
  const auto report = reconcile_trades(expected, observed, context);
  assert(report && report->entries.size() == 1);
  const auto& match = report->entries.front();
  assert(match.kind == TradeComparisonKind::exact_match && match.differing_fields.empty());
  assert(match.expected->active_record().record_id() == EventId{"record-1"});
  assert(match.expected->economic_event_id() == EconomicEventId{"economic-1"});
  assert(match.expected->lineage().front().provenance() == provenance("source-original"));
  assert(match.expected->mapping_provenance() == provenance("explicit-mapping"));
  assert(match.observed->provenance() == provenance("observed-1"));
  assert(match.observed->source_record().payload_hash().value() == "hash-observed-1");
  assert(report == reconcile_trades(expected, observed, context));
  const std::array variants{
      terms("AAPL"), terms("MSFT", "-100"), terms("MSFT", "100", "50.00000001"),
      terms("MSFT", "100", "50", eur), terms("MSFT", "100", "50", usd, day2),
      terms("MSFT", "100", "50", usd, day1, day3)};
  const std::array fields{TradeField::instrument, TradeField::quantity, TradeField::price,
                          TradeField::currency, TradeField::trade_date, TradeField::settlement_date};
  for (std::size_t i = 0; i < fields.size(); ++i) {
    const std::array rows{observation(variants[i])};
    const auto mismatch = reconcile_trades(expected, rows, context);
    assert(mismatch && mismatch->entries.front().kind == TradeComparisonKind::field_mismatch);
    assert(mismatch->entries.front().differing_fields == std::vector{fields[i]});
  }
  const std::array all{observation(terms("AAPL", "-80", "55", eur, day2, day3))};
  const auto multi = reconcile_trades(expected, all, context);
  assert(multi && multi->entries.front().differing_fields == std::vector(fields.begin(), fields.end()));
  // Compare extremes without subtracting or multiplying fixed-width values.
  const auto large = projected(terms("MSFT", "92233720368.54775807", "0"));
  const std::array small{observation(terms("MSFT", "-92233720368.54775808", "0"))};
  assert(reconcile_trades(large, small, context)->entries.front().differing_fields == std::vector{TradeField::quantity});
}
void missing_unexpected_order_and_partition() {
  auto left = projected();
  // Different account + currency; same external ID is a distinct comparison key.
  LifecycleLedger ledger;
  assert(ledger.accept(LifecycleRecordDraft::originate(EconomicEventId{"economic-2"}, sys_days{day1},
      event("record-2", "source-2", terms("MSFT", "-10", "7", eur), "b"))));
  std::array maps{mapping("record-2", key("external-1", "b"), "economic-2")};
  const auto right = project_trades(ledger, maps, context);
  assert(right);
  left.push_back(right->front());
  std::vector observed{observation(terms("MSFT", "-10", "7", eur), key("external-1", "b"), "observed-2"),
                       observation(terms(), key("external-extra"), "observed-extra")};
  auto report = reconcile_trades(left, observed, context);
  assert(report && report->entries.size() == 3);
  assert(report->entries[0].kind == TradeComparisonKind::missing_observation);
  assert(report->entries[0].expected && !report->entries[0].observed);
  assert(report->entries[1].kind == TradeComparisonKind::unexpected_observation);
  assert(!report->entries[1].expected && report->entries[1].observed);
  assert(report->entries[2].kind == TradeComparisonKind::exact_match);
  std::reverse(left.begin(), left.end());
  std::reverse(observed.begin(), observed.end());
  assert(report == reconcile_trades(left, observed, context));
  const auto first_partition = reconcile_trades(std::span{&left[1], 1}, std::span{&observed[0], 1}, context);
  const auto second_partition = reconcile_trades(std::span{&left[0], 1}, std::span{&observed[1], 1}, context);
  auto combined = first_partition->entries;
  combined.insert(combined.end(), second_partition->entries.begin(), second_partition->entries.end());
  assert(combined == report->entries);  // Disjoint keys and identical policy/context only.
  assert(reconcile_trades({}, {}, context)->entries.empty());
}
void errors_are_atomic() {
  const auto expected = projected();
  const auto obs = observation();
  auto duplicate_expected = expected;
  duplicate_expected.push_back(expected.front());
  const std::array observed{obs};
  auto error = reconcile_trades(duplicate_expected, observed, context);
  assert(!error && error.error().code == TradeReconciliationErrorCode::duplicate_projection_key);
  std::vector duplicates{obs, obs};
  error = reconcile_trades(expected, duplicates, context);
  assert(!error && error.error().code == TradeReconciliationErrorCode::duplicate_observation_key);
  duplicates[1] = observation(terms("MSFT", "-100"));
  error = reconcile_trades(expected, duplicates, context);
  assert(!error && error.error().code == TradeReconciliationErrorCode::duplicate_observation_key);
  duplicates[1] = observation(terms(), key("other"));  // Same evidence claims two keys.
  error = reconcile_trades(expected, duplicates, context);
  assert(!error && error.error().code == TradeReconciliationErrorCode::ambiguous_observation_identity);
  auto ambiguous = expected;
  ambiguous.push_back(projected(terms(), key("other")).front());
  error = reconcile_trades(ambiguous, observed, context);
  assert(!error && error.error().code == TradeReconciliationErrorCode::ambiguous_projection_identity);
  for (int dimension = 0; dimension < 4; ++dimension) {
    const auto changed = *TradeComparisonContext::create(
        cutoff + nanoseconds{dimension == 0 ? 1 : 0}, cutoff + nanoseconds{dimension == 1 ? 1 : 0},
        day1, dimension == 2 ? day2 : day3,
        dimension == 3 ? std::vector{AccountId{"a"}} : std::vector{AccountId{"a"}, AccountId{"b"}});
    const std::array wrong_scope{observation(terms(), key(), "observed-1", changed)};
    error = reconcile_trades(expected, wrong_scope, context);
    assert(!error && error.error().code == TradeReconciliationErrorCode::context_mismatch);
    assert(error.error().side == TradeInputSide::observation);
    error = reconcile_trades(expected, {}, changed);
    assert(!error && error.error().side == TradeInputSide::projection);
  }
  assert(!TradeKey::create(AccountId{" a"}, "x"));
  assert(!TradeKey::create(AccountId{"a"}, ""));
  assert(!TradeTerms::create(InstrumentId{"MSFT"}, Quantity::from_scaled(0), *Price::parse("1"), usd, day1, *SettlementDate::create(day2)));
  assert(!TradeTerms::create(InstrumentId{"MSFT"}, *Quantity::parse("1"), *Price::parse("-1"), usd, day1, *SettlementDate::create(day2)));
  assert(!TradeComparisonContext::create(cutoff, cutoff, day3, day1, {AccountId{"a"}}));
  assert(!TradeComparisonContext::create(cutoff, cutoff, day1, day3, {}));
  assert(!TradeComparisonContext::create(cutoff, cutoff, day1, day3, {AccountId{"a"}, AccountId{"a"}}));
  assert(!TradeObservation::create(key(), terms(), context, obs.source_record(), provenance("wrong-evidence")));
}
void lifecycle_and_mapping() {
  LifecycleLedger ledger;
  assert(ledger.accept(LifecycleRecordDraft::originate(EconomicEventId{"economic-1"}, sys_days{day1}, event())));
  assert(ledger.accept(LifecycleRecordDraft::correct(EconomicEventId{"economic-1"}, EventId{"record-1"}, cutoff,
      event("record-2", "source-corrected", terms("MSFT", "80", "55")))));
  std::array maps{mapping("record-2")};
  auto rows = project_trades(ledger, maps, context);
  assert(rows && rows->size() == 1 && rows->front().lineage().size() == 2);
  assert(rows->front().lineage()[0].record_id() == EventId{"record-1"});
  assert(rows->front().lineage()[1].provenance() == provenance("source-corrected"));
  const std::array original{observation()};
  auto report = reconcile_trades(*rows, original, context);
  assert((report->entries.front().differing_fields == std::vector{TradeField::quantity, TradeField::price}));
  const std::array corrected{observation(terms("MSFT", "80", "55"), key(), "observed-corrected")};
  auto corrected_report = reconcile_trades(*rows, corrected, context);
  assert(corrected_report->entries.front().kind == TradeComparisonKind::exact_match);
  assert(report->entries.front().observed->source_record().id() != corrected_report->entries.front().observed->source_record().id());
  const auto earlier = *TradeComparisonContext::create(cutoff, cutoff - nanoseconds{1}, day1, day3,
                                                       {AccountId{"a"}, AccountId{"b"}});
  std::array old_map{mapping()};
  const auto before = project_trades(ledger, old_map, earlier);
  assert(before && before->front().terms().quantity() == *Quantity::parse("100"));
  assert(!project_trades(ledger, old_map, context));  // Stale active-record binding.
  assert(!project_trades(ledger, {}, context));       // Never infer an external ID.
  std::array duplicate_maps{maps[0], maps[0]};
  assert(project_trades(ledger, duplicate_maps, context).error().code == TradeReconciliationErrorCode::duplicate_mapping);
  std::array unused{maps[0], mapping("unknown", key("extra"), "unknown-economic")};
  assert(project_trades(ledger, unused, context).error().code == TradeReconciliationErrorCode::unused_mapping);
  // Cancellation removes the row but does not reinterpret an old statement.
  assert(ledger.accept(LifecycleRecordDraft::cancel(EventId{"record-3"}, EconomicEventId{"economic-1"},
      EventId{"record-2"}, AccountId{"a"}, cutoff, provenance("cancel-source"))));
  assert(project_trades(ledger, {}, context)->empty());
  assert(reconcile_trades({}, corrected, context)->entries.front().kind == TradeComparisonKind::unexpected_observation);
  // Already-produced rows/reports remain owned snapshots after ledger mutation.
  assert(rows->front().active_record().record_id() == EventId{"record-2"});
}
void reversal_evidence() {
  LifecycleLedger ledger;
  assert(ledger.accept(LifecycleRecordDraft::originate(EconomicEventId{"economic-1"}, sys_days{day1}, event())));
  assert(ledger.accept(LifecycleRecordDraft::reverse(EconomicEventId{"economic-reverse"}, EventId{"record-1"}, cutoff,
      event("record-reverse", "reverse-source", terms("MSFT", "-100")))));
  std::array maps{mapping(), mapping("record-reverse", key("reverse-external"), "economic-reverse")};
  auto rows = project_trades(ledger, maps, context);
  assert(rows && rows->size() == 2);
  assert(rows->back().reversal_target_lineage().size() == 1);
  assert(rows->back().reversal_target_lineage().front().provenance() == provenance("source-original"));
}
}  // namespace
int main() {
  static_assert(!std::is_same_v<TradeProjectionRow, TradeObservation>);
  static_assert(!std::is_convertible_v<TradeObservation, EconomicEvent>);
  static_assert(!std::is_convertible_v<TradeObservation, TradeProjectionRow>);
  exact_and_each_field();
  missing_unexpected_order_and_partition();
  errors_are_atomic();
  lifecycle_and_mapping();
  reversal_evidence();
}
