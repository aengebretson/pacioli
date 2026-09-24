#pragma once

#include "luca/core/identifiers.hpp"
#include "luca/serialization/unicode_nfc.hpp"
#include "luca/time.hpp"

#include <algorithm>
#include <chrono>
#include <compare>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <limits>
#include <ranges>
#include <span>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

namespace luca {

namespace checkpoint_detail {
struct CheckpointValidation;
}

enum class CheckpointDiagnosticCategory {
  invalid_text,
  invalid_digest,
  invalid_timestamp,
  invalid_date,
  duplicate_identity,
  empty_partition,
  invalid_prefix,
  invalid_watermark,
  inconsistent_lineage,
};

[[nodiscard]] constexpr std::string_view
category_name(CheckpointDiagnosticCategory category) noexcept {
  switch (category) {
  case CheckpointDiagnosticCategory::invalid_text:
    return "invalid_text";
  case CheckpointDiagnosticCategory::invalid_digest:
    return "invalid_digest";
  case CheckpointDiagnosticCategory::invalid_timestamp:
    return "invalid_timestamp";
  case CheckpointDiagnosticCategory::invalid_date:
    return "invalid_date";
  case CheckpointDiagnosticCategory::duplicate_identity:
    return "duplicate_identity";
  case CheckpointDiagnosticCategory::empty_partition:
    return "empty_partition";
  case CheckpointDiagnosticCategory::invalid_prefix:
    return "invalid_prefix";
  case CheckpointDiagnosticCategory::invalid_watermark:
    return "invalid_watermark";
  case CheckpointDiagnosticCategory::inconsistent_lineage:
    return "inconsistent_lineage";
  }
  return "invalid_text";
}

class CheckpointError {
public:
  [[nodiscard]] CheckpointDiagnosticCategory category() const noexcept { return category_; }
  [[nodiscard]] std::string_view category_name() const noexcept {
    return luca::category_name(category_);
  }
  [[nodiscard]] const std::string &message() const noexcept { return message_; }

private:
  friend struct checkpoint_detail::CheckpointValidation;

  CheckpointError(CheckpointDiagnosticCategory category, std::string message)
      : category_(category), message_(std::move(message)) {}

  CheckpointDiagnosticCategory category_;
  std::string message_;
};

namespace checkpoint_detail {

struct CheckpointValidation {
  [[nodiscard]] static CheckpointError error(CheckpointDiagnosticCategory category,
                                             std::string message) {
    return CheckpointError{category, std::move(message)};
  }
};

[[nodiscard]] inline std::expected<void, CheckpointError> validate_text(std::string_view value,
                                                                        std::string_view field) {
  if (value.empty()) {
    return std::unexpected(CheckpointValidation::error(CheckpointDiagnosticCategory::invalid_text,
                                                       std::string{field} + " must not be empty"));
  }
  if (value.find('\0') != std::string_view::npos) {
    return std::unexpected(CheckpointValidation::error(
        CheckpointDiagnosticCategory::invalid_text, std::string{field} + " must not contain NUL"));
  }
  if (value.size() > std::numeric_limits<std::uint32_t>::max()) {
    return std::unexpected(CheckpointValidation::error(
        CheckpointDiagnosticCategory::invalid_text,
        std::string{field} + " exceeds the v1 unsigned 32-bit text limit"));
  }
  switch (serialization::detail::unicode_nfc::validate(value)) {
  case serialization::detail::unicode_nfc::ValidationResult::valid:
    return {};
  case serialization::detail::unicode_nfc::ValidationResult::invalid_utf8:
    return std::unexpected(CheckpointValidation::error(
        CheckpointDiagnosticCategory::invalid_text, std::string{field} + " must be valid UTF-8"));
  case serialization::detail::unicode_nfc::ValidationResult::not_nfc:
    return std::unexpected(
        CheckpointValidation::error(CheckpointDiagnosticCategory::invalid_text,
                                    std::string{field} + " must be NFC-normalized"));
  }
  return std::unexpected(CheckpointValidation::error(CheckpointDiagnosticCategory::invalid_text,
                                                     std::string{field} + " is invalid"));
}

[[nodiscard]] inline bool utf8_bytes_less(std::string_view left, std::string_view right) noexcept {
  return std::lexicographical_compare(
      left.begin(), left.end(), right.begin(), right.end(), [](char left_byte, char right_byte) {
        return static_cast<unsigned char>(left_byte) < static_cast<unsigned char>(right_byte);
      });
}

[[nodiscard]] inline bool valid_canonical_year(std::chrono::year_month_day value) noexcept {
  const auto year = static_cast<int>(value.year());
  return value.ok() && year >= 1 && year <= 9999;
}

[[nodiscard]] inline std::expected<void, CheckpointError>
validate_timestamp(Timestamp value, std::string_view field) {
  const auto date = std::chrono::year_month_day{std::chrono::floor<std::chrono::days>(value)};
  if (!valid_canonical_year(date)) {
    return std::unexpected(CheckpointValidation::error(
        CheckpointDiagnosticCategory::invalid_timestamp,
        std::string{field} + " must be representable as a v1 timestamp"));
  }
  return {};
}

[[nodiscard]] inline std::expected<void, CheckpointError> validate_date(SettlementDate value,
                                                                        std::string_view field) {
  if (!valid_canonical_year(value.value())) {
    return std::unexpected(
        CheckpointValidation::error(CheckpointDiagnosticCategory::invalid_date,
                                    std::string{field} + " must be representable as a v1 date"));
  }
  return {};
}

template <class Values, class ValueOf>
[[nodiscard]] inline bool has_duplicates(const Values &values, ValueOf value_of) {
  std::unordered_set<std::string_view> seen;
  seen.reserve(values.size());
  for (const auto &value : values) {
    if (!seen.emplace(value_of(value)).second)
      return true;
  }
  return false;
}

} // namespace checkpoint_detail

class Sha256Digest {
public:
  [[nodiscard]] static std::expected<Sha256Digest, CheckpointError> create(std::string_view value) {
    if (value.size() != 64 || !std::ranges::all_of(value, [](char digit) {
          return (digit >= '0' && digit <= '9') || (digit >= 'a' && digit <= 'f');
        })) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_digest,
          "digest must be exactly 64 lowercase SHA-256 hexadecimal characters"));
    }
    return Sha256Digest{std::string{value}};
  }

  [[nodiscard]] const std::string &value() const noexcept { return value_; }
  auto operator<=>(const Sha256Digest &) const = default;

