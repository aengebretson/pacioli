#include "luca/reconciliation.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <exception>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t max_input_bytes = 1U << 20U;
constexpr std::size_t max_nesting = 16U;
constexpr std::size_t max_container_items = 8192U;
constexpr std::size_t max_partials = 4096U;
constexpr std::size_t max_observations = 4096U;
constexpr std::size_t max_lineage_items = 4096U;
constexpr std::size_t max_string_bytes = 65536U;
constexpr std::string_view schema_version = "luca.exact-cash-cli.v1";

class Failure final : public std::exception {
public:
  Failure(std::string category, std::string message)
      : category_(std::move(category)), message_(std::move(message)) {}

  [[nodiscard]] const char *what() const noexcept override { return message_.c_str(); }
  [[nodiscard]] const std::string &category() const noexcept { return category_; }

private:
  std::string category_;
  std::string message_;
};

[[noreturn]] void fail(std::string category, std::string message) {
  throw Failure{std::move(category), std::move(message)};
}

[[nodiscard]] bool valid_utf8(std::string_view input) noexcept {
  std::size_t position = 0;
  while (position < input.size()) {
    const auto first = static_cast<unsigned char>(input[position]);
    if (first <= 0x7fU) {
      ++position;
      continue;
    }

    std::size_t continuation_count = 0;
    std::uint32_t code_point = 0;
    if (first >= 0xc2U && first <= 0xdfU) {
      continuation_count = 1;
      code_point = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      continuation_count = 2;
      code_point = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      continuation_count = 3;
      code_point = first & 0x07U;
    } else {
      return false;
    }
    if (position + continuation_count >= input.size())
      return false;
    for (std::size_t index = 1; index <= continuation_count; ++index) {
      const auto next = static_cast<unsigned char>(input[position + index]);
      if ((next & 0xc0U) != 0x80U)
        return false;
      code_point = (code_point << 6U) | (next & 0x3fU);
    }
    if ((continuation_count == 2 && code_point < 0x800U) ||
        (continuation_count == 3 && code_point < 0x10000U) ||
        (code_point >= 0xd800U && code_point <= 0xdfffU) || code_point > 0x10ffffU) {
      return false;
    }
    position += continuation_count + 1U;
  }
  return true;
}

enum class JsonKind { null_value, boolean, number, string, array, object };

struct JsonValue {
  JsonKind kind{JsonKind::null_value};
  std::string text;
  bool boolean{};
  std::vector<JsonValue> array;
  std::vector<std::pair<std::string, JsonValue>> object;
};

class JsonParser {
public:
  explicit JsonParser(std::string_view input) : input_(input) {}

  [[nodiscard]] JsonValue parse() {
    skip_space();
    auto result = parse_value(0);
    skip_space();
    if (position_ != input_.size())
      syntax("trailing content after the JSON value");
    return result;
  }

private:
  [[noreturn]] void syntax(std::string message) const {
    fail("invalid_json", std::move(message) + " at byte " + std::to_string(position_));
  }

  void skip_space() noexcept {
    while (position_ < input_.size()) {
      const char character = input_[position_];
      if (character != ' ' && character != '\n' && character != '\r' && character != '\t')
        return;
      ++position_;
    }
  }

  [[nodiscard]] bool consume(char expected) noexcept {
    if (position_ == input_.size() || input_[position_] != expected)
      return false;
    ++position_;
    return true;
  }

  void expect(char expected) {
    if (!consume(expected))
      syntax(std::string{"expected '"} + expected + "'");
  }

  [[nodiscard]] JsonValue parse_value(std::size_t depth) {
    if (depth > max_nesting)
      fail("nesting_limit_exceeded", "JSON nesting exceeds 16 levels");
    if (position_ == input_.size())
      syntax("expected a JSON value");
    switch (input_[position_]) {
    case 'n':
      parse_literal("null");
      return {};
    case 't':
      parse_literal("true");
      return boolean_value(true);
    case 'f':
      parse_literal("false");
      return boolean_value(false);
    case '"': {
      JsonValue result;
      result.kind = JsonKind::string;
      result.text = parse_string();
      return result;
    }
    case '[':
      return parse_array(depth + 1U);
    case '{':
      return parse_object(depth + 1U);
    default:
      if (input_[position_] == '-' || (input_[position_] >= '0' && input_[position_] <= '9')) {
        JsonValue result;
        result.kind = JsonKind::number;
        result.text = parse_number();
        return result;
      }
      syntax("expected a JSON value");
    }
  }

  [[nodiscard]] static JsonValue boolean_value(bool value) {
    JsonValue result;
    result.kind = JsonKind::boolean;
    result.boolean = value;
    return result;
  }

  void parse_literal(std::string_view literal) {
    if (input_.substr(position_, literal.size()) != literal)
      syntax("invalid JSON literal");
    position_ += literal.size();
  }

  [[nodiscard]] static unsigned hex_digit(char character) noexcept {
    if (character >= '0' && character <= '9')
      return static_cast<unsigned>(character - '0');
    if (character >= 'a' && character <= 'f')
      return static_cast<unsigned>(character - 'a') + 10U;
    if (character >= 'A' && character <= 'F')
      return static_cast<unsigned>(character - 'A') + 10U;
    return 16U;
  }

  [[nodiscard]] std::uint32_t parse_hex_quad() {
    if (input_.size() - position_ < 4U)
      syntax("truncated Unicode escape");
    std::uint32_t result = 0;
    for (unsigned index = 0; index < 4U; ++index) {
      const unsigned digit = hex_digit(input_[position_++]);
      if (digit > 15U)
        syntax("invalid Unicode escape");
      result = (result << 4U) | digit;
    }
    return result;
  }

