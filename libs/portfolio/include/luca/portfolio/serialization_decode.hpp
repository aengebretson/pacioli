#pragma once

#include "luca/portfolio/serialization.hpp"
#include "luca/serialization/canonical_decode.hpp"

#include <cstddef>
#include <cstdint>
#include <expected>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca::serialization {
namespace portfolio_decode_detail {

[[nodiscard]] inline std::expected<std::string, DecodeError>
read_identifier(decode_detail::Reader &reader, std::string_view field) {
  auto value = decode_detail::read_required_text(reader, field);
  if (!value)
    return std::unexpected(value.error());
  return std::string{*value};
}

[[nodiscard]] inline std::expected<Currency, DecodeError>
read_currency(decode_detail::Reader &reader, std::string_view field) {
  auto text = reader.read_text();
  if (!text)
    return std::unexpected(text.error());
  const auto currency = Currency::from_code(*text);
  if (!currency) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::canonical_encoding,
                     std::string{field} + " must be three upper-case ASCII letters"));
  }
  return *currency;
}

[[nodiscard]] inline std::expected<Money, DecodeError> read_money(decode_detail::Reader &reader) {
  auto shape = reader.read_map(4U, "luca.money.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("currency", previous);
  if (!key)
    return std::unexpected(key.error());
  auto currency = read_currency(reader, "money currency");
  if (!currency)
    return std::unexpected(currency.error());

  key = reader.read_key("scale", previous);
  if (!key)
    return std::unexpected(key.error());
  auto scale = reader.read_text();
  if (!scale)
    return std::unexpected(scale.error());
  if (*scale != "6") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "money scale is not supported"));
  }

  key = reader.read_key("scaled_value", previous);
  if (!key)
    return std::unexpected(key.error());
  auto scaled_text = reader.read_text();
  if (!scaled_text)
    return std::unexpected(scaled_text.error());
  auto scaled = decode_detail::parse_signed_decimal(reader, *scaled_text, "money scaled value");
  if (!scaled)
    return std::unexpected(scaled.error());

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.money.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "money schema version is not supported"));
  }
  return Money::from_scaled(*scaled, *currency);
}

[[nodiscard]] inline std::expected<Quantity, DecodeError>
read_quantity(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "luca.quantity.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("scale", previous);
  if (!key)
    return std::unexpected(key.error());
  auto scale = reader.read_text();
  if (!scale)
    return std::unexpected(scale.error());
  if (*scale != "8") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "quantity scale is not supported"));
  }

  key = reader.read_key("scaled_value", previous);
  if (!key)
    return std::unexpected(key.error());
  auto scaled_text = reader.read_text();
  if (!scaled_text)
    return std::unexpected(scaled_text.error());
  auto scaled = decode_detail::parse_signed_decimal(reader, *scaled_text, "quantity scaled value");
  if (!scaled)
    return std::unexpected(scaled.error());

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.quantity.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "quantity schema version is not supported"));
  }
  return Quantity::from_scaled(*scaled);
}

[[nodiscard]] inline std::expected<Position, DecodeError>
read_position(decode_detail::Reader &reader) {
  auto shape = reader.read_map(4U, "luca.position-balance.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("account", previous);
  if (!key)
    return std::unexpected(key.error());
  auto account = read_identifier(reader, "position account");
  if (!account)
    return std::unexpected(account.error());

  key = reader.read_key("instrument", previous);
  if (!key)
    return std::unexpected(key.error());
  auto instrument = read_identifier(reader, "position instrument");
  if (!instrument)
    return std::unexpected(instrument.error());

  key = reader.read_key("quantity", previous);
  if (!key)
    return std::unexpected(key.error());
  auto quantity = read_quantity(reader);
  if (!quantity)
    return std::unexpected(quantity.error());
  if (quantity->scaled_value() == 0) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::schema_shape, "position quantity must be non-zero"));
  }

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.position-balance.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "position-balance schema version is not supported"));
  }
  return Position{PositionKey{AccountId{std::move(*account)}, InstrumentId{std::move(*instrument)}},
                  *quantity};
}

