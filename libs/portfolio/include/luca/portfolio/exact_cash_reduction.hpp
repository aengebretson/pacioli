#pragma once

#include "luca/portfolio/cash.hpp"
#include "luca/time.hpp"

#include <algorithm>
#include <expected>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca {

enum class ExactCashReductionError {
  invalid_identifier,
  incomplete_context,
  incomplete_lineage,
  duplicate_event_lineage,
  account_mismatch,
  currency_mismatch,
  operation_version_mismatch,
  policy_id_mismatch,
  policy_version_mismatch,
  context_mismatch,
  unit_mismatch,
  partition_key_mismatch,
  amount_overflow,
};

[[nodiscard]] constexpr std::string_view category_name(ExactCashReductionError error) noexcept {
  switch (error) {
  case ExactCashReductionError::invalid_identifier:
    return "invalid_identifier";
  case ExactCashReductionError::incomplete_context:
    return "incomplete_context";
  case ExactCashReductionError::incomplete_lineage:
    return "incomplete_lineage";
  case ExactCashReductionError::duplicate_event_lineage:
    return "duplicate_event_lineage";
  case ExactCashReductionError::account_mismatch:
    return "account_mismatch";
  case ExactCashReductionError::currency_mismatch:
    return "currency_mismatch";
  case ExactCashReductionError::operation_version_mismatch:
    return "operation_version_mismatch";
  case ExactCashReductionError::policy_id_mismatch:
    return "policy_id_mismatch";
  case ExactCashReductionError::policy_version_mismatch:
    return "policy_version_mismatch";
  case ExactCashReductionError::context_mismatch:
    return "context_mismatch";
  case ExactCashReductionError::unit_mismatch:
    return "unit_mismatch";
  case ExactCashReductionError::partition_key_mismatch:
    return "partition_key_mismatch";
  case ExactCashReductionError::amount_overflow:
    return "amount_overflow";
  }
  return "invalid_identifier";
}

enum class ExactCashReductionUnit {
  money,
  quantity,
};

enum class ExactCashPartitionKey {
  account,
  currency,
};

namespace exact_cash_reduction_detail {

[[nodiscard]] inline bool valid_identifier(std::string_view value) noexcept {
  if (value.empty())
    return false;
  return std::ranges::all_of(value, [](unsigned char byte) { return byte > 0x20 && byte != 0x7f; });
}

template <class Identifier>
[[nodiscard]] inline bool identifier_less(const Identifier &left,
                                          const Identifier &right) noexcept {
  return left.value() < right.value();
}

template <class Identifier> inline void canonicalize(std::vector<Identifier> &identifiers) {
  std::ranges::sort(identifiers, identifier_less<Identifier>);
}

template <class Identifier>
[[nodiscard]] inline bool
has_adjacent_duplicate(const std::vector<Identifier> &identifiers) noexcept {
  return std::ranges::adjacent_find(identifiers) != identifiers.end();
}

} // namespace exact_cash_reduction_detail

class ExactCashPartitioning {
public:
  [[nodiscard]] static std::expected<ExactCashPartitioning, ExactCashReductionError>
  create(std::vector<ExactCashPartitionKey> keys) {
    if (keys.empty())
      return std::unexpected(ExactCashReductionError::partition_key_mismatch);
    std::ranges::sort(keys);
    if (std::ranges::adjacent_find(keys) != keys.end())
      return std::unexpected(ExactCashReductionError::partition_key_mismatch);
    return ExactCashPartitioning{std::move(keys)};
  }

  [[nodiscard]] static ExactCashPartitioning account_currency() {
    return ExactCashPartitioning{{ExactCashPartitionKey::account, ExactCashPartitionKey::currency}};
  }

  [[nodiscard]] std::span<const ExactCashPartitionKey> keys() const noexcept { return keys_; }
  bool operator==(const ExactCashPartitioning &) const = default;

private:
  explicit ExactCashPartitioning(std::vector<ExactCashPartitionKey> keys)
      : keys_(std::move(keys)) {}

