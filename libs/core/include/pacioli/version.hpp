#pragma once

#include <string_view>

namespace pacioli {

[[nodiscard]] constexpr std::string_view version() noexcept {
  return "0.1.0";
}

[[nodiscard]] std::string_view name() noexcept;

}  // namespace pacioli
