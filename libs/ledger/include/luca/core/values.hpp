#pragma once

#include "luca/core/currency.hpp"
#include "luca/core/detail/fixed_point.hpp"

#include <compare>
#include <cstdint>
#include <expected>
#include <string_view>

namespace luca {

template <class Derived, unsigned Scale> class Scalar {
 public:
  static constexpr unsigned scale = Scale;
  [[nodiscard]] static constexpr Derived from_scaled(std::int64_t value) noexcept {
    return Derived(detail::FixedPoint<Scale>::from_scaled(value));
  }
  [[nodiscard]] static std::expected<Derived, ValueError> parse(std::string_view value) noexcept {
    auto parsed = detail::FixedPoint<Scale>::parse(value);
    if (!parsed) return std::unexpected(parsed.error());
    return Derived(*parsed);
  }
  [[nodiscard]] constexpr std::int64_t scaled_value() const noexcept { return value_.scaled_value(); }
  // Internal fixed-point access used by dimensionally checked free functions.
  [[nodiscard]] constexpr detail::FixedPoint<Scale> fixed() const noexcept { return value_; }
  [[nodiscard]] std::expected<Derived, ValueError> add(Derived rhs) const noexcept {
    auto result = value_.add(rhs.fixed());
    if (!result) return std::unexpected(result.error());
    return Derived(*result);
  }
  [[nodiscard]] std::expected<Derived, ValueError> subtract(Derived rhs) const noexcept {
    auto result = value_.subtract(rhs.fixed());
    if (!result) return std::unexpected(result.error());
    return Derived(*result);
  }
  auto operator<=>(const Scalar&) const = default;
 protected:
  explicit constexpr Scalar(detail::FixedPoint<Scale> value) : value_(value) {}
 private:
  detail::FixedPoint<Scale> value_;
};

class Quantity final : public Scalar<Quantity, 8> { public: using Scalar::Scalar; };
class Rate final : public Scalar<Rate, 12> { public: using Scalar::Scalar; };

class Price final : public Scalar<Price, 8> {
 public:
  using Scalar::Scalar;
  [[nodiscard]] static std::expected<Price, ValueError> parse(std::string_view value) noexcept {
    return Scalar::parse(value);
  }
};

class Money {
 public:
  static constexpr unsigned scale = 6;
  [[nodiscard]] static constexpr Money from_scaled(std::int64_t amount, Currency currency) noexcept {
    return Money(detail::FixedPoint<scale>::from_scaled(amount), currency);
  }
  [[nodiscard]] static std::expected<Money, ValueError> parse(
      std::string_view amount, Currency currency) noexcept {
    auto parsed = detail::FixedPoint<scale>::parse(amount);
    if (!parsed) return std::unexpected(parsed.error());
    return Money(*parsed, currency);
  }
  [[nodiscard]] constexpr std::int64_t scaled_value() const noexcept { return amount_.scaled_value(); }
  [[nodiscard]] constexpr Currency currency() const noexcept { return currency_; }
  [[nodiscard]] std::expected<Money, ValueError> add(const Money& rhs) const noexcept {
    if (currency_ != rhs.currency_) return std::unexpected(ValueError::currency_mismatch);
    auto result = amount_.add(rhs.amount_);
    if (!result) return std::unexpected(result.error());
    return Money(*result, currency_);
  }
  [[nodiscard]] std::expected<Money, ValueError> subtract(const Money& rhs) const noexcept {
    if (currency_ != rhs.currency_) return std::unexpected(ValueError::currency_mismatch);
    auto result = amount_.subtract(rhs.amount_);
    if (!result) return std::unexpected(result.error());
    return Money(*result, currency_);
  }
  [[nodiscard]] std::partial_ordering operator<=>(const Money& rhs) const noexcept {
    if (currency_ != rhs.currency_) return std::partial_ordering::unordered;
    return amount_ <=> rhs.amount_;
  }
  [[nodiscard]] bool operator==(const Money& rhs) const noexcept = default;
 private:
  constexpr Money(detail::FixedPoint<scale> amount, Currency currency) : amount_(amount), currency_(currency) {}
  detail::FixedPoint<scale> amount_;
  Currency currency_;
};

// Quote currency is explicit at valuation time: a Price is a reusable scalar,
// while the resulting Money always carries its currency.
[[nodiscard]] inline std::expected<Money, ValueError> value(
    Quantity quantity, Price price, Currency quote_currency,
    RoundingMode rounding = RoundingMode::half_even) noexcept {
  auto result = detail::multiply<Money::scale>(quantity.fixed(), price.fixed(), rounding);
  if (!result) return std::unexpected(result.error());
  return Money::from_scaled(result->scaled_value(), quote_currency);
}

[[nodiscard]] inline std::expected<Money, ValueError> scale(
    Money amount, Rate rate, RoundingMode rounding = RoundingMode::half_even) noexcept {
  auto result = detail::multiply<Money::scale>(
      detail::FixedPoint<Money::scale>::from_scaled(amount.scaled_value()), rate.fixed(), rounding);
  if (!result) return std::unexpected(result.error());
  return Money::from_scaled(result->scaled_value(), amount.currency());
}

}  // namespace luca