  std::vector<ExactCashPartitionKey> keys_;
};

class ExactCashReductionPolicy {
public:
  [[nodiscard]] static std::expected<ExactCashReductionPolicy, ExactCashReductionError>
  create(std::string id, std::string version) {
    if (!exact_cash_reduction_detail::valid_identifier(id) ||
        !exact_cash_reduction_detail::valid_identifier(version)) {
      return std::unexpected(ExactCashReductionError::invalid_identifier);
    }
    return ExactCashReductionPolicy{std::move(id), std::move(version)};
  }

  [[nodiscard]] const std::string &id() const noexcept { return id_; }
  [[nodiscard]] const std::string &version() const noexcept { return version_; }
  bool operator==(const ExactCashReductionPolicy &) const = default;

private:
  ExactCashReductionPolicy(std::string id, std::string version)
      : id_(std::move(id)), version_(std::move(version)) {}

  std::string id_;
  std::string version_;
};

class ExactCashEvaluationContext {
public:
  [[nodiscard]] static std::expected<ExactCashEvaluationContext, ExactCashReductionError>
  create(std::string id, std::string engine_version, Timestamp recorded_through,
         Timestamp economic_as_of, SettlementDate settlement_as_of_date) {
    if (id.empty() || engine_version.empty())
      return std::unexpected(ExactCashReductionError::incomplete_context);
    if (!exact_cash_reduction_detail::valid_identifier(id) ||
        !exact_cash_reduction_detail::valid_identifier(engine_version)) {
      return std::unexpected(ExactCashReductionError::invalid_identifier);
    }
    return ExactCashEvaluationContext{std::move(id), std::move(engine_version), recorded_through,
                                      economic_as_of, settlement_as_of_date};
  }

  [[nodiscard]] const std::string &id() const noexcept { return id_; }
  [[nodiscard]] const std::string &engine_version() const noexcept { return engine_version_; }
  [[nodiscard]] Timestamp recorded_through() const noexcept { return recorded_through_; }
  [[nodiscard]] Timestamp economic_as_of() const noexcept { return economic_as_of_; }
  [[nodiscard]] SettlementDate settlement_as_of_date() const noexcept {
    return settlement_as_of_date_;
  }
  bool operator==(const ExactCashEvaluationContext &) const = default;

private:
  ExactCashEvaluationContext(std::string id, std::string engine_version, Timestamp recorded_through,
                             Timestamp economic_as_of, SettlementDate settlement_as_of_date)
      : id_(std::move(id)), engine_version_(std::move(engine_version)),
        recorded_through_(recorded_through), economic_as_of_(economic_as_of),
        settlement_as_of_date_(settlement_as_of_date) {}

  std::string id_;
  std::string engine_version_;
  Timestamp recorded_through_;
  Timestamp economic_as_of_;
  SettlementDate settlement_as_of_date_;
};

class ExactCashReductionContract {
public:
  static constexpr std::string_view operation_id = "reduce.cash.exact";

  [[nodiscard]] static std::expected<ExactCashReductionContract, ExactCashReductionError>
  create(CashKey key, std::string operation_version, ExactCashReductionPolicy policy,
         ExactCashEvaluationContext context,
         ExactCashReductionUnit unit = ExactCashReductionUnit::money,
         ExactCashPartitioning partitioning = ExactCashPartitioning::account_currency()) {
    if (!exact_cash_reduction_detail::valid_identifier(key.account().value()) ||
        !exact_cash_reduction_detail::valid_identifier(operation_version)) {
      return std::unexpected(ExactCashReductionError::invalid_identifier);
    }
    return ExactCashReductionContract{
        std::move(key), std::move(operation_version), std::move(policy), std::move(context),
        unit,           std::move(partitioning)};
  }

