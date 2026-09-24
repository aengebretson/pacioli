#include "luca/portfolio.hpp"

#include <algorithm>
#include <chrono>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <expected>
#include <initializer_list>
#include <iostream>
#include <source_location>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using namespace std::chrono_literals;
using luca::AccountId;
using luca::AccountSetPartition;
using luca::CheckpointDiagnosticCategory;
using luca::CheckpointEvaluationContext;
using luca::CheckpointEventPrefix;
using luca::CheckpointIdentity;
using luca::CheckpointInput;
using luca::CheckpointLineage;
using luca::CheckpointManifest;
using luca::EventId;
using luca::ResolvedEventWatermark;
using luca::SettlementDate;
using luca::Sha256Digest;
using luca::SourceRecordId;
using luca::Timestamp;
using luca::serialization::canonical_bytes;
using luca::serialization::canonical_digest;
using luca::serialization::CanonicalBytes;

void check(bool condition, const std::source_location location = std::source_location::current()) {
  if (!condition) {
    std::cerr << "check failed at " << location.file_name() << ':' << location.line() << '\n';
    std::abort();
  }
}

template <class Value, class Error>
Value require(std::expected<Value, Error> result,
              const std::source_location location = std::source_location::current()) {
  if (!result)
    std::cerr << "unexpected error at " << location.file_name() << ':' << location.line() << '\n';
  check(result.has_value(), location);
  return std::move(*result);
}

template <class Value>
void check_error(const std::expected<Value, luca::CheckpointError> &result,
                 CheckpointDiagnosticCategory category,
                 const std::source_location location = std::source_location::current()) {
  check(!result.has_value(), location);
  check(result.error().category() == category, location);
  check(result.error().category_name() == luca::category_name(category));
  check(!result.error().message().empty());
}

SettlementDate date(int year, unsigned month_value, unsigned day_value) {
  return require(SettlementDate::create(std::chrono::year{year} / std::chrono::month{month_value} /
                                        std::chrono::day{day_value}));
}

Timestamp timestamp(int year, unsigned month_value, unsigned day_value,
                    std::chrono::nanoseconds time) {
  return Timestamp{std::chrono::sys_days{std::chrono::year{year} / std::chrono::month{month_value} /
                                         std::chrono::day{day_value}} +
                   time};
}

Sha256Digest digest(std::string_view value) { return require(Sha256Digest::create(value)); }

CheckpointIdentity identity(std::string_view id, std::string_view version) {
  return require(CheckpointIdentity::create(id, version));
}

CheckpointInput input(std::string_view id, std::string_view version,
                      std::string_view digest_value) {
  return require(CheckpointInput::create(id, version, digest(digest_value)));
}

std::vector<EventId> event_ids(std::initializer_list<std::string_view> values) {
  std::vector<EventId> result;
  result.reserve(values.size());
  for (const auto value : values)
    result.emplace_back(std::string{value});
  return result;
}

std::vector<SourceRecordId> source_ids(std::initializer_list<std::string_view> values) {
  std::vector<SourceRecordId> result;
  result.reserve(values.size());
  for (const auto value : values)
    result.emplace_back(std::string{value});
  return result;
}

CheckpointManifest fixture_manifest() {
  const auto rounding = input("luca.half-even", "1",
                              "b2be4d87b2f322900cd752bd7db0be406bdc41650456d89a535719d7c4c45205");
  const auto context = require(CheckpointEvaluationContext::create(
      timestamp(2026, 1, 6, 23h + 59min + 59s), timestamp(2026, 1, 6, 23h + 59min + 59s),
      date(2026, 1, 6), {}, {}, {}, {rounding}, {}));
  const auto partition = require(AccountSetPartition::create({AccountId{"acct-main"}}));
  const auto prefix = require(CheckpointEventPrefix::create(
      1, 2, 2, EventId{"record-buy-origin"},
      digest("9fe51890a95a2d82e46606e6339d3599e368d134d9f2054903b6fae62f934e84")));
  const auto watermark = require(
      ResolvedEventWatermark::create(timestamp(2026, 1, 3, 10h), 2, EventId{"record-buy-origin"}));
  const auto lineage =
      require(CheckpointLineage::create(event_ids({"record-cash-origin", "record-buy-origin"}),
                                        event_ids({"record-cash-origin", "record-buy-origin"}),
                                        source_ids({"source-cash-origin", "source-buy-origin"})));
  return require(CheckpointManifest::create(
      identity("luca.portfolio-state", "1"), "luca-engine-1",
      identity("luca.portfolio-default", "1"), partition, prefix, context,
      digest("72c3555ab26a7a4ec42f1024c0404e6b0094510908783e9e1069141f6a88a738"), watermark,
      lineage));
}

