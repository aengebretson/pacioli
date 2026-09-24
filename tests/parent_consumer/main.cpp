#include <luca/portfolio.hpp>

#include <chrono>
#include <iostream>
#include <string>
#include <vector>

int main() {
  using namespace std::chrono_literals;

  const auto usd = luca::Currency::from_code("USD");
  if (!usd)
    return 1;
  const auto amount = luca::Money::parse("125.00", *usd);
  if (!amount)
    return 1;
  const auto provenance = luca::Provenance::create(
      std::vector{luca::SourceRecordId{"parent-consumer-source-1"}}, "parent-consumer", "1");
  if (!provenance)
    return 1;
  constexpr luca::Timestamp effective_at{1s};
  const auto header =
      luca::EventHeader::create(luca::EventId{"parent-deposit-1"},
                                luca::AccountId{"parent-account-1"}, effective_at, *provenance);
  if (!header)
    return 1;

  luca::Ledger ledger;
  const auto appended = ledger.append(luca::CashMovement::create(*header, *amount));
  if (!appended)
    return 2;

  const auto balances = luca::project_cash(
      ledger.entries(), luca::CashProjectionContext{effective_at, std::chrono::year{2026} /
                                                                      std::chrono::January / 1});
  if (!balances || balances->size() != 1)
    return 3;

  const auto &balance = balances->front();
  if (balance.amount().scaled_value() != 125'000'000 || balance.amount().currency() != *usd) {
    return 4;
  }

  const luca::PortfolioState state{{}, *balances, {}};
  const auto state_bytes = luca::serialization::canonical_bytes(state);
  const auto state_digest = luca::serialization::canonical_digest(state);
  const auto decoded_state = luca::serialization::decode_portfolio_state(state_bytes);
  if (state_bytes != luca::serialization::canonical_bytes(state) ||
      state_digest != luca::serialization::canonical_digest(state) || state_digest.size() != 64 ||
      !decoded_state || *decoded_state != state ||
      luca::serialization::canonical_bytes(*decoded_state) != state_bytes) {
    return 5;
  }

  const auto checkpoint_digest = luca::Sha256Digest::create(state_digest);
  luca::LifecycleLedger lifecycle;
  const auto accepted_prefix = lifecycle.accept(luca::LifecycleRecordDraft::originate(
      luca::EconomicEventId{"parent-deposit-economic"}, effective_at,
      luca::CashMovement::create(*header, *amount)));
  if (!accepted_prefix)
    return 6;
  const auto input_digest =
      luca::Sha256Digest::create(luca::serialization::canonical_digest(lifecycle));
  if (!checkpoint_digest || !input_digest)
    return 6;
  const auto projection = luca::CheckpointIdentity::create("parent.portfolio-state", "1");
  const auto policy = luca::CheckpointIdentity::create("parent.default-policy", "1");
  const auto partition =
      luca::AccountSetPartition::create(std::vector{luca::AccountId{"parent-account-1"}});
  const auto prefix = luca::CheckpointEventPrefix::create(
      1, 1, 1, luca::EventId{"parent-deposit-1"}, *input_digest);
  const auto settlement_as_of =
      luca::SettlementDate::create(std::chrono::year{2026} / std::chrono::January / 1);
  if (!projection || !policy || !partition || !prefix || !settlement_as_of)
    return 6;
  constexpr luca::Timestamp resume_through{2s};
  const auto context =
      luca::CheckpointEvaluationContext::create(resume_through, resume_through, *settlement_as_of);
  const auto watermark =
      luca::ResolvedEventWatermark::create(effective_at, 1, luca::EventId{"parent-deposit-1"});
  const auto lineage = luca::CheckpointLineage::create(
      std::vector{luca::EventId{"parent-deposit-1"}},
      std::vector{luca::EventId{"parent-deposit-1"}},
      std::vector{luca::SourceRecordId{"parent-consumer-source-1"}});
  if (!context || !watermark || !lineage) {
    return 6;
  }
  const auto manifest =
      luca::CheckpointManifest::create(*projection, "parent-engine-1", *policy, *partition, *prefix,
                                       *context, *checkpoint_digest, *watermark, *lineage);
  if (!manifest)
    return 6;
  const auto manifest_bytes = luca::serialization::canonical_bytes(*manifest);
  const auto decoded_manifest = luca::serialization::decode_checkpoint_manifest(manifest_bytes);
  if (!decoded_manifest || *decoded_manifest != *manifest ||
      luca::serialization::canonical_bytes(*manifest) !=
          luca::serialization::canonical_bytes(*decoded_manifest) ||
      luca::serialization::canonical_digest(*manifest).size() != 64) {
    return 6;
  }
  const auto manifest_digest =
      luca::Sha256Digest::create(luca::serialization::canonical_digest(*manifest));
  if (!manifest_digest)
    return 7;
  const auto resume = luca::CheckpointResumeRequest::create(
      luca::CheckpointResumeRequest::schema_version,
      luca::CheckpointResumeRequest::serialization_version, *manifest_digest, *projection,
      "parent-engine-1", *policy, *partition, *context, *prefix, *checkpoint_digest);
  if (!resume || luca::serialization::canonical_digest(*resume).size() != 64 ||
      luca::serialization::canonical_bytes(*resume) !=
          luca::serialization::canonical_bytes(*resume)) {
    return 7;
  }

  const auto suffix_header =
      luca::EventHeader::create(luca::EventId{"parent-deposit-2"},
                                luca::AccountId{"parent-account-1"}, resume_through, *provenance);
  const auto suffix_amount = luca::Money::parse("25.00", *usd);
  if (!suffix_header || !suffix_amount ||
      !lifecycle
           .accept(luca::LifecycleRecordDraft::originate(
               luca::EconomicEventId{"parent-deposit-2-economic"}, resume_through,
               luca::CashMovement::create(*suffix_header, *suffix_amount)))
           .has_value()) {
    return 8;
  }
  const auto applied = luca::apply_checkpoint_suffix(
      *resume, *manifest, state, lifecycle.records().first(1), lifecycle.records().subspan(1));
  if (!applied || applied->settled_cash().size() != 1 ||
      applied->settled_cash().front().amount().scaled_value() != 150'000'000) {
    return 8;
  }

  std::cout << "cash_scaled=" << balance.amount().scaled_value()
            << " currency=" << balance.amount().currency().code()
            << " state_digest=" << state_digest
            << " resumed_cash_scaled=" << applied->settled_cash().front().amount().scaled_value()
            << '\n';
  return 0;
}
