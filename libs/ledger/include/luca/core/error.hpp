#pragma once

namespace luca {

enum class ValueError {
  invalid_currency,
  invalid_decimal,
  precision_loss,
  overflow,
  currency_mismatch,
};

enum class RoundingMode { toward_zero, floor, ceiling, half_up, half_even };

}  // namespace luca
