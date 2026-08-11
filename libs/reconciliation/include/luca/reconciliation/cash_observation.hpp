#pragma once

#include <chrono>
#include <expected>
#include <utility>

#include "luca/portfolio/cash.hpp"
#include "luca/time.hpp"

namespace luca {

// An external claim about settled cash. It is deliberately separate from
// EconomicEvent and therefore cannot be appended to a Ledger.
class CashObservation {
 public:
  [[nodiscard]] static std::expected<CashObservation, ValueError> create(
      AccountId account, Money amount, Timestamp as_of,
      std::chrono::year_month_day settlement_as_of_date,
      Provenance provenance) {
    if (account.value().empty())
      return std::unexpected(ValueError::empty_identifier);
    if (!settlement_as_of_date.ok())
      return std::unexpected(ValueError::invalid_date);
    return CashObservation(CashKey{std::move(account), amount.currency()},
                           amount, as_of, settlement_as_of_date,
                           std::move(provenance));
  }

  [[nodiscard]] const CashKey &key() const noexcept { return key_; }
  [[nodiscard]] const AccountId &account() const noexcept {
    return key_.account();
  }
  [[nodiscard]] Currency currency() const noexcept { return key_.currency(); }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  [[nodiscard]] Timestamp as_of() const noexcept { return as_of_; }
  [[nodiscard]] std::chrono::year_month_day settlement_as_of_date()
      const noexcept {
    return settlement_as_of_date_;
  }
  [[nodiscard]] const Provenance &provenance() const noexcept {
    return provenance_;
  }
  bool operator==(const CashObservation &) const = default;

 private:
  CashObservation(CashKey key, Money amount, Timestamp as_of,
                  std::chrono::year_month_day settlement_as_of_date,
                  Provenance provenance)
      : key_(std::move(key)),
        amount_(amount),
        as_of_(as_of),
        settlement_as_of_date_(settlement_as_of_date),
        provenance_(std::move(provenance)) {}

  CashKey key_;
  Money amount_;
  Timestamp as_of_;
  std::chrono::year_month_day settlement_as_of_date_;
  Provenance provenance_;
};

}  // namespace luca