std::size_t find_text(std::span<const std::byte> bytes, std::string_view text) {
  std::vector<std::byte> needle;
  needle.reserve(text.size());
  for (const auto character : text)
    needle.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  return static_cast<std::size_t>(
      std::search(bytes.begin(), bytes.end(), needle.begin(), needle.end()) - bytes.begin());
}

template <class Value>
concept CanonicallySerializable = requires(const Value &value) {
  { canonical_bytes(value) } -> std::same_as<CanonicalBytes>;
  { canonical_digest(value) } -> std::same_as<std::string>;
};

static_assert(CanonicallySerializable<CheckpointManifest>);
static_assert(CheckpointManifest::schema_version == "luca.checkpoint-manifest.v1");
static_assert(CheckpointManifest::serialization_version == "luca.canonical-bytes.v1");
static_assert(CheckpointManifest::digest_algorithm == "sha-256");
static_assert(CheckpointEvaluationContext::schema_version == "luca.evaluation-context.v1");
static_assert(AccountSetPartition::definition == "account-set");
static_assert(AccountSetPartition::version == "1");
static_assert(CheckpointEventPrefix::kind == "acceptance_sequence_inclusive");
static_assert(CheckpointEventPrefix::record_schema_version == "luca.lifecycle-record.v1");

void test_integrated_manifest_vector_twice() {
  constexpr std::string_view expected_digest =
      "0caf30cfaa3169c60af55fc68173d3979e6f34f6cebc87fe73117ee4e8fc2964";
  const auto manifest = fixture_manifest();
  const auto first_bytes = canonical_bytes(manifest);
  const auto second_bytes = canonical_bytes(manifest);

  check(first_bytes == second_bytes);
  check(canonical_digest(manifest) == expected_digest);
  check(canonical_digest(manifest) == expected_digest);
  check(first_bytes.size() == 1'703);
}

void test_partition_and_input_canonicalization() {
  const std::string unicode_account{"\xC3\xA9-account"};
  const std::vector<AccountId> declared{AccountId{unicode_account}, AccountId{"z-account"},
                                        AccountId{"acct-a"}};
  const auto partition = require(AccountSetPartition::create(declared));
  check(declared.front().value() == unicode_account);
  check(partition.keys()[0].value() == "acct-a");
  check(partition.keys()[1].value() == "z-account");
  check(partition.keys()[2].value() == unicode_account);

  const auto zero = std::string(64, '0');
  const auto one = std::string(64, '1');
  const auto inputs = std::vector{input(unicode_account, "1", zero), input("z-input", "2", one),
                                  input("z-input", "1", zero)};
  const auto context = require(CheckpointEvaluationContext::create(
      timestamp(2026, 1, 1, 0ns), timestamp(2026, 1, 1, 0ns), date(2026, 1, 1), inputs, inputs,
      inputs, inputs, inputs));
  check(inputs.front().id() == unicode_account);
  const auto check_canonical_inputs = [&](std::span<const CheckpointInput> values) {
    check(values[0].id() == "z-input");
    check(values[0].version() == "1");
    check(values[1].version() == "2");
    check(values[2].id() == unicode_account);
  };
  check_canonical_inputs(context.reference_data_inputs());
  check_canonical_inputs(context.price_inputs());
  check_canonical_inputs(context.calendar_inputs());
  check_canonical_inputs(context.rounding_inputs());
  check_canonical_inputs(context.fx_inputs());

  const auto context_bytes = canonical_bytes(require(CheckpointManifest::create(
      identity("projection", "1"), "engine", identity("policy", "1"),
      require(AccountSetPartition::create({AccountId{"acct"}})),
      require(CheckpointEventPrefix::create(1, 1, 1, EventId{"record"}, digest(zero))), context,
      digest(zero),
      require(ResolvedEventWatermark::create(timestamp(2026, 1, 1, 0ns), 1, EventId{"record"})),
      require(CheckpointLineage::create(event_ids({"record"}), event_ids({"record"}),
                                        source_ids({"source"}))))));
  check(find_text(context_bytes, "z-input") < find_text(context_bytes, unicode_account));
}

void test_duplicate_and_invalid_declarations_are_rejected_without_mutation() {
  const auto zero = std::string(64, '0');
  const auto one = std::string(64, '1');
  const std::vector<AccountId> duplicate_accounts{AccountId{"acct"}, AccountId{"acct"}};
  const auto saved_accounts = duplicate_accounts;
  check_error(AccountSetPartition::create(duplicate_accounts),
              CheckpointDiagnosticCategory::duplicate_identity);
  check(duplicate_accounts == saved_accounts);
  check_error(AccountSetPartition::create({}), CheckpointDiagnosticCategory::empty_partition);
  check_error(AccountSetPartition::create({AccountId{""}}),
              CheckpointDiagnosticCategory::invalid_text);

  const std::vector duplicate_inputs{input("reference", "1", zero), input("reference", "1", one)};
  const auto saved_inputs = duplicate_inputs;
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), date(2026, 1, 1),
                                                  duplicate_inputs),
              CheckpointDiagnosticCategory::duplicate_identity);
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), date(2026, 1, 1), {},
                                                  duplicate_inputs),
              CheckpointDiagnosticCategory::duplicate_identity);
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), date(2026, 1, 1), {},
                                                  {}, duplicate_inputs),
              CheckpointDiagnosticCategory::duplicate_identity);
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), date(2026, 1, 1), {},
                                                  {}, {}, duplicate_inputs),
              CheckpointDiagnosticCategory::duplicate_identity);
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), date(2026, 1, 1), {},
                                                  {}, {}, {}, duplicate_inputs),
              CheckpointDiagnosticCategory::duplicate_identity);
  check(duplicate_inputs == saved_inputs);

  check_error(Sha256Digest::create(std::string(63, '0')),
              CheckpointDiagnosticCategory::invalid_digest);
  check_error(Sha256Digest::create(std::string(64, 'A')),
              CheckpointDiagnosticCategory::invalid_digest);
  check_error(CheckpointIdentity::create("", "1"), CheckpointDiagnosticCategory::invalid_text);
  check_error(CheckpointIdentity::create("identity", ""),
              CheckpointDiagnosticCategory::invalid_text);
  check_error(CheckpointInput::create("", "1", digest(zero)),
              CheckpointDiagnosticCategory::invalid_text);
  check_error(CheckpointInput::create("input", "", digest(zero)),
              CheckpointDiagnosticCategory::invalid_text);
  check_error(CheckpointIdentity::create("e\xCC\x81", "1"),
              CheckpointDiagnosticCategory::invalid_text);
  check_error(CheckpointIdentity::create(std::string{1, static_cast<char>(0xff)}, "1"),
              CheckpointDiagnosticCategory::invalid_text);
}

