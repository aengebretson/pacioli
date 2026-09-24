#include "luca/portfolio.hpp"

#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <expected>
#include <optional>
#include <ranges>
#include <source_location>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using namespace std::chrono_literals;
using namespace luca;

void check(bool condition, const std::source_location location = std::source_location::current()) {
  if (!condition) {
    std::fprintf(stderr, "check failed at %s:%u\n", location.file_name(), location.line());
    std::abort();
  }
}

template <class Value, class Error>
Value require(std::expected<Value, Error> result,
              const std::source_location location = std::source_location::current()) {
  check(result.has_value(), location);
  return std::move(*result);
}

template <class Value>
void expect_error(const std::expected<Value, CheckpointResumeError> &result,
                  CheckpointResumeDiagnosticCategory category,
                  const std::source_location location = std::source_location::current()) {
  check(!result.has_value(), location);
  check(result.error().category() == category, location);
  check(result.error().category_name() == category_name(category), location);
  check(!result.error().message().empty(), location);
}

Timestamp timestamp(int year, unsigned month, unsigned day, std::chrono::nanoseconds time) {
  return Timestamp{std::chrono::sys_days{std::chrono::year{year} / std::chrono::month{month} /
                                         std::chrono::day{day}} +
                   time};
}

SettlementDate date(int year, unsigned month, unsigned day) {
  return require(SettlementDate::create(std::chrono::year{year} / std::chrono::month{month} /
                                        std::chrono::day{day}));
}

Currency usd() { return require(Currency::from_code("USD")); }

Sha256Digest digest(std::string_view value) { return require(Sha256Digest::create(value)); }

CheckpointIdentity identity(std::string_view id, std::string_view version) {
  return require(CheckpointIdentity::create(id, version));
}

Provenance provenance(std::string_view source, std::string_view transformation,
                      std::optional<std::string> metadata = std::nullopt) {
  return require(Provenance::create({SourceRecordId{std::string{source}}},
                                    std::string{transformation}, "1", std::move(metadata)));
}

EconomicEvent cash_event(std::string_view record_id, std::string_view account,
                         Timestamp effective_at, std::string_view amount, std::string_view source,
                         std::string_view transformation = "normalize-cash-movement",
                         std::optional<std::string> metadata = std::nullopt) {
  const auto event_provenance = provenance(source, transformation, std::move(metadata));
  const auto header =
      require(EventHeader::create(EventId{std::string{record_id}}, AccountId{std::string{account}},
                                  effective_at, event_provenance));
  return CashMovement::create(header, require(Money::parse(amount, usd())));
}

EconomicEvent trade_event(std::string_view record_id, std::string_view account,
                          Timestamp effective_at, std::string_view quantity, std::string_view price,
                          std::string_view source, SettlementDate settlement_date,
                          std::optional<std::string> metadata = std::nullopt) {
  const auto event_provenance = provenance(source, "normalize-equity-trade", std::move(metadata));
  const auto header =
      require(EventHeader::create(EventId{std::string{record_id}}, AccountId{std::string{account}},
                                  effective_at, event_provenance));
  return require(EquityTrade::create(header, InstrumentId{"instrument-xyz"},
                                     require(Quantity::parse(quantity)),
                                     require(Price::parse(price)), usd(), settlement_date));
}

void accept(LifecycleLedger &ledger, const LifecycleRecordDraft &draft) {
  check(ledger.accept(draft).has_value());
}

void append_fixture_prefix(LifecycleLedger &ledger) {
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"economic-cash-origin"}, timestamp(2026, 1, 2, 10h),
                     cash_event("record-cash-origin", "acct-main", timestamp(2026, 1, 2, 9h),
                                "100000", "source-cash-origin")));
  accept(ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"economic-buy-origin"}, timestamp(2026, 1, 3, 11h),
             trade_event("record-buy-origin", "acct-main", timestamp(2026, 1, 3, 10h), "80", "55",
                         "source-buy-origin", date(2026, 1, 8), "allocation=complete")));
}

