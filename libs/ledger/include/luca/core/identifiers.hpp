#pragma once

#include <compare>
#include <string>
#include <utility>

namespace luca {

template <class Tag> class Identifier {
 public:
  explicit Identifier(std::string value) : value_(std::move(value)) {}
  [[nodiscard]] const std::string& value() const noexcept { return value_; }
  auto operator<=>(const Identifier&) const = default;
 private:
  std::string value_;
};

struct AccountIdTag;
struct InstrumentIdTag;
struct EventIdTag;
struct SourceIdTag;
using AccountId = Identifier<AccountIdTag>;
using InstrumentId = Identifier<InstrumentIdTag>;
using EventId = Identifier<EventIdTag>;
using SourceId = Identifier<SourceIdTag>;

}  // namespace luca
