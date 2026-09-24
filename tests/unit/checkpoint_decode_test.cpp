#include "luca/portfolio.hpp"

#include <algorithm>
#include <chrono>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <expected>
#include <fstream>
#include <iterator>
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
using luca::CashBalance;
using luca::CheckpointEvaluationContext;
using luca::CheckpointEventPrefix;
using luca::CheckpointIdentity;
using luca::CheckpointInput;
using luca::CheckpointLineage;
using luca::CheckpointManifest;
using luca::Currency;
using luca::EventId;
using luca::InstrumentId;
using luca::Money;
using luca::PortfolioState;
using luca::Position;
using luca::PositionKey;
using luca::Quantity;
using luca::ResolvedEventWatermark;
using luca::SettlementDate;
using luca::SettlementDirection;
using luca::SettlementObligation;
using luca::Sha256Digest;
using luca::SourceRecordId;
using luca::Timestamp;
using luca::serialization::canonical_bytes;
using luca::serialization::canonical_digest;
using luca::serialization::CanonicalBytes;
using luca::serialization::DecodeDiagnosticCategory;

void check(bool condition, std::source_location location = std::source_location::current()) {
  if (!condition) {
    std::fprintf(stderr, "check failed at %s:%u\n", location.file_name(), location.line());
    std::abort();
  }
}

template <class Value, class Error> Value require(std::expected<Value, Error> result) {
  check(result.has_value());
  return std::move(*result);
}

template <class Result> void expect_error(const Result &result, DecodeDiagnosticCategory category) {
  check(!result.has_value());
  check(result.error().category() == category);
  check(result.error().category_name() == luca::serialization::category_name(category));
  check(!result.error().message().empty());
}

Currency currency(std::string_view code) { return require(Currency::from_code(code)); }

SettlementDate date(int year, unsigned month, unsigned day) {
  return require(SettlementDate::create(std::chrono::year{year} / std::chrono::month{month} /
                                        std::chrono::day{day}));
}

Timestamp timestamp(int year, unsigned month, unsigned day, std::chrono::nanoseconds time) {
  return Timestamp{std::chrono::sys_days{std::chrono::year{year} / std::chrono::month{month} /
                                         std::chrono::day{day}} +
                   time};
}

Sha256Digest digest(std::string_view value) { return require(Sha256Digest::create(value)); }

CheckpointIdentity identity(std::string_view id, std::string_view version) {
  return require(CheckpointIdentity::create(id, version));
}

CheckpointInput input(std::string_view id, std::string_view version, char digest_digit) {
  return require(CheckpointInput::create(id, version, digest(std::string(64, digest_digit))));
}

Position position(std::string account, std::string instrument, std::int64_t quantity) {
  return Position{PositionKey{AccountId{std::move(account)}, InstrumentId{std::move(instrument)}},
                  Quantity::from_scaled(quantity)};
}

CashBalance cash(std::string account, std::string_view code, std::int64_t amount) {
  return CashBalance{AccountId{std::move(account)}, Money::from_scaled(amount, currency(code))};
}

SettlementObligation obligation(std::string account, SettlementDate settlement_date,
                                std::string_view code, SettlementDirection direction,
                                std::int64_t amount) {
  return SettlementObligation{AccountId{std::move(account)}, settlement_date, direction,
                              Money::from_scaled(amount, currency(code))};
}