private:
  explicit Sha256Digest(std::string value) : value_(std::move(value)) {}
  std::string value_;
};

class CheckpointIdentity {
public:
  [[nodiscard]] static std::expected<CheckpointIdentity, CheckpointError>
  create(std::string_view id, std::string_view version) {
    if (auto valid = checkpoint_detail::validate_text(id, "identity id"); !valid)
      return std::unexpected(valid.error());
    if (auto valid = checkpoint_detail::validate_text(version, "identity version"); !valid)
      return std::unexpected(valid.error());
    return CheckpointIdentity{std::string{id}, std::string{version}};
  }

  [[nodiscard]] const std::string &id() const noexcept { return id_; }
  [[nodiscard]] const std::string &version() const noexcept { return version_; }
  bool operator==(const CheckpointIdentity &) const = default;

private:
  CheckpointIdentity(std::string id, std::string version)
      : id_(std::move(id)), version_(std::move(version)) {}

  std::string id_;
  std::string version_;
};

class CheckpointInput {
public:
  [[nodiscard]] static std::expected<CheckpointInput, CheckpointError>
  create(std::string_view id, std::string_view version, const Sha256Digest &digest) {
    if (auto valid = checkpoint_detail::validate_text(id, "input id"); !valid)
      return std::unexpected(valid.error());
    if (auto valid = checkpoint_detail::validate_text(version, "input version"); !valid)
      return std::unexpected(valid.error());
    return CheckpointInput{std::string{id}, std::string{version}, digest};
  }

  [[nodiscard]] const std::string &id() const noexcept { return id_; }
  [[nodiscard]] const std::string &version() const noexcept { return version_; }
  [[nodiscard]] const Sha256Digest &digest() const noexcept { return digest_; }
  bool operator==(const CheckpointInput &) const = default;

private:
  CheckpointInput(std::string id, std::string version, Sha256Digest digest)
      : id_(std::move(id)), version_(std::move(version)), digest_(std::move(digest)) {}

  std::string id_;
  std::string version_;
  Sha256Digest digest_;
};

class AccountSetPartition {
public:
  static constexpr std::string_view definition = "account-set";
  static constexpr std::string_view version = "1";

