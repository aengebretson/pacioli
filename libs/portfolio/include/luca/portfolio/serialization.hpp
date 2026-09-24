#pragma once

#include "luca/portfolio/cash.hpp"
#include "luca/portfolio/position.hpp"
#include "luca/portfolio/settlement.hpp"
#include "luca/serialization/canonical.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca {

// An exchange value for the complete existing portfolio projection surface.
// Canonical serialization validates and orders each owned sparse collection.
class PortfolioState {
public:
  PortfolioState(std::vector<Position> positions = {}, std::vector<CashBalance> settled_cash = {},
                 std::vector<SettlementObligation> open_settlement_obligations = {})
      : positions_(std::move(positions)), settled_cash_(std::move(settled_cash)),
        open_settlement_obligations_(std::move(open_settlement_obligations)) {}

  [[nodiscard]] std::span<const Position> positions() const noexcept { return positions_; }
  [[nodiscard]] std::span<const CashBalance> settled_cash() const noexcept { return settled_cash_; }
  [[nodiscard]] std::span<const SettlementObligation> open_settlement_obligations() const noexcept {
    return open_settlement_obligations_;
  }

  bool operator==(const PortfolioState &) const = default;

private:
  std::vector<Position> positions_;
  std::vector<CashBalance> settled_cash_;
  std::vector<SettlementObligation> open_settlement_obligations_;
};

} // namespace luca