  static void append_utf8(std::string &output, std::uint32_t code_point) {
    if (code_point <= 0x7fU) {
      output.push_back(static_cast<char>(code_point));
    } else if (code_point <= 0x7ffU) {
      output.push_back(static_cast<char>(0xc0U | (code_point >> 6U)));
      output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
    } else if (code_point <= 0xffffU) {
      output.push_back(static_cast<char>(0xe0U | (code_point >> 12U)));
      output.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
    } else {
      output.push_back(static_cast<char>(0xf0U | (code_point >> 18U)));
      output.push_back(static_cast<char>(0x80U | ((code_point >> 12U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
    }
  }

  [[nodiscard]] std::string parse_string() {
    expect('"');
    std::string result;
    while (position_ < input_.size()) {
      const auto character = static_cast<unsigned char>(input_[position_++]);
      if (character == '"') {
        if (result.size() > max_string_bytes)
          fail("string_limit_exceeded", "JSON string exceeds 65536 bytes");
        return result;
      }
      if (character < 0x20U)
        syntax("unescaped control character in JSON string");
      if (character != '\\') {
        result.push_back(static_cast<char>(character));
        continue;
      }
      if (position_ == input_.size())
        syntax("truncated JSON escape");
      const char escaped = input_[position_++];
      switch (escaped) {
      case '"':
      case '\\':
      case '/':
        result.push_back(escaped);
        break;
      case 'b':
        result.push_back('\b');
        break;
      case 'f':
        result.push_back('\f');
        break;
      case 'n':
        result.push_back('\n');
        break;
      case 'r':
        result.push_back('\r');
        break;
      case 't':
        result.push_back('\t');
        break;
      case 'u': {
        auto code_point = parse_hex_quad();
        if (code_point >= 0xd800U && code_point <= 0xdbffU) {
          if (input_.size() - position_ < 6U || input_[position_] != '\\' ||
              input_[position_ + 1U] != 'u') {
            syntax("high surrogate is not followed by a low surrogate");
          }
          position_ += 2U;
          const auto low = parse_hex_quad();
          if (low < 0xdc00U || low > 0xdfffU)
            syntax("high surrogate is not followed by a low surrogate");
          code_point = 0x10000U + ((code_point - 0xd800U) << 10U) + (low - 0xdc00U);
        } else if (code_point >= 0xdc00U && code_point <= 0xdfffU) {
          syntax("unpaired low surrogate");
        }
        append_utf8(result, code_point);
        break;
      }
      default:
        syntax("invalid JSON escape");
      }
      if (result.size() > max_string_bytes)
        fail("string_limit_exceeded", "JSON string exceeds 65536 bytes");
    }
    syntax("unterminated JSON string");
  }

  [[nodiscard]] std::string parse_number() {
    const auto start = position_;
    const bool negative = consume('-');
    (void)negative;
    if (position_ == input_.size())
      syntax("truncated JSON number");
    if (consume('0')) {
      if (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9')
        syntax("leading zero in JSON number");
    } else {
      if (input_[position_] < '1' || input_[position_] > '9')
        syntax("invalid JSON number");
      while (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9')
        ++position_;
    }
    if (consume('.')) {
      if (position_ == input_.size() || input_[position_] < '0' || input_[position_] > '9')
        syntax("invalid JSON fraction");
      while (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9')
        ++position_;
    }
    if (position_ < input_.size() && (input_[position_] == 'e' || input_[position_] == 'E')) {
      ++position_;
      if (position_ < input_.size() && (input_[position_] == '+' || input_[position_] == '-'))
        ++position_;
      if (position_ == input_.size() || input_[position_] < '0' || input_[position_] > '9')
        syntax("invalid JSON exponent");
      while (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9')
        ++position_;
    }
    return std::string{input_.substr(start, position_ - start)};
  }

  [[nodiscard]] JsonValue parse_array(std::size_t depth) {
    expect('[');
    skip_space();
    JsonValue result;
    result.kind = JsonKind::array;
    if (consume(']'))
      return result;
    for (;;) {
      if (result.array.size() == max_container_items)
        fail("count_limit_exceeded", "JSON array exceeds 8192 items");
      result.array.push_back(parse_value(depth));
      skip_space();
      if (consume(']'))
        return result;
      expect(',');
      skip_space();
    }
  }

  [[nodiscard]] JsonValue parse_object(std::size_t depth) {
    expect('{');
    skip_space();
    JsonValue result;
    result.kind = JsonKind::object;
    if (consume('}'))
      return result;
    for (;;) {
      if (result.object.size() == max_container_items)
        fail("count_limit_exceeded", "JSON object exceeds 8192 members");
      if (position_ == input_.size() || input_[position_] != '"')
        syntax("expected a JSON object member name");
      auto name = parse_string();
      if (std::ranges::any_of(result.object,
                              [&name](const auto &member) { return member.first == name; })) {
        fail("duplicate_member", "duplicate JSON member");
      }
      skip_space();
      expect(':');
      skip_space();
      result.object.emplace_back(std::move(name), parse_value(depth));
      skip_space();
      if (consume('}'))
        return result;
      expect(',');
      skip_space();
    }
  }

  std::string_view input_;
  std::size_t position_{};
};

[[nodiscard]] std::string_view kind_name(JsonKind kind) noexcept {
  switch (kind) {
  case JsonKind::null_value:
    return "null";
  case JsonKind::boolean:
    return "boolean";
  case JsonKind::number:
    return "number";
  case JsonKind::string:
    return "string";
  case JsonKind::array:
    return "array";
  case JsonKind::object:
    return "object";
  }
  return "value";
}

void require_kind(const JsonValue &value, JsonKind kind, std::string_view path) {
  if (value.kind != kind) {
    fail("invalid_value", std::string{path} + " must be a JSON " + std::string{kind_name(kind)});
  }
}

[[nodiscard]] bool listed(std::string_view name,
                          std::initializer_list<std::string_view> names) noexcept {
  return std::ranges::find(names, name) != names.end();
}

void require_closed_object(const JsonValue &value, std::string_view path,
                           std::initializer_list<std::string_view> required,
                           std::initializer_list<std::string_view> optional = {}) {
  require_kind(value, JsonKind::object, path);
  for (const auto &[name, member] : value.object) {
    (void)member;
    if (!listed(name, required) && !listed(name, optional))
      fail("unknown_member", std::string{path} + " contains an unknown member");
  }
  for (const auto name : required) {
    const auto found = std::ranges::find_if(
        value.object, [name](const auto &member) { return member.first == name; });
    if (found == value.object.end())
      fail("missing_member", std::string{path} + " is missing member '" + std::string{name} + "'");
  }
}

[[nodiscard]] const JsonValue &member(const JsonValue &object, std::string_view name) {
  const auto found = std::ranges::find_if(
      object.object, [name](const auto &candidate) { return candidate.first == name; });
  if (found == object.object.end())
    fail("missing_member", "missing JSON member '" + std::string{name} + "'");
  return found->second;
}

[[nodiscard]] const std::string &text(const JsonValue &value, std::string_view path) {
  require_kind(value, JsonKind::string, path);
  return value.text;
}

[[nodiscard]] bool valid_token(std::string_view value) noexcept {
  if (value.empty() || value.size() > 128U)
    return false;
  return std::ranges::all_of(value,
                             [](unsigned char byte) { return byte > 0x20U && byte != 0x7fU; });
}

[[nodiscard]] std::string token(const JsonValue &value, std::string_view path) {
  const auto &result = text(value, path);
  if (!valid_token(result))
    fail("invalid_identifier",
         std::string{path} + " must be a non-empty token of at most 128 bytes");
  return result;
}

[[nodiscard]] unsigned small_decimal(std::string_view value) noexcept {
  unsigned result = 0;
  for (const char digit : value)
    result = result * 10U + static_cast<unsigned>(digit - '0');
  return result;
}

[[nodiscard]] bool digits(std::string_view value) noexcept {
  return std::ranges::all_of(value, [](char digit) { return digit >= '0' && digit <= '9'; });
}

[[nodiscard]] luca::SettlementDate parse_date(std::string_view value, std::string_view path) {
  if (value.size() != 10U || value[4] != '-' || value[7] != '-' || !digits(value.substr(0, 4)) ||
      !digits(value.substr(5, 2)) || !digits(value.substr(8, 2))) {
    fail("invalid_context", std::string{path} + " must be a canonical YYYY-MM-DD date");
  }
  const auto date = std::chrono::year{static_cast<int>(small_decimal(value.substr(0, 4)))} /
                    std::chrono::month{small_decimal(value.substr(5, 2))} /
                    std::chrono::day{small_decimal(value.substr(8, 2))};
  const auto result = luca::SettlementDate::create(date);
  if (!result || static_cast<int>(date.year()) == 0)
    fail("invalid_context", std::string{path} + " is not a valid date");
  return *result;
}

[[nodiscard]] luca::Timestamp parse_timestamp(std::string_view value, std::string_view path) {
  using namespace std::chrono;
  if (value.size() != 20U || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
      value[13] != ':' || value[16] != ':' || value[19] != 'Z' || !digits(value.substr(0, 4)) ||
      !digits(value.substr(5, 2)) || !digits(value.substr(8, 2)) || !digits(value.substr(11, 2)) ||
      !digits(value.substr(14, 2)) || !digits(value.substr(17, 2))) {
    fail("invalid_context", std::string{path} + " must be a canonical UTC timestamp");
  }
  const auto date = year{static_cast<int>(small_decimal(value.substr(0, 4)))} /
                    month{small_decimal(value.substr(5, 2))} /
                    day{small_decimal(value.substr(8, 2))};
  const auto hour = small_decimal(value.substr(11, 2));
  const auto minute = small_decimal(value.substr(14, 2));
  const auto second = small_decimal(value.substr(17, 2));
  if (!date.ok() || static_cast<int>(date.year()) == 0 || hour > 23U || minute > 59U ||
      second > 59U) {
    fail("invalid_context", std::string{path} + " is not a valid UTC timestamp");
  }

  constexpr auto nanoseconds_per_day = duration_cast<nanoseconds>(days{1}).count();
  constexpr auto floor_days = [nanoseconds_per_day](std::int64_t count) {
    auto result = count / nanoseconds_per_day;
    if (count % nanoseconds_per_day < 0)
      --result;
    return result;
  };
  constexpr auto day_remainder = [nanoseconds_per_day](std::int64_t count) {
    auto result = count % nanoseconds_per_day;
    if (result < 0)
      result += nanoseconds_per_day;
    return result;
  };
  constexpr auto minimum_count = luca::Timestamp::duration::min().count();
  constexpr auto maximum_count = luca::Timestamp::duration::max().count();
  constexpr auto minimum_day = floor_days(minimum_count);
  constexpr auto maximum_day = floor_days(maximum_count);
  constexpr auto minimum_time = day_remainder(minimum_count);
  constexpr auto maximum_time = day_remainder(maximum_count);
  const auto parsed_day = sys_days{date}.time_since_epoch().count();
  const auto time_of_day = static_cast<std::int64_t>(hour) * 3'600'000'000'000LL +
                           static_cast<std::int64_t>(minute) * 60'000'000'000LL +
                           static_cast<std::int64_t>(second) * 1'000'000'000LL;
  if (parsed_day < minimum_day || parsed_day > maximum_day ||
      (parsed_day == minimum_day && time_of_day < minimum_time) ||
      (parsed_day == maximum_day && time_of_day > maximum_time)) {
    fail("invalid_context", std::string{path} + " is outside the timestamp range");
  }
  const auto count = parsed_day >= 0 ? parsed_day * nanoseconds_per_day + time_of_day
                                     : (parsed_day + 1) * nanoseconds_per_day +
                                           (time_of_day - nanoseconds_per_day);
  return luca::Timestamp{nanoseconds{count}};
}

[[nodiscard]] luca::Money parse_money(std::string_view amount, luca::Currency currency,
                                      std::string_view path) {
  std::string_view magnitude = amount;
  bool negative = false;
  if (!magnitude.empty() && magnitude.front() == '-') {
    negative = true;
    magnitude.remove_prefix(1);
  }
  const auto decimal = magnitude.find('.');
  const bool canonical =
      !magnitude.empty() && decimal != std::string_view::npos && decimal != 0U &&
      magnitude.size() - decimal - 1U == luca::Money::scale &&
      digits(magnitude.substr(0, decimal)) && digits(magnitude.substr(decimal + 1U)) &&
      (decimal == 1U || magnitude.front() != '0') && !(negative && magnitude == "0.000000");
  if (!canonical)
    fail("invalid_decimal", std::string{path} + " must be canonical scale-6 decimal text");
  const auto result = luca::Money::parse(amount, currency);
  if (!result)
    fail("invalid_decimal", std::string{path} + " is outside the exact Money range");
  return *result;
}

[[nodiscard]] luca::Currency parse_currency(const JsonValue &value, std::string_view path) {
  const auto &code = text(value, path);
  const auto result = luca::Currency::from_code(code);
  if (!result)
    fail("invalid_currency", std::string{path} + " must be an uppercase three-letter code");
  return *result;
}

[[nodiscard]] std::vector<std::string> parse_tokens(const JsonValue &value, std::string_view path) {
  require_kind(value, JsonKind::array, path);
  if (value.array.empty())
    fail("incomplete_lineage", std::string{path} + " must not be empty");
  if (value.array.size() > max_lineage_items)
    fail("count_limit_exceeded", std::string{path} + " exceeds 4096 items");
  std::vector<std::string> result;
  result.reserve(value.array.size());
  for (std::size_t index = 0; index < value.array.size(); ++index) {
    result.push_back(
        token(value.array[index], std::string{path} + "[" + std::to_string(index) + "]"));
  }
  return result;
}

struct PolicyDeclaration {
  std::string id;
  std::string version;
};

struct OperationDeclaration {
  std::string id;
  std::string version;
  PolicyDeclaration policy;
};

[[nodiscard]] PolicyDeclaration parse_policy(const JsonValue &value, std::string_view path) {
  require_closed_object(value, path, {"id", "version"});
  return PolicyDeclaration{token(member(value, "id"), std::string{path} + ".id"),
                           token(member(value, "version"), std::string{path} + ".version")};
}

void require_text_value(const JsonValue &value, std::string_view path, std::string_view expected) {
  if (text(value, path) != expected)
    fail("unsupported_operation", std::string{path} + " must be '" + std::string{expected} + "'");
}

[[nodiscard]] OperationDeclaration parse_reduction(const JsonValue &value) {
  constexpr std::string_view path = "$.operations.reduction";
  require_closed_object(value, path,
                        {"operation_id", "operation_version", "policy", "unit", "partition_keys",
                         "ordering", "rounding"});
  auto operation = OperationDeclaration{
      token(member(value, "operation_id"), "$.operations.reduction.operation_id"),
      token(member(value, "operation_version"), "$.operations.reduction.operation_version"),
      parse_policy(member(value, "policy"), "$.operations.reduction.policy")};
  if (operation.id != luca::ExactCashReductionContract::operation_id)
    fail("unsupported_operation", "unsupported reduction operation '" + operation.id + "'");
  if (operation.version != "1" || operation.policy.version != "1")
    fail("unsupported_version", "unsupported reduction operation or policy version");
  if (operation.policy.id != "exact-cash-sum")
    fail("unsupported_operation", "unsupported reduction policy '" + operation.policy.id + "'");
  require_text_value(member(value, "unit"), "$.operations.reduction.unit", "money");
  require_text_value(member(value, "ordering"), "$.operations.reduction.ordering", "arbitrary");
  require_text_value(member(value, "rounding"), "$.operations.reduction.rounding", "none");
  const auto &keys = member(value, "partition_keys");
  require_kind(keys, JsonKind::array, "$.operations.reduction.partition_keys");
  if (keys.array.size() != 2U ||
      text(keys.array[0], "$.operations.reduction.partition_keys[0]") != "account" ||
      text(keys.array[1], "$.operations.reduction.partition_keys[1]") != "currency") {
    fail("partition_key_mismatch", "reduction partition_keys must be ['account','currency']");
  }
  return operation;
}

[[nodiscard]] OperationDeclaration parse_comparison(const JsonValue &value) {
  constexpr std::string_view path = "$.operations.comparison";
  require_closed_object(
      value, path,
      {"operation_id", "operation_version", "policy", "ordering", "rounding", "sign_convention"});
  auto operation = OperationDeclaration{
      token(member(value, "operation_id"), "$.operations.comparison.operation_id"),
      token(member(value, "operation_version"), "$.operations.comparison.operation_version"),
      parse_policy(member(value, "policy"), "$.operations.comparison.policy")};
  if (operation.id != luca::ExactCashComparisonContract::operation_id)
    fail("unsupported_operation", "unsupported comparison operation '" + operation.id + "'");
  if (operation.version != "1" || operation.policy.version != "1")
    fail("unsupported_version", "unsupported comparison operation or policy version");
  if (operation.policy.id != "exact-cash-comparison")
    fail("unsupported_operation", "unsupported comparison policy '" + operation.policy.id + "'");
  require_text_value(member(value, "ordering"), "$.operations.comparison.ordering",
                     "account_currency_break_kind");
  require_text_value(member(value, "rounding"), "$.operations.comparison.rounding", "none");
  require_text_value(member(value, "sign_convention"), "$.operations.comparison.sign_convention",
                     "observed_minus_expected");
  return operation;
}

struct EngineDeclaration {
  std::string id;
  std::string version;
};

[[nodiscard]] EngineDeclaration parse_engine(const JsonValue &value) {
  require_closed_object(value, "$.engine", {"id", "version"});
  auto result = EngineDeclaration{token(member(value, "id"), "$.engine.id"),
                                  token(member(value, "version"), "$.engine.version")};
  if (result.id != "luca")
    fail("unsupported_operation", "unsupported engine identity '" + result.id + "'");
  return result;
}

struct EvaluationContext {
  luca::ExactCashEvaluationContext value;
};

[[nodiscard]] EvaluationContext parse_context(const JsonValue &value,
                                              const EngineDeclaration &engine) {
  require_closed_object(value, "$.evaluation_context",
                        {"id", "recorded_through", "economic_as_of", "settlement_as_of_date"});
  const auto id = token(member(value, "id"), "$.evaluation_context.id");
  const auto recorded = parse_timestamp(
      text(member(value, "recorded_through"), "$.evaluation_context.recorded_through"),
      "$.evaluation_context.recorded_through");
  const auto economic =
      parse_timestamp(text(member(value, "economic_as_of"), "$.evaluation_context.economic_as_of"),
                      "$.evaluation_context.economic_as_of");
  const auto settlement = parse_date(
      text(member(value, "settlement_as_of_date"), "$.evaluation_context.settlement_as_of_date"),
      "$.evaluation_context.settlement_as_of_date");
  const auto result =
      luca::ExactCashEvaluationContext::create(id, engine.version, recorded, economic, settlement);
  if (!result)
    fail(std::string{luca::category_name(result.error())}, "invalid exact-cash evaluation context");
  return EvaluationContext{*result};
}

[[noreturn]] void fail_reduction(luca::ExactCashReductionError error) {
  fail(std::string{luca::category_name(error)}, "exact-cash reduction failed");
}

[[noreturn]] void fail_comparison(luca::ExactCashComparisonError error) {
  const auto category = error == luca::ExactCashComparisonError::duplicate_observation ||
                                error == luca::ExactCashComparisonError::duplicate_projected_key
                            ? "duplicate_key"
                            : luca::category_name(error);
  fail(std::string{category}, "exact-cash comparison failed");
}

[[nodiscard]] std::string read_input(std::istream &stream) {
  std::string result;
  result.reserve(8192U);
  std::array<char, 8192> buffer{};
  while (stream) {
    stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const auto count = stream.gcount();
    if (count > 0) {
      if (result.size() + static_cast<std::size_t>(count) > max_input_bytes)
        fail("input_too_large", "input exceeds 1048576 bytes");
      result.append(buffer.data(), static_cast<std::size_t>(count));
    }
  }
  if (!stream.eof())
    fail("input_error", "could not read the complete input");
  if (!valid_utf8(result))
    fail("invalid_utf8", "input must be valid UTF-8");
  return result;
}

void append_json_string(std::string &output, std::string_view value) {
  constexpr char hex[] = "0123456789abcdef";
  output.push_back('"');
  for (const char character : value) {
    const auto byte = static_cast<unsigned char>(character);
    switch (byte) {
    case '"':
      output += "\\\"";
      break;
    case '\\':
      output += "\\\\";
      break;
    case '\b':
      output += "\\b";
      break;
    case '\f':
      output += "\\f";
      break;
    case '\n':
      output += "\\n";
      break;
    case '\r':
      output += "\\r";
      break;
    case '\t':
      output += "\\t";
      break;
    default:
      if (byte < 0x20U) {
        output += "\\u00";
        output.push_back(hex[byte >> 4U]);
        output.push_back(hex[byte & 0x0fU]);
      } else {
        output.push_back(static_cast<char>(byte));
      }
    }
  }
  output.push_back('"');
}

void append_member(std::string &output, std::string_view name) {
  append_json_string(output, name);
  output.push_back(':');
}

[[nodiscard]] std::string format_money(luca::Money amount) {
  const auto scaled = amount.scaled_value();
  const bool negative = scaled < 0;
  const auto magnitude = negative ? static_cast<std::uint64_t>(-(scaled + 1)) + 1U
                                  : static_cast<std::uint64_t>(scaled);
  const auto whole = magnitude / 1'000'000U;
  const auto fraction = magnitude % 1'000'000U;
  std::array<char, 32> buffer{};
  const auto [end, error] = std::to_chars(buffer.data(), buffer.data() + buffer.size(), whole);
  (void)error;
  std::string result;
  if (negative)
    result.push_back('-');
  result.append(buffer.data(), end);
  result.push_back('.');
  const auto digits_count =
      fraction == 0U ? 1U : static_cast<unsigned>(std::to_string(fraction).size());
  result.append(6U - digits_count, '0');
  result += std::to_string(fraction);
  return result;
}

void append_padded(std::string &output, unsigned value, std::size_t width) {
  std::array<char, 16> buffer{};
  const auto [end, error] = std::to_chars(buffer.data(), buffer.data() + buffer.size(), value);
  (void)error;
  const auto count = static_cast<std::size_t>(end - buffer.data());
  output.append(width - count, '0');
  output.append(buffer.data(), end);
}

[[nodiscard]] std::string format_date(std::chrono::year_month_day date) {
  std::string result;
  result.reserve(10U);
  append_padded(result, static_cast<unsigned>(static_cast<int>(date.year())), 4U);
  result.push_back('-');
  append_padded(result, static_cast<unsigned>(date.month()), 2U);
  result.push_back('-');
  append_padded(result, static_cast<unsigned>(date.day()), 2U);
  return result;
}

[[nodiscard]] std::string format_timestamp(luca::Timestamp value) {
  using namespace std::chrono;
  const auto day = floor<days>(value);
  const year_month_day date{day};
  const hh_mm_ss time{value - day};
  std::string result = format_date(date);
  result.push_back('T');
  append_padded(result, static_cast<unsigned>(time.hours().count()), 2U);
  result.push_back(':');
  append_padded(result, static_cast<unsigned>(time.minutes().count()), 2U);
  result.push_back(':');
  append_padded(result, static_cast<unsigned>(time.seconds().count()), 2U);
  result.push_back('Z');
  return result;
}

template <class Identifier>
void append_identifiers(std::string &output, std::span<const Identifier> identifiers) {
  output.push_back('[');
  for (std::size_t index = 0; index < identifiers.size(); ++index) {
    if (index != 0U)
      output.push_back(',');
    append_json_string(output, identifiers[index].value());
  }
  output.push_back(']');
}

void append_projection(std::string &output, const luca::ExactCashReductionResult &projection) {
  output.push_back('{');
  append_member(output, "account");
  append_json_string(output, projection.key().account().value());
  output.push_back(',');
  append_member(output, "currency");
  append_json_string(output, projection.key().currency().code());
  output.push_back(',');
  append_member(output, "amount");
  append_json_string(output, format_money(projection.amount()));
  output.push_back(',');
  append_member(output, "source_event_ids");
  append_identifiers(output, projection.source_event_ids());
  output.push_back(',');
  append_member(output, "source_record_ids");
  append_identifiers(output, projection.source_record_ids());
  output.push_back('}');
}

void append_provenance(std::string &output, const luca::Provenance &provenance) {
  output.push_back('{');
  append_member(output, "source_record_ids");
  append_identifiers(output, provenance.source_records());
  output.push_back(',');
  append_member(output, "transformation_name");
  append_json_string(output, provenance.transformation_name());
  output.push_back(',');
  append_member(output, "transformation_version");
  append_json_string(output, provenance.transformation_version());
  output.push_back(',');
  append_member(output, "transformation_metadata");
  if (provenance.transformation_metadata())
    append_json_string(output, *provenance.transformation_metadata());
  else
    output += "null";
  output.push_back('}');
}

void append_observation(std::string &output, const luca::CashObservation &observation) {
  output.push_back('{');
  append_member(output, "account");
  append_json_string(output, observation.account().value());
  output.push_back(',');
  append_member(output, "currency");
  append_json_string(output, observation.currency().code());
  output.push_back(',');
  append_member(output, "amount");
  append_json_string(output, format_money(observation.amount()));
  output.push_back(',');
  append_member(output, "as_of");
  append_json_string(output, format_timestamp(observation.as_of()));
  output.push_back(',');
  append_member(output, "settlement_as_of_date");
  append_json_string(output, format_date(observation.settlement_as_of_date()));
  output.push_back(',');
  append_member(output, "provenance");
  append_provenance(output, observation.provenance());
  output.push_back('}');
}

void append_optional_money(std::string &output, const std::optional<luca::Money> &amount) {
  if (amount)
    append_json_string(output, format_money(*amount));
  else
    output += "null";
}

void append_trace(std::string &output, const OperationDeclaration &operation,
                  const EngineDeclaration &engine, const EvaluationContext &context) {
  output.push_back('{');
  append_member(output, "operation_id");
  append_json_string(output, operation.id);
  output.push_back(',');
  append_member(output, "operation_version");
  append_json_string(output, operation.version);
  output.push_back(',');
  append_member(output, "policy_id");
  append_json_string(output, operation.policy.id);
  output.push_back(',');
  append_member(output, "policy_version");
  append_json_string(output, operation.policy.version);
  output.push_back(',');
  append_member(output, "engine_id");
  append_json_string(output, engine.id);
  output.push_back(',');
  append_member(output, "engine_version");
  append_json_string(output, engine.version);
  output.push_back(',');
  append_member(output, "context_id");
  append_json_string(output, context.value.id());
  output.push_back('}');
}

[[nodiscard]] std::string execute(const JsonValue &root) {
  require_closed_object(
      root, "$",
      {"schema_version", "engine", "operations", "evaluation_context", "partials", "observations"});
  if (text(member(root, "schema_version"), "$.schema_version") != schema_version)
    fail("unsupported_schema_version", "unsupported exact-cash CLI schema version");

  const auto engine = parse_engine(member(root, "engine"));
  const auto &operations = member(root, "operations");
  require_closed_object(operations, "$.operations", {"reduction", "comparison"});
  const auto reduction_declaration = parse_reduction(member(operations, "reduction"));
  const auto comparison_declaration = parse_comparison(member(operations, "comparison"));
  const auto context = parse_context(member(root, "evaluation_context"), engine);

  const auto reduction_policy = luca::ExactCashReductionPolicy::create(
      reduction_declaration.policy.id, reduction_declaration.policy.version);
  if (!reduction_policy)
    fail_reduction(reduction_policy.error());

  const auto &partial_values = member(root, "partials");
  require_kind(partial_values, JsonKind::array, "$.partials");
  if (partial_values.array.size() > max_partials)
    fail("count_limit_exceeded", "$.partials exceeds 4096 items");

  std::map<luca::CashKey, std::vector<luca::ExactCashPartial>> groups;
  std::set<std::string> event_ids;
  for (std::size_t index = 0; index < partial_values.array.size(); ++index) {
    const auto path = "$.partials[" + std::to_string(index) + "]";
    const auto &partial_value = partial_values.array[index];
    require_closed_object(
        partial_value, path,
        {"account", "currency", "amount", "source_event_ids", "source_record_ids"});
    const auto account = token(member(partial_value, "account"), path + ".account");
    const auto currency = parse_currency(member(partial_value, "currency"), path + ".currency");
    const auto amount = parse_money(text(member(partial_value, "amount"), path + ".amount"),
                                    currency, path + ".amount");
    auto event_texts =
        parse_tokens(member(partial_value, "source_event_ids"), path + ".source_event_ids");
    auto source_texts =
        parse_tokens(member(partial_value, "source_record_ids"), path + ".source_record_ids");
    std::vector<luca::EventId> partial_events;
    partial_events.reserve(event_texts.size());
    for (auto &event_id : event_texts) {
      if (!event_ids.insert(event_id).second)
        fail("duplicate_event_lineage", "source event identity appears more than once");
      partial_events.emplace_back(std::move(event_id));
    }
    std::vector<luca::SourceRecordId> partial_sources;
    partial_sources.reserve(source_texts.size());
    for (auto &source_id : source_texts)
      partial_sources.emplace_back(std::move(source_id));

    const auto contract = luca::ExactCashReductionContract::create(
        luca::CashKey{luca::AccountId{account}, currency}, reduction_declaration.version,
        *reduction_policy, context.value, luca::ExactCashReductionUnit::money,
        luca::ExactCashPartitioning::account_currency());
    if (!contract)
      fail_reduction(contract.error());
    const auto partial = luca::ExactCashPartial::create(
        *contract, amount, std::move(partial_events), std::move(partial_sources));
    if (!partial)
      fail_reduction(partial.error());
    groups[partial->contract().key()].push_back(*partial);
  }

  std::vector<luca::ExactCashReductionResult> projections;
  projections.reserve(groups.size());
  for (const auto &[key, partials] : groups) {
    (void)key;
    const auto reduced = luca::reduce_exact_cash(partials.front().contract(), partials);
    if (!reduced)
      fail_reduction(reduced.error());
    projections.push_back(*reduced);
  }

  const auto &observation_values = member(root, "observations");
  require_kind(observation_values, JsonKind::array, "$.observations");
  if (observation_values.array.size() > max_observations)
    fail("count_limit_exceeded", "$.observations exceeds 4096 items");
  std::vector<luca::CashObservation> observations;
  observations.reserve(observation_values.array.size());
  for (std::size_t index = 0; index < observation_values.array.size(); ++index) {
    const auto path = "$.observations[" + std::to_string(index) + "]";
    const auto &observation_value = observation_values.array[index];
    require_closed_object(
        observation_value, path,
        {"account", "currency", "amount", "as_of", "settlement_as_of_date", "provenance"});
    const auto account = token(member(observation_value, "account"), path + ".account");
    const auto currency = parse_currency(member(observation_value, "currency"), path + ".currency");
    const auto amount = parse_money(text(member(observation_value, "amount"), path + ".amount"),
                                    currency, path + ".amount");
    const auto as_of =
        parse_timestamp(text(member(observation_value, "as_of"), path + ".as_of"), path + ".as_of");
    const auto settlement = parse_date(
        text(member(observation_value, "settlement_as_of_date"), path + ".settlement_as_of_date"),
        path + ".settlement_as_of_date");

    const auto &provenance_value = member(observation_value, "provenance");
    const auto provenance_path = path + ".provenance";
    require_closed_object(provenance_value, provenance_path,
                          {"source_record_ids", "transformation_name", "transformation_version",
                           "transformation_metadata"});
    auto source_texts = parse_tokens(member(provenance_value, "source_record_ids"),
                                     provenance_path + ".source_record_ids");
    std::ranges::sort(source_texts);
    if (std::ranges::adjacent_find(source_texts) != source_texts.end())
      fail("invalid_provenance", "observation provenance source identities must be unique");
    std::vector<luca::SourceRecordId> sources;
    sources.reserve(source_texts.size());
    for (auto &source_id : source_texts)
      sources.emplace_back(std::move(source_id));
    const auto transformation_name = token(member(provenance_value, "transformation_name"),
                                           provenance_path + ".transformation_name");
    const auto transformation_version = token(member(provenance_value, "transformation_version"),
                                              provenance_path + ".transformation_version");
    std::optional<std::string> metadata;
    const auto &metadata_value = member(provenance_value, "transformation_metadata");
    if (metadata_value.kind != JsonKind::null_value) {
      metadata = text(metadata_value, provenance_path + ".transformation_metadata");
      if (metadata->size() > luca::Provenance::max_metadata_size)
        fail("invalid_provenance", "observation provenance metadata exceeds 1024 bytes");
    }
    const auto provenance = luca::Provenance::create(std::move(sources), transformation_name,
                                                     transformation_version, std::move(metadata));
    if (!provenance)
      fail("invalid_provenance", "observation provenance is invalid");
    const auto observation = luca::CashObservation::create(luca::AccountId{account}, amount, as_of,
                                                           settlement.value(), *provenance);
    if (!observation)
      fail("invalid_observation", "cash observation is invalid");
    observations.push_back(*observation);
  }

  const auto comparison_policy = luca::ExactCashComparisonPolicy::create(
      comparison_declaration.policy.id, comparison_declaration.policy.version);
  if (!comparison_policy)
    fail_comparison(comparison_policy.error());
  const auto comparison_contract = luca::ExactCashComparisonContract::create(
      comparison_declaration.version, *comparison_policy, context.value);
  if (!comparison_contract)
    fail_comparison(comparison_contract.error());
  const auto comparison = luca::compare_exact_cash(*comparison_contract, projections, observations);
  if (!comparison)
    fail_comparison(comparison.error());

  std::size_t exact_count = 0;
  std::map<luca::CashKey, const luca::CashObservation *> observed_by_key;
  for (const auto &observation : observations)
    observed_by_key.emplace(observation.key(), &observation);
  for (const auto &projection : projections) {
    const auto found = observed_by_key.find(projection.key());
    if (found != observed_by_key.end() && found->second->amount() == projection.amount())
      ++exact_count;
  }
  std::size_t missing_count = 0;
  std::size_t unexpected_count = 0;
  std::size_t mismatch_count = 0;
  for (const auto &cash_break : comparison->breaks()) {
    switch (cash_break.kind()) {
    case luca::ExactCashBreakKind::missing_observation:
      ++missing_count;
      break;
    case luca::ExactCashBreakKind::unexpected_observation:
      ++unexpected_count;
      break;
    case luca::ExactCashBreakKind::amount_mismatch:
      ++mismatch_count;
      break;
    }
  }

  std::string output;
  output.reserve(4096U + projections.size() * 256U + comparison->breaks().size() * 512U);
  output.push_back('{');
  append_member(output, "schema_version");
  append_json_string(output, schema_version);
  output.push_back(',');
  append_member(output, "engine");
  output.push_back('{');
  append_member(output, "id");
  append_json_string(output, engine.id);
  output.push_back(',');
  append_member(output, "version");
  append_json_string(output, engine.version);
  output.push_back('}');
  output.push_back(',');
  append_member(output, "evaluation_context");
  output.push_back('{');
  append_member(output, "id");
  append_json_string(output, context.value.id());
  output.push_back(',');
  append_member(output, "recorded_through");
  append_json_string(output, format_timestamp(context.value.recorded_through()));
  output.push_back(',');
  append_member(output, "economic_as_of");
  append_json_string(output, format_timestamp(context.value.economic_as_of()));
  output.push_back(',');
  append_member(output, "settlement_as_of_date");
  append_json_string(output, format_date(context.value.settlement_as_of_date().value()));
  output.push_back('}');
  output.push_back(',');
  append_member(output, "operation_trace");
  output.push_back('[');
  append_trace(output, reduction_declaration, engine, context);
  output.push_back(',');
  append_trace(output, comparison_declaration, engine, context);
  output.push_back(']');
  output.push_back(',');
  append_member(output, "summary");
  output += "{\"exact\":" + std::to_string(exact_count) +
            ",\"missing_observation\":" + std::to_string(missing_count) +
            ",\"unexpected_observation\":" + std::to_string(unexpected_count) +
            ",\"amount_mismatch\":" + std::to_string(mismatch_count) + "}";
  output.push_back(',');
  append_member(output, "projections");
  output.push_back('[');
  for (std::size_t index = 0; index < projections.size(); ++index) {
    if (index != 0U)
      output.push_back(',');
    append_projection(output, projections[index]);
  }
  output.push_back(']');
  output.push_back(',');
  append_member(output, "matches");
  output.push_back('[');
  std::size_t match_index = 0;
  for (const auto &projection : projections) {
    const auto found = observed_by_key.find(projection.key());
    if (found == observed_by_key.end() || found->second->amount() != projection.amount())
      continue;
    if (match_index++ != 0U)
      output.push_back(',');
    output.push_back('{');
    append_member(output, "account");
    append_json_string(output, projection.key().account().value());
    output.push_back(',');
    append_member(output, "currency");
    append_json_string(output, projection.key().currency().code());
    output.push_back(',');
    append_member(output, "kind");
    append_json_string(output, "exact");
    output.push_back(',');
    append_member(output, "projection_evidence");
    append_projection(output, projection);
    output.push_back(',');
    append_member(output, "observation_evidence");
    append_observation(output, *found->second);
    output.push_back('}');
  }
  output.push_back(']');
  output.push_back(',');
  append_member(output, "breaks");
  output.push_back('[');
  for (std::size_t index = 0; index < comparison->breaks().size(); ++index) {
    if (index != 0U)
      output.push_back(',');
    const auto &cash_break = comparison->breaks()[index];
    output.push_back('{');
    append_member(output, "account");
    append_json_string(output, cash_break.key().account().value());
    output.push_back(',');
    append_member(output, "currency");
    append_json_string(output, cash_break.key().currency().code());
    output.push_back(',');
    append_member(output, "kind");
    append_json_string(output, luca::category_name(cash_break.kind()));
    output.push_back(',');
    append_member(output, "expected_amount");
    append_optional_money(output, cash_break.expected());
    output.push_back(',');
    append_member(output, "observed_amount");
    append_optional_money(output, cash_break.observed());
    output.push_back(',');
    append_member(output, "difference");
    append_optional_money(output, cash_break.difference());
    output.push_back(',');
    append_member(output, "projection_evidence");
    if (cash_break.projection())
      append_projection(output, *cash_break.projection());
    else
      output += "null";
    output.push_back(',');
    append_member(output, "observation_evidence");
    if (cash_break.observation())
      append_observation(output, *cash_break.observation());
    else
      output += "null";
    output.push_back('}');
  }
  output.push_back(']');
  output += "}\n";
  return output;
}

[[nodiscard]] int run(int argument_count, char **arguments) {
  std::optional<std::string> input_path;
  if (argument_count == 3 && std::string_view{arguments[1]} == "--input") {
    input_path = arguments[2];
    if (input_path->empty())
      fail("usage", "--input requires a non-empty file name");
  } else if (argument_count != 1) {
    fail("usage", "usage: luca-exact-cash [--input FILE]");
  }

  std::string input;
  if (input_path) {
    std::ifstream stream{*input_path, std::ios::binary};
    if (!stream)
      fail("input_error", "could not open the explicitly named input file");
    input = read_input(stream);
  } else {
    input = read_input(std::cin);
  }
  const auto document = JsonParser{input}.parse();
  std::cout << execute(document);
  if (!std::cout)
    fail("output_error", "could not write the result");
  return 0;
}

} // namespace

int main(int argument_count, char **arguments) {
  try {
    return run(argument_count, arguments);
  } catch (const Failure &failure) {
    std::cerr << "luca-exact-cash: " << failure.category() << ": " << failure.what() << '\n';
    return 1;
  } catch (const std::exception &) {
    std::cerr << "luca-exact-cash: internal_error: unexpected failure\n";
    return 1;
  }
}
