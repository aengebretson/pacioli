#pragma once

#include "luca/core.hpp"
#include "luca/time.hpp"

#include <algorithm>
#include <chrono>
#include <compare>
#include <cstdint>
#include <expected>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca {

enum class TradeValueError {
  invalid_identifier, invalid_coverage, invalid_date, zero_quantity,
  negative_price, outside_coverage, incomplete_evidence,
};

namespace trade_detail {
// Strict scalar UTF-8: reject overlong encodings, surrogates and > U+10FFFF.
inline bool valid_utf8(std::string_view text) noexcept {
  for (std::size_t i = 0; i < text.size();) {
    const auto first = static_cast<unsigned char>(text[i++]);
    if (first < 0x80) continue;
    unsigned count;
    std::uint32_t point;
    std::uint32_t minimum;
    if (first >= 0xc2 && first <= 0xdf) {
      count = 1; point = first & 0x1fU; minimum = 0x80;
    } else if (first >= 0xe0 && first <= 0xef) {
      count = 2; point = first & 0x0fU; minimum = 0x800;
    } else if (first >= 0xf0 && first <= 0xf4) {
      count = 3; point = first & 0x07U; minimum = 0x10000;
    } else return false;
    if (text.size() - i < count) return false;
    while (count--) {
      const auto next = static_cast<unsigned char>(text[i++]);
      if ((next & 0xc0U) != 0x80U) return false;
      point = (point << 6U) | (next & 0x3fU);
    }
    if (point < minimum || point > 0x10ffff ||
        (point >= 0xd800 && point <= 0xdfff)) return false;
  }
  return true;
}

// Normalized identifiers are supplied by the caller. No trimming, case folding,
// Unicode normalization, symbol aliasing or internal-ID inference occurs here.
inline bool valid_identifier(std::string_view text) noexcept {
  if (text.empty() || text.front() == ' ' || text.back() == ' ' ||
      !valid_utf8(text)) return false;
  for (unsigned char c : text)
    if (c < 0x20 || c == 0x7f) return false;
  return true;
}
}  // namespace trade_detail

class TradeKey {
 public:
  [[nodiscard]] static std::expected<TradeKey, TradeValueError> create(
      AccountId account, std::string external_trade_id) {
    if (!trade_detail::valid_identifier(account.value()) ||
        !trade_detail::valid_identifier(external_trade_id))
      return std::unexpected(TradeValueError::invalid_identifier);
    return TradeKey(std::move(account), std::move(external_trade_id));
  }
  [[nodiscard]] const AccountId& account() const noexcept { return account_; }
  [[nodiscard]] const std::string& external_trade_id() const noexcept { return external_trade_id_; }
  auto operator<=>(const TradeKey&) const = default;
 private:
  TradeKey(AccountId account, std::string id)
      : account_(std::move(account)), external_trade_id_(std::move(id)) {}
  AccountId account_;
  std::string external_trade_id_;
};

class TradeComparisonContext {
 public:
  static constexpr std::string_view policy = "luca.trade-comparison.exact";
  static constexpr std::string_view version = "1";
  [[nodiscard]] static std::expected<TradeComparisonContext, TradeValueError> create(
      Timestamp economic_as_of, Timestamp recorded_through,
      std::chrono::year_month_day trade_date_from,
      std::chrono::year_month_day trade_date_through,
      std::vector<AccountId> accounts) {
    if (!trade_date_from.ok() || !trade_date_through.ok() ||
        trade_date_through < trade_date_from || accounts.empty())
      return std::unexpected(TradeValueError::invalid_coverage);
    for (const auto& account : accounts)
      if (!trade_detail::valid_identifier(account.value()))
        return std::unexpected(TradeValueError::invalid_identifier);
    std::sort(accounts.begin(), accounts.end());
    if (std::adjacent_find(accounts.begin(), accounts.end()) != accounts.end())
      return std::unexpected(TradeValueError::invalid_coverage);
    return TradeComparisonContext(economic_as_of, recorded_through,
                                  trade_date_from, trade_date_through, std::move(accounts));
  }
  [[nodiscard]] Timestamp economic_as_of() const noexcept { return economic_as_of_; }
  [[nodiscard]] Timestamp recorded_through() const noexcept { return recorded_through_; }
  [[nodiscard]] auto trade_date_from() const noexcept { return trade_date_from_; }
  [[nodiscard]] auto trade_date_through() const noexcept { return trade_date_through_; }
  [[nodiscard]] std::span<const AccountId> accounts() const noexcept { return accounts_; }
  [[nodiscard]] bool covers(const AccountId& account) const {
    return std::binary_search(accounts_.begin(), accounts_.end(), account);
  }
  [[nodiscard]] bool covers(std::chrono::year_month_day date) const noexcept {
    return date.ok() && date >= trade_date_from_ && date <= trade_date_through_;
  }
  bool operator==(const TradeComparisonContext&) const = default;
 private:
  TradeComparisonContext(Timestamp economic, Timestamp knowledge,
                         std::chrono::year_month_day from,
                         std::chrono::year_month_day through, std::vector<AccountId> accounts)
      : economic_as_of_(economic), recorded_through_(knowledge), trade_date_from_(from),
        trade_date_through_(through), accounts_(std::move(accounts)) {}
  Timestamp economic_as_of_;
  Timestamp recorded_through_;
  std::chrono::year_month_day trade_date_from_;
  std::chrono::year_month_day trade_date_through_;
  std::vector<AccountId> accounts_;
};

