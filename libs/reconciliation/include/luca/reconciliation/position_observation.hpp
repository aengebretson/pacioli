#pragma once

#include "luca/core.hpp"
#include "luca/portfolio/position.hpp"
#include "luca/time.hpp"

#include <expected>
#include <utility>

namespace luca {

// An external claim about position state. It is deliberately separate from
// EconomicEvent and therefore cannot be appended to a Ledger.
class PositionObservation {
 public:
  [[nodiscard]] static std::expected<PositionObservation, ValueError> create(
      AccountId account, InstrumentId instrument, Quantity quantity,
      Timestamp as_of, Provenance provenance) {
    if (account.value().empty() || instrument.value().empty())
      return std::unexpected(ValueError::empty_identifier);
    return PositionObservation(
        PositionKey{std::move(account), std::move(instrument)}, quantity, as_of,
        std::move(provenance));
  }

  [[nodiscard]] const PositionKey& key() const noexcept { return key_; }
  [[nodiscard]] const AccountId& account() const noexcept { return key_.account(); }
  [[nodiscard]] const InstrumentId& instrument() const noexcept {
    return key_.instrument();
  }
  [[nodiscard]] Quantity quantity() const noexcept { return quantity_; }
  [[nodiscard]] Timestamp as_of() const noexcept { return as_of_; }
  [[nodiscard]] const Provenance& provenance() const noexcept { return provenance_; }
  bool operator==(const PositionObservation&) const = default;

 private:
  PositionObservation(PositionKey key, Quantity quantity, Timestamp as_of,
                      Provenance provenance)
      : key_(std::move(key)), quantity_(quantity), as_of_(as_of),
        provenance_(std::move(provenance)) {}

  PositionKey key_;
  Quantity quantity_;
  Timestamp as_of_;
  Provenance provenance_;
};

}  // namespace luca
