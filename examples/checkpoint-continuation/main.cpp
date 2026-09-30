#include "luca/portfolio/checkpoint_result.hpp"

#include <chrono>
#include <iostream>
#include <string>

// Bounded synthetic evidence; no storage, transport, or external context lookup.
int main() {
  using namespace luca;
  using namespace std::chrono_literals;
  const auto day = std::chrono::sys_days{2026y / 1 / 1};
  const auto usd = Currency::from_code("USD").value();
  const auto context = CheckpointEvaluationContext::create(
      Timestamp{day + std::chrono::days{10}}, Timestamp{day + std::chrono::days{10}}, SettlementDate::create(2026y / 1 / 11).value()).value();
  LifecycleLedger ledger;
  const auto append = [&](int index, std::string_view amount) {
    const auto id = std::to_string(index);
    const auto provenance = Provenance::create({SourceRecordId{"source-" + id}}, "example", "1").value();
    const auto header = EventHeader::create(EventId{"record-" + id}, AccountId{"account"},
        Timestamp{day + std::chrono::days{index}}, provenance).value();
    return ledger.accept(LifecycleRecordDraft::originate(
        EconomicEventId{"economic-" + id}, Timestamp{day + std::chrono::days{index}},
        CashMovement::create(header, Money::parse(amount, usd).value()))).has_value();
  };
  if (!append(1, "1000")) return 1;
  const auto resolution = ledger.resolve(context.recorded_through(), context.economic_as_of());
  auto projected = project_lifecycle(resolution,
      LifecycleProjectionContext{context.economic_as_of(), context.settlement_as_of_date().value()});
  if (!projected.positions || !projected.settled_cash || !projected.open_settlement_obligations) return 1;
  PortfolioState state{std::move(*projected.positions), std::move(*projected.settled_cash),
                       std::move(*projected.open_settlement_obligations)};
  const auto prefix = CheckpointEventPrefix::create(1, 1, 1, EventId{"record-1"},
      Sha256Digest::create(serialization::canonical_digest(ledger)).value()).value();
  auto manifest = CheckpointManifest::create(
      CheckpointIdentity::create("luca.portfolio-state", "1").value(), "luca-engine-1",
      CheckpointIdentity::create("luca.portfolio-default", "1").value(),
      AccountSetPartition::create({AccountId{"account"}}).value(), prefix, context,
      Sha256Digest::create(serialization::canonical_digest(state)).value(),
      ResolvedEventWatermark::create(Timestamp{day + std::chrono::days{1}}, 1, EventId{"record-1"}).value(),
      CheckpointLineage::create({EventId{"record-1"}}, {EventId{"record-1"}},
                               {SourceRecordId{"source-1"}}).value()).value();

  // Each continuation binds a fresh request to the exact returned manifest.
  // The application owns persistence of the accepted records and result bundle.
  for (int index = 2; index <= 3; ++index) {
    const auto boundary = ledger.size();
    if (!append(index, index == 2 ? "100" : "-25")) return 1;
    const auto request = CheckpointResumeRequest::create(
        CheckpointResumeRequest::schema_version, CheckpointResumeRequest::serialization_version,
        Sha256Digest::create(serialization::canonical_digest(manifest)).value(),
        manifest.projection(), manifest.engine_version(), manifest.policy(), manifest.partition(),
        manifest.evaluation_context(), manifest.event_prefix(), manifest.canonical_state_digest()).value();
    auto continued = apply_checkpoint_suffix_with_manifest(request, manifest, state,
        ledger.records().first(boundary), ledger.records().subspan(boundary));
    if (!continued) {
      std::cerr << "Checkpoint continuation failed; error alternative " << continued.error().index() << '\n';
      return 1;
    }
    state = std::move(continued->state);
    manifest = std::move(continued->manifest);
  }
  std::cout << "Accepted records: " << manifest.event_prefix().record_count() << '\n'
            << "State SHA-256: " << manifest.canonical_state_digest().value() << '\n'
            << "Manifest SHA-256: " << serialization::canonical_digest(manifest) << '\n';
}