class TradeTerms {
 public:
  [[nodiscard]] static std::expected<TradeTerms, TradeValueError> create(
      InstrumentId instrument, Quantity quantity, Price price, Currency currency,
      std::chrono::year_month_day trade_date, SettlementDate settlement_date) {
    if (!trade_detail::valid_identifier(instrument.value()))
      return std::unexpected(TradeValueError::invalid_identifier);
    if (!trade_date.ok()) return std::unexpected(TradeValueError::invalid_date);
    if (quantity.scaled_value() == 0) return std::unexpected(TradeValueError::zero_quantity);
    if (price.scaled_value() < 0) return std::unexpected(TradeValueError::negative_price);
    return TradeTerms(std::move(instrument), quantity, price, currency, trade_date, settlement_date);
  }
  [[nodiscard]] const InstrumentId& instrument() const noexcept { return instrument_; }
  [[nodiscard]] Quantity quantity() const noexcept { return quantity_; }
  [[nodiscard]] Price price() const noexcept { return price_; }
  [[nodiscard]] Currency currency() const noexcept { return currency_; }
  [[nodiscard]] auto trade_date() const noexcept { return trade_date_; }
  [[nodiscard]] SettlementDate settlement_date() const noexcept { return settlement_date_; }
  bool operator==(const TradeTerms&) const = default;
 private:
  TradeTerms(InstrumentId instrument, Quantity quantity, Price price, Currency currency,
             std::chrono::year_month_day trade_date, SettlementDate settlement_date)
      : instrument_(std::move(instrument)), quantity_(quantity), price_(price), currency_(currency),
        trade_date_(trade_date), settlement_date_(settlement_date) {}
  InstrumentId instrument_;
  Quantity quantity_;
  Price price_;
  Currency currency_;
  std::chrono::year_month_day trade_date_;
  SettlementDate settlement_date_;
};

// External evidence only: no conversion to an EconomicEvent or projected row.
class TradeObservation {
 public:
  [[nodiscard]] static std::expected<TradeObservation, TradeValueError> create(
      TradeKey key, TradeTerms terms, TradeComparisonContext context,
      SourceRecord source_record, Provenance provenance) {
    if (!context.covers(key.account()) || !context.covers(terms.trade_date()))
      return std::unexpected(TradeValueError::outside_coverage);
    // One statement row is the complete external evidence for this claim.
    if (provenance.source_records().size() != 1 ||
        provenance.source_records().front() != source_record.id())
      return std::unexpected(TradeValueError::incomplete_evidence);
    return TradeObservation(std::move(key), std::move(terms), std::move(context),
                            std::move(source_record), std::move(provenance));
  }
  [[nodiscard]] const TradeKey& key() const noexcept { return key_; }
  [[nodiscard]] const TradeTerms& terms() const noexcept { return terms_; }
  [[nodiscard]] const TradeComparisonContext& context() const noexcept { return context_; }
  [[nodiscard]] const SourceRecord& source_record() const noexcept { return source_record_; }
  [[nodiscard]] const Provenance& provenance() const noexcept { return provenance_; }
  bool operator==(const TradeObservation&) const = default;
 private:
  TradeObservation(TradeKey key, TradeTerms terms, TradeComparisonContext context,
                   SourceRecord source_record, Provenance provenance)
      : key_(std::move(key)), terms_(std::move(terms)), context_(std::move(context)),
        source_record_(std::move(source_record)), provenance_(std::move(provenance)) {}
  TradeKey key_;
  TradeTerms terms_;
  TradeComparisonContext context_;
  SourceRecord source_record_;
  Provenance provenance_;
};

}  // namespace luca