  [[nodiscard]] const CashKey &key() const noexcept { return key_; }
  [[nodiscard]] const std::string &operation_version() const noexcept { return operation_version_; }
  [[nodiscard]] const ExactCashReductionPolicy &policy() const noexcept { return policy_; }
  [[nodiscard]] const ExactCashEvaluationContext &evaluation_context() const noexcept {
    return context_;
  }
  [[nodiscard]] ExactCashReductionUnit unit() const noexcept { return unit_; }
  [[nodiscard]] const ExactCashPartitioning &partitioning() const noexcept { return partitioning_; }
  bool operator==(const ExactCashReductionContract &) const = default;

private:
  ExactCashReductionContract(CashKey key, std::string operation_version,
                             ExactCashReductionPolicy policy, ExactCashEvaluationContext context,
                             ExactCashReductionUnit unit, ExactCashPartitioning partitioning)
      : key_(std::move(key)), operation_version_(std::move(operation_version)),
        policy_(std::move(policy)), context_(std::move(context)), unit_(unit),
        partitioning_(std::move(partitioning)) {}

  CashKey key_;
  std::string operation_version_;
  ExactCashReductionPolicy policy_;
  ExactCashEvaluationContext context_;
  ExactCashReductionUnit unit_;
  ExactCashPartitioning partitioning_;
};

class ExactCashPartial {
public:
  [[nodiscard]] static std::expected<ExactCashPartial, ExactCashReductionError>
  create(ExactCashReductionContract contract, Money amount, std::vector<EventId> source_event_ids,
         std::vector<SourceRecordId> source_record_ids) {
    if (amount.currency() != contract.key().currency())
      return std::unexpected(ExactCashReductionError::currency_mismatch);
    if (source_event_ids.empty() || source_record_ids.empty())
      return std::unexpected(ExactCashReductionError::incomplete_lineage);
    for (const auto &id : source_event_ids) {
      if (!exact_cash_reduction_detail::valid_identifier(id.value()))
        return std::unexpected(ExactCashReductionError::invalid_identifier);
    }
    for (const auto &id : source_record_ids) {
      if (!exact_cash_reduction_detail::valid_identifier(id.value()))
        return std::unexpected(ExactCashReductionError::invalid_identifier);
    }

    exact_cash_reduction_detail::canonicalize(source_event_ids);
    if (exact_cash_reduction_detail::has_adjacent_duplicate(source_event_ids))
      return std::unexpected(ExactCashReductionError::duplicate_event_lineage);
    exact_cash_reduction_detail::canonicalize(source_record_ids);
    source_record_ids.erase(std::ranges::unique(source_record_ids).begin(),
                            source_record_ids.end());
    return ExactCashPartial{std::move(contract), amount, std::move(source_event_ids),
                            std::move(source_record_ids)};
  }

  [[nodiscard]] const ExactCashReductionContract &contract() const noexcept { return contract_; }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  [[nodiscard]] std::span<const EventId> source_event_ids() const noexcept {
    return source_event_ids_;
  }
  [[nodiscard]] std::span<const SourceRecordId> source_record_ids() const noexcept {
    return source_record_ids_;
  }
  bool operator==(const ExactCashPartial &) const = default;

private:
  ExactCashPartial(ExactCashReductionContract contract, Money amount,
                   std::vector<EventId> source_event_ids,
                   std::vector<SourceRecordId> source_record_ids)
      : contract_(std::move(contract)), amount_(amount),
        source_event_ids_(std::move(source_event_ids)),
        source_record_ids_(std::move(source_record_ids)) {}

  ExactCashReductionContract contract_;
  Money amount_;
  std::vector<EventId> source_event_ids_;
  std::vector<SourceRecordId> source_record_ids_;
};

class ExactCashReductionResult;

[[nodiscard]] std::expected<ExactCashReductionResult, ExactCashReductionError>
exact_cash_zero(const ExactCashReductionContract &contract);

[[nodiscard]] std::expected<ExactCashReductionResult, ExactCashReductionError>
reduce_exact_cash(const ExactCashReductionContract &contract,
                  std::span<const ExactCashPartial> partials);

