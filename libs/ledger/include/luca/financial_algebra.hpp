#pragma once

#include <algorithm>
#include <expected>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace luca {

enum class FinancialOperationKind { normalization, map, ordered_fold, reduction, comparison };
enum class FinancialOrdering { not_applicable, ordered, unordered };
enum class AlgebraLaw { identity, associativity, commutativity, invertibility, distributivity };
enum class AlgebraLawStatus { unknown, claimed, not_applicable };

// A claim is documentation, never proof or permission to optimize execution.
struct AlgebraLawDeclaration {
  AlgebraLaw law;
  AlgebraLawStatus status{AlgebraLawStatus::unknown};
  std::string domain;
  bool operator==(const AlgebraLawDeclaration &) const = default;
};

// Names describe ports; they do not implement runtime type checking/composition.
struct FinancialAlgebraPort {
  std::string role;
  std::string type_name;
  bool operator==(const FinancialAlgebraPort &) const = default;
};

enum class FinancialAlgebraDeclarationError {
  invalid_enum,
  invalid_identifier,
  invalid_ports,
  invalid_ordering,
  invalid_partition_keys,
  duplicate_law,
  missing_law_domain,
  unsupported_law_claim,
};

[[nodiscard]] constexpr std::string_view
category_name(FinancialAlgebraDeclarationError error) noexcept {
  switch (error) {
  case FinancialAlgebraDeclarationError::invalid_enum: return "invalid_enum";
  case FinancialAlgebraDeclarationError::invalid_identifier: return "invalid_identifier";
  case FinancialAlgebraDeclarationError::invalid_ports: return "invalid_ports";
  case FinancialAlgebraDeclarationError::invalid_ordering: return "invalid_ordering";
  case FinancialAlgebraDeclarationError::invalid_partition_keys: return "invalid_partition_keys";
  case FinancialAlgebraDeclarationError::duplicate_law: return "duplicate_law";
  case FinancialAlgebraDeclarationError::missing_law_domain: return "missing_law_domain";
  case FinancialAlgebraDeclarationError::unsupported_law_claim: return "unsupported_law_claim";
  }
  return "invalid_enum";
}

namespace financial_algebra_detail {
[[nodiscard]] inline bool token(std::string_view value) noexcept {
  return !value.empty() && std::ranges::all_of(value, [](unsigned char byte) {
    return byte > 0x20 && byte != 0x7f;
  });
}

[[nodiscard]] inline bool distinct_tokens(const std::vector<std::string> &values) {
  for (auto it = values.begin(); it != values.end(); ++it) {
    if (!token(*it) || std::find(values.begin(), it, *it) != it)
      return false;
  }
  return true;
}
} // namespace financial_algebra_detail

// Owns its strings/vectors and exposes only const access after validation.
// This deliberately has no executor, registry, proof flag or optimizer API.
class FinancialAlgebraDescriptor {
public:
  struct Definition {
    FinancialOperationKind kind{FinancialOperationKind::map};
    std::string operation_id;
    std::string operation_version;
    std::string policy_id;
    std::string policy_version;
    std::vector<FinancialAlgebraPort> inputs;
    FinancialAlgebraPort output;
    FinancialOrdering ordering{FinancialOrdering::not_applicable};
    std::vector<std::string> ordering_keys;
    bool partitioned{false};
    std::vector<std::string> partition_keys;
    std::vector<AlgebraLawDeclaration> laws;
    bool operator==(const Definition &) const = default;
  };

