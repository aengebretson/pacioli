#pragma once

#include "luca/serialization/canonical.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>

namespace luca::serialization {

enum class DecodeDiagnosticCategory {
  schema_shape,
  unsupported_version,
  canonical_encoding,
  duplicate_identity,
  deterministic_ordering,
  lineage_reference_missing,
};

[[nodiscard]] constexpr std::string_view category_name(DecodeDiagnosticCategory category) noexcept {
  switch (category) {
  case DecodeDiagnosticCategory::schema_shape:
    return "schema_shape";
  case DecodeDiagnosticCategory::unsupported_version:
    return "unsupported_version";
  case DecodeDiagnosticCategory::canonical_encoding:
    return "canonical_encoding";
  case DecodeDiagnosticCategory::duplicate_identity:
    return "duplicate_identity";
  case DecodeDiagnosticCategory::deterministic_ordering:
    return "deterministic_ordering";
  case DecodeDiagnosticCategory::lineage_reference_missing:
    return "lineage_reference_missing";
  }
  return "canonical_encoding";
}

class DecodeError {
public:
  [[nodiscard]] DecodeDiagnosticCategory category() const noexcept { return category_; }
  [[nodiscard]] std::string_view category_name() const noexcept {
    return serialization::category_name(category_);
  }
  [[nodiscard]] std::size_t offset() const noexcept { return offset_; }
  [[nodiscard]] const std::string &message() const noexcept { return message_; }

  DecodeError(DecodeDiagnosticCategory category, std::size_t offset, std::string message)
      : category_(category), offset_(offset), message_(std::move(message)) {}

private:
  DecodeDiagnosticCategory category_;
  std::size_t offset_;
  std::string message_;
};

namespace decode_detail {

// The typed v1 schemas are intentionally bounded. Limits prevent attacker-
// controlled counts from becoming allocation requests even when a caller
// supplies an unusually large backing span.
inline constexpr std::size_t maximum_input_bytes = 64U * 1024U * 1024U;
inline constexpr std::size_t maximum_text_bytes = 16U * 1024U * 1024U;
inline constexpr std::size_t maximum_collection_items = 1'000'000U;
inline constexpr std::uint32_t maximum_map_members = 64U;

[[nodiscard]] inline bool raw_bytes_less(std::string_view left, std::string_view right) noexcept {
  return std::lexicographical_compare(
      left.begin(), left.end(), right.begin(), right.end(), [](char left_byte, char right_byte) {
        return static_cast<unsigned char>(left_byte) < static_cast<unsigned char>(right_byte);
      });
}

class Reader {
public:
  explicit Reader(std::span<const std::byte> input) : input_(input) {}

  [[nodiscard]] std::size_t offset() const noexcept { return offset_; }

  [[nodiscard]] DecodeError error(DecodeDiagnosticCategory category, std::string message) const {
    return DecodeError{category, offset_, std::move(message)};
  }