[[nodiscard]] inline std::expected<CashBalance, DecodeError>
read_cash_balance(decode_detail::Reader &reader) {
  auto shape = reader.read_map(3U, "luca.cash-balance.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("account", previous);
  if (!key)
    return std::unexpected(key.error());
  auto account = read_identifier(reader, "cash-balance account");
  if (!account)
    return std::unexpected(account.error());

  key = reader.read_key("amount", previous);
  if (!key)
    return std::unexpected(key.error());
  auto amount = read_money(reader);
  if (!amount)
    return std::unexpected(amount.error());
  if (amount->scaled_value() == 0) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::schema_shape,
                                        "settled-cash amount must be non-zero"));
  }

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.cash-balance.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "cash-balance schema version is not supported"));
  }
  return CashBalance{AccountId{std::move(*account)}, *amount};
}

[[nodiscard]] inline std::expected<SettlementObligation, DecodeError>
read_obligation(decode_detail::Reader &reader) {
  auto shape = reader.read_map(5U, "luca.settlement-obligation.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("account", previous);
  if (!key)
    return std::unexpected(key.error());
  auto account = read_identifier(reader, "settlement-obligation account");
  if (!account)
    return std::unexpected(account.error());

  key = reader.read_key("amount", previous);
  if (!key)
    return std::unexpected(key.error());
  auto amount = read_money(reader);
  if (!amount)
    return std::unexpected(amount.error());
  if (amount->scaled_value() <= 0) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::schema_shape,
                                        "settlement-obligation amount must be positive"));
  }

  key = reader.read_key("direction", previous);
  if (!key)
    return std::unexpected(key.error());
  auto direction_text = reader.read_text();
  if (!direction_text)
    return std::unexpected(direction_text.error());
  SettlementDirection direction{};
  if (*direction_text == "receivable")
    direction = SettlementDirection::receivable;
  else if (*direction_text == "payable")
    direction = SettlementDirection::payable;
  else
    return std::unexpected(reader.error(DecodeDiagnosticCategory::schema_shape,
                                        "settlement direction is not supported"));

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.settlement-obligation.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "settlement-obligation schema version is not supported"));
  }

  key = reader.read_key("settlement_date", previous);
  if (!key)
    return std::unexpected(key.error());
  auto date_text = reader.read_text();
  if (!date_text)
    return std::unexpected(date_text.error());
  auto date = decode_detail::parse_date(reader, *date_text, "settlement date");
  if (!date)
    return std::unexpected(date.error());

  return SettlementObligation{AccountId{std::move(*account)}, *date, direction, *amount};
}

[[nodiscard]] inline bool position_less(const Position &left, const Position &right) noexcept {
  if (left.key().account() != right.key().account()) {
    return decode_detail::raw_bytes_less(left.key().account().value(),
                                         right.key().account().value());
  }
  return decode_detail::raw_bytes_less(left.key().instrument().value(),
                                       right.key().instrument().value());
}

[[nodiscard]] inline bool cash_less(const CashBalance &left, const CashBalance &right) noexcept {
  if (left.key().account() != right.key().account()) {
    return decode_detail::raw_bytes_less(left.key().account().value(),
                                         right.key().account().value());
  }
  return left.key().currency().code() < right.key().currency().code();
}

[[nodiscard]] inline bool obligation_less(const SettlementObligation &left,
                                          const SettlementObligation &right) noexcept {
  if (left.key().account() != right.key().account()) {
    return decode_detail::raw_bytes_less(left.key().account().value(),
                                         right.key().account().value());
  }
  if (left.key().settlement_date() != right.key().settlement_date())
    return left.key().settlement_date() < right.key().settlement_date();
  if (left.key().currency() != right.key().currency())
    return left.key().currency().code() < right.key().currency().code();
  return detail::settlement_direction_rank(left.key().direction()) <
         detail::settlement_direction_rank(right.key().direction());
}

