#include "luca/portfolio.hpp"

#include <algorithm>
#include <chrono>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using luca::AccountId;
using luca::CashBalance;
using luca::Currency;
using luca::InstrumentId;
using luca::Money;
using luca::PortfolioState;
using luca::Position;
using luca::PositionKey;
using luca::Quantity;
using luca::SettlementDate;
using luca::SettlementDirection;
using luca::SettlementObligation;
using luca::serialization::canonical_bytes;
using luca::serialization::canonical_digest;
using luca::serialization::CanonicalBytes;

void check(bool condition) {
  if (!condition)
    std::abort();
}

template <class Operation> void check_rejected(Operation &&operation) {
  try {
    std::forward<Operation>(operation)();
  } catch (const std::invalid_argument &) {
    return;
  } catch (const std::out_of_range &) {
    return;
  } catch (const std::length_error &) {
    return;
  }
  check(false);
}

Currency currency(std::string_view code) {
  const auto value = Currency::from_code(code);
  check(value.has_value());
  return *value;
}

SettlementDate date(int year, unsigned month, unsigned day) {
  const auto value = SettlementDate::create(std::chrono::year{year} / std::chrono::month{month} /
                                            std::chrono::day{day});
  check(value.has_value());
  return *value;
}

Position position(std::string account, std::string instrument, std::int64_t quantity) {
  return Position{PositionKey{AccountId{std::move(account)}, InstrumentId{std::move(instrument)}},
                  Quantity::from_scaled(quantity)};
}

CashBalance cash(std::string account, std::string_view currency_code, std::int64_t amount) {
  return CashBalance{AccountId{std::move(account)},
                     Money::from_scaled(amount, currency(currency_code))};
}

SettlementObligation obligation(std::string account, SettlementDate settlement_date,
                                std::string_view currency_code, SettlementDirection direction,
                                std::int64_t amount) {
  return SettlementObligation{AccountId{std::move(account)}, settlement_date, direction,
                              Money::from_scaled(amount, currency(currency_code))};
}

std::string hex(std::span<const std::byte> bytes) {
  constexpr std::string_view digits = "0123456789abcdef";
  std::string result;
  result.reserve(bytes.size() * 2);
  for (const auto byte : bytes) {
    const auto value = std::to_integer<std::uint8_t>(byte);
    result.push_back(digits[value >> 4]);
    result.push_back(digits[value & 0x0f]);
  }
  return result;
}

std::size_t find_text(std::span<const std::byte> bytes, std::string_view text) {
  std::vector<std::byte> needle;
  needle.reserve(text.size());
  for (const char character : text)
    needle.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  const auto found = std::search(bytes.begin(), bytes.end(), needle.begin(), needle.end());
  return static_cast<std::size_t>(found - bytes.begin());
}

bool contains_text(std::span<const std::byte> bytes, std::string_view text) {
  return find_text(bytes, text) != bytes.size();
}

template <class Value>
concept CanonicallySerializable = requires(const Value &value) {
  { canonical_bytes(value) } -> std::same_as<CanonicalBytes>;
  { canonical_digest(value) } -> std::same_as<std::string>;
};

static_assert(CanonicallySerializable<PortfolioState>);

