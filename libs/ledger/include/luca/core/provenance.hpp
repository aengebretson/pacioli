#pragma once

#include "luca/core/error.hpp"
#include "luca/core/identifiers.hpp"

#include <cstddef>
#include <expected>
#include <optional>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace luca {

class Provenance {
 public:
  static constexpr std::size_t max_metadata_size = 1024;

  [[nodiscard]] static std::expected<Provenance, ValueError> create(
      std::vector<SourceRecordId> source_records, std::string transformation_name,
      std::string transformation_version,
      std::optional<std::string> transformation_metadata = std::nullopt) {
    if (source_records.empty())
      return std::unexpected(ValueError::empty_source_records);
    for (const auto& id : source_records)
      if (id.value().empty()) return std::unexpected(ValueError::empty_identifier);
    if (transformation_name.empty() || transformation_version.empty())
      return std::unexpected(ValueError::empty_required_field);
    if (transformation_metadata && transformation_metadata->size() > max_metadata_size)
      return std::unexpected(ValueError::metadata_too_large);
    return Provenance(std::move(source_records), std::move(transformation_name),
                      std::move(transformation_version),
                      std::move(transformation_metadata));
  }

  [[nodiscard]] std::span<const SourceRecordId> source_records() const noexcept {
    return source_records_;
  }
  [[nodiscard]] const std::string& transformation_name() const noexcept {
    return transformation_name_;
  }
  [[nodiscard]] const std::string& transformation_version() const noexcept {
    return transformation_version_;
  }
  [[nodiscard]] const std::optional<std::string>& transformation_metadata() const noexcept {
    return transformation_metadata_;
  }
  bool operator==(const Provenance&) const = default;

 private:
  Provenance(std::vector<SourceRecordId> source_records, std::string name,
             std::string version, std::optional<std::string> metadata)
      : source_records_(std::move(source_records)), transformation_name_(std::move(name)),
        transformation_version_(std::move(version)),
        transformation_metadata_(std::move(metadata)) {}

  std::vector<SourceRecordId> source_records_;
  std::string transformation_name_;
  std::string transformation_version_;
  std::optional<std::string> transformation_metadata_;
};

}  // namespace luca
