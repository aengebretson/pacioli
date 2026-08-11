#pragma once

#include "luca/core.hpp"
#include "luca/time.hpp"

#include <utility>

namespace luca {

enum class SettlementDirection { receivable, payable };

class SettlementObligationKey {
 public:
  SettlementObligationKey(AccountId account, SettlementDate settlement_date,
                          Currency currency, SettlementDirection direction)
      : account_(std::move(account)), settlement_date_(settlement_date),
        currency_(currency), direction_(direction) {}

  [[nodiscard]] const AccountId& account() const noexcept { return account_; }
  [[nodiscard]] SettlementDate settlement_date() const noexcept { return settlement_date_; }
  [[nodiscard]] Currency currency() const noexcept { return currency_; }
  [[nodiscard]] SettlementDirection direction() const noexcept { return direction_; }
  auto operator<=>(const SettlementObligationKey&) const = default;

 private:
  AccountId account_;
  SettlementDate settlement_date_;
  Currency currency_;
  SettlementDirection direction_;
};

// The key carries the currency, so an obligation cannot contain a mismatched amount.
class SettlementObligation {
 public:
  SettlementObligation(AccountId account, SettlementDate settlement_date,
                       SettlementDirection direction, Money amount)
      : key_(std::move(account), settlement_date, amount.currency(), direction),
        amount_(amount) {}

  [[nodiscard]] const SettlementObligationKey& key() const noexcept { return key_; }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  bool operator==(const SettlementObligation&) const = default;

 private:
  SettlementObligationKey key_;
  Money amount_;
};

}  // namespace luca
