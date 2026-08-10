#pragma once

#include "luca/core.hpp"

#include <utility>

namespace luca {

class PositionKey {
 public:
  PositionKey(AccountId account, InstrumentId instrument)
      : account_(std::move(account)), instrument_(std::move(instrument)) {}

  [[nodiscard]] const AccountId& account() const noexcept { return account_; }
  [[nodiscard]] const InstrumentId& instrument() const noexcept { return instrument_; }
  auto operator<=>(const PositionKey&) const = default;

 private:
  AccountId account_;
  InstrumentId instrument_;
};

class Position {
 public:
  Position(PositionKey key, Quantity quantity)
      : key_(std::move(key)), quantity_(quantity) {}

  [[nodiscard]] const PositionKey& key() const noexcept { return key_; }
  [[nodiscard]] Quantity quantity() const noexcept { return quantity_; }
  bool operator==(const Position&) const = default;

 private:
  PositionKey key_;
  Quantity quantity_;
};

}  // namespace luca