[[nodiscard]] std::expected<ExactCashReductionResult, ExactCashReductionError>
merge_exact_cash(const ExactCashReductionContract &contract,
                 std::span<const ExactCashReductionResult> partial_results);

class ExactCashReductionResult {
public:
  [[nodiscard]] const ExactCashReductionContract &contract() const noexcept { return contract_; }
  [[nodiscard]] const CashKey &key() const noexcept { return contract_.key(); }
  [[nodiscard]] std::string_view operation_id() const noexcept {
    return ExactCashReductionContract::operation_id;
  }
  [[nodiscard]] const std::string &operation_version() const noexcept {
    return contract_.operation_version();
  }
  [[nodiscard]] const ExactCashReductionPolicy &policy() const noexcept {
    return contract_.policy();
  }
  [[nodiscard]] const ExactCashEvaluationContext &evaluation_context() const noexcept {
    return contract_.evaluation_context();
  }
  [[nodiscard]] ExactCashReductionUnit unit() const noexcept { return contract_.unit(); }
  [[nodiscard]] const ExactCashPartitioning &partitioning() const noexcept {
    return contract_.partitioning();
  }
  [[nodiscard]] Money amount() const noexcept { return amount_; }
  [[nodiscard]] std::span<const EventId> source_event_ids() const noexcept {
    return source_event_ids_;
  }
  [[nodiscard]] std::span<const SourceRecordId> source_record_ids() const noexcept {
    return source_record_ids_;
  }
  bool operator==(const ExactCashReductionResult &) const = default;

private:
  friend std::expected<ExactCashReductionResult, ExactCashReductionError>
  exact_cash_zero(const ExactCashReductionContract &contract);
  friend std::expected<ExactCashReductionResult, ExactCashReductionError>
  reduce_exact_cash(const ExactCashReductionContract &contract,
                    std::span<const ExactCashPartial> partials);
  friend std::expected<ExactCashReductionResult, ExactCashReductionError>
  merge_exact_cash(const ExactCashReductionContract &contract,
                   std::span<const ExactCashReductionResult> partial_results);

  ExactCashReductionResult(ExactCashReductionContract contract, Money amount,
                           std::vector<EventId> source_event_ids,
                           std::vector<SourceRecordId> source_record_ids)
      : contract_(std::move(contract)), amount_(amount),
        source_event_ids_(std::move(source_event_ids)),
        source_record_ids_(std::move(source_record_ids)) {}

  ExactCashReductionContract contract_;
  Money amount_;
  std::vector<EventId> source_event_ids_;
  std::vector<SourceRecordId> source_record_ids_;
};

namespace exact_cash_reduction_detail {

[[nodiscard]] inline std::expected<void, ExactCashReductionError>
validate_supported(const ExactCashReductionContract &contract) {
  if (contract.unit() != ExactCashReductionUnit::money)
    return std::unexpected(ExactCashReductionError::unit_mismatch);
  if (contract.partitioning() != ExactCashPartitioning::account_currency())
    return std::unexpected(ExactCashReductionError::partition_key_mismatch);
  return {};
}

[[nodiscard]] inline std::expected<void, ExactCashReductionError>
validate_compatible(const ExactCashReductionContract &expected,
                    const ExactCashReductionContract &actual) {
  if (expected.key().account() != actual.key().account())
    return std::unexpected(ExactCashReductionError::account_mismatch);
  if (expected.key().currency() != actual.key().currency())
    return std::unexpected(ExactCashReductionError::currency_mismatch);
  if (expected.operation_version() != actual.operation_version())
    return std::unexpected(ExactCashReductionError::operation_version_mismatch);
  if (expected.policy().id() != actual.policy().id())
    return std::unexpected(ExactCashReductionError::policy_id_mismatch);
  if (expected.policy().version() != actual.policy().version())
    return std::unexpected(ExactCashReductionError::policy_version_mismatch);
  if (expected.evaluation_context() != actual.evaluation_context())
    return std::unexpected(ExactCashReductionError::context_mismatch);
  if (expected.unit() != actual.unit())
    return std::unexpected(ExactCashReductionError::unit_mismatch);
  if (expected.partitioning() != actual.partitioning())
    return std::unexpected(ExactCashReductionError::partition_key_mismatch);
  return {};
}

template <class Partial>
[[nodiscard]] inline std::expected<std::pair<std::vector<EventId>, std::vector<SourceRecordId>>,
                                   ExactCashReductionError>
combine_lineage(std::span<const Partial> partials) {
  std::vector<EventId> event_ids;
  std::vector<SourceRecordId> source_record_ids;
  for (const auto &partial : partials) {
    event_ids.insert(event_ids.end(), partial.source_event_ids().begin(),
                     partial.source_event_ids().end());
    source_record_ids.insert(source_record_ids.end(), partial.source_record_ids().begin(),
                             partial.source_record_ids().end());
  }

  canonicalize(event_ids);
  if (has_adjacent_duplicate(event_ids))
    return std::unexpected(ExactCashReductionError::duplicate_event_lineage);
  canonicalize(source_record_ids);
  source_record_ids.erase(std::ranges::unique(source_record_ids).begin(), source_record_ids.end());
  return std::pair{std::move(event_ids), std::move(source_record_ids)};
}

} // namespace exact_cash_reduction_detail