  [[nodiscard]] static std::expected<AccountSetPartition, CheckpointError>
  create(const std::vector<AccountId> &keys) {
    if (keys.empty()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::empty_partition,
          "account-set partition keys must not be empty"));
    }
    for (const auto &key : keys) {
      if (auto valid = checkpoint_detail::validate_text(key.value(), "partition key"); !valid)
        return std::unexpected(valid.error());
    }

    auto canonical = keys;
    std::ranges::sort(canonical, [](const AccountId &left, const AccountId &right) {
      return checkpoint_detail::utf8_bytes_less(left.value(), right.value());
    });
    if (std::ranges::adjacent_find(canonical) != canonical.end()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::duplicate_identity,
          "account-set partition keys must be unique"));
    }
    return AccountSetPartition{std::move(canonical)};
  }

  [[nodiscard]] std::span<const AccountId> keys() const noexcept { return keys_; }
  bool operator==(const AccountSetPartition &) const = default;

private:
  explicit AccountSetPartition(std::vector<AccountId> keys) : keys_(std::move(keys)) {}
  std::vector<AccountId> keys_;
};

class CheckpointEventPrefix {
public:
  static constexpr std::string_view kind = "acceptance_sequence_inclusive";
  static constexpr std::string_view record_schema_version = "luca.lifecycle-record.v1";

  [[nodiscard]] static std::expected<CheckpointEventPrefix, CheckpointError>
  create(std::uint64_t first_sequence, std::uint64_t last_sequence, std::uint64_t record_count,
         const EventId &last_record_id, const Sha256Digest &canonical_input_digest) {
    if (first_sequence != 1 || last_sequence < first_sequence || record_count == 0 ||
        last_sequence - first_sequence != record_count - 1) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_prefix,
          "event prefix must be one non-empty contiguous inclusive sequence beginning at one"));
    }
    if (auto valid = checkpoint_detail::validate_text(last_record_id.value(), "last record id");
        !valid)
      return std::unexpected(valid.error());
    return CheckpointEventPrefix{first_sequence, last_sequence, record_count, last_record_id,
                                 canonical_input_digest};
  }

  [[nodiscard]] std::uint64_t first_sequence() const noexcept { return first_sequence_; }
  [[nodiscard]] std::uint64_t last_sequence() const noexcept { return last_sequence_; }
  [[nodiscard]] std::uint64_t record_count() const noexcept { return record_count_; }
  [[nodiscard]] const EventId &last_record_id() const noexcept { return last_record_id_; }
  [[nodiscard]] const Sha256Digest &canonical_input_digest() const noexcept {
    return canonical_input_digest_;
  }
  bool operator==(const CheckpointEventPrefix &) const = default;

private:
  CheckpointEventPrefix(std::uint64_t first_sequence, std::uint64_t last_sequence,
                        std::uint64_t record_count, EventId last_record_id,
                        Sha256Digest canonical_input_digest)
      : first_sequence_(first_sequence), last_sequence_(last_sequence), record_count_(record_count),
        last_record_id_(std::move(last_record_id)),
        canonical_input_digest_(std::move(canonical_input_digest)) {}

  std::uint64_t first_sequence_;
  std::uint64_t last_sequence_;
  std::uint64_t record_count_;
  EventId last_record_id_;
  Sha256Digest canonical_input_digest_;
};

class CheckpointEvaluationContext {
public:
  static constexpr std::string_view schema_version = "luca.evaluation-context.v1";

  [[nodiscard]] static std::expected<CheckpointEvaluationContext, CheckpointError>
  create(Timestamp recorded_through, Timestamp economic_as_of, SettlementDate settlement_as_of_date,
         const std::vector<CheckpointInput> &reference_data_inputs = {},
         const std::vector<CheckpointInput> &price_inputs = {},
         const std::vector<CheckpointInput> &calendar_inputs = {},
         const std::vector<CheckpointInput> &rounding_inputs = {},
         const std::vector<CheckpointInput> &fx_inputs = {}) {
    if (auto valid = checkpoint_detail::validate_timestamp(recorded_through, "recorded through");
        !valid)
      return std::unexpected(valid.error());
    if (auto valid = checkpoint_detail::validate_timestamp(economic_as_of, "economic as of");
        !valid)
      return std::unexpected(valid.error());
    if (auto valid =
            checkpoint_detail::validate_date(settlement_as_of_date, "settlement as-of date");
        !valid)
      return std::unexpected(valid.error());

    auto reference_data = canonical_inputs(reference_data_inputs, "reference-data inputs");
    if (!reference_data)
      return std::unexpected(reference_data.error());
    auto prices = canonical_inputs(price_inputs, "price inputs");
    if (!prices)
      return std::unexpected(prices.error());
    auto calendars = canonical_inputs(calendar_inputs, "calendar inputs");
    if (!calendars)
      return std::unexpected(calendars.error());
    auto rounding = canonical_inputs(rounding_inputs, "rounding inputs");
    if (!rounding)
      return std::unexpected(rounding.error());
    auto fx = canonical_inputs(fx_inputs, "FX inputs");
    if (!fx)
      return std::unexpected(fx.error());

    return CheckpointEvaluationContext{recorded_through,      economic_as_of,
                                       settlement_as_of_date, std::move(*reference_data),
                                       std::move(*prices),    std::move(*calendars),
                                       std::move(*rounding),  std::move(*fx)};
  }