void test_invalid_prefix_context_watermark_and_lineage_are_rejected() {
  const auto zero = digest(std::string(64, '0'));
  check_error(CheckpointEventPrefix::create(2, 2, 1, EventId{"record"}, zero),
              CheckpointDiagnosticCategory::invalid_prefix);
  check_error(CheckpointEventPrefix::create(1, 3, 2, EventId{"record"}, zero),
              CheckpointDiagnosticCategory::invalid_prefix);
  check_error(CheckpointEventPrefix::create(1, 1, 1, EventId{""}, zero),
              CheckpointDiagnosticCategory::invalid_text);
  check_error(ResolvedEventWatermark::create(timestamp(2026, 1, 1, 0ns), 0, EventId{"record"}),
              CheckpointDiagnosticCategory::invalid_watermark);
  check_error(ResolvedEventWatermark::create(timestamp(2026, 1, 1, 0ns), 1, EventId{""}),
              CheckpointDiagnosticCategory::invalid_text);

  const auto year_zero_date =
      require(SettlementDate::create(std::chrono::year{0} / std::chrono::January / 1));
  check_error(CheckpointEvaluationContext::create(timestamp(2026, 1, 1, 0ns),
                                                  timestamp(2026, 1, 1, 0ns), year_zero_date),
              CheckpointDiagnosticCategory::invalid_date);
  check_error(CheckpointLineage::create(event_ids({"record", "record"}), event_ids({"record"}),
                                        source_ids({"source"})),
              CheckpointDiagnosticCategory::duplicate_identity);
  check_error(CheckpointLineage::create(event_ids({"record"}), event_ids({"missing"}),
                                        source_ids({"source"})),
              CheckpointDiagnosticCategory::inconsistent_lineage);
  check_error(CheckpointLineage::create(event_ids({"record"}), event_ids({"record"}),
                                        std::vector{SourceRecordId{""}}),
              CheckpointDiagnosticCategory::invalid_text);

  const auto fixture = fixture_manifest();
  check_error(CheckpointManifest::create(fixture.projection(), "", fixture.policy(),
                                         fixture.partition(), fixture.event_prefix(),
                                         fixture.evaluation_context(),
                                         fixture.canonical_state_digest(),
                                         fixture.resolved_event_watermark(), fixture.lineage()),
              CheckpointDiagnosticCategory::invalid_text);
  const auto one_record_lineage = require(CheckpointLineage::create(
      event_ids({"record-buy-origin"}), event_ids({"record-buy-origin"}), source_ids({"source"})));
  check_error(CheckpointManifest::create(fixture.projection(), fixture.engine_version(),
                                         fixture.policy(), fixture.partition(),
                                         fixture.event_prefix(), fixture.evaluation_context(),
                                         fixture.canonical_state_digest(),
                                         fixture.resolved_event_watermark(), one_record_lineage),
              CheckpointDiagnosticCategory::inconsistent_lineage);

  const auto out_of_prefix = require(
      ResolvedEventWatermark::create(timestamp(2026, 1, 3, 10h), 3, EventId{"record-buy-origin"}));
  check_error(CheckpointManifest::create(
                  fixture.projection(), fixture.engine_version(), fixture.policy(),
                  fixture.partition(), fixture.event_prefix(), fixture.evaluation_context(),
                  fixture.canonical_state_digest(), out_of_prefix, fixture.lineage()),
              CheckpointDiagnosticCategory::invalid_watermark);

  const auto wrong_sequence = require(
      ResolvedEventWatermark::create(timestamp(2026, 1, 3, 10h), 1, EventId{"record-buy-origin"}));
  check_error(CheckpointManifest::create(
                  fixture.projection(), fixture.engine_version(), fixture.policy(),
                  fixture.partition(), fixture.event_prefix(), fixture.evaluation_context(),
                  fixture.canonical_state_digest(), wrong_sequence, fixture.lineage()),
              CheckpointDiagnosticCategory::invalid_watermark);
}

