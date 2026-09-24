#pragma once

#include "luca/portfolio/checkpoint_serialization.hpp"
#include "luca/portfolio/serialization_decode.hpp"

#include <cstddef>
#include <cstdint>
#include <expected>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca::serialization {
namespace checkpoint_decode_detail {

[[nodiscard]] inline DecodeError domain_error(decode_detail::Reader &reader,
                                              const CheckpointError &error) {
  auto category = DecodeDiagnosticCategory::canonical_encoding;
  switch (error.category()) {
  case CheckpointDiagnosticCategory::duplicate_identity:
    category = DecodeDiagnosticCategory::duplicate_identity;
    break;
  case CheckpointDiagnosticCategory::inconsistent_lineage:
    category = DecodeDiagnosticCategory::lineage_reference_missing;
    break;
  case CheckpointDiagnosticCategory::invalid_prefix:
  case CheckpointDiagnosticCategory::invalid_watermark:
    category = DecodeDiagnosticCategory::schema_shape;
    break;
  case CheckpointDiagnosticCategory::invalid_text:
  case CheckpointDiagnosticCategory::invalid_digest:
  case CheckpointDiagnosticCategory::invalid_timestamp:
  case CheckpointDiagnosticCategory::invalid_date:
  case CheckpointDiagnosticCategory::empty_partition:
    break;
  }
  return reader.error(category, "decoded checkpoint value is invalid: " + error.message());
}

template <class Value>
[[nodiscard]] inline std::expected<Value, DecodeError>
validated(decode_detail::Reader &reader, std::expected<Value, CheckpointError> value) {
  if (!value)
    return std::unexpected(domain_error(reader, value.error()));
  return std::move(*value);
}

[[nodiscard]] inline std::expected<Sha256Digest, DecodeError>
read_digest(decode_detail::Reader &reader, std::string_view field) {
  auto text = reader.read_text();
  if (!text)
    return std::unexpected(text.error());
  auto result = Sha256Digest::create(*text);
  if (!result) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::canonical_encoding,
                                        std::string{field} + " is not a lowercase SHA-256 digest"));
  }
  return *result;
}

