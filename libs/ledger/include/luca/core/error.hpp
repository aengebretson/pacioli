#pragma once

namespace luca {

enum class ValueError {
  invalid_currency,
  invalid_decimal,
  precision_loss,
  overflow,
  currency_mismatch,
  empty_identifier,
  empty_required_field,
  empty_source_records,
  metadata_too_large,
  zero_quantity,
  invalid_date,
};

enum class RoundingMode { toward_zero, floor, ceiling, half_up, half_even };

}  // namespace luca