void test_compatibility_critical_mutations_change_owned_representation() {
  const auto base = fixture_manifest();
  const auto base_digest = canonical_digest(base);
  const auto changed = [&](const std::expected<CheckpointManifest, luca::CheckpointError> &value) {
    check(value.has_value());
    check(canonical_digest(*value) != base_digest);
  };

  changed(CheckpointManifest::create(identity("luca.portfolio-state", "2"), base.engine_version(),
                                     base.policy(), base.partition(), base.event_prefix(),
                                     base.evaluation_context(), base.canonical_state_digest(),
                                     base.resolved_event_watermark(), base.lineage()));
  changed(CheckpointManifest::create(base.projection(), "luca-engine-2", base.policy(),
                                     base.partition(), base.event_prefix(),
                                     base.evaluation_context(), base.canonical_state_digest(),
                                     base.resolved_event_watermark(), base.lineage()));
  changed(CheckpointManifest::create(
      base.projection(), base.engine_version(), identity("luca.portfolio-default", "2"),
      base.partition(), base.event_prefix(), base.evaluation_context(),
      base.canonical_state_digest(), base.resolved_event_watermark(), base.lineage()));
  changed(CheckpointManifest::create(
      base.projection(), base.engine_version(), base.policy(),
      require(AccountSetPartition::create({AccountId{"acct-main"}, AccountId{"acct-other"}})),
      base.event_prefix(), base.evaluation_context(), base.canonical_state_digest(),
      base.resolved_event_watermark(), base.lineage()));

  const auto changed_prefix = require(CheckpointEventPrefix::create(
      1, 2, 2, EventId{"record-buy-origin"}, digest(std::string(64, '1'))));
  changed(CheckpointManifest::create(base.projection(), base.engine_version(), base.policy(),
                                     base.partition(), changed_prefix, base.evaluation_context(),
                                     base.canonical_state_digest(), base.resolved_event_watermark(),
                                     base.lineage()));

  const auto changed_context = require(CheckpointEvaluationContext::create(
      base.evaluation_context().recorded_through(),
      base.evaluation_context().economic_as_of() + 1ns,
      base.evaluation_context().settlement_as_of_date(),
      {base.evaluation_context().reference_data_inputs().begin(),
       base.evaluation_context().reference_data_inputs().end()},
      {base.evaluation_context().price_inputs().begin(),
       base.evaluation_context().price_inputs().end()},
      {base.evaluation_context().calendar_inputs().begin(),
       base.evaluation_context().calendar_inputs().end()},
      {base.evaluation_context().rounding_inputs().begin(),
       base.evaluation_context().rounding_inputs().end()},
      {base.evaluation_context().fx_inputs().begin(),
       base.evaluation_context().fx_inputs().end()}));
  changed(CheckpointManifest::create(base.projection(), base.engine_version(), base.policy(),
                                     base.partition(), base.event_prefix(), changed_context,
                                     base.canonical_state_digest(), base.resolved_event_watermark(),
                                     base.lineage()));
  changed(CheckpointManifest::create(base.projection(), base.engine_version(), base.policy(),
                                     base.partition(), base.event_prefix(),
                                     base.evaluation_context(), digest(std::string(64, '2')),
                                     base.resolved_event_watermark(), base.lineage()));

  const auto changed_watermark =
      require(ResolvedEventWatermark::create(base.resolved_event_watermark().effective_at() + 1ns,
                                             base.resolved_event_watermark().acceptance_sequence(),
                                             base.resolved_event_watermark().record_id()));
  changed(CheckpointManifest::create(base.projection(), base.engine_version(), base.policy(),
                                     base.partition(), base.event_prefix(),
                                     base.evaluation_context(), base.canonical_state_digest(),
                                     changed_watermark, base.lineage()));

  const auto changed_lineage = require(CheckpointLineage::create(
      {base.lineage().lifecycle_record_ids().begin(), base.lineage().lifecycle_record_ids().end()},
      {base.lineage().active_record_ids().begin(), base.lineage().active_record_ids().end()},
      source_ids({"source-buy-origin", "source-cash-origin"})));
  changed(CheckpointManifest::create(base.projection(), base.engine_version(), base.policy(),
                                     base.partition(), base.event_prefix(),
                                     base.evaluation_context(), base.canonical_state_digest(),
                                     base.resolved_event_watermark(), changed_lineage));
  check(changed_lineage.source_record_ids().front().value() == "source-buy-origin");
}

} // namespace

int main() {
  test_integrated_manifest_vector_twice();
  test_partition_and_input_canonicalization();
  test_duplicate_and_invalid_declarations_are_rejected_without_mutation();
  test_invalid_prefix_context_watermark_and_lineage_are_rejected();
  test_compatibility_critical_mutations_change_owned_representation();
}