[[nodiscard]] inline std::expected<CheckpointIdentity, DecodeError>
read_identity(decode_detail::Reader &reader, std::string_view field) {
  auto shape = reader.read_map(2U, field);
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("id", previous);
  if (!key)
    return std::unexpected(key.error());
  auto id = decode_detail::read_required_text(reader, "checkpoint identity id");
  if (!id)
    return std::unexpected(id.error());

  key = reader.read_key("version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto version = decode_detail::read_required_text(reader, "checkpoint identity version");
  if (!version)
    return std::unexpected(version.error());

  return validated(reader, CheckpointIdentity::create(*id, *version));
}

[[nodiscard]] inline std::expected<CheckpointInput, DecodeError>
read_input(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "checkpoint input");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("digest", previous);
  if (!key)
    return std::unexpected(key.error());
  auto digest = read_digest(reader, "checkpoint input digest");
  if (!digest)
    return std::unexpected(digest.error());

  key = reader.read_key("id", previous);
  if (!key)
    return std::unexpected(key.error());
  auto id = decode_detail::read_required_text(reader, "checkpoint input id");
  if (!id)
    return std::unexpected(id.error());

  key = reader.read_key("version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto version = decode_detail::read_required_text(reader, "checkpoint input version");
  if (!version)
    return std::unexpected(version.error());

  return validated(reader, CheckpointInput::create(*id, *version, *digest));
}

[[nodiscard]] inline bool input_less(const CheckpointInput &left,
                                     const CheckpointInput &right) noexcept {
  if (left.id() != right.id())
    return decode_detail::raw_bytes_less(left.id(), right.id());
  return decode_detail::raw_bytes_less(left.version(), right.version());
}

[[nodiscard]] inline std::expected<std::vector<CheckpointInput>, DecodeError>
read_inputs(decode_detail::Reader &reader, std::string_view field) {
  auto count = reader.read_array_count(field);
  if (!count)
    return std::unexpected(count.error());
  std::vector<CheckpointInput> values;
  values.reserve(*count);
  for (std::size_t index = 0; index < *count; ++index) {
    auto input = read_input(reader);
    if (!input)
      return std::unexpected(input.error());
    values.push_back(std::move(*input));
    if (values.size() < 2U)
      continue;
    const auto &left = values[values.size() - 2U];
    const auto &right = values.back();
    if (left.id() == right.id() && left.version() == right.version()) {
      return std::unexpected(
          reader.error(DecodeDiagnosticCategory::duplicate_identity,
                       std::string{field} + " contains a duplicate id and version"));
    }
    if (!input_less(left, right)) {
      return std::unexpected(
          reader.error(DecodeDiagnosticCategory::deterministic_ordering,
                       std::string{field} + " is not in canonical identity order"));
    }
  }
  return values;
}

[[nodiscard]] inline std::expected<CheckpointEvaluationContext, DecodeError>
read_context(decode_detail::Reader &reader) {
  auto shape = reader.read_map(9U, CheckpointEvaluationContext::schema_version);
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("calendar_inputs", previous);
  if (!key)
    return std::unexpected(key.error());
  auto calendars = read_inputs(reader, "calendar inputs");
  if (!calendars)
    return std::unexpected(calendars.error());

  key = reader.read_key("economic_as_of", previous);
  if (!key)
    return std::unexpected(key.error());
  auto economic_text = reader.read_text();
  if (!economic_text)
    return std::unexpected(economic_text.error());
  auto economic = decode_detail::parse_timestamp(reader, *economic_text, "economic as-of");
  if (!economic)
    return std::unexpected(economic.error());

  key = reader.read_key("fx_inputs", previous);
  if (!key)
    return std::unexpected(key.error());
  auto fx = read_inputs(reader, "FX inputs");
  if (!fx)
    return std::unexpected(fx.error());

  key = reader.read_key("price_inputs", previous);
  if (!key)
    return std::unexpected(key.error());
  auto prices = read_inputs(reader, "price inputs");
  if (!prices)
    return std::unexpected(prices.error());

  key = reader.read_key("recorded_through", previous);
  if (!key)
    return std::unexpected(key.error());
  auto recorded_text = reader.read_text();
  if (!recorded_text)
    return std::unexpected(recorded_text.error());
  auto recorded = decode_detail::parse_timestamp(reader, *recorded_text, "recorded-through");
  if (!recorded)
    return std::unexpected(recorded.error());

  key = reader.read_key("reference_data_inputs", previous);
  if (!key)
    return std::unexpected(key.error());
  auto references = read_inputs(reader, "reference-data inputs");
  if (!references)
    return std::unexpected(references.error());

  key = reader.read_key("rounding_inputs", previous);
  if (!key)
    return std::unexpected(key.error());
  auto rounding = read_inputs(reader, "rounding inputs");
  if (!rounding)
    return std::unexpected(rounding.error());

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != CheckpointEvaluationContext::schema_version) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "evaluation-context schema version is not supported"));
  }

  key = reader.read_key("settlement_as_of_date", previous);
  if (!key)
    return std::unexpected(key.error());
  auto settlement_text = reader.read_text();
  if (!settlement_text)
    return std::unexpected(settlement_text.error());
  auto settlement = decode_detail::parse_date(reader, *settlement_text, "settlement as-of date");
  if (!settlement)
    return std::unexpected(settlement.error());

  return validated(reader, CheckpointEvaluationContext::create(*recorded, *economic, *settlement,
                                                               *references, *prices, *calendars,
                                                               *rounding, *fx));
}

[[nodiscard]] inline std::expected<CheckpointEventPrefix, DecodeError>
read_prefix(decode_detail::Reader &reader) {
  auto shape = reader.read_map(7U, "checkpoint event prefix");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("canonical_input_digest", previous);
  if (!key)
    return std::unexpected(key.error());
  auto digest = read_digest(reader, "canonical input digest");
  if (!digest)
    return std::unexpected(digest.error());

  key = reader.read_key("first_sequence", previous);
  if (!key)
    return std::unexpected(key.error());
  auto first_text = reader.read_text();
  if (!first_text)
    return std::unexpected(first_text.error());
  auto first = decode_detail::parse_positive_decimal(reader, *first_text, "first sequence");
  if (!first)
    return std::unexpected(first.error());

  key = reader.read_key("kind", previous);
  if (!key)
    return std::unexpected(key.error());
  auto kind = reader.read_text();
  if (!kind)
    return std::unexpected(kind.error());
  if (*kind != CheckpointEventPrefix::kind) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "checkpoint-prefix kind is not supported"));
  }

  key = reader.read_key("last_record_id", previous);
  if (!key)
    return std::unexpected(key.error());
  auto last_record_id =
      decode_detail::read_required_text(reader, "checkpoint-prefix last record id");
  if (!last_record_id)
    return std::unexpected(last_record_id.error());

  key = reader.read_key("last_sequence", previous);
  if (!key)
    return std::unexpected(key.error());
  auto last_text = reader.read_text();
  if (!last_text)
    return std::unexpected(last_text.error());
  auto last = decode_detail::parse_positive_decimal(reader, *last_text, "last sequence");
  if (!last)
    return std::unexpected(last.error());

  key = reader.read_key("record_count", previous);
  if (!key)
    return std::unexpected(key.error());
  auto count_text = reader.read_text();
  if (!count_text)
    return std::unexpected(count_text.error());
  auto count = decode_detail::parse_positive_decimal(reader, *count_text, "record count");
  if (!count)
    return std::unexpected(count.error());

  key = reader.read_key("record_schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto record_schema = reader.read_text();
  if (!record_schema)
    return std::unexpected(record_schema.error());
  if (*record_schema != CheckpointEventPrefix::record_schema_version) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "checkpoint record schema version is not supported"));
  }

  return validated(reader,
                   CheckpointEventPrefix::create(*first, *last, *count,
                                                 EventId{std::string{*last_record_id}}, *digest));
}

