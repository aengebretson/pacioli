#pragma once

#include "luca/core/error.hpp"

#include <array>
#include <compare>
#include <expected>
#include <string_view>

namespace luca {

class Currency {
 public:
  [[nodiscard]] static constexpr std::expected<Currency, ValueError> from_code(
      std::string_view code) noexcept {
    if (code.size() != 3) return std::unexpected(ValueError::invalid_currency);
    for (char c : code)
      if (c < 'A' || c > 'Z') return std::unexpected(ValueError::invalid_currency);
    return Currency({code[0], code[1], code[2]});
  }
  [[nodiscard]] constexpr std::string_view code() const noexcept {
    return {code_.data(), code_.size()};
  }
  auto operator<=>(const Currency&) const = default;
 private:
  explicit constexpr Currency(std::array<char, 3> code) : code_(code) {}
  std::array<char, 3> code_;
};

}  // namespace luca
