#include "luca/serialization/canonical.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using namespace std::chrono_literals;
using luca::AccountId;
using luca::CashMovement;
using luca::Currency;
using luca::EconomicEvent;
using luca::EconomicEventId;
using luca::EquityTrade;
using luca::EventHeader;
using luca::EventId;
using luca::InstrumentId;
using luca::LifecycleLedger;
using luca::LifecycleRecord;
using luca::LifecycleRecordDraft;
using luca::Money;
using luca::Price;
using luca::Provenance;
using luca::Quantity;
using luca::SettlementDate;
using luca::SourceRecordId;
using luca::Timestamp;
using luca::serialization::canonical_bytes;
using luca::serialization::canonical_digest;
using luca::serialization::CanonicalBytes;

void check(bool condition) {
  if (!condition)
    std::abort();
}

template <class Operation> void check_invalid_argument(Operation &&operation) {
  try {
    std::forward<Operation>(operation)();
  } catch (const std::invalid_argument &) {
    return;
  }
  check(false);
}

Currency usd() {
  const auto value = Currency::from_code("USD");
  check(value.has_value());
  return *value;
}

Timestamp timestamp(std::chrono::year_month_day date, std::chrono::hours hour) {
  return Timestamp{std::chrono::sys_days{date} + hour};
}

SettlementDate settlement_date(std::chrono::year_month_day date) {
  const auto value = SettlementDate::create(date);
  check(value.has_value());
  return *value;
}

Provenance provenance(std::string_view record_id,
                      std::optional<std::string> metadata = std::nullopt,
                      bool include_allocation = false) {
  std::vector<SourceRecordId> sources;
  sources.emplace_back("src-" + std::string{record_id});
  if (include_allocation)
    sources.emplace_back("src-" + std::string{record_id} + "-allocation");
  const auto value = Provenance::create(std::move(sources), "normalize", "1", std::move(metadata));
  check(value.has_value());
  return *value;
}

CashMovement cash(std::string_view record_id, std::int64_t amount, Timestamp effective_at,
                  const Provenance &source) {
  const auto header =
      EventHeader::create(EventId{std::string{record_id}}, AccountId{"acct"}, effective_at, source);
  check(header.has_value());
  return CashMovement::create(*header, Money::from_scaled(amount, usd()));
}

EquityTrade trade(std::string_view record_id, std::int64_t quantity, std::int64_t price,
                  Timestamp effective_at, const Provenance &source) {
  const auto header =
      EventHeader::create(EventId{std::string{record_id}}, AccountId{"acct"}, effective_at, source);
  check(header.has_value());
  const auto value = EquityTrade::create(
      *header, InstrumentId{"XYZ"}, Quantity::from_scaled(quantity), Price::from_scaled(price),
      usd(), settlement_date(std::chrono::year{2026} / std::chrono::March / 20));
  check(value.has_value());
  return *value;
}

void accept(LifecycleLedger &ledger, const LifecycleRecordDraft &draft) {
  check(ledger.accept(draft).has_value());
}