LifecycleLedger fixture_ledger() {
  LifecycleLedger ledger;
  append_fixture_prefix(ledger);
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"economic-cash-append"}, timestamp(2026, 1, 4, 11h),
                     cash_event("record-cash-append", "acct-main", timestamp(2026, 1, 4, 9h),
                                "2000", "source-cash-append")));
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"economic-sell-append"}, timestamp(2026, 1, 5, 11h),
                     trade_event("record-sell-append", "acct-main", timestamp(2026, 1, 5, 10h),
                                 "-20", "60", "source-sell-append", date(2026, 1, 9))));
  return ledger;
}

PortfolioState fixture_state(std::string_view account = "acct-main") {
  return PortfolioState{
      {Position{PositionKey{AccountId{std::string{account}}, InstrumentId{"instrument-xyz"}},
                require(Quantity::parse("80"))}},
      {CashBalance{AccountId{std::string{account}}, require(Money::parse("100000", usd()))}},
      {SettlementObligation{AccountId{std::string{account}}, date(2026, 1, 8),
                            SettlementDirection::payable, require(Money::parse("4400", usd()))}}};
}

CheckpointEvaluationContext fixture_context() {
  const auto rounding = require(CheckpointInput::create(
      "luca.half-even", "1",
      digest("b2be4d87b2f322900cd752bd7db0be406bdc41650456d89a535719d7c4c45205")));
  return require(CheckpointEvaluationContext::create(timestamp(2026, 1, 6, 23h + 59min + 59s),
                                                     timestamp(2026, 1, 6, 23h + 59min + 59s),
                                                     date(2026, 1, 6), {}, {}, {}, {rounding}, {}));
}

CheckpointEventPrefix
fixture_prefix(std::string_view input_digest =
                   "9fe51890a95a2d82e46606e6339d3599e368d134d9f2054903b6fae62f934e84") {
  return require(
      CheckpointEventPrefix::create(1, 2, 2, EventId{"record-buy-origin"}, digest(input_digest)));
}

CheckpointLineage fixture_lineage() {
  return require(CheckpointLineage::create(
      {EventId{"record-cash-origin"}, EventId{"record-buy-origin"}},
      {EventId{"record-cash-origin"}, EventId{"record-buy-origin"}},
      {SourceRecordId{"source-cash-origin"}, SourceRecordId{"source-buy-origin"}}));
}

CheckpointManifest
make_manifest(const AccountSetPartition &partition = require(AccountSetPartition::create({AccountId{
                  "acct-main"}})),
              const CheckpointEventPrefix &prefix = fixture_prefix(),
              const CheckpointEvaluationContext &context = fixture_context(),
              const Sha256Digest &state_digest =
                  digest("72c3555ab26a7a4ec42f1024c0404e6b0094510908783e9e1069141f6a88a738"),
              const CheckpointIdentity &projection = identity("luca.portfolio-state", "1"),
              std::string_view engine = "luca-engine-1",
              const CheckpointIdentity &policy = identity("luca.portfolio-default", "1")) {
  const auto watermark = require(
      ResolvedEventWatermark::create(timestamp(2026, 1, 3, 10h), 2, EventId{"record-buy-origin"}));
  return require(CheckpointManifest::create(projection, engine, policy, partition, prefix, context,
                                            state_digest, watermark, fixture_lineage()));
}

struct RequestOverrides {
  std::optional<Sha256Digest> manifest_digest;
  std::optional<CheckpointIdentity> projection;
  std::optional<std::string> engine;
  std::optional<CheckpointIdentity> policy;
  std::optional<AccountSetPartition> partition;
  std::optional<CheckpointEvaluationContext> context;
  std::optional<CheckpointEventPrefix> prefix;
  std::optional<Sha256Digest> state_digest;
};

CheckpointResumeRequest make_request(const CheckpointManifest &manifest,
                                     const RequestOverrides &overrides = {}) {
  const auto manifest_digest =
      overrides.manifest_digest.value_or(digest(serialization::canonical_digest(manifest)));
  return require(CheckpointResumeRequest::create(
      CheckpointResumeRequest::schema_version, CheckpointResumeRequest::serialization_version,
      manifest_digest, overrides.projection.value_or(manifest.projection()),
      overrides.engine.value_or(manifest.engine_version()),
      overrides.policy.value_or(manifest.policy()),
      overrides.partition.value_or(manifest.partition()),
      overrides.context.value_or(manifest.evaluation_context()),
      overrides.prefix.value_or(manifest.event_prefix()),
      overrides.state_digest.value_or(manifest.canonical_state_digest())));
}

