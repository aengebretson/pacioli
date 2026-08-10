#pragma once

#include "luca/core.hpp"

#include <utility>

namespace luca {

class CashKey {
 public:
  CashKey(AccountId account, Currency currency)
      : account_(std::move(account)), currency_(currency) {}
  [[nodiscard]] const AccountId& account() const noexcept { return account_; }
  [[nodiscard]] Currency currency() const noexcept { return currency_; }
  auto operator<=>(const CashKey&) const = default;
 private:
  AccountId account_;
  Currency currency_;
};

// Deriving the key currency from amount makes a mismatched balance impossible.
class CashBalance {
 public:
  CashBalance(AccountId account, Money amount)
      : key_(std::move(account), amount.currency()), amount_(amount) {}
  [[nodiscard]] const CashKey& key() const noexcept { return key_; }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  bool operator==(const CashBalance&) const = default;
 private:
  CashKey key_;
  Money amount_;
};

}  // namespace luca
