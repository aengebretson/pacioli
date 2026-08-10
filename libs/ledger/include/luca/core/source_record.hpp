#pragma once

#include "luca/core/error.hpp"
#include "luca/core/identifiers.hpp"

#include <chrono>
#include <expected>
#include <optional>
#include <string>
#include <utility>

namespace luca {

// An opaque digest supplied by an ingestion boundary. LUCA does not calculate or
// interpret the digest, but records its algorithm so the evidence can be verified.
class PayloadHash {
 public:
  [[nodiscard]] static std::expected<PayloadHash, ValueError> create(
      std::string algorithm, std::string value) {
    if (algorithm.empty() || value.empty())
      return std::unexpected(ValueError::empty_required_field);
    return PayloadHash(std::move(algorithm), std::move(value));
  }

  [[nodiscard]] const std::string& algorithm() const noexcept { return algorithm_; }
  [[nodiscard]] const std::string& value() const noexcept { return value_; }
  bool operator==(const PayloadHash&) const = default;

 private:
  PayloadHash(std::string algorithm, std::string value)
      : algorithm_(std::move(algorithm)), value_(std::move(value)) {}

  std::string algorithm_;
  std::string value_;
};

class SourceRecord {
 public:
  using Timestamp = std::chrono::sys_time<std::chrono::nanoseconds>;

  [[nodiscard]] static std::expected<SourceRecord, ValueError> create(
      SourceId source, SourceRecordId id, std::optional<std::string> external_record_id,
      Timestamp observed_at, std::optional<Timestamp> source_event_at,
      PayloadHash payload_hash, std::string kind,
      std::optional<std::string> source_reference = std::nullopt) {
    if (source.value().empty() || id.value().empty())
      return std::unexpected(ValueError::empty_identifier);
    if ((external_record_id && external_record_id->empty()) || kind.empty())
      return std::unexpected(ValueError::empty_required_field);
    return SourceRecord(std::move(source), std::move(id), std::move(external_record_id),
                        observed_at, source_event_at, std::move(payload_hash),
                        std::move(kind), std::move(source_reference));
  }

  [[nodiscard]] const SourceId& source() const noexcept { return source_; }
  [[nodiscard]] const SourceRecordId& id() const noexcept { return id_; }
  [[nodiscard]] const std::optional<std::string>& external_record_id() const noexcept {
    return external_record_id_;
  }
  [[nodiscard]] Timestamp observed_at() const noexcept { return observed_at_; }
  [[nodiscard]] const std::optional<Timestamp>& source_event_at() const noexcept {
    return source_event_at_;
  }
  [[nodiscard]] const PayloadHash& payload_hash() const noexcept { return payload_hash_; }
  [[nodiscard]] const std::string& kind() const noexcept { return kind_; }
  [[nodiscard]] const std::optional<std::string>& source_reference() const noexcept {
    return source_reference_;
  }
  bool operator==(const SourceRecord&) const = default;

 private:
  SourceRecord(SourceId source, SourceRecordId id,
               std::optional<std::string> external_record_id,
               Timestamp observed_at, std::optional<Timestamp> source_event_at,
               PayloadHash payload_hash, std::string kind,
               std::optional<std::string> source_reference)
      : source_(std::move(source)), id_(std::move(id)),
        external_record_id_(std::move(external_record_id)), observed_at_(observed_at),
        source_event_at_(source_event_at), payload_hash_(std::move(payload_hash)),
        kind_(std::move(kind)), source_reference_(std::move(source_reference)) {}

  SourceId source_;
  SourceRecordId id_;
  std::optional<std::string> external_record_id_;
  Timestamp observed_at_;
  std::optional<Timestamp> source_event_at_;
  PayloadHash payload_hash_;
  std::string kind_;
  std::optional<std::string> source_reference_;
};

}  // namespace luca