template <class Value>
concept CanonicallySerializable = requires(const Value &value) {
  { serialization::canonical_bytes(value) } -> std::same_as<serialization::CanonicalBytes>;
  { serialization::canonical_digest(value) } -> std::same_as<std::string>;
};

static_assert(CanonicallySerializable<CheckpointResumeRequest>);
static_assert(CheckpointResumeRequest::schema_version == "luca.checkpoint-resume.v1");
static_assert(CheckpointResumeRequest::serialization_version == "luca.canonical-bytes.v1");

void compatible_fixture_is_deterministic_and_non_mutating() {
  const auto ledger = fixture_ledger();
  const auto state = fixture_state();
  const auto manifest = make_manifest();
  const auto request = make_request(manifest);
  const auto prefix = ledger.records().first(2);
  const auto suffix = ledger.records().subspan(2);
  const auto original_state = state;
  const std::vector<LifecycleRecord> original_records{ledger.records().begin(),
                                                      ledger.records().end()};

  check(
      check_checkpoint_resume_compatibility(request, manifest, state, prefix, suffix).has_value());
  check(
      check_checkpoint_resume_compatibility(request, manifest, state, prefix, suffix).has_value());
  check(serialization::canonical_digest(request) ==
        "96c17cdba8afaf68d801f2db4e110b92f4439d21f6d8e2152d3057f2b5a71b43");
  check(serialization::canonical_bytes(request) == serialization::canonical_bytes(request));
  check(state == original_state);
  check(std::ranges::equal(ledger.records(), original_records));
}

void request_factory_rejects_unsupported_versions_without_consuming_inputs() {
  const auto manifest = make_manifest();
  const auto manifest_digest = digest(serialization::canonical_digest(manifest));
  const std::vector<AccountId> caller_keys{AccountId{"acct-main"}};
  const auto partition = require(AccountSetPartition::create(caller_keys));

  expect_error(CheckpointResumeRequest::create(
                   "luca.checkpoint-resume.v2", CheckpointResumeRequest::serialization_version,
                   manifest_digest, manifest.projection(), manifest.engine_version(),
                   manifest.policy(), partition, manifest.evaluation_context(),
                   manifest.event_prefix(), manifest.canonical_state_digest()),
               CheckpointResumeDiagnosticCategory::unsupported_version);
  expect_error(CheckpointResumeRequest::create(
                   CheckpointResumeRequest::schema_version, "luca.canonical-bytes.v2",
                   manifest_digest, manifest.projection(), manifest.engine_version(),
                   manifest.policy(), partition, manifest.evaluation_context(),
                   manifest.event_prefix(), manifest.canonical_state_digest()),
               CheckpointResumeDiagnosticCategory::unsupported_version);
  expect_error(
      CheckpointResumeRequest::create(CheckpointResumeRequest::schema_version,
                                      CheckpointResumeRequest::serialization_version,
                                      manifest_digest, manifest.projection(), "", manifest.policy(),
                                      partition, manifest.evaluation_context(),
                                      manifest.event_prefix(), manifest.canonical_state_digest()),
      CheckpointResumeDiagnosticCategory::schema_shape);
  check(caller_keys == std::vector<AccountId>{AccountId{"acct-main"}});
}