LifecycleLedger lifecycle_vectors() {
  using std::chrono::March;
  using std::chrono::year;

  LifecycleLedger ledger;
  const auto recorded = [](unsigned sequence) {
    return timestamp(year{2026} / March / 10, std::chrono::hours{sequence});
  };

  auto source = provenance("cash-correct-origin", "meta", true);
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"cash-correct"}, recorded(1),
                                         cash("cash-correct-origin", 1'000'000,
                                              timestamp(year{2026} / March / 1, 9h), source)));
  source = provenance("cash-correct-v2");
  accept(ledger,
         LifecycleRecordDraft::correct(
             EconomicEventId{"cash-correct"}, EventId{"cash-correct-origin"}, recorded(2),
             cash("cash-correct-v2", 1'200'000, timestamp(year{2026} / March / 1, 9h), source)));

  source = provenance("trade-correct-origin");
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"trade-correct"}, recorded(3),
                                         trade("trade-correct-origin", 200'000'000, 700'000'000,
                                               timestamp(year{2026} / March / 1, 10h), source)));
  source = provenance("trade-correct-v2");
  accept(ledger, LifecycleRecordDraft::correct(
                     EconomicEventId{"trade-correct"}, EventId{"trade-correct-origin"}, recorded(4),
                     trade("trade-correct-v2", 300'000'000, 750'000'000,
                           timestamp(year{2026} / March / 1, 10h), source)));

  source = provenance("cash-cancel-origin");
  accept(ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"cash-cancel"}, recorded(5),
             cash("cash-cancel-origin", 2'500'000, timestamp(year{2026} / March / 2, 9h), source)));
  accept(ledger,
         LifecycleRecordDraft::cancel(EventId{"cash-cancel-record"}, EconomicEventId{"cash-cancel"},
                                      EventId{"cash-cancel-origin"}, AccountId{"acct"}, recorded(6),
                                      provenance("cash-cancel-record")));

  source = provenance("trade-cancel-origin");
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"trade-cancel"}, recorded(7),
                                         trade("trade-cancel-origin", -400'000'000, 800'000'000,
                                               timestamp(year{2026} / March / 2, 10h), source)));
  accept(ledger, LifecycleRecordDraft::cancel(EventId{"trade-cancel-record"},
                                              EconomicEventId{"trade-cancel"},
                                              EventId{"trade-cancel-origin"}, AccountId{"acct"},
                                              recorded(8), provenance("trade-cancel-record")));

  source = provenance("cash-reverse-origin");
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"cash-reverse"}, recorded(9),
                                         cash("cash-reverse-origin", 5'000'000,
                                              timestamp(year{2026} / March / 3, 9h), source)));
  source = provenance("cash-reverse-record");
  accept(ledger, LifecycleRecordDraft::reverse(
                     EconomicEventId{"cash-reversal"}, EventId{"cash-reverse-origin"}, recorded(10),
                     cash("cash-reverse-record", -5'000'000, timestamp(year{2026} / March / 4, 9h),
                          source)));

  source = provenance("trade-reverse-origin");
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"trade-reverse"}, recorded(11),
                                         trade("trade-reverse-origin", 600'000'000, 900'000'000,
                                               timestamp(year{2026} / March / 3, 10h), source)));
  source = provenance("trade-reverse-record");
  accept(ledger,
         LifecycleRecordDraft::reverse(EconomicEventId{"trade-reversal"},
                                       EventId{"trade-reverse-origin"}, recorded(12),
                                       trade("trade-reverse-record", -600'000'000, 900'000'000,
                                             timestamp(year{2026} / March / 4, 10h), source)));
  return ledger;
}