template <class IdentifierType>
[[nodiscard]] inline std::expected<std::vector<IdentifierType>, DecodeError>
read_identifiers(decode_detail::Reader &reader, std::string_view field) {
  auto count = reader.read_array_count(field);
  if (!count)
    return std::unexpected(count.error());
  std::vector<IdentifierType> values;
  values.reserve(*count);
  for (std::size_t index = 0; index < *count; ++index) {
    auto text = decode_detail::read_required_text(reader, field);
    if (!text)
      return std::unexpected(text.error());
    values.emplace_back(std::string{*text});
  }
  return values;
}

[[nodiscard]] inline std::expected<CheckpointLineage, DecodeError>
read_lineage(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "checkpoint lineage");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("active_record_ids", previous);
  if (!key)
    return std::unexpected(key.error());
  auto active = read_identifiers<EventId>(reader, "active-record lineage");
  if (!active)
    return std::unexpected(active.error());

  key = reader.read_key("lifecycle_record_ids", previous);
  if (!key)
    return std::unexpected(key.error());
  auto lifecycle = read_identifiers<EventId>(reader, "lifecycle-record lineage");
  if (!lifecycle)
    return std::unexpected(lifecycle.error());

  key = reader.read_key("source_record_ids", previous);
  if (!key)
    return std::unexpected(key.error());
  auto sources = read_identifiers<SourceRecordId>(reader, "source-record lineage");
  if (!sources)
    return std::unexpected(sources.error());

  return validated(reader, CheckpointLineage::create(*lifecycle, *active, *sources));
}

[[nodiscard]] inline std::expected<AccountSetPartition, DecodeError>
read_partition(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "account-set partition");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("definition", previous);
  if (!key)
    return std::unexpected(key.error());
  auto definition = reader.read_text();
  if (!definition)
    return std::unexpected(definition.error());
  if (*definition != AccountSetPartition::definition) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "partition definition is not supported"));
  }

  key = reader.read_key("keys", previous);
  if (!key)
    return std::unexpected(key.error());
  auto keys = read_identifiers<AccountId>(reader, "partition keys");
  if (!keys)
    return std::unexpected(keys.error());
  for (std::size_t index = 1; index < keys->size(); ++index) {
    if ((*keys)[index - 1U] == (*keys)[index]) {
      return std::unexpected(reader.error(DecodeDiagnosticCategory::duplicate_identity,
                                          "partition contains a duplicate account key"));
    }
    if (!decode_detail::raw_bytes_less((*keys)[index - 1U].value(), (*keys)[index].value())) {
      return std::unexpected(reader.error(DecodeDiagnosticCategory::deterministic_ordering,
                                          "partition keys are not in canonical order"));
    }
  }

  key = reader.read_key("version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto version = reader.read_text();
  if (!version)
    return std::unexpected(version.error());
  if (*version != AccountSetPartition::version) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "partition version is not supported"));
  }

  return validated(reader, AccountSetPartition::create(*keys));
}

