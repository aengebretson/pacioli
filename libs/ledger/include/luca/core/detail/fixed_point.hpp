#pragma once

#include "luca/core/error.hpp"

#include <cstdint>
#include <expected>
#include <limits>
#include <string_view>

namespace luca::detail {

using Wide = __int128_t;
constexpr Wide pow10(unsigned scale) {
  Wide result = 1;
  while (scale--) result *= 10;
  return result;
}

inline std::expected<std::int64_t, ValueError> narrow(Wide value) noexcept {
  if (value < std::numeric_limits<std::int64_t>::min() ||
      value > std::numeric_limits<std::int64_t>::max())
    return std::unexpected(ValueError::overflow);
  return static_cast<std::int64_t>(value);
}

inline Wide divide_rounded(Wide numerator, Wide denominator, RoundingMode mode) {
  Wide quotient = numerator / denominator;
  Wide remainder = numerator % denominator;
  if (remainder == 0) return quotient;
  const bool negative = (numerator < 0) != (denominator < 0);
  const Wide direction = negative ? -1 : 1;
  const Wide abs_remainder = remainder < 0 ? -remainder : remainder;
  const Wide abs_denominator = denominator < 0 ? -denominator : denominator;
  bool increment = false;
  switch (mode) {
    case RoundingMode::toward_zero: break;
    case RoundingMode::floor: increment = negative; break;
    case RoundingMode::ceiling: increment = !negative; break;
    case RoundingMode::half_up: increment = abs_remainder * 2 >= abs_denominator; break;
    case RoundingMode::half_even:
      increment = abs_remainder * 2 > abs_denominator ||
                  (abs_remainder * 2 == abs_denominator && quotient % 2 != 0);
      break;
  }
  return increment ? quotient + direction : quotient;
}

template <unsigned Scale> class FixedPoint {
 public:
  static constexpr unsigned scale = Scale;
  constexpr static FixedPoint from_scaled(std::int64_t value) noexcept {
    return FixedPoint(value);
  }
  [[nodiscard]] constexpr std::int64_t scaled_value() const noexcept { return value_; }

  [[nodiscard]] static std::expected<FixedPoint, ValueError> parse(std::string_view text) noexcept {
    if (text.empty()) return std::unexpected(ValueError::invalid_decimal);
    bool negative = false;
    std::size_t position = 0;
    if (text[0] == '-' || text[0] == '+') {
      negative = text[0] == '-';
      if (++position == text.size()) return std::unexpected(ValueError::invalid_decimal);
    }
    Wide whole = 0, fraction = 0;
    unsigned digits = 0;
    bool point = false, any = false;
    for (; position < text.size(); ++position) {
      const char c = text[position];
      if (c == '.' && !point) { point = true; continue; }
      if (c < '0' || c > '9') return std::unexpected(ValueError::invalid_decimal);
      any = true;
      if (!point) whole = whole * 10 + (c - '0');
      else {
        if (digits == Scale) return std::unexpected(ValueError::precision_loss);
        fraction = fraction * 10 + (c - '0');
        ++digits;
      }
      if (whole > pow10(19)) return std::unexpected(ValueError::overflow);
    }
    if (!any) return std::unexpected(ValueError::invalid_decimal);
    while (digits++ < Scale) fraction *= 10;
    Wide result = whole * pow10(Scale) + fraction;
    if (negative) result = -result;
    auto narrowed = narrow(result);
    if (!narrowed) return std::unexpected(narrowed.error());
    return from_scaled(*narrowed);
  }

  [[nodiscard]] std::expected<FixedPoint, ValueError> add(FixedPoint rhs) const noexcept {
    auto value = narrow(Wide(value_) + rhs.value_);
    if (!value) return std::unexpected(value.error());
    return from_scaled(*value);
  }
  [[nodiscard]] std::expected<FixedPoint, ValueError> subtract(FixedPoint rhs) const noexcept {
    auto value = narrow(Wide(value_) - rhs.value_);
    if (!value) return std::unexpected(value.error());
    return from_scaled(*value);
  }
  template <unsigned TargetScale>
  [[nodiscard]] std::expected<FixedPoint<TargetScale>, ValueError> rescale(RoundingMode mode) const noexcept {
    if constexpr (TargetScale >= Scale) {
      auto result = narrow(Wide(value_) * pow10(TargetScale - Scale));
      if (!result) return std::unexpected(result.error());
      return FixedPoint<TargetScale>::from_scaled(*result);
    } else {
      return FixedPoint<TargetScale>::from_scaled(static_cast<std::int64_t>(
          divide_rounded(value_, pow10(Scale - TargetScale), mode)));
    }
  }
  auto operator<=>(const FixedPoint&) const = default;
 private:
  explicit constexpr FixedPoint(std::int64_t value) : value_(value) {}
  std::int64_t value_{};
};

template <unsigned ResultScale, unsigned LeftScale, unsigned RightScale>
std::expected<FixedPoint<ResultScale>, ValueError> multiply(
    FixedPoint<LeftScale> lhs, FixedPoint<RightScale> rhs, RoundingMode mode) noexcept {
  Wide value = Wide(lhs.scaled_value()) * rhs.scaled_value();
  constexpr int reduction = int(LeftScale + RightScale) - int(ResultScale);
  if constexpr (reduction > 0) value = divide_rounded(value, pow10(reduction), mode);
  else if constexpr (reduction < 0) value *= pow10(-reduction);
  auto result = narrow(value);
  if (!result) return std::unexpected(result.error());
  return FixedPoint<ResultScale>::from_scaled(*result);
}

}  // namespace luca::detail