  [[nodiscard]] std::expected<void, DecodeError> read_header() {
    if (input_.size() > maximum_input_bytes) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 input exceeds the v1 decoder byte limit"));
    }
    constexpr std::string_view header = "LCB1";
    if (remaining() < header.size()) {
      return std::unexpected(
          error(DecodeDiagnosticCategory::canonical_encoding, "LCB1 header is truncated"));
    }
    for (const char character : header) {
      if (read_octet_unchecked() != static_cast<std::uint8_t>(character)) {
        return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                     "LCB1 header is invalid or unsupported"));
      }
    }
    return {};
  }

  [[nodiscard]] std::expected<void, DecodeError> read_map(std::uint32_t expected_members,
                                                          std::string_view schema_name) {
    auto tag = expect_tag(0x06U, "map");
    if (!tag)
      return std::unexpected(tag.error());
    auto count = read_u32();
    if (!count)
      return std::unexpected(count.error());
    if (*count > maximum_map_members || *count > remaining() / 5U) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 map count exceeds the bounded input"));
    }
    if (*count != expected_members) {
      return std::unexpected(
          error(DecodeDiagnosticCategory::schema_shape,
                std::string{schema_name} + " has a missing or extra map member"));
    }
    return {};
  }

  [[nodiscard]] std::expected<std::size_t, DecodeError>
  read_array_count(std::string_view field_name) {
    auto tag = expect_tag(0x05U, "array");
    if (!tag)
      return std::unexpected(tag.error());
    auto count = read_u64();
    if (!count)
      return std::unexpected(count.error());
    if (*count > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
        *count > maximum_collection_items || *count > remaining()) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   std::string{field_name} + " count exceeds the bounded input"));
    }
    return static_cast<std::size_t>(*count);
  }

  [[nodiscard]] std::expected<std::string_view, DecodeError> read_text() {
    auto tag = expect_tag(0x04U, "text");
    if (!tag)
      return std::unexpected(tag.error());
    auto length = read_u32();
    if (!length)
      return std::unexpected(length.error());
    if (*length > maximum_text_bytes || *length > remaining()) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 text length exceeds the bounded input"));
    }
    const auto result = text_at(offset_, *length);
    offset_ += *length;
    if (auto valid = validate_utf8(result, "LCB1 text"); !valid)
      return std::unexpected(valid.error());
    return result;
  }

  [[nodiscard]] std::expected<void, DecodeError> read_key(std::string_view expected,
                                                          std::string_view &previous) {
    auto length = read_u32();
    if (!length)
      return std::unexpected(length.error());
    if (*length > maximum_text_bytes || *length > remaining()) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 map-key length exceeds the bounded input"));
    }
    const auto key = text_at(offset_, *length);
    offset_ += *length;
    if (auto valid = validate_utf8(key, "LCB1 map key"); !valid)
      return std::unexpected(valid.error());

    if (!previous.empty() && !raw_bytes_less(previous, key)) {
      const auto category = previous == key ? DecodeDiagnosticCategory::duplicate_identity
                                            : DecodeDiagnosticCategory::deterministic_ordering;
      return std::unexpected(
          error(category, previous == key ? "LCB1 map keys must be unique"
                                          : "LCB1 map keys are not in canonical raw-byte order"));
    }
    previous = key;
    if (key != expected) {
      return std::unexpected(error(DecodeDiagnosticCategory::schema_shape,
                                   "LCB1 map has an unknown, missing, or reordered member"));
    }
    return {};
  }

  [[nodiscard]] std::expected<void, DecodeError> finish() const {
    if (offset_ != input_.size()) {
      return std::unexpected(
          error(DecodeDiagnosticCategory::canonical_encoding, "LCB1 value has trailing bytes"));
    }
    return {};
  }

private:
  [[nodiscard]] std::size_t remaining() const noexcept { return input_.size() - offset_; }

  [[nodiscard]] std::uint8_t read_octet_unchecked() noexcept {
    return std::to_integer<std::uint8_t>(input_[offset_++]);
  }

  [[nodiscard]] std::expected<void, DecodeError> expect_tag(std::uint8_t expected,
                                                            std::string_view expected_name) {
    if (remaining() == 0) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 value is truncated before a tag"));
    }
    const auto actual = read_octet_unchecked();
    if (actual > 0x06U) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 value contains an unknown tag"));
    }
    if (actual != expected) {
      return std::unexpected(error(DecodeDiagnosticCategory::schema_shape,
                                   "LCB1 value is not the expected " + std::string{expected_name}));
    }
    return {};
  }

  [[nodiscard]] std::expected<std::uint32_t, DecodeError> read_u32() {
    if (remaining() < 4U) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 unsigned 32-bit value is truncated"));
    }
    std::uint32_t result = 0;
    for (unsigned index = 0; index < 4U; ++index)
      result = static_cast<std::uint32_t>((result << 8U) | read_octet_unchecked());
    return result;
  }

  [[nodiscard]] std::expected<std::uint64_t, DecodeError> read_u64() {
    if (remaining() < 8U) {
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   "LCB1 unsigned 64-bit value is truncated"));
    }
    std::uint64_t result = 0;
    for (unsigned index = 0; index < 8U; ++index)
      result = (result << 8U) | read_octet_unchecked();
    return result;
  }

  [[nodiscard]] std::string_view text_at(std::size_t offset, std::size_t length) const noexcept {
    const auto *characters = reinterpret_cast<const char *>(input_.data() + offset);
    return {characters, length};
  }

  [[nodiscard]] std::expected<void, DecodeError> validate_utf8(std::string_view value,
                                                               std::string_view field) const {
    switch (detail::unicode_nfc::validate(value)) {
    case detail::unicode_nfc::ValidationResult::valid:
      return {};
    case detail::unicode_nfc::ValidationResult::invalid_utf8:
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   std::string{field} + " must be valid UTF-8"));
    case detail::unicode_nfc::ValidationResult::not_nfc:
      return std::unexpected(error(DecodeDiagnosticCategory::canonical_encoding,
                                   std::string{field} + " must be NFC-normalized"));
    }
    return std::unexpected(
        error(DecodeDiagnosticCategory::canonical_encoding, std::string{field} + " is invalid"));
  }

  std::span<const std::byte> input_;
  std::size_t offset_{};
};