LifecycleLedger integrated_valid_append_fixture(std::size_t record_count = 4) {
  using std::chrono::January;
  using std::chrono::year;

  LifecycleLedger ledger;
  auto source = Provenance::create(std::vector{SourceRecordId{"source-cash-origin"}},
                                   "normalize-cash-movement", "1");
  check(source.has_value());
  auto event =
      cash("record-cash-origin", 100'000'000'000, timestamp(year{2026} / January / 2, 9h), *source);
  // The fixture account is deliberately longer than the focused-vector account.
  auto header = EventHeader::create(EventId{"record-cash-origin"}, AccountId{"acct-main"},
                                    event.header().effective_at(), *source);
  check(header.has_value());
  event = CashMovement::create(*header, event.amount());
  accept(ledger, LifecycleRecordDraft::originate(EconomicEventId{"economic-cash-origin"},
                                                 timestamp(year{2026} / January / 2, 10h), event));
  if (record_count == 1)
    return ledger;

  source = Provenance::create(std::vector{SourceRecordId{"source-buy-origin"}},
                              "normalize-equity-trade", "1", "allocation=complete");
  check(source.has_value());
  header = EventHeader::create(EventId{"record-buy-origin"}, AccountId{"acct-main"},
                               timestamp(year{2026} / January / 3, 10h), *source);
  check(header.has_value());
  auto equity = EquityTrade::create(
      *header, InstrumentId{"instrument-xyz"}, Quantity::from_scaled(8'000'000'000),
      Price::from_scaled(5'500'000'000), usd(), settlement_date(year{2026} / January / 8));
  check(equity.has_value());
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"economic-buy-origin"},
                                         timestamp(year{2026} / January / 3, 11h), *equity));
  if (record_count == 2)
    return ledger;

  source = Provenance::create(std::vector{SourceRecordId{"source-cash-append"}},
                              "normalize-cash-movement", "1");
  check(source.has_value());
  header = EventHeader::create(EventId{"record-cash-append"}, AccountId{"acct-main"},
                               timestamp(year{2026} / January / 4, 9h), *source);
  check(header.has_value());
  accept(ledger,
         LifecycleRecordDraft::originate(
             EconomicEventId{"economic-cash-append"}, timestamp(year{2026} / January / 4, 11h),
             CashMovement::create(*header, Money::from_scaled(2'000'000'000, usd()))));
  if (record_count == 3)
    return ledger;

  source = Provenance::create(std::vector{SourceRecordId{"source-sell-append"}},
                              "normalize-equity-trade", "1");
  check(source.has_value());
  header = EventHeader::create(EventId{"record-sell-append"}, AccountId{"acct-main"},
                               timestamp(year{2026} / January / 5, 10h), *source);
  check(header.has_value());
  equity = EquityTrade::create(
      *header, InstrumentId{"instrument-xyz"}, Quantity::from_scaled(-2'000'000'000),
      Price::from_scaled(6'000'000'000), usd(), settlement_date(year{2026} / January / 9));
  check(equity.has_value());
  accept(ledger,
         LifecycleRecordDraft::originate(EconomicEventId{"economic-sell-append"},
                                         timestamp(year{2026} / January / 5, 11h), *equity));
  return ledger;
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

bool contains(std::span<const std::byte> bytes, std::string_view text) {
  CanonicalBytes needle;
  needle.reserve(text.size());
  for (const auto character : text)
    needle.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  return std::search(bytes.begin(), bytes.end(), needle.begin(), needle.end()) != bytes.end();
}

template <class Value>
concept CanonicallySerializable = requires(const Value &value) {
  { canonical_bytes(value) } -> std::same_as<CanonicalBytes>;
  { canonical_digest(value) } -> std::same_as<std::string>;
};

static_assert(CanonicallySerializable<Provenance>);
static_assert(CanonicallySerializable<EventHeader>);
static_assert(CanonicallySerializable<CashMovement>);
static_assert(CanonicallySerializable<EquityTrade>);
static_assert(CanonicallySerializable<EconomicEvent>);
static_assert(CanonicallySerializable<LifecycleRecord>);
static_assert(CanonicallySerializable<LifecycleLedger>);

void test_integrated_header_and_event_vectors(const LifecycleLedger &ledger) {
  const auto &cash_record = ledger.records()[0];
  const auto &trade_record = ledger.records()[2];
  const auto &cash_event = std::get<CashMovement>(*cash_record.event());
  const auto &trade_event = std::get<EquityTrade>(*trade_record.event());

  constexpr std::string_view header_hex =
      "4c4342310600000005000000076163636f756e740400000004616363740000000c65666665637469"
      "76655f6174040000001e323032362d30332d30315430393a30303a30302e3030303030303030305a"
      "0000000a70726f76656e616e636506000000050000000e736368656d615f76657273696f6e040000"
      "00126c7563612e70726f76656e616e63652e763100000011736f757263655f7265636f72645f6964"
      "7305000000000000000204000000177372632d636173682d636f72726563742d6f726967696e0400"
      "0000227372632d636173682d636f72726563742d6f726967696e2d616c6c6f636174696f6e000000"
      "177472616e73666f726d6174696f6e5f6d6574616461746104000000046d65746100000013747261"
      "6e73666f726d6174696f6e5f6e616d6504000000096e6f726d616c697a65000000167472616e7366"
      "6f726d6174696f6e5f76657273696f6e040000000131000000097265636f72645f69640400000013"
      "636173682d636f72726563742d6f726967696e0000000e736368656d615f76657273696f6e040000"
      "00146c7563612e6576656e742d6865616465722e7631";
  check(hex(canonical_bytes(cash_event.header())) == header_hex);
  check(canonical_digest(cash_event.header()) ==
        "7bc237154f784817cfbbd857d231a59955ca6da9937f25c07d7fe7d91babcfb3");

  check(canonical_digest(cash_event) ==
        "b9059e5eff0af7c9ede1a25f6c77e90de791fabb61e74330dab6d024a2b4278c");
  check(canonical_digest(EconomicEvent{cash_event}) == canonical_digest(cash_event));
  check(canonical_digest(trade_event) ==
        "a27efd1f9b9d4b682cb897b6d93652eb232e5b070939ab4558d45981c959e15b");
  check(canonical_digest(EconomicEvent{trade_event}) == canonical_digest(trade_event));
}

void test_action_vectors_and_null_event(const LifecycleLedger &ledger) {
  struct Vector {
    std::size_t index;
    std::size_t byte_count;
    std::string_view digest;
  };
  constexpr std::array vectors{
      Vector{0, 1167, "07f71cb4058342a86e2d406223bdcc672da674275f2a28d8537fa455ff325d48"},
      Vector{2, 1241, "4048a36f309484e7a1b1c3c1e35790658999c28525a0d21b667912595413208a"},
      Vector{1, 1078, "0bae00009314aafab56165050c6a4f1c576222eb81105a53d92e2c0d802061a8"},
      Vector{3, 1247, "292bbc50de23fcd1194a00b6f4d294fade953cab675f948d8288ce685f95c939"},
      Vector{5, 516, "1374e51609bfbed96d508099015be44b1ceac0c0e662cc9ee2107f63f23acc47"},
      Vector{7, 520, "c4ae25a74587f1ff1da3dcf7d8cc3c4ad0db77c665aa25ffbcb8affb1e137d4c"},
      Vector{9, 1097, "fdeb51c59828dcbf78d08a479cabc934780f620843d4c33e7b5128710fc77440"},
      Vector{11, 1266, "73bce25f6d745cdad578ce79c4f7cb9d11a3a04f268e4dda133139a6828c92ac"},
  };

  for (const auto &vector : vectors) {
    const auto bytes = canonical_bytes(ledger.records()[vector.index]);
    check(bytes.size() == vector.byte_count);
    check(canonical_digest(ledger.records()[vector.index]) == vector.digest);
    check(canonical_bytes(ledger.records()[vector.index]) == bytes);
    check(canonical_digest(ledger.records()[vector.index]) == vector.digest);
  }

  const auto cash_cancel = canonical_bytes(ledger.records()[5]);
  const auto equity_cancel = canonical_bytes(ledger.records()[7]);
  check(!contains(cash_cancel, "luca.economic-event.v1"));
  check(!contains(equity_cancel, "luca.economic-event.v1"));
}

void test_complete_sequence_vector(const LifecycleLedger &ledger) {
  const auto bytes = canonical_bytes(ledger);
  check(bytes.size() == 12'789);
  check(canonical_digest(ledger) ==
        "9a11d3844d1f27ce4135ffc2cce7f67e460775d7ab2c1388631056b8d7ccfb13");
  check(canonical_bytes(ledger) == bytes);
  check(canonical_digest(ledger) ==
        "9a11d3844d1f27ce4135ffc2cce7f67e460775d7ab2c1388631056b8d7ccfb13");

  CanonicalBytes concatenated;
  for (const auto &record : ledger.records()) {
    const auto record_bytes = canonical_bytes(record);
    concatenated.insert(concatenated.end(), record_bytes.begin(), record_bytes.end());
  }
  check(canonical_digest(ledger) != luca::serialization::detail::sha256_hex(concatenated));
  check(contains(bytes, "luca.lifecycle-record-sequence.v1"));
}

void test_unsigned_64_bit_sequence_primitives() {
  CanonicalBytes array;
  luca::serialization::detail::append_array(array, std::numeric_limits<std::uint64_t>::max());
  check(hex(array) == "05ffffffffffffffff");
  check(luca::serialization::detail::canonical_decimal(std::numeric_limits<std::uint64_t>::max()) ==
        "18446744073709551615");
}

void test_timestamp_boundaries() {
  struct Boundary {
    Timestamp value;
    std::string_view text;
    std::string_view id;
  };
  constexpr std::array boundaries{
      Boundary{Timestamp::min(), "1677-09-21T00:12:43.145224192Z", "timestamp-minimum"},
      Boundary{Timestamp::max(), "2262-04-11T23:47:16.854775807Z", "timestamp-maximum"},
  };

  for (const auto &boundary : boundaries) {
    check(luca::serialization::detail::canonical_timestamp(boundary.value) == boundary.text);

    const auto source = provenance(boundary.id);
    const auto event = cash(boundary.id, 1, boundary.value, source);
    const auto event_bytes = canonical_bytes(event);
    check(contains(event_bytes, boundary.text));
    check(canonical_bytes(event) == event_bytes);

    LifecycleLedger ledger;
    accept(ledger, LifecycleRecordDraft::originate(EconomicEventId{std::string{boundary.id}},
                                                   boundary.value, event));
    const auto ledger_bytes = canonical_bytes(ledger);
    check(contains(ledger_bytes, boundary.text));
    check(canonical_bytes(ledger) == ledger_bytes);
  }
}

void test_integrated_portable_sequence_vectors() {
  const auto prefix = integrated_valid_append_fixture(2);
  check(canonical_bytes(prefix).size() == 2'511);
  check(canonical_digest(prefix) ==
        "9fe51890a95a2d82e46606e6339d3599e368d134d9f2054903b6fae62f934e84");

  const auto full = integrated_valid_append_fixture();
  check(canonical_bytes(full).size() == 4'895);
  check(canonical_digest(full) ==
        "f721b1451d65d2d315d70d210c49078d7a16a9df4bf5d6cd05a672d178547ad9");
}

void test_schema_invalid_text_and_empty_sequence_are_rejected() {
  std::string malformed_utf8{"normalize-"};
  malformed_utf8.push_back(static_cast<char>(0xc3));
  malformed_utf8.push_back('(');
  const auto malformed =
      Provenance::create(std::vector{SourceRecordId{"source"}}, malformed_utf8, "1");
  check(malformed.has_value());
  check_invalid_argument([&] { (void)canonical_bytes(*malformed); });

  const auto decomposed =
      Provenance::create(std::vector{SourceRecordId{"source"}}, "normalize", "1", "Cafe\xcc\x81");
  check(decomposed.has_value());
  check_invalid_argument([&] { (void)canonical_digest(*decomposed); });

  const auto nul_source = Provenance::create(
      std::vector{SourceRecordId{std::string{"source\0suffix", 13}}}, "normalize", "1");
  check(nul_source.has_value());
  check_invalid_argument([&] { (void)canonical_bytes(*nul_source); });

  const auto nul_metadata = Provenance::create(std::vector{SourceRecordId{"source"}}, "normalize",
                                               "1", std::string{"x\0y", 3});
  check(nul_metadata.has_value());
  check_invalid_argument([&] { (void)canonical_bytes(*nul_metadata); });

  const auto composed = Provenance::create(std::vector{SourceRecordId{"source"}}, "normalize", "1",
                                           "Caf\xc3\xa9 q\xcc\x87");
  check(composed.has_value());
  check(!canonical_bytes(*composed).empty());

  const LifecycleLedger empty;
  check_invalid_argument([&] { (void)canonical_bytes(empty); });
  check_invalid_argument([&] { (void)canonical_digest(empty); });
}

LifecycleLedger two_cash_records(bool reverse_order, std::int64_t second_amount = 2'000'000) {
  using std::chrono::March;
  using std::chrono::year;
  const auto effective = timestamp(year{2026} / March / 5, 9h);
  const auto recorded = timestamp(year{2026} / March / 10, 20h);
  const auto first_source = provenance("order-a");
  const auto second_source = provenance("order-b");
  const auto first = LifecycleRecordDraft::originate(
      EconomicEventId{"order-a"}, recorded, cash("order-a", 1'000'000, effective, first_source));
  const auto second =
      LifecycleRecordDraft::originate(EconomicEventId{"order-b"}, recorded,
                                      cash("order-b", second_amount, effective, second_source));

  LifecycleLedger ledger;
  if (reverse_order) {
    accept(ledger, second);
    accept(ledger, first);
  } else {
    accept(ledger, first);
    accept(ledger, second);
  }
  return ledger;
}

void test_owned_field_order_lineage_action_and_payload_mutations(const LifecycleLedger &ledger) {
  const auto ordered = two_cash_records(false);
  const auto reordered = two_cash_records(true);
  const auto changed_payload = two_cash_records(false, 2'000'001);
  check(canonical_bytes(ordered) != canonical_bytes(reordered));
  check(canonical_digest(ordered) != canonical_digest(reordered));
  check(canonical_bytes(ordered) != canonical_bytes(changed_payload));
  check(canonical_digest(ordered) != canonical_digest(changed_payload));

  auto reversed_sources = provenance("cash-correct-origin", "meta", true);
  std::vector<SourceRecordId> sources{SourceRecordId{"src-cash-correct-origin-allocation"},
                                      SourceRecordId{"src-cash-correct-origin"}};
  auto changed_source_order = Provenance::create(std::move(sources), "normalize", "1", "meta");
  check(changed_source_order.has_value());
  check(canonical_bytes(reversed_sources) != canonical_bytes(*changed_source_order));

  check(canonical_bytes(ledger.records()[0]) != canonical_bytes(ledger.records()[1]));
  check(canonical_bytes(ledger.records()[4]) != canonical_bytes(ledger.records()[5]));
  check(canonical_bytes(ledger.records()[8]) != canonical_bytes(ledger.records()[9]));

  const auto base_event = *ledger.records()[2].event();
  const auto base_digest = canonical_digest(base_event);
  const auto make_trade = [](std::string_view record_id, std::string_view account,
                             std::string_view instrument, std::int64_t quantity, std::int64_t price,
                             Currency currency, std::chrono::year_month_day date,
                             Timestamp effective, const Provenance &source) {
    const auto header = EventHeader::create(EventId{std::string{record_id}},
                                            AccountId{std::string{account}}, effective, source);
    check(header.has_value());
    const auto event = EquityTrade::create(
        *header, InstrumentId{std::string{instrument}}, Quantity::from_scaled(quantity),
        Price::from_scaled(price), currency, settlement_date(date));
    check(event.has_value());
    return *event;
  };
  const auto source = provenance("trade-correct-origin");
  const auto effective = timestamp(std::chrono::year{2026} / std::chrono::March / 1, 10h);
  const auto eur = Currency::from_code("EUR");
  check(eur.has_value());
  check(canonical_digest(make_trade("changed-id", "acct", "XYZ", 200'000'000, 700'000'000, usd(),
                                    std::chrono::year{2026} / std::chrono::March / 20, effective,
                                    source)) != base_digest);
  check(canonical_digest(make_trade(
            "trade-correct-origin", "changed-account", "XYZ", 200'000'000, 700'000'000, usd(),
            std::chrono::year{2026} / std::chrono::March / 20, effective, source)) != base_digest);
  check(canonical_digest(make_trade(
            "trade-correct-origin", "acct", "changed-instrument", 200'000'000, 700'000'000, usd(),
            std::chrono::year{2026} / std::chrono::March / 20, effective, source)) != base_digest);
  check(canonical_digest(make_trade("trade-correct-origin", "acct", "XYZ", 200'000'001, 700'000'000,
                                    usd(), std::chrono::year{2026} / std::chrono::March / 20,
                                    effective, source)) != base_digest);
  check(canonical_digest(make_trade("trade-correct-origin", "acct", "XYZ", 200'000'000, 700'000'001,
                                    usd(), std::chrono::year{2026} / std::chrono::March / 20,
                                    effective, source)) != base_digest);
  check(canonical_digest(make_trade("trade-correct-origin", "acct", "XYZ", 200'000'000, 700'000'000,
                                    *eur, std::chrono::year{2026} / std::chrono::March / 20,
                                    effective, source)) != base_digest);
  check(canonical_digest(make_trade("trade-correct-origin", "acct", "XYZ", 200'000'000, 700'000'000,
                                    usd(), std::chrono::year{2026} / std::chrono::March / 21,
                                    effective, source)) != base_digest);
  check(canonical_digest(make_trade("trade-correct-origin", "acct", "XYZ", 200'000'000, 700'000'000,
                                    usd(), std::chrono::year{2026} / std::chrono::March / 20,
                                    effective + 1ns, source)) != base_digest);

  LifecycleLedger identity_a;
  LifecycleLedger identity_b;
  accept(identity_a,
         LifecycleRecordDraft::originate(
             EconomicEventId{"identity-a"},
             timestamp(std::chrono::year{2026} / std::chrono::March / 10, 23h), base_event));
  accept(identity_b,
         LifecycleRecordDraft::originate(
             EconomicEventId{"identity-b"},
             timestamp(std::chrono::year{2026} / std::chrono::March / 10, 23h), base_event));
  check(canonical_digest(identity_a) != canonical_digest(identity_b));
}

} // namespace

int main() {
  const auto ledger = lifecycle_vectors();
  check(ledger.records().size() == 12);
  for (std::size_t index = 0; index < ledger.records().size(); ++index)
    check(ledger.records()[index].acceptance_sequence().value() == index + 1);
  test_integrated_header_and_event_vectors(ledger);
  test_action_vectors_and_null_event(ledger);
  test_complete_sequence_vector(ledger);
  test_unsigned_64_bit_sequence_primitives();
  test_timestamp_boundaries();
  test_integrated_portable_sequence_vectors();
  test_schema_invalid_text_and_empty_sequence_are_rejected();
  test_owned_field_order_lineage_action_and_payload_mutations(ledger);
}