[[nodiscard]] inline std::expected<ExactCashReductionResult, ExactCashReductionError>
exact_cash_zero(const ExactCashReductionContract &contract) {
  const auto supported = exact_cash_reduction_detail::validate_supported(contract);
  if (!supported)
    return std::unexpected(supported.error());
  return ExactCashReductionResult{
      contract, Money::from_scaled(0, contract.key().currency()), {}, {}};
}

[[nodiscard]] inline std::expected<ExactCashReductionResult, ExactCashReductionError>
reduce_exact_cash(const ExactCashReductionContract &contract,
                  std::span<const ExactCashPartial> partials) {
  const auto supported = exact_cash_reduction_detail::validate_supported(contract);
  if (!supported)
    return std::unexpected(supported.error());
  for (const auto &partial : partials) {
    const auto compatible =
        exact_cash_reduction_detail::validate_compatible(contract, partial.contract());
    if (!compatible)
      return std::unexpected(compatible.error());
  }

  auto lineage = exact_cash_reduction_detail::combine_lineage(partials);
  if (!lineage)
    return std::unexpected(lineage.error());

  auto amount = Money::from_scaled(0, contract.key().currency());
  for (const auto &partial : partials) {
    const auto sum = amount.add(partial.amount());
    if (!sum)
      return std::unexpected(ExactCashReductionError::amount_overflow);
    amount = *sum;
  }
  return ExactCashReductionResult{contract, amount, std::move(lineage->first),
                                  std::move(lineage->second)};
}

[[nodiscard]] inline std::expected<ExactCashReductionResult, ExactCashReductionError>
merge_exact_cash(const ExactCashReductionContract &contract,
                 std::span<const ExactCashReductionResult> partial_results) {
  const auto supported = exact_cash_reduction_detail::validate_supported(contract);
  if (!supported)
    return std::unexpected(supported.error());
  for (const auto &partial : partial_results) {
    const auto compatible =
        exact_cash_reduction_detail::validate_compatible(contract, partial.contract());
    if (!compatible)
      return std::unexpected(compatible.error());
  }

  auto lineage = exact_cash_reduction_detail::combine_lineage(partial_results);
  if (!lineage)
    return std::unexpected(lineage.error());

  auto amount = Money::from_scaled(0, contract.key().currency());
  for (const auto &partial : partial_results) {
    const auto sum = amount.add(partial.amount());
    if (!sum)
      return std::unexpected(ExactCashReductionError::amount_overflow);
    amount = *sum;
  }
  return ExactCashReductionResult{contract, amount, std::move(lineage->first),
                                  std::move(lineage->second)};
}

} // namespace luca