[[nodiscard]] inline std::expected<std::string_view, DecodeError>
read_required_text(Reader &reader, std::string_view field) {
  auto value = reader.read_text();
  if (!value)
    return std::unexpected(value.error());
  if (value->empty() || value->find('\0') != std::string_view::npos) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " must be non-empty text without NUL"));
  }
  return *value;
}

[[nodiscard]] inline std::expected<std::int64_t, DecodeError>
parse_signed_decimal(Reader &reader, std::string_view value, std::string_view field) {
  if (value.empty() || value.front() == '+' || value == "-0" ||
      (value.size() > 1U && value.front() == '0') ||
      (value.front() == '-' && (value.size() == 1U || value[1] == '0'))) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " is not canonical signed decimal text"));
  }
  std::int64_t parsed{};
  const auto [end, result] = std::from_chars(value.data(), value.data() + value.size(), parsed);
  if (result != std::errc{} || end != value.data() + value.size()) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " is outside signed 64-bit canonical decimal"));
  }
  return parsed;
}

[[nodiscard]] inline std::expected<std::uint64_t, DecodeError>
parse_positive_decimal(Reader &reader, std::string_view value, std::string_view field) {
  if (value.empty() || value.front() < '1' || value.front() > '9') {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " is not canonical positive decimal text"));
  }
  std::uint64_t parsed{};
  const auto [end, result] = std::from_chars(value.data(), value.data() + value.size(), parsed);
  if (result != std::errc{} || end != value.data() + value.size()) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " is outside unsigned 64-bit canonical decimal"));
  }
  return parsed;
}

[[nodiscard]] inline bool decimal_digits(std::string_view value) noexcept {
  for (const char digit : value) {
    if (digit < '0' || digit > '9')
      return false;
  }
  return true;
}

[[nodiscard]] inline unsigned parse_small_decimal(std::string_view value) noexcept {
  unsigned result = 0;
  for (const char digit : value)
    result = result * 10U + static_cast<unsigned>(digit - '0');
  return result;
}

[[nodiscard]] inline std::expected<SettlementDate, DecodeError>
parse_date(Reader &reader, std::string_view value, std::string_view field) {
  if (value.size() != 10U || value[4] != '-' || value[7] != '-' ||
      !decimal_digits(value.substr(0, 4)) || !decimal_digits(value.substr(5, 2)) ||
      !decimal_digits(value.substr(8, 2))) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " is not a canonical settlement date"));
  }
  const auto date = std::chrono::year{static_cast<int>(parse_small_decimal(value.substr(0, 4)))} /
                    std::chrono::month{parse_small_decimal(value.substr(5, 2))} /
                    std::chrono::day{parse_small_decimal(value.substr(8, 2))};
  const auto result = SettlementDate::create(date);
  if (!result || static_cast<int>(date.year()) == 0) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::canonical_encoding,
                                        std::string{field} + " is not a valid v1 date"));
  }
  return *result;
}

[[nodiscard]] inline std::expected<Timestamp, DecodeError>
parse_timestamp(Reader &reader, std::string_view value, std::string_view field) {
  using namespace std::chrono;
  if (value.size() != 30U || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
      value[13] != ':' || value[16] != ':' || value[19] != '.' || value[29] != 'Z' ||
      !decimal_digits(value.substr(0, 4)) || !decimal_digits(value.substr(5, 2)) ||
      !decimal_digits(value.substr(8, 2)) || !decimal_digits(value.substr(11, 2)) ||
      !decimal_digits(value.substr(14, 2)) || !decimal_digits(value.substr(17, 2)) ||
      !decimal_digits(value.substr(20, 9))) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::canonical_encoding,
                                        std::string{field} + " is not a canonical timestamp"));
  }
  const auto date = year{static_cast<int>(parse_small_decimal(value.substr(0, 4)))} /
                    month{parse_small_decimal(value.substr(5, 2))} /
                    day{parse_small_decimal(value.substr(8, 2))};
  const auto hour = parse_small_decimal(value.substr(11, 2));
  const auto minute = parse_small_decimal(value.substr(14, 2));
  const auto second = parse_small_decimal(value.substr(17, 2));
  const auto nanosecond = parse_small_decimal(value.substr(20, 9));
  if (!date.ok() || static_cast<int>(date.year()) == 0 || hour > 23U || minute > 59U ||
      second > 59U) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::canonical_encoding,
                                        std::string{field} + " is not a valid v1 timestamp"));
  }
  return Timestamp{sys_days{date} + hours{hour} + minutes{minute} + seconds{second} +
                   nanoseconds{nanosecond}};
}

} // namespace decode_detail
} // namespace luca::serialization
