#pragma once

#include "luca/event.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <functional>
#include <limits>
#include <span>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace luca {

class LedgerSequence {
 public:
  // The first event accepted by a Ledger has sequence 1.
  static constexpr std::uint64_t first_value = 1;
  [[nodiscard]] constexpr std::uint64_t value() const noexcept { return value_; }
  auto operator<=>(const LedgerSequence&) const = default;

 private:
  friend class Ledger;
  explicit constexpr LedgerSequence(std::uint64_t value) noexcept : value_(value) {}
  std::uint64_t value_;
};

class LedgerEntry {
 public:
  [[nodiscard]] LedgerSequence sequence() const noexcept { return sequence_; }
  [[nodiscard]] const EconomicEvent& event() const noexcept { return event_; }
  bool operator==(const LedgerEntry&) const = default;

 private:
  friend class Ledger;
  LedgerEntry(LedgerSequence sequence, EconomicEvent event)
      : sequence_(sequence), event_(std::move(event)) {}
  LedgerSequence sequence_;
  EconomicEvent event_;
};

enum class LedgerError { duplicate_event, sequence_overflow };

// An append-only, in-memory ledger. A Ledger is not safe for concurrent mutation.
// Spans and reference views may be invalidated when a later append reallocates
// storage; callers should request a fresh view after mutation.
class Ledger {
 public:
  using EntryReference = std::reference_wrapper<const LedgerEntry>;
  using EntryView = std::vector<EntryReference>;

  [[nodiscard]] bool empty() const noexcept { return entries_.empty(); }
  [[nodiscard]] std::size_t size() const noexcept { return entries_.size(); }
  [[nodiscard]] std::span<const LedgerEntry> entries() const noexcept { return entries_; }

  [[nodiscard]] std::expected<EntryReference, LedgerError> append(
      const EconomicEvent& event) {
    const auto& id = header(event).id().value();
    if (event_index_.contains(id)) return std::unexpected(LedgerError::duplicate_event);
    if (sequence_exhausted_) return std::unexpected(LedgerError::sequence_overflow);

    const auto sequence = LedgerSequence{next_sequence_};
    entries_.push_back(LedgerEntry(sequence, event));
    event_index_.emplace(id, entries_.size() - 1);
    if (next_sequence_ == std::numeric_limits<std::uint64_t>::max())
      sequence_exhausted_ = true;
    else
      ++next_sequence_;
    return std::cref(entries_.back());
  }

  [[nodiscard]] const LedgerEntry* find(const EventId& id) const noexcept {
    const auto position = event_index_.find(id.value());
    return position == event_index_.end() ? nullptr : &entries_[position->second];
  }

  // Sequence is only a deterministic tie-breaker, not an assertion that
  // acceptance order is economically authoritative.
  [[nodiscard]] EntryView economic_order() const {
    EntryView result;
    result.reserve(entries_.size());
    for (const auto& entry : entries_) result.emplace_back(std::cref(entry));
    std::sort(result.begin(), result.end(), economic_less);
    return result;
  }

  // Returns [from, to) in economic replay order. Empty and reversed intervals
  // produce an empty view.
  [[nodiscard]] EntryView entries_between(Timestamp from, Timestamp to) const {
    if (from >= to) return {};
    EntryView result;
    for (const auto& entry : entries_) {
      const auto time = header(entry.event()).effective_at();
      if (time >= from && time < to) result.emplace_back(std::cref(entry));
    }
    std::sort(result.begin(), result.end(), economic_less);
    return result;
  }

 private:
  [[nodiscard]] static bool economic_less(EntryReference lhs,
                                          EntryReference rhs) noexcept {
    const auto left_time = header(lhs.get().event()).effective_at();
    const auto right_time = header(rhs.get().event()).effective_at();
    if (left_time != right_time) return left_time < right_time;
    return lhs.get().sequence() < rhs.get().sequence();
  }

  std::vector<LedgerEntry> entries_;
  std::unordered_map<std::string, std::size_t> event_index_;
  std::uint64_t next_sequence_ = LedgerSequence::first_value;
  bool sequence_exhausted_ = false;
};

}  // namespace luca
