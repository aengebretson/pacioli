#pragma once

#include "luca/ledger.hpp"
#include "luca/portfolio/position.hpp"

#include <algorithm>
#include <concepts>
#include <expected>
#include <functional>
#include <span>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

namespace luca {

enum class PositionProjectionError { quantity_overflow };

// The input may be in any order. Entries at or before as_of are replayed in
// economic order (effective_at, then ledger sequence). Results omit zero
// quantities and are ordered by account, then instrument.
[[nodiscard]] inline std::expected<std::vector<Position>, PositionProjectionError>
project_positions(std::span<const LedgerEntry> entries, Timestamp as_of) {
  using EntryReference = std::reference_wrapper<const LedgerEntry>;
  std::vector<EntryReference> ordered;
  ordered.reserve(entries.size());
  for (const auto& entry : entries) {
    if (header(entry.event()).effective_at() <= as_of)
      ordered.emplace_back(std::cref(entry));
  }
  std::sort(ordered.begin(), ordered.end(), [](EntryReference lhs, EntryReference rhs) {
    const auto left_time = header(lhs.get().event()).effective_at();
    const auto right_time = header(rhs.get().event()).effective_at();
    if (left_time != right_time) return left_time < right_time;
    return lhs.get().sequence() < rhs.get().sequence();
  });

  struct KeyHash {
    std::size_t operator()(const PositionKey& key) const noexcept {
      const auto first = std::hash<std::string>{}(key.account().value());
      const auto second = std::hash<std::string>{}(key.instrument().value());
      return first ^ (second + 0x9e3779b9U + (first << 6U) + (first >> 2U));
    }
  };
  std::unordered_map<PositionKey, Quantity, KeyHash> quantities;
  for (const auto entry : ordered) {
    const auto result = std::visit(
        [&quantities](const auto& event) -> std::expected<void, PositionProjectionError> {
          using Event = std::remove_cvref_t<decltype(event)>;
          if constexpr (std::same_as<Event, EquityTrade>) {
            PositionKey key{event.header().account(), event.instrument()};
            const auto existing = quantities.find(key);
            if (existing == quantities.end()) {
              quantities.emplace(std::move(key), event.quantity());
            } else {
              const auto sum = existing->second.add(event.quantity());
              if (!sum)
                return std::unexpected(PositionProjectionError::quantity_overflow);
              existing->second = *sum;
            }
          }
          return {};
        },
        entry.get().event());
    if (!result) return std::unexpected(result.error());
  }

  std::vector<Position> positions;
  positions.reserve(quantities.size());
  for (const auto& [key, quantity] : quantities)
    if (quantity.scaled_value() != 0) positions.emplace_back(key, quantity);
  std::sort(positions.begin(), positions.end(), [](const Position& lhs, const Position& rhs) {
    return lhs.key() < rhs.key();
  });
  return positions;
}

}  // namespace luca
