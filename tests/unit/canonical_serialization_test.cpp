#include "luca/core.hpp"
#include "luca/serialization/canonical.hpp"

#include <algorithm>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {

using luca::Currency;
using luca::Money;
using luca::Price;
using luca::Quantity;
using luca::Rate;
using luca::serialization::canonical_bytes;
using luca::serialization::canonical_digest;
using luca::serialization::CanonicalBytes;

void check(bool condition) {
  if (!condition)
    std::abort();
}

Currency currency(std::string_view code) {
  const auto result = Currency::from_code(code);
  check(result.has_value());
  return *result;
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

CanonicalBytes bytes(std::string_view text) {
  CanonicalBytes result;
  result.reserve(text.size());
  for (const char character : text)
    result.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  return result;
}

bool contains(std::span<const std::byte> haystack, std::string_view needle) {
  const auto encoded = bytes(needle);
  return std::search(haystack.begin(), haystack.end(), encoded.begin(), encoded.end()) !=
         haystack.end();
}

template <class Value>
concept CanonicallySerializable = requires(const Value &value) {
  { canonical_bytes(value) } -> std::same_as<CanonicalBytes>;
  { canonical_digest(value) } -> std::same_as<std::string>;
};

static_assert(CanonicallySerializable<Money>);
static_assert(CanonicallySerializable<Quantity>);
static_assert(CanonicallySerializable<Price>);
static_assert(!CanonicallySerializable<Rate>);

void test_sha256_standard_vectors() {
  check(luca::serialization::detail::sha256_hex({}) ==
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");

  const auto abc = bytes("abc");
  check(luca::serialization::detail::sha256_hex(abc) ==
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");

  const auto multi_block = bytes("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq");
  check(luca::serialization::detail::sha256_hex(multi_block) ==
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");

  const CanonicalBytes million_a(1'000'000, std::byte{0x61});
  check(luca::serialization::detail::sha256_hex(million_a) ==
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}

void test_integrated_money_vector() {
  const auto usd = currency("USD");
  const auto value = Money::from_scaled(4'400'000'000LL, usd);
  constexpr std::string_view expected_hex =
      "4c43423106000000040000000863757272656e63790400000003555344000000057363616c650400"
      "000001360000000c7363616c65645f76616c7565040000000a343430303030303030300000000e73"
      "6368656d615f76657273696f6e040000000d6c7563612e6d6f6e65792e7631";
  constexpr std::string_view expected_digest =
      "a92590d43f88689fb3d67d2f34c0b71e98d00f5b46f86270610b54f185bcf1f8";

  check(hex(canonical_bytes(value)) == expected_hex);
  check(canonical_digest(value) == expected_digest);
  check(hex(canonical_bytes(value)) == expected_hex);
  check(canonical_digest(value) == expected_digest);
}

void test_exact_quantity_and_price_vectors() {
  const auto quantity = Quantity::from_scaled(1);
  constexpr std::string_view quantity_hex =
      "4c4342310600000003000000057363616c650400000001380000000c7363616c65645f76616c7565"
      "0400000001310000000e736368656d615f76657273696f6e04000000106c7563612e7175616e7469"
      "74792e7631";
  constexpr std::string_view quantity_digest =
      "db082f2f15056e20360d1c21bcad0f077b692f15b383a0d7a93b75f1e1a76b25";
  check(hex(canonical_bytes(quantity)) == quantity_hex);
  check(canonical_digest(quantity) == quantity_digest);

  const auto price = Price::from_scaled(-42);
  constexpr std::string_view price_hex =
      "4c4342310600000003000000057363616c650400000001380000000c7363616c65645f76616c7565"
      "04000000032d34320000000e736368656d615f76657273696f6e040000000d6c7563612e70726963"
      "652e7631";
  constexpr std::string_view price_digest =
      "d470df2d9a216b39be707e9b789151d7428d6ffeaed0ad26e89d7ca770d60e18";
  check(hex(canonical_bytes(price)) == price_hex);
  check(canonical_digest(price) == price_digest);
}

void test_canonical_decimal_spellings_and_extrema() {
  const auto usd = currency("USD");
  const auto zero = canonical_bytes(Money::from_scaled(0, usd));
  const auto signed_zero = canonical_bytes(Money::from_scaled(-0, usd));
  check(zero == signed_zero);
  check(contains(zero, "0"));
  check(!contains(zero, "-0"));

  const auto positive = canonical_bytes(Quantity::from_scaled(123'456'789));
  const auto negative = canonical_bytes(Price::from_scaled(-123'456'789));
  check(contains(positive, "123456789"));
  check(contains(negative, "-123456789"));

  const auto minimum =
      canonical_bytes(Money::from_scaled(std::numeric_limits<std::int64_t>::min(), usd));
  const auto maximum =
      canonical_bytes(Money::from_scaled(std::numeric_limits<std::int64_t>::max(), usd));
  check(contains(minimum, "-9223372036854775808"));
  check(contains(maximum, "9223372036854775807"));
  check(canonical_digest(Money::from_scaled(std::numeric_limits<std::int64_t>::min(), usd)) !=
        canonical_digest(Money::from_scaled(std::numeric_limits<std::int64_t>::max(), usd)));
}

void test_owned_fields_and_type_separation() {
  const auto usd = currency("USD");
  const auto eur = currency("EUR");
  const auto usd_money = Money::from_scaled(1, usd);
  const auto eur_money = Money::from_scaled(1, eur);
  check(canonical_bytes(usd_money) != canonical_bytes(eur_money));
  check(canonical_digest(usd_money) != canonical_digest(eur_money));

  const auto quantity = Quantity::from_scaled(1);
  const auto price = Price::from_scaled(1);
  check(canonical_bytes(quantity) != canonical_bytes(price));
  check(canonical_digest(quantity) != canonical_digest(price));
  check(contains(canonical_bytes(quantity), "luca.quantity.v1"));
  check(contains(canonical_bytes(price), "luca.price.v1"));
  check(contains(canonical_bytes(quantity), "8"));
  check(contains(canonical_bytes(usd_money), "6"));

  check(canonical_bytes(Quantity::from_scaled(1)) != canonical_bytes(Quantity::from_scaled(2)));
  check(canonical_digest(Price::from_scaled(1)) != canonical_digest(Price::from_scaled(2)));
}

void test_lcb1_header_and_repeatability() {
  const auto value = Price::from_scaled(-42);
  const auto expected_bytes = canonical_bytes(value);
  const auto expected_digest = canonical_digest(value);
  check(expected_bytes.size() >= 4);
  check(hex(std::span(expected_bytes).first<4>()) == "4c434231");
  for (int iteration = 0; iteration < 128; ++iteration) {
    check(canonical_bytes(value) == expected_bytes);
    check(canonical_digest(value) == expected_digest);
  }
}

} // namespace

int main() {
  test_sha256_standard_vectors();
  test_integrated_money_vector();
  test_exact_quantity_and_price_vectors();
  test_canonical_decimal_spellings_and_extrema();
  test_owned_fields_and_type_separation();
  test_lcb1_header_and_repeatability();
}
