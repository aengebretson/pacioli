#pragma once

#include "luca/portfolio/exact_cash_reduction.hpp"
#include "luca/reconciliation/cash_observation.hpp"

#include <algorithm>
#include <expected>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca {

enum class ExactCashComparisonError {
  invalid_identifier,
  incomplete_operation_identity,
  incomplete_policy_identity,
  duplicate_projected_key,
  duplicate_observation,
  account_mismatch,
  currency_mismatch,
  observation_time_mismatch,
  observation_settlement_date_mismatch,
  context_mismatch,
  amount_overflow,
};

[[nodiscard]] constexpr std::string_view category_name(ExactCashComparisonError error) noexcept {
  switch (error) {
  case ExactCashComparisonError::invalid_identifier:
    return "invalid_identifier";
  case ExactCashComparisonError::incomplete_operation_identity:
    return "incomplete_operation_identity";
  case ExactCashComparisonError::incomplete_policy_identity:
    return "incomplete_policy_identity";
  case ExactCashComparisonError::duplicate_projected_key:
    return "duplicate_projected_key";
  case ExactCashComparisonError::duplicate_observation:
    return "duplicate_observation";
  case ExactCashComparisonError::account_mismatch:
    return "account_mismatch";
  case ExactCashComparisonError::currency_mismatch:
    return "currency_mismatch";
  case ExactCashComparisonError::observation_time_mismatch:
    return "observation_time_mismatch";
  case ExactCashComparisonError::observation_settlement_date_mismatch:
    return "observation_settlement_date_mismatch";
  case ExactCashComparisonError::context_mismatch:
    return "context_mismatch";
  case ExactCashComparisonError::amount_overflow:
    return "amount_overflow";
  }
  return "invalid_identifier";
}

enum class ExactCashBreakKind {
  missing_observation,
  unexpected_observation,
  amount_mismatch,
};

[[nodiscard]] constexpr std::string_view category_name(ExactCashBreakKind kind) noexcept {
  switch (kind) {
  case ExactCashBreakKind::missing_observation:
    return "missing_observation";
  case ExactCashBreakKind::unexpected_observation:
    return "unexpected_observation";
  case ExactCashBreakKind::amount_mismatch:
    return "amount_mismatch";
  }
  return "amount_mismatch";
}

namespace exact_cash_comparison_detail {

[[nodiscard]] inline bool valid_identifier(std::string_view value) noexcept {
  if (value.empty())
    return false;
  return std::ranges::all_of(value, [](unsigned char byte) { return byte > 0x20 && byte != 0x7f; });
}

} // namespace exact_cash_comparison_detail

class ExactCashComparisonPolicy {
public:
  [[nodiscard]] static std::expected<ExactCashComparisonPolicy, ExactCashComparisonError>
  create(std::string id, std::string version) {
    if (id.empty() || version.empty())
      return std::unexpected(ExactCashComparisonError::incomplete_policy_identity);
    if (!exact_cash_comparison_detail::valid_identifier(id) ||
        !exact_cash_comparison_detail::valid_identifier(version)) {
      return std::unexpected(ExactCashComparisonError::invalid_identifier);
    }
    return ExactCashComparisonPolicy{std::move(id), std::move(version)};
  }

  [[nodiscard]] const std::string &id() const noexcept { return id_; }
  [[nodiscard]] const std::string &version() const noexcept { return version_; }
  bool operator==(const ExactCashComparisonPolicy &) const = default;

private:
  ExactCashComparisonPolicy(std::string id, std::string version)
      : id_(std::move(id)), version_(std::move(version)) {}

  std::string id_;
  std::string version_;
};

class ExactCashComparisonContract {
public:
  static constexpr std::string_view operation_id = "compare.cash.exact";

  [[nodiscard]] static std::expected<ExactCashComparisonContract, ExactCashComparisonError>
  create(std::string operation_version, ExactCashComparisonPolicy policy,
         ExactCashEvaluationContext context) {
    if (operation_version.empty())
      return std::unexpected(ExactCashComparisonError::incomplete_operation_identity);
    if (!exact_cash_comparison_detail::valid_identifier(operation_version))
      return std::unexpected(ExactCashComparisonError::invalid_identifier);
    return ExactCashComparisonContract{std::move(operation_version), std::move(policy),
                                       std::move(context)};
  }

