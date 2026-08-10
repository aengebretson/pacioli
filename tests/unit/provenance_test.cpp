#include "luca/core.hpp"

#include <cassert>
#include <chrono>
#include <string>
#include <type_traits>
#include <vector>

using namespace luca;
using namespace std::chrono_literals;

int main() {
  static_assert(!std::is_convertible_v<SourceRecordId, EventId>);
  static_assert(!std::is_convertible_v<EventId, SourceRecordId>);
  static_assert(std::is_same_v<decltype(Provenance::create(
      std::vector<SourceRecordId>{}, "x", "1")->source_records()[0]),
      const SourceRecordId&>);

  const auto hash = PayloadHash::create("sha256", "0123456789abcdef");
  assert(hash);
  assert(!PayloadHash::create("", "digest"));
  assert(!PayloadHash::create("sha256", ""));

  const SourceRecord::Timestamp observed{1'786'355'400s};
  const SourceRecord::Timestamp emitted{1'786'355'399s};
  const auto record = SourceRecord::create(
      SourceId{"broker-a"}, SourceRecordId{"record-12882"}, "12882", observed,
      emitted, *hash, "execution-report", "fix-session:ABC:seq=12882");
  assert(record);
  assert(record->source() == SourceId{"broker-a"});
  assert(record->id() == SourceRecordId{"record-12882"});
  assert(record->source_local_id() == "12882");
  assert(record->observed_at() == observed);
  assert(record->source_event_at() == emitted);
  assert(record->payload_hash() == *hash);
  assert(record->source_reference() == "fix-session:ABC:seq=12882");
  assert(record->kind() == "execution-report");
  assert(*record == *record);

  const auto without_source_time = SourceRecord::create(
      SourceId{"file-drop"}, SourceRecordId{"row-182"}, "trades.csv:182", observed,
      std::nullopt, *hash, "trade", std::nullopt);
  assert(without_source_time && !without_source_time->source_event_at());
  assert(!without_source_time->source_reference());
  assert(!SourceRecord::create(SourceId{""}, SourceRecordId{"id"}, "key", observed,
                               std::nullopt, *hash, "trade"));
  assert(!SourceRecord::create(SourceId{"feed"}, SourceRecordId{""}, "key", observed,
                               std::nullopt, *hash, "trade"));
  assert(!SourceRecord::create(SourceId{"feed"}, SourceRecordId{"id"}, "", observed,
                               std::nullopt, *hash, "trade"));

  const auto one = Provenance::create({SourceRecordId{"record-12882"}},
                                      "fix.execution_report", "1", "normalized tags");
  assert(one && one->source_records().size() == 1);
  assert(one->transformation_name() == "fix.execution_report");
  assert(one->transformation_version() == "1");
  assert(one->transformation_metadata() == "normalized tags");
  assert(*one == *one);

  const auto correction = Provenance::create(
      {SourceRecordId{"original"}, SourceRecordId{"correction"},
       SourceRecordId{"custodian-corroboration"}},
      "trade.normalization", "2");
  assert(correction && correction->source_records().size() == 3);
  assert(correction->source_records()[1] == SourceRecordId{"correction"});
  assert(!correction->transformation_metadata());

  assert(!Provenance::create({}, "trade.normalization", "1"));
  assert(!Provenance::create({SourceRecordId{""}}, "trade.normalization", "1"));
  assert(!Provenance::create({SourceRecordId{"record"}}, "", "1"));
  assert(!Provenance::create({SourceRecordId{"record"}}, "name", ""));
  assert(!Provenance::create({SourceRecordId{"record"}}, "name", "1",
                             std::string(Provenance::max_metadata_size + 1, 'x')));
}