namespace luca::serialization {
namespace detail {

inline void validate_portfolio_identifier(std::string_view value) {
  if (value.empty())
    throw std::invalid_argument("LCB1 identifier must not be empty");
  if (value.find('\0') != std::string_view::npos)
    throw std::invalid_argument("LCB1 identifier must not contain NUL");
  if (value.size() > std::numeric_limits<std::uint32_t>::max())
    throw std::length_error("LCB1 text exceeds the unsigned 32-bit length limit");
  validate_text(value);
}

inline bool utf8_bytes_less(std::string_view left, std::string_view right) noexcept {
  return std::lexicographical_compare(
      left.begin(), left.end(), right.begin(), right.end(), [](char left_byte, char right_byte) {
        return static_cast<unsigned char>(left_byte) < static_cast<unsigned char>(right_byte);
      });
}

inline std::string_view settlement_direction_name(SettlementDirection direction) {
  switch (direction) {
  case SettlementDirection::receivable:
    return "receivable";
  case SettlementDirection::payable:
    return "payable";
  }
  throw std::invalid_argument("LCB1 settlement direction is invalid");
}

inline unsigned settlement_direction_rank(SettlementDirection direction) {
  switch (direction) {
  case SettlementDirection::receivable:
    return 0;
  case SettlementDirection::payable:
    return 1;
  }
  throw std::invalid_argument("LCB1 settlement direction is invalid");
}

inline void validate_settlement_date(SettlementDate value) {
  if (!value.value().ok())
    throw std::invalid_argument("LCB1 settlement date must be a valid date");
  (void)canonical_date(value);
}

inline std::vector<Position> canonical_positions(const PortfolioState &value) {
  std::vector<Position> positions{value.positions().begin(), value.positions().end()};
  for (const auto &position : positions) {
    validate_portfolio_identifier(position.key().account().value());
    validate_portfolio_identifier(position.key().instrument().value());
    if (position.quantity().scaled_value() == 0)
      throw std::invalid_argument("LCB1 position quantity must be non-zero");
  }

  std::sort(positions.begin(), positions.end(), [](const Position &left, const Position &right) {
    const auto &left_account = left.key().account().value();
    const auto &right_account = right.key().account().value();
    if (left_account != right_account)
      return utf8_bytes_less(left_account, right_account);
    return utf8_bytes_less(left.key().instrument().value(), right.key().instrument().value());
  });
  for (std::size_t index = 1; index < positions.size(); ++index) {
    if (positions[index - 1].key() == positions[index].key())
      throw std::invalid_argument("LCB1 position keys must be unique");
  }
  return positions;
}

inline std::vector<CashBalance> canonical_cash(const PortfolioState &value) {
  std::vector<CashBalance> cash{value.settled_cash().begin(), value.settled_cash().end()};
  for (const auto &balance : cash) {
    validate_portfolio_identifier(balance.key().account().value());
    if (balance.amount().scaled_value() == 0)
      throw std::invalid_argument("LCB1 settled cash amount must be non-zero");
  }

  std::sort(cash.begin(), cash.end(), [](const CashBalance &left, const CashBalance &right) {
    const auto &left_account = left.key().account().value();
    const auto &right_account = right.key().account().value();
    if (left_account != right_account)
      return utf8_bytes_less(left_account, right_account);
    return left.key().currency().code() < right.key().currency().code();
  });
  for (std::size_t index = 1; index < cash.size(); ++index) {
    if (cash[index - 1].key() == cash[index].key())
      throw std::invalid_argument("LCB1 settled cash keys must be unique");
  }
  return cash;
}

inline std::vector<SettlementObligation> canonical_obligations(const PortfolioState &value) {
  std::vector<SettlementObligation> obligations{value.open_settlement_obligations().begin(),
                                                value.open_settlement_obligations().end()};
  for (const auto &obligation : obligations) {
    validate_portfolio_identifier(obligation.key().account().value());
    validate_settlement_date(obligation.key().settlement_date());
    (void)settlement_direction_rank(obligation.key().direction());
    if (obligation.amount().scaled_value() <= 0)
      throw std::invalid_argument("LCB1 settlement obligation amount must be positive");
  }

  std::sort(obligations.begin(), obligations.end(),
            [](const SettlementObligation &left, const SettlementObligation &right) {
              const auto &left_key = left.key();
              const auto &right_key = right.key();
              if (left_key.account() != right_key.account())
                return utf8_bytes_less(left_key.account().value(), right_key.account().value());
              if (left_key.settlement_date() != right_key.settlement_date())
                return left_key.settlement_date() < right_key.settlement_date();
              if (left_key.currency() != right_key.currency())
                return left_key.currency().code() < right_key.currency().code();
              return settlement_direction_rank(left_key.direction()) <
                     settlement_direction_rank(right_key.direction());
            });
  for (std::size_t index = 1; index < obligations.size(); ++index) {
    if (obligations[index - 1].key() == obligations[index].key())
      throw std::invalid_argument("LCB1 settlement obligation keys must be unique");
  }
  return obligations;
}

inline void append_position_balance(CanonicalBytes &output, const Position &value) {
  append_map(output, 4);
  append_key(output, "account");
  append_identifier(output, value.key().account().value());
  append_key(output, "instrument");
  append_identifier(output, value.key().instrument().value());
  append_key(output, "quantity");
  append_quantity(output, value.quantity());
  append_key(output, "schema_version");
  append_text(output, "luca.position-balance.v1");
}

inline void append_cash_balance(CanonicalBytes &output, const CashBalance &value) {
  append_map(output, 3);
  append_key(output, "account");
  append_identifier(output, value.key().account().value());
  append_key(output, "amount");
  append_money(output, value.amount());
  append_key(output, "schema_version");
  append_text(output, "luca.cash-balance.v1");
}

inline void append_settlement_obligation(CanonicalBytes &output,
                                         const SettlementObligation &value) {
  append_map(output, 5);
  append_key(output, "account");
  append_identifier(output, value.key().account().value());
  append_key(output, "amount");
  append_money(output, value.amount());
  append_key(output, "direction");
  append_text(output, settlement_direction_name(value.key().direction()));
  append_key(output, "schema_version");
  append_text(output, "luca.settlement-obligation.v1");
  append_key(output, "settlement_date");
  append_text(output, canonical_date(value.key().settlement_date()));
}

} // namespace detail

[[nodiscard]] inline CanonicalBytes canonical_bytes(const PortfolioState &value) {
  const auto positions = detail::canonical_positions(value);
  const auto cash = detail::canonical_cash(value);
  const auto obligations = detail::canonical_obligations(value);

  auto output = detail::top_level_bytes();
  detail::append_map(output, 4);
  detail::append_key(output, "open_settlement_obligations");
  detail::append_array(output, static_cast<std::uint64_t>(obligations.size()));
  for (const auto &obligation : obligations)
    detail::append_settlement_obligation(output, obligation);
  detail::append_key(output, "positions");
  detail::append_array(output, static_cast<std::uint64_t>(positions.size()));
  for (const auto &position : positions)
    detail::append_position_balance(output, position);
  detail::append_key(output, "schema_version");
  detail::append_text(output, "luca.portfolio-state.v1");
  detail::append_key(output, "settled_cash");
  detail::append_array(output, static_cast<std::uint64_t>(cash.size()));
  for (const auto &balance : cash)
    detail::append_cash_balance(output, balance);
  return output;
}

[[nodiscard]] inline std::string canonical_digest(const PortfolioState &value) {
  return detail::sha256_hex(canonical_bytes(value));
}

} // namespace luca::serialization
