#include <pacioli/ledger.hpp>

int main() {
    const pacioli::Ledger ledger;
    return ledger.empty() ? 0 : 1;
}
