#pragma once

#include "luca/core/error.hpp"

#include <chrono>
#include <expected>

namespace luca {

// Nanoseconds preserve fine-grained source values; the type does not imply that
// every source measured its event with nanosecond accuracy.
using Timestamp = std::chrono::sys_time<std::chrono::nanoseconds>;

class SettlementDate {
 public:
  [[nodiscard]] static constexpr std::expected<SettlementDate, ValueError> create(
      std::chrono::year_month_day value) noexcept {
    if (!value.ok()) return std::unexpected(ValueError::invalid_date);
    return SettlementDate(value);
  }

  [[nodiscard]] constexpr std::chrono::year_month_day value() const noexcept {
    return value_;
  }
  auto operator<=>(const SettlementDate&) const = default;

 private:
  explicit constexpr SettlementDate(std::chrono::year_month_day value) : value_(value) {}
  std::chrono::year_month_day value_;
};

}  // namespace luca