void digest_and_repeated_identity_mutations_are_rejected() {
  const auto ledger = fixture_ledger();
  const auto state = fixture_state();
  const auto manifest = make_manifest();
  const auto prefix = ledger.records().first(2);
  const auto suffix = ledger.records().subspan(2);
  const auto zero = digest(std::string(64, '0'));

  RequestOverrides changed_manifest_digest;
  changed_manifest_digest.manifest_digest = zero;
  expect_error(
      check_checkpoint_resume_compatibility(make_request(manifest, changed_manifest_digest),
                                            manifest, state, prefix, suffix),
      CheckpointResumeDiagnosticCategory::digest_mismatch);
  RequestOverrides changed_state_digest;
  changed_state_digest.state_digest = zero;
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_state_digest),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::digest_mismatch);
  RequestOverrides changed_projection;
  changed_projection.projection = identity("luca.portfolio-state", "2");
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_projection),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_projection);
  RequestOverrides changed_engine;
  changed_engine.engine = "luca-engine-2";
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_engine),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_engine);
  RequestOverrides changed_policy;
  changed_policy.policy = identity("luca.portfolio-default", "2");
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_policy),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_policy);

  const auto other_partition = require(AccountSetPartition::create({AccountId{"acct-other"}}));
  RequestOverrides changed_partition;
  changed_partition.partition = other_partition;
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_partition),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_partition);

  const auto changed_context = require(CheckpointEvaluationContext::create(
      timestamp(2026, 1, 7, 23h + 59min + 59s), manifest.evaluation_context().economic_as_of(),
      date(2026, 1, 6), {}, {}, {},
      std::vector<CheckpointInput>{manifest.evaluation_context().rounding_inputs().begin(),
                                   manifest.evaluation_context().rounding_inputs().end()},
      {}));
  RequestOverrides changed_context_request;
  changed_context_request.context = changed_context;
  expect_error(
      check_checkpoint_resume_compatibility(make_request(manifest, changed_context_request),
                                            manifest, state, prefix, suffix),
      CheckpointResumeDiagnosticCategory::incompatible_context);

  const auto changed_prefix = require(CheckpointEventPrefix::create(
      1, 1, 1, EventId{"record-cash-origin"}, digest(std::string(64, 'f'))));
  RequestOverrides changed_prefix_request;
  changed_prefix_request.prefix = changed_prefix;
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest, changed_prefix_request),
                                                     manifest, state, prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_prefix);
}

void supplied_prefix_and_state_digests_are_recomputed() {
  auto altered_ledger = fixture_ledger();
  LifecycleLedger changed_prefix_ledger;
  accept(changed_prefix_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"economic-cash-origin"}, timestamp(2026, 1, 2, 10h),
             cash_event("record-cash-origin", "acct-main", timestamp(2026, 1, 2, 9h), "99999",
                        "source-cash-origin")));
  accept(changed_prefix_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"economic-buy-origin"}, timestamp(2026, 1, 3, 11h),
             trade_event("record-buy-origin", "acct-main", timestamp(2026, 1, 3, 10h), "80", "55",
                         "source-buy-origin", date(2026, 1, 8), "allocation=complete")));
  const auto manifest = make_manifest();
  const auto request = make_request(manifest);
  expect_error(check_checkpoint_resume_compatibility(request, manifest, fixture_state(),
                                                     changed_prefix_ledger.records(),
                                                     altered_ledger.records().subspan(2)),
               CheckpointResumeDiagnosticCategory::digest_mismatch);

  const auto original_state = fixture_state();
  auto changed_state = original_state;
  changed_state = PortfolioState{
      {Position{PositionKey{AccountId{"acct-main"}, InstrumentId{"instrument-xyz"}},
                require(Quantity::parse("79"))}},
      std::vector<CashBalance>{original_state.settled_cash().begin(),
                               original_state.settled_cash().end()},
      std::vector<SettlementObligation>{original_state.open_settlement_obligations().begin(),
                                        original_state.open_settlement_obligations().end()}};
  expect_error(check_checkpoint_resume_compatibility(request, manifest, changed_state,
                                                     altered_ledger.records().first(2),
                                                     altered_ledger.records().subspan(2)),
               CheckpointResumeDiagnosticCategory::digest_mismatch);

  const auto bad_prefix = fixture_prefix(std::string(64, 'f'));
  const auto bad_manifest =
      make_manifest(require(AccountSetPartition::create({AccountId{"acct-main"}})), bad_prefix);
  expect_error(check_checkpoint_resume_compatibility(
                   make_request(bad_manifest), bad_manifest, fixture_state(),
                   altered_ledger.records().first(2), altered_ledger.records().subspan(2)),
               CheckpointResumeDiagnosticCategory::digest_mismatch);
}

