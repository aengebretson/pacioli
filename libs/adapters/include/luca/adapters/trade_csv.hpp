#pragma once

#include "luca/reconciliation/trade_observation.hpp"

#include <array>
#include <cstddef>
#include <map>
#include <optional>

namespace luca::adapters {

inline constexpr std::string_view trade_csv_header =
    "external_trade_id,account,instrument,quantity,price,currency,trade_date,settlement_date";

struct TradeCsvSource {
  SourceId source;
  SourceRecordId statement_id;
  PayloadHash payload_hash;
  Timestamp observed_at;
};

// Callers may lower these caps; increasing them is rejected, so this API always
// has a finite documented bound independent of untrusted input.
struct TradeCsvLimits {
  std::size_t max_bytes = 8 * 1024 * 1024;
  std::size_t max_rows = 100000;
  std::size_t max_record_bytes = 8192;
  std::size_t max_field_bytes = 1024;
};
enum class TradeCsvErrorCode {
  invalid_limits, invalid_source, input_too_large, invalid_utf8,
  missing_header, invalid_header, record_too_large, field_too_large,
  too_many_rows, malformed_csv, wrong_column_count, invalid_identifier,
  invalid_decimal, invalid_currency, invalid_date, invalid_trade,
  outside_coverage, duplicate_key,
};
struct TradeCsvError {
  TradeCsvErrorCode code;
  std::size_t row;     // Physical line, header is 1; 0 denotes whole input/context.
  std::size_t column;  // Schema column, 1..8; 0 denotes whole record/input.
  std::optional<TradeKey> key = std::nullopt;
  std::optional<TradeValueError> value_error = std::nullopt;
  bool operator==(const TradeCsvError&) const = default;
};

namespace trade_csv_detail {
inline std::expected<std::array<std::string, 8>, TradeCsvError> fields(
    std::string_view line, std::size_t row, std::size_t field_limit) {
  std::array<std::string, 8> result;
  std::size_t position = 0;
  std::size_t column = 0;
  while (true) {
    if (column == result.size())
      return std::unexpected(TradeCsvError{TradeCsvErrorCode::wrong_column_count, row, 0});
    auto& field = result[column];
    const bool quoted = position < line.size() && line[position] == '"';
    if (quoted) ++position;
    bool closed = !quoted;
    while (position < line.size()) {
      const char c = line[position];
      if (c == '\r' || c == '\n' || c == '\0')
        return std::unexpected(TradeCsvError{TradeCsvErrorCode::malformed_csv, row, column + 1});
      if (quoted && c == '"') {
        ++position;
        if (position == line.size() || line[position] != '"') { closed = true; break; }
        // Doubled quote contributes one decoded byte.
      } else if (!quoted && c == ',') break;
      else if (!quoted && c == '"')
        return std::unexpected(TradeCsvError{TradeCsvErrorCode::malformed_csv, row, column + 1});
      if (field.size() == field_limit)
        return std::unexpected(TradeCsvError{TradeCsvErrorCode::field_too_large, row, column + 1});
      field.push_back(c);
      ++position;
    }
    if (!closed || (position < line.size() && line[position] != ','))
      return std::unexpected(TradeCsvError{TradeCsvErrorCode::malformed_csv, row, column + 1});
    ++column;
    if (position == line.size()) break;
    ++position;  // comma; next iteration also handles a trailing empty field
  }
  if (column != result.size())
    return std::unexpected(TradeCsvError{TradeCsvErrorCode::wrong_column_count, row, 0});
  return result;
}

// Closed decimal grammar: -?[0-9]+(\.[0-9]{1,8})?. No plus, exponent,
// whitespace, separators, leading/trailing decimal point, rounding or float.
inline bool decimal(std::string_view text) noexcept {
  std::size_t i = 0;
  if (!text.empty() && text.front() == '-') ++i;
  const auto start = i;
  while (i < text.size() && text[i] >= '0' && text[i] <= '9') ++i;
  if (i == start) return false;
  if (i == text.size()) return true;
  if (text[i++] != '.') return false;
  const auto fraction = i;
  while (i < text.size() && text[i] >= '0' && text[i] <= '9') ++i;
  return i == text.size() && i > fraction && i - fraction <= 8;
}
inline std::optional<std::chrono::year_month_day> date(std::string_view text) noexcept {
  if (text.size() != 10 || text[4] != '-' || text[7] != '-') return std::nullopt;
  unsigned values[3]{};
  std::size_t part = 0;
  for (std::size_t i = 0; i < text.size(); ++i) {
    if (i == 4 || i == 7) { ++part; continue; }
    if (text[i] < '0' || text[i] > '9') return std::nullopt;
    values[part] = values[part] * 10 + static_cast<unsigned>(text[i] - '0');
  }
  if (values[0] == 0) return std::nullopt;
  const auto result = std::chrono::year{static_cast<int>(values[0])} /
                      std::chrono::month{values[1]} / std::chrono::day{values[2]};
  if (!result.ok()) return std::nullopt;
  return result;
}
}  // namespace trade_csv_detail

// Pure atomic ingestion. The supplied hash is retained, not computed/verified;
// parsing is not authentication or a persistence deduplication operation.
[[nodiscard]] inline std::expected<std::vector<TradeObservation>, TradeCsvError>
parse_trade_csv(std::string_view text, const TradeCsvSource& source,
                const TradeComparisonContext& context, TradeCsvLimits limits = {}) {
  using Code = TradeCsvErrorCode;
  constexpr TradeCsvLimits hard{};
  if (!limits.max_bytes || !limits.max_rows || !limits.max_record_bytes || !limits.max_field_bytes ||
      limits.max_bytes > hard.max_bytes || limits.max_rows > hard.max_rows ||
      limits.max_record_bytes > hard.max_record_bytes || limits.max_field_bytes > hard.max_field_bytes)
    return std::unexpected(TradeCsvError{Code::invalid_limits, 0, 0});
  if (!trade_detail::valid_identifier(source.source.value()) ||
      !trade_detail::valid_identifier(source.statement_id.value()) ||
      source.source.value().size() > hard.max_field_bytes ||
      source.statement_id.value().size() > hard.max_field_bytes ||
      source.payload_hash.algorithm().empty() || source.payload_hash.value().empty() ||
      source.payload_hash.algorithm().size() > hard.max_field_bytes ||
      source.payload_hash.value().size() > hard.max_field_bytes)
    return std::unexpected(TradeCsvError{Code::invalid_source, 0, 0});
  if (text.size() > limits.max_bytes)
    return std::unexpected(TradeCsvError{Code::input_too_large, 0, 0});
  if (!trade_detail::valid_utf8(text))
    return std::unexpected(TradeCsvError{Code::invalid_utf8, 0, 0});
  if (text.empty()) return std::unexpected(TradeCsvError{Code::missing_header, 1, 0});
  constexpr std::array<std::string_view, 8> header{
      "external_trade_id", "account", "instrument", "quantity", "price", "currency", "trade_date", "settlement_date"};
  std::vector<TradeObservation> result;
  std::map<TradeKey, std::size_t> keys;
  std::size_t position = 0;
  std::size_t row = 0;
  while (position < text.size()) {
    ++row;
    const auto newline = text.find('\n', position);
    const auto end = newline == std::string_view::npos ? text.size() : newline;
    auto line = text.substr(position, end - position);
    position = newline == std::string_view::npos ? text.size() : newline + 1;
    // A bare final CR is not a CRLF record terminator.
    if (newline != std::string_view::npos && !line.empty() && line.back() == '\r') line.remove_suffix(1);
    if (line.size() > limits.max_record_bytes)
      return std::unexpected(TradeCsvError{Code::record_too_large, row, 0});
    if (row > 1 && result.size() == limits.max_rows)
      return std::unexpected(TradeCsvError{Code::too_many_rows, row, 0});
    auto parsed = trade_csv_detail::fields(line, row, limits.max_field_bytes);
    if (!parsed) return std::unexpected(parsed.error());
    const auto& f = *parsed;
    if (row == 1) {
      for (std::size_t c = 0; c < header.size(); ++c)
        if (f[c] != header[c]) return std::unexpected(TradeCsvError{Code::invalid_header, row, c + 1});
      continue;
    }
    for (std::size_t c = 0; c < 3; ++c)
      if (!trade_detail::valid_identifier(f[c]))
        return std::unexpected(TradeCsvError{Code::invalid_identifier, row, c + 1});
    auto key = TradeKey::create(AccountId{f[1]}, f[0]);
    if (!key) return std::unexpected(TradeCsvError{Code::invalid_identifier, row, 1});
    if (!trade_csv_detail::decimal(f[3]))
      return std::unexpected(TradeCsvError{Code::invalid_decimal, row, 4});
    if (!trade_csv_detail::decimal(f[4]))
      return std::unexpected(TradeCsvError{Code::invalid_decimal, row, 5});
    const auto quantity = Quantity::parse(f[3]);
    const auto price = Price::parse(f[4]);
    if (!quantity) return std::unexpected(TradeCsvError{Code::invalid_decimal, row, 4});
    if (!price) return std::unexpected(TradeCsvError{Code::invalid_decimal, row, 5});
    const auto currency = Currency::from_code(f[5]);
    if (!currency) return std::unexpected(TradeCsvError{Code::invalid_currency, row, 6});
    const auto trade_date = trade_csv_detail::date(f[6]);
    const auto settlement_date = trade_csv_detail::date(f[7]);
    if (!trade_date) return std::unexpected(TradeCsvError{Code::invalid_date, row, 7});
    if (!settlement_date) return std::unexpected(TradeCsvError{Code::invalid_date, row, 8});
    auto terms = TradeTerms::create(InstrumentId{f[2]}, *quantity, *price, *currency,
                                    *trade_date, *SettlementDate::create(*settlement_date));
    if (!terms) return std::unexpected(TradeCsvError{
        Code::invalid_trade, row, quantity->scaled_value() == 0 ? 4U : 5U, *key, terms.error()});
    if (!context.covers(key->account()) || !context.covers(*trade_date))
      return std::unexpected(TradeCsvError{Code::outside_coverage, row, 0, *key});
    if (!keys.emplace(*key, row).second)
      return std::unexpected(TradeCsvError{Code::duplicate_key, row, 0, *key});
    // Length framing makes delimiters in identities unambiguous. Physical row
    // identity is stable across repeated parsing with the same source/context.
    SourceRecordId row_id{"trade-csv-v1:" + std::to_string(source.source.value().size()) + ":" +
        source.source.value() + ":" + std::to_string(source.statement_id.value().size()) + ":" +
        source.statement_id.value() + ":" + std::to_string(row)};
    auto evidence = SourceRecord::create(source.source, row_id, key->external_trade_id(),
        source.observed_at, std::nullopt, source.payload_hash, "trade.csv.v1", source.statement_id.value());
    auto provenance = Provenance::create({row_id}, "luca.trade-csv", "1");
    // All factories' preconditions are validated above; keep errors explicit.
    if (!evidence || !provenance)
      return std::unexpected(TradeCsvError{Code::invalid_source, row, 0});
    auto observation = TradeObservation::create(std::move(*key), std::move(*terms), context,
                                                std::move(*evidence), std::move(*provenance));
    if (!observation) return std::unexpected(TradeCsvError{
        Code::invalid_trade, row, 0, std::nullopt, observation.error()});
    result.push_back(std::move(*observation));
  }
  return result;
}

}  // namespace luca::adapters
