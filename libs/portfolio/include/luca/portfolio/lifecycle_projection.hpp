#pragma once

#include "luca/lifecycle.hpp"
#include "luca/portfolio/cash_projection.hpp"
#include "luca/portfolio/position_projection.hpp"
#include "luca/portfolio/settlement_projection.hpp"

#include <chrono>
#include <exception>
#include <expected>
#include <vector>

namespace luca {

struct LifecycleProjectionContext {
  Timestamp economic_as_of;
  std::chrono::year_month_day settlement_as_of_date;
};

// Every result is evaluated even when another projection reports an error, and
// each projection retains its existing public error type.
struct LifecycleProjectionResult {
  std::expected<std::vector<Position>, PositionProjectionError> positions;
  std::expected<std::vector<CashBalance>, CashProjectionError> settled_cash;
  std::expected<std::vector<SettlementObligation>, SettlementProjectionError>
      open_settlement_obligations;
};

// Lifecycle selection and validation belong to LifecycleLedger::resolve. This
// adapter consumes only its ordered active set, materializes it once through the
// existing Ledger API, and supplies that identical set and context to every
// existing portfolio projection. The resolution should be produced with the
// same economic cutoff; an earlier resolution cutoff cannot be widened here.
[[nodiscard]] inline LifecycleProjectionResult
project_lifecycle(const LifecycleResolution &resolution, LifecycleProjectionContext context) {
  Ledger active_ledger;
  for (const auto &resolved : resolution.active_events()) {
    // Lifecycle resolution guarantees globally unique record IDs. A reachable
    // failure would therefore indicate a violated core invariant rather than a
    // recoverable projection error.
    if (!active_ledger.append(resolved.event()))
      std::terminate();
  }

  return LifecycleProjectionResult{
      .positions = project_positions(active_ledger.entries(), context.economic_as_of),
      .settled_cash = project_cash(
          active_ledger.entries(),
          CashProjectionContext{context.economic_as_of, context.settlement_as_of_date}),
      .open_settlement_obligations = project_settlement_obligations(
          active_ledger.entries(),
          SettlementProjectionContext{context.economic_as_of, context.settlement_as_of_date}),
  };
}

} // namespace luca