PortfolioState fixture_state() {
  return PortfolioState{
      {position("acct-a", "instrument-a", -2), position("acct-b", "instrument-b", 8'000'000'000)},
      {cash("acct-a", "EUR", -3), cash("acct-b", "USD", 100'000'000'000)},
      {obligation("acct-a", date(2026, 1, 8), "USD", SettlementDirection::receivable, 5),
       obligation("acct-b", date(2026, 1, 9), "USD", SettlementDirection::payable, 4'400'000'000)}};
}

CheckpointManifest fixture_manifest() {
  const auto context = require(CheckpointEvaluationContext::create(
      timestamp(2026, 1, 6, 23h + 59min + 59s), timestamp(2026, 1, 6, 23h + 59min + 59s),
      date(2026, 1, 6), {}, {}, {}, {input("a-input", "1", 'a'), input("b-input", "1", 'b')}, {}));
  const auto partition =
      require(AccountSetPartition::create({AccountId{"acct-a"}, AccountId{"acct-b"}}));
  const auto prefix = require(
      CheckpointEventPrefix::create(1, 2, 2, EventId{"record-2"}, digest(std::string(64, 'c'))));
  const auto watermark =
      require(ResolvedEventWatermark::create(timestamp(2026, 1, 3, 10h), 2, EventId{"record-2"}));
  const auto lineage = require(CheckpointLineage::create(
      {EventId{"record-1"}, EventId{"record-2"}}, {EventId{"record-1"}, EventId{"record-2"}},
      {SourceRecordId{"source-1"}, SourceRecordId{"source-2"}}));
  return require(CheckpointManifest::create(
      identity("luca.portfolio-state", "1"), "luca-engine-1",
      identity("luca.portfolio-default", "1"), partition, prefix, context,
      digest(canonical_digest(fixture_state())), watermark, lineage));
}

std::size_t find_ascii(std::span<const std::byte> bytes, std::string_view value,
                       std::size_t start = 0) {
  std::vector<std::byte> needle;
  needle.reserve(value.size());
  for (const char character : value)
    needle.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  const auto found = std::search(bytes.begin() + static_cast<std::ptrdiff_t>(start), bytes.end(),
                                 needle.begin(), needle.end());
  check(found != bytes.end());
  return static_cast<std::size_t>(found - bytes.begin());
}

unsigned char hex_value(char digit) {
  if (digit >= '0' && digit <= '9')
    return static_cast<unsigned char>(digit - '0');
  if (digit >= 'a' && digit <= 'f')
    return static_cast<unsigned char>(digit - 'a' + 10);
  check(false);
  return 0;
}

struct PinnedVector {
  CanonicalBytes bytes;
  std::string digest;
};

PinnedVector pinned_vector(std::string_view path, std::string_view id) {
  std::ifstream input{std::string{path}};
  check(input.is_open());
  const std::string fixture{std::istreambuf_iterator<char>{input},
                            std::istreambuf_iterator<char>{}};
  const auto id_position = fixture.find("\"id\": \"" + std::string{id} + "\"");
  check(id_position != std::string::npos);
  constexpr std::string_view hex_key = "\"canonical_hex\": \"";
  const auto hex_position = fixture.find(hex_key, id_position);
  check(hex_position != std::string::npos);
  const auto hex_begin = hex_position + hex_key.size();
  const auto hex_end = fixture.find('"', hex_begin);
  check(hex_end != std::string::npos);
  const std::string_view hex{fixture.data() + hex_begin, hex_end - hex_begin};
  check(hex.size() % 2U == 0U);

  PinnedVector result;
  result.bytes.reserve(hex.size() / 2U);
  for (std::size_t offset = 0; offset < hex.size(); offset += 2U) {
    result.bytes.push_back(
        static_cast<std::byte>((hex_value(hex[offset]) << 4U) | hex_value(hex[offset + 1U])));
  }
  constexpr std::string_view digest_key = "\"sha256\": \"";
  const auto digest_position = fixture.find(digest_key, hex_end);
  check(digest_position != std::string::npos);
  const auto digest_begin = digest_position + digest_key.size();
  const auto digest_end = fixture.find('"', digest_begin);
  check(digest_end != std::string::npos);
  result.digest = fixture.substr(digest_begin, digest_end - digest_begin);
  check(result.digest.size() == 64U);
  return result;
}

void replace_ascii(CanonicalBytes &bytes, std::string_view old_value, std::string_view new_value,
                   std::size_t start = 0) {
  check(old_value.size() == new_value.size());
  const auto offset = find_ascii(bytes, old_value, start);
  for (std::size_t index = 0; index < new_value.size(); ++index) {
    bytes[offset + index] = static_cast<std::byte>(static_cast<unsigned char>(new_value[index]));
  }
}

std::size_t text_payload_after_key(std::span<const std::byte> bytes, std::string_view key) {
  auto start = std::size_t{};
  while (start < bytes.size()) {
    const auto key_offset = find_ascii(bytes, key, start);
    const auto tag_offset = key_offset + key.size();
    if (tag_offset < bytes.size() && std::to_integer<std::uint8_t>(bytes[tag_offset]) == 0x04U)
      return tag_offset + 5U;
    start = key_offset + 1U;
  }
  check(false);
  return 0;
}

void replace_text_after_key(CanonicalBytes &bytes, std::string_view key, std::string_view value) {
  const auto offset = text_payload_after_key(bytes, key);
  check(value.size() == 30U);
  check(offset + value.size() <= bytes.size());
  for (std::size_t index = 0; index < value.size(); ++index)
    bytes[offset + index] = static_cast<std::byte>(static_cast<unsigned char>(value[index]));
}

CanonicalBytes empty_state_with_second_key(std::string_view second_key) {
  using namespace luca::serialization::detail;
  auto bytes = top_level_bytes();
  append_map(bytes, 4U);
  append_key(bytes, "open_settlement_obligations");
  append_array(bytes, 0U);
  append_key(bytes, second_key);
  append_array(bytes, 0U);
  append_key(bytes, "schema_version");
  append_text(bytes, "luca.portfolio-state.v1");
  append_key(bytes, "settled_cash");
  append_array(bytes, 0U);
  return bytes;
}

CanonicalBytes state_with_positions(std::span<const Position> positions) {
  using namespace luca::serialization::detail;
  auto bytes = top_level_bytes();
  append_map(bytes, 4U);
  append_key(bytes, "open_settlement_obligations");
  append_array(bytes, 0U);
  append_key(bytes, "positions");
  append_array(bytes, static_cast<std::uint64_t>(positions.size()));
  for (const auto &value : positions)
    append_position_balance(bytes, value);
  append_key(bytes, "schema_version");
  append_text(bytes, "luca.portfolio-state.v1");
  append_key(bytes, "settled_cash");
  append_array(bytes, 0U);
  return bytes;
}

template <class Value>
concept TypedDecoder = requires(std::span<const std::byte> bytes) {
  {
    luca::serialization::decode_portfolio_state(bytes)
    } -> std::same_as<std::expected<PortfolioState, luca::serialization::DecodeError>>;
  {
    luca::serialization::decode_checkpoint_manifest(bytes)
    } -> std::same_as<std::expected<CheckpointManifest, luca::serialization::DecodeError>>;
};

static_assert(TypedDecoder<void>);

void test_round_trips_twice() {
  const auto state = fixture_state();
  const auto state_bytes = canonical_bytes(state);
  const auto state_saved = state_bytes;
  const auto first_state = luca::serialization::decode_portfolio_state(state_bytes);
  const auto second_state = luca::serialization::decode_portfolio_state(state_bytes);
  check(first_state.has_value() && second_state.has_value());
  check(*first_state == state);
  check(*second_state == state);
  check(canonical_bytes(*first_state) == state_bytes);
  check(canonical_bytes(*second_state) == state_bytes);
  check(canonical_digest(*first_state) == canonical_digest(state));
  check(state_bytes == state_saved);

  const auto manifest = fixture_manifest();
  const auto manifest_bytes = canonical_bytes(manifest);
  const auto manifest_saved = manifest_bytes;
  const auto first_manifest = luca::serialization::decode_checkpoint_manifest(manifest_bytes);
  const auto second_manifest = luca::serialization::decode_checkpoint_manifest(manifest_bytes);
  check(first_manifest.has_value() && second_manifest.has_value());
  check(*first_manifest == manifest);
  check(*second_manifest == manifest);
  check(canonical_bytes(*first_manifest) == manifest_bytes);
  check(canonical_bytes(*second_manifest) == manifest_bytes);
  check(canonical_digest(*first_manifest) == canonical_digest(manifest));
  check(manifest_bytes == manifest_saved);
}

void test_integrated_vectors_twice() {
  const std::vector state_vectors{
      pinned_vector(LUCA_CHECKPOINT_DECODE_FIXTURE_PATH, "checkpoint-state"),
      pinned_vector(LUCA_CHECKPOINT_DECODE_FIXTURE_PATH, "full-state"),
      pinned_vector(LUCA_CHECKPOINT_DECODE_LATE_FIXTURE_PATH, "late-checkpoint-state"),
      pinned_vector(LUCA_CHECKPOINT_DECODE_LATE_FIXTURE_PATH, "late-full-state")};
  for (const auto &vector : state_vectors) {
    for (unsigned run = 0; run < 2U; ++run) {
      const auto state = luca::serialization::decode_portfolio_state(vector.bytes);
      check(state.has_value());
      check(canonical_bytes(*state) == vector.bytes);
      check(canonical_digest(*state) == vector.digest);
    }
  }

  const std::vector manifest_vectors{
      pinned_vector(LUCA_CHECKPOINT_DECODE_FIXTURE_PATH, "checkpoint-manifest"),
      pinned_vector(LUCA_CHECKPOINT_DECODE_LATE_FIXTURE_PATH, "late-checkpoint-manifest")};
  for (const auto &vector : manifest_vectors) {
    for (unsigned run = 0; run < 2U; ++run) {
      const auto manifest = luca::serialization::decode_checkpoint_manifest(vector.bytes);
      check(manifest.has_value());
      check(canonical_bytes(*manifest) == vector.bytes);
      check(canonical_digest(*manifest) == vector.digest);
    }
  }
}

void test_reader_failures_and_closed_shape() {
  const auto valid = canonical_bytes(fixture_state());

  auto malformed_header = valid;
  malformed_header[0] = std::byte{'X'};
  expect_error(luca::serialization::decode_portfolio_state(malformed_header),
               DecodeDiagnosticCategory::canonical_encoding);

  auto malformed_tag = valid;
  malformed_tag[4] = std::byte{0xff};
  expect_error(luca::serialization::decode_portfolio_state(malformed_tag),
               DecodeDiagnosticCategory::canonical_encoding);

  auto mistyped = valid;
  const auto settled_key = find_ascii(mistyped, "settled_cash");
  mistyped[settled_key + std::string_view{"settled_cash"}.size()] = std::byte{0x04};
  expect_error(luca::serialization::decode_portfolio_state(mistyped),
               DecodeDiagnosticCategory::schema_shape);

  for (const std::uint8_t count : {std::uint8_t{3}, std::uint8_t{5}}) {
    auto wrong_shape = valid;
    wrong_shape[8] = static_cast<std::byte>(count);
    expect_error(luca::serialization::decode_portfolio_state(wrong_shape),
                 DecodeDiagnosticCategory::schema_shape);
  }

  const auto duplicate_map = empty_state_with_second_key("open_settlement_obligations");
  expect_error(luca::serialization::decode_portfolio_state(duplicate_map),
               DecodeDiagnosticCategory::duplicate_identity);
  const auto reordered_map = empty_state_with_second_key("aaa");
  expect_error(luca::serialization::decode_portfolio_state(reordered_map),
               DecodeDiagnosticCategory::deterministic_ordering);
  const auto unknown_member = empty_state_with_second_key("positionz");
  expect_error(luca::serialization::decode_portfolio_state(unknown_member),
               DecodeDiagnosticCategory::schema_shape);

  auto invalid_utf8 = valid;
  invalid_utf8[find_ascii(invalid_utf8, "acct-a")] = std::byte{0xff};
  expect_error(luca::serialization::decode_portfolio_state(invalid_utf8),
               DecodeDiagnosticCategory::canonical_encoding);

  auto non_nfc = valid;
  const auto account = find_ascii(non_nfc, "acct-a");
  non_nfc[account] = std::byte{'e'};
  non_nfc[account + 1U] = std::byte{0xcc};
  non_nfc[account + 2U] = std::byte{0x81};
  expect_error(luca::serialization::decode_portfolio_state(non_nfc),
               DecodeDiagnosticCategory::canonical_encoding);

  auto excessive_length = valid;
  const auto account_value = find_ascii(excessive_length, "acct-a");
  for (std::size_t index = account_value - 4U; index < account_value; ++index)
    excessive_length[index] = std::byte{0xff};
  expect_error(luca::serialization::decode_portfolio_state(excessive_length),
               DecodeDiagnosticCategory::canonical_encoding);

  auto excessive_count = valid;
  const auto positions_key = find_ascii(excessive_count, "positions");
  const auto positions_tag = positions_key + std::string_view{"positions"}.size();
  check(std::to_integer<std::uint8_t>(excessive_count[positions_tag]) == 0x05U);
  for (std::size_t index = positions_tag + 1U; index < positions_tag + 9U; ++index)
    excessive_count[index] = std::byte{0xff};
  const auto saved_excessive_count = excessive_count;
  expect_error(luca::serialization::decode_portfolio_state(excessive_count),
               DecodeDiagnosticCategory::canonical_encoding);
  check(excessive_count == saved_excessive_count);

  auto trailing = valid;
  trailing.push_back(std::byte{0});
  expect_error(luca::serialization::decode_portfolio_state(trailing),
               DecodeDiagnosticCategory::canonical_encoding);

  const std::vector<std::size_t> truncations{
      0U, 1U, 3U, 4U, 8U, valid.size() / 2U, valid.size() - 1U};
  for (const auto size : truncations) {
    expect_error(
        luca::serialization::decode_portfolio_state(std::span<const std::byte>{valid}.first(size)),
        DecodeDiagnosticCategory::canonical_encoding);
  }
}

void test_portfolio_schema_scalars_and_ordering() {
  const auto valid = canonical_bytes(fixture_state());

  auto unsupported = valid;
  replace_ascii(unsupported, "luca.portfolio-state.v1", "luca.portfolio-state.v2");
  expect_error(luca::serialization::decode_portfolio_state(unsupported),
               DecodeDiagnosticCategory::unsupported_version);

  auto unsupported_nested = valid;
  replace_ascii(unsupported_nested, "luca.quantity.v1", "luca.quantity.v2");
  expect_error(luca::serialization::decode_portfolio_state(unsupported_nested),
               DecodeDiagnosticCategory::unsupported_version);

  auto invalid_decimal = valid;
  replace_ascii(invalid_decimal, "8000000000", "0800000000");
  expect_error(luca::serialization::decode_portfolio_state(invalid_decimal),
               DecodeDiagnosticCategory::canonical_encoding);

  auto invalid_currency = valid;
  replace_ascii(invalid_currency, "EUR", "EuR");
  expect_error(luca::serialization::decode_portfolio_state(invalid_currency),
               DecodeDiagnosticCategory::canonical_encoding);

  auto invalid_date = valid;
  replace_ascii(invalid_date, "2026-01-08", "2026-02-30");
  expect_error(luca::serialization::decode_portfolio_state(invalid_date),
               DecodeDiagnosticCategory::canonical_encoding);

  const std::vector reversed{position("z-account", "instrument", 1),
                             position("a-account", "instrument", 2)};
  expect_error(luca::serialization::decode_portfolio_state(state_with_positions(reversed)),
               DecodeDiagnosticCategory::deterministic_ordering);

  const std::vector duplicates{position("a-account", "instrument", 1),
                               position("a-account", "instrument", 2)};
  expect_error(luca::serialization::decode_portfolio_state(state_with_positions(duplicates)),
               DecodeDiagnosticCategory::duplicate_identity);

  const std::vector zero{position("a-account", "instrument", 0)};
  expect_error(luca::serialization::decode_portfolio_state(state_with_positions(zero)),
               DecodeDiagnosticCategory::schema_shape);
}

void test_manifest_mutations() {
  const auto valid = canonical_bytes(fixture_manifest());

  auto unsupported = valid;
  replace_ascii(unsupported, "luca.checkpoint-manifest.v1", "luca.checkpoint-manifest.v2");
  expect_error(luca::serialization::decode_checkpoint_manifest(unsupported),
               DecodeDiagnosticCategory::unsupported_version);

  auto invalid_digest = valid;
  const auto state_digest = canonical_digest(fixture_state());
  const auto digest_offset = find_ascii(invalid_digest, state_digest);
  invalid_digest[digest_offset] = std::byte{'A'};
  const auto saved_invalid_digest = invalid_digest;
  expect_error(luca::serialization::decode_checkpoint_manifest(invalid_digest),
               DecodeDiagnosticCategory::canonical_encoding);
  check(invalid_digest == saved_invalid_digest);

  auto invalid_prefix = valid;
  invalid_prefix[text_payload_after_key(invalid_prefix, "first_sequence")] = std::byte{'2'};
  expect_error(luca::serialization::decode_checkpoint_manifest(invalid_prefix),
               DecodeDiagnosticCategory::schema_shape);

  auto invalid_watermark = valid;
  invalid_watermark[text_payload_after_key(invalid_watermark, "acceptance_sequence")] =
      std::byte{'1'};
  expect_error(luca::serialization::decode_checkpoint_manifest(invalid_watermark),
               DecodeDiagnosticCategory::schema_shape);

  auto partition_order = valid;
  const auto partition_key = find_ascii(partition_order, "keys");
  const auto account_a = find_ascii(partition_order, "acct-a", partition_key);
  const auto account_b = find_ascii(partition_order, "acct-b", account_a + 1U);
  partition_order[account_a + 5U] = std::byte{'b'};
  partition_order[account_b + 5U] = std::byte{'a'};
  expect_error(luca::serialization::decode_checkpoint_manifest(partition_order),
               DecodeDiagnosticCategory::deterministic_ordering);

  auto input_order = valid;
  const auto input_a = find_ascii(input_order, "a-input");
  const auto input_b = find_ascii(input_order, "b-input", input_a + 1U);
  input_order[input_a] = std::byte{'b'};
  input_order[input_b] = std::byte{'a'};
  expect_error(luca::serialization::decode_checkpoint_manifest(input_order),
               DecodeDiagnosticCategory::deterministic_ordering);

  auto duplicate_lineage = valid;
  const auto active_key = find_ascii(duplicate_lineage, "active_record_ids");
  replace_ascii(duplicate_lineage, "record-2", "record-1", active_key);
  expect_error(luca::serialization::decode_checkpoint_manifest(duplicate_lineage),
               DecodeDiagnosticCategory::duplicate_identity);

  auto missing_lineage = valid;
  replace_ascii(missing_lineage, "record-2", "missing2", active_key);
  expect_error(luca::serialization::decode_checkpoint_manifest(missing_lineage),
               DecodeDiagnosticCategory::lineage_reference_missing);

  auto trailing = valid;
  trailing.push_back(std::byte{0});
  expect_error(luca::serialization::decode_checkpoint_manifest(trailing),
               DecodeDiagnosticCategory::canonical_encoding);
  expect_error(luca::serialization::decode_checkpoint_manifest(
                   std::span<const std::byte>{valid}.first(valid.size() - 1U)),
               DecodeDiagnosticCategory::canonical_encoding);
}

void test_timestamp_representability() {
  const auto valid = canonical_bytes(fixture_manifest());

  auto minimum = valid;
  replace_text_after_key(minimum, "recorded_through", "1677-09-21T00:12:43.145224192Z");
  const auto minimum_saved = minimum;
  const auto decoded_minimum = luca::serialization::decode_checkpoint_manifest(minimum);
  check(decoded_minimum.has_value());
  check(decoded_minimum->evaluation_context().recorded_through() == Timestamp::min());
  check(minimum == minimum_saved);

  auto maximum = valid;
  replace_text_after_key(maximum, "economic_as_of", "2262-04-11T23:47:16.854775807Z");
  const auto maximum_saved = maximum;
  const auto decoded_maximum = luca::serialization::decode_checkpoint_manifest(maximum);
  check(decoded_maximum.has_value());
  check(decoded_maximum->evaluation_context().economic_as_of() == Timestamp::max());
  check(canonical_bytes(*decoded_maximum) == maximum);
  check(maximum == maximum_saved);

  for (const auto invalid : {std::string_view{"1677-09-21T00:12:43.145224191Z"},
                             std::string_view{"2262-04-11T23:47:16.854775808Z"},
                             std::string_view{"9999-12-31T23:59:59.999999999Z"}}) {
    auto out_of_range = valid;
    replace_text_after_key(out_of_range, "recorded_through", invalid);
    const auto saved = out_of_range;
    expect_error(luca::serialization::decode_checkpoint_manifest(out_of_range),
                 DecodeDiagnosticCategory::canonical_encoding);
    check(out_of_range == saved);
  }
}

} // namespace

int main() {
  test_round_trips_twice();
  test_integrated_vectors_twice();
  test_reader_failures_and_closed_shape();
  test_portfolio_schema_scalars_and_ordering();
  test_manifest_mutations();
  test_timestamp_representability();
  return 0;
}