  [[nodiscard]] Timestamp recorded_through() const noexcept { return recorded_through_; }
  [[nodiscard]] Timestamp economic_as_of() const noexcept { return economic_as_of_; }
  [[nodiscard]] SettlementDate settlement_as_of_date() const noexcept {
    return settlement_as_of_date_;
  }
  [[nodiscard]] std::span<const CheckpointInput> reference_data_inputs() const noexcept {
    return reference_data_inputs_;
  }
  [[nodiscard]] std::span<const CheckpointInput> price_inputs() const noexcept {
    return price_inputs_;
  }
  [[nodiscard]] std::span<const CheckpointInput> calendar_inputs() const noexcept {
    return calendar_inputs_;
  }
  [[nodiscard]] std::span<const CheckpointInput> rounding_inputs() const noexcept {
    return rounding_inputs_;
  }
  [[nodiscard]] std::span<const CheckpointInput> fx_inputs() const noexcept { return fx_inputs_; }
  bool operator==(const CheckpointEvaluationContext &) const = default;

private:
  [[nodiscard]] static std::expected<std::vector<CheckpointInput>, CheckpointError>
  canonical_inputs(const std::vector<CheckpointInput> &inputs, std::string_view field) {
    auto canonical = inputs;
    std::ranges::sort(canonical, [](const CheckpointInput &left, const CheckpointInput &right) {
      if (left.id() != right.id())
        return checkpoint_detail::utf8_bytes_less(left.id(), right.id());
      return checkpoint_detail::utf8_bytes_less(left.version(), right.version());
    });
    const auto duplicate = std::ranges::adjacent_find(
        canonical, [](const CheckpointInput &left, const CheckpointInput &right) {
          return left.id() == right.id() && left.version() == right.version();
        });
    if (duplicate != canonical.end()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::duplicate_identity,
          std::string{field} + " must not repeat an id and version"));
    }
    return canonical;
  }

  CheckpointEvaluationContext(Timestamp recorded_through, Timestamp economic_as_of,
                              SettlementDate settlement_as_of_date,
                              std::vector<CheckpointInput> reference_data_inputs,
                              std::vector<CheckpointInput> price_inputs,
                              std::vector<CheckpointInput> calendar_inputs,
                              std::vector<CheckpointInput> rounding_inputs,
                              std::vector<CheckpointInput> fx_inputs)
      : recorded_through_(recorded_through), economic_as_of_(economic_as_of),
        settlement_as_of_date_(settlement_as_of_date),
        reference_data_inputs_(std::move(reference_data_inputs)),
        price_inputs_(std::move(price_inputs)), calendar_inputs_(std::move(calendar_inputs)),
        rounding_inputs_(std::move(rounding_inputs)), fx_inputs_(std::move(fx_inputs)) {}

  Timestamp recorded_through_;
  Timestamp economic_as_of_;
  SettlementDate settlement_as_of_date_;
  std::vector<CheckpointInput> reference_data_inputs_;
  std::vector<CheckpointInput> price_inputs_;
  std::vector<CheckpointInput> calendar_inputs_;
  std::vector<CheckpointInput> rounding_inputs_;
  std::vector<CheckpointInput> fx_inputs_;
};

class ResolvedEventWatermark {
public:
  [[nodiscard]] static std::expected<ResolvedEventWatermark, CheckpointError>
  create(Timestamp effective_at, std::uint64_t acceptance_sequence, const EventId &record_id) {
    if (auto valid = checkpoint_detail::validate_timestamp(effective_at, "watermark effective at");
        !valid)
      return std::unexpected(valid.error());
    if (acceptance_sequence == 0) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_watermark,
          "watermark acceptance sequence must be positive"));
    }
    if (auto valid = checkpoint_detail::validate_text(record_id.value(), "watermark record id");
        !valid)
      return std::unexpected(valid.error());
    return ResolvedEventWatermark{effective_at, acceptance_sequence, record_id};
  }

  [[nodiscard]] Timestamp effective_at() const noexcept { return effective_at_; }
  [[nodiscard]] std::uint64_t acceptance_sequence() const noexcept { return acceptance_sequence_; }
  [[nodiscard]] const EventId &record_id() const noexcept { return record_id_; }
  bool operator==(const ResolvedEventWatermark &) const = default;