template <class Value, class Less>
[[nodiscard]] inline std::expected<void, DecodeError>
validate_next(decode_detail::Reader &reader, const std::vector<Value> &values, Less less,
              std::string_view collection) {
  if (values.size() < 2U)
    return {};
  const auto &previous = values[values.size() - 2U];
  const auto &current = values.back();
  if (previous.key() == current.key()) {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::duplicate_identity,
                                        std::string{collection} + " contains a duplicate key"));
  }
  if (!less(previous, current)) {
    return std::unexpected(
        reader.error(DecodeDiagnosticCategory::deterministic_ordering,
                     std::string{collection} + " is not in canonical financial order"));
  }
  return {};
}

[[nodiscard]] inline std::expected<PortfolioState, DecodeError>
read_portfolio_state(decode_detail::Reader &reader) {
  auto shape = reader.read_map(4U, "luca.portfolio-state.v1");
  if (!shape)
    return std::unexpected(shape.error());
  std::string_view previous;

  auto key = reader.read_key("open_settlement_obligations", previous);
  if (!key)
    return std::unexpected(key.error());
  auto obligation_count = reader.read_array_count("open-settlement-obligation array");
  if (!obligation_count)
    return std::unexpected(obligation_count.error());
  std::vector<SettlementObligation> obligations;
  obligations.reserve(*obligation_count);
  for (std::size_t index = 0; index < *obligation_count; ++index) {
    auto value = read_obligation(reader);
    if (!value)
      return std::unexpected(value.error());
    obligations.push_back(std::move(*value));
    if (auto ordered =
            validate_next(reader, obligations, obligation_less, "open-settlement-obligation array");
        !ordered)
      return std::unexpected(ordered.error());
  }

  key = reader.read_key("positions", previous);
  if (!key)
    return std::unexpected(key.error());
  auto position_count = reader.read_array_count("position array");
  if (!position_count)
    return std::unexpected(position_count.error());
  std::vector<Position> positions;
  positions.reserve(*position_count);
  for (std::size_t index = 0; index < *position_count; ++index) {
    auto value = read_position(reader);
    if (!value)
      return std::unexpected(value.error());
    positions.push_back(std::move(*value));
    if (auto ordered = validate_next(reader, positions, position_less, "position array"); !ordered)
      return std::unexpected(ordered.error());
  }

  key = reader.read_key("schema_version", previous);
  if (!key)
    return std::unexpected(key.error());
  auto schema = reader.read_text();
  if (!schema)
    return std::unexpected(schema.error());
  if (*schema != "luca.portfolio-state.v1") {
    return std::unexpected(reader.error(DecodeDiagnosticCategory::unsupported_version,
                                        "portfolio-state schema version is not supported"));
  }

  key = reader.read_key("settled_cash", previous);
  if (!key)
    return std::unexpected(key.error());
  auto cash_count = reader.read_array_count("settled-cash array");
  if (!cash_count)
    return std::unexpected(cash_count.error());
  std::vector<CashBalance> cash;
  cash.reserve(*cash_count);
  for (std::size_t index = 0; index < *cash_count; ++index) {
    auto value = read_cash_balance(reader);
    if (!value)
      return std::unexpected(value.error());
    cash.push_back(std::move(*value));
    if (auto ordered = validate_next(reader, cash, cash_less, "settled-cash array"); !ordered)
      return std::unexpected(ordered.error());
  }

  return PortfolioState{std::move(positions), std::move(cash), std::move(obligations)};
}

} // namespace portfolio_decode_detail

[[nodiscard]] inline std::expected<PortfolioState, DecodeError>
decode_portfolio_state(std::span<const std::byte> input) {
  decode_detail::Reader reader{input};
  if (auto header = reader.read_header(); !header)
    return std::unexpected(header.error());
  auto state = portfolio_decode_detail::read_portfolio_state(reader);
  if (!state)
    return std::unexpected(state.error());
  if (auto complete = reader.finish(); !complete)
    return std::unexpected(complete.error());
  return state;
}

} // namespace luca::serialization
