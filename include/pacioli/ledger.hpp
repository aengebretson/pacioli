#pragma once

namespace pacioli {

// v0.1 intentionally starts with a minimal public surface.
// Domain primitives and ledger semantics will be added incrementally.
class Ledger {
public:
    [[nodiscard]] constexpr bool empty() const noexcept { return true; }
};

} // namespace pacioli