private:
  ResolvedEventWatermark(Timestamp effective_at, std::uint64_t acceptance_sequence,
                         EventId record_id)
      : effective_at_(effective_at), acceptance_sequence_(acceptance_sequence),
        record_id_(std::move(record_id)) {}

  Timestamp effective_at_;
  std::uint64_t acceptance_sequence_;
  EventId record_id_;
};

class CheckpointLineage {
public:
  [[nodiscard]] static std::expected<CheckpointLineage, CheckpointError>
  create(const std::vector<EventId> &lifecycle_record_ids,
         const std::vector<EventId> &active_record_ids,
         const std::vector<SourceRecordId> &source_record_ids) {
    if (auto valid = validate_ids(lifecycle_record_ids, "lifecycle record lineage", true); !valid)
      return std::unexpected(valid.error());
    if (auto valid = validate_ids(active_record_ids, "active record lineage", true); !valid)
      return std::unexpected(valid.error());
    if (auto valid = validate_ids(source_record_ids, "source record lineage", true); !valid)
      return std::unexpected(valid.error());

    std::unordered_set<std::string_view> lifecycle_ids;
    lifecycle_ids.reserve(lifecycle_record_ids.size());
    for (const auto &record_id : lifecycle_record_ids)
      lifecycle_ids.emplace(record_id.value());
    for (const auto &record_id : active_record_ids) {
      if (!lifecycle_ids.contains(record_id.value())) {
        return std::unexpected(checkpoint_detail::CheckpointValidation::error(
            CheckpointDiagnosticCategory::inconsistent_lineage,
            "every active record must occur in lifecycle lineage"));
      }
    }
    return CheckpointLineage{lifecycle_record_ids, active_record_ids, source_record_ids};
  }

  [[nodiscard]] std::span<const EventId> lifecycle_record_ids() const noexcept {
    return lifecycle_record_ids_;
  }
  [[nodiscard]] std::span<const EventId> active_record_ids() const noexcept {
    return active_record_ids_;
  }
  [[nodiscard]] std::span<const SourceRecordId> source_record_ids() const noexcept {
    return source_record_ids_;
  }
  bool operator==(const CheckpointLineage &) const = default;

private:
  template <class IdentifierType>
  [[nodiscard]] static std::expected<void, CheckpointError>
  validate_ids(const std::vector<IdentifierType> &values, std::string_view field, bool nonempty) {
    if (nonempty && values.empty()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::inconsistent_lineage,
          std::string{field} + " must not be empty"));
    }
    for (const auto &value : values) {
      if (auto valid = checkpoint_detail::validate_text(value.value(), field); !valid)
        return std::unexpected(valid.error());
    }
    if (checkpoint_detail::has_duplicates(
            values, [](const IdentifierType &value) { return std::string_view{value.value()}; })) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::duplicate_identity,
          std::string{field} + " must not contain duplicate identities"));
    }
    return {};
  }

  CheckpointLineage(std::vector<EventId> lifecycle_record_ids,
                    std::vector<EventId> active_record_ids,
                    std::vector<SourceRecordId> source_record_ids)
      : lifecycle_record_ids_(std::move(lifecycle_record_ids)),
        active_record_ids_(std::move(active_record_ids)),
        source_record_ids_(std::move(source_record_ids)) {}

  std::vector<EventId> lifecycle_record_ids_;
  std::vector<EventId> active_record_ids_;
  std::vector<SourceRecordId> source_record_ids_;
};

class CheckpointManifest {
public:
  static constexpr std::string_view schema_version = "luca.checkpoint-manifest.v1";
  static constexpr std::string_view serialization_version = "luca.canonical-bytes.v1";
  static constexpr std::string_view digest_algorithm = "sha-256";