[[nodiscard]] inline std::expected<ResolvedEventWatermark, DecodeError>
read_watermark(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "resolved-event watermark");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("acceptance_sequence", previous);
  if (!key)
    return std::unexpected(key.error());
  auto sequence_text = reader.read_text();
  if (!sequence_text)
    return std::unexpected(sequence_text.error());
  auto sequence =
      decode_detail::parse_positive_decimal(reader, *sequence_text, "watermark sequence");
  if (!sequence)
    return std::unexpected(sequence.error());

  key = reader.read_key("effective_at", previous);
  if (!key)
    return std::unexpected(key.error());
  auto effective_text = reader.read_text();
  if (!effective_text)
    return std::unexpected(effective_text.error());
  auto effective =
      decode_detail::parse_timestamp(reader, *effective_text, "watermark effective time");
  if (!effective)
    return std::unexpected(effective.error());

  key = reader.read_key("record_id", previous);
  if (!key)
    return std::unexpected(key.error());
  auto record = decode_detail::read_required_text(reader, "watermark record id");
  if (!record)
    return std::unexpected(record.error());

  return validated(
      reader, ResolvedEventWatermark::create(*effective, *sequence, EventId{std::string{*record}}));
}

[[nodiscard]] inline std::expected<CheckpointManifest, DecodeError>
read_manifest(decode_detail::Reader &reader) {
  auto shape = reader.read_map(12U, CheckpointManifest::schema_version);
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("canonical_state_digest", previous);
  if (!key)
    return std::unexpected(key.error());
  auto state_digest = read_digest(reader, "canonical state digest");
  if (!state_digest)
    return std::unexpected(state_digest.error());

  key = reader.read_key("digest_algorithm", previous);
  if (!key)
    return std::unexpected(key.error());
  auto algorithm = reader.read_text();
  if (!algorithm)
    return std::unexpected(algorithm.error());
  if (*algorithm != CheckpointManifest::digest_algorithm) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "checkpoint digest algorithm is not supported"));
  }

  key = reader.read_key("engine_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto engine = decode_detail::read_required_text(reader, "engine version");
  if (!engine)
    return std::unexpected(engine.error());

  key = reader.read_key("evaluation_context", previous);
  if (!key)
    return std::unexpected(key.error());
  auto context = read_context(reader);
  if (!context)
    return std::unexpected(context.error());

  key = reader.read_key("event_prefix", previous);
  if (!key)
    return std::unexpected(key.error());
  auto prefix = read_prefix(reader);
  if (!prefix)
    return std::unexpected(prefix.error());

  key = reader.read_key("lineage", previous);
  if (!key)
    return std::unexpected(key.error());
  auto lineage = read_lineage(reader);
  if (!lineage)
    return std::unexpected(lineage.error());

  key = reader.read_key("partition", previous);
  if (!key)
    return std::unexpected(key.error());
  auto partition = read_partition(reader);
  if (!partition)
    return std::unexpected(partition.error());

  key = reader.read_key("policy", previous);
  if (!key)
    return std::unexpected(key.error());
  auto policy = read_identity(reader, "checkpoint policy");
  if (!policy)
    return std::unexpected(policy.error());

  key = reader.read_key("projection", previous);
  if (!key)
    return std::unexpected(key.error());
  auto projection = read_identity(reader, "checkpoint projection");
  if (!projection)
    return std::unexpected(projection.error());

  key = reader.read_key("resolved_event_watermark", previous);
  if (!key)
    return std::unexpected(key.error());
  auto watermark = read_watermark(reader);
  if (!watermark)
    return std::unexpected(watermark.error());

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != CheckpointManifest::schema_version) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "checkpoint-manifest schema version is not supported"));
  }

  key = reader.read_key("serialization_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto serialization = reader.read_text();
  if (!serialization)
    return std::unexpected(serialization.error());
  if (*serialization != CheckpointManifest::serialization_version) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "checkpoint serialization version is not supported"));
  }

  return validated(reader,
                   CheckpointManifest::create(*projection, *engine, *policy, *partition, *prefix,
                                              *context, *state_digest, *watermark, *lineage));
}

} // namespace checkpoint_decode_detail

[[nodiscard]] inline std::expected<CheckpointManifest, DecodeError>
decode_checkpoint_manifest(std::span<const std::byte> input) {
  decode_detail::Reader reader{input};
  if (auto header = reader.read_header(); !header)
    return std::unexpected(header.error());
  auto manifest = checkpoint_decode_detail::read_manifest(reader);
  if (!manifest)
    return std::unexpected(manifest.error());
  if (auto complete = reader.finish(); !complete)
    return std::unexpected(complete.error());
  return manifest;
}

} // namespace luca::serialization
