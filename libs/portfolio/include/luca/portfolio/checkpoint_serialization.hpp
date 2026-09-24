#pragma once

#include "luca/portfolio/checkpoint.hpp"
#include "luca/serialization/canonical.hpp"

#include <cstdint>
#include <string>

namespace luca::serialization {
namespace detail {

inline void append_checkpoint_identity(CanonicalBytes &output, const CheckpointIdentity &value) {
  append_map(output, 2);
  append_key(output, "id");
  append_text(output, value.id());
  append_key(output, "version");
  append_text(output, value.version());
}

inline void append_checkpoint_input(CanonicalBytes &output, const CheckpointInput &value) {
  append_map(output, 3);
  append_key(output, "digest");
  append_text(output, value.digest().value());
  append_key(output, "id");
  append_text(output, value.id());
  append_key(output, "version");
  append_text(output, value.version());
}

inline void append_checkpoint_inputs(CanonicalBytes &output,
                                     std::span<const CheckpointInput> values) {
  append_array(output, static_cast<std::uint64_t>(values.size()));
  for (const auto &value : values)
    append_checkpoint_input(output, value);
}

inline void append_checkpoint_context(CanonicalBytes &output,
                                      const CheckpointEvaluationContext &value) {
  append_map(output, 9);
  append_key(output, "calendar_inputs");
  append_checkpoint_inputs(output, value.calendar_inputs());
  append_key(output, "economic_as_of");
  append_text(output, canonical_timestamp(value.economic_as_of()));
  append_key(output, "fx_inputs");
  append_checkpoint_inputs(output, value.fx_inputs());
  append_key(output, "price_inputs");
  append_checkpoint_inputs(output, value.price_inputs());
  append_key(output, "recorded_through");
  append_text(output, canonical_timestamp(value.recorded_through()));
  append_key(output, "reference_data_inputs");
  append_checkpoint_inputs(output, value.reference_data_inputs());
  append_key(output, "rounding_inputs");
  append_checkpoint_inputs(output, value.rounding_inputs());
  append_key(output, "schema_version");
  append_text(output, CheckpointEvaluationContext::schema_version);
  append_key(output, "settlement_as_of_date");
  append_text(output, canonical_date(value.settlement_as_of_date()));
}

inline void append_checkpoint_prefix(CanonicalBytes &output, const CheckpointEventPrefix &value) {
  append_map(output, 7);
  append_key(output, "canonical_input_digest");
  append_text(output, value.canonical_input_digest().value());
  append_key(output, "first_sequence");
  append_text(output, canonical_decimal(value.first_sequence()));
  append_key(output, "kind");
  append_text(output, CheckpointEventPrefix::kind);
  append_key(output, "last_record_id");
  append_text(output, value.last_record_id().value());
  append_key(output, "last_sequence");
  append_text(output, canonical_decimal(value.last_sequence()));
  append_key(output, "record_count");
  append_text(output, canonical_decimal(value.record_count()));
  append_key(output, "record_schema_version");
  append_text(output, CheckpointEventPrefix::record_schema_version);
}

template <class IdentifierType>
inline void append_checkpoint_lineage_ids(CanonicalBytes &output,
                                          std::span<const IdentifierType> values) {
  append_array(output, static_cast<std::uint64_t>(values.size()));
  for (const auto &value : values)
    append_text(output, value.value());
}

inline void append_checkpoint_lineage(CanonicalBytes &output, const CheckpointLineage &value) {
  append_map(output, 3);
  append_key(output, "active_record_ids");
  append_checkpoint_lineage_ids(output, value.active_record_ids());
  append_key(output, "lifecycle_record_ids");
  append_checkpoint_lineage_ids(output, value.lifecycle_record_ids());
  append_key(output, "source_record_ids");
  append_checkpoint_lineage_ids(output, value.source_record_ids());
}

inline void append_checkpoint_partition(CanonicalBytes &output, const AccountSetPartition &value) {
  append_map(output, 3);
  append_key(output, "definition");
  append_text(output, AccountSetPartition::definition);
  append_key(output, "keys");
  append_array(output, static_cast<std::uint64_t>(value.keys().size()));
  for (const auto &key : value.keys())
    append_text(output, key.value());
  append_key(output, "version");
  append_text(output, AccountSetPartition::version);
}

inline void append_resolved_event_watermark(CanonicalBytes &output,
                                            const ResolvedEventWatermark &value) {
  append_map(output, 3);
  append_key(output, "acceptance_sequence");
  append_text(output, canonical_decimal(value.acceptance_sequence()));
  append_key(output, "effective_at");
  append_text(output, canonical_timestamp(value.effective_at()));
  append_key(output, "record_id");
  append_text(output, value.record_id().value());
}

inline void append_checkpoint_manifest(CanonicalBytes &output, const CheckpointManifest &value) {
  append_map(output, 12);
  append_key(output, "canonical_state_digest");
  append_text(output, value.canonical_state_digest().value());
  append_key(output, "digest_algorithm");
  append_text(output, CheckpointManifest::digest_algorithm);
  append_key(output, "engine_version");
  append_text(output, value.engine_version());
  append_key(output, "evaluation_context");
  append_checkpoint_context(output, value.evaluation_context());
  append_key(output, "event_prefix");
  append_checkpoint_prefix(output, value.event_prefix());
  append_key(output, "lineage");
  append_checkpoint_lineage(output, value.lineage());
  append_key(output, "partition");
  append_checkpoint_partition(output, value.partition());
  append_key(output, "policy");
  append_checkpoint_identity(output, value.policy());
  append_key(output, "projection");
  append_checkpoint_identity(output, value.projection());
  append_key(output, "resolved_event_watermark");
  append_resolved_event_watermark(output, value.resolved_event_watermark());
  append_key(output, "schema_version");
  append_text(output, CheckpointManifest::schema_version);
  append_key(output, "serialization_version");
  append_text(output, CheckpointManifest::serialization_version);
}

} // namespace detail

[[nodiscard]] inline CanonicalBytes canonical_bytes(const CheckpointManifest &value) {
  auto output = detail::top_level_bytes();
  detail::append_checkpoint_manifest(output, value);
  return output;
}

[[nodiscard]] inline std::string canonical_digest(const CheckpointManifest &value) {
  return detail::sha256_hex(canonical_bytes(value));
}

} // namespace luca::serialization