  [[nodiscard]] const std::string &operation_version() const noexcept { return operation_version_; }
  [[nodiscard]] const ExactCashComparisonPolicy &policy() const noexcept { return policy_; }
  [[nodiscard]] const ExactCashEvaluationContext &evaluation_context() const noexcept {
    return context_;
  }
  bool operator==(const ExactCashComparisonContract &) const = default;

private:
  ExactCashComparisonContract(std::string operation_version, ExactCashComparisonPolicy policy,
                              ExactCashEvaluationContext context)
      : operation_version_(std::move(operation_version)), policy_(std::move(policy)),
        context_(std::move(context)) {}

  std::string operation_version_;
  ExactCashComparisonPolicy policy_;
  ExactCashEvaluationContext context_;
};

class ExactCashComparisonResult;

class ExactCashBreak;

[[nodiscard]] std::expected<ExactCashComparisonResult, ExactCashComparisonError>
compare_exact_cash(const ExactCashComparisonContract &contract,
                   std::span<const ExactCashReductionResult> projected,
                   std::span<const CashObservation> observed);

class ExactCashBreak {
public:
  [[nodiscard]] const CashKey &key() const noexcept { return key_; }
  [[nodiscard]] ExactCashBreakKind kind() const noexcept { return kind_; }
  [[nodiscard]] const std::optional<Money> &expected() const noexcept { return expected_; }
  [[nodiscard]] const std::optional<Money> &observed() const noexcept { return observed_; }
  [[nodiscard]] const std::optional<Money> &difference() const noexcept { return difference_; }
  [[nodiscard]] const std::optional<ExactCashReductionResult> &projection() const noexcept {
    return projection_;
  }
  [[nodiscard]] const std::optional<CashObservation> &observation() const noexcept {
    return observation_;
  }
  [[nodiscard]] std::span<const EventId> projection_source_event_ids() const noexcept {
    if (!projection_)
      return {};
    return projection_->source_event_ids();
  }
  [[nodiscard]] std::span<const SourceRecordId> projection_source_record_ids() const noexcept {
    if (!projection_)
      return {};
    return projection_->source_record_ids();
  }
  [[nodiscard]] const std::optional<Provenance> &observation_provenance() const noexcept {
    return observation_provenance_;
  }
  bool operator==(const ExactCashBreak &) const = default;

private:
  friend class ExactCashComparisonResult;
  friend std::expected<ExactCashComparisonResult, ExactCashComparisonError>
  compare_exact_cash(const ExactCashComparisonContract &contract,
                     std::span<const ExactCashReductionResult> projected,
                     std::span<const CashObservation> observed);

  [[nodiscard]] static ExactCashBreak missing(ExactCashReductionResult projection) {
    return ExactCashBreak{projection.key(),    ExactCashBreakKind::missing_observation,
                          projection.amount(), std::nullopt,
                          std::nullopt,        std::move(projection),
                          std::nullopt};
  }

  [[nodiscard]] static ExactCashBreak unexpected(CashObservation observation) {
    return ExactCashBreak{observation.key(),     ExactCashBreakKind::unexpected_observation,
                          std::nullopt,          observation.amount(),
                          std::nullopt,          std::nullopt,
                          std::move(observation)};
  }

  [[nodiscard]] static ExactCashBreak mismatch(ExactCashReductionResult projection,
                                               CashObservation observation, Money difference) {
    return ExactCashBreak{projection.key(),
                          ExactCashBreakKind::amount_mismatch,
                          projection.amount(),
                          observation.amount(),
                          difference,
                          std::move(projection),
                          std::move(observation)};
  }

  ExactCashBreak(CashKey key, ExactCashBreakKind kind, std::optional<Money> expected,
                 std::optional<Money> observed, std::optional<Money> difference,
                 std::optional<ExactCashReductionResult> projection,
                 std::optional<CashObservation> observation)
      : key_(std::move(key)), kind_(kind), expected_(expected), observed_(observed),
        difference_(difference), projection_(std::move(projection)),
        observation_(std::move(observation)),
        observation_provenance_(observation_ ? std::optional{observation_->provenance()}
                                             : std::nullopt) {}

  CashKey key_;
  ExactCashBreakKind kind_;
  std::optional<Money> expected_;
  std::optional<Money> observed_;
  std::optional<Money> difference_;
  std::optional<ExactCashReductionResult> projection_;
  std::optional<CashObservation> observation_;
  std::optional<Provenance> observation_provenance_;
};