void partition_membership_is_checked_for_prefix_state_and_suffix() {
  const auto ledger = fixture_ledger();
  const auto prefix = ledger.records().first(2);
  const auto suffix = ledger.records().subspan(2);

  const auto other_partition = require(AccountSetPartition::create({AccountId{"acct-other"}}));
  const auto prefix_outside_manifest = make_manifest(other_partition);
  expect_error(check_checkpoint_resume_compatibility(make_request(prefix_outside_manifest),
                                                     prefix_outside_manifest, fixture_state(),
                                                     prefix, suffix),
               CheckpointResumeDiagnosticCategory::incompatible_partition);

  const auto state_outside = fixture_state("acct-other");
  const auto state_outside_digest = digest(serialization::canonical_digest(state_outside));
  const auto state_outside_manifest =
      make_manifest(require(AccountSetPartition::create({AccountId{"acct-main"}})),
                    fixture_prefix(), fixture_context(), state_outside_digest);
  expect_error(check_checkpoint_resume_compatibility(make_request(state_outside_manifest),
                                                     state_outside_manifest, state_outside, prefix,
                                                     suffix),
               CheckpointResumeDiagnosticCategory::incompatible_partition);

  LifecycleLedger suffix_outside_ledger;
  append_fixture_prefix(suffix_outside_ledger);
  accept(suffix_outside_ledger, LifecycleRecordDraft::originate(
                                    EconomicEventId{"economic-outside"}, timestamp(2026, 1, 4, 11h),
                                    cash_event("record-outside", "acct-other",
                                               timestamp(2026, 1, 4, 9h), "1", "source-outside")));
  const auto manifest = make_manifest();
  expect_error(check_checkpoint_resume_compatibility(make_request(manifest), manifest,
                                                     fixture_state(),
                                                     suffix_outside_ledger.records().first(2),
                                                     suffix_outside_ledger.records().subspan(2)),
               CheckpointResumeDiagnosticCategory::incompatible_partition);
}

void suffix_continuity_is_required() {
  const auto ledger = fixture_ledger();
  const auto manifest = make_manifest();
  const auto request = make_request(manifest);
  expect_error(check_checkpoint_resume_compatibility(request, manifest, fixture_state(),
                                                     ledger.records().first(2), {}),
               CheckpointResumeDiagnosticCategory::prefix_continuity);
  expect_error(check_checkpoint_resume_compatibility(request, manifest, fixture_state(),
                                                     ledger.records().first(2),
                                                     ledger.records().subspan(3)),
               CheckpointResumeDiagnosticCategory::prefix_continuity);
}

LifecycleLedger relationship_ledger(std::string_view target_account,
                                    std::string_view target_economic_id,
                                    bool add_unrelated_before_correction = false) {
  LifecycleLedger ledger;
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"filler-economic-1"}, timestamp(2026, 1, 1, 1h),
                     cash_event("filler-record-1", "acct-main", timestamp(2026, 1, 1, 1h), "1",
                                "filler-source-1")));
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"filler-economic-2"}, timestamp(2026, 1, 2, 1h),
                     cash_event("filler-record-2", "acct-main", timestamp(2026, 1, 2, 1h), "1",
                                "filler-source-2")));
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{std::string{target_economic_id}}, timestamp(2026, 1, 4, 10h),
                     cash_event("record-cash-append", target_account, timestamp(2026, 1, 4, 9h),
                                "2000", "source-cash-append")));
  if (add_unrelated_before_correction) {
    accept(ledger, LifecycleRecordDraft::originate(
                       EconomicEventId{"unrelated-economic"}, timestamp(2026, 1, 4, 11h),
                       cash_event("unrelated-record", "acct-main", timestamp(2026, 1, 4, 10h), "2",
                                  "unrelated-source")));
  }
  accept(ledger,
         LifecycleRecordDraft::correct(
             EconomicEventId{std::string{target_economic_id}}, EventId{"record-cash-append"},
             timestamp(2026, 1, 5, 10h),
             cash_event(add_unrelated_before_correction ? "second-correction" : "first-correction",
                        target_account, timestamp(2026, 1, 5, 9h), "2100",
                        add_unrelated_before_correction ? "second-correction-source"
                                                        : "first-correction-source")));
  return ledger;
}