PortfolioState checkpoint_state() {
  return PortfolioState{{position("acct-main", "instrument-xyz", 8'000'000'000)},
                        {cash("acct-main", "USD", 100'000'000'000)},
                        {obligation("acct-main", date(2026, 1, 8), "USD",
                                    SettlementDirection::payable, 4'400'000'000)}};
}

void test_integrated_checkpoint_state_vector_twice() {
  constexpr std::string_view expected_hex =
      "4c43423106000000040000001b6f70656e5f736574746c656d656e745f6f626c69676174696f6e73050000000000"
      "0000"
      "010600000005000000076163636f756e740400000009616363742d6d61696e00000006616d6f756e740600000004"
      "0000"
      "000863757272656e63790400000003555344000000057363616c650400000001360000000c7363616c65645f7661"
      "6c75"
      "65040000000a343430303030303030300000000e736368656d615f76657273696f6e040000000d6c7563612e6d6f"
      "6e65"
      "792e763100000009646972656374696f6e040000000770617961626c650000000e736368656d615f76657273696f"
      "6e04"
      "0000001d6c7563612e736574746c656d656e742d6f626c69676174696f6e2e76310000000f736574746c656d656e"
      "745f"
      "64617465040000000a323032362d30312d303800000009706f736974696f6e730500000000000000010600000004"
      "0000"
      "00076163636f756e740400000009616363742d6d61696e0000000a696e737472756d656e74040000000e696e7374"
      "7275"
      "6d656e742d78797a000000087175616e746974790600000003000000057363616c650400000001380000000c7363"
      "616c"
      "65645f76616c7565040000000a383030303030303030300000000e736368656d615f76657273696f6e0400000010"
      "6c75"
      "63612e7175616e746974792e76310000000e736368656d615f76657273696f6e04000000186c7563612e706f7369"
      "7469"
      "6f6e2d62616c616e63652e76310000000e736368656d615f76657273696f6e04000000176c7563612e706f727466"
      "6f6c"
      "696f2d73746174652e76310000000c736574746c65645f6361736805000000000000000106000000030000000761"
      "6363"
      "6f756e740400000009616363742d6d61696e00000006616d6f756e7406000000040000000863757272656e637904"
      "0000"
      "0003555344000000057363616c650400000001360000000c7363616c65645f76616c7565040000000c3130303030"
      "3030"
      "30303030300000000e736368656d615f76657273696f6e040000000d6c7563612e6d6f6e65792e76310000000e73"
      "6368"
      "656d615f76657273696f6e04000000146c7563612e636173682d62616c616e63652e7631";
  constexpr std::string_view expected_digest =
      "72c3555ab26a7a4ec42f1024c0404e6b0094510908783e9e1069141f6a88a738";

  const auto state = checkpoint_state();
  check(hex(canonical_bytes(state)) == expected_hex);
  check(canonical_digest(state) == expected_digest);
  check(hex(canonical_bytes(state)) == expected_hex);
  check(canonical_digest(state) == expected_digest);
}

void test_collection_canonicalization_and_direction_order() {
  const auto january_8 = date(2026, 1, 8);
  const auto january_9 = date(2026, 1, 9);
  const std::string unicode_account{"\xC3\xA9-account"};

  const PortfolioState shuffled{
      {position(unicode_account, "instrument-a", 3), position("acct-a", "instrument-z", -2),
       position("acct-a", "instrument-a", 1)},
      {cash(unicode_account, "USD", 4), cash("acct-a", "USD", -3), cash("acct-a", "EUR", 2)},
      {obligation("acct-a", january_9, "USD", SettlementDirection::payable, 7),
       obligation("acct-a", january_8, "USD", SettlementDirection::payable, 6),
       obligation(unicode_account, january_8, "USD", SettlementDirection::receivable, 5),
       obligation("acct-a", january_8, "USD", SettlementDirection::receivable, 4)}};
  const PortfolioState ordered{
      {position("acct-a", "instrument-a", 1), position("acct-a", "instrument-z", -2),
       position(unicode_account, "instrument-a", 3)},
      {cash("acct-a", "EUR", 2), cash("acct-a", "USD", -3), cash(unicode_account, "USD", 4)},
      {obligation("acct-a", january_8, "USD", SettlementDirection::receivable, 4),
       obligation("acct-a", january_8, "USD", SettlementDirection::payable, 6),
       obligation("acct-a", january_9, "USD", SettlementDirection::payable, 7),
       obligation(unicode_account, january_8, "USD", SettlementDirection::receivable, 5)}};

  check(canonical_bytes(shuffled) == canonical_bytes(ordered));
  check(canonical_digest(shuffled) == canonical_digest(ordered));

  const PortfolioState directions{
      {},
      {},
      {obligation("acct-a", january_8, "USD", SettlementDirection::payable, 6),
       obligation("acct-a", january_8, "USD", SettlementDirection::receivable, 4)}};
  const auto direction_bytes = canonical_bytes(directions);
  check(find_text(direction_bytes, "receivable") < find_text(direction_bytes, "payable"));

  const PortfolioState utf8_order{
      {position(unicode_account, "instrument-a", 1), position("z-account", "instrument-a", 2)},
      {},
      {}};
  const auto utf8_bytes = canonical_bytes(utf8_order);
  check(find_text(utf8_bytes, "z-account") < find_text(utf8_bytes, unicode_account));
}

void test_duplicate_and_sparse_state_rejection() {
  const auto january_8 = date(2026, 1, 8);
  check_rejected([] {
    (void)canonical_bytes(PortfolioState{
        {position("acct", "instrument", 1), position("acct", "instrument", 2)}, {}, {}});
  });
  check_rejected([] {
    (void)canonical_bytes(PortfolioState{{}, {cash("acct", "USD", 1), cash("acct", "USD", 2)}, {}});
  });
  check_rejected([&] {
    (void)canonical_bytes(
        PortfolioState{{},
                       {},
                       {obligation("acct", january_8, "USD", SettlementDirection::payable, 1),
                        obligation("acct", january_8, "USD", SettlementDirection::payable, 2)}});
  });

  check_rejected([] {
    (void)canonical_bytes(PortfolioState{{position("acct", "instrument", 0)}, {}, {}});
  });
  check_rejected([] { (void)canonical_bytes(PortfolioState{{}, {cash("acct", "USD", 0)}, {}}); });
  check_rejected([&] {
    (void)canonical_bytes(PortfolioState{
        {}, {}, {obligation("acct", january_8, "USD", SettlementDirection::payable, 0)}});
  });
  check_rejected([&] {
    (void)canonical_bytes(PortfolioState{
        {}, {}, {obligation("acct", january_8, "USD", SettlementDirection::payable, -1)}});
  });
}

void test_identifier_date_and_direction_validation() {
  check_rejected([] {
    (void)canonical_bytes(PortfolioState{{position("", "instrument", 1)}, {}, {}});
  });
  check_rejected([] { (void)canonical_bytes(PortfolioState{{position("acct", "", 1)}, {}, {}}); });
  check_rejected([] {
    (void)canonical_bytes(
        PortfolioState{{position(std::string{"acct\0suffix", 11}, "instrument", 1)}, {}, {}});
  });
  check_rejected([] {
    (void)canonical_bytes(PortfolioState{
        {position(std::string{1, static_cast<char>(0xff)}, "instrument", 1)}, {}, {}});
  });
  check_rejected([] {
    (void)canonical_bytes(
        PortfolioState{{position(std::string{"e\xCC\x81"}, "instrument", 1)}, {}, {}});
  });

  check_rejected([] {
    (void)canonical_bytes(PortfolioState{
        {}, {}, {obligation("acct", date(0, 1, 1), "USD", SettlementDirection::payable, 1)}});
  });
  check_rejected([] {
    (void)canonical_bytes(PortfolioState{
        {},
        {},
        {obligation("acct", date(2026, 1, 1), "USD", static_cast<SettlementDirection>(99), 1)}});
  });
}

void test_owned_representation_mutations() {
  const auto january_8 = date(2026, 1, 8);
  const auto january_9 = date(2026, 1, 9);
  const PortfolioState base{
      {position("acct-a", "instrument-a", 10)},
      {cash("acct-a", "USD", 20)},
      {obligation("acct-a", january_8, "USD", SettlementDirection::payable, 30)}};
  const auto base_position = base.positions().front();
  const auto base_cash = base.settled_cash().front();
  const auto base_obligation = base.open_settlement_obligations().front();
  const auto base_digest = canonical_digest(base);
  const auto changed = [&](PortfolioState state) { check(canonical_digest(state) != base_digest); };

  changed({{position("acct-b", "instrument-a", 10)}, {base_cash}, {base_obligation}});
  changed({{position("acct-a", "instrument-b", 10)}, {base_cash}, {base_obligation}});
  changed({{position("acct-a", "instrument-a", 11)}, {base_cash}, {base_obligation}});
  changed({{base_position}, {cash("acct-b", "USD", 20)}, {base_obligation}});
  changed({{base_position}, {cash("acct-a", "EUR", 20)}, {base_obligation}});
  changed({{base_position}, {cash("acct-a", "USD", 21)}, {base_obligation}});
  changed({{base_position},
           {base_cash},
           {obligation("acct-b", january_8, "USD", SettlementDirection::payable, 30)}});
  changed({{base_position},
           {base_cash},
           {obligation("acct-a", january_8, "EUR", SettlementDirection::payable, 30)}});
  changed({{base_position},
           {base_cash},
           {obligation("acct-a", january_9, "USD", SettlementDirection::payable, 30)}});
  changed({{base_position},
           {base_cash},
           {obligation("acct-a", january_8, "USD", SettlementDirection::receivable, 30)}});
  changed({{base_position},
           {base_cash},
           {obligation("acct-a", january_8, "USD", SettlementDirection::payable, 31)}});
  changed({{}, {base_cash}, {base_obligation}});
  changed({{base_position}, {}, {base_obligation}});
  changed({{base_position}, {base_cash}, {}});

  const auto bytes = canonical_bytes(base);
  check(contains_text(bytes, "luca.position-balance.v1"));
  check(contains_text(bytes, "luca.cash-balance.v1"));
  check(contains_text(bytes, "luca.settlement-obligation.v1"));
  check(contains_text(bytes, "luca.portfolio-state.v1"));
}

} // namespace

int main() {
  test_integrated_checkpoint_state_vector_twice();
  test_collection_canonicalization_and_direction_order();
  test_duplicate_and_sparse_state_rejection();
  test_identifier_date_and_direction_validation();
  test_owned_representation_mutations();
}