  [[nodiscard]] static std::expected<CheckpointManifest, CheckpointError>
  create(const CheckpointIdentity &projection, std::string_view engine_version,
         const CheckpointIdentity &policy, const AccountSetPartition &partition,
         const CheckpointEventPrefix &event_prefix,
         const CheckpointEvaluationContext &evaluation_context,
         const Sha256Digest &canonical_state_digest,
         const ResolvedEventWatermark &resolved_event_watermark, const CheckpointLineage &lineage) {
    if (auto valid = checkpoint_detail::validate_text(engine_version, "engine version"); !valid)
      return std::unexpected(valid.error());
    if (lineage.lifecycle_record_ids().size() != event_prefix.record_count() ||
        lineage.lifecycle_record_ids().back() != event_prefix.last_record_id()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::inconsistent_lineage,
          "lifecycle lineage must exactly describe the declared event prefix"));
    }
    if (resolved_event_watermark.acceptance_sequence() < event_prefix.first_sequence() ||
        resolved_event_watermark.acceptance_sequence() > event_prefix.last_sequence()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_watermark,
          "resolved-event watermark must lie within the declared event prefix"));
    }
    if (resolved_event_watermark.effective_at() > evaluation_context.economic_as_of()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_watermark,
          "resolved-event watermark effective time must not exceed the economic as-of time"));
    }

    const auto lifecycle = lineage.lifecycle_record_ids();
    const auto watermark_record =
        std::ranges::find(lifecycle, resolved_event_watermark.record_id());
    if (watermark_record == lifecycle.end()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::inconsistent_lineage,
          "resolved-event watermark record must occur in lifecycle lineage"));
    }
    const auto watermark_offset = static_cast<std::uint64_t>(watermark_record - lifecycle.begin());
    if (watermark_offset !=
        resolved_event_watermark.acceptance_sequence() - event_prefix.first_sequence()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::invalid_watermark,
          "resolved-event watermark sequence must identify its lifecycle record"));
    }
    if (lineage.active_record_ids().back() != resolved_event_watermark.record_id()) {
      return std::unexpected(checkpoint_detail::CheckpointValidation::error(
          CheckpointDiagnosticCategory::inconsistent_lineage,
          "resolved-event watermark must identify the last replay-ordered active record"));
    }

    return CheckpointManifest{projection,
                              std::string{engine_version},
                              policy,
                              partition,
                              event_prefix,
                              evaluation_context,
                              canonical_state_digest,
                              resolved_event_watermark,
                              lineage};
  }

  [[nodiscard]] const CheckpointIdentity &projection() const noexcept { return projection_; }
  [[nodiscard]] const std::string &engine_version() const noexcept { return engine_version_; }
  [[nodiscard]] const CheckpointIdentity &policy() const noexcept { return policy_; }
  [[nodiscard]] const AccountSetPartition &partition() const noexcept { return partition_; }
  [[nodiscard]] const CheckpointEventPrefix &event_prefix() const noexcept { return event_prefix_; }
  [[nodiscard]] const CheckpointEvaluationContext &evaluation_context() const noexcept {
    return evaluation_context_;
  }
  [[nodiscard]] const Sha256Digest &canonical_state_digest() const noexcept {
    return canonical_state_digest_;
  }
  [[nodiscard]] const ResolvedEventWatermark &resolved_event_watermark() const noexcept {
    return resolved_event_watermark_;
  }
  [[nodiscard]] const CheckpointLineage &lineage() const noexcept { return lineage_; }
  bool operator==(const CheckpointManifest &) const = default;

private:
  CheckpointManifest(CheckpointIdentity projection, std::string engine_version,
                     CheckpointIdentity policy, AccountSetPartition partition,
                     CheckpointEventPrefix event_prefix,
                     CheckpointEvaluationContext evaluation_context,
                     Sha256Digest canonical_state_digest,
                     ResolvedEventWatermark resolved_event_watermark, CheckpointLineage lineage)
      : projection_(std::move(projection)), engine_version_(std::move(engine_version)),
        policy_(std::move(policy)), partition_(std::move(partition)),
        event_prefix_(std::move(event_prefix)), evaluation_context_(std::move(evaluation_context)),
        canonical_state_digest_(std::move(canonical_state_digest)),
        resolved_event_watermark_(std::move(resolved_event_watermark)),
        lineage_(std::move(lineage)) {}

  CheckpointIdentity projection_;
  std::string engine_version_;
  CheckpointIdentity policy_;
  AccountSetPartition partition_;
  CheckpointEventPrefix event_prefix_;
  CheckpointEvaluationContext evaluation_context_;
  Sha256Digest canonical_state_digest_;
  ResolvedEventWatermark resolved_event_watermark_;
  CheckpointLineage lineage_;
};

} // namespace luca