void causal_account_event_and_successor_rules_are_checked() {
  const auto fixture = fixture_ledger();
  const auto prefix = fixture.records().first(2);
  const auto main_manifest = make_manifest();

  const auto cross_account = relationship_ledger("acct-other", "economic-cash-append");
  std::vector<LifecycleRecord> cross_account_suffix{fixture.records()[2],
                                                    cross_account.records()[3]};
  const auto two_account_partition =
      require(AccountSetPartition::create({AccountId{"acct-main"}, AccountId{"acct-other"}}));
  const auto two_account_manifest = make_manifest(two_account_partition);
  expect_error(check_checkpoint_resume_compatibility(make_request(two_account_manifest),
                                                     two_account_manifest, fixture_state(), prefix,
                                                     cross_account_suffix),
               CheckpointResumeDiagnosticCategory::incompatible_account);

  const auto changed_identity = relationship_ledger("acct-main", "different-economic-id");
  std::vector<LifecycleRecord> changed_identity_suffix{fixture.records()[2],
                                                       changed_identity.records()[3]};
  expect_error(check_checkpoint_resume_compatibility(make_request(main_manifest), main_manifest,
                                                     fixture_state(), prefix,
                                                     changed_identity_suffix),
               CheckpointResumeDiagnosticCategory::incompatible_event_relationship);

  const auto first_successor = relationship_ledger("acct-main", "economic-cash-append");
  LifecycleLedger unrelated_ledger;
  append_fixture_prefix(unrelated_ledger);
  accept(unrelated_ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"unrelated-suffix-economic"}, timestamp(2026, 1, 4, 10h),
             cash_event("unrelated-suffix-record", "acct-main", timestamp(2026, 1, 4, 9h), "1",
                        "unrelated-suffix-source")));
  std::vector<LifecycleRecord> missing_target_suffix{unrelated_ledger.records()[2],
                                                     first_successor.records()[3]};
  expect_error(check_checkpoint_resume_compatibility(make_request(main_manifest), main_manifest,
                                                     fixture_state(), prefix,
                                                     missing_target_suffix),
               CheckpointResumeDiagnosticCategory::incompatible_event_relationship);

  const auto second_successor = relationship_ledger("acct-main", "economic-cash-append", true);
  std::vector<LifecycleRecord> conflicting_suffix{
      fixture.records()[2], first_successor.records()[3], second_successor.records()[4]};
  expect_error(check_checkpoint_resume_compatibility(make_request(main_manifest), main_manifest,
                                                     fixture_state(), prefix, conflicting_suffix),
               CheckpointResumeDiagnosticCategory::conflicting_lifecycle_successor);
}

void prefix_targets_and_late_payloads_require_rebuild() {
  const auto test_prefix_target = [](LifecycleRecordDraft suffix_draft) {
    LifecycleLedger ledger;
    append_fixture_prefix(ledger);
    accept(ledger, suffix_draft);
    const auto manifest = make_manifest();
    expect_error(check_checkpoint_resume_compatibility(make_request(manifest), manifest,
                                                       fixture_state(), ledger.records().first(2),
                                                       ledger.records().subspan(2)),
                 CheckpointResumeDiagnosticCategory::late_lifecycle_knowledge);
  };

  test_prefix_target(LifecycleRecordDraft::correct(
      EconomicEventId{"economic-cash-origin"}, EventId{"record-cash-origin"},
      timestamp(2026, 1, 4, 11h),
      cash_event("late-correction", "acct-main", timestamp(2026, 1, 4, 9h), "120000",
                 "late-correction-source")));
  test_prefix_target(LifecycleRecordDraft::cancel(
      EventId{"late-cancellation"}, EconomicEventId{"economic-cash-origin"},
      EventId{"record-cash-origin"}, AccountId{"acct-main"}, timestamp(2026, 1, 4, 11h),
      provenance("late-cancellation-source", "normalize-cash-cancellation")));
  test_prefix_target(LifecycleRecordDraft::reverse(
      EconomicEventId{"economic-cash-reversal"}, EventId{"record-cash-origin"},
      timestamp(2026, 1, 4, 11h),
      cash_event("late-reversal", "acct-main", timestamp(2026, 1, 4, 9h), "-100000",
                 "late-reversal-source")));

  LifecycleLedger watermark_ledger;
  append_fixture_prefix(watermark_ledger);
  accept(watermark_ledger, LifecycleRecordDraft::originate(
                               EconomicEventId{"economic-at-watermark"}, timestamp(2026, 1, 4, 11h),
                               cash_event("record-at-watermark", "acct-main",
                                          timestamp(2026, 1, 3, 9h), "1", "source-at-watermark")));
  const auto manifest = make_manifest();
  expect_error(check_checkpoint_resume_compatibility(
                   make_request(manifest), manifest, fixture_state(),
                   watermark_ledger.records().first(2), watermark_ledger.records().subspan(2)),
               CheckpointResumeDiagnosticCategory::late_lifecycle_knowledge);
}