class ExactCashComparisonResult {
public:
  [[nodiscard]] const ExactCashComparisonContract &contract() const noexcept { return contract_; }
  [[nodiscard]] std::string_view operation_id() const noexcept {
    return ExactCashComparisonContract::operation_id;
  }
  [[nodiscard]] const std::string &operation_version() const noexcept {
    return contract_.operation_version();
  }
  [[nodiscard]] const ExactCashComparisonPolicy &policy() const noexcept {
    return contract_.policy();
  }
  [[nodiscard]] const ExactCashEvaluationContext &evaluation_context() const noexcept {
    return contract_.evaluation_context();
  }
  [[nodiscard]] std::span<const ExactCashBreak> breaks() const noexcept { return breaks_; }
  bool operator==(const ExactCashComparisonResult &) const = default;

private:
  friend std::expected<ExactCashComparisonResult, ExactCashComparisonError>
  compare_exact_cash(const ExactCashComparisonContract &contract,
                     std::span<const ExactCashReductionResult> projected,
                     std::span<const CashObservation> observed);

  ExactCashComparisonResult(ExactCashComparisonContract contract,
                            std::vector<ExactCashBreak> breaks)
      : contract_(std::move(contract)), breaks_(std::move(breaks)) {}

  ExactCashComparisonContract contract_;
  std::vector<ExactCashBreak> breaks_;
};

[[nodiscard]] inline std::expected<ExactCashComparisonResult, ExactCashComparisonError>
compare_exact_cash(const ExactCashComparisonContract &contract,
                   std::span<const ExactCashReductionResult> projected,
                   std::span<const CashObservation> observed) {
  std::map<CashKey, std::size_t> projection_index;
  for (std::size_t index = 0; index < projected.size(); ++index) {
    const auto &projection = projected[index];
    if (!exact_cash_comparison_detail::valid_identifier(projection.key().account().value()))
      return std::unexpected(ExactCashComparisonError::account_mismatch);
    if (projection.key().currency() != projection.amount().currency())
      return std::unexpected(ExactCashComparisonError::currency_mismatch);
    if (projection.evaluation_context() != contract.evaluation_context())
      return std::unexpected(ExactCashComparisonError::context_mismatch);
    if (!projection_index.emplace(projection.key(), index).second)
      return std::unexpected(ExactCashComparisonError::duplicate_projected_key);
  }

  std::map<CashKey, std::size_t> observation_index;
  for (std::size_t index = 0; index < observed.size(); ++index) {
    const auto &observation = observed[index];
    if (!exact_cash_comparison_detail::valid_identifier(observation.key().account().value()))
      return std::unexpected(ExactCashComparisonError::account_mismatch);
    if (observation.key().currency() != observation.amount().currency())
      return std::unexpected(ExactCashComparisonError::currency_mismatch);
    if (observation.as_of() != contract.evaluation_context().economic_as_of())
      return std::unexpected(ExactCashComparisonError::observation_time_mismatch);
    if (observation.settlement_as_of_date() !=
        contract.evaluation_context().settlement_as_of_date().value()) {
      return std::unexpected(ExactCashComparisonError::observation_settlement_date_mismatch);
    }
    if (!observation_index.emplace(observation.key(), index).second)
      return std::unexpected(ExactCashComparisonError::duplicate_observation);
  }

  std::vector<ExactCashBreak> breaks;
  breaks.reserve(projected.size() + observed.size());
  for (const auto &[key, projection_position] : projection_index) {
    const auto observation_position = observation_index.find(key);
    if (observation_position == observation_index.end()) {
      breaks.push_back(ExactCashBreak::missing(projected[projection_position]));
      continue;
    }

    const auto &projection = projected[projection_position];
    const auto &observation = observed[observation_position->second];
    if (projection.amount() == observation.amount())
      continue;
    const auto difference = observation.amount().subtract(projection.amount());
    if (!difference)
      return std::unexpected(ExactCashComparisonError::amount_overflow);
    breaks.push_back(ExactCashBreak::mismatch(projection, observation, *difference));
  }
  for (const auto &[key, observation_position] : observation_index) {
    if (!projection_index.contains(key))
      breaks.push_back(ExactCashBreak::unexpected(observed[observation_position]));
  }

  std::ranges::sort(breaks, [](const ExactCashBreak &left, const ExactCashBreak &right) {
    if (left.key() != right.key())
      return left.key() < right.key();
    return left.kind() < right.kind();
  });
  return ExactCashComparisonResult{contract, std::move(breaks)};
}

} // namespace luca
