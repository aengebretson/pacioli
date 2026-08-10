#include "luca/core.hpp"

#include <cassert>
#include <compare>
#include <cstdint>
#include <limits>
#include <type_traits>

using namespace luca;

template <class T> T parsed(const char* text) {
  auto result = T::parse(text);
  assert(result);
  return *result;
}

int main() {
  static_assert(!std::is_convertible_v<InstrumentId, AccountId>);
  static_assert(sizeof(Quantity) == sizeof(std::int64_t));
  static_assert(sizeof(Price) == sizeof(std::int64_t));
  static_assert(sizeof(Rate) == sizeof(std::int64_t));
  assert(AccountId{"A"} == AccountId{"A"});
  assert(AccountId{"A"} < AccountId{"B"});
  assert(InstrumentId{"AAPL"}.value() == "AAPL");
  assert(EventId{"event-1"}.value() == "event-1");
  assert(SourceId{"feed"}.value() == "feed");

  auto usd_result = Currency::from_code("USD");
  auto eur_result = Currency::from_code("EUR");
  assert(usd_result && eur_result);
  const auto usd = *usd_result;
  const auto eur = *eur_result;
  assert(usd.code() == "USD" && eur < usd);
  assert(!Currency::from_code("usd"));
  assert(!Currency::from_code("US"));
  assert(!Currency::from_code("U1D"));
  assert(!Currency::from_code("USDX"));

  const auto exact = parsed<Quantity>("1234.56789012");
  assert(exact.scaled_value() == 123456789012LL);
  assert(parsed<Quantity>("-0.00000001").scaled_value() == -1);
  assert(!Quantity::parse("1.000000001"));
  assert(exact.add(parsed<Quantity>("0.00000001"))->scaled_value() == 123456789013LL);
  assert(exact.subtract(parsed<Quantity>("0.00000012"))->scaled_value() == 123456789000LL);
  assert(!Quantity::from_scaled(std::numeric_limits<std::int64_t>::max())
              .add(Quantity::from_scaled(1)));

  using F3 = detail::FixedPoint<3>;
  auto rounded = [](std::int64_t raw, RoundingMode mode) {
    return F3::from_scaled(raw).rescale<2>(mode)->scaled_value();
  };
  assert(rounded(125, RoundingMode::toward_zero) == 12);
  assert(rounded(-125, RoundingMode::toward_zero) == -12);
  assert(rounded(121, RoundingMode::floor) == 12);
  assert(rounded(-121, RoundingMode::floor) == -13);
  assert(rounded(121, RoundingMode::ceiling) == 13);
  assert(rounded(-121, RoundingMode::ceiling) == -12);
  assert(rounded(125, RoundingMode::half_up) == 13);
  assert(rounded(-125, RoundingMode::half_up) == -13);
  assert(rounded(124, RoundingMode::half_up) == 12);
  assert(rounded(126, RoundingMode::half_up) == 13);
  assert(rounded(125, RoundingMode::half_even) == 12);
  assert(rounded(135, RoundingMode::half_even) == 14);
  assert(rounded(-125, RoundingMode::half_even) == -12);
  assert(rounded(-135, RoundingMode::half_even) == -14);
  assert(F3::from_scaled(123).rescale<5>(RoundingMode::toward_zero)->scaled_value() == 12300);

  const auto quantity = parsed<Quantity>("1234.56789012");
  const auto price = parsed<Price>("187.12345678");
  const auto market_value = value(quantity, price, usd);
  assert(market_value && market_value->scaled_value() == 231016611229LL);
  assert(value(parsed<Quantity>("-2.5"), parsed<Price>("10.25"), usd)->scaled_value() == -25625000);
  assert(value(parsed<Quantity>("0.12345678"), parsed<Price>("9.87654321"), usd)->scaled_value() == 1219326);
  // The product exceeds int64 before scaling, proving use of a widened intermediate.
  assert(value(Quantity::from_scaled(900000000000000000LL),
               Price::from_scaled(100000000LL), usd)->scaled_value() == 9000000000000000LL);
  assert(!value(Quantity::from_scaled(std::numeric_limits<std::int64_t>::max()),
                Price::from_scaled(std::numeric_limits<std::int64_t>::max()), usd));

  auto cash = Money::parse("100.125", usd);
  auto fee = Money::parse("-0.125", usd);
  assert(cash && fee);
  assert(cash->add(*fee)->scaled_value() == 100000000);
  assert(cash->subtract(*fee)->scaled_value() == 100250000);
  assert(!cash->add(Money::from_scaled(1, eur)));
  assert((*cash <=> Money::from_scaled(1, eur)) == std::partial_ordering::unordered);
  assert(!Money::from_scaled(std::numeric_limits<std::int64_t>::max(), usd)
              .add(Money::from_scaled(1, usd)));

  assert(apply_rate(Money::from_scaled(100000000, usd), parsed<Rate>("0.0525"))
             ->scaled_value() == 5250000);
}
