#pragma once

#include "luca/core.hpp"
#include "luca/time.hpp"

#include <expected>
#include <utility>
#include <variant>

namespace luca {

class EventHeader {
 public:
  [[nodiscard]] static std::expected<EventHeader, ValueError> create(
      EventId id, AccountId account, Timestamp effective_at, Provenance provenance) {
    if (id.value().empty() || account.value().empty())
      return std::unexpected(ValueError::empty_identifier);
    // Provenance has no public invalid constructor, but recheck so a moved-from
    // value cannot be used to create a production event.
    if (provenance.source_records().empty())
      return std::unexpected(ValueError::empty_source_records);
    for (const auto& source_record : provenance.source_records())
      if (source_record.value().empty())
        return std::unexpected(ValueError::empty_identifier);
    if (provenance.transformation_name().empty() ||
        provenance.transformation_version().empty())
      return std::unexpected(ValueError::empty_required_field);
    return EventHeader(std::move(id), std::move(account), effective_at,
                       std::move(provenance));
  }

  [[nodiscard]] const EventId& id() const noexcept { return id_; }
  [[nodiscard]] const AccountId& account() const noexcept { return account_; }
  [[nodiscard]] Timestamp effective_at() const noexcept { return effective_at_; }
  [[nodiscard]] const Provenance& provenance() const noexcept { return provenance_; }
  bool operator==(const EventHeader&) const = default;

 private:
  [[nodiscard]] bool valid() const noexcept {
    if (id_.value().empty() || account_.value().empty() ||
        provenance_.source_records().empty() ||
        provenance_.transformation_name().empty() ||
        provenance_.transformation_version().empty())
      return false;
    for (const auto& source_record : provenance_.source_records())
      if (source_record.value().empty()) return false;
    return true;
  }
  friend class CashMovement;
  friend class EquityTrade;

  EventHeader(EventId id, AccountId account, Timestamp effective_at,
              Provenance provenance)
      : id_(std::move(id)), account_(std::move(account)), effective_at_(effective_at),
        provenance_(std::move(provenance)) {}

  EventId id_;
  AccountId account_;
  Timestamp effective_at_;
  Provenance provenance_;
};

class CashMovement {
 public:
  [[nodiscard]] static std::expected<CashMovement, ValueError> create(
      EventHeader header, Money amount) {
    if (!header.valid()) return std::unexpected(ValueError::empty_required_field);
    return CashMovement(std::move(header), amount);
  }

  [[nodiscard]] const EventHeader& header() const noexcept { return header_; }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  bool operator==(const CashMovement&) const = default;

 private:
  CashMovement(EventHeader header, Money amount)
      : header_(std::move(header)), amount_(amount) {}
  EventHeader header_;
  Money amount_;
};

class EquityTrade {
 public:
  [[nodiscard]] static std::expected<EquityTrade, ValueError> create(
      EventHeader header, InstrumentId instrument, Quantity quantity, Price price,
      Currency quote_currency, SettlementDate settlement_date) {
    if (!header.valid()) return std::unexpected(ValueError::empty_required_field);
    if (instrument.value().empty())
      return std::unexpected(ValueError::empty_identifier);
    if (quantity.scaled_value() == 0)
      return std::unexpected(ValueError::zero_quantity);
    return EquityTrade(std::move(header), std::move(instrument), quantity, price,
                       quote_currency, settlement_date);
  }

  [[nodiscard]] const EventHeader& header() const noexcept { return header_; }
  [[nodiscard]] const InstrumentId& instrument() const noexcept { return instrument_; }
  [[nodiscard]] Quantity quantity() const noexcept { return quantity_; }
  [[nodiscard]] Price price() const noexcept { return price_; }
  [[nodiscard]] Currency quote_currency() const noexcept { return quote_currency_; }
  [[nodiscard]] SettlementDate settlement_date() const noexcept { return settlement_date_; }
  bool operator==(const EquityTrade&) const = default;

 private:
  EquityTrade(EventHeader header, InstrumentId instrument, Quantity quantity,
              Price price, Currency quote_currency, SettlementDate settlement_date)
      : header_(std::move(header)), instrument_(std::move(instrument)),
        quantity_(quantity), price_(price), quote_currency_(quote_currency),
        settlement_date_(settlement_date) {}

  EventHeader header_;
  InstrumentId instrument_;
  Quantity quantity_;
  Price price_;
  Currency quote_currency_;
  SettlementDate settlement_date_;
};

using EconomicEvent = std::variant<CashMovement, EquityTrade>;

[[nodiscard]] inline const EventHeader& header(const EconomicEvent& event) noexcept {
  return std::visit([](const auto& value) -> const EventHeader& {
    return value.header();
  }, event);
}

}  // namespace luca