void integrated_late_correction_fixture_is_rejected() {
  LifecycleLedger ledger;
  accept(ledger, LifecycleRecordDraft::originate(
                     EconomicEventId{"economic-cash-deposit"}, timestamp(2026, 2, 1, 10h),
                     cash_event("record-cash-1000", "acct-late", timestamp(2026, 2, 1, 9h), "1000",
                                "source-cash-1000")));
  accept(ledger, LifecycleRecordDraft::correct(
                     EconomicEventId{"economic-cash-deposit"}, EventId{"record-cash-1000"},
                     timestamp(2026, 2, 3, 10h),
                     cash_event("record-cash-1200-correction", "acct-late",
                                timestamp(2026, 2, 1, 9h), "1200", "source-cash-1200-correction",
                                "normalize-cash-correction", "replacement-not-delta")));
  const PortfolioState state{
      {}, {CashBalance{AccountId{"acct-late"}, require(Money::parse("1000", usd()))}}, {}};
  const auto partition = require(AccountSetPartition::create({AccountId{"acct-late"}}));
  const auto prefix = require(CheckpointEventPrefix::create(
      1, 1, 1, EventId{"record-cash-1000"},
      digest("4e85a46707eb41302e7ed9dedc43e501e0c8953647683b14b26f016eb95dc2e8")));
  const auto context = require(CheckpointEvaluationContext::create(
      timestamp(2026, 2, 5, 23h + 59min + 59s), timestamp(2026, 2, 5, 23h + 59min + 59s),
      date(2026, 2, 5)));
  const auto watermark = require(
      ResolvedEventWatermark::create(timestamp(2026, 2, 1, 9h), 1, EventId{"record-cash-1000"}));
  const auto lineage = require(CheckpointLineage::create({EventId{"record-cash-1000"}},
                                                         {EventId{"record-cash-1000"}},
                                                         {SourceRecordId{"source-cash-1000"}}));
  const auto manifest = require(CheckpointManifest::create(
      identity("luca.portfolio-state", "1"), "luca-engine-1",
      identity("luca.portfolio-default", "1"), partition, prefix, context,
      digest("bef57f357556b13f7473f82ebede95549e575c136b0b664940422193506f4c77"), watermark,
      lineage));
  check(serialization::canonical_digest(manifest) ==
        "d16409446bcb09ec63389d907a84d0a4dcd673fbd24849b67a3fef6c72199c38");
  const auto request = make_request(manifest);
  expect_error(check_checkpoint_resume_compatibility(request, manifest, state,
                                                     ledger.records().first(1),
                                                     ledger.records().subspan(1)),
               CheckpointResumeDiagnosticCategory::late_lifecycle_knowledge);
}

} // namespace

int main() {
  compatible_fixture_is_deterministic_and_non_mutating();
  request_factory_rejects_unsupported_versions_without_consuming_inputs();
  digest_and_repeated_identity_mutations_are_rejected();
  supplied_prefix_and_state_digests_are_recomputed();
  partition_membership_is_checked_for_prefix_state_and_suffix();
  suffix_continuity_is_required();
  causal_account_event_and_successor_rules_are_checked();
  prefix_targets_and_late_payloads_require_rebuild();
  integrated_late_correction_fixture_is_rejected();
}