  [[nodiscard]] static std::expected<FinancialAlgebraDescriptor, FinancialAlgebraDeclarationError>
  create(Definition definition) {
    using Error = FinancialAlgebraDeclarationError;
    using financial_algebra_detail::token;
    using financial_algebra_detail::distinct_tokens;
    switch (definition.kind) {
    case FinancialOperationKind::normalization:
    case FinancialOperationKind::map:
    case FinancialOperationKind::ordered_fold:
    case FinancialOperationKind::reduction:
    case FinancialOperationKind::comparison: break;
    default: return std::unexpected(Error::invalid_enum);
    }
    switch (definition.ordering) {
    case FinancialOrdering::not_applicable:
    case FinancialOrdering::ordered:
    case FinancialOrdering::unordered: break;
    default: return std::unexpected(Error::invalid_enum);
    }
    if (!token(definition.operation_id) || !token(definition.operation_version) ||
        !token(definition.policy_id) || !token(definition.policy_version))
      return std::unexpected(Error::invalid_identifier);
    if (definition.inputs.empty() || !token(definition.output.role) ||
        !token(definition.output.type_name))
      return std::unexpected(Error::invalid_ports);
    std::vector<std::string> roles;
    for (const auto &port : definition.inputs) {
      if (!token(port.type_name))
        return std::unexpected(Error::invalid_ports);
      roles.push_back(port.role);
    }
    if (!distinct_tokens(roles))
      return std::unexpected(Error::invalid_ports);
    if (definition.kind == FinancialOperationKind::comparison &&
        (roles.size() != 2 || std::ranges::find(roles, "projected") == roles.end() ||
         std::ranges::find(roles, "observed") == roles.end()))
      return std::unexpected(Error::invalid_ports);
    if (!distinct_tokens(definition.ordering_keys) ||
        ((definition.ordering == FinancialOrdering::ordered) !=
         !definition.ordering_keys.empty()) ||
        (definition.kind == FinancialOperationKind::ordered_fold &&
         definition.ordering != FinancialOrdering::ordered))
      return std::unexpected(Error::invalid_ordering);
    if (!distinct_tokens(definition.partition_keys) ||
        (definition.partitioned != !definition.partition_keys.empty()))
      return std::unexpected(Error::invalid_partition_keys);

    std::vector<AlgebraLaw> seen;
    for (const auto &declaration : definition.laws) {
      switch (declaration.law) {
      case AlgebraLaw::identity:
      case AlgebraLaw::associativity:
      case AlgebraLaw::commutativity:
      case AlgebraLaw::invertibility:
      case AlgebraLaw::distributivity: break;
      default: return std::unexpected(Error::invalid_enum);
      }
      switch (declaration.status) {
      case AlgebraLawStatus::unknown:
      case AlgebraLawStatus::claimed:
      case AlgebraLawStatus::not_applicable: break;
      default: return std::unexpected(Error::invalid_enum);
      }
      if (std::ranges::find(seen, declaration.law) != seen.end())
        return std::unexpected(Error::duplicate_law);
      seen.push_back(declaration.law);
      if (declaration.status != AlgebraLawStatus::claimed)
        continue;
      if (std::ranges::none_of(declaration.domain, [](unsigned char byte) {
            return byte > 0x20 && byte != 0x7f;
          }))
        return std::unexpected(Error::missing_law_domain);
      // First increment only describes reduction identity/association/permutation.
      // An inverse or distributive claim needs additional operand contracts.
      if (definition.kind != FinancialOperationKind::reduction ||
          declaration.law == AlgebraLaw::invertibility ||
          declaration.law == AlgebraLaw::distributivity)
        return std::unexpected(Error::unsupported_law_claim);
    }
    return FinancialAlgebraDescriptor{std::move(definition)};
  }

  [[nodiscard]] const Definition &definition() const noexcept { return definition_; }

  // An omitted law is unknown, never implicitly true.
  [[nodiscard]] AlgebraLawStatus law_status(AlgebraLaw law) const noexcept {
    for (const auto &declaration : definition_.laws) {
      if (declaration.law == law)
        return declaration.status;
    }
    return AlgebraLawStatus::unknown;
  }
  bool operator==(const FinancialAlgebraDescriptor &) const = default;

private:
  explicit FinancialAlgebraDescriptor(Definition definition) : definition_(std::move(definition)) {}
  Definition definition_;
};

} // namespace luca
